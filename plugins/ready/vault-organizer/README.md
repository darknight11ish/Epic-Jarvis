# vault-organizer

A read-only PLAN for an Obsidian vault: what a tidy-up *would* do, before
anything is changed.

- `POST /api/vault/organize-plan` - the dry run. It reads the vault's notes and
  answers the vault's shape: how many notes, what tags it would add (merged with
  the owner's own, never replacing them), which `up: "[[_MOC - <Topic>]]"` link
  each note would get, the `_MOC - <Topic>.md` hub notes and a
  `00 - Vault Home.md` it would create, the duplicates and empty stubs it found
  (listed, never deleted), and a `plan_id` + `digest` for the later apply. It
  writes nothing anywhere, raises no card and calls no model.
- `GET /api/vault/organizer` - the switch, the default scheme and the schemes.
- `POST /api/vault/organizer/enabled` - the switch: OFF is immediate, ON is ONE
  `change_own_config` approval card.

DEFAULT SCHEME: `mocs_only` - no file moves at all. `topic_folders` and `para`
preview their moves, and only a later, explicitly approved apply may use them.

**Off by default** (`[vault_organizer] enabled = false` in
`jarvis-framework.toml`), **PC-only**, and the writer - one card for the whole
batch, file-guardian snapshots and one-click Undo - is a named follow-up slice.
It is NOT claimed here. See `docs/JARVIS-API.md` section 150.

The module is `backend/jarvis_vault_organizer.py`; it reuses `jarvis_notes.py`
for the vault resolution and the inside-the-vault rule. No patch: this folder
calls its `install()`.
