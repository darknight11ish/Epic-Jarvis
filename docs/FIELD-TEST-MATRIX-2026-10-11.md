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

## The headline: features that have NEVER run on a real device

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
