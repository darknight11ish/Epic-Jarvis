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
- it also carries the HUD fixes that live in the published base but in **no**
  `.patch` as literal deltas (DEF-002's status cache, its start call and the
  cached `/api/status` route, and the reasoning fallback); a REPLACE delta's old
  block must appear in the live file exactly once, or the run refuses;
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

**The backup journal names the tree it deployed (2026-10-27).** An `--apply`
writes `source_ref`, `source_commit_sha` and `source_tree_sha` into the backup
folder's `_journal.json`, the last being `git rev-parse <ref>^{tree}`. A tree
hash is **content-addressed**: it names the files, not the history, so a rebase,
a squash or a merge that rewrites the commit SHA leaves it unchanged. That is
what makes "the files on the live PC are the files the reviewer approved"
checkable later with one command, `git rev-parse <candidate>^{tree}` against
`source_tree_sha`, instead of trusting a note. The keys are additive - a journal
written by the older tool has none of them and still loads and rolls back - and a
ref git cannot peel is **refused with nothing written** rather than journaled
without the proof.

**Verified on 2026-10-20 (Area 12, no `--apply`).** Dry run against the live
backend folder: exit 0, **0 refusals**, `$SHIPPED` 218 files all unchanged, 188
of 189 HUD patch/file deltas already present (the one to insert is DEF-002's
route, below), 9 ready plug-ins present and 0 to add, planned changes 153 (1 HUD
route insert + 152 stale `.pyc` files; "DRY RUN, nothing written"). A second dry
run half an hour later planned 168 for the same two reasons (the running server
keeps writing `.pyc`, so only the 1 HUD route insert is stable). Its own
suite, `backend/test_reconcile_live_backend.py`, passes (334 checks as of
2026-10-27, all on temporary folders). As an extra read-only check (Area 12), its `run_probes()`
was called directly against `http://127.0.0.1:4719` - no `--apply`, nothing
written - and all four probes PASS (setup 200, media-index 200, app-control 409
while off, voice 200).

**DEF-002's missing route delta (2026-10-20).** The two #668 deltas inserted the
status cache and its start call, but not the route: the live `/api/status` still
probed upstream inline (measured 3094/3117 ms plain and 3084/3097 ms with
`?force=1`, which the old route ignored; the same ten keys either way).
`tools/hud-deltas/` now carries the base's cached route as a literal REPLACE:
`status-route-old.txt` is the live block (starts at
`        if path == "/api/status":`, ends at the `            })` that closes
`_send(200, {...})`, and appears in the live HUD exactly once) and
`status-route-new.txt` is the same block from `jarvis-backend/jarvis_hud.py`.
The dry run above stages exactly that one block (40 lines) and refuses instead
of writing if the old block is absent or present twice. After `--apply` and a
restart, a plain `GET /api/status` answers from the cache (no upstream probe) and
`?force=1` deliberately re-probes on the caller's thread (about 3.1 s on this PC
while the dead :8000/:4000 endpoints time out), with the same ten keys.

**A RETIRED blocked record: `traces.db` retention (F10 / Q2, retired
2026-10-23).** Gemini's Q2 ruling asked for the trace store's retention to be a
small live-HUD/reconcile delta, not a fake backend module. The live HUD was read
read-only and has **no `traces.db` writer, schema or insert/startup anchor**:
`jarvis_hud.py` has zero `traces.db` matches, its `sqlite3` use is the read-only
memory readers, the live folder has no writer, and `~/.openjarvis` has no
`traces.db` today. A standalone prune in the HUD would delete a database this
program does not own, so the tool recorded the decision as
**`BLOCKED_DELTAS["traces-retention"]`** (PR #669, with that evidence) and every
run printed **BLOCKED LIVE DELTAS** - it was never staged.

**That record is retired, not applied (RA-5, 2026-10-23).** Four hours after
#669, **#673** shipped the cap the safe way, in SHIPPED modules rather than in
the HUD: `jarvis_sqlite.trim_table` / `idle_maintenance` caps any `traces.db`'s
`traces` table at the newest 10,000 rows, and
`jarvis_initiative.sqlite_maintenance` calls it from the 30-minute heartbeat.
Deploy step 1 (the SHIPPED sync) carries both files, and on this PC (measured
2026-10-23) the live `jarvis_sqlite.py` and `jarvis_initiative.py` are
byte-identical to `origin/main:backend/...`, while the live `jarvis_hud.py`
still has zero `traces.db` matches and no `traces.db` exists in the live folder
or `~/.openjarvis`. The HUD never owned the store, so there is no anchor a
live-HUD delta could attach to - "re-anchoring" it would mean inventing a writer
the program does not have. `BLOCKED_DELTAS` is now empty, the dry run reports
**0 blocked deltas**, and the retention remains tested where it ships
(`backend/test_sqlite_perf.py`). This is not a claim that a writer exists: the
cap acts only if a store from an older build or a backup restore appears.

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
