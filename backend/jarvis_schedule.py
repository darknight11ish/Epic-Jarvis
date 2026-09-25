"""jarvis_schedule.py - the one scheduler: timers, alarms, one-time and
repeating reminders, and the to-do list.

NEW MODULE, shipped whole (schedule.patch adds the routes and starts it).

THE OWNER'S DECISIONS (2026-09-25, CLAUDE.md)
  * Timers, reminders and ONE shared scheduler come first. Briefings, sleep
    mode and the overnight tidy will be new KINDS of job on this scheduler,
    not a scheduler each (register_kind below is how they plug in).
  * A plain timer or a one-time reminder needs no approval card. Anything
    that repeats asks once, with a card that lists the next run times.
  * Simple commands like timers are answered without the AI model
    (jarvis_quick.py), so they work when the model is slow, unloaded or
    asleep. Nothing in this file talks to a model or opens a socket.

WHY NOT THE INITIATIVE ENGINE (rebuilt/jarvis_initiative.py)
It was the first place to look, and it cannot host this cleanly, for four
reasons that are facts about that file, not taste:
  1. Its clock is a heartbeat of 30 minutes, with a floor of one minute. A
     ten-minute timer needs to go off within a second or two.
  2. Its findings live in memory only and are gone on a restart. A reminder
     for next Tuesday has to survive the PC restarting.
  3. It only runs when `[initiative] enabled` is true. The owner asked for
     timers; they must not stop because background checks were switched off.
  4. A finding carries its text in the payload of /api/initiative. A
     reminder's words are private and are read by id, one at a time.
So there is still ONE scheduler - this one. The initiative engine's
heartbeat can move onto it later as one more kind ("check"); until then the
engine is left as it is. The daily digest ([arbiter] in the toml) lives in
jarvis_arbiter.py on the owner's PC, which this repository does not hold, so
nothing here writes to it. The toml's own rule covers timers anyway:
"Anything you ASKED for is exempt and is not counted" - every job here was
asked for.

WHAT IS KEPT, AND WHERE
`schedule.db` in the Jarvis settings folder, beside memory.db and
feedback.db (JARVIS_SCHEDULE_DB overrides it, for the tests). One row per
job. A reminder's or a to-do's words are kept in that file as the owner
said them - plain SQLite on this PC, like memory.db. They are never written
to a log (the audit log gets the id and the kind), never put on the event
bus, and never sent anywhere: this file opens no socket.

A job that went off is kept for FIRED_KEEP (a day), so an app that was
asleep can still read what it was by its id; a to-do marked done is kept for
DONE_KEEP (a week). Then they are gone.

THE CLOCK AND THE TIME ZONE
The PC's own local time, read through the C library (time.mktime and
time.localtime), which follows Windows' own time-zone and daylight-saving
settings - no time-zone database is needed on the PC. A daily 07:00 stays
07:00 across a clock change. Two edge cases, decided rather than left to the
library:
  * a time that does not exist (the hour the clocks go forward - 01:30 on
    that night in the UK) goes off the moment the clocks jump (02:00);
  * a time that happens twice (the hour the clocks go back) goes off the
    FIRST time, once.
A timer is a length of time, not a clock time: ten minutes is 600 seconds
whatever the clocks do.

MISSED WHILE THE PC WAS OFF OR ASLEEP
A job found overdue by more than LATE_AFTER goes off ONCE, late, and says
"missed at 07:00". A repeating job then moves straight to its next time
after now - it never goes off once for every time it missed. Never a burst.

THE EVENT
`schedule` on the bus: `{"id", "kind", "state"}` and, for a job going off,
`"late": true|false`. Ids and the kind only - never the words (ARCHITECTURE
section 6: every event is a doorbell). `state` is "fired" when a job goes
off and "changed" when the list changed (added, paused, deleted, a card
decided). The apps read the words by id: `GET /api/schedule?id=<id>`.

REPEATING JOBS AND THE CARD
One approval card, action `schedule_repeat`, tier "ask" (anything else is
refused: a config line must not become the owner's yes). The card says what
it is, when, and the next three times it will go off, in plain words. The
job waits, doing nothing, until the card is approved. Denied, timed out or
refused: the job is removed. Deleting it while the card waits withdraws it.
Stopping or deleting any job is immediate - it only makes things quieter.

KINDS THAT PLUG IN (register_kind)
The first is the standby schedule (jarvis_standby_schedule.py, 2026-09-25):
a WINDOW - {"every": "day", "at": "01:00", "until": "07:00"} - that goes
off at both ends, one of its kind at a time, and notifies nobody (its event
says "notify": false, so neither app shows a toast or a notification at
01:00). It is set up by the same schedule_repeat card, listing the next
three windows, and deleted like any job. KIND_MODULES below imports it
before the loop first starts.

NO BULK
Every change names ONE job. There is no "delete all", no "clear the list",
no "mark everything done" - here, in the routes, or in either app.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Callable, Optional

try:
    import jarvis_framework as fw
except Exception:  # pragma: no cover - shipped beside it on the PC
    fw = None  # type: ignore

# --------------------------------------------------------------------------
#   Numbers
# --------------------------------------------------------------------------

#: Overdue by more than this and a job says it was missed. The tick loop
#: wakes at least every TICK_MAX seconds, so on a PC that is awake nothing
#: is ever this late; a PC that slept or was off is.
LATE_AFTER = 120.0

#: The longest the loop sleeps between looks, in seconds. It also wakes at
#: once when a job is added or changed (poke()).
TICK_MAX = 30.0

#: How long a job that went off stays readable by id, and a done to-do.
FIRED_KEEP = 24 * 3600.0
DONE_KEEP = 7 * 24 * 3600.0

#: Limits. Each is said plainly when it is reached.
MAX_TEXT = 300
MAX_JOBS = 100               # timers, alarms, reminders and repeating jobs
MAX_TODO = 300               # open to-do items
MAX_TIMER = 24 * 3600.0      # a timer is for today; later is a reminder
MIN_TIMER = 1.0
MAX_AHEAD = 366 * 24 * 3600.0
#: "every N hours": never more often than this. Anything more frequent is a
#: nag, not a reminder.
MIN_EVERY_HOURS = 1
MAX_EVERY_HOURS = 24 * 7

#: The approval action for anything that repeats.
ACTION = "schedule_repeat"

#: How many future times the card and the list show for a repeating job.
NEXT_SHOWN = 3

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December")

# --------------------------------------------------------------------------
#   Kinds
# --------------------------------------------------------------------------
#
# `kind` is free text in the database, checked against this table. A later
# feature (a morning briefing, the overnight tidy, sleep mode) adds its own
# with register_kind() - no change to the table, the loop, the routes or the
# event. What each kind's job does when it goes off beyond ringing the
# doorbell is its `on_fire` (None: the doorbell and the apps' notification
# are the whole of it).

class Kind:
    def __init__(self, name: str, noun: str, lock_screen: str, *, has_text: bool,
                 on_fire: Optional[Callable[[str], None]] = None,
                 owner_listed: bool = True, notify: bool = True, window: bool = False,
                 single: bool = False, edges: tuple = ("", ""), about: tuple = (),
                 note: Optional[Callable[[str], str]] = None):
        self.name = name
        self.noun = noun                 # "timer", "reminder"
        self.lock_screen = lock_screen   # what a locked phone may show
        self.has_text = has_text
        self.on_fire = on_fire
        self.owner_listed = owner_listed
        # False: going off is not something to tell the owner about (the
        # standby schedule, at 01:00). The event then carries
        # "notify": false and neither app shows a notification or a toast.
        self.notify = notify
        # True: a job of this kind is a WINDOW - {"every": "day", "at":
        # "01:00", "until": "07:00"} - and goes off at both ends. on_fire
        # reads in_window() to know which end it is, so a late start and a
        # late end found together (the PC was off all night) agree.
        self.window = window
        # True: at most one job of this kind on the list at a time.
        self.single = single
        # The words for a window's two ends in the list: ("on standby",
        # "awake") -> "next: awake at 07:00 tomorrow".
        self.edges = edges
        # Extra lines for the approval card, saying what it does.
        self.about = tuple(about)
        # note(job_id) -> one sentence about how it last went ("" for none),
        # shown under the job in both apps. Never raises into the list.
        self.note = note


KINDS: dict = {}


def register_kind(name: str, noun: str, lock_screen: str, *, has_text: bool = False,
                  on_fire: Optional[Callable[[str], None]] = None,
                  owner_listed: bool = True, notify: bool = True, window: bool = False,
                  single: bool = False, edges: tuple = ("", ""), about: tuple = (),
                  note: Optional[Callable[[str], str]] = None) -> Kind:
    """Add a kind of job. For the features still to come (briefing, tidy,
    sleep): their job goes off through the same loop, the same missed-while-
    off rule and the same event; `on_fire(job_id)` is called after the event,
    on its own thread, and nothing it raises stops the loop.

    The standby schedule (jarvis_standby_schedule.py) is the first: a
    window kind, single, that notifies nobody."""
    if not re.fullmatch(r"[a-z][a-z_]{1,23}", str(name or "")):
        raise ValueError("a kind is a short lower-case word")
    k = Kind(name, noun, lock_screen, has_text=has_text, on_fire=on_fire,
             owner_listed=owner_listed, notify=notify, window=window, single=single,
             edges=edges, about=about, note=note)
    KINDS[name] = k
    return k


register_kind("timer", "timer", "Jarvis: your timer is done.", has_text=True)
register_kind("alarm", "alarm", "Jarvis: alarm.", has_text=True)
register_kind("reminder", "reminder", "Jarvis: a reminder is due.", has_text=True)
register_kind("todo", "to-do", "Jarvis: a to-do item is due.", has_text=True)

# --------------------------------------------------------------------------
#   Where
# --------------------------------------------------------------------------

def _config_dir() -> Path:
    # The same folder memory.db and feedback.db are in.
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
    env = os.environ.get("JARVIS_SCHEDULE_DB")
    return Path(env) if env else _config_dir() / "schedule.db"


_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id        TEXT PRIMARY KEY,
    kind      TEXT NOT NULL,
    text      TEXT NOT NULL DEFAULT '',
    state     TEXT NOT NULL,
    due       REAL,
    rule      TEXT,
    duration  REAL,
    left_s    REAL,
    created   REAL NOT NULL,
    changed   REAL NOT NULL,
    fired_at  REAL,
    fired_due REAL,
    late      INTEGER NOT NULL DEFAULT 0,
    source    TEXT NOT NULL DEFAULT 'app'
);
CREATE INDEX IF NOT EXISTS jobs_due ON jobs(state, due);
CREATE TABLE IF NOT EXISTS commands (
    digest TEXT PRIMARY KEY,
    at     REAL NOT NULL
);
"""

#: States. `active` and `paused` are on the list; `waiting` is a repeating
#: job whose card has not been answered; `fired` is a one-off that went off
#: (kept FIRED_KEEP, readable by id); `done` is a to-do ticked off.
LISTED = ("active", "paused", "waiting")

# --------------------------------------------------------------------------
#   Local time, and daylight saving
# --------------------------------------------------------------------------

def _wall(t: float) -> tuple:
    lt = time.localtime(t)
    return (lt.tm_year, lt.tm_mon, lt.tm_mday, lt.tm_hour, lt.tm_min)


def wall_to_epoch(y: int, mo: int, d: int, hh: int, mm: int) -> float:
    """The moment this PC's clock reads y-mo-d hh:mm.

    Both daylight-saving readings are tried and only one that really shows
    that time on the clock is kept. Twice (the clocks went back): the
    earlier. Never (the clocks went forward): the moment of the jump."""
    want = (y, mo, d, hh, mm)
    found = []
    for dst in (0, 1):
        try:
            t = time.mktime((y, mo, d, hh, mm, 0, 0, 0, dst))
        except (OverflowError, ValueError):
            continue
        if _wall(t) == want:
            found.append(t)
    if found:
        return min(found)
    # In the gap. The first second whose wall time is at or after the
    # wanted one, found between the two readings (at most two hours apart).
    try:
        a = time.mktime((y, mo, d, hh, mm, 0, 0, 0, 1))
        b = time.mktime((y, mo, d, hh, mm, 0, 0, 0, 0))
    except (OverflowError, ValueError):
        return time.mktime((y, mo, d, hh, mm, 0, 0, 0, -1))
    lo, hi = min(a, b) - 3600, max(a, b) + 3600
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if _wall(mid) >= want:
            hi = mid
        else:
            lo = mid
    return float(hi)


def _add_days(y: int, mo: int, d: int, n: int) -> tuple:
    # Noon avoids every clock change; the date is all that is read.
    t = time.mktime((y, mo, d, 12, 0, 0, 0, 0, -1)) + n * 86400
    lt = time.localtime(t)
    # A clock change can move noon by an hour, never by a day.
    return lt.tm_year, lt.tm_mon, lt.tm_mday


def _weekday(y: int, mo: int, d: int) -> int:
    return time.localtime(time.mktime((y, mo, d, 12, 0, 0, 0, 0, -1))).tm_wday


def next_at(hh: int, mm: int, after: float, days: Optional[set] = None) -> float:
    """The next time the clock reads hh:mm after `after`, on one of `days`
    (0 = Monday; None: any day)."""
    lt = time.localtime(after)
    y, mo, d = lt.tm_year, lt.tm_mon, lt.tm_mday
    for n in range(0, 9):
        yy, mmo, dd = _add_days(y, mo, d, n) if n else (y, mo, d)
        if days is not None and _weekday(yy, mmo, dd) not in days:
            continue
        t = wall_to_epoch(yy, mmo, dd, hh, mm)
        if t > after:
            return t
    raise ValueError("no such time in the next week")


# --------------------------------------------------------------------------
#   Repeating rules
# --------------------------------------------------------------------------
#
# A small, fixed set - RRULE-like, not RRULE. Each is a JSON object:
#   {"every": "day",     "at": "07:00"}
#   {"every": "weekday", "at": "07:00"}                   Monday to Friday
#   {"every": "week",    "at": "09:00", "days": [0, 3]}   0 = Monday
#   {"every": "hours",   "hours": 2, "start": <epoch>}    every N hours from start
# and, for a WINDOW kind only (Kind.window - the standby schedule):
#   {"every": "day", "at": "01:00", "until": "07:00"}     goes off at both ends
# Anything else is refused with the reason.

def _hhmm(s) -> tuple:
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", str(s or ""))
    if not m:
        raise ValueError("a time is written HH:MM, like 07:30")
    hh, mm = int(m.group(1)), int(m.group(2))
    if hh > 23 or mm > 59:
        raise ValueError("that is not a time of day")
    return hh, mm


def check_rule(rule, now: Optional[float] = None, *, window: bool = False) -> dict:
    """The rule, tidied, or ValueError with a sentence. `window`: the rule
    is for a window kind, and must be every day from one time to another."""
    if not isinstance(rule, dict):
        raise ValueError("a repeat is an object like {\"every\": \"day\", \"at\": \"07:00\"}")
    every = str(rule.get("every") or "").strip().lower()
    if window:
        # Every day only, for now: it is what the owner asked for ("sleep at
        # 01:00, wake at 07:00, every day"), and the one both apps offer.
        if every != "day":
            raise ValueError("a standby schedule is every day, from one time to another")
        hh, mm = _hhmm(rule.get("at"))
        uh, um = _hhmm(rule.get("until"))
        if (hh, mm) == (uh, um):
            raise ValueError("the start and the end are the same time - pick two different times")
        return {"every": "day", "at": f"{hh:02d}:{mm:02d}", "until": f"{uh:02d}:{um:02d}"}
    if rule.get("until") is not None:
        raise ValueError("only a standby schedule has an end time")
    if every in ("day", "weekday"):
        hh, mm = _hhmm(rule.get("at"))
        return {"every": every, "at": f"{hh:02d}:{mm:02d}"}
    if every == "week":
        hh, mm = _hhmm(rule.get("at"))
        days = rule.get("days")
        if (not isinstance(days, list) or not days
                or not all(isinstance(x, int) and not isinstance(x, bool) and 0 <= x <= 6
                           for x in days)):
            raise ValueError("a weekly repeat needs its days, 0 (Monday) to 6 (Sunday)")
        return {"every": "week", "at": f"{hh:02d}:{mm:02d}", "days": sorted(set(days))}
    if every == "hours":
        n = rule.get("hours")
        if not isinstance(n, int) or isinstance(n, bool):
            raise ValueError("\"every N hours\" needs a whole number of hours")
        if n < MIN_EVERY_HOURS:
            raise ValueError(f"the shortest repeat is every {MIN_EVERY_HOURS} hour")
        if n > MAX_EVERY_HOURS:
            raise ValueError("the longest \"every N hours\" is a week; use a weekly repeat")
        start = rule.get("start")
        if not isinstance(start, (int, float)) or isinstance(start, bool):
            start = float(now if now is not None else time.time())
        return {"every": "hours", "hours": n, "start": float(start)}
    raise ValueError("a repeat is every day, every weekday, every week on some days, "
                     "or every N hours")


def next_run(rule: dict, after: float) -> float:
    """The first time the rule goes off strictly after `after`. A window
    goes off at both ends: whichever comes first."""
    if rule.get("until"):
        hh, mm = _hhmm(rule["at"])
        uh, um = _hhmm(rule["until"])
        return min(next_at(hh, mm, after), next_at(uh, um, after))
    every = rule["every"]
    if every == "hours":
        step = rule["hours"] * 3600.0
        start = float(rule["start"])
        if after < start:
            return start
        k = int((after - start) // step) + 1
        return start + k * step
    hh, mm = _hhmm(rule["at"])
    days = None
    if every == "weekday":
        days = {0, 1, 2, 3, 4}
    elif every == "week":
        days = set(rule["days"])
    return next_at(hh, mm, after, days)


def next_runs(rule: dict, after: float, n: int = NEXT_SHOWN) -> list:
    out, t = [], after
    for _ in range(n):
        t = next_run(rule, t)
        out.append(t)
    return out


def last_at(hh: int, mm: int, at_or_before: float) -> float:
    """The last time the clock read hh:mm at or before `at_or_before`.
    Two days back is always far enough: every day has an hh:mm (a time the
    clocks skip counts as the moment they jump - next_at)."""
    t = next_at(hh, mm, at_or_before - 2 * 86400 - 7200)
    prev = t
    while t <= at_or_before:
        prev = t
        t = next_at(hh, mm, t)
    return prev


def in_window(rule: dict, now: float) -> bool:
    """Is `now` inside a window rule - after its latest start, before the
    end that follows it? False for a rule that is not a window.

    Worked out from the clock, not from which end last went off, so two
    ends found overdue together (the PC was off all night: 01:00 and 07:00
    both missed) come to the same answer - awake - whichever runs first."""
    if not rule or not rule.get("until"):
        return False
    hh, mm = _hhmm(rule["at"])
    uh, um = _hhmm(rule["until"])
    return last_at(hh, mm, now) > last_at(uh, um, now)


def next_windows(rule: dict, after: float, n: int = NEXT_SHOWN) -> list:
    """The next `n` windows that START after `after`: [(start, end), ...]."""
    hh, mm = _hhmm(rule["at"])
    uh, um = _hhmm(rule["until"])
    out, t = [], after
    for _ in range(n):
        start = next_at(hh, mm, t)
        out.append((start, next_at(uh, um, start)))
        t = start
    return out


# --------------------------------------------------------------------------
#   Plain words
# --------------------------------------------------------------------------

def clock(t: float) -> str:
    """07:30 - the PC's local time, 24-hour, the same in both apps."""
    lt = time.localtime(t)
    return f"{lt.tm_hour:02d}:{lt.tm_min:02d}"


def day_words(t: float, now: float) -> str:
    """'today', 'tomorrow', 'Friday', or 'Friday 2 October'."""
    a, b = time.localtime(now), time.localtime(t)
    da = (a.tm_year, a.tm_mon, a.tm_mday)
    db = (b.tm_year, b.tm_mon, b.tm_mday)
    if da == db:
        return "today"
    if _add_days(*da, 1) == db:
        return "tomorrow"
    if t - now < 6 * 86400 and t > now:
        return WEEKDAYS[b.tm_wday]
    return f"{WEEKDAYS[b.tm_wday]} {b.tm_mday} {MONTHS[b.tm_mon - 1]}"


def when_words(t: float, now: float) -> str:
    """'07:00 today', '07:00 tomorrow', '09:00 on Friday 2 October'."""
    d = day_words(t, now)
    if d in ("today", "tomorrow"):
        return f"{clock(t)} {d}"
    return f"{clock(t)} on {d}"


def long_date(t: float) -> str:
    """'Monday 28 September at 07:00' - for the card, where every run is
    named in full."""
    lt = time.localtime(t)
    return f"{WEEKDAYS[lt.tm_wday]} {lt.tm_mday} {MONTHS[lt.tm_mon - 1]} at {clock(t)}"


def window_words(start: float, end: float) -> str:
    """'Saturday 26 September, 01:00 to 07:00', or across midnight 'Friday
    25 September at 23:00 to Saturday at 07:00' - for the card."""
    a, b = time.localtime(start), time.localtime(end)
    day = f"{WEEKDAYS[a.tm_wday]} {a.tm_mday} {MONTHS[a.tm_mon - 1]}"
    if (a.tm_year, a.tm_mon, a.tm_mday) == (b.tm_year, b.tm_mon, b.tm_mday):
        return f"{day}, {clock(start)} to {clock(end)}"
    return f"{day} at {clock(start)} to {WEEKDAYS[b.tm_wday]} at {clock(end)}"


def length_words(seconds: float) -> str:
    """'10 minutes', '1 hour 30 minutes', '45 seconds'."""
    s = int(round(max(0.0, float(seconds))))
    h, rest = divmod(s, 3600)
    m, sec = divmod(rest, 60)
    parts = []
    if h:
        parts.append(f"{h} hour" + ("s" if h != 1 else ""))
    if m:
        parts.append(f"{m} minute" + ("s" if m != 1 else ""))
    if sec and not h:
        parts.append(f"{sec} second" + ("s" if sec != 1 else ""))
    return " ".join(parts) if parts else "0 seconds"


def rule_words(rule: Optional[dict]) -> str:
    if not rule:
        return ""
    every = rule.get("every")
    if rule.get("until"):
        return f"every day from {rule['at']} to {rule['until']}"
    if every == "day":
        return f"every day at {rule['at']}"
    if every == "weekday":
        return f"every weekday (Monday to Friday) at {rule['at']}"
    if every == "week":
        names = [WEEKDAYS[i] for i in rule.get("days", [])]
        joined = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
        return f"every {joined} at {rule['at']}"
    if every == "hours":
        n = rule.get("hours")
        return "every hour" if n == 1 else f"every {n} hours"
    return ""


def _digest(text: str) -> str:
    norm = " ".join(str(text or "").lower().split())
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
#   The gate (repeating jobs only)
# --------------------------------------------------------------------------

def _default_gate(action: str, detail: dict, prompt: str):
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def _default_tier(action: str) -> str:
    try:
        return str(fw.action_tier(action)) if fw is not None else "ask"
    except Exception as exc:
        return f"unreadable ({type(exc).__name__})"


def _spawn(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="jarvis-schedule-card", daemon=True).start()


def _publish(kind: str, data: dict) -> None:
    try:
        import jarvis_events
        jarvis_events.BUS.publish(kind, data)
    except Exception:
        pass


def _audit(event: str, detail: dict) -> None:
    # Ids, kinds and outcomes. Never a job's words.
    try:
        if fw is not None:
            fw.audit_log(event, detail)
    except Exception:
        pass


CARD_REFUSED_WORDS = ("Your PC's settings do not let a repeating reminder be approved, "
                      "so it was not set up.")
LAST_WORDS = {
    "approved": "You approved the card, so it is set up.",
    "denied": "The card was turned down, so nothing was set up.",
    "timed_out": "Nobody answered the card in time, so nothing was set up.",
    "refused": CARD_REFUSED_WORDS,
    "withdrawn": "It was deleted while the card waited, so nothing was set up.",
}


# --------------------------------------------------------------------------
#   The scheduler
# --------------------------------------------------------------------------

class Scheduler:
    """One loop, one database. `clock`, `gate`, `tier_of`, `spawn` and
    `publish` are replaceable so the tests run without waiting, without a
    gate and without a bus."""

    def __init__(self, path: Optional[Path] = None, *, clock: Callable[[], float] = time.time,
                 gate: Callable = _default_gate, tier_of: Callable[[str], str] = _default_tier,
                 spawn: Callable[[Callable[[], None]], None] = _spawn,
                 publish: Callable[[str, dict], None] = _publish):
        self.path = Path(path) if path else db_path()
        self.now = clock
        self._gate = gate
        self._tier_of = tier_of
        self._spawn = spawn
        self._publish = publish
        self._lock = threading.RLock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.last_card: dict = {}      # job id -> outcome, for the list
        self.errors = 0
        self.fired = 0
        with self._db() as c:
            c.executescript(_SCHEMA)

    # ---- storage ------------------------------------------------------------

    def _db(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(self.path, timeout=30)
        c.row_factory = sqlite3.Row
        return c

    def _row(self, c, job_id: str):
        return c.execute("SELECT * FROM jobs WHERE id = ?", (str(job_id),)).fetchone()

    def _count(self, c, *, todo: bool) -> int:
        if todo:
            q = "SELECT COUNT(*) FROM jobs WHERE kind = 'todo' AND state IN ('active','paused')"
        else:
            q = ("SELECT COUNT(*) FROM jobs WHERE kind != 'todo' "
                 "AND state IN ('active','paused','waiting')")
        return int(c.execute(q).fetchone()[0])

    def _insert(self, kind: str, *, text: str, state: str, due, rule, duration,
                source: str) -> str:
        jid = "s" + uuid.uuid4().hex[:10]
        now = self.now()
        with self._lock, self._db() as c:
            c.execute("INSERT INTO jobs (id, kind, text, state, due, rule, duration, created, "
                      "changed, source) VALUES (?,?,?,?,?,?,?,?,?,?)",
                      (jid, kind, text, state, due,
                       json.dumps(rule) if rule else None, duration, now, now, source))
        _audit("schedule.add", {"id": jid, "kind": kind, "repeats": bool(rule)})
        self._changed(jid, kind)
        return jid

    def _changed(self, jid: str, kind: str) -> None:
        self._publish("schedule", {"id": jid, "kind": kind, "state": "changed"})
        self.poke()

    # ---- checks shared by every way in ---------------------------------------

    @staticmethod
    def _clean_text(text, kind: str) -> str:
        t = " ".join(str(text or "").split())
        if len(t) > MAX_TEXT:
            raise ValueError(f"that is longer than {MAX_TEXT} characters - say it more briefly")
        if kind in ("reminder", "todo") and not t:
            raise ValueError("a reminder needs some words: what should Jarvis remind you of?")
        return t

    def _room(self, c, kind: str) -> None:
        if kind == "todo":
            if self._count(c, todo=True) >= MAX_TODO:
                raise OverflowError(f"the to-do list is full ({MAX_TODO} items) - mark some done")
        elif self._count(c, todo=False) >= MAX_JOBS:
            raise OverflowError(f"there are already {MAX_JOBS} timers and reminders - "
                                f"delete some first")

    # ---- adding ---------------------------------------------------------------

    def add_timer(self, seconds: float, label: str = "", source: str = "app") -> dict:
        try:
            seconds = float(seconds)
        except (TypeError, ValueError):
            raise ValueError("a timer needs a length")
        if seconds != seconds or seconds < MIN_TIMER:
            raise ValueError("a timer needs a length of at least a second")
        if seconds > MAX_TIMER:
            raise ValueError("a timer can be up to 24 hours - for later than that, "
                             "set a reminder")
        label = self._clean_text(label, "timer")
        with self._lock, self._db() as c:
            self._room(c, "timer")
        jid = self._insert("timer", text=label, state="active", due=self.now() + seconds,
                           rule=None, duration=seconds, source=source)
        return self.job(jid)

    def add_at(self, kind: str, at: float, text: str = "", source: str = "app") -> dict:
        """A one-off alarm, reminder or to-do with a time. No card."""
        if kind not in KINDS or kind == "timer":
            raise ValueError("that kind of job needs a time: alarm, reminder or to-do")
        try:
            at = float(at)
        except (TypeError, ValueError):
            raise ValueError("a time is needed")
        now = self.now()
        if at <= now:
            raise ValueError("that time has already passed")
        if at - now > MAX_AHEAD:
            raise ValueError("that is more than a year away")
        text = self._clean_text(text, kind)
        with self._lock, self._db() as c:
            self._room(c, kind)
        jid = self._insert(kind, text=text, state="active", due=at, rule=None,
                           duration=None, source=source)
        return self.job(jid)

    def add_todo(self, text: str, source: str = "app") -> dict:
        text = self._clean_text(text, "todo")
        with self._lock, self._db() as c:
            self._room(c, "todo")
            dup = c.execute("SELECT id FROM jobs WHERE kind = 'todo' AND state = 'active' "
                            "AND lower(text) = lower(?)", (text,)).fetchone()
        if dup is not None:
            return dict(self.job(dup["id"]), already=True)
        jid = self._insert("todo", text=text, state="active", due=None, rule=None,
                           duration=None, source=source)
        return self.job(jid)

    def add_repeat(self, kind: str, rule, text: str = "", source: str = "app") -> dict:
        """A repeating job. It WAITS until one approval card is approved."""
        k = KINDS.get(kind)
        window = bool(k is not None and k.window)
        if kind not in ("alarm", "reminder") and not window:
            raise ValueError("only alarms and reminders can repeat")
        now = self.now()
        rule = check_rule(rule, now, window=window)
        text = self._clean_text(text, kind) if k.has_text else ""
        with self._lock, self._db() as c:
            self._room(c, kind)
            if k.single and c.execute(
                    "SELECT 1 FROM jobs WHERE kind = ? AND state IN ('active','paused','waiting')",
                    (kind,)).fetchone() is not None:
                raise OverflowError(f"there is already a {k.noun} - delete it first to set "
                                    f"a different one")
        jid = self._insert(kind, text=text, state="waiting", due=None, rule=rule,
                           duration=None, source=source)
        # Read BEFORE the card is raised: a card answered at once (or a
        # refusal) removes the row, and the caller still needs to say what
        # was asked for.
        view = self.job(jid)
        self._spawn(lambda: self._ask(jid))
        return view

    # ---- the card ---------------------------------------------------------------

    def card_text(self, kind: str, rule: dict, text: str, now: float) -> str:
        k = KINDS[kind]
        if rule.get("until"):
            return self._window_card(k, rule, now)
        runs = next_runs(rule, now)
        what = k.noun
        lines = [f"Set up a repeating {what}.", ""]
        if text:
            lines.append(f"What: {text}")
        lines.append(f"When: {rule_words(rule)}.")
        lines.append("")
        lines.append("The next three times it will go off:")
        lines.extend(f"  - {long_date(t)}" for t in runs)
        lines.extend([
            "",
            "It runs on this PC, by this PC's clock. It goes off on both apps while "
            "they are connected. Nothing is sent anywhere.",
            "Stopping or deleting it is immediate, from either app.",
            "",
            "If you say no: nothing is set up.",
        ])
        return "\n".join(lines)

    @staticmethod
    def _window_card(k: Kind, rule: dict, now: float) -> str:
        """The card for a window kind (the standby schedule): what, when,
        what it does at each end (the kind's own `about`), and the next
        three windows in full."""
        lines = [f"Set up a {k.noun}.", "", f"When: {rule_words(rule)}.", ""]
        if k.about:
            lines.extend(k.about)
            lines.append("")
        lines.append("The next three times:")
        lines.extend(f"  - {window_words(a, b)}" for a, b in next_windows(rule, now))
        lines.extend([
            "",
            "It runs on this PC, by this PC's clock. Nothing is sent anywhere.",
            "Stopping or deleting it is immediate, from either app.",
            "",
            "If you say no: nothing is set up.",
        ])
        return "\n".join(lines)

    def _ask(self, jid: str) -> None:
        with self._lock, self._db() as c:
            row = self._row(c, jid)
        if row is None or row["state"] != "waiting":
            return
        rule = json.loads(row["rule"])
        text = self.card_text(row["kind"], rule, row["text"], self.now())

        def finish(outcome: str) -> None:
            self.last_card[jid] = outcome
            _audit("schedule.card", {"id": jid, "outcome": outcome})
            if outcome == "approved":
                return
            with self._lock, self._db() as c:
                c.execute("DELETE FROM jobs WHERE id = ? AND state = 'waiting'", (jid,))
            self._changed(jid, row["kind"])

        if self._tier_of(ACTION) != "ask":
            return finish("refused")
        try:
            v = self._gate(ACTION, {"text": text, "what": "set up a repeating " +
                                    KINDS[row["kind"]].noun, "leaves_this_pc": False,
                                    "job": jid}, text)
        except Exception:
            return finish("refused")
        vtier = getattr(v, "tier", "unknown")
        allowed = getattr(v, "allowed", False) is True
        outcome = getattr(v, "outcome", None)
        if outcome is None:
            outcome = "approved" if (allowed and vtier == "ask") else "refused"
        if vtier != "ask" or self._tier_of(ACTION) != "ask":
            # allowed on "auto" or "notify" is not a person saying yes (§3).
            return finish("refused")
        if not (allowed and outcome == "approved"):
            return finish(outcome if outcome in ("denied", "timed_out") else "refused")
        with self._lock, self._db() as c:
            cur = self._row(c, jid)
            if cur is None or cur["state"] != "waiting":
                # Deleted while the card waited: approving it sets up nothing.
                self.last_card[jid] = "withdrawn"
                return
            due = next_run(rule, self.now())
            c.execute("UPDATE jobs SET state = 'active', due = ?, changed = ? WHERE id = ?",
                      (due, self.now(), jid))
        finish("approved")
        self._changed(jid, row["kind"])

    # ---- changing one job ---------------------------------------------------------

    def act(self, jid: str, do: str, seconds: Optional[float] = None) -> tuple:
        """ONE job: pause, resume, delete, done, add_time. (code, answer)."""
        do = str(do or "").strip().lower()
        now = self.now()
        with self._lock, self._db() as c:
            row = self._row(c, jid)
            if row is None or row["state"] not in ("active", "paused", "waiting"):
                return 404, {"ok": False, "reason": "no_such_job",
                             "error": "That is not on the list any more."}
            kind, state = row["kind"], row["state"]
            if do == "delete":
                c.execute("DELETE FROM jobs WHERE id = ?", (jid,))
                said = "Deleted."
                if state == "waiting":
                    said = "Deleted. The card for it will set nothing up."
            elif do == "done":
                if kind != "todo":
                    return 409, {"ok": False, "error": "Only a to-do item can be marked done."}
                c.execute("UPDATE jobs SET state = 'done', changed = ?, fired_at = ? "
                          "WHERE id = ?", (now, now, jid))
                said = "Marked done."
            elif do == "pause":
                if state != "active" or kind == "todo":
                    return 409, {"ok": False, "error": "That cannot be paused now."}
                left = max(0.0, (row["due"] or now) - now) if kind == "timer" else None
                c.execute("UPDATE jobs SET state = 'paused', left_s = ?, changed = ? "
                          "WHERE id = ?", (left, now, jid))
                said = "Paused."
            elif do == "resume":
                if state != "paused":
                    return 409, {"ok": False, "error": "That is not paused."}
                if kind == "timer":
                    due = now + float(row["left_s"] or 0.0)
                elif row["rule"]:
                    due = next_run(json.loads(row["rule"]), now)
                else:
                    # A one-off whose time passed while it was paused goes
                    # off now, once, as missed - not silently dropped.
                    due = row["due"]
                c.execute("UPDATE jobs SET state = 'active', due = ?, left_s = NULL, "
                          "changed = ? WHERE id = ?", (due, now, jid))
                said = "Resumed."
            elif do == "add_time":
                if kind != "timer":
                    return 409, {"ok": False, "error": "Time can only be added to a timer."}
                try:
                    extra = float(seconds)
                except (TypeError, ValueError):
                    return 400, {"ok": False, "error": "How much time? (seconds)"}
                if extra == 0 or extra != extra:
                    return 400, {"ok": False, "error": "How much time? (seconds)"}
                if state == "paused":
                    left = float(row["left_s"] or 0.0) + extra
                else:
                    left = float(row["due"] or now) - now + extra
                if left < MIN_TIMER:
                    return 409, {"ok": False, "error": "That would leave no time on the timer."}
                if left > MAX_TIMER:
                    return 409, {"ok": False, "error": "A timer can be up to 24 hours."}
                dur = float(row["duration"] or 0.0) + extra
                if state == "paused":
                    c.execute("UPDATE jobs SET left_s = ?, duration = ?, changed = ? "
                              "WHERE id = ?", (left, dur, now, jid))
                else:
                    c.execute("UPDATE jobs SET due = ?, duration = ?, changed = ? "
                              "WHERE id = ?", (now + left, dur, now, jid))
                said = f"{length_words(left)} left."
            else:
                return 400, {"ok": False, "error": "do is one of: pause, resume, delete, done, "
                                                   "add_time"}
        _audit("schedule.act", {"id": jid, "kind": kind, "do": do})
        self._changed(jid, kind)
        return 200, {"ok": True, "id": jid, "said": said}

    # ---- the loop -------------------------------------------------------------------

    def tick(self, now: Optional[float] = None) -> list:
        """One look at the list: everything due goes off, ONCE. Returns the
        ids that went off. Public, so the tests drive it with their own clock."""
        now = self.now() if now is None else now
        went = []
        with self._lock, self._db() as c:
            rows = c.execute("SELECT * FROM jobs WHERE state = 'active' AND due IS NOT NULL "
                             "AND due <= ? ORDER BY due", (now,)).fetchall()
            for row in rows:
                late = (now - float(row["due"])) > LATE_AFTER
                if row["rule"]:
                    try:
                        nxt = next_run(json.loads(row["rule"]), now)
                    except Exception:
                        nxt = None
                    # Straight to the next time after NOW: a week of missed
                    # dailies goes off once, not seven times.
                    c.execute("UPDATE jobs SET due = ?, fired_at = ?, fired_due = ?, late = ?, "
                              "changed = ?, state = ? WHERE id = ?",
                              (nxt, now, row["due"], int(late), now,
                               "active" if nxt is not None else "fired", row["id"]))
                elif row["kind"] == "todo":
                    # A to-do with a time stays on the list until it is
                    # done; going off only takes its time away.
                    c.execute("UPDATE jobs SET due = NULL, fired_at = ?, fired_due = ?, "
                              "late = ?, changed = ? WHERE id = ?",
                              (now, row["due"], int(late), now, row["id"]))
                else:
                    c.execute("UPDATE jobs SET state = 'fired', fired_at = ?, fired_due = ?, "
                              "late = ?, changed = ? WHERE id = ?",
                              (now, row["due"], int(late), now, row["id"]))
                went.append((row["id"], row["kind"], late))
            # Housekeeping: what went off a day ago, and done to-dos a week old.
            c.execute("DELETE FROM jobs WHERE state = 'fired' AND fired_at < ?",
                      (now - FIRED_KEEP,))
            c.execute("DELETE FROM jobs WHERE state = 'done' AND fired_at < ?",
                      (now - DONE_KEEP,))
            c.execute("DELETE FROM commands WHERE at < ?", (now - 30 * 86400,))
        for jid, kind, late in went:
            self.fired += 1
            _audit("schedule.fired", {"id": jid, "kind": kind, "late": late})
            k = KINDS.get(kind)
            data = {"id": jid, "kind": kind, "state": "fired", "late": bool(late)}
            if k is not None and not k.notify:
                # Nothing to tell the owner (the standby schedule at 01:00):
                # both apps show no notification or toast for it.
                data["notify"] = False
            self._publish("schedule", data)
            if k is not None and k.on_fire is not None:
                fn = k.on_fire
                self._spawn(lambda fn=fn, jid=jid: _safe(fn, jid))
        return [j for j, _, _ in went]

    def next_due(self) -> Optional[float]:
        with self._lock, self._db() as c:
            r = c.execute("SELECT MIN(due) FROM jobs WHERE state = 'active' "
                          "AND due IS NOT NULL").fetchone()
        return float(r[0]) if r and r[0] is not None else None

    def poke(self) -> None:
        self._wake.set()

    def start(self) -> "Scheduler":
        if self._thread and self._thread.is_alive():
            return self
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="jarvis-schedule", daemon=True)
        self._thread.start()
        return self

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        self._wake.set()
        t = self._thread
        if t and t.is_alive():
            t.join(timeout)

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
                nxt = self.next_due()
            except Exception:
                # A bad row must not stop every other timer. Counted, so it
                # shows in status() rather than going silent.
                self.errors += 1
                nxt = None
            wait = TICK_MAX
            if nxt is not None:
                wait = max(0.2, min(TICK_MAX, nxt - self.now() + 0.05))
            self._wake.wait(wait)
            self._wake.clear()

    # ---- reading ----------------------------------------------------------------------

    def _view(self, row, now: float) -> dict:
        kind = row["kind"]
        rule = json.loads(row["rule"]) if row["rule"] else None
        v = {"id": row["id"], "kind": kind, "text": row["text"], "state": row["state"],
             "due": row["due"], "created": row["created"], "source": row["source"],
             "repeats": bool(rule)}
        if row["state"] == "active" and row["due"] is not None:
            v["left"] = max(0.0, float(row["due"]) - now)
            v["when"] = when_words(float(row["due"]), now)
        if kind == "timer":
            v["duration"] = row["duration"]
            if row["state"] == "paused":
                v["left"] = float(row["left_s"] or 0.0)
        k = KINDS.get(kind)
        if rule and rule.get("until") and "when" in v and k is not None:
            # A window's next end, said as which end it is: "awake at 07:00
            # tomorrow", "on standby at 01:00 today".
            edge = k.edges[1] if in_window(rule, now) else k.edges[0]
            if edge:
                v["when"] = f"{edge} at {v['when']}"
        if rule:
            v["rule"] = rule
            v["repeat"] = rule_words(rule)
            base = now if row["state"] != "active" or row["due"] is None else float(row["due"]) - 1
            try:
                v["next"] = next_runs(rule, base)
            except Exception:
                v["next"] = []
        if row["state"] == "waiting":
            v["card"] = "Waiting for your yes on the approval card."
        if row["fired_at"] is not None and row["state"] in ("fired", "active") and (
                kind != "todo" or row["fired_due"] is not None):
            v["fired_at"] = row["fired_at"]
            v["late"] = bool(row["late"])
            if row["late"] and row["fired_due"] is not None:
                v["missed"] = f"missed at {clock(float(row['fired_due']))}"
        v["lock_screen"] = k.lock_screen if k else "Jarvis: something is due."
        if k is not None and not k.notify:
            v["notify"] = False
        if k is not None and k.note is not None:
            try:
                said = str(k.note(row["id"]) or "")
            except Exception:
                said = ""
            if said:
                v["note"] = said
        return v

    def job(self, jid: str) -> Optional[dict]:
        with self._lock, self._db() as c:
            row = self._row(c, jid)
        return None if row is None else self._view(row, self.now())

    def listed(self) -> list:
        now = self.now()
        with self._lock, self._db() as c:
            rows = c.execute("SELECT * FROM jobs WHERE kind != 'todo' AND state IN "
                             "('active','paused','waiting')").fetchall()
        out = [self._view(r, now) for r in rows if KINDS.get(r["kind"], None) is None
               or KINDS[r["kind"]].owner_listed]

        def key(v):
            if v["state"] == "active" and v.get("due") is not None:
                return (0, v["due"])
            if v["state"] == "paused":
                return (1, v.get("left") or 0)
            return (2, v["created"])
        return sorted(out, key=key)

    def todos(self) -> list:
        now = self.now()
        with self._lock, self._db() as c:
            rows = c.execute("SELECT * FROM jobs WHERE kind = 'todo' AND state IN "
                             "('active','paused') ORDER BY created").fetchall()
        return [self._view(r, now) for r in rows]

    def timers(self) -> list:
        return [j for j in self.listed() if j["kind"] == "timer"]

    def status(self) -> dict:
        now = self.now()
        return {"available": True, "now": now, "tz": _tz_name(now),
                "jobs": self.listed(), "todo": self.todos(),
                "running": self.running, "limits": {
                    "text": MAX_TEXT, "jobs": MAX_JOBS, "todo": MAX_TODO,
                    "timer_seconds": MAX_TIMER, "min_every_hours": MIN_EVERY_HOURS}}

    # ---- "this sentence set a reminder" (for the learner) ------------------------------

    def mark_command(self, text: str) -> None:
        """Remember THAT this sentence was a command to the scheduler - its
        digest, never its words - so the learner does not read it for facts."""
        if not str(text or "").strip():
            return
        with self._lock, self._db() as c:
            c.execute("INSERT OR REPLACE INTO commands (digest, at) VALUES (?, ?)",
                      (_digest(text), self.now()))

    def was_command(self, text: str) -> bool:
        with self._lock, self._db() as c:
            return c.execute("SELECT 1 FROM commands WHERE digest = ?",
                             (_digest(text),)).fetchone() is not None


def _safe(fn: Callable[[str], None], jid: str) -> None:
    try:
        fn(jid)
    except Exception:
        pass


def _tz_name(now: float) -> str:
    try:
        lt = time.localtime(now)
        return str(time.tzname[1 if lt.tm_isdst > 0 else 0])
    except Exception:
        return ""


# --------------------------------------------------------------------------
#   The one scheduler this backend runs
# --------------------------------------------------------------------------

_SCHED: Optional[Scheduler] = None
_SCHED_LOCK = threading.Lock()


#: The modules that add kinds of their own with register_kind. Imported
#: before the loop first starts, so a job of their kind found overdue at
#: start-up already has its on_fire. A module that is not there is skipped:
#: its jobs then only ring the doorbell.
KIND_MODULES = ("jarvis_standby_schedule",)


def _load_kind_modules() -> None:
    for name in KIND_MODULES:
        try:
            __import__(name)
        except Exception:
            continue


def get() -> Scheduler:
    """The scheduler, started. Every way in comes through here - the boot
    line in jarvis_hud.py, the routes, the fast path, the model's tools - so
    whichever is first starts the loop, once."""
    global _SCHED
    with _SCHED_LOCK:
        if _SCHED is None:
            _load_kind_modules()
            _SCHED = Scheduler()
        s = _SCHED
    return s.start()


def start() -> Scheduler:
    return get()


def was_command(text: str) -> bool:
    """For jarvis_intake.owner_turns: did this sentence set a job? False on
    any failure - the other checks there still run."""
    try:
        s = _SCHED
        if s is None:
            # Not started in this process (a test, a tool): read the file if
            # there is one, and start nothing.
            if not db_path().is_file():
                return False
            s = Scheduler()
        return s.was_command(text)
    except Exception:
        return False


# --------------------------------------------------------------------------
#   Routes (schedule.patch hands the request here)
# --------------------------------------------------------------------------

def handle_get(query="") -> tuple:
    """GET /api/schedule - the list; ?id=<id> - one job, even one that went
    off in the last day (the apps read a notification's words this way).
    `query` is the raw query string, or a dict already parsed."""
    if isinstance(query, str):
        from urllib.parse import parse_qs
        query = {k: v[0] for k, v in parse_qs(query).items() if v}
    s = get()
    jid = (query or {}).get("id")
    if isinstance(jid, list):
        jid = jid[0] if jid else None
    if jid:
        v = s.job(str(jid))
        if v is None:
            return 404, {"ok": False, "reason": "no_such_job",
                         "error": "That is not on the list any more."}
        return 200, {"available": True, "job": v}
    return 200, s.status()


def _num(v) -> Optional[float]:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v)


def handle_add(body: dict) -> tuple:
    """POST /api/schedule/add - one job.
      {"kind": "todo", "text"}                     a to-do item
      {"kind": "timer", "seconds", "text"?}        a timer
      {"kind": "alarm"|"reminder", "at", "text"?}  once, at an epoch time
      {"kind": "alarm"|"reminder", "repeat": {...}, "text"?}   repeating: a card
    200 {"ok", "job"}, 202 {"ok", "waiting": true, "job"} for a repeat."""
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "need a JSON object"}
    kind = str(body.get("kind") or "").strip().lower()
    s = get()
    try:
        if kind == "todo":
            job = s.add_todo(body.get("text"), source="app")
        elif kind == "timer":
            job = s.add_timer(_num(body.get("seconds")), body.get("text") or "", source="app")
        elif kind in ("alarm", "reminder"):
            if body.get("repeat") is not None:
                job = s.add_repeat(kind, body.get("repeat"), body.get("text") or "",
                                   source="app")
                return 202, {"ok": True, "waiting": True, "job": job,
                             "said": "It repeats, so it waits for your yes on the card."}
            job = s.add_at(kind, _num(body.get("at")), body.get("text") or "", source="app")
        elif kind in KINDS and KINDS[kind].window:
            # The standby schedule: {"kind": "standby", "repeat": {"every":
            # "day", "at": "01:00", "until": "07:00"}}. It repeats, so it is
            # one card, like any repeat.
            if not isinstance(body.get("repeat"), dict):
                return 400, {"ok": False, "error": f"A {KINDS[kind].noun} needs its two times."}
            job = s.add_repeat(kind, body.get("repeat"), "", source="app")
            return 202, {"ok": True, "waiting": True, "job": job,
                         "said": "It repeats, so it waits for your yes on the card."}
        else:
            names = ["todo", "timer", "alarm", "reminder"] + sorted(
                n for n, k in KINDS.items() if k.window)
            return 400, {"ok": False, "error": "kind is one of: " + ", ".join(names)}
    except OverflowError as exc:
        return 409, {"ok": False, "error": _sentence(exc)}
    except (ValueError, TypeError) as exc:
        return 400, {"ok": False, "error": _sentence(exc)}
    return 200, {"ok": True, "job": job}


def handle_act(body: dict) -> tuple:
    """POST /api/schedule/act {"id", "do", "seconds"?} - ONE job. There is
    no list form."""
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "need a JSON object"}
    jid = body.get("id")
    if not isinstance(jid, str) or not re.fullmatch(r"s[0-9a-f]{10}", jid):
        return 400, {"ok": False, "error": "need one job id"}
    return get().act(jid, body.get("do"), _num(body.get("seconds")))


def _sentence(exc: BaseException) -> str:
    t = str(exc).strip() or type(exc).__name__
    return t[0].upper() + t[1:] + ("" if t.endswith(".") else ".")
