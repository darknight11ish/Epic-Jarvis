# model-lanes

the button that starts the model lane that is down.

**Drop-in.** Nothing about `jarvis_hud.py` changes to add this. Copy
this folder into the backend's `jarvis_plugins\` folder (or run
`scripts\add-plugin.ps1 -Name model-lanes`) and restart Jarvis.

- Module the loader calls: `jarvis_model_lanes.install()` (takes the core's Handler)
- The patch this replaces: `backend/model-lanes.patch`
- Position in the old patch stack: 144 of 155

The module itself is one of the ones this repository already ships
(`backend/jarvis_model_lanes.py`), copied into the backend by
`scripts/apply-patches.ps1` exactly as before. This folder does not
change it.
