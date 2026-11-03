"""jarvis_mood.py - the owner's own mood log: one 1-5 tap a day, optional
words, and a history he can look at (the owner's 2026-11-02 decision D1,
.dsh-scratch/LIFE-COACH-RESEARCH-2026-11-02/OWNER-DECISIONS.md).

NEW MODULE, shipped whole. Its routes come from its own install(), called by
the drop-in folder `plugins/ready/mood` - there is no patch to `jarvis_hud.py`
(plugins/loader/README.md).

WHY THIS EXISTS WHEN THE PROJECT SAID NO ON 2026-09-26
docs/CUTTING-EDGE-2026-09-26-round4-wellbeing.md:314 declined "a mood log,
score or chart. A health-like record nobody asked for." The owner asked, on
2026-11-02, and chose the number-plus-chart shape himself (D1). That reverses
the decline for HIS OWN log and nothing else: no score, no judgement, no
interpretation, and no "how are you feeling today?" prompt ever. The record of
the reversal is decisions.d/2026-11-02-mood-log-recorded.md.

WHAT IT IS, AND WHAT IT IS NOT
A day has at most ONE row: `value` (an integer 1-5 the owner tapped) and
optional `words` (his own sentence, capped). A second entry on the same day
REPLACES the first - that is what "one row per day" means, and it is an
upsert, not a second record. There is no average, no trend, no "you seem low",
no streak and no advice: reading the rows is the client's business and drawing
the chart is a display concern. This module never computes a word about how
the owner feels.

It learns NOTHING and sends NOTHING. Mood values and words never reach
jarvis_intake, jarvis_auto_learn, jarvis_memory or any other fact path, and
`backend/test_learning_exclusion.py` proves that in both directions - no such
call exists in this file, no learner names this file, and writing a mood
creates no fact store. That is D2's "excluded entirely": not card-gated,
impossible by construction. It is stricter than the existing mood rule
(jarvis_intake.mood_rule, "Moods ... is not a fact. Do not propose it"), and
the two work together: the model is told not to propose a mood, and this log
is not a place a fact could come from in the first place.

No card is raised, in either direction: setting a mood is personal logging,
the same class as ticking a to-do (the owner, 2026-11-02), and it never
touches a gate. `jarvis_gate` is not imported anywhere in this file.

WHERE IT IS KEPT
`mood.db` beside habits.db, goals.db, schedule.db and memory.db, in the Jarvis
settings folder (JARVIS_MOOD_DB overrides it, for the tests). One table, one
row per day. Nothing is written to a log beyond the day and the fact that a row
changed - never the value and never the words.

THE CRISIS PATH IS NOT THIS MODULE'S
A sentence that is bigger than a mood note still belongs to jarvis_wellbeing.py
and a real person. Nothing here reads the words for crisis phrases and nothing
here answers them: this is a log, not a conversation, and it must never look
like a place the owner went for help. `backend/test_mood.py` pins that this
module holds no crisis phrase list and imports no wellbeing module, so the one
crisis path cannot be half-reimplemented here.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional

import jarvis_sqlite

try:
    import jarvis_framework as fw
except Exception:  # pragma: no cover - shipped beside it on the PC
    fw = None  # type: ignore

# --------------------------------------------------------------------------
#   Numbers
# --------------------------------------------------------------------------

MIN_VALUE = 1         # the lowest tap, and the highest - the whole scale
MAX_VALUE = 5
MAX_WORDS = 200       # the optional words on one day
MAX_DAYS = 400        # the longest history one read may ask for

#: The sentences both apps show, word for word - the PC's own copy.
WORDS = {
    "saved": "Saved for today.",
    "replaced": "Today's entry was replaced.",
    "scale": "A mood entry is a whole number from 1 to 5.",
    "no_entry": "No mood entry for that day.",
}

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
    env = os.environ.get("JARVIS_MOOD_DB")
    return Path(env) if env else _config_dir() / "mood.db"


_SCHEMA = """
CREATE TABLE IF NOT EXISTS moods (
    day      TEXT PRIMARY KEY,
    value    INTEGER NOT NULL,
    words    TEXT NOT NULL DEFAULT '',
    created  REAL NOT NULL,
    changed  REAL NOT NULL
);
"""

_LOCK = threading.RLock()


def _connect() -> sqlite3.Connection:
    """A connection that CLOSES when its `with` block ends (jarvis_sqlite)."""
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    jarvis_sqlite.ensure_schema(path, lambda c: c.executescript(_SCHEMA))
    c = jarvis_sqlite.connect(path, timeout=30)
    c.row_factory = sqlite3.Row
    return c


# --------------------------------------------------------------------------
#   Days and values
# --------------------------------------------------------------------------

def _today() -> _dt.date:
    """The owner's own wall-clock day, never UTC."""
    lt = time.localtime()
    return _dt.date(lt.tm_year, lt.tm_mon, lt.tm_mday)


def _iso_day(value) -> str:
    if value is None:
        return _today().isoformat()
    if isinstance(value, _dt.datetime):
        return value.date().isoformat()
    if isinstance(value, _dt.date):
        return value.isoformat()
    text = str(value).strip()
    if not (len(text) == 10 and text[4] == "-" and text[7] == "-"
            and text[:4].isdigit() and text[5:7].isdigit() and text[8:].isdigit()):
        raise ValueError("a day looks like 2026-11-02")
    try:
        return _dt.date.fromisoformat(text).isoformat()
    except ValueError:
        raise ValueError("that day is not on the calendar")


def _value(value) -> int:
    """The tap, as a whole number 1-5. A bool is not a number here, a float is
    not a tap, and "3" is accepted because a JSON client may send a string."""
    if isinstance(value, bool):
        raise ValueError(WORDS["scale"])
    if isinstance(value, str) and value.strip().isdigit():
        value = int(value.strip())
    if not isinstance(value, int):
        raise ValueError(WORDS["scale"])
    if not MIN_VALUE <= value <= MAX_VALUE:
        raise ValueError(WORDS["scale"])
    return value


def _clean(value) -> str:
    t = " ".join(str(value or "").split())
    if len(t) > MAX_WORDS:
        raise ValueError(f"the words on a mood are longer than {MAX_WORDS} characters")
    return t


def _view(row) -> dict:
    return {"day": str(row["day"]), "value": int(row["value"]),
            "words": str(row["words"] or ""),
            "created": float(row["created"]), "changed": float(row["changed"])}


# --------------------------------------------------------------------------
#   Recording and reading
# --------------------------------------------------------------------------

def record(value, *, words="", day=None) -> dict:
    """Save ONE day's entry: the value, optional words, and whether an earlier
    entry that day was replaced.

    Upsert by day, no card, no model, nothing learned. Idempotent in the sense
    the owner expects from a log: the same tap twice leaves ONE row, and the
    second tap simply becomes today's entry.
    """
    val = _value(value)
    note = _clean(words)
    day = _iso_day(day)
    now = time.time()
    with _LOCK, _connect() as c:
        had = c.execute("SELECT 1 FROM moods WHERE day = ?", (day,)).fetchone() is not None
        if had:
            c.execute("UPDATE moods SET value = ?, words = ?, changed = ? WHERE day = ?",
                      (val, note, now, day))
        else:
            c.execute("INSERT INTO moods (day, value, words, created, changed) "
                      "VALUES (?,?,?,?,?)", (day, val, note, now, now))
        row = c.execute("SELECT * FROM moods WHERE day = ?", (day,)).fetchone()
    _audit("mood.record", {"day": day, "replaced": bool(had)})
    return {"ok": True, "replaced": bool(had), "entry": _view(row),
            "said": WORDS["replaced"] if had else WORDS["saved"]}


def get(day=None) -> Optional[dict]:
    day = _iso_day(day)
    with _LOCK, _connect() as c:
        row = c.execute("SELECT * FROM moods WHERE day = ?", (day,)).fetchone()
    return _view(row) if row is not None else None


def history(days: int = 30, *, day=None) -> list:
    """The last `days` days, newest first: rows only, with no computed average
    and no verdict. The client draws the chart from this."""
    days = max(1, min(int(days or 30), MAX_DAYS))
    end = _dt.date.fromisoformat(_iso_day(day))
    since = (end - _dt.timedelta(days=days - 1)).isoformat()
    with _LOCK, _connect() as c:
        rows = c.execute("SELECT * FROM moods WHERE day >= ? AND day <= ? "
                         "ORDER BY day DESC", (since, end.isoformat())).fetchall()
    return [_view(r) for r in rows]


def latest() -> Optional[dict]:
    with _LOCK, _connect() as c:
        row = c.execute("SELECT * FROM moods ORDER BY day DESC LIMIT 1").fetchone()
    return _view(row) if row is not None else None


def count_days(start, end) -> int:
    """How many days between two dates hold a row - a COUNT, for the weekly
    review. It reads no value and no word: a review can say "4 of 7 days" and
    can never say what any of them was."""
    lo, hi = _iso_day(start), _iso_day(end)
    with _LOCK, _connect() as c:
        return int(c.execute("SELECT COUNT(*) FROM moods WHERE day >= ? AND day <= ?",
                             (lo, hi)).fetchone()[0])


def clear(day=None) -> dict:
    """Remove ONE day's entry - the owner's own row, deleted at once, no card.
    Days before and after it are untouched."""
    day = _iso_day(day)
    with _LOCK, _connect() as c:
        cur = c.execute("DELETE FROM moods WHERE day = ?", (day,))
        removed = cur.rowcount > 0
    if removed:
        _audit("mood.clear", {"day": day})
    return {"ok": True, "removed": bool(removed), "day": day,
            "said": "Removed." if removed else WORDS["no_entry"]}


# --------------------------------------------------------------------------
#   The routes both apps call
# --------------------------------------------------------------------------

PATH = "/api/mood"


def handle_get(route: str, query: str = "") -> tuple:
    if route != PATH:
        return 404, {"ok": False, "error": "That address is not a mood entry on this PC."}
    days = 30
    try:
        from urllib.parse import parse_qs
        asked = (parse_qs(query or "").get("days") or [""])[0]
        if asked:
            days = int(asked)
    except Exception:
        days = 30
    days = max(1, min(days, MAX_DAYS))
    return 200, {"ok": True, "history": history(days), "latest": latest(),
                 "limits": {"min": MIN_VALUE, "max": MAX_VALUE,
                            "words": MAX_WORDS, "days": MAX_DAYS},
                 "words": dict(WORDS)}


def handle_post(route: str, body) -> tuple:
    if route != PATH:
        return 404, {"ok": False, "error": "That address is not a mood entry on this PC."}
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "need a JSON object"}
    try:
        # Strictly a yes: a client sending {"clear": "false"} must not delete
        # the day, so anything that is not a real true is ignored here.
        if body.get("clear") is True or body.get("clear") == 1:
            return 200, dict(clear(body.get("day")))
        return 200, dict(record(body.get("value"), words=body.get("words"),
                                day=body.get("day")),
                         history=history(30))
    except ValueError as exc:
        return 400, {"ok": False, "error": str(exc)}
    except Exception as exc:
        return 503, {"ok": False, "error": type(exc).__name__}


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls.do_GET`/`do_POST` so /api/mood is answered here, after
    the server's own origin and token checks. Every other request goes straight
    to the original - the reason this feature needs no patch and no change to
    jarvis_hud.py."""
    global _ARMED
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(post0, "_jarvis_mood", False):
        _ARMED = True
        return "  mood       Mood log (already on)"

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

    def _parts(self):
        from urllib.parse import urlsplit
        p = urlsplit(str(getattr(self, "path", "") or ""))
        return p.path.rstrip("/"), p.query

    def do_GET(self):
        route, query = _parts(self)
        if route != PATH:
            return get0(self)
        if not _allowed(self):
            return None
        try:
            code, out = handle_get(route, query)
        except Exception as exc:
            code, out = 503, {"ok": False, "error": type(exc).__name__}
        return self._send(code, out)

    def do_POST(self):
        route, _query = _parts(self)
        if route != PATH:
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

    do_GET._jarvis_mood = True
    do_POST._jarvis_mood = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    _ARMED = True
    try:
        n = len(history(MAX_DAYS))
    except Exception:
        n = 0
    return f"  mood       Mood log: {n} entries kept (GET/POST /api/mood)"


_ARMED = False


def _audit(event: str, detail: dict) -> None:
    """The day and whether a row was replaced - never the value, never the
    words."""
    try:
        if fw is not None:
            fw.audit_log(event, detail)
    except Exception:
        pass


def _reset_for_tests() -> None:
    global _ARMED
    _ARMED = False
