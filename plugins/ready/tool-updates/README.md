# tool-updates

"Check for tool updates", on request: is each Python package, Rust building block and pinned GitHub-hosted tool Jarvis is built from still the newest version, or is a newer one out.

**Drop-in.** Nothing about `jarvis_hud.py` changes to add this. Copy
this folder into the backend's `jarvis_plugins\` folder (or run
`scripts\add-plugin.ps1 -Name tool-updates`) and restart Jarvis.

- Module the loader calls: `jarvis_tool_updates.install()` (takes the core's Handler)
- The patch this replaces: `backend/tool-updates.patch`
- Position in the old patch stack: 79 of 123

The module itself is one of the ones this repository already ships
(`backend/jarvis_tool_updates.py`), copied into the backend by
`scripts/apply-patches.ps1` exactly as before. This folder does not
change it.
