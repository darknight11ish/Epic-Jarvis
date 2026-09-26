"""The plug-in bridge (jarvis_mcp.py) inside jarvis_agent's real tool loop,
against a REAL child process (fake_mcp_server.py).

What is proven (feasibility audit I07; replaces the draft's
test_agent_wiring.py and its patch, which no longer applied):
  - plug-in tools are reached ONLY through more_tools("plugins"), whether or
    not the short tool list is on, and only when [mcp] lists a server;
  - opening "plugins" starts the program through this turn's gate - one
    start card, "mcp_start__<server>" - and a refused start adds nothing;
  - each call is put to the gate under its OWN action ("mcp__fake__echo"),
    not folded into "unclassified_tool", with the arguments in full;
  - it runs only on a person's yes: a tier that lets it through with nobody
    asked is refused, and a denial runs nothing;
  - what the program sends back is outside text: labelled, marked
    untrusted, it counts as a tool that ran (so jarvis_chat_log marks the
    conversation), and a note write after it waits for a yes;
  - a later turn of the same chat gets the running program's tools back
    with no second card.

    python3 test_mcp_wiring.py
"""
import json
import os
import sys
import tempfile
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402
require_shipped("jarvis_agent.py", "jarvis_mcp.py", "jarvis_child_env.py")
sys.path.append(str(HERE / "rebuilt"))
import jarvis_agent as AG  # noqa: E402
import jarvis_mcp as M  # noqa: E402
import test_mcp as T  # noqa: E402  (its fixtures: the fake server, Gate, pins)
from test_agent import NoRealIO, scripted_stream  # noqa: E402

AG._manner_now = lambda: None
FAILED, PASSED = [], []
TMP = tempfile.mkdtemp(prefix="mcp-wiring-")


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def said(*calls):
    return {"choices": [{"message": {"role": "assistant", "tool_calls": [
        {"id": f"c{i}", "function": {"name": n, "arguments": json.dumps(a)}}
        for i, (n, a) in enumerate(calls)]}}]}


def answer(text="done"):
    return {"choices": [{"message": {"role": "assistant", "content": text}}]}


def fake_gate_module():
    """jarvis_gate's action_for_tool as the owner's has it: a table, and
    anything unknown folded into "unclassified_tool"."""
    g = types.ModuleType("jarvis_gate")
    g.action_for_tool = lambda name, args: (
        {"append_obsidian_daily": "append_obsidian_daily"}.get(name, "unclassified_tool"),
        None)
    return g


class Setup:
    """[mcp] listing the fake server with echo pinned, a private config
    folder, and the owner's gate table - put back afterwards."""

    def __init__(self, configured=True):
        self.configured = configured

    def __enter__(self):
        self.load, self.dir = M._load_section, M._config_dir
        sec = T.section(tools=T.tools("echo")) if self.configured else {}
        M._load_section = lambda: sec
        M._config_dir = lambda: TMP
        self.gate_mod = sys.modules.get("jarvis_gate")
        sys.modules["jarvis_gate"] = fake_gate_module()
        return self

    def __exit__(self, *a):
        M._load_section = lambda: {}
        M.shared_bridge()                    # stops every server it started
        M._load_section, M._config_dir = self.load, self.dir
        if self.gate_mod is None:
            sys.modules.pop("jarvis_gate", None)
        else:
            sys.modules["jarvis_gate"] = self.gate_mod
        try:
            os.remove(os.path.join(TMP, M.APPROVALS_FILE))
        except OSError:
            pass
        return False


def turn(responses, gate, *, cid="chat-1", enabled=None, user="what changed in the repo?"):
    opener, bodies = scripted_stream(responses)
    real = AG.short_list_on
    AG.short_list_on = lambda: False
    try:
        with NoRealIO():
            out = AG.run_local_turn(
                [{"role": "user", "content": user}], "qwen3:8b",
                ollama_url="http://127.0.0.1:11434", stream_out=lambda b: None,
                open_stream=opener, gate_check=gate,
                enabled_tools={"calculator", "append_obsidian_daily"} if enabled is None
                else enabled,
                request={"conversation_id": cid, "messages": [
                    {"role": "user", "content": user, "provenance": "typed"}]})
    finally:
        AG.short_list_on = real
    return out, bodies


def names(body):
    return [t["function"]["name"] for t in body.get("tools") or []]


def tool_replies(body):
    return [json.loads(m["content"]) for m in body["messages"] if m.get("role") == "tool"]


# --------------------------------------------------------------------------

def t_plugins_only_through_more_tools_and_only_when_listed():
    with Setup(configured=False):
        _o, bodies = turn([answer()], T.Gate())
        check("nothing listed under [mcp]: no more_tools (short list off)",
              AG.MORE_TOOLS not in names(bodies[0]), names(bodies[0]))
    with Setup():
        _o, bodies = turn([answer()], T.Gate(), cid="chat-listed")
        tools = {t["function"]["name"]: t for t in bodies[0]["tools"]}
        check("a server listed: more_tools is offered, even with the short list off",
              AG.MORE_TOOLS in tools, list(tools))
        enum = tools[AG.MORE_TOOLS]["function"]["parameters"]["properties"]["group"]["enum"]
        check("and its only group is plugins", enum == [AG.PLUGINS], enum)
        check("no plug-in tool is shown before it is asked for",
              not any(n.startswith("mcp_") for n in tools), list(tools))
        check("no program was started just by a turn", M.reach_status()["running"] == [])
        _o, bodies = turn([said(("mcp_fake__echo", {"text": "hi"})), answer()], T.Gate(),
                          cid="chat-early")
        reply = tool_replies(bodies[1])[0]
        check("a plug-in tool called before it is opened is 'no such tool'",
              "no such tool" in reply.get("error", ""), reply)


def t_a_whole_turn_start_card_call_card_outside_text():
    with Setup():
        gate = T.Gate()
        out, bodies = turn([said(("more_tools", {"group": "plugins"})),
                            said(("mcp_fake__echo", {"text": "hi"})),
                            said(("append_obsidian_daily", {"text": "echoed"})),
                            answer()], gate)
        asked = [c[0] for c in gate.calls]
        check("opening plugins raised ONE start card, for this server",
              asked[:1] == ["mcp_start__fake"], asked)
        check("the plug-in tool is shown from the next round", "mcp_fake__echo" in names(bodies[1]))
        opened = tool_replies(bodies[1])[0]
        check("the model is told which tools are ready",
              "mcp_fake__echo" in opened.get("note", ""), opened)
        check("the call is put to the gate under its own action, not unclassified_tool",
              "mcp__fake__echo" in asked and "unclassified_tool" not in asked, asked)
        card = next(c[1]["text"] for c in gate.calls if c[0] == "mcp__fake__echo")
        check("its card shows the arguments in full", '"text": "hi"' in card, card)
        result = tool_replies(bodies[2])[-1]
        check("it ran, once, after the yes", "echo: hi" in json.dumps(result), result)
        check("its result is labelled as outside text by the loop",
              result.get(AG.OUTSIDE_FIELD) == AG.OUTSIDE_LABEL, result)
        check("and as untrusted by the bridge", result.get("untrusted") is True, result)
        check("it counts as a tool that ran (so the chat log marks the conversation)",
              out["tools_ran"][:1] == ["mcp_fake__echo"], out["tools_ran"])
        check("more_tools is not in that list", AG.MORE_TOOLS not in out["tools_ran"])
        check("a note write after it waits for a yes (the outside-text rule)",
              AG.NOTE_AFTER_OUTSIDE_ACTION in asked, asked)
        check("the start was remembered for next time",
              "fake" in json.load(open(os.path.join(TMP, M.APPROVALS_FILE))))

        gate2 = T.Gate()
        _o, bodies = turn([answer()], gate2)
        check("a later turn of the same chat has the tool back with no card",
              "mcp_fake__echo" in names(bodies[0]) and gate2.calls == [], gate2.calls)
        _o, bodies = turn([answer()], T.Gate(), cid="chat-other")
        check("another chat does not", "mcp_fake__echo" not in names(bodies[0]))


def t_only_a_person_s_yes_runs_it():
    with Setup():
        gate = T.Gate(lambda a: "approve" if a.startswith("mcp_start__") else "auto")
        _o, bodies = turn([said(("more_tools", {"group": "plugins"})),
                           said(("mcp_fake__echo", {"text": "hi"})), answer()], gate,
                          cid="chat-auto")
        result = tool_replies(bodies[2])[-1]
        check("a tier that lets it through with nobody asked is refused",
              result.get("ok") is False and "echo: hi" not in json.dumps(result), result)
        check("and it says why, in words", "plug-in program" in result.get("error", ""),
              result)
        gate = T.Gate(lambda a: "approve" if a.startswith("mcp_start__") else "deny")
        _o, bodies = turn([said(("more_tools", {"group": "plugins"})),
                           said(("mcp_fake__echo", {"text": "hi"})), answer()], gate,
                          cid="chat-deny")
        result = tool_replies(bodies[2])[-1]
        check("a denial runs nothing", result.get("ok") is False
              and "echo: hi" not in json.dumps(result), result)


def t_a_refused_start_adds_nothing():
    with Setup():
        gate = T.Gate("deny")
        _o, bodies = turn([said(("more_tools", {"group": "plugins"})), answer()], gate,
                          cid="chat-nostart")
        reply = tool_replies(bodies[1])[0]
        check("the start card was asked", [c[0] for c in gate.calls] == ["mcp_start__fake"])
        check("the model is told it was not started", reply.get("ok") is False
              and "not started" in reply.get("error", ""), reply)
        check("no plug-in tool is shown", not any(n.startswith("mcp_") for n in names(bodies[1])))
        check("nothing is running", M.reach_status()["running"] == [])


def t_the_cards_titles_and_the_two_lists():
    import jarvis_card_words as W
    check("the start card's title names the owner's program",
          W.title_for("mcp_start__repo") == 'Jarvis wants to start the plug-in program "repo"')
    check("a call's title names the program, not the tool the program named",
          W.title_for("mcp__repo__git_status")
          == 'Jarvis wants to use a tool from the plug-in program "repo"')
    import jarvis_reach as R
    ctx = R.Ctx(enabled={"calculator"}, tier=lambda a: "ask", env=lambda n: "",
                lanes=[], providers=[], search={}, key_saved=lambda p: False,
                second_card={"master": False}, big_model={"master": False},
                gate_action=lambda lookup: None,
                plugins={"servers": ["repo"], "running": [], "problem": "",
                         "card_every_start": False})
    row = R._plugins(ctx)
    check("reach: listed and tools on - the row is on, and asks every time",
          row["state"] == "on" and row["asks"] == R.ASK_EVERY and "repo" in row["where"], row)
    ctx.plugins = {"servers": [], "running": [], "problem": "", "card_every_start": False}
    check("reach: nothing listed - not set up", R._plugins(ctx)["state"] == "not_set_up")
    ctx.plugins = {"servers": [], "running": [], "problem": "bad line", "card_every_start": False}
    check("reach: a mistake in [mcp] - off, and says so",
          R._plugins(ctx)["state"] == "off" and "bad line" in R._plugins(ctx)["line"])
    check("reach: the row is in KINDS", any(k == "plugins" for k, _f in R.KINDS))
    import jarvis_asks_first as AF
    rows = {r["id"]: r for g in AF.view()["groups"] for r in g["rows"]}
    check("What asks first: a call always asks",
          rows["fixed:plugin_use"]["says"] == AF.SAYS["ask"], rows.get("fixed:plugin_use"))
    check("What asks first: a start asks when new or changed (question 9's answer)",
          rows["fixed:plugin_start"]["says"] == AF.PLUGIN_START_SAYS)
    real = M.CARD_EVERY_START
    M.CARD_EVERY_START = True
    try:
        rows = {r["id"]: r for g in AF.view()["groups"] for r in g["rows"]}
        check("and follows the one-line switch", rows["fixed:plugin_start"]["says"]
              == AF.SAYS["ask"] and "every time" in rows["fixed:plugin_start"]["note"])
    finally:
        M.CARD_EVERY_START = real


if __name__ == "__main__":
    for fn in (t_the_cards_titles_and_the_two_lists,
               t_plugins_only_through_more_tools_and_only_when_listed,
               t_a_whole_turn_start_card_call_card_outside_text,
               t_only_a_person_s_yes_runs_it,
               t_a_refused_start_adds_nothing):
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
