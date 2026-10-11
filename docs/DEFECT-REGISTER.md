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
