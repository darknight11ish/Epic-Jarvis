# Audit stream C — Android Kotlin + phone/desktop contracts

**Target:** clean `main` worktree `.dsh-scratch/audit-main` (detached HEAD `fa2b379f` = `origin/main`).
**Scope audited:** `jarvis-client/**` (488 Kotlin files, 153,368 lines), `jarvis-android/**`,
`contract/**`, and the phone-side fixture generators under `tools/` that feed the Kotlin tests.
**Method:** read-and-reason. No Gradle build was attempted (no Android SDK assumed). Python
tools were run read-only where that gave hard evidence. `grep`/`glob` sweeps over all 488 Kotlin
files; ≈9,500 lines read line by line across ~60 files, plus the backend producers they talk to.

**Headline:** `jarvis-client` is exceptionally well defended — every pattern on the brief's hunt list
that I could test came back either handled or handled twice. The real findings are therefore mostly
at the *edges*: one home-screen redraw path that was missed while its neighbour was fixed, and three
places where nothing in CI enforces a contract that the code assumes. `jarvis-android` is the one
place with rule violations, and they are already partly written down in `docs/`.

Severity counts: **Critical 0 · High 0 · Medium 3 · Low 2**.

**Audit-target integrity — read this before merging any stream's findings.** The worktree's HEAD is
still `fa2b379f`, but its *working tree* was modified by another stream while this pass ran:

```
$ git -C .dsh-scratch/audit-main status --porcelain
 M backend/_apply_toml_tiers.py        (23:21:48)
 M backend/_where.py                   (23:22:00)  — 13 added / 6 removed lines of real content
 M backend/decks_fsrs_golden.json      (23:14:29)
 M backend/jarvis_scrub.py             (23:21:43)
 M jarvis-client/app/src/main/java/com/jarvis/client/face/Palette.kt        (23:14:34) — 51/51 lines
 M jarvis-client/app/src/test/resources/pattern-golden.json                 (23:14:30)
?? backend/run_suites_audit.py
```

I wrote nothing into the worktree (my only write anywhere is this report; the audit rules say
READ-ONLY). `backend/_where.py` is a genuine source edit with new comment prose, so this is not just
line-ending churn, and it means the tree is no longer byte-identical to `origin/main`. None of the
lines I cite below are in those six files, so my line references hold — but the Lead should decide
whether to `git checkout -- .` the worktree before anyone else's findings are merged, and should ask
whoever ran the writing tool to stop.

---

## C1. The approval widget is never redrawn when App lock or "Hide memory lists" changes

**Where:** `jarvis-client/app/src/main/java/com/jarvis/client/JarvisRuntime.kt:882`
(redraw trigger) against `jarvis-client/app/src/main/java/com/jarvis/client/widget/ApprovalWidget.kt:104`

Evidence — the approvals widget redraws on three flows only:

```kotlin
// JarvisRuntime.kt:881
widgetJob = scope.launch {
    combine(_pending, _link, _stale) { _, _, _ -> }.collect {
        ApprovalWidget().updateAll(app)
        QuickLinkWidget().updateAll(app)
    }
}
```

while `settings.security` is not among them, and the widget reads it at draw time:

```kotlin
// ApprovalWidget.kt:104
val security = if (ready) JarvisRuntime.settings.security.value else null
val hidden = ApprovalWidgetRules.hidden(
    settingsKnown = security != null,
    appLock = security?.appLock == true,
    privateLists = security?.privateLists == true,
)
```

The *next* job in the same file does include it. The comment is `JarvisRuntime.kt:889-892`; the code
is `:895-899` (both verbatim):

```kotlin
// JarvisRuntime.kt:895
boardJob = scope.launch {
    combine(_link, _stale, _scheduleTick, _widgetsTick, settings.homeWidgets) { _, _, _, _, _ -> }
        .combine(settings.security) { _, _ -> }
        .collect { com.jarvis.client.widget.JarvisBoardWidgets.updateAll(app) }
}
```

> `... when App lock or "Hide memory lists" changes (so the words hide, and the buttons turn into`
> `"open Jarvis", at once - not up to 30 minutes later).`

and the approvals widget is never redrawn on a clock, because its provider declares none:

```xml
<!-- app/src/main/res/xml/widget_approval_info.xml:18 -->
android:updatePeriodMillis="0"
```

**What happens:** the owner turns App lock on (or "Hide memory lists and chat history"). The in-app
rule is instant — `ui/screens/SecurityScreen.kt:259` promises "Turning something on is instant", and
`ApprovalWidgetRules.HIDDEN_TITLE` exists so the public home screen then shows only
"A decision is waiting". But an approval card *already on the home screen* keeps rendering its full
`notice.title` and `notice.body`, and keeps `denyActsDirectly(hidden = false, …)` — a one-tap Deny
that the rule says should open the locked app first
(`widget/ApprovalWidgetRules.kt:20-24`). It stays that way until `_pending`, `_link` or `_stale`
changes, which on a quiet queue can be never: `updatePeriodMillis` is 0, so nothing re-draws it.
The same missing key is at the notification half —
`service/EventService.kt:78-82` re-syncs `ApprovalNotifier` on `combine(link, activity, pending)`
only, while `service/ApprovalNotifier.kt:263` reads `settings.security.value` when it builds the
notification.

**Confidence:** Confirmed (both ends read; the neighbouring job proves the intended behaviour).
**Severity:** Medium.
**Obvious or subtle:** obvious — the fix is the exact line the board widgets already carry.
**Fix:** add `.combine(settings.security) { _, _ -> }` to `widgetJob` at `JarvisRuntime.kt:882`, and
add `settings.security` to the `combine` at `EventService.kt:78` so a posted approval notification is
re-built when the lock changes.

---

## C2. CI never regenerates or compares 44 of the 47 phone contract fixtures

**Where:** `.github/workflows/ci.yml:240` (the complete list of fixture checks that run)

Evidence — every `--check` run in every workflow, exhaustively:

```
ci.yml:240  python tools/gen_critters.py --check
ci.yml:247  run: python tools/gen_lipsync.py --check
ci.yml:255  python tools/gen_sky.py --check
ci.yml:256  python tools/gen_sky_cases.py --check
ci.yml:263  run: python tools/gen_animal_cases.py --check
ci.yml:283  python tools/gen_season.py --check
ci.yml:1079 python3 ../../tools/gen_notices.py --check
```

The phone's tests decode 47 checked-in wire fixtures from
`jarvis-client/app/src/test/resources/contract/`, each written by a generator that already supports
the mode being skipped. Only three of those 47 are covered by a CI step: `animal-cases.json`
(`ci.yml:263`), `sky-cases.json` (`ci.yml:256`), and `pending-rows.json`
(`backend/test_approval_contract.py`, run through `backend/run_suites.py` — I ran it: 67 passed).
The other 44 — `pairing-cases.json`, `asks-first-cases.json`, `phone-voice-cases.json`,
`menu-cases.json`, `history-cases.json`, `live-cases.json`, `second-card-cases.json`, … — have a
generator with `--check` (`tools/gen_pairing_cases.py:212`, `tools/gen_asks_first_cases.py:145`, …)
that no workflow ever calls. Example pair: `PairWordsContractTest.kt:24` reads
`contract/pairing-cases.json`; `tools/gen_pairing_cases.py` is never run by CI.

**What happens:** the phone's contract tests assert the Kotlin decoder against a fixture, and nothing
asserts the fixture against the producer. A backend module changes; the fixture keeps the old shape;
`AsksFirstTest`/`PairWordsContractTest` stay green while the real PC answers something the phone no
longer reads. This is the same class of drift `tools/check_parity.py` cannot see (it compares route
*strings* only) and the same class the re-check of 2026-09-27 caught by hand when the phone's "open a
chat" phrase list had drifted from `jarvis_quick.py`'s. Everything is currently up to date — I ran
`--check` on six of them (pairing, open-chat, own-network, risky-approval, sayable, card-words) and
all six reported "up to date", so this is a missing *tripwire*, not a present break. That also means
the finding will look like nothing until the day it matters.

**Confidence:** Confirmed (the check list is exhaustive; the tools' `--check` modes exist and work).
**Severity:** Medium.
**Obvious or subtle:** obvious — one loop step, no product change.
**Fix:** add a CI step that runs `python tools/gen_<x>.py --check` for every generator whose output is
a file under `jarvis-client/app/src/test/resources/contract/`, and fails on a non-zero exit.

---

## C3. The event-name check covers the desktop only; the phone's SSE consumer is unchecked

**Where:** `tools/check_event_names.py:42-55`

Evidence — the tool's own statement of what it reads:

```
42: What it reads - all from THIS checkout:
44: jarvis-desktop/src-tauri/src/sse.rs           the wire grammar: ...
46: jarvis-desktop/src-tauri/src/stream.rs        `dispatch`'s own match ...
51: jarvis-desktop/src-tauri/src/hud_bootstrap.js the EventSource shim ...
54: jarvis-desktop/src/**                         the pages and modules that read them
```

There is no `jarvis-client` entry, and nothing else in `tools/` reads the phone's event kinds. The
phone's consumer is `JarvisRuntime.kt:1371-1576` (a `when (event.kind)` over
`approval, voices, deep, attention, activity, power, persona, finding, model, voice, hello,
proposal, memory_saved, schedule, ring_phone, lockdown, focus, screen_watch, live, appearance, sky,
step, wellbeing`), with `else -> Log.d(TAG, "unhandled event kind …")`.

**What happens:** an event the PC renames or stops sending, or a kind the phone reads that no
producer writes, fails silently on the phone — one `Log.d` line nobody reads. The repo already has
one of these in its history, documented in the same file: `JarvisRuntime.kt:1443` — *"This read
`activity_detail`, which no backend sends"* — a progress line that was dead until someone noticed.
I checked the four kind constants the phone defines outside that `when`
(`net/AutoLearn.kt:67 "memory_saved"`, `net/Schedule.kt:78 "schedule"`, `net/FindPhone.kt:36
"ring_phone"`, `net/ScreenRules.kt:42 "screen_watch"`) against the producers
(`jarvis_auto_learn.py:1881`, `jarvis_schedule.py:974`, `jarvis_find_phone.py:49`,
`jarvis_screen.py:187`) and all four match today — again, no present drift, no tripwire.

**Confidence:** Confirmed (the tool's read-list is explicit; the Kotlin kinds and the producers were
both read).
**Severity:** Low.
**Obvious or subtle:** subtle — extending the existing checker to Kotlin is a design choice.
**Fix:** teach `tools/check_event_names.py` to collect `event.kind` literals and `const val EVENT`
strings from `jarvis-client/app/src/main/java/**` and require each to appear in a producer or in an
explicit "handled without a producer" list, the way `SENT_BY_THE_BACKEND` already works for the
desktop.

---

## C4. The older app stores the bearer token and the HMAC signing secret in plain SharedPreferences

**Where:** `jarvis-android/app/src/main/java/com/jarvis/assistant/data/JarvisSettings.kt:53`

Evidence:

```kotlin
53:     var sharedSecret: String
54:         get() = prefs.getString(KEY_SECRET, "") ?: ""
55:         set(value) { prefs.edit { putString(KEY_SECRET, value) } … }
…
64:     var authToken: String
65:         get() = prefs.getString(KEY_TOKEN, "") ?: ""
66:         set(value) { prefs.edit { putString(KEY_TOKEN, value) } … }
```

backed by a plain private-preference file (`:19-20`) named at `:89-94`, with the class doc at `:14-15`
arguing the secret "is only meaningful to the paired desktop and never leaves the Tailnet".

**What happens:** this breaks non-negotiable rule 3 — a key "kept out of anything the app writes to
disk in plain text". Anyone with the unlocked device, a `run-as`/backup path, or a same-signature
update can read the token and the approval-signing secret straight out of `jarvis_settings.xml`.
Two mitigations, both stated plainly: the module cannot reach Jarvis at all (its one endpoint is not
wired into the backend, per the root `CLAUDE.md` and `jarvis-android/README.md`), and the module is
still compiled by CI — `.github/workflows/android-apk.yml:52` sets `PROJECT_DIR: jarvis-android` and
its path filters at `:27`/`:36` are `jarvis-android/**`, so an APK is still built on every change to
that folder (the workflow publishes nothing). This is *already recorded* in
`docs/FEATURE-REVIEW-2026-10-04.md:302`, together with the cleartext-to-`.local` point — I am not
claiming it as new, only confirming it is still true at `fa2b379f` and still built.

**Confidence:** Confirmed.
**Severity:** Medium (Low in practice for a module that cannot connect; the rating is for the rule).
**Obvious or subtle:** subtle — the owner's call is "fix the two keys, or move the module out of the
build", and `docs/` already recommends the second.
**Fix:** either delete the module and `android-apk.yml`, or point `sharedSecret`/`authToken` at a
Keystore-backed store the way `jarvis-client/app/src/main/java/com/jarvis/client/data/TokenStore.kt`
does, and drop the stale class comment at `JarvisSettings.kt:14-15`.

---

## C5. The older app's home-screen widget approves an irreversible decision in one tap, with no owner check

**Where:** `jarvis-android/app/src/main/java/com/jarvis/assistant/widget/approval/ApprovalActionCallback.kt:32`

Evidence:

```kotlin
// ApprovalActionCallback.kt:25-32
val id = parameters[PARAM_ID] ?: return
val approved = parameters[PARAM_DECISION] ?: return
JarvisRuntime.initialize(context)
JarvisRuntime.submitApprovalDecision(id, approved)
```

and the only gate inside that call is a pending/staleness check, not identity:

```kotlin
// JarvisApplication.kt:487-504
fun submitApprovalDecision(requestId: String, approved: Boolean) {
    val blocker = approvalBlocker(requestId)          // pending + link freshness only
    …
    val signature = ApprovalSigner.sign(secret = settings.sharedSecret, …)
```

**What happens:** a single tap on the home screen approves, with no screen lock, fingerprint or PIN
involved — the owner's rule of 2026-09-25, "no lock, no risky approval", is not implemented in this
module at all. The current app explicitly rejected this shape when it ported the widget:
`jarvis-client/app/src/main/java/com/jarvis/client/widget/ApprovalWidget.kt:45-60` says the port must
"only ever let Deny be a one-tap widget action" and that copying the old Approve button "would have
been a real regression against that rule". Same mitigation as C4: the module cannot reach Jarvis.
**Confidence:** Confirmed.
**Severity:** Low.
**Obvious or subtle:** subtle — fixed by C4's decision (delete the module, or port the current
widget's Deny-only rule into it).
**Fix:** if the module stays, make `PARAM_DECISION = true` open `MainActivity` instead of calling
`submitApprovalDecision`, exactly as `ApprovalWidget.kt:271-276` does.

---

## Checked and found clean (with the line that shows it)

Recorded so the Lead does not re-do this work. Each item was read, not assumed.

**The five non-negotiables, on the live app.**
- `X-Jarvis-Client: hud` on every request: one `authed()` builder adds it
  (`net/JarvisApi.kt:319-323`), and the two no-key pairing routes add it by hand
  (`net/JarvisApi.kt:648-653`). No `OkHttpClient` in the app bypasses those two paths, and every
  `execute()` sits inside `withContext(Dispatchers.IO)` (`net/JarvisApi.kt:3063`, `:2595`, and the
  40-odd route helpers).
- The pairing token: AES/GCM under a Keystore key, never plaintext (`data/TokenStore.kt:100-157`);
  a crash log redacts it three ways — the literal value, the `X-Jarvis-Token` header shape, and the
  per-device key's own shape (`platform/CrashLog.kt:72-80`).
- No auto-approve, no bulk approve: the widget offers Deny + "Review" only
  (`widget/ApprovalWidget.kt:252-276`); the notification offers Deny only, and would ignore an
  Approve if one arrived (`service/ApprovalNotifier.kt:301-329`); swipes route through the same
  `approve()` → `onApprove` → `approveItem()` path as the button
  (`ui/approval/ApprovalCard.kt:241-250`, `:298`, `MainActivity.kt:3031-3043`).
- Rule 4, staleness: `decisionBlocker` refuses on stale or dropped link (`JarvisRuntime.kt:3460-3479`),
  `actionBlocker` is applied at ~100 call sites in `JarvisRuntime.kt`, and the widget/notification
  paths refuse before they act (`widget/ApprovalWidget.kt:99-101`,
  `service/EventService.kt:243-303`).
- No client-side speech-to-text: `audio/Recorder.kt:23` and
  `assistant/JarvisRecognitionServiceStub.kt:15-25`; the on-device `TextToSpeech` path explicitly
  refuses cloud-backed voices rather than synthesising remotely (`audio/Speaker.kt:556-572`); the
  voice-print gate only proceeds on the PC's `TRANSCRIBED` outcome
  (`voice/VoiceSession.kt:1155-1181`), with `NOT_THE_OWNER`/`NO_ENGINE`/`REFUSED` returning before any
  text is used.
- Screenshots blocked: `SecurityRules.blockScreenCapture` (`data/Security.kt:324-330`) wired to
  `FLAG_SECURE` + `setRecentsScreenshotEnabled` (`MainActivity.kt:1014-1027`), including the
  token-shown, hand-off-picture and form-picture cases.
- Address allowlist: two independent readings of the host must both pass, one hand-split and one
  OkHttp-parsed (`data/OwnNetwork.kt:63-69`), then the phone narrows it further to
  `.ts.net`/`.nord`/localhost (`data/PhoneAddress.kt:81-104`); the result is applied at the single
  point every request and the event stream go through (`data/ClientSettings.kt:313-316`,
  `net/JarvisApi.kt:296-299`, `net/EventStream.kt:124-131`), the QR/typed-code path refuses anything
  that is not a mesh name (`net/Pairing.kt:178-185`), and redirects and the system proxy are both off
  (`net/JarvisApi.kt:231-244`).
- Per-device keys: the PC's proof and the four words are verified on the phone before anything is
  trusted (`net/Pairing.kt:400-414`), the key shape is checked before it is stored
  (`net/Pairing.kt:425-435`), and a failed handshake restores the old host and key in a
  `NonCancellable` `finally` (`MainActivity.kt:1901-1930`).
- Approval cards + screen lock: risky = outbound, irreversible, unclassified or rush-latched
  (`data/Security.kt:184-192`); "no lock, no risky approval" refuses rather than waves through
  (`data/Security.kt:220-230`); a loosening needs a fresh check and every loosening field is in one
  place (`data/Security.kt:337-346`, `MainActivity.kt:3439-3465`).

**Android platform traps.**
- Every `PendingIntent` carries `FLAG_IMMUTABLE` (all 25 sites; e.g. `service/EventService.kt:478`,
  `service/ApprovalNotifier.kt:390`).
- Notification ids are centralised with a test that fails on a clash
  (`service/NotificationIds.kt:1-61`); every channel is created in `JarvisApp.onCreate`
  (`JarvisApp.kt:35-138`) or in the service's own `onCreate` before its `startForeground`
  (`service/WakeWordService.kt:121-122`, `service/ScreenWatchService.kt:360`,
  `service/LiveService.kt:130` before `:132`).
- `android:exported` is set on all 22 components, and the exported ones carry either
  `BIND_*` permissions or a deliberate comment (`app/src/main/AndroidManifest.xml:137-509`).
- Foreground-service types match their permissions (`specialUse`, `microphone`,
  `mediaProjection` — `AndroidManifest.xml:76-435`), and the `mediaProjection` service goes
  foreground *before* `getMediaProjection`, which is what Android 14+ requires
  (`service/ScreenWatchService.kt:121-148`).
- No `AlarmManager` anywhere: the phone takes timers from the PC's events, so there is no
  exact-alarm permission trap. `SET_ALARM` is used only for `AlarmClock.ACTION_SET_ALARM`, as
  documented at `AndroidManifest.xml:41-46`.
- Every `registerReceiver` has a matching `unregisterReceiver` on every path
  (`platform/PowerWatch.kt:56-75`, `platform/NetworkWatch.kt:89-97`,
  `service/ScreenWatchService.kt:192`/`:333`).
- `MainActivity`'s exported actions that do real things (START/RESUME Live, the hand-off screen) need
  a per-install random proof checked in constant time (`InternalLaunch.kt:44-71`); the actions that
  need none only open a screen, and the voice ones are gated on the app lock
  (`MainActivity.kt:1555`, `:1615-1623`, `:1693-1701`).
- No `GlobalScope`, no `runBlocking`, no `Thread.sleep`, and no blocking work on the main thread in
  `src/main`. Of the 31 `while (true)` loops in main sources, the 24 in long-lived
  runtime/service/composable positions all carry a `delay`, an `await` (channel/pointer/frame), or an
  explicit input/`break` — `JarvisRuntime.kt:791`, `:816`, `:1102`, `:3726`, `:3839`, `:6394`,
  `:6747`, `:6877`; `MainActivity.kt:1058`, `:1200`, `:1246`, `:1418`; `ui/screens/HandoffScreen.kt:122`;
  `ui/screens/LiveScreen.kt:119`; `ui/screens/QuizPlate.kt:176`; `ui/screens/ReadinessScreen.kt:632`;
  `ui/screens/AppearanceScreen.kt:251`; `ui/screens/BrainScreen.kt:298`; `ui/parts/VoiceButton.kt:129`;
  `ui/parts/Parts.kt:322`; `ui/approval/ApprovalCard.kt:667`; `voice/SpeechAhead.kt:73`;
  `platform/PictureEncoder.kt:36`; `net/PairingFlow.kt:74`. The other seven terminate on a finite
  reader/buffer or a frame clock (`net/SseParser.kt:58`, `net/ChatSession.kt:888` — blocking reads
  inside `Dispatchers.IO` with `ensureActive()` on cancellation and EOF as the exit; `voice/SpeechText.kt:56`;
  `ui/theme/JarvisTheme.kt:403`; `face/FaceView.kt:312`, `:412`, `:571`).
- `!!` on a nullable: 29 sites, all guarded (regex groups, `takeIf` on the same expression, a
  `by lazy` that cannot change after the null check, or a `require` immediately above).
- No file, stream or cursor is left open: the only `File` write in the app is the crash log
  (`platform/CrashLog.kt:80`), the only `SharedPreferences` writes use `apply()` (no `commit()` in
  the module), and every `OkHttp` response uses `.use { }`.

**Contracts between the phone and the PC.**
- Route parity: `tools/check_parity.py` (reads both app trees; run in `ci.yml:230`).
- Approval rows: `backend/test_approval_contract.py` checks the phone's `Notice`/`Risk` field sets,
  the nine keys `PendingRows.kt` reads, and the 409 handling, against the real producers — run
  locally at `fa2b379f`: **67 passed, 0 failed**.
- Handshake/capabilities: `backend/test_connection_contract.py` lifts the phone's own
  `asCapabilityFlag` out of `ApiModels.kt` and checks `appearance`/`power`/`compute` against the real
  `jarvis_events.hello()`. The two capabilities it does *not* name — `pairing` and `temporary_chat`,
  the other two the phone gates on — I checked by hand and both are produced
  (`backend/rebuilt/jarvis_events.py:814`, `:839`).
- Hand-rolled POST bodies I read against their backend readers, all matching: `{"action","ask"}`
  (`net/AsksFirst.kt:287` ↔ `jarvis_asks_first.py:947-956`), `{"enabled":…}` (`AsksFirst.kt:306` ↔
  `jarvis_asks_first.py:2071`), `{"obscura":…}` (`net/BrowserEngine.kt:110` ↔
  `jarvis_browser_engine.py:324`), `{"sensitive":…}` (`net/Projects.kt:978` ↔
  `jarvis_projects.py:977`), `{"mode":"train","cancel":true}` (`net/VoiceStrict.kt:465` ↔
  `jarvis_voice_enroll.py:664`), `{"retired":true}` (`net/Devices.kt:206` ↔
  `jarvis_devices.py:851`), `{"missed":true}` (`net/Briefing.kt:78` ↔ `jarvis_briefing.py:1727`),
  `{"voice","speed","speaker","face"}` (`net/CustomVoices.kt:529-566` ↔ `jarvis_voices.py:3435`,
  `:1583`, `:680`, `:1120`).
- The crisis flag the phone reads is really produced: `wellbeing: "crisis"`
  (`net/Wellbeing.kt:33`) ↔ `backend/wellbeing.patch:23`.

## Limits of this pass

- No build, no test run of the Kotlin suite (no Android SDK). Everything above is read from source;
  the one Python suite I ran is named with its result (**67 passed, 0 failed**).
- Compose recomposition behaviour (`remember` keys, `LaunchedEffect` keying) was checked by reading
  call sites, not by running the UI. I found no `remember` holding a value that changes without that
  value in its key list — the ones carrying mutable inputs are keyed on them, e.g.
  `ui/approval/ApprovalCard.kt:193` (`remember(item.id, expiry)`), `:217`, `:223`, and
  `MainActivity.kt:1384` (`remember(faceId)`).
- The older app's `ApprovalSigner`/`CleartextTargetTest` were skimmed only; C4/C5 rest on the
  settings and callback files quoted above.
- `face/**` (drawing and shaders), `ui/theme/**` and the golden-fixture tests were not audited
  beyond confirming their generators *are* covered by CI (`ci.yml:240-283`).
