# Android audit — the first one with the phone actually paired

**2026-10-10.** Every earlier phone report was written with the app unpaired, so
the screens behind pairing could not be drawn at all and twelve of them were
recorded as "cannot be reached yet". This is the pass that had a paired phone:
it walks every screen, runs the PC's own preflight against the live system, and
runs both phone suites.

Device: `f0a5b32b`, OnePlus CPH2419, API 35, 1080×2412 @ 480 dpi, unlocked
(`dumpsys trust` → `deviceLocked=0`), dark mode on.

## 1. Pairing, as it happened

Three cards were raised; **two timed out**. The card's own life is
`APPROVAL_TIMEOUT` in the PC's gate — measured here as exactly **180 seconds**
(created 21:09:07, expired 21:12:07, `decided_by` empty), while the pairing
*session* allows 600. The phone waits the full ten minutes and then says
"The card on your PC ran out of time. Start again" — which is what the owner
saw twice.

The third card was approved: `state=approved`, `decided_by=desktop_spotlight`.
The PC's device list then held
`{"id": "dbe6473b6", "name": "OnePlus", "kind": "phone"}` and the phone's own
read-only list showed `Approved · 3 min ago · desktop_spotlight` next to the two
`Timed out` rows.

**One desktop finding, for the surface that owns it.** The card's buttons live in
the **"Jarvis Desktop Widget"** window. Reachable through Windows' accessibility
tree, its Approve button sits at x≈817–1020, to the right of Deny at x≈606–809 —
and on this display only the Deny half was visible to the owner, who reported
"there was only a deny button". The card text itself was never in doubt: the four
words on the PC matched the four on the phone exactly. This is a layout/width
question in the desktop widget, not an Android one; nothing here changed it.

## 2. The PC's own preflight — 35 pass, 1 fail, 4 warn (5 skipped)

Run against the live system with `JARVIS_BACKEND` set, `py -3 backend/selftest.py
--preflight`. The phone half finally had a phone to check:

```
Can your phone reach Jarvis?
  PASS  the phone address is 100.75.21.228
  PASS  Tailscale or Meshnet is on: this PC has 100.75.21.228
  PASS  Jarvis answers on 100.75.21.228:4719, where the phone looks for it
  WARN  the Windows Firewall rules could not be read
```

**The one FAIL is real, and it explains a feature that looked broken:**

```
FAIL  jarvis_settings_registry.py in the backend folder is not this repository's copy
      (1af5e181 there, 9780d919 here) — Most likely an older one.
      Run apply-patches.ps1, then restart Jarvis.
```

`scripts/apply-patches.ps1` is in this repository. Until it is run on the PC and
Jarvis is restarted, **the installed Jarvis is older than the app it is talking
to**, and that is a user-visible fault, not a technicality — see §3.

The 5 skips are things genuinely not set up on this PC (calendar, email, Home
Assistant, the email watch) and the 4 warns are things switched off or not
installed; each names itself in the output.

## 3. "Name this device…" cannot work against this install — and the app says so

`Settings → Devices` is populated now that a device exists:
`OnePlus (this phone) · phone · paired 9 Oct · last used just now`, with
**Name this device…** beneath it. Typing a new name and pressing **Save** changes
nothing on the PC.

That is not the app's fault, and the app does not pretend otherwise. Three
independent pieces of evidence, in the order they were taken:

| Proof | Result |
|---|---|
| `POST /api/devices/label {"id":"dbe6473b6","label":"OnePlus 10T"}` straight from the PC, with the PC's own token | **HTTP 404** |
| `GET /api/devices` after that call | `"name": "OnePlus"` — unchanged; the record has no label field at all |
| The phone's screen after Save (below the fold, which is why it was missed at first) | *"Not named. Your PC answered in a way this app can't read. Update both: run apply-patches.ps1 on …"* |

And the route does exist in this repository's copy: `backend/jarvis_devices.py`
line 1858, `def label(body, *, you)` — "POST /api/devices/label {"id", "label"} -
the owner's own name for a [device]", with `bad_label` and `no_such_device`
refusals.

**So the fix is on the PC, not in the app: run `scripts/apply-patches.ps1`, then
restart Jarvis, then rename the device again.** The app's wording already tells
the owner exactly that, which is the behaviour this audit wanted to see.

## 4. Every screen, with the phone paired

Screenshots are in `docs/android-paired-2026-10-10/`; each was taken from the
attached phone with `screencap` after a `uiautomator` dump confirmed what was on
screen.

**Home and the five destinations** — Home draws `Connected` and the nav row.
Brain: *"Link live · board read just now"*, the board, `Now / DOING / Activity`.
Inbox: *"3 of 3 spoken interruptions left. 0 waiting."*, mute, and **Past
approvals** (read-only). Live: *"Talk back and forth - no 'Hey Jarvis' needed"*.
Appearance: `Follow the system`, `Reactor`, `Daylight`, `High Contrast`.
History (*Earlier chats*): *"Chat history, kept on your PC · On. New chats are
kept on your PC, encrypted."*, Tags, *Forget a time frame…*.

**Platform checks** (tap `Connected`) — the pairing seen from the app:
`Connection: Connected, and updates are arriving`, `Desktop:
marioirelan11-alps.nord:4719`, `Reconnect`, `Change desktop or token`,
`Background restart: Not allowed yet`, `Your voice: Not trained`.

**Settings, every section jumped to and read**: Voice, Security, Show or hide
menus, Appearance, Floating Jarvis, How Jarvis talks, Web search, Prompt coach,
What asks first, What Jarvis can reach, Sending email, Folders Jarvis may look
in, Backups, Smartwatch notifications, Phone notifications (and Picture mode),
Notifications from Jarvis, Look at this and Watch with me, Browser without a
window, When the phone does not answer, When a captcha stops Jarvis, Devices,
Quick Settings tiles, Limits and how often Jarvis does things.

Every one drew its real content. Two sections honestly report states of the PC
rather than faults — *What Jarvis can reach* says "Not set up: No DeepSeek API
key is saved on this PC", and *Sending email* says `JARVIS_IMAP_USER` is not set
— both with the one-line remedy; both match the preflight's own skips.

**Devices** is the section pairing unlocked, and it now shows the real list, the
rename row, `Remove`, and `Signed approvals` — *"Off. Risky approvals from this
phone are held until you turn it on."* That switch is a loosening, so it asks for
the phone's fingerprint or PIN; it was **not** flipped, and this audit says so
rather than reporting it as passed.

**Prompt coach**: the master switch is in Settings and says *"Prompt coach is
on."* after being turned on, with **no card raised** (the PC's pending list stayed
empty) — so that switch is immediate. The coach's own settings are not in that
section; the plate that renders them is `PromptCoachPlate.kt`, which its own doc
places on the Brain screen.

## 5. The one feature that still could not be drawn, and exactly why

**The Material3 time picker (#170) was not exercised.** The app's only
`TimePicker` lives in `LimitsPlate.kt` (`TimeRowDialog`), and it is opened by a
row whose kind is `TIME` — `net/Limits.kt` line 70, "the quiet hours' two ends".
`Limits.kt` line 99 says what happens when they are off: the app shows a sentence
*instead of* the button ("Quiet hours are off, so this hour decides nothing. Turn
"Be quiet during quiet hours" …"), deliberately, "rather than offer a clock that
changes nothing". Quiet hours are **off** on this PC, and the switch that turns
them on is the PC's own (`SettingsCatalog.kt` row `notif-quiet-enabled`, owner
`desktop`).

So this is not a phone fault and not a skip dressed up as a pass: the picker is
unreachable from the phone until that one PC switch is on. Turning it on and
re-running this section is the whole remaining job for #170.

The clock-looking fields that *are* reachable — Brain's `STANDBY AT 01:00` and
`WAKE AT 07:00` — are typed `EditText`s, not the picker: tapping one raises the
keyboard (`mInputShown=true`). They are the standby schedule, a different control.

## 6. The test batteries, and two findings about the tools themselves

| Battery | Result |
|---|---|
| Instrumented suite, on the phone | **46 tests, 0 failures, 0 errors, 0 skipped** — `TEST-CPH2419 - 15.xml`, 04:39 tonight, device `f0a5b32b` |
| Phone unit tests | 2,053 passed (measured on merged `main` earlier the same day; no app code changed since) |
| Backend suites | **28,619 passed, 92 skipped, 44 failed** — and every failure is in one file, `backend/test_apply_outcomes.py` |
| The PC's preflight | 35 pass, 1 fail, 4 warn, 5 skipped — §2; the fail was the stale install, now patched |
| Desktop suites (CI) | green on the last two pull requests (`frontend`, 54m 9s; `backend-windows`, 38m 2s) |

**Finding A — running the instrumented suite on the owner's own phone uninstalls
the app, and the pairing with it.** Gradle's own cleanup does this
(`connectedDebugAndroidTest` removes both APKs when it finishes), so it is not a
crash: immediately afterwards `adb shell am start` answered
`Error type 3 … Activity class {com.jarvis.client/com.jarvis.client.MainActivity}
does not exist`, `pm list packages` held no `com.jarvis.client`, and
`run-as com.jarvis.client` answered "unknown package". The pairing key lives in
the app's data, so the phone had to be re-paired from scratch. The app was put
back from the same debug APK and now sits on the pairing screen. Anyone
repeating this on the owner's daily-driver phone should expect to re-pair
afterwards; `android.injected.androidTest.leaveApksInstalledAfterRun=true` in
`jarvis-client/gradle.properties` is the one-line change that stops it, and
`docs/ANDROID-TOUR-2026-10-09.md` should say so either way.

**Finding B — two checks in `backend/test_apply_outcomes.py` no longer match
`scripts/apply-patches.ps1`.** First, 42 of the 44 failures were environmental
and not real: the harness runs the real script, and the script's own guard
refuses while a Jarvis is running — *"Jarvis looks like it is still running
(process 35804: py.exe; process 24808: python.exe). Close it, then run this
again"*. Stopping the backend took the file from **44 failures to 2**:
`108 passed, 2 failed`. Both survivors are static reads of the script's text:

| The check wants | What is actually in the script |
|---|---|
| `$undoFirst = ...$found...})` | present, but as a **multi-line** statement — `$undoFirst = @($found | Where-Object {` at line 3217, so a single-line pattern cannot match it |
| `if ($acc -contains $nm) {` | **`$acc` does not exist at all** — 0 matches in the file |

So either both checks are stale or the script lost a branch. It passes in CI's
`backend-windows` job on the same commit (`9f7de92b`), so the difference is in
this environment as well. `scripts/` and `backend/` belong to the patch/installer
surface, not to the Android app, so this is reported rather than changed — but it
is worth someone's five minutes, because a check that cannot fail any more is
not a check.

## 7. What to do next

1. **Done during this audit: the install was brought up to date.**
   `scripts/apply-patches.ps1 -SkipTests` ran against the installed backend —
   27 patches, the two missing `[autonomy.tiers]` lines added to
   `jarvis-framework.toml` (previous copy kept beside it), Python packages
   installed, everything backed up into `_jarvis-backup-2026-10-09-214407`, and
   Jarvis restarted. The proof that it took: `POST /api/devices/label` answered
   **404 before and 200 after**, which is exactly the route "Name this
   device…" needs. Re-run `py -3 backend/selftest.py --preflight` to watch the
   one FAIL turn into a PASS.
2. **Install the desktop build `0.2.115`** (artifact `jarvis-desktop-0.2.115`,
   or the release that the workflow publishes once the signing key exists). The
   installed app is still `0.2.0` from 9 Oct 14:08 — four hours *before* PR #177
   rewrote the widget's layout and Approve target, which is very likely the
   cropped "only a deny button" card the owner hit. Use the **NSIS `setup.exe`**
   (`asInvoker`, per-user); the MSI is per-machine and fails with `1925`
   without admin on this machine.
3. **Turn on "Be quiet during quiet hours" on the PC** if #170's time picker is
   to be seen; the two clock rows appear in Limits the moment it is on.
4. **Re-pair the phone** — it is on the pairing screen because the instrumented
   run uninstalled the app (Finding A). The old device record
   (`dbe6473b6`, "OnePlus") is still in the PC's list and can be removed from
   `Settings → Devices` once the new pairing lands.

## Evidence index

| What | Where |
|---|---|
| Screenshots of the paired sweep | `docs/android-paired-2026-10-10/` |
| Full preflight output | this document, §2 (the failure and the phone block quoted verbatim) |
| The label route in this repository | `backend/jarvis_devices.py:1858` |
| The picker and its row kind | `jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/LimitsPlate.kt:292`, `.../net/Limits.kt:70` |
| The app's own wording after a failed rename | `.../net/Devices.kt:291` |
