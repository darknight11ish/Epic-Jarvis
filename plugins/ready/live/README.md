# live

Jarvis Live: a back-and-forth voice conversation the owner starts and stops, with no "hey Jarvis" between turns.

**Drop-in.** Nothing about `jarvis_hud.py` changes to add this. Copy
this folder into the backend's `jarvis_plugins\` folder (or run
`scripts\add-plugin.ps1 -Name live`) and restart Jarvis.

- Module the loader calls: `jarvis_live.install()` (takes the core's Handler)
- The patch this replaces: `backend/live.patch`
- Position in the old patch stack: 94 of 122

The module itself is one of the ones this repository already ships
(`backend/jarvis_live.py`), copied into the backend by
`scripts/apply-patches.ps1` exactly as before. This folder does not
change it.
