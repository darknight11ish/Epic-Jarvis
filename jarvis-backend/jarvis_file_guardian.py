"""jarvis_file_guardian.py - a local "time machine" for the files Jarvis changes.

WHY THIS EXISTS

Every other protection in this backend is about whether an action may run:
`jarvis_gate.py` asks the owner, `jarvis_receipts.py` leaves a receipt saying
what changed with one button to put it back. Neither keeps the FILE. When a
tool overwrites a note, a project file or a script, the bytes that were there
a second earlier are gone - and the receipt can only put back the change if
the change itself kept enough of the old state, which an overwrite does not.

This module keeps them. Before anything writes over a file in a folder Jarvis
is allowed to change, it stores a compressed copy of the file's previous bytes
under a content address (the sha256 of those bytes). The same bytes are only
ever stored once, so two identical versions cost one copy; the owner can see a
point-in-time difference and put one version back in one click.

WHAT IT IS

Two things in the Jarvis settings folder:

    $OPENJARVIS_HOME/guardian/blobs/<sha256>.gz
        one compressed copy per DISTINCT content, named by its sha256. The
        name is the hash of the UNCOMPRESSED bytes, so the name proves what
        the file held.

    $OPENJARVIS_HOME/guardian/guardian.jsonl
        one JSON line per snapshot, in order: `timestamp`, `path`,
        `before_sha256`, `size`, `reason`, `receipt_id`. Append-only, so a
        snapshot is never rewritten and a half-written line is at the end,
        where the reader can see and skip it.

where `$OPENJARVIS_HOME` is, in this order: `OPENJARVIS_HOME` itself; else the
same rule every other module follows (read from `jarvis_receipts.py` and
`jarvis_projects.py`, word for word) - `jarvis_framework.CONFIG_DIR`, else
`OPENJARVIS_CONFIG_DIR` / `JARVIS_CONFIG_DIR`, else `~/.openjarvis`. The tests
point `OPENJARVIS_HOME` at a scratch folder and never touch the owner's own.

THE API

    snapshot_before_write(path, *, reason="", max_file_bytes=MAX_FILE_BYTES) -> dict
        Refuse a link, a path outside an allowed folder, a folder, a missing
        or unreadable file - in plain words, touching nothing. A file bigger
        than `max_file_bytes` (25 MiB by default) is refused BEFORE its bytes
        are read, with the machine-readable `error` value
        `"file_too_large_for_guardian"` plus `size_bytes` and `max_file_bytes`
        (and `words`, the same sentence a person reads); the file, the store
        and the journal are untouched. Otherwise hash the CURRENT bytes, store
        the compressed copy, record a receipt with the EXISTING
        `jarvis_receipts.py` (`record()`, tool `guardian_snapshot`, before
        snapshot carrying the path and sha256, so the receipt's own Undo puts
        the previous bytes back), append the row, then prune the store to the
        quota. Returns `{ok, path, before_sha256, snapshot_id, size, stored,
        receipt_id, pruned, prune_words, words}`; `snapshot_id` is the opaque
        copy id the receipt and the journal row carry, so a caller can link
        its own record of the write to the saved version. `ok` False carries
        `error`/`words` in plain English and a `refused` flag; a refusal by
        the size ceiling also carries `too_large: True`.

    diff_versions(path, sha_before) -> dict
        The unified diff between that saved version and the file now, oldest
        on the left, bounded (MAX_DIFF_BYTES characters, and at most
        MAX_TEXT_BYTES of each side is decoded). A binary pair answers
        `binary: True` with no line diff. A file that is already that version
        answers `same: True`. A version no longer in the store is refused in
        plain words.

    restore_version(path, sha_before, *, gate=None) -> dict
        One click, and NEVER silently: the one permission model is asked
        first - `gate(action, detail, prompt)` exactly as the other modules
        take it, defaulting to the real `jarvis_gate.check()` - and only an
        answer that is a person's yes writes anything. The action is the
        EXISTING `undo_action` card (`jarvis_receipts.UNDO_ACTION`), not a new
        tier or a new kind of card. The current bytes are stored first and a
        NEW receipt is recorded before the write, so the existing Undo button
        puts this restore back in one click too ("before" = what is here now,
        "after" = the version being put back). A denied, timed-out, failed or
        answered-by-nobody card changes nothing at all.

    prune() -> dict
        Remove the OLDEST UNPINNED blobs until the store is under QUOTA_BYTES
        (250 MB), and say in plain words what was removed. A pinned blob is
        never removed, even when that leaves the store over the quota - the
        owner's own pin outranks the automatic tidy.

    pin(sha256) / unpin(sha256) / pinned() / usage()
        Keep a version for good, stop keeping it, list what is kept, and how
        much space the store is using.

ALLOWED FOLDERS - the one rule everything above goes through

A path may be guarded only when it is inside a folder the owner has already
allowed Jarvis to touch: the folders on the existing "Folders Jarvis may look
in" list (`jarvis_documents.folders()`), or the configured Obsidian vault
(`jarvis_notes.obsidian_vault()`). `roots=` overrides that list for a caller
that already knows its folder, and `JARVIS_GUARDIAN_FOLDERS` (a
`os.pathsep`-separated list) overrides it for the tests and for a caller with
its own list. With neither, and nothing on the list, EVERY path is refused -
the fail-closed direction. `os.path.realpath` is what is compared, so a
Windows junction that leads outside is caught the same way a symlink is.

WHY A RECEIPT, AND WHY THE CARD IS THE EXISTING ONE

`jarvis_receipts.py` is the project's answer to "put back what a change did":
one row per action, an in-memory callable while the process lives, a before
snapshot plus a registered restorer after a restart, and exactly-one undo
enforced in the database. This module does not grow a second receipt store and
does not invent a new approval tier or action. It calls `record()` with the
real API, registers a restorer for its two tool names through
`register_restorer()`, and asks for `undo_action` - the card that already
exists for "put a change back", with its own line in the owner's settings file
(tier "ask"). A caller that wants a route or a chat tool later passes a gate
callable exactly as the routes do; nothing here is wired into the chat tool
list, because that list is the owner's decision.

WHAT THIS MODULE DOES NOT DO, SAID PLAINLY

  * It does not decide whether Jarvis may change a file. A snapshot changes
    nothing (it reads and copies), so it needs no card; the WRITE that follows
    is the caller's action and goes through the caller's own gate, as always.
    The one place a card is raised here is the restore, because a restore
    itself overwrites the file.
  * TWO READ-ONLY routes expose its history since 2026-10-18 (LM-2A):
    `GET /api/guardian/snapshots` (the journal, newest first and bounded) and
    `GET /api/guardian/diff` (the bounded unified diff this module already
    works out), answered by `jarvis_brain_reads.py` and documented in
    JARVIS-API section 140. They read the store and nothing else; a request
    from another device is refused BEFORE anything is read; neither writes.
    ONE gated restore route exists too since 2026-10-18 (LM-2B):
    `POST /api/guardian/restore` calls `restore_version()` with the EXISTING
    `undo_action` card through the real `jarvis_gate.check()` - no new tier.
    It is POST-only, the only route here that writes, and a request from
    another device is refused before the request body is read. There is
    still no chat tool: no model can reach any of this.
  * The backend cannot see App lock or "Hide memory lists" by itself (both are
    desktop-side state), so the desktop's own drawer hides while either is on.
    Since 2026-10-20 (Q1) the two read routes can ALSO withhold at the server:
    when the request carries `?app_locked=1` or `?hide_memory_lists=1` (which
    only ADD withholding - jarvis_private_view merges them, a False can never
    unlock), jarvis_brain_reads answers with the honest marker and an empty
    page/diff, before it reads the journal or works out the difference.
    JARVIS-API section 140 records that the live HUD must eventually pass the
    state; until it does, the drawer rule above is the one in force.
  * It is not a backup and not encryption. The copies sit in the owner's
    settings folder on this PC, readable by this process and by anything else
    that can read that folder; nothing here sends them anywhere, and nothing
    here survives the folder being deleted. `jarvis_backup.py` is the backup.
  * It keeps ordinary files, not a whole disk: one file bigger than
    MAX_FILE_BYTES (25 MiB, an N_placeholder) is refused before a byte of it
    is read (`error="file_too_large_for_guardian"`), so a single huge file
    cannot blow the quota or the memory the copy is compressed in. A caller
    that legitimately guards a bigger file passes its own `max_file_bytes`.
  * It does not keep every version for ever: the quota pruning above removes
    the oldest unpinned ones, and says so.

TESTS: `backend/test_file_guardian.py` drives every claim above - a byte-exact
restore, dedup, the pruning order and a pinned blob never pruned, every
refusal, the card being required and the Undo receipt left behind, a bounded
diff, and the home folder being honoured. Every check is proven to bite: the
module was mutated deliberately and the suite went red for each mutation.
"""
from __future__ import annotations

import difflib
import gzip
import hashlib
import io
import json
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional

try:                                            # the owner's own module
    import jarvis_framework as fw
except Exception:                               # pragma: no cover - CI has it
    fw = None  # type: ignore

# --------------------------------------------------------------------------
#   Numbers and words
# --------------------------------------------------------------------------

#: The store is pruned to this size (after a snapshot, oldest unpinned first).
QUOTA_BYTES = 250 * 1024 * 1024

#: How much of one diff is returned. Past this it is cut and the answer says
#: so - an app drawing a 40 MB diff is not a feature.
MAX_DIFF_BYTES = 64 * 1024

#: How much of each SIDE of a diff is decoded at all, so a 2 GB file cannot
#: hold up the call that shows one difference.
MAX_TEXT_BYTES = 1024 * 1024

#: One file bigger than this is refused rather than read: the copy is
#: compressed in memory, and a single huge file must not be able to blow the
#: quota (or this process) in one snapshot. 25 MiB (an N_placeholder, not a
#: measurement) is far above any note, project file or script this feature is
#: for. A caller passes its own `max_file_bytes` when it guards bigger files.
MAX_FILE_BYTES = 25 * 1024 * 1024

#: A snapshot's own reason is one short line.
MAX_REASON = 200

#: Rows read at most from the journal at once (it is append-only and long).
MAX_ROWS_READ = 50000

#: Where the store lives. `OPENJARVIS_HOME` is the brief's own name for it;
#: the fallback is the rule `jarvis_receipts.py` and `jarvis_projects.py`
#: follow for the settings folder (see `_config_dir` below).
HOME_ENV = "OPENJARVIS_HOME"

#: A caller's own list of allowed folders, `os.pathsep`-separated. The tests
#: use it; it takes the place of the two module lists below when it is set.
FOLDERS_ENV = "JARVIS_GUARDIAN_FOLDERS"

GUARDIAN_DIR = "guardian"
BLOBS_DIR = "blobs"
INDEX_NAME = "guardian.jsonl"
PINS_NAME = "pins.json"

#: The EXISTING card action for "put a change back", read from
#: jarvis_receipts.UNDO_ACTION's own value (the suite checks the two agree).
#: A new tier or a new action would be a second permission model, which this
#: project has one of, on purpose.
UNDO_ACTION = "undo_action"

#: The `tool_name` on the two kinds of receipt. Distinct, because a new
#: process finds a restorer by either the tool name or the label written in
#: the row, and both kinds put a saved version back the same way.
TOOL_SNAPSHOT = "guardian_snapshot"
TOOL_RESTORE = "guardian_restore"

_SHA = re.compile(r"^[0-9a-f]{64}$")
_LOCK = threading.Lock()

#: Fixed card words. No emoji, no "!", and the last line is what refusing
#: costs - the one thing a permission request must never leave out. Only the
#: file's own NAME appears on the card; never its full path, never its words.
CARD_HEAD = "Put back an earlier version of a file?"
CARD_NOTE = ("Putting a version back overwrites the file as it is now. Jarvis saves the "
             "version that is here now first, so Undo puts it back in one click.")
CARD_TAIL = "If you say no, nothing changes: the file stays exactly as it is now."

WORDS = {
    "link": ("That is a link, not the file itself, so Jarvis will not change it: a link "
             "can point somewhere else after this check."),
    "no_roots": ("No folder is on Jarvis's list of folders it may change, so nothing was "
                 "touched. Add the folder to \"Folders Jarvis may look in\" first."),
    "outside": ("That file is not inside a folder Jarvis is allowed to change, so nothing "
                "was touched."),
    "folder": "That is a folder, not a file, so there is nothing to copy.",
    "missing": "There is no file at that path on this PC.",
    "no_path": "Say which file, as its full path on this PC.",
    "too_big": ("That file is bigger than the time machine's {limit} limit for one file, "
                "so nothing was read or copied."),
    "bad_sha": ("That is not a saved version's name (a sha256 of the file's bytes), so "
                "nothing was touched."),
    "no_version": ("That earlier version is not in the time machine any more - it may have "
                   "been removed to stay under the size limit."),
    "damaged": ("That saved version is damaged or was altered - it does not match its own "
                "content address - so nothing was put back."),
    "unpacked_too_big": ("That saved version unpacks to more than the time machine's limit "
                         "for one file, so nothing was put back."),
    "not_this_files_version": ("That saved version was saved from a different file, so "
                               "nothing was put back."),
    "receipt_failed": ("The restore could not be recorded, so nothing was written."),
    "record_failed": ("The restore could not be added to the file history, so nothing "
                      "was written."),
    "denied": "The card was turned down, so nothing was written.",
    "timed_out": "Nobody answered the card in time, so nothing was written.",
    "refused": "The card was not approved, so nothing was written.",
    "gate_failed": "The approval card could not be raised ({why}), so nothing was written.",
    "read_failed": "The file could not be read ({why}), so nothing was copied.",
    "write_failed": "The file could not be written ({why}), so nothing was changed.",
    "saved": "Saved a copy of {name} ({size}) before Jarvis changes it.",
    "saved_no_receipt": (" The receipt store is not available, so Undo cannot take this "
                         "copy back - the copy itself is safe."),
    "already_saved": "This exact version of {name} was already saved, so nothing was copied again.",
    "same": "The file is already that version, so there is nothing to put back.",
    "same_diff": "The file is exactly that saved version - there is no difference to show.",
    "diff": "The file changed since that version was saved.",
    "diff_cut": " The difference is long, so only the beginning is shown.",
    "binary": ("One of the two versions is a binary file (pictures, a program, an "
               "archive), so there is no line difference to show. The version can still "
               "be put back."),
    "restored": ("Put back the version from {when}. The version that was here a moment ago "
                 "is saved too, so one Undo puts it back."),
    "restored_no_receipt": (" The receipt store is not available, so this restore cannot be "
                            "undone with the Undo button."),
}


class Refused(ValueError):
    """A plain-English refusal. The public functions return it as `error`."""


# --------------------------------------------------------------------------
#   Where
# --------------------------------------------------------------------------


def _config_dir() -> Path:
    """The settings folder - the same rule jarvis_receipts.py follows.

    Kept word for word with `jarvis_receipts._config_dir` and
    `jarvis_projects._config_dir`: the framework's own CONFIG_DIR first, then
    the two environment names, then `~/.openjarvis`. `OPENJARVIS_HOME` is
    checked BEFORE this rule (see `home_dir`), because that is the folder the
    brief names for the store and the tests inject it.
    """
    if fw is not None:
        try:
            return Path(fw.CONFIG_DIR)
        except Exception:
            pass
    env = os.environ.get("OPENJARVIS_CONFIG_DIR") or os.environ.get("JARVIS_CONFIG_DIR")
    if env:
        return Path(os.path.expanduser(env))
    return Path(os.path.expanduser("~")) / ".openjarvis"


def home_dir() -> Path:
    """The folder the store lives under. Read on every call, never cached.

    `OPENJARVIS_HOME` first (the brief's own name for it, and the tests point
    it at a scratch folder), then the repository's own settings-folder rule.
    """
    env = os.environ.get(HOME_ENV)
    if env and str(env).strip():
        return Path(os.path.expanduser(str(env).strip()))
    return _config_dir()


def guardian_dir() -> Path:
    return home_dir() / GUARDIAN_DIR


def blobs_dir() -> Path:
    return guardian_dir() / BLOBS_DIR


def index_path() -> Path:
    return guardian_dir() / INDEX_NAME


def pins_path() -> Path:
    return guardian_dir() / PINS_NAME


# --------------------------------------------------------------------------
#   The allowed folders - one rule every path goes through
# --------------------------------------------------------------------------


def _clean_roots(items) -> list:
    out = []
    for item in items or []:
        if isinstance(item, bytes):
            item = os.fsdecode(item)
        elif not isinstance(item, str):
            try:
                item = os.fspath(item)
            except TypeError:
                continue
        if not isinstance(item, str) or item is None or not item.strip() or "\x00" in item:
            continue
        try:
            real = os.path.realpath(os.path.expanduser(item.strip()))
        except Exception:
            continue
        if real and real not in out:
            out.append(real)
    return out


def allowed_roots() -> list:
    """The folders a path must be inside. Fail closed: an empty list is "none".

    1. `JARVIS_GUARDIAN_FOLDERS` when it is set (tests, and a caller with its
       own list) - it replaces the two lists below rather than adding to them.
    2. The owner's own "Folders Jarvis may look in" (`jarvis_documents`), and
    3. the configured Obsidian vault (`jarvis_notes`), links resolved.

    A module that cannot be imported simply contributes nothing; it never
    widens the list. `roots=` on the public functions overrides all of it.
    """
    env = os.environ.get(FOLDERS_ENV)
    if env is not None:
        return _clean_roots(str(env).split(os.pathsep))
    out = []
    try:
        import jarvis_documents
        out.extend(jarvis_documents.folders())
    except Exception:
        pass
    try:
        import jarvis_notes
        vault = jarvis_notes.obsidian_vault()
        if vault:
            out.append(str(vault))
    except Exception:
        pass
    return _clean_roots(out)


def _inside(root: str, real: str) -> bool:
    """True when `real` is `root` or under it. Windows does not care about case."""
    try:
        return os.path.commonpath([os.path.normcase(root), os.path.normcase(real)]) \
            == os.path.normcase(root)
    except ValueError:              # different drives on Windows
        return False


def _check_path(path, roots=None) -> tuple:
    """(real path, the allowed folders) or `Refused` in plain words.

    A link is refused on the raw path BEFORE it is resolved, because a link's
    target can change between the check and the write; a path outside every
    allowed folder is refused after resolution, so a junction that leads out
    is caught too.
    """
    roots_list = _clean_roots(roots) if roots is not None else allowed_roots()
    if not isinstance(path, str) or not path.strip() or "\x00" in path:
        raise Refused(WORDS["no_path"])
    raw = os.path.expanduser(path.strip())
    try:
        if os.path.islink(raw):
            raise Refused(WORDS["link"])
        real = os.path.realpath(raw)
    except Refused:
        raise
    except Exception:
        raise Refused(WORDS["no_path"])
    if not roots_list:
        raise Refused(WORDS["no_roots"])
    if not any(_inside(root, real) for root in roots_list):
        raise Refused(WORDS["outside"])
    return real, roots_list


def _check_file(real: str) -> bytes:
    """The file's bytes, or a plain refusal: no folder, no file, no read, too big."""
    if os.path.isdir(real):
        raise Refused(WORDS["folder"])
    if not os.path.isfile(real):
        raise Refused(WORDS["missing"])
    try:
        size = os.path.getsize(real)
    except OSError:
        raise Refused(WORDS["missing"])
    if size > MAX_FILE_BYTES:
        raise Refused(WORDS["too_big"].format(limit=_size_words(MAX_FILE_BYTES)))
    try:
        return _read_bytes(real)
    except OSError as exc:
        raise Refused(WORDS["read_failed"].format(why=type(exc).__name__))


def _read_bytes(real: str) -> bytes:
    """One file's bytes. Its own function so the suite can make a read fail."""
    with open(real, "rb") as handle:
        return handle.read()


# --------------------------------------------------------------------------
#   Compression and the content address
# --------------------------------------------------------------------------


def sha256_bytes(data: bytes) -> str:
    """The name a saved version is kept under: sha256 of the raw bytes."""
    return hashlib.sha256(data).hexdigest()


def _gzip_bytes(data: bytes) -> bytes:
    """Deterministic gzip: the same bytes always pack to the same file.

    `mtime=0` and no file name in the header, so two runs (or two machines)
    that compress the same content get the same bytes - which is what lets a
    test compare the stored copy rather than just trust it.
    """
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=6, mtime=0) as handle:
        handle.write(data)
    return buf.getvalue()


def _gunzip_bytes(packed: bytes, limit: int = 0) -> bytes:
    """The unpacked bytes. With a positive `limit`, read at most one byte past
    it, so a corrupt or tampered copy cannot unpack into an unbounded amount of
    memory before the caller refuses it."""
    with gzip.GzipFile(fileobj=io.BytesIO(packed), mode="rb") as handle:
        if isinstance(limit, int) and limit > 0:
            return handle.read(limit + 1)
        return handle.read()


def blob_path(sha256: str) -> Path:
    """Where one saved version lives. The name is checked, never guessed at."""
    sha = str(sha256 or "").strip().lower()
    if not _SHA.match(sha):
        raise Refused(WORDS["bad_sha"])
    return blobs_dir() / f"{sha}.gz"


def _store_blob(data: bytes, sha: str) -> tuple:
    """(path, packed size, created) - one copy per distinct content.

    An existing file under this name is the same content by definition (the
    name IS the hash), so it is not written again; that is the dedup the
    feature promises. A write that fails is a plain refusal, and its temporary
    file is removed so a half-copied blob cannot sit under a real name.
    """
    path = blob_path(sha)
    try:
        if path.is_file():
            # THE NAME IS NOT ENOUGH. A blob planted or corrupted under a real
            # content address must never be trusted just because the file
            # exists: re-hash it before dedup, and refuse rather than report a
            # copy that is not this content.
            try:
                stored = _load_blob(sha)
            except Refused:
                raise
            except Exception:
                raise Refused(WORDS["damaged"])
            if stored != data:
                raise Refused(WORDS["damaged"])
            return path, path.stat().st_size, False
    except Refused:
        raise
    except OSError:
        pass
    packed = _gzip_bytes(data)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise Refused(WORDS["write_failed"].format(why=type(exc).__name__))
    tmp = path.with_name(path.name + f".{uuid.uuid4().hex[:8]}.tmp")
    try:
        with open(tmp, "wb") as handle:
            handle.write(packed)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except OSError as exc:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise Refused(WORDS["write_failed"].format(why=type(exc).__name__))
    return path, len(packed), True


def _load_blob(sha256: str) -> bytes:
    """The saved bytes for one content address, or a plain refusal.

    The name IS the sha256 of the unpacked bytes, so it is checked again here
    (F3, 2026-10-18): a copy that was altered, or merely corrupted, is refused
    rather than written into a file whose card named the real hash. The unpack
    is read with a one-byte-over-the-limit cap first, so a tampered gzip cannot
    allocate an unbounded amount of memory or write a file larger than the
    store's own ceiling.
    """
    sha = str(sha256 or "").strip().lower()
    path = blob_path(sha)
    try:
        packed = path.read_bytes()
    except FileNotFoundError:
        raise Refused(WORDS["no_version"])
    except OSError as exc:
        raise Refused(WORDS["read_failed"].format(why=type(exc).__name__))
    try:
        data = _gunzip_bytes(packed, limit=MAX_FILE_BYTES)
    except (OSError, EOFError):
        raise Refused(WORDS["damaged"])
    if len(data) > MAX_FILE_BYTES:
        raise Refused(WORDS["unpacked_too_big"])
    if sha256_bytes(data) != sha:
        raise Refused(WORDS["damaged"])
    return data


def _refuse_reparse(real: str) -> None:
    """Refuse when any folder between the root and the file is a link/junction.

    Walked with `lstat` at WRITE time, after the card: a parent folder swapped
    for a junction between the card's last `_check_path` and this write is seen
    here rather than silently followed. Windows marks the reparse attribute on
    junctions as well as symlinks, so the attribute is checked too (a junction
    is not `os.path.islink` on every Python version). A component that has
    vanished mid-walk is a change too, and refused.
    """
    path = os.path.abspath(real)
    parts = Path(path).parts
    current = parts[0] if parts else path
    for part in parts[1:]:
        current = os.path.join(current, part)
        try:
            info = os.lstat(current)
        except OSError:
            raise Refused("The folder changed while the card was up, so nothing "
                          "was written.")
        attrs = int(getattr(info, "st_file_attributes", 0) or 0)
        if os.path.islink(current) or (attrs & 0x400):
            raise Refused("The folder changed while the card was up, so nothing "
                          "was written.")


def _recheck_destination(real: str, roots_list: list) -> None:
    """Re-prove at WRITE time that `real` is still the allowed file itself.

    The last `_check_path` can be several operations (and one card) away from
    the write. This resolves the path again, requires it to resolve to itself
    and to be inside an allowed folder, and refuses ANY link or junction on the
    way - so a parent-directory swap cannot redirect the restore.
    """
    try:
        resolved = os.path.realpath(real)
    except Exception:
        raise Refused(WORDS["no_path"])
    if os.path.normcase(os.path.abspath(resolved)) != os.path.normcase(os.path.abspath(real)):
        raise Refused("The file moved while the card was up, so nothing was written.")
    if not any(_inside(root, resolved) for root in roots_list):
        raise Refused("The file moved while the card was up, so nothing was written.")
    _refuse_reparse(real)


def _open_destination_handle(real: str, roots_list: list) -> int:
    """Open the DESTINATION itself, refusing a reparse point, and return its fd.

    This is the second half of the race fix (T slice, 2026-10-18): the last
    `_check_path` can be a card away from the write, so the write does not
    follow the path again. A junction/symlink swapped in after the check is
    refused by `FILE_FLAG_OPEN_REPARSE_POINT` (Windows: open the reparse point
    ITSELF, then refuse it) / `O_NOFOLLOW` (elsewhere), and the file is written
    through this one handle. A language-level restore cannot do better without
    a restricted token; this is the OS boundary the host audit asked for here.
    """
    if os.name == "nt":
        import ctypes
        import msvcrt
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateFileW.restype = wintypes.HANDLE
        kernel32.CreateFileW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
            wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        kernel32.GetFileInformationByHandle.restype = wintypes.BOOL
        kernel32.GetFileInformationByHandle.argtypes = [
            wintypes.HANDLE, wintypes.LPVOID]
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

        class _ByHandleFileInformation(ctypes.Structure):
            _fields_ = [
                ("dwFileAttributes", wintypes.DWORD),
                ("ftCreationTime", wintypes.FILETIME),
                ("ftLastAccessTime", wintypes.FILETIME),
                ("ftLastWriteTime", wintypes.FILETIME),
                ("dwVolumeSerialNumber", wintypes.DWORD),
                ("nFileSizeHigh", wintypes.DWORD),
                ("nFileSizeLow", wintypes.DWORD),
                ("nNumberOfLinks", wintypes.DWORD),
                ("nFileIndexHigh", wintypes.DWORD),
                ("nFileIndexLow", wintypes.DWORD),
            ]

        GENERIC_WRITE = 0x40000000
        OPEN_EXISTING = 3
        FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
        FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
        invalid = ctypes.c_void_p(-1).value
        handle = kernel32.CreateFileW(
            str(real), GENERIC_WRITE, 0, None, OPEN_EXISTING,
            FILE_FLAG_OPEN_REPARSE_POINT, None)
        if not handle or int(handle) == invalid:
            raise Refused(WORDS["write_failed"].format(why="open refused"))
        info = _ByHandleFileInformation()
        if not kernel32.GetFileInformationByHandle(handle, ctypes.byref(info)):
            kernel32.CloseHandle(handle)
            raise Refused(WORDS["write_failed"].format(why="handle unreadable"))
        if int(info.dwFileAttributes) & FILE_ATTRIBUTE_REPARSE_POINT:
            kernel32.CloseHandle(handle)
            raise Refused("The file changed while the card was up, so nothing was written.")
        try:
            return msvcrt.open_osfhandle(handle, os.O_WRONLY | os.O_BINARY)
        except OSError:
            kernel32.CloseHandle(handle)
            raise Refused(WORDS["write_failed"].format(why="handle"))
    flags = os.O_WRONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        return os.open(real, flags)
    except OSError as exc:
        raise Refused(WORDS["write_failed"].format(why=type(exc).__name__))


def _write_file(real: str, data: bytes, roots=None) -> None:
    """Replace one file's bytes THROUGH ONE OPENED HANDLE, or a plain refusal.

    The destination is re-proved just before it is opened, then opened through
    `_open_destination_handle` (reparse points refused, by handle), then
    re-proved once more before a byte is written. The bytes go through that
    already-open handle, so a folder swapped for a junction after the checks
    cannot redirect the write - no path is followed a second time.

    This is a deliberate trade: the old write was a temp file plus an atomic
    path `os.replace`, which could follow a swapped parent. The current write
    can leave a partial file if the PC dies mid-write; the journal row and the
    receipt were already written, so a restore that fails is visible, and the
    host audit's race is closed. `roots` is the card's own allowed-folder list;
    a caller that omits it gets the live list, never "no rule".
    """
    roots_list = _clean_roots(roots) if roots is not None else allowed_roots()
    if not roots_list:
        raise Refused(WORDS["no_roots"])
    _recheck_destination(real, roots_list)
    handle = _open_destination_handle(real, roots_list)
    try:
        # The path may have been swapped between the check and the open; the
        # handle pins the file, and this proves the path still names it.
        _recheck_destination(real, roots_list)
        try:
            os.ftruncate(handle, 0)
            offset = 0
            while offset < len(data):
                wrote = os.write(handle, data[offset:])
                if wrote <= 0:
                    raise OSError("short write")
                offset += wrote
            os.fsync(handle)
        except OSError as exc:
            raise Refused(WORDS["write_failed"].format(why=type(exc).__name__))
    finally:
        try:
            os.close(handle)
        except OSError:
            pass



# --------------------------------------------------------------------------
#   The journal (guardian.jsonl) and the pins
# --------------------------------------------------------------------------


def _append_row(row: dict) -> None:
    """Append one JSON line. Never rewrites a line that is already there."""
    path = index_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    with _LOCK:
        with open(path, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(line)


def rows() -> list:
    """Every row this journal can read, oldest first. A bad line is skipped."""
    path = index_path()
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return []
    except OSError:
        return []
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue                  # a half-written last line is not a row
        if isinstance(row, dict):
            out.append(row)
            if len(out) >= MAX_ROWS_READ:
                break
    return out


def _load_pins(strict: bool = False) -> list:
    """The pinned content addresses. `strict` says so loudly when unreadable.

    Pruning passes `strict=True`: a pins file that cannot be read must stop the
    pruning rather than be read as "nothing is pinned", because a pinned copy
    being removed by a damaged settings file is exactly what a pin is for.
    """
    path = pins_path()
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    except OSError:
        if strict:
            raise
        return []
    try:
        doc = json.loads(raw)
    except ValueError:
        if strict:
            raise
        return []
    items = doc.get("pins") if isinstance(doc, dict) else None
    if items is None:
        return []
    if not isinstance(items, list):
        if strict:
            raise ValueError("the pins file is not a list")
        return []
    return [str(s).lower() for s in items if isinstance(s, str) and _SHA.match(s.lower())]


def _save_pins(items: list) -> None:
    path = pins_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps({"pins": sorted({str(s).lower() for s in items if _SHA.match(str(s).lower())})},
                      indent=1, sort_keys=True) + "\n"
    tmp = path.with_name(path.name + f".{uuid.uuid4().hex[:8]}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(body)
        os.replace(tmp, path)
    except OSError as exc:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise Refused(WORDS["write_failed"].format(why=type(exc).__name__))


def pinned() -> list:
    """The content addresses the owner pinned. A pinned blob is never pruned."""
    return _load_pins()


def purge_words(text) -> int:
    """Delete UNPINNED saved versions whose bytes contain `text`. Returns how many.

    Audit DATA D2/D5 (2026-10-18): the file time machine keeps the bytes a file
    had before Jarvis changed it, so a forgotten fact's words could survive in a
    blob after the fact itself is erased. Forget/Erase call this with the erased
    words; only blobs that still contain them go, and a PINNED version is never
    removed (the pin is the owner's own decision to keep that version).
    Best effort by design - an unreadable blob, a missing store or an unreadable
    pins file means nothing is deleted rather than a pin being broken.
    """
    needle = " ".join(str(text or "").split()).encode("utf-8")
    if not needle:
        return 0
    try:
        pins = set(_load_pins(strict=False))
    except Exception:
        return 0                      # never guess "nothing is pinned"
    directory = blobs_dir()
    if not directory.is_dir():
        return 0
    removed = 0
    for p in sorted(directory.glob("*.gz")):
        sha = p.stem.lower()
        if sha in pins:
            continue
        try:
            raw = gzip.decompress(p.read_bytes())
        except Exception:
            continue
        if needle.lower() not in raw.lower():
            continue
        try:
            p.unlink()
            removed += 1
        except OSError:
            continue
    return removed


def pin(sha256: str) -> dict:
    """Keep one saved version for good. Never raises; plain words on failure."""
    try:
        sha = str(sha256 or "").strip().lower()
        if not _SHA.match(sha):
            raise Refused(WORDS["bad_sha"])
        items = _load_pins()
        if sha not in items:
            items.append(sha)
            _save_pins(items)
        return {"ok": True, "sha256": sha, "pinned": _load_pins(),
                "words": "That version is pinned, so it will not be removed to save space."}
    except Refused as exc:
        return {"ok": False, "error": str(exc), "words": str(exc)}
    except Exception as exc:                    # pragma: no cover - disk gone
        return {"ok": False, "error": f"the pin could not be saved ({type(exc).__name__})"}


def unpin(sha256: str) -> dict:
    """Stop keeping one saved version for good. Never raises."""
    try:
        sha = str(sha256 or "").strip().lower()
        if not _SHA.match(sha):
            raise Refused(WORDS["bad_sha"])
        items = [s for s in _load_pins() if s != sha]
        _save_pins(items)
        return {"ok": True, "sha256": sha, "pinned": _load_pins(),
                "words": "That version is no longer pinned; it can be removed to save space."}
    except Refused as exc:
        return {"ok": False, "error": str(exc), "words": str(exc)}
    except Exception as exc:                    # pragma: no cover - disk gone
        return {"ok": False, "error": f"the pin could not be saved ({type(exc).__name__})"}


# --------------------------------------------------------------------------
#   Quota
# --------------------------------------------------------------------------


def _size_words(count) -> str:
    try:
        n = max(0, int(count))
    except (TypeError, ValueError):
        return "0 bytes"
    if n < 1024:
        return f"{n} bytes"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


def _ages() -> dict:
    """sha -> the first timestamp it was seen at (the oldest snapshot wins)."""
    out = {}
    for row in rows():
        sha = row.get("before_sha256")
        stamp = row.get("timestamp")
        if not isinstance(sha, str) or not _SHA.match(sha.lower()):
            continue
        if not isinstance(stamp, (int, float)) or isinstance(stamp, bool):
            continue
        sha = sha.lower()
        if sha not in out or float(stamp) < out[sha]:
            out[sha] = float(stamp)
    return out


def usage() -> dict:
    """How much space the store is using, and what is pinned. Never raises."""
    try:
        sizes = {}
        directory = blobs_dir()
        if directory.is_dir():
            for path in directory.glob("*.gz"):
                try:
                    sizes[path.name[:-3]] = path.stat().st_size
                except OSError:
                    continue
        total = sum(sizes.values())
        kept = [s for s in _load_pins() if s in sizes]
        return {"ok": True, "blob_bytes": total, "blobs": len(sizes),
                "quota_bytes": QUOTA_BYTES, "pinned": len(kept),
                "over_quota": total > QUOTA_BYTES,
                "words": (f"The time machine holds {len(sizes)} saved version(s), "
                          f"{_size_words(total)} of a {_size_words(QUOTA_BYTES)} limit."),
                "sizes": sizes, "pinned_sha256": kept}
    except Exception as exc:                    # pragma: no cover - disk gone
        return {"ok": False, "error": f"the store could not be read ({type(exc).__name__})"}


def _prune_words(pruned: list, kept_pinned: int, total: int, protected: str = "") -> str:
    """What pruning did, in plain words. The brief's "say what was pruned"."""
    removed = sum(int(p.get("bytes") or 0) for p in pruned)
    if not pruned:
        if total <= QUOTA_BYTES:
            return (f"Nothing needed removing: the saved copies are under the "
                    f"{_size_words(QUOTA_BYTES)} limit.")
        over = f"the store is over the {_size_words(QUOTA_BYTES)} limit, but "
        if kept_pinned and protected:
            return (f"Nothing was removed: {over}the versions left are pinned "
                    f"({kept_pinned}) or the copy just saved, and a pinned version is "
                    f"never removed.")
        if kept_pinned:
            return (f"Nothing was removed: {over}every version left is pinned "
                    f"({kept_pinned}) and a pinned version is never removed.")
        return (f"Nothing was removed: {over}the copy just saved is what is over it, "
                f"and it is kept so it can still be put back.")
    words = (f"Removed {len(pruned)} old version(s) ({_size_words(removed)}) to stay under "
             f"the {_size_words(QUOTA_BYTES)} limit.")
    if kept_pinned:
        words += (f" {kept_pinned} pinned version(s) were kept, because a pinned version is "
                  f"never removed.")
    return words


def prune(protect: str = "") -> dict:
    """Remove the oldest UNPINNED blobs until the store is under the quota.

    Age is the first snapshot that stored a content address (the journal is
    append-only, so that order cannot be rewritten by a later copy); a blob
    with no row falls back to the folder's own timestamp. A pinned blob is
    skipped, never removed, even when the store then stays over the quota; so
    is `protect`, the version the caller has just saved - a copy that was
    removed in the same breath as it was taken would be no copy at all. Never
    raises - a pruning that cannot run must not fail the snapshot that asked
    for it - and it says what it did in plain words.
    """
    try:
        protected = str(protect or "").strip().lower()
        if not _SHA.match(protected):
            protected = ""
        directory = blobs_dir()
        sizes = {}
        if directory.is_dir():
            for path in directory.glob("*.gz"):
                try:
                    sizes[path.name[:-3]] = path.stat().st_size
                except OSError:
                    continue
        total = sum(sizes.values())
        if total <= QUOTA_BYTES:
            return {"ok": True, "pruned": [], "freed": 0, "blob_bytes": total,
                    "quota_bytes": QUOTA_BYTES, "kept_pinned": 0,
                    "words": _prune_words([], 0, total)}
        ages = _ages()
        try:
            base = directory.stat().st_mtime
        except OSError:
            base = time.time()
        try:
            pins = set(_load_pins(strict=True))
        except Exception:
            return {"ok": False, "pruned": [], "freed": 0, "blob_bytes": total,
                    "quota_bytes": QUOTA_BYTES, "kept_pinned": 0,
                    "error": "the list of pinned versions could not be read, so nothing "
                             "was removed - a pinned copy must never be removed by accident",
                    "words": ("The list of pinned versions could not be read, so nothing "
                              "was removed: a pinned copy must never be removed by "
                              "accident.")}
        order = sorted(sizes, key=lambda s: (ages.get(s, base), s))
        kept_pinned = sum(1 for s in order if s in pins)
        pruned = []
        for sha in order:
            if total <= QUOTA_BYTES:
                break
            if sha in pins or sha == protected:
                continue
            path = directory / f"{sha}.gz"
            try:
                size = path.stat().st_size
                path.unlink()
            except OSError:
                continue
            total -= size
            pruned.append({"sha256": sha, "bytes": size})
        words = _prune_words(pruned, kept_pinned, total, protected)
        return {"ok": True, "pruned": pruned, "freed": sum(p["bytes"] for p in pruned),
                "blob_bytes": total, "quota_bytes": QUOTA_BYTES,
                "kept_pinned": kept_pinned, "words": words}
    except Exception as exc:                    # pragma: no cover - disk gone
        return {"ok": False, "pruned": [], "freed": 0, "blob_bytes": 0,
                "quota_bytes": QUOTA_BYTES, "kept_pinned": 0,
                "error": f"the old copies could not be tidied ({type(exc).__name__})",
                "words": "The old copies could not be tidied, so nothing was removed."}


# --------------------------------------------------------------------------
#   Receipts - the EXISTING store, not a second one
# --------------------------------------------------------------------------


def _receipts():
    """jarvis_receipts, or None. A missing store is said out loud, not raised."""
    try:
        import jarvis_receipts
        return jarvis_receipts
    except Exception:
        return None


def _new_copy_id() -> str:
    """An opaque name for ONE journal row, carried on the receipt instead of the path.

    A receipt's before snapshot is scrubbed by `jarvis_receipts.py` before it
    is written - that is the project's rule, and it is right: a receipt may be
    shown or listed. The scrubber redacts things that look like a user name,
    and a Windows path carries one, so the real path cannot ride in a receipt.
    The opaque id can: it names a row in `guardian.jsonl`, where the path
    already lives, and it is never a path or a secret itself.
    """
    return "gc" + uuid.uuid4().hex


def _path_for_copy(copy_id) -> Optional[str]:
    """The path one journal row names, or None. Used after a restart."""
    wanted = str(copy_id or "").strip()
    if not wanted:
        return None
    for row in reversed(rows()):
        if row.get("copy_id") == wanted:
            path = row.get("path")
            if isinstance(path, str) and path:
                return path
            return None
    return None


def _restore_path(real: str, sha: str) -> None:
    """Put one saved version back over one file. The rules are applied again here."""
    real, _roots = _check_path(real, None)
    data = _load_blob(sha)
    _write_file(real, data)


def _undo_in_memory(real: str, sha: str) -> None:
    """The live-callable half of Undo: the path never left this process."""
    _restore_path(real, sha)


def _undo_saved_version(before) -> None:
    """The receipts restorer: put a saved version back from its before snapshot.

    Called by `jarvis_receipts.undo()` after a restart, when the live callable
    is gone by definition. The before snapshot carries the content address and
    an opaque copy id, never the path (the receipt store scrubs its rows; see
    `_new_copy_id`); the path is read back from this module's own journal. The
    path rules are applied again, because the snapshot was taken earlier and
    the file may have moved since.
    """
    got = before if isinstance(before, dict) else {}
    sha = got.get("sha256")
    if not isinstance(sha, str):
        raise ValueError("the receipt carries no saved version to put back")
    path = _path_for_copy(got.get("copy_id"))
    if not path:
        raise ValueError("the receipt's journal row is gone, so there is no file to put back")
    _restore_path(path, sha)


def _register_restorers(R) -> None:
    """Say how both kinds of receipt are put back after a restart."""
    try:
        R.register_restorer(TOOL_SNAPSHOT, _undo_saved_version)
        R.register_restorer(TOOL_RESTORE, _undo_saved_version)
    except Exception:
        pass


def _clean_reason(reason) -> str:
    try:
        text = " ".join(str(reason or "").split())
    except Exception:
        return ""
    return text[:MAX_REASON]


def _record_snapshot(real: str, sha: str, size: int, reason: str, copy_id: str) -> str:
    """One receipt saying a copy was taken before the file changes. "" on failure.

    `record()` is the real API of jarvis_receipts.py: it writes the row, scrubs
    every word, keeps the undo callable while this process lives and never
    raises into its caller. The before snapshot holds the content address, the
    size and an opaque copy id - never the bytes themselves, so a receipt can
    never grow to hold a whole file, and never the path, because the receipt
    store scrubs its strings and a Windows path carries the owner's name.
    """
    R = _receipts()
    if R is None:
        return ""
    _register_restorers(R)
    before = {"sha256": sha, "copy_id": copy_id, "size": int(size)}
    name = os.path.basename(real)
    summary = f"Jarvis saved a copy of {name} before changing it"
    if reason:
        summary += f" ({reason})"
    try:
        return str(R.record(TOOL_SNAPSHOT, summary, before=before, after=None,
                            undo=lambda: _undo_in_memory(real, sha)) or "")
    except Exception:
        return ""


def _record_restore(real: str, now_sha: str, put_back_sha: str, reason: str,
                    copy_id: str) -> str:
    """One receipt for a restore, written BEFORE the write. "" on failure.

    `before` is what the file holds now and `after` is the version being put
    back, so the existing Undo button reverses THIS restore: putting the
    current version back. That is the "a restore can itself be undone" half.
    """
    R = _receipts()
    if R is None:
        return ""
    _register_restorers(R)
    before = {"sha256": now_sha, "copy_id": copy_id}
    after = {"sha256": put_back_sha}
    name = os.path.basename(real)
    summary = f"Jarvis put back an earlier version of {name}"
    if reason:
        summary += f" ({reason})"
    try:
        return str(R.record(TOOL_RESTORE, summary, before=before, after=after,
                            undo=lambda: _undo_in_memory(real, now_sha)) or "")
    except Exception:
        return ""


# --------------------------------------------------------------------------
#   The approval card - the EXISTING one, action undo_action
# --------------------------------------------------------------------------


def card_text(path: str, sha_before: str) -> str:
    """The words on the one card. The file's NAME and a short hash only.

    No contents and no full path: the card says enough to decide - which file,
    and that the current version is saved first - and nothing the owner's
    private words could leak through.
    """
    name = os.path.basename(str(path or "")) or "a file"
    short = str(sha_before or "")[:12]
    lines = [CARD_HEAD, "", f"File: {name}"]
    if short:
        lines.append(f"The version to put back: {short}")
    lines += ["", CARD_NOTE, "", CARD_TAIL]
    return "\n".join(lines)


def _gate(action: str, detail: dict, prompt: str):
    """The one permission model, imported the way every other module does."""
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def _approved(verdict) -> bool:
    """Did a PERSON say yes? An outcome of exactly `"approved"`, nothing less.

    `allowed` is not enough: the gate returns allowed=True with nobody in the
    loop at tier "notify"/"auto", and older verdict objects could leave
    `outcome` at None. A missing or different outcome is NOT a person's yes
    (F5, 2026-10-18) - a restore writes a file, so only a card approval counts.
    """
    try:
        allowed = getattr(verdict, "allowed", False) is True
        outcome = str(getattr(verdict, "outcome", "") or "")
        return bool(allowed and outcome == "approved")
    except Exception:
        return False


def _ask(gate, detail: dict, prompt: str) -> tuple:
    """(verdict, why-not) from the caller's gate or the real one. Never raises."""
    try:
        checker = gate or _gate
        return checker(UNDO_ACTION, detail, prompt), ""
    except Exception as exc:
        # The exception's NAME only: a message can carry a path, and this is
        # the path of a file the owner asked Jarvis to keep private.
        return None, type(exc).__name__


# --------------------------------------------------------------------------
#   snapshot_before_write - the copy that makes the rest possible
# --------------------------------------------------------------------------


def _file_limit(value) -> int:
    """The per-file limit this call uses: `max_file_bytes`, or MAX_FILE_BYTES.

    A caller that legitimately guards a bigger file passes its own. Anything
    that is not a positive whole number falls back to the ceiling rather than
    refusing everything: a broken argument must not become a limit nobody
    asked for.
    """
    if value is None:
        return MAX_FILE_BYTES
    try:
        limit = int(value)
    except (TypeError, ValueError):
        return MAX_FILE_BYTES
    return limit if limit > 0 else MAX_FILE_BYTES


def _plain_refusal(path, exc) -> dict:
    """The result a `Refused` becomes: plain words, nothing touched, no receipt."""
    return {"ok": False, "refused": True, "path": str(path),
            "error": str(exc), "words": str(exc), "receipt_id": ""}


def _too_large(path, size: int, limit: int) -> dict:
    """The structured refusal a file over the ceiling gets, before any read."""
    return {"ok": False, "refused": True, "too_large": True,
            "error": "file_too_large_for_guardian",
            "size_bytes": int(size), "max_file_bytes": int(limit),
            "path": str(path), "receipt_id": "",
            "words": WORDS["too_big"].format(limit=_size_words(limit))}


def snapshot_before_write(path, *, reason: str = "", roots=None, now=None,
                          max_file_bytes=None) -> dict:
    """Save the file's CURRENT bytes, and record that a change is coming.

    Refuses - plainly, touching nothing - a link, a path outside the allowed
    folders, a folder, a missing or unreadable file. A file bigger than
    `max_file_bytes` (MAX_FILE_BYTES, 25 MiB, when the caller passes nothing)
    is refused BEFORE a single byte of it is read: the answer carries
    `error="file_too_large_for_guardian"`, `size_bytes` and `max_file_bytes`,
    and neither the store nor the journal changes. Otherwise it hashes the
    bytes, stores one compressed copy per distinct content, records a receipt
    with the existing jarvis_receipts.py, appends the journal row and prunes
    the store to the quota. Returns a dict; it never raises.

    Call this BEFORE the write, not after: the point is to have the previous
    bytes when there is no way back without them.
    """
    reason_text = _clean_reason(reason)
    limit = _file_limit(max_file_bytes)
    try:
        real, _root_list = _check_path(path, roots)
        try:
            if os.path.isdir(real):
                raise Refused(WORDS["folder"])
            if not os.path.isfile(real):
                raise Refused(WORDS["missing"])
            size = os.path.getsize(real)
            if size > limit:
                return _too_large(real, size, limit)
            data = _read_bytes(real)
        except Refused:
            raise
        except OSError as exc:
            if not os.path.isfile(real):
                raise Refused(WORDS["missing"])
            raise Refused(WORDS["read_failed"].format(why=type(exc).__name__))
        # THE FILE CAN GROW between getsize and the read. The read has happened
        # by now, so this is the second half of the same ceiling: a file over
        # the limit is still refused before it is hashed, stored or recorded.
        if len(data) > limit:
            return _too_large(real, len(data), limit)
        sha = sha256_bytes(data)
        blob, packed_size, created = _store_blob(data, sha)
        copy_id = _new_copy_id()
        receipt_id = _record_snapshot(real, sha, len(data), reason_text, copy_id)
        stamp = float(now) if isinstance(now, (int, float)) and not isinstance(now, bool) \
            else time.time()
        row = {"timestamp": stamp, "path": real, "before_sha256": sha,
               "size": len(data), "reason": reason_text, "receipt_id": receipt_id,
               "copy_id": copy_id}
        try:
            _append_row(row)
        except Exception as exc:
            return {"ok": False, "path": real, "before_sha256": sha,
                    "snapshot_id": copy_id, "size": len(data),
                    "stored": created, "receipt_id": receipt_id, "row": row,
                    "error": (f"The copy was saved, but its record could not be written "
                              f"({type(exc).__name__}), so the list of versions is not "
                              f"complete."),
                    "words": "The copy was saved but its record could not be written."}
        pruned = prune(protect=sha)
        name = os.path.basename(real)
        if created:
            words = WORDS["saved"].format(name=name, size=_size_words(len(data)))
        else:
            words = WORDS["already_saved"].format(name=name)
        if receipt_id:
            words += " One Undo puts it back."
        else:
            words += WORDS["saved_no_receipt"]
        return {"ok": True, "path": real, "before_sha256": sha,
                "snapshot_id": copy_id, "size": len(data),
                "stored": created, "blob_bytes": packed_size, "receipt_id": receipt_id,
                "row": row, "pruned": pruned.get("pruned", []),
                "prune_words": pruned.get("words", ""), "words": words}
    except Refused as exc:
        return _plain_refusal(path, exc)
    except Exception as exc:                    # pragma: no cover - last resort
        return {"ok": False, "path": str(path), "receipt_id": "",
                "error": f"the copy could not be saved ({type(exc).__name__}), so nothing "
                         f"was touched.",
                "words": "The copy could not be saved, so nothing was touched."}


# --------------------------------------------------------------------------
#   diff_versions - what changed between a saved version and now
# --------------------------------------------------------------------------


def _looks_binary(data: bytes) -> bool:
    return b"\x00" in data[:8192]


def _as_text(data: bytes, limit: int) -> tuple:
    """(text, cut off?) - decoded as UTF-8 with replacement, at most `limit` bytes."""
    try:
        cut = len(data) > limit
        return data[:limit].decode("utf-8", errors="replace"), cut
    except Exception:                           # pragma: no cover - decode is total
        return "", True


def diff_versions(path, sha_before, *, roots=None, max_bytes=MAX_DIFF_BYTES) -> dict:
    """A bounded unified diff: the saved version on the left, the file now on the right.

    Answers `same: True` when the file is exactly that version, `binary: True`
    with no line diff when either side is binary, and refuses an unknown
    version in plain words. `truncated` is True when the answer was cut - a
    difference too big to show is said out loud, never silently shortened.
    Never raises.
    """
    try:
        sha = str(sha_before or "").strip().lower()
        if not _SHA.match(sha):
            raise Refused(WORDS["bad_sha"])
        real, _roots = _check_path(path, roots)
        old = _load_blob(sha)
        new = _check_file(real)
        new_sha = sha256_bytes(new)
        base = {"ok": True, "path": real, "before_sha256": sha,
                "after_sha256": new_sha, "diff": "", "truncated": False,
                "binary": False, "same": False}
        if new_sha == sha:
            base.update({"same": True, "words": WORDS["same_diff"]})
            return base
        if _looks_binary(old) or _looks_binary(new):
            base.update({"binary": True, "words": WORDS["binary"]})
            return base
        old_text, old_cut = _as_text(old, MAX_TEXT_BYTES)
        new_text, new_cut = _as_text(new, MAX_TEXT_BYTES)
        try:
            limit = int(max_bytes)
        except (TypeError, ValueError):
            limit = MAX_DIFF_BYTES
        limit = max(64, min(MAX_DIFF_BYTES, limit))
        diff = "\n".join(difflib.unified_diff(
            old_text.splitlines(), new_text.splitlines(),
            fromfile=f"before ({sha[:12]})", tofile="now", lineterm=""))
        truncated = bool(old_cut or new_cut)
        if len(diff) > limit:
            diff = diff[:limit] + "\n... (the rest of the difference is not shown) ...\n"
            truncated = True
        words = WORDS["diff"] + (WORDS["diff_cut"] if truncated else "")
        base.update({"diff": diff, "truncated": truncated, "words": words})
        return base
    except Refused as exc:
        return {"ok": False, "refused": True, "path": str(path), "error": str(exc),
                "words": str(exc), "diff": "", "truncated": False, "binary": False,
                "same": False}
    except Exception as exc:                    # pragma: no cover - last resort
        return {"ok": False, "path": str(path),
                "error": f"the difference could not be worked out ({type(exc).__name__})",
                "words": "The difference could not be worked out.", "diff": "",
                "truncated": False, "binary": False, "same": False}


# --------------------------------------------------------------------------
#   restore_version - one click, and never silent
# --------------------------------------------------------------------------


def _version_was_saved_from(real: str, sha: str) -> bool:
    """Did this file's own history save this exact version? (F2, 2026-10-18)

    A saved version is content-addressed, so the bytes alone do not say which
    file they came from. Restoring is only safe when a journal row for THIS
    resolved path names this sha; otherwise an approved card for file B could
    write file A's saved words into it.
    """
    try:
        for row in rows():
            if not isinstance(row, dict) or row.get("before_sha256") != sha:
                continue
            saved_path = row.get("path")
            if not isinstance(saved_path, str) or not saved_path:
                continue
            try:
                if os.path.normcase(os.path.realpath(saved_path)) == os.path.normcase(real):
                    return True
            except OSError:
                continue
    except Exception:
        return False
    return False


def _discard_receipt(receipt_id) -> None:
    """Take the receipt back when the change it announced did not happen.

    The receipt is written BEFORE the write on purpose; if the write then
    fails, no receipt may claim a restore that never happened (F4, 2026-10-18).
    Best effort: a store that cannot discard is louder elsewhere, never here.
    """
    if not receipt_id:
        return
    R = _receipts()
    if R is None:
        return
    try:
        discard = getattr(R, "discard", None)
        if callable(discard):
            discard(receipt_id)
    except Exception:
        pass


def restore_version(path, sha_before, *, gate=None, roots=None, reason: str = "",
                    now=None) -> dict:
    """Put one saved version back, on a person's yes and nothing less.

    The order is the whole safety story (F1-F5, 2026-10-18):

      1. the path rules, the saved bytes (whose name is verified against them
         again) and the requirement that THIS file's own history saved this
         version are checked first - no card is ever raised for something that
         could only refuse;
      2. the ONE permission model is asked, with the EXISTING `undo_action`
         card; only an outcome of exactly "approved" is a person's yes. A
         denied, timed-out or unraisable card writes nothing;
      3. what is here NOW is read AFTER the card - an edit made while the person
         was deciding is the version saved and the version Undo puts back -
         then it is saved, with a NEW receipt and journal row BEFORE the write.
         If any of those cannot be recorded, nothing is written;
      4. the path rules are applied once more, then the bytes are replaced in
         one atomic rename. A write that fails takes its receipt back, so no
         receipt claims a restore that did not happen.

    Never raises; returns a dict with plain words either way.
    """
    reason_text = _clean_reason(reason)
    receipt_id = ""
    try:
        sha = str(sha_before or "").strip().lower()
        if not _SHA.match(sha):
            raise Refused(WORDS["bad_sha"])
        real, roots_list = _check_path(path, roots)
        old = _load_blob(sha)
        if not _version_was_saved_from(real, sha):
            raise Refused(WORDS["not_this_files_version"])
        # This read only answers "already that version?" before bothering the
        # person; its bytes are discarded and never stored. The version saved
        # for Undo is re-read AFTER the card (below), so an edit made during
        # the wait is the version that gets saved and put back by Undo.
        current = _check_file(real)
        if sha256_bytes(current) == sha:
            return {"ok": True, "changed": False, "same": True, "path": real,
                    "before_sha256": sha, "after_sha256": sha, "receipt_id": "",
                    "words": WORDS["same"]}
        detail = {"file_name": os.path.basename(real), "sha256": sha[:12],
                  "size": len(old)}
        verdict, why = _ask(gate, detail, card_text(real, sha))
        if verdict is None:
            words = WORDS["gate_failed"].format(why=why or "no way to ask")
            return {"ok": False, "refused": True, "gated": True, "path": real,
                    "error": words, "words": words}
        if not _approved(verdict):
            outcome = str(getattr(verdict, "outcome", "") or "")
            words = (WORDS["denied"] if outcome == "denied"
                     else WORDS["timed_out"] if outcome == "timed_out"
                     else WORDS["refused"])
            return {"ok": False, "refused": True, "gated": True, "outcome": outcome,
                    "path": real, "error": words, "words": words}
        # The card can wait minutes. Re-check the path, then read what is here
        # NOW: this is the version the receipt and the journal record, so Undo
        # brings back what was really replaced (not a stale pre-card copy).
        real_now, _same_roots = _check_path(path, roots_list)
        if os.path.normcase(os.path.realpath(real_now)) != os.path.normcase(real):
            raise Refused("The file moved while the card was up, so nothing was written.")
        current = _check_file(real)
        now_sha = sha256_bytes(current)
        if now_sha == sha:
            return {"ok": True, "changed": False, "same": True, "path": real,
                    "before_sha256": sha, "after_sha256": sha, "receipt_id": "",
                    "words": WORDS["same"]}
        # What is here now becomes a saved version too, so the restore itself
        # can be undone in one click. The receipt and the journal row both go
        # down BEFORE the write: a change that could not be recorded must not
        # be made (F4: every one of these failures aborts with the file as it
        # was, and takes back the receipt the failure did not complete).
        _store_blob(current, now_sha)
        copy_id = _new_copy_id()
        receipt_id = _record_restore(real, now_sha, sha, reason_text, copy_id)
        if not receipt_id:
            raise Refused(WORDS["receipt_failed"])
        stamp = float(now) if isinstance(now, (int, float)) and not isinstance(now, bool) \
            else time.time()
        row = {"timestamp": stamp, "path": real, "before_sha256": now_sha,
               "size": len(current), "reason": reason_text, "receipt_id": receipt_id,
               "copy_id": copy_id}
        try:
            _append_row(row)
        except Exception:
            raise Refused(WORDS["record_failed"])
        real_now, _same_roots = _check_path(path, roots_list)
        if os.path.normcase(os.path.realpath(real_now)) != os.path.normcase(real):
            raise Refused("The file moved while the card was up, so nothing was written.")
        _write_file(real, old, roots_list)
        pruned = prune(protect=now_sha)
        when = ""
        for candidate in reversed(rows()):
            if candidate.get("before_sha256") == sha:
                try:
                    when = time.strftime("%Y-%m-%d %H:%M",
                                         time.localtime(float(candidate.get("timestamp"))))
                except Exception:
                    when = ""
                break
        words = WORDS["restored"].format(when=when or "that day")
        return {"ok": True, "changed": True, "same": False, "path": real,
                "before_sha256": now_sha, "after_sha256": sha,
                "restored_sha256": sha, "receipt_id": receipt_id,
                "pruned": pruned.get("pruned", []),
                "prune_words": pruned.get("words", ""), "words": words}
    except Refused as exc:
        _discard_receipt(receipt_id)
        return {"ok": False, "refused": True, "path": str(path), "receipt_id": "",
                "error": str(exc), "words": str(exc)}
    except Exception as exc:                    # pragma: no cover - last resort
        _discard_receipt(receipt_id)
        return {"ok": False, "path": str(path), "receipt_id": "",
                "error": f"the version could not be put back ({type(exc).__name__})",
                "words": "The version could not be put back."}
