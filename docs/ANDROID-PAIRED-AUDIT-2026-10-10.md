# Android audit — the first one with the phone actually paired

**2026-10-10.** Every earlier phone report was written with the app unpaired, so
the screens behind pairing could not be drawn at all and twelve of them were
recorded as "cannot be reached yet". This is the pass that had a paired phone:
it walks every screen, runs the PC's own preflight against the live system, and
runs both phone suites.

Device: `f0a5b32b`, OnePlus CPH2419, API 35, 1080×2412 @ 480 dpi, unlocked
(`dumpsys trust` → `deviceLocked=0`), dark mode on.

## What changed after this audit

**This document is the record of one night, 2026-10-10.** Four pull requests
have merged since, and two of the findings below turned out to be wrong. This
section says what moved and how each change was checked. The body is left as it
was measured that night, with a short marker wherever it now misleads a reader.

| Change | What it touched | Evidence |
|---|---|---|
| #202 — the settings search index quoted a sentence the app had stopped saying | phone app only | merge `f44b7950` |
| #203 — a connected test run no longer uninstalls the app (and the pairing) | phone build file + a new test | merge `0aa6150d` |
| #210 — the approval widget keeps its buttons on screen after it grows | desktop app only | commit `43c8f978` |
| #211 — "Name this device" never left the phone | phone app only | commit `f047391e` |
| §6 Finding B was wrong — there is nothing to fix on `main` | this document | `git grep` on `origin/main` |
| §2's one FAIL is tree-dependent, and is unresolved | the owner's call | measured against the installed folder |

### #202: a Settings search pointed at a sentence the app no longer says

Android app only, and **nothing on any screen changed**. The app keeps a *search
index* — a list of phrases its Settings search box matches against, so a search
can find a setting without drawing its screen. One entry quoted the old wording
"Turning something up asks you on the PC first, and nothing changes until you
answer "; it now reads "Changing something here may take effect at once or ask
you on the PC first, and " + "nothing changes until you answer there."
(`jarvis-client/app/src/main/java/com/jarvis/client/ui/SettingsSearch.kt:245-246`).
The old sentence survives in exactly one place on `main`, as a fixture inside
`SettingsSearchTest.kt:168-170`.

Merge `f44b7950`, branch `fix/settings-search-index`, merged
2026-10-10T00:27:59-07:00 (07:27:59Z). `SettingsSearch.kt` +11/-1 and its test
+37/-1 (`git show --numstat f44b7950`).

### #203: a connected test run no longer uninstalls the app

This is the fix for §6 Finding A below. `jarvis-client/gradle.properties:15` now
reads `android.injected.androidTest.leaveApksInstalledAfterRun=true`, under a
comment block (lines 9-14) that names this audit document. The new test
`jarvis-client/app/src/test/java/com/jarvis/client/InstrumentedRunKeepsInstallTest.kt`
(+58 lines) reads that file and asserts the line equals exactly
`android.injected.androidTest.leaveApksInstalledAfterRun=true` and does not start
with `#` — its own words are "A commented-out copy is not the setting". So
deleting the line, or commenting it out, fails CI.

Merge `0aa6150d`, branch `chore/leave-apks-after-test`, merged
2026-10-10T00:55:10-07:00 (07:55:10Z).

### #210: the widget keeps its buttons on screen

Desktop app only: `jarvis-desktop/src-tauri/src/windows.rs` (+112/-1), no other
file. It closes §1's desktop finding. When an approval card makes the widget
taller, on a scaled display the window also grows physically wider — and nothing
pulled it back inside the monitor afterwards, so the right-most button, Approve,
was the part clipped off. That is the owner's "there was only a deny button".

`resize_widget` (`windows.rs:1026`) now ends by calling
`keep_widget_on_screen(&window)` (`windows.rs:1045`); `keep_widget_on_screen` is
at 1062, and its arithmetic, `clamp_into`, at 1104. The new doc-comment
(`windows.rs:1048-1057`) names the owner's complaint and the geometry: a 480x507
physical window at x=1509 on a 1920x1080 monitor at 150%, 69px past the right
edge. A unit test at `windows.rs:1115-1123` asserts
`clamp_into((1509, 744), (480, 507), (0, 0, 1920, 1080)) == (1440, 573)`.

Commit `43c8f978` (2026-10-10T01:38:38-07:00), merged by `49881475`.

### #211: "Name this device" never left the phone — §3 was wrong

The audit's §3 says the failed rename was "not the app's fault" and that the
app's wording "already tells the owner exactly that, which is the behaviour this
audit wanted to see". **That is wrong. The fault was in the app.**

Every device change goes through one function, `devicesPost`, and it refused
anything that was not on a hardcoded pair of routes. Before #211 that line read
`if (path != Devices.REMOVE_PATH && path != Devices.SHARED_PATH)`
(`git show f047391e^:jarvis-client/app/src/main/java/com/jarvis/client/net/JarvisApi.kt`);
the label route, `LABEL_PATH`, added later, was never put on it. So `renameDevice`
was refused **inside the phone**, with "not a devices route" — nothing was ever
sent to the PC. That internal refusal reached the owner as app wording: a
"malformed" answer maps to "Your PC answered in a way this app can't read."
(`PlainErrors.kt:217` does the mapping; the sentence is at `PlainErrors.kt:118`),
which sent him to run `apply-patches.ps1` against a PC that was already up to
date.

On `main` today the allowed routes live in one list —
`val POST_PATHS: Set<String> = setOf(REMOVE_PATH, LABEL_PATH, SHARED_PATH)`
(`jarvis-client/app/src/main/java/com/jarvis/client/net/Devices.kt:42`) — and the
guard is `if (path !in Devices.POST_PATHS)`
(`.../net/JarvisApi.kt:677`). A new test,
`jarvis-client/app/src/test/java/com/jarvis/client/DevicesRoutesTest.kt` (+69),
fails if a route is missing from that list or if the sender stops reading it.

#211's own commit message says it was verified against the live backend:
`POST /api/devices/label` answered 200, the label persisted, and 2,077 unit tests
passed with 0 failures. **What cannot be checked from this repository:** whether
that PC's install still 404s the route, and whether the audit's 404 row was
itself caused by the old installed copy rather than by the app.

Commit `f047391e` (2026-10-10T01:38:41-07:00). **#210 and #211 were merged by the
same merge commit, `49881475`** — its title names only #211's branch, so a reader
should not read that as #210 having gone in unmerged.

The route was in the repository all along: `def label(body, *, you)` at
`backend/jarvis_devices.py:1858`, with its docstring on the next line, 1859 (the
audit's index cites 1858 for the docstring, which is the `def` line itself).

### §6 Finding B was wrong: there was nothing to fix on `main`

Verified by reading `origin/main` read-only (`git grep`):

- **Neither pattern the audit names appears in `backend/test_apply_outcomes.py`
  on `main`.** `git grep -n "undoFirst" -- .` matches only this document's own §6
  table, and real uses inside `scripts/apply-patches.ps1` (lines 3115, 3647,
  3752, 3781, 3803, 3826, 3829). `git grep -n -- "acc -contains"` matches only
  this document's §6 table.
- **Both patterns live in commit `9719790a`** ("the installer can no longer
  reverse a patch off the owner's PC and certify it"), **and in the uncommitted
  working-tree changes of the owner's own checkout.** That dirty tree is the
  environment this audit's suite run was really measured in: its HEAD,
  `9a315915`, is 105 commits behind, `git status` shows
  `M backend/test_apply_outcomes.py`, and that file's working-tree copy holds the
  two patterns at lines 1231 and 1248. The commit is on no remote branch. (A
  remote branch *named* `origin/fix/installer-undo-first` does exist, but it
  points at a different, earlier commit, `364f7043`, which is an ancestor of
  `main` and contains neither check.)
- **They are not "stale by drift" in the way §6's table says.**
  `scripts/apply-patches.ps1:3217` on `main` is an unrelated comment; the real
  `$undoFirst` assignment is at 3647.
- **§6's reason for the first failure is itself wrong.** That check's own pattern
  is `^\s*\$undoFirst = ([^\n]*\$found.*?\n\s*\}\)\s*)$`, searched with
  `re.M | re.S`. Run against `main`'s script it **matches**, capturing
  `@($found | Where-Object { -not (@($alreadyOn | ...) -contains $_.Name) })`.
  It matches because `$found` sits on the same line as `$undoFirst = ` (3647),
  so the `[^\n]*` prefix is satisfied there and the `.*?` spans the newline to
  the closing `})` on 3649. So check 1 would PASS on `main`; it fails only
  against the dirty checkout's OLD script, whose `$undoFirst = $found` is a
  single line with no `})` to close on.
- **`$acc` never existed on `main` at all.** `git log -S'$acc' origin/main` is
  empty. `9719790a`'s own change renamed `$Accept` to `$acc` in the same commit
  that added the check, so the check tests a refactor local to that uncommitted
  work — not a branch `main` lost. On `main` that branch is still
  `if ($Accept -contains $nm) {` (3166).
- **That pairing reproduces the number this audit reported.** Run `9719790a`'s
  test file against the dirty checkout's old script — which is exactly what that
  checkout is — and BOTH checks fail: row 1 has no `})` to match, row 2 has no
  `$acc`. That is "108 passed, 2 failed". The commit §6 blames for passing in CI,
  `9f7de92b`, is an ancestor of `main` and contains neither check, so CI could not
  have produced those two failures either.
- **The `$acc` branch was not lost, and `main` fixed the underlying bug earlier
  and by another route.** `main` does the same job inline at
  `scripts/apply-patches.ps1:3647-3649`, with `$undoFirst = @($found |
  Where-Object { -not (@($alreadyOn | ForEach-Object { $_.Name }) -contains
  $_.Name) })`. The comment block directly above it (3636-3646) names the real
  incident it came from: the run of 2026-10-09 09:40, which switched
  `tutorials.patch` and `screen-attach.patch` off while reporting every patch as
  on. That landed in commit `ba344211` ("the installer stops switching off a
  patch it answered 'already on'") some 85 minutes *before* `9719790a`, which
  re-derived the same fix without having seen it.
- **`main` already covers that behaviour with real, behavioural tests:**
  `t_already_on_is_proved_by_the_patchs_own_bytes`
  (`backend/test_apply_outcomes.py:1306`),
  `t_a_shifted_stack_is_still_recognised_as_on` (1344) and
  `t_a_patch_answered_already_on_is_never_reversed_off` (1451).

So the honest reading: on `main` there is nothing to fix here. The two failing
checks were never on `main` — they were measured in a dirty checkout that paired
an unmerged commit's test file with a pre-fix script, and `main` had already
fixed the underlying bug earlier, by another route, and covered it with a
behavioural test that is strictly better than reading the script's text. The
audit's sentence "It passes in CI's `backend-windows` job on the same commit, so
the difference is in this environment as well" is replaced by that explanation.

Worth one sentence, because the shape recurs: CI does have a guard for the
general class — `tools/check_vacuous_checks.py`, run by
`.github/workflows/ci.yml:1454`, "No suite check can pass while checking
nothing" — but it only catches a literal `True` condition, a string used as the
condition, and a harness whose condition has a default. It does **not** catch a
pattern that can never match the file it reads, which is the shape of the two
checks above.

### §2's one FAIL is tree-dependent, and is not resolved

The check is `pf_modules` in `backend/selftest.py` (1331-1357). Its comparison is
`theirs, ours = live.backend / leaf, HERE / rel` (line 1343), where `HERE` is the
directory `selftest.py` itself is sitting in (`backend/selftest.py:82`). So it
compares the **installed** backend against the copy in whichever checkout the
check is run from — never against the install's own history. Run from two
different checkouts, it gives two different answers about the same install.

Measured against the same installed folder, using the check's own rule (`_sha`,
`selftest.py:949-951`: sha256 of the bytes with CRLF folded to LF):

- From the owner's checkout: **10 FAIL rows**, all "text differs"
  (`jarvis_settings_registry.py`, `jarvis_owner_check.py`, `jarvis_card_words.py`,
  `jarvis_asks_first.py`, `jarvis_tutorials.py`, `jarvis_chatbot_routes.py`,
  `jarvis_devices.py`, `jarvis_menus.py`, `jarvis_limits.py`,
  `jarvis_prompt_coach.py`).
- From a tree at `origin/main`: **7 FAIL rows** — 6 whose text differs
  (`jarvis_framework.py`, `jarvis_voice.py`, `jarvis_voice_enroll.py`,
  `jarvis_settings_registry.py`, `jarvis_asks_first.py`, `jarvis_limits.py`) plus
  `jarvis_plugins.py`, which is not in the install at all.
- The file list differs too: `_where.SHIPPED` on `origin/main` holds **181**
  entries (180 `.py` files plus `jarvis_hud.html`) against **178** in the owner's
  checkout. The preflight's own summary line agrees with the larger number:
  `PASS  174 of 181 shipped modules are identical to this repository's copies`.

So the FAIL cannot be made to pass while the two checkouts disagree — a fix in
one tree makes it wrong in the other.

About the pair of hashes §2 prints (`1af5e181` there, `9780d919` here): neither
string appears in the repository as text, but both can be re-derived from what is
on this PC. `9780d919` is the sha256 of the owner's checkout's own
`backend/jarvis_settings_registry.py` — the "here" half. `1af5e181` is the copy
the installer **replaced** at 2026-10-09 21:45: it is still on disk in the
installed folder, at
`_jarvis-backup-2026-10-09-214407\jarvis_settings_registry.py`, and hashes
`1af5e1810500…`. So the "there" half is the pre-replacement copy — one install
out of date, not a mystery. The installed copy right now hashes `ad261b09…`,
which is neither value and is not `origin/main`'s copy either, so the FAIL line as
printed in §2 can no longer be reproduced; run from `origin/main` today, the same
check would print `(ad261b09 there, a3924ce0 here)` for that module.

Still unresolved: §7 item 1 says the install was brought up to date while §2
still shows the old FAIL, and there is no post-patch preflight output anywhere to
settle it.

**This is written up, and it is the owner's decision.** What that check should
compare against — the record `apply-patches.ps1` writes beside the backend, the
published `jarvis-backend/` snapshot, or the checkout — is laid out with its
measurements and trade-offs in `docs/PREFLIGHT-MODULE-COMPARISON-DECISION.md`.
The owner chose the installer's own record on 2026-10-10; the code change that
follows from that is its own pull request, not this one.

### What this refresh did not re-verify

This refresh read the repository and the files already on this PC. It ran no
preflight, no test suite and no `adb`, and it touched no phone. So these stay
exactly as the audit left them:

- **§1's pairing observations** — the three cards, the two timeouts, the
  180-second card life. They happened on the phone and the PC that night.
- **Whether quiet hours are on right now** (§5, and §7 item 3) — live-PC state.
  The switch itself is real and on `main`: settings row `notif-quiet-enabled`
  (`backend/jarvis_settings_registry.py:1031-1043`, title "Turn on quiet hours",
  owner `desktop`), its desktop control at
  `jarvis-desktop/src/settings.html:1133`, and the phone row it gates,
  `quiet_enabled` (`backend/jarvis_limits.py:447`).
- **Whether desktop build 0.2.115 is installed** — live-PC state, and see §7 item
  2: `0.2.115` appears only in this audit, the repository's own version is
  `0.2.0`, and `gh release view desktop-latest` answers "release not found".
- **The phone's pairing state and device list** (§1, §7 item 4) — needs the
  phone.
- **Every test-battery number in §6** — the 46 instrumented tests, the 2,053
  phone unit tests, the 28,619 / 92 / 44 backend figures and the two green CI
  runs. No suite was run for this refresh.
- **What the preflight itself now reports.** The hashes above were re-derived by
  hashing the files on disk, not by running the check.

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

*(Superseded — fixed by #210; see "What changed after this audit".)*

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

*(Partly superseded — this FAIL depends on which checkout the check is run from,
and the two hashes are now explained; see "What changed after this audit".)*

The 5 skips are things genuinely not set up on this PC (calendar, email, Home
Assistant, the email watch) and the 4 warns are things switched off or not
installed; each names itself in the output.

## 3. "Name this device…" cannot work against this install — and the app says so

*(Overturned — the fault was in the app; see "What changed after this audit".)*

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

*(Wrong — this was an app fault, fixed by #211; see "What changed after this
audit".)*

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

*(Line numbers moved, and the conclusion still holds — the gate is now
`LimitsPlate.kt:247`, the sentence shown instead of the button is
`Limits.TIME_QUIET_OFF` at `Limits.kt:117-119`, and the picker is
`TimePicker(state = state)` at `LimitsPlate.kt:313` inside `TimeRowDialog` at 295;
see "What changed after this audit".)*

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

*(Fixed by #203 — the property is now set in `gradle.properties` and pinned by a
test; see "What changed after this audit".)*

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

*(Wrong — both rows of that table are wrong, and the "It passes in CI" sentence is
replaced by the explanation in "What changed after this audit".)*

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
   **Status, 2026-10-10 refresh: NOT re-verified.** It is a statement about the
   owner's PC, and no post-patch preflight output exists anywhere. The installed
   copy of `jarvis_settings_registry.py` now hashes `ad261b09…` — not the pair §2
   prints and not `origin/main`'s copy either — and the module FAIL is
   tree-dependent (see "What changed after this audit").
2. **Install the desktop build `0.2.115`** (artifact `jarvis-desktop-0.2.115`,
   or the release that the workflow publishes once the signing key exists). The
   installed app is still `0.2.0` from 9 Oct 14:08 — four hours *before* PR #177
   rewrote the widget's layout and Approve target, which is very likely the
   cropped "only a deny button" card the owner hit. Use the **NSIS `setup.exe`**
   (`asInvoker`, per-user); the MSI is per-machine and fails with `1925`
   without admin on this machine.
   **Status: NOT re-verified, and the number needs care.** `0.2.115` appears only
   in this audit; the repository's own desktop version is `0.2.0` in all four
   places (`VERSION`, `jarvis-desktop/package.json`,
   `jarvis-desktop/src-tauri/tauri.conf.json`,
   `jarvis-desktop/src-tauri/Cargo.toml`). Rolling builds are named
   `0.2.<run number>` by `.github/workflows/desktop-release.yml` (lines 49-53,
   126, 219), so `0.2.115` would be run 115 of that workflow — and no such
   release is published (`gh release view desktop-latest` answers "release not
   found"). That workflow currently publishes nothing: `tauri.conf.json` has
   `"createUpdaterArtifacts": false` and `"pubkey": ""`, and the workflow's own
   rule (lines 130-133) says nothing is signed or published until the signing key
   is added, which matches this item's "once the signing key exists". Whether
   `0.2.115` is *installed* on this PC cannot be determined from the repository.
3. **Turn on "Be quiet during quiet hours" on the PC** if #170's time picker is
   to be seen; the two clock rows appear in Limits the moment it is on.
   **Status: NOT re-verified.** The switch is real and on `main`: settings row
   `notif-quiet-enabled` (`backend/jarvis_settings_registry.py:1031-1043`, title
   "Turn on quiet hours", owner `desktop`), its desktop control at
   `jarvis-desktop/src/settings.html:1133`, and the phone row it gates,
   `quiet_enabled` (`backend/jarvis_limits.py:447`). Whether it is ON right now
   is live-PC state.
4. **Re-pair the phone** — it is on the pairing screen because the instrumented
   run uninstalled the app (Finding A). The old device record
   (`dbe6473b6`, "OnePlus") is still in the PC's list and can be removed from
   `Settings → Devices` once the new pairing lands.
   **Status: NOT re-verified** — it needs the live phone, and this refresh ran no
   `adb` and touched no phone. Note that #203 has now removed the cause this item
   names.

## Evidence index

| What | Where |
|---|---|
| Screenshots of the paired sweep | `docs/android-paired-2026-10-10/` |
| Full preflight output | this document, §2 (the failure and the phone block quoted verbatim) |
| The label route in this repository | `backend/jarvis_devices.py:1859` (the docstring; 1858 is the `def label(...)` line) |
| The picker and its row kind | `jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/LimitsPlate.kt:295` (the `TimeRowDialog`; the `TimePicker` is at 313), `.../net/Limits.kt:70` (`PATH`) and `74-75` (the `TIME` comment) |
| The app's own wording after a failed rename | `jarvis-client/app/src/main/java/com/jarvis/client/net/PlainErrors.kt:118` (the "unreadable" sentence; a "malformed" answer maps to it at 217) |
| What changed after this audit | this document, the section above §1 |
