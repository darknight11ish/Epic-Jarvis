# news

news headlines in the morning briefing, from RSS/Atom feed addresses the owner names.

**Drop-in.** Nothing about `jarvis_hud.py` changes to add this. Copy
this folder into the backend's `jarvis_plugins\` folder (or run
`scripts\add-plugin.ps1 -Name news`) and restart Jarvis.

- Module the loader calls: `jarvis_news.install()` (takes the core's Handler)
- The patch this replaces: `backend/news.patch`
- Position in the old patch stack: 76 of 134

The module itself is one of the ones this repository already ships
(`backend/jarvis_news.py`), copied into the backend by
`scripts/apply-patches.ps1` exactly as before. This folder does not
change it.
