# Android device feature tour — 2026-10-09

**Run on a real phone.** OnePlus CPH2419 (OnePlus 10T), Android 15 / API 35,
arm64-v8a, 1080×2412 at 480 dpi, dark mode on. App `com.jarvis.client` 0.2.0
(build `2f925c1`), reached over `adb reverse tcp:4719 tcp:4719`.

**Unpaired. Nothing approved. No credential typed. No pairing token touched.**
The backend reports 0 paired devices, so only the 4 screens exempt from the
pairing takeover were reachable: `CHECKS`, `FAQ`, `SECURITY`, `SETTINGS`. The
other 12 are replaced by the pairing screen.

**Read-only audit.** No app source was changed. No app data cleared, nothing
uninstalled, nothing paired. Every device setting touched during the run was
put back — see [Device state](#device-state-and-what-was-put-back).

This worktree was branched from `origin/main` at `2f925c11`. The phone was
running the release APK built from that commit (`2f925c1`). `origin/main` has
since moved on; nothing here was re-checked against the newer commits, and this
branch changes exactly one file — this report.

**What I could not complete, and exactly what stopped me**

| Not done | What stopped me |
| --- | --- |
| The black-frame test for App lock / "Hide memory lists and chat history" | Turning either switch **on** is instant, but turning it back **off** asks for the owner's fingerprint or PIN (`SecurityRules.loosens`, `data/Security.kt`: `(from.privateLists && !to.privateLists)`, `(from.appLock && !to.appLock)`). I am not allowed to type a credential, so I could not put the phone back. **Not measured.** The exact two-tap procedure for the owner is in [Device-only answers](#device-only-answers) Q2. |
| `Scan the code on your PC`, `Type the code instead`, `Use the old shared key instead` | Each one starts pairing. |
| The two credential-gated switches on `SECURITY` ("Lock Jarvis", "Hide memory lists and chat history") and the "Look at this" screen switch | Turning them **on** is instant and turning them off needs the owner's fingerprint. Same reason as above. |
| 15 of the 20 FAQ questions | Time. 5 were opened and closed; the same control shape covers all 20. |
| The ~100 individual switches under `SETTINGS` sections | Time. All 20 section jump chips were tapped; the controls inside each section were enumerated but not each tapped. |
| Anything behind pairing | The 12 screens are unreachable. Listed in [What still needs pairing](#what-still-needs-pairing). |

---

## Screen-by-screen

| Screen | Reached? | Rendered right? | Controls a person would tap | Tapped | Responded | Errors |
| --- | --- | --- | --- | --- | --- | --- |
| Pairing (stands in for 12 screens) | yes, on launch | yes, dark | 5 | 2 (`Platform checks`, `Help`) | 2 | none |
| `CHECKS` — "Platform checks" | yes | yes, dark | 15 | 15 | **13** | none |
| `FAQ` — "Help" | yes | yes, dark | 22 (20 questions + 2 footer links) | 5 | 5 | none |
| `SECURITY` — "Lock and fingerprint settings" | yes | yes, dark | 23 (11 groups) | 1 (`Add an app`) + picker open/close | 2 | none |
| `SETTINGS` | yes | yes, dark | 20 jump chips + ~100 inside | 20 | 20 | none |
| *Android's own* app-notification page | yes, opened by `Allow notifications` | system UI | — | — | — | none |
| *Android's own* "Let app always run in background?" | yes, opened by `Keep link alive` | system UI | — | — | — | none |

**Totals: 4 of 16 app screens reached, 43 distinct controls tapped, 41 responded, 2 did nothing.**

`FATAL`, `ANR in`, `SkipDraw` and "Force finishing" were **empty for the whole
session** — checked after every phase (`adb logcat -d | Select-String
"FATAL|ANR in|SkipDraw|Force finishing"`). Not one exception from
`com.jarvis.client`.

---

## Findings, ranked by what actually hurts the owner

### 1. "Set Jarvis as the assistant app" is a dead button that says nothing

*What happens:* tap it and **nothing at all changes**. No new screen, no
dialog, no message. Tapped twice, on two separate runs.

*How I know:* the screen signature is identical before and after
(`transcript-J.txt`: `'Set Jarvis as the assistant app': screen changed=False`),
and logcat over the tap shows no role request, no new activity, nothing from
`RoleManager` (`transcript-J.txt`, the "logcat around the tap" block).

*Why it matters:* this is the only button on `CHECKS` for the Digital assistant
card, and the "Look at this" screen-reading feature is gated on that role —
`ScreenNever.kt`: *"this works only when Jarvis is set as your phone's assistant
app"*. So the owner is told they need it, taps the button offered, and gets no
result and no reason. The code explains why: `MainActivity.kt:3817-3822` —
`requestAssistantRole()` returns silently if the role is unavailable
(`if (!runCatching { rm.isRoleAvailable(...) }.getOrDefault(false)) return`)
and swallows a failed launch (`runCatching { assistantRolePermission.launch(intent) }`).
Both paths are invisible to the owner.

*Evidence:* `transcript-J.txt`, `.evidence/Kres-Digitalassistant.xml`,
`MainActivity.kt:3809-3822`.

### 2. "Start link" gives no sign that it did anything

*What happens:* tap it and the screen does not change at all.

*How I know:* `transcript-J.txt` — `'Start link': screen changed=False`. In an
earlier run the same tap was followed by a network request from the app
(`D/OemPaidWifiNetworkFactory ... RequestorPkg: com.jarvis.client`,
`transcript-D.txt`), so the service probably *does* start. But the card's own
line is **"No problems starting the connection so far."** both before and after,
so the owner cannot tell a successful tap from a missed one.

*Why it matters:* small, but it is the one button on the Link service card, and
an owner who taps it twice because nothing happened has no way to know they
were fine the first time. An unpaired phone makes this worse — there is nothing
for the link to connect to, and the button does not say so.

*Evidence:* `transcript-J.txt`, `transcript-D.txt`, `.evidence/C03-checks-s04.png`.

### 3. Help tells the owner to tap a button that is not on the screen

*What happens:* the FAQ answer "How do I teach Jarvis my voice? Where is the
talk button?" says: *"Open Platform checks and tap **Train my voice** on the
Your voice card."* On this phone that button is not there. The "Your voice" card
shows only **"Unknown — Your PC has not answered yet, so this is not known."**
with no control at all. The same is true of the "Wake word — hey Jarvis" card.
The whole FAQ answer is a dead end in the unpaired state.

*How I know:* `.evidence/C03-checks-s02.png` and the dump of the same screen
show no `Train my voice` node anywhere on `CHECKS`; the union of every control
on the screen is in `transcript-1.txt` (lines 247-277). The button is
conditional by design — `ReadinessScreen.kt:127`: *"Opens 'Train my voice'. Null
hides the button."* — but `FaqScreen.kt:109` states the instruction
unconditionally.

*Why it matters:* Help is the screen an owner reads *when something is wrong*,
and this is the one place it points at a control that does not exist yet.
Low harm, but it costs trust exactly when trust is thin.

*Evidence:* `transcript-C.txt`, `.evidence/C03-checks-s02.png`,
`ReadinessScreen.kt:127`, `FaqScreen.kt:108-114`.

### 4. (Method note, not an app fault) A stray gesture pulled the phone into another app and changed three settings

During the very first scroll, `adb shell input swipe 540 2100 540 500` — a swipe
starting 312 px above the bottom edge, inside ColorOS's gesture strip — brought
`com.android.settings` and then Digital Wellbeing to the front and left the
device in a compatibility container: **720×1280 at 320 dpi**, `font_scale`
**1.5**, `user_rotation` **1**. I found it, reverted it, and proved the revert:
the app's node bounds are pixel-identical to the first capture (14/14 nodes,
`bounds identical to first capture: True`).

*Not a Jarvis finding* — Jarvis neither caused it nor misbehaved in it. It is
recorded because it is a live hazard for anyone else driving this handset over
adb: **keep `input swipe` start points above y≈1900.** It also produced the one
genuinely useful accident: the app survived the whole episode without a crash
and re-laid itself out at a completely different density.

---

## Device-only answers

### Q1. Dark mode and clipping

**Dark mode renders correctly on every screen reached, and I found no clipped
text.**

- All four screens render on the dark navy surface with light text and the
  accent blue/orange intact: `.evidence/00-launch.png` (pairing),
  `.evidence/C02-checks-top.png` (`CHECKS`), `.evidence/H01-faq-top.png`
  (`FAQ`), `.evidence/S01-security-top.png` (`SECURITY`),
  `.evidence/G01-settings-top.png` (`SETTINGS`).
- **Clipping:** none. Every text node's reported bounds sit inside its card at
  480 dpi, and every long string wraps rather than truncating — checked across
  the 8 scroll positions of `CHECKS` (`transcript-C.txt`) and 35 of `SETTINGS`
  (`transcript-G.txt`). The longest strings on the screen (the `ScreenNever`
  explanation, ~500 characters) wrap to 8 lines without a cut.
- **Landscape** is also clean: the pairing screen and `CHECKS` re-flow with no
  clipping and no crash (`.evidence/11-landscape-pairing-scrolled.png`,
  `.evidence/13-landscape-checks.png`).
- One cosmetic note, not a bug: in landscape `CHECKS`, "Platform checks" sits
  partly past the bottom edge (bounds `[161,949][2358,1080]`) and is reachable
  by scrolling. The screen is a scroll view, so this is expected.

### Q2. App lock and the black frame — **NOT MEASURED**

I did not flip either switch, because I could not undo it. Both are one-way
without the owner: turning `App lock` or `Hide memory lists and chat history`
**on** saves at once, and turning it **off** is a loosening that asks for the
fingerprint or PIN (`SecurityRules.loosens`). The task forbids typing a
credential, so the phone would have been left in a state only the owner could
change, and every later screenshot of Jarvis would have come back black.

What I *can* state, and how:

- **At the settings that were live, `FLAG_SECURE` is absent and `screencap`
  works** — that is the baseline, and every screenshot in `.evidence/` is proof.
- **The mechanism is real and is wired to these two switches.**
  `MainActivity.kt:1018-1031` runs a `LaunchedEffect` on
  `security.appLock, security.privateLists` and calls
  `window.addFlags(FLAG_SECURE)` when true, `clearFlags` when false, keyed on
  `SecurityRules.blockScreenCapture(s, ...)`, which is
  `s.appLock || s.privateLists || keyShown || handoffShown || formPictureShown`.
  So a black frame after either switch is turned on **is** the app's doing, and
  would not be the device's.

**For the owner to check it in about 30 seconds:** `Platform checks` → scroll to
`Security` → `Lock and fingerprint settings` → turn on **"Hide memory lists and
chat history"** → take a screenshot (the frame will be black, or the screenshot
will fail). To undo: the same switch, which asks for the fingerprint or PIN.
Nothing else on the phone changes.

I left that switch **off**, exactly as I found it.

### Q3. What the app says about notifications it cannot deliver

**It says so plainly, in the one place it can, and offers the fix.** The
`Notifications` card on `CHECKS` reads (`.evidence/C02-checks-top.png`):

> **Notifications** — Not allowed, so you are not told about any approval.
> Nothing else looks broken, so this is the only place it shows. Tap Allow
> notifications to fix it.

Its "Technical detail" adds: *"POST_NOTIFICATIONS denied. The ongoing
link-service notification is hidden as well, and appears only in the Task
Manager."* (`.evidence/Kres-Notifications.xml`)

Tapping **Allow notifications** opened Android's own page for Jarvis, headed
"Jarvis", with the **Allow notifications** switch reading **Off**
(`transcript-D.txt`, the `Allow notifications` block). The app does not pretend
it can grant this itself and does not nag elsewhere — the card states outright
that this is the only place the problem shows. That matches the app's own
claim, and I confirmed it: no other screen in the tour mentioned notifications.

### Q4. Does the stale-link gate ever show, and what does it say?

**It never showed, and it could not have.** The gate needs a live link that has
gone quiet; an unpaired phone has no link at all, so the app shows the
"not paired" state instead and the stale path is never entered.

Its exact words are fixed and testable, from `LinkWords.kt`:

- The link word, on Home's status line and on `CHECKS`' Connection card:
  **"Catching up…"**
- A decision refused because the link is stale:
  **"Jarvis is catching up with your PC to make sure it has the latest, so this
  decision waits until then."**
- A decision refused because there is no link:
  **"Not connected to the desktop, so this decision cannot be delivered."**

`CHECKS`' own Deep-sleep card describes the behaviour to the owner: *"If it
does, Jarvis says the link is stale and will not let you approve anything until
it catches up."* (`.evidence/Kres-DeepsleepDoze.xml`) — matching rule 4.

Note what I did **not** verify: that the gate fires correctly in the live case.
That needs a paired phone and a dropped stream.

### Q5. Is the "Never look at" picker visibly slow?

**No.** It opens and fills essentially at once.

- Measured: the picker appeared **within 3.2 s of the tap**, but a bare
  `uiautomator dump` on this device costs **2.33 s** on its own (three runs:
  2.33 / 2.29 / 2.37 s, `transcript-P.txt`), and each polling step also took a
  screenshot. Subtracting the tooling, the picker's own cost is **under about
  half a second**.
- The list is real and populated: search field plus installed apps with an
  **Add** button each (Ad Privacy, Adreno Graphics Drivers, Android
  Accessibility Suite, Android Auto, Android Easter Egg, …),
  `.evidence/S11-look-open.png`, `.evidence/P01-picker-open.png`.
- Opening and closing it changes no setting: **Add an app** → **Close the list**
  leaves the card exactly as it was (`transcript-P.txt`).
- The walk over installed apps is memoised per `neverApps` in the source
  (`LookPlate.kt:116`), so it does not re-run on every keystroke.

Rendering is a `LazyColumn` capped at 240 dp (`LookPlate.kt:138`), so a phone
with hundreds of apps will not build the whole list at once.

### Q6. Crashes — launch, rotation, backgrounding, and returning

**None. Zero `FATAL`, `ANR in`, `SkipDraw` or "Force finishing" in the whole
session.**

| Test | Result | Evidence |
| --- | --- | --- |
| Cold launch after `am force-stop` | pairing screen up in ~6 s, no crash | `transcript-J.txt` §D, `.evidence/J21-cold-launch.png` |
| Launch from the launcher (`monkey`) | worked every time it was used | throughout |
| Rotation, portrait → landscape | re-laid out correctly, no crash | `.evidence/13-landscape-checks.png` |
| Rotation, landscape → portrait | re-laid out correctly, no crash | `.evidence/14-portrait-restored.png` |
| Accidental density change (720×1280 @ 320 dpi) | survived, re-laid out, no crash | `transcript-A.txt` |
| Home, then back to the app | returned to the **same screen** (`CHECKS`), state kept | `transcript-J.txt` §C, `.evidence/J20-return-from-background.png` |
| 6 screens of scrolling, 43 taps | no exception | all transcripts |

The only warnings naming the app are the phone's own, not the app's:
`E/OplusThermalStats: Error getting package info: com.jarvis.client` (OnePlus's
thermal service) and `W/PackageConfigPersister: App-specific configuration not
found for packageName: com.jarvis.client` (ColorOS per-app config). Neither is
from Jarvis and neither is a fault.

---

## What still needs pairing

**12 of the 16 screens**, plus most of the data on the 4 that are reachable.

Unreachable screens (`ui/Nav.kt` `enum class Screen`, and `MainActivity.kt:1846`
which exempts only `CHECKS`, `FAQ`, `SECURITY`, `SETTINGS` from the pairing
takeover):

1. `HOME` — the face, the talk button, Retry, "Earlier chats"
2. `BRAIN`
3. `INBOX` — approvals
4. `APPEARANCE` — faces, animal options
5. `VOICE` — "Train my voice"
6. `VOICE_CHECK`
7. `VOICES` — "Jarvis's voice"
8. `HISTORY`
9. `LIVE` — Jarvis Live
10. `HANDOFF` — "Solve it here"
11. `APPROVALS` — past approvals
12. `FEATURES` — "Everything Jarvis can do"

Data that is on a reachable screen but still waiting for the desktop:

| Where | What it shows unpaired |
| --- | --- |
| `CHECKS` → Connection | "Not paired", Desktop "Not set" |
| `CHECKS` → Your voice | "Unknown — Your PC has not answered yet, so this is not known." |
| `CHECKS` → Wake word | "Unknown — The desktop has not answered, so this is not known." |
| `CHECKS` → Link service | "No problems starting the connection so far." (meaningless with nothing to connect to) |
| `CHECKS` → Frame rate | "Face (last measured): —" — "The face has not been drawn since the app started." |
| `SETTINGS` → Voice | "Pair with your desktop first - these settings live on it." |
| `SETTINGS` → Security | "Off. Your fingerprint or PIN is asked for risky approvals only." |
| `SETTINGS` → every jump-chip section | shows its own "pair first" line |

This is the honest split the brief asked for: **the phone showed these**, the
**backend did none of them**. The `CHECKS` screen is unusually good at saying
which is which — "Your PC has not answered yet" is exactly the right sentence.

One thing the phone *did* do over the network, unpaired: **the update check
reached GitHub** — "Build 2f925c1", "Up to date, as of 29 min ago."
(`transcript-1.txt` line 243). That is the documented behaviour in
`FaqScreen.kt` ("Jarvis asks GitHub, at most every six hours... The question to
GitHub carries nothing about you or Jarvis").

---

## Device state, and what was put back

Everything below was verified after the run.

| Setting | At the start | Now | Restored by me? |
| --- | --- | --- | --- |
| `system font_scale` | 1.0 | 1.0 | yes — it drifted to 1.5, set back |
| `secure display_density_forced` | unset | unset | yes — it was set to 320, cleared |
| `global display_size_forced` | unset | unset | n/a — never changed |
| `system user_rotation` | 0 | 0 | yes |
| `system accelerometer_rotation` | 0 | 0 | yes |
| `wm size` / `wm density` | 1080×2412 / 480 | 1080×2412 / 480 | n/a |
| App "Check for new versions" | on | on | yes — my tap turned it off, I turned it back on |
| Pairing | unpaired | unpaired | n/a — never paired |
| Approvals | none | none | n/a — never approved |
| App data / install | — | — | never cleared, never uninstalled |

The layout check that proves it: the pairing screen's UI dump after the run is
**pixel-identical in every node bound** to the dump taken before anything was
touched (14 of 14 nodes, same `text` and same `bounds`).

---

## Evidence index

All screenshots, UI dumps and transcripts are untracked, under
`.dsh-scratch/device-tour/.evidence/` in the `audit/android-tour` worktree.
266 PNGs, 266 UI dumps, 11 transcripts.

| File | What it is |
| --- | --- |
| `00-launch.png`, `00-launch.xml` | the pairing screen, first capture, and the bounds baseline |
| `01-checks.png`, `C02-checks-top.png` | `CHECKS`, top — Connection, Settings, Desktop address, Notifications |
| `C03-checks-s00…s07.png` | `CHECKS` scrolled end to end (Background restart, Your voice, Wake word, Security, Microphone, Running in the background, Link service, Digital assistant, Deep sleep, Frame rate, This app) |
| `13-landscape-checks.png` | `CHECKS` in landscape |
| `14-portrait-restored.png` | portrait after restore |
| `H01-faq-top.png`, `H02-faq-s00…s03.png` | `FAQ` end to end |
| `S01-security-top.png`, `S02-security-s00…s05.png` | `SECURITY` end to end |
| `S10-look-section.png`, `S11-look-open.png`, `P01-picker-open.png` | the "Never look at" picker, open |
| `G01-settings-top.png`, `G02-settings-s00…s34.png` | `SETTINGS` end to end |
| `J20-return-from-background.png`, `J21-cold-launch.png` | backgrounding and cold launch |
| `transcript-1.txt` | the first full scroll of `CHECKS`, and the union of every control on it |
| `transcript-C.txt` | `CHECKS`: every control, every scroll position |
| `transcript-D.txt` | the per-control tap sweep, with before/after signatures |
| `transcript-J.txt` | 20 jump chips, the two silent buttons, background, cold launch |
| `transcript-K.txt` | all six "Technical detail" expanders |
| `transcript-S.txt`, `transcript-P.txt` | `SECURITY` + the picker timing |
| `transcript-G.txt`, `transcript-H.txt` | `SETTINGS`; `FAQ` open/close |
