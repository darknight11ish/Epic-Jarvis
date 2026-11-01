#!/usr/bin/env python3
"""Goals honesty (2026-10-31): the goals plugin is real; the answers say so.

Live Jarvis said "I don't have a built-in goal-tracking system that updates
automatically". False: plugins/ready/goals + backend/jarvis_goals.py keep goals
on this PC. This suite pins the fast-path answers to a fake goals list, the
module's real limits, and the catalogue/prompt truth.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import jarvis_quick as Q  # noqa: E402
import jarvis_goals as G  # noqa: E402

PASSED, FAILED = [], []
ROWS = [{"text": "run a marathon", "status": "active"},
        {"text": "read twelve books", "status": "active"}]


class Stub:
    def mark_command(self, text):
        pass

    def note_set(self, *a, **k):
        pass

    def last_set(self, *a, **k):
        return None


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def ask(text, surface="hud"):
    return Q.answer(text, sched=Stub(), now=1793505565.0, peer="127.0.0.1", local=True,
                    client_surface=surface)


def test_source_truth():
    check("the goals module keeps a short plan cap", getattr(G, "MAX_STEPS", 7) == 7,
          str(getattr(G, "MAX_STEPS", None)))
    check("the goals plugin is a real drop-in folder",
          (ROOT / "plugins/ready/goals/plugin.json").is_file())
    check("the catalogue row is goals", any(r["id"] == "goals"
          for r in json.loads((ROOT / "features/features.json").read_text(encoding="utf-8"))))


def test_capability_and_list():
    Q._goal_rows = lambda: ROWS
    try:
        for text in ("can you keep track of goals for me?", "do you have a built-in goal tracker?",
                     "can you track goals?"):
            r = ask(text)
            check(f"{text!r} is answered", r is not None and r.intent == "goal_capability",
                  r.intent if r else "model")
            reply = r.reply if r else ""
            check("... it says goals are real on the PC", "Yes" in reply and "Brain, Work, Goals" in reply,
                  reply[:220])
            check("... it does NOT repeat the old denial",
                  "don't have a built-in goal" not in reply.lower()
                  and "no goal-tracking" not in reply.lower(), reply[:220])
            check("... it states the no-silent-progress limit",
                  "not tracked automatically" in reply.lower() or "nothing ticks" in reply.lower(),
                  reply[:400])
        r = ask("what goals am I working on?")
        check("the goal list reads the real store",
              r is not None and r.intent == "goal_list" and "run a marathon" in r.reply
              and "read twelve books" in r.reply, r.reply if r else "model")
        r = ask("do I have a goal about marathon?")
        check("a named goal is found", r is not None and r.intent == "goal_state"
              and "marathon" in r.reply and "Yes" in r.reply, r.reply if r else "model")
        r = ask("is losing weight one of my goals?")
        check("an unknown goal is refused honestly", r is not None and r.intent == "goal_state"
              and "don't see a goal" in r.reply, r.reply if r else "model")
        r = ask("how do I add a goal?")
        check("adding/updating is explained", r is not None and r.intent == "goal_update"
              and "Brain, Work, Goals" in r.reply, r.reply if r else "model")
        r = ask("what does the goals feature do?")
        check("the feature explanation names the card rule", r is not None and r.intent == "goal_about"
              and "one" in r.reply.lower() and "card" in r.reply.lower(), r.reply if r else "model")
    finally:
        Q._goal_rows = _ORIG_ROWS


def test_empty_and_phone():
    Q._goal_rows = lambda: []
    try:
        r = ask("what goals am I working on?")
        check("an empty store says so", r is not None and "no goals" in r.reply.lower(),
              r.reply if r else "model")
    finally:
        Q._goal_rows = _ORIG_ROWS
    Q._goal_rows = lambda: ROWS
    try:
        r = ask("can you keep track of goals for me?", "phone")
        check("the phone answer says goals are on the PC", r is not None and "PC" in r.reply,
              r.reply if r else "model")
    finally:
        Q._goal_rows = _ORIG_ROWS


def test_over_capture():
    for text in ("what are the company goals?", "track my package", "what are the goals of this game?",
                 "track my spending", "can you track my sleep?"):
        r = Q.match(text)
        check(f"not a Jarvis goal-tracking question: {text!r}",
              r is None or not str(r.name).startswith("goal_"), r.name if r else "model")


def test_prompt_and_catalogue():
    mf = (ROOT / "backend" / "jarvis-primary.Modelfile").read_text(encoding="utf-8")
    m = re.search(r'SYSTEM """(.*?)"""', mf, re.S)
    text = m.group(1) if m else ""
    check("the Modelfile says goal tracking is real", "keep track of goals on this PC" in text)
    profiles = (ROOT / "backend" / "jarvis_profiles.py").read_text(encoding="utf-8")
    check("the tuned-model copy carries the same line", "keep track of goals on this PC" in profiles)
    line = next((ln for ln in text.splitlines() if "keep track of goals" in ln), "")
    check("the prompt line names the place, the card rule and the no-silent limit",
          "Brain, Work, Goals" in line and "card" in line and "silently" in line, line)
    rows = json.loads((ROOT / "features/features.json").read_text(encoding="utf-8"))
    row = next(r for r in rows if r["id"] == "goals")
    joined = " ".join(str(row.get(k) or "") for k in ("what", "where", "asks", "limit"))
    check("the catalogue row carries the real state and limits",
          "9 steps" in joined and "automatic" in joined and "card" in joined, joined[:300])
    check("the three features.json copies are byte-identical", 
          len({(ROOT / p).read_bytes() for p in ("features/features.json",
                                                  "jarvis-desktop/src/features.json",
                                                  "jarvis-client/app/src/main/assets/features.json")}) == 1)


_ORIG_ROWS = Q._goal_rows


def main():
    tests = [test_source_truth, test_capability_and_list, test_empty_and_phone,
             test_over_capture, test_prompt_and_catalogue]
    for t in tests:
        print("\n-- " + t.__name__ + " " + "-" * 50)
        try:
            t()
        except Exception as exc:            # noqa: BLE001
            check(t.__name__ + " ran", False, repr(exc))
    print("\n" + "=" * 74)
    print(f"PASS {len(PASSED)}  FAIL {len(FAILED)}  SKIP 0")
    for name in FAILED:
        print("  FAIL:", name)
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
