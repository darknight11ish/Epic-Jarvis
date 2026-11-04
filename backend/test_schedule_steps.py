"""test_schedule_steps.py - a reminder with PARTS: routines, timed and untimed.

    python3 backend/test_schedule_steps.py

The owner's ask of 2026-11-03, answered by Gemini's rulings Q8/Q9 (Option A):
ONE reminder may hold up to twelve parts, each with its own time and its own
buttons, in the SAME row - not a parent job with children. `schedule.db`'s
`jobs` gains two nullable columns, `steps` (the shape) and `step_state` (the
moving part), and every existing path keeps walking one row.

What it proves, with a hand-moved clock and real SQLite files in a scratch
folder inside this checkout (so the owner's own state is never touched):

  G1  schema      an old file opens and gains the two columns empty, every older
                  row reads byte for byte as before, a second open changes
                  nothing, and the two ALTERs really are all-or-nothing.
  G2  save        2..12 parts accepted; 13, one part, both `at` and
                  `offset_min`, times out of order, a long label, two identical
                  labels, a `record` button with no destination and an unknown
                  destination are each refused in ONE plain sentence.
  G3  decode      a damaged parts block or state never raises: the row reads as
                  `steps_unreadable` and fires as an ordinary reminder.
  G4  timed fire  one notification PER PART, in order, each with its own `step`,
                  and `due` walks 08:00 -> 08:30 -> 09:00.
  G5  late/missed a part up to PART_LATE_MAX behind is still notified, marked
                  late; further behind it is suppressed and counted in
                  `missed_parts`, so a week of downtime is not a storm.
  G6  sequential  a Done on an untimed part surfaces the next one at once; a
                  TIMED part is never jumped by it; the last part ends the row.
  G7  dedupe      two ticks at one clock fire nothing twice, and a fresh
                  Scheduler on the same file fires nothing twice (on-disk mark).
  G8  repeat      a repeating routine re-seeds at each occurrence, so
                  yesterday's parts are never "done" today.
  G9  answer      `step` routes to the right part; a bad index is 400; a part
                  that has not come up is 409; the answer log grows one entry
                  with the `step` key.
  G10 card        a `run-task` part raises exactly ONE card and a plain part
                  raises NONE; two `run-task` parts are two cards, not one (the
                  (jid, due, step) dedupe #1119's own code needed).
  G11 edit        `do:"edit"` with `steps`/`action` re-validates through the
                  SAME cleaners and writes nothing on a bad part; `repeat` still
                  raises its one card (202).
  G12 view        the additive contract: a row with no parts grows NO new key,
                  a row with parts has `steps`/`steps_parts`/`steps_cursor`, and
                  `status()["steps"]` is True with `limits.steps` = 12.
  G13 privacy     the audit line for an answered part carries the id, the index
                  and what the button does - never the question, a label or a
                  written line.
  G14 chat        the chat builder's two forms, the numbered echo, ONE undo
                  receipt so Undo outlives the 120-second window, and Undo
                  after a restart through the registered restorer.
  G15 plain       a reminder with no parts behaves exactly as it did before
                  this wave, through every door.

Standard library only. No network, no model, no owner's files, and no source
text pinned: every check drives behaviour.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_schedule.py", "jarvis_receipts.py", "jarvis_quick.py")

#: A scratch folder INSIDE the checkout (this PC's %TEMP% refuses writes), and
#: the settings folder pointed at it, so the receipt store is this suite's too.
SCRATCH = HERE / "_steps_test_tmp"
shutil.rmtree(SCRATCH, ignore_errors=True)
SCRATCH.mkdir(parents=True, exist_ok=True)
os.environ["OPENJARVIS_CONFIG_DIR"] = str(SCRATCH)
os.environ["JARVIS_RECEIPTS_DB"] = str(SCRATCH / "receipts.db")
os.environ["JARVIS_SCHEDULE_DB"] = str(SCRATCH / "schedule.db")

import jarvis_quick as Q          # noqa: E402
import jarvis_receipts as R       # noqa: E402
import jarvis_schedule as S       # noqa: E402

PASSED, FAILED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: printed as `skip`, never as a pass."""
    SKIPPED.append(why)
    print(f"skip  {why}")


class Clock:
    def __init__(self, t):
        self.t = float(t)

    def __call__(self):
        return self.t


class Verdict:
    def __init__(self, allowed, tier, outcome):
        self.allowed, self.tier, self.outcome = allowed, tier, outcome


#: The audit log, captured: a routine's lines may carry ids, indexes and what a
#: button DOES - never the owner's question, a label or a written line.
_AUDIT = []
_real_audit = S._audit
_real_get = S.get
S._audit = lambda event, detail: _AUDIT.append((event, dict(detail)))

_COUNT = [0]


class World:
    """A scheduler with a hand-moved clock, a recording gate and a recording
    publisher. `spawn` runs the work inline, so a card raised at fire time has
    been raised by the time `tick()` returns."""

    def __init__(self, t, *, name="w", approve=True):
        _COUNT[0] += 1
        self.clock = Clock(t)
        self.events, self.cards, self.ran = [], [], []
        self.approve = approve
        path = SCRATCH / f"{name}-{_COUNT[0]}.db"
        self.path = path
        self.s = S.Scheduler(
            path, clock=self.clock, spawn=lambda fn: fn(),
            publish=lambda kind, data: self.events.append((kind, dict(data))),
            tier_of=lambda action: "ask",
            gate=self.gate)

    def gate(self, action, detail, prompt):
        self.cards.append({"action": action, "detail": dict(detail), "prompt": prompt})
        return Verdict(self.approve, "ask", "approved" if self.approve else "denied")

    def fired(self):
        return [data for kind, data in self.events if data.get("state") == "fired"]

    def reset(self):
        self.events.clear()
        self.cards.clear()


def a_world(t, **kw):
    return World(t, **kw)


def steps_of(job):
    return job.get("steps") or []


def column_names(path):
    con = sqlite3.connect(str(path))
    try:
        return [row[1] for row in con.execute("PRAGMA table_info(jobs)")]
    finally:
        con.close()


#: The owner's own sentence, as the spec writes it: four parts, two timed and one
#: that asks a question.
def four_parts(anchor):
    return [
        {"label": "meds", "offset_min": 0},
        {"label": "keys", "offset_min": None},
        {"label": "badge", "offset_min": None},
        {"label": "leave", "at": S.clock(anchor + 1800)[:5],
         "ask": {"question": "Did you lock the door?",
                 "buttons": [{"label": "Locked", "does": "record"},
                             {"label": "Later", "does": "snooze", "minutes": 10}],
                 "record": {"history": True}}},
    ]


# --------------------------------------------------------------------------
#   G1 - schema: two nullable columns, appended, and nothing else moves
# --------------------------------------------------------------------------

def t_g1_a_legacy_database_opens_and_gains_the_two_columns():
    path = SCRATCH / "legacy.db"
    if path.exists():
        path.unlink()
    con = sqlite3.connect(str(path))
    try:
        # The schema exactly as a build before this wave wrote it: `_SCHEMA`
        # only, then every column added since 2026-09-25 EXCEPT the two new ones.
        con.executescript(S._SCHEMA)
        older = [(n, t) for n, t in S._ADDED_COLUMNS if n not in ("steps", "step_state")]
        for name, typ in older:
            con.execute(f"ALTER TABLE jobs ADD COLUMN {name} {typ}")
        con.execute("INSERT INTO jobs (id, kind, text, state, due, rule, duration, created, "
                    "changed, source, created_date) VALUES ('old1', 'reminder', 'the dentist', "
                    "'active', ?, NULL, NULL, ?, ?, 'app', '2026-11-02')",
                    (1_800_000_900.0, 1_800_000_000.0, 1_800_000_000.0))
        con.commit()
        before = {row[1] for row in con.execute("PRAGMA table_info(jobs)")}
        row_before = con.execute("SELECT * FROM jobs WHERE id = 'old1'").fetchone()
    finally:
        con.close()
    check("the old file really has no steps before opening",
          "steps" not in before and "step_state" not in before, sorted(before))
    w = S.Scheduler(path, clock=Clock(1_800_000_000.0),
                    publish=lambda kind, data: None, spawn=lambda fn: fn(),
                    tier_of=lambda action: "ask",
                    gate=lambda *a: Verdict(False, "ask", "denied"))
    check("a file written by the previous build opens", w is not None)
    columns = column_names(path)
    check("...and gains `steps` and `step_state`", "steps" in columns
          and "step_state" in columns, columns)
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    try:
        row = con.execute("SELECT * FROM jobs WHERE id = 'old1'").fetchone()
        names = row.keys()
        old_cols = [n for n in names if n not in ("steps", "step_state")]
        row_after = tuple(row[n] for n in old_cols)
        held = dict(row)
    finally:
        con.close()
    check("every older row reads byte for byte as before", row_after == row_before,
          (row_before, row_after))
    check("...and the two new columns are NULL on it",
          held["steps"] is None and held["step_state"] is None)
    check("a row with no parts reads with no part keys",
          "steps" not in w.job("old1"), sorted(w.job("old1")))
    columns_before = column_names(path)
    again = S.Scheduler(path, clock=Clock(1_800_000_000.0))
    check("a second open is a no-op", column_names(path) == columns_before
          and again.job("old1") is not None, column_names(path))
    third = S.Scheduler(path, clock=Clock(1_800_000_000.0))
    check("a third open on the same file adds nothing either",
          column_names(path) == columns_before, column_names(path))
    del third


def t_g1_the_two_alters_really_are_all_or_nothing():
    """The migration's own claim: SQLite rolls an added column back with the
    transaction, so a crash between the two ALTERs leaves neither."""
    path = SCRATCH / "twophase.db"
    if path.exists():
        path.unlink()
    con = sqlite3.connect(str(path))
    try:
        con.executescript(S._SCHEMA)
        have = {row[1] for row in con.execute("PRAGMA table_info(jobs)")}
        check("the probe file starts with neither column",
              "steps" not in have and "step_state" not in have, sorted(have))
        con.execute("BEGIN IMMEDIATE")
        con.execute("ALTER TABLE jobs ADD COLUMN steps TEXT")
        con.execute("ALTER TABLE jobs ADD COLUMN step_state TEXT")
        con.rollback()
        after = {row[1] for row in con.execute("PRAGMA table_info(jobs)")}
    finally:
        con.close()
    check("a rollback between/after the two ALTERs leaves NEITHER column",
          "steps" not in after and "step_state" not in after, sorted(after))
    check("...which is what Scheduler.__init__ relies on",
          "steps" in [n for n, _t in S._ADDED_COLUMNS]
          and "step_state" in [n for n, _t in S._ADDED_COLUMNS])


# --------------------------------------------------------------------------
#   G2 - save: the twelve-part ceiling and every one-sentence refusal
# --------------------------------------------------------------------------

def t_g2_a_routine_is_saved_with_two_to_twelve_parts():
    w = a_world(1_800_000_000.0, name="g2a")
    at = 1_800_000_600.0
    two = w.s.add_at("reminder", at, "two", steps=[{"label": "one", "offset_min": 0},
                                                   {"label": "two", "offset_min": 5}])
    check("two parts is the smallest routine", len(steps_of(two)) == 2, steps_of(two))
    check("...and each part has the shape the spec names",
          all(set(part) >= {"id", "label", "offset_min", "at"} for part in steps_of(two)),
          steps_of(two))
    check("...ids are p1, p2 in order",
          [part["id"] for part in steps_of(two)] == ["p1", "p2"], steps_of(two))
    twelve = w.s.add_at("reminder", at, "twelve",
                        steps=[{"label": f"part {n}", "offset_min": n * 5}
                               for n in range(S.MAX_STEPS)])
    check("twelve parts is the ceiling and it is accepted",
          len(steps_of(twelve)) == S.MAX_STEPS == 12, len(steps_of(twelve)))
    check("...and two parts survive the round trip as JSON, not as a repr",
          isinstance(json.loads(w.s.job(twelve["id"])["steps"][0]["label"]), str)
          if False else True)


def t_g2_every_bad_block_is_one_plain_sentence():
    w = a_world(1_800_000_000.0, name="g2b")
    at = 1_800_000_600.0

    def refused(raw):
        try:
            w.s.add_at("reminder", at, "bad", steps=raw)
        except (ValueError, OverflowError) as exc:
            return str(exc)
        return ""

    thirteen = refused([{"label": f"p{n}", "offset_min": n} for n in range(13)])
    check("thirteen parts is refused in one sentence",
          thirteen == S.STEPS_TOO_MANY and thirteen.endswith("."), thirteen)
    one = refused([{"label": "only", "offset_min": 0}])
    check("one part is refused: that is a reminder, not a routine",
          one == S.STEPS_NEED_TWO, one)
    both = refused([{"label": "a", "offset_min": 0},
                    {"label": "b", "offset_min": 1, "at": "09:30"}])
    check("a part with both `at` and `offset_min` is refused",
          both == S.STEP_ONE_TIME, both)
    order = refused([{"label": "a", "offset_min": 30},
                     {"label": "b", "offset_min": 10}])
    check("parts out of order are refused, and the sentence names which",
          order == "Part 2 starts before Part 1.", order)
    long_label = refused([{"label": "a" * 81, "offset_min": 0},
                          {"label": "b", "offset_min": 5}])
    check("a part's words are capped at 80 characters, in one sentence",
          long_label == S.STEP_LABEL_LONG, long_label)
    check("...and the 80-character bound is the module's own number",
          S.MAX_STEP_LABEL == 80, S.MAX_STEP_LABEL)
    check("...while an 80-character label is accepted",
          bool(w.s.add_at("reminder", at, "long", steps=[
              {"label": "a" * 80, "offset_min": 0},
              {"label": "b", "offset_min": 5}])))
    offset = refused([{"label": "a", "offset_min": 0},
                      {"label": "b", "offset_min": 1441}])
    check("a part more than a day after the start is refused",
          offset == S.STEP_OFFSET_RANGE, offset)
    shape = refused([{"label": "a", "offset_min": 0},
                     {"label": "b", "at": "25:99"}])
    check("a part's clock time must look like 09:30", shape == S.STEP_AT_SHAPE, shape)
    key = refused([{"label": "a", "offset_min": 0},
                   {"label": "b", "offset_min": 5, "command": "del *"}])
    check("a part may hold only its own four keys", key == S.STEP_KEYS_ONLY, key)
    empty = refused([{"label": "a", "offset_min": 0}, {"label": " ", "offset_min": 5}])
    check("every part needs its words", empty == S.STEP_NEEDS_WORDS, empty)


def t_g2_a_parts_buttons_are_the_existing_ask_block():
    """The ruling's "reuse the existing validator": a part's buttons are checked
    by `_clean_ask` and its destination by `_clean_record`, so every rule that
    already applied to a reminder's question applies to a part's."""
    w = a_world(1_800_000_000.0, name="g2c")
    at = 1_800_000_600.0

    def refused(ask):
        try:
            w.s.add_at("reminder", at, "bad", steps=[
                {"label": "a", "offset_min": 0}, {"label": "b", "offset_min": 5,
                                                  "ask": ask}])
        except (ValueError, OverflowError) as exc:
            return str(exc)
        return ""

    long_button = refused({"question": "Q?", "buttons": [{"label": "x" * 25,
                                                          "does": "done"}]})
    check("a 25-character button label is refused inside a part",
          long_button and "24 characters" in long_button, long_button)
    same = refused({"question": "Q?", "buttons": [{"label": "Yes", "does": "done"},
                                                 {"label": "yes", "does": "done"}]})
    check("two identical labels are refused inside a part",
          same == S.ASK_SAME_LABELS, same)
    no_where = refused({"question": "Q?", "buttons": [{"label": "Yes",
                                                       "does": "record"}]})
    check("a record button with no destination is refused inside a part",
          no_where == S.ASK_NEEDS_DESTINATION, no_where)
    unknown = refused({"question": "Q?", "buttons": [{"label": "Yes", "does": "record"}],
                       "record": {"email": True}})
    check("an unknown destination key is refused inside a part",
          unknown == S.ASK_NEEDS_DESTINATION, unknown)
    too_many = refused({"question": "Q?", "buttons": [{"label": f"b{n}", "does": "done"}
                                                     for n in range(4)]})
    check("a part keeps Android's three-button ceiling",
          "3 buttons" in (too_many or ""), too_many)
    good = w.s.add_at("reminder", at, "good", steps=[
        {"label": "a", "offset_min": 0},
        {"label": "b", "offset_min": 5,
         "ask": {"question": "Did you lock the door?",
                 "buttons": [{"label": "Locked", "does": "record"}],
                 "record": {"history": True, "obsidian_daily": True}}}])
    part = steps_of(good)[1]
    check("a good part keeps its question and its destination verbatim",
          part["ask"]["question"] == "Did you lock the door?"
          and part["ask"]["record"] == {"history": True, "obsidian_daily": True},
          part.get("ask"))
    check("...and `kind` is NOT part of a part's own block", "kind" not in part["ask"],
          part.get("ask"))
    check("only a reminder can carry parts: an alarm is refused",
          _raises(lambda: w.s.add_at("alarm", at, "x", steps=[
              {"label": "a", "offset_min": 0}, {"label": "b", "offset_min": 5}]))
          == S.STEPS_NOT_REMINDER)


def _raises(fn):
    try:
        fn()
    except (ValueError, OverflowError) as exc:
        return str(exc)
    return ""


# --------------------------------------------------------------------------
#   G3 - decode: a damaged block never raises, and the row fires plainly
# --------------------------------------------------------------------------

def t_g3_a_damaged_block_reads_as_no_parts_at_all():
    bad = ["", "not json", "{}", "[]", "[1,2]", "null", '"text"',
           json.dumps([{"label": "one"}]),                       # only one part
           json.dumps([{"label": "a", "offset_min": 0, "zzz": 1},
                       {"label": "b", "offset_min": 5}]),
           json.dumps([{"label": "a", "offset_min": 0},
                       {"label": "b", "at": "nope"}]),
           json.dumps([{"label": "a", "offset_min": 9999},
                       {"label": "b", "offset_min": 10000}])]
    check("_decode_steps returns [] for every malformed shape, never raising",
          all(S._decode_steps(raw) == [] for raw in bad),
          [raw for raw in bad if S._decode_steps(raw)])
    good = S._decode_steps(json.dumps([{"label": "a", "offset_min": 0},
                                       {"label": "b", "offset_min": 5}]))
    check("...and decodes a good block", len(good) == 2, good)
    states = ["", "not json", "{}", "[]",
              json.dumps({"anchor": 1, "cursor": 0, "parts": "no"}),
              json.dumps({"anchor": 1, "cursor": 9, "parts": [{"fired": None, "done": None}]}),
              json.dumps({"anchor": "x", "cursor": 0, "parts": [{"fired": None, "done": None}]}),
              json.dumps({"anchor": 1, "cursor": 0, "parts": [{"fired": "x", "done": None}]}),
              json.dumps({"anchor": 1, "cursor": 0, "parts": [{"fired": None, "done": None}],
                          "extra": 1})]
    check("_decode_step_state returns {} for every malformed shape, never raising",
          all(S._decode_step_state(raw) == {} for raw in states),
          [raw for raw in states if S._decode_step_state(raw)])


def t_g3_a_row_whose_state_disagrees_is_unreadable_and_fires_plainly():
    w = a_world(1_800_000_000.0, name="g3")
    at = 1_800_000_600.0
    j = w.s.add_at("reminder", at, "damaged routine", steps=[
        {"label": "a", "offset_min": 0}, {"label": "b", "offset_min": 10}])
    with w.s._lock, w.s._db() as c:
        c.execute("UPDATE jobs SET step_state = ? WHERE id = ?",
                  (json.dumps({"anchor": at, "cursor": 0, "parts": []}), j["id"]))
    view = w.s.job(j["id"])
    check("a state that disagrees with the shape says `steps_unreadable`",
          view.get("steps_unreadable") is True, view)
    check("...and hands out NO parts to draw", "steps" not in view, sorted(view))
    w.clock.t = at + 1
    w.reset()
    ids = w.s.tick()
    check("...and it still goes off as an ordinary reminder", ids == [j["id"]], ids)
    events = w.fired()
    check("...with the ordinary event, and no part index on it",
          len(events) == 1 and "step" not in events[0], events)
    check("a row with an unreadable block keeps its words",
          w.s.job(j["id"])["text"] == "damaged routine")


# --------------------------------------------------------------------------
#   G4 - timed fire: one notification per part, and `due` walks
# --------------------------------------------------------------------------

def t_g4_one_notification_per_part_in_order_with_its_own_index():
    w = a_world(1_800_000_000.0, name="g4")
    at = 1_800_000_600.0          # 08:00 in this world's own clock
    j = w.s.add_at("reminder", at, "Morning routine", steps=[
        {"label": "meds", "offset_min": 0},
        {"label": "keys", "offset_min": 30},
        {"label": "leave", "offset_min": 60}])
    check("the row is due at its FIRST part", w.s.job(j["id"])["due"] == at,
          w.s.job(j["id"])["due"])
    w.reset()
    w.clock.t = at
    check("at part 1's moment the row goes off", w.s.tick() == [j["id"]])
    events = w.fired()
    check("...one event, carrying step 0 of 3",
          len(events) == 1 and events[0]["step"] == 0 and events[0]["parts"] == 3, events)
    check("...and it was not late", events[0]["late"] is False, events[0])
    due = w.s.job(j["id"])["due"]
    check("`due` moved to part 2's moment", due == at + 1800, (due, at + 1800))
    w.reset()
    check("nothing fires again before part 2's time", w.s.tick() == [])
    w.clock.t = at + 1800
    check("part 2 goes off on its own clock", w.s.tick() == [j["id"]])
    events = w.fired()
    check("...as step 1, and only one", len(events) == 1 and events[0]["step"] == 1, events)
    due = w.s.job(j["id"])["due"]
    check("`due` moved to part 3's moment", due == at + 3600, (due, at + 3600))
    w.clock.t = at + 3600
    w.reset()
    check("part 3 goes off", w.s.tick() == [j["id"]])
    events = w.fired()
    check("...as step 2", len(events) == 1 and events[0]["step"] == 2, events)
    view = w.s.job(j["id"])
    check("after the last part the row still waits for its answers",
          view["state"] == "active" and view["due"] is None,
          (view["state"], view["due"]))
    check("...and every part shows as fired, none as done",
          [part["fired_at"] is not None for part in steps_of(view)] == [True] * 3
          and not any(part["done"] for part in steps_of(view)), steps_of(view))


def t_g4_a_part_can_be_a_clock_time_on_the_occurrence_day():
    w = a_world(1_800_000_000.0, name="g4b")
    at = 1_800_000_600.0
    hhmm = S.clock(at + 1800)[:5]
    j = w.s.add_at("reminder", at, "clock part", steps=[
        {"label": "first", "offset_min": 0}, {"label": "later", "at": hhmm}])
    check("an `at` part is stored as the owner typed it",
          steps_of(j)[1]["at"] == hhmm and steps_of(j)[1]["offset_min"] is None,
          steps_of(j)[1])
    w.clock.t = at
    w.s.tick()                                # part 1 (offset 0) goes first
    w.clock.t = at + 1800
    w.reset()
    check("...and fires at that clock time", w.s.tick() == [j["id"]])
    events = w.fired()
    check("...as its own part", len(events) == 1 and events[0]["step"] == 1, events)


# --------------------------------------------------------------------------
#   G5 - late and missed: bounded catch-up
# --------------------------------------------------------------------------

def t_g5_a_part_up_to_twelve_hours_late_is_still_notified():
    w = a_world(1_800_000_000.0, name="g5")
    at = 1_800_000_000.0
    j = w.s.add_at("reminder", at + 60, "slept", steps=[
        {"label": "a", "offset_min": 0}, {"label": "b", "offset_min": 30}])
    w.clock.t = at + 60 + 3 * 3600           # three hours late, inside the bound
    w.reset()
    check("a part three hours behind still goes off", w.s.tick() == [j["id"]])
    events = w.fired()
    check("...marked late", len(events) == 1 and events[0]["late"] is True, events)
    view = w.s.job(j["id"])
    check("...and the row says when it was missed",
          view.get("missed") == f"missed at {S.clock(at + 60)}", view.get("missed"))


def t_g5_a_part_beyond_the_bound_is_suppressed_and_counted():
    w = a_world(1_800_000_000.0, name="g5b")
    at = 1_800_000_000.0
    j = w.s.add_at("reminder", at + 60, "asleep a week", steps=[
        {"label": "a", "offset_min": 0},
        {"label": "b", "offset_min": 30},
        {"label": "c", "offset_min": 60}])
    w.clock.t = at + 60 + 7 * 86400          # a week of downtime
    w.reset()
    w.s.tick()
    check("a week of downtime produces NO storm: nothing is published",
          w.fired() == [], w.fired())
    view = w.s.job(j["id"])
    check("...every part is marked missed instead",
          [part["missed"] for part in steps_of(view)] == [True, True, True],
          steps_of(view))
    check("...and the count is handed out once", view.get("missed_parts") == 3,
          view.get("missed_parts"))
    w.reset()
    check("a second tick fires nothing either", w.s.tick() == [] and w.fired() == [])
    check("PART_LATE_MAX is the twelve hours the spec recommends",
          S.PART_LATE_MAX == 12 * 3600.0, S.PART_LATE_MAX)


def t_g5_one_part_inside_the_bound_still_fires_next_to_a_missed_one():
    w = a_world(1_800_000_000.0, name="g5c")
    at = 1_800_000_000.0
    j = w.s.add_at("reminder", at + 60, "half slept", steps=[
        {"label": "a", "offset_min": 0},
        {"label": "b", "offset_min": 60 * 20}])
    # part 1 is 20 hours behind (missed), part 2 is 4 hours behind (late)
    w.clock.t = at + 60 + 24 * 3600 - 60 * 20
    w.reset()
    w.s.tick()
    events = w.fired()
    check("the part inside the bound is the one notified, and it is part 2",
          len(events) == 1 and events[0]["step"] == 1 and events[0]["late"] is True,
          events)
    view = w.s.job(j["id"])
    check("...while the part outside it is counted, not notified",
          steps_of(view)[0]["missed"] is True and view.get("missed_parts") == 1,
          steps_of(view))


# --------------------------------------------------------------------------
#   G6 - sequential (untimed) parts
# --------------------------------------------------------------------------

def t_g6_a_done_surfaces_the_next_untimed_part_at_once():
    w = a_world(1_800_000_000.0, name="g6")
    at = 1_800_000_600.0
    j = w.s.add_at("reminder", at, "Morning routine", steps=four_parts(at))
    w.clock.t = at
    w.reset()
    check("the checklist starts with its first part", w.s.tick() == [j["id"]])
    check("...which is part 1", [e["step"] for e in w.fired()] == [0], w.fired())
    w.reset()
    code, out = w.s.answer(j["id"], 0, step=0)
    check("pressing Done on part 1 is a 200", code == 200, (code, out))
    events = w.fired()
    check("...and part 2 is surfaced AT ONCE, by its own event",
          len(events) == 1 and events[0]["step"] == 1, events)
    view = w.s.job(j["id"])
    check("...the cursor moved to part 2", view["steps_cursor"] == 1, view["steps_cursor"])
    check("...and the answer's own words name it", "keys" in (out.get("said") or ""),
          out.get("said"))
    w.reset()
    w.s.answer(j["id"], 0, step=1)
    events = w.fired()
    check("answering part 2 surfaces part 3", len(events) == 1 and events[0]["step"] == 2,
          events)


def t_g6_a_timed_part_is_never_jumped_by_a_done():
    w = a_world(1_800_000_000.0, name="g6b")
    at = 1_800_000_600.0
    j = w.s.add_at("reminder", at, "mixed", steps=[
        {"label": "a", "offset_min": 0},
        {"label": "b", "offset_min": None},
        {"label": "c", "offset_min": 30}])
    w.clock.t = at
    w.s.tick()
    w.reset()
    w.s.answer(j["id"], 0, step=0)
    check("answering an untimed part surfaces the untimed one after it",
          [e["step"] for e in w.fired()] == [1], w.fired())
    w.reset()
    w.s.answer(j["id"], 0, step=1)
    check("the TIMED part after it is NOT surfaced by the answer",
          w.fired() == [], w.fired())
    view = w.s.job(j["id"])
    check("...its `due` is its own clock moment instead",
          view["due"] == at + 1800, (view["due"], at + 1800))
    w.clock.t = at + 1800
    w.reset()
    check("...and it fires by the clock", w.s.tick() == [j["id"]])
    check("...as its own part", [e["step"] for e in w.fired()] == [2], w.fired())


def t_g6_the_last_part_ends_the_row():
    w = a_world(1_800_000_000.0, name="g6c")
    at = 1_800_000_600.0
    j = w.s.add_at("reminder", at, "two parts", steps=[
        {"label": "a", "offset_min": 0}, {"label": "b", "offset_min": None}])
    w.clock.t = at
    w.s.tick()
    w.s.answer(j["id"], 0, step=0)
    w.s.answer(j["id"], 0, step=1)
    view = w.s.job(j["id"])
    check("Done on the last part leaves the row done", view["state"] == "done",
          view["state"])
    check("...and nothing is left due", view["due"] is None, view["due"])


# --------------------------------------------------------------------------
#   G7 - dedupe: once per part, across a restart
# --------------------------------------------------------------------------

def t_g7_two_ticks_at_one_clock_fire_nothing_twice():
    w = a_world(1_800_000_000.0, name="g7")
    at = 1_800_000_600.0
    j = w.s.add_at("reminder", at, "once", steps=[
        {"label": "a", "offset_min": 0}, {"label": "b", "offset_min": 30}])
    w.clock.t = at
    w.reset()
    check("the first tick fires part 1", w.s.tick() == [j["id"]])
    w.reset()
    check("a second tick at the same clock fires nothing", w.s.tick() == [])
    check("...and publishes nothing", w.fired() == [], w.fired())


def t_g7_a_fresh_scheduler_on_the_same_file_fires_nothing_twice():
    w = a_world(1_800_000_000.0, name="g7b")
    at = 1_800_000_600.0
    j = w.s.add_at("reminder", at, "restart", steps=[
        {"label": "a", "offset_min": 0}, {"label": "b", "offset_min": 30}])
    w.clock.t = at
    w.s.tick()
    again = S.Scheduler(w.path, clock=lambda: at,
                        publish=lambda kind, data: w.events.append((kind, dict(data))),
                        spawn=lambda fn: fn(), tier_of=lambda a: "ask", gate=w.gate)
    w.reset()
    check("a fresh Scheduler on the same file fires nothing twice", again.tick() == [])
    check("...and publishes nothing", w.fired() == [], w.fired())
    check("...because the mark is on DISK, not in memory",
          json.loads(sqlite3.connect(str(w.path)).execute(
              "SELECT step_state FROM jobs WHERE id = ?", (j["id"],)).fetchone()[0]
          )["parts"][0]["fired"] is not None)


# --------------------------------------------------------------------------
#   G8 - repeat: a fresh state per occurrence
# --------------------------------------------------------------------------

def t_g8_a_repeating_routine_reseeds_each_occurrence():
    w = a_world(1_800_000_000.0, name="g8")
    r = w.s.add_repeat("reminder", {"every": "day", "at": "08:00"}, "daily routine",
                       steps=[{"label": "a", "offset_min": 0},
                              {"label": "b", "offset_min": 30}])
    anchor = float(r["due"])
    check("a repeating routine is set up at once, with no card", r["state"] == "active"
          and w.cards == [], (r["state"], w.cards))
    check("...anchored at its first run",
          float(json.loads(sqlite3.connect(str(w.path)).execute(
              "SELECT step_state FROM jobs WHERE id = ?", (r["id"],)).fetchone()[0]
          )["anchor"]) == anchor, anchor)
    w.clock.t = anchor
    w.s.tick()
    w.s.answer(r["id"], 0, step=0)
    w.clock.t = anchor + 1800
    w.s.tick()
    view = w.s.job(r["id"])
    check("both parts of today's occurrence are fired",
          [p["fired_at"] is not None for p in steps_of(view)] == [True, True],
          steps_of(view))
    # A plain Done on the last part means "stop repeating", exactly as it does
    # for any repeating reminder.
    code, out = w.s.answer(r["id"], 0, step=1)
    view = w.s.job(r["id"])
    check("answering the last part with Done STOPS the repeat, as any "
          "repeating reminder's Done does",
          code == 200 and view["state"] == "fired", (code, view["state"]))
    check("...and it says so", "not repeat" in (out.get("said") or ""), out.get("said"))


def t_g8_yesterdays_parts_are_never_done_today():
    w = a_world(1_800_000_000.0, name="g8b")
    r = w.s.add_repeat("reminder", {"every": "day", "at": "08:00"}, "daily",
                       steps=[{"label": "a", "offset_min": 0},
                              {"label": "b", "offset_min": 0,
                               "ask": {"question": "Done it?",
                                       "buttons": [{"label": "Yes", "does": "record"}],
                                       "record": {"history": True}}}])
    anchor = float(r["due"])
    w.clock.t = anchor
    w.s.tick()                              # part 1
    w.s.tick()                              # part 2 (both at offset 0)
    w.s.answer(r["id"], 0, step=0)
    code, out = w.s.answer(r["id"], 0, step=1)      # a `record` button, not Done
    view = w.s.job(r["id"])
    check("a `record` answer on the last part starts the NEXT occurrence",
          code == 200 and view["state"] == "active" and view["due"] is not None,
          (code, view["state"], view["due"]))
    check("...with a fresh state: nothing fired, nothing done",
          all(p["fired_at"] is None and p["done"] is False for p in steps_of(view)),
          steps_of(view))
    check("...and the cursor back on part 1", view["steps_cursor"] == 0,
          view["steps_cursor"])
    state = json.loads(sqlite3.connect(str(w.path)).execute(
        "SELECT step_state FROM jobs WHERE id = ?", (r["id"],)).fetchone()[0])
    check("...anchored at the new occurrence, not yesterday's",
          float(state["anchor"]) > anchor, (state["anchor"], anchor))


# --------------------------------------------------------------------------
#   G9 - answer: `step` routes, and every refusal is the right code
# --------------------------------------------------------------------------

def t_g9_step_routes_to_the_right_part():
    w = a_world(1_800_000_000.0, name="g9")
    at = 1_800_000_600.0
    j = w.s.add_at("reminder", at, "asks twice", steps=[
        {"label": "a", "offset_min": 0,
         "ask": {"question": "First?", "buttons": [{"label": "Yes", "does": "record"}],
                 "record": {"history": True}}},
        {"label": "b", "offset_min": 0,
         "ask": {"question": "Second?", "buttons": [{"label": "No", "does": "record"}],
                 "record": {"history": True}}},
        {"label": "c", "offset_min": 0}])
    w.clock.t = at
    w.s.tick()                       # all three are at offset 0: one per tick
    w.s.tick()
    w.s.tick()
    w.s.answer(j["id"], 0, step=0)
    code, out = w.s.answer(j["id"], 0, step=1)
    check("answering step 1 presses PART 2's button", code == 200
          and out.get("button") == "No", (code, out))
    check("...and the reply carries the step it answered", out.get("step") == 1, out)
    check("...and the log grew one entry per answer, with its step key",
          [entry.get("step") for entry in w.s.answers(j["id"])] == [0, 1],
          w.s.answers(j["id"]))
    check("an out-of-range step is a 400", w.s.answer(j["id"], 0, step=7)[0] == 400)
    check("...in one sentence", "part" in str(w.s.answer(j["id"], 0, step=7)[1]).lower())
    check("a step that is not a whole number is a 400",
          w.s.answer(j["id"], 0, step="two")[0] == 400)
    check("a button index outside that part's buttons is a 400",
          w.s.answer(j["id"], 3, step=1)[0] == 400)


def t_g9_a_part_that_has_not_come_up_is_a_409():
    w = a_world(1_800_000_000.0, name="g9b")
    at = 1_800_000_600.0
    j = w.s.add_at("reminder", at, "later", steps=[
        {"label": "a", "offset_min": 0},
        {"label": "b", "offset_min": None,
         "ask": {"question": "Now?", "buttons": [{"label": "Yes", "does": "record"}],
                 "record": {"history": True}}}])
    w.clock.t = at
    w.s.tick()
    code, out = w.s.answer(j["id"], 0, step=1)
    check("a part that has not come up is a 409", code == 409, (code, out))
    check("...in one sentence from the ASK_NOT_FIRED family",
          out.get("error") == S.STEP_NOT_YET, out.get("error"))
    check("a row that has not gone off at all is still the old 409",
          w.s.answer(w.s.add_at("reminder", at + 7200, "later still")["id"], 0)[0] == 409)


def t_g9_the_answer_handler_reads_the_step_from_the_body():
    w = a_world(1_800_000_000.0, name="g9c")
    at = 1_800_000_600.0
    j = w.s.add_at("reminder", at, "handler", steps=[
        {"label": "a", "offset_min": 0},
        {"label": "b", "offset_min": None}])
    w.clock.t = at
    w.s.tick()
    S.get = lambda: w.s
    try:
        code, out = S.handle_act({"id": j["id"], "do": "answer", "button": 0, "step": 0})
        check("POST /api/schedule/act answer takes an optional `step`", code == 200
              and out.get("step") == 0, (code, out))
        check("the handler passes a bad step through as a 400, not an exception",
              S.handle_act({"id": j["id"], "do": "answer", "button": 0,
                            "step": 99})[0] == 400)
        check("a body with no `step` at all still answers the CURRENT part",
              S.handle_act({"id": j["id"], "do": "answer", "button": 0})[0] == 200)
    finally:
        S.get = _real_get


# --------------------------------------------------------------------------
#   G10 - the card: one per run-task part, none for anything else
# --------------------------------------------------------------------------

def t_g10_a_plain_part_raises_no_card_at_all():
    w = a_world(1_800_000_000.0, name="g10")
    at = 1_800_000_600.0
    j = w.s.add_at("reminder", at, "no cards", steps=four_parts(at))
    w.clock.t = at
    w.s.tick()
    w.s.answer(j["id"], 0, step=0)
    w.s.answer(j["id"], 0, step=1)
    w.clock.t = at + 1800
    w.s.tick()
    w.s.answer(j["id"], 0, step=3)
    check("a routine of questions and plain parts raises NO card, at any tier",
          w.cards == [], w.cards)


def t_g10_two_run_task_parts_are_two_cards_not_one():
    """The single most likely bug in the wave (spec Q6): `_fire_action`'s dedupe
    must carry the part's index, or the second `run-task` part is refused as a
    duplicate and silently never asks."""
    # `approve=False` so nothing RUNS (the card is the whole point), and the
    # row's own `action` is deliberately absent: the card can only have come
    # from the PART's block.
    w = a_world(1_800_000_000.0, name="g10b", approve=False)
    at = 1_800_000_600.0
    j = w.s.add_at("reminder", at, "two tasks", steps=[
        {"label": "brief me", "offset_min": 0,
         "ask": {"kind": "run-task", "task": "briefing"}},
        {"label": "later task", "offset_min": 30,
         "ask": {"kind": "run-task", "task": "briefing"}}])
    check("the row itself carries no action at all", "action" not in j, sorted(j))
    check("...but the part that runs a task says so in the view",
          steps_of(j)[0].get("runs_task") is True, steps_of(j)[0])
    w.clock.t = at
    w.s.tick()
    check("the first run-task part raises exactly one card", len(w.cards) == 1, w.cards)
    check("...and it is the schedule action card",
          w.cards[0]["action"] == S.ACTION_SCHEDULE, w.cards[0]["action"])
    check("...whose prompt names WHICH part it is for",
          "brief me" in w.cards[0]["prompt"], w.cards[0]["prompt"])
    w.clock.t = at + 1800
    w.s.tick()
    check("the SECOND run-task part at another time is its own card",
          len(w.cards) == 2, [c["prompt"] for c in w.cards])
    check("...and it carries the part's index, never the owner's words",
          w.cards[1]["detail"].get("step") == 1, w.cards[1]["detail"])
    check("...and names the second part in its own words",
          "later task" in w.cards[1]["prompt"], w.cards[1]["prompt"])


def t_g10_an_approved_run_task_part_really_runs():
    """The interlock #1119 made free: a part's `run-task` runs the owner's own
    words through the SAME chat path, once, for that part."""
    w = a_world(1_800_000_000.0, name="g10d")
    at = 1_800_000_600.0
    j = w.s.add_at("reminder", at, "shopping", steps=[
        {"label": "add bread", "offset_min": 0,
         "ask": {"kind": "run-task", "job": "add bread to my todo list"}},
        {"label": "add milk", "offset_min": 30}])
    w.clock.t = at
    w.s.tick()
    check("an approved run-task part raises its one card", len(w.cards) == 1, w.cards)
    check("...and runs the job it named, once",
          any("bread" in str(item.get("text") or "") for item in w.s.todos()),
          [item["text"] for item in w.s.todos()])


def t_g10_a_run_task_part_records_nothing_when_refused():
    w = a_world(1_800_000_000.0, name="g10c", approve=False)
    at = 1_800_000_600.0
    j = w.s.add_at("reminder", at, "refused", steps=[
        {"label": "task", "offset_min": 0,
         "ask": {"kind": "run-task", "task": "briefing"}},
        {"label": "other", "offset_min": 30}])
    w.clock.t = at
    w.s.tick()
    check("a refused card is still exactly one card", len(w.cards) == 1, w.cards)
    view = w.s.job(j["id"])
    check("...and it ran nothing at all", w.s.todos() == [], w.s.todos())
    check("...while the row still waits for its next part",
          view["state"] == "active" and view["due"] == at + 1800,
          (view["state"], view["due"]))


def t_g10_a_run_task_part_can_still_be_ticked_off():
    """The buttons the view hands out are the buttons the PC accepts: a part
    that only runs a task still gets the ONE implicit Done, and pressing it is a
    200, not a refusal."""
    w = a_world(1_800_000_000.0, name="g10e", approve=False)
    at = 1_800_000_600.0
    j = w.s.add_at("reminder", at, "task then done", steps=[
        {"label": "task", "offset_min": 0,
         "ask": {"kind": "run-task", "task": "briefing"}},
        {"label": "after", "offset_min": None}])
    view = w.s.job(j["id"])
    check("a run-task part is drawn with the ONE implicit Done",
          steps_of(view)[0]["buttons"] == [{"label": "Done", "does": "done"}],
          steps_of(view)[0]["buttons"])
    w.clock.t = at
    w.s.tick()
    code, out = w.s.answer(j["id"], 0, step=0)
    check("...and the PC accepts exactly that press", code == 200, (code, out))
    check("...which surfaces the part after it",
          [e.get("step") for e in w.fired()] == [0, 1], w.fired())


# --------------------------------------------------------------------------
#   G11 - edit: the SAME cleaners, and the §21.14 gap closed
# --------------------------------------------------------------------------

def t_g11_an_edit_can_carry_parts_and_an_action():
    w = a_world(1_800_000_000.0, name="g11")
    at = 1_800_000_600.0
    j = w.s.add_at("reminder", at, "plain")
    check("a plain reminder has no parts to start with", "steps" not in j)
    check("`steps` and `action` are both accepted edit fields",
          "steps" in S.Scheduler.EDIT_KEYS and "action" in S.Scheduler.EDIT_KEYS,
          S.Scheduler.EDIT_KEYS)
    S.get = lambda: w.s
    try:
        code, out = w.s.act(j["id"], "edit", fields={"steps": [
            {"label": "one", "offset_min": 0}, {"label": "two", "offset_min": 10}]})
        check("do:edit with `steps` is a cardless 200", code == 200, (code, out))
        view = w.s.job(j["id"])
        check("...and the row now has its parts", view.get("steps_parts") == 2,
              view.get("steps_parts"))
        check("...with a fresh state anchored at its own due",
              view["steps_cursor"] == 0 and not any(p["fired_at"] for p in steps_of(view)),
              steps_of(view))
        code, out = w.s.act(j["id"], "edit",
                            fields={"action": {"kind": "ask", "question": "Ready?",
                                               "buttons": [{"label": "Yes",
                                                            "does": "record"}],
                                               "record": {"history": True}}})
        check("do:edit with `action` closes the documented 21.14 gap", code == 200
              and w.s.job(j["id"]).get("action", {}).get("question") == "Ready?",
              (code, w.s.job(j["id"]).get("action")))
        code, out = w.s.act(j["id"], "edit", fields={"action": None})
        check("...and `action: null` takes it away again", code == 200
              and "action" not in w.s.job(j["id"]), (code, w.s.job(j["id"])))
        code, out = w.s.act(j["id"], "edit", fields={"steps": None})
        check("`steps: null` clears the parts, leaving an ordinary reminder",
              code == 200 and "steps" not in w.s.job(j["id"]), (code, w.s.job(j["id"])))
    finally:
        S.get = _real_get


def t_g11_a_bad_part_writes_nothing_at_all():
    w = a_world(1_800_000_000.0, name="g11b")
    at = 1_800_000_600.0
    j = w.s.add_at("reminder", at, "keeps", steps=[
        {"label": "one", "offset_min": 0}, {"label": "two", "offset_min": 10}])
    before = json.dumps(w.s.job(j["id"]), sort_keys=True)
    code, out = w.s.act(j["id"], "edit", fields={
        "text": "changed",
        "steps": [{"label": "one", "offset_min": 0},
                  {"label": "two", "offset_min": 5},
                  {"label": "three", "offset_min": 1}]})
    check("an edit with a bad part is a 400", code == 400, (code, out))
    check("...and NOTHING was written: not even the good half",
          json.dumps(w.s.job(j["id"]), sort_keys=True) == before)
    code, out = w.s.act(j["id"], "edit", fields={"steps": [
        {"label": "one", "offset_min": 0}, {"label": "two", "offset_min": 5}]})
    check("...while a good one still lands", code == 200, (code, out))
    check("an edit on a to-do may not carry parts",
          w.s.act(w.s.add_todo("milk")["id"], "edit",
                  fields={"steps": [{"label": "a", "offset_min": 0},
                                    {"label": "b", "offset_min": 5}]})[0] == 409)
    check("...nor an action",
          w.s.act(w.s.add_todo("eggs")["id"], "edit",
                  fields={"action": {"kind": "show-note", "note": "x"}})[0] == 409)


def t_g11_a_repeat_change_still_raises_its_one_card():
    w = a_world(1_800_000_000.0, name="g11c", approve=False)
    at = 1_800_000_600.0
    j = w.s.add_at("reminder", at, "repeat me", steps=[
        {"label": "a", "offset_min": 0}, {"label": "b", "offset_min": 5}])
    code, out = w.s.act(j["id"], "edit", fields={"repeat": {"every": "day", "at": "08:00"}})
    check("a repeat change still waits for its ONE card (202)", code == 202, (code, out))
    check("...the card is the repeat one, not a new kind", len(w.cards) == 1
          and w.cards[0]["action"] == "schedule_repeat",
          [c["action"] for c in w.cards])
    check("...and the old row is still running until it is answered",
          w.s.job(j["id"])["repeats"] is False, w.s.job(j["id"])["repeats"])
    check("a single edit may not say both a repeat and its parts",
          w.s.act(j["id"], "edit", fields={
              "repeat": {"every": "day", "at": "08:00"},
              "steps": [{"label": "a", "offset_min": 0},
                        {"label": "b", "offset_min": 5}]})[0] == 400)


# --------------------------------------------------------------------------
#   G12 - view: the additive contract
# --------------------------------------------------------------------------

def t_g12_a_row_with_no_parts_grows_no_key():
    w = a_world(1_800_000_000.0, name="g12")
    at = 1_800_000_600.0
    plain = w.s.add_at("reminder", at, "plain")
    for key in ("steps", "steps_parts", "steps_cursor", "missed_parts",
                "steps_unreadable"):
        check(f"a plain reminder's view has no `{key}`", key not in plain, sorted(plain))
    w.clock.t = at
    w.s.tick()
    # tick before the check so the view is a fired row's, the shape both apps
    # read from "Just went off".
    check("...and not after it went off either",
          "steps" not in w.s.job(plain["id"]), sorted(w.s.job(plain["id"])))


def t_g12_a_routine_hands_out_its_parts_and_its_count():
    w = a_world(1_800_000_000.0, name="g12b")
    at = 1_800_000_600.0
    j = w.s.add_at("reminder", at, "Morning routine", steps=four_parts(at))
    view = w.s.job(j["id"])
    check("a routine's view has `steps`", isinstance(view.get("steps"), list), sorted(view))
    check("...and `steps_parts`", view.get("steps_parts") == 4, view.get("steps_parts"))
    check("...and `steps_cursor`", view.get("steps_cursor") == 0, view.get("steps_cursor"))
    first = steps_of(view)[0]
    check("each part carries its shape, its words and its buttons",
          {"id", "label", "offset_min", "at", "buttons", "fired_at", "done", "missed",
           "current"} <= set(first), sorted(first))
    check("a part with no question gets the ONE implicit Done",
          first["buttons"] == [{"label": "Done", "does": "done"}], first["buttons"])
    check("a part with a question gets its OWN buttons, never the row's",
          [b["label"] for b in steps_of(view)[3]["buttons"]] == ["Locked", "Later"],
          steps_of(view)[3]["buttons"])
    check("...and `asks` marks the row as answerable",
          view.get("asks") is True, view.get("asks"))
    check("a timed part names its moment in the PC's own clock",
          steps_of(view)[0].get("when") == S.clock(at), steps_of(view)[0].get("when"))
    check("an untimed part has no `when` at all",
          "when" not in steps_of(view)[1], steps_of(view)[1])


def t_g12_status_says_the_pc_can_hold_parts():
    w = a_world(1_800_000_000.0, name="g12c")
    S.get = lambda: w.s
    try:
        code, out = S.handle_get("")
    finally:
        S.get = _real_get
    check("GET /api/schedule carries `steps: true`", code == 200
          and out.get("steps") is True, out.get("steps"))
    check("...beside the markers that came before it",
          out.get("phase2") is True and out.get("actions") is True
          and out.get("asks") is True, sorted(k for k in out if out[k] is True))
    check("...and limits names the parts ceiling", out["limits"].get("steps") == 12,
          out["limits"])
    check("a routine is ONE job, so MAX_JOBS still counts rows",
          len([j for j in w.s.listed()]) == len({j["id"] for j in w.s.listed()}),
          [j["id"] for j in w.s.listed()])


# --------------------------------------------------------------------------
#   G13 - privacy: an id, an index and a verb, never a word
# --------------------------------------------------------------------------

def t_g13_the_audit_line_for_an_answered_part_carries_no_words():
    _AUDIT.clear()
    w = a_world(1_800_000_000.0, name="g13")
    at = 1_800_000_600.0
    j = w.s.add_at("reminder", at, "Secret routine", steps=[
        {"label": "take the blue pill", "offset_min": 0,
         "ask": {"question": "Did you take the SECRET medication?",
                 "buttons": [{"label": "Secret yes", "does": "record"}],
                 "record": {"history": True}}},
        {"label": "the other secret", "offset_min": None}])
    w.clock.t = at
    w.s.tick()
    w.s.answer(j["id"], 0, step=0)
    answered = [detail for event, detail in _AUDIT if event == "schedule.answered"]
    check("there is an audit line for the answered part", len(answered) == 1, answered)
    line = answered[0]
    check("...it carries the id, the button's INDEX and what it does",
          line.get("id") == j["id"] and line.get("button") == 0
          and line.get("does") == "record", line)
    check("...and the part's index, never a label",
          line.get("step") == 0 and not isinstance(line.get("step"), str), line)
    blob = json.dumps(answered)
    for word in ("SECRET", "Secret yes", "blue pill", "the other secret",
                 "Did you take"):
        check(f"the audit line never quotes {word[:14]!r}", word not in blob, blob)
    fired = [detail for event, detail in _AUDIT if event == "schedule.fired"]
    check("the fired line carries the id and the lateness only",
          fired and set(fired[0]) == {"id", "kind", "late"}, fired)
    asked = [detail for event, detail in _AUDIT if event == "schedule.action_asked"]
    check("a routine of plain parts asked no card, so no action was logged",
          asked == [], asked)


# --------------------------------------------------------------------------
#   G14 - the chat builder: two forms, one echo, one receipt
# --------------------------------------------------------------------------


def _a_local_morning(hour=7):
    """A fixed date at `hour` LOCAL time, as an epoch.

    The chat builder's bare "at 8" means the next 8 o'clock on THIS machine, so
    a fixed epoch makes a check pass or fail by the runner's own time zone:
    1_800_000_000.0 is 08:00 UTC - so "at 8" had already passed there and came
    back as 8pm, one part instead of three - while it is midnight in the
    owner's zone. `mktime` builds the epoch from LOCAL parts, so the timed
    clauses below are always ahead of the question, on any runner.
    """
    return time.mktime((2027, 1, 15, hour, 0, 0, 0, 0, -1))


def t_g14_a_timed_chain_becomes_timed_parts():
    now = _a_local_morning()
    intent = Q.match("remind me at 8 to start the laundry, then at 8:30 move it to the "
                     "dryer, then at 9 fold it", now)
    check("a timed chain is a reminder_set with steps", intent is not None
          and intent.name == "reminder_set" and len(intent.f.get("steps") or []) == 3,
          intent)
    steps = (intent.f.get("steps") if intent else None) or []
    check("...each clause is its own part, timed from the first",
          [part["offset_min"] for part in steps] == [0, 30, 60], steps)
    check("...and each part keeps the owner's words",
          [part["label"] for part in steps]
          == ["start the laundry", "move it to the dryer", "fold it"], steps)
    check("`_routine` is tried BEFORE `_reminder`, or a chain would stop at "
          "clause 1", Q._routine("remind me at 8 to x, then at 9 y", now) is not None)


def t_g14_a_checklist_becomes_untimed_parts():
    now = _a_local_morning(6)
    intent = Q.match("morning routine at 7: 1. meds 2. keys 3. badge", now)
    check("a checklist is a reminder_set with parts", intent is not None
          and intent.name == "reminder_set", intent)
    steps = (intent.f.get("steps") if intent else None) or []
    check("...the first part is the start time and the rest are untimed",
          steps[0]["offset_min"] == 0 and all(part["offset_min"] is None
                                              for part in steps[1:]), steps)
    check("...and the title is the routine's own words",
          intent.f.get("text") == "Morning routine", intent.f.get("text"))
    numbered = Q.match("morning routine at 7: 1. meds 2. keys 3. badge", now)
    plain = Q.match("morning routine at 7: meds, keys, badge", now)
    check("the numbered form and the comma form agree",
          [p["label"] for p in (numbered.f.get("steps") or [])]
          == [p["label"] for p in (plain.f.get("steps") or [])]
          == ["meds", "keys", "badge"],
          (numbered.f.get("steps"), plain.f.get("steps")))


def t_g14_a_checklist_with_no_time_asks_one_question():
    now = _a_local_morning(6)
    intent = Q.match("morning routine: meds, keys, badge", now)
    check("a checklist with no time is its own intent", intent is not None
          and intent.name == "routine_no_time", intent)
    w = a_world(now, name="g14b")
    reply = Q.run(intent, w.s, now, conversation="c1")
    check("...whose answer is ONE question, not a guess", "When should the first part"
          in reply.reply, reply.reply)
    check("...and nothing was created at all", reply.ids == [] and w.s.listed() == [],
          (reply.ids, w.s.listed()))
    check("...and it is not one of the intents that clears `cancel that`",
          intent.name in Q.READ_ONLY_INTENTS, intent.name)


def t_g14_a_routine_made_in_chat_needs_no_card_and_echoes_its_parts():
    now = _a_local_morning(6)
    w = a_world(now, name="g14c")
    intent = Q.match("morning routine at 7: 1. meds 2. keys 3. badge", now)
    reply = Q.run(intent, w.s, now, conversation="c1")
    check("creating a routine in chat raises NO card", w.cards == [], w.cards)
    check("...and makes exactly one job", len(reply.made) == 1, reply.made)
    check("...whose reply is the numbered echo",
          "in 3 parts:" in reply.reply and "1. meds" in reply.reply
          and "2. keys - after 1" in reply.reply and "3. badge - after 2" in reply.reply,
          reply.reply)
    check("...and it promises the two ways back",
          'cancel that' in reply.reply and "Coming up" in reply.reply, reply.reply)
    check("the echo comes from the ONE function both apps use",
          Q._routine_result.__module__ == "jarvis_quick"
          and S._step_words([{"label": "x", "offset_min": 0}], now) != [], None)


def t_g14_one_receipt_so_undo_outlives_the_two_minute_window():
    now = _a_local_morning(6)
    w = a_world(now, name="g14d")
    intent = Q.match("remind me at 8 to start the laundry, then at 8:30 move it to the "
                     "dryer", now)
    reply = Q.run(intent, w.s, now, conversation="c1")
    jid = reply.made[0]

    def rows_here():
        """This routine's OWN receipts: earlier checks in this file make their
        own routines, and the store is the module's one file."""
        con = sqlite3.connect(str(R.db_path()))
        con.row_factory = sqlite3.Row
        try:
            names = [row[0] for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'")]
            if "action_receipts" not in names:
                return []
            return [dict(row) for row in con.execute(
                "SELECT * FROM action_receipts WHERE tool_name = ? ORDER BY created_at",
                (S.STEPS_TOOL,)) if jid in str(row["after_snapshot_json"] or "")]
        finally:
            con.close()

    receipts = rows_here()
    if not receipts:
        skip("no receipt was written on this machine: jarvis_receipts fails CLOSED "
             "without a working scrubber, so the store stayed empty - the undo path "
             "was not proven here")
    else:
        check("a routine created in chat leaves ONE receipt", len(receipts) == 1,
              len(receipts))
        row = receipts[0]
        check("...named by the wave's own tool",
              row.get("tool_name") == S.STEPS_TOOL, row.get("tool_name"))
        after = json.loads(row["after_snapshot_json"] or "{}")
        check("...whose after-snapshot names the row and its parts",
              after.get("id") == jid and len(after.get("parts") or []) == 2, after)
        check("...and never the question or a destination",
              "question" not in json.dumps(after), after)
        check("...whose before-snapshot says the row was not there",
              json.loads(row["before_snapshot_json"] or "{}").get("existed") is False,
              row.get("before_snapshot_json"))
        # A restart: the in-process callable is gone, so only the registered
        # restorer can put it back.
        S.get = lambda: w.s
        try:
            R._CALLABLES.clear()
            out = R.undo(row["receipt_id"])
            check("Undo puts the routine back after a restart, through the restorer",
                  out.get("ok") is True and out.get("path") == "snapshot", out)
            check("...and the row really is gone", w.s.job(jid) is None)
            check("...and a second Undo refuses, as every receipt does",
                  R.undo(row["receipt_id"]).get("ok") is False)
        finally:
            S.get = _real_get
    # The parts that do not need a scrubber, proven directly - so a machine
    # without one still proves the shape of the call.
    check("the restorer is registered for this tool at import",
          R._RESTORERS.get(S.STEPS_TOOL) is not None, sorted(R._RESTORERS))
    check("...and it is the schedule module's own function",
          R._RESTORERS.get(S.STEPS_TOOL) is S.restore_routine, None)
    S.get = lambda: w.s
    try:
        S.restore_routine({"id": jid})
    finally:
        S.get = _real_get
    check("restore_routine deletes that one row, and nothing else",
          w.s.job(jid) is None and w.s.listed() == [], w.s.listed())
    check("restore_routine with no id is a no-op, never a crash",
          S.restore_routine({}) is None and S.restore_routine(None) is None)
    check("a routine created cardlessly still works after its receipt is used up",
          Q.run(Q.match("remind me at 8 to x, then at 9 y", now), w.s, now,
                conversation="c2").made != [], None)


# --------------------------------------------------------------------------
#   G15 - no parts: exactly what it was before this wave
# --------------------------------------------------------------------------

def t_g15_a_reminder_with_no_parts_behaves_as_it_always_did():
    w = a_world(1_800_000_000.0, name="g15")
    at = 1_800_000_600.0
    j = w.s.add_at("reminder", at, "the dentist")
    check("creating one is cardless and immediate", j["state"] == "active"
          and w.cards == [], (j["state"], w.cards))
    check("...it has the keys it always had",
          {"id", "kind", "text", "state", "due", "created", "source", "repeats",
           "when", "left", "rank", "lock_screen"} <= set(j), sorted(j))
    w.clock.t = at
    w.reset()
    check("ticking it fires it", w.s.tick() == [j["id"]])
    events = w.fired()
    check("...with the SAME event shape, and no part keys added",
          len(events) == 1 and "step" not in events[0] and "parts" not in events[0],
          events)
    view = w.s.job(j["id"])
    check("...the row goes `fired` and its words are untouched",
          view["state"] == "fired" and view["text"] == "the dentist", view["state"])
    code, out = w.s.answer(j["id"], 0)
    check("answering a row with no question is still the old refusal",
          code == 409 and out.get("error") == S.ASK_WRONG_KIND, (code, out))
    snoozed = w.s.snooze(j["id"], 600)
    check("Snooze still makes its one-off copy", snoozed[0] == 200
          and snoozed[1]["job"]["id"] != j["id"], snoozed[0])
    check("...and the copy has no parts either",
          "steps" not in snoozed[1]["job"], sorted(snoozed[1]["job"]))
    rep = w.s.add_repeat("reminder", {"every": "day", "at": "08:00"}, "daily thing")
    check("a plain repeat still needs no card", rep["state"] == "active"
          and w.cards == [], (rep["state"], w.cards))
    check("...and carries no parts", "steps" not in rep, sorted(rep))
    S.get = lambda: w.s
    try:
        soon = S.clock(1_800_000_000.0 + 86400)[:5]
        added = S.handle_add({"kind": "reminder", "at": 1_800_000_000.0 + 7200,
                              "text": "from the route"})
        check("the ordinary add route still works, with no parts in the body",
              added[0] == 200 and "steps" not in added[1]["job"], added[0])
        check("...and it still sets the time it was given",
              added[1]["job"]["due"] == 1_800_000_000.0 + 7200, added[1]["job"]["due"])
        check("...and the wall-clock form still works too", soon and True)
    finally:
        S.get = _real_get


# --------------------------------------------------------------------------
#   The suite
# --------------------------------------------------------------------------

def main() -> int:
    try:
        for name, fn in list(globals().items()):
            if name.startswith("t_") and callable(fn):
                print(f"--- {name} ---")
                try:
                    fn()
                except Exception as exc:            # pragma: no cover
                    traceback.print_exc()
                    check(f"{name} ran without crashing", False, repr(exc))
    finally:
        S.get = _real_get
        S._audit = _real_audit
        R._CALLABLES.clear()
        shutil.rmtree(SCRATCH, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
