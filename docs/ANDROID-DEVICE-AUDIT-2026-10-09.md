# Android **device** audit — 2026-10-09

**Run on a real phone.** OnePlus **CPH2419** (the device reports no marketing name —
`ro.product.marketname` is empty; device `OP5552L1`, build
`CPH2419_15.0.0.1700(EX01)`), **Android 15 / API 35**, `arm64-v8a`, 1080x2412 @ 480 dpi,
120 Hz panel, serial `f0a5b32b`, attached over USB with debugging authorised.
`adb reverse tcp:4719 tcp:4719` was in place.

**Nothing was paired and no approval was given.** No pairing token was read, written,
printed or entered; no approval card was approved; no credential of any kind was typed.

- The APK was built **from this branch's base (`origin/main`, `2f925c11`)** in an
  isolated worktree, not reused from another worktree: `assembleDebug`,
  BUILD SUCCESSFUL, SHA-256
  `FAEEB07584B457EE3EB2330380227042046DCDCDD49211A94AE71698094FD294`.
- Installed **clean** (`adb install -r -t`): `com.jarvis.client` **0.2.0**, versionCode 1,
  minSdk 33, targetSdk 36, `firstInstallTime` = `lastUpdateTime` = 2026-10-09 13:25:49.

---

## 0. Read this first: the tour this audit was for did not happen

**The screen-by-screen tour — deliberately the centre of this job — could not be run,
and this report does not pretend otherwise.**

The phone was **locked behind a secure keyguard for the entire run**:

- `dumpsys window policy` → `secure=true`, `deviceHasKeyguard=true`
- `dumpsys trust` → user 0: `deviceLocked=1`, `strongAuthRequired=0x0`
- `dumpsys window displays` → `mCurrentFocus=Window{… NotificationShade}`; the
  Jarvis window is `isVisible=false`.
- `logcat`: `E ViewRootImpl: SkipDraw reason : screen_off … mViewVisibility=0x8`.

**Nothing in the app has ever been drawn on this device.** `wm dismiss-keyguard` is a
no-op against a secure keyguard; there is no `am` option to show an activity over the
lock screen; and I deliberately did **not** run `locksettings set-disabled true` or
anything else that would disable the owner's screen lock — that is a security gate on
his phone and not mine to open. I could also not reach a human: this session's
`ask_user_question` is disabled while it is owned by a live parent agent, so the parent
was asked to relay the request instead (`unlock-watch.txt` shows a 15-minute watch for
an unlock; the phone stayed locked throughout).

**What a locked phone could still answer is below. That is all it is.**
Treat the app as **unverified on a device**.

---

## 1. Screen-by-screen table

All **16** screens in `ui/Nav.kt`'s `Screen` enum (`ui/Nav.kt:82-106`), plus the pairing
screen and the crash screen — 18 rows. "Reached" means a screenshot and a
`uiautomator dump` were taken of that screen rendering.

| # | Screen (`ui/Nav.kt`) | File | Reached? | Renders | Controls respond | Crash / error |
|---|---|---|---|---|---|---|
| — | Pairing (the unpaired takeover) | `PairingScreen.kt` | **No** | not observed | not observed | none seen |
| 1 | `HOME` | `HomeScreen.kt` | **No** | not observed | not observed | none seen |
| 2 | `BRAIN` | `BrainScreen.kt` | **No** | not observed | not observed | none seen |
| 3 | `INBOX` | `InboxScreen.kt` | **No** | not observed | not observed | none seen |
| 4 | `CHECKS` | `ReadinessScreen.kt` | **No** | not observed | not observed | none seen |
| 5 | `APPEARANCE` | `AppearanceScreen.kt` | **No** | not observed | not observed | none seen |
| 6 | `FAQ` | `FaqScreen.kt` | **No** | not observed | not observed | none seen |
| 7 | `VOICE` | `VoiceTrainingScreen.kt` | **No** | not observed | not observed | none seen |
| 8 | `SECURITY` | `SecurityScreen.kt` | **No** | not observed | not observed | none seen |
| 9 | `VOICE_CHECK` | `VoiceCheckScreen.kt` | **No** | not observed | not observed | none seen |
| 10 | `VOICES` | `VoicesScreen.kt` | **No** | not observed | not observed | none seen |
| 11 | `HISTORY` | `HistoryScreen.kt` | **No** | not observed | not observed | none seen |
| 12 | `SETTINGS` | `SettingsScreen.kt` | **No** | not observed | not observed | none seen |
| 13 | `LIVE` | `LiveScreen.kt` | **No** | not observed | not observed | none seen |
| 14 | `HANDOFF` | `HandoffScreen.kt` | **No** | not observed | not observed | none seen |
| 15 | `APPROVALS` | `ApprovalsScreen.kt` | **No** | not observed | not observed | none seen |
| 16 | `FEATURES` | `FeaturesScreen.kt` | **No** | not observed | not observed | none seen |
| 17 | (crash screen, not a `Screen` value) | `CrashScreen.kt` | **No** | not observed | not observed | not triggered |

**Rows reached: 0 of 18.** Of those, **0 of 16 `Screen` enum values**.
**Controls tapped and observed to respond: 0.**
Any table claiming more would be invented.

---

## 2. What the device *did* show, with evidence

Every line below is a command output, a log line, or a file in this scratch space
(`.dsh-scratch/device-audit/audit-evidence/`, **not committed**).

### 2.1 It installs and starts on a real Android 15 phone, with no crash

| Observation | Evidence |
|---|---|
| Clean install succeeds | `adb install -r` → `Success`; `permissions-dumpsys.txt` (`firstInstallTime` = `lastUpdateTime`, so no prior install) |
| First launch starts the process and does not crash | `ps -A` → `com.jarvis.client` pid 23355 alive at the end of the run; **no `FATAL EXCEPTION` anywhere in `logcat-full.txt`** |
| No app service runs while unpaired | `services.txt` → `ACTIVITY MANAGER SERVICES … (nothing)`. Consistent with "no always-on listening before pairing" |
| The advertised entry points deliver without a crash | `am start -a android.intent.action.SEND -t text/plain` → `MainActivity`; the same to the `.ShareToLive` alias; `-a android.intent.action.ASSIST`. All three: *"intent has been delivered to currently running top-most instance"*, pid unchanged 23355, no fatal |

The OS-only noise in `logcat-full.txt` from pid 23355 (`OplusAppHeapManager`,
`callGcSupression: NullPointerException`, `SchedAssist`, `FeatureFlagsImplExport`) is
OnePlus system-extensions probing its own hooks — **not** app exceptions. Said plainly
because a careless grep of that log looks alarming.

### 2.2 `POST_NOTIFICATIONS` — the answer, on a clean install

`dumpsys package com.jarvis.client` (full text in `permissions-dumpsys.txt`):

```
android.permission.POST_NOTIFICATIONS: granted=false, flags=[ USER_SENSITIVE_WHEN_GRANTED|USER_SENSITIVE_WHEN_DENIED]
android.permission.CAMERA:            granted=false
android.permission.RECORD_AUDIO:      granted=false
```

**Not granted.** That is the honest state of a fresh phone, and it matches the design:
`MainActivity.kt:1578-1583`

```kotlin
LaunchedEffect(paired) {
    if (!paired || askedForNotifications) return@LaunchedEffect
    if (PlatformReadiness.notificationsGranted(this@MainActivity)) return@LaunchedEffect
    askedForNotifications = true
    notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
}
```

so before pairing the app **never asks**, and after this run the phone had posted
nothing from Jarvis (the lock screen's shade showed only Android System and System UI
notifications — `screens/05-density-reset.png`). This settles the second audit's
Part 4 item 1 for the *unpaired* case only: on a clean install the permission really is
absent, and **the app says nothing about it before pairing** because it has nothing to
announce yet. Whether "Send test" now tells the truth (the first audit's finding 1) is
**still not tested** — that needs the Checks screen rendered.

### 2.3 The backend link, reachable and unreachable

From the phone's own shell, through the USB reverse:

| State | Command | Result |
|---|---|---|
| Reachable | `adb reverse --list` → `UsbFfs tcp:4719 tcp:4719`; `curl -s -m 6 -o /dev/null -w 'code=%{http_code} time=%{time_total}' http://127.0.0.1:4719/api/version` | **`code=403 time=0.006630`** |
| Unreachable | `adb reverse --remove tcp:4719`, same curl | **`code=000`**, no body |
| Restored | `adb reverse tcp:4719 tcp:4719`, same curl | **`code=403`** |

So the transport is live and answers in **6.6 ms**, and the 403 is the backend refusing
an **unauthenticated** request — correct, and the only answer I was willing to get
without a token. This is the *link*, not the app: the app's own behaviour when the link
drops (the stale-event gate, the 70-second keepalive watchdog) is **untested**.

### 2.4 Screenshots are **not** blocked at default settings

`dumpsys window windows` for the MainActivity window (`window-flags.txt`):

```
fl=LAYOUT_IN_SCREEN LAYOUT_INSET_DECOR SPLIT_TOUCH HARDWARE_ACCELERATED DRAWS_SYSTEM_BAR_BACKGROUNDS
```

**No `SECURE` in that list** — i.e. `FLAG_SECURE` is not set on a clean install, which
is the correct default (App lock off, "Hide memory lists and chat history" off). So
`adb shell screencap` is *not* refused on this phone: every capture in `screens/` is a
real frame.

Two traps for whoever reads this next, stated so they are not misread:

- `DisplayDeviceInfo{… FLAG_SECURE …}` and `mBaseDisplayInfo{… FLAG_SECURE …}` in
  `dumpsys display` are the **display's** own capability flag (it can carry protected
  buffers). They say nothing about the app blocking screenshots.
- Because `screencap` demonstrably works here, a later run that *does* want to test
  App lock / "Hide memory lists" can attribute a black or refused capture to the app.
  That test was **not** run: flipping either switch needs the Security screen rendered.

### 2.5 Bubbles are switched off on this phone

```
adb shell settings get secure notification_bubbles   →  0
adb shell dumpsys notification_manager | grep -i bubble  →  (nothing)
```

`0` is Android's *"bubbles off"*, set system-wide. **So on this handset a Floating
Jarvis bubble would not appear even if the app's Bubble mode were on** — and this is on
top of the already-known unfixed blocker (`NotificationCompat.MessagingStyle`,
`service/WakeWordService.kt:636-639`). Honest caveat: `0` can also be the OEM default
rather than a deliberate choice, and I could not open Settings → Notifications to see
which; either way the value the OS will act on today is `0`.

### 2.6 Density: the OS honours the override and the app survives it

`screens/04-density-420.png`, `screens/05-density-reset.png`.

| Step | Evidence |
|---|---|
| Baseline | `wm density` → `Physical density: 480` |
| `wm density 420` | `wm density` → `Physical density: 480` / `Override density: 420`; app pid **still 23355** |
| `wm density reset` | `wm density` → `Physical density: 480` (override gone); pid **still 23355** |

So **the running app process survived a live 480→420→480 configuration change with no
crash and no process restart.** That is the whole of what this can prove: with no
rendered UI it says nothing about whether any screen lays out correctly at 420 dpi, and
**that is the part the audit was asked about.** Density was reset; the phone is back at
480.

### 2.7 Dark mode is currently ON (read, not changed)

```
adb shell cmd uimode night   →  Night mode: yes
adb shell settings get secure ui_night_mode  →  2
```

Recorded as the device's state at audit time. **Not exercised against the app** — no
pixels, so "how the app behaves in dark mode" is unanswered. I did not toggle it: with
nothing rendering, a toggle plus a reset would have been a device change that proved
nothing.

### 2.8 Device facts worth having on record

`CPH2419`, Android 15 (API 35), `arm64-v8a`, 1080x2412, **480 dpi**, cutout top-centre
(`Rect(0, 107 - 0, 0)`), rounded corners r=60, panel modes 60/90/**120 Hz**
(`renderFrameRate 120.00001`), HDR types 2/3/4, no SIM ("Emergency calls only"),
battery 78%. Full text: `logs/getprop.txt`, `logs/window-policy.txt`.

---

## 3. Device-only items from the previous audit's list

| # | Question (2nd audit, Part 4) | Answered? |
|---|---|---|
| 1 | Is `POST_NOTIFICATIONS` granted, and does "Send test" tell the truth? | **Half.** Granted = **false** on a clean install, and the app correctly does not ask before pairing (2.2). The "Send test" message needs the Checks screen → **not tested** |
| 2 | Does `/api/watch/report` fail on this PC? | **No.** Needs the Watches screen paired → not tested |
| 3 | Does App lock really block screenshots and the recents thumbnail? | **No.** `FLAG_SECURE` is absent at defaults, and `screencap` works (2.4). The locked case was not reachable |
| 4 | Does a Floating Jarvis bubble appear on Android 11+? | **No — and it would not here anyway:** `notification_bubbles=0` system-wide on this phone (2.5). The project's own `MessagingStyle` blocker still stands |
| 5 | SSE reconnection and the stale-link gate on a half-open socket | **No.** Not paired, and no UI |
| 6 | Live audio, the 2-second voice check, the headset button, hand-off frames | **No.** `RECORD_AUDIO` is `granted=false` and Live is behind pairing |
| 7 | TalkBack ordering and announcements | **No.** TalkBack itself was not enabled and nothing rendered |
| 8 | Is the "Never look at" app picker visibly slow (finding 7)? | **No.** Behind pairing |
| 9 | Which menus are hidden for the owner? | **No.** Menu visibility comes from the PC, which needs pairing |
| — | Density and dark mode | **Partly.** The OS honours `wm density` and the app survived the change (2.6); dark mode is ON (2.7). **No layout was observed at either** |
| — | Backend unreachable vs reachable | **Yes, at the link level** (2.3). The app's behaviour on a dropped link is untested |

---

## 4. What stops at "pair first"

With no pairing there is no way to know this by tapping, so this is read from the one
place that decides it — `MainActivity.kt:1845-1848`:

```kotlin
if ((!paired || repairing) &&
    nav.current != Screen.CHECKS && nav.current != Screen.FAQ &&
    nav.current != Screen.SECURITY && nav.current != Screen.SETTINGS
) { PairingScreen(...); return@JarvisTheme }
```

**Exactly 4 of the 16 screens survive the pairing takeover: `CHECKS`, `FAQ`,
`SECURITY`, `SETTINGS`.** Every other screen — **12 of the 16** — is replaced by the
pairing screen until the owner approves a card on the PC. Inside those four, the
paired-only links are absent rather than dead: `SettingsScreen` draws its rows through
`menus.shows(...)`, which is server-driven, so unpaired it renders essentially only the
jump list, Security, "Show or hide menus" and "What asks first", and its voice and
Appearance links are `null` until paired.

So **everything that is Jarvis — Home, the approvals queue, Brain and memory, Inbox,
History, Live, the hand-off, Everything Jarvis can do — is behind pairing, 12 screens
and every plate inside them.** That list is the only part of this audit that is
complete, and it is complete by reading, not by tapping.

---

## 5. Could not determine

In rough order of how much it costs the reader:

1. **Whether any screen renders at all.** No screen was ever drawn.
2. **Whether any control responds** — every button, switch, tile, dialog and swipe.
3. **Whether anything crashes in normal use.** Only the launch, the three intent
   deliveries and a density change were exercised.
4. All 9 previous items in §3 except the bubble value.
5. **The `POST_NOTIFICATIONS` request dialog** — never shown, because it waits for
   pairing.
6. **Whether `FLAG_SECURE` is applied when App lock or "Hide memory lists" is on**, and
   whether the recents thumbnail blanked.
7. **Layout at 420 dpi or in dark mode.**
8. **The stale-event gate under a dropped link** — the link was dropped at the *shell*
   level (§2.3), never while the app was watching it.
9. Whether the app's own frame-rate preference (`platform/DisplayRate.kt`) takes effect
   on a 120 Hz panel.

---

## 6. Risk

- **The app is unverified on a device.** This run adds install-and-start facts, one
  permission state, one system setting and one configuration-change survival test. It
  does **not** reduce the risk the audit was commissioned to reduce: that a screen,
  a control or a crash only a phone can reveal is still out there. The two prior audits
  each list 8 and 4 open findings respectively and **none of them is confirmed or
  cleared here.**
- **The one device finding with teeth is §2.5:** bubbles are off system-wide on this
  phone, so "Floating Jarvis: Bubble" cannot work here as things stand, on top of the
  unfixed `MessagingStyle` blocker. Do not promise the bubble to the owner without
  fixing both.
- **A clean install is a real state worth noting:** until the owner pairs and then
  grants notifications, **every** reminder and approval notification is silently
  dropped (`granted=false`, §2.2). That is by design, but the owner should be told that
  a fresh phone announces nothing until he pairs and answers the prompt.
- **The blocker is cheap to fix and worth a re-run.** The phone needs one fingerprint
  touch and to be left awake. Everything in this report that is marked "not observed"
  becomes possible the moment it is unlocked — the harness, evidence folders, logcat
  capture and APK are all in place.
- **Every device setting touched was put back.** `stay_on_while_plugged_in` was set to
  `2` (`usb`) so the phone would not sleep mid-run, and is reset to **`0`**
  (verified). Density is back to `Physical density: 480` with **no override**
  (verified). Night mode was read, never changed, and is still `yes` as found. The
  `adb reverse tcp:4719` mapping was removed and restored, and is present as it was.

---

*Evidence (screenshots, UI dumps, raw `dumpsys` text, full logcat) lives in
`.dsh-scratch/device-audit/audit-evidence/` and is deliberately not committed.
Nothing was paired. No approval was given. No app source was changed.*
