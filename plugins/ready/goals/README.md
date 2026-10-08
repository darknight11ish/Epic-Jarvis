# goals

"Goals with one card per step".

**Drop-in.** Nothing about `jarvis_hud.py` changes to add this. Copy
this folder into the backend's `jarvis_plugins\` folder (or run
`scripts\add-plugin.ps1 -Name goals`) and restart Jarvis.

- Module the loader calls: `jarvis_goals.install()` (takes the core's Handler)
- The patch this replaces: `backend/goals.patch`
- Position in the old patch stack: 84 of 123

The module itself is one of the ones this repository already ships
(`backend/jarvis_goals.py`), copied into the backend by
`scripts/apply-patches.ps1` exactly as before. This folder does not
change it.
