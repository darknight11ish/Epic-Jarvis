# history-import

"Bring in chats from ChatGPT, Claude, Gemini or DeepSeek".

**Drop-in.** Nothing about `jarvis_hud.py` changes to add this. Copy
this folder into the backend's `jarvis_plugins\` folder (or run
`scripts\add-plugin.ps1 -Name history-import`) and restart Jarvis.

- Module the loader calls: `jarvis_history_import.install()` (takes the core's Handler)
- The patch this replaces: `backend/history-import.patch`
- Position in the old patch stack: 90 of 122

The module itself is one of the ones this repository already ships
(`backend/jarvis_history_import.py`), copied into the backend by
`scripts/apply-patches.ps1` exactly as before. This folder does not
change it.
