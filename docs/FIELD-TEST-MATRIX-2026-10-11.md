# Field-test matrix - what has actually run on the owner's own devices

**Written 2026-10-11. Checkout `.dsh-scratch/field-matrix` (branch `docs/field-test-matrix`) off `origin/main` `70077268`.**

The owner asked: *"are there any features that haven't been field tested on the real world jarvis android app or desktop app? Or conversation driven features that haven't been? I want thorough testing on everything."*

`features/features.json` holds **128 features in 9 groups and has no `tested`, `verified` or `status` field at all** - so this document cannot be read from a file. Every verdict below was built from a dated artifact, and every row names the one it came from.


> ## CORRECTED 2026-10-15: the status column was machine-assigned and is NOT a pass
>
> **Every status below was assigned by a KEYWORD SCAN, not by testing.** The scan
> that built it is `.dsh-scratch/field-matrix/build_matrix.py`, whose own line 7
> says it outright: *"NO verdict is decided here: this only finds candidates WITH
> their file and line."* It called a feature `FIELD-TESTED` whenever the
> feature's own words matched **anywhere** in one of two pass records - it never
> required the feature to have been operated. The evidence column therefore holds
> **keyword-hit line numbers, not the line a verdict came from**. Reading those
> lines back is what this correction does.
>
> **A `FIELD-TESTED` row here is not a pass, and the old word is kept inside each
> row as `was ...` so the change is visible.** Nothing below is promoted;
> every change is a lowering or a split.
>
> ### What the states mean
>
> | state | means |
> |---|---|
> | **DRIVEN** | the cited record shows the feature **operated and its effect observed** |
> | **SCREEN** | its screen or row was **found and read**; its behaviour was never exercised |
> | **BLOCKED** | a record says it **could not be reached** |
> | **NOT-TESTABLE** | the record says it **needs something absent** (his voice, his accounts, his fingerprint, Home Assistant, hardware) |
> | **NEVER** | **no record at all** |
>
> ### The rule, and that it is mine
>
> Later records outrank the main table, and where they disagree the row says
> **`was ...`** so the earlier reading stays visible. A row that could not be
> told apart went to the **lower** state. **These counts are this correction's,
> not the audit's**: the audit's per-row table was never on disk, so they were
> re-derived row by row from the cited lines and every one is traceable. Nothing
> was reverse-engineered to match a target distribution.
>
> | state | features |
> |---|---|
> | DRIVEN | **5** |
> | SCREEN | **93** |
> | BLOCKED | **19** |
> | NOT-TESTABLE | **12** |
> | NEVER | **0** |
> | **total** | **129** |
>
> ### The build the evidence came from, and why age alone is not the finding
>
> The desktop record is **0.2.129.0, built 2026-10-10 15:38** - 43 commits behind
> the main it was measured against - and the phone record is 37 behind. **That
> alone is not a fault**: a feature that has not changed since its record may be
> well tested by it. The fault this correction fixes is narrower and worse: rows
> marked `FIELD-TESTED` **whose own cited line shows a status**, not a run.
>
> ### The three rows I could not settle, and which way I erred
>
> Three rows have operation evidence **elsewhere in the record** but a
> cited line that does not show it. The rule puts all three DOWN at
> **SCREEN**, and none is claimed as driven:
>
> - **`typing`** - the desktop pass logged a real turn (`chat-turn.log`:
>   `status 200`, an `X-Jarvis-Route` header, 36.6 s), but this row cites
>   `FINDINGS.md:139` - a sentence about 404s being POST-only routes.
> - **`focus`** - the row cites `sweep-results.tsv:34`, which is
>   `/api/chatbot/start STATIC`: a route sweep, not a focus session.
> - **`settings-entry`** - the row cites `chat-turn.log:4`, an HTTP status
>   and route header. The Settings SCREEN was demonstrably opened (the
>   crash-notes FAIL row says the row is not on his Settings page), which is
>   reading it, not observing its behaviour.
> Citing the stronger line would settle each one; none is claimed as driven here.
>
> ### What cannot be tested from a checkout
>
> These need the owner's own machine, voice, accounts or hardware, so reading
> this repository can never settle them. **This is the actionable list.**
>
> - **NOT-TESTABLE (12 rows)**: `accounts`, `calendar`, `chatbot-money`, `crisis-help`, `email-drafts`, `email-read`, `email-send`, `home-status`, `inbox-tidy`, `lights`, `locks`, `weather-sky`. Each row's own reason is
>   beside it - his voice print, his accounts, his fingerprint, Home Assistant,
>   and hardware this machine does not have.
> - **The third pass's own list, with who can settle each** (its section
>   "NOT TESTED (7) and NOT-TESTABLE (2)"): the voice gate's ACCEPT half (**his**
>   voice); desktop-microphone voice (no `owner-desktop.json`); #355 the phone's
>   Live face, #356 the silent mic and face-size options, #357 "Choose a model"
>   (**the phone**, which was disconnected); #361 the approval toast's
>   where-to-approve line (**seen on his desktop**); settings through the **model**
>   path; the two apps refreshing live after a setting changes; the tray menu's
>   trimmed rows (**his** hidden tray).
>
> ### What this correction did NOT do
>
> It did not promote anything, and it did not delete a single evidence line or
> build column - the owner asked for those kept. The counts the first three
> passes wrote are left in place below, marked as theirs.
>
> > **The `## The counts` table immediately below is the FIRST PASS'S OWN COUNT,
> > kept exactly as measured. It counts keyword-scan verdicts, NOT passes. The
> > corrected counts are the table just above this note.**
>

## The counts

| verdict | features |
|---|---|
| FIELD-TESTED | **82** |
| TEST-VERIFIED ONLY | **13** |
| NEVER TESTED | **17** |
| NOT FOUND | **15** |
| **total** | **127** |

> **Corrected 2026-10-13: the list is 128 entries, and `pictures` had no row.** The tally above is the **first pass's** four-verdict count over its own 127 rows and is left as measured; `features/features.json` holds **128** (`git show origin/main:features/features.json`, 128 ids), and **`pictures`** ("Ask for a picture, and keep it") was missing from the table entirely. It is added at **row 128** with the only verdict the document set records for it - **PARTIAL**, driven on the phone on 2026-10-12 and with no screen of its own (`docs/FIELD-TEST-2026-10-12-TOPUP.md:52`). No other row was renumbered or rewritten; the dated notes below that say "the 127-feature counts" or "the 127-feature table" name the list as those passes saw it.

> **Corrected 2026-10-13: 21 of these 82 are not passes, so the field-tested set is 61.** The tally above is the **first pass's** own count over its own 127 rows and is **left as measured**. The later top-up passes then could not reach **21** of those 82 rows and wrote each one down as **BLOCKED** (9), **NOT-TESTABLE** (10) or **PARTIAL** (2) - and the project's rule, reaffirmed by the owner on 2026-10-13, is that **BLOCKED and NOT-TESTABLE are never counted as passes** (`CLAUDE.md`; `docs/DECISIONS.md`). Read over the first pass's same 127 rows, the corrected position is **FIELD-TESTED 61**, TEST-VERIFIED ONLY 13, NEVER TESTED 17, NOT FOUND 15, **BLOCKED 9, NOT-TESTABLE 10, PARTIAL 2**; row 128 (`pictures`) carries the PARTIAL the document already records for it. Each of the 21 rows below now shows **both** its verdicts, with the top-up's own reason and the file and line it came from beside the original reading; no row the top-ups do not contradict was touched, and no row was renumbered.

> **Overtaken 2026-10-11, later the same day.** The counts below are what this document measured that night; the **second pass** (section after "Build freshness") drove **43 of these 45** on real hardware and **could not drive 2** - the phone on **real CI builds and locally-built branches of #294**, the desktop on **0.2.140** - and its verdicts stand beside these. The rows below are left exactly as they were measured, and the marker here is the document's own convention for being overtaken.
>
> **Again 2026-10-12/13.** The **third pass** (below the second, section "Third pass - 2026-10-12/13") records **five things driven on the live PC tonight and ten that were not**, every row with its evidence **and the person who can settle it**. Those rows are conversation- and fix-level, so the 127-feature counts below are unchanged by them; what changed is that the testing queue is now written down instead of living in agent reports.

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

### BLOCKED (10)

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
| 101 | The Work tab (`work-tab`) | desktop 0.2.140 | it lives in the **desktop Brain window**, which could not be opened from here: **three routes tried and all failed** - the tray icon is inside the "Show Hidden Icons" overflow and a right-click produced **no readable menu**, no in-app control opens the Brain (the Settings page says *"open it from the tray icon, 'Open the Brain'"*), and the HUD's **GALAXY tab is a different view**. **A person at the machine with a mouse reaches it in two clicks; this harness cannot** |

### PARTIAL (19)

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
| 13 | The extras around Live (`live-extras`) | phone CI build | **no row of its own** - Find → `live extras` offers two matches (`Screens / Jarvis Live` and `Settings / Voice`). The extras are **behaviours and OS surfaces** (a Quick Settings tile, a headset button, a 10-minute "Live ended - Resume" notification, a PC hotkey, preferring a Bluetooth headset mic, and "Talk about this in Live" from Share), so testing them needs a Live session and, for some, hardware |
| 12 | Jarvis Live (`live`) | phone CI build | **the screen is real and reachable**: Find → `jarvis live` drew `Jarvis Live` with a **`Start Jarvis Live`** control. **The session itself was not started, deliberately** - a Live session opens the phone's microphone and there is nobody here to talk to it, so starting one would have tested the microphone rather than the feature |

### PASS (12)

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
| 43 | Look at this (`look-at-this`) | desktop 0.2.140 | **driven with its own key** - the Settings page names it (`Look at this: Alt + Shift + S`), and sending it opened **`Jarvis and your screen`** showing **`Looked at: DeepSeek Harness window - words only`** (the window that was in front), a **`Forget this look`** control, and `Secrets in pictures you attach are covered with black boxes before Jarvis looks.` One press, one read, and the words-only mode reported honestly |

### All 45, and where each verdict came from

**PASS 12, FAIL 2, PARTIAL 19, BLOCKED 10, NOT-TESTABLE 2 = 45.** Every count above is derived from
the record's own table (`.dsh-scratch/fieldtest-2026-10-11/RESULTS.md`), not adjusted here: the rows
are the record's rows.

### NOT-TESTABLE (2), and the three that were driven only in part

| # | feature | why it could not be driven |
|---|---|---|
| 67 | Crisis help (`crisis-help`) | **deliberately not provoked** ("must not be provoked casually") - the one feature this pass refused to drive |
| 68 | Ask how the house is (`home-status`) | needs **Home Assistant**, which this machine does not have |

Three more could only be driven in part, and their reasons are in their own rows above:
`phone-watch` (81, PARTIAL - the row is real and readable, but there is **no paired watch**),
`big-model` (105, BLOCKED - the row exists; turning it on needs the owner's click through Windows Hello),
and `faces` (90, PARTIAL - the picker is **drawn, not text**, and there is **no vision provider here**).

The pass's own summary of the pattern, kept because it is what the counts do not show: across four batches, **the features that drew a screen when asked passed almost every time, and the ones that failed were almost all features with no screen of their own** (actions and behaviours) **or features whose menu the owner's privacy setting hides**. **Twenty-nine of the 45 now read PARTIAL or BLOCKED** (19 PARTIAL + 10 BLOCKED), and most of those are "there is nothing to point at", not "it is broken". (The record's batch note said twenty of the 45 at the time it was written; the last four were driven after it, so this line carries today's number.)

## Third pass - 2026-10-12/13: what was driven tonight, and who can settle the rest

**Written 2026-10-13. Checkout `.dsh-scratch/wt-fieldmatrix` (branch `docs/field-test-matrix-2026-10-13`) off `origin/main` `94da2d61`.** The owner asked: *"did you or the new conversation finish field testing everything that could be that hasn't been already?"* This section is the honest answer: **five things were driven on the live PC tonight, and nine were not** - each with the reason and the person who can settle it.

Every evidence path below was read from disk (the shared `.dsh-scratch/` reports); nothing here was re-measured except the Ollama lanes, which are marked as measured by this pass. **`BLOCKED` and `NOT-TESTABLE` are never counted as passes** (`CLAUDE.md`, 2026-10-11).

**One column is new in this pass: `who can settle it`.** The earlier passes had no such column, and a row without a "who" is a row nobody can finish.

### The counts (tonight's rows only)

| verdict | rows |
|---|---|
| **PASS** | **5** |
| NOT TESTED | 7 |
| NOT-TESTABLE | 2 |
| **total** | **14** |

### PASS (5) - driven on the owner's own machine tonight

| # | what ran | verdict | build / when | the evidence, in the record's own words | who settled it |
|---|---|---|---|---|---|
| T1 | **Voice gate, refusal direction** | **PASS** | live backend `127.0.0.1:4719`, 2026-10-12 | a synthetic clip was **refused**: `{"is_owner": false, "text": "", "score": -0.0414, "threshold": 0.5, "voice_print": "phone", "too_short": false}` - no transcript and no turn. The **first attempt proved nothing** (`score: 0.0`, `threshold: 0.0`, `voice_print: ""`, `too_short: true` - the comparison never ran), which is exactly why the second run is the evidence. Report: `.dsh-scratch/voice-field-test-report.md` §3, §3c | an agent, on the live build; needs no owner |
| T2 | **Settings by typing, BOTH directions** | **PASS** | live backend, 2026-10-12 | cosmetic: typed *"keep the animal still"* → `still` went **`false → true`** in the live store, `X-Jarvis-Route: {"lane": "no AI model", "quick": "animal_switch"}`, answer *"Done - the animal keeps still now…"*; typed *"let the animal move again"* → **`true → false`**. Loosening: typed *"turn on remembering sensitive topics automatically"* → **a card was raised** (`"expires_in": 599`), `auto_sensitive` stayed **`false`**; **DENIED** → `{"ok": true, "id": "9749ddd28b2b", "state": "denied"}`, 0 waiting, setting still `false`. Approve was never called. Report: `.dsh-scratch/settings-turn-test-report.md` §1-§2 | an agent; needs no owner |
| T3 | **The 10-minute card window** | **PASS** | live build, 2026-10-12 | a real card reported **`"expires_in": 599`** - the ten-minute window is what the live build actually offers. Report: `.dsh-scratch/settings-turn-test-report.md` §2.1 | an agent; needs no owner |
| T4 | **Voice enrolment saved** | **PASS** | live PC, 2026-10-12 20:58:12 | `owner-phone.json` 59,128 bytes = **3 sub-prints (`close`, `far`, `room`) × 12 samples = 36**, **phone microphone only**, scored by two embedders (512-dim and 192-dim). A second repeat **ADDS** a sub-print rather than replacing. Report: `.dsh-scratch/voice-field-test-report.md` §1 | an agent read the file; the training itself was the owner's |
| T5 | **The grey rectangles are gone** | **PASS** | installed desktop build, 2026-10-12 | **two independent instruments**: exact `rgb(84,84,84)` was **355,327 px in exactly two regions** before (220,320 px at `(1440,480)` 480x459; 135,000 px at `(398,259)` 1125x120) and **24 px / 18 px / 0 px** after, with **no region ≥ 2,000 px**; the untouched HUD rail is **pixel-identical** across the pair (0 of 270,750 px differing), so it is a like-for-like comparison. Report: `.dsh-scratch/grey-recheck-report.md` | an agent, on the installed build. The owner's own before/after screenshots remain the human record |

### NOT TESTED (7) and NOT-TESTABLE (2) - each with the reason and the person who can settle it

| # | what | verdict | why not tonight | who can settle it |
|---|---|---|---|---|
| T6 | **Voice gate, ACCEPT half - does it recognise HIM** | **NOT-TESTABLE here** | a stand-in voice would only test the stand-in; the print holds his voice only (a synthetic clip scores −0.04 against the 0.50 bar, which is the *refusal* working) | **the owner**, in about two minutes: (1) on the phone open **Checks → Your voice**; (2) hold the **talk button** and say a normal command in his ordinary voice and distance, e.g. *"Hey Jarvis, what is the weather like tomorrow?"*; (3) **watch for** the answer being spoken and **no** "does not match the enrolled voice" line (that line naming a negative score is the refusal seen in T1); (4) if it refuses, repeat once from the same distance - more than two refusals means the print is wrong for that microphone. **Record:** whether the turn ran, and if it refused, the score and threshold. Source: `.dsh-scratch/voice-field-test-report.md` §5 |
| T7 | **Desktop-microphone voice** | **NOT-TESTABLE** | there is **no `owner-desktop.json`**; the module's fallback resolves a desktop clip to the **phone** print, and the module's own docstring says *"a print trained on one scores the other lower"* - so a PC-mic test may refuse **legitimately** and would not tell us anything new. Measured in `.dsh-scratch/voice-field-test-report.md` §6 | **the owner** trains the PC microphone (Settings → Voice), then an agent re-runs the synthetic refusal with `mic=desktop` |
| T8 | **#355 - Jarvis's face on the phone's Live screen** (merged 2026-10-13 05:30) | **NOT TESTED on a device** | the phone is **disconnected**; the change cannot be seen or driven from this machine | **the owner**, on the phone: start Jarvis Live and look for the face as the largest element |
| T9 | **#356 - the silent mic, the face-size options, and the idle "Playing on your PC" plate** (merged 05:54) | **NOT TESTED on a device** | same - phone disconnected. **Three separate defects, one row each is owed when it is driven** | **the owner**, on the phone: tap and hold the mic; change the face size; check the PC plate when nothing is playing |
| T10 | **#357 - "Choose a model" lands on the Models plate** (merged 05:50) | **NOT TESTED on a device** | same - phone disconnected | **the owner**, on the phone: when the plate says a model is missing, tap **Choose a model** |
| T11 | **#361 - the approval toast's where-to-approve line stays visible** (merged 06:37; the brief called this "the notification's fixed wording") | **NOT TESTED** | it must be **seen on his desktop with a card actually raised**; no card was raised to look at | **the owner**, at the PC: raise any approval card and look at the toast; or an agent at the machine |
| T12 | **Settings through the MODEL path** | **NOT TESTED** | every settings turn tonight was answered by the **fixed phrase grammar** - `X-Jarvis-Route: {"lane": "no AI model", "quick": "settings_bool"}` - so no model was ever asked to change a setting. **The reported "both Ollama lanes down" is now MEASURED, not reported:** this pass ran `tools/check_lanes.py` (read-only: *"starts nothing, stops nothing … writes no file"*) and it printed **`LANE DOWN everyday port 11436`** and **`LANE DOWN coding port 11435`** (both `WinError 10061`), **`NOT HEALTHY - 2 lane(s) DOWN`**, **exit code 1**. So an unmatched sentence could not have been answered by a local model tonight at all | **an agent**, once the lanes are back: the tool prints the exact command for each (`Start-ScheduledTask -TaskName 'Jarvis Ollama - Everyday model (RTX 2060)'` and `… 'Jarvis Ollama - Coding model (RTX 2080 Super)'`) - starting them is the **owner's** machine, so the owner or an agent at the PC. Then send an unmatched sentence and read `X-Jarvis-Route` |
| T13 | **The two apps refreshing live after a setting changes by asking** | **NOT TESTED** | **neither UI was driven**: the settings test changed the value on the backend and read the store, and its own report says the live app was *"NOT TESTED"* (§4). The backend applied the change; whether the open window redrew is unmeasured | **the owner** (or an agent with the desktop app open): type a cosmetic change, then watch the Settings screen and the animal without touching anything |
| T14 | **The tray menu's trimmed rows (#353, merged 05:08)** | **NOT TESTED on his desktop** | the earlier pass could not read the tray at all - *"the tray icon is inside the 'Show Hidden Icons' overflow and a right-click produced no readable menu"* - and nothing tonight opened it | **the owner**, at the PC: open the tray and check that ~12 rows show and the rest are under **More…**; or an agent sitting at the machine |

### The one existing table this pass had to touch - checked, not assumed

In **Conversation-driven features - preflight coverage and real turns** (the table at the end), the row
`"what asks first"` reads *"read and switched, not driven by a turn"*. **That row is unchanged** - tonight
did not move an asks-first tier, and claiming otherwise would be exactly the kind of overstatement this
document exists to prevent. What **is** new is that **a settings change has now been driven by a real
typed turn**, which that table had no row for at all, so a row was added for it, carrying the model-path
caveat from T12. No other existing row's verdict changes tonight: the five PASS rows above are new
measurements, and the merges they belong to (#353-#357, #361) postdate every build the 127-feature table
was measured against.

### The one-sentence answer to the owner's question

**What is left, and who can do it: five things passed tonight on the live PC; of the ten that did not, one
needs his voice and one needs the PC microphone trained (both his, minutes of work), three are the merged
phone changes waiting for the phone to be plugged back in, one needs a card seen on his desktop, one needs
the two local Ollama lanes started (verified down tonight, exit 1) before a model-path settings test is
even possible, one needs the apps left open while a setting changes, and one needs the tray opened at the
machine.**

## The headline: features that have NEVER run on a real device

> **Overtaken 2026-10-11, later the same day:** the second pass above drove **43 of the 45** in this queue on real hardware and could not drive 2 (crisis-help and home-status) - the phone on real CI builds and locally-built branches of #294, the desktop on 0.2.140. The list below is left as it was written that night; read the **Second pass** verdicts above for what each one did when it was driven.

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

## The 128 features

`surface` is the repo's own field. `evidence` names the file and line the verdict came from.

| # | feature | group | surface | status | build it ran against | evidence |
|---|---|---|---|---|---|---|
| 1 | Type a message and read the answer (`typing`) | Talking | both | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:139 |
| 2 | Check a prompt before you send it (`prompt-coach`) | Talking | both | **SCREEN** <br>was `FIELD-TESTED` | phone 0.2.0 installed 2026-10-11 01:17 - **37 commits behind main** <br>desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/phone-pass-2026-10-11/README.md:80<br>/.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:23 |
| 3 | The talk button (`talk-button`) | Talking | both | **SCREEN** <br>was `FIELD-TESTED` | phone 0.2.0 installed 2026-10-11 01:17 - **37 commits behind main** <br>desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/phone-pass-2026-10-11/README.md:31<br>/.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:32 |
| 4 | Say "Hey Jarvis" (`wake-word`) | Talking | both | **SCREEN** <br>was `TEST-VERIFIED ONLY` | never ran on a device | jarvis_wakeword.py, test_wakeword.py, train_wakeword.py |
| 5 | Jarvis reads its answers aloud (`read-aloud`) | Talking | both | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:19 |
| 6 | Short answers to spoken questions (`spoken-style`) | Talking | both | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:19 |
| 7 | Teach Jarvis your voice (`voice-training`) | Talking | both | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:42 |
| 8 | How strict the voice check is (`voice-check`) | Talking | both | **SCREEN** <br>was `NEVER TESTED` | never ran on a device | only a review mentions it: /.dsh-scratch/device-tour/README.md:79 |
| 9 | The voice Jarvis speaks with (`custom-voices`) | Talking | both | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/sweep-results.tsv:160 |
| 10 | How Jarvis talks (`manner`) | Talking | both | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/sweep-results.tsv:97 |
| 11 | Interrupt Jarvis while it talks (`interrupt`) | Talking | both | **SCREEN** <br>was `NEVER TESTED` | never ran on a device | only a review mentions it: /.dsh-scratch/device-tour/README.md:36 |
| 12 | Jarvis Live (`live`) | Talking | both | **SCREEN** <br>was `TEST-VERIFIED ONLY` | never ran on a device | jarvis_live.py, jarvis_live_photo_test.py, test_browser_control_live.py, test_live.py |
| 13 | The extras around Live (`live-extras`) | Talking | both | **SCREEN** <br>was `NEVER TESTED` | never ran on a device | only a review mentions it: /.dsh-scratch/device-tour/README.md:12 |
| 14 | Talk-to-type (`talk-to-type`) | Talking | desktop | **SCREEN** <br>was `NOT FOUND` | never ran on a device | no evidence either way: no pass record, no suite and no review names it |
| 15 | The whole conversation, and carrying it on (`chat-thread`) | Talking | both | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:174 |
| 16 | Temporary chat (`temporary-chat`) | Talking | both | **SCREEN** <br>was `TEST-VERIFIED ONLY` | never ran on a device | test_temporary_chat.py |
| 17 | Search what was said (`history-search`) | Talking | both | **SCREEN** <br>was `NOT FOUND` | never ran on a device | no evidence either way: no pass record, no suite and no review names it |
| 18 | The morning briefing (`briefing`) | Talking | both | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:9 |
| 19 | Timers, alarms, reminders and lists (`coming-up`) | Talking | both | **BLOCKED** <br>was `NEVER TESTED` | never ran on a device | only a review mentions it: /.dsh-scratch/device-tour/README.md:48 |
| 20 | Today (`today`) | Talking | both | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/sweep-results.tsv:142 |
| 21 | Widgets you describe (`widgets`) | Talking | both | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:149 |
| 22 | Background jobs (`jobs`) | Talking | both | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/sweep-results.tsv:49 |
| 23 | What Jarvis is doing right now (`now`) | Talking | both | **SCREEN** <br>was `TEST-VERIFIED ONLY` | never ran on a device | gen_own_network_cases.py |
| 24 | How much Jarvis may interrupt you (`attention-budget`) | Talking | both | **SCREEN** <br>was `TEST-VERIFIED ONLY` | never ran on a device | test_attention_budget.py |
| 25 | Focus session (`focus`) | Talking | both | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/sweep-results.tsv:34 |
| 26 | The Memory tab (`memory-tab`) | Memory | desktop | **BLOCKED** <br>was `NOT FOUND` | never ran on a device | no evidence either way: no pass record, no suite and no review names it |
| 27 | Facts Jarvis saved by itself (`memory-saved`) | Memory | both | **BLOCKED** <br>was `FIELD-TESTED (first pass); BLOCKED (later top-up)` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/chat-turn.log:4 <br>**Corrected 2026-10-13 - BLOCKED, never a pass:** the `brain.memory.*` menus are hidden on this phone by **"Hide memory lists and chat history"**, which only the owner's fingerprint can change, so Find does not offer them (`docs/FIELD-TEST-2026-10-12-TOPUP.md:113`; the fingerprint prompt itself is measured at `docs/FIELD-TEST-2026-10-12-TOPUP-3.md:82`). |
| 28 | Facts waiting for your yes (`memory-waiting`) | Memory | both | **SCREEN** <br>was `FIELD-TESTED (first pass); PARTIAL (later top-up)` | phone 0.2.0 installed 2026-10-11 01:17 - **37 commits behind main** <br>desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/phone-pass-2026-10-11/README.md:59<br>/.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:303 <br>**Corrected 2026-10-13 - PARTIAL, never a pass:** **"The row is real; the content behind it is the owner's fingerprint"** - the section is reachable and reads `Hidden. Tap Show and confirm it is you.` (`docs/FIELD-TEST-2026-10-12-TOPUP-3.md:72`; the first top-up had it **BLOCKED**, `docs/FIELD-TEST-2026-10-12-TOPUP.md:114`). |
| 29 | What Jarvis knows about you (`memory-known`) | Memory | desktop | **BLOCKED** <br>was `NOT FOUND` | never ran on a device | no evidence either way: no pass record, no suite and no review names it |
| 30 | People and things (`memory-people`) | Memory | phone | **BLOCKED** <br>was `FIELD-TESTED (first pass); BLOCKED (later top-up)` | phone 0.2.0 installed 2026-10-11 01:17 - **37 commits behind main** | /.dsh-scratch/phone-pass-2026-10-11/README.md:32 <br>**Corrected 2026-10-13 - BLOCKED, never a pass:** the `brain.memory.*` menus are hidden on this phone by **"Hide memory lists and chat history"**, which only the owner's fingerprint can change, so Find does not offer them (`docs/FIELD-TEST-2026-10-12-TOPUP.md:115`; re-stated `docs/FIELD-TEST-2026-10-12-TOPUP-3.md:83`). |
| 31 | Always keep in mind (`pinned-facts`) | Memory | both | **BLOCKED** <br>was `NEVER TESTED` | never ran on a device | only a review mentions it: /.dsh-scratch/device-tour/README.md:68 |
| 32 | Between us (`between-us`) | Memory | both | **BLOCKED** <br>was `TEST-VERIFIED ONLY` | never ran on a device | test_between_us.py |
| 33 | Topics (`topics`) | Memory | both | **SCREEN** <br>was `FIELD-TESTED` | phone 0.2.0 installed 2026-10-11 01:17 - **37 commits behind main** <br>desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/phone-pass-2026-10-11/README.md:44<br>/.dsh-scratch/desktop-pass-2026-10-11/chat-turn.log:4 |
| 34 | The learning switches (`memory-learning`) | Memory | both | **BLOCKED** <br>was `FIELD-TESTED (first pass); BLOCKED (later top-up)` | phone 0.2.0 installed 2026-10-11 01:17 - **37 commits behind main** <br>desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/phone-pass-2026-10-11/README.md:58<br>/.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:18 <br>**Corrected 2026-10-13 - BLOCKED, never a pass:** the `brain.memory.*` menus are hidden on this phone by **"Hide memory lists and chat history"**, which only the owner's fingerprint can change, so Find does not offer them (`docs/FIELD-TEST-2026-10-12-TOPUP.md:116`; re-stated `docs/FIELD-TEST-2026-10-12-TOPUP-3.md:84`). |
| 35 | The wiki Jarvis builds (`wiki`) | Memory | both | **SCREEN** <br>was `FIELD-TESTED` | phone 0.2.0 installed 2026-10-11 01:17 - **37 commits behind main** <br>desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/phone-pass-2026-10-11/README.md:54<br>/.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:134 |
| 36 | Deep questions (`deep-questions`) | Memory | both | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:24 |
| 37 | What did I believe on this date? (`memory-as-of`) | Memory | phone | **BLOCKED** <br>was `NEVER TESTED` | never ran on a device | only a review mentions it: /.dsh-scratch/device-tour/.evidence/transcript-G.txt:654 |
| 38 | Bring in old chats (`import-chats`) | Memory | desktop | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/sweep-results.tsv:114 |
| 39 | Your past chats (`history`) | Memory | both | **SCREEN** <br>was `FIELD-TESTED (first pass); PARTIAL (later top-up)` | phone 0.2.0 installed 2026-10-11 01:17 - **37 commits behind main** <br>desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/phone-pass-2026-10-11/README.md:40<br>/.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:172 <br>**Corrected 2026-10-13 - PARTIAL, never a pass:** **"The screen works and states its own setting; the conversation list is the owner's to unlock"** - Home -> `Earlier chats` opened `History`, and its `CONVERSATIONS` list reads `Hidden. Tap Show and confirm it is you.` (`docs/FIELD-TEST-2026-10-12-TOPUP-3.md:74`; the first top-up had it **BLOCKED**, `docs/FIELD-TEST-2026-10-12-TOPUP.md:50`). |
| 40 | Chat tags (`chat-tags`) | Memory | both | **BLOCKED** <br>was `TEST-VERIFIED ONLY` | never ran on a device | test_chat_tags.py |
| 41 | Forget a time frame (`forget-range`) | Memory | both | **BLOCKED** <br>was `FIELD-TESTED (first pass); BLOCKED (later top-up)` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:175 <br>**Corrected 2026-10-13 - BLOCKED, never a pass:** **"it is an action taken by asking, and the phone's own chat history and memory lists are behind the same gate"** (`docs/FIELD-TEST-2026-10-12-TOPUP-3.md:85`; the first top-up had it **BLOCKED** too, `docs/FIELD-TEST-2026-10-12-TOPUP.md:51`). |
| 42 | Galaxy (`galaxy`) | Memory | desktop | **SCREEN** <br>was `FIELD-TESTED` | phone 0.2.0 installed 2026-10-11 01:17 - **37 commits behind main** <br>desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/phone-pass-2026-10-11/README.md:48<br>/.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:209 |
| 43 | Look at this (`look-at-this`) | Screen and pictures | both | **DRIVEN** <br>was `NEVER TESTED` | never ran on a device | only a review mentions it: /.dsh-scratch/device-tour/.evidence/transcript-D.txt:44 |
| 44 | Watch with me (`watch-with-me`) | Screen and pictures | both | **DRIVEN** <br>was `NEVER TESTED` | never ran on a device | only a review mentions it: /.dsh-scratch/device-tour/.evidence/transcript-D.txt:44 |
| 45 | Picture mode (`picture-mode`) | Screen and pictures | both | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:164 |
| 46 | Photo to reminder (`photo-reminder`) | Screen and pictures | both | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/sweep-results.tsv:140 |
| 47 | Show Jarvis the camera in Live (`live-camera`) | Screen and pictures | phone | **SCREEN** <br>was `NEVER TESTED` | never ran on a device | only a review mentions it: /.dsh-scratch/device-tour/.evidence/transcript-D.txt:85 |
| 48 | Quiz me on a text (`quiz`) | Screen and pictures | both | **SCREEN** <br>was `FIELD-TESTED` | phone 0.2.0 installed 2026-10-11 01:17 - **37 commits behind main** <br>desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/phone-pass-2026-10-11/README.md:33<br>/.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:102 |
| 49 | My study decks (`decks`) | Notes and files | both | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:146 |
| 50 | Write a note for you (`notes-write`) | Notes and files | both | **SCREEN** <br>was `NOT FOUND` | never ran on a device | no evidence either way: no pass record, no suite and no review names it |
| 51 | Folders Jarvis may look in (`folders`) | Notes and files | both | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:13 |
| 52 | Ask about a PDF, a Word file or a Notion page (`documents`) | Notes and files | both | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:40 |
| 53 | Tutorials and the FAQ (`tutorials`) | Notes and files | both | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:40 |
| 54 | PC help (`pc-help`) | Notes and files | phone | **SCREEN** <br>was `TEST-VERIFIED ONLY` | never ran on a device | jarvis_pc_help.py, test_pc_help.py, gen_pc_help_cases.py |
| 55 | Web search (`web-search`) | Notes and files | both | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:26 |
| 56 | A browser without a window (`browser-engine`) | Notes and files | both | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:187 |
| 57 | What's new on GitHub (`github-watchlist`) | Notes and files | both | **SCREEN** <br>was `NOT FOUND` | never ran on a device | no evidence either way: no pass record, no suite and no review names it |
| 58 | Talk to a chatbot for me (`chatbot`) | Notes and files | both | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:10 |
| 59 | Deal with customer support for me (`support`) | Notes and files | both | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/sweep-results.tsv:34 |
| 60 | Projects (`projects`) | Notes and files | both | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:150 |
| 61 | Goals (`goals`) | Notes and files | both | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/sweep-results.tsv:71 |
| 62 | Progress (`progress`) | Notes and files | both | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:40 |
| 63 | Spending summaries (`spending`) | Money and health | both | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:109 |
| 64 | Retirement what-if (`retirement`) | Money and health | both | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/sweep-results.tsv:172 |
| 65 | Chatbot keys and a monthly money limit (`chatbot-money`) | Money and health | desktop | **NOT-TESTABLE** <br>was `FIELD-TESTED (first pass); NOT-TESTABLE (later top-up)` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:10 <br>**Corrected 2026-10-13 - NOT-TESTABLE, never a pass:** **"needs chatbot API keys and a monthly amount the owner sets on the PC"** (`docs/FIELD-TEST-2026-10-12-TOPUP.md:126`). |
| 66 | Health and money facts wait for your yes (`sensitive-facts`) | Money and health | both | **BLOCKED** <br>was `NEVER TESTED` | never ran on a device | only a review mentions it: /.dsh-scratch/device-tour/README.md:42 |
| 67 | Crisis help (`crisis-help`) | Money and health | both | **NOT-TESTABLE** <br>was `NOT FOUND` | never ran on a device | no evidence either way: no pass record, no suite and no review names it |
| 68 | Ask how the house is (`home-status`) | Home | both | **NOT-TESTABLE** <br>was `NOT FOUND` | never ran on a device | no evidence either way: no pass record, no suite and no review names it |
| 69 | Lights, plugs and fans (`lights`) | Home | both | **NOT-TESTABLE** <br>was `FIELD-TESTED (first pass); NOT-TESTABLE (later top-up)` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:3 <br>**Corrected 2026-10-13 - NOT-TESTABLE, never a pass:** **"needs the owner's Home Assistant and devices paired to it; the page says Home Assistant needs Home Assistant set up for Jarvis on the PC"** (`docs/FIELD-TEST-2026-10-12-TOPUP.md:121`). |
| 70 | Locks, doors, alarms and covers (`locks`) | Home | both | **NOT-TESTABLE** <br>was `FIELD-TESTED (first pass); NOT-TESTABLE (later top-up)` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:37 <br>**Corrected 2026-10-13 - NOT-TESTABLE, never a pass:** **"same as `lights`: Home Assistant, not set up here, and locks always keep a card of their own"** (`docs/FIELD-TEST-2026-10-12-TOPUP.md:122`). |
| 71 | Read your own calendar (`calendar`) | Home | desktop | **NOT-TESTABLE** <br>was `FIELD-TESTED (first pass); NOT-TESTABLE (later top-up)` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:191 <br>**Corrected 2026-10-13 - NOT-TESTABLE, never a pass:** the page's own words - **"Not included: your calendar is not set up for Jarvis on this PC."** (`docs/FIELD-TEST-2026-10-12-TOPUP.md:117`). |
| 72 | Weather and the sky behind the animals (`weather-sky`) | Home | both | **NOT-TESTABLE** <br>was `FIELD-TESTED (first pass); NOT-TESTABLE (later top-up)` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:104 <br>**Corrected 2026-10-13 - NOT-TESTABLE, never a pass:** the page's own words - **"Not included: the weather is not set up for Jarvis on this PC."** (`docs/FIELD-TEST-2026-10-12-TOPUP.md:120`). |
| 73 | Jarvis reads your email (`email-read`) | Home | both | **NOT-TESTABLE** <br>was `FIELD-TESTED (first pass); NOT-TESTABLE (later top-up)` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:9 <br>**Corrected 2026-10-13 - NOT-TESTABLE, never a pass:** the page's own words - **"Not included: how many unread emails you have is not set up for Jarvis on this PC."** (`docs/FIELD-TEST-2026-10-12-TOPUP.md:118`). |
| 74 | Send an email for you (`email-send`) | Home | both | **NOT-TESTABLE** <br>was `FIELD-TESTED (first pass); NOT-TESTABLE (later top-up)` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/sweep-results.tsv:56 <br>**Corrected 2026-10-13 - NOT-TESTABLE, never a pass:** **"needs the owner's mail account (not set up here) and his approval, one card per email"** (`docs/FIELD-TEST-2026-10-12-TOPUP.md:123`). |
| 75 | Save a draft to your Drafts folder (`email-drafts`) | Home | desktop | **NOT-TESTABLE** <br>was `FIELD-TESTED (first pass); NOT-TESTABLE (later top-up)` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:170 <br>**Corrected 2026-10-13 - NOT-TESTABLE, never a pass:** **"needs the owner's mail account (not set up here)"** (`docs/FIELD-TEST-2026-10-12-TOPUP.md:124`). |
| 76 | Tidy the inbox by voice (`inbox-tidy`) | Home | both | **NOT-TESTABLE** <br>was `FIELD-TESTED (first pass); NOT-TESTABLE (later top-up)` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/sweep-results.tsv:57 <br>**Corrected 2026-10-13 - NOT-TESTABLE, never a pass:** **"needs the mail account the page says is not set up here, and the inbox routes read it"** (`docs/FIELD-TEST-2026-10-12-TOPUP.md:119`). |
| 77 | News headlines, and pages that change (`news-and-page-watches`) | Home | both | **SCREEN** <br>was `FIELD-TESTED` | phone 0.2.0 installed 2026-10-11 01:17 - **37 commits behind main** <br>desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/phone-pass-2026-10-11/README.md:22<br>/.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:29 |
| 78 | Pairing and the connection (`connection`) | Phone | both | **SCREEN** <br>was `FIELD-TESTED` | phone 0.2.0 installed 2026-10-11 01:17 - **37 commits behind main** <br>desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/phone-pass-2026-10-11/README.md:23<br>/.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:20 |
| 79 | Devices (`devices`) | Phone | both | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:12 |
| 80 | Let Jarvis read phone notifications (`phone-notifications`) | Phone | phone | **SCREEN** <br>was `TEST-VERIFIED ONLY` | never ran on a device | jarvis_phone_notifications.py, test_phone_notifications.py |
| 81 | Smartwatch notifications (`phone-watch`) | Phone | phone | **SCREEN** <br>was `NOT FOUND` | never ran on a device | no evidence either way: no pass record, no suite and no review names it |
| 82 | Floating Jarvis (`phone-floating`) | Phone | phone | **SCREEN** <br>was `NEVER TESTED` | never ran on a device | only a review mentions it: /.dsh-scratch/device-tour/.evidence/transcript-D.txt:22 |
| 83 | Quick Settings tiles (`phone-tiles`) | Phone | phone | **SCREEN** <br>was `NEVER TESTED` | never ran on a device | only a review mentions it: /.dsh-scratch/device-tour/docs/RESEARCH-AUDIT-2026-09-28.md:320 |
| 84 | Screen refresh rate (`phone-screen-rate`) | Phone | phone | **SCREEN** <br>was `FIELD-TESTED` | phone 0.2.0 installed 2026-10-11 01:17 - **37 commits behind main** <br>desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/phone-pass-2026-10-11/README.md:35<br>/.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:171 |
| 85 | Also on my phone (`also-on-phone`) | Phone | both | **SCREEN** <br>was `NOT FOUND` | never ran on a device | no evidence either way: no pass record, no suite and no review names it |
| 86 | Ring my phone (`find-phone`) | Phone | both | **DRIVEN** <br>was `TEST-VERIFIED ONLY` | never ran on a device | jarvis_find_phone.py, test_find_phone.py |
| 87 | What the phone deliberately does not do (`phone-limits`) | Phone | phone | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:78 |
| 88 | Appearance (`appearance`) | The PC itself | both | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/sweep-results.tsv:4 |
| 89 | Hang and crash notes (`crash-notes`) | The PC itself | desktop | **DRIVEN** <br>was `NOT FOUND` | never ran on a device | no evidence either way: no pass record, no suite and no review names it |
| 90 | Choose Jarvis's face (`faces`) | The PC itself | both | **SCREEN** <br>was `NEVER TESTED` | never ran on a device | only a review mentions it: /.dsh-scratch/device-tour/README.md:63 |
| 91 | Animal options (`animal-options`) | The PC itself | both | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:195 |
| 92 | Set up Jarvis (`first-run`) | The PC itself | desktop | **SCREEN** <br>was `NOT FOUND` | never ran on a device | no evidence either way: no pass record, no suite and no review names it |
| 93 | Show or hide menus (`menu-visibility`) | The PC itself | both | **SCREEN** <br>was `TEST-VERIFIED ONLY` | never ran on a device | test_menu_visibility.py |
| 94 | Keyboard shortcuts (`shortcuts`) | The PC itself | desktop | **SCREEN** <br>was `FIELD-TESTED` | phone 0.2.0 installed 2026-10-11 01:17 - **37 commits behind main** | /.dsh-scratch/phone-pass-2026-10-11/README.md:36 |
| 95 | Models (`models`) | The PC itself | both | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/chat-turn.log:19 |
| 96 | Compute (`compute`) | The PC itself | both | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/sweep-results.tsv:41 |
| 97 | Skills (`skills`) | The PC itself | both | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/sweep-results.tsv:192 |
| 98 | Memory on the Model page (`model-memory`) | The PC itself | desktop | **SCREEN** <br>was `NOT FOUND` | never ran on a device | no evidence either way: no pass record, no suite and no review names it |
| 99 | Notifications (`notifications`) | The PC itself | desktop | **SCREEN** <br>was `TEST-VERIFIED ONLY` | never ran on a device | jarvis_phone_notifications.py, test_phone_notifications.py |
| 100 | Starting Jarvis for you (`start-jarvis`) | The PC itself | desktop | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:22 |
| 101 | The Work tab (`work-tab`) | The PC itself | desktop | **BLOCKED** <br>was `NEVER TESTED` | never ran on a device | only a review mentions it: /.dsh-scratch/device-tour/docs/CONTINUITY-AUDIT-2026-09-26.md:39 |
| 102 | Jobs that keep going after the chat ends (`job-list`) | The PC itself | both | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:36 |
| 103 | Hardware and models (`hardware`) | The PC itself | both | **SCREEN** <br>was `FIELD-TESTED` | phone 0.2.0 installed 2026-10-11 01:17 - **37 commits behind main** <br>desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/phone-pass-2026-10-11/README.md:38<br>/.dsh-scratch/desktop-pass-2026-10-11/sweep-results.tsv:76 |
| 104 | The second graphics card (`second-card`) | The PC itself | both | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/chat-turn.log:5 |
| 105 | The big model (slow) (`big-model`) | The PC itself | both | **BLOCKED** <br>was `TEST-VERIFIED ONLY` | never ran on a device | jarvis_big_model.py, test_big_model.py, gen_big_model_cases.py |
| 106 | Updates (`updates`) | The PC itself | both | **SCREEN** <br>was `FIELD-TESTED` | phone 0.2.0 installed 2026-10-11 01:17 - **37 commits behind main** | /.dsh-scratch/phone-pass-2026-10-11/README.md:71 |
| 107 | Check for tool updates (`tool-updates`) | The PC itself | desktop | **SCREEN** <br>was `FIELD-TESTED` | phone 0.2.0 installed 2026-10-11 01:17 - **37 commits behind main** <br>desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/phone-pass-2026-10-11/README.md:71<br>/.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:37 |
| 108 | The settings file, the logs and starting with Windows (`settings-file`) | The PC itself | desktop | **SCREEN** <br>was `FIELD-TESTED` | phone 0.2.0 installed 2026-10-11 01:17 - **37 commits behind main** <br>desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/phone-pass-2026-10-11/README.md:97<br>/.dsh-scratch/desktop-pass-2026-10-11/chat-turn.log:1 |
| 109 | What this backend supports (`backend-supports`) | The PC itself | both | **SCREEN** <br>was `FIELD-TESTED` | phone 0.2.0 installed 2026-10-11 01:17 - **37 commits behind main** <br>desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/phone-pass-2026-10-11/README.md:50<br>/.dsh-scratch/desktop-pass-2026-10-11/chat-turn.log:1 |
| 110 | About Jarvis (`about`) | The PC itself | both | **SCREEN** <br>was `NOT FOUND` | never ran on a device | no evidence either way: no pass record, no suite and no review names it |
| 111 | The big HUD window (`hud-window`) | The PC itself | desktop | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:187 |
| 112 | Backups (`backup`) | The PC itself | both | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:59 |
| 113 | Accounts and keys (`accounts`) | The PC itself | desktop | **NOT-TESTABLE** <br>was `FIELD-TESTED (first pass); NOT-TESTABLE (later top-up)` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/sweep-results.tsv:2 <br>**Corrected 2026-10-13 - NOT-TESTABLE, never a pass:** **"the owner's accounts and keys - they are his, and the page keeps them under `Accounts`"** (`docs/FIELD-TEST-2026-10-12-TOPUP.md:125`). |
| 114 | What Jarvis can reach (`reach`) | The PC itself | both | **SCREEN** <br>was `FIELD-TESTED` | phone 0.2.0 installed 2026-10-11 01:17 - **37 commits behind main** <br>desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/phone-pass-2026-10-11/README.md:50<br>/.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:5 |
| 115 | Undo (`undo`) | The PC itself | both | **SCREEN** <br>was `FIELD-TESTED` | phone 0.2.0 installed 2026-10-11 01:17 - **37 commits behind main** <br>desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/phone-pass-2026-10-11/README.md:76<br>/.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:81 |
| 116 | Activity: cards you already decided (`past-approvals`) | The PC itself | both | **BLOCKED** <br>was `FIELD-TESTED (first pass); BLOCKED (later top-up)` | phone 0.2.0 installed 2026-10-11 01:17 - **37 commits behind main** <br>desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/phone-pass-2026-10-11/README.md:21<br>/.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:13 <br>**Corrected 2026-10-13 - BLOCKED, never a pass:** **"it lists what the owner already decided; nothing to read until he has"** (`docs/FIELD-TEST-2026-10-12-TOPUP.md:130`). |
| 117 | Limits and frequency (`limits`) | The PC itself | both | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:10 |
| 118 | Approval cards (`approvals`) | Safety | both | **BLOCKED** <br>was `FIELD-TESTED (first pass); BLOCKED (later top-up)` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:28 <br>**Corrected 2026-10-13 - BLOCKED, never a pass:** **"an approval card needs a person to decide it; raising one and answering it are both the owner's"** (`docs/FIELD-TEST-2026-10-12-TOPUP.md:129`). |
| 119 | What asks first (`what-asks-first`) | Safety | both | **SCREEN** <br>was `NEVER TESTED` | never ran on a device | only a review mentions it: /.dsh-scratch/device-tour/README.md:78 |
| 120 | Lock Jarvis, and hide what it remembers (`app-lock`) | Safety | both | **BLOCKED** <br>was `FIELD-TESTED (first pass); BLOCKED (later top-up)` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:21 <br>**Corrected 2026-10-13 - BLOCKED, never a pass:** **"turning it off or on is the owner's own Windows Hello / phone lock; a harness cannot answer a fingerprint prompt"** (`docs/FIELD-TEST-2026-10-12-TOPUP.md:127`). |
| 121 | Hand a captcha to your phone ("Solve it here") (`captcha-handoff`) | Safety | both | **SCREEN** <br>was `NEVER TESTED` | never ran on a device | only a review mentions it: /.dsh-scratch/device-tour/.evidence/transcript-G.txt:483 |
| 122 | When the connection is catching up (`stale-link`) | Safety | both | **BLOCKED** <br>was `FIELD-TESTED (first pass); BLOCKED (later top-up)` | phone 0.2.0 installed 2026-10-11 01:17 - **37 commits behind main** <br>desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/phone-pass-2026-10-11/README.md:97<br>/.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:20 <br>**Corrected 2026-10-13 - BLOCKED, never a pass:** **"Find -> `catching up` says `Nothing matches that.` - no row on the phone"** (`docs/FIELD-TEST-2026-10-12-TOPUP.md:64`). |
| 123 | Stop everything (`stop-everything`) | Safety | both | **SCREEN** <br>was `FIELD-TESTED` | phone 0.2.0 installed 2026-10-11 01:17 - **37 commits behind main** <br>desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/phone-pass-2026-10-11/README.md:94<br>/.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:54 |
| 124 | Trust: content risk and the audit chain (`trust`) | Safety | both | **BLOCKED** <br>was `FIELD-TESTED (first pass); BLOCKED (later top-up)` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/chat-turn.log:6 <br>**Corrected 2026-10-13 - BLOCKED, never a pass:** **"the audit chain's own state is set by approvals the owner decides"** (`docs/FIELD-TEST-2026-10-12-TOPUP.md:128`). |
| 125 | A warning when text tried to rush you (`rush-latch`) | Safety | phone | **SCREEN** <br>was `NOT FOUND` | never ran on a device | no evidence either way: no pass record, no suite and no review names it |
| 126 | Jarvis marks what it read from outside (`outside-text`) | Safety | both | **SCREEN** <br>was `NEVER TESTED` | never ran on a device | only a review mentions it: /.dsh-scratch/device-tour/.evidence/transcript-G.txt:1001 |
| 127 | Settings itself (`settings-entry`) | Safety | both | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/chat-turn.log:4 |
| 128 | Ask for a picture, and keep it (`pictures`) | Screen and pictures | both | **SCREEN** <br>was `PARTIAL` | phone, 2026-10-12 - the record names no build | /docs/FIELD-TEST-2026-10-12-TOPUP.md:52 |
| 129 | Change a setting by asking, in any words (`settings-by-asking`) | The PC itself | both | **DRIVEN** | live backend, 2026-10-12 | this document, third pass PASS T2 (typed "keep the animal still" and `still` went `false -> true` in the live store) - added 2026-10-15: the 129th entry had no row at all |
| 130 | The phone's read-only Galaxy picture (`galaxy`, 2026-10-26) | Memory | phone | **NOT-TESTABLE** | built at PR #869; CI compiled it and ran the phone JVM unit tests on 2026-10-26 (`build` passed in 7m41s, `phone-unit-tests` in 4m13s) | no human has run it on a phone or an emulator: the look and a real tap are unverified. Its layout is pinned to the desktop JavaScript at 1e-6 by `GalaxyPictureTest.kt`, which is a test, not a field test. |
| 131 | #889 the phone's model name and the "Model →" fallback door open the models list (`model-door`, 2026-10-27) | Phone | phone | **DRIVEN** | `jarvis-client-b7f7f86.apk`, v0.2.2881 | Home drew `The Galaxy →`, `Presets →`, `Model →` and a tap opened Brain's MODEL plate with the real models (`.dsh-scratch/PHONE-FEATURE-AUDIT-2026-10-27/README.md:33`). The lane **pill** is not drawn on this PC (`/api/status` names no lane or model), so what was driven is the "Model →" fallback; Face size was Hidden only *after* the run, so the Hidden and keyboard-up cases were **not** driven - at that build they removed the row (row 136). |
| 132 | #889 the PC's cloud setting shown read-only on the phone (`cloud-line`, 2026-10-27) | Phone | phone | **BLOCKED** | no build: the live PC sends no `cloud` block | The live `/api/presets` answer (13,482 B, read 2026-10-27) has no `cloud` key, so the phone draws nothing (`.dsh-scratch/PHONE-FEATURE-AUDIT-2026-10-27/README.md:36`). **Not a pass.** Only `CloudParityTest` pins the decode, off-device; merging #896 does not deploy the block. |
| 133 | #892 a typed answer read aloud in the PC's chosen voice (`read-aloud`, 2026-10-27) | Talking | phone | **DRIVEN** | `jarvis-client-081f5c3.apk`, v0.2.2874; Stop on `jarvis-client-37ec4f7.apk`, v0.2.2893 | The control appeared, a tap reached Stop within 0.25 s, logcat showed the app's own `AudioTrack` 24000 Hz mono `usage=16`, and the PC-voice clip was fetched and played (`.dsh-scratch/PHONE-FEATURE-AUDIT-2026-10-27/README.md:34`); Stop during a long clip passed 2026-10-27 05:14 (`README.md:35`). The audible tail after Stop was **not measured** - there is no device audio-capture path - and both builds predate this PR's fix. |
| 134 | #892 the withheld sentence on a refused read (`read-aloud-withheld`, 2026-10-27) | Talking | phone | **NOT-TESTABLE** | no APK built from the fix; the unit suite only | The sentence is **reachable in code** now - `HomeScreen.kt:3481` draws `offer.withheld?.let { … }` and `ReadAloud.kt:128-129` returns it only for the one privacy refusal - but **no phone was driven on this path**, so this is not a pass. Before the fix it could not be drawn at all (`.dsh-scratch/PHONE-FEATURE-AUDIT-2026-10-27/C-PARITY-FIT.md:99-119`). Re-test with an APK and a private-gated answer. |
| 135 | #892 a read stops when the phone leaves the app (`read-aloud-stop`, a51bb2285) | Talking | phone | **NOT-TESTABLE** | no APK built from the fix; `:app:testDebugUnitTest` green offline | `MainActivity`'s `ON_STOP` observer calls `JarvisRuntime.stopReadingAloud()`, and the read loop re-asks the live lock before every sentence (`.dsh-scratch/PHONE-FEATURE-AUDIT-2026-10-27/PATCHES-READY.md:12`). Its drive needs the APK this PR produces and a real power-button press - logcat `AudioTrack: stop`, no later `AF::Track: start` (`PATCHES-READY.md:37`) - so it is **not** a pass. |
| 136 | #889 the three Brain doors outlive the face and the keyboard (`model-door`, 47469fd28) | Home | phone | **NOT-TESTABLE** | no APK built from the fix; unit suite green, mutation-proved | `ModelDoorsRow` is drawn in `FaceBlock` and in `HomeScreen`'s `faceSize.hidden` branch, and a source pin fails if the caption gate returns (3 tests fail when it is put back) (`.dsh-scratch/PHONE-FEATURE-AUDIT-2026-10-27/PATCHES-READY.md:45-64`). The drive is the next action once an APK exists: Face size Hidden, keyboard up, then `Model →` (`PATCHES-READY.md:71`). |

## Method, and its limits, said plainly

1. The 128 entries come from `features/features.json`; no field in it records testing, so nothing here is read from the repo's own claim.
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
| **a setting changed by asking (any switch)** | yes - `settings_bool` / `settings_open` / the on-off phrases | **yes - 2026-10-12, a real typed turn** - *"keep the animal still"* applied and was reversed, and a loosening (*"turn on remembering sensitive topics automatically"*) raised a card and did **not** apply | .dsh-scratch/settings-turn-test-report.md §1-§2. **Through the MODEL path: NOT TESTED** - every settings turn was answered by the fixed grammar (`lane: "no AI model"`), and both Ollama lanes were verified DOWN (Third pass T12) |
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