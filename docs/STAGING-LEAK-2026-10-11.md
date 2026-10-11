# The `%TEMP%\jarvis-*` staging leak - diagnosis (2026-10-11)

Every backend suite run copies the whole backend into `%TEMP%` and, when the
run is killed rather than finished, leaves the copy there. 20,633 abandoned
folders reached 123.6 GB and took `C:` from 165 GB free to 34 GB. A 131 GB
hand cleanup has already run; the mechanism is unchanged, so it recurs.

## Every place a staging copy is made

| # | Where | What it creates | Cleaned up? |
|---|-------|-----------------|-------------|
| 1 | `backend/run_suites.py:291-295` `stage()` | `tempfile.mkdtemp(prefix="jarvis-staged-backend-")`, then `shutil.copy2` of every `_where.SHIPPED` module (~10 MB per run) | No. `shutil.rmtree(backend, ...)` at `:443` runs only on the normal path out of `main()`. |
| 2 | `backend/run_suites.py:391` (`state = Path(tempfile.mkdtemp(prefix="jarvis-suite-state-"))`) | the per-run `OPENJARVIS_CONFIG_DIR` + audit log the suites write into | No. `shutil.rmtree(state, ...)` at `:444`, same normal path only. Measured at 64 MB in one abandoned folder. |
| 3 | `backend/test_selftest_preflight.py:91-93` `backend_folder()` | `jarvis-preflight-backend-` + `copy2` of every `SHIPPED` module | Only in `main()` at `:1084-1085` - not on exception, not on kill. |

Items 1 and 2 are the runner's own folders. They are not the whole leak: the
bulk of the twenty thousand was one folder per suite per run, made by the
suites themselves (see "The fix" below - the same fix covers both). `main()`
reads:

```python
    real = os.environ.get("JARVIS_BACKEND")
    backend = Path(real).resolve() if real else stage()      # :369
    ...
    state = Path(tempfile.mkdtemp(prefix="jarvis-suite-state-"))   # :391
    ...
    if not real:
        shutil.rmtree(backend, ignore_errors=True)           # :443
    shutil.rmtree(state, ignore_errors=True)                 # :444
```

There is no `try`/`finally` anywhere in `main()`. A Ctrl-C, a `timeout 900`
that kills a wedged suite, a CI cancel, or a `SystemExit` raised before line
443 all skip both `rmtree` calls. On this machine two live sweeps (PIDs 50324
and 41036, started 00:24 and 00:53) were each still holding a 10 MB
`jarvis-staged-backend-*` and a `jarvis-suite-state-*` - the folders look
abandoned but are not, which is why the reaper must check ownership.

## Places that already clean up (checked, no change needed)

* `backend/run_suites.py:4776` `--state-env` mode - the caller
  (`scripts/apply-patches.ps1:4777`) removes `jarvis-suite-state-$TempName` at
  `:4822`.
* `scripts/apply-patches.ps1:2092` `jarvis-patches-lf-` - removed at `:4319`.
* `scripts/apply-patches.ps1:3152` `jarvis-rehearsal-` - removed at `:3827`
  and `:4048` (finally).
* `scripts/apply-patches.ps1:3764` `jarvis-result-check-` - removed with the
  rehearsal.
* `scripts/apply-patches.ps1:3964` `jarvis-undo-check-` - removed at `:3985`.

## The fix

Table items 1 and 2 above are the runner's own folders, but they were not the
bulk of the twenty thousand. **Nearly every suite in `backend/` makes its own
`jarvis-<suite>-<random>` at import time with `tempfile.mkdtemp` and never
removes it** (296 files do it today - `jarvis-enrol-`, `jarvis-big-model-`,
`jarvis-referee-`, `jarvis-picture-card-`, ...). That is one folder per suite
per run, and it is why the count grew by roughly one per suite while this was
being investigated.

1. **One folder per run.** `main()` makes a single
   `%TEMP%\jarvis-sweep-<random>` root and everything goes inside it: the
   staged backend (`root/backend`), the config folder and audit log
   (`root/state`), and the suites' own scratch. It is claimed with an
   `_owner.json` marker and an exclusive lock.
2. **The suites' scratch goes there too.** The children are given `TMPDIR`,
   `TEMP` and `TMP` pointing at `root/tmp`; `tempfile.gettempdir()` reads
   exactly those, so every `mkdtemp` a suite makes lands inside the root. This
   is what turns ~296 folders per run into zero. The folder is created up
   front because Python falls back to the *working directory* for a temp
   directory it cannot write to, which would put a suite's scratch in the
   checkout.
3. **`main()` removes the root in a `finally`**, so a normal end, a failed
   suite and an exception all clean up the same way. `remove_tree()` prints a
   plain `NOTE` if anything could not be removed; `ignore_errors=True` with no
   word is how the 123.6 GB went unnoticed.
4. **A reaper for what a kill leaves.** A killed process runs no `finally` at
   all, so its root stays - one folder, not three hundred. The start of every
   run reaps a candidate only when *both* hold: it is older than `REAP_AFTER`
   (1 h) **and** the lock on its `_owner.json` can be taken, which means the
   run that made it has ended. A folder whose lock is still held belongs to a
   live sweep and is **never** touched - two sweeps were running while this
   was written. The lock, not the pid, is the proof: a pid can be reused, and
   `os.kill(pid, 0)` on Windows would *terminate* the process rather than
   test it.
5. **Candidates are a shape, not a list.** `REAPABLE` matches
   `jarvis-<something>-<random>` where the tail is what `mkdtemp` appends (6+
   characters, no dot) - so both families from the incident are covered
   (`jarvis-staged-backend-<rand>`, `jarvis-suite-state-<rand>`) and a suite
   added tomorrow is covered without editing the rule, while a name a person
   chose (`jarvis-tool`, `jarvis-framework.toml`) never is.
6. **A folder with no marker** - one an older run left, where there is nothing
   to ask about its owner - has to be `REAP_AFTER_UNMARKED` (24 h) old. A suite
   is killed at 900 s, so nothing can still be writing into a folder that old.

`stage()` still works with no argument, for `backend/test_suite_state.py`,
which stages two backends of its own and removes each one itself. No suite
semantics change. No new shipped module (and `run_suites.py` is not in
`jarvis-backend/`, so no twin to keep byte-identical).

## Measured, 2026-10-11

`backend/test_suites_staging.py` - 31 checks, `31 passed, 0 skipped, 0 failed`,
exit 0. It runs one small suite (`test_front.py`, 0.2 s) as a real nested
sweep with its temp folder redirected into the test's own scratch folder.

* **With the cleanup removed from `main()`'s `finally`:** `28 passed, 0
  skipped, 3 failed`, exit 1, and the leftover was named:
  `FAIL the run left NO jarvis-* directory behind  ['jarvis-sweep-68tx079w']`.
* **With the cleanup leaving an EMPTY directory** (the shape the twenty
  thousand really were): also `FAIL ... ['jarvis-sweep-y7s_m_ar']`, and a
  direct run showed the leftover as `jarvis-sweep-npvs0wqb DIRECTORY, 0
  file(s) inside -> empty=True`. A check that counted bytes would have called
  that clean, which is why this test lists names.
* **Restored:** `31 passed, 0 skipped, 0 failed`, exit 0.
* **The acceptance measurement**, one real run of
  `py -3 backend/run_suites.py test_front.py` from `backend/` with
  `JARVIS_BACKEND` cleared and the machine's real `%TEMP%`:
  `jarvis-*` directories **before 550, after 550**, and
  `jarvis-sweep-*` left behind **0**. Run again as
  `py -3 run_suites.py test_suites_staging.py` (the way CI runs it): also
  **equal**, 0 left.
* **A crafted orphan vs a live folder, in the real `%TEMP%`:** an
  `_owner.json` naming a dead pid with a 2 h-old timestamp was reaped by the
  next run (`reaped 1 staging folder(s) an earlier run left behind:
  jarvis-orphan-proof-dead7777`, 506 -> 505 directories, **0 new names**),
  while a 2 h-old folder held by a live holder process was left alone; once
  that process was killed, the next run reaped it.
* Guards re-run green afterwards: `tools/check_stale_twins.py`,
  `tools/check_same_tick_paths.py`, `tools/check_vacuous_checks.py`,
  `backend/test_suite_state.py` (18), `backend/test_suite_report.py` (43),
  `backend/test_shipped_modules.py` (613).

Two live sweeps were running the old code throughout, so the raw `%TEMP%`
count was also rising independently of these runs: the numbers above are the
name-set delta around one run, not a claim that the machine's total fell.

