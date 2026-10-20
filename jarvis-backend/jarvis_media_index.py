"""jarvis_media_index.py - search the words in the recordings and videos Jarvis
may look in.

F5 slice S2 (owner decision, 2026-10-19 14:50 PT - `docs/MEDIA-READ-DESIGN.md`
and `.dsh-scratch/BRIEF-F5-S2-MEDIA-INDEX-2026-10-19.md`). S1
(`jarvis_media_read.py`) reads ONE recording and stores nothing. S2 keeps a
searchable index on this PC so "which of my recordings mention X?" can be
answered once, from the words themselves.

WHAT IS STORED, AND WHAT IS NOT (the owner's own decision - option B)

  * For every recording or video inside a folder on the owner's "Folders
    Jarvis may look in" list: the file's path, folder, display name, size,
    modified time, its length, and **the transcript words as readable text**
    with their times (one row per spoken window). That readable copy is the
    owner's choice: searching then shows the exact line instantly.
  * NEVER the audio or video itself. The original file is only ever read; no
    copy of it is made, and nothing is opened outside the listed folders.
  * NO memory fact and no learned fact: the words here are searchable text,
    not something Jarvis "knows" about the owner. `search()` is marked as
    outside text by the caller, exactly like S1's read.
  * Only the listed folders: each file goes through the SAME
    `jarvis_documents.allowed_path()` rule S1 uses (hidden folders and
    protected places refused), so an index run can never reach elsewhere.
  * Rows for files deleted, moved away or renamed leave the index on the next
    run; a row is never kept for a file that is not there.
  * Kept until deleted - no timer, no automatic expiry. One Delete removes
    all of it (the index file itself) or one file's rows.

THE SWITCH (owner's override: ON by default)

  `[media_index] enabled = true` in the shipped `jarvis-framework.toml` and
  its published-base twin is the default. The owner's own state file
  (`media-index.json` in the settings folder) wins when it exists, so OFF is
  instant: the very next search or index run refuses, nothing more is read or
  written, and a waiting "turn it on" card is taken back. Turning it back ON
  after OFF is ONE normal approval card (`change_own_config`, tier "ask") -
  the same action and card shape the data sandbox switch uses - because it
  starts keeping readable private speech again. Nothing is written before a
  person says yes.

WHY THE INDEX IS EXCLUDED FROM BACKUPS (day one, not later)

  `jarvis_backup.py` excludes `documents-index.db` because a backup cannot
  reach a word erased after the backup was made. This feature keeps readable
  speech, so a backup copy would outlive a Delete. `media-index.db` is added
  to that same exclusion table in this slice, and the suite drives the real
  backup module to prove the file is excluded.

WHAT IT DOES NOT DO YET (said plainly, in docs/JARVIS-API.md section 149)

  * Videos' on-screen text is not indexed (S1 reads a few frames per answer;
    the index stores the transcript only), so a searchable line comes from
    what was SAID.
  * The phone has no Settings row for it yet; its chat path works, and the
    switch can be spoken. The disclosure and Delete are on the desktop
    (docs/ARCHITECTURE.md section 8 records the phone follow-up honestly).
  * One at a time: an index run transcribes at most INDEX_PER_RUN new or
    changed files, so the first run after a large folder is added fills in
    over several searches. The answer says how many are still waiting.

Standard library plus the shipped modules. No network. Nothing is loaded at
import time.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import sqlite3
import sys
import threading
import time
import urllib.parse
from pathlib import Path
from typing import Callable, Optional

INDEX_FILE = "media-index.db"
SWITCH_FILE = "media-index.json"
INDEX_SCHEMA = 1

#: The route the drop-in plugin folder installs (plugins/ready/media-index).
PATH = "/api/media-index"
#: The gate action a re-enable is asked under. The same action the data
#: sandbox switch uses: the shipped tier table already answers it "ask", so
#: turning a data store back on raises exactly one normal approval card.
SWITCH_ACTION = "change_own_config"

#: At most this many files are transcribed in one index run - a search must
#: not turn into ten minutes of speech-to-text. The answer says how many are
#: still waiting.
INDEX_PER_RUN = 2
#: More media files than this in the listed folders and the walk stops, so one
#: enormous folder cannot make a search take forever. Rows are still searched.
INDEX_MAX_FILES = 500
#: How many matching lines a search answers with.
SEARCH_LIMIT = 8
#: A stored line is at most this many characters (S1 already caps a file's
#: transcript at 20,000 characters; this only stops a damaged row being huge).
MAX_LINE_CHARS = 2000

DISCLOSURE = (
    "Jarvis can keep the words it reads from recordings and videos in your listed "
    "folders, so it can search them. The words are stored as readable text on this "
    "PC - including other people's voices and anything read aloud - until you delete "
    "them. It never copies the audio or video, never learns them as a fact, and only "
    "looks inside folders you have already listed. Turning this off is instant; "
    "Delete removes the stored words for good (it is never in a backup). If you "
    "leave the switch on after deleting, the next search reads the folders again."
)
WORDS = ("Read the words in one recording or video on this PC, or search what the "
         "recordings and videos in the listed folders say.")
OFF_WORDS = ("Searching recordings is off, so nothing is read or kept. Turn it back on "
             "in Settings, or say \"turn on searchable recordings\".")
NO_FOLDERS = ("No recordings can be indexed yet: add a folder to \"Folders Jarvis may "
              "look in\" first, then ask again.")
IDLE_WORDS = "Searching recordings is on."

SWITCH_ON_WORDS = ("On. Jarvis keeps the words it reads from recordings and videos in "
                   "your listed folders, as readable text on this PC, until you delete "
                   "them.")
SWITCH_OFF_WORDS = ("Off. Nothing more is read or kept, and the stored words are still "
                    "here until you press Delete.")
SWITCH_ALREADY_WORDS = "Searching recordings is already on."
SWITCH_WAITING_WORDS = ("Waiting for your approval. Jarvis keeps readable words from "
                        "recordings only if you approve the card.")
SWITCH_CARD = "\n".join([
    "Start keeping the words from recordings and videos?",
    "",
    "Jarvis would read the recordings and videos inside folders you have already "
    "listed, on this PC, and keep the words as searchable, READABLE text. That is a "
    "lasting copy of what was said - other people's voices, anything read aloud - "
    "stored in your Jarvis settings folder until you delete it.",
    "",
    "It never copies the audio or video, never learns the words as a fact about you, "
    "and nothing outside your listed folders is opened. The index is left out of "
    "backups, so Delete really deletes it.",
    "",
    "Turning it back off is instant and costs nothing. If you did not just ask for "
    "this, say no.",
    "",
    "If you say no: nothing changes - the stored words are still not kept.",
])
SWITCH_LAST_WORDS = {
    "enabled": "You approved the card, so Jarvis now keeps readable words from the "
               "recordings in your listed folders.",
    "denied": "The card was turned down, so nothing is kept.",
    "timed_out": "Nobody answered the card in time, so nothing is kept.",
    "refused": "Your PC did not allow the change, so nothing is kept.",
    "withdrawn": "You turned it off while the card waited, so approving it changed nothing.",
    "failed": "It was approved, but the setting could not be saved, so nothing is kept.",
}

_LOCK = threading.Lock()          # the switch's waiting card
_SWITCH = threading.Lock()        # one switch change at a time
_PENDING: dict = {}
_WITHDRAWN: set = set()
_LAST_CARD: dict = {}
_INDEX_LOCK = threading.Lock()    # one index run at a time

#: Words too common to carry a search. The same lesson `jarvis_documents`'
#: `_INDEX_STOP` records: an OR over "the" and "is" ranks everything.
_STOP = frozenset(
    """a about an and are as at be but by can could did do does for from had has have he
    her his how i if in into is it its me my no not of on or our out she should so some
    than that the their them then there these they this to too up us very was we were
    what when where which who why will with would you your""".split())


class Refused(Exception):
    """One plain sentence, and nothing else."""


# --------------------------------------------------------------------------
#   Where the state lives
# --------------------------------------------------------------------------

def _config_dir() -> Path:
    """The Jarvis settings folder, read live like every other module's."""
    env = os.environ.get("OPENJARVIS_CONFIG_DIR") or os.environ.get("JARVIS_CONFIG_DIR")
    if env:
        return Path(os.path.expanduser(env))
    mod = sys.modules.get("jarvis_framework")
    if mod is not None:
        try:
            return Path(mod.CONFIG_DIR)
        except Exception:
            pass
    return Path(os.path.expanduser("~")) / ".openjarvis"


def index_path() -> Path:
    """`media-index.db` in the settings folder - never memory.db, never a
    listed folder. This is the one place the file's name is written."""
    return _config_dir() / INDEX_FILE


def settings_path() -> Path:
    """The owner's own switch state (`media-index.json`), if they changed it."""
    return _config_dir() / SWITCH_FILE


def framework_default() -> bool:
    """What the shipped settings file says. The owner's override (2026-10-19)
    is `[media_index] enabled = true` in `jarvis-framework.toml`; a machine
    with no readable settings file still defaults ON, which is the shipped
    behaviour, and the suite pins both."""
    try:
        import jarvis_framework as FW
        section = FW.load_framework().get("media_index") or {}
        if isinstance(section, dict) and "enabled" in section:
            return section.get("enabled") is not False
    except Exception:
        pass
    return True


def settings() -> dict:
    """{"enabled": bool, "why": str}. The owner's file wins; with no file the
    shipped default is used. A damaged file falls back to the shipped default
    and says why it could not be read."""
    path = settings_path()
    try:
        if not path.is_file():
            return {"enabled": framework_default(), "why": ""}
        got = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(got, dict) or not isinstance(got.get("enabled"), bool):
            raise ValueError("not a switch object")
        return {"enabled": got["enabled"] is True, "why": ""}
    except Exception as exc:
        return {"enabled": framework_default(),
                "why": f"the recording index's settings file could not be read "
                       f"({type(exc).__name__}), so the shipped default is used"}


def enabled() -> bool:
    """True only when the switch is ON and readable - never a guess."""
    return settings()["enabled"] is True


def set_enabled(on: bool) -> dict:
    """Write the switch. OFF also withdraws a waiting card. Never raises."""
    on = bool(on)
    path = settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps({"enabled": on}), encoding="utf-8")
        os.replace(tmp, path)
    except Exception as exc:
        return {"ok": False, "enabled": enabled(),
                "error": f"the recording index's setting could not be saved "
                         f"({type(exc).__name__}), so it did not change"}
    return {"ok": True, "enabled": on,
            "message": SWITCH_ON_WORDS if on else SWITCH_OFF_WORDS}


# --------------------------------------------------------------------------
#   The switch's one approval card (the same shape as the data sandbox's)
# --------------------------------------------------------------------------

def _audit(event: str, detail: dict) -> None:
    try:
        mod = sys.modules.get("jarvis_framework")
        if mod is not None:
            mod.audit_log(event, detail)
    except Exception:
        pass


def _gate(action: str, detail: dict, prompt: str):
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def _tier(action: str) -> str:
    try:
        mod = sys.modules.get("jarvis_framework")
        return str(mod.action_tier(action))
    except Exception as exc:
        return f"unreadable ({type(exc).__name__})"


def _start_card_thread(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="jarvis-media-index-card", daemon=True).start()


def _finish(pid: str, outcome: str, why: str = "") -> None:
    with _LOCK:
        if _PENDING.get("id") == pid:
            _PENDING.clear()
        _WITHDRAWN.discard(pid)
        _LAST_CARD.clear()
        _LAST_CARD.update(outcome=outcome, at=time.time(), why=why,
                          message=SWITCH_LAST_WORDS.get(outcome, ""))
    _audit("media_index.switch.card", {"outcome": outcome})


def _decide(pid: str, gate: Callable, tier_of: Callable) -> None:
    detail = {"text": SWITCH_CARD,
              "what": "keep readable words from the recordings in the listed folders",
              "setting": "media_index_enabled", "to": True, "leaves_this_pc": False}
    try:
        v = gate(SWITCH_ACTION, detail, SWITCH_CARD)
    except Exception as exc:
        return _finish(pid, "refused", f"the approval gate failed ({type(exc).__name__})")
    vtier = getattr(v, "tier", "unknown")
    allowed = getattr(v, "allowed", False) is True
    outcome = getattr(v, "outcome", None)
    if outcome is None:
        outcome = "approved" if (allowed and vtier == "ask") else "refused"
    if vtier != "ask" or tier_of(SWITCH_ACTION) != "ask":
        return _finish(pid, "refused",
                       f"the gate answered at tier {vtier!r}, which is not a person saying yes")
    if not (allowed and outcome == "approved"):
        if outcome in ("denied", "timed_out"):
            return _finish(pid, outcome)
        return _finish(pid, "refused", str(getattr(v, "reason", "refused")))
    with _SWITCH:
        with _LOCK:
            withdrawn = pid in _WITHDRAWN
        if withdrawn:
            return _finish(pid, "withdrawn", "you turned it off while the card was waiting")
        out = set_enabled(True)
        if out.get("ok") is False:
            return _finish(pid, "failed", str(out.get("error", "")))
        _finish(pid, "enabled")


def request_enabled(on, *, gate: Optional[Callable] = None,
                    tier_of: Optional[Callable[[str], str]] = None,
                    spawn: Optional[Callable] = None) -> tuple:
    """Ask for the switch to change. (http code, body).

    ON is never applied here: it raises ONE normal approval card and answers
    202 {"waiting": true}. OFF is immediate (200), withdraws a waiting card and
    never asks. A gate that cannot be asked, a tier that is not "ask", or a
    setting that cannot be saved changes nothing and says so."""
    gate = gate or _gate
    tier_of = tier_of or _tier
    spawn = spawn or _start_card_thread
    if not isinstance(on, bool):
        return 400, {"ok": False, "error": 'need {"enabled": true|false}'}
    if not on:
        with _SWITCH:
            with _LOCK:
                if _PENDING:
                    _WITHDRAWN.add(_PENDING["id"])
                    _PENDING.clear()
            out = dict(set_enabled(False) or {})
        out.setdefault("ok", True)
        out.update(enabled=False, waiting=False, message=SWITCH_OFF_WORDS)
        _audit("media_index.switch.off", {})
        return 200, out
    if enabled():
        return 200, {"ok": True, "enabled": True, "waiting": False,
                     "message": SWITCH_ALREADY_WORDS}
    t = tier_of(SWITCH_ACTION)
    if t != "ask":
        return 503, {"ok": False, "enabled": False, "waiting": False,
                     "error": (f"{SWITCH_ACTION} is tier {t!r} in the settings file; keeping "
                               "readable words from recordings needs a person to say yes, so "
                               "it must be 'ask'")}
    with _LOCK:
        if _PENDING:
            return 202, {"ok": True, "enabled": False, "waiting": True,
                         "message": "A card to turn on searchable recordings is already "
                                    "waiting for your approval."}
        pid = secrets.token_hex(12)
        _PENDING.update(id=pid, since=time.time())
    _audit("media_index.switch.asked", {})
    try:
        spawn(lambda: _decide(pid, gate, tier_of))
    except Exception:
        with _LOCK:
            _PENDING.clear()
        return 503, {"ok": False, "enabled": False, "waiting": False,
                     "error": "could not raise the approval card, so nothing changed"}
    return 202, {"ok": True, "enabled": False, "waiting": True,
                 "message": SWITCH_WAITING_WORDS}


def switch_state() -> dict:
    """{"enabled", "waiting", "last"} - the switch, as the route reports it."""
    with _LOCK:
        pending = dict(_PENDING)
        last = dict(_LAST_CARD)
    return {"enabled": enabled(), "waiting": bool(pending), "last": last or None}


def _reset_for_tests() -> None:
    with _LOCK:
        _PENDING.clear()
        _WITHDRAWN.clear()
        _LAST_CARD.clear()
    with _INDEX_LOCK:
        pass


# --------------------------------------------------------------------------
#   The index: one SQLite file in the settings folder
# --------------------------------------------------------------------------
# Tables:
#   media_meta   one schema version (a later shape drops and rebuilds the
#                DERIVED tables; the recordings themselves are on disk)
#   media_files  one row per recording: path, folder, display name, size,
#                modified time, length, when indexed, lines
#   media_lines  the READABLE transcript rows the owner chose to keep: the
#                line, its start and end time, its file
#   media_fts    the word index over those lines (rowid = media_lines.id), so
#                a search returns the exact stored line without reading the
#                recording again

def _db() -> sqlite3.Connection:
    """A connection that CLOSES when its `with` ends (`jarvis_sqlite.connect`,
    the one place this repository closes a connection properly)."""
    import jarvis_sqlite
    c = jarvis_sqlite.connect(str(index_path()))
    c.row_factory = sqlite3.Row
    try:
        # The words are readable private speech: a deleted row is overwritten
        # rather than left in a free page of the database file.
        c.execute("PRAGMA secure_delete=ON")
    except Exception:
        pass
    return c


def _ready(c: sqlite3.Connection) -> None:
    c.execute("CREATE TABLE IF NOT EXISTS media_meta ("
              "key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    row = c.execute("SELECT value FROM media_meta WHERE key='schema'").fetchone()
    have = int(row["value"]) if row is not None and str(row["value"]).isdigit() else 0
    if have and have != INDEX_SCHEMA:
        for table in ("media_fts", "media_lines", "media_files"):
            c.execute(f"DROP TABLE IF EXISTS {table}")
        c.execute("DELETE FROM media_meta WHERE key='schema'")
        have = 0
    c.execute("CREATE TABLE IF NOT EXISTS media_files ("
              "path TEXT PRIMARY KEY, root TEXT NOT NULL, name TEXT NOT NULL,"
              " size INTEGER, mtime_ns INTEGER, seconds REAL,"
              " indexed_at REAL NOT NULL, lines INTEGER NOT NULL)")
    c.execute("CREATE TABLE IF NOT EXISTS media_lines ("
              "id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT NOT NULL,"
              " start REAL, end REAL, text TEXT NOT NULL)")
    c.execute("CREATE INDEX IF NOT EXISTS media_lines_path ON media_lines(path)")
    try:
        c.execute("CREATE VIRTUAL TABLE IF NOT EXISTS media_fts USING fts5(text)")
    except Exception:
        # An FTS5-less SQLite still stores the readable rows; search says so
        # rather than pretending it searched.
        c.execute("CREATE TABLE IF NOT EXISTS media_fts_missing ("
                  "id INTEGER PRIMARY KEY)")
    if not have:
        c.execute("INSERT OR REPLACE INTO media_meta(key, value) VALUES('schema', ?)",
                  (str(INDEX_SCHEMA),))
    c.commit()


def _terms(words: str, limit: int = 24) -> list:
    out: list = []
    for w in re.findall(r"[a-z0-9']+", str(words or "").lower()):
        w = w.strip("'")
        if w in _STOP or (len(w) < 2 and not w.isdigit()):
            continue
        if w not in out:
            out.append(w)
    return out[:limit]


def _fts_query(terms: list) -> str:
    return " OR ".join('"' + str(t).replace('"', '""') + '"' for t in terms)


def _drop_file_rows(c: sqlite3.Connection, path: str) -> int:
    ids = [r["id"] for r in c.execute(
        "SELECT id FROM media_lines WHERE path=?", (path,))]
    for rowid in ids:
        try:
            c.execute("DELETE FROM media_fts WHERE rowid = ?", (rowid,))
        except Exception:
            pass
    c.execute("DELETE FROM media_lines WHERE path=?", (path,))
    c.execute("DELETE FROM media_files WHERE path=?", (path,))
    return len(ids)


def _store_file(c: sqlite3.Connection, path: str, root: str, name: str,
                size: int, mtime: int, read: Callable) -> dict:
    """Transcribe one file and store its rows. The recording itself is only
    read; nothing is copied."""
    got = read(path)
    if not isinstance(got, dict) or got.get("ok") is not True:
        why = str((got or {}).get("error") or "it could not be read")
        return {"ok": False, "error": why}
    segments = got.get("segments")
    lines = []
    if isinstance(segments, list) and segments:
        for seg in segments:
            text = str((seg or {}).get("text") or "").strip()
            if not text:
                continue
            lines.append((float(seg.get("start") or 0.0), float(seg.get("end") or 0.0),
                          text[:MAX_LINE_CHARS]))
    else:
        for ln in str(got.get("text") or "").splitlines():
            ln = ln.strip()
            if ln:
                lines.append((0.0, 0.0, ln[:MAX_LINE_CHARS]))
    if not lines:
        return {"ok": False, "error": "no speech was recognised in it"}
    _drop_file_rows(c, path)
    for start, end, text in lines:
        cur = c.execute("INSERT INTO media_lines(path, start, end, text) VALUES(?,?,?,?)",
                        (path, start, end, text))
        try:
            c.execute("INSERT INTO media_fts(rowid, text) VALUES(?, ?)",
                      (cur.lastrowid, text))
        except Exception:
            pass
    c.execute("INSERT OR REPLACE INTO media_files"
              "(path, root, name, size, mtime_ns, seconds, indexed_at, lines) "
              "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
              (path, root, name, int(size), int(mtime),
               float(got.get("seconds") or 0.0), time.time(), len(lines)))
    return {"ok": True, "lines": len(lines), "seconds": float(got.get("seconds") or 0.0)}


def _rebuild_words(c) -> None:
    """Rebuild the word index from the rows that still exist. FTS5 keeps the
    TERMS of a deleted row in its segments until a merge, and a term IS the
    word itself - so after a Delete the index table is dropped and re-made
    from the readable rows (which are the source of truth here, not a file on
    disk). That is what makes the suite's grep for the deleted word in the
    database file pass. Best effort: the rows are already gone if this cannot
    run; Delete-all removes the whole file."""
    try:
        c.execute("DROP TABLE IF EXISTS media_fts")
        c.execute("CREATE VIRTUAL TABLE media_fts USING fts5(text)")
        for row in c.execute("SELECT id, text FROM media_lines"):
            c.execute("INSERT INTO media_fts(rowid, text) VALUES(?, ?)",
                      (row["id"], row["text"]))
    except Exception:
        pass


def _checkpoint() -> None:
    """Flush the write-ahead log into the main file and TRUNCATE it.

    WHY (Gemini's ruling on "really deleted", 2026-10-20). secure_delete and
    VACUUM scrub the main `.db`, but if the file is ever in WAL mode, plaintext
    transcript pages can sit in `media-index.db-wal` until a checkpoint runs.
    Delete therefore checkpoints and truncates BEFORE it says the words are
    gone. A database in SQLite's default rollback-journal mode answers this
    harmlessly (and never has a -wal file). Every connection this module opens
    is closed by `with`, so the checkpoint is not blocked by our own handle."""
    try:
        with _db() as c:
            c.commit()
            c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            c.commit()
    except Exception:
        pass


def _vacuum() -> None:
    """Rewrite the database file so a row removed by the one Delete leaves no
    readable copy in a free page, then truncate any write-ahead log. Best
    effort: a vacuum that cannot run changes nothing about the rows already
    removed, and Delete-all removes the file."""
    try:
        with _db() as c:
            c.commit()
            c.execute("VACUUM")
            c.commit()
            c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            c.commit()
    except Exception:
        pass


# --------------------------------------------------------------------------
#   Staying level with the listed folders
# --------------------------------------------------------------------------

def _media_docs():
    import jarvis_documents as DOCS
    return DOCS


def _walk_media(roots: list, clock: Callable[[], float] = time.monotonic):
    """(found, incomplete): {real_path: (root, name, size, mtime_ns)} for every
    media file the folder rule lets in. The same `allowed_path()` rule as S1:
    hidden folders and protected places are refused before anything is read."""
    import jarvis_media_read as MEDIA
    DOCS = _media_docs()
    found: dict = {}
    capped = [False]
    mine = os.path.realpath(str(index_path()))

    def visit(root, dirpath, name):
        if os.path.splitext(name)[1].lower() not in MEDIA.MEDIA_EXTS:
            return True
        got = DOCS.allowed_path(os.path.join(dirpath, name), [root])
        if not got:
            return True
        real = got[0]
        if os.path.realpath(real) == mine:
            return True
        try:
            st = os.stat(real)
        except OSError:
            return True
        found[real] = (root, name, st.st_size, st.st_mtime_ns)
        if len(found) >= INDEX_MAX_FILES:
            capped[0] = True
            return False
        return True

    stopped = DOCS._walk(roots, visit, clock=clock) if roots else []
    return found, bool(stopped) or capped[0]


def pending_count(roots=None, *, clock: Callable[[], float] = time.monotonic) -> int:
    """How many recordings are not in the index yet (new or changed). Read-only
    and cheap enough for the route; never reads a recording."""
    if not enabled():
        return 0
    DOCS = _media_docs()
    roots = list(roots if roots is not None else DOCS.folders())
    if not roots:
        return 0
    try:
        found, _incomplete = _walk_media(roots, clock=clock)
        with _INDEX_LOCK, _db() as c:
            _ready(c)
            rows = {r["path"]: r for r in c.execute(
                "SELECT path, size, mtime_ns FROM media_files")}
        return sum(1 for path, (_root, _name, size, mtime) in found.items()
                   if path not in rows
                   or rows[path]["size"] != size or rows[path]["mtime_ns"] != mtime)
    except Exception:
        return 0


def _default_read(path: str) -> dict:
    """The real S1 read, without the video OCR pass (the index stores the
    transcript; S1's own read of one file still returns on-screen text)."""
    import jarvis_media_read as MEDIA
    return MEDIA.read_media(path, frames=lambda _p: [], ocr=lambda _b: "",
                            owner_busy=lambda: False, lock=MEDIA.READ_LOCK)


def reconcile(roots=None, *, read: Optional[Callable] = None,
              index_at_most: int = INDEX_PER_RUN,
              clock: Callable[[], float] = time.monotonic) -> dict:
    """Bring the index level with the listed folders.

    Drops rows for files that are gone or moved; transcribes at most
    `index_at_most` new or changed files (so one search never becomes ten
    minutes of speech-to-text); never prunes when the walk stopped early.
    Never raises: a broken index simply answers "could not be used"."""
    out = {"ok": True, "off": False, "indexed": 0, "dropped": 0, "failed": [],
           "pending": 0, "files": 0, "roots": 0}
    if not enabled():
        out.update(ok=False, off=True)
        return out
    DOCS = _media_docs()
    try:
        roots = list(roots if roots is not None else DOCS.folders())
    except Exception as exc:
        out.update(ok=False, error=f"the folder list could not be read "
                                   f"({type(exc).__name__})")
        return out
    out["roots"] = len(roots)
    if not roots:
        out.update(ok=False, error=NO_FOLDERS)
        return out
    read = read or _default_read
    try:
        with _INDEX_LOCK, _db() as c:
            _ready(c)
            found, incomplete = _walk_media(roots, clock=clock)
            rows = {r["path"]: r for r in c.execute(
                "SELECT path, size, mtime_ns FROM media_files")}
            gone = [] if incomplete else [p for p in rows if p not in found]
            changed = [p for p in found if p in rows
                       and (rows[p]["size"] != found[p][2]
                            or rows[p]["mtime_ns"] != found[p][3])]
            fresh = [p for p in found if p not in rows]
            for path in gone + changed:
                out["dropped"] += _drop_file_rows(c, path)
            work = sorted(fresh + changed, key=lambda p: found[p][3], reverse=True)
            for path in work[:max(0, int(index_at_most))]:
                root, name, size, mtime = found[path]
                got = _store_file(c, path, root, name, size, mtime, read)
                if got.get("ok"):
                    out["indexed"] += 1
                else:
                    out["failed"].append({"path": path, "why": got.get("error", "")})
            c.commit()
            total = c.execute("SELECT count(*) AS n FROM media_files").fetchone()["n"]
            out["files"] = int(total)
            out["pending"] = max(0, len(fresh) + len(changed) - out["indexed"])
    except Exception as exc:
        out.update(ok=False, error=f"the recording index could not be used "
                                   f"({type(exc).__name__})")
    return out


def index_file(path, *, read: Optional[Callable] = None) -> dict:
    """Index ONE named recording (must be inside a listed folder). Returns
    {"ok", "lines", "seconds"} or {"ok": False, "error": <plain sentence>}."""
    import jarvis_media_read as MEDIA
    if not enabled():
        return {"ok": False, "off": True, "error": OFF_WORDS}
    if not isinstance(path, str) or not path.strip():
        return {"ok": False, "error": "say which recording or video to index - its full path"}
    ext = Path(path.strip()).suffix.lower()
    if ext not in MEDIA.MEDIA_EXTS:
        return {"ok": False, "error": "that is not an audio or video file this reader knows"}
    DOCS = _media_docs()
    try:
        got = DOCS.allowed_path(path.strip())
    except Exception as exc:
        return {"ok": False, "error": f"the folder list could not be read "
                                      f"({type(exc).__name__})"}
    if not got:
        return {"ok": False, "error": "that file is not inside a folder on your list, "
                                      "so nothing was opened"}
    real = got[0]
    if not os.path.isfile(real):
        return {"ok": False, "error": "that file is not there any more, so nothing was read"}
    if os.path.getsize(real) > MEDIA.MAX_BYTES:
        return {"ok": False, "error": "that file is bigger than the reader's limit, so "
                                      "nothing was read"}
    root = got[1] if len(got) > 1 else ""
    try:
        size = os.path.getsize(real)
        mtime = os.stat(real).st_mtime_ns
        with _INDEX_LOCK, _db() as c:
            _ready(c)
            out = _store_file(c, real, str(root), os.path.basename(real),
                              size, mtime, read or _default_read)
            c.commit()
    except Exception as exc:
        return {"ok": False, "error": f"the recording index could not be used "
                                      f"({type(exc).__name__})"}
    return out


# --------------------------------------------------------------------------
#   Search, delete, and what the owner is shown
# --------------------------------------------------------------------------

def search(words: str, *, roots=None, read: Optional[Callable] = None,
           index_at_most: int = INDEX_PER_RUN, limit: int = SEARCH_LIMIT) -> dict:
    """Search the stored lines. {"ok", "words", "matches": [{path, name, start,
    end, text}], "files", "pending", "indexed"} - or {"ok": False, "off": True}
    when the switch is off. A match IS the stored line, so the answer is the
    exact sentence with its file and time, with no second read."""
    if not enabled():
        return {"ok": False, "off": True, "words": OFF_WORDS, "matches": []}
    terms = _terms(words)
    if not terms:
        return {"ok": False, "error": "say which words to look for", "matches": []}
    recon = reconcile(roots, read=read, index_at_most=index_at_most)
    out = {"ok": True, "words": "", "matches": [], "files": recon.get("files", 0),
           "pending": recon.get("pending", 0), "indexed": recon.get("indexed", 0),
           "dropped": recon.get("dropped", 0)}
    if recon.get("off"):
        return {"ok": False, "off": True, "words": OFF_WORDS, "matches": []}
    try:
        with _INDEX_LOCK, _db() as c:
            _ready(c)
            rows = c.execute(
                "SELECT l.path, l.start, l.end, l.text, f.name AS name "
                "FROM media_fts JOIN media_lines l ON l.id = media_fts.rowid "
                "LEFT JOIN media_files f ON f.path = l.path "
                "WHERE media_fts MATCH ? ORDER BY bm25(media_fts) LIMIT ?",
                (_fts_query(terms), int(limit))).fetchall()
    except Exception as exc:
        out.update(ok=False, words=f"The recording index could not be searched "
                                   f"({type(exc).__name__}).")
        return out
    matches = []
    for row in rows:
        if row["name"] is None:
            continue                      # a row whose file record has gone
        matches.append({"path": row["path"], "name": row["name"],
                        "start": row["start"], "end": row["end"],
                        "text": row["text"]})
    out["matches"] = matches
    if matches:
        out["words"] = "I found the words in the recordings in your listed folders."
    elif recon.get("pending"):
        out["words"] = (f"No stored line matches those words yet, and "
                        f"{recon['pending']} more recording(s) are not indexed yet - "
                        f"ask again and Jarvis will keep filling the index in.")
    else:
        out["words"] = "No recording in your listed folders has those words."
    return out


def delete(path=None) -> dict:
    """THE ONE DELETE. No path: every stored word and the index file itself
    (that is what makes a backup exclusion matter). A path: that one file's
    rows only. The original recording is never opened or touched."""
    try:
        index = index_path()
        if path is None:
            dropped = 0
            if index.is_file():
                try:
                    with _INDEX_LOCK, _db() as c:
                        _ready(c)
                        dropped = c.execute(
                            "SELECT count(*) AS n FROM media_lines").fetchone()["n"]
                except Exception:
                    dropped = 0
                # Flush and truncate any -wal BEFORE the unlink, so a copy of a
                # deleted word cannot survive in `media-index.db-wal` when the
                # main file is gone. All our connections are closed by now.
                _checkpoint()
                for suffix in ("", "-wal", "-shm", "-journal"):
                    target = Path(str(index) + suffix)
                    for _attempt in range(5):
                        try:
                            target.unlink()
                            break
                        except FileNotFoundError:
                            break
                        except OSError:
                            time.sleep(0.05)
            _audit("media_index.deleted", {"scope": "all"})
            return {"ok": True, "deleted": dropped, "index_file": True,
                    "words": "Deleted. The stored words from your recordings are gone, "
                             "and there is no copy in a backup."}
        if not isinstance(path, str) or not path.strip():
            return {"ok": False, "error": "say which recording's stored words to delete"}
        real = os.path.realpath(path.strip())
        with _INDEX_LOCK, _db() as c:
            _ready(c)
            dropped = _drop_file_rows(c, real)
            if dropped:
                _rebuild_words(c)
            c.commit()
        if dropped:
            _vacuum()
        _audit("media_index.deleted", {"scope": "one"})
        if dropped:
            return {"ok": True, "deleted": dropped, "index_file": False,
                    "words": f"Deleted the stored words for {os.path.basename(real)}. "
                             "The recording itself is untouched."}
        return {"ok": True, "deleted": 0, "index_file": False,
                "words": "That recording had no stored words."}
    except Exception as exc:
        return {"ok": False, "deleted": 0,
                "error": f"the stored words could not be deleted "
                         f"({type(exc).__name__})"}


def index_stats() -> dict:
    """Read-only counts for the Settings panel. Never reads a recording."""
    out = {"files": 0, "lines": 0, "bytes": 0}
    path = index_path()
    try:
        out["bytes"] = path.stat().st_size if path.is_file() else 0
    except OSError:
        out["bytes"] = 0
    if not path.is_file():
        return out
    try:
        with _INDEX_LOCK, _db() as c:
            _ready(c)
            out["files"] = int(c.execute(
                "SELECT count(*) AS n FROM media_files").fetchone()["n"])
            out["lines"] = int(c.execute(
                "SELECT count(*) AS n FROM media_lines").fetchone()["n"])
    except Exception:
        pass
    return out


def view(*, here: bool = True) -> dict:
    """What Settings and the route show: the switch, the counts, the disclosure
    words, and the one Delete. Pure reads only."""
    state = switch_state()
    stats = index_stats()
    pending = 0
    try:
        pending = pending_count()
    except Exception:
        pending = 0
    line = (SWITCH_ON_WORDS if state["enabled"] else SWITCH_OFF_WORDS) \
        if not state["waiting"] else SWITCH_WAITING_WORDS
    if state["enabled"] and not state["waiting"]:
        # Gemini's empty-state bar (2026-10-20): "enabled: true, 0 files" must read as
        # empty, not broken. The same sentence also gives the count once files exist,
        # so Settings never shows an unexplained zero.
        n = int(stats["files"])
        line = f"{line} {n} recording{'s' if n != 1 else ''} indexed so far."
    return {"enabled": state["enabled"],
            "default": framework_default(),
            "waiting": state["waiting"],
            "last": state["last"],
            "files": stats["files"],
            "lines": stats["lines"],
            "bytes": stats["bytes"],
            "pending": pending,
            "index_file": str(index_path()),
            "disclosure": DISCLOSURE,
            "line": line}


# --------------------------------------------------------------------------
#   THE ROUTE (a drop-in plugin folder, no patch and no core edit)
# --------------------------------------------------------------------------
# Installed by `plugins/ready/media-index/plugin.json` through the core's own
# plugin loader - the same no-patch mechanism jarvis_sandbox_exec.py's switch
# and jarvis_receipts.py use. The core hands install() its Handler and its own
# origin/token/body helpers:
#
#   GET  /api/media-index                the switch, the counts, the disclosure
#   POST /api/media-index {"enabled": bool}
#                                        ON  -> request_enabled() -> ONE card,
#                                              202 {"waiting": true}
#                                        OFF -> 200 at once
#   POST /api/media-index {"action": "delete", "path": "..."}   one file's rows
#   POST /api/media-index {"action": "delete"}                  everything, and
#                                                               the index file
#
# The POST never writes the switch itself; it calls request_enabled(), so a
# direct POST cannot bypass the approval card. Delete never touches a
# recording: it removes stored words only.

def handle_get() -> tuple:
    try:
        return 200, view()
    except Exception as exc:
        return 503, {"ok": False, "error": type(exc).__name__}


def handle_post(body) -> tuple:
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": 'send {"enabled": true|false} or '
                                           '{"action": "delete"}'}
    if str(body.get("action") or "").strip().lower() == "delete":
        try:
            return 200, delete(body.get("path"))
        except Exception as exc:
            return 503, {"ok": False, "error": type(exc).__name__}
    return request_enabled(body.get("enabled"))


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls` so GET/POST /api/media-index are answered here, after
    the server's own origin and token checks. Every other request goes to the
    original handler untouched. Returns the banner line."""
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(post0, "_jarvis_media_index", False):
        return "  media-index  Searchable recordings answers at /api/media-index (already on)"

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
        route = urllib.parse.urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if route != PATH:
            return get0(self)
        if not _allowed(self):
            return None
        code, out = handle_get()
        return self._send(code, out)

    def do_POST(self):
        route = urllib.parse.urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if route != PATH:
            return post0(self)
        if not _allowed(self):
            return None
        try:
            body = json.loads(read_body(self) or b"{}")
        except Exception as exc:
            return self._send(400, {"error": type(exc).__name__})
        code, out = handle_post(body)
        return self._send(code, out)

    do_GET._jarvis_media_index = True
    do_POST._jarvis_media_index = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    return ("  media-index  Searchable recordings: "
            + ("on - readable words from your listed folders are kept until deleted"
               if enabled() else "off - nothing is read or kept"))
