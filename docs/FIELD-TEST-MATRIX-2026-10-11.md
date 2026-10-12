# Field-test matrix - what has actually run on the owner's own devices

**Written 2026-10-11. Checkout `.dsh-scratch/field-matrix` (branch `docs/field-test-matrix`) off `origin/main` `70077268`.**

The owner asked: *"are there any features that haven't been field tested on the real world jarvis android app or desktop app? Or conversation driven features that haven't been? I want thorough testing on everything."*

`features/features.json` holds **127 features in 9 groups and has no `tested`, `verified` or `status` field at all** - so this document cannot be read from a file. Every verdict below was built from a dated artifact, and every row names the one it came from.

## The counts

| verdict | features |
|---|---|
| FIELD-TESTED | **82** |
| TEST-VERIFIED ONLY | **13** |
| NEVER TESTED | **17** |
| NOT FOUND | **15** |
| **total** | **127** |

> **Overtaken 2026-10-11, later the same day.** The counts below are what this document measured that night; the **second pass** (section after "Build freshness") re-ran 45 of these on real builds - the phone on **real CI builds and locally-built branches of #294**, the desktop on **0.2.140** - and its verdicts stand beside these. The rows below are left exactly as they were measured, and the marker here is the document's own convention for being overtaken.

## What each verdict means here, exactly

- **FIELD-TESTED** - a *pass record* names it: one of the two artifacts that recorded the app RUNNING and a result per thing.
  - the phone pass, `.dsh-scratch/phone-pass-2026-10-11/README.md` (2026-10-11, phone `f0a5b32b`, APK from `04af95c3` = merged main `f8e96ab4`);
  - the desktop pass, `.dsh-scratch/desktop-pass-2026-10-11/`: `FINDINGS.md`, `gap-table.md`, `sweep-results.tsv` and `chat-turn.log` (2026-10-10 21:57-22:30, desktop **0.2.129.0**).
- **TEST-VERIFIED ONLY** - a suite or checker in this repository names it and no pass record does. **Suites passing is not field testing.**
- **NEVER TESTED** - no pass record and no suite. A mention in an audit or tour document does not change this: those read the code and the screens, they did not drive the feature.
- **NOT FOUND** - no evidence either way: no pass record, no suite, and no review even names it. It says so rather than guessing.

**A mention is not a run.** The first pass of this work matched the feature's own words against every file in the audit folders and called **118** features field-tested. That was wrong: it was matching copied `.kt` source and tour documents. The device tier was then cut to the two pass records above, which is where the 80 below comes from. The scan, its input list and the rule are in `.dsh-scratch/field-matrix/build_matrix.py`.

## Build freshness - the column that matters most

| | version / when | base commit | commits behind main `70077268` |
|---|---|---|---|
| **phone** | 0.2.0, installed 2026-10-11 01:17:57 (`adb shell dumpsys package com.jarvis.client`, device `f0a5b32b`) | `6947f458` | **37** |
| **desktop** | 0.2.129.0, built 2026-10-10 15:38 (the pass below; 0.2.135 was written 2026-10-11 02:28) | `0f244f7b` | **43** |

Measured, not assumed: `git rev-list --count 6947f458..main` = 37 and `git rev-list --count 0f244f7b..main` = 43.

**So: nothing merged in the last 37 commits has ever run on the phone, and nothing in the last 43 has run on the desktop.** Every phone verdict below is against a build 37 commits old; every desktop verdict is older still. The phone's own install time (`lastUpdateTime`) and `firstInstallTime` (`2026-10-09 22:14:29`) were read from the device itself.

> **Since this was measured:** the second pass below ran the phone's **real CI builds and locally-built branches of #294** and the desktop at **0.2.140**, so the "37 commits behind" and "43 commits behind" columns describe the first pass's builds, not those. A verdict without its build is not evidence.

## Second pass - 2026-10-11, later the same day: the verdicts, and the two defects that matter

**Read this before the body below.** The body is left exactly as it was measured that night, with a short marker wherever it now misleads a reader; this section is the second pass, which re-ran the never-tested set on real builds. The source record is `.dsh-scratch/fieldtest-2026-10-11/RESULTS.md`, and every line of evidence below is taken from it rather than paraphrased.

**The builds.** The phone half ran on **real CI builds** and on **locally-built branches of #294** - the batch that pinned the `coming-up` count printed that screen's own key list on **`edf85d2f`**. The desktop half ran on **0.2.140**. Evidence came from the phone's own accessibility dump (`uiautomator`), the desktop's own **UI Automation** tree, and the backend's own answers: no screenshots and no vision.

**A feature that could not be reached is never a pass**, so PARTIAL and BLOCKED read as such below.

### The two defects this pass found - they matter more than the counts

1. **The "Jarvis is watching" badge does not clear after the session ends.** The session stops; **the sign does not.** Symptom: the backend's own state says `state:"ended"` while the badge is still on screen with a **decreasing countdown**. Read after stopping: `GET /api/screen` answered **HTTP 200** with **`{"state":"ended","on":false,"paused":null,"left_s":null,"ended":"owner","ended_words":"you stopped it", …}`** - and `ended:"owner"` is the string the backend's `ENGINE.stop()` writes, so **the stop worked**. The badge stayed up for **another ten minutes** all the same, reading `Jarvis is watching - paused` / `Paused: one of Jarvis's own windows · 8 min left`, its countdown falling because the badge **decrements `left_s` locally and never re-reads**: `watch-badge.js:156` listens for a `screen-status` event the desktop emits only when **that app** makes the call, and `:161` fetches the status **once at startup**. So **any ending that does not come through the app's own command leaves the sign up for ever** - a permanent false privacy alarm. What does work: the pause rule fires on Jarvis's own windows (the session sat paused because a Jarvis window was in front). **FAIL** - and the reproduction is two lines: **start a watch, stop it, then compare `GET /api/screen` against the badge window.**

   **Correction, kept visible - this row has now been corrected twice.** An earlier desktop-quickbar line in the record called it a **PASS** ("the control toggled and reported `Off`"); the direct test then wrote it up as **"cannot be stopped"**, which the backend's own state above **disproved** - it was ended by the owner's own click (`ended:"owner"`), and the broken thing is the badge. Claim, measurement and verdict are all three here on purpose: that is what this document is for.
2. **The Brain declares 19 rows and the list registers 11.** On `edf85d2f`, the screen's own key list and the list's count were printed side by side: **`screen declared=19 … hasWanted=true`**, **`composed=11`**, **`found=false`**, and `head` shows **`brain-plate:coming-up` is the eighth entry of the declared list**. The plate is declared and `shown=true`, so this is neither the walk nor the screen's keys: **the content lambda is not registering eight declared rows**, and **the Brain is drawing a third less than it declares**. That is why `coming-up` has been unreachable through six builds, and it is bigger than this one feature.

### One setting, not six bugs - the single most useful sentence in this pass

`pinned-facts`, `memory-as-of`, `between-us`, `memory-known`, `memory-tab` and `sensitive-facts` are all **BLOCKED by the same thing: "Hide memory lists and chat history"**. Every one of those menus is real - four of them are named with their own line (`MenuCatalog.kt:100`, `:101`, `:104`, `:107`, `brain.memory.*`) and the other two are the same group - and Find only offers a row whose menu is **shown**; the phone says so in its own words: **`Hidden. Tap Show and confirm it is you.`** That confirmation is the owner's fingerprint. **Turning that one setting off unblocks six features - they are not six defects.** `chat-tags` is blocked the same way (**"part of the same hidden memory group"**), and `between-us` in particular is **not a defect**, although it was filed as one once and corrected.

### FAIL (2)

| # | feature | build | evidence |
|---|---|---|---|
| 44 | Watch with me (`watch-with-me`) | desktop 0.2.140 | **the "Jarvis is watching" badge does not clear after the session ends**: the backend says `GET /api/screen` → `"state":"ended"`, `"ended":"owner"` (`ended_words":"you stopped it"`) while the badge stays on screen with a **decreasing countdown** for ~10 more minutes (`watch-badge.js:156`/`:161`). The session itself **was** stopped, by the owner's own click - an earlier write-up called it unstoppable and the backend's state corrected that |
| 89 | Hang and crash notes (`crash-notes`) | desktop 0.2.140 | the row is **not on his Settings page at all**: the word `crash` appears **zero times** in all **2,067** strings the Settings window exposes, though the row is supposed to be there (`jarvis_settings_registry.py:289-292`, `DESKTOP`-gated) |

### BLOCKED (9)

| # | feature | build | the blocker, in the record's own words |
|---|---|---|---|
| 19 | Timers, alarms, reminders and lists (`coming-up`) | phone `edf85d2f` | **`screen declared=19 … composed=11`**, `found=false` - the plate is declared, the list registers eleven of nineteen |
| 31 | Always keep in mind (`pinned-facts`) | phone CI build | the menu exists (`MenuCatalog.kt:100`) but Find → `keep in mind` offers **no such row**; `brain.memory.*` hidden by "Hide memory lists and chat history" |
| 37 | What did I believe on this date? (`memory-as-of`) | phone CI build | Find → `believe` says **`Nothing matches that.`** - same hidden-memory cause |
| 66 | Health and money facts wait for your yes (`sensitive-facts`) | phone CI build | Find → `sensitive` says **`Nothing matches that.`** - same cause |
| 26 | The Memory tab (`memory-tab`) | desktop 0.2.140 | same hidden-memory cause on the phone; the desktop Brain was not opened (the tray icon is not exposed to UI Automation by name) |
| 29 | What Jarvis knows about you (`memory-known`) | phone CI build | the phone **did draw the row**, with its own hidden state under it: **`Hidden. Tap Show and confirm it is you.`** |
| 32 | Between us (`between-us`) | phone CI build | **not a defect - a privacy setting**: Find → `between` says **`Nothing matches that.`** |
| 40 | Chat tags (`chat-tags`) | phone CI build | Find → `tags` says **`Nothing matches that.`** - part of the same hidden group |
| 105 | The big model (slow) (`big-model`) | desktop 0.2.140 | the row exists (`Big model (slow)`); turning it on needs the owner's click through Windows Hello |

### PARTIAL (17)

| # | feature | build | exactly which part was driven, and why the rest was not |
|---|---|---|---|
| 8 | How strict the voice check is (`voice-check`) | phone CI build | Find → `strict` gives **one match, and it is the `Voice` section** - the setting exists, but not under a "How strict" row of its own |
| 11 | Interrupt Jarvis while it talks (`interrupt`) | phone CI build | Find → `interrupt` gives **one match: `Attention budget`** - no screen of its own; it is a behaviour needing a live spoken answer to cut into |
| 47 | Show Jarvis the camera in Live (`live-camera`) | phone CI build | **no row of its own** - Find → `camera` offers one match, `Settings / Look at this and Watch with me`; it also needs the 12 GB card per the design |
| 90 | Choose Jarvis's face (`faces`) | phone CI build | the Appearance page opens and reads correctly (THEME, HOME, face sizes, tabs row), but the FACE section is **drawn, not text** - `uiautomator` sees no labels - and there is no vision provider here |
| 126 | Jarvis marks what it read from outside (`outside-text`) | phone CI build | **no Find row** - Find → `outside` says `Nothing matches that.`; it is a marking behaviour needing a turn that reads an email, file or page |
| 14 | Talk-to-type (`talk-to-type`) | desktop 0.2.140 | the row is real and reports its own live state: **`Nothing listens for the talk-to-type key.`** Turning it on needs an approval card plus Windows Hello (the owner) |
| 17 | Search what was said (`history-search`) | phone CI build | **no Find row** - Find → `history` says `Nothing matches that.`; it lives in History, which was not opened in this batch |
| 50 | Write a note for you (`notes-write`) | phone CI build | **no row of its own** - Find → `note` offers two unrelated matches; it is an action, so asking is the honest test |
| 57 | What's new on GitHub (`github-watchlist`) | phone CI build | **no row of its own** - Find → `github` landed in the Brain; it is an action/plate |
| 81 | Smartwatch notifications (`phone-watch`) | phone CI build | the row is **real and readable** (`Show notifications on a compatible watch`) but **no paired watch**, so the behaviour cannot be tested here |
| 85 | Also on my phone (`also-on-phone`) | phone CI build | **no Find row** - Find → `also on my phone` says `Nothing matches that.`; it hands an alarm to the phone's own apps by a tap, so it needs a share sheet |
| 92 | Set up Jarvis (`first-run`) | desktop 0.2.140 | the entry exists (`Set up Jarvis`) and clicking it **invoked**, but **neither window's text changed afterwards** |
| 98 | Memory on the Model page (`model-memory`) | desktop 0.2.140 | the row exists; its own words are in the page (`The memory summary on the Model page.`) - not driven |
| 125 | A warning when text tried to rush you (`rush-latch`) | phone CI build | **no Find row at all** - Find → `rush` says `Nothing matches that.`; it is a behaviour needing a turn with rushing text |
| 4 | Say "Hey Jarvis" (`wake-word`) | phone CI build | **no row** - Find → `hey jarvis` offers one unrelated match (`Screens / Jarvis Live`); it is a behaviour needing a voice |
| 54 | PC help (`pc-help`) | phone CI build | **no screen of its own** - Find → `PC help` landed in the Brain; like `find-phone` it is an action |
| 99 | Notifications (`notifications`) | desktop 0.2.140 | the desktop Settings section is real (`Start reading notifications from apps you choose on your phone - Asks you first, every time`) - not driven |

### PASS (11)

| # | feature | build | the evidence, in the record's own words |
|---|---|---|---|
| 82 | Floating Jarvis (`phone-floating`) | phone CI build | Find → `floating` → the phone drew `FLOATING JARVIS` with `Off / Bubble / Overlay` and the live line `Off. Nothing floats over other apps.` |
| 83 | Quick Settings tiles (`phone-tiles`) | phone CI build | `QUICK SETTINGS TILES`, with `Tile 1 - 10-min timer`, `Tile 2 - Open briefing` and the whole choice list |
| 119 | What asks first (`what-asks-first`) | phone CI build | `WHAT ASKS FIRST`, `Lockdown is off: everything asks first as your settings say.`, `Turn on Lockdown`, each action with its `Ask me first` control |
| 121 | Hand a captcha to your phone (`captcha-handoff`) | phone CI build | `WHEN A CAPTCHA STOPS JARVIS` read in full, with both choices (`Leave it where it is (in use)` / `Bring it to the front`) and what each does |
| 110 | About Jarvis (`about`) | desktop 0.2.140 | Help → the About card: `Version 0.2.1227`, `Made by darknight11ish`, `MIT, with third-party parts under their own licences` |
| 16 | Temporary chat (`temporary-chat`) | desktop 0.2.140 | clicked in the Jarvis bar: `toggled to Off` (it was On) - and **put back**, re-read as `toggled to On` |
| 23 | What Jarvis is doing right now (`now`) | phone CI build | Find → `doing` → landed in the Brain with the `What Jarvis is doing` plate drawn and unfolded |
| 24 | How much Jarvis may interrupt you (`attention-budget`) | phone CI build | `ATTENTION BUDGET`, `of 3 spoken interruptions left today`, `Speak up`, and the count's own explanation |
| 80 | Let Jarvis read phone notifications (`phone-notifications`) | phone CI build | `PHONE NOTIFICATIONS` with its live state: `Notification access: not granted yet.`, `Turn on Notification access`, `Apps Jarvis may read` |
| 86 | Ring my phone (`find-phone`) | phone CI build | **driven by asking** (`ring my phone`), and the phone's own notification confirms it really rang: `title = "Jarvis is ringing this phone"`, `SCHEDULE_KIND = ring_phone`, `channel = jarvis_alarm` |
| 93 | Show or hide menus (`menu-visibility`) | phone CI build | `SHOW OR HIDE MENUS`, `This hides menus on this device only.`, `Nothing is hidden.`, `Show everything`, and per-menu rows naming what each hides |

### Not tested, and not testable - with the reason

| # | feature | why it was not driven |
|---|---|---|
| 67 | Crisis help (`crisis-help`) | **deliberately not provoked** ("must not be provoked casually") - the one feature this pass refused to drive |
| 68 | Ask how the house is (`home-status`) | **NOT-TESTABLE**: needs Home Assistant |
| 81 | Smartwatch notifications (`phone-watch`) | **no paired watch** - the row is evidenced above; the behaviour is not |
| 105 | The big model (slow) (`big-model`) | needs **his** click through Windows Hello (BLOCKED above) |
| 90 | Choose Jarvis's face (`faces`) | the picker is **drawn, not text**, and there is **no vision provider on this machine** (PARTIAL above) |
| 12, 13, 43, 101 | Jarvis Live (`live`), the extras around Live (`live-extras`), Look at this (`look-at-this`), the Work tab (`work-tab`) | **not started** in this pass |

The pass's own summary of the pattern, kept because it is what the counts do not show: across four batches, **the features that drew a screen when asked passed almost every time, and the ones that failed were almost all features with no screen of their own** (actions and behaviours) **or features whose menu the owner's privacy setting hides**. Twenty of the 45 now read PARTIAL or BLOCKED, and most of those are "there is nothing to point at", not "it is broken".

## The headline: features that have NEVER run on a real device

> **Overtaken 2026-10-11, later the same day:** the second pass above re-ran most of this queue on real builds - the phone on real CI builds and locally-built branches of #294, the desktop on 0.2.140. The list below is left as it was written that night; read the **Second pass** verdicts above for what each one did when it was driven.

The whole NEVER TESTED and NOT FOUND set - this is the testing queue from the device side:

- **How strict the voice check is** (`voice-check`, Talking, both) - only a review mentions it: /.dsh-scratch/device-tour/README.md:79
- **Interrupt Jarvis while it talks** (`interrupt`, Talking, both) - only a review mentions it: /.dsh-scratch/device-tour/README.md:36
- **The extras around Live** (`live-extras`, Talking, both) - only a review mentions it: /.dsh-scratch/device-tour/README.md:12
- **Talk-to-type** (`talk-to-type`, Talking, desktop) - no evidence either way: no pass record, no suite and no review names it
- **Search what was said** (`history-search`, Talking, both) - no evidence either way: no pass record, no suite and no review names it
- **Timers, alarms, reminders and lists** (`coming-up`, Talking, both) - only a review mentions it: /.dsh-scratch/device-tour/README.md:48
- **The Memory tab** (`memory-tab`, Memory, desktop) - no evidence either way: no pass record, no suite and no review names it
- **What Jarvis knows about you** (`memory-known`, Memory, desktop) - no evidence either way: no pass record, no suite and no review names it
- **Always keep in mind** (`pinned-facts`, Memory, both) - only a review mentions it: /.dsh-scratch/device-tour/README.md:68
- **What did I believe on this date?** (`memory-as-of`, Memory, phone) - only a review mentions it: /.dsh-scratch/device-tour/.evidence/transcript-G.txt:654
- **Look at this** (`look-at-this`, Screen and pictures, both) - only a review mentions it: /.dsh-scratch/device-tour/.evidence/transcript-D.txt:44
- **Watch with me** (`watch-with-me`, Screen and pictures, both) - only a review mentions it: /.dsh-scratch/device-tour/.evidence/transcript-D.txt:44
- **Show Jarvis the camera in Live** (`live-camera`, Screen and pictures, phone) - only a review mentions it: /.dsh-scratch/device-tour/.evidence/transcript-D.txt:85
- **Write a note for you** (`notes-write`, Notes and files, both) - no evidence either way: no pass record, no suite and no review names it
- **What's new on GitHub** (`github-watchlist`, Notes and files, both) - no evidence either way: no pass record, no suite and no review names it
- **Health and money facts wait for your yes** (`sensitive-facts`, Money and health, both) - only a review mentions it: /.dsh-scratch/device-tour/README.md:42
- **Crisis help** (`crisis-help`, Money and health, both) - no evidence either way: no pass record, no suite and no review names it
- **Ask how the house is** (`home-status`, Home, both) - no evidence either way: no pass record, no suite and no review names it
- **Smartwatch notifications** (`phone-watch`, Phone, phone) - no evidence either way: no pass record, no suite and no review names it
- **Floating Jarvis** (`phone-floating`, Phone, phone) - only a review mentions it: /.dsh-scratch/device-tour/.evidence/transcript-D.txt:22
- **Quick Settings tiles** (`phone-tiles`, Phone, phone) - only a review mentions it: /.dsh-scratch/device-tour/docs/RESEARCH-AUDIT-2026-09-28.md:320
- **Also on my phone** (`also-on-phone`, Phone, both) - no evidence either way: no pass record, no suite and no review names it
- **Hang and crash notes** (`crash-notes`, The PC itself, desktop) - no evidence either way: no pass record, no suite and no review names it
- **Choose Jarvis's face** (`faces`, The PC itself, both) - only a review mentions it: /.dsh-scratch/device-tour/README.md:63
- **Set up Jarvis** (`first-run`, The PC itself, desktop) - no evidence either way: no pass record, no suite and no review names it
- **Memory on the Model page** (`model-memory`, The PC itself, desktop) - no evidence either way: no pass record, no suite and no review names it
- **The Work tab** (`work-tab`, The PC itself, desktop) - only a review mentions it: /.dsh-scratch/device-tour/docs/CONTINUITY-AUDIT-2026-09-26.md:39
- **About Jarvis** (`about`, The PC itself, both) - no evidence either way: no pass record, no suite and no review names it
- **What asks first** (`what-asks-first`, Safety, both) - only a review mentions it: /.dsh-scratch/device-tour/README.md:78
- **Hand a captcha to your phone ("Solve it here")** (`captcha-handoff`, Safety, both) - only a review mentions it: /.dsh-scratch/device-tour/.evidence/transcript-G.txt:483
- **A warning when text tried to rush you** (`rush-latch`, Safety, phone) - no evidence either way: no pass record, no suite and no review names it
- **Jarvis marks what it read from outside** (`outside-text`, Safety, both) - only a review mentions it: /.dsh-scratch/device-tour/.evidence/transcript-G.txt:1001

## Conversation-driven gaps (the list the owner asked for by name)

See the table at the end: every entry there says whether the **preflight** covers it and whether a **real turn** has ever driven it. The short version: the preflight last reported **35 pass / 0 fail / 3 warn (5 skipped)** against the backend of 2026-10-10 (`.dsh-scratch/preflight2.txt`, quoted in `.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md` line 30 and in `.dsh-scratch/gate-fix-msg.txt` line 65) - i.e. **before the 43 commits since**. A green preflight is a real chain test; it is still not a spoken turn, and several conversation features are not in it at all.

## The 127 features

`surface` is the repo's own field. `evidence` names the file and line the verdict came from.

| # | feature | group | surface | status | build it ran against | evidence |
|---|---|---|---|---|---|---|
| 1 | Type a message and read the answer (`typing`) | Talking | both | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:139 |
| 2 | Check a prompt before you send it (`prompt-coach`) | Talking | both | **FIELD-TESTED** | phone 0.2.0 installed 2026-10-11 01:17 - **37 commits behind main** <br>desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/phone-pass-2026-10-11/README.md:80<br>/.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:23 |
| 3 | The talk button (`talk-button`) | Talking | both | **FIELD-TESTED** | phone 0.2.0 installed 2026-10-11 01:17 - **37 commits behind main** <br>desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/phone-pass-2026-10-11/README.md:31<br>/.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:32 |
| 4 | Say "Hey Jarvis" (`wake-word`) | Talking | both | **TEST-VERIFIED ONLY** | never ran on a device | jarvis_wakeword.py, test_wakeword.py, train_wakeword.py |
| 5 | Jarvis reads its answers aloud (`read-aloud`) | Talking | both | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:19 |
| 6 | Short answers to spoken questions (`spoken-style`) | Talking | both | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:19 |
| 7 | Teach Jarvis your voice (`voice-training`) | Talking | both | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:42 |
| 8 | How strict the voice check is (`voice-check`) | Talking | both | **NEVER TESTED** | never ran on a device | only a review mentions it: /.dsh-scratch/device-tour/README.md:79 |
| 9 | The voice Jarvis speaks with (`custom-voices`) | Talking | both | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/sweep-results.tsv:160 |
| 10 | How Jarvis talks (`manner`) | Talking | both | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/sweep-results.tsv:97 |
| 11 | Interrupt Jarvis while it talks (`interrupt`) | Talking | both | **NEVER TESTED** | never ran on a device | only a review mentions it: /.dsh-scratch/device-tour/README.md:36 |
| 12 | Jarvis Live (`live`) | Talking | both | **TEST-VERIFIED ONLY** | never ran on a device | jarvis_live.py, jarvis_live_photo_test.py, test_browser_control_live.py, test_live.py |
| 13 | The extras around Live (`live-extras`) | Talking | both | **NEVER TESTED** | never ran on a device | only a review mentions it: /.dsh-scratch/device-tour/README.md:12 |
| 14 | Talk-to-type (`talk-to-type`) | Talking | desktop | **NOT FOUND** | never ran on a device | no evidence either way: no pass record, no suite and no review names it |
| 15 | The whole conversation, and carrying it on (`chat-thread`) | Talking | both | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:174 |
| 16 | Temporary chat (`temporary-chat`) | Talking | both | **TEST-VERIFIED ONLY** | never ran on a device | test_temporary_chat.py |
| 17 | Search what was said (`history-search`) | Talking | both | **NOT FOUND** | never ran on a device | no evidence either way: no pass record, no suite and no review names it |
| 18 | The morning briefing (`briefing`) | Talking | both | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:9 |
| 19 | Timers, alarms, reminders and lists (`coming-up`) | Talking | both | **NEVER TESTED** | never ran on a device | only a review mentions it: /.dsh-scratch/device-tour/README.md:48 |
| 20 | Today (`today`) | Talking | both | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/sweep-results.tsv:142 |
| 21 | Widgets you describe (`widgets`) | Talking | both | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:149 |
| 22 | Background jobs (`jobs`) | Talking | both | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/sweep-results.tsv:49 |
| 23 | What Jarvis is doing right now (`now`) | Talking | both | **TEST-VERIFIED ONLY** | never ran on a device | gen_own_network_cases.py |
| 24 | How much Jarvis may interrupt you (`attention-budget`) | Talking | both | **TEST-VERIFIED ONLY** | never ran on a device | test_attention_budget.py |
| 25 | Focus session (`focus`) | Talking | both | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/sweep-results.tsv:34 |
| 26 | The Memory tab (`memory-tab`) | Memory | desktop | **NOT FOUND** | never ran on a device | no evidence either way: no pass record, no suite and no review names it |
| 27 | Facts Jarvis saved by itself (`memory-saved`) | Memory | both | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/chat-turn.log:4 |
| 28 | Facts waiting for your yes (`memory-waiting`) | Memory | both | **FIELD-TESTED** | phone 0.2.0 installed 2026-10-11 01:17 - **37 commits behind main** <br>desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/phone-pass-2026-10-11/README.md:59<br>/.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:303 |
| 29 | What Jarvis knows about you (`memory-known`) | Memory | desktop | **NOT FOUND** | never ran on a device | no evidence either way: no pass record, no suite and no review names it |
| 30 | People and things (`memory-people`) | Memory | phone | **FIELD-TESTED** | phone 0.2.0 installed 2026-10-11 01:17 - **37 commits behind main** | /.dsh-scratch/phone-pass-2026-10-11/README.md:32 |
| 31 | Always keep in mind (`pinned-facts`) | Memory | both | **NEVER TESTED** | never ran on a device | only a review mentions it: /.dsh-scratch/device-tour/README.md:68 |
| 32 | Between us (`between-us`) | Memory | both | **TEST-VERIFIED ONLY** | never ran on a device | test_between_us.py |
| 33 | Topics (`topics`) | Memory | both | **FIELD-TESTED** | phone 0.2.0 installed 2026-10-11 01:17 - **37 commits behind main** <br>desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/phone-pass-2026-10-11/README.md:44<br>/.dsh-scratch/desktop-pass-2026-10-11/chat-turn.log:4 |
| 34 | The learning switches (`memory-learning`) | Memory | both | **FIELD-TESTED** | phone 0.2.0 installed 2026-10-11 01:17 - **37 commits behind main** <br>desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/phone-pass-2026-10-11/README.md:58<br>/.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:18 |
| 35 | The wiki Jarvis builds (`wiki`) | Memory | both | **FIELD-TESTED** | phone 0.2.0 installed 2026-10-11 01:17 - **37 commits behind main** <br>desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/phone-pass-2026-10-11/README.md:54<br>/.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:134 |
| 36 | Deep questions (`deep-questions`) | Memory | both | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:24 |
| 37 | What did I believe on this date? (`memory-as-of`) | Memory | phone | **NEVER TESTED** | never ran on a device | only a review mentions it: /.dsh-scratch/device-tour/.evidence/transcript-G.txt:654 |
| 38 | Bring in old chats (`import-chats`) | Memory | desktop | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/sweep-results.tsv:114 |
| 39 | Your past chats (`history`) | Memory | both | **FIELD-TESTED** | phone 0.2.0 installed 2026-10-11 01:17 - **37 commits behind main** <br>desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/phone-pass-2026-10-11/README.md:40<br>/.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:172 |
| 40 | Chat tags (`chat-tags`) | Memory | both | **TEST-VERIFIED ONLY** | never ran on a device | test_chat_tags.py |
| 41 | Forget a time frame (`forget-range`) | Memory | both | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:175 |
| 42 | Galaxy (`galaxy`) | Memory | desktop | **FIELD-TESTED** | phone 0.2.0 installed 2026-10-11 01:17 - **37 commits behind main** <br>desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/phone-pass-2026-10-11/README.md:48<br>/.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:209 |
| 43 | Look at this (`look-at-this`) | Screen and pictures | both | **NEVER TESTED** | never ran on a device | only a review mentions it: /.dsh-scratch/device-tour/.evidence/transcript-D.txt:44 |
| 44 | Watch with me (`watch-with-me`) | Screen and pictures | both | **NEVER TESTED** | never ran on a device | only a review mentions it: /.dsh-scratch/device-tour/.evidence/transcript-D.txt:44 |
| 45 | Picture mode (`picture-mode`) | Screen and pictures | both | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:164 |
| 46 | Photo to reminder (`photo-reminder`) | Screen and pictures | both | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/sweep-results.tsv:140 |
| 47 | Show Jarvis the camera in Live (`live-camera`) | Screen and pictures | phone | **NEVER TESTED** | never ran on a device | only a review mentions it: /.dsh-scratch/device-tour/.evidence/transcript-D.txt:85 |
| 48 | Quiz me on a text (`quiz`) | Screen and pictures | both | **FIELD-TESTED** | phone 0.2.0 installed 2026-10-11 01:17 - **37 commits behind main** <br>desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/phone-pass-2026-10-11/README.md:33<br>/.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:102 |
| 49 | My study decks (`decks`) | Notes and files | both | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:146 |
| 50 | Write a note for you (`notes-write`) | Notes and files | both | **NOT FOUND** | never ran on a device | no evidence either way: no pass record, no suite and no review names it |
| 51 | Folders Jarvis may look in (`folders`) | Notes and files | both | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:13 |
| 52 | Ask about a PDF, a Word file or a Notion page (`documents`) | Notes and files | both | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:40 |
| 53 | Tutorials and the FAQ (`tutorials`) | Notes and files | both | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:40 |
| 54 | PC help (`pc-help`) | Notes and files | phone | **TEST-VERIFIED ONLY** | never ran on a device | jarvis_pc_help.py, test_pc_help.py, gen_pc_help_cases.py |
| 55 | Web search (`web-search`) | Notes and files | both | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:26 |
| 56 | A browser without a window (`browser-engine`) | Notes and files | both | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:187 |
| 57 | What's new on GitHub (`github-watchlist`) | Notes and files | both | **NOT FOUND** | never ran on a device | no evidence either way: no pass record, no suite and no review names it |
| 58 | Talk to a chatbot for me (`chatbot`) | Notes and files | both | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:10 |
| 59 | Deal with customer support for me (`support`) | Notes and files | both | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/sweep-results.tsv:34 |
| 60 | Projects (`projects`) | Notes and files | both | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:150 |
| 61 | Goals (`goals`) | Notes and files | both | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/sweep-results.tsv:71 |
| 62 | Progress (`progress`) | Notes and files | both | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:40 |
| 63 | Spending summaries (`spending`) | Money and health | both | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:109 |
| 64 | Retirement what-if (`retirement`) | Money and health | both | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/sweep-results.tsv:172 |
| 65 | Chatbot keys and a monthly money limit (`chatbot-money`) | Money and health | desktop | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:10 |
| 66 | Health and money facts wait for your yes (`sensitive-facts`) | Money and health | both | **NEVER TESTED** | never ran on a device | only a review mentions it: /.dsh-scratch/device-tour/README.md:42 |
| 67 | Crisis help (`crisis-help`) | Money and health | both | **NOT FOUND** | never ran on a device | no evidence either way: no pass record, no suite and no review names it |
| 68 | Ask how the house is (`home-status`) | Home | both | **NOT FOUND** | never ran on a device | no evidence either way: no pass record, no suite and no review names it |
| 69 | Lights, plugs and fans (`lights`) | Home | both | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:3 |
| 70 | Locks, doors, alarms and covers (`locks`) | Home | both | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:37 |
| 71 | Read your own calendar (`calendar`) | Home | desktop | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:191 |
| 72 | Weather and the sky behind the animals (`weather-sky`) | Home | both | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:104 |
| 73 | Jarvis reads your email (`email-read`) | Home | both | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:9 |
| 74 | Send an email for you (`email-send`) | Home | both | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/sweep-results.tsv:56 |
| 75 | Save a draft to your Drafts folder (`email-drafts`) | Home | desktop | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:170 |
| 76 | Tidy the inbox by voice (`inbox-tidy`) | Home | both | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/sweep-results.tsv:57 |
| 77 | News headlines, and pages that change (`news-and-page-watches`) | Home | both | **FIELD-TESTED** | phone 0.2.0 installed 2026-10-11 01:17 - **37 commits behind main** <br>desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/phone-pass-2026-10-11/README.md:22<br>/.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:29 |
| 78 | Pairing and the connection (`connection`) | Phone | both | **FIELD-TESTED** | phone 0.2.0 installed 2026-10-11 01:17 - **37 commits behind main** <br>desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/phone-pass-2026-10-11/README.md:23<br>/.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:20 |
| 79 | Devices (`devices`) | Phone | both | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:12 |
| 80 | Let Jarvis read phone notifications (`phone-notifications`) | Phone | phone | **TEST-VERIFIED ONLY** | never ran on a device | jarvis_phone_notifications.py, test_phone_notifications.py |
| 81 | Smartwatch notifications (`phone-watch`) | Phone | phone | **NOT FOUND** | never ran on a device | no evidence either way: no pass record, no suite and no review names it |
| 82 | Floating Jarvis (`phone-floating`) | Phone | phone | **NEVER TESTED** | never ran on a device | only a review mentions it: /.dsh-scratch/device-tour/.evidence/transcript-D.txt:22 |
| 83 | Quick Settings tiles (`phone-tiles`) | Phone | phone | **NEVER TESTED** | never ran on a device | only a review mentions it: /.dsh-scratch/device-tour/docs/RESEARCH-AUDIT-2026-09-28.md:320 |
| 84 | Screen refresh rate (`phone-screen-rate`) | Phone | phone | **FIELD-TESTED** | phone 0.2.0 installed 2026-10-11 01:17 - **37 commits behind main** <br>desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/phone-pass-2026-10-11/README.md:35<br>/.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:171 |
| 85 | Also on my phone (`also-on-phone`) | Phone | both | **NOT FOUND** | never ran on a device | no evidence either way: no pass record, no suite and no review names it |
| 86 | Ring my phone (`find-phone`) | Phone | both | **TEST-VERIFIED ONLY** | never ran on a device | jarvis_find_phone.py, test_find_phone.py |
| 87 | What the phone deliberately does not do (`phone-limits`) | Phone | phone | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:78 |
| 88 | Appearance (`appearance`) | The PC itself | both | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/sweep-results.tsv:4 |
| 89 | Hang and crash notes (`crash-notes`) | The PC itself | desktop | **NOT FOUND** | never ran on a device | no evidence either way: no pass record, no suite and no review names it |
| 90 | Choose Jarvis's face (`faces`) | The PC itself | both | **NEVER TESTED** | never ran on a device | only a review mentions it: /.dsh-scratch/device-tour/README.md:63 |
| 91 | Animal options (`animal-options`) | The PC itself | both | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:195 |
| 92 | Set up Jarvis (`first-run`) | The PC itself | desktop | **NOT FOUND** | never ran on a device | no evidence either way: no pass record, no suite and no review names it |
| 93 | Show or hide menus (`menu-visibility`) | The PC itself | both | **TEST-VERIFIED ONLY** | never ran on a device | test_menu_visibility.py |
| 94 | Keyboard shortcuts (`shortcuts`) | The PC itself | desktop | **FIELD-TESTED** | phone 0.2.0 installed 2026-10-11 01:17 - **37 commits behind main** | /.dsh-scratch/phone-pass-2026-10-11/README.md:36 |
| 95 | Models (`models`) | The PC itself | both | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/chat-turn.log:19 |
| 96 | Compute (`compute`) | The PC itself | both | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/sweep-results.tsv:41 |
| 97 | Skills (`skills`) | The PC itself | both | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/sweep-results.tsv:192 |
| 98 | Memory on the Model page (`model-memory`) | The PC itself | desktop | **NOT FOUND** | never ran on a device | no evidence either way: no pass record, no suite and no review names it |
| 99 | Notifications (`notifications`) | The PC itself | desktop | **TEST-VERIFIED ONLY** | never ran on a device | jarvis_phone_notifications.py, test_phone_notifications.py |
| 100 | Starting Jarvis for you (`start-jarvis`) | The PC itself | desktop | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:22 |
| 101 | The Work tab (`work-tab`) | The PC itself | desktop | **NEVER TESTED** | never ran on a device | only a review mentions it: /.dsh-scratch/device-tour/docs/CONTINUITY-AUDIT-2026-09-26.md:39 |
| 102 | Jobs that keep going after the chat ends (`job-list`) | The PC itself | both | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:36 |
| 103 | Hardware and models (`hardware`) | The PC itself | both | **FIELD-TESTED** | phone 0.2.0 installed 2026-10-11 01:17 - **37 commits behind main** <br>desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/phone-pass-2026-10-11/README.md:38<br>/.dsh-scratch/desktop-pass-2026-10-11/sweep-results.tsv:76 |
| 104 | The second graphics card (`second-card`) | The PC itself | both | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/chat-turn.log:5 |
| 105 | The big model (slow) (`big-model`) | The PC itself | both | **TEST-VERIFIED ONLY** | never ran on a device | jarvis_big_model.py, test_big_model.py, gen_big_model_cases.py |
| 106 | Updates (`updates`) | The PC itself | both | **FIELD-TESTED** | phone 0.2.0 installed 2026-10-11 01:17 - **37 commits behind main** | /.dsh-scratch/phone-pass-2026-10-11/README.md:71 |
| 107 | Check for tool updates (`tool-updates`) | The PC itself | desktop | **FIELD-TESTED** | phone 0.2.0 installed 2026-10-11 01:17 - **37 commits behind main** <br>desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/phone-pass-2026-10-11/README.md:71<br>/.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:37 |
| 108 | The settings file, the logs and starting with Windows (`settings-file`) | The PC itself | desktop | **FIELD-TESTED** | phone 0.2.0 installed 2026-10-11 01:17 - **37 commits behind main** <br>desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/phone-pass-2026-10-11/README.md:97<br>/.dsh-scratch/desktop-pass-2026-10-11/chat-turn.log:1 |
| 109 | What this backend supports (`backend-supports`) | The PC itself | both | **FIELD-TESTED** | phone 0.2.0 installed 2026-10-11 01:17 - **37 commits behind main** <br>desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/phone-pass-2026-10-11/README.md:50<br>/.dsh-scratch/desktop-pass-2026-10-11/chat-turn.log:1 |
| 110 | About Jarvis (`about`) | The PC itself | both | **NOT FOUND** | never ran on a device | no evidence either way: no pass record, no suite and no review names it |
| 111 | The big HUD window (`hud-window`) | The PC itself | desktop | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:187 |
| 112 | Backups (`backup`) | The PC itself | both | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:59 |
| 113 | Accounts and keys (`accounts`) | The PC itself | desktop | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/sweep-results.tsv:2 |
| 114 | What Jarvis can reach (`reach`) | The PC itself | both | **FIELD-TESTED** | phone 0.2.0 installed 2026-10-11 01:17 - **37 commits behind main** <br>desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/phone-pass-2026-10-11/README.md:50<br>/.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:5 |
| 115 | Undo (`undo`) | The PC itself | both | **FIELD-TESTED** | phone 0.2.0 installed 2026-10-11 01:17 - **37 commits behind main** <br>desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/phone-pass-2026-10-11/README.md:76<br>/.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:81 |
| 116 | Activity: cards you already decided (`past-approvals`) | The PC itself | both | **FIELD-TESTED** | phone 0.2.0 installed 2026-10-11 01:17 - **37 commits behind main** <br>desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/phone-pass-2026-10-11/README.md:21<br>/.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:13 |
| 117 | Limits and frequency (`limits`) | The PC itself | both | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:10 |
| 118 | Approval cards (`approvals`) | Safety | both | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:28 |
| 119 | What asks first (`what-asks-first`) | Safety | both | **NEVER TESTED** | never ran on a device | only a review mentions it: /.dsh-scratch/device-tour/README.md:78 |
| 120 | Lock Jarvis, and hide what it remembers (`app-lock`) | Safety | both | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:21 |
| 121 | Hand a captcha to your phone ("Solve it here") (`captcha-handoff`) | Safety | both | **NEVER TESTED** | never ran on a device | only a review mentions it: /.dsh-scratch/device-tour/.evidence/transcript-G.txt:483 |
| 122 | When the connection is catching up (`stale-link`) | Safety | both | **FIELD-TESTED** | phone 0.2.0 installed 2026-10-11 01:17 - **37 commits behind main** <br>desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/phone-pass-2026-10-11/README.md:97<br>/.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:20 |
| 123 | Stop everything (`stop-everything`) | Safety | both | **FIELD-TESTED** | phone 0.2.0 installed 2026-10-11 01:17 - **37 commits behind main** <br>desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/phone-pass-2026-10-11/README.md:94<br>/.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:54 |
| 124 | Trust: content risk and the audit chain (`trust`) | Safety | both | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/chat-turn.log:6 |
| 125 | A warning when text tried to rush you (`rush-latch`) | Safety | phone | **NOT FOUND** | never ran on a device | no evidence either way: no pass record, no suite and no review names it |
| 126 | Jarvis marks what it read from outside (`outside-text`) | Safety | both | **NEVER TESTED** | never ran on a device | only a review mentions it: /.dsh-scratch/device-tour/.evidence/transcript-G.txt:1001 |
| 127 | Settings itself (`settings-entry`) | Safety | both | **FIELD-TESTED** | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/chat-turn.log:4 |

## Method, and its limits, said plainly

1. The 127 entries come from `features/features.json`; no field in it records testing, so nothing here is read from the repo's own claim.
2. The scan is keyword-based (each feature's id, its title's longer words, and a short alias table) over the dated artifacts. **False negatives are possible**: a pass record may describe a feature in words the scan does not know. False positives are the thing this document exists to avoid, so the device tier holds only the two pass records and every row cites its line.
3. `TEST-VERIFIED ONLY` says a suite names it. It does **not** say the suite passes today; that is CI's job and `main`'s state is a separate question.
4. **The device-tour transcripts (2026-10-09) are shown as mentions, not as runs.** They are a real record of a device, but the tour is older than either pass record, so a feature that appears only there is NEVER TESTED with the transcript named in its evidence column - a person should re-check those rows first, and they are the ones most likely to move up.
5. The conversation-driven table below was written by hand from the same artifacts, because those features are driven by words and a word is not a keyword.

## Conversation-driven features - preflight coverage and real turns

`preflight` = named in `backend/selftest.py --preflight`. `real turn` = an artifact records the owner (or a tester) actually saying or typing it on the PC or phone.

| conversation feature | preflight covers it? | a real turn ever? | evidence |
|---|---|---|---|
| timers, alarms, reminders (spoken/typed) | yes, a chain check | **no spoken or typed turn found** | no transcript drives a timer; selftest chain only |
| memory saving ("remember that...") | partly | yes - the phone pass drove the Brain's learning plates | phone-pass README, Brain/Memory rows |
| "what asks first" | yes | read and switched, not driven by a turn | settings-audit/INVENTORY.md; desktop-pass sweep |
| focus sessions | unknown | **no** | no artifact drives one |
| "Coach this" | yes | **no** - only its setting is checked | desktop-pass gap-table.md (the setting route answered 404) |
| "Look at this" / "Watch with me" | partly | the screen feature was built and shown, but no artifact records a real look on the PC | docs/SCREEN-DESIGN.md; phone XML dumps |
| web search and its ask-first rules | yes | partly - the search route answered in the sweep; no real search turn was kept | desktop-pass sweep-results.tsv |
| email / calendar / notes reads | yes | **no real mailbox or calendar read found** | inbox tidy was "tried against a stand-in mail server, never a real mailbox" (CLAUDE.md) |
| note writes (Obsidian / Logseq / Joplin) | partly | **no** | no artifact writes a real note |
| inbox tidy by voice | partly | **no** - stand-in mail server only | CLAUDE.md, 2026-09-28 |
| "Forget a time frame" | yes | **no** | no artifact approves one |
| crisis handling | yes | **no** - never driven by a real crisis turn, and it should not be provoked | test_wellbeing.py only |
| model switch / install | yes | **no** - the routes answered in the sweep, no switch was approved | desktop-pass gap-table.md |
| Jarvis Live | partly | **no** | no artifact records a Live session |
| "from now on..." rules | unknown | **no** | no artifact |

**Read the `real turn` column as the second half of the testing queue.** Everything marked **no** there has never been driven by the owner's own words on his own machine, whatever the suites say.
