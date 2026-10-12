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

## Before reporting a NEGATIVE result, check the instrument

**A "nothing found" is the shape that most looks like a clean run, so it needs
the most proof. Before a negative result is reported, ask whether the step that
was supposed to happen actually happened.** The practical form of that rule:
**make the check say what it did, not only what it found.**

Three examples from 2026-10-11, all on real work, none of them hypothetical:

- **The plate.** `BrainScreen`'s source said a plate was drawn; the runtime
  dropped it from the list. Every check that read the source was green while the
  thing being checked for was never on screen. *A claim in the source is not
  evidence the thing is drawn.*
- **The zero-line probe.** `adb logcat -d -s JarvisRuntime:I` returned **0 lines
  in total** - not "no reconcile line". It read like "nothing wrong". *A probe
  that returns nothing is not evidence of absence; it is not evidence at all
  until the probe is shown to work.*
- **The reading that was nearly sent.** An armed watcher **did** catch the
  orphan condition at 16:05, then failed to find a Coming up row, fell back to
  tapping the Brain tab, and printed **"STILL POSTED"** - an instrument failure
  wearing a result's clothes. What stopped it being reported was one diagnostic
  line above the verdict: *"no Coming up row found"*. *A negative verdict is
  worth nothing if the step it depended on did not run.*

All three were caught by a line that **contradicted the verdict** rather than by
the verdict itself, which is why the check has to narrate its own steps. **The
paired rule for positive results:** a test that passes because it is looking at
nowhere or nothing proves nothing either - run the allowed case first and watch
it FIND what the forbidden case must not contain
(`docs/PIP-DESIGN.md` section 7.1 is that rule written out for one feature).

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
| DEF-008 | unclaimed | 2026-10-11 | open | `backend/jarvis_schedule.py`; `backend/schedule.patch` | **LOW SEVERITY, and NOT TO BE FIXED YET** - this one is the owner's product decision, not a repair. The two routes contradict each other about the same id. On the owner's live backend (139 patches) on 2026-10-11: `GET /api/schedule` -> **200**, `jobs: 1`, `todo: 0`, `went_off: 1`, `running: true`, ids `se80955f188` and `s1106891920`; then `POST /api/schedule/act` with `{"id": "s1106891920", "do": "delete"}` (usual `X-Jarvis-Token` / `X-Jarvis-Client: hud`) -> **404** `{"ok": false, "reason": "no_such_job", "error": "That is not on the list any more."}`. So the PC lists that job under `went_off` and then rejects it as not on the list: a fired entry cannot be cleared until it ages out of `went_off` an hour later, and the phone shows it that whole time. **Where the two sides differ**, both in `backend/jarvis_schedule.py` (`jarvis-backend/jarvis_schedule.py` is byte-identical, same lines): the **read** puts a fired job in `went_off` - `handle_get:2037` answers with `status()`, `status():1834` sets `"went_off": self.went_off(now)`, and `went_off()`'s query at `:1413-1417` accepts `state IN ('fired','active','paused')` within `WENT_OFF_SHOWN = 3600.0` (`:189` - one hour, documented at `docs/JARVIS-API.md:4740`); the **write** refuses it - the route at `backend/schedule.patch:82` calls `jarvis_schedule.handle_act(body)`, `handle_act:2158` calls `get().act(jid, do, seconds)`, and `act()`'s gate at `:1271-1274` accepts only `state IN ('active','paused','waiting')`, the same set the live list uses at `:1805-1806`, so anything `'fired'` comes back 404 `no_such_job`. The **same route, same id, accepts snooze**: `act()` routes `do == "snooze"` to `snooze()` at `:1267`, and `snooze()`'s own gate at `:1380` accepts `state IN ('fired','active','paused')` within `FIRED_KEEP` (24 hours); `GET /api/schedule?id=<id>` answers 200 for it too (`handle_get:2032-2036`, via `job():1797-1800`, which has no state filter). **The distinction that matters:** `went_off` may legitimately be history rather than a job, so "not on the list any more" is an honest sentence - the finding is the **inconsistency between the two routes**, not that either side is obviously wrong. `docs/JARVIS-API.md:5058-5061` documents the two windows as deliberately different ("The route reaches back a day ... while the Just went off list and the spoken phrase reach back one hour"), and snooze is the verb that implements the day-long reach-back. **This is not the cause of the alarm that rang for ever** (that one is DEF-006): that incident happened with the jobs **absent from all three lists** (`went_off` empty, more than an hour after they fired) - exactly the condition the phone's reconcile now covers. The notification side is already covered by **#280**: the reconcile needs the job absent from `jobs` + `todo` + `went_off` and does **not** need the delete to succeed, so nothing is unfixed for the owner's original complaint. If the owner wants a way to clear a fired entry, that is a **product decision** - a "Clear this" on the went-off row - not a bug fix. Do not repair it here or anywhere yet | `.dsh-scratch/docs-defect-008 @ 5f382aff` |
