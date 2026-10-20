"""test_settings_tool.py - the model-facing settings tool (2026-10-13).

    python3 backend/test_settings_tool.py

WHY THIS SUITE EXISTS. "Jarvis can change all settings if I ask" was false. A
settings request reached a setting only when the sentence fitted the fixed
phrase grammar in jarvis_quick.py, checked BEFORE the model ran, and
jarvis_agent.TOOLS had no settings tool at all - so a sentence that missed the
grammar was answered by the model, which could not change anything and was
never told so. The failure looked like success
(`.dsh-scratch/settings-reachability-audit.md`).

`change_setting` is the other half: a tool the model can call, so ANY wording
works. Its safety rests on ONE claim, and this suite tests that claim rather
than the code around it:

    the tool decides no tier, raises no card and applies no change of its own.
    It calls the SAME per-setting function a spoken sentence calls -
    `BoolSetting.set` in jarvis_settings_registry.py - and that function is
    what applies a cosmetic change at once and raises the setting's OWN card
    (its own risk text, its own Windows Hello rule, its own PC rule) for
    anything that loosens a rule, reads or reaches more, or touches privacy or
    how Jarvis works.

That makes it a second ENTRANCE to the one guarded door, never a second door.
If the tests below pass and that sentence is true, the gate is not weakened.

WHAT IT CHECKS, IN PLAIN WORDS
  1. both entrances reach the SAME setter for the same setting - proven with a
     recording setter, so neither path can quietly grow its own copy;
  2. a change still waiting on its card is NOT reported as done, and `changed`
     is False - which is the failure that would make the tool look as though it
     had worked;
  3. a name it cannot resolve changes NOTHING and raises NO card; it answers in
     words. It never guesses, because changing a switch the owner did not name
     is worse than changing nothing;
  4. a turn shaped by outside text changes nothing at all, so a page or an
     email cannot talk the model into a setting change - STRICTER than the
     spoken path, never looser;
  5. it has no second path (the generic plan/execute route refuses) and its
     gate lookup name is an action jarvis_gate already knows, so no new gate
     action, no new tier and no new card wording is invented;
  6. every module function a setting's setter calls actually exists. The humour
     switch named `jarvis_manner.handle_post`, which has never existed - so
     "turn on humour", added by #360, raised AttributeError and could not work.
  7. THE HALF THE 2026-10-13 FIELD TEST TURNED ON: the tool is still OFFERED by
     the shipped settings file, the description that made the model actually
     call it is still an instruction rather than a note about the tool, and the
     tier rule behind it has not moved - the privacy actions still ask first,
     and the cosmetic setters still reach no gate at all.

No network, no model, no Windows, and nothing under the owner's real config
directory is read or written: every setter this suite reaches is a recording
stand-in. The two checks that must read a real file read the repository's own
copies (jarvis-backend/jarvis_gate.py, backend/rebuilt/jarvis-framework.toml).
"""
from __future__ import annotations

import ast
import importlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent

#: THIS SUITE MUST NOT LITTER THE TREE IT TESTS (measured 2026-10-13). One of
#: its own checks imports `jarvis_gate` from this repository's `jarvis-backend/`
#: copy (t_its_gate_action_already_exists, which appends that folder to
#: sys.path). Run WITHOUT `-B` - which is how tools/check_claims.py runs every
#: `test:` row, as a plain child process - that import wrote
#: `jarvis-backend/__pycache__/jarvis_gate.cpython-312.pyc`, and
#: `backend/test_base_matches_repo.py` fails on exactly that file ("no private,
#: generated or superseded file is in the base"). The damage is not visible in
#: the run that causes it: the pycache is written during ONE run and the base
#: check fails in the NEXT one, so `backend/test_claims.py` - which runs the
#: whole register, then runs it again to read its green line - went red the
#: moment a `test:` row named this suite (row F01 of docs/CLAIMS.tsv). A run
#: with `python -B`, which is how the briefs say to run a suite by hand, hides
#: it entirely. So bytecode writing is off for this whole process.
sys.dont_write_bytecode = True

#: Before ANY import of the backend: a temp config dir, so that nothing this
#: suite touches can reach the owner's own settings.
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-settings-tool-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
(_TMP / "config").mkdir(parents=True, exist_ok=True)
os.environ["JARVIS_FRAMEWORK_TOML"] = str(_TMP / "jarvis-framework.toml")

sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

require_shipped("jarvis_agent.py", "jarvis_settings_registry.py", "jarvis_quick.py",
                "jarvis_reach.py")
if str(HERE / "rebuilt") not in sys.path:
    sys.path.append(str(HERE / "rebuilt"))

import jarvis_agent as AG  # noqa: E402
import jarvis_quick as Q  # noqa: E402
import jarvis_settings_registry as R  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skipped(name, why):
    """Printed, never counted. A check that could not run is not a pass
    (CLAUDE.md: BLOCKED is never counted as a pass)."""
    print(f"SKIP  {name}\n        {why}")


# --------------------------------------------------------------------------
#   Driving the tool with a recording setter
# --------------------------------------------------------------------------

class _Recording:
    """A stand-in BoolSetting that records what it was asked to do and returns
    a chosen Outcome. It is installed in R.BOOL_SETTINGS, which is the table
    BOTH entrances resolve through - so this proves the two paths share one
    setter rather than asserting it in a comment."""

    def __init__(self, on_result):
        self.calls = []
        self._on_result = on_result

    def setting(self, key="a test setting", names=("a test setting",)):
        rec = self

        def set_(on, *, peer=None, local=None):
            rec.calls.append(bool(on))
            return rec._on_result

        return R.BoolSetting(key, tuple(names), None, set_)

    def result(self, ok=True, said="Done.", waiting=False):
        return R.Outcome(ok, said, waiting=waiting)


def _watch(**kw):
    """A _TurnWatch that is explicitly NOT conversation-tainted, so a test can
    choose exactly one shaped-turn signal and know that is the one under test.
    (`tainted=False` is passed rather than left out: left out, the
    conversation's real taint would be looked up from the chat log.)"""
    w = AG._TurnWatch(None, None, tainted=kw.pop("tainted", False))
    for name, value in kw.items():
        setattr(w, name, value)
    return w


def run_tool(setting, value, watch=None, table=None):
    """One change_setting call through the REAL _settings_call. Returns
    (result dict, steps, events, watch)."""
    convo, steps, events = [], [], []
    w = watch if watch is not None else _watch()

    def say_step(*a, **k):
        events.append((a, k))

    call = {"id": "call-1", "function": {"name": AG.SETTINGS_TOOL,
                                         "arguments": {"setting": setting, "value": value}}}
    real = R.BOOL_SETTINGS
    if table is not None:
        R.BOOL_SETTINGS = table
    try:
        AG._settings_call({"setting": setting, "value": value}, call, convo, steps,
                          say_step, watch=w)
    finally:
        R.BOOL_SETTINGS = real
    assert convo, "the tool answered nothing"
    return json.loads(convo[-1]["content"]), steps, events, w


# --------------------------------------------------------------------------
#   1. the tool is there, and offered only when the owner enables it
# --------------------------------------------------------------------------

def t_the_tool_exists_and_is_offered_only_when_enabled():
    check("change_setting is a tool", AG.SETTINGS_TOOL in AG.TOOLS)
    check("it is offered when [tools].enabled names it",
          AG.offered_tools({AG.SETTINGS_TOOL}) == [AG.SETTINGS_TOOL],
          repr(AG.offered_tools({AG.SETTINGS_TOOL})))
    check("it is NOT offered when nothing names it",
          AG.SETTINGS_TOOL not in AG.offered_tools({"calculator"}))
    fn = AG.TOOLS[AG.SETTINGS_TOOL].schema()["function"]
    check("it takes a setting and an on/off value",
          fn["parameters"].get("required") == ["setting", "value"],
          repr(fn["parameters"].get("required")))
    check("the value can only be on or off",
          fn["parameters"]["properties"]["value"].get("enum") == ["on", "off"],
          repr(fn["parameters"]["properties"]["value"]))
    check("it has exactly one home (the core, or exactly one group)",
          (1 if AG.SETTINGS_TOOL in AG.CORE_TOOLS else 0)
          + sum(1 for _g, _w, m in AG.TOOL_GROUPS if AG.SETTINGS_TOOL in m) == 1)
    check("its description fits the per-tool budget of 300 tokens",
          AG.estimate_tokens(AG.TOOLS[AG.SETTINGS_TOOL].schema()) <= 300,
          str(AG.estimate_tokens(AG.TOOLS[AG.SETTINGS_TOOL].schema())))


# --------------------------------------------------------------------------
#   2. BOTH ENTRANCES REACH THE SAME SETTER - the claim the safety rests on
# --------------------------------------------------------------------------

def t_asking_and_speaking_run_the_same_function():
    """The claim the whole safety argument rests on: both entrances reach the
    SAME setter. Proven with a recording setter installed in `R.BOOL_SETTINGS` -
    the table BOTH resolve through - so neither path can quietly grow its own
    copy of one.

    WHAT THIS DOES NOT PROVE, said plainly because a second reader asked: it
    shows the tool calls the TABLE's setter function, not that the two entrances
    choose the same setting from the same words. They resolve differently on
    purpose - the spoken grammar matches an exact alias, while
    `find_bool_setting_words` is the tolerant matcher the model needs, and the
    tool is handed a setting name by the model rather than a sentence. The
    resolver is covered by `t_the_two_entrances_resolve_through_the_one_table`
    and `t_a_phrase_that_names_no_setting_is_refused`."""
    rec = _Recording(R.Outcome(True, "Done."))
    fake = rec.setting(key="quiet hours", names=("quiet hours",))
    # The table is patched across BOTH calls on purpose: run_tool() restores it
    # afterwards, so patching only around the tool would leave the spoken call
    # reading the real table and the comparison would prove nothing.
    real = R.BOOL_SETTINGS
    R.BOOL_SETTINGS = (fake,)
    try:
        got, steps, _events, _w = run_tool("quiet hours", "on")
        check("the tool changed the setting through the table's own setter",
              rec.calls == [True], repr(rec.calls))
        # The SPOKEN path - jarvis_quick._run_settings_bool, the one function
        # the phrase grammar calls - against that same table.
        spoken = Q._run_settings_bool({"key": "quiet hours", "on": False}, None, None)
    finally:
        R.BOOL_SETTINGS = real
    check("the spoken path runs that SAME setter",
          rec.calls == [True, False], repr(rec.calls))
    check("and it is the sentence the spoken path would say",
          getattr(spoken, "reply", None) == "Done.", repr(spoken))
    check("the tool reports it changed", got.get("changed") is True, repr(got))


def t_the_two_entrances_resolve_through_the_one_table():
    """The tool must not carry its own list of settings: what it can reach is
    exactly what the table holds, and each entry's setter is the table's own."""
    b = R.find_bool_setting_words("quiet hours")
    check("the resolver returns a member of BOOL_SETTINGS", b in R.BOOL_SETTINGS)
    check("and its setter is the one the table declares",
          b is not None and b.set is R.set_pc_quiet_hours,
          repr(getattr(b, "key", None)))
    # A name in NO table resolves to nothing, so the tool has nothing to call.
    for bad in ("the turbo setting", "app lock", "notifications", "sounds", ""):
        check(f"{bad!r} names no single switch",
              R.find_bool_setting_words(bad) is None)


# --------------------------------------------------------------------------
#   3. what the tool must NEVER do: claim a change it did not make
# --------------------------------------------------------------------------

def t_a_change_waiting_on_its_card_is_not_reported_as_done():
    rec = _Recording(R.Outcome(True, "Waiting for your approval. It turns on only if "
                                     "you approve the card, on your PC or phone.",
                               waiting=True))
    table = (rec.setting(key="background learning", names=("background learning",)),)
    got, steps, events, w = run_tool("background learning", "on", table=table)
    check("the setter was called exactly once", rec.calls == [True], repr(rec.calls))
    check("the answer says it is waiting", got.get("waiting") is True, repr(got))
    check("and it does NOT claim the setting changed",
          got.get("changed") is False, repr(got))
    check("the setter's own sentence is passed on unchanged",
          "Waiting for your approval" in str(got.get("said", "")), repr(got))
    check("the step is not recorded as having run",
          steps and steps[0].get("ran") is False, repr(steps))
    # BOTH apps render a "tool_finished" step as "<tool> done"
    # (jarvis-desktop/src/step-words.js, .../net/Steps.kt), so emitting one here
    # would show the owner "change_setting done" while the card is still up and
    # nothing has changed - the looks-like-success failure this tool exists to
    # end. Found by a second reader; this pins the fix.
    finished = [e for e in events if e[0] and e[0][0] == "tool_finished"]
    check("no step event tells the apps it finished",
          finished == [], repr(events))
    check("a card this turn raised is counted against CARDS_PER_TURN",
          w.cards == 1, repr(w.cards))


def t_a_cosmetic_change_applies_and_says_so():
    rec = _Recording(R.Outcome(True, "Done - no jokes."))
    table = (rec.setting(key="humour", names=("humour",)),)
    got, steps, _events, w = run_tool("humour", "off", table=table)
    check("the setter was called with the value asked for", rec.calls == [False],
          repr(rec.calls))
    check("it is reported as changed", got.get("changed") is True, repr(got))
    check("nothing is reported as waiting", got.get("waiting") is False, repr(got))
    check("the step is recorded as run, under the gate's own word for no card",
          steps and steps[0].get("ran") is True and steps[0].get("outcome") == "auto",
          repr(steps))
    check("no card was counted", w.cards == 0, repr(w.cards))


def t_a_setter_that_refuses_changes_nothing_and_claims_nothing():
    rec = _Recording(R.Outcome(False, "Your settings file switches this off."))
    table = (rec.setting(key="web search", names=("web search",)),)
    got, steps, _events, _w = run_tool("web search", "on", table=table)
    check("it is not reported as changed", got.get("changed") is False, repr(got))
    check("it is not reported as ok", got.get("ok") is False, repr(got))
    check("the setter's own refusal is passed on",
          "switches this off" in str(got.get("error", "")), repr(got))
    check("the step reads as refused",
          steps and steps[0].get("outcome") == "refused", repr(steps))


def t_a_setter_that_raises_is_contained():
    class Boom:
        key = "an exploding setting"
        names = ("an exploding setting",)

        def set(self, on, *, peer=None, local=None):
            raise AttributeError("handle_post")

    table = (Boom(),)
    got, steps, _events, _w = run_tool("an exploding setting", "on", table=table)
    check("the raise does not escape the tool", isinstance(got, dict))
    check("it is reported as not changed", got.get("changed") is False, repr(got))
    check("the error names the failure",
          "AttributeError" in str(got.get("error", "")), repr(got))
    check("the step is unknown rather than a pass",
          steps and steps[0].get("outcome") == "unknown", repr(steps))


# --------------------------------------------------------------------------
#   4. a name it cannot resolve: nothing changed, no card, answered in words
# --------------------------------------------------------------------------

def t_an_unknown_name_changes_nothing_and_raises_no_card():
    rec = _Recording(R.Outcome(True, "Done."))
    table = (rec.setting(key="quiet hours", names=("quiet hours",)),)
    # The table is patched ACROSS the read as well as the call, so the sentence
    # the tool embeds and the sentence this test expects come from the SAME
    # table. Doing it the obvious way - call run_tool(), then read
    # changeable_words() - compares two different lists, because run_tool()
    # restores the real table before it returns: the tool's answer listed the one
    # patched switch and the expectation listed all 21.
    #
    # WHY NOT A LITERAL, which is what was here first. It read "You can change
    # these by asking", and that went stale the moment this branch met main -
    # main's own 2026-10-13 change rewrote the sentence to "You can change 51
    # settings by asking. Here is what they cover: ...". Running this suite on a
    # REAL merge of origin/main is the only place either side's CI could have
    # seen that, and it is why the check now reads the registry instead of
    # quoting it.
    real = R.BOOL_SETTINGS
    R.BOOL_SETTINGS = table
    try:
        got, steps, _events, w = run_tool("turn off the turbo setting", "off")
        expected = R.changeable_words()
    finally:
        R.BOOL_SETTINGS = real
    check("NO setter was reached", rec.calls == [], repr(rec.calls))
    check("no card was raised", w.cards == 0, repr(w.cards))
    check("it is reported as not changed", got.get("changed") is False, repr(got))
    check("it says it cannot change it",
          "cannot change" in str(got.get("error", "")), repr(got))
    check("and it lists what CAN be changed, from the registry itself",
          expected in str(got.get("error", "")), repr(got))
    check("the step reads as refused with nothing run",
          steps and steps[0].get("ran") is False and steps[0].get("outcome") == "refused",
          repr(steps))


def t_a_setting_that_lives_on_the_page_names_the_page():
    got, _steps, _events, _w = run_tool("app lock", "on")
    err = str(got.get("error", ""))
    check("it says the setting cannot be changed by asking",
          "cannot change" in err, err)
    check("it names the Settings screen and the row to use instead",
          "Settings" in err and "App lock" in err, err)
    check("it does not pretend it was done", got.get("changed") is False, repr(got))


def t_a_bad_value_changes_nothing():
    rec = _Recording(R.Outcome(True, "Done."))
    table = (rec.setting(key="quiet hours", names=("quiet hours",)),)
    got, _steps, _events, _w = run_tool("quiet hours", "maybe", table=table)
    check("no setter was reached", rec.calls == [], repr(rec.calls))
    check("the answer asks for on or off", "on" in str(got.get("error", "")),
          repr(got))


# --------------------------------------------------------------------------
#   5. a turn shaped by outside text changes nothing (stricter than speaking)
# --------------------------------------------------------------------------

def t_outside_text_stops_a_setting_change():
    for field, value, why in (("read", {"web_search": 1}, "a reading tool ran this turn"),
                              ("provenance", "pasted", "the newest message was not typed"),
                              ("app_context", True, "the app sent text of its own"),
                              ("flags", {"code": "why"}, "planted instructions were seen")):
        rec = _Recording(R.Outcome(True, "Done."))
        table = (rec.setting(key="quiet hours", names=("quiet hours",)),)
        got, _steps, _events, w = run_tool("quiet hours", "off", watch=_watch(**{field: value}),
                                          table=table)
        check(f"{why}: no setter is reached", rec.calls == [], repr(rec.calls))
        check(f"{why}: nothing is reported as changed",
              got.get("changed") is False, repr(got))
        check(f"{why}: no card is raised", w.cards == 0, repr(w.cards))
        check(f"{why}: the owner is told to say it themselves",
              "own words" in str(got.get("error", "")), repr(got))


def t_conversation_taint_alone_does_not_stop_it():
    """A DELIBERATE, DOCUMENTED LIMIT, pinned so it is a choice and not an
    accident. `tainted` is conversation-wide and sticky: once any earlier turn
    of a chat read outside text, every later turn of it is tainted. Refusing on
    that alone would mean the owner could not change a setting by asking for the
    rest of any chat in which Jarvis had once read an email or a page - and the
    SPOKEN path changes a setting in exactly that chat with no check at all, so
    it would be stricter than the app, only than the tool. What IS caught is
    above: everything that shaped THIS turn."""
    rec = _Recording(R.Outcome(True, "Done."))
    table = (rec.setting(key="quiet hours", names=("quiet hours",)),)
    got, _steps, _events, _w = run_tool("quiet hours", "off", watch=_watch(tainted=True),
                                       table=table)
    check("a tainted conversation on its own still changes the setting",
          rec.calls == [False], repr(rec.calls))
    check("and it is reported as changed", got.get("changed") is True, repr(got))


# --------------------------------------------------------------------------
#   6. no second path, and no new gate action invented
# --------------------------------------------------------------------------

def t_it_has_no_second_path():
    check("a plan cannot name it",
          AG.SETTINGS_TOOL in AG._PLAN_EXCLUDED_STEPS)
    check("the generic execute path refuses rather than changes anything",
          AG._execute_change_setting({}, None).get("ok") is False)
    check("a change is not recorded as reading anything",
          AG.SETTINGS_TOOL in AG._NOT_READING)
    state, text = AG._prepare_change_setting({})
    check("its prepare() carries no state, so reaching execute() could not write "
          "anything", state is None and isinstance(text, str) and bool(text),
          repr((state, text)))


def t_its_gate_action_already_exists():
    """The project's OWN check for this is in test_agent.py: it asserts that
    every tool's lookup name is a KEY of `jarvis_gate._TOOL_ACTIONS` - and it
    SKIPS wherever jarvis_gate is not importable, which is every CI job here.

    This suite has the repository's own `jarvis-backend/` on hand, so it runs
    the real thing instead of a substring search. That distinction matters: an
    earlier version of this check looked for `"change_own_config":` anywhere in
    the file, which jarvis_gate's `_RISK` table also satisfies, so it printed ok
    while `action_for_tool` really returned `unclassified_tool`. A second reader
    caught it (2026-10-13); `backend/gate-entries.patch` and the base now carry
    `"change_setting": "change_own_config"`."""
    if str(REPO / "jarvis-backend") not in sys.path:
        sys.path.append(str(REPO / "jarvis-backend"))
    gate = importlib.import_module("jarvis_gate")
    tool = AG.TOOLS[AG.SETTINGS_TOOL]
    lookup = tool.gate_lookup_name({}) if tool.gate_lookup_name else AG.SETTINGS_TOOL
    check("its lookup name is a KEY of jarvis_gate._TOOL_ACTIONS "
          "(exactly what test_agent.py checks)", lookup in gate._TOOL_ACTIONS,
          repr(lookup))
    check("and it resolves to the action the Reach page shows",
          gate.action_for_tool(lookup, {})[0] == AG.SETTINGS_GATE_ACTION,
          repr(gate.action_for_tool(lookup, {})))
    check("that action is not the tool's own name, so no new gate action, tier or "
          "card wording is invented",
          gate.action_for_tool(lookup, {})[0] != AG.SETTINGS_TOOL)
    toml = (REPO / "backend" / "rebuilt" / "jarvis-framework.toml").read_text(encoding="utf-8")
    check(f"[autonomy.tiers] already gives {AG.SETTINGS_GATE_ACTION!r} the tier the "
          f"Reach page shows",
          re.search(rf"^{re.escape(AG.SETTINGS_GATE_ACTION)}\s*=\s*\"ask\"", toml, re.M)
          is not None)


def t_a_phrase_that_names_no_setting_is_refused():
    """REGRESSION CASES for four REAL false positives that a second reader found
    in the first version of the tolerant matcher (2026-10-13).

    It accepted a request whose every word fitted INSIDE a longer alias name, so
    a bare category noun resolved to a switch that has nothing to do with it - and
    those switches apply with NO card, so the owner's words would have flipped a
    switch they never named. The exact spoken matcher returns None for all of
    them, and so must this. Each row records what it wrongly resolved to."""
    for phrase, was in (("graphics card", "better_voice"),
                        ("the graphics card", "better_voice"),
                        ("second graphics card", "better_voice"),
                        ("the second card", "better_voice"),
                        ("second card", "better_voice"),
                        ("pc sounds", "pc_alarm_sounds"),
                        ("the pc sounds", "pc_alarm_sounds"),
                        ("my pc sounds", "pc_alarm_sounds"),
                        ("screen mode", "screen_picture"),
                        ("the screen mode", "screen_picture"),
                        ("the big model", "big_coder")):
        got = R.find_bool_setting_words(phrase)
        check(f"{phrase!r} names no single switch (it used to reach {was})",
              got is None, repr(got and got.key))
        check(f"{phrase!r} is refused by the spoken matcher too",
              R.find_bool_setting(phrase) is None)
    # The restatements this matcher exists for must still work.
    for phrase, want in (("stop showing me notifications on my watch",
                          "smartwatch_notifications"),
                         ("search the web", "web_search"),
                         ("the watch notifications thing", "smartwatch_notifications"),
                         ("quiet hours", "pc_quiet_hours")):
        got = R.find_bool_setting_words(phrase)
        check(f"{phrase!r} still reaches {want}",
              got is not None and got.key == want, repr(got and got.key))


# --------------------------------------------------------------------------
#   7. every function a setting's setter calls must exist (the humour bug)
# --------------------------------------------------------------------------

def missing_module_calls(source: str) -> tuple:
    """((function, alias.attribute) pairs whose attribute does NOT exist,
    (function, module) pairs that could not be imported here).

    THE SHAPE OF THE BUG THIS EXISTS FOR: `set_humor` called
    `MN.handle_post({"humor": ...})`, and jarvis_manner.py has only
    `handle_get` and `handle_set`. The phrase "turn on humour" therefore raised
    AttributeError and could not work, while the Settings page's own route went
    through handle_set and did. The module is imported FOR REAL here, so this
    proves the attribute exists rather than that it is spelled the same
    somewhere else.

    THE SECOND LIST IS THE POINT OF RETURNING TWO (a second reader asked): a
    module this environment cannot import is NOT evidence that its attributes are
    right. The caller reports each one as a SKIP, never folds it into a pass - a
    check that could not run is not a pass (CLAUDE.md)."""
    tree = ast.parse(source)
    bad, skipped = [], []
    for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        aliases = {}
        for node in ast.walk(fn):
            if isinstance(node, ast.Import):
                for a in node.names:
                    aliases[a.asname or a.name.split(".")[0]] = a.name
        if not aliases:
            continue
        for node in ast.walk(fn):
            if not (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                    and node.value.id in aliases):
                continue
            module = aliases[node.value.id]
            try:
                mod = importlib.import_module(module)
            except Exception:
                if (fn.name, module) not in skipped:
                    skipped.append((fn.name, module))
                continue
            if not hasattr(mod, node.attr):
                bad.append((fn.name, f"{node.value.id}.{node.attr}"))
    return bad, skipped


def t_every_setter_calls_a_function_that_exists():
    src = (HERE / "jarvis_settings_registry.py").read_text(encoding="utf-8")
    wanted = {b.set.__name__ for b in R.BOOL_SETTINGS}
    bad, skipped = missing_module_calls(src)
    bad = [row for row in bad if row[0] in wanted]
    mine_skipped = sorted({m for f, m in skipped if f in wanted})
    for module in mine_skipped:
        skipped(f"a switch's setter imports {module}", "not importable in this environment")
    check(f"all {len(wanted)} switches' setters call functions that exist "
          f"({len(mine_skipped)} module(s) reported as SKIP above, never as a pass)",
          not bad, repr(bad))
    # The instrument proves itself on the bug it was written from: the same
    # checker, run over the shape the registry really used - the import INSIDE
    # the setter, which is how every one of these functions imports its module.
    control = ("def set_humor_before_the_fix(on):\n"
               "    import jarvis_manner as MN\n"
               "    return MN.handle_post({'humor': on})\n")
    control_bad, control_skipped = missing_module_calls(control)
    check("the checker finds that same bug if it comes back",
          control_bad == [("set_humor_before_the_fix", "MN.handle_post")],
          repr(control_bad))
    check("and the fixed call is real", hasattr(importlib.import_module("jarvis_manner"),
                                                "handle_set"))


def t_a_pending_change_cannot_back_an_i_did_it_claim():
    """The honesty machinery already in the tree, tied in (jarvis_claims.py).

    A change still waiting on its card must NOT let the model's answer stand as
    "I have done it" - that is the exact shape of the failure this tool exists
    to end: an answer that sounds like it did something. It falls out of
    recording a pending change as NOT run, so this pins that choice."""
    import jarvis_claims as CL
    waiting = _Recording(R.Outcome(True, "Waiting for your approval.", waiting=True))
    _got, steps, _e, _w = run_tool(
        "background learning", "on",
        table=(waiting.setting(key="background learning", names=("background learning",)),))
    check("a change waiting on a card does not back a done claim",
          CL.action_succeeded(steps) is False, repr(steps))
    done = _Recording(R.Outcome(True, "Done - no jokes."))
    _got2, steps2, _e2, _w2 = run_tool(
        "humour", "off", table=(done.setting(key="humour", names=("humour",)),))
    check("a cosmetic change that really happened does back it",
          CL.action_succeeded(steps2) is True, repr(steps2))


def t_an_answer_that_has_asked_too_often_changes_nothing():
    """CARDS_PER_TURN is checked BEFORE the setting is named, because this tool
    cannot know in advance whether the setting's own rule will ask - and by the
    time it has decided, its card is already up. So the turn's card limit holds
    for this tool too, including for a change that would have needed no card."""
    rec = _Recording(R.Outcome(True, "Done."))
    table = (rec.setting(key="humour", names=("humour",)),)
    w = _watch()
    w.cards = AG.CARDS_PER_TURN
    got, steps, _events, _w = run_tool("humour", "off", watch=w, table=table)
    check("no setter is reached once the answer has asked its fill",
          rec.calls == [], repr(rec.calls))
    check("nothing is reported as changed", got.get("changed") is False, repr(got))
    check("the owner is told to ask again in a new message",
          "new message" in str(got.get("error", "")), repr(got))
    check("the step reads as refused", steps and steps[0].get("outcome") == "refused",
          repr(steps))
    one_under = _watch()
    one_under.cards = AG.CARDS_PER_TURN - 1
    rec2 = _Recording(R.Outcome(True, "Done - no jokes."))
    table2 = (rec2.setting(key="humour", names=("humour",)),)
    got2, _s2, _e2, _w2 = run_tool("humour", "off", watch=one_under, table=table2)
    check("one under the limit still works", got2.get("changed") is True, repr(got2))


def t_one_call_routes_it_without_the_generic_gate():
    """The WIRING, which the rest of this suite does not touch: every other
    check here calls _settings_call directly, so the `if name == SETTINGS_TOOL:`
    branch in _one_call could be deleted and they would all still pass.

    `checker` is the generic approval gate. It records every call, and the
    assertion is that it is NEVER called - which is the whole safety argument:
    the setting's own setter is the gate, so one change cannot raise two cards
    (a generic card first, then the setting's own)."""
    rec = _Recording(R.Outcome(True, "Done - no jokes."))
    table = (rec.setting(key="humour", names=("humour",)),)
    convo, steps, events, gate_calls = [], [], [], []

    def checker(*a, **k):
        gate_calls.append(a)
        return None

    call = {"id": "c1", "function": {"name": AG.SETTINGS_TOOL,
            "arguments": json.dumps({"setting": "humour", "value": "off"})}}
    real = R.BOOL_SETTINGS
    R.BOOL_SETTINGS = table
    try:
        AG._one_call(call, [AG.SETTINGS_TOOL], convo, steps, checker, None, None,
                     lambda *a, **k: events.append((a, k)), watch=_watch())
    finally:
        R.BOOL_SETTINGS = real
    check("_one_call routes change_setting to the setting's own path",
          rec.calls == [False], repr(rec.calls))
    check("the generic approval gate is NEVER consulted, so one change cannot "
          "raise two cards", gate_calls == [], repr(gate_calls))
    check("the model is handed a tool result",
          bool(convo) and convo[-1].get("role") == "tool", repr(convo))
    check("the step is recorded against the tool",
          bool(steps) and steps[0].get("tool") == AG.SETTINGS_TOOL, repr(steps))

    # A call to a tool this turn was not offered changes nothing at all.
    rec.calls.clear()
    convo2, steps2 = [], []
    R.BOOL_SETTINGS = table
    try:
        AG._one_call(call, ["calculator"], convo2, steps2, checker, None, None,
                     lambda *a, **k: None, watch=_watch())
    finally:
        R.BOOL_SETTINGS = real
    check("a call the turn was not offered changes nothing", rec.calls == [],
          repr(rec.calls))
    # _one_call refuses a call whose arguments or name do not fit BEFORE any
    # step is recorded (it only tells the model), so the honest assertion is
    # that nothing at all was recorded as running.
    check("and nothing is recorded as having run", steps2 == [], repr(steps2))
    told = json.loads(convo2[-1]["content"]) if convo2 else {}
    check("the model is told the tool is not one it has here",
          told.get("ok") is False and "no such tool" in str(told.get("error", "")),
          repr(convo2))


def t_every_one_of_the_22_switches_resolves_from_its_own_names():
    """The tool's resolver must reach every switch the spoken grammar reaches -
    a name that resolves for the phrase path but not for the tool would leave
    exactly the gap this tool exists to close."""
    missing = []
    for b in R.BOOL_SETTINGS:
        for name in b.names:
            got = R.find_bool_setting_words(name)
            if got is None or got.key != b.key:
                missing.append((b.key, name, None if got is None else got.key))
    check(f"all {len(R.BOOL_SETTINGS)} switches answer to every one of their names",
          not missing, repr(missing))
    # 23 since 2026-10-19 (F5 S2): `media_index` joined the spoken table. Its
    # setter calls the module's own request_enabled(), the same function the
    # Settings card route calls, so the tool can reach it exactly as the phrase
    # can - which is what this test is about.
    check("the count is still the 23 measured on 2026-10-19 (22 before it)",
          len(R.BOOL_SETTINGS) == 23, str(len(R.BOOL_SETTINGS)))


def gate_signs_in(source: str, fn_name: str) -> list:
    """Names in ONE function of `source` that would mean it puts a change to a
    gate (or asks a person) rather than applying it. Read with `ast`, so a
    comment saying "no card" cannot make this pass.

    THE LIMIT, said plainly: this reads ONE function's own body. A setter that
    is a thin wrapper (set_background_learning, set_learn_sensitive) calls
    another module which does the asking, so an empty answer here means "this
    function raises no card itself", never "this change needs no card" - the
    second claim is the tier rows' job, above."""
    signs = []
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.FunctionDef) and node.name == fn_name):
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.Name) and "gate" in sub.id.lower():
                signs.append(sub.id)
            if isinstance(sub, ast.Attribute) and "gate" in sub.attr.lower():
                signs.append(sub.attr)
            if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute)
                    and sub.func.attr in ("check", "raise_card")):
                signs.append(f"{ast.unparse(sub.func)}()")
    return sorted(set(signs))


def function_source(source: str, fn_name: str) -> str:
    """One function's own body, as text (`ast.unparse`), for a check that has
    to see WHICH module a setter hands the change to."""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.FunctionDef) and node.name == fn_name:
            return ast.unparse(node)
    return ""


# --------------------------------------------------------------------------
#   8. the two things the 2026-10-13 field test turned on: is it OFFERED still,
#      and does the wording that made the model call it stay in place
# --------------------------------------------------------------------------

def t_it_ships_on_so_a_turn_really_offers_it():
    """FAILS IF THE TOOL STOPS BEING OFFERED. The field test found this half
    intact - `enabled_tools_for_turn` returned 28 names including this tool and
    `offered_tools` returned it - and it is the half that would take the
    feature away without a word: `offered_tools` silently drops a name in
    `[tools].enabled` that is not a tool here.

    The owner's decision of 2026-10-13 ("yes turn it on for my pc. it should
    also be enabled by default") is what the shipped file has to keep saying;
    the owner's own PC reads `~/.openjarvis/config.toml`'s list, which no test
    on another machine can check, so what is pinned here is the SHIPPED
    file - `backend/rebuilt/jarvis-framework.toml`, the copy this repository
    puts beside `jarvis_hud.py` on a fresh install."""
    toml = (REPO / "backend" / "rebuilt" / "jarvis-framework.toml").read_text(encoding="utf-8")
    m = re.search(r"^enabled\s*=\s*\[(.*?)\]", toml, re.M | re.S)
    enabled = [n.strip().strip('"') for n in m.group(1).split(",")] if m else []
    check("the shipped settings file names it in [tools].enabled",
          AG.SETTINGS_TOOL in enabled, repr(enabled))
    check("so a fresh install's turn OFFERS it",
          AG.SETTINGS_TOOL in AG.offered_tools(set(enabled)),
          repr(AG.offered_tools(set(enabled))))
    check("and it is a real tool, so the turn could actually run a call to it",
          AG.SETTINGS_TOOL in AG.TOOLS)
    check("a turn that names NO tools still does not offer it - the switch is "
          "the only thing that turns it on",
          AG.SETTINGS_TOOL not in AG.offered_tools(set()), repr(AG.offered_tools(set())))


def t_its_description_tells_the_model_to_call_it():
    """THE WORDING IS THE FIX, so it is pinned like the rest of the tool text
    (backend/test_tool_text.py pins the shape of every description).

    Measured on the owner's own PC and model (qwen3.5:9b) through the real turn
    on 2026-10-13, HEAD's whole module against this branch's: the same seven
    owner-worded requests three times each, the owner's own `[tools].enabled`
    list, every question tagged `provenance: "typed"` as both apps tag it, a
    recording setter so a call is visible and harmless, and the calculator
    request as a control. The old text - a note ABOUT the tool, third person,
    bare setting names as examples, and "say so plainly" offering an answer in
    words as a fine outcome - called it 0 times in 21 at temperature 0 and 3 in
    21 at the model's own 1.0, while the control called its own tool 3/3 and
    2/3. The text below calls it 18 in 21 at temperature 0 and 13 in 21 at 1.0,
    control 3/3 and 3/3. `_settings_tool_text`'s own docstring in
    jarvis_agent.py carries the full record, including what this is NOT (one
    request in twenty still finds no call at the model's own temperature, and
    "turn on background learning" was never called in any run).

    Each check below is one of the levers that measurement found, so this fails
    if the text drifts back into a note rather than an instruction."""
    text = AG.TOOLS[AG.SETTINGS_TOOL].schema()["function"]["description"]
    check("it opens by telling the model to call the tool",
          text.startswith("Call this tool when the owner asks you to change "), text[:60])
    check("it says not to ask first - the old text's replies kept asking",
          "do not ask first, just call it" in text)
    for phrase in ("turn on humour", "switch the prompt coach off",
                   "enable web search", "turn on quiet hours"):
        check(f"its examples are whole sentences the owner says ({phrase!r})",
              phrase in text)
    check('it says the value is "on" or "off", as the parameter demands',
          '"value" is on or off' in text)
    check("it says the tool's OWN RESULT reports the change, which keeps the "
          "honesty half of the old last line",
          "Its own result says what happened" in text
          and "never say a setting changed when it did not" in text)
    check("the old escape hatch is gone - 'say so plainly' was the line that "
          "let a text answer stand in for a call",
          "say so plainly" not in text)
    check("the full list of switches is still deliberately NOT in it (the "
          "registry answers with it when a name cannot be changed)",
          "background learning" not in text and "quiet hours" in text)


def t_the_tier_rule_is_untouched_by_the_wording():
    """THE DOOR, WHICH THE WORDING MUST NOT MOVE.

    Driven END TO END on 2026-10-13 with the real setters, the real gate and a
    temp config dir (nothing of the owner's touched): `change_setting("humour",
    "on")` applied at once, reported changed true, raised no card, and wrote
    `{"humor": true}`; `change_setting("sensitive topics automatically", "on")`
    raised ONE card (`cards == 1`), reported `changed` false and `waiting`
    true, and changed nothing. That drive is NOT in this suite: the
    sensitive-topics path imports the memory embedder, which downloads a 66 MB
    model, and a suite must not need the network. What a suite can hold is
    pinned here instead - the shipped tier for the actions those setters use,
    and that the cosmetic setters' own bodies raise no card (the limit of that
    reading is in gate_signs_in's own docstring)."""
    toml = (REPO / "backend" / "rebuilt" / "jarvis-framework.toml").read_text(encoding="utf-8")
    for action in ("learning_sensitive_enable", "learning_auto_enable"):
        check(f"{action} still asks first in the shipped file",
              re.search(rf"^{action}\s*=\s*\"ask\"", toml, re.M) is not None)
    src = (HERE / "jarvis_settings_registry.py").read_text(encoding="utf-8")
    for fn in ("set_humor", "set_pc_quiet_hours"):
        signs = gate_signs_in(src, fn)
        check(f"{fn} raises no card of its own (nothing gate-shaped in it, and "
              f"the module it calls - the manner wording, this PC's notification "
              f"choices - asks nobody)", signs == [], repr(signs))
    # The two that DO ask: as thin wrappers, so the card is raised one level
    # down, in the module whose own tier rows are pinned above. Named here so
    # the difference between these and the two above is a check and not a
    # reader's assumption.
    for fn in ("set_background_learning", "set_learn_sensitive"):
        body = function_source(src, fn)
        check(f"{fn} hands the change to jarvis_auto_learn's own request(), "
              f"where the card is raised", "handle_post" in body, body[:200])
    check("the same function is what change_setting calls for the cosmetic one",
          R.find_bool_setting_words("humour") is not None
          and R.find_bool_setting_words("humour").set is R.set_humor)
    check("and the privacy one resolves to its own setter, not a cosmetic one",
          (R.find_bool_setting_words("sensitive topics automatically") or None)
          is not None
          and R.find_bool_setting_words("sensitive topics automatically").set
          is R.set_learn_sensitive)
    check("the tool itself still carries no gate action of its own",
          AG.SETTINGS_GATE_ACTION != AG.SETTINGS_TOOL)


if __name__ == "__main__":
    for fn in (t_the_tool_exists_and_is_offered_only_when_enabled,
               t_asking_and_speaking_run_the_same_function,
               t_the_two_entrances_resolve_through_the_one_table,
               t_a_change_waiting_on_its_card_is_not_reported_as_done,
               t_a_cosmetic_change_applies_and_says_so,
               t_a_setter_that_refuses_changes_nothing_and_claims_nothing,
               t_a_setter_that_raises_is_contained,
               t_an_unknown_name_changes_nothing_and_raises_no_card,
               t_a_setting_that_lives_on_the_page_names_the_page,
               t_a_bad_value_changes_nothing,
               t_an_answer_that_has_asked_too_often_changes_nothing,
               t_outside_text_stops_a_setting_change,
               t_conversation_taint_alone_does_not_stop_it,
               t_it_has_no_second_path,
               t_one_call_routes_it_without_the_generic_gate,
               t_its_gate_action_already_exists,
               t_a_phrase_that_names_no_setting_is_refused,
               t_every_setter_calls_a_function_that_exists,
               t_a_pending_change_cannot_back_an_i_did_it_claim,
               t_every_one_of_the_22_switches_resolves_from_its_own_names,
               t_it_ships_on_so_a_turn_really_offers_it,
               t_its_description_tells_the_model_to_call_it,
               t_the_tier_rule_is_untouched_by_the_wording):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            import traceback
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
