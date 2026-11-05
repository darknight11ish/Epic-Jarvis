# protected-items

**"Protected from Jarvis"** - the owner's list of folders, files and programs
Jarvis may not touch (the owner's request of 2026-10-31: *"add a list of file
folders, and programs that i can manually add to (or ask jarvis to exclude in
chat and get a card) that blocks jarvis from having any access (read or write)
or the ability to make certain files or folders or programs read only"*).

**Drop-in.** Nothing about `jarvis_hud.py` changes to add this. Copy this
folder into the backend's `jarvis_plugins\` folder (or run
`scripts\add-plugin.ps1 -Name protected-items`) and restart Jarvis.

- Module the loader calls: `jarvis_protection.install()` (takes the core's Handler)
- The module itself is one of the ones this repository already ships
  (`backend/jarvis_protection.py`), copied into the backend by
  `scripts/apply-patches.ps1` exactly as before. This folder does not change it.
- Position in the loader order: 170 (after `android-builder`). There is no
  patch behind it: this feature was born as a folder.

## The routes

```
GET  /api/protection                  the list, in the PC's own words
POST /api/protection/add              the desktop Settings' own act - no card
POST /api/protection/remove           ONE card (action unprotect_item)
POST /api/protection/propose          the chat path - ONE card (protect_item)
GET  /api/protection/propose?id=      how one proposal ended
```

Chat reaches the SAME routes, not a copy of them (2026-11-04): the model tool
`protect_from_jarvis` has three actions - `add`, `remove` and `list` (add and
remove raise the ONE card above; `list` reads the store with no card) - and
`jarvis_quick.py`'s fixed phrasings ("restrict the folder C:\X from Jarvis",
"stop Jarvis reading C:\X", "unrestrict C:\X", "what folders are restricted?",
"is Jarvis blocked from C:\X?") call `handle_propose`, `handle_remove` and
`handle_get`/`status_for` directly. Both apps chat through the same
`/api/chat`, so a folder-level restriction can be set by plain chat from the
PC and the phone alike.

## Two modes

- **Blocked - no access.** A folder or file: no read, no search hit, no
  snippet, no document read, no write, no delete, no rename, no File-Guardian
  restore into it, no note-capture write into it. A program: no opening,
  closing or controlling it, and no screen reading of its windows.
- **Read-only.** A folder or file: reading and search results allowed; every
  write, delete, rename and restore refused. A program: "see it, never act" -
  its window title or a screenshot may be read; clicking, typing, opening,
  closing or controlling it is refused.

The list lives in `protected-items.json` in the PC's Jarvis settings folder
(`%USERPROFILE%\.openjarvis`). A damaged or missing file is EMPTY and safe:
it never crashes and never means "protect everything".

## Where the check is enforced

`jarvis_protection.path_refusal()` / `program_refusal()` are called by the
existing modules before they act: `jarvis_documents` (allow-list, find,
search, read, Notion import), `jarvis_agent`'s file tools and the
`protect_from_jarvis` chat tool, `jarvis_note_capture`, `jarvis_notes`,
`jarvis_attached_file`, `jarvis_file_guardian` (restore), `jarvis_open`,
`jarvis_ui_control`, `jarvis_screen` / `jarvis_screen_win`, `jarvis_schedule`
and `jarvis_pictures`. Named gaps are in `docs/JARVIS-API.md` section 170.
