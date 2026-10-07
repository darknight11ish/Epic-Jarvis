"""jarvis_documents.py - "Folders Jarvis may look in": finding files by name,
searching inside notes and text files, reading PDFs, Word, Excel and
PowerPoint files one part at a time, and bringing in a Notion export.

NEW MODULE, shipped whole. documents.patch adds one call at start-up,
`install(Handler, ...)`, which answers the four routes below (the same shape
as jarvis_stop_all.py). The model reaches it through ONE tool in
jarvis_agent.py, `my_files`. docs/JARVIS-API.md section 35; backend/README.md
"Folders Jarvis may look in".

THE OWNER'S DECISIONS (CLAUDE.md)
  * 2026-09-26, cutting-edge research, "Documents & email": "asking about
    PDFs and Word files".
  * 2026-09-26, "Bring in my Notion export": the export (Markdown pages and
    CSV tables) goes into a folder Jarvis searches, then the owner can ask
    about it. Imported notes are outside text: they are never learned as
    facts, and every note Jarvis writes back after reading them asks first,
    as for any note.
  * The feasibility audit (docs/FEASIBILITY-AUDIT-2026-09-26.md, section 4,
    guardrail 1): ONE "Folders Jarvis may look in" list, PC only, empty by
    default - for file names (I39), documents (I40) and the Notion import.

THE LIST - empty by default, kept in folders.json in the Jarvis settings folder
  * Adding a folder: only from this PC (the backend refuses any other device,
    jarvis_owner_check.from_this_pc), and ONE approval card (action
    `change_own_config`, tier "ask" only - the shape of every setting that
    lets Jarvis see more). The card names the folder in full.
  * Removing one: at once, no card, from either app - it only lets Jarvis
    see less. It also withdraws a waiting card for the same folder.
  * Refused outright: a drive's top (C:\\), your whole user folder, Windows
    and Program Files, AppData, and any place file_read refuses (keys, saved
    passwords, browser data, Jarvis's own data - jarvis_agent._protected_path,
    the ONE refusal list, never a copy of it).

WHAT THE MODEL MAY DO - the `my_files` tool, reads only
  find    file NAMES inside the listed folders that have every word asked.
  search  words inside the notes and text files there (.md, .txt, .csv).
  read    ONE part of ONE file: its text, split at its headings into parts of
          at most PART_TOKENS, with the list of parts. PDF, Word (.docx),
          Excel (.xlsx) and PowerPoint (.pptx) are turned into text by
          MarkItDown; .md, .txt and .csv are read as they are.
Every path it touches must, after links are followed, be inside a listed
folder and not in a protected place. It never writes, moves or deletes
anything, never opens a web address, and runs no program but the converter.
Hidden folders (a name starting with ".") are never entered.

It is a read of the owner's own files on this PC, so it goes through the
gate as `read_files_readonly` - the same action as file_read, the same line
on "What asks first". What it returns is OUTSIDE TEXT (jarvis_agent's
_TurnWatch.took_in): the turn and the chat count as having read outside
text, so a note written afterwards asks first, a web search afterwards asks
first, and nothing in it is ever learned as a fact (learning takes only the
owner's own typed or said words). The model reading it is always the one on
this PC: tools run only on the local lane.

THE CONTEXT BUDGET (hardware reviewer: about 8,000 tokens on the 8 GB card,
with about 3,450 free for a turn's reading)
  * A part is at most PART_TOKENS (1,200 by jarvis_agent's pessimistic 3
    characters a token). A big document is SPLIT at its headings, never
    refused and never cut short: the rest is there as further parts.
  * One answer reads at most PARTS_PER_TURN parts (jarvis_agent enforces it).
  * find returns at most FIND_MAX names; search at most SEARCH_MAX, each with
    a short snippet.

THE CONVERTER - MarkItDown, the document parts only, in a child process
  * Installed as `markitdown[pdf,docx,xlsx,pptx]` - NEVER `[all]`: its audio
    converter sends sound to Google and its YouTube converter fetches from
    YouTube (rule 1). backend/requirements.txt pins it; test_documents.py
    fails if the audio, YouTube or "all" extras are ever named there.
  * Only four converters are switched on (PDF, Word, Excel, PowerPoint);
    MarkItDown's own list - web pages, YouTube, zip files inside zip files,
    audio, Outlook - is not (enable_builtins=False).
  * A separate program: `python -I` (no user folder, no PYTHONPATH, not the
    document's folder on the import path) with jarvis_child_env's allowlist
    (no token, no password, no key), a time limit (CONVERT_SECONDS) and a
    size limit on the file going in (MAX_DOC_BYTES) and the text coming back.
    A crafted PDF that tries something runs as that child, with nothing to
    steal from its environment and a clock on it.
  * The text is kept in memory only, for the last few files (so reading
    part 2 does not convert again) - never written to disk.
  * A scanned letter or bill has no text layer: the answer says "no text
    was found", plainly, rather than guessing.

THE NOTION IMPORT - an explicit owner action on the PC, never the model
POST /api/folders/import {"zip": "<the .zip Notion made>", "into": "<a
listed folder>"}: unzipped into a NEW folder "Notion export <date>" inside
it, never over anything. Safe unzipping:
  * every name is checked: no absolute path, no drive letter, no "..", no
    link, Windows' reserved names and characters replaced;
  * only notes, tables, documents and pictures are written
    (IMPORT_KINDS); anything else - a program, a script, a shortcut, a web
    page - is skipped and counted, and nothing from the zip is ever run;
  * at most IMPORT_MAX_FILES files and IMPORT_MAX_BYTES in all, counted as
    they are written (not as the zip claims), one file at most
    IMPORT_MAX_ONE; one level of zip inside the zip (Notion splits a big
    workspace into "Part-1.zip" ...), no deeper;
  * written to a hidden folder first and moved into place in one step, so a
    refused import leaves nothing behind.
No card: the owner picked the file and the folder on the PC, the folder is
already on the list (a card was approved for it), and nothing leaves the
PC. Notion's long ids ("Trip plan 1a2b...32 hex.md") stay in the file names
so the pages' links to each other keep working; find and search show the
names without them.

Standard library only, apart from MarkItDown in the child process.
Nothing here opens a socket.
"""
from __future__ import annotations

import json
import ntpath
import os
import re
import shutil
import stat
import subprocess
import sys
import threading
import time
import uuid
import zipfile
from collections import OrderedDict
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import parse_qs, urlsplit

try:
    import jarvis_framework as fw
except Exception:  # pragma: no cover - shipped beside it on the PC
    fw = None  # type: ignore

PATH = "/api/folders"
ADD_ROUTE = "/api/folders/add"
REMOVE_ROUTE = "/api/folders/remove"
IMPORT_ROUTE = "/api/folders/import"

# --------------------------------------------------------------------------
#   The words both apps show (jarvis-desktop/src/folders.js,
#   jarvis-client net/Folders.kt - tests check they match)
# --------------------------------------------------------------------------

TITLE = "Folders Jarvis may look in"
DETAIL = ("Jarvis can find your files by name, search inside your notes and text files, and "
          "read PDF, Word, Excel and PowerPoint files - only in the folders listed here. "
          "None are listed at first. Adding a folder is done on the PC and takes an "
          "approval card; removing one is instant, from either app. What Jarvis reads "
          "there is outside text: it is never saved as a fact about you, and a note Jarvis "
          "writes after reading it asks you first.")
EMPTY = "No folders yet, so Jarvis does not look in any of your files."
PHONE_ADD = "Folders are added on the PC: Settings, Folders Jarvis may look in."
MISSING = ("Your PC's Jarvis cannot look in folders yet - run apply-patches.ps1 on the PC.")
WAITING = "Waiting for your yes on the approval card."
NOTION_TITLE = "Bring in a Notion export"
NOTION_DETAIL = ("In Notion: Settings, Export all workspace content, as Markdown & CSV. Then "
                 "pick the .zip it made and a folder from the list: Jarvis unzips it into a "
                 "new folder there and never runs anything from it. If that folder is synced "
                 "by OneDrive or a similar app, that app uploads the new files, as it does "
                 "anything you put there.")
REMOVE_LABEL = "Remove"
PC_ONLY = ("Folders are added on the PC only (Settings, Folders Jarvis may look in), with an "
           "approval card.")
CONVERTER_MISSING = ("Reading PDF, Word, Excel and PowerPoint files is off: MarkItDown is not "
                     "installed on the PC. Notes and text files can still be read.")
CONVERTER_READY = "PDF, Word, Excel and PowerPoint files can be read."

#: How the last card went, in words the apps show.
LAST_WORDS = {
    "added": "Added. Jarvis can look in that folder when you ask.",
    "denied": "You said no, so that folder was not added.",
    "timed_out": "Nobody answered the card in time, so that folder was not added.",
    "withdrawn": "You removed it before the card was answered, so it was not added.",
    "refused": "The card could not be answered, so that folder was not added.",
    "failed": "It was approved, but the list could not be saved, so that folder was not "
              "added.",
}

CARD_ACTION = "change_own_config"
GATE_ACTION = "read_files_readonly"
TOOL = "my_files"

MAX_FOLDERS = 20

# The tool's limits (see the module docstring: the context budget).
CHARS_PER_TOKEN = 3                  # jarvis_agent.estimate_tokens' count
PART_TOKENS = 1200
PART_CHARS = PART_TOKENS * CHARS_PER_TOKEN
PARTS_PER_TURN = 2
MAX_PARTS = 400
CONTENTS_SHOWN = 40
FIND_MAX = 20
SEARCH_MAX = 8
SNIPPET_CHARS = 240
WALK_MAX_ENTRIES = 100_000
WALK_MAX_SECONDS = 4.0
SEARCH_MAX_FILES = 5000
SEARCH_FILE_BYTES = 256 * 1024
MAX_TEXT_BYTES = 4 * 1024 * 1024     # a .md/.txt/.csv read whole, at most this much
MAX_DOC_BYTES = 50 * 1024 * 1024     # a PDF/Word/Excel/PowerPoint file going in
MAX_CONVERTED_CHARS = 4_000_000      # the text coming back
CONVERT_SECONDS = 120.0
CACHE_FILES = 4

TEXT_KINDS = {".md": "note", ".markdown": "note", ".txt": "text", ".csv": "table"}
DOC_KINDS = {".pdf": "PDF", ".docx": "Word", ".xlsx": "Excel", ".pptx": "PowerPoint"}
#: What a Notion import writes; everything else in the zip is skipped.
IMPORT_KINDS = frozenset(set(TEXT_KINDS) | set(DOC_KINDS) | {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".heic"})
IMPORT_MAX_FILES = 20_000
IMPORT_MAX_BYTES = 1024 * 1024 * 1024
IMPORT_MAX_ONE = 200 * 1024 * 1024
IMPORT_MAX_ZIP = 2 * 1024 * 1024 * 1024
IMPORT_NAME_CHARS = 150

#: Notion's ids in names: "Trip plan 1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d.md".
_NOTION_ID = re.compile(r"\s+[0-9a-f]{32}(?=(?:_all)?(?:\.[A-Za-z0-9]{1,8})?$)")

# --------------------------------------------------------------------------
#   Settings, the gate, the clock - replaceable, so the tests open nothing
# --------------------------------------------------------------------------


def _config_dir() -> Path:
    if fw is not None:
        try:
            return Path(fw.CONFIG_DIR)
        except Exception:
            pass
    env = os.environ.get("OPENJARVIS_CONFIG_DIR") or os.environ.get("JARVIS_CONFIG_DIR")
    if env:
        return Path(os.path.expanduser(env))
    return Path(os.path.expanduser("~")) / ".openjarvis"


def settings_path() -> Path:
    """folders.json in the Jarvis settings folder."""
    return _config_dir() / "folders.json"


def _tier(action: str) -> str:
    try:
        return str(fw.action_tier(action)) if fw is not None else "ask"
    except Exception:
        return "ask"


def _gate(action: str, detail: dict, prompt: str):
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def _spawn(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="jarvis-folders-card", daemon=True).start()


def _audit(event: str, detail: dict) -> None:
    # Counts and outcomes. Never a folder's path or a file's name.
    try:
        if fw is not None:
            fw.audit_log(event, detail)
    except Exception:
        pass


def _from_this_pc(peer, local) -> bool:
    try:
        import jarvis_owner_check
        return bool(jarvis_owner_check.from_this_pc(peer, local))
    except Exception:
        # Cannot tell: not this PC, so nothing is added (fail closed).
        return False


def _program_folder() -> str:
    """Jarvis's own program folder - where this file, jarvis_hud.py, and on
    some PCs the settings file and the logs sit."""
    return os.path.dirname(os.path.realpath(__file__))


def protected(path: str) -> bool:
    """file_read's refusal list (jarvis_agent._protected_path) - the ONE list -
    and, for the folders here, Jarvis's own program folder too (the owner's
    backend folder is inside Documents on their PC: "Documents\\Claude\\Open
    jarvis files\\Desktop program"). Without jarvis_agent.py, every path is
    refused rather than guessed."""
    try:
        real = os.path.realpath(os.path.expanduser(path))
        if _inside(_program_folder(), real):
            return True
        import jarvis_agent
        return bool(jarvis_agent._protected_path(path))
    except Exception:
        return True


# --------------------------------------------------------------------------
#   The list
# --------------------------------------------------------------------------

_S_LOCK = threading.RLock()
_DAMAGED = ("the list of folders is damaged, so Jarvis looks in none of them - add them "
            "again on the PC")


def _norm(path: str) -> str:
    """A folder as it is kept: the real place, links followed."""
    return os.path.realpath(os.path.expanduser(str(path)))


def _key(path: str) -> str:
    """For comparing two places: Windows does not care about case."""
    return os.path.normcase(_norm(path))


def _inside(root: str, path: str) -> bool:
    """True when `path` (already real) is `root` (already real) or under it."""
    try:
        return os.path.commonpath([os.path.normcase(root), os.path.normcase(path)]) \
            == os.path.normcase(root)
    except ValueError:      # different drives on Windows
        return False


def load() -> dict:
    """{"folders": [{"path", "added"}], "why": str}. No file: none (the
    default). Damaged: none, and `why` says so."""
    try:
        raw = settings_path().read_text(encoding="utf-8")
    except FileNotFoundError:
        return {"folders": [], "why": ""}
    except OSError as exc:
        return {"folders": [], "why": f"the list of folders could not be read "
                                      f"({type(exc).__name__}), so Jarvis looks in none"}
    try:
        doc = json.loads(raw)
        items = doc.get("folders") if isinstance(doc, dict) else None
        if not isinstance(items, list):
            raise ValueError
        out = []
        for it in items[:MAX_FOLDERS]:
            if not isinstance(it, dict) or not isinstance(it.get("path"), str):
                raise ValueError
            added = it.get("added")
            out.append({"path": it["path"],
                        "added": float(added) if isinstance(added, (int, float))
                        and not isinstance(added, bool) else 0.0})
    except Exception:
        return {"folders": [], "why": _DAMAGED}
    return {"folders": out, "why": ""}


def folders() -> list:
    """The listed folders' paths, as kept. What the tool looks in."""
    return [f["path"] for f in load()["folders"]]


def _save(items: list) -> None:
    with _S_LOCK:
        p = settings_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps({"folders": items, "changed": time.time()}, indent=1),
                       encoding="utf-8")
        os.replace(tmp, p)


#: Folder names that are Windows' or the programs', never the owner's own files.
_SYSTEM_FOLDERS = frozenset({"windows", "program files", "program files (x86)", "programdata",
                             "appdata", "$recycle.bin", "system volume information"})


def _too_broad(real: str) -> str:
    """"" when `real` may be listed, else why not (a sentence's end)."""
    low = real.replace("\\", "/").rstrip("/").lower()
    drive, rest = ntpath.splitdrive(real)
    if real in ("/", "") or (drive and rest.strip("\\/") == ""):
        return "that is the top of a drive - pick a folder inside it, like Documents"
    home = os.path.realpath(os.path.expanduser("~")).replace("\\", "/").rstrip("/").lower()
    if low == home:
        return "that is your whole user folder - pick a folder inside it, like Documents"
    if set(low.split("/")) & _SYSTEM_FOLDERS:
        return "that folder belongs to Windows or your programs, not to your own files"
    return ""


def check_folder(path) -> str:
    """The folder, as it would be kept, or ValueError with a sentence."""
    if not isinstance(path, str) or not path.strip():
        raise ValueError("say which folder, as its full path, like C:\\Users\\you\\Documents")
    raw = path.strip()
    if "\x00" in raw or len(raw) > 1000:
        raise ValueError("that is not a folder's path")
    if not (os.path.isabs(raw) or ntpath.isabs(raw)) or raw.startswith(("\\\\", "//")):
        raise ValueError("give the folder's full path on this PC, like "
                         "C:\\Users\\you\\Documents (not a network share)")
    real = _norm(raw)
    if not os.path.isdir(real):
        raise ValueError("there is no folder at that path on this PC")
    why = _too_broad(real)
    if why:
        raise ValueError(why)
    if protected(real) or protected(os.path.join(real, "x")):
        raise ValueError("Jarvis never looks there: that place holds keys, saved passwords, "
                         "browser data or Jarvis's own private data")
    return real


def view(*, here: bool = False, ready: Optional[bool] = None) -> dict:
    """GET /api/folders: the list, the words, whether this request may add
    (only one from this PC), a waiting card, how the last one went, and
    whether PDFs and Word files can be read."""
    st = load()
    with _P_LOCK:
        waiting = dict(_P_STATE["pending"]) or None
        last = dict(_P_STATE["last"]) or None
    shown = []
    for f in st["folders"]:
        # A Windows path on the PC; split on either slash, wherever this runs.
        name = re.split(r"[\\/]", f["path"].rstrip("\\/"))[-1]
        shown.append({"path": f["path"], "name": name or f["path"], "added": f["added"],
                      "exists": os.path.isdir(f["path"])})
    conv = converter_ready() if ready is None else ready
    return {
        "available": True, "title": TITLE, "detail": DETAIL, "folders": shown,
        "empty": EMPTY, "why": st["why"], "can_add": bool(here), "phone_add": PHONE_ADD,
        "waiting": {"path": waiting["path"]} if waiting else None,
        "waiting_words": WAITING if waiting else "",
        "last": last, "max": MAX_FOLDERS,
        "documents": {"ready": conv, "said": CONVERTER_READY if conv else CONVERTER_MISSING},
        "notion": {"title": NOTION_TITLE, "detail": NOTION_DETAIL, "can_import": bool(here)},
        "remove_label": REMOVE_LABEL,
    }


# --------------------------------------------------------------------------
#   Adding - this PC only, ONE card
# --------------------------------------------------------------------------

_P_LOCK = threading.Lock()
_P_STATE: dict = {"pending": {}, "withdrawn": set(), "last": {}, "latest": {}}
_P_SWITCH = threading.Lock()


def card(path: str) -> str:
    return "\n".join([
        "Let Jarvis look in this folder?",
        "",
        f"Folder: {path}",
        "",
        "From now on, when you ask, Jarvis can find files in this folder and the folders "
        "inside it by name, search inside its notes and text files, and read its PDF, Word, "
        "Excel and PowerPoint files - with the AI model on this PC. It reads only when you "
        "ask, one part of one file at a time. It never changes, moves or deletes anything "
        "there, and nothing is copied or sent anywhere.",
        "",
        "Places that hold keys, saved passwords or browser data stay closed even inside this "
        "folder, and so do hidden folders.",
        "",
        "What Jarvis reads there counts as outside text: it is never saved as a fact about "
        "you, and a note Jarvis writes after reading it asks you first.",
        "",
        "Removing the folder from the list is instant, from either app.",
        "",
        "If you did not just do this, say no.",
        "",
        "If you say no: nothing changes.",
    ])


def _person_said_yes(v) -> bool:
    if getattr(v, "allowed", False) is not True:
        return False
    outcome = getattr(v, "outcome", None)
    if outcome is not None:
        return outcome == "approved" and getattr(v, "tier", "ask") == "ask"
    return getattr(v, "tier", None) == "ask"


def _finish(pid: str, outcome: str, why: str = "") -> None:
    with _P_LOCK:
        if _P_STATE["pending"].get("id") == pid:
            _P_STATE["pending"].clear()
        _P_STATE["withdrawn"].discard(pid)
        if _P_STATE["latest"].get("id") not in (None, pid):
            return
        _P_STATE["last"].clear()
        _P_STATE["last"].update(outcome=outcome, why=why, at=time.time(),
                                message=LAST_WORDS.get(outcome, ""))
    _audit("folders.add.card", {"outcome": outcome})


def _add_now(path: str) -> None:
    with _S_LOCK:
        st = load()
        if st["why"]:
            items = []
        else:
            items = [dict(f) for f in st["folders"]]
        if any(_key(f["path"]) == _key(path) for f in items):
            return
        if len(items) >= MAX_FOLDERS:
            raise OverflowError("the list is full")
        items.append({"path": path, "added": time.time()})
        _save(items)


def _decide(pid: str, path: str, gate: Callable, tier_of: Callable,
            write: Callable[[str], None]) -> None:
    text = card(path)
    detail = {"text": text, "what": "let Jarvis look in one more folder",
              "setting": "folders Jarvis may look in", "to": path, "leaves_this_pc": False}
    try:
        v = gate(CARD_ACTION, detail, text)
    except Exception as exc:
        return _finish(pid, "refused", f"the approval gate failed ({type(exc).__name__})")
    vtier = getattr(v, "tier", "unknown")
    outcome = getattr(v, "outcome", None)
    if vtier != "ask" or tier_of(CARD_ACTION) != "ask":
        return _finish(pid, "refused", f"the gate answered at tier {vtier!r}, which is not "
                                       f"a person saying yes")
    if not _person_said_yes(v):
        if outcome in ("denied", "timed_out"):
            return _finish(pid, outcome)
        return _finish(pid, "refused", str(getattr(v, "reason", "refused"))[:200])
    with _P_SWITCH:
        with _P_LOCK:
            withdrawn = pid in _P_STATE["withdrawn"]
        if withdrawn:
            return _finish(pid, "withdrawn")
        try:
            write(path)
        except Exception as exc:
            return _finish(pid, "failed", type(exc).__name__)
    _audit("folders.added", {"count": len(folders())})
    _finish(pid, "added")


def request_add(body, *, peer=None, local=None, here: Optional[bool] = None,
                gate: Optional[Callable] = None, tier_of: Optional[Callable] = None,
                spawn: Optional[Callable] = None,
                write: Optional[Callable[[str], None]] = None) -> tuple:
    """POST /api/folders/add {"path"}. (code, body). 202 and ONE card."""
    gate = gate or _gate
    tier_of = tier_of or _tier
    spawn = spawn or _spawn
    write = write or _add_now
    is_here = bool(here) if here is not None else _from_this_pc(peer, local)
    if not is_here:
        return 403, {"ok": False, "error": PC_ONLY, "pc_only": True}
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": 'need {"path": "<a folder on this PC>"}'}
    try:
        real = check_folder(body.get("path"))
    except ValueError as exc:
        return 400, {"ok": False, "error": _sentence(exc)}
    st = load()
    for f in st["folders"]:
        if _key(f["path"]) == _key(real):
            return 200, {"ok": True, "changed": False, "view": view(here=True),
                         "message": "That folder is already on the list."}
        if _inside(_norm(f["path"]), real):
            return 200, {"ok": True, "changed": False, "view": view(here=True),
                         "message": f"That folder is already covered: it is inside "
                                    f"{f['path']}, which is on the list."}
    if len(st["folders"]) >= MAX_FOLDERS:
        return 409, {"ok": False, "error": f"The list already has {MAX_FOLDERS} folders - "
                                           f"remove one first."}
    t = tier_of(CARD_ACTION)
    if t != "ask":
        return 503, {"ok": False, "error": (
            f"{CARD_ACTION} is tier {t!r} in jarvis-framework.toml; adding a folder needs a "
            f"person to say yes, so it must be 'ask'")}
    with _P_LOCK:
        if _P_STATE["pending"]:
            return 409, {"ok": False, "error": "A card to add a folder is already waiting - "
                                               "answer it first."}
        pid = uuid.uuid4().hex
        _P_STATE["pending"].update(id=pid, path=real, since=time.time())
        _P_STATE["latest"]["id"] = pid
    try:
        spawn(lambda: _decide(pid, real, gate, tier_of, write))
    except Exception:
        with _P_LOCK:
            _P_STATE["pending"].clear()
        return 503, {"ok": False, "error": "could not raise the approval card"}
    return 202, {"ok": True, "waiting": True, "view": view(here=True),
                 "message": "Waiting for your approval. Nothing is added unless you approve "
                            "the card."}


def request_remove(body, *, peer=None, local=None) -> tuple:
    """POST /api/folders/remove {"path"}. At once, no card, either app."""
    if not isinstance(body, dict) or not isinstance(body.get("path"), str) \
            or not body["path"].strip():
        return 400, {"ok": False, "error": 'need {"path": "<a folder on the list>"}'}
    want = body["path"].strip()
    removed = False
    with _P_SWITCH:
        with _P_LOCK:
            p = _P_STATE["pending"]
            if p and (p.get("path") == want or _key(p.get("path", "")) == _key(want)):
                _P_STATE["withdrawn"].add(p["id"])
                p.clear()
                removed = True
        with _S_LOCK:
            st = load()
            items = [dict(f) for f in st["folders"]]
            kept = [f for f in items if f["path"] != want and _key(f["path"]) != _key(want)]
            if len(kept) != len(items):
                try:
                    _save(kept)
                except Exception as exc:
                    return 500, {"ok": False, "error": f"could not save the list "
                                                       f"({type(exc).__name__})"}
                removed = True
    _audit("folders.removed", {"count": len(folders())})
    here = _from_this_pc(peer, local) if peer is not None else False
    return 200, {"ok": True, "changed": removed, "view": view(here=here),
                 "message": ("Removed. Jarvis no longer looks in that folder." if removed
                             else "That folder was not on the list.")}


def _sentence(exc) -> str:
    s = str(exc).strip() or type(exc).__name__
    s = s[:1].upper() + s[1:]
    return s if s.endswith((".", "?", "!")) else s + "."


# --------------------------------------------------------------------------
#   Where a path may be - the rule every read and every name goes through
# --------------------------------------------------------------------------


def allowed_path(path, roots: Optional[list] = None) -> Optional[tuple]:
    """(real path, the listed folder it is in) when `path` may be read, else
    None: inside a listed folder once links are followed, no hidden folder on
    the way, not a reserved Windows name, not a protected place."""
    if not isinstance(path, str) or not path.strip() or "\x00" in path:
        return None
    roots = folders() if roots is None else roots
    real = os.path.realpath(os.path.expanduser(path.strip()))
    try:
        import jarvis_agent
        if jarvis_agent._is_reserved_windows_name(real):
            return None
    except Exception:
        return None
    for root in roots:
        r = _norm(root)
        if _inside(r, real):
            rel = os.path.relpath(real, r)
            parts = [] if rel == "." else re.split(r"[\\/]", rel)
            if any(p.startswith(".") for p in parts):
                return None
            if protected(real):
                return None
            return real, root
    return None


def display_name(name: str) -> str:
    """A file or folder's name without Notion's long id."""
    return _NOTION_ID.sub("", name)


def _walk(roots: list, visit: Callable[[str, str, str], bool], *,
          clock: Callable[[], float] = time.monotonic) -> str:
    """Every file under the listed folders, bounded. `visit(root, dirpath,
    name)` returns False to stop. Returns "" or why it stopped early."""
    started = clock()
    entries = 0
    for root in roots:
        r = _norm(root)
        if not os.path.isdir(r):
            continue
        for dirpath, dirnames, filenames in os.walk(r, followlinks=False):
            # Hidden folders are never entered, nor one whose real place
            # (through a link or a junction) is outside the listed folder,
            # nor a protected place.
            dirnames[:] = sorted(
                d for d in dirnames if not d.startswith(".")
                and _inside(r, os.path.realpath(os.path.join(dirpath, d)))
                and not protected(os.path.join(dirpath, d)))
            for name in sorted(filenames):
                entries += 1
                if entries > WALK_MAX_ENTRIES:
                    return f"it looked at {WALK_MAX_ENTRIES:,} files"
                if clock() - started > WALK_MAX_SECONDS:
                    return f"it ran for {WALK_MAX_SECONDS:g} seconds"
                if name.startswith("."):
                    continue
                if not visit(r, dirpath, name):
                    return ""
    return ""


def _words(text: str) -> list:
    return [w for w in re.split(r"[^\w]+", str(text or "").casefold()) if w]


def _kind(name: str) -> str:
    ext = os.path.splitext(name)[1].lower()
    return TEXT_KINDS.get(ext) or DOC_KINDS.get(ext) or ""


def find(words: str, *, roots: Optional[list] = None,
         clock: Callable[[], float] = time.monotonic) -> dict:
    """File NAMES with every word, in the listed folders."""
    roots = folders() if roots is None else roots
    want = _words(words)
    if not want:
        return {"ok": False, "error": "say a word or two from the file's name"}
    hits: list = []

    def visit(root, dirpath, name):
        shown = display_name(name)
        have = set(_words(shown))
        joined = shown.casefold()
        if all(w in have or w in joined for w in want):
            full = os.path.join(dirpath, name)
            got = allowed_path(full, [root])
            if got is not None:
                try:
                    stt = os.stat(got[0])
                    size, mtime = stt.st_size, stt.st_mtime
                except OSError:
                    size, mtime = None, None
                hits.append({"name": shown, "path": got[0],
                             "kind": _kind(name) or os.path.splitext(name)[1].lstrip(".").lower(),
                             "size": size,
                             "modified": time.strftime("%Y-%m-%d", time.localtime(mtime))
                             if mtime else ""})
        return len(hits) < FIND_MAX * 5

    stopped = _walk(roots, visit, clock=clock)
    # Newest first, then by name, so the same folder answers the same way.
    hits.sort(key=lambda h: h["name"].casefold())
    hits.sort(key=lambda h: h["modified"] or "", reverse=True)
    out = {"ok": True, "found": hits[:FIND_MAX], "matches": len(hits)}
    if stopped:
        out["stopped_early"] = (f"the search stopped early ({stopped}), so files it did not "
                                f"reach are not listed")
    return out


def _snippet(text: str, want: list) -> str:
    low = text.casefold()
    first = min((low.find(w) for w in want if w in low), default=0)
    start = max(0, first - 60)
    s = " ".join(text[start:start + SNIPPET_CHARS].split())
    return ("..." if start else "") + s


def search(words: str, *, roots: Optional[list] = None,
           clock: Callable[[], float] = time.monotonic) -> dict:
    """Words inside the notes and text files (.md, .txt, .csv)."""
    roots = folders() if roots is None else roots
    want = _words(words)
    if not want:
        return {"ok": False, "error": "say what to look for, in a few words"}
    hits: list = []
    scanned = [0]
    capped = [""]

    def visit(root, dirpath, name):
        if os.path.splitext(name)[1].lower() not in TEXT_KINDS:
            return True
        full = os.path.join(dirpath, name)
        got = allowed_path(full, [root])
        if got is None:
            return True
        if scanned[0] >= SEARCH_MAX_FILES:
            capped[0] = f"it read {SEARCH_MAX_FILES:,} files"
            return False
        scanned[0] += 1
        try:
            with open(got[0], "rb") as f:
                text = f.read(SEARCH_FILE_BYTES).decode("utf-8", "replace")
        except OSError:
            return True
        title = display_name(os.path.splitext(name)[0])
        in_title = [w for w in want if w in title.casefold()]
        body = text.casefold()
        if all(w in in_title or w in body for w in want):
            hits.append((not in_title, got[0].casefold(), {
                "name": display_name(name), "path": got[0], "snippet": _snippet(text, want)}))
        return True

    stopped = _walk(roots, visit, clock=clock) or capped[0]
    hits.sort(key=lambda h: (h[0], h[1]))
    out = {"ok": True, "results": [h[2] for h in hits[:SEARCH_MAX]], "matches": len(hits),
           "files_searched": scanned[0],
           "note": "PDF, Word, Excel and PowerPoint files are not searched inside - find them "
                   "by name, then read them."}
    if stopped:
        out["stopped_early"] = (f"the search stopped early ({stopped}), so files it did not "
                                f"reach are not in these results")
    return out


# --------------------------------------------------------------------------
#   Reading one part of one file
# --------------------------------------------------------------------------

_CHILD = r"""
import json, sys
path, ext = sys.argv[1], sys.argv[2]
extra = sys.argv[3] if len(sys.argv) > 3 else ""
if extra:
    sys.path.append(extra)
try:
    from markitdown import MarkItDown, StreamInfo
    from markitdown.converters import PdfConverter, DocxConverter, XlsxConverter, PptxConverter
except Exception as exc:
    sys.stdout.buffer.write(json.dumps({"ok": False, "missing": True,
                                        "error": type(exc).__name__}).encode("ascii"))
    sys.exit(0)
try:
    md = MarkItDown(enable_builtins=False, enable_plugins=False)
    conv = {".pdf": PdfConverter, ".docx": DocxConverter, ".xlsx": XlsxConverter,
            ".pptx": PptxConverter}[ext]
    md.register_converter(conv())
    with open(path, "rb") as fh:
        res = md.convert_stream(fh, stream_info=StreamInfo(extension=ext))
    text = res.text_content or ""
    sys.stdout.buffer.write(json.dumps({"ok": True, "text": text[:%d]}).encode("ascii"))
except Exception as exc:
    sys.stdout.buffer.write(json.dumps({"ok": False, "error": type(exc).__name__}).encode("ascii"))
""" % MAX_CONVERTED_CHARS


def _user_site() -> str:
    """The per-user packages folder, when this Python uses one: `python -I`
    leaves it out, and MarkItDown may have been installed there."""
    try:
        import site
        if site.ENABLE_USER_SITE:
            p = site.getusersitepackages()
            return p if isinstance(p, str) and os.path.isdir(p) else ""
    except Exception:
        pass
    return ""


def _child_env() -> dict:
    import jarvis_child_env
    return jarvis_child_env.inherited()


def _default_convert(path: str, ext: str) -> dict:
    """MarkItDown in its own program: no secrets, a clock, a size cap."""
    try:
        env = _child_env()
    except Exception:
        return {"ok": False, "error": "jarvis_child_env.py is missing from the backend folder, "
                                      "so no converter runs"}
    args = [sys.executable, "-I", "-c", _CHILD, path, ext]
    us = _user_site()
    if us:
        args.append(us)
    try:
        r = subprocess.run(args, env=env, capture_output=True, timeout=CONVERT_SECONDS,
                           cwd=os.path.dirname(sys.executable) or None,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"it took longer than {int(CONVERT_SECONDS)} seconds to "
                                      f"turn into text, so it was stopped"}
    except Exception as exc:
        return {"ok": False, "error": f"the converter could not start ({type(exc).__name__})"}
    out = r.stdout or b""
    try:
        # ASCII JSON: at most 6 bytes a character (\uXXXX) of the capped text.
        if len(out) > MAX_CONVERTED_CHARS * 6 + 1000:
            raise ValueError("too long")
        doc = json.loads(out.decode("ascii", "replace"))
        if not isinstance(doc, dict):
            raise ValueError("not an object")
    except Exception:
        return {"ok": False, "error": "the converter did not answer in a way Jarvis can read"}
    if doc.get("missing"):
        return {"ok": False, "missing": True, "error": CONVERTER_MISSING}
    return doc


_READY: dict = {}


def converter_ready() -> bool:
    """Is MarkItDown installed for this Python? Looked up once (no import:
    importing it here would load its converters into the backend itself)."""
    if "ready" not in _READY:
        try:
            import importlib.util
            _READY["ready"] = importlib.util.find_spec("markitdown") is not None
        except Exception:
            _READY["ready"] = False
    return bool(_READY["ready"])


#: The text of the last few files read, in memory only.
_CACHE: "OrderedDict[tuple, list]" = OrderedDict()
_C_LOCK = threading.Lock()


def split_parts(text: str, limit: int = PART_CHARS) -> list:
    """[(title, text)] - split at headings, and a section still too long at
    its paragraphs (then, for one huge paragraph, at `limit`). Nothing is
    dropped: every character of `text` is in exactly one part."""
    sections: list = []
    title, buf = "", []
    for line in text.splitlines(keepends=True):
        m = re.match(r"\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if m and buf and "".join(buf).strip():
            sections.append((title, "".join(buf)))
            buf = []
        if m:
            title = m.group(2).strip()[:120]
        buf.append(line)
    if buf and "".join(buf).strip():
        sections.append((title, "".join(buf)))
    parts: list = []
    for t, body in sections:
        if len(body) <= limit:
            parts.append((t, body))
            continue
        pieces, cur = [], ""
        for para in re.split(r"(\n\s*\n)", body):
            if len(cur) + len(para) <= limit:
                cur += para
                continue
            if cur.strip():
                pieces.append(cur)
            while len(para) > limit:
                pieces.append(para[:limit])
                para = para[limit:]
            cur = para
        if cur.strip():
            pieces.append(cur)
        for i, p in enumerate(pieces):
            parts.append((t if i == 0 else f"{t or 'Part'} (continued)", p))
    # Small neighbours with no heading of their own are joined up to the limit.
    merged: list = []
    for t, body in parts:
        if merged and not t and len(merged[-1][1]) + len(body) <= limit:
            merged[-1] = (merged[-1][0], merged[-1][1] + body)
        else:
            merged.append((t, body))
    return merged


def _text_of(real: str, ext: str, convert: Callable[[str, str], dict]) -> dict:
    """{"ok", "parts"} or {"ok": False, "error"}."""
    try:
        stt = os.stat(real)
    except OSError as exc:
        return {"ok": False, "error": f"the file could not be opened ({type(exc).__name__})"}
    if not stat.S_ISREG(stt.st_mode):
        return {"ok": False, "error": "that is not a file"}
    key = (os.path.normcase(real), stt.st_size, stt.st_mtime)
    with _C_LOCK:
        if key in _CACHE:
            _CACHE.move_to_end(key)
            return {"ok": True, "parts": _CACHE[key]}
    if ext in TEXT_KINDS:
        if stt.st_size > MAX_TEXT_BYTES:
            with open(real, "rb") as f:
                raw = f.read(MAX_TEXT_BYTES)
            note = "\n\n(The file goes on beyond this; only its first 4 MB is read.)"
        else:
            with open(real, "rb") as f:
                raw = f.read()
            note = ""
        text = raw.decode("utf-8-sig", "replace") + note
    else:
        if stt.st_size > MAX_DOC_BYTES:
            return {"ok": False, "error": f"it is larger than {MAX_DOC_BYTES // (1024 * 1024)} "
                                          f"MB, so Jarvis does not turn it into text"}
        got = convert(real, ext)
        if not got.get("ok"):
            return {"ok": False, "error": str(got.get("error") or "it could not be turned into "
                                                                  "text")}
        text = str(got.get("text") or "")
    if not text.strip():
        return {"ok": False, "error": (
            "no text was found in it. A scanned letter or bill is a picture of the page, "
            "with no text inside it for Jarvis to read." if ext == ".pdf" else
            "it has no text in it")}
    parts = split_parts(text)[:MAX_PARTS]
    with _C_LOCK:
        _CACHE[key] = parts
        _CACHE.move_to_end(key)
        while len(_CACHE) > CACHE_FILES:
            _CACHE.popitem(last=False)
    return {"ok": True, "parts": parts}


def read(path: str, part=None, words: str = "", *, roots: Optional[list] = None,
         convert: Optional[Callable[[str, str], dict]] = None) -> dict:
    """ONE part of ONE file in a listed folder, with the list of its parts."""
    roots = folders() if roots is None else roots
    got = allowed_path(path, roots)
    if got is None:
        return {"ok": False, "error": (
            "Jarvis may read only files inside the folders on the owner's list (Settings, "
            "Folders Jarvis may look in), and never keys, saved passwords, browser data or "
            "hidden folders. Use action find to get a file's path.")}
    real = got[0]
    ext = os.path.splitext(real)[1].lower()
    if ext not in TEXT_KINDS and ext not in DOC_KINDS:
        return {"ok": False, "error": "Jarvis reads PDF, Word (.docx), Excel (.xlsx), PowerPoint "
                                      "(.pptx), Markdown, text and CSV files only."}
    try:
        t = _text_of(real, ext, convert or _default_convert)
    except OSError as exc:
        return {"ok": False, "error": f"the file could not be read ({type(exc).__name__})"}
    if not t["ok"]:
        return {"ok": False, "error": t["error"], "name": display_name(os.path.basename(real))}
    parts = t["parts"]
    n = len(parts)
    k = None
    if isinstance(part, int) and not isinstance(part, bool):
        k = part
    elif isinstance(part, str) and part.strip().isdigit():
        k = int(part.strip())
    if k is not None and not 1 <= k <= n:
        return {"ok": False, "error": f"it has {n} part{'s' if n != 1 else ''}; ask for one "
                                      f"from 1 to {n}"}
    if k is None:
        want = _words(words)
        k = 1
        if want:
            best = -1
            for i, (title, body) in enumerate(parts, 1):
                low = (title + "\n" + body).casefold()
                score = sum(low.count(w) for w in want)
                if score > best:
                    best, k = score, i
    title, body = parts[k - 1]
    out = {"ok": True, "name": display_name(os.path.basename(real)), "path": real,
           "kind": DOC_KINDS.get(ext) or TEXT_KINDS.get(ext), "part": k, "parts": n,
           "title": title, "text": body}
    if n > 1:
        shown = [f"{i}. {t or '(untitled)'}" for i, (t, _b) in enumerate(parts, 1)]
        out["contents"] = shown[:CONTENTS_SHOWN] + (
            [f"... and {n - CONTENTS_SHOWN} more"] if n > CONTENTS_SHOWN else [])
        out["how"] = "Ask for another part by its number."
    return out


def run_tool(args: dict, *, roots: Optional[list] = None,
             convert: Optional[Callable[[str, str], dict]] = None) -> dict:
    """The `my_files` tool (jarvis_agent.py): find, search or read."""
    roots = folders() if roots is None else roots
    if not roots:
        return {"ok": False, "error": "The owner has not listed any folders for Jarvis to look "
                                      "in. They can add one on the PC: Settings, " + TITLE + "."}
    action = str(args.get("action") or "").strip().lower()
    if action == "find":
        return find(str(args.get("words") or ""), roots=roots)
    if action == "search":
        return search(str(args.get("words") or ""), roots=roots)
    if action == "read":
        return read(str(args.get("path") or ""), args.get("part"), str(args.get("words") or ""),
                    roots=roots, convert=convert)
    return {"ok": False, "error": "action is find, search or read"}


def describe(args: dict) -> str:
    """What a card would say, if the owner set reading files to ask."""
    action = str(args.get("action") or "")
    if action == "read":
        what = f"read part of {args.get('path', '')}"
        if args.get("part"):
            what += f" (part {args.get('part')})"
    elif action == "search":
        what = f"search inside your notes and text files for: {args.get('words', '')}"
    else:
        what = f"find files named: {args.get('words', '')}"
    return (f"Jarvis would like to {what} - only in the folders on your list, on this PC. "
            "Nothing is changed, and nothing is sent anywhere.")


# --------------------------------------------------------------------------
#   The Notion import
# --------------------------------------------------------------------------

_BAD_CHARS = re.compile(r'[<>:"|?*\x00-\x1f]')
_RESERVED = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9]|conin\$|conout\$|clock\$)(\..*)?$",
                       re.I)


class ImportRefused(Exception):
    """Why nothing was brought in, in plain words."""


def safe_parts(name: str) -> Optional[list]:
    """A zip entry's name as safe folder and file names, or None to skip it:
    no absolute path, drive letter or "..", Windows' reserved names and
    characters replaced, each name at most IMPORT_NAME_CHARS."""
    n = str(name or "").replace("\\", "/")
    if not n or n.startswith("/") or re.match(r"^[A-Za-z]:", n):
        return None
    out = []
    for seg in n.split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            return None
        seg = _BAD_CHARS.sub("_", seg).rstrip(" .")
        if not seg:
            seg = "_"
        if _RESERVED.match(seg):
            seg = "_" + seg
        if len(seg) > IMPORT_NAME_CHARS:
            stem, ext = os.path.splitext(seg)
            seg = stem[:IMPORT_NAME_CHARS - len(ext)] + ext
        out.append(seg)
    return out or None


def _is_link(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0xFFFF
    return stat.S_ISLNK(mode)


def _unzip(zf: zipfile.ZipFile, dest: str, counts: dict, depth: int) -> None:
    for info in zf.infolist():
        if info.is_dir():
            continue
        parts = safe_parts(info.filename)
        if parts is None or _is_link(info):
            counts["skipped"] += 1
            continue
        ext = os.path.splitext(parts[-1])[1].lower()
        if ext == ".zip" and depth == 0:
            # Notion splits a big workspace into Part-1.zip, Part-2.zip ...
            # One level only; its contents land beside the rest.
            # Kept in the hidden folder being filled - never a shared temp
            # folder - and deleted as soon as it is unpacked.
            inner_path = os.path.join(dest, f".inner-{uuid.uuid4().hex[:8]}.zip")
            try:
                with zf.open(info) as src, open(inner_path, "xb") as out:
                    _copy(src, out, counts, IMPORT_MAX_ZIP)
                counts["bytes"] -= os.path.getsize(inner_path)   # counted as it unpacks
                try:
                    with zipfile.ZipFile(inner_path) as inner:
                        _unzip(inner, dest, counts, depth + 1)
                except zipfile.BadZipFile:
                    counts["skipped"] += 1
            finally:
                try:
                    os.remove(inner_path)
                except OSError:
                    pass
            continue
        if ext not in IMPORT_KINDS:
            counts["skipped"] += 1
            continue
        if counts["files"] >= IMPORT_MAX_FILES:
            raise ImportRefused(f"it has more than {IMPORT_MAX_FILES:,} files")
        target = os.path.join(dest, *parts)
        real = os.path.realpath(target)
        if not _inside(os.path.realpath(dest), real):
            counts["skipped"] += 1
            continue
        if os.path.exists(real):
            base, e = os.path.splitext(real)
            i = 2
            while os.path.exists(f"{base} ({i}){e}"):
                i += 1
            real = f"{base} ({i}){e}"
        try:
            os.makedirs(os.path.dirname(real), exist_ok=True)
            with zf.open(info) as src, open(real, "xb") as out:
                _copy(src, out, counts, IMPORT_MAX_ONE)
        except ImportRefused:
            raise
        except OSError:
            # A name Windows cannot take (a path too long, for one).
            counts["failed"] += 1
            continue
        counts["files"] += 1


def _copy(src, out, counts: dict, one_max: int) -> None:
    """Copy, counting the bytes really written - not what the zip claims."""
    n = 0
    while True:
        chunk = src.read(1024 * 1024)
        if not chunk:
            return
        n += len(chunk)
        counts["bytes"] += len(chunk)
        if n > one_max:
            raise ImportRefused(f"one file in it is larger than {one_max // (1024 * 1024)} MB")
        if counts["bytes"] > IMPORT_MAX_BYTES:
            raise ImportRefused(f"it unpacks to more than "
                                f"{IMPORT_MAX_BYTES // (1024 * 1024 * 1024)} GB")
        out.write(chunk)


def import_notion(zip_path, into, *, roots: Optional[list] = None,
                  today: Optional[str] = None) -> dict:
    """Unzip a Notion export into a NEW folder inside a listed folder.
    {"ok", "folder", "files", "skipped", "failed", "said"} or ImportRefused."""
    roots = folders() if roots is None else roots
    if not isinstance(zip_path, str) or not zip_path.strip():
        raise ImportRefused("pick the .zip file Notion made")
    zp = os.path.realpath(os.path.expanduser(zip_path.strip()))
    if not zp.lower().endswith(".zip") or not os.path.isfile(zp):
        raise ImportRefused("that is not a .zip file on this PC")
    if protected(zp):
        raise ImportRefused("Jarvis does not open files in that place")
    if os.path.getsize(zp) > IMPORT_MAX_ZIP:
        raise ImportRefused("that zip is larger than 2 GB")
    if not isinstance(into, str) or not into.strip():
        raise ImportRefused("pick a folder from the list to put it in")
    target_root = None
    for r in roots:
        if _key(r) == _key(into):
            target_root = _norm(r)
    if target_root is None:
        raise ImportRefused("it can only go into a folder on the list - add the folder first")
    if not os.path.isdir(target_root) or protected(target_root):
        raise ImportRefused("that folder is not there any more")
    day = today or time.strftime("%Y-%m-%d")
    final = os.path.join(target_root, f"Notion export {day}")
    i = 2
    while os.path.exists(final):
        final = os.path.join(target_root, f"Notion export {day} ({i})")
        i += 1
    tmp = os.path.join(target_root, f".jarvis-import-{uuid.uuid4().hex[:12]}")
    counts = {"files": 0, "skipped": 0, "failed": 0, "bytes": 0}
    try:
        os.makedirs(tmp)
        try:
            with zipfile.ZipFile(zp) as zf:
                _unzip(zf, tmp, counts, 0)
        except zipfile.BadZipFile:
            raise ImportRefused("that file is not a zip Jarvis can open")
        if counts["files"] == 0:
            raise ImportRefused("there were no notes, tables or documents in it")
        os.replace(tmp, final)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    said = f"Brought in {counts['files']:,} file{'s' if counts['files'] != 1 else ''} into " \
           f"\"{os.path.basename(final)}\"."
    if counts["skipped"]:
        said += (f" {counts['skipped']:,} other file{'s were' if counts['skipped'] != 1 else ' was'}"
                 f" left out (only notes, tables, documents and pictures are brought in).")
    if counts["failed"]:
        said += (f" {counts['failed']:,} could not be written - most often a name too long "
                 f"for Windows.")
    _audit("folders.import", {"files": counts["files"], "skipped": counts["skipped"],
                              "failed": counts["failed"]})
    return {"ok": True, "folder": final, "files": counts["files"], "skipped": counts["skipped"],
            "failed": counts["failed"], "said": said}


def request_import(body, *, peer=None, local=None, here: Optional[bool] = None) -> tuple:
    """POST /api/folders/import {"zip", "into"}. This PC only; no card."""
    is_here = bool(here) if here is not None else _from_this_pc(peer, local)
    if not is_here:
        return 403, {"ok": False, "error": "A Notion export is brought in on the PC only "
                                           "(Settings, Folders Jarvis may look in).",
                     "pc_only": True}
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": 'need {"zip": "<file>", "into": "<folder>"}'}
    try:
        out = import_notion(body.get("zip"), body.get("into"))
    except ImportRefused as exc:
        return 400, {"ok": False, "error": "Nothing was brought in: " + _sentence(exc)}
    except Exception as exc:
        return 500, {"ok": False, "error": f"Nothing was brought in ({type(exc).__name__})."}
    return 200, dict(out, view=view(here=True))


# --------------------------------------------------------------------------
#   The routes - wrapped round the server's handler (documents.patch)
# --------------------------------------------------------------------------

_ARMED = False


def armed() -> bool:
    return _ARMED


def _peer_local(handler) -> tuple:
    peer = (getattr(handler, "client_address", None) or ("",))[0]
    try:
        local = handler.connection.getsockname()[0]
    except Exception:
        local = None
    return peer, local


def handle_get(peer=None, local=None) -> tuple:
    return 200, view(here=_from_this_pc(peer, local))


def handle_post(route: str, body, peer=None, local=None) -> tuple:
    if route == ADD_ROUTE:
        return request_add(body, peer=peer, local=local)
    if route == REMOVE_ROUTE:
        return request_remove(body, peer=peer, local=local)
    return request_import(body, peer=peer, local=local)


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls.do_GET` and `do_POST` so the four folder routes are
    answered here, after the server's own origin and token checks. Every
    other request goes straight to the original. Returns the banner line."""
    global _ARMED
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(post0, "_jarvis_folders", False):
        _ARMED = True
        return "  folders    Folders Jarvis may look in (already on)"

    def _allowed(self) -> bool:
        try:
            if not origin_ok(self):
                self._send(403, {"error": "cross-origin request refused"})
                return False
            if not token_ok(self):
                self._send(401, {"error": "bad or missing X-Jarvis-Token"})
                return False
        except Exception:
            self._send(401, {"error": "bad or missing X-Jarvis-Token"})
            return False
        return True

    def do_GET(self):
        route = urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if route != PATH:
            return get0(self)
        if not _allowed(self):
            return None
        try:
            code, out = handle_get(*_peer_local(self))
        except Exception as exc:
            code, out = 503, {"available": False, "error": type(exc).__name__}
        return self._send(code, out)

    def do_POST(self):
        route = urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if route not in (ADD_ROUTE, REMOVE_ROUTE, IMPORT_ROUTE):
            return post0(self)
        if not _allowed(self):
            return None
        try:
            body = json.loads(read_body(self) or b"{}")
        except Exception as exc:
            return self._send(400, {"error": type(exc).__name__})
        try:
            code, out = handle_post(route, body, *_peer_local(self))
        except Exception as exc:
            code, out = 503, {"available": False, "error": type(exc).__name__}
        return self._send(code, out)

    do_GET._jarvis_folders = True
    do_POST._jarvis_folders = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    _ARMED = True
    return (f"  folders    Folders Jarvis may look in: {len(folders())} listed; "
            + ("PDF and Word reading on" if converter_ready() else
               "PDF and Word reading off (MarkItDown not installed)"))


def _reset_for_tests() -> None:
    global _ARMED
    with _P_LOCK:
        _P_STATE["pending"].clear()
        _P_STATE["withdrawn"].clear()
        _P_STATE["last"].clear()
        _P_STATE["latest"].clear()
    with _C_LOCK:
        _CACHE.clear()
    _READY.clear()
    _ARMED = False


if __name__ == "__main__":
    st = load()
    print(f"  {TITLE}: {len(st['folders'])} listed" + (f" ({st['why']})" if st["why"] else ""))
    for f in st["folders"]:
        print(f"    {f['path']}")
    print(f"  {CONVERTER_READY if converter_ready() else CONVERTER_MISSING}")
