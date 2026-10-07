# photo-reminder

"Photo to reminder": a picture in, a PROPOSED reminder out. Nothing is set up here.

**Drop-in.** Nothing about `jarvis_hud.py` changes to add this. Copy
this folder into the backend's `jarvis_plugins\` folder (or run
`scripts\add-plugin.ps1 -Name photo-reminder`) and restart Jarvis.

- Module the loader calls: `jarvis_photo_remind.install()` (takes the core's Handler)
- The patch this replaces: `backend/photo-reminder.patch`
- Position in the old patch stack: 89 of 134

The module itself is one of the ones this repository already ships
(`backend/jarvis_photo_remind.py`), copied into the backend by
`scripts/apply-patches.ps1` exactly as before. This folder does not
change it.
