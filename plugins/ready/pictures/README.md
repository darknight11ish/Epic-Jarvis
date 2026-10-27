# pictures

"ask for a picture, and keep it" (the owner's decision of 2026-09-27: *"12 GB card: longer conversations with picture understanding first, and making pictures too (swapped in when asked, since both ca

**Drop-in.** Nothing about `jarvis_hud.py` changes to add this. Copy
this folder into the backend's `jarvis_plugins\` folder (or run
`scripts\add-plugin.ps1 -Name pictures`) and restart Jarvis.

- Module the loader calls: `jarvis_pictures.install()` (takes the core's Handler)
- The patch this replaces: `backend/pictures.patch`
- Position in the old patch stack: 143 of 157

The module itself is one of the ones this repository already ships
(`backend/jarvis_pictures.py`), copied into the backend by
`scripts/apply-patches.ps1` exactly as before. This folder does not
change it.
