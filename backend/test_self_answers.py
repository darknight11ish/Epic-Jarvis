#!/usr/bin/env python3
"""test_self_answers.py - the self-questions docs/SELF-AWARENESS.md promises.

    python3 backend/test_self_answers.py

WHAT THIS PROVES (2026-11-04, the self-awareness audit's gap 4):

  - THE DOC'S PROMISED QUESTIONS REALLY ANSWER, without the model. The page
    says "What can you do?", "Where do I change how Jarvis talks?", "What is
    connected?", "What tools do you have?", "Which of your tools ask before
    they act?" and "refresh your abilities" already work. Three of those
    answered NOTHING (the sentence went to the local model, which has no state
    to answer it from) and the refresh phrase was not wired at all. Every
    quoted question in the page's "Asking about itself" section is driven
    through the real matcher here, so the doc cannot promise more than the
    code keeps again.
  - EACH ANSWER IS THE REAL SOURCE'S OWN NUMBERS, at answer time:
    jarvis_self_portrait.tool_inventory (jarvis_agent.TOOLS + the live
    [tools].enabled), jarvis_asks_first.view's own "Asks you first" rows,
    jarvis_reach.view's own ON rows and the plug-in folder, and the portrait's
    own refresh. No typed list, and no 136 the old counts() used to emit.
  - THE ANSWER FOLLOWS A REAL SETTINGS FILE. A one-tool [tools].enabled is
    written through JARVIS_FRAMEWORK_TOML, and "what tools do you have" must
    say ONE switched on - not a constant, and not the shipped 21.
  - THE FULL-LIST QUESTION GETS THE COMPLETE LIST (2026-11-25). "Can you list
    all of your tools?" used to reach the count answer, whose `cap=30` named 30
    switched-on tools and said "and 17 more" - the owner's complaint, with the
    live settings file naming 47. "list all/every ..." now reaches
    `tools_list_all`, and these checks prove the answer names EVERY registered
    tool exactly once, marks each on or off against a fixture with a known
    split, groups the lines under plain area headings, and never prints
    "and N more". The summary question keeps its summary, in the same suite.
  - ONE GROUP, THE GROUP LIST, AND THE OTHER SIDE OF THE SWITCH (2026-11-26).
    The owner measured "which github tools do you have", "what note tools are
    there", "show me the email tools", "what groups of tools do you have",
    "list your tools by category", "which tools are switched off" and "what
    tools can change my settings" all going to the model. Each now reaches its
    own read-only intent, and each case is checked BY INTENT and by the area it
    names - not by "an answer came back", because a neighbour swallowing a
    sentence is the failure this project has already paid for. The partition is
    proved to hold every registered tool exactly once, and the lanes that
    already work ("what github tools do you have", "what plugins do you have",
    "what does the calculator tool do", "switch on the email tool", "turn off
    web search") are pinned so they cannot move.
  - THE TOOL-SURFACE ANSWERS ARE READ-ONLY. "cancel that" must not be able to
    undo a question, and a question must not clear a pending card; every one of
    the nine tool-surface intent names is in jarvis_quick.READ_ONLY_INTENTS.
  - NEAR MISSES STILL GO TO THE MODEL. "what tools do I need for this job",
    "what is connected to my phone" and "refresh my browser" are not the
    owner asking about Jarvis's own inventory, and none may be hijacked.

No network, no model, no live install: the config folder is a throwaway temp
directory, and the memory/receipts databases are pointed there too.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import traceback
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-self-answers-"))
# Before anything imports jarvis_framework or jarvis_memory: their paths are
# read once, at import.
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["JARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["JARVIS_MEMORY_DB"] = str(_TMP / "config" / "memory.db")
os.environ["JARVIS_RECEIPTS_DB"] = str(_TMP / "config" / "receipts.db")
(_TMP / "config").mkdir(parents=True, exist_ok=True)

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_quick.py", "jarvis_self_portrait.py", "jarvis_asks_first.py",
                "jarvis_reach.py")
# The framework module the real backend ships beside these modules lives in
# `backend/rebuilt/` in a checkout; on the path, the live [tools].enabled read
# is the shipped `jarvis-framework.toml`, exactly as on an install.
sys.path.append(str(HERE / "rebuilt"))

import jarvis_agent as A  # noqa: E402
import jarvis_asks_first as ASK  # noqa: E402
import jarvis_feature_guide as FG  # noqa: E402
import jarvis_quick as Q  # noqa: E402
import jarvis_reach as REACH  # noqa: E402
import jarvis_self_portrait as SP  # noqa: E402
import jarvis_settings_registry as REG  # noqa: E402

PASSED, FAILED = [], []
DOC = (REPO / "docs" / "SELF-AWARENESS.md").read_text(encoding="utf-8")

#: The five intents this area owns, each read-only. `tools_list_all` is the
#: 2026-11-25 addition: "list all of your tools" is a different ANSWER from
#: "what tools do you have", not a different question about the machine.
SELF_INTENTS = ("tools_inventory", "tools_list_all", "tools_asking",
                "connected_list", "self_refresh")


class _Sched:
    def mark_command(self, text):
        pass


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def answer(words):
    return Q.answer(words, sched=_Sched())


# ---------------------------------------------------------------------------
#   1. The doc's own promises, driven
# ---------------------------------------------------------------------------


def the_docs_quoted_questions_all_answer():
    """EVERY QUOTED QUESTION IN THE PAGE'S "Asking about itself" SECTION.

    The page is the owner's map of what he can ask. It is read here, not
    restated, so a line added to it without a real answer fails this suite.
    """
    # The three self-knowledge sections the page promises (2026-11-04 phase 2
    # added the last two): every quoted question in each must answer.
    sections = (
        ("## Asking about itself", "## Its own machine, speed and memory"),
        ("## Its own machine, speed and memory", "## Two things at once"),
        ("## Two things at once", '## "Open <a place>"'),
    )
    promised = []
    for start_heading, end_heading in sections:
        start = DOC.index(start_heading)
        end = DOC.index(end_heading)
        promised += re.findall(r'"([^"\n]+\?)"', DOC[start:end])
    check("the page's section still quotes a set of questions", len(promised) >= 4,
          str(promised))
    for words in promised:
        got = Q.match(words)
        check(f"the page's promise {words!r} really answers without the model",
              got is not None, "went to the model")
    # The refresh sentence is not a question, so it is quoted separately.
    check("the page's 'refresh your abilities' line is in the document",
          '"refresh your abilities"' in DOC)
    got = Q.match("refresh your abilities")
    check("... and it is answered by the portrait refresh, not the model",
          got is not None and got.name == "self_refresh",
          got.name if got else "went to the model")
    # The three the audit drove to silence are the ones this change answers.
    for words, want in (("What is connected?", "connected_list"),
                        ("What tools do you have?", "tools_inventory"),
                        ("Which of your tools ask before they act?", "tools_asking")):
        got = Q.match(words)
        check(f"{words!r} is answered by {want}", got is not None and got.name == want,
              got.name if got else "went to the model")
    # The full-list promise (2026-11-25) is quoted as a question so the same
    # doc-driven check above covers it too; this one names the intent, because
    # the whole point is that it is NOT the count answer.
    check("the page promises the complete inventory as its own question",
          '"Can you list all of your tools?"' in DOC)
    got = Q.match("Can you list all of your tools?")
    check("... and that promise reaches the complete list, not the count",
          got is not None and got.name == "tools_list_all",
          got.name if got else "went to the model")


def near_misses_still_go_to_the_model():
    for words in ("what tools do I need for this job",
                  "what is connected to my phone",
                  "which tools ask for a password",
                  "refresh my browser",
                  "refresh the page",
                  "what tools does a carpenter need",
                  # "all" must not capture a request about something else.
                  "list all the tools for painting",
                  "name every setting"):
        got = Q.match(words)
        check(f"{words!r} is not hijacked", got is None or got.name not in SELF_INTENTS,
              got.name if got else None)


def all_self_answers_are_read_only():
    for name in SELF_INTENTS:
        check(f"{name} cannot be undone by 'cancel that'",
              name in Q.READ_ONLY_INTENTS)


# ---------------------------------------------------------------------------
#   2. "What tools do you have?" - the real counts, never 136
# ---------------------------------------------------------------------------


def tools_answer_is_the_registry_and_the_live_file():
    # 79, not the 51 this read on main: the six on-demand GitHub tools (2026-11-03,
    # GitHub "Read + actions") are in jarvis_agent.TOOLS and ship switched OFF,
    # hands-free then added send_text_message (on by default), the product check
    # added product_check (off), the four pack tools (2026-11-05) ship ON, and the
    # cloud-escalation door (2026-11-06) rides with change_setting instead of a
    # switch of its own; wave 13's one CREATE (2026-11-09, the carded
    # github_create_repo) joined after it, project_read - the read half of
    # "Jarvis takes over dev work" - ships OFF like file_read, wave 16's three
    # GitHub tools (2026-11-10: the PR cockpit, the carded merge and the carded
    # fix-and-push) also ship OFF, wave 16E's two local review tools (2026-11-10)
    # joined after them, and the parity pass added the full pull-request read and
    # six more carded writes. The registered count is therefore whatever
    # `jarvis_agent.TOOLS` holds and enabled is whatever the shipped settings
    # file lists (19 plus the two review gates the owner enabled by default);
    # both are DERIVED below, never typed, so a tool added later moves both
    # sides together (2026-11-13 audit, finding 4).
    inv = SP.tool_inventory()
    registered = len(A.TOOLS)
    enabled = len({str(getattr(ASK, "real_tool", lambda n: n)(n))
                   for n in (ASK.tools_enabled_set() or ())} & set(A.TOOLS))
    check("the inventory reads jarvis_agent.TOOLS", inv["registered"] == registered,
          str(inv["registered"]))
    check("the inventory reads the settings file's own enabled list",
          inv["enabled"] == enabled, str(inv["enabled"]))
    r = answer("what tools do you have")
    check("the answer exists", r is not None and r.reply, r and r.reply)
    reply = r.reply
    check("it names the registered count", f"{registered} tools" in reply, reply[:120])
    check("it names the switched-on count",
          f"{enabled} of them are switched on" in reply, reply[:160])
    # The list is capped at about fourteen names plus "and N more", so the
    # two named here are ones a fresh install really shows. "Web search"
    # fell past the cap when the four pack tools joined the shipped list
    # (2026-11-05), which is the cap working, not the answer losing it.
    check("it names a REAL tool in plain words",
          "Calculator" in reply and "drop-in plugins" in reply, reply[:200])
    check("it never repeats the old 136 as a tool count", "136 tools" not in reply)
    # ONE TRUTH: the chat answer, /api/self and the refresh sentence agree.
    c = SP.counts(SP.build(refresh=True))
    check("counts()['tools'] is the same number the answer names",
          f"{c['tools']} of them are switched on" in reply, str(c["tools"]))
    said = SP.refresh_sentence({}, c)
    check("the refresh sentence names the same pair",
          f"{c['tools_registered']} tools ({c['tools_enabled']} switched on" in said,
          said)


def tools_answer_follows_a_real_settings_file():
    """The answer is not a constant: a one-tool file changes it to ONE."""
    tmp = Path(tempfile.mkdtemp(prefix="jarvis-self-answers-toml-"))
    only_web = tmp / "only-web.toml"
    only_web.write_text('[tools]\nenabled = ["web_search"]\n', encoding="utf-8")
    real = os.environ.get("JARVIS_FRAMEWORK_TOML")
    try:
        os.environ["JARVIS_FRAMEWORK_TOML"] = str(only_web)
        inv = SP.tool_inventory()
        check("the inventory follows the file it is given", inv["enabled"] == 1
              and inv["enabled_names"] == ["web_search"],
              f"{inv['enabled']} / {inv['enabled_names']}")
        reply = answer("what tools can you use").reply
        check("the chat answer follows the same file",
              bool(reply) and "1 of them are switched on" in reply
              and "Web search" in reply, reply or "")
        remaining = len(A.TOOLS) - 1
        check(f"... and says the other {remaining} are not switched on",
              bool(reply)
              and f"other {remaining} are built in but not switched on" in reply,
              reply or "")
    finally:
        if real is None:
            os.environ.pop("JARVIS_FRAMEWORK_TOML", None)
        else:
            os.environ["JARVIS_FRAMEWORK_TOML"] = real


# ---------------------------------------------------------------------------
#   2b. "List all of your tools" - the COMPLETE inventory (2026-11-25)
# ---------------------------------------------------------------------------
#
# THE OWNER'S COMPLAINT. "Can you list all of your tools?" was answered "I have
# 90 tools built in. 47 of them are switched on in your settings file: ...
# and 17 more." That is `_run_tools_inventory`'s `cap=30`, and the cap is RIGHT
# for "what tools do you have?" - a count and a flavour - and wrong for a
# question that says ALL. These checks drive the real matcher and the real
# answer: the full list names every registered tool exactly once, marks each on
# or off from the settings file, and never says "and N more".

FULL_LIST_PHRASINGS = (
    "list all of your tools",
    "list every tool",
    "name every tool",
    "show me all your tools",
    "list all 90 tools",
    "list every tool you have",
    "can you list all of your tools",
)

#: Six REAL tools from four areas, with a known 2-on split. Real names so the
#: grouping is exercised; a made-up name would land under "Other" and prove
#: nothing about the area table.
FULL_LIST_FIXTURE = {
    "tools": {
        "registered": 6,
        "all_names": ["calculator", "notes_search", "append_obsidian_daily",
                      "github_ci_status", "send_email", "my_spending"],
        "registered_names": ["calculator", "notes_search",
                             "append_obsidian_daily", "github_ci_status",
                             "send_email", "my_spending"],
        "enabled": 2,
        "enabled_names": ["calculator", "append_obsidian_daily"],
    }
}


class _Fixture:
    """Set `jarvis_quick._MEASURED_FIXTURE` for the block, then put it back."""

    def __init__(self, fixture):
        self.fixture = fixture
        self.real = None

    def __enter__(self):
        self.real = Q._MEASURED_FIXTURE
        Q._MEASURED_FIXTURE = dict(self.fixture)

    def __exit__(self, *exc):
        Q._MEASURED_FIXTURE = self.real
        return False


def _bullets(reply):
    return [ln for ln in str(reply or "").splitlines() if ln.startswith("- ")]


def _marks(reply):
    """{plain label: "on"/"off"} from the answer's own bullet lines."""
    out = {}
    for line in _bullets(reply):
        label, _sep, mark = line[2:].rpartition(" — ")
        out[label] = mark
    return out


def the_full_list_phrasings_reach_the_complete_inventory():
    for words in FULL_LIST_PHRASINGS:
        got = Q.match(words)
        check(f"{words!r} asks for the complete inventory",
              got is not None and got.name == "tools_list_all",
              got.name if got else "went to the model")
    # And the count question keeps its own answer: the distinction only works
    # if both sides stay put.
    for words in ("what tools do you have", "how many tools do you have",
                  "how many tools do you have switched on right now",
                  "list tools", "what tools do you have around notes"):
        got = Q.match(words)
        check(f"{words!r} keeps the count answer",
              got is not None and got.name == "tools_inventory",
              got.name if got else "went to the model")


def the_first_person_count_question_reaches_the_inventory():
    """The owner's ruling Q2 (2026-11-27): the count is never the model's.

    Measured on the live backend at 12:45 that day: "how many tools do I have"
    was the ONE phrasing of this family that fell through, because every
    alternation said "do you". The model answered "You have 45 optional
    plug-ins" - a different noun and a fourth number, against 46 enabled in the
    settings file and 48 on the Reach page. The question a person asks about his
    own PC is "do I have", so it is read now.

    The last check is the other half: a near miss that names no "you"/"jarvis"
    must keep falling through, exactly as the module's own docstring promises.
    """
    for words in ("how many tools do I have", "how many tools do i have",
                  "what tools do I have", "how many tools are there",
                  "how many tools do I have switched on"):
        got = Q.match(words)
        check(f"first person reaches the inventory: {words!r}",
              got is not None and got.name == "tools_inventory",
              got.name if got else "went to the model")
    got = Q.match("what tools do I need for this job")
    check("... and a near miss that names no you/jarvis still goes to the model",
          got is None, got.name if got else "")


def the_summary_question_still_summarises():
    """The cap is deliberate for THIS question, and it stays."""
    with _Fixture(FULL_LIST_FIXTURE):
        res = answer("what tools do you have")
    reply = res.reply
    check("the count answer still counts",
          res.intent == "tools_inventory" and "6 tools" in reply
          and "2 of them are switched on" in reply, reply[:200])
    check("... and names the switched-on tools in one sentence",
          "Calculator" in reply and " — on" not in reply
          and " — off" not in reply, reply[:300])
    check("... and is not the line-per-tool list",
          not _bullets(reply), reply[:300])


def the_full_list_names_every_tool_exactly_once():
    names = FULL_LIST_FIXTURE["tools"]["all_names"]
    labels = {Q._tool_label(n) for n in names}
    with _Fixture(FULL_LIST_FIXTURE):
        res = answer("list all of your tools")
    reply = res.reply
    bullets = _bullets(reply)
    check("the complete inventory is its own intent",
          res.intent == "tools_list_all", res.intent)
    check("the count line comes first, from the registry's own numbers",
          reply.splitlines()[0] == "6 tools built in, 2 switched on.",
          reply.splitlines()[:1])
    check("one bullet per registered tool, no more and no fewer",
          len(bullets) == len(names), (len(bullets), len(names)))
    check("every registered tool is named exactly once",
          all(sum(1 for b in bullets if b[2:].startswith(lbl + " —")) == 1
              for lbl in labels),
          [lbl for lbl in labels
           if sum(1 for b in bullets if b[2:].startswith(lbl + " —")) != 1])
    check("... and no bullet names a tool that is not registered",
          all(b[2:].rpartition(" — ")[0] in labels for b in bullets), bullets)
    check("the answer never says 'and N more'",
          re.search(r"\band \d+ more\b", reply) is None, reply[-300:])
    check("it is line-per-tool text, not one comma-run",
          reply.count("\n") >= len(names), reply.count("\n"))


def the_full_list_marks_on_and_off_correctly():
    """A fixture with a KNOWN 2-of-6 split: every mark is checked both ways."""
    want = {"calculator": "on", "append_obsidian_daily": "on",
            "notes_search": "off", "github_ci_status": "off",
            "send_email": "off", "my_spending": "off"}
    with _Fixture(FULL_LIST_FIXTURE):
        reply = answer("name every tool").reply
    got = _marks(reply)
    check("each tool's mark is the settings file's own split",
          got == {Q._tool_label(n): m for n, m in want.items()}, got)
    check("... the two switched-on tools are marked on, not off",
          sum(1 for m in got.values() if m == "on") == 2, got)
    check("every tool line is a plain '- <label> — on/off' bullet",
          all(re.fullmatch(r"- .+ — (?:on|off)", b) for b in _bullets(reply)),
          _bullets(reply)[:3])


def the_full_list_is_grouped_by_area_in_plain_text():
    with _Fixture(FULL_LIST_FIXTURE):
        reply = answer("show me all your tools").reply
    headings = [ln for ln in reply.splitlines()
                if ln.endswith(":") and not ln.startswith("- ")]
    check("the tools are grouped under area headings",
          len(headings) >= 4, headings)
    check("... the headings are plain words, with no '#' and no table",
          all(re.fullmatch(r"[A-Z][A-Za-z' ]+:", h) for h in headings)
          and "#" not in reply and "|" not in reply, headings)
    check("... and the areas a person would look under are there",
          {"Notes", "Email", "GitHub", "Money"} <= {h[:-1] for h in headings},
          headings)
    check("... with every heading followed by at least one tool",
          all(reply.split(h, 1)[1].lstrip().startswith("- ") for h in headings),
          headings)


def a_tool_in_no_group_is_still_listed():
    """THE "NEVER A SILENT OMISSION" RULE: an unknown name lands under Other."""
    fixture = {"tools": {
        "registered": 2,
        "all_names": ["calculator", "not_a_real_tool"],
        "registered_names": ["calculator", "not_a_real_tool"],
        "enabled": 1, "enabled_names": ["calculator"]}}
    with _Fixture(fixture):
        reply = answer("list all of your tools").reply
    check("a tool the grouping tables do not know is listed under Other",
          "Other:" in reply and "- not_a_real_tool — off" in reply, reply)
    check("... so the answer still carries every registered name",
          len(_bullets(reply)) == 2, _bullets(reply))


def a_short_name_list_says_what_is_missing():
    fixture = {"tools": {
        "registered": 10,
        "all_names": ["calculator", "send_email"],
        "registered_names": ["calculator", "send_email"],
        "enabled": 0, "enabled_names": []}}
    with _Fixture(fixture):
        reply = answer("list all of your tools").reply
    check("a name list shorter than the count says how many are missing",
          "The registry names 2 of them; the other 8 could not be read" in reply,
          reply[:400])
    check("... and says they are missing, NOT switched off",
          "not switched off" in reply, reply[:400])


def an_unreadable_settings_file_marks_nothing_and_hides_nothing():
    fixture = {"tools": {
        "registered": 2,
        "all_names": ["calculator", "send_email"],
        "registered_names": ["calculator", "send_email"],
        "enabled": None, "enabled_names": []}}
    with _Fixture(fixture):
        reply = answer("list all of your tools").reply
    check("without a settings read the answer says it will not guess",
          "did not answer" in reply and "no tool below is marked" in reply,
          reply[:300])
    check("... it still lists every tool",
          len(_bullets(reply)) == 2, _bullets(reply))
    check("... and marks none of them on or off",
          " — on" not in reply and " — off" not in reply, reply)


def a_settings_file_naming_every_tool_does_not_break_it():
    """The real seam: every tool in the owner's own file, against the real path."""
    all_names = sorted(A.TOOLS)
    tmp = Path(tempfile.mkdtemp(prefix="jarvis-self-answers-all-"))
    every = tmp / "every-tool.toml"
    every.write_text('[tools]\nenabled = ["' + '", "'.join(all_names) + '"]\n',
                     encoding="utf-8")
    real = os.environ.get("JARVIS_FRAMEWORK_TOML")
    try:
        os.environ["JARVIS_FRAMEWORK_TOML"] = str(every)
        reply = answer("list all of your tools").reply
    finally:
        if real is None:
            os.environ.pop("JARVIS_FRAMEWORK_TOML", None)
        else:
            os.environ["JARVIS_FRAMEWORK_TOML"] = real
    bullets = _bullets(reply)
    check("a settings file naming every tool lists every tool",
          len(bullets) == len(A.TOOLS), (len(bullets), len(A.TOOLS)))
    check("... with every one marked on",
          all(ln.endswith(" — on") for ln in bullets),
          [ln for ln in bullets if not ln.endswith(" — on")][:3])
    check("... and the count line says all of them are switched on",
          f"{len(A.TOOLS)} tools built in, {len(A.TOOLS)} switched on."
          in reply, reply.splitlines()[:1])


def the_area_tables_cover_the_registry():
    """A new tool group or core tool gets a DELIBERATE area, not "Other".

    The names and the membership are `jarvis_agent`'s; only the plain-word area
    names live in this answer (see `_TOOL_AREA_ORDER`). That split is what makes
    a new tool appear without a second list - and these checks are what make the
    area names a decision rather than a default: a group or core tool with no
    area fails here, and an area name that is not one of the ordered headings
    fails too. A name-table entry that stops matching the registry is named as
    well, so the table cannot quietly go stale.
    """
    groups = {str(g) for g, _what, _members in A.TOOL_GROUPS}
    check("every tool group has a plain-words area",
          groups <= set(Q._TOOL_GROUP_AREA),
          sorted(groups - set(Q._TOOL_GROUP_AREA)))
    check("... and every mapped group still exists",
          set(Q._TOOL_GROUP_AREA) <= groups,
          sorted(set(Q._TOOL_GROUP_AREA) - groups))
    check("every core tool has an area",
          set(A.CORE_TOOLS) <= set(Q._TOOL_CORE_AREA),
          sorted(set(A.CORE_TOOLS) - set(Q._TOOL_CORE_AREA)))
    check("... and every mapped core tool still exists",
          set(Q._TOOL_CORE_AREA) <= set(A.TOOLS),
          sorted(set(Q._TOOL_CORE_AREA) - set(A.TOOLS)))
    named = (set(Q._TOOL_GROUP_AREA.values()) | set(Q._TOOL_CORE_AREA.values())
             | set(Q._TOOL_AREA_OVERRIDE.values()))
    check("every area an entry names is one of the ordered headings",
          named <= set(Q._TOOL_AREA_ORDER), sorted(named - set(Q._TOOL_AREA_ORDER)))
    check("a per-tool area override names a real tool",
          set(Q._TOOL_AREA_OVERRIDE) <= set(A.TOOLS),
          sorted(set(Q._TOOL_AREA_OVERRIDE) - set(A.TOOLS)))
    check("the area order ends with the catch-all",
          Q._TOOL_AREA_ORDER[-1] == "Other", Q._TOOL_AREA_ORDER[-1])


# ---------------------------------------------------------------------------
#   2c. One category, the group list, the other side of the switch (2026-11-26)
# ---------------------------------------------------------------------------
#
# THE OWNER MEASURED THESE ON THE LIVE APP and every one fell to the model:
# "which github tools do you have", "what note tools are there", "show me the
# email tools", "what groups of tools do you have", "list your tools by
# category", "which tools are switched off", "what tools can change my
# settings". The checks below assert the INTENT, not just that an answer came
# back: a neighbour swallowing the sentence is exactly the failure the
# note-merge bug taught this project to test for.

#: (sentence, intent, the areas it must name; None when the intent decides).
CATEGORY_CASES = (
    ("which github tools do you have", "tools_in_category", ["GitHub"]),
    ("what note tools are there", "tools_in_category", ["Notes"]),
    ("show me the email tools", "tools_in_category", ["Email"]),
    ("list the github tools", "tools_in_category", ["GitHub"]),
    ("the calendar tools", "tools_in_category", ["Calendar"]),
    ("what can the files tools do", "tools_in_category", ["Files and documents"]),
    ("which tools work on notes", "tools_in_category", ["Notes"]),
    ("which vault tools do you have", "tools_in_category", ["Notes"]),
    ("what obsidian tools are there", "tools_in_category", ["Notes"]),
    ("show me the mail tools", "tools_in_category", ["Email"]),
    ("which pr tools do you have", "tools_in_category", ["GitHub"]),
    ("the phone tools", "tools_in_category", ["Phone and messages"]),
    ("which android tools do you have", "tools_in_category",
     ["Phone and messages"]),
    ("the memory tools", "tools_in_category", ["Memory"]),
    ("what settings tools do you have", "tools_in_category", ["Settings"]),
    ("the web tools", "tools_in_category", ["The web"]),
    ("what browser tools are there", "tools_in_category", ["The web"]),
    ("what pc tools are there", "tools_in_category",
     ["Files and documents", "Controlling your PC and phone"]),
    ("what picture tools do you have", "tools_in_category", []),
    ("which photo tools are there", "tools_in_category", []),
    ("what groups of tools do you have", "tools_categories", None),
    ("list your tools by category", "tools_categories", None),
    ("which tools are switched off", "tools_switched_off", None),
    ("what tools are switched off", "tools_switched_off", None),
    ("what tools can change my settings", "tools_settings", None),
    ("which tools can change my settings", "tools_settings", None),
)

#: Sentences that already have their own owner and MUST NOT move here. Every
#: one was measured working on the live install (the owner's two reports).
KEPT_LANES = (
    ("what github tools do you have", "github_self"),
    ("what can you do with files", "feature_capabilities"),
    ("what plugins do you have", "plugin_list"),
    ("what plugins are switched on", "plugin_list"),
    ("how do I add a plugin", "plugin_install"),
    ("what skills are installed", "skill_menu_info"),
    ("what does the calculator tool do", "tool_profile"),
    ("turn off web search", "settings_bool"),
    ("switch on the email tool", "settings_tool"),
    ("disable the email tool", "settings_tool"),
    ("which tools ask before they act", "tools_asking"),
    ("what tools do you have", "tools_inventory"),
    ("list all of your tools", "tools_list_all"),
)


def the_category_questions_reach_their_own_answers():
    for words, want, areas in CATEGORY_CASES:
        got = Q.match(words)
        check(f"{words!r} -> {want}",
              got is not None and got.name == want,
              got.name if got else "went to the model")
        if got is None or got.name != "tools_in_category" or areas is None:
            continue
        check(f"... and {words!r} names {areas!r}",
              list(got.f.get("areas") or ()) == list(areas),
              got.f.get("areas"))


def the_lanes_that_already_work_do_not_move():
    for words, want in KEPT_LANES:
        got = Q.match(words)
        check(f"{words!r} still reaches {want}",
              got is not None and got.name == want,
              got.name if got else "went to the model")


def the_categories_partition_the_registry():
    """Every registered tool lands in EXACTLY one category, from the registry.

    The partition is `jarvis_agent.CORE_TOOLS` + `jarvis_agent.TOOL_GROUPS`
    (which `test_short_tool_list.py` already forces to hold every tool), read
    through `_tool_area_rows`. Nothing is hand-listed here: the check fails if a
    tool is in no category, in two, or if a category is empty.
    """
    rows = Q._tool_area_rows(sorted(A.TOOLS))
    flat = [(name, area) for area, names in rows for name in names]
    check("every registered tool is in exactly one category",
          sorted(n for n, _a in flat) == sorted(A.TOOLS),
          sorted(set(A.TOOLS) - {n for n, _a in flat}))
    check("... and no tool is listed twice",
          len(flat) == len(A.TOOLS) == len({n for n, _a in flat}),
          (len(flat), len(A.TOOLS)))
    check("no category is empty", all(names for _a, names in rows),
          [(a, len(ns)) for a, ns in rows if not ns])
    check("every category name is one of the ordered headings",
          all(a in Q._TOOL_AREA_ORDER for a, _ns in rows),
          [a for a, _ns in rows if a not in Q._TOOL_AREA_ORDER])
    check("every category WORD names a real heading (or none for pictures)",
          all(set(areas) <= set(Q._TOOL_AREA_ORDER)
              for areas in Q._TOOL_CATEGORY_AREAS.values()),
          [w for w, areas in Q._TOOL_CATEGORY_AREAS.items()
           if not set(areas) <= set(Q._TOOL_AREA_ORDER)])


def a_category_answer_is_the_same_bullet_shape():
    with _Fixture(FULL_LIST_FIXTURE):
        reply = answer("what note tools are there").reply
        github = answer("which github tools do you have").reply
    bullets = _bullets(reply)
    check("a category answer's count line is that category's own",
          reply.splitlines()[0] == "2 tools in Notes, 1 switched on.",
          reply.splitlines()[:1])
    check("... it names exactly the tools in that category", len(bullets) == 2,
          bullets)
    check("... with the same '- label — on/off' bullets as the full list",
          all(re.fullmatch(r"- .+ — (?:on|off)", b) for b in bullets), bullets)
    check("... and the settings split reaches the category answer",
          _marks(reply) == {"Searching your notes": "off",
                            "Adding to your Obsidian daily note": "on"},
          _marks(reply))
    check("... with no 'and N more'", re.search(r"\band \d+ more\b", reply)
          is None, reply[-200:])
    check("a second category answers from ITS tools, not the first one's",
          len(_bullets(github)) == 1
          and "GitHub" in github.splitlines()[0], github.splitlines()[:2])


def an_empty_category_is_an_honest_answer():
    with _Fixture(FULL_LIST_FIXTURE):
        reply = answer("what picture tools do you have").reply
    check("a category the registry has no tools for says so",
          "no built-in tool for pictures" in reply, reply[:200])
    check("... it lists no tool at all", not _bullets(reply), reply[:300])
    check("... and it does not name a nearest tool that is not registered",
          "The nearest" not in reply, reply[:300])
    # The real registry DOES have send_file_to_phone, so the live answer names
    # it - read from the registry, not typed.
    live = answer("what picture tools do you have").reply
    check("the live empty answer names the nearest real file tool",
          Q._tool_label("send_file_to_phone") in live, live[:300])


def the_switched_off_answer_is_the_complement():
    with _Fixture(FULL_LIST_FIXTURE):
        reply = answer("which tools are switched off").reply
    bullets = _bullets(reply)
    check("the switched-off answer counts the complement",
          reply.splitlines()[0] == "4 of my 6 built-in tools are switched off; "
                                   "2 are switched on.", reply.splitlines()[:1])
    check("... and lists every one of them", len(bullets) == 4, bullets)
    check("... each marked off, never on",
          all(b.endswith(" — off") for b in bullets), bullets)
    check("... and the enabled tools are NOT in it",
          "Calculator" not in reply
          and "Adding to your Obsidian daily note" not in reply, bullets)


def the_group_list_counts_are_the_partition():
    with _Fixture(FULL_LIST_FIXTURE):
        reply = answer("what groups of tools do you have").reply
    lines = [ln for ln in reply.splitlines() if ln.startswith("- ")]
    check("the group list counts the registry's own partition",
          reply.splitlines()[0] == "5 groups of tools, 6 built in, 2 switched on.",
          reply.splitlines()[:1])
    check("... one bullet per non-empty category", len(lines) == 5, lines)
    total = 0
    parsed = []
    for line in lines:
        m = re.fullmatch(r"- ([A-Z][A-Za-z' ]+): (\d+) tools? \((\d+) on\)", line)
        if m:
            parsed.append((m.group(1), int(m.group(2)), int(m.group(3))))
            total += int(m.group(2))
    check("... every line is a plain '- Area: N tools (K on)' bullet",
          len(parsed) == len(lines), lines)
    check("... and the per-group counts add up to the registry",
          total == 6, (total, lines))


def the_settings_attribute_is_read_from_the_registry():
    """The split uses the tool's own plain label, never a second list.

    A tool whose label says "(read-only)" cannot change anything; every settings
    tool whose label does not say that has a card or a write path. The group is
    `jarvis_agent.TOOL_GROUPS`' "settings" group.
    """
    reply = answer("what tools can change my settings").reply
    settings = Q._category_names(Q._tool_area_rows(sorted(A.TOOLS)),
                                 ("Settings",))
    changers = [n for n in settings
                if "read-only" not in Q._tool_label(n).lower()]
    readers = [n for n in settings if n not in changers]
    check("the settings group is not empty and has both halves",
          settings and changers and readers,
          (len(settings), len(changers), len(readers)))
    check("the answer's count line is the registry's own split",
          f"{len(changers)} of my {len(settings)} tools about my own settings can "
          f"change one; the other {len(readers)} only read them." in reply,
          reply.splitlines()[:1])
    bullets = _bullets(reply)
    check("... it lists every settings tool exactly once",
          len(bullets) == len(settings), (len(bullets), len(settings)))
    check("... the people who can change one are the ones whose label does not "
          "say read-only",
          all("read-only" not in b.lower() for b in bullets[:len(changers)])
          and all("read-only" in b.lower() for b in bullets[len(changers):]),
          bullets)


def every_category_answer_is_the_partition():
    """Live: each word's answer carries exactly the tools its areas hold."""
    rows = Q._tool_area_rows(sorted(A.TOOLS))
    for word, areas in Q._TOOL_CATEGORY_AREAS.items():
        if not areas:
            continue
        want = len(Q._category_names(rows, areas))
        reply = answer(f"which {word} tools do you have").reply
        check(f"the {word!r} answer is all {want} tools of its group(s)",
              len(_bullets(reply)) == want, (len(_bullets(reply)), want, word))
        check(f"... and the {word!r} sentence really reached the category lane",
              Q._self_tools_categories(
                  Q.normalize_spoken_command(f"which {word} tools do you have"))
              is not None, word)


def the_category_intents_are_read_only():
    for name in ("tools_in_category", "tools_categories",
                 "tools_switched_off", "tools_settings"):
        check(f"{name} cannot be undone by 'cancel that'",
              name in Q.READ_ONLY_INTENTS)


# ---------------------------------------------------------------------------
#   3. "Which of your tools ask before they act?" - the page's own rows
# ---------------------------------------------------------------------------


def asking_answer_is_the_pages_own_rows():
    view = ASK.view(here=False)
    want = [str(row.get("title") or row.get("id") or "")
            for group in view.get("groups") or ()
            for row in group.get("rows") or ()
            if str((row or {}).get("says") or "") == ASK.SAYS["ask"]]
    check("the page really has rows that ask first", len(want) > 0, str(len(want)))
    reply = answer("which of your tools ask before they act").reply
    check("the answer counts the page's own ask rows",
          f"{len(want)} actions ask you first" in reply, reply[:160])
    check("... and names a real row from the page", want[0] in reply, reply[:300])
    check("it says where the full list is",
          '"What asks first"' in reply and "Settings" in reply)
    # It must not be a made-up "all tools ask": the page says some do not.
    check("it does not claim every action asks", len(want) < 136, str(len(want)))


# ---------------------------------------------------------------------------
#   4. "What is connected?" - the reach page's ON rows + the plug-in folder
# ---------------------------------------------------------------------------


def connected_answer_is_the_reach_pages_on_rows():
    view = REACH.view()
    on = [str(r.get("name") or "") for r in view.get("rows") or () if r.get("on")]
    reply = answer("what is connected").reply
    check("the answer exists and is the reach list's own", reply.startswith(
        "Right now these are connected or reachable from this PC:") if on else
        reply.startswith("Nothing is connected"), reply[:160])
    for name in on:
        check(f"the connected answer names the reach row {name!r}", name in reply,
              reply[:300])
    try:
        import jarvis_plugins as P
        plugins = len(P.available() or ())
        want = (f"Plug-ins installed on this PC: {plugins}." if plugins
                else "No plug-ins are installed on this PC.")
        check("the plug-in count is the loader's own", want in reply, reply)
    except Exception:
        check("without jarvis_plugins the answer says it cannot read the folder",
              "cannot read the plug-in folder" in reply, reply)
    check("it says the PC wrote the list, not the model",
          "not by the AI model" in reply)


# ---------------------------------------------------------------------------
#   5. "Refresh your abilities" - the portrait's own refresh, said
# ---------------------------------------------------------------------------


def refresh_answer_is_the_portraits_own_refresh():
    r = answer("refresh your abilities")
    check("the refresh answer exists", r is not None and r.reply, r and r.reply)
    check("it says it re-read rather than restarted",
          "re-read" in r.reply and "Nothing was restarted" in r.reply, r.reply)
    c = SP.counts(SP.build(refresh=True))
    check("it names the real numbers the portrait holds",
          f"{c['settings']} settings" in r.reply
          and f"{c['tools_registered']} tools" in r.reply, r.reply)
    check("it changes nothing: the counts before and after are equal",
          c == SP.counts(SP.build(refresh=True)), str(c))


# ---------------------------------------------------------------------------
#   6. Two answers that used to deny something real (audit gaps 5 and 6)
# ---------------------------------------------------------------------------


def read_a_link_is_the_feature_it_names():
    """"compare web search and read a link" denied the row read-web-page.

    The row's own names were "read a web page" and "read a page"; "read a link"
    was answered "The feature list has no 'reading a link' row" - a limit that
    sounded honest and was false.
    """
    good = FG.find("read a link", loose=True)
    check('"read a link" names the real read-web-page row',
          good.get("kind") == "feature" and good["row"]["id"] == "read-web-page",
          str(good)[:200])
    check('"reading a link" names it too',
          FG.find("reading a link", loose=True).get("kind") == "feature")
    got = Q.match("compare web search and read a link")
    check("the comparison resolves to the real row, not a bare phrase",
          got is not None and got.name == "feature_difference"
          and got.f.get("second") == "read-web-page",
          str(got.f if got else None))
    r = answer("compare web search and read a link")
    check("the comparison answers with both real features",
          r is not None and "Read one web page out loud" in r.reply
          and "Web search" in r.reply, r and r.reply[:200])
    check("... and never repeats the false 'no reading a link row' limit",
          r is not None and "nothing to compare it with" not in r.reply)


def the_focus_preset_is_a_real_setting():
    """"what is the focus preset" denied a real 22-option setting.

    The preset-detail grammar read the words as a preset called "focus" and
    answered "There is no preset called focus" - while `focus_preset` is a real
    choice in the settings registry. Phase 3 gave it the richer answer the
    ruling asked for: every real preset row with its model, and which one is
    chosen - read from `jarvis_presets`, not typed here. A REAL preset must
    still answer as one.
    """
    got = Q.match("what is the focus preset")
    check("it is the focus preset's own answer, not a preset detail",
          got is not None and got.name == "focus_presets",
          f"{got.name if got else None} {getattr(got, 'f', None)}")
    r = answer("what is the focus preset")
    check("the answer never denies it exists",
          r is not None and "There is no preset called" not in r.reply,
          r and r.reply)
    check("... it names the setting and how many real rows it picks between",
          r is not None and "focus preset is a choice in Settings" in r.reply
          and f"{len(_presets())} model presets" in r.reply,
          r and r.reply[:300])
    check("... every row it lists is a real row's own title and model",
          r is not None and all(p.title in r.reply and p.model in r.reply
                                for p in _presets()), r and r.reply[:600])
    check("... and it says which one is chosen, or that none is",
          r is not None and ("chosen on this PC right now" in r.reply
                             or "none is chosen" in r.reply
                             or "could not read which preset" in r.reply),
          r and r.reply[-300:])
    got = Q.match("what is the coding preset")
    check("a REAL preset still answers as a preset",
          got is not None and got.name == "preset_detail"
          and got.f.get("name") == "coding", str(getattr(got, "f", None)))


def _presets():
    import jarvis_presets as P
    return list(P.PRESETS)


def the_two_settings_numbers_reconcile():
    """80 vs 48: "what can I change?" and /api/self used to disagree.

    Both numbers are honest - the spoken answer counts permission rules, tool
    offers and family rows; the portrait counts the Settings cards' own rows -
    but two doors gave two numbers with nothing relating them (audit gap 9).
    The spoken sentence now states the difference, and both counts are derived
    from the tables rather than typed.
    """
    data = REG.changeable_settings()
    registry_rows = (len(REG.BOOL_SETTINGS) + len(REG.CHOICE_SETTINGS)
                     + len(REG.NUMBER_SETTINGS))
    # Wave-10 Q4 added `wifi_auto_reconnect` to BOOL_SETTINGS (the owner's
    # six-guardrail ruling), so this derived count moves 49 -> 50 with it.
    # 2026-11-25: `answer_style` joined CHOICE_SETTINGS (the typed answer's
    # layout dial beside the manner pair), so the same derived count moves
    # 50 -> 51. Measured from the three tables, not chosen.
    check("the registry's own row count is 51", registry_rows == 51,
          str(registry_rows))
    check("the spoken answer names how many of its count are those rows",
          f"{registry_rows} of them are the switches, named choices and numbers" in
          data["words"], data["words"][-500:])
    check("the spoken answer names the other half as what it is",
          data["count"] > registry_rows
          and f"the other {data['count'] - registry_rows} are permission rules" in
          data["words"], data["words"][-500:])
    p = SP.counts(SP.build(refresh=True))
    check("the portrait's settings count IS the registry's own row count",
          p["settings"] == registry_rows, str(p["settings"]))
    check("the visible settings list has the same size",
          len([r for r in SP.settings() if r["kind"] in
               ("switch", "choice", "number")]) == registry_rows)


#: The GitHub questions the audit of 2026-11-07 measured as model guesses
#: (`.dsh-scratch/TOOL-CAPABILITY-AUDIT-2026-11-07/chat_answers.json`). Each is
#: the deterministic intent now; "how do I disconnect it?" with no noun is
#: deliberately NOT here - a bare "it" is ambiguous and must keep the model.
GITHUB_SELF_CASES = (
    ("what is your GitHub repository?", "github_self", "darknight11ish/Epic-Jarvis"),
    ("where does your code live?", "github_self", "darknight11ish/Epic-Jarvis"),
    # 2026-11-10: merging IS built now, behind one card per merge and merge
    # commit only. The old needles ("no merge card", "cannot merge") pinned the
    # read/comment-only boundary this decision replaced; the honest answers name
    # the card, the merge commit and the bans that remain.
    ("can you merge a pull request?", "github_self", "one approval card"),
    ("did you merge that PR?", "github_self", "merge commit"),
    ("what can't you do on GitHub?", "github_self", "force-push"),
    ("what do you need before you can read my repos?", "github_self",
     "personal access token"),
    ("what GitHub tools do you have?", "github_self", "github_rerun_workflow"),
    ("can you comment on an issue?", "github_self", "approval card"),
    ("what asks before GitHub acts?", "github_self", "ask you first"),
    ("what accounts do I have?", "accounts_answer", "GitHub"),
    ("what abilities does my GitHub connection have?", "accounts_answer",
     "github comment"),
    ("how do I disconnect my GitHub?", "accounts_answer",
     "Windows Credential Manager"),
)


def the_github_questions_read_their_modules():
    """The 2026-11-07 audit's false answers are deterministic, from the modules.

    The merge one is the measured inversion this holds: the model answered
    "no" and then offered "the system's card for it" - a card that did not exist.
    Since 2026-11-10 the card DOES exist for a merge and for a PR-branch push, so
    the fixed answers name the card, say merge commit only, and say the bans that
    remain (`jarvis_github.NEVER_WORDS`).
    """
    for question, intent_name, needle in GITHUB_SELF_CASES:
        got = Q.match(question)
        check(f"{question!r} -> {intent_name}",
              got is not None and got.name == intent_name,
              got.name if got else None)
        if got is None:
            continue
        try:
            reply = Q.run(got, _Sched(), 0.0).reply
        except Exception as exc:            # noqa: BLE001 - a real failure, named
            check(f"{question!r} answers", False, f"{type(exc).__name__}: {exc}")
            continue
        check(f"{question!r} names {needle!r}", needle.lower() in reply.lower(),
              reply[:300])
        if "merge" in question.lower():
            check(f"{question!r} names the ONE card and merge-commit-only, and "
                  f"never proposes a merge",
                  "propose the merge" not in reply.lower()
                  and "one approval card" in reply.lower()
                  and "merge commit" in reply.lower(), reply)
    check("the two new GitHub intents are read-only",
          {"github_self", "accounts_answer"} <= set(Q.READ_ONLY_INTENTS))


# ---------------------------------------------------------------------------


def the_page_carries_no_hand_typed_counts():
    """Finding 4 (2026-11-13): the page typed counts that had gone stale.

    `docs/SELF-AWARENESS.md` said "all 49 settings, all 61 tool switches" and
    "(49 settings, 61 tools, 181 features)" long after the registries had moved
    past every one of those numbers. A count typed into prose has no owner and
    no test; the page now says "every setting value, every tool switch" and
    "the counts read from the program's own tables". This check fails if a
    count of settings, tools or features is typed into the page again, so the
    stale number cannot come back unnoticed.
    """
    typed = re.findall(r"\b\d+\s+(?:settings|tools?|tool switches|features)\b",
                       DOC, re.IGNORECASE)
    check("docs/SELF-AWARENESS.md carries no hand-typed count of settings, "
          "tools or features", not typed, typed[:8])


def main() -> int:
    try:
        the_docs_quoted_questions_all_answer()
        near_misses_still_go_to_the_model()
        all_self_answers_are_read_only()
        tools_answer_is_the_registry_and_the_live_file()
        tools_answer_follows_a_real_settings_file()
        the_full_list_phrasings_reach_the_complete_inventory()
        the_first_person_count_question_reaches_the_inventory()
        the_summary_question_still_summarises()
        the_full_list_names_every_tool_exactly_once()
        the_full_list_marks_on_and_off_correctly()
        the_full_list_is_grouped_by_area_in_plain_text()
        the_area_tables_cover_the_registry()
        a_tool_in_no_group_is_still_listed()
        a_short_name_list_says_what_is_missing()
        an_unreadable_settings_file_marks_nothing_and_hides_nothing()
        a_settings_file_naming_every_tool_does_not_break_it()
        the_category_questions_reach_their_own_answers()
        the_lanes_that_already_work_do_not_move()
        the_categories_partition_the_registry()
        a_category_answer_is_the_same_bullet_shape()
        an_empty_category_is_an_honest_answer()
        the_switched_off_answer_is_the_complement()
        the_group_list_counts_are_the_partition()
        the_settings_attribute_is_read_from_the_registry()
        every_category_answer_is_the_partition()
        the_category_intents_are_read_only()
        asking_answer_is_the_pages_own_rows()
        connected_answer_is_the_reach_pages_on_rows()
        refresh_answer_is_the_portraits_own_refresh()
        the_two_settings_numbers_reconcile()
        read_a_link_is_the_feature_it_names()
        the_focus_preset_is_a_real_setting()
        the_github_questions_read_their_modules()
        the_page_carries_no_hand_typed_counts()
    except Exception:
        traceback.print_exc()
        FAILED.append("the suite itself raised")
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        for name in FAILED:
            print(f"  FAILED  {name}")
        return 1
    print("PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
