# The field-test run, 2026-10-31 — what the machine drove, and what the owner still owes

**What this is.** The record of the 2026-10-30 evening / 2026-10-31 UTC close-out run,
written up on 2026-10-31: a **real live deploy** of the backend, a **real updater
round trip**, and an agent-driven pass on the phone and desktop on the installed
builds. It is **not** a plan and **not** a suite run. Its one-line-per-step source is
`.dsh-scratch/FIELD-TEST-2026-10-30/pass8/NOTES.md`; the deploy's raw evidence is
`.dsh-scratch/DEPLOY-EVIDENCE-2026-10-31.md`.

**The rule this record runs on, unchanged.** *BLOCKED and NOT-TESTABLE are never
counted as passes.* A step that could not be reached is written **BLOCKED**,
**PARTIAL** or **NOT-TESTABLE**, and reads as such. Only a feature **driven on real
hardware** is a PASS, and a screen read is not a drive. Where this record reasons
from a timestamp or a source read rather than a measurement, it says so in the step.

**Which tree this record was written in.** `origin/main` at **`4b785622c`** (PR #1014,
the Final-1 squash) — that commit is also the deploy ref. Every claim about the repo
was read from that tree; every claim about a live file names the live file. The
repository root's `CLAUDE.md` was not used.

---

## 1. The builds under test

A verdict without its build is not evidence, so each one was read from the thing itself:

| what | the build, and where it was read |
|---|---|
| **Phone** | **0.2.3303**, versionCode `1000003303`, installed from `jarvis-client-4b78562.apk` (34,628,202 B, SHA-256 `FCC30E2B887ED7112F6BF0059FC01BBC7CEBB5760EFFDD45BFEB54B1DD3F029E`) with `adb install -r`. `dumpsys package` shows `versionName=0.2.3303`, `firstInstallTime 2026-10-09 22:14:29` **unchanged** (the pairing survived) and `lastUpdateTime 2026-10-30 23:15:30`. Built from the deployed tree `4b785622c`. |
| **Desktop** | **0.2.368** before the run, **0.2.374** after the updater round trip; installed exe `FileVersion=ProductVersion 0.2.374`, 12,609,024 B. The countdown/Calendar/widget-surface checks below were read on the running 0.2.374 HUD. |
| **Live backend** | deployed at `4b785622c` by repair+reconcile: `jarvis_gate.py` **182,806 B**, SHA-256 `3E9B80689239F5F06F8C85D4FD5CAEA40912B37C60C6083519F3A1B91CC33041`; `jarvis_hud.py` **424,819 B**, SHA-256 `E508CD3E93B469D3CD5BDE0727CC4E0811A4B01B8AE13B6D01D51C3856C98350`; backend pid 37132, listening on 4719. |

The phone's own screenshots of Jarvis content are **black by design**: the app window
carries `FLAG_SECURE`. Every PiP/phone-content claim below is therefore either a text
read (accessibility dump) or a measurement of the window itself, never a reading of
the picture.

---

## 2. The live deploy — 2026-10-30 22:58–23:12 PDT / 2026-10-31 05:58–06:12Z

One pass, RUNBOOK rev 3 (deploy ref `4b785622c`, detached worktree, HEAD == `origin/main`):

- **Preflight (read-only):** LIVE **9/9 file hashes matched** the expected bytes
  (`7DFF103A…26D1`, 175,876 B); exactly one older `jarvis_gate.py.before-repair-*` and
  one older `_jarvis-deploy-backup-tool-*`, so nothing had deployed before tonight.
  Repair check read exactly `ok gate` / `ok history` / `MISSING timer` /
  `MISSING unknown-risk`, exit 1.
- **Repair apply:** `applied timer` + `applied unknown-risk` + 2 `ok`, exit 0; exactly
  one new backup `jarvis_gate.py.before-repair-20261030-225818` (175,876 B, the
  pre-deploy gate); re-check read four `ok … already present`, exit 0.
- **Reconcile dry run:** `to update: 15` SHIPPED, `unchanged: 280`, HUD deltas
  `already present: 216`, **`to insert: 1` → `jobs-routes.patch -> jarvis_hud.py
  (4 hunk(s))`** with `rehearsal: py_compile OK`, no refusal section, exit 0.
  (`show-card-timer.patch` read `already present` — the known Trap-1 false positive,
  proven by the repair chain and the two marker counts instead.)
- **Gemini R7 guard (Step 8b):** live `jarvis_hud.py` copied to
  `jarvis_hud.py.before-jobs-routes-20261030` — 422,109 B, SHA-256 `2B7B020C…`, the
  expected pre-write hash.
- **Apply:** `RESULT: PASS - backend reconciled… wrote 16 file(s)` (= 15 SHIPPED + the
  HUD), probes `PASS setup / PASS media-index / SKIP app-control (expected) / PASS
  voice`; backup folder `_jarvis-deploy-backup-tool-20261030-225949`.
- **Restart:** desktop + backend restarted; 4719 back up as pid 37132; `/api/version`
  answered `server=jarvis-hud`, `api=1`.
- **End-to-end proofs:** a harmless `switch_model` card carried **`expires_in=655`** on
  `/api/pending` and was then **DENIED and gone** (nothing left waiting);
  **`GET /api/jobs` = 200** with `grants=True ticking=True`; the four live HUD markers
  are each present exactly once, and the timer's three markers and unknown-risk's two
  are each present the expected number of times. A second dry run was a no-op, and the
  repair tool then read four `already present`.
- **Rollback state named:** the backup folder above (16 files), the pre-deploy gate
  `jarvis_gate.py.before-repair-20261030-225818`, and the HUD's own pre-write copy.
  Nothing was approved by the deploy: the one card raised was denied.

---

## 3. The updater round trip — 2026-10-30 23:28:36 PDT

The owner said "update jarvis and do everything else you can", so the real updater was
run: `update-jarvis.ps1 -SkipPatches`, exit 0 —

`published desktop version: 0.2.374` → `the download's signature is verified against
the app's own update key` → `the desktop app was replaced with version 0.2.374` →
`Jarvis is answering on this PC` → **`ALL DONE - the desktop app is up to date`**.

The installed exe reads `FileVersion=ProductVersion 0.2.374` (12,609,024 B); desktop
pid 23008 and backend pid 25200 started 23:28:49/23:28:52. `-SkipPatches` left the live
backend **byte-identical** (gate `3E9B8068…C33041` 182,806 B and HUD `E508CD3E…C98350`
424,819 B before and after). The phone dump after the update reads **`Connected - 1
waiting`** with **no re-pair prompt**.

The updater's own post-update live check printed `35 pass / 17 fail / 3 warn`. All 17
FAIL rows are the **known, expected** patch-record drift from deploying by
repair+reconcile instead of re-running the 166-patch installer (4 patch rows such as
`show-card-timer 10/60`, and 13 "changed since the installer wrote it" rows whose live
hashes are exactly the repaired gate and patched HUD). The runbook marks the optional
reseal as expected PARTIAL and **never a pass**; the check changes nothing, so this is
**EXPECTED, not an update failure and not a pass**.

---

## 4. The agent-driven products pass — 23:15–23:25 PDT / 06:15–06:25Z

One line per step; the full record with every dump name is
`.dsh-scratch/FIELD-TEST-2026-10-30/pass8/NOTES.md`.

| step | verdict | evidence in one line |
|---|---|---|
| 1 — APK install-over | **PASS (machine)** | 0.2.3303 installed with `adb install -r`; `firstInstallTime` unchanged; `lastUpdateTime` 23:15:30 |
| 2 — app launch | **PASS (machine)** | `am start` worked, process alive, no FATAL EXCEPTION / AndroidRuntime crash in the last 400 logcat lines |
| 3 — widget after install | **PARTIAL (machine), superseded by I-1** | the card drew words instead of the endless spinner, but the saved board content was not on it yet; the owner glance was owed |
| 4 — live deploy | **PASS (machine)** | repair 2 applied + 2 ok; the jobs-routes hunks inserted; restart; `expires_in=655`; `GET /api/jobs` 200; four HUD markers once each |
| **G-1 — start a job** | **PASS (machine)** | `watch_github` created, ticked, finished: `jobs.created {"id":"60a988548c90","handler":"watch_github","caps":[]}` → `jobs.finished {"state":"done","attempts":1}` → `jobs.tick {"ran":1,"done":1,"waiting":0}` |
| G-2 — the job parks asking one action | **BLOCKED (measured product gap)** | no registered job handler on this PC calls `ctx.require()`: the only registration is `jarvis_watch.py:566` and its handler (`:554-564`) never asks; the other listed kind is refused by the start route. Filed **DEF-024** |
| G-3 — No / Allow once / one-use grant | **BLOCKED** | unreachable because G-2 never parks; the audit has no `jobs.waiting`, `jobs.grant_decided` or `jobs.capability_granted` line |
| H-1 — More sheet doors | **PASS** | exactly five doors + Close (`New chat`, `Photo`, `Attach a file`, `Modes`, `Quick note`); no Earlier chats / Pinned messages / Presets / Notifications row |
| H-2 — Modes sub-sheet | **PASS** | `Think`, `Coach this`, `Incognito`, Back, Close |
| H-3 — Quick note | **PASS (screen) / NOT EXERCISED (filing)** | the panel opened and its words were read; no note was written (a write, and no note app is configured on this PC) |
| H-4 — History header actions | **PASS** | `Pinned` (content-desc "Messages you pinned, newest first."), `New chat`, `Refresh`; Pinned opened `Pinned messages` / `0 pinned messages` / `PINNED MESSAGES` |
| H-5 — History filter row + Filters sheet | **BLOCKED (owner Show)** | with hidden lists ON the body shows only `Hidden. Tap Show and confirm it is you.` + `Show`; the Show control was not tapped |
| H-6 — largest-font crowding | **NOT MEASURED** | font_scale 1.3, the accessibility dump came back rotated/transposed twice (identical 12,862-byte dumps), and the setting was restored to exactly 1.0 |
| F-1 — PiP setting row | **PASS** | the plate was reached via Find anything: four choices Off / The face and the answer / The conversation / Jarvis Live, the Maps comparison, and the never-approves / hidden-host limits |
| F-2 — mode 1 auto-window | **PARTIAL** | Home opened the window by itself (pinned, bounds Rect(442,1984 - 1032,2316)); content unverifiable because the window is `FLAG_SECURE` |
| F-3 — Expand | **PASS** | one tap showed Android's chrome, Expand returned the full app to the same chat; `topResumed=MainActivity` |
| F-4 — Close | **PASS** | Close closed the window, no pinned task left, launcher top, process alive |
| F-5 — mode 2 | **PARTIAL** | "The conversation" selected, window opened, but its measured bounds were identical to mode 1 (590×332, wider than tall) — the addendum's "taller than wide" was **not observed** |
| F-6 — mode 3 + Live | **PASS (mechanics)** | Live started ("Jarvis Live - 30 min left", End Live, Mic off, LiveService running); Home pinned the window; LiveService still running after Home |
| F-7 — mode-1 auto-swap with Live | **BLOCKED / NOT DRIVEN** | the mode-1 reselect did not reach the plate, so the window ran with mode 3; the swap claim is untested |
| F-8 — give it back | **PASS (mechanics)** | End Live pressed, LiveService gone, Home left the window there; the mode-3-with-Live-off sentence is unverifiable |
| F-9 — hidden lists negative control | **BLOCKED (owner fingerprint)** | turning the setting off is a loosening that needs the owner; the hidden sentence itself is unreachable to the agent |
| F-10 — app lock | **BLOCKED (owner fingerprint)** | needs the owner both to turn it on and to turn it back off; not attempted |
| F-11 — Floating Jarvis / overlay | **BLOCKED / NOT DRIVEN** | would change the owner's setting and the one-Jarvis outcome is optical |
| F-12 — face smoothness | **BLOCKED (owner only)** | no eyes and the screencap is black; no frame measurement is possible from here |
| **F-13 — Off** | **PARTIAL / CONTRADICTED** | `Off` selected (`checked=true`), yet Home left a PiP window on screen, and it appeared again after a force-stop + fresh start with Off stored; closing it worked and the launcher was clean. Filed **DEF-023**, needs a clean retest |
| W-1 — widget after reconnect | **PASS (machine), upgrades step 3** | the card draws `Next Reminders` / `Coming up` / `Hidden - open Jarvis to see it.` — words, the saved widget's title, and the privacy wording; content hidden by design needs no owner glance |
| B-1 — desktop drawn countdown | **PASS (machine)** | HUD card bar drew `NEEDS YOUR OK` / `14m 49s left`, then `14m 36s left` 12 s later; `/api/pending` read `expires_in=889` then `875` |
| B-2 — phone drawn countdown | **PASS (machine)** | the drawn card read `Expires in 14 minutes`, then `13 minutes` (TalkBack's own words — minute granularity; no literal `EXPIRES IN <n>m` string is drawn) |
| B-3 — deny leaves nothing | **PASS (machine)** | both cards denied from the PC: `DENIED and gone: 673b64d1c338` and `DENIED and gone: 00fa67a6f8dd`; neither appears in `/api/pending` afterwards |
| C-1 — desktop Calendar panel | **PASS (machine)** | UIA harness attached to the running HUD (66 descendants), opened the Calendar door with ENTER (no Invoke pattern), read `CALENDAR`, `Today`, `October 2026`, Month/Week/Day and the day cells, then closed it with its own button (0 remnants) |
| D-1 — updater round trip | **PASS (machine)** | §3 above |
| D-2 — post-update live check | **EXPECTED, not a pass** | §3 above: 17 FAIL rows are the documented patch-record drift after repair+reconcile |

---

## 5. What the matrix got

`docs/FIELD-TEST-MATRIX-2026-10-11.md` carries the dated pass-8 block and these moves:

- **3 rows moved to DRIVEN:** `widgets` 21 (the F5 PASS bar is met: the card itself
  reads "Next Reminders"), `jobs` 22 (DRIVEN with the limit named — start/run only),
  `updates` 106 (the real updater round trip).
- **2 new rows:** 137 the card timer (#1006, DRIVEN machine), 138 Android PiP (#1013,
  DRIVEN with the limit named: mechanics only).
- **3 dated notes, state unchanged:** `history` 39, `calendar` 71 (the desktop limit is
  now closed; the row itself does not move), `notes-write` 50 (screen read, no write).
- **1 row deliberately not touched:** `job-list` 102 (the job finished before the list
  was read).
- **Inventory after the pass: 31 DRIVEN / 75 SCREEN / 19 BLOCKED / 13 NOT-TESTABLE =
  138 rows** (was 26 / 78 / 19 / 13 = 136).

---

## 6. Defects filed

- **DEF-023 — PiP mode "Off" does not prevent the window** (open, claimed by `lead`,
  2026-10-31). Measured: Off was stored and selected, the window still appeared after
  Home, and again after a force-stop + fresh start; closing it worked. It is **not yet
  proven** whether the setting fails to stop the current process's entry or fails to
  persist — a clean retest on a fresh process distinguishes the two. Evidence
  `pass8/NOTES.md` F-13, `p8-pip-off.xml`, `pip-13-check.png`,
  `pip-13d-off-freshstart.png`.
- **DEF-024 — no registered job handler calls `ctx.require()`, so no job can park on
  this PC** (open, claimed by `lead`, 2026-10-31). Measured: the only registration is
  `watch_github` (`jarvis_watch.py:566`) and its handler (`:554-564`) never asks; the
  other listed kind is refused by the start route. The park / No / Allow once /
  one-use-grant steps are unreachable on this PC. **Not a phone defect** — the phone
  started and ran a real job. Evidence `pass8/NOTES.md` G-2/G-3,
  `jobs-audit-lines.jsonl`.

---

## 7. The exact FAIL / BLOCKED / NOT-MEASURED list

- **BLOCKED (owner):** F-9 hidden-lists negative control, F-10 app lock, H-5 History
  filter row + Filters sheet (all behind the owner's biometric Show); F-12 face
  smoothness (owner only).
- **BLOCKED (product gap, not the test):** G-2 park / G-3 No / Allow once / one-use
  grant — DEF-024.
- **BLOCKED / NOT DRIVEN:** F-7 mode-1 auto-swap, F-11 Floating Jarvis interaction.
- **PARTIAL:** F-2 mode 1 (mechanics pass, content unverifiable), F-5 mode 2 (window
  opened; expected taller-than-wide aspect not observed), F-13 Off contradicted
  (DEF-023), H-3 Quick note (screen read, filing not exercised).
- **NOT MEASURED:** H-6 largest-font crowding (dump returned rotated; setting
  restored).
- **No FAIL row was recorded in this pass.** The one previous FAIL (row 44, the
  "Jarvis is watching" badge) is not retested here and stays FAIL.

**Every one of these is a non-pass.** A PARTIAL/BLOCKED step is never read as a pass
anywhere in this record or the matrix.

---

## 8. The owner-only remainder

The machine half is done; these need the owner's hands (and are the rows that stay
BLOCKED otherwise), taken from `OWNER-SITTING-2026-10-31.md`:

1. **The one Show** (fingerprint/PIN) — unlocks the History archive round trip (row
   39), the Galaxy picture (row 130) and the hidden-memory rows.
2. **App control, five guards** — Android's Accessibility switch, the Clock-only
   allow-list, one approve, one deny, Stop; the live PC side is already ON.
3. **PiP content and lock steps** — the hidden/locked sentences, the app-lock test,
   the overlay interaction, and one sentence on how smooth the face looks in the
   window. The Off contradiction (DEF-023) should be re-checked on a fresh process.
4. **A glance at the drawn countdown** and the **desktop Calendar panel** if the owner
   wants to confirm by eye what the machine already read; the widget repaint needs no
   glance (W-1 measured it).
5. **The update round trip is already done** by the machine (§3), so the owner's F6
   step is only to confirm the app runs normally.

Owner-visible items are recorded in the matrix and here as **PARTIAL/BLOCKED until
driven**; the owner's observation starts a row, and the record completes it.

---

## 9. Honest limits of this run

- **The phone's Jarvis content is black in every screenshot** (`FLAG_SECURE` by
  design), so PiP content, hidden/locked wording and the countdown's drawn *look* are
  text reads or measurements, never visual confirmation.
- **The widget's content is hidden by the owner's setting** — that is the design, not
  a defect; what matters (the saved widget's title and the privacy wording) is drawn.
- **The largest-font check failed on the instrument**, not on the screen: the
  accessibility dump came back rotated and transposed twice, the font scale was
  restored, and the row says NOT MEASURED rather than guessing.
- **No external calendar account was touched**; the desktop Calendar panel was read
  in its empty state (the field-test event had been deleted).
- **F-7 and F-11 were not attempted** rather than claimed: one would change a setting
  and the other's outcome is optical.
- **The deploy's drawn surfaces are proven; the deploy's live runtime proofs are in
  §2** (timer `expires_in`, jobs 200, restart banner). The record reseal was
  deliberately not run — the runbook marks it optional and expected PARTIAL.
- **This agent session cannot host an interactive desktop app**; the desktop checks
  that need a GUI were done through the installed builds and the UIA harness, and the
  rest remain the owner's.

---

## 10. Evidence index

- One line per step, with every dump name: `.dsh-scratch/FIELD-TEST-2026-10-30/pass8/NOTES.md`.
- Deploy: `.dsh-scratch/DEPLOY-EVIDENCE-2026-10-31.md`; runbook and rollback:
  `.dsh-scratch/DEPLOY-RUNBOOK-2026-10-30/RUNBOOK.md` (rev 3).
- Updater: `F6-UPDATE-RUN-2026-10-31.log`, `_jarvis-logs\preflight-2026-10-30-232836.txt`,
  `pass8\desktop-after-update.png`.
- Owner checklist: `.dsh-scratch/OWNER-SITTING-2026-10-31.md`.
- Defects: `docs/defect-register.tsv` (DEF-023, DEF-024) and `docs/DEFECT-REGISTER.md`.
- Matrix: `docs/FIELD-TEST-MATRIX-2026-10-11.md`, the "UPDATED 2026-10-31, pass 8"
  block and rows 21, 22, 39, 50, 71, 106, 137, 138.

---

## Pass 9 — the calendar driven end to end, and what the chat knows (2026-10-31 01:09–01:55 PDT)

**What pass 9 was.** The overnight pass after the machine run above: the calendar feature driven one
surface at a time on the installed builds, then a second set of questions on whether Jarvis can
answer about its own features. It used **two instruments, named because the Windows shells differ in
integrity level**: desktop PART A/B by **the Lead's shell, Medium Mandatory Level `S-1-16-8192`,
Windows UI Automation + CopyFromScreen**; the phone half by **field-test's own shell, Low Mandatory
Level `S-1-16-4096`**, through `adb` (`am start`, `uiautomator dump`, `screencap`). UIPI blocks the
Low shell from the Medium HUD window (`pass9/desktop-privilege-evidence.txt`), which is why the two
halves could not be driven by one instrument. Builds: **desktop 0.2.374** (`/api/version` 0.40.12;
desktop pid 14152, backend pid 16356 after the runbook-step-10 restart), **phone 0.2.3303**
(versionCode 1000003303, lastUpdate 2026-10-30 23:15:30), live backend on 4719. The phone build
predates #1018 (the PiP Off fix merged later that morning); pass 9 did not re-drive PiP.

**Repairs before the test, measured.** The running HUD was blank - pid 29596 had the window title
`Jarvis` but a UIA tree of 7 chrome elements and no `msedgewebview2` child. The documented restart
fixed it (stop the app and the stale backend on 4719, start `jarvis-desktop.exe`): afterwards 8
WebView2 children and **UIA descendants 66**. The three `0xc0000409` WER events at 01:11 were
**second-instance launches while the app was already running**, not a crash of the running app.

### PART A - desktop calendar (Lead's shell, UIA): 8 of 8 driven rows PASS

| row | what was driven | what the app said (quoted) | verdict |
|---|---|---|---|
| A1 | the rail's Calendar door, UIA focus + ENTER (it has no Invoke pattern) | panel: `CALENDAR`, `Times in America/Los_Angeles`, `Close the calendar`, `Today`, prev/next, `October 2026` | **PASS** |
| A2 | Month view, six-week grid + side panel | `Sunday 27 September 2026, nothing` … `Saturday 7 November 2026, nothing`; selected `Saturday 31 October 2026`; footer `Your own events, on this PC · Google Calendar is read in chat only · Your iCal calendar is read in chat only` | **PASS** |
| A3 | Week tab | header `Sun 25 Oct – Sat 31 Oct 2026`, `No events this week.`, seven day rows | **PASS** |
| A4 | Day tab | header `Saturday 31 October 2026`, week strip SUN 25 … SAT 31 with 31 highlighted | **PASS** (state change). Note: the month grid's day cells stay in the UIA tree in Week/Day - hidden DOM, a text-extraction property, not the app failing |
| A5 | Add form, read-only | `New event`; EVENT, DATE, ALL DAY, STARTS, ENDS, LAST DAY, REMIND, PLACE, REPEATS, NOTES; `Add event` / `Cancel`; `A reminder is saved with the event; this slice does not ring it.` | **PASS (screen read)** |
| A6 | Cancel with the form's own Cancel | form gone, nothing created, side panel back to `Nothing on Saturday 31 October 2026.` | **PASS** |
| A7 | `Close the calendar` | no `calendar-panel` element remains | **PASS** |
| A8 | Settings → Jarvis Calendar switch, read only | `On. The Calendar card is drawn in the HUD, and the phone's Calendar screen works.`; `Turn the Jarvis Calendar off`; account rows `Jarvis Calendar`, CALENDAR ICAL LINK, CALENDAR (CALDAV) ADDRESS | **PASS (state read; nothing toggled)** |

**Owner-only, never passes:** A9 edit/delete an existing event (none exists on the desktop and
writing one was not authorised), A10 switch the calendar off (an owner setting write), A11 outside
calendars (a credential write; the chat's own unsolicited connect-account dialog was cancelled),
A12 briefing extras and A13 "parking for my next meeting" (no briefing or outside-calendar event
exists on this PC tonight).

### PART B - chat answering about its own features (Lead's shell): 2 of 8 accurate

| # | question | answer (verbatim in `lead/LEAD-DRIVE.md`) | verdict |
|---|---|---|---|
| Q8 (control) | `what is the time?` | `It is 01:22 on Saturday 31 October.` | **ACCURATE** |
| Q1 | `what can you do with the calendar?` | generic model text claiming availability and invitations that are not built; never names the HUD card, the three views, the Add form or the local/Google/iCal split | **WRONG** |
| Q2 | `can you add something to my calendar?` | did not answer, and raised an unsolicited `Connect an account — CALENDAR - THE PRIVATE ICAL LINK` dialog (cancelled; nothing saved) | **WRONG** |
| Q3 | `what are the smart features of the calendar?` | `I am currently unaware of these details…` | **WRONG** |
| Q4 | `what can you edit in my notes?` | claimed it can add entries / open a Notes application that is not deployed (also a red `Could not reach Jarvis: the request was cancelled or timed out` harness artefact from overlapping questions) | **WRONG** |
| Q5 | `can I protect a folder from you?` | invented a filesystem-permissions workaround because Protected from Jarvis is not deployed | **WRONG / unknowing** |
| Q6 | `what is picture-in-picture?` | answered from the feature list: `Phone-Only Setting`, the Maps comparison, the never-approves limits, `It is on the phone only` | **ACCURATE** |
| Q7 | `what's my next reminder?` | `I am currently unaware of your next reminder` + "device's notification history", which it cannot read | **WRONG** |

**What PART B proves:** "ask Jarvis what it can do" is **not** a trustworthy feature list on this
build - 2 of 8 answers were accurate, and the two that were came from the feature list or the clock.
The feature guide screen is the trustworthy list.

### The phone half (field-test's shell, adb): P1-P8/P12 PASS, Edit read-only

| row | what was driven | evidence | verdict |
|---|---|---|---|
| P1 | Calendar screen: 7-column month grid, today marked, event counts | `Thursday 1 October, not read` … `Saturday 31 October, today`; after the test event `1 event, hidden` | **PASS** |
| P2 | month navigation ‹ / Today / › | `September 2026` → `October 2026` → `November 2026` | **PASS** |
| P3 | selected-day list + empty state | `Today`, `Add`, `Nothing on this day.` | **PASS** |
| P4 | Add sheet fields, read-only | WHAT IS IT?, DATE 2026-10-31, TIME 09:00, All day, LAST DAY, ENDS, WHERE, NOTES, REMIND ME, Repeats `Does not repeat (Chosen)`, `Kept on your PC, beside your reminders. No card, and nothing leaves this PC.` | **PASS** |
| P5 | save one clearly-named test event | `ZZ field test delete me` at 09:00 today, drawn `09:00 / (hidden) / Edit / Delete`, cell `1 event, hidden` | **PASS** |
| P6 | Edit opens prefilled | date/time prefilled; title box empty under hidden lists; cancelled with system Back, no write | **PASS (screen read; not saved)** |
| P7 | Delete with confirmation | `Delete this event?` / `One event on your PC. This cannot be undone.` / `Keep it` / `Yes, delete it` → `Deleted.`; read-only DB check then `events` count 0 | **PASS** |
| P12 | no Android calendar permission | `dumpsys package com.jarvis.client`: no READ_CALENDAR / WRITE_CALENDAR | **PASS** |
| P8 | hidden-lists title redaction | drawn title `(hidden)`, place/recurrence suppressed (`CalendarPlate.kt:562`); **but the a11y tree carried the full title** - see below | **PASS (drawn) + finding** |

**Blocked / not-reachable, never passes:** P9 the phone's Jarvis Calendar switch (not located in
Settings; the desktop state was read in A8), P10 the home-screen calendar widget (only the board
widget is placed; placing one needs the owner), P11 the Brain row beside Coming up (not on
0.2.3303; the screen was reached through the widget's own `OPEN_CALENDAR` intent), P13 off state /
recurrence / DST / reminder ringing (needs the switch or writes beyond the one authorised event;
`Nothing rings yet` by design).

**The privacy finding (DEF-025).** With "Hide memory lists and chat history" ON, the phone drew
`(hidden)` and suppressed place/recurrence, but the same accessibility dump also carries a TextView
with the full test-event title - `text="ZZ field test delete me, Saturday 31 October at 09:00."`,
node index 49, bounds `[36,1883][1033,1922]` (`p9-cal-saved.xml`). The screen is FLAG_SECURE, so the
pixels cannot be checked from here, and the root cause (which composable emits that node, and
whether it is visible or only TalkBack-readable) is **not determined**. It is recorded as a finding,
not a claimed-exploited defect: it needs the owner's own eyes, then a fix decision.

### What the matrix got from pass 9

Three new rows, continuing the sequence: **139** `calendar-hud` (DRIVEN, A1-A8), **140**
`calendar-phone` (DRIVEN with the limits named, P1-P8/P12), **141** `feature-qa` (DRIVEN, the
2-of-8 result). Inventory after the pass: **34 DRIVEN / 75 SCREEN / 19 BLOCKED / 13 NOT-TESTABLE =
141 rows** (was 31 / 75 / 19 / 13 = 138).

### Honest limits of pass 9

- **BLOCKED and NOT-REACHABLE are never passes.** A9-A13, P9-P11 and P13 are blocks, not failures
  of the feature.
- **The two shells differ by integrity level** - that is why the desktop half is the Lead's
  instrument; the Low shell could not type into or read the HUD (UIPI), not even with
  `keybd_event` / `SetForegroundWindow` / `PrintWindow`.
- **Phone screenshots are black by design** (`FLAG_SECURE`); the accessibility dumps are the record,
  and that is also why P8's finding is "needs the owner's eyes", not a confirmed leak.
- **The owner's Show was not available**, so hidden lists stayed hidden throughout.
- **One clearly-named test event was created and deleted** on the phone's own calendar, exactly as
  the task allowed; the live `calendar.db` was then verified read-only (`events` count 0). Nothing
  else was written and no card was approved (one card the chat raised was cancelled).
- The phone build predates **#1018** (PiP Off fix), so nothing PiP-related is claimed in this pass.

### Evidence index for pass 9

- The whole pass, one line per step: `.dsh-scratch/FIELD-TEST-2026-10-31/pass9/NOTES.md`.
- Desktop/chat drive and raw captures: `.dsh-scratch/FIELD-TEST-2026-10-31/pass9/lead/LEAD-DRIVE.md`,
  `lead/q0*.txt/.png`, `lead/calendar-*.txt/.png`, `lead/settings-elements.txt`, `lead/hud.ps1`,
  `lead/chat.ps1`.
- Phone dumps: `.dsh-scratch/FIELD-TEST-2026-10-31/pass9/p9-*.xml`, `check_cal_db.py`,
  `phone-ui9.ps1`; the FLAG_SECURE screenshot `p9-calendar.png`.
- Environment boundary: `pass9/desktop-privilege-evidence.txt`.
- Matrix: the "UPDATED 2026-10-31, pass 9" block and rows 139-141.
- Defects: `docs/defect-register.tsv` (DEF-025) and `docs/DEFECT-REGISTER.md`.

---

## Pass 10 — the PiP Off fix confirmed on the new APK, the calendar's write half driven, the notes editor and Protected from Jarvis reached (2026-10-31 05:40–08:30 PDT)

**What pass 10 was.** The morning pass after the 2026-10-31 deploy, in two halves with the same two
instruments pass 9 used. **The phone half** (2026-10-31 07:54–08:30 PDT) ran on **0.2.3326 /
versionCode 1000003326**: `lastUpdateTime 2026-10-31 06:19:17`, `firstInstallTime` unchanged at
2026-10-09 22:14:29 (install-over, pairing kept), 1080×2412; the client release is "Jarvis for
Android 0.2.3326 (main @ 8f7e165)", which includes #1017 (notes), #1018 (PiP Off) and #1019
(Protected from Jarvis). It was driven by **field-test's own shell, Low Mandatory Level
`S-1-16-4096`**, through `adb` (`am start`, `uiautomator dump`, `screencap`); Jarvis screens are
FLAG_SECURE, so the accessibility dumps are the record. **The desktop half** was **the Lead's own HUD
drive** on desktop **0.2.376** (installed 06:13 PDT) against the live backend from the deployed wave
(`/api/protection` 200, `/api/notes/list` 200, vault configured), through **Windows UI Automation** -
the app's real controls, not screenshots.

### The PiP "Off" retest - PASS on 0.2.3326 (DEF-023/F-13's on-device retest is DONE)

| step | what was driven | measured result | verdict |
|---|---|---|---|
| 1 | PiP plate, Off selected, press Home | plate reads the four choices plus **"Off. Leaving Jarvis just puts it in the background."**; `dumpsys activity` has **no `mode=pinned` task**, top task is the launcher, `p10-pip-off-home.png` is the launcher alone - **no window** | **PASS** |
| 2 | force-stop + fresh start, Off still stored, press Home | `am force-stop com.jarvis.client` (pid gone), relaunch (new pid); Off still stored; Home → **no pinned task**, launcher top, `p10-pip-off-fresh-home.png` launcher alone - **no window** | **PASS** |
| 3 | the three non-Off modes still enter PiP | "The face and the answer" → pinned task + window (`p10-pip-mode1.png`); "The conversation" → pinned task + window (`p10-pip-conv.png`); "Jarvis Live" → pinned task + window (`p10-pip-live.png`) | **PASS** |
| 4 | restore the found state | Off re-selected (checked node `[90,792][301,936]`), Home → no pinned task, `p10-pip-off-restored.png` launcher alone | **PASS** |

**So the pass-9 F-13 contradiction does not reproduce on 0.2.3326**: with Off stored, the window does
what the plate says. DEF-023's on-device retest is **done and passes**; its register row is the
owner's to close (this fold records the evidence and does not close it).

### Phone pass 10 - what was reached, and what was not

| step | what was driven | measured result | verdict |
|---|---|---|---|
| 2 | Protected from Jarvis, live | Settings search "protected" → "1 setting matches." → PROTECTED FROM JARVIS with the plate's own words (what may not be touched; Blocked / Read-only), the empty state ("Nothing is protected yet. Add folders, files and programs on your PC - or ask Jarvis in chat from here and it will raise a card… Removing one asks for one card too."), and **no Add/Remove control by design** - nothing added or removed (`p10-se-res.xml`) | **PASS (read only)** |
| 3 | Notes editor, live | the plate exists (Brain → "What Jarvis knows about you" → NOTES) but drew **"Hidden. Tap Show and confirm it is you."** + a `Show` button; the owner's hidden-lists setting is ON and was not changed, so the content read needs the owner's fingerprint - **not tapped**. Settings search "notes" → WHAT JARVIS CAN REACH (no Notes settings row by design). The vault file itself is 205 B (`C:\Users\pcadmin\Documents\Obsidian Vault\Welcome.md`) | **PARTIAL / BLOCKED (owner Show)** |
| 4 | DEF-025 evidence, live | one clearly-named test event **"ZZ pass10 def025"**, 2026-10-31 09:00, created through the phone's own Add; with hidden lists ON the drawn title is `(hidden)` (node `bounds=[36,1668][204,1721]`) and the **same accessibility tree holds the full title** as class `android.widget.TextView`, `text='ZZ pass10 def025, Saturday 31 October at 09:00.'`, `bounds=[36,1883][948,1922]`. Deleted through the app's own flow ("Deleted." / "Nothing on this day."); the live `calendar.db` was read back **`events` 0**, no titles | **PASS: reproduced (evidence for open DEF-025)** |
| 5 | Calendar widget | long-press Home → Widgets worked; the picker lists **"Jarvis Calendar 4 × 2"** with the quick-link and board widgets; two adb placement attempts (`input swipe` long-press-drag, then `input draganddrop 726 899 540 1500 1500`) placed a Google "Collections Widget" instead and nothing from Jarvis. The accidental widget was removed via its own "Remove widget" and the launcher was verified clean (`p10-home-after-drag.xml`, `p10-editmenu.xml`, `p10-home-cleaned.xml`); net effect on the owner's launcher: none | **NOT-REACHABLE (placement)** |
| 6 | Menus / settings search | "protected" landed right; "notes" → 1 match → WHAT JARVIS CAN REACH (by design); SHOW OR HIDE MENUS read ("This hides menus on this device only." / "Hiding a menu only tidies it away…" / always-visible list / "Nothing is hidden." / per-menu rows). **The hide → confirm → unhide loop was NOT completed** and no row was toggled, so nothing was left changed | **PARTIAL** |
| 7 | Sanity | force-stop then launch: new pid 31002, home draws "Connected", no `FATAL EXCEPTION` / `AndroidRuntime` crash lines for `com.jarvis.client` since the launch; `versionName=0.2.3326`, `versionCode=1000003326`, 1080×2412; pairing intact | **PASS** |

### Lead's desktop drive - what passed, what failed, what was blocked

| part | measured result | verdict |
|---|---|---|
| Calendar write half (A9–A12) | add "ZZ deploy test delete me" (`/api/calendar` 1 event, `id c1df84ec7b8`), edit to "ZZ edit test EDITED" (the change stuck), two-step delete ("Press again to delete") → `/api/calendar` 0 events; every step read back live, 0 events left | **PASS** |
| Protected from Jarvis card | heading + the PC's own sentence + empty state + the three pickers `Add a folder…` / `Add a file…` / `Add a program…`; `GET /api/protection` 200, `count: 0`, `modes: ["blocked","readonly"]`. Add/remove by hand NOT driven on purpose (an entry cannot be undone without the owner's removal card) | **PASS (read); add/remove BLOCKED (owner card)** |
| Chat about its own features | 4 questions after the deploy: 0 of 4 accurate (pass 9: 2 of 8) - notes edit claimed impossible, protection invented a permissions workaround, calendar "smart features" unknown/generic, notes read/edit understated | **FAIL (quality defect; fix in progress)** |
| "open settings" / "open the second brain" typed in the HUD | "Opening Jarvis settings on this PC." - no Settings window; "I have asked this PC to open brain." - nothing opened, "brain" treated as a program; a direct `POST /api/chat` returned a model answer with no open field (the HUD page sends the owner's message with provenance "typed"; the hand-made POST did not) | **FAIL (both fixed on branches for the next build)** |
| Notes editor Brain card | NOT DRIVEN: the Brain window could not be opened from the HUD (tray "Open the Brain" unreachable through UIA; the typed phrase is the defect above). The editor is live at the API: list 200, read 200 (sha `add7b780…`), save → one `edit_vault_note` card, **denied**, bytes unchanged | **NOT-REACHABLE (this build)** |

### What the matrix got from pass 10

Six new rows, continuing the sequence: **142** the notes editor (SCREEN, with its PARTIAL/BLOCKED
limits named and the API-level drive recorded), **143** Protected from Jarvis (DRIVEN, read-only),
**144** the desktop calendar's write half (DRIVEN, A9–A12), **145** the notes editor's Brain card
(BLOCKED, not-reachable this build), **146** the phone's home-screen calendar widget (BLOCKED,
not-reachable placement), **147** show-or-hide menus (SCREEN, PARTIAL note). Rows **138**
(`android-pip`) and **141** (`feature-qa`) are updated with dated notes; their states do not change.
Inventory after the pass: **36 DRIVEN / 77 SCREEN / 21 BLOCKED / 13 NOT-TESTABLE = 147 rows** (was
34 / 75 / 19 / 13 = 141; 2 new DRIVEN, 2 new SCREEN, 2 new BLOCKED).

**Defects.** **DEF-025 is reproduced on 0.2.3326** and stays **OPEN** (fix PR #1026 awaits CI/merge
and an on-device confirm); its register row carries the pass-10 sentence. **No new defect row came
from pass 10** other than that reproduction - the two open-place FAILs already have fixes on branches
and are recorded here for the next build's drive, not filed as new rows.

### Honest limits of pass 10

- **BLOCKED / PARTIAL / NOT-REACHABLE are never passes.** Step 3 (owner's Show), step 5 (launcher
  placement), step 6 (hide/unhide loop), the Protected add/remove half, the notes Brain card and the
  desktop calendar's owner-only A13 (outside calendars, credentials) are blocks, not failures.
- **The phone's window is FLAG_SECURE**: screenshots of Jarvis content are black; the dumps are the
  evidence, and that is also why DEF-025's pixels were not checked - the dump is the proof, the
  owner's eyes still decide whether it is visible or TalkBack-only.
- **Two deliberate side effects, both undone and verified:** one test event created then deleted
  (live DB count 0) and one accidental launcher widget added then removed (home clean). No approval
  card was approved or denied; the one card the desktop raised (the notes save) was denied.
- **The desktop drive could not re-drive the notes Brain card or the open-place fixes** - the former
  needed the HUD to open the Brain, which is the open-place defect; both are for the next build.
- **"Open my calendar" was not credited from the typed-chat path** (the rail's calendar was verified
  in pass 9; this pass did not re-drive the phrase) and the AI chat answers were not fixed by this
  pass - only measured.

### Evidence index for pass 10

- The phone half, one line per step and the honest limits: `.dsh-scratch/FIELD-TEST-2026-10-31/pass10/NOTES.md`
  (142 lines, 198 captures named).
- The Lead's desktop drive: `.dsh-scratch/FIELD-TEST-2026-10-31/pass10/lead/DESKTOP-DRIVE.md`.
- Phone dumps and screenshots: `.dsh-scratch/FIELD-TEST-2026-10-31/pass10/p10-*.xml/.png/.txt`
  (`p10-pip-*`, `p10-se-res.xml`, `p10-knows3.xml`, `p10-sd-res.xml`, `p10-def-*.xml`,
  `p10-widgets-jarvis.xml`, `p10-home-*.xml`, `p10-editmenu.xml`, `p10-menus*.xml`, `p10-s-res.xml`,
  `p10-after-relaunch.xml`, `p10-cal-*.xml`).
- Matrix: the "UPDATED 2026-10-31, pass 10" block and rows 138, 141, 142-147.
- Defects: `docs/defect-register.tsv` (DEF-025, reproduced) and `docs/DEFECT-REGISTER.md`.
