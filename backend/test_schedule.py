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
    form, no "delete all";
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
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-schedule-"))


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


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
        return check("SKIP - no time.tzset here (Windows); the rules are the same", True)
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
        return check("SKIP - no time.tzset here", True)
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


def t_one_card_for_a_repeat_none_for_a_one_off():
    use_tz("Europe/London")
    now = local(2026, 9, 25, 12, 0)            # Friday
    w = World(now, name="card")
    w.s.add_timer(60)
    w.s.add_at("alarm", now + 3600)
    w.s.add_at("reminder", now + 7200, "call the bank")
    w.s.add_todo("milk")
    check("a timer, a one-off alarm, a one-off reminder and a to-do raise no card", w.cards == [])
    j = w.s.add_repeat("reminder", {"every": "weekday", "at": "07:00"}, "take my pills")
    check("a repeat raises ONE card", len(w.cards) == 1)
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
        j2 = w2.s.add_repeat("alarm", {"every": "day", "at": "06:30"})
        check(f"{answer}: nothing is set up, and it is off the list",
              w2.s.job(j2["id"]) is None and w2.s.listed() == [])
    w3 = World(now, tier="auto", name="auto")
    j3 = w3.s.add_repeat("alarm", {"every": "day", "at": "06:30"})
    check("tier \"auto\" in the settings is refused without asking - a config line is not a yes",
          w3.cards == [] and w3.s.job(j3["id"]) is None)

    class Late(World):
        def gate(self, action, detail, prompt):
            # The owner deletes it while the card is up, then approves.
            self.s.act(detail["job"], "delete")
            return Verdict(True, "ask", "approved")
    w4 = Late(now, name="late")
    j4 = w4.s.add_repeat("alarm", {"every": "day", "at": "06:30"})
    check("deleted while the card waited: approving it sets nothing up",
          w4.s.job(j4["id"]) is None and w4.s.last_card.get(j4["id"]) == "withdrawn")

    class Liar(World):
        def gate(self, action, detail, prompt):
            return Verdict(True, "auto", "approved")
    w5 = Liar(now, name="liar")
    j5 = w5.s.add_repeat("alarm", {"every": "day", "at": "06:30"})
    check("allowed at tier \"auto\" is not a person saying yes: refused",
          w5.s.job(j5["id"]) is None)
    w6 = World(now, answer="denied", name="waiting")
    w6.answer = "approved"
    w6.s._spawn = lambda fn: None          # the card is still up
    j6 = w6.s.add_repeat("reminder", {"every": "day", "at": "08:00"}, "stretch")
    v6 = w6.s.job(j6["id"])
    check("while the card waits it is listed as waiting, with its next three times, and "
          "nothing goes off", v6["state"] == "waiting" and len(v6["next"]) == 3
          and w6.s.tick(now + 30 * 86400) == [])

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
    check("a repeat says a card is up and nothing is set until the card is approved",
          "approval card" in r.reply and "Nothing is set up until you approve the card" in r.reply
          and "say yes" not in r.reply
          and len(w.cards) == 1, r.reply)
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
        return check("SKIP - git is not installed", True)
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
        check("the answer is Ollama's SSE shape, then [DONE]",
              h.headers.get("Content-Type") == "text/event-stream"
              and b'"content":"Timer set for 10 minutes."' in h.out
              and h.out.endswith(b"data: [DONE]\n\n"), h.out[:300])
        check("this PC's record of the turn gets the answer (for chat history)",
              hist["turn"]["answer"] == "Timer set for 10 minutes."
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
              and json.loads(h2.out)["choices"][0]["message"]["content"].startswith("Reminder set"))
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
        check("set_reminder repeating: ONE card, from the scheduler, action schedule_repeat",
              [c[0] for c in w.cards] == ["schedule_repeat"] and gated == [], (w.cards, gated))
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
        return check("SKIP - git is not installed", True)
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
        check("add a repeat: 202, waiting on a card", code == 202 and out["waiting"] is True)
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
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
