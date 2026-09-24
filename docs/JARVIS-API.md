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
| `activity` | Updates activity + detail. The sentence is read from `value.detail` (the rebuilt bus's `set_activity` shape), then a top-level `detail`, then `activity_detail` (`stream.rs`, `activity_detail()`) | Reads the sentence off the event the same way - `value.detail` first, then `detail`, then `activity_detail` (`net/ActivityEvent.kt`) - and re-fetches status (`JarvisRuntime.onEvent`). Before 2026-09-24 it read only `activity_detail`, which no backend sends |
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
| `memory_saved` | Brain: the quiet "Jarvis remembered N things" line; re-reads the auto list and `memory_facts` (`brain.js` `noteMemorySaved`/`onEvent`). Automatic learning saved facts without a card (`auto-learn.patch`; §19); the data is flat, `{"ids": [<fact id>, ...]}` - fact ids only, never the words | The same line on Mind; the list re-reads (`JarvisRuntime.onMemorySaved`). Never a notification. |
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
`summary`**: a client makes its title from `notice.title` (else the action
name) and never from `prompt` or `detail`, because a title also ends up on a
lock screen. Shapes vary, so both clients read each row on its own and
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
400 recalled facts + 2,600 tool list (13 tools, 7,851 characters of JSON) +
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

**No tool receipt.** A 200 from `/api/chat` means "a chat completed", not
"the thing you asked for happened". There is no `tool_calls` field on the
response. `docs/API-DISAGREEMENTS.md` §10 records the consequence: the quick-
capture widget used to say "Appended to Logseq." on any 200, and now reports
only what Jarvis itself said it did.

**Tool calls and outside text** (`jarvis_agent.py`, 2026-09-24). Nothing
here changes which tools need a card; that is still the gate's tier table.
What changed, all on the PC, no app change needed:

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
  returned this turn and not in anything the owner typed or said. The plan
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
| `/api/voice/utterance` | POST | **WAV bytes**, `?source=push_to_talk\|wake_word&mic=phone\|desktop`; since 2026-09-24 also `source=barge_in` and `&waited_ms=` (section 17, neither app yet) | `voice.rs:335` | `JarvisApi.kt:574` | The one route whose body is not JSON. `mic` (2026-09-24, `voice-mic.patch`) picks that microphone's voice print. `source=barge_in` answers "stop or not" and is never transcribed (`voice-flow.patch`). |
| `/api/voice/moment` | GET | - → WAV bytes | **not yet** | **not yet** | The "One moment." clip in the voice in use now (section 17, `voice-flow.patch`). 503 with `why` when there is none. |
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
| `/api/version` | GET | `sidecar.rs:321`, `stream.rs:569` | `JarvisApi.kt:268` | The handshake. **Branch on capabilities, never on version numbers** (`JarvisRuntime.kt:394-396`). Also carries `activity` (the state word) - since 2026-09-23 in the rebuilt `jarvis_events.hello()`, which did not send it before. `capabilities.power` is `jarvis_power.status()` (`mode`, `why`, `quiet_hours`, ...) rather than a bare `true`; `capabilities.appearance` is true when `appearance.patch` is in the running server. The desktop falls back to `/api/status` for anything an older server leaves out. |
| `/api/status` | GET | `commands.rs:677`, `routes.rs:16`, `stream.rs` (power/activity fallback) | `JarvisApi.kt:271` | Reports the power mode (written by `POST /api/power` since `power-mode.patch`). Also `held` (a boolean): **what sets it is not documented anywhere in this repository** - it comes from the owner's `jarvis_hud.py`. Two phone comments used to give it two different meanings; the Mind screen now says only "something held back" and points to the undo shelf, and the quick-settings tile does not read it. |
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
| `/api/memory/facts` | GET | `routes.rs:32`, `brain.rs:413` | `JarvisApi.kt:429` | Takes `?known_at=<unix seconds>` — "what did I believe then?" Each fact's `current` is judged as Jarvis knew it at that moment, not as of today: a fact retired later (`retired_at` after that moment) was current then; `valid_to` counts only while `retired_at` is empty (`bitemporal.patch`). |
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
| `/api/history?limit=&before=` | GET | `brain/history.rs` `brain_history_list` (Brain, History) | `JarvisApi.history` (Mind, Chat history) | `chat-history.patch`, `jarvis_chat_log.py`, 2026-09-24 - **§18**. Token + origin. The switch's state (`enabled`, `recording`, `why_not`, `waiting`, `keep_days`, `encrypted`) and `conversations`, newest first: `[{id, title, started, updated, turns, device, has_voice, tainted}]`. `limit` 1-100 (default 30); `before=<updated>` pages to older ones. `503 {"available": false, "error", "reason"}` if `jarvis_chat_log.py` is missing. |
| `/api/memory/learning` | GET | `brain_memory_learning_status` (`brain/auto_learn.rs`) | `JarvisApi.autoLearnSettings` | `auto-learn.patch`, `jarvis_auto_learn.py`, 2026-09-24 - **§19**. Token + origin. The learning switches in one read: `{"enabled", "auto", "auto_sensitive", "auto_waiting", "sensitive_waiting", "auto_last", "sensitive_last", ...}` (`enabled` is background learning's own switch). Before this, only the POST existed. `503 {"available": false, "error", "reason"}` if `jarvis_auto_learn.py` is missing. |
| `/api/memory/auto?limit=&before=` | GET | `brain_memory_auto_list` (hidden with the other memory lists under Windows Hello) | `JarvisApi.autoFacts` (hidden under "Hide memory lists and chat history") | `auto-learn.patch` - **§19**. "Saved automatically": `{"facts": [{id, text, saved_at, provenance, device}], "auto", "auto_sensitive"}`, current facts only, newest first; `limit` 1-100 (default 30); `before=<saved_at>` pages to older ones (floored to whole seconds; a page never splits a second). |
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
conversation text. **Android** does exactly those three things in Mind's Model
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
| `auto_reason` | string | `auto-learn.patch` (§19). Why automatic learning left this proposal as a card, in plain words: `"from pasted text"`, `"sensitive: health"`, `"not in your own words"`, ... Show it as one quiet line on the card. `""` (or absent, on an older backend) when automatic learning was off or never looked at this card. |

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
| `/api/memory/forget` | POST | object, optional `valid_to` | `brain.rs` `brain_memory_forget` | `JarvisApi.forgetFact`, from the "Saved automatically" list only (§19), after a confirm, held on a stale link | Retires rather than deletes. No undo. Refused by the desktop while the event stream is stale, like every memory write. Since the owner's decision of 2026-09-24 (automatic learning, §19) the phone calls it too, for automatically saved facts - one fact per request, held on a stale link, like the desktop. Rewording (`/api/memory/edit`) stays desktop-only. |
| `/api/memory/edit` | POST | object | `brain.rs` `brain_memory_edit` | **no** | Refused while the stream is stale. |
| `/api/memory/learning` | POST | `{"enabled": bool}` | `brain.rs` `brain_memory_learning` | `JarvisApi.setLearning` (Mind, "What Jarvis remembers") | **ON asks first** (`learning-asks.patch`, `jarvis_learning_switch.py`, 2026-09-24): **202** `{"ok": true, "waiting": true, "enabled": false, "message"}` while one approval card under the action `learning_enable` waits; it turns on (and starts the learner) only when that card is approved. A second ON while one waits: 202, no second card. A toml tier other than `ask`: **503**. **OFF**: 200 at once, never a card, and it withdraws a waiting ON. Both apps hold ON (not OFF) while the stream is stale, and say "waiting" until the card leaves the queue. A "Remember:" message makes a card even while learning is off. |
| `/api/memory/learning/auto` | POST | `{"enabled": bool}` | `brain_memory_learning_auto` (ON held on a stale link) | `JarvisApi.setAutoLearn` (the same hold) | `auto-learn.patch` - **§19**. "Learn automatically" (on by default). The shape of `/api/memory/learning`: **OFF** 200 at once, never a card, withdraws a waiting ON; **ON** 202 `{"waiting": true, ...}` and ONE approval card, action `learning_auto_enable`; on only when it is approved. Already on: 200, no card. A second ON while one waits: 202, no second card. Tier other than `ask`: **503**. Bad body: `400`. Every reply carries the `GET /api/memory/learning` fields (not `enabled`). |
| `/api/memory/learning/sensitive` | POST | `{"enabled": bool}` | `brain_memory_learning_sensitive` (ON held on a stale link) | `JarvisApi.setAutoLearn` (the same hold) | `auto-learn.patch` - **§19**. "Also remember sensitive topics automatically" (off by default). The same shape, action `learning_sensitive_enable`. |
| `/api/history/settings` | POST | `{"enabled": bool}` or `{"keep_days": 0 \| 30 \| 90 \| 365}` (one per request) | `brain_history_settings` (ON and every keep change held on a stale link) | `JarvisApi.setHistory` / `setHistoryKeepDays` (the same holds) | `chat-history.patch`, `jarvis_chat_log.py`, 2026-09-24 - **§18**. The same shape as `/api/memory/learning`: **ON asks first** - **202** `{"waiting": true, ...}` and ONE approval card under the action `history_enable`; on only when it is approved. ON while already on: 200, no card. A second ON while one waits: 202, no second card. A toml tier other than `ask`: **503**. **OFF**: 200 at once, never a card, withdraws a waiting ON; what is kept stays. `keep_days`: 200 at once, the reply says how many conversations it deleted. Anything else: `400`. Every reply carries the `/api/history` status fields. |
| `/api/history/delete` | POST | `{"id": "<conversation id>"}` | `brain_history_delete`, after a confirm; held on a stale link | `JarvisRuntime.deleteHistory`, after a confirm; held on a stale link | `chat-history.patch` - **§18**. One conversation per request, `200 {"ok": true}` or `404`. **There is no delete-all** - a list, or any other key, is `400`. |
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

### Power — `backend/power-mode.patch`

| Route | Body | Answers | What it does |
|---|---|---|---|
| `POST /api/power` | `{"mode": "active"\|"quiet"\|"standby"}` | 200 `{"ok", "mode", "changed", "message", "unloaded"?, "also"?}`; **202** `{"waiting": true, ...}` while a card is up (only if the owner set `power_manage` to ask); **400** unknown mode; **409** standby while a task runs, or while another power card waits; **503** no power module | Through `jarvis_gate` as `power_manage` (`auto` in the shipped toml). Standby also unloads the resident model, and (2026-09-24) stops the second card's Ollama and the big model when they run: `also` is one sentence per engine that had something to say, and each sentence is appended to `message`, so an app that shows `message` shows them. The second card then stays stopped - status reads do not restart it - until the owner uses a second-card feature or Jarvis leaves standby; background learning does not wake it. A big-model job already under way is left to finish. |

The mode clients show still comes from `/api/status` and the `power` event.
Desktop: tray → Change power mode (`commands::set_power_mode`). Phone: Mind
screen buttons (`JarvisRuntime.setPower`). Both hold **waking** on a stale
link and let going quieter through.

<!-- ===== task controls, notes, power (2026-09-23) - end ===== -->

---

## 12. The second graphics card (added 2026-09-24)

`backend/second-card.patch` and `backend/jarvis_second_card.py`. The owner's
guide is `docs/SECOND-CARD.md`. **Both apps call both** (2026-09-24). The
phone: Mind screen, "Second graphics card" (`SecondCardPlate.kt` /
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
`commands.rs`), the phone from Mind (`net/Wiki.kt`, `WikiPlate.kt`).
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
window only; `src/deep.js`). The phone: Mind screen, "Big model (slow)" and
"Deep questions" (`BigModelPlate.kt` / `net/BigModel.kt`).
`tools/check_parity.py` records all three as `ported`.

| Route | Body | Answers | Notes |
|---|---|---|---|
| `GET /api/big-model` | - | 200 `status()` (below); 503 `{"available": false, "error"}` if `jarvis_big_model.py` is missing | Token + origin. Folder paths, memory and disk numbers; never the key colibri is started with. Does not start colibri. |
| `POST /api/big-model` | `{"switch": "master" \| "wiki" \| "deep_questions", "enabled": true \| false}` | 200 `{"ok": true, "pending": true, "enabled": false, "message"}` - a card is up, nothing is on yet; 200 `{"ok": true, "enabled": false, "pending": false, "message"}` - off; 200 `{"ok": true, "enabled": true, "pending": false, "message"}` - already on; **409** a card for that switch already waits; **400** unknown switch, `enabled` not a boolean, or a job before the main switch; **503** not possible (colibri or Python not found, no usable model, not enough memory in total, a nearly full drive - the sentence says which), or `big_model_enable` is not tier `ask` | ON is one approval card (action `big_model_enable`). OFF is immediate and stops colibri if nothing else needs it. Show `error` word for word. |
| `GET /api/deep` | - | 200 `deep_status()` (below) | Token + origin. The owner's own questions and answers; reads only, starts nothing. |
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
Times are Unix seconds. The answers are kept on the PC in
`<config dir>/deep-questions.jsonl` (the last 100), so they survive a
restart; questions still waiting when the backend stops are lost.

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

**Check before you send.** An older PC reads a body it does not know as a
plain training (any body with clips in it) or answers 400. Offer each new
mode only when `gate.training` says the PC understands it:

| flag in `gate.training` | the modes it allows |
|---|---|
| `calibrate: true` | `calibrate`, `threshold` (since 2026-09-24, earlier) |
| `rounds: true` | `train` (rounds, `add`, `finish`, `cancel`) |
| `settings: true` | `strictness`, `privacy`; and `memory` when `gate.settings.memory` is present (an older PC answers `mode: "memory"` with 503) |
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

### `/api/voice/status` - new in `gate`

```
"strictness": "very_strict" | "balanced",
"privacy": "private_on_screen" | "voice_is_enough",
"memory": "memory_aloud" | "memory_on_screen",
"sensitive_memory": "sensitive_on_screen" | "sensitive_aloud",   "" from an older PC: do not offer it
"settings": {"strictness", "privacy", "memory", "sensitive_memory", "changed": epoch,
             "voice_is_enough_allowed": bool,        true only while very strict
             "min_command_seconds": 2.0 | 1.5,
             "choices": {"strictness": ["very_strict", "balanced"],
                         "privacy": ["private_on_screen", "voice_is_enough"],
                         "memory": ["memory_aloud", "memory_on_screen"],
                         "sensitive_memory": ["sensitive_on_screen", "sensitive_aloud"]},
             "defaults": {"strictness": "very_strict", "privacy": "private_on_screen",
                          "memory": "memory_aloud", "sensitive_memory": "sensitive_on_screen"}},
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
```

`sensitive_memory` (added 2026-09-24, the owner's decision: an answer that
uses a sensitive saved fact stays on screen by default, even under "Read
aloud" for memories): `sensitive_on_screen` is the default and the strict
value, and applies at once. `sensitive_aloud` is the looser one and raises
the voice card, which reads: "Let Jarvis read answers that use a saved fact
about your health, money, passwords or other people aloud, when you ask by
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
| `503` | this PC's voice check is too old for that setting (`memory` or `sensitive_memory` on a PC from before them) |
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
3. **Sensitive saved facts** (the owner's decision, 2026-09-24): when the
   route's `injected_sensitive` is above 0 - or it is missing and
   `injected_facts` is above 0 (an older PC: fail closed) - and the
   utterance reply's `sensitive_aloud` is not true, keep the answer on
   screen ("It's on your screen."). This applies **even when
   `memory_aloud` or `private_aloud` is true**.
4. Treat a reply from an older PC (no `private_aloud`, no `memory_aloud` or
   no `sensitive_aloud` field) as `false`.

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
2026-09-24. **Built on the backend first; neither app uses any of it yet** -
this section is what they build against. One new route
(`GET /api/voice/moment`, `planned` in `tools/check_parity.py`); the rest
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
  "summary":  [{"step", "label", "turns", "median_ms", "worst_ms"}, ...]   one line per step, over `timings`
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

**What an app should build** (suggested, for both): extend the existing
"Interrupt Jarvis while it talks" switch so that, while Jarvis speaks,
speech the microphone hears is sent as `source=barge_in` (with the rules in
1); a "Say 'One moment' if I'm kept waiting" switch (on by default) that
plays the clip as in 3; send `waited_ms` on every utterance; and a "Voice
delay" panel showing `flow.summary` (the `label`, `median_ms` and
`worst_ms` columns), with `flow.warm.state`.
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

On each `role: "user"` message:

- `provenance`, one of:

  | value | meaning |
  |---|---|
  | `typed` | typed into the box by the owner (the app's default for its own box) |
  | `voice` | the transcript the PC's speech route gave back for this turn |
  | `shared` | came from another app (the phone's Share sheet) |
  | `clipboard` | put in the box from the clipboard (the desktop hotkey) and not edited before sending |
  | `pasted` | pasted or dropped into the box (desktop: a `paste` or `drop` on the box since it was last empty; phone: one edit that inserted more than 40 characters at once) |
  | `picture_caption` | words sent with a picture |

  Missing, or any other value, is recorded as **`unknown`**, and unknown
  counts as "not the owner's own words" everywhere it matters. The apps keep
  each user turn's `provenance` in their own history and send it again with
  that turn every time. The existing `origin` field is unchanged.

**Phone Share.** Shared text is no longer put into the owner's draft. It
is held as a chip above the box ("Shared text · 1,204 characters", with an
X), and sent as its **own** user message, `provenance: "shared"`, just
before the owner's typed message in the same request. If the owner typed
nothing, the shared message is sent alone.

**Desktop clipboard hotkey.** The short-snippet prefill is tagged
`clipboard`; it becomes `typed` only if the owner edits it before sending.
The long-snippet `system` context path is unchanged.

**The server takes `provenance`, `conversation_id` and `device` off before
anything goes to any model**, local or cloud: the local answering loop gets
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
held, with the voice check's strictness, model and mode). Otherwise a claimed
`voice` is recorded as `voice_unverified`.

**Not kept:** tool output, system or context messages, deep questions,
wiki jobs, notes (#obs, #log), approval cards, pictures. None of them come
through `/api/chat`'s record.

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
the Brain window next to Memory; phone, a History screen next to Mind's
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

The learner still **proposes** every fact into the review queue, exactly as
before (§6, `/api/memory/pending`). After each learning pass, and after each
"Remember: ...", the PC looks at what was just proposed and saves a proposal
**without a card only when every check below passes**. Everything else stays
an ordinary card, with the reason on it.

Backend: `backend/auto-learn.patch` (last in the patch order) and
`backend/jarvis_auto_learn.py` (shipped whole); a live-turn registry in
`jarvis_chat_log.py`. **Both apps have it**: desktop Brain -> Memory
(`brain/auto_learn.rs`, `auto-learn.js`), phone Mind -> What Jarvis remembers
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
   is on (GUARDS L7). A word-list check (no model) on the fact AND on the
   turns it shares words with: passwords and codes in several languages, PINs,
   card-like digit groups, expiry dates, account and ID numbers, security
   questions; health words, medicines and doses; money amounts, salaries,
   debt, rent, savings; and other people's private details (affairs, arrests,
   addresses, phone numbers, email addresses, secrets). "sensitive: health",
   "sensitive: money", "sensitive: passwords and account details",
   "sensitive: private details about someone else", "sensitive: someone
   else's health". Deliberately broad: a false hit costs one card.

**"Remember: ..."** is saved without a card only with a **colon**, on **one
line**, at most 600 characters, from a typed or verified-voice live turn,
with background learning and "Learn automatically" both on, and nothing
sensitive or instruction-like in it (GUARDS L3). No model reads it, so check
2 does not apply. Otherwise it stays the card it already is - and that card
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
so a saved fact cannot close the block early.

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

`POST /api/memory/forget {"id": <fact id>}` - unchanged (§6): one fact per
request, retired, not deleted. Now **also called by the phone**, for this
list; both apps hold it on a stale link.

`/api/memory/pending` rows gain `auto_reason` (§6's row table) and
`verbatim` is narrowed (above).

Event **`memory_saved`**: data is flat, `{"ids": [<fact id>, ...]}` - ids
only, never the words (GUARDS L10). One event per pass or per "Remember:".

If `jarvis_auto_learn.py` is not installed: `GET /api/memory/learning`,
`GET /api/memory/auto` and both POSTs answer **503** `{"available": false,
"error": "automatic learning is not installed on this PC, so every fact
waits for your yes", "reason"}` - and nothing is ever saved without a card.

### 19.5 What each app shows (both apps - parity rule)

Where the learning switch lives today (desktop: Brain -> Memory; phone: Mind
-> "What Jarvis remembers"):

- **"Learn automatically"**, with: "Jarvis saves facts about you and your
  projects from what you type or say to it - never from web pages, emails,
  documents or notes. You can forget any of them here."
- **"Also remember sensitive topics automatically"** (off by default), with:
  "Health, money, passwords and account details, and private details about
  other people. When this is off, Jarvis asks you first."
- Both: ON raises the card and shows "Waiting for your approval" (from
  `auto_waiting` / `sensitive_waiting`, and the card in the approval queue -
  including one raised on the other device); OFF immediate; ON held on a
  stale link.
- **"Saved automatically"**: newest first, the fact, when, a small "said
  aloud" mark for voice, and a one-tap **Forget** on each (with the same
  confirm as the desktop's Forget today). "Load older".
- On `memory_saved`: a quiet line, "Jarvis remembered 2 things", that opens
  the list. Never a pop-up; never the fact's text in a notification.
- Cards that stayed cards show `auto_reason` as one quiet line.

The approval cards read "Turn on automatic learning. ..." and "Also remember
sensitive topics automatically. ..." (`jarvis_auto_learn.AUTO_CARD`,
`SENSITIVE_CARD`); both say nothing leaves this PC and what a "no" means.

### 19.6 Known gaps, said plainly

- **Strict on purpose, so many real facts stay cards.** A fact the model
  rewords ("prefers" for "likes better") is not grounded; a conversation
  with one pasted message, one shared text, one tool run or one voice turn at
  the balanced voice setting makes every later pass of that conversation
  cards; and the sensitive word list is broad (it flags "tokens", "bank",
  "budget", "doctor"...). No local-model sensitivity check yet.
- **The registry is in memory.** After a backend restart, the rest of an
  ongoing conversation is cards (the earlier turns are "not seen arrive"). An
  app that sends no `conversation_id` gets cards only.
- **Voice** is saved automatically only at `very_strict` with the stronger
  voice model installed and in mode `owner`.
- **The 38 phrasings.** The memory audit's sensitive-topic red-team script
  holds 38 phrasings (the brief said 42); all 38 are flagged, and
  `backend/test_auto_learn.py` carries them word for word.
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
