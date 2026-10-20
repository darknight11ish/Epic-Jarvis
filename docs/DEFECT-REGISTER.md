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
| DEF-002 | desktop feature-test agent | 2026-10-11 | open | `jarvis-desktop/src-tauri/src/windows.rs`; `jarvis-backend/jarvis_hud.py` | CORRECTED 2026-10-11, and this row had not been carried across from `docs/defect-register.tsv`: the desktop half named the WRONG code. `main.js:5233` is Esc handling, not the gear (the gear is `main.js:5324-5335` and already has a 45 s watchdog); `windows.rs:516` is `focus_quickbar_input`, not `show_settings` (that is `:662` now, `show_settings_unlocked` `:670`, `settings.html` built `:684`); and the stated mechanism - "builds the window on the command thread" - was already addressed on 2026-09-27. The file's own 2026-10-11 finding names a different candidate, a `tauri-plugin-window-state` cache-lock deadlock, and the tree already carries a candidate fix for it: `af578c96` (2026-10-11, an ancestor of this commit) added `show_restored` (`windows.rs:637`, called at `:706/:804/:850`), which posts restore, show and focus as ONE main-thread closure, and its docstring says the hang was "reproduced on demand twice on 2026-10-11" (AppHangB1, 2026-10-10 22:27:08). **That reproduction was not re-run here**, so the row stays open on this evidence. THE HUD HALF IS FIXED: `/api/status` (`jarvis_hud.py:3181`) no longer makes 3-4 live upstream probes inline - one daemon thread polls every 15 s and the route reads `_STATUS_CACHE`, with `?force=1` for a probe on the caller's thread (PR #399, `a99ebe9a`). The 4598 ms against 9 ms for `/api/pending` (`jarvis_hud.py:3160`) is the measurement that made it a defect; the full correction history is in `docs/defect-register.tsv`, the machine file. **SLICE C (2026-10-20, origin/main 935c5a83, worktree `.dsh-scratch/wt-audit-c`):** the cache-mutex re-entry is REAL as written, read from the dependency's own source - `tauri-plugin-window-state` 2.5.0 `src/lib.rs:183-195` holds `RestoringWindowState` + `WindowStateCache` (`Arc<Mutex<HashMap<..>>>`, `lib.rs:124`) while `restore_state` calls `available_monitors()`/`set_position()`/`set_size()`/`maximize()`, which post to the main thread and block off it, and the plugin's `on_window_ready` hook then locks the same `WindowStateCache` (`lib.rs:458-467`). The deferral fix is already in this tree: `windows.rs` `show_restored` (`:682-702`) posts restore+show+focus as ONE main-thread closure and is used for Settings (`:751`), the Brain (`:849`) and Faces (`:895`); the HUD's restore (`lib.rs:749`) runs in the app-setup (main) thread. What is still missing is MEASUREMENT, not code: this pass did NOT reproduce the freeze (it needs an interactive desktop `AppHang`, and window tests were skipped with `JARVIS_SKIP_WINDOW_TESTS=1`) and did not re-measure the 4,598 ms `/api/status` figure. A stale comment, not a behaviour: `window_memory.rs:6-8` still says the plugin is 2.4.1/Rust 1.89 while `Cargo.toml:51` and `Cargo.lock:5086-5087` pin 2.5.0. **Verdict: the desktop half STAYS OPEN, no fix is claimed, and the row is not closed by this pass.** | wt-reg-2026-10-11 @ f8e96ab4 |
