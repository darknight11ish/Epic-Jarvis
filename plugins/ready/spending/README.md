# spending

"How much did I spend on food last month?", added up from a bank export the owner dropped into a folder Jarvis may look in.

**Drop-in.** Nothing about `jarvis_hud.py` changes to add this. Copy
this folder into the backend's `jarvis_plugins\` folder (or run
`scripts\add-plugin.ps1 -Name spending`) and restart Jarvis.

- Module the loader calls: `jarvis_spending.install()` (takes the core's Handler)
- The patch this replaces: `backend/spending.patch`
- Position in the old patch stack: 109 of 122

The module itself is one of the ones this repository already ships
(`backend/jarvis_spending.py`), copied into the backend by
`scripts/apply-patches.ps1` exactly as before. This folder does not
change it.
