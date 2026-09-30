# Report 02 (audit), agent a759e1f1, 2026-09-29T08:19Z

> **What it was asked** (first 600 characters of the task): Repo /home/user/Epic-Jarvis at origin/main (79a36545). Do NOT edit files. There is NO local Android build here (CLAUDE.md 'How the Android apps get built'), so read Kotlin carefully by eye; CI is the compiler. Bug-hunt the NEWEST jarvis-client/ Kotlin (Jetpack Compose): QR-pairing (CameraX + ZXing core: camera permission flow, lifecycle/leaks, scan callback firing twice, camera left open, key storage - Keystore/EncryptedSharedPreferences? never in plain prefs or logs), per-device key handling and Remove, PhoneNotificationListenerService + NotificationRedactor + allow-list + CapturedNotificatio

> This is a sub-agent's own report, saved word for word. It is model output: it was
> checked only as far as the report itself says. Line numbers were read, not run.

---

Bug hunt: newest jarvis-client Kotlin (read only, nothing compiled, nothing run)

I found 5 real but modest bugs and nothing serious. No safety-rule break (approvals, key storage, token logging, header, allow-list) turned up. All of it is read by eye. There is no Android build here, and I ran no tests, so CI is the only compiler. Findings are ordered worst first, and all are low to low-medium.

## Proven bugs

**1. Captured notifications: lost rows, and rows that survive the "off" switch. Low-medium (data integrity plus privacy).**
- Evidence:
  - `data/CapturedNotifications.kt` `add()` does `save(CapturedRows.added(load(), n, ...))`, a read-modify-write on SharedPreferences with no lock.
  - `clear()` is a plain `remove(KEY_ITEMS)`.
  - `JarvisRuntime.kt:3635-3644` `storeIfPhoneNotificationsStillOn` does `scope.launch { ... if (phoneNotificationsAllowed()) withContext(Dispatchers.IO) { store() } }`. The scope is `Dispatchers.Default` (line 243), so one coroutine starts per notification and runs in parallel.
  - The switch-off clear at `JarvisRuntime.kt:827-828` also runs on that scope.
- Trigger A: two allowed-app notifications arrive together (a chat burst). Both threads `load()` the same list, and the second `save()` overwrites the first. One notification is silently lost.
- Trigger B: the owner turns the switch off (or the PC does) just after a coroutine passed the `phoneNotificationsAllowed()` check. The `clear()` runs first, then the pending `store()` writes a row back.
  - That row stays on disk. Nothing clears again until the switch changes once more, and the 7-day trim only runs on a later `add`.
  - This breaks "turning it off is immediate, nothing captured stays behind".
- Fix: make `add` and `clear` `@Synchronized` (or run them on one single-thread dispatcher). Re-check the switch inside that lock, immediately before the write.

**2. The models cache is not tied to a PC. Low, a wrong answer shown.**
- Evidence:
  - `data/ModelsCacheStore.kt` uses one key, `"models"`, and stores no host.
  - `JarvisRuntime.kt:1503-1512` `refreshModels` writes it on every success.
  - `grep` shows nothing clears or keys it (`modelsCacheStore` appears only at lines 373, 717, 722 and 1510).
- Trigger: pair the phone with PC A, open Brain -> Model, then re-pair to PC B (the pairing-branch code in MainActivity, ~1500-1600, never clears it) or get a different key. If B is unreachable, or is an older backend, Brain -> Model shows A's installed models and current/previous refs as if they were B's, with A's "as of" time. The Use/Install/Roll back buttons stay visible but dimmed.
- Fix: store the host with the cache and only replay it when it matches `settings.host`. Or clear it in `setHost` when the host changes.

**3. A duplicate watchdog loop can start. Low.**
- Evidence: `JarvisRuntime.kt:921-1008` `startStream`.
  - The only `watchdog?.cancel()` calls are in the forced-restart branch (line 934) and `stopStream` (line 1160).
  - The normal path, reached when `streamJob` is no longer active, ends with `watchdog = scope.launch { while (true) ... }` and no cancel of the old one.
- Trigger: the stream collector dies from an exception thrown inside `onOpen` or `onEvent` (for example `refreshAll` throwing). The runtime scope only logs it. The next `startStream()` (from onResume or a network change) then leaves two watchdogs running. Both call `refreshPending()` and toggle `_stale`, so the reads double and the stale flag can flap.
- Fix: put `watchdog?.cancel()` before `watchdog = scope.launch`.

**4. An event dropped on a full buffer can never be replayed. Low.**
- Evidence: `net/EventStream.kt`, in the frame callback, `if (trySend(Signal.Event(event)).isSuccess) { resumeFrom = id; onResumePoint(id) }`. The flow is a `callbackFlow` with the default 64-slot buffer.
- Trigger: a long replay after being offline. Each `approval` event costs the collector several HTTP round trips (`JarvisRuntime.kt:1257-1300`), so the buffer fills and events are dropped.
  - The next event that does fit advances `resumeFrom` past the dropped one, so the dropped event is unrecoverable.
  - An `approval` event lost this way means no re-read of the queue and no notification for it. That card only appears at the next approval event or reconnect.
- The code comment shows the author knew about drops but only protected against advancing the id past the dropped frame itself.
- Fix: on a failed `trySend`, force a full refresh after draining (or use a larger or unlimited buffer for events). Keeping `Alive` as droppable is fine.

**5. Blocking work on the main thread in the notification allow-list screen. Low, jank or ANR risk on a phone with many apps.**
- `ui/screens/PhoneNotificationsPlate.kt`: `val candidates = remember(version) { store.installedApps() }` runs during composition. It calls `getInstalledApplications(GET_META_DATA)` and `getApplicationLabel()` for every app, and does the label lookups (an I/O-bound resource load) on the main thread.
- The `Add` onClick calls `store.add()`, which calls `Telephony.Sms.getDefaultSmsPackage` and `PackageManager` on the main thread.
- Fix: load the candidate list in `produceState` on `Dispatchers.IO`, and run `add` on IO.

## Checked, no bug found

- **QR pairing** (`ui/screens/QrScanScreen.kt`, `PairByCode.kt`, `net/Pairing.kt`, `PairingFlow.kt`)
  - Camera use: the permission is requested only after the explain step. The camera unbinds in `onDispose`. The analyzer closes each frame. A `disposed` flag stops late callbacks. Repeated scan callbacks are harmless because the step changes and the composable is removed.
  - The QR parse is strict: six parts, host must end in `.ts.net` or `.nord`, port range checked. The claim goes only to the QR host with no token. The key lives in memory only and `takeKey()` hands it over once.
  - FLAG_SECURE turns on while the code, camera or words are shown.
- **Key storage** (`data/TokenStore.kt`): an AES-GCM Keystore key, not plain prefs. The log lines never include the token. `CrashLog` scrubs it, and `headerSafe` logs lengths only.
- **X-Jarvis-Client header:** it is set in `authed()` and in `pairPost`. I did not enumerate every other OkHttp request builder; the update-check path is intentionally exempt (`net/UpdateCheck.kt`).
- **Cleartext rules:** the `network_security_config.xml` list and `PhoneAddress` agree.
- **Notification listener** (`service/PhoneNotificationListenerService.kt`, `NotificationRedactor.kt`, `NotificationAllowList*.kt`)
  - The gate order is right: switch, then SMS, then allow list, then redact, then store.
  - The manifest declaration is correct (`BIND_NOTIFICATION_LISTENER_SERVICE`).
  - Redaction gaps are exactly the ones the class doc and `NotificationRedactorTest` already list: codes of 9 digits or more, non-digit codes, no trigger word inside a sentence.
  - The banking check runs only when an app is added, not at capture. That is a design choice and I did not count it as a bug.
- **Widgets:** `JarvisBoardWidget` hides words under App lock or Hide-lists and redraws when `security` changes. Under App lock its buttons only open the app. `ApprovalWidget` offers only Deny directly and its Review button opens the app. It shows the notice text (title and body), not the raw title or summary, which the code says is safe for a home screen.
- **FLAG_SECURE** (`MainActivity.kt:794-815`): set and cleared correctly.
- **Approvals**
  - `decide()` and `decisionBlocker()` refuse on a stale or dropped link.
  - Swipe is gated by `swipeAllowed`. `ApprovalCard` is used in only one place, `HomeScreen.kt:1213`, which passes the setting.
  - Approve goes through `approveItem`, then biometric or signature, then `decideDetached`.
  - Deny is never gated, by design.
- **Removing this phone's device key** (`net/Devices.kt`, `DevicesPlate.kt`): the handling is consistent.
- **Null and JSON safety:** there are no `!!` anywhere in the source. Parse sites use `as?` and `runCatching`.
- **Removed APIs:** minSdk is 33, so the newer APIs used (`getParcelableExtra` with a class, `availableCommunicationDevices`) are fine.
- **Tests:** I read `NotificationRedactorTest`, `NotificationsStayLocalTest` and the store tests. They assert what the code does. I did not find one asserting the wrong thing.

## Not covered
- Screen "Look at this" and "Watch with me" do not exist in the phone code. The only match for those terms was in `net/VoiceModels.kt` and `voice/StrictVoice.kt`, so there was nothing to audit.
- The `LiveService` audio loop I read only partly. I saw no lifecycle leak, but I did not trace `voice/*`.
- I did not examine the Goals plate beyond confirming it parses safely.

The main file paths are under `/home/user/Epic-Jarvis/jarvis-client/app/src/main/java/com/jarvis/client/`:
- `data/CapturedNotifications.kt`
- `data/ModelsCacheStore.kt`
- `net/EventStream.kt`
- `JarvisRuntime.kt`
- `ui/screens/PhoneNotificationsPlate.kt`
