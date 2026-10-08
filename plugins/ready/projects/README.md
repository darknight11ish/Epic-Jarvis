# projects

Projects, steps 1 and 2.

**Drop-in.** Nothing about `jarvis_hud.py` changes to add this. Copy
this folder into the backend's `jarvis_plugins\` folder (or run
`scripts\add-plugin.ps1 -Name projects`) and restart Jarvis.

- Module the loader calls: `jarvis_projects.install()` (takes the core's Handler)
- The patch this replaces: `backend/projects.patch`
- Position in the old patch stack: 91 of 123

The module itself is one of the ones this repository already ships
(`backend/jarvis_projects.py`), copied into the backend by
`scripts/apply-patches.ps1` exactly as before. This folder does not
change it.
