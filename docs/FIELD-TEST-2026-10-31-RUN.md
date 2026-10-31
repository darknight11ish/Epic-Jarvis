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
