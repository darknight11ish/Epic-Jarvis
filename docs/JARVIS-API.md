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
| `activity` | Updates activity + detail. The sentence is a step number and a fixed word while Jarvis drives a browser, a window or the phone ("Step 2/3: a click in another program's window") - never an address, a window title, a control's name or typed text (security audit L4, 2026-09-25); those are on the card. The sentence is read from `value.detail` (the rebuilt bus's `set_activity` shape), then a top-level `detail`, then `activity_detail` (`stream.rs`, `activity_detail()`) | Reads the sentence off the event the same way - `value.detail` first, then `detail`, then `activity_detail` (`net/ActivityEvent.kt`) - and re-fetches status (`JarvisRuntime.onEvent`). Before 2026-09-24 it read only `activity_detail`, which no backend sends |
| `power` | Updates power mode (`stream.rs:529`) | Re-fetches status (`JarvisRuntime.kt:682`) |
| `persona` | Fanned out verbatim | Re-fetches status (`JarvisRuntime.kt:682`) |
| `finding` | Fanned out verbatim | Ignored — the digest covers these (`JarvisRuntime.kt:683`) |
| `model` | Fanned out verbatim | Re-reads the model list (`JarvisRuntime.kt:689`) |
| `voice` | Fanned out verbatim | Ignored (`JarvisRuntime.kt:690`) |
| `job` | Fanned out verbatim | Falls through to "unhandled" |
| `proposal` | Re-reads the review queue when the Brain shows it (`brain.js` `onEvent`, section `memory_pending`); the HUD page re-reads its "N memory cards waiting" pointer | Re-reads the review queue (`JarvisRuntime.onEvent` -> `refreshMemoryQueue`) |
| `step` | Rendered in Brain → Live (`brain.js`, `stepText`) | Counted for the private-answer rule: `tool_started` / `tool_finished` mean a tool ran while an answer was written (`voice/PrivateAloud.kt`, `JarvisRuntime.onEvent`) |
| `voices` | Re-reads `/api/voice/voices` while Settings shows Jarvis's voice (`voice-panel.js`) | Re-reads the custom voices once the Voices screen has asked for them (`JarvisRuntime.onEvent`) |
| `appearance` | Re-reads `/api/appearance` and repaints the tray, every window and the HUD (`stream.rs` → `appearance::refresh_from_server`; before 2026-09-23 it did nothing, so a phone change arrived only on reopen) | Re-reads the shared document (`JarvisRuntime.refreshAppearance`) |
| `memory_saved` | Brain: the quiet "Jarvis remembered N things" line; re-reads the auto list and `memory_facts` (`brain.js` `noteMemorySaved`/`onEvent`). Automatic learning saved facts without a card (`auto-learn.patch`; §19); the data is flat, `{"ids": [<fact id>, ...]}` - fact ids only, never the words | The same line on the phone's Brain screen; the list re-reads (`JarvisRuntime.onMemorySaved`). Never a notification. |
| `schedule` | A timer, alarm or reminder went off, or Coming up changed: `{"id", "kind", "state": "fired" \| "changed" \| "ready", "late"?}` only, never the words (`jarvis_schedule.py`, section 21). On `fired` the Rust reads the job by id and shows a Windows toast (`brain/schedule.rs` `toast_fired`, only the kind's lock-screen words while App lock or hiding is on) - except for a briefing, whose toast comes on `ready` (`brain/briefing.rs` `toast_ready`, always only "Jarvis: your morning briefing is ready.", section 22); the Brain reads Coming up again, and the briefing too for kind `briefing` (`brain.js`) | the Brain's Coming up reads itself again; on `fired` the job is read by id and shown as a notification, the lock screen showing only the kind (`JarvisRuntime.onScheduleEvent`, `ScheduleNotifier`). For kind `briefing`: the Brain's Morning briefing reads itself again, and on `ready` (not `fired`) a notification with only the fixed words, which opens the Brain (`JarvisRuntime.onBriefingReady`) |
| `focus` | A focus session started, changed or ended - `{"state": "started" \| "changed" \| "ended"}` - or has a line to say, `{"state": "callout", "seq"}`; never what was in front (section 26). The Brain's Work tab and the widget read `GET /api/focus` again (`brain.js`, `widget.js`); on `callout` the Rust fetches the line as SOUND from this PC only and the Jarvis bar plays it (`brain/focus.rs` `play_callout`) | the Brain's Focus session reads itself again (`JarvisRuntime.onEvent` -> `focusTick`); a `callout` is ignored - the line is the PC's alone |
| `deep` | A deep question finished: `{"id", "state": "done" \| "failed"}` only, never the question or the answer (`jarvis_big_model.py`, section 14). Nothing in Rust reads for it (`stream.rs`); it is fanned out, and the Brain re-reads `GET /api/deep` (`brain.js`, Deep questions) | Re-reads `/api/deep` and `/api/big-model` (`JarvisRuntime.onEvent`: `refreshDeep`, `refreshBigModel`) |

`attention` is the one kind that carries its own state instead of ringing a
bell (`stream.rs:506-511`).

`step` (`backend/jarvis_agent.py`, `_step_event`) is published by the tool
loop while it answers: `{"phase": "model" | "tool_started" | "tool_finished"
| "tool_refused" | "answer", "tool"?: <a name from jarvis_agent.TOOLS, or
"unknown">, "ok"?: bool, "round"?: int}`. An allowlist: never a tool's
arguments or result, never the model's text or reasoning. Only sent when
tools are switched on (`[tools] enabled`). A client that does not show it
can ignore it.

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
| `/api/pending/<id>/amend` | POST | `{"note": "…"}` | via `amend_approval` | `JarvisApi.amend` | **Real since `backend/task-control.patch`.** Keeps a note with one waiting card; approves and denies nothing. See §11. |

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

### What one pending row carries

`id`, `action`, `tier`, `detail`, `prompt`, `created`, `raised` (stored by
`jarvis_gate`), plus `risk`, `notice` and - with `approval-expiry.patch` -
`expires_in` (added when the list is read). There is **no `title` and no
`summary`**: a client makes its title from `notice.title` (else the PC's
fallback, below) and never from `prompt` or `detail`, because a title also
ends up on a lock screen.

**`notice.title` is a plain sentence (2026-09-25).** It comes from
`backend/jarvis_card_words.py` `TITLES`, one phrase per gate action: "Jarvis
wants to switch to a different AI model", "Jarvis wants to turn on automatic
learning", "Jarvis wants to search the web". It used to be the action name
with its underscores removed ("Jarvis wants to learning enable"). An action
with no phrase reads `Jarvis wants your OK for "<its name in words>"`, and a
row with no action "Jarvis is asking for your approval". A row with **no
`notice`** (a backend older than approval-notice.patch) gets that same
fallback in both apps. `backend/test_card_words.py` fails when an action the
gate knows has no phrase.

**One card on every screen.** The Jarvis bar, the widget, the HUD page, the
phone's card and its home-screen widget all show the label "Needs your OK",
then the title, then the rest of the card, with **Deny on the left and
Approve on the right** (docs/ARCHITECTURE.md §3 says why). A notification
still offers Deny only, never Approve.

**"Open the card".** Settings and the Brain on the PC, and every phone screen
but Home, show one line while a card waits: the label, the title of the last
card in the queue, "and N more waiting", and an "Open the card" button. It decides
nothing: on the PC it calls the Tauri command `open_approval_in_quickbar`
with the card's `id` (the Jarvis bar, behind App lock, opens on that card);
on the phone it opens Home on that card. No backend route is involved.

**Windows notifications.** The PC now shows a toast for **every** card that
arrives, not only `weight: "heavy"` ones: a heavy card with the usual sound,
a normal one silently (the phone already posted normal cards to its quiet
channel). While App lock is on the toast shows the title only. Deny is still
the only button. Shapes vary, so both clients read each row on its own and
accept all of them: `detail` as JSON text or an object; `raised` as an
object, `true`, or JSON text (any truthy value counts as raised); `id` as
text or a number. A row that still cannot be read is skipped and the phone
says so, instead of failing the whole list.

A tool card's `detail.text` may end with a "What shaped this request:" block
- which tools Jarvis had read before proposing it, and which of its values
came from that text rather than from the owner (§4, "Tool calls and outside
text"). It is part of the text; show it the way the rest is shown.

`expires_in` is seconds left before the gate stops waiting and refuses the
card (`approval_timeout_seconds`, 180 in the shipped config). Seconds left,
not a clock time, so the phone's clock does not have to agree with the PC's.
Without the patch the field is absent and no countdown is shown.
`backend/test_approval_contract.py` builds these rows from the real
`notice_for` and `expires_in` code into
`jarvis-client/app/src/test/resources/contract/pending-rows.json`, which the
phone's and the desktop's tests decode.

### The PC's own check before an approval - `backend/owner-check.patch` (2026-09-25)

The approval gap's step 1 (`docs/APPROVAL-GAP-DESIGN.md`, the owner's
decisions of 2026-09-25; `backend/jarvis_owner_check.py`). What changed for
a client:

- **A risky `POST /api/approve` from the PC waits for Windows Hello.** Risky
  is the phone's rule on the pending row (not classified, `reach`
  outbound, `reversible` "no", or `raised` set), the same in all three
  places: `tools/gen_risky_approval_cases.py` writes the shared cases
  (`jarvis-desktop/tests/fixtures/risky-approval-cases.json` and the
  phone's copy in `contract/`). "From the PC" is decided by the
  connection: loopback, a sender address equal to the address it arrived at
  (the PC calling its own Tailscale address), or one of the PC's own
  addresses; anything that cannot be placed counts as the PC. The request
  stays open while the prompt is up, at most the card's `expires_in`. A
  phone approval, or a card that is not risky, is not held.
- **The answers it can give instead of the owner's handler's:**

  | Status | Body | Means |
  |---|---|---|
  | 403 | `{"ok": false, "owner_check": "not_set_up", "error": "Windows Hello is not set up on this PC, ..."}` | No Windows Hello on the PC: "no lock, no risky approval". |
  | 403 | `{"ok": false, "owner_check": "cancelled", "error": "..."}` | The owner dismissed the prompt. |
  | 403 | `{"ok": false, "owner_check": "failed", "error": "..."}` | The prompt could not be shown just now. |
  | 409 | `{"ok": false, "owner_check": "gone", "error": "This request stopped waiting while Windows Hello was open ..."}` | It ran out of time or was answered while the prompt was open. Both apps read a 409 as "no longer waiting". |
  | 503 | `{"ok": false, "owner_check": "unreadable", "error": "..."}` | The queue could not be read, so nothing was approved. |

  The desktop shows a 403/503 `error` as it is (`owner_check_refusal`,
  commands.rs); none of the sentences contains "already" or "409", which
  the windows read as "answered elsewhere".
- **`/api/deny` is unchanged** and never held.
- **Every approval is stamped** in the backend's memory, and the gate
  believes an "approved" row only with that stamp: "approved" written into
  `approvals.db` directly, or a `jarvis_gate.decide()` from another program,
  is refused (`Verdict.outcome` "refused", reason "it was marked approved,
  but not through Jarvis's own approval check").
- **`GET /api/version`'s `capabilities.owner_check`** is `"backend"` when
  the running server has the check, else `false`. The desktop reads it at
  each Approve (`backend_owner_check`); when it is `"backend"` and the
  desktop's address is loopback, the desktop does not show its own Windows
  Hello prompt for a risky card (`lock/rules.rs`
  `approval_needs_local_check`) and waits up to the card's time left plus a
  few seconds (`approval_wait`), after letting the backend's prompt come to
  the front. The phone does not read it: its approvals are not checked on
  the PC (step 2 is the phone's half).

---

## 4. Chat

| Endpoint | Method | Body | Desktop | Android | Notes |
|---|---|---|---|---|---|
| `/api/chat` | POST | `{"messages": [...], "has_image", "stream", "auto"}` | `commands.rs` `stream_chat` / `pump_chat` (body built in `main.js` `send()`) | `JarvisApi.kt` `chatCall` (body built by `net/ChatHistory.kt`), read by `ChatSession` | See below. |

**Both clients now send the same shape, with the conversation so far.**
(Updated 2026-09-23. Earlier versions of this page said the phone sent
`{"message": "<text>"}`; it has sent the `messages` shape for a while, and
until now only ever one user turn.)

```
{"messages": [
   {"role": "user",      "content": "<an earlier question>"},    ┐ the conversation so far,
   {"role": "assistant", "content": "<Jarvis's answer to it>"},  ┘ oldest first, 0 to 10 pairs
   … the quickbar's per-turn system turns (#log / #joplin note, clipboard) …
   {"role": "user",      "content": "<the new question>"}],     ← always last
 "has_image": false, "stream": true, "auto": true}
```

**Why the conversation is sent.** Nothing in this repository shows the
backend keeping one: requests carry no conversation id, and every patch
that touches `/api/chat` works on the `messages` array the client sent (the
degrade loop's local rebuild restores `body["messages"]`; the learner reads
it). So a client that sends only the newest question gets follow-ups
answered with nothing before them - which is what the phone and the quickbar
did until 2026-09-23. The HUD page (`jarvis_hud.html`) already sent its own
last 12 messages.

**How much.** Pairs of (question as sent, whole answer), plain text only, no
system turns, tool output, images or ids. At most **10 pairs and 18,000
characters**; past either, the oldest go until it is back to **6 pairs and
12,000 characters**, so the start of the prompt changes rarely and Ollama's
prompt cache survives. The budget, against `num_ctx 16384`
(`jarvis-primary.Modelfile`): 2,048 answer + 250 system prompt and template +
400 recalled facts (plus up to ~300 more for the 1,200 characters of
"Always keep in mind", §6) + 2,600 tool list (13 tools, 7,851 characters of JSON) +
3,000 new question = 8,298, leaving ~8,000; 18,000 characters is 6,000
tokens at a pessimistic 3 characters per token (~4,500 at English's ~4).
Same numbers on both clients: `net/ChatHistory.kt` and
`jarvis-desktop/src/chat-history.js`, held together by
`jarvis-desktop/tests/chat-history.mjs`.

**These caps are an upper bound, not the fit.** The model actually loaded may
have far less than 16,384 (4,096 unless `jarvis-primary` is loaded - a model
switched to from the phone, say), and tool results were in nobody's budget.
Since `chat-stream.patch`, the PC asks Ollama what the loaded model has
(`/api/ps`, then `/api/show`) and drops the oldest earlier turns to fit,
leaving room for the answer - never the recalled facts or the new question
(`jarvis_agent.fit_messages`). Only the PC can know that number.

**Only finished answers are kept.** Not an error, not one the owner stopped,
not an empty one, and not an SSE answer that ended without `[DONE]` or a
`finish_reason` (cut off) - the same line `jarvis_hud.html` draws.

**Memory only, and a way out.** Neither client writes the conversation to
disk. The phone clears it on "New conversation" (under the answer on Home)
and when the app process ends. The quickbar clears it on "New conversation"
(in the answer card's header) and on Esc, together with the card; hiding on
focus loss keeps it. Nothing the backend has learned is touched by either.

**Cloud lanes get the newest question alone.** The backend's cloud cut keeps
every `role == "user"` turn, which with a conversation attached includes the
earlier questions. `backend/cloud-one-turn.patch` cuts any request to a lane
that is not the local model down to the newest user turn, inside `_open`, so
an earlier private question cannot ride along on a later one that was sent
to the cloud. Until that patch is applied, that protection is not there - see
its section in `backend/README.md`.

**A past answer grants nothing.** An assistant turn saying "I have proposed
that" or "approved" is text in a transcript; approvals are decided by id on
`/api/approve` and nowhere else.

**Framing.** `stream: true` (what all three apps send) gets Ollama's own
OpenAI-compatible stream, `Content-Type: text/event-stream`: `data: {chunk}`
lines, the words in `choices[0].delta.content`, a chunk with a
`finish_reason` (`"stop"`, or `"length"` when the answer hit its length limit
and was cut short), then `data: [DONE]`. `stream: false` gets one JSON body,
`choices[0].message.content`, `Content-Type: application/json`. A failure
after the answer has started is one more line: `data: {"error": {"message":
"<a plain sentence>"}}` (or `{"error": "<sentence>"}` in a JSON body). All
three readers handle all of it - the phone's `ChatChunkParser`, the
quickbar's `consumeLine`, the HUD page's reader - and are tested against
bodies made by running the backend (`backend/test_chat_stream_contract.py`
writes `chat-stream-cases.json`; `ChatStreamContractTest.kt`,
`jarvis-desktop/tests/chat-stream.mjs` and `hud.mjs` read it).

Before `chat-stream.patch`, a turn with tools on was sent as
`application/json` with an SSE body, which the HUD page cannot read ("Unexpected
token 'd'"). An older note here said the phone mis-reads SSE; it has not since
`ChatChunkParser` existed.

**Lines that are not the answer.** Two SSE comment lines (they start with
`:`, and every SSE reader skips them): `: keepalive`, after 10 seconds with
nothing else to send, and `: jarvis-status approval` (or `working`) while an
approval card for a tool waits. The apps show "Waiting for your approval…"
for the second.

**`: jarvis-status loading` (2026-09-25).** Said instead of `thinking` for the
first wait of a turn when the model is not in memory yet - Ollama's
`/api/ps` on this PC did not list it when the turn began (after standby, or
the first question of the day). Like the other words it is said only once the
wait has lasted 1.5 seconds. Both apps show "Waking up the model - the first
answer after standby takes a little longer." An app that does not know the
word ignores it and keeps its own "Thinking…".

**When an answer fails (2026-09-25).** The PC's own failure sentence arrives
as `{"error": {"message": "...", "type": "jarvis", "code": "..."}}`. `code` is
new, and is there only for the PC's own failures (`jarvis_agent.ERROR_CODES`):
`model_missing`, `model_not_running`, `model_stuck`, `model_stopped`,
`model_error`. Both apps turn a failure - a code, an HTTP status, a network
failure - into the SAME plain words: what happened, what to do, and ONE
button ("Try again", "Reconnect", "Check the connection settings", "Choose a
model"). The PC's sentence and any technical detail go behind a "Details"
toggle, scrubbed first (no token, key, password, email address or user
name). The words and the rules that pick them are one list,
`tools/gen_plain_error_cases.py`, written to `plain-error-cases.json` for
both apps' tests. A failure with no code shows the PC's sentence as before.
The desktop's `stream_chat` now rejects with one tagged line of facts
(`\u001fjarvis-error:{"network"|"http", "said", "detail"}`) that the page
turns into those words, instead of an English sentence.

"Streaming" and the "N chunks · 3.4s" count are gone from the desktop's
answer card: it says "Answering…" once words arrive, and nothing in the
corner.
**How the card ended (added 2026-09-25).** After an `approval` line, and only
then, the PC sends one more at once: `: jarvis-status approved`, `denied` or
`timed_out` - the gate's own outcome word (`jarvis_agent.CARD_OUTCOME_WORDS`,
`_Out.card_answered`). Nothing else is in it, never what the card was for. A
gate that answers before the `approval` line went out (under 1.5 seconds)
sends neither. During a **spoken** question both apps say, in fixed words
(`backend/jarvis_card_words.py` `VOICE`; desktop `card-words.js`, phone
`voice/CardVoice.kt`):

| Word | Said aloud |
|---|---|
| `approval` (once per card) | "I need your OK for that. There's a card on your screen." |
| `approved` | "Approved. Carrying on." |
| `denied` | "OK, I won't do that." |
| `timed_out` | "That card timed out, so nothing was done." |

An outcome is said only after the waiting line was. These are fixed lines,
so they are said whatever the private-answer rule decides for the answer
itself (§16); the answer's own words still follow that rule. **There is no
approving by voice** and there will be none: the voice check cannot tell a
recording from the owner, so a "yes" said aloud answers nothing - only a tap
on the card does. `tools/gen_card_words_cases.py` writes the lines and a set
of status-word sequences (`voice_script`) into one file both apps' tests
read.

**Cancelling.** Android cancels the OkHttp `Call` (`ChatSession.cancel`); the
desktop drops the request future (`commands.rs` `cancel_chat`). While words
are streaming the PC sees the app go at its next write and stops Ollama. While
it is waiting (an approval card, a tool running) it notices at the next
keepalive, within about 20 seconds, and then does **not** run a tool that is
approved after that - nobody is there to read the answer - and says so on the
event bus. Before `chat-stream.patch` it did not notice at all during a
wait, and an approved tool ran for nobody.

**Timeouts.** Android gives chat a 120-second *read* timeout, not a call
timeout — the clock restarts on every byte, so a four-minute reply is fine but
two minutes of silence is a wedge (`JarvisApi.kt`, the comment on `client`).
The keepalive above is what keeps a three-minute approval wait inside that.
The HUD page uses the same kind of 120-second silence limit.

**`turn_id` in `X-Jarvis-Route`** (`feedback.patch`). The chat response's
`X-Jarvis-Route` header (JSON) now carries `turn_id`, a 32-character hex id
for this answer. Show a right/wrong mark on the answer only when it is there,
and post it to `/api/feedback/mark` (§6). Missing means an older backend or
that recording failed - show no mark buttons. **Android reads it** in
`ChatSession.send` (parsed by
`Feedback.turnIdFromRouteHeader` in `net/Learning.kt`): the header must be a
JSON object and the id exactly 32 lowercase hex characters, the same rule the
backend's `jarvis_feedback._TURN` applies, or the phone shows no buttons. The
id is cleared the moment a new question is sent, so a mark can never land on
the answer being replaced. Home shows "Was this right?" with Right and
Wrong under a finished answer; tapping the chosen one again sends `"none"`;
nothing is sent while the event stream is stale (the same `actionBlocker` as
the other writes); a `404` (unknown answer) or `503` (module missing) swaps
the buttons for one quiet line. The phone does not read
`/api/feedback/counts` - a per-fact list of counts needs the fact list beside
it, which is the desktop Brain's job. The quickbar gets the id from
`pump_chat` as its own line (`TURN_LINE_PREFIX`); the HUD page's mark
(`hud_bootstrap.js`) appears only once the answer has finished.

**`where` in `X-Jarvis-Route`** (`chat-stream.patch`): `"local"` or
`"cloud"` - where the answer was made - with `lane` set to the lane that
really answered. The apps' Local/Cloud badge reads it (an older backend
without it is read by `gate`: only `"escalate"` picks a cloud lane). The
quickbar used to guess from each chunk's `model` name and the HUD page tested
`gate == "privacy"`, a gate the router never returns - so every answer there
was painted as cloud.

**`gate: "cloud_model"` in `X-Jarvis-Route`** (security audit H1, 2026-09-25):
the everyday model is one of Ollama's cloud models (`-cloud` / `:cloud`,
answered on ollama.com, not on this PC). Nothing is sent to it: the answer
is one plain error ("Jarvis did not answer: the everyday model ... is one of
Ollama's cloud models ...", in the same framing as any other failed turn),
and `inject_memory` is false. The same happens, with a sentence of its own,
when `OLLAMA_URL` is not this PC. Apps show the error as they show any
other; nothing new to handle.

**`offer` in `X-Jarvis-Route`** (the router, 2026-09-24): a cloud lane that
could have answered this turn, named but NOT used - gate `"offer"`, `where`
`"local"`. The router sends a turn to a cloud lane only when the owner said
yes for that one question (`jarvis_router.choose(owner_said_yes=True)`), and
never for a turn a privacy gate kept local; those carry no `offer` at all.
No app sends that yes yet - asking is built with "model advice" - so today
no answer goes to a cloud lane on its own. Apps that do not know `offer`
read the turn as local, which it is.

**`second_card` in `X-Jarvis-Route`** (`second-card.patch`, 2026-09-24): on a
turn the second graphics card answered, `where` is still `"local"` (it is
this PC), `lane` is the model really answering (e.g. `"qwen3:8b"`), and
`second_card` says why: `"long_context"` or `"vision"`. Absent on every other
turn. See section 12.

**`injected_sensitive` in `X-Jarvis-Route`** (`auto-learn.patch`,
2026-09-24): how many of the recalled facts this answer used (`injected_facts`)
are **sensitive** - health, money, passwords and account details, other
people - by `jarvis_auto_learn.sensitivity()`, the same check automatic
learning uses. Worked out after the degrade loop, so a turn that left the
local lane (memory dropped, `injected_facts: 0`) says `0`. It fails closed:
a recalled fact that was not checked (the check could not run, or it was
recalled somewhere this patch does not see) counts as sensitive. **Missing
while `injected_facts` is above 0** - a PC from before this - means "all of
them may be sensitive". The apps use it to keep such an answer on screen
when the question came by voice (§16, "What the apps must do about private
answers"). Said plainly: the header is built in the owner's `jarvis_hud.py`,
which is not in this repository; the patch sets this field beside the
`turn_id` line `feedback.patch` added, and was checked only against the
patch-stack stand-in (`backend/test_auto_learn.py`).

**Which facts a local turn recalls** (memory wave 1, 2026-09-24; no field or
route changed). Word search now has a floor (`JARVIS_MEMORY_MIN_WORD_SHARE`,
default 0.1), so a question that shares one ordinary word with a fact no
longer recalls it - `injected_facts` is 0 more often, which is right. And a
question about the past ("where did I live before?", "what did I tell you in
June?") also recalls up to three matching **retired** facts
(`past-recall.patch`, `jarvis_past.py`), each ending "(no longer true since
<date>)" inside the FACTS block. They are counted in `injected_facts`,
listed in `injected_ids` and checked for `injected_sensitive` like any
other recalled fact. `backend/README.md`, "Memory wave 1", has the details.
(Since 2026-09-25 both apps can show the facts an answer used - "Used in
this answer", below.)

**"Always keep in mind"** (memory wave 2, the owner's decision of
2026-09-24; `memory-profile.patch`, `rebuilt/jarvis_memory.py`
`with_profile()`; the list itself is §6 `/api/memory/profile`). Every local
turn that recalls memory now starts the FACTS block with the facts the
owner pinned, under the fixed line "Always keep in mind (the owner pinned
these):", word for word, each through the same `recall_line` as every
other recalled fact; then "Recalled for this question:" and the searched
facts. A pinned fact the search also found is not listed twice. With
nothing pinned the block is exactly what it was. Pinned facts are counted
in `injected_facts`, listed in `injected_ids` (first) and checked for
`injected_sensitive` like any other recalled fact, so the read-aloud and
sensitive-on-screen rules (§16) cover them. `JARVIS_MEMORY_K=0` is still no
memory at all - pinned facts included - and a turn that leaves the local
lane drops them with the rest of the block. The block stays off position 0:
on a conversation's first question `jarvis_agent.keep_rules_first()` puts
the Jarvis rules in front of it (`backend/test_memory_profile.py` holds
that with pinned facts in the block). A pinned fact never gets a "retire
this?" card from answer marks (`jarvis_feedback.py`): it is in every answer,
so its marks say nothing about it.

**A temporary chat** (the owner's decision, 2026-09-25;
`backend/temporary-chat.patch`; the request field is §18.1). A request with
`"temporary": true` (JSON `true` and nothing else) is answered exactly like
any other - the same tools, the same approval cards, the same local-first
routing - except that:

- **no fact is recalled**: no search, no pinned list, and nothing the older
  word list over the jsonl might find. In place of the FACTS block the model
  gets one fixed system line, in the same place: "This is a temporary chat.
  You have no saved facts about the user in it, and nothing said in it is
  remembered, learned or kept. If the user asks you to remember something,
  say that Remember is off in a temporary chat."
- **nothing is learned**: the learner is not offered the turn, so no
  background learning, no proposal and no "Remember:" card or automatic save.
- **nothing is kept in the chat history** (§18): `jarvis_chat_log` notes a
  HASH of the live message in its in-memory registry - never the words - so
  a tool that read outside text still marks the rest of the conversation
  (the note-write card), under the provenance `"temporary"`, which automatic
  learning always turns into a card ("said in a temporary chat, which
  Jarvis never learns from") if an app ever re-sent the turn in a normal
  chat. Nothing is written to `chat-history.db`. A `jarvis_chat_log.py` older
  than this (no `TEMPORARY_CHAT`) is not called at all for a temporary chat.

`X-Jarvis-Route` then carries **`"temporary": true`**, `injected_facts: 0`,
`injected_ids: []`, `injected_sensitive: 0`, `memory_side: "none"`, and
**`"remember_off": true`** when the newest user message was a "Remember:
..." (the apps show "Remember: is off in a temporary chat."). `temporary` is
left out when memory is Jarvis's own upstream's (`memory_side: "jarvis"`),
which the PC cannot switch off. An app that sent `temporary: true` and gets
no `"temporary": true` back says so - "Your PC did not confirm this was a
temporary chat, so this answer may have used your memory and the chat may
be kept." - and never pretends. The right/wrong mark (`turn_id`) still
works: it records the answer's id and no fact.

`GET /api/version`'s `capabilities.temporary_chat` is true only when the
running server has the patch (asked of the server by name, like
`appearance`). Both apps offer the mode only then, and check again before
every temporary question; otherwise they say "Temporary chat isn't
available on this PC's version of Jarvis, so nothing was sent. Run
apply-patches.ps1 on the PC to update it." and send nothing. Turning it on
or off needs no card - it only ever makes a turn stricter - and starts a new
conversation in both apps, so nothing said in one kind of chat is re-sent in
the other. Both apps: a marker for the whole chat, and on the empty chat
"Temporary chat: Jarvis won't use or learn from your memory, and this chat
isn't kept." Desktop: the quickbar's temporary-chat button and strip
(`answer-memory.js`; `stream_chat` refuses to send one to a PC without it).
Phone: "Temporary chat" above Home's chat box, "End" to leave it
(`UsedMemoriesPlate.kt` `TemporaryChatStrip`, `ChatSession.setTemporary`);
the voice loop's questions go temporary too. The HUD page (the backend's own
`jarvis_hud.html`) has no temporary chat.

**"Used in this answer"** (the owner's decision, 2026-09-25). Both apps
read `injected_ids` - its `"mem:<id>"` entries, as numbers; `"fact:<n>"`
(the older word list) has no id and is not listed - and under an answer
that used any show a quiet line, "Used 2 memories". Only when it is opened
are the facts' words read, by id, from `GET /api/memory/used` (§6) - the
header never carries words. Each fact shows its words, "pinned" when it is
on "Always keep in mind", "no longer in use" when it is not current (a
question about the past recalls retired facts), "Erased on <date>" (desktop)
/ "Erased" (phone) instead of words for an erased one, and a Forget on each
fact still in use, with the confirm both apps already use; the desktop adds
"Erase the words" beside it. One fact per tap, held on a stale link, hidden
while the memory lists are hidden (Windows Hello / the phone's "Hide memory
lists and chat history"). Desktop: the quickbar (`answer-memory.js`; the
route line carries the ids as `memory_ids`, commands.rs
`route_line_from_header`). Phone: under the answer on Home
(`ChatSession.usedIds`, `UsedMemoriesPlate.kt`).

**No tool receipt.** A 200 from `/api/chat` means "a chat completed", not
"the thing you asked for happened". There is no `tool_calls` field on the
response. `docs/API-DISAGREEMENTS.md` §10 records the consequence: the quick-
capture widget used to say "Appended to Logseq." on any 200, and now reports
only what Jarvis itself said it did.

**Tool calls and outside text** (`jarvis_agent.py`, 2026-09-24). One thing
here changes which tools need a card - note writes after outside text, the
owner's decision after the safety research - and the rest does not. All on
the PC, no app change needed:

- **A note write after outside text waits for a yes.** In a turn where a
  reading tool ran (anything but the calculator and the note writes
  themselves), or the conversation is tainted, or the newest message's
  `provenance` is `pasted`, `shared` or `clipboard`, `append_obsidian_daily`,
  `append_logseq_journal` and `create_joplin_note` go to the gate as
  **`write_notes_after_outside_text`** instead of their own action - `"ask"`
  in the shipped `jarvis-framework.toml`, and `"ask"` through
  `unknown_action_tier` in a file without the line - so a card is raised.
  The card's `detail.text` has one plain line above "What shaped this
  request:" - "Jarvis read outside text in this conversation, so it asks
  before writing to your notes." (or, when only the newest message was not
  typed: "Your newest message was pasted in, not typed, so Jarvis asks
  before writing to your notes."). The note runs only when the verdict
  records a person approving: a config that sets the new action to `auto`
  gets the note refused, never written unasked. A note action set to
  `"never"` stays never; one already at `"ask"` keeps its own action and
  gets the same line. Any other turn: unchanged, the note's own tier decides
  (the shipped config saves straight away). The approval notice reads "Jarvis
  wants to write notes after outside text" and says it stays on this PC
  (`note-capture.patch`'s risk line); a "no" on this card never becomes a
  proposed standing rule (`gate-outcome.patch`). Not affected: the `#log` /
  `#obs` / `#joplin` prefixes and the quick-note field, which go to
  `POST /api/notes/capture` with no model involved (§11) - the
  capture route is not told whether the words were typed or pasted, so a
  pasted `#obs` note is filed the way a typed one is.

- **A broken tool call raises no card.** Before a call is prepared, its
  arguments are checked against the tool's own schema: not JSON, not an
  object, a required field missing or blank, a wrong type, a value outside
  the allowed list, a key the tool does not have. A broken call is never
  prepared and never reaches the gate; the model is told what was wrong in
  one sentence and may try once more. A second broken try at the same tool
  in the same answer ends it, and the answer itself carries one plain line
  saying so ("Jarvis tried to use shell_exec twice and could not write the
  request correctly, so it was not used. Nothing ran and nobody was
  asked."). It used to turn such arguments into `{}` - a `shell_exec` card
  with an empty command. An unknown tool name is answered with the names of
  the tools that are on.
- **At most five approval cards in one answer** (2026-09-25,
  `jarvis_agent.CARDS_PER_TURN`; the extraction research's gate fixes).
  A card counts when a person approved it, denied it or left it unanswered.
  Past five, a call that would raise a card is refused before any card is
  raised: nothing runs, the model is told, and the answer itself carries one
  plain line, once ("(Jarvis wanted to ask for your approval more than 5
  times in one answer, so it stopped asking. Nothing more was run. Ask again
  in a new message to carry on.)"). A tool that asks nobody (tier `auto` or
  `notify`) is not limited. A new message starts at zero. Both apps show the
  line as part of the answer; neither needed a change.
- **Several smart-home devices on ONE card** (2026-09-25, the owner's
  decision after the creativity audit; `jarvis_home.plan_services`).
  `home_control` takes `entity_ids` (a list, at most 10) beside `entity_id`:
  the same service and data on each device, one request per device, and
  ONE approval card - so it counts once toward the five. The card's first
  line names every device and the action ("Jarvis would like to call
  light.turn_off on 3 Home Assistant devices: light.kitchen, light.hall,
  light.bedroom."), then each device's exact request and body, numbered,
  and says it is one decision about exactly these devices, with nothing
  added after the yes and no permission for anything later. After a yes,
  exactly the listed requests are sent, in order (a digest of them is taken
  when the plan is made, and `run()` sends nothing if they no longer
  match); one device failing does not stop the others, and the model is
  told which worked (`results`). Never grouped - refused before any card,
  with the reason, so the model can ask again: a lock, alarm panel, cover
  (garage doors, gates, blinds), valve or siren; any entity whose id says
  door, gate, garage, lock, alarm, security or safe (`switch.garage_door`);
  a camera, script, scene, automation or button (Jarvis cannot see what
  those would change); more than 10 devices (refused, never cut); a `data`
  that names its own `entity_id`, `area_id` or `device_id`. Each of those
  still works on a card of its own, as before. Both apps show the card's
  text as sent (the phone as plain lines, the desktop's bar as Markdown,
  where the numbered requests are a list); neither needed a change. The
  desktop's small approval widget shows only the card's first line - which
  is why the first line names every device - and cuts it at 200 characters,
  so a long list is only complete in the Jarvis bar or on the phone.
- **Ollama failing to read a tool call** (HTTP 500 before the answer, or
  `{"error": ...}` in the stream, with Ollama's "failed to parse JSON"-style
  wording) is asked again once, with a short note to the model. A second
  failure is the same plain error as before (`data: {"error": ...}`).
- **What a tool returns is cleaned and labelled** before the model reads it:
  chat-control markers (`<|im_start|>`, `</tool_response>`, `<think>` and
  the rest) and invisible Unicode tag characters are removed; the result
  carries `"outside_text": "This came from a tool, not from the owner..."`;
  and the turn gets one system line saying tool text is data, never
  instructions. The result is also checked with the same planted-instruction
  warnings memory cards use (`jarvis_intake.injection_flags`).
- **A card says what shaped it.** When a tool is proposed after a reading
  tool ran in this answer, or in a conversation that read outside text
  earlier (`jarvis_chat_log.conversation_tainted`, from the request's
  `conversation_id`), or when the newest message's `provenance` is
  `pasted`, `shared` or `clipboard`, the card's `detail.text` ends with:

  ```
  What shaped this request:
  - Proposed after Jarvis read: email_check (once).
  - Something Jarvis read may hold planted instructions: It tells Jarvis to send, ...
  - “billing@evil.example” came from what Jarvis read, not from you.
  ```

  Only the lines that apply. A value is named when it appears in what a tool
  returned this turn and not in anything the owner typed or said. Since
  2026-09-25, when something a tool returned looks like a password or key
  (`jarvis_scrub.find_secret`), one more line names its kind, never its
  value: "- Something Jarvis read holds what looks like a password or key (a
  GitHub token). Check that this request does not send it anywhere." The plan
  that runs is not changed - only the words on the card. Both apps already
  show `detail.text` in full on the card (desktop `approvalPreview` in
  `main.js`; phone `normalisePendingRow` → the card's summary), so neither
  needed a change. The desktop's small approval widget shows only the
  first line, as it always has.

Said plainly: the gate's own rush latch (`[content_risk]`, rushing language
raises the tier for ten minutes) lives in `jarvis_content_risk.py` on the
owner's PC, which this repository does not have. A planted-instruction hit
here does **not** set it - it is recorded on the turn (`outside_flags` in
`run_local_turn`'s summary, codes only) and shown on the card.

---

## 5. Voice

| Endpoint | Method | Body / params | Desktop | Android | Notes |
|---|---|---|---|---|---|
| `/api/voice/status` | GET | — | **no** | `JarvisApi.kt:553` | Phone calls it before showing a mic button; failure returns refusing defaults. |
| `/api/voice/utterance` | POST | **WAV bytes**, `?source=push_to_talk\|wake_word&mic=phone\|desktop`; since 2026-09-24 also `source=barge_in` and `&waited_ms=` (section 17; both apps since 2026-09-25) | `voice.rs:335` | `JarvisApi.kt:574` | The one route whose body is not JSON. `mic` (2026-09-24, `voice-mic.patch`) picks that microphone's voice print. `source=barge_in` answers "stop or not" and is never transcribed (`voice-flow.patch`). |
| `/api/voice/moment` | GET | - → WAV bytes | `voice_flow.rs` `get_voice_moment` | `JarvisApi.voiceMoment` | The "One moment." clip in the voice in use now (section 17, `voice-flow.patch`). 503 with `why` when there is none. |
| `/api/voice/say` | POST | `{"text": …}` → WAV bytes | `voice.rs:716` | `JarvisApi.kt:601` | **503 is a legitimate answer.** |
| `/api/voice/wake` | POST | `{"enabled": bool}` | `voice.rs` `ensure_wake_ready` | `JarvisApi.setWakeWord` | ON raises an approval card; OFF is immediate. |
| `/api/voice/enroll` | POST | `{"clips": ["<base64 WAV>", ...], "mic": "phone"}`; also `"mode": "calibrate"` / `"threshold"`, and since 2026-09-24 `"train"` / `"strictness"` / `"privacy"` / `"memory"` / `"measure"` (§16) | `voice_training.rs` `send_voice_training`, `set_voice_setting`, `measure_voice`, `cancel_voice_training` | `JarvisApi.enrollVoice`, `calibrateVoice`, `proposeVoiceThreshold` | "Train my voice". Raises an approval card; enrols nothing itself. `voice-enroll.patch`. |
| `/api/voice/turn` | POST | **WAV bytes** (the last few seconds of speech) | `voice.rs` `ask_turn` | **no** (runs the model itself) | Smart Turn: `{"available", "complete", "probability", "threshold", "ms"}`. Sound in, one number out; nothing kept. `voice-turn.patch`. |
| `/api/voice/voices` (+ `/create`, `/active`, `/delete`, `/better`) | GET / POST | see section 15 | `get_custom_voices`, `create_custom_voice`, `set_active_voice`, `delete_custom_voice`, `set_better_voice` (Settings -> Jarvis's voice) | `CustomVoices.kt` via `JarvisRuntime` (Checks -> Jarvis's voice, `VoicesScreen.kt`) | Custom voices (2026-09-24, `voices.patch`), section 15. |

**Since 2026-09-24 `/api/voice/say` may answer in a custom voice** (section
15) - the same WAV, the same 503 when nothing can speak. `/api/voice/status`'s
`tts` block gained `voice` (`{"active", "name", "engine": "kokoro" |
"zipvoice" | "f5", "fallback"}` - `fallback` is the sentence saying why the
built-in voice is used instead of the chosen one, or `""`) and `timings` (the
last five rows of section 15's `timings`).

**Since 2026-09-24 `/api/voice/status` also carries `flow`** (section 17):
interrupting Jarvis by talking (`source=barge_in`), the "One moment." clip
(`GET /api/voice/moment`), the engines kept warm, and each spoken turn's
delay step by step, in numbers. The first status read starts the warm-up in
the background; the reply does not wait for it.

**The audio format: 16-bit PCM in a WAV container. The two apps send
different rates, and the server copes with both** (checked against the code
on 2026-09-24):

- **The phone** sends 16 kHz mono. It records at 16 kHz when the phone
  allows it, and otherwise records at a rate the phone does allow and
  resamples on the phone before sending (`audio/Recorder.kt`,
  `Wav.resample`).
- **The desktop** sends whatever the microphone gives it: the default input
  device's own sample rate and channel count, 16-bit (`voice.rs`,
  `open_input_stream`, which builds the WAV header from
  `default_input_config()`). A 48 kHz stereo headset arrives as 48 kHz
  stereo. **Pending:** the desktop is being changed to downmix to mono and
  resample to 16 kHz before sending, so both apps send the same thing.
- **The server** reads any 16-bit PCM WAV (`jarvis_speech._read_wav`;
  anything else - 8-bit, 24-bit, float - is refused as unreadable), averages
  the channels down to mono, and resamples where a model needs 16 kHz
  (`jarvis_wakeword.to_16k` for the speech check; the speech-to-text and
  voice-print models are told the real rate and resample themselves).

Two places still say the old rule ("fixed at 16 kHz mono, and the server
will not convert"): the phone's comment on `JarvisApi.utterance`, and
`AUDIO_IN` in `jarvis_speech.py`, which `/api/voice/status` reports. The
reason they gave still stands as a goal - these are bytes arriving from the
network *before* the gate, so the less that code has to do, the better -
which is why the desktop is being changed to match the phone rather than the
other way round.

**503 from `/api/voice/say` means "there is no speech engine here", not
"failed."** Speaking text the client already holds reveals nothing and skips
no check, so this is the one half of the voice path allowed to be missing.
The body may carry `client_fallback_ok` (a boolean) and `reason`
(`JarvisApi.kt:612-628`). Absent `client_fallback_ok` is treated as **false**,
deliberately — that flag decides whether the owner's reply gets handed to the
handset's default engine, which on a stock phone is Google's. A 200 carrying
no audio is treated as a server fault, not as permission to synthesise locally.

**`/api/voice/wake` with `true` asks, it does not apply.** Since 2026-09-23
`jarvis_speech.set_wake_enabled(True)` raises ONE approval card
(`change_own_config`, through `jarvis_gate.check()`, the tier checked before
the card and on the answer) and returns at once with
`{"ok": true, "pending": true, "enabled": false, "message": ...}`. Only
approving the card turns it on. A second request while a card waits is
`{"ok": false, "pending": true, "error": ...}`; a tier other than `ask` is
`{"ok": false, "error": ...}` and no card. `false` is immediate -
`{"ok": true, "enabled": false}` - and also cancels a waiting card (approving
it afterwards does nothing). What `jarvis_hud.py`'s route does with this dict
is not visible here; the module used to return `{"ok": true, "enabled": ...}`
for both. Re-read `/api/voice/status` to learn the truth:
`listening.wake_word`, `listening.wake_word_pending`, and a `wake` block -
`{enabled, pending, expires_in?, last?, phrase, threshold, awake_seconds,
spotter: {available, engine, why}}` (`spotter` says whether this PC can hear
"hey Jarvis" in a clip, which the desktop app's listening needs).

**`source=wake_word`.** The server refuses it while the wake word is off
(`available: false`). Otherwise it runs, in order: Silero VAD (no speech ->
refused), the "hey Jarvis" spotter (not heard -> refused, never voice-checked
or transcribed), the owner check, speech-to-text, and finally the transcript
must start with "hey Jarvis" (else `text: ""`, "ignored"). Four fields were
added to the reply: `wake_heard` (the phrase was heard, from the owner),
`wake_score`, `awake` (the clip was only "hey Jarvis": the next `wake_word`
clip within `awake_seconds` needs no phrase), `awake_seconds`. The returned
`text` has the phrase removed. A client drops a reply with `wake_heard:
false` silently. `backend/README.md`, "Voice that works", has the details.

**"Stop" (since 2026-09-24).** Before the spotter, a `wake_word` clip with at
most 2 s of speech (`STOP_MAX_SECONDS`) is put to the stop-word model
(`jarvis_wakeword.spot_stop`). If it is "stop" ("stop", "Jarvis, stop"),
the reply is `stop: true` with `owner: false`, `ok: false`, `text: ""` -
no voice check, no speech-to-text, nothing kept - and the desktop app
silences the reply it is speaking; nothing else happens. Ignored (a plain
refusal) while Jarvis itself said "stop" in the last 30 s: then the reply
has `stop: false`, `stop_ignored: true`, and a `reason` sentence saying so
and how many seconds to wait, which an app can show as it is. "Said stop"
means the whole word (`\bstop\b`, so "stopped" or "stopwatch" do not
count), and it is kept per app: words `say()` was told were for the phone
only hold back the phone's microphone, and the same for the desktop. Words
said with no app named - which is what the say route does today - still
hold back both. Every reply carries `stop` and `stop_ignored` (false
otherwise). The status's `wake` block adds
`stop_word: {available, threshold, why}`. The phone spots "stop" on its own
(the same numbers, `assets/wakeword/stop_head.bin`) and sends nothing for it.

**Since 2026-09-24 `/api/voice/enroll` also takes** a `mic` ("phone" or
"desktop": which microphone's voice print this trains - one print per
microphone, the old single `owner.json` read as the fallback), up to 12
clips (80 s in all), and two more modes on the same route:

- `{"mode": "calibrate", "mic": "phone", "clips": [...]}` (1-5 clips of
  SOMEONE ELSE): 200 `{"ok": true, "scores": [0.21, ...], "threshold": 0.35,
  "owner_low": 0.62, "others_high": 0.4, "separated": true, "suggested":
  0.51, "print": "phone", "message": "..."}`. Scored and dropped; no card;
  nothing changes. `suggested` is null unless every one of the owner's own
  training clips scored above every one of theirs. 409 `{"ok": false,
  "error": ...}` when nothing is trained.
- `{"mode": "threshold", "mic": "phone", "threshold": 0.51}`: raises ONE
  card to use that bar for that microphone's print (0.05-0.9); 202 like a
  training. The outcome shows as `last.outcome = "threshold_set"`.

**A client must not send either mode unless `gate.training.calibrate` is
true**: an older PC reads any body with clips in it as a training. The
status also carries `gate.prints` = `{phone, desktop, general}`, each
`{trained, samples, threshold, created, needs_retraining}`, and
`gate.training.last.wake_check` (the "hey Jarvis" verifier built from the
same training, `jarvis_wakeword.py`).

**`/api/voice/turn` - Smart Turn** (`voice-turn.patch`, module
`jarvis_turn.py`, added 2026-09-24). "Has the speaker finished, or only
paused?" The body is one WAV (any rate, mono or stereo, at most 30 s; only
the last 8 s are used). The answer is always 200 unless the body is not a
WAV (400): `{"available": true, "complete": bool, "probability": 0..1,
"threshold": 0.5, "ms": 43.0}`, or `{"available": false, "why": "..."}` when
the model is not installed. The desktop asks it after 200 ms of quiet while
listening for "hey Jarvis" (the same audio already goes to this PC over
loopback); the phone runs the same model on the phone. `/api/voice/status`
carries `turn`: `{enabled, available, threshold, ask_after_ms: 200,
max_pause_ms: 2000, engine, why}` - `enabled` (`[voice] turn_enabled`)
governs both listeners.

**`/api/voice/enroll` - "Train my voice"** (`voice-enroll.patch`, module
`jarvis_voice_enroll.py`). The phone sends the owner's recorded sentences:

```
POST /api/voice/enroll
{"clips": ["<base64 of one WAV>", ...]}       3 to 12 clips, each 1-10 s, 80 s in all,
                                              16 kHz 16-bit mono, not silent
```

JSON with base64 rather than a raw WAV body, because there are several clips
and each needs its own boundary. The route checks origin and token like the
other writes. Answers:

| code | body | meaning |
|---|---|---|
| `202` | `{"ok": true, "pending": true, "clips": 5, "seconds": 21.4, "message": "..."}` | The clips are held **in memory** and ONE approval card (action `change_own_config`) is up. **Nothing is enrolled yet.** |
| `400` | `{"error": "clip 3 is too short (0.6 s) - read the whole sentence"}` | A clip, the count or the body is wrong. The sentence names the clip and is written for the owner. |
| `409` | `{"error": "...", "pending": true, "expires_in": 140}` | A training card is already waiting. It is not replaced. |
| `409` | `{"error": "change_own_config is tier 'auto' ...", "pending": false}` | The tier is not `ask`, so no card was raised. |
| `503` | `{"error": "voice training is not installed on this PC", "available": false}` | `jarvis_voice_enroll.py` is missing. |

Approving the card runs `jarvis_voice.enroll()` with the same embedder
`hear()` uses, then deletes the clips. Denying, a timeout or any refusal
deletes them and changes nothing. The outcome shows up in the status:

**`/api/voice/status`** now sends the nested shape the phone reads -
`available`, `listening` (`push_to_talk`, `push_to_talk_why`, `wake_word`,
`wake_word_why`), `stt`, `tts`, `audio_in`, and `gate` (`mode`, `enabled`,
`enrolled`, `samples`, `threshold`, `embedder`, `speaker_model`,
`needs_retraining`, `note`, and `training`: `available`, `pending`, `clips`
and `expires_in` while a card waits, `last` = `{outcome, at, samples,
reason}` once one has been answered). The old flat keys are still there.
Before 2026-09-23 only the flat keys were sent, so the phone's
`listening.push_to_talk` was always missing and its talk button never
appeared. `listening.push_to_talk` is true only when a clip could get an
answer end to end: the voice is trained (or mode is `broad`) **and** there
is speech-to-text on the PC. `backend/test_voice_contract.py` checks this
JSON against `VoiceModels.kt` and the desktop's `voice.rs`.

**`/api/voice/utterance`'s answer** carries both clients' names:
`is_owner`/`available` (desktop, `voice.rs` `HeardRaw`) and `ok`/`owner`
(phone, `Heard`), plus `mode`, `seconds` and `engine`. This assumes the
route sends `jarvis_speech.Heard.as_dict()` unchanged, as `voice.rs` also
assumes; the route's reply line is not in this repository.

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
| `/api/version` | GET | `sidecar.rs:321`, `stream.rs:569` | `JarvisApi.kt:268` | The handshake. **Branch on capabilities, never on version numbers** (`JarvisRuntime.kt:394-396`). Also carries `activity` (the state word) - since 2026-09-23 in the rebuilt `jarvis_events.hello()`, which did not send it before. `capabilities.power` is `jarvis_power.status()` (`mode`, `why`, `quiet_hours`, ...) rather than a bare `true`; `capabilities.appearance` is true when `appearance.patch` is in the running server; `capabilities.temporary_chat` (2026-09-25) when `temporary-chat.patch` is - both apps offer a temporary chat only then (§4), the desktop asking through `temporary_chat_available` and again in `stream_chat`. `capabilities.owner_check` (2026-09-25) is `"backend"` when `owner-check.patch` has wrapped the running server's `/api/approve` (§3, "The PC's own check before an approval"); the desktop then leaves Windows Hello for risky cards to the backend. `capabilities.stop_all` (2026-09-25) is true when `stop-all.patch` has wrapped the running server's POST handler, so `POST /api/stop_all` answers (§28). `started` (2026-09-25) is when the server process started, in epoch seconds (§29). The desktop falls back to `/api/status` for anything an older server leaves out. |
| `/api/status` | GET | `commands.rs:677`, `routes.rs:16`, `stream.rs` (power/activity fallback) | `JarvisApi.kt:271` | Reports the power mode (written by `POST /api/power` since `power-mode.patch`). Also `held` (a boolean): **what sets it is not documented anywhere in this repository** - it comes from the owner's `jarvis_hud.py`. Two phone comments used to give it two different meanings; the Brain screen now says only "something held back" and points to the undo shelf, and the quick-settings tile does not read it. |
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
| `/api/memory/status` | GET | `routes.rs:28` | **no** | `{available, db, facts, current, retired, erased, entities, embedder, semantic, vector_search, unembedded, sleep_time}` - `MemoryStore.status()` plus the route's own two. `facts` counts retired ones too; `current` is what is in use; `erased` (since 2026-09-24) counts facts whose words were erased; `entities` (since 2026-09-25) counts the people and things facts are linked to (one per group), and `entity_errors` appears only when linking a saved fact failed (the fact is saved either way). |
| `/api/memory/pending` | GET | `routes.rs` (`memory_pending`), as `?retire_cards=1&sleep_offer=1&merge_cards=1` (the "are these the same?" card, desktop only - below) | via `probe`, as `/api/memory/pending?retire_cards=1&sleep_offer=1` (`MemoryCards.PENDING_PATH`, read by `JarvisRuntime.refreshBrain`/`refreshMemoryQueue`) | The review QUEUE, never the corpus. Both apps ask for retire cards because they label them correctly, and for the overnight-tidy card because they show it - see below. The HUD page reads it plainly, for a count only. |
| `/api/memory/facts` | GET | `routes.rs:32`, `brain.rs:413` | `JarvisApi.kt:429` | Takes `?known_at=<unix seconds>` — "what did I believe then?" Each fact's `current` is judged as Jarvis knew it at that moment, not as of today: a fact retired later (`retired_at` after that moment) was current then; `valid_to` counts only while `retired_at` is empty (`bitemporal.patch`). Every row carries `erased_at` (a column since 2026-09-24): a number means "Erase the words" was used on it - its `text` is then only the marker `[erased]`, and both apps show "Erased on <date>" instead, never the marker (`/api/memory/erase`, under Writes). |
| `/api/memory/export` | GET | `brain.rs` `brain_memory_export` | **no** | Everything, current and retired. The desktop saves it to a file the owner picks in the Windows "Save as" dialog - never the clipboard, which Windows can sync to other devices. |
| `/api/initiative` | GET | `routes.rs:33` | via `probe` | The **only** list route that uses the key `items`. |
| `/api/attention` | GET | `attention.rs:54`, `routes.rs:34` | `JarvisApi.kt:277` | Nests the budget; the phone flattens it (`ApiModels.kt:366`). |
| `/api/digest` | GET | `attention.rs:81`, `routes.rs:35` | `JarvisApi.kt:280` | List key: `digest`. |
| `/api/config` | GET | `routes.rs:36` | **no** | **Read-only: writing answers 501.** This is why there is no shared place to store a preference — `API-DISAGREEMENTS.md` §11. |
| `/api/visual-spec` | GET | `spec_drift.rs:50` | **no** | Desktop checks its bundled spec against the server's at startup. The phone never fetches it. |
| `/api/appearance` | GET / POST | `appearance.rs` | `JarvisApi.getAppearance` / `postAppearance` | `appearance.patch`. `/api/version` lists `capabilities.appearance` (rebuilt `jarvis_events.hello()`); the phone also tries the route once when the flag is absent. See §7.3. |
| `/api/feedback/counts` | GET | **no** | **no** (not built - see the `turn_id` note in §4) | `feedback.patch`. Token + origin. `{"facts": {"<fact id>": {"helpful", "harmful"}}, "skill_notes": {same shape}, "answers_marked": {"right", "wrong"}, "retire_cards_raised", "threshold": {"min_wrong": 5, "ratio": 3}, "note"}`. Match a fact id to its words with `/api/memory/facts`, and show `note` with the counts: a fact in a wrong answer did not necessarily cause it. `503` if `jarvis_feedback.py` is missing. |
| `/api/feedback/mark?turn_id=<id>` | GET | **no** | **no** - not needed: the phone keeps the mark for the one answer on screen in memory, and that answer is gone when the app is | `feedback.patch`. The current mark on one answer: `200 {"turn_id", "mark"}` (`"right"`, `"wrong"` or `"none"`), `404` if the id is unknown on this machine. |
| `/api/skills/suggestions` | GET | **no** | **no** | `skill-suggest.patch`. Read-only, same guard as `/api/skills`. `{available, enabled, recording, tier, why_off, min_repeats, window_days, every_hours, in_flight, next_offer_after, ledger_error, note, chains: [{chain, turns, last_seen, status}], offers: [newest first, up to 50]}`; `status` is `eligible`, `counting`, `asked_before`, `declined`, `saved` or `covered`. `{"available": false, "reason"}` if the module is missing. **No approve or save button on this screen** - an offer is decided only on its approval card (§3, action `modify_own_code`). |
| `/api/history?limit=&before=` | GET | `brain/history.rs` `brain_history_list` (Brain, History) | `JarvisApi.history` (Brain, Chat history) | `chat-history.patch`, `jarvis_chat_log.py`, 2026-09-24 - **§18**. Token + origin. The switch's state (`enabled`, `recording`, `why_not`, `waiting`, `keep_days`, `encrypted`) and `conversations`, newest first: `[{id, title, started, updated, turns, device, has_voice, tainted}]`. `limit` 1-100 (default 30); `before=<updated>` pages to older ones. `503 {"available": false, "error", "reason"}` if `jarvis_chat_log.py` is missing. |
| `/api/memory/learning` | GET | `brain_memory_learning_status` (`brain/auto_learn.rs`) | `JarvisApi.autoLearnSettings` | `auto-learn.patch`, `jarvis_auto_learn.py`, 2026-09-24 - **§19**. Token + origin. The learning switches in one read: `{"enabled", "auto", "auto_sensitive", "auto_waiting", "sensitive_waiting", "auto_last", "sensitive_last", ...}` (`enabled` is background learning's own switch). Before this, only the POST existed. `503 {"available": false, "error", "reason"}` if `jarvis_auto_learn.py` is missing. |
| `/api/memory/auto?limit=&before=` | GET | `brain_memory_auto_list` (hidden with the other memory lists under Windows Hello) | `JarvisApi.autoFacts` (hidden under "Hide memory lists and chat history") | `auto-learn.patch` - **§19**. "Saved automatically": `{"facts": [{id, text, saved_at, provenance, device}], "auto", "auto_sensitive"}`, current facts only, newest first; `limit` 1-100 (default 30); `before=<saved_at>` pages to older ones (floored to whole seconds; a page never splits a second). |
| `/api/memory/profile` | GET | `brain_memory_profile` (`brain/profile.rs`; hidden with the other memory lists under Windows Hello) | `JarvisApi.memoryProfile` / `JarvisRuntime.memoryProfile` (hidden under "Hide memory lists and chat history") | **"Always keep in mind"** (the owner's decision, 2026-09-24; `memory-profile.patch`, `rebuilt/jarvis_memory.py`). Token + origin. The facts the owner pinned, which every local chat question reads word for word (§4): `{"facts": [{"id", "text", "added"}], "chars", "limit"}`, oldest pin first. `chars` is how many characters the listed facts' words use; `limit` is 1,200 (`PROFILE_LIMIT`). Only facts still current are listed: a pinned fact that is forgotten, corrected, runs out or is erased leaves the list by itself. Both apps show "N of 1,200 characters used". `501` from a PC whose `jarvis_memory.py` is older (both apps then say the list is not there yet), `503` memory not running. |
| `/api/memory/used?ids=` | GET | `memory_used` (`brain/used.rs`; the quickbar's "Used 2 memories", the Brain's "Jarvis remembered N things" and, since memory wave 3, its "About <name>"; facts taken out in Rust while Windows Hello hides the memory lists) | `JarvisApi.memoryUsed` / `JarvisRuntime.memoryUsed` (Home's "Used 2 memories", the Brain's "Jarvis remembered N things"; hidden under "Hide memory lists and chat history") | **"Used in this answer"** (the owner's decision, 2026-09-25; `temporary-chat.patch`, `rebuilt/jarvis_memory.py` `used_view()`). Token + origin, like every memory read. `ids` is 1 to 100 comma-separated whole numbers above 0 (`"mem:12"` is read as 12); anything else - `fact:3`, a name, a fraction - is a `400` in words. `200 {"facts": [{"id", "text", "current", "pinned", "created", "valid_to", "erased_at"}], "missing": [id, ...]}`, in the order asked. `current` is the usual rule (`valid_to` empty or ahead) and false for an erased fact; a fact that is no longer current still has its words (an answer about the past may have used it); an **erased** fact never has words - `text` is `""`, never the `[erased]` marker. An id with no fact at all is in `missing`. `501` from an older `jarvis_memory.py` (both apps then say they cannot show which facts these were yet), `503` memory not running. A read: nothing here acts on memory. |
| `/api/memory/entities` | GET | `routes.rs` (`memory_entities`; hidden with the other memory lists under Windows Hello, `lock/rules.rs` PRIVATE_LISTS) | **no - by rule** (the memory graph stays off the phone; ARCHITECTURE.md section 8) | **"Who is my sister?"** (memory wave 3, 2026-09-25; `memory-entities.patch`, `rebuilt/jarvis_memory.py` `entities_view()`). Token + origin. The people, pets, places and things saved facts are linked to: `{"entities": [{"id", "name", "kind", "also": [other names joined to it], "aliases": ["sister"], "fact_ids": [newest first], "facts": n}], "count", "limit"}` - one entry per group (a merge is followed), only entries with at least one current, unerased fact, most facts first, at most 500. Names and aliases exactly as the facts wrote them (aliases lower-cased); no fact's words and no summary. `kind` is `person`, `pet`, `place`, `organisation`, `project`, `thing` or null. An app reads the facts' words by id with `/api/memory/used`. The desktop draws the names under each fact in "Saved automatically" and "What Jarvis knows about you", each opening "About <name>" - that entry's facts, word for word (`brain.js` `paintAbout`, `memory-entities.js`). `501` on a PC whose `jarvis_memory.py` predates it. |
| `/api/history/conversation?id=` | GET | `brain_history_open` | `JarvisApi.historyConversation` | `chat-history.patch` - **§18**. One kept conversation, read-only: `{id, title, tainted, turns: [{role, text, at, provenance, read_outside, answer_kept} or {role: "assistant", text, at}]}`. `404` if there is no such conversation, `400` for a malformed id, `503` if it cannot be opened (the reason in words). |

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
conversation text. **Android** does exactly those three things in the Brain's Model
section (`ModelSpeed.from` in `ApiModels.kt`, drawn by `BrainScreen.kt`'s
`ModelsPlate`); `by_model` is matched to the running model by name, treating
`name` and `name:latest` as the same. **The desktop** does the same three
since 2026-09-23 (Brain → Faculties → Models, `brain.js` `modelSpeed`, a
line-for-line port); before that it ignored the block. Both apps can also
**install** a model there now - a typed name, one approval card, no
catalogue.

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
| `verbatim` | bool | True when `source` is `"remember"`: the owner's own words from a "Remember:" message. Label it that way. Since `auto-learn.patch` (§19) it is **false** on a "Remember:" card whose words this PC saw arrive as shared, pasted, clipboard, picture words or untagged, or could not match to a live turn at all - those are not known to be the owner's own words. |
| `auto_reason` | string | `auto-learn.patch` (§19). Why automatic learning left this proposal as a card, in plain words: `"from pasted text"`, `"about health, a sensitive topic"`, `"not in your own words"`, ... Show it as one quiet line on the card. `""` (or absent, on an older backend) when automatic learning was off or never looked at this card. |

**How the phone draws these** (`MemoryCards.from` in `net/Learning.kt`, pinned
by `LearningTest`; drawn by `BrainScreen.kt`'s `MemoryProposalRow`): each `why`
under the plain line "Careful: this may be an instruction someone slipped in,
not a fact about you." and "If you did not say this, discard it." - both
buttons stay; `flags_checked: false` gets one quiet line saying the check could
not run, and an absent `flags_checked` says nothing; a `verbatim` card gets a
"Your own words" label; a correction (a card with a non-zero `replaces_id`)
shows "Would replace: <replaces_text>", and "Both are true" only when
`keep_both_ok` is true AND the card is not a retire card AND it has an id. A
card with `replaces` words but no `replaces_id` is shown as a plain new fact,
because `_accept()` retires only by id. Under the cards: `remember_last.note`
when `queued` is false (a queued one is already a card), and
`near_duplicates_note`.

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
**Android** labels accept "Stop using this fact" (the same action in plainer
words) and discard "Keep using it", with the line "Stopping it does not delete
it. The fact stays in the history - Jarvis just stops using it."
The desktop labels it the same way as the phone (`brain.js` `proposalRow`);
an older client's plain Keep button would say the opposite of what happens
on this card, which is why it is hidden unless asked for:

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

**The "are these the same?" card** (`memory-entities.patch`, memory wave 3,
2026-09-25) is a row in this same queue with `source == "entity_merge"`,
`confidence: null` and no `replaces_id` (so `keep_both_ok` is false). The PC
raises one when a newly named person or thing is a likely typo of one it
already knows ("Priya Sharma" / "Priya Sharmaa"): ONE card per pair, ever.
`text` is the whole question, both names in it. Accepting it
(`/api/memory/decide {"id", "accept": true}`) **joins** the two entries - a
question about one then finds the other's facts - and adds, changes and
retires no fact (`decide` returns 0: there is no new fact). Discarding keeps
them apart, and the PC never asks about that pair again. Label accept "Yes,
the same" and discard "No, keep them apart"; no "Both are true". Like the
retire card it is **hidden unless asked for**: `GET
/api/memory/pending?merge_cards=1` (exactly `1`) includes it; without the
flag it waits, undecided. The desktop asks (`routes.rs`); the phone does not,
on purpose (ARCHITECTURE.md section 8). Erasing a fact that was the only one
to name either person wipes the card's words and turns it down.

**The overnight-tidy card, `setup.sleep_time_offer`, also only when asked
for: `?sleep_offer=1`** (exactly `1`). `jarvis_sleep.reminder_card()` marks
the day's offer as made the moment it is called, so the route calls it only
for a client that shows the card - the Brain window and the phone. Without
the flag the field is `null`. (The HUD page reads this route often and never
showed the card, and used to use up the day's offer that way.) The card says
the feature is not built, and carries `"implemented": false`. Since
2026-09-25 it is also an offer under the back-off (section 22.6): it is not
handed out within two minutes of a chat message or while three other offers
wait (the day is not used up then - a later read that day gets it), and
"Not now" keeps it quiet for 1 day, then 7, then 30.

**Which card says "would replace".** Only a row with a non-null
`replaces_id` replaces anything: `jarvis_extract._accept()` retires by that
id and nothing else. `replaces` alone is the model's own description of
some fact; a row with `replaces` but no `replaces_id` retires nothing, and
neither app says it would.

### Writes

| Endpoint | Method | Body | Desktop | Android | Notes |
|---|---|---|---|---|---|
| `/api/undo/revert` | POST | `{"id": …}` | `brain.rs:158` | `JarvisApi.kt:403` | "The one state-changing thing a phone may drive" — it only moves toward a state the owner already had. |
| `/api/jobs/cancel` | POST | `{"id": …}` | `brain.rs:169` | `JarvisApi.kt:450` | |
| `/api/holds/cancel` | POST | `{"handle": …}` | `brain.rs` `brain_cancel_hold` | `JarvisRuntime.cancelHold` | Both clients take the handle from the undo shelf (`GET /api/undo`): an entry with `category: "hold"` and `detail.handle` - the desktop's reading of that shape, which the phone now shares (2026-09-23). **Unconfirmed against the backend's `jarvis_undo.py`**, which is not in this repo; a shelf without those fields shows no Stop button. |
| `/api/watch/add` | POST | object | `brain.rs:219` | **no** | |
| `/api/watch/remove` | POST | object | `brain.rs:228` | **no** | |
| `/api/watch/seen` | POST | object | `brain.rs:248` | **no** | The consume, vs the GET peek. |
| `/api/skills/decide` | POST | `{"name": …, "remove": true}` | `brain.rs:258` | **no** | **Removal only.** There is deliberately no install route: installing runs the scanner and the gate inside the module. |
| `/api/models/install` | POST | `{"ref": …}` | `brain.rs:434` | `JarvisApi.kt:326` | Allowed from the phone since the 2026-09-20 amendment: tier `ask`, same shape as switch. No catalogue - the ref is typed in, never browsed. |
| `/api/models/switch` | POST | `{"ref": …}` | `brain.rs:435` | `JarvisApi.kt:310` | Allowed from the phone since the 2026-09-18 amendment: tier `ask`, so success means "a card was raised". |
| `/api/models/rollback` | POST | `{}` | `brain.rs:436` | `JarvisApi.kt:314` | Tier `auto`; never waits. |
| `/api/memory/decide` | POST | `{"id": <int>, "accept": bool}` | `brain.rs:283` | `JarvisApi.kt:417` | One id, one decision. **No list form anywhere** — a "keep all" would be an approve-all with another name. |
| `/api/memory/keep_both` | POST | `{"id": <int>}` (a PROPOSAL id) | `brain.rs` `brain_memory_keep_both` | `JarvisApi.kt:439` (`keepBothMemory`) | `memory-intake.patch`. The third answer on a correction card: keep the new fact and do NOT retire the old one. Same claim as `decide` (two taps, one fact). `200 {"ok": true, "id", "fact_id", "kept_id", "kept_text"}`; `409 {"ok": false, "reason": "not_a_correction", "note"}` for a card that retires nothing; `404` if the id is not pending; `400` for a non-integer id; `501` if the patch is missing. Show the button only when the row's `keep_both_ok` is true. |
| `/api/feedback/mark` | POST | `{"turn_id": "<32 hex>", "mark": "right" \| "wrong" \| "none"}` | `commands.rs` `mark_answer` (quickbar, and the HUD page through `hud_bootstrap.js`, which holds no token) | `JarvisApi.kt:451` (`markAnswer`) | `feedback.patch`. One answer, one mark; `"none"` takes a mark back. A list of ids is refused (`400`) - there is no "mark all". `200 {"ok": true, "turn_id", "mark", "was", "changed", "facts", "retire_cards_raised"}`; `400` bad id or mark; `401`/`403` token or origin; `404` unknown id; `503` module missing. A mark never changes memory: at most it queues ONE "retire this?" card (above). |
| `/api/memory/forget` | POST | object, optional `valid_to` | `brain.rs` `brain_memory_forget` | `JarvisApi.forgetFact`, from the "Saved automatically" list (§19) and, since 2026-09-25, from "Used in this answer" and "Jarvis remembered N things" (§4, §19.5), after a confirm, held on a stale link | Retires rather than deletes. No undo. Refused by the desktop while the event stream is stale, like every memory write. Since the owner's decision of 2026-09-24 (automatic learning, §19) the phone calls it too, for automatically saved facts - one fact per request, held on a stale link, like the desktop. Rewording (`/api/memory/edit`) stays desktop-only. |
| `/api/memory/erase` | POST | `{"id": <int>}` and nothing else | `brain.rs` `brain_memory_erase` (Saved automatically, and every fact in What Jarvis knows about you - forgotten ones too; since 2026-09-25 also beside Forget under the quickbar's "Used in this answer" and the Brain's "Jarvis remembered N things"), after a confirm, held on a stale link | `JarvisApi.eraseFact` / `JarvisRuntime.eraseAutoFact` (Brain, Saved automatically), after a confirm, held on a stale link | **"Erase the words"** (the owner's decision, 2026-09-24; `memory-erase.patch`, `rebuilt/jarvis_memory.py` `erase()`). Wipes ONE fact's words for good and keeps its row and dates: `text` becomes `[erased]`, `erased_at` is set, the word-search row and meaning vector are deleted, meta keeps only dates, ids and where it came from (no message hash, no conversation id), a current fact is retired as Forget retires it, and copies of the words in the review queue go too (a card still waiting with exactly those words, or a "retire this?" card about the fact, is turned down). Then the file is cleaned: the word index compacted, freed space zeroed, `memory.db-wal` emptied. Works on an already-forgotten fact. Same token and origin checks as forget and, like forget, **no approval card** - both apps ask first ("Erase the words of this fact from your PC for good? Jarvis keeps only the date it was saved, so its history shows something was erased here. This cannot be undone.") and say "Erased.". **The earlier wordings go too** (security audit L3, 2026-09-25): every fact this one replaced - an edit (`/api/memory/edit`) or a correction - and every fact THOSE replaced is erased the same way; never a later one. `200 {"ok": true, "id", "erased_at", "already_erased", "retired_now", "file_clean", "copies", "earlier", "note"}` (`earlier`: the ids of the earlier wordings erased with it, newest first) - **never the words** (forget's reply has a `was`; this has not). `file_clean: false`: something was reading the file, so an old copy may stay in `memory.db-wal` until the next erase. `400` for anything but one integer `id` (a list, a string, `true`, an extra key); `404 {"ok": false, "reason": "no_such_fact"}` - an app tells this apart from a PC without the route (a plain 404, or `501` from an older `jarvis_memory.py`), where nothing was erased; `503` memory not running. **No event** - forget sends none either, so the other app's list shows the change on its next read. |
| `/api/memory/profile` | POST | `{"id": <int>, "pinned": true \| false}` and nothing else | `brain/profile.rs` `brain_memory_pin` (Pin / Unpin on every current fact in Saved automatically and What Jarvis knows about you, and Unpin in Always keep in mind), held on a stale link | `JarvisApi.pinFact` / `JarvisRuntime.pinFact` (Pin / Unpin in Brain, Saved automatically; Unpin in Always keep in mind), held on a stale link | **"Always keep in mind"** - pin or unpin ONE fact (the owner's decision, 2026-09-24). Only the id is stored (a `profile(fact_id, added, how)` table in memory.db); the words stay the fact's own, never summarised or rewritten. **No approval card and no confirm**: it is the owner's own tap on a fact they can see, like Forget, and Unpin takes it back. Pinning a sensitive fact is allowed - only the owner's tap can put one there. Same token and origin checks as forget. `200 {"ok": true, "id", "pinned", "changed", "chars", "limit", "note"}` (pinning a pinned fact, or unpinning one that is not, is `changed: false`); **`409`** `{"ok": false, "reason", "error", "chars", "limit"}` with `reason` `"too_long"` ("That would make the list too long - unpin something first"), `"fact_too_long"` (one fact over 1,200 characters on its own) or `"not_current"` (forgotten or erased) - both apps show `error` word for word; `404 {"ok": false, "reason": "no_such_fact"}` (told apart from a PC without the route, as for erase); `400` for anything but one integer `id` and one boolean `pinned`; `501` older `jarvis_memory.py`; `503` memory not running. The reply never has the words. Audit log: `memory.pinned` / `memory.unpinned` with the id only. **No event** - forget and erase send none either; each app reads the list again after its own memory writes and when Memory / Brain is shown. |
| `/api/memory/edit` | POST | object | `brain.rs` `brain_memory_edit` | **no** | Refused while the stream is stale. Rewording supersedes (a new fact, the old one retired), so a pinned fact that is reworded leaves "Always keep in mind" - pin the new wording. |
| `/api/memory/learning` | POST | `{"enabled": bool}` | `brain.rs` `brain_memory_learning` | `JarvisApi.setLearning` (Brain, "What Jarvis remembers") | **ON asks first** (`learning-asks.patch`, `jarvis_learning_switch.py`, 2026-09-24): **202** `{"ok": true, "waiting": true, "enabled": false, "message"}` while one approval card under the action `learning_enable` waits; it turns on (and starts the learner) only when that card is approved. A second ON while one waits: 202, no second card. A toml tier other than `ask`: **503**. **OFF**: 200 at once, never a card, and it withdraws a waiting ON. Both apps hold ON (not OFF) while the stream is stale, and say "waiting" until the card leaves the queue. A "Remember:" message makes a card even while learning is off. |
| `/api/memory/learning/auto` | POST | `{"enabled": bool}` | `brain_memory_learning_auto` (ON held on a stale link) | `JarvisApi.setAutoLearn` (the same hold) | `auto-learn.patch` - **§19**. "Learn automatically" (on by default). The shape of `/api/memory/learning`: **OFF** 200 at once, never a card, withdraws a waiting ON; **ON** 202 `{"waiting": true, ...}` and ONE approval card, action `learning_auto_enable`; on only when it is approved. Already on: 200, no card. A second ON while one waits: 202, no second card. Tier other than `ask`: **503**. Bad body: `400`. Every reply carries the `GET /api/memory/learning` fields (not `enabled`). |
| `/api/memory/learning/sensitive` | POST | `{"enabled": bool}` | `brain_memory_learning_sensitive` (ON held on a stale link) | `JarvisApi.setAutoLearn` (the same hold) | `auto-learn.patch` - **§19**. "Also remember sensitive topics automatically" (off by default). The same shape, action `learning_sensitive_enable`. |
| `/api/history/settings` | POST | `{"enabled": bool}` or `{"keep_days": 0 \| 30 \| 90 \| 365}` (one per request) | `brain_history_settings` (ON and every keep change held on a stale link) | `JarvisApi.setHistory` / `setHistoryKeepDays` (the same holds) | `chat-history.patch`, `jarvis_chat_log.py`, 2026-09-24 - **§18**. The same shape as `/api/memory/learning`: **ON asks first** - **202** `{"waiting": true, ...}` and ONE approval card under the action `history_enable`; on only when it is approved. ON while already on: 200, no card. A second ON while one waits: 202, no second card. A toml tier other than `ask`: **503**. **OFF**: 200 at once, never a card, withdraws a waiting ON; what is kept stays. `keep_days`: 200 at once, the reply says how many conversations it deleted. Anything else: `400`. Every reply carries the `/api/history` status fields. |
| `/api/history/delete` | POST | `{"id": "<conversation id>"}` | `brain_history_delete`, after a confirm; held on a stale link | `JarvisRuntime.deleteHistory`, after a confirm; held on a stale link | `chat-history.patch` - **§18**. One conversation per request, `200 {"ok": true}` or `404`. **There is no delete-all** - a list, or any other key, is `400`. |
| `/api/memory/sleep_time` | POST | `{"enabled": bool}` and/or `{"remind": bool}`, or `{"not_now": true}` alone | `brain.rs` `brain_memory_sleep_time` | `JarvisApi.setSleepTime` | The overnight tidy is **not built**: `enabled` only records the wish, and nothing runs. "Not now" sends `{"not_now": true}` since 2026-09-25 (`briefing.patch`): the PC keeps the offer quiet for 1 day, then 7, then 30 (`jarvis_backoff.py`, section 22.6), and answers `{"ok", "said", "quiet_until"}`; it changes no setting and is not held on a stale link in either app (it only makes Jarvis quieter). An older PC answers 400 and the card simply returns tomorrow. `not_now` beside `enabled` or `remind` is ignored. |
| `/api/attention/mute` | POST | `{}` | `attention.rs:119` | `JarvisApi.kt:469` | **Until tomorrow only.** There is no "mute forever". |
| `/api/attention/unmute` | POST | `{}` | `attention.rs:121` | `JarvisApi.kt:471` | Response is `budget()`, not `status()`, so the desktop re-reads rather than applying half an update. |
| `/api/digest/seen` | POST | `{}` = all, or `{"ids": [...]}` | `attention.rs:102` | `JarvisApi.kt:481` | **Marking read is not approving.** Both clients say so in the same words. |
| `/api/shutdown` | POST | `{}` | `sidecar.rs:636` | **no** | Unloads the model from the GPU. Desktop-only, and failure is not fatal — the grace period exists because this may not work. |

---

## 7. Where the two clients disagree

These are differences I verified by reading both call sites. I have no way to
know which side the backend agrees with.

1. **`/api/chat` body — settled.** Both send
   `{"messages": [...], "has_image", "stream", "auto"}` with the conversation
   so far; see §4. (This item used to say the phone sent `{"message": ...}`,
   and that it could not read an SSE-framed reply. Both are out of date: the
   phone reads both framings through `net/ChatChunkParser.kt`, as the
   desktop does - `API-DISAGREEMENTS.md` §4.)

2. **Approve/deny attribution.** Desktop sends `"by": "desktop_spotlight"`
   (`commands.rs:914-916`); Android sends only `{"id": …}` (`JarvisApi.kt:395`).
   If the server records `by`, phone decisions are attributed to nothing. If it
   ignores `by`, the desktop is sending a field nobody reads.

3. **`/api/appearance` — the clients used to contradict each other about
   whether it exists.** *Resolved on the desktop side:* `appearance.rs` now
   says "The route exists once `appearance.patch` is applied", and since
   2026-09-23 the desktop also handles the `appearance` event. *And on the
   phone:* it only synced when `/api/version` listed an `appearance`
   capability, which no backend sent; the rebuilt `jarvis_events.hello()`
   now does, and the phone also tries the route once and treats a 404 as
   "not here". What follows is the history. `appearance.rs:17-24` used to say, under a heading reading *"The route
   does not exist yet"*, that the backend "answers neither", and fell back to
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

5. **Voice control routes were phone-only.** Until 2026-09-23 the desktop
   posted `utterance` and `say` and nothing else. Now its "hey Jarvis" button
   (`voice.rs` `ensure_wake_ready`) reads `/api/voice/status` and, when the
   wake word is off, posts `/api/voice/wake {"enabled": true}` - which raises
   the approval card, the same as the phone's button.

6. **`/api/visual-spec` is desktop-only.** `spec_drift.rs` fetches it and
   compares structurally; the phone's `SpecDriftTest` compares Kotlin constants
   against its own bundled copy, so it is structurally incapable of noticing
   the desktop's copy drifting. `docs/CROSS-CLIENT-CONTRACT.md` §3 asks whether
   the served spec should replace both vendored copies.

7. **Event kinds each client ignores.** The phone ignores `finding` and
   `voice`, and does not handle `job` at all; both re-read the review queue
   on `proposal`; the desktop fans the rest out verbatim. Deliberate on the phone's side
   (see the reasoning at `JarvisRuntime.kt:683-705`), but worth knowing before
   assuming a feature works on both.

---

## 8. Draft, proposed, or not actually wired

Nothing in this section is confirmed to exist. Treat every name here as a
guess someone wrote down honestly.

| Route | Status |
|---|---|
| `/api/pending/<id>/amend`, `/api/task/pause`, `/api/task/resume`, `/api/task/stop`, `/api/task/note` | **No longer draft** — served by `backend/task-control.patch` under exactly these names (2026-09-23). See §11. A 404 now means the patch is not applied on that backend. |
| `/api/appearance` | Proposed in `docs/APPEARANCE-API.md`; **implemented in `backend/appearance.patch`**, which may or may not be applied on the owner's machine. See §7.3. |
| `/api/visual-spec` | Real and correct per `docs/CROSS-CLIENT-CONTRACT-REPLY-2.md`, but only the desktop fetches it. |
| `GET /api/holds` | **Does not exist and was deliberately not invented.** `JarvisApi.kt:455-464` records that an earlier draft made it up to fill the gap, and that doing so "is the exact mistake that produced `jarvis-android`'s protocol". Removed rather than kept behind a 404. |
| `/api/approvals` | **Does not exist.** Named once by mistake; `backend/extraction-wiring.patch:342-345` records the correction. The queue is `/api/pending`. |
| A decide-with-option route | Needed for approvals carrying two or more options (`ApiModels.kt:294-302`). No name proposed. |
| `POST /api/note` | Suggested, not proposed (`API-DISAGREEMENTS.md` §10). **Superseded** by `POST /api/notes/capture` (§11), which does let a client truthfully report whether a note was filed. |

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
- **No public tunnel, ever.** Everything here is loopback, Tailscale or NordVPN Meshnet (both private device-to-device networks, never a public tunnel).

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

---

<!-- ===== task controls, notes, power (2026-09-23) - begin ===== -->

## 11. Task controls, notes and power (added 2026-09-23)

Written from the backend code that serves them (`backend/jarvis_task_control.py`
and `backend/task-control.patch`), not from the clients. Every route below
checks the origin and the token like every other private route.

### Task controls — `backend/task-control.patch`

| Route | Body | Answers | What it does |
|---|---|---|---|
| `POST /api/task/stop` | `{}` | 200 `{"ok", "stopping": [ids], "forgot_paused": id\|null, "message"}`; **409** nothing running or paused | Stops the running multi-step task before its next step, and forgets a paused one. No approval card. |
| `POST /api/task/pause` | `{}` | 200 `{"ok", "pausing": [ids], "message"}`; **409** nothing running / already paused | Stops before the next step and keeps the steps not run. No card. `activity` becomes `"paused"` only once the run has really stopped. |
| `POST /api/task/resume` | `{}` | **202** `{"ok", "task", "asking": true, "message"}`; **409** nothing paused / a resume card already waiting | **Runs nothing.** Raises ONE approval card (same action, so the same tier, as the original task) listing every remaining step via the module's own `describe()`. Runs those steps only on an allowed verdict. |
| `POST /api/task/note` | `{"note": "…"}` (≤ 1000 chars kept) | 200; **400** empty; **409** nothing to attach to | Kept with the running (else paused) task. Given to the model when the current step finishes; shown on a resume card. Changes no step. |
| `POST /api/pending/<id>/amend` | `{"note": "…"}` (≤ 1000 chars kept) | 200 `{"ok", "id", "kept": true, "message"}`; **400** empty; **409** card no longer waiting; **503** queue unreadable | Kept with that one card, which does not change. Given to the model with the owner's answer, approve or deny. |
| `GET /api/task` | — | `{"available", "running", "paused", "last_resumed", "recent"}` | Ids, tool names and step counts. Never a note's text. |

`activity: "paused"` (with `activity_detail` like "Paused with 2 steps not
run…") is reported from the moment a run stops at a pause until it is
resumed, stopped, or an hour old. Clients must keep showing Resume only on
that report, never on their own click.

Stale link (rule 4): both clients hold **Resume** on a stale stream and let
Stop, Pause and notes through.

App lock (the owner's decision of 2026-09-26): with App lock on, the
desktop's widget - which sits outside the lock - offers neither note, and
`inject_task_note` / `amend_approval` refuse the widget in Rust ("App lock
is on, so notes to Jarvis are added in the Jarvis bar, not the widget. Open
the Jarvis bar and confirm it is you to add one"). The phone's notes are
inside the app, which is behind App lock already.

### Notes — `backend/note-capture.patch`

| Route | Body | Answers | What it does |
|---|---|---|---|
| `POST /api/notes/capture` | `{"target": "logseq"\|"joplin"\|"obsidian", "text": "…", "title"?: "…", "notebook"?: "…"}` | **200** job, finished; **202** job, `state: "waiting"` (an approval card is up); **400** empty / unknown target, or a body that is not a JSON object (`{"ok": false, "state": "not_filed", "error", "message"}`); **503** not set up (no graph folder, no token, no vault, a daily-note format it cannot follow — `message` says which, starting "X isn't set up on your PC" when it is the setup); **429** four notes already waiting (`state: "not_filed"`, with `error` and a `message` saying why) | Files the owner's own words. No model. Written through `jarvis_gate` as `append_logseq_journal` / `create_joplin_note` / `append_obsidian_daily`, under the owner's own tier for those in `jarvis-framework.toml`. |
| `GET /api/notes/capture?id=…` | — | 200/202 job; 404 unknown id | How that note ended. |
| `GET /api/notes/capture` (no id) | — | **200** `{"ok": true, "targets": ["logseq", "joplin", "obsidian"]}` — only those set up on the PC, names only; a backend from before 2026-09-24 answers **404** (its "unknown id") | Which note apps to show. Both apps show only these, and show none (saying why) when this cannot be read. |

A job is `{"id", "state", "target", "message", "created", "updated", "ok"}`
with `state` one of `waiting`, `filed` (written and read back), `not_filed`
(denied / timed out / refused — `message` says which) or `failed`. **It never
carries the note's text.** Clients show `message` and nothing of their own.

Replaces what `POST /api/note` in §8 suggested. The desktop's `#log` / `#obs` /
`#joplin` / quick note / widget capture use it (`capture_note`,
`capture_note_status`); the chat turn with a routing system message is gone.
The phone uses it too: Home's "Quick note…" field, opened directly or by the
home-screen widget's Note button (`JarvisApi.captureNote`, `noteStatus`,
`JarvisRuntime.fileNote`). The phone keeps asking while a card waits and
shows the desktop's own sentence in its notice.

A note Jarvis writes from chat (the `append_*` / `create_joplin_note`
tools) is a different path: after outside text in that turn it always
waits for a yes, as `write_notes_after_outside_text` (§4, "Tool calls and
outside text"). This route is not affected.

### Power — `backend/power-mode.patch`

| Route | Body | Answers | What it does |
|---|---|---|---|
| `POST /api/power` | `{"mode": "active"\|"quiet"\|"standby"}` | 200 `{"ok", "mode", "changed", "message", "unloaded"?, "still_loaded"?, "also"?, "note"?, "warm_up"?}`; **202** `{"waiting": true, ...}` while a card is up (only if the owner set `power_manage` to ask); **400** unknown mode; **409** standby while a task runs, or while another power card waits; **503** no power module | Through `jarvis_gate` as `power_manage` (`auto` in the shipped toml). Standby also unloads the resident model, and (2026-09-24) stops the second card's Ollama and the big model when they run: `also` is one sentence per engine that had something to say, and each sentence is appended to `message`, so an app that shows `message` shows them. The second card then stays stopped - status reads do not restart it - until the owner uses a second-card feature or Jarvis leaves standby; background learning does not wake it. A big-model job already under way is left to finish. |

The mode clients show still comes from `/api/status` and the `power` event.
Desktop: tray → Change power mode (`commands::set_power_mode`). Phone: Brain
screen buttons (`JarvisRuntime.setPower`). Both hold **waking** on a stale
link and let going quieter through.

**Added 2026-09-25, with the standby schedule (§21.8):**

- **Every model, not only the one `jarvis_models` names.** After
  `jarvis_models.unload()`, standby asks the everyday Ollama itself
  (`GET /api/ps`) for every model it still holds and unloads each
  (`POST /api/generate {"model", "keep_alive": 0}`, no prompt - Ollama's
  documented unload), then reads `/api/ps` again for up to three seconds.
  `unloaded` lists what is really gone; `still_loaded` (and a sentence in
  `also` and `message`) what Ollama did not let go of. Loopback only
  (`OLLAMA_URL` must be this PC, else nothing is asked and `note` says so),
  through `jarvis_local_http` (no proxy); only model names are sent.
- **Warm-up on waking.** Leaving standby for `active` loads the chat
  model again at once, in the background (not for `quiet`: the apps let
  Quiet through on a stale link and hold only Active, so only Active may
  start loading a model): `jarvis_models.
  current_model()` (else `JARVIS_MODEL`), `POST /api/generate {"model"}`
  with no prompt and no `keep_alive` (Ollama's own setting decides - `-1`
  on the owner's PC). `warm_up` names the model and `message` says it is
  loading. Never a cloud model (`:cloud`, `-cloud`) and never another
  machine's Ollama - the chat path's two checks (ARCHITECTURE §4). If
  Jarvis is back on standby when the load finishes, the model is unloaded
  again.
- **The answer comes when the mode has changed.** Freeing the cards can
  take seconds; an answer that waited for it past `wait_s` (1.5 s) used to
  be the 202 "Waiting for your approval" with no card up. Now, once the
  gate has allowed it and the mode has changed, a slow unload answers 200
  `changed: true` with "Freeing the graphics card now." and carries on
  behind it (the audit log gets `power.standby`).
- **`why`.** A change the standby schedule makes is recorded by
  `jarvis_power` as `"the standby schedule"`, not `"the owner, from ..."`,
  so the desktop's tray says "Power: standby · standby schedule" rather than
  "set by hand" (`stream.rs power_set_by` -> `"standby_schedule"`). Since
  the owner's decision of 2026-09-25 the schedule also READS it: at the end
  of its hours it wakes Jarvis only when `jarvis_power.status()["why"]` is
  still `"the standby schedule"` (§21.8). `jarvis_power` changes `why` on a
  change of mode and on nothing else, so a Standby chosen by hand, before
  or during the hours, stays; and a tap on Standby while already on standby
  (`"Already standby."`) records nothing.

<!-- ===== task controls, notes, power (2026-09-23) - end ===== -->

---

## 12. The second graphics card (added 2026-09-24)

`backend/second-card.patch` and `backend/jarvis_second_card.py`. The owner's
guide is `docs/SECOND-CARD.md`. **Both apps call both** (2026-09-24). The
phone: Brain screen, "Second graphics card" (`SecondCardPlate.kt` /
`net/SecondCard.kt`), and chat's photo button. The desktop: Settings, "Second
graphics card" (`get_second_card` / `set_second_card` in `commands.rs`,
granted to the settings window only), and `vision.rs`, which reads it before
deciding whether pictures can be sent. `tools/check_parity.py` records
`/api/second-card` as `ported`.

| Route | Body | Answers | Notes |
|---|---|---|---|
| `GET /api/second-card` | - | 200 `status()` (below); 503 `{"available": false, "error"}` if `jarvis_second_card.py` is missing | Token + origin. Card names and hardware ids (`GPU-...`); never a token. Re-read it after a card is decided - there is no event for it. |
| `POST /api/second-card` | `{"feature": "master" \| "<feature id>", "enabled": true \| false}` | 200 `{"ok": true, "pending": true, "enabled": false, "message"}` - a card is up, nothing is on yet; 200 `{"ok": true, "enabled": false, "pending": false, "message"}` - off; 200 `{"ok": true, "enabled": true, "pending": false, "message"}` - already on; **409** a card for that switch already waits, or (2026-09-24) "Not now: the big model is using the ...; it stops after N idle minutes" - an ON that would start the second Ollama while the big model holds that card; **400** unknown feature, `enabled` not a boolean, the main switch off, or a needed feature off; **503** no capable second card (the sentence says why), or the switch's action is not tier `ask` (`second_card_enable`, or `second_card_browser_enable` for Browser control) | ON is one approval card: action `second_card_enable`, except Browser control, which has its own action `second_card_browser_enable` because it lets Jarvis work pages on the internet. OFF is immediate. Show `error` word for word. |

**`status()`** - the real output of each case is in
`jarvis-desktop/tests/fixtures/second-card-cases.json` (`one_card`,
`capable_off`, `capable_pending`, `running_long_context`,
`card_missing_but_enabled`, `not_capable_old_card`). Build against that file,
not this summary.

```
{"detected": {"capable": bool, "why": str,
              "primary": {"uuid", "index", "name"} | null,
              "second": {"uuid", "index", "name", "total_mb", "compute_cap"} | null,
              "cards": [{"index", "uuid", "name", "total_mb", "free_mb", "compute_cap",
                         "display_active", "role": "primary"|"second"|"unused", "why"}]},
 "enabled": bool,            the main switch
 "active": bool,             main switch on AND a capable card seen
 "pending": [ids],           switches with a card waiting ("master" included)
 "lane": {"state": "off"|"starting"|"running"|"failed", "why": str},
 "main_ollama_pinned": true|false|null, "pin_note": str, "pin_command": str|null,
 "features": [{"id", "name", "what", "enabled", "active", "available", "needs": [ids],
               "model", "model_installed": bool|null, "memory_gib": float|null, "why"}],
 "last": {"feature", "outcome", "why", "at"} | null}
```

`last` (2026-09-24) is how the most recent approval card for any of these
switches ended: `outcome` is one of `enabled`, `denied`, `timed_out`,
`refused`, `failed`, `withdrawn`; `why` is a sentence to show as it is (for
example "You said no, so "Pictures" stays off."); `at` is Unix seconds.
`null` when no card has ended since Jarvis started. The phone shows `why` as
a line under that switch while it is off and not waiting
(`SecondCard.lastLine`); the desktop uses it to say how a card it was
waiting on ended (`settings.js` `cardLast`).

Feature ids, in display order: `long_context`, `vision`, `learning`,
`browser_control` (needs `long_context`), `wiki`. `enabled` is the owner's
switch; `active` is that switch with the main switch, its needs and a capable
card; `available` is active and actually working (second Ollama running,
model installed). Show `why` as the line under each switch - it always says,
in words, what is missing. A switch whose card has gone stays `enabled` with
`active: false`: show it as on-but-waiting, never flip it off.

`pin_command` is one PowerShell line (Windows PowerShell 5.1-safe) that keeps
the owner's everyday Ollama on the main card; show it with a copy button and
`pin_note` above it, on the desktop. The phone shows `pin_note` only (the
command is run on the PC).

**Pictures: what the apps must change.** The desktop's
`vision.rs::local_model_vision` asks `/api/models` for `current` and then
asks Ollama's `/api/show` about that model. With the second card's Pictures
switch working, the picture does NOT go to `current` - it goes to
`qwen2.5vl:7b` on the second card - so that check keeps answering "cannot
see pictures". The backend cannot make it say yes without lying about
`current`. So, before that check, read `GET /api/second-card` and find the
`vision` row: if `available` is true, the answer is "yes" (reason: "Pictures
go to <model> on the second graphics card."); otherwise do what it does
today. The phone does the same wherever it decides whether to send a
picture. The route header then carries `second_card: "vision"` on that turn.

**The phone's picture** (2026-09-24): a Photo button in chat, shown only
while the `vision` row's `available` is true, and checked again (a fresh
`GET`) before the send. Android's photo picker, no storage permission; the
photo is shrunk in memory to 1920 pixels on its long side at JPEG quality 82
(the desktop's `MAX_CAPTURE_WIDTH` and `JPEG_QUALITY`), then lower quality or
smaller until it is at most 1.5 MB, which stays well inside `MAX_BODY` (4 MiB)
after base64. The request is the desktop's, byte for byte in shape: the text
and an `image_url` part (`data:image/jpeg;base64,...`) in the newest user
message, `has_image: true`. `backend/test_phone_second_card_contract.py`
checks that shape against `newest_turn_has_image`, `choose_lane` and the
router, and the phone's `ChatPictureContractTest` builds the same bodies with
its own encoder. Under the answer the phone says "Answered on the second
graphics card (<model>)" when `second_card` is in the route header.

---

## 13. The wiki builder (added 2026-09-24)

`backend/wiki.patch` and `backend/jarvis_wiki.py`; the owner's guide is
`docs/SECOND-CARD.md`, "Wiki builder". Both apps call these routes: the
desktop from the Brain's Memory tab (`src/wiki.js`, the `wiki_*` commands in
`commands.rs`), the phone from Brain (`net/Wiki.kt`, `WikiPlate.kt`).
`tools/check_parity.py` records both as `ported`.

| Route | Body | Answers | Notes |
|---|---|---|---|
| `GET /api/wiki` | - | 200 `status()` (below); 503 `{"available": false, "error"}` if `jarvis_wiki.py` is missing | Token + origin. Names, states and reasons; never a page's text. `folder` is the absolute path of `Jarvis Wiki` on the PC (the desktop uses it to open the folder; the phone ignores it). |
| `POST /api/wiki/ingest` | `{"source": "<file name in Sources>"}` | **202** `{"ok": true, "id", "pending": true, "state": "reading", "message"}` - the model is reading it; the card comes after; **400** not a plain name, too big, or not readable; **409** already in the wiki and unchanged, or another document is being added; **503** the second card's wiki lane is not ready, or no vault / `Jarvis Wiki` folder. Every refusal is `{"ok": false, "state": "refused", "error": "<a sentence>"}` | ONE approval card, action `wiki_update` (tier `ask` as shipped), raised after the model has read the document. Nothing is written before it is answered. Show `error` word for word. Hold it on a stale link (rule 4). |
| `GET /api/wiki/ingest?id=` | - | 200 the job: `{"id", "source", "state", "message", "ok", "pending", "created", "updated", "pages"?, "outcome"?}`; 404 unknown id (a restart forgets jobs); 400 no id | `state` is `reading`, `waiting` (the card is up), `writing`, `done`, `refused` or `failed`. Say "added" only on `done`. `message` is the sentence to show. `pages` is `[{"action": "create"\|"update", "path", "summary", "chars"}]` once planned. |

**`status()`** - the real output is in
`jarvis-desktop/tests/fixtures/wiki-cases.json` (`status_ready`,
`status_off`, `status_no_wiki_folder`, `status_running`, then each POST
answer and each job state). Build against that file, not this summary.

```
{"available": bool,          lane_for("wiki") returned a lane
 "why": str,                 "Ready: ..." or, when not, the second card's own reason
 "vault_folder_ok": bool, "folder_why": str, "folder": str | null,
 "sources": [{"name", "state": "new"|"changed"|"in_wiki"|"too_big"|"unreadable", "why"}],
 "recent": ["## [YYYY-MM-DD] ingest | <source>", ...],   the last five
 "pages": int, "running": {"id", "source", "state"} | null, "reads": [".md", ".txt"]}
```

Offer "Add to wiki" only for `new` and `changed`, only when `available` and
`vault_folder_ok` are true and `running` is null. Show every other state
with its `why`. There is no event for the wiki; ask the job route until the
state is final, then read `GET /api/wiki` again.


---

## 14. The big model, slow (added 2026-09-24)

`backend/big-model.patch` and `backend/jarvis_big_model.py`; the owner's
guide is `docs/BIG-MODEL.md`. A very large model run by colibri on the PC,
for two background jobs only: the wiki builder and deep questions. Never
chat, voice or approvals. **Both apps call all three** (2026-09-24). The
desktop: Settings, "Big model (slow)" (`get_big_model` / `set_big_model` in
`commands.rs`, granted to the settings window only), and the Brain's Memory
tab, "Deep questions" (`get_deep` / `ask_deep`, the `brain-deep` set, Brain
window only; `src/deep.js`). The phone: Brain screen, "Big model (slow)" and
"Deep questions" (`BigModelPlate.kt` / `net/BigModel.kt`).
`tools/check_parity.py` records all three as `ported`.

| Route | Body | Answers | Notes |
|---|---|---|---|
| `GET /api/big-model` | - | 200 `status()` (below); 503 `{"available": false, "error"}` if `jarvis_big_model.py` is missing | Token + origin. Folder paths, memory and disk numbers; never the key colibri is started with. Does not start colibri. |
| `POST /api/big-model` | `{"switch": "master" \| "wiki" \| "deep_questions", "enabled": true \| false}` | 200 `{"ok": true, "pending": true, "enabled": false, "message"}` - a card is up, nothing is on yet; 200 `{"ok": true, "enabled": false, "pending": false, "message"}` - off; 200 `{"ok": true, "enabled": true, "pending": false, "message"}` - already on; **409** a card for that switch already waits; **400** unknown switch, `enabled` not a boolean, or a job before the main switch; **503** not possible (colibri or Python not found, no usable model, not enough memory in total, a nearly full drive - the sentence says which), or `big_model_enable` is not tier `ask` | ON is one approval card (action `big_model_enable`). OFF is immediate and stops colibri if nothing else needs it. Show `error` word for word. |
| `GET /api/deep` | - | 200 `deep_status()` (below) | Token + origin. The owner's own questions and answers; reads only, starts nothing. **Hidden with the private lists** (2026-09-26): while "Hide memory lists and chat history" hides them, the desktop's Rust takes every `question` and `answer` out (`redact_deep`: `"hidden": true`, rows keep their state and times) and the phone shows the plate as hidden with its Show button, like the wiki. |
| `POST /api/deep/ask` | `{"question": "<at most 4,000 characters>"}` | **202** `{"ok": true, "id", "pending": true, "state": "queued", "message"}`; **400** empty, not text or too long; **409** three questions already waiting or running; **503** not available (the switch is off, the model cannot be used, or not enough memory is free right now). Every refusal is `{"ok": false, "state": "refused", "error": "<a sentence>"}` | No approval card per question: the switch was approved, and a question acts on nothing (no tools, no memory writes, no web) and nothing leaves the PC. Hold it on a stale link anyway (rule 4). |

**`status()`** - the real output of each case is in
`jarvis-desktop/tests/fixtures/big-model-cases.json` (the phone has the same
file in its test resources). Build against that file, not this summary.

```
{"detected": {"capable": bool, "why": str,
              "colibri": {"found", "dir", "why"}, "python": {"found", "why"},
              "ram": {"total_gb", "available_gb"},
              "models": [{"id", "name", "kind": "medium"|"giant", "dir", "drive",
                          "drive_type": "NVMe"|"SATA SSD"|"SATA HDD"|"SATA"|"USB"|"SSD"|"HDD"|"unknown",
                          "free_gb", "need_gb", "found", "usable", "can_start_now",
                          "why", "note": str|null}]},
 "enabled": bool,            the main switch
 "active": bool,             main switch on AND capable
 "pending": [ids],           switches with a card waiting ("master" included)
 "engine": {"state": "off"|"loading"|"ready"|"failed", "why", "model": id|null,
            "listens_on": "127.0.0.1:8765", "idle_minutes", "since": epoch|null, "busy": bool},
 "cuda": {"setting": "off"|"on", "usable": bool, "why"},
 "key_kept": "not-made-yet"|"credential-manager"|"this-run-only", "key_where": str,
 "switches": [{"id": "wiki"|"deep_questions", "name", "what", "enabled", "available",
               "model", "model_name", "why"}],
 "measured": {"wiki": M|null, "deep_questions": M|null},
 "verified": false, "unverified": str,
 "last": {"feature", "outcome", "why", "at"} | null}
M = {"model", "seconds", "tokens", "tokens_per_s", "words", "words_per_s", "at"}
```

`last` is the same as in `GET /api/second-card`: how the most recent card
for one of these switches ended (`feature` is `master`, `wiki` or
`deep_questions`), or `null`. `words` and `words_per_s` count every word
the model wrote, its reasoning (`<think>`) included.

Show `why` under each switch and each model; `note` (for example "a giant
model on a SATA drive") as a warning line; `unverified` somewhere near the
speed, always. `available` on a switch means it can run now or as soon as a
job asks (colibri starts on demand); it is false when not enough memory is
free right now or the last start failed, and `why` says which. `engine.state` `loading` can last minutes.
A switch whose model has gone stays `enabled`: show it as on-but-waiting.

**`deep_status()`**:

```
{"available": bool, "why": str, "enabled": bool, "model": id|null,
 "jobs": [{"id", "question", "state": "queued"|"loading"|"thinking"|"done"|"failed",
           "queued", "started", "finished", "seconds", "tokens",
           "words_per_s", "tokens_per_s", "model", "why", "answer"?}],   newest first, at most 20
 "limits": {"question_chars": 4000, "queue": 3, "answer_tokens": int}}
```

`answer` is there only when `state` is `done`. `why` is the sentence to show
under each job (on `done` it says the speed; on `failed`, what went wrong).
An answer cut off while the model was still reasoning (a `<think>` with no
`</think>`) is `failed`, and nothing is kept. An answer cut off at the length
limit after the reasoning closed is `done`, and `why` says it may end
mid-sentence. While the big model is on another job, a question stays
`loading` and `why` says it is waiting for that job.
Times are Unix seconds. The questions and answers are kept **in memory
only**, until the backend stops (security audit L2, 2026-09-25): they used
to be written to `<config dir>/deep-questions.jsonl` in plain text, outside
chat history's switch and encryption. After a restart the list is empty. An
older `deep-questions.jsonl` is no longer read or written.

**The event.** When a deep question finishes, the event stream carries kind
`deep` with `{"id", "state": "done"|"failed"}` - a doorbell, never the
question or the answer. On it, read `GET /api/deep`. Both apps do. The
desktop: `brain.js`'s `onEvent` (`stream.rs` fans the frame out to every
window and reads nothing for it), and a poll every 15 s only while a job is
`queued`, `loading` or `thinking`, in case the event is missed. The phone:
`JarvisRuntime.onEvent` re-reads `GET /api/deep`, and `GET /api/big-model`
for the measured speed, and polls every 20 s only while a job is going and
its plate is on screen. There is no event for the switches: read `GET
/api/big-model` again after a card is decided (both apps do).

**The wiki.** With the big model's `wiki` switch on, `GET /api/wiki`'s
`why` names the big model, and `POST /api/wiki/ingest` may answer 202 while
colibri is still loading: the job's `state` stays `reading` and its
`message` says it is waiting for the big model. Nothing else about the wiki
routes changes.

## 15. Custom voices (added 2026-09-24)

`backend/voices.patch` and `backend/jarvis_voices.py` (with
`backend/jarvis_f5_worker.py` for the better voice). Jarvis can speak in a
voice the owner recorded: 3 to 10 seconds of someone reading a sentence
Jarvis shows (so the words are exact), or an uploaded clip with its words
typed in. **Both apps call all five** (desktop Settings -> Jarvis's voice,
`voice_training.rs`; phone Checks -> Jarvis's voice, `VoicesScreen.kt`) -
`ported` in `tools/check_parity.py`. How it works,
and the owner's install lines, are in `backend/README.md`, "Custom voices".

Two engines make the voice, and the built-in Kokoro voice is always the
fallback:

- **ZipVoice** (sherpa-onnx) on the PC's **processor**. Always tried first.
- **F5-TTS**, "the better voice", on the **second graphics card**, in its
  own program, behind its own switch (off by default; ON is a card). Started
  only when Jarvis speaks in a custom voice, stopped after idle minutes, in
  standby and when switched off. While it loads, ZipVoice speaks in the same
  voice.

**Where the audio goes: nowhere.** The recording is held in the PC's memory
until the card is answered; approved, it is kept in
`<config dir>/voices/<id>/` (`clip.wav` - mono, 24 kHz, 16-bit -
`transcript.txt`, `voice.json`); anything else, it is dropped. The PC makes
no network call for any of this. The clip, its words and the text Jarvis
says are never logged, never in an audit line, never in an event.

**The owner's own voice is refused.** A recording that scores at or above
any trained voice print's threshold minus 0.10 (`[voice]
custom_voice_margin`) is refused, with the reason: Jarvis speaking in the
owner's voice through the speakers could pass its own "is it the owner?"
check. Checked on create, on switch, and again before the first word after
any voice print changes.

All routes: token + origin, like every other write. A client sends
`X-Jarvis-Client: hud` as always. **Hold on a stale link (rule 4) every
POST that raises a card** - adding a voice, switching to a custom one,
better voice ON. Deleting a voice, going back to the built-in one and
better voice OFF only take something away and always go (both apps). Show every `error` and `why` word for word: they are written for the
owner.

| Route | Body | Answers | Notes |
|---|---|---|---|
| `GET /api/voice/voices` | - | 200 `status()` (below); **503** `{"available": false, "error", "reason"}` if `jarvis_voices.py` is missing; 500 `{"available": false, "error": "<exception name>"}` | Loads no model, starts nothing. |
| `POST /api/voice/voices/create` | `{"name": "<1-40 characters>", "clip": "<base64 of one WAV>", "transcript": "<exactly what is said in it>"}` | **202** `{"ok": true, "pending": true, "voice": "<id>", "name", "seconds": 5.3, "message"}` - ONE card is up (action `custom_voice`), **nothing is saved yet**; **400** `{"ok": false, "error"}` - the clip, words or name (see limits); **409** `{"ok": false, "refused": "owner_voice", "error"}` - it sounds like the owner (no card); **409** `{"ok": false, "refused": "owner_check_failed" \| "no_voice_check", "error"}` - it could not be checked, so it is refused; **409** `{"ok": false, "pending": true, "error"}` - a voice card already waits; **409** `{"ok": false, "error"}` - that name exists, or there are already 20 voices; **409** `{"ok": false, "pending": false, "error"}` - `custom_voice` is not tier `ask` (no card); **503** module missing | The WAV: 16- or 24-bit PCM, 8-48 kHz, mono or stereo, at most 2.9 MB; 3-10 s of speech once silence at the ends is trimmed; not silent. The words must fit the length (0.5-8 words a second). Approving saves it; Jarvis does **not** start speaking in it - that is `active`, its own card. |
| `POST /api/voice/voices/active` | `{"voice": "<id>"}` or `{"voice": "builtin"}` | `builtin`: **200** `{"ok": true, "active": "builtin", "pending": false, "message"}` at once, no card (it also withdraws a waiting switch card and stops the better voice). A custom voice: **202** `{"ok": true, "pending": true, "voice": "<id>", "message"}` - ONE card (`custom_voice`); **200** `{"ok": true, "active": "<id>", "pending": false, "message"}` if already active; **404** unknown id; **409** as for create (`refused: "owner_voice"`, a card waiting, tier not `ask`, or its recording unreadable) | Nothing changes until the card is approved. |
| `POST /api/voice/voices/delete` | `{"voice": "<id>"}` | **200** `{"ok": true, "deleted": "<id>", "active": "<id>" \| "builtin"}` at once, no card; **400** for `builtin`; **404** unknown id; 500 `{"ok": false, "error"}` if the folder could not be removed | Deletes the folder. If Jarvis was speaking in it, it goes back to the built-in voice (`active` says so). |
| `POST /api/voice/voices/better` | `{"enabled": true \| false}` | `false`: **200** `{"ok": true, "enabled": false, "pending": false, "message"}` at once, and the F5 program stops. `true`: **202** `{"ok": true, "enabled": false, "pending": true, "message"}` - ONE card (`better_voice_enable`); **200** `{"ok": true, "enabled": true, "pending": false, "message"}` if already on; **409** `{"ok": false, "pending": true, "error"}` a card waits; **503** `{"ok": false, "error"}` no capable second card, or the tier is not `ask`; **400** `enabled` not a boolean | Offer the switch only when `better_voice.can_turn_on` is true. |

Errors from the route itself (not the module): **400** `{"error": "the
request is not JSON"}` or `{"error": "could not read the request
(<name>)"}`, **403** cross-origin, **401** token, **500** `{"error":
"<exception name>"}` - never the exception's message, which could quote the
request.

**`status()`**, exactly (from the code; `null` where shown):

```
{"available": true,
 "active": "builtin" | "<id>",
 "active_name": "Built-in voice" | "<name>",
 "speaking_with": "kokoro" | "zipvoice" | "f5",   what the NEXT sentence would use
 "fallback": "" | "<why the built-in voice is used instead of the chosen one>",
 "voices": [
   {"id": "builtin", "name": "Built-in voice", "builtin": true, "ready": bool, "why": str},
   {"id": "<id>", "name": str, "builtin": false, "ready": true, "why": "",
    "seconds": 5.3, "created": <unix seconds>, "transcript": str},
   {"id": "<id>", "name": "<id>", "builtin": false, "ready": false, "why": str}   a broken folder
 ],
 "engines": {"kokoro":   {"available": bool, "why": str},
             "zipvoice": {"available": bool, "why": str, "where": "this PC's processor"},
             "f5":       {"available": bool, "why": str, "where": "the second graphics card"}},
 "better_voice": {"enabled": bool,        the switch
                  "pending": bool,        its card is waiting
                  "can_turn_on": bool,    a capable second card is here
                  "why": str,             what it is, or why it cannot be turned on
                  "files": bool, "files_why": str,     F5-TTS's model files on the PC
                  "state": "off" | "loading" | "ready" | "failed",
                  "state_why": str,       show this under the switch
                  "card": str | null, "idle_minutes": 10, "load_seconds": float | null,
                  "need_mb": 3072, "need_mb_measured": false,
                  "last": {"outcome": "enabled"|"denied"|"timed_out"|"withdrawn"|"refused"|"failed",
                           "at", "why"} | null},
 "pending": {"kind": "create" | "switch", "voice": "<id>", "name": str, "expires_in": <seconds>} | null,
 "last": {"kind": "create" | "switch", "voice": "<id>",
          "outcome": "created"|"switched"|"denied"|"timed_out"|"withdrawn"|"refused"|"failed",
          "at": <unix seconds>, "why": "<a sentence to show>"} | null,
 "timings": [T, ...],           oldest first, at most 20
 "sentences": [str, ...],       sentences to show for recording; the transcript sent must be the one read
 "limits": {"min_seconds": 3.0, "max_seconds": 10.0, "max_clip_bytes": 2900000,
            "max_transcript_chars": 300, "max_name_chars": 40, "max_voices": 20}}

T = {"at": <unix seconds>, "engine": "kokoro" | "zipvoice" | "f5" | "none",
     "voice": "builtin" | "<id>", "chars": int,
     "seconds": float,          from say() being called to the sound being ready (loading included)
     "audio_seconds": float,    how long the sound lasts
     "rtf": float | null,       seconds / audio_seconds
     "fallback": str,           why the chosen custom voice was not used ("" if it was, or none was chosen)
     "note": str,               e.g. "better voice not used: loading F5-TTS ..." (it still spoke)
     "failed": str}             engine "none": why nothing was said
```

`timings` counts every `say()`, whoever asked (`/api/voice/say`, the
desktop, the phone). Never the text.

**The event.** When a card ends, a voice is deleted, the voice goes back to
the built-in one, or the better voice is switched off, the stream carries
kind `voices` with `{"what": "create" | "switch" | "delete" | "better",
"outcome": "<as in last.outcome, or builtin / deleted / off>"}` - a doorbell,
never a name or words. On it, read `GET /api/voice/voices` again.

**What an app should build** (suggested, for both): a "Voices" list with the
built-in voice and each custom one (name, length, `why` when not ready), a
radio for the active one (built-in: immediate; custom: "waiting for your
approval" until `last` says otherwise), delete per voice (immediate; confirm
on the client), "Add a voice" (record while showing one of `sentences`, or
pick a file and type its words; show the 202's message, or the 409's
`error` - the owner-voice refusal especially - word for word), the better
voice switch with `state_why` under it, and `fallback` wherever the active
voice is shown. Recording on the phone sends the clip; **the phone must not
transcribe it** (CLAUDE.md): the words come from the sentence shown or from
the owner's typing.
## 16. The stricter voice check (added 2026-09-24)

`backend/rebuilt/jarvis_voice.py`, `backend/jarvis_voice_enroll.py`,
`backend/jarvis_speech.py`, and the shipped bank
`backend/jarvis_voicebank.py`. **Both apps use it**: desktop Settings ->
Voice (`voice_training.rs`, `voice-training.js`, `voice-panel.js`), phone
Checks -> Voice check and Train my voice. **No new route and no new
patch**: everything below is on routes the apps already call
(`/api/voice/status`, `/api/voice/enroll`, `/api/voice/utterance`), so
`tools/check_parity.py` has nothing new to classify. The owner's guide and
every measured number are in `backend/README.md`, "The stricter voice
check".

**What it cannot do.** It tells your voice from other people's. It cannot
tell your voice from a recording or a copy of it: a replayed recording or
a cloned voice can pass, even at very strict. Both apps end the Very
strict description with those two sentences, word for word
(`voice-training.js` `STRICTNESS`, `StrictVoice.kt` `STRICTNESS`; pinned by
`tests/voice-training.mjs` and `VoiceStrictTest.kt`). Approvals do not rest
on the voice check (a card is always a tap), but reading memory or private
answers aloud and automatic learning from a voice turn (§19.2 item 5) do.
The fifth setting, `hands_free` (below), lets the owner trust only the
talk button for those, because the hands-free microphone is the one a
recording can reach without anyone touching a device.

**Check before you send.** An older PC reads a body it does not know as a
plain training (any body with clips in it) or answers 400. Offer each new
mode only when `gate.training` says the PC understands it:

| flag in `gate.training` | the modes it allows |
|---|---|
| `calibrate: true` | `calibrate`, `threshold` (since 2026-09-24, earlier) |
| `rounds: true` | `train` (rounds, `add`, `finish`, `cancel`) |
| `settings: true` | `strictness`, `privacy`; and `memory`, `sensitive_memory` or `hands_free` when `gate.settings` has it (an older PC answers that mode with 503) |
| `measure: true` | `measure` |

### What changed for every app, even one that changes nothing

- **No voice-ID model, no voice commands.** With only the basic check
  installed, owner mode refuses every clip: the utterance reply says
  "no voice-ID model is installed, ... install the voice-ID model";
  `listening.push_to_talk` is false with `push_to_talk_why` saying the
  same; a training (any mode that would raise a card) answers
  **409** `{"error": "<that sentence>", "pending": false, "needs_model": true}`
  before any card. Show the sentence as it is.
- **A command needs enough speech.** 2.0 s at very strict, 1.5 s at
  balanced (`gate.settings.min_command_seconds`), measured the way the
  server measures it (the VAD's span, which includes 0.3 s of quiet either
  side). A shorter clip is refused BEFORE the voice check and never
  transcribed; the reply has `too_short: true`, `min_seconds`, `threshold:
  0` and a `reason` like "that was too short to be sure it was you (1.2
  seconds of speech; a command needs at least 2.0) - say a little more".
  Show `reason`; do not show "that didn't sound like you" for it (the phone
  tells them apart by `threshold > 0` today, which still works). A
  `wake_word` clip that is only "hey Jarvis" may be short: it still opens
  the listening window (`awake: true`). A short `wake_word` clip that has a
  command in it answers `too_short: true`, `wake_heard: true`, `text: ""`.
  Only once a voice is trained - with none, the reply is "no enrolled voice
  profile", as before.
- **The one-shot training still works** (`{"clips": [...]}`, as today): it
  becomes round 1 ("close"), replacing the print, with one card.

### The utterance reply: six new fields

```
"too_short": bool, "min_seconds": float,     see above
"strictness": "very_strict" | "balanced" | ""   the setting the voice was checked at ("" = not checked)
"private_aloud": bool       may an answer that uses email, calendar, notes or memory be READ ALOUD
                            for this request? (jarvis_voice.may_speak(True, "voice"))
"question_private": bool    the words asked about something private (the router's private-topic
                            list plus notes; plus memory only while `memory_on_screen`) - a hint,
                            see below
"memory_aloud": bool        (2026-09-24) may an answer that uses what Jarvis REMEMBERS - and asks
                            about nothing else private - be read aloud? True by default (the
                            owner's choice); false with `memory_on_screen`. Missing (an older PC)
                            = false.
"sensitive_aloud": bool     (2026-09-24) may an answer that uses a SENSITIVE saved fact (the chat
                            route's `injected_sensitive`, §4) be read aloud? True only when the
                            owner chose `sensitive_aloud` AND this voice passed a real check (not
                            broad mode). Not implied by `memory_aloud` or `private_aloud`. On every
                            reply, refusals included. Missing (an older PC) = false.
```

**Hands-free (2026-09-24).** With `hands_free: button_only`, a clip whose
`?source=` is not `push_to_talk` - `wake_word`, or anything the PC does not
know - gets `private_aloud`, `memory_aloud` and `sensitive_aloud` all
**false**, whatever the other settings say; the answer is still given, and
the apps' rule below keeps it on screen. Under the default,
`same_as_button`, nothing changes. The utterance route itself still reads a
request with no `?source=` as `push_to_talk` (that line is in the owner's
`jarvis_hud.py`), so **send `source` on every clip**: `push_to_talk` for
the talk button, `wake_word` for everything the "hey Jarvis" listener
sends (both apps do).

### `/api/voice/status` - new in `gate`

```
"strictness": "very_strict" | "balanced",
"privacy": "private_on_screen" | "voice_is_enough",
"memory": "memory_aloud" | "memory_on_screen",
"sensitive_memory": "sensitive_on_screen" | "sensitive_aloud",   "" from an older PC: do not offer it
"hands_free": "same_as_button" | "button_only",                   "" from an older PC: do not offer it
"settings": {"strictness", "privacy", "memory", "sensitive_memory", "hands_free", "changed": epoch,
             "voice_is_enough_allowed": bool,        true only while very strict
             "min_command_seconds": 2.0 | 1.5,
             "choices": {"strictness": ["very_strict", "balanced"],
                         "privacy": ["private_on_screen", "voice_is_enough"],
                         "memory": ["memory_aloud", "memory_on_screen"],
                         "sensitive_memory": ["sensitive_on_screen", "sensitive_aloud"],
                         "hands_free": ["same_as_button", "button_only"]},
             "defaults": {"strictness": "very_strict", "privacy": "private_on_screen",
                          "memory": "memory_aloud", "sensitive_memory": "sensitive_on_screen",
                          "hands_free": "same_as_button"}},
"models": {"small":  {"installed", "name", "label": "the small voice-ID model", "bars_measured", "path"},
           "strong": {"installed", "name", "label": "the stronger voice-ID model", "bars_measured",
                      "path", "why"},
           "very_strict_uses": 0 | 1,               how many models very strict asks (one since 2026-09-24)
           "very_strict_model": "strong" | "small" | "",  which one: the stronger one whenever installed
           "balanced_uses": "strong" | "small" | ""},
"cohort": {"small":  null | {"speakers": 300, "source": "...", "where": "shipped with Jarvis" |
                            "built on this PC", "matches": bool},
           "strong": null | {...}},
"repeat": {"window_seconds": 10.0, "since": epoch,
           "very_strict": {"accepted", "refused", "too_short", "refused_then_accepted", "repeat_rate"},
           "balanced":    {...}},
"prints": {"phone" | "desktop" | "general": {... as before ...,
           "subprints": [{"condition": "close" | "far" | "room" | "general", "samples": int}],
           "strong_trained": bool,        the stronger model has a print of its own in it
           "strong_threshold": float}},   the owner's own bar for it (0 = the measured one)
"training": {... as before ..., "rounds": true, "settings": true, "measure": true,
             "session": null | {"mic", "add", "rounds": [{"round", "condition", "clips", "seconds"}],
                                "clips", "seconds", "expires_in"},
             "measure_last": {"at", "clips", "strong_model",
                              "very_strict": {"passed", "of", "too_short", "repeat_rate"},
                              "balanced": {...}},              only after a guided test
             "kind": "enroll" | "threshold" | "setting",       while a card waits
             "setting": {"name", "value"},                      while a setting card waits
             "last": {... as before ..., "outliers": [{"round", "clip"}], "added": bool,
                      "subprints": ["close", ...], "setting", "value", "model"},
             "limits": {... as before ..., "rounds": 3, "session_seconds": 900.0,
                        "measure_max_clips": 20},
             "round_asks": {"1": "normal, close to the microphone",
                            "2": "further away from the microphone, or quieter",
                            "3": "at another time of day, or in another room"}}
```

`gate.note` says, in words, when very strict is using one model, when the
print was made before the stronger model was installed (then
`needs_retraining` is true and the talk button hides), and when the model
installed is not one whose bars were measured. Show it.
`gate.repeat` counts since the backend started; nothing is kept on disk.
`repeat_rate` = `refused_then_accepted / accepted` - how often the owner had
to say it again within 10 s.

### `POST /api/voice/enroll` - the new modes

Every answer below is JSON; every refusal has `error`, a sentence to show
as it is.

**Training in rounds** (`rounds: true`):

```
{"mode": "train", "round": 1 | 2 | 3, "mic": "phone" | "desktop", "clips": [<base64 WAV>, ...],
 "add": false, "finish": false}
```

| answer | when |
|---|---|
| `200 {"ok": true, "pending": false, "held": <session>, "round": 1, "next_round": 2, "next_ask": "further away from the microphone, or quieter", "message"}` | the round is held in memory; **no card, nothing changed** |
| `202 {"ok": true, "pending": true, "clips": 30, "seconds": 104.0, "rounds": 3, "message"}` | `"finish": true` (with the last round's clips, or with no `clips` at all): ONE card for every held round |
| `400` | a clip is wrong (as today, with `"round"`), `round` is not 1-3, or `finish` with nothing held |
| `409 {"error", "session": <session>}` | another training (another mic, or `add` differs) is held - finish or cancel it |
| `409 {"error", "pending": true, "expires_in"}` | a voice card is already waiting |

- Each round is 3-12 clips and 80 s at most (the same limits as today).
  Sending a round again replaces that round's clips.
- Held clips are dropped, all of them, on `{"mode": "train", "cancel":
  true}` (`200 {"ok": true, "cancelled": bool, "message"}`), on a denied or
  timed-out card, and 15 minutes (`limits.session_seconds`) after the last
  round. `last.outcome` is then `"cancelled"` or `"expired"`.
- `"add": true` keeps the print that is there and adds these recordings
  to it (the card says "Add the recordings ... Nothing it had is
  deleted"). Without it the print is replaced, as today.
- The card's outcome: `last.outcome = "enrolled"`, with `outliers` - the
  clips left out because they did not sound like the rest, as
  `[{"round": 2, "clip": 5}]` (clip counted from 1 within its round). **Ask
  the owner to record exactly those again** (another `train` round with
  `"add": true`). `"failed"` with `outliers` means most clips were like
  that: record them again somewhere quieter.

**Strictness and private answers** (`settings: true`):

```
{"mode": "strictness", "value": "very_strict" | "balanced"}
{"mode": "privacy",    "value": "private_on_screen" | "voice_is_enough"}
{"mode": "memory",     "value": "memory_aloud" | "memory_on_screen"}
{"mode": "sensitive_memory", "value": "sensitive_on_screen" | "sensitive_aloud"}
{"mode": "hands_free", "value": "same_as_button" | "button_only"}
```

`hands_free` (added 2026-09-24, the owner's decision: "hands-free voice is
as trusted as the talk button by default, with a setting to make it
stricter"): how far a question started with "Hey Jarvis" is trusted.
`same_as_button` is the default and the looser value; `button_only` is the
stricter one and applies at once. Under `button_only`, a clip that did not
come from the talk button reads nothing private, remembered or sensitive
aloud (the reply's three `*_aloud` are false, above), and automatic
learning never saves a fact from that turn without a card (§19.2 item 5).
Going back to `same_as_button` raises the voice card, which reads: "Let a
question started with "Hey Jarvis" count the same as pressing the talk
button? / Then a recording or a copy of your voice played near the
microphone could have Jarvis remember things, or read memory and private
answers aloud. / If you did not just do this, say no. / If you say no:
nothing changes - "Hey Jarvis" questions stay on the stricter setting." A
settings file with no `hands_free` in it (every file from before) reads as
`same_as_button`; a damaged value, or an unreadable file, as
`button_only`. An older PC answers `mode: "hands_free"` with **503**, and
its `/api/voice/status` has `gate.hands_free: ""` - the apps then do not
offer the setting. Both apps show it as "Hands-free ("Hey Jarvis")", with
"Same as the talk button (default)" and "Only trust the talk button", and
name it "how far "Hey Jarvis" is trusted" in the waiting and last-card
lines.

`sensitive_memory` (added 2026-09-24, the owner's decision: an answer that
uses a sensitive saved fact stays on screen by default, even under "Read
aloud" for memories): `sensitive_on_screen` is the default and the strict
value, and applies at once. `sensitive_aloud` is the looser one and raises
the voice card, which reads: "Let Jarvis read answers that use a saved fact
about your health, money, passwords or other people's private details aloud, when you ask by
voice? / Anyone near the speaker will hear them. / If you did not just do
this, say no. / If you say no: nothing changes - those answers stay on your
screen." A missing, damaged or unreadable value reads as
`sensitive_on_screen`. An older PC answers `mode: "sensitive_memory"` with
**503**, and its `/api/voice/status` has `gate.sensitive_memory: ""` - the
apps then do not offer the setting.

`memory` (added 2026-09-24, the owner's choice: "looser now, with a setting
to make it more strict"): answers that use what Jarvis remembers are read
aloud by default. `memory_on_screen` is the stricter value and applies at
once; going back to `memory_aloud` is the looser one and raises the card.
A settings file with no `memory` in it (every file from before) reads as
`memory_aloud`; a damaged value, or an unreadable file, as
`memory_on_screen`. An older PC answers `mode: "memory"` with **503**.

| answer | when |
|---|---|
| `200 {"ok": true, "changed": true, "pending": false, "settings": {"strictness", "privacy", "voice_is_enough_allowed"}, "message": "Done - that applies now."}` | tightening (`very_strict`, `private_on_screen`): immediate, no card. It also makes a waiting card that would loosen the same setting do nothing (`last.outcome = "withdrawn"`). |
| `200 {"ok": true, "changed": false, ...}` | it was already that |
| `202 {"ok": true, "pending": true, "setting", "value", "message"}` | loosening: ONE card (`change_own_config`). **Nothing changes until it is approved.** `last.outcome` becomes `"setting_changed"`, `"denied"`, `"timed_out"`, `"refused"`, `"withdrawn"` or `"failed"`. |
| `503` | this PC's voice check is too old for that setting (`memory`, `sensitive_memory` or `hands_free` on a PC from before them) |
| `409` | `voice_is_enough` while balanced ("private answers can only be read aloud while the voice check is very strict"), a voice card already waiting, or the tier is not `ask` |

Choosing `balanced` also puts private answers back on screen
(`privacy` becomes `private_on_screen`), and the card says so.

**The guided repeat test** (`measure: true`):

```
{"mode": "measure", "mic": "phone", "clips": [up to 20 of the owner's own sentences]}
-> 200 {"ok": true, "clips": 20, "print": "phone", "strong_model": true,
        "very_strict": {"passed": 15, "too_short": 2, "of": 20, "repeat_rate": 0.25},
        "balanced":    {"passed": 19, "too_short": 0, "of": 20, "repeat_rate": 0.05},
        "per_clip": [{"seconds": 2.4, "very_strict": true, "balanced": true, "score": 0.71}, ...],
        "message": "Very strict let 15 of 20 through; balanced 19 of 20."}
```

No card, nothing stored but the counts (`measure_last`), and not counted in
`repeat`. 80 s in all per request, as for training; send two halves if the
sentences are long, and add the counts up.

**"Someone else"** (`calibrate`, unchanged request): the reply adds
`"passed": [bool, ...]` (would each clip have been let in, with everything
the current setting uses), `"passed_count"`, `"strictness"`, and
`"model": "small" | "strong"` - which model `scores` and `suggested` are
for. Send that `model` back with the threshold card:
`{"mode": "threshold", "mic": "phone", "threshold": 0.55, "model": "strong"}`
(default: the stronger model when the print has it). A bar below that
model's measured floor is a **400** naming the lowest allowed.

### What the apps must do about private answers

The owner's rule: with `private_on_screen` (the default), an answer drawn
from email, the calendar or notes is **not read aloud** unless the question
was typed or tapped on the owner's own unlocked device. An answer that uses
what Jarvis remembers is read aloud by default, and kept on screen too when
the owner chooses `memory_on_screen` (the owner's choice, 2026-09-24). So,
for a question that came by VOICE and reply `private_aloud: false`:

1. Show the answer on screen as usual.
2. Read it aloud only when nothing says it is private: `question_private`
   is false, the chat reply's `X-Jarvis-Route` has no `gate: "private"`,
   no tool ran while it was being written, and - **only when
   `memory_aloud` is false** - no `injected_facts` above 0 (both route
   fields §4 describes; the route that fills them is on the PC and was not
   read for this). Otherwise say one fixed line instead, such as "It's on
   your screen."
   "A tool ran" is read from the event stream's `step` events
   (`tool_started` / `tool_finished`) between the question and each
   sentence, and a stream that was stale or dropped in that time counts as
   "a tool may have run". Both apps do this: `: jarvis-status working`
   alone arrives only after 1.5 s, so a quick calendar or email lookup was
   missed (voice audit, 2026-09-24).
   Both apps ask `/api/voice/say` for the next sentence's sound while the
   current one plays (one ahead, never more). So the rule is asked twice
   per sentence: before its sound is asked for, and **again right before
   it is played** - a sound made while the answer still looked safe is
   dropped unplayed if a tool started, or the stream dropped, in the
   meantime. "Stop", a barge-in or a new question drops it too.
3. **Sensitive saved facts** (the owner's decision, 2026-09-24): when the
   route's `injected_sensitive` is above 0 - or it is missing and
   `injected_facts` is above 0 (an older PC: fail closed) - and the
   utterance reply's `sensitive_aloud` is not true, keep the answer on
   screen ("It's on your screen."). This applies **even when
   `memory_aloud` or `private_aloud` is true**.
4. Treat a reply from an older PC (no `private_aloud`, no `memory_aloud` or
   no `sensitive_aloud` field) as `false`.
5. Nothing more is needed for `hands_free`: under `button_only` the PC
   sends the three `*_aloud` as false for a hands-free clip, and steps 2-4
   keep its answer on screen.

**Said plainly about `memory_aloud`:** a remembered fact can be about
something sensitive (health, money) while the question is not ("what
should I have for dinner?"). Step 3 keeps such an answer on screen by
default: `injected_sensitive` counts the recalled facts the same word-list
check automatic learning uses (§19.2, check 9) calls sensitive. It is a word
list, not a model - a sensitive fact worded in a way the list misses is
read aloud under `memory_aloud`, and `memory_on_screen` is the way to keep
every memory answer on screen.

**Known gap, said plainly:** the server cannot yet label a finished answer
as private. `X-Jarvis-Route` is sent before the model starts, so it cannot
know that the model will call the email or calendar tool; the rule above is
the apps' best information until the chat route says so at the end of the
answer. `jarvis_voice.may_speak(private, origin)` is the helper that route
should call when it does.

## 17. Interrupting by talking, the delay, and "One moment." (added 2026-09-24)

`backend/voice-flow.patch` and `backend/jarvis_voice_flow.py` (with small
changes in `jarvis_speech.py`, `jarvis_voice.py`, `jarvis_voices.py`,
`jarvis_turn.py` and `jarvis_agent.py`). The owner's three decisions of
2026-09-24. **Built on the backend first; both apps use it since
2026-09-25** - what each app does is part 5, "In the apps", below, with the
two additions of 2026-09-25 (parts 6 and 7). One new route
(`GET /api/voice/moment`, `ported` in `tools/check_parity.py`); the rest
is on routes both apps already call. How it works, and the owner's one-line
commands, are in `backend/README.md`, "The voice flow".

**Check before you send.** Everything below exists only when
`GET /api/voice/status` has a `flow` block. **Never send
`source=barge_in` to a PC whose status has no `flow` block, or whose
`flow.barge_in.available` is not `true`**: an older `jarvis_speech.hear()`
treats any `source` other than `wake_word` as push-to-talk, so it would
check the clip and, if it was the owner, TRANSCRIBE it. (Whether the
owner's route refuses an unknown `source` before that is not visible from
this repository.)

### The `flow` block of `/api/voice/status`

```
"flow": {
  "available": true,                      false: jarvis_voice_flow.py is missing (everything else below then off/empty)
  "barge_in": {"enabled": bool,           [voice] barge_in_enabled (default true)
               "available": bool,         the PC can tell your voice now: switched on, a voice print, a voice-ID model, not broad mode
               "why": str,                why not, a sentence to show ("" when available)
               "min_seconds": 1.0,        least speech it judges (the VAD's span, about 0.4 s of words)
               "bar": "balanced",         the voice-print bar it uses, whatever commands use
               "stop_word": bool},        this PC can also hear "stop" in a barge-in clip
  "moment":   {"enabled": bool,           [voice] one_moment_enabled (default true)
               "text": "One moment.",
               "key": str,                changes whenever the clip would sound different (another voice, engine, speaker, speed)
               "ready": bool,             the clip for `key` is made; GET /api/voice/moment answers at once
               "voice": "builtin" | "<id>", "engine": "kokoro" | "zipvoice" | "f5",
               "seconds": float | null,   how long the clip lasts, once ready
               "after_ms": 1000,          a suggestion only: the apps decide when to play it
               "why": str},               why there is none, when there is none
  "warm":     {"enabled": bool,           [voice] warm_engines (default true)
               "state": "waiting" | "warming" | "ready" | "off",
               "seconds": float | null, "steps": {"speech_check": ms, "speech_to_text": ms, ...}},
  "timings":  [ROW, ...],                 oldest first, at most 20, in memory only
  "summary":  [{"step", "label", "turns", "median_ms", "worst_ms"}, ...]   one line per step, over `timings`,
  "after_question": bool,                 since 2026-09-25: keeps listening after Jarvis asks a question (part 6)
  "cut_off": true                         since 2026-09-25: reads `interrupted` and keeps it on this PC (part 7)
}
```

The three switches are `[voice]` lines in `jarvis-framework.toml`, read and
never written by a route - the same as `turn_enabled`. No app can change
them; each app keeps its own per-device switch for whether to use them (both
apps already have "Interrupt Jarvis while it talks"). None is an approval
card: interrupting only stops Jarvis's own speech, the clip is Jarvis's own
words, the warm-up loads what is already installed, and none of them sends
anything anywhere.

### 1. Interrupting Jarvis by talking - `source=barge_in`

```
POST /api/voice/utterance?source=barge_in&mic=phone|desktop      body: one WAV, as for any utterance
-> 200 {"stop": bool, "available": bool, "source": "barge_in",
        "why": "owner_voice" | "stop_word"                        (stop: true)
             | "not_owner" | "jarvis_voice" | "too_short" | "no_speech" | "unreadable"
             | "stop_ignored" | "not_ready" | "off" | "not_installed",   (stop: false)
        "reason": "<a sentence>", "seconds": <clip length>, "ms": <how long the PC took>}
```

- **Send it only while Jarvis is speaking** (reply audio playing), only with
  `flow.barge_in.available` true and the app's own switch on, and hold it on
  a stale link like every other request. Send what the microphone heard
  from when speech started; measured here on synthetic voices (not the
  owner's), the owner was recognised from 2-second clips and **not** from
  1.2-1.5 second ones, so about 2 s of sound is the suggestion.
- **`stop: true`**: silence the reply at once - exactly what an app already
  does for a wake-word reply with `stop: true`. **Do nothing else**: it is
  not a command, and there are no words in it. **`stop: false`**: carry on
  speaking; show nothing, except `reason` for `stop_ignored` if you like.
  **`available: false`**: stop sending barge-in clips until the status says
  otherwise (show `flow.barge_in.why` in settings).
- **What stops it:** the owner's voice (the voice print for `mic`, at the
  balanced bar), and the word "stop" said by anyone (the same stop-word
  model and 30-second echo guard as a wake-word clip). **What does not:**
  anyone else (the TV, a visitor), Jarvis's own voice through the speakers
  (the clip is also compared with the active custom voice's recording, the
  cached "One moment." clip and a sentence of the built-in voice made on the
  PC; `why: "jarvis_voice"` when it was at least as close to one of those
  as to the owner), a clip with too little speech, broad mode.
- **Never transcribed.** No speech-to-text runs for it, on the PC or
  anywhere; the check does not count towards the owner's "had to say it
  again" numbers; nothing is kept. "Hey Jarvis, ..." said over a reply
  stops the reply and nothing more: to have the question answered, send
  the same clip again as `source=wake_word`, which makes every check it
  always made (the desktop already sends such a sentence as a new
  question).
- Through a route without `voice-flow.patch` but with this
  `jarvis_speech.py`, the reply is the usual utterance reply with `stop`,
  `reason`, `ok: false` and `text: ""` - read `stop` and it means the same.

### 2. The delay, step by step - `&waited_ms=` and `flow.timings`

An app MAY add `&waited_ms=<whole milliseconds>` to a push-to-talk or
wake-word utterance: from the moment its own speech detector last heard
speech to the moment it sends the clip (its Smart Turn pause included).
0-60000; anything else is ignored. It is only ever kept as that number.

One `ROW` per spoken turn that became words (a refused clip makes none).
Every value is a number of milliseconds, `null` when not known, or as
shown - **never words**:

```
{"at": <unix seconds>, "mic": "phone" | "desktop" | "", "source": "push_to_talk" | "wake_word",
 "cold": bool,               speech-to-text had to be loaded during this turn
 "end_wait_ms",              the app's own wait (waited_ms); null if not sent
 "turn_ms",                  Smart Turn on this PC, if the desktop asked it in the 5 s before
 "vad_ms", "wake_ms",        finding the speech; "stop" and "hey Jarvis" (wake-word clips only)
 "owner_check_ms", "stt_ms", checking it is the owner; speech-to-text
 "heard_ms",                 from the clip arriving to its words being ready (all of the above)
 "chat_ms",                  ... to the chat request starting on this PC
 "first_token_ms",           ... to the answer's first word
 "first_sentence_ms",        ... to its first complete sentence (".", "!" or "?" and a space)
 "say_start_ms",             ... to the first /api/voice/say of the answer arriving
 "say_ms",                   how long that first say() took to make its sound
 "first_audio_ms",           from the clip arriving to that sound being ready on this PC
 "total_ms"}                 end_wait_ms + first_audio_ms, when both are known
```

`summary` lists these steps: `end_wait_ms`, `turn_ms`, `vad_ms`,
`owner_check_ms`, `stt_ms`, `to_chat_ms` (the app passing the words on),
`model_first_word_ms`, `first_sentence_ms` (the rest of the first
sentence), `say_ms`, `first_audio_ms`, `total_ms` - each with `label`
(fixed words to show), `turns` (how many rows had it), `median_ms` and
`worst_ms`.

**How a row is put together, honestly:** by time, not by an id. A chat
turn on the local model starting within 20 s of a voice turn's words is
taken as its answer, and the first `/api/voice/say` within 120 s after that
as its first sound. A typed question inside that window would be counted
as the answer - numbers only, so a wrong guess is a wrong number and
nothing more. Not measured: a cloud answer, and the time for the sound to
reach the app and start playing (the app can add its own).

### 3. "One moment." - `GET /api/voice/moment`

```
GET /api/voice/moment    -> 200, Content-Type audio/wav: "One moment." (mono, 16-bit, the voice's own rate)
                         -> 503 {"available": false, "error": str, "why": str}   none right now (switched off,
                                                                                nothing can speak, ...)
```

Token and `X-Jarvis-Client: hud` as always; 401 / 403 as for any route.

- **It is in the voice Jarvis speaks in now**, custom voices included. The
  PC makes it once per voice (`flow.moment.key`) and keeps it in memory;
  when the voice changes, the key changes and it is made again - in the
  background as soon as a status read notices, so it is normally `ready`
  before anyone asks. Making it never starts the better voice's program on
  the second card.
- **For the apps:** fetch it when `flow.moment.key` differs from the one you
  have, and keep it. When the owner has finished speaking and **no reply
  sound has started** about `after_ms` later (the apps decide the exact
  time), play it - **once per turn at most, and never over the reply**: if
  the reply's first sound arrives while it plays, stop it (or let it end,
  it is under a second) before the reply starts. Not after a refused clip,
  a barge-in, or a "stop". It is Jarvis's own voice, so the barge-in check
  above already counts it as Jarvis, not the owner.
- **At today's speeds, `after_ms: 1000` would fire on most spoken turns.**
  From the owner finishing to Jarvis's first sound is estimated at roughly
  2.5-4 s with the voice on the PC's processor (making the first
  sentence's sound alone takes about 1.3-1.6 s, measured in the dev
  container; the model's part is not measured). So "no sound a second
  later" is the usual case, not the exception. The suggestion is
  unchanged; an app that builds this should look at the owner's own
  `flow.summary` first. The voice research of 2026-09-24 suggests playing
  it when a tool starts (a `step` event with `tool_started`, which both
  apps already watch) rather than on a flat timer.

**What an app should build** (suggested, for both): extend the existing
"Interrupt Jarvis while it talks" switch so that, while Jarvis speaks,
speech the microphone hears is sent as `source=barge_in` (with the rules in
1); a "Say 'One moment' if I'm kept waiting" switch (on by default) that
plays the clip as in 3; send `waited_ms` on every utterance; and a "Voice
delay" panel showing `flow.summary` (the `label`, `median_ms` and
`worst_ms` columns), with `flow.warm.state`. **Built 2026-09-25** (part 5),
except the "Voice delay" panel, which neither app has yet - the one-line
command in `backend/README.md` prints the same table.

### 4. Spoken-style answers, and speaking from the first comma (2026-09-24)

The owner's decision of 2026-09-24: "spoken questions get spoken-style
answers, and speech starts at the first comma". **No new route, no new
field, nothing to check before sending**: both halves ride on what the apps
already send and already do.

**On the PC** (`backend/jarvis_agent.py`, `SPOKEN_NOTE`,
`with_spoken_note`). When the **newest** user message of a `POST /api/chat`
has `provenance: "voice"` (18.1), every request the answering loop makes to
this PC's model for that turn carries one extra system line: the answer
will be read aloud; start with one short sentence; one to three sentences
unless the owner asks for more detail; no lists, headings, markdown, emojis
or symbols that cannot be said; numbers and units written as they are said.
Adapted from kyutai unmute's prompt (MIT, `THIRD-PARTY-NOTICES.txt`).

- **Typed turns are unchanged**, byte for byte - and so is a typed turn
  whose earlier messages were spoken. `provenance` missing or anything but
  `voice` on the newest message: no line.
- **Never message 0.** It goes just before the newest user message. When
  that message is the first one, the Modelfile's SYSTEM block
  (`LANE_SYSTEM`, word for word) is put first, then the line: a system
  message at position 0 would make Ollama leave the built-in block out
  (`memory-prefix.patch`). Placed after the history is trimmed, so trimming
  cannot leave it first. On the second card the block is not sent twice.
- **Local only.** It is added to the request for this PC's model inside the
  answering loop, never to the conversation the relay sends; a cloud lane
  gets the newest user turn only (`cloud-one-turn.patch`) and, when a turn
  leaves this PC, user messages only (`degrade-filter.patch`).
- The answer is shorter on screen too. The private-answer rules (16) are
  unchanged: a private answer to a spoken question is still kept on screen.

**In both apps** (desktop `src/speech-pieces.js`, used by `main.js`
`checkForSpeakableSentence`; phone `voice/SpeechText.kt`
`findSentences(..., firstPiece)`, used by `VoiceSession.speakStreamed`).
The **first** piece of a spoken answer - nothing of it cut yet - ends at the
earliest of:

- `,` `;` or `:` followed by whitespace, with at least **10** characters
  before it, when the word before it is not in stream2sentence's
  avoid-pause list (100 words: "and", "the", "to", "is", "I", ...; MIT,
  credited). "1,450", "10:30" and "https://" are never cut: no whitespace
  follows the mark;
- a sentence end (`.` `!` `?` followed by whitespace), as before;
- with neither, after **12** complete words, at the first word from there
  that is not on the list.

Every later piece is a sentence, as before. Everything else is unchanged:
one piece per `/api/voice/say`, the next piece's sound asked for while the
current one plays (one ahead), the private-answer check before asking for a
sound and again right before playing it, "stop". The numbers, marks and
word list are the same on both apps, and both are held to one list of cases,
`jarvis-desktop/tests/fixtures/first-piece-cases.json` (desktop
`tests/speech-pieces.mjs`, phone `SpeechTextTest.kt`), fed whole and one
character at a time.

`flow.timings` is unchanged: `first_sentence_ms` still marks the first
complete sentence; an app that asks for the first piece's sound earlier
shows up in `say_start_ms`.

### 5. In the apps (2026-09-25)

Both apps, the same rules and the same numbers: desktop `src/voice-flow.js`
(the rules), `main.js` (the Jarvis bar), `src-tauri/src/voice_flow.rs` (the
clip); phone `voice/VoiceFlow.kt` (the rules), `VoiceSession.kt`,
`service/WakeWordService.kt`, `audio/Speaker.kt`. One list of cases holds
both: `jarvis-desktop/tests/fixtures/voice-flow-cases.json` (desktop
`tests/voice-flow.mjs`, phone `VoiceFlowTest.kt`).

**Interrupting by talking - pause first, decide second** (LiveKit agents'
shape, `voice/agent_activity.py`; the voice research of 2026-09-24,
recommendation 4). Only while "hey Jarvis" listening is on (the phone's
hands-free listener, the desktop's listener) and the app's own "Interrupt
Jarvis while it talks" is on - the switch both apps already had; no new one.

1. The app's own loudness detector (no speech-to-text, no words: the same
   rule both apps' pause detectors use) hears **0.5 s** of speech in one
   utterance while a reply plays.
2. Ignored during the first **3 s** of a reply (from its first sound):
   that is when Jarvis's own voice most often comes back through the
   microphone while the echo canceller settles (kyutai unmute waits 3 s
   too). The stop word is not affected - it works from the first word, as
   before.
3. Otherwise - and only with `flow.barge_in.available` true and a live link
   (rule 4) - the reply is **paused at once** (not talked over), and about
   **2 s** of that speech, from 0.3 s before it began, goes as
   `source=barge_in` (or less, if the speech ends first: the desktop when
   its listener cuts the utterance, the phone after 0.7 s of quiet).
4. `stop: true`: silenced for good, exactly like "stop" - and the sentence
   whose sound was already made ahead is dropped, never played. `stop:
   false`: the reply carries on from where it paused. No answer within
   **4 s** of pausing: it carries on too. `available: false`: no more
   barge-in clips until the status says otherwise.
5. The utterance is still sent as `source=wake_word` when it ends, as
   before, so "hey Jarvis, ..." said over a reply is still a new question.

**"One moment."** Each app fetches the clip when `flow.moment.key` changes
(the phone on every status read, the desktop when listening starts, when the
talk button is pressed and with every spoken question), and plays it when a
`step` event says `tool_started` during a spoken question - **once per
question**, only **before the answer has made a sound** (the answer's first
sound waits for it to end; it is under a second), never after "stop" or an
interruption, and only with the app's own switch on and
`flow.moment.enabled`. Not on a timer. The new switch, in both apps, is the
one this section suggested: **"Say "One moment" if I'm kept waiting"**, on
by default, per device (desktop Settings -> Voice, "While you wait"; phone
Checks, the "hey Jarvis" card). The PC's `[voice] one_moment_enabled` still
turns the clip off for both.

**`waited_ms`.** Sent with every push-to-talk and wake-word clip: how long
it had been quiet when the clip went. The desktop's listener measures it
exactly (its last loud moment to the send, the Smart Turn pause included);
push-to-talk on both apps, and the phone's hands-free clips, measure the
quiet at the end of the clip (30 ms steps, louder than three times the
clip's quietest step counts as speech - `trailing_quiet` /
`VoiceFlow.trailingQuietMs`, the same rule).

**"I heard you."** A tiny two-note sound (660 Hz then 990 Hz, 55 and 75 ms,
quiet), made from numbers in each app - no file, no new dependency - when
the owner's turn is cut: letting go of the talk button (both apps), the end
of a "hey Jarvis" sentence (the phone: its own spotter heard the phrase;
the desktop: when the PC answers that "hey Jarvis" was heard from the owner,
because only the PC knows which of the sounds its listener cuts were meant
for Jarvis), and the reply to a question (part 6). **It has a switch in
both apps since 2026-09-25** (the owner's decision): **"Play a short sound
when I finish speaking"**, off by default, per device, right under the "One
moment" switch (desktop Settings -> Voice, "While you wait"; phone Checks,
the "hey Jarvis" card). Off, the sound is simply not played; nothing else
about the turn changes. It is the app's own setting, like "One moment", but
unlike that one there is nothing on the PC behind it - no route, no
`[voice]` key: the sound is made in the app and never leaves it. Desktop:
`jarvis.voice.heardSound` in the app's own storage (`voice-flow.js`
`loadHeard`); phone: `heard_sound` in `ClientSettings`
(`VoiceSession.heardYou` asks it first).

**Not built:** the "Voice delay" panel (above); pausing the phone's own
fallback voice (the handset's text-to-speech, used only when the PC has no
voice and allows it) - it plays on while the PC decides.

### 6. Keep listening after a question (2026-09-25)

When the **last** sentence Jarvis spoke ends with a question mark (`?`,
full-width `？`, or the Greek question mark U+037E - and a plain `;` in
Greek text, where Unicode folds that mark into it; closing quotes and
brackets after it allowed), the next hands-free clip needs **no "hey
Jarvis"**, as after "Hey Jarvis." on its own. The pattern is Home
Assistant's `continue_conversation` (`conversation/chat_log.py`,
Apache-2.0); nothing of it is copied.

- **On the PC** (`jarvis_speech.py`, no new route, no new field): `say()`
  opens the window when it makes the sound of a sentence that asks
  something, and any later sentence closes it (the question was not the
  last thing said). It lasts `awake_timeout_s` (8 s shipped) after the
  question should have finished playing (its sound's length, plus the
  sentence before it, which may still have been playing - the apps ask for
  one sentence ahead). Kept per app: a question said to the phone opens it
  for the phone's clips only.
- **The owner check still runs on the clip**, before any words exist, and
  a clip that fails it does not use the window up - Jarvis's own voice or
  the TV heard through the microphone cannot take it. The first clip that
  passes does. It is a hands-free clip in every other way: under "Only
  trust the talk button" it is trusted like any "hey Jarvis" clip.
  Push-to-talk is unchanged. "Hey Jarvis, ..." said anyway is answered with
  the words after the phrase.
- **The desktop** needs nothing more: its listener sends every utterance
  anyway. **The phone** (hands-free only, and only when the status says
  `flow.after_question: true`): when the answer it just spoke
  ended with a question and was not cut off, it records the owner's reply
  without waiting for its spotter (up to `awake_seconds`, like the sentence
  after "Hey Jarvis."), plays "I heard you", and sends it - only if it holds
  speech. After a push-to-talk question the phone does not open the
  microphone by itself.

### 7. Telling the model it was interrupted (2026-09-25)

When the owner stops Jarvis's spoken answer - talking over it (a `stop:
true`), "stop", "hey Jarvis" over it, or the talk button - the app keeps the
sentence the owner heard last (the one playing, or else the last one that
played) and sends it **once**, with the **next** question (typed or spoken,
within two minutes), as **`interrupted`** on the newest user message:

```
{"role": "user", "content": "what about the weekend", "provenance": "voice",
 "interrupted": "Tomorrow looks mild, with light rain in the morning."}
```

- **On the PC** (`jarvis_agent.py`, `CUT_OFF_NOTE`, `with_cut_off_note`):
  the answering loop reads it from the request as it arrived and adds one
  system line to the request for **this PC's model**, just before the
  newest question: the owner interrupted the last spoken answer and heard
  it only up to that sentence; do not go on as if they heard the rest. The
  sentence is cleaned (one line, at most 240 characters). The idea is
  Hermes Agent's (`tools/tts_streaming.py`, MIT); the words are this
  project's.
- **Never first** (placed like the spoken-style note; `keep_rules_first`
  runs after it), **never the owner's words**: it is a system line, never
  in the conversation the app sent - which is what the learner
  (`jarvis_intake.owner_turns`: user messages, their `content` only) and
  chat history read - and **never leaves this PC**: `chat-history.patch`
  takes `interrupted` off with `provenance` before any model or the relay
  sees the conversation (18.1).
- **Sent only when the status says `flow.cut_off: true`.** A PC without the
  new `chat-history.patch` line would not take the field off, and a
  question the router sends to a cloud model would carry it there inside
  the message - so both apps check first, and a PC that does not say so is
  never sent it.
---

## 18. Chat history (added 2026-09-24)

**What it is.** The owner decided on 2026-09-24 that chat history,
including what is said to Jarvis by voice, is kept **on the PC**, by
default, **encrypted**, with a switch to turn it off. Until now the only copy
of a conversation was the one an app held in memory. The phone keeps no
history of its own beyond what it already does: both apps read it from the
PC.

It is also the PC's own record of each turn, written as the turn arrives,
with **where its words came from**. The apps re-send the whole conversation
with every question (§4), so a re-sent turn is only the app's say-so;
automatic learning (§19) trusts this PC's record of the live turn instead -
through an in-memory registry `record_turn()` writes on every request,
**whether or not history is on**.

Backend: `backend/chat-history.patch` (last in the patch order) and
`backend/jarvis_chat_log.py` (shipped whole). Routes are in the §6 tables
too. Every route needs the pairing token and passes the origin check, like
every other private route.

### 18.1 What every app adds to `POST /api/chat`

Both optional; an app that sends neither still works exactly as before.

On the request:

- `conversation_id`: 8-64 characters of `A-Z a-z 0-9 _ -`, made by the app (a
  random UUID is fine). A new one on "New conversation", when the chat is
  cleared, and when the app starts. Anything else is treated as missing.
- `device`: `"desktop"`, `"hud"` or `"phone"`. Shown in the History list;
  never trusted for anything.
- `temporary` (2026-09-25, `temporary-chat.patch`): `true` asks for a
  **temporary chat** - no memory used, nothing learned, nothing kept (§4,
  "A temporary chat"). Only JSON `true` counts; the apps send it only while
  the mode is on, and never `false`. Taken off with the other three before
  any model sees the request. Sent only to a PC whose `/api/version`
  reports `capabilities.temporary_chat`.

On each `role: "user"` message:

- `provenance`, one of:

  | value | meaning |
  |---|---|
  | `typed` | typed into the box by the owner (the app's default for its own box) |
  | `voice` | the transcript the PC's speech route gave back for this turn; on the newest message it also gets the answer in a spoken style (17, part 4) |
  | `shared` | came from another app (the phone's Share sheet) |
  | `clipboard` | put in the box from the clipboard (the desktop hotkey) and not edited before sending |
  | `pasted` | pasted or dropped into the box (desktop: a `paste` or `drop` on the box since it was last empty; phone: one edit that inserted more than 40 characters at once) |
  | `picture_caption` | words sent with a picture |

  Missing, or any other value, is recorded as **`unknown`**, and unknown
  counts as "not the owner's own words" everywhere it matters. The apps keep
  each user turn's `provenance` in their own history and send it again with
  that turn every time. The existing `origin` field is unchanged.
- `interrupted` (since 2026-09-25, newest message only, never replayed):
  the last sentence of Jarvis's spoken answer the owner heard before
  cutting it off - section 17, part 7.

**Phone Share.** Shared text is no longer put into the owner's draft. It
is held as a chip above the box ("Shared text · 1,204 characters", with an
X), and sent as its **own** user message, `provenance: "shared"`, just
before the owner's typed message in the same request. If the owner typed
nothing, the shared message is sent alone.

**Desktop clipboard hotkey.** The short-snippet prefill is tagged
`clipboard` until the box is emptied, edited or not. Clipboard context
(the attached snippet) is sent as its **own** user message,
`{"role": "user", "content": "Context:\n<the text>", "provenance":
"clipboard"}`, just before the question - the same shape as the phone's
Share. Since 2026-09-25 (security audit M1); it used to be a `system`
message, and the PC's outside-text rules read only user messages, so
copied text slipped past them. The PC does not keep it in History (only
the newest message, and a `shared` one just before it, are kept).

**What the PC does with the tags in the answering loop** (`jarvis_agent`,
"Outside text in the tool loop"): only `typed` and `voice` are the owner's
own words. Any other value - or none - on the newest message, or on a
`shared` or `clipboard` message sent just before it, makes the turn one
shaped by outside text: a note write asks first, and every card says so.
So does any `system` message in the request as the app sent it.

**The server takes `provenance`, `interrupted`, `conversation_id` and
`device` off before anything goes to any model**, local or cloud: the local answering loop gets
the messages without them, and every request the relay sends (each hop of
the step-down loop) is cleaned in `_open()`. The request as it arrived is
left alone, because the learner reads `origin` from it and the history
record reads `provenance`.

### 18.2 What the PC keeps

For each `/api/chat` request, while history is on and encryption works:

- **The newest user message only** - the live question, never the history
  the app re-sent - with its provenance. The one addition: a `shared`
  message sent immediately before it in the same request (phone Share) is
  kept with it.
- **The answer - only when the local model made it** through Jarvis's own
  answering loop (`jarvis_agent.run_local_turn`) and it finished. **A cloud
  answer is not kept**: the question is recorded with `answer_kept: false`
  and the answer is not. Nor is an answer the app left before it finished,
  or one that failed.
- `read_outside`: true if **any** tool ran in that turn - every tool result
  is text Jarvis did not get from the owner. From that turn on, the
  conversation is `tainted`.
- when (`at`, unix seconds), which app (`device`), which model (`lane`),
  and the turn's number in the conversation.
- A picture turn: **the words only**, as `picture_caption`. The picture
  itself is never kept.

`voice` is recorded as `voice` only when the words match a transcript the
PC's own speech route produced in the last 10 minutes (only a hash of it is
held, with the voice check's strictness, model and mode, and - since the
`hands_free` setting - how the clip started, `source`: `push_to_talk`,
`wake_word`, or `""` when the speech route did not say). Otherwise a claimed
`voice` is recorded as `voice_unverified`.

**Not kept:** tool output, system or context messages, deep questions,
wiki jobs, notes (#obs, #log), approval cards, pictures. None of them come
through `/api/chat`'s record. And nothing at all of a **temporary chat**
(`"temporary": true`, §4): only the in-memory registry's hash of its live
message, under the provenance `"temporary"` - never its words, and nothing
in `chat-history.db`.

A request with no (or a malformed) `conversation_id` - an older app - is
still kept, grouped per app and per day under an id like
`untagged-phone-20260924`.

**Encryption.** Every piece of text (each turn, and each conversation's
title - its first user line, cut to 80 characters) is encrypted on its own
with AES-256-GCM and a fresh nonce; the conversation id and turn number are
bound in, so a row cannot be moved to another conversation and still open.
The key is 32 random bytes in **Windows Credential Manager**, under
`Jarvis Backend/chat history key`, made on first use and read back before
use. The file is `<config folder>/chat-history.db` (the same folder as the
custom voices). Not encrypted, said plainly: the conversation ids, turn
numbers, times, roles, provenance, device, model name, `read_outside` and
`answer_kept` - they say when and how often you talked to Jarvis, not what
about.

**Fail closed.** If the `cryptography` package is missing, Credential
Manager cannot be used, or the key does not open what is already kept (it
was deleted or replaced), **nothing is recorded and nothing is written in
plain text**. `recording` is `false` and `why_not` says why, in words the
apps show as they are.

**Keeping and deleting.** `keep_days` is `0` (keep until deleted - the
default), `30`, `90` or `365`. Conversations whose last turn is older are
deleted when the history is first used after the backend starts, and then
at most once a day. Turning history off stops recording at once; what is
already kept stays until it is deleted or expires. Deleting a conversation
removes its rows. **Why the extra step:** SQLite does not wipe deleted rows -
their bytes stay in the file's free pages until something reuses them - so
`secure_delete` is on (freed space is overwritten with zeros) and the file
is compacted with `VACUUM` after a delete, at most once an hour.

### 18.3 Routes

`GET /api/history?limit=30&before=<updated unix seconds>`

```json
{"enabled": true, "recording": true, "why_not": "", "waiting": false,
 "keep_days": 0, "encrypted": true,
 "conversations": [{"id": "...", "title": "...", "started": 1790000000,
   "updated": 1790000300, "turns": 6, "device": "phone",
   "has_voice": true, "tainted": false}]}
```

Newest first. `limit` 1-100, default 30; `before` pages to older ones
(pass the last row's `updated`). `has_voice` is true when any message was
`voice` or `voice_unverified`. When the history cannot be opened the list is
empty and `why_not` says why.

`GET /api/history/conversation?id=<id>`

```json
{"id": "...", "title": "...", "tainted": false,
 "turns": [{"role": "user", "text": "...", "at": 1790000000,
            "provenance": "typed", "read_outside": false, "answer_kept": true},
           {"role": "assistant", "text": "...", "at": 1790000004}]}
```

`404` if there is no such conversation. `answer_kept: false` on a user turn
means its answer was not kept (a cloud answer, or one that did not finish).

`POST /api/history/delete {"id": "..."}` - `200 {"ok": true}` or `404`. One
conversation per request. **There is no "delete all" route**: irreversible
bulk actions stay off the API.

`POST /api/history/settings` - one setting per request:

- `{"enabled": false}` - 200 at once, "Chat history is off. Nothing new is
  kept. What is already kept stays until you delete it." It also withdraws
  a waiting ON card.
- `{"enabled": true}` - **202** `{"waiting": true, ...}` and ONE approval
  card, action **`history_enable`**, which must be tier `ask` in
  `jarvis-framework.toml` (shipped that way) or this answers **503**. Only
  approving the card turns history on; denied, timed out or withdrawn
  changes nothing. Already on: 200, no card. A card already waiting: 202, no
  second card. A "no" on this card is never turned into a proposed memory
  (`gate-outcome.patch`'s list).
- `{"keep_days": 0 | 30 | 90 | 365}` - 200 at once; the reply says how many
  conversations the change deleted.
- Anything else - `400`.

Every reply carries the same status fields as `GET /api/history`.

If `jarvis_chat_log.py` is not installed, all four routes answer **503**
`{"available": false, "error": "chat history is not installed on this PC,
so no chats are kept", "reason"}` - and chat keeps working, keeping nothing.

### 18.4 What each app shows

Both apps (parity rule): a **History** view - desktop, a History section in
the Brain window next to Memory; phone, a History screen next to the Brain's
other sections. (The HUD page sends `conversation_id`, `device: "hud"` and
`provenance` too, but has no History view of its own.)

- The list: title, when, device, a small mic mark for `has_voice`, a small
  "read outside text" mark for `tainted`. Newest first, "Load older".
- Opening one: a read-only transcript. On user turns that are not
  typed or voice, the provenance is shown quietly ("shared", "pasted",
  "from clipboard").
- Deleting one, with a confirm step. No delete-all.
- On a stale link (rule 4) both apps hold turning history ON, deleting a
  conversation and changing how long they are kept - each cannot be taken
  back or raises a card, and acts on a list that may be out of date, the
  same as the desktop's Forget. Turning history OFF is never held.
- In the same place: **"Keep chat history on this PC"** - under it, "Your
  chats, including what you say to Jarvis by voice, are kept on this PC,
  encrypted. Nothing is sent anywhere." ON raises the card and shows
  "Waiting for your approval" the way the learning switch does (track the
  `history_enable` card in the approval queue); OFF is immediate. And
  **"Delete conversations older than"**: Never / 30 days / 90 days / 1 year.
- When `recording` is false, show `why_not` plainly.

The approval card reads: "Turn chat history back on? Jarvis will keep your
chats, including voice, on this PC, encrypted. Nothing leaves this PC."

### 18.5 Known gaps, said plainly

- **A cloud answer is not in the history.** Only the question is. A cloud
  answer never passes through the PC's answering loop, where the answer is
  collected.
- **Voice is checked against what THIS PC heard.** `jarvis_speech.hear()`
  calls `jarvis_chat_log.note_transcript()` with every transcript it makes
  from a voice that passed the check (a hash, kept 10 minutes), so a turn
  sent with `provenance: "voice"` and those exact words is recorded as
  `voice`; any other claimed voice turn as `voice_unverified`.
- **Shared text does not go to a cloud model, on purpose.** The phone sends
  shared text as its own message before the typed one; a cloud turn
  (`cloud-one-turn.patch`) carries only the newest message, so the shared
  one is left out. That is kept: shared text is very often an email or a
  document, which rule 1 keeps on this PC. The local model sees it.
- **Checked only against a stand-in of the owner's `jarvis_hud.py`** built
  from the whole patch stack, not against the real file.

---

## 19. Automatic learning (added 2026-09-24)

**What it is.** The owner decided on 2026-09-24 (CLAUDE.md): "Jarvis learns
automatically by default. Facts about the owner and their projects, learned
from the owner's own words only (never from web pages, emails, documents,
notes or tool output), are saved without a per-fact yes, and every one is
listed in both apps with a one-tap Forget. Sensitive topics (health, money,
passwords and account details, private details about other people) still
wait for the owner's yes, unless the owner turns on 'Also remember
sensitive topics automatically', which is off by default. Turning either
setting on raises an approval card; turning it off is immediate."

Decided the same day, after the safety research: "Passwords, PINs, account
numbers and ID numbers always wait for the owner's yes, even with 'Also
remember sensitive topics automatically' on. That setting covers health,
money and the other sensitive topics only." (Check 9 below.)

The learner still **proposes** every fact into the review queue, exactly as
before (§6, `/api/memory/pending`). After each learning pass, and after each
"Remember: ...", the PC looks at what was just proposed and saves a proposal
**without a card only when every check below passes**. Everything else stays
an ordinary card, with the reason on it.

Backend: `backend/auto-learn.patch` (last in the patch order) and
`backend/jarvis_auto_learn.py` (shipped whole); a live-turn registry in
`jarvis_chat_log.py`. **Both apps have it**: desktop Brain -> Memory
(`brain/auto_learn.rs`, `auto-learn.js`), phone's Brain -> What Jarvis remembers
and Saved automatically (`net/AutoLearn.kt`, `AutoLearnPlate.kt`); `ported`
in `tools/check_parity.py`.
Every route needs the pairing token and passes the origin check.

Deleting a conversation from History does not forget facts learned from it - use Forget in Saved automatically.

### 19.1 The two settings

| setting | default | when missing | when damaged |
|---|---|---|---|
| **"Learn automatically"** (`auto`) | **on** | on (a file that never had it) | **off** (fail closed), and `why` says so |
| **"Also remember sensitive topics automatically"** (`auto_sensitive`) | **off** | off | off |

Kept in `<config folder>/auto-learning.json` (plain JSON, no fact text in
it). Turning either **on** raises ONE approval card (`learning_auto_enable`
or `learning_sensitive_enable`, both tier `ask` in `jarvis-framework.toml`;
any other tier and the route answers 503 rather than let a config line be
the owner's yes). Turning either **off** is immediate and withdraws a card
that is still waiting. A "no" on either card is never turned into a proposed
memory (`gate-outcome.patch`'s list). Only the newest card may change what
`auto_last` / `sensitive_last` say.

"Learn automatically" means something only while **background learning**
(the existing `/api/memory/learning` switch) is on. `GET
/api/memory/learning` says both; when learning is off, its `note` - and both
apps - say "Background learning is off, so nothing is saved automatically.
Start learning above to use this."

A damaged settings file reads as off, and `why` says: "the automatic
learning settings file is damaged, so nothing is saved automatically. Turn
"Learn automatically" on again to rewrite it". Turning it on (the card,
approved) writes a good file.

### 19.2 When a proposal is saved without a card

ALL of these, or it stays a card. The words in quotes are what the card's
`auto_reason` says when that check stopped it.

1. **Settings.** "Learn automatically" on, background learning on,
   `jarvis_intake.py` installed. (Off: every proposal is a card, as it always
   was, and `auto_reason` is empty.)
2. **The model is on this PC** (GUARDS L11): `OLLAMA_URL` is loopback AND the
   model's name is not an Ollama cloud model (`jarvis_router.is_remote_model`,
   e.g. `gpt-oss:120b-cloud`) - and nor is the second card's learning model.
   "the learning model is a cloud model, not one on this PC". Separately, the
   learner now **refuses to run at all** with a cloud model, not only to save.
3. **Source.** `conversation`, or `remember`. Never `gate_denial`
   ("made from an action you turned down ..."), `import:*` ("from an imported
   chat history"), `feedback_retire` or anything else.
4. **Every owner turn the learner read was seen LIVE by this PC**, in this
   conversation, typed or a verified voice transcript, and the conversation
   had not read outside text by then. The PC's record is an in-memory
   registry, written by `jarvis_chat_log.record_turn()` for **every** chat
   request whether or not chat history is on: per live user message, a hash
   of its words (never the words), its provenance, the voice check's facts,
   the conversation id, the app, and whether a tool ran in that turn. The
   newest 200 turns; a backend restart forgets them.
   - a turn it did not see arrive (re-sent or made-up history, or older than
     the registry): "from a message this PC did not see arrive ..."
   - no valid `conversation_id` on the request: "the app did not say which
     conversation this was"
   - `pasted` / `shared` / `clipboard` / `picture_caption`: "from pasted
     text" / "from shared text" / "from the clipboard" / "from words sent with
     a picture"; `unknown`: "not marked as typed or said by you";
     `voice_unverified`: "said aloud, but this PC could not check it was your
     voice"
   - a tool ran in that turn or earlier in the conversation: "the
     conversation read outside text (a tool ran)"

   **One turn that fails makes every proposal of that pass a card.** The
   model read every turn, and nothing says which turn a fact came from.
5. **Voice** (GUARDS L8) counts only when the voice check that let it in was
   `very_strict`, decided by the stronger voice model, in mode `owner`. Else:
   "said aloud, but the voice check was not at its strictest ...".
   (`jarvis_speech.py` now tells the history which model DECIDED - it used to
   pass the small model's name even when the stronger one decided.)
   **And, when the owner chose `hands_free: button_only`** (§16), only when
   the clip came from the talk button (`source: push_to_talk`, recorded
   with the transcript). A "hey Jarvis" turn - or one whose start was not
   recorded, or is not known - is a card: "said hands-free - your setting
   only trusts the talk button". Under the default, `same_as_button`,
   nothing changes. A damaged setting reads as `button_only`.
6. **No sign of outside text** in any of those turns (GUARDS L4): a link or
   web-page code (`http`, `www.`, markdown links, HTML tags, comments,
   entities) or a bare web address (`evil.example/page`, or a name ending in
   a common top-level domain such as `.com`); hidden characters - any
   character Unicode calls format, private-use or unassigned, control
   characters other than tab and line ends, variation selectors (both
   blocks), the combining grapheme joiner, the Hangul and half-width
   fillers, the Braille blank, line and paragraph separators; a run of 48+
   encoded-looking characters, whole or cut into pieces of 8+ with spaces or
   punctuation between them; email headers or a quoted reply; more than
   **600** characters; or any `injection_flags()` hit, read both as written
   and with look-alike letters folded (NFKC, then Cyrillic and Greek
   look-alikes swapped for Latin, invisible characters removed) - on the
   turns AND on the proposal: "looks like pasted text: ..." / "reads like an
   instruction to Jarvis". (Red team R4, 2026-09-24.) Said plainly: an emoji
   written with a variation selector (a red heart, for one) counts as a
   hidden character, so a message with one stays a card.
7. **Grounded** (GUARDS L5): every content word and every number of the fact
   is in those turns. "I"/"my" and "the owner"/"the owner's" count as the
   same, as do simple plurals and -s/-ed/-ing endings - but a plain word is
   not grounded by only a past or -ing form ("hated" does not ground "hat");
   a date counts when it is the real date of a relative date the owner used
   ("yesterday"). Negations ("not", "no longer") must be there word for
   word. Else: "not in your own words".
   **And the fact leaves out nothing that changed what was said** (red team
   R2, 2026-09-24). Each sentence the fact shares a word with is read for:
   a negation or change of state (not, n't, no, never, no longer, any more,
   used to, quit, stopped, gave up, former), a condition or plan (if,
   unless, would, could, should, might, maybe, perhaps, planning, thinking
   of, hope to, wish, want to), a question mark, a relation (sister,
   brother, wife, husband, partner, boss, friend, mum, dad, son, daughter,
   colleague, neighbour...), or he/she/his/her/they/them. One the fact does
   not also say makes it a card: "what you said had "used to" in it, and the
   fact leaves it out", "what you said was about your sister, and the fact
   leaves that out - it may be about someone else", "what you said was
   about "she" - someone else - and the fact does not say who", "what you
   said was a question, and the fact states it as true". A fact that says
   "the owner" from sentences with no I/me/my/we in them is a card too:
   "what you said was not about you, but the fact says it is".
8. **Never a correction** (GUARDS L6): a proposal that would replace a stored
   fact (`replaces_id`, or even `replaces` words) is always a card: "it would
   replace a fact you already have".
9. **Not sensitive**, unless "Also remember sensitive topics automatically"
   is on (GUARDS L7). **With it on**, only one narrow check runs:
   passwords, PINs, account and ID numbers, birthdays, phone numbers and email addresses still wait
   (`jarvis_sensitive.always_asks`, on the fact AND the turns it shares
   words with, the patterns alone - the model is not asked, so the switch
   adds no wait). It catches whatever the patterns put under passwords and
   account details or under ID numbers, birth dates and contact details
   (the latter category is whole: a phone number, an email address and a
   birth date wait too), anything `jarvis_router.looks_like_a_secret`
   catches, and account numbers, IBANs and sort codes, which the patterns
   otherwise count as money ("my salary is 40k" stays money, and is saved).
   The card says "a password, PIN or account number - these always wait for
   your yes" or "an ID number, birth date or contact details - these always
   wait for your yes". Said plainly: with the switch on, a password the
   patterns miss - a plain word with no password word near it, "my
   Netflix is sunflower" - is saved, because only the model would have
   caught it ("my Netflix password is sunflower" still waits).
   **With it off**, `jarvis_sensitive.py` looks at the fact AND at the
   turns it shares words with, in two layers; either one saying "sensitive"
   makes a card:
   - **patterns** (no model): word lists for health, money, passwords and
     account details, ID numbers and birth dates, addresses and routines,
     religion, politics, sexuality, ethnicity, immigration and the law, in
     English, Spanish, French, German, Italian, Portuguese, Dutch and Polish
     (accents ignored); the shapes of codes near a lock word, "<service> is
     <token>", card, account and ID numbers, money amounts, postcodes and
     street addresses; and **another person** - a relation word, a common
     first name, a title or "he"/"she" (a famous name as a taste, a pet's
     name and the owner's own name are not). Since 2026-09-26 (the owner's
     decision after the approvals audit) another person on their own is
     NOT a card: "my sister likes jazz" goes to the model below, told that
     an everyday fact about someone is not sensitive, and only its clear
     "not sensitive" saves it. Anything private about them still is a card
     whatever the model says: their health, money, address or contact
     details (their own topics), a break-up, a death, a secret, a debt or
     trouble ("my brother owes me money", the private-life words),
     "<Name>'s address / salary / diagnosis ...", and passwords, PINs,
     account and ID numbers. `patterns()` still sees the other person, but
     since the owner's later decision of 2026-09-26 ("treated as normal
     everywhere") `topic()` calls an everyday fact about someone normal
     too: a recalled "my sister likes jazz" may be read aloud and does not
     make a web search ask first (section 23). Their private details stay
     sensitive there as well;
   - **the learner's own local model**, asked only when the patterns find
     nothing (or only another person, above), for a one-line JSON verdict. Its "unsure", an answer that is
     not that JSON, no answer within 8 seconds, Ollama not reachable, no
     model known, or a model that is not on this PC or is a cloud model: a
     card (fail closed).

   The reason is one per topic: "about health, a sensitive topic", "about
   money, ...", "about passwords or account details, ...", "about ID
   numbers, birth dates or contact details, ...", "about religion, ..."
   (or "politics or union membership", "sexuality or sex life",
   "ethnicity", "immigration status", "arrests, courts or a criminal
   record"), "about where someone can be found, ...", "about another
   person, ..."; "about someone else's health, ..." when another person is
   in the same sentence and the sentence is not about the owner ("I came
   out to my parents" is "about sexuality or sex life"); and, from the
   model, "the local model was not sure it is free of sensitive topics" or
   why it gave no answer. The general words for a secret ("password", "PIN",
   "API key", "2FA") count only with the secret or a give-away habit next to
   them ("I keep the API key in an env var" is not a card).

   The numbers, patterns only (no model runs where they were measured):
   - **fair, measured before round 2** on the first held-out set (963 lines
     written by someone who never saw the lists): 86.8% of sensitive lines
     caught (credentials 94%, health 81%, money 85%, identity 95%, special
     83%, location 72%, other people 99%), 15.3% of harmless lines flagged;
   - **after round 2**, which used those same lines as training material
     (now `backend/sensitive_cases/heldout1.jsonl`, no longer held out):
     100% caught, 0.6% flagged - fitted to those lines, so not a fair test;
   - **new wording** written by the round-2 author after the rules and
     measured once before any change for it: 81.6% caught in a first batch
     (79.8% before round 2) and 90.1% in a second (87.1% before), with
     9.0% and 0% of harmless lines flagged (13.4% and 7.6% before). Same
     author as the rules, so these flatter too;
   - the development set (`dev.jsonl`): still all 777 lines in the eight
     languages caught, none of its 259 plainly harmless lines flagged.

   The fair test is a second held-out set, written by someone else and
   never used for tuning (983 lines): the patterns alone catch **84.8%**
   of its sensitive lines and flag **13.9%** of its harmless ones (round 1:
   78.0% / 18.0%; the old word list: 43.4% / 23.6%). What the
   patterns cannot catch, the local model has to: other languages, slang
   and euphemisms they have not seen, unlisted names, a password that looks
   like a word with no password word next to it. The model layer has not
   been measured with a real model yet (`backend/README.md`, "The
   sensitive-topic check", has the command).

**"Remember: ..."** is saved without a card only with a **colon**, on **one
line**, at most 600 characters, from a typed or verified-voice live turn,
with background learning and "Learn automatically" both on, and nothing
sensitive or instruction-like in it (GUARDS L3). No model writes it, so check
2 does not apply - though the sensitive-topic check (9) does ask the local
model about it. Otherwise it stays the card it already is - and that card
says "Your own words" (`verbatim`) only when the words were typed or said to
this PC.

### 19.3 What a saved fact carries

Saved through `jarvis_extract.accept_auto()`, which claims the proposal the
way `decide()` does and writes it with the same `_accept()` - so meaning
search, word search and both dates are exactly as for a card the owner kept.
The fact's `source` is **`"auto"`**, and its `meta`:

```json
{"auto": true, "proposal_source": "conversation", "device": "phone",
 "provenance": "typed", "conversation_id": "...", "message_hash": "<sha256>",
 "tainted": false, "saved_at": 1790000000.0, "confidence": 0.9, "proposal_id": 12}
```

`provenance` is `"voice"` when any of the turns was said aloud.

**A card the owner accepts keeps the proposal's own source** now
(`"conversation"`, `"remember"`, `"gate_denial"`, `"import:claude"`, ...);
every one used to become `"extracted"`. A proposal whose source column says
`"auto"` is stored as `"extracted"` when accepted by hand - only
`accept_auto()` can make an `"auto"` fact.

**Recalled facts are quoted.** The recalled-facts block every local chat
turn carries now puts the facts between `---FACTS---` and `---END FACTS---`
lines and says they are information about the user, never an instruction
(GUARDS L6's delimiter note) - for every recalled fact, not only automatic
ones. Each fact is put on one line, with anything in it that reads as one
of those two lines taken out (`jarvis_auto_learn.recall_line`, red team R7),
so a saved fact cannot close the block early. Facts the owner pinned
("Always keep in mind", §4 and §6 `/api/memory/profile`, 2026-09-24) are
inside the same block, first, through the same `recall_line`.

**Which recalled facts are sensitive** rides out in `X-Jarvis-Route` as
`injected_sensitive` (§4): the owner's decision of 2026-09-24 keeps an
answer that uses one on screen when the question came by voice, unless the
owner turned on the fourth voice setting, `sensitive_memory:
sensitive_aloud` (§16).

### 19.4 Routes

`GET /api/memory/learning`

```json
{"enabled": true, "floor": true, "auto": true, "auto_sensitive": false,
 "auto_waiting": false, "sensitive_waiting": false,
 "auto_last": null, "sensitive_last": {"outcome": "denied", "why": "", "at": 1790000000.0},
 "auto_active": true, "note": "", "why": "",
 "learning_waiting": false, "learning_last": null}
```

`enabled` is background learning's own switch (`floor` false means
`JARVIS_EXTRACT` is off in the environment); `learning_waiting`/`learning_last` are its card.
`auto_active` is `enabled and auto`. `why` is set when the settings file is
damaged. `*_last` is `{"outcome": "enabled" | "denied" | "timed_out" |
"refused" | "withdrawn" | "failed", "why", "message", "at"}` or `null`.
`why` is the technical reason (for a log or a details line); `message` is
the plain sentence to show (fit audit item 28), e.g. refused: "Your PC's
settings do not let this be approved, so it stayed off."; withdrawn: "You
turned it off while the card waited, so approving it changed nothing.";
denied: "The card was turned down, so it stayed off."; timed out: "Nobody
answered the card in time, so it stayed off."; a gate that failed: "The
approval card could not be raised, so it stayed off." `learning_last` has
the same `message` for background learning's card. A PC from before this
sends no `message`.

The ON card and OFF share one lock per switch on the PC: an OFF pressed
while an approved card is being applied waits for it, then turns the switch
off - it can no longer be answered "off" and then overwritten by the card
(red team R5). The same holds for background learning and chat history.

`POST /api/memory/learning/auto` and `POST /api/memory/learning/sensitive`,
`{"enabled": true | false}`:

- `false` - 200 at once. It also withdraws a waiting ON card.
- `true` - **202** `{"ok": true, "waiting": true, "message", ...}` and ONE
  approval card; on only when approved. Already on: 200, no card. A card
  already waiting: 202, no second card. Tier other than `ask`: **503**.
- Anything else - `400`.

Every reply carries the `GET /api/memory/learning` fields except `enabled`,
`floor`, `auto_active` and `note`.

`GET /api/memory/auto?limit=30&before=<saved_at>`

```json
{"facts": [{"id": 41, "text": "The owner is learning Kotlin",
            "saved_at": 1790000300, "provenance": "typed", "device": "phone"}],
 "auto": true, "auto_sensitive": false}
```

Facts saved automatically that are still current (Forget retires them),
newest first. `limit` 1-100, default 30. `before` pages to older ones: pass
the last row's `saved_at`. It may carry a fraction; it is floored, and means
"strictly older seconds". **A page never splits a second** - rows sharing
the last row's second come with it - so nothing is skipped or repeated.
`provenance` is `"typed"` or `"voice"` (show a small "said aloud" mark).
A fact the owner has said again since it was saved also carries
`"said_again": {"count": 3, "last": 1790000900}` (memory idea 3, §34);
both apps add "said again 3 times" to the row's small line. No field when
it was never said again.

`POST /api/memory/forget {"id": <fact id>}` - unchanged (§6): one fact per
request, retired, not deleted. Now **also called by the phone**, for this
list; both apps hold it on a stale link.

`POST /api/memory/erase {"id": <fact id>}` - "Erase the words" (the owner's
decision, 2026-09-24; §6): the fact's words wiped for good, its dates kept.
Offered beside Forget on every row of this list in both apps, asked about
first in the same words, held on a stale link. An erased fact is no longer
current, so it leaves this list.

`/api/memory/pending` rows gain `auto_reason` (§6's row table) and
`verbatim` is narrowed (above).

Event **`memory_saved`**: data is flat, `{"ids": [<fact id>, ...]}` - ids
only, never the words (GUARDS L10). One event per pass or per "Remember:".

If `jarvis_auto_learn.py` is not installed: `GET /api/memory/learning`,
`GET /api/memory/auto` and both POSTs answer **503** `{"available": false,
"error": "automatic learning is not installed on this PC, so every fact
waits for your yes", "reason"}` - and nothing is ever saved without a card.

### 19.5 What each app shows (both apps - parity rule)

Where the learning switch lives today (desktop: Brain -> Memory; phone: Brain
-> "What Jarvis remembers"):

- **"Learn automatically"**, with: "Jarvis saves facts about you and your
  projects from what you type or say to it - never from web pages, emails,
  documents or notes. You can forget any of them here."
- **"Also remember sensitive topics automatically"** (off by default), with:
  "Health, money, and private details about other people. When this is
  off, Jarvis asks you first. Passwords, PINs, account and ID numbers, birthdays, phone numbers and email addresses always
  wait for your yes." (Changed 2026-09-24 with the owner's decision; it
  used to list "passwords and account details" among what the switch
  covers.)
- Both: ON raises the card and shows "Waiting for your approval" (from
  `auto_waiting` / `sensitive_waiting`, and the card in the approval queue -
  including one raised on the other device); OFF immediate; ON held on a
  stale link.
- **"Saved automatically"**: newest first, the fact, when, a small "said
  aloud" mark for voice, and a one-tap **Forget** on each (with the same
  confirm as the desktop's Forget today). "Load older". Beside Forget,
  **"Erase the words"** (2026-09-24, §6 `/api/memory/erase`). First on each
  row, **Pin** / **Unpin** ("Always keep in mind", 2026-09-24, §6
  `/api/memory/profile`): no confirm, held on a stale link, shown once the
  PC has said which facts are pinned. Under the list, in both apps, the
  section **"Always keep in mind"**: "Jarvis reads these with every
  question, word for word. Keep it short.", "N of 1,200 characters used",
  and each pinned fact with Unpin.
- On `memory_saved`: a quiet line, "Jarvis remembered 2 things". Never a
  pop-up; never the fact's text in a notification. Since 2026-09-25 it
  opens **the facts themselves** - "Remembered just now", their words read
  by id from `GET /api/memory/used` (§6) only then - each with Forget (the
  same confirm; the desktop adds "Erase the words"), then "Show everything
  saved automatically" for the whole list. Hidden like the other memory
  lists. Desktop: Brain -> Memory (`brain.js` `openSavedList`); phone:
  Brain (`MemoryCountsPlate.kt`, `JarvisRuntime.autoRememberedIds`).
- Cards that stayed cards show `auto_reason` as one quiet line.

The approval cards read "Turn on automatic learning. ..." and "Also remember
sensitive topics automatically. ..." (`jarvis_auto_learn.AUTO_CARD`,
`SENSITIVE_CARD`); both say nothing leaves this PC and what a "no" means.
The sensitive one also says "Passwords, PINs, account and ID numbers, birthdays, phone numbers and email addresses always
wait for your yes, even with this on."

### 19.6 Known gaps, said plainly

- **Strict on purpose, so many real facts stay cards.** A fact the model
  rewords ("prefers" for "likes better") is not grounded; a conversation
  with one pasted message, one shared text, one tool run or one voice turn at
  the balanced voice setting makes every later pass of that conversation
  cards; and the sensitive-topic check flags anything private about another
  person (an everyday fact about someone saves since 2026-09-26, but only
  on the local model's clear "no"), and asks the local model about
  everything else (a card when it is unsure
  or does not answer in 8 seconds).
- **The registry is in memory.** After a backend restart, the rest of an
  ongoing conversation is cards (the earlier turns are "not seen arrive"). An
  app that sends no `conversation_id` gets cards only.
- **Voice** is saved automatically only at `very_strict` with the stronger
  voice model installed and in mode `owner`. The voice check cannot tell
  the owner's voice from a recording or a copy of it: under the default,
  a recording played near a "hey Jarvis" microphone could have a fact
  saved. `hands_free: button_only` (§16) closes that path; the talk button
  still trusts the voice alone.
- **The attack phrasings.** The memory audit's sensitive-topic red-team
  script holds 38 phrasings (the brief said 42); all 38, the auto-learning
  red team's list (lupus, the alarm code, the Netflix password, "Estoy
  embarazada", "Ich habe Krebs", ...) and the memory-safety research's
  political and ethnicity cases are flagged by the patterns alone, and
  `backend/test_sensitive.py` carries them word for word.
- **Checked only against stand-ins.** `auto-learn.patch` was applied to
  stand-ins of `jarvis_hud.py`, `jarvis_gate.py` and `jarvis_extract.py`
  built from the whole patch stack, and `accept_auto()` / `_accept()` were
  run lifted from that stand-in against a real memory store - never against
  the owner's real files, and nothing has run on the owner's PC.
- **The meaning check is a word list, not understanding.** Check 7 catches
  a fact that drops one of its listed words. A change of meaning carried by
  a word that is not on the list can still get through. It also makes more
  cards than strictly needed: "I love Radiohead, they are great" -> "Owner
  loves Radiohead" is a card (the "they").
- **Deleting a conversation from History does not forget facts learned from
  it** - use Forget in Saved automatically.

---

## 20. Graphics cards and the three setups (added 2026-09-25)

`backend/hardware.patch`, `backend/jarvis_hardware.py` (finding the cards,
the steps, making a model, measuring) and `backend/jarvis_profiles.py` (the
arithmetic and the words, no I/O). The design is
[`HARDWARE-PROFILES.md`](HARDWARE-PROFILES.md). **Both apps call all four
routes.** The desktop: Settings, "Hardware and models" (`hardware-panel.js`,
`hardware.rs`: `get_hardware`, `apply_hardware`, `hardware_step`,
`measure_hardware`, settings window only). The phone: Brain, "Hardware"
(`HardwarePlate.kt`, `net/Hardware.kt`). `tools/check_parity.py` records all
four as `ported`.

| Route | Body | Answers | Notes |
|---|---|---|---|
| `GET /api/hardware` | - | 200 `status()` (below); 503 `{"available": false, "error"}` without `jarvis_hardware.py` | Token + origin. Reads only: loads, starts and changes nothing. Card names and hardware ids; never a token. |
| `POST /api/hardware/apply` | `{"preset": "fast" \| "smart" \| "features" \| null}` | 200 `{"ok", "chosen", "message", "applying"}`; 400 an unknown setup or no `preset` field; 409 the setup does not fit these cards; 503 no card Ollama can use | Remembers the owner's choice (`hardware-choice.json` beside the other settings) and returns its steps. **It changes no model and no setting.** `null` forgets the choice. If the extra features move (to another card, or into the everyday Ollama), the main second-card switch goes OFF - the safe direction - and the `message` says so; its step asks again. |
| `POST /api/hardware/create` | `{"name": "jarvis-chat" \| "jarvis-long" \| "jarvis-vision"}` | 200 `{"ok", "pending": true, "message"}` - a card is up, nothing made; 400 another name; 409 no setup chosen, the base model not downloaded, or a card already waits; 503 Ollama not answering, or `models_create` not tier `ask` | ONE approval card, action **`models_create`** (tier `ask`; the shipped toml has the line, and a toml without it asks too). The card shows the Modelfile word for word. On approval, Ollama on 127.0.0.1 makes the model from a base already downloaded (`POST /api/create` with `from`, `parameters`, `system`) - never a download. `jarvis-primary` is never made over. |
| `POST /api/hardware/measure` | `{}` | 200 `{"ok", "running": true, "message"}`; 409 one is already running | Times each model of the chosen setup (or today's chat model) with `jarvis_speed.measure()`, reads how much is on the card (`/api/ps`) and llama.cpp's own count (`offloaded N/M layers`), and keeps the result in `hardware-measured.json`. It LOADS each model once. A model partly on the processor makes that setup use the next smaller size from then on - its "make" step opens again. |

**Steps.** Choosing a setup lists, in order: one download per base model
not on the PC (the existing `POST /api/models/install` card), one "make"
per tuned model (`/api/hardware/create`), the switch (the existing
`POST /api/models/switch` card), the second-card switches the setup uses
(the existing `POST /api/second-card` cards, main switch first), and the
one PowerShell line. Each step is `{"id", "kind", "title", "detail",
"route", "body", "state", "done", "waiting"}`; `state` is `done`, `next`,
`waiting` (its card is up) or `later`. **An app asks only for the step whose
state is `next`, by posting that step's own `body` to that step's own
`route`, read from a fresh `GET` - never a route or body of its own - and
only to these four routes:** `/api/models/install`, `/api/models/switch`,
`/api/hardware/create`, `/api/second-card` (`hardware.rs` `step_request`,
`Hardware.stepRequest`). There is no request that asks for more than one
step. A step asked for shows as waiting for 180 seconds even when the PC
cannot see its card (a download's or switch's card is shaped by the owner's
own `jarvis_gate`), so one tap is one card.

**`status()`** - the real answers are in
`jarvis-desktop/tests/fixtures/hardware-cases.json` (the phone's copy is
byte for byte the same): `today_one_card`, `planned_pair`,
`chosen_first_step`, `chosen_halfway`, `create_waiting`, `amd_vulkan`,
`no_ollama_log`, `card_dropped`, and the POST answers `post_*`. Build
against that file, not this summary.

```
{"available": true,
 "found": str,                     every card, and which Ollama can use
 "sources": {"ollama_log", "nvidia_smi", "registry"},
 "cards": [{"key", "name", "total_gb", "free_gb", "vendor", "route", "generation",
            "monitor": bool|null, "uuid", "used": bool, "why_unused": str|null,
            "sources": [str], "desktop_share_gb", "desktop_share_how",
            "conversation_format": "q8_0"|"f16"|null, "best_effort": str|null,
            "chat_first": bool, "words": str,
            "health": {"temp_c", "power_w", "power_limit_w", "fan_percent",
                       "load_percent", "hot_slowdown": bool|null} | null,
            "health_words": str|null}],
 "chat_card_why": str|null,        why chat goes on the card it does (two cards)
 "gap_gb": 0.75,                   the owner's decision 1
 "now": {"preset", "label", "model", "context", "format", "on_card_percent",
         "bar": {...}|null, "words"},
 "presets": [{"id", "name", "summary", "chat": role|null, "long": role|{"same_as_chat",
              "context", "words"}|null, "pictures": role|null, "off": [str], "notes": [str],
              "best_effort": bool, "best_effort_why": [str], "ollamas": 1|2,
              "bars": [{"card", "card_key", "models_gib", "fixed_gib", "used_gib",
                        "total_gib", "blocks", "words"}],
              "details": [str], "measured": bool, "measured_words": str,
              "recommended": bool, "recommended_why": str|null,
              "command": {"line", "undo", "settings"}}],
 "recommended": id, "chosen": id|null, "chosen_stale": str|null,
 "applying": {"preset", "name", "chosen_at", "steps": [step], "next", "done",
              "restart_pending": bool|null, "undo"} | null,
 "command": {"for", "line", "undo", "check", "restart_pending"},
 "measure": {"state": "idle"|"running"|"done"|"failed", "why", "at", "last"},
 "last": {"name", "outcome", "why", "at"} | null,     how the last "make" card ended
 "pending": [tuned names with a card waiting],
 "test_later": [{"model", "why"}]}
role = {"model", "size", "context", "context_words", "format", "card", "card_key",
        "mode": "own"|"beside"|"swap"|"turns", "need_gib", "creates", "words"}
```

**Every card's health** (the feasibility audit's I12, 2026-09-26; before
the RTX 2060 goes in). `health` is each card's heat, power (drawn and its
limit, in watts), fan and load right now, and `hot_slowdown` is the
driver's own "slowing down because it is hot" (`null` when an older driver
does not say). It comes from a second `nvidia-smi --query-gpu` of its own
(`jarvis_hardware.HEALTH_FIELDS`; an older driver's
`clocks_throttle_reasons`, then no reasons at all, are tried in turn, so a
refused field can never cost the card list), read at most every 5 seconds,
and matched to its card by the `GPU-...` id. `health_words` is the same in
one line - "84 °C, using 247 of 250 watts, fan at 78%, 99% busy. It is
slowing itself down because it is hot." - and both apps show it under the
card as "Now: ..." (desktop Settings -> Hardware and models; phone Brain ->
Hardware). A card `nvidia-smi` does not see (AMD, Intel) has `null`. Read on
this PC only; nothing is sent anywhere, and there is no "card is hot"
notification (the feasibility audit's Overwhelm guardrail). The desktop's
widget reads `nvidia-smi` itself every 3 seconds (`commands.rs`
`parse_gpu_lines`): since 2026-09-26 it reads EVERY card, not only the
first line, lists each on its own line once there are two, and its
collapsed glance shows the hottest card's temperature. Field names and the
thermal-slowdown values ("Active" / "Not Active") are from NVIDIA's
documentation, not checked on the owner's driver.

**Not a model catalogue** (CLAUDE.md). The phone gets three setups worked
out on the PC for the PC's own cards, as words. It shows no list of models
that could be installed, no search and no picker, and it cannot compose a
setup; the only model names it ever posts are the ones in the chosen
setup's own steps.

**The one line.** `command.line` is one PowerShell line (Windows PowerShell
5.1-safe: only `[Environment]::SetEnvironmentVariable(..., 'User')` and one
`Write-Host`, only `OLLAMA_KV_CACHE_TYPE`, `OLLAMA_KEEP_ALIVE`,
`CUDA_VISIBLE_DEVICES` (two cards only), `OLLAMA_VULKAN` (all-NVIDIA PCs
only) and `LLAMA_ARG_FIT_TARGET` (768 MiB - the owner's 0.75 GB gap), each
value checked against a fixed pattern). `undo` puts each back the way it was
when the setup was chosen; `check` only prints. The desktop shows them with
Copy; the phone shows them to read. `restart_pending: true` means the
Windows user settings hold a value Ollama did not start with (its
"server config" log line) - "restart Ollama".

**Known gaps, said plainly.** Nothing here has run on a real graphics card
or a real Ollama: Ollama's log lines, `nvidia-smi` and the registry were
replayed in the shapes the design read from source, with made-up values.
Whether `LLAMA_ARG_FIT_TARGET` reaches llama.cpp through Ollama as a single
MiB number has not been checked; if it does not, models may fail to load
until the undo line is run. Ollama's `/api/create` with `from` and
`parameters` was not run either.

---

## 21. Timers, alarms, reminders and the to-do list (added 2026-09-25)

The owner's decisions of 2026-09-25 (`CLAUDE.md`): timers, reminders and ONE
shared scheduler come first; a timer or a one-time reminder needs no approval
card, anything that repeats asks once with a card that lists the next run
times; simple commands like timers are answered without the AI model.

**Changed 2026-09-26** (the owner's decision after the approvals audit,
`docs/APPROVALS-AUDIT-2026-09-26.md`): a plain repeating reminder or alarm,
and the standby schedule, need **no card**. Only the owner's own words or
taps can set one, and deleting is instant. They are set up at once, and
the answer says the next three times (`jarvis_schedule.repeat_set_words`):
"Reminder set up, every weekday (Monday to Friday) at 07:00. Next: 07:00 on
Monday, 07:00 on Tuesday and 07:00 on Wednesday. Delete it under Coming up
to stop it." Coming up shows each one's next time. The morning briefing
(section 22) and "tell me when" (section 30) keep their ONE card: they read
email or the calendar. A kind added later asks by default
(`Kind.plain_repeat` is off unless it says so).

`backend/schedule.patch`, `backend/jarvis_schedule.py` (the scheduler) and
`backend/jarvis_quick.py` (the answers without the model), and since
2026-09-25 the first kind that plugs in, the standby schedule
(`backend/jarvis_standby_schedule.py`, 21.8). **Both apps call
all three routes.** The desktop: the Brain's Work tab, "Coming up"
(`coming-up.js`, `brain/schedule.rs`: `brain_schedule`,
`brain_schedule_act`, `brain_schedule_add_todo`, Brain window only), and a
Windows toast when a job goes off (`stream.rs` -> `toast_fired`). The phone:
Brain, "Coming up" (`ComingUpPlate.kt`, `net/Schedule.kt`), and a
notification when a job goes off (`JarvisRuntime.onScheduleEvent` ->
`ScheduleNotifier`). `tools/check_parity.py` records all three as `ported`.

### 21.1 The PC is the clock

Every job lives in `schedule.db` in the Jarvis settings folder (beside
`memory.db`) and goes off **on the PC, by the PC's own clock** - its local
time, with both daylight-saving changes handled (a daily 07:00 stays 07:00;
a time in the hour the clocks skip goes off when they jump; a time that
happens twice goes off once, the first time). The apps show what goes off
**while they are connected**. The phone sets no alarm of its own and asks
for no exact-alarm permission: a reminder due while the phone is off, or out
of reach of the PC, is not shown on the phone then - it is still on the
list, and the PC still shows its toast. A job found overdue after the PC was
off or asleep goes off **once**, late, and says `missed at 07:00`; a
repeating job then moves to its next time - never once per missed time.

### 21.2 Routes

| Route | Body | Answers | Notes |
|---|---|---|---|
| `GET /api/schedule` | - | 200 `{"available": true, "now", "tz", "jobs": [job], "todo": [job], "went_off": [job], "lists": [{"name", "title", "open"}], "running", "limits"}`; 503 `{"available": false, "error": <exception name>}` without `jarvis_schedule.py` | Token + origin. `jobs`: timers, alarms, reminders and repeating jobs that are active, paused or waiting for a card, soonest first. `todo`: the open to-do items of every list, oldest first (each with its `list`). Since 2026-09-25 (21.9): `went_off` - timers, alarms and reminders that went off in the last hour and are not snoozed, newest first, at most five; `lists` - the named lists with open items. An older PC sends neither. |
| `GET /api/schedule?id=<id>` | - | 200 `{"available": true, "job": job}`; 404 `{"reason": "no_such_job"}` | ONE job - also one that went off in the last day (kept 24 hours). How an app reads a notification's words. |
| `POST /api/schedule/add` | `{"kind": "todo", "text", "list"?}` (`list`: a named list, 21.9) · `{"kind": "timer", "seconds", "text"?}` · `{"kind": "alarm" \| "reminder", "at": <epoch seconds>, "text"?}` · `{"kind": "alarm" \| "reminder", "repeat": rule, "text"?}` | 200 `{"ok": true, "job"}` - since 2026-09-26 also for a plain repeating alarm or reminder and the standby schedule, with `"waiting": false` and `"said"` naming the next times; **202** `{"ok": true, "waiting": true, "job", "said"}` for a repeat that waits for its card (a briefing); 400 `{"ok": false, "error": <sentence>}`; 409 a list is full | No card for anything that goes off once, and (2026-09-26) none for a plain repeating alarm, reminder or standby schedule. A repeating briefing or "tell me when" raises ONE card and is set up only on its yes. Both apps add only a to-do item here, and (since 2026-09-25) a morning briefing that repeats - `{"kind": "briefing", "repeat": rule}`, section 22; timers and reminders are said or typed to Jarvis. |
| `POST /api/schedule/act` | `{"id", "do": "pause" \| "resume" \| "delete" \| "done" \| "add_time" \| "snooze", "seconds"?}` · `{"do": "clear_list", "list", "count"}` | 200 `{"ok": true, "id", "said"}` (`snooze` adds `"job"`: the copy, and `"already": true` when it was snoozed already); 404 `{"reason": "no_such_job"}`; 409 not possible for that job (`done` on a timer, pause on a to-do, time below nothing, snooze on something that has not gone off); 400 anything else | ONE job, at once, no card - it only makes things quieter, or (snooze) sets the same thing to go off once more. **No "delete all"**: `id` must be one job id (`s` and ten hex digits). The one other form is `clear_list` (21.9): every item on ONE named list, only with the `count` the app showed, never the to-do list. Both apps hold every one on a stale link. Deleting a repeat whose card is still up withdraws it: approving that card then sets nothing up. |

A `job`:

```
{"id": "s0123456789", "kind": "timer"|"alarm"|"reminder"|"todo"|"standby"|<a later kind>,
 "text": str,                     the owner's own words ("" for a plain timer or alarm)
 "state": "active"|"paused"|"waiting"|"fired"|"done",
 "due": epoch|null, "left": seconds (active, or a paused timer), "when": "07:00 tomorrow",
 "duration": seconds (timers), "repeats": bool,
 "rule": {...}, "repeat": "every weekday (Monday to Friday) at 07:00", "next": [3 epochs],
 "card": "Waiting for your yes on the approval card." (waiting),
 "fired_at", "late": bool, "missed": "missed at 07:00",
 "went_off_at": "07:00",          when it last went off, by the PC's clock (21.9)
 "list": "shopping",              a to-do item's named list; "" is the to-do list (21.9)
 "snoozed": true,                 a snoozed copy of something that went off (21.9)
 "lock_screen": "Jarvis: a reminder is due.",   the kind's words, never the job's
 "notify": false,                 only for a kind that tells nobody (the standby schedule)
 "note": "Went on standby at 01:00.",   a kind's line about how it last went (21.8)
 "urgent", "watches", "alert", "alert_at",   a "tell me when" only (section 30)
 "created", "source": "quick"|"tool"|"app"}
```

`rule` is one of `{"every": "day", "at": "HH:MM"}`, `{"every": "weekday",
"at"}`, `{"every": "week", "at", "days": [0-6, 0 = Monday]}`, `{"every":
"hours", "hours": N, "start": epoch}` (N at least 1). Limits: 300
characters of words, 100 timers and reminders, 300 open to-do items, a
timer up to 24 hours, a time up to a year ahead - each said in a sentence
when reached.

### 21.3 The card for a repeat that reads (the briefing, "tell me when")

Since 2026-09-26 only the repeats that read email or the calendar have this
card: a repeating morning briefing and "tell me when". A plain repeating
alarm or reminder and the standby schedule are set up at once (above) and
do not read this action's tier. The example below is what the card looked
like for a repeating reminder until then; a briefing's card has the same
shape.

Action **`schedule_repeat`**, tier `ask` (the shipped toml has the line; a
toml without it asks too; any other tier is refused and nothing is set up -
a config line is not the owner's yes). The card reads, for example:

```
Set up a repeating reminder.

What: take my pills
When: every weekday (Monday to Friday) at 07:00.

The next three times it will go off:
  - Monday 28 September at 07:00
  - Tuesday 29 September at 07:00
  - Wednesday 30 September at 07:00

It runs on this PC, by this PC's clock. It goes off on both apps while they
are connected. Nothing is sent anywhere.
Stopping or deleting it is immediate, from either app.

If you say no: nothing is set up.
```

Its notice (the lock screen's words) comes from `jarvis_gate`'s table like
every other card: since 2026-09-26 "sets up a morning briefing, which reads
your calendar and email if they are set up, or a \"tell me when\", which looks
at your own mail server or Home Assistant each time; the card says exactly
what each run reads, what it finds goes only to your own apps, and deleting
it is immediate" (`asks-first.patch`; it said "setting it up sends nothing
anywhere" for a few hours on 2026-09-26, which contradicted a "tell me when"
card's own "How:" line; before it, `briefing.patch`
said "... - a reminder, an alarm, a morning briefing or a standby schedule
...", and `schedule.patch` alone "sets up a reminder, an alarm or a standby
schedule that repeats, on this PC ..."). A briefing's card replaces the "It runs on this
PC... Nothing is sent anywhere." paragraph with its own lines on what each
run reads (section 22.3). Denied, timed out
or refused: the job is removed, and a `schedule` event says the list
changed. A "no" to it proposes no standing rule (`_NO_RULE_FROM_DENIAL`):
the owner asked for it.

### 21.4 The event

`schedule`: `{"id", "kind", "state": "fired" | "changed", "late"?: bool,
"notify"?: false}` - **ids and the kind only, never the words**
(ARCHITECTURE section 6). `"notify": false` (since 2026-09-25) marks a kind
that tells nobody - the standby schedule at 01:00 - and then neither app
shows a toast or a notification; both still read Coming up again.
`"fired"` is a job going off; `"changed"` is the list changing (added,
paused, deleted, a card decided). Both apps read Coming up again on it.
Since 2026-09-25 there is also `"matched"` - a "tell me when" that
happened, `{"id", "kind": "tellme", "state": "matched", "urgent"}`
(section 30) - and an ALARM going off keeps ringing until seen in both
apps (30.5). On `"fired"`:

- **Desktop**: reads the job by id and shows a Windows toast - title "Timer
  done", "Alarm", "Reminder" or "To-do", and the words (or "The pasta timer
  is done."), with "(missed at 07:00 - the PC was off or asleep.)" when it
  was late. While **App lock** is on, or the private lists are hidden
  ("Windows Hello for memory lists and chat history"), the toast says only
  the kind's lock-screen words. Shown once per job going off, even when a
  reconnect replays the event - and, since 2026-09-26, even after only the
  desktop app restarts: the last event id is written at once on every
  `schedule` event and when the app exits, and a job that could not be read
  is remembered by its event id.
- **Phone**: the same words as a notification on the approval channel. Its
  lock-screen version is always only the kind's words ("Jarvis: a reminder
  is due."); while App lock or "Hide memory lists and chat history" is on,
  the notification itself says only that too. Each job's notification is
  tagged with its id, so it is the same one after the app restarts, and a
  new one never replaces another.
- **Heard late** (the owner's decision of 2026-09-26): a job that went off
  more than **10 minutes** before the app heard of it (the phone was out of
  reach, an app restarted) does not ring. Both apps show a silent notice
  instead - "Missed at 07:00." and then the usual words (the PC's
  `went_off_at`), with no Snooze.
- **Answered elsewhere**: on `"changed"` for a timer, alarm or reminder
  (snoozed, deleted or done on the PC, by voice or in Coming up) the phone
  takes that job's notification away, ringing or not, and the desktop takes
  its "went off" toast away (tagged with the job id; a looping alarm stops -
  `winrt_toast.rs` `remove_fired`). A "tell me when" match's stays: its job
  ends the moment it matched.

### 21.5 Answered without the model - `/api/chat`

Before a chat turn can reach the model, `jarvis_quick.answer_turn` tries a
small fixed grammar on the newest message. **English only.** It must match
the WHOLE sentence (after "please", "Jarvis," and the like are taken off);
anything else - or anything unclear - goes to the model exactly as before.
What it understands:

| | Examples |
|---|---|
| Timers | "set a timer for 10 minutes", "10 minute timer", "timer for 1h30", "set a pasta timer for 12 minutes", "cancel the timer", "cancel the pasta timer", "pause / resume the timer", "add 5 minutes to the timer", "5 more minutes" (only while a timer runs), "take 2 minutes off the timer", "how long is left" |
| Alarms | "set an alarm for 7" (the next 7 o'clock), "alarm at 7:30am", "wake me up at 6", "set an alarm for tomorrow at 6" (an alarm on another day: the morning), "cancel my 7am alarm", "what alarms do I have" |
| Reminders | "remind me to call Mum at 6", "remind me in 20 minutes to check the oven", "remind me tomorrow to call the bank" (no time: 09:00, and the reply says so), "remind me on Friday at 5pm to pay rent", "remind me every weekday at 7 to take my pills" (a card), "remind me to stretch every 2 hours" (a card) |
| To-do list | "add milk to my to-do list", "what's on my to-do list", "mark milk as done", "tick off milk", "remove milk from my to-do list" |
| Named lists (21.9) | "add milk to the shopping list", "add milk, eggs and bread to the shopping list", "what's on my shopping list", "cross milk off the shopping list", "remove eggs from the shopping list", "what lists do I have", "clear the shopping list" (changes nothing: it points to the app) |
| Snooze (21.9) | "snooze", "snooze 5 minutes", "snooze the alarm", "remind me again in 10 minutes" |
| "Cancel that" (21.9) | "cancel that", "never mind", "undo", "delete that reminder", "no, cancel that alarm" |
| Morning briefing | "brief me now", "brief me every weekday at 7", "stop my briefing" - section 22.5 |
| "What did I miss?" (22.9) | "what did I miss", "did I miss anything", "catch me up", "what's new" |

"cancel all timers", "clear my to-do list" and the like are answered
"Jarvis does not clear everything at once" and change nothing. Two timers
and "cancel the timer": it asks which, and cancels nothing.

**Only the owner's own words act**: the newest message tagged `typed` or
`voice`, with no app system message and no Share or clipboard message sent
with it, and no picture. Anything else goes to the model. A "Hey Jarvis"
turn is fine either way: setting a reminder is an action the owner asked
for, not a fact being saved.

**The answer** is one short sentence ("Timer set for 10 minutes.",
"Reminder set for 18:00 today." - a reminder's words are not repeated back)
in exactly the format a model's answer comes in (SSE chunks, or one JSON
body for `stream: false`). `X-Jarvis-Route` then carries `"quick": <what was
done>`, `"where": "local"`, `"lane": "no AI model"`, and no facts used; a
reply that reads the to-do list out carries `"gate": "private"`, so a voice
answer stays on screen under the apps' private-answer rule. Both apps show
a small line under such an answer: **"Done - answered on this PC without the
AI model."**

**A temporary chat** still sets the reminder - it is an action, not memory -
and, as for any temporary chat, the chat is not kept and nothing is learned.

**The model's own tools** (`jarvis_agent.py`, offered only when
`[tools].enabled` names them, like every tool): `set_timer`, `set_reminder`
(once or repeating; `when` in plain English or `2026-10-02 17:30`),
`todo_add`, `todo_done`, `coming_up`. They are not put to the gate for a
one-off (the owner's decision); a repeat raises the scheduler's own card
above. In a turn shaped by outside text (the same test as a note write -
section 4) they set and change nothing, so a web page or an email cannot
set Jarvis's alarms.

### 21.6 What is private, and where it stays

A reminder's and a to-do item's words are the owner's own. They stay in
`schedule.db` on the PC (plain SQLite, like `memory.db`), are never put on
the event bus or in the audit log (ids and kinds only), and are never sent
anywhere. **They are not learned as facts**: `jarvis_intake.owner_turns`
skips a sentence the grammar matches, and one the model set a reminder
from (the scheduler keeps its digest, never its words). The chat history
keeps the turn like any other (encrypted, and not for a temporary chat).
While the private lists are hidden, the desktop's Rust takes the words out
of Coming up before the page sees them, and the phone hides them on the phone's Brain screen;
the times stay, so a timer still counts down.

### 21.7 Known gaps, said plainly

- **Not run on the owner's PC.** Everything above was tested in the dev
  container: the scheduler with a hand-moved clock and real SQLite files,
  daylight saving with the London and New York rules (`time.tzset`, which
  Windows does not have - on Windows the same code asks Windows' own
  time-zone rules, and that was not watched), and `/api/chat` through the
  patched block lifted from the whole patch stack. The toast and the phone
  notification have not been seen on a real Windows PC or phone.
- **English only.** Other languages go to the model, whose tools can still
  set a timer when they are switched on.
- **The phone hears of a job going off only while connected** (21.1) -
  except an alarm or reminder the owner handed to the phone's own apps with
  "Also on my phone" (21.10).
- **Snooze, "cancel that" and named lists (21.9)** were tested in the dev
  container only. The Windows toast's Snooze button and the phone
  notification's Snooze action have not been pressed on a real PC or phone;
  the phone's screen code is compiled by CI only.
- **The initiative engine and the digest are not hooked in.** The engine's
  30-minute heartbeat and in-memory findings could not host timers
  (`jarvis_schedule.py`'s header says why); the digest lives in the owner's
  `jarvis_arbiter.py`, which this repository does not hold. The scheduler is
  the one clock; briefings, sleep mode and the overnight tidy are to plug in
  as new kinds (`register_kind`), not as schedulers of their own. Sleep mode
  now has, as the standby schedule (21.8), and so has the morning briefing
  (section 22).

### 21.10 "Also on my phone" (added 2026-09-26, the phone only)

The owner's decision of 2026-09-26 (the cutting-edge "Quick wins"; the
feasibility audit's I93). In the phone's Brain -> Coming up, an **alarm**
or a **reminder** has a button, "Also on my phone", that hands a copy to the
phone's own apps - **by the owner's tap only, never on its own**:

- an alarm -> the phone's Clock app (`AlarmClock.ACTION_SET_ALARM`): the
  hour, the minute and the owner's words, and for a repeat the days (every
  day, weekdays, or the chosen days). The Clock app shows its own screen
  (`EXTRA_SKIP_UI` false) and the owner saves it there. A one-off alarm is
  offered only when it is due within 24 hours - the Clock app sets an alarm
  by time of day only - and further ahead the row says "offered from the day
  before". One that repeats every few hours is not offered.
- a reminder -> the phone's calendar (`Intent.ACTION_INSERT` on
  `CalendarContract.Events`): an event at its next time, 15 minutes long,
  titled with the owner's words, repeating the same way (`RRULE`
  `FREQ=DAILY` or `FREQ=WEEKLY;BYDAY=...`). The calendar app shows its own
  editing screen.

Nothing is sent to the PC and nothing changes there, so there is **no
approval card** (the tap, and saving in the phone's own app, are the
owner's decision) and the button is not held on a stale link. It reads the
job's `rule` (`every`, `at`, `days`) and `due` from `GET /api/schedule` -
the same answer Coming up already reads; no new route. Not offered while
the private lists are hidden (the words are hidden), nor for a paused one,
a timer, a to-do item, a briefing, a "tell me when" or the standby
schedule. One line under the list says what it does and warns plainly:
"Keep both and both will ring; the phone's calendar may copy the event to
your Google account." The phone asks for one install-time permission,
`com.android.alarm.permission.SET_ALARM`, and still no exact-alarm
permission. Jarvis's own late-alarm rule (21.1, a job heard of more than 10
minutes late is a silent "Missed at") stays on Jarvis's own alarms; a copy
in the Clock app is the Clock app's. A repeat's time is the PC's wall-clock
time ("07:00"); on a phone set to another time zone it rings at 07:00 there.

The desktop has no such button, on purpose (ARCHITECTURE section 8, "On the
phone, kept off the desktop").

### 21.9 Snooze, "cancel that" and named lists (added 2026-09-25)

The creativity audit's everyday quick wins (`docs/CREATIVITY-AUDIT-2026-09-25.md`
item 6, `docs/creativity-2026-09-25/usefulness.md` idea 1). No new route, no
new patch: `jarvis_schedule.py` and `jarvis_quick.py` only, and both apps.
Nothing here needs a card: a snooze is a one-off, and the owner's rule is no
card for a one-off.

**Snooze.** A timer, alarm or reminder that WENT OFF (in the last day) can be
snoozed: `POST /api/schedule/act {"id", "do": "snooze", "seconds"?}` (10
minutes when not said; 1 minute to 24 hours). It makes a **new one-off copy**
of the job (same kind, same words, `"snoozed": true`, `source` `"snooze"`),
due after the snooze. A repeating job's own rule and next time are not
touched, so only that one occurrence moves. Snoozing the same one again
while its copy waits changes nothing (`"already": true`, "Already snoozed
until 07:10."); when a repeat goes off again, it can be snoozed afresh. A to-do
item, a briefing and the standby schedule cannot be snoozed (409).

- **Both apps**, "Just went off" at the top of Coming up, in the same words
  ("In the last hour. Snooze sets it to go off again in 10 minutes - a
  repeating one keeps its usual times."): each thing that went off in the
  last hour and is not snoozed, "Went off at 07:00", and **Snooze 10
  minutes** - ONE job per tap, no question, held on a stale link. A snoozed
  copy's tag reads "alarm, snoozed".
- **The phone's notification** for a timer, alarm or reminder carries a
  "Snooze 10 minutes" action (never Approve, never "all"). It goes to the
  link service, which waits for the link like a notification's Deny and
  then sends the one snooze (held on a stale link), and says how it went in
  a toast. The locked screen's version has no action.
- **The Windows toast** carries the same button (`winrt_toast.rs`
  `notify_fired`, the same foreground activation as the approval toast's
  Deny: the click relaunches Jarvis with `jarvis-snooze:<id>`, which is
  answered without putting a window up). **Not watched on a real Windows
  PC**, like the Deny button. If the toast cannot be built that way (an
  uninstalled build, or any WinRT error) the plain toast is shown instead and
  Snooze is in the Brain's Coming up.
- **Said or typed**: "snooze" takes the most recent thing that went off in
  the last hour; "snooze the alarm" the most recent alarm. "Snoozed the alarm
  for 10 minutes - until 07:10."

**"Cancel that".** "cancel that", "never mind", "undo", "delete that
reminder" take back the LAST thing the fast path set **in this conversation**
(the request's `conversation_id`, 18.1), within **two minutes**, once - and say
what it was ("Cancelled: the 10 minute timer.", "Removed the 3 items just
added to your shopping list.", "Cancelled: the repeating reminder (...). Its
approval card will set nothing up."). It never takes back anything else:

- only what the fast path itself made in that answer - not what the model's
  tools set, not an item that was already on the list, not another
  conversation's;
- anything else said in between (another command, or a turn the model
  answered) means "that" is no longer the thing set, so nothing is taken
  back;
- more than two minutes later: "That was more than 2 minutes ago, so nothing
  was cancelled - delete it under Coming up.";
- "delete that reminder" after an alarm: "The last thing set here was an
  alarm, not a reminder, so nothing was cancelled.";
- with nothing to take back, "never mind" and "cancel that" go to the model
  as before, and "cancel that timer" / "... alarm" keep their old meaning
  (the one running timer, the one alarm).

What was set is kept in the scheduler's memory only (ids, a few words, the
time) and forgotten on a restart. A snooze taken back frees its original, so
it shows under "Just went off" again.

**Named lists.** A to-do item may carry a list name - `"list": "shopping"`
(`""` is the to-do list itself). A name is one to three plain words, kept in
lower case without "list" ("Shopping list" -> `shopping`); up to 20 named
lists, and the 300 open items are for all lists together. The same words
twice on ONE list are one item.

- Said or typed: "add milk to the shopping list" (with commas, several
  items: "add milk, eggs and bread to the shopping list"; without a comma
  "mac and cheese" stays one item), "what's on my shopping list" (private,
  like the to-do list), "cross milk off the shopping list", "remove eggs from
  the shopping list", "what lists do I have". "What's on my to-do list"
  reads the to-do list only and names the other lists.
- **Clearing a whole list** happens only in the apps: under each named list,
  **Clear list** asks "Clear the shopping list? This deletes all 3 items on
  it, and cannot be undone." (the desktop's own OK / Cancel; the phone's "Yes,
  clear it" / "Keep it"), then sends `{"do": "clear_list", "list", "count"}`
  with the number of items it showed. The PC clears nothing when that number
  is no longer right ("The shopping list changed since you looked - ...").
  The to-do list itself is never cleared at once (409), and "clear the
  shopping list" said to Jarvis changes nothing and says where the button
  is. This is the one bulk change in the scheduler, asked for by the owner's
  plan; it deletes items the owner can see listed, never approves anything.
- **Both apps**, under the to-do list: each named list under its own heading
  with its items (Done / Delete), its own Add box ("Add to the shopping
  list"), and Clear list; and a line "To start another list, say or type "add
  milk to the shopping list"." While the private lists are hidden the list
  names are hidden too (the desktop's Rust and the phone replace each with
  "hidden-1", ... so the items still group under "(hidden) list"), and
  neither Add nor Clear list is offered.
- The morning briefing's to-do part counts each named list as one line
  ("Shopping list: 2 items").

### 21.8 The standby schedule - "sleep mode" (added 2026-09-25)

Task #55 ("sleep feature - schedule + manual sleep/wake, unload ALL models
on both GPUs, warm-up on wake"), built on what was there. `backend/
jarvis_standby_schedule.py`; the changes to Standby itself are in §11.

**One concept, not two.** Jarvis already had Standby (§11, both apps call
it that), which frees the graphics cards. Sleep mode is that Standby on a
timetable, so it is called the **standby schedule** in both apps. Manual
sleep and wake are the Standby and Active controls that already exist -
nothing new. "Sleep" is avoided because `[memory.sleep_time]` /
`jarvis_sleep.py` is the overnight memory tidy, which the toml warns does
the opposite.

**A kind of job, not a loop.** Kind `"standby"`, registered with
`jarvis_schedule.register_kind` (ARCHITECTURE section 12): a **window**
kind, one of its kind at a time, that notifies nobody. Its rule:

```
{"every": "day", "at": "01:00", "until": "07:00"}     every day only; the two times must differ
```

It goes off at both ends (`next_run` is whichever end comes first). Which
end it is comes from the clock (`jarvis_schedule.in_window`), not from which
end last fired, so a night the PC was off - 01:00 and 07:00 both overdue,
found together, going off ONCE late - agrees: it is after 07:00, so awake.

| Route | Body | Answers | Notes |
|---|---|---|---|
| `POST /api/schedule/add` | `{"kind": "standby", "repeat": {"every": "day", "at": "HH:MM", "until": "HH:MM"}}` | 200 `{"ok": true, "waiting": false, "job", "said"}` - set up at once, no card, since 2026-09-26 ("Standby schedule set up, every day from 01:00 to 07:00. Next: Saturday 26 September, 01:00 to 07:00. Delete it under Coming up to stop it."); until then **202** and ONE `schedule_repeat` card; 400 bad times or no `repeat`; **409** there is already one ("delete it first to set a different one") | No card since 2026-09-26 (the owner's decision after the approvals audit). Desktop: `brain_schedule_add_standby` (Brain window only, held on a stale link). Phone: `JarvisRuntime.addStandbySchedule` (held on a stale link). |
| `POST /api/schedule/act` | `{"id", "do": "pause" \| "resume" \| "delete"}` | as 21.2 | Pause skips it, Delete turns it off - immediate, no card. **Neither wakes Jarvis**; Active does that. |
| `GET /api/schedule` | - | as 21.2 | Listed with the others: `repeat` "every day from 01:00 to 07:00", `when` "on standby at 01:00 tomorrow" or "awake at 07:00 today, if the schedule put it on standby", `note` how the last end went, `notify: false`. |

Until 2026-09-26 it was set up by a card (21.3's action and tier, its own
words, below). Since then it has none: the answer's `said` names the next
night instead, and both apps' Standby schedule section says "Setting it up
needs no approval card, and Delete turns it off at once." The card's lines
about each end are still true, and are kept here as the reference:

```
Set up a standby schedule.

When: every day from 01:00 to 07:00.

At the start, Jarvis goes on standby - the same as choosing Standby: it unloads its models and frees the graphics card(s).
At the end, if the schedule put it on standby, it wakes (Active) and loads the chat model again, so the first answer is not slow. If you chose Standby yourself, it stays on standby until you choose Active.
Timers, alarms and reminders still go off while it is on standby. A question asked then is answered, but the first answer takes 5-15 seconds.
Turning it off does not wake Jarvis if it is on standby at that moment - choose Active for that.

The next three times:
  - Saturday 26 September, 01:00 to 07:00
  - Sunday 27 September, 01:00 to 07:00
  - Monday 28 September, 01:00 to 07:00

It runs on this PC, by this PC's clock. Nothing is sent anywhere.
Stopping or deleting it is immediate, from either app.

If you say no: nothing is set up.
```

**Each end** calls `jarvis_power_switch.set_mode` - the same call as the
Standby and Active buttons, through the gate as `power_manage` (`auto` as
shipped; a card at 01:00 if the owner set it to `ask`), with `why` "the
standby schedule":

- start: on standby, unless it already is ("Already on standby at 01:00.").
  Refused while a task runs: that night is skipped ("Skipped standby at
  01:00: a task was running, ...").
- end: Active, and the warm-up loads the chat model (§11) - **only if the
  schedule put Jarvis on standby** (the owner's decision of 2026-09-25:
  "Only if the schedule did it. If you switched Standby on yourself, it
  stays on until you switch it off"). Who did is `jarvis_power.status()
  ["why"]` (§11): `"the standby schedule"` wakes it; anything else - the
  owner's tap in either app, or a power module that cannot say - leaves it
  ("Left on standby at 07:00: you chose Standby yourself, so it stays on
  until you choose Active."). If it is already awake, nothing ("Already
  awake at 07:00.").
- a start found late inside the window (the PC came on at 03:00): standby
  then, once.

The cases, as the tests run them (`backend/test_standby_schedule.py`):

| What happened | 01:00 | 07:00 |
|---|---|---|
| Standby by hand at 23:00 | "Already on standby at 01:00 - you chose it, so the end of the schedule will leave it on." (it stays the owner's) | Left on standby |
| The schedule's standby, woken by hand at 03:00 | "Went on standby at 01:00." | "Already awake at 07:00." - not put back on standby |
| ... then Standby by hand again at 04:00 | | Left on standby (the owner's now) |
| The schedule's standby, and a tap on Standby at 04:00 | | Wakes: the tap changed nothing, so it is still the schedule's |
| 01:00 skipped (a task ran), then Standby by hand | "Skipped standby at 01:00: ..." | Left on standby |
| The backend restarted at 03:00 | | "Already awake at 07:00." - the mode is in memory, so it came back Active, and nothing puts it back that night |

The last end's sentence is the job's `note` (kept in memory; gone on a
restart). The going-off event says `"notify": false`: no toast, no phone
notification. The `power` event updates both apps' Power line.

**While on standby** - the same as Standby by hand: timers, alarms and
reminders still go off (the scheduler does not look at the power mode, and
21.5 answers without the model); a question is answered after 5-15 seconds
while Ollama loads the model, and Jarvis stays on standby (nothing in this
repository changes the mode on a question) until the end of the window or
Active.

**Both apps**, in the same words (`coming-up.js`, `net/Schedule.kt`,
checked against each other by `tests/coming-up.mjs`): under Coming up, a
"Standby schedule" part - its line says it "wakes only if the schedule put
it on standby: if you chose Standby yourself, it stays on until you choose
Active" - with "Standby at" and "Wake at" (01:00 and 07:00 to start with)
and **Set up**; once one exists, its row sits in the list
("standby, repeats", Pause, Delete, and its `note`) and the part says "Your
standby schedule is in the list above. Pause skips it and Delete turns it
off. Neither wakes Jarvis - choose Active for that." The desktop's tray
Power row says "· standby schedule" when the schedule set the mode.

**Known gaps, said plainly.** Not run on the owner's PC; Ollama was a
stand-in in every test. Every day only (no weekdays-only window yet). The
power mode is kept in memory, so a backend restart inside the window comes
back Active until the next start (the start already went off) - and, for the
same reason, a Standby the owner chose by hand before a restart comes back
Active too. Who chose Standby is known only from `jarvis_power`'s one
`why`: a tap on Standby while the schedule's standby is on changes nothing,
so the end still wakes it. With one
graphics card, the second card's part of standby finds nothing and says
nothing.

## 22. The morning briefing, and the back-off for offers (added 2026-09-25)

The owner's decisions of 2026-09-25 (`CLAUDE.md`): ONE scheduler, reused for
briefings; anything that repeats asks once with a card listing the next run
times, a one-off needs none; simple commands are answered without the AI
model. And rule 1: email, files, credentials and memory stay on this PC.

`backend/briefing.patch`, `backend/jarvis_briefing.py` and
`backend/jarvis_backoff.py`. **Both apps call both routes.** The desktop:
the Brain's Work tab, "Morning briefing" (`brain/briefing.rs`
`brain_briefing`, `brain_briefing_now`, Brain only) and Settings, "Morning
briefing" (`get_briefing_setup`, `set_briefing`, `stop_briefing`, Settings
only); a Windows toast when one is ready (`stream.rs` -> `toast_ready`). The
phone: Brain, "Morning briefing" (`BriefingPlate.kt`, `net/Briefing.kt`) -
on the phone, settings for a PC feature live on the phone's Brain screen, like the second
card's switches; a notification when one is ready, which opens the Brain.

### 22.1 What it is

A short list of the day, **put together in code on the PC - no model, local
or cloud, ever sees it**, so it works while the model is slow, unloaded or
asleep. Only what Jarvis can already read on this PC, in this order:

| Section (`key`) | What | When it is left out |
|---|---|---|
| Calendar (`calendar`) | Today's events: all-day first, then by this PC's time. Repeating events (RRULE) are worked out, so a weekly meeting shows on today's date; one whose rule `jarvis_calendar` cannot work out (BYSETPOS and the like) shows the time of its first date and "(repeats)"; one that began earlier "(continues from an earlier day)". | Not set up (neither `JARVIS_CALDAV_URL` nor the private calendar link `JARVIS_CALENDAR_ICS_SECRET_URL` set, or `calendar_read` not in `[tools].enabled`); or `calendar_read` is not tier `auto`/`notify` - then it is not read and **no card is raised**, and the briefing says why. |
| Today (`today`) | Alarms, reminders and timers still to come today, with their words. | Never. |
| To-do list (`todo`) | How many open items, and the first five. | Never. |
| Approvals (`approvals`) | How many approval cards wait - "Open Jarvis to answer." Never an Approve. | Never. |
| Email (`email`) | **How many** unread emails, and **who the newest five are from** (the owner's decision of 2026-09-25): the summary "3 unread emails." and one line, "From Alex, Your Bank and GitHub" (or "The newest 5 are from ..." when there are more). `jarvis_email.senders()`: ONE connection, the mailbox opened read-only, SEARCH UNSEEN, then `FETCH <id> (BODY.PEEK[HEADER.FIELDS (FROM)])` for the newest five only - the From line, never a subject or any text, and PEEK so nothing is marked as read. Each name is decoded (RFC 2047), stripped of control and direction characters, capped at 60 characters, with any one-time code or sign-in link hidden (section 25), and listed once; a sender with no name shows the whole address (`noreply@github.com` - the part before the @ alone is "noreply" or "info" as often as not). With "Show who new emails are from" off (22.2): the number only, through `jarvis_email.count()` (no message fetched), as before. | Not set up (`JARVIS_IMAP_HOST` unset, or `email_check` not in `[tools].enabled`) - then it is not mentioned at all; or `email_read` is not `auto`/`notify` - then it says why. |

| Weather (`weather`, first; added 2026-09-26, the feasibility audit's I75 - the owner's choice) | From the owner's **own Home Assistant only**, which already fetches a forecast for its weather device, so Jarvis opens no connection to any weather service. The summary "Now 12 °C, partly cloudy." and a line for today and for tomorrow - "Today: rain, 9 to 14 °C, 80% chance of rain". Built from numbers and HA's own list of conditions only (an unknown condition, and every free-text field such as the device's name, is left out). `jarvis_home.plan_forecast()`: exactly two fixed requests to ONE weather device - `GET /api/states/<device>` and `POST /api/services/weather/get_forecasts?return_response` with the body `{"entity_id", "type": "daily"}` - never a service call through `home_control`, and `run()` refuses a weather plan whose requests are anything else (`test_home_control.py` tampers with it seven ways). The device is `JARVIS_HOME_WEATHER` on the PC, or HA's usual `weather.forecast_home`; no screen sets it. | Not set up (`JARVIS_HOME_URL` unset, or `home_read` not in `[tools].enabled`) - then the last line says so; or `home_read` is not `auto`/`notify` - then it is not read, **no card is raised**, and the briefing says why. HA without that device: "Not read: Home Assistant has no device called weather.forecast_home. Set JARVIS_HOME_WEATHER ...". |

Then always the PC's own last line, `outside_line`: with the weather in it,
"News: not available. No news provider has been chosen, so Jarvis fetches
nothing from the internet for this."; without it, "Weather and news: not
available. The weather can come only from your own Home Assistant, and no
news provider has been chosen, so Jarvis fetches nothing from the internet
for this." (Both apps show `outside_line`, and their own copy of the second
line from a PC that sends none.)

Each read that leaves the PC (the calendar to the owner's CalDAV server, or
to Google through the private calendar link - section 22.8 - the count
and senders to the owner's IMAP server, and the weather to the owner's Home
Assistant) goes through `jarvis_gate.check()` as its own action
(`calendar_read`, `email_read`, `home_read`), exactly as the model's
tools do, and runs only if the gate says `allowed`. The forecast is
**outside text** (Home Assistant says whatever its weather device says), so
a briefing that shows it lists `home_read` in `read`. The senders are
**outside text** - anyone can write anything in a From line - so, like
calendar titles, they are lines (`items`), never a summary, and a briefing
that shows them lists `email_check` in `read` (below). Together they get 25 seconds
(`READ_DEADLINE`); a slow one is left out ("did not answer in time"). A
failure says so without quoting the server.

### 22.2 Routes

| Route | Body | Answers | Notes |
|---|---|---|---|
| `GET /api/briefing` | - | 200 `{"available": true, "briefing": briefing \| null, "building": bool, "setups": [job], "sources": {"calendar", "email", "weather": {"state", "said"}}, "senders": {"on", "waiting", "last", "why"}, "title", "lock_screen", "empty"}`; 503 `{"available": false, "error": <exception name>}` without `jarvis_briefing.py` | Token + origin. `setups`: the briefing jobs (section 21's job shape). `sources`: what a briefing would include, worked out without reading anything - `state` is `on`, `off` or `asks` (a PC from before 2026-09-26 says `not_available` for the weather); `email` also has `senders` (bool) and says "Included: how many unread emails you have, and who the newest 5 are from." or "... (the number only)." `senders`: the setting below - `last` is `{"outcome", "message", "why", "at"}` of the last ON card, or null. A PC from before it sends no `senders`, and both apps then offer no switch. |
| `POST /api/briefing/senders` | `{"enabled": bool}` | 200 `{"ok": true, "waiting": false, "senders", "message"}` (OFF, done; or ON when it is already on); **202** `{"ok": true, "waiting": true, "senders", "message"}` (ON: ONE card is up; nothing has changed); 400 not true/false; **503** `change_own_config` is not tier `ask` (no card is raised - a config line is not a person's yes); 500 the setting could not be saved | "Show who new emails are from" (on by default). OFF is immediate, never a card, and withdraws a waiting ON card (approving it later changes nothing, `last.outcome` `"withdrawn"`). ON is ONE approval card, action `change_own_config` - the one the voice settings use to show or say more - and only tier `ask` with outcome `approved` turns it on; `last.outcome` becomes `enabled`, `denied`, `timed_out`, `refused`, `withdrawn` or `failed`, with a plain `message`. Kept on this PC in `briefing.json` in the settings folder (`{"senders": bool, "changed": epoch}`); no file reads as on, a damaged one as off (and `why` says so). Both apps hold ON on a stale link and let OFF through (desktop `set_briefing_senders`, Settings only; phone `JarvisRuntime.setBriefingSenders`). |
| `POST /api/briefing/now` | `{}` · `{"missed": true}` ("What did I miss?", 22.9) | 200 `{"ok": true, "briefing"}`; 400 not an object; 500 `{"ok": false, "error": <exception name>}` | One put together now, and kept as the latest. It only READS, asks no card and changes nothing, so **neither app holds it on a stale link** (like every read). Up to about 25 seconds with a slow calendar or mail server. |

Setting one up and stopping one are section 21's routes:
`POST /api/schedule/add {"kind": "briefing", "repeat": rule}` (202, ONE
card; `rule` is `every` `day`, `weekday` or `week` with `days` - the apps
offer no "every N hours") or `{"kind": "briefing", "at": <epoch>}` (once, no
card); `POST /api/schedule/act {"id", "do": "delete"}`. Both held on a
stale link in both apps. The same repeat set up twice is refused ("a
morning briefing every weekday ... at 07:00 is already set up"). A
`briefing` job has no words of its own; Coming up calls it "Morning
briefing" in both apps.

A `briefing`:

```
{"id": "b0123456789", "made": epoch, "date": "Friday 25 September",
 "heading": "Your briefing for Friday 25 September, made at 07:00.",
 "source": "schedule" | "now" | "chat", "job": job id | null,
 "missed": "missed at 07:00" | "", "late": bool, "private": true,
 "sections": [{"key", "title", "state": "ok" | "empty" | "failed" | "refused" | "slow",
               "summary": "2 events today.", "items": ["09:30 Dentist", ...]}],
 "not_included": ["Not included: your calendar is not set up for Jarvis on this PC."],
 "read": ["calendar_read", "email_check", "home_read"] | [],   outside text in the lines (below)
 "outside_line": "News: not available. ..." | "Weather and news: not available. ...",
 "lock_screen": "Jarvis: your morning briefing is ready.",
 "text": the whole of it as plain lines (the chat answer)}
```

**Kept in memory only** - the latest one, in the backend process. Never
written to disk, never put on the event bus; gone when Jarvis restarts.

### 22.3 The card, and when it goes off

A repeat is the scheduler's own `schedule_repeat` card (section 21.3): what,
when, the next three times - and, in place of "Nothing is sent anywhere.",
what each run reads: "Each time, Jarvis puts together a short list on this
PC, without the AI model: ... how many unread emails you have and who the
newest are from (the number only, if you turned that off), if email is set
up - the weather, from your own Home Assistant, if it is set up for Jarvis
... It only reads. It changes nothing and approves nothing." and "Reading
your calendar, email and Home Assistant is a request to your own calendar,
mail server and Home Assistant, the same as asking Jarvis to read them,
under the same settings. Nothing else is sent anywhere, and nothing goes to
the AI model."

When its time comes the scheduler rings `schedule` `fired` as for any job,
then the briefing is put together on its own thread, then `schedule`
`{"id", "kind": "briefing", "state": "ready"}` - always, even when a part
could not be read. **Both apps notify on `ready`, not `fired`**, so the
notification is never ahead of the briefing. Missed while the PC was off:
it goes off once, late, and says "(Due at 07:00 - the PC was off or asleep,
so it is late.)".

### 22.4 What the apps show

- **The notification and the Windows toast say only "Jarvis: your morning
  briefing is ready."** (title "Morning briefing") - on the lock screen and
  inside it, whatever App lock or the privacy settings say. The words of the
  briefing are read in the app, behind the token.
- **The briefing**: the heading, each section's summary and its lines, the
  PC's last line (`outside_line`), what was left out, and "Kept on your PC until
  Jarvis restarts." While the private lists are hidden (the desktop's
  "Windows Hello for memory lists and chat history", taken out in Rust; the
  phone's "Hide memory lists and chat history") the lines go and the
  summaries - counts only - stay. The email senders are lines, so they go
  too ("3 unread emails." stays).
- **"Show who new emails are from"** - the desktop's Settings -> Morning
  briefing, the phone's Brain -> Morning briefing, in the same words
  (`briefing.js`, `net/Briefing.kt`, checked by `tests/briefing.mjs`): "The
  briefing lists who your newest unread emails are from (up to 5), next to
  how many there are. Off: the number only. Turning it on shows you an
  approval card first; turning it off happens at once." While the card
  waits the switch reads on and says "Waiting for your yes on the approval
  card, on your PC or phone." - and turning it off then takes the request
  back. Held on a stale link when turning ON only. The card:

  ```
  Show who your new emails are from in the morning briefing?

  The briefing will list the names your newest unread emails are from (up to 5), next to how many there are. To get them, Jarvis asks your mail server for each email's From line only - never its subject or text - and nothing is marked as read.

  The names show only inside the Jarvis apps, and are hidden with your memory lists and chat history when those are hidden. The notification still says only "Jarvis: your morning briefing is ready." Nothing goes to the AI model.

  If you did not just do this, say no.

  If you say no: nothing changes - the briefing shows only how many new emails there are.
  ```
- **"Brief me now"**, and the setup: every day, weekdays, or chosen days,
  at a time; the setups with one Stop each. No "stop all".

### 22.5 Said or typed - without the model

`jarvis_quick.py` (section 21.5), English only, whole sentences:

| | Examples |
|---|---|
| Now | "brief me", "brief me now", "read my briefing", "what's my briefing", "give me my morning briefing", "morning briefing" |
| Set up | "brief me every weekday at 7" (a card), "brief me every day at 6:30am", "set up a morning briefing every weekday morning at 7", "brief me on mondays and fridays at 8", "brief me tomorrow at 7" (once, no card) |
| Stop | "stop my briefing" (with two set up it asks which and deletes nothing); "cancel all my briefings" is refused like every bulk change |
| When | "when is my briefing" |

**"What's the weather?"** (2026-09-26) is answered here too, from the same
read as the briefing's Weather section (`jarvis_briefing.weather_now`):
"Now 12 °C, partly cloudy. Today: rain, 9 to 14 °C, 80% chance of rain.
Tomorrow: sunny, 11 to 18 °C. (From your own Home Assistant.)" - only the
plain question ("what's the weather", "how's the weather tomorrow", "what's
the forecast", "weather"); "what's the weather in Paris" or "this weekend"
go to the model. Without Home Assistant it says there is none and looks
nothing up. Not private, but the record of the turn says `home_read` ran, so
the conversation counts as having read outside text.

"Brief me on the project" and the like go to the model. The answer to "brief
me now" is the briefing itself, with `X-Jarvis-Route` `"quick":
"briefing_now"` and `"gate": "private"` - so a spoken question's answer
**stays on screen under the apps' private-answer rule** (section 16), like a
calendar answer, unless the owner chose "voice check is enough". A typed
"read my briefing" follows the same rule as any typed answer. When the
answer quotes calendar titles (text from the calendar server), this PC's
record of the turn says `calendar_read` ran, so the conversation counts as
having read outside text (ARCHITECTURE section 3) exactly as when the
calendar tool runs. The same for email senders (text from whoever sent the
email): the record says `email_check` ran.

### 22.6 The back-off for offers (`jarvis_backoff.py`)

Jarvis's offers nobody asked for - today the overnight-tidy card
(`setup.sleep_time_offer`) and the "save this routine as a skill?" card
(`jarvis_skill_discovery.py`) - follow four rules:

0. **Not in Quiet or Standby** (added 2026-09-25, a bug the creativity audit
   found): `may_offer` reads `jarvis_power.current()` (which applies the
   quiet hours too) and answers `(False, "quiet")` in `quiet` or `standby`.
   The offer is kept for later - nothing is written, it is not counted as
   waiting and never as a "no"; the overnight card is offered later the same
   day once Jarvis is Active. A mode that cannot be read also holds offers
   back (`"mode_unknown"`).
1. **At most three offers waiting** for an answer at once.
2. **None within two minutes** of the last chat message (`/api/chat` notes
   the time of every message, in memory, never the words). The skill offer,
   which starts at the end of a chat turn, waits until the owner has been
   quiet for two minutes (up to 30 minutes, then gives up).
3. **Each "no" is heard**: the same offer - matched by a sha256 fingerprint
   of what is offered, never its wording - is quiet for 1 day, then 7, then
   30 (and 30 after that). A "yes" clears the count.
4. **An offer never asks for more** (the Muse audit, 2026-09-25). An
   offer Jarvis makes on its own may never ask for more access, a new
   connection, a key, a password, a payment method, an identity document,
   or to turn on a setting that shows or trusts more. Checked in code by
   the offer's KIND, not its words: every kind is declared in
   `jarvis_backoff.OFFERS` with what it asks for (`MAY_ASK`), and
   `may_offer(fp, kind=...)` refuses a kind that is not declared or asks
   for anything in `NEVER_ASKS`, logs why ("offer refused: kind ... - ...")
   and counts it (`status()`: `refused_asking_for_more`, `last_refused`).
   Both offers made today pass their kind and ask only to record a wish
   (the overnight tidy) or to save a routine as a skill; none breaks the
   rule - it guards the future. `backend/test_backoff_rule.py` fails if any
   `may_offer()` call in the shipped code leaves out `kind=`. Offers made
   inside an answer to the owner's own request (switching web search when
   it is down, the cloud lane for one question) are not offers "on its
   own"; the web search one never names a provider that needs a key.

It keeps only fingerprints, counts and dates, in `backoff.json` in the Jarvis
settings folder (a file it cannot read makes every offer wait, and says so).
It **never approves or acts** and calls no gate; **the owner's own requests
never consult it** - switching the overnight tidy on, or asking for a
routine, works whatever was declined - and a "no" never becomes a memory
rule or a setting. A skill offer's own "no" is already for good (its
ledger), so nothing is written for it here. The briefing makes no offers.
The initiative engine has no checks registered (section 21.7), so it makes
none either.

Design from Leon (leon-ai/leon, MIT, `server/src/core/pulse-manager.ts`:
`MAX_PENDING_MATTERS`, `ACTIVE_CONVERSATION_GRACE_MS`,
`PULSE_DECLINE_COOLDOWN_MS`); no code copied. Leon can also save a declined
offer as a remembered preference; that part was not taken.

### 22.7 Known gaps, said plainly

- **Not run on the owner's PC**, nor against a real calendar or mail
  server. The toast and the notification have not been seen on a real
  Windows PC or phone.
- **Repeating calendar events**: the common rules are worked out (section
  22.8); a rule that is not is shown with its first date's time, marked
  "(repeats)". An event kept in a time zone (a `TZID`) is shown at the right
  hour only when Python on the PC has time-zone data - on Windows the
  `tzdata` package, in `requirements.txt` since 2026-09-25 - and otherwise as
  if it were in this PC's time zone.
- **The desktop toast does not open the briefing**: it is the same plain
  toast the timers use; the briefing is on the Brain's Work tab. The
  phone's notification opens the Brain.
- **English only**, like the timers.
- **One briefing is kept - the latest.** "Brief me now" on one app replaces
  it; the other app shows the new one at its next read (Refresh, or opening
  the section again) - there is no event for a briefing asked for by hand.
- **The email senders have not met a real mail server.** The IMAP
  conversation was run against a stand-in `imaplib` that records every
  command (`backend/test_email.py`), which proves what is ASKED (read-only,
  `BODY.PEEK`, the From line only, no STORE) but not how a given provider
  answers. A server that ignores PEEK and marks messages read would be a
  server bug; the mailbox is also opened read-only (EXAMINE), which by the
  IMAP standard cannot change flags.
- **Only the newest five senders**, and a name longer than 60 characters is
  cut short with "...".

### 22.9 "What did I miss?" (added 2026-09-25)

The creativity audit's item 7 (`docs/creativity-2026-09-25/usefulness.md`
idea 2): **the briefing's builder, run for "since you last looked"**
(`jarvis_briefing.build_missed`) - no second builder, no model.

**"Since you last looked", defined simply**: the time of the owner's
previous message to Jarvis, from **either app** (every `/api/chat` request
counts, whoever's words it carries - `jarvis_quick.answer_turn` calls
`jarvis_briefing.touch()`), or the last time "What did I miss?" was asked in
an app. One time for the whole PC, in the backend's memory only (the time,
never the words). The answer says it: "What you missed since 14:05 today,
when you last talked to Jarvis." After a restart it does not know: "What you
missed in the last 12 hours. Jarvis restarted since you last talked to it,
so it does not know when that was." Never more than a day back (the
scheduler keeps what went off for a day), and said so.

What it lists, in this order, each a section in the briefing's own shape:

| Section (`key`) | What |
|---|---|
| Went off (`went_off`) | Every timer, alarm, reminder, briefing and to-do due that went off since then (a repeating one: its latest time), "10:00 call the bank", "(late - the PC was off or asleep)". Not a "tell me when" look (a `silent` kind: looking at the inbox is not news - fixed 2026-09-26), and not the standby schedule. |
| Approvals (`approvals`) | How many cards wait, and how many of them came up since then - "Open Jarvis to answer." Never an Approve. **Cards that expired while you were away are not listed**: the gate's record of past cards is in the owner's `jarvis_gate.py`, which this repository does not hold, so nothing reads it. |
| Email (`email`) | Exactly as the briefing (22.1): unread count and the newest five senders, only when email is set up, through the same gate action and the same "Show who new emails are from" setting; `read` says email was read when senders are shown. |
| Coming up (`next`) | The next three things on the list, "18:00 today: water the plants". |

No calendar, and no weather line. `source` is `"missed"`, and `since` /
`since_known` say what "since" was. It is **not kept** as the latest
briefing.

- **Said or typed** (`jarvis_quick.py`): "what did I miss", "did I miss
  anything", "catch me up", "what's new", "what happened while I was away".
  The answer is private (`"gate": "private"`), so a spoken question's answer
  stays on screen under the apps' private-answer rule, like the briefing.
- **Both apps**: "What did I miss?" next to "Brief me now" in the Morning
  briefing part (desktop Brain -> Work, `brain_briefing_now {missed: true}`;
  phone's Brain, `JarvisRuntime.briefingMissed`) -> `POST /api/briefing/now
  {"missed": true}` -> `{"ok": true, "briefing": <the answer>}`. A read, so not
  held on a stale link. Shown in place of the briefing, with "Since you last
  talked to Jarvis, on either app: ... Put together on your PC without the AI
  model." under it, until the next read. The lines are hidden with the
  private lists exactly as the briefing's are (the desktop's Rust, the
  phone's `Briefing.hide`). A PC from before it ignores `missed` and sends an
  ordinary briefing; both apps then say "Your PC's Jarvis does not have "What
  did I miss?" yet - run apply-patches.ps1 on the PC." No notification is
  ever made for it, so nothing of it reaches a lock screen.

### 22.8 The calendar's second source: a private calendar link (added 2026-09-25)

The owner's decision (2026-09-25): Jarvis may read Google Calendar through
its **private link** ("Secret address in iCal format"), read-only, the link
kept like a password. No route, no event and no app screen changes: it is a
PC setting, the environment variable `JARVIS_CALENDAR_ICS_SECRET_URL`
(steps: `backend/README.md`, "Google Calendar, by its private link"), and
there is no way to type it into either app.

- **The same tool, gate action and tier** as the CalDAV read:
  `calendar_read`, gate action `calendar_read` (`jarvis_calendar_read_run`),
  shipped `auto`. When both are set, the private link wins and the card
  says the CalDAV address was not read.
- **One GET** of the link, with no password or header of its own (the link
  is the key). The card names only the calendar and the host: "Jarvis would
  like to read your Google Calendar (private link) ... 1 request, to
  calendar.google.com". The link itself is never in the card, the plan, the
  tool's result, an error, the log, the bus or the audit log.
- `https://` only (plain `http://` only inside the owner's own networks,
  the same rule as the CalDAV address). A redirect is followed only to
  https on the same host or between `calendar.google.com`,
  `www.google.com` and `google.com`, at most three times.
- The whole calendar comes back; at most 10 MB of it is read, for at most
  30 seconds, and the days asked for are picked out on the PC. A result cut
  short says so: `"incomplete": true` and a `"note"` in the tool's result,
  and "Some may be missing" in the briefing's calendar summary.
- `GET /api/briefing`'s `sources.calendar.said` names the source in use:
  "Included: your Google Calendar (private link)." (the only place either
  app shows which calendar is read).

## 23. Web search (added 2026-09-25)

The owner's decisions of 2026-09-25 (`CLAUDE.md`, "Web search with a choice
of providers" and "When a search asks first"). `backend/jarvis_search.py`
(shipped whole), `backend/web-search.patch` (the routes and the gate's words),
and the model tool `web_search` in `backend/jarvis_agent.py`. **Both apps
call all three routes**: the desktop's Settings, "Web search"
(`web_search.rs`: `get_web_search`, `set_web_search`, `test_web_search`,
Settings window only; `web-search-settings.js`, `web-search.js`), and the
phone's Brain, "Web search" (`WebSearchPlate.kt`, `net/WebSearch.kt`) - on the
phone, settings for a PC feature live on the phone's Brain screen. `ported` in
`tools/check_parity.py`. The contract file both apps build against is
`tests/fixtures/web-search-cases.json` / `contract/web-search-cases.json`,
written by `tools/gen_web_search_cases.py` from the real code.

### 23.1 The five providers

| id | label | where the words go | needs |
|---|---|---|---|
| `searxng` (**default**) | SearXNG (on this PC) | the owner's own SearXNG, `http://127.0.0.1:8888` unless set otherwise - which asks several search engines itself | Docker, and `json` added to its `formats` (it ships `html` only; without it SearXNG answers 403) |
| `duckduckgo` | DuckDuckGo | `html.duckduckgo.com`, through the `ddgs` package with `backend="duckduckgo"` ONLY | `py -3 -m pip install ddgs` |
| `exa` | Exa | `POST https://api.exa.ai/search`, `x-api-key: <key>`, body `{"query", "numResults": 5, "contents": {"highlights": true}}` (address, header and field names read from the official exa-py 2.22.2 source); the snippet is the page's highlighted passages joined, else the start of its text - page content, so outside text, cut to 300 characters like every snippet | a key (free, no payment card) |
| `tavily` | Tavily | `POST https://api.tavily.com/search`, `Authorization: Bearer <key>` | a key (free, no payment card) |
| `brave` | Brave Search | `GET https://api.search.brave.com/res/v1/web/search?q=...&count=5`, `X-Subscription-Token: <key>` | a key, and an account with a payment card - **charged past the free monthly credit** |

Whoogle is left out, and `left_out` says why (both apps show it): "Not
offered: its own README says it no longer returns results, since Google
blocked searching without JavaScript in 2025."

Brave was removed and added back on the same day (the owner, 2026-09-25):
it stays, fifth, and its "why use this one" line says plainly that it can
cost money: "Brave's own independent index, with about $5 of free credit each month (roughly 1,000 searches). Needs an account, a payment card that is charged if you go past the free credit, and a key, and Brave sees what you search, tied to your key."

Each provider's **"why use this one"** line (`why`) comes from the PC and both
apps show it word for word; each app also carries a copy, used only when an
answer lacks it, and `backend/test_web_search.py` checks all three are the
same words. `jarvis_quick.py` answers "which search should I use?", "why
SearXNG?", "why Exa?" from the same words without the model, and
"use DuckDuckGo for web search" / "switch web search to Exa" changes the
provider at once (the owner's own typed or said words only, like every fast
path).

**The SearXNG address** may be this PC or the owner's own networks only -
`jarvis_local_http`'s rule (this PC, private addresses and `.local` names,
Tailscale, NordVPN Meshnet), judged by spelling, for `http://` and `https://`
alike. It is reached with NO proxy. No user name, password, `?` or `#` part.

**No silent fallback.** A search goes to the chosen provider or nowhere. When
it cannot run - SearXNG not running, its JSON off (403), no key, a key
refused, the month's credits used up, rate-limited, `ddgs` not installed or
without its DuckDuckGo engine - the answer says so in plain words and adds an
offer, e.g. "Switch web search to DuckDuckGo? Say "use DuckDuckGo for web
search", or choose it in Settings, Web search." Nothing is tried elsewhere.

### 23.2 Routes

Every route needs the pairing token and passes the origin check.

| Route | Body | Answers | Notes |
|---|---|---|---|
| `GET /api/search` | - | 200 view (below); 503 `{"available": false, "error": <exception name>}` without `jarvis_search.py` | A read. |
| `POST /api/search/settings` | exactly ONE of `{"provider": id}`, `{"searxng_url": address}` (`""` = the default), `{"ask_every_time": bool}` | 200 `{"ok": true, "said", ...view}`; **202** `{"ok": true, "waiting": true, "said"}` for `ask_every_time: false` (ONE card); 400 `{"ok": false, "error"}` (two fields, an unknown provider, an address outside the owner's networks); 503 when `stop_asking_before_every_web_search` is not tier `ask` | Held on a stale link in both apps. There is **no field and no route for a key**. |
| `POST /api/search/test` | `{}` | 200 `{"ok", "state", "said", "provider", "offer"?, "results"?: n}` | ONE search for the fixed word `wikipedia` through the chosen provider; no card (fixed words, the owner pressed the button). A real search: one Tavily credit, or a little of Exa's free credit. Held on a stale link in both apps. |

The view:

```
{"available": true, "provider": "searxng" | ... | null (damaged settings),
 "why": "" | why nothing is searched, "default": "searxng", "default_why",
 "providers": [{"id", "label", "why", "needs_key", "key_saved": bool | null,
                "key_where", "needs_docker", "ready", "state", "said"}],
 "left_out": [{"id": "whoogle", "label", "why"}],
 "searxng_url", "searxng_default", "ask_every_time", "ask_every_time_label",
 "ask_every_time_detail", "key_entry", "test_query": "wikipedia",
 "waiting": bool, "last": {"outcome", "why", "at", "message"} | null}
```

`state` (and a test's `state`) is one of `works`, `not_running`, `json_off`,
`key_missing`, `key_refused`, `quota_used`, `rate_limited`, `not_installed`,
`no_results`, `timeout`, `not_allowed`, `failed`, `secret`,
`settings_damaged`, `empty` - for an icon; the apps show `said`. `ready` is
worked out without a socket, so SearXNG shows ready until a search or a test
finds it is not running.

Settings live in `<config folder>/web-search.json` (no key, no search words).
No file: SearXNG on this PC, not asking every time. A damaged file fails
closed both ways: no provider (nothing is searched, `why` says so) and "ask
every time" on.

### 23.3 When a search asks first

In the chat loop (`jarvis_agent._web_search_call`), never through a tier
alone:

- **No card** for a search straight from the owner's own question: the
  newest message typed or said by the owner (`typed` / `voice`), nothing
  read from outside in this turn, the conversation not tainted, no
  sensitive saved fact in the turn and no saved fact repeated in the search
  words, no text the app attached. Since the owner's decision after the
  creativity audit (2026-09-25), a pinned or recalled fact on its own no
  longer makes a search ask.
- **One card** (gate action **`search_the_web`**, tier `ask` in the shipped
  toml; `"ask"` by `unknown_action_tier` without the line) showing the
  **exact search words**, where they go, whether a key goes with them and
  what saying no costs, plus the reason, whenever any of these holds: a
  reading tool ran this turn (an earlier web search included); the
  conversation read outside text before (`jarvis_chat_log` taint);
  `memory_search` ran this turn (a tool's answer, like any reading tool); a
  fact in the chat route's quoted FACTS block (pinned facts too) is
  **sensitive** (`jarvis_search.fact_topic` - `jarvis_sensitive`'s
  patterns, no model; a fact that cannot be checked counts as sensitive); the
  **search words repeat a fact** in that block (below); the facts could not
  be checked at all; the newest message was pasted,
  shared, from the clipboard, a picture's caption or untagged; the app sent
  a `system` message; or **"Ask before every web search"** is on. "What
  shaped this request:" follows, as on every card after outside text. It
  runs only when the verdict records a person approving - a toml that sets
  `search_the_web` to `auto` gets the search refused, never sent unasked. The
  card counts toward the five-cards-per-answer limit.
- **Refused, never a card**: search words holding what looks like a password
  or key (`jarvis_router.looks_like_a_secret`, `jarvis_scrub.find_secret`,
  which also knows this PC's own secrets by value) - the answer names the
  kind, never the value; `search_the_web = "never"` in the toml (web search
  switched off); and a provider that cannot run (see 23.1).

**"The search words repeat a saved fact"** (`jarvis_search.repeated_facts`,
no model, no socket): each fact in the turn's FACTS block is cut into its
distinctive pieces - words that are not everyday words (`_EVERYDAY`),
numbers of three digits or more that are not years (a phone number written
with spaces counts as one), and, from the names layer
(`jarvis_search.names_for_facts`, `jarvis_memory`'s entities on this PC),
the names, other names and nicknames of anyone or anything the fact
mentions. A piece the owner typed or said themselves in this conversation
does not count - it is their own words. Any other piece in the search words
and the search asks. The card then says which fact: "The search words
repeat something you told Jarvis (“Leeds”), so it asks before searching.
The saved fact: “Owner lives in Leeds”" - and for a sensitive fact only the
matching words from the search itself and the topic ("It comes from a saved
fact about another person, so that fact's own words are not shown here").
A sensitive fact asks on its own: "Jarvis used a saved fact about health for
this question, so it asks before searching ...". **The honest limit:** a
fact said in other words ("vegetarian" saved, "meat-free" searched) is not
caught by comparing words; sensitive facts ask whatever the words say, and
the test suite pins this limit so it is not forgotten
(`test_web_search.t_saved_facts_ask_only_when_repeated_or_sensitive`). An
everyday fact about another person ("Owner's sister Priya likes jazz") is a
normal fact (the owner's decision of 2026-09-26: everyday facts about people
are normal everywhere): it asks only when the search words repeat it, like
any other. A fact about someone's health, money, address, contact details,
debts or secrets is still sensitive, so a PINNED fact like that still makes
every search in the answer ask (`test_sensitive.
t_everyday_people_facts_are_normal_when_used`).

**"Ask before every web search"**: turning it ON is immediate; turning it
OFF is ONE approval card, **`stop_asking_before_every_web_search`** (tier `ask`; any other
tier and the route answers 503), like the other settings that loosen
something. Turning it on while that card waits withdraws the card. A "no" on
either card never becomes a proposed memory rule (`gate-outcome.patch`'s
list). The notices: `search_the_web` is outbound ("Jarvis wants to search the web",
heavy), `stop_asking_before_every_web_search` local.

**Results are outside text**: at most 5, each `{title, url, snippet}` (title
150 characters, snippet 300, tags and control characters removed, only
`http(s)` links). The model reads them labelled as outside data and checked
for planted instructions; the turn records `web_search` in `tools_ran`, so
the rest of the conversation counts as having read outside text.

### 23.4 The keys (rule 3)

The Exa, Tavily and Brave keys live in **Windows Credential Manager** on the
PC, as `Jarvis Backend/Exa key`, `Jarvis Backend/Tavily key` and
`Jarvis Backend/Brave Search key` (UTF-8,
the same format as the pairing token). They are entered **on the PC only**:
the desktop's Settings, Web search (`save_search_key` / `forget_search_key`,
written by Rust straight into Credential Manager - never sent over HTTP), or
`py -3 jarvis_search.py key exa` (or `key tavily`, `key brave`) in the backend folder (it asks for the
key without showing it). **The phone has no way to enter one** (ARCHITECTURE
section 8). A key is read fresh for each search, registered with the log
scrubber (`jarvis_scrub.register_secret`), sent only to its own service's
fixed `https` address, never after a redirect, and never put in a plan, a
card, an answer, an error, the settings file or a log. `GET /api/search`
says only `key_saved: true|false`.

### 23.5 Known gaps, said plainly

- **Brave can cost money, and Jarvis cannot stop it.** Past the free monthly credit Brave charges the card and answers as usual - it does not refuse - so nothing Jarvis sees tells a free search from a paid one. There is no guard against that in Jarvis. The only limit is the one you set in Brave's own dashboard (a spending limit, if Brave offers one for your plan - not checked here). Brave's 402 and 429 answers are said in words (402: "your free credit for this month is used up, or your payment card was not accepted"), but by the time Brave is billing, it no longer sends them for going over the credit.
- **Nothing here has reached a real SearXNG, DuckDuckGo, Exa, Tavily or
  Brave.** Every test uses local stand-in servers and a stand-in `ddgs`.
  The error codes for "credits used up" (Tavily 432/433; Exa 402, and 429
  read as "too many searches, or the credit is used up"; Brave 402/429, and
  401/403/422 for a refused key) are not seen: Tavily's and Brave's from
  their documentation as understood, Exa's assumed - exa-py only raises on any
  status of 400 or more, so it says nothing about which means what. Exa's
  free credit ($10 a month, roughly 1,400 searches, no payment card) and
  its dashboard address come from web search summaries on 2026-09-25, not
  from Exa's pricing page, which was unreachable. Brave's "roughly 1,000 searches" for
  the $5 credit is not checked against Brave's price list either.
- DuckDuckGo through `ddgs`: whether its HTTP client (`primp`) uses the
  Windows system proxy is not checked; Jarvis passes it none. `ddgs` cannot
  tell "no results" from "blocked for a while", so the answer says both.
- The phone learns of a setting changed on the desktop at its next read
  (Refresh or opening the Brain) - there is no event for it.
- "Saved memories were read" is judged on THIS turn (the FACTS block, or
  `memory_search`); an earlier turn's recalled facts are not tracked, so a
  later search in the same conversation that has read nothing else runs
  without a card.

## 24. What Jarvis can reach (added 2026-09-25)

The Muse audit (`docs/COMPETITORS-MUSE-2026-09-25.md`, idea 1): Meta's
Muse described its own access wrongly. This list is written by **code**
from the PC's own settings, never by the model. `backend/jarvis_reach.py`
(shipped whole) and `backend/reach.patch` (the route). **Both apps show
it**: the desktop's Settings, "What Jarvis can reach" (`reach.rs`
`get_reach`, Settings window only; `reach-settings.js`, `reach.js`), and the
phone's Brain, "What Jarvis can reach" (`ReachPlate.kt`, `net/Reach.kt`).
`ported` in `tools/check_parity.py`. The contract file both apps build
against is `tests/fixtures/reach-cases.json` /
`contract/reach-cases.json`, written by `tools/gen_reach_cases.py` from the
real code.

### 24.1 The route

`GET /api/reach` - behind the origin check and `X-Jarvis-Token`, like every
other read. **A read**: it changes nothing, opens no socket, starts or wakes
nothing (not the second card, not the big model), writes no file - so
neither app holds it on a stale event stream. An older PC answers 404; a PC
without `jarvis_reach.py` answers 503 `{"available": false}`, and both apps
then say "Your PC's Jarvis cannot list what it can reach yet - run
apply-patches.ps1 on the PC."

```
{"available": true, "written_by": "code",
 "title", "detail", "tools_title", "tools_none", "everything_else",
 "where_label": "Goes to", "asks_label": "Asks you first",
 "on": 4,                                   how many rows are on
 "rows": [{"id", "name", "state": "on"|"off"|"not_set_up"|"blocked",
           "on": bool, "state_words": "On", "where": "imap.example.com",
           "asks": "Yes, every time", "line": "one plain sentence"}, ...],
 "tools": [{"id": "web_search", "name": "Web search"}, ...]}
```

The rows, in this order (`jarvis_reach.KINDS`): the cloud model; web search;
calendar (reading); email (reading); email (sending - "not set up" until
sending is built; adding it is one `KINDS` entry); Home Assistant (reading);
Home Assistant (changing things); notes (searching); notes (writing); GitHub
research; phone notifications (ntfy); computer control; browser control;
phone control; commands on this PC; the second graphics card; the big model.
`tools` is the list the chat's tool loop offers the model
(`jarvis_agent.offered_tools()` of `[tools].enabled`), in plain names.

Both apps show a row as "`name` - `state_words`", then, only when it is on,
"Goes to: `where`" and "Asks you first: `asks`" (not when `asks` is "-"),
then `line`. The words are the PC's; the apps add none.

### 24.2 Where each part comes from

- **On or off**: the tool's name in `[tools].enabled` (read the way the
  morning briefing reads it) AND its account set up - the same environment
  variables each module reads (`JARVIS_IMAP_HOST`, `JARVIS_CALDAV_URL` or
  `JARVIS_CALENDAR_ICS_SECRET_URL`, `JARVIS_HOME_URL`, the notes settings,
  `JARVIS_NTFY_TOPIC`). Browser control also needs the second card's
  "Browser control" switch on (its switch file; nothing is probed, so it
  says "switched on", not "working").
- **Asks first**: the tool's gate action (jarvis_gate's own
  `action_for_tool` when it is there, else the names `backend/README.md`
  lists) and that action's tier in `[autonomy.tiers]`. The six tools the
  loop only ever runs on a person's yes (`NEEDS_A_PERSON`: GitHub, browser,
  computer, phone, commands, Home Assistant changes) say "Yes, every time"
  whatever the tier (seven since `send_email`; Home Assistant changes say
  "Yes, every time - except the lights, plugs and fans you name yourself
  (your setting)" while "Lights, plugs and fans without a card" is on,
  section 33); tier `never` is "blocked"; note writes say they ask after
  outside text; web search says when it asks (23.3).
- **The cloud model**: the chat route's own `_lane_names()` when the list is
  made inside the server; otherwise the same file it reads
  (`litellm-proxy.yaml`: lane names and the provider part of `model:`
  lines only).
- **Web search**: `jarvis_search.settings()`, and whether a key is saved
  (yes or no).

### 24.3 What is never in it

No password, key, token, private calendar link, ntfy topic or full address.
"Where it goes" is a **host name** (`imap.example.com`,
`calendar.google.com`, "this PC"); the email row adds the account's user
name ("imap.example.com (as me@example.com)"). `backend/test_reach.py` sets
fake secrets (built by concatenation) for every one and checks none reaches
the list, the spoken answer or the route.

### 24.4 "What can you reach?" without the model

`jarvis_quick.py` answers "what can you reach?", "what can Jarvis access?",
"what do you have access to?", "what are you connected to?" and close
phrasings (whole sentences only, the owner's own typed or said words) from
`jarvis_reach.sentence()` - the same list, in one answer, host names only
(no account name). A near miss ("what can you reach on the top shelf") goes
to the model, as does pasted text.

### 24.5 Known gaps, said plainly

- The gate on the owner's PC (`jarvis_gate.py`) is not in this repository.
  When it cannot be asked, the tool's action comes from the names
  `backend/README.md` lists; the tiers themselves are always read from the
  owner's `jarvis-framework.toml`.
- "On" means switched on and set up, not "has worked": nothing is tried.
  An email row can be on while the password is wrong.
- The phone and the desktop learn of a change at their next read (Refresh,
  opening the screen, or an answered card on the desktop) - there is no
  event for it.

## 25. One-time codes and sign-in links hidden in email (added 2026-09-25)

The Muse audit (idea 2). Every subject, preview and sender name
`jarvis_email.py` reads goes through `jarvis_mail_mask.hide()` (shipped
whole) before anything else sees it - so the model (`email_check`), both
apps, the morning briefing's sender names and anything written to a log only
get the hidden version. "Your code is 482913" becomes "Your code is [a
one-time code, hidden]"; a password-reset, magic sign-in, verify or confirm
link becomes "[a sign-in link, hidden]"; a link carrying a long
random-looking piece becomes "[a link with a private code, hidden]". The
preview is hidden first and cut at 400 characters after, never leaving half
a marker. Without `jarvis_mail_mask.py` the text is withheld ("[not shown:
jarvis_mail_mask.py is missing on this PC]"), never shown as it is.

What counts as a code: 4 to 8 digits, "123-456", "G-482913", or capitals
and digits ("X7K9P2", only right after "code"), near a code word (code, OTP,
passcode, verification, one-time, 2FA, two-step, security code, PIN, sign
in, log in) - or anywhere in a message whose subject says so ("Your
verification code"). Kept: prices, percentages, years, order / invoice /
booking / tracking / account numbers, phone numbers, dates and ordinary
links. `backend/test_mail_mask.py`: 27 cases hidden, 26 kept, and of
AgentDojo's 180 ordinary texts only the three that really are a code or a
reset link change. It also hides some things it need not: a discount or
error code right after "code" ("promo code SAVE20"), an unlabelled number
near "sign in" or "log in", and any link with a long random piece (a
newsletter's tracking link included).

**What it cannot catch**: a code with no code word near it and none in the
subject; a code written in words, split oddly, in a picture, or in an
HTML-only email (those have no preview at all); code words in other
languages; a link without `http://` or `www.`; a sign-in link with neither a
telling word nor a long random piece; anything past the first 1,600
characters. It lowers the risk; it does not make an email safe to send
anywhere.

## 26. Sending email (added 2026-09-25)

The owner's decision of 2026-09-25, after the audit against Meta's Muse
(`CLAUDE.md`: "Jarvis may SEND email, one approval card per email, the card
showing the exact recipients, subject and full text; never an 'always
allow'; the card says plainly when the conversation has read outside
text"). `backend/jarvis_email_send.py` (shipped whole),
`backend/email-send.patch` (one route and the gate's words), and the model
tool `send_email` in `backend/jarvis_agent.py`. `jarvis_email.py` stays
read-only. A new way out of the PC: docs/ARCHITECTURE.md section 4,
"sending email".

**Both apps**: every email is an ordinary approval card in `/api/pending`,
answered through the same Approve and Deny as every other card (section 3).
The one route below is the Settings line: the desktop's Settings, "Sending
email" (`email_sending.rs` `get_email_sending`, Settings window only;
`email-sending-settings.js`, `email-sending.js`), and the phone's Brain,
"Sending email" (`EmailSendingPlate.kt`, `net/EmailSending.kt`). `ported` in
`tools/check_parity.py`. The contract file both apps build against is
`tests/fixtures/email-sending-cases.json` /
`contract/email-sending-cases.json`, written by
`tools/gen_email_sending_cases.py` from the real code - the route's answers
and one real card.

### 26.1 The card

Gate action `send_email`, tier `ask` in the shipped `jarvis-framework.toml`
(it was already there). One card per email; two emails are two cards, each
counted toward the five cards one answer may raise (`CARDS_PER_TURN`). The
row's `detail` is `{"text": <the card>}`, and the card is the WHOLE email -
never cut: a card that would not fit the gate's 4,000 characters is refused
before anyone is asked. An example, word for word (the fixture's
`example_card`):

```
Send this email from your account? It goes only if you approve, exactly as shown - every word is below.

From: owner@example.com
To: alex@example.com
Cc: sam@example.org
Subject: Dinner on Friday

---------- the whole email ----------
Hi Alex,

Friday at 7 works for me. [the menu](https://example.com/menu)

**See you there.**

Mario
---------- end of the email ----------

No attachments, no hidden (Bcc) recipients.
It goes through smtp.office365.com, port 587, encrypted before logging in (STARTTLS - if the server will not encrypt, nothing is sent). Jarvis logs in there as owner@example.com; your password goes to that server and nowhere else.
Once sent, an email cannot be taken back.

If you say no: nothing is sent, and Jarvis tells you it was not sent.
```

When outside text shaped the turn - a reading tool ran (the inbox, a file,
a web page...), the conversation had read outside text before, the newest
message was not typed or said by the owner, or the app sent text of its own
- the card STARTS with one plain line, before "Send this email...":

```
This conversation read outside text (an email, a web page, a file or another tool's answer) before this email was written - check that sending it was your idea.
```

(or "Your newest message was pasted in, not typed - check that sending this
email was your idea.", or the app's-own-text line), and ends with the usual
"What shaped this request:" list, which names an address that came from
what Jarvis read rather than from the owner.

**What each app must do with it** (both do):

- Show `detail.text` WORD FOR WORD, and all of it. The phone's card shows
  it as plain text in the scrolling approval list (`PendingRows.kt`
  `summary`). The desktop's Jarvis bar shows an email's card in a `<pre>`
  (`main.js`, `isEmailCard`), never through the Markdown renderer - which
  would show `[the menu](https://...)` as "the menu" and hide where the link
  goes - wrapped, in the scrolling preview.
- Never approve an email from a one-line surface. The desktop's widget
  shows "An email - open the Jarvis bar to read all of it before
  approving." and its button opens the Jarvis bar on the card; Rust refuses
  an email's Approve from the widget as well (`commands.rs`
  `waiting_email`). Deny works from anywhere.
- Lock screens, notifications, the phone's home-screen widget and the
  desktop's widget under App lock show the `notice` only - "Jarvis wants to
  send email" and "sends the email shown on the card from your own account,
  to exactly the people it lists; once sent it cannot be taken back.
  nothing has happened yet." - never a recipient, the subject or a word of
  the text. `weight` is `heavy` (it leaves the PC and cannot be undone).
- A "no" proposes no memory rule (`_NO_RULE_FROM_DENIAL`): it answers one
  email, not a standing wish.

### 26.2 When it is refused with no card at all

The model is told why, in words, and nobody is asked:

- the turn's model is not on this PC - an Ollama cloud model, or
  `OLLAMA_URL` pointing at another machine (rule 1: an email is written by
  the local model only; the whole turn is refused up front for the same
  reason, and `_one_call` checks again);
- `send_email` is not tier `ask` (`auto` or `notify` would send with nobody
  asked; `never` switches sending off);
- the plan says why nothing could be sent: an address that is not a plain
  address (no names, commas or line breaks), more than 10 people in To and
  Cc, no subject or one over 200 characters or holding a line break, no
  text or more than 2,500 characters, an invisible or control character
  (a right-to-left override, a zero-width joiner) that would make the card
  read differently from what is sent, or sending not set up;
- the card would not fit whole on one card.

A tool call is offered only when `[tools].enabled` names `send_email`.

### 26.3 What is sent

Exactly the plan the card showed: `From` (the owner's account), `To`, `Cc`,
`Subject`, `Date`, a `Message-ID`, and the text as `text/plain; charset=utf-8`
- no Bcc, no attachment, no HTML. A reply (`plan(..., reply_to_message_id=)`)
adds `In-Reply-To` and `References`; the model's tool does not offer it yet
(24.5). `run()` refuses, and sends nothing, if the plan's fingerprint no
longer matches (its content changed after the card was made) or the account,
server or encryption setting changed since. It sends once and never retries:
a connection that drops after the email was handed over is reported as "may
have been sent - check your Sent folder".

### 26.4 The route

Needs the pairing token and passes the origin check.

| Route | Body | Answers | Notes |
|---|---|---|---|
| `GET /api/email/sending` | - | 200 view (below); 503 `{"available": false, "error": <exception name>}` without `jarvis_email_send.py` | A read of the settings only: connects to no mail server and sends nothing. |

```
{"available": true,
 "state": "not_set_up" | "tool_off" | "refused" | "off" | "ready",
 "ready": bool, "said": <the one line both apps show>,
 "from": "owner@example.com" | "", "server": "smtp.gmail.com", "port": 465,
 "encryption": "ssl" | "starttls" | "off", "server_guessed": bool,
 "password_set": bool,          never the password
 "tool_enabled": bool,          "send_email" in [tools].enabled
 "limits": {"recipients": 10, "subject_chars": 200, "body_chars": 2500,
            "attachments": false}}
```

Both apps show `said` as it is. The settings are environment variables on
the PC (`backend/README.md`, "Sending email"): the account and password are
`JARVIS_IMAP_USER` and `JARVIS_IMAP_PASSWORD`; the server is `smtp.X` for
`JARVIS_IMAP_HOST = imap.X`, or `JARVIS_SMTP_HOST` / `JARVIS_SMTP_PORT` /
`JARVIS_SMTP_TLS`. Neither app has a box for any of them.

### 26.5 Known gaps, said plainly

- **Nothing has reached a real mail server.** Every test uses a stand-in
  SMTP server on 127.0.0.1 written with the standard library
  (`backend/test_email_send.py`): SSL, STARTTLS, a server that will not
  encrypt, a refused login, refused recipients, a dropped connection. That
  Gmail takes the same app password for sending (`smtp.gmail.com`, port
  465) is general knowledge of how Google's app passwords work - not
  checked here against a real account, and Google's pages were not read
  for it.
- **The model cannot thread a reply yet.** `email_check` does not return a
  message's `Message-ID`, so the tool does not offer `reply_to_message_id`;
  the module supports it. A reply is a new email with "Re:" in its subject
  until then.
- **The Sent folder.** Gmail files a copy of what it sends by itself; other
  providers may not, and Jarvis does not save one.
- **Plain ASCII addresses only**; no Bcc; no attachments; no HTML.
- A program already on the PC could approve a card with the pairing token,
  without Windows Hello - the known limit in docs/ARCHITECTURE.md section 3,
  which the owner chose to close later. It applies to an email's card as to
  every other.

---

## 27. How Jarvis talks: warm and brief, or plain (added 2026-09-25)

The owner's decision: "Jarvis's manner: warm and brief by default, with a
'Plain' option in both apps' settings. Manner never changes what Jarvis does,
asks or remembers - only how it phrases things." `backend/jarvis_manner.py`,
`backend/manner.patch`.

### 27.1 Routes

| Route | What |
|---|---|
| `GET /api/manner` | `{"available": true, "manner": "warm"\|"plain", "default": "warm", "title", "detail", "spoken", "choices": [{"id", "label", "why"}]}` - the words both apps show. |
| `POST /api/manner` | `{"manner": "warm"}` or `{"manner": "plain"}` - at once, 200 `{"ok": true, "said", ...view}`. **No approval card either way**: it does not trust, show or send anything more. Anything else is 400. Both apps hold it on a stale link like every change. |

Without `jarvis_manner.py` the routes answer 503 `{"available": false}` and
answers are worded as before.

### 27.2 What it changes, and only this

- **One short system line for THIS PC's model**, added by
  `jarvis_agent.run_local_turn` just before the newest question - never first,
  so the Jarvis rules block stays first (`keep_rules_first` runs after it), and
  before the spoken-style note, so that one is nearest the question and wins on
  length. Warm: friendly, brief, natural; no gushing, no filler such as "Great
  question!", no emoji unless the owner uses them. Plain: neutral and
  businesslike. Both lines say they are about wording only and that every rule
  still applies ("still say what is a guess, and never claim an action was
  taken when it was not"); `backend/test_manner.py` holds them to that.
- **Never to the cloud.** The line is added to the request for this PC's
  model only, never to the conversation the app sent, so the relay (which gives
  a cloud lane the newest user turn and nothing else, `cloud-one-turn.patch`)
  never sees it.
- **The fast path's fixed answers** (`jarvis_quick.py`: timers, reminders, the
  to-do list) have a warm wording for each short reply - "Got it - timer set
  for 10 minutes." beside the plain "Timer set for 10 minutes." - with every
  fact taken over word for word (checked). Lists read out, a briefing, the
  repeating job's card line and errors are the same in both.

### 27.3 In the apps

Desktop: Settings, "How Jarvis talks" (two choices with the PC's words).
Phone: Brain, "How Jarvis talks". The same words in both, checked against
`plain-error-cases.json` (`manner`).

### 27.4 Known gaps, said plainly

- An 8B model follows a tone line loosely; nothing measures how warm or plain
  its answers really are.
- A turn with tools switched off in `jarvis-framework.toml` is relayed to
  Ollama without `run_local_turn`, so it gets no manner line - the same gap the
  spoken-style note has.
- The big model's deep questions and the wiki builder do not use it.

## 28. Stop everything (added 2026-09-25)

The owner's decision of 2026-09-25 (CLAUDE.md, after the "Build Your Own
Jarvis" prompt pack): one control that halts whatever Jarvis is doing, at
once. Served by `backend/jarvis_stop_all.py`, which `backend/stop-all.patch`
installs round the server's POST handler at start-up (the same shape as
`owner-check.patch`).

| Route | Body | Answers | Notes |
|---|---|---|---|
| `POST /api/stop_all` | `{}` (ignored) | 200 `{"ok": true, "stopped": [sentence, ...], "problems": [sentence, ...], "message", "at"}`; 401 no or wrong token; 403 another website's page; 404 on a PC without `stop-all.patch` | Never a card. Never held on a stale event stream or by a waiting card - in the apps or on the PC - and the desktop's hotkey works while App lock is on (on the phone, the button is on Home, behind App lock like the rest of the app). `message` is "Stopped everything. " plus every `stopped` sentence, or "Nothing was running, so there was nothing to stop."; each `problems` sentence is added after. |

**What one call does**, in this order:

1. The task Stop (`/api/task/stop`, section 11): a running multi-step task
   (computer, browser or phone control) stops before its next step, and a
   paused one is forgotten. Named in plain words ("computer control").
2. The chat answer being written uses no more tools. Every tool call it
   asks for from then on is refused before the gate ("refused: the owner
   pressed Stop everything ..."), and a call whose card is approved AFTER
   the press does not run either. The answer says so once, in its own
   words: "(Stopped: you pressed Stop everything, so Jarvis did not use
   <tool> or anything else in this answer.)". A plan that began just after
   the press reads "stop" at its first checkpoint. The next question is not
   affected.
3. Every stopper registered with `jarvis_stop_all.register(name, fn)` is
   called in turn (focus sessions register one, which pauses a running
   session). Each returns one
   sentence, or nothing when it had nothing running; one that raises is
   reported in `problems` and the rest still run.

It never approves, denies or answers a card (a waiting card stays waiting),
never resumes or starts anything, and never asks the gate anything. The
audit log gets one line, `stop_all`, with counts only.

**Speech is the apps' own.** The backend plays no sound, so each app stops
its own speech first, before it even calls the route - a dead link never
keeps Jarvis talking - and puts "Stopped speaking." before the PC's
`message`:

- **Desktop:** the global hotkey "Stop everything", **Alt+Shift+X** by
  default, rebindable in Settings, Hotkeys (`hotkeys.rs`), and listed in the
  quickbar's primer. It tells every window to stop speaking (the quickbar's
  `stopSpeaking`, and the HUD window's browser speech), then calls the route
  (`commands.rs` `stop_everything_now`) and shows the answer in a
  notification titled "Stop everything". Why that key: `backend/README.md`,
  "Stop everything". The same command is a **"Stop everything" row in the
  tray menu** (2026-09-26), for a mouse or when another program holds the
  key; never greyed, not by a stale link, App lock or a waiting card. A
  focus line already being made when it is pressed is dropped when it
  arrives (`focus.rs` `play_callout`).
- **Phone:** a "Stop everything" button on Home, shown whenever Jarvis is
  doing anything (the PC's activity is not idle, an answer is arriving, or
  the phone is speaking). It stops the phone's speech, calls the route and
  puts the answer in the shared notice (`net/StopEverything.kt`,
  `JarvisRuntime.stopEverything`).

Both apps say the same sentences: "Stopped speaking." and then the PC's
`message`, or "Jarvis stopped what it was doing." when it sent none. When
the PC could not be reached: "Stopped speaking. Nothing else could be
stopped." and then the plain words for why ("Your PC isn't answering. ...",
section 4 - never the address or the network library's text; the phone's
notice carries their button). A 404 in either app says "This PC's Jarvis
cannot stop anything else yet - run apply-patches.ps1 on the PC
(stop-all.patch)". Neither app hides the
control when `capabilities.stop_all` is false: stopping its own speech is
worth doing anyway, and a stop button must not depend on a handshake.

`GET /api/version`'s `capabilities.stop_all` is true once the running server
answers the route (asked of `jarvis_stop_all.armed()`, like `owner_check`).

**What it cannot do**, said plainly: a step already under way finishes (a
click being made, a command already running, one page loading) - the stop
lands before the NEXT step. A timer or reminder still goes off later.
Pressing it on one app does not stop the other app's speech.

## 29. The live preflight (added 2026-09-25)

`py -3 backend\selftest.py --preflight` asks the RUNNING Jarvis every
question a live chain depends on and prints PASS / FAIL / WARN per check,
ending "N pass, N fail, N warn" (`backend/README.md`, "The preflight"). It
uses only routes above, read-only: `GET` `/api/status`, `/api/version`,
`/api/pending` (with no token, to see it refused), `/api/reach`,
`/api/schedule`, `/api/events`, `/api/voice/status`, `/api/search`; `POST`
only `/api/chat` (one fixed question, as a temporary chat, and only when no
tool is switched on unless `--with-chat`) and `/api/search/test` (only when
web search is on and a provider is chosen). It never calls `/api/approve`,
`/api/deny`, `/api/power`, a model route or `/api/stop_all`. It also asks a
list of addresses that must never serve a file (the settings file, the
databases, the token) and fails loudly if one does.

**Home Assistant** (added 2026-09-26, the feasibility audit's I81): when
`JARVIS_HOME_URL` and `JARVIS_HOME_TOKEN` are set, it asks the owner's own
Home Assistant two things that read nothing of the house - `GET /api/`
(does it accept the token?) and `POST /api/template` with the constant
`{"template": "ok"}`, which Home Assistant renders only for an
ADMINISTRATOR's token (`jarvis_home.check_token`). An administrator's token
is a WARN pointing to `backend/README.md`, "Home Assistant: a user of its
own for Jarvis"; a plain user's is a PASS. With `--with-reads` it also reads
the weather once and prints only how many days came back. Both go straight
to the owner's Home Assistant with its own token (never to the Jarvis
server), never through a proxy for plain `http://`, and never onto a
redirect.

`GET /api/version` now also carries `started` (epoch seconds: when the
server process started), which the preflight compares with each shipped
module's file time - a module changed after the start may not be the code
the running server uses.

## 30. "Tell me when ..." and urgent alerts (added 2026-09-25)

The owner's decision (`CLAUDE.md`, after the prompt pack): "Urgent alerts
without phone calls: 'tell me when ...' (a named sender's email, a device
change) set up with one card; a match only notifies - urgent ones as a
phone notification that keeps ringing until seen. No telephony service: a
call would send private text to an outside voice company (rule 1)." And
from the creativity audit: alarms that keep ringing.

`backend/jarvis_tellme.py`, shipped whole, no patch: a KIND of job on the
one scheduler (section 21), kind `"tellme"`, loaded by
`jarvis_schedule.KIND_MODULES`. Called "Tell me when" in both apps - not
"Watch", which is the desktop's GitHub watchlist (Brain -> Watch).

### 30.1 What it watches

| Source | Set up with | Each look |
|---|---|---|
| **An email from a named sender** | `{"source": "email", "sender": "Alex"}` (a name, 1-60 plain characters, or an address) | ONE connection to the mail server `jarvis_email.plan()` names: LOGIN, EXAMINE (read-only), `UID SEARCH UID <n>:*`, `UID FETCH <new uids> (BODY.PEEK[HEADER.FIELDS (FROM)])`, CLOSE, LOGOUT. The From line only, of mail that arrived since the last look (at most 50), with PEEK so nothing is marked as read. The first look only notes where the mailbox is. The name is matched ON THIS PC (every word of it a whole word of the sender's name or address; an address compared whole) and never sent to the server. |
| **A Home Assistant device reaching a state** | `{"source": "home", "entity": "switch.washing_machine", "say": "finishes" \| "opens" \| "closes" \| "turns on" \| "turns off"}` or `"states": ["off"]`, and `"name"?` (the owner's word for it) | `jarvis_home.plan_states([entity])`: one GET of one entity. It matches when the state CHANGES into a wanted one - already there when the watch starts is not a match; `unavailable` / `unknown` are skipped. "finishes" = off, idle, finished, complete(d), done, stopped or standby; "opens" = on, open, opening or unlocked; "closes" = off, closed, closing or locked. |

Both add `"urgent"?: bool` (default false) and `"once"?: bool` (default
true: tell once, then end; false: every time until the end date).

**How often, and until when.** Email every 5 minutes at most often (each
look is one sign-in; mail apps check every 5-15 minutes, and providers slow
down accounts that sign in much more often); Home Assistant every minute at
most often (one small request on the owner's own network). Up to every 60
minutes. These floors are for this kind only: the generic rule check still
refuses "every N minutes", so every other repeat keeps the hourly floor
(`MIN_EVERY_HOURS`). It ends 30 days later by default (the same clock time),
90 days at most, or at the first match when it tells once. At most 10 at
once, 5 of them watching email.

**Each look goes through the gate**, as `email_read` or `home_read` - the
same actions as the model's reads - and runs only at tier `"auto"` (the
shipped tier). `"ask"` would be a card every few minutes and `"notify"` a
"Jarvis read your email" message every few minutes, so with either,
setting one up is refused with the reason ("Your settings ask for a yes each
time Jarvis reads email, and a "tell me when" cannot ask you every 5
minutes - so it cannot watch email."), and a look that meets it later is
skipped and says so under Coming up. The source must be set up for Jarvis
on the PC (`JARVIS_IMAP_HOST` and `email_check`; `JARVIS_HOME_URL` and
`home_read` in `[tools].enabled`) or setting one up is refused.

### 30.2 Setting one up: ONE card

| Route | Body | Answers |
|---|---|---|
| `POST /api/schedule/add` | `{"kind": "tellme", "source": "email", "sender", "urgent"?, "once"?, "days"?, "minutes"?}` or `{"kind": "tellme", "source": "home", "entity", "say" \| "states", "name"?, ...}` | **202** `{"ok": true, "waiting": true, "job", "said"}`; 400 a bad watch (a sentence); **409** the source is not set up or its reads ask each time, or too many (a sentence) |
| `POST /api/schedule/act` | `{"id", "do": "pause" \| "resume" \| "delete"}` | as 21.2 - immediate, no card. Deleting while the card waits withdraws it. |
| `GET /api/schedule` / `?id=` | - | as 21.2 |

Neither app sends the add today: a "tell me when" is set up by saying or
typing it (30.4), like a timer. The route is there for a later form.

The card is the scheduler's `schedule_repeat` (tier `ask`; any other tier
is refused and nothing is set up), in this kind's own words. For example:

```
Set up "Tell me when".

Watching for: an email from Alex.
How: every 5 minutes, Jarvis signs in to your mail server (imap.gmail.com:993, mailbox "INBOX") and reads only the From line of mail that arrived since it last looked - with PEEK, so nothing is marked as read. No subject, no text and no attachment is read, and nothing goes to the AI model.
It matches when the sender's name or address has "Alex" in it, as whole words. Your words stay on this PC: they are not sent to the mail server.
Until: Sunday 25 October at 12:00 (30 days), or the first time it happens - whichever comes first.
Urgent: yes. Your phone rings and vibrates until you look, and the PC plays an alarm sound until you dismiss it.

When it happens, Jarvis only tells you: "An email from Alex arrived." It never replies, never acts, and never opens or reads out the email or anything else.
A locked phone shows only: "Jarvis: something you asked to be told about happened."

It runs on this PC, by this PC's clock. Each look is a request to your own mail server, under the same settings as asking Jarvis to read it; the notification goes only to your own apps. Nothing else is sent anywhere.
Stopping or deleting it is immediate, from either app.

If you say no: nothing is set up, and nothing is watched.
```

A device's card says instead "Watching for: the washing machine
(switch.washing_machine) - when it finishes.", "How: every minute, Jarvis
reads that one device's state from your Home Assistant: GET
http://homeassistant.local:8123/api/states/switch.washing_machine. Nothing
in your home is changed." and "It matches when the state CHANGES to: off,
idle, finished, complete, completed, done, stopped, standby." Its detail
says `leaves_this_pc: true` (each look asks the owner's own server). Once
approved, the first look is at once.

### 30.3 A match only notifies

A look rings no doorbell and writes no "fired" line (the kind is `silent`
on the scheduler). A match publishes `schedule` `{"id", "kind": "tellme",
"state": "matched", "urgent": bool}` - no words - and, when it tells once,
ends the job (kept readable by id for a day, like a job that went off).
Nothing else happens: no reply, no action, no card, nothing to the model.

**Past its end date, it does not look again** (fixed 2026-09-26). If the
scheduler finds a look due only more than 2 minutes after the end date (the
PC slept through it, or was off), or a paused watch is resumed after its end
date (or so near it that no look is left), the watch simply ends: no sign-in,
no read, no match - a look then could tell the owner about an email that
arrived after the date the card promised. Resume answers "Its end date has
passed, so it has ended." A look is never listed by "What did I miss?"
(22.9): only a match is news.

The job's view then carries `"alert"` - "An email from Alex arrived.", "2
emails from Alex arrived.", "The washing machine finished.",
"switch.dryer is now off." - and `"alert_at"`. **The alert is built from
the owner's own words** (the name they asked to watch for, the device's
name they said), never from the email or the device: no From line, address,
subject or state value is shown, kept or logged. What this module keeps
(the `tellme` table in `schedule.db`): the mailbox position (a number), the
device's last state (a short word), when it last looked and how that went
(a fixed sentence), when it last matched.

Other fields on a "tell me when" job: `"urgent"`, `"watches"` (`"email"` or
`"home"`), `"repeat"` ("every 5 minutes"), `"note"` ("Until Sunday 25
October at 12:00, or the first time it happens. Urgent: rings until you
look. Last looked at 12:05 - nothing yet."), `"lock_screen"` ("Jarvis:
something you asked to be told about happened."). `rule` has no `watch` in
the view: what is watched is in `text` ("an email from Alex arrives"), the
one field the desktop blanks while the private lists are hidden - and it
blanks `alert` too.

**In the apps** (both, the same words): Coming up lists it as "When an
email from Alex arrives", tagged "tell me when" (", urgent"), with "Looks
every 5 minutes" and the note, and Pause / Delete. Under the list, "Tell me
when" and one line: "Say or type "tell me when an email from Alex arrives"
or "tell me when the washing machine finishes" - add "urgently" to make it
ring until you look. Setting one up asks once with an approval card; when it
happens, Jarvis only tells you." On `matched` each app reads the job by id
and shows a notification titled "Tell me when" with the alert - or only the
lock-screen words while App lock or "Hide memory lists and chat history"
is on (and always on a locked phone). Once per match.

### 30.4 Said or typed - the fast path

`jarvis_quick.py`, the owner's own typed or said words only (21.5):
"tell me when an email from Alex arrives", "let me know when I get an email
from Dr Patel", "tell me when Sam emails me", "tell me every time Sam
emails me", "urgently tell me when ...", "... it's urgent", "let me know
when the washing machine finishes", "tell me when the front door opens",
"tell me when switch.dryer is off", "... for the next 2 hours", "...
today". The answer does not say the name back (the card shows it): "That
needs your yes on the approval card, which shows exactly what is watched.
Then Jarvis looks every 5 minutes until Sunday 25 October at 12:00 and
tells you once." "tell me when it's done", "tell me when you are ready",
"tell me when dinner is ready" go to the model.

A device said in words is looked up first: `switch.`, `binary_sensor.` and
`sensor.` + the words (`binary_sensor.`, `cover.`, `lock.` for opens and
closes) - one GET of each, through the gate as `home_read`, never a list of
the whole house. One found: set up. None: "Jarvis could not find a Home
Assistant device called tumble dryer (it looked for switch.tumble_dryer,
binary_sensor.tumble_dryer and sensor.tumble_dryer). Say its Home Assistant
name, like "tell me when switch.tumble_dryer is off"." Two: it asks which,
and sets nothing up. Such an answer counts as having read Home Assistant
(outside text), like a briefing that quotes the calendar. With "opens",
"closes", "starts" or "stops", a name that is no device (or Home Assistant
not set up) goes to the model instead: "tell me when the shop opens" is as
often a question as a request.

**The model has no tool for this.** A web page or an email cannot set one
up.

### 30.5 Ringing until seen - urgent alerts, and every alarm

An **alarm** going off, and a **"tell me when" marked urgent** that
matches, keep ringing until the owner looks:

- **Phone**: a notification on its own channel, "Alarms and urgent alerts"
  (`jarvis_alarm`, importance high, the phone's ALARM sound with alarm
  usage, vibration), `CATEGORY_ALARM`, `FLAG_INSISTENT` - the sound and
  vibration repeat until the notification is opened, pulled down, tapped,
  stopped or swiped away - marked ongoing, which stops a swipe on Android 13
  (Android 14 and later allow the swipe, which also silences it), with one
  button, **Stop**,
  which removes it and does nothing else. Still never a full-screen intent.
  **Do Not Disturb**: nothing overrides it. As an alarm, it rings through
  Do Not Disturb when the phone lets alarms through (Android's default:
  Settings -> Do Not Disturb -> Alarms); if the owner turned alarms off
  there, it arrives silently. The lock screen still shows only the kind's
  words.
- **Desktop**: a Windows toast with `scenario="alarm"`, which stays on
  screen, and `ms-winsoundevent:Notification.Looping.Alarm` with
  `loop="true"`, which repeats until it is dismissed; its one button is
  Windows' own Dismiss (`winrt_toast.rs` `notify_alarm`). On an uninstalled
  build, or if the WinRT call fails, the plain toast rings once instead.
  Windows' own Do not disturb may hold it back like any toast.

Timers still ring once. **Said aloud**: on the desktop, a timer going off
while "Hey Jarvis" listening is on in the Jarvis bar is also said: "Your
timer is done." (never the timer's own words - the room may not be
private). The phone does not say timers aloud (ARCHITECTURE section 8).

### 30.6 Known gaps, said plainly

- **Not run against a real mail server or Home Assistant**, and the
  ringing has not been seen on a real phone or Windows PC. The IMAP
  conversation was checked against a stand-in that records the commands;
  a server that sends no UIDNEXT falls back to `UID SEARCH ALL` once.
- **The phone hears of a match only while connected** (21.1). An urgent
  alert while the phone is out of reach of the PC rings on the PC only.
- **A ringing ALARM also has Snooze** (the everyday quick wins, section 21):
  beside Stop on the phone and Dismiss on the PC. An urgent "tell me when"
  has Stop / Dismiss only - there is nothing to snooze.
- **Every look writes one line to the gate's audit log** (email every 5
  minutes, a device every minute).
- A paused watch that is resumed reports what happened while it was
  paused (an email that arrived, a device that changed) at its next look.
- The desktop says timers aloud only while "Hey Jarvis" listening is on.
- The approval card's lock-screen notice is the scheduler's shared
  `schedule_repeat` one ("sets up something that repeats on this PC - a
  reminder, an alarm, a morning briefing or a standby schedule; setting it
  up sends nothing anywhere, ..."), which does not name "tell me when".
- The GitHub watchlist (Brain -> Watch) is NOT merged into this: it lives
  in the owner's own backend files, which this repository does not hold,
  and a GitHub source would need a key and a new way out of the PC. Left
  for later.

## 31. Focus sessions (added 2026-09-25)

The owner's decision of 2026-09-25 (`CLAUDE.md`, after the "Build Your Own
Jarvis" prompt pack): "Focus sessions, off unless started: a timer plus
Quiet; Jarvis watches which app/site is in front ON THE PC ONLY, names the
distraction out loud ('Instagram can wait') but never stores what it saw
(only counts), waits until the owner settles before locking on, and ends
with a report card. Snooze, 'I'm doing research', pause and stop by voice.
Nothing leaves the PC." `backend/jarvis_focus.py` (shipped whole),
`backend/focus.patch` (the routes), the fast path in `backend/jarvis_quick.py`.

### 31.1 What happens, in order

1. **Started** by "focus for 30 minutes (on the essay)", or Start in either
   app. Nothing is watched before, or after it ends.
2. **Quiet**: if Jarvis was Active it goes Quiet, through
   `jarvis_power_switch.set_mode` (`power_manage`, `auto` as shipped), with
   `why` "the focus session". Quiet or Standby already: left alone.
3. **The timer** is ONE job of kind `focus` on the one scheduler
   (`jarvis_schedule.register_kind`; section 21) - not listed in Coming up
   (the focus panel counts down) and `notify: false`. Pause takes it off;
   Resume and +10 minutes put a new one on.
4. **Once a second** (while it runs, not paused) the PC reads, fresh, which
   program's window is in front and - for Chrome, Edge, Brave, Vivaldi,
   Opera or Firefox - the SITE of the front tab (the host, e.g.
   `docs.google.com`; the address is cut to the host where it is read and
   never kept). Both become salted fingerprints (a random key per session,
   never written) and are compared, then thrown away.
5. **Settling**: Jarvis's own windows are home base and never count;
   Windows' own surfaces (the desktop, the taskbar, Alt+Tab, the lock
   screen) count as nothing. The same program (and site) in front for two
   looks in a row is where the owner works: Jarvis locks on and says
   "Locked on." A browser whose site cannot be read is locked as a whole
   only after 45 seconds, and it says so ("Locked on the browser as a
   whole - I could not read which site, so any site in it counts."). It
   never guesses from a window that is not in front.
6. **Drifts**: away for longer than the grace (0.8 s - in practice, still
   away at the next look) is a drift. Jarvis says a canned line out loud
   ON THE PC (never the AI model): three tiers of four lines, firmer with
   each drift, named ("YouTube can wait.") from a table of big sites, the
   bare domain ("example.com can wait.") or the program's name; the first
   one uses the owner's "on what" ("YouTube doesn't look like the essay to
   me."). While one drift lasts it speaks again every minute ("call me out
   every 30 seconds" changes that, 20 seconds to 10 minutes). Going to
   Jarvis in the middle of a drift neither counts nor splits it.
7. **The end**: the scheduler's job goes off; the report card is said on
   the PC and shown in both apps; Active again ONLY if focus set Quiet and
   `jarvis_power.status()["why"]` still says so (the owner choosing a mode
   meanwhile wins - the same rule as the standby schedule, 21.8).

### 31.2 Routes (`focus.patch`)

Every route checks the origin and the token.

| Route | Body | Answers | Notes |
|---|---|---|---|
| `GET /api/focus` | - | 200 the status (below); 503 `{"available": false}` without `jarvis_focus.py` | A read, not held on a stale link. Both apps. |
| `POST /api/focus/start` | `{"minutes": 1-240, "on"?: "<the owner's words, 60 characters>"}` | 200 `{"ok": true, "said", "focus": status}`; 400 minutes out of range; **409** one is already running (`error` says how long is left) | No approval card (31.4). Both apps hold it on a stale link. |
| `POST /api/focus/act` | `{"do": "pause" \| "resume" \| "stop" \| "extend" \| "snooze" \| "research" \| "relief" \| "lock", "minutes"?}` or `{"do": "nag", "seconds"}` | 200 `{"ok": true, "said", "focus"}`; **409** `"No focus session is running."`; 400 anything else | ONE thing, at once, no card. `extend` default 10 minutes; `snooze` default 5 (up to 30); `nag`'s `seconds` is how often to speak during one drift (20 to 600). Both apps: pause, resume, extend, stop. The desktop's widget also: lock. Resume, extend and lock are held on a stale link; pause and stop are let through - they only make Jarvis do less. |
| `GET /api/focus/diag` | - | 200 booleans and counts | For "it didn't notice" / "it locked the wrong thing": is the front window readable, is it Jarvis, a browser, is its site readable, deferred, settle ticks, is there an app target / a site target, on target, drifting, is the look thread alive, the knobs. Never what was in front. Neither app shows it; read it on the PC (31.6). |
| `GET /api/focus/callout?seq=N` | - | 200 `audio/wav`; **403** from any address but this PC's own (loopback); 404 `{"reason": "no_line"}` nothing waiting (said, or older than 8 seconds); 503 no voice on this PC | The one waiting spoken line, made into sound by the voice in use (`jarvis_speech._synthesise` - the "One moment." path: nothing remembered, no question window, no microphone) and ERASED as it is read. The words never leave the backend. The desktop's Rust asks for it on the `focus` event (`brain/focus.rs` `play_callout`); the phone never does (ARCHITECTURE section 8). |

The status (`jarvis_focus.Engine.status()`), a whitelist:

```
{"available": true, "title", "detail", "phone_note",   the words both apps show
 "on": bool, "paused": bool, "state": "off"|"settling"|"locked"|"paused",
 "minutes": planned, "left_s": seconds, "ends_at": epoch|null, "intent": the owner's own "on what",
 "deferred": bool (waiting to lock on), "locked": bool, "lock": "app"|"app_and_site"|"",
 "on_target": bool|null, "drifting": bool, "excused": bool,
 "drifts", "on_target_s", "adrift_s", "excused_s", "quiet_left_s",   counts (0 when off)
 "set_quiet": bool, "timer_on_scheduler": bool, "watching": bool,
 "line": "24 minutes left - on target.", "note": "No callouts for 4 minutes - drifts still count.",
 "report": {"title", "lines": [...], "spoken", "completed", "clean", "streak", "percent",
            "planned_min", "active_min", "on_target_min", "adrift_min", "excused_min", "drifts", "at"} | null,
 "streak": int}
```

While "Hide memory lists and chat history" hides the lists, the desktop's
Rust takes `intent` out and sets `"intent_hidden": true` - `focus.rs`
`hide_intent` - and both apps say "On: hidden until ... confirms it is
you." instead: the words are the owner's own, like a reminder's. (2026-09-26.)

**The report card** is built from the ledger row, so it can only say
numbers: "Focus session done." / "Focus session stopped early.", "On target:
27 of 30 minutes.", "Drifted twice, 3 minutes in all.", "Research: 4
minutes, not counted against you.", "90% focused.", "Streak: 3 clean
sessions in a row." A session is **clean** at 85% or more of its watched time
on target, run to the end; the streak counts clean sessions in a row.

### 31.3 Said or typed - without the model

`jarvis_quick.py`, the owner's own words only (section 21.5's rule). Always:
"focus for 30 minutes (on the essay)", "start a focus session" (25 minutes),
"let's focus for an hour", "a 45 minute focus session", "30 minutes of
focus", "focus on the essay for 25 minutes", "stop focus", "pause focus",
"resume focus", "extend focus by 10 minutes", "add 15 minutes to my focus
session", "how's my focus going", "focus status". **Only while a session
runs** (otherwise they go on to the rest of the grammar, then the model):
"pause", "resume", "I'm back", "extend it by 5 minutes", "snooze" / "snooze
for 10 minutes" / "give me fifteen seconds", "I need a minute" / "give me a
minute" / "no Jarvis, I need to do something important" (no nudges for 3
minutes), "I'm doing research" / "it's okay, I'm doing research" / "this is
research" (the trip now - or one that ended in the last 90 seconds - does not
count, and nothing is said until back on target; said in advance, the next
trip), "lock on this" / "keep me in this tab" / "okay, I'm gonna need you to
keep me in this tab" / "this is the app I'm working in", "how am I doing?",
"how long is left" (a running timer answers first), "call me out every 30
seconds". Never "stop" alone (that is the stop word). "Focus on the
positives" and the like go to the model.

"Lock on this": what is in front NOW becomes the target, and the trip that
got there does not count. If Jarvis's own window is in front (the widget's
Lock on, or typing it to Jarvis) it locks on where the owner lands next,
and says "Go to it - I'll lock on where you land."

### 31.4 No approval card - why

Reading what is on screen sits under the computer-control rules: there,
READING a window is `jarvis_ui_control_plan`, tier `auto` (read-only,
`ui-control-wiring.patch`), and only ACTING (`control_computer`) asks. A
focus session reads less than that (the front window's program and one
site name, not its controls), sends no input, keeps only counts, is local,
and runs only because the owner asked that moment. Going Quiet is
`power_manage` (`auto`); an owner who set `power_manage` to `ask` gets that
card for the Quiet part, and the session runs either way.

### 31.5 The event

`focus`: `{"state": "started" | "changed" | "ended"}` or `{"state":
"callout", "seq": N}` - a word or a number, **never what was in front**.
`changed` is sent when Jarvis locks on, a drift starts or ends, and on
pause, resume, extend, snooze, research and lock - not every second.

| | Desktop | Phone |
|---|---|---|
| any `focus` | The Brain's Work tab and the widget read `GET /api/focus` again (`brain.js`, `widget.js`) | the Brain's Focus session reads itself again (`JarvisRuntime.onEvent` -> `focusTick`) |
| `callout` | Rust fetches `GET /api/focus/callout?seq=` from this PC only (loopback) and hands the sound to the Jarvis bar, which plays it unless Jarvis is talking; "stop" silences it (`brain/focus.rs` `play_callout`, `main.js` `playFocusCallout`) | Nothing - the line is the PC's alone |

### 31.6 What is kept, and where

- **Nothing of what was in front.** Not in the status, the diag, the report
  card, the ledger, the audit log (`focus.start`, `focus.locked`,
  `focus.act`, `focus.end`: counts and words of Jarvis's own), an event, the
  scheduler's file (the job has no words), the chat history's answer to "how
  am I doing?", or the engine's memory once a line was said or 8 seconds
  old. `backend/test_focus.py` drives drifts to a made-up program and site
  and proves their names reach the spoken line and nowhere else.
- **The ledger**, `focus_ledger.json` in the Jarvis settings folder (the last
  200 sessions): `at`, `planned_min`, `active_min`, `on_target_min`,
  `adrift_min`, `excused_min`, `drifts`, `percent`, `completed`, `clean` -
  numbers and true/false only; its writer turns every value into one.
- **The owner's "on what"** is kept in memory for the session (both apps
  show it) and in no file.

To see the diag on the PC (one line; prints to the window):

```
$t = (py -3 jarvis_token_store.py show).Trim(); (Invoke-WebRequest -UseBasicParsing -Uri http://127.0.0.1:4719/api/focus/diag -Headers @{"X-Jarvis-Token"=$t; "X-Jarvis-Client"="hud"}).Content
```

(run it in the backend folder, where `jarvis_token_store.py` is; 4719 is the
backend's usual port - use yours if you changed `JARVIS_HUD_PORT`. The answer
prints in the same window.)

### 31.7 Known gaps, said plainly

- **Not run on Windows.** Every test uses a stand-in for "what is in front".
  Reading the front program (`GetForegroundWindow` ->
  `QueryFullProcessImageNameW`, ctypes) is documented Windows behaviour and
  believed reliable. Reading a browser's SITE (UI Automation, the
  `uiautomation` package, the address box inside the browser's toolbar -
  Firefox's by its id `urlbar-input`) is **assumed** from how those browsers
  show their toolbars, and must be tried: if it fails, every browser is
  locked as a whole after 45 seconds, and the diag says
  `front_site_readable: false`.
- **The spoken line needs the desktop app running**, with the Jarvis bar
  loaded (it is, hidden, from start-up). Without it the session still
  counts, and the widget has no countdown. A line that arrives while Jarvis
  is talking is dropped - the next one comes at the next nag.
- **A backend restart forgets the session** (it is kept in memory on
  purpose); its scheduler job then goes off later and does nothing, and the
  power mode comes back Active as after any restart.
- **The manner setting** ("warm" / "plain", section 27) chooses the lines:
  `jarvis_focus.MANNER_SOURCE` reads `jarvis_manner.current` each time.
- **Stop everything** (section 28) PAUSES a running session - its stopper
  is registered as "focus", and it says "The focus session was paused." -
  and the desktop's `stopSpeaking` silences a callout (`stopFocusCallout`).
- English only, like the rest of the fast path.

## 32. What asks first (added 2026-09-26)

The owner's decision of 2026-09-26, after the approvals audit
(`docs/APPROVALS-AUDIT-2026-09-26.md`, `CLAUDE.md`): **a "What asks first"
page in both apps lists every action and whether it asks, in plain words,
with "make stricter" switches. On the PC only, the owner may also loosen a
short safe list - one card plus Windows Hello per change. Nothing outside
that list can be loosened from an app.**

`backend/asks-first.patch` (the routes, last in `$PATCHES`),
`backend/jarvis_asks_first.py` (shipped whole). Desktop: Settings, "What asks
first" (`asks-first.js`, `asks-first-settings.js`, `asks_first.rs`:
`get_asks_first`, `set_asks_first`, `set_lights_without_card`, Settings
window only). Phone: Brain, "What asks first" (`AsksFirstPlate.kt`,
`net/AsksFirst.kt`). Both read `tests/fixtures/asks-first-cases.json` /
`contract/asks-first-cases.json`, written by `tools/gen_asks_first_cases.py`
from the real `view()`. `tools/check_parity.py` records all three routes as
`ported`; loosening is the desktop's only (ARCHITECTURE section 8).

### 32.1 Routes

| Route | Body | Answers | Notes |
|---|---|---|---|
| `GET /api/asks_first` | - | 200 the page (32.2); 503 `{"available": false, "error"}` without `jarvis_asks_first.py` | Token + origin. A read: never held. `can_loosen` is true only for a request from this PC (`jarvis_owner_check.from_this_pc`: loopback, the PC's own addresses, or anything that cannot be placed). |
| `POST /api/asks_first/tier` | `{"action", "ask": true}` | 200 `{"ok", "changed", "message", "view"}` | **Stricter**, from either app, at once, never a card, never held on a stale link: the action's line becomes `"ask"`. Also withdraws a waiting loosening card for the same action. |
| `POST /api/asks_first/tier` | `{"action", "ask": false}` | **202** `{"ok", "waiting": true, "message", "view"}` while its card waits; 200 `changed: false` if it already goes ahead; **403** `{"error", "pc_only": true}` from any device but this PC; **403** for an action off the list; **409** "never" in the file, or another loosening card already waits; **503** the backend cannot ask Windows Hello itself (`owner-check.patch` not armed), or `loosen_what_asks_first` is not tier `ask` | **Looser**: the desktop only, held on a stale link. ONE approval card, action **`loosen_what_asks_first`** (32.3). Only a person's "approved" writes the line back to the shipped tier (32.4). |
| `POST /api/asks_first/lights` | `{"enabled": bool}` | as the briefing's senders switch (section 22): OFF 200 at once; ON **202** while ONE card waits; 503 if `change_own_config` is not `ask` | Section 33. |

### 32.2 The page

```
{"available": true, "title": "What asks first", "detail": <the sentence under it>,
 "switch_label": "Ask me first", "can_loosen": bool,
 "switchable": [the seven actions of 32.4],
 "groups": [{"title": "Reading your own things",
             "rows": [{"id": "calendar_read", "action": "calendar_read",
                       "title": "Read your calendar",          the card's own words (jarvis_card_words)
                       "tier": "auto"|"notify"|"ask"|"never",
                       "says": "Does it without asking",       the tier in plain words
                       "note": <one line>, "fixed": false,
                       "switch": {"asks": bool, "loose": "auto"|"notify", "can_loosen": bool}}]}, ...],
 "waiting": {"action", "title", "said"}|null,     a loosening card that waits
 "last": {"outcome", "action", "message", "why", "at"}|null,
 "lights": {"on", "waiting", "last", "why", "label", "detail"}}
```

The tiers in plain words: `auto` "Does it without asking", `notify` "Does it,
then tells you", `ask` "Asks you first, every time", `never` "Never - your
settings file switches it off". An action that only runs on a person's yes
(NEEDS_A_PERSON's, and every "Must stay 'ask'" line) says "Always asks. This
cannot be changed from an app."; set looser in the file it says "Refused - it
only runs on your yes, so its line must say "ask"". Anything else not on the
short list says "Only your settings file (jarvis-framework.toml) changes this
one." Three rows have no tier (`"fixed": true`): timers and one-off
reminders, plain repeats and the standby schedule (both "Does it without
asking", section 21), and "Switch lights, plugs and fans you name" (section
33). Every action an approval card can name (`jarvis_card_words.TITLES`) is
on the page, in ten groups; a line in the owner's file that no group names is
added under "Other", never hidden.

### 32.3 The loosening card

```
Let Jarvis read your calendar without asking you first?

From now on Jarvis will read your calendar without an approval card. This
changes one line of your settings file on this PC (jarvis-framework.toml):
calendar_read = "auto". Nothing else in it changes.

A chat where it reads something still counts as having read outside text,
so a later web search or note in that chat still asks.

Approving it needs Windows Hello on this PC. You can make it ask again at
any time from either app, and that is instant.

If you did not just do this, say no.

If you say no: nothing changes - it keeps asking first.
```

Its title: "Jarvis wants to let one action go ahead without asking you
first". Its risk entry (`asks-first.patch`, `jarvis_gate._RISK`): local,
undoable. **It is approved on the PC only, always with Windows Hello**:
`jarvis_owner_check.PC_ONLY_ACTIONS` refuses its approval from any other
device (403 `owner_check: "pc_only"`) and asks Windows Hello for it from the
PC whether it is risky or not; no Windows Hello, no approval. The phone
shows the card with Deny only and "Approve this one on the PC - it needs
Windows Hello there. Deny still works here." A "no" proposes no standing
rule (`_NO_RULE_FROM_DENIAL`).

### 32.4 The short safe list, and the settings file

`calendar_read`, `email_read`, `notes_search`, `home_read` (loosened back to
`auto`), `append_obsidian_daily`, `append_logseq_journal` (`auto`) and
`create_joplin_note` (`notify`). The backend refuses every other action,
and never anything in NEEDS_A_PERSON or its hard-limit list (anything that
leaves the PC, deletes, sends, spends, moves a lock or door, touches secrets
or loosens a security or privacy setting); `backend/test_asks_first.py`
checks the two lists never meet.

**The wiki is not on it, said plainly.** The owner's list named it, but
since the security audit (L1) `jarvis_wiki.py` writes the wiki only on a
person's yes whatever `wiki_update` says, so a looser line would switch "Add
to wiki" off rather than stop it asking. Its row says so. (The shipped
toml's comment that said "you may lower it" was wrong and is corrected.)

Making a read stricter also leaves it out of the morning briefing and "tell
me when" (they cannot stop to ask); a note write made stricter asks in every
turn, and after outside text it asks anyway (section 19's rule, unchanged).

**Writing the file** (`set_tier`): only the one `<action> = "<tier>"` line
under `[autonomy.tiers]` changes - its value, its comment kept - or, when the
file has no line for it, one line is added after the table's last line
(`calendar_read = "ask"  # set in the app's "What asks first" page`). Every
other byte is kept: comments, spacing, CRLF line endings, a byte-order mark.
The new text is parsed and must be exactly the old settings with that one
tier changed, or nothing is written; it is written to a temporary file
beside the old one and moved into place in one step. A file written some
other way (the table twice, the key twice, an inline table, not UTF-8, a
mistake in it) is refused with a sentence saying to edit it by hand. The
backend reads the file again on its next check (`jarvis_framework` notices
the change), so no restart is needed.

### 32.5 Known gaps, said plainly

- **Not run on Windows.** The Windows Hello prompt for the loosening card is
  the approval gap's step 1 machinery (section 3 of ARCHITECTURE), which is
  itself untested on Windows.
- **A program already on the PC** that holds the token can make things
  stricter (harmless) and can raise a loosening card; approving it still
  needs Windows Hello at the backend. Step 1's known limits apply.
- The desktop asks Windows Hello a second time for this card only if the
  owner chose "Every approval" in Security (the desktop's own check, then
  the backend's).

## 33. Lights, plugs and fans without a card (added 2026-09-26)

The owner's decision of 2026-09-26, after the approvals audit: **"Lights,
plugs and fans: a setting, off by default, lets Jarvis switch devices the
owner names without a card. Turning it on raises a card; turning it off is
immediate. Never after outside text in the turn. Locks, doors, alarms and
covers always keep a card of their own."**

The switch is on the "What asks first" page in both apps, in the "Your smart
home" group: **"Lights, plugs and fans without a card"** - "When you name a
light, plug or fan yourself - "turn off the kitchen light" - Jarvis switches
it without an approval card. Locks, doors, alarms, covers and garage doors
always ask, each with a card of its own, and so does everything after
Jarvis has read outside text in the chat. Turning this on shows you an
approval card first; turning it off happens at once."

**The setting** (`POST /api/asks_first/lights {"enabled"}`): the shape of
every setting that trusts more (the briefing's senders, automatic
learning). OFF is immediate and withdraws a waiting ON card. ON is ONE card,
action `change_own_config` (tier `ask` only; anything else 503), and nothing
changes before a person's "approved". Kept in
`<config folder>/asks_first.json` (`{"lights": bool, "changed"}`); no file
is off, a damaged file is off and says why. Both apps hold ON on a stale
link and let OFF through.

**When a home change runs without a card** (`jarvis_agent`
LIGHTS_WITHOUT_CARD, `jarvis_asks_first.lights_without_card`,
`jarvis_home.everyday_problem`) - every one of these, or it is a card
exactly as before:
- the setting is on;
- nothing from outside shaped the turn: no reading tool ran, the chat is not
  tainted, the newest message was typed or said by the owner (not pasted,
  shared, from the clipboard, a picture's caption, or a voice this PC could
  not check), and the app sent no text of its own;
- every request is `light`, `switch` or `fan`'s own `turn_on`, `turn_off` or
  `toggle` (never the `homeassistant` domain, which forwards to anything), on
  an entity of the same domain, with no `data` but brightness, colour and fan
  speed keys;
- none of them stands alone: a lock, alarm, cover, valve, siren, camera,
  scene, script, automation or button, or an id with door, gate, garage,
  lock, alarm, security, safe, siren or valve in it ("switch.garage_door" is
  a door);
- every device was named in the owner's newest message: each word of its id,
  after the domain and the device words (light, lamp, plug, fan...), is
  there ("light.kitchen" by "turn off the kitchen light"; "light.kitchen_
  ceiling" needs "ceiling" too; "all the lights" names none).

Such a change is not an approval and raises nothing: the audit log records
`asks_first.lights.no_card` with the devices and the service. `home_control`
stays in NEEDS_A_PERSON, and "What Jarvis can reach" says "Yes, every time -
except the lights, plugs and fans you name yourself (your setting)" while it
is on. A card for lights (the setting off, or a condition failed) is still
unclassified in the gate, so it still asks Windows Hello from the PC - the
safe side (the audit's item 7: no risk entry was added for `home_control`,
so locks keep theirs).

## 34. Memory ideas 1-4: a re-ranker, "said again", real "true from" dates (added 2026-09-26)

The owner's decision of 2026-09-26, after docs/MEMORY-RESEARCH-2026-09-26.md:
build ideas 1-4, each measured by the memory self-test
(`backend/eval_memory.py`; the numbers are in backend/README.md, "Memory
ideas 1-4"). **No new route and no new setting in either app.** What the
apps can see:

- `GET /api/memory/auto` - a fact said again carries `said_again`
  `{count, last}` (§19). Both apps show "said again once" / "said again 3
  times" in the row's small line.
- A correction card that sounds OLDER than the fact it would replace has
  `older_news: true`, and its `auto_reason` (the line both apps already show
  as "Not saved automatically: ...") ends with: "It sounds older than what
  Jarvis knows: your words date it from 2026-01-01, and the fact it would
  replace is true from 2026-03-01. Keeping it saves it as history - the
  newer fact stays in use". Keep, Discard and "Both are true" are
  unchanged.
- `GET /api/memory/status` has two more fields: `reranker`
  `{"state": "on" | "loading" | "off" | "not started", "model", "why",
  "used", "slow"?}` and `said_again` (how many repeats are recorded).
  Setup status (`jarvis_intake.status`) says the same count in words.

What changed on the PC, and nothing else:

1. **The re-ranker.** Chat recall re-orders the top 20 facts search found
   with a small cross-encoder on the processor
   (`Xenova/ms-marco-MiniLM-L-6-v2` through fastembed, Apache-2.0, about
   80 MB, downloaded once like the meaning model) before the first 5 go to
   the model. The same facts, a better order: none added, none that would
   have been among the 20 dropped, `JARVIS_MEMORY_K` and both floors
   unchanged. It never blocks a chat - loaded on a background thread; not
   loaded yet, not loadable, or slower than `JARVIS_MEMORY_RERANK_BUDGET`
   (1.5 s) on a question: that question gets the old order. Said once in the
   audit log (`memory.rerank_off`) and in `status()`. Off:
   `JARVIS_MEMORY_RERANK=0`. Pool size: `JARVIS_MEMORY_RERANK_POOL` (20).
2. **A bigger self-test** - questions that need two facts, questions about
   a time, more "don't know" questions, and a test of the learner (which
   turns it reads, "Remember:", dates, the automatic-learning gate, "said
   again", "true from"). Offline; `--learner-model NAME` also runs the real
   learner with the PC's local model.
3. **"Said again".** When the owner says something Jarvis already keeps,
   one row: the fact's id, when this PC saw the turn arrive, typed or voice
   - no words. Only from the owner's own live words, with automatic
   learning's checks; only after the fact was saved; once per turn. Erase
   keeps these rows (no words in them); nothing uses them to decide
   anything.
4. **Real "true from" dates.** A fact whose words say when it changed ("I
   moved to Leeds in January", told in March) is true from that date - never
   a future one, never from a plan ("I'm moving in March"), never from two
   dates. A correction with such a date ends the old fact on it. **Older
   news never replaces newer news:** when both dates come from the owner's
   words and the correction's is earlier, keeping the card saves it as
   history and the newer fact stays in use (the audit log says
   `memory.older_news`, ids only). Questions about the past ("what phone did
   I have in June?") then use the real dates.

Also fixed with idea 4: `retire()`, `add(supersedes=...)` and `edit()`
treated only `valid_to IS NULL` as "still in use", so a fact that ends in
the future could not be forgotten, corrected or reworded. They now use
`valid_to IS NULL OR valid_to > now`, like every reader (§6 Forget and the
"stop using this fact?" card now work on such a fact).
