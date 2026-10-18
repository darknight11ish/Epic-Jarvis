"""test_schedule.py - the one scheduler, and timers answered without the model.

    python3 backend/test_schedule.py

The owner's decisions of 2026-09-25 (CLAUDE.md; docs/JARVIS-API.md section
21): timers, reminders and ONE shared scheduler first; a timer or a one-time
reminder needs no card, anything that repeats asks once with a card listing
the next run times; simple commands are answered without the AI model.

What it proves, with a clock the test moves by hand and real SQLite files in
a temporary folder:
  - next-run times: daily, weekdays, weekly on days, every N hours (with its
    minimum), across both daylight-saving changes in London and New York -
    07:00 stays 07:00, a time in the missing hour goes off when the clocks
    jump, a time that happens twice goes off once, the first time;
  - a restart keeps every job, and a running timer keeps its end time;
  - a job missed while the PC was off goes off ONCE, late, "missed at
    07:00" - never once per missed time;
  - one card for a repeating job, action schedule_repeat, tier "ask" only,
    listing the next three times in plain words; nothing for a one-off;
    denied, timed out or refused removes it; deleted while waiting sets
    nothing up;
  - the `schedule` event and the audit log carry ids and kinds, never the
    words;
  - one job per change: pause, resume, add time, delete, done - no list
    form, no "delete all"; a job that has GONE OFF can be deleted (DEF-008,
    the owner's decision of 2026-10-13), which is the one verb that accepts
    a 'fired' job, while pausing one still refuses;
  - the fast path: many phrasings, and near-misses that must go to the model;
    only the owner's own typed or said words act;
  - the model is never called on a match: every socket and the model's own
    turn are made to fail, and the answer still arrives - through the real
    patched /api/chat block from the whole patch stack;
  - the learner skips a command; the model's tools act without the gate for
    a one-off and through the scheduler's card for a repeat, and do nothing
    after outside text;
  - schedule.patch applies to what the earlier patches wrote, and reverses.

Every check fails on the code before this change: jarvis_schedule.py,
jarvis_quick.py and schedule.patch did not exist. No pytest, no network, no
model.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

require_shipped("jarvis_schedule.py", "jarvis_quick.py", "jarvis_intake.py", "jarvis_agent.py")

for p in (HERE / "rebuilt",):
    if str(p) not in sys.path:
        sys.path.append(str(p))

import jarvis_schedule as S  # noqa: E402
import jarvis_quick as Q  # noqa: E402
import _stack  # noqa: E402

PASSED, FAILED = [], []
SKIPPED = []
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-schedule-"))


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: printed as `skip`, counted on its own,
    never as a pass. (It used to be check("SKIP - ...", True) - a condition of
    the constant True, so it printed as a pass and was counted as one.)"""
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
    """A scheduler with a hand-moved clock, a gate that records, and the bus
    and the audit log captured."""

    def __init__(self, t, *, answer="approved", tier="ask", name=None):
        self.clock = Clock(t)
        self.events, self.cards, self.audit = [], [], []
        self.answer, self.tier = answer, tier
        path = _TMP / f"{name or 'w'}-{len(os.listdir(_TMP))}.db"
        self.s = S.Scheduler(path, clock=self.clock, gate=self.gate, tier_of=lambda a: self.tier,
                             spawn=lambda fn: fn(), publish=lambda k, d: self.events.append((k, d)))

    def gate(self, action, detail, prompt):
        self.cards.append((action, detail, prompt))
        if self.answer == "approved":
            return Verdict(True, "ask", "approved")
        return Verdict(False, "ask", self.answer)


_real_audit = S._audit
_AUDIT = []
S._audit = lambda event, detail: _AUDIT.append((event, detail))


def use_tz(name):
    """Set this process's time zone. Linux and macOS only (time.tzset)."""
    if not hasattr(time, "tzset"):
        return False
    os.environ["TZ"] = name
    time.tzset()
    return True


def local(y, mo, d, hh, mm):
    return S.wall_to_epoch(y, mo, d, hh, mm)


def wall(t):
    lt = time.localtime(t)
    return (lt.tm_year, lt.tm_mon, lt.tm_mday, lt.tm_hour, lt.tm_min)

# --------------------------------------------------------------------------
#   Next-run times and daylight saving
# --------------------------------------------------------------------------


def t_next_run_in_london_across_both_clock_changes():
    if not use_tz("Europe/London"):
        return skip("no time.tzset here (Windows); the rules are the same")
    rule = S.check_rule({"every": "day", "at": "07:00"})
    # Clocks go forward at 01:00 on Sunday 29 March 2026.
    sat = local(2026, 3, 28, 7, 0)
    sun = S.next_run(rule, sat)
    check("London, spring: a daily 07:00 is 07:00 on the Sunday the clocks go forward",
          wall(sun) == (2026, 3, 29, 7, 0), wall(sun))
    check("... which is 23 hours after the Saturday's, not 24", sun - sat == 23 * 3600,
          (sun - sat) / 3600)
    # Clocks go back at 02:00 on Sunday 25 October 2026.
    sat = local(2026, 10, 24, 7, 0)
    sun = S.next_run(rule, sat)
    check("London, autumn: a daily 07:00 is 07:00 on the Sunday the clocks go back",
          wall(sun) == (2026, 10, 25, 7, 0) and sun - sat == 25 * 3600, (wall(sun), sun - sat))
    gap = local(2026, 3, 29, 1, 30)
    check("a time in the missing hour (01:30 on 29 March) goes off when the clocks jump, 02:00",
          wall(gap) == (2026, 3, 29, 2, 0), wall(gap))
    twice = local(2026, 10, 25, 1, 30)
    check("a time that happens twice (01:30 on 25 October) is the FIRST one (still summer time)",
          wall(twice) == (2026, 10, 25, 1, 30) and time.localtime(twice).tm_isdst == 1,
          (wall(twice), time.localtime(twice).tm_isdst))
    rule = S.check_rule({"every": "day", "at": "01:30"})
    a = S.next_run(rule, local(2026, 10, 24, 12, 0))
    b = S.next_run(rule, a)
    check("... and a daily 01:30 goes off once that night, not twice",
          wall(b) == (2026, 10, 26, 1, 30), wall(b))


def t_next_run_in_new_york():
    if not use_tz("America/New_York"):
        return skip("no time.tzset here")
    rule = S.check_rule({"every": "weekday", "at": "07:30"})
    fri = local(2026, 3, 6, 7, 30)          # Friday; clocks go forward Sun 8 March
    mon = S.next_run(rule, fri)
    check("New York: every weekday skips the weekend and stays 07:30 across the change",
          wall(mon) == (2026, 3, 9, 7, 30), wall(mon))
    rule = S.check_rule({"every": "week", "at": "09:00", "days": [6]})
    sun = S.next_run(rule, local(2026, 10, 31, 12, 0))   # clocks go back Sun 1 Nov
    check("New York: every Sunday 09:00 on the day the clocks go back",
          wall(sun) == (2026, 11, 1, 9, 0), wall(sun))


def t_repeating_rules():
    use_tz("Europe/London")
    now = local(2026, 9, 25, 12, 0)            # a Friday
    r = S.check_rule({"every": "week", "at": "9:05", "days": [0, 3]})
    runs = S.next_runs(r, now)
    check("every Monday and Thursday at 09:05: the next three",
          [wall(t) for t in runs] == [(2026, 9, 28, 9, 5), (2026, 10, 1, 9, 5), (2026, 10, 5, 9, 5)],
          [wall(t) for t in runs])
    r = S.check_rule({"every": "hours", "hours": 2, "start": now})
    check("every 2 hours from a start time", S.next_runs(r, now) == [now + 7200, now + 14400,
                                                                     now + 21600])
    for bad, why in (({"every": "hours", "hours": 0}, "minimum"),
                     ({"every": "minutes", "at": "07:00"}, "unknown"),
                     ({"every": "day", "at": "25:00"}, "not a time"),
                     ({"every": "week", "at": "07:00", "days": []}, "no days"),
                     ({"every": "week", "at": "07:00", "days": [7]}, "day 7"),
                     ({"every": "hours", "hours": True}, "a boolean")):
        try:
            S.check_rule(bad)
            ok = False
        except ValueError:
            ok = True
        check(f"a bad repeat is refused with a reason ({why})", ok)
    check("the shortest repeat is one hour", S.MIN_EVERY_HOURS == 1)
    check("plain words for each rule",
          S.rule_words({"every": "weekday", "at": "07:00"}) ==
          "every weekday (Monday to Friday) at 07:00"
          and S.rule_words({"every": "week", "at": "09:00", "days": [0, 3]}) ==
          "every Monday and Thursday at 09:00"
          and S.rule_words({"every": "hours", "hours": 1}) == "every hour")

# --------------------------------------------------------------------------
#   The loop: going off, restarts, missed, no burst
# --------------------------------------------------------------------------


def t_a_timer_goes_off_once_and_the_event_has_no_words():
    use_tz("Europe/London")
    w = World(local(2026, 9, 25, 12, 0))
    j = w.s.add_timer(600, "pasta")
    check("a timer needs no card", w.cards == [])
    check("the timer is listed with its time left", w.s.timers()[0]["left"] == 600)
    w.clock.t += 599
    check("nothing goes off a second early", w.s.tick() == [])
    w.clock.t += 1
    check("it goes off on time", w.s.tick() == [j["id"]])
    check("... once", w.s.tick() == [] and w.s.tick(w.clock.t + 3600) == [])
    fired = [d for k, d in w.events if d.get("state") == "fired"]
    check("the event is kind `schedule`, with the id, the kind and late=false",
          fired == [{"id": j["id"], "kind": "timer", "state": "fired", "late": False}], fired)
    blob = json.dumps(w.events)
    check("no event carries the words", "pasta" not in blob)
    check("every event has only id, kind, state (and late)",
          all(set(d) <= {"id", "kind", "state", "late"} and k == "schedule" for k, d in w.events))
    v = w.s.job(j["id"])
    check("after it went off it is still readable by id, words and all",
          v is not None and v["state"] == "fired" and v["text"] == "pasta")
    check("... and no longer on the list", w.s.timers() == [])
    check("... and gone a day later", (w.s.tick(w.clock.t + S.FIRED_KEEP + 5), w.s.job(j["id"]))[1]
          is None)
    check("the audit log has ids and kinds, never the words",
          _AUDIT and "pasta" not in json.dumps(_AUDIT))


def t_a_restart_keeps_everything():
    use_tz("Europe/London")
    w = World(local(2026, 9, 25, 12, 0), name="restart")
    t = w.s.add_timer(900)
    r = w.s.add_at("reminder", local(2026, 9, 26, 9, 0), "call Mum")
    d = w.s.add_todo("buy milk")
    again = S.Scheduler(w.s.path, clock=w.clock, gate=w.gate, tier_of=lambda a: "ask",
                        spawn=lambda fn: fn(), publish=lambda k, d: None)
    ids = {j["id"] for j in again.listed()} | {j["id"] for j in again.todos()}
    check("a new scheduler on the same file lists every job", ids == {t["id"], r["id"], d["id"]})
    check("the timer's end time survives the restart",
          again.job(t["id"])["due"] == t["due"])
    check("the reminder's words survive", again.job(r["id"])["text"] == "call Mum")


def t_missed_while_off_goes_off_once_late():
    use_tz("Europe/London")
    w = World(local(2026, 9, 25, 6, 0), name="missed")
    w.s.add_repeat("alarm", {"every": "day", "at": "07:00"})
    rem = w.s.add_at("reminder", local(2026, 9, 25, 8, 0), "take the bins out")
    # The PC is off for five days.
    w.clock.t = local(2026, 9, 30, 12, 0)
    went = w.s.tick()
    check("after five days off, the daily alarm and the reminder each go off ONCE",
          len(went) == 2 and len(set(went)) == 2, went)
    fired = [d for k, d in w.events if d.get("state") == "fired"]
    check("... both marked late", all(d["late"] is True for d in fired), fired)
    alarm = [j for j in w.s.listed() if j["kind"] == "alarm"][0]
    check("the alarm says when it was missed: \"missed at 07:00\"",
          alarm.get("missed") == "missed at 07:00", alarm)
    check("... and its next time is tomorrow 07:00, not one of the missed ones",
          wall(alarm["due"]) == (2026, 10, 1, 7, 0), wall(alarm["due"]))
    check("the one-off reminder says it was missed at 08:00",
          w.s.job(rem["id"]).get("missed") == "missed at 08:00")
    check("a second look goes off nothing (never a burst)", w.s.tick() == [])
    w.clock.t = local(2026, 10, 1, 7, 0)
    check("the next morning it goes off on time, not late",
          len(w.s.tick()) == 1 and [d for k, d in w.events if d.get("state") == "fired"][-1]["late"]
          is False)


def t_one_job_at_a_time():
    use_tz("Europe/London")
    w = World(local(2026, 9, 25, 12, 0), name="act")
    t = w.s.add_timer(600)
    w.clock.t += 100
    code, out = w.s.act(t["id"], "pause")
    check("pause", code == 200 and w.s.job(t["id"])["state"] == "paused")
    w.clock.t += 1000
    check("a paused timer keeps its time left", abs(w.s.job(t["id"])["left"] - 500) < 0.01)
    check("... and does not go off", w.s.tick() == [])
    code, _ = w.s.act(t["id"], "resume")
    check("resume: it ends 500 seconds from now",
          code == 200 and abs(w.s.job(t["id"])["due"] - (w.clock.t + 500)) < 0.01)
    code, out = w.s.act(t["id"], "add_time", 60)
    check("add a minute", code == 200 and abs(w.s.job(t["id"])["left"] - 560) < 0.01, out)
    check("time cannot be taken below nothing",
          w.s.act(t["id"], "add_time", -10000)[0] == 409)
    code, _ = w.s.act(t["id"], "delete")
    check("delete is immediate", code == 200 and w.s.job(t["id"]) is None)
    check("a second delete says it is gone", w.s.act(t["id"], "delete")[0] == 404)
    # DEF-008, closed on the owner's decision of 2026-10-13: a job that has
    # gone off is SHOWN under "Just went off" for an hour, so it must be one
    # the apps can clear. `delete` is the one verb routed before act()'s own
    # list gate, exactly as `snooze` is; pausing one still refuses.
    f = w.s.add_at("reminder", w.clock.t + 60, "call the bank")
    w.clock.t += 60
    w.s.tick()
    check("a job that has gone off can be deleted (DEF-008)",
          w.s.job(f["id"]) is not None and w.s.job(f["id"])["state"] == "fired"
          and w.s.act(f["id"], "delete")[0] == 200 and w.s.job(f["id"]) is None)
    g = w.s.add_at("reminder", w.clock.t + 60, "call Dad")
    w.clock.t += 60
    w.s.tick()
    check("... while pausing one that has gone off still refuses, with a true sentence",
          w.s.act(g["id"], "pause")[0] == 409
          and w.s.act(g["id"], "pause")[1]["error"] == "It has already gone off.")
    d = w.s.add_todo("buy milk")
    check("the same to-do twice is one item", w.s.add_todo("Buy milk").get("already") is True
          and len(w.s.todos()) == 1)
    check("done on a to-do", w.s.act(d["id"], "done")[0] == 200 and w.s.todos() == [])
    check("done is only for a to-do", w.s.act(w.s.add_timer(60)["id"], "done")[0] == 409)
    S._SCHED = w.s
    try:
        for body in ({"id": ["s0123456789", "s0123456780"], "do": "delete"},
                     {"ids": ["s0123456789"], "do": "delete"}, {"id": "*", "do": "delete"},
                     {"id": "all", "do": "delete"}):
            check(f"no list form and no wildcard: {json.dumps(body)} is refused",
                  S.handle_act(body)[0] == 400)
    finally:
        S._SCHED = None
    src = (HERE / "jarvis_schedule.py").read_text(encoding="utf-8")
    code_only = re.sub(r'"""[\s\S]*?"""|#[^\n]*', "", src)
    check("there is no delete-all, clear or done-all in the scheduler's code",
          not re.search(r"DELETE FROM jobs(?! WHERE (?:id|state))", code_only)
          and "delete_all" not in code_only and "clear_all" not in code_only)


def t_limits_say_why():
    use_tz("Europe/London")
    w = World(local(2026, 9, 25, 12, 0), name="limits")
    for fn, why in ((lambda: w.s.add_timer(0), "no length"),
                    (lambda: w.s.add_timer(S.MAX_TIMER + 1), "over a day"),
                    (lambda: w.s.add_at("reminder", w.clock.t - 1, "x"), "in the past"),
                    (lambda: w.s.add_at("reminder", w.clock.t + 60, ""), "no words"),
                    (lambda: w.s.add_todo("x" * (S.MAX_TEXT + 1)), "too long"),
                    (lambda: w.s.add_repeat("timer", {"every": "day", "at": "07:00"}),
                     "a timer does not repeat")):
        try:
            fn()
            ok = False
        except (ValueError, OverflowError) as exc:
            ok = bool(str(exc))
        check(f"refused with a sentence: {why}", ok)

# --------------------------------------------------------------------------
#   The card for anything that repeats
# --------------------------------------------------------------------------


#: A kind that repeats through the ONE card, like the morning briefing and
#: "tell me when" (both registered by their own modules): the card path is
#: tested on it, since plain alarms and reminders no longer have a card.
S.register_kind("asktest", "test repeat", "Jarvis: a test repeat.", has_text=True,
                repeatable=True)


def t_no_card_for_a_plain_repeat():
    """The owner's decision of 2026-09-26 (the approvals audit): plain
    repeating alarms and reminders need no card. Set up at once, due at the
    first time; the answer says the next three times, as the card did."""
    use_tz("Europe/London")
    now = local(2026, 9, 25, 12, 0)            # Friday
    w = World(now, name="plain")
    w.s.add_timer(60)
    w.s.add_at("alarm", now + 3600)
    w.s.add_at("reminder", now + 7200, "call the bank")
    w.s.add_todo("milk")
    check("a timer, a one-off alarm, a one-off reminder and a to-do raise no card", w.cards == [])
    j = w.s.add_repeat("reminder", {"every": "weekday", "at": "07:00"}, "take my pills")
    check("a repeating reminder raises NO card (2026-09-26)", w.cards == [], w.cards)
    v = w.s.job(j["id"])
    check("... it is on the list at once, due Monday 07:00",
          v["state"] == "active" and wall(v["due"]) == (2026, 9, 28, 7, 0), v)
    said = S.repeat_set_words(v, now)
    check("... and the answer names it, its rule and its next three times",
          said == "Reminder set up, every weekday (Monday to Friday) at 07:00. Next: 07:00 on "
                  "Monday, 07:00 on Tuesday and 07:00 on Wednesday. Delete it under Coming up "
                  "to stop it.", said)
    check("... and Coming up lists its next three times", len(v["next"]) == 3 and
          [wall(t) for t in v["next"]] == [(2026, 9, 28, 7, 0), (2026, 9, 29, 7, 0),
                                           (2026, 9, 30, 7, 0)], v)
    for tier in ("auto", "never", "unreadable"):
        wt = World(now, tier=tier, name=f"plain-{tier}")
        jt = wt.s.add_repeat("alarm", {"every": "day", "at": "06:30"})
        check(f"schedule_repeat's tier ({tier}) does not touch a plain repeat",
              wt.cards == [] and wt.s.job(jt["id"])["state"] == "active")
    check("a plain repeat still goes off at its time, and again the next day",
          j["id"] in [x if isinstance(x, str) else x.get("id")
                      for x in w.s.tick(local(2026, 9, 28, 7, 0) + 1)]
          and wall(w.s.job(j["id"])["due"]) == (2026, 9, 29, 7, 0))
    check("... and deleting it is immediate", w.s.act(j["id"], "delete")[0] == 200
          and w.s.job(j["id"]) is None)
    code, out = None, None
    keep = S._SCHED
    S._SCHED = World(now, name="route").s
    try:
        code, out = S.handle_add({"kind": "alarm", "repeat": {"every": "day", "at": "06:30"},
                                  "text": "wake up"})
    finally:
        S._SCHED = keep
    check("POST /api/schedule/add, a repeating alarm: 200, set up, with its next times in `said`",
          code == 200 and out["waiting"] is False and out["job"]["state"] == "active"
          and out["said"].startswith("Alarm set up, every day at 06:30. Next: 06:30 tomorrow"),
          (code, out))


def t_one_card_for_a_repeat_that_reads():
    """The kinds that keep their card (the briefing, "tell me when"): ONE
    card, schedule_repeat, listing the next three times."""
    use_tz("Europe/London")
    now = local(2026, 9, 25, 12, 0)            # Friday
    w = World(now, name="card")
    j = w.s.add_repeat("asktest", {"every": "weekday", "at": "07:00"}, "take my pills")
    check("a repeat of a kind that asks raises ONE card", len(w.cards) == 1)
    action, detail, prompt = w.cards[0]
    check("... action schedule_repeat", action == "schedule_repeat" == S.ACTION)
    check("... which lists the next three times in plain words",
          all(s in prompt for s in ("Monday 28 September at 07:00",
                                    "Tuesday 29 September at 07:00",
                                    "Wednesday 30 September at 07:00")), prompt)
    check("... says what, when, that nothing leaves the PC and what no means",
          "What: take my pills" in prompt and "every weekday (Monday to Friday) at 07:00" in prompt
          and "Nothing is sent anywhere" in prompt and "If you say no: nothing is set up." in prompt)
    check("... and leaves_this_pc is false", detail.get("leaves_this_pc") is False)
    check("approved: it is set up, due Monday 07:00",
          w.s.job(j["id"])["state"] == "active" and wall(w.s.job(j["id"])["due"]) ==
          (2026, 9, 28, 7, 0))
    for answer in ("denied", "timed_out"):
        w2 = World(now, answer=answer, name=answer)
        j2 = w2.s.add_repeat("asktest", {"every": "day", "at": "06:30"}, "x")
        check(f"{answer}: nothing is set up, and it is off the list",
              w2.s.job(j2["id"]) is None and w2.s.listed() == [])
    w3 = World(now, tier="auto", name="auto")
    j3 = w3.s.add_repeat("asktest", {"every": "day", "at": "06:30"}, "x")
    check("tier \"auto\" in the settings is refused without asking - a config line is not a yes",
          w3.cards == [] and w3.s.job(j3["id"]) is None)

    class Late(World):
        def gate(self, action, detail, prompt):
            # The owner deletes it while the card is up, then approves.
            self.s.act(detail["job"], "delete")
            return Verdict(True, "ask", "approved")
    w4 = Late(now, name="late")
    j4 = w4.s.add_repeat("asktest", {"every": "day", "at": "06:30"}, "x")
    check("deleted while the card waited: approving it sets nothing up",
          w4.s.job(j4["id"]) is None and w4.s.last_card.get(j4["id"]) == "withdrawn")

    class Liar(World):
        def gate(self, action, detail, prompt):
            return Verdict(True, "auto", "approved")
    w5 = Liar(now, name="liar")
    j5 = w5.s.add_repeat("asktest", {"every": "day", "at": "06:30"}, "x")
    check("allowed at tier \"auto\" is not a person saying yes: refused",
          w5.s.job(j5["id"]) is None)
    w6 = World(now, answer="denied", name="waiting")
    w6.answer = "approved"
    w6.s._spawn = lambda fn: None          # the card is still up
    j6 = w6.s.add_repeat("asktest", {"every": "day", "at": "08:00"}, "stretch")
    v6 = w6.s.job(j6["id"])
    check("while the card waits it is listed as waiting, with its next three times, and "
          "nothing goes off", v6["state"] == "waiting" and len(v6["next"]) == 3
          and w6.s.tick(now + 30 * 86400) == [])
    check("a kind added later asks by default (plain_repeat is off unless said)",
          S.KINDS["asktest"].plain_repeat is False and S.KINDS["alarm"].plain_repeat
          and S.KINDS["reminder"].plain_repeat)

# --------------------------------------------------------------------------
#   The fast path: the grammar
# --------------------------------------------------------------------------

OURS = {
    "set a timer for 10 minutes": ("timer_set", {"seconds": 600}),
    "10 minute timer": ("timer_set", {"seconds": 600}),
    "timer for 1h30": ("timer_set", {"seconds": 5400}),
    "Timer for 1h 30m.": ("timer_set", {"seconds": 5400}),
    "Jarvis, set a pasta timer for 12 minutes please": ("timer_set", {"seconds": 720,
                                                                       "label": "pasta"}),
    "set a 10 minute timer for the eggs": ("timer_set", {"seconds": 600, "label": "eggs"}),
    "set a timer for an hour and a half": ("timer_set", {"seconds": 5400}),
    "set a timer for half an hour": ("timer_set", {"seconds": 1800}),
    "start a twenty five minute timer": ("timer_set", {"seconds": 1500}),
    "timer 45 seconds": ("timer_set", {"seconds": 45}),
    "can you set a timer for 2 minutes and 30 seconds": ("timer_set", {"seconds": 150}),
    "cancel the timer": ("timer_cancel", {}),
    "stop the 10 minute timer": ("timer_cancel", {"length": 600}),
    "cancel the pasta timer": ("timer_cancel", {"label": "pasta"}),
    "pause the timer": ("timer_pause", {}),
    "resume my timer": ("timer_resume", {}),
    "add 5 minutes to the timer": ("timer_add", {"seconds": 300}),
    "5 more minutes": ("timer_add", {"seconds": 300, "bare": True}),
    "add another 2 minutes": ("timer_add", {"seconds": 120, "bare": True}),
    "take 2 minutes off the timer": ("timer_add", {"seconds": -120}),
    "how long is left": ("timer_status", {"bare": True}),
    "how much time is left on the timer": ("timer_status", {}),
    "how long left on the pasta timer": ("timer_status", {"label": "pasta"}),
    "set an alarm for 7": ("alarm_set", {}),
    "alarm at 7:30am": ("alarm_set", {}),
    "wake me up at 6": ("alarm_set", {}),
    "set an alarm for tomorrow at 6": ("alarm_set", {}),
    "set an alarm for half past seven": ("alarm_set", {}),
    "7am alarm": ("alarm_set", {}),
    "cancel my 7am alarm": ("alarm_cancel", {}),
    "what alarms do I have": ("alarm_list", {}),
    "remind me to call Mum at 6": ("reminder_set", {"text": "call Mum"}),
    "remind me in 20 minutes to check the oven": ("reminder_set", {"text": "check the oven"}),
    "remind me tomorrow to call the bank": ("reminder_set", {"text": "call the bank"}),
    "Remind me to call Mum tomorrow at 6pm.": ("reminder_set", {"text": "call Mum"}),
    "remind me to do the laundry at 5": ("reminder_set", {"text": "do the laundry"}),
    "remind me at noon to eat": ("reminder_set", {"text": "eat"}),
    "set a reminder for 5pm to leave": ("reminder_set", {"text": "leave"}),
    "remind me on Friday at 5pm to pay rent": ("reminder_set", {"text": "pay rent"}),
    "remind me every weekday at 7 to take my pills": ("reminder_set", {"text": "take my pills"}),
    "remind me to stretch every 2 hours": ("reminder_set", {"text": "stretch"}),
    "remind me every Monday and Thursday at 9 to water the plants": ("reminder_set", {}),
    "add milk to my to-do list": ("todo_add", {"text": "milk"}),
    "put Call the dentist on my todo list": ("todo_add", {"text": "Call the dentist"}),
    "what's on my to do list": ("todo_list", {}),
    "read my to-do list": ("todo_list", {}),
    "mark milk as done": ("todo_done", {"text": "milk"}),
    "tick off milk": ("todo_done", {"text": "milk"}),
    "remove milk from my todo list": ("todo_remove", {"text": "milk"}),
    "cancel all timers": ("bulk", {}),
    "clear my to-do list": ("bulk", {}),
    "delete all my reminders": ("bulk", {}),
}

NOT_OURS = [
    "how long does it take to boil an egg", "what's a good timer app",
    "should i set a timer for 10 minutes", "how do I set a timer",
    "remind me what we talked about", "remind me who wrote Dune", "remind me about the meeting",
    "can you remind me later", "set an alarm system up at home",
    "tell me about the history of alarms", "add salt to the pasta recipe",
    "what time is it in Tokyo", "timer", "set a timer", "set an alarm", "remind me",
    "check the oven", "wake me up when september ends", "how long is the flight to Paris",
    "I have to do my taxes", "what should I add to my list", "the timer on my oven is broken",
    "my alarm didn't go off this morning", "what's the best way to remember things",
    "remind me to", "stop", "cancel", "add it to my to-do list",
    "set a timer for 10 minutes and then tell me a joke",
    "Stelle einen Timer für 10 Minuten", "pon un temporizador de 10 minutos",
]


def t_the_grammar_knows_these():
    use_tz("Europe/London")
    now = local(2026, 9, 25, 12, 0)
    for text, (name, fields) in OURS.items():
        got = Q.match(text, now)
        ok = got is not None and got.name == name and all(
            (abs(got.f.get(k, 0) - v) < 0.5 if isinstance(v, (int, float)) and not isinstance(
                v, bool) else got.f.get(k) == v) for k, v in fields.items())
        check(f"ours: {text!r} -> {name}", ok, got and (got.name, got.f))


def t_near_misses_go_to_the_model():
    use_tz("Europe/London")
    now = local(2026, 9, 25, 12, 0)
    for text in NOT_OURS:
        got = Q.match(text, now)
        check(f"to the model: {text!r}", got is None, got and (got.name, got.f))
    check("English only, and said so", Q.LANGUAGES == ("English",))


def t_times_are_read_right():
    use_tz("Europe/London")
    now = local(2026, 9, 25, 12, 0)             # Friday noon

    def at(text):
        i = Q.match(text, now)
        return wall(i.f["when"].at) if i and i.f["when"].at else None
    cases = {
        "set an alarm for 7": (2026, 9, 25, 19, 0),        # the next 7 o'clock: this evening
        "set an alarm for 7am": (2026, 9, 26, 7, 0),
        "set an alarm for tomorrow at 6": (2026, 9, 26, 6, 0),   # an alarm: the morning
        "remind me tomorrow at 5 to call": (2026, 9, 26, 17, 0),  # a reminder at 5: afternoon
        "remind me tomorrow at 9 to call": (2026, 9, 26, 9, 0),
        "remind me tomorrow to call": (2026, 9, 26, 9, 0),        # no time: 09:00, said
        "remind me tonight to call": (2026, 9, 25, 20, 0),
        "remind me in 20 minutes to call": (2026, 9, 25, 12, 20),
        "remind me on Monday at 8:15 to call": (2026, 9, 28, 8, 15),
        "remind me on Friday at 9 to call": (2026, 10, 2, 9, 0),  # said on a Friday: next one
        "wake me at quarter to 7 tomorrow": (2026, 9, 26, 6, 45),
        "set an alarm for 19:30": (2026, 9, 25, 19, 30),
        "remind me at midnight to call": (2026, 9, 26, 0, 0),
    }
    for text, want in cases.items():
        check(f"{text!r} is {want[3]:02d}:{want[4]:02d} on the {want[2]}th", at(text) == want,
              at(text))


def t_twelve_at_night_is_midnight_and_a_bare_twelve_is_said_back():
    use_tz("Europe/London")
    now = local(2026, 9, 25, 10, 0)             # Friday 10:00
    w = World(now, name="twelve")

    def when(text, kind="alarm"):
        return Q.parse_when(Q.normalise(text), now, kind)
    for text in ("12 at night", "12 in the evening", "12:00 at night", "tonight at 12"):
        got = when(text)
        check(f"{text!r} is midnight (00:00 on Saturday), never noon",
              got is not None and got.at is not None and wall(got.at) == (2026, 9, 26, 0, 0),
              wall(got.at) if got and got.at else got)
    check("'12pm' is still noon and is not flagged", wall(when("12pm").at) == (2026, 9, 25, 12, 0)
          and when("12pm").said12 is False)
    check("'12am' is still midnight and is not flagged", wall(when("12am").at) == (2026, 9, 26, 0, 0)
          and when("12am").said12 is False)
    check("'noon' and 'midnight' are not flagged", when("noon").said12 is False
          and when("midnight").said12 is False)
    check("'12 in the afternoon' is noon", wall(when("12 in the afternoon").at) == (2026, 9, 25, 12, 0))
    check("a bare '12' is flagged", when("12").said12 is True)
    check("... and so is '12:30'", when("12:30").said12 is True)
    check("... but '7' is not", when("7").said12 is False)
    r = Q.answer("set an alarm for 12 at night", sched=w.s, now=now)
    check("the reply says the time back: 12:00 midnight, and how to get noon",
          r.reply.endswith('That is 12:00 midnight. If you meant the other, say "12 noon".')
          and "00:00" in r.reply, r.reply)
    r = Q.answer("set an alarm for 12", sched=w.s, now=now)
    check("a bare 12 (10:00 now): the next one is noon, and the reply says so",
          "12:00 noon" in r.reply and 'say "midnight"' in r.reply, r.reply)
    r = Q.answer("set an alarm for 12pm", sched=w.s, now=now)
    check("an explicit 12pm needs no extra words", "That is" not in r.reply, r.reply)
    got = when("every day at 12")
    check("'every day at 12' is midnight (00:00) and flagged so the reply says it",
          got.rule == {"every": "day", "at": "00:00"} and got.said12 is True, got.rule)
    got = when("every night at 12")
    check("'every night at 12' is midnight too", got.rule["at"] == "00:00")
    got = when("every weekday at 12")
    check("'every weekday at 12' is flagged", got.said12 is True and got.rule["at"] == "00:00")
    r = Q.answer("remind me every day at 12 to stretch", sched=w.s, now=now)
    check("a repeating reminder says '12:00 midnight' back",
          "12:00 midnight" in r.reply, r.reply)
    r = Q.answer("remind me every day at 12 noon to stretch", sched=w.s, now=now)
    check("... but '12 noon' is 12:00 and says nothing extra", "That is" not in r.reply
          and "at 12:00" in r.reply, r.reply)


def t_a_fired_job_says_how_long_ago_by_the_pcs_own_clock():
    use_tz("Europe/London")
    w = World(local(2026, 9, 25, 12, 0), name="age")
    j = w.s.add_timer(60, "tea")
    check("a job that has not gone off has no age", "age_s" not in w.s.job(j["id"]))
    w.clock.t += 60
    w.s.tick()
    w.clock.t += 45
    v = w.s.job(j["id"])
    check("once it went off, the view says how long ago, in seconds, by the PC's clock",
          v.get("age_s") == 45.0, v)
    check("... and it is the same in the list", any(x.get("age_s") == 45.0
                                                    for x in w.s.listed() + [v]))
    w.clock.t -= 3600
    check("... and never negative, even if the clock was set back",
          w.s.job(j["id"])["age_s"] == 0.0)


def t_a_clock_set_back_keeps_a_timers_time_left_but_not_a_reminders_time():
    use_tz("Europe/London")
    w = World(local(2026, 9, 25, 12, 0), name="back")
    t = w.s.add_timer(600, "pasta")
    r = w.s.add_at("reminder", local(2026, 9, 25, 13, 0), "call")
    w.clock.t += 100
    w.s.tick()
    check("CONTROL: 100 s in, the timer has 500 s left", w.s.job(t["id"])["left"] == 500)
    w.clock.t -= 3600                           # the PC's clock is set back an hour
    w.s.tick()
    check("after the clock went back an hour the timer STILL has 500 s left",
          abs(w.s.job(t["id"])["left"] - 500) < 1, w.s.job(t["id"])["left"])
    check("... a reminder is a time on the clock and stays where it was",
          w.s.job(r["id"])["due"] == local(2026, 9, 25, 13, 0))
    w.clock.t += 499
    check("the timer does not go off early", w.s.tick() == [])
    w.clock.t += 2
    check("... and goes off when its own 500 s are over (not an hour later)",
          w.s.tick() == [t["id"]])


def t_acting_and_the_replies():
    use_tz("Europe/London")
    now = local(2026, 9, 25, 12, 0)
    w = World(now, name="quick")
    r = Q.answer("set a timer for 10 minutes", sched=w.s, now=now)
    check("a timer: one short sentence", r.reply == "Timer set for 10 minutes.", r.reply)
    r2 = Q.answer("set a pasta timer for 5 minutes", sched=w.s, now=now)
    r = Q.answer("cancel the timer", sched=w.s, now=now)
    check("two timers and \"cancel the timer\": asks which, cancels nothing",
          r.reply.startswith("You have 2 timers") and len(w.s.timers()) == 2, r.reply)
    r = Q.answer("cancel the pasta timer", sched=w.s, now=now)
    check("... \"cancel the pasta timer\" cancels that one",
          r.reply == "Pasta timer cancelled." and len(w.s.timers()) == 1, r.reply)
    w.clock.t = now + 150
    r = Q.answer("how long is left", sched=w.s, now=w.clock.t)
    check("how long is left", r.reply == "7 minutes 30 seconds left.", r.reply)
    r = Q.answer("add 5 minutes to the timer", sched=w.s, now=w.clock.t)
    check("add time", r.reply == "Added 5 minutes. 12 minutes 30 seconds left.", r.reply)
    r = Q.answer("remind me to call Mum at 6pm", sched=w.s, now=now)
    check("a reminder: the reply says when, not the words",
          r.reply == "Reminder set for 18:00 today." and "Mum" not in r.reply, r.reply)
    job = w.s.job(r.ids[0])
    check("... and keeps the owner's own words, capitals and all", job["text"] == "call Mum")
    r = Q.answer("remind me every weekday at 7 to take my pills", sched=w.s, now=now)
    check("a repeat is set up at once, no card, and says its next three times (2026-09-26)",
          r.reply.startswith("Reminder set up, every weekday (Monday to Friday) at 07:00. Next: ")
          and r.reply.endswith("Delete it under Coming up to stop it.")
          and r.reply.count(" and ") == 1 and "approval card" not in r.reply
          and w.cards == [] and w.s.job(r.ids[0])["state"] == "active", r.reply)
    Q.answer("add milk to my to-do list", sched=w.s, now=now)
    Q.answer("add call the bank to my to-do list", sched=w.s, now=now)
    r = Q.answer("what's on my to-do list", sched=w.s, now=now)
    check("the to-do list, read out", r.reply == "Your to-do list: milk and call the bank."
          and r.private, r.reply)
    check("... marked private, so a voice answer stays on screen like notes",
          Q.route_fields(r).get("gate") == "private")
    r = Q.answer("mark milk as done", sched=w.s, now=now)
    check("mark done", r.reply == "Marked done." and len(w.s.todos()) == 1)
    check("mark done for something not on the list goes to the model",
          Q.answer("mark the report as done", sched=w.s, now=now) is None)
    check("\"5 more minutes\" with no timer running goes to the model",
          Q.answer("5 more minutes", sched=World(now, name="empty").s, now=now) is None)
    r = Q.answer("cancel all timers", sched=w.s, now=now)
    check("\"cancel all timers\" cancels nothing and says one at a time",
          "one at a time" in r.reply and len(w.s.timers()) == 1)
    r = Q.answer("set an alarm for 7am today", sched=w.s, now=now)
    check("a time that has passed today is said, not set", "already passed" in r.reply)


def t_only_the_owners_own_words_act():
    use_tz("Europe/London")
    now = local(2026, 9, 25, 12, 0)
    w = World(now, name="prov")

    def body(*msgs):
        return {"messages": list(msgs), "stream": True}
    say = {"role": "user", "content": "set a timer for 10 minutes"}
    check("typed: acts", Q.answer_turn(body(dict(say, provenance="typed")), sched=w.s, now=now)
          is not None)
    check("said: acts (a voice turn, hands-free or not)",
          Q.answer_turn(body(dict(say, provenance="voice")), sched=w.s, now=now) is not None)
    for how in ("pasted", "shared", "clipboard", "picture_caption", "voice_unverified",
                "unknown", None):
        m = dict(say)
        if how:
            m["provenance"] = how
        check(f"{how or 'no tag'}: goes to the model",
              Q.answer_turn(body(m), sched=w.s, now=now) is None)
    check("with an app's own system text: the model",
          Q.answer_turn(body({"role": "system", "content": "x"}, dict(say, provenance="typed")),
                        sched=w.s, now=now) is None)
    check("sent with a share: the model",
          Q.answer_turn(body({"role": "user", "content": "x", "provenance": "shared"},
                             dict(say, provenance="typed")), sched=w.s, now=now) is None)
    check("with a picture: the model", Q.answer_turn(body(dict(
        say, provenance="typed", content=[{"type": "text", "text": say["content"]},
                                          {"type": "image_url", "image_url": {"url": "x"}}])),
        sched=w.s, now=now) is None)
    check("the newest message only: an older command is not acted on again",
          Q.answer_turn(body(dict(say, provenance="typed"),
                             {"role": "assistant", "content": "Timer set."},
                             {"role": "user", "content": "thanks, what's for dinner",
                              "provenance": "typed"}), sched=w.s, now=now) is None)

# --------------------------------------------------------------------------
#   The model is never called on a match - through the real patched block
# --------------------------------------------------------------------------


def _patched(target):
    order = _stack.order()
    text, log = _stack.stand_in(target, order)
    return text, log


def _quick_block(hud: str) -> str:
    start = hud.index("        # schedule.patch: timers, alarms, reminders and the to-do list are")
    end = hud.index("            return\n", start) + len("            return\n")
    return hud[start:end]


class _Handler:
    def __init__(self):
        self.status, self.headers, self.out, self._headers_sent = None, {}, b"", False
        self.wfile = self

    def send_response(self, code):
        self.status = code

    def send_header(self, k, v):
        self.headers[k] = v

    def end_headers(self):
        pass

    def write(self, b):
        self.out += b

    def flush(self):
        pass


def t_no_model_on_a_match():
    if not shutil.which("git"):
        return skip("git is not installed")
    use_tz("Europe/London")
    hud, log = _patched("jarvis_hud.py")
    check("the whole stack, schedule.patch included, builds", hud is not None, log)
    if hud is None:
        return
    block = _quick_block(hud)
    i = hud.index(block)
    later = hud[i + len(block):]
    check("the fast path comes before the speed record, the tool loop and the relay",
          "jarvis_speed.start(lane)" in later and "run_local_turn(" in later
          and "_degrade_hops" in later)
    check("... and returns: nothing after it runs on a match", block.rstrip().endswith("return"))
    ns = {}
    exec(compile("import json, socket\n"
                 "def f(self, body, route_header, _history, _temporary_chat):\n" + block,
                 "<schedule.patch block>", "exec"), ns)
    now = time.time()
    w = World(now, name="nomodel")
    S._SCHED = w.s
    saved = (socket.socket.connect, urllib.request.urlopen)
    called = []

    def refuse(*a, **k):
        called.append(a)
        raise AssertionError("the model (or any socket) was reached")
    socket.socket.connect = refuse
    urllib.request.urlopen = refuse
    import jarvis_agent
    saved_turn = jarvis_agent.run_local_turn
    jarvis_agent.run_local_turn = refuse
    try:
        h, hist = _Handler(), {"turn": None}
        route = {"lane": "qwen3:8b", "inject_memory": True, "injected_facts": 2,
                 "injected_ids": ["mem:1", "mem:2"], "memory_side": "hud"}
        body = {"messages": [{"role": "user", "content": "set a timer for 10 minutes",
                              "provenance": "voice"}], "stream": True}
        ns["f"](h, body, route, hist, lambda b: b.get("temporary") is True)
        check("a match is answered with every socket and the model's turn made to fail",
              h.status == 200 and not called, called)
        rh = json.loads(h.headers.get("X-Jarvis-Route", "{}"))
        check("X-Jarvis-Route: quick, local, no AI model, no facts used",
              rh.get("quick") == "timer_set" and rh.get("where") == "local"
              and rh.get("lane") == Q.LANE and rh.get("injected_facts") == 0
              and rh.get("injected_ids") == [] and rh.get("inject_memory") is False, rh)
        # In the owner's manner - warm by default (jarvis_manner.py): the
        # same facts as the plain "Timer set for 10 minutes." (test_manner.py).
        check("the answer is Ollama's SSE shape, then [DONE]",
              h.headers.get("Content-Type") == "text/event-stream"
              and b'"content":"Got it - timer set for 10 minutes."' in h.out
              and h.out.endswith(b"data: [DONE]\n\n"), h.out[:300])
        check("this PC's record of the turn gets the answer (for chat history)",
              hist["turn"]["answer"] == "Got it - timer set for 10 minutes."
              and hist["turn"]["tools_ran"] == [])
        check("the timer is really running", len(w.s.timers()) == 1)
        h2 = _Handler()
        body2 = {"messages": [{"role": "user", "content": "remind me at 6pm to call Mum",
                               "provenance": "typed"}], "stream": False, "temporary": True}
        ns["f"](h2, body2, {"memory_side": "hud"}, {"turn": None},
                lambda b: b.get("temporary") is True)
        rh2 = json.loads(h2.headers.get("X-Jarvis-Route", "{}"))
        check("a temporary chat: the reminder is still set, and the header says temporary",
              rh2.get("temporary") is True and h2.headers["Content-Type"] == "application/json"
              and json.loads(h2.out)["choices"][0]["message"]["content"].startswith("Got it - reminder set"))
        h3 = _Handler()
        got = ns["f"](h3, {"messages": [{"role": "user", "content": "how long does it take to "
                                         "boil an egg", "provenance": "typed"}]},
                      {}, {"turn": None}, lambda b: False)
        check("anything else falls through untouched, to the model as before",
              got is None and h3.status is None and h3.out == b"")
    finally:
        socket.socket.connect, urllib.request.urlopen = saved
        jarvis_agent.run_local_turn = saved_turn
        S._SCHED = None

# --------------------------------------------------------------------------
#   The learner, and the model's own tools
# --------------------------------------------------------------------------


def t_the_learner_skips_commands():
    import jarvis_intake as I
    use_tz("Europe/London")
    w = World(time.time(), name="learn")
    S._SCHED = w.s
    try:
        msgs = [{"role": "user", "content": "remind me to call Mum at 6"},
                {"role": "user", "content": "add insulin pen to my to-do list"},
                {"role": "user", "content": "My sister lives in Porto"}]
        got = [m["content"] for m in I.owner_turns(msgs, "owner")]
        check("a command is not read for facts; an ordinary sentence still is",
              got == ["My sister lives in Porto"], got)
        odd = "could you make sure I don't forget the dentist thing next week"
        check("before the tool marks it, an odd phrasing is read", I.schedule_command(odd) is False)
        w.s.mark_command(odd)
        check("after a tool set a reminder from it, it is skipped too",
              I.schedule_command(odd) is True)
        raw = w.s.path.read_bytes()
        check("the command record is a digest, never the words", b"dentist" not in raw)
    finally:
        S._SCHED = None


def t_the_models_tools():
    import jarvis_agent as AG
    use_tz("Europe/London")
    w = World(time.time(), name="tools")
    S._SCHED = w.s
    gated = []

    def checker(action, detail, prompt):
        gated.append(action)
        return Verdict(True, "ask", "approved")

    class Out:
        gone = False

        def set_status(self, *_):
            pass

    def call(name, args, watch):
        convo = [{"role": "user", "content": "please sort this out"}]
        steps = []
        AG._one_call({"id": "c1", "function": {"name": name, "arguments": json.dumps(args)}},
                     list(AG.SCHEDULE_TOOLS), convo, steps, checker, None, Out(),
                     lambda *a, **k: None, watch=watch)
        return json.loads(convo[-1]["content"]), steps
    try:
        clean = AG._TurnWatch([{"role": "user", "content": "x", "provenance": "typed"}],
                              tainted=False)
        res, steps = call("set_timer", {"minutes": 10, "label": "tea"}, clean)
        check("set_timer: runs with no card - the owner's decision for a one-off",
              res.get("ok") is True and gated == [] and len(w.s.timers()) == 1, res)
        res, _ = call("set_reminder", {"text": "call Mum", "when": "tomorrow at 6pm"}, clean)
        check("set_reminder once: no card", res.get("ok") is True and gated == [] and
              w.cards == [], res)
        res, _ = call("set_reminder", {"text": "pills", "repeat": {"every": "day", "at": "08:00"}},
                      clean)
        check("set_reminder repeating: no card (2026-09-26), set up at once, and the model is "
              "told the next times", w.cards == [] and gated == [] and res.get("ok") is True
              and "Next: " in str(res.get("said")), (w.cards, gated, res))
        res, _ = call("todo_add", {"text": "buy stamps"}, clean)
        res, _ = call("coming_up", {}, clean)
        check("coming_up lists the jobs and the to-do list", res.get("ok") is True
              and "buy stamps" in res.get("todo", []))
        check("the sentence that asked is marked as a command for the learner",
              w.s.was_command("please sort this out"))
        n = len(w.s.listed())
        tainted = AG._TurnWatch([{"role": "user", "content": "x", "provenance": "pasted"}],
                                tainted=False)
        res, steps = call("set_timer", {"minutes": 5}, tainted)
        check("after outside text (a pasted message) it sets nothing, and says why",
              res.get("ok") is False and "outside text" in res.get("error", "")
              and len(w.s.listed()) == n and steps[-1]["ran"] is False, res)
        check("every scheduler tool is in TOOLS with a schema",
              all(n in AG.TOOLS for n in AG.SCHEDULE_TOOLS))

        # jarvis_quick.run() is declared `-> Optional[Result]` (its own line
        # 3711). The todo_done branch always checked for None; set_timer and
        # todo_add did not, so a None there was an AttributeError on res.ids,
        # mid-turn, after the model had already asked for a timer. Found by
        # pyright's reportOptionalMemberAccess, 2026-10-03 - and proven against
        # the deployed file, where both raised:
        #   AttributeError: 'NoneType' object has no attribute 'ids'
        import jarvis_quick as Q
        real_run = Q.run
        Q.run = lambda *a, **k: None
        try:
            for name, args, want_error in (
                    ("set_timer", {"minutes": 10}, "the timer was not set"),
                    ("todo_add", {"text": "buy stamps"}, "the item was not added")):
                # Counts, not emptiness: earlier in this same test a real
                # set_timer and todo_add already ran, so the scheduler is not
                # empty and "nothing at all" would be the wrong thing to assert.
                before = (len(w.s.timers()), len(w.s.todos()))
                raised = None
                try:
                    res, _st = call(name, args, clean)
                except Exception as exc:            # noqa: BLE001 - the bug
                    raised = exc
                    res = {}
                after = (len(w.s.timers()), len(w.s.todos()))
                check(f"{name}: a None from jarvis_quick.run is a plain refusal, "
                      f"not an AttributeError",
                      raised is None and res.get("ok") is False
                      and res.get("error") == want_error,
                      repr(raised) if raised is not None else repr(res))
                check(f"{name}: and that None added nothing",
                      after == before, f"{before} -> {after}")
        finally:
            Q.run = real_run
    finally:
        S._SCHED = None

# --------------------------------------------------------------------------
#   schedule.patch
# --------------------------------------------------------------------------


def _rehearse():
    order = _stack.order()
    if "schedule.patch" not in order:
        return False, "schedule.patch is not in apply-patches.ps1's list", {}, {}
    before_list = order[:order.index("schedule.patch")]
    patch = (HERE / "schedule.patch").read_text(encoding="utf-8")
    befores, afters = {}, {}
    git = shutil.which("git")
    for target in ("jarvis_hud.py", "jarvis_gate.py"):
        text, log = _stack.stand_in(target, before_list)
        if text is None:
            return False, "; ".join(log), {}, {}
        d = Path(tempfile.mkdtemp(prefix="jarvis-sched-patch-"))
        try:
            (d / target).write_text(text, encoding="utf-8", newline="\n")
            (d / "p.patch").write_text(patch, encoding="utf-8", newline="\n")
            r = subprocess.run([git, "apply", "--include", target, "p.patch"], cwd=d,
                               capture_output=True, text=True)
            if r.returncode != 0:
                return False, f"{target}: {r.stderr}", {}, {}
            after = (d / target).read_text(encoding="utf-8")
            r = subprocess.run([git, "apply", "-R", "--include", target, "p.patch"], cwd=d,
                               capture_output=True, text=True)
            if r.returncode != 0 or (d / target).read_text(encoding="utf-8") != text:
                return False, f"{target}: does not reverse cleanly: {r.stderr}", {}, {}
        finally:
            shutil.rmtree(d, ignore_errors=True)
        befores[target], afters[target] = text, after
    return True, "", befores, afters


def t_the_patch():
    if not shutil.which("git"):
        return skip("git is not installed")
    ok, why, before, after = _rehearse()
    check("schedule.patch applies to what the earlier patches wrote, and reverses", ok, why)
    if not ok:
        return
    hud, gate = after["jarvis_hud.py"], after["jarvis_gate.py"]
    i = hud.index('        if path == "/api/schedule":')
    blk = hud[i:hud.index('        if path in ("/api/wiki"', i)]
    check("GET /api/schedule checks origin and token, then hands the query over",
          "_origin_ok(self)" in blk and "_token_ok(self)" in blk
          and "jarvis_schedule.handle_get(" in blk)
    i = hud.index('        if route in ("/api/schedule/add", "/api/schedule/act"):')
    blk2 = hud[i:hud.index('        if route == "/api/wiki/ingest":', i)]
    check("the two POSTs check origin and token and hand the body over",
          "_origin_ok(self)" in blk2 and "_token_ok(self)" in blk2
          and "jarvis_schedule.handle_add(body)" in blk2
          and "jarvis_schedule.handle_act(body)" in blk2)
    for name, b in (("GET", blk), ("POST", blk2)):
        try:
            compile("def f(self, path, route):\n" + b, "<patched block>", "exec")
            check(f"the patched {name} block compiles", True)
        except SyntaxError as exc:
            check(f"the patched {name} block compiles", False, str(exc))
    check("the scheduler is started at boot, and a failure there is said, not raised",
          "_sched = jarvis_schedule.start()" in hud and "schedule   OFF" in hud)
    check("the approval notice knows schedule_repeat stays on this PC",
          '"schedule_repeat": ("yes", "local",' in gate)
    check("... and a \"no\" to it proposes no standing rule (the owner asked for it)",
          '"schedule_repeat",' in gate[gate.index("_NO_RULE_FROM_DENIAL"):])
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    start = ps1.index("$PATCHES = @(")
    names = [l.strip().strip("'") for l in ps1[start:ps1.index("\n)", start)].splitlines()
             if l.strip().startswith("'")]
    # Only the real dependencies are pinned - the patches whose lines its
    # context uses - not "last", which the next new patch would break.
    check("apply-patches.ps1 applies schedule.patch after the patches it builds on",
          all(names.index(p) < names.index("schedule.patch")
              for p in ("hardware.patch", "chat-history.patch", "extraction-wiring.patch")))
    shipped = ps1[ps1.index("$SHIPPED = @("):]
    import _where
    check("both new modules are copied in, in _where.SHIPPED too",
          "'jarvis_schedule.py'" in shipped and "'jarvis_quick.py'" in shipped
          and "jarvis_schedule.py" in _where.SHIPPED and "jarvis_quick.py" in _where.SHIPPED)
    toml = (HERE / "rebuilt" / "jarvis-framework.toml").read_text(encoding="utf-8")
    check('the shipped toml has schedule_repeat = "ask"',
          re.search(r'^schedule_repeat\s*=\s*"ask"', toml, re.M) is not None)


def t_the_routes_answer():
    use_tz("Europe/London")
    w = World(time.time(), name="routes")
    S._SCHED = w.s
    try:
        code, out = S.handle_add({"kind": "todo", "text": "post the letter"})
        check("add a to-do", code == 200 and out["job"]["text"] == "post the letter")
        code, out = S.handle_add({"kind": "timer", "seconds": 90})
        check("add a timer", code == 200 and out["job"]["kind"] == "timer")
        tid = out["job"]["id"]
        code, out = S.handle_add({"kind": "reminder", "text": "stretch",
                                  "repeat": {"every": "hours", "hours": 2}})
        check("add a repeat: 200, set up at once with no card (2026-09-26)",
              code == 200 and out["waiting"] is False and out["job"]["state"] == "active"
              and out["said"].startswith("Reminder set up, every 2 hours. Next: "), out)
        code, out = S.handle_add({"kind": "asktest", "text": "x",
                                  "repeat": {"every": "day", "at": "07:00"}})
        check("... a kind that asks: 202, waiting on its card",
              code == 202 and out["waiting"] is True and out["said"] == S.WAITS_FOR_CARD, out)
        S.get().act(out["job"]["id"], "delete")
        code, out = S.handle_get("")
        check("GET: the jobs and the to-do list", code == 200 and len(out["jobs"]) == 2
              and out["todo"][0]["text"] == "post the letter" and out["available"] is True)
        code, out = S.handle_get(f"id={tid}")
        check("GET ?id=: one job", code == 200 and out["job"]["id"] == tid
              and out["job"]["lock_screen"] == "Jarvis: your timer is done.")
        check("GET ?id= for something gone: 404", S.handle_get("id=s0000000000")[0] == 404)
        check("act by id", S.handle_act({"id": tid, "do": "pause"})[0] == 200)
        check("a bad kind is 400", S.handle_add({"kind": "everything"})[0] == 400)
        # The four built in; kinds added later (the standby schedule) have
        # their own words and their own tests.
        check("the lock-screen words are the kind's, never the job's",
              {k.name: k.lock_screen for k in S.KINDS.values()
               if k.name in ("timer", "alarm", "reminder", "todo")} == {
                  "timer": "Jarvis: your timer is done.", "alarm": "Jarvis: alarm.",
                  "reminder": "Jarvis: a reminder is due.",
                  "todo": "Jarvis: a to-do item is due."})
    finally:
        S._SCHED = None


def t_a_new_kind_plugs_in():
    use_tz("Europe/London")
    seen = []
    S.register_kind("briefing", "morning briefing", "Jarvis: your briefing is ready.",
                    on_fire=lambda jid: seen.append(jid), owner_listed=True)
    try:
        w = World(local(2026, 9, 25, 6, 0), name="kind")
        j = w.s.add_at("briefing" if "briefing" in S.KINDS else "reminder",
                       local(2026, 9, 25, 7, 0))
        w.clock.t = local(2026, 9, 25, 7, 0)
        w.s.tick()
        check("a later kind (a morning briefing) goes off through the same loop and event",
              seen == [j["id"]] and w.events[-1][1]["kind"] == "briefing")
    finally:
        S.KINDS.pop("briefing", None)


def t_a_scheduler_call_does_not_leave_its_database_file_open():
    """Every connection the scheduler opens is CLOSED when its block ends.

    WHY (2026-10-07, the intermittent backend-windows CI failure; still failing
    a different suite on 2026-10-08). sqlite3's context manager commits on the
    way out and never closes the connection, so a bare
    `with self._db() as c:` left an OPEN HANDLE on schedule.json behind until
    CPython happened to collect it - immediate on a quiet line, and NOT
    immediate when a caught exception's traceback, a generator frame or a
    temp-folder object still held a reference. On Windows an open handle makes
    the file undeletable, which is what the runner's own log said, twice,
    inside test_sayable.py's group (run 2026-10-07, PR #86):

        Exception ignored in: <finalize object at ...; dead>
          File "...\\tempfile.py", line 939, in _cleanup
            cls._rmtree(name, ignore_errors=ignore_errors)
          ...
          File "...\\tempfile.py", line 909, in onexc
            _os.unlink(path)
        PermissionError: [WinError 32] The process cannot access the file
        because it is being used by another process:
        'C:\\Users\\RUNNER~1\\AppData\\Local\\Temp\\tmpqw88ug3r\\schedule.json'

    - TemporaryDirectory's own cleanup, and the same again for a second folder
    (tmpxh2pi8w1) a moment later. Which suite it lands on depends on when the
    handle is released, which is why the failing suite's name kept changing.

    This is the deterministic half of that, and it holds on every platform:
    every connection is KEPT (so no refcount can be what closes it) and then
    asked to do something. On the old code each one answers and the check is
    red; with _ClosingConnection they are all closed and it is green. Linux
    cannot show the deletion failure at all, so without this the fix would be
    unmeasurable here."""
    import sqlite3
    made = []
    real = S.sqlite3.connect

    def spy(*a, **kw):
        c = real(*a, **kw)
        made.append(c)          # held on purpose: the collector must not close it
        return c

    S.sqlite3.connect = spy
    try:
        w = World(local(2026, 9, 25, 12, 0), name="closed")
        jid = w.s.add_timer(600, "tea")["id"]
        w.s.act(jid, "pause")
        w.s.job(jid)
        w.s.listed()
        w.s.status()
        w.s.mark_command("set a timer for ten minutes")
        w.s.was_command("set a timer for ten minutes")
    finally:
        S.sqlite3.connect = real

    def still_readable(c):
        try:
            c.execute("SELECT 1")
            return True
        except sqlite3.ProgrammingError:
            return False

    open_ones = [c for c in made if still_readable(c)]
    check("every connection the scheduler opens is closed when its `with` block "
          "ends (a leaked handle is what made schedule.json undeletable on the "
          "Windows runner, 2026-10-07)",
          bool(made) and not open_ones, f"{len(open_ones)} of {len(made)} still open")
    # And the thing the runner actually saw: a folder holding the scheduler's
    # own file, removed the way a suite's temporary folder is.
    d = Path(tempfile.mkdtemp(prefix="jarvis-schedule-del-"))
    s2 = S.Scheduler(d / "schedule.json", clock=Clock(local(2026, 9, 25, 12, 0)),
                     spawn=lambda fn: fn(), publish=lambda k, x: None)
    s2.add_timer(60, "think")
    try:
        shutil.rmtree(str(d))
        removed, why = True, ""
    except OSError as exc:
        removed, why = False, f"{type(exc).__name__}: {exc}"
    check("... so the folder holding it can be removed at once, the way a suite's "
          "temporary folder is removed (on Windows an open handle refuses this)",
          removed, why)


def t_the_docs_say_which_channel_a_phone_notification_uses():
    """Which notification channel a fired job uses on the phone (docs, 2026-10-10).

    `docs/JARVIS-API.md` section 21.4 said it went on the APPROVAL channel. It
    does not. `ScheduleNotifier.kt` builds an ordinary one on its own
    `jarvis_schedule` channel ("Reminders and timers"; the owner's decision of
    2026-09-30, so silencing reminders does not silence approvals), and an
    alarm - or an urgent "tell me when" - on `jarvis_alarm` ("Alarms and urgent
    alerts"). Measured on the owner's own phone: a reminder set on the PC
    arrived on `jarvis_schedule`, title "Reminder", with its Snooze action.

    Both channel ids are read OUT OF the phone's own source here rather than
    written into this test, so the document and the app cannot drift apart
    quietly: rename a channel in `ScheduleNotifier.kt` and this fails until the
    document says the new name."""
    api = (REPO / "docs" / "JARVIS-API.md").read_text(encoding="utf-8")
    start = api.index("### 21.4 The event")
    section = api[start:api.index("### 21.5", start)]
    kotlin = (REPO / "jarvis-client" / "app" / "src" / "main" / "java" / "com" / "jarvis"
              / "client" / "service" / "ScheduleNotifier.kt")
    if not kotlin.is_file():
        return skip("jarvis-client's ScheduleNotifier.kt is not here to check the doc against")
    src = kotlin.read_text(encoding="utf-8")
    named = re.search(r'SCHEDULE_CHANNEL_ID\s*=\s*"([^"]+)"', src)
    ringing = re.search(r'ALARM_CHANNEL_ID\s*=\s*"([^"]+)"', src)
    if not named or not ringing:
        return check("ScheduleNotifier.kt still names its two channels", False, str(kotlin))
    channel, alarm = named.group(1), ringing.group(1)
    check("the phone's own code gives a schedule notification its own channel, apart from "
          "the approval one", (channel, alarm) == ("jarvis_schedule", "jarvis_alarm"),
          (channel, alarm))
    check(f"JARVIS-API.md section 21.4 names `{channel}` for it", f"`{channel}`" in section,
          section[:200])
    check(f"... and `{alarm}` for an alarm that keeps ringing", f"`{alarm}`" in section)
    check("... and no longer says it goes on the approval channel (the line that was wrong)",
          "on the approval channel" not in section)


# --------------------------------------------------------------------------
#   GTD-1 (2026-10-18): context-rich reminders, read-only conditions, smart
#   snooze, and "the owner is at the PC".
#
#   The reminder store is THIS module's (jarvis_schedule.py); jarvis_tasks.py
#   is the job list and holds no reminders (git grep finds none), so the
#   slice lands here, additively - every old row and old payload is unchanged.
# --------------------------------------------------------------------------

def _gtd_world(name, now):
    return World(now, name=name)


def _gtd_reminder(w, text, **kw):
    return w.s.add_at("reminder", w.clock.t + 3600.0, text, **kw)


def _fake_latch():
    """A stand-in jarvis_gate that records latch_taint calls."""
    import types
    fake = types.ModuleType("jarvis_gate")
    calls = []

    def latch_taint(*, why=""):
        calls.append(why)
        return True
    fake.latch_taint = latch_taint
    old = sys.modules.get("jarvis_gate")
    sys.modules["jarvis_gate"] = fake
    return calls, old


def _restore_gate(old):
    if old is None:
        sys.modules.pop("jarvis_gate", None)
    else:
        sys.modules["jarvis_gate"] = old


def t_gtd_a_context_bundle_is_scrubbed_and_never_a_path():
    import jarvis_scrub
    now = S.wall_to_epoch(2026, 10, 20, 9, 0)
    w = _gtd_world("gtd-bundle", now)
    jarvis_scrub.register_secret("gtd-one-secret-value-98765")
    bundle = {
        "source_conv_id": "conv-42",
        "source_summary": "We talked about the tax form and the token "
                          "gtd-one-secret-value-98765. " + "x" * 400,
        "linked_entities": ["Sam Fisher", "Mum"],
        "linked_files": ["C:\\Users\\pcadmin\\Documents\\tax form.pdf",
                         "/home/pcadmin/notes/secret.txt", "doc-42", "tax-form"],
        "suggested_prompt": "Help me finish the tax form",
    }
    job = _gtd_reminder(w, "Finish the tax form", context_bundle=bundle)
    stored = w.s.bundle(job["id"])
    check("a reminder keeps its context packet on disk", stored != {} and
          stored.get("source_conv_id") == "conv-42", stored)
    check("... the summary is at most 280 characters",
          len(stored.get("source_summary") or "") <= S.BUNDLE_SUMMARY_MAX,
          stored.get("source_summary"))
    check("... a registered secret in the summary is scrubbed out",
          "gtd-one-secret-value-98765" not in (stored.get("source_summary") or ""),
          stored.get("source_summary"))
    check("... a Windows path in linked_files is NEVER stored",
          stored.get("linked_files") == ["doc-42", "tax-form"],
          stored.get("linked_files"))
    check("... no path-shaped string survives anywhere in the packet",
          "C:\\" not in json.dumps(stored) and "/home/" not in json.dumps(stored),
          stored)
    check("... the names are kept, scrubbed", stored.get("linked_entities") ==
          ["Sam Fisher", "Mum"], stored.get("linked_entities"))
    check("... and the suggested prompt is kept",
          stored.get("suggested_prompt") == "Help me finish the tax form", stored)
    # Fail closed (privacy review F2): without the scrubber every WORD is
    # dropped, because a file label or a name can carry a secret too. GTD-1
    # follow-up (2026-10-18): the ONE thing kept is the plain boolean saying
    # the packet was dropped (and never a hash of it).
    real_scrubber = S._scrubber
    S._scrubber = lambda: None
    try:
        bare = S.scrub_context_bundle({"source_summary": "raw private words",
                                       "linked_files": ["keep-me"]})
    finally:
        S._scrubber = real_scrubber
    check("with no scrubber the whole packet is dropped, never raw",
          bare == {S.CONTEXT_DROPPED: True}, bare)
    check("... and the only thing kept is the plain boolean",
          list(bare) == [S.CONTEXT_DROPPED] and bare[S.CONTEXT_DROPPED] is True,
          bare)
    check("... with no raw words in it",
          "raw private words" not in json.dumps(bare) and "keep-me" not in json.dumps(bare),
          bare)


def t_gtd_old_rows_and_plain_reminders_grow_nothing():
    import sqlite3
    now = S.wall_to_epoch(2026, 10, 20, 9, 0)
    old = _TMP / "gtd-old-schedule.db"
    con = sqlite3.connect(str(old))
    try:
        con.executescript(S._SCHEMA)
        con.execute("INSERT INTO jobs (id, kind, text, state, due, created, changed) "
                    "VALUES (?,?,?,?,?,?,?)",
                    ("soldjob0001", "reminder", "Old reminder", "active",
                     now + 100.0, now, now))
        con.commit()
    finally:
        con.close()
    s2 = S.Scheduler(old, clock=Clock(now))
    j = s2.job("soldjob0001")
    check("a schedule.db written before GTD-1 still opens and reads",
          j is not None and j["text"] == "Old reminder", j)
    check("... and grows no GTD keys (trigger, context, count, condition)",
          j is not None and not any(k in j for k in
                                    ("trigger", "has_context", "snooze_count",
                                     "condition_kind")), j)
    w = _gtd_world("gtd-plain", now)
    plain = _gtd_reminder(w, "Book a haircut")
    v = w.s.job(plain["id"])
    check("a plain reminder's payload is what it was before GTD-1",
          not any(k in v for k in ("trigger", "has_context", "snooze_count",
                                   "condition_kind")), v)
    job = _gtd_reminder(w, "Buy milk", context_bundle={
        "source_summary": "we spoke about milk", "linked_files": ["doc-9"]})
    check("a reminder with context says only THAT it has some, never the words",
          w.s.job(job["id"]).get("has_context") is True
          and "context_bundle" not in w.s.job(job["id"])
          and "we spoke about milk" not in json.dumps(w.s.job(job["id"])))


def t_gtd_enrichment_is_withheld_completely_when_hidden():
    now = S.wall_to_epoch(2026, 10, 20, 9, 0)
    w = _gtd_world("gtd-hide", now)
    job = _gtd_reminder(w, "Reply to Sam", context_bundle={
        "source_summary": "Sam asked about the invoice",
        "linked_entities": ["Sam"], "linked_files": ["doc-7"],
        "suggested_prompt": "Draft the reply"})
    view = dict(w.s.job(job["id"]))
    view["context_bundle"] = w.s.bundle(job["id"])
    view.update({"condition_kind": "no_email_reply_from", "condition_target": "Sam"})
    called = []
    readers = {"memory_facts": lambda name: called.append(("memory", name)) or ["x"],
               "email_reply_since": lambda t, since: called.append(("email", t)) or
               {"at": now + 60, "body": "SECRET BODY"},
               "decks_due": lambda: called.append(("decks",)) or 0}
    latch, old = _fake_latch()
    try:
        hidden = S.enrich_and_check_condition(view, readers=readers,
                                              hide_memory_lists=True)
        locked = S.enrich_and_check_condition(view, readers=readers,
                                              app_locked=True)
    finally:
        _restore_gate(old)
    for label, out in (("hide_memory_lists", hidden), ("App lock", locked)):
        check(f"{label}: the whole detail block is withheld",
              out.get("withheld") is True and out.get("context") == {}
              and out.get("facts") == [] and out.get("condition_note") == ""
              and out.get("toast") == "" and out.get("context_attached") is False,
              out)
        check(f"{label}: no reader ran at all", called == [], called)
    check("hide/app-lock: the privacy latch was never touched",
          latch == [], latch)


def t_gtd_enrichment_attaches_context_and_latches_only_then():
    now = S.wall_to_epoch(2026, 10, 20, 9, 0)
    w = _gtd_world("gtd-enrich", now)
    job = _gtd_reminder(w, "Reply to Sam", context_bundle={
        "source_summary": "Sam asked about the invoice",
        "linked_entities": ["Sam"], "linked_files": ["doc-7"],
        "suggested_prompt": "Draft the reply"})
    view = dict(w.s.job(job["id"]))
    view["context_bundle"] = w.s.bundle(job["id"])
    view.update({"condition_kind": "no_email_reply_from", "condition_target": "Sam"})
    asked = []

    def reply(target, since):
        asked.append((target, since))
        return {"at": now + 60.0, "body": "SECRET BODY - must never be shown"}
    latch, old = _fake_latch()
    try:
        out = S.enrich_and_check_condition(
            view, readers={"memory_facts": lambda name: ["Sam's birthday is in May"],
                           "email_reply_since": reply})
    finally:
        _restore_gate(old)
    check("the remembered fact is attached", out["facts"] ==
          ["Sam's birthday is in May"], out["facts"])
    check("the emailed condition says EARLY SATISFACTION", out[
        "condition_satisfied_early"] is True, out)
    check("... the note names the sender and the time - and no body",
          "Sam already replied at" in out["condition_note"]
          and "SECRET BODY" not in out["condition_note"], out["condition_note"])
    check("... the toast carries the note and no email body",
          "Sam already replied at" in out["toast"]
          and "SECRET BODY" not in out["toast"], out["toast"])
    check("... the reader was asked only WHO and SINCE (never for a body)",
          asked == [("Sam", view["created"])], asked)
    check("the context packet came back scrubbed (no path)",
          out["context"]["linked_files"] == ["doc-7"], out["context"])
    check("private context attached -> the taint latch fired, once, with the one reason",
          latch == ["reminder_context"], latch)
    # A bare reminder reads nothing and latches nothing.
    bare = _gtd_reminder(w, "buy milk")
    latch2, old2 = _fake_latch()
    try:
        out2 = S.enrich_and_check_condition(dict(w.s.job(bare["id"])))
    finally:
        _restore_gate(old2)
    check("a bare reminder attaches nothing and latches nothing",
          out2["context_attached"] is False and out2["facts"] == []
          and out2["condition_note"] == "" and latch2 == [], out2)


def t_gtd_conditions_are_read_only_and_never_a_body():
    now = S.wall_to_epoch(2026, 10, 20, 9, 0)
    w = _gtd_world("gtd-cond", now)
    job = _gtd_reminder(w, "Reply to Sam")
    base = dict(w.s.job(job["id"]))
    base["condition_kind"] = "no_email_reply_from"
    base["condition_target"] = "Sam"
    latch, old = _fake_latch()
    try:
        not_replied = S.enrich_and_check_condition(
            base, readers={"email_reply_since": lambda t, since: None})
        latch_after_negative = list(latch)
        decks_three = S.enrich_and_check_condition(
            dict(base, condition_kind="decks_due", condition_target=""),
            readers={"decks_due": lambda: 3})
        decks_none = S.enrich_and_check_condition(
            dict(base, condition_kind="decks_due", condition_target=""),
            readers={"decks_due": lambda: 0})
    finally:
        _restore_gate(old)
    check("no reply yet: the condition is NOT satisfied", not_replied[
        "condition_satisfied_early"] is False and not_replied["condition_note"] == "",
        not_replied)
    check("no reply yet: nothing was attached, so no taint latch",
          not_replied["context_attached"] is False
          and latch_after_negative == [], latch_after_negative)
    check("three cards due: not satisfied", decks_three[
        "condition_satisfied_early"] is False)
    check("no cards due: the condition is satisfied early, in plain words",
          decks_none["condition_satisfied_early"] is True
          and decks_none["condition_note"] == "No cards are due right now",
          decks_none["condition_note"])


def t_gtd_snooze_presets_and_the_boundary_at_three():
    now = S.wall_to_epoch(2026, 10, 20, 9, 0)
    w = _gtd_world("gtd-snooze", now)
    job = _gtd_reminder(w, "Book a haircut")
    short = S.snooze_reminder(job["id"], "15m", now=now, scheduler=w.s)
    check("15m snooze: due fifteen minutes later, count 1",
          short["ok"] and abs(short["due"] - (now + 900.0)) < 0.5
          and short["snooze_count"] == 1, short)
    check("... two snoozes is still below the <3 boundary",
          S.snooze_reminder(job["id"], "15m", now=now, scheduler=w.s)[
              "stuck_hint"] is False)
    third = S.snooze_reminder(job["id"], "1h", now=now, scheduler=w.s)
    check("... the THIRD snooze is stuck (boundary is < 3)",
          third["stuck_hint"] is True and third["snooze_count"] == 3, third)
    check("... but no micro-steps without the owner's opt-in",
          third["micro_steps"] == [], third)
    fourth = S.snooze_reminder(job["id"], "1h", now=now, scheduler=w.s,
                               micro_steps_opt_in=True)
    check("... with the opt-in, three small steps, and only then",
          len(fourth["micro_steps"]) == 3
          and all(isinstance(step, str) and step for step in fourth["micro_steps"]),
          fourth)
    check("1h snooze: due an hour later", abs(S.snooze_reminder(
        _gtd_reminder(w, "Buy milk")["id"], "1h", now=now, scheduler=w.s)["due"]
        - (now + 3600.0)) < 0.5)
    tonight = S.snooze_reminder(_gtd_reminder(w, "Water the plants")["id"],
                                "tonight", now=now, scheduler=w.s)
    check("tonight: the next 19:00 on this PC's clock",
          wall(tonight["due"])[3:] == (19, 0) and tonight["due"] > now, tonight)
    morning = S.snooze_reminder(_gtd_reminder(w, "Buy milk")["id"],
                                "tomorrow_morning", now=now, scheduler=w.s)
    y, mo, d = S._add_days(*S._wall(now)[:3], 1)
    check("tomorrow morning: tomorrow at 09:00 on this PC's clock",
          wall(morning["due"]) == (y, mo, d, 9, 0), morning)
    pc = S.snooze_reminder(_gtd_reminder(w, "Buy milk")["id"],
                           "next_pc_active", now=now, scheduler=w.s)
    pv = w.s.job(pc["snoozed_id"])
    check("next_pc_active: no time, a trigger, and it is on the list",
          pc["due"] is None and pv.get("trigger") == "on_pc_active"
          and pv["state"] == "active", (pc, pv))
    check("an unknown preset is refused in plain words",
          _raises(ValueError, S.snooze_reminder, job["id"], "someday",
                  now=now, scheduler=w.s))
    gone = S.snooze_reminder("snosuchjob0", "15m", now=now, scheduler=w.s)
    check("a reminder that is not there is a plain answer, not an exception",
          gone.get("ok") is False and gone.get("error"), gone)


def _raises(exc_type, fn, *a, **k):
    try:
        fn(*a, **k)
    except exc_type:
        return True
    except Exception:
        return False
    return False


def t_gtd_sensitive_reminders_never_offer_micro_steps():
    now = S.wall_to_epoch(2026, 10, 20, 9, 0)
    w = _gtd_world("gtd-sensitive", now)
    job = _gtd_reminder(w, "Pay the electricity bill")
    out = None
    for _ in range(3):
        out = S.snooze_reminder(job["id"], "15m", now=now, scheduler=w.s,
                                micro_steps_opt_in=True)
    check("the sensitive reminder is recognised as sensitive",
          out["sensitive"] is True, out)
    check("... three snoozes do NOT make it stuck", out["stuck_hint"] is False, out)
    check("... and it never gets the three-step breaker", out["micro_steps"] == [], out)


def t_gtd_pc_active_needs_unlocked_idle_and_no_focus():
    def readers(**kw):
        base = {"session_unlocked": lambda: True, "app_locked": lambda: False,
                "idle_seconds": lambda: 10.0, "focus_active": lambda: False}
        base.update(kw)
        return base
    active = S.pc_active(readers())
    check("all three signals: the owner is at the PC",
          active["active"] is True and active["reason"] == "active"
          and active.get("idle_seconds") == 10.0, active)
    check("a locked Windows session is not active, and says so",
          S.pc_active(readers(session_unlocked=lambda: False))["reason"]
          == "session_locked")
    check("the Jarvis App lock is not active, and says so",
          S.pc_active(readers(app_locked=lambda: True))["reason"] == "app_locked")
    check("121 idle seconds is not active", S.pc_active(
        readers(idle_seconds=lambda: 121.0))["active"] is False)
    check("exactly 120 idle seconds still is (the boundary is <=120)",
          S.pc_active(readers(idle_seconds=lambda: 120.0))["active"] is True)
    check("an idle time that cannot be read is NOT active (fail closed)",
          S.pc_active(readers(idle_seconds=lambda: None))["reason"] == "user_idle")
    focus = S.pc_active(readers(focus_active=lambda: True))
    check("a focus session HOLDS it, even at the keyboard",
          focus["active"] is False and focus["reason"] == "in_focus_session", focus)
    check("no readers at all is the conservative not-active answer",
          S.pc_active()["active"] is False
          and S.pc_active()["reason"] == "session_locked")
    check("an idle-only call is NOT active: a missing lock reader fails closed",
          S.pc_active({"idle_seconds": lambda: 5.0})["active"] is False
          and S.pc_active({"idle_seconds": lambda: 5.0})["reason"]
          == "session_locked")
    half = {"session_unlocked": lambda: True, "idle_seconds": lambda: 5.0}
    check("a missing App-lock reader is NOT active either",
          S.pc_active(half)["active"] is False
          and S.pc_active(half)["reason"] == "app_locked")
    no_focus = dict(half, app_locked=lambda: False)
    check("a missing focus reader is NOT active either",
          S.pc_active(no_focus)["active"] is False
          and S.pc_active(no_focus)["reason"] == "in_focus_session")
    check("a reader that raises is not counted as a yes",
          S.pc_active(readers(idle_seconds=lambda: 1 / 0))["active"] is False)
    check("the answer always carries idle_seconds",
          "idle_seconds" in S.pc_active(readers()))


def t_gtd_active_triggers_hold_until_the_owner_is_back():
    now = S.wall_to_epoch(2026, 10, 20, 9, 0)
    w = _gtd_world("gtd-trigger", now)
    pc_job = _gtd_reminder(w, "Buy milk", trigger="on_pc_active")
    focus_job = _gtd_reminder(w, "Book a haircut", trigger="after_focus")
    plain_job = _gtd_reminder(w, "Water the plants")
    w.clock.t = now + 4000.0
    fired = w.s.tick()
    check("a time reminder still fires on the ordinary tick",
          plain_job["id"] in fired, fired)
    check("an on_pc_active reminder does NOT fire on the clock while idle/locked",
          pc_job["id"] not in fired and w.s.job(pc_job["id"])["state"] == "active")
    check("a locked PC: it stays held",
          S.due_active_reminders(now=w.clock.t, scheduler=w.s,
                                 readers={"session_unlocked": lambda: False}) == [])
    at_pc = S.due_active_reminders(
        now=w.clock.t, scheduler=w.s,
        readers={"session_unlocked": lambda: True, "app_locked": lambda: False,
                 "idle_seconds": lambda: 5.0, "focus_active": lambda: False})
    check("the owner at the PC: both PC triggers are ready (read-only)",
          {j["id"] for j in at_pc} == {pc_job["id"], focus_job["id"]}
          and w.s.job(pc_job["id"])["state"] == "active",
          [j["id"] for j in at_pc])
    in_focus = S.due_active_reminders(
        now=w.clock.t, scheduler=w.s,
        readers={"session_unlocked": lambda: True, "app_locked": lambda: False,
                 "idle_seconds": lambda: 5.0, "focus_active": lambda: True})
    check("a focus session holds them both", in_focus == [], in_focus)
    view = w.s.job(focus_job["id"])
    check("after_focus holds during focus, and is ready afterwards",
          S.reminder_ready(view, now=w.clock.t,
                           readers={"session_unlocked": lambda: True,
                                    "app_locked": lambda: False,
                                    "idle_seconds": lambda: 1.0,
                                    "focus_active": lambda: True}) ==
          (False, "in_focus_session")
          and S.reminder_ready(view, now=w.clock.t,
                               readers={"session_unlocked": lambda: True,
                                        "app_locked": lambda: False,
                                        "idle_seconds": lambda: 1.0,
                                        "focus_active": lambda: False})[0] is True)
    check("a time reminder's readiness is its own due time",
          S.reminder_ready({"due": now, "trigger": "time"}, now=now)[0] is True
          and S.reminder_ready({"due": now + 50, "trigger": "time"}, now=now)[0]
          is False)


def t_gtd_context_expires_seven_days_after_resolution():
    now = S.wall_to_epoch(2026, 10, 20, 9, 0)
    w = _gtd_world("gtd-expire", now)
    job = _gtd_reminder(w, "Buy milk", context_bundle={
        "source_summary": "we spoke about milk", "linked_files": ["doc-3"]})
    w.clock.t = now + 4000.0
    fired = w.s.tick()
    check("the reminder went off and was resolved",
          job["id"] in fired and w.s.job(job["id"])["state"] == "fired", fired)
    check("on day 6 the packet is still there",
          S.expire_context_bundles(now=w.clock.t + 6 * 86400.0, scheduler=w.s)
          == 0 and w.s.bundle(job["id"]) != {})
    check("after seven days the packet is dropped",
          S.expire_context_bundles(now=w.clock.t + 8 * 86400.0, scheduler=w.s)
          == 1 and w.s.bundle(job["id"]) == {})
    check("... but the bare reminder row is still readable",
          w.s.job(job["id"]) is not None
          and w.s.job(job["id"])["text"] == "Buy milk"
          and "has_context" not in w.s.job(job["id"]))


def t_gtd_the_add_route_accepts_the_reminder_fields():
    now = S.wall_to_epoch(2026, 10, 20, 9, 0)
    w = _gtd_world("gtd-route", now)
    real_get = S.get
    S.get = lambda: w.s
    try:
        before = len(w.s.listed())
        code, out = S.handle_add({
            "kind": "reminder", "at": now + 3600.0, "text": "Reply to Sam",
            "trigger": "on_pc_active", "condition_kind": "no_email_reply_from",
            "condition_target": "Sam",
            "context_bundle": {"source_summary": "Sam asked about the invoice",
                               "linked_files": ["C:\\Users\\x\\invoice.pdf",
                                                "doc-11"]}})
        job = out.get("job") or {}
        stored = w.s.bundle(job["id"])
        check("POST /api/schedule/add accepts the GTD fields for a reminder",
              code == 200 and job.get("trigger") == "on_pc_active"
              and job.get("condition_kind") == "no_email_reply_from"
              and job.get("condition_target") == "Sam", (code, out))
        check("... the bundle is stored scrubbed, path dropped",
              stored.get("linked_files") == ["doc-11"], stored)
        old_style = S.handle_add({"kind": "reminder", "at": now + 7200.0,
                                  "text": "Plain reminder"})
        old_job = (old_style[1] or {}).get("job") or {}
        check("a body written before GTD-1 adds exactly the reminder it did",
              old_style[0] == 200 and
              not any(k in old_job for k in ("trigger", "has_context",
                                             "condition_kind", "snooze_count")),
              old_job)
        bad = S.handle_add({"kind": "reminder", "at": now + 9000.0,
                            "text": "Buy milk", "trigger": "sometimes"})
        check("an unknown trigger is refused in words and sets nothing",
              bad[0] == 400 and "trigger" in str((bad[1] or {}).get("error", "")).lower()
              and len(w.s.listed()) == before + 2, bad)
        alarm = S.handle_add({"kind": "alarm", "at": now + 9000.0, "text": "Wake up",
                              "context_bundle": {"source_summary": "ignored"}})
        check("a non-reminder cannot carry a context packet (it is ignored there)",
              alarm[0] == 200 and w.s.bundle((alarm[1] or {}).get("job", {}).get("id"))
              == {}, alarm)
        check("... and the API itself refuses context on an alarm, in words",
              _raises(ValueError, w.s.add_at, "alarm", now + 9099.0, "Wake up",
                      context_bundle={"source_summary": "x"}))
    finally:
        S.get = real_get


def t_gtd_scrubber_failure_stores_no_words():
    """Privacy review F1/F2: no scrubber, or a scrubber that raises, must never
    store a raw word - not a summary, not a name, not a file label. GTD-1
    follow-up (2026-10-18): what IS stored is the plain dropped boolean."""
    secret = "sk-live-FIXTURE-SECRET-1234567890"

    class Boom:
        def __call__(self, text):
            raise RuntimeError("scrubber down")

    real = S._scrubber
    bundle_in = {"source_summary": "key " + secret,
                 "linked_entities": ["name " + secret],
                 "linked_files": ["file " + secret],
                 "suggested_prompt": "use " + secret}
    S._scrubber = lambda: Boom()
    try:
        raised = S.scrub_context_bundle(bundle_in)
    finally:
        S._scrubber = real
    check("a raising scrubber drops the WHOLE packet",
          raised == {S.CONTEXT_DROPPED: True}, raised)
    check("... and no raw secret survives", secret not in json.dumps(raised))
    S._scrubber = lambda: None
    try:
        missing = S.scrub_context_bundle(bundle_in)
        w = _gtd_world("gtd-scrub-fail", S.wall_to_epoch(2026, 10, 20, 9, 0))
        job = w.s.add_at("reminder", w.clock.t + 100.0, "Buy milk",
                         context_bundle=bundle_in)
    finally:
        S._scrubber = real
    check("a missing scrubber drops the WHOLE packet",
          missing == {S.CONTEXT_DROPPED: True}, missing)
    check("... and no raw secret survives", secret not in json.dumps(missing))
    stored_view = w.s.job(job["id"])
    check("... so the reminder stores no context words, and says it dropped them",
          "has_context" not in stored_view
          and stored_view.get(S.CONTEXT_DROPPED) is True
          and secret not in json.dumps(stored_view), stored_view)


def t_gtd_dropped_context_keeps_only_a_plain_boolean():
    """GTD-1 follow-up (Gemini's Q2 ruling, 2026-10-18): when the scrubber is
    missing or raising, the packet's words are gone and the reminder keeps ONE
    plain true flag - no words, no ids, and no hash of them (a hash would be a
    secret oracle). The flag is exposed additively on the reminder view."""
    import sqlite3
    secret = "sk-live-FIXTURE-SECRET-2345678901"
    bundle_in = {"source_conv_id": "conv-9",
                 "source_summary": "key " + secret,
                 "linked_entities": ["name " + secret],
                 "linked_files": ["doc-" + secret],
                 "suggested_prompt": "use " + secret}
    real = S._scrubber

    class Boom:
        def __call__(self, text):
            raise RuntimeError("scrubber down")

    S._scrubber = lambda: Boom()
    try:
        marker = S.scrub_context_bundle(bundle_in)
        w = _gtd_world("gtd-drop-raise", S.wall_to_epoch(2026, 10, 20, 9, 0))
        job = w.s.add_at("reminder", w.clock.t + 100.0, "Buy milk",
                         context_bundle=bundle_in)
    finally:
        S._scrubber = real
    check("a raising scrubber keeps only the plain boolean, no words",
          marker == {S.CONTEXT_DROPPED: True}, marker)
    check("... and no raw secret survives in the result",
          secret not in json.dumps(marker), marker)

    con = sqlite3.connect(str(w.s.path))
    try:
        raw_row = con.execute("SELECT context_bundle FROM jobs WHERE id = ?",
                              (job["id"],)).fetchone()[0]
    finally:
        con.close()
    view = w.s.job(job["id"])
    stored = w.s.bundle(job["id"])
    check("the stored row is the breadcrumb and nothing else",
          json.loads(raw_row) == {S.CONTEXT_DROPPED: True}, raw_row)
    check("... and the raw row holds no secret", secret not in str(raw_row))
    check("the view exposes the boolean additively, and no context words",
          view.get(S.CONTEXT_DROPPED) is True and "has_context" not in view
          and "context_bundle" not in view, view)
    check("... and no raw word or id survives in the view",
          secret not in json.dumps(view) and "conv-9" not in json.dumps(view), view)
    check("a scrubbed dropped marker never grows words when read again",
          S.scrub_context_bundle(stored) == {S.CONTEXT_DROPPED: True}, stored)

    latch, old = _fake_latch()
    try:
        out = S.enrich_and_check_condition(
            dict(view, context_bundle=stored,
                 condition_kind="", condition_target=""), readers={})
    finally:
        _restore_gate(old)
    check("the enriched block says it was dropped and attaches nothing",
          out.get(S.CONTEXT_DROPPED) is True and out.get("context") == {}
          and out.get("context_attached") is False, out)
    check("... the toast is the bare title, never the dropped words",
          out.get("toast") == "Buy milk", out.get("toast"))
    check("... no secret survives in any enriched field",
          secret not in json.dumps(out), out)
    check("... and no privacy latch was touched (no private words were read)",
          latch == [], latch)

    # A MISSING scrubber behaves the same as a raising one.
    S._scrubber = lambda: None
    try:
        w2 = _gtd_world("gtd-drop-missing", S.wall_to_epoch(2026, 10, 20, 9, 0))
        job2 = w2.s.add_at("reminder", w2.clock.t + 100.0, "Buy milk",
                           context_bundle=bundle_in)
    finally:
        S._scrubber = real
    check("a missing scrubber leaves the same plain boolean",
          w2.s.bundle(job2["id"]) == {S.CONTEXT_DROPPED: True}
          and w2.s.job(job2["id"]).get(S.CONTEXT_DROPPED) is True,
          w2.s.job(job2["id"]))

    # A snoozed copy keeps the breadcrumb (a new row, with no words to copy).
    snoozed = S.snooze_reminder(job["id"], "1h", now=w.clock.t + 5.0, scheduler=w.s)
    check("a snoozed copy keeps the plain boolean on the new row",
          bool(snoozed.get("ok"))
          and w.s.bundle(snoozed["snoozed_id"]) == {S.CONTEXT_DROPPED: True},
          snoozed)

    # A scrubber that WORKS leaves no breadcrumb at all.
    w3 = _gtd_world("gtd-drop-clean", S.wall_to_epoch(2026, 10, 20, 9, 0))
    job3 = w3.s.add_at("reminder", w3.clock.t + 100.0, "Buy milk",
                       context_bundle={"source_summary": "we spoke about milk"})
    stored3 = w3.s.bundle(job3["id"])
    check("a scrubbed packet stores no breadcrumb",
          S.CONTEXT_DROPPED not in stored3 and stored3.get("source_summary"),
          stored3)
    check("... and its view says it HAS context, not that it was dropped",
          w3.s.job(job3["id"]).get("has_context") is True
          and S.CONTEXT_DROPPED not in w3.s.job(job3["id"]),
          w3.s.job(job3["id"]))


def t_gtd_legacy_context_row_reads_cleanly_without_the_flag():
    """A row written before the boolean existed has no key: it reads as an
    ordinary packet, with no invented breadcrumb and no error."""
    import sqlite3
    now = S.wall_to_epoch(2026, 10, 20, 9, 0)
    w = _gtd_world("gtd-legacy-context", now)
    job = _gtd_reminder(w, "Buy milk", context_bundle={
        "source_summary": "we spoke about milk", "linked_files": ["doc-9"]})
    con = sqlite3.connect(str(w.s.path))
    try:
        row = con.execute("SELECT context_bundle FROM jobs WHERE id = ?",
                          (job["id"],)).fetchone()[0]
        legacy = json.loads(row)
        legacy.pop(S.CONTEXT_DROPPED, None)      # as an older build wrote it
        con.execute("UPDATE jobs SET context_bundle = ? WHERE id = ?",
                    (json.dumps(legacy), job["id"]))
        con.commit()
    finally:
        con.close()
    view = w.s.job(job["id"])
    check("a legacy packet without the key still reads as context",
          view.get("has_context") is True and S.CONTEXT_DROPPED not in view, view)
    check("... and the bundle reads with no invented flag",
          S.CONTEXT_DROPPED not in w.s.bundle(job["id"])
          and w.s.bundle(job["id"]) != {}, w.s.bundle(job["id"]))
    latch, old = _fake_latch()
    try:
        out = S.enrich_and_check_condition(
            dict(view, context_bundle=w.s.bundle(job["id"])), readers={})
    finally:
        _restore_gate(old)
    check("... enrichment carries the words and no dropped flag",
          S.CONTEXT_DROPPED not in out and bool(out.get("context")), out)
    check("... and no secret is invented anywhere", "doc-9" in json.dumps(out["context"]),
          out)


def t_gtd_condition_target_is_a_name():
    """Privacy review F3/F4: the condition target is persisted and shown by
    every client; a path/address must be refused, and an old raw row must
    never be handed out."""
    import sqlite3
    now = S.wall_to_epoch(2026, 10, 20, 9, 0)
    w = _gtd_world("gtd-target", now)
    due = now + 100.0
    check("a path-shaped condition target is refused in words",
          _raises(ValueError, w.s.add_at, "reminder", due, "Reply to Sam",
                  condition_kind="no_email_reply_from",
                  condition_target="C:\\Users\\pcadmin\\secret.txt"))
    check("... and a web address too",
          _raises(ValueError, w.s.add_at, "reminder", due, "Reply to Sam",
                  condition_kind="no_email_reply_from",
                  condition_target="https://example.com/private"))
    safe = w.s.add_at("reminder", due, "Reply to Sam",
                      condition_kind="no_email_reply_from", condition_target="Sam")
    check("a plain name is kept and shown",
          w.s.job(safe["id"]).get("condition_target") == "Sam"
          and w.s.job(safe["id"]).get("condition_kind") == "no_email_reply_from")
    con = sqlite3.connect(w.s.path)
    con.execute("UPDATE jobs SET condition_target = ? WHERE id = ?",
                ("C:\\Users\\pcadmin\\secret.txt", safe["id"]))
    con.commit(); con.close()
    view = w.s.job(safe["id"])
    shown = json.dumps(w.s.status())
    check("a legacy path target is never handed out by job()",
          "condition_target" not in view, view)
    check("... nor by any listed/status payload", "C:\\\\Users" not in shown, shown)
    con = sqlite3.connect(w.s.path)
    con.execute("UPDATE jobs SET condition_kind = ? WHERE id = ?",
                ("C:\\Users\\pcadmin\\secret.txt", safe["id"]))
    con.commit(); con.close()
    view2 = w.s.job(safe["id"])
    check("... nor an unknown/raw condition kind",
          "condition_kind" not in view2
          and "C:\\\\Users" not in json.dumps(w.s.status()), view2)


def t_gtd_sensitive_bundle_blocks_the_breaker():
    """Privacy review F10: a bland title must not hide a sensitive packet."""
    now = S.wall_to_epoch(2026, 10, 20, 9, 0)
    w = _gtd_world("gtd-sensitive-packet", now)
    job = _gtd_reminder(w, "Buy milk", context_bundle={
        "source_summary": "my therapy appointment and diagnosis details"})
    out = None
    for _ in range(3):
        out = S.snooze_reminder(job["id"], "15m", now=now, scheduler=w.s,
                                micro_steps_opt_in=True)
    check("the packet is sensitive even though the title is bland",
          out["sensitive"] is True, out)
    check("... so three snoozes do NOT make it stuck", out["stuck_hint"] is False, out)
    check("... and it never gets the three-step breaker", out["micro_steps"] == [], out)


def t_gtd_pc_trigger_respects_due():
    """Privacy review F13: a PC-triggered reminder with a real due is not
    surfaced before that time; a next_pc_active copy (no due) still is."""
    now = S.wall_to_epoch(2026, 10, 20, 9, 0)
    w = _gtd_world("gtd-trigger-due", now)
    readers = {"session_unlocked": lambda: True, "app_locked": lambda: False,
               "idle_seconds": lambda: 5.0, "focus_active": lambda: False}
    future = _gtd_reminder(w, "Buy milk", trigger="on_pc_active")
    check("a future-due on_pc_active reminder is not ready",
          S.reminder_ready(w.s.job(future["id"]), now=now, readers=readers)[0]
          is False)
    check("... and is not surfaced as due",
          S.due_active_reminders(now=now, scheduler=w.s, readers=readers) == [])
    w.clock.t = now + 3601.0
    check("... and becomes ready once its due has passed",
          {j["id"] for j in S.due_active_reminders(
              now=w.clock.t, scheduler=w.s, readers=readers)} == {future["id"]})
    plain = _gtd_reminder(w, "Water the plants")
    res = S.snooze_reminder(plain["id"], "next_pc_active", now=w.clock.t,
                            scheduler=w.s)
    copy = w.s.job(res["snoozed_id"])
    check("a next_pc_active copy has no due and is eligible at activity",
          copy.get("due") is None
          and res["snoozed_id"] in [j["id"] for j in S.due_active_reminders(
              now=w.clock.t, scheduler=w.s, readers=readers)], copy)


def t_gtd_latch_covers_every_context_and_fails_closed():
    """Privacy review F6/F7: every returned private word counts as attached
    and latches exactly once; a latch that cannot be set withholds all of it."""
    now = S.wall_to_epoch(2026, 10, 20, 9, 0)
    w = _gtd_world("gtd-latch-all", now)
    base = dict(_gtd_reminder(w, "Buy milk"))
    for label, ctx in (
            ("entities-only", {"linked_entities": ["Sam"]}),
            ("files-only", {"linked_files": ["doc-7"]}),
            ("prompt-only", {"suggested_prompt": "Draft the reply"})):
        view = dict(base, context_bundle=ctx)
        latch, old = _fake_latch()
        try:
            out = S.enrich_and_check_condition(view)
        finally:
            _restore_gate(old)
        check(f"{label}: attached context counts as attached",
              out["context_attached"] is True, out)
        check(f"{label}: it latches exactly once",
              latch == ["reminder_context"], latch)
    import types
    mod = types.ModuleType("jarvis_gate")

    def boom(*, why=""):
        raise RuntimeError("gate down")
    mod.latch_taint = boom
    old = sys.modules.get("jarvis_gate")
    sys.modules["jarvis_gate"] = mod
    try:
        out = S.enrich_and_check_condition(dict(base, context_bundle={
            "source_summary": "Sam asked about the invoice"}))
    finally:
        if old is None:
            sys.modules.pop("jarvis_gate", None)
        else:
            sys.modules["jarvis_gate"] = old
    check("a failing latch withholds every private word",
          out["withheld"] is True and out["context"] == {} and out["facts"] == []
          and out["context_attached"] is False, out)
    check("... and says why in plain words",
          "privacy latch" in (out.get("error") or "").lower()
          and "withheld" in (out.get("error") or "").lower(), out.get("error"))


def t_gtd_snooze_resolves_the_original():
    """Privacy review F17: a snooze resolves the original one-off, so it cannot
    fire twice, and its packet is resolved with it."""
    now = S.wall_to_epoch(2026, 10, 20, 9, 0)
    w = _gtd_world("gtd-resolve", now)
    job = _gtd_reminder(w, "Buy milk", context_bundle={
        "source_summary": "we spoke about milk", "linked_files": ["doc-3"]})
    res = S.snooze_reminder(job["id"], "1h", now=now, scheduler=w.s)
    orig = w.s.job(job["id"])
    check("the original is resolved by its snooze",
          orig["state"] != "active" and orig.get("due") is None, orig)
    check("... and is not shown as having gone off", "fired_at" not in orig, orig)
    w.clock.t = now + 200.0
    check("... so it cannot fire a second time", w.s.tick() == [])
    copy = w.s.job(res["snoozed_id"])
    check("the copy is the only active reminder",
          copy["state"] == "active"
          and abs(copy["due"] - (now + 3600.0)) < 0.5, copy)
    w.clock.t = now + 3700.0
    check("... and it fires once", w.s.tick() == [res["snoozed_id"]])
    check("the original's packet is resolved and swept after seven days",
          S.expire_context_bundles(now=w.clock.t + 8 * 86400.0, scheduler=w.s) >= 1
          and w.s.bundle(job["id"]) == {})


def main():
    orig_tz = os.environ.get("TZ")
    try:
        for name, fn in list(globals().items()):
            if name.startswith("t_") and callable(fn):
                print(f"--- {name} ---")
                try:
                    fn()
                except Exception as exc:  # pragma: no cover
                    traceback.print_exc()
                    check(f"{name} ran without crashing", False, repr(exc))
    finally:
        if orig_tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = orig_tz
        if hasattr(time, "tzset"):
            time.tzset()
        S._audit = _real_audit
        shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
