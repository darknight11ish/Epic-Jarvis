#!/usr/bin/env python3
"""Reminders, alarms and timers honesty (2026-10-31).

The owner asked "can you make a reminder for me" and the model said it could
not set a system-wide alarm and could only note reminders in a calendar; asked
"make a reminder for 30 minutes from now to check my phone" it offered a
calendar event. Both are false: jarvis_schedule.py keeps timers, alarms and
reminders on the PC (no card for a one-off), the desktop shows a Windows
notification while it runs (brain/schedule.rs toast_fired, rings()), and the
phone shows an Android notification while connected (ScheduleNotifier.kt - the
PC is the clock).

This suite pins: the relative-time parser forms, the exact computed time, the
capability answers, capability-vs-real-request separation, and the prompt/catalogue
truth. A stub scheduler is enough; no model is called.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import jarvis_quick as Q  # noqa: E402
import jarvis_schedule as S  # noqa: E402

PASSED, FAILED = [], []
NOW = 1793505565.0


class Sched:
    """Records what the quick path asks the real scheduler to add."""

    def __init__(self):
        self.calls = []

    def mark_command(self, text):
        pass

    def note_set(self, *a, **k):
        pass

    def last_set(self, *a, **k):
        return None

    def add_at(self, kind, at, text="", source="quick", **k):
        self.calls.append(("at", kind, at, text))
        return {"id": "s1", "kind": kind, "due": at, "text": text}

    def add_timer(self, seconds, label="", source="quick", **k):
        self.calls.append(("timer", seconds, label))
        return {"id": "s2", "kind": "timer", "due": NOW + seconds}


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def ask(text, surface="hud"):
    sched = Sched()
    r = Q.answer(text, sched=sched, now=NOW, peer="127.0.0.1", local=True,
                 client_surface=surface)
    return r, sched


def test_relative_reminders_parse_and_compute():
    cases = (
        ("make a reminder for 30 minutes from now to check my phone", 1800, "check my phone"),
        ("remind me in 30 minutes to check my phone", 1800, "check my phone"),
        ("remind me 30 minutes from now", 1800, "your reminder"),
        ("in 20 minutes remind me to check my phone", 1200, "check my phone"),
        ("set a reminder in an hour", 3600, "your reminder"),
        ("remind me in 2 hours", 7200, "your reminder"),
        ("at 6pm", None, "your reminder"),
        ("tomorrow at 9", None, "your reminder"),
    )
    for text, delta, expected_text in cases:
        r, sched = ask(text)
        check(f"{text!r} is the real reminder path",
              r is not None and r.intent == "reminder_set", r.intent if r else "model")
        check("... it added exactly one reminder, no card",
              len(sched.calls) == 1 and sched.calls[0][0] == "at" and sched.calls[0][1] == "reminder",
              str(sched.calls))
        if delta is not None:
            at = sched.calls[0][2] if sched.calls else 0
            check(f"... its time is now + {delta}s", abs(at - (NOW + delta)) < 1, str(at))
        got_text = sched.calls[0][3] if sched.calls else ""
        check(f"... its words are {expected_text!r}", got_text == expected_text, got_text)
    # boundaries 29/30/31 minutes
    for mins in (29, 30, 31):
        r, sched = ask(f"make a reminder for {mins} minutes from now to check")
        at = sched.calls[0][2] if sched.calls else 0
        check(f"{mins} minutes is {mins * 60}s", r is not None and abs(at - (NOW + mins * 60)) < 1,
              f"{at} vs {NOW + mins * 60}")


def test_bare_relative_is_a_timer_not_a_reminder():
    for text, seconds in (("in 10 minutes", 600), ("in half an hour", 1800)):
        r, sched = ask(text)
        check(f"{text!r} is the timer path", r is not None and r.intent == "timer_set",
              r.intent if r else "model")
        check("... one timer, no card",
              len(sched.calls) == 1 and sched.calls[0][0] == "timer" and sched.calls[0][1] == seconds,
              str(sched.calls))


def test_real_requests_are_not_stolen():
    for text in ("remind me to call Mom at 6pm", "set a timer for 10 minutes",
                 "set an alarm for 7am", "can you set a timer for 10 minutes"):
        r, _ = ask(text)
        check(f"real request stays its own path: {text!r}",
              r is not None and r.intent in ("reminder_set", "timer_set", "alarm_set"),
              r.intent if r else "model")
    r, _ = ask("put it in my calendar for 30 minutes from now")
    check("a calendar request stays calendar/model, never a reminder", r is None,
          r.intent if r else "model")
    r, _ = ask("remind me what we said")
    check("'remind me what we said' stays chat, not a reminder", r is None,
          r.intent if r else "model")


def test_capability_answers():
    prompts = (
        ("can you make a reminder for me?", "reminder_capability"),
        ("can you set a timer?", "reminder_capability"),
        ("can you set an alarm?", "reminder_capability"),
        ("will it pop up on my computer?", "reminder_popup"),
        ("will it ring?", "reminder_sound"),
        ("do you show a system notification?", "reminder_notify"),
        ("can you remind me even if the app is closed?", "reminder_closed"),
        ("how do I ask for one?", "reminder_howto"),
    )
    for text, intent in prompts:
        r, sched = ask(text)
        check(f"{text!r} is answered with no model",
              r is not None and r.intent == intent, r.intent if r else "model")
        reply = r.reply if r else ""
        check("... it does not deny reminders",
              "cannot" not in reply.lower() and "can't" not in reply.lower()
              and "calendar for you to check" not in reply.lower(), reply[:220])
        check("... no card and nothing added", sched.calls == [], str(sched.calls))
        check("... it names a true place or surface",
              any(word in reply.lower() for word in ("coming up", "windows notification", "android",
                                                     "reminder", "timer", "alarm")), reply[:220])


def test_phone_surface():
    r, _ = ask("can you make a reminder for me?", "phone")
    check("the phone answer names the PC as the clock",
          r is not None and "PC" in r.reply and ("connected" in r.reply or "phone" in r.reply),
          r.reply if r else "model")


def test_every_answer_is_read_only():
    for text in ("can you make a reminder for me?", "will it ring?",
                 "can you remind me even if the app is closed?", "how do I ask for one?"):
        r, _ = ask(text)
        check(f"{text!r} is in READ_ONLY_INTENTS",
              r is not None and r.intent in Q.READ_ONLY_INTENTS, r.intent if r else "model")


def test_system_prompt_line():
    mf = (ROOT / "backend" / "jarvis-primary.Modelfile").read_text(encoding="utf-8")
    m = re.search(r'SYSTEM """(.*?)"""', mf, re.S)
    text = m.group(1) if m else ""
    check("the Modelfile says the reminder capability is real",
          "really do keep timers, alarms, reminders" in text, "missing line")
    profiles = (ROOT / "backend" / "jarvis_profiles.py").read_text(encoding="utf-8")
    check("the tuned-model copy carries the same line", "really do keep timers" in profiles)
    line = next((ln for ln in text.splitlines() if "timers, alarms, reminders" in ln), "")
    check("the prompt line names the real surface and limits",
          "Windows notification" in line and "phone" in line and "closed" in line, line)
    check("the prompt line carries no token or secret",
          not re.search(r"token|secret|api[ _-]?key|Bearer", line, re.I), line)


def test_catalogue_row_carries_the_truth():
    rows = json.loads((ROOT / "features" / "features.json").read_text(encoding="utf-8"))
    by_id = {r["id"]: r for r in rows}
    row = by_id["coming-up"]
    text = " ".join(str(row.get(k) or "") for k in ("what", "where", "limit"))
    check("the Timers, alarms, reminders row names relative asks",
          "30 minutes from now" in text or "in 30 minutes" in text, text[:300])
    check("... and the true limit (10 minutes late, Windows notification, phone connected)",
          "10 minutes" in text and "Windows notification" in text and "connected" in text,
          text[:300])
    three = [(ROOT / p).read_bytes() for p in (
        "features/features.json", "jarvis-desktop/src/features.json",
        "jarvis-client/app/src/main/assets/features.json")]
    check("the three features.json copies are byte-identical", three[0] == three[1] == three[2])


def main():
    tests = [test_relative_reminders_parse_and_compute,
             test_bare_relative_is_a_timer_not_a_reminder,
             test_real_requests_are_not_stolen, test_capability_answers,
             test_phone_surface, test_every_answer_is_read_only,
             test_system_prompt_line, test_catalogue_row_carries_the_truth]
    for t in tests:
        print("\n-- " + t.__name__ + " " + "-" * 50)
        try:
            t()
        except Exception as exc:            # noqa: BLE001 - a crash is a failure
            check(t.__name__ + " ran", False, repr(exc))
    print("\n" + "=" * 74)
    print(f"PASS {len(PASSED)}  FAIL {len(FAILED)}  SKIP 0")
    for name in FAILED:
        print("  FAIL:", name)
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
