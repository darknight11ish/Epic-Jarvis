# Audit prompt

Paste this, then attach `SOURCE-BUNDLE.md` (every source file in the repo) and
`AUDIT-2026-09-14.md` (the previous audit, so you can check its conclusions
rather than rediscover them).

---

You are auditing a personal, non-commercial Android project. Be adversarial and
concrete. I would much rather hear that something is wrong than have it
smoothed over.

## What this is

A native Android companion for a self-hosted "Jarvis" desktop server reached
over Tailscale. The phone holds a persistent link to the desktop, shows
approval prompts for actions the desktop wants to take, streams duplex audio,
and renders desktop telemetry. It is sideloaded over adb and never listed on
Play.

Two Gradle roots, and they are not equally important:

- **`jarvis-android/`** (~5,100 lines) — the full app: WebSocket link, HMAC-signed
  approvals, AudioRecord/AudioTrack duplex audio, three Jetpack Glance widgets,
  a Quick Settings tile, and registration as the system assistant and speech
  recognizer. This is the APK currently installed on the phone.
- **`jarvis-client/`** (~500 lines) — a rewrite against a separate written
  contract, currently at step 0: platform configuration and a readiness screen
  only. No networking yet.

`server/jarvis_mobile_ws.py` is the desktop half — a stdlib-only RFC 6455
implementation plus the approval-signature verifier.

## The five rules the app must not break

1. Anything touching email, files, credentials or stored memory stays on the
   local model. The app sends none of it anywhere.
2. The app never opens a public tunnel. No ngrok, no Cloudflare Tunnel, no
   Tailscale Funnel, no "share my Jarvis".
3. No API keys in the app. The only secret it stores is the pairing token.
4. The app never auto-approves anything, and blocks acting when the event
   stream is stale.
5. Non-commercial build. Sideloaded via adb, never listed on Play.

Treat these as the top of the severity scale. A defect that lets rule 1, 3 or 4
be violated outranks any crash.

## What just happened

A five-reviewer audit ran (the attached `AUDIT-2026-09-14.md`) and its findings
were then fixed. So the code you are reading is **post-fix** — and post-CI: both
modules compile, both test suites pass, and both debug APKs assemble on the
commit in the bundle. "It builds" is therefore not a finding; what it does at
runtime still is.
Your job is not to re-derive that audit. It is to answer three questions:

### 1. Did the fixes actually work, or do they just look like they did?

For each of these, check the current code and say whether the hole is genuinely
closed, partly closed, or closed in one place and still open in another:

- `JarvisSettings.hostOf` now parses with `java.net.URI` instead of splitting
  the authority on `:`. Is there any input for which `URI(url).host` and
  OkHttp's own parser disagree about the host? That disagreement is the whole
  bug class. Check IDN/punycode, percent-encoding, backslashes, a trailing dot,
  a null byte, and whatever else you can think of.
- `JarvisRuntime.approvalBlocker` gates decisions on the request being pending,
  unexpired and the link being CONNECTED. Find a path to
  `submitApprovalDecision` that bypasses it, or a way to make `_pendingApprovals`
  contain something the user never saw.
- Approval decisions are now persisted to `PendingDecisionStore` before the send
  is attempted, and replayed from `onConnected`. Can a decision be lost, sent
  twice with different content, or replayed in a way that means something
  different from what the user agreed to?
- `JarvisWebSocketManager` now runs its dial state machine under one lock and
  bumps an `AtomicInteger` generation in `openSocket` and `disconnect`. Find a
  remaining interleaving that produces two live sockets, or a socket that
  survives `disconnect()`.
- The socket now blocks its reader thread (`runBlocking { signals.send(...) }`)
  when the consumer is behind, rather than dropping frames. Find a deadlock:
  any path where a thread holding the socket's lock ends up waiting on that
  channel, or where the single consumer coroutine ends up waiting on something
  only the blocked reader thread can provide.
- `AudioPlayer` and `AudioStreamer` now have the writer/reader coroutine own and
  release the native object, with the caller only pausing and flushing. Check
  the teardown orderings and the `streamToken` logic in `AudioPlayer.finish`.

### 2. What did the previous audit get wrong or miss?

It recorded two corrections already — read them, and check *those* too. It
concluded the audio release race could not crash the process because
`AudioTrack.write` and `AudioRecord.read` return `ERROR_INVALID_OPERATION`
rather than throwing. Verify that against the actual platform source or
documentation and say if it is wrong.

Then look for what five reviewers did not: I am specifically interested in the
Markdown renderer (`MarkdownText.kt`) and diff engine (`NoteDiff.kt`), which
nobody examined closely, and in `server/jarvis_mobile_ws.py`, which hand-rolls
RFC 6455 framing.

### 3. Does the wire protocol hold up against a hostile desktop?

Assume the desktop is compromised, or that something else on the Tailnet can
reach the port. Every inbound event is attacker-controlled. What can it do to
the phone? Look at the base64 audio path, the binary frame tag, the WAV header
strip, `device_command`, and the note-edit payload that feeds the diff viewer.

## Ground rules for your findings

- **Cite `file.kt:line`.** A finding without a location is not a finding.
- **Give the concrete sequence.** "Thread A is at line X while thread B reaches
  line Y" — not "this could race".
- **Check the platform semantics before asserting a crash.** The previous audit
  claimed a process crash from a native call that actually returns an error
  code. If you assert a throw, name the method and the condition under which it
  throws.
- **Say when something is fine.** A short "checked and clear" list is useful,
  and it tells me what you actually read.
- **Rank by the five rules first, then by whether a user would notice.** A
  silent wrong answer beats a loud crash for severity: this app's failure mode
  of record is the user believing they approved something that never arrived.
- If the code and a comment disagree, **the code wins** — and tell me, because a
  comment asserting the opposite of what the code does is its own defect. There
  are several in this repo's history.

## Known and deliberate — do not report these as defects

- Cleartext `ws://` over the Tailnet is intended. Android's network security
  config takes hostnames and IP literals, not CIDR ranges, so 100.64.0.0/10
  cannot be expressed there and the check lives in
  `JarvisSettings.isCleartextTargetPrivate`. Attack *that check*, not the
  decision.
- `jarvis-android` is the older app and `jarvis-client` supersedes it. Findings
  in the former are still worth having — it is the installed APK — but say which
  module you are in.
- Debug signing and no release build are deliberate (rule 5).
- A persistent socket instead of FCM is deliberate (rule 1: FCM routes through
  Google).
- `jarvis-client` has no networking yet. Do not report the absence of step 2.

## Output

One ranked list, most severe first. For each: severity, module, `file:line`, the
sequence, and the smallest fix that closes it. Then a "checked and clear"
section. Then one paragraph per rule saying whether the code currently upholds
it.
