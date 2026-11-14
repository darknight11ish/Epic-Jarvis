# Wave 6 field test — addendum, 2026-11-06 14:05 PT (repo-map row)

The 09:21 PT field run (`results.json`, 11 checks: 7 PASS, 1 NOT-MEASURED, 2
BLOCKED, 1 FAIL) had one real failure:

- `repo_map` → `GET /api/projects/<id>/map` answered **HTTP 400**
  `{"ok": false, "available": true, "error": "That project has no folder..."}`.
  The only project on the PC ("Field Test App") had `folder: null`, so the map
  had nothing to walk. The row was recorded as FAIL, not as a pass.

## What changed (owner approved: "Create/open a project folder so I can re-test it")

Created one coding project on the PC through the real route
(`POST /api/projects`, `here=true` from localhost, folder chosen PC-only):

```
POST /api/projects
{"name": "Epic Jarvis (repo map field test)", "kind": "coding",
 "folder": "C:\\Users\\pcadmin\\Documents\\Jarvis github\\Epic-Jarvis-main"}
-> 200 {"ok": true, "project": {"id": "65c6e3a9e00d4f4389842c7f45623c91",
        "kind": "coding", "folder": {"path": "...\\Epic-Jarvis-main",
        "name": "Epic-Jarvis-main", "listed": true}, ...}}
```

The folder is inside `C:\Users\pcadmin\Documents`, which is already on "Folders
Jarvis may look in" (`GET /api/folders` → one folder, listed), so no folder-list
change and no extra card were needed.

## Re-test result

```
GET /api/projects/65c6e3a9e00d4f4389842c7f45623c91/map?q=where is the bench module
-> 200
"Repository map of Epic-Jarvis-main - 175 files with names to show,
 6772 symbols declared.
 Question: bench module
 (Not the whole folder: the walk reached its 6 second limit.)
 1. backend/test_bench.py  score=36.05
    L1299 def t_the_module_only_ever_talks_to_this_pc()
    ..."
```

So the repo-map feature now demonstrably works on the live build: a real project
folder, a ranked map with file names and declared symbols, and the documented
"the walk reached its limit" honesty line instead of a silent truncation.

## Verdict for this row

**repo_map: PASS (addendum evidence), not a re-run of the harness row** — the
harness row ran against the project-less state and stays FAIL in `results.json`
as the historical record. A re-run of the whole harness on the next deploy should
now score this row PASS with the project above (the check names the project it
tests; keep `65c6e3a9e00d4f4389842c7f45623c91` or re-create it).

## Still open in the field matrix

- `phone_app_foreground` — BLOCKED (phone asleep/locked; owner deferred waking it).
- `skills_read` — BLOCKED (list empty; nothing to observe).
- `chat_packs_list` — NOT-MEASURED (model tool; opt-in model turn did not use it).
- All PR-2 features (deny-and-steer, hidden-byte pill, cost line, curator lock,
  "New — currently off") — **not field-tested**: not deployed yet (in #1197 CI).
- Clean 100%-on-card benchmark baseline — **not yet taken**: the bench's default
  `num_gpu` is the model's `block_count` (32) while Ollama needs 33 for every layer;
  measured 84% at 32 vs 100% at 33/34/40/99. Fix is in the priority PR; after it
  deploys, the baseline is re-taken per the owner's ruling.

## Evidence

- `.dsh-scratch/NV-UNLOCK-2026-11-06/repomap-field-test.json` — the request and the
  full returned map (saved by the session).
- `GET /api/folders` at 13:5x PT — one allowed folder, `C:\Users\pcadmin\Documents`.
- `GET /api/projects` at 13:5x PT — the project with `folder.name = "Epic-Jarvis-main"`.
