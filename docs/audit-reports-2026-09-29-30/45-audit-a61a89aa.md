# Report 45 (audit), agent a61a89aa, 2026-09-30T07:09Z

> **What it was asked** (first 600 characters of the task): Read-only audit of /home/user/Epic-Jarvis's ANDROID background services (jarvis-client/app/src/main/java/com/jarvis/client/service/, receivers, boot, workers, plus AndroidManifest.xml; read CLAUDE.md first; verify each claim with file:line + quote; 'not checked' honestly; do not run Android; change no files). Services/parts: EventService (link, SSE/stream), WakeWordService, WakeResumeNotifier + boot receiver, ScreenWatchService (MediaProjection capture), AvatarOverlayService (SYSTEM_ALERT_WINDOW), LiveService, PhoneNotificationListenerService, Handoff (captcha 'Solve it here' live picture), qu

> This is a sub-agent's own report, saved word for word. It is model output: it was
> checked only as far as the report itself says. Line numbers were read, not run.

---

Android background-services audit. Read only, nothing built or run, no files changed. All quotes are from jarvis-client/app/src/main/java/com/jarvis/client/ (short paths below). "Not checked" is stated where it applies.

**Clean (checked)**
- No WorkManager, AlarmManager, GlobalScope, FCM or Firebase anywhere. I grepped the Kotlin sources and the manifest.
- The only network paths are the paired-PC address and the notification-listener check; nothing public turned up (rule 2).
- Boot: BootReceiver.kt:35 returns unless the phone is paired, then starts EventService only. The mic and screen services are never started at boot.
- Every foreground service calls startForeground first, inside a try/catch, and every failure path ends in stopSelf. The manifest declares FOREGROUND_SERVICE_MICROPHONE, FOREGROUND_SERVICE_MEDIA_PROJECTION and FOREGROUND_SERVICE_SPECIAL_USE.
- MediaProjection: ScreenWatchService.kt:110-115 starts the foreground service before `getMediaProjection`, and the token is used once. `end()` (:295-320) releases the ImageReader, VirtualDisplay, projection, thread and receiver.
- Solve it here (Handoff): the backend takes a screenshot of one page only (`backend/jarvis_handoff.py:476` `page.screenshot`; input only via `page.mouse/keyboard`, :532-538). The phone holds the picture in memory only (HandoffScreen.kt:152 `picture = null`), and its screenshots are blocked. Input is held on a stale link (JarvisRuntime.kt `handoffInput`). Not checked: whether taps are refused after the page stops being paused; that logic is in the backend.
- Phone notification listener: allow-list first, then the SMS check, then redaction, and the store is encrypted with a cap. Stored on the IO dispatcher.
- The avatar overlay is a static launcher icon, not the shader face, so it costs almost no memory or GPU. Overlay touches are `NOT_FOCUSABLE | NOT_TOUCH_MODAL` (AvatarOverlayService.kt:199); a tap only opens the app.

**Findings, worst first**

1. **Phone Watch does not stop on link loss.** The only ways it ends are Stop, 30 minutes, screen-off, Android ending the share, the setting being turned off, and Stop everything (ScreenWatchService.kt:86-93, :139-146, :200-203). `ScreenWatch.requestStop` is called from only two places: `stopEverything` (JarvisRuntime.kt:3521) and the Home button. Nothing ends Watch when the link goes stale or drops, so capture and the sign stay on for up to 30 minutes with no PC to send to. It is not a leak, because a picture is only sent per question. The decision said Watch should stop on link loss; I found no phone unpair path to test (only `removeDevice`, JarvisRuntime.kt:4006). Smallest fix: in ScreenWatchService, collect `JarvisRuntime.link` and `stale` and call `end("link lost")` after N seconds down.

2. **The password-box limit is not stated where Watch starts.** `ScreenWatch.HOW` (net/ScreenWatch.kt:64-69) says one picture, sent only to the PC, nothing kept. It never says Watch cannot pause on password fields. The only protections are:
   - the never-look-at list and the bank/password-manager package check (`ScreenNever.blocked`), and
   - a "looks black" test at ≥99.5% dark (`BLACK_SHARE`, :50), which catches whole-window FLAG_SECURE apps only.

   A password box in a normal app, or a partly secure window, goes through as a picture. The PC blacks out text-shaped secrets, but its own note says dots behind a show-password eye have no pattern to catch. Fix: add one sentence to `HOW` and to `NOTIFICATION_TEXT` saying it cannot see password boxes, so close those pages first.

3. **The approval widget ignores App lock.** widget/ApprovalWidget.kt:192-217 draws the card headline and body, and a one-tap Deny, with no check of `appLock` or `privateLists`. widget/JarvisBoardWidget.kt:95 does hide words under those settings, and the widget's own comment says "the home screen is as public as a lock screen". This clashes with the 2026-09-28 rule that widget buttons open the locked app first. Not checked: on-device behaviour. Owner decision:
   - (a) Hide the words and route Deny through the locked app when App lock is on (recommended);
   - (b) leave Deny as is (it is the safe direction) but hide the words;
   - (c) leave it.

4. **The link tile mutes and unmutes with no unlock.** LinkTileService.kt:78-90 calls `setMuted(!muted)` and never checks App lock or `isLocked`. QuickTileService does check them. From a locked phone, whoever holds it can unmute Jarvis. Fix: reuse `QuickTiles.decide`, or add an `unlockAndRun` when App lock is on.

5. **Concurrency risks in JarvisRuntime (6992 lines).**
   - (a) `streamJob`, `watchdog`, `restartJob`, `faceJob` (JarvisRuntime.kt:607-614) are plain `var`s on `Dispatchers.Default` (:244), a multi-threaded pool. `startStream` (:986) does check-then-set with no lock. It is called from Main (EventService, network change at :1203), from the restartJob coroutine on Default (:1010), and from the UI. Two concurrent calls can open two streams.
   - (b) `ScreenWatchService.end()` (:295-297) does `if (ended) return; ended = true` on a `@Volatile`, which is not atomic. It can be hit from Main (the projection callback, timers) and from the Default-thread `stopHook` via `stopEverything`. Worst case is a double release, and the `runCatching` blocks make that harmless.
   - (c) `WakeWordService.goForeground` (:773-845) rebuilds the notification and, in Bubble mode, republishes the shortcut. It runs on every recorder reopen and every wake detection, inside the audio loop. That is notification churn, not a crash.
   - (d) `EventService.startInForeground`'s failure path (:489-513) cancels `watcher` before `onCreate` assigns it (:56-64), so the cancel is a no-op there. The collector's next emission cancels it, so the effect is benign.
   - (e) `EventService.start` (:428-433) logs a failed start but does not set `lastStartFailure`, so a refused boot or update start is silent on the readiness screen. Only a failure inside `startInForeground` sets it.

6. **Battery and doze.** There is no wake lock anywhere (grep: none). The wake-word loop is continuous ONNX inference under a mic foreground service. Not checked: whether the CPU keeps running with the screen off in deep doze; that needs a device. The battery exemption is declared in the manifest and requested from the readiness screen, with FAQ wording at FaqScreen.kt:227. The stream reconnect after a network change is debounced (`reconnectForNetworkChange`, :1200), so I found no reconnect storm. I did not read the OkHttp/EventStream backoff itself.

7. **Minor.**
   - `AvatarOverlayService.addAvatarView` (:208-211) sets `avatarView` even when `addView` fails, so `removeView` later just logs.
   - `LiveService` calls `rec?.release()` (:291) outside `runCatching`.
   - Unverified doc claim: BootReceiver's comment at :17-19 treats BOOT_COMPLETED as a foreground-service exemption. I did not verify that MY_PACKAGE_REPLACED is exempt on Android 12-14 (not checked). The `runCatching` around the start hides a refusal.
   - No `filterTouchesWhenObscured` anywhere. It does not matter for the overlay, since the overlay cannot approve anything. Approvals happen in MainActivity, which I did not audit for tapjacking (not checked).
   - `onTaskRemoved`, `onTrimMemory` and `onLowMemory` are not implemented anywhere (grep). The services are START_NOT_STICKY (EventService is START_STICKY) and rely on `onDestroy`. If the process is killed, Android reclaims the mic, projection and windows, so I found no leak.

**Owner decisions (short)**
- Link loss: should Watch end itself after 10 seconds of a down or stale link? (a) Yes (recommended); (b) leave it.
- Password limit: (a) add the sentence to the start screen and the notification (recommended); (b) also block Watch when any app has a password field on screen. That needs an accessibility service, which is bigger.
- Widget and tile under App lock: see findings 3 and 4. The recommendation is to apply App lock to both.
