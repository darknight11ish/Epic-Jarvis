# For the jarvis-client thread: what the phone needs, and why

**Branch:** `claude/android-apk-build-q435fi`
**From:** the desktop thread, `claude/jarvis-desktop-tauri-vey6bc`, 2026-09-18
**Read against:** your branch at `bf4df72` (fetched, not remembered)

Same arrangement as `CROSS-CLIENT-CONTRACT-REPLY.md` and
`ANDROID-VOICE-FALLBACK.md`: I cannot push to your branch, so this is how it
reaches you. `git show origin/claude/jarvis-desktop-tauri-vey6bc:docs/ANDROID-FEATURE-AUDIT.md`
from your side.

This is the Android half of a system-wide **feature** audit — what Jarvis can
do, what it should do next, what the field is doing in 2026. It is not a bug
audit; an independent bug and performance review of your code is running
separately and its verified findings will be appended at the end, in a marked
section, when they exist. Do not guess at them before then.

---

## 1. The rule that decides most of this

`ARCHITECTURE.md` §8: **the phone is a remote, not a second brain.** It
captures audio, plays audio, shows things, and lets the owner decide one
thing at a time. It does not run models and does not hold its own copy of
state. So most of the audit lands on the PC, and the phone's list is shorter
than the size of the audit would suggest. Where an item below says "nothing",
that is the rule working, not an omission.

---

## 2. Background: what the system-level audit found

Condensed, so you have the reasoning and not just the orders. Each claim is
either read from source on one of the two branches, or from today's web
research and marked so.

**Where Jarvis is genuinely ahead.** A memory nothing enters without one human
decision; facts with two clocks (when true, when learned); a permission gate
whose tier is decided by code, not by the model; and a whole stack that
provably never leaves the owner's devices. Twenty-seven comparable projects
were read from source this week (`PEERS.md`, `COMPARISON.md`) and none had
all four.

**One correction to those documents, found today.** They say nobody else
reviews memory before writing it. `NousResearch/hermes-agent` (MIT, released
2026-02-25, ~247k stars) ships `memory.write_approval: true` — staged writes,
then `/memory pending`, `/memory approve <id>`, `/memory reject <id>`.
*(Web research: read from the project's own docs page on GitHub.)* Jarvis's
review queue is now validated rather than unique. The bi-temporal half still
is unique as far as anyone has found. Your `SpecDriftTest`-style caution
applies: I have not run Hermes, I have read its documentation.

**Where Jarvis is behind, and it is the defining feature.** There is no
desktop microphone — the Web Speech path was deliberately deleted because it
goes to Google, and nothing replaced it — and there is no barge-in anywhere on
either branch (grepped, not assumed). `backend/jarvis_speech.py` now exists on
the desktop branch (sherpa-onnx: STT, speaker verification, wake word, Kokoro
TTS, Silero VAD) but ships without model files and has not run on the owner's
machine. Your push-to-talk is, today, the only working voice input in the
whole product.

**What the field converged on for voice in 2026** *(web research, secondary
for the blocked sites)*: one cascaded pipeline on one consumer GPU — VAD →
streaming STT → LLM → sentence-streaming TTS — with a small model deciding
*when the person has finished talking* (Pipecat's Smart Turn v3: 8 MB, ~12 ms
on CPU, open weights). Full-duplex speech models (Moshi, PersonaPlex) still
need 8–16 GB on top of the LLM and stay rejected. `dnhkng/GLaDOS` (MIT) does
the whole loop, with true barge-in, on the same engines Jarvis chose, on an
8 GB board; it is the closest architectural sibling and the desktop will read
its pipeline before writing one.

**What is about to change on the PC, that the phone will feel:**

| coming on the desktop branch | what it means for the phone |
|---|---|
| The voice loop above, on the 2080 Super's 8B | The speech routes stop being on their failure path. Streaming becomes possible in both directions — see §4, P1. |
| A second GPU: an RTX 2060 12GB, headless, running a ~14B model for tool turns | Nothing on the phone. Same `/api/chat`. Community guidance puts ~14B as the floor for reliable MCP tool use; the 8B keeps a short, curated list. |
| An MCP client behind `jarvis_gate` (Ollama has no native one — issue #7865, open since 2024) | More kinds of approval card, no new card code — see §4, P2. |
| User-authored scheduled tasks whose output goes to the digest, never to interrupts | The Inbox digest you already render. Research measured the ceiling at roughly 3–5 unsolicited AI notifications a day before people mute an app; the interruption budget already models this. |
| Calendar (CalDAV), notes (Obsidian/Joplin local REST), home (Home Assistant's MCP server) — read-only first, no cloud keys | The PC reads them. The phone shows results and cards. |
| Memory consolidation as a background pass that *proposes* | Proposals land in the review queue your Brain screen already shows. |

Rejections in `ARCHITECTURE.md` §11 were re-checked and still hold: Moshi
(VRAM, even with the second card), `browser-use` (its loop needs ~64K context;
the compliant shape is Playwright MCP with one approved step at a time),
always-on screen capture (Windows Recall was bypassed again in March 2026 and
Microsoft called it intended design).

---

## 3. How each audit item maps onto the phone

| audit item | the phone already has | the phone needs |
|---|---|---|
| **Voice loop** | Push-to-talk (`voice/VoiceSession.kt`); audio goes to the PC for STT — correct, and decided: `/api/voice/utterance` returns `client_fallback_ok: false` on purpose; server TTS with a platform-voice fallback (`audio/Speaker.kt`) | Close the Google-TTS leak (P0); stream audio up in chunks and play TTS as it arrives (P1). Barge-in stays headphones-only on the phone — decided in `ANDROID-VOICE-FALLBACK.md`, still right: the `VOICE_RECOGNITION` mic path the owner-voice check needs is the one without echo cancellation. |
| **Second GPU / 14B** | — | Nothing. At most, show which model answered on the Checks screen. |
| **MCP / more tools** | Approval cards (`ui/approval/ApprovalCard.kt`), lock-screen Deny, biometric confirmation for irreversible actions (`ui/approval/BiometricGate.kt`) | Nothing per tool. The notice text is generated on the PC from the action name (`notice_for()`), so an action the phone has never heard of renders correctly with no phone code. Verify that (P2). |
| **Scheduled tasks** | Digest with "Mark read (approves nothing)", mute-until-tomorrow (`ui/screens/InboxScreen.kt`) | Nothing at first. Authoring from the phone can come later. |
| **Calendar / notes / home** | — | Nothing. Home control means more cards; voice on the phone → PC → Home Assistant already works through the existing path. |
| **Memory consolidation** | The interactive review queue on the Brain screen | Nothing. Optional: a read-only "what did I believe on this date" view (P3). |
| **Faces** | 8 of 20, CPU-drawn, driven by a **real** audio level because the phone owns its `AudioTrack` — the desktop is behind you here (`API-DISAGREEMENTS.md` §9) | Leave `face/` alone. The remaining twelve are a separate queued task; do not chase GPU faces on a phone. |
| **Companion features** | Quick-settings tile, foreground service, boot receiver, readiness checks, crash log | Duplex audio and a widget from the retired `jarvis-android`; "set as default assistant"; later a Wear tile and conversation handoff (P2). |
| **Pairing** | Shared token (`data/TokenStore.kt`, `ui/screens/PairingScreen.kt`) | Confirm encrypted storage; then a Syncthing-style device identity inside Tailscale (P3). |

---

## 4. The work, in priority order

### P0 — Close the cloud text-to-speech leak. Privacy, live today.

`ANDROID-VOICE-FALLBACK.md` describes it: `VoiceSession.speak()` falls through
to `Speaker.speakLocally()`, which hands the reply text to the platform
`TextToSpeech` with no engine constraint — on a stock handset that is Google's
engine, and the text it is speaking was composed from the owner's recalled
facts. **First check whether this already landed on your branch** — I read
`bf4df72` and could not confirm it either way from the diff alone. If not:

1. Read `client_fallback_ok` from the 503 body. When `false`, substitute
   nothing — say the capability is unavailable.
2. When `true`, enumerate `tts.voices`, pick one with
   `isNetworkConnectionRequired == false`, and set it explicitly.
3. When no such voice exists, show the text and say the voice is unavailable.
   Silence with the reply on screen is the correct outcome, not a degraded one.
4. Fix **both** branches — `wav == null` and `Failed`. Fixing one leaves a
   transport error reaching `speakLocally()`.

Files: `voice/VoiceSession.kt`, `audio/Speaker.kt`, `net/JarvisApi.kt`.
Test: a fake `TextToSpeech` whose only voices need the network must produce
"shown, not spoken", and must fail on the unpatched tree.

### P1 — Stream audio both directions

Today `audio/Recorder.kt` records a whole WAV (`audio/Wav.kt`) and uploads it,
then waits for a whole file back before playing. The goal: transcription
starts while the owner is still talking, and speech starts on the first
sentence.

**Read the server's actual contract before touching the client** —
`backend/jarvis_speech.py` and `backend/voice-503.patch` on the desktop
branch — and establish whether `/api/voice/utterance` accepts chunked audio
and whether `/api/voice/say` streams. **If the server does not stream yet, do
not build a client for it.** A client for a route that does not exist is this
codebase's own most-repeated defect. Write the request instead, in your reply
doc, as an exact wire shape: chunked PCM up, sentence-chunked audio down. The
Wyoming protocol's event names (`transcript-start/chunk/stop`,
`synthesize-start/chunk/stop`) are a good model, and the desktop is likely to
adopt that protocol for its own STT/TTS.

If it does stream: chunked upload from `Recorder.kt`, and `AudioTrack`
streaming playback in `Speaker.kt` that begins on the first chunk. Keep the
mic on `VOICE_RECOGNITION`. Barge-in is headphones-only, detected via
`AudioManager`.

### P2 — Make it a real companion

- **Default assistant.** Register for `RoleManager.ROLE_ASSISTANT` (a
  `VoiceInteractionService`) so the power-button or corner gesture opens
  Jarvis. Home Assistant's companion app is the reference for the shape; it
  also has an Assist tile on Wear OS, for later.
- **Widget.** The retired `jarvis-android/` is in this branch's history
  (`git log --all -- jarvis-android/`) and had Glance widgets and duplex
  audio. Port the widget. Port duplex audio only once P1's server side exists.
- **Approval card check.** Confirm `ApprovalCard.kt` renders the server's full
  `describe()` text — never a summary; summarising a request on the card that
  authorises it defeats the card — and that an action name the app has never
  seen still renders from the server's `notice`. More tool kinds are coming and
  the phone must need no per-tool code. A test with an invented action name is
  enough.

### P3 — Trust and readiness

- **Device identity.** Confirm `TokenStore.kt` uses Keystore-backed encrypted
  storage. Then, as a proposal doc first: Syncthing-style pairing inside
  Tailscale — the phone generates its own key, shows a fingerprint, pins the
  PC's. Tailnet membership should not be the only thing between a device and
  the memory store. (`PEERS.md` #10 on the desktop branch has the design.)
- **Checks screen.** `platform/PlatformReadiness.kt`: one line saying whether
  the PC's model is on the GPU or has spilled to the CPU. The desktop shows
  this from `/api/status` (`backend/gpu-offload.patch` documents the fields).
  The phone should not be the surface that hides it.
- **Brain screen, optional.** A read-only "what did I believe on this date"
  view over `GET /api/memory/facts?known_at=`.

### Do not fold in

The twelve remaining faces (separate task). Any on-device speech-to-text.
Any approve-all, bulk-approve, or "always allow" control — there is none and
there will be none.

---

## 5. Rules that have already bitten this project

1. **Fetch before claiming anything about the server.**
   `git fetch origin claude/jarvis-desktop-tauri-vey6bc`, then `git show`.
   Five misunderstandings in two days came from reasoning about code nobody
   had fetched (`ARCHITECTURE.md` §8 lists them).
2. **Quote the evidence.** "I checked X and it says Y" beats "Y".
3. **Every change gets a test that fails on the unpatched tree.**
4. **Never compose notification text from `detail` or `prompt`.** Render the
   server's `notice`. Deny may be a notification action; Approve may never be.
5. **No on-device STT.** It moves the privacy boundary and disarms the
   owner-voice gate. The server says so in its own 503 body.
6. **No client for a route that does not exist.** Request it instead.
7. **CI is the build**, ~15 minutes a round. The desktop session can read
   your CI logs in seconds and has offered to; ask via a doc, and it will
   relay the log, not a reading of it.

---

## 6. Bug and performance findings — addendum

*An independent multi-agent review of `jarvis-client/` is running from the
desktop side: eight specialists (concurrency and lifecycle, networking and
SSE, Compose state, the audio pipeline, persistence and the exported surface,
Compose rendering cost, the face-rendering hot path, background and battery
cost), each finding then attacked by two adversarial reviewers before it
survives. What survives will be appended here with file and line. Until then
this section is deliberately empty.*

---

## 7. How to reply

Add `docs/ANDROID-REPLY-<date>.md` on your branch: what changed (commit
hashes), what you verified and how, what you could not do and why, and any
server-side change you need — as an exact route and field request, not a
wish. The desktop fetches your branch before concluding anything went
unanswered; do the same.

---

## Sources, for the web-research claims above

Everything about our own code was read from one of the two branches. These
are the outside claims, primary where the proxy allowed it:

- Hermes Agent memory approval — https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/memory.md
- GLaDOS pipeline and barge-in — https://github.com/dnhkng/GLaDOS
- Smart Turn v3 — https://github.com/pipecat-ai/smart-turn
- Wyoming protocol — https://github.com/rhasspy/wyoming
- Ollama, no native MCP — https://github.com/ollama/ollama/issues/7865
- Home Assistant MCP server — https://github.com/home-assistant/home-assistant.io/blob/current/source/_integrations/mcp_server.markdown
- Home Assistant companion quick-settings / Assist tile — https://companion.home-assistant.io/docs/integrations/android-quick-settings/
- OpenClaw approval binding (the reference if the gate ever bends) — https://github.com/openclaw/openclaw/blob/main/docs/tools/exec-approvals.md
- The notification budget — https://tianpan.co/blog/2026-05-13-background-agents-notification-budget-attention-economy
- Windows Recall bypass, "intended design" — https://www.itnews.com.au/news/microsoft-says-new-windows-recall-bypass-isnt-a-vulnerability-624918
