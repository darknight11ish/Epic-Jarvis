"""The tool descriptions the 8B model reads: short, and kept short.

Every enabled tool's description is sent to the model on every round, and
on the 8 GB card the model's whole working memory is about 8,000 tokens of
real room (docs/MODEL-TOPOLOGY.md). The research (docs/RESEARCH-2026-09-24.md
§6, recommendation 5) measured the sixteen tools at about 3,000 tokens -
browser_control alone about 850 - and recommended trimming them, plus one
"use this, not that" line for each pair the model confuses, before building
anything that hides tools. This suite pins the result so it cannot quietly
grow back, and checks a "use that" line never points at a tool the turn
does not have.

Measured with jarvis_agent.estimate_tokens (3 characters a token, on the
pessimistic side), the same count the chat loop budgets with:
    before 3,006 tokens for the sixteen tools (browser_control 850)
    after  2,524 (browser_control 545), the "use that" lines included

    python3 test_tool_text.py
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
from test_agent import NoRealIO, scripted_stream  # noqa: E402

FAILED, PASSED = [], []

#: The sixteen tools the trim was measured on, and their budget. A tool added
#: later is held to PER_TOOL instead, so a new tool does not have to squeeze
#: these; raising a number here is a decision - write down why beside it.
MEASURED = ("calculator", "memory_search", "file_read", "shell_exec", "control_computer",
            "control_phone", "browser_control", "github_search", "calendar_read",
            "email_check", "notes_search", "home_read", "home_control",
            "append_logseq_journal", "append_obsidian_daily", "create_joplin_note")
MEASURED_BUDGET = 2600
PER_TOOL = 300
#: browser_control drives a page with seven kinds of step; its parameters
#: alone are most of this.
PER_TOOL_EXCEPT = {"browser_control": 600}

#: The pairs the research found the model mixes up, each told apart both ways.
CONFUSABLE = (("memory_search", "notes_search"), ("home_read", "home_control"),
              ("calendar_read", "email_check"), ("append_obsidian_daily", "create_joplin_note"),
              # web_search (2026-09-25): three searches the model could reach for
              # instead - the owner's facts, the owner's notes, GitHub's libraries.
              ("web_search", "memory_search"), ("web_search", "notes_search"),
              ("web_search", "github_search"))


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def tokens(name, offered=None) -> int:
    return AG.estimate_tokens(AG.TOOLS[name].schema(offered))


def t_the_measured_tools_stay_inside_their_budget():
    present = [n for n in MEASURED if n in AG.TOOLS]
    check("every measured tool is still there", present == list(MEASURED),
          repr(set(MEASURED) - set(present)))
    total = sum(tokens(n) for n in present)
    print(f"      (info) the sixteen tools: {total} tokens; every tool: "
          f"{sum(tokens(n) for n in AG.TOOLS)} tokens")
    check(f"the sixteen tools are at most {MEASURED_BUDGET} tokens, with every "
          f"'use that' line in ({total})", total <= MEASURED_BUDGET)
    check("browser_control is well under its old ~850 tokens",
          tokens("browser_control") <= PER_TOOL_EXCEPT["browser_control"],
          str(tokens("browser_control")))


def t_no_tool_is_long():
    for name in AG.TOOLS:
        limit = PER_TOOL_EXCEPT.get(name, PER_TOOL)
        check(f"{name}: at most {limit} tokens ({tokens(name)})", tokens(name) <= limit)


def t_each_confusable_pair_is_told_apart_both_ways():
    for a, b in CONFUSABLE:
        both = [a, b]
        check(f"{a} says when to use {b}",
              b in AG.TOOLS[a].schema(both)["function"]["description"])
        check(f"{b} says when to use {a}",
              a in AG.TOOLS[b].schema(both)["function"]["description"])


def t_a_use_that_line_only_names_a_tool_the_turn_has():
    for name, tool in AG.TOOLS.items():
        for other in tool.instead:
            check(f"{name}'s 'use that' line names a real tool ({other})", other in AG.TOOLS)
            alone = tool.schema([name])["function"]["description"]
            check(f"{name} alone does not mention {other}", other not in alone, alone)
    check("with nothing said about the turn (the tool test), every line is in",
          "notes_search" in AG.TOOLS["memory_search"].schema()["function"]["description"])


def t_the_model_is_sent_only_lines_for_tools_it_has():
    for enabled, want in (({"calendar_read"}, False), ({"calendar_read", "email_check"}, True)):
        opener, bodies = scripted_stream([{"choices": [{"message": {
            "role": "assistant", "content": "ok"}}]}])
        with NoRealIO():
            AG.run_local_turn([{"role": "user", "content": "what is on"}], "qwen3:8b",
                              ollama_url="http://127.0.0.1:11434", stream_out=lambda b: None,
                              open_stream=opener, gate_check=lambda *a: None,
                              enabled_tools=enabled)
        sent = {t["function"]["name"]: t["function"]["description"] for t in bodies[0]["tools"]}
        check(f"offered {sorted(enabled)}: calendar_read "
              f"{'names' if want else 'does not name'} email_check",
              ("email_check" in sent.get("calendar_read", "")) == want, repr(sent))


def t_the_tool_test_still_reads_the_live_list():
    """tools/tool_eval reads jarvis_agent.TOOLS itself (its saved copy is only
    a fallback). It must still get the live, trimmed text."""
    sys.path.insert(0, str(HERE.parent / "tools" / "tool_eval"))
    try:
        import ollama_tool_eval as E
    except Exception as exc:
        check("tools/tool_eval imports", False, repr(exc))
        return
    live = {t["function"]["name"]: t["function"]["description"] for t in E.TOOLS}
    check("it reads every tool but browser_control",
          set(live) == set(AG.TOOLS) - {"browser_control"}, repr(sorted(live)))
    check("with today's text, not the saved copy's",
          live.get("memory_search") == AG.TOOLS["memory_search"].schema()["function"]["description"])
    saved = json.loads((HERE.parent / "tools" / "tool_eval" / "jarvis_tools.json")
                       .read_text(encoding="utf-8"))
    check("its saved fallback copy matches the live list",
          saved == [AG.TOOLS[n].schema() for n in AG.TOOLS if n != "browser_control"])


if __name__ == "__main__":
    for fn in (t_the_measured_tools_stay_inside_their_budget, t_no_tool_is_long,
               t_each_confusable_pair_is_told_apart_both_ways,
               t_a_use_that_line_only_names_a_tool_the_turn_has,
               t_the_model_is_sent_only_lines_for_tools_it_has,
               t_the_tool_test_still_reads_the_live_list):
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
