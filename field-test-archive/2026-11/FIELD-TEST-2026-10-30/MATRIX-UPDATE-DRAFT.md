# Matrix-update DRAFT v2 — 2026-10-30 field-test evidence → `docs/FIELD-TEST-MATRIX-2026-10-11.md`

**Status: DRAFT ONLY — NOT APPLIED.** Prepared by teammate `docs-stale` for the Lead / **record owner** to review.
Nothing in the shared matrix, `docs/README.md` or any tracked file was changed. No push, no PR, no approval card touched.

**v2 (this file) folds in the SCREEN-row batch.** v1 covered the five rows the Lead named from the first/concurrent passes; v2 adds the 27 rows measured in `.dsh-scratch/FIELD-TEST-2026-10-30/REPORT.md` §"SCREEN-row batch 2026-10-30 18:05–18:10 PDT (read-only phone UI, 27 rows)" (REPORT.md lines 510–591; 115 raw dumps in `pass3\`). Evidence already in v1 is unchanged in substance; the only encoding change is explained in §2.

- **Matrix read:** `REPO\docs\FIELD-TEST-MATRIX-2026-10-11.md` in the primary checkout. That file is **clean and identical to `origin/main` (`263ea0d86`)** — verified with `git -C REPO status --short -- docs/FIELD-TEST-MATRIX-2026-10-11.md` (empty) and `git -C REPO diff origin/main --stat -- docs/FIELD-TEST-MATRIX-2026-10-11.md` (empty). (The primary checkout's *HEAD* is stale at `b0aabefcd`, but this file agrees with `origin/main`.)
- **Evidence read:** `.dsh-scratch/FIELD-TEST-2026-10-30/REPORT.md` (first pass, the 17:52–17:56 concurrent pass, and the 18:05–18:10 SCREEN-row batch), `.dsh-scratch/FIELD-TEST-FINAL-2026-10-30.md`, `docs/FIELD-TEST-2026-10-13-PHONE-PASS.md`, `docs/FIELD-TEST-2026-10-12-TOPUP-3.md`, `docs/FIELD-TEST-2026-10-12-TOPUP.md`, and the two Gemini documents in Downloads.
- **Gemini rulings status:** **F5 is still PENDING.** `gemini_review_field_test_gaps_2026_10_30.md` §7 (lines 178–191) *requests* F1–F6; the newest Gemini answer on disk is `gemini_rulings_q1_to_q8_maxout_continuation_2026_10_30.md` (17:50 PDT), which rules Q1–Q8 only (Q4 app-control and Q5 deploy order are adjacent but do **not** rule F5), and `gemini_review_of_maxout_continuation_2026_10_30.md` contains no F1–F6 ruling either. Every item that needs a record ruling below is marked **`[PENDING: F5 ruling]`**.
- **Batch method, stated up front (it bounds every status below):** the batch was **read-only** — no setting toggled, no model switched, no style added, no backup made, no folder added, no notification access granted, no Live session started, no chat message sent (a chat turn writes history, so it was not done); no live API, no token, no install, no approval. The batch deliberately skipped the memory-gated rows (`history`, `memory-*`, `pinned-facts`, `between-us`, `chat-tags`, `sensitive-facts`, `forget-range`, row 130 galaxy) because opening them shows the owner's biometric `Hidden. Tap Show and confirm it is you.` gate. Phone build for all 27 rows: **0.2.3261 / versionCode 1000003261 / main `21add9d53` / installed 2026-10-30 12:01:36**.

---

## 1. Verified baseline inventory of the matrix as it stands today

I re-counted the numbered feature table from the document itself (table header line 358, data rows from line 360 to line 495; one row per number, no gaps, no duplicates). This is an arithmetic count of the document's rows, **not a new test**:

| state | rows |
|---|---|
| DRIVEN | **10** |
| SCREEN | **93** |
| BLOCKED | **19** |
| NOT-TESTABLE | **14** |
| NEVER | 0 |
| **total** | **136** |

That agrees with the field-test report and the Gemini gaps document. **The matrix's own in-place dated correction (2026-10-15) counts a different set and must stay visible:** it says **129** rows — DRIVEN **5** / SCREEN **93** / BLOCKED **19** / NOT-TESTABLE **12** / NEVER 0. Rows 129–136 were added after that note (row 129 says so itself; 130–136 carry their own 2026-10-26/27 evidence). So **136 is arithmetic over rows 1–136, not a number written in the matrix**, and this draft does not rewrite the 2026-10-15 table (§9 proposes the dated note that keeps it consistent).

---

## 2. Encoding: PARTIAL is not one of the matrix's five states

The field-test records use **PASS / PARTIAL / NOT-REACHABLE**; the matrix's states are **DRIVEN / SCREEN / BLOCKED / NOT-TESTABLE / NEVER**. To avoid inventing a state (the Lead's latest instruction), this v2 uses the **smallest consistent mapping**:

| field-test verdict | matrix status proposed | why |
|---|---|---|
| **PASS** (read-only readout operated and observed) | **DRIVEN** | the feature *is* the readout; it was opened and its real data observed — operated + effect observed. The batch's own PASS definition says exactly this (REPORT.md:526–531). |
| **PARTIAL** (screen/control opened and read; the write an effect needs was not performed) | keep the row's honest existing state — **SCREEN** where the screen was found and read; **BLOCKED** unchanged where the blocker is the owner's (rows 118/120, see flag) — **plus a dated `PARTIAL` note in the evidence column** | SCREEN is the matrix's own "found and read; behaviour never exercised", which is exactly what the batch did. **`[PENDING: F5 ruling]`** on whether PARTIAL becomes a sixth state |
| **NOT-REACHABLE** (needs the owner's accounts) | **NOT-TESTABLE** | "needs something absent" — the owner's sign-ins |
| **not claimed** (83 phone-tiles, 94 shortcuts, 92 first-run) | **no change** | the batch claimed nothing either way |

**Variant P (alternative, if the record owner adopts `PARTIAL` as a sixth state):** the per-row diffs below are Variant S. Variant P changes only the **status cell** of the 19 rows that carry a dated `PARTIAL` note (rows 19, 21, 39 and the 16 batch PARTIAL rows 12, 24, 25, 53, 56, 80, 81, 82, 88, 90, 91, 93, 99, 112, 119, 121) to `**PARTIAL** <br>was ...`, leaving every other cell exactly as proposed here. Rows 118/120 stay BLOCKED in both variants (see §7 flag). §6 gives both inventories.

**What changed from v1:** v1 proposed `**PARTIAL**` as the status of rows 19/21/39 because the Lead's earlier instruction asked for it. Per the latest instruction ("smallest consistent mapping, without inventing a state") v2 keeps those rows' status cells at the matrix's states (SCREEN) and puts the dated `PARTIAL` evidence/note in the evidence column. The evidence and the "never PASS" conclusions are identical; Variant P restores v1's status cells.

---

## 3. Proposed diff A — the five rows from the first/concurrent passes

Each block is one whole-line replacement. **Nothing is applied.**

### Row 19 — `coming-up` — BLOCKED → **SCREEN** with a dated `PARTIAL` note (never PASS)

BEFORE (line 378, exact):

```
| 19 | Timers, alarms, reminders and lists (`coming-up`) | Talking | both | **BLOCKED** <br>was `NEVER TESTED` | never ran on a device | only a review mentions it: /.dsh-scratch/device-tour/README.md:48 |
```

PROPOSED AFTER (Variant S):

```
| 19 | Timers, alarms, reminders and lists (`coming-up`) | Talking | both | **SCREEN** <br>was `BLOCKED` (the `screen declared=19 … composed=11` defect), `NEVER TESTED` before that | phone 0.2.3261, versionCode 1000003261, built from main `21add9d53`, installed 2026-10-30 12:01:36 | only a review mentions it: /.dsh-scratch/device-tour/README.md:48 <br>**Measured read-only 2026-10-30 17:52–17:56 PDT — PARTIAL: the plate was found and read, no behaviour exercised.** The Brain's **COMING UP** plate opened (a `Fold` control is present, which only an expanded plate has) and read, top to bottom: `Timers, alarms and reminders, kept on your PC. They go off on both apps while they are connected. …`, `They go off on your PC. This phone shows them while it is connected to it.`, `Words hidden. Tap Show and confirm it is you.` + `Show` (the reminder words are hidden by the same privacy setting, by design, and the times stay visible), `Nothing coming up. Say or type "set a timer for 10 minutes" or "remind me at 6 to call Mum".`, `Tell me when`, `Reminder for next time`, `To-do list` -> `Nothing on your to-do list.` + `Add`, `Standby schedule` -> `STANDBY AT 01:00` / `WAKE AT 07:00` + `Set up`, then `JARVIS CALENDAR` -> `Today, 30 October` / `Nothing today`. **The old blocker looks fixed on this build** (the 2026-10-11 record was `screen declared=19 … composed=11`, `found=false`) — **but this is not a PASS**: the PC reported nothing coming up and nothing on the to-do list, so no timer/reminder/alarm/to-do row existed to observe, and no action was driven by this read-only pass. PASS needs one real upcoming item on screen (a live timer counting down, or a reminder with its time) and, for the action half, one disposable item's Pause/Resume/Delete driven. Source: `.dsh-scratch/FIELD-TEST-2026-10-30/REPORT.md:445-472` (`pass2/pass2-money-time.xml`, `pass2/pass2-comingup-2.xml`, `pass2/pass2-comingup-3.xml`). **[PENDING: F5 ruling if PARTIAL is adopted as a state]** |
```

### Row 21 — `widgets` — SCREEN stays **SCREEN** with a dated `PARTIAL` note (never PASS for this install)

BEFORE (line 380, exact):

```
| 21 | Widgets you describe (`widgets`) | Talking | both | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:149 |
```

PROPOSED AFTER (Variant S; status cell unchanged):

```
| 21 | Widgets you describe (`widgets`) | Talking | both | **SCREEN** <br>was `FIELD-TESTED` | the feature was driven on 2026-10-30 morning on the debug build; the installed build is phone 0.2.3261, versionCode 1000003261, built from main `21add9d53`, installed 2026-10-30 12:01:36 | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:149 <br>**Measured 2026-10-30 — PARTIAL: driven once on the morning debug build, not on the current CI install.** **The feature was driven end-to-end on the morning debug build** (`.dsh-scratch/FIELD-TEST-FINAL-2026-10-30.md:24`): chat "make me a widget showing my next 3 reminders put them at the top" -> PC answered "Made a widget preview… Next Reminders"; `GET /api/widgets` showed the saved widget `w7dbe0ba0ae`; the phone's Widgets plate showed "Preview - not added yet"; Add saved it; the slot was set to *Jarvis widget 2*; "Put it on my home screen" answered "Jarvis widget 2 is already on your home screen."; the home card drew "Next Reminders / Coming up / Hidden - open Jarvis to see it." **After installing the CI release APK the debug build's app data was replaced and the slot reads "No widget chosen".** Measured 16:26 PDT and again 17:55 PDT: the launcher's Jarvis card is **bound and drawing** (content-desc `Jarvis widget 2`) but its text is exactly `No widget chosen` / `Tap, then choose one under Brain, Widgets`; `adb shell dumpsys appwidget` shows all Jarvis board widgets still bound to `com.android.launcher` (`widgets.size=8`, `zombie=false`); the saved widget `w7dbe0ba0ae` "Next Reminders" is still on the PC (`C:\Users\pcadmin\.openjarvis\widgets.json`, written 2026-10-30 06:26:15). **Not a pass for the current install:** the PASS evidence is the home card's own text changing from "No widget chosen" to the saved widget's content after the owner re-picks the slot (Brain -> Widgets, about four taps); this read-only pass did not make that persistent write. Source: `.dsh-scratch/FIELD-TEST-2026-10-30/REPORT.md:66-133,474-486` (`home-dump-20261030.xml`, `appwidget-dump-20261030.txt`). **[PENDING: F5 ruling if PARTIAL is adopted as a state]** |
```

### Row 39 — `history` — SCREEN stays **SCREEN** with a dated `PARTIAL` note (three records; archive still unproven)

BEFORE (line 398, exact):

```
| 39 | Your past chats (`history`) | Memory | both | **SCREEN** <br>was `FIELD-TESTED (first pass); PARTIAL (later top-up)` | phone 0.2.0 installed 2026-10-11 01:17 - **37 commits behind main** <br>desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/phone-pass-2026-10-11/README.md:40<br>/.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:172 <br>**Corrected 2026-10-13 - PARTIAL, never a pass:** **"The screen works and states its own setting; the conversation list is the owner's to unlock"** - Home -> `Earlier chats` opened `History`, and its `CONVERSATIONS` list reads `Hidden. Tap Show and confirm it is you.` (`docs/FIELD-TEST-2026-10-12-TOPUP-3.md:74`; the first top-up had it **BLOCKED**, `docs/FIELD-TEST-2026-10-12-TOPUP.md:50`). |
```

PROPOSED AFTER (Variant S; status cell unchanged):

```
| 39 | Your past chats (`history`) | Memory | both | **SCREEN** <br>was `FIELD-TESTED (first pass); PARTIAL (later top-up)` | phone 0.2.3261, versionCode 1000003261, built from main `21add9d53`, installed 2026-10-30 12:01:36; the live PC backend after #997's route repair | /.dsh-scratch/phone-pass-2026-10-11/README.md:40<br>/.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:172 <br>**Corrected 2026-10-13 - PARTIAL, never a pass:** **"The screen works and states its own setting; the conversation list is the owner's to unlock"** - Home -> `Earlier chats` opened `History`, and its `CONVERSATIONS` list reads `Hidden. Tap Show and confirm it is you.` (`docs/FIELD-TEST-2026-10-12-TOPUP-3.md:74`; the first top-up had it **BLOCKED**, `docs/FIELD-TEST-2026-10-12-TOPUP.md:50`). <br>**Updated 2026-10-30 — PARTIAL; three records disagree, and the disagreement is lock state, not a contradiction:** `docs/FIELD-TEST-2026-10-13-PHONE-PASS.md:80` **PASS** ("the screen and its list are reachable and readable with no gate … that sentence is gone"); `docs/FIELD-TEST-2026-10-12-TOPUP-3.md:74` **PARTIAL** ("the conversation list is the owner's to unlock"); this table **SCREEN** (kept the lower reading). **(a) Rendering, OWNER-VISUAL 16:22–16:23 PDT:** the installed app renders History with a real PC-backed list — "Chat history, kept on your PC", "On. New chats are kept on your PC, encrypted.", the filters, `Untagged (238)` expanded with named chats/times/`phone`/message counts — and the More sheet; the owner's screenshots were relayed in words, not viewed by the agent, and were **not driven**. **(b) The Show gate is real, by design, and is the owner's:** `HistoryScreen.kt:144-146`, `SecurityScreen.kt:330`, `MainActivity.kt:4576-4583` -> `ownerCheck` -> `BiometricGate.check:4551`; the PC refuses server-side while hidden (`jarvis_chat_log.py:4061-4065`, `:4124-4131`, `:4144-4151`). The morning record had the list hidden, the 16:22 screenshot shows it visible — both can be true in different lock states. **(c) The archive action has never been driven on this install:** the routes are live after #997 (`jarvis_hud.py:4735-4738`, `:4765`; `jarvis_chat_log.py:4138-4157`, audit event `:4156`), but the live audit log `C:\Users\pcadmin\.openjarvis\logs\jarvis-2026-10-30.jsonl` contains no `history.archive` and no `history.pin` event. **PARTIAL, never a pass:** PASS needs the Archive -> Archived filter -> Unarchive round trip observed (phone screen plus the audit line) in an unlocked session; the archive tap is reversible and cardless, but this read-only pass made no live writes. Source: `.dsh-scratch/FIELD-TEST-2026-10-30/REPORT.md:135-248,308-324`. **[PENDING: F5 ruling]** |
```

### Row 71 — `calendar` — NOT-TESTABLE → **DRIVEN**, with the limit named ([PENDING: F5 ruling])

BEFORE (line 430, exact):

```
| 71 | Read your own calendar (`calendar`) | Home | desktop | **NOT-TESTABLE** <br>was `FIELD-TESTED (first pass); NOT-TESTABLE (later top-up)` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:191 <br>**Corrected 2026-10-13 - NOT-TESTABLE, never a pass:** the page's own words - **"Not included: your calendar is not set up for Jarvis on this PC."** (`docs/FIELD-TEST-2026-10-12-TOPUP.md:117`). |
```

PROPOSED AFTER (option A, recommended — matches F5's own "driven-with-limit"):

```
| 71 | Read your own calendar (`calendar`) | Home | desktop | **DRIVEN** <br>with the limit named: phone only; was `NOT-TESTABLE` (later top-up), `FIELD-TESTED` (first pass) | phone 0.2.3261, versionCode 1000003261, built from main `21add9d53`, installed 2026-10-30 12:01:36, plus the live PC backend | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:191 <br>**Corrected 2026-10-13 - NOT-TESTABLE, never a pass:** the page's own words - **"Not included: your calendar is not set up for Jarvis on this PC."** (`docs/FIELD-TEST-2026-10-12-TOPUP.md:117`). <br>**Updated 2026-10-30 — the reason is overtaken, the feature was driven on the phone:** the phone Calendar rendered "October 2026", "Friday 30 October, today", "Nothing on this day."; after the New-event scroll fix one swipe brought up Save; a *"Field test"* 09:00 event was created and the PC's `GET /api/calendar` showed it (`id cf10c9605c7`); it was deleted from the phone (confirm -> "Yes, delete it") and the PC read `events=0` (`.dsh-scratch/FIELD-TEST-FINAL-2026-10-30.md:27`). **Limits, said plainly:** this row's `surface` is `desktop`, and the desktop's own calendar surface (the HUD Calendar card/sheet) was **not** driven, and no external-calendar account (Google/iCal) was touched — so this is a DRIVEN with a limit, not a desktop pass. Source: `.dsh-scratch/FIELD-TEST-2026-10-30/REPORT.md:282-290`, `.dsh-scratch/FIELD-TEST-FINAL-2026-10-30.md:27`. **[PENDING: F5 ruling]** |
```

**Option B (if the record owner does not want a limit form in the status):** keep `**NOT-TESTABLE**` and replace the evidence tail with: "**Updated 2026-10-30 — the reason is overtaken for the phone half:** the phone's local calendar was driven (create -> PC read `id cf10c9605c7` -> delete -> `events=0`, `.dsh-scratch/FIELD-TEST-FINAL-2026-10-30.md:27`); the desktop calendar page this row is about was still not driven." The limit sentence must not be dropped in either option.

### Row 130 — `galaxy picture` — NOT-TESTABLE → **BLOCKED** (owner's biometric Show)

BEFORE (line 489, exact):

```
| 130 | The phone's read-only Galaxy picture (`galaxy`, 2026-10-26) | Memory | phone | **NOT-TESTABLE** | built at PR #869; CI compiled it and ran the phone JVM unit tests on 2026-10-26 (`build` passed in 7m41s, `phone-unit-tests` in 4m13s) | no human has run it on a phone or an emulator: the look and a real tap are unverified. Its layout is pinned to the desktop JavaScript at 1e-6 by `GalaxyPictureTest.kt`, which is a test, not a field test. |
```

PROPOSED AFTER:

```
| 130 | The phone's read-only Galaxy picture (`galaxy`, 2026-10-26) | Memory | phone | **BLOCKED** <br>was `NOT-TESTABLE` | phone 0.2.3261, versionCode 1000003261, built from main `21add9d53`, installed 2026-10-30 12:01:36 | built at PR #869; CI compiled it and ran the phone JVM unit tests on 2026-10-26 (`build` passed in 7m41s, `phone-unit-tests` in 4m13s). Its layout is pinned to the desktop JavaScript at 1e-6 by `GalaxyPictureTest.kt`, which is a test, not a field test. **Updated 2026-10-30 — BLOCKED by the owner's biometric Show, not NOT-TESTABLE:** the concurrent phone pass tapped Home's "The Galaxy →" door (`HomeScreen.kt:2636-2642`) and the Brain opened on **PEOPLE AND THINGS** with its whole body replaced by exactly `Hidden. Tap Show and confirm it is you.` + a `Show` button — no picture, no dot names, no band and no names list. The picture is behind that guard by design (`EntitiesPlate.kt:100-108`: `if (privateHidden) { HiddenSection(...); return }`; the picture is drawn only after it at `:209-238`), so **no part of this row was driven**: no names, no links, no 48-name cap, no tap-to-facts. **The earlier "drivable now without the owner" reading is wrong** — it is drivable only while the hidden-memory gate is unlocked, and at 17:53 PDT it was locked (why it re-locked was not measured; screen lock/app restart are likely). The blocker is the owner's Show (fingerprint/PIN), by design — BLOCKED, never a pass. To finish, one owner action (Show + biometric) unlocks this row and the history archive row together. Source: `.dsh-scratch/FIELD-TEST-2026-10-30/REPORT.md:395,403-443` (`pass2/pass2-galaxy-open.xml`). |
```

---

## 4. Proposed diff B — the 27 rows measured in the SCREEN-row batch

Source section: `.dsh-scratch/FIELD-TEST-2026-10-30/REPORT.md:510-591`; each row's own evidence line is cited in its AFTER line. The batch's raw dumps are in `pass3\` (list at REPORT.md:584-591). **Method limits (REPORT.md:512-520, 578-582): read-only `adb`/`uiautomator`; nothing toggled; a settings-page read is not a setting operated; the memory-gated rows were deliberately not opened.** All 27 rows: build **phone 0.2.3261 / versionCode 1000003261 / main `21add9d53` / installed 2026-10-30 12:01:36**.

### 4.1 PASS → **DRIVEN** (8 rows)

These are read-only readout/list features: the readout *is* the feature, opened and observed with real PC data — the batch's own PASS definition (REPORT.md:526–531). No write was needed or made.

**Row 23 — `now` (What Jarvis is doing right now)** — BEFORE (line 382, exact):

```
| 23 | What Jarvis is doing right now (`now`) | Talking | both | **SCREEN** <br>was `TEST-VERIFIED ONLY` | never ran on a device | gen_own_network_cases.py |
```

PROPOSED AFTER:

```
| 23 | What Jarvis is doing right now (`now`) | Talking | both | **DRIVEN** <br>was `SCREEN`; `TEST-VERIFIED ONLY` before that | phone 0.2.3261, versionCode 1000003261, built from main `21add9d53`, installed 2026-10-30 12:01:36 | gen_own_network_cases.py <br>**Measured 2026-10-30 18:05–18:10 PDT — PASS as a read-only state readout:** Home -> Brain -> `What Jarvis is doing` -> DOING plate read `Link live · board read just now`, `Activity — Idle`, `Power — Active`, `Route — Not reported`, and `WHAT JARVIS IS DOING / Nothing yet. Steps appear here while Jarvis answers with its tools.` The readout is the feature; it was operated and observed, and no write is involved. Source: `.dsh-scratch/FIELD-TEST-2026-10-30/REPORT.md:536` (`pass3/p3-doing.xml`). |
```

**Row 51 — `folders` (Folders Jarvis may look in)** — BEFORE (line 410, exact):

```
| 51 | Folders Jarvis may look in (`folders`) | Notes and files | both | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:13 |
```

PROPOSED AFTER:

```
| 51 | Folders Jarvis may look in (`folders`) | Notes and files | both | **DRIVEN** <br>was `SCREEN`; `FIELD-TESTED` before that | phone 0.2.3261, versionCode 1000003261, built from main `21add9d53`, installed 2026-10-30 12:01:36 | /.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:13 <br>**Measured 2026-10-30 18:05–18:10 PDT — PASS:** Settings -> `Folders Jarvis may look in` read the real folder list `Documents — C:\Users\pcadmin\Documents — Remove`, `Folders are added on the PC: Settings, Folders Jarvis may look in.`, `PDF, Word, Excel and PowerPoint files can be read.` A read-only list, opened and read on the phone. Source: `.dsh-scratch/FIELD-TEST-2026-10-30/REPORT.md:539` (`pass3/p3-folders.xml`). |
```

**Row 79 — `devices` (Devices)** — BEFORE (line 438, exact):

```
| 79 | Devices (`devices`) | Phone | both | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:12 |
```

PROPOSED AFTER:

```
| 79 | Devices (`devices`) | Phone | both | **DRIVEN** <br>was `SCREEN`; `FIELD-TESTED` before that | phone 0.2.3261, versionCode 1000003261, built from main `21add9d53`, installed 2026-10-30 12:01:36 | /.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:12 <br>**Measured 2026-10-30 18:05–18:10 PDT — PASS:** Settings -> `Devices` read the real paired-device list `This PC — PC`, `OnePlus (this phone) — phone · paired 10 Oct · last active just now`, `Pixel 9 — phone · paired 17 Oct · last active just now`, `Signed approvals — Off…`, `Old shared key…`. A read-only list, opened and read on the phone. Source: `.dsh-scratch/FIELD-TEST-2026-10-30/REPORT.md:543` (`pass3/p3-devices.xml`). |
```

**Row 95 — `models` (Models)** — BEFORE (line 454, exact):

```
| 95 | Models (`models`) | The PC itself | both | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/chat-turn.log:19 |
```

PROPOSED AFTER:

```
| 95 | Models (`models`) | The PC itself | both | **DRIVEN** <br>was `SCREEN`; `FIELD-TESTED` before that | phone 0.2.3261, versionCode 1000003261, built from main `21add9d53`, installed 2026-10-30 12:01:36 | /.dsh-scratch/desktop-pass-2026-10-11/chat-turn.log:19 <br>**Measured 2026-10-30 18:05–18:10 PDT — PASS:** Home -> `Model →` opened the MODEL plate with the real installed models, each with `Use` (`gemma4:12b-it-qat`, `minicpm-v4.6:latest`, `medgemma1.5:4b-it-q4_K_M`, `hf.co/mradermacher/Huihui-Qwen3.5-9B-abliterated-GGUF:Q4_K_M`, `qwen3-coder-30b-a3b-ud-q3-k-xl:latest`, `qwen3-vl:8b-thinking`, `qwen3.5:0.8b`, …). The read-only list is the feature; `Use` was not tapped (switching a model is a write + approval card). Source: `.dsh-scratch/FIELD-TEST-2026-10-30/REPORT.md:551` (`pass3/p3-model.xml`). |
```

**Row 103 — `hardware` (Hardware and models)** — BEFORE (line 462, exact):

```
| 103 | Hardware and models (`hardware`) | The PC itself | both | **SCREEN** <br>was `FIELD-TESTED` | phone 0.2.0 installed 2026-10-11 01:17 - **37 commits behind main** <br>desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/phone-pass-2026-10-11/README.md:38<br>/.dsh-scratch/desktop-pass-2026-10-11/sweep-results.tsv:76 |
```

PROPOSED AFTER:

```
| 103 | Hardware and models (`hardware`) | The PC itself | both | **DRIVEN** <br>was `SCREEN`; `FIELD-TESTED` before that | phone 0.2.3261, versionCode 1000003261, built from main `21add9d53`, installed 2026-10-30 12:01:36 | /.dsh-scratch/phone-pass-2026-10-11/README.md:38<br>/.dsh-scratch/desktop-pass-2026-10-11/sweep-results.tsv:76 <br>**Measured 2026-10-30 18:05–18:10 PDT — PASS:** Home -> `Presets →` -> `HARDWARE` read `FOCUS PRESETS`, `General - Current`, `qwen3.5:9b on RTX 2060 (the long-context card), 196,608 tokens`, *"9.17 of its 12 GB; nothing else fits beside it. Writing is 44.9 tokens a second…"*, `The Fast preset uses the 2080 SUPER.` A read-only hardware readout; operated and read. Source: `.dsh-scratch/FIELD-TEST-2026-10-30/REPORT.md:553` (`pass3/p3-presets.xml`). |
```

**Row 104 — `second-card` (The second graphics card)** — BEFORE (line 463, exact):

```
| 104 | The second graphics card (`second-card`) | The PC itself | both | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/chat-turn.log:5 |
```

PROPOSED AFTER:

```
| 104 | The second graphics card (`second-card`) | The PC itself | both | **DRIVEN** <br>was `SCREEN`; `FIELD-TESTED` before that | phone 0.2.3261, versionCode 1000003261, built from main `21add9d53`, installed 2026-10-30 12:01:36 | /.dsh-scratch/desktop-pass-2026-10-11/chat-turn.log:5 <br>**Measured 2026-10-30 18:05–18:10 PDT — PASS:** the same `HARDWARE` plate names the **RTX 2060** as the long-context card with its model/token/GB/speed readout, and the **2080 SUPER** as the Fast preset's card — the second-card lane's readout was observed. No preset applied, no model switched. Source: `.dsh-scratch/FIELD-TEST-2026-10-30/REPORT.md:554` (`pass3/p3-presets.xml`). |
```

**Row 110 — `about` (About Jarvis)** — BEFORE (line 469, exact):

```
| 110 | About Jarvis (`about`) | The PC itself | both | **SCREEN** <br>was `NOT FOUND` | never ran on a device | no evidence either way: no pass record, no suite and no review names it |
```

PROPOSED AFTER:

```
| 110 | About Jarvis (`about`) | The PC itself | both | **DRIVEN** <br>was `SCREEN`; `NOT FOUND` before that | phone 0.2.3261, versionCode 1000003261, built from main `21add9d53`, installed 2026-10-30 12:01:36 | no evidence either way: no pass record, no suite and no review names it <br>**Measured 2026-10-30 18:05–18:10 PDT — PASS (read-only card):** Help -> scrolled to `About Jarvis` read `Version — 0.2.3261`, `Made by — darknight11ish`, `Licence — MIT, with third-party parts under their own licences`, `Signed by — 62ef7742e35e`, and the About paragraph. A read-only card; operated and read. Source: `.dsh-scratch/FIELD-TEST-2026-10-30/REPORT.md:555` (`pass3/p3-help.xml`). |
```

**Row 114 — `reach` (What Jarvis can reach)** — BEFORE (line 473, exact):

```
| 114 | What Jarvis can reach (`reach`) | The PC itself | both | **SCREEN** <br>was `FIELD-TESTED` | phone 0.2.0 installed 2026-10-11 01:17 - **37 commits behind main** <br>desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/phone-pass-2026-10-11/README.md:50<br>/.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:5 |
```

PROPOSED AFTER:

```
| 114 | What Jarvis can reach (`reach`) | The PC itself | both | **DRIVEN** <br>was `SCREEN`; `FIELD-TESTED` before that | phone 0.2.3261, versionCode 1000003261, built from main `21add9d53`, installed 2026-10-30 12:01:36 | /.dsh-scratch/phone-pass-2026-10-11/README.md:50<br>/.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:5 <br>**Measured 2026-10-30 18:05–18:10 PDT — PASS:** Settings -> `What Jarvis can reach` read the list: `Cloud model - On / Goes to: api.deepseek.com / Asks you first: Yes, every question`; `Web search - On / Goes to: this PC (SearXNG, which asks other search engines) / Asks you first: Only when private things could slip in…`; `Read one web page out loud - Off`; and the intro *"The PC writes this list from its own settings - the AI model does not write it…"*. A read-only list; operated and read. Source: `.dsh-scratch/FIELD-TEST-2026-10-30/REPORT.md:557` (`pass3/p3-reach.xml`). |
```

### 4.2 PARTIAL → keep **SCREEN** + dated `PARTIAL` note (16 rows; `[PENDING: F5 ruling]`)

Each was reached and read; the write an effect needs was named but not performed. The status cell is **unchanged** in Variant S; the dated note goes in the evidence column. Variant P turns each status cell into `**PARTIAL** <br>was ...` (see §2).

**Row 12 — `live` (Jarvis Live)** — BEFORE (line 371, exact):

```
| 12 | Jarvis Live (`live`) | Talking | both | **SCREEN** <br>was `TEST-VERIFIED ONLY` | never ran on a device | jarvis_live.py, jarvis_live_photo_test.py, test_browser_control_live.py, test_live.py |
```

PROPOSED AFTER:

```
| 12 | Jarvis Live (`live`) | Talking | both | **SCREEN** <br>was `TEST-VERIFIED ONLY` | phone 0.2.3261, versionCode 1000003261, built from main `21add9d53`, installed 2026-10-30 12:01:36 | jarvis_live.py, jarvis_live_photo_test.py, test_browser_control_live.py, test_live.py <br>**Measured 2026-10-30 18:05–18:10 PDT — PARTIAL: screen read, session not started (starting it opens the mic — a state change).** Home -> Live tab read `Jarvis Live`, `Talk back and forth - no "Hey Jarvis" needed`, `Jarvis is idle`, `Start Jarvis Live`, and the listening sentence (*"Jarvis listens after every answer until you end it, say "Okay Jarvis, that's all for now", or it has been quiet for 90 seconds. Every sentence is checked for your voice on your PC before any words are made of it."*). The behaviour is undriven. Source: `.dsh-scratch/FIELD-TEST-2026-10-30/REPORT.md:535`. **[PENDING: F5 ruling]** |
```

**Row 24 — `attention-budget` (How much Jarvis may interrupt you)** — BEFORE (line 383, exact):

```
| 24 | How much Jarvis may interrupt you (`attention-budget`) | Talking | both | **SCREEN** <br>was `TEST-VERIFIED ONLY` | never ran on a device | test_attention_budget.py |
```

PROPOSED AFTER:

```
| 24 | How much Jarvis may interrupt you (`attention-budget`) | Talking | both | **SCREEN** <br>was `TEST-VERIFIED ONLY` | phone 0.2.3261, versionCode 1000003261, built from main `21add9d53`, installed 2026-10-30 12:01:36 | test_attention_budget.py <br>**Measured 2026-10-30 18:05–18:10 PDT — PARTIAL: screen/control read, the write not performed.** Brain read `ATTENTION BUDGET`, `3 of 3 spoken interruptions left today`, `Speak up`, and *"Turning the count down applies at once. Turning it up asks you on the PC first, and nothing changes until you answer there."* Value read; changing it is a write (not done). Source: `.dsh-scratch/FIELD-TEST-2026-10-30/REPORT.md:537`. **[PENDING: F5 ruling]** |
```

**Row 25 — `focus` (Focus session)** — BEFORE (line 384, exact):

```
| 25 | Focus session (`focus`) | Talking | both | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/sweep-results.tsv:34 |
```

PROPOSED AFTER:

```
| 25 | Focus session (`focus`) | Talking | both | **SCREEN** <br>was `FIELD-TESTED` | phone 0.2.3261, versionCode 1000003261, built from main `21add9d53`, installed 2026-10-30 12:01:36 | /.dsh-scratch/desktop-pass-2026-10-11/sweep-results.tsv:34 <br>**Measured 2026-10-30 18:05–18:10 PDT — PARTIAL: the last-session report was read; starting a session is a state change (not done).** Brain -> `Your projects and goals` region read `Last session`, `Focus session stopped early.`, `On target: 0 of 1 minute (10 planned).`, `No drifts.`, `100% focused.` Source: `.dsh-scratch/FIELD-TEST-2026-10-30/REPORT.md:538`. **[PENDING: F5 ruling]** |
```

**Row 53 — `tutorials` (Tutorials and the FAQ)** — BEFORE (line 412, exact):

```
| 53 | Tutorials and the FAQ (`tutorials`) | Notes and files | both | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:40 |
```

PROPOSED AFTER:

```
| 53 | Tutorials and the FAQ (`tutorials`) | Notes and files | both | **SCREEN** <br>was `FIELD-TESTED` | phone 0.2.3261, versionCode 1000003261, built from main `21add9d53`, installed 2026-10-30 12:01:36 | /.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:40 <br>**Measured 2026-10-30 18:05–18:10 PDT — PARTIAL: the FAQ half was driven; the tutorials catalogue half was not reached on this screen.** Help tab read the FAQ index (`Do I need Tailscale for this to work?`, `Does this app run any AI on my phone?`, `How do I teach Jarvis my voice? …`, `Why can't I approve everything waiting for me in one tap?`, …), then opened `How do I update Jarvis?` and read its full answer (*"Most of it in one command… scripts/update-jarvis.ps1… This app: install the newest file from the release page over the old one; it stays paired."*). Source: `.dsh-scratch/FIELD-TEST-2026-10-30/REPORT.md:540` (`pass3/p3-help.xml`, `p3-faq-answer.xml`). **[PENDING: F5 ruling]** |
```

**Row 56 — `browser-engine` (A browser without a window)** — BEFORE (line 415, exact):

```
| 56 | A browser without a window (`browser-engine`) | Notes and files | both | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:187 |
```

PROPOSED AFTER:

```
| 56 | A browser without a window (`browser-engine`) | Notes and files | both | **SCREEN** <br>was `FIELD-TESTED` | phone 0.2.3261, versionCode 1000003261, built from main `21add9d53`, installed 2026-10-30 12:01:36 | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:187 <br>**Measured 2026-10-30 18:05–18:10 PDT — PARTIAL: state read; the behaviour needs Obscura installed on the PC (a PC-side install, not done).** Settings -> `Browser without a window (Obscura)` read `Off. Jarvis uses the visible browser only.`, `Obscura is not installed on this PC yet.`, plus the full explanation. Source: `.dsh-scratch/FIELD-TEST-2026-10-30/REPORT.md:541` (`pass3/p3-browser.xml`). **[PENDING: F5 ruling]** |
```

**Row 80 — `phone-notifications` (Let Jarvis read phone notifications)** — BEFORE (line 439, exact):

```
| 80 | Let Jarvis read phone notifications (`phone-notifications`) | Phone | phone | **SCREEN** <br>was `TEST-VERIFIED ONLY` | never ran on a device | jarvis_phone_notifications.py, test_phone_notifications.py |
```

PROPOSED AFTER:

```
| 80 | Let Jarvis read phone notifications (`phone-notifications`) | Phone | phone | **SCREEN** <br>was `TEST-VERIFIED ONLY` | phone 0.2.3261, versionCode 1000003261, built from main `21add9d53`, installed 2026-10-30 12:01:36 | jarvis_phone_notifications.py, test_phone_notifications.py <br>**Measured 2026-10-30 18:05–18:10 PDT — PARTIAL: state read, granting notification access is an OS write (not done).** Settings -> `Phone notifications` read `Jarvis never sees a phone notification.`, `Notification access: not granted yet.`, `No apps added yet.`, `No captured notifications are kept on this phone.` Source: `.dsh-scratch/FIELD-TEST-2026-10-30/REPORT.md:544` (`pass3/p3-phone-notifications.xml`). **[PENDING: F5 ruling]** |
```

**Row 81 — `phone-watch` (Smartwatch notifications)** — BEFORE (line 440, exact):

```
| 81 | Smartwatch notifications (`phone-watch`) | Phone | phone | **SCREEN** <br>was `NOT FOUND` | never ran on a device | no evidence either way: no pass record, no suite and no review names it |
```

PROPOSED AFTER:

```
| 81 | Smartwatch notifications (`phone-watch`) | Phone | phone | **SCREEN** <br>was `NOT FOUND` | phone 0.2.3261, versionCode 1000003261, built from main `21add9d53`, installed 2026-10-30 12:01:36 | no evidence either way: no pass record, no suite and no review names it <br>**Measured 2026-10-30 18:05–18:10 PDT — PARTIAL: row label read only; no paired watch exists, so the behaviour is not observable.** Settings -> `Smartwatch notifications` section read `NOTIFICATIONS`, `Show notifications on a compatible watch`. Source: `.dsh-scratch/FIELD-TEST-2026-10-30/REPORT.md:545` (`pass3/p3-watch.xml`). **[PENDING: F5 ruling]** |
```

**Row 82 — `phone-floating` (Floating Jarvis)** — BEFORE (line 441, exact):

```
| 82 | Floating Jarvis (`phone-floating`) | Phone | phone | **SCREEN** <br>was `NEVER TESTED` | never ran on a device | only a review mentions it: /.dsh-scratch/device-tour/.evidence/transcript-D.txt:22 |
```

PROPOSED AFTER:

```
| 82 | Floating Jarvis (`phone-floating`) | Phone | phone | **SCREEN** <br>was `NEVER TESTED` | phone 0.2.3261, versionCode 1000003261, built from main `21add9d53`, installed 2026-10-30 12:01:36 | only a review mentions it: /.dsh-scratch/device-tour/.evidence/transcript-D.txt:22 <br>**Measured 2026-10-30 18:05–18:10 PDT — PARTIAL: choices/state read; switching is a write (not done).** Settings -> `Floating Jarvis` read `Off / Bubble / Overlay`, `Off. Nothing floats over other apps.` Source: `.dsh-scratch/FIELD-TEST-2026-10-30/REPORT.md:546` (`pass3/p3-floating.xml`). **[PENDING: F5 ruling]** |
```

**Row 88 — `appearance` (Appearance)** — BEFORE (line 447, exact):

```
| 88 | Appearance (`appearance`) | The PC itself | both | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/sweep-results.tsv:4 |
```

PROPOSED AFTER:

```
| 88 | Appearance (`appearance`) | The PC itself | both | **SCREEN** <br>was `FIELD-TESTED` | phone 0.2.3261, versionCode 1000003261, built from main `21add9d53`, installed 2026-10-30 12:01:36 | /.dsh-scratch/desktop-pass-2026-10-11/sweep-results.tsv:4 <br>**Measured 2026-10-30 18:05–18:10 PDT — PARTIAL: options read, nothing changed (a write).** Appearance tab read `Follow the system`, `THEME` (`Reactor`, `Daylight`, `High Contrast` + descriptions), `HOME` (`Face size on Home: Full screen / Extra large / Large / Medium / Hidden` + explanation), `Tabs row`. Source: `.dsh-scratch/FIELD-TEST-2026-10-30/REPORT.md:547` (`pass3/p3-appearance*.xml`). **[PENDING: F5 ruling]** |
```

**Row 90 — `faces` (Choose Jarvis's face)** — BEFORE (line 449, exact):

```
| 90 | Choose Jarvis's face (`faces`) | The PC itself | both | **SCREEN** <br>was `NEVER TESTED` | never ran on a device | only a review mentions it: /.dsh-scratch/device-tour/README.md:63 |
```

PROPOSED AFTER:

```
| 90 | Choose Jarvis's face (`faces`) | The PC itself | both | **SCREEN** <br>was `NEVER TESTED` | phone 0.2.3261, versionCode 1000003261, built from main `21add9d53`, installed 2026-10-30 12:01:36 | only a review mentions it: /.dsh-scratch/device-tour/README.md:63 <br>**Measured 2026-10-30 18:05–18:10 PDT — PARTIAL: labels read; the face picture is the documented drawn-not-text dead end (no vision), and no face was changed.** Appearance -> `FACE`: the face is drawn (`content-desc="Jarvis is idle"`), and the readable labels were captured: `Cycle states`, `Face editor — Pattern, colour, quality, frame rate and speed.`, patterns `Arc / Orbit / Comb / Spiral / Iris / Fullerene`, and the face list `Tokamak / Membrane / Red Panda / Pygmy Owl / Sea Otter / Monkey / Robot` with *"All 25 of the desktop's faces render here now"*. Source: `.dsh-scratch/FIELD-TEST-2026-10-30/REPORT.md:548` (`pass3/p3-appearance*.xml`). **[PENDING: F5 ruling]** |
```

**Row 91 — `animal-options` (Animal options)** — BEFORE (line 450, exact):

```
| 91 | Animal options (`animal-options`) | The PC itself | both | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:195 |
```

PROPOSED AFTER:

```
| 91 | Animal options (`animal-options`) | The PC itself | both | **SCREEN** <br>was `FIELD-TESTED` | phone 0.2.3261, versionCode 1000003261, built from main `21add9d53`, installed 2026-10-30 12:01:36 | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:195 <br>**Measured 2026-10-30 18:05–18:10 PDT — PARTIAL: full options plate read; none changed (writes).** Appearance -> `ANIMAL OPTIONS` read `Keep the animal still`, `Cute idle moments`, `Seasonal touches`, `SUN, MOON AND WEATHER / Show the sun and moon behind the face`, `Your town — No town yet, so there is no sun or moon to show…`. Source: `.dsh-scratch/FIELD-TEST-2026-10-30/REPORT.md:549` (`pass3/p3-appearance*.xml`). **[PENDING: F5 ruling]** |
```

**Row 93 — `menu-visibility` (Show or hide menus)** — BEFORE (line 452, exact):

```
| 93 | Show or hide menus (`menu-visibility`) | The PC itself | both | **SCREEN** <br>was `TEST-VERIFIED ONLY` | never ran on a device | test_menu_visibility.py |
```

PROPOSED AFTER:

```
| 93 | Show or hide menus (`menu-visibility`) | The PC itself | both | **SCREEN** <br>was `TEST-VERIFIED ONLY` | phone 0.2.3261, versionCode 1000003261, built from main `21add9d53`, installed 2026-10-30 12:01:36 | test_menu_visibility.py <br>**Measured 2026-10-30 18:05–18:10 PDT — PARTIAL: list read; hiding settings are writes.** Settings -> `Show or hide menus` read `This hides menus on this device only.`, `Nothing is hidden.`, `Show everything`, and the per-group rows with what each hides (e.g. `Study — Hides Quiz me on a text, Quiz from a YouTube link, My study decks`). Source: `.dsh-scratch/FIELD-TEST-2026-10-30/REPORT.md:550` (`pass3/p3-menus.xml`). **[PENDING: F5 ruling]** |
```

**Row 99 — `notifications` (Notifications)** — BEFORE (line 458, exact):

```
| 99 | Notifications (`notifications`) | The PC itself | desktop | **SCREEN** <br>was `TEST-VERIFIED ONLY` | never ran on a device | jarvis_phone_notifications.py, test_phone_notifications.py |
```

PROPOSED AFTER:

```
| 99 | Notifications (`notifications`) | The PC itself | desktop | **SCREEN** <br>was `TEST-VERIFIED ONLY` | phone 0.2.3261, versionCode 1000003261, built from main `21add9d53`, installed 2026-10-30 12:01:36 | jarvis_phone_notifications.py, test_phone_notifications.py <br>**Measured 2026-10-30 18:05–18:10 PDT — PARTIAL: state read; creating/adding a style is a write.** Settings -> `Notifications from Jarvis` read `NOTIFICATIONS FROM JARVIS / Open Android's notification settings`, `NOTIFICATION STYLES`, `Live now: approval cards - Deep Blue Spark Pulse, reminders - Deep Blue Spark Pulse.`, `Hidden - open Jarvis to see it.`, and the style prompt. Source: `.dsh-scratch/FIELD-TEST-2026-10-30/REPORT.md:552` (`pass3/p3-notifications.xml`). **[PENDING: F5 ruling]** |
```

**Row 112 — `backup` (Backups)** — BEFORE (line 471, exact):

```
| 112 | Backups (`backup`) | The PC itself | both | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:59 |
```

PROPOSED AFTER:

```
| 112 | Backups (`backup`) | The PC itself | both | **SCREEN** <br>was `FIELD-TESTED` | phone 0.2.3261, versionCode 1000003261, built from main `21add9d53`, installed 2026-10-30 12:01:36 | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:59 <br>**Measured 2026-10-30 18:05–18:10 PDT — PARTIAL: status/integrity read; making a new backup is a write (not done).** Settings -> `Backups` read `Last backup: 20 days ago.`, `In: Jarvis Backups`, `Kept: 4 of the last 5.`, *"Jarvis checked this file just now: it is a complete, well-formed backup, and nothing about it has changed since it was written."*, plus the note that proving a backup opens needs the recovery code on the PC. Source: `.dsh-scratch/FIELD-TEST-2026-10-30/REPORT.md:556` (`pass3/p3-backups.xml`). **[PENDING: F5 ruling]** |
```

**Row 119 — `what-asks-first` (What asks first)** — BEFORE (line 478, exact):

```
| 119 | What asks first (`what-asks-first`) | Safety | both | **SCREEN** <br>was `NEVER TESTED` | never ran on a device | only a review mentions it: /.dsh-scratch/device-tour/README.md:78 |
```

PROPOSED AFTER:

```
| 119 | What asks first (`what-asks-first`) | Safety | both | **SCREEN** <br>was `NEVER TESTED` | phone 0.2.3261, versionCode 1000003261, built from main `21add9d53`, installed 2026-10-30 12:01:36 | only a review mentions it: /.dsh-scratch/device-tour/README.md:78 <br>**Measured 2026-10-30 18:05–18:10 PDT — PARTIAL: list read; toggling a row is a write.** Settings -> `What asks first` read `WHAT ASKS FIRST`, `Lockdown is off: everything asks first as your settings say.`, `Turn on Lockdown`, `Reading your own things`, `Read your calendar - Does it without asking` + `Ask me first`, `Read your email - Does it without asking` + `Ask me first`, and the explanation *"The PC writes this list from its own settings - the AI model does not write it… Letting one go ahead without asking … takes an approval card and Windows Hello."* Source: `.dsh-scratch/FIELD-TEST-2026-10-30/REPORT.md:559` (`pass3/p3-asks-first.xml`). **[PENDING: F5 ruling]** |
```

**Row 121 — `captcha-handoff` (Hand a captcha to your phone)** — BEFORE (line 480, exact):

```
| 121 | Hand a captcha to your phone ("Solve it here") (`captcha-handoff`) | Safety | both | **SCREEN** <br>was `NEVER TESTED` | never ran on a device | only a review mentions it: /.dsh-scratch/device-tour/.evidence/transcript-G.txt:483 |
```

PROPOSED AFTER:

```
| 121 | Hand a captcha to your phone ("Solve it here") (`captcha-handoff`) | Safety | both | **SCREEN** <br>was `NEVER TESTED` | phone 0.2.3261, versionCode 1000003261, built from main `21add9d53`, installed 2026-10-30 12:01:36 | only a review mentions it: /.dsh-scratch/device-tour/.evidence/transcript-G.txt:483 <br>**Measured 2026-10-30 18:05–18:10 PDT — PARTIAL: both choices read; choosing is a write/approval.** Settings -> `When a captcha stops Jarvis` read `Leave it where it is (in use)` + *"The window is not touched: it keeps its size, its place and whatever is in front of it…"*; `Bring it to the front` + *"That one window is raised and activated the moment Jarvis is stuck… turning this on asks for your approval."* Source: `.dsh-scratch/FIELD-TEST-2026-10-30/REPORT.md:561` (`pass3/p3-captcha.xml`). **[PENDING: F5 ruling]** |
```

### 4.3 PARTIAL but the row stays **BLOCKED** — 2 rows (the report says so)

**Row 118 — `approvals` (Approval cards)** — the batch read the card-display setting, but the report's own row says *"**the matrix row stays BLOCKED** — actually raising and answering a card is the owner's"* (REPORT.md:558). So the status stays BLOCKED and the read is recorded as evidence only.

BEFORE (line 477, exact):

```
| 118 | Approval cards (`approvals`) | Safety | both | **BLOCKED** <br>was `FIELD-TESTED (first pass); BLOCKED (later top-up)` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:28 <br>**Corrected 2026-10-13 - BLOCKED, never a pass:** **"an approval card needs a person to decide it; raising one and answering it are both the owner's"** (`docs/FIELD-TEST-2026-10-12-TOPUP.md:129`). |
```

PROPOSED AFTER:

```
| 118 | Approval cards (`approvals`) | Safety | both | **BLOCKED** <br>was `FIELD-TESTED (first pass); BLOCKED (later top-up)` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md:28 <br>**Corrected 2026-10-13 - BLOCKED, never a pass:** **"an approval card needs a person to decide it; raising one and answering it are both the owner's"** (`docs/FIELD-TEST-2026-10-12-TOPUP.md:129`). <br>**Measured 2026-10-30 18:05–18:10 PDT — PARTIAL evidence, status unchanged (BLOCKED):** Settings -> `Approval cards` read `APPROVAL CARDS`, *"This only changes how much of a card is shown at first - the same card, the same words underneath, the same buttons."*, `Start short (default) (in use)`, `Always show everything`. Only the card-display half was read; raising and answering a card is still the owner's, so this row does not move. Source: `.dsh-scratch/FIELD-TEST-2026-10-30/REPORT.md:558` (`pass3/p3-approvalcards.xml`). **[PENDING: F5 ruling on whether the independent display-setting half deserves its own row]** |
```

**Row 120 — `app-lock` (Lock Jarvis, and hide what it remembers)** — the batch read the Security summary; the report's own row says *"**the matrix row stays BLOCKED** — enabling the lock needs the owner's lock/fingerprint"* (REPORT.md:560). Status stays BLOCKED.

BEFORE (line 479, exact):

```
| 120 | Lock Jarvis, and hide what it remembers (`app-lock`) | Safety | both | **BLOCKED** <br>was `FIELD-TESTED (first pass); BLOCKED (later top-up)` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:21 <br>**Corrected 2026-10-13 - BLOCKED, never a pass:** **"turning it off or on is the owner's own Windows Hello / phone lock; a harness cannot answer a fingerprint prompt"** (`docs/FIELD-TEST-2026-10-12-TOPUP.md:127`). |
```

PROPOSED AFTER:

```
| 120 | Lock Jarvis, and hide what it remembers (`app-lock`) | Safety | both | **BLOCKED** <br>was `FIELD-TESTED (first pass); BLOCKED (later top-up)` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:21 <br>**Corrected 2026-10-13 - BLOCKED, never a pass:** **"turning it off or on is the owner's own Windows Hello / phone lock; a harness cannot answer a fingerprint prompt"** (`docs/FIELD-TEST-2026-10-12-TOPUP.md:127`). <br>**Measured 2026-10-30 18:05–18:10 PDT — PARTIAL evidence, status unchanged (BLOCKED):** Settings -> `Security` read `SECURITY`, `App lock off, risky approvals ask, memory lists hidden.`, `Lock and fingerprint settings`, and the `APP CONTROL` section. Enabling the lock still needs the owner's lock/fingerprint, so this row does not move. Source: `.dsh-scratch/FIELD-TEST-2026-10-30/REPORT.md:560` (`pass3/p3-security.xml`). **[PENDING: F5 ruling]** |
```

### 4.4 NOT-REACHABLE → **NOT-TESTABLE** — 1 row

**Row 58 — `chatbot` (Talk to a chatbot for me)** — the current matrix state is **SCREEN** (checked: line 417), so this is a state *change* to NOT-TESTABLE, not "stays".

BEFORE (line 417, exact):

```
| 58 | Talk to a chatbot for me (`chatbot`) | Notes and files | both | **SCREEN** <br>was `FIELD-TESTED` | desktop 0.2.129.0, 2026-10-10 - **older still** | /.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:10 |
```

PROPOSED AFTER:

```
| 58 | Talk to a chatbot for me (`chatbot`) | Notes and files | both | **NOT-TESTABLE** <br>was `SCREEN`; `FIELD-TESTED` before that | phone 0.2.3261, versionCode 1000003261, built from main `21add9d53`, installed 2026-10-30 12:01:36 | /.dsh-scratch/desktop-pass-2026-10-11/gap-table.md:10 <br>**Measured 2026-10-30 18:05–18:10 PDT — NOT-REACHABLE: needs the owner's accounts.** Brain -> `TALK TO A CHATBOT FOR ME` read its explanation (*"Jarvis asks an AI chatbot about something for you, and writes its own follow-up questions on this PC, within limits you set. One approval card covers the whole conversation…"*) and the per-site state: `Gemini — Jarvis's Gemini window has never been signed in…`, `ChatGPT — …never been signed in…`, `Claude` listed. **Nothing can be operated without a sign-in on the PC**, which only the owner can do — the matrix's NOT-TESTABLE ("needs something absent"), never a pass. Source: `.dsh-scratch/FIELD-TEST-2026-10-30/REPORT.md:542`. **[PENDING: F5 ruling — leaving SCREEN would overstate it]** |
```

### 4.5 NOT CLAIMED — 3 rows, no change

- **83 `phone-tiles`** — no on-screen row was found on the Settings/Appearance surfaces visited (REPORT.md:569–571); the batch claims **nothing either way**. Matrix row untouched.
- **94 `shortcuts`** — the phone's own feature directory says it is a PC-only setting on the phone (`FeatureDirectory.kt:137`, "Honest Refusal on Phone"); not driven on the phone (REPORT.md:572–573). Matrix row untouched.
- **92 `first-run`** — the row was not found on the Home/Settings/Help surfaces visited in this pass (REPORT.md:574). Matrix row untouched.

---

## 5. The rule check — "BLOCKED and PARTIAL are never passes"

| group | proposed status | is it a pass? | why not / why |
|---|---|---|---|
| 8 batch PASS rows → DRIVEN | DRIVEN | **not a PASS word** in this matrix; it is the matrix's top state | these are read-only readout features: the readout *is* the feature, and it was operated and observed with real PC data. **Caveat:** DRIVEN here means "read-only readout operated"; it does **not** mean a control was exercised (no model switched, no folder added, no backup made) |
| 16 batch PARTIAL rows → SCREEN + dated note | SCREEN | **no** | screen/control opened and read; the write an effect needs was named and **not** performed |
| 118 / 120 | BLOCKED (unchanged) | **no** | the owner's card decision / lock remains the blocker; only the display half was read |
| 58 | NOT-TESTABLE | **no** | needs the owner's chatbot sign-ins |
| 12/24/25/… in Variant P | PARTIAL | **no** | "some hardware evidence exists, the effect was not operated" |
| 19 (diff A) | SCREEN + dated PARTIAL note | **no** | plate found and read; nothing coming up existed, no action driven |
| 21 (diff A) | SCREEN + dated PARTIAL note | **no** | driven once on a different (morning debug) build; current CI install shows the empty-slot state |
| 39 (diff A) | SCREEN + dated PARTIAL note | **no** | rendering is owner-visual only; Show gate by design; Archive/Unarchive never driven on this install |
| 71 (diff A) | **DRIVEN, phone only** | a drive with a named limit | operated + effect observed (phone create/read/delete, PC saw it) — the limit sentence (desktop side not driven) is part of the status and must not be dropped |
| 130 (diff A) | BLOCKED | **no** | could not be reached — biometric gate was up; nothing operated |

No row is promoted to **PASS** by this draft, and no PARTIAL or BLOCKED row is counted as a pass anywhere in it.

---

## 6. Inventory after these moves — the arithmetic, with both variants

Baseline (verified today): **10 DRIVEN + 93 SCREEN + 19 BLOCKED + 14 NOT-TESTABLE = 136**. The matrix's own 2026-10-15 counts (**129 rows = 5 DRIVEN / 93 SCREEN / 19 BLOCKED / 12 NOT-TESTABLE**) are left visible/unmodified.

**Move set A** (the five rows, §3, Variant S):
- 19 `coming-up`: BLOCKED → **SCREEN** (+1 SCREEN, −1 BLOCKED)
- 21 `widgets`: SCREEN → SCREEN (evidence only)
- 39 `history`: SCREEN → SCREEN (evidence only)
- 71 `calendar`: NOT-TESTABLE → **DRIVEN** (+1 DRIVEN, −1 NOT-TESTABLE)
- 130 `galaxy`: NOT-TESTABLE → **BLOCKED** (+1 BLOCKED, −1 NOT-TESTABLE)
- A net: DRIVEN +1, SCREEN +1, BLOCKED 0, NOT-TESTABLE −2 → **11 / 94 / 19 / 12 = 136**

**Move set B** (the 27 batch rows, §4, Variant S):
- 8 PASS rows: SCREEN → **DRIVEN** (+8 DRIVEN, −8 SCREEN)
- 16 PARTIAL rows: SCREEN → SCREEN (evidence only)
- 118, 120: BLOCKED → BLOCKED (evidence only)
- 58 `chatbot`: SCREEN → **NOT-TESTABLE** (−1 SCREEN, +1 NOT-TESTABLE)
- 3 unclaimed: no change
- B net: DRIVEN +8, SCREEN −9, BLOCKED 0, NOT-TESTABLE +1 → **18 / 84 / 19 / 15 = 136**

**A + B, Variant S (recommended — no invented state):**

| state | before | change | after |
|---|---|---|---|
| DRIVEN | 10 | +1 (71) +8 (PASS) = **+9** | **19** |
| SCREEN | 93 | +1 (19) −8 (PASS) −1 (58) = **−8** | **85** |
| BLOCKED | 19 | −1 (19) +1 (130) = **0** | **19** |
| NOT-TESTABLE | 14 | −1 (71) −1 (130) +1 (58) = **−1** | **13** |
| **total** | **136** | 0 | **136** (19 + 85 + 19 + 13) |

**A + B, Variant P (if PARTIAL is adopted as a sixth state):** the 19 rows carrying a dated `PARTIAL` note (19, 21, 39, 12, 24, 25, 53, 56, 80, 81, 82, 88, 90, 91, 93, 99, 112, 119, 121) move SCREEN → PARTIAL: **DRIVEN 19 + SCREEN 66 + BLOCKED 19 + NOT-TESTABLE 13 + PARTIAL 19 = 136**. (118/120 stay BLOCKED in both variants, per the report.)

---

## 7. Flags — where the evidence does NOT support the proposed state, or the Lead's summary needs a correction

1. **Rows 118 `approvals` and 120 `app-lock` — do NOT downgrade to SCREEN.** The Lead's summary lists both under the 18 PARTIAL rows, but the field-test report's own row text says, verbatim: *"**the matrix row stays BLOCKED** — actually raising and answering a card is the owner's"* (REPORT.md:558) and *"**the matrix row stays BLOCKED** — enabling the lock needs the owner's lock/fingerprint"* (REPORT.md:560). Proposed: **status unchanged (BLOCKED)**, measured screen-read evidence appended. Downgrading to SCREEN would say the row was found/read and the behaviour never exercised — true only of the *display* half, while the row's blocker is untouched. `[PENDING: F5 ruling]` on whether the display half deserves a separate row/note.
2. **Row 58 `chatbot` — this is a state CHANGE, not "stays".** The Lead's wording says it "stays NOT-TESTABLE"; the matrix currently says **SCREEN** (line 417). Proposed: SCREEN → NOT-TESTABLE (owner's accounts absent). Flagging the discrepancy so the record owner does not think the row was already NOT-TESTABLE.
3. **Row 110 `about` — the weakest DRIVEN candidate.** It is a static card; its DRIVEN rests on the batch's own PASS definition ("read-only readout operated and observed"). If the record owner requires an effect beyond rendering for DRIVEN, row 110 is **SCREEN**; the other 7 PASS rows (23, 51, 79, 95, 103, 104, 114) read live PC data, and are stronger.
4. **Row 81 `phone-watch` — a near-NOT-TESTABLE reason inside a SCREEN mapping.** The measured note is "no paired watch exists, so the behaviour is not observable — row label read only". The batch calls it PARTIAL and SCREEN is the smallest consistent state (the screen was found and read), but the *reason* it cannot be exercised is absent hardware, which is the NOT-TESTABLE definition. Flagged; SCREEN is proposed per the batch's own verdict.
5. **Row 56 `browser-engine`** has the same shape — the behaviour needs Obscura installed on the PC; the screen/state was read, so SCREEN is proposed, not NOT-TESTABLE.
6. **Row 19 (diff A)** — evidence supports "the old declared=19/composed=11 blocker no longer reproduces", **not** "defect formally fixed": the batch drew the plate but did not re-count composed vs declared rows (the report's own Limits say so). Keep the hedge.
7. **Rows 83, 94, 92 — untouched on purpose.** Nothing was claimed: 83 no on-screen row found; 94 PC-only on the phone by design (`FeatureDirectory.kt:137`); 92 not found on the visited surfaces. No diff proposed; nobody should infer a verdict either way.
8. **DRIVEN ≠ a control was exercised anywhere in this batch.** Every PASS row is a read-only readout/list; no setting, model, style, backup, folder or notification permission was changed, and no Live session was started. The draft never says otherwise.

---

## 8. Rulings this draft needs

| # | item | ruling needed | marker |
|---|---|---|---|
| 1 | `PARTIAL` as a matrix state (19 rows carry a dated PARTIAL note) | gaps review **F5** covers rows 39/71/130 but does **not** settle the state vocabulary. Variant S (SCREEN + dated note) is the no-new-state default; Variant P (PARTIAL) is the alternative | **[PENDING: record-owner ruling; F5 does not cover it]** |
| 2 | Row 39 record form (SCREEN + dated PARTIAL note; lock-state dependency; archive unproven) | F5 explicitly asks to confirm | **[PENDING: F5 ruling]** |
| 3 | Row 71 promotion to DRIVEN-with-limit | F5 explicitly asks to confirm or keep | **[PENDING: F5 ruling]** |
| 4 | Row 130 eventual agent-driven PASS standard (only relevant once unlocked) | F5's third clause | **[PENDING: F5 ruling]** |
| 5 | Row 71 `surface` = `desktop` vs the drive being phone-only | record owner; not proposed as an edit here | **[PENDING: record-owner ruling]** |
| 6 | Rows 118/120: display half read but row stays BLOCKED | record owner (see §7.1) | **[PENDING: F5 ruling]** |

---

## 9. Companion edit needed for internal consistency (proposed text)

Applying the row lines alone would leave the document contradicting itself (the 2026-10-15 counts still say 129 rows/5 DRIVEN; the "What cannot be tested" bullet still lists `calendar` as NOT-TESTABLE; the "The 128 features" heading and method line remain as written — those are historical and are left). The matrix's convention is that later records outrank and are written as a dated block with `was ...` kept, so **propose ONE new dated blockquote inserted after the 2026-10-15 correction block and before `## The counts`** (anchor: line 104 is the closing `>` of that block, line 106 is `## The counts`):

```
>
> ## UPDATED 2026-10-30: thirty-two rows moved by the day's field test — none to a pass
>
> The rows below this note still read as the 2026-10-15 correction measured
> them, and that table is left exactly as measured. Today's field test
> (`2026-10-30`: phone 0.2.3261 / versionCode 1000003261 from main `21add9d53`,
> installed 12:01:36; desktop 0.2.368) produced evidence for **32** of the 136
> rows, and each row shows its move with `was ...`:
>
> * **8 rows moved to DRIVEN** (`now` 23, `folders` 51, `devices` 79,
>   `models` 95, `hardware` 103, `second-card` 104, `about` 110, `reach` 114) —
>   read-only readout/list features, opened and observed on the phone with real
>   PC data. **DRIVEN here means "the readout was operated"; no control was
>   changed and no write was made.**
> * **18 rows carry a dated PARTIAL note** (`live` 12, `attention-budget` 24,
>   `focus` 25, `tutorials` 53, `browser-engine` 56, `phone-notifications` 80,
>   `phone-watch` 81, `phone-floating` 82, `appearance` 88, `faces` 90,
>   `animal-options` 91, `menu-visibility` 93, `notifications` 99, `backup`
>   112, `approvals` 118, `what-asks-first` 119, `app-lock` 120,
>   `captcha-handoff` 121): the screen/control was opened and read, but the
>   write an effect would need was named and not performed. Their status cells
>   keep the matrix's states (SCREEN, or BLOCKED for 118/120, whose blocker is
>   the owner's decision/lock) — **PARTIAL is never a pass.**
> * **1 row moved to NOT-TESTABLE** (`chatbot` 58: needs the owner's sign-ins).
> * **5 rows from the earlier passes moved** (`coming-up` 19 BLOCKED→SCREEN
>   with a dated PARTIAL note, `widgets` 21 and `history` 39 SCREEN with dated
>   PARTIAL notes, `calendar` 71 NOT-TESTABLE→DRIVEN **phone only** with that
>   limit named, `galaxy` 130 NOT-TESTABLE→BLOCKED by the owner's biometric
>   Show). The "What cannot be tested from a checkout" list above is the
>   2026-10-15 reading; row 71 supersedes it for the phone half only.
> * **3 rows deliberately untouched** (`phone-tiles` 83: no on-screen row
>   found; `shortcuts` 94: PC-only on the phone by design,
>   `FeatureDirectory.kt:137`; `first-run` 92: not found on the visited
>   surfaces). No verdict is claimed for them.
>
> **BLOCKED and PARTIAL are never passes**, and no row in this note is a pass.
> Counted over all 136 rows (rows 129-136 were added after the 2026-10-15
> note), the inventory was **10 DRIVEN / 93 SCREEN / 19 BLOCKED /
> 14 NOT-TESTABLE** before these moves and is **19 DRIVEN / 85 SCREEN /
> 19 BLOCKED / 13 NOT-TESTABLE** after them. (If the record owner adopts
> PARTIAL as a sixth state, the 19 rows carrying a dated PARTIAL note become
> PARTIAL instead of SCREEN: **19 / 66 / 19 / 13 / 19 PARTIAL**.)
>
> Dated evidence: `.dsh-scratch/FIELD-TEST-2026-10-30/REPORT.md` (first pass
> 16:25-16:35, concurrent pass 17:52-17:56, SCREEN-row batch 18:05-18:10 PDT;
> 115 raw dumps in `pass3\`), `.dsh-scratch/FIELD-TEST-FINAL-2026-10-30.md`,
> and the two owner screenshots relayed in words (OWNER-VISUAL, rendering
> only).
```

If the record owner prefers no sixth state (Variant S), the note stands as written. If Variant P is adopted, only the last counts line changes and the word "PARTIAL" joins the state table in the correction block above (one more row there).

---

## 10. Not proposed / left alone

- **The matrix's dated sections** are left as measured: the 2026-10-15 correction block, the first/second/third-pass sections, the build-freshness table (2026-10-11 readings), "The 128 features" heading and its method line. The new dated note in §9 is the only structural addition proposed.
- **The 3 unclaimed rows** (83, 94, 92) — untouched (§4.5).
- **The 104 rows not named in this draft** — untouched.
- **`docs/README.md`** — untouched (no document added anywhere; the count stays 408).
- **`docs/DECISIONS.md`, `CHANGELOG.md`, decision/changelog fragments** — untouched (this is a record-owner edit of one document; no new decision is recorded by a draft).
- **`tools/check_parity.py` and the stale-number work** — not part of this draft (reported separately on the docs branch `docs/stale-refs-2026-10-30`, commit `48609fdab`).

---

## 11. Verification used (read-only)

```powershell
# 1. the matrix file in the primary checkout is clean and identical to origin/main
git -C "C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main" status --short -- docs/FIELD-TEST-MATRIX-2026-10-11.md
git -C "C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main" diff origin/main --stat -- docs/FIELD-TEST-MATRIX-2026-10-11.md

# 2. baseline inventory counted from the matrix's own table (lines 360-495):
#    136 rows -> 10 DRIVEN / 93 SCREEN / 19 BLOCKED / 14 NOT-TESTABLE
#    (old 2026-10-15 blockquote counts 129 rows: 5 / 93 / 19 / 12)

# 3. every BEFORE line in this draft was checked byte-for-byte against the
#    matrix's current line (a one-off script over Get-Content; no writes).
```

**Files written by this task:** this draft only (`.dsh-scratch/FIELD-TEST-2026-10-30/MATRIX-UPDATE-DRAFT.md`).
**Files NOT touched:** `docs/FIELD-TEST-MATRIX-2026-10-11.md`, `docs/README.md`, `docs/FIELD-TEST-FINAL*`, `.dsh-scratch/FIELD-TEST-2026-10-30/REPORT.md`, `tools/check_parity.py`, and every tracked file.
