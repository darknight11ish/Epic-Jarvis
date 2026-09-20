# Audit prompt — `jarvis-client`

Paste everything below the line into Gemini, and attach **`SOURCE-BUNDLE.md`**
(every source file in the module, plus the CI workflows that build it).

Optionally also attach `AUDIT-2026-09-14.md` — three earlier audit passes on this
code. Attaching it makes the review sharper, because it can check those
conclusions rather than rediscover them. Leaving it off gives you a clean second
opinion. Both are reasonable; don't attach it if you want to know whether an
independent reader reaches the same findings.

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
chat with streaming replies, show and decide approval requests, render an
animated "reactor" face, and capture push-to-talk audio for the desktop to
verify and transcribe.

## The five rules this app must not break

These are non-negotiable and they are the first thing I want checked. For each
one, tell me whether the code actually enforces it, citing files and lines —
not whether a comment claims it does.

1. **Anything touching email, files, credentials or stored memory stays on the
   local model. The app sends none of it anywhere.**
2. **The app never opens a public tunnel.** No ngrok, no Cloudflare Tunnel, no
   Tailscale Funnel, no "share my Jarvis".
3. **No API keys in the app. The only secret it stores is the pairing token.**
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
- **The pairing token must never be logged** or written to any file that gets
  read aloud, pasted or shared — including crash reports.

## What I want most: comments that lie

This code is unusually heavily commented, and the comments assert invariants.
That is a liability as much as an asset. **Find every place where a comment
claims a property the code does not actually have** — a guarantee that isn't
enforced, a "this can never happen" that can, a rationale that stopped being
true when the code around it changed, a doc-comment describing an earlier
design. I consider these the highest-value findings in the whole review,
because they are the ones a reader cannot catch by reading carefully.

## Specific things to attack

- **The audio layer** (`audio/`, `voice/`). Newest code, and the least
  exercised. `Recorder` captures into a growable primitive array; `Wav` encodes,
  resamples and parses RIFF; `Speaker` plays via `AudioTrack` with a
  `TextToSpeech` fallback. Look for buffer arithmetic errors, off-by-ones in the
  resampler, anything that misreads a WAV header, and lifecycle leaks of
  `AudioRecord`/`AudioTrack`/`TextToSpeech`.
- **Concurrency in `VoiceSession`.** One coroutine owns a capture. Consider
  cancel racing completion, a second `begin()` arriving during teardown, and
  whether any `StateFlow` can be left in a phase that never clears.
- **`TokenStore`.** Hand-rolled AES-GCM against the Android Keystore rather than
  `EncryptedSharedPreferences`. Check the IV handling, the failure paths, and
  whether an unreadable blob can ever be treated as a valid token.
- **The stale gate.** `JarvisRuntime.decisionBlocker` is the enforcement point
  for rule 4. Find any path that can approve or deny without consulting it.
- **The SSE parser and `JarvisApi`'s response handling.** Look for wrapper
  shapes that would silently parse as empty — an arriving approval rendering as
  "nothing waiting" is the worst failure this app has.
- **The face engine** (`face/`). It ports a JavaScript reference. There are
  photosensitivity limits in the spec (max transitions per second, minimum
  strobe period, flicker rate cap). Check the arithmetic actually respects them
  rather than restating the numbers.
- **The wake-word control** on the readiness screen. It is deliberately
  off-only. Check that "could not reach the desktop" can never render as "off",
  and that the displayed state is the desktop's reported one rather than the
  one just requested.

## What I already know, so don't spend the review on it

- **This code has never been compiled on the machine that wrote it.** The
  Android Gradle plugin cannot be resolved through that network, so CI is the
  only thing that builds it. Assume no local verification of anything.
- **Push-to-talk has never met a real microphone.** Capture, playback and the
  permission flow are untested on hardware.
- **The wake word is not built.** No model is bundled and the phone never
  listens for a phrase. Only the off switch exists.
- `versionCode` is pinned at 1 on purpose, so any build installs over any other.
- The app is signed with a debug key committed to the repo, on purpose, so
  builds install over each other. It is not a secret and not a finding.

## What I do not want suggested

Play Store policy compliance. Analytics, telemetry or crash-reporting SaaS. Any
tunnelling or remote-access service. Anything requiring an API key. A model
catalogue, a memory graph, or deep config editing on the phone — all three are
deliberately out of scope. Generic advice about dependency injection frameworks
or architecture patterns, unless a specific bug follows from the current shape.

## How to report

Rank findings by severity: what can lose data, expose the token, act without
consent, or crash — before style.

For each finding give me:
1. **File and line.**
2. **What is wrong**, in one sentence.
3. **A concrete failure scenario** — specific inputs or a specific sequence of
   events leading to a specific wrong outcome. If you cannot write one, say so
   and mark the finding as speculative rather than dropping it.
4. **The smallest fix**, and what it would break.

End with two short lists:
- **The three things you would check first on a real device**, given that
  hardware audio is the untested part.
- **Anything you could not judge from the source alone**, and what you would
  need to see.

If you disagree with a design decision rather than finding a bug, say so
separately and label it as such. Do not pad the review — a short list of real
findings is worth more than a long list that includes things you are unsure
about, as long as you say which is which.
