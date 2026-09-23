# JARVIS-API — the client side of the contract, reconstructed

**Read this paragraph before you trust anything else on this page.**

Eight files in this repository cite `docs/JARVIS-API.md` as the authoritative
contract — `CLAUDE.md`, the top-level `README.md`, `ApiModels.kt`,
`TokenStore.kt`, `stream.rs`, `main.js` and others. That file has never
existed. Checked on 2026-09-20: it is not in the working tree, and
`git log --all -- "**/JARVIS-API.md"` returns **zero** commits — it was never
added and never deleted. So every "§4 says…" comment in this codebase points
at a document nobody here has. This page is an attempt to fill that hole
honestly, not to pretend the hole was never there.

## What this is

A list of every HTTP call the two Jarvis clients actually make, read out of
their source code, with the file and line number of each call site so you can
check any line of it yourself.

## What this is NOT

- **It is not the backend's contract.** The Python backend (`jarvis_hud.py`
  and friends) lives on the owner's Windows machine, outside this repository —
  `docs/ARCHITECTURE.md` §9 says where. Nobody writing this page could read it.
- **It describes what the clients EXPECT, not what the server GUARANTEES.**
  A row below saying a route takes `{"id": …}` means "the phone sends that",
  not "the server accepts that".
- **Where the backend disagrees, the backend wins.** Every time. That is
  already the project's standing rule — `docs/API-DISAGREEMENTS.md` opens by
  quoting it: *"Where the docs and `jarvis_hud.py` disagree, the code wins."*
  If you find a difference, fix the client and add a line to that file.
- **It is not a licence to build against.** Several routes here are marked
  DRAFT because the client author invented a plausible name and said so in a
  comment. Those are guesses. They are listed so nobody mistakes them for
  facts.

Where a real document already covers something, this page points at it rather
than restating it: `docs/CROSS-CLIENT-CONTRACT.md` (the four decisions neither
client can take alone), `docs/APPEARANCE-API.md` (the appearance document's
full schema), `docs/API-DISAGREEMENTS.md` (where the old prose was wrong), and
`docs/ARCHITECTURE.md` (the permission model every feature has to use).

---

## 1. Authentication and the two headers

Every request to the backend carries two headers.

| Header | Value | Why |
|---|---|---|
| `X-Jarvis-Token` | the pairing token | The actual credential. |
| `X-Jarvis-Client` | the literal string `hud` | Gets past the server's origin check. |

**`X-Jarvis-Client` is not identity.** The server checks where a request came
from (its "origin") *before* it checks the token, and a native app — a phone
app, or a Tauri window — sends no origin at all. This header is what tells the
check "first-party, let it through". It proves nothing: anything can send the
word `hud`. `docs/CROSS-CLIENT-CONTRACT.md` §1 spells out the consequence —
the server cannot tell the laptop from the phone, so no per-device permission
scheme can be built on it.

Sent by:
- Android: `jarvis-client/app/src/main/java/com/jarvis/client/net/JarvisApi.kt:257`
  (`Request.Builder.authed()`); header names at `JarvisApi.kt:723-724`, and the
  value `hud` with its reasoning at `JarvisApi.kt:726-733`.
- Desktop: `jarvis-desktop/src-tauri/src/commands.rs:34`
  (`const JARVIS_CLIENT: &str = "hud"`), applied by `jarvis_headers()`.

**The token is never logged.** Not in a log line, not in a URL, not in a query
string. `stream.rs:331-334` gives the reason in its own words: the resume point
is sent as a *header* rather than `?since=` partly because "the token also
travels as a header here, and putting either in a URL is how they end up in a
log."

One caveat, from `docs/API-DISAGREEMENTS.md` §5: the backend's own check admits
any request from the same machine when no token is configured at all, and
reports that honestly as `auth.token_required: false`. Both clients send the
token regardless whenever they have one.

### What the errors mean

The Android client maps status codes to plain sentences at `JarvisApi.kt:694-704`:

| Code | Means | Not |
|---|---|---|
| 401 / 403 | The token was refused. | "The desktop is down." |
| 404 | This backend does not have that route. | "Wrong address." |
| 409 | Already decided, expired, or unknown id. | An error worth a red banner — routine when both clients are open. |
| 503 | That subsystem is not installed here. | "The desktop is broken." |
| 501 | Writing is not allowed on this route (`/api/config`). | Anything temporary. |

There is also a body-level signal: a read that answers `{"available": false}`
means *the thing behind this route is not running* — which is a different
sentence from "the list is empty", and the Android parser checks for it before
anything else (`JarvisApi.kt:136`). An empty approval queue is reassuring;
a missing approval queue is not, and they must not look the same.

---

## 2. The event stream

One long-lived connection carries the news. It is **Server-Sent Events** (SSE)
— an HTTP response that never finishes, with the server writing small text
frames down it as things happen.

`GET /api/events`

- Desktop: `jarvis-desktop/src-tauri/src/stream.rs:345`
- Android: `jarvis-client/.../net/EventStream.kt:133`

### Resuming

Both clients resume with the **`Last-Event-ID` request header**, carrying the
id of the last frame they saw — not a `?since=` query parameter.

- Desktop: `stream.rs:336` (and the reasoning at `stream.rs:331-334`)
- Android: `EventStream.kt:139`

The desktop persists that id to disk (`RESUME_KEY = "events.last_id"`,
`stream.rs:68`), so restarting the app resumes rather than starting over.

### Keepalives, and how each client decides the link is dead

The server sends a bare SSE comment line (`: keepalive`) roughly every 20
seconds so a quiet connection can be told from a dead one. The two clients
handle silence differently, and both numbers are deliberate:

| | Silence limit | Mechanism |
|---|---|---|
| Desktop | **70 s** (`stream.rs:54`, `SILENCE_TIMEOUT`) | Three missed keepalives, with room for a stalled laptop. |
| Android | **90 s** (`JarvisApi.kt:239-241`, `streamClient`) plus its own watchdog | An OkHttp *read* timeout — four missed keepalives — so a half-open socket actually fails its read and reconnects. |

The Android note at `JarvisApi.kt:220-241` is worth reading if you touch this:
a stream with no read timeout cannot fail, so a phone that lost its radio
mid-stream would latch "stale" for ever and never reconnect. The keepalive must
reach the watchdog too — `SseParser.kt:24-36` records that a comment line used
to be silently skipped, which made a healthy idle link look dead after 70
seconds.

### `hello`

The first frame on every connection. Four fields, per
`docs/API-DISAGREEMENTS.md` §3: `resumed_from`, `stale`, `latest`, `retry_ms`.

**`stale: true` means "re-fetch everything, do not replay".** It is the field
with teeth: while the link is stale, nothing may be approved (see §7 below).

`hello` does **not** carry the current activity, despite older prose saying it
did. The desktop reads `GET /api/version` for that instead
(`API-DISAGREEMENTS.md` §3).

### `retry:`

The server can send a `retry:` line telling the client how long to wait before
reconnecting. Both clients clamp it. Android's comment at `EventStream.kt:193-200`
explains why: the raw value was used unchecked, and `0` removed the backoff
entirely while a huge value overflowed and came out negative — "a field meant
to SLOW reconnection produced the fastest possible loop."

### Event kinds

**An event is a doorbell, not a database.** It says *something changed*; the
client then re-fetches the real endpoint. Both clients say this in the same
words (`stream.rs:18-20`, `JarvisRuntime.kt:662-665`).

| Kind | Desktop does | Android does |
|---|---|---|
| `hello` | Reads link state, re-fetches on `stale` (`stream.rs:452`) | Nothing — arrives as `Signal.Open` instead (`JarvisRuntime.kt:700`) |
| `approval` | Re-fetches `/api/pending` once for all three surfaces (`stream.rs:518`) | Re-fetches pending (`JarvisRuntime.kt:668`) |
| `attention` | Applies the payload directly (`stream.rs:511`) | Re-fetches `/api/attention` (`JarvisRuntime.kt:669`) |
| `activity` | Updates activity + detail (`stream.rs:520`) | Reads `activity_detail` off the event, re-fetches status (`JarvisRuntime.kt:670-679`) |
| `power` | Updates power mode (`stream.rs:529`) | Re-fetches status (`JarvisRuntime.kt:682`) |
| `persona` | Fanned out verbatim | Re-fetches status (`JarvisRuntime.kt:682`) |
| `finding` | Fanned out verbatim | Ignored — the digest covers these (`JarvisRuntime.kt:683`) |
| `model` | Fanned out verbatim | Re-reads the model list (`JarvisRuntime.kt:689`) |
| `voice` | Fanned out verbatim | Ignored (`JarvisRuntime.kt:690`) |
| `job` | Fanned out verbatim | Falls through to "unhandled" |
| `proposal` | Rendered in the Brain pane (`brain.js:1496`) | Ignored (`JarvisRuntime.kt:701`) |
| `appearance` | — | Re-reads the shared document (`JarvisRuntime.kt:707`) |

`attention` is the one kind that carries its own state instead of ringing a
bell (`stream.rs:506-511`).

Note: the `approval` event carries `count`, and `event-allowlist.patch` is
explicit that the queue itself is fetched from `/api/pending` — **not**
`/api/approvals`, which does not exist (`backend/extraction-wiring.patch:342-345`).

---

## 3. Approvals and the pending queue

| Endpoint | Method | Body / params | Desktop | Android | Notes |
|---|---|---|---|---|---|
| `/api/pending` | GET | — | `stream.rs:641`, `brain/routes.rs` (not listed; fetched by the stream) | `JarvisApi.kt:274` | Answers `{"available", "pending", "history"}`. **Not a bare array.** |
| `/api/approve` | POST | see below | `commands.rs:954` | `JarvisApi.kt:395` | **The two clients send different bodies.** |
| `/api/deny` | POST | see below | `commands.rs:954` | `JarvisApi.kt:397` | Same. |
| `/api/pending/<id>/amend` | POST | `{"note": "…"}` | via `amend_approval` (`jarvis-link.js:429`) | `JarvisApi.kt:339` | **DRAFT — invented name.** See §8. |

### The list-key trap

`/api/pending` does not answer a bare array. It answers an object, and each
list route uses a *different key*: `pending`, `digest`, `shelf`, `jobs` —
only `/api/initiative` uses `items`. The Android keys are at
`JarvisApi.kt:715-718`.

The comment at `JarvisApi.kt:75-110` is the best thing in this repo to read
before touching list parsing. In short: an earlier version guessed `items`,
found nothing, and showed an empty queue while approvals were waiting — which
looks exactly like a quiet backend. The fix guessed *better* and got worse: a
body with only `history` in it decoded cleanly as a pending list, because
`PendingItem` needs only an `id`, so already-decided items appeared as waiting
and approving one would have posted a verdict on a request closed days ago.
The current parser refuses names that mean "already dealt with"
(`ALREADY_HANDLED_KEYS`, `JarvisApi.kt:113`).

### Approve/deny bodies — the clients disagree

```
Desktop  →  {"id": "<id>", "by": "desktop_spotlight"}      commands.rs:914-916, 954-958
Android  →  {"id": "<id>"}                                  JarvisApi.kt:395, 484
```

The desktop adds `by` so the server can record which machine the human was
sitting at. The phone sends no such field, so a decision made from the phone is
attributed to nothing. Neither client knows whether the server reads `by` at
all. See §7.

A **409** from either route means "already decided, expired, or unknown id"
(`commands.rs:853-855`) — routine when both clients are open, and the Android
client gives it its own named outcome rather than rendering it as a failure
(`JarvisApi.kt:501`).

### Approving with a choice

A pending item can carry an `options` list. When there are two or more, a bare
approve no longer names which plan — `ApiModels.kt:294-302`. The phone
therefore disables approve (but keeps deny, "refusing is always the safe
direction") until a route exists that takes the choice. The desktop's
`jarvis-link.js:403-404` *does* pass an `option_id` argument, but see §8: the
Rust command it calls does not accept one — so as of this writing, **neither**
client can actually send a choice, even though the desktop used to render
one clickable button per option as if it could. `main.js`/`widget.js` now
render those buttons disabled, with a tooltip pointing here, until a real
decide-with-option route exists on the server (see §8's own note on this).

---

## 4. Chat

| Endpoint | Method | Body | Desktop | Android | Notes |
|---|---|---|---|---|---|
| `/api/chat` | POST | **different on each client** | `commands.rs:836` (streaming), `commands.rs:1293` (quick capture) | `JarvisApi.kt:661` | See below. |

**This is the biggest client-vs-client difference in the whole API.**

```
Desktop  →  {"messages": [{"role": …, "content": …}, …],
             "has_image": false, "stream": true, "auto": true}     commands.rs:801-806
Android  →  {"message": "<text>"}                                  JarvisApi.kt:662-663
```

The desktop sends an OpenAI-style message array; the phone sends a single
string under a different key. Both cannot be right. The desktop's note at
`commands.rs:778-781` says the backend's `_build_payload` forwards only
`model / messages / stream / temperature / …`, which suggests the desktop's
shape is the real one — but that is the desktop session reading the backend,
reported here as evidence, not as a verdict. Do not change the phone on the
strength of this page alone; check `jarvis_hud.py`.

**Framing.** Android treats the reply as a chunked HTTP body, "**not** SSE,
whatever the shape suggests" (`JarvisApi.kt:653-659`). The desktop handles
both, because `docs/API-DISAGREEMENTS.md` §4 found the route copies the
upstream `Content-Type` verbatim, so an SSE-framed upstream produces
`data:`-framed chunks here too. The phone would mis-read that.

**Cancelling.** Android cancels the OkHttp `Call` (`JarvisApi.kt:660-667`);
the desktop drops the request future (`commands.rs:823-826`). Either way the
server sees the client go immediately.

**Timeouts.** Android gives chat a 120-second *read* timeout, not a call
timeout — the clock restarts on every byte, so a four-minute reply is fine but
two minutes of silence is a wedge (`JarvisApi.kt:192-215`).

**`turn_id` in `X-Jarvis-Route`** (`feedback.patch`). The chat response's
`X-Jarvis-Route` header (JSON) now carries `turn_id`, a 32-character hex id
for this answer. Show a right/wrong mark on the answer only when it is there,
and post it to `/api/feedback/mark` (§6). Missing means an older backend or
that recording failed - show no mark buttons. Neither client's chat code was
checked for whether it passes response headers through to the screen; if it
does not, it will need to.

**No tool receipt.** A 200 from `/api/chat` means "a chat completed", not
"the thing you asked for happened". There is no `tool_calls` field on the
response. `docs/API-DISAGREEMENTS.md` §10 records the consequence: the quick-
capture widget used to say "Appended to Logseq." on any 200, and now reports
only what Jarvis itself said it did.

---

## 5. Voice

| Endpoint | Method | Body / params | Desktop | Android | Notes |
|---|---|---|---|---|---|
| `/api/voice/status` | GET | — | **no** | `JarvisApi.kt:553` | Phone calls it before showing a mic button; failure returns refusing defaults. |
| `/api/voice/utterance` | POST | **WAV bytes**, `?source=push_to_talk\|wake_word` | `voice.rs:335` | `JarvisApi.kt:574` | The one route whose body is not JSON. |
| `/api/voice/say` | POST | `{"text": …}` → WAV bytes | `voice.rs:716` | `JarvisApi.kt:601` | **503 is a legitimate answer.** |
| `/api/voice/wake` | POST | `{"enabled": bool}` | **no** | `JarvisApi.kt:651` | Phone-only. |

**The audio format is fixed and the server will not convert.** 16 kHz,
16-bit, mono PCM in a WAV container, resampled on the client. The phone's
comment at `JarvisApi.kt:556-562` gives the reason: these are bytes arriving
from the network *before* the gate, and a resampler is the last thing that
code should be carrying.

**503 from `/api/voice/say` means "there is no speech engine here", not
"failed."** Speaking text the client already holds reveals nothing and skips
no check, so this is the one half of the voice path allowed to be missing.
The body may carry `client_fallback_ok` (a boolean) and `reason`
(`JarvisApi.kt:612-628`). Absent `client_fallback_ok` is treated as **false**,
deliberately — that flag decides whether the owner's reply gets handed to the
handset's default engine, which on a stock phone is Google's. A 200 carrying
no audio is treated as a server fault, not as permission to synthesise locally.

**`/api/voice/wake` approves, it does not apply.** Success means a decision
card was raised, not that the wake word is now on. Re-read `/api/voice/status`
to learn the truth (`JarvisApi.kt:644-651`).

**A client must not do speech-to-text.** That is a standing rule in
`CLAUDE.md`, and it is why `utterance` posts a complete recorded clip rather
than streaming: the phone's voice-print gate needs the whole clip to check it.

---

## 6. Memory, the Brain, models, attention, appearance, status

### The desktop's read allowlist

The desktop's Brain window cannot name a URL. It names a *section*, and
`jarvis-desktop/src-tauri/src/brain/routes.rs:14-37` maps that to a path. The
grant is auditable by reading one array, and a test asserts no state-changing
path ever appears in it (`routes.rs:67-101`).

| Endpoint | Method | Desktop | Android | Notes |
|---|---|---|---|---|
| `/api/version` | GET | `sidecar.rs:321`, `stream.rs:569` | `JarvisApi.kt:268` | The handshake. **Branch on capabilities, never on version numbers** (`JarvisRuntime.kt:394-396`). Also carries `activity`. |
| `/api/status` | GET | `commands.rs:677`, `routes.rs:16` | `JarvisApi.kt:271` | Reports power mode; nothing writes it (`LinkTileService.kt:26`). |
| `/api/graph` | GET | `routes.rs:15` | **no — by rule** | The memory graph stays off the phone. Gets its own longer timeout (`brain.rs:97`). |
| `/api/models` | GET | `routes.rs:17` | `JarvisApi.kt:300` | Phone reads it only where the handshake reports the `models` capability. |
| `/api/compute` | GET | `routes.rs:18` | via `probe` | GPU/VRAM plan. Shape undocumented — see below. |
| `/api/skills` | GET | `routes.rs:19` | via `probe` | |
| `/api/jobs` | GET | `routes.rs:20` | `JarvisApi.kt:286` | List key: `jobs`. |
| `/api/undo` | GET | `routes.rs:21` | `JarvisApi.kt:283` | List key: **`shelf`**. |
| `/api/ledger` | GET | `routes.rs:22` | via `probe` | Audit chain. |
| `/api/content-risk` | GET | `routes.rs:23` | **no** | Read-only by design. |
| `/api/watch` | GET | `routes.rs:24` | **no** | |
| `/api/watch/report` | GET | `routes.rs:27` | **no** | A peek. Marking read is a POST on purpose. |
| `/api/memory/status` | GET | `routes.rs:28` | **no** | |
| `/api/memory/pending` | GET | `routes.rs:29` | via `probe` (`BrainScreen.kt:697`) | The review QUEUE, never the corpus. |
| `/api/memory/facts` | GET | `routes.rs:32`, `brain.rs:413` | `JarvisApi.kt:429` | Takes `?known_at=<unix seconds>` — "what did I believe then?" |
| `/api/memory/export` | GET | `brain.rs:382` | **no** | |
| `/api/initiative` | GET | `routes.rs:33` | via `probe` | The **only** list route that uses the key `items`. |
| `/api/attention` | GET | `attention.rs:54`, `routes.rs:34` | `JarvisApi.kt:277` | Nests the budget; the phone flattens it (`ApiModels.kt:366`). |
| `/api/digest` | GET | `attention.rs:81`, `routes.rs:35` | `JarvisApi.kt:280` | List key: `digest`. |
| `/api/config` | GET | `routes.rs:36` | **no** | **Read-only: writing answers 501.** This is why there is no shared place to store a preference — `API-DISAGREEMENTS.md` §11. |
| `/api/visual-spec` | GET | `spec_drift.rs:50` | **no** | Desktop checks its bundled spec against the server's at startup. The phone never fetches it. |
| `/api/appearance` | GET / POST | `appearance.rs:41` | `JarvisApi.kt:381`, `:391` | See §7 — the clients disagree about whether this exists. |
| `/api/feedback/counts` | GET | **no** | **no** | `feedback.patch`. Token + origin. `{"facts": {"<fact id>": {"helpful", "harmful"}}, "skill_notes": {same shape}, "answers_marked": {"right", "wrong"}, "retire_cards_raised", "threshold": {"min_wrong": 5, "ratio": 3}, "note"}`. Match a fact id to its words with `/api/memory/facts`, and show `note` with the counts: a fact in a wrong answer did not necessarily cause it. `503` if `jarvis_feedback.py` is missing. |
| `/api/feedback/mark?turn_id=<id>` | GET | **no** | **no** | `feedback.patch`. The current mark on one answer: `200 {"turn_id", "mark"}` (`"right"`, `"wrong"` or `"none"`), `404` if the id is unknown on this machine. |
| `/api/skills/suggestions` | GET | **no** | **no** | `skill-suggest.patch`. Read-only, same guard as `/api/skills`. `{available, enabled, recording, tier, why_off, min_repeats, window_days, every_hours, in_flight, next_offer_after, ledger_error, note, chains: [{chain, turns, last_seen, status}], offers: [newest first, up to 50]}`; `status` is `eligible`, `counting`, `asked_before`, `declined`, `saved` or `covered`. `{"available": false, "reason"}` if the module is missing. **No approve or save button on this screen** - an offer is decided only on its approval card (§3, action `modify_own_code`). |

**`/api/models` gains `speed`** (`speed-record.patch`), next to `offload`:
`{"available": true, "recent": [up to 20 answer rows, oldest first],
"by_model": {"<model>": {"answers", "median_first_word_ms",
"median_tokens_per_s", "median_words_per_s", "median_on_gpu_percent",
"last_at"}}, "last_switch": null | {...}, "last_switch_note": null | "<sentence>",
"slowdown": null | {"slower", "change_percent", "recent_tokens_per_s",
"earlier_tokens_per_s"}, "note"}`, or `{"available": false, "note"}`. Show one
line for `by_model[current]`; show `note` as a warning line only when
`slowdown.slower` is true; show `last_switch_note` word for word beside the
rollback button when `last_switch` is set. Numbers only - nothing in it is
conversation text.

**`/api/graph` gains `sources.documents_not_ours`** (`documents-owned.patch`):
true means a `documents` table made by another program (most likely
OpenJarvis's indexer) is in `memory.db` and Jarvis is not reading it. Desktop
only, one line saying exactly that. The route that serves `build_graph()` was
not checked; `/api/graph` is the likely one.

**Undocumented shapes are read as raw JSON on purpose.** `/api/compute`,
`/api/memory/pending`, `/api/ledger`, `/api/skills` and `/api/initiative` had
one line of description each and no field names, so the Android client reads
them through `probe()` and renders whatever keys are actually present
(`JarvisApi.kt:508-522`). Writing a data class against a guess "fails silently,
as an empty panel that looks built" — which is precisely the mistake that
produced `jarvis-android`'s unusable protocol.

**`/api/memory/pending`, as far as it is now known** (from the patches that
wrote it, not a real capture): `{"available": true, "pending": [row, ...],
"setup": {...}}`. Each row has `id`, `text`, `replaces`, `replaces_id`,
`replaces_text`, `confidence`, `source`, `created`; `memory-intake.patch`
adds four:

| row field | type | show it how |
|---|---|---|
| `flags` | list of `{"code", "why"}` | Not empty: a warning on the card, each `why` as a line ("It tells Jarvis to send, forward or share something to an address, link or number."). Codes: `override`, `sends_elsewhere`, `standing_order`, `less_oversight`, `addressed_to_ai`, `markup`, `encoded`. A warning only - the card still has keep and discard. |
| `flags_checked` | bool | `false` means the check could not run (the backend lacks `jarvis_intake.py`), which is not the same as "clean". |
| `keep_both_ok` | bool | True only on a correction card (one that would retire `replaces_text` by adding a new fact). **False on a "retire this?" card** (`source == "feedback_retire"`), even though that card also has `replaces_id`. Only when true, show a third button, "Both are true", which posts `{"id": row.id}` to `/api/memory/keep_both`. |
| `verbatim` | bool | True when `source` is `"remember"`: the owner's own words from a "Remember:" message. Label it that way. |

`setup` may also carry `near_duplicate_check` (`"on"`, or why not),
`near_duplicates_dropped` + `near_duplicates_note` (only once one has been
dropped), and `remember_last`: `{"at", "queued", "reason", "note",
"proposal_id"}` for the last "Remember:" message - `note` is a plain-words
sentence meant to be shown as-is ("This exact wording is already waiting for
your review.").

**The "retire this?" card** (`feedback.patch`) is a row in this same queue
with `source == "feedback_retire"`, `confidence: null`, and
`replaces_id`/`replaces_text` naming a stored fact that keeps turning up in
answers the owner marked wrong. Its buttons must NOT read Keep / Discard:
accepting it (`/api/memory/decide {"id", "accept": true}`) **retires** the
fact, and discarding it keeps the fact exactly as it is. Label accept
"Retire it" and discard "Keep using it"; show `replaces_text` as the fact in
question and `text` as the reason; show no confidence; no "Both are true".
The desktop's current Keep button, and its "Kept. Jarvis can recall it now."
reply, would say the opposite of what happens on this card.

**So the card is hidden unless asked for.** `GET /api/memory/pending` leaves
out every `source == "feedback_retire"` row. A client that shows the card
with the labels above asks for it with `GET /api/memory/pending?retire_cards=1`
(exactly `1`; anything else is the same as not asking), and gets those rows
in the same `pending` list as every other card. A client that has not been
changed never sees one, so its Keep button can never retire a fact. Hidden
from the list is not removed from the queue: the card waits, undecided, until
a client that asks shows it. Two things still count it, and a client should
not be surprised by either: `setup.pending` (the queue size) and the
`proposal` event's `count`/ids on the event stream. `/api/memory/export`
lists it too - it is a backup, not a card list.

### Writes

| Endpoint | Method | Body | Desktop | Android | Notes |
|---|---|---|---|---|---|
| `/api/undo/revert` | POST | `{"id": …}` | `brain.rs:158` | `JarvisApi.kt:403` | "The one state-changing thing a phone may drive" — it only moves toward a state the owner already had. |
| `/api/jobs/cancel` | POST | `{"id": …}` | `brain.rs:169` | `JarvisApi.kt:450` | |
| `/api/holds/cancel` | POST | `{"handle": …}` | `brain.rs:190` | `JarvisApi.kt:466` | **Unreachable from the phone** — nothing lists holds, so it has no way to learn a handle. Left in deliberately; see §9. |
| `/api/watch/add` | POST | object | `brain.rs:219` | **no** | |
| `/api/watch/remove` | POST | object | `brain.rs:228` | **no** | |
| `/api/watch/seen` | POST | object | `brain.rs:248` | **no** | The consume, vs the GET peek. |
| `/api/skills/decide` | POST | `{"name": …, "remove": true}` | `brain.rs:258` | **no** | **Removal only.** There is deliberately no install route: installing runs the scanner and the gate inside the module. |
| `/api/models/install` | POST | `{"ref": …}` | `brain.rs:434` | `JarvisApi.kt:326` | Allowed from the phone since the 2026-09-20 amendment: tier `ask`, same shape as switch. No catalogue - the ref is typed in, never browsed. |
| `/api/models/switch` | POST | `{"ref": …}` | `brain.rs:435` | `JarvisApi.kt:310` | Allowed from the phone since the 2026-09-18 amendment: tier `ask`, so success means "a card was raised". |
| `/api/models/rollback` | POST | `{}` | `brain.rs:436` | `JarvisApi.kt:314` | Tier `auto`; never waits. |
| `/api/memory/decide` | POST | `{"id": <int>, "accept": bool}` | `brain.rs:283` | `JarvisApi.kt:417` | One id, one decision. **No list form anywhere** — a "keep all" would be an approve-all with another name. |
| `/api/memory/keep_both` | POST | `{"id": <int>}` (a PROPOSAL id) | **no** | **no** | `memory-intake.patch`. The third answer on a correction card: keep the new fact and do NOT retire the old one. Same claim as `decide` (two taps, one fact). `200 {"ok": true, "id", "fact_id", "kept_id", "kept_text"}`; `409 {"ok": false, "reason": "not_a_correction", "note"}` for a card that retires nothing; `404` if the id is not pending; `400` for a non-integer id; `501` if the patch is missing. Show the button only when the row's `keep_both_ok` is true. |
| `/api/feedback/mark` | POST | `{"turn_id": "<32 hex>", "mark": "right" \| "wrong" \| "none"}` | **no** | **no** | `feedback.patch`. One answer, one mark; `"none"` takes a mark back. A list of ids is refused (`400`) - there is no "mark all". `200 {"ok": true, "turn_id", "mark", "was", "changed", "facts", "retire_cards_raised"}`; `400` bad id or mark; `401`/`403` token or origin; `404` unknown id; `503` module missing. A mark never changes memory: at most it queues ONE "retire this?" card (above). |
| `/api/memory/forget` | POST | object, optional `valid_to` | `brain.rs:308` | **no** | Retires rather than deletes. No undo. |
| `/api/memory/edit` | POST | object | `brain.rs:329` | **no** | |
| `/api/memory/learning` | POST | object | `brain.rs:344` | **no** | |
| `/api/memory/sleep_time` | POST | `{"enabled": bool}` and/or `{"remind": bool}` | `brain.rs:369` | `JarvisApi.kt:447` | "Not now" sends nothing at all — the card tracks "already offered today" itself. |
| `/api/attention/mute` | POST | `{}` | `attention.rs:119` | `JarvisApi.kt:469` | **Until tomorrow only.** There is no "mute forever". |
| `/api/attention/unmute` | POST | `{}` | `attention.rs:121` | `JarvisApi.kt:471` | Response is `budget()`, not `status()`, so the desktop re-reads rather than applying half an update. |
| `/api/digest/seen` | POST | `{}` = all, or `{"ids": [...]}` | `attention.rs:102` | `JarvisApi.kt:481` | **Marking read is not approving.** Both clients say so in the same words. |
| `/api/shutdown` | POST | `{}` | `sidecar.rs:636` | **no** | Unloads the model from the GPU. Desktop-only, and failure is not fatal — the grace period exists because this may not work. |

---

## 7. Where the two clients disagree

These are differences I verified by reading both call sites. I have no way to
know which side the backend agrees with.

1. **`/api/chat` body — the serious one.** Desktop sends
   `{"messages": [...], "has_image", "stream", "auto"}` (`commands.rs:801-806`);
   Android sends `{"message": "<text>"}` (`JarvisApi.kt:661-663`). These are
   not variations on a theme; they are different protocols. Related: the
   desktop handles both chunked-text and SSE framing on the reply
   (`API-DISAGREEMENTS.md` §4), the phone handles only chunked text
   (`JarvisApi.kt:653-659`), so an SSE-framed reply would arrive at the phone
   as `data:` noise.

2. **Approve/deny attribution.** Desktop sends `"by": "desktop_spotlight"`
   (`commands.rs:914-916`); Android sends only `{"id": …}` (`JarvisApi.kt:395`).
   If the server records `by`, phone decisions are attributed to nothing. If it
   ignores `by`, the desktop is sending a field nobody reads.

3. **`/api/appearance` — the clients contradict each other about whether it
   exists.** `appearance.rs:17-24` says under a heading reading *"The route
   does not exist yet"* that the backend "answers neither", and falls back to
   a local store on every read. The Android client calls it as a normal
   capability (`JarvisApi.kt:381`, `:391`) and even handles an `appearance`
   event to re-read it (`JarvisRuntime.kt:707`). **And `backend/appearance.patch`
   implements both verbs** (`appearance.patch:253`, `:273`, plus the
   allowlist entry at `:317`), with fourteen tests in `backend/test_appearance.py`.
   So: the route is written and tested but not necessarily applied to the
   owner's machine, and the desktop's comment is describing a backend that
   predates the patch. Anyone reading only `appearance.rs` would conclude the
   feature is impossible. It is not — it is unapplied. The document's schema
   lives in `docs/APPEARANCE-API.md`.

   There is a further unresolved schema conflict on top of that — three shapes
   for one document, and no agreement on whether conflicts resolve by
   last-write-wins or a server-owned revision with a 409.
   `docs/CROSS-CLIENT-CONTRACT.md` §2 states the open question; do not settle
   it from this page.

4. **Staleness.** Desktop: 70 seconds (`stream.rs:54`). Android: a 90-second
   read timeout plus its own watchdog (`JarvisApi.kt:232`). Both are defended
   in comments and neither is wrong, but the two devices will disagree about
   when the same quiet backend has died.

5. **Voice control routes are phone-only.** `/api/voice/status` and
   `/api/voice/wake` have no desktop call site at all — the desktop posts
   `utterance` and `say` and nothing else. So the wake word can be toggled
   from the phone and not from the machine it runs on.

6. **`/api/visual-spec` is desktop-only.** `spec_drift.rs` fetches it and
   compares structurally; the phone's `SpecDriftTest` compares Kotlin constants
   against its own bundled copy, so it is structurally incapable of noticing
   the desktop's copy drifting. `docs/CROSS-CLIENT-CONTRACT.md` §3 asks whether
   the served spec should replace both vendored copies.

7. **Event kinds each client ignores.** The phone ignores `finding`, `voice`
   and `proposal`, and does not handle `job` at all; the desktop renders
   `proposal` and fans the rest out verbatim. Deliberate on the phone's side
   (see the reasoning at `JarvisRuntime.kt:683-705`), but worth knowing before
   assuming a feature works on both.

---

## 8. Draft, proposed, or not actually wired

Nothing in this section is confirmed to exist. Treat every name here as a
guess someone wrote down honestly.

| Route | Status |
|---|---|
| `/api/pending/<id>/amend` | **DRAFT.** The name comes from `docs/AUTONOMY-PROPOSALS.md` §3b, not from the backend. Both clients target it (`JarvisApi.kt:326-339`, `jarvis-link.js:407-429`) and both say in comments that it is unconfirmed. A 404 means "this build has no such route", not "wrong address". |
| `/api/task/pause` | **DRAFT.** No route name exists anywhere in the design doc; only the mechanism is specified. The name follows the existing domain/verb shape (`JarvisApi.kt:341-362`). |
| `/api/task/resume` | **DRAFT**, same standing (`JarvisApi.kt:364`). |
| `/api/task/stop` | **DRAFT**, same standing (`JarvisApi.kt:366`). |
| `/api/task/note` | **DRAFT**, `{"note": …}`, same standing (`JarvisApi.kt:369`). |
| `/api/appearance` | Proposed in `docs/APPEARANCE-API.md`; **implemented in `backend/appearance.patch`**, which may or may not be applied on the owner's machine. See §7.3. |
| `/api/visual-spec` | Real and correct per `docs/CROSS-CLIENT-CONTRACT-REPLY-2.md`, but only the desktop fetches it. |
| `GET /api/holds` | **Does not exist and was deliberately not invented.** `JarvisApi.kt:455-464` records that an earlier draft made it up to fill the gap, and that doing so "is the exact mistake that produced `jarvis-android`'s protocol". Removed rather than kept behind a 404. |
| `/api/approvals` | **Does not exist.** Named once by mistake; `backend/extraction-wiring.patch:342-345` records the correction. The queue is `/api/pending`. |
| A decide-with-option route | Needed for approvals carrying two or more options (`ApiModels.kt:294-302`). No name proposed. |
| `POST /api/note` | Suggested, not proposed — it would let a client truthfully report that a note was filed (`API-DISAGREEMENTS.md` §10). |

### The desktop task controls — fixed since this doc was first written

Originally verified on 2026-09-20 by grepping `jarvis-desktop/src-tauri/src/`
and the `invoke_handler` list in `lib.rs`: at that point, `jarvis-link.js`
called five Tauri commands — `amend_approval`, `pause_task`, `resume_task`,
`stop_task`, `inject_task_note` — none of which existed in the Rust source or
`lib.rs`'s `invoke_handler`, so every one of those buttons failed at the
app's own internal boundary, before any HTTP request was made.

**Re-verified the same day, after a fix landed:** all five now exist in
`commands.rs` (`pause_task`/`resume_task`/`stop_task`/`inject_task_note` at
`:1054-1071`, `amend_approval` at `:1101-1109`), are registered in `lib.rs`'s
`invoke_handler` (`:600-604`), and reach the same routes the phone already
used (`/api/task/pause`, `/api/task/resume`, `/api/task/stop`,
`/api/task/note`, `/api/pending/<id>/amend`) — still `docs/AUTONOMY-PROPOSALS.md`
§3d/§3b names, still unconfirmed against the real backend, so a 404 from any
of them means "this build has no such route" and is reported as that rather
than as a generic failure (`commands.rs:1025-1034`). The Android side has
called the same routes over plain HTTP the whole time, so the desktop was
the odd one out; it no longer is.

Same shape, one still open: `jarvis-link.js:403-404` passes an `option_id`
argument to `decide_approval`, but the Rust `decide_approval` signature is
still `(app, id, approved)` (`commands.rs:918-922`) — there is no
`option_id` parameter, and the extra argument is simply dropped by Tauri.
Unlike the task controls, this one is **not** a matter of wiring an existing,
named backend route — no decide-with-option route is confirmed to exist at
all (see the table above), so adding an `option_id` field to the
`/api/approve` request body would be guessing a server contract, the same
mistake this document exists to avoid making. Fixed on the UI side instead,
2026-09-20: `main.js`/`widget.js` now render the per-option approve buttons
disabled rather than letting them send an approve indistinguishable from any
other option's, matching `jarvis-client`'s `needsChoice` restraint
(`ApiModels.kt:294-302`). The underlying gap — no client can actually convey
which option was approved — stays open until a server route exists.

---

## 9. Rules that constrain this API

These are from `CLAUDE.md` and `docs/ARCHITECTURE.md`, restated here because
they explain why several obvious routes are missing rather than forgotten.

- **Nothing auto-approves, and nothing acts on a stale stream.** The desktop
  enforces this in Rust at `commands.rs:944-951` — it used to live only in the
  webview, where a disabled button "is a courtesy, not a gate". The phone
  enforces it in `JarvisRuntime.decisionBlocker`.
- **No bulk decisions anywhere.** No approve-all, no "keep all" for memory, no
  route that clears a rush latch. `/api/digest/seen` marks read and decides
  nothing.
- **The phone does not get to browse the catalogue, the memory graph, or
  deep config.** Switching between models the desktop already has is
  allowed (amended 2026-09-18), and so is installing a typed-in model name
  (amended 2026-09-20) - both raise an approval card like any other change.
  There is still no scrollable, searchable list of what could be installed.
- **A client must not do speech-to-text.** Hence one complete WAV per
  utterance, and no streaming audio.
- **No public tunnel, ever.** Everything here is loopback or Tailscale.

---

## 10. If you are changing this file

1. Check the claim against the actual source file first, and cite the
   file and line.
2. If the backend contradicts something here, **the backend wins** — fix the
   client, then add an entry to `docs/API-DISAGREEMENTS.md`.
3. If you are adding a route nobody has confirmed, put it in §8 and say who
   proposed it. An invented endpoint that looks real is how
   `jarvis-android` became unusable.

Reconstructed 2026-09-20 from client call sites on branch
`fix/audit-remaining-four`. Roughly 55 distinct endpoint paths.
