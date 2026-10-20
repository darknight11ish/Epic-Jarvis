# Deploying the backend, and the two checks that prove it

Two tools do the deploy-side work, and both are read-only until told
otherwise. This page says what each one is for, how it is run, and what was
measured on this PC on 2026-10-20 (the deploy-tooling area of the audit).

Neither tool is part of the backend the PC runs; they live in this repository's
`tools/` folder and are run from a checkout. Neither one installs an app, edits
a patch, or restarts Jarvis.

## 1. `tools/check_field_test_binaries.py` - Step 0 of every field test

A field-test row is only evidence for the build it ran on. This tool records
what is actually installed - the installed desktop and phone versions and the
commits they were built from, the commit of the live backend - and answers one
question in three ways:

- **PASS** (exit 0): the feature commit is an ancestor of every installed build
  asked about, so the installed binaries really contain the feature;
- **WAITING_FOR_RELEASE_BUILD** (exit 3): a newer build is building, or was
  published but not installed - a row in this state is not a failure;
- **REFUSED** (exit 2): the question cannot be answered honestly (bad version or
  commit, commit not in the checkout, backend unreachable). Nothing is guessed.

It never writes or installs anything; with `--github` it reads the rolling
`desktop-latest` / `client-latest` release metadata, and with `--backend-url` it
does one GET of `/api/version`.

**The HUD header (fixed 2026-10-20, PR #646).** The backend probe sends
`X-Jarvis-Client: hud`. The HUD's origin rule accepts an Origin-less request only
from the HUD's own client name; the gate used to send `field-test-gate`, so
`/api/version` answered 403 and the build-SHA gate could never record the live
backend. It now records it.

**Token.** When the live backend has a HUD token set, the probe needs it. Read
it from the live folder with `py -3 jarvis_token_store.py show` (that command
prints only the token, on stdout, so it can be piped or held in a shell
variable) and pass it with `--backend-token`. Treat the value as a secret: never
type it into a saved command file, a report, a commit, or a log, and do not
paste it into an agent transcript.

**Verified on 2026-10-20 (Area 12, read-only).** Run against the live backend
`http://127.0.0.1:4719` (token read from the live folder, kept in memory), with
`--feature-sha 4c8d81c8`, installed desktop `0.2.236` built from `4c8d81c8`,
installed APK `0.2.2127` built from `dee94c8f`, and live backend `935c5a83`:

```
live backend: http://127.0.0.1:4719 reachable - server=jarvis-hud api=1
- backend: PASS - 4c8d81c8 is in the live backend (merge-base exits 0)
- desktop: PASS - 4c8d81c8 is in the installed build (merge-base exits 0)
- phone: PASS - 4c8d81c8 is in the installed build (merge-base exits 0)
VERDICT: PASS
```

Exit code 0. Before #646 the same probe ended with `403` and the row was
recorded BLOCKED. Its own suite, `backend/test_field_test_binaries.py`, passes
(34 checks, no network and no real app; it drives the tool's `main()` with a
fake repository and a fake HTTP function).

## 2. `tools/reconcile_live_backend.py` - the backend deploy itself

**Dry-run by default; `--apply` is the only thing that writes.** It is what
replaced the two hand-written scripts used for the 2026-10-20 deploy:

- it syncs every module in `scripts/apply-patches.ps1`'s `$SHIPPED` list into the
  live folder byte-for-byte (no line-ending rewriting), backing up every file it
  overwrites;
- for the five patched base files it adds only the HUD deltas a patch really
  needs, and **refuses** when an anchor is missing or a patch has no rule - it
  never guesses;
- it rehearses every staged file with `py_compile` before anything is swapped,
  clears stale `__pycache__/*.pyc`, and adds ready plug-ins that the running HUD
  does not already wire;
- with `--apply` it then probes the live routes (`/api/setup`,
  `/api/media-index`, `/api/app-control/run` while app control is off, and
  `/api/voice/status`), reading the token itself from the live folder and never
  printing or logging it. A dry run does not run the probes - it says so.

```
py -3 tools/reconcile_live_backend.py --backend-path "<live backend folder>"           # dry run
py -3 tools/reconcile_live_backend.py --backend-path "<live backend folder>" --apply   # after reviewing
```

Exit codes: 0 success, 1 a plug-in or route probe failed, 2 refused before
writing.

**Verified on 2026-10-20 (Area 12, no `--apply`).** Dry run against the live
backend folder: exit 0, **0 refusals**, `$SHIPPED` 217 files all unchanged, all
185 HUD patch/file deltas already present, planned changes 153 (153 stale
`.pyc` files; "DRY RUN, nothing written"), 7 ready plug-ins to add. Its own suite,
`backend/test_reconcile_live_backend.py`, passes (105 checks, all on temporary
folders). As an extra read-only check, its `run_probes()` was called directly
against `http://127.0.0.1:4719` - no `--apply`, nothing written - and all four
probes PASS (setup 200, media-index 200, app-control 409 while off, voice 200).

## 3. The old one-off scripts are superseded

The 2026-10-20 deploy used two throwaway scripts kept in scratch:

- `.dsh-scratch/reconcile-hud-2026-10-20.py` (insert the HUD deltas);
- `.dsh-scratch/reconcile-setup-2026-10-20.py` (insert the setup install block).

`tools/reconcile_live_backend.py`'s own docstring names both as the work it
replaces, and its dry run above proves the live HUD already has those deltas.
**Do not run or copy them**; use the tool. They are untracked scratch files, so
nothing in the repository depends on them and no tracked file was deleted.

## 4. Limits worth knowing

- The reconcile tool writes only that repository's `$SHIPPED` Python modules and
  the HUD deltas; it does not handle the non-Python beside-files
  (`requirements.lock`, `quiz_grader_cases.json`, the plugin catalogue) that
  `apply-patches.ps1` carries. Those stay that script's job.
- It never restarts Jarvis. After `--apply`, restart and read the start-up
  banner; the probes only prove the routes answer while the new code is running.
- `jarvis-backend/` is never copied over the live folder - it is a snapshot of
  the published base, not the runtime tree.
