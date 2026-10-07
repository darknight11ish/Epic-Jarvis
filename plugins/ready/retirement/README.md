# retirement

the retirement what-if calculator.

**Drop-in.** Nothing about `jarvis_hud.py` changes to add this. Copy
this folder into the backend's `jarvis_plugins\` folder (or run
`scripts\add-plugin.ps1 -Name retirement`) and restart Jarvis.

- Module the loader calls: `jarvis_retirement.install()` (takes the core's Handler)
- The patch this replaces: `backend/retirement.patch`
- Position in the old patch stack: 110 of 122

The module itself is one of the ones this repository already ships
(`backend/jarvis_retirement.py`), copied into the backend by
`scripts/apply-patches.ps1` exactly as before. This folder does not
change it.
