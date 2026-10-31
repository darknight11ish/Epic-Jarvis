# notes-edit

Browse, open and edit **any** note in your Obsidian vault, from the desktop
program or the phone — the owner's decision of 2026-10-31: *"The whole vault,
both apps."*

**Drop-in.** Nothing about `jarvis_hud.py` changes to add this. Copy this
folder into the backend's `jarvis_plugins\` folder (or run
`scripts\add-plugin.ps1 -Name notes-edit`) and restart Jarvis.

- Module the loader calls: `jarvis_notes_edit.install()` (takes the core's Handler)
- The module itself is one of the ones this repository already ships
  (`backend/jarvis_notes_edit.py`), copied into the backend by
  `scripts/apply-patches.ps1` exactly as before. This folder does not change it.
- Position in the loader order: 169 (after `android-builder`). There is no
  patch behind it: this feature was born as a folder.

## The four routes

```
GET  /api/notes/list?q=<text>     every note: path, title, size, mtime (never text)
GET  /api/notes/read?path=<rel>   one note: its text and the sha256 of its bytes
POST /api/notes/save              save the WHOLE new text of one note
GET  /api/notes/save?id=<job id>  waiting / saved / denied / failed
```

A save body is `{"path": "...", "text": "...", "expected_sha256": "<hex>"}`.
The request answers **202 waiting** with a job id while the card is up, and
**200 saved** only after the owner approves. A deny, an expiry or a refused
card leaves the file untouched. A hash that no longer matches is **409
conflict** with the current hash, and nothing is written.

## What protects the vault

- **One card per save**, the ordinary approval card: gate action
  `edit_vault_note`, tier `ask` in the shipped `jarvis-framework.toml`. The
  app never approves anything; the owner does.
- **The File Guardian** copies the note's current bytes before any write, so a
  bad save can be put back. If the copy cannot be made, nothing is written.
- **The vault is the world**: a path is vault-relative, cannot be absolute,
  cannot climb out with `..`, cannot go through a symlink or junction, and
  must be a `.md` or `.txt` file. Hidden folders are never touched.
- **A 2 MiB bound** per note, and at most 2,000 notes in one list.
- Nothing leaves this PC, and no note text is ever put in a card, an audit
  line or a log.
