# documents

"Folders Jarvis may look in": finding files by name, searching inside notes and text files, reading PDFs, Word, Excel and PowerPoint files one part at a time, and bringing in a Notion export.

**Drop-in.** Nothing about `jarvis_hud.py` changes to add this. Copy
this folder into the backend's `jarvis_plugins\` folder (or run
`scripts\add-plugin.ps1 -Name documents`) and restart Jarvis.

- Module the loader calls: `jarvis_documents.install()` (takes the core's Handler)
- The patch this replaces: `backend/documents.patch`
- Position in the old patch stack: 67 of 123

The module itself is one of the ones this repository already ships
(`backend/jarvis_documents.py`), copied into the backend by
`scripts/apply-patches.ps1` exactly as before. This folder does not
change it.
