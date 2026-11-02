"""test_phone_app_launch.py: "open YouTube Music and play The Weeknd", from Live.

The owner asked (2026-11-01, their words): "id like jarvis live to be able to
open certain apps on my android phone if i ask it ... and to be able to perform
certain actions like if i aaid 'hey jarvis open yourube music and play the
weekend'". The module half - the literal adb command, the allow-list, the URL
encoding - is proved in test_android_control.py. THIS suite proves the half the
model actually touches:

  * the tool schema the model is SENT really names open_app, play and
    list_apps, and the fields those need;
  * a call that only lists the owner's apps, or that names an app the owner
    did not allow, is answered with NO approval card at all - the model is told
    and the gate is never called;
  * a real plan still goes to the SAME gate action ("jarvis_android_control_run")
    at the SAME tier (control_phone = "ask"), and the card it raises prints
    every literal adb command;
  * the tool stays opt-in: `control_phone` is not in the shipped
    `[tools].enabled`, so nothing here is offered until the owner adds it.

    python -B backend/test_phone_app_launch.py
"""
import json
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.append(str(HERE / "rebuilt"))
import jarvis_agent as AG  # noqa: E402
import jarvis_android_control as A  # noqa: E402

FAILED, PASSED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: printed as `skip`, counted on its own,
    never as a pass."""
    SKIPPED.append(why)
    print(f"skip  {why}")


class Result:
    def __init__(self, returncode=0, stdout=b"", stderr=b""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


class NoRealProcess:
    """Fail loudly if the real adb ever runs. Every check below plans against a
    named serial or an injected fake, so a real process means the test is
    driving the owner's phone."""

    def __enter__(self):
        self.real = A._real_adb

        def boom(argv, timeout=15.0):
            raise AssertionError(f"a real process was started: {argv}")
        A._real_adb = boom
        return self

    def __exit__(self, *a):
        A._real_adb = self.real
        return False


class Verdict:
    """What a jarvis_gate verdict looks like to _one_call, for one outcome."""

    def __init__(self, allowed=True, tier="ask", action="jarvis_android_control_run",
                 outcome="approved", reason=""):
        self.allowed, self.tier, self.action = allowed, tier, action
        self.outcome, self.reason = outcome, reason
        self.request_id = "req-1"


class OneCall:
    """One real `_one_call`, with the gate and the tool's own run() replaced by
    recorders. Nothing reaches a phone, and every gate call is counted - which
    is how "no card" is proved rather than asserted from the source."""

    def __init__(self, args, verdict=None):
        self.args = args
        self.verdict = verdict or Verdict()
        self.gate_calls = []
        self.executed = []
        self.convo, self.steps, self.said = [], [], []
        self._out = AG._Out(lambda data: None, False)

    def run(self):
        tool = AG.TOOLS["control_phone"]
        real_execute = tool.execute

        def execute(args, state, **kw):
            self.executed.append(state)
            return {"ok": True, "done": [], "not_run": []}

        def gate(action, detail, prompt):
            self.gate_calls.append({"action": action, "detail": detail,
                                    "prompt": prompt})
            return self.verdict

        call = {"id": "call-1",
                "function": {"name": "control_phone",
                             "arguments": json.dumps(self.args)}}
        tool.execute = execute
        try:
            AG._one_call(call, ["control_phone"], self.convo, self.steps, gate,
                         lambda text: None, self._out,
                         lambda event, name, **kw: self.said.append((event, name)),
                         watch=AG._TurnWatch())
        finally:
            tool.execute = real_execute
        return self

    @property
    def told(self):
        """What the model was handed back: the tool result, as JSON."""
        if not self.convo:
            return {}
        try:
            return json.loads(self.convo[-1]["content"])
        except Exception:
            return {"_raw": self.convo[-1]["content"]}


ALLOW = {"YouTube Music": "com.google.android.apps.youtube.music"}


def with_allow_list(table):
    """A context manager that makes the module read `table` as [phone_apps].

    Both entry points are patched, because both are real: `phone_apps()` is what
    open_app and play are checked against, and `read_phone_apps()` is what
    list_apps reports. A test that patched only one would prove half the rule.
    """
    class Allow:
        def __enter__(self):
            self.real_apps, self.real_read = A.phone_apps, A.read_phone_apps
            A.phone_apps = lambda: dict(table)
            A.read_phone_apps = lambda: (dict(table), [])
            return self

        def __exit__(self, *a):
            A.phone_apps, A.read_phone_apps = self.real_apps, self.real_read
            return False
    return Allow()


def t_the_tool_the_model_is_sent_names_the_three_new_actions():
    schema = AG.TOOLS["control_phone"].schema()
    fn = schema["function"]
    actions = fn["parameters"]["properties"]["requests"]["items"]["properties"]["action"]
    for action in ("open_app", "play", "list_apps"):
        check(f"the schema offers {action!r}", action in actions["enum"], actions["enum"])
    for old in ("tap", "swipe", "key", "text", "screenshot"):
        check(f"... and still offers {old!r}", old in actions["enum"], actions["enum"])
    props = fn["parameters"]["properties"]["requests"]["items"]["properties"]
    check("the schema names the field an app is asked for by", "app" in props,
          sorted(props))
    check("... and the field the words go in", "query" in props, sorted(props))
    check("... and a package is still accepted, for an app already on the list",
          "package" in props, sorted(props))
    description = fn["description"]
    for word in ("list_apps", "open_app", "play", "refused"):
        check(f"the description says {word!r}", word in description, description)
    check("the description does not promise that music starts by itself",
          "one tap" in description, description)
    check("device is optional, because the one connected phone is found for you",
          fn["parameters"]["required"] == ["goal", "requests"],
          fn["parameters"]["required"])
    device_help = fn["parameters"]["properties"]["device"].get("description", "")
    check("... and the field itself says leaving it out is fine",
          "leave it out" in device_help, device_help)


def t_a_call_the_schema_does_not_allow_is_refused_before_anything():
    ok, problem = AG.check_call(
        "control_phone",
        json.dumps({"device": "EMULATOR123", "goal": "open it",
                    "requests": [{"action": "open_app", "app": "YouTube Music"}]}),
        ["control_phone"])
    check("a well-formed open_app call is accepted", problem is None, repr(problem))
    check("... with the app name intact", (ok or {}).get("requests", [{}])[0].get("app")
          == "YouTube Music", ok)
    bad, problem = AG.check_call(
        "control_phone",
        json.dumps({"device": "E", "goal": "x",
                    "requests": [{"action": "launch_everything"}]}),
        ["control_phone"])
    check("an action that is not in the enum is refused, not sent on",
          bad is None and problem is not None, repr((bad, problem)))
    check("... and the refusal names the actions that ARE allowed",
          problem is not None and "open_app" in problem, problem)


def t_listing_the_apps_is_answered_with_no_card_at_all():
    with NoRealProcess(), with_allow_list(ALLOW):
        turn = OneCall({"device": "", "goal": "which apps can you open on my phone?",
                        "requests": [{"action": "list_apps"}]}).run()
    check("the gate was never called: no card to approve a list",
          turn.gate_calls == [], repr(turn.gate_calls))
    told = turn.told
    check("the model was given the list", told.get("apps") ==
          [{"name": "YouTube Music", "can_play": True}], told)
    check("... and not a single package name", "com.google" not in json.dumps(told), told)
    check("the step is recorded as needing no card",
          turn.steps and turn.steps[0].get("outcome") == "no card needed", turn.steps)
    check("... and nothing was run on a phone", turn.executed == [], repr(turn.executed))


def t_an_app_the_owner_did_not_allow_raises_no_card_either():
    with NoRealProcess(), with_allow_list(ALLOW):
        turn = OneCall({"device": "EMULATOR123", "goal": "open TikTok",
                        "requests": [{"action": "open_app", "app": "TikTok"}]}).run()
    check("the gate was never called", turn.gate_calls == [], repr(turn.gate_calls))
    told = turn.told
    check("the model is told plainly, so it can say it to the owner",
          told.get("ok") is False
          and "not in your phone's app list" in str(told.get("error")), told)
    check("... and that nothing was sent and nobody was asked",
          "Nothing was sent and nobody was asked" in str(told.get("error")), told)
    check("... and the step reads as refused",
          turn.steps and turn.steps[0].get("outcome") == "refused", turn.steps)


def t_an_empty_allow_list_says_so_instead_of_raising_a_card():
    with NoRealProcess(), with_allow_list({}):
        turn = OneCall({"device": "EMULATOR123", "goal": "open YouTube Music",
                        "requests": [{"action": "open_app",
                                      "app": "YouTube Music"}]}).run()
    check("no card for an empty list", turn.gate_calls == [], repr(turn.gate_calls))
    check("... and the owner's own sentence is what the model reads",
          A.NO_APPS_LINE in str(turn.told.get("error")), turn.told)
    check("... naming the table to fill in",
          "[phone_apps]" in str(turn.told.get("error")), turn.told)


def t_a_real_plan_goes_to_the_same_gate_action_and_prints_every_command():
    with NoRealProcess(), with_allow_list(ALLOW):
        turn = OneCall({"device": "EMULATOR123", "goal": "open YouTube Music and play The Weeknd",
                        "requests": [{"action": "play", "app": "YouTube Music",
                                      "query": "The Weeknd"}]}).run()
    check("exactly one card is raised", len(turn.gate_calls) == 1, repr(turn.gate_calls))
    got = turn.gate_calls[0] if turn.gate_calls else {}
    check("... under the SAME gate action as before this slice",
          got.get("action") == "jarvis_android_control_run", got.get("action"))
    card = str((got.get("detail") or {}).get("text") or "")
    check("... and the card prints the literal adb command",
          "adb -s EMULATOR123 shell am start -a android.intent.action.VIEW" in card,
          card)
    check("... with the words already URL-encoded on it",
          "The%20Weeknd" in card and "?q=The Weeknd" not in card, card)
    check("... and it says plainly what the app is being asked to do",
          "open YouTube Music and search for those words" in card, card)
    check("... and that the plan was really handed to run()",
          len(turn.executed) == 1, repr(turn.executed))


def t_a_refused_card_still_runs_nothing():
    denied = Verdict(allowed=False, outcome="denied", reason="not now")
    with NoRealProcess(), with_allow_list(ALLOW):
        turn = OneCall({"device": "EMULATOR123", "goal": "open it",
                        "requests": [{"action": "open_app",
                                      "app": "YouTube Music"}]}, verdict=denied).run()
    check("a denied card runs nothing", turn.executed == [], repr(turn.executed))
    check("... and the model is told", turn.told.get("ok") is False, turn.told)


def t_the_gate_action_the_tier_and_the_opt_in_are_unchanged():
    """The wiring is checked where it lives: this repository's agent, the
    published gate base (what the owner's PC applies patches to), and the two
    settings templates."""
    tool = AG.TOOLS["control_phone"]
    check("the tool still resolves to jarvis_android_control_run",
          tool.gate_lookup_name({}) == "jarvis_android_control_run")
    check("... and it is still one of the tools that must ask a person",
          "control_phone" in AG.NEEDS_A_PERSON, sorted(AG.NEEDS_A_PERSON))
    gate_src = (REPO / "jarvis-backend" / "jarvis_gate.py").read_text(encoding="utf-8")
    check("the gate base still maps that name to the control_phone action",
          '"jarvis_android_control_run": "control_phone"' in gate_src)
    check("... and still calls it outbound and not reversible",
          '"control_phone":' in gate_src and '"outbound"' in gate_src)
    for label, path in (("shipped template", HERE / "rebuilt" / "jarvis-framework.toml"),
                        ("published base", REPO / "jarvis-backend" / "jarvis-framework.toml")):
        text = path.read_text(encoding="utf-8")
        check(f"{label}: control_phone is still tier ask",
              'control_phone             = "ask"' in text)
        check(f"{label}: control_phone is NOT in [tools].enabled (opt-in only)",
              "control_phone" not in text.split("[tools]", 1)[1].split("[", 1)[0],
              text.split("[tools]", 1)[1].split("[", 1)[0])
        check(f"{label}: it has a [phone_apps] table", "[phone_apps]" in text)
        check(f"{label}: that table ships with no app in it",
              _only_comments(_table_block(text, "[phone_apps]")))


def _table_block(text: str, header: str) -> list:
    """One TOML table's own lines (header excluded), up to the next section."""
    out, inside = [], False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == header:
            inside = True
            continue
        if inside and stripped.startswith("[") and stripped.endswith("]"):
            break
        if inside:
            out.append(line)
    return out


def _only_comments(block) -> bool:
    """True when a TOML table's own block holds no setting lines, only comments
    and blank lines - i.e. it ships empty."""
    for line in block:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return False
    return True


def t_the_shipped_module_and_the_agent_agree_on_the_actions():
    """One list of action names, in the schema the model sees and in the module
    that turns them into argv: a name the schema offers and the module does not
    know would be a refusal at the worst moment."""
    props = AG.TOOLS["control_phone"].schema()["function"]["parameters"][
        "properties"]["requests"]["items"]["properties"]
    offered = set(props["action"]["enum"])
    known = {"tap", "swipe", "key", "text", "screenshot", "long_press",
             "open_app", "play", "ui_dump", A.LIST_APPS}
    check("the schema offers nothing the module cannot answer",
          offered <= known, repr(sorted(offered - known)))
    with NoRealProcess(), with_allow_list(ALLOW):
        for action, extra in (("open_app", {"app": "YouTube Music"}),
                              ("play", {"app": "YouTube Music", "query": "x"}),
                              ("tap", {"x": 1, "y": 2}),
                              ("long_press", {"x": 1, "y": 2}),
                              ("ui_dump", {}), ("screenshot", {})):
            p = A.plan("EMULATOR123", "x", [{"action": action, **extra}])
            check(f"{action!r} builds a step here, so the enum is not a promise "
                  f"the module breaks", len(p.steps) == 1, repr(p.rejected))
    check("list_apps is the one action that is answered without a command",
          A.plan("E", "x", [{"action": "list_apps"}], apps=ALLOW).steps == [])


if __name__ == "__main__":
    for fn in (t_the_tool_the_model_is_sent_names_the_three_new_actions,
               t_a_call_the_schema_does_not_allow_is_refused_before_anything,
               t_listing_the_apps_is_answered_with_no_card_at_all,
               t_an_app_the_owner_did_not_allow_raises_no_card_either,
               t_an_empty_allow_list_says_so_instead_of_raising_a_card,
               t_a_real_plan_goes_to_the_same_gate_action_and_prints_every_command,
               t_a_refused_card_still_runs_nothing,
               t_the_gate_action_the_tier_and_the_opt_in_are_unchanged,
               t_the_shipped_module_and_the_agent_agree_on_the_actions):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if SKIPPED:
        print(f"{len(SKIPPED)} skipped (never counted as a pass): " + "; ".join(SKIPPED))
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
