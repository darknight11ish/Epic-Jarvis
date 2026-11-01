"""jarvis_notes_edit.py - browse, open and save ANY note in the owner's
Obsidian vault, with one approval card per save.

WHAT THIS IS FOR

The owner's decision of 2026-10-31, in his own words: **"The whole vault, both
apps"** - search and browse every note in the Obsidian vault, open and edit
any, from the desktop program and from the phone. `jarvis_notes.py` could
already SEARCH the vault (read-only), and `jarvis_note_capture.py` could APPEND
one entry to today's daily note. Neither could browse the vault or change an
existing note. This module is those four routes:

    GET  /api/notes/list?q=<text>     every note: path, title, size, mtime
    GET  /api/notes/read?path=<rel>   one note: its text and its sha256
    POST /api/notes/save              save the WHOLE new text of one note
    GET  /api/notes/save?id=<job id>  how one save ended
    POST /api/notes/create            make ONE new note (no overwrite ever)
    POST /api/notes/append            add words to the END of one note
    POST /api/notes/tag               add or remove ONE tag on one note
    GET  /api/notes/change?id=<job>   how one of those three ended

The three wave-1 writes (2026-10-31, the owner's flexibility decision) are the
same single-file shape as the save: one note, one approval card, the File
Guardian copy first where there are old bytes to keep, and every answer says
you can undo it. Rename, move, delete and several-notes-at-once are NOT here:
they belong to the wave-2 slice and are refused in plain words by the routes.

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
                 gate has no `_RISK` row for this name yet (a drop-in module
                 cannot add one; risk rows are written by patches), so the
                 gate does what it does with any unclassified action: it is
                 FORCED to "ask" whatever the settings file says, and its card
                 carries the generic worst-case warning line. That is the safe
                 side: the write can never run unattended. Classifying it
                 properly is a small follow-up patch, named in the section
                 below.
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
  - Delete or rename a note. They are still not built (wave 2, with the link
    repairs a rename needs), so a missing path is a 404 on read, save, append
    and tag, and no route here removes or moves a file.
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
  - `edit_vault_note` has no `_RISK` row until a patch adds one (see above),
    so its card shows the gate's generic unclassified-action warning; the
    tier itself is the shipped "ask" line in both copies of
    `jarvis-framework.toml`.
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

#: One note may be at most 2 MiB. Bigger is refused BEFORE any card, for a
#: read (413) and for a save (413): a card the owner cannot read is not an
#: approval, and a whole-vault editor is not a file manager.
MAX_FILE_BYTES = 2 * 1024 * 1024

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
CHANGE_PATH = "/api/notes/change"
GET_PATHS = (LIST_PATH, READ_PATH, SAVE_PATH, CHANGE_PATH, TEMPLATES_PATH)
POST_PATHS = (SAVE_PATH, CREATE_PATH, APPEND_PATH, TAG_PATH,
              INSERT_PATH, FORMAT_PATH, REPLACE_PATH, CUSTOMIZE_PATH)

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


def _worker(job_id: str, full: Path, rel: str, data: bytes, expected: str,
            vault: Path, gate_check) -> None:
    """Ask the gate, then (and only then) write. Runs on a daemon thread."""
    try:
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
    thread = threading.Thread(
        target=_worker,
        args=(job_id, full, rel2, data, expected, vault,
              gate_check or _gate_check),
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
    if kind == "append":
        data = payload
        return (f"add {len(data)} bytes to the end of {rel} in your Obsidian vault",
                {"path": rel, "bytes": len(data), "action": "add to the end of a note"})
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
        if kind in ("create", "create_template"):
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
        _finish(job_id, state="failed",
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
        _finish(job_id, state="failed",
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
                  by: str = "") -> tuple:
    """POST /api/notes/create: exactly one new note, one card, undo by receipt."""
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
    if full.exists():
        return _error(409, f"There is already a note at {rel2}, so nothing was created.",
                      state="exists")
    return _start_change_job("create", full, rel2, data, "", vault,
                             gate_check, wait_s, by, {})


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
    if mode not in ("under_heading", "before", "after"):
        return _error(400, "mode must be under_heading, before or after.", state="refused")
    if not isinstance(text, str) or not text.strip():
        return _error(400, "Need the words to add as text.", state="refused")
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
        fresh = opened + "".join(new_front) + "---" + eol + body
        preview = _preview(_line_body(front[idx]), "", note="the property removed")
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


def _append_link(text: str, note_name: str, heading: str = ""):
    """`(new_text, said, preview, why)` - one `[[Note]]` line."""
    name = str(note_name or "").strip().strip("[]")
    if not name or "\n" in name or "[" in name or "]" in name:
        return text, "", {}, "which note should be linked?"
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
    """Notes whose title equals (then merely contains) `title`, newest first."""
    want = str(title or "").strip()
    if not want:
        return 400, {"said": CHAT_ONE_AT_A_TIME}
    notes, why = _chat_notes_meta()
    if notes is None:
        return 503, {"said": why}
    low = want.lower()
    exact = [n for n in notes if str(n.get("title", "")).lower() == low]
    if exact:
        return 200, {"ok": True, "matches": exact, "exact": True}
    return 200, {"ok": True,
                 "matches": [n for n in notes if low in str(n.get("title", "")).lower()],
                 "exact": False}


def _chat_read(path: str) -> tuple:
    return handle_read("?path=" + quote(str(path), safe=""))


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
    return 200, {"ok": True, "title": str(note.get("title") or ""),
                 "path": note.get("path", ""), "text": cut,
                 "total_chars": len(text), "more": max(0, len(text) - len(cut))}


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
                code, out = handle_create(body)
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
            "append and tag ONE note per request (one approval card each, undo "
            "receipt)")


def _reset_for_tests() -> None:
    """Clear the job table between tests; nothing else uses this."""
    with _lock:
        _jobs.clear()
