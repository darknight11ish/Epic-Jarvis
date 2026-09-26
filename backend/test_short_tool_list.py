"""The short tool list, more on request (feasibility audit I06):
jarvis_agent.CORE_TOOLS, TOOL_GROUPS and `more_tools`.

What is proven, with a scripted model and nothing real touched:
  - every tool is in the core or in exactly one group, so a new tool cannot
    land nowhere (the Upkeep reviewer's test);
  - it is OFF unless `[tools] short_list = true` (SHORT_LIST_DEFAULT), and
    off, the model is sent exactly what it was sent before;
  - on, a turn shows the enabled core tools in a fixed order plus
    `more_tools`; opening a group adds that group's ENABLED tools for the
    rest of that conversation - never a tool that is switched off, never
    for another conversation;
  - `more_tools` runs nothing, asks nobody, is not outside text and is not a
    step (so it neither taints the chat nor counts for skill discovery);
  - a group opened after outside text is named on the next card;
  - a model that cannot use tools gets no tools and no `more_tools`;
  - the tokens it saves, by Jarvis's own estimate_tokens.

    python3 test_short_tool_list.py
"""
import json
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402
require_shipped("jarvis_agent.py")
sys.path.append(str(HERE / "rebuilt"))
import jarvis_agent as AG  # noqa: E402
from test_agent import NoRealIO, scripted_stream, RECORDED  # noqa: E402

AG._manner_now = lambda: None
FAILED, PASSED = [], []
REAL_SHORT = AG.short_list_on


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


class Gate:
    def __init__(self):
        self.asked = []

    def __call__(self, action, detail, prompt):
        self.asked.append((action, detail.get("text", "")))

        class V:
            allowed = True
            outcome = "approved"
            tier = "ask"
            request_id = f"r{len(self.asked)}"
            reason = "approved"
        V.action = action
        return V()


def turn(responses, *, enabled=None, short=True, cid="conv-1", gate=None, user="hi",
         can_use_tools=None):
    AG.short_list_on = (lambda: short)
    opener, bodies = scripted_stream(responses)
    gate = gate or Gate()
    real_can = AG._model_can_use_tools
    if can_use_tools is not None:
        AG._model_can_use_tools = lambda url, model: can_use_tools
    try:
        with NoRealIO():
            out = AG.run_local_turn(
                [{"role": "user", "content": user}], "qwen3:8b",
                ollama_url="http://127.0.0.1:11434", stream_out=lambda b: None,
                open_stream=opener, gate_check=gate,
                enabled_tools=set(AG.TOOLS) - {"browser_control"} if enabled is None
                else enabled,
                request={"conversation_id": cid,
                         "messages": [{"role": "user", "content": user,
                                       "provenance": "typed"}]})
    finally:
        AG.short_list_on = REAL_SHORT
        AG._model_can_use_tools = real_can
    return out, bodies, gate


def names(body):
    return [t["function"]["name"] for t in body.get("tools") or []]


# --------------------------------------------------------------------------

def t_every_tool_is_in_the_core_or_exactly_one_group():
    for name in AG.TOOLS:
        homes = (1 if name in AG.CORE_TOOLS else 0) + sum(
            1 for _g, _w, m in AG.TOOL_GROUPS if name in m)
        check(f"{name} has exactly one home ({homes})", homes == 1)
    check("the core names only real tools", all(n in AG.TOOLS for n in AG.CORE_TOOLS))
    check("no group is called more_tools, and the names are unique",
          len({g for g, _w, _m in AG.TOOL_GROUPS}) == len(AG.TOOL_GROUPS)
          and AG.MORE_TOOLS not in AG.TOOLS)
    check("plug-in tools have a group of their own, empty here",
          any(g == AG.PLUGINS and not m for g, _w, m in AG.TOOL_GROUPS))


def t_it_is_off_until_the_owner_turns_it_on():
    check("off by default, until the PC's tool test says it costs nothing",
          AG.SHORT_LIST_DEFAULT is False)
    import jarvis_framework as FW
    real = FW.load_framework
    try:
        FW.load_framework = lambda *a, **k: {}
        check("no setting: off", REAL_SHORT() is False)
        FW.load_framework = lambda *a, **k: {"tools": {"short_list": True}}
        check("short_list = true: on", REAL_SHORT() is True)
        FW.load_framework = lambda *a, **k: {"tools": {"short_list": "yes"}}
        check("anything but a real true: off", REAL_SHORT() is False)

        def broken(*a, **k):
            raise OSError("unreadable")
        FW.load_framework = broken
        check("an unreadable settings file: the default (off)", REAL_SHORT() is False)
    finally:
        FW.load_framework = real


def t_off_the_model_is_sent_what_it_was_sent_before():
    enabled = set(AG.TOOLS) - {"browser_control"}
    _o, bodies, _g = turn([answer()], short=False, enabled=enabled)
    before = [AG.TOOLS[n].schema(AG.offered_tools(enabled))
              for n in AG.offered_tools(enabled)]
    check("the same tools, the same words, the same order", bodies[0]["tools"] == before)
    check("no more_tools", AG.MORE_TOOLS not in names(bodies[0]))


def t_on_the_core_in_a_fixed_order_and_more_tools():
    _o, bodies, _g = turn([answer()])
    want = [n for n in AG.CORE_TOOLS] + [AG.MORE_TOOLS]
    check("the core, in CORE_TOOLS order, then more_tools", names(bodies[0]) == want,
          repr(names(bodies[0])))
    _o, bodies2, _g = turn([answer()], cid="conv-other")
    check("the same list, word for word, on another turn", bodies2[0]["tools"] == bodies[0]["tools"])
    enabled = {"calculator", "notes_search", "send_email"}
    _o, bodies, _g = turn([answer()], enabled=enabled)
    check("only ENABLED core tools; more_tools only offers enabled groups",
          names(bodies[0]) == ["calculator", "notes_search", AG.MORE_TOOLS],
          repr(names(bodies[0])))
    enum = bodies[0]["tools"][-1]["function"]["parameters"]["properties"]["group"]["enum"]
    check("its groups are only the ones with an enabled tool", enum == ["send_email"],
          repr(enum))
    _o, bodies, _g = turn([answer()], enabled={"calculator", "memory_search"})
    check("nothing to open: no more_tools", names(bodies[0]) == ["calculator", "memory_search"])


def t_opening_a_group_adds_it_for_the_rest_of_that_chat_only():
    RECORDED.clear()
    AG._OPENED.clear()
    out, bodies, gate = turn([said(("more_tools", {"group": "timers"})),
                              said(("set_timer", {"minutes": 5})), answer()],
                             cid="conv-open")
    check("the next round shows the group's tools",
          all(n in names(bodies[1]) for n in ("set_timer", "todo_add", "todo_done",
                                              "coming_up")), repr(names(bodies[1])))
    reply = next(m for m in bodies[1]["messages"] if m.get("role") == "tool")
    body = json.loads(reply["content"])
    check("the model is told which tools are ready", "set_timer" in body.get("note", ""),
          repr(body))
    check("more_tools's answer is Jarvis's own, not outside text",
          AG.OUTSIDE_FIELD not in body)
    check("more_tools is not a step: only the timer is in the chain",
          [s["tool"] for s in (RECORDED[-1] if RECORDED else [])] == ["set_timer"],
          repr(RECORDED[-1:]))
    check("and it did not mark the turn as having read anything",
          out["tools_ran"] == ["set_timer"], repr(out["tools_ran"]))
    check("nobody was asked to open it", gate.asked == [])
    check("the groups order is fixed, not the order of opening",
          names(bodies[1]).index("set_timer") > names(bodies[1]).index("set_reminder"))
    _o, later, _g = turn([answer()], cid="conv-open")
    check("a later turn of the same chat still has it", "set_timer" in names(later[0]))
    _o, other, _g = turn([answer()], cid="conv-fresh")
    check("another chat does not", "set_timer" not in names(other[0]))
    check("more_tools's own text did not change when a group opened",
          later[0]["tools"][-1] == other[0]["tools"][-1])


def t_a_switched_off_tool_is_never_offered():
    enabled = set(AG.TOOLS) - {"browser_control", "send_email"}
    _o, bodies, _g = turn([said(("more_tools", {"group": "send_email"})), answer()],
                          enabled=enabled, cid="conv-off")
    reply = json.loads(next(m for m in bodies[1]["messages"] if m.get("role") == "tool")
                       ["content"])
    check("asking for a group of switched-off tools is refused",
          reply.get("ok") is False and "No such group" in reply.get("error", ""), repr(reply))
    check("and send_email is not offered", "send_email" not in names(bodies[1]))
    _o, bodies, _g = turn([said(("more_tools", {"group": "control"})), answer()],
                          cid="conv-browser")
    check("browser_control, not enabled here, never comes with its group",
          "browser_control" not in names(bodies[1]) and "control_phone" in names(bodies[1]),
          repr(names(bodies[1])))


def t_a_hidden_but_allowed_tool_still_works():
    real = AG.TOOLS["file_read"].execute
    ran = []
    AG.TOOLS["file_read"].execute = lambda args, state, **k: ran.append(args) or {
        "ok": True, "content": "hello"}
    try:
        _o, bodies, gate = turn([said(("file_read", {"path": "C:/notes/a.txt"})), answer()],
                                cid="conv-hidden")
    finally:
        AG.TOOLS["file_read"].execute = real
    check("a call to an allowed tool that is not shown goes to the gate as before",
          [a for a, _t in gate.asked] and ran == [{"path": "C:/notes/a.txt"}],
          repr((gate.asked, ran)))


def t_a_group_opened_after_outside_text_is_named_on_the_card():
    real = {n: AG.TOOLS[n].execute for n in ("calculator", "file_read")}
    AG.TOOLS["calculator"].execute = lambda a, s, **k: {"ok": True, "value": 2}
    AG.TOOLS["file_read"].execute = lambda a, s, **k: {"ok": True, "content": "x"}
    try:
        # notes_search reads outside text; its result is made up here.
        realn = AG.TOOLS["notes_search"].execute
        AG.TOOLS["notes_search"].execute = lambda a, s, **k: {"ok": True, "results": []}
        _o, bodies, gate = turn([said(("notes_search", {"query": "path"})),
                                 said(("more_tools", {"group": "files"})),
                                 said(("file_read", {"path": "C:/x.txt"})), answer()],
                                cid="conv-outside")
        AG.TOOLS["notes_search"].execute = realn
    finally:
        for n, f in real.items():
            AG.TOOLS[n].execute = f
    card = next((t for a, t in gate.asked if "x.txt" in t), "")
    check("the card for the tool it opened says so",
          AG.MORE_TOOLS_AFTER_OUTSIDE.format(groups="files") in card, card)


def t_a_model_without_tools_gets_no_more_tools():
    _o, bodies, _g = turn([answer()], can_use_tools=False)
    check("no tools and no more_tools", not bodies[0].get("tools"))


def t_bad_group_names_are_told_not_guessed():
    _o, bodies, _g = turn([said(("more_tools", {"group": "everything"})), answer()],
                          cid="conv-bad")
    reply = json.loads(next(m for m in bodies[1]["messages"] if m.get("role") == "tool")
                       ["content"])
    check("an unknown group is refused, listing the real ones",
          reply.get("ok") is False and "timers" in reply.get("error", ""), repr(reply))


def t_the_opened_memory_is_bounded():
    AG._OPENED.clear()
    for i in range(AG._OPENED_MAX + 25):
        AG._remember_opened(f"c{i}", {"timers"})
    check("at most _OPENED_MAX conversations are remembered",
          len(AG._OPENED) == AG._OPENED_MAX)
    check("the oldest go first", "c0" not in AG._OPENED and f"c{AG._OPENED_MAX + 24}"
          in AG._OPENED)
    check("an id that is not an id is never remembered",
          AG.opened_groups("../../x y") == frozenset())


def t_what_it_saves():
    every = [n for n in AG.TOOLS if n != "browser_control"]
    full = AG.tool_text_tokens(every)
    shown = AG.tool_offer(every, (), short=True)
    short = AG.estimate_tokens(AG._schemas_for(
        shown, AG.more_tools_groups(every, short=True), {}))
    print(f"      (info) every tool but browser_control: {full} tokens; short list: {short} "
          f"(saves {full - short}, {round(100 * (full - short) / full)}%)")
    check("the short list is well under half of the full one", short * 2 < full)
    check("the short list stays small (pinned: at most 1,450 tokens)", short <= 1450,
          str(short))
    check("more_tools itself stays small (at most 300 tokens)",
          AG.estimate_tokens(AG.more_tools_schema(AG.more_tools_groups(every, short=True)))
          <= 300)


if __name__ == "__main__":
    for fn in (t_every_tool_is_in_the_core_or_exactly_one_group,
               t_it_is_off_until_the_owner_turns_it_on,
               t_off_the_model_is_sent_what_it_was_sent_before,
               t_on_the_core_in_a_fixed_order_and_more_tools,
               t_opening_a_group_adds_it_for_the_rest_of_that_chat_only,
               t_a_switched_off_tool_is_never_offered,
               t_a_hidden_but_allowed_tool_still_works,
               t_a_group_opened_after_outside_text_is_named_on_the_card,
               t_a_model_without_tools_gets_no_more_tools,
               t_bad_group_names_are_told_not_guessed,
               t_the_opened_memory_is_bounded,
               t_what_it_saves):
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
