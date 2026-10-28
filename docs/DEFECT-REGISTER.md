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
DEF-006	some-agent	2026-10-11	open	tools/example.py	tools/example.py:41 returns before the check; test_example.py fails	x/some-branch @ 1a2b3c4
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
| DEF-017 | learning-lane | 2026-10-28 | open | `backend/jarvis_auto_learn.py`; `jarvis-backend/jarvis_auto_learn.py`; `backend/test_learning_after_pass.py`; `jarvis-backend/jarvis_extract.py` | REAL DEFECT, FOUND 2026-10-27/28 IN THE LIVE LEARNING LANE AND REPRODUCED HERE. `_init_notes()` migrated `auto_learn_notes` with three unguarded `ALTER TABLE` statements, and its `CREATE TABLE IF NOT EXISTS` omitted `topic_ask` - so a FIRST-RUN database ran an ALTER on its very first card. Two writers reach `_init_notes` on the same table: `after_pass` -> `_note_card` (`jarvis_auto_learn.py:1799` at origin/main `44fa39a58`) and every `/api/memory/pending` read -> `card_notes` (`:1820`). A second writer that adds the column between the first one's `PRAGMA table_info` (`:1778`) and its `ALTER` (`:1780`) makes the loser raise `sqlite3.OperationalError: duplicate column name: sensitive`. REPRODUCED deterministically, not reasoned: `_init_notes:1780` <- `_note_card:1799` <- `after_pass:2067`, the pass returns `{'saved': [], 'cards': {}, 'error': 'OperationalError'}`, `note_failure` (`:2104`) records `last_error` `after_pass: OperationalError`, and `passes` never moves - exactly the live counter shape. THE LIVE COUNTERS ARE STALE AND SAID SO: `~/.openjarvis/learning-stats.json` was last written 2026-10-10 20:03 local (eight `learning.failed` events inside six seconds; `last_error_at` 1791687798.5), the eight audit lines carry only `{where, kind}`, and today's `memory.db` has NO `auto_learn_notes` table - the store was re-seeded 2026-10-15, after those events. THE FIX IN THIS PR: a guarded `_add_note_column()` that swallows ONLY `sqlite3.OperationalError` whose message names a duplicate column (everything else re-raises, and the suite pins that), plus `topic_ask` in the CREATE so a new install runs no ALTER at all. REGRESSION TEST: `backend/test_learning_after_pass.py`, 11 checks - 6 passed / 5 failed against origin/main `44fa39a58`, 11 passed / 0 failed with the fix, and one check is the guard that "database is locked" and "no such table" still raise. SECOND HALF OF THE SAME ROW, the swallowed exception: `jarvis_extract._local_llm`'s `except Exception: return None` threw away the HTTP status and the body, so the learner could only print "reached no model at http://127.0.0.1:11436 ... Is it pulled?" while Ollama listed AND loaded `qwen3.5:9b`. It now records a CLOSED-WORLD reason - exception class, HTTP status, wall duration and Ollama's own `done_reason`, never a prompt word or an answer word - keeps returning None, and hands the reason to `jarvis_auto_learn.note_model_failure`, which `/api/memory/learning` already reads back, so no HUD change is needed. ONE AUTHORIZED BOUNDED LIVE DIAGNOSTIC (2026-10-27 23:46 local, no user data, one POST, no retry): `POST /api/generate` to `127.0.0.1:11436` with the one-word prompt "ok", `num_predict` 1, returned HTTP 200 in 1.969 s with an EMPTY `response` and `done_reason` "length" on a lane whose `/api/ps` reports `qwen3.5:9b` loaded (9.86 GB VRAM) - so "Is it pulled?" is measurably the wrong question, and an empty answer (not only an exception) is a reason worth recording. Raw evidence: `.dsh-scratch/RED-PR-LANE-2026-10-28/learning/POST-DIAGNOSTIC.txt`. NOT DEPLOYED: the owner's PC still runs the old modules until `scripts/apply-patches.ps1` is re-run, and the row stays open until it is. | fix/learning-after-pass-notes-migration @ `1452f4525` plus this PR's later commits (worktree `.dsh-scratch/RED-PR-LANE-2026-10-28/wt-learning`) |
