"""test_github_tools_by_chat.py - the owner talks about the GitHub tools, and
switches them on, in chat or Jarvis Live (2026-11-15).

    python3 backend/test_github_tools_by_chat.py

THE OWNER'S OWN WORDS, and the measurements that made this suite exist:

    "i should be able to talk to jarvis about what github tools or has
     available, what is enabled, and activate them through chat or jarvis live"

Measured on the installed build (0.2.456) through the real /api/chat route on
2026-11-15, with the message tagged `provenance: "typed"` the way both apps tag
it (see `jarvis_quick.newest_own_words` - WITHOUT that tag every turn skips the
fast path and reaches the model, which is how the first readings of this were
taken and why they were wrong):

    "what github tools do you have"      fast path, 0.1 s - the inventory  OK
    "what github tools are switched on"  MODEL: "I don't have access to a list
                                         of which GitHub tools are currently
                                         switched on for you"              WRONG
    "turn on the github tools"           MODEL: "... Want me to raise the card
                                         so you can approve it here?"       WRONG

The facts behind both wrong answers:

  * `github_tools_group` is the ONE master switch for the twenty tools (the
    eighteen GitHub tools plus `review_changes` and `check_records`). It works
    end to end in `jarvis_asks_first.request_tool_enable`: ON is one card plus
    Windows Hello, OFF is instant and cardless.
  * It was NOT a spoken name: `GITHUB_TOOLS_GROUP in TOOLS_SWITCHABLE` was
    False and `find_tool_target("github")` was None, while
    `find_tool_target("browser control")` returned `browser_control`.
  * `_TOOL_SWITCH` demanded the SINGULAR word "tool", so "turn on the github
    TOOLS" matched nothing at all.
  * "enable the github tools" was claimed by the connect-a-token lane and
    answered with an offer to save a personal access token.

WHAT THIS SUITE PINS, and each one is a separate way the owner's request can
regress:

  1. every sentence he actually says resolves to the right intent;
  2. the group is a name in the registry's closed-world tool table, and a
     single tool's name still wins over it;
  3. ON asks for one card and writes NOTHING until a person says yes; OFF is
     instant and cardless;
  4. "what is enabled" answers with the LIVE count, from
     `jarvis_asks_first.tools_status`, and never offers to switch on what is
     already on;
  5. a model-driven `change_setting` call reaches the same group card, and
     reaches NOTHING else (a single tool's switch is not this door);
  6. the provenance rule above, so nobody re-measures the model and calls it
     the fast path.

No network, no model, no Windows, no card: every approval is a stub, and no
file this PC owns is written.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-gh-tools-chat-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
(_TMP / "config").mkdir(parents=True, exist_ok=True)
os.environ["JARVIS_FRAMEWORK_TOML"] = str(_TMP / "jarvis-framework.toml")

sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_quick.py", "jarvis_settings_registry.py",
                "jarvis_asks_first.py", "jarvis_agent.py")
if str(HERE / "rebuilt") not in sys.path:
    sys.path.append(str(HERE / "rebuilt"))

import jarvis_asks_first as AF  # noqa: E402
import jarvis_quick as Q  # noqa: E402
import jarvis_settings_registry as REG  # noqa: E402

PASSED: list = []
FAILED: list = []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name if cond else f"{name}  <-- {detail}")
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  <-- {detail}"))


#: The sentences the owner says, and what each one must become. Every one of
#: these was measured as the wrong answer (or no intent at all) before this
#: change, except the two marked "worked".
SENTENCES = (
    # --- switching the twenty on or off -----------------------------------
    ("turn on the github tools", "settings_tool", ("github_tools_group", True)),
    ("switch on the github tools", "settings_tool", ("github_tools_group", True)),
    ("enable the github tools", "settings_tool", ("github_tools_group", True)),
    ("turn the github tools on", "settings_tool", ("github_tools_group", True)),
    ("turn off the github tools", "settings_tool", ("github_tools_group", False)),
    ("disable the github tools", "settings_tool", ("github_tools_group", False)),
    ("let the ai model use github", "settings_tool", ("github_tools_group", True)),
    ("let the ai model use the github tools", "settings_tool",
     ("github_tools_group", True)),
    # --- what is available, and what is enabled ---------------------------
    ("what github tools do you have", "github_self", "tools"),      # worked
    ("what github tools are there", "github_self", "tools"),
    ("what github tools are switched on", "github_self", "tools_state"),
    ("what github tools are enabled", "github_self", "tools_state"),
    ("which github tools are switched on", "github_self", "tools_state"),
    ("are the github tools on", "github_self", "tools_state"),
    ("how many github tools are on", "github_self", "tools_state"),
)


def t_every_sentence_resolves_to_the_right_intent():
    """1. The owner's sentences, each to one intent - and never to the token card."""
    for text, want, payload in SENTENCES:
        got = Q.match(text)
        name = getattr(got, "name", None)
        fields = dict(getattr(got, "f", None) or {})
        if want == "settings_tool":
            tool, on = payload
            ok = (name == "settings_tool" and fields.get("tool") == tool
                  and bool(fields.get("on")) is on)
        else:
            ok = (name == "github_self" and fields.get("shape") == payload)
        check(f"{text!r} -> {want}", ok, (name, fields))
        check(f"{text!r} is never answered as a connect-token request",
              name != "connect_account", name)


def t_the_group_is_a_name_and_a_single_tool_still_wins():
    """2. The closed-world table: the group is a name, and 'github search' is not it."""
    check("github_tools_group is a spoken tool target",
          REG.find_tool_target("github") == AF.GITHUB_TOOLS_GROUP,
          REG.find_tool_target("github"))
    check("... and 'the github tools' is the same target",
          REG.find_tool_target("the github tools") == AF.GITHUB_TOOLS_GROUP,
          REG.find_tool_target("the github tools"))
    check("a single tool's own name still wins over the group",
          REG.find_tool_target("github search") == "github_search",
          REG.find_tool_target("github search"))
    check("... and so does another single tool",
          REG.find_tool_target("browser control") == "browser_control",
          REG.find_tool_target("browser control"))
    check("a sentence naming no tool resolves to nothing",
          REG.find_tool_target("the kitchen light") is None,
          REG.find_tool_target("the kitchen light"))
    check("the group is still NOT one of the per-tool switch rows",
          AF.GITHUB_TOOLS_GROUP not in AF.TOOLS_SWITCHABLE,
          "it is one switch speaking for twenty tools")


def t_on_asks_one_card_and_writes_nothing_until_a_person_says_yes():
    """3. ON: nothing happens until a person answers; the answer writes all twenty."""
    calls = {"cards": 0, "writes": [], "pending": []}

    class _V:
        tier = "ask"
        outcome = "approved"
        reason = ""
        approved = True

    real = {n: getattr(AF, n) for n in
            ("_gate", "_tier", "_spawn", "_owner_check_armed", "_person_said_yes",
             "tools_enabled_set")}
    # WHAT IS ON NOW IS STUBBED, and this is not tidiness. `request_tool_enable`
    # reads the live settings (`tools_enabled_set`, line ~2783 of
    # jarvis_asks_first.py) to decide whether there is anything to change, and
    # this suite only redirects the CONFIG DIR - on a PC whose settings file
    # names GitHub tools the real file is still found through the framework
    # loader's own search, and on CI it is not. So without these two stubs the
    # same check passes at the desk and fails in CI (measured 2026-11-15:
    # shard 2 red on "... and the group is written off in ONE step" because CI
    # read nothing as on, took the "already not offered" early return, and
    # wrote nothing - while the desk's live file said some were on).
    AF.tools_enabled_set = lambda: set()
    AF._gate = lambda action, detail, card: (calls.__setitem__("cards",
                                                              calls["cards"] + 1) or _V())
    AF._tier = lambda action: "ask"
    # `_spawn` is the thread that asks: captured, NOT run, so the suite can see
    # the state before anything is decided - which is the claim being pinned.
    AF._spawn = lambda fn: calls["pending"].append(fn)
    AF._owner_check_armed = lambda: True
    AF._person_said_yes = lambda v: True
    AF._reset_for_tests()
    try:
        code, out = AF.request_tool_enable(
            {"tool": AF.GITHUB_TOOLS_GROUP, "enabled": True}, here=True,
            write=lambda t, on: calls["writes"].append((t, on)))
        check("ON answers 202 waiting", code == 202 and out.get("waiting") is True,
              (code, out.get("waiting")))
        check("... the ask is raised, not yet answered", len(calls["pending"]) == 1,
              len(calls["pending"]))
        check("... NO card has been drawn before a person is asked",
              calls["cards"] == 0, calls["cards"])
        check("... and NOTHING is written until the card is answered",
              calls["writes"] == [], calls["writes"])
        check("... and the card is the twenty-tool group's own",
              "TWENTY" in AF.GITHUB_TOOLS_GROUP_CARD_TITLE.upper(),
              AF.GITHUB_TOOLS_GROUP_CARD_TITLE)
        check("... and the message tells him where to approve it",
              "Windows Hello" in str(out.get("message") or ""),
              out.get("message"))
        # Now the person answers: the captured ask runs and writes the twenty,
        # in ONE step, and only because the gate said a person said yes.
        calls["pending"][0]()
        check("after the yes, ONE card was drawn", calls["cards"] == 1,
              calls["cards"])
        check("... and all twenty are written in one step",
              calls["writes"] == [(AF.GITHUB_TOOLS_GROUP, True)], calls["writes"])
    finally:
        for n, fn in real.items():
            setattr(AF, n, fn)
        AF._reset_for_tests()


def t_off_is_instant_and_cardless():
    """3b. OFF: one write, no card at all, and it says Done."""
    calls = {"cards": 0, "writes": []}
    real = {n: getattr(AF, n) for n in
            ("_gate", "_tier", "_spawn", "_owner_check_armed", "tools_enabled_set")}
    # The group is ON now, so OFF has something to narrow - see the longer note
    # in `t_on_asks_one_card_and_writes_nothing_until_a_person_says_yes`.
    AF.tools_enabled_set = lambda: set(AF.GITHUB_TOOLS)
    AF._gate = lambda *a, **k: calls.__setitem__("cards", calls["cards"] + 1)
    AF._tier = lambda action: "ask"
    AF._spawn = lambda fn: None
    AF._owner_check_armed = lambda: True
    AF._reset_for_tests()
    try:
        code, out = AF.request_tool_enable(
            {"tool": AF.GITHUB_TOOLS_GROUP, "enabled": False}, here=True,
            write=lambda t, on: calls["writes"].append((t, on)))
        check("OFF answers 200 at once", code == 200, code)
        check("... with no card", calls["cards"] == 0, calls["cards"])
        check("... and the group is written off in ONE step",
              calls["writes"] == [(AF.GITHUB_TOOLS_GROUP, False)], calls["writes"])
        check("... and it says it is done",
              "not offered" in str(out.get("message") or ""), out.get("message"))
    finally:
        for n, fn in real.items():
            setattr(AF, n, fn)
        AF._reset_for_tests()


def _status_with(on_count: int, waiting: bool = False) -> dict:
    total = len(AF.GITHUB_TOOLS)
    return {"github_group": {"on_count": on_count, "total": total,
                             "waiting": waiting,
                             "on": on_count == total}}


def t_the_state_answer_says_the_live_count_and_how_to_change_it():
    """4. "what is enabled" - the count from tools_status, then the two sentences."""
    real_status = AF.tools_status
    try:
        cases = ((0, "Right now 0 of the 20 are switched on."),
                 (9, "Right now 9 of the 20 are switched on."),
                 (20, "All 20 are switched on right now."))
        for on, want in cases:
            AF.tools_status = lambda here=True, _n=on: _status_with(_n)
            got = Q._github_tools_group_state_words()
            check(f"{on} of 20 says {want!r}", got.startswith(want), got)
        # A waiting card is said, and said as NOT changed.
        AF.tools_status = lambda here=True: _status_with(0, waiting=True)
        got = Q._github_tools_group_state_words()
        check("a waiting card is said, and nothing is called changed",
              "waiting for your approval" in got and "switched on yet" in got, got)
        # ALL ON: never offer to switch on what is already on.
        AF.tools_status = lambda here=True: _status_with(20)
        how = Q._github_tools_how_words()
        check("with all twenty on, the offer is to stop, never to start",
              "already on" in how and "turn on the GitHub tools" not in how, how)
        check("... and it still names the cardless stop",
              "turn off the GitHub tools" in how, how)
        # NONE ON: both halves are said.
        AF.tools_status = lambda here=True: _status_with(0)
        how = Q._github_tools_how_words()
        check("with none on, both sentences are offered",
              "turn on the GitHub tools" in how and "Windows Hello" in how
              and "turn off the GitHub tools" in how, how)
        # An unreadable module says so instead of guessing a number.
        AF.tools_status = lambda here=True: (_ for _ in ()).throw(RuntimeError("x"))
        got = Q._github_tools_group_state_words()
        check("an unreadable group is said, never guessed",
              "could not read" in got and "0 of" not in got, got)
    finally:
        AF.tools_status = real_status


def t_the_state_shape_is_the_short_answer_not_the_inventory():
    """4b. tools_state answers with the count; the inventory stays for 'do you have'."""
    real_status = AF.tools_status
    AF.tools_status = lambda here=True: _status_with(0)
    try:
        short = Q._run_github_self({"shape": "tools_state"}).reply
        full = Q._run_github_self({"shape": "tools"}).reply
        check("the state answer names the count", "0 of the 20" in short, short[:200])
        check("... and how to change it", "turn on the GitHub tools" in short, short[:200])
        check("... and points at the inventory for the list",
              "what GitHub tools do you have" in short, short[:200])
        check("... and is far shorter than the inventory",
              len(short) < len(full) / 4, (len(short), len(full)))
    finally:
        AF.tools_status = real_status


def t_a_model_switch_call_reaches_the_group_card_and_nothing_else():
    """5. change_setting: the group resolves; a single tool's switch does not."""
    import jarvis_agent as AG

    seen = []

    class _Out:
        ok = True
        waiting = True
        said = "Waiting for your approval."

    real_set = REG.set_reading_tool
    real_now = REG.reading_tool_now
    real_receipt = getattr(Q, "_settings_receipt", None)
    REG.set_reading_tool = lambda tool, on, **k: (seen.append((tool, on)) or _Out())
    REG.reading_tool_now = lambda tool: None
    Q._settings_receipt = lambda *a, **k: None

    class _Watch:
        cards = 0
        read = None
        provenance = None
        app_context = None
        flags = None
        newest_own_words = ""

    def call(setting, value):
        steps, convo = [], []
        watch = _Watch()
        AG._settings_call({"setting": setting, "value": value},
                          {"id": "c1"}, convo, steps, lambda *a, **k: None,
                          watch=watch)
        return convo[-1]["content"] if convo else "", steps, watch

    try:
        content, steps, watch = call("the github tools", "on")
        check("'the github tools' reaches set_reading_tool with the group id",
              seen and seen[-1] == (AF.GITHUB_TOOLS_GROUP, True), seen)
        check("... and the model is told it is waiting, never that it changed",
              "waiting" in content.lower() and '"changed": true' not in content.lower(),
              content[:300])
        check("... and the turn counts the card it raised", watch.cards == 1,
              watch.cards)
        check("... and the step is NOT reported as done",
              steps and steps[-1].get("ran") is False, steps)
        seen.clear()
        content, steps, _ = call("the browser control tool", "on")
        check("a single tool's switch is NOT reached by this door",
              seen == [], seen)
        check("... it gets the plain cannot-change answer",
              "cannot" in content.lower() or "can't" in content.lower(),
              content[:300])
    finally:
        REG.set_reading_tool = real_set
        REG.reading_tool_now = real_now
        if real_receipt is not None:
            Q._settings_receipt = real_receipt


def t_the_provenance_tag_is_what_makes_the_fast_path_run():
    """6. Without the tag the model answers, and this suite would measure nothing."""
    bare = {"messages": [{"role": "user", "content": "what github tools do you have"}]}
    tagged = {"messages": [{"role": "user", "content":
                            "what github tools do you have", "provenance": "typed"}]}
    check("an untagged message is NOT the owner's own words",
          Q.newest_own_words(bare) is None, Q.newest_own_words(bare))
    check("... and a tagged one is",
          Q.newest_own_words(tagged) == "what github tools do you have",
          Q.newest_own_words(tagged))
    check("a system message stops it too, whatever the tag",
          Q.newest_own_words({"messages": [
              {"role": "system", "content": "x"},
              {"role": "user", "content": "y", "provenance": "typed"}]}) is None)


def t_no_new_switch_row_and_one_setter():
    """The whole feature rides doors that already exist - no new route, no new tool.

    These checks used to pin source TEXT, which the source-pin gate
    (tools/check_no_source_pins.py) counts against a ceiling - and one of them
    was worse than that: `"/api/asks_first/tools" not in src or True` can never
    fail. Both are gone: what replaces them is behaviour, so the checks survive
    a rename and mean something when they pass.

    "No new route" is proved by the state test above rather than here: it stubs
    `tools_status` and the answer follows the stub for 0, 9 and 20, so the words
    come from this PC's own registry read and not from anything fetched. (A
    blanket "imports no HTTP client" check would be false anyway -
    `jarvis_quick.py` does import `urllib.request`, for the update check.)

      1. the group is not a row of the per-tool switch table (it speaks for
         twenty), which is `t_the_group_is_a_name...`'s point from the other
         side;
      2. the registry has ONE setter and ONE reader, the pair every other
         switchable name uses, and the reader answers for the group too. The
         model-door test above already pins that `set_reading_tool` receives the
         group; this pins that nothing was added beside it. Read only, so this
         suite still writes nothing.
    """
    check("the group is not a row of the per-tool switch table",
          AF.GITHUB_TOOLS_GROUP not in AF.TOOLS_SWITCHABLE,
          AF.GITHUB_TOOLS_GROUP)

    setters = sorted(n for n in dir(REG) if n.startswith("set_") and "reading" in n)
    check("the registry has ONE setter for a reading tool",
          setters == ["set_reading_tool"], setters)
    readers = sorted(n for n in dir(REG) if n.startswith("reading_") and n.endswith("_now"))
    now = REG.reading_tool_now(AF.GITHUB_TOOLS_GROUP)
    check("... and ONE reader, which answers for the group",
          readers == ["reading_tool_now"] and isinstance(now, bool),
          (readers, now))


def main():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("t_") and callable(v)]
    for t in tests:
        print(f"--- {t.__name__} ---")
        try:
            t()
        except Exception as exc:            # a crash is a failure, with its trace
            import traceback
            traceback.print_exc()
            check(f"{t.__name__} ran to the end", False, repr(exc))
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("\nFAILED:")
        for f in FAILED:
            print(f"  {f}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
