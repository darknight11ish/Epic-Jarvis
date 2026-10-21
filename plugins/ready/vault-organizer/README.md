# vault-organizer

Plan a tidy-up of an Obsidian vault, look at it, then let ONE approval card do
exactly that - with one click to put it all back.

- `POST /api/vault/organize-plan` - the read-only dry run. It reads the vault's
  notes and answers the vault's shape: how many notes, what tags it would add
  (merged with the owner's own, never replacing them), which
  `up: "[[_MOC - <Topic>]]"` link each note would get, the
  `_MOC - <Topic>.md` hub notes and a `00 - Vault Home.md` it would create, the
  duplicates and empty stubs it found (listed, never deleted), and a `plan_id`
  + `digest` for the writer. It writes nothing anywhere, raises no card and
  calls no model.
- `POST /api/vault/organize` - the writer: ONE `organize_obsidian_vault`
  approval card for the whole batch, a file-guardian snapshot of every file it
  changes, atomic writes, nothing ever deleted, and ONE batch receipt whose
  single Undo restores the exact bytes AND paths. A vault edited since the plan
  is refused as stale; a write that fails part-way says so and is still
  undoable.
- `GET /api/vault/organizer` - the switch, the default scheme, the schemes, and
  whether the writer can apply.
- `POST /api/vault/organizer/enabled` - the switch: OFF is immediate, ON is ONE
  `change_own_config` approval card.

DEFAULT SCHEME: `mocs_only` - no file moves at all. `topic_folders` and `para`
preview AND write their moves, behind the explicit `scheme` parameter.

**Off by default** (`[vault_organizer] enabled = false` in
`jarvis-framework.toml`), **PC-only**, and the FIRST REAL RUN IS ON A COPY of
the vault - the runbook is in `docs/JARVIS-API.md` section 151.

The module is `backend/jarvis_vault_organizer.py`; it reuses `jarvis_notes.py`
for the vault resolution and the inside-the-vault rule, `jarvis_file_guardian`
for the pre-write copies, `jarvis_receipts` for the one batch receipt and its
Undo, and `jarvis_documents` only to refresh the index when the vault is a
folder the owner already let Jarvis read. No patch: this folder calls its
`install()`.
