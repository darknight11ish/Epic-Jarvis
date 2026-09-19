"""jarvis_ui_control.py - lets Jarvis click inside OTHER Windows programs.

WHAT IT IS FOR
Jarvis cannot touch any other app's UI today. `microsoft/UFO` was suggested
as a way to fix that - it reads the Windows accessibility tree (UI
Automation, "UIA") instead of guessing pixel coordinates, so it clicks named
buttons rather than blind (x, y) positions. That idea is worth having. UFO's
own architecture is not: see docs/UFO-SAFETY-DESIGN.md for why its live
perceive-act loop - keep clicking on its own judgment until the goal looks
done - is a standing grant for future, unnamed actions, which is exactly what
this project's one hard rule forbids. This module takes the idea (read the
tree, click named controls) and builds it the shape docs/ARCHITECTURE.md
requires instead: no dependency on UFO, no loop.

THE PERMISSION MODEL, WHICH IS THE POINT
    plan(goal, window, requests)   reads the CURRENT accessibility tree of
                                    one window - no input is sent - and binds
                                    each requested control to a concrete,
                                    identified UI element. Returns a Plan: a
                                    bounded, fully enumerated list of Steps
                                    decided now, not improvised later.
    run(plan, approved=True)       executes ONLY the enumerated steps, in
                                    order. Before each one, re-reads the tree
                                    and checks the target is still there,
                                    still enabled, and still the same control
                                    it was at plan time. The moment that is
                                    not true - the window closed, a dialog
                                    appeared, the control moved - run() STOPS
                                    and reports exactly which step failed,
                                    rather than guessing or clicking the
                                    nearest thing. Whatever changed needs a
                                    new plan() and a new decision, not a
                                    retry of the old one.

WHY ONE CARD FOR SEVERAL STEPS IS NOT AN "APPROVE ALL"
Same reasoning as jarvis_research.py, which this module's shape is copied
from: one decision for one bounded, fully-printed set of steps is not a
standing grant. A goal that needs to change mid-way - because a step failed,
or because it turns out to need one more click nobody enumerated - is a NEW
plan and a new decision. Nothing here is allowed to keep going on its own
say-so past the steps that were shown and approved.

WHAT ACTUALLY HAPPENS, AND WHAT DOES NOT LEAVE THIS MACHINE
Reading the accessibility tree and sending a click or keystroke are both
entirely local - no network, no credential, nothing here touches the API-key
rule at all. If a requested step is itself a network action from inside the
target app (typing into a browser that then submits a form), that step's
`why` has to say so, in full, same as jarvis_research says what leaves the
machine - this module does not detect that on its own; the caller states it.

TESTING WITHOUT WINDOWS
Real accessibility-tree reads and real input happen through two small
functions, `read` and `act`, both injectable - exactly how jarvis_research.py
injects `fetch` so its grading logic can be tested with no socket. Nothing in
this file imports a Windows-only package at module load time; the default
`read`/`act` only try to import one when actually called with nothing
injected, and fail with a clear message rather than a stack trace from deep
inside a missing dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Callable, Optional

# The two things a caller MUST tell this module, because it cannot infer
# them from the UI tree on its own: whether a step can be undone, and
# whether it makes something leave the machine. Both push a plan to "heavy".
IRREVERSIBLE_HINT = "irreversible"
LEAVES_MACHINE_HINT = "leaves_machine"


# --------------------------------------------------------------------------
#   The plan - built locally from a live but read-only look at the screen
# --------------------------------------------------------------------------

@dataclass
class Step:
    """One concrete action, bound to one concrete control. Nothing here is
    resolved again at run() time except to VERIFY it still matches - the
    identity was decided at plan() time, not guessed at run() time."""
    window: str
    control: str            # the accessible name, as read from the tree
    automation_id: str       # empty string if the control has none
    action: str              # "click" | "type" | "select" | "read"
    value: Optional[str] = None
    why: str = ""
    heavy: bool = False

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Plan:
    goal: str
    window: str
    steps: list = field(default_factory=list)
    # Requests that named a control the tree did not have. These are NOT
    # steps and will not run - describe() must say so plainly, because a
    # silently-dropped step is a plan that does something other than what
    # it claims.
    unmatched: list = field(default_factory=list)
    if_refused: str = ""

    @property
    def weight(self) -> str:
        return "heavy" if any(s.heavy for s in self.steps) else "normal"

    def as_dict(self) -> dict:
        d = asdict(self)
        d["weight"] = self.weight
        return d


# How many levels deep _default_read walks below the window itself. Direct
# children only (the original shape here) sees almost nothing in a real
# Windows app: WPF, WinUI and most Win32 dialogs nest their actual controls
# inside panes, group boxes, toolbars and tab items several levels down, so
# every one of them was reported "not found" at plan() time - not because
# the control was not on screen, but because this never looked past the
# window's immediate children. Unbounded recursion is the other failure
# mode (a virtualised list or a deeply nested layout can be very large); an
# explicit, generous-but-finite depth is the middle ground.
_READ_DEPTH = 8


def _default_read(window: str) -> list:
    """The real accessibility-tree read. Windows-only, imported lazily so
    this module loads fine on any platform and fails clearly, not with an
    ImportError three frames down, when nobody injected a `read`."""
    try:
        import uiautomation as auto  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "no UI reader was given and 'uiautomation' is not installed - "
            "this only works on a real Windows desktop with that package "
            "present, or with a `read` function supplied for testing"
        ) from exc
    top = auto.WindowControl(searchDepth=1, Name=window)
    if not top.Exists(maxSearchSeconds=2):
        return []
    out = []

    def walk(parent, depth: int) -> None:
        if depth <= 0:
            return
        for c in parent.GetChildren():
            out.append({
                "name": c.Name,
                "automation_id": getattr(c, "AutomationId", "") or "",
                "control_type": c.ControlTypeName,
                "enabled": bool(c.IsEnabled),
            })
            walk(c, depth - 1)

    walk(top, _READ_DEPTH)
    return out


def _default_act(step: Step) -> Optional[str]:
    """Returns the read-back text for a "read" step, None for every other
    action - `run()` folds a non-None return into that step's own `value`
    before it is reported as done."""
    try:
        import uiautomation as auto  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "no `act` function was given and 'uiautomation' is not "
            "installed - see _default_read"
        ) from exc
    top = auto.WindowControl(searchDepth=1, Name=step.window)
    # top.Control(...) is the real search API (an instance method that
    # returns a plain Control, not a Name/AutomationId-specific subclass) -
    # verified against the library's own source, since a wrong guess here
    # fails silently on a real Windows machine, not in any test this
    # project can run.
    ctrl = (top.Control(AutomationId=step.automation_id) if step.automation_id
            else top.Control(Name=step.control))
    if step.action == "click":
        ctrl.Click()
    elif step.action == "type":
        ctrl.SendKeys(step.value or "")
    elif step.action == "select":
        # A plain Control (what .Control() above returns) has no .Select()
        # method at all - that only exists on specific typed subclasses
        # (e.g. ComboBoxControl), none of which this module ever
        # instantiates. GetPattern(SelectionItemPattern) is the one call
        # that works on any Control - it selects THIS control as the chosen
        # item in its container, which matches how a "select" step already
        # names the specific item to select at plan() time, not a separate
        # dropdown-plus-item-name pair.
        pattern = ctrl.GetPattern(auto.PatternId.SelectionItemPattern)
        if pattern is None:
            raise RuntimeError(f'"{step.control}" does not support being selected')
        pattern.Select()
    elif step.action == "read":
        pattern = ctrl.GetPattern(auto.PatternId.ValuePattern)
        return pattern.Value if pattern is not None else ctrl.Name
    else:
        raise ValueError(f"unknown action {step.action!r}")
    return None


def _find(tree: list, name: str) -> Optional[dict]:
    for c in tree:
        if c.get("name") == name:
            return c
    return None


def plan(goal: str, window: str, requests: list,
         *, read: Optional[Callable[[str], list]] = None) -> Plan:
    """Work out the concrete steps. Reads the screen; sends no input.

    `requests` is a list of dicts, each naming what the caller wants to
    happen, in the owner's or Jarvis's own words - not yet bound to anything
    real:

        {"control": "Send", "action": "click", "why": "..."}
        {"control": "Subject", "action": "type", "value": "...", "why": "...",
         "irreversible": False, "leaves_machine": False}

    Every request is checked against the CURRENT tree right now. A control
    that is not there yet - or not there any more - is not guessed at; it is
    reported in `unmatched` and simply does not become a step.
    """
    getter = read or _default_read
    tree = getter(window) or []
    steps, unmatched = [], []
    for r in requests:
        name = str(r.get("control", "")).strip()
        action = str(r.get("action", "")).strip()
        found = _find(tree, name)
        if not found or not found.get("enabled", True):
            unmatched.append({**r, "reason": "not found" if not found
                               else "found but disabled"})
            continue
        steps.append(Step(
            window=window, control=name,
            automation_id=str(found.get("automation_id") or ""),
            action=action, value=r.get("value"),
            why=str(r.get("why", "")),
            heavy=bool(r.get(IRREVERSIBLE_HINT)) or bool(r.get(LEAVES_MACHINE_HINT)),
        ))
    return Plan(
        goal=str(goal), window=str(window), steps=steps, unmatched=unmatched,
        if_refused="nothing in this window changes; the goal is not attempted")


def describe(p: Plan) -> str:
    """The card text. Every step in full, in the order it would run."""
    lines = [f"Jarvis would like to do this in the window \"{p.window}\": {p.goal}",
             "",
             f"{len(p.steps)} step(s), weight: {p.weight}.",
             ""]
    if not p.steps:
        lines.append("No requested control could be matched, so nothing "
                      "would happen.")
    for i, s in enumerate(p.steps, 1):
        target = s.control + (f" (id: {s.automation_id})" if s.automation_id else "")
        detail = f" = {s.value!r}" if s.value is not None else ""
        lines += [f"  {i}. {s.action} \"{target}\"{detail}{'  [irreversible or leaves the machine]' if s.heavy else ''}",
                  f"     why: {s.why}", ""]
    if p.unmatched:
        lines.append(f"{len(p.unmatched)} requested step(s) could NOT be "
                      "matched to anything on screen right now, and will "
                      "NOT run:")
        for u in p.unmatched:
            lines.append(f"  - \"{u.get('control')}\": {u.get('reason')}")
        lines.append("")
    lines.append(f"If you say no: {p.if_refused}")
    return "\n".join(lines)


# --------------------------------------------------------------------------
#   Execution - only the enumerated steps, re-verified just before each one
# --------------------------------------------------------------------------

def run(p: Plan, *, read: Optional[Callable[[str], list]] = None,
        act: Optional[Callable[[Step], None]] = None,
        announce: Optional[Callable[[str], None]] = None,
        checkpoint: Optional[Callable[[], Optional[str]]] = None,
        approved: bool = False) -> dict:
    """Execute an approved plan, one step at a time.

    `approved` has no default of True, same reason as jarvis_research.py: a
    module that can act on the world must not be one call away from doing it
    by accident.

    Before EVERY step, the live tree is re-read and the target must still
    exist, still be enabled, and still carry the same automation id (or name,
    if it never had one). If it does not, execution STOPS at that step -
    steps already done are reported as done, the failing step and everything
    after it are reported as not run, and nothing here decides what to do
    about it. That is a new plan() and a new decision.

    `announce(text)`, if given, is called just before each step with a short
    human sentence - this is the hook a caller wires to
    `jarvis_events.set_activity("working", text)` so the owner can see, live,
    that Jarvis is in the middle of doing this. Not wiring it up does not
    disable the safety checks; it only means nobody is told while it runs.

    `checkpoint()`, if given, is read at that same point, before the live
    tree re-read - see docs/AUTONOMY-PROPOSALS.md section 3d, "no new
    architecture, one more read at a point that already exists." A caller
    wires it to `lambda: jarvis_task_control.checkpoint(task_id)`; this
    module has no idea what a task id is and imports nothing to find out,
    the same way it has no idea what `jarvis_events.set_activity` is for
    `announce`. A "stop" ends the run exactly like a failed re-verification
    does. A "pause" ends it the same way but with `paused: True` in the
    result - the steps not yet run stay reported, ready for one explicit
    "continue" decision to become a fresh, approved run() rather than
    resuming on their own.
    """
    if not approved:
        return {"ok": False, "reason": "not approved; nothing was done",
                "plan": p.as_dict()}
    getter = read or _default_read
    actor = act or _default_act
    tell = announce or (lambda _text: None)
    check = checkpoint or (lambda: None)

    done = []
    for i, step in enumerate(p.steps, 1):
        # The checkpoint comes FIRST, before the announcement. It used to
        # come second, and `announce` is wired to
        # `jarvis_events.set_activity("working", text)`, which is sticky -
        # so a pause left the Brain window saying "Step 4/6: click Send"
        # about a step that never ran, and went on saying it.
        signal = check()
        if signal in ("stop", "pause"):
            remaining = p.steps[i - 1:]
            result = {"ok": False,
                      "reason": ("stopped by request" if signal == "stop"
                                 else "paused by request - resuming needs a new decision"),
                      "done": [s.as_dict() for s in done],
                      "not_run": [s.as_dict() for s in remaining]}
            if signal == "pause":
                result["paused"] = True
            return result
        tell(f"Step {i}/{len(p.steps)}: {step.action} \"{step.control}\" "
             f"in {step.window}")
        tree = getter(step.window) or []
        current = _find(tree, step.control)
        same_control = (
            current is not None
            and current.get("enabled", True)
            and str(current.get("automation_id") or "") == step.automation_id
        )
        if not same_control:
            remaining = p.steps[i - 1:]
            return {"ok": False,
                    "reason": (f"step {i} (\"{step.control}\" in "
                               f"{step.window}) no longer matches what was "
                               "planned - stopping rather than guessing"),
                    "done": [s.as_dict() for s in done],
                    "not_run": [s.as_dict() for s in remaining]}
        try:
            read_back = actor(step)
        except Exception as exc:
            remaining = p.steps[i - 1:]
            return {"ok": False,
                    "reason": f"step {i} failed: {type(exc).__name__}: {exc}",
                    "done": [s.as_dict() for s in done],
                    "not_run": [s.as_dict() for s in remaining]}
        if step.action == "read" and read_back is not None:
            # `value` already means "the text this step carries" for
            # "type" - reusing it for "read"'s result needs no new field on
            # Step, and describe()/as_dict() already render it.
            step.value = read_back
        done.append(step)
    # One last read, so a Stop that arrived while the final step was
    # running is not simply thrown away. The plan really did finish - every
    # step ran, so `ok` stays True and nothing pretends otherwise - but the
    # owner pressed Stop and deserves to be told it was seen and was too
    # late, rather than watching it vanish. This read also SPENDS the
    # signal (see jarvis_task_control.checkpoint), which is what stops a
    # stop that missed its run from stopping the next one instead.
    late = check()
    result = {"ok": True, "done": [s.as_dict() for s in done], "not_run": []}
    if late in ("stop", "pause"):
        result["late_signal"] = late
        result["note"] = (f"a {late} arrived after the last step had already "
                          "run - the plan finished, and nothing was left undone")
        tell(f"Done. (A {late} arrived too late to change anything.)")
    else:
        tell("Done.")
    return result
