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
| `proposal` | Re-reads the review queue when the Brain shows it (`brain.js` `onEvent`, section `memory_pending`); the HUD page re-reads its "N memory cards waiting" pointer | Re-reads the review queue (`JarvisRuntime.onEvent` -> `refreshMemoryQueue`) |
| `step` | Rendered in Brain → Live (`brain.js`, `stepText`) | Falls through to "unhandled" |
| `appearance` | Re-reads `/api/appearance` and repaints the tray, every window and the HUD (`stream.rs` → `appearance::refresh_from_server`; before 2026-09-23 it did nothing, so a phone change arrived only on reopen) | Re-reads the shared document (`JarvisRuntime.refreshAppearance`) |

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
`summary`**: a client makes its title from `notice.title` (else the action
name) and never from `prompt` or `detail`, because a title also ends up on a
lock screen. Shapes vary, so both clients read each row on its own and
accept all of them: `detail` as JSON text or an object; `raised` as an
object, `true`, or JSON text (any truthy value counts as raised); `id` as
text or a number. A row that still cannot be read is skipped and the phone
says so, instead of failing the whole list.

`expires_in` is seconds left before the gate stops waiting and refuses the
card (`approval_timeout_seconds`, 180 in the shipped config). Seconds left,
not a clock time, so the phone's clock does not have to agree with the PC's.
Without the patch the field is absent and no countdown is shown.
`backend/test_approval_contract.py` builds these rows from the real
`notice_for` and `expires_in` code into
`jarvis-client/app/src/test/resources/contract/pending-rows.json`, which the
phone's and the desktop's tests decode.

---

## 4. Chat

| Endpoint | Method | Body | Desktop | Android | Notes |
|---|---|---|---|---|---|
| `/api/chat` | POST | `{"messages": [...], "has_image", "stream", "auto"}` | `commands.rs:942` `stream_chat` (body built in `main.js` `send()`), quick capture in `commands.rs` | `JarvisApi.kt:719` `chatCall` (body built by `net/ChatHistory.kt`) | See below. |

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
400 recalled facts + 2,600 tool list (13 tools, 7,851 characters of JSON) +
3,000 new question = 8,298, leaving ~8,000; 18,000 characters is 6,000
tokens at a pessimistic 3 characters per token (~4,500 at English's ~4).
Same numbers on both clients: `net/ChatHistory.kt` and
`jarvis-desktop/src/chat-history.js`, held together by
`jarvis-desktop/tests/chat-history.mjs`.

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
that recording failed - show no mark buttons. **Android reads it** in
`ChatSession.send` (`ChatSession.kt:204`, parsed by
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
it, which is the desktop Brain's job. The desktop's chat code was not checked
here.

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
| `/api/voice/wake` | POST | `{"enabled": bool}` | `voice.rs` `ensure_wake_ready` | `JarvisApi.setWakeWord` | ON raises an approval card; OFF is immediate. |
| `/api/voice/enroll` | POST | `{"clips": ["<base64 WAV>", ...]}` | **no** | `JarvisApi.enrollVoice` | "Train my voice". Raises an approval card; enrols nothing itself. `voice-enroll.patch`. |

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

**`/api/voice/enroll` - "Train my voice"** (`voice-enroll.patch`, module
`jarvis_voice_enroll.py`). The phone sends the owner's recorded sentences:

```
POST /api/voice/enroll
{"clips": ["<base64 of one WAV>", ...]}       3 to 8 clips, each 1-10 s,
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
| `/api/version` | GET | `sidecar.rs:321`, `stream.rs:569` | `JarvisApi.kt:268` | The handshake. **Branch on capabilities, never on version numbers** (`JarvisRuntime.kt:394-396`). Also carries `activity` (the state word) - since 2026-09-23 in the rebuilt `jarvis_events.hello()`, which did not send it before. `capabilities.power` is `jarvis_power.status()` (`mode`, `why`, `quiet_hours`, ...) rather than a bare `true`; `capabilities.appearance` is true when `appearance.patch` is in the running server. The desktop falls back to `/api/status` for anything an older server leaves out. |
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
| `/api/memory/status` | GET | `routes.rs:28` | **no** | `{available, db, facts, current, retired, embedder, semantic, vector_search, unembedded, sleep_time}` - `MemoryStore.status()` plus the route's own two. `facts` counts retired ones too; `current` is what is in use. |
| `/api/memory/pending` | GET | `routes.rs` (`memory_pending`), as `?retire_cards=1&sleep_offer=1` | via `probe`, as `/api/memory/pending?retire_cards=1&sleep_offer=1` (`MemoryCards.PENDING_PATH`, read by `JarvisRuntime.refreshBrain`/`refreshMemoryQueue`) | The review QUEUE, never the corpus. Both apps ask for retire cards because they label them correctly, and for the overnight-tidy card because they show it - see below. The HUD page reads it plainly, for a count only. |
| `/api/memory/facts` | GET | `routes.rs:32`, `brain.rs:413` | `JarvisApi.kt:429` | Takes `?known_at=<unix seconds>` — "what did I believe then?" |
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
conversation text. **Android** does exactly those three things in Mind's Model
section (`ModelSpeed.from` in `ApiModels.kt`, drawn by `BrainScreen.kt`'s
`ModelsPlate`); `by_model` is matched to the running model by name, treating
`name` and `name:latest` as the same.

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

**The overnight-tidy card, `setup.sleep_time_offer`, also only when asked
for: `?sleep_offer=1`** (exactly `1`). `jarvis_sleep.reminder_card()` marks
the day's offer as made the moment it is called, so the route calls it only
for a client that shows the card - the Brain window and the phone. Without
the flag the field is `null`. (The HUD page reads this route often and never
showed the card, and used to use up the day's offer that way.) The card says
the feature is not built, and carries `"implemented": false`.

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
| `/api/feedback/mark` | POST | `{"turn_id": "<32 hex>", "mark": "right" \| "wrong" \| "none"}` | `commands.rs:1017` (quickbar), `hud_bootstrap.js` (HUD page) | `JarvisApi.kt:451` (`markAnswer`) | `feedback.patch`. One answer, one mark; `"none"` takes a mark back. A list of ids is refused (`400`) - there is no "mark all". `200 {"ok": true, "turn_id", "mark", "was", "changed", "facts", "retire_cards_raised"}`; `400` bad id or mark; `401`/`403` token or origin; `404` unknown id; `503` module missing. A mark never changes memory: at most it queues ONE "retire this?" card (above). |
| `/api/memory/forget` | POST | object, optional `valid_to` | `brain.rs` `brain_memory_forget` | **no** | Retires rather than deletes. No undo. Refused by the desktop while the event stream is stale, like every memory write. |
| `/api/memory/edit` | POST | object | `brain.rs` `brain_memory_edit` | **no** | Refused while the stream is stale. |
| `/api/memory/learning` | POST | `{"enabled": bool}` | `brain.rs` `brain_memory_learning` | **no** | Switching on also starts the learner (no restart needed). A "Remember:" message makes a card even while it is off. Refused while the stream is stale. |
| `/api/memory/sleep_time` | POST | `{"enabled": bool}` and/or `{"remind": bool}` | `brain.rs` `brain_memory_sleep_time` | `JarvisApi.kt:447` | The overnight tidy is **not built**: `enabled` only records the wish, and nothing runs. "Not now" sends nothing at all — the card tracks "already offered today" itself. |
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

### Notes — `backend/note-capture.patch`

| Route | Body | Answers | What it does |
|---|---|---|---|
| `POST /api/notes/capture` | `{"target": "logseq"\|"joplin", "text": "…", "title"?: "…", "notebook"?: "…"}` | **200** job, finished; **202** job, `state: "waiting"` (an approval card is up); **400** empty / unknown target; **503** not set up (no graph folder, no token — `message` says which); **429** four notes already waiting | Files the owner's own words. No model. Written through `jarvis_gate` as `append_logseq_journal` / `create_joplin_note`, under the owner's own tier for those in `jarvis-framework.toml`. |
| `GET /api/notes/capture?id=…` | — | 200/202 job; 404 unknown id | How that note ended. |

A job is `{"id", "state", "target", "message", "created", "updated", "ok"}`
with `state` one of `waiting`, `filed` (written and read back), `not_filed`
(denied / timed out / refused — `message` says which) or `failed`. **It never
carries the note's text.** Clients show `message` and nothing of their own.

Replaces what `POST /api/note` in §8 suggested. The desktop's `#log` /
`#joplin` / quick note / widget capture use it (`capture_note`,
`capture_note_status`); the chat turn with a routing system message is gone.
The phone uses it too: Home's "Quick note…" field, opened directly or by the
home-screen widget's Note button (`JarvisApi.captureNote`, `noteStatus`,
`JarvisRuntime.fileNote`). The phone keeps asking while a card waits and
shows the desktop's own sentence in its notice.

### Power — `backend/power-mode.patch`

| Route | Body | Answers | What it does |
|---|---|---|---|
| `POST /api/power` | `{"mode": "active"\|"quiet"\|"standby"}` | 200 `{"ok", "mode", "changed", "message", "unloaded"?}`; **202** `{"waiting": true, ...}` while a card is up (only if the owner set `power_manage` to ask); **400** unknown mode; **409** standby while a task runs; **503** no power module | Through `jarvis_gate` as `power_manage` (`auto` in the shipped toml). Standby also unloads the resident model. |

The mode clients show still comes from `/api/status` and the `power` event.
Desktop: tray → Change power mode (`commands::set_power_mode`). Phone: Mind
screen buttons (`JarvisRuntime.setPower`). Both hold **waking** on a stale
link and let going quieter through.

<!-- ===== task controls, notes, power (2026-09-23) - end ===== -->
