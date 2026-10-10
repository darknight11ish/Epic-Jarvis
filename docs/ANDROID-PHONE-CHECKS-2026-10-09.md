# Phone checks — 2026-10-09/10, on the attached handset

Run on the owner's OnePlus CPH2419 (Android 15 / API 35, 1080×2412 @ 480 dpi,
dark mode on, `f0a5b32b`), over USB with `adb reverse tcp:4719 tcp:4719`. The
phone was **unlocked** (`dumpsys trust` → `deviceLocked=0`) and awake
(`mWakefulness=Awake`) throughout; nothing was typed into a keyguard, and
**App lock was never turned on** (see "Not done, on purpose").

Every claim below names its evidence: a UI dump, a screenshot, a logcat line or
a command's own output. Dumps and screenshots are untracked, under
`.dsh-scratch/android-verify/` (`shots/` holds the PNGs).

## 1. The instrumented suite

All six classes ran, in one `.\gradlew.bat connectedDebugAndroidTest`:
**46 tests, 0 failures, 0 errors, 0 skipped** (2 m 11 s).

| Class | Tests | Failures | Time |
| --- | --- | --- | --- |
| `ApiContractTest` | 32 | 0 | 4.7 s |
| `EventStreamContractTest` | 3 | 0 | 16.5 s |
| `FaceRenderTest` | 1 | 0 | 52.0 s |
| `FaceShotTest` | 1 | 0 | 40.1 s |
| `LaunchTest` | 3 | 0 | 4.5 s |
| `TokenStoreTest` | 6 | 0 | 0.1 s |

Getting there needed a fix in the tests, not the app: `LaunchTest` and
`FaceRenderTest` call `UiAutomation.grantRuntimePermission` in `@Before`, and
ColorOS refuses it to the shell the instrumentation runs as —
`SecurityException: grantRuntimePermission: Neither user 2000 nor current
process has android.permission.GRANT_RUNTIME_PERMISSIONS`. All three
`LaunchTest` tests failed before asserting anything **and the run stopped
there**, so `TokenStoreTest` and `FaceRenderTest` never ran and `FaceShotTest`
came back with an empty `<failure>`. Both classes now treat a refused grant as
a fact of the device, log it (`W/JarvisFaceRender`, `W/JarvisLaunch`) and carry
on; the crash-log and shader oracles are unchanged, and the lifecycle
assertion stays RESUMED whenever the grant happened, falling back to STARTED
only when an OS dialog the test must not touch is on top.

`FaceShotTest` photographed **all 25 faces** into
`/data/local/tmp/jarvis-face-shots` — 945×945 px each at 2.625×, plus one
whole-screen image — with its own `manifest.txt` recording each one
(lit-pixel share, quality tier). It is **not** a golden-image test and did not
disagree with anything: nothing about it is screen-specific. Its `wm size
1080x2160` / `wm density 420` override came off in its own `finally`.

## 2. The day's feature screens, drawn on a real screen

Each feature PR was built and installed **on its own branch** (three of the five
are still open PRs; the other two are on `main`). One build per branch, because
they do not merge cleanly with each other or with today's `main`.

| Feature | Drawn? | Evidence |
| --- | --- | --- |
| **Settings search box** (#164) | **Yes** | `shots/01-settings-search-voice.png`, `shots/02-settings-search-cleared.png` |
| **Screen refresh rate** (#167) | **Yes**, with the honest line | `shots/03-refresh-rate.png`, `shots/04-refresh-rate-120-did-not-take.png` |
| **Name this device** (#174, on `main`) | **No — needs pairing** | see below |
| **Notification time picker** (#170) | **No — needs pairing** | `shots/05-limits-unpaired.png` |
| **Prompt coach's four settings** (#179) | **No — needs pairing** | `shots/06-prompt-coach-settings.png` |

**Search box.** Typing `voice` into the field (`android.widget.EditText` at
`[90,392][990,536]`) filtered the screen to **"1 setting matches."** with a
Clear button; tapping Clear brought the whole jump list back (Voice, Security,
Prompt coach, …). So: it filters live, and clearing restores.

**Screen refresh rate.** The screen renders its own explanation — *"It cannot
change your phone's own display setting - that belongs to the phone, and only
the phone's own Settings or a system app can change it. If the screen does not
take the rate, this screen will say so."* Picking **120 Hz** produced exactly
the honest sentence the handoff predicted: *"Jarvis asked the screen for 120 Hz,
but it is running at 60 Hz - so the change did not take effect. Your phone's own
display settings decide the real rate; an app can only ask."* (The phone's own
`peak_refresh_rate` is 60 and it sets `mIgnorePreferredRefreshRate: true`.)
Choosing **Follow the phone** again was verified: *"Now: the phone decides."*

**The three that could not be drawn are not failures.** They are all rows whose
values come from the PC, and the phone is unpaired:

- Limits (#170): *"Couldn't read the limits: This app isn't connected to a PC
  yet. Add your PC's name and pairing key in the connection settings."* The
  time picker lives inside that section, so it cannot be laid out without a PC
  answer.
- Prompt coach (#179): *"Couldn't read the prompt coach: This app isn't
  connected to a PC yet. …"*
- Name this device (#174): the row shows *"Your PC's Jarvis does not have a
  device list yet."* `Devices.LABEL_BUTTON` ("Name this device…") is drawn only
  by `DevicesPlate.kt` (lines 154, 177), which `MainActivity`/`SettingsScreen`
  reaches only when the PC reports it can pair (`can("pairing")`); unpaired,
  `Devices.MISSING` is drawn instead.

## 3. The checks that need no fingerprint

**Notification channels exist.** `dumpsys notification --noredact` on the phone
lists the app's own channels:

- `jarvis_link` — "Jarvis link"
- `jarvis_approval` — "Approvals" (importance 4, vibrates)
- `jarvis_approval_quiet` — "Approvals (quiet)" (importance 2)
- `jarvis_alarm` — "Alarms and urgent alerts" (importance 4, alarm sound, its
  own vibration pattern)
- `jarvis_schedule` — "Reminders and timers" (the morning briefing arrives here
  too: `ScheduleNotifier`'s own comment says "reminders, timers, and briefings")

`jarvis_needs_you` — "A website needs you" — is **not** in that list yet, and
that is correct: `HandoffNotifier.ensureChannel` creates it when a hand-off is
first posted. **Finding for the record:** the phone's "Notifications from
Jarvis" row says the four kinds have their own switch there; the briefing is not
one of them (it shares the reminders channel), and its wording was corrected to
say so.

**The stale-link gate cannot fire unpaired, and that is not a fault.** The
Connection card says *"Not paired — This phone is not paired with a desktop yet.
Go back to type the desktop's address and token."*, so there is no link to go
stale. Its words for the live case are in `LinkWords.kt` ("Catching up…", *"…so
this decision waits until then"*), unchanged and unexercised.

**The two credential-gated switches on SECURITY are off, and were not
touched.** `shots/12-security-top.png` and `shots/13-security-hidden-lists.png`
show **Lock Jarvis** (off) and **Hide memory lists and chat history**, under
"FINGERPRINT FOR PRIVATE LISTS". Their own words: *"Turning something off, or
making it looser, asks for your fingerprint or PIN first."* Flipping either
**on** is instant but flipping it back **off** needs the owner's fingerprint, so
this run did not flip them — the state a reader sees in the screenshots is the
state it found.

**Dark mode and a larger font.** The phone is in dark mode (`cmd uimode night`
→ "Night mode: yes") and every screenshot above is the dark theme. Font scale
was raised to 1.3 and the two new screens that can draw unpaired were re-shot:
the search box (`shots/08-search-font130.png`, filtering
`shots/09-search-font130-filtered.png` — a long word wraps inside its row) and
the refresh-rate screen (`shots/10-refresh-rate-font130.png`). Nothing clipped;
every text node stayed inside its card.

**Overrides, and proof they are back:**

| Setting | Before | During | Now |
| --- | --- | --- | --- |
| `system font_scale` | 1.0 | 1.3 | **1.0** |
| `wm size` | physical 1080×2412 | — | **physical only, no override** |
| `wm density` | physical 480 | — | **physical only, no override** |
| `secure display_density_forced` | unset | — | **unset** |
| `global display_size_forced` | unset | — | **unset** |
| `system user_rotation` | 0 | — | **0** |
| `system accelerometer_rotation` | 0 (as the tour recorded) | — | **0**, restored after it read 1 |
| App install | `com.jarvis.client` | — | same package, upgraded in place |

Swipes used to scroll always started at y≈1800 or higher (the ColorOS gesture
strip starts lower), so no stray gesture changed density or rotation this run.

## Not done, on purpose

- **The App-lock black-frame test.** Turning either switch on is instant;
  turning it off asks for the owner's fingerprint. The 30-second procedure for
  the owner is in `docs/ANDROID-TOUR-2026-10-09.md`, Q2.
- Anything behind pairing: the 12 screens, and the three feature rows above.
  Pairing needs the owner's Windows Hello tap on the PC.
