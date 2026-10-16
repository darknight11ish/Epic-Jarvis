# card-prefs

how much of an approval card is shown at first, and the setting that decides it, kept where BOTH apps can read it.

**Drop-in.** Nothing about `jarvis_hud.py` changes to add this. Copy
this folder into the backend's `jarvis_plugins\` folder (or run
`scripts\add-plugin.ps1 -Name card-prefs`) and restart Jarvis.

- Module the loader calls: `jarvis_card_summary.install()` (takes the core's Handler)
- The patch this replaces: `backend/card-prefs.patch`
- Position in the old patch stack: 138 of 145

The module itself is one of the ones this repository already ships
(`backend/jarvis_card_summary.py`), copied into the backend by
`scripts/apply-patches.ps1` exactly as before. This folder does not
change it.
