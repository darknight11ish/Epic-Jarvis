# progress

the activity heatmap and the owner's balance chart (the owner's decision of 2026-09-30, docs/BUILD-QUEUE-2026-09-30.md item 7; docs/GOALS-PROGRESS-DESIGN.md part C and its "Progress contract (frozen)"

**Drop-in.** Nothing about `jarvis_hud.py` changes to add this. Copy
this folder into the backend's `jarvis_plugins\` folder (or run
`scripts\add-plugin.ps1 -Name progress`) and restart Jarvis.

- Module the loader calls: `jarvis_progress.install()` (takes the core's Handler)
- The patch this replaces: `backend/progress.patch`
- Position in the old patch stack: 111 of 122

The module itself is one of the ones this repository already ships
(`backend/jarvis_progress.py`), copied into the backend by
`scripts/apply-patches.ps1` exactly as before. This folder does not
change it.
