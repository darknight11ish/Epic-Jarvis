"""jarvis_agent.py's wiring of jarvis_plan.py ("one card, several steps" -
the plan card, the owner's own words, 2026-09-28) into the `TOOLS` table as
`propose_plan`: a real, model-callable tool that stays genuinely
unreachable until `jarvis_plan.enabled()` says a real safety-test run has
cleared its two bars, even though it is registered like any other tool.

What is proven here, not assumed (CLAUDE.md's "do not claim more than the
evidence supports" - every check below drives the real `jarvis_agent.
run_local_turn()`/`_one_call()` loop, the same one every other tool's own
tests in `test_agent.py` drive, never a hand-simulated shortcut):

  - the tool is invisible/refused while `jarvis_plan.enabled()` says no -
    the shipped default, today, with no `tools/tool_eval/
    tool_eval_results.json` in this checkout - and refused BEFORE
    `jarvis_plan.propose()` (called from `Tool.prepare()`) ever runs;
  - a tainted turn is refused outright the same way, before `propose()`
    runs, whichever of the four signals (`.tainted`, `.read`,
    `.provenance`, `.app_context`) made it so;
  - a step the model did not flag `risky` (and gave no `from_step`) runs
    once, with no further card of its own, on the strength of the one
    card that started the plan;
  - a `risky` step, and separately a `from_step` one, always get their
    OWN separate card, mid-run, even inside an already-approved plan -
    and that card is asked EXACTLY once, never twice, whichever of
    `jarvis_plan.run()`'s own `gate_check`/`run_step` calls it first;
  - the real safety gap this dispatcher exists to close: a step the model
    did NOT flag risky, naming a tool whose REAL configured tier still
    needs a person, is refused rather than let through silently - trusting
    the model's own `risky` flag alone would have missed exactly this;
  - a denial anywhere stops the WHOLE run - steps already done stay done,
    nothing after it runs, including a later step that would otherwise
    have been perfectly safe;
  - a step naming send_email, draft_email, a schedule tool (set_timer) or
    another plan (propose_plan itself) is refused outright, never run
    through a shortcut around each of THEIR own bespoke pre-gate checks;
  - running a plan step for a real tool goes through THAT tool's own real
    `prepare()` - proven by a step whose arguments `home_control.prepare()`
    itself rejects, not by anything this dispatcher invents.

    python3 test_agent_plan_wiring.py
"""
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _where import require_shipped  # noqa: E402
require_shipped("jarvis_agent.py")
import jarvis_agent as AG  # noqa: E402
import jarvis_plan as PL  # noqa: E402
from test_agent import NoRealIO, FakeStream, scripted_post  # noqa: E402

# Same reasons test_agent.py/test_tool_text.py silence these: none of this
# file's turns should reach the real audit log, the real event bus, or a
# real manner lookup.
AG._manner_now = lambda *a, **k: None
AG._record_chain = lambda steps: None
AG._publish_step = lambda step: None

FAILED, PASSED = [], []
SKIPPED = []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: printed as `skip`, counted on its own,
    never as a pass. (It used to be check("SKIP - ...", True) - a condition of
    the constant True, so it printed as a pass and was counted as one.)"""
    SKIPPED.append(why)
    print(f"skip  {why}")


class _Verdict:
    """The gate's own verdict shape, after gate-outcome.patch: allowed,
    tier, action, reason, outcome, request_id."""

    def __init__(self, allowed, tier="ask", outcome=None, reason=""):
        self.allowed = allowed
        self.tier = tier
        self.reason = reason or ("approved" if allowed else "denied")
        self.outcome = outcome if outcome is not None else (
            "approved" if (allowed and tier == "ask") else
            "denied" if tier == "ask" else tier)
        self.request_id = None


def _fake_checker(rules: dict, default=None):
    """A `gate_check`/`checker` that answers by ACTION NAME, and logs every
    call it was actually asked. `rules[action]` is the verdict to give;
    `default` (or a hard denial) answers anything not named, so a step this
    test forgot to script is refused loudly rather than silently allowed."""
    calls = []

    def checker(action, detail, prompt):
        calls.append((action, detail, prompt))
        if action in rules:
            return rules[action]
        return default if default is not None else _Verdict(False, tier="ask", outcome="denied")
    return checker, calls


def _plan_turn(steps_arg, *, goal="a test plan", checker, enabled_tools=None,
               request=None):
    """One turn: the model asks for propose_plan(goal, steps_arg), gated by
    `checker`, then answers plainly. Returns (the tool result dict fed back
    to the model for the propose_plan call, jarvis_agent's own step log)."""
    responses = [
        {"choices": [{"message": {"role": "assistant", "tool_calls": [
            {"id": "1", "function": {"name": "propose_plan",
             "arguments": json.dumps({"goal": goal, "steps": steps_arg})}}]}}]},
        {"choices": [{"message": {"role": "assistant", "content": "ok"}}]},
    ]
    post, calls = scripted_post(responses)
    steps_seen = []
    with NoRealIO():
        AG.run_local_turn(
            # "provenance": "typed" - without it, a message is neither
            # "typed" nor "voice" (OWN_WORDS), which _propose_plan_refusal
            # already (correctly) treats as "not really the owner's own
            # words" and refuses. Every real app request tags this; a
            # hand-built test message must too, or every test below would
            # be testing the taint refusal by accident.
            [{"role": "user", "content": "make a plan", "provenance": "typed"}], "qwen3:8b",
            ollama_url="http://127.0.0.1:11434", stream_out=lambda b: None, post=post,
            gate_check=checker, enabled_tools=enabled_tools, request=request,
            on_step=steps_seen.append,
            open_stream=lambda url, payload: FakeStream([b'{"done":true}\n']))
    tool_msg = calls[1]["messages"][-1]
    result = json.loads(tool_msg["content"]) if tool_msg.get("role") == "tool" else None
    return result, steps_seen


# One card, always approved, for propose_plan's own action (run_plan) -
# every test below is about what happens INSIDE an already-approved plan.
_APPROVE_RUN_PLAN = {"run_plan": _Verdict(True, tier="ask", outcome="approved")}

#: The two names the checker can be asked with for the home_control tool, and
#: why there are two. On the owner's PC jarvis_agent resolves the tool's lookup
#: name through `jarvis_gate.action_for_tool()` and asks with the RESOLVED
#: action ("home_control") - 2026-10-03's fix, and the reason a real tier is
#: found at all. In a CI or repository run there is no `jarvis_gate.py` to
#: resolve with (it is not in this repository), so `jarvis_agent`'s
#: `except Exception: pass` leaves the tool's own lookup name in place
#: ("jarvis_home_control_run"). Registering both keeps every check below
#: measuring the PLAN machinery on a machine of either shape; which name really
#: arrived is asserted by `t_the_checker_is_asked_with_the_resolved_action_name`,
#: which runs only where the table exists.
HOME_CONTROL_NAMES = ("home_control", "jarvis_home_control_run")


def _home_control(verdict):
    """The same verdict registered under both names home_control can arrive as."""
    return {name: verdict for name in HOME_CONTROL_NAMES}


def _with_real_enabled(fn):
    """Runs `fn` with jarvis_plan.enabled() genuinely mocked True (a
    results file this checkout does not ship), restoring the real one
    afterwards even if `fn` raises."""
    real = PL.enabled
    PL.enabled = lambda *a, **k: (True, "")
    try:
        fn()
    finally:
        PL.enabled = real


# --------------------------------------------------------------------------
#   Switched off by default, and refused BEFORE propose() ever runs
# --------------------------------------------------------------------------

def t_default_off_refuses_before_propose_runs():
    # No tools/tool_eval/tool_eval_results.json ships in this checkout -
    # PL.enabled() genuinely says no, unmocked.
    ok, why = PL.enabled("jarvis-primary")
    check("CONTROL: jarvis_plan.enabled() really says no by default", ok is False, why)
    ran = []
    real_propose = PL.propose
    PL.propose = lambda *a, **k: ran.append(1) or real_propose(*a, **k)
    try:
        result, _ = _plan_turn(
            [{"tool": "calculator", "args": {"expression": "1+1"}, "why": "check"}],
            checker=_fake_checker(_APPROVE_RUN_PLAN))
    finally:
        PL.propose = real_propose
    check("propose() never ran - refused before prepare() reached it", ran == [])
    check("refused plainly, not a silent nothing",
          isinstance(result, dict) and result.get("ok") is False
          and "refused" in (result.get("error") or ""), repr(result))
    check("names the real reason (the safety test has not run)",
          "safety test" in (result.get("error") or ""), repr(result))


def t_enabled_but_tainted_refuses_before_propose_runs():
    """Every one of the four signals _propose_plan_refusal folds into
    jarvis_plan's own `tainted` - proven one at a time, each restored."""
    def one_signal(setup):
        ran = []
        real_propose = PL.propose
        PL.propose = lambda *a, **k: ran.append(1) or real_propose(*a, **k)
        real_watch_init = AG._TurnWatch.__init__

        def patched_init(self, *a, **k):
            real_watch_init(self, *a, **k)
            setup(self)
        AG._TurnWatch.__init__ = patched_init
        try:
            def body():
                return _plan_turn(
                    [{"tool": "calculator", "args": {"expression": "1+1"}, "why": "x"}],
                    checker=_fake_checker(_APPROVE_RUN_PLAN))
            holder = {}
            _with_real_enabled(lambda: holder.update(out=body()))
            result, _ = holder["out"]
        finally:
            PL.propose = real_propose
            AG._TurnWatch.__init__ = real_watch_init
        return ran, result

    for label, setup in (
            ("tainted", lambda w: setattr(w, "tainted", True)),
            ("read something this turn", lambda w: w.read.update({"memory_search": 1})),
            ("provenance not the owner's own words", lambda w: setattr(w, "provenance", "shared")),
            ("app_context", lambda w: setattr(w, "app_context", True))):
        ran, result = one_signal(setup)
        check(f"{label}: propose() never ran", ran == [], label)
        check(f"{label}: refused, in jarvis_plan's own words",
              isinstance(result, dict) and result.get("ok") is False
              and "own words" in (result.get("error") or ""), repr(result))


# --------------------------------------------------------------------------
#   Inside an approved plan: safe steps run once; risky/from_step steps,
#   and any step whose REAL tier needs a person, always ask again
# --------------------------------------------------------------------------

def t_a_safe_step_runs_with_no_card_of_its_own():
    def body():
        checker, calls = _fake_checker({
            **_APPROVE_RUN_PLAN,
            # calculator's real tier is auto - nobody is really asked, but
            # the dispatcher still consults the real gate for it.
            "calculator": _Verdict(True, tier="auto", outcome="auto"),
        })
        result, _ = _plan_turn(
            [{"tool": "calculator", "args": {"expression": "2+2"}, "why": "check the sum"}],
            checker=checker)
        check("the plan ran to completion", result.get("ok") is True, repr(result))
        check("the safe step really executed (calculator's own real result)",
              len(result.get("done") or []) == 1
              and result["done"][0]["result"].get("value") == 4, repr(result))
        check("nothing was left un-run", result.get("not_run") == [], repr(result))
        check("the real gate WAS consulted for the step (never a bypass)",
              any(c[0] == "calculator" for c in calls), repr(calls))
        check("but only once - no double card for a step nobody flagged risky",
              sum(1 for c in calls if c[0] == "calculator") == 1, repr(calls))
    _with_real_enabled(body)


def _risky_or_from_step_case(step_extra, label):
    """One step naming home_control (a NEEDS_A_PERSON tool), marked either
    `risky` or `from_step` - jarvis_plan.run() calls THIS dispatcher's
    gate_check for either kind before run_step, per PlanStep.needs_own_card."""
    def body():
        checker, calls = _fake_checker({
            **_APPROVE_RUN_PLAN,
            # The name the checker is asked with is the RESOLVED ACTION where
            # the product can resolve it ("home_control"), and the tool's own
            # lookup name where it cannot (no jarvis_gate.py: a CI/repo run).
            # Both are registered - see HOME_CONTROL_NAMES.
            **_home_control(_Verdict(True, tier="ask", outcome="approved")),
            "calculator": _Verdict(True, tier="auto", outcome="auto"),
        })
        steps = [{"tool": "calculator", "args": {"expression": "1+1"}, "why": "warm up"}] \
            if step_extra.get("from_step") is not None else []
        steps.append({"tool": "home_control",
                      "args": {"domain": "light", "service": "turn_on",
                               "entity_id": "light.kitchen"},
                      "why": "the owner asked", **step_extra})
        result, _ = _plan_turn(steps, checker=checker)
        check(f"{label}: the plan ran to completion", result.get("ok") is True, repr(result))
        check(f"{label}: its own card really was asked for the home_control step",
              any(c[0] in HOME_CONTROL_NAMES for c in calls), repr(calls))
        check(f"{label}: asked exactly once, whichever of gate_check/run_step asked it",
              sum(1 for c in calls if c[0] in HOME_CONTROL_NAMES) == 1, repr(calls))
    _with_real_enabled(body)


def t_a_risky_step_gets_its_own_card():
    _risky_or_from_step_case({"risky": True}, "risky")


class _FakeTools:
    """Swaps named tools in AG.TOOLS for stand-ins with a plain prepare()
    and a recording execute() (no vault, no memory database), and pins
    AG._tier_of to `tiers` - restored on exit."""

    def __init__(self, results: dict, tiers: dict):
        self.results, self.tiers, self.ran = results, tiers, []

    def __enter__(self):
        self.saved = {n: AG.TOOLS[n] for n in self.results}
        self.real_tier = AG._tier_of
        for n, res in self.results.items():
            old = AG.TOOLS[n]

            def execute(args, state, n=n, res=res, **_):
                self.ran.append((n, dict(args)))
                return dict(res)
            AG.TOOLS[n] = AG.Tool(n, old.description, old.parameters,
                                  lambda args, n=n: (None, f"{n}: {json.dumps(args)}"),
                                  execute)
        AG._tier_of = lambda action: self.tiers.get(action, "ask")
        return self

    def __exit__(self, *exc):
        AG.TOOLS.update(self.saved)
        AG._tier_of = self.real_tier
        return False


def t_a_from_step_step_gets_its_own_card():
    """Bug audit 2026-09-28, F2 + F3: a result-filled step is asked about on
    its own card, for a PERSON's yes, even when its tool is auto-tier - and
    both that card and the step that runs hold the earlier step's real
    result, not the model's guess."""
    def body():
        with _FakeTools({"append_obsidian_daily": {"ok": True, "written": True}},
                        {"append_obsidian_daily": "auto", "calculator": "auto",
                         "run_plan": "ask"}) as fk:
            checker, calls = _fake_checker({
                **_APPROVE_RUN_PLAN,
                "calculator": _Verdict(True, tier="auto", outcome="auto")})
            result, _ = _plan_turn(
                [{"tool": "calculator", "args": {"expression": "2+2"}, "why": "add it up"},
                 {"tool": "append_obsidian_daily", "args": {"text": "The sum: {{step 1}}"},
                  "why": "log it", "from_step": 0}],
                checker=checker)
            step_cards = [c for c in calls if c[0] == AG.PLAN_STEP_ASK_ACTION
                          and "Plan step" in c[1]["text"]]
            check("an auto-tier result-filled step still got its own card (run_plan)",
                  len(step_cards) == 1, repr(calls))
            check("... and that card shows the REAL result, not {{step 1}}",
                  step_cards and "{{step 1}}" not in step_cards[0][1]["text"]
                  and '\\"value\\": 4' in step_cards[0][1]["text"], repr(step_cards))
            check("the step ran with the real result",
                  fk.ran and fk.ran[-1][0] == "append_obsidian_daily"
                  and '"value": 4' in fk.ran[-1][1]["text"]
                  and "{{step" not in fk.ran[-1][1]["text"], repr(fk.ran))
            check("the plan finished", result.get("ok") is True, repr(result))
    _with_real_enabled(body)


def t_a_chain_of_from_step_steps_each_gets_its_own_card_and_runs_once():
    """Bug audit 2026-09-29: jarvis_plan.run() makes a fresh copy of every
    result-filled step and drops it when the next begins, and the
    dispatcher cached each verdict under id(step). CPython reuses a freed
    object's id, so the SECOND filled step in a row landed on the first's
    cache entry: it skipped its own card and re-ran the earlier step's tool.
    Three filled steps in a row must each be asked about and each run once."""
    def body():
        results = {"append_obsidian_daily": {"ok": True, "written": "A"},
                   "append_logseq_journal": {"ok": True, "written": "B"},
                   "calculator": {"ok": True, "value": 4}}
        with _FakeTools(results, {"calculator": "auto", "run_plan": "ask",
                                  **{n: "auto" for n in results}}) as fk:
            checker, calls = _fake_checker({
                **_APPROVE_RUN_PLAN,
                "calculator": _Verdict(True, tier="auto", outcome="auto")})
            result, _ = _plan_turn(
                [{"tool": "calculator", "args": {"expression": "2+2"}, "why": "add"},
                 {"tool": "append_obsidian_daily", "args": {"text": "one {{step 1}}"},
                  "why": "log", "from_step": 0},
                 {"tool": "append_logseq_journal", "args": {"text": "two {{step 2}}"},
                  "why": "log", "from_step": 1},
                 {"tool": "calculator", "args": {"expression": "{{step 3}}"},
                  "why": "log", "from_step": 2}],
                checker=checker)
            step_cards = [c for c in calls if c[0] == AG.PLAN_STEP_ASK_ACTION
                          and "Plan step" in c[1]["text"]]
            check("chain: all three filled steps got their OWN card",
                  len(step_cards) == 3, repr([c[1]["text"][:60] for c in step_cards]))
            names = [n for n, _ in fk.ran]
            check("chain: each step ran exactly once, in order (none repeated, none skipped)",
                  names == ["calculator", "append_obsidian_daily",
                            "append_logseq_journal", "calculator"], repr(names))
            check("chain: the plan finished", result.get("ok") is True, repr(result))
    _with_real_enabled(body)


def t_a_risky_auto_step_needs_a_person():
    """F2: a step marked risky whose tool is auto-tier must really be asked
    (the card promised it). A gate that lets it through without a person -
    run_plan misconfigured to auto - refuses it; nothing runs."""
    def body():
        with _FakeTools({"append_obsidian_daily": {"ok": True}},
                        {"append_obsidian_daily": "auto", "run_plan": "ask"}) as fk:
            checker, calls = _fake_checker({**_APPROVE_RUN_PLAN})
            result, _ = _plan_turn(
                [{"tool": "append_obsidian_daily", "args": {"text": "hello"},
                  "why": "log it", "risky": True}], checker=checker)
            step_cards = [c for c in calls if c[0] == AG.PLAN_STEP_ASK_ACTION
                          and "Plan step" in c[1]["text"]]
            check("risky + auto tool: asked on its own card", len(step_cards) == 1,
                  repr(calls))
            check("... and ran once a person said yes",
                  result.get("ok") is True and fk.ran, repr(result))
        with _FakeTools({"append_obsidian_daily": {"ok": True}},
                        {"append_obsidian_daily": "auto", "run_plan": "ask"}) as fk:
            seen = {"n": 0}

            def checker(action, detail, prompt):
                if action == "run_plan" and "Plan step" not in detail["text"]:
                    return _Verdict(True, tier="ask", outcome="approved")
                seen["n"] += 1
                return _Verdict(True, tier="auto", outcome="auto")
            result, _ = _plan_turn(
                [{"tool": "append_obsidian_daily", "args": {"text": "hello"},
                  "why": "log it", "risky": True}], checker=checker)
            check("a yes nobody gave (tier auto) is refused: nothing ran",
                  result.get("ok") is False and not fk.ran and seen["n"] == 1
                  and "not approved on its own card" in (result.get("reason") or ""),
                  repr(result))
    _with_real_enabled(body)


def t_a_note_write_after_a_reading_step_in_the_plan_waits_for_a_yes():
    """F2 (the 2026-09-24 note rule) + F4: a reading step in the plan makes
    a later note write in the same plan ask, as a direct call would."""
    def body():
        with _FakeTools({"memory_search": {"ok": True, "facts": ["The roofer is Sam"]},
                         "append_obsidian_daily": {"ok": True}},
                        {"memory_search": "auto", "append_obsidian_daily": "auto",
                         AG.NOTE_AFTER_OUTSIDE_ACTION: "ask", "run_plan": "ask"}) as fk:
            checker, calls = _fake_checker({
                **_APPROVE_RUN_PLAN,
                "memory_search": _Verdict(True, tier="auto", outcome="auto"),
                AG.NOTE_AFTER_OUTSIDE_ACTION: _Verdict(True, tier="ask", outcome="approved")})
            result, _ = _plan_turn(
                [{"tool": "memory_search", "args": {"query": "roofer"}, "why": "look it up"},
                 {"tool": "append_obsidian_daily", "args": {"text": "call the roofer"},
                  "why": "log it"}], checker=checker)
            check("the note write was put to the 'after outside text' card",
                  any(c[0] == AG.NOTE_AFTER_OUTSIDE_ACTION for c in calls), repr(calls))
            check("both steps ran once approved", result.get("ok") is True
                  and [r[0] for r in fk.ran] == ["memory_search", "append_obsidian_daily"],
                  repr((result, fk.ran)))
        with _FakeTools({"append_obsidian_daily": {"ok": True}},
                        {"append_obsidian_daily": "auto", "calculator": "auto"}) as fk:
            checker, calls = _fake_checker({
                **_APPROVE_RUN_PLAN,
                "calculator": _Verdict(True, tier="auto", outcome="auto"),
                "append_obsidian_daily": _Verdict(True, tier="auto", outcome="auto")})
            result, _ = _plan_turn(
                [{"tool": "calculator", "args": {"expression": "1+1"}, "why": "sum"},
                 {"tool": "append_obsidian_daily", "args": {"text": "hi"}, "why": "log"}],
                checker=checker)
            check("CONTROL: after a step that reads nothing, a note saves straight away",
                  result.get("ok") is True
                  and not any(c[0] == AG.NOTE_AFTER_OUTSIDE_ACTION for c in calls),
                  repr(calls))
    _with_real_enabled(body)


def t_a_risky_step_denied_stops_the_run_there():
    def body():
        checker, calls = _fake_checker({
            **_APPROVE_RUN_PLAN,
            **_home_control(_Verdict(False, tier="ask", outcome="denied")),
        })
        result, _ = _plan_turn(
            [{"tool": "home_control",
              "args": {"domain": "light", "service": "turn_on", "entity_id": "light.kitchen"},
              "why": "the owner asked", "risky": True}],
            checker=checker)
        check("the run reports failure", result.get("ok") is False, repr(result))
        check("nothing was done", result.get("done") == [], repr(result))
        check("the denied step is the one left not run",
              len(result.get("not_run") or []) == 1
              and result["not_run"][0]["tool"] == "home_control", repr(result))
    _with_real_enabled(body)


def t_a_step_the_model_did_not_flag_but_whose_real_tier_needs_a_person_is_refused():
    """THE gap this dispatcher exists to close: jarvis_plan.run() would call
    run_step directly for a step nobody flagged risky - trusting the
    model's OWN "risky" self-report alone would let this run unasked. The
    real gate answers auto here (as if the owner had set the tier that
    loose, or the model simply guessed wrong): the dispatcher's own
    NEEDS_A_PERSON check must still refuse it."""
    def body():
        checker, calls = _fake_checker({
            **_APPROVE_RUN_PLAN,
            # home_control's real tier is auto here (as if the owner had set it
            # that loose); registered under both names - see HOME_CONTROL_NAMES.
            **_home_control(_Verdict(True, tier="auto", outcome="auto")),
        })
        result, _ = _plan_turn(
            [{"tool": "home_control",
              "args": {"domain": "light", "service": "turn_on", "entity_id": "light.kitchen"},
              "why": "the owner asked"}],   # NOT marked risky, no from_step
            checker=checker)
        check("the step's own real gate WAS consulted (never a bypass)",
              any(c[0] in HOME_CONTROL_NAMES for c in calls), repr(calls))
        check("but it is refused anyway - nobody was really asked",
              result.get("ok") is False, repr(result))
        check("the reason says which tool, and that it was let through unasked",
              "home_control" in (result.get("reason") or "")
              and "without asking anyone" in (result.get("reason") or ""), repr(result))
        check("nothing ran", result.get("done") == [], repr(result))
    _with_real_enabled(body)


def t_a_denial_stops_later_safe_steps_too():
    """Condition 4, proven with three steps: the first safe step runs, the
    second (risky) is denied, and the THIRD - itself perfectly safe - must
    never run either. Not skipping the bad step and continuing: stopping."""
    def body():
        checker, calls = _fake_checker({
            **_APPROVE_RUN_PLAN,
            "calculator": _Verdict(True, tier="auto", outcome="auto"),
            **_home_control(_Verdict(False, tier="ask", outcome="denied")),
        })
        result, _ = _plan_turn(
            [{"tool": "calculator", "args": {"expression": "1+1"}, "why": "first"},
             {"tool": "home_control",
              "args": {"domain": "light", "service": "turn_on", "entity_id": "light.kitchen"},
              "why": "second", "risky": True},
             {"tool": "calculator", "args": {"expression": "3+3"}, "why": "third"}],
            checker=checker)
        check("the run reports failure", result.get("ok") is False, repr(result))
        check("exactly the first step is done", [d["tool"] for d in result.get("done") or []]
              == ["calculator"], repr(result))
        check("the second and third steps are both left not run",
              [d["tool"] for d in result.get("not_run") or []]
              == ["home_control", "calculator"], repr(result))
        check("calculator's own card was asked only once - the third step never reached it",
              sum(1 for c in calls if c[0] == "calculator") == 1, repr(calls))
    _with_real_enabled(body)


# --------------------------------------------------------------------------
#   Excluded tools, and a real prepare() actually running
# --------------------------------------------------------------------------

def t_excluded_tools_are_refused_as_plan_steps():
    for tname, args in (("send_email", {"to": ["a@example.com"], "subject": "x", "body": "y"}),
                        ("draft_email", {"body": "y"}),
                        ("set_timer", {"minutes": 5}),
                        ("propose_plan", {"goal": "nested", "steps": []})):
        def body(tname=tname, args=args):
            checker, calls = _fake_checker(_APPROVE_RUN_PLAN)
            result, _ = _plan_turn(
                [{"tool": tname, "args": args, "why": "try to sneak one in"}], checker=checker)
            check(f"{tname}: refused as a plan step", result.get("ok") is False, repr(result))
            check(f"{tname}: never even reached its own gate",
                  not any(c for c in calls if c[0] != "run_plan"), repr(calls))
            check(f"{tname}: says plainly it cannot be a step",
                  "cannot be run as a plan step" in (result.get("not_run") or [{}])[0]
                  .get("tool", "") or "cannot be run as a plan step" in json.dumps(result),
                  repr(result))
        _with_real_enabled(body)


def t_running_a_step_goes_through_that_tools_own_real_prepare():
    """No entity named at all - home_control's REAL prepare() (jarvis_agent.
    _prepare_home_control) raises ValueError for exactly this, unrelated to
    anything jarvis_plan or this dispatcher invents. Proves prepare() truly
    ran, rather than being skipped for a step. Not marked `risky`, so this
    goes through run_step directly (jarvis_plan.run() never calls a
    separate gate_check for it) - the path where the safety GAP tests
    above matter most, since nothing else double-checks this step first."""
    def body():
        checker, calls = _fake_checker({
            **_APPROVE_RUN_PLAN,
            # Both names, as above - and the point of this case is that it is
            # never asked at all, because prepare() rejects the arguments first.
            **_home_control(_Verdict(True, tier="ask", outcome="approved")),
        })
        result, _ = _plan_turn(
            [{"tool": "home_control", "args": {"domain": "light", "service": "turn_on"},
              "why": "no device named"}],
            checker=checker)
        check("refused - the real prepare() rejected these arguments",
              result.get("ok") is False, repr(result))
        check("the real prepare()'s own message reaches the reason",
              "could not accept its arguments" in (result.get("reason") or ""), repr(result))
        check("never even reached the gate - a bad call is not what a person approves",
              not any(c[0] in HOME_CONTROL_NAMES for c in calls), repr(calls))
    _with_real_enabled(body)


def t_the_checker_is_asked_with_the_resolved_action_name():
    """2026-10-03's fix, and the reason HOME_CONTROL_NAMES has two entries.

    The plan dispatcher asks the checker with the RESOLVED action name, looked
    up through `jarvis_gate.action_for_tool()`, not the tool's own lookup name -
    which is what makes a real tier findable at all. Without jarvis_gate.py (a
    CI or repository run) there is no table, the lookup name arrives instead,
    and the checks above still run because both names are registered. This is
    the one that would go red if the resolution quietly stopped happening on
    the owner's PC, so it is proved there and SKIPPED, with its reason, where
    it cannot be.
    """
    from _where import missing as _missing
    if _missing("jarvis_gate.py"):
        return skip("the checker is asked with the resolved action name: no jarvis_gate.py "
                    "here, so no table can turn 'jarvis_home_control_run' into an action "
                    "name; the owner's own run proves this")
    try:
        import jarvis_gate
        want, _known = jarvis_gate.action_for_tool("jarvis_home_control_run", {})
    except Exception as exc:
        return skip("the checker is asked with the resolved action name: "
                    f"jarvis_gate.action_for_tool could not be asked "
                    f"({type(exc).__name__}: {exc})")

    def body():
        checker, calls = _fake_checker({
            **_APPROVE_RUN_PLAN,
            **_home_control(_Verdict(True, tier="ask", outcome="approved")),
        })
        _plan_turn([{"tool": "home_control",
                     "args": {"domain": "light", "service": "turn_on",
                              "entity_id": "light.kitchen"},
                     "why": "the owner asked", "risky": True}], checker=checker)
        asked = [c[0] for c in calls]
        check("the checker is asked with the RESOLVED action name, never the "
              "tool's own",
              [a for a in asked if a in HOME_CONTROL_NAMES] == [want]
              and "jarvis_home_control_run" not in asked, (want, asked))
    _with_real_enabled(body)


if __name__ == "__main__":
    for fn in (t_default_off_refuses_before_propose_runs,
               t_enabled_but_tainted_refuses_before_propose_runs,
               t_a_safe_step_runs_with_no_card_of_its_own,
               t_a_risky_step_gets_its_own_card,
               t_a_from_step_step_gets_its_own_card,
               t_a_chain_of_from_step_steps_each_gets_its_own_card_and_runs_once,
               t_a_risky_auto_step_needs_a_person,
               t_a_note_write_after_a_reading_step_in_the_plan_waits_for_a_yes,
               t_a_risky_step_denied_stops_the_run_there,
               t_a_step_the_model_did_not_flag_but_whose_real_tier_needs_a_person_is_refused,
               t_a_denial_stops_later_safe_steps_too,
               t_excluded_tools_are_refused_as_plan_steps,
               t_running_a_step_goes_through_that_tools_own_real_prepare,
               t_the_checker_is_asked_with_the_resolved_action_name):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
