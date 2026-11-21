"""test_hud_crisis_route.py - a crisis turn SAYS WHY it stayed on this PC.

    py -3 -B backend/test_hud_crisis_route.py

THE RULING THIS PROVES (external review, 2026-11-19, 5.2). A crisis turn is
already never sent to a cloud lane: the crisis words are private terms, so
`jarvis_router.choose()` answers `gate: "taint"` and the turn is answered on
this PC. But that was the ONLY thing an app could read, so `cloud_refused:
"crisis"` - the field cloud-honesty.patch adds when a cloud lane was PICKED by
hand - was unobservable on the automatic path: the header said "taint" and
nothing said the turn had been headed for a cloud lane, or why it was not.

The ruling keeps the taint gate EXACTLY as it is and evaluates
`jarvis_wellbeing.crisis_in_turn` independently, so `X-Jarvis-Route` carries
`crisis: true` and `cloud_refused: "crisis"` whenever a crisis turn is
detected - even when taint also fired. NOTHING is weakened: no gate is skipped
or loosened, the decision, its gate and the lane are untouched, and nothing is
sent to a cloud lane on this path.

WHAT THIS SUITE RUNS, AND WHY IT IS NOT A SOURCE READ. It builds the text the
WHOLE patch stack leaves (`backend/_stack.stand_in("jarvis_hud.py")`), lifts
`crisis-route.patch`'s block out of it - the shipping code, not a copy - and
EXECUTES it against the real `jarvis_wellbeing` and decisions the real
`jarvis_router.choose()` returns. It also lifts cloud-honesty.patch's
crisis-rebind block and proves a hand-picked cloud lane still cannot answer a
crisis turn (the behaviour ruling 5.2 must not weaken). No source pins, no
socket, no model, no live settings file; a scratch home is made before any
import.
"""
from __future__ import annotations

import os
import sys
import tempfile
import textwrap
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
REBUILT = HERE / "rebuilt"

SCRATCH = Path(tempfile.mkdtemp(prefix="jarvis-hud-crisis-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(SCRATCH)
os.environ["JARVIS_CONFIG_DIR"] = str(SCRATCH)
os.environ["JARVIS_SUITE_RUNNING"] = "1"
os.environ["JARVIS_NTFY_TOPIC"] = ""
os.environ["JARVIS_NTFY_SERVER"] = ""
os.environ.setdefault("JARVIS_APPROVAL_TIMEOUT", "2.0")

sys.dont_write_bytecode = True
sys.path.insert(0, str(REBUILT))
sys.path.insert(0, str(HERE))

import _stack  # noqa: E402
import jarvis_router as RT  # noqa: E402
import jarvis_wellbeing as WB  # noqa: E402

FAILED, PASSED = [], []
LOCAL = "qwen3.5:9b"
CLOUD = RT.CLOUD_LANE
#: A crisis message from the owner: the wellbeing module's own worked phrase.
CRISIS = "I want to kill myself"
#: A long, clause-heavy crisis message: the turn is plainly heading for the
#: cloud when the taint gate stops it.
CRISIS_HARD = (
    "I want to kill myself. Explain in detail how the three-body problem "
    "differs from the two-body problem, and why the difference matters for "
    "predicting orbits over a long horizon.")
#: Private but NOT a crisis: a password question.
PRIVATE = "What is my password for the bank?"
#: An ordinary short question.
ORDINARY = "What is a semicolon?"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


# ==========================================================================
#  the shipping text, lifted out of the patch stack
# ==========================================================================

def _stack_text():
    src, log = _stack.stand_in("jarvis_hud.py")
    if not src:
        return None, "; ".join((log or [])[-3:]) or "empty stand-in"
    return src, ""


SRC, SRC_WHY = _stack_text()

BLOCK_START = "        _crisis_turn = False"
BLOCK_END = "\n        # Times this answer: first word, total, words and tokens per second."
REBIND_START = "        if _crisis_turn and lane != local_model and _agent_ok:"
REBIND_END = "\n        # The degrade loop below opens its own connection"


def _slice(start: str, end: str) -> str:
    if SRC is None:
        raise AssertionError(SRC_WHY)
    a = SRC.find(start)
    if a < 0:
        raise AssertionError(f"the patch stack does not carry {start[:60]!r}")
    b = SRC.find(end, a)
    if b < 0:
        raise AssertionError(f"the block after {start[:60]!r} has no {end[:40]!r}")
    return SRC[a:b]


def _exec(code: str, ns: dict) -> dict:
    exec(compile(code, "<lifted from the patch stack>", "exec"), ns)
    return ns


def _drive_crisis(messages, route_header, decision, lane):
    """Run crisis-route.patch's block as part of one chat turn."""
    block = _slice(BLOCK_START, BLOCK_END)
    code = ("def _drive(messages, route_header, decision, lane, local_model):\n"
            + "".join("    " + line + "\n"
                      for line in textwrap.dedent(block).splitlines()))
    ns = {}
    _exec(code, ns)
    ns["_drive"](messages, route_header, decision, lane, LOCAL)


def _drive_rebind(route_header, body):
    """Run cloud-honesty.patch's crisis-rebind block as part of one chat turn."""
    block = _slice(REBIND_START, REBIND_END)
    ns = {
        "_crisis_turn": True, "lane": CLOUD, "local_model": LOCAL,
        "_agent_ok": True, "route_header": route_header, "body": body,
        "is_cloud": True, "use_tools": False,
        "decision": types.SimpleNamespace(inject_memory=False),
        "_build_payload": lambda lane: {"model": lane},
    }
    exec(compile(textwrap.dedent(block), "<lifted crisis rebind>", "exec"), ns)
    return ns


def _route_header(decision=None):
    if decision is None:
        return {"lane": LOCAL, "gate": "taint", "reason": "the conversation is tainted"}
    if hasattr(decision, "as_dict"):
        return dict(decision.as_dict())
    return {"lane": decision.lane, "gate": decision.gate,
            "reason": "picked by hand for this question"}


def _choose(query, *, tainted=False, lanes=(CLOUD,), yes=True):
    return RT.choose(query, local_model=LOCAL, lanes=list(lanes),
                     owner_said_yes=yes, conversation_tainted=tainted)


def _user(text):
    return [{"role": "user", "content": text, "provenance": "typed"}]


# ==========================================================================
#  1. the stack carries the block, and it compiles
# ==========================================================================

def t_the_patch_stack_carries_the_crisis_block():
    check("the whole patch stack can be built", SRC is not None, SRC_WHY)
    if SRC is None:
        return
    block = _slice(BLOCK_START, BLOCK_END)
    try:
        compile("def _f():\n" + "".join("    " + line + "\n"
                                        for line in textwrap.dedent(block).splitlines()),
                "<crisis block>", "exec")
        ok, why = True, ""
    except SyntaxError as exc:
        ok, why = False, str(exc)
    check("crisis-route.patch's block ships and compiles in the HUD text", ok, why)


# ==========================================================================
#  2. a crisis turn records crisis AND cloud_refused - even when taint fired
# ==========================================================================

def t_a_crisis_turn_records_the_key():
    decision = _choose(CRISIS, tainted=True)
    header = _route_header(decision)
    _drive_crisis(_user(CRISIS), header, decision, decision.lane)
    check("a crisis turn records `crisis: true` in X-Jarvis-Route",
          header.get("crisis") is True, header)
    check("... the calm panel's existing `wellbeing: crisis` flag is unchanged",
          header.get("wellbeing") == "crisis", header)


def t_even_when_taint_fired_the_cloud_refusal_is_visible():
    decision = _choose(CRISIS_HARD, tainted=True)
    check("the router's own taint gate is what holds this turn (gate 'taint', "
          "lane local) - it is unchanged",
          decision.gate == "taint" and decision.lane == LOCAL,
          (decision.gate, decision.lane))
    header = _route_header(decision)
    _drive_crisis(_user(CRISIS_HARD), header, decision, decision.lane)
    check("... the header now says `cloud_refused: crisis` as well",
          header.get("cloud_refused") == "crisis", header)
    check("... and the turn still says it IS a crisis turn", header.get("crisis") is True,
          header)
    check("... the decision's own gate was NOT weakened or changed",
          header.get("gate") == "taint" and header.get("lane") == LOCAL,
          (header.get("gate"), header.get("lane")))


def t_a_tainted_non_crisis_turn_gets_no_crisis_key():
    # Tainted for some other reason (e.g. an earlier turn read outside text),
    # but this turn itself is not a crisis.
    decision = _choose(ORDINARY, tainted=True)
    header = _route_header(decision)
    _drive_crisis(_user(ORDINARY), header, decision, decision.lane)
    check("a tainted but NON-crisis turn gets no crisis key",
          "crisis" not in header, header)
    check("... and no cloud_refused key either", "cloud_refused" not in header, header)


def t_a_non_crisis_private_turn_gets_no_crisis_key():
    decision = _choose(PRIVATE, tainted=False)
    check("a private question is held by its own gate, not by crisis",
          decision.gate == "private" and decision.lane == LOCAL,
          (decision.gate, decision.lane))
    header = _route_header(decision)
    _drive_crisis(_user(PRIVATE), header, decision, decision.lane)
    check("a non-crisis private turn has no `crisis` key", "crisis" not in header, header)
    check("... no cloud_refused key, and no wellbeing flag",
          "cloud_refused" not in header and "wellbeing" not in header, header)


def t_an_ordinary_turn_gets_no_crisis_key():
    decision = _choose(ORDINARY, tainted=False)
    header = _route_header(decision)
    _drive_crisis(_user(ORDINARY), header, decision, decision.lane)
    check("an ordinary turn gains nothing from this change",
          "crisis" not in header and "cloud_refused" not in header
          and "wellbeing" not in header, header)


# ==========================================================================
#  3. a hand-picked cloud lane still cannot answer a crisis turn
# ==========================================================================

def t_a_picked_cloud_lane_is_still_refused_and_says_why():
    decision = types.SimpleNamespace(gate="escalate", lane=CLOUD,
                                     inject_memory=False, auto=False)
    header = _route_header(decision)
    _drive_crisis(_user(CRISIS), header, decision, CLOUD)
    check("a crisis turn headed for a cloud lane records cloud_refused: crisis",
          header.get("cloud_refused") == "crisis", header)
    check("... and it is a crisis turn", header.get("crisis") is True, header)
    # cloud-honesty.patch's rebind runs next in the real turn: prove it still
    # hands the turn to this PC and rebuilds the payload as a local turn's.
    ns = _drive_rebind(header, {"messages": _user(CRISIS)})
    check("the cloud lane is rebound to this PC's model", ns.get("lane") == LOCAL,
          ns.get("lane"))
    check("... the header says which lane really answered",
          header.get("lane") == LOCAL and header.get("cloud_refused") == "crisis",
          header)
    check("... and the payload is rebuilt as a local turn's",
          ns.get("is_cloud") is False and ns.get("payload", {}).get("model") == LOCAL,
          (ns.get("is_cloud"), ns.get("payload")))
    check("... so the tool-less local loop answers it here",
          ns.get("use_tools") is True, ns.get("use_tools"))


# ==========================================================================
#  4. the taint protection itself is untouched
# ==========================================================================

def t_the_taint_gate_is_unchanged():
    decision = _choose(CRISIS, tainted=True)
    check("the real router still refuses a crisis turn at gate 'taint'",
          decision.gate == "taint", decision.gate)
    check("... and keeps it on the local model", decision.lane == LOCAL, decision.lane)
    check("... with the cloud lane not offered at all",
          decision.offer in (None, ""), decision.offer)
    check("nothing is sent on this path: the decision that would send it "
          "never leaves local", decision.lane == LOCAL, decision.lane)


def t_a_crisis_turn_is_recognised_by_the_shared_rule():
    check("jarvis_wellbeing.crisis_in_turn sees the crisis in the newest user turn",
          WB.crisis_in_turn(_user(CRISIS)) is True,
          WB.crisis_in_turn(_user(CRISIS)))
    check("... and does not see one in the private or ordinary turns",
          WB.crisis_in_turn(_user(PRIVATE)) is False
          and WB.crisis_in_turn(_user(ORDINARY)) is False,
          (WB.crisis_in_turn(_user(PRIVATE)), WB.crisis_in_turn(_user(ORDINARY))))


# ==========================================================================

TESTS = [
    t_the_patch_stack_carries_the_crisis_block,
    t_a_crisis_turn_records_the_key,
    t_even_when_taint_fired_the_cloud_refusal_is_visible,
    t_a_tainted_non_crisis_turn_gets_no_crisis_key,
    t_a_non_crisis_private_turn_gets_no_crisis_key,
    t_an_ordinary_turn_gets_no_crisis_key,
    t_a_picked_cloud_lane_is_still_refused_and_says_why,
    t_the_taint_gate_is_unchanged,
    t_a_crisis_turn_is_recognised_by_the_shared_rule,
]


def main() -> int:
    for fn in TESTS:
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(f"{fn.__name__} raised")
            print(f"FAIL  {fn.__name__} raised")
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        for name in FAILED:
            print(f"  failed: {name}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
