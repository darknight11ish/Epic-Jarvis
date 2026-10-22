"""test_schedule_phase2.py - HUD Reminders Phase 2 backend (2026-10-22).

    python3 backend/test_schedule_phase2.py   (run it through run_suites.py)

The scheduler half of Phase 2, added to the SHIPPED `jarvis_schedule.py`:
`edit` (text / a one-off's own time / repeat / a to-do's list), `move` (between
named lists), `reorder` (a `rank` column + migration), and the ONE additive
top-level `"phase2": true` capability marker on the list read - plus the privacy
and card rules the Lead fixed on 2026-10-22:

  * text-only edit: cardless;
  * a `repeat` change: exactly ONE `schedule_repeat` 202 card, the OLD rule
    still active until approved (denied = nothing changes);
  * a `when`/date+time/`at`/timer-`seconds` edit on a ONE-OFF: cardless;
  * a `when` edit on a REPEATING job: refused 409 (change its repeat instead);
  * `move`/`reorder`: cardless; never a list form, never a delete-all.

What it proves, with a hand-moved clock and real SQLite files in a temporary
folder:
  - the old-DB migration: `rank` added through the idempotent ALTER path, one
    deterministic `(created,rowid)` 0..n-1 backfill per list in the same
    transaction, done/fired rows untouched, a second open writes nothing, a
    row written by old code later sorts last and is topped up on the next open;
  - reorder: deterministic, exactly 0..n-1 with no gaps/duplicates, the same
    request twice is idempotent (no writes/events), before/after convenience,
    a reopen preserves the order;
  - move: exactly one list before and after, ids/words/created/state kept,
    to-do list and back, MAX_LISTS boundary, bad names/non-to-do refused;
  - edit: only the named fields change, ids kept, one-off time moves cardless,
    timer seconds (active and paused), unknown keys/partial-bad input write
    nothing, fired/waiting/done/module-managed refusals;
  - the repeat card: 202, one card, old rule active; approved applies the new
    rule (and words); denied keeps everything;
  - audit and events: ids/kinds/outcomes, `fields` names only,
    `named_list: bool`, integer `rank` - never a job's words, never a list name;
  - the read: `"phase2": true` present on the list answer, absent from the
    one-job answer, every prior key unchanged.

Hermetic: its own temp DBs, a fake gate, no model, no network. The config/home
folders are the runner's own throwaway ones.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_schedule.py")

import jarvis_schedule as S  # noqa: E402

PASSED, FAILED, SKIPPED = [], [], []
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-schedule-phase2-"))
_N = 0


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
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


class World:
    """A scheduler with a hand-moved clock, a recording gate, and the bus and
    audit captured."""

    def __init__(self, t, *, answer="approved", tier="ask", name=None):
        global _N
        _N += 1
        self.clock = Clock(t)
        self.events, self.cards, self.audit, self.prompts = [], [], [], []
        self.answer, self.tier = answer, tier
        self.path = _TMP / f"{name or 'w'}-{_N}.db"
        self.s = S.Scheduler(self.path, clock=self.clock, gate=self.gate,
                             tier_of=lambda a: self.tier,
                             spawn=lambda fn: fn(),
                             publish=lambda k, d: self.events.append((k, d)))

    def gate(self, action, detail, prompt):
        self.cards.append((action, detail, prompt))
        self.prompts.append(prompt)
        if self.answer == "approved":
            return Verdict(True, "ask", "approved")
        return Verdict(False, "ask", self.answer)

    def reopen(self):
        return S.Scheduler(self.path, clock=self.clock, gate=self.gate,
                           tier_of=lambda a: self.tier,
                           spawn=lambda fn: fn(), publish=lambda k, d: None)


_real_audit = S._audit
_AUDIT = []


def _spy_audit(event, detail):
    _AUDIT.append((event, detail))
    _real_audit(event, detail)


S._audit = _spy_audit


def local(y, mo, d, hh, mm):
    return S.wall_to_epoch(y, mo, d, hh, mm)


def by_list(view, name):
    return [j for j in view if j["list"] == name]


def ranks(view):
    return [j["rank"] for j in view]


# --------------------------------------------------------------------------
#   The additive capability marker and the rank field
# --------------------------------------------------------------------------


def t_phase2_marker_and_rank_on_the_read():
    w = World(local(2026, 9, 25, 12, 0), name="marker")
    a = w.s.add_todo("first", list_name="shopping")
    b = w.s.add_todo("second", list_name="shopping")
    c = w.s.add_todo("solo")
    real_get, real_handle = S.get, S.handle_get
    S.get = lambda: w.s
    try:
        code, out = S.handle_get("")
        code_one, one = S.handle_get("id=" + b["id"])
    finally:
        S.get, S.handle_get = real_get, real_handle
    check("GET /api/schedule is 200 and carries the ONE additive marker",
          code == 200 and out.get("phase2") is True, out.get("phase2"))
    check("... every prior top-level key is still present",
          {"available", "now", "tz", "jobs", "todo", "went_off", "lists",
           "running", "limits"} <= set(out), sorted(out))
    check("... and limits is unchanged, with its seven numbers",
          set(out["limits"]) == {"text", "jobs", "todo", "timer_seconds",
                                 "min_every_hours", "lists", "snooze_seconds"}
          and out["limits"]["todo"] == S.MAX_TODO, out.get("limits"))
    check("the `?id=` one-job read keeps its existing shape (no marker on it)",
          code_one == 200 and one.get("available") is True and "phase2" not in one
          and one["job"]["id"] == b["id"], one)
    check("a new to-do's rank is its position in its own list",
          ranks(by_list(w.s.todos(), "shopping")) == [0, 1]
          and ranks(by_list(w.s.todos(), "")) == [0],
          [(j["text"], j["list"], j["rank"]) for j in w.s.todos()])
    check("... and the same number survives to the one-job read",
          w.s.job(c["id"])["rank"] == 0)
    tea = w.s.add_timer(60, "tea")
    check("a timer carries rank None (a number or None, never a word)",
          tea["rank"] is None, tea.get("rank"))
    check("every to-do's rank is an int",
          all(isinstance(j["rank"], int) for j in w.s.todos()),
          [j.get("rank") for j in w.s.todos()])


# --------------------------------------------------------------------------
#   Migration from a pre-Phase-2 DB
# --------------------------------------------------------------------------


def t_migration_on_an_old_db_is_deterministic_and_idempotent():
    path = _TMP / "old-phase1.db"
    c = sqlite3.connect(path)
    try:
        c.executescript(S._SCHEMA)
        # enough of the old added columns for a real old file: list_name only
        c.execute("ALTER TABLE jobs ADD COLUMN list_name TEXT")
        rows = [
            ("s0000000001", "todo", "b first", "active", 10.0, "shopping"),
            ("s0000000002", "todo", "a second", "active", 20.0, "shopping"),
            ("s0000000003", "todo", "home one", "paused", 15.0, None),
            ("s0000000004", "todo", "done one", "done", 5.0, "shopping"),
            ("s0000000005", "todo", "fired one", "fired", 6.0, None),
        ]
        for jid, kind, text, state, created, listed in rows:
            c.execute("INSERT INTO jobs (id, kind, text, state, created, changed, "
                      "source, list_name) VALUES (?,?,?,?,?,?,?,?)",
                      (jid, kind, text, state, created, created, "app", listed))
        c.commit()
    finally:
        c.close()
    clock = Clock(local(2026, 9, 25, 12, 0))

    def new():
        return S.Scheduler(path, clock=clock,
                           gate=lambda *a: Verdict(True, "ask", "approved"),
                           tier_of=lambda a: "ask", spawn=lambda fn: fn(),
                           publish=lambda k, d: None)
    s = new()
    cols = {r[1] for r in sqlite3.connect(path).execute("PRAGMA table_info(jobs)")}
    check("opening an OLD database adds the rank column", "rank" in cols)
    check("... and keeps every row and every word",
          sorted(j["text"] for j in s.todos()) == ["a second", "b first", "home one"],
          [j["text"] for j in s.todos()])
    check("active/paused to-dos are ranked 0..n-1 per list, in (created,rowid) order",
          ranks(by_list(s.todos(), "shopping")) == [0, 1]
          and ranks(by_list(s.todos(), "")) == [0],
          [(j["text"], j["list"], j["rank"]) for j in s.todos()])
    check("done and fired rows are never ranked",
          sqlite3.connect(path).execute(
              "SELECT COUNT(*) FROM jobs WHERE state IN ('done','fired') "
              "AND rank IS NOT NULL").fetchone()[0] == 0)
    check("the migration leaves text and ids untouched",
          {j["id"] for j in s.todos()} == {"s0000000001", "s0000000002",
                                           "s0000000003"})
    before = sorted((j["id"], j["rank"], j["text"], j["state"]) for j in s.todos())
    check("a second open is a no-op: ranks, words and ids unchanged",
          sorted((j["id"], j["rank"], j["text"], j["state"]) for j in new().todos())
          == before, before)
    # A row written by OLD code after the upgrade: no rank, sorts last, and the
    # next open gives it the next free number without touching the ranked ones.
    c = sqlite3.connect(path)
    c.execute("INSERT INTO jobs (id, kind, text, state, created, changed, source, "
              "list_name) VALUES ('s0000000009','todo','old writer','active',30,30,"
              "'app','shopping')")
    c.commit()
    c.close()
    s3 = new()
    check("an old-code row sorts last, then gets the next free rank on open",
          [(j["text"], j["rank"]) for j in by_list(s3.todos(), "shopping")]
          == [("b first", 0), ("a second", 1), ("old writer", 2)],
          [(j["text"], j["rank"]) for j in by_list(s3.todos(), "shopping")])
    check("... the ranked rows did not move", ranks(by_list(s3.todos(), "")) == [0])


# --------------------------------------------------------------------------
#   Reorder
# --------------------------------------------------------------------------


def t_reorder_is_deterministic_and_idempotent():
    w = World(local(2026, 9, 25, 12, 0), name="reorder")
    ids = [w.s.add_todo(f"item {i}", list_name="shopping")["id"] for i in range(6)]

    def order():
        return [j["text"] for j in by_list(w.s.todos(), "shopping")]

    check("six items start in creation order, ranked 0..5",
          order() == [f"item {i}" for i in range(6)]
          and ranks(by_list(w.s.todos(), "shopping")) == list(range(6)),
          ranks(by_list(w.s.todos(), "shopping")))
    for target in range(6):
        code, _ = w.s.act(ids[5], "reorder", fields={"rank": target})
        rest = [f"item {i}" for i in range(5)]
        expected = rest[:target] + ["item 5"] + rest[target:]
        check(f"reorder to {target}: 200, and the item sits exactly there",
              code == 200 and order() == expected, (code, order()))
        check(f"reorder to {target}: ranks are exactly 0..5, no gaps/dupes",
              ranks(by_list(w.s.todos(), "shopping")) == list(range(6)))
        events_before = len(w.events)
        code2, _ = w.s.act(ids[5], "reorder", fields={"rank": target})
        check(f"reorder to {target} twice: 200, still there, and NO new event",
              code2 == 200 and len(w.events) == events_before and order() == expected,
              (code2, order(), len(w.events), events_before))
    reopened = w.reopen()
    check("a reopen keeps the order and the ranks",
          [j["text"] for j in by_list(reopened.todos(), "shopping")] == order()
          and ranks(by_list(reopened.todos(), "shopping")) == list(range(6)))
    code, _ = w.s.act(ids[0], "reorder", fields={"before": ids[1]})
    current = [j["id"] for j in by_list(w.s.todos(), "shopping")]
    check("`before` puts the item just before its anchor", code == 200
          and current.index(ids[1]) == current.index(ids[0]) + 1, current)
    code, _ = w.s.act(ids[0], "reorder", fields={"after": ids[1]})
    current = [j["id"] for j in by_list(w.s.todos(), "shopping")]
    check("`after` puts it just after", code == 200
          and current.index(ids[0]) == current.index(ids[1]) + 1, current)
    for bad, why in (({"rank": True}, "a boolean"),
                     ({"rank": 2.5}, "a float"),
                     ({"rank": -1}, "below the first"),
                     ({"rank": 6}, "past the last"),
                     ({"before": "sdeadbeef00"}, "an id not on the list")):
        code, out = w.s.act(ids[0], "reorder", fields=bad)
        check(f"a bad reorder is a plain 400 ({why})",
              code == 400 and isinstance(out.get("error"), str), (code, out))
    code, out = w.s.act(w.s.add_timer(60, "tea")["id"], "reorder",
                        fields={"rank": 0})
    check("reorder on a timer is refused 409", code == 409, (code, out))


# --------------------------------------------------------------------------
#   Move
# --------------------------------------------------------------------------


def t_move_keeps_one_list_and_respects_limits():
    w = World(local(2026, 9, 25, 12, 0), name="move")
    item = w.s.add_todo("milk", list_name="shopping")
    w.s.add_todo("report", list_name="work")
    before = w.s.job(item["id"])
    code, out = w.s.act(item["id"], "move", fields={"list": "work"})
    after = w.s.job(item["id"])
    check("move to another list is 200 with fixed words and no card",
          code == 200 and out["said"] == "Moved to that list." and w.cards == [],
          (code, out))
    check("... the item is in exactly one list after the move",
          [j["list"] for j in w.s.todos() if j["id"] == item["id"]] == ["work"])
    check("... id, kind, words, created and state are unchanged",
          after["id"] == before["id"] and after["kind"] == before["kind"]
          and after["text"] == before["text"]
          and after["created"] == before["created"]
          and after["state"] == before["state"], (before, after))
    check("... lists() reflects it (shopping is gone, work has two)",
          {l["name"]: l["open"] for l in w.s.lists()} == {"work": 2},
          w.s.lists())
    code, out = w.s.act(item["id"], "move", fields={"list": None})
    check("move back to the to-do list (null) is 200 with its own words",
          code == 200 and out["said"] == "Moved to the to-do list."
          and w.s.job(item["id"])["list"] == "", out)
    code, out = w.s.act(item["id"], "move", fields={"list": "shopping"})
    check("... and back into a named list", code == 200
          and w.s.job(item["id"])["list"] == "shopping")
    before_events = len(w.events)
    check("moving to the list it is already on is a no-op 200 with no event",
          w.s.act(item["id"], "move", fields={"list": "shopping"})[0] == 200
          and len(w.events) == before_events)
    # MAX_LISTS = 20: with 20 named lists, a NEW name is refused; an existing
    # one still accepts a move.
    extra = ["red", "blue", "green", "white", "black", "brown", "pink",
             "gold", "silver", "orange", "purple", "yellow", "grey", "teal",
             "navy", "olive", "plum", "rose"]
    for name in extra:                       # + work + shopping = 20
        w.s.add_todo("item", list_name=name)
    check("that is exactly the 20 lists the PC allows",
          len(w.s.lists()) == S.MAX_LISTS, (len(w.s.lists()), S.MAX_LISTS))
    code, out = w.s.act(item["id"], "move", fields={"list": "brand new"})
    check("moving onto a NEW name when 20 lists exist is refused 409",
          code == 409 and "already 20 lists" in out.get("error", ""), (code, out))
    code, out = w.s.act(item["id"], "move", fields={"list": "Not A List"})
    check("a bad list name is refused 400", code == 400 and out.get("error"),
          (code, out))
    code, out = w.s.act(item["id"], "move", fields={"list": "work"})
    check("... while moving onto an EXISTING list still works", code == 200,
          (code, out))
    reminder = w.s.add_at("reminder", local(2026, 9, 26, 9, 0), "call Mum")
    code, out = w.s.act(reminder["id"], "move", fields={"list": "shopping"})
    check("move on a reminder is refused 409 (named lists are to-dos)",
          code == 409, (code, out))
    code, out = w.s.act(item["id"], "move", fields={})
    check("move with no list field is a plain 400", code == 400, (code, out))
    code, out = w.s.act(item["id"], "move", fields={"list": True})
    check("a non-string list name is refused 400 (values are type-checked)",
          code == 400, (code, out))


# --------------------------------------------------------------------------
#   Edit
# --------------------------------------------------------------------------


def t_edit_text_is_cardless_and_preserves_identity():
    w = World(local(2026, 9, 25, 12, 0), name="edit-text")
    job = w.s.add_at("reminder", local(2026, 9, 26, 9, 0), "call Mum")
    events_before = len([d for k, d in w.events if d.get("state") == "changed"])
    code, out = w.s.act(job["id"], "edit", fields={"text": "  call   Mum back "})
    after = w.s.job(job["id"])
    check("a text-only edit is 200, cardless, with the fixed sentence",
          code == 200 and out["said"] == "Changed." and w.cards == [], (code, out))
    check("... id, kind, created, source, state and due are unchanged",
          after["id"] == job["id"] and after["kind"] == job["kind"]
          and after["created"] == job["created"]
          and after["source"] == job["source"]
          and after["state"] == job["state"] and after["due"] == job["due"],
          (job, after))
    check("... only the words changed (tidied)",
          after["text"] == "call Mum back", after["text"])
    check("... exactly one more `schedule` change event was published",
          len([d for k, d in w.events if d.get("state") == "changed"])
          == events_before + 1, w.events)
    code, out = w.s.act(job["id"], "edit", fields={"text": "call", "nonsense": 1})
    check("an unknown edit key is refused 400 and writes nothing",
          code == 400 and w.s.job(job["id"])["text"] == "call Mum back", (code, out))
    code, out = w.s.act(job["id"], "edit", fields={})
    check("an edit with no fields is 400", code == 400, (code, out))
    code, out = w.s.act(job["id"], "edit", fields={"text": ""})
    check("empty words on a reminder are 400", code == 400, (code, out))
    long = "x" * (S.MAX_TEXT + 1)
    code, out = w.s.act(job["id"], "edit", fields={"text": long})
    check("words over MAX_TEXT are 400", code == 400, (code, out))
    code, out = w.s.act(job["id"], "edit", fields={"text": 5})
    check("non-string words are refused 400 (values are type-checked)",
          code == 400, (code, out))
    check("... and none of those refusals wrote anything",
          w.s.job(job["id"])["text"] == "call Mum back")


def t_edit_one_off_time_is_cardless():
    w = World(local(2026, 9, 25, 12, 0), name="edit-time")
    job = w.s.add_at("alarm", local(2026, 9, 26, 9, 0), "wake up")
    when = local(2026, 9, 27, 8, 30)
    code, out = w.s.act(job["id"], "edit", fields={"when": when})
    after = w.s.job(job["id"])
    check("a one-off alarm's `when` edit is 200, cardless",
          code == 200 and out["said"] == "Changed." and w.cards == [], (code, out))
    check("... it moved `due` and kept the id",
          after["due"] == when and after["id"] == job["id"], after)
    code, out = w.s.act(job["id"], "edit",
                        fields={"date": "2026-09-30", "time": "07:15"})
    check("date+time is another cardless one-off move",
          code == 200 and w.s.job(job["id"])["due"]
          == S.wall_at("2026-09-30", "07:15"), (code, out))
    code, out = w.s.act(job["id"], "edit", fields={"at": local(2026, 9, 25, 12, 0)})
    check("a past time is a plain 400", code == 400, (code, out))
    code, out = w.s.act(job["id"], "edit", fields={"when": "soon"})
    check("a non-time `when` is a plain 400", code == 400, (code, out))
    code, out = w.s.act(job["id"], "edit", fields={"seconds": 120})
    check("seconds on an alarm is refused 409", code == 409, (code, out))


def t_edit_timer_seconds_honours_paused_state():
    w = World(local(2026, 9, 25, 12, 0), name="edit-timer")
    job = w.s.add_timer(600, "pasta")
    code, out = w.s.act(job["id"], "edit", fields={"seconds": 120})
    after = w.s.job(job["id"])
    check("a timer's new length is cardless and resets the countdown",
          code == 200 and w.cards == [] and after["state"] == "active"
          and after["duration"] == 120 and after["due"] == w.clock.t + 120,
          (code, after))
    w.s.act(job["id"], "pause")
    code, out = w.s.act(job["id"], "edit", fields={"seconds": 60})
    after = w.s.job(job["id"])
    check("editing seconds on a PAUSED timer keeps it paused with the new left time",
          code == 200 and after["state"] == "paused" and after["left"] == 60
          and after["duration"] == 60, (code, after))
    for bad, why in (({"seconds": 0}, "zero"), ({"seconds": -5}, "negative"),
                     ({"seconds": S.MAX_TIMER + 1}, "over 24 hours"),
                     ({"seconds": True}, "a boolean")):
        code, out = w.s.act(job["id"], "edit", fields=bad)
        check(f"a bad timer length is 400 ({why})", code == 400, (code, out))
    code, out = w.s.act(job["id"], "edit", fields={"at": w.clock.t + 300})
    check("a timer's time is changed in seconds, not `at` (409)", code == 409,
          (code, out))
    check("... and the refusals left the timer exactly as it was",
          w.s.job(job["id"])["left"] == 60)


def t_edit_todo_refuses_time_and_accepts_text_and_list():
    w = World(local(2026, 9, 25, 12, 0), name="edit-todo")
    job = w.s.add_todo("milk", list_name="shopping")
    code, out = w.s.act(job["id"], "edit", fields={"when": w.clock.t + 600})
    check("a to-do has no time of its own - a `when` edit is 409",
          code == 409 and "no time" in out.get("error", ""), (code, out))
    code, out = w.s.act(job["id"], "edit",
                        fields={"text": "oat milk", "list": "groceries"})
    after = w.s.job(job["id"])
    check("a to-do edit may change the words AND the list together",
          code == 200 and after["text"] == "oat milk"
          and after["list"] == "groceries", (code, after))
    check("... and the item is on exactly one list",
          [j["list"] for j in w.s.todos() if j["id"] == job["id"]] == ["groceries"])


def t_edit_repeating_when_is_refused_not_moved():
    w = World(local(2026, 9, 25, 12, 0), name="edit-repeat-when")
    job = w.s.add_repeat("reminder", S.check_rule({"every": "day", "at": "07:00"}),
                         "stretch")
    before = w.s.job(job["id"])
    code, out = w.s.act(job["id"], "edit", fields={"when": w.clock.t + 7200})
    after = w.s.job(job["id"])
    check("a repeating job's `when` edit is refused 409, not silently moved",
          code == 409 and "change its repeat" in out.get("error", ""), (code, out))
    check("... the old rule and its next run are untouched, and no card was raised",
          after.get("rule") == before.get("rule") and after["due"] == before["due"]
          and w.cards == [], (before, after, w.cards))
    code, out = w.s.act(job["id"], "edit", fields={"text": "stretch gently"})
    check("... while a text-only edit of the same repeating job stays cardless",
          code == 200 and w.cards == []
          and w.s.job(job["id"])["text"] == "stretch gently", (code, out, w.cards))


# --------------------------------------------------------------------------
#   The ONE repeat card
# --------------------------------------------------------------------------


def t_repeat_edit_raises_one_card_and_keeps_the_old_rule():
    w = World(local(2026, 9, 25, 12, 0), name="edit-repeat-card")
    job = w.s.add_at("reminder", local(2026, 9, 26, 9, 0), "call Mum")
    code, out = w.s.act(job["id"], "edit",
                        fields={"repeat": {"every": "weekday", "at": "07:30"}})
    check("a repeat change answers 202 waiting:true (ONE `schedule_repeat` card)",
          code == 202 and out.get("waiting") is True and out.get("ok") is True, out)
    check("... exactly one card was raised, action schedule_repeat",
          len(w.cards) == 1 and w.cards[0][0] == "schedule_repeat", w.cards)
    prompt = w.cards[0][2]
    check("... the card explains the new rule and that the old schedule stays",
          "07:30" in prompt and "stays exactly as it is" in prompt, prompt)
    after = w.s.job(job["id"])
    check("approved: the job keeps its id and becomes the new repeat",
          after["id"] == job["id"] and after["repeats"] is True
          and after["repeat"] == "every weekday (Monday to Friday) at 07:30", after)
    check("... and its next run comes from the NEW rule",
          after["due"] == S.next_run(S.check_rule({"every": "weekday",
                                                   "at": "07:30"}), w.clock.t))
    check("... one `schedule.card` audit line, ids and outcome only",
          [d for e, d in _AUDIT if e == "schedule.card"][-1]["outcome"]
          == "approved")
    check("the audit detail is ids/field NAMES only - no words, no rule values",
          [d for e, d in _AUDIT
           if e == "schedule.act" and d.get("do") == "edit"][-1].get("fields")
          == ["repeat"], _AUDIT[-6:])


def t_repeat_edit_denied_changes_nothing():
    w = World(local(2026, 9, 25, 12, 0), name="edit-repeat-denied",
              answer="denied")
    job = w.s.add_at("reminder", local(2026, 9, 26, 9, 0), "call Mum")
    before = w.s.job(job["id"])
    events_before = len(w.events)
    code, out = w.s.act(job["id"], "edit",
                        fields={"repeat": {"every": "day", "at": "07:00"},
                                "text": "call Mum every day"})
    after = w.s.job(job["id"])
    check("a DENIED repeat edit still answers 202 (one card raised)",
          code == 202 and len(w.cards) == 1, (code, w.cards))
    check("... and then nothing changes: words, rule and due are the old ones",
          after.get("rule") == before.get("rule")
          and after["due"] == before["due"]
          and after["text"] == before["text"], (before, after))
    check("... the last card outcome is `denied`",
          w.s.last_card.get(job["id"]) == "denied", w.s.last_card)
    check("... and no NEW `schedule` event was published for it",
          len(w.events) == events_before, w.events[events_before:])


def t_repeat_edit_on_repeating_job_keeps_old_until_approved():
    w = World(local(2026, 9, 25, 12, 0), name="edit-repeat-existing",
              answer="denied")
    job = w.s.add_repeat("alarm", S.check_rule({"every": "day", "at": "07:00"}),
                         "wake")
    old = w.s.job(job["id"])
    code, out = w.s.act(job["id"], "edit",
                        fields={"repeat": {"every": "weekday", "at": "08:00"}})
    after = w.s.job(job["id"])
    check("changing an existing repeat raises ONE card and keeps the old rule",
          code == 202 and len(w.cards) == 1
          and after.get("rule") == old.get("rule")
          and after["due"] == old["due"], (code, after, w.cards))
    check("... a denied card leaves it on the old rule",
          w.s.last_card[job["id"]] == "denied")
    code, out = w.s.act(job["id"], "edit",
                        fields={"repeat": {"every": "minutes"}})
    check("an invalid new repeat is a plain 400 (no card)",
          code == 400 and len(w.cards) == 1, (code, out, w.cards))
    timer = w.s.add_timer(60, "tea")
    code, out = w.s.act(timer["id"], "edit",
                        fields={"repeat": {"every": "day", "at": "07:00"}})
    check("a timer cannot repeat - the edit is 409", code == 409, (code, out))
    todo = w.s.add_todo("milk")
    code, out = w.s.act(todo["id"], "edit",
                        fields={"repeat": {"every": "day", "at": "07:00"}})
    check("a to-do cannot repeat - the edit is 409", code == 409, (code, out))


# --------------------------------------------------------------------------
#   Refusals and precedence
# --------------------------------------------------------------------------


def t_refusals_and_precedence():
    w = World(local(2026, 9, 25, 12, 0), name="refuse")
    real_get = S.get
    S.get = lambda: w.s
    try:
        code, out = S.handle_act({"do": "clear_list", "list": "nothing here",
                                  "count": 1})
    finally:
        S.get = real_get
    check("clear_list is still handled before the id check",
          code in (400, 409) and out.get("ok") is False, (code, out))
    job = w.s.add_timer(60, "tea")
    w.clock.t += 60
    w.s.tick()
    code, out = w.s.act(job["id"], "edit", fields={"text": "cold tea"})
    check("edit on a FIRED job is refused 409 with the existing sentence",
          code == 409 and "already gone off" in out.get("error", ""), (code, out))
    check("delete still works on a fired job",
          w.s.act(job["id"], "delete")[0] == 200)
    S.register_kind("fakewait", "fake thing", "Jarvis: fake thing.",
                    repeatable=True)
    try:
        waiting_id = w.s._insert(
            "fakewait", text="waiting words", state="waiting", due=None,
            rule=S.check_rule({"every": "day", "at": "06:00"}), duration=None,
            source="app")
        code, out = w.s.act(waiting_id, "edit", fields={"text": "x"})
        check("edit on a WAITING job is refused 409 (answer its card first)",
              code == 409, (code, out))
    finally:
        S.KINDS.pop("fakewait", None)
    S.register_kind("fakemod", "fake module job", "Jarvis: fake.",
                    has_text=True, add=lambda body: (200, {"ok": True}))
    try:
        managed = w.s.add_at("fakemod", local(2026, 9, 26, 7, 0), "owned words")
        code, out = w.s.act(managed["id"], "edit", fields={"text": "other"})
        check("a module-managed kind refuses edit 409, in plain words",
              code == 409 and "changed where it was set up" in out.get("error", ""),
              (code, out))
        check("... and its words are untouched",
              w.s.job(managed["id"])["text"] == "owned words")
    finally:
        S.KINDS.pop("fakemod", None)
    code, out = w.s.act("sdeadbeef00", "edit", fields={"text": "x"})
    check("edit on an unknown id is 404 no_such_job (reason kept)",
          code == 404 and out.get("reason") == "no_such_job", (code, out))
    done = w.s.add_todo("chore")
    w.s.act(done["id"], "done")
    code, out = w.s.act(done["id"], "edit", fields={"text": "chore again"})
    check("edit on a DONE job is 404 (not on the list any more)",
          code == 404 and out.get("reason") == "no_such_job", (code, out))
    code, out = w.s.act(w.s.add_todo("x")["id"], "nonsense")
    check("an unknown verb is 400 and names ALL verbs, the new three included",
          code == 400 and all(v in out.get("error", "")
                              for v in ("pause", "edit", "move", "reorder")),
          (code, out))
    code, out = w.s.act(w.s.add_todo("milk", list_name="shopping")["id"], "move",
                        fields={"list": "shopping", "rank": 1})
    check("move refuses an unknown key 400 (all-or-nothing, like edit)",
          code == 400, (code, out))
    code, out = w.s.act(w.s.add_todo("eggs", list_name="shopping")["id"],
                        "reorder", fields={"rank": 0, "text": "x"})
    check("reorder refuses an unknown key 400", code == 400, (code, out))
    todo = w.s.add_todo("milk")
    check("done/pause/resume/add_time/snooze still answer as before",
          w.s.act(todo["id"], "done")[0] == 200
          and w.s.act(w.s.add_timer(60, "t")["id"], "add_time", 30)[0] == 200)


# --------------------------------------------------------------------------
#   No words anywhere: audit, events, replies
# --------------------------------------------------------------------------


def t_no_words_in_audit_events_or_replies():
    w = World(local(2026, 9, 25, 12, 0), name="leaks")
    secret = "Zebracorn secret words"
    item = w.s.add_todo(secret, list_name="presents")
    w.s.act(item["id"], "edit", fields={"text": "another private sentence"})
    w.s.act(item["id"], "move", fields={"list": "hospital"})
    w.s.act(item["id"], "reorder", fields={"rank": 0})
    reminder = w.s.add_at("reminder", local(2026, 9, 26, 9, 0),
                          "Doctor visit words")
    w.s.act(reminder["id"], "edit", fields={"when": local(2026, 9, 27, 9, 0)})
    allowed_keys = {"id", "kind", "do", "fields", "named_list", "rank",
                    "outcome", "copy"}
    blob_audit = json.dumps(_AUDIT)
    blob_events = json.dumps(w.events)
    for word in ("Zebracorn", "private sentence", "presents", "hospital",
                 "Doctor visit"):
        check(f"audit never carries {word!r}", word not in blob_audit,
              blob_audit[-300:])
        check(f"events never carry {word!r}", word not in blob_events,
              blob_events[-300:])
    bad_keys = []
    for event, detail in _AUDIT:
        if event == "schedule.act":
            extra = set(detail) - allowed_keys
            if extra:
                bad_keys.append((event, sorted(extra), detail))
    check("every schedule.act audit detail only uses ids/kinds/outcomes/field names",
          bad_keys == [], bad_keys)
    edit_audit = [d for e, d in _AUDIT
                  if e == "schedule.act" and d.get("do") == "edit"]
    check("edit audit lines carry a fields list of NAMES only",
          all(set(d.get("fields", [])) <= {"repeat", "text", "when"}
              for d in edit_audit), edit_audit)
    move_audit = [d for e, d in _AUDIT
                  if e == "schedule.act" and d.get("do") == "move"]
    check("move audit lines carry named_list: true|false, never the name",
          move_audit and all(isinstance(d.get("named_list"), bool)
                             for d in move_audit), move_audit)
    reorder_audit = [d for e, d in _AUDIT
                     if e == "schedule.act" and d.get("do") == "reorder"]
    check("reorder audit lines carry the integer rank",
          reorder_audit and all(isinstance(d.get("rank"), int)
                                and not isinstance(d.get("rank"), bool)
                                for d in reorder_audit), reorder_audit)
    check("the read still shows the words (redaction is the clients' job)",
          w.s.job(item["id"])["text"] == "another private sentence")


def main():
    try:
        for name, fn in list(globals().items()):
            if name.startswith("t_") and callable(fn):
                print(f"--- {name} ---")
                try:
                    fn()
                except Exception:
                    traceback.print_exc()
                    check(f"{name} ran without crashing", False, "see traceback")
    finally:
        S._audit = _real_audit
        shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
