"""test_attention_phrases.py - changing the interruption budget by asking.

    python3 backend/test_attention_phrases.py

Runs anywhere; no model, no network, no Windows Hello (where a raise needs the
approval gate, the test stands one in, exactly as
backend/test_attention_settings_route.py does).

"How much Jarvis may interrupt you" is a card in the Brain on the PC. The
audit of all 117 features (2026-10-08) found the owner could read it and change
it nowhere; the backend half is `jarvis_arbiter.set_spoken_per_day` /
`set_digest_hour`, and the route the two screens will use is
POST /api/attention/settings. This file is the THIRD way in, and the one that
needs no patch and no screen: asking Jarvis.

    "speak up 5 times a day"        -> that number
    "speak up less" / "speak up more" -> one step, that direction
    "the brief at 8pm"              -> when the digest arrives

What it proves:

1. The number is applied, and answered in plain words, for a tightening.
2. RAISING it does NOT slip through without the gate: with no gate reachable
   the request is refused and NOTHING is written - and with an approving gate
   it goes through, with a denying one it does not. Same rule as the route,
   because both call `jarvis_arbiter.change()`.
3. The digest hour converts the way people say it: "8pm" is 20, "7 in the
   morning" is 7, and the two the arithmetic gets wrong - 12am is midnight,
   12pm is noon - are right.
4. A sentence that only looks like one ("let jarvis speak", "speak up") is NOT
   a command, so it still goes to the model rather than picking a number.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402
require_shipped("jarvis_quick.py", "jarvis_arbiter.py", "jarvis_settings_registry.py",
                "jarvis_asks_first.py", "jarvis_owner_check.py", "jarvis_schedule.py")
sys.path.append(str(HERE / "rebuilt"))

TMP = Path(tempfile.mkdtemp(prefix="jarvis-attention-phrases-"))
os.environ["JARVIS_FRAMEWORK_TOML"] = str(TMP / "jarvis-framework.toml")
os.environ["OPENJARVIS_CONFIG_DIR"] = str(TMP)
os.environ["JARVIS_CONFIG_DIR"] = str(TMP)
os.environ["JARVIS_ARBITER_DB"] = str(TMP / "arbiter.db")

import jarvis_arbiter as AR  # noqa: E402
import jarvis_quick as Q  # noqa: E402

SHIPPED = REPO / "backend" / "rebuilt" / "jarvis-framework.toml"
FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


class Verdict:
    def __init__(self, allowed, outcome, tier="ask"):
        self.allowed, self.outcome, self.tier = allowed, outcome, tier


def fresh():
    shutil.copyfile(SHIPPED, TMP / "jarvis-framework.toml")
    AR._reload()


def ask(text, *, peer=None):
    body = {"messages": [{"role": "user", "content": text, "provenance": "typed"}]}
    return Q.answer_turn(body, now=time.time(), peer=peer, local="127.0.0.1")


def says(r) -> str:
    return str(getattr(r, "reply", "") or "")


# --------------------------------------------------------------------------


def t_turning_it_down_is_applied_and_answered_in_plain_words():
    fresh()
    AR.configure(gate=None, tier_of=None)
    check("the shipped budget is 3", AR._limit() == 3, AR._limit())
    r = ask("speak up 1 time a day")
    check("the sentence is recognised as a setting, not a question",
          r is not None and says(r), r)
    check("the budget really moved", AR._limit() == 1, AR._limit())
    check("and the answer says the number in words",
          "1 times a day" in says(r), says(r))
    check("nothing in the answer leaks a setting key or an underscore",
          "spoken_per_day" not in says(r) and "_" not in says(r), says(r))
    r0 = ask("speak up 0 times a day")
    check("zero is allowed, and says what it means",
          AR._limit() == 0 and "not speak up" in says(r0), (AR._limit(), says(r0)))


def t_a_raise_cannot_slip_through_without_the_gate():
    fresh()
    AR.configure(gate=None, tier_of=None)
    r = ask("speak up 6 times a day")
    check("with no gate reachable, the raise is refused", AR._limit() == 3, AR._limit())
    # BOTH WORDINGS COUNT (corrected 2026-10-09). Which one the owner sees
    # depends on the machine, not on the feature:
    #   * with no settings file to write, the module refuses with
    #     "...so nothing was changed";
    #   * on the owner's PC a real `jarvis_gate` is importable, so the raise
    #     becomes a card, and an unanswered card answers "The card was not
    #     answered in time, so Jarvis still speaks up to 3 times a day."
    # Both report the same thing - the budget did not move - and the check above
    # already proves it did not. Requiring only the first made this suite pass in
    # CI and fail on the one PC it exists to check.
    check("and refused in plain words that say nothing was changed",
          "nothing was changed" in says(r) or "still speaks up to" in says(r),
          says(r))

    fresh()
    AR.configure(gate=lambda action, detail, prompt: Verdict(True, "approved"),
                 tier_of=lambda action: "ask")
    r = ask("speak up 6 times a day")
    check("an approved card lets it through", AR._limit() == 6, AR._limit())
    check("and the answer says so", "6 times a day" in says(r), says(r))

    fresh()
    AR.configure(gate=lambda action, detail, prompt: Verdict(False, "denied"),
                 tier_of=lambda action: "ask")
    r = ask("speak up 9 times a day")
    check("a denied card leaves the budget alone", AR._limit() == 3, AR._limit())
    check("and the answer says why, in plain words",
          "You said no" in says(r), says(r))
    fresh()
    AR.configure(gate=None, tier_of=None)


def t_speak_up_less_and_more_are_one_step():
    fresh()
    AR.configure(gate=None, tier_of=None)
    ask("speak up less")
    check("'speak up less' takes one off the budget", AR._limit() == 2, AR._limit())
    ask("speak up less")
    ask("speak up less")
    check("it stops at zero rather than going negative", AR._limit() == 0, AR._limit())
    AR.configure(gate=lambda action, detail, prompt: Verdict(True, "approved"),
                 tier_of=lambda action: "ask")
    ask("speak up more")
    check("'speak up more' adds one back, through the card", AR._limit() == 1, AR._limit())
    fresh()
    AR.configure(gate=None, tier_of=None)


def t_the_brief_hour_is_read_the_way_people_say_it():
    fresh()
    AR.configure(gate=None, tier_of=None)
    for text, hour, why in (("the brief at 8pm", 20, "8pm is the evening"),
                            ("the digest arrives at 7 in the morning", 7, "7 in the morning"),
                            ("the brief at 12am", 0, "12am is midnight"),
                            ("the brief at 12pm", 12, "12pm is noon"),
                            ("the brief at 20", 20, "a 24-hour hour is taken as it is")):
        r = ask(text)
        check(f"{why}: {text!r} -> {hour}", AR._digest_hour() == hour,
              (text, AR._digest_hour()))
        check(f"{why}: and the answer names the time",
              f"{hour:02d}:00" in says(r), says(r))
    check("moving the brief never touches how often Jarvis speaks",
          AR._limit() == 3, AR._limit())


def t_only_whole_sentences_count():
    fresh()
    AR.configure(gate=None, tier_of=None)
    for text in ("let jarvis speak", "speak up", "the brief", "speak up sometimes",
                 "speak up a lot", "the brief at some point"):
        check(f"{text!r} is not treated as a setting",
              not Q.is_command(text), text)
    check("and the budget was not touched by any of them", AR._limit() == 3, AR._limit())


def main():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("t_") and callable(v)]
    for t in tests:
        print(f"--- {t.__name__} ---")
        t()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("\nFAILED:")
        for f in FAILED:
            print(f"  {f}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
