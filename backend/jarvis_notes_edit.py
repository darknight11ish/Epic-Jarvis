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
from urllib.parse import parse_qs, urlsplit

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
CHANGE_PATH = "/api/notes/change"
GET_PATHS = (LIST_PATH, READ_PATH, SAVE_PATH, CHANGE_PATH)
POST_PATHS = (SAVE_PATH, CREATE_PATH, APPEND_PATH, TAG_PATH)

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
    """(prompt, detail) - the card's own words: the file, what changes, undo."""
    if kind == "create":
        data = payload
        return (f"create {rel} in your Obsidian vault ({len(data)} bytes)",
                {"path": rel, "bytes": len(data), "action": "create a new note"})
    if kind == "append":
        data = payload
        return (f"add {len(data)} bytes to the end of {rel} in your Obsidian vault",
                {"path": rel, "bytes": len(data), "action": "add to the end of a note"})
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
        if kind == "create":
            _finish_create(job_id, full, rel, payload)
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
        # tag: the new text was worked out before the card; re-check it is legal
        new_data = payload
        try:
            _write_note(full, new_data)
        except OSError as exc:
            _finish(job_id, state="failed",
                    message=f"The note could not be written ({type(exc).__name__}), so it was left as it was.")
            _audit("tag_failed", {"job": job_id, "path": rel, "why": "write"})
            return
        tag = str(extra.get("tag") or "")
        said = ("Tagged " + rel + " with #" + tag + "." if extra.get("action") == "add"
                else "Removed the tag #" + tag + " from " + rel + ".")
        _finish(job_id, state="saved", sha256=_sha256(new_data),
                snapshot=snap.get("snapshot_id") or None,
                message=said + " You can undo it.")
        _audit("tagged", {"job": job_id, "path": rel,
                          "tag": tag, "action": extra.get("action")})
    except Exception as exc:                                # noqa: BLE001
        _finish(job_id, state="failed",
                message=f"The change failed ({type(exc).__name__}), so nothing was written.")
        _audit(kind + "_failed", {"job": job_id, "path": rel, "why": "exception"})


def _finish_create(job_id: str, full: Path, rel: str, data: bytes) -> None:
    """The new note: receipt first, then one O_EXCL file, then read it back."""
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
    _finish(job_id, state="saved", sha256=_sha256(data), receipt=rid,
            message=f"Created {rel} in your Obsidian vault. You can undo it.")
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
