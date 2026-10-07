# tutorials

Tutorials and the FAQ, for both apps, with the owner's progress.

**Drop-in.** Nothing about `jarvis_hud.py` changes to add this. Copy
this folder into the backend's `jarvis_plugins\` folder (or run
`scripts\add-plugin.ps1 -Name tutorials`) and restart Jarvis.

- Module the loader calls: `jarvis_tutorials.install()` (takes the core's Handler)
- The patch this replaces: `backend/tutorials.patch`
- Position in the old patch stack: 118 of 122

The module itself is one of the ones this repository already ships
(`backend/jarvis_tutorials.py`), copied into the backend by
`scripts/apply-patches.ps1` exactly as before. This folder does not
change it.
