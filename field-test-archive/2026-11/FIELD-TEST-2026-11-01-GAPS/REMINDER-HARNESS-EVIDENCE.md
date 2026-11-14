# Reminder harness assertions — evidence (Gemini review 2026-11-01, item 2)

Written 2026-11-01 (run 15:06–15:07 PT) by the field-test workstream. Everything here is
under `.dsh-scratch\FIELD-TEST-2026-11-01-GAPS\`; nothing else was edited, no commit, no
deploy, no backend restart, no config change.

**What this closes.** Gemini item 2, from pass-16's own evidence: the HUD said
`"Got it - reminder set for 05:37"` and then `"Cancelled: the reminder for 05:37 today"`,
and `B-reminder-create` / `B-reminder-cancel` were written on those words alone while
`/api/schedule` was `[]` at the end of that run. Nobody had measured whether a job really
existed, or really went away. Both rows now read `GET /api/schedule` themselves.

**Which tree / backend was asked.** The **LIVE install** on this PC — backend
`http://127.0.0.1:4719`, folder `C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program`,
HUD window `Jarvis`, desktop **`0.2.387`** (read from the running `jarvis-desktop.exe` at proof
time; the last field-test gate recorded `0.2.386`). **Not** a repo worktree, and not a copy.

---

## 1. What changed in the harness

| File | Change |
| :--- | :--- |
| `gaps6.ps1` | **+82 lines** (206 → 288): a new `# ==== REMINDERS ====` section at line 132, between the HUD block and the PHONE block, adding the two rows `B-reminder-create` and `B-reminder-cancel`, each with the `/api/schedule` assertion. No existing line was changed, moved or deleted. |
| `reminder-schedule.ps1` | **New.** The one token reader and `/api/schedule` reader, plus the two row bodies (`Invoke-ReminderCreateProof`, `Invoke-ReminderCancelProof`) so the live proof drives exactly the code the field test drives. |
| `reminder-live-proof.ps1` | **New.** The one live drive: idle gate → baseline → HUD create → schedule assert → HUD cancel → schedule assert → leftover cleanup. |
| `selftest-reminder-rows.ps1` | **New.** Reads the REMINDERS section out of `gaps6.ps1` itself and runs it with **fake** measurements (no HUD, no reminder, no write): 5 scenarios / 11 checks, `SELFTEST PASS`, exit 0. |
| `logs\reminder-live-proof-20261101-150659.txt` | **New.** The measured proof (raw statuses, counts and job words). |
| `results.tsv` | The two rows added as **PASS** with the measured detail (see §3 for why they were added rather than edited). |

### `gaps6.ps1` diff shape

```
 line 130  }                              <- end of the existing HUD block (unchanged)
 line 132  # =============================== REMINDERS ====================================
 line 133  # Gemini review 2026-11-01 item 2 (pass-16 PHASE-B-VERDICT §1): ... (why)
 line 146  if ($deskGate.ok) {
 line 147    . (Join-Path $PSScriptRoot 'reminder-schedule.ps1')
 line 152    $baseSnap = Get-ScheduleSnapshot            # baseline BEFORE the create
 line 154    $remBase = $baseSnap.jobs.Count
 line 155    $cr = Invoke-ReminderCreateProof -MinutesAhead 3 -MaxWaitSec 240
 line 157    $file = Save-Evidence 'B-reminder-create' (...)   # ask, answer, said time, counts, job
 line 165    if ($cr.saidTime -and $cr.matched -and ($cr.afterCount -eq ($cr.beforeCount + 1)) ...) {
 line 166      $st = 'PASS'
 line 167    } elseif ($cr.snapshotOk -and a job appeared -and -not $cr.saidTime) {   # half proven
 line 169      $st = 'PARTIAL'
 line 170    } else {
 line 171      $st = 'FAIL'
 line 173    Write-Row 'D6' 'B-reminder-create' $st ...
 line 176    } catch {
 line 177      Write-Row 'D6' 'B-reminder-create' 'BLOCKED-PC' ...
 line 182    try {
 line 183      if (-not $remCreated) { throw 'no reminder job was created and identified...' }
 line 184      $ca = Invoke-ReminderCancelProof -CreatedJob $remCreated -ExpectedCountAfter $remBase ...
 line 185      $file = Save-Evidence 'B-reminder-cancel' (...)
 line 193      if ($ca.snapshotOk -and $ca.removed -and ($ca.afterCount -eq $remBase) -and $ca.saidCancel) {
 line 194        $st2 = 'PASS'
 line 195      } elseif ($ca.snapshotOk -and $ca.removed -and ($ca.afterCount -eq $remBase)) {  # gone, unsaid
 line 197        $st2 = 'PARTIAL'
 line 198      } else {
 line 199        $st2 = 'FAIL'
 line 201      Write-Row 'D6' 'B-reminder-cancel' $st2 ...
 line 204    } catch {
 line 205      Write-Row 'D6' 'B-reminder-cancel' 'BLOCKED-PC' ...
 line 209  } else {                       <- the desktop gate failed: both rows BLOCKED-PC
 line 210    Write-Row 'D6' 'B-reminder-create' 'BLOCKED-PC' ...
 line 211    Write-Row 'D6' 'B-reminder-cancel' 'BLOCKED-PC' ...
 line 214  # ================================ PHONE =======================================  (unchanged)
```

The statuses are computed from the measurement, never hardcoded: a wrong count is `FAIL`,
an unreadable schedule is `BLOCKED-PC`, a job that appeared without the HUD naming its time
is `PARTIAL`. The count assertions are **baseline-relative** (the count read before the
create), so a pre-existing timer or alarm cannot false-fail the row; on this install the
baseline was `0`, so the assertions were literally *1 job after the create, 0 after the
cancel*.

`Windows PowerShell 5.1` compliance: the whole file parses with **0 errors** under the 5.1
parser (`[System.Management.Automation.Language.Parser]::ParseFile` on
`powershell.exe 5.1.26100.9711`), there is no `??`, no ternary and no `-AsHashtable`, and
the proof was executed by `powershell.exe` 5.1, not 7.

**The token.** Read once, by the same reader every other field-test script uses — the
backend's own store: `py -3 "<live>\jarvis_token_store.py" show` (pass-15
`common15.ps1`'s `Get-Token` and `probe_live.py`'s `selftest.Live` do the same). It is held
in a script variable, used only inside request headers, and never printed, logged or put in
an error sentence. Checked after the run: of the 6 files under `logs\` and
`captures\reminder\`, **0** contain the token.

---

## 2. The live proof (measured, 2026-11-01 15:06:59–15:07 PT)

Log: `logs\reminder-live-proof-20261101-150659.txt` (raw, 30 lines). The HUD was driven with
pass-12's `Ask-Hud` (UIA, Medium integrity) — the same helper pass-16 used.

| Step | Measured |
| :--- | :--- |
| 0 idle gate | `GET /api/pending` HTTP **200**, `available=True`, **waiting cards = 0**; HUD window `Jarvis`, `busy=False`, `denyButtons=0` |
| 1 baseline | `GET /api/schedule` HTTP **200**, **jobs = 0**, `todo = 0`, `now=1793574420.56`, `tz=Pacific Standard Time` |
| 2 create (HUD) | asked `make a reminder for 3 minutes from now to check my phone`; HUD answered `Got it - reminder set for 15:10, in 3 minutes.` |
| 3 assert after create | `GET /api/schedule` **jobs 0 → 1**; the job: `id=sfd6389c305 kind=reminder text=check my phone when=15:10 today due=1793574602.47` — the said time **15:10** and the word **phone** are both present |
| 4 cancel (HUD) | asked `cancel that`; HUD answered `Cancelled: the reminder for 15:10 today.` |
| 5 assert after cancel | `GET /api/schedule` **jobs = 0**, `removed=True` (job id `sfd6389c305` gone), `saidCancel=True`, `baseline 0, leftover 0` |
| 6 cleanup | not needed: `leftover = 0`. (`/api/pending` after the run: **0** cards; `/api/schedule` after: **0** jobs) |

**Verdict: PASS** — `created -> /api/schedule count=1 contains "15:10"; cancelled -> count=0`.

The reminder was created by the HUD's own chat turn (the model calling the schedule tool),
not by an API shortcut, so this proves the whole route the row exercises: chat box → model →
reminder job → `/api/schedule` → "cancel that" → no job.

**One change after the run, on the error path only.** `reminder-schedule.ps1`'s
`Invoke-JarvisHttp` was then tightened so a REFUSED request carries the server's own JSON
sentence (`$_.ErrorDetails.Message` first, the response stream second) instead of PowerShell's
"The remote server returned an error" text. The passing run never took that path — every
request in it answered 200 — and no reminder was created by the re-check, which was read-only:
`GET /api/no-such-route-…` → `status=404 {"error": "not found"}`; `POST /api/schedule/act` with
a bogus job id → `status=400 {"ok": false, "error": "need one job id"}`; and the happy path
still reads `ok=True jobs=0 todo=0`.

---

## 3. The two rows in `results.tsv`

| Row | Before | After (measured) |
| :--- | :--- | :--- |
| `B-reminder-create` | **not in this file**; in pass-16's `results.tsv` it was `BLOCKED-OWNER` (`write row needs -DoWrites`), and in phase B the HUD did say `Got it - reminder set for 05:37, in 30 minutes` — words only, never checked against `/api/schedule` | **PASS** — `created -> /api/schedule count=1 (id=sfd6389c305, text="check my phone", when="15:10 today")` |
| `B-reminder-cancel` | **not in this file**; in pass-16's `results.tsv` it was `PASS` on the words `Cancelled: the reminder for 05:37 today.` alone, with `/api/schedule` `[]` at the end of the run | **PASS** — `cancelled -> /api/schedule count=0, job sfd6389c305 gone; baseline 0, leftover 0` |

**Why they were added and not edited.** This results file
(`.dsh-scratch\FIELD-TEST-2026-11-01-GAPS\results.tsv`, 10 rows before) has never carried a
reminder row, and `gaps6.ps1` had no reminder step — the reminder rows lived in
`.dsh-scratch\FIELD-TEST-2026-11-01\pass16\` (`chat-hud-gate.ps1` + `results.tsv`), a
different lane folder that this workstream was told to treat as read-only. So the two rows
were **appended** here with the measured detail, and no other row in the file was touched
(12 lines now, every line 7 columns, same UTF-8 BOM as before). Pass-16's file was left
exactly as it was: its word-only reminder statuses there are now superseded by this
measurement, not rewritten by it.

---

## 4. How the backend was confirmed idle before the drive

- `GET /api/pending` → HTTP 200, `available=True`, **0 waiting cards** (checked by the script
  as a hard gate: a non-zero count means it refuses to create anything and says BLOCKED).
- The HUD itself: **0** `Deny` buttons on the window (no approval card on screen) and
  `busy=False` (not mid-answer), input box empty, log at 2 lines ("Systems online, sir.").
- `GET /api/schedule` → **0 jobs, 0 todo** — nothing of the owner's was in the way, so a
  count of 1 afterwards is unambiguously the reminder this run created.

A second, earlier attempt failed *before* touching the HUD or the backend (a bad path in my
own dot-source, `common12.ps1` not found under the repo root instead of under `.dsh-scratch`).
It created nothing: `logs\reminder-live-proof-20261101-150648.txt` holds only its own
four-line header and that one `BLOCKED` line.

---

## 5. Limits (what this does NOT prove)

1. **A full `gaps6.ps1` run has not happened.** The live proof called the same two functions
   the rows call (`Invoke-ReminderCreateProof` / `Invoke-ReminderCancelProof`) with the same
   asks, and the row text itself — read straight out of `gaps6.ps1` — was exercised by
   `selftest-reminder-rows.ps1` with fake measurements (5 scenarios: PASS/PASS, PARTIAL/FAIL,
   FAIL/BLOCKED-PC, BLOCKED-PC/BLOCKED-PC from an unreadable schedule, and both BLOCKED-PC
   from a blocked version gate — 11/11 checks, exit 0). What has never run is the whole
   harness in one go, which would also drive the phone/ADB rows and the release gates.
2. **UIA needs Medium integrity.** From a Low shell the HUD cannot be driven; `Ask-Hud`
   throws, and both rows will honestly land `BLOCKED-PC`, never PASS.
3. **The create is a model turn.** It needs the local model answering — the whole run (idle
   gate, both HUD turns and four `GET /api/schedule` reads) took **10.4 s** here, start
   `15:06:59.74` → log written `15:07:10.10`. A dead or slow model makes the row `FAIL` —
   no words, no job — not a false pass.
4. **The cancel leans on the HUD's "that"** referring to the reminder just created. It did
   (`Cancelled: the reminder for 15:10 today.`). If a future HUD answered without a job
   going away, the row is `FAIL` by design (the count would not drop).
5. **A card is not expected** for a one-off reminder (docs `JARVIS-API.md` §21.2: no card for
   anything that goes off once), and the measured run raised none (`/api/pending` stayed 0).
   If one ever appears, the row records `FAIL` rather than approving it — this workstream
   never approves or denies a card.
6. **The harness now creates one real reminder per field-test run** (cancelled by the next
   row). If the create row fails midway, that reminder is left to fire in 3 minutes; it is a
   notification only, and the live-proof script has a leftover-deletion step that the
   harness rows deliberately do not (the harness must not tidy away a failure it is asked to
   report).
7. **The owner's HUD log gained 4 lines** from the proof (`make a reminder…` / its answer /
   `cancel that` / its answer). That is the route; there is no way to drive the HUD's chat
   box without a chat turn.
