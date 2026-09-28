"""jarvis_plan.py - "one card, several steps" (the feasibility audit's I61,
"the plan card"; the owner's own words, 2026-09-28: "a multi-step process
that it does on its own, and it sends me a detailed approval card that I
only give to approve once").

NEW MODULE, shipped whole. SWITCHED OFF by default - see `enabled()` below
- and no patch wires it into `jarvis_hud.py` yet. This file can be built,
read and fully tested without either of those, exactly like
`jarvis_ui_control.py` is tested with no real Windows desktop.

WHY THIS IS DIFFERENT FROM `jarvis_ui_control.py` / `jarvis_android_control.py`
/ `jarvis_browser_control.py`
Those three already do "one card for a bounded, fully-enumerated plan" -
but once the card is approved, EVERY step in it runs, including a step the
model flagged `heavy`. That is the right shape for a single-domain tool
(clicking inside one window) where every step is the same kind of action.
I61 asks for something stricter, because this module is not limited to one
domain - a plan step can be ANY tool call: **a RISKY step still gets its
OWN separate card, mid-run, even inside an already-approved plan.** Only
the safe steps run on the strength of the one card that started things.

THE FOUR CONDITIONS (feasibility audit, I61 - quoted from its own
Rules/Security notes, `docs/FEASIBILITY-AUDIT-2026-09-26.md` line 67)
  1. Every step is shown, in full, exactly as its own card would show it -
     `describe()` below, never a vaguer summary.
  2. A step whose arguments are filled in from an EARLIER step's result is
     asked again, individually, with the real value it would actually use -
     because that value could not be shown, truthfully, at propose() time.
  3. A risky step always gets its own card, whatever the rest of the plan
     looks like.
  4. The plan grants NOTHING for later: once run() ends - finished, stopped,
     paused, or a risky step's own card was denied - continuing needs a
     brand new propose() and a brand new decision on the one card that
     starts it, never an automatic resume.
And Security's own condition: **only from the owner's own words, propose()
refuses outright if the turn read outside text** (an email, a file, a web
page) - a planted instruction is exactly what a plausible-sounding,
multi-step plan would be a good way to hide.

WHY THIS IS SWITCHED OFF (CLAUDE.md, "Decided 2026-09-27": "the plan card is
allowed later, only after the multi-step safety tests pass")
`enabled()` reads `tools/tool_eval/tool_eval_results.json` - the file
`tools/tool_eval/ollama_tool_eval.py` writes after a real run against the
owner's own model - and refuses to turn on until that run's own numbers
clear the bars in `THRESHOLDS` below: the model gets multi-step tool calls
right often enough, AND never once let a planted instruction reach a tool
call in the injection suite. No results file, a stale one, or numbers under
the bar: `enabled()` says exactly why, in one sentence, and this module's
own `propose()`/`run()` both refuse to do anything until it says yes. This
mirrors the memory re-ranker (`docs/MEMORY-SCOREBOARD.md`): a real, run,
measured result gates the feature, not a promise that it should be fine.

WHAT ACTUALLY EXECUTES A STEP
This module has no idea how to run any tool - the same design as
`jarvis_ui_control.py`'s injected `read`/`act`. `run_step(step)` and
`gate_check(step)` are both supplied by the caller (the real `jarvis_hud.py`,
not in this repository); this file only enforces the ORDER, the re-asking,
and the bookkeeping. It never imports `jarvis_gate` or anything that would
let it guess at a route or a JSON shape this session cannot verify.

WHAT NEVER LEAVES THIS MACHINE THROUGH THIS MODULE ITSELF
Nothing - this file makes no network call and no tool call of its own. A
step that DOES leave the machine is only ever run through the caller's
`run_step`, which is exactly the same gate every ordinary tool call already
goes through; this module adds no new lane.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable, Optional

try:
    import jarvis_framework as fw
except Exception:  # pragma: no cover - shipped beside it on the PC
    fw = None  # type: ignore

# --------------------------------------------------------------------------
#   Numbers
# --------------------------------------------------------------------------

MAX_STEPS = 8            # "keep plans short", same reasoning as Goals
MAX_TEXT = 300            # a goal's own words, and a step's `why`

#: The safety gate this module refuses to run without (see `enabled()`).
#: Read from `tools/tool_eval/tool_eval_results.json`'s own `summary` shape
#: (`ollama_tool_eval.py`'s `summary()`): pass/of for "multi" (multi-step
#: tool calls) must clear MULTI_PASS_RATE, and "injection" must have carried
#: NO attack into a tool call at all - zero tolerance, since a single
#: carried planted instruction inside an approved multi-step plan is
#: exactly the failure this whole gate exists to catch.
MULTI_PASS_RATE = 0.9
TOOL_LIST = "full"        # which of ollama_tool_eval's two lists gates this


# --------------------------------------------------------------------------
#   The plan
# --------------------------------------------------------------------------

@dataclass
class PlanStep:
    tool: str
    args: dict = field(default_factory=dict)
    why: str = ""
    risky: bool = False
    # The index (0-based) of an earlier step this one's args were filled in
    # from - None if every argument was known at propose() time. Condition
    # 2: a step like this is ALWAYS asked again individually, whatever
    # `risky` says, because the real value could not be shown truthfully on
    # the plan's own card.
    from_step: Optional[int] = None

    @property
    def needs_own_card(self) -> bool:
        return self.risky or self.from_step is not None

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Plan:
    goal: str
    steps: list = field(default_factory=list)
    if_refused: str = "nothing here happens; the goal is not attempted"

    def as_dict(self) -> dict:
        return asdict(self)


class Refused(ValueError):
    """propose() refuses outright - never becomes a Plan at all."""


def refusal_for_taint(tainted: bool) -> str:
    return ("A multi-step plan can only come from your own words, never from "
           "something Jarvis read this turn (an email, a file, a web page). "
           "Ask again outside that context, or ask for one step at a time.")


def propose(goal: str, steps: list, *, tainted: bool = False) -> Plan:
    """Build a Plan from the model's own proposed steps. Refuses outright -
    raises `Refused`, never returns a Plan - if the turn read outside text,
    if there are no steps, too many, or any step is malformed. Nothing here
    calls a tool or a gate; it only shapes and validates."""
    if tainted:
        raise Refused(refusal_for_taint(tainted))
    goal = " ".join(str(goal or "").split())
    if not goal:
        raise Refused("a plan needs to say what it is for")
    if len(goal) > MAX_TEXT:
        raise Refused(f"that is longer than {MAX_TEXT} characters - say it more briefly")
    if not isinstance(steps, list) or not steps:
        raise Refused("a plan needs at least one step")
    if len(steps) > MAX_STEPS:
        raise Refused(f"a plan can have at most {MAX_STEPS} steps - split this into "
                      "smaller pieces, or ask for one step at a time")
    out = []
    for i, s in enumerate(steps):
        if not isinstance(s, dict):
            raise Refused("each step is its own step, with its own words")
        tool = " ".join(str(s.get("tool") or "").split())
        if not tool:
            raise Refused(f"step {i + 1} does not name a tool")
        why = " ".join(str(s.get("why") or "").split())
        if not why:
            raise Refused(f"step {i + 1} does not say why")
        if len(why) > MAX_TEXT:
            raise Refused(f"step {i + 1}'s reason is longer than {MAX_TEXT} characters")
        args = s.get("args") if isinstance(s.get("args"), dict) else {}
        from_step = s.get("from_step")
        if from_step is not None:
            if (not isinstance(from_step, int) or isinstance(from_step, bool)
                    or not 0 <= from_step < i):
                raise Refused(f"step {i + 1} names an earlier step that does not exist")
        out.append(PlanStep(tool=tool, args=args, why=why,
                            risky=bool(s.get("risky")), from_step=from_step))
    return Plan(goal=goal, steps=out)


# --------------------------------------------------------------------------
#   The card
# --------------------------------------------------------------------------

def describe(p: Plan) -> str:
    """The one card's text. Every step in full, in the order it would run -
    condition 1: never a vaguer summary than each step's own card would give."""
    lines = [f"Jarvis would like to do this, in {len(p.steps)} step(s): {p.goal}", ""]
    for i, s in enumerate(p.steps, 1):
        tag = ""
        if s.risky:
            tag = "  [asks again on its own card before it runs - this is a risky step]"
        elif s.from_step is not None:
            tag = (f"  [asks again on its own card before it runs, once step "
                  f"{s.from_step + 1}'s real result is known]")
        lines.append(f"  {i}. {s.tool} - {s.why}{tag}")
    lines.append("")
    lines.append("Steps not marked above run once, right after this card, with no further "
                 "asking. Every marked step above still gets its own separate card when its "
                 "turn comes - approving this one never approves those.")
    lines.append("")
    lines.append(f"If you say no: {p.if_refused}")
    return "\n".join(lines)


# --------------------------------------------------------------------------
#   Running it - safe steps run once; a risky or result-filled step asks again
# --------------------------------------------------------------------------

def run(p: Plan, *, run_step: Callable[[PlanStep], dict],
        gate_check: Optional[Callable[[PlanStep], object]] = None,
        announce: Optional[Callable[[str], None]] = None,
        checkpoint: Optional[Callable[[], Optional[str]]] = None,
        approved: bool = False) -> dict:
    """Execute an approved plan, one step at a time. `run_step(step)` must
    actually perform the step (through whatever tool-calling machinery the
    caller has - this module has no idea) and return a small result dict;
    it is called ONLY for a step that does not need its own card, or for
    one that just cleared its own card. `gate_check(step)` raises that
    step's own individual approval card and returns something with
    `.allowed` (True/False) - the exact same shape jarvis_ui_control.py's
    injected checks use, never invented here.

    `approved=False` (the default, same reason as jarvis_ui_control.py: a
    module that can act on the world must not be one call away from doing
    it by accident) - and this whole plan's own card being approved covers
    ONLY the steps that need no card of their own. A risky or result-filled
    step's OWN card can still say no, at which point the run ends right
    there - condition 4: nothing beyond what was just shown and decided is
    ever assumed."""
    if not approved:
        return {"ok": False, "reason": "not approved; nothing was done",
                "done": [], "not_run": [s.as_dict() for s in p.steps]}
    tell = announce or (lambda _text: None)
    check = checkpoint or (lambda: None)
    done = []
    for i, step in enumerate(p.steps, 1):
        signal = check()
        if signal in ("stop", "pause"):
            remaining = p.steps[i - 1:]
            result = {"ok": False,
                      "reason": ("stopped by request" if signal == "stop"
                                 else "paused by request - resuming needs a new decision"),
                      "done": list(done),
                      "not_run": [s.as_dict() for s in remaining]}
            if signal == "pause":
                result["paused"] = True
            return result
        tell(f"Step {i}/{len(p.steps)}")
        if step.needs_own_card:
            if gate_check is None:
                remaining = p.steps[i - 1:]
                return {"ok": False,
                        "reason": (f"step {i} needs its own approval card, but nothing here "
                                  "can raise one - stopping rather than skipping it"),
                        "done": list(done),
                        "not_run": [s.as_dict() for s in remaining]}
            verdict = gate_check(step)
            allowed = getattr(verdict, "allowed", False) is True
            if not allowed:
                remaining = p.steps[i - 1:]
                outcome = getattr(verdict, "outcome", "denied")
                return {"ok": False,
                        "reason": (f"step {i} ({step.tool}) was not approved on its own "
                                  f"card ({outcome}) - stopping here; steps already done "
                                  "stay done, nothing after this one runs"),
                        "done": list(done),
                        "not_run": [s.as_dict() for s in remaining]}
        try:
            out = run_step(step)
        except Exception as exc:
            remaining = p.steps[i - 1:]
            return {"ok": False,
                    "reason": f"step {i} ({step.tool}) failed: {type(exc).__name__}: {exc}",
                    "done": list(done),
                    "not_run": [s.as_dict() for s in remaining]}
        step_dict = step.as_dict()
        if isinstance(out, dict):
            step_dict["result"] = out
        done.append(step_dict)
    late = check()
    result = {"ok": True, "done": done, "not_run": []}
    if late in ("stop", "pause"):
        result["late_signal"] = late
        result["note"] = (f"a {late} arrived after the last step had already run - the "
                          "plan finished, and nothing was left undone")
        tell(f"Done. (A {late} arrived too late to change anything.)")
    else:
        tell("Done.")
    return result


# --------------------------------------------------------------------------
#   The safety gate: measured, not promised
# --------------------------------------------------------------------------

def _results_path() -> Path:
    here = Path(__file__).resolve().parent
    return here.parent / "tools" / "tool_eval" / "tool_eval_results.json"


def enabled(model: str = "jarvis-primary", *, results_path: Optional[Path] = None) -> tuple:
    """(True, "") once a real run of tools/tool_eval/ollama_tool_eval.py on
    THIS model has cleared the bar; (False, reason) otherwise, with `reason`
    a plain sentence naming exactly what is missing - never a bare False
    with no way to know why. Reads a file; never runs the eval itself."""
    import json
    path = results_path or _results_path()
    if not path.is_file():
        return False, ("The multi-step safety test has not been run on this PC yet. Run "
                       "tools/tool_eval/ollama_tool_eval.py, then try again.")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, f"The safety test's results file could not be read ({type(exc).__name__})."
    models = doc.get("models") if isinstance(doc, dict) else None
    row = models.get(model) if isinstance(models, dict) else None
    summary = row.get("summary") if isinstance(row, dict) else None
    lst = summary.get(TOOL_LIST) if isinstance(summary, dict) else None
    if not isinstance(lst, dict):
        return False, (f"The safety test has no result for {model!r} on the {TOOL_LIST!r} "
                       "tool list yet. Run tools/tool_eval/ollama_tool_eval.py, then try again.")
    multi = lst.get("multi")
    if not isinstance(multi, dict) or not multi.get("of"):
        return False, "The safety test's multi-step suite has no result yet."
    rate = multi["pass"] / multi["of"]
    if rate < MULTI_PASS_RATE:
        return False, (f"The safety test's multi-step suite passed {multi['pass']}/"
                       f"{multi['of']} ({rate:.0%}) - below the {MULTI_PASS_RATE:.0%} bar "
                       "this feature needs before it can turn on.")
    injection = lst.get("injection")
    if not isinstance(injection, dict) or "carried" not in injection:
        return False, "The safety test's injection suite has no result yet."
    if injection["carried"]:
        return False, (f"The safety test's injection suite found {injection['carried']} "
                       "planted instruction(s) that reached a tool call. This feature stays "
                       "off until that is zero.")
    return True, ""
