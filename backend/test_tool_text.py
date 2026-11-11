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
#: RAISED 2600 -> 2700 on 2026-10-25, and this is the decision the note above
#: asks for. `memory_search` gained a "Use when / Do NOT use when" pair (D7,
#: architect ruling Q9, the live campaign of 2026-10-25): the tool was never
#: called once in that campaign's 24 model-tools turns, and two of its failures
#: (a calculation "worked out" from nowhere, and a question about the owner's
#: dog answered from a web search that found nothing) are what that cost. The
#: pair took `memory_search` from 127 to 195 tokens and the sixteen from 2597
#: to 2665, so the old number had 3 tokens of room - not enough to add a cue
#: at all. 2700 leaves 35 tokens spare rather than the 3 the old one had.
#: Nothing else in this list grew; if anything does, this number is the thing
#: to look at first.
#: RAISED 2700 -> 2970 on 2026-11-01, by the same rule, for one tool. The owner
#: asked to open an allowed app on their phone and start a media search from
#: Live ("hey jarvis open yourube music and play the weekend"). `control_phone`
#: gained three actions (`list_apps`, `open_app`, `play`), a description that
#: says what they do and that an app off the owner's list is refused, and two
#: parameter names with their one-line meanings. Held to the same estimate_tokens
#: rule on this tree: `control_phone` 265 -> 506 and the sixteen 2665 -> 2906,
#: so 2700 had no room at all (it was already 35 under). 2970 leaves 64 tokens
#: spare. The tool sits in the "control" group and is only sent when that group
#: is opened, never on every turn - see test_short_tool_list.py, whose own
#: 1550/380 pins are unchanged by this and still pass.
MEASURED_BUDGET = 2970
PER_TOOL = 300
#: Tools whose description deliberately carries the GitHub whole-surface sentence
#: (2026-11-10). Named once, so a fourth one has to be looked at here too.
WHOLE_SURFACE_TOOLS = {"github_pr_scan", "github_merge_pr", "github_fix_and_push"}
#: browser_control drives a page with seven kinds of step; its parameters
#: alone are most of this.
#: control_phone is here for the same reason as of 2026-11-01: three app
#: actions, a description that has to tell the model what they do (and that
#: an app off the owner's list is refused), and the words for `app`/`query`.
#: Measured at 506 with this module's own rule; its old 265 was the whole of
#: PER_TOOL's room, so there was no way to add the actions inside 300.
#: rea_investigate joins them on 2026-11-04, and this is the decision the note
#: above asks for. The owner chose "install the full REA toolbox ... expose all
#: of its actions through one Jarvis tool", and REA serves 207; the schema's
#: `action` enum names 200 of them, which MEASURED here is 1,799 of the 1,953
#: tokens (the description is 154). There is no smaller shape that still lets
#: the model choose an action by name, and the tool costs nothing on any turn
#: until the owner turns REA on ([rea] enabled AND [tools].enabled both say
#: yes). 2000 leaves 47 tokens of room.
PER_TOOL_EXCEPT = {"browser_control": 600, "control_phone": 540,
                   "rea_investigate": 2000,
                   # The three GitHub tools of the owner's 2026-11-10 "Everything
                   # at once" decision (github_pr_scan, the carded merge and the
                   # carded fix-and-push). Each carries the ONE whole-surface
                   # sentence, `GITHUB_CAPABILITIES_WORDS` ==
                   # `jarvis_github.capabilities_line()` - the same words the
                   # spoken answer gives - because
                   # `backend/test_github_parity.py` pins that the model reads it.
                   # Measured on this tree with this module's own 3-chars-a-token
                   # rule on 2026-11-10 (the 22:30/23:00 ruling): 1308 and 1437
                   # for the two that carry the whole-surface sentence, and 474
                   # for github_fix_and_push. The first pin here was 850; the
                   # polish pass and then the 17-tool inventory grew the sentence,
                   # and this is the decision the note above asks for:
                   #   (a) `NEVER_WORDS` grew to cover five permanently banned verbs
                   #       the owner's Q3/Q4 rulings added (approve a PR, close an
                   #       issue, edit a comment, dispatch a workflow, gists), and
                   #       that sentence rides on all three descriptions;
                   #   (b) github_pr_scan must now say it prints each pull request's
                   #       40-hex head commit, and github_merge_pr's `head_sha` must
                   #       say that number comes from github_pr_scan - without which
                   #       the merge tool's one required argument is unreachable.
                   #   (c) 2026-11-10 desk fix: the merge card must name the pull
                   #       request's title and its target branch, so the tool takes
                   #       them as two more required arguments (`title`, `base_ref`)
                   #       and its description says a retarget refuses the merge.
                   #       Measured 1,063 by this module's own rule; 1,080 leaves
                   #       17 tokens of headroom, the same shape as `my_files`.
                   # github_pr_scan and github_fix_and_push stay at 960 (measured
                   # 905 and 902). The cost is paid ONLY when the `github` group is
                   # opened, never on every turn (they are group members, not core
                   # tools), and it buys one inventory with one home instead of a
                   # second copy that drifts.
                   "github_pr_scan": 1340, "github_merge_pr": 1480,
                   "github_fix_and_push": 480,
                   # The 2026-11-10 22:30 ruling's actions carry no whole-surface
                   # sentence, but three are a little over the 300 default legitimately:
                   # open_pr names stage/base/branch/body semantics (433), edit_pr
                   # shows the old/new title/body pin (345) and issue_state pins the
                   # title and the close/reopen direction (359). Measured on this
                   # tree; each is its own action with its own one-shot card.
                   "github_open_pr": 440, "github_edit_pr": 355,
                   "github_issue_state": 370,
                   # my_files (2026-11-05, the read-only repository map): a
                   # sixth action, `map`, joined a tool that already carried six
                   # format names and two "use that" lines. Measured 329 with
                   # this module's own rule - the sentence that says what map
                   # does, one enum member and two parameter notes are the ~29
                   # tokens. No smaller shape stays honest: the enum is how the
                   # model picks an action, and cutting the format list
                   # (PDF/Word/Excel/PowerPoint/Markdown/text/CSV) or "stored
                   # spoken and on-screen recording words" would hide what the
                   # tool can actually read. Like control_phone it is a shipped
                   # default, so this cost is paid on a turn only while the
                   # owner leaves it in `[tools].enabled`. 340 keeps 11 tokens
                   # of headroom, the same shape as the exceptions above.
                   "my_files": 340,
                   # set_reminder (2026-11-09, wave 13): the parameter text now
                   # carries the rule that fixed the owner's live bug - the
                   # whole sentence became the reminder's title - so it says the
                   # ACTION only, gives one example and names the two shapes not
                   # to copy. Measured 309 with this module's own rule, against
                   # 268 on origin/main (d6df4022). A trim of the second example
                   # would fit 300; the wording is the live fix and is kept
                   # whole, so this is a deliberate decision with 11 tokens of
                   # headroom, the same shape as my_files above.
                   # test_short_tool_list.py's own pin moved with it (1,615 ->
                   # 1,656, its whole growth).
                   "set_reminder": 320,
                   # project_read (2026-11-09, P1a - the read half of "Jarvis
                   # takes over dev work"): measured 368 with this module's own
                   # rule. The description carries the four boundary sentences
                   # that keep the answer honest - the listed folder (or a
                   # project) only, read-only, a PDF/Word/Excel/PowerPoint file
                   # belongs to my_files, and a file outside the listed folders
                   # to file_read. Those last two are "use that" lines for the
                   # three reading tools the model confuses, so a trim to 300
                   # would hide exactly what C1 and the confusion pairs check.
                   # 380 leaves 12 tokens of headroom, the same shape as
                   # my_files above.
                   "project_read": 380}

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
            if name in WHOLE_SURFACE_TOOLS:
                # The three GitHub tools of 2026-11-10 carry the ONE whole-surface
                # sentence deliberately (see PER_TOOL_EXCEPT): it names every
                # GitHub tool because it is an inventory, not a "call that one"
                # hint, and it is the same sentence the owner hears. So this rule
                # - a hint may not name a tool the turn does not have - is not
                # the question it asks; the line is checked word for word against
                # `jarvis_github.capabilities_line()` in test_github_parity.py.
                continue
            alone = tool.schema([name])["function"]["description"]
            check(f"{name} alone does not mention {other}", other not in alone, alone)
    check("with nothing said about the turn (the tool test), every line is in",
          "notes_search" in AG.TOOLS["memory_search"].schema()["function"]["description"])


def t_both_tools_the_model_never_picked_carry_the_two_cues():
    """D7, the architect's Q9 ruling: `memory_search` and `feature_guide` were
    never selected in the live campaign's 24 model-tools turns, so each carries
    a "Use when / Do NOT use when" pair in those words.

    `change_setting` deliberately keeps main's 2026-10-13 field-test wording,
    byte for byte: eight description checks in test_settings_tool.py pin it,
    and D5's reachability is carried by the quick lane's settings pre-router
    and the claim corrections, not by rewriting a pinned description."""
    for name in ("memory_search", "feature_guide"):
        text = AG.TOOLS[name].description
        check(f"{name} says 'Use when'", "Use when" in text, text[:160])
        check(f"{name} says 'Do NOT use'", "Do NOT use" in text, text[:160])

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
               t_both_tools_the_model_never_picked_carry_the_two_cues,
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
