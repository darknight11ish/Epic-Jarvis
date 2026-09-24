"""test_learning_switch.py - turning learning ON raises a card; OFF is instant.

Run: python3 backend/test_learning_switch.py
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jarvis_learning_switch as L  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


class V:
    def __init__(self, outcome, allowed=None, tier="ask"):
        self.outcome, self.tier = outcome, tier
        self.allowed = (outcome == "approved") if allowed is None else allowed
        self.reason = outcome


class World:
    def __init__(self, verdict=None, tier="ask"):
        L._reset_for_tests()
        self.applied, self.cards, self.later = [], [], []
        self.verdict, self.tier = verdict or V("approved"), tier

    def apply(self, on):
        self.applied.append(on)
        return {"ok": True, "enabled": on}

    def gate(self, action, detail, prompt):
        self.cards.append((action, detail))
        return self.verdict

    def tier_of(self, action):
        return self.tier

    def req(self, enabled):
        return L.request(enabled, self.apply, gate=self.gate, tier_of=self.tier_of,
                         spawn=self.later.append)

    def run_card(self):
        for fn in list(self.later):
            fn()
        self.later.clear()


def t_on_asks_and_off_is_instant():
    w = World()
    code, out = w.req(True)
    check("ON answers 202 waiting and changes nothing yet",
          code == 202 and out["waiting"] and out["enabled"] is False and w.applied == [], out)
    check("the card is raised under learning_enable, and says nothing leaves",
          not w.cards and len(w.later) == 1)
    w.run_card()
    check("approved: learning is turned on, once",
          w.applied == [True] and w.cards[0][0] == "learning_enable"
          and w.cards[0][1]["leaves_this_pc"] is False, (w.applied, w.cards))
    check("status: not waiting, last card enabled",
          L.state()["waiting"] is False and L.state()["last"]["outcome"] == "enabled")
    code, out = w.req(False)
    check("OFF: immediate, no card", code == 200 and w.applied == [True, False]
          and len(w.cards) == 1 and out["waiting"] is False, out)


def t_no_yes_changes_nothing():
    for outcome in ("denied", "timed_out", "refused"):
        w = World(V(outcome))
        w.req(True)
        w.run_card()
        check(f"{outcome}: learning stays off", w.applied == []
              and L.state()["last"]["outcome"] == outcome, L.state())
    w = World(V("approved", tier="auto"))
    w.req(True)
    w.run_card()
    check("a gate that answered at tier auto is not a person saying yes",
          w.applied == [] and L.state()["last"]["outcome"] == "refused")


def t_the_toml_cannot_make_it_automatic():
    for tier in ("auto", "notify", "never", "unreadable (KeyError)"):
        w = World(tier=tier)
        code, out = w.req(True)
        check(f"tier {tier!r}: 503, no card, nothing applied",
              code == 503 and not w.later and w.applied == [] and "must be 'ask'" in out["error"],
              out)


def t_off_while_waiting_withdraws_it():
    w = World()
    w.req(True)
    w.req(False)
    w.run_card()
    check("turned off while the card waited: the approval does not turn it on",
          w.applied == [False] and L.state()["last"]["outcome"] == "withdrawn", w.applied)


def t_one_card_at_a_time():
    w = World()
    w.req(True)
    code, out = w.req(True)
    check("a second ON while one waits: no second card", code == 202 and len(w.later) == 1
          and "already waiting" in out["message"], out)


def t_the_patch():
    """learning-asks.patch, applied as apply-patches.ps1 applies the whole
    stack: the route answers through this module, and the old line that
    switched learning on with no card is gone."""
    import _stack
    names = [str(p).replace("\\", "/").split("/")[-1] for p in _stack.order()]
    check("learning-asks.patch is in apply-patches.ps1's order, after memory-pane",
          "learning-asks.patch" in names
          and names.index("learning-asks.patch") > names.index("memory-pane.patch"), names[-4:])
    text, log = _stack.stand_in("jarvis_hud.py")
    check("the whole stack builds", text is not None, "\n".join(log or [])[-500:])
    if text is None:
        return
    route = text[text.index('if route == "/api/memory/learning":'):]
    route = route[:route.index('if route == "/api/memory/sleep_time":')]
    check("the learning route goes through jarvis_learning_switch.request",
          "jarvis_learning_switch.request(body[\"enabled\"], set_learning)" in route, route)
    check("and no longer answers set_learning(...) directly",
          "self._send(200, set_learning(" not in route, route)
    check("a missing module is a 503, not a silent switch-on",
          "503" in route and "set_learning(body" not in route.split("except Exception")[1].split("code, out")[0],
          route)


def t_bad_input():
    w = World()
    for bad in ("yes", 1, None, "true"):
        code, _ = w.req(bad)
        check(f"enabled={bad!r} is refused", code == 400 and w.applied == [] and not w.later)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
