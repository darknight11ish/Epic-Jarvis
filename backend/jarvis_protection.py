"""jarvis_protection.py - "Protected from Jarvis": the owner's list of folders,
files and programs Jarvis may not touch, and the ONE check every other module
asks before it reads, writes, opens or controls anything.

THE OWNER'S REQUEST (2026-10-31, his own words): *"add a list of file folders,
and programs that i can manually add to (or ask jarvis to exclude in chat and
get a card) that blocks jarvis from having any access (read or write) or the
ability to make certain files or folders or programs read only"*. Two answers
came with it: **build it now**; and for a protected **program**, "read only"
means **"see it, never act"** - its window title or a screenshot may be read,
clicking, typing, opening or controlling it is refused.

TWO MODES, ONE LIST

  * ``blocked`` - no access at all. A folder or file: no read, no search hit,
    no snippet, no document read, no write, no delete, no rename, no File
    Guardian restore into it, no note-capture write into it, and no generated
    picture written into it. A program: no opening, closing or controlling it,
    and no screen reading of its windows.
  * ``readonly`` - reading allowed, changing refused. A folder or file:
    reading and search results are allowed; every write, delete, rename and
    restore is refused. A program: **see it, never act** - reading its window
    title or screenshot is allowed; opening, clicking, typing, closing or
    controlling it is refused.

WHY THIS IS A MODULE AND NOT A SETTING IN ONE FEATURE

The request is "block access", which is only real if EVERY door asks. So the
module exposes a small, boring API and the existing modules call it BEFORE they
do anything (see ``ENFORCEMENT`` below). Protection WINS over every allow-list
("Folders Jarvis may look in", app-control's list), over a chat request, and
over any default tier - a tier ``auto`` read is still refused. A damaged or
missing store is **empty and safe**: it never crashes, never blocks the
feature's own settings, and never means "protect everything".

THE STORE

``protected-items.json`` beside the other Jarvis settings files on this PC
(``jarvis_framework.CONFIG_DIR``, or ``OPENJARVIS_CONFIG_DIR``): readable JSON,
versioned, one entry per item::

    {"version": 1,
     "items": [
       {"id": "prot_ab12cd34", "kind": "folder", "target": "C:\\...\\Taxes",
        "mode": "blocked", "added": "2026-10-31T08:00:00Z", "added_by": "owner"}
     ]}

``kind`` is ``folder`` | ``file`` | ``program``. ``target`` is an absolute PC
path for folders/files (folders protect their whole subtree, after links are
resolved) and a lowercase executable name for a program (``notepad.exe``).
Matching is case-insensitive, normalises ``..``, ``/`` and separators, and
every path is resolved before it is compared, so a junction or symlink that
LEADS INTO a protected folder is protected too.

THE ROUTES (all token-authenticated, ``X-Jarvis-Client`` on every call)

    GET  /api/protection                 the list, in the PC's own words
    POST /api/protection/add             the desktop Settings' own act - no card
    POST /api/protection/remove          ONE card (action ``unprotect_item``)
    POST /api/protection/propose         the chat path - ONE card (``protect_item``)
    GET  /api/protection/propose?id=     how one proposal ended

The chat side is the model tool ``protect_from_jarvis`` (in jarvis_agent.py):
the model proposes, the owner decides on ONE ordinary approval card, and the
store is written only after that verdict. The model never writes the store by
itself and never claims it happened until the PC says so. A manual add in
Settings is the owner's own direct act, so it is immediate (tightening), with
an audit line. REMOVING an entry is loosening, so it always raises ONE card
whichever app asks.

WHAT THIS MODULE NEVER DOES

  * No network, no model, no token, and no file content in a sentence, an
    audit line or a job record: audit lines carry kinds, targets and outcomes.
  * It never reads a protected file to answer "is it protected": matching is
    on paths only.
  * It adds no second permission mechanism: ``protect_item`` /
    ``unprotect_item`` are ordinary ``jarvis_gate.check()`` actions with a
    shipped tier of "ask" in both copies of ``jarvis-framework.toml``. The gate
    has no ``_RISK`` row for them yet (a drop-in module cannot add one; risk
    rows are written by patches), so the gate forces them to "ask" and shows
    its generic worst-case warning - the safe side. A follow-up patch can
    classify them; that is named in the docs section and in the lane report.

ENFORCEMENT - WHERE THE CHECK IS CALLED (the module itself does not enforce;
every caller does, before it acts). Each point has its own test in
``backend/test_protection.py``:

  1. ``jarvis_documents.allowed_path`` (the folders allow-list door) and its
     ``find`` / ``search`` / ``read`` / import answers.
  2. ``jarvis_agent``'s ``file_read`` tool and ``my_files`` read preflight
     (before any card, for a blocked path).
  3. ``jarvis_note_capture.plan`` (the daily-note write) and its ``run``.
  4. ``jarvis_notes.snapshot_vault_before_write`` (the vault's guarded write
     door) and its vault search.
  5. ``jarvis_attached_file.read`` - a PC path can never be attached as the
     victim (attachments are bytes); if an attachment ever carries a ``path``
     it is checked too.
  6. ``jarvis_file_guardian._write_file`` (every guardian write, including a
     version restore) and ``snapshot_before_write`` (a blocked file is not
     copied out either).
  7. ``jarvis_open.resolve`` (opening a program on the PC).
  8. ``jarvis_ui_control.jarvis_target_refusal`` (looking at or acting in one
     program's window).
  9. ``jarvis_screen.pause_reason`` and ``jarvis_screen_win.must_hide`` (screen
     capture and OCR: a blocked program's window is never in the picture).
  10. ``jarvis_schedule._path_problem`` (a reminder that opens a file).
  11. ``jarvis_pictures.save_picture`` / ``picture_path`` (a generated picture
      written into, or read from, a protected folder).

NAMED GAPS, WRITTEN DOWN RATHER THAN LEFT SILENT (v1):

  * ``shell_exec``, ``run_data_script`` and ``rea_investigate`` run programs or
    scripts that can read any file by themselves; there is no path to check
    before the run. Refused wholesale? That would break unrelated uses. They
    are named gaps: their own cards say what they will run, and a protected
    item is not guaranteed to be safe from them in v1.
  * ``jarvis_app_control`` acts in the PHONE's Android apps (package names),
    not in PC programs: a protected program is a PC executable, so there is no
    name to match. Named gap (different kind of target).
  * ``jarvis_browser_control`` drives its own bundled Playwright Chromium, not
    the owner's installed browser; there is no link between a protected
    executable and that bundled one. Named gap.
  * ``jarvis_media`` (pause / next / now-playing) uses Windows' GLOBAL media
    session: whatever program is playing, including a protected one. Named gap.
  * A full-screen screen capture can include a blocked program's window when
    that program's window cannot be identified by ``jarvis_front``; identified
    windows are masked (point 9), unidentifiable ones are a named gap.
  * Backup/restore of the BACKEND folder and model installs write inside
    Jarvis's own folders, not the owner's listed folders; if an owner protects
    such a path, the File Guardian restore point (6) still covers the restore
    path, and the rest is a named gap.
  * The separate Obsidian notes-editor lane walks the vault itself; when it
    merges it must call this module's ``path_refusal`` too (it already calls
    ``jarvis_notes.snapshot_vault_before_write`` before a write). Owed.

Standard library only. No network, no subprocess, no second permission
mechanism.
"""
from __future__ import annotations

import json
import os
import secrets
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

# ---------------------------------------------------------------------------
#   The contract's constants
# ---------------------------------------------------------------------------

#: The two gate actions. Their tier is the shipped "ask" line in BOTH copies of
#: jarvis-framework.toml; the gate forces "ask" for an unclassified action even
#: if that line were removed.
ACTION_PROTECT = "protect_item"
ACTION_UNPROTECT = "unprotect_item"

KINDS = ("folder", "file", "program")
MODES = ("blocked", "readonly")

MODE_WORDS = {
    "blocked": "Blocked - no access",
    "readonly": "Read-only",
}

STORE_NAME = "protected-items.json"
STORE_VERSION = 1

#: Where the routes live.
PATH = "/api/protection"
ADD_ROUTE = "/api/protection/add"
REMOVE_ROUTE = "/api/protection/remove"
PROPOSE_ROUTE = "/api/protection/propose"
GET_PATHS = (PATH, PROPOSE_ROUTE)
POST_PATHS = (ADD_ROUTE, REMOVE_ROUTE, PROPOSE_ROUTE)

#: Bounds. The list is the owner's own, so the cap is a sanity bound, not a
#: security boundary; the waiting/job caps keep a long-lived backend small.
MAX_ITEMS = 500
MAX_TARGET_CHARS = 1000
MAX_WAITING = 4
MAX_JOBS = 50
DEFAULT_WAIT_S = 1.5

#: The sentence the list route carries about changes - one place both apps read.
CHANGE_CARD = ("Removing protection raises one approval card; adding in Settings "
               "is immediate; asking in chat raises one card.")

#: The one sentence a refused request gets when it did not come from this PC.
PC_ONLY = ("This can only be set up on your PC: open Jarvis's Settings on the PC "
           "and use \"Protected from Jarvis\".")

_lock = threading.Lock()
_jobs: dict = {}            # id -> public job record

# ---------------------------------------------------------------------------
#   Small shared helpers
# ---------------------------------------------------------------------------


def _audit(what: str, detail: dict) -> None:
    """One audit line, never carrying a file's contents."""
    try:
        import jarvis_framework
        jarvis_framework.audit_log("protection." + what, detail)
    except Exception:                                       # noqa: BLE001
        pass


def _config_dir() -> Path:
    try:
        import jarvis_framework as fw
        got = getattr(fw, "CONFIG_DIR", None)
        if got:
            return Path(got)
    except Exception:                                       # noqa: BLE001
        pass
    return Path(os.environ.get("OPENJARVIS_CONFIG_DIR") or Path.home() / ".openjarvis")


def store_path() -> Path:
    """The JSON file this list lives in. ``JARVIS_PROTECTION_STORE`` overrides
    it for the suite; on the owner's PC it sits beside the other settings."""
    override = os.environ.get("JARVIS_PROTECTION_STORE")
    if override:
        return Path(override)
    return _config_dir() / STORE_NAME


def _now_text() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _clean_target(kind: str, target) -> str:
    text = str(target or "").strip()
    if not text:
        return ""
    if "\x00" in text:
        return ""
    return text[:MAX_TARGET_CHARS]


def normal_path(path) -> str:
    """One comparable form of a Windows path: separators normalised, ``..``
    collapsed, case folded (Windows is case-insensitive). Links are resolved by
    the caller when it can; this is the string form used for the same-path
    comparison of a target that no longer exists."""
    text = str(path or "").strip()
    if not text:
        return ""
    text = text.replace("\x00", "")
    try:
        text = os.path.normpath(text)
    except Exception:                                       # noqa: BLE001
        pass
    return os.path.normcase(text)


def normal_program(name) -> str:
    """One comparable form of a program: its bare executable name, lowercased."""
    text = str(name or "").strip().strip('"')
    if not text:
        return ""
    base = os.path.basename(text.replace("/", "\\"))
    return base.lower()


def _real(text: str) -> str:
    try:
        return os.path.realpath(str(text))
    except Exception:                                       # noqa: BLE001
        return str(text)


def _same_or_inside(candidate_real: str, target_real: str) -> bool:
    """True when the candidate IS the target folder or is inside it, after both
    are resolved and folded. Uses commonpath so ``C:\\Taxes2`` is not inside
    ``C:\\Taxes`` (a plain startswith would say it is)."""
    c = normal_path(candidate_real)
    t = normal_path(target_real).rstrip("\\")
    if not c or not t:
        return False
    if c == t:
        return True
    try:
        return os.path.commonpath([c, t]) == t
    except (ValueError, AttributeError):
        return c.startswith(t + "\\")


# ---------------------------------------------------------------------------
#   The store - readable, versioned, and EMPTY AND SAFE when damaged
# ---------------------------------------------------------------------------


def _valid_item(raw) -> dict:
    if not isinstance(raw, dict):
        return {}
    kind = str(raw.get("kind") or "").strip().lower()
    mode = str(raw.get("mode") or "").strip().lower()
    target = raw.get("target")
    if kind not in KINDS or mode not in MODES:
        return {}
    if not isinstance(target, str) or not target.strip():
        return {}
    item = {
        "id": str(raw.get("id") or "").strip() or "prot_" + secrets.token_hex(4),
        "kind": kind,
        "target": target.strip(),
        "mode": mode,
        "added": str(raw.get("added") or "").strip() or _now_text(),
        "added_by": str(raw.get("added_by") or "owner").strip() or "owner",
    }
    return item


def load() -> dict:
    """The store as a dict. A missing, damaged or wrongly shaped file is EMPTY
    and safe: no crash, no accidental protection, and never "protect
    everything" - that is the contract's rule, not an accident."""
    path = store_path()
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except Exception:                                       # noqa: BLE001
        return {"version": STORE_VERSION, "items": []}
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return {"version": STORE_VERSION, "items": []}
    clean = []
    for entry in items[:MAX_ITEMS]:
        item = _valid_item(entry)
        if item:
            clean.append(item)
    return {"version": STORE_VERSION, "items": clean}


def items() -> list:
    """The list, as stored, without reading any protected file."""
    return list(load()["items"])


def save(new_items: list) -> None:
    """Write the list atomically, human-readable, beside the other settings."""
    path = store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": STORE_VERSION,
               "items": [dict(i) for i in new_items[:MAX_ITEMS]]}
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=1, sort_keys=False) + "\n",
                   encoding="utf-8")
    os.replace(str(tmp), str(path))


def public_item(item: dict) -> dict:
    return {k: item.get(k) for k in
            ("id", "kind", "target", "mode", "added", "added_by")}


# ---------------------------------------------------------------------------
#   Matching - the one central decision
# ---------------------------------------------------------------------------


def matching_path_item(path) -> dict:
    """The entry that covers this path, or {} - a folder entry covers its whole
    subtree (links resolved first), a file entry covers that file."""
    candidate = _real(str(path or ""))
    if not candidate:
        return {}
    for item in items():
        if item.get("kind") == "folder":
            if _same_or_inside(candidate, _real(item["target"])):
                return item
        elif item.get("kind") == "file":
            if normal_path(candidate) == normal_path(_real(item["target"])):
                return item
    return {}


def matching_program_item(name) -> dict:
    """The entry that covers this program, or {} - by bare executable name."""
    wanted = normal_program(name)
    if not wanted:
        return {}
    for item in items():
        if item.get("kind") == "program" and normal_program(item["target"]) == wanted:
            return item
    return {}


def _sentence(item: dict, what: str) -> str:
    mode = item.get("mode")
    if mode == "blocked":
        return (f"{item.get('target')} is on your Protected from Jarvis list as "
                f"{MODE_WORDS['blocked']}, so Jarvis will not {what}.")
    return (f"{item.get('target')} is on your Protected from Jarvis list as "
            f"{MODE_WORDS['readonly']}, so Jarvis may not {what}.")


def path_refusal(path, *, write: bool = False, what: str = "") -> str:
    """The plain sentence refusing this path, or "" when it is allowed.

    ``write`` asks the WRITE question: blocked refuses reads and writes,
    readonly refuses writes only. The caller passes ``what`` for its own action
    ("read it", "change it", "open it") so the sentence names what was refused.
    """
    item = matching_path_item(path)
    if not item:
        return ""
    if item.get("mode") == "blocked" or (write and item.get("mode") == "readonly"):
        return _sentence(item, what or ("change it" if write else "read it"))
    return ""


def program_refusal(name, *, act: bool = False, what: str = "") -> str:
    """The plain sentence refusing this program, or "" when it is allowed.

    ``act=False`` asks the SEE/READ question: only a blocked program is
    refused. ``act=True`` asks the ACT question: a read-only program is
    refused too ("see it, never act").
    """
    item = matching_program_item(name)
    if not item:
        return ""
    if item.get("mode") == "blocked" or (act and item.get("mode") == "readonly"):
        default = "act in it" if act else "look at it"
        return _sentence(item, what or default)
    return ""


def blocked_path(path) -> bool:
    item = matching_path_item(path)
    return bool(item and item.get("mode") == "blocked")


def protected_path(path) -> bool:
    return bool(matching_path_item(path))


def blocked_programs() -> list:
    return [i for i in items() if i.get("kind") == "program"
            and i.get("mode") == "blocked"]


def has_blocked_programs() -> bool:
    return bool(blocked_programs())


# ---------------------------------------------------------------------------
#   Validation - before any card, and before anything is stored
# ---------------------------------------------------------------------------


class Refused(ValueError):
    """A plain-sentence refusal a caller turns into its own 400/409 answer."""


class Duplicate(Refused):
    """The target is already protected; `.item` is the existing entry."""

    def __init__(self, message: str, item: dict):
        super().__init__(message)
        self.item = item


def _kind_mode(kind, mode) -> tuple:
    k = str(kind or "").strip().lower()
    m = str(mode or "").strip().lower()
    if k not in KINDS:
        raise Refused("Choose what to protect: a folder, a file or a program.")
    if m not in MODES:
        raise Refused("Choose how to protect it: Blocked (no access) or Read-only.")
    return k, m


def _running_program_names() -> set:
    """The bare executable names currently running on this PC, lowercased.

    Best effort and never a security boundary: it exists so a program entry
    names a program that is really there. On a platform that cannot answer
    (the suite, CI) it returns an empty set, and the caller then accepts a
    plain ``.exe`` name - the desktop lane picks from the running programs
    itself, so a wrong name is caught there."""
    try:
        import ctypes
        from ctypes import wintypes
    except Exception:                                       # noqa: BLE001
        return set()
    try:
        TH32CS_SNAPPROCESS = 0x00000002
        INVALID = ctypes.c_void_p(-1).value

        class PROCESSENTRY32(ctypes.Structure):
            _fields_ = [("dwSize", wintypes.DWORD),
                        ("cntUsage", wintypes.DWORD),
                        ("th32ProcessID", wintypes.DWORD),
                        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
                        ("th32ModuleID", wintypes.DWORD),
                        ("cntThreads", wintypes.DWORD),
                        ("th32ParentProcessID", wintypes.DWORD),
                        ("pcPriClassBase", ctypes.c_long),
                        ("dwFlags", wintypes.DWORD),
                        ("szExeFile", ctypes.c_char * 260)]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        snap = kernel.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if snap == INVALID or snap is None:
            return set()
        entry = PROCESSENTRY32()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
        names = set()
        try:
            ok = kernel.Process32First(snap, ctypes.byref(entry))
            while ok:
                raw = bytes(entry.szExeFile).split(b"\x00", 1)[0]
                if raw:
                    names.add(raw.decode("mbcs", "replace").lower())
                ok = kernel.Process32Next(snap, ctypes.byref(entry))
        finally:
            try:
                kernel.CloseHandle(snap)
            except Exception:                               # noqa: BLE001
                pass
        return names
    except Exception:                                       # noqa: BLE001
        return set()


def validate_request(kind, target, mode, *, known_programs=None) -> tuple:
    """`(normalised_target, "")` for a storable entry, or `("", why)`.

    Pure apart from the existence checks: it reads the filesystem for a
    folder/file (so a typo is refused before any card) and, for a program,
    compares the bare name against `known_programs` when that can be read.
    Never writes anything.
    """
    try:
        k, m = _kind_mode(kind, mode)
    except Refused as exc:
        return "", str(exc)
    text = _clean_target(k, target)
    if not text:
        return "", "Name the folder, file or program to protect."
    if k in ("folder", "file"):
        if not os.path.isabs(text):
            return "", "Give the whole path, starting with the drive, like C:\\Users\\you\\Documents."
        real = _real(text)
        if k == "folder":
            if not os.path.isdir(real):
                return "", f"There is no folder at {text} on this PC."
        else:
            if not os.path.isfile(real):
                return "", f"There is no file at {text} on this PC."
        return normal_path(real), ""
    name = normal_program(text)
    if not name:
        return "", "Name the program by its own executable name, like notepad.exe."
    if not name.endswith(".exe"):
        return "", "A program is named by its executable, like notepad.exe."
    if known_programs:
        if name not in {normal_program(p) for p in known_programs}:
            return "", (f"{name} is not running on this PC now, so there is no "
                        "program by that name to protect.")
    return name, ""


def find_item(item_id) -> dict:
    wanted = str(item_id or "").strip()
    if not wanted:
        return {}
    for item in items():
        if item.get("id") == wanted:
            return item
    return {}


def _duplicate(kind: str, target: str) -> dict:
    for item in items():
        if item.get("kind") != kind:
            continue
        if kind == "program":
            if normal_program(item["target"]) == normal_program(target):
                return item
        else:
            if normal_path(_real(item["target"])) == normal_path(_real(target)):
                return item
    return {}


def add_item(kind, target, mode, *, known_programs=None, added_by="owner") -> dict:
    """Store one entry. Raises `Refused`/`Duplicate` before anything changes."""
    norm, why = validate_request(kind, target, mode, known_programs=known_programs)
    if why:
        raise Refused(why)
    k, m = _kind_mode(kind, mode)
    with _lock:
        current = items()
        other = _duplicate(k, norm)
        if other:
            raise Duplicate(_duplicate_sentence(other), other)
        if len(current) >= MAX_ITEMS:
            raise Refused(f"The protected list already holds {MAX_ITEMS} items, "
                          "which is the most this list keeps.")
        item = {"id": "prot_" + secrets.token_hex(4), "kind": k,
                "target": norm, "mode": m, "added": _now_text(),
                "added_by": str(added_by or "owner")}
        save(current + [item])
    _audit("added", {"id": item["id"], "kind": k, "target": norm, "mode": m,
                     "by": item["added_by"]})
    return item


def _duplicate_sentence(item: dict) -> str:
    return (f"{item.get('target')} is already on your Protected from Jarvis list "
            f"({MODE_WORDS.get(item.get('mode'), item.get('mode'))}).")


def remove_item(item_id) -> dict:
    """Remove one entry. Returns the removed entry, or {} when the id is not
    in the list. The caller is responsible for the approval card."""
    item = find_item(item_id)
    if not item:
        return {}
    with _lock:
        kept = [i for i in items() if i.get("id") != item.get("id")]
        save(kept)
    _audit("removed", {"id": item.get("id"), "kind": item.get("kind"),
                       "target": item.get("target")})
    return item


# ---------------------------------------------------------------------------
#   Words shared by the card, the routes and the model tool
# ---------------------------------------------------------------------------


def mode_words(mode) -> str:
    return MODE_WORDS.get(str(mode or "").strip().lower(), str(mode or ""))


def card_prompt(kind: str, target: str, mode: str, *, removal: bool = False) -> str:
    """The card's one line, naming the target and the mode in plain language."""
    if removal:
        return (f"stop protecting {target} from Jarvis "
                f"(it is on the list as {mode_words(mode)}; after this Jarvis may "
                f"touch it again)")
    return f"protect {target} from Jarvis ({mode_words(mode)})"


def card_detail(kind: str, target: str, mode: str, *, item_id: str = "") -> dict:
    """The card's detail. Kinds, target and mode ONLY - never a file's bytes."""
    detail = {"kind": kind, "target": target, "mode": mode}
    if item_id:
        detail["id"] = item_id
    return detail


def describe_for_tool(kind: str, target: str, mode: str) -> str:
    return ("Protect this from Jarvis: " + str(target) + " as " +
            mode_words(mode) + ". Nothing is stored until the owner approves "
            "the card.")


def tool_add(kind, target, mode) -> dict:
    """Called by the model tool AFTER its gate card was approved."""
    item = add_item(kind, target, mode, added_by="chat")
    return {"ok": True, "item": public_item(item),
            "said": (f"Done - {item['target']} is on your Protected from Jarvis "
                     f"list as {mode_words(item['mode'])}.")}


# ---------------------------------------------------------------------------
#   The routes
# ---------------------------------------------------------------------------


def _error(code: int, message: str, **extra) -> tuple:
    body = {"ok": False, "error": message}
    body.update(extra)
    return code, body


def handle_get() -> tuple:
    """GET /api/protection - the list, in the PC's own words."""
    got = items()
    return 200, {"ok": True, "count": len(got),
                 "items": [public_item(i) for i in got],
                 "modes": list(MODES), "change_card": CHANGE_CARD}


def handle_add(body, *, from_this_pc: bool, known_programs=None) -> tuple:
    """POST /api/protection/add - the desktop Settings' own act. No card."""
    if not from_this_pc:
        return _error(403, PC_ONLY, pc_only=True)
    if not isinstance(body, dict):
        return _error(400, "Send kind, target and mode as a JSON object.")
    try:
        item = add_item(body.get("kind"), body.get("target"), body.get("mode"),
                        known_programs=known_programs, added_by="owner")
    except Duplicate as exc:
        return _error(409, str(exc), item=public_item(exc.item))
    except Refused as exc:
        return _error(400, str(exc))
    return 200, {"ok": True, "item": public_item(item),
                 "message": (f"Protecting {item['target']} from Jarvis "
                             f"({mode_words(item['mode'])}).")}


def _job_finish(job_id: str, **fields) -> None:
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(fields)
            _jobs[job_id]["updated"] = time.time()


def _job_make(what: str, detail: dict, prompt: str, action: str, *,
              gate_check, wait_s: float, on_approved) -> str:
    """One job, one card, one worker thread - the notes-edit shape."""
    with _lock:
        waiting = sum(1 for j in _jobs.values() if j.get("state") == "waiting")
        if waiting >= MAX_WAITING:
            raise Refused(f"{MAX_WAITING} protection changes are already waiting "
                          "for a card - answer those first, then ask again.")
        job_id = "prot_" + secrets.token_hex(8)
        _jobs[job_id] = {"id": job_id, "what": what, "state": "waiting",
                         "kind": detail.get("kind"), "target": detail.get("target"),
                         "mode": detail.get("mode"),
                         "message": "Waiting for your approval card.",
                         "created": time.time(), "updated": time.time()}
        while len(_jobs) > MAX_JOBS:
            oldest = min(_jobs, key=lambda k: _jobs[k]["created"])
            _jobs.pop(oldest, None)

    def worker() -> None:
        try:
            verdict = gate_check(action, detail, prompt)
            if not getattr(verdict, "allowed", False):
                outcome = str(getattr(verdict, "outcome", "refused") or "refused")
                state = "denied" if outcome in ("denied", "timed_out") else "failed"
                _job_finish(job_id, state=state,
                            message=("Nothing was changed: the approval card was "
                                     f"{outcome}."))
                _audit("refused", {"job": job_id, "action": action,
                                   "outcome": outcome})
                return
            added = on_approved()
            _job_finish(job_id, state="removed" if what == "remove" else "added",
                        item=public_item(added) if added else None,
                        message=("Done - the entry was removed from your protected "
                                 "list." if what == "remove" else
                                 f"Done - {detail.get('target')} is on your "
                                 f"Protected from Jarvis list as "
                                 f"{mode_words(detail.get('mode'))}."))
        except Duplicate as exc:
            _job_finish(job_id, state="failed", message=str(exc),
                        item=public_item(exc.item))
            _audit("failed", {"job": job_id, "why": "duplicate"})
        except Refused as exc:
            _job_finish(job_id, state="failed", message=str(exc))
            _audit("failed", {"job": job_id, "why": "refused"})
        except Exception as exc:                            # noqa: BLE001
            _job_finish(job_id, state="failed",
                        message=f"The change failed ({type(exc).__name__}), so "
                                "nothing was changed.")
            _audit("failed", {"job": job_id, "why": type(exc).__name__})

    thread = threading.Thread(target=worker, name="jarvis-protection", daemon=True)
    thread.start()
    thread.join(max(0.0, float(wait_s)))
    return job_id


def _gate_check_fallback(action: str, detail: dict, prompt: str):
    """jarvis_gate.check(), failing CLOSED on any error (the project's shape)."""
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


def handle_remove(body, *, gate_check=None, wait_s: float = DEFAULT_WAIT_S) -> tuple:
    """POST /api/protection/remove - ONE card (action unprotect_item)."""
    if not isinstance(body, dict):
        return _error(400, "Send the id of the protected item to remove.")
    item = find_item(body.get("id"))
    if not item:
        return _error(404, "There is no protected item with that id on this PC.")
    detail = card_detail(item["kind"], item["target"], item["mode"],
                         item_id=item["id"])
    try:
        job_id = _job_make("remove", detail,
                           card_prompt(item["kind"], item["target"], item["mode"],
                                       removal=True),
                           ACTION_UNPROTECT, gate_check=gate_check or _gate_check_fallback,
                           wait_s=wait_s,
                           on_approved=lambda: remove_item(item["id"]))
    except Refused as exc:
        return _error(429, str(exc))
    with _lock:
        state = dict(_jobs.get(job_id) or {})
    if state.get("state") == "refused":
        return _error(429, state.get("message", ""))
    return 202, {"ok": True, "state": "waiting", "id": job_id}


def handle_propose(body, *, gate_check=None, wait_s: float = DEFAULT_WAIT_S,
                   known_programs=None) -> tuple:
    """POST /api/protection/propose - the chat path, ONE card (protect_item)."""
    if not isinstance(body, dict):
        return _error(400, "Send kind, target and mode as a JSON object.")
    try:
        norm, why = validate_request(body.get("kind"), body.get("target"),
                                     body.get("mode"),
                                     known_programs=known_programs)
    except Exception as exc:                                # noqa: BLE001
        return _error(400, f"That could not be read ({type(exc).__name__}).")
    if why:
        return _error(400, why)
    kind, mode = _kind_mode(body.get("kind"), body.get("mode"))
    other = _duplicate(kind, norm)
    if other:
        return _error(409, _duplicate_sentence(other), item=public_item(other))
    detail = card_detail(kind, norm, mode)
    try:
        job_id = _job_make("propose", detail,
                           card_prompt(kind, norm, mode), ACTION_PROTECT,
                           gate_check=gate_check or _gate_check_fallback,
                           wait_s=wait_s,
                           on_approved=lambda: add_item(kind, norm, mode,
                                                        known_programs=None,
                                                        added_by="chat"))
    except Refused as exc:
        return _error(429, str(exc))
    return 202, {"ok": True, "state": "waiting", "id": job_id}


def propose_status(job_id) -> tuple:
    """GET /api/protection/propose?id= - waiting / added / denied / failed."""
    jid = str(job_id or "").strip()
    if not jid:
        return _error(400, "Need the id of a protection request.")
    with _lock:
        job = dict(_jobs.get(jid) or {})
    if not job or job.get("what") != "propose":
        return _error(404, "There is no protection request with that id on this PC.")
    out = {"ok": job.get("state") in ("waiting", "added"),
           "state": job.get("state"), "item": job.get("item"),
           "message": job.get("message") or ""}
    if job.get("state") == "waiting":
        out["id"] = jid
    return 200, out


def handle_propose_status(query: str = "") -> tuple:
    try:
        jid = (parse_qs(str(query or "").lstrip("?"))
               .get("id") or [""])[0]
    except Exception:                                       # noqa: BLE001
        jid = ""
    return propose_status(jid)


# ---------------------------------------------------------------------------
#   install(): the drop-in loader's convention, exactly like receipts / vault /
#   notes-edit. `plugins/ready/protected-items/plugin.json` names this module
#   and jarvis_plugins.py makes the call a patch would have made.
# ---------------------------------------------------------------------------


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap the core's Handler with the five routes below.

    After the server's own origin and token checks; every other request goes
    straight to the original.
    """
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(get0, "_jarvis_protection", False):
        return "  protection  Protected from Jarvis (already on)"

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
            if route == PATH:
                code, out = handle_get()
            else:
                code, out = handle_propose_status(parts.query)
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
            if route == ADD_ROUTE:
                code, out = handle_add(body, from_this_pc=_from_this_pc(self))
            elif route == REMOVE_ROUTE:
                code, out = handle_remove(body)
            else:
                code, out = handle_propose(body)
        except Exception as exc:                            # noqa: BLE001
            code, out = 503, {"ok": False, "error": type(exc).__name__}
        return self._send(code, out)

    def _from_this_pc(handler) -> bool:
        try:
            import jarvis_owner_check
            peer = (getattr(handler, "client_address", None) or ("",))[0]
            try:
                local = handler.connection.getsockname()[0]
            except Exception:                               # noqa: BLE001
                local = None
            return bool(jarvis_owner_check.from_this_pc(peer, local))
        except Exception:                                   # noqa: BLE001
            return False

    do_GET._jarvis_protection = True
    do_POST._jarvis_protection = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    return ("  protection  Protected from Jarvis: the owner's list of folders, "
            "files and programs Jarvis may not touch")


def _reset_for_tests() -> None:
    """Clear the job table between tests; nothing else uses this."""
    with _lock:
        _jobs.clear()
