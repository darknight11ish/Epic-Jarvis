"""jarvis_notes_edit.py - browse, open and save ANY note in the owner's
Obsidian vault, with one approval card per save.

WHAT THIS IS FOR

The owner's decision of 2026-10-31, in his own words: **"The whole vault, both
apps"** - search and browse every note in the Obsidian vault, open and edit
any, from the desktop program and from the phone. `jarvis_notes.py` could
already SEARCH the vault (read-only), and `jarvis_note_capture.py` could APPEND
one entry to today's daily note. Neither could browse the vault or change an
existing note. This module is those routes:

    GET  /api/notes/list?q=<text>     every note: path, title, size, mtime
    GET  /api/notes/read?path=<rel>   one note: its text and its sha256
    POST /api/notes/save              save the WHOLE new text of one note
    GET  /api/notes/save?id=<job id>  how one save ended
    POST /api/notes/create            make ONE new note (no overwrite ever)
    POST /api/notes/append            add words to the END of one note
    POST /api/notes/tag               add or remove ONE tag on one note
    POST /api/notes/rename            same folder, new title, links updated
    POST /api/notes/move              into an existing (or created) folder
    POST /api/notes/delete            move up to twenty notes into the vault's
                                      own .trash folder, one card naming them all
    POST /api/notes/merge             fold two to twenty notes into ONE survivor,
                                      one card naming the survivor and every note
                                      that leaves
    POST /api/notes/copy              duplicate ONE note (a new note, so it is
                                      additive: no card for a direct owner write)
    POST /api/notes/trash             empty the vault's own .trash folder: ONE
                                      card listing every file with its age, and
                                      nothing happens without it
    GET  /api/notes/change?id=<job>   how one of those writes ended

The three wave-1 writes (2026-10-31, the owner's flexibility decision) are the
same single-file shape as the save: one note, one approval card, the File
Guardian copy first where there are old bytes to keep, and every answer says
you can undo it. The wave-2 slice added rename and move (one note each, their
links updated, an undo receipt either way), and the owner's request of
2026-11-23 adds delete: one to twenty notes, ONE card that names every one of
them, no undo receipt, and the notes move into the vault's own `.trash` folder
rather than being written over. Delete is the one write here that is NOT asked
under `edit_vault_note` - see `DELETE_ACTION` below, and the block above
`handle_delete` for why.

`/api/notes/list`'s `count` is the number of rows in THIS answer (never the
vault's total); `truncated: true` is what says more notes exist beyond the
2,000-row bound. The save-status 404 carries `{"ok": false, "error": "<plain
sentence>"}` so a client can show the PC's own words instead of inventing a
sentence of its own.

It is a DROP-IN module: `plugins/ready/notes-edit/plugin.json` names it and
`jarvis_plugins.py` calls `install()`, exactly like `plugins/ready/receipts`
and `plugins/ready/vault`. There is no patch and no edit to `jarvis_hud.py`;
the loader is what makes the call a patch would have made.

THE ONE PERMISSION MODEL, NOT A SECOND ONE

A save is one more place where Jarvis CHANGES something on this PC, so it uses
the project's one approval mechanism - `jarvis_gate.check()` under the action
name **`edit_vault_note`**, whose tier line lives in the shipped
`jarvis-framework.toml` (`[autonomy.tiers]`, `"ask"`):

    plan()       Work out exactly what would change and where. Reads the
                 disk and the settings; no card, no write.
    card         jarvis_gate.check("edit_vault_note", detail, prompt=...) -
                 the ordinary card, the ordinary Approve / Deny words. The
                 gate has its OWN `_RISK` row for this name (added 2026-11-17
                 by the end-of-file `_RISK.update({...})` block in
                 jarvis-backend/jarvis_gate.py; a drop-in module cannot add
                 one), so its card says what a note change really is:
                 reversible and local. The tier line above is what makes it
                 ask - the row loosens nothing.
    run()        Writes, and only after a verdict whose `allowed` is True.
                 `approved` has no default of True anywhere in this module.

The reply shape is the contract's, not a new one:

    POST /api/notes/save
        202 {"ok": true, "state": "waiting", "id": "<job id>", "path": "..."}
        200 {"ok": true, "state": "saved", "path": "...", "sha256": "..."}
        409 {"ok": false, "state": "conflict", "path": "...",
             "current_sha256": "..."}
        400 / 413 / 429 / 503 - plain sentences, see each helper.
    GET  /api/notes/save?id=<job id>
        200 {"ok": true, "state": "waiting"|"saved"|"denied"|"failed",
             "path": "...", "sha256": "<hex or null>",
             "message": "<plain sentence>"}
        404 unknown id.

WHAT IT WILL NOT DO

  - Write anything on a Deny, an expiry, or a refused card. The card is the
    ONLY yes, and the write happens after it, never before.
  - Leave a path it cannot prove is inside the vault. A path is
    vault-relative, normalised, refused if absolute or if any `..` component
    escapes, refused if ANY component is a symlink or junction (a reparse
    point), and refused unless the last component is a `.md` or `.txt` file.
    Hidden folders (`.obsidian`, `.trash`, anything starting with a dot) are
    never listed, opened or written.
  - Overwrite silently. Before writing it takes the EXISTING
    `jarvis_notes.snapshot_vault_before_write()`, which is
    `jarvis_file_guardian.snapshot_before_write()` with the configured vault
    as the allowed root - so the old bytes are recoverable through the File
    Guardian. If that copy cannot be made, NOTHING is written.
  - Clobber another editor. The edit carries the sha256 it started from; if
    the file no longer matches - at the request, or while the card was up -
    the save is refused as a conflict with the CURRENT hash, and nothing is
    written.
  - Touch the network, a model, a token or a log line. The routes are local;
    they answer through the core's own origin + token checks; not one byte of
    a note's text is put in a message, an audit line or a log (the audit
    records the path, the sizes and the job id only).
  - Touch a note the owner put on the "Protected from Jarvis" list (2026-10-31):
    a BLOCKED folder or file is never listed, never read and never saved; a
    READ-ONLY one is read normally and refused on save. The refusal is a plain
    sentence and raises NO card - it is a keep-out, not an approval question.
    When that module is not on the backend at all, this editor behaves as it did
    before the list existed. No note's bytes are read to answer it.
  - Destroy a note. Since wave 2 (2026-10-31) a note CAN be renamed or moved
    (with the links that named it updated) and, since 2026-11-23, deleted: up to
    twenty notes are MOVED into the vault's own `.trash` folder, never written
    over, and the owner can put one back from Explorer. What no route here does
    is write over a file to destroy it. The one thing that really destroys bytes
    is `/api/notes/trash`, which empties that trash folder, and it says so on its
    own card.
  - Treat `untitled*` notes specially. Nothing in this module keys on a note's
    name at all: `untitled` handling is a separate feature (the vault organizer's),
    and a note called "Untitled" is renamed, moved, merged, copied or deleted here
    exactly like any other note.
  - Overwrite an existing note from `/api/notes/create`: a path that is already
    there is a 409 before any card. Creation makes ONE new file; undo removes
    exactly that file and refuses if it changed since.
  - Write several notes in one request. Every route takes ONE path; a body that
    tries to name a list is refused in plain words before any card.

ONE CARD PER SAVE, AND WHAT "WAITING" MEANS

Each save gets a job id and one card. The save runs on a small daemon thread
because `jarvis_gate.check()` BLOCKS for the "ask" tier until the owner
answers; the request itself answers after a short wait (`wait_s`, 1.5 s by
default) with `202 waiting` and the job id, and `GET /api/notes/save?id=`
then says how it ended. At most `MAX_WAITING` (4) saves may be waiting at
once - the refusal names the limit in plain words - and the finished-job
table is bounded too (`MAX_JOBS`), so a long-lived backend cannot grow here.

HONEST LIMITS

  - The routes are built and proved in this repository; they are NOT deployed
    to the owner's live PC by this change (the live backend deploy is its own
    pass), so the live apps do not show the editor until that deploy.
  - `edit_vault_note`'s risk row is in the published base, not in a patch
    (2026-11-17): the end-of-file `_RISK.update({...})` block covers the whole
    editor's action. It reaches a live install the way the Android builder's
    rows do - `tools/repair_live_backend_gaps.py` - because a drop-in module
    adds no patch. The tier itself is the shipped "ask" line in both copies of
    `jarvis-framework.toml`, and the row does not change it.
  - `text` is decoded as UTF-8 with replacement characters for invalid bytes
    (a deliberate, stated policy: a note written by another editor in another
    encoding is still readable, and saving it writes valid UTF-8). The
    sha256 is always of the BYTES on disk.
  - The hidden/locked presentation rule is unchanged: this module serves the
    note text; the apps keep their existing Show gate and hidden-list guard
    in front of it, and this module adds no bypass. The chat fast path refuses
    to start any of these writes while the lists are hidden, so no card of its
    own can show a title.

Standard library only. No network, no subprocess, no second permission
mechanism.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

# ---------------------------------------------------------------------------
#   The contract's constants
# ---------------------------------------------------------------------------

#: The gate action one save is asked under. The owner's settings file (both
#: shipped copies) carries `edit_vault_note = "ask"`; the gate forces "ask"
#: for an unclassified action even if that line were removed.
ACTION = "edit_vault_note"

#: The gate action a DELETE is asked under - deliberately NOT `ACTION`. Every
#: other write in this module is reversible, so `edit_vault_note` is an ordinary
#: card. The owner's request of 2026-11-23 is that deleting notes always meets a
#: PERSON, so a delete is its own action with its own row in `jarvis_gate._RISK`
#: ("no"/"local"): the gate then asks Windows Hello on this PC, and the asking
#: phone's own fingerprint or PIN, on every yes, however it arrives. The name is
#: also what the Windows Hello prompt is titled from (`jarvis_card_words`), so
#: an unnamed action could not be approved at all.
DELETE_ACTION = "delete_vault_notes"

#: How many notes ONE delete request may name (the owner's choice, 2026-11-23).
#: The card names every note, so a bigger batch would be a list too long to read
#: before saying yes. More than this is refused in plain words, before any card.
MAX_DELETE = 20

#: The vault's own trash folder. A deleted note is MOVED here - every byte and
#: its relative path kept - which is where Obsidian itself puts a deleted note
#: when the vault's "Deleted files" setting is the local trash folder.
TRASH_DIR = ".trash"

#: The gate action EMPTYING that folder is asked under - deliberately neither of
#: the two above (2026-11-25). `edit_vault_note` says the old text is copied by
#: the File Guardian first, and `delete_vault_notes` says every byte is kept in
#: `.trash`; both of those sentences would be FALSE here. Emptying the trash
#: destroys bytes for good, so it has its own row ("no"/"local") in
#: `jarvis_gate._RISK` and its own card, whose words say so. The row reaches a
#: live install the way every drop-in module's does - the published base plus
#: `tools/repair_live_backend_gaps.py` - never a new patch.
EMPTY_TRASH_ACTION = "empty_vault_trash"

#: How many notes ONE merge request may fold in (the same bound as a delete, for
#: the same reason: the card names every note, and a longer list is not read).
MAX_MERGE = 20

#: When the trash is worth ONE quiet line in a vault-health answer, and never
#: otherwise (the owner's ruling Q6, 2026-11-25). All three are "it has stopped
#: being a handful of mistakes": a size, a count, and an age. Below every one of
#: them this feature says nothing at all, and it never acts.
TRASH_NUDGE_BYTES = 50 * 1024 * 1024
TRASH_NUDGE_FILES = 100
TRASH_NUDGE_DAYS = 90

#: One note may be at most 2 MiB. Bigger is refused BEFORE any card, for a
#: read (413) and for a save (413): a card the owner cannot read is not an
#: approval, and a whole-vault editor is not a file manager.
MAX_FILE_BYTES = 2 * 1024 * 1024
#: A CARD-FREE create is capped far below that (Gemini round-3 ruling 2): a new
#: note is unattended, additive work, so 64 KB of words is the most it writes
#: without a card. Anything larger goes through the carded path.
CARD_FREE_MAX_BYTES = 64 * 1024

#: At most this many notes are returned by one list; `truncated` says more
#: exist. Sorted newest first, so the cut keeps the notes most likely wanted.
MAX_NOTES = 2000

#: At most this many saves may be waiting for a card at once. The refusal
#: names the number in its sentence.
MAX_WAITING = 4

#: Finished jobs kept in memory for `GET ...?id=` (the oldest are dropped).
MAX_JOBS = 50

#: The note suffixes this editor opens. Anything else is not a note here.
TEXT_SUFFIXES = (".md", ".txt")

#: A search string longer than this is cut; the query is a filter, not a
#: payload, and the vault's own size is the real bound.
MAX_QUERY_CHARS = 200

#: Where the routes live. GET /api/notes/save and POST /api/notes/save are the
#: same path by the contract (the POST creates, the GET asks how it ended).
LIST_PATH = "/api/notes/list"
READ_PATH = "/api/notes/read"
SAVE_PATH = "/api/notes/save"
CREATE_PATH = "/api/notes/create"
APPEND_PATH = "/api/notes/append"
TAG_PATH = "/api/notes/tag"
INSERT_PATH = "/api/notes/insert"
FORMAT_PATH = "/api/notes/format"
REPLACE_PATH = "/api/notes/replace"
CUSTOMIZE_PATH = "/api/notes/customize"
TEMPLATES_PATH = "/api/notes/templates"
RENAME_PATH = "/api/notes/rename"
MOVE_PATH = "/api/notes/move"
DELETE_PATH = "/api/notes/delete"
MERGE_PATH = "/api/notes/merge"
COPY_PATH = "/api/notes/copy"
TRASH_PATH = "/api/notes/trash"
CHANGE_PATH = "/api/notes/change"
GET_PATHS = (LIST_PATH, READ_PATH, SAVE_PATH, CHANGE_PATH, TEMPLATES_PATH,
             TRASH_PATH)
POST_PATHS = (SAVE_PATH, CREATE_PATH, APPEND_PATH, TAG_PATH,
              INSERT_PATH, FORMAT_PATH, REPLACE_PATH, CUSTOMIZE_PATH,
              RENAME_PATH, MOVE_PATH, DELETE_PATH, MERGE_PATH, COPY_PATH,
              TRASH_PATH)

#: A tag is one Obsidian tag name without the `#`: letters, digits, `_`, `-`
#: and `/` (nested tags), at least one non-digit, never a space. 64 characters
#: is the bound this module will write.
_TAG_NAME = re.compile(r"[A-Za-z0-9_/-]{1,64}")
_TAG_HAS_WORD = re.compile(r"[A-Za-z_/-]")

#: The words a refused wave-1 write says, in the module's own voice.
_REFUSED_WRITE = {
    "create": {
        "denied": "You said no, so the note was not created.",
        "timed_out": "Nobody answered the approval card in time, so the note was not created.",
        "refused": "The approval gate refused it, so the note was not created.",
    },
    "append": {
        "denied": "You said no, so nothing was added.",
        "timed_out": "Nobody answered the approval card in time, so nothing was added.",
        "refused": "The approval gate refused it, so nothing was added.",
    },
    "append_dated": {
        "denied": "You said no, so nothing was added.",
        "timed_out": "Nobody answered the approval card in time, so nothing was added.",
        "refused": "The approval gate refused it, so nothing was added.",
    },
    "tag": {
        "denied": "You said no, so the note was not tagged.",
        "timed_out": "Nobody answered the approval card in time, so the note was not tagged.",
        "refused": "The approval gate refused it, so the note was not tagged.",
    },
    "insert": {
        "denied": "You said no, so nothing was changed.",
        "timed_out": "Nobody answered the approval card in time, so nothing was changed.",
        "refused": "The approval gate refused it, so nothing was changed.",
    },
    "format": {
        "denied": "You said no, so nothing was changed.",
        "timed_out": "Nobody answered the approval card in time, so nothing was changed.",
        "refused": "The approval gate refused it, so nothing was changed.",
    },
    "replace": {
        "denied": "You said no, so nothing was changed.",
        "timed_out": "Nobody answered the approval card in time, so nothing was changed.",
        "refused": "The approval gate refused it, so nothing was changed.",
    },
    "customize": {
        "denied": "You said no, so nothing was changed.",
        "timed_out": "Nobody answered the approval card in time, so nothing was changed.",
        "refused": "The approval gate refused it, so nothing was changed.",
    },
    "create_template": {
        "denied": "You said no, so the template was not saved.",
        "timed_out": "Nobody answered the approval card in time, so the template was not saved.",
        "refused": "The approval gate refused it, so the template was not saved.",
    },
    "delete": {
        "denied": "You said no, so no note was deleted.",
        "timed_out": "Nobody answered the approval card in time, so no note was deleted.",
        "refused": "The approval gate refused it, so no note was deleted.",
    },
    "merge": {
        "denied": "You said no, so no note was merged and nothing moved.",
        "timed_out": "Nobody answered the approval card in time, so no note was merged and nothing moved.",
        "refused": "The approval gate refused it, so no note was merged and nothing moved.",
    },
    "copy": {
        "denied": "You said no, so no copy was made.",
        "timed_out": "Nobody answered the approval card in time, so no copy was made.",
        "refused": "The approval gate refused it, so no copy was made.",
    },
    "empty_trash": {
        "denied": "You said no, so the vault's trash folder was left exactly as it was.",
        "timed_out": "Nobody answered the approval card in time, so the vault's trash folder was left exactly as it was.",
        "refused": "The approval gate refused it, so the vault's trash folder was left exactly as it was.",
    },
}

#: The one receipts tool name a created note's undo is recorded under. Its
#: restorer is registered at import, so Undo works after a restart too.
CREATE_RECEIPT = "notes_create"

#: How long the POST waits before answering `waiting`. The common Deny/Approve
#: comes back inside this; anything slower is polled through the id.
DEFAULT_WAIT_S = 1.5

#: Windows marks junctions, mount points and symlinks with this attribute on
#: the directory entry. `stat.S_ISLNK` catches symlinks; this catches the
#: junctions a `mklink /J` makes, which are NOT symlinks to `lstat`.
_FILE_ATTRIBUTE_REPARSE_POINT = 0x400

_REFUSED_WORDS = {
    "denied": "You said no, so the note was not changed.",
    "timed_out": ("Nobody answered the approval card in time, so the note was "
                  "not changed."),
    "refused": "The approval gate refused it, so the note was not changed.",
}

_UNCLASSIFIED_NOTE = (  # docs only; the gate decides the card's own line
    "the gate has no risk row for this action yet, so it forces it to ask and "
    "shows its generic worst-case warning")

_lock = threading.Lock()
_jobs: dict = {}            # id -> public job record

# ---------------------------------------------------------------------------
#   Small shared helpers
# ---------------------------------------------------------------------------


def _audit(what: str, detail: dict) -> None:
    """One audit line, never carrying a byte of the note's text."""
    try:
        import jarvis_framework
        jarvis_framework.audit_log("notes." + what, detail)
    except Exception:                                       # noqa: BLE001
        pass


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_link_or_reparse(path) -> bool:
    """True for a symlink OR a Windows junction/mount point at `path`."""
    try:
        st = os.lstat(str(path))
    except OSError:
        return False
    if stat.S_ISLNK(st.st_mode):
        return True
    return bool(getattr(st, "st_file_attributes", 0)
                & _FILE_ATTRIBUTE_REPARSE_POINT)


def _inside(root: Path, path: Path) -> bool:
    """Is `path` inside `root`, after both are resolved? Case-insensitive on
    Windows, the way the filesystem is."""
    try:
        r = os.path.normcase(os.path.realpath(str(root)))
        p = os.path.normcase(os.path.realpath(str(path)))
        return os.path.commonpath([r, p]) == r
    except (OSError, ValueError):
        return False



def _protection():
    """jarvis_protection, or None when that module is not on this backend.

    The "Protected from Jarvis" list (2026-10-31) is a separate drop-in module.
    On a backend that has it, `path_refusal` is the ONE keep-out check every
    door asks before it reads, writes, opens or controls anything; on a backend
    that does not (an older install, or this branch before the list merges) this
    editor behaves exactly as it did before - the feature is absent, never a
    guess. The check is a plain sentence and raises no card.

    Looked up by NAME through importlib rather than with an `import` line: this
    editor merges BEFORE the list does, so this branch's base must not claim a
    module it does not ship - test_base_matches_repo.py's import closure is red
    on `import jarvis_protection` alone. On the assembled tree both shapes find
    the very same module.
    """
    try:
        import importlib
        return importlib.import_module("jarvis_protection")
    except Exception:                                       # noqa: BLE001
        return None


def note_parts(raw) -> tuple:
    """`(parts, "")` for a safe vault-relative note path, or `([], why)`.

    A path is refused here, BEFORE the vault and BEFORE any card, when it is
    not text, is empty, is absolute (a drive letter, a leading slash or a UNC
    path), contains a `..` or `.` component, any component starts with a dot
    (the hidden folders are not part of "the whole vault"), or is not a `.md`
    / `.txt` file. Backslashes are normalised to `/` so a Windows client and
    the phone agree on one path shape.
    """
    if not isinstance(raw, str):
        return [], "the note path was not text"
    text = raw.replace("\\", "/").strip()
    if not text:
        return [], "the note path is empty"
    if "\x00" in text:
        return [], "the note path contains a character a filename cannot hold"
    if re.match(r"^[A-Za-z]:", text) or text.startswith("/") or text.startswith("//"):
        return [], ("the note path is absolute; send a path relative to the "
                    "Obsidian vault")
    parts = [p for p in text.split("/") if p != ""]
    if not parts:
        return [], "the note path is empty"
    for p in parts:
        if p in (".", ".."):
            return [], ("the note path climbs out of the vault; only a path "
                        "inside it can be opened")
        if p.startswith("."):
            return [], "hidden folders and files are not part of the vault editor"
        if ":" in p:
            return [], "the note path contains a character a filename cannot hold"
    if not parts[-1].lower().endswith(TEXT_SUFFIXES):
        return [], "only .md and .txt notes can be opened here"
    return parts, ""


def _vault():
    """`(resolved vault Path or None, why not, in plain words)`.

    The configured vault comes from `jarvis_notes.obsidian_vault()` (the
    owner's `JARVIS_OBSIDIAN_VAULT`, else `[notes.obsidian] vault_directory` in
    jarvis-framework.toml, the setting both this and the vault search already
    use), and `jarvis_notes.vault_problem()` says why it is unusable. A
    missing vault is a 503 naming the setting, never a guess at a folder.
    """
    try:
        import jarvis_notes as N
    except Exception:                                       # noqa: BLE001
        return None, ("the notes module is not on this backend, so the Obsidian "
                      "vault cannot be found")
    try:
        vault = N.obsidian_vault()
        why = N.vault_problem(vault)
    except Exception as exc:                                # noqa: BLE001
        return None, f"the Obsidian vault setting could not be read ({type(exc).__name__})"
    if why:
        return None, why
    return Path(os.path.realpath(str(vault))), ""


def _resolve_note(raw) -> tuple:
    """`(absolute Path, relative path, why)` - why non-empty means refuse.

    Every component under the vault is checked with `lstat` so a symlink or a
    junction ANYWHERE in the path is refused (the contract's rule), and the
    final real path must still be inside the vault. Nothing here reads or
    writes the note.
    """
    parts, why = note_parts(raw)
    if why:
        return None, "", why
    vault, why = _vault()
    if vault is None:
        return None, "", why
    rel = "/".join(parts)
    full = vault.joinpath(*parts)
    cur = vault
    for part in parts:
        cur = cur / part
        if _is_link_or_reparse(cur):
            return None, "", ("the note path goes through a link; links are not "
                              "opened by the vault editor")
    if not _inside(vault, full):
        return None, "", "the note path is outside your Obsidian vault"
    return full, rel, ""


def _read_bytes(full: Path) -> bytes:
    with open(str(full), "rb") as fh:
        return fh.read()


def _stat_note(full: Path):
    """(size, mtime, sha256) for a regular file, or raise OSError."""
    st = os.stat(str(full))
    return st.st_size, st.st_mtime, _sha256(_read_bytes(full))


def _query(raw: str) -> str:
    """The raw query string without a leading `?`, the way urlsplit gives it
    and the way a caller who passes `?path=...` also means it."""
    text = str(raw or "")
    return text[1:] if text.startswith("?") else text


def _error(code: int, message: str, *, state: str = "") -> tuple:
    body = {"ok": False, "error": message}
    if state:
        body["state"] = state
    return code, body


# ---------------------------------------------------------------------------
#   GET /api/notes/list
# ---------------------------------------------------------------------------


def handle_list(query: str = "") -> tuple:
    """Every note in the vault: path, title, size and mtime - never its text."""
    vault, why = _vault()
    if vault is None:
        return _error(503, "No notes list: " + why + ".")
    # "Protected from Jarvis" (2026-10-31): the list is a READ of every note
    # it names, and of the vault folder itself, so it asks before the walk.
    # A blocked vault refuses the whole answer; a blocked note is left out.
    _P = _protection()
    if _P is not None:
        _said = _P.path_refusal(str(vault))
        if _said:
            return _error(403, _said)
    try:
        raw_q = (parse_qs(_query(query)).get("q") or [""])[0]
    except Exception:                                       # noqa: BLE001
        raw_q = ""
    needle = str(raw_q or "")[:MAX_QUERY_CHARS].strip().lower()
    found = []
    try:
        for dirpath, dirnames, filenames in os.walk(str(vault)):
            here = Path(dirpath)
            dirnames[:] = [d for d in sorted(dirnames)
                           if not d.startswith(".")
                           and not _is_link_or_reparse(here / d)
                           # "Protected from Jarvis": a blocked folder inside
                           # the vault is not even listed, let alone walked.
                           and not (_P is not None and _P.blocked_path(here / d))]
            for name in filenames:
                if name.startswith(".") or not name.lower().endswith(TEXT_SUFFIXES):
                    continue
                full = here / name
                if _is_link_or_reparse(full):
                    continue
                if _P is not None and _P.blocked_path(full):
                    continue
                try:
                    st = os.stat(str(full))
                except OSError:
                    continue
                if not stat.S_ISREG(st.st_mode):
                    continue
                try:
                    rel = full.relative_to(vault).as_posix()
                except ValueError:
                    continue
                title = name.rsplit(".", 1)[0]
                if needle and needle not in rel.lower() and needle not in title.lower():
                    continue
                found.append({"path": rel, "title": title,
                              "size": int(st.st_size), "mtime": float(st.st_mtime)})
    except OSError as exc:
        return _error(503, f"The vault could not be read ({type(exc).__name__}).")
    found.sort(key=lambda n: (-n["mtime"], n["path"]))
    truncated = len(found) > MAX_NOTES
    notes = found[:MAX_NOTES]
    return 200, {"ok": True, "root": str(vault), "count": len(notes),
                 "notes": notes, "truncated": bool(truncated)}


# ---------------------------------------------------------------------------
#   GET /api/notes/read
# ---------------------------------------------------------------------------


def handle_read(query: str = "") -> tuple:
    """One note's whole text plus the sha256 of its bytes."""
    try:
        raw = (parse_qs(_query(query)).get("path") or [""])[0]
    except Exception:                                       # noqa: BLE001
        raw = ""
    parts, why = note_parts(raw)
    if why:
        return _error(400, why)
    vault, why = _vault()
    if vault is None:
        return _error(503, "No note was read: " + why + ".")
    full, rel, why = _resolve_note(raw)
    if why:
        return _error(400, why)
    # "Protected from Jarvis": a blocked note is not read; a read-only one is
    # a read and is allowed. The check comes before `_stat_note`/`_read_bytes`.
    _P = _protection()
    if _P is not None:
        _said = _P.path_refusal(str(full))
        if _said:
            return _error(403, _said)
    if not full.is_file():
        return _error(404, f"There is no note at {rel} in your Obsidian vault.")
    try:
        size, mtime, sha = _stat_note(full)
    except OSError as exc:
        return _error(503, f"The note could not be read ({type(exc).__name__}).")
    if size > MAX_FILE_BYTES:
        return _error(413, (f"{rel} is {size} bytes, over the "
                            f"{MAX_FILE_BYTES} byte limit this editor opens; "
                            "open it in Obsidian instead."))
    try:
        data = _read_bytes(full)
    except OSError as exc:
        return _error(503, f"The note could not be read ({type(exc).__name__}).")
    try:
        text = data.decode("utf-8", errors="replace")
    except Exception:                                       # noqa: BLE001
        text = data.decode("utf-8", errors="replace")
    return 200, {"ok": True, "path": rel, "text": text,
                 "sha256": _sha256(data), "size": len(data), "mtime": float(mtime)}


# ---------------------------------------------------------------------------
#   The save: one card, then the write
# ---------------------------------------------------------------------------


def _gate_check(action: str, detail: dict, prompt: str):
    """jarvis_gate.check(), failing CLOSED on any error (note_capture's shape)."""
    class _Refused:
        allowed = False
        outcome = "refused"

        def __init__(self, reason):
            self.reason = reason
    try:
        import jarvis_gate
    except Exception as exc:                                # noqa: BLE001
        return _Refused(f"the approval gate is not available here ({exc})")
    try:
        return jarvis_gate.check(action, detail, prompt=prompt)
    except Exception as exc:                                # noqa: BLE001
        return _Refused(f"the approval gate raised {type(exc).__name__}")


def _snapshot(full: Path, rel: str) -> dict:
    """Save the note's CURRENT bytes through the File Guardian.

    `jarvis_notes.snapshot_vault_before_write` is the vault's one guarded door
    for "the bytes that are about to change": it calls
    `jarvis_file_guardian.snapshot_before_write(...)` with the configured vault
    as the allowed root. Never raises; the caller refuses to write if it did
    not work.
    """
    try:
        import jarvis_notes as N
        return N.snapshot_vault_before_write(
            str(full), reason="notes editor: overwrite before an approved save")
    except Exception as exc:                                # noqa: BLE001
        return {"ok": False, "error": f"the copy of the note could not be saved ({type(exc).__name__})",
                "words": "The copy of the note could not be saved."}


def _write_note(full: Path, data: bytes) -> None:
    """Atomically replace one note's bytes; the mode of the old file is kept."""
    mode = None
    try:
        mode = stat.S_IMODE(os.stat(str(full)).st_mode)
    except OSError:
        mode = None
    fd, tmpname = tempfile.mkstemp(prefix="." + full.name + ".",
                                   suffix=".jarvis-save", dir=str(full.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        if mode is not None:
            try:
                os.chmod(tmpname, mode)
            except OSError:
                pass
        os.replace(tmpname, str(full))
    except Exception:
        try:
            os.unlink(tmpname)
        except OSError:
            pass
        raise


def _finish(job_id: str, **fields) -> None:
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(fields)
            _jobs[job_id]["updated"] = time.time()


def _save_change_words(old_text: str, new_text: str, rel: str) -> tuple:
    """`(prompt, detail)` for a whole-body rewrite - what the card SAYS.

    A card whose whole sentence is "overwrite Shopping.md (412 bytes)" can be
    answered blind, and the owner's rule is that a body change must be visible
    on the card. So the words state the body line count that is going away and
    the first line that differs, before and after. The counts are of the BODY
    (what follows any front matter), because "this replaces 14 lines of the body
    of X" is a fact about the owner's words, not about a `---` block.
    """
    _opened, _front, old_body, _why = _split_frontmatter(str(old_text or ""))
    _opened2, _front2, new_body, _why2 = _split_frontmatter(str(new_text or ""))
    old_lines = _lines(old_body)
    new_lines = _lines(new_body)
    first_old, first_new = "", ""
    for i in range(max(len(old_lines), len(new_lines))):
        one = old_lines[i] if i < len(old_lines) else ""
        two = new_lines[i] if i < len(new_lines) else ""
        if one != two:
            first_old, first_new = _line_body(one), _line_body(two)
            break
    preview = _preview(first_old, first_new, note="the first line that changes")
    detail = {"path": rel, "action": "replace the whole text of a note",
              "lines_before": len(old_lines), "lines_after": len(new_lines),
              "bytes": len(str(new_text or "").encode("utf-8", "surrogatepass")),
              "preview": _card_preview(preview)}
    prompt = (f"replace the body of {rel} in your Obsidian vault: this replaces "
              f"{len(old_lines)} line(s) of the body with {len(new_lines)} line(s)")
    return prompt, detail


def _worker(job_id: str, full: Path, rel: str, data: bytes, expected: str,
            vault: Path, gate_check, preview: dict = None) -> None:
    """Ask the gate, then (and only then) write. Runs on a daemon thread."""
    try:
        if isinstance(preview, dict) and preview.get("prompt"):
            prompt = str(preview["prompt"])
            detail = dict(preview.get("detail") or {})
        else:
            prompt = (f"overwrite {rel} in your Obsidian vault "
                      f"({len(data)} bytes, replacing the note that is there now)")
            detail = {"path": rel, "size": len(data), "vault": str(vault)}
        verdict = gate_check(ACTION, detail, prompt)
        if not getattr(verdict, "allowed", False):
            outcome = str(getattr(verdict, "outcome", "refused") or "refused")
            state = "denied" if outcome in ("denied", "timed_out") else "failed"
            _finish(job_id, state=state, outcome=outcome,
                    message=_REFUSED_WORDS.get(
                        outcome,
                        "The approval gate refused it, so the note was not "
                        "changed: " + str(getattr(verdict, "reason", ""))[:200]))
            _audit("save_refused", {"job": job_id, "path": rel, "outcome": outcome})
            return
        # TOCTOU: another editor may have written while the card waited.
        if not full.is_file():
            _finish(job_id, state="failed",
                    message=(f"{rel} is no longer in your Obsidian vault, so the "
                             "save was not written."))
            _audit("save_failed", {"job": job_id, "path": rel, "why": "gone"})
            return
        try:
            current = _read_bytes(full)
        except OSError as exc:
            _finish(job_id, state="failed",
                    message=(f"The note could not be re-read before writing "
                             f"({type(exc).__name__}), so nothing was changed."))
            _audit("save_failed", {"job": job_id, "path": rel, "why": "reread"})
            return
        current_sha = _sha256(current)
        if current_sha != expected:
            _finish(job_id, state="failed", current_sha256=current_sha,
                    message=(f"{rel} changed while the card waited, so nothing "
                             "was written; open it again and save the new text."))
            _audit("save_failed", {"job": job_id, "path": rel, "why": "moved"})
            return
        snap = _snapshot(full, rel)
        if not snap.get("ok"):
            words = str(snap.get("words") or snap.get("error") or "no copy was made")
            _finish(job_id, state="failed",
                    message=("Nothing was written, because a copy of the note "
                             "could not be saved first: " + words))
            _audit("save_failed", {"job": job_id, "path": rel, "why": "guardian"})
            return
        try:
            _write_note(full, data)
        except OSError as exc:
            _finish(job_id, state="failed",
                    message=(f"The note could not be written "
                             f"({type(exc).__name__}), so it was left as it was."))
            _audit("save_failed", {"job": job_id, "path": rel, "why": "write"})
            return
        new_sha = _sha256(data)
        _finish(job_id, state="saved", sha256=new_sha,
                snapshot=snap.get("snapshot_id") or None,
                message=f"Saved {rel} into your Obsidian vault.")
        _audit("saved", {"job": job_id, "path": rel, "bytes": len(data),
                         "sha256": new_sha})
    except Exception as exc:                                # noqa: BLE001
        _finish(job_id, state="failed",
                message=(f"The save failed ({type(exc).__name__}), so nothing "
                         "was written."))
        _audit("save_failed", {"job": job_id, "path": rel, "why": "exception"})


def handle_save(body, *, gate_check=None, wait_s: float = DEFAULT_WAIT_S,
                by: str = "") -> tuple:
    """POST /api/notes/save: the contract's whole body, one card, one write."""
    if not isinstance(body, dict):
        return _error(400, "Need a JSON object with path, text and expected_sha256.",
                      state="refused")
    raw_path = body.get("path")
    parts, why = note_parts(raw_path)
    if why:
        return _error(400, why, state="refused")
    rel = "/".join(parts)
    vault, why = _vault()
    if vault is None:
        return _error(503, "No note was saved: " + why + ".", state="refused")
    expected = str(body.get("expected_sha256") or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        return _error(400, ("Need expected_sha256: the sha256 of the note when "
                            "this edit started - GET /api/notes/read returns it."),
                      state="refused")
    text = body.get("text")
    if not isinstance(text, str):
        return _error(400, "Need the note's new text as text.", state="refused")
    data = text.encode("utf-8", errors="surrogatepass")
    if len(data) > MAX_FILE_BYTES:
        return _error(413, (f"The new text is {len(data)} bytes, over the "
                            f"{MAX_FILE_BYTES} byte limit this editor saves; "
                            "open the note in Obsidian instead."), state="refused")
    full, rel2, why = _resolve_note(raw_path)
    if why:
        return _error(400, why, state="refused")
    # "Protected from Jarvis" (2026-10-31): a save is a WRITE. Blocked and
    # read-only are both refused, BEFORE the existing bytes are read and
    # before the job/card exists - a keep-out must never raise a card. The
    # File Guardian copy after the card stays as it is (one guarded door;
    # this check is the earlier one, not a duplicate of that copy).
    _P = _protection()
    if _P is not None:
        _said = _P.path_refusal(str(full), write=True)
        if _said:
            return _error(403, _said, state="refused")
    if not full.is_file():
        return _error(404, f"There is no note at {rel2} in your Obsidian vault.",
                      state="refused")
    try:
        current = _read_bytes(full)
    except OSError as exc:
        return _error(503, f"The note could not be read ({type(exc).__name__}).",
                      state="refused")
    current_sha = _sha256(current)
    if current_sha != expected:
        return 409, {"ok": False, "state": "conflict", "path": rel2,
                     "current_sha256": current_sha,
                     "error": (f"{rel2} changed since this edit started, so nothing "
                               "was written; open it again and save the new text.")}
    with _lock:
        waiting = sum(1 for j in _jobs.values() if j.get("state") == "waiting")
        if waiting >= MAX_WAITING:
            return _error(429, (f"{MAX_WAITING} note saves are already waiting for "
                                "approval - answer those cards first, then save "
                                "this one."), state="refused")
        job_id = "notesave_" + secrets.token_hex(8)
        _jobs[job_id] = {
            "id": job_id, "state": "waiting", "path": rel2,
            "sha256": None, "current_sha256": None,
            "message": "Waiting for your approval card.",
            "created": time.time(), "updated": time.time(), "by": by,
        }
        while len(_jobs) > MAX_JOBS:
            oldest = min(_jobs, key=lambda k: _jobs[k]["created"])
            _jobs.pop(oldest, None)
    _card_prompt, _card_detail = _save_change_words(
        current.decode("utf-8", "replace"), text, rel2)
    thread = threading.Thread(
        target=_worker,
        args=(job_id, full, rel2, data, expected, vault,
              gate_check or _gate_check,
              {"prompt": _card_prompt, "detail": _card_detail}),
        name="jarvis-note-save", daemon=True)
    thread.start()
    thread.join(max(0.0, float(wait_s)))
    code, out = save_status(job_id)
    # The contract's POST 202 body carries the job id; the GET body does not.
    if out.get("state") == "waiting":
        out["id"] = job_id
    # The POST's own codes: 202 while the card is up, 200 once it ended.
    return (202 if out.get("state") == "waiting" else 200), out


def save_status(job_id: str) -> tuple:
    """GET /api/notes/save?id=: waiting / saved / denied / failed, never text."""
    jid = str(job_id or "").strip()
    if not jid:
        return _error(400, "Need the id of a note save.", state="refused")
    with _lock:
        job = dict(_jobs.get(jid) or {})
    if not job:
        return _error(404, "There is no note save with that id on this PC.",
                      state="unknown")
    out = {
        "ok": job.get("state") in ("waiting", "saved"),
        "state": job.get("state"),
        "path": job.get("path"),
        "sha256": job.get("sha256"),
        "message": job.get("message") or "",
    }
    if job.get("current_sha256"):
        out["current_sha256"] = job["current_sha256"]
    return 200, out


def handle_save_status(query: str = "") -> tuple:
    """GET /api/notes/save?id=<job id> from the raw query string."""
    try:
        jid = (parse_qs(_query(query)).get("id") or [""])[0]
    except Exception:                                       # noqa: BLE001
        jid = ""
    return save_status(jid)



# ---------------------------------------------------------------------------
#   The wave-1 writes: create ONE note, append to ONE note, tag ONE note
# ---------------------------------------------------------------------------
#
# Each is the save's shape: validate everything BEFORE any card; ask the one
# ordinary card; after the card re-check the disk (TOCTOU); for a change to old
# bytes take the File Guardian copy FIRST; write atomically (or append-only);
# answer with the module's own sentence and "You can undo it." Nothing here
# creates a folder tree, touches `.obsidian`, deletes, renames or moves.


def _write_refusal(kind: str, outcome: str, reason: str = "") -> str:
    words = _REFUSED_WRITE.get(kind, {}).get(
        outcome, "The approval gate refused it, so nothing was written.")
    if reason and outcome not in ("denied", "timed_out"):
        words += " " + str(reason)[:200]
    return words


def _tag_name(raw) -> tuple:
    """`(tag, "")` for a legal Obsidian tag name, or `("", why not)`."""
    text = str(raw or "").strip()
    if text.startswith("#"):
        text = text[1:]
    if not text:
        return "", "the tag is empty"
    if not _TAG_NAME.fullmatch(text):
        return "", ("a tag can use letters, numbers, _ - and / (for nested tags), "
                    "and no spaces")
    if not _TAG_HAS_WORD.search(text):
        return "", "a tag needs at least one letter, _ or - (numbers alone are not a tag)"
    return text, ""


def _split_frontmatter(text: str) -> tuple:
    """`(open_line, front_lines, body, why)`; why non-empty means refuse.

    The front matter exists only when the file starts with a `---` line, and it
    ends at the next `---` line. Everything is kept as the exact lines they
    were, line endings included.
    """
    if not text.startswith("---"):
        return "", [], text, ""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return "", [], text, ""
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            return lines[0], lines[1:idx], "".join(lines[idx + 1:]), ""
    return "", [], text, ("the note's front matter opens with --- and never closes, "
                          "so this editor will not change it")


def _frontmatter_tags(front: list) -> tuple:
    """`(kind, index, values, end, why)` for the tags property, or refuse.

    Only the two shapes Obsidian documents are edited: a list block under
    `tags:` and a one-line flow list `tags: [a, b]`. A scalar `tags: x`, a
    second `tags:` line or an unreadable indented block is refused in words -
    the editor never guesses how to rewrite YAML it does not understand.
    """
    hits = [i for i, line in enumerate(front) if line.strip().startswith("tags:")]
    if not hits:
        return "", -1, [], -1, ""
    if len(hits) > 1:
        return "", -1, [], -1, ("the note has more than one tags: line, so it is not "
                                "changed")
    i = hits[0]
    line = front[i]
    rest = line.split("tags:", 1)[1].strip()
    if rest.startswith("["):
        if not rest.endswith("]") or "]" in rest[:-1]:
            return "", -1, [], -1, "the note's tags line is not a list this editor can read"
        inner = rest[1:-1].strip()
        values = [p.strip().strip('"').strip("'") for p in inner.split(",")] if inner else []
        if any(v == "" for v in values):
            return "", -1, [], -1, "the note's tags line is not a list this editor can read"
        return "flow", i, values, i + 1, ""
    if rest and not rest.startswith("#"):
        return "", -1, [], -1, ("the note's tags value is a single word, not a list; "
                                "change it in Obsidian first")
    values = []
    j = i + 1
    while j < len(front):
        nxt = front[j]
        stripped = nxt.strip()
        if stripped == "":
            break
        if stripped.startswith("-"):
            item_m = re.fullmatch(r"-\s+(.+?)\s*", stripped)
            if not item_m:
                return "", -1, [], -1, ("the note's tags list is not a list this "
                                        "editor can read")
            item = item_m.group(1).strip().strip('"').strip("'")
            if not item:
                return "", -1, [], -1, "the note's tags list has an empty item"
            values.append(item)
            j += 1
            continue
        break
    return "block", i, values, j, ""


def _tag_block_lines(tag: str) -> list:
    return ["  - " + tag + "\n"]


def _edit_frontmatter_tags(text: str, tag: str, action: str) -> tuple:
    """`(new_text, changed, why)` for a frontmatter add/remove; surgical."""
    opened, front, body, why = _split_frontmatter(text)
    if why:
        return text, False, why
    if not opened:
        if action == "remove":
            return text, False, "the note has no tags property to remove it from"
        fm = ["---\n", "tags:\n"] + _tag_block_lines(tag) + ["---\n"]
        return ("".join(fm) + body), True, ""
    kind, idx, values, end, why = _frontmatter_tags(front)
    if why:
        return text, False, why
    lower = [v.casefold() for v in values]
    if action == "add":
        if tag.casefold() in lower:
            return "That note already has #" + tag + ".", False, ""
        if kind == "":
            new_front = list(front) + ["tags:\n"] + _tag_block_lines(tag)
        elif kind == "flow":
            new_front = list(front)
            new_front[idx] = "tags: [" + ", ".join(values + [tag]) + "]\n"
        else:
            new_front = list(front)
            insert = _tag_block_lines(tag)
            new_front[end:end] = insert
        return opened + "".join(new_front) + "---\n" + body, True, ""
    # remove
    if kind == "" or tag.casefold() not in lower:
        return "That note does not have #" + tag + ".", False, ""
    keep = [v for v in values if v.casefold() != tag.casefold()]
    new_front = list(front)
    if kind == "flow":
        if keep:
            new_front[idx] = "tags: [" + ", ".join(keep) + "]\n"
        else:
            new_front[idx] = "tags: []\n"
    else:
        replaced = ["tags:\n"] + [("  - " + v + "\n") for v in keep] if keep else ["tags: []\n"]
        new_front[idx:end] = replaced
    return opened + "".join(new_front) + "---\n" + body, True, ""


def _edit_tag_line(text: str, tag: str, action: str) -> tuple:
    """`(new_text, changed, why)` for a visible `#tag` line; surgical."""
    target = "#" + tag
    lines = text.splitlines(keepends=True)
    hits = [i for i, line in enumerate(lines) if line.strip().casefold() == target.casefold()]
    if action == "add":
        if hits:
            return "That note already has #" + tag + ".", False, ""
        add = target + "\n"
        if text and not text.endswith("\n"):
            add = "\n" + add
        return text + add, True, ""
    if not hits:
        return "That note does not have #" + tag + ".", False, ""
    if len(hits) > 1:
        return text, False, ("that tag appears on more than one line, so this editor "
                             "will not guess which one to remove")
    idx = hits[0]
    new_lines = lines[:idx] + lines[idx + 1:]
    return "".join(new_lines), True, ""


def _new_note_bytes(text: str) -> bytes:
    data = text.encode("utf-8", errors="surrogatepass")
    return data


def _append_block(old: bytes, text: str) -> bytes:
    """The exact bytes an append adds: the note's own paragraph, then a newline."""
    body = text.encode("utf-8", errors="surrogatepass")
    if not old:
        lead = b""
    elif old.endswith(b"\n\n"):
        lead = b""
    elif old.endswith(b"\n"):
        lead = b"\n"
    else:
        lead = b"\n\n"
    return lead + body + b"\n"


#: A date heading a dated append uses - exactly `## YYYY-MM-DD`, which is the
#: shape the owner's own Workout Log note already keeps its days in.
_DATE_HEADING = re.compile(r"^##\s+(?P<day>\d{4}-\d{2}-\d{2})\s*$")
_ANY_HEADING = re.compile(r"^(?P<level>#{1,6})\s+")
_DATE_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _entry_line(text: str, eol: str) -> str:
    """The words as ONE bullet, a second line kept as the bullet's continuation.

    The owner's words are kept verbatim; only the list marker is added (and an
    existing one is not doubled). A newline inside the words becomes an
    indented continuation line so the entry stays one item.
    """
    lines = str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    first = lines[0].strip()
    out = [first if first.startswith(("- ", "* ", "+ ")) else "- " + first]
    for line in lines[1:]:
        if line.strip():
            out.append("  " + line.strip())
    return eol.join(out)


def _dated_entry(old: bytes, text: str, day: str) -> tuple:
    """`(new bytes, insert offset, inserted block, why)` for one dated entry.

    The entry goes under a `## YYYY-MM-DD` heading, "newest last": a heading the
    note already has is used, a newer date gets a new heading after every other
    one, and an older date gets its heading in date order. The result is the
    OLD BYTES with the block inserted at `insert_at` - every existing byte
    stays exactly where it was, so nothing is rewritten. `why` non-empty means
    the request is refused and nothing should be written.
    """
    try:
        text_all = old.decode("utf-8")
    except UnicodeDecodeError:
        return None, 0, b"", ("the note is not valid UTF-8, so this editor will not "
                              "rewrite it")
    if not _DATE_DAY.fullmatch(str(day or "")):
        return None, 0, b"", "the date to file under must be YYYY-MM-DD"
    eol = "\r\n" if "\r\n" in text_all else "\n"
    entry = _entry_line(text, eol)
    lines = text_all.splitlines(keepends=True)
    heads = []
    for idx, line in enumerate(lines):
        stripped = line.rstrip("\r\n")
        m = _ANY_HEADING.match(stripped)
        if not m:
            continue
        dm = _DATE_HEADING.match(stripped)
        heads.append((idx, len(m.group("level")), dm.group("day") if dm else ""))
    date_heads = [(i, lvl, d) for (i, lvl, d) in heads if lvl == 2 and d]
    mine = next((h for h in date_heads if h[2] == day), None)
    if mine is not None:
        idx, _lvl, _d = mine
        # The section runs to the next heading of the same or a higher level.
        stop = len(lines)
        for (j, lvl, _dj) in heads:
            if j > idx and lvl <= 2:
                stop = j
                break
        content = [j for j in range(idx + 1, stop) if lines[j].strip()]
        if content:
            # After the section's last line that has words on it, so an entry
            # never lands between a heading and its own blank line.
            at = content[-1] + 1
            block = ("" if lines[at - 1].endswith(("\n", "\r")) else eol) + entry + eol
        else:
            # An empty section gets one blank line after the heading first.
            at = idx + 1
            after = lines[at] if at < len(lines) else ""
            block = ("" if lines[idx].endswith(("\n", "\r")) else eol)
            block += eol + entry + eol
            if after and after.strip():
                block += eol
        at_chars = len("".join(lines[:at]))
        new_text = "".join(lines[:at]) + block + "".join(lines[at:])
        return new_text.encode("utf-8"), at_chars, block.encode("utf-8"), ""
    # No heading for this day: place the new heading in date order.
    later = [(i, d) for (i, lvl, d) in date_heads if d > day]
    if later:
        idx = later[0][0]
        lead = "" if idx == 0 or not lines[idx - 1].strip() else eol
        block = lead + "## " + day + eol + eol + entry + eol + eol
        at = len("".join(lines[:idx]))
    else:
        at = len(text_all)
        lead = ""
        if text_all and not text_all.endswith(eol):
            lead = eol
        if text_all and not (text_all + lead).endswith(eol + eol):
            lead += eol
        block = lead + "## " + day + eol + eol + entry + eol
    new_text = text_all[:at] + block + text_all[at:]
    return new_text.encode("utf-8"), at, block.encode("utf-8"), ""


def _create_restorer(before) -> None:
    """Undo one created note, from its receipt's before snapshot.

    Deletes the file ONLY when it still holds exactly the bytes the create
    wrote; a note the owner (or Obsidian) changed since is never removed."""
    try:
        rel = str((before or {}).get("path") or "")
        want = str((before or {}).get("created_sha256") or "")
        if not rel or not want:
            return
        full, _rel, why = _resolve_note(rel)
        if why or full is None or not full.is_file():
            return
        if _sha256(_read_bytes(full)) != want:
            return
        os.unlink(str(full))
    except Exception:                                       # noqa: BLE001
        return


def _record_create(rel: str, data: bytes) -> str:
    """One undo receipt for the new note, BEFORE the file exists. "" on failure."""
    try:
        import jarvis_receipts as R
        rid = R.record(
            CREATE_RECEIPT, "created " + rel,
            before={"path": rel, "created_sha256": _sha256(data)},
            after={"path": rel, "sha256": _sha256(data)},
            undo=lambda: _create_restorer({"path": rel,
                                           "created_sha256": _sha256(data)}))
        return str(rid or "")
    except Exception:                                       # noqa: BLE001
        return ""


try:                                            # undo after a restart, by name
    import jarvis_receipts as _RC
    _RC.register_restorer(CREATE_RECEIPT, _create_restorer)
except Exception:                               # noqa: BLE001 - module absent
    pass


def _start_change_job(kind: str, full: Path, rel: str, payload,
                      expected: str, vault: Path, gate_check,
                      wait_s: float, by: str, extra: dict) -> tuple:
    """Register one job and its daemon thread; return the POST's (code, body)."""
    with _lock:
        waiting = sum(1 for j in _jobs.values() if j.get("state") == "waiting")
        if waiting >= MAX_WAITING:
            return _error(429, (f"{MAX_WAITING} note changes are already waiting for "
                                "approval - answer those cards first, then ask "
                                "this one."), state="refused")
        job_id = "note" + kind + "_" + secrets.token_hex(8)
        _jobs[job_id] = {
            "id": job_id, "kind": kind, "state": "waiting", "path": rel,
            "sha256": None, "current_sha256": None,
            "message": "Waiting for your approval card.",
            "created": time.time(), "updated": time.time(), "by": by,
        }
        while len(_jobs) > MAX_JOBS:
            oldest = min(_jobs, key=lambda k: _jobs[k]["created"])
            _jobs.pop(oldest, None)
    thread = threading.Thread(
        target=_change_worker,
        args=(kind, job_id, full, rel, payload, expected, vault,
              gate_check or _gate_check, extra),
        name="jarvis-note-" + kind, daemon=True)
    thread.start()
    thread.join(max(0.0, float(wait_s)))
    code, out = change_status(job_id)
    if out.get("state") == "waiting":
        out["id"] = job_id
    return (202 if out.get("state") == "waiting" else 200), out


def _change_prompt(kind: str, rel: str, payload, extra: dict) -> tuple:
    """(prompt, detail) - the card's own words: the file, what changes, undo.

    The surgical kinds carry the EXACT before/after text (bounded) or, while the
    hidden lists hide the note's words, a counts-only preview instead.
    """
    if kind == "create":
        data = payload
        return (f"create {rel} in your Obsidian vault ({len(data)} bytes)",
                {"path": rel, "bytes": len(data), "action": "create a new note"})
    if kind == "copy":
        source = str(extra.get("source") or "")
        return (f"make a copy of {source} at {rel} in your Obsidian vault",
                {"path": rel, "source": source, "bytes": len(payload or b""),
                 "action": "copy a note"})
    if kind == "append":
        data = payload
        return (f"add {len(data)} bytes to the end of {rel} in your Obsidian vault",
                {"path": rel, "bytes": len(data), "action": "add to the end of a note"})
    if kind == "append_dated":
        day = str(extra.get("day") or "")
        return (f"add a dated entry under ## {day} to {rel} in your Obsidian vault",
                {"path": rel, "date": day, "bytes": len(extra.get("block") or b""),
                 "action": "add a dated entry under a heading"})
    if kind in ("insert", "format", "replace", "customize"):
        words = str(extra.get("card") or "change one part of")
        detail = {"path": rel,
                  "action": str(extra.get("action") or kind),
                  "preview": extra.get("preview") or {}}
        return (f"{words} {rel} in your Obsidian vault", detail)
    if kind == "create_template":
        words = str(extra.get("card") or f"save {rel} as a template in")
        return (f"{words} your Obsidian vault",
                {"path": rel, "bytes": len(payload),
                 "action": "save a note as a template"})
    tag = str(extra.get("tag") or "")
    action = str(extra.get("action") or "add")
    verb = "add the tag #" + tag + " to" if action == "add" else "remove the tag #" + tag + " from"
    return (f"{verb} {rel} in your Obsidian vault",
            {"path": rel, "tag": tag, "action": action + " a tag on a note"})


def _change_worker(kind: str, job_id: str, full: Path, rel: str, payload,
                   expected: str, vault: Path, gate_check, extra: dict) -> None:
    """Ask the card, then (and only then) make the one change. Daemon thread."""
    try:
        prompt, detail = _change_prompt(kind, rel, payload, extra)
        verdict = gate_check(ACTION, detail, prompt)
        if not getattr(verdict, "allowed", False):
            outcome = str(getattr(verdict, "outcome", "refused") or "refused")
            state = "denied" if outcome in ("denied", "timed_out") else "failed"
            _finish(job_id, state=state, outcome=outcome,
                    message=_write_refusal(kind, outcome,
                                           str(getattr(verdict, "reason", ""))))
            _audit(kind + "_refused", {"job": job_id, "path": rel, "outcome": outcome})
            return
        if kind in ("create", "create_template", "copy"):
            _finish_create(job_id, full, rel, payload, kind=kind,
                           source=str(extra.get("source") or ""))
            return
        # append/tag: the note and its bytes must still be what the request saw
        if not full.is_file():
            _finish(job_id, state="failed",
                    message=f"{rel} is no longer in your Obsidian vault, so nothing was changed.")
            _audit(kind + "_failed", {"job": job_id, "path": rel, "why": "gone"})
            return
        try:
            current = _read_bytes(full)
        except OSError as exc:
            _finish(job_id, state="failed",
                    message=f"The note could not be re-read before writing ({type(exc).__name__}), so nothing was changed.")
            _audit(kind + "_failed", {"job": job_id, "path": rel, "why": "reread"})
            return
        current_sha = _sha256(current)
        if current_sha != expected:
            _finish(job_id, state="failed", current_sha256=current_sha,
                    message=(f"{rel} changed while the card waited, so nothing was "
                             "written; open it again and ask again."))
            _audit(kind + "_failed", {"job": job_id, "path": rel, "why": "moved"})
            return
        snap = _snapshot(full, rel)
        if not snap.get("ok"):
            words = str(snap.get("words") or snap.get("error") or "no copy was made")
            _finish(job_id, state="failed",
                    message=("Nothing was written, because a copy of the note could "
                             "not be saved first: " + words))
            _audit(kind + "_failed", {"job": job_id, "path": rel, "why": "guardian"})
            return
        if kind == "append":
            block = payload
            try:
                fd = os.open(str(full), os.O_WRONLY | os.O_APPEND
                             | getattr(os, "O_BINARY", 0))
                try:
                    os.write(fd, block)
                finally:
                    os.close(fd)
                with open(str(full), "rb") as fh:
                    fh.seek(max(0, os.stat(str(full)).st_size - len(block)))
                    landed = fh.read() == block
            except OSError as exc:
                _finish(job_id, state="failed",
                        message=f"The note could not be written ({type(exc).__name__}), so it was left as it was.")
                _audit("append_failed", {"job": job_id, "path": rel, "why": "write"})
                return
            new_data = current + block
            if not landed:
                _finish(job_id, state="failed",
                        message="The words were written but could not be read back, so check the note.")
                _audit("append_failed", {"job": job_id, "path": rel, "why": "readback"})
                return
            _finish(job_id, state="saved", sha256=_sha256(new_data),
                    snapshot=snap.get("snapshot_id") or None,
                    message=f"Added to {rel} in your Obsidian vault. You can undo it.")
            _audit("appended", {"job": job_id, "path": rel, "bytes": len(block)})
            return
        if kind == "append_dated":
            # The bytes were built BEFORE the card from exactly the bytes the
            # sha256 names: the old note with one block inserted. Verify that
            # shape here rather than trusting the payload - then the write
            # adds bytes and cannot change any existing one.
            at = int(extra.get("insert_at") or 0)
            block = extra.get("block") or b""
            new_data = payload
            if (at < 0 or at > len(current)
                    or not isinstance(block, bytes) or not block
                    or len(new_data) != len(current) + len(block)
                    or new_data[:at] != current[:at]
                    or new_data[at + len(block):] != current[at:]):
                _finish(job_id, state="failed",
                        message=("The dated entry could not be added safely, so the "
                                 "note was left exactly as it was."))
                _audit("append_failed", {"job": job_id, "path": rel, "why": "shape"})
                return
            day = str(extra.get("day") or "")
            try:
                if at == len(current):
                    # The block belongs at the very end: a true append, the
                    # same O_APPEND write the plain append route uses.
                    fd = os.open(str(full), os.O_WRONLY | os.O_APPEND
                                 | getattr(os, "O_BINARY", 0))
                    try:
                        os.write(fd, block)
                    finally:
                        os.close(fd)
                    with open(str(full), "rb") as fh:
                        fh.seek(max(0, os.stat(str(full)).st_size - len(block)))
                        landed = fh.read() == block
                else:
                    # A day whose heading is not last: insert the block and keep
                    # every other byte. This is a splice, never a rewrite of the
                    # note's words - the check above proved both sides match.
                    _write_note(full, new_data)
                    landed = _read_bytes(full) == new_data
            except OSError as exc:
                _finish(job_id, state="failed",
                        message=(f"The note could not be written "
                                 f"({type(exc).__name__}), so it was left as it was."))
                _audit("append_failed", {"job": job_id, "path": rel, "why": "write"})
                return
            if not landed:
                _finish(job_id, state="failed",
                        message="The entry was written but could not be read back, so check the note.")
                _audit("append_failed", {"job": job_id, "path": rel, "why": "readback"})
                return
            _finish(job_id, state="saved", sha256=_sha256(new_data),
                    snapshot=snap.get("snapshot_id") or None,
                    message=(f"Added to {rel} under the ## {day} heading in your "
                             "Obsidian vault. You can undo it."))
            _audit("appended", {"job": job_id, "path": rel, "bytes": len(block),
                                "dated": day})
            return
        # tag / insert / format / replace: the new text was worked out before
        # the card, from the same bytes the sha256 named; write it atomically.
        new_data = payload
        try:
            _write_note(full, new_data)
        except OSError as exc:
            _finish(job_id, state="failed",
                    message=f"The note could not be written ({type(exc).__name__}), so it was left as it was.")
            _audit(kind + "_failed", {"job": job_id, "path": rel, "why": "write"})
            return
        if kind == "tag":
            tag = str(extra.get("tag") or "")
            said = ("Tagged " + rel + " with #" + tag + "." if extra.get("action") == "add"
                    else "Removed the tag #" + tag + " from " + rel + ".")
        else:
            said = str(extra.get("said") or ("Changed " + rel + "."))
        _finish(job_id, state="saved", sha256=_sha256(new_data),
                snapshot=snap.get("snapshot_id") or None,
                message=said + " You can undo it.")
        _audit(kind + "ed", {"job": job_id, "path": rel,
                             "action": extra.get("action")})
    except Exception as exc:                                # noqa: BLE001
        _finish(job_id, state="failed",
                message=f"The change failed ({type(exc).__name__}), so nothing was written.")
        _audit(kind + "_failed", {"job": job_id, "path": rel, "why": "exception"})


def _finish_create(job_id: str, full: Path, rel: str, data: bytes,
                   kind: str = "create", source: str = "") -> None:
    """The new note (or template): receipt first, one O_EXCL file, read back."""
    if full.exists():
        _finish(job_id, state="failed", code="content_preexists",
                message=f"There is already a note at {rel}, so nothing was created.")
        _audit("create_failed", {"job": job_id, "path": rel, "why": "exists"})
        return
    parent_real = Path(os.path.realpath(str(full.parent)))
    vault, _why = _vault()
    if vault is None or not _inside(vault, parent_real) or not _inside(vault, full):
        _finish(job_id, state="failed",
                message="That note's folder is not inside your Obsidian vault, so nothing was created.")
        _audit("create_failed", {"job": job_id, "path": rel, "why": "outside"})
        return
    rid = _record_create(rel, data)
    if not rid:
        _finish(job_id, state="failed",
                message=("Nothing was created, because an undo receipt could not be "
                         "recorded first."))
        _audit("create_failed", {"job": job_id, "path": rel, "why": "receipt"})
        return
    try:
        full.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(full), os.O_WRONLY | os.O_CREAT | os.O_EXCL
                     | getattr(os, "O_BINARY", 0), 0o644)
        try:
            os.write(fd, data)
        finally:
            os.close(fd)
        with open(str(full), "rb") as fh:
            landed = fh.read() == data
    except FileExistsError:
        _finish(job_id, state="failed", code="content_preexists",
                message=f"There is already a note at {rel}, so nothing was created.")
        try:
            import jarvis_receipts as R
            R.discard(rid)
        except Exception:                               # noqa: BLE001
            pass
        _audit("create_failed", {"job": job_id, "path": rel, "why": "exists"})
        return
    except OSError as exc:
        try:
            import jarvis_receipts as R
            R.discard(rid)
        except Exception:                               # noqa: BLE001
            pass
        _finish(job_id, state="failed",
                message=f"The note could not be created ({type(exc).__name__}), so nothing was created.")
        _audit("create_failed", {"job": job_id, "path": rel, "why": "write"})
        return
    if not landed:
        _finish(job_id, state="failed",
                message="The note was made but could not be read back, so check Obsidian.")
        _audit("create_failed", {"job": job_id, "path": rel, "why": "readback"})
        return
    if kind == "create_template":
        said = (f"Saved {source or 'the note'} as the template {rel} in your "
                "Obsidian vault.")
    else:
        said = f"Created {rel} in your Obsidian vault."
    _finish(job_id, state="saved", sha256=_sha256(data), receipt=rid,
            message=said + " You can undo it.")
    _audit("created", {"job": job_id, "path": rel, "bytes": len(data),
                       "sha256": _sha256(data)})


def _create_now(full: Path, rel: str, data: bytes) -> tuple:
    """Create ONE new note with NO approval card (owner's decision 2026-10-31:
    "jarvis should be able to make a new note into my notes without needing an
    approval card").

    Creating a brand-new file is ADDITIVE: it cannot overwrite or delete any
    existing content, which is why the owner's one-card rule for changes does
    not apply to it. Everything that still applies does: the path is inside the
    vault, a collision is refused (never overwritten, and the O_EXCL open is a
    second guard), the undo receipt is recorded BEFORE the file exists so one
    Undo removes exactly the new file, and the bytes are read back. The File
    Guardian copy is not needed for a brand-new path (there are no old bytes to
    keep) - the receipt is what makes the undo exact.

    Returns the same `(status, body)` shape the routes use, so every caller sees
    the module's own words.
    """
    import jarvis_receipts as R
    # Gemini round-3 ruling 2: the card-free payload is capped at 64 KB. A
    # bigger note is a bigger change than an unattended write should be.
    if len(data) > CARD_FREE_MAX_BYTES:
        return 413, {"ok": False, "state": "refused", "path": rel,
                     "error": (f"A brand-new note is capped at {CARD_FREE_MAX_BYTES} "
                               f"bytes here and that one is {len(data)} bytes, so "
                               "nothing was created; use the notes editor for a "
                               "bigger note.")}
    if full.exists():
        return 409, {"ok": False, "state": "exists", "code": "content_preexists",
                     "path": rel,
                     "error": f"There is already a note at {rel}, so nothing was created."}
    # On Windows a name is case-insensitive: "gym.md" and "Gym.md" are the SAME
    # note, but a case-sensitive filesystem would let a second one appear. Look
    # for a name-equal sibling before the O_EXCL write either way (ruling 2).
    try:
        key = full.name.casefold()
        parent = full.parent
        if parent.is_dir():
            for sibling in parent.iterdir():
                if sibling.name.casefold() == key:
                    sib_rel = (((rel.rsplit("/", 1)[0] + "/") if "/" in rel else "")
                               + sibling.name)
                    return 409, {"ok": False, "state": "exists",
                                 "code": "case_variant_exists", "path": rel,
                                 "candidates": [{"path": sib_rel,
                                                 "title": sibling.stem}],
                                 "error": (f"There is already a note at {sibling.name} "
                                           f"(same name, different case) so nothing "
                                           "was created.")}
    except OSError:
        pass
    try:
        vault, _why = _vault()
        parent_real = Path(os.path.realpath(str(full.parent)))
        if (vault is None or not _inside(vault, parent_real)
                or not _inside(vault, full)):
            return 403, {"ok": False, "state": "refused", "path": rel,
                         "error": ("That note's folder is not inside your Obsidian "
                                   "vault, so nothing was created.")}
    except Exception as exc:                                # noqa: BLE001
        return 503, {"ok": False, "state": "refused", "path": rel,
                     "error": (f"The note could not be created "
                               f"({type(exc).__name__}), so nothing was created.")}
    rid = _record_create(rel, data)
    if not rid:
        return 503, {"ok": False, "state": "refused", "path": rel,
                     "error": ("Nothing was created, because an undo receipt "
                               "could not be recorded first.")}
    try:
        full.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(full), os.O_WRONLY | os.O_CREAT | os.O_EXCL
                     | getattr(os, "O_BINARY", 0), 0o644)
        try:
            os.write(fd, data)
        finally:
            os.close(fd)
        with open(str(full), "rb") as fh:
            landed = fh.read() == data
    except FileExistsError:
        try:
            R.discard(rid)
        except Exception:                                   # noqa: BLE001
            pass
        return 409, {"ok": False, "state": "exists", "code": "content_preexists",
                     "path": rel,
                     "error": f"There is already a note at {rel}, so nothing was created."}
    except OSError as exc:
        try:
            R.discard(rid)
        except Exception:                                   # noqa: BLE001
            pass
        return 503, {"ok": False, "state": "refused", "path": rel,
                     "error": (f"The note could not be created "
                               f"({type(exc).__name__}), so nothing was created.")}
    if not landed:
        try:
            R.discard(rid)
        except Exception:                                   # noqa: BLE001
            pass
        return 503, {"ok": False, "state": "refused", "path": rel,
                     "error": ("The note was made but could not be read back, so "
                               "check Obsidian.")}
    _audit("created", {"path": rel, "bytes": len(data), "sha256": _sha256(data),
                       "card": False})
    return 200, {"ok": True, "state": "created", "path": rel,
                 "sha256": _sha256(data), "receipt": rid,
                 "message": f"Created {rel} in your Obsidian vault. You can undo it."}


def _one_path(body) -> tuple:
    """`(raw_path, why)`: ONE path string, or a plain refusal for a list."""
    if not isinstance(body, dict):
        return "", "Need a JSON object with one note path."
    raw = body.get("path")
    if isinstance(raw, (list, tuple)):
        return "", ("One note at a time, please: this route names one file, and a "
                    "list was sent so nothing was changed.")
    return raw, ""


def handle_create(body, *, gate_check=None, wait_s: float = DEFAULT_WAIT_S,
                  by: str = "", provenance: str = "typed",
                  client: str = "hud") -> tuple:
    """POST /api/notes/create: exactly one new note, ONE card unless owner-direct.

    Gemini round-3 ruling 2 (2026-10-31): card-free is allowed ONLY for a
    direct owner write - provenance "typed" or "voice" AND the HUD client. A
    write after outside text (`after_outside_text`), a background job, or any
    other client keeps the old ONE-card path. A brand-new note is still
    additive: the vault/protected/hidden/reserved/collision checks and the undo
    receipt are unchanged, and every OTHER note change keeps its card.
    """
    raw, why = _one_path(body)
    if why:
        return _error(400, why, state="refused")
    parts, why = note_parts(raw)
    if why:
        return _error(400, why, state="refused")
    rel = "/".join(parts)
    vault, why = _vault()
    if vault is None:
        return _error(503, "No note was created: " + why + ".", state="refused")
    text = body.get("text", "")
    if text is None:
        text = ""
    if not isinstance(text, str):
        return _error(400, "Need the new note's text as text.", state="refused")
    data = _new_note_bytes(text)
    if len(data) > MAX_FILE_BYTES:
        return _error(413, (f"The new note is {len(data)} bytes, over the "
                            f"{MAX_FILE_BYTES} byte limit this editor writes; open it "
                            "in Obsidian instead."), state="refused")
    full, rel2, why = _resolve_note(raw)
    if why:
        return _error(400, why, state="refused")
    _P = _protection()
    if _P is not None:
        _said = _P.path_refusal(str(full), write=True)
        if _said:
            return _error(403, _said, state="refused")
    # THE VOCABULARY AND THE TWO OPTIONS live in the ONE resolver
    # (`jarvis_notes.create_target`): `content_preexists`,
    # `case_variant_exists`, `ambiguous_section`, and the booleans
    # `create_target_if_missing` / `reject_if_content_preexists`. Their defaults
    # keep this route's behaviour exactly as it was; the checks below stay as
    # the final guard against a race.
    try:
        import jarvis_notes as N
        target = N.create_target(
            rel2,
            create_target_if_missing=bool(body.get("create_target_if_missing", True)),
            reject_if_content_preexists=bool(
                body.get("reject_if_content_preexists", True)))
    except Exception:                       # noqa: BLE001 - module absent
        target = None
    if isinstance(target, dict) and not target.get("ok"):
        code = str(target.get("code") or "")
        if code in ("content_preexists", "case_variant_exists"):
            return 409, {"ok": False, "state": "exists", "code": code,
                         "path": str(target.get("path") or rel2),
                         "candidates": list(target.get("candidates") or []),
                         "error": str(target.get("reason") or "")}
        if code == "ambiguous_section":
            return 409, {"ok": False, "state": "ambiguous", "code": code,
                         "candidates": list(target.get("candidates") or []),
                         "error": str(target.get("reason") or "")}
        if code == "not_found":
            return 400, {"ok": False, "state": "refused", "code": code,
                         "error": (str(target.get("reason") or "")
                                   + " This request asked not to create a note "
                                     "that is not there.")}
    if full.exists():
        return 409, {"ok": False, "state": "exists", "code": "content_preexists",
                     "path": rel2,
                     "error": f"There is already a note at {rel2}, so nothing was created."}
    # OWNER DECISION 2026-10-31: creating a brand-new note is card-free - but
    # ONLY when the owner is writing directly in the HUD (typed or voice).
    # After outside text, a background job, or another client, the ONE-card
    # path stays (Gemini round-3 ruling 2).
    body_prov = str((body or {}).get("provenance") or provenance or "typed").strip().lower()
    body_client = str((body or {}).get("client") or client or "").strip().lower()
    owner_direct = body_prov in ("typed", "voice") and body_client == "hud"
    if not owner_direct:
        return _start_change_job("create", full, rel2, data, "", vault,
                                 gate_check, wait_s, by,
                                 {"provenance": body_prov, "client": body_client})
    return _create_now(full, rel2, data)


def handle_append(body, *, gate_check=None, wait_s: float = DEFAULT_WAIT_S,
                  by: str = "") -> tuple:
    """POST /api/notes/append: add words to the END of one existing note."""
    raw, why = _one_path(body)
    if why:
        return _error(400, why, state="refused")
    parts, why = note_parts(raw)
    if why:
        return _error(400, why, state="refused")
    rel = "/".join(parts)
    vault, why = _vault()
    if vault is None:
        return _error(503, "Nothing was added: " + why + ".", state="refused")
    text = body.get("text")
    if not isinstance(text, str) or not text.strip():
        return _error(400, "Need the words to add as text.", state="refused")
    expected = str(body.get("expected_sha256") or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        return _error(400, ("Need expected_sha256: the sha256 of the note when this "
                            "started - GET /api/notes/read returns it."), state="refused")
    full, rel2, why = _resolve_note(raw)
    if why:
        return _error(400, why, state="refused")
    _P = _protection()
    if _P is not None:
        _said = _P.path_refusal(str(full), write=True)
        if _said:
            return _error(403, _said, state="refused")
    if not full.is_file():
        return _error(404, f"There is no note at {rel2} in your Obsidian vault; "
                           "create it first.", state="refused")
    try:
        current = _read_bytes(full)
    except OSError as exc:
        return _error(503, f"The note could not be read ({type(exc).__name__}).",
                      state="refused")
    current_sha = _sha256(current)
    if current_sha != expected:
        return 409, {"ok": False, "state": "conflict", "path": rel2,
                     "current_sha256": current_sha,
                     "error": (f"{rel2} changed since this started, so nothing was "
                               "added; open it again and ask again.")}
    if len(current) > MAX_FILE_BYTES:
        return _error(413, (f"{rel2} is {len(current)} bytes, over the "
                            f"{MAX_FILE_BYTES} byte limit this editor writes; open it "
                            "in Obsidian instead."), state="refused")
    dated = str(body.get("dated") or body.get("day") or "").strip()
    if dated:
        # A DATED entry (2026-11-16): the words go under a `## YYYY-MM-DD`
        # heading, newest last, creating that heading when the note has none.
        # Same ONE card, same File Guardian copy, same sha guard; the write
        # only ever adds bytes at one offset.
        if not _DATE_DAY.fullmatch(dated):
            return _error(400, "dated must be a YYYY-MM-DD date.", state="refused")
        new_data, at, the_block, why = _dated_entry(current, text, dated)
        if why:
            return _error(400, why + " Nothing was added.", state="refused")
        if len(new_data) > MAX_FILE_BYTES:
            return _error(413, (f"Adding those words would make {rel2} over the "
                                f"{MAX_FILE_BYTES} byte limit, so nothing was added."),
                          state="refused")
        return _start_change_job("append_dated", full, rel2, new_data, expected,
                                 vault, gate_check, wait_s, by,
                                 {"day": dated, "insert_at": at,
                                  "block": the_block})
    block = _append_block(current, text)
    if len(current) + len(block) > MAX_FILE_BYTES:
        return _error(413, (f"Adding those words would make {rel2} over the "
                            f"{MAX_FILE_BYTES} byte limit, so nothing was added."),
                      state="refused")
    return _start_change_job("append", full, rel2, block, expected, vault,
                             gate_check, wait_s, by, {})


def handle_tag(body, *, gate_check=None, wait_s: float = DEFAULT_WAIT_S,
               by: str = "") -> tuple:
    """POST /api/notes/tag: add or remove ONE tag on ONE note, surgically."""
    raw, why = _one_path(body)
    if why:
        return _error(400, why, state="refused")
    parts, why = note_parts(raw)
    if why:
        return _error(400, why, state="refused")
    rel = "/".join(parts)
    vault, why = _vault()
    if vault is None:
        return _error(503, "No tag was changed: " + why + ".", state="refused")
    action = str(body.get("action") or "add").strip().lower()
    if action not in ("add", "remove"):
        return _error(400, "action must be add or remove.", state="refused")
    tag, why = _tag_name(body.get("tag"))
    if why:
        return _error(400, why, state="refused")
    where = str(body.get("where") or "auto").strip().lower()
    if where not in ("auto", "frontmatter", "line"):
        return _error(400, "where must be auto, frontmatter or line.", state="refused")
    expected = str(body.get("expected_sha256") or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        return _error(400, ("Need expected_sha256: the sha256 of the note when this "
                            "started - GET /api/notes/read returns it."), state="refused")
    full, rel2, why = _resolve_note(raw)
    if why:
        return _error(400, why, state="refused")
    _P = _protection()
    if _P is not None:
        _said = _P.path_refusal(str(full), write=True)
        if _said:
            return _error(403, _said, state="refused")
    if not full.is_file():
        return _error(404, f"There is no note at {rel2} in your Obsidian vault.",
                      state="refused")
    try:
        old = _read_bytes(full)
    except OSError as exc:
        return _error(503, f"The note could not be read ({type(exc).__name__}).",
                      state="refused")
    current_sha = _sha256(old)
    if current_sha != expected:
        return 409, {"ok": False, "state": "conflict", "path": rel2,
                     "current_sha256": current_sha,
                     "error": (f"{rel2} changed since this started, so no tag was "
                               "changed; open it again and ask again.")}
    try:
        text = old.decode("utf-8")
    except UnicodeDecodeError:
        return _error(400, (f"{rel2} is not valid UTF-8, so this editor will not rewrite "
                            "it; change the tag in Obsidian."), state="refused")
    if where == "frontmatter":
        changed, ok, why = _edit_frontmatter_tags(text, tag, action)
    elif where == "line":
        changed, ok, why = _edit_tag_line(text, tag, action)
    else:
        opened, _front, _body, fm_why = _split_frontmatter(text)
        if fm_why:
            return _error(400, fm_why, state="refused")
        if opened:
            changed, ok, why = _edit_frontmatter_tags(text, tag, action)
        else:
            changed, ok, why = _edit_tag_line(text, tag, action)
    if why:
        return _error(400, why, state="refused")
    if not ok:
        return 200, {"ok": True, "state": "unchanged", "path": rel2,
                     "sha256": current_sha, "message": changed}
    new_data = changed.encode("utf-8", errors="surrogatepass")
    if len(new_data) > MAX_FILE_BYTES:
        return _error(413, (f"The tagged note would be {len(new_data)} bytes, over the "
                            f"{MAX_FILE_BYTES} byte limit, so nothing was changed."),
                      state="refused")
    return _start_change_job("tag", full, rel2, new_data, expected, vault,
                             gate_check, wait_s, by,
                             {"tag": tag, "action": action, "where": where})


# ---------------------------------------------------------------------------
#   Wave 2 - surgical edits: under a heading, before/after an anchor, wrap
#   bold/italic, and replace exactly once. Every one is pure text work on the
#   bytes the request read; the card shows the exact before/after (or counts
#   only while the hidden lists hide the words); the write is one card, one
#   File Guardian copy, one atomic write, one Undo.
# ---------------------------------------------------------------------------

MAX_PREVIEW_CHARS = 260
_WORD = re.compile(r"[A-Za-z0-9_]")


def _eol_of(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def _lines(text: str) -> list:
    return text.splitlines(keepends=True)


def _line_body(line: str) -> str:
    return line.rstrip("\r\n")


def _heading_at(line: str):
    """`(level, title)` for a markdown heading line, or None."""
    m = re.match(r"^(#{1,6})[ \t]+(.*?)[ \t]*#*[ \t]*$", _line_body(line))
    if not m:
        return None
    return len(m.group(1)), m.group(2).strip()


def _split_clip(words: str) -> str:
    one = " ".join(str(words or "").split())
    return one[:MAX_PREVIEW_CHARS] + ("..." if len(one) > MAX_PREVIEW_CHARS else "")


def _preview(before: str, after: str, note: str = "") -> dict:
    out = {"before": _split_clip(before), "after": _split_clip(after)}
    if note:
        out["note"] = _split_clip(note)
    return out


def _hidden_lists() -> bool:
    """True while the backend's hidden-lists / App-lock hook says words hide."""
    try:
        import importlib
        PV = importlib.import_module("jarvis_private_view")
        state = PV.effective()
        return bool(state.get("app_locked") or state.get("hide_memory_lists"))
    except Exception:                                       # noqa: BLE001
        return False


def _card_preview(preview: dict) -> dict:
    """The card's preview, or counts-only while the hidden lists hide words."""
    if _hidden_lists():
        return {"counts_only": True, "changes": 1,
                "why": "the lists are hidden, so the words are not shown"}
    return preview


def _insert_lines(new_text: str, eol: str) -> list:
    parts = str(new_text).splitlines() or [str(new_text)]
    return [p + eol for p in parts]


def _insert_under_heading(text: str, target: str, new_text: str):
    """`(new_text, heading_title, preview, why)` for one exact heading."""
    want = str(target or "").strip().lstrip("#").strip()
    if not want:
        return text, "", {}, "which heading?"
    eol = _eol_of(text)
    lines = _lines(text)
    found = []
    for i, line in enumerate(lines):
        h = _heading_at(line)
        if h and h[1].casefold() == want.casefold():
            found.append((i, h[0], h[1]))
    if not found:
        return text, "", {}, f'There is no "{want}" heading in this note, so nothing was changed.'
    if len(found) > 1:
        return text, "", {}, (f'There are {len(found)} "{want}" headings in this note, '
                              'so nothing was changed - name one of them.')
    idx, level, title = found[0]
    end = len(lines)
    for j in range(idx + 1, len(lines)):
        h = _heading_at(lines[j])
        if h and h[0] <= level:
            end = j
            break
    last_nonempty = idx
    for j in range(idx + 1, end):
        if _line_body(lines[j]).strip():
            last_nonempty = j
    at = last_nonempty + 1
    insert = _insert_lines(new_text, eol)
    new_lines = lines[:at] + insert + lines[at:]
    before = _line_body(lines[last_nonempty])
    after = _line_body(insert[0])
    preview = _preview(before, after, note="under the \"" + title + "\" heading")
    return "".join(new_lines), title, preview, ""


def _insert_at_anchor(text: str, anchor: str, mode: str, new_text: str):
    """`(new_text, preview, why)` - one literal anchor, its own bytes untouched."""
    want = str(anchor or "").strip().strip('"').strip("'")
    if not want:
        return text, {}, "which words should the new line go before or after?"
    count = len(re.findall(re.escape(want), text, re.IGNORECASE))
    if count == 0:
        return text, {}, f'I could not find "{want}" in this note, so nothing was changed.'
    if count > 1:
        return text, {}, (f'"{want}" appears {count} times in this note, so nothing '
                          "was changed - give words that appear once.")
    eol = _eol_of(text)
    off = text.lower().find(want.lower())
    line_start = text.rfind("\n", 0, off) + 1
    line_end = text.find("\n", off)
    if line_end < 0:
        line_end = len(text)
    line_body = text[line_start:line_end]
    insert = _insert_lines(new_text, eol)
    if mode == "before":
        at = line_start
        before = line_body
        after = _line_body(insert[0])
        preview = _preview(before, after, note="before \"" + want + "\"")
    else:
        before = line_body
        after = _line_body(insert[0])
        preview = _preview(before, after, note="after \"" + want + "\"")
        if line_end >= len(text):
            # the anchor is the last line and the file has no final newline:
            # start the new line with one, so the anchor's own bytes are kept
            at = len(text)
            joined = eol + "".join(insert)
            return text[:at] + joined, preview, ""
        at = line_end + 1
    new_lines = text[:at] + "".join(insert) + text[at:]
    return new_lines, preview, ""


def _insert_at_top(text: str, new_text: str):
    """`(new_text, preview, why)` - the line at the TOP of the note's own words.

    "add this to the top of my Shopping note" is a POSITION, not a heading. The
    new line goes above the first body line and below any front matter, so a
    note with properties keeps them where Obsidian expects them. A note with no
    body at all gets the line as its first line.
    """
    opened, front, body, why = _split_frontmatter(text)
    if why:
        return text, {}, why
    eol = _eol_of(text)
    insert = "".join(_insert_lines(new_text, eol))
    head = (opened + "".join(front) + "---" + eol) if opened else ""
    first = body.splitlines()[0] if body else ""
    preview = _preview(first, _line_body(insert), note="the top of the note")
    return head + insert + body, preview, ""


def _fence_ranges(text: str) -> list:
    """`[(start, end)]` character ranges of fenced code blocks (``` or ~~~)."""
    ranges = []
    pos = 0
    open_at = None
    for line in _lines(text):
        body = _line_body(line).strip()
        if body.startswith("```") or body.startswith("~~~"):
            if open_at is None:
                open_at = pos
            else:
                ranges.append((open_at, pos + len(line)))
                open_at = None
        pos += len(line)
    if open_at is not None:
        ranges.append((open_at, len(text)))
    return ranges


def _format_span(text: str, target: str, style: str, action: str):
    """`(new_text, said, preview, why)` - wrap/unwrap ONE exact span."""
    want = str(target or "").strip().strip('"').strip("'")
    if not want:
        return text, "", {}, "which words should be formatted?"
    count = len(re.findall(re.escape(want), text, re.IGNORECASE))
    if count == 0:
        return text, "", {}, f'I could not find "{_split_clip(want)}" in this note, so nothing was changed.'
    if count > 1:
        return text, "", {}, (f'"{_split_clip(want)}" appears {count} times in this note, so '
                              "nothing was changed - give words that appear once.")
    start = text.lower().find(want.lower())
    found = text[start:start + len(want)]
    end = start + len(found)
    for a, b in _fence_ranges(text):
        if a <= start < b:
            return text, "", {}, ("that text is inside a code block, and formatting is "
                                  "not changed there")
    _MARKERS = {"bold": "**", "italic": "*", "strike": "~~", "code": "`"}
    marker = _MARKERS.get(style, "")
    if not marker:
        return text, "", {}, "style must be bold, italic, strike or code"
    before = text[max(0, start - len(marker)):start]
    after = text[end:end + len(marker)]
    wrapped = (before == marker and after == marker)
    if style == "italic" and (text[max(0, start - 2):start] == "**"
                              or text[end:end + 2] == "**") and action == "add":
        # bold and italic TOGETHER is standard Markdown: ***text***
        left_italic = (text[start - 1:start] == "*"
                       and text[max(0, start - 2):start] != "**")
        right_italic = (text[end:end + 1] == "*" and text[end:end + 2] != "**")
        if left_italic or right_italic:
            return text, "That text is already italic.", {}, ""
        new = text[:start] + "*" + found + "*" + text[end:]
        return new, "", _preview("***" + want + "***", "***" + want + "***",
                                 note="the span, italic"), ""
    if action == "add":
        if wrapped:
            return text, f"That text is already {style}.", {}, ""
        if text[start - 1:start] == "*" or text[end:end + 1] == "*":
            return text, "That text is already inside asterisks, so nothing was changed.", {}, ""
        new = text[:start] + marker + found + marker + text[end:]
        preview = _preview(marker + want + marker,
                           marker + want + marker,
                           note="the span, " + style)
        return new, "", preview, ""
    # remove: unwrap exactly one matching pair of this style
    if text[start - len(marker):start] != marker or text[end:end + len(marker)] != marker:
        return text, f"That text is not {style}.", {}, ""
    new = text[:start - len(marker)] + want + text[end + len(marker):]
    preview = _preview(marker + want + marker, want, note="the span")
    return new, "", preview, ""


def _replace_once(text: str, old: str, new: str):
    """`(new_text, preview, why)` - one literal occurrence, whole-word edge."""
    old_s = str(old or "")
    if not old_s:
        return text, {}, "what should be replaced?"
    old_l = old_s.lower()
    count = len(re.findall(re.escape(old_s), text, re.IGNORECASE))
    if count == 0:
        return text, {}, f'I could not find "{_split_clip(old_s)}" in this note, so nothing was changed.'
    if count > 1:
        return text, {}, (f'"{_split_clip(old_s)}" appears {count} times in this note, so '
                          "nothing was changed - give words that appear once.")
    start = text.lower().find(old_l)
    found = text[start:start + len(old_s)]
    end = start + len(found)
    if _WORD.match(found[0]) and start > 0 and _WORD.match(text[start - 1]):
        return text, {}, ("that is part of a longer word, so nothing was changed - give "
                          "the whole word")
    if _WORD.match(found[-1]) and end < len(text) and _WORD.match(text[end]):
        return text, {}, ("that is part of a longer word, so nothing was changed - give "
                          "the whole word")
    new_text = text[:start] + str(new) + text[end:]
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    if line_end < 0:
        line_end = len(text)
    before_line = text[line_start:line_end]
    new_line_start = new_text.rfind("\n", 0, start) + 1
    new_line_end = new_text.find("\n", start)
    if new_line_end < 0:
        new_line_end = len(new_text)
    after_line = new_text[new_line_start:new_line_end]
    return new_text, _preview(before_line, after_line, note="the line"), ""


def _surgical_common(body, kind: str, gate_check, wait_s: float, by: str):
    """`(code, out, full, rel, text, sha)` or an error tuple."""
    raw, why = _one_path(body)
    if why:
        return (_error(400, why, state="refused"),) + (None,) * 5
    parts, why = note_parts(raw)
    if why:
        return (_error(400, why, state="refused"),) + (None,) * 5
    vault, why = _vault()
    if vault is None:
        return (_error(503, "Nothing was changed: " + why + ".", state="refused"),) + (None,) * 5
    expected = str(body.get("expected_sha256") or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        return (_error(400, ("Need expected_sha256: the sha256 of the note when this "
                             "started - GET /api/notes/read returns it."),
                       state="refused"),) + (None,) * 5
    full, rel, why = _resolve_note(raw)
    if why:
        return (_error(400, why, state="refused"),) + (None,) * 5
    _P = _protection()
    if _P is not None:
        _said = _P.path_refusal(str(full), write=True)
        if _said:
            return (_error(403, _said, state="refused"),) + (None,) * 5
    if not full.is_file():
        return (_error(404, f"There is no note at {rel} in your Obsidian vault.",
                       state="refused"),) + (None,) * 5
    try:
        old = _read_bytes(full)
    except OSError as exc:
        return (_error(503, f"The note could not be read ({type(exc).__name__}).",
                       state="refused"),) + (None,) * 5
    current_sha = _sha256(old)
    if current_sha != expected:
        return ((409, {"ok": False, "state": "conflict", "path": rel,
                       "current_sha256": current_sha,
                       "error": (f"{rel} changed since this started, so nothing was "
                                 "changed; open it again and ask again.")})
                + (None,) * 5)
    try:
        text = old.decode("utf-8")
    except UnicodeDecodeError:
        return (_error(400, (f"{rel} is not valid UTF-8, so this editor will not rewrite "
                             "it; edit it in Obsidian."), state="refused"),) + (None,) * 5
    return None, full, rel, text, current_sha, old


def _start_surgical(kind: str, body, gate_check, wait_s: float, by: str,
                    transform, card_words, action_words):
    """One route's whole flow: validate, transform, one card, one write."""
    got = _surgical_common(body, kind, gate_check, wait_s, by)
    if got[0] is not None:
        code, out = got[0]
        return code, out
    _none, full, rel, text, current_sha, old = got
    new_text, extra_words, preview, why = transform(text)
    if why:
        return _error(400, why, state="refused")
    if new_text == text:
        said = str(extra_words or "Nothing needed changing.").replace("{rel}", rel)
        return 200, {"ok": True, "state": "unchanged", "path": rel,
                     "sha256": current_sha, "message": said}
    new_data = new_text.encode("utf-8", errors="surrogatepass")
    if len(new_data) > MAX_FILE_BYTES:
        return _error(413, (f"The changed note would be {len(new_data)} bytes, over the "
                            f"{MAX_FILE_BYTES} byte limit, so nothing was changed."),
                      state="refused")
    said = str(extra_words or ("Changed " + rel + ".")).replace("{rel}", rel)
    extra = {"said": said, "preview": _card_preview(preview),
             "card": card_words, "action": action_words}
    return _start_change_job(kind, full, rel, new_data, current_sha, _vault()[0],
                             gate_check, wait_s, by, extra)


def handle_insert(body, *, gate_check=None, wait_s: float = DEFAULT_WAIT_S,
                  by: str = "") -> tuple:
    """POST /api/notes/insert: under ONE heading, or before/after ONE anchor."""
    mode = str(body.get("mode") or "").strip().lower() if isinstance(body, dict) else ""
    target = str((body or {}).get("target") or "").strip() if isinstance(body, dict) else ""
    text = (body or {}).get("text") if isinstance(body, dict) else None
    if mode not in ("under_heading", "before", "after", "top"):
        return _error(400, "mode must be under_heading, before, after or top.",
                      state="refused")
    if not isinstance(text, str) or not text.strip():
        return _error(400, "Need the words to add as text.", state="refused")
    if mode == "top":
        def transform(current):
            new, preview, why = _insert_at_top(current, text)
            if why:
                return current, "", {}, why
            said = f'Added "{_split_clip(text)}" at the top of {{rel}}.'
            return new, said, preview, ""
        words = f'add "{_split_clip(text)}" at the top of'
        action = "add a line at the top of a note"
        code, out = _start_surgical("insert", body, gate_check, wait_s, by,
                                    transform, words, action)
        if isinstance(out, dict) and isinstance(out.get("message"), str):
            out["message"] = out["message"].replace(
                "{rel}", str(out.get("path") or "the note"))
        return code, out
    if mode == "under_heading":
        def transform(current):
            new, title, preview, why = _insert_under_heading(current, target, text)
            if why:
                return current, "", {}, why
            said = f'Added under the "{title}" heading in {{rel}}.'
            return new, said, preview, ""
        words = f'add "{_split_clip(text)}" under the "{_split_clip(target)}" heading in'
        action = "add a line under a heading"
    else:
        def transform(current):
            new, preview, why = _insert_at_anchor(current, target, mode, text)
            if why:
                return current, "", {}, why
            said = (f'Added {mode} "{_split_clip(target)}" in {{rel}}.')
            return new, said, preview, ""
        words = f'add "{_split_clip(text)}" {mode} "{_split_clip(target)}" in'
        action = "add a line " + mode + " some words"
    code, out = _start_surgical("insert", body, gate_check, wait_s, by,
                                transform, words, action)
    if isinstance(out, dict) and isinstance(out.get("message"), str):
        out["message"] = out["message"].replace("{rel}", str(out.get("path") or "the note"))
    return code, out


def handle_format(body, *, gate_check=None, wait_s: float = DEFAULT_WAIT_S,
                  by: str = "") -> tuple:
    """POST /api/notes/format: wrap ONE exact span in bold/italic, or unwrap it."""
    style = str((body or {}).get("style") or "").strip().lower() if isinstance(body, dict) else ""
    action = str((body or {}).get("action") or "").strip().lower() if isinstance(body, dict) else ""
    target = str((body or {}).get("target") or "").strip() if isinstance(body, dict) else ""
    if style not in ("bold", "italic", "strike", "code"):
        return _error(400, "style must be bold or italic.", state="refused")
    if action not in ("add", "remove"):
        return _error(400, "action must be add or remove.", state="refused")

    def transform(current):
        new, _unused, preview, why = _format_span(current, target, style, action)
        if why:
            return current, "", {}, why
        if action == "add":
            said = f'Made "{_split_clip(target)}" {style} in {{rel}}.'
        else:
            said = f'Removed the {style} from "{_split_clip(target)}" in {{rel}}.'
        return new, said, preview, ""

    words = (f'make "{_split_clip(target)}" {style} in' if action == "add"
             else f'remove the {style} from "{_split_clip(target)}" in')
    action_words = ("wrap one span in " + style) if action == "add" else ("unwrap one " + style)
    code, out = _start_surgical("format", body, gate_check, wait_s, by,
                                transform, words, action_words)
    if isinstance(out, dict) and isinstance(out.get("message"), str):
        out["message"] = out["message"].replace("{rel}", str(out.get("path") or "the note"))
    return code, out


def handle_replace(body, *, gate_check=None, wait_s: float = DEFAULT_WAIT_S,
                   by: str = "") -> tuple:
    """POST /api/notes/replace: replace ONE exact, whole-word occurrence."""
    old = (body or {}).get("old") if isinstance(body, dict) else None
    new = (body or {}).get("new") if isinstance(body, dict) else None
    if not isinstance(old, str) or not old:
        return _error(400, "Need the words to replace as old.", state="refused")
    if not isinstance(new, str) or new == old:
        return _error(400, "Need different words as new.", state="refused")

    def transform(current):
        fresh, preview, why = _replace_once(current, old, new)
        if why:
            return current, "", {}, why
        said = f'Replaced "{_split_clip(old)}" with "{_split_clip(new)}" in {{rel}}.'
        return fresh, said, preview, ""

    words = f'replace "{_split_clip(str(old))}" with "{_split_clip(str(new))}" in'
    code, out = _start_surgical("replace", body, gate_check, wait_s, by,
                                transform, words, "replace one exact occurrence")
    if isinstance(out, dict) and isinstance(out.get("message"), str):
        out["message"] = out["message"].replace("{rel}", str(out.get("path") or "the note"))
    return code, out


# ---------------------------------------------------------------------------
#   Wave 3 - customization: more formatting, line/checklist conversions,
#   headings and sections, properties, links and templates. One route with an
#   action, so every capability keeps ONE card, one guardian copy, one undo.
# ---------------------------------------------------------------------------

#: The built-in templates the owner can create from chat. Plain Markdown only:
#: headings and checkboxes, nothing Obsidian-specific beyond that.
BUILTIN_TEMPLATES = {
    "workout": ("workout log", """# Workout log

## Warm-up
- [ ] 5 minutes of easy movement

## Session
- [ ] Exercise - sets x reps

## Cool-down
- [ ] 5 minutes of stretching

## Notes
"""),
    "meeting": ("meeting notes", """# Meeting notes - {topic}

## Attendees

## Agenda
- [ ]

## Decisions

## Actions
- [ ] 
"""),
    "journal": ("daily journal", """# Daily journal - {date}

## What happened

## What I noticed

## Tomorrow
- [ ] 
"""),
    "project": ("project note", """# Project - {name}

## Goal

## Next steps
- [ ]

## Notes
"""),
}


def builtin_template(kind: str, subject: str = "") -> tuple:
    """`(title, body)` for one built-in template, or `("", why)`."""
    got = BUILTIN_TEMPLATES.get(str(kind or "").lower())
    if got is None:
        return "", "that is not one of the built-in templates"
    title, body = got
    subject = str(subject or "").strip()
    if "{topic}" in body:
        if not subject:
            return "", "say the meeting's topic"
        body = body.replace("{topic}", subject)
    if "{name}" in body:
        if not subject:
            return "", "say the project's name"
        body = body.replace("{name}", subject)
    if "{date}" in body:
        import datetime
        body = body.replace("{date}", datetime.date.today().isoformat())
    return title, body


def _heading_line(level: int, title: str, eol: str) -> str:
    level = max(1, min(6, int(level or 2)))
    return "#" * level + " " + str(title).strip() + eol


def _line_index_exact(text: str, target: str):
    """`(index, why)` for the ONE line whose stripped text equals `target`."""
    want = str(target or "").strip()
    if not want:
        return -1, "which line?"
    hits = [i for i, line in enumerate(_lines(text))
            if _line_body(line).strip() == want]
    if not hits:
        return -1, f'There is no line that is exactly "{_split_clip(want)}", so nothing was changed.'
    if len(hits) > 1:
        return -1, (f'"{_split_clip(want)}" is the whole line {len(hits)} times, so '
                    "nothing was changed - give words that appear once.")
    return hits[0], ""


def _with_prefix(text: str, idx: int, prefix: str, replace_prefix=None):
    """One line with `prefix` after its indentation; other bytes untouched."""
    lines = _lines(text)
    eol = _eol_of(text)
    body = _line_body(lines[idx])
    indent = body[:len(body) - len(body.lstrip())]
    content = body[len(indent):]
    if replace_prefix is not None:
        m = re.match(replace_prefix, content)
        if m:
            content = content[m.end():]
    lines[idx] = indent + prefix + content + (eol if lines[idx].endswith(("\n", "\r")) else "")
    return "".join(lines), body, indent + prefix + content


def _line_edit(text: str, action: str, target: str, level: int = 2):
    """`(new_text, said, preview, why)` for one line's prefix shape."""
    idx, why = _line_index_exact(text, target)
    if why:
        return text, "", {}, why
    body = _line_body(_lines(text)[idx])
    stripped = body.lstrip()
    bullet = r"(?:[-*+] |\d+\. |#{1,6} |> |\[[ xX]\] )"
    if action == "bullet":
        fresh, _b, newline = _with_prefix(text, idx, "- ", bullet)
        said = "Turned that line into a bullet."
    elif action == "number":
        fresh, _b, newline = _with_prefix(text, idx, "1. ", bullet)
        said = "Numbered that line."
    elif action == "checklist":
        fresh, _b, newline = _with_prefix(text, idx, "- [ ] ", bullet)
        said = "Turned that line into a checklist item."
    elif action == "quote":
        fresh, _b, newline = _with_prefix(text, idx, "> ", bullet)
        said = "Turned that line into a quote."
    elif action == "heading":
        fresh, _b, newline = _with_prefix(text, idx, "#" * max(1, min(6, level)) + " ", bullet)
        said = "Made that line a heading."
    elif action == "tick":
        if not re.match(r"^\s*- \[ \] ", body):
            return text, "", {}, "that checklist item is not unticked."
        fresh, _b, newline = _with_prefix(text, idx, "- [x] ", r"^\s*- \[ \] ")
        said = "Ticked that checklist item."
    elif action == "untick":
        if not re.match(r"^\s*- \[[xX]\] ", body):
            return text, "", {}, "that checklist item is not ticked."
        fresh, _b, newline = _with_prefix(text, idx, "- [ ] ", r"^\s*- \[[xX]\] ")
        said = "Unticked that checklist item."
    elif action == "plain":
        fresh, _b, newline = _with_prefix(text, idx, "", bullet)
        said = "Turned that line back into plain text."
    else:
        return text, "", {}, "unknown line action"
    if fresh == text:
        return text, said, {}, ""
    preview = _preview(body, newline, note="the line")
    return fresh, said, preview, ""


def _rename_heading(text: str, old: str, new: str):
    """`(new_text, said, preview, why)` for ONE heading renamed, level kept."""
    old_s = str(old or "").strip().lstrip("#").strip()
    new_s = str(new or "").strip()
    if not old_s or not new_s:
        return text, "", {}, "which heading, and to what?"
    lines = _lines(text)
    hits = [i for i, line in enumerate(lines)
            if (_heading_at(line) or (0, ""))[1].casefold() == old_s.casefold()]
    if not hits:
        return text, "", {}, f'There is no "{_split_clip(old_s)}" heading in this note.'
    if len(hits) > 1:
        return text, "", {}, (f'There are {len(hits)} "{_split_clip(old_s)}" headings, so '
                              "nothing was changed - name one of them.")
    i = hits[0]
    level, _title = _heading_at(lines[i])
    eol = _eol_of(text)
    old_line = _line_body(lines[i])
    lines[i] = _heading_line(level, new_s, eol if lines[i].endswith(("\n", "\r")) else "")
    fresh = "".join(lines)
    preview = _preview(old_line, _line_body(lines[i]), note="the heading")
    return fresh, f'Renamed the "{_split_clip(old_s)}" heading to "{_split_clip(new_s)}".', preview, ""


def _new_section(text: str, heading: str, body: str, level: int = 2):
    """`(new_text, said, preview, why)` - a section appended at the end."""
    head = str(heading or "").strip().lstrip("#").strip()
    if not head:
        return text, "", {}, "what should the new section be called?"
    for line in _lines(text):
        h = _heading_at(line)
        if h and h[1].casefold() == head.casefold():
            return text, "", {}, f'There is already a "{head}" heading in this note.'
    eol = _eol_of(text)
    block = ""
    if not text.endswith(("\n", "\r")):
        block += eol + eol
    elif not text.endswith(eol + eol):
        block += eol
    block += _heading_line(level, head, eol) + eol
    if str(body or "").strip():
        block += str(body).strip() + eol
    preview = _preview("", "#" * level + " " + head, note="a new section at the end")
    return text + block, f'Added a new "{_split_clip(head)}" section.', preview, ""


def _section_span(text: str, heading: str):
    """`(start, end, level, title, why)` for ONE heading's whole section.

    A section is its own heading line and every line after it up to the next
    heading of the SAME or a HIGHER level (a `##` section owns its `###`
    subsections, and stops at the next `##`), which is the span Obsidian itself
    folds. Character offsets into `text`, so the caller can cut exactly that
    span and leave every other byte alone.
    """
    want = str(heading or "").strip().lstrip("#").strip()
    if not want:
        return -1, -1, 0, "", "which section?"
    lines = _lines(text)
    found = []
    for i, line in enumerate(lines):
        h = _heading_at(line)
        if h and h[1].casefold() == want.casefold():
            found.append((i, h[0], h[1]))
    if not found:
        return -1, -1, 0, "", (f'There is no "{_split_clip(want)}" section in this '
                               "note, so nothing was changed.")
    if len(found) > 1:
        return -1, -1, 0, "", (f'There are {len(found)} "{_split_clip(want)}" '
                               "headings in this note, so nothing was changed - "
                               "name one of them.")
    idx, level, title = found[0]
    stop = len(lines)
    for j in range(idx + 1, len(lines)):
        h = _heading_at(lines[j])
        if h and h[0] <= level:
            stop = j
            break
    # A blank line directly before the next heading belongs to that heading's
    # spacing, not to this section: keep it, so removing a section never leaves
    # two headings touching with no blank line between them.
    while stop > idx + 1 and not _line_body(lines[stop - 1]).strip():
        stop -= 1
    start_at = sum(len(line) for line in lines[:idx])
    end_at = sum(len(line) for line in lines[:stop])
    return start_at, end_at, level, title, ""


def _remove_section(text: str, heading: str, rel: str = ""):
    """`(new_text, said, preview, why)` - ONE whole section taken out.

    The one DELETE-shaped edit to the inside of a note. It is carded under
    `edit_vault_note` (never `delete_vault_notes`, whose row says every byte is
    kept in `.trash`): this is a change to ONE note, the File Guardian copies the
    old text first, and one Undo puts the section back. The card names the
    section and states how many lines it removes, because a section is not one
    line and "delete the Warm-up section" must not be accepted blind.
    """
    start, end, _level, title, why = _section_span(text, heading)
    if why:
        return text, "", {}, why
    removed = text[start:end]
    count = len(_lines(removed))
    first = _line_body(_lines(removed)[0]) if removed else ""
    preview = _preview(first, "", note=(f'the whole "{title}" section is removed '
                                       f"({count} line{'s' if count != 1 else ''})"))
    preview["lines_removed"] = count
    fresh = text[:start] + text[end:]
    where = (" from " + rel) if rel else ""
    said = (f'Deleted the "{_split_clip(title)}" section ({count} line'
            f'{"s" if count != 1 else ""}){where}.')
    return fresh, said, preview, ""


def _property_edit(text: str, action: str, key: str, value: str):
    """`(new_text, said, preview, why)` for ONE frontmatter property."""
    key_s = str(key or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", key_s):
        return text, "", {}, "a property name can use letters, numbers, dot, dash and underscore"
    opened, front, body, why = _split_frontmatter(text)
    if why:
        return text, "", {}, why
    eol = _eol_of(text)
    hits = [i for i, line in enumerate(front) if line.split(":", 1)[0].strip() == key_s]
    if len(hits) > 1:
        return text, "", {}, f'the note has {len(hits)} "{key_s}:" lines, so nothing was changed'
    if action == "remove":
        if not opened or not hits:
            return text, f"That note has no \"{key_s}\" property.", {}, ""
        idx = hits[0]
        new_front = front[:idx] + front[idx + 1:]
        preview = _preview(_line_body(front[idx]), "", note="the property removed")
        if not new_front:
            # The note's ONLY property (2026-11-09: "unpin my ... note"): take
            # the whole front matter away rather than leave an empty "---/---"
            # block behind, so the note is byte-for-byte what it was before
            # the property was added.
            return body, f'Removed the "{key_s}" property.', preview, ""
        fresh = opened + "".join(new_front) + "---" + eol + body
        return fresh, f'Removed the "{key_s}" property.', preview, ""
    val = str(value or "").strip()
    if val.lower() in ("true", "false"):
        quoted = val.lower()
    elif re.fullmatch(r"-?\d+(?:\.\d+)?", val):
        quoted = val
    else:
        quoted = json.dumps(val, ensure_ascii=False)
    line = f"{key_s}: {quoted}{eol}"
    if not opened:
        fresh = "---" + eol + line + "---" + eol + text
        preview = _preview("", line.rstrip("\r\n"), note="a new property")
        return fresh, f'Added the "{key_s}" property.', preview, ""
    if hits:
        idx = hits[0]
        new_front = list(front)
        new_front[idx] = line
    else:
        new_front = list(front) + [line]
    fresh = opened + "".join(new_front) + "---" + eol + body
    preview = _preview("", line.rstrip("\r\n"), note="the property")
    return fresh, f'Set the "{key_s}" property.', preview, ""


#: Obsidian's own frontmatter key for the other names a note answers to. It is a
#: LIST there (`aliases:` then `  - name`), which is what Obsidian reads and
#: writes; a scalar is coerced on read and dropped on the next edit. The chat
#: resolver reads this key at tier 3 (jarvis_notes.py), so a name written here
#: works in every later conversation and travels with the note.
ALIAS_KEY = "aliases"


def _alias_read(front: list):
    """`(every alias already on the note, why)` - why non-empty means refuse.

    Only the shape this writer can put back is accepted: one `aliases:` line and,
    under it, nothing but `  - name` item lines; or one plain scalar on the
    `aliases:` line itself. Everything else is refused in words rather than
    rebuilt, because a rebuild of a shape this reader only half understands
    corrupts the note (measured 2026-11-24 with PyYAML on valid originals):

    * a comment line inside the list was left behind by the rebuild, which made
      the whole frontmatter invalid YAML (ParserError);
    * a blank line inside the list orphaned the items after it, so `title: x`
      became `'x\\n- old2'` and the alias `old2` was silently dropped;
    * a one-line flow list `aliases: ["Salt, Pepper", "Workout"]` was split on
      the quoted comma into four aliases.

    Read exactly as `jarvis_notes._frontmatter_aliases` reads, so the aliases the
    resolver answers to and the aliases this writer keeps are the same list.
    """
    hits = [i for i, line in enumerate(front)
            if re.match(r"^aliases\s*:", line, re.I)]
    if not hits:
        return [], ""
    if len(hits) > 1:
        return [], ("the note has more than one aliases: line, so it is not "
                    "changed; change them in Obsidian first")
    i = hits[0]
    rest = front[i].split(":", 1)[1].strip()
    if rest.startswith("["):
        return [], ("the note's aliases are written on one line inside [ ], and "
                    "this editor will not rebuild that line; change it in "
                    "Obsidian first")
    if rest.startswith("{"):
        return [], ("the note's aliases are not a list, so this editor will not "
                    "change them; change them in Obsidian first")
    if rest:
        return [rest.strip().strip("\"'")], ""
    out, j = [], i + 1
    while j < len(front):
        line = front[j]
        stripped = line.strip()
        if stripped == "":
            nxt = next((n for n in front[j + 1:] if n.strip()), "")
            if re.match(r"^\s+-\s+", nxt):
                return [], ("the note has a blank line inside its aliases: list, "
                            "and this editor will not rebuild that; change it in "
                            "Obsidian first")
            break
        if stripped.startswith("#"):
            if line[:1] in (" ", "\t"):
                return [], ("the note has a comment line inside its aliases: "
                            "list, and this editor will not rebuild that; change "
                            "it in Obsidian first")
            break
        item = re.fullmatch(r"\s+-\s+(.+?)\s*", line)
        if not item:
            break
        out.append(item.group(1).strip().strip("\"'"))
        j += 1
    return [a for a in out if a], ""


def _alias_add(text: str, alias: str, rel: str = ""):
    """`(new_text, said, preview, why)` - one more name in `aliases:`.

    The list is rebuilt from what the note already answers to, so an existing
    alias is kept, a repeated one changes nothing, and the note's other
    properties are untouched. One card, through handle_customize, like every
    other edit to an existing note.

    Every value is written as a JSON-quoted YAML scalar (`json.dumps`), so a `*`,
    a `&`, a leading `- `, a comma and a `#` are all just characters in one line
    instead of YAML syntax. Measured 2026-11-24: `*gym*` made the file
    unreadable (ScannerError), `&co` became `aliases: [null]`, and `- gym` became
    a nested list.
    """
    name = " ".join(str(alias or "").split()).strip().strip("\"'").strip()
    if not name:
        return text, "", {}, "which name should the note answer to?"
    # Anything else is safe inside the JSON-quoted scalar written below, so the
    # only names refused are the ones that could not be read back the same way:
    # a quote or a backslash would be escaped there and read back escaped
    # (`jarvis_notes._frontmatter_aliases` strips the outer quotes and nothing
    # else), so the alias would answer to a name the owner never said.
    if len(name) > 64 or any(ord(c) < 32 for c in name) or '"' in name or "\\" in name:
        return (text, "", {},
                "a name for a note can be up to 64 characters and cannot contain "
                "a quote, a backslash or a line break")
    opened, front, body, why = _split_frontmatter(text)
    if why:
        return text, "", {}, why
    # A name that already opens ANOTHER note can never win: the resolver reads a
    # file's own name before any note's aliases list, so writing it would leave a
    # promise the vault cannot keep. Measured 2026-11-24: with Workout.md in the
    # vault, "call my Exercise note workout" wrote the alias and "read my workout
    # note" still opened Workout.md, while the reply said "say workout ... and I
    # will look for that note". Refused in words that name that other note.
    if rel:
        try:
            _row, _why, _matches = find_name(name)
        except Exception:                   # noqa: BLE001 - keep the words given
            _row = None
        if (_row and _row.get("path")
                and str(_row["path"]).casefold() != str(rel).casefold()):
            other = str(_row["path"]).rsplit("/", 1)[-1]
            return (text, "", {},
                    f"There is already a note called {other}, so saying "
                    f"{name} would open that one")
    eol = _eol_of(text)
    have, why = _alias_read(front)
    if why:
        return text, "", {}, why
    if any(a.casefold() == name.casefold() for a in have):
        return text, f'The note already answers to "{name}".', {}, ""
    keep, skipping = [], False
    for line in front:
        if re.match(r"^aliases\s*:", line, re.I):
            skipping = True
            continue
        if skipping and re.match(r"^\s+-\s+", line):
            continue
        skipping = False
        keep.append(line)
    new_front = keep + [f"{ALIAS_KEY}:{eol}"] + [
        f"  - {json.dumps(a)}{eol}" for a in have + [name]]
    if not opened:
        fresh = "---" + eol + "".join(new_front) + "---" + eol + text
    else:
        fresh = opened + "".join(new_front) + "---" + eol + body
    preview = _preview("", f"aliases: {name}", note="another name")
    return fresh, f'The note now also answers to "{name}".', preview, ""


def _append_link(text: str, note_name: str, heading: str = ""):
    """`(new_text, said, preview, why)` - one `[[Note]]` line."""
    name = str(note_name or "").strip().strip("[]")
    if not name or "\n" in name or "[" in name or "]" in name:
        return text, "", {}, "which note should be linked?"
    # The chat matcher lowercases the sentence, so the target arrived as
    # "exercise" and the note was written `[[exercise]]` (measured 2026-11-24).
    # A target that resolves to a real note takes that note's own title back,
    # which is what Obsidian links on.
    try:
        _row, _why, _matches = find_name(name)
        if _row and _row.get("path"):
            name = str(_row["path"]).rsplit("/", 1)[-1].rsplit(".", 1)[0]
    except Exception:                       # noqa: BLE001 - keep the words given
        pass
    link_line = "[[" + name + "]]"
    if "[[" + name + "]]" in text:
        return text, "That link is already in the note.", {}, ""
    if heading:
        placed = _insert_under_heading(text, heading, link_line)
        if placed[3]:
            return text, "", {}, placed[3]
        return placed[0], f'Added a link to [[{name}]] under the "{heading}" heading.', placed[2], ""
    eol = _eol_of(text)
    led = "" if not text.startswith("\n") else ""
    if text and not text.endswith(("\n", "\r")):
        led = eol
    fresh = text + led + link_line + eol
    preview = _preview("", link_line, note="a new link line at the end")
    return fresh, f"Added a link to [[{name}]] at the end of the note.", preview, ""


def _template_dir():
    """`(Path, why)` - the Templates plugin folder or <vault>/Templates."""
    try:
        import jarvis_notes as N
        vault = N.obsidian_vault()
        why = N.vault_problem(vault)
    except Exception as exc:                                # noqa: BLE001
        return None, f"the vault could not be found ({type(exc).__name__})"
    if why:
        return None, why
    root = Path(os.path.realpath(str(vault)))
    folder = "Templates"
    try:
        cfg = root / ".obsidian" / "templates.json"
        if cfg.is_file():
            got = json.loads(cfg.read_text(encoding="utf-8"))
            if isinstance(got, dict) and isinstance(got.get("folder"), str) and got["folder"].strip():
                folder = got["folder"].strip()
    except Exception:                                       # noqa: BLE001
        folder = "Templates"
    parts = [p for p in folder.replace("\\", "/").split("/") if p and p not in (".", "..")]
    if any(p.startswith(".") for p in parts):
        return None, "the templates folder is hidden, so nothing was written there"
    target = root.joinpath(*parts)
    if not _inside(root, target):
        return None, "the templates folder is outside the vault"
    return target, ""


def list_templates() -> tuple:
    """`(names, why)` - the template file names only, never their text."""
    folder, why = _template_dir()
    if folder is None:
        return [], why
    if not folder.is_dir():
        return [], ""
    names = sorted({p.stem for p in folder.glob("*.md") if p.is_file()
                    and not _is_link_or_reparse(p)})
    return names[:200], ""


def handle_templates_list() -> tuple:
    names, why = list_templates()
    return 200, {"ok": True, "count": len(names), "templates": names, "why": why}


def handle_template_save(body, *, gate_check=None, wait_s: float = DEFAULT_WAIT_S,
                         by: str = "") -> tuple:
    """POST /api/notes/customize, action save_template: ONE new template file."""
    raw, why = _one_path(body)
    if why or not isinstance(body, dict):
        return _error(400, why or "Need a JSON object.", state="refused")
    parts, why = note_parts(raw)
    if why:
        return _error(400, why, state="refused")
    vault, why = _vault()
    if vault is None:
        return _error(503, "Nothing was saved: " + why + ".", state="refused")
    full, rel, why = _resolve_note(raw)
    if why:
        return _error(400, why, state="refused")
    _P = _protection()
    if _P is not None:
        _said = _P.path_refusal(str(full))
        if _said:
            return _error(403, _said, state="refused")
    if not full.is_file():
        return _error(404, f"There is no note at {rel} in your Obsidian vault.",
                      state="refused")
    folder, why = _template_dir()
    if folder is None:
        return _error(503, "Nothing was saved: " + why + ".", state="refused")
    name = str(body.get("name") or Path(rel).stem).strip()
    if not re.fullmatch(r"[A-Za-z0-9 _.-]{1,80}", name or ""):
        return _error(400, "a template name can use letters, numbers, spaces, dot, dash and underscore",
                      state="refused")
    target_rel = folder.name + "/" + (name if name.lower().endswith(".md") else name + ".md")
    target = vault.joinpath(*target_rel.replace("\\", "/").split("/"))
    if not _inside(vault, target):
        return _error(400, "the template path is outside the vault", state="refused")
    if target.exists():
        return _error(409, f"There is already a template at {target_rel}, so nothing was saved.",
                      state="exists")
    try:
        data = _read_bytes(full)
    except OSError as exc:
        return _error(503, f"The note could not be read ({type(exc).__name__}).", state="refused")
    extra = {"card": "save", "source": rel}
    return _start_change_job("create_template", target, target_rel, data, "", vault,
                             gate_check, wait_s, by, extra)


def handle_customize(body, *, gate_check=None, wait_s: float = DEFAULT_WAIT_S,
                     by: str = "") -> tuple:
    """POST /api/notes/customize: one action, one exact-match edit, one card."""
    action = str((body or {}).get("action") or "").strip().lower()
    if action == "save_template":
        return handle_template_save(body, gate_check=gate_check, wait_s=wait_s, by=by)
    got = _surgical_common(body, "customize", gate_check, wait_s, by)
    if got[0] is not None:
        return got[0][0], got[0][1]
    _none, full, rel, text, current_sha, old = got
    preview = {}
    if action in ("format",):
        style = str(body.get("style") or "").strip().lower()
        target = str(body.get("target") or "").strip()
        act = str(body.get("action2") or body.get("format_action") or "add").strip().lower()
        new_text, said, preview, why = _format_span(text, target, style, act)
        card = (f'make "{_split_clip(target)}" {style} in' if act == "add"
                else f'remove the {style} from "{_split_clip(target)}" in')
    elif action == "line":
        kind = str(body.get("line_action") or "").strip().lower()
        target = str(body.get("target") or "").strip()
        level = int(body.get("level") or 2)
        new_text, said, preview, why = _line_edit(text, kind, target, level)
        card = f"change one line ({kind}) in"
    elif action == "rename_heading":
        old_h = str(body.get("old") or "").strip()
        new_h = str(body.get("new") or "").strip()
        new_text, said, preview, why = _rename_heading(text, old_h, new_h)
        card = f'rename the "{_split_clip(old_h)}" heading in'
    elif action == "new_section":
        head = str(body.get("heading") or "").strip()
        body_text = str(body.get("text") or "")
        level = int(body.get("level") or 2)
        new_text, said, preview, why = _new_section(text, head, body_text, level)
        card = f'add a new "{_split_clip(head)}" section to'
    elif action in ("remove_section", "delete_section"):
        head = str(body.get("heading") or body.get("section") or "").strip()
        new_text, said, preview, why = _remove_section(text, head, rel)
        card = f'delete the "{_split_clip(head)}" section from'
    elif action in ("set_property", "remove_property"):
        key = str(body.get("key") or "").strip()
        value = str(body.get("value") or "")
        act = "remove" if action == "remove_property" else "set"
        new_text, said, preview, why = _property_edit(text, act, key, value)
        card = (f'set the "{_split_clip(key)}" property in' if act == "set"
                else f'remove the "{_split_clip(key)}" property from')
    elif action == "link":
        note_name = str(body.get("note") or "").strip()
        heading = str(body.get("heading") or "").strip()
        new_text, said, preview, why = _append_link(text, note_name, heading)
        card = f'add a link to "{_split_clip(note_name)}" in'
    elif action == "add_alias":
        alias = str(body.get("alias") or "").strip()
        new_text, said, preview, why = _alias_add(text, alias, rel)
        card = f'add "{_split_clip(alias)}" as another name for'
    else:
        return _error(400, "unknown action.", state="refused")
    if why:
        return _error(400, why, state="refused")
    if new_text == text:
        return 200, {"ok": True, "state": "unchanged", "path": rel,
                     "sha256": current_sha, "message": said or "Nothing needed changing."}
    new_data = new_text.encode("utf-8", errors="surrogatepass")
    if len(new_data) > MAX_FILE_BYTES:
        return _error(413, ("The changed note would be over the size limit, so nothing "
                            "was changed."), state="refused")
    extra = {"said": str(said or "Changed the note."), "preview": _card_preview(preview),
             "card": card, "action": action}
    return _start_change_job("customize", full, rel, new_data, current_sha, _vault()[0],
                             gate_check, wait_s, by, extra)


# ---------------------------------------------------------------------------
#   Wave 4 - rename or move ONE note, keeping its links working (2026-10-31)
# ---------------------------------------------------------------------------
# The owner's "flexibility" decision. A rename/move is one note's PATH change
# plus the links that named it, so the plan is read-only, the card names the
# file and the link counts, and ONE approval writes the move plus only those
# link bytes. Every changed/moved note is copied through the File Guardian
# first and ONE batch Undo puts every byte and path back. Code fences and
# inline code are never rewritten.

RENAME_PATH = "/api/notes/rename"
MOVE_PATH = "/api/notes/move"
RENAME_RECEIPT = "notes_rename"
MOVE_RECEIPT = "notes_move"
MAX_LINK_SCAN = 2000
_BAD_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WIKI_LINK = re.compile(r"(!?)\[\[([^\]\n]+)\]\]")
_MD_LINK = re.compile(r"(!?)\[([^\]\n]*)\]\(\s*(?P<target><[^>\n]+>|[^)\s]+)(?P<tail>[^)\n]*)\)")
_INLINE_CODE = re.compile(r"(`+)([^\n]*?)\1")

for _kind, _words in {
    "rename": {
        "denied": "You said no, so the note was not renamed and no link was changed.",
        "timed_out": "Nobody answered the approval card in time, so the note was not renamed and no link was changed.",
        "refused": "The approval gate refused it, so the note was not renamed and no link was changed.",
    },
    "move": {
        "denied": "You said no, so the note was not moved and no link was changed.",
        "timed_out": "Nobody answered the approval card in time, so the note was not moved and no link was changed.",
        "refused": "The approval gate refused it, so the note was not moved and no link was changed.",
    },
}.items():
    _REFUSED_WRITE.setdefault(_kind, {}).update(_words)


def _safe_filename(raw) -> tuple:
    """`(new .md filename, why)` - ONE filename, never a path."""
    text = str(raw or "").strip().strip('"').strip("'").strip("`")
    if text.lower().endswith(".md"):
        text = text[:-3].strip()
    if not text:
        return "", "what should the new name be?"
    if text.startswith(".") or text.endswith((" ", ".")):
        return "", "a note name cannot start with a dot or end with a space or dot"
    if _BAD_FILENAME.search(text):
        return "", "a note name cannot contain < > : \" / \\ | ? * or a control character"
    if len(text) > 120:
        return "", "that note name is longer than the editor's 120-character limit"
    return text + ".md", ""


def _folder_parts(raw) -> tuple:
    """`(relative folder parts, why)` - inside the vault, not hidden."""
    text = str(raw or "").strip().strip('"').strip("'").strip("`").replace("\\", "/")
    if not text:
        return [], "which folder should it move to?"
    if os.path.isabs(text) or re.match(r"^[A-Za-z]:", text):
        return [], "that folder is outside your Obsidian vault"
    parts = [p for p in text.split("/") if p not in ("", ".")]
    if not parts:
        return [], "which folder should it move to?"
    if ".." in parts:
        return [], "that folder is outside your Obsidian vault"
    if any(p.startswith(".") for p in parts):
        return [], "that folder is hidden, and the notes editor does not change hidden folders"
    if any(_BAD_FILENAME.search(p) for p in parts):
        return [], "that folder name contains a character a filename cannot hold"
    return parts, ""


def _folder_full(vault: Path, parts: list) -> Path:
    return vault.joinpath(*parts)


def _folder_is_safe(vault: Path, full: Path) -> bool:
    """Every existing component from the vault down is a real directory."""
    try:
        cur = vault
        rel = os.path.relpath(str(full), str(vault)).replace("\\", "/")
        for part in rel.split("/"):
            if part in ("", "."):
                continue
            cur = cur / part
            if cur.exists() and (_is_link_or_reparse(cur) or not cur.is_dir()):
                return False
        return _inside(vault, full)
    except (OSError, ValueError):
        return False


def _case_exists(parent: Path, name: str) -> bool:
    try:
        want = name.casefold()
        return any(p.name.casefold() == want for p in parent.iterdir())
    except OSError:
        return True


def _code_ranges(text: str) -> list:
    """Character ranges for fenced blocks and inline code, where links do not change."""
    ranges = list(_fence_ranges(text))
    for m in _INLINE_CODE.finditer(text):
        ranges.append((m.start(), m.end()))
    ranges.sort()
    return ranges


def _in_ranges(pos: int, ranges: list) -> bool:
    return any(a <= pos < b for a, b in ranges)


def _scan_vault_notes(vault: Path):
    """[(rel, full, old bytes, text)] for readable .md notes, or (None, why)."""
    out = []
    try:
        paths = sorted(p for p in vault.rglob("*.md") if p.is_file())
    except OSError as exc:                                  # noqa: BLE001
        return None, f"the vault could not be read ({type(exc).__name__})"
    if len(paths) > MAX_LINK_SCAN:
        return None, (f"the vault has more than {MAX_LINK_SCAN} notes, and the link "
                      "plan would take too long; nothing was changed")
    P = _protection()
    for path in paths:
        try:
            rel = os.path.relpath(str(path), str(vault)).replace("\\", "/")
        except ValueError:
            continue
        parts = rel.split("/")
        if any(part.startswith(".") for part in parts[:-1]):
            continue
        if _is_link_or_reparse(path):
            continue
        if P is not None and P.path_refusal(str(path), write=False):
            continue
        try:
            if os.stat(str(path)).st_size > MAX_FILE_BYTES:
                continue
            old = _read_bytes(path)
            text = old.decode("utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        out.append((rel, path, old, text))
    return out, ""


def _wiki_target(inner: str, source_rel: str, target_rel: str, kind: str):
    """The new `[[...]]` inner text, or None when this link is not the note."""
    cut = len(inner)
    for mark in ("|", "#"):
        at = inner.find(mark)
        if at != -1:
            cut = min(cut, at)
    core, suffix = inner[:cut], inner[cut:]
    if not core:
        return None
    segments = core.replace("\\", "/").split("/")
    old_stem = Path(source_rel).stem
    new_stem = Path(target_rel).stem
    if kind == "rename":
        last = segments[-1]
        stem = last[:-3] if last.lower().endswith(".md") else last
        if stem.casefold() != old_stem.casefold():
            return None
        segments[-1] = new_stem + (".md" if last.lower().endswith(".md") else "")
    else:
        # Wikilinks name a note by title; a move does not change its title. Only
        # a path-style wikilink that named the old path is rewritten.
        if "/" not in core:
            return None
        norm = os.path.normpath(core).replace("\\", "/")
        candidates = {source_rel.casefold(), source_rel[:-3].casefold()
                      if source_rel.lower().endswith(".md") else source_rel.casefold()}
        if norm.casefold() not in candidates:
            return None
        segments = target_rel.replace("\\", "/").split("/")
        if segments[-1].lower().endswith(".md"):
            segments[-1] = segments[-1][:-3]
    return "/".join(segments) + suffix


def _markdown_target(raw: str, note_rel: str, source_rel: str, target_rel: str):
    """The new markdown link target for this note, or None if it is not the note."""
    bracketed = raw.startswith("<") and raw.endswith(">")
    target = raw[1:-1] if bracketed else raw
    if not target or target.startswith(("#", "/", "//")) or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target):
        return None
    core, sep, anchor = target.partition("#")
    if not core:
        return None
    note_dir = os.path.dirname(note_rel).replace("\\", "/")
    if core.startswith("/"):
        resolved = core.lstrip("/")
    elif core.startswith("./"):
        resolved = os.path.normpath(os.path.join(note_dir, core[2:])).replace("\\", "/")
    else:
        resolved = os.path.normpath(os.path.join(note_dir, core)).replace("\\", "/")
    want = source_rel.casefold()
    got = resolved.casefold()
    if got != want and got != (want[:-3] if want.endswith(".md") else want):
        return None
    new_core = os.path.relpath(target_rel, note_dir or ".").replace("\\", "/")
    if core.startswith("./") and not new_core.startswith("./"):
        new_core = "./" + new_core
    if bracketed:
        new_core = "<" + new_core + ">"
    return new_core + (sep + anchor if sep else "")


def _link_plan(vault: Path, source_rel: str, target_rel: str, kind: str):
    """(plan files, update count, note count, why). Read-only."""
    notes, why = _scan_vault_notes(vault)
    if notes is None:
        return None, 0, 0, why
    files = []
    updates = 0
    for rel, full, old, text in notes:
        ranges = _code_ranges(text)
        changed = {"count": 0}

        def wiki(m):
            if _in_ranges(m.start(), ranges):
                return m.group(0)
            inner = _wiki_target(m.group(2), source_rel, target_rel, kind)
            if inner is None:
                return m.group(0)
            changed["count"] += 1
            return m.group(1) + "[[" + inner + "]]"

        def markdown(m):
            if _in_ranges(m.start(), ranges):
                return m.group(0)
            tail = m.group("tail") or ""
            target = _markdown_target(m.group("target"), rel, source_rel, target_rel)
            if target is None:
                return m.group(0)
            changed["count"] += 1
            return m.group(1) + "[" + m.group(2) + "](" + target + tail + ")"

        new_text = _WIKI_LINK.sub(wiki, text)
        # The positions moved after the wiki replacements, so recompute the
        # code ranges before checking markdown links for fenced/inline code.
        ranges = _code_ranges(new_text)
        new_text = _MD_LINK.sub(markdown, new_text)
        if changed["count"]:
            new_bytes = new_text.encode("utf-8")
            if len(new_bytes) > MAX_FILE_BYTES:
                return None, 0, 0, (f"{rel} would grow over the {MAX_FILE_BYTES} byte "
                                   f"limit while its links are updated; nothing was changed")
            files.append({"rel": rel, "full": str(full), "old": old,
                          "new": new_bytes, "sha_before": _sha256(old),
                          "sha_after": _sha256(new_bytes)})
            updates += changed["count"]
    return files, updates, len(files), ""


def _plan_batch(kind: str, body: dict, *, gate_check=None) -> tuple:
    """`(plan dict, error tuple)`; every refusal happens before any card."""
    raw, why = _one_path(body)
    if why:
        return None, _error(400, why, state="refused")
    source_full, source_rel, why = _resolve_note(raw)
    if why:
        return None, _error(400, why, state="refused")
    if not source_rel.lower().endswith(".md"):
        return None, _error(400, "Rename and move work on .md notes only; this note is not one.",
                            state="refused")
    if any(part.startswith(".") for part in source_rel.split("/")):
        return None, _error(403, "that note is in the hidden part of your vault, so nothing was changed.",
                            state="refused")
    if not source_full.is_file():
        return None, _error(404, f"There is no note at {source_rel} in your Obsidian vault.",
                            state="refused")
    _P = _protection()
    if _P is not None:
        said = _P.path_refusal(str(source_full), write=True)
        if said:
            return None, _error(403, said, state="refused")
    vault, why = _vault()
    if vault is None:
        return None, _error(503, "Nothing was changed: " + why + ".", state="refused")
    old = _read_bytes(source_full)
    source_sha = _sha256(old)
    if kind == "rename":
        filename, why = _safe_filename(body.get("title") or body.get("new_title")
                                       or body.get("new_name"))
        if why:
            return None, _error(400, why, state="refused")
        parent = os.path.dirname(source_rel).replace("\\", "/").strip("/")
        target_rel = (parent + "/" + filename) if parent else filename
        target_folder_rel = parent
        create_folder = False
    else:
        parts, why = _folder_parts(body.get("folder") or body.get("target_folder")
                                   or body.get("folder_path"))
        if why:
            return None, _error(400, why, state="refused")
        target_folder_rel = "/".join(parts)
        folder_full = _folder_full(vault, parts)
        if not _folder_is_safe(vault, folder_full):
            return None, _error(400, "that folder is not a real folder inside your Obsidian vault",
                                state="refused")
        create_folder = bool(body.get("create_folder") or body.get("create"))
        if not folder_full.is_dir() and not create_folder:
            return None, _error(
                400, (f'There is no folder "{target_folder_rel}" in your Obsidian vault, so '
                      'nothing was moved. Say "create the folder" if you want it made.'),
                state="refused")
        if folder_full.exists() and not folder_full.is_dir():
            return None, _error(400, "that path is a file, not a folder", state="refused")
        if _P is not None:
            said = _P.path_refusal(str(folder_full), write=True)
            if said:
                return None, _error(403, said, state="refused")
        target_rel = (target_folder_rel + "/" + os.path.basename(source_rel)) if target_folder_rel else os.path.basename(source_rel)
    target_full = vault.joinpath(*target_rel.split("/"))
    target_parent = target_full.parent
    if not _inside(vault, target_full) or not _inside(vault, target_parent):
        return None, _error(400, "the destination is outside your Obsidian vault", state="refused")
    if target_rel.casefold() == source_rel.casefold():
        return None, (200, {"ok": True, "state": "unchanged", "path": source_rel,
                            "message": "That is already the note's name."})
    if not _folder_is_safe(vault, target_parent):
        return None, _error(400, "the destination folder is not a safe folder in your vault",
                            state="refused")
    if target_parent.exists() and _case_exists(target_parent, target_full.name):
        return None, _error(409, f"There is already a note at {target_rel}, so nothing was changed.",
                            state="refused")
    # Creating a folder is only ever done when the owner explicitly said so.
    created_folders = []
    if create_folder:
        cur = vault
        for part in target_parent.relative_to(vault).parts:
            cur = cur / part
            if not cur.exists():
                created_folders.append(os.path.relpath(str(cur), str(vault)).replace("\\", "/"))
    files, updates, notes_n, why = _link_plan(vault, source_rel, target_rel, kind)
    if files is None:
        return None, _error(400, why + " Nothing was changed.", state="refused")
    if kind == "rename":
        new_stem = Path(target_rel).stem.casefold()
        old_stem = Path(source_rel).stem.casefold()
        others = []
        for other_rel, _full, _old, _text in (_scan_vault_notes(vault)[0] or []):
            if other_rel.casefold() != source_rel.casefold() \
                    and Path(other_rel).stem.casefold() == new_stem:
                others.append(other_rel)
        if others:
            return None, _error(409, ("There is already another note with that name in your "
                                      "vault, so nothing was renamed."), state="refused")
    source_changed = next((f for f in files if f["rel"] == source_rel), None)
    target_data = source_changed["new"] if source_changed else old
    plan = {
        "kind": kind, "vault": str(vault), "source": source_rel,
        "target": target_rel, "source_sha": source_sha,
        "target_sha": _sha256(target_data), "target_data": target_data,
        "source_unchanged": source_changed is None,
        "files": files, "updates": updates, "notes": notes_n,
        "created_folders": created_folders,
        "hidden": _hidden_lists(),
    }
    plan["preview"] = _batch_preview(plan)
    return plan, None


def _batch_preview(plan: dict) -> str:
    verb = "renames" if plan["kind"] == "rename" else "moves"
    created = " and creates the folder" if plan["created_folders"] else ""
    if plan["hidden"]:
        return (f"This {verb} a note{created} and updates {plan['updates']} link(s) in "
                f"{plan['notes']} note(s).")
    if plan["updates"]:
        return (f"This {verb} {plan['source']} to {plan['target']}{created} and updates "
                f"{plan['updates']} link(s) in {plan['notes']} note(s).")
    return f"This {verb} {plan['source']} to {plan['target']}{created}. It has no links to update."


def _changed_note_labels(plan: dict, limit: int = 3) -> list:
    """The first few affected note filenames, in scan order, no duplicates."""
    names = []
    for row in plan["files"]:
        rel = str(row.get("rel") or "")
        if not rel or rel == plan["source"]:
            continue
        name = rel.rsplit("/", 1)[-1]
        if name not in names:
            names.append(name)
        if len(names) >= limit:
            break
    return names


def _batch_prompt_detail(plan: dict) -> tuple:
    created = " and create the folder" if plan["created_folders"] else ""
    if plan["hidden"]:
        prompt = (f"{plan['kind']} a note in your Obsidian vault{created} and update "
                  f"{plan['updates']} link(s) in {plan['notes']} note(s)")
        detail = {"action": "rename a note" if plan["kind"] == "rename" else "move a note",
                  "updates": plan["updates"], "notes": plan["notes"],
                  "hidden_lists": True, "undo": True, "deletes": False}
        return prompt, detail
    labels = _changed_note_labels(plan)
    more = max(0, plan["notes"] - len(labels))
    shown = ""
    if labels:
        shown = " (" + ", ".join(labels) + (f" (+{more} more)" if more else "") + ")"
    prompt = (f"{plan['kind']} {plan['source']} to {plan['target']} in your Obsidian "
              f"vault{created} and update {plan['updates']} link(s) in "
              f"{plan['notes']} note(s){shown}")
    detail = {"path": plan["source"], "target": plan["target"],
              "action": "rename a note" if plan["kind"] == "rename" else "move a note",
              "updates": plan["updates"], "notes": plan["notes"],
              "undo": True, "deletes": False,
              "creates_folder": bool(plan["created_folders"])}
    if labels:
        detail["changed_notes"] = labels
        if more:
            detail["changed_notes_more"] = more
    return prompt, detail


def _batch_verify(plan: dict) -> str:
    """Empty when the plan still matches the disk; else plain words."""
    vault, why = _vault()
    if vault is None:
        return "The Obsidian vault could not be found, so nothing was changed."
    source = vault.joinpath(*plan["source"].split("/"))
    if not source.is_file() or _is_link_or_reparse(source):
        return f"{plan['source']} is no longer in your Obsidian vault, so nothing was changed."
    try:
        if _sha256(_read_bytes(source)) != plan["source_sha"]:
            return f"{plan['source']} changed while the card waited, so nothing was changed."
    except OSError:
        return f"{plan['source']} could not be re-read, so nothing was changed."
    target = Path(plan["vault"]).joinpath(*plan["target"].split("/"))
    if target.parent.exists() and (target.exists() or _case_exists(target.parent, target.name)):
        return f"There is already a note at {plan['target']}, so nothing was changed."
    if not target.parent.exists() and not plan.get("created_folders"):
        return "The destination folder disappeared, so nothing was changed."
    for entry in plan["files"]:
        full = Path(entry["full"])
        if not full.is_file() or _is_link_or_reparse(full):
            return f"{entry['rel']} is no longer there, so nothing was changed."
        want = entry["sha_before"]
        try:
            if _sha256(_read_bytes(full)) != want:
                return f"{entry['rel']} changed while the card waited, so nothing was changed."
        except OSError:
            return f"{entry['rel']} could not be re-read, so nothing was changed."
    return ""


def _write_new_file(full: Path, data: bytes) -> None:
    fd = os.open(str(full), os.O_WRONLY | os.O_CREAT | os.O_EXCL
                 | getattr(os, "O_BINARY", 0), 0o644)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
    except Exception:
        try:
            os.unlink(str(full))
        except OSError:
            pass
        raise


def _batch_restore_before(before: dict) -> None:
    """Undo the whole batch from its own copies. Best effort, never raises."""
    try:
        backup = Path(str(before.get("backup_dir") or ""))
        source = str(before.get("source") or "")
        target = str(before.get("target") or "")
        vault = Path(str(before.get("vault") or ""))
        if not backup.is_dir() or not source or not target:
            return
        target_full = vault.joinpath(*target.split("/"))
        source_full = vault.joinpath(*source.split("/"))
        if target_full.is_file():
            try:
                os.unlink(str(target_full))
            except OSError:
                return
        for row in before.get("files") or []:
            rel = str(row.get("rel") or "")
            name = str(row.get("backup") or "")
            if not rel or not name:
                continue
            data = (backup / name).read_bytes()
            full = vault.joinpath(*rel.split("/"))
            _write_note(full, data)
        for rel in sorted((before.get("created_folders") or []), reverse=True):
            full = vault.joinpath(*str(rel).split("/"))
            try:
                if full.is_dir() and not any(full.iterdir()):
                    os.rmdir(str(full))
            except OSError:
                pass
    except Exception:                                       # noqa: BLE001
        return


def _batch_worker(job_id: str, plan: dict, gate_check) -> None:
    kind = plan["kind"]
    try:
        prompt, detail = _batch_prompt_detail(plan)
        verdict = gate_check(ACTION, detail, prompt)
        if not getattr(verdict, "allowed", False):
            outcome = str(getattr(verdict, "outcome", "refused") or "refused")
            state = "denied" if outcome in ("denied", "timed_out") else "failed"
            _finish(job_id, state=state, outcome=outcome,
                    message=_REFUSED_WRITE.get(kind, {}).get(
                        outcome, "The approval gate refused it, so nothing was changed."))
            _audit(kind + "_refused", {"job": job_id, "outcome": outcome})
            return
        why = _batch_verify(plan)
        if why:
            _finish(job_id, state="failed", message=why)
            _audit(kind + "_failed", {"job": job_id, "why": "changed"})
            return
        vault = Path(plan["vault"])
        source_full = vault.joinpath(*plan["source"].split("/"))
        target_full = vault.joinpath(*plan["target"].split("/"))
        snap_files = [(plan["source"], source_full)]
        for row in plan["files"]:
            if row["rel"] != plan["source"]:
                snap_files.append((row["rel"], Path(row["full"])))
        snaps = []
        for rel, full in snap_files:
            snap = _snapshot(full, rel)
            if not snap.get("ok"):
                _finish(job_id, state="failed",
                        message=("Nothing was changed, because a copy of "
                                 f"{rel} could not be saved first: "
                                 + str(snap.get("words") or snap.get("error") or "no copy was made")))
                _audit(kind + "_failed", {"job": job_id, "why": "guardian"})
                return
            snaps.append({"rel": rel, "snapshot": snap})
        backup = Path(tempfile.mkdtemp(prefix="jarvis-notes-batch-"))
        backup_rows = []
        for i, (rel, full) in enumerate(snap_files):
            old = _read_bytes(full)
            name = f"{i}.bin"
            (backup / name).write_bytes(old)
            backup_rows.append({"rel": rel, "backup": name, "sha256": _sha256(old)})
        before = {"kind": kind, "vault": str(vault), "source": plan["source"],
                  "target": plan["target"], "target_sha": plan["target_sha"],
                  "files": backup_rows, "created_folders": plan["created_folders"],
                  "backup_dir": str(backup)}
        try:
            import jarvis_receipts as R
            rid = R.record(RENAME_RECEIPT if kind == "rename" else MOVE_RECEIPT,
                           plan["preview"], before=before,
                           after={"target": plan["target"], "updates": plan["updates"],
                                  "notes": plan["notes"]},
                           undo=lambda: _batch_restore_before(before))
        except Exception:                                   # noqa: BLE001
            rid = ""
        if not rid:
            _finish(job_id, state="failed",
                    message="Nothing was changed, because an undo receipt could not be recorded first.")
            _audit(kind + "_failed", {"job": job_id, "why": "receipt"})
            return
        created = []
        try:
            for rel in plan["created_folders"]:
                full = vault.joinpath(*rel.split("/"))
                full.mkdir(parents=False, exist_ok=True)
                created.append(rel)
            for row in plan["files"]:
                if row["rel"] == plan["source"]:
                    continue
                _write_note(Path(row["full"]), row["new"])
            if plan["source_unchanged"]:
                os.replace(str(source_full), str(target_full))
            else:
                _write_new_file(target_full, plan["target_data"])
                os.unlink(str(source_full))
            _finish(job_id, state="saved", sha256=plan["target_sha"],
                    target=plan["target"], updates=plan["updates"],
                    notes=plan["notes"], receipt=rid,
                    message=plan["preview"] + " You can undo it.")
            _audit(kind + "d", {"job": job_id, "updates": plan["updates"],
                                "notes": plan["notes"]})
        except Exception as exc:                            # noqa: BLE001
            _batch_restore_before(before)
            _finish(job_id, state="failed",
                    message=(f"The {kind} failed ({type(exc).__name__}), so the copies "
                             "that were saved first were put back."))
            _audit(kind + "_failed", {"job": job_id, "why": "write"})
    except Exception as exc:                                # noqa: BLE001
        _finish(job_id, state="failed",
                message=f"The {kind} failed ({type(exc).__name__}), so nothing was changed.")
        _audit(kind + "_failed", {"job": job_id, "why": "exception"})


def _start_batch_job(kind: str, plan: dict, gate_check, wait_s: float, by: str) -> tuple:
    deleting = kind == "delete"
    with _lock:
        waiting = sum(1 for j in _jobs.values() if j.get("state") == "waiting")
        if waiting >= MAX_WAITING:
            return _error(429, (f"{MAX_WAITING} note changes are already waiting for "
                                "approval - answer those cards first, then ask this one."),
                          state="refused")
        job_id = "notebatch_" + kind + "_" + secrets.token_hex(8)
        _jobs[job_id] = {"id": job_id, "kind": kind, "state": "waiting",
                         "path": plan["rows"][0]["rel"] if deleting else plan["source"],
                         "target": TRASH_DIR if deleting else plan["target"],
                         "updates": 0 if deleting else plan["updates"],
                         "notes": 0 if deleting else plan["notes"],
                         "count": plan["n"] if deleting else None,
                         "message": plan["preview"], "created": time.time(),
                         "updated": time.time(), "by": by}
        while len(_jobs) > MAX_JOBS:
            oldest = min(_jobs, key=lambda k: _jobs[k]["created"])
            _jobs.pop(oldest, None)
    worker = _delete_worker if deleting else _batch_worker
    thread = threading.Thread(target=worker,
                              args=(job_id, plan, gate_check or _gate_check),
                              name="jarvis-note-" + kind, daemon=True)
    thread.start()
    thread.join(max(0.0, float(wait_s)))
    code, out = change_status(job_id)
    if out.get("state") == "waiting":
        out["id"] = job_id
    return (202 if out.get("state") == "waiting" else 200), out


def handle_rename(body, *, gate_check=None, wait_s: float = DEFAULT_WAIT_S,
                  by: str = "") -> tuple:
    """POST /api/notes/rename: same folder, new title, links preserved, one card."""
    if not isinstance(body, dict):
        return _error(400, "Need a JSON object with path and title.", state="refused")
    plan, err = _plan_batch("rename", body, gate_check=gate_check)
    if err is not None:
        return err
    return _start_batch_job("rename", plan, gate_check, wait_s, by)


def handle_move(body, *, gate_check=None, wait_s: float = DEFAULT_WAIT_S,
                by: str = "") -> tuple:
    """POST /api/notes/move: into an existing (or explicitly created) folder."""
    if not isinstance(body, dict):
        return _error(400, "Need a JSON object with path and folder.", state="refused")
    plan, err = _plan_batch("move", body, gate_check=gate_check)
    if err is not None:
        return err
    return _start_batch_job("move", plan, gate_check, wait_s, by)


# ---------------------------------------------------------------------------
#   Deleting notes, one or many, into the vault's own .trash (2026-11-23)
# ---------------------------------------------------------------------------
#
# THE OWNER'S REQUEST, in their words: "i want Jarvis to be able to delete
# obsidian notes , even multiple at a time. but it will always require a card
# with fingerprint or windows hello confirmation", and "it will list the names
# of the notes it wants to delete (from my request) in the card and the
# conversation as well". Asked which shape a delete takes, they chose the
# vault's trash over "gone for good", and twenty notes as the most in one go.
#
# WHY ITS OWN GATE ACTION. `edit_vault_note` (everything else here) is
# reversible and local, so its card is ordinary and its approval is one tap on
# the phone. A delete is raised under `delete_vault_notes` instead, whose own
# `_RISK` row in jarvis_gate.py says "no"/"local": the gate then needs a PERSON
# on every yes - Windows Hello on this PC, or the asking phone's own fingerprint
# or PIN - and refuses a phone with no approval key with the sentence that
# offers to set one up. That is the whole of the owner's requirement, and it is
# the gate's existing machinery rather than a second permission path.
#
# WHY "cannot be undone" IS TRUE OF AN APP, THOUGH THE BYTES SURVIVE. The note
# is MOVED, never written over: `os.replace` into `<vault>/.trash/<same path>`,
# created when it is not there yet, and a name already in the trash gets
# " (2)". Obsidian does not show or restore that folder, this editor cannot
# read a hidden path (`note_parts` refuses any dot-prefixed component), and no
# Undo receipt is recorded for a delete - so neither app can put one back. The
# owner can, from Explorer: the reply names the folder and the notes, which is
# why the honest card says "moved out of your vault", never "destroyed".
#
# WHAT IS REFUSED BEFORE ANY CARD: no paths at all, more than MAX_DELETE, the
# same note named twice, a path that is not a vault-relative .md/.txt
# (`note_parts`), a hidden folder, a link or junction anywhere in the path, a
# Protected path, a note that is not there, and a note whose bytes cannot be
# read. Nothing is moved until every one of those has passed for EVERY path, and
# the whole batch is verified again after the card is approved.


def _delete_target(vault: Path, rel: str, taken=None) -> str:
    """Where one note's bytes go inside `.trash`, never over another file.

    `taken` carries the targets this SAME batch has already chosen. The disk
    check alone is not enough: delete ["Foo.md", "Foo (2).md"] while
    `.trash/Foo.md` already exists, and both rows would be handed
    `.trash/Foo (2).md`, because neither move has happened yet when the second
    target is chosen - the second `os.replace` would then overwrite the first
    note while the reply said both moved.
    """
    claimed = taken if taken is not None else set()
    stem, suffix = os.path.splitext(rel)
    for n in range(1, 100):
        cand = rel if n == 1 else f"{stem} ({n}){suffix}"
        if cand.casefold() in claimed:
            continue
        if not vault.joinpath(TRASH_DIR, *cand.split("/")).exists():
            return cand
    raise OSError("the trash folder already holds too many notes with that name")


def _delete_preview(plan: dict) -> str:
    """The sentence the conversation and the card both start from."""
    n = plan["n"]
    one = "note" if n == 1 else "notes"
    if plan["hidden"]:
        return (f"This moves {n} {one} out of your Obsidian vault and into its "
                ".trash folder.")
    if n == 1:
        return (f'This moves the note "{plan["names"][0]}" out of your Obsidian '
                "vault and into its .trash folder.")
    return (f"These {n} notes move out of your Obsidian vault and into its .trash "
            "folder: " + ", ".join(f'"{p}"' for p in plan["names"]) + ".")


def _delete_prompt_detail(plan: dict) -> tuple:
    """The card's own line and detail - every note named, unless lists are hidden."""
    n = plan["n"]
    one = "note" if n == 1 else "notes"
    if plan["hidden"]:
        prompt = f"delete {n} {one} from your Obsidian vault"
        detail = {"action": "delete notes", "count": n, "trash": True,
                  "undo": False, "deletes": True, "hidden_lists": True}
        return prompt, detail
    names = ", ".join(f'"{p}"' for p in plan["names"])
    prompt = f'delete {names} from your Obsidian vault' if n == 1 \
        else f"delete {n} notes from your Obsidian vault: {names}"
    detail = {"action": "delete notes", "count": n, "paths": plan["names"],
              "trash": True, "undo": False, "deletes": True}
    return prompt, detail


def _plan_delete(body: dict) -> tuple:
    """`(plan dict, error tuple)`; every refusal happens before any card."""
    if not isinstance(body, dict):
        return None, _error(400, "Need a JSON object with a list of note paths.",
                            state="refused")
    raw = body.get("paths")
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list) or not raw:
        return None, _error(400, ("Say which notes to delete: send a list of note "
                                  "paths inside your Obsidian vault."),
                            state="refused")
    if len(raw) > MAX_DELETE:
        return None, _error(400, (f"I delete up to {MAX_DELETE} notes at a time, and "
                                  f"{len(raw)} were named, so nothing was deleted."),
                            state="refused")
    vault, why = _vault()
    if vault is None:
        return None, _error(503, "Nothing was deleted: " + why + ".", state="refused")
    _P = _protection()
    rows, seen, taken = [], set(), set()
    for one in raw:
        full, rel, why = _resolve_note(one)
        if why:
            return None, _error(400, "Nothing was deleted: " + why + ".", state="refused")
        key = rel.casefold()
        if key in seen:
            return None, _error(400, (f"{rel} was named twice, so nothing was "
                                     "deleted."), state="refused")
        seen.add(key)
        if not full.is_file():
            return None, _error(404, (f"There is no note at {rel} in your Obsidian "
                                      "vault, so nothing was deleted."),
                                state="refused")
        if _P is not None:
            said = _P.path_refusal(str(full), write=True)
            if said:
                return None, _error(403, said, state="refused")
        try:
            data = _read_bytes(full)
        except OSError:
            return None, _error(503, (f"{rel} could not be read, so nothing was "
                                      "deleted."), state="refused")
        try:
            target_rel = _delete_target(vault, rel, taken)
        except OSError:
            return None, _error(409, (f"The trash folder already holds too many notes "
                                      f"called {rel}, so nothing was deleted."),
                                state="refused")
        taken.add(target_rel.casefold())
        rows.append({"rel": rel, "full": str(full), "sha256": _sha256(data),
                     "bytes": len(data), "target": target_rel})
    plan = {"kind": "delete", "vault": str(vault), "rows": rows, "n": len(rows),
            "names": [r["rel"] for r in rows], "hidden": _hidden_lists()}
    plan["preview"] = _delete_preview(plan)
    return plan, None


def _delete_verify(plan: dict) -> str:
    """Empty when every note is still the one the card named; else plain words."""
    for row in plan["rows"]:
        full = Path(row["full"])
        if not full.is_file() or _is_link_or_reparse(full):
            return (f"{row['rel']} is no longer in your Obsidian vault, so nothing "
                    "was deleted.")
        try:
            if _sha256(_read_bytes(full)) != row["sha256"]:
                return (f"{row['rel']} changed while the card waited, so nothing was "
                        "deleted.")
        except OSError:
            return f"{row['rel']} could not be re-read, so nothing was deleted."
    return ""


def _deleted_words(plan: dict) -> str:
    """What the conversation says once the notes have moved."""
    n = plan["n"]
    one = "note" if n == 1 else "notes"
    if plan["hidden"]:
        return (f"Moved {n} {one} out of your Obsidian vault and into its .trash "
                "folder.")
    if n == 1:
        return (f'Moved "{plan["names"][0]}" into the vault\'s .trash folder. You can '
                "put it back from Windows Explorer.")
    return (f'Moved {n} notes into the vault\'s .trash folder: '
            + ", ".join(f'"{p}"' for p in plan["names"])
            + ". You can put one back from Windows Explorer.")


def _delete_worker(job_id: str, plan: dict, gate_check) -> None:
    """Ask the gate, then (and only then) move the notes into `.trash`."""
    try:
        prompt, detail = _delete_prompt_detail(plan)
        verdict = gate_check(DELETE_ACTION, detail, prompt)
        if not getattr(verdict, "allowed", False):
            outcome = str(getattr(verdict, "outcome", "refused") or "refused")
            state = "denied" if outcome in ("denied", "timed_out") else "failed"
            _finish(job_id, state=state, outcome=outcome,
                    message=_REFUSED_WRITE["delete"].get(
                        outcome, "The approval gate refused it, so no note was deleted."))
            _audit("delete_refused", {"job": job_id, "outcome": outcome,
                                      "count": plan["n"]})
            return
        # The card was read from a plan; the disk is what counts now.
        why = _delete_verify(plan)
        if why:
            _finish(job_id, state="failed", message=why)
            _audit("delete_failed", {"job": job_id, "why": "changed"})
            return
        vault = Path(plan["vault"])
        trash = vault / TRASH_DIR
        # A free name was chosen when the card was raised; os.replace() would
        # silently overwrite a file that took that exact name while the card
        # waited, so the whole batch refuses instead, before anything moves.
        taken_now = [row["rel"] for row in plan["rows"]
                     if trash.joinpath(*row["target"].split("/")).exists()]
        if taken_now:
            _finish(job_id, state="failed",
                    message=("A file named like the trash copy appeared while the "
                             "card waited, so nothing was deleted: "
                             + ", ".join(taken_now) + "."))
            _audit("delete_failed", {"job": job_id, "why": "trash-name-taken"})
            return
        moved = []
        try:
            for row in plan["rows"]:
                target = trash.joinpath(*row["target"].split("/"))
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(row["full"], str(target))
                moved.append(row)
            _finish(job_id, state="saved", target=TRASH_DIR, count=plan["n"],
                    paths=[] if plan["hidden"] else list(plan["names"]),
                    message=_deleted_words(plan))
            _audit("deleted", {"job": job_id, "count": plan["n"]})
        except Exception as exc:                            # noqa: BLE001
            put_back, stuck = [], []
            for row in moved:
                try:
                    os.replace(str(trash.joinpath(*row["target"].split("/"))),
                               row["full"])
                    put_back.append(row["rel"])
                except Exception:                        # noqa: BLE001
                    stuck.append(row["rel"])
            if stuck:
                said = (f"The delete failed ({type(exc).__name__}). {len(put_back)} of "
                        f"{plan['n']} were put back; {', '.join(stuck)} could not be, "
                        "and are in the vault's .trash folder.")
            else:
                said = (f"The delete failed ({type(exc).__name__}), so the notes that "
                        "had moved were put back.")
            _finish(job_id, state="failed", message=said)
            _audit("delete_failed", {"job": job_id, "why": "write",
                                     "stuck": len(stuck)})
    except Exception as exc:                                # noqa: BLE001
        _finish(job_id, state="failed",
                message=(f"The delete failed ({type(exc).__name__}), so no note was "
                         "deleted."))
        _audit("delete_failed", {"job": job_id, "why": "exception"})


def handle_delete(body, *, gate_check=None, wait_s: float = DEFAULT_WAIT_S,
                  by: str = "") -> tuple:
    """POST /api/notes/delete: move one or more notes into the vault's trash.

    One card for the whole batch, under `DELETE_ACTION`, and the card names every
    note. Nothing is moved until that card is approved. The answer is the
    module's ordinary change shape: 202 while the card waits, 200 once it has
    been answered, `GET /api/notes/change?id=` for the rest.
    """
    plan, err = _plan_delete(body)
    if err is not None:
        return err
    return _start_batch_job("delete", plan, gate_check, wait_s, by)


try:
    import jarvis_receipts as _RENAME_RC
    _RENAME_RC.register_restorer(RENAME_RECEIPT, _batch_restore_before)
    _RENAME_RC.register_restorer(MOVE_RECEIPT, _batch_restore_before)
except Exception:                                           # noqa: BLE001
    pass


# ---------------------------------------------------------------------------
#   Copying ONE note (2026-11-25) - additive, so a direct owner write is card-free
# ---------------------------------------------------------------------------
#
# WHY CARDLESS. The owner's standing model (2026-10-31, and the reason create is
# card-free) is that a brand-new file cannot overwrite or remove anything: a copy
# is one more note, and one Undo removes exactly it. So a direct owner write in
# the HUD (typed or voice) takes the same no-card path create takes, with the
# same 64 KB cap and the same receipt recorded before the file exists. Every
# other caller - a background job, another client, a write after outside text -
# keeps ONE `edit_vault_note` card, exactly as create does.
#
# WHAT IT COPIES. The note's bytes, verbatim: a duplicate is a duplicate, so a
# note's properties, tags, links and words all survive. That also means a copied
# `aliases:` line points two notes at one name; the resolver's own ambiguity
# refusal already answers that in words ("matches 2 notes"), which is the honest
# behaviour rather than this writer editing the copy's frontmatter unasked.

COPY_SUFFIX = " copy"


def _copy_target(vault: Path, source_rel: str, wanted) -> tuple:
    """`(target_rel, why)` - a free path for the copy, never over another file."""
    parent = os.path.dirname(source_rel).replace("\\", "/").strip("/")
    stem, suffix = os.path.splitext(os.path.basename(source_rel))
    raw = str(wanted or "").strip().strip('"').strip("'")
    if raw:
        if "/" in raw or "\\" in raw:
            parts, why = note_parts(raw)
            if why:
                return "", why
            return "/".join(parts), ""
        name = raw
        if name.lower().endswith((".md", ".txt")):
            name = name[:-len(".md")] if name.lower().endswith(".md") else name[:-4]
        if _BAD_FILENAME.search(name) or name.startswith("."):
            return "", ("a note name cannot contain < > : \" / \\ | ? * or start "
                        "with a dot")
        if len(name) > 120:
            return "", "that note name is longer than the editor's 120-character limit"
        stem = name
        cand = (parent + "/" + stem + suffix) if parent else (stem + suffix)
        if not vault.joinpath(*cand.split("/")).exists() \
                and not _case_exists(vault.joinpath(*parent.split("/")) if parent else vault,
                                     stem + suffix):
            return cand, ""
        return "", f'There is already a note called "{stem}", so nothing was copied.'
    for n in range(1, 100):
        name = stem + COPY_SUFFIX + ("" if n == 1 else " " + str(n))
        cand = (parent + "/" + name + suffix) if parent else (name + suffix)
        folder = vault.joinpath(*parent.split("/")) if parent else vault
        if not vault.joinpath(*cand.split("/")).exists() \
                and not _case_exists(folder, name + suffix):
            return cand, ""
    return "", "there are already too many copies of that note in its folder"


def _plan_copy(body: dict) -> tuple:
    """`(plan dict, error tuple)`; every refusal happens before any card."""
    raw, why = _one_path(body)
    if why:
        return None, _error(400, why, state="refused")
    source_full, source_rel, why = _resolve_note(raw)
    if why:
        return None, _error(400, why, state="refused")
    if not source_full.is_file():
        return None, _error(404, (f"There is no note at {source_rel} in your Obsidian "
                                  "vault, so nothing was copied."), state="refused")
    _P = _protection()
    if _P is not None:
        said = _P.path_refusal(str(source_full), write=True)
        if said:
            return None, _error(403, said, state="refused")
    vault, why = _vault()
    if vault is None:
        return None, _error(503, "Nothing was copied: " + why + ".", state="refused")
    try:
        data = _read_bytes(source_full)
    except OSError as exc:
        return None, _error(503, (f"The note could not be read "
                                  f"({type(exc).__name__}), so nothing was copied."),
                            state="refused")
    target_rel, why = _copy_target(vault, source_rel,
                                   body.get("as") or body.get("new_name")
                                   or body.get("target") or body.get("new_path"))
    if why:
        return None, _error(409 if "already a note" in why else 400, why,
                            state="refused")
    target_full = vault.joinpath(*target_rel.split("/"))
    if not _inside(vault, target_full) or not _inside(vault, target_full.parent):
        return None, _error(400, "the copy would land outside your Obsidian vault",
                            state="refused")
    if _P is not None:
        said = _P.path_refusal(str(target_full), write=True)
        if said:
            return None, _error(403, said, state="refused")
    return {"source": source_rel, "target": target_rel, "data": data,
            "vault": str(vault), "hidden": _hidden_lists(),
            "bytes": len(data)}, None


def handle_copy(body, *, gate_check=None, wait_s: float = DEFAULT_WAIT_S,
                by: str = "", provenance: str = "typed",
                client: str = "hud") -> tuple:
    """POST /api/notes/copy: duplicate ONE note; additive, so usually no card."""
    plan, err = _plan_copy(body)
    if err is not None:
        return err
    vault = Path(plan["vault"])
    body_prov = str((body or {}).get("provenance") or provenance or "typed").strip().lower()
    body_client = str((body or {}).get("client") or client or "").strip().lower()
    owner_direct = body_prov in ("typed", "voice") and body_client == "hud"
    if owner_direct:
        target_full = vault.joinpath(*plan["target"].split("/"))
        return _create_now(target_full, plan["target"], plan["data"])
    target_full = vault.joinpath(*plan["target"].split("/"))
    return _start_change_job("copy", target_full, plan["target"], plan["data"], "",
                             vault, gate_check, wait_s, by,
                             {"source": plan["source"]})


# ---------------------------------------------------------------------------
#   Merging notes into ONE survivor (2026-11-25)
# ---------------------------------------------------------------------------
#
# THE OWNER'S REQUEST: "i want atlas to have full control and full ability to
# manipulate and change any of my notes, with deletions requiring a card of
# approval". A merge is the one verb that writes AND deletes in one act, so it
# is built to the strictest of the two:
#
#   * ONE card, under `delete_vault_notes` - not `edit_vault_note` - because a
#     note really does leave the vault when the merge is done. Its row already
#     says every byte is kept in the vault's .trash and that neither app can put
#     the note back, which is exactly true here, and its words are what title the
#     Windows Hello prompt.
#   * The card names the SURVIVOR and every note that goes, and how many lines
#     each contributes, so "which one survives" is on the card in the owner's own
#     words rather than implied by field order.
#   * Nothing is written until the card is answered; a Deny writes nothing and
#     says so. After the yes, every note is re-verified against the sha256 the
#     card named, so a note edited while the card waited refuses the whole merge.
#   * The absorbed notes are MOVED into .trash, never written over: the bytes
#     survive, and the reply names the folder, exactly as a delete's does.
#
# WHAT LANDS IN THE SURVIVOR. Each absorbed note's BODY (its text after any front
# matter) is appended below the survivor's own words, behind one invisible
# marker line naming where it came from. An HTML comment renders as nothing in
# Obsidian, so the merge reads as one note - while the provenance is still
# readable in the file itself, which a plain concatenation would lose.
MERGE_MARK = "<!-- merged from \"{name}\" -->"


def _body_of(text: str) -> str:
    """One note's own words: everything after a closed front matter block."""
    _opened, _front, body, _why = _split_frontmatter(str(text or ""))
    return body


def _merge_block(source_title: str, source_text: str, eol: str) -> str:
    """The bytes one absorbed note contributes to the survivor."""
    body = _body_of(source_text).replace("\r\n", eol).replace("\n", eol).strip("\r\n")
    mark = MERGE_MARK.format(name=source_title.replace('"', "'"))
    return mark + eol + (body + eol if body else "")


def _plan_merge(body: dict) -> tuple:
    """`(plan dict, error tuple)`; every refusal happens before any card."""
    if not isinstance(body, dict):
        return None, _error(400, "Need a JSON object naming the notes to merge.",
                            state="refused")
    into_raw = body.get("into") or body.get("survivor") or body.get("target")
    if not isinstance(into_raw, str) or not into_raw.strip():
        return None, _error(400, ("Say which note should survive: send `into` as "
                                  "that note's path."), state="refused")
    raw = body.get("paths") or body.get("notes") or body.get("sources")
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list) or not raw:
        return None, _error(400, ("Say which notes to fold in: send `paths` as a "
                                  "list of note paths."), state="refused")
    if len(raw) > MAX_MERGE:
        return None, _error(400, (f"I merge up to {MAX_MERGE} notes at a time, and "
                                  f"{len(raw)} were named, so nothing was merged."),
                            state="refused")
    vault, why = _vault()
    if vault is None:
        return None, _error(503, "Nothing was merged: " + why + ".", state="refused")
    _P = _protection()
    into_full, into_rel, why = _resolve_note(into_raw)
    if why:
        return None, _error(400, "Nothing was merged: " + why + ".", state="refused")
    if not into_full.is_file():
        return None, _error(404, (f"There is no note at {into_rel} in your Obsidian "
                                  "vault, so nothing was merged."), state="refused")
    if _P is not None:
        said = _P.path_refusal(str(into_full), write=True)
        if said:
            return None, _error(403, said, state="refused")
    try:
        into_text = _read_bytes(into_full).decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return None, _error(400, (f"{into_rel} could not be read as text "
                                  f"({type(exc).__name__}), so nothing was merged."),
                            state="refused")
    eol = _eol_of(into_text)
    rows, seen, taken = [], {into_rel.casefold()}, set()
    for one in raw:
        full, rel, why = _resolve_note(one)
        if why:
            return None, _error(400, "Nothing was merged: " + why + ".", state="refused")
        key = rel.casefold()
        if key in seen:
            return None, _error(400, (f"{rel} was named twice, so nothing was "
                                      "merged."), state="refused")
        seen.add(key)
        if not full.is_file():
            return None, _error(404, (f"There is no note at {rel} in your Obsidian "
                                      "vault, so nothing was merged."), state="refused")
        if _P is not None:
            said = _P.path_refusal(str(full), write=True)
            if said:
                return None, _error(403, said, state="refused")
        try:
            data = _read_bytes(full)
            text = data.decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            return None, _error(400, (f"{rel} could not be read as text "
                                      f"({type(exc).__name__}), so nothing was "
                                      "merged."), state="refused")
        try:
            target_rel = _delete_target(vault, rel, taken)
        except OSError:
            return None, _error(409, (f"The trash folder already holds too many "
                                      f"notes called {rel}, so nothing was merged."),
                                state="refused")
        taken.add(target_rel.casefold())
        title = Path(rel).stem
        rows.append({"rel": rel, "full": str(full), "sha256": _sha256(data),
                     "bytes": len(data), "target": target_rel, "title": title,
                     "lines": len(_lines(_body_of(text)))})
    merged = into_text
    for row in rows:
        try:
            absorbed = Path(row["full"]).read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError):       # re-read: it was read above
            return None, _error(503, (f"{row['rel']} could not be re-read, so nothing "
                                      "was merged."), state="refused")
        block = _merge_block(row["title"], absorbed, eol)
        if not merged.endswith(("\n", "\r")):
            merged += eol
        if not merged.endswith(eol + eol):
            merged += eol
        merged += block
    data = merged.encode("utf-8", errors="surrogatepass")
    if len(data) > MAX_FILE_BYTES:
        return None, _error(413, (f"The merged note would be {len(data)} bytes, over "
                                  f"the {MAX_FILE_BYTES} byte limit, so nothing was "
                                  "merged."), state="refused")
    plan = {"kind": "merge", "vault": str(vault), "into": into_rel,
            "into_full": str(into_full), "into_sha": _sha256(into_text.encode("utf-8")),
            "rows": rows, "n": len(rows),
            "names": [r["rel"] for r in rows],
            "lines_added": sum(r["lines"] for r in rows),
            "hidden": _hidden_lists()}
    plan["preview"] = _merge_preview(plan)
    plan["data"] = data
    return plan, None


def _merge_preview(plan: dict) -> str:
    """The sentence the conversation and the card both start from."""
    n = plan["n"]
    one = "note" if n == 1 else "notes"
    if plan["hidden"]:
        return (f"This merges {n} {one} into one note and moves the other one out "
                "of your Obsidian vault and into its .trash folder.")
    if n == 1:
        return (f'This merges "{plan["names"][0]}" into "{plan["into"]}" and moves '
                "it out of your Obsidian vault and into its .trash folder.")
    return (f'These {n} notes are merged into "{plan["into"]}" and move out of your '
            "Obsidian vault and into its .trash folder: "
            + ", ".join(f'"{p}"' for p in plan["names"]) + ".")


def _merge_prompt_detail(plan: dict) -> tuple:
    """The card's own line and detail - the survivor, every note, the line counts."""
    n = plan["n"]
    if plan["hidden"]:
        return (f"merge {n} note(s) into one note in your Obsidian vault and move "
                f"{n} into its .trash folder",
                {"action": "merge notes", "count": n, "trash": True,
                 "undo": False, "deletes": True, "hidden_lists": True})
    names = ", ".join(f'"{p}"' for p in plan["names"])
    tail = ("and it moves into the vault's .trash folder" if n == 1
            else f"and the other {n} move into the vault's .trash folder")
    prompt = (f'merge {names} into "{plan["into"]}" in your Obsidian vault: '
              f'"{plan["into"]}" survives and gains {plan["lines_added"]} line(s), '
              f"{tail}")
    detail = {"action": "merge notes", "into": plan["into"], "count": n,
              "paths": list(plan["names"]), "survivor": plan["into"],
              "lines_added": plan["lines_added"], "trash": True,
              "undo": False, "deletes": True}
    return prompt, detail


def _merge_verify(plan: dict) -> str:
    """Empty when every note is still the one the card named; else plain words."""
    try:
        if _sha256(_read_bytes(Path(plan["into_full"]))) != plan["into_sha"]:
            return (f'{plan["into"]} changed while the card waited, so nothing was '
                    "merged.")
    except OSError:
        return f'{plan["into"]} could not be re-read, so nothing was merged.'
    why = _delete_verify(plan)
    if why:
        return why.replace("deleted", "merged")
    return ""


def _merge_worker(job_id: str, plan: dict, gate_check) -> None:
    """Ask the gate, then (and only then) write the survivor and trash the rest."""
    try:
        prompt, detail = _merge_prompt_detail(plan)
        verdict = gate_check(DELETE_ACTION, detail, prompt)
        if not getattr(verdict, "allowed", False):
            outcome = str(getattr(verdict, "outcome", "refused") or "refused")
            state = "denied" if outcome in ("denied", "timed_out") else "failed"
            _finish(job_id, state=state, outcome=outcome,
                    message=_REFUSED_WRITE["merge"].get(
                        outcome, "The approval gate refused it, so nothing was merged."))
            _audit("merge_refused", {"job": job_id, "outcome": outcome,
                                     "count": plan["n"]})
            return
        why = _merge_verify(plan)
        if why:
            _finish(job_id, state="failed", message=why)
            _audit("merge_failed", {"job": job_id, "why": "changed"})
            return
        vault = Path(plan["vault"])
        trash = vault / TRASH_DIR
        taken_now = [row["rel"] for row in plan["rows"]
                     if trash.joinpath(*row["target"].split("/")).exists()]
        if taken_now:
            _finish(job_id, state="failed",
                    message=("A file named like the trash copy appeared while the "
                             "card waited, so nothing was merged: "
                             + ", ".join(taken_now) + "."))
            _audit("merge_failed", {"job": job_id, "why": "trash-name-taken"})
            return
        into_full = Path(plan["into_full"])
        old_into = _read_bytes(into_full)
        snap = _snapshot(into_full, plan["into"])
        if not snap.get("ok"):
            words = str(snap.get("words") or snap.get("error") or "no copy was made")
            _finish(job_id, state="failed",
                    message=("Nothing was merged, because a copy of "
                             f'{plan["into"]} could not be saved first: ' + words))
            _audit("merge_failed", {"job": job_id, "why": "guardian"})
            return
        moved = []
        try:
            _write_note(into_full, plan["data"])
        except OSError as exc:
            _finish(job_id, state="failed",
                    message=(f"The merged note could not be written "
                             f"({type(exc).__name__}), so nothing was merged."))
            _audit("merge_failed", {"job": job_id, "why": "write"})
            return
        try:
            for row in plan["rows"]:
                target = trash.joinpath(*row["target"].split("/"))
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(row["full"], str(target))
                moved.append(row)
        except Exception as exc:                            # noqa: BLE001
            put_back, stuck = [], []
            for row in moved:
                try:
                    os.replace(str(trash.joinpath(*row["target"].split("/"))),
                               row["full"])
                    put_back.append(row["rel"])
                except Exception:                        # noqa: BLE001
                    stuck.append(row["rel"])
            try:
                _write_note(into_full, old_into)
            except OSError:
                stuck.append(plan["into"])
            if stuck:
                said = (f"The merge failed ({type(exc).__name__}). "
                        f'{plan["into"]} was put back; {", ".join(stuck)} could not '
                        "be, and are in the vault's .trash folder.")
            else:
                said = (f"The merge failed ({type(exc).__name__}), so every note was "
                        "put back exactly as it was.")
            _finish(job_id, state="failed", message=said)
            _audit("merge_failed", {"job": job_id, "why": "write",
                                    "stuck": len(stuck)})
            return
        _finish(job_id, state="saved", target=plan["into"], count=plan["n"],
                paths=[] if plan["hidden"] else list(plan["names"]),
                message=_merged_words(plan))
        _audit("merged", {"job": job_id, "count": plan["n"],
                          "into": plan["into"]})
    except Exception as exc:                                # noqa: BLE001
        _finish(job_id, state="failed",
                message=(f"The merge failed ({type(exc).__name__}), so nothing was "
                         "merged."))
        _audit("merge_failed", {"job": job_id, "why": "exception"})


def _merged_words(plan: dict) -> str:
    """What the conversation says once the merge has landed."""
    n = plan["n"]
    if plan["hidden"]:
        return ("Merged the notes into one and moved the others into the vault's "
                ".trash folder.")
    if n == 1:
        return (f'Merged "{plan["names"][0]}" into "{plan["into"]}". The merged note '
                "is in your vault, and the other one is in the vault's .trash folder.")
    return (f'Merged {n} notes into "{plan["into"]}". They are now in the vault\'s '
            ".trash folder: " + ", ".join(f'"{p}"' for p in plan["names"]) + ".")


def handle_merge(body, *, gate_check=None, wait_s: float = DEFAULT_WAIT_S,
                 by: str = "") -> tuple:
    """POST /api/notes/merge: fold one or more notes into ONE survivor, one card."""
    plan, err = _plan_merge(body)
    if err is not None:
        return err
    with _lock:
        waiting = sum(1 for j in _jobs.values() if j.get("state") == "waiting")
        if waiting >= MAX_WAITING:
            return _error(429, (f"{MAX_WAITING} note changes are already waiting for "
                                "approval - answer those cards first, then ask this "
                                "one."), state="refused")
        job_id = "notemerge_" + secrets.token_hex(8)
        _jobs[job_id] = {"id": job_id, "kind": "merge", "state": "waiting",
                         "path": plan["into"], "target": plan["into"],
                         "count": plan["n"], "paths": list(plan["names"]),
                         "message": plan["preview"], "created": time.time(),
                         "updated": time.time(), "by": by}
        while len(_jobs) > MAX_JOBS:
            oldest = min(_jobs, key=lambda k: _jobs[k]["created"])
            _jobs.pop(oldest, None)
    thread = threading.Thread(target=_merge_worker,
                              args=(job_id, plan, gate_check or _gate_check),
                              name="jarvis-note-merge", daemon=True)
    thread.start()
    thread.join(max(0.0, float(wait_s)))
    code, out = change_status(job_id)
    if out.get("state") == "waiting":
        out["id"] = job_id
    return (202 if out.get("state") == "waiting" else 200), out


# ---------------------------------------------------------------------------
#   Emptying the vault's own .trash folder (2026-11-25)
# ---------------------------------------------------------------------------
#
# WHY. Obsidian's `.trash` folder has no timer: a note deleted last month is
# still there, so the folder grows for ever. Until now nothing could empty it -
# every route here refuses a dot-prefixed path - so the owner's own deletions
# accumulated with no way to finish the job from either app.
#
# WHY ITS OWN CARD AND ITS OWN ACTION. This is the ONE note operation that
# really destroys bytes: no Undo receipt, no File Guardian copy of what is in the
# trash (it IS the copy), and nothing left for Explorer to restore. Neither
# `edit_vault_note` ("the old text is copied first") nor `delete_vault_notes`
# ("every byte is kept in .trash") can say that honestly, so it is asked under
# `empty_vault_trash`, whose `_RISK` row says it cannot be undone. The row lives
# in the published base (`jarvis-backend/jarvis_gate.py`) with the other
# end-of-file update blocks, and reaches a live install through
# `tools/repair_live_backend_gaps.py` - never a new patch.
#
# WHAT THE CARD SHOWS. Every file, with its name and how many days old it is,
# the count and the total size. An age is the thing that tells the owner whether
# they are about to throw away yesterday's mistake before they notice it, or
# three weeks of clutter - so it is on the card, not in a log.
TRASH_EMPTY_SAID = ("The vault's trash folder is already empty, so there was "
                    "nothing to empty and no card was raised.")
TRASH_NUDGE_SAID = ('Your vault\'s .trash folder has {why}. Say "empty the vault '
                    'trash" and I will list every file on one card before anything '
                    'is deleted.')


def _size_words(total: int) -> str:
    """A byte count in words a beginner reads at a glance (never "0.0 KB")."""
    if total >= 1024 * 1024:
        return f"{round(total / (1024 * 1024), 1)} MB"
    if total >= 1024:
        return f"{round(total / 1024, 1)} KB"
    return f"{total} byte{'' if total == 1 else 's'}"


def _trash_rows(vault: Path, *, now: float = None) -> list:
    """Every FILE in `<vault>/.trash`, with its size and age; never a symlink."""
    stamp = time.time() if now is None else float(now)
    root = vault / TRASH_DIR
    rows = []
    if not root.is_dir():
        return rows
    for dirpath, dirnames, filenames in os.walk(str(root), followlinks=False):
        here = Path(dirpath)
        dirnames[:] = sorted(d for d in dirnames
                             if not _is_link_or_reparse(here / d))
        for name in sorted(filenames):
            full = here / name
            if _is_link_or_reparse(full):
                continue
            try:
                st = os.stat(str(full))
            except OSError:
                continue
            rel = os.path.relpath(str(full), str(root)).replace(os.sep, "/")
            rows.append({"rel": rel, "full": str(full), "bytes": int(st.st_size),
                         "mtime": float(st.st_mtime),
                         "age_days": max(0, int((stamp - float(st.st_mtime)) // 86400))})
    return rows


def trash_state(*, now: float = None) -> dict:
    """The trash folder's own numbers: count, bytes, oldest age, and any nudge.

    Read-only, and the ONE place the three thresholds live: every caller that
    wants to mention the trash asks this, so the answer cannot differ between the
    card, chat and the GET route. `nudge` is "" unless one of the owner's three
    thresholds is passed (the ruling of 2026-11-25) - a handful of recent files
    says nothing at all, ever.
    """
    vault, why = _vault()
    if vault is None:
        return {"ok": False, "readable": False, "why": why, "count": 0,
                "bytes": 0, "oldest_days": 0, "nudge": ""}
    rows = _trash_rows(vault, now=now)
    total = sum(r["bytes"] for r in rows)
    oldest = max((r["age_days"] for r in rows), default=0)
    tripped = []
    if total > TRASH_NUDGE_BYTES:
        tripped.append(f"{len(rows)} file(s) taking {round(total / (1024 * 1024), 1)} MB")
    if len(rows) > TRASH_NUDGE_FILES:
        tripped.append(f"{len(rows)} files in it")
    if oldest > TRASH_NUDGE_DAYS:
        tripped.append(f"a file {oldest} days old in it")
    nudge = ""
    if tripped:
        nudge = TRASH_NUDGE_SAID.format(why=tripped[0])
    return {"ok": True, "readable": True, "why": "", "count": len(rows),
            "bytes": total, "oldest_days": oldest, "nudge": nudge,
            "rows": rows}


def trash_nudge(*, now: float = None) -> str:
    """The ONE quiet line, or "" - never a card, never a write."""
    try:
        return str(trash_state(now=now).get("nudge") or "")
    except Exception:                                       # noqa: BLE001
        return ""


def _trash_prompt_detail(rows: list) -> tuple:
    """The card's own line and detail: EVERY file, its age, the count and size."""
    total = sum(r["bytes"] for r in rows)
    size = _size_words(total)
    listing = "; ".join(f'"{r["rel"]}" ({r["age_days"]} day'
                        f'{"s" if r["age_days"] != 1 else ""} old)' for r in rows)
    prompt = (f"empty the vault's trash folder: {len(rows)} file(s) taking {size}, "
              f"and this cannot be undone - {listing}")
    detail = {"action": "empty the vault trash", "count": len(rows),
              "bytes": total, "files": [r["rel"] for r in rows],
              "ages": [r["age_days"] for r in rows],
              "undo": False, "deletes": True}
    return prompt, detail


def _empty_trash_words(rows: list) -> str:
    total = sum(r["bytes"] for r in rows)
    return (f"Emptied the vault's trash folder: {len(rows)} file(s), {total} byte(s) "
            "gone for good. This cannot be undone.")


def _empty_trash_worker(job_id: str, plan: dict, gate_check) -> None:
    """Ask the card, then (and only then) delete every file in `.trash`."""
    try:
        prompt, detail = _trash_prompt_detail(plan["rows"])
        verdict = gate_check(EMPTY_TRASH_ACTION, detail, prompt)
        if not getattr(verdict, "allowed", False):
            outcome = str(getattr(verdict, "outcome", "refused") or "refused")
            state = "denied" if outcome in ("denied", "timed_out") else "failed"
            _finish(job_id, state=state, outcome=outcome,
                    message=_REFUSED_WRITE["empty_trash"].get(
                        outcome, "The approval gate refused it, so nothing was "
                                 "deleted."))
            _audit("empty_trash_refused", {"job": job_id, "outcome": outcome,
                                           "count": plan["count"]})
            return
        vault, why = _vault()
        if vault is None:
            _finish(job_id, state="failed",
                    message="The Obsidian vault could not be found, so nothing was "
                            "deleted.")
            return
        rows = _trash_rows(vault)
        if len(rows) != plan["count"] or any(
                r["rel"] not in plan["names"] for r in rows):
            _finish(job_id, state="failed",
                    message=("The trash folder changed while the card waited, so "
                             "nothing was deleted; ask again to see the new list."))
            _audit("empty_trash_failed", {"job": job_id, "why": "changed"})
            return
        gone, stuck = [], []
        for row in rows:
            try:
                os.unlink(row["full"])
                gone.append(row["rel"])
            except OSError:
                stuck.append(row["rel"])
        if stuck:
            _finish(job_id, state="failed",
                    message=(f"{len(gone)} file(s) were deleted and {len(stuck)} "
                             "could not be: " + ", ".join(stuck) + "."))
            _audit("empty_trash_failed", {"job": job_id, "why": "unlink",
                                          "stuck": len(stuck)})
            return
        _finish(job_id, state="saved", count=len(gone), paths=list(plan["names"]),
                message=_empty_trash_words(plan["rows"]))
        _audit("empty_trash", {"job": job_id, "count": len(gone)})
    except Exception as exc:                                # noqa: BLE001
        _finish(job_id, state="failed",
                message=(f"Emptying the trash failed ({type(exc).__name__}), so "
                         "nothing was deleted."))
        _audit("empty_trash_failed", {"job": job_id, "why": "exception"})


def handle_empty_trash(body=None, *, gate_check=None,
                       wait_s: float = DEFAULT_WAIT_S, by: str = "") -> tuple:
    """POST /api/notes/trash: empty the vault's own .trash folder, one card.

    An EMPTY trash is a 200 with its own sentence and NO card: there is nothing
    to approve. More files than `MAX_DELETE` is refused with the count stated, so
    the folder is emptied whole or not at all - never half-empty.
    """
    vault, why = _vault()
    if vault is None:
        return _error(503, "Nothing was deleted: " + why + ".", state="refused")
    rows = _trash_rows(vault)
    if not rows:
        return 200, {"ok": True, "state": "empty", "count": 0,
                     "message": TRASH_EMPTY_SAID}
    if len(rows) > MAX_DELETE:
        return _error(400, (f"The vault's trash folder holds {len(rows)} files and I "
                            f"empty at most {MAX_DELETE} at a time, so nothing was "
                            "deleted. Empty it in Explorer, or delete fewer notes "
                            "before asking again."), state="refused")
    plan = {"rows": rows, "count": len(rows), "names": [r["rel"] for r in rows]}
    with _lock:
        waiting = sum(1 for j in _jobs.values() if j.get("state") == "waiting")
        if waiting >= MAX_WAITING:
            return _error(429, (f"{MAX_WAITING} note changes are already waiting for "
                                "approval - answer those cards first, then ask this "
                                "one."), state="refused")
        job_id = "notetrash_" + secrets.token_hex(8)
        _jobs[job_id] = {"id": job_id, "kind": "empty_trash", "state": "waiting",
                         "path": TRASH_DIR, "count": plan["count"],
                         "paths": list(plan["names"]),
                         "message": (f"This deletes all {plan['count']} file(s) in "
                                     "your vault's .trash folder for good."),
                         "created": time.time(), "updated": time.time(), "by": by}
        while len(_jobs) > MAX_JOBS:
            oldest = min(_jobs, key=lambda k: _jobs[k]["created"])
            _jobs.pop(oldest, None)
    thread = threading.Thread(target=_empty_trash_worker,
                              args=(job_id, plan, gate_check or _gate_check),
                              name="jarvis-note-empty-trash", daemon=True)
    thread.start()
    thread.join(max(0.0, float(wait_s)))
    code, out = change_status(job_id)
    if out.get("state") == "waiting":
        out["id"] = job_id
    return (202 if out.get("state") == "waiting" else 200), out


def handle_trash_status(query: str = "") -> tuple:
    """GET /api/notes/trash: what is in the trash, and the ONE nudge line or ""."""
    state = trash_state()
    if not state.get("readable"):
        return _error(503, "No trash list: " + str(state.get("why") or
                                                   "the vault could not be read") + ".")
    return 200, {"ok": True, "count": state["count"], "bytes": state["bytes"],
                 "oldest_days": state["oldest_days"],
                 "files": [{"path": r["rel"], "bytes": r["bytes"],
                            "age_days": r["age_days"]} for r in state["rows"]],
                 "nudge": state["nudge"]}




def change_status(job_id: str) -> tuple:
    """GET /api/notes/change?id=: waiting / saved / denied / failed, never text."""
    jid = str(job_id or "").strip()
    if not jid:
        return _error(400, "Need the id of a note change.", state="refused")
    with _lock:
        job = dict(_jobs.get(jid) or {})
    if not job:
        return _error(404, "There is no note change with that id on this PC.",
                      state="unknown")
    out = {
        "ok": job.get("state") in ("waiting", "saved"),
        "state": job.get("state"),
        "kind": job.get("kind") or "",
        "path": job.get("path"),
        "sha256": job.get("sha256"),
        "message": job.get("message") or "",
    }
    if job.get("current_sha256"):
        out["current_sha256"] = job["current_sha256"]
    if job.get("receipt"):
        out["receipt"] = job["receipt"]
    if job.get("snapshot"):
        out["snapshot"] = job["snapshot"]
    for key in ("target", "updates", "notes", "count", "paths"):
        if job.get(key) is not None:
            out[key] = job[key]
    return 200, out


def handle_change_status(query: str = "") -> tuple:
    """GET /api/notes/change?id=<job id> from the raw query string."""
    try:
        jid = (parse_qs(_query(query)).get("id") or [""])[0]
    except Exception:                                       # noqa: BLE001
        jid = ""
    return change_status(jid)


# ---------------------------------------------------------------------------
#   Chat doors (2026-10-31): read and search, deterministic and read-only
# ---------------------------------------------------------------------------
#
# The owner chose all three Obsidian abilities on 2026-10-31. This is the
# read/search half's backend: the chat answers call THESE functions, which call
# the same `handle_list` and `handle_read` the routes use - one reader, one
# vault resolution (`_vault()`), the same hidden-folder/protection/size rules.
# Nothing here writes, raises a card, or starts a model.

#: How much of one note the chat quotes before it says how much is left.
CHAT_READ_CHARS = 4000
#: How many notes one content search will open. Honest about the bound.
CHAT_SEARCH_SCAN = 500
#: How many matching titles one search prints.
CHAT_SEARCH_SHOWN = 5
#: How much of a note's first line "which one?" shows - enough to tell two
#: notes apart, never a paragraph.
CHAT_START_CHARS = 120

CHAT_NO_NOTE = "I could not find a note called \"{}\" in the vault."
CHAT_ONE_AT_A_TIME = "I can read one note at a time; tell me which one."
CHAT_SEARCH_DOOR = "You can search the whole vault in the notes editor on this PC."


def _chat_notes_meta() -> tuple:
    """Every note's path/title from the ONE list reader; `(None, why)` on error."""
    code, body = handle_list("")
    if code != 200:
        return None, str(body.get("error") or "The vault could not be read.")
    return list(body.get("notes") or []), ""


def chat_find_notes(title: str) -> tuple:
    """Notes that answer to `title`, the ONE resolver's tiers plus a read list.

    `jarvis_notes.resolve_note()` decides (exact path, case-insensitive
    basename, the note's own `aliases:`); this only turns its answer into the
    chat read shape. A refusal that listed candidates still returns them, so a
    partial title can be read when exactly one note contains it (the behaviour
    readers already have), and two or more make the chat ask which.
    """
    want = str(title or "").strip()
    if not want:
        return 400, {"said": CHAT_ONE_AT_A_TIME}
    notes, why = _chat_notes_meta()
    if notes is None:
        return 503, {"said": why}
    try:
        import jarvis_notes as N
        got = N.resolve_note(want)
    except Exception:                       # noqa: BLE001 - module absent
        return 503, {"said": "The notes could not be read on this PC."}
    if got.get("ok"):
        return 200, {"ok": True, "exact": True,
                     "matches": [{"path": str(got.get("path") or ""),
                                  "title": str(got.get("title") or "")}]}
    rows = [{"path": str(r.get("path") or ""), "title": str(r.get("title") or "")}
            for r in (got.get("candidates") or []) if isinstance(r, dict)]
    if str(got.get("code") or "") == "ambiguous_section" and rows:
        return 200, {"ok": True, "matches": rows, "exact": True}
    # A read question also accepts a merely CONTAINING title ("read my note
    # about the boiler" names no exact title). The resolver listed those as
    # near candidates; one may be read, several make the chat ask.
    low = want.lower()
    loose = [n for n in notes if low in str(n.get("title", "")).lower()]
    if rows:
        loose = rows
    return 200, {"ok": True, "matches": loose, "exact": False}


def _chat_read(path: str) -> tuple:
    return handle_read("?path=" + quote(str(path), safe=""))


def chat_vault_root() -> str:
    """The configured vault's folder, or "" when it cannot be read (never a guess)."""
    vault, _why = _vault()
    return str(vault) if vault is not None else ""


def chat_read_choices(text: str) -> tuple:
    """The notes a read question could mean, each with how it STARTS.

    "read my notes" names no title, and a title that matches several notes names
    more than one - both are answered by asking which, never by guessing. Each
    row carries the note's real `title`, its `folder` - the one fact that tells
    two notes lowercasing to the same title apart, and the same folder
    `jarvis_notes.resolve_note`'s exact-path tier accepts - and `start`: its
    first non-empty line, the same bytes `handle_read` returns, cut to
    CHAT_START_CHARS so a long paragraph cannot flood the answer. With `text`
    empty every note is a candidate; otherwise title matching is
    `chat_find_notes`' own rule (exact first, then merely contains) so the two
    answers cannot disagree about what "Welcome" matches.

    Nothing here reads a file outside the vault or a dot-folder: it goes through
    `_chat_notes_meta`/`_chat_read`, the same two readers the editor routes use.
    """
    notes, why = _chat_notes_meta()
    if notes is None:
        return 503, {"said": why}
    want = str(text or "").strip()
    if want:
        low = want.lower()
        matches = [n for n in notes if low in str(n.get("title", "")).lower()]
        exact = [n for n in matches if str(n.get("title", "")).lower() == low]
        if exact:
            matches = exact
    else:
        matches = list(notes)
    rows = []
    for note in matches[:CHAT_SEARCH_SHOWN]:
        start = ""
        code, read = _chat_read(note.get("path", ""))
        if code == 200:
            for line in str(read.get("text") or "").splitlines():
                line = line.strip()
                if line:
                    start = line[:CHAT_START_CHARS]
                    break
        rows.append({"title": str(note.get("title") or ""), "start": start,
                     "folder": os.path.dirname(str(note.get("path") or ""))})
    return 200, {"ok": True, "choices": rows, "count": len(matches),
                 "truncated": len(matches) > len(rows)}


def chat_read_note(title: str) -> tuple:
    """One note's text, bounded, named only by the real title it was read from."""
    code, found = chat_find_notes(title)
    if code != 200:
        return code, found
    matches = found["matches"]
    if not matches:
        return 404, {"said": CHAT_NO_NOTE.format(str(title or "").strip())}
    if len(matches) > 1:
        return 409, {"said": CHAT_ONE_AT_A_TIME,
                     "titles": [str(n.get("title") or "") for n in matches[:CHAT_SEARCH_SHOWN]],
                     "count": len(matches)}
    note = matches[0]
    code, read = _chat_read(note.get("path", ""))
    if code != 200:
        return code, {"said": str(read.get("error") or "The note could not be read.")}
    text = str(read.get("text") or "")
    cut = text[:CHAT_READ_CHARS]
    # `outside_text` is the store's own fact, not a prefix string a caller can
    # drop (the same shape jarvis_documents._mark_answer sets): a note is a
    # FILE, so its words are data to read, never something to learn from or act
    # on. The text itself is returned exactly as the bytes are - cutting the
    # tail is the only transformation, and `total_chars`/`more` state it.
    return 200, {"ok": True, "title": str(note.get("title") or ""),
                 "path": note.get("path", ""), "text": cut,
                 "total_chars": len(text), "more": max(0, len(text) - len(cut)),
                 "outside_text": True}


def chat_search_notes(needle: str) -> tuple:
    """Titles whose NOTE TEXT contains `needle`; never a body, never a path."""
    want = str(needle or "").strip()
    if not want:
        return 400, {"ok": True, "count": 0, "titles": [], "scanned": 0, "capped": False}
    notes, why = _chat_notes_meta()
    if notes is None:
        return 503, {"said": why}
    low = want.lower()
    titles, scanned = [], 0
    for note in notes[:CHAT_SEARCH_SCAN]:
        scanned += 1
        code, read = _chat_read(note.get("path", ""))
        if code != 200:
            continue
        if low in str(read.get("text") or "").lower():
            titles.append(str(note.get("title") or ""))
    return 200, {"ok": True, "count": len(titles),
                 "titles": titles[:CHAT_SEARCH_SHOWN],
                 "scanned": scanned, "capped": len(notes) > scanned}


def chat_open_note(title: str) -> tuple:
    """The note's title/path when it exists (the chat says to open the Brain)."""
    code, found = chat_find_notes(title)
    if code != 200:
        return code, found
    matches = found["matches"]
    if not matches:
        return 404, {"said": CHAT_NO_NOTE.format(str(title or "").strip())}
    first = matches[0]
    return 200, {"ok": True, "title": str(first.get("title") or ""),
                 "path": first.get("path", ""), "count": len(matches)}


# ---------------------------------------------------------------------------
#   The note's own names: the YAML `aliases:` list Obsidian reads natively
# ---------------------------------------------------------------------------
#
# WHY (the owner's report, 2026-11-16). "my workout log" is a note whose file is
# called `Workout Log.md` inside `Private & Shared/Workout/`; its own front
# matter says so:
#
#     ---
#     aliases:
#       - workout log
#       - my workout log
#     pinned: true
#     ---
#
# so a resolver that looks only at FILE NAMES cannot find it. The registry is
# that list - Obsidian reads it natively, it travels with the note, and it needs
# no index, no model and no state from an earlier conversation. `find_name` is
# the ONE resolver the chat paths use; it reads the vault fresh every time.

def note_aliases(text: str) -> list:
    """The aliases in one note's own YAML frontmatter ([] when there are none).

    The parser lives in `jarvis_notes` (the ONE resolver); this keeps the name
    the editor's callers already use.
    """
    try:
        import jarvis_notes as N
        return N.note_aliases(text)
    except Exception:                       # noqa: BLE001 - module absent
        return []


def find_name(phrase: str) -> tuple:
    """`(row, why, matches)` - a compatibility shape over the ONE resolver.

    `jarvis_notes.resolve_note()` is where a name is resolved (exact vault path,
    then case-insensitive basename, then the note's own `aliases:`, then a
    refusal that lists the candidates). This function adds nothing to that
    order; it keeps the `(row, why, matches)` shape the chat and editor callers
    already use, so there is one implementation behind every door.
    """
    try:
        import jarvis_notes as N
        got = N.resolve_note(phrase)
    except Exception:                       # noqa: BLE001 - module absent
        return None, "unreadable", []
    rows = [{"path": str(r.get("path") or ""), "title": str(r.get("title") or "")}
            for r in (got.get("candidates") or []) if isinstance(r, dict)]
    if got.get("ok"):
        row = {"path": str(got.get("path") or ""),
               "title": str(got.get("title") or "")}
        return row, "", [row]
    code = str(got.get("code") or "")
    if code == "not_found":
        return None, "not_found", rows
    if code == "ambiguous_section":
        return None, "ambiguous", rows
    if code == "case_variant_exists":
        return None, "case_variant", rows
    return None, "unreadable", rows


# ---------------------------------------------------------------------------
#   install(): the loader's convention, exactly like receipts and vault
# ---------------------------------------------------------------------------


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap the core's Handler with these four routes.

    After the server's own origin and token checks, and every other request
    goes straight to the original. This is the shape `jarvis_receipts.install`
    and `jarvis_vault.install` use; `plugins/ready/notes-edit/plugin.json`
    names this module and `jarvis_plugins.py` makes the call a patch would
    have made.
    """
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(get0, "_jarvis_notes_edit", False):
        return "  notes-edit  Obsidian notes editor (already on)"

    def _allowed(self) -> bool:
        try:
            if not origin_ok(self):
                self._send(403, {"error": "cross-origin request refused"})
                return False
            if not token_ok(self):
                self._send(401, {"error": "bad or missing X-Jarvis-Token"})
                return False
        except Exception:                                   # noqa: BLE001
            self._send(401, {"error": "bad or missing X-Jarvis-Token"})
            return False
        return True

    def do_GET(self):
        parts = urlsplit(str(getattr(self, "path", "") or ""))
        route = parts.path.rstrip("/")
        if route not in GET_PATHS:
            return get0(self)
        if not _allowed(self):
            return None
        try:
            if route == LIST_PATH:
                code, out = handle_list(parts.query)
            elif route == READ_PATH:
                code, out = handle_read(parts.query)
            elif route == TEMPLATES_PATH:
                code, out = handle_templates_list()
            elif route == CHANGE_PATH:
                code, out = handle_change_status(parts.query)
            elif route == TRASH_PATH:
                code, out = handle_trash_status(parts.query)
            else:
                code, out = handle_save_status(parts.query)
        except Exception as exc:                            # noqa: BLE001
            code, out = 503, {"ok": False, "error": type(exc).__name__}
        return self._send(code, out)

    def do_POST(self):
        route = urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if route not in POST_PATHS:
            return post0(self)
        if not _allowed(self):
            return None
        try:
            body = json.loads(read_body(self) or b"{}")
        except Exception:                                   # noqa: BLE001
            body = None
        try:
            if route == CREATE_PATH:
                _hdr_client = ""
                try:
                    _hdr_client = str(self.headers.get("X-Jarvis-Client") or "")
                except Exception:                       # noqa: BLE001
                    _hdr_client = ""
                code, out = handle_create(
                    body,
                    client=_hdr_client.strip().lower() or "hud",
                    provenance=str((body or {}).get("provenance") or "typed"))
            elif route == APPEND_PATH:
                code, out = handle_append(body)
            elif route == TAG_PATH:
                code, out = handle_tag(body)
            elif route == INSERT_PATH:
                code, out = handle_insert(body)
            elif route == FORMAT_PATH:
                code, out = handle_format(body)
            elif route == REPLACE_PATH:
                code, out = handle_replace(body)
            elif route == CUSTOMIZE_PATH:
                code, out = handle_customize(body)
            elif route == RENAME_PATH:
                code, out = handle_rename(body)
            elif route == MOVE_PATH:
                code, out = handle_move(body)
            elif route == DELETE_PATH:
                code, out = handle_delete(body)
            elif route == MERGE_PATH:
                code, out = handle_merge(body)
            elif route == COPY_PATH:
                code, out = handle_copy(
                    body,
                    client=str(self.headers.get("X-Jarvis-Client") or "").strip().lower()
                    or "hud",
                    provenance=str((body or {}).get("provenance") or "typed"))
            elif route == TRASH_PATH:
                code, out = handle_empty_trash(body)
            else:
                code, out = handle_save(body)
        except Exception as exc:                            # noqa: BLE001
            code, out = 503, {"ok": False, "error": type(exc).__name__}
        return self._send(code, out)

    do_GET._jarvis_notes_edit = True
    do_POST._jarvis_notes_edit = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    return ("  notes-edit  browse and read any Obsidian note; save, create, "
            "append, tag, rename and move ONE note per request (one approval "
            "card each, undo receipt); a rename/move also updates the links to it; "
            "delete up to twenty notes per request (one card naming all of them, "
            "and that card needs Windows Hello or the asking phone's fingerprint)")


def _reset_for_tests() -> None:
    """Clear the job table between tests; nothing else uses this."""
    with _lock:
        _jobs.clear()
