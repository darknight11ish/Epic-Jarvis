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

Items 1 and 2 are the leak. `main()` reads:

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

1. `main()` cleans up in a `finally`, so normal end and exception both remove
   the staged backend and the state folder.
2. A cheap reaper at the **start** of a run removes orphaned staging folders
   under `%TEMP%` that are (a) older than a safe age and (b) not owned by a
   live process. Each staging folder gets a `_owner.json` marker (pid, process
   start time, suite/kind, created-at) written when it is made. A folder whose
   owner pid is alive **and** whose recorded process start time matches is left
   alone.
3. A test that fails if a completed run leaves its folder behind.

No suite semantics change. No new shipped module.
