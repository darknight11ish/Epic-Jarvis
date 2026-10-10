# brain-reads

the Brain's read-only routes (the Brain upgrades, and a chat's facts).

**Drop-in.** Nothing about `jarvis_hud.py` changes to add this. Copy
this folder into the backend's `jarvis_plugins\` folder (or run
`scripts\add-plugin.ps1 -Name brain-reads`) and restart Jarvis.

- Module the loader calls: `jarvis_brain_reads.install()` (takes the core's Handler)
- The patch this replaces: `backend/brain-reads.patch`
- Position in the old patch stack: 87 of 134

The module itself is one of the ones this repository already ships
(`backend/jarvis_brain_reads.py`), copied into the backend by
`scripts/apply-patches.ps1` exactly as before. This folder does not
change it.
