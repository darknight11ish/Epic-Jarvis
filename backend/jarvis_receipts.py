"""jarvis_receipts.py - a receipt for every action that changed something, and one button to put it back.

WHY THIS EXISTS

Every other record in this backend says what Jarvis was ALLOWED to do
(`approvals.db`, `jarvis_gate.py`) or what was SAID (`chat-history.db`,
`jarvis_chat_log.py`). Nothing said what an action actually CHANGED - so an
action that was allowed, ran, and turned out to be wrong left the owner with
no way back except doing the opposite by hand, if they could remember what it
was. The idea is borrowed from BasedHardware/omi: an action that changes
something leaves a receipt saying what changed, with one button to put it
back.

WHAT IT IS

One table, in a database of its own:

    action_receipts
        receipt_id            TEXT PRIMARY KEY   ("rc" + 12 hex)
        created_at            REAL               when the change was made
        tool_name             TEXT               which action changed it
        summary               TEXT               what changed, in plain words
        before_snapshot_json  TEXT               enough to put it back (JSON)
        after_snapshot_json   TEXT               what it looks like now (JSON)
        undo_callable         TEXT               the code that can put it back, BY NAME
        undone_at             REAL               when Undo really ran, or NULL

WHY ITS OWN FILE, AND NOT A TABLE IN `approvals.db`

`approvals.db` is one of the nine files `jarvis_gate.py` refuses to let any
tool modify, precisely because the approval stamp lives in it. A receipt is
written by the same call path as the action it records, so putting receipts
in there would hand every recorded action a write path into the file the gate
trusts. The house pattern for a module's own records is its own SQLite file
beside `goals.db` and `schedule.db` - `receipts.db` in the same settings
folder, `JARVIS_RECEIPTS_DB` overriding it for the tests - opened per call,
WAL, with a busy timeout, exactly as `jarvis_chat_log.py` and `jarvis_gate.py`
do it.

THE API

    record(tool_name, summary, *, before=None, after=None, undo=None) -> str
        Write one row, before the change is made, and return its id. `undo`
        is a zero-argument callable that reverses the change; `before` and
        `after` are JSON-serialisable snapshots.

    undo(receipt_id) -> dict
        Reverse that one action, exactly once. Idempotent: a second call
        refuses in plain words ("this was already undone") and applies
        nothing. `undone_at` is set only when the reversal really ran.

    recent(limit=20) -> list      what the apps would show, newest first
    get(receipt_id) -> dict|None  one receipt, or None
    register_restorer(tool_name, fn)
        The code that can put a `tool_name` change back FROM ITS BEFORE
        SNAPSHOT, `fn(before) -> None`. A module that records receipts calls
        this once, at import (jarvis_goals.py does).

TWO WAYS BACK, AND WHICH ONE RAN IS SAID OUT LOUD

1. **The callable, while the process is alive.** `record(undo=...)` keeps the
   zero-argument callable in a small in-memory table, keyed by receipt id. It
   is the exact code that made the change, so it is preferred.
2. **The before snapshot, after a restart.** A new process has no in-memory
   callable - that is the normal case, not an error. Then the store looks up
   the RESTORER registered for this `tool_name`, imports the module the row's
   `undo_callable` names if that is needed to register it, and calls it with
   the parsed before snapshot. Both paths say which one they took
   (`"path": "callable"` or `"path": "snapshot"`).
3. **Neither.** The store refuses, in plain words, rather than pretending:
   the code that changed it is not running and the before snapshot is not
   enough on its own. `undone_at` stays NULL, so it can be tried again.

EXACTLY ONCE, INCLUDING UNDER TWO CALLERS AT THE SAME TIME

The idempotence is a claim in the database, not a check in a variable:
`undone_at` is claimed with one conditional UPDATE
(`... WHERE receipt_id=? AND undone_at IS NULL`) BEFORE the reversal runs, and
only the caller whose UPDATE changed a row goes on to reverse anything. A
second call - a double tap, two app screens, a retry - finds the row already
claimed and is refused with "this was already undone". If the reversal itself
fails, the claim is released and the reason is returned, so a receipt is
never left marked undone when nothing was put back. The one honest gap: a
process killed between the claim and the reversal leaves it marked undone and
it will not be applied again. Said here rather than left implicit.

IT NEVER RAISES INTO THE CALLER, AND NEVER WRITES A SECRET

`record()` is called from inside other modules' actions. A receipt that cannot
be written must not fail the action it was recording, so every function here
returns a plain value ("" / a dict with `"ok": False` / [] / None) instead of
raising, and a failure is audit-logged by name only.

Nothing here is written before the project's own scrubber has been over it:
`jarvis_scrub.scrub_text` cleans the summary and every string in both
snapshots, so a key, a token or a password that happened to be in the words an
action changed lands as `[redacted: ...]` and never as itself. **No scrubber,
nothing written** - the same rule chat history follows when it has no key:
`record()` returns "" rather than storing unscrubbed words. Snapshots are
capped; one too large to keep is replaced by a plain note saying so, so
`schema`-shaped guessing never happens and Undo refuses rather than restoring
half a row.

THE ROUTES (installed by install(), below - the drop-in folder's own call)

    GET  /api/receipts                    the recent list. A read.
    POST /api/receipts/<receipt_id>/undo   undo one action.

The list accepts `?app_locked=1` / `?hide_memory_lists=1` (Q1, 2026-10-20):
the desktop passes its own state there, the answer is the honest "Hidden while
App lock is on." / hidden-lists sentence with NO rows, and `recent()` is never
called. The two flags can only ADD withholding - a `0` is not an unlock key,
and the merge (jarvis_private_view) can never lower the trusted live state.
Until the live HUD passes the state, the apps keep hiding the drawer themselves.

Undo is a mutating action, so it is put to the ONE permission model like
everything else that changes something: ONE card, action `undo_action`, and
the reversal runs only on the gate's own answer. A denied or timed-out card
changes nothing at all. The id is checked, and the receipt's own state read,
BEFORE any card is raised - so no card is ever raised for a receipt that
cannot be undone - and one card is raised at a time.

WHICH TIER, AND WHY THIS MODULE DOES NOT DECIDE IT

The tier comes from the owner's own settings file, read by `jarvis_gate`.
`undo_action` has a line of its own there - `"ask"`, one card per undo, which is
what this feature is for. It was a fall-through until 2026-10-16: with no line
it took `unknown_action_tier`, which the shipped file also sets to "ask", so the
card is the same one either way and the line only pins it. That is why the line
exists rather than being left out: a fall-through depends on a setting that can
be loosened later, and a name with no line anywhere is what `test_gate_names.py`
reports as an action the gate cannot resolve.

This module does NOT read that table itself and does not force the tier, and
that is deliberate rather than an omission. `jarvis_gate.py` carries a list,
`_NO_RULE_FROM_DENIAL`, of the actions where a "no" must not become a proposed
standing rule - actions that ALWAYS ask and that the owner started with a
button, for which "I do not want Jarvis to X without asking me first" says
nothing. `backend/test_gate_denial_rule.py` reads every module that refuses to
act on any tier but "ask" and requires its action to be on that list. Joining
that list means editing `jarvis_gate.py`, which is one of the files this
feature is forbidden to touch (and a patch is the thing the drop-in folder
exists to avoid). So this module takes the tier the gate gives it, exactly as
`jarvis_media.py`, `jarvis_news.py` and the rest do, and the tier table is the
single policy - one reader, not two. In the shipped configuration that is
"ask", one card, as above. It also keeps the one rule that is easy to get
wrong: at tier "ask", only an outcome of "approved" counts as a yes, because
`check()` returns `allowed=True` on tier "notify" too with nobody in the loop.

The two routes need no patch at all: `plugins/ready/receipts/` names this
module in its `plugin.json`, and `jarvis_plugins.py` calls `install()` with
the core's own Handler and its own three checks, exactly as the patch it
replaces would have.
"""
from __future__ import annotations

import importlib
import json
import os
import re
import sqlite3
import sys
import threading
import time
import uuid
from contextlib import closing
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import parse_qs, urlsplit

try:                                            # the owner's own module
    import jarvis_framework as fw
except Exception:                               # pragma: no cover - CI has it
    fw = None  # type: ignore

# --------------------------------------------------------------------------
#   Numbers and words
# --------------------------------------------------------------------------

#: The settings folder, and its own file. `JARVIS_RECEIPTS_DB` overrides the
#: file (the tests use a scratch one; the same shape as JARVIS_GOALS_DB).
DB_ENV = "JARVIS_RECEIPTS_DB"
DB_NAME = "receipts.db"

#: One snapshot may add up to this many characters of JSON. A bigger one is
#: NOT truncated - half a row is worse than none - it is replaced by a plain
#: note, and Undo then refuses instead of putting back part of a change.
MAX_SNAPSHOT = 8000
MAX_SUMMARY = 500
MAX_TOOL = 80
#: How many receipts one list may ask for, and how many live undo callables
#: are held at once (the oldest is dropped; its snapshot path still works).
MAX_LIMIT = 200
DEFAULT_LIMIT = 20
MAX_CALLABLES = 200

#: Retention (2026-10-18, audit DATA D5). A receipt holds the owner's words
#: about what changed (scrubbed of secrets, not of private words), so an
#: uncapped file would keep them for ever. Newest `MAX_ROWS` and nothing older
#: than `KEEP_DAYS` are kept; the sweep runs on the write path so a receipt
#: never waits for a separate job. Sized for a year of ordinary use: 90 days
#: is the audit log's own window, and 5,000 actions is far above real days.
KEEP_DAYS = 90
MAX_ROWS = 5000

#: What a purged word becomes in a receipt: a fixed marker, never a hash -
#: a hash of a guessable name would be a way back to the words.
FORGOTTEN = "[forgotten]"

#: The gate action this module asks under. Deliberately NOT in jarvis_gate.py's
#: `_RISK` table, and deliberately not given a row by this feature: adding one
#: means patching the gate, and the drop-in folder exists so a new route needs
#: no patch. An unclassified action is treated as risky and irreversible by
#: the gate's own fail-closed rule (Windows Hello on the PC, the screen lock
#: on the phone, a heavy card) - stricter than the action it undoes, which is
#: the safe direction to be wrong in.
#:
#: It also has a line of its own in the shipped `[autonomy.tiers]` - "ask", one
#: card per undo (2026-10-16). With no line it took `unknown_action_tier`, which
#: the same file sets to "ask", so the card is unchanged; the line pins it. The
#: module still must not force the tier itself (see this file's docstring, "WHICH
#: TIER, AND WHY THIS MODULE DOES NOT DECIDE IT") - the line is the settings
#: file's decision, and the gate is the one reader that acts on it.
UNDO_ACTION = "undo_action"

LIST_PATH = "/api/receipts"
_ROUTE = re.compile(r"^/api/receipts/([A-Za-z0-9_-]{4,64})/undo$")
_ID = re.compile(r"^[A-Za-z0-9_-]{4,64}$")
PATHS = (LIST_PATH,)

WORDS = {
    "already": "this was already undone",
    "unknown": "no receipt with that id",
    "callable": "Put back by the same code that changed it.",
    "snapshot": ("The code that made this change is not running in this process, so it was "
                 "put back from the receipt's own before snapshot."),
    "no_path": ("The code that made this change is not running in this process, and the "
                "before snapshot on its own is not enough to put it back. Nothing was "
                "changed."),
    "denied": "The card was turned down, so nothing was put back.",
    "timed_out": "Nobody answered the card in time, so nothing was put back.",
    "refused": "The card could not be raised, so nothing was put back.",
    "failed": "The card was approved, but putting it back failed, so the change is still there.",
    "undone": "Approved. The change was put back.",
}

#: Fixed card words. No emoji, no "!", and the last line is what refusing
#: costs - the one thing a permission request must never leave out.
CARD_HEAD = "Put back a change Jarvis made?"
CARD_TAIL = ("If you say no, nothing changes: this stays exactly as it is now.")
CARD_NOTE = ("Undo puts back the receipt's own before snapshot - what the thing looked like "
             "before the change, captured at the moment it was made. Nothing else is touched.")

SCHEMA = """
CREATE TABLE IF NOT EXISTS action_receipts (
    receipt_id           TEXT PRIMARY KEY,
    created_at           REAL NOT NULL,
    tool_name            TEXT NOT NULL,
    summary              TEXT NOT NULL DEFAULT '',
    before_snapshot_json TEXT,
    after_snapshot_json  TEXT,
    undo_callable        TEXT NOT NULL DEFAULT '',
    undone_at            REAL
);
CREATE INDEX IF NOT EXISTS ix_receipts_created ON action_receipts (created_at DESC);
"""

# --------------------------------------------------------------------------
#   Where
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


def db_path() -> Path:
    env = os.environ.get(DB_ENV)
    return Path(env) if env else _config_dir() / DB_NAME


def _connect() -> sqlite3.Connection:
    """Always `with closing(_connect()) as c:` - never `with _connect() as c:`.

    That distinction is jarvis_gate._connect's own, and it cost real handles
    there: `with sqlite3.connect(...)` commits, it does not close, and on
    Windows the unclosed handles hold locks on the -wal file. One connection
    per call, closed by the caller, is what this project does.
    """
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    # WAL so a read (the apps' list) never blocks a write (a receipt), and the
    # busy timeout so two actions finishing together wait rather than fail.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    # Deleted words must not come back out of free pages: a receipt is deleted
    # by the sweep below and by purge_words(), and both are about text leaving.
    conn.execute("PRAGMA secure_delete=ON")
    conn.executescript(SCHEMA)
    return conn


def _sweep(c) -> int:
    """Apply the retention caps on the write path. Returns rows removed."""
    now = time.time()
    try:
        removed = c.execute("DELETE FROM action_receipts WHERE created_at < ?",
                            (now - KEEP_DAYS * 86400,)).rowcount or 0
        removed += c.execute(
            "DELETE FROM action_receipts WHERE receipt_id NOT IN ("
            " SELECT receipt_id FROM action_receipts ORDER BY created_at DESC LIMIT ?)",
            (int(MAX_ROWS),)).rowcount or 0
    except sqlite3.Error:
        return 0
    if removed:
        # VACUUM cannot run inside a transaction; isolation_level=None means
        # there is none pending here. A VACUUM that fails is not a failure of
        # the receipt - the rows are already gone.
        try:
            c.execute("VACUUM")
        except sqlite3.Error:
            pass
    return removed


# --------------------------------------------------------------------------
#   Never write a secret
# --------------------------------------------------------------------------


def _scrubber():
    """jarvis_scrub, or None. Fails CLOSED: no scrubber, nothing recorded."""
    try:
        import jarvis_scrub
        return jarvis_scrub
    except Exception:
        return None


def _clean(value: Any, scrub) -> Any:
    """`value` with every string - keys included - scrubbed, still JSON-shaped.

    The scrubber works on text, and json.dumps() of a whole object would let a
    redaction land inside the JSON grammar, so each string is scrubbed and the
    object is then dumped. Non-JSON leaves are stringified and scrubbed too:
    a snapshot is never a place to smuggle an object through.
    """
    if isinstance(value, str):
        return scrub.scrub_text(value)
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, dict):
        return {_clean(k, scrub): _clean(v, scrub) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_clean(v, scrub) for v in value]
    if isinstance(value, (bytes, bytearray)):
        return scrub.scrub_text(bytes(value))
    return scrub.scrub_text(str(value))


#: The marker that says "this snapshot was not kept" - one key nothing a
#: caller would choose by accident, so a real snapshot can never be mistaken
#: for it and restored as if it were whole.
_TOO_BIG = "_receipts_snapshot"


def _snapshot(value: Any, scrub) -> Optional[str]:
    """The JSON text for one snapshot, or None when there is none.

    A snapshot that will not serialise is dropped (a receipt without one is
    still a receipt), and a snapshot over MAX_SNAPSHOT is replaced by a plain
    note saying so: Undo reads that note as "not enough to restore" and
    refuses, rather than putting back the half of a change that fitted.
    """
    if value is None:
        return None
    try:
        text = json.dumps(_clean(value, scrub), ensure_ascii=False, default=str,
                          sort_keys=True, separators=(",", ":"))
    except Exception:
        return None
    if len(text) > MAX_SNAPSHOT:
        return json.dumps({_TOO_BIG: "too large to keep", "characters": len(text),
                           "note": "this snapshot was not kept, so Undo cannot use it"},
                          sort_keys=True, separators=(",", ":"))
    return text


def _parsed(text: Any) -> Any:
    if not isinstance(text, str) or not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        return None


def _usable_snapshot(text: Any) -> bool:
    """Is this snapshot a real record, or the "too large" note?"""
    got = _parsed(text)
    return got is not None and not (isinstance(got, dict) and _TOO_BIG in got)


# --------------------------------------------------------------------------
#   The live tables: in-memory only, gone with the process
# --------------------------------------------------------------------------

_LOCK = threading.Lock()
#: receipt id -> the zero-argument callable that reverses that change. Bounded;
#: the oldest is dropped. Dropping one is harmless: that receipt falls back to
#: its before snapshot.
_CALLABLES: dict = {}
#: tool_name -> the function that can put that kind of change back FROM its
#: before snapshot. Registered by the module that owns the change, at import.
_RESTORERS: dict = {}
_STATE: dict = {"pending": None, "last": None}


def _audit(event: str, detail: dict) -> None:
    """The project's audit log, by name only. Never raises, never blocks."""
    try:
        if fw is not None:
            fw.audit_log(event, detail)
    except Exception:
        pass


def _name(value: Any, limit: int) -> str:
    try:
        text = str(value or "").strip()
    except Exception:
        return ""
    return text[:limit]


# --------------------------------------------------------------------------
#   record
# --------------------------------------------------------------------------


def _label(fn: Any) -> str:
    """An importable name for a callable, or "".

    Only `module.qualname` where the qualname is a real module-level name: a
    closure or a lambda (`...<locals>...`) cannot be found again in a new
    process, and saying it can would be a lie the Undo button then repeats.
    """
    module = getattr(fn, "__module__", "") or ""
    qual = getattr(fn, "__qualname__", "") or ""
    if not module or not qual or "<locals>" in qual or "<lambda>" in qual:
        return ""
    return f"{module}.{qual}"[:120]


def register_restorer(tool_name: str, fn: Callable[[Any], None]) -> bool:
    """Say how a `tool_name` change is put back from its before snapshot.

    Called once at import by the module that owns the change: it is the only
    way the snapshot path can work at all after a restart, because the
    in-memory callable is gone by definition. Never raises."""
    try:
        name = _name(tool_name, MAX_TOOL)
        if not name or not callable(fn):
            return False
        with _LOCK:
            _RESTORERS[name] = fn
        return True
    except Exception:
        return False


def record(tool_name: str, summary: str, *, before: Any = None, after: Any = None,
           undo: Optional[Callable[[], None]] = None) -> str:
    """Write one receipt and return its id. "" when it could not be written.

    Called BEFORE the change is made, so the receipt exists even if the change
    then fails half way. Never raises, never writes an unscrubbed word, and
    never writes anything at all without the project's scrubber."""
    try:
        name = _name(tool_name, MAX_TOOL)
        if not name:
            return ""
        scrub = _scrubber()
        if scrub is None:
            # Chat history's own rule ("no key, nothing is recorded"), applied
            # to words rather than to a database: better no receipt than one
            # holding a key it could not check.
            _audit("receipts.withheld", {"tool_name": name, "why": "no scrubber"})
            return ""
        restorer = _RESTORERS.get(name)
        # uuid4, like every other id in this backend, and NOT os.urandom: the
        # contract fixtures are built by driving the real modules with `uuid`
        # stood in for (tools/gen_projects_cases.py's `_Counted`), and a
        # receipt id that came from anywhere else could never be reproduced.
        receipt_id = "rc" + uuid.uuid4().hex[:12]
        clean_summary = scrub.scrub_text(str(summary or ""))[:MAX_SUMMARY]
        before_json = _snapshot(before, scrub)
        after_json = _snapshot(after, scrub)
        label = _label(restorer) or _label(undo)
        with closing(_connect()) as c:
            c.execute(
                "INSERT INTO action_receipts (receipt_id, created_at, tool_name, summary,"
                " before_snapshot_json, after_snapshot_json, undo_callable, undone_at)"
                " VALUES (?,?,?,?,?,?,?,NULL)",
                (receipt_id, time.time(), name, clean_summary, before_json, after_json, label))
            _sweep(c)
        if callable(undo):
            with _LOCK:
                _CALLABLES[receipt_id] = undo
                while len(_CALLABLES) > MAX_CALLABLES:
                    _CALLABLES.pop(next(iter(_CALLABLES)), None)
        return receipt_id
    except Exception as exc:
        # A receipt that cannot be written must never fail the action it was
        # recording. Named, never quoted.
        _audit("receipts.record_failed", {"tool_name": _name(tool_name, MAX_TOOL),
                                          "error": type(exc).__name__})
        return ""


def discard(receipt_id: str) -> bool:
    """Remove one receipt whose action then DID NOT happen. True when removed.

    The one caller is the file guardian's restore path (2026-10-18): it records
    the receipt BEFORE the write, as the project's rule says, and if the write
    itself then fails there must be no receipt claiming a restore that never
    happened. This is the narrow, deliberately-loud counterweight to `record()`:
    it never touches an undone or already-used row, it drops the live Undo
    callable at the same time, and its only observable effect is that the row
    is gone (it is not an "undo": nothing is put back). Never raises.
    """
    try:
        rid = _name(receipt_id, 64)
        if not _ID.match(rid):
            return False
        with _LOCK:
            _CALLABLES.pop(rid, None)
        with closing(_connect()) as c:
            cur = c.execute(
                "DELETE FROM action_receipts WHERE receipt_id = ? AND undone_at IS NULL",
                (rid,))
            removed = cur.rowcount == 1
        if removed:
            _audit("receipts.discarded", {"receipt_id": rid})
        return removed
    except Exception as exc:
        _audit("receipts.discard_failed", {"error": type(exc).__name__})
        return False


def purge_words(text) -> int:
    """Scrub one forgotten thing's words out of every receipt. Returns rows changed.

    A receipt records what a tool was given: a summary and two small before/
    after snapshots, all scrubbed of SECRETS at write time - but a private word
    a tool was asked to write is not a secret shape, so it could sit there. When
    the owner forgets a fact (or an erased conversation's own words), the memory
    and chat stores call this so the words cannot reappear from a receipt. It is
    a plain, case-insensitive replacement with the fixed `[forgotten]` marker -
    never a hash, because a hash of a guessable name is a way back. Best effort
    by design: no scrubber, no key, no database, or a word that spans a JSON
    escape leaves the row as it was rather than raising into the caller."""
    needle = " ".join(str(text or "").split())
    if not needle:
        return 0
    pat = re.compile(re.escape(needle), re.I)
    changed = 0
    try:
        with closing(_connect()) as c:
            rows = c.execute(
                "SELECT receipt_id, summary, before_snapshot_json, after_snapshot_json"
                " FROM action_receipts").fetchall()
            for row in rows:
                summary = str(row["summary"] or "")
                before = row["before_snapshot_json"]
                after = row["after_snapshot_json"]
                new_summary = pat.sub(FORGOTTEN, summary)
                new_before = pat.sub(FORGOTTEN, str(before)) if before else before
                new_after = pat.sub(FORGOTTEN, str(after)) if after else after
                if new_summary == summary and new_before == before and new_after == after:
                    continue
                c.execute("UPDATE action_receipts SET summary=?, before_snapshot_json=?,"
                          " after_snapshot_json=? WHERE receipt_id=?",
                          (new_summary, new_before, new_after, row["receipt_id"]))
                changed += 1
            if changed:
                try:
                    c.execute("VACUUM")     # no transaction is pending here
                except sqlite3.Error:
                    pass
    except Exception:
        return 0
    return changed


# --------------------------------------------------------------------------
#   Reading
# --------------------------------------------------------------------------


def _row_out(row) -> dict:
    """One row as the apps read it: the snapshots parsed, no key ever empty."""
    try:
        return {
            "receipt_id": str(row["receipt_id"]),
            "created_at": float(row["created_at"] or 0.0),
            "tool_name": str(row["tool_name"] or ""),
            "summary": str(row["summary"] or ""),
            "before": _parsed(row["before_snapshot_json"]),
            "after": _parsed(row["after_snapshot_json"]),
            "has_before": _usable_snapshot(row["before_snapshot_json"]),
            "undo_callable": str(row["undo_callable"] or ""),
            "undone_at": (None if row["undone_at"] is None else float(row["undone_at"])),
            "undone": row["undone_at"] is not None,
        }
    except Exception as exc:                    # pragma: no cover - bad row
        return {"receipt_id": "", "tool_name": "", "summary": "",
                "before": None, "after": None, "has_before": False,
                "undo_callable": "", "created_at": 0.0, "undone_at": None,
                "undone": False, "error": type(exc).__name__}


def get(receipt_id: str) -> Optional[dict]:
    """One receipt, or None. Never raises."""
    try:
        rid = _name(receipt_id, 64)
        if not _ID.match(rid):
            return None
        with closing(_connect()) as c:
            row = c.execute("SELECT * FROM action_receipts WHERE receipt_id = ?",
                            (rid,)).fetchone()
        return _row_out(row) if row is not None else None
    except Exception as exc:
        _audit("receipts.read_failed", {"error": type(exc).__name__})
        return None


def recent(limit: int = DEFAULT_LIMIT) -> list:
    """The newest receipts first - what the apps would show. Never raises."""
    try:
        n = int(limit)
    except Exception:
        n = DEFAULT_LIMIT
    n = max(1, min(MAX_LIMIT, n))
    try:
        with closing(_connect()) as c:
            rows = c.execute("SELECT * FROM action_receipts ORDER BY created_at DESC,"
                             " receipt_id DESC LIMIT ?", (n,)).fetchall()
        return [_row_out(r) for r in rows]
    except Exception as exc:
        _audit("receipts.read_failed", {"error": type(exc).__name__})
        return []


def is_undoable(receipt: Optional[dict]) -> bool:
    """Could this receipt be put back at all - in THIS process, right now?

    True when the live callable is still held, or when a restorer for its
    tool_name is registered and its before snapshot is a real one. The list
    route uses it so the apps never offer a button that can only refuse.
    """
    try:
        if not receipt or receipt.get("undone") or not receipt.get("receipt_id"):
            return False
        rid = receipt["receipt_id"]
        with _LOCK:
            if callable(_CALLABLES.get(rid)):
                return True
        return (callable(_RESTORERS.get(receipt.get("tool_name", "")))
                and bool(receipt.get("has_before")))
    except Exception:
        return False


# --------------------------------------------------------------------------
#   undo - exactly once
# --------------------------------------------------------------------------


def _claim(receipt_id: str) -> bool:
    """Take this receipt's undo, or find it already taken.

    One conditional UPDATE is the whole of the idempotence: exactly one caller
    can change the row, and only that caller goes on to reverse anything."""
    try:
        now = time.time()
        with closing(_connect()) as c:
            cur = c.execute("UPDATE action_receipts SET undone_at = ?"
                            " WHERE receipt_id = ? AND undone_at IS NULL", (now, receipt_id))
            return cur.rowcount == 1
    except Exception as exc:
        _audit("receipts.claim_failed", {"error": type(exc).__name__})
        return False


def _release(receipt_id: str) -> None:
    """The reversal failed: give the claim back, so it can be tried again."""
    try:
        with closing(_connect()) as c:
            c.execute("UPDATE action_receipts SET undone_at = NULL WHERE receipt_id = ?",
                      (receipt_id,))
    except Exception:
        pass


def _restorer_for(tool_name: str, label: str):
    """The snapshot-path restorer for this kind of change, or None.

    A restorer registers itself when its module is imported, and `record()`
    writes that module's name into the row (`undo_callable`). A new process
    therefore finds it two ways, in this order: the registry, when the module
    has already been imported here; or the name itself - `module.function` -
    looked up in that module, importing it when it is a `jarvis_` module and
    not already loaded, which is also what runs its register_restorer() again.
    Only a `jarvis_` module is ever imported, and only a name this file wrote."""
    fn = _RESTORERS.get(tool_name)
    if callable(fn):
        return fn
    module_name, _, func_name = str(label or "").partition(".")
    if not re.match(r"^jarvis_[a-z0-9_]+$", module_name) or not func_name:
        return None
    module = sys.modules.get(module_name)
    if module is None:
        try:
            module = importlib.import_module(module_name)
        except Exception:
            return None
    fn = getattr(module, func_name, None)
    if callable(fn):
        return fn
    return _RESTORERS.get(tool_name)


def undo(receipt_id: str) -> dict:
    """Put back exactly what that receipt recorded. Never raises.

    Returns {"ok", "path", "words"|"error", "receipt_id", ...}. `ok` is True
    only when the reversal really ran and `undone_at` was recorded; a second
    call for the same receipt refuses - "this was already undone" - and
    applies nothing."""
    try:
        rid = _name(receipt_id, 64)
        row = get(rid)
        if row is None:
            return {"ok": False, "receipt_id": rid, "path": "none",
                    "error": WORDS["unknown"]}
        if row.get("undone"):
            return {"ok": False, "receipt_id": rid, "path": "none",
                    "already_undone": True, "undone_at": row.get("undone_at"),
                    "error": WORDS["already"]}
        if not _claim(rid):
            # Another caller claimed it between the read and the claim.
            return {"ok": False, "receipt_id": rid, "path": "none",
                    "already_undone": True, "error": WORDS["already"]}
        with _LOCK:
            fn = _CALLABLES.pop(rid, None)
        if callable(fn):
            try:
                fn()
            except Exception as exc:
                _release(rid)
                return {"ok": False, "receipt_id": rid, "path": "callable",
                        "error": f"putting it back failed ({type(exc).__name__})"}
            return {"ok": True, "receipt_id": rid, "path": "callable",
                    "words": WORDS["callable"], "tool_name": row.get("tool_name", "")}
        # A new process: the callable is gone by definition. The before
        # snapshot, through the restorer that knows how to apply it.
        before = row.get("before")
        restore = (_restorer_for(row.get("tool_name", ""), row.get("undo_callable", ""))
                   if (row.get("has_before") and before is not None) else None)
        if callable(restore):
            try:
                restore(before)
            except Exception as exc:
                _release(rid)
                return {"ok": False, "receipt_id": rid, "path": "snapshot",
                        "error": f"putting it back failed ({type(exc).__name__})"}
            return {"ok": True, "receipt_id": rid, "path": "snapshot",
                    "words": WORDS["snapshot"], "tool_name": row.get("tool_name", "")}
        _release(rid)
        return {"ok": False, "receipt_id": rid, "path": "none", "error": WORDS["no_path"],
                "tool_name": row.get("tool_name", "")}
    except Exception as exc:
        return {"ok": False, "receipt_id": _name(receipt_id, 64), "path": "none",
                "error": type(exc).__name__}


# --------------------------------------------------------------------------
#   The routes
# --------------------------------------------------------------------------


def _query(query: str) -> dict:
    try:
        return {k: v[0] for k, v in parse_qs(query or "", keep_blank_values=True).items() if v}
    except Exception:
        return {}


def _tier(action: str) -> str:
    """The tier the owner's own settings file gives this action, read now.

    **For the list route to report, and for nothing else.** This module does
    not decide the tier and does not refuse on it - `jarvis_gate` is the one
    reader that decides (see the file's docstring, "WHICH TIER, AND WHY THIS
    MODULE DOES NOT DECIDE IT"). What an app reads here is whether tapping
    Undo will put a card up, which in the shipped configuration it will:
    `[autonomy.tiers]` gives `undo_action` "ask" - a line of its own since
    2026-10-16, and the `unknown_action_tier` fall-through it took before that is
    also "ask". An unreadable settings file reads as "ask", and the gate then
    decides for itself on its own fail-closed rule.

    The try/except below was written twice, byte for byte, with the second copy
    left unreachable behind the first `return` (removed 2026-10-16: dead code a
    reader has to check twice is a small tax on every reader after that).
    """
    try:
        return str(fw.action_tier(action)) if fw is not None else "ask"
    except Exception:
        return "ask"


def _gate(action: str, detail: dict, prompt: str):
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def card_text(receipt: dict) -> str:
    """The words on the one Undo card, built from the receipt's own row.

    Every word comes from this module's own table and from the summary the
    recording module wrote; nothing here re-reads the snapshot, so the card
    cannot become a second copy of the owner's private words."""
    when = ""
    try:
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(float(receipt.get("created_at") or 0)))
    except Exception:
        when = ""
    lines = [CARD_HEAD, ""]
    summary = str(receipt.get("summary") or "").strip()
    if summary:
        lines += [f"Jarvis: {summary}"]
    else:
        lines += [f"Jarvis: {receipt.get('tool_name', 'an action')} changed something."]
    if when:
        lines += [f"  (made at {when})"]
    lines += ["", CARD_NOTE, "", CARD_TAIL]
    return "\n".join(lines)


def _finish(outcome: str, why: str = "", message: str = "", receipt_id: str = "") -> None:
    with _LOCK:
        _STATE["pending"] = None
        _STATE["last"] = {"outcome": outcome, "why": why, "at": time.time(),
                          "message": message or WORDS.get(outcome, ""),
                          "receipt_id": receipt_id}
    _audit("receipts.undo_card", {"outcome": outcome})


def _decide(receipt: dict, *, gate=None) -> None:
    """Put the one card to the gate, and reverse only on its own answer.

    The tier is the gate's business, not this module's (see the file's
    docstring): whatever tier the owner's settings file gives `undo_action`,
    `check()` is what decides it. In the shipped configuration that tier is
    "ask", so this is one card and a person's yes. The one rule this does keep
    is the one that is easy to get wrong: at tier "ask", `allowed` alone is not
    a yes - only an outcome of "approved" is, because `check()` also returns
    `allowed=True` at tier "notify" with nobody in the loop."""
    gate = gate or _gate
    rid = str(receipt.get("receipt_id") or "")
    try:
        verdict = gate(UNDO_ACTION,
                       {"receipt_id": rid, "tool_name": receipt.get("tool_name", "")},
                       card_text(receipt))
    except Exception as exc:
        return _finish("refused", f"the approval gate failed ({type(exc).__name__})",
                       WORDS["refused"], rid)
    vtier = str(getattr(verdict, "tier", "unknown") or "unknown")
    allowed = getattr(verdict, "allowed", False) is True
    outcome = getattr(verdict, "outcome", None)
    if vtier == "ask" and outcome not in (None, "approved"):
        allowed = False
    if not allowed:
        return _finish(outcome if outcome in ("denied", "timed_out") else "refused",
                       str(getattr(verdict, "reason", "")), "", rid)
    out = undo(rid)
    if out.get("ok"):
        return _finish("undone", "", out.get("words", WORDS["undone"]), rid)
    if out.get("already_undone"):
        return _finish("already", WORDS["already"], WORDS["already"], rid)
    return _finish("failed", str(out.get("error", "")), WORDS["failed"], rid)


def request_undo(receipt_id: str, *, gate=None, spawn=None) -> tuple:
    """POST /api/receipts/<id>/undo -> (http status, body).

    The id is checked, and the receipt's own state is read, BEFORE any card:
    a card is never raised for something that cannot be undone, and a receipt
    already undone is refused here without asking anybody. The reversal runs
    on its own thread - a card can wait fifteen minutes and an HTTP request
    must not - and how it ended is read back from GET /api/receipts (`last`).

    One card at a time, like every other card in this project. Whether a card
    is raised at all is the gate's decision, from the owner's own settings
    file; this module does not read that table (see the file's docstring)."""
    spawn = spawn or _spawn
    rid = _name(receipt_id, 64)
    if not _ID.match(rid):
        return 400, {"ok": False, "error": "need a receipt id"}
    receipt = get(rid)
    if receipt is None:
        return 404, {"ok": False, "error": WORDS["unknown"]}
    if receipt.get("undone"):
        return 409, {"ok": False, "already_undone": True, "error": WORDS["already"]}
    with _LOCK:
        if _STATE["pending"]:
            return 202, {"ok": True, "waiting": True, "receipt_id": rid,
                         "message": "A card is already waiting for your answer."}
        _STATE["pending"] = {"receipt_id": rid, "since": time.time()}
    spawn(lambda: _decide(receipt, gate=gate))
    return 202, {"ok": True, "waiting": True, "receipt_id": rid,
                 "message": "Waiting for your yes on the approval card. Nothing has changed yet."}


def _spawn(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="jarvis-receipts-undo", daemon=True).start()


def status() -> dict:
    """What the last Undo card did - for the apps' list route and the suites."""
    with _LOCK:
        return {"pending": dict(_STATE["pending"]) if _STATE["pending"] else None,
                "last": dict(_STATE["last"]) if _STATE["last"] else None}


def _flag(value) -> bool:
    """One query flag: only "1"/"true"/"yes"/"on" (any case) counts.

    A flag can only ADD withholding; `app_locked=0` is not an unlock key."""
    try:
        return str(value or "").strip().lower() in ("1", "true", "yes", "on")
    except Exception:
        return False


def _lock_view(app_locked=None, hide_memory_lists=None) -> dict:
    """The merged lock answer for GET /api/receipts, from jarvis_private_view.

    The helper ORs the trusted live state and the request flags, so a request
    can only make the answer more private. With no helper (an older backend),
    the same two flags are ORed here and an absent state still means unlocked.
    """
    try:
        import jarvis_private_view as private_view
        return private_view.effective(app_locked=app_locked,
                                      hide_memory_lists=hide_memory_lists)
    except Exception:
        locked = _flag(app_locked) or _flag(hide_memory_lists)
        why = ("Hidden while App lock is on." if _flag(app_locked) else
               'Hidden while "Hide memory lists and chat history" is on.'
               if _flag(hide_memory_lists) else "")
        return {"app_locked": _flag(app_locked),
                "hide_memory_lists": _flag(hide_memory_lists),
                "locked": locked, "why": why}


def list_view(limit: int = DEFAULT_LIMIT, *, app_locked=None,
              hide_memory_lists=None) -> dict:
    """The body of GET /api/receipts.

    While App lock is on (or the private lists are hidden), the answer carries
    the same honest marker and NO receipt rows: `recent()` is never called, so
    no summary, path or snapshot leaves the database for a locked view. The
    two flags can only add withholding - the merge lives in
    jarvis_private_view, and a False never clears the trusted live state.
    """
    try:
        wanted = max(1, min(MAX_LIMIT, int(limit)))
    except Exception:
        wanted = DEFAULT_LIMIT
    view = _lock_view(app_locked, hide_memory_lists)
    if view["locked"]:
        return {"ok": True, "withheld": True, "private": True,
                "why": view["why"], "receipts": [], "count": 0,
                "limit": wanted, "undo_action": UNDO_ACTION,
                "undo_tier": _tier(UNDO_ACTION), "waiting": False,
                "last": None, "words": dict(WORDS)}
    rows = recent(wanted)
    out = []
    for row in rows:
        row = dict(row)
        row["undoable"] = is_undoable(row)
        out.append(row)
    st = status()
    return {"ok": True, "receipts": out, "count": len(out), "limit": wanted,
            "undo_action": UNDO_ACTION, "undo_tier": _tier(UNDO_ACTION),
            "waiting": bool(st["pending"]), "last": st["last"], "words": dict(WORDS)}


def handle_get(route: str, query: str = "") -> tuple:
    if route != LIST_PATH:
        return 404, {"ok": False, "error": "no such route"}
    q = _query(query)
    raw = q.get("limit", "")
    try:
        limit = int(raw) if raw else DEFAULT_LIMIT
    except Exception:
        return 400, {"ok": False, "error": "limit must be a whole number"}
    return 200, list_view(limit, app_locked=q.get("app_locked"),
                          hide_memory_lists=q.get("hide_memory_lists"))


def handle_post(route: str, body, *, gate=None, spawn=None) -> tuple:
    match = _ROUTE.match(route or "")
    if not match:
        return 404, {"ok": False, "error": "no such route"}
    if body is not None and not isinstance(body, dict):
        return 400, {"ok": False, "error": "send a JSON object"}
    return request_undo(match.group(1), gate=gate, spawn=spawn)


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls.do_GET` and `do_POST` so these two routes are answered
    here, after the server's own origin and token checks. Every other request
    goes straight to the original, untouched - the same shape jarvis_news.py,
    jarvis_sources.py and jarvis_goals.py already use, and the reason this
    feature needs no patch: `plugins/ready/receipts/plugin.json` names this
    module and `jarvis_plugins.py` makes the call the patch would have made."""
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(get0, "_jarvis_receipts", False):
        return "  receipts   action receipts and one-click undo (already on)"

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
        parts = urlsplit(str(getattr(self, "path", "") or ""))
        route = parts.path.rstrip("/")
        if route not in PATHS:
            return get0(self)
        if not _allowed(self):
            return None
        try:
            code, out = handle_get(route, parts.query)
        except Exception as exc:
            code, out = 503, {"ok": False, "error": type(exc).__name__}
        return self._send(code, out)

    def do_POST(self):
        route = urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if not _ROUTE.match(route):
            return post0(self)
        if not _allowed(self):
            return None
        try:
            body = json.loads(read_body(self) or b"{}")
        except Exception:
            body = None
        try:
            code, out = handle_post(route, body)
        except Exception as exc:
            code, out = 503, {"ok": False, "error": type(exc).__name__}
        return self._send(code, out)

    do_GET._jarvis_receipts = True
    do_POST._jarvis_receipts = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    return "  receipts   action receipts and one-click undo: on"


# --------------------------------------------------------------------------
#   For the suites
# --------------------------------------------------------------------------


def _reset_for_tests() -> None:
    """Forget what a RESTART forgets: the in-memory callables, and the two
    status lines. A receipt whose callable is gone takes the snapshot path,
    which is exactly the case a new process is.

    The RESTORERS are deliberately left alone. They are import-time
    registrations, so they are what the modules imported in THIS process
    really hold; a test that wants the store to find one by name (the
    `undo_callable` label, which is all a new process has) clears
    `_RESTORERS` itself."""
    with _LOCK:
        _CALLABLES.clear()
        _STATE["pending"] = None
        _STATE["last"] = None
