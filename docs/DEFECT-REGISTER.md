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
| DEF-002 | desktop feature-test agent | 2026-10-11 | open | `jarvis-desktop/src-tauri/src/windows.rs`; `jarvis-backend/jarvis_hud.py` | the Settings gear's path (`main.js:5233` -> `plain_errors.rs:312` -> `windows.rs:516`) builds the window on the command thread, and `/api/status` (`jarvis_hud.py:3181`) makes 3-4 live upstream probes while `/api/pending` (`jarvis_hud.py:3160`) is a DB read: measured 4598 ms against 9 ms at app 0.2.129 | wt-reg-2026-10-11 @ f8e96ab4 |
| DEF-009 | unclaimed | 2026-10-11 | open | `tools/gen_phone_voice_cases.py`; `backend/test_voice_contract.py` | CORRECTED 2026-10-11 FROM PR #319 (b2d22f81, branch def009-check) - THE CORRECTION IS THEIRS, read from the source and run, and the first version of this row described the defect BACKWARDS in three ways. WHAT IT ACTUALLY IS: a real defect in the TOOL, not in the app. tools/gen_phone_voice_cases.py renders the phone's shared fixture from jarvis_voice_flow's module-level list of measured turns, so inside ONE interpreter main(['--check']) returns 0 the first time and 1 the second, on ONE UNCHANGED TREE. Proven with a causal control: calling the module's own _reset_for_tests() makes the next render BYTE-IDENTICAL to the fixture (sha 811a76b5d614653e), so the leftover rows are the cause - not a cache, not a clock. CORRECTION 1, THE DIRECTION: this row said 'a test that can pass because of state left by an earlier run'. Leftover rows CANNOT make the check pass - green needs the rows EMPTY at the start, which is the correct condition - and leftover state makes a CORRECT TREE LOOK STALE: a SPURIOUS RED, 0 then 1. What is order-dependent is that it is green only because it is the FIRST RENDER in that process, for a reason the check does not guarantee; a reader trusting the old wording would hunt for a false green that cannot happen. CORRECTION 2, THE FIX: this row said a fix is 'not one line' and that the committed fixture may need regenerating. The fix IS one line (S._flow('_reset_for_tests') at the top of render()) and THE FIXTURE DOES NOT CHANGE - byte for byte, same sha. What made it look expensive was the test's own workaround comment at backend/test_voice_contract.py:476-484 claiming the producer 'is not repeatable inside one interpreter'; that comment is now corrected rather than relied on. CORRECTION 3, A MEASUREMENT: this row said render #1 has 'turns 0 ... for every step'. #1 IS the fixture and carries 408 turns summed over 26 cases (some cases zero, NOT all of them), which is why the honest answer to 'same run or a later run?' is BOTH, not 'later run only'. THE FIX, theirs (#319, open while this row is written): a check added to t_the_desktop_fixture_is_fresh renders TWICE in one process and demands the same bytes, and IT BITES - with the line removed, same bytes twice -> False, 1,054,760 then 1,218,390; with it, backend/test_voice_contract.py went 741 passed / 0 failed -> 742 passed / 0 failed, and run_suites.py discovers suites by shape (:183), so the runner and CI execute it. CLOSE THIS ROW WHEN #319 MERGES, with the checker as the authority on the number and the counts. Nothing here needs the owner's PC. | `.dsh-scratch/voice-triage @ 82c27ff7` |
| DEF-012 | unclaimed |  | open | `jarvis-backend/jarvis_gate.py`; `backend/gate-touches.patch`; `backend/jarvis_mcp.py`; `jarvis-backend/jarvis_mcp.py` | THE DEF-003 CUT SURVIVES IN TWO CALLERS THAT ARE NOT WIRED UP - the same defect shape, in files DEF-003 did not own, so it is recorded rather than claimed as fixed. (1) jarvis_gate.gate_tool, `jarvis-backend/jarvis_gate.py:1699-1712`: it builds `detail = {"tool": name, "args": (params if isinstance(params, str) else json.dumps(params, default=str))[:1500]}` and then builds the prompt from that same cut string, `f"tool {name} {detail['args']}"`. `_target_blobs` reads BOTH sides of that pair - `jarvis-backend/jarvis_gate.py:1013-1020` serialises `detail` minus `_PROSE_KEYS` as one blob, and the `_TOOL_CALL_PROMPTS` loop at `:1047-1051` then reads the prompt's raw argument text - so a protected name past character 1500 in those arguments is unscanned on both paths and the action comes back as an ordinary card a person could approve, exactly as in DEF-003. (2) jarvis_mcp.call, `backend/jarvis_mcp.py:1643` and its byte-identical twin `jarvis-backend/jarvis_mcp.py` (same line): the gate is handed `f"tool {model_name} {plan.args_json[:1500]}"` with `detail {"text": self.describe(plan)}`. `text` is prose and is dropped by `_PROSE_KEYS`, so the cut prompt is the ONLY carrier of those arguments and a protected name past 1500 is invisible there too. REACHABILITY, CHECKED 2026-10-12 AND STATED PLAINLY, NEITHER OVERSTATED NOR SOFTENED: both entry points are LATENT - unreachable today and not exploited. `ToolExecutor` exists in this checkout only as a word in `gate_tool`'s own docstring (`jarvis-backend/jarvis_gate.py:1700`) and in `backend/README.md:2517`, which itself calls `gate_tool` the hook for "a `ToolExecutor` or a tool registry" - there is no class, no definition and no production call site, and the only caller of `gate_tool` anywhere is `backend/test_gate_outcome.py:350`, with short arguments. `jarvis_mcp.call` has no caller in this repository at all; its own docstring says it is "for call sites other than jarvis_agent". Both become live the moment either entry point is actually wired, which is the only reason they are worth a row. WHY NOT FIXED WITH DEF-003: the gate one needs patch-stack surgery - `jarvis-backend/jarvis_gate.py` is itself a protected file, and the code and comments around it are carried by `backend/gate-touches.patch`, so a change must land in that patch AND in the published copy AND in `backend/patch-history` (`tools/build_patch_history.py` records the patch's earlier text for the owner's install), with the pinned checks at `backend/test_gate_touches.py:528-628` re-run; the mcp one has a published twin as well. Neither file was in DEF-003's write scope (`backend/jarvis_agent.py`, its twin, `backend/test_gate_touches.py`). | wt-def003-gate-2026-10-12 @ 8ddfc503 |
