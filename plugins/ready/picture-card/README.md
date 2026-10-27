# picture-card

"which card draws the pictures, and what the chat does about it".

**Drop-in.** Nothing about `jarvis_hud.py` changes to add this. Copy
this folder into the backend's `jarvis_plugins\` folder (or run
`scripts\add-plugin.ps1 -Name picture-card`) and restart Jarvis.

- Module the loader calls: `jarvis_picture_card.install()` (takes the core's Handler)
- The patch this replaces: `backend/picture-card.patch`
- Position in the old patch stack: 141 of 158

The module itself is one of the ones this repository already ships
(`backend/jarvis_picture_card.py`), copied into the backend by
`scripts/apply-patches.ps1` exactly as before. This folder does not
change it.
