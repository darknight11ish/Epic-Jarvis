"""test_tool_diet_named_action.py - the tool diet must never hide a tool the
question NAMES the thing for.

THE MEASURED FAILURE (2026-11-18 17:57Z, the owner's live /api/chat). Eight
real questions about his own GitHub repository were asked. "What is the latest
commit on main in Epic-Jarvis?" was shown only `web_search` ("latest") and
`feature_guide` (a settings tool, matched by accident) - EVERY GitHub tool was
dieted away, so the model could not have called one, and it answered "I don't
have direct access to your GitHub repositories". A false denial of an ability
this backend has. The same shape hid the tool on any question that named a
thing in the owner's words instead of the tool's own hint words.

**The #1382 lane merged before this branch** and patched the two hint words it
needed (`commit` on `github_ci_status`, `defect`/`register` on `check_records`),
so on today's `main` the exact commit question is shown a GitHub tool again.
That does not make this suite vacuous: nothing in the hint table knows the
owner's repository by NAME, "branches" does not match any tool's hints (so the
branch question still got a 29-tool full-list fallback), and `feature_guide`
was still matched by accident. Against that merged `main` this suite fails 8
checks; with the floor it passes. The safety rule is what keeps the NEXT
owner-worded question from being hidden, not the two words #1382 added.

WHAT THIS SUITE PROVES, driving the REAL `_new_offer`/`_fill_offer` - the
exact path a local turn uses - and `tool_diet_selection`, with no model, no
network, no GPU and no live config:

  1. the hints cannot see the owner's repository by name: no tool's hint words
     match "Epic-Jarvis", and the repository read is not a hint match for the
     exact sentence - the named-thing floor is what names the read he wanted;
  2. the owner's exact question now shows the GitHub commit read and at least
     one GitHub tool, in a list of at most TOOL_DIET_LIMIT (before the fix the
     live turn was shown two tools, neither GitHub);
  3. a question naming a repository, a pull request, a commit, a branch or a
     defect is NEVER dieted away from its read tool - on the owner's live tool
     set AND on the whole built-in catalogue;
  4. the eight-question battery shows the tool each question needs;
  5. ordinary questions (weather, timer, notes, arithmetic) are still dieted,
     and an unrecognised question still falls back to the whole list;
  6. the floor cannot show a tool the owner switched off, and it adds only
     card-free reads: every GitHub WRITE still raises its own card;
  7. hiding is not refusing: a tool the diet did not show is still in the
     allowed list, and `check_call` passes it on to prepare() and the gate,
     while a tool the owner switched off is refused before the gate.

The tool set is the owner's own live `[tools].enabled` list, captured from the
`jarvis-framework.toml` beside his installed backend on 2026-11-18 and reduced
to the tools this repository ships. It is a FIXTURE, not a live read, so the
suite reproduces the live turn deterministically on any machine.

    python3 test_tool_diet_named_action.py
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

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


#: The owner's live `[tools].enabled`, captured 2026-11-18 from the
#: `jarvis-framework.toml` beside his installed backend, reduced to the tools
#: this repository ships (29 names). The same fixture the wave-21 GitHub lane
#: used for its own live-battery test.
LIVE_ENABLED = (
    "calculator", "change_setting", "memory_search", "web_search",
    "feature_guide", "my_files", "calendar_read", "email_check", "home_read",
    "notes_search", "self_portrait", "conversation_find", "conversation_open",
    "refresh_abilities", "github_list", "github_read_file", "github_ci_status",
    "github_pr_scan", "github_comment", "github_open_issue",
    "github_rerun_workflow", "github_create_repo", "github_merge_pr",
    "github_fix_and_push", "github_search", "github_pr_detail",
    "github_open_pr", "review_changes", "check_records",
)

#: The eight questions of the 17:57Z live battery, verbatim, with the tool
#: each one needs (the other lane makes the answer itself work; this suite is
#: only about the tool being OFFERED at all).
BATTERY = (
    ("What are my open pull requests on Epic-Jarvis?", "github_list"),
    ("Which pull requests are ready to merge?", "github_pr_scan"),
    ("What is failing on pull request 1376?", "github_pr_detail"),
    ("What checks are still running on PR 1378?", "github_ci_status"),
    ("What is the latest commit on main in Epic-Jarvis?", "github_ci_status"),
    ("Which branches have unmerged work?", "github_pr_scan"),
    ("How do I merge a pull request on GitHub?", "github_merge_pr"),
    ("How many open defects are in the register?", "check_records"),
)

#: The one measured question that was answered with a false denial.
FALSE_DENIAL_QUESTION = "What is the latest commit on main in Epic-Jarvis?"

LIVE = [n for n in AG.TOOLS if n in set(LIVE_ENABLED)]
GITHUB_WRITES = frozenset(n for n in LIVE
                          if n.startswith("github_") and n in AG.NEEDS_A_PERSON)


def turn_tools(question, allowed=None):
    """What a real local turn is shown for this question.

    The SAME `_new_offer`/`_fill_offer` pair ``run_local_turn`` fills, so this
    is the list that would go in the request's `tools` array - not a second
    re-implementation of the diet. `MORE_TOOLS` is left out of the returned
    names (it is a door to more tools, not a tool) but kept in the offer.
    """
    names = list(LIVE if allowed is None else allowed)
    offer = AG._new_offer(names)
    AG._fill_offer(offer, names, question=question)
    return [n for n in offer["shown"] if n != AG.MORE_TOOLS], offer


def diet(question, allowed=None):
    return AG.tool_diet_selection(question, list(LIVE if allowed is None else allowed))


# --------------------------------------------------------------------------
#   0. the pieces this suite reads are the real ones
# --------------------------------------------------------------------------

def t_the_suite_reads_the_real_selector_and_the_live_tool_set():
    check("the fixture is the owner's live enabled list (29 tools)",
          len(LIVE) == 29 and "github_ci_status" in LIVE, LIVE)
    check("the diet ships ON, so what it shows is what the model is given",
          AG.tool_diet_on() is True)
    check("the eight battery questions are the eight the owner's live run asked",
          len(BATTERY) == 8)
    check("the GitHub writes the live PC enables still need a person, before any fix",
          len(GITHUB_WRITES) == 7, sorted(GITHUB_WRITES))


# --------------------------------------------------------------------------
#   1. the measured cause: the hints cannot see the owner's repository NAME
# --------------------------------------------------------------------------

def t_the_owners_repository_name_is_not_a_tool_hint_and_the_floor_is_what_adds_it():
    """"What is the latest commit on main in Epic-Jarvis?" - the hints that
    decide the diet score a tool by ITS OWN words, and every GitHub tool's
    hints open with `github`. The owner says "Epic-Jarvis", not "GitHub".

    The 17:57Z live turn was shown only `web_search` and `feature_guide`. The
    #1382 lane then gave `github_ci_status` the word "commit" (merged before
    this branch), so on today's `main` the hints DO reach that one tool for
    this exact sentence - but NOTHING in the hint table knows the owner's
    repository by name, and the other named things the battery asks about (a
    branch, a defect register) still fell into the full-list fallback. The
    checks below are therefore about what the FLOOR adds, not about the hint
    table being empty: the repository's name matches no hint, and the
    repository read is not a hint match for the sentence.
    """
    question = FALSE_DENIAL_QUESTION
    repo_words = "epic-jarvis"
    name_hits = [n for n in LIVE
                 if any(rx.search(repo_words) for rx in AG._TOOL_HINTS_RX.get(n, ()))]
    check("no tool's hints match the owner's repository by its NAME", not name_hits, name_hits)
    hint_hits = [n for n in LIVE
                 if any(rx.search(question) for rx in AG._TOOL_HINTS_RX.get(n, ()))]
    check("the hints alone do not reach the owner's repository read (github_list)",
          "github_list" not in hint_hits, hint_hits)
    floor = AG.named_action_floor(question, LIVE)
    check("the named-thing floor names the commit read the question is about",
          "github_ci_status" in floor, floor)
    check("...and the owner's repository read, from his repository's own name",
          "github_list" in floor, floor)


# --------------------------------------------------------------------------
#   2. the owner's exact question, before and after
# --------------------------------------------------------------------------

def t_the_owners_exact_question_now_shows_the_github_tools():
    """THE REPRODUCTION. Before the fix this question's shown list was
    ``['web_search', 'feature_guide']`` - 2 tools, neither GitHub - and the
    live turn answered with a false denial. After the fix the model is given
    the commit read itself.

    The "before" list is asserted from the production hint table in the test
    above; this one asserts what the model is given now, through the real
    turn builder.
    """
    question = FALSE_DENIAL_QUESTION
    shown, offer = turn_tools(question)
    selection = diet(question)
    github = [n for n in shown if n.startswith("github_")]
    check("the live question is DIETED, not a whole-list fallback",
          not selection["fallback"], selection)
    check("the commit read (github_ci_status) is shown", "github_ci_status" in shown, shown)
    check("at least one GitHub tool is shown", bool(github), shown)
    check("the shown list is small - the diet still trims",
          len(shown) <= AG.TOOL_DIET_LIMIT, shown)
    check("the tool list the request would carry has the same names, in the same order",
          [t["function"]["name"] for t in offer["schemas"]]
          == [n for n in offer["shown"]], offer["schemas"])
    check("...and the accidental settings-tool match is gone",
          "feature_guide" not in shown, shown)
    check("the same words show the same list every time (prompt reuse depends on it)",
          turn_tools(question)[0] == shown
          and diet(question)["tools"] == diet(question)["tools"], shown)


# --------------------------------------------------------------------------
#   3. THE DECIDING TEST: a named thing keeps its tool
# --------------------------------------------------------------------------

#: One question per thing the owner names, and the read tool that answers it.
NAMED_THINGS = (
    ("Which repository holds the owner's project?", "github_list"),
    ("What is failing on pull request 1376?", "github_pr_detail"),
    ("What is the latest commit on main in Epic-Jarvis?", "github_ci_status"),
    ("Which branches have unmerged work?", "github_pr_scan"),
    ("How many open defects are in the register?", "check_records"),
)


def t_a_question_that_names_a_thing_is_never_dieted_away_from_its_read_tool():
    """A question naming a repository, a pull request, a defect, a commit or
    a branch must be offered the corresponding tool - on the owner's live tool
    set and on the whole built-in catalogue (another machine may enable more).
    """
    for label, allowed in (("the owner's live tool set", LIVE),
                           ("every built-in tool", list(AG.TOOLS))):
        for question, needed in NAMED_THINGS:
            shown, _offer = turn_tools(question, allowed)
            selection = diet(question, allowed)
            check(f"{label}: {question!r} shows {needed}", needed in shown, shown)
            check(f"{label}: ...and is dieted, not a fallback",
                  not selection["fallback"] and len(shown) < len(allowed),
                  (selection, shown))


# --------------------------------------------------------------------------
#   4. the whole live battery
# --------------------------------------------------------------------------

def t_the_eight_battery_questions_show_the_tool_they_need():
    for question, needed in BATTERY:
        shown, _offer = turn_tools(question)
        check(f"{question!r}: the tool it needs is shown ({needed})",
              needed in shown, shown)
        if needed.startswith("github_"):
            check(f"{question!r}: at least one GitHub tool is shown",
                  any(n.startswith("github_") for n in shown), shown)
        check(f"{question!r}: the list is a diet, not a full-list fallback",
              not diet(question)["fallback"], shown)


# --------------------------------------------------------------------------
#   5. the diet's benefit is kept: ordinary questions still trim
# --------------------------------------------------------------------------

#: Ordinary questions (weather, timer, notes, arithmetic) and the tool each
#: needs from the whole catalogue. The diet must still find the tool and must
#: still be far smaller than the catalogue.
ORDINARY = (
    ("what is the weather like tomorrow?", "web_search"),
    ("set a timer for 10 minutes", "set_timer"),
    ("what did I note about the dentist?", "notes_search"),
    ("what is 20% of 420?", "calculator"),
)


def t_ordinary_questions_are_still_dieted():
    catalogue = list(AG.TOOLS)
    for question, needed in ORDINARY:
        shown, _offer = turn_tools(question, catalogue)
        check(f"{question!r}: it still shows the tool it needs ({needed})",
              needed in shown, shown)
        check(f"{question!r}: trimmed far below the {len(catalogue)}-tool catalogue",
              len(shown) <= AG.TOOL_DIET_LIMIT, shown)
    # The unknown-question fallback is UNTOUCHED: an ordinary question that
    # names none of the owner's things and matches no hint still shows every
    # allowed tool, the safe side.
    selection = AG.tool_diet_selection("tell me a joke", catalogue)
    check("an unrecognised ordinary question still falls back to the whole list",
          selection["fallback"] and selection["tools"] == catalogue, selection)
    # On the live set, a timer question falls back because set_timer is not
    # enabled there: the diet can never offer a tool the owner switched off.
    live = AG.tool_diet_selection("set a timer for 10 minutes", LIVE)
    check("a question for a switched-off tool falls back rather than inventing it",
          live["fallback"] and live["tools"] == LIVE, live)


# --------------------------------------------------------------------------
#   6. the floor cannot show what is switched off, and adds no write tool
# --------------------------------------------------------------------------

def t_the_floor_is_bounded_by_the_allowed_list_and_adds_only_reads():
    question = FALSE_DENIAL_QUESTION
    allowed = ["calculator", "web_search"]
    shown, _offer = turn_tools(question, allowed)
    check("only tools in the allowed list are ever shown",
          set(shown) <= set(allowed), shown)
    check("with GitHub switched off, no GitHub tool can appear",
          not any(n.startswith("github_") for n in shown), shown)
    check("the floor itself is bounded by the allowed list",
          AG.named_action_floor(question, allowed) == [],
          AG.named_action_floor(question, allowed))
    for battery_question, _needed in BATTERY:
        floor = AG.named_action_floor(battery_question, list(AG.TOOLS))
        check(f"the floor adds only card-free reads: {battery_question!r}",
              not (set(floor) & set(AG.NEEDS_A_PERSON)), floor)
    check("every GitHub WRITE the live PC enables still raises its own card",
          GITHUB_WRITES == {
              "github_comment", "github_open_issue", "github_rerun_workflow",
              "github_create_repo", "github_merge_pr", "github_fix_and_push",
              "github_open_pr"}, sorted(GITHUB_WRITES))


# --------------------------------------------------------------------------
#   7. offered is not run: hiding is not refusing, and the gate still decides
# --------------------------------------------------------------------------

def t_a_hidden_tool_is_still_allowed_and_goes_to_the_gate():
    """The diet only decides what is SHOWN. `check_call` reads `names`, the
    allowed list, so a hidden tool can still be called and is put to the gate
    exactly like a shown one - and a tool the owner switched off is refused
    before the gate, whatever the diet would have shown.
    """
    question = FALSE_DENIAL_QUESTION
    shown, _offer = turn_tools(question)
    hidden = "github_read_file"
    check("the diet hides a read tool the owner has switched on",
          hidden in LIVE and hidden not in shown, shown)
    args, problem = AG.check_call(
        hidden, json.dumps({"repo": "darknight11ish/Epic-Jarvis",
                            "path": "README.md"}), list(LIVE))
    check("a hidden tool still passes check_call, on its way to prepare() and the gate",
          problem is None and isinstance(args, dict), problem)
    args2, problem2 = AG.check_call(
        hidden, json.dumps({"repo": "darknight11ish/Epic-Jarvis",
                            "path": "README.md"}), ["calculator"])
    check("...while a switched-off tool is refused before the gate",
          args2 is None and "no such tool" in (problem2 or ""), problem2)


if __name__ == "__main__":
    for fn in (t_the_suite_reads_the_real_selector_and_the_live_tool_set,
               t_the_owners_repository_name_is_not_a_tool_hint_and_the_floor_is_what_adds_it,
               t_the_owners_exact_question_now_shows_the_github_tools,
               t_a_question_that_names_a_thing_is_never_dieted_away_from_its_read_tool,
               t_the_eight_battery_questions_show_the_tool_they_need,
               t_ordinary_questions_are_still_dieted,
               t_the_floor_is_bounded_by_the_allowed_list_and_adds_only_reads,
               t_a_hidden_tool_is_still_allowed_and_goes_to_the_gate):
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
