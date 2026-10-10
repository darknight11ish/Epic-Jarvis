# The phone's three dead ends, its notification row, and audit 2's leftovers

Written 2026-10-09, in the second conversation, which owns `jarvis-client/` and
the attached phone (`docs/HANDOFF-ANDROID-2026-10-09.md`). This is items **1**,
**2** and **4** of that handoff's queue. Item 3 — the 12 screens behind pairing —
is not here: it needs the owner's Windows Hello tap on the PC, so it is the
owner's to start.

Everything below was **run on the owner's own handset** (OnePlus CPH2419,
Android 15 / API 35, `f0a5b32b`) unless the line says otherwise. Evidence is in
`.dsh-scratch/android-verify/` (UI dumps, untracked), named per finding.

---

## 1. The three dead ends, all closed

### 1a. "Set Jarvis as the assistant app" said nothing at all

**The tour saw** a tap that changed nothing, twice, with no role request in
logcat (`docs/ANDROID-TOUR-2026-10-09.md`, finding 1).

**The cause, measured this time.** The request *is* launched. The phone's own
permission controller then refuses it:

```
E/RequestRoleActivity( 4618): Role is not requestable: android.app.role.ASSISTANT
I/RequestRoleFragment( 4618): Role request result ... result=1
```

So `RoleManager.isRoleAvailable` answers **yes** while the role cannot be
requested at all, the system screen opens and closes without drawing anything,
and `MainActivity.requestAssistantRole()` returned silently on both failure
paths. Nothing in the public API can tell the app this beforehand — which is
why the fix is to report the outcome rather than to predict it.

**What it does now.** Both failure paths say so in the card, and the card
offers the route that does work there:

- the outcome line: *"Android has not made Jarvis your assistant. Use Open
  Android's assistant settings and pick Jarvis there."*
- a second, always-present button, **"Open Android's assistant settings"**,
  which opens `ACTION_VOICE_INPUT_SETTINGS` — on this phone ColorOS's
  `Settings$ManageAssistActivity`, the real "Digital assistant app" screen —
  falling back to the default-apps list and then to Settings itself.

**Verified on the phone.** Tapping the role button now draws the line
(`v04-role-tapped.xml`, logcat still shows the same refusal); tapping the
second button opens `Settings$ManageAssistActivity`
(`v05-assist-settings.xml`).

### 1b. "Start link" gave no sign it had done anything

**The tour saw** the card reading exactly the same before and after the tap, so
a second tap was indistinguishable from the first — worse on an unpaired phone,
where there is nothing for the link to reach and the card did not say so.

**What it does now.** The tap leaves a line under the button, and the line
names where the real answer shows: *"Asked Android to start the link. The
Connection card above says whether your desktop has answered."* — or, unpaired,
*"…This phone is not paired yet, so there is nothing for it to reach."*

**Verified on the phone** (`v07-link-tapped.xml`): the unpaired sentence is on
screen after one tap.

### 1c. Help pointed at a button that is not on the screen

**The tour saw** the FAQ answer *"Open Platform checks and tap Train my voice on
the Your voice card"* — while an unpaired phone deliberately does not draw that
button (`MainActivity` passes `onTrainVoice` only once paired, because the clips
go to the desktop). Help is the screen someone reads when something is wrong.

**What it does now.** The answer names the condition first: *"Pair this phone
with your desktop first: the recordings go to the desktop, so Train my voice
appears on the Your voice card only once there is one to send them to - before
that the card says Unknown. Once paired, open Platform checks and tap..."*

**Verified on the phone** (`v16-faq-answer.xml`).

---

## 2. "Notifications from Jarvis" — the row the owner chose

`docs/SETTINGS-COVERAGE-AUDIT-2026-10-09.md` (GAP 1) found the PC's
Notifications card had no phone counterpart, and the owner chose the audit's
first option on 2026-10-09: **point at Android's own per-app notification
screen** rather than build a second copy of the PC's card.

**What was built.** One Settings row — `item(key = "jarvis-notify")`, section
"Notifications from Jarvis", sitting with the other two notification rows — with
one line and one button. The line names which app owns which half, because that
is the confusing part of two notification screens on one phone:

> Android decides whether this phone shows what Jarvis sends from your PC:
> alarms, reminders (the morning briefing arrives as one), approvals and "a
> website needs you" are separate switches there, and quiet hours are Android's
> own Do Not Disturb. Which kinds your PC sends at all is the PC's own
> Notifications card.

Those kinds are the app's real Android channels, read off the phone with
`dumpsys notification --noredact` on 2026-10-09: `jarvis_alarm` ("Alarms and
urgent alerts"), `jarvis_schedule` ("Reminders and timers" - the morning
briefing arrives there too, which is why it is not named as a switch of its
own), `jarvis_approval` ("Approvals", with `jarvis_approval_quiet` beside it)
and `jarvis_needs_you` ("A website needs you", created when a hand-off is first
posted, so it appears in Android's own screen only after one has happened).
An earlier draft of this line said each kind - the briefing included - had its
own switch; the dump is what corrected it.

**Verified on the phone:** the row is in the jump list (`v11-settings.xml`),
jumping to it draws the section (`v12-notify-row.xml`), and the button opens
ColorOS's own per-app notification page for Jarvis —
`com.oplus.notificationmanager/…AppNotificationSettingsActivity`, "Allow
notifications: Off" (`v13-android-notify.xml`).

**What was deliberately not built:** the PC's four per-kind switches, quiet
hours and Test button. Those belong to the PC's card, which the desktop's Rust
really honours, and a second copy on the phone would be a third place to keep in
step with Android's own settings.

**Why it is not a hideable menu.** There is no menu id for it on the phone: the
registry's `notifications` Section is `app="desktop"` (the PC's card), so the
row is listed among `MenuVisibilityTest`'s deliberately-not-menus keys, and
`OpenPlace` keeps answering "only in Jarvis on your PC" for the id
`notifications` — which is still true of the four switches and quiet hours.
`tools/check_parity.py` is clean.

---

## 3. Audit 2's remaining findings

### N2 — already closed by N1's fix; now held by a test

N2 was the same root cause as N1 with a different symptom: with rows already on
screen, a failed report left them there indefinitely under "What is new". N1's
fix (#162) made a failed report **its own state with no findings**
(`Watch.Report.Failed`, `Watch.reportOf`), so the rows are gone rather than
stale and the block draws its own failure line. A new test
(`WatchReportTest.rows on screen do not survive a failed refresh`) holds that
closed. **No separate fix was needed** — the handoff listed N2 as open, and this
is the correction.

### N3 — "open the approval" counted the list's own items by hand

`HomeScreen` found the focused card by summing ten conditional items above the
approval cards, with a comment asking the next person to keep it in step — the
same bug class as the first audit's finding 8, in the one place a notification
sends the owner to decide something. It now scrolls to the **card's own key**
(the cards are keyed by their id), through a shared `scrollToKey` that can start
from the top, because Home can be opened with the thread scrolled anywhere while
the walk only moves down. `ScrollToKeyOnce` keeps its own behaviour.

### N4 — a condition the compiler proved always true

`ChatbotPlate.kt`'s `if (showCompare && c != null)` printed "Condition is always
'true'." on every build. The non-null comparison is bound once now, and no such
warning is in the build output.

---

## 4. Tests and what ran where

- `.\gradlew.bat testDebugUnitTest` from `jarvis-client`, with `ANDROID_HOME`
  set: **BUILD SUCCESSFUL, 2,000 tests, 0 failures, 0 errors, 0 skipped**
  across 184 JUnit XML files, read from the XML rather than the exit code.
  **19 of those are new** (4 for the three dead ends, 3 for the notification
  row, 3 for N3/N4, 1 for N2, 8 for the first audit's leftovers below).
- `.\gradlew.bat assembleDebug`: BUILD SUCCESSFUL, and that APK was installed
  on the phone with `adb install -r` (in place — the app is debuggable, and no
  app data was cleared, nothing uninstalled, nothing paired, no credential
  typed).
- The four fixes above were then driven over adb and read back from UI dumps.
- `tools/check_parity.py`: "No undecided drift."
- **One change outside `jarvis-client/`.** `backend/test_settings_registry.py`
  (merged into `main` by PR #166 the same day) requires every phone Settings row
  to be a registry `SECTION`, and the new row deliberately is not one. Its named
  exceptions (`phone_ok`) gained `jarvis-notify`, with the reason written beside
  it: the row opens Android's own screen and the registry's `notifications`
  Section stays desktop-only. That is what the backend CI job caught, and the
  suite passes locally (`115 passed, 0 failed`) with `JARVIS_BACKEND` unset -
  with it set, the suite tests the owner's live backend instead and says so,
  which is the known trap in the handoff, not a code failure.
- **Not run:** the instrumented/emulator suite (this machine has no
  virtualization), and CI is the first place this code is compiled by GitHub's
  toolchain.

### Three tests were updated by name, not relaxed

- `LimitsTest` pins `"limits" to 21`; inserting the notification row moved it to
  22.
- `MenuVisibilityTest`'s deliberately-not-menus list gained `jarvis-notify`.
- `TouchTargetAndInsetsTest` window starts for FaqScreen's two ~19dp targets
  moved 444/473 → 454/483, because the FAQ answer above them grew.

## 5. The first audit's eight remaining findings, now closed

None of these was in the 2026-10-09 handoff's queue, and the second audit's
Part 1 recorded all eight as still standing. One line each:

- **4** — Security's footer promised that "turning something on is instant"
  while two switches on that screen are loosenings that ask for the fingerprint
  or PIN on the way ON. The sentence is gone; the loosening rule stays.
- **5** — the daily standby card's payload was plain `remember` while its
  suppression flag was saveable, so a process death lost the offer for the day
  (the PC marks the day as made when it *serves* one). The payload now crosses
  that boundary through its own `Saver`, as its own JSON text.
- **7** — the "Never look at" picker walked every installed app **during
  composition**. It loads off the main thread with a "Looking for apps…" line
  now, exactly as `PhoneNotificationsPlate`'s identical walk does.
- **8** — "Show everything saved automatically" scrolled to "one item after
  `memory-counts`", which with that menu hidden landed on "Always keep in mind".
  It scrolls to the row's own key now, and shows the row for the visit when the
  owner has hidden it.
- **9** — "Clear the numbers" put the PC's assumed figures straight back. It is
  "Start over" now, which is what it does.
- **10** — Tasks' "Reading…" state existed and nothing constructed it, so the
  line and its colour were dead. The plate sets it before the first read.
- **11** — Voices drew the same "Hear it" result line twice, only one with
  `liveStatus()`. The duplicate is gone.
- **12** — one setting, two names on one screen: "Quality" and "Sharpness" are
  the same stored field and the same control. Sharpness is what the rest of the
  app calls it, so the per-face editor says that too.

Each is held by one assertion in `FirstAuditLeftoversTest`.

## 6. The instrumented suite, on the phone, at last

**All six instrumented classes had never run successfully** — two earlier
attempts died on the phone's lock screen. This run was on the attached CPH2419,
unlocked (`dumpsys trust` → `deviceLocked=0`) and awake, with
`adb reverse tcp:4719 tcp:4719` already in place.

**The one real defect was in the tests, not the app.** `LaunchTest` and
`FaceRenderTest` call `UiAutomation.grantRuntimePermission` in `@Before`, and
ColorOS refuses it to the shell the instrumentation runs as:

```
java.lang.SecurityException: Error granting runtime permission
Caused by: java.lang.SecurityException: grantRuntimePermission: Neither user 2000
nor current process has android.permission.GRANT_RUNTIME_PERMISSIONS.
```

So all three `LaunchTest` tests failed before asserting anything, and the run
stopped there: `TokenStoreTest` (which never grants) and `FaceRenderTest` never
ran at all. `FaceShotTest`'s JUnit entry came back with an **empty** `<failure>`
in that run and two classes missing — the same abort, recorded where it landed.

Each class now treats a refused grant as a fact of the device, logs it
(`W/JarvisFaceRender`, `W/JarvisLaunch`), and carries on. The oracles are
unchanged: the crash log, the shader-build marker, and the lifecycle assertion —
which stays **RESUMED** whenever the grant did happen, and falls back to
**STARTED** only when an OS permission dialog this test must not touch is on top.

**Measured after the fix, in one `connectedDebugAndroidTest` run:**

| Class | Tests | Failures | Time |
| --- | --- | --- | --- |
| `ApiContractTest` | 32 | 0 | 4.7 s |
| `EventStreamContractTest` | 3 | 0 | 16.5 s |
| `FaceRenderTest` | 1 | 0 | 52.0 s (every face really drew) |
| `FaceShotTest` | 1 | 0 | 40.1 s |
| `LaunchTest` | 3 | 0 | 4.5 s |
| `TokenStoreTest` | 6 | 0 | 0.1 s |
| **Total** | **46** | **0** | 2 m 11 s |

`FaceShotTest` photographed **all 25 faces** (20 shader faces, 4 animals and the
robot) into `/data/local/tmp/jarvis-face-shots`, 945×945 px each at 2.625×, plus
one whole-screen image, and its own `manifest.txt` recorded every one with a
lit-pixel share and the quality tier in use — so the faces can be looked at, not
just asserted. The display override it applies (`wm size 1080x2160`,
`wm density 420`) was removed by its own `finally`; measured afterwards:
physical 1080×2412, density 480, `font_scale` 1.0, rotation 0.

## 7. Still open, honestly

- **The 12 of 16 screens behind pairing** (handoff item 3): they need the
  owner's Windows Hello tap on the PC. Unchanged by either pass.
- **`docs/ANDROID-TOUR-2026-10-09.md` is not on `main`.** The handoff cites it
  as if it were; it exists only on the `audit/android-tour` branch
  (`3370ca32`). Its evidence directory is there too. Nothing here depends on it
  being merged, but the citation should not stay dangling.
- **App lock and the black frame** are still unmeasured, for the reason the tour
  gave: turning either switch on is instant, turning it off asks for the owner's
  fingerprint. The two-tap procedure for the owner is in the tour's Q2.
- **Refresh rate:** unchanged. The phone offers 60/90/120 and runs at 60 Hz
  because the owner's own `peak_refresh_rate` is 60; an app cannot change that
  without `WRITE_SECURE_SETTINGS`, and this handset ignores per-window requests.
