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

THE SEARCH INDEX - a derived file that makes `search` rank, not just match
  * `search` ranks with SQLite's own `bm25` over an FTS5 index, the same
    machinery jarvis_memory.py ranks remembered facts with, and fuses it by
    reciprocal rank with meaning when this PC has a meaning model loaded. The
    index is ONE new file in the settings folder, beside folders.json:
    `documents-index.db`. It is NOT `memory.db` - that file is not ours
    (jarvis_owned_tables.py) and no table here is called `documents`.
  * IT IS NOT A SOURCE OF TRUTH. It can only rank: every snippet is read from
    the file when the answer is built, a file whose size or mtime moved is
    re-indexed first, a row whose file has gone is dropped, and deleting the
    index rebuilds it. The FTS table is CONTENTLESS, so a file's words are
    indexed and its text is never stored in the index.
  * WITHOUT fastembed (CI, or a PC that has never had it) the meaning half is
    simply not used and `bm25` alone ranks. A missing model is never an error
    and never an empty answer; with no usable index at all, `search` is the
    plain word scan it has always been. `JARVIS_DOCUMENTS_EMBED=0` turns the
    meaning half off outright.
  * Writes locally and only locally: the index file, inside Jarvis's own
    settings folder. Nothing is written into a listed folder, nothing is sent
    anywhere, and the tool still never changes, moves or deletes a file of
    the owner's.

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
    part 2 does not convert again) - never written to disk. (The search
    index above is a different thing, and holds no document text at all.)
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

Standard library only, apart from MarkItDown in the child process, the shared
closing-connection helper (jarvis_sqlite.py) the search index uses, and the
meaning model (fastembed, inside jarvis_memory.py, imported only when the
index is used, and never required). Nothing here opens a socket.
"""
from __future__ import annotations

import json
import ntpath
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import threading
import time
import uuid
import zipfile
from array import array
from collections import OrderedDict
from math import sqrt
from operator import mul
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import parse_qs, urlsplit

try:
    import jarvis_framework as fw
except Exception:  # pragma: no cover - shipped beside it on the PC
    fw = None  # type: ignore

try:
    import jarvis_sqlite  # the ONE closing-connection helper (test_sqlite_close_guard.py)
except Exception:  # pragma: no cover - shipped beside it on the PC
    jarvis_sqlite = None  # type: ignore

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
#: A .docx/.xlsx/.pptx is a ZIP: the most its members may declare in total
#: before any parser sees it (the 2026-10-20 parser audit; a 50 MB compressed
#: file can otherwise unpack to gigabytes - a zip bomb).
DOC_UNCOMPRESSED_MAX = 100 * 1024 * 1024
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
#: A chat/Notion export is also a ZIP. The same member check as DOC above, with
#: the export ceiling the 2026-10-20 audit asks for (250 MiB, not 100); the
#: byte counter in _copy still bounds what is really written.
EXPORT_UNCOMPRESSED_MAX = 250 * 1024 * 1024
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


def _real(path) -> str:
    """One real place: `Path.resolve()` (links AND NTFS junctions followed,
    each part of the path resolved), never the spelling a caller typed. The
    2026-10-20 parser audit asks for exactly this on every walked child, so a
    junction inside a listed folder cannot smuggle a read out of it."""
    return str(Path(os.path.expanduser(str(path))).resolve())


def _private_roots() -> list:
    """Places always refused, even when a listed folder links to them: Jarvis's
    own config folder (tokens, setup answers, chat history). The program folder
    is refused by `protected()`; the folders a person may list are never inside
    AppData because `_too_broad()` refuses it at add time, so refusing all of
    AppData here would also refuse the scratch folders the suites run in."""
    try:
        return [_real(_config_dir())]
    except Exception:
        return []


def _in_a_private_place(real: str) -> bool:
    return any(_inside(root, real) for root in _private_roots())


def zip_path_problem(zf: zipfile.ZipFile) -> str:
    """'' when no member path points outside the archive, else why not.

    Rejected: an absolute path, a drive-qualified path, or any `..` segment -
    the traversal half of the 2026-10-20 parser audit. Used where an archive
    is unpacked or handed to a parser (a `.docx` and a chat export), never to
    decide whether a Notion export may be read: that importer has always
    skipped such a member and kept the rest (`safe_parts`), which is safer for
    the person than refusing the whole export over one junk name."""
    for info in zf.infolist():
        name = str(info.filename or "")
        flat = name.replace("\\", "/")
        if (flat.startswith("/") or re.match(r"^[A-Za-z]:", flat)
                or any(part == ".." for part in flat.split("/"))):
            return f"it contains a path that points outside itself ({name!r})"
    return ""


def zip_bomb_problem(zf: zipfile.ZipFile, limit: int) -> str:
    """'' when the declared uncompressed total is at or under `limit`, else why
    not. Declared sizes do not replace counting what is written on extraction;
    `IMPORT_MAX_BYTES` still does that."""
    total = 0
    for info in zf.infolist():
        total += max(0, int(info.file_size or 0))
        if limit and total > limit:
            return (f"it unpacks to more than {limit // (1024 * 1024)} MB "
                    "(a zip-bomb guard)")
    return ""


def zip_problem(zf: zipfile.ZipFile, limit: int) -> str:
    """'' when this archive may be parsed, else why not (a sentence's end)."""
    return zip_path_problem(zf) or zip_bomb_problem(zf, limit)


def allowed_path(path, roots: Optional[list] = None) -> Optional[tuple]:
    """(real path, the listed folder it is in) when `path` may be read, else
    None: inside a listed folder once links are followed, no hidden folder on
    the way, not a reserved Windows name, not a protected place."""
    if not isinstance(path, str) or not path.strip() or "\x00" in path:
        return None
    roots = folders() if roots is None else roots
    real = _real(path.strip())
    if _in_a_private_place(real):
        return None
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
                and _inside(r, _real(os.path.join(dirpath, d)))
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


# --------------------------------------------------------------------------
#   The search index - derived, rebuildable, and never a second copy
# --------------------------------------------------------------------------
#
# WHY. The scan below reads every note and text file it can reach, on every
# call (up to SEARCH_MAX_FILES of them inside WALK_MAX_SECONDS), and calls a
# hit "every word is somewhere in the file". That answers "is this word in my
# notes" and nothing better: on a folder of a few thousand notes it is slow,
# and a note that is plainly about the thing in other words is not found.
#
# WHAT IT IS. One SQLite file in Jarvis's own settings folder, beside
# `folders.json`:
#   * `doc_index` - one row per indexed file: its real path, the listed folder
#     it was found under, its display name, and the size and mtime the row was
#     built from;
#   * `doc_fts`   - a CONTENTLESS FTS5 index: SQLite's own word index, ranked
#     with `bm25(...)`, which is the same machinery jarvis_memory.py ranks
#     `facts_fts` with. CONTENTLESS means a file's words are INDEXED and not
#     STORED - the index holds no readable copy of a document, and a note the
#     owner deletes leaves no text behind in it;
#   * `doc_vec`   - one optional vector per file, present only when a meaning
#     model is loaded, so a question can reach a note that shares no words.
#
# NOT A SOURCE OF TRUTH, AND THIS IS THE PART THAT MATTERS. The files on disk
# are the only truth:
#   * the index can only RANK. Every hit's snippet is read from the file when
#     the answer is built, so what the model is shown is the file as it is now;
#   * a file whose size or mtime moved is re-indexed before it is ranked, and
#     a row whose file has gone is dropped - and nothing is dropped at all
#     when the walk stopped early and so cannot say what is still there;
#   * delete the index file and the next search rebuilds it from the folders.
#     It holds nothing that is not on disk, so losing it loses nothing.
#
# AN EXISTING INSTALL. The first search after this lands creates ONE new file
# in the settings folder and adds three tables to it. It never opens, reads or
# changes `memory.db`: that file is not ours (jarvis_owned_tables.py says why),
# and a table called `documents` in it belongs to OpenJarvis. NO TABLE HERE IS
# CALLED `documents`, deliberately. Nothing is ALTERed; there is one schema
# version in `doc_meta`, and if a later version of this module ever changed
# the shape of the DERIVED tables it would drop and rebuild them, which loses
# no document because every document is on disk.
#
# WITHOUT A MEANING MODEL (CI, and any PC without fastembed). The vector half
# is simply not used: `bm25` alone ranks, which is the same word-index ranking
# a machine with the model gets, minus the semantic recall. A missing embedder
# is never an error and never an empty answer.

#: The index file, in the settings folder - NOT memory.db, and not a listed
#: folder. `index_path()` below is the one place its name is written.
INDEX_FILE = "documents-index.db"
#: One schema version, kept in `doc_meta`. A mismatch drops and rebuilds the
#: DERIVED tables - see the note above about what that does and does not lose.
INDEX_SCHEMA = 1
#: Reciprocal-rank fusion, the same shape AND the same constant that
#: jarvis_memory.search() fuses its own lists with: the hit at rank r adds
#: 1 / (RRF_K + r) to that file's score, so two lists that agree lift a file
#: and one list on its own cannot bury it.
RRF_K = 60
#: How many candidates each half hands to the fusion.
INDEX_CANDIDATES = 50
#: At most this many files get a MEANING vector per search, so the first
#: search after a change is never held up by an embedding model. Words rank
#: everything immediately; meaning fills in over the next few searches.
EMBED_MAX_PER_CALL = 64
#: The whole meaning pass is bounded at this many rows.
VEC_MAX_ROWS = SEARCH_MAX_FILES
#: HOW CLOSE A DOCUMENT HAS TO BE to be added by MEANING. This is a floor and
#: a margin, not a "> 0", and the difference is the whole feature: two pieces
#: of ordinary English score about 0.35-0.5 against each other whatever they
#: are about, so "every cosine above zero" hands back every file in the folder
#: and buries the one that matched. MEASURED on this PC (2026-10-16, the
#: memory model, 5 documents, 6 questions): the document a question is really
#: about scored 0.56-0.81, and every other document scored 0.35-0.52 - even
#: for "quantum chromodynamics lecture", which is about nothing in the folder.
#: So a document joins by meaning only when it is both above the floor and
#: within the margin of the best one - and a question with no near document
#: adds none at all, which is the honest answer.
VEC_MIN_SCORE = float(os.environ.get("JARVIS_DOCUMENTS_VEC_MIN", "0.55"))
VEC_MARGIN = float(os.environ.get("JARVIS_DOCUMENTS_VEC_MARGIN", "0.90"))
#: Words too common to carry a query. The same lesson jarvis_memory.py's _STOP
#: records: an OR over "the" and "is" ranks the whole corpus and tells you
#: nothing about which file you meant.
_INDEX_STOP = frozenset(
    """a about an and are as at be but by can could did do does for from had has have he her
    his how i if in into is it its me my no not of on or our out she should so some than that
    the their them then there these they this to too up us very was we were what when where
    which who why will with would you your""".split())


def index_path(name: str = INDEX_FILE) -> Path:
    """A derived search index: one SQLite file in Jarvis's settings folder.

    `name` is how a second caller keeps its own corpus apart - jarvis_notes.py
    indexes an Obsidian vault in `notes-index.db` rather than sharing this
    module's file, so one index never holds two different answers to "what is
    in the folders".

    Deliberately NOT `memory.db`. That file is not ours (jarvis_owned_tables.py
    records why) and a table called `documents` in it is OpenJarvis's, read
    into the brain map by jarvis_hud.py if it is ever there.
    """
    return _config_dir() / name


def _index_terms(words: str, limit: int = 24) -> list:
    """The query's content words, in the order they were asked, without the
    words that appear in everything."""
    out: list = []
    for w in _words(words):
        if w in _INDEX_STOP or (len(w) < 2 and not w.isdigit()):
            continue
        if w not in out:
            out.append(w)
    return out[:limit]


def _fts_query(terms: list) -> str:
    """An OR of quoted terms - FTS5's own syntax, built from words this module
    took apart itself, never from a raw string the model handed in."""
    return " OR ".join('"' + str(t).replace('"', '""') + '"' for t in terms)


def _pack_vec(vec) -> bytes:
    return array("f", [float(x) for x in vec]).tobytes()


def _unpack_vec(blob: bytes, dim: int):
    try:
        out = array("f")
        out.frombytes(bytes(blob))
    except Exception:
        return None
    return out if len(out) == dim and dim > 0 else None


def _cosine(a, b) -> float:
    """How close two vectors point. 0.0 when either is empty or all zero."""
    if a is None or b is None or len(a) != len(b) or not len(a):
        return 0.0
    dot = sum(map(mul, a, b))
    na = sqrt(sum(map(mul, a, a)))
    nb = sqrt(sum(map(mul, b, b)))
    if not na or not nb:
        return 0.0
    return dot / (na * nb)


class TextIndex:
    """The word (and, when a meaning model is loaded, meaning) index.

    A connection is opened and CLOSED around each call, never held open -
    an open handle on Windows is what makes a file undeletable, which is the
    whole reason jarvis_sqlite.py exists. Every method is safe to call when
    nothing works: it answers False or an empty ranking rather than raising,
    because a search that cannot use its index must fall back to the scan.
    """

    def __init__(self, path: Optional[Path] = None, *,
                 kinds: Optional[set] = None) -> None:
        self.path = Path(path) if path is not None else index_path()
        #: Which file kinds this index carries. `search()` wants every text
        #: file; a notes vault wants its own `.md` pages only.
        self.kinds = set(TEXT_KINDS) if kinds is None else set(kinds)
        self.why = ""                # why it is not being used, in plain words
        self.row_delete: Optional[bool] = None   # can ONE row leave the index?
        self._lock = threading.RLock()

    # -- the database -------------------------------------------------------
    def _db(self):
        """A connection that CLOSES when its `with` ends, with rows by name.

        `jarvis_sqlite.connect` is the one place this repository closes a
        connection properly (test_sqlite_close_guard.py is the guard), and it
        leaves `row_factory` to its caller - every query below reads its
        columns by name.
        """
        c = jarvis_sqlite.connect(str(self.path))
        c.row_factory = sqlite3.Row
        return c

    def _ready(self, c) -> None:
        """Create what is missing. Idempotent, and safe on a fresh file, an
        existing index and a file left by a LATER version of this module."""
        c.execute("CREATE TABLE IF NOT EXISTS doc_meta ("
                  "key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        row = c.execute("SELECT value FROM doc_meta WHERE key='schema'").fetchone()
        have = int(row["value"]) if row is not None and str(row["value"]).isdigit() else 0
        if have and have != INDEX_SCHEMA:
            # The DERIVED tables only. No document lives here, so there is
            # nothing to lose: the next reconcile re-reads the folders.
            for table in ("doc_fts", "doc_vec", "doc_index"):
                c.execute(f"DROP TABLE IF EXISTS {table}")
            c.execute("DELETE FROM doc_meta WHERE key='schema'")
            have = 0
        c.execute("CREATE TABLE IF NOT EXISTS doc_index ("
                  "path TEXT PRIMARY KEY, root TEXT NOT NULL, name TEXT NOT NULL,"
                  " size INTEGER, mtime_ns INTEGER, indexed_at REAL NOT NULL)")
        # CONTENTLESS: the words are indexed, the document is not stored.
        # `contentless_delete` lets one row out again, which arrived in SQLite
        # 3.43; where it is not supported the plain contentless table is made
        # instead and a removal rebuilds the word index (see _drop_rows).
        try:
            c.execute("CREATE VIRTUAL TABLE IF NOT EXISTS doc_fts USING fts5("
                      "text, content='', contentless_delete=1)")
        except Exception:
            c.execute("CREATE VIRTUAL TABLE IF NOT EXISTS doc_fts USING fts5("
                      "text, content='')")
        c.execute("CREATE TABLE IF NOT EXISTS doc_vec ("
                  "path TEXT PRIMARY KEY, model TEXT NOT NULL, dim INTEGER NOT NULL,"
                  " vec BLOB NOT NULL)")
        if not have:
            c.execute("INSERT OR REPLACE INTO doc_meta(key, value) "
                      "VALUES('schema', ?)", (str(INDEX_SCHEMA),))

    def _can_drop_one_row(self, c) -> bool:
        """Does ONE row come out of this SQLite's contentless FTS index?

        Not "is the module new enough" - the question is whether the DELETE
        works, so this does the delete on a throwaway table in `temp.`, the
        rule jarvis_memory._try_vec records for its own vec0 probe.
        """
        if self.row_delete is not None:
            return self.row_delete
        try:
            c.execute("CREATE VIRTUAL TABLE IF NOT EXISTS temp._doc_fts_probe "
                      "USING fts5(x, content='', contentless_delete=1)")
            c.execute("INSERT INTO temp._doc_fts_probe(rowid, x) VALUES (1, 'probe')")
            c.execute("DELETE FROM temp._doc_fts_probe WHERE rowid = 1")
            c.execute("DROP TABLE temp._doc_fts_probe")
            self.row_delete = True
        except Exception:
            try:
                c.execute("DROP TABLE IF EXISTS temp._doc_fts_probe")
            except Exception:
                pass
            self.row_delete = False
        return self.row_delete

    def _read_text(self, path: str) -> Optional[str]:
        """What of one file is indexed: the same bytes the scan reads, decoded
        the same forgiving way."""
        try:
            with open(path, "rb") as f:
                return f.read(SEARCH_FILE_BYTES).decode("utf-8", "replace")
        except OSError:
            return None

    # -- staying level with the folders -------------------------------------
    def reconcile(self, roots: list, *,
                  clock: Callable[[], float] = time.monotonic) -> bool:
        """Bring the index level with the listed folders.

        True when it can be used afterwards. Reads only files whose size or
        mtime moved, keeps exactly what the scan would reach (allowed_path,
        protected places, hidden folders), and never prunes when the walk
        stopped early. Never raises: any failure means "use the scan".
        """
        if not roots:
            return False
        try:
            with self._lock, self._db() as c:
                self._ready(c)
                return self._reconcile(c, roots, clock=clock)
        except Exception as exc:
            self.why = f"the index could not be used ({type(exc).__name__})"
            return False

    def _reconcile(self, c, roots: list, *,
                   clock: Callable[[], float]) -> bool:
        found: dict = {}
        capped = [False]
        mine = os.path.realpath(str(self.path))

        def visit(root, dirpath, name):
            if os.path.splitext(name)[1].lower() not in self.kinds:
                return True
            got = allowed_path(os.path.join(dirpath, name), [root])
            if got is None:
                return True
            real = got[0]
            if os.path.realpath(real) == mine:
                return True                    # never index the index itself
            try:
                stt = os.stat(real)
            except OSError:
                return True
            found[real] = (root, name, stt.st_size, stt.st_mtime_ns)
            if len(found) >= SEARCH_MAX_FILES:
                capped[0] = True               # as many as one search reads
                return False
            return True

        stopped = _walk(roots, visit, clock=clock)
        incomplete = bool(stopped) or capped[0]

        rows = {r["path"]: r for r in c.execute(
            "SELECT rowid, path, size, mtime_ns FROM doc_index")}
        fresh, moved = [], []
        for path, (root, name, size, mtime) in found.items():
            row = rows.get(path)
            if row is None:
                fresh.append((path, root, name, size, mtime))
            elif row["size"] != size or row["mtime_ns"] != mtime:
                moved.append((path, root, name, size, mtime, row["rowid"]))
        gone = [] if incomplete else [p for p in rows if p not in found]
        gone_rows = [rows[p]["rowid"] for p in gone]
        moved_rows = [m[5] for m in moved]
        wipe = False

        if gone_rows or moved_rows:
            if incomplete:
                # Something left or moved, and the walk cannot say whether it
                # is still there: change nothing rather than drop a good row.
                pass
            elif self._drop_rows(c, gone_rows + moved_rows):
                pass
            else:
                # This SQLite cannot take one row out of a contentless index,
                # so the whole word index is rebuilt from the files - which is
                # where the documents are, and the only place they live.
                c.execute("INSERT INTO doc_fts(doc_fts) VALUES('delete-all')")
                c.execute("DELETE FROM doc_vec")
                wipe = True
                # A file that has GONE still has to leave the index's own
                # table: its row is what the ranking reads paths from.
                for path in gone:
                    c.execute("DELETE FROM doc_index WHERE path=?", (path,))
                fresh = [(path, root, name, size, mtime)
                         for path, (root, name, size, mtime) in found.items()]
                moved = []
                for path, (root, name, size, mtime) in found.items():
                    # the rowids stay; only the FTS rows are rebuilt
                    c.execute("UPDATE doc_index SET size=?, mtime_ns=? WHERE path=?",
                              (size, mtime, path))
                gone = []
                gone_rows = []

        for path, root, name, size, mtime, _rowid in moved:
            c.execute("DELETE FROM doc_vec WHERE path=?", (path,))
            fresh.append((path, root, name, size, mtime))

        for path, root, name, size, mtime in fresh:
            text = self._read_text(path)
            if text is None:
                continue
            c.execute("INSERT OR REPLACE INTO doc_index"
                      "(path, root, name, size, mtime_ns, indexed_at) "
                      "VALUES(?, ?, ?, ?, ?, ?)",
                      (path, root, name, size, mtime, time.time()))
            rowid = c.execute("SELECT rowid FROM doc_index WHERE path=?",
                              (path,)).fetchone()["rowid"]
            if not wipe:
                # Take this file's OLD row out. A brand-new rowid has nothing
                # to remove, so this is a no-op for a file that is simply new;
                # it matters for one that CHANGED. `wipe` means the clear
                # above already did it for every row at once.
                try:
                    c.execute("DELETE FROM doc_fts WHERE rowid = ?", (rowid,))
                except Exception:
                    pass
            # The NAME goes in with the text, because a search for a note's
            # own title has to find it: the scan this replaced matched the file
            # name as well as the body ("Margaret" finds "Margaret Hale.md"
            # even when the page never says her name), and losing that would be
            # a worse answer than the one it improved on.
            c.execute("INSERT INTO doc_fts(rowid, text) VALUES(?, ?)",
                      (rowid, display_name(name) + "\n" + text))

        for path in gone:
            c.execute("DELETE FROM doc_index WHERE path=?", (path,))
            c.execute("DELETE FROM doc_vec WHERE path=?", (path,))

        stayed = c.execute("SELECT count(*) AS n FROM doc_index").fetchone()["n"]
        return bool(stayed) or not incomplete

    def _drop_rows(self, c, rowids: list) -> bool:
        """Take rows out of the word index. False when this SQLite cannot, so
        the caller rebuilds instead."""
        if not rowids:
            return True
        if not self._can_drop_one_row(c):
            return False
        try:
            for rowid in rowids:
                c.execute("DELETE FROM doc_fts WHERE rowid = ?", (rowid,))
            return True
        except Exception:
            return False

    # -- meaning, when there is a model -------------------------------------
    def embed_missing(self, embedder, *, limit: int = EMBED_MAX_PER_CALL) -> int:
        """Give up to `limit` files a meaning vector. 0 when there is no usable
        model - never an error, and never anything the word half depends on."""
        if embedder is None or not getattr(embedder, "semantic", False):
            return 0
        model = str(getattr(embedder, "model", "") or getattr(embedder, "name", "") or "?")
        done = 0
        try:
            with self._lock, self._db() as c:
                self._ready(c)
                rows = c.execute(
                    "SELECT i.path AS path FROM doc_index i "
                    "LEFT JOIN doc_vec v ON v.path = i.path "
                    "WHERE v.path IS NULL LIMIT ?", (int(limit),)).fetchall()
                for row in rows:
                    text = self._read_text(row["path"])
                    if not text:
                        continue
                    vec = _embed_texts(embedder, [text[:SEARCH_FILE_BYTES]])[0]
                    if not vec:
                        break
                    c.execute("INSERT OR REPLACE INTO doc_vec"
                              "(path, model, dim, vec) VALUES(?, ?, ?, ?)",
                              (row["path"], model, len(vec), _pack_vec(vec)))
                    done += 1
        except Exception:
            return done
        return done

    # -- ranking ------------------------------------------------------------
    def query(self, words: str, *, embedder=None,
              candidates: int = INDEX_CANDIDATES) -> dict:
        """Rank the indexed files for `words`.

        `bm25` over the word index, fused by reciprocal rank with the meaning
        half when an embedder is really there. Returns
        {"ranked": [{path, name, score, how}], "how": "...", "matches": n,
         "meaning": bool} - an empty ranking when nothing matched, never an
        exception.
        """
        terms = _index_terms(words)
        out = {"ranked": [], "how": "bm25", "matches": 0, "meaning": False,
               "files": 0}
        try:
            with self._lock, self._db() as c:
                self._ready(c)
                meta = {r["path"]: r for r in c.execute(
                    "SELECT rowid, path, name FROM doc_index")}
                by_rowid = {r["rowid"]: r for r in meta.values()}
                by_path = {r["path"]: r["rowid"] for r in meta.values()}
                out["files"] = len(meta)
                scores: dict = {}

                if terms:
                    q = _fts_query(terms)
                    try:
                        rows = c.execute(
                            "SELECT rowid, bm25(doc_fts) AS s FROM doc_fts "
                            "WHERE doc_fts MATCH ? ORDER BY s LIMIT ?",
                            (q, int(candidates))).fetchall()
                        out["matches"] = c.execute(
                            "SELECT count(*) AS n FROM doc_fts WHERE doc_fts MATCH ?",
                            (q,)).fetchone()["n"]
                    except Exception:
                        rows = []
                    for rank, row in enumerate(rows, 1):
                        if row["rowid"] in by_rowid:
                            scores[row["rowid"]] = scores.get(row["rowid"], 0.0) \
                                + 1.0 / (RRF_K + rank)

                if embedder is not None and getattr(embedder, "semantic", False):
                    qv = _embed_texts(embedder, [words])
                    if qv and qv[0]:
                        qvec = _unpack_vec(_pack_vec(qv[0]), len(qv[0]))
                        got = []
                        for row in c.execute(
                                "SELECT path, dim, vec FROM doc_vec LIMIT ?",
                                (VEC_MAX_ROWS,)):
                            score = _cosine(qvec,
                                            _unpack_vec(row["vec"], int(row["dim"])))
                            if score > 0:
                                got.append((score, row["path"]))
                        got.sort(key=lambda t: (-t[0], t[1].casefold()))
                        # The floor: see VEC_MIN_SCORE. A file joins by meaning
                        # only when it is close in its own right AND close to
                        # the best one, so a question nothing is about adds
                        # nothing rather than everything.
                        if got:
                            line = max(VEC_MIN_SCORE, got[0][0] * VEC_MARGIN)
                            got = [t for t in got if t[0] >= line]
                        out["meaning"] = bool(got)
                        if got:
                            out["how"] = "bm25+meaning"
                            for rank, (_s, path) in enumerate(got[:candidates], 1):
                                rowid = by_path.get(path)
                                if rowid is not None:
                                    scores[rowid] = scores.get(rowid, 0.0) \
                                        + 1.0 / (RRF_K + rank)

                ranked = [{"rowid": rowid, "path": by_rowid[rowid]["path"],
                           "name": by_rowid[rowid]["name"], "score": score,
                           "how": out["how"]}
                          for rowid, score in scores.items() if rowid in by_rowid]
                ranked.sort(key=lambda h: (-h["score"], h["path"].casefold()))
                out["ranked"] = ranked
        except Exception as exc:
            out["how"] = f"none ({type(exc).__name__})"
            out["ranked"] = []
        return out

    def status(self) -> dict:
        """What the index holds, for a test or a status line - never raises."""
        out = {"file": str(self.path), "exists": self.path.exists(),
               "files": 0, "vectors": 0, "why": self.why}
        try:
            with self._lock, self._db() as c:
                self._ready(c)
                out["files"] = c.execute(
                    "SELECT count(*) AS n FROM doc_index").fetchone()["n"]
                out["vectors"] = c.execute(
                    "SELECT count(*) AS n FROM doc_vec").fetchone()["n"]
        except Exception as exc:
            out["why"] = f"{type(exc).__name__}"
        return out


#: The one index this process uses, and the one meaning model. Both are made
#: on first use and can be dropped by `_reset_for_tests()`.
_INDEX: Optional[TextIndex] = None
_INDEX_LOCK = threading.Lock()
_EMBEDDER = None
_EMBEDDER_TRIED = False


def the_index() -> TextIndex:
    """THE index for the current settings folder.

    Rebuilt when the settings folder moved (which is how the tests keep one
    run away from the next), so nothing is ever indexed into the wrong file.
    """
    global _INDEX
    with _INDEX_LOCK:
        if _INDEX is None or Path(_INDEX.path) != index_path():
            _INDEX = TextIndex()
        return _INDEX


def document_embedder():
    """The meaning model for document search, or None - never an exception.

    This machine already knows one way to load fastembed for a search, and it
    is `jarvis_memory`'s. Reusing it means one model in memory and one model
    on disk, not a second copy of either. It never raises: with no fastembed
    (or `JARVIS_NO_EMBED=1`) it hands back a hash stand-in, and a stand-in's
    numbers are not meaning - so it is refused here by checking `semantic`,
    exactly the test jarvis_memory.search() makes for its own vector half.

    `JARVIS_DOCUMENTS_EMBED=0` turns the meaning half off outright.
    """
    global _EMBEDDER, _EMBEDDER_TRIED
    if os.environ.get("JARVIS_DOCUMENTS_EMBED", "").strip().lower() in (
            "0", "off", "no", "false"):
        return None
    with _INDEX_LOCK:
        if _EMBEDDER_TRIED:
            return _EMBEDDER
        _EMBEDDER_TRIED = True
        try:
            import jarvis_memory as M               # the one embedder here
            maker = getattr(M, "_make_embedder", None)
            _EMBEDDER = maker() if callable(maker) else None
        except Exception:
            _EMBEDDER = None
        if _EMBEDDER is not None and not getattr(_EMBEDDER, "semantic", False):
            _EMBEDDER = None                        # a stand-in is not meaning
        return _EMBEDDER


def _embed_texts(embedder, texts: list) -> list:
    """Vectors for `texts`, or [] - a model that fails is simply not used."""
    if embedder is None:
        return []
    for name in ("embed_query", "embed"):
        fn = getattr(embedder, name, None)
        if not callable(fn):
            continue
        try:
            got = fn(list(texts))
        except Exception:
            continue
        try:
            return [list(v) for v in got]
        except Exception:
            return []
    return []


def _scan_search(words: str, *, roots: Optional[list] = None,
                 clock: Callable[[], float] = time.monotonic) -> dict:
    """The word scan - the fallback search() falls back TO.

    Used when there is no usable index (no SQLite with FTS5, an index file
    that cannot be opened or written, a settings folder that cannot be
    written in). A missing index can therefore never be an error and never an
    empty answer: this is the answer search() gave before the index existed,
    kept whole.
    """
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
           "files_searched": scanned[0], "note": SEARCH_NOTE}
    if stopped:
        out["stopped_early"] = (f"the search stopped early ({stopped}), so files it did not "
                                f"reach are not in these results")
    return out


#: The sentence every search carries about what it does NOT look inside. It is
#: one string because the two halves of search() - the index and the scan -
#: must say the same thing; `t_find_and_search` pins the words.
SEARCH_NOTE = ("PDF, Word, Excel and PowerPoint files are not searched inside - find them "
               "by name, then read them.")


def search(words: str, *, roots: Optional[list] = None,
           clock: Callable[[], float] = time.monotonic,
           index=None, embedder=None) -> dict:
    """Words inside the notes and text files (.md, .txt, .csv).

    Ranked by SQLite's own `bm25` over the index (and, when a meaning model is
    loaded on this PC, by meaning as well, fused by reciprocal rank) - and by
    the plain word scan below when there is no usable index. The two answer
    with the SAME keys, because callers exist and none of them should care
    which half answered:

        ok, results [{name, path, snippet}], matches, files_searched, note,
        and `stopped_early` when the walk could not reach everything.
    Added, so a caller CAN care: `ranked_by` ("bm25", "bm25+meaning" or
    "words"), `index_files` (how many files the index holds) and `meaning`.

    Every snippet is read from the file itself, index or no index, so what
    comes back is the file as it is now.
    """
    roots = folders() if roots is None else roots
    want = _words(words)
    if not want:
        return {"ok": False, "error": "say what to look for, in a few words"}

    idx = the_index() if index is None else index
    if idx is not None:
        model = document_embedder() if embedder is None else embedder
        # A rank is a nicety; the answer is not. Anything the index does wrong
        # - including a bug in it - falls through to the scan below rather than
        # reaching the owner as a failed search. (`TextIndex` catches its own
        # failures; this is the belt to that pair of braces.)
        try:
            usable = idx.reconcile(roots, clock=clock)
            if usable:
                idx.embed_missing(model)
                ranked = idx.query(words, embedder=model)
                if ranked["ranked"] or not ranked["how"].startswith("none"):
                    return _index_results(words, want, ranked, idx, model, roots)
        except Exception:
            pass

    out = _scan_search(words, roots=roots, clock=clock)
    out["ranked_by"] = "words"
    out["meaning"] = False
    out["index_files"] = 0
    return out


def _index_results(words: str, want: list, ranked: dict, idx: "TextIndex",
                   model, roots: Optional[list] = None) -> dict:
    """Build search()'s answer from a ranking, reading every snippet from the
    file. A file that has gone since it was indexed is left out here and
    dropped by the next reconcile - the index can rank, and only the disk can
    say what a file says. The path from the index is resolved through
    `allowed_path()` AGAIN before it is opened: a file that was a normal note
    when indexed and is a junction to Jarvis's config folder now is refused,
    not read (2026-10-20 parser audit)."""
    roots = folders() if roots is None else roots
    results, read = [], 0
    for hit in ranked["ranked"]:
        if len(results) >= SEARCH_MAX:
            break
        got = allowed_path(str(hit.get("path") or ""), roots)
        if got is None:
            continue
        real = got[0]
        try:
            with open(real, "rb") as f:
                text = f.read(SEARCH_FILE_BYTES).decode("utf-8", "replace")
        except OSError:
            continue
        read += 1
        results.append({"name": display_name(hit["name"]), "path": real,
                        "snippet": _snippet(text, want)})
    why = idx.why if not results and not ranked["ranked"] else ""
    out = {"ok": True, "results": results, "matches": int(ranked["matches"]),
           "files_searched": read, "note": SEARCH_NOTE,
           "ranked_by": ranked["how"], "meaning": bool(ranked["meaning"]),
           "index_files": int(ranked.get("files", 0))}
    if why:
        out["index_why"] = why
    if not results and ranked["ranked"]:
        # Every ranked file had gone by the time its snippet was read: say so
        # rather than answering as if nothing had ever matched.
        out["stopped_early"] = ("the index pointed at files that are no longer there, so "
                                "nothing could be read from them")
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
        # A .docx/.xlsx/.pptx is a ZIP: check its members BEFORE the converter
        # (and its parser) sees it. A 50 MB file can otherwise declare an
        # enormous unpacked size - the zip-bomb half of the 2026-10-20 audit.
        if ext != ".pdf" and zipfile.is_zipfile(real):
            try:
                with zipfile.ZipFile(real) as zf:
                    why = zip_problem(zf, DOC_UNCOMPRESSED_MAX)
            except (zipfile.BadZipFile, OSError):
                why = "it is not a readable Word, Excel or PowerPoint file"
            if why:
                return {"ok": False, "error": f"Jarvis will not open it: {why}"}
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
    tail = "Nothing is changed, and nothing is sent anywhere."
    if action == "read":
        what = f"read part of {args.get('path', '')}"
        if args.get("part"):
            what += f" (part {args.get('part')})"
    elif action == "search":
        what = f"search inside your notes and text files for: {args.get('words', '')}"
        # A search is the one action that writes anything: Jarvis keeps its own
        # word index. Say so on the card, and say where it is.
        tail = ("Nothing of yours is changed, and nothing is sent anywhere. Jarvis keeps its "
                "own word index of the notes and text files it searches, in its settings "
                "folder.")
    else:
        what = f"find files named: {args.get('words', '')}"
    return (f"Jarvis would like to {what} - only in the folders on your list, on this PC. "
            + tail)


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
    why = zip_bomb_problem(zf, EXPORT_UNCOMPRESSED_MAX)
    if why:
        raise ImportRefused(f"Jarvis will not open that export: {why}")
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
                why = zip_bomb_problem(zf, EXPORT_UNCOMPRESSED_MAX)
                if why:
                    raise ImportRefused(f"Jarvis will not open that export: {why}")
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
    global _ARMED, _INDEX, _EMBEDDER, _EMBEDDER_TRIED
    with _P_LOCK:
        _P_STATE["pending"].clear()
        _P_STATE["withdrawn"].clear()
        _P_STATE["last"].clear()
        _P_STATE["latest"].clear()
    with _C_LOCK:
        _CACHE.clear()
    with _INDEX_LOCK:
        _INDEX = None
        _EMBEDDER = None
        _EMBEDDER_TRIED = False
    _READY.clear()
    _ARMED = False


if __name__ == "__main__":
    st = load()
    print(f"  {TITLE}: {len(st['folders'])} listed" + (f" ({st['why']})" if st["why"] else ""))
    for f in st["folders"]:
        print(f"    {f['path']}")
    print(f"  {CONVERTER_READY if converter_ready() else CONVERTER_MISSING}")
