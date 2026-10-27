# secret-handoff

the host half of the owner-secret hand-off.

**Drop-in.** Nothing about `jarvis_hud.py` changes to add this. Copy
this folder into the backend's `jarvis_plugins\` folder (or run
`scripts\add-plugin.ps1 -Name secret-handoff`) and restart Jarvis.

- Module the loader calls: `jarvis_secret_handoff_wiring.install()` (takes the core's Handler)
- The patch this replaces: `backend/secret-handoff.patch`
- Position in the old patch stack: 153 of 155

The module itself is one of the ones this repository already ships
(`backend/jarvis_secret_handoff_wiring.py`), copied into the backend by
`scripts/apply-patches.ps1` exactly as before. This folder does not
change it.
