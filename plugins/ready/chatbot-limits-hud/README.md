# chatbot-limits-hud

the monthly money limits and the price list for the chatbot driver's API services, set from the PC's own app.

**Drop-in.** Nothing about `jarvis_hud.py` changes to add this. Copy
this folder into the backend's `jarvis_plugins\` folder (or run
`scripts\add-plugin.ps1 -Name chatbot-limits-hud`) and restart Jarvis.

- Module the loader calls: `jarvis_chatbot_limits.install()` (takes the core's Handler)
- The patch this replaces: `backend/chatbot-limits-hud.patch`
- Position in the old patch stack: 117 of 134

The module itself is one of the ones this repository already ships
(`backend/jarvis_chatbot_limits.py`), copied into the backend by
`scripts/apply-patches.ps1` exactly as before. This folder does not
change it.
