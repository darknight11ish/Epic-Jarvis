# screen-attach

"look at this" can hand the owner the PICTURE, so they can say "look at this" with a chart or an error message and ask about it.

**Drop-in.** Nothing about `jarvis_hud.py` changes to add this. Copy
this folder into the backend's `jarvis_plugins\` folder (or run
`scripts\add-plugin.ps1 -Name screen-attach`) and restart Jarvis.

- Module the loader calls: `jarvis_screen_attach.install()` (takes the core's Handler)
- The patch this replaces: `backend/screen-attach.patch`
- Position in the old patch stack: 129 of 134

The module itself is one of the ones this repository already ships
(`backend/jarvis_screen_attach.py`), copied into the backend by
`scripts/apply-patches.ps1` exactly as before. This folder does not
change it.
