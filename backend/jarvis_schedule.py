"""jarvis_schedule.py - the one scheduler: timers, alarms, one-time and
repeating reminders, and the to-do list.

NEW MODULE, shipped whole (schedule.patch adds the routes and starts it).

THE OWNER'S DECISIONS (2026-09-25, CLAUDE.md)
  * Timers, reminders and ONE shared scheduler come first. Briefings, sleep
    mode and the overnight tidy will be new KINDS of job on this scheduler,
    not a scheduler each (register_kind below is how they plug in). The
    morning briefing is the first (jarvis_briefing.py, loaded by get()
    through KIND_MODULES): a kind may repeat through the same one card
    (`repeatable`) and put its own lines on it (`card_note`).
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

"Tell me when" (jarvis_tellme.py, 2026-09-25) is a kind that LOOKS every
few minutes and tells the owner only when something happened. It brings
its own rule check (every N minutes, with an end date - the shared
check_rule still refuses minutes, so every other repeat keeps the hourly
floor), its own card, and is `silent`: a look rings no doorbell. See
Kind's hooks below.

NO BULK
Every change names ONE job. There is no "delete all", no "mark everything
done" - here, in the routes, or in either app. The one exception, asked for
by the owner's plan of 2026-09-25 (docs/CREATIVITY-AUDIT-2026-09-25.md, item
6): a NAMED list ("shopping") can be cleared in one go from the apps, after
an "are you sure?" there, and only when the app names how many items it saw
(clear_list below) - so nothing added since the owner looked is lost. The
to-do list itself is never cleared at once, and nothing is cleared by voice.

SNOOZE, "CANCEL THAT" AND NAMED LISTS (2026-09-25, the creativity audit's
everyday quick wins)
  * Snooze: a timer, alarm or reminder that went off can be snoozed. It
    makes a NEW one-off copy of the job, due after the snooze (10 minutes
    unless said otherwise); a repeating job's own times are not touched, so
    only that one occurrence moves. No card - a one-off needs none.
  * "Cancel that": the fast path (jarvis_quick.py) notes what it just set,
    per conversation, in memory (note_set / take_set). Only that, only for
    UNDO_WINDOW seconds, and only once.
  * Named lists: a to-do item may carry a list name ("shopping"); none is
    the to-do list. One limit (MAX_TODO) for every list together.
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

#: Snooze: how long, unless the owner says (10 minutes), and the shortest
#: and longest. A snooze is a one-off, so it needs no card.
SNOOZE_DEFAULT = 600.0
SNOOZE_MIN = 60.0
SNOOZE_MAX = MAX_TIMER
#: The kinds that can be snoozed once they went off.
SNOOZABLE = ("timer", "alarm", "reminder")
#: Something that went off is shown under "Just went off" in both apps, and
#: is what a spoken "snooze" means, for this long.
WENT_OFF_SHOWN = 3600.0

#: "Cancel that": how long after the fast path set something it may be
#: taken back by saying so, and how long the note is kept to say "that was
#: too long ago" instead of handing the sentence to the model.
UNDO_WINDOW = 120.0
UNDO_REMEMBER = 30 * 60.0

#: Named lists ("shopping", "packing"). None is the to-do list itself.
MAX_LISTS = 20
MAX_LIST_NAME = 30
DEFAULT_LIST_TITLE = "To-do list"

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
                 note: Optional[Callable[[str], str]] = None, repeatable: bool = False,
                 card_note: tuple = (), check: Optional[Callable] = None,
                 card: Optional[Callable] = None, silent: bool = False,
                 add: Optional[Callable] = None, first_now: bool = False,
                 fields: Optional[Callable[[str], dict]] = None, what: str = "",
                 leaves: bool = False):
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
        # "awake") -> "next: awake at 07:00 tomorrow". An optional third
        # word is said after the END's time: the standby schedule's
        # ", if the schedule put it on standby" -> "awake at 07:00 today, if
        # the schedule put it on standby" (the owner's decision of
        # 2026-09-25: it wakes only what it put on standby).
        self.edges = edges
        # Extra lines for the approval card, saying what it does.
        self.about = tuple(about)
        # note(job_id) -> one sentence about how it last went ("" for none),
        # shown under the job in both apps. Never raises into the list.
        self.note = note
        # A later kind that may repeat (the morning briefing) - through the
        # same ONE schedule_repeat card as an alarm or a reminder.
        self.repeatable = repeatable
        # Its card's own lines about what each run does and what it reads,
        # in place of the plain "nothing is sent anywhere" paragraph.
        self.card_note = tuple(card_note)
        # "Tell me when" (jarvis_tellme.py, 2026-09-25) - a kind that LOOKS
        # at something every few minutes and tells the owner only when it
        # matches. These let a kind do that without a scheduler of its own:
        #   check(rule, now) -> rule   its own rule check, used instead of
        #                              check_rule (which keeps the hourly
        #                              floor for every other kind);
        #   card(rule, text, now)      the whole approval card, in its words;
        #   silent                     going off rings NO doorbell - a look
        #                              is not news; the kind publishes its
        #                              own event when there is something;
        #   add(body) -> (code, body)  POST /api/schedule/add for this kind;
        #   first_now                  once approved, the first run is now,
        #                              not one interval later;
        #   fields(job_id) -> dict     extra fields for the job's view;
        #   what                       the card's short "what" line;
        #   leaves                     each run asks a server outside this
        #                              PC (the owner's own), said on the card.
        self.check = check
        self.card = card
        self.silent = silent
        self.add = add
        self.first_now = first_now
        self.fields = fields
        self.what = what
        self.leaves = leaves


KINDS: dict = {}

#: Modules that add a kind of their own (register_kind, on import). get()
#: imports each one before the loop first runs, so a job of that kind that
#: is already due - missed while the PC was off - finds its on_fire there.
#: A module that is missing is skipped: its jobs still go off, as a doorbell.
KIND_MODULES = ("jarvis_standby_schedule", "jarvis_briefing", "jarvis_tellme")


def register_kind(name: str, noun: str, lock_screen: str, *, has_text: bool = False,
                  on_fire: Optional[Callable[[str], None]] = None,
                  owner_listed: bool = True, notify: bool = True, window: bool = False,
                  single: bool = False, edges: tuple = ("", ""), about: tuple = (),
                  note: Optional[Callable[[str], str]] = None, repeatable: bool = False,
                  card_note: tuple = (), check: Optional[Callable] = None,
                  card: Optional[Callable] = None, silent: bool = False,
                  add: Optional[Callable] = None, first_now: bool = False,
                  fields: Optional[Callable[[str], dict]] = None, what: str = "",
                  leaves: bool = False) -> Kind:
    """Add a kind of job. For the features still to come (briefing, tidy,
    sleep): their job goes off through the same loop, the same missed-while-
    off rule and the same event; `on_fire(job_id)` is called after the event,
    on its own thread, and nothing it raises stops the loop.

    The standby schedule (jarvis_standby_schedule.py) is a window kind,
    single, that notifies nobody. `repeatable` (the morning briefing): it may
    be set up to repeat, which asks ONCE with the schedule_repeat card, like
    a repeating reminder."""
    if not re.fullmatch(r"[a-z][a-z_]{1,23}", str(name or "")):
        raise ValueError("a kind is a short lower-case word")
    k = Kind(name, noun, lock_screen, has_text=has_text, on_fire=on_fire,
             owner_listed=owner_listed, notify=notify, window=window, single=single,
             edges=edges, about=about, note=note, repeatable=repeatable,
             card_note=card_note, check=check, card=card, silent=silent, add=add,
             first_now=first_now, fields=fields, what=what, leaves=leaves)
    KINDS[name] = k
    return k


def _repeatable(kind: str) -> bool:
    k = KINDS.get(kind)
    return kind in ("alarm", "reminder") or bool(k is not None and k.repeatable)


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

#: Columns added after the first release (2026-09-25): a file made before
#: them gets them on open, empty. `list_name`: a to-do item's named list
#: (NULL: the to-do list). `snooze_of`: a snoozed copy's original job.
#: `snoozed_to`: the copy made from a job that went off (cleared when a
#: repeating job goes off again).
_ADDED_COLUMNS = (("list_name", "TEXT"), ("snooze_of", "TEXT"), ("snoozed_to", "TEXT"))

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
    if every == "minutes":
        # Only a kind with its own check() may have this ("tell me when",
        # jarvis_tellme.py): check_rule() refuses it, so every other repeat
        # keeps the hourly floor.
        step = rule["minutes"] * 60.0
        start = float(rule["start"])
        if after < start:
            return start
        k = int((after - start) // step) + 1
        return start + k * step
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
    if every == "minutes":
        n = rule.get("minutes")
        return "every minute" if n == 1 else f"every {n} minutes"
    return ""


def _digest(text: str) -> str:
    norm = " ".join(str(text or "").lower().split())
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
#   Named lists
# --------------------------------------------------------------------------

_LIST_WORD = re.compile(r"[a-z][a-z'-]*")
_NOT_A_LIST = frozenset("my the a an our to for of and or on in it this that these those all "
                        "every any list lists todo todos timer timers alarm alarms reminder "
                        "reminders".split())
_THE_TODO_LIST = ("", "todo", "to-do", "to do", "todos", "to-dos", "to dos")


def list_key(name) -> Optional[str]:
    """A list's name as it is kept: lower case, with "list" taken off
    ("Shopping list" -> "shopping"). None for the to-do list itself (no
    name, "to-do", "todo"). ValueError, with a sentence, for a name that
    cannot be one: one to three plain words."""
    if name is None:
        return None
    t = " ".join(str(name).lower().replace("\u2019", "'").split())
    t = re.sub(r"\s*\blist$", "", t).strip()
    if t in _THE_TODO_LIST:
        return None
    words = t.split()
    if (len(t) > MAX_LIST_NAME or not 1 <= len(words) <= 3
            or not all(_LIST_WORD.fullmatch(w) for w in words)
            or any(w in _NOT_A_LIST for w in words)):
        raise ValueError("a list's name is one to three plain words, like \"shopping\"")
    return t


def list_title(key: Optional[str]) -> str:
    """"Shopping list", or "To-do list" for the to-do list - both apps' words."""
    if not key:
        return DEFAULT_LIST_TITLE
    return key[0].upper() + key[1:] + " list"


def _lower_first(s: str) -> str:
    return s[:1].lower() + s[1:]


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
        # "Cancel that" (jarvis_quick.py): conversation id -> what the fast
        # path last set there. In memory only - a restart forgets it.
        self._recent: dict = {}
        with self._db() as c:
            c.executescript(_SCHEMA)
            have = {r[1] for r in c.execute("PRAGMA table_info(jobs)").fetchall()}
            for name, typ in _ADDED_COLUMNS:
                if name not in have:
                    c.execute(f"ALTER TABLE jobs ADD COLUMN {name} {typ}")

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
                source: str, list_name: Optional[str] = None,
                snooze_of: Optional[str] = None) -> str:
        jid = "s" + uuid.uuid4().hex[:10]
        now = self.now()
        with self._lock, self._db() as c:
            c.execute("INSERT INTO jobs (id, kind, text, state, due, rule, duration, created, "
                      "changed, source, list_name, snooze_of) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                      (jid, kind, text, state, due,
                       json.dumps(rule) if rule else None, duration, now, now, source,
                       list_name, snooze_of))
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
        text = self._clean_text(text, kind) if KINDS[kind].has_text else ""
        with self._lock, self._db() as c:
            self._room(c, kind)
        jid = self._insert(kind, text=text, state="active", due=at, rule=None,
                           duration=None, source=source)
        return self.job(jid)

    def add_todo(self, text: str, source: str = "app", list_name=None) -> dict:
        """One to-do item - on the to-do list, or on a named list ("shopping").
        The same words twice on one list are one item."""
        key = list_key(list_name)
        text = self._clean_text(text, "todo")
        with self._lock, self._db() as c:
            self._room(c, "todo")
            dup = c.execute("SELECT id FROM jobs WHERE kind = 'todo' AND state = 'active' "
                            "AND lower(text) = lower(?) AND ifnull(list_name, '') = ?",
                            (text, key or "")).fetchone()
            if dup is None and key is not None:
                names = {r[0] for r in c.execute(
                    "SELECT DISTINCT list_name FROM jobs WHERE kind = 'todo' AND state IN "
                    "('active','paused') AND list_name IS NOT NULL").fetchall()}
                if key not in names and len(names) >= MAX_LISTS:
                    raise OverflowError(f"there are already {MAX_LISTS} lists - finish one first")
        if dup is not None:
            return dict(self.job(dup["id"]), already=True)
        jid = self._insert("todo", text=text, state="active", due=None, rule=None,
                           duration=None, source=source, list_name=key)
        return self.job(jid)

    def add_repeat(self, kind: str, rule, text: str = "", source: str = "app") -> dict:
        """A repeating job. It WAITS until one approval card is approved."""
        k = KINDS.get(kind)
        window = bool(k is not None and k.window)
        if not _repeatable(kind) and not window:
            raise ValueError("only alarms, reminders and briefings can repeat")
        now = self.now()
        if k is not None and k.check is not None:
            rule = k.check(rule, now)
        else:
            rule = check_rule(rule, now, window=window)
        text = self._clean_text(text, kind) if (k is None or k.has_text) else ""
        with self._lock, self._db() as c:
            self._room(c, kind)
            if k.single and c.execute(
                    "SELECT 1 FROM jobs WHERE kind = ? AND state IN ('active','paused','waiting')",
                    (kind,)).fetchone() is not None:
                raise OverflowError(f"there is already a {k.noun} - delete it first to set "
                                    f"a different one")
            if not k.has_text and not window and rule["every"] != "hours":
                # A kind with no words of its own (a briefing): the same
                # repeat twice would only go off twice, so it is refused.
                for r in c.execute("SELECT rule FROM jobs WHERE kind = ? AND rule IS NOT NULL "
                                   "AND state IN ('active','paused','waiting')",
                                   (kind,)).fetchall():
                    try:
                        same = check_rule(json.loads(r["rule"]), now) == rule
                    except Exception:
                        same = False
                    if same:
                        raise ValueError(f"a {k.noun} {rule_words(rule)} is already set up")
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
        if k.card is not None:
            return k.card(rule, text, now)
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
        note = KINDS[kind].card_note
        if note:
            lines.append("")
            lines.extend(note)
        else:
            lines.extend([
                "",
                "It runs on this PC, by this PC's clock. It goes off on both apps while "
                "they are connected. Nothing is sent anywhere.",
            ])
        lines.extend([
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
            k = KINDS[row["kind"]]
            v = self._gate(ACTION, {"text": text,
                                    "what": k.what or ("set up a repeating " + k.noun),
                                    "leaves_this_pc": bool(k.leaves), "job": jid}, text)
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
            kk = KINDS.get(row["kind"])
            if kk is not None and kk.first_now:
                due = self.now()
            else:
                due = next_run(rule, self.now())
            c.execute("UPDATE jobs SET state = 'active', due = ?, changed = ? WHERE id = ?",
                      (due, self.now(), jid))
        finish("approved")
        self._changed(jid, row["kind"])

    # ---- changing one job ---------------------------------------------------------

    def act(self, jid: str, do: str, seconds: Optional[float] = None) -> tuple:
        """ONE job: pause, resume, delete, done, add_time, snooze. (code, answer)."""
        do = str(do or "").strip().lower()
        if do == "snooze":
            return self.snooze(jid, seconds)
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
                                                   "add_time, snooze"}
        _audit("schedule.act", {"id": jid, "kind": kind, "do": do})
        self._changed(jid, kind)
        return 200, {"ok": True, "id": jid, "said": said}

    # ---- snooze -----------------------------------------------------------------------

    def snooze(self, jid: str, seconds: Optional[float] = None) -> tuple:
        """A timer, alarm or reminder that WENT OFF, again after `seconds`
        (SNOOZE_DEFAULT when not said). A new one-off copy: a repeating
        job's own times are not touched, so only that one occurrence moves.
        No card - a one-off needs none. Snoozing the same one twice while
        its copy waits changes nothing ("already")."""
        now = self.now()
        try:
            length = SNOOZE_DEFAULT if seconds is None else float(seconds)
        except (TypeError, ValueError):
            length = float("nan")
        if length != length or length < SNOOZE_MIN or length > SNOOZE_MAX:
            return 400, {"ok": False, "error": "A snooze is from 1 minute to 24 hours."}
        with self._lock:
            with self._db() as c:
                row = self._row(c, jid)
                if row is None:
                    return 404, {"ok": False, "reason": "no_such_job",
                                 "error": "That is not on the list any more."}
                if row["kind"] not in SNOOZABLE:
                    return 409, {"ok": False,
                                 "error": "Only a timer, an alarm or a reminder can be snoozed."}
                fired = row["fired_at"]
                if (fired is None or row["state"] not in ("fired", "active", "paused")
                        or now - float(fired) > FIRED_KEEP):
                    return 409, {"ok": False, "error": "It has not gone off, so there is nothing "
                                                       "to snooze."}
                if row["snoozed_to"]:
                    copy = self._row(c, row["snoozed_to"])
                    if copy is not None and copy["state"] in ("active", "paused") \
                            and copy["due"] is not None:
                        return 200, {"ok": True, "id": jid, "already": True,
                                     "job": self._view(copy, now),
                                     "said": f"Already snoozed until {clock(float(copy['due']))}."}
                try:
                    self._room(c, row["kind"])
                except OverflowError as exc:
                    return 409, {"ok": False, "error": _sentence(exc)}
                kind, text = row["kind"], row["text"]
            copy_id = self._insert(kind, text=text, state="active", due=now + length, rule=None,
                                   duration=length if kind == "timer" else None,
                                   source="snooze", snooze_of=jid)
            with self._db() as c:
                c.execute("UPDATE jobs SET snoozed_to = ?, changed = ? WHERE id = ?",
                          (copy_id, now, jid))
        _audit("schedule.snooze", {"id": jid, "kind": kind, "copy": copy_id})
        self._changed(jid, kind)
        return 200, {"ok": True, "id": jid, "job": self.job(copy_id),
                     "said": f"Snoozed for {length_words(length)} - until {clock(now + length)}."}

    def went_off(self, now: Optional[float] = None) -> list:
        """What went off in the last WENT_OFF_SHOWN seconds and could be
        snoozed - newest first, at most five. One already snoozed is left
        out: its copy is on the list."""
        now = self.now() if now is None else now
        with self._lock, self._db() as c:
            rows = c.execute("SELECT * FROM jobs WHERE fired_at IS NOT NULL AND fired_at >= ? "
                             "AND kind IN ('timer','alarm','reminder') "
                             "AND state IN ('fired','active','paused') AND snoozed_to IS NULL "
                             "ORDER BY fired_at DESC LIMIT 5",
                             (now - WENT_OFF_SHOWN,)).fetchall()
        return [self._view(r, now) for r in rows]

    def fired_since(self, since: float, now: Optional[float] = None) -> list:
        """Everything that went off at or after `since`, oldest first, that
        the owner is told about ("What did I miss?"). A repeating job shows
        its latest time only; a one-off is kept FIRED_KEEP."""
        now = self.now() if now is None else now
        with self._lock, self._db() as c:
            rows = c.execute("SELECT * FROM jobs WHERE fired_at IS NOT NULL AND fired_at >= ? "
                             "AND fired_at <= ? ORDER BY fired_at", (since, now)).fetchall()
        out = []
        for r in rows:
            k = KINDS.get(r["kind"])
            if k is not None and (not k.notify or not k.owner_listed):
                continue
            if r["kind"] == "todo" and r["fired_due"] is None:
                continue       # a to-do ticked off, not one that went off
            out.append(self._view(r, now))
        return out

    # ---- named lists ------------------------------------------------------------------

    def lists(self) -> list:
        """The named lists with open items, oldest first:
        [{"name": "shopping", "title": "Shopping list", "open": 3}]."""
        with self._lock, self._db() as c:
            rows = c.execute("SELECT list_name, COUNT(*) AS n, MIN(created) AS first FROM jobs "
                             "WHERE kind = 'todo' AND state IN ('active','paused') "
                             "AND list_name IS NOT NULL GROUP BY list_name "
                             "ORDER BY first").fetchall()
        return [{"name": r["list_name"], "title": list_title(r["list_name"]), "open": int(r["n"])}
                for r in rows]

    def clear_list(self, name, count) -> tuple:
        """Every open item on ONE named list, deleted - only from the apps,
        after their "are you sure?", and only when `count` is how many items
        the app showed (so nothing added since is lost). Never the to-do
        list itself."""
        try:
            key = list_key(name)
        except ValueError as exc:
            return 400, {"ok": False, "error": _sentence(exc)}
        if key is None:
            return 409, {"ok": False, "error": "The to-do list is not cleared all at once - mark "
                                               "items done or delete them one at a time."}
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            return 400, {"ok": False, "error": "Say how many items you saw on the list."}
        title = _lower_first(list_title(key))
        with self._lock:
            with self._db() as c:
                ids = [r["id"] for r in c.execute(
                    "SELECT id FROM jobs WHERE kind = 'todo' AND state IN ('active','paused') "
                    "AND list_name = ?", (key,)).fetchall()]
                if not ids:
                    # 409, like a count that no longer fits: the list changed
                    # since the app looked (a 404 would read as an older PC).
                    return 409, {"ok": False, "error": f"There is nothing on the {title} any more."}
                if len(ids) != count:
                    return 409, {"ok": False, "error": (
                        f"The {title} changed since you looked - it has {len(ids)} "
                        f"item{'s' if len(ids) != 1 else ''} now. Look again before clearing it.")}
                for jid in ids:
                    c.execute("DELETE FROM jobs WHERE id = ?", (jid,))
        _audit("schedule.clear_list", {"count": len(ids)})
        self._changed(ids[0], "todo")
        n = len(ids)
        return 200, {"ok": True, "cleared": n,
                     "said": f"Cleared your {title} ({n} item{'s' if n != 1 else ''})."}

    # ---- "cancel that" ------------------------------------------------------------------

    def note_set(self, conversation, ids, what: str, intent: str, nouns=()) -> None:
        """The fast path just SET these jobs in this conversation (in memory
        only). The next note replaces it: only the last thing can be taken
        back."""
        if not conversation or not ids:
            return
        with self._lock:
            if len(self._recent) > 200:
                oldest = min(self._recent, key=lambda k: self._recent[k]["at"])
                self._recent.pop(oldest, None)
            self._recent[str(conversation)] = {"ids": list(ids), "what": str(what),
                                               "intent": str(intent), "nouns": list(nouns),
                                               "at": self.now()}

    def last_set(self, conversation, now: Optional[float] = None) -> Optional[dict]:
        """What the fast path last set in this conversation, with its `age`
        in seconds - or None (nothing, or more than UNDO_REMEMBER ago)."""
        if not conversation:
            return None
        now = self.now() if now is None else now
        with self._lock:
            rec = self._recent.get(str(conversation))
            if rec is None:
                return None
            if now - rec["at"] > UNDO_REMEMBER:
                self._recent.pop(str(conversation), None)
                return None
            return dict(rec, ids=list(rec["ids"]), age=max(0.0, now - rec["at"]))

    def forget_set(self, conversation) -> None:
        with self._lock:
            self._recent.pop(str(conversation or ""), None)

    def take_back(self, ids) -> int:
        """Delete the jobs the fast path just set ("cancel that"). Only jobs
        still on the list; a snoozed copy also frees its original, so it can
        be snoozed again. Returns how many were taken back."""
        n = 0
        with self._lock:
            for jid in ids:
                with self._db() as c:
                    row = self._row(c, jid)
                    if row is None or row["state"] not in ("active", "paused", "waiting"):
                        continue
                    c.execute("DELETE FROM jobs WHERE id = ?", (jid,))
                    if row["snooze_of"]:
                        c.execute("UPDATE jobs SET snoozed_to = NULL WHERE id = ? "
                                  "AND snoozed_to = ?", (row["snooze_of"], jid))
                n += 1
                _audit("schedule.act", {"id": jid, "kind": row["kind"], "do": "take_back"})
                self._changed(jid, row["kind"])
        return n

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
                ended = False
                if row["rule"]:
                    try:
                        rule = json.loads(row["rule"])
                        nxt = next_run(rule, now)
                        # A rule with an end date ("tell me when",
                        # jarvis_tellme.py): this is its last run when the
                        # next one would come after the end.
                        if rule.get("ends") is not None and nxt > float(rule["ends"]):
                            nxt = None
                    except Exception:
                        nxt = None
                    ended = nxt is None
                    # Straight to the next time after NOW: a week of missed
                    # dailies goes off once, not seven times.
                    # Going off again: an earlier snooze of it is its own job
                    # now, so this time can be snoozed afresh.
                    c.execute("UPDATE jobs SET due = ?, fired_at = ?, fired_due = ?, late = ?, "
                              "changed = ?, state = ?, snoozed_to = NULL WHERE id = ?",
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
                went.append((row["id"], row["kind"], late, ended))
            # Housekeeping: what went off a day ago, and done to-dos a week old.
            c.execute("DELETE FROM jobs WHERE state = 'fired' AND fired_at < ?",
                      (now - FIRED_KEEP,))
            c.execute("DELETE FROM jobs WHERE state = 'done' AND fired_at < ?",
                      (now - DONE_KEEP,))
            c.execute("DELETE FROM commands WHERE at < ?", (now - 30 * 86400,))
        for jid, kind, late, ended in went:
            self.fired += 1
            k = KINDS.get(kind)
            if k is not None and k.silent:
                # A look, not news ("tell me when" checking the inbox every
                # five minutes): no doorbell, and no audit line per look -
                # the kind's own on_fire says when something matched. Only
                # the list changing (its last look, at its end) is told.
                if ended:
                    self._changed(jid, kind)
            else:
                _audit("schedule.fired", {"id": jid, "kind": kind, "late": late})
                data = {"id": jid, "kind": kind, "state": "fired", "late": bool(late)}
                if k is not None and not k.notify:
                    # Nothing to tell the owner (the standby schedule at
                    # 01:00): both apps show no notification or toast for it.
                    data["notify"] = False
                self._publish("schedule", data)
            if k is not None and k.on_fire is not None:
                fn = k.on_fire
                self._spawn(lambda fn=fn, jid=jid: _safe(fn, jid))
        return [w[0] for w in went]

    def end(self, jid: str) -> bool:
        """ONE job with a rule is over before its end date - a "tell me
        when" that matched and was to tell only once. It is kept readable by
        id for FIRED_KEEP, like a job that went off, so an app can still read
        what it was. False when it is not on the list (deleted meanwhile)."""
        now = self.now()
        with self._lock, self._db() as c:
            row = self._row(c, jid)
            if row is None or row["state"] not in ("active", "paused"):
                return False
            c.execute("UPDATE jobs SET state = 'fired', due = NULL, fired_at = ?, "
                      "fired_due = NULL, late = 0, changed = ? WHERE id = ?", (now, now, jid))
        _audit("schedule.ended", {"id": jid, "kind": row["kind"]})
        self._changed(jid, row["kind"])
        return True

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
            inside = in_window(rule, now)
            edge = k.edges[1] if inside else k.edges[0]
            if edge:
                tail = k.edges[2] if inside and len(k.edges) > 2 else ""
                v["when"] = f"{edge} at {v['when']}{tail}"
        if rule:
            # What a "tell me when" watches (a sender's name, a device) is in
            # the rule's `watch`, for the card and the checks. It is the
            # owner's own words, like `text`, which is what an app shows -
            # so it is not handed out a second time here, where the desktop's
            # hiding of the private lists (it blanks `text`) would miss it.
            watch = rule.get("watch") if isinstance(rule.get("watch"), dict) else None
            v["rule"] = {key: x for key, x in rule.items() if key != "watch"}
            if watch is not None:
                v["urgent"] = watch.get("urgent") is True
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
            v["went_off_at"] = clock(float(row["fired_at"]))
            if row["late"] and row["fired_due"] is not None and not (k is not None and k.silent):
                # A silent kind's late look (the PC slept) is just a look
                # made later - there is nothing the owner missed.
                v["missed"] = f"missed at {clock(float(row['fired_due']))}"
        if kind == "todo":
            # "" is the to-do list itself; a name is a named list ("shopping").
            v["list"] = row["list_name"] or ""
        if row["snooze_of"]:
            v["snoozed"] = True
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
        if k is not None and k.fields is not None:
            try:
                extra = k.fields(row["id"]) or {}
            except Exception:
                extra = {}
            for key, x in extra.items():
                # A kind adds fields; it never replaces the scheduler's own.
                if key not in v:
                    v[key] = x
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
                # 2026-09-25: what went off in the last hour (Snooze), and
                # the named lists. An app from before them ignores both.
                "went_off": self.went_off(now), "lists": self.lists(),
                "running": self.running, "limits": {
                    "text": MAX_TEXT, "jobs": MAX_JOBS, "todo": MAX_TODO,
                    "timer_seconds": MAX_TIMER, "min_every_hours": MIN_EVERY_HOURS,
                    "lists": MAX_LISTS, "snooze_seconds": SNOOZE_DEFAULT}}

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


def _load_kind_modules() -> None:
    import importlib
    for name in KIND_MODULES:
        try:
            importlib.import_module(name)
        except Exception:
            pass


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
      {"kind": "todo", "text", "list"?}            a to-do item (on a named list)
      {"kind": "timer", "seconds", "text"?}        a timer
      {"kind": "alarm"|"reminder", "at", "text"?}  once, at an epoch time
      {"kind": "alarm"|"reminder", "repeat": {...}, "text"?}   repeating: a card
    200 {"ok", "job"}, 202 {"ok", "waiting": true, "job"} for a repeat."""
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "need a JSON object"}
    kind = str(body.get("kind") or "").strip().lower()
    s = get()
    if kind in KINDS and KINDS[kind].add is not None:
        # A kind with its own way in ("tell me when", jarvis_tellme.add_route):
        # it checks its own body and ends in add_repeat - ONE card.
        return KINDS[kind].add(body)
    try:
        if kind == "todo":
            job = s.add_todo(body.get("text"), source="app", list_name=body.get("list"))
        elif kind == "timer":
            job = s.add_timer(_num(body.get("seconds")), body.get("text") or "", source="app")
        elif _repeatable(kind):
            # An alarm, a reminder, or a later kind that may repeat (the
            # morning briefing, from its settings in either app).
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
                n for n, k in KINDS.items() if k.window or k.repeatable)
            return 400, {"ok": False, "error": "kind is one of: " + ", ".join(names)}
    except OverflowError as exc:
        return 409, {"ok": False, "error": _sentence(exc)}
    except (ValueError, TypeError) as exc:
        return 400, {"ok": False, "error": _sentence(exc)}
    return 200, {"ok": True, "job": job}


def handle_act(body: dict) -> tuple:
    """POST /api/schedule/act {"id", "do", "seconds"?} - ONE job; "snooze"
    takes `seconds` (10 minutes when not said). The one other form:
    {"do": "clear_list", "list", "count"} - one NAMED list, cleared after the
    app's "are you sure?"."""
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "need a JSON object"}
    if str(body.get("do") or "").strip().lower() == "clear_list":
        # The one form that is not one job: every item on ONE named list,
        # after the app's "are you sure?", and only when `count` matches what
        # the app showed (Scheduler.clear_list). Never the to-do list.
        return get().clear_list(body.get("list"), body.get("count"))
    jid = body.get("id")
    if not isinstance(jid, str) or not re.fullmatch(r"s[0-9a-f]{10}", jid):
        return 400, {"ok": False, "error": "need one job id"}
    return get().act(jid, body.get("do"), _num(body.get("seconds")))


def _sentence(exc: BaseException) -> str:
    t = str(exc).strip() or type(exc).__name__
    return t[0].upper() + t[1:] + ("" if t.endswith(".") else ".")
