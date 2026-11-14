# Wave-14 rollback note (2026-11-09 night -> 2026-11-10)

This is the pointer for the wave-14 deploy. The general procedure is **wave 13's
`ROLLBACK.md`** (`.dsh-scratch\WAVE13-DEPLOY-2026-11-09\ROLLBACK.md`, 14,898 B, sha256
`F309B19C…`; verified SAFE TO FOLLOW on 2026-11-09) — read it first and follow it in order. Only the
anchor folder and the Q3 extra step below are wave-14-specific.

## The wave-14 backend anchor (printed by the apply gate)

- Backup folder (28th `_jarvis-deploy-backup-tool-*`):
  `C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program\_jarvis-deploy-backup-tool-20261109-213922`
- Its journal: `_journal.json` inside that folder.
- The apply wrote `wrote 25` (`PLANNED CHANGES: 257`, `VERSION: wrote 0.2.444`) and printed
  `BACKUP: … -20261109-213922`.

## Roll back the backend (only after proving the stack is stopped)

```
powershell -NoProfile -ExecutionPolicy Bypass -File ".dsh-scratch\WAVE14-DEPLOY-2026-11-09\deploy-gates-wave14.ps1" -Gate stopped
py -3 -B C:\Users\pcadmin\Documents\jarvis-install-tree\tools\reconcile_live_backend.py --backend-path "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program" --rollback "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program\_jarvis-deploy-backup-tool-20261109-213922"
```

Then start the app again (`.dsh-scratch\WAVE14-DEPLOY-2026-11-09\deploy-gates-wave14.ps1 -Gate restart`)
and re-check VERSION/phone identity. The desktop EXE and the phone APK roll back by installing the
**wave-13** assets (desktop 0.2.444 -> 0.2.443, phone 0.2.4047 -> 0.2.4042); wave-13's `ROLLBACK.md`
names where those verified assets live. Do not start a different server; do not touch
`jarvis-framework.toml` (58,409 B / `9C6CDF76…C92D97` before and after this deploy).

## The Q3 cache-cap change (owner ruling Q3) — its own two-line rollback

The deploy itself did NOT write these; they were applied AFTER all gates/acceptance, backed up first:

| live file | pre-Q3 sha256 | post-Q3 sha256 | backup |
|---|---|---|---|
| `C:\Users\pcadmin\AppData\Local\JarvisOllama\start-lane.ps1` (live-only, not in git) | `684B14FC70D18DFDE44FE1D0C8A525859D38E0B6CA626117F575A6D438D32502` | `2D3C761CD6490895052F83D20A41B0793AF38241746C6C4DFF38C86BF9A22E94` | `D:\jarvis-scratch\WAVE14-CACHE-CAP-2026-11-09\pre-q3\start-lane.ps1.pre-q3` |
| `…\Desktop program\jarvis_big_coder.py` | `A21C0D847587FA963C725529BEAF0E052493D97A88DFB268808B9C54C26F81BC` | `96F526077BF42A2C0EBA64C00A0F36B4A577106FB110E5FA112276DEEA80B547` | `D:\jarvis-scratch\WAVE14-CACHE-CAP-2026-11-09\pre-q3\jarvis_big_coder.py.pre-q3` |

To undo Q3 only: copy the two `.pre-q3` files back over those live paths, restart the two lane tasks
once (`Jarvis Ollama - Everyday model (RTX 2060)`, `Jarvis Ollama - Coding model (RTX 2080 Super)`),
and restart the app once. Nothing else was changed for Q3. The same one-line change belongs in the
repository (`backend/jarvis_big_coder.py` + `jarvis-backend/jarvis_big_coder.py`) in the wave-15 PR,
so a future deploy does not silently remove the cap.

## What is NOT rolled back by any of the above

- The phone APK install (0.2.4047) — reinstall the old APK to undo.
- The verification evidence: `run-20261109-212243` in the wave-14 packet, and
  `D:\jarvis-scratch\WAVE14-REVERIFY-2026-11-09\`, `D:\jarvis-scratch\WAVE14-PROBES-2026-11-09\`.
- Any owner data/TOML — none of it was written by this deploy.
