# Android phone checks — 2026-10-09

Checks that need the USB-connected phone. **Checks only: no app source was
edited, and a bug found is reported here rather than fixed.**

## What this ran against

| Thing | Value | How I know |
|---|---|---|
| Device | `f0a5b32b`, OnePlus CPH2419, API 35, arm64-v8a, 1080x2412 @ 480 dpi | `adb devices -l`, `wm size`, `wm density` |
| Dark mode | yes | `adb shell cmd uimode night` → `Night mode: yes` |
| Worktree | `.dsh-scratch/phone-checks`, branch `audit/phone-checks` | the commands in "Evidence" below |
| Commit tested | `f388925d` (my snapshot), then remote `main` = `0541ae60` | `git rev-parse origin/main`, `git ls-remote origin main` |
| App under test | `com.jarvis.client` 0.2.0, versionCode 1 | `adb shell dumpsys package com.jarvis.client` |

**`origin/main` was stale when this work started.** The local ref was
`f388925d`; the real remote `main` was `0541ae60`. I fetched it (read-only for
other worktrees). This matters for one reason: it proves the test results
below are valid for today's `main`, because

```
git diff --stat f388925d origin/main -- jarvis-client
   (empty — no diff at all, androidTest included)
```

so `jarvis-client` is byte-identical between the two, and no re-run was needed.

---

## 1. The instrumented suite — six classes

Command, from `jarvis-client`:

```
$env:ANDROID_HOME = "$env:LOCALAPPDATA\Android\Sdk"
.\gradlew.bat connectedDebugAndroidTest --console=plain
```

Pre-flight: `adb shell dumpsys trust` → current user
`trustState=UNTRUSTED, ... deviceLocked=0`; `dumpsys power` →
`mWakefulness=Awake`. The phone was **unlocked and awake**, so the run
proceeded (no keyguard bypass was needed or attempted).

Result: **46 tests, 4 failures, 0 errors, 0 skipped, 2m57s, build FAILED.**

Evidence: `jarvis-client/app/build/outputs/androidTest-results/connected/debug/TEST-CPH2419 - 15.xml`.

| Class | Tests | Failed | Result |
|---|---|---|---|
| `LaunchTest` | 3 | 3 | **FAILED — before the app was launched** |
| `TokenStoreTest` | 6 | 0 | **PASSED** (all 6) |
| `ApiContractTest` | 32 | 0 | **PASSED** (all 32) |
| `EventStreamContractTest` | 3 | 0 | **PASSED** (all 3) |
| `FaceRenderTest` | 1 | 1 | **FAILED — before any face was drawn** |
| `FaceShotTest` | 1 | 0 | **PASSED, and it really did photograph the faces** |

### The four failures are one cause, and it is not the app

All four (3 × `LaunchTest`, 1 × `FaceRenderTest`) fail identically in `@Before`:

```
java.lang.SecurityException: Error granting runtime permission
  at android.app.UiAutomation.grantRuntimePermission(UiAutomation.java:1540)
  at com.jarvis.client.LaunchTest.grantNotifications(LaunchTest.kt:65)
  at com.jarvis.client.LaunchTest.clean(LaunchTest.kt:44)
Caused by: java.lang.SecurityException: grantRuntimePermission:
  Neither user 2000 nor current process has android.permission.GRANT_RUNTIME_PERMISSIONS.
```

This is the test harness being refused by **this** device, not the app
misbehaving: `LaunchTest` and `FaceRenderTest` grant `POST_NOTIFICATIONS` in
`@Before` so the app's own permission prompt cannot cover the activity, and on
this Android 15 / ColorOS build the shell identity behind `UiAutomation` is not
allowed to grant it.

**What that means, stated plainly: these two classes did not test the app at
all on this phone.** `LaunchTest`'s whole purpose — "the app reaches RESUMED
without throwing" — was **not verified here**, and `FaceRenderTest`'s "every
offered face draws" was **not verified here**. They are red for a harness
reason. I am not calling them app bugs, and I am not calling them passes
either.

The bad news worth flagging: the reason they grant that permission is about
being *paired*. On this phone the app is unpaired, and `MainActivity` only asks
for `POST_NOTIFICATIONS` once paired — so the grant is not even needed for the
unpaired path, yet its failure aborts both classes before `ActivityScenario`
runs.

### `FaceShotTest` — a correction to the brief

The brief expected `FaceShotTest` to fail as a "golden-image test built for
CI's 1080x2160 @ 420 dpi emulator". **It is not a golden-image test and it did
not fail.** Its own source says so:

> **It gates nothing, on purpose.** Its only assertion is the stall check
> described at the end of this comment; every other step that can go wrong is
> caught and written into `manifest.txt` … Whether a face is RIGHT is a
> judgement made by looking, not a check a test can make.
> — `FaceShotTest.kt` lines 58-65

So there is no pixel comparison to mismatch, and no golden file in the repo. It
ran for **41.3 s and passed**, and it produced real output — 25 face PNGs plus
an uncropped screen, pulled back to `docs/phone-checks-2026-10-09/faceshots/`.
From its own `manifest.txt` on the device:

```
device: OnePlus CPH2419, API 35
gpu: Adreno (TM) 730
each face: IDLE, 360dp square, ~1200ms after it was laid out
01-arc.png: 945x945px (360dp at 2.625x), screen 1080x2160, 4.9% of pixels
  brighter than the ground, quality high at up to 60 fps
...
25-robot.png: ... quality ...
```

It also **caught the same permission failure and carried on** rather than
failing — `manifest.txt` line 1 is
`setup: SecurityException: Error granting runtime permission`, because its
setup is wrapped in `runCatching`. That is the design working as documented,
and it is why the two classes diverge.

Two side effects of this class, worth knowing:
- Before it ran, `wm size` already reported an override of `1080x2160` at
  420 dpi (`display before: Physical size: 1080x2412 Override size: 1080x2160`),
  left behind by an earlier attempt. Its `finally` resets the display, so after
  the run that override is gone.
- `connectedDebugAndroidTest` **uninstalls the app when it finishes**. See §6.

---

## 2. A fresh build, and the five "new features"

`.\gradlew.bat installDebug` → `BUILD SUCCESSFUL`, `Installed on 1 device`,
`com.jarvis.client` 0.2.0 / versionCode 1, and `MainActivity` resumed.

### The five features are not in `main`. They cannot be screenshotted from it.

This is the headline finding, and it is why the requested screenshot-by-
screenshot table does not exist: **there is nothing in a `main` build to
photograph.**

Evidence, all four independent of each other:

1. **Merged PR numbers at or above 150 on the fetched remote `main`** are
   `150,151,153-158,160-163,165,166,168,171,172,176`. **`164`, `167`, `170`,
   `174` and `179` are absent** — never merged.
2. `git grep` over the `origin/main` tree for `Name this device`, `TimePicker`,
   `did not take effect`, `SettingsSearch`, `DeviceLabel` → **zero matches** in
   `jarvis-client`.
3. The work exists, but on unmerged branches: `81a51890` ("Settings search"),
   `5a69f61d` ("Add a phone Screen refresh rate setting"), `105266d3` ("prompt
   coach: four settings beside the switch"), `e76adb3c` ("label a paired
   device"). Each: `git merge-base --is-ancestor <sha> origin/main` → **not an
   ancestor**.
4. They are **open, unmerged pull requests**:
   `git ls-remote origin refs/pull/N/head` →
   `164=73b2f7b3`, `167=896763ea`, `170=13e829c7`, `174=348ef856`,
   `179=1b9d6084`.

I did not checkout other agents' in-progress branches into this worktree, and I
did not edit source, so this is reported rather than worked around.

### What the installed `main` build shows in each place instead

Every row below is a screenshot plus a `uiautomator dump` taken at the same
moment. The app is unpaired, so several sections legitimately cannot load —
that is the app's own honest "not connected to a PC yet" sentence, not a
failure, and not a pass either.

| # | Feature asked for | What actually rendered | Evidence |
|---|---|---|---|
| 1 | Settings search box (PR #164) | **No search box.** The top of Settings is a `JUMP TO:` list of 22 section chips, then sections. There is no text field anywhere on the screen. | `03-settings-top.png`, `dump-settings.xml` |
| 2 | Notification time picker (PR #170) | **No time picker.** The `PHONE NOTIFICATIONS` section renders a read switch, "Android's own permission" text, `Notification access: not granted yet.`, and the app allow-list. No time control, no `TimePicker` anywhere in `main`. | `07-settings-phone-notifications.png`, `dump-phonenotif.xml` |
| 3 | "Name this device" (PR #174) | **No naming box.** The `DEVICES` section shows one line: "Your PC's Jarvis does not have a device list yet." | `06-settings-devices.png`, `dump-devices2.xml` |
| 4 | Prompt coach's four new settings (PR #179) | **Only the section header.** "Couldn't read the prompt coach: This app isn't connected to a PC yet. Add your PC's name and pairing key in the connection settings." Source on `main` has a single `coach-enabled` row, not five. | `04-settings-prompt-coach.png`, `dump-promptcoach.xml` |
| 5 | Refresh-rate screen (PR #167) | **No such row or section.** No refresh-rate entry in the `JUMP TO:` list or the sections, and no "did not take effect" string in `main` — so the honest sentence the brief expects cannot be checked, because the screen it belongs to is not here. | `dump-settings.xml` (full chip list) |

So of the five: **none rendered.** Not one of them is a regression — they were
never merged.

---

## 3. The checks that need no fingerprint

### The stale-link gate cannot fire unpaired — confirmed, and here is why

Not "broken"; **unreachable, by construction**:

```kotlin
fun decisionBlocked(link: LinkState, stale: Boolean): String? = when {
    link != LinkState.CONNECTED -> DECISION_NOT_CONNECTED   // <- taken first
    stale -> DECISION_CATCHING_UP
    else -> null
}
```
— `LinkWords.kt` lines 47-51

The not-connected branch is tested **first**, so while the phone is unpaired —
`link` is never `CONNECTED` — the *stale* sentence can never be the one shown.
Staleness is also only meaningful once connected: `_stale` starts `true`
(`JarvisRuntime.kt` line 321) and is only cleared after a successful refresh
following a real connection (`if (refreshedSinceOpen) _stale.value = false`,
line 1380). Reaching `CONNECTED` needs a paired desktop.

Device-side agreement: the CHECKS screen reports `Connection: Not paired` and
`Desktop: Not set`, and the app's own prefs contain no host and no token (below).

### The two credential-gated switches on the SECURITY screen

Both render, I read their real state, and **I deliberately did not toggle
either** — for one of them, doing so could not be undone without the owner's
fingerprint (see §4).

| Switch | State now | Which direction needs a credential |
|---|---|---|
| **Lock Jarvis** (App lock) | **OFF** (`checked=false`) | ON is a tightening and is saved at once; **OFF is a loosening and waits for a fingerprint or PIN** |
| **Swipe to approve or deny** | **ON** (`checked=true`) | OFF is instant; **turning it back ON asks for the fingerprint or PIN** |

Evidence: `09-security-lock-and-fingerprint.png` and `dump-security-toggles.xml`.
The dump's switch nodes: `[90,440][990,632] checkable=true checked=false` (Lock
Jarvis) and `[90,2334][990,2412] checkable=true checked=true` (Swipe). The
Swipe row states its own rule on screen: *"Turning it back on asks for your
fingerprint or PIN."* The App lock rule is the code's: `SecurityScreen.kt`
lines 43-44 — *"a loosening waits for a fingerprint or PIN check, a tightening
is saved at once (`SecurityRules.loosens`)"*.

Only these two behave that way. The other controls on that screen are either
not switches or not credential-gated: `Lock again after` (1 min selected),
`End Live when` (stricter option selected; the screen says the *other* option
asks for the fingerprint), and `Fingerprint for approvals` (Risky only
selected).

### The app's own notification channels

The four names in the brief — `channel_alarm`, `channel_schedule`,
`channel_approval`, `channel_handoff` — are **string-resource keys, not channel
ids**, so checking for a channel literally named `channel_handoff` would check
the wrong thing. The real ids, read off the running app with
`adb shell dumpsys notification --noredact`:

| Channel id | Name | Importance | Exists? |
|---|---|---|---|
| `jarvis_approval` | Approvals | 4 | **yes** |
| `jarvis_approval_quiet` | Approvals (quiet) | 2 | **yes** |
| `jarvis_alarm` | Alarms and urgent alerts | 4 (alarm sound + vibration) | **yes** |
| `jarvis_schedule` | Reminders and timers | 4 | **yes** |
| `jarvis_link` | Jarvis link | 2 | **yes** |
| `jarvis_needs_you` | (hand-off / "a website needs you") | — | **not present** |

`jarvis_needs_you` is `HandoffNotifier.CHANNEL_ID` and is created lazily when
that notification is first posted, so its absence now is expected on a fresh
install, not a defect. There is no channel id containing "handoff" at all.

Separately: **`POST_NOTIFICATIONS` is not granted** on this phone. The app's own
CHECKS screen says so — *"Not allowed, so you are not told about any approval.
Nothing else looks broken, so this is the only place it shows."* The channels
exist regardless, because they are created at application start.

### Dark mode and font scale, measured

Dark mode is on, and the screens render dark — measured, not eyeballed. Mean
luma and the share of pixels below luma 60, via Pillow over the whole
screenshot:

```
03-settings-top.png                1080x2412  mean_luma=12.9  below_60=96.0%
04-settings-prompt-coach.png       1080x2412  mean_luma=21.7  below_60=92.8%
06-settings-devices.png            1080x2412  mean_luma=25.4  below_60=91.7%
07-settings-phone-notifications.png1080x2412  mean_luma=24.2  below_60=93.0%
09-security-lock-and-fingerprint.p 1080x2412  mean_luma=27.6  below_60=89.0%
```

Every screenshot is the full 1080x2412 — so no display override was in force —
and none is blank.

Font scale, on the reachable screens (the five "new screens" do not exist, so
they could not be the subject):

- At `font_scale = 1.0`, the `Voice` jump chip is `[78,447][177,493]` — 99x46 px.
- At `font_scale = 1.3`, the same chip is `[78,451][208,512]` — **130x61 px**,
  about 1.3x in both directions. Screenshots `10-fontscale-1.3.png` and
  `11-settings-fontscale-1.3.png`.

So text scaling is honoured by these screens.

### Every override reset, and proven reset

I set exactly one: `font_scale`. Nothing else was set by me (`wm size` /
`wm density` were already at physical). Proof of the reset:

```
settings get system font_scale  ->  1.0
wm size                         ->  Physical size: 1080x2412
                                    (no "Override size:" line at all)
wm density                      ->  Physical density: 480
```

and the reset rendering matches the original pixel-for-pixel in aggregate:
`12-settings-fontscale-reset-1.0.png` mean_luma = **12.9**, identical to
`03-settings-top.png`'s 12.9.

---

## 4. What I did not do, and why

### The App-lock black-frame test — not done, on purpose

Turning App lock **OFF** is a loosening and asks for the owner's fingerprint
(§3). So switching it on to see the black frame would strand the phone unable
to switch it back, and every later screenshot on this shared device would be
black until the owner intervened. **I did not touch either switch.** The
owner-run procedure for this is the 30-second one in the tour report; it needs
the owner's finger on the sensor.

### Nothing was fixed

No app source was edited. The five missing features are unmerged other-agent
work (§2); the two red classes are a harness permission problem (§1). Both are
reported, not patched.

---

## 5. Things that look wrong

1. **The brief's premise about the five features is wrong, and that is the
   most consequential finding.** They are not "today's merges"; they are open
   PRs. Anyone screenshotting-against-`main` will keep hitting this. Evidence
   in §2.
2. **`LaunchTest` and `FaceRenderTest` will stay red on any real phone of this
   generation, and will stay red about nothing.** They abort in `@Before` on a
   `UiAutomation` grant that this device refuses, so the app is never launched
   and no face is ever drawn. The suite therefore reports failures that a
   reader will naturally read as "the app does not start" — the exact opposite
   of the truth, and the exact gap `LaunchTest` was written to close. On this
   phone the app *does* start (I installed and launched it, and drove its UI
   for an hour). **This is the worst thing I found**, because a false red here
   hides the real thing the test exists to catch.
3. **`FaceShotTest`'s pass is weaker than it looks, and its name invites the
   wrong conclusion.** It gates nothing but a stall, so "passed" means "it did
   not hang", not "the faces are right". The brief expected it to fail and it
   cannot fail that way.
4. **`POST_NOTIFICATIONS` is not granted on this phone**, and the app's own
   CHECKS screen is the only place that says so. With the channel checks,
   that means notification behaviour cannot be exercised end to end here until
   someone taps "Allow notifications".
5. **`screen` dump noise:** `dumpsys notification` shows
   `AppSettings: com.jarvis.client (10043) importance=NONE`. Worth a glance
   from whoever owns notification behaviour.

---

## 6. Side effects on the shared device (so other sessions are not surprised)

- `connectedDebugAndroidTest` **uninstalled `com.jarvis.client`** when it
  finished — that is Gradle's normal behaviour, not a fault. `pm list packages
  | grep jarvis` returned **nothing** immediately afterwards. I then installed
  the freshly built `main` APK, so the package is back at 0.2.0 / versionCode 1.
- Because the app was reinstalled, **whatever local app state existed before is
  gone.** I cannot prove what that was. The brief states the app was unpaired,
  and that is consistent with what I can see: Security is one of the four
  screens reachable with no pairing at all (`MainActivity.kt` lines 1849-1852 —
  unpaired, only `CHECKS`, `FAQ`, `SECURITY` and `SETTINGS` survive), so being
  on the Security screen implies nothing about a token.
- The display override that was already present before this run
  (`1080x2160` @ 420) was cleared by `FaceShotTest`'s own `finally`. The phone
  is back at physical 1080x2412 / 480.
- `adb reverse tcp:4719 tcp:4719` is set, as the brief suggested.
- Face PNGs remain at `/data/local/tmp/jarvis-face-shots` on the device
  (27 files) and are copied into this folder's `faceshots/`.

**The install-safety claim, verified rather than assumed.** The brief said
installing is safe because Jarvis is not paired, so there is no pairing token or
data to lose. What I found:

```
adb shell pm list packages | grep jarvis   ->  package:com.jarvis.client   (only)
run-as com.jarvis.client ls shared_prefs   ->  internal_launch.xml
                                               jarvis_captured_notifications.xml
                                               jarvis_client.xml
cat .../shared_prefs/jarvis_secure.xml     ->  No such file or directory
cat .../shared_prefs/jarvis_client.xml     ->  <map>
                                                 <long name="update_last_try_ms" .../>
                                               </map>
```

`jarvis_secure.xml` is where `TokenStore` keeps the encrypted pairing token, and
it **does not exist**; the settings file holds a single update-timestamp and no
host and no token. So yes — there was no token or settings to lose.

---

## 7. What still needs the owner

1. **Pairing.** The phone is unpaired, so most screens reasonably say "pair
   first". Nothing about prompt coach, "What asks first", devices or the
   notification read switch can be exercised until the owner pairs the phone to
   the PC (phone pairing is QR + a short typed code, confirmed by an approval
   card on the PC).
2. **The fingerprint test.** The App-lock black-frame behaviour needs the
   owner's own finger, using the tour report's 30-second procedure.
3. **The five features need merging.** Until PRs #164/#167/#170/#174/#179 land,
   no phone check can see them. Once merged, the screenshots in §2 are the ones
   to take.
4. **`Allow notifications`** on the app's CHECKS screen, if notification
   behaviour is to be tested end to end.

---

## Evidence index

All paths relative to this folder (`docs/phone-checks-2026-10-09/`).

**Screenshots** — `01-fresh-install-after-launch.png`, `02-platform-checks.png`,
`03-settings-top.png`, `04-settings-prompt-coach.png`,
`05-checks-after-back.png`, `06-settings-devices.png`,
`07-settings-phone-notifications.png`, `08-security.png`,
`09-security-lock-and-fingerprint.png`, `10-fontscale-1.3.png`,
`11-settings-fontscale-1.3.png`, `12-settings-fontscale-reset-1.0.png`.

**UI dumps** (paired with the screenshot of the same screen) —
`dump-launch.xml`, `dump-checks.xml`, `dump-settings.xml`,
`dump-promptcoach.xml`, `dump-devices.xml`, `dump-devices2.xml`,
`dump-phonenotif.xml`, `dump-security.xml`, `dump-security-toggles.xml`,
`dump-before-fontscale.xml`, `dump-checks-fontscale13.xml`,
`dump-settings-fontscale13.xml`.

**Face evidence** — `faceshots/00-whole-screen-arc.png`,
`faceshots/01-arc.png`, `faceshots/21-redpanda.png`,
`faceshots/25-robot.png`, `faceshots/manifest.txt`.

**JUnit XML** —
`jarvis-client/app/build/outputs/androidTest-results/connected/debug/TEST-CPH2419 - 15.xml`.
