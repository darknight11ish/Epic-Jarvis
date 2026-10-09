"""test_attention_settings_route.py - changing the interruption budget: the
route the two apps call, and the card that raising it needs.

    python3 backend/test_attention_settings_route.py

Runs anywhere; no model, no network, no Windows Hello (the approval gate is
stood in for, exactly as backend/test_chatbot_limits.py stands in for it).

The rule this file exists to hold (the owner's, from every other setting):
**turning something DOWN is immediate and asks nothing; turning it UP is a
loosening and waits for one approval card.** For this setting "down" means
Jarvis speaks up less often, and "up" means more often - and which one a
request is comes from the NUMBER against the budget already in force, never
from anything the caller sends. The money limits had exactly this hole once
(a `lower` label carrying a bigger number walked straight past the card; bug
audit 2026-10-07, finding E2), so it is tested here rather than rediscovered:

1. Lowering the budget, and moving the digest hour, write at once with NO card.
2. Raising it calls the gate with `raise_attention_budget`, and NOTHING is
   written until a person approves.
3. A denied card, a timed-out card, a tier that is not "ask", and a gate that
   cannot be reached each leave the file byte-for-byte as it was.
4. Nonsense - not a number, out of range, two settings at once, an unknown
   route - is refused before any card is raised.
5. The budget the readers use (`_limit()`, `budget()`) is the new one after a
   change, and the old one after a refusal.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402
require_shipped("jarvis_arbiter.py", "jarvis_framework.py")
sys.path.append(str(HERE / "rebuilt"))

TMP = Path(tempfile.mkdtemp(prefix="jarvis-attention-route-"))
os.environ["JARVIS_FRAMEWORK_TOML"] = str(TMP / "jarvis-framework.toml")
os.environ["OPENJARVIS_CONFIG_DIR"] = str(TMP)
os.environ["JARVIS_CONFIG_DIR"] = str(TMP)
os.environ["JARVIS_ARBITER_DB"] = str(TMP / "arbiter.db")

import jarvis_arbiter as A  # noqa: E402

SHIPPED = REPO / "backend" / "rebuilt" / "jarvis-framework.toml"
FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


class Verdict:
    """What jarvis_gate.check() hands back, in the fields this module reads."""

    def __init__(self, allowed, outcome, tier="ask"):
        self.allowed, self.outcome, self.tier = allowed, outcome, tier


class Gate:
    """Stands in for jarvis_gate: records what it was asked, answers what the
    test tells it to."""

    def __init__(self, verdict=None, raises=False):
        self.asked, self.verdict, self.raises = [], verdict, raises

    def __call__(self, action, detail, prompt):
        self.asked.append({"action": action, "detail": detail, "prompt": prompt})
        if self.raises:
            raise RuntimeError("the gate is not reachable")
        return self.verdict or Verdict(True, "approved")


def fresh() -> Path:
    p = TMP / "jarvis-framework.toml"
    shutil.copyfile(SHIPPED, p)
    A._reload()
    return p


def reset(gate=None, tier="ask"):
    A.configure(gate=gate, tier_of=lambda action: tier)
    return gate


# --------------------------------------------------------------------------


def t_lowering_the_budget_writes_at_once_with_no_card():
    fresh()
    g = reset(Gate())
    check("the shipped budget is 3", A._limit() == 3, A._limit())
    code, out = A.handle_post("/api/attention/settings", {"spoken_per_day": 1})
    check("lowering answers 200", code == 200, (code, out))
    check("lowering asks nothing - no card, no gate call", g.asked == [], g.asked)
    check("lowering is not called a loosening", out.get("loosening") is False, out)
    check("and the new budget is the one the readers use", A._limit() == 1, A._limit())
    check("the answer says so in the owner's words", "1 times a day" in out.get("said", ""),
          out.get("said"))


def t_the_digest_hour_never_asks_either_way():
    fresh()
    g = reset(Gate())
    code, out = A.handle_post("/api/attention/settings", {"digest_hour": 20})
    check("the digest hour answers 200", code == 200, (code, out))
    check("it never raises a card", g.asked == [], g.asked)
    check("even moving it later is not a loosening", out.get("loosening") is False, out)
    check("and the reader sees it", A._digest_hour() == 20, A._digest_hour())
    check("the answer names the time in the owner's words", "20:00" in out.get("said", ""),
          out.get("said"))


def t_raising_the_budget_needs_a_card_and_waits_for_it():
    p = fresh()
    before = p.read_bytes()
    g = reset(Gate(Verdict(True, "approved")))
    code, out = A.handle_post("/api/attention/settings", {"spoken_per_day": 6})
    check("raising answers 200 once it is approved", code == 200, (code, out))
    check("it went through the gate", len(g.asked) == 1, g.asked)
    check("asked as the raise action, not as a tightening",
          g.asked and g.asked[0]["action"] == A.RAISE_ACTION, g.asked)
    check("the card says what it is about, in the owner's words",
          g.asked and "6 times a day" in g.asked[0]["prompt"]
          and "3" in g.asked[0]["prompt"], g.asked)
    check("the card says it does NOT leave the PC",
          g.asked and g.asked[0]["detail"].get("leaves_this_pc") is False, g.asked)
    check("the answer marks it a loosening AND approved",
          out.get("loosening") is True and out.get("approved") is True, out)
    check("and the budget really moved", A._limit() == 6, A._limit())


def t_every_refusal_leaves_the_file_exactly_as_it_was():
    cases = [
        ("a denied card", Gate(Verdict(False, "denied")), "ask", 6, "times a day"),
        ("a card that timed out", Gate(Verdict(False, "timed_out")), "ask", 6, "times a day"),
        # These two never reached the owner at all, so the words are about the
        # card, not about the budget: the budget was not the thing that failed.
        ("a PC whose Jarvis cannot ask", Gate(Verdict(True, "approved")), "auto", 6,
         "nothing was changed"),
        ("a gate that cannot be reached", Gate(raises=True), "ask", 6,
         "nothing was changed"),
    ]
    for why, gate, tier, want, words in cases:
        p = fresh()
        before = p.read_bytes()
        reset(gate, tier)
        code, out = A.handle_post("/api/attention/settings", {"spoken_per_day": want})
        check(f"{why}: refused with a code, not applied", code >= 400, (code, out))
        check(f"{why}: the file was not written", p.read_bytes() == before)
        check(f"{why}: the budget is still the old one", A._limit() == 3, A._limit())
        check(f"{why}: and the answer says so in plain words",
              words in str(out.get("error")), out)
    # The words differ by outcome, which is the difference between the owner
    # saying no and never seeing the card.
    fresh()
    reset(Gate(Verdict(False, "denied")))
    _, denied = A.handle_post("/api/attention/settings", {"spoken_per_day": 9})
    fresh()
    reset(Gate(Verdict(False, "timed_out")))
    _, timed_out = A.handle_post("/api/attention/settings", {"spoken_per_day": 9})
    check("saying no and not answering are told apart",
          denied.get("error") != timed_out.get("error"),
          (denied.get("error"), timed_out.get("error")))


def t_the_number_decides_the_direction_not_the_caller():
    """The money limits' own bug (E2), which this module is written without."""
    fresh()
    g = reset(Gate(Verdict(True, "approved")))
    # Calling a plain set "lower" changes nothing about the direction: 9 > 3.
    code, out = A.handle_post("/api/attention/settings", {"spoken_per_day": 9})
    check("a bigger number is a raise even when nothing says 'raise'",
          len(g.asked) == 1 and code == 200, (g.asked, code))
    # And once it IS the budget, the same number asks nothing at all.
    g2 = Gate(Verdict(True, "approved"))
    reset(g2)
    code2, out2 = A.handle_post("/api/attention/settings", {"spoken_per_day": 9})
    check("a number equal to the budget asks nothing", g2.asked == [], g2.asked)
    check("and is not called a loosening", out2.get("loosening") is False, out2)
    # A smaller number after a raise is a tightening again.
    g3 = Gate(Verdict(True, "approved"))
    reset(g3)
    code3, out3 = A.handle_post("/api/attention/settings", {"spoken_per_day": 2})
    check("a smaller number tightens, with no card", g3.asked == [] and code3 == 200,
          (g3.asked, code3))
    check("and is reported as a tightening", out3.get("loosening") is False, out3)


def t_nonsense_is_refused_before_any_card_is_raised():
    fresh()
    g = reset(Gate(Verdict(True, "approved")))
    for body, why in (({"spoken_per_day": 99}, "above the range"),
                      ({"spoken_per_day": -1}, "below it"),
                      ({"spoken_per_day": "lots"}, "not a number"),
                      ({"spoken_per_day": None}, "nothing at all"),
                      ({"digest_hour": 24}, "an hour the day does not have"),
                      ({}, "no setting named"),
                      ({"spoken_per_day": 4, "digest_hour": 9}, "two settings at once"),
                      ({"nonsense": 1}, "a setting that does not exist")):
        p = TMP / "jarvis-framework.toml"
        before = p.read_bytes()
        code, out = A.handle_post("/api/attention/settings", body)
        check(f"{why}: refused with 400", code == 400, (code, out))
        check(f"{why}: no card was raised", g.asked == [], g.asked)
        check(f"{why}: nothing was written", p.read_bytes() == before)
        check(f"{why}: and the owner is told in plain words",
              bool(out.get("error")), out)
    code, out = A.handle_post("/api/attention/unmute", {"spoken_per_day": 4})
    check("a route this module does not own is a 404", code == 404, (code, out))


def t_budget_reports_what_the_screens_show_after_a_change():
    fresh()
    reset(Gate(Verdict(True, "approved")))
    A.handle_post("/api/attention/settings", {"spoken_per_day": 4})
    b = A.budget()
    check("budget() carries the new number to both screens", b.get("limit") == 4, b)


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
