# chatbot-routes

the routes both apps use to have Jarvis talk to an AI chatbot for the owner.

**Drop-in.** Nothing about `jarvis_hud.py` changes to add this. Copy
this folder into the backend's `jarvis_plugins\` folder (or run
`scripts\add-plugin.ps1 -Name chatbot-routes`) and restart Jarvis.

- Module the loader calls: `jarvis_chatbot_routes.install()` (takes the core's Handler)
- The patch this replaces: `backend/chatbot-routes.patch`
- Position in the old patch stack: 93 of 122

The module itself is one of the ones this repository already ships
(`backend/jarvis_chatbot_routes.py`), copied into the backend by
`scripts/apply-patches.ps1` exactly as before. This folder does not
change it.
