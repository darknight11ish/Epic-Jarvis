# model-recommendations

suggest a better local model, measure it, and suggest which preset should use it. Nothing here downloads, switches or applies.

**Drop-in.** Nothing about `jarvis_hud.py` changes to add this. Copy
this folder into the backend's `jarvis_plugins\` folder (or run
`scripts\add-plugin.ps1 -Name model-recommendations`) and restart Jarvis.

- Module the loader calls: `jarvis_model_recommendations.install()` (takes the core's Handler)
- The patch this replaces: `backend/model-recommendations.patch`
- Position in the old patch stack: 157 of 164

The module itself is one of the ones this repository already ships
(`backend/jarvis_model_recommendations.py`), copied into the backend by
`scripts/apply-patches.ps1` exactly as before. This folder does not
change it.
