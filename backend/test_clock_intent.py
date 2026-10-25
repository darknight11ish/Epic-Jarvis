"""test_clock_intent.py - "what time is it?" and "what's the date?" answered
from THIS PC's own clock (D3, the live-tools campaign of 2026-10-25).

    python -B backend/test_clock_intent.py

WHY. Campaign row R13 asked "What time is it?" and waited 82.1 s for the 9B
model to answer "10:42 AM" while the PC's own clock read 20:16 - a wrong answer
to a question this machine knows exactly, for free, and the one question where
a model must never be involved.

WHAT THIS PROVES
  1. THE WHOLE QUESTION, AND NOTHING ELSE. The time/date/both wordings match
     their intents; a question that only MENTIONS a time - above all "what time
     is it in Tokyo?" (a timezone conversion this PC's clock cannot answer) -
     stays the model's, and "what time is my alarm set for" keeps the alarm path.
  2. THE ANSWER IS THIS PC'S CLOCK. It is computed from a fixed `now` with
     time.localtime, so this suite re-derives the same local hour:minute and day
     INDEPENDENTLY and compares. On a machine whose local time is behind UTC the
     answer must show the LOCAL hour, never the UTC one - the wrong-clock defect
     was exactly that (10:42 AM against a PC clock reading 20:16), and the
     24-hour form is what both apps show.
  3. NO MODEL, AND FAST. The real /api/chat entry (`answer_turn`, the function
     schedule.patch calls) answers in under a second and its route says
     `lane="no AI model"` / `where="local"` - a model round trip cannot fit that
     budget, and the route line is the contract both apps read.
  4. IT CHANGES NOTHING. No ids, no made jobs, no facts, not private: asking the
     clock is not an action and raises no card.

No model, no network, no real settings file: the scheduler and the config
folders are throwaway temp dirs, and nothing is written outside them.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-clock-intent-"))
os.environ["JARVIS_SCHEDULE_DB"] = str(_TMP / "schedule.db")
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["OPENJARVIS_HOME"] = str(_TMP / "home")
os.environ["JARVIS_HOME"] = str(_TMP / "home")
(_TMP / "config").mkdir(parents=True, exist_ok=True)
(_TMP / "home").mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_quick.py", "jarvis_schedule.py")
sys.path.insert(0, str(HERE / "rebuilt"))
import jarvis_quick as Q  # noqa: E402

PASSED, FAILED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    SKIPPED.append(why)
    print(f"skip  {why}")


#: A fixed PC-clock instant: 2026-09-21 07:13 LOCAL (the suite never types the
#: hour or the day twice; it derives them from time.localtime below).
NOW = 1790000000.0

TIME = ("what time is it", "what's the time", "what is the time",
        "what time is it now", "what time is it right now", "tell me the time",
        "current time")
DATE = ("what's the date", "what is the date", "what date is it",
        "what day is it", "what day is it today", "what's today's date",
        "today's date")
BOTH = ("what is the time and date", "what time and date is it")
CLOCK_INTENTS = ("time_now", "date_today", "clock_both")

_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
             "Saturday", "Sunday")
_MONTHS = ("January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December")


def _local_words(now):
    """(HH:MM, 'Monday 21 September 2026') by this PC's own local clock, written
    here independently of the module under test."""
    lt = time.localtime(now)
    return (f"{lt.tm_hour:02d}:{lt.tm_min:02d}",
            f"{_WEEKDAYS[lt.tm_wday]} {lt.tm_mday} {_MONTHS[lt.tm_mon - 1]} "
            f"{lt.tm_year}")


def t_the_clock_questions_match_their_intents():
    for phrase in TIME:
        got = Q.match(phrase, NOW)
        check(f"{phrase!r} -> time_now",
              got is not None and got.name == "time_now",
              None if got is None else got.name)
    for phrase in DATE:
        got = Q.match(phrase, NOW)
        check(f"{phrase!r} -> date_today",
              got is not None and got.name == "date_today",
              None if got is None else got.name)
    for phrase in BOTH:
        got = Q.match(phrase, NOW)
        check(f"{phrase!r} -> clock_both",
              got is not None and got.name == "clock_both",
              None if got is None else got.name)


def t_a_question_that_only_mentions_a_time_is_still_the_models():
    for phrase in ("what time is it in Tokyo", "what time is the meeting",
                   "what time is the meeting tomorrow", "what day is the meeting",
                   "what time does the shop open",
                   "how long does it take to boil an egg"):
        got = Q.match(phrase, NOW)
        check(f"{phrase!r} is not answered by the clock",
              got is None or got.name not in CLOCK_INTENTS,
              None if got is None else got.name)
    got = Q.match("what time is my alarm set for", NOW)
    check("'what time is my alarm set for' keeps the alarm path",
          got is not None and got.name == "alarm_list",
          None if got is None else got.name)


def t_the_time_answer_is_this_pcs_local_clock():
    hhmm, day = _local_words(NOW)
    res = Q.answer("what time is it", now=NOW)
    check("answered without the model (a Result, not None)", res is not None)
    if res is None:
        return
    check(f"the exact local hour and minute are in the answer ({hhmm})",
          hhmm in res.reply, res.reply)
    check(f"the PC's own day is in the answer ({day})", day in res.reply, res.reply)
    utc = time.strftime("%H:%M", time.gmtime(NOW))
    if utc != hhmm:
        check(f"...and it is LOCAL time, not UTC ({utc})", utc not in res.reply,
              res.reply)
    else:
        skip("local time equals UTC on this machine, so local-vs-UTC cannot differ")
    check("the 24-hour form is used (the wrong answer said 10:42 AM)",
          "AM" not in res.reply and "PM" not in res.reply, res.reply)
    later = Q.answer("what time is it", now=NOW + 3600)
    later_hhmm, _ = _local_words(NOW + 3600)
    check("an hour later the answer is an hour later",
          later is not None and later.reply != res.reply and later_hhmm in later.reply,
          None if later is None else later.reply)


def t_the_date_and_both_answers_are_the_pcs_own():
    _, day = _local_words(NOW)
    date = Q.answer("what's the date", now=NOW)
    check("'what's the date' gives the PC's own date",
          date is not None and date.intent == "date_today" and day in date.reply,
          None if date is None else (date.intent, date.reply))
    both = Q.answer("what is the time and date", now=NOW)
    hhmm, _ = _local_words(NOW)
    check("the both-at-once question carries both",
          both is not None and both.intent == "clock_both"
          and hhmm in both.reply and day in both.reply,
          None if both is None else (both.intent, both.reply))


def t_the_real_turn_path_is_no_model_and_under_a_second():
    body = {"messages": [{"role": "user", "content": "what time is it",
                          "provenance": "typed"}],
            "conversation_id": "clock-test-1"}
    t0 = time.perf_counter()
    res = Q.answer_turn(body, now=NOW)
    elapsed = time.perf_counter() - t0
    check("the real /api/chat entry answers this turn",
          res is not None and res.intent == "time_now",
          None if res is None else res.intent)
    check(f"...under a second ({elapsed:.3f} s) - a model round trip cannot fit",
          elapsed < 1.0, elapsed)
    if res is None:
        return
    route = Q.route_fields(res)
    check("the route says no AI model answered",
          route.get("lane") == "no AI model", route)
    check("...the answer was made on this PC", route.get("where") == "local", route)
    check("...and it names the clock intent for the apps",
          route.get("quick") == "time_now", route)
    check("...with no memory injected", route.get("inject_memory") is False, route)
    check("a clock question changes nothing: no jobs, no ids, not private",
          res.made == [] and res.ids == [] and res.private is False
          and not res.facts, res)


def main():
    try:
        for name, fn in list(globals().items()):
            if name.startswith("t_") and callable(fn):
                print(f"--- {name} ---")
                try:
                    fn()
                except Exception:  # noqa: BLE001
                    traceback.print_exc()
                    check(f"{name} ran without crashing", False)
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed, {len(SKIPPED)} skipped")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
