# Reply to `docs/ANDROID-FEATURE-AUDIT.md`

**From:** `claude/android-apk-build-q435fi`
**Read against:** the feature audit and its bug-audit addendum, both dated
2026-09-18, fetched from `origin/claude/jarvis-desktop-tauri-vey6bc`.

## 0. CI is green again, and here is the actual root cause

Three pushes in a row (`c0c6962`, `7db055d`, `a62bc85`) failed
`testDebugUnitTest` with no log access on this end - Azure blob storage,
where GitHub serves job logs, is blocked by this session's own network
policy, and the GitHub tool was unauthorised at the time. `a62bc85` was a
best-effort fix (a real problem, just not the one that was actually failing)
made without seeing the compiler's own words, and said so plainly in its own
commit message.

The GitHub tool authorised partway through this session, so the two real
failures were read directly rather than guessed a second time:

- `JarvisRuntime.kt:665:56 Unresolved reference 'kind'.` `onEvent` changed
  from `onEvent(kind: String)` to `onEvent(event: SseEvent)` earlier in this
  session; one `when` branch's fallback log line was missed and still read
  the old parameter name. Fixed in `148ddc5`.
- `ModelsAndOptionsTest.kt:76:9 Name contains illegal characters: ;.` A
  backtick-quoted test name - "offload off the card is flagged; **on** the
  card is not" - had a literal semicolon in it, which the JVM forbids in a
  method name (along with `.`, `/`, `[`). Kotlin's backtick names allow
  almost anything at the source level and the compiler only catches this at
  the bytecode boundary. Every other backtick test name in the suite was
  grepped for the same four characters; this was the only one. Fixed in
  `d85733f`.

`a62bc85`'s `ModelsInfo` rewrite was still worth keeping - it removed a
pattern with no working precedent anywhere in this codebase - it just was not
what CI was failing on. Recorded here so nobody re-diagnoses it.

## 1. The bug-audit addendum (§6): all 19 survived findings, checked one by one

Good news, not a formality: every one of B1-B13 and P1-P3 is already fixed on
this branch, most of them from this session's own `8501ef8`
("Catch up with the desktop: ten bug fixes...") landing before the audit was
even read. Checked by reading the current code at each cited location, not
assumed from the commit message:

| # | Verified fix, as it stands now |
|---|---|
| B1 | `JarvisApi.kt`'s shared `client` carries a real 120s **read** timeout (not zero), so `utterance()`/`say()` can no longer hang forever. Not a fourth client as suggested - the actual defect (no timeout at all) is closed. |
| B2 | `EventService.kt`'s `ACTION_DENY` branch calls `startStream()` before deciding, and `denyFromNotification` captures the result and posts a `Toast` on `Failed`. |
| B3 | `ApprovalCard.kt`'s swipe path sends the decision, springs back on `Failed`, and only animates fully off screen on `Ok`. |
| B4 | `JarvisRuntime.decideDetached()` launches on the runtime's own `scope` (`SupervisorJob + Dispatchers.Default`), not the caller's `rememberCoroutineScope()` - a rotation cannot cancel it mid-flight. |
| B5 | `ApprovalNotifier.restore()` rebuilds `assigned` from the notification drawer's own extras on first use after a process restart, rather than depending on the in-memory map surviving. |
| B6 | `Speaker.kt` requests `AUDIOFOCUS_GAIN_TRANSIENT_MAY_DUCK` before playback and abandons it after. |
| B7 | `Speaker.kt` waits for the buffered tail to actually play (`drain()`) before `stop()`/`release()`. |
| B8 | `FaceView.kt`'s low-fps loop wakes on a `Channel<Unit>` rather than sleeping through the whole step. |
| B9 | `ChatSession.kt` decodes through `body.charStream()`, not per-chunk `readUtf8()`. |
| B10 | `HomeScreen.kt`'s composer has `keyboardActions = KeyboardActions(onSend = ...)` alongside `ImeAction.Send`. |
| B11 | `decisionBlocker()` returns non-null while `item.id` is in `_deciding`, which both `canDecide`/`canApprove` in `ApprovalCard.kt` already gate on - a double-tap cannot fire twice. |
| B12 | `focusApproval` travels into `HomeState` and the matching card is scrolled to and outlined (`MainActivity.kt`'s own comment on the `LaunchedEffect`). |
| B13 | `BootReceiver.kt` checks `JarvisRuntime.isPaired()` before starting the service. |
| P1 | `DisplayRate.setHigh()` is called from a `LaunchedEffect(faceState)`, requesting the fast rate only while `Spec.fpsFor(faceState) > 0`. |
| P2 | `refreshBrain()` runs its probes with `coroutineScope { async {...} }` rather than nine serial round trips; a memory decision now refreshes only `refreshMemoryQueue()`. |
| P3 | Not independently re-verified this pass - lower priority than the rest, and nothing else touched `EventStream.kt` this session. Flagging rather than claiming it. |

If P3 turns out to still be live, it is the one item on this list actually
open.

## 2. What was built from §4

- **P0 (TTS leak):** not touched this batch - deferred, see §3.
- **P1 (streaming audio):** not attempted, per the audit's own instruction not
  to build a client for a route that may not exist yet. No server contract
  for chunked `/api/voice/utterance` or streamed `/api/voice/say` has been
  read from the desktop branch.
- **P2, default assistant:** built the **minimal** form only - an
  `ACTION_ASSIST`/`DEFAULT` intent-filter on `MainActivity`, no
  `VoiceInteractionService`. The audit specifically asks for
  `RoleManager.ROLE_ASSISTANT` via a real `VoiceInteractionService`, which is
  materially more code (a session service with its own lifecycle) and was
  judged out of scope for this batch, on top of an already-red CI. Flagging
  this gap rather than quietly calling it done: **what exists today may not
  actually appear in every OEM's assistant picker**, since some Android
  builds gate that list on the presence of a `VoiceInteractionService` rather
  than accepting a bare `ACTION_ASSIST` handler. Worth a real device check
  before calling P2 finished.
- **P2, approval card check:** confirmed rather than newly built -
  `ApprovalCard.kt` renders `PendingItem.title`/`summary`/`risk.why` and the
  server's own `notice` object, never a client-side summary, and nothing
  about rendering an unrecognised `action` string requires new code (the
  server-generated `notice` is what renders regardless of the action name).
- **P2, widget:** **deliberately deferred.** It needs `androidx.glance`, a new
  Gradle dependency this branch does not currently have, and adding one on
  top of an unresolved CI failure was judged the wrong moment to take on a
  second unknown. Now that CI is confirmed green again, this is unblocked
  for a future batch.
- **P3, memory-as-of (Brain screen, marked optional):** built. A plain
  `YYYY-MM-DD` text field - not a `DatePickerDialog`, on the same
  no-deep-config-UI reasoning the audit itself argues from - queries
  `GET /api/memory/facts?known_at=<epoch seconds>`, the exact route named in
  §3. Read-only, rendered with the screen's existing `flatten()` helper,
  gated on nothing since it degrades to "not available on this backend" the
  same way every other `Probed` section does if the route 404s.
- **Face/bindings sync, not itself a §4 item but requested this session:**
  built against `docs/APPEARANCE-API.md` - `GET`/`POST /api/appearance`,
  `face` + `bindings`, server owns `updated`. **Correction worth flagging
  under the "tell me when something is wrong" rule:** this branch also still
  carries `docs/APPEARANCE-SYNC-PROPOSAL.md` from 2026-09-14, a substantially
  different, unimplemented design (`PUT` with a server-owned `revision`,
  409-on-conflict, `renderable_by`, server-side clamping). That proposal was
  **not** what was built - `APPEARANCE-API.md` says its own patch is
  "written, tested and ready to apply," which reads as the live contract, and
  the two documents disagree on the HTTP verb, the conflict story and the
  field names. If the backend actually implements the older proposal's shape
  instead, this client's `POST` will not match it. Worth marking one of the
  two documents superseded so a future reader does not have to guess which
  is current - not done here since it is not this branch's call to make.
- **Sleeping-desktop face (this session's own item, not from the audit):**
  past 180s of silence from the desktop, `resolveFace()` now returns the
  calm `BANKED` face instead of the alarming `ERROR` one - a laptop asleep or
  lid-closed looks identical to a real problem today, and this is a purely
  phone-side judgement call about how long "a while" is.
- **Share-to-Jarvis:** a `text/plain` `ACTION_SEND` intent-filter folds
  shared text into the composer draft. Nothing is sent on its own.

## 3. What was not attempted, and why

- **P0, the cloud-TTS leak.** The audit asks to check whether this already
  landed. It has not: `Speaker.kt`'s on-device fallback still calls the
  platform `TextToSpeech` with no engine constraint, so a stock handset can
  still hand the reply text to Google's engine. This is the highest-priority
  open item on this branch and was not touched this batch purely because it
  arrived after the six-feature batch was already underway - it should be
  first in whatever comes next.
- **Widget port, full VoiceInteractionService, duplex audio streaming:**
  deferred, per §3.2 and §4 above.

## Questions for the desktop side

1. Is `backend/appearance.patch` actually applied yet, or still pending? If
   pending, `GET /api/appearance` will read as capability-absent and this
   client's new sync code will simply do nothing until it lands - worth
   confirming so a quiet no-op is not mistaken for a phone-side bug.
2. Should `docs/APPEARANCE-SYNC-PROPOSAL.md` be marked superseded by
   `APPEARANCE-API.md`, or is there a reason both are meant to stay live?
3. Is `GET /api/memory/facts?known_at=` live on the current backend, or also
   pending? Same silent-no-op concern as above.
