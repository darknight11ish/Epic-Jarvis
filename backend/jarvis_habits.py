"""jarvis_habits.py - habit check-ins: "I want to walk three times a week",
and one tap records that it happened (the owner's 2026-11-02 decisions D1-D4,
.dsh-scratch/LIFE-COACH-RESEARCH-2026-11-02/OWNER-DECISIONS.md).

NEW MODULE, shipped whole. Its routes come from its own install(), called by
the drop-in folder `plugins/ready/habits` - there is no patch to
`jarvis_hud.py`, which is the whole point of the plug-in loader
(plugins/loader/README.md).

WHAT IT IS FOR, IN PLAIN WORDS
A habit is a repeating thing the owner wants to do - walk, stretch, practise -
with a frequency in their own words and a time they picked. Once it exists,
Jarvis asks at that time (the one scheduler already owns the clock), and a
single tap on either app writes ONE row saying "this happened on this day".
That is the entire feature. There is no score, no streak, no percentage and no
"longest run": this project has removed a streak twice on purpose
(docs/JARVIS-API.md section 21's report card and section 19472/19577), and the
owner's D4 is explicit that the habit record must not become a game.

WHAT IT DELIBERATELY DOES NOT DO
  * It does not judge. No module here computes a rate, a target, a trend or a
    word like "slipping". A count of stored rows is the most it can say, and
    only the week-in-review prints one.
  * It learns NOTHING. A habit's name, its ticks and any words typed on a tick
    are never handed to jarvis_intake, jarvis_auto_learn, jarvis_memory or any
    other fact path - not because a card stands in front of them, but because
    no such call exists anywhere in this file. `backend/test_learning_
    exclusion.py` proves that in both directions (this module names no learner,
    and no learner names this module), and that writing a habit creates no
    fact store at all.
  * It sends nothing anywhere. No network call of any kind, no model call, no
    child process. The file has no `urllib`, no `requests`, no `open_stream`.
  * It raises NO card. Creating a check-in is the cardless `plain_repeat` path
    on the one scheduler - the same class as a plain repeating reminder
    (decided 2026-09-26) and a tick is the same class as ticking a to-do
    (`schedule act done`): the owner's own tap, reading nothing new, acting on
    nothing. Stopping is immediate and keeps every tick.
  * It is not a new gate tier and not a shell or script kind. There is no
    approval logic in this file at all - `jarvis_gate` is not imported, and
    the absence is pinned by a test.

WHAT IS KEPT, AND WHERE
`habits.db` in the Jarvis settings folder, beside goals.db, schedule.db and
memory.db (JARVIS_HABITS_DB overrides it, for the tests). Two tables:
`habits` (one row per habit: the owner's own words, the repeating rule as
accepted, the scheduler job id, and when it was stopped) and `ticks` (one row
per habit per DAY - `PRIMARY KEY (habit, day)` is what makes a second tick on
the same day a no-op rather than a second row). Stop sets `stopped` and deletes
the job; it never deletes a tick. Nothing here is ever written to a log beyond
an id, and never put on the event bus beyond an id.

THE TWO KINDS ON THE ONE SCHEDULER
`KIND = "habit_checkin"` is the habit's own nudge, registered exactly like
`jarvis_goals.KIND = "goal_checkin"` (a kind, not a timer of its own -
docs/ARCHITECTURE.md section 12). Its `on_fire` re-reads a habit this module
already owns and does nothing else; its `note` hook is the line both apps show
under the job, and it is deterministic and free of counts.
`WEEK_KIND = "week_review"` is the weekly review (week_summary / render_week
below): it only exists because the owner turned it on, and `stop_week()` takes
it down in one tap.

WHERE THE REMINDER LANE PLUGS IN (that lane may land before or after this one)
`record_tick(habit_id, ...)` is the clean entry point for anything that wants
to record a habit tick without a route: a reminder's answer destination, a
quick reply, a voice action. It takes the habit id, an optional wall-clock day
and optional words, writes or keeps the one row for that day, raises no card
and returns the row. It never needs a server to be listening, never touches
the scheduler, and is safe to call from a background thread (one RLock per
call, one connection per call). `jarvis_schedule.py` is NOT edited by this
lane: it is deliberately not touched, so that lane's own change cannot conflict
with this one.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Callable, Optional

import jarvis_sqlite

try:
    import jarvis_framework as fw
except Exception:  # pragma: no cover - shipped beside it on the PC
    fw = None  # type: ignore

# --------------------------------------------------------------------------
#   Numbers
# --------------------------------------------------------------------------

MAX_TEXT = 300        # a habit's own words
MAX_HABITS = 20       # active habits at once
MAX_WORDS = 200       # optional words typed on one tick
MAX_DAYS = 400        # the longest history one read may ask for

#: The scheduler kind a habit's own nudge is registered under.
KIND = "habit_checkin"

#: The scheduler kind the weekly review is set up under.
WEEK_KIND = "week_review"

#: A new habit with no rule given: once a day, in the morning. A plain default,
#: never presented as a measurement or a recommendation.
DEFAULT_RULE = {"every": "day", "at": "09:00"}

#: The weekly review's own plain default: Monday morning, like the goals
#: check-in (jarvis_goals.DEFAULT_RULE). The owner may pass another rule.
WEEK_RULE = {"every": "week", "at": "09:00", "days": [0]}

_DAY_RE = re.compile(r"\d{4}-\d{2}-\d{2}")

#: The sentences both apps show for this feature, word for word - the PC's own
#: copy, so a client never invents wording. `{...}` is filled by the PC.
WORDS = {
    "note": '"{text}" - tick it when you have done it.',
    "already": "Already ticked for that day.",
    "ticked": "Ticked.",
    "stopped": "Stopped. Every tick stays on your list.",
    "no_journal": ("no journal is set up on this PC - choose Obsidian, Logseq or "
                   "Joplin in Settings first"),
    "week_title": "Week in review",
    "counts_note": ("These are counts of what is stored on this PC - "
                    "nothing here is a judgement."),
    "week_on": "The week in review is on - it files one line a week until you stop it.",
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
    env = os.environ.get("JARVIS_HABITS_DB")
    return Path(env) if env else _config_dir() / "habits.db"


_SCHEMA = """
CREATE TABLE IF NOT EXISTS habits (
    id       TEXT PRIMARY KEY,
    text     TEXT NOT NULL,
    rule     TEXT NOT NULL,
    job      TEXT,
    created  REAL NOT NULL,
    changed  REAL NOT NULL,
    stopped  REAL
);
CREATE TABLE IF NOT EXISTS ticks (
    habit    TEXT NOT NULL,
    day      TEXT NOT NULL,
    at       REAL NOT NULL,
    words    TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (habit, day)
);
CREATE INDEX IF NOT EXISTS ticks_day ON ticks(day);
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
#   Days and words
# --------------------------------------------------------------------------

def _today() -> _dt.date:
    """The owner's own wall-clock day (the same way jarvis_local_calendar does
    it), never UTC: a tick at 23:30 belongs to that evening, not to tomorrow."""
    lt = time.localtime()
    return _dt.date(lt.tm_year, lt.tm_mon, lt.tm_mday)


def _iso_day(value) -> str:
    """(YYYY-MM-DD) for a date, a datetime or a strict string; ValueError in
    words for anything else. Never guesses a missing day."""
    if value is None:
        return _today().isoformat()
    if isinstance(value, _dt.datetime):
        return value.date().isoformat()
    if isinstance(value, _dt.date):
        return value.isoformat()
    text = str(value).strip()
    if not _DAY_RE.fullmatch(text):
        raise ValueError("a day looks like 2026-11-02")
    try:
        return _dt.date.fromisoformat(text).isoformat()
    except ValueError:
        raise ValueError("that day is not on the calendar")


def _day_start(day: str) -> float:
    """The first second of that wall-clock day, as an epoch (the unit
    goals.db stamps `done_at` in)."""
    d = _dt.date.fromisoformat(day)
    return _dt.datetime.combine(d, _dt.time.min).timestamp()


def _day_end(day: str) -> float:
    """The last second of that wall-clock day, as an epoch."""
    d = _dt.date.fromisoformat(day)
    return _dt.datetime.combine(d, _dt.time.max).timestamp()


def _clean(value, cap: int, what: str) -> str:
    """One line of the owner's own words, whitespace collapsed, capped."""
    t = " ".join(str(value or "").split())
    if len(t) > cap:
        raise ValueError(f"{what} is longer than {cap} characters - say it more briefly")
    return t


def _clean_text(text) -> str:
    t = _clean(text, MAX_TEXT, "a habit")
    if not t:
        raise ValueError("a habit needs some words")
    return t


def _new_id() -> str:
    return "h" + uuid.uuid4().hex[:10]


# --------------------------------------------------------------------------
#   The rows, as a client reads them
# --------------------------------------------------------------------------

def _habit_view(row, last_tick: str = "") -> dict:
    return {
        "id": str(row["id"]),
        "text": str(row["text"]),
        "rule": _json(row["rule"], {}),
        "created": float(row["created"]),
        "changed": float(row["changed"]),
        "stopped": (float(row["stopped"]) if row["stopped"] is not None else None),
        "active": row["stopped"] is None,
        # The day of the newest tick, or "" - a fact about the row, not a score.
        "last_tick": last_tick,
    }


def _tick_view(row) -> dict:
    return {"habit": str(row["habit"]), "day": str(row["day"]),
            "at": float(row["at"]), "words": str(row["words"] or "")}


def _json(raw, default):
    try:
        out = json.loads(raw) if isinstance(raw, str) else raw
    except ValueError:
        return default
    return out if isinstance(out, type(default)) else default


# --------------------------------------------------------------------------
#   Creating, ticking, stopping
# --------------------------------------------------------------------------

def _scheduler():
    """The one scheduler, or None - lazily, so importing this module on a PC
    without jarvis_schedule.py is harmless."""
    try:
        import jarvis_schedule
        return jarvis_schedule
    except Exception:
        return None


def create(text, rule=None) -> dict:
    """A new habit and its repeating nudge, at once, with NO card: the same
    class as a plain repeating reminder (Kind.plain_repeat, decided
    2026-09-26). The owner's own tap is the whole of the permission - it reads
    nothing new and acts on nothing.

    THE ORDER IS DELIBERATE, and it is jarvis_goals.accept's own order: the
    count and the id in one SHORT database block, then the scheduler call with
    no connection held (a connection held open across another module's work is
    how a database gets locked out from under it), then the row. If the row
    cannot be written, the job it just made is deleted again - a reminder for a
    habit that does not exist would fire at the owner for nothing.
    """
    text = _clean_text(text)
    sched = _scheduler()
    if sched is None:
        raise RuntimeError("the scheduler is not available")
    clean_rule = dict(DEFAULT_RULE) if rule is None else rule
    if not isinstance(clean_rule, dict):
        raise ValueError("a rule is a small object")
    with _LOCK:
        with _connect() as c:
            active = int(c.execute(
                "SELECT COUNT(*) FROM habits WHERE stopped IS NULL").fetchone()[0])
            if active >= MAX_HABITS:
                raise OverflowError(f"there are already {MAX_HABITS} habits - "
                                    "stop one before adding another")
            hid = _new_id()
        # add_repeat validates the rule through the scheduler's own check_rule
        # and, because this kind is plain_repeat, raises nothing at all.
        job = sched.get().add_repeat(KIND, clean_rule, text=text, source="app")
        try:
            now = time.time()
            with _connect() as c:
                c.execute("INSERT INTO habits (id, text, rule, job, created, changed, "
                          "stopped) VALUES (?,?,?,?,?,?,NULL)",
                          (hid, text, json.dumps(clean_rule), job.get("id"), now, now))
        except Exception:
            try:
                sched.get().act(str(job.get("id")), "delete")
            except Exception:
                pass
            raise
    _audit("habits.create", {"id": hid})
    return dict(get(hid), checkin=job)


def _row(habit_id):
    with _LOCK, _connect() as c:
        return c.execute("SELECT * FROM habits WHERE id = ?",
                         (str(habit_id or ""),)).fetchone()


def get(habit_id) -> Optional[dict]:
    row = _row(habit_id)
    if row is None:
        return None
    return dict(_habit_view(row, _last_tick(str(row["id"]))), history=_history(row["id"], 30))


def _last_tick(habit_id: str) -> str:
    with _LOCK, _connect() as c:
        row = c.execute("SELECT MAX(day) AS d FROM ticks WHERE habit = ?",
                        (habit_id,)).fetchone()
    return str(row["d"] or "") if row is not None else ""


def _history(habit_id: str, days: int) -> list:
    days = max(1, min(int(days or 30), MAX_DAYS))
    since = (_today() - _dt.timedelta(days=days - 1)).isoformat()
    with _LOCK, _connect() as c:
        rows = c.execute("SELECT * FROM ticks WHERE habit = ? AND day >= ? "
                         "ORDER BY day DESC", (habit_id, since)).fetchall()
    return [_tick_view(r) for r in rows]


def list_habits(history_days: int = 30) -> list:
    """Every habit, newest first, each with its own recent ticks (the chart's
    own data - rows, never a rate)."""
    with _LOCK, _connect() as c:
        rows = c.execute("SELECT * FROM habits ORDER BY created DESC").fetchall()
    return [dict(_habit_view(r, _last_tick(str(r["id"]))),
                 history=_history(r["id"], history_days))
            for r in rows]


def record_tick(habit_id, *, day=None, words="", source="app") -> dict:
    """Record ONE tick for one day. Idempotent by construction.

    `PRIMARY KEY (habit, day)` is the whole of the rule: the first call
    inserts the row, every later call that day keeps it and says
    `"added": False`. Two taps cannot make two rows, so a habit cannot be
    "double-counted" - which is also why no score is possible to inflate.

    Raises KeyError for an unknown habit and ValueError for a stopped one: a
    habit the owner stopped does not quietly keep collecting ticks. No card is
    raised, nothing is learned, nothing is sent anywhere.

    THIS IS THE REMINDER LANE'S ENTRY POINT (see the module docstring): call it
    with the habit id only; nothing here needs a listening server.
    """
    hid = str(habit_id or "")
    day = _iso_day(day)
    note = _clean(words, MAX_WORDS, "the words on a tick")
    with _LOCK, _connect() as c:
        row = c.execute("SELECT * FROM habits WHERE id = ?", (hid,)).fetchone()
        if row is None:
            raise KeyError("no such habit")
        if row["stopped"] is not None:
            raise ValueError("that habit is stopped")
        now = time.time()
        cur = c.execute("INSERT OR IGNORE INTO ticks (habit, day, at, words) "
                        "VALUES (?,?,?,?)", (hid, day, now, note))
        added = cur.rowcount == 1
        if added:
            c.execute("UPDATE habits SET changed = ? WHERE id = ?", (now, hid))
        tick = c.execute("SELECT * FROM ticks WHERE habit = ? AND day = ?",
                         (hid, day)).fetchone()
    if added:
        # `source` comes from the caller (a route body, the reminder lane) and
        # is NOT the owner's words: it is a short tag. Capped here so a client
        # cannot push an unbounded string into the audit log through it.
        _audit("habits.tick", {"id": hid, "day": day,
                               "source": str(source or "")[:40]})
    return {"ok": True, "added": bool(added), "tick": _tick_view(tick),
            "said": WORDS["ticked"] if added else WORDS["already"]}


def tick(habit_id, **kw) -> dict:
    """The route's name for `record_tick` - one function, so a tick means the
    same thing whether it came from an app, a reminder or a voice action."""
    return record_tick(habit_id, **kw)


def untick(habit_id, *, day=None) -> dict:
    """Take back ONE mistaken tick for one day. No card, immediate, and it
    never touches another day's row."""
    hid = str(habit_id or "")
    day = _iso_day(day)
    with _LOCK, _connect() as c:
        if c.execute("SELECT 1 FROM habits WHERE id = ?", (hid,)).fetchone() is None:
            raise KeyError("no such habit")
        cur = c.execute("DELETE FROM ticks WHERE habit = ? AND day = ?", (hid, day))
        removed = cur.rowcount > 0
    if removed:
        _audit("habits.untick", {"id": hid, "day": day})
    return {"ok": True, "removed": bool(removed), "day": day}


def stop(habit_id) -> dict:
    """Stop tracking a habit: one tap, immediate, and EVERY TICK STAYS.

    The repeating job is deleted so it never fires again, the habit is marked
    stopped so it cannot take a new tick, and the history is untouched -
    stopping is "no more asks", never "delete what happened".
    """
    hid = str(habit_id or "")
    with _LOCK, _connect() as c:
        row = c.execute("SELECT * FROM habits WHERE id = ?", (hid,)).fetchone()
        if row is None:
            raise KeyError("no such habit")
        job = row["job"]
        if row["stopped"] is None:
            c.execute("UPDATE habits SET stopped = ?, changed = ? WHERE id = ?",
                      (time.time(), time.time(), hid))
    if job:
        sched = _scheduler()
        if sched is not None:
            try:
                sched.get().act(str(job), "delete")
            except Exception:
                pass  # a job already gone is not a reason to keep the habit on
    _audit("habits.stop", {"id": hid})
    return dict(get(hid), said=WORDS["stopped"])


def habit_id_for_job(job_id) -> str:
    """The reverse of `job` - looked up FROM the habit, never by parsing the
    job's own text (the habit's words are for display only)."""
    with _LOCK, _connect() as c:
        row = c.execute("SELECT id FROM habits WHERE job = ?", (str(job_id),)).fetchone()
    return str(row["id"]) if row is not None else ""


# --------------------------------------------------------------------------
#   The scheduler's own hooks - deterministic, and they act on nothing
# --------------------------------------------------------------------------

def habit_note(habit_id) -> str:
    """The line both apps show under the habit's job in Coming up. One
    sentence, the habit's own words, no count, no streak and no praise."""
    row = _row(habit_id)
    if row is None or row["stopped"] is not None:
        return ""
    return WORDS["note"].format(text=str(row["text"]))


def on_habit_fire(job_id: str) -> None:
    """register_kind's on_fire for KIND. Calls no model, no tool, raises no
    card and writes nothing: a habit going off is a reminder the owner asked
    for, and the note under it is the whole output."""
    try:
        habit_note(habit_id_for_job(job_id))
    except Exception:
        pass  # a bad read must never take the scheduler's loop down


# --------------------------------------------------------------------------
#   The week in review: counts of stored rows, never interpretations
# --------------------------------------------------------------------------

def _week_window(day=None) -> tuple:
    """The seven days BEFORE the day the review runs - the week that passed,
    not the week in progress. Deterministic, so two PCs agree."""
    end = _dt.date.fromisoformat(_iso_day(day)) - _dt.timedelta(days=1)
    start = end - _dt.timedelta(days=6)
    return start.isoformat(), end.isoformat()


def _goal_steps(start: str, end: str, reader=None):
    """How many goal steps were ticked inside the window, by reading the goals
    store's OWN rows (jarvis_goals.Goals with no scheduler: a read only).

    `done_at` is the only record a step keeps, so this counts the steps whose
    latest tick falls in the window. It reads nothing else, calls no model and
    writes nothing - and if the goals module is not on this PC it says so
    (None) rather than reporting a confident zero.
    """
    if reader is not None:
        return reader(start, end)
    try:
        import jarvis_goals
    except Exception:
        return None
    try:
        store = jarvis_goals.Goals()          # no scheduler: read only
        lo, hi = _day_start(start), _day_end(end)
        n = 0
        for goal in store.list():
            for step in goal.get("plan") or []:
                at = step.get("done_at")
                if step.get("done") and isinstance(at, (int, float)) and lo <= at <= hi:
                    n += 1
        return n
    except Exception:
        return None


def _reminders_fired(start: str, end: str, reader=None):
    """How many jobs the owner was told about went off inside the window, from
    the scheduler's own `fired_since` - the same list "What did I miss?" reads.
    None (never a confident 0) when the scheduler cannot be asked."""
    if reader is not None:
        return reader(start, end)
    try:
        sched = _scheduler()
        if sched is None:
            return None
        return len(sched.get().fired_since(_day_start(start), _day_end(end)))
    except Exception:
        return None


def _mood_days(start: str, end: str, reader=None):
    """How many days of the window hold a mood row, and nothing about what the
    value was: the review counts rows, it does not read a mood out loud."""
    if reader is not None:
        return reader(start, end)
    try:
        import jarvis_mood
        return int(jarvis_mood.count_days(start, end))
    except Exception:
        return None


def week_summary(day=None, *, goal_reader=None, reminder_reader=None,
                 mood_reader=None) -> dict:
    """The week that passed, as COUNTS OF STORED ROWS and nothing else.

    Four numbers, each from a store this project already keeps:
      * habit ticks         - this module's own `ticks` rows (with the per-habit
                              counts, and the habit's own words);
      * goal steps ticked    - jarvis_goals' plan rows whose `done_at` is in it;
      * reminders that went off - jarvis_schedule's own fired list;
      * mood rows present    - jarvis_mood's rows, a DAY COUNT only (the values
                              are never read here, so a review can never say
                              what a mood was).
    No model is called, no tool runs, no file is read beyond those stores. A
    count that could not be read is None, never a made-up zero.
    """
    start, end = _week_window(day)
    with _LOCK, _connect() as c:
        rows = c.execute("SELECT habit, COUNT(*) AS n FROM ticks "
                         "WHERE day >= ? AND day <= ? GROUP BY habit",
                         (start, end)).fetchall()
        names = {}
        for r in c.execute("SELECT id, text FROM habits").fetchall():
            names[str(r["id"])] = str(r["text"])
    per_habit = [{"text": names.get(str(r["habit"]), ""), "ticks": int(r["n"])}
                 for r in rows]
    mood_n = _mood_days(start, end, mood_reader)
    out = {
        "from": start,
        "to": end,
        "habit_ticks": sum(int(r["n"]) for r in rows),
        "habits": per_habit,
        "goal_steps": _goal_steps(start, end, goal_reader),
        "reminders": _reminders_fired(start, end, reminder_reader),
        "mood_rows": mood_n,
        "mood_days_in_week": 7,
        "note": WORDS["counts_note"],
    }
    out["text"] = render_week(out)
    return out


def _count_line(label: str, n) -> str:
    return f"{label}: not read on this PC" if n is None else f"{label}: {n}"


def render_week(summary: dict) -> str:
    """The review as plain lines. Deterministic: the same stored rows always
    produce the same words, because nothing here is generated and nothing is
    interpreted. It says out loud that these are counts."""
    start, end = summary.get("from", ""), summary.get("to", "")
    lines = [f"{WORDS['week_title']}, {start} to {end}"]
    habits = [h for h in summary.get("habits") or [] if h.get("ticks")]
    if habits:
        each = ", ".join(f"{h['text']} {h['ticks']}" for h in habits)
        lines.append(f"Habit ticks: {summary.get('habit_ticks', 0)} ({each})")
    else:
        lines.append("Habit ticks: 0")
    lines.append(_count_line("Goal steps ticked", summary.get("goal_steps")))
    lines.append(_count_line("Reminders that went off", summary.get("reminders")))
    mood = summary.get("mood_rows")
    if mood is None:
        lines.append("Mood entries: not read on this PC")
    else:
        lines.append(f"Mood entries: {mood} of {summary.get('mood_days_in_week', 7)} days")
    lines.append(summary.get("note") or WORDS["counts_note"])
    return "\n".join(lines)


def _capture_target() -> str:
    """The first journal target this PC is actually set up for, or ""."""
    try:
        import jarvis_note_capture
        have = list(jarvis_note_capture.available_targets())
    except Exception:
        return ""
    for name in ("obsidian", "logseq", "joplin"):
        if name in have:
            return name
    return ""


def file_week_review(day=None, *, capture=None, target=None) -> tuple:
    """File the review as ONE line in the owner's own journal, through the
    existing cardless notes route - not a second writer.

    `jarvis_note_capture.capture()` is the same function `POST
    /api/notes/capture` calls, so the review lands exactly where the owner
    already files notes, appends rather than edits (Logseq and Obsidian only
    ever append) and needs no card: `append_obsidian_daily` and
    `append_logseq_journal` are both tier "auto" and `create_joplin_note` is
    "notify" in backend/rebuilt/jarvis-framework.toml. Returns (status, body).
    """
    summary = week_summary(day)
    text = render_week(summary)
    which = target or _capture_target()
    if not which:
        return 503, {"ok": False, "error": WORDS["no_journal"],
                     "summary": summary, "text": text}
    cap = capture
    if cap is None:
        try:
            import jarvis_note_capture
            cap = jarvis_note_capture.capture
        except Exception:
            return 503, {"ok": False, "error": WORDS["no_journal"],
                         "summary": summary, "text": text}
    code, body = cap(which, text, title=WORDS["week_title"])
    out = dict(body or {})
    out["summary"] = summary
    out["text"] = text
    return code, out


# --------------------------------------------------------------------------
#   The weekly review's own job: on because the owner turned it on
# --------------------------------------------------------------------------

def week_job() -> Optional[dict]:
    """The repeating review job as the scheduler holds it, or None."""
    sched = _scheduler()
    if sched is None:
        return None
    try:
        for job in sched.get().listed():
            if job.get("kind") == WEEK_KIND:
                return job
    except Exception:
        return None
    return None


def start_week(rule=None) -> dict:
    """Turn the weekly review ON: one repeating job, at once, with NO card -
    the same plain_repeat class as a repeating reminder. It only exists
    because the owner asked for it."""
    sched = _scheduler()
    if sched is None:
        raise RuntimeError("the scheduler is not available")
    clean_rule = dict(WEEK_RULE) if rule is None else rule
    if not isinstance(clean_rule, dict):
        raise ValueError("a rule is a small object")
    if week_job() is not None:
        raise ValueError("the week in review is already on")
    job = sched.get().add_repeat(WEEK_KIND, clean_rule, text=WORDS["week_title"],
                                 source="app")
    _audit("habits.week_on", {"job": job.get("id")})
    return {"ok": True, "job": job, "said": WORDS["week_on"]}


def stop_week() -> dict:
    """One tap, immediate: delete the review job. Nothing that was already
    filed is touched - those lines are in the owner's own journal now."""
    job = week_job()
    if job is None:
        return {"ok": True, "stopped": False, "said": "The week in review is already off."}
    sched = _scheduler()
    try:
        sched.get().act(str(job.get("id")), "delete")
    except Exception:
        raise RuntimeError("the review job could not be deleted")
    _audit("habits.week_off", {"job": job.get("id")})
    return {"ok": True, "stopped": True, "said": "The week in review is off."}


def on_week_fire(job_id: str) -> None:
    """register_kind's on_fire for WEEK_KIND: file the review.

    Nothing it raises may stop the scheduler's loop, and a journal that is not
    set up is not an error worth a card - the job simply has nowhere to file to
    until the owner sets one up."""
    try:
        file_week_review()
    except Exception:
        pass


#: How the two kinds are registered on the one scheduler (register() below;
#: the tests use the same). plain_repeat=True on both: the owner's own tap
#: sets one up, it reads nothing new and acts on nothing but its own note.
KIND_OPTIONS = dict(has_text=True, repeatable=True, plain_repeat=True,
                    what="set up a habit check-in")
WEEK_OPTIONS = dict(has_text=True, repeatable=True, plain_repeat=True,
                    what="file a week in review")


def register() -> None:
    """Register BOTH kinds on the one scheduler. Called once by install()."""
    sched = _scheduler()
    if sched is None:
        raise RuntimeError("the scheduler is not available")
    sched.register_kind(
        KIND, "habit check-in", "Jarvis: a habit check-in is due.",
        on_fire=on_habit_fire, note=habit_note, **KIND_OPTIONS)
    sched.register_kind(
        WEEK_KIND, "week in review", "Jarvis: the week in review is due.",
        on_fire=on_week_fire, **WEEK_OPTIONS)


# --------------------------------------------------------------------------
#   The routes both apps call
# --------------------------------------------------------------------------

PATH = "/api/habits"
WEEK_PATH = "/api/habits/week"
_TAILS = ("tick", "untick", "stop")


def _habit_route(route: str):
    """None, or (habit_id, tail) for PATH/<id> or PATH/<id>/(tick|untick|stop).

    "week" is a reserved word under PATH and no habit id can be it (ids are
    "h" and ten hex characters), so WEEK_PATH can never be read as a habit.
    """
    if not isinstance(route, str) or not route.startswith(PATH + "/"):
        return None
    parts = route[len(PATH) + 1:].split("/")
    if len(parts) == 1 and parts[0] and parts[0] != "week":
        return parts[0], ""
    if len(parts) == 2 and parts[0] and parts[0] != "week" and parts[1] in _TAILS:
        return parts[0], parts[1]
    return None


def _err(exc) -> tuple:
    if isinstance(exc, KeyError):
        return 404, {"ok": False, "error": "no such habit"}
    if isinstance(exc, ValueError):
        return 400, {"ok": False, "error": str(exc)}
    if isinstance(exc, OverflowError):
        return 409, {"ok": False, "error": str(exc)}
    if isinstance(exc, RuntimeError):
        return 503, {"ok": False, "error": str(exc)}
    return 503, {"ok": False, "error": type(exc).__name__}


def handle_get(route: str) -> tuple:
    if route == PATH:
        return 200, {"ok": True, "habits": list_habits(),
                     "limits": {"text": MAX_TEXT, "habits": MAX_HABITS,
                                "words": MAX_WORDS, "days": MAX_DAYS},
                     "words": dict(WORDS)}
    if route == WEEK_PATH:
        job = week_job()
        return 200, {"ok": True, "week": week_summary(),
                     "on": job is not None, "job": job, "words": dict(WORDS)}
    hit = _habit_route(route)
    if hit is None or hit[1] != "":
        return 404, {"ok": False, "error": "no such habit"}
    habit = get(hit[0])
    if habit is None:
        return 404, {"ok": False, "error": "no such habit"}
    return 200, {"ok": True, "habit": habit, "words": dict(WORDS)}


def handle_post(route: str, body) -> tuple:
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "need a JSON object"}
    try:
        if route == PATH:
            return 200, {"ok": True, "habit": create(body.get("text"), body.get("rule")),
                         "words": dict(WORDS)}
        if route == WEEK_PATH + "/start":
            return 200, {"ok": True, **start_week(body.get("rule"))}
        if route == WEEK_PATH + "/stop":
            return 200, dict(stop_week(), ok=True)
        hit = _habit_route(route)
        if hit is None:
            return 404, {"ok": False, "error": "no such habit"}
        habit_id, tail = hit
        if tail == "tick":
            return 200, dict(tick(habit_id, day=body.get("day"),
                                  words=body.get("words"), source=body.get("source")),
                             habit=get(habit_id))
        if tail == "untick":
            return 200, dict(untick(habit_id, day=body.get("day")), habit=get(habit_id))
        if tail == "stop":
            return 200, {"ok": True, "habit": stop(habit_id)}
    except Exception as exc:
        return _err(exc)
    return 404, {"ok": False, "error": "no such habit"}


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls.do_GET`/`do_POST` so the habits routes are answered
    here, after the server's own origin and token checks. Every other request
    goes straight to the original - the same shape jarvis_goals.install and
    jarvis_local_calendar.install use, and the reason this feature needs no
    patch and no change to jarvis_hud.py.
    """
    global _ARMED
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(post0, "_jarvis_habits", False):
        _ARMED = True
        return "  habits     Habit check-ins (already on)"

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

    def _path(self) -> str:
        from urllib.parse import urlsplit
        return urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")

    def do_GET(self):
        route = _path(self)
        if route != PATH and route != WEEK_PATH and _habit_route(route) is None:
            return get0(self)
        if not _allowed(self):
            return None
        try:
            code, out = handle_get(route)
        except Exception as exc:
            code, out = 503, {"ok": False, "error": type(exc).__name__}
        return self._send(code, out)

    def do_POST(self):
        route = _path(self)
        if (route != PATH and not route.startswith(WEEK_PATH + "/")
                and _habit_route(route) is None):
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

    do_GET._jarvis_habits = True
    do_POST._jarvis_habits = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    try:
        register()
    except Exception as exc:
        _ARMED = True
        return f"  habits     NOT ON ({type(exc).__name__}) - habit check-ins are off"
    _ARMED = True
    try:
        n = len(list_habits())
    except Exception:
        n = 0
    return f"  habits     Habit check-ins: {n} kept (GET/POST /api/habits)"


_ARMED = False


def _audit(event: str, detail: dict) -> None:
    """Ids and counts only - never a habit's words, never the words on a tick."""
    try:
        if fw is not None:
            fw.audit_log(event, detail)
    except Exception:
        pass


def _reset_for_tests() -> None:
    global _ARMED
    _ARMED = False
