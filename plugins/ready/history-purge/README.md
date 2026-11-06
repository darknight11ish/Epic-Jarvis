# history-purge

clear old chats (and the facts they taught) for a date range, after a card, TWO separate yeses and a Windows Hello / fingerprint ticket. This is the one route pair in Jarvis that deletes in bulk and c

**Drop-in.** Nothing about `jarvis_hud.py` changes to add this. Copy
this folder into the backend's `jarvis_plugins\` folder (or run
`scripts\add-plugin.ps1 -Name history-purge`) and restart Jarvis.

- Module the loader calls: `jarvis_history_purge.install()` (takes the core's Handler)
- The patch this replaces: `backend/history-purge.patch`
- Position in the old patch stack: 170 of 177

The module itself is one of the ones this repository already ships
(`backend/jarvis_history_purge.py`), copied into the backend by
`scripts/apply-patches.ps1` exactly as before. This folder does not
change it.
