# sky

the sun, the moon and the weather behind the animal faces and the robot (which counts as an animal face for every option).

**Drop-in.** Nothing about `jarvis_hud.py` changes to add this. Copy
this folder into the backend's `jarvis_plugins\` folder (or run
`scripts\add-plugin.ps1 -Name sky`) and restart Jarvis.

- Module the loader calls: `jarvis_sky.install()` (takes the core's Handler)
- The patch this replaces: `backend/sky.patch`
- Position in the old patch stack: 96 of 123

The module itself is one of the ones this repository already ships
(`backend/jarvis_sky.py`), copied into the backend by
`scripts/apply-patches.ps1` exactly as before. This folder does not
change it.
