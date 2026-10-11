# Defect register

Where the agents on this repo write down a defect **before** they touch it, so
two of them do not repair the same thing twice and nobody has to guess who is
on what.

Two files, and they must agree:

- `docs/defect-register.tsv` - the machine file. The checker reads this one.
- `docs/DEFECT-REGISTER.md` - this file. The open defects are in the table at
  the bottom.

## How to claim a defect (3 steps)

1. **Add one row to `docs/defect-register.tsv`**: `status` = `open`, your own
   name in `owner`, the `files` you are about to touch, the `evidence` you
   already have, and the `checkout` you are working in.
2. **Add the same `id` as one row of the table at the bottom of this file.**
   The two must list exactly the same open ids.
3. **Run the checker** from the repo root:

   ```
   py -3 tools/check_defect_register.py
   ```

   It must print `defect register OK: ...` and exit 0. It exits 1, naming the
   row, when a row is malformed, when two open rows claim the same file, when a
   row names a file that is not in the checkout, or when this file and the
   `.tsv` disagree about which defects are open.

When the defect is fixed: set `status` to `closed` in the `.tsv` (leave the
row - the history is the point) and delete its row from the table below.

## The exact TSV row format

Seven fields, separated by **TAB** characters (not spaces), one defect per
line, after this header row:

```
id	owner	claimed_at	status	files	evidence	checkout
```

- `id` - `DEF-` and a number, unique.
- `owner` - who is on it, or `unclaimed`.
- `claimed_at` - `YYYY-MM-DD`, or empty while `owner` is `unclaimed`.
- `status` - `open` or `closed` only.
- `files` - repo-relative paths separated by `;`. One path may sit in only one
  open row.
- `evidence` - the log line, the suite numbers or the test name that proves it.
  One line: no tabs, no line breaks.
- `checkout` - the worktree and revision the evidence came from.

An example row (every gap between two words below is one TAB):

```
DEF-003	some-agent	2026-10-11	open	tools/example.py	tools/example.py:41 returns before the check; test_example.py fails	x/some-branch @ 1a2b3c4
```

## Why this exists (history, not an open defect)

On the night of 2026-10-11 the same real bug was repaired several times over,
by agents that had no shared view of what the others were doing:

- **three** duplicate repairs of one test module,
- **three** for one patch anchor,
- **five** for one branch cleanup,
- **six** for one test file.

Every one of those was paid for twice. That is the whole reason this register
exists: one line in one file, before the work starts.

## Open defects

| id | owner | claimed_at | status | files | evidence | checkout |
| --- | --- | --- | --- | --- | --- | --- |
| DEF-003 | unclaimed | 2026-10-11 | open | `backend/jarvis_agent.py`; `backend/test_gate_touches.py` | a protected name **beyond character 1500** of the tool arguments is still never scanned: `jarvis_agent.py:1199` (`_gate_prompt`) and `:1384` (the plan-step line) cut the JSON at 1500 **before** the gate sees it, so a long argument can still hide a write to `jarvis_gate.py`. PR #260 closed only the half where the cut JSON did not parse | wt-verify2-2026-10-11 @ 621aad36 |
| DEF-004 | unclaimed | 2026-10-11 | open | `scripts/move-models-to-d.ps1` | section 8h called `Start-ScheduledTask` on `Jarvis Ollama - Everyday model` / `... Coding model` - names that do not exist (the real ones end ` (RTX 2060)` / ` (RTX 2080 Super)`) - with `-ErrorAction SilentlyContinue`, then exited 0. Both tasks show `LastTaskResult 0xC000013A` and the lanes stayed down for an hour. Fixed by PR #255 | wt-lanes-2026-10-11 @ bda48094 |
| DEF-002 | desktop feature-test agent | 2026-10-11 | open | `jarvis-desktop/src-tauri/src/windows.rs`; `jarvis-backend/jarvis_hud.py` | the Settings gear's path (`main.js:5233` -> `plain_errors.rs:312` -> `windows.rs:516`) builds the window on the command thread, and `/api/status` (`jarvis_hud.py:3181`) makes 3-4 live upstream probes while `/api/pending` (`jarvis_hud.py:3160`) is a DB read: measured 4598 ms against 9 ms at app 0.2.129 | wt-reg-2026-10-11 @ f8e96ab4 |
| DEF-005 | fix-265 | 2026-10-11 | open | `backend/test_power_switch.py` | `backend-windows` on PR #265 (job 114438288189) printed `FAIL  waking from standby loads the chat model at once` and then `KeyError: 'warm_up'` in `t_waking_loads_the_chat_model_again` (59 passed, 1 skipped, 2 failed). `set_mode` joins its work thread for `wait_s` only (1.5 s) and then answers 202 "Waiting for your approval", a body with no `warm_up` in it, so an in-place warm-up slower than 1.5 s is read as if it were the answer. Reproduced exactly on `.dsh-scratch/docs-drift`: fails at 2.0 s of warm-up, passes at 1.2 s - the boundary **is** the 1.5 s join. `main` carries the same racy test, so merging `main` alone does not fix it. Fixed by #265 (`45e35ec9`): the test passes `wait_s=30` and asserts `code == 200` | `.dsh-scratch/docs-drift @ 45e35ec9` |
| DEF-006 | frontend-triage | 2026-10-11 | open | `jarvis-client/app/src/main/java/com/jarvis/client/service/ScheduleNotifier.kt`; `jarvis-client/app/src/main/java/com/jarvis/client/net/Schedule.kt`; `jarvis-client/app/src/main/java/com/jarvis/client/JarvisRuntime.kt` | a job **DELETED on the PC** while its "went off" notification is still posted leaves the notification up for ever: nothing cancels it, because the PC's `changed` event is the only cancellation this app has and a job that no longer exists sends none. Measured on the owner's CPH2419 (`adb f0a5b32b`) on 2026-10-11 - `POST /api/schedule/act {id,do:delete}` for `s7623a9a982` and `sf50b6d4930` both answered `{ok:false,reason:no_such_job}`, `GET /api/schedule` showed `jobs:[se80955f188]` and `went_off:[]`, and both tags were still posted (`tag=s7623a9a982 channel=jarvis_alarm flags=ONGOING_EVENT\|INSISTENT\|AUTO_CANCEL\|LOCAL_ONLY category=alarm actions=2` and `tag=sf50b6d4930 channel=jarvis_schedule actions=1`) - so the alarm kept ringing with no event left to cancel it. Fixed on `fix/phone-timer-offers-stop`: a schedule notification whose job is in none of `GET /api/schedule`'s `jobs`/`todo`/`went_off` is taken away, and only after a read that SUCCEEDED | `fix/phone-timer-offers-stop @ 719963ae` |
