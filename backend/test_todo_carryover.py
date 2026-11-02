"""test_todo_carryover.py - the to-do list's own day, and the two ways to show it.

    python backend/test_todo_carryover.py

THE OWNER'S CHOICE (2026-11-02 ~00:41 PT, after the measured gap in
`.dsh-scratch/OWNER-QUEUE-2026-11-02/OWNER-QUEUE.md` item 4). Yesterday's
unfinished items DID carry over - they stayed on the list until done - but
nothing said they were yesterday's, so "what's on my to-do list today?" read as
if everything was new. He chose BOTH:

  * full daily rollover, the DEFAULT: today's list is every open item written
    today or earlier, and each older one says how old it is;
  * day by day: each item stays on the day it was written;
  * switchable from either app's Settings, and by asking Jarvis in chat.

Gemini's ruling 8 (2026-11-02) fixed the design this file proves:

  1. `created_date` is immutable. It is written once, when the item is created,
     and nothing rewrites it - not midnight, not an edit, not the mode switch.
  2. The tag is DYNAMIC and measured from `created_date`:
         1 day      "from yesterday"
         2-6 days   "from <Weekday> (<N>d ago)"
         7+ days    "from <MMM D>"
     so a 3-day-old item never says "from yesterday".
  3. The mode switch is 100% lossless: the same rows, in the same order, with
     the same `created_date`, in both directions.
  4. Migration: an old row is backfilled from its own `created`; a legacy row
     with no usable stamp is stamped TODAY.

No model, no network, no port. Every check runs on a throwaway schedule.db.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# A throwaway config folder BEFORE jarvis_schedule is imported (schedule.patch
# starts the one scheduler from the config folder, and db_path() reads it).
TMP = Path(tempfile.mkdtemp(prefix="jarvis-todo-carryover-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(TMP)
os.environ["JARVIS_CONFIG_DIR"] = str(TMP)
os.environ.pop("JARVIS_SCHEDULE_DB", None)

import jarvis_quick as Q  # noqa: E402
import jarvis_schedule as S  # noqa: E402
import jarvis_settings_registry as R  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def at(y, mo, d, hh=9, mm=0):
    """The epoch of a local wall-clock moment on THIS PC (no zone maths by hand)."""
    return time.mktime((y, mo, d, hh, mm, 0, 0, 0, -1))


def fresh(name):
    return TMP / f"{name}.db"


class Clock:
    """One mutable clock, so a test can move the PC's own day under the code."""

    def __init__(self, when):
        self.now = when

    def __call__(self):
        return self.now


# --------------------------------------------------------------------------
# 1. Migration: an old schedule.db is backfilled, once, and a legacy row with
#    no usable stamp is stamped today (ruling 8, item 4)
# --------------------------------------------------------------------------

print("--- 1. an old schedule.db is backfilled ---")
LEGACY = fresh("legacy")
_OLD_COLUMNS = ("id TEXT PRIMARY KEY, kind TEXT NOT NULL, "
                "text TEXT NOT NULL DEFAULT '', state TEXT NOT NULL, due REAL, "
                "rule TEXT, duration REAL, left_s REAL, created REAL NOT NULL, "
                "changed REAL NOT NULL, fired_at REAL, fired_due REAL, "
                "late INTEGER NOT NULL DEFAULT 0, source TEXT NOT NULL DEFAULT 'app'")
for _name, _type in S._ADDED_COLUMNS:
    if _name != "created_date":
        _OLD_COLUMNS += f", {_name} {_type}"
import sqlite3  # noqa: E402  (only the fixture needs the raw connection)

with sqlite3.connect(LEGACY) as c:
    c.execute(f"CREATE TABLE jobs ({_OLD_COLUMNS})")
    # Three rows written by a build before `created_date` existed. The first is
    # three days old, the second was written today, and the third is the legacy
    # case the owner's brief names: no usable stamp at all.
    c.execute("INSERT INTO jobs (id, kind, text, state, created, changed) "
              "VALUES ('s0000000001', 'todo', 'call the dentist', 'active', ?, ?)",
              (at(2026, 10, 30), at(2026, 10, 30)))
    c.execute("INSERT INTO jobs (id, kind, text, state, created, changed) "
              "VALUES ('s0000000002', 'todo', 'buy stamps', 'active', ?, ?)",
              (at(2026, 11, 2), at(2026, 11, 2)))
    c.execute("INSERT INTO jobs (id, kind, text, state, created, changed) "
              "VALUES ('s0000000003', 'todo', 'a legacy row', 'active', 0, 0)")

clock = Clock(at(2026, 11, 2))
sched = S.Scheduler(LEGACY, clock=clock)
have = {r["id"]: dict(r) for r in
        sched._db().execute("SELECT * FROM jobs").fetchall()}
check("every migrated row has a created_date",
      all(str(r.get("created_date") or "") for r in have.values()), have)
check("...the 3-day-old row is stamped with the day it was really written",
      have["s0000000001"]["created_date"] == "2026-10-30",
      have["s0000000001"]["created_date"])
check("...today's row is stamped today",
      have["s0000000002"]["created_date"] == "2026-11-02",
      have["s0000000002"]["created_date"])
check("...a legacy row with no usable stamp is stamped TODAY (the brief's rule)",
      have["s0000000003"]["created_date"] == "2026-11-02",
      have["s0000000003"]["created_date"])

# Idempotent: opening again, a day later, rewrites nothing.
clock.now = at(2026, 11, 3, 0, 1)
again = S.Scheduler(LEGACY, clock=clock)
with again._db() as c:
    rows = {r["id"]: r["created_date"] for r in c.execute("SELECT * FROM jobs")}
check("opening it again the NEXT day rewrites no created_date",
      rows == {k: v["created_date"] for k, v in have.items()}, rows)
check("...and yesterday's item now says 'from yesterday'",
      again.job("s0000000002").get("carry") == "from yesterday",
      again.job("s0000000002").get("carry"))
check("...while the 4-day-old one says its weekday, never 'from yesterday'",
      again.job("s0000000001").get("carry") == "from Friday (4d ago)",
      again.job("s0000000001").get("carry"))
print()

# --------------------------------------------------------------------------
# 2. The tag is measured from created_date (ruling 8, item 2)
# --------------------------------------------------------------------------

print("--- 2. how old an item is, in the owner's words ---")
clock.now = at(2026, 10, 30)
s2 = S.Scheduler(fresh("tags"), clock=clock)
three = s2.add_todo("call the dentist")
check("a new item is stamped with the day it was written",
      three["created_date"] == "2026-10-30", three["created_date"])
check("...and says nothing about its age on the day it was written",
      "carry" not in three, three)

clock.now = at(2026, 10, 31)
check("one day later it says 'from yesterday'",
      s2.job(three["id"]).get("carry") == "from yesterday",
      s2.job(three["id"]).get("carry"))

clock.now = at(2026, 11, 2)          # exactly three days after 2026-10-30
v = s2.job(three["id"])
check("3 days later it says 'from Friday (3d ago)' - the brief's exact wording",
      v.get("carry") == "from Friday (3d ago)", v.get("carry"))
check("...and NEVER 'from yesterday' (a 3-day-old item is not yesterday's)",
      v.get("carry") != "from yesterday", v.get("carry"))
check("...and its created_date did not move through any of that",
      v["created_date"] == "2026-10-30", v["created_date"])

clock.now = at(2026, 11, 5)          # 6 days
check("6 days later it still names the weekday and the count",
      s2.job(three["id"]).get("carry") == "from Friday (6d ago)",
      s2.job(three["id"]).get("carry"))
clock.now = at(2026, 11, 6)          # 7 days
check("7 days later it says 'from Oct 30' (the date, no count)",
      s2.job(three["id"]).get("carry") == "from Oct 30",
      s2.job(three["id"]).get("carry"))
check("...and still says nothing it cannot back up",
      s2.job(three["id"])["created_date"] == "2026-10-30")
print()

# --------------------------------------------------------------------------
# 3. The mode switch is 100% lossless (ruling 8, item 3)
# --------------------------------------------------------------------------

print("--- 3. rollover -> day by day -> rollover changes no item ---")
clock.now = at(2026, 10, 31)
s3 = S.Scheduler(fresh("toggle"), clock=clock)
old = s3.add_todo("renew the prescription")        # 2026-10-31
clock.now = at(2026, 11, 2)
today = s3.add_todo("buy milk")                    # 2026-11-02
before = s3.todos()
before_mode = s3.status()["todo_mode"]
check("the default mode is full daily rollover",
      before_mode == "rollover", before_mode)
check("...which is the mode the owner chose as the default",
      S.TODO_MODE_DEFAULT == "rollover")

s3.set_todo_mode("day")
day_view = s3.todos()
days = s3.status()["todo_days"]
check("the switch changed the mode", s3.status()["todo_mode"] == "day")
check("...and every item is the same item, in the same order",
      [(j["id"], j["text"], j["created_date"], j.get("carry")) for j in day_view]
      == [(j["id"], j["text"], j["created_date"], j.get("carry")) for j in before],
      day_view)
check("...with created_date untouched",
      {j["id"]: j["created_date"] for j in day_view}
      == {j["id"]: j["created_date"] for j in before})
check("...grouped by the day each was written",
      days == [{"date": "2026-11-02", "label": "Today", "count": 1, "items": [today["id"]]},
               {"date": "2026-10-31", "label": "Saturday (2d ago)", "count": 1,
                "items": [old["id"]]}], days)

s3.set_todo_mode("rollover")
after = s3.todos()
check("switching back gives the identical list again",
      [(j["id"], j["text"], j["created_date"], j.get("carry"), j.get("rank"))
       for j in after]
      == [(j["id"], j["text"], j["created_date"], j.get("carry"), j.get("rank"))
          for j in before], after)
check("...and the mode is the default again", s3.status()["todo_mode"] == "rollover")
check("...and nothing was added or lost by any of it", len(after) == 2, after)
check("both modes are offered in the PC's own words, for the Settings switch",
      [m["value"] for m in before and s3.status()["todo_modes"]] == ["rollover", "day"])
print()

# --------------------------------------------------------------------------
# 4. Asking Jarvis in chat, and the Settings switch, are the same change
# --------------------------------------------------------------------------

print("--- 4. a sentence and the switch cannot disagree ---")
setting = R.find_choice_setting_words("the to-do list mode")
check("the registry knows the to-do list's carry-over as a setting",
      setting is not None and setting.key == "todo_carryover",
      setting)
check("...and offers both real choices",
      setting is not None and set(setting.options().values()) == {"rollover", "day"},
      setting.options() if setting else None)

import jarvis_quick  # noqa: E402  (already imported as Q; kept for the docstring)

for phrase, want in (("set the to-do list mode to day by day", "day"),
                     ("set the to-do carry-over to full daily rollover", "rollover"),
                     ("set the to-do list mode to each day separately", "day")):
    m = Q.match(phrase)
    check(f"'{phrase}' is answered without the model",
          m is not None and m.name == "settings_choice",
          f"got {m.name if m else 'the model'}")
    if m is not None and m.name == "settings_choice":
        check(f"...and it names the to-do carry-over, value {want!r}",
              m.f.get("key") == "todo_carryover" and m.f.get("value") == want,
              m.f)

s4 = S.Scheduler(fresh("chat"), clock=clock)
_SCHED_BEFORE = S._SCHED
S._SCHED = s4            # the door the setter uses, pointed at this test's file
try:
    out = R.set_todo_carryover("day")
    check("the spoken change really changes the mode", out.ok and s4.todo_mode() == "day",
          out.said)
    check("...and says nothing was moved", "moved" in out.said, out.said)
    check("the Settings switch reads the identical state",
          S.handle_act({"do": "todo_mode", "mode": "rollover"})[1]["mode"] == "rollover"
          and s4.todo_mode() == "rollover")
    again_out = R.set_todo_carryover("rollover")
    check("asking for the mode it is already in changes nothing and says so",
          again_out.ok and "already" in again_out.said, again_out.said)
    check("a mode that does not exist is refused in words",
          not R.set_todo_carryover("sideways").ok)
    bad = S.handle_act({"do": "todo_mode", "mode": "sideways"})
    check("...and the route refuses it too", bad[0] == 400 and not bad[1]["ok"], bad)
finally:
    S._SCHED = _SCHED_BEFORE
print()

# --------------------------------------------------------------------------
# 5. Taking something off the list is unchanged (the owner's ask (c))
# --------------------------------------------------------------------------

print("--- 5. done and delete are exactly what they were ---")
clock.now = at(2026, 10, 30)
s5 = S.Scheduler(fresh("removal"), clock=clock)
one = s5.add_todo("post the letter")
two = s5.add_todo("water the plants")
clock.now = at(2026, 11, 2)
check("both items carry over to today's list", len(s5.todos()) == 2)
check("...each tagged with how old it is",
      all(j.get("carry") == "from Friday (3d ago)" for j in s5.todos()),
      [j.get("carry") for j in s5.todos()])
code, out = s5.act(one["id"], "done")
check("marking one done still works", code == 200 and out.get("ok") is not False, out)
check("...and it is off the list", [j["id"] for j in s5.todos()] == [two["id"]])
code, out = s5.act(two["id"], "delete")
check("removing one still works", code == 200, out)
check("...and the list is empty", s5.todos() == [])
print()

# --------------------------------------------------------------------------
# 6. The spoken read-out says which items are older
# --------------------------------------------------------------------------

print("--- 6. 'what's on my to-do list?' says how old each item is ---")
clock.now = at(2026, 10, 31)
s6 = S.Scheduler(fresh("said"), clock=clock)
s6.add_todo("renew the prescription")
clock.now = at(2026, 11, 2)
s6.add_todo("buy milk")
_SCHED_BEFORE = S._SCHED
S._SCHED = s6
try:
    items = [Q._todo_said(j) for j in s6.todos()]
finally:
    S._SCHED = _SCHED_BEFORE
check("the older item is said with its own age",
      "renew the prescription (from Saturday (2d ago))" in items, items)
check("today's item is said with its own words and no tag",
      "buy milk" in items and not any(i.startswith("buy milk (") for i in items), items)

# --------------------------------------------------------------------------
print()
print(f"{len(PASSED)} passed, {len(FAILED)} failed")
if FAILED:
    for name in FAILED:
        print(f"  failed: {name}")
    raise SystemExit(1)
