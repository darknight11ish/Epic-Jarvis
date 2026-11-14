# Wave-15 rollback note (2026-11-10)

This is the pointer for the wave-15 deploy. The general procedure is **wave 13's
`ROLLBACK.md`** (`.dsh-scratch\WAVE13-DEPLOY-2026-11-09\ROLLBACK.md`) — read it first and
follow it in order. Only the anchor folder and the wave-15-specific pointers below are new.

## The wave-15 backend anchor (printed by the apply gate)

- Backup folder (the 29th `_jarvis-deploy-backup-tool-*`):
  `C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program\_jarvis-deploy-backup-tool-20261110-104447`
- Its journal: `_journal.json` inside that folder.
- The apply wrote `wrote 8` (`PLANNED CHANGES: 244 = add 0 + update 7 + VERSION 1 + pycache 236`),
  `VERSION: wrote 0.2.445`, `RESULT: FAIL (3 expected)`, `applyExit=1`.
- Insurance copy taken just before the apply:
  `D:\jarvis-rehearsal\predeploy-wave15-20261110-102144` (`program\` 940 files / 106,786,533 B,
  byte-identical filtered count+bytes to the live folder; `data\` 2,498 files / 1,585,924,433 B —
  182.7 MB LARGER than the live measurement because robocopy de-referenced the HuggingFace cache's
  symlinks into real copies; TOML hash equal, `program\VERSION` 0.2.444).

## Roll back the backend (only after proving the stack is stopped)

```
powershell -NoProfile -ExecutionPolicy Bypass -File ".dsh-scratch\WAVE15-DEPLOY-2026-11-10\deploy-gates-wave15.ps1" -Gate stopped
py -3 -B C:\Users\pcadmin\Documents\jarvis-install-tree\tools\reconcile_live_backend.py --backend-path "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program" --rollback "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program\_jarvis-deploy-backup-tool-20261110-104447"
```

Then start the app again (`.dsh-scratch\WAVE15-DEPLOY-2026-11-10\deploy-gates-wave15.ps1 -Gate restart`)
and re-check VERSION/phone identity. Do not start a different server; do not touch
`jarvis-framework.toml` (58,409 B / `9C6CDF76…C92D97` before and after this deploy).

## Desktop and phone

- Desktop rolls back to **0.2.444** by running the wave-14 setup that was installed then. Its
  verified copy came from the wave-14 gate train; re-derive it with the wave-14 packet's Gate 0F
  pattern (`.dsh-scratch\WAVE14-DEPLOY-2026-11-09\deploy-gates-wave14.ps1`) or use the wave-14
  run-folder artefacts if still present:
  `.dsh-scratch\WAVE14-DEPLOY-2026-11-09\run-20261109-212243\artifacts\jarvis-desktop_0.2.444_x64-setup.exe`
  (check the file exists before relying on it; the rolling `desktop-latest` release no longer holds
  0.2.444).
- Phone rolls back to **0.2.4047** by `adb install -r` of the wave-14 APK
  (`…\WAVE14-DEPLOY-2026-11-09\run-20261109-212243\artifacts\jarvis-client-<sha7>.apk`,
  versionName 0.2.4047 / versionCode 1000004047). Reinstalling an OLDER `versionCode` needs
  `adb install -r -d`; record honestly if Android refuses.
- Wave-15 itself installed desktop **0.2.445** (setup sha256
  `22D554DDDA4899B52075FED03F4EF7F854FBE5A1D54EFEB57C438FEF2F029277`) and phone **0.2.4054**
  (`jarvis-client-fd9cb57.apk`, sha256 `2D006B5E9F3A20695F40FFF460347EA32F8FBF6FA3B90DA726C6C55EC1F1D42B`,
  versionCode 1000004054).

## Q3 cache-cap and Q7 lane state — nothing to roll back

- The 3 GB prompt-cache cap is in the REPOSITORY now (`backend/jarvis_big_coder.py` + twin,
  53,831 B, sha256 `96F52607…`), byte-identical to the live file; the live-only
  `C:\Users\pcadmin\AppData\Local\JarvisOllama\start-lane.ps1` (sha256 `2D3C761C…`) carries the
  other two lanes' cap. This deploy did NOT edit either file for Q3. To undo Q3 (owner's call),
  restore the `.pre-q3` backups in `D:\jarvis-scratch\WAVE14-CACHE-CAP-2026-11-09\pre-q3\` and
  restart the two lane tasks once plus the app once.
- The deploy did NOT restart the 11436/11435 lane tasks. Lane 11436 was restored by owner ruling
  Q7 from `qwen3-coder-30b-a3b-ud-q3-k-xl:latest` (14.44 GB / 10.68 GB VRAM, ctx 8192) back to
  `qwen3.5:9b` (ctx 196608, all 9,857,400,830 B in VRAM, 0 spill). 11435 and 11450 are cold.
  A rollback of the backend does not change the lane model; re-warm it the same way if needed.

## What is NOT rolled back by any of the above

- The phone APK install (0.2.4054) — reinstall the older APK to undo.
- The verification evidence: run folder `run-20261110-102051` in this packet (all gate logs,
  `10-probes-*`, `10b2-post-checks*`, `awareness-sanity.json`, `12-verify-wave8-wave15.json`,
  `q7-restoration.txt`, `final-state-wave15.txt`).
- Any owner data / TOML / memory.db / approval cards — none of it was written by this deploy.
