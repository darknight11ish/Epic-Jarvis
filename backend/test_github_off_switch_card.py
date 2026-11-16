#!/usr/bin/env python3
"""test_github_off_switch_card.py - a switched-off GitHub tool is ONE card away,
not a trip to Settings (the owner's ruling, 2026-11-16).

    py -3 -B backend/test_github_off_switch_card.py

WHAT THE OWNER RULED, and what was measured before this suite existed:

    "abilities on by default, one approval per job instead of per action, and
     no need to visit Settings to enable a tool"

The measured answer to "can you create a repository?" ended:

    "Its own tool, github_create_repo, is switched OFF in Settings, What asks
     first, under \\"Jarvis's own tools\\" - switching it on is one card on the
     PC. While it is off, I cannot ask GitHub to create one."

Every word of that was true and it still failed him: the ONE card it named was
in another window. So the deterministic answer now offers that card IN PLACE,
through the route the Settings switch itself uses, and reports a card that was
turned down instead of silently staying off.

WHAT THIS SUITE PINS, each one a separate way the ruling can regress:

  1. THE BITE: answering the capability question RAISES the switch card
     (`jarvis_asks_first.request_tool_enable`), with the body
     `{"tool": "github_create_repo", "enabled": true}` and the request's own
     `peer`/`local`. On the old answer nothing was requested at all.
  2. It is the SAME card, not a new permission surface: the card's action is
     `jarvis_asks_first.ENABLE_TOOL_ACTION` (`enable_reading_tool`), and the
     call goes through `request_tool_enable` - the one function
     `POST /api/asks_first/tools` calls.
  3. NOTHING is written before a person approves, and the write after a yes is
     the one line `github_create_repo`.
  4. A card that was turned down is SAID ("You declined that card, so it stays
     off"), once, and the ask after that offers the card again.
  5. A card already waiting is not drawn twice.
  6. From a phone (a request that does not come from this PC) NO card is
     requested - the route's own PC-only rule - and the answer says to ask on
     the PC.
  7. With the tool already on, no card is raised at all.
  8. A PC that cannot raise it falls back to the honest Settings sentence, never
     to a promise of a card.

No network, no model, no Windows Hello, no card and no file written: the gate,
the spawn, the armed check and the settings writer are all stubs here, and the
owner's own settings file is never read through `tools_enabled_set`.
"""
from __future__ import annotations

import contextlib
import os
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-gh-off-card-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["JARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["JARVIS_LOG_DIR"] = str(_TMP / "logs")
os.environ["JARVIS_FRAMEWORK_TOML"] = str(_TMP / "jarvis-framework.toml")
os.environ.pop("JARVIS_BACKEND", None)
(_TMP / "config").mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_quick.py", "jarvis_asks_first.py", "jarvis_github.py")
if str(HERE / "rebuilt") not in sys.path:
    sys.path.append(str(HERE / "rebuilt"))

import jarvis_asks_first as AF  # noqa: E402
import jarvis_github as GH  # noqa: E402
import jarvis_quick as Q  # noqa: E402

PASSED: list = []
FAILED: list = []


class _NoToken:
    """The whole run: no token is saved, and the credential store is never read.

    `jarvis_github.connected()` would otherwise answer from the owner's own
    store, so the same suite would pass at his desk and read differently in CI.
    Nothing here is about the token; the answer's token sentence is another
    suite's.
    """

    def __enter__(self):
        self._keep = GH.connected
        GH.connected = lambda: False
        return self

    def __exit__(self, *_exc):
        GH.connected = self._keep
        return False


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name if cond else f"{name}  <-- {detail}")
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  <-- {detail}"))


#: The owner's own question and the shapes the capability answer claims. The
#: card must be offered for every one of them, because they are one answer.
QUESTIONS = (
    "can you create a repository?",
    "create a repository",
    "can you create a github repository?",
    "set up a new github repository",
)


class _Said:
    """A gate verdict: `approved` True is a person's yes, False a decline."""

    tier = "ask"
    reason = ""

    def __init__(self, approved: bool):
        self.approved = bool(approved)
        self.outcome = "approved" if approved else "denied"


@contextlib.contextmanager
def _carded(verdict=None, *, enabled=(), run_the_card=False, request=None):
    """The real answer, over stubbed card plumbing (no Windows, no real gate).

    Everything `request_tool_enable` reaches for is replaced EXCEPT
    `tools_status` (the answer's own honest read of a waiting card and of the
    last outcome) and `request_tool_enable` itself, which is wrapped rather than
    replaced so this suite drives the real route. `run_the_card` False keeps the
    spawned ask captured, which is how a test sees the state BEFORE anyone
    answers - the claim that nothing is written until then.
    """
    calls = {"cards": 0, "actions": [], "writes": [], "pending": []}
    names = ("_gate", "_tier", "_spawn", "_owner_check_armed", "_person_said_yes",
             "tools_enabled_set", "set_tools_enabled", "request_tool_enable",
             "tools_status")
    real = {n: getattr(AF, n) for n in names}

    def gate(action, detail, prompt):
        calls["cards"] += 1
        calls["actions"].append(action)
        return verdict if verdict is not None else _Said(True)

    AF.tools_enabled_set = lambda: set(enabled)
    AF._tier = lambda action: "ask"
    AF._owner_check_armed = lambda: True
    AF._gate = gate
    AF._spawn = ((lambda fn: fn()) if run_the_card
                 else (lambda fn: calls["pending"].append(fn)))
    AF._person_said_yes = lambda v: bool(getattr(v, "approved", False))
    AF.set_tools_enabled = lambda t, on: calls["writes"].append((t, on))
    AF._reset_for_tests()
    seen = []
    real_request = real["request_tool_enable"]

    def spy(body, **kw):
        seen.append((dict(body or {}), dict(kw)))
        if request is not None:
            return request(body, **kw)
        return real_request(body, **kw)

    AF.request_tool_enable = spy
    try:
        yield calls, seen
    finally:
        for n, fn in real.items():
            setattr(AF, n, fn)
        AF._reset_for_tests()


def _ask(sentence, **kw):
    intent = Q.match(sentence)
    if intent is None:
        return None, ""
    return intent, str(Q.run(intent, None, 0.0, **kw).reply)


# ---------------------------------------------------------------------------
#   1. THE BITE: the answer raises the switch card in place
# ---------------------------------------------------------------------------


def t_the_answer_offers_the_switch_card_in_place():
    for sentence in QUESTIONS:
        with _carded() as (calls, seen):
            intent, reply = _ask(sentence)
            check(f"{sentence!r} is the GitHub answer, not the model",
                  intent is not None and intent.name == "github_self",
                  None if intent is None else intent.name)
            check(f"{sentence!r}: the switch card is ASKED FOR", bool(seen), seen)
            if seen:
                body, _kw = seen[0]
                check(f"{sentence!r}: the card is for github_create_repo, ON",
                      body.get("tool") == "github_create_repo"
                      and body.get("enabled") is True, body)
            check(f"{sentence!r}: the ask is raised and not yet answered",
                  len(calls["pending"]) == 1, calls["pending"])
            check(f"{sentence!r}: NO verdict exists before a person is asked",
                  calls["cards"] == 0, calls["cards"])
            check(f"{sentence!r}: the answer SAYS a card is waiting",
                  "Waiting for your approval" in reply, reply[-700:])
            check(f"{sentence!r}: it says where to approve it (PC or phone)",
                  "Windows Hello" in reply and "phone" in reply, reply[-700:])
            check(f"{sentence!r}: it stays honest that the tool is still off",
                  "still off" in reply.lower(), reply[-700:])
            check(f"{sentence!r}: it never claims the repository was created",
                  "was created" not in reply.lower()
                  and "created the repository" not in reply.lower(), reply[-700:])


# ---------------------------------------------------------------------------
#   2. the SAME card the Settings switch raises - no new permission surface
# ---------------------------------------------------------------------------


def t_it_is_the_settings_switch_card_and_nothing_new():
    check("the card's action is the Settings switch's own (enable_reading_tool)",
          AF.ENABLE_TOOL_ACTION == "enable_reading_tool", AF.ENABLE_TOOL_ACTION)
    with _carded(run_the_card=True) as (calls, seen):
        _intent, _reply = _ask("can you create a repository?")
        check("the answer went through request_tool_enable (the route's own door)",
              bool(seen), seen)
        check("... and drew exactly that one card, under that one action",
              calls["actions"] == [AF.ENABLE_TOOL_ACTION], calls["actions"])
        check("... and the body is the route's own body",
              seen and seen[0][0] == {"tool": "github_create_repo", "enabled": True},
              seen)
        # THE ROUTE ITSELF: POST /api/asks_first/tools ends in that same
        # function, so the chat answer and the Settings switch cannot be two
        # permission surfaces. Calling the route directly must hit the spy.
        seen.clear()
        code, _out = AF.handle_tools(
            {"tool": "github_create_repo", "enabled": True}, None, None)
        check("... which is the same function the Settings route calls",
              bool(seen) and seen[0][0] == {"tool": "github_create_repo",
                                            "enabled": True}, (code, seen))


# ---------------------------------------------------------------------------
#   3. nothing is written before a person says yes
# ---------------------------------------------------------------------------


def t_nothing_is_written_until_a_person_approves():
    with _carded() as (calls, _seen):
        _intent, reply = _ask("can you create a repository?")
        check("the answer hands over exactly one ask", len(calls["pending"]) == 1,
              calls["pending"])
        check("before the answer: nothing written",
              calls["writes"] == [], calls["writes"])
        check("before the answer: no verdict drawn", calls["cards"] == 0,
              calls["cards"])
        check("the answer itself never says the write happened",
              "is switched on" not in reply, reply[-700:])
        # The captured ask runs AFTER the answer, exactly as the thread does in
        # the real backend once a person presses Approve (the gate stub is yes).
        for fn in list(calls["pending"]):
            fn()
        check("after the yes: ONE card drawn", calls["cards"] == 1, calls["cards"])
        check("after the yes: the ONE line written is github_create_repo = true",
              calls["writes"] == [("github_create_repo", True)], calls["writes"])


# ---------------------------------------------------------------------------
#   4. a declined card is SAID, once, and the card is offered again after that
# ---------------------------------------------------------------------------


def t_a_decline_is_said_and_then_the_card_is_offered_again():
    with _carded(_Said(False)) as (calls, seen):
        _intent, first = _ask("can you create a repository?")
        check("first ask: the card is raised", len(calls["pending"]) == 1,
              calls["pending"])
        check("first ask: it says a card is waiting, not that it is on",
              "Waiting for your approval" in first and "still off" in first.lower(),
              first[-700:])
        for fn in list(calls["pending"]):
            fn()                                   # the person says NO
        calls["pending"].clear()
        seen.clear()
        _intent, second = _ask("can you create a repository?")
        check("the answer after a NO says the owner declined it",
              "You declined that card" in second, second[-900:])
        check("... and says it stays off", "stays off" in second, second[-900:])
        check("... and promises the card is still one ask away",
              "offer the card again" in second, second[-900:])
        check("... and does NOT draw a second card unasked", not seen
              and not calls["pending"], (seen, calls["pending"]))
        check("... and never claims it is on", "is switched on" not in second,
              second[-900:])
        _intent, third = _ask("can you create a repository?")
        check("the ask AFTER the decline offers the card again",
              len(calls["pending"]) == 1 and bool(seen), (calls["pending"], seen))
        check("... with the same body as the first time",
              seen and seen[0][0] == {"tool": "github_create_repo", "enabled": True},
              seen)


# ---------------------------------------------------------------------------
#   5. a card already waiting is not drawn a second time
# ---------------------------------------------------------------------------


def t_a_waiting_card_is_not_drawn_twice():
    with _carded() as (calls, seen):
        _intent, first = _ask("can you create a repository?")
        check("first ask raises it", len(calls["pending"]) == 1, calls["pending"])
        seen.clear()
        _intent, second = _ask("can you create a repository?")
        check("a second ask sees the waiting card and says so",
              "already waiting" in second, second[-700:])
        check("... and asks for no second card", not seen, seen)
        check("... while the first card is still the only one",
              len(calls["pending"]) == 1, calls["pending"])


# ---------------------------------------------------------------------------
#   6. from a phone: no card is requested, and the answer says where
# ---------------------------------------------------------------------------


def t_from_a_phone_no_card_is_requested_and_it_says_where():
    with _carded() as (calls, seen):
        _intent, reply = _ask("can you create a repository?",
                              peer="192.0.2.9", local="192.0.2.1")
        check("a phone request asks the route, and the route's own PC rule refuses",
              bool(seen), seen)
        check("a phone request draws NO card", not calls["pending"],
              calls["pending"])
        check("... and no verdict", calls["cards"] == 0, calls["cards"])
        check("... and the answer says the card is asked for on the PC",
              "from a chat on the PC" in reply, reply[-900:])
        check("... and says the card can be approved from the phone",
              "approve it from this phone" in reply, reply[-900:])
        check("... and says the tool is still off",
              "cannot ask GitHub to create one" in reply, reply[-900:])


# ---------------------------------------------------------------------------
#   7. already on: no card at all
# ---------------------------------------------------------------------------


def t_an_on_tool_raises_no_card():
    with _carded(enabled=("github_create_repo",)) as (calls, seen):
        _intent, reply = _ask("can you create a repository?")
        check("an offered tool draws no card", not seen and not calls["pending"],
              (seen, calls["pending"]))
        check("... and the answer says it is switched on",
              "is switched on in Settings" in reply, reply[-700:])


# ---------------------------------------------------------------------------
#   8. a PC that cannot raise it falls back to the honest Settings sentence
# ---------------------------------------------------------------------------


def t_a_pc_that_cannot_raise_it_says_the_settings_sentence():
    with _carded(request=lambda *a, **k: (503, {
            "ok": False,
            "error": ("Your PC's Jarvis cannot ask Windows Hello itself yet, so no tool "
                      "can be offered to the AI model from the app - run "
                      "apply-patches.ps1 on the PC.")})) as (calls, _seen):
        _intent, reply = _ask("can you create a repository?")
        check("the route's own refusal is quoted, not a promise of a card",
              "cannot ask Windows Hello itself yet" in reply, reply[-900:])
        check("... and it still says the tool is off",
              "cannot ask GitHub to create one" in reply, reply[-900:])
        check("... with no card raised", not calls["pending"] and calls["cards"] == 0,
              (calls["pending"], calls["cards"]))
    # An older backend with no card route at all: the old sentence, unchanged.
    with _carded() as (calls, _seen):
        keep = AF.request_tool_enable
        AF.request_tool_enable = None
        try:
            _intent, reply = _ask("can you create a repository?")
        finally:
            AF.request_tool_enable = keep
        check("an older PC gets the Settings sentence, not a promise",
              "switched OFF in Settings, What asks first" in reply, reply[-900:])
        check("... and no card is pretended", not calls["pending"],
              calls["pending"])


# ---------------------------------------------------------------------------

def main() -> int:
    try:
        with _NoToken():
            t_the_answer_offers_the_switch_card_in_place()
            t_it_is_the_settings_switch_card_and_nothing_new()
            t_nothing_is_written_until_a_person_approves()
            t_a_decline_is_said_and_then_the_card_is_offered_again()
            t_a_waiting_card_is_not_drawn_twice()
            t_from_a_phone_no_card_is_requested_and_it_says_where()
            t_an_on_tool_raises_no_card()
            t_a_pc_that_cannot_raise_it_says_the_settings_sentence()
    except Exception:
        FAILED.append("the suite itself raised")
        traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        for name in FAILED:
            print(f"  FAILED  {name}")
        return 1
    print("PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
