# docker

the containers on Jarvis's OWN list, and start/stop for them.

**Drop-in.** Nothing about `jarvis_hud.py` changes to add this. Copy
this folder into the backend's `jarvis_plugins\` folder (or run
`scripts\add-plugin.ps1 -Name docker`) and restart Jarvis.

- Module the loader calls: `jarvis_docker.install()` (takes the core's Handler)
- The patch this replaces: `backend/docker.patch`
- Position in the old patch stack: 130 of 155

The module itself is one of the ones this repository already ships
(`backend/jarvis_docker.py`), copied into the backend by
`scripts/apply-patches.ps1` exactly as before. This folder does not
change it.
