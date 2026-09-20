# Audit prompt — `jarvis-client`

Paste everything below the line into Gemini, and attach **`SOURCE-BUNDLE.md`**
(every source file in the module, plus the CI workflows that build it — 107
files, ~1.3 MB, regenerated against commit `a708467` on `main`).

Do **not** attach `AUDIT-2026-09-14.md` — it describes this module at
"step 0, 435 lines, no networking", which was true six days ago and is not
true now. It would mislead an auditor rather than help one.

Optionally attach `AUDIT-FINDINGS-2026-09-19.md` and `UI-AUDIT-2026-09-18.md`
instead — both are recent and both cover this module (the first is a 4-language
bug audit that includes a Kotlin pass; the second is Android-specific UI
findings). Attaching them makes the review sharper, because it can check those
conclusions rather than rediscover them. Leaving them off gives you a clean
second opinion. Both are reasonable; don't attach them if you want to know
whether an independent reader reaches the same findings on its own.

---

You are auditing a personal, non-commercial Android app. Be adversarial,
specific and unsparing. I would much rather be told something is broken than
have it smoothed over, and "looks fine" on a file you did not actually read is
worse than saying you skipped it.

## What this is

A native Jetpack Compose client for a self-hosted "Jarvis" assistant whose
Python backend runs on my desktop. The phone reaches it over Tailscale on a
private network. It is sideloaded via adb and will never be listed on Play.

The phone can: pair with the desktop using a token, hold an SSE event stream,
chat with streaming replies, show and decide approval requests (including
from two home-screen widgets built with Glance), render an animated "reactor"
face with a real GPU-accelerated rendering path for some states, capture
push-to-talk audio for the desktop to verify and transcribe, register as the
phone's assist app (`RoleManager.ROLE_ASSISTANT`) without doing any
speech-to-text of its own, pause/resume/stop/annotate a running desktop task,
and sync appearance/bindings with the desktop.

## What's new since the last full audit (14 Sep)

This module has grown enormously — from 435 lines to 107 files — since it was
last bundled whole for an outside reviewer. In rough order of how much is
unexamined:

- **A real GPU rendering path for the reactor face** (`face/`) — a GLES 3.0
  mesh pipeline and an AGSL fragment shader for some states, added to reach
  parity with the desktop's twenty faces. Entirely new since 14 Sep and the
  least scrutinized code in the app.
- **`VoiceInteractionService`/`RecognitionService` registration**, so the
  phone can be set as the system assistant. This includes a stub recognizer
  that exists only to satisfy the Android schema and is required to do
  nothing — check it cannot become reachable as a real speech recognizer by
  any path (`android:selectableAsDefault` on the `<recognition-service>` in
  `res/xml/recognition_service.xml`, and whether any intent-filter makes it
  discoverable beyond that attribute).
- **Two Glance home-screen widgets** (`widget/`) — approvals and a quick
  link/mic action — each independently reading the same runtime state the
  in-app screens do. Look for either widget going stale or showing "nothing
  waiting" when it actually has no data yet, as opposed to when there
  genuinely is nothing waiting.
- **Task control and approval notes** (pause/resume/stop/inject-note/amend,
  `docs/AUTONOMY-PROPOSALS.md` §3b/§3d) — new commands sent over HTTP,
  independent of the approve/deny path.
- **Chat networking was rewritten this session** (`net/ChatSession.kt`,
  `net/ChatChunkParser.kt`, `net/JarvisApi.kt`). The request body changed
  shape entirely (`{"message": ...}` → a `messages` array, matching what the
  real backend actually reads), and the response reader went from
  appending raw decoded characters with no parsing to a line-buffered parser
  handling both a plain token stream and SSE-`data:`-framed chunks, with
  proactive stream termination. This is days old and has never been
  compiled or run — no Android SDK is available in the environment that
  wrote it, so it has only been checked by careful re-reading plus CI's
  compile step. Please look hard at this.
- **A multi-option approval flow** (`ApiModels.kt`'s `needsChoice`,
  `ApprovalCard.kt`) exists because a pending item can offer more than one
  plan to choose between, but no server route exists yet that can tell the
  server WHICH option was picked — so this client (correctly, on purpose)
  refuses to let a multi-option item be approved from here at all, and only
  denial stays available. Check this restraint actually holds everywhere an
  approval can be decided (the notification action, the widget, a swipe,
  the in-app card) — a single path that forgets to check `needsChoice` would
  let an approval go through with the wrong plan silently applied.

## The five rules this app must not break

These are non-negotiable and they are the first thing I want checked. For each
one, tell me whether the code actually enforces it, citing files and lines —
not whether a comment claims it does.

1. **Anything touching email, files, credentials or stored memory stays on the
   local model. The app sends none of it anywhere.**
2. **The app never opens a public tunnel.** No ngrok, no Cloudflare Tunnel, no
   Tailscale Funnel, no "share my Jarvis".
3. **API keys are allowed now** (reversed 2026-09-17), but every key — and the
   pairing token — gets the same care: never logged, sent only to the one
   service it authenticates against, never written to disk in plain text,
   including in crash reports.
4. **The app never auto-approves anything, and blocks acting when the event
   stream is stale.**
5. **Non-commercial build, sideloaded, never on Play.**

Four more constraints from the server's own API contract:

- A client **must not do speech-to-text**. The desktop runs an owner
  voice-print gate, and it can only check a voice if it is given the voice.
  Sending text instead would turn "is this the owner?" into "is this someone
  holding the owner's phone?". The status endpoint carries
  `audio_in.client_stt_allowed: false`.
- **No control may clear a rush latch or approve in bulk.**
- `X-Jarvis-Client: hud` on every request.
- **The pairing token (and any API key) must never be logged** or written to
  any file that gets read aloud, pasted or shared — including crash reports.
- The model catalogue, the memory graph, and deep config editing all stay off
  the phone on purpose — flag it if any of the new work quietly grew toward
  any of the three.

## What I want most: comments that lie

This code is unusually heavily commented, and the comments assert invariants.
That is a liability as much as an asset. **Find every place where a comment
claims a property the code does not actually have** — a guarantee that isn't
enforced, a "this can never happen" that can, a rationale that stopped being
true when the code around it changed, a doc-comment describing an earlier
design. I consider these the highest-value findings in the whole review,
because they are the ones a reader cannot catch by reading carefully.

## Specific things to attack

- **The GPU/GL face rendering** (`face/`), because it is brand new. Look for
  GL state leaks across frames or lifecycle events, a shader compiled once
  and assumed to survive a context loss, and anything that skips the
  photosensitivity limits (max transitions per second, minimum strobe
  period, flicker rate cap) that the non-GPU faces respect.
- **The audio layer** (`audio/`, `voice/`). `Recorder` captures into a
  growable primitive array; `Wav` encodes, resamples and parses RIFF;
  `Speaker` plays via `AudioTrack` with a `TextToSpeech` fallback. Look for
  buffer arithmetic errors, off-by-ones in the resampler, anything that
  misreads a WAV header, and lifecycle leaks of
  `AudioRecord`/`AudioTrack`/`TextToSpeech`.
- **Concurrency in `VoiceSession`.** One coroutine owns a capture. Consider
  cancel racing completion, a second `begin()` arriving during teardown, and
  whether any `StateFlow` can be left in a phase that never clears.
- **`TokenStore`.** Hand-rolled AES-GCM against the Android Keystore rather
  than `EncryptedSharedPreferences`. Check the IV handling, the failure
  paths, and whether an unreadable blob can ever be treated as a valid
  token.
- **The stale gate.** `JarvisRuntime.decisionBlocker` is the enforcement
  point for rule 4. Find any path that can approve or deny without
  consulting it — including from either widget and from the notification
  action, which are easy to add without routing through the same check the
  in-app screen uses.
- **`net/ChatChunkParser.kt` and `net/ChatSession.kt`**, rewritten this
  session and described above. It is a hand port of a JavaScript reference
  (`jarvis-desktop/src/main.js`'s `consumeLine`/`deltaFromChunk`/
  `isTerminal`) — check the port is faithful to the fallback order, not just
  superficially similar, and that a chunk shape the fallback chain doesn't
  recognize fails safe (shows nothing) rather than silently mis-rendering.
- **The SSE parser and `JarvisApi`'s response handling generally.** Look for
  wrapper shapes that would silently parse as empty — an arriving approval
  rendering as "nothing waiting" is the worst failure this app has.
- **The two Glance widgets.** Do they ever show a state (like "Nothing
  waiting") that means "I have no data" as if it meant "I checked and there
  is nothing"? Those are different facts and this app has confused them
  before.
- **The face engine's non-GPU faces** (`face/`, ported from a JavaScript
  reference). The photosensitivity limits again — check the arithmetic
  actually respects them rather than restating the numbers.
- **The wake-word control** on the readiness screen. It is deliberately
  off-only. Check that "could not reach the desktop" can never render as
  "off", and that the displayed state is the desktop's reported one rather
  than the one just requested.

## What I already know, so don't spend the review on it

- **This code has never been compiled on the machine that wrote it.** The
  Android Gradle plugin cannot be resolved through that network, so CI is
  the only thing that builds it. Assume no local verification of anything
  beyond careful re-reading.
- **CI does now compile it and boot it on an emulator** (a `build` job and a
  `smoke` job in `.github/workflows/jarvis-client.yml`), so "does this even
  compile" is answered by CI, not by this review. The `smoke` job's
  emulator step is currently broken by an unrelated CI-infrastructure issue
  (a `Failed to find ColorBuffer` GPU-emulation error in the runner itself,
  confirmed to reproduce identically on unrelated commits) — that is a CI
  environment problem, not a finding about the app.
- **Push-to-talk has never met a real microphone.** Capture, playback and
  the permission flow are untested on hardware.
- **The wake word is not built.** No model is bundled and the phone never
  listens for a phrase. Only the off switch exists.
- `versionCode` is pinned at 1 on purpose, so any build installs over any
  other.
- The app is signed with a debug key taken from a GitHub secret at build
  time, on purpose, so builds install over each other. It is not a secret
  and not a finding if you see it referenced.
- **No client can tell the server which option was picked on a multi-option
  approval yet** (see above) — that is known, deliberate, and the mitigation
  (refusing to approve at all in that case) is exactly what I want checked,
  not the gap's existence.

## What I do not want suggested

Play Store policy compliance. Analytics, telemetry or crash-reporting SaaS. Any
tunnelling or remote-access service. A model catalogue, a memory graph, or deep
config editing on the phone — all three are deliberately out of scope. Generic
advice about dependency injection frameworks or architecture patterns, unless
a specific bug follows from the current shape.

## How to report

Rank findings by severity: what can lose data, expose the token or a key, act
without consent, or crash — before style.

For each finding give me:
1. **File and line.**
2. **What is wrong**, in one sentence.
3. **A concrete failure scenario** — specific inputs or a specific sequence of
   events leading to a specific wrong outcome. If you cannot write one, say so
   and mark the finding as speculative rather than dropping it.
4. **The smallest fix**, and what it would break.

End with two short lists:
- **The three things you would check first on a real device**, given that
  hardware audio and the GPU rendering path are the untested parts.
- **Anything you could not judge from the source alone**, and what you would
  need to see.

If you disagree with a design decision rather than finding a bug, say so
separately and label it as such. Do not pad the review — a short list of real
findings is worth more than a long list that includes things you are unsure
about, as long as you say which is which.
