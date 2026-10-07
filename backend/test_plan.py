"""jarvis_plan.py - "one card, several steps" (I61, "the plan card"; the
owner's own words, 2026-09-28).

    python3 backend/test_plan.py

What it proves: propose() refuses on outside text and on anything malformed;
describe() shows every step in full, marking which ones ask again; run()
executes only the steps that need no card of their own on the strength of
the one card that started things, and stops the whole run - never skipping,
never continuing past it - the moment a risky or result-filled step's own
card is not approved; the plan grants nothing for later (no auto-resume);
and `enabled()` refuses until a real safety-test result clears the bar,
with a plain reason every time, never a bare False.
"""
import json
import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jarvis_plan as P

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


class Verdict:
    def __init__(self, allowed, outcome="approved"):
        self.allowed, self.outcome = allowed, outcome


STEPS = [
    {"tool": "web_search", "args": {"q": "garage insulation installers"}, "why": "find installers"},
    {"tool": "send_email", "args": {"to": "x@example.com"}, "why": "ask for a quote", "risky": True},
]


def t_propose_refuses_on_outside_text():
    try:
        P.propose("do a thing", STEPS, tainted=True)
        check("propose() refuses when the turn read outside text", False)
    except P.Refused as exc:
        check("propose() refuses when the turn read outside text", True)
        check("  ...with a plain sentence naming why", "own words" in str(exc), str(exc))


def t_propose_validates_shape():
    cases = [
        ("", STEPS, "no goal"),
        ("x" * (P.MAX_TEXT + 1), STEPS, "goal too long"),
        ("goal", [], "no steps"),
        ("goal", "not a list", "steps not a list"),
        ("goal", [{"tool": "x"} for _ in range(P.MAX_STEPS + 1)], "too many steps"),
        ("goal", [{"args": {}}], "a step with no tool"),
        ("goal", [{"tool": "x"}], "a step with no why"),
        ("goal", [{"tool": "x", "why": "y" * (P.MAX_TEXT + 1)}], "a why too long"),
        ("goal", [{"tool": "x", "why": "y", "from_step": 5}], "from_step points nowhere"),
        ("goal", [{"tool": "x", "why": "y", "from_step": -1}], "from_step negative"),
        ("goal", [{"tool": "x", "why": "y", "from_step": True}], "from_step a bool"),
    ]
    for goal, steps, label in cases:
        try:
            P.propose(goal, steps)
            check(f"refused: {label}", False)
        except P.Refused as exc:
            check(f"refused: {label}", True)
            check(f"  ...with a plain sentence ({label})", str(exc) not in ("", "Refused"), repr(exc))


def t_a_valid_plan_is_shaped_correctly():
    p = P.propose("insulate the garage", STEPS)
    check("two steps", len(p.steps) == 2)
    check("the first step needs no card of its own", not p.steps[0].needs_own_card)
    check("the risky step needs its own card", p.steps[1].needs_own_card)
    check("from_step defaults to None", p.steps[0].from_step is None)


def t_from_step_forces_its_own_card_even_if_not_marked_risky():
    steps = [
        {"tool": "web_search", "args": {}, "why": "find the price"},
        {"tool": "send_email", "args": {"body": "{{step 1}}"},
         "why": "tell them the price we found", "from_step": 0},  # NOT marked risky
    ]
    p = P.propose("do a thing", steps)
    check("a step filled in from an earlier result needs its own card, "
         "whatever `risky` says", p.steps[1].needs_own_card and not p.steps[1].risky)


def t_describe_shows_every_step_and_marks_which_ask_again():
    p = P.propose("insulate the garage", STEPS)
    text = P.describe(p)
    check("names the goal", "insulate the garage" in text)
    check("shows step 1 in full", "find installers" in text)
    check("shows step 2 in full", "ask for a quote" in text)
    check("marks the risky step as asking again", "risky step" in text)
    check("says what happens on no", "nothing here happens" in text)


def t_describe_marks_a_result_filled_step_distinctly():
    steps = [
        {"tool": "web_search", "args": {}, "why": "find the price"},
        {"tool": "send_email", "args": {"body": "The price: {{step 1}}"}, "why": "tell them",
         "from_step": 0},
    ]
    p = P.propose("do a thing", steps)
    text = P.describe(p)
    check("names which earlier step it depends on", "step 1" in text.lower())


def t_the_card_shows_every_steps_arguments_in_full():
    """Bug audit 2026-09-28, F1: the card showed `tool - why` only, so a safe
    step ran with values the owner never saw."""
    steps = [{"tool": "append_obsidian_daily", "args": {"text": "Called the roofer at 3pm"},
              "why": "log it"},
             {"tool": "web_search", "args": {"query": "roofers near me"}, "why": "find more"},
             {"tool": "calendar_read", "why": "check the week"}]
    text = P.describe(P.propose("sort the roof", steps))
    check("the note's exact text is on the card", "Called the roofer at 3pm" in text, text)
    check("the search words are on the card", "roofers near me" in text, text)
    check("a step with no arguments says so rather than showing nothing",
          "(nothing else)" in text, text)


def t_a_result_filled_step_must_say_where_the_result_goes():
    """Bug audit 2026-09-28, F3: from_step was only a flag. Now the step names
    the argument the earlier result goes into ("{{step N}}"), or is refused."""
    cases = [
        ([{"tool": "web_search", "args": {"query": "x"}, "why": "a"},
          {"tool": "append_obsidian_daily", "args": {"text": "found it"}, "why": "b",
           "from_step": 0}], "from_step with no {{step N}} anywhere"),
        ([{"tool": "web_search", "args": {"query": "x"}, "why": "a"},
          {"tool": "web_search", "args": {"query": "y"}, "why": "a"},
          {"tool": "append_obsidian_daily", "args": {"text": "{{step 1}}"}, "why": "b",
           "from_step": 1}], "{{step N}} naming a different step than from_step"),
        ([{"tool": "web_search", "args": {"query": "x"}, "why": "a"},
          {"tool": "append_obsidian_daily", "args": {"text": "{{step 1}}"}, "why": "b"}],
         "{{step N}} with no from_step"),
    ]
    for steps, label in cases:
        try:
            P.propose("goal", steps)
            check(f"refused: {label}", False)
        except P.Refused as exc:
            check(f"refused: {label}, in plain words", "step" in str(exc), str(exc))
    p = P.propose("goal", [{"tool": "web_search", "args": {"query": "x"}, "why": "a"},
                           {"tool": "append_obsidian_daily",
                            "args": {"text": "Price: {{ step 1 }}", "tags": ["{{step 1}}"]},
                            "why": "b", "from_step": 0}])
    check("a well-formed one is accepted (spaces and nested lists allowed)",
          p.steps[1].from_step == 0)
    text = P.describe(p)
    check("... and its card says where the real result goes",
          "Where it says {{step 1}}" in text, text)


def t_a_result_filled_step_really_receives_the_earlier_result():
    """F3: the step that is asked about on its own card, and the step that
    runs, both hold step 1's real result - never the proposal-time text."""
    p = P.propose("goal", [{"tool": "web_search", "args": {"query": "price"}, "why": "a"},
                           {"tool": "append_obsidian_daily",
                            "args": {"text": "Found: {{step 1}}"}, "why": "b",
                            "from_step": 0}])
    asked, ran = [], []

    def run_step(step):
        ran.append(dict(step.args))
        return {"ok": True, "price": "42 pounds"} if step.tool == "web_search" else {"ok": True}

    out = P.run(p, run_step=run_step,
                gate_check=lambda s: asked.append(dict(s.args)) or Verdict(True),
                approved=True)
    want = 'Found: {"ok": true, "price": "42 pounds"}'
    check("its own card was asked with the real value", asked == [{"text": want}], asked)
    check("and it ran with the same real value", ran[-1] == {"text": want}, ran)
    check("the plan's record shows the value it really used",
          out["done"][1]["args"] == {"text": want}, out["done"])
    check("the plan itself is unchanged (a later run starts from the proposal again)",
          p.steps[1].args == {"text": "Found: {{step 1}}"})
    long = P.result_text({"x": "y" * (P.MAX_FILL + 50)})
    check("a long result is cut, and says so",
          len(long) <= P.MAX_FILL + 20 and long.endswith("[cut short]"))


def t_run_without_approval_does_nothing():
    p = P.propose("insulate the garage", STEPS)
    calls = []
    out = P.run(p, run_step=lambda s: calls.append(s) or {"ok": True}, approved=False)
    check("nothing ran", calls == [])
    check("not ok", out["ok"] is False)
    check("every step reported not_run", len(out["not_run"]) == 2)


def t_safe_steps_run_on_the_one_card_no_risky_step_runs_without_its_own():
    ran = []
    def run_step(step):
        ran.append(step.tool)
        return {"ok": True}
    gate_calls = []
    def gate_check(step):
        gate_calls.append(step.tool)
        return Verdict(True)
    p = P.propose("insulate the garage", STEPS)
    out = P.run(p, run_step=run_step, gate_check=gate_check, approved=True)
    check("the plan finished", out["ok"] is True)
    check("both steps ran", ran == ["web_search", "send_email"])
    check("only the risky step's own card was raised", gate_calls == ["send_email"])


def t_a_denied_risky_step_stops_the_whole_run_steps_already_done_stay_done():
    ran = []
    p = P.propose("insulate the garage", STEPS)
    out = P.run(p, run_step=lambda s: ran.append(s.tool) or {"ok": True},
               gate_check=lambda s: Verdict(False, "denied"), approved=True)
    check("stopped, not ok", out["ok"] is False)
    check("only the safe step ran before the denial", ran == ["web_search"])
    check("the safe step is reported done", len(out["done"]) == 1)
    check("the risky step is reported not run", len(out["not_run"]) == 1)
    check("the reason names the outcome", "denied" in out["reason"])


def t_a_risky_step_with_no_gate_check_stops_rather_than_skipping():
    p = P.propose("insulate the garage", STEPS)
    out = P.run(p, run_step=lambda s: {"ok": True}, gate_check=None, approved=True)
    check("stopped rather than silently running the risky step", out["ok"] is False)
    check("only the safe step is reported done", len(out["done"]) == 1)


def t_a_result_filled_step_gets_its_own_card_even_though_the_first_is_safe():
    steps = [
        {"tool": "web_search", "args": {}, "why": "find the price"},
        {"tool": "send_email", "args": {"body": "The price: {{step 1}}"}, "why": "tell them",
         "from_step": 0},
    ]
    p = P.propose("do a thing", steps)
    gate_calls = []
    out = P.run(p, run_step=lambda s: {"ok": True},
               gate_check=lambda s: gate_calls.append(s.tool) or Verdict(True), approved=True)
    check("the result-filled step's own card was raised", gate_calls == ["send_email"])
    check("the plan still finished", out["ok"] is True)


def t_checkpoint_stop_ends_the_run_at_the_next_step_steps_done_stay_done():
    ran = []
    signals = iter(["", "stop"])
    p = P.propose("insulate the garage", STEPS)
    out = P.run(p, run_step=lambda s: ran.append(s.tool) or {"ok": True},
               gate_check=lambda s: Verdict(True),
               checkpoint=lambda: next(signals, "stop"), approved=True)
    check("stopped before the second step", ran == ["web_search"])
    check("not ok", out["ok"] is False)
    check("reason says stopped by request", "stopped" in out["reason"])


def t_a_failed_step_stops_the_run_and_names_the_failure():
    def boom(step):
        raise RuntimeError("network down")
    p = P.propose("insulate the garage", STEPS)
    out = P.run(p, run_step=boom, approved=True)
    check("stopped on the failure", out["ok"] is False)
    check("names the exception", "RuntimeError" in out["reason"])
    check("nothing after it ran", len(out["not_run"]) == 2)


def t_a_late_stop_after_the_last_step_does_not_undo_anything():
    p = P.propose("insulate the garage", [STEPS[0]])
    signals = iter(["", "stop"])
    out = P.run(p, run_step=lambda s: {"ok": True},
               checkpoint=lambda: next(signals, ""), approved=True)
    check("the plan still reports done", out["ok"] is True)
    check("the late signal is named, not hidden", out.get("late_signal") == "stop")


def t_finishing_grants_nothing_for_later_no_state_carries_between_runs():
    p = P.propose("insulate the garage", STEPS)
    out1 = P.run(p, run_step=lambda s: {"ok": True},
                gate_check=lambda s: Verdict(False), approved=True)
    check("first run stopped at the risky step", out1["ok"] is False)
    # Nothing in this module remembers that decision - approving the SAME
    # plan object again is a fresh, independent run, exactly like calling
    # run() a first time. There is no partial-resume state anywhere to leak.
    ran = []
    out2 = P.run(p, run_step=lambda s: ran.append(s.tool) or {"ok": True},
                gate_check=lambda s: Verdict(True), approved=True)
    check("a fresh approved run starts from step one again, not mid-plan",
         ran == ["web_search", "send_email"])
    check("second run finished", out2["ok"] is True)


# --------------------------------------------------------------------------
#   The safety gate
# --------------------------------------------------------------------------

def _write(tmp, doc):
    p = Path(tmp) / "results.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    return p


def t_enabled_refuses_with_no_results_file():
    with tempfile.TemporaryDirectory() as tmp:
        ok, why = P.enabled(results_path=Path(tmp) / "nope.json")
        check("refused: no file", ok is False)
        check("  ...names what to run", "tool_eval" in why, why)


def t_enabled_refuses_on_an_unreadable_file():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "results.json"
        p.write_text("not json", encoding="utf-8")
        ok, why = P.enabled(results_path=p)
        check("refused: unreadable", ok is False)
        check("  ...says so plainly, not a stack trace", "could not be read" in why, why)


def t_enabled_refuses_with_no_result_for_this_model():
    with tempfile.TemporaryDirectory() as tmp:
        doc = {"models": {"some-other-model": {"summary": {"full": {}}}}}
        p = _write(tmp, doc)
        ok, why = P.enabled("jarvis-primary", results_path=p)
        check("refused: model not in the file", ok is False)


def t_enabled_refuses_below_the_multi_step_bar():
    with tempfile.TemporaryDirectory() as tmp:
        doc = {"models": {"jarvis-primary": {"summary": {"full": {
            "multi": {"pass": 5, "of": 10}, "injection": {"carried": 0}}}}}}
        p = _write(tmp, doc)
        ok, why = P.enabled("jarvis-primary", results_path=p)
        check("refused: below the pass rate", ok is False)
        check("  ...names the real numbers", "5/10" in why, why)


def t_enabled_refuses_on_any_carried_injection():
    with tempfile.TemporaryDirectory() as tmp:
        doc = {"models": {"jarvis-primary": {"summary": {"full": {
            "multi": {"pass": 10, "of": 10}, "injection": {"carried": 1}}}}}}
        p = _write(tmp, doc)
        ok, why = P.enabled("jarvis-primary", results_path=p)
        check("refused: a planted instruction was carried, even once", ok is False)
        check("  ...zero tolerance, not a rate", "1" in why, why)


def t_enabled_says_yes_once_the_real_bars_are_cleared():
    with tempfile.TemporaryDirectory() as tmp:
        doc = {"models": {"jarvis-primary": {"summary": {"full": {
            "multi": {"pass": 10, "of": 10}, "injection": {"carried": 0}}}}}}
        p = _write(tmp, doc)
        ok, why = P.enabled("jarvis-primary", results_path=p)
        check("enabled once both bars clear", ok is True, why)
        check("no reason needed when it says yes", why == "")


def t_enabled_finds_the_result_where_the_runner_publishes_it():
    """2026-10-06: the runner saves beside itself (inside the repository) and
    the backend looks for the file in the config folder - different folders on
    the owner's PC - so a real, passed run could never satisfy this gate. The
    reader now searches, and the runner publishes a copy. This checks the
    searching half; nothing here touches the owner's real folder."""
    import os
    doc = {"models": {"jarvis-primary": {"summary": {"full": {
        "multi": {"pass": 10, "of": 10}, "injection": {"carried": 0}}}}}}
    keep = {k: os.environ.get(k) for k in (P.RESULTS_ENV, "OPENJARVIS_CONFIG_DIR")}
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.environ["OPENJARVIS_CONFIG_DIR"] = tmp
            os.environ.pop(P.RESULTS_ENV, None)
            check("the config folder is one of the places searched",
                  (Path(tmp) / P.RESULTS_NAME) in P._candidate_paths(),
                  P._candidate_paths())
            # A missing override: refused, and the sentence names the file.
            os.environ[P.RESULTS_ENV] = str(Path(tmp) / "missing.json")
            ok, why = P.enabled("jarvis-primary")
            check("refused with nothing at the override path", ok is False)
            check("  ...and the sentence names the file it looks for",
                  P.RESULTS_NAME in why, why)
            # The override, once it holds a passed run: the gate opens.
            good = Path(tmp) / "elsewhere.json"
            good.write_text(json.dumps(doc), encoding="utf-8")
            os.environ[P.RESULTS_ENV] = str(good)
            ok, why = P.enabled("jarvis-primary")
            check("the override is read", ok is True, why)
            # A config-folder copy with no result for this model: still refused.
            (Path(tmp) / P.RESULTS_NAME).write_text(
                json.dumps({"models": {"other": {"summary": {}}}}), encoding="utf-8")
            os.environ.pop(P.RESULTS_ENV, None)
            ok, why = P.enabled("jarvis-primary")
            check("a copy that names another model does not open the gate",
                  ok is False, why)
        finally:
            for k, v in keep.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


def main() -> int:
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"--- {name} ---")
            try:
                fn()
            except Exception as exc:  # pragma: no cover
                traceback.print_exc()
                check(f"{name} ran without crashing", False, repr(exc))
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
