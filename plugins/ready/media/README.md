# media

"pause", "next song", "what's playing": play, pause, next, previous and now-playing for whatever is playing on this PC (Spotify, a browser tab, or any other app that reports to Windows' own media cont

**Drop-in.** Nothing about `jarvis_hud.py` changes to add this. Copy
this folder into the backend's `jarvis_plugins\` folder (or run
`scripts\add-plugin.ps1 -Name media`) and restart Jarvis.

- Module the loader calls: `jarvis_media.install()` (takes the core's Handler)
- The patch this replaces: `backend/media.patch`
- Position in the old patch stack: 75 of 134

The module itself is one of the ones this repository already ships
(`backend/jarvis_media.py`), copied into the backend by
`scripts/apply-patches.ps1` exactly as before. This folder does not
change it.
