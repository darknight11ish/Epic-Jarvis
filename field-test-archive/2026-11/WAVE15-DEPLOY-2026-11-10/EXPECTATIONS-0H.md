# EXPECTATIONS-0H - wave 15 (measured at the frozen merge commit)

Frozen ref (authority: frozen-ref.txt in this folder): merge commit
`fd9cb5762c021a4b16508a7c0c75c7073db17fa4`, tree `be33366702d062459e0df2d97b11a837e4ee215f`.

## How these were measured

Read-only Gate 0H dry run, in the deploy tree at the frozen ref, against the real live folder:

```
cd .dsh-scratch\WAVE15-DEPLOY-2026-11-10\wt
$env:JARVIS_BACKEND = $null
py -3 -B tools\reconcile_live_backend.py --backend-path "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program" --ref fd9cb5762c021a4b16508a7c0c75c7073db17fa4 --dry-run
```

Evidence: `0H-preview-wave15.txt` (pre-run) and run folder `run-20261110-102051\0H-dryrun.txt`
(the gate's own execution). Both said the same numbers; the gate also recorded
`dryRunExit=0`, `VERSIONsame=True`, `backupFolders=28->28`, no REFUSED / no Traceback.

## Measured values (these are the expectations for the wave-15 run)

| line | measured at the frozen tree |
|---|---|
| SHIPPED | **335 files = add 0 + update 7 + unchanged 328** |
| the seven updates | `jarvis_recent_changes.py`, `jarvis_hud.html`, `hud-edit.js`, `hud-presets.js`, `hud-layout.js`, `jarvis_vault_organizer.py`, `jarvis-self-code.json` |
| HUD DELTAS | **234 checked = 234 already present + 0 to insert** (an insert row is a STOP) |
| READY PLUG-INS | 32 present, 0 to add, 26 already wired |
| PYCACHE | 236 stale `.pyc` files (LIVE measurement - read the tool's own number at 0H) |
| PLANNED CHANGES | **243 = add 0 + update 7 + insert 0 + beside+version 0 + pycache 236** |
| VERSION | unchanged 0.2.444 (apply writes 0.2.445) |
| BESIDE | requirements.lock unchanged, quiz_grader_cases.json unchanged |
| backup folders | 28 -> 28 before apply; the apply's BACKUP line creates the 29th |

## What the apply is expected to write

`wrote N = update 7 + VERSION 1 = 8` (0 add, 0 insert, 0 beside at this ref). Wave 14's
formula gave 25 = add 1 + update 21 + staged delta 2 + VERSION 1; the pycache purges are
counted by PLANNED, never by `wrote`.

## Residual measurements (not predictable; read the tool)

- The exact `PLANNED CHANGES` total moves with the live pycache count at 0H time.
- The apply's three by-design probe failures and the SKIP app-control row.
- reseal: `VERIFY: 0 of 335` and the PARTIAL name list (expected subset of
  jarvis_gate.py, jarvis_hud.py, jarvis_skills.py, jarvis_extract.py,
  jarvis_project_read.py - this wave changes none of those modules).

## Live state at 0H time (recorded, not a gate input)

Backend + desktop 0.2.444, phone 0.2.4047, 28 `_jarvis-deploy-backup-tool-*` folders,
backend listener pid 36612 on 127.0.0.1:4719 and 100.75.21.228:4719, HTTP 403 without a
token, owner TOML 58,409 B / `9C6CDF76...C92D97`, jarvis_gate.py 220,771 B /
`B410327D...` (both unchanged by the wave-15 apply, which does not ship either).

Pre-deploy evidence file (file sizes + sha256 of the live files this deploy changes, the
lane snapshots, and the cache-cap log counts): `baseline-before-wave15.txt`.
