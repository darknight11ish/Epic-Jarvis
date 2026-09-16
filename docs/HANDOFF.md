# Handoff — Android client, 15 September 2026

Everything a new session needs to pick this up. Written for someone starting
cold, in the order they will need it.

**First: read `CLAUDE.md` at the repository root.** It records that the owner is
a beginner developer, the five non-negotiable rules, and the fact that there is
no local build. Everything below assumes it.

---

## 1. Where things stand right now

**Corrected 2026-09-16, against live GitHub data, not assumed:** everything
below this note through "Known facts about the failure" describes a CI outage
that is **over**. Runs 65, 66, 67 and 68's `build` job (verified directly via
`mcp__github__actions_get`/`actions_list`, not by re-reading this file) are
all green. The specific test this section was hunting —
`EventStreamContractTest.cancellingTheCollectorEndsTheConnection` — was found
and fixed in `9cbac9f` ("Hold the Call, not the Response, and hold it before
execute()"), whose own run (65) passed both jobs including the emulator step.
**Do not re-open this investigation** on the strength of this section's old
present-tense wording; check a fresh `list_workflow_runs` first. The
debugging lessons below (log tail truncation, etc.) are kept because they are
real and could recur with a different test.

**Branch:** `claude/android-apk-build-q435fi`.

### Historical: how a hidden test name was finally found (resolved in `9cbac9f`)

Three runs were spent on *seeing* the failure rather than fixing it, and that
is worth knowing so it is not repeated:

- The smoke job printed only a Gradle exception and a `file:///home/runner/...`
  path. Fixed in `f49b7e2` by parsing the JUnit XML inline.
- Those parsed names were then buried: GitHub's log API serves a **tail**, and
  the emulator's exit trap dumped 120 lines of boot properties *after* them.
  Fixed in `9c95a7b` (ordering) and `75e61b8` (capped the dump to 12 lines).

### Known facts about the failure (historical — fixed in `9cbac9f`)

- It was a **test failure, not a compile error**. `androidTest` compiles: run 50
  passed "Compile the app and the test".
- It was not `TokenStoreTest.anUnreadableBlobIsDroppedRatherThanThrown` — that
  one was found and fixed in `ca38fcf`.
- The actual cause: the two new contract tests added in `8f3e620`
  (`ApiContractTest`, `EventStreamContractTest`). They had never run against an
  emulator before run 52. The SSE ones involve real timing (a ~3s reconnect
  backoff, a 60s held-open body) on a 2-core runner, so a timing assumption is
  plausible.

---

## 2. What was done, and what it means

### Bugs found and fixed (all verified in the source before acting)

| Commit | What was wrong |
|---|---|
| `45c0680` | **A half-open socket condemned the link permanently.** No read timeout on `/api/events`, so a lost radio left TCP half-open forever. The watchdog latched "stale" (which refuses every approval) and never tore the socket down; the only line that clears staleness needs a frame that could not arrive. The `awaitClose` meant to fix this was unreachable — it sits after a loop that only ends once the blocking read returns. Fixed with a 90s read timeout on a stream-only client plus a child coroutine that is parked on nothing and can do the close. |
| `45c0680` | **A body carrying only `history` was read as the pending queue** — settled items shown as waiting for a decision. |
| `44a1202` | **Rule 4 was enforced in one write path out of seven.** `revert` and `cancelJob` went out against possibly hours-old state with no staleness gate, and the refusal was invisible because `InboxScreen` renders no notice surface. Added `actionBlocker()`, lifted `Freshness` into `ui/parts`, greyed the controls. |
| `44a1202` | The quick-settings tile used `STATE_UNAVAILABLE` when offline — SystemUI does not dispatch clicks to an unavailable tile, so its own reconnect branch was dead code. |
| `ca38fcf` | `require(packed.size > IV_BYTES)` was one constant loose. A GCM blob needs IV (12) **and** tag (16), so 28 is the floor. A permanently-dead blob failed inside AndroidKeyStore instead of at the structural check, which is the difference between dropping the token and keeping it. |
| `b5cdcdb` | `androidx.biometric:1.1.0` pulls `androidx.fragment:1.2.5`; `registerForActivityResult` needs 1.3.0+. Latent since the project began, because `lintVitalRelease` only runs on release builds and the release variant had never been built. |

### Work completed

- **Contract tests** (`8f3e620`) — `ApiContractTest` and `EventStreamContractTest`
  in `androidTest`, using MockWebServer **pinned to 4.12.0** (5.x replaced
  `MockResponse`'s setters with a builder, so the version is load-bearing).
  They are in `androidTest` deliberately: `JarvisApi` takes `TokenStore` as a
  constructor argument and `TokenStore` needs the real Keystore, so a JVM test
  could only reach this code by making the token store injectable — a
  production change to suit a test.
- **R8 turned on** (`d2a026c`). The blocker recorded in `build.gradle.kts` was
  out of date: `kotlinx-serialization-core` 1.7.3 ships
  `META-INF/com.android.tools/r8/kotlinx-serialization-r8.pro` and OkHttp
  4.12.0 ships `META-INF/proguard/okhttp3.pro`. Verified by unzipping the
  artifacts. **R8 itself succeeded in run 52's build job.**
- **Accessibility** (`d2a026c`). The face was a bare `Canvas` with no semantics,
  so TalkBack skipped the app's primary status indicator entirely. Now carries
  a `contentDescription` for all eight states and a polite live region.

### Audits run, and the honest verdict on them

`docs/ARCHITECTURE-PANEL-2026-09-14.md` records a four-reviewer panel, including
**three claims that did not survive checking** — two of them caused by this
repo's own stale tooling and docs. Treat every agent finding as a lead, never a
conclusion.

A later sweep for "comments that assert a guarantee the code does not provide"
checked five load-bearing claims and **all five held**. That defect class has
been worked out; do not run it again.

**Do not run another broad audit.** The face, rendering, and general
bug-hunting have each had three passes. The remaining value is in tests and in
the two things only the owner can do (below).

---

## 3. What is decided and must not be re-litigated

- **The published artifact is still the DEBUG APK.** R8 builds, but the release
  variant has never run on a device. A stripped serializer is a crash on first
  decode, not a build error. Switching what gets published waits until the
  smoke job has run *against the release variant*.
- **No local build exists.** `dl.google.com` is blocked, so the Android Gradle
  plugin cannot resolve. CI is the only compiler. Every check costs ~15 minutes.
- **The face's configurability is the owner's call, not a cleanup target.** One
  reviewer argued for deleting 36% of the client. Its own self-critique was
  right: that cut removes the lines with the best bug-per-line record and keeps
  the worst. Do not act on it.

---

## 4. Open items, in priority order

Items 1 and 2 as originally written here are DONE, verified against live CI
on 2026-09-16, not left in this list on the strength of an old draft:
the failing emulator test was fixed in `9cbac9f` (see §1's correction), and
the published APK was switched to the release build behind its own gate in
`edee026` ("Publish the release build, behind a gate that starts it first")
— run 66 and later show `Assemble release APK` and `Publish the APK to a
rolling release` both succeeding. What remains:

1. **A sleeping desktop renders as a red alarm.** `JarvisRuntime.resolveFace`
   returns `FaceState.ERROR` 12s after the link drops, before considering
   anything else, and `STANDBY`/`BANKED` are only reachable *with* a
   connection. Close the laptop at 23:00 and the phone pulses rose until
   morning, every night. Three of four reviewers found this independently.
   Needs a spec decision (a new `unreachable` state) — see
   `docs/CROSS-CLIENT-CONTRACT.md`.
2. **`versionCode` is 1 and `CrashLog` carries no build stamp**, so a crash
   report cannot say which build produced it.
3. **`ApprovalNotifier.assigned` is in-memory**, so after the process is
   reclaimed the new process cannot cancel notifications the old one posted.
   Fails safe (a stale tap hits `decisionBlocker`), so it is a lingering
   notification, not a wrong decision. `getActiveNotifications()` fixes it.
4. **`cancelHold` is unreachable** — no route serves a hold handle. The code
   says so itself. Noted so it is not rediscovered.

## 5. Only the owner can do these

- **Test push-to-talk against a real microphone.** It has never met one.
- **Pair the phone with the real desktop backend.** Everything tested so far
  talks to a fake server.

## 6. The desktop side

Separate session, branch `claude/jarvis-desktop-tauri-vey6bc`. It cannot be
reached by peer messaging (it is a cloud session and does not appear in
`ListAgents`), so the repo is the channel.

`docs/CROSS-CLIENT-CONTRACT.md` puts four questions to it that neither client
can settle alone: the origin check that forces both clients to send an
identical `X-Jarvis-Client: hud`, appearance conflict resolution, whether the
visual spec should be served rather than vendored twice, and the missing
staleness gate in its Rust `decide_approval`. **Nothing has prompted it to read
that file.** The owner has to nudge it.

## 7. Documents worth reading, in order

1. `CLAUDE.md` — how to talk to the owner, and the rules.
2. `docs/HANDOFF.md` — this file.
3. `docs/CROSS-CLIENT-CONTRACT.md` — the four cross-client questions.
4. `docs/ARCHITECTURE-PANEL-2026-09-14.md` — the panel, and what it got wrong.
5. `docs/AUDIT-2026-09-14.md` and `docs/UI-AUDIT-2026-09-14.md` — earlier audits.
6. `docs/WAKE-WORD.md` — why the wake word is blocked (needs openWakeWord model
   files; Porcupine's AccessKey would violate rule 3).
7. `docs/APPEARANCE-SYNC-PROPOSAL.md` — a proposal, not implemented, and its
   client-identity premise has been corrected.

---

## 8. Added since this handoff was written: a FAQ screen

A new `Screen.FAQ`, reachable from Home's "Help" button next to "Look". Its
own file, `ui/screens/FaqScreen.kt`, is a static list of phone-specific
questions and answers — no network calls, no new state, nothing that touches
the failing-emulator-test investigation in §1. Every answer is grounded in
this codebase (`PairingScreen.kt`'s Keystore comment, `VoiceModels.kt`'s
`clientSttAllowed`, `ReadinessScreen.kt`'s wake-word note, `ApprovalNotifier`'s
lock-screen redaction, `Speaker.kt`'s on-device-only fix, and §4 item 3's
"sleeping desktop looks like an alarm" bug above) rather than invented copy.

**Correction, 2026-09-16, after the fact:** this section originally said CI
was red for the emulator failure in §1 at the time of this commit, and that
was wrong — carried over from §1's stale wording without checking live CI
first. Runs 65-67 (before this commit) and this commit's own run (68) were
checked directly against GitHub's API afterward: all green. §1 above is now
corrected to match. This change's own build did pass, including both debug
and release APK assembly.
