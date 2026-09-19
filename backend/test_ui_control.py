"""jarvis_ui_control.py, and the promise that it never improvises a step.

Three things are being proven, not just the happy path: plan() sends no
input at all, run() refuses without approval, and run() STOPS the moment the
live screen stops matching what was planned - it never guesses or clicks the
nearest thing.

    python3 test_ui_control.py
"""
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jarvis_ui_control as U

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def tree(*controls):
    """A fake accessibility tree: each control is (name, automation_id, enabled)."""
    return [{"name": n, "automation_id": a, "control_type": "Button", "enabled": e}
            for (n, a, e) in controls]


class NoRealAction:
    """Fail loudly if the default (real, Windows-only) reader or actor is
    ever reached - proves every test below only exercises injected fakes."""

    def __enter__(self):
        self.real_read, self.real_act = U._default_read, U._default_act
        def boom_read(_w):
            raise AssertionError("the real accessibility-tree reader ran")
        def boom_act(_s):
            raise AssertionError("the real input-sender ran")
        U._default_read, U._default_act = boom_read, boom_act
        return self

    def __exit__(self, *a):
        U._default_read, U._default_act = self.real_read, self.real_act
        return False


def t_planning_sends_no_input():
    calls = []
    def read(window):
        calls.append(window)
        return tree(("Send", "btnSend", True), ("Subject", "txtSubject", True))
    with NoRealAction():
        p = U.plan("send the draft", "Outlook - Compose",
                   [{"control": "Subject", "action": "type", "value": "hi",
                     "why": "fill in the subject line"},
                    {"control": "Send", "action": "click", "why": "send it",
                     "irreversible": True}],
                   read=read)
    check("plan() only reads, once per window asked about", calls == ["Outlook - Compose"])
    check("both requests matched", len(p.steps) == 2, repr(p.steps))
    check("nothing unmatched", p.unmatched == [], repr(p.unmatched))
    check("the irreversible step is marked heavy",
          [s.heavy for s in p.steps if s.control == "Send"] == [True])
    check("plan weight is heavy because one step is",
          p.weight == "heavy", p.weight)


def t_unmatched_requests_do_not_become_steps():
    def read(window):
        return tree(("Send", "btnSend", True))
    with NoRealAction():
        p = U.plan("send the draft", "Outlook - Compose",
                   [{"control": "Send", "action": "click", "why": "send it"},
                    {"control": "Attach", "action": "click", "why": "attach a file"}],
                   read=read)
    check("only the real control becomes a step", len(p.steps) == 1, repr(p.steps))
    check("the missing one is reported, not silently dropped",
          len(p.unmatched) == 1 and p.unmatched[0]["control"] == "Attach",
          repr(p.unmatched))
    card = U.describe(p)
    check("the card says what will NOT run", "will\nNOT run" in card or "NOT run" in card, card)
    check("the card names the missing control", "Attach" in card, card)


def t_disabled_control_is_treated_as_unmatched():
    def read(window):
        return tree(("Send", "btnSend", False))
    with NoRealAction():
        p = U.plan("send", "Outlook - Compose",
                   [{"control": "Send", "action": "click", "why": "send it"}],
                   read=read)
    check("a disabled control is not turned into a step", p.steps == [], repr(p.steps))
    check("and the reason says so",
          p.unmatched[0]["reason"] == "found but disabled", repr(p.unmatched))


def t_the_card_prints_every_step_in_full():
    def read(window):
        return tree(("Send", "btnSend", True))
    with NoRealAction():
        p = U.plan("send it", "Outlook - Compose",
                   [{"control": "Send", "action": "click", "why": "because the draft is ready"}],
                   read=read)
    card = U.describe(p)
    check("the control name is on the card", "Send" in card, card)
    check("the action is on the card", "click" in card, card)
    check("the reason is on the card", "because the draft is ready" in card, card)
    check("the window is named", "Outlook - Compose" in card, card)
    check("the card says what refusing costs", "If you say no" in card, card)


def t_run_refuses_without_approval():
    def read(window):
        return tree(("Send", "btnSend", True))
    with NoRealAction():
        p = U.plan("send", "W", [{"control": "Send", "action": "click", "why": "x"}], read=read)
        out = U.run(p, read=read, act=lambda s: (_ for _ in ()).throw(
            AssertionError("act() ran without approval")))
    check("run() does nothing without approval", out["ok"] is False, repr(out))
    check("and says so plainly", "not approved" in out["reason"], out["reason"])


def t_run_re_verifies_before_every_step_and_stops_on_mismatch():
    # Both controls are there and enabled at plan() time. By the time run()
    # re-checks right before step 2, "Send" has been disabled - a dialog
    # popped up and is blocking it, say. run() must stop AT that step, not
    # push through on what plan() saw a moment ago.
    plan_tree = tree(("Attach", "btnAttach", True), ("Send", "btnSend", True))
    calls = {"n": 0}
    def read(window):
        calls["n"] += 1
        if calls["n"] == 1:
            return tree(("Attach", "btnAttach", True))     # step 1 check: fine
        return tree(("Send", "btnSend", False))              # step 2 check: now disabled
    acted = []
    with NoRealAction():
        p = U.plan("attach and send", "W",
                   [{"control": "Attach", "action": "click", "why": "attach"},
                    {"control": "Send", "action": "click", "why": "send"}],
                   read=lambda _w: plan_tree)
        out = U.run(p, read=read, act=lambda s: acted.append(s.control),
                    approved=True)
    check("the first step, still valid, ran", acted == ["Attach"], repr(acted))
    check("run() reports failure rather than pushing through",
          out["ok"] is False, repr(out))
    check("it names which step stopped it", "step 2" in out["reason"] and "Send" in out["reason"],
          out["reason"])
    check("it reports exactly one step done", len(out["done"]) == 1, repr(out["done"]))
    check("and exactly one step not run", len(out["not_run"]) == 1, repr(out["not_run"]))


def t_run_executes_the_approved_steps_in_order():
    live = tree(("Subject", "txtSubject", True), ("Send", "btnSend", True))
    acted = []
    with NoRealAction():
        p = U.plan("send", "W",
                   [{"control": "Subject", "action": "type", "value": "hi", "why": "x"},
                    {"control": "Send", "action": "click", "why": "y"}],
                   read=lambda _w: live)
        out = U.run(p, read=lambda _w: live, act=lambda s: acted.append((s.control, s.action)),
                    approved=True)
    check("CONTROL: an approved, still-matching plan runs every step",
          out["ok"] is True and acted == [("Subject", "type"), ("Send", "click")],
          repr((out, acted)))
    check("done lists both steps, nothing left not-run",
          len(out["done"]) == 2 and out["not_run"] == [], repr(out))


class _FakeElement:
    def __init__(self, name, children=None):
        self.Name = name
        self.AutomationId = name
        self.ControlTypeName = "Button"
        self.IsEnabled = True
        self._children = children or []

    def GetChildren(self):
        return self._children

    def Exists(self, maxSearchSeconds=2):
        return True


def t_default_read_walks_several_levels_deep_but_not_unbounded():
    """The bug this guards against: the original _default_read only ever
    called top.GetChildren() once - direct children of the window. Most
    real Windows apps (WPF, WinUI, most Win32 dialogs) nest their actual
    controls several levels inside panes and group boxes, so plan() would
    report every one of them "not found" despite being on screen. Proven
    here against a fake `uiautomation` module (this is _default_read
    itself, the one thing in this file that is NOT reachable through the
    injectable `read`/`act` parameters everything else in this suite
    uses) rather than a real Windows session."""
    # Nest a control 3 levels below the window, and one right at the depth
    # boundary (_READ_DEPTH levels down) that must NOT show up.
    deepest = _FakeElement("TooDeep")
    chain = deepest
    for i in range(U._READ_DEPTH):
        chain = _FakeElement(f"level{i}", children=[chain])
    nested = _FakeElement("NestedButton")
    top_children = [_FakeElement("Pane", children=[_FakeElement("GroupBox", children=[nested])]),
                    chain]

    class FakeAuto:
        @staticmethod
        def WindowControl(searchDepth, Name):
            return _FakeElement(Name, children=top_children)

    real_module = sys.modules.get("uiautomation")
    sys.modules["uiautomation"] = FakeAuto()
    try:
        out = U._default_read("SomeWindow")
    finally:
        if real_module is not None:
            sys.modules["uiautomation"] = real_module
        else:
            del sys.modules["uiautomation"]
    names = {c["name"] for c in out}
    check("a control 3 levels below the window is found",
          "NestedButton" in names, repr(names))
    check("a control past the depth bound is not found (bounded, not unbounded, recursion)",
          "TooDeep" not in names, repr(names))


def t_a_read_steps_result_reaches_the_caller():
    """The bug this guards against: `act`'s default implementation used to
    do `elif step.action == "read": pass` - a step the model can genuinely
    request (it is in the tool's own JSON schema) that always ran
    "successfully" and reported nothing at all, because run() never had
    anywhere to put a value even if `act` produced one. Fixed on both ends:
    the actor now returns the read text, and run() folds a non-None return
    into that step's own `value` before it goes into `done`."""
    live = tree(("OutputBox", "txtOutput", True))
    with NoRealAction():
        p = U.plan("check the result", "W",
                   [{"control": "OutputBox", "action": "read", "why": "x"}],
                   read=lambda _w: live)
        out = U.run(p, read=lambda _w: live, act=lambda s: "the value on screen",
                     approved=True)
    check("the run succeeded", out["ok"] is True, repr(out))
    check("the read-back text reaches the done step, not silently dropped",
          out["done"][0]["value"] == "the value on screen", repr(out))
    # CONTROL: an actor that returns None for a non-read action must not
    # accidentally overwrite that step's own value.
    live2 = tree(("Subject", "txtSubject", True))
    with NoRealAction():
        p2 = U.plan("send", "W",
                    [{"control": "Subject", "action": "type", "value": "hi", "why": "x"}],
                    read=lambda _w: live2)
        out2 = U.run(p2, read=lambda _w: live2, act=lambda s: None, approved=True)
    check("CONTROL: a non-read step's own value survives untouched",
          out2["done"][0]["value"] == "hi", repr(out2))


def t_announce_is_called_once_per_step_and_is_optional():
    live = tree(("Send", "btnSend", True))
    heard = []
    with NoRealAction():
        p = U.plan("send", "W", [{"control": "Send", "action": "click", "why": "x"}],
                   read=lambda _w: live)
        out = U.run(p, read=lambda _w: live, act=lambda s: None,
                    announce=heard.append, approved=True)
    check("announce saw the step and a final message", len(heard) == 2, repr(heard))
    check("the step text names the control", "Send" in heard[0], heard[0])
    # CONTROL: omitting announce must not raise or change the result.
    with NoRealAction():
        p2 = U.plan("send", "W", [{"control": "Send", "action": "click", "why": "x"}],
                    read=lambda _w: live)
        out2 = U.run(p2, read=lambda _w: live, act=lambda s: None, approved=True)
    check("CONTROL: no announce given still runs to completion", out2["ok"] is True, repr(out2))


def t_checkpoint_stop_ends_the_run_before_the_next_step():
    live = tree(("Subject", "txtSubject", True), ("Send", "btnSend", True))
    acted = []
    signals = iter([None, "stop"])   # clean at step 1, a stop lands before step 2
    with NoRealAction():
        p = U.plan("send", "W",
                   [{"control": "Subject", "action": "type", "value": "hi", "why": "x"},
                    {"control": "Send", "action": "click", "why": "y"}],
                   read=lambda _w: live)
        out = U.run(p, read=lambda _w: live, act=lambda s: acted.append(s.control),
                    checkpoint=lambda: next(signals), approved=True)
    check("only step 1 ran", acted == ["Subject"], repr(acted))
    check("run() reports not-ok", out["ok"] is False, repr(out))
    check("the reason names a stop, not a re-verification mismatch",
          "stopped" in out["reason"], out["reason"])
    check("step 2 is reported not-run", len(out["not_run"]) == 1 and
          out["not_run"][0]["control"] == "Send", repr(out))
    check("CONTROL: a stop is not reported as a pause", "paused" not in out, repr(out))


def t_checkpoint_pause_ends_the_run_and_says_so():
    live = tree(("Subject", "txtSubject", True), ("Send", "btnSend", True))
    acted = []
    signals = iter([None, "pause"])
    with NoRealAction():
        p = U.plan("send", "W",
                   [{"control": "Subject", "action": "type", "value": "hi", "why": "x"},
                    {"control": "Send", "action": "click", "why": "y"}],
                   read=lambda _w: live)
        out = U.run(p, read=lambda _w: live, act=lambda s: acted.append(s.control),
                    checkpoint=lambda: next(signals), approved=True)
    check("only step 1 ran", acted == ["Subject"], repr(acted))
    check("run() reports not-ok", out["ok"] is False, repr(out))
    check("the result says paused", out.get("paused") is True, repr(out))
    check("step 2 is still reported, ready to resume", len(out["not_run"]) == 1, repr(out))


def t_no_checkpoint_given_behaves_exactly_as_before():
    # CONTROL: omitting checkpoint (every existing caller) must not change
    # anything - this is the regression the whole feature must not cause.
    live = tree(("Send", "btnSend", True))
    with NoRealAction():
        p = U.plan("send", "W", [{"control": "Send", "action": "click", "why": "x"}],
                   read=lambda _w: live)
        out = U.run(p, read=lambda _w: live, act=lambda s: None, approved=True)
    check("CONTROL: runs to completion with no checkpoint hook at all",
          out["ok"] is True and out["not_run"] == [], repr(out))


if __name__ == "__main__":
    for fn in (t_planning_sends_no_input, t_unmatched_requests_do_not_become_steps,
               t_disabled_control_is_treated_as_unmatched,
               t_the_card_prints_every_step_in_full, t_run_refuses_without_approval,
               t_run_re_verifies_before_every_step_and_stops_on_mismatch,
               t_run_executes_the_approved_steps_in_order,
               t_default_read_walks_several_levels_deep_but_not_unbounded,
               t_a_read_steps_result_reaches_the_caller,
               t_announce_is_called_once_per_step_and_is_optional,
               t_checkpoint_stop_ends_the_run_before_the_next_step,
               t_checkpoint_pause_ends_the_run_and_says_so,
               t_no_checkpoint_given_behaves_exactly_as_before):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
