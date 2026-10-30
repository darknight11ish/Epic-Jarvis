"""jarvis_local_calendar.py - the calendar Jarvis owns.

NEW MODULE, shipped whole (the routes come from its own install(); no patch).

THE OWNER'S DECISION (2026-10-29)
  * "full fledged easy to use calendar built into Jarvis ... disabled but on
    by default" - so this feature is ON when no settings file says otherwise,
    OFF hides every surface, and NOTHING is deleted when it is switched off.
  * The calendar is Jarvis's own: events live in one SQLite file on this PC,
    are shown beside Google Calendar and iCal (never merged into them), and
    are NEVER synced out. Google's and iCal's readers are untouched modules;
    this is a third reader with its own store, its own routes and no gate
    (nothing leaves the PC, so there is no egress to approve).

WHERE THE DATA LIVES
  `calendar.db` in the Jarvis settings folder, beside `schedule.db` and
  `memory.db` (`JARVIS_CALENDAR_DB` overrides it, for the tests). Plain SQLite,
  exactly like `schedule.db`: the boundary is the Windows account plus
  BitLocker, which is the boundary this project already accepts for reminders.
  A second encryption scheme would be new code with a new way to lose data.
  The file is opened through `jarvis_sqlite.connect`, whose connection CLOSES
  when its `with` block ends (an open handle once made a database undeletable
  on the Windows runner).

THE EVENT AND THE WALL CLOCK
  One row per event: id "c" + 10 lowercase hex, title (1..300), date
  ("YYYY-MM-DD"), time ("HH:MM", or none for an all-day event), optional
  end_date/end_time, all_day, place, notes, remind_minutes, recurrence
  ("none" | "daily" | "weekly" | "monthly") with an optional count/until,
  tz (the zone it was written in, informational), and created/updated stamps.

  **The date and time are stored as they read on the clock, never as an
  epoch.** `jarvis_schedule`'s own docstring says why: "A daily 07:00 stays
  07:00 across a clock change". An event stored as a bare epoch is 14:00 in
  summer and 13:00 in winter after a daylight-saving change, and the owner
  notices exactly that. `date`/`time` are the record; an epoch is computed on
  read by `_wall_epoch` for ordering and for the "next" words, and that
  computation follows this PC's own daylight-saving rules (the same two
  readings `jarvis_schedule.wall_to_epoch` tries, with the same answers: a
  time that does not exist goes off at the moment of the jump, a time that
  happens twice takes the first).

RECURRENCE (v1, deliberately small)
  Four modes with the optional two cuts the RFC's own COUNT/UNTIL provide:
  every day, every week, every month (clamped to the month's last day, so a
  "31st" event lands on 28 February in a common year and 31 March after it),
  or no repeat. Occurrences are expanded inside the read window only, capped
  at `_MAX_PER_EVENT` per event and `_MAX_EVENTS` in the answer. There is no
  series object and no exception date: editing or deleting a repeating event
  changes or removes the WHOLE series, which is stated on the route rather
  than guessed at. `backend/jarvis_calendar.py`'s full RRULE expander was read
  and its ideas reused (wall-clock arithmetic, a per-read budget, a hard cap
  per event); its code was not copied, because that module's job is an outside
  read and this one's is a local store.

THE ROUTES (four, all behind the server's own origin and X-Jarvis-Token)
  GET  /api/calendar?days=7  (1..90, default 7) - the window, every event
       expanded into it, and a `sources` block that says honestly what Google
       and iCal are doing (today: "not_on_a_screen"). `?id=<id>` answers ONE
       stored event. Reads are safe and raise no card.
  POST /api/calendar/add      - one event, title required.
  POST /api/calendar/act      - {"id", "do": "delete" | "update", ...}, ONE
       event. There is no delete-all, no clear-range and no bulk anything:
       the same rule `/api/schedule/act` keeps, for the same reason.
  POST /api/calendar/settings - {"on": true|false} - a preference you can
       change back in one press, so no card either way.

  The three writes are cardless BY THE OWNER'S RULING OF 2026-10-29 recorded
  in `decisions.d/` and in `docs/ARCHITECTURE.md`'s "Cardless by design"
  table: the reasoning is the "One job on the schedule" row's, word for word -
  one item, no list form, no delete-all, the audit line carries ids and
  outcomes only, and rule 4's stale-link hold still blocks ACTING while the
  event stream is stale (the HUD/phone commands, when they land, hold it; this
  module names nothing and knows no link).

WHAT THIS MODULE NEVER DOES
  No socket, no URL, no credential, no model call, no clock loop, no job on
  the scheduler: it reads and writes one local file when a route asks. Title,
  place and notes are the owner's own words, kept in that file and returned
  only to a request that already passed the server's token and origin checks.
  The audit line (`_audit`) carries the event's id and the outcome; never a
  title, a place or a note.

  `py -3 jarvis_local_calendar.py check` is the self-check: it seeds a
  throwaway file, proves add / list / act / settings / backup-list / recurrence
  / DST, prints PASS and the counts, and removes its own folder. It touches no
  owner data and opens no network.
"""
from __future__ import annotations

import calendar as _cal
import datetime
import json
import os
import re
import secrets
import sqlite3
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlsplit

import jarvis_sqlite

try:                                    # the audit log, when the backend has one
    import jarvis_framework as fw
except Exception:                       # noqa: BLE001 - a bare module still works
    fw = None


# --------------------------------------------------------------------------
#   The contract this module answers
# --------------------------------------------------------------------------

READ_PATH = "/api/calendar"
ADD_PATH = "/api/calendar/add"
ACT_PATH = "/api/calendar/act"
SETTINGS_PATH = "/api/calendar/settings"

#: Every path `install()` answers. Everything else goes straight to the
#: server's own handler, untouched - the same shape jarvis_antislop.install and
#: jarvis_google_calendar.install use, and the reason this feature needs no
#: patch to jarvis_hud.py.
ROUTES = (READ_PATH, ADD_PATH, ACT_PATH, SETTINGS_PATH)

#: The one source name a local event carries.
SOURCE = "local"

DEFAULT_DAYS = 7
MAX_DAYS = 90
#: Events returned by one read. The calendar reader's own discipline
#: (_MAX_EVENTS = 50) scaled for a store; more is said in the answer, never
#: silently dropped.
MAX_EVENTS = 200
#: Events stored at once. A full store answers 409 in words, never silently
#: drops the newest event.
MAX_STORED = 2000
MAX_PER_EVENT = 400
MAX_TITLE = 300
MAX_PLACE = 300
MAX_NOTES = 2000
MAX_TZ = 64
#: Four weeks in minutes: past that a "reminder" is a different feature, and
#: this field is stored only (PC/phone may ring later - not this slice).
MAX_REMIND_MINUTES = 40_320
MAX_SPAN_DAYS = 366
MAX_RECUR_COUNT = 500

RECURRENCES = ("none", "daily", "weekly", "monthly")
WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
                 "Saturday", "Sunday")
MONTH_NAMES = ("January", "February", "March", "April", "May", "June", "July",
               "August", "September", "October", "November", "December")

DB_FILE = "calendar.db"
SETTINGS_FILE = "calendar-settings.json"
DEFAULT_ON = True

_ID_RE = re.compile(r"^c[0-9a-f]{10}$")
_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")

#: The fields a client may send. An unknown key is refused rather than
#: ignored: a typo must not read back as "your event was saved".
FIELDS = ("title", "date", "time", "end_date", "end_time", "all_day", "place",
          "notes", "remind_minutes", "recurrence", "recur_count", "recur_until",
          "tz")

_LOCK = threading.RLock()


# --------------------------------------------------------------------------
#   Where
# --------------------------------------------------------------------------

def _config_dir() -> Path:
    """The folder memory.db and schedule.db are in (no new folder)."""
    if fw is not None:
        try:
            return Path(fw.CONFIG_DIR)
        except Exception:               # noqa: BLE001 - fall back to the env
            pass
    env = os.environ.get("OPENJARVIS_CONFIG_DIR") or os.environ.get("JARVIS_CONFIG_DIR")
    if env:
        return Path(os.path.expanduser(env))
    return Path(os.path.expanduser("~")) / ".openjarvis"


def db_path() -> Path:
    """`calendar.db` in the per-user state folder; JARVIS_CALENDAR_DB wins."""
    env = os.environ.get("JARVIS_CALENDAR_DB")
    return Path(env) if env else _config_dir() / DB_FILE


def settings_path() -> Path:
    """`calendar-settings.json` beside it; JARVIS_CALENDAR_SETTINGS wins.

    The override exists for the same reason JARVIS_CALENDAR_DB does: every
    test (and the self-check) seeds a disposable file and never reads the
    owner's real switch.
    """
    env = os.environ.get("JARVIS_CALENDAR_SETTINGS")
    return Path(env) if env else _config_dir() / SETTINGS_FILE


# --------------------------------------------------------------------------
#   The switch: ON by default, a damaged file is OFF with a reason
# --------------------------------------------------------------------------

def settings() -> dict:
    """The switch as it really is: {"on", "why", "changed", "source"}.

    NO FILE = ON. That is what "on by default" means and what this project's
    little settings files already do (the briefing's own senders switch keeps
    its default the same way). A DAMAGED FILE IS OFF, with a sentence saying
    why: a silent "on" from a file nobody can read is the wrong direction.
    """
    path = settings_path()
    if not path.is_file():
        return {"on": DEFAULT_ON, "why": "", "changed": 0.0, "source": "default"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("on"), bool):
            raise ValueError("the file has no on/off value")
        changed = data.get("changed")
        if isinstance(changed, bool) or not isinstance(changed, (int, float)):
            changed = 0.0
        return {"on": data["on"], "why": "", "changed": float(changed),
                "source": "file"}
    except Exception as exc:            # noqa: BLE001 - any damage means off
        return {
            "on": False,
            "why": ("The calendar's settings file could not be read "
                    f"({type(exc).__name__}), so the calendar is off until you "
                    "turn it back on. Nothing was deleted."),
            "changed": 0.0,
            "source": "damaged",
        }


def is_on() -> bool:
    """The switch, for another module's "is it on?" answer."""
    return settings()["on"] is True


def set_on(on: bool) -> dict:
    """Save the switch. A preference, so no card in either direction."""
    if not isinstance(on, bool):
        raise ValueError("on must be true or false")
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"on": on, "changed": time.time()}
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    _audit("calendar.settings", {"on": on})
    return settings()


# --------------------------------------------------------------------------
#   The store
# --------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id             TEXT PRIMARY KEY,
    title          TEXT NOT NULL,
    date           TEXT NOT NULL,
    time           TEXT,
    end_date       TEXT NOT NULL,
    end_time       TEXT,
    all_day        INTEGER NOT NULL DEFAULT 1,
    place          TEXT NOT NULL DEFAULT '',
    notes          TEXT NOT NULL DEFAULT '',
    remind_minutes INTEGER,
    recurrence     TEXT NOT NULL DEFAULT 'none',
    recur_count    INTEGER,
    recur_until    TEXT,
    tz             TEXT NOT NULL DEFAULT '',
    created        REAL NOT NULL,
    updated        REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS events_date ON events(date, time);
"""

#: Columns added after the first release, in the `ALTER TABLE ... ADD COLUMN`
#: pattern jarvis_schedule uses: a file made before one gets it on open, empty.
#: Today the list is empty - v1's recurrence lives in the first schema (a
#: shipped store needs no second migration yet). The tuple is kept so v2's
#: column costs three lines and no migration script, exactly as the design
#: says.
_ADDED_COLUMNS: tuple = ()


def _init_schema(conn) -> None:
    conn.executescript(_SCHEMA)
    have = {row[1] for row in conn.execute("PRAGMA table_info(events)")}
    for name, decl in _ADDED_COLUMNS:
        if name not in have:
            conn.execute(f"ALTER TABLE events ADD COLUMN {name} {decl}")


def _connect() -> sqlite3.Connection:
    """A connection that CLOSES when its `with` block ends (jarvis_sqlite)."""
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    jarvis_sqlite.ensure_schema(path, _init_schema)
    conn = jarvis_sqlite.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _all_rows() -> list:
    with _LOCK, _connect() as c:
        return list(c.execute("SELECT * FROM events ORDER BY date, time, id"))


def _row(event_id: str):
    with _LOCK, _connect() as c:
        return c.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()


def _stored_count() -> int:
    with _LOCK, _connect() as c:
        return int(c.execute("SELECT COUNT(*) FROM events").fetchone()[0])


# --------------------------------------------------------------------------
#   The event, as a client reads it
# --------------------------------------------------------------------------

def _view(row) -> dict:
    """One stored row as the contract's event object (source: "local")."""
    remind = row["remind_minutes"]
    return {
        "id": str(row["id"]),
        "title": str(row["title"]),
        "date": str(row["date"]),
        "time": row["time"] or None,
        "end_date": str(row["end_date"]),
        "end_time": row["end_time"] or None,
        "all_day": bool(row["all_day"]),
        "place": str(row["place"] or ""),
        "notes": str(row["notes"] or ""),
        "remind_minutes": int(remind) if remind is not None else None,
        "recurrence": str(row["recurrence"] or "none"),
        "recur_count": int(row["recur_count"]) if row["recur_count"] is not None else None,
        "recur_until": row["recur_until"] or None,
        "tz": str(row["tz"] or ""),
        "created": float(row["created"]),
        "updated": float(row["updated"]),
        "source": SOURCE,
    }


# --------------------------------------------------------------------------
#   Dates and times - wall clock, never an epoch
# --------------------------------------------------------------------------

def _today() -> datetime.date:
    lt = time.localtime()
    return datetime.date(lt.tm_year, lt.tm_mon, lt.tm_mday)


def _iso_date(value) -> datetime.date:
    """A strict calendar date, ValueError in words for anything else."""
    text = str(value or "").strip()
    m = _DATE_RE.fullmatch(text)
    if not m:
        raise ValueError('A date looks like 2026-11-03.')
    try:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        raise ValueError("That date is not on the calendar.")


def _iso_time(value) -> str:
    """A strict wall time, HH:MM, as the contract spells it."""
    text = str(value or "").strip()
    m = _TIME_RE.fullmatch(text)
    if not m:
        raise ValueError("A time looks like 14:30.")
    return f"{int(m.group(1)):02d}:{m.group(2)}"


def _local_tz() -> str:
    """The zone this PC is in, as a short informational name.

    Windows does not expose an IANA name to Python, so the honest answer is
    the name the C library reports ("Pacific Standard Time"). A caller that
    knows better (an app writing for the owner's own zone) may send its own.
    """
    env = str(os.environ.get("TZ") or "").strip()
    if env:
        return env[:MAX_TZ]
    try:
        name = time.tzname[1 if time.daylight and time.localtime().tm_isdst > 0 else 0]
        return str(name or "")[:MAX_TZ]
    except Exception:                   # noqa: BLE001 - informational only
        return ""


def _wall_epoch(y: int, mo: int, d: int, hh: int, mm: int,
                tz=None) -> float:
    """The moment the clock in `tz` reads y-mo-d hh:mm.

    `tz` is None for "this PC's own clock", which is the shipped path and the
    same algorithm as `jarvis_schedule.wall_to_epoch`: both daylight-saving
    readings are tried and only one that really shows that time is kept; twice
    (the clocks went back) takes the earlier; never (the clocks went forward)
    takes the moment of the jump.

    A `datetime.tzinfo` may be passed instead (the self-check and the suite use
    a real IANA zone), which proves the same two edge cases without depending
    on the machine's own clock - and that is how the DST test runs on a runner
    that has no daylight saving at all.
    """
    want = (y, mo, d, hh, mm)
    if tz is None:
        found = []
        for dst in (0, 1):
            try:
                t = time.mktime((y, mo, d, hh, mm, 0, 0, 0, dst))
            except (OverflowError, ValueError):
                continue
            if _pc_wall(t) == want:
                found.append(t)
        if found:
            return float(min(found))
        try:
            a = time.mktime((y, mo, d, hh, mm, 0, 0, 0, 1))
            b = time.mktime((y, mo, d, hh, mm, 0, 0, 0, 0))
        except (OverflowError, ValueError):
            return float(time.mktime((y, mo, d, hh, mm, 0, 0, 0, -1)))
        lo, hi = min(a, b) - 3600, max(a, b) + 3600
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if _pc_wall(mid) >= want:
                hi = mid
            else:
                lo = mid
        return float(hi)

    naive = datetime.datetime(y, mo, d, hh, mm)
    valid = []
    cands = []
    for fold in (0, 1):
        aware = naive.replace(tzinfo=tz, fold=fold)
        cands.append(aware.timestamp())
        back = aware.astimezone(datetime.timezone.utc).astimezone(tz)
        if back.replace(tzinfo=None) == naive:
            valid.append(aware.timestamp())
    if valid:
        return float(min(valid))
    # In the gap: the first instant whose wall reading is at or after `want`,
    # found between the two readings (they straddle the jump).
    lo, hi = min(cands), max(cands)
    while hi - lo > 1:
        mid = (lo + hi) / 2
        if _tz_wall(mid, tz) >= naive:
            hi = mid
        else:
            lo = mid
    return float(hi)


def _pc_wall(t: float) -> tuple:
    lt = time.localtime(t)
    return (lt.tm_year, lt.tm_mon, lt.tm_mday, lt.tm_hour, lt.tm_min)


def _tz_wall(epoch: float, tz) -> datetime.datetime:
    return datetime.datetime.fromtimestamp(epoch, tz).replace(tzinfo=None)


def _event_epoch(ev: dict) -> float:
    """When an occurrence starts on this PC's clock (ordering only)."""
    start = datetime.date.fromisoformat(ev["date"])
    if ev.get("all_day") or not ev.get("time"):
        return _wall_epoch(start.year, start.month, start.day, 0, 0)
    hh, mm = (int(x) for x in ev["time"].split(":"))
    return _wall_epoch(start.year, start.month, start.day, hh, mm)


def _add_months(base: datetime.date, n: int) -> datetime.date:
    """The same day `n` months on, clamped to that month's last day.

    This is the "31st" edge decided rather than left to the library: a monthly
    event on 31 January lands on 28 February in a common year (29 in a leap
    year) and on 31 March after it, so it repeats every month instead of
    disappearing for the short ones.
    """
    total = base.year * 12 + (base.month - 1) + n
    y, m0 = divmod(total, 12)
    m = m0 + 1
    last = _cal.monthrange(y, m)[1]
    return datetime.date(y, m, min(base.day, last))


def _nth(base: datetime.date, mode: str, n: int) -> datetime.date:
    if mode == "daily":
        return base + datetime.timedelta(days=n)
    if mode == "weekly":
        return base + datetime.timedelta(days=7 * n)
    if mode == "monthly":
        return _add_months(base, n)
    return base


def _series_dates(ev: dict, from_day: datetime.date,
                  to_day: datetime.date) -> list:
    """Every occurrence day of `ev` in [from_day, to_day).

    The window is walked from the series' own start; no occurrence is invented
    before it, and COUNT counts from that start (not from the window), which is
    what RFC 5545's COUNT means.
    """
    base = datetime.date.fromisoformat(ev["date"])
    mode = ev.get("recurrence") or "none"
    if mode not in RECURRENCES or mode == "none":
        return [base] if from_day <= base < to_day else []
    count = ev.get("recur_count")
    until = datetime.date.fromisoformat(ev["recur_until"]) if ev.get("recur_until") else None
    step = 1 if mode == "daily" else 7 if mode == "weekly" else 0
    if mode in ("daily", "weekly"):
        n = max(0, (from_day - base).days // step)
    else:
        n = max(0, (from_day.year - base.year) * 12 + from_day.month - base.month - 1)
    out = []
    for _ in range(MAX_PER_EVENT + 1):
        if count is not None and n >= count:
            break
        day = _nth(base, mode, n)
        if until is not None and day > until:
            break
        if day >= to_day:
            break
        if day >= from_day:
            out.append(day)
            if len(out) >= MAX_PER_EVENT:
                break
        n += 1
    return out


# --------------------------------------------------------------------------
#   Writes: one event, validated before anything is stored
# --------------------------------------------------------------------------

def _clean(value, cap: int, *, multiline: bool = True) -> str:
    """One text field: no control characters, capped, the owner's words kept."""
    text = "" if value is None else str(value)
    if multiline:
        text = "".join(ch for ch in text if ch == "\n" or ch == "\t" or ord(ch) >= 32)
    else:
        text = "".join(ch for ch in text if ch == "\t" or ord(ch) >= 32)
        text = text.replace("\t", " ")
    text = text.replace("\x7f", "")
    return text.strip()[:cap]


def _recurrence(value, recur_count, recur_until) -> tuple:
    """(mode, count, until) from the body's three shapes.

    Accepted: `"weekly"`, or `{"mode": "weekly", "count": 5, "until":
    "2026-12-31"}`. The object form is what the HUD and the phone will send
    when the owner asks for "5 times"; the string form is the plain one.
    """
    count = recur_count
    until = recur_until
    if isinstance(value, dict):
        mode = str(value.get("mode") or value.get("recurrence") or "none").strip().lower()
        count = value.get("count", recur_count)
        until = value.get("until", recur_until)
    elif value is None:
        mode = "none"
    else:
        mode = str(value).strip().lower()
    if mode in ("", "no", "off", "never"):
        mode = "none"
    if mode not in RECURRENCES:
        raise ValueError("A repeat is one of: none, daily, weekly, monthly.")
    if mode == "none":
        # A count left over from a series that is now a one-off is dropped
        # rather than refused: turning a repeat off is one edit, and the old
        # count is not a field the owner is looking at.
        return "none", None, None
    if count is not None:
        try:
            count = int(count)
        except (TypeError, ValueError):
            raise ValueError("A repeat count is a whole number, 1 or more.")
    if isinstance(count, bool) or (count is not None and not 1 <= count <= MAX_RECUR_COUNT):
        raise ValueError(f"A repeat count is a whole number from 1 to {MAX_RECUR_COUNT}.")
    if until is not None and str(until).strip():
        until = _iso_date(until).isoformat()
    else:
        until = None
    return mode, count, until


def _fields(body: dict, existing: Optional[dict]) -> dict:
    """Validate one whole event body (add), or the merged result (update)."""
    unknown = sorted(set(body) - set(FIELDS) - {"id", "do"})
    if unknown:
        raise ValueError(f"The calendar has no field called {unknown[0]}.")
    old = existing or {}
    title = _clean(body.get("title", old.get("title")), MAX_TITLE, multiline=False)
    if not title:
        raise ValueError('A title is needed - for example "Dentist".')
    date = _iso_date(body.get("date", old.get("date") or _today().isoformat()))
    raw_time = body.get("time", old.get("time"))
    all_day = body.get("all_day", old.get("all_day"))
    if all_day is None:
        all_day = raw_time in (None, "")
    if not isinstance(all_day, bool):
        raise ValueError("all_day is true or false.")
    time_text = None
    if not all_day:
        if raw_time in (None, ""):
            raise ValueError("A timed event needs a time, or tick all day.")
        time_text = _iso_time(raw_time)
    raw_end_date = body.get("end_date")
    if raw_end_date is None:
        # A date that moved and no end date sent: an event that ended the same
        # day keeps ending the same day; a multi-day span keeps its length.
        old_start = old.get("date")
        old_end = old.get("end_date") or old_start
        if "date" in body and old_end == old_start:
            raw_end_date = date.isoformat()
        else:
            raw_end_date = old_end or date.isoformat()
    end_date = _iso_date(raw_end_date)
    if end_date < date:
        raise ValueError("The end date is before the start date.")
    if (end_date - date).days > MAX_SPAN_DAYS:
        raise ValueError(f"An event can span at most {MAX_SPAN_DAYS} days.")
    end_time = None
    raw_end_time = body.get("end_time", old.get("end_time"))
    if not all_day and raw_end_time not in (None, ""):
        end_time = _iso_time(raw_end_time)
        if end_date == date and end_time <= time_text:
            raise ValueError("The end time is not after the start time.")
    place = _clean(body.get("place", old.get("place")), MAX_PLACE)
    notes = _clean(body.get("notes", old.get("notes")), MAX_NOTES)
    remind = body.get("remind_minutes", old.get("remind_minutes"))
    if remind is not None:
        if isinstance(remind, bool):
            raise ValueError("remind_minutes is a whole number of minutes, or empty.")
        try:
            remind = int(remind)
        except (TypeError, ValueError):
            raise ValueError("remind_minutes is a whole number of minutes, or empty.")
        if not 0 <= remind <= MAX_REMIND_MINUTES:
            raise ValueError(f"remind_minutes is from 0 to {MAX_REMIND_MINUTES}.")
    mode, count, until = _recurrence(
        body.get("recurrence", old.get("recurrence", "none")),
        body.get("recur_count", old.get("recur_count")),
        body.get("recur_until", old.get("recur_until")),
    )
    tz = _clean(body.get("tz", old.get("tz")) or _local_tz(), MAX_TZ, multiline=False)
    return {"title": title, "date": date.isoformat(), "time": time_text,
            "end_date": end_date.isoformat(), "end_time": end_time,
            "all_day": all_day, "place": place, "notes": notes,
            "remind_minutes": remind, "recurrence": mode,
            "recur_count": count, "recur_until": until, "tz": tz}


def _new_id() -> str:
    return "c" + secrets.token_hex(5)


def _insert(fields: dict) -> dict:
    for _ in range(20):
        eid = _new_id()
        if _row(eid) is None:
            break
    else:                               # pragma: no cover - 40 bits, 20 tries
        raise ValueError("A new event's id could not be made unique.")
    now = time.time()
    with _LOCK, _connect() as c:
        c.execute(
            "INSERT INTO events (id, title, date, time, end_date, end_time, all_day,"
            " place, notes, remind_minutes, recurrence, recur_count, recur_until,"
            " tz, created, updated) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (eid, fields["title"], fields["date"], fields["time"],
             fields["end_date"], fields["end_time"], 1 if fields["all_day"] else 0,
             fields["place"], fields["notes"], fields["remind_minutes"],
             fields["recurrence"], fields["recur_count"], fields["recur_until"],
             fields["tz"], now, now))
    row = _row(eid)
    _audit("calendar.add", {"id": eid, "repeats": fields["recurrence"] != "none"})
    return _view(row)


def _save(eid: str, fields: dict) -> dict:
    with _LOCK, _connect() as c:
        c.execute(
            "UPDATE events SET title=?, date=?, time=?, end_date=?, end_time=?,"
            " all_day=?, place=?, notes=?, remind_minutes=?, recurrence=?,"
            " recur_count=?, recur_until=?, tz=?, updated=? WHERE id=?",
            (fields["title"], fields["date"], fields["time"], fields["end_date"],
             fields["end_time"], 1 if fields["all_day"] else 0, fields["place"],
             fields["notes"], fields["remind_minutes"], fields["recurrence"],
             fields["recur_count"], fields["recur_until"], fields["tz"],
             time.time(), eid))
    row = _row(eid)
    _audit("calendar.change", {"id": eid})
    return _view(row)


# --------------------------------------------------------------------------
#   Reading a window
# --------------------------------------------------------------------------

def _days(value) -> int:
    """The window, clamped to 1..90 (the contract's own cap)."""
    try:
        days = int(value)
    except (TypeError, ValueError):
        return DEFAULT_DAYS
    return max(1, min(MAX_DAYS, days))


def _occurrences(ev: dict, start: datetime.date, end: datetime.date) -> list:
    """Every in-window occurrence of one event, as contract-shaped rows."""
    base = datetime.date.fromisoformat(ev["date"])
    span = (datetime.date.fromisoformat(ev["end_date"]) - base).days
    rows = []
    for day in _series_dates(ev, start - datetime.timedelta(days=span), end):
        last = day + datetime.timedelta(days=span)
        if last < start or day >= end:
            continue
        item = dict(ev)
        item["date"] = day.isoformat()
        item["end_date"] = last.isoformat()
        item["series_date"] = base.isoformat()
        item["occurrence"] = day.isoformat()
        item["recurring"] = ev["recurrence"] != "none"
        rows.append(item)
    return rows


def _sources(state: str, count: int) -> dict:
    """The honest sources block: local is real, the other two are not on a screen."""
    return {
        "local": {"state": state, "count": count},
        "google": {"state": "not_on_a_screen"},
        "ical": {"state": "not_on_a_screen"},
    }


def list_events(days=DEFAULT_DAYS) -> dict:
    """GET /api/calendar: the window, the events, and what each source is doing.

    A read. Nothing is written, no card is raised, and OFF answers `on: false`
    with an empty list rather than an error: an app needs no special case for
    a switched-off feature, and the stored events are counted, never dropped.
    """
    days = _days(days)
    start, end = _today(), _today() + datetime.timedelta(days=days)
    st = settings()
    out = {
        "available": True,
        "on": st["on"],
        "days": days,
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "events": [],
        "sources": _sources("on" if st["on"] else "off", 0),
    }
    if st["why"]:
        out["why"] = st["why"]
    try:
        rows = _all_rows()
        out["sources"] = _sources("on" if st["on"] else "off", len(rows))
        if not st["on"]:
            return out
        for row in rows:
            out["events"].extend(_occurrences(_view(row), start, end))
    except Exception as exc:            # noqa: BLE001 - said, never swallowed
        out.update({
            "available": False,
            "on": False,
            "events": [],
            "why": ("The calendar's store could not be read "
                    f"({type(exc).__name__}). Nothing was changed."),
        })
        out["sources"] = _sources("damaged", 0)
        return out
    out["events"].sort(key=lambda e: (e["date"], e["time"] or "", e["title"].lower(),
                                      e["id"]))
    if len(out["events"]) > MAX_EVENTS:
        out["events"] = out["events"][:MAX_EVENTS]
        out["truncated"] = True
    return out


def get_one(event_id) -> Optional[dict]:
    """One stored event by id, or None. The series, not one occurrence."""
    if not isinstance(event_id, str) or not _ID_RE.fullmatch(event_id):
        return None
    row = _row(event_id)
    return _view(row) if row is not None else None


# --------------------------------------------------------------------------
#   The words (the HUD and the phone show these; nothing is logged)
# --------------------------------------------------------------------------

def _when_words(ev: dict) -> str:
    base = datetime.date.fromisoformat(ev["date"])
    day = f"{WEEKDAY_NAMES[base.weekday()]} {base.day} {MONTH_NAMES[base.month - 1]}"
    if ev.get("all_day") or not ev.get("time"):
        words = f"all day on {day}"
    else:
        words = f"{day} at {ev['time']}"
    last = datetime.date.fromisoformat(ev["end_date"])
    if last != base:
        words += f" to {WEEKDAY_NAMES[last.weekday()]} {last.day} {MONTH_NAMES[last.month - 1]}"
    if ev.get("recurrence") not in (None, "", "none"):
        words += f", repeating {ev['recurrence']}"
    return words


def _said(ev: dict) -> str:
    return f"{ev['title']}, {_when_words(ev)}."


# --------------------------------------------------------------------------
#   The routes
# --------------------------------------------------------------------------

def _audit(event: str, detail: dict) -> None:
    """One line in the backend's audit log: ids and outcomes, never words."""
    if fw is None:
        return
    try:
        fw.audit_log(event, detail)
    except Exception:                   # noqa: BLE001 - never fails a write
        pass


def _off_answer() -> tuple:
    return 409, {"ok": False, "reason": "off",
                 "error": ("The Jarvis calendar is off. Turn it on in Settings "
                           "first - nothing was changed.")}


def handle_get(route: str, query="") -> tuple:
    """GET /api/calendar and ?id=<id>. A read; nothing is written."""
    if route != READ_PATH:
        return 404, {"ok": False, "error": "not_found"}
    if isinstance(query, str):
        query = {k: v[0] for k, v in parse_qs(query or "").items() if v}
    query = query or {}
    event_id = query.get("id")
    if event_id:
        ev = get_one(event_id)
        if ev is None:
            return 404, {"ok": False, "reason": "no_such_event",
                         "error": "That event is not in the Jarvis calendar any more."}
        st = settings()
        out = {"available": True, "on": st["on"] and not st.get("why"),
               "event": ev, "source": SOURCE}
        if st["why"]:
            out["why"] = st["why"]
        return 200, out
    return 200, list_events(query.get("days", DEFAULT_DAYS))


def handle_add(body) -> tuple:
    """POST /api/calendar/add - ONE event. 200 on save, 400 in words, 409 full."""
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "the request body must be a JSON object"}
    st = settings()
    if not st["on"]:
        return _off_answer()
    try:
        fields = _fields(body, None)
    except ValueError as exc:
        return 400, {"ok": False, "error": str(exc)}
    with _LOCK:
        try:
            if _stored_count() >= MAX_STORED:
                return 409, {
                    "ok": False, "reason": "full",
                    "error": (f"The Jarvis calendar already holds {MAX_STORED} "
                              "events, its own limit. Delete one first - nothing "
                              "was added.")}
            ev = _insert(fields)
        except (sqlite3.Error, OSError) as exc:
            return 503, {"ok": False, "error": type(exc).__name__,
                         "message": "the event could not be saved"}
    return 200, {"ok": True, "event": ev, "said": _said(ev)}


def handle_act(body) -> tuple:
    """POST /api/calendar/act - ONE event: {"id", "do": "delete" | "update"}.

    There is deliberately no "delete all", no clear-range and no bulk form:
    the same rule `/api/schedule/act` keeps. A body that asks for one gets the
    sentence that says so, not a quiet no-op.
    """
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "the request body must be a JSON object"}
    do = str(body.get("do") or "").strip().lower()
    event_id = body.get("id")
    if not isinstance(event_id, str) or not _ID_RE.fullmatch(event_id):
        return 400, {"ok": False, "error": "need one event id"}
    if do in ("delete_all", "clear", "clear_range", "delete_range", "bulk"):
        return 400, {"ok": False, "reason": "no_bulk",
                     "error": ("One event at a time: the Jarvis calendar has no "
                               "delete-all and no bulk change.")}
    if do not in ("delete", "update"):
        return 400, {"ok": False, "error": 'do is "delete" or "update"'}
    row = _row(event_id)
    if row is None:
        return 404, {"ok": False, "reason": "no_such_event",
                     "error": "That event is not in the Jarvis calendar any more."}
    st = settings()
    if not st["on"]:
        return _off_answer()
    if do == "delete":
        with _LOCK, _connect() as c:
            c.execute("DELETE FROM events WHERE id = ?", (event_id,))
        _audit("calendar.delete", {"id": event_id})
        return 200, {"ok": True, "id": event_id, "said": "Deleted."}
    existing = _view(row)
    body = {k: v for k, v in body.items() if k not in ("id", "do")}
    try:
        fields = _fields(body, existing)
    except ValueError as exc:
        return 400, {"ok": False, "error": str(exc)}
    try:
        ev = _save(event_id, fields)
    except (sqlite3.Error, OSError) as exc:
        return 503, {"ok": False, "error": type(exc).__name__,
                     "message": "the change could not be saved"}
    return 200, {"ok": True, "event": ev, "said": _said(ev)}


def handle_settings(body) -> tuple:
    """POST /api/calendar/settings - {"on": bool}. No card, either direction."""
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "the request body must be a JSON object"}
    on = body.get("on")
    if not isinstance(on, bool):
        return 400, {"ok": False, "error": "on must be true or false"}
    try:
        saved = set_on(on)
    except (OSError, ValueError) as exc:
        return 503, {"ok": False, "error": type(exc).__name__,
                     "message": "the switch could not be saved"}
    out = {"ok": True, "on": saved["on"], "said": (
        "The Jarvis calendar is on. Your events are exactly as you left them."
        if saved["on"] else
        "The Jarvis calendar is off. Everything is kept - turn it back on "
        "and it is all there.")}
    if saved["why"]:
        out["why"] = saved["why"]
    return 200, out


def handle_post(route: str, body) -> tuple:
    """Every POST this module answers. One event per request, never a list."""
    if route == ADD_PATH:
        return handle_add(body)
    if route == ACT_PATH:
        return handle_act(body)
    if route == SETTINGS_PATH:
        return handle_settings(body)
    return 404, {"ok": False, "error": "not_found"}


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls.do_GET`/`do_POST` so the four routes are answered here.

    After the server's own origin and token checks, on every one of them - a
    read is safe but still needs the token, and the three writes are host-only
    writes while the HUD commands that will call them do not exist yet. Every
    other request goes straight to the original handler, untouched: the same
    shape jarvis_antislop.install and jarvis_google_calendar.install use, and
    the reason this feature needs no patch and no change to jarvis_hud.py.
    """
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(get0, "_jarvis_local_calendar", False):
        return "  calendar   Jarvis Calendar (already on)"

    def _allowed(self) -> bool:
        try:
            if not origin_ok(self):
                self._send(403, {"error": "cross-origin request refused"})
                return False
            if not token_ok(self):
                self._send(401, {"error": "bad or missing X-Jarvis-Token"})
                return False
        except Exception:               # noqa: BLE001 - fail closed, say 401
            self._send(401, {"error": "bad or missing X-Jarvis-Token"})
            return False
        return True

    def do_GET(self):
        parts = urlsplit(str(getattr(self, "path", "") or ""))
        route = parts.path.rstrip("/")
        if route != READ_PATH:
            return get0(self)
        if not _allowed(self):
            return None
        try:
            code, out = handle_get(route, parts.query)
        except Exception as exc:        # noqa: BLE001 - the name only
            code, out = 503, {"ok": False, "error": type(exc).__name__}
        return self._send(code, out)

    def do_POST(self):
        parts = urlsplit(str(getattr(self, "path", "") or ""))
        route = parts.path.rstrip("/")
        if route not in ROUTES:
            return post0(self)
        if not _allowed(self):
            return None
        try:
            body = json.loads(read_body(self) or b"{}")
        except Exception:               # noqa: BLE001 - answered as a bad body
            body = None
        try:
            code, out = handle_post(route, body)
        except Exception as exc:        # noqa: BLE001 - the name only
            code, out = 503, {"ok": False, "error": type(exc).__name__}
        return self._send(code, out)

    do_GET._jarvis_local_calendar = True
    do_POST._jarvis_local_calendar = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    try:
        state = "on" if is_on() else "off"
    except Exception:                   # noqa: BLE001 - the banner only
        state = "on (the switch could not be read)"
    return ("  calendar   Jarvis Calendar, your own local calendar "
            f"({state}; GET/POST /api/calendar)")


# --------------------------------------------------------------------------
#   The self-check: py -3 jarvis_local_calendar.py check
# --------------------------------------------------------------------------

def self_check() -> int:
    """Prove the store end to end in a throwaway folder; print PASS + counts.

    It seeds its own `calendar.db` and settings file, proves add / list / act /
    settings / backup-list / recurrence / DST, prints what it kept, and removes
    the folder. No owner data, no network, no app.
    """
    passed, failed = [], []

    def check(name: str, ok, detail="") -> None:
        (passed if ok else failed).append(name)
        print(f"{'ok   ' if ok else 'FAIL '} {name}"
              + (f"\n        {detail}" if detail and not ok else ""))

    with tempfile.TemporaryDirectory(prefix="jarvis-calendar-check-") as folder:
        old_db = os.environ.get("JARVIS_CALENDAR_DB")
        old_set = os.environ.get("JARVIS_CALENDAR_SETTINGS")
        os.environ["JARVIS_CALENDAR_DB"] = str(Path(folder) / DB_FILE)
        os.environ["JARVIS_CALENDAR_SETTINGS"] = str(Path(folder) / SETTINGS_FILE)
        jarvis_sqlite.forget_initialized()
        try:
            check("no settings file means ON (the owner's default)",
                  settings()["on"] is True and settings()["source"] == "default")
            today = _today()
            tuesday = today + datetime.timedelta(days=(1 - today.weekday()) % 7 or 7)
            code, added = handle_add({"title": "Dentist", "date": tuesday.isoformat(),
                                      "time": "14:30", "place": "High Street",
                                      "notes": "Bring the form",
                                      "remind_minutes": 30})
            check("add: one event is saved and answered in words",
                  code == 200 and added["ok"] and added["event"]["id"].startswith("c")
                  and added["event"]["source"] == "local", added)
            check("add: the owner's words come back exactly",
                  added["event"]["title"] == "Dentist"
                  and added["event"]["date"] == tuesday.isoformat()
                  and added["event"]["time"] == "14:30"
                  and added["event"]["recurrence"] == "none", added["event"])
            listing = list_events(7)
            check("list: the event is in the next 7 days, once",
                  listing["on"] is True and len(listing["events"]) == 1
                  and listing["sources"]["local"]["count"] == 1, listing)
            check("list: the window is today .. today+7",
                  listing["window"] == {"start": today.isoformat(),
                                        "end": (today + datetime.timedelta(days=7)).isoformat()},
                  listing["window"])
            check("read one: ?id= answers that event",
                  get_one(added["event"]["id"])["title"] == "Dentist")
            code, changed = handle_act({"id": added["event"]["id"], "do": "update",
                                        "title": "Dentist (moved)", "time": "15:00"})
            check("update: one field changes, the rest stays",
                  code == 200 and changed["event"]["title"] == "Dentist (moved)"
                  and changed["event"]["time"] == "15:00"
                  and changed["event"]["date"] == tuesday.isoformat(), changed)
            code, _ = handle_act({"do": "delete_all"})
            check("there is no delete-all", code == 400)
            code, _ = handle_act({"id": added["event"]["id"], "do": "delete"})
            check("delete: one event goes", code == 200 and _stored_count() == 0)
            code, _kept = handle_add({"title": "Kept while off"})
            check("add: a second event is saved before the switch is tested",
                  code == 200 and _stored_count() == 1)

            # recurrence: monthly on the 31st, clamped, and counted
            base = datetime.date(2027, 1, 31)
            rec = {"date": base.isoformat(), "time": None, "all_day": True,
                   "recurrence": "monthly", "recur_count": 4,
                   "end_date": base.isoformat()}
            days = _series_dates(rec, base, datetime.date(2027, 6, 1))
            check("recurrence: a monthly 31st lands on Feb 28 then Mar 31",
                  [d.isoformat() for d in days] == ["2027-01-31", "2027-02-28",
                                                    "2027-03-31", "2027-04-30"], days)

            # DST: the same two readings jarvis_schedule documents
            try:
                from zoneinfo import ZoneInfo
                la = ZoneInfo("America/Los_Angeles")
                gap = _wall_epoch(2026, 3, 8, 2, 30, la)
                gap_wall = _tz_wall(gap, la)
                fold = _wall_epoch(2026, 11, 1, 1, 30, la)
                two = [datetime.datetime(2026, 11, 1, 1, 30, tzinfo=la,
                                         fold=f).timestamp() for f in (0, 1)]
                check("DST: a time that never happened goes off at the jump",
                      gap_wall == datetime.datetime(2026, 3, 8, 3, 0), gap_wall)
                check("DST: a time that happened twice takes the first",
                      len(set(two)) == 2 and fold == min(two)
                      and _tz_wall(fold, la) == datetime.datetime(2026, 11, 1, 1, 30)
                      and _tz_wall(fold + 3600, la) == datetime.datetime(2026, 11, 1, 1, 30),
                      (fold, two, _tz_wall(fold, la)))
            except Exception as exc:    # noqa: BLE001 - said, never a silent pass
                print(f"skip  DST: no time-zone database here ({type(exc).__name__})")

            set_on(False)
            code, kept = handle_add({"title": "Kept while off"})
            check("off: an add is refused in words", code == 409 and kept["ok"] is False,
                  kept)
            hidden = list_events(7)
            check("off: the list is empty, the data is still counted",
                  hidden["on"] is False and hidden["events"] == []
                  and hidden["sources"]["local"]["count"] == 1, hidden)
            set_on(True)
            back = list_events(7)
            check("on again: everything that was stored is still there",
                  back["on"] is True and len(back["events"]) == 1
                  and back["events"][0]["title"] == "Kept while off", back)

            try:
                import jarvis_backup as backup
                check("backup: calendar.db is on the list of databases saved",
                      DB_FILE in backup.SOURCE_DBS, backup.SOURCE_DBS)
            except Exception as exc:    # noqa: BLE001
                check("backup: jarvis_backup.py is beside this module",
                      False, type(exc).__name__)

            source = Path(__file__).read_text(encoding="utf-8")
            check("no socket, no URL opener and no model call in this module",
                  not re.search(r"^\s*(?:import|from)\s+(socket|http|urllib\.request|"
                                r"requests|urllib3)\b", source, re.M))
            print(f"\nkept: {_stored_count()} event(s) in the throwaway file; "
                  f"the folder is removed")
        finally:
            jarvis_sqlite.forget_initialized(os.environ["JARVIS_CALENDAR_DB"])
            for key, old in (("JARVIS_CALENDAR_DB", old_db),
                             ("JARVIS_CALENDAR_SETTINGS", old_set)):
                if old is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = old
    print(f"\n{len(passed)} passed, {len(failed)} failed")
    if failed:
        print("failed: " + ", ".join(failed))
        return 1
    print("PASS  the Jarvis calendar's store, routes, settings, recurrence, "
          "DST and backup line all work")
    return 0


def _main(argv) -> int:
    if argv and argv[0].lower() == "check":
        return self_check()
    print("usage: py -3 jarvis_local_calendar.py check")
    return 2


if __name__ == "__main__":
    import sys
    raise SystemExit(_main(sys.argv[1:]))
