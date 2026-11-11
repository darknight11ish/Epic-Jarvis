"""test_tool_contract.py - the tool table's three policies, pinned side by side.

    python -B backend/test_tool_contract.py

THE FINDING (schedule-source-taint wave, 2026-10-26). The tool table is the
one place where "what may the model do" is decided, and its three answers
live in different files: `[tools].enabled` in `jarvis-framework.toml` (what a
fresh install offers), the cloud lane (which must be offered no tools at all),
and a private turn (the same). Nothing compared them, so a tool could be
added to `jarvis_agent.TOOLS` without anyone deciding whether the cloud lane
or a private turn may offer it - and a SWAP (one tool out, another in) would
not move any count at all.

WHAT THIS PINS, AS EXPLICIT SORTED NAME LISTS
  (a) FULL_ENABLED - what `enabled_tools_for_turn()` returns on a fresh
      install: the shipped template copied in as the settings file, in a temp
      folder, exactly as `test_tool_defaults.py` does it. Nineteen names today.
  (b) CLOUD_ALLOWED - the tools a cloud lane may be offered. There is no
      cloud-tool allow-list in this tree, and that is the answer: the local
      tool loop is never called for a cloud lane and no cloud request builder
      sends a `tools` key. The list is pinned empty, and two source sentences
      that state it are checked, so adding cloud tools cannot pass silently.
  (c) PRIVATE_CHAT_ALLOWED - the tools a private turn may be offered. The
      private-chat slice (PR #836) is not on `main`; this tree has no
      private-turn path at all, so the list is pinned empty ON PURPOSE. When
      that work lands, this is the decision it must come back and change.
  (d) CATALOGUE - every name in `jarvis_agent.TOOLS`, pinned in full. This is
      the part that makes a future tool stop here: a new tool cannot be added
      without editing this list, and the moment someone does, the three
      policies above are right beside it.

Offered lists are compared the same way: `offered_tools` returns `TOOLS`
order, so every comparison below sorts first. No model, no network, no real
settings file: the config folder is a temp one, and the settings file read is
a copy of the shipped template.

Run it with no ambient JARVIS_BACKEND (as `run_suites.py` does by default):
this suite pins THIS repository's copy.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent

TMP = Path(tempfile.mkdtemp(prefix="jarvis-tool-contract-"))
CONFIG_DIR = TMP / "config"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
os.environ["OPENJARVIS_CONFIG_DIR"] = str(CONFIG_DIR)
os.environ["JARVIS_CONFIG_DIR"] = str(CONFIG_DIR)

sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

sys.path.insert(0, str(HERE / "rebuilt"))
require_shipped("jarvis_agent.py", "jarvis_documents.py")
import jarvis_agent as AG  # noqa: E402
import jarvis_documents as JD  # noqa: E402

try:
    import tomllib
except ModuleNotFoundError:                       # Python < 3.11
    try:
        import tomli as tomllib
    except ModuleNotFoundError:
        tomllib = None

TEMPLATE = REPO / "backend" / "rebuilt" / "jarvis-framework.toml"
BASE = REPO / "jarvis-backend" / "jarvis-framework.toml"

# --------------------------------------------------------------------------
#   THE THREE POLICIES, PINNED. Sorted, explicit, no counts.
# --------------------------------------------------------------------------

#: (a) A fresh install's `[tools].enabled`, read through
#: `jarvis_agent.enabled_tools_for_turn()` with the shipped template copied in.
FULL_ENABLED = [
    "approval_policy", "calculator", "change_setting", "conversation_find", "conversation_open",
    "feature_guide", "memory_search", "my_files", "pack_inspect", "pack_install",
    "pack_list", "pack_remove", "phone_apps", "plugin_list", "plugin_switch",
    "refresh_abilities", "self_portrait", "send_text_message",
    "web_search",
]

#: (b) Tools a cloud lane may be offered. NONE: the tool loop is local-only
#: and the cloud lane's request builder sends no tools. Pinned empty.
CLOUD_ALLOWED = []

#: (c) Tools a private turn may be offered. NONE: no private-turn path is on
#: this tree yet (the private-chat slice is a separate branch). Pinned empty
#: so the decision is recorded here rather than assumed.
PRIVATE_CHAT_ALLOWED = []

#: What those enabled nineteen become when a turn is built: `my_files` is
#: dropped while no folder is listed (the model is never offered a tool that
#: could read nothing), so a fresh PC offers twelve base tools - plus the
#: conversation web-search approval and its instant stop, which ride with
#: `web_search` (2026-11-02, `jarvis_agent.GRANT_ASK_TOOLS`): offering the ASK
#: grants nothing, because the store is written only after a person answers the
#: card. `phone_apps` joined the fresh offer on 2026-11-02 (#1097): it
#: manages the phone's app allow-list, is card-first, and is the only way to
#: fill a list that ships empty. `send_file_to_phone` is NOT a default (it
#: leaves the PC for the phone); the owner enables it in their own settings.
#: The four read-only self/chat tools joined on 2026-11-04 (Gemini ruling Q2)
#: and are offered like any other enabled tool - `conversation_clear` is not a
#: tool at all, so it cannot appear here.
OFFERED_FRESH = [
    "approval_policy", "approve_web_search_for_conversation", "calculator",
    "change_setting", "cloud_escalation",
    "conversation_find", "conversation_open", "feature_guide", "memory_search",
    "pack_inspect", "pack_install", "pack_list", "pack_remove", "phone_apps",
    "plugin_list", "plugin_switch", "refresh_abilities",
    "self_portrait", "stop_web_search_approval", "web_search",
]

#: (d) Every tool that exists, pinned in full. A future tool must be added
#: here, which forces the three lists above to be looked at in the same edit.
#: `approve_web_search_for_conversation` and `stop_web_search_approval` (the
#: conversation-scoped web-search approval and its instant stop, 2026-11-01)
#: are NOT in FULL_ENABLED: `[tools].enabled` never names them (2026-11-02,
#: after the field test that proved the old "Settings -> Tools" switch left the
#: feature dead on the owner's own PC). They ARE in OFFERED_FRESH because the
#: ask rides with `web_search` - it is not a capability, and its card is the
#: permission.
CATALOGUE = [
    "append_logseq_journal", "append_obsidian_daily",
    "approval_policy",
    "approve_web_search_for_conversation", "browser_control",
    "calculator", "calendar_read", "change_setting", "check_records",
    # The standing cloud escalation switch (2026-11-06, the 0-of-6 action-card
    # run): the only door in chat to the PRESETS menu's Cloud row. Like the
    # web-search ask and its stop, `[tools].enabled` never names it - it rides
    # with `change_setting` (jarvis_agent.RIDES_WITH_SETTINGS) - so it is NOT in
    # FULL_ENABLED and IS in OFFERED_FRESH. Its ONE `change_own_config` card is
    # raised inside jarvis_presets.cloud_escalate(), the same call the Presets
    # menu makes.
    "cloud_escalation", "coming_up",
    "connect_account", "control_computer", "control_phone",
    # Reading one of the owner's own kept conversations (2026-11-03: "pull up
    # any old conversation"). Both are read-only under `skill_list`. Clearing is
    # NOT a model tool (Gemini ruling 1, 2026-11-03): it stays route / app /
    # fast-path only, behind its ONE `conversation_clear` card.
    "conversation_find", "conversation_open",
    "create_joplin_note",
    "draft_email",
    "email_check", "feature_guide", "file_read",
    # Your own GitHub, on demand (2026-11-03, the owner's "Read + actions").
    # None of the six is in FULL_ENABLED or OFFERED_FRESH: like `github_search`
    # they ship SWITCHED OFF, because each one sends the owner's GitHub token
    # out and the tools are useless until a token is saved anyway. They are in
    # the catalogue so the next tool added has to be looked at here too.
    # The three of the owner's 2026-11-10 "Everything at once" decision - the
    # read-only PR cockpit, the carded merge and the carded fix-and-push - sit
    # in their sorted places, so a swap reads as a change.
    #
    # The two LOCAL review gates (2026-11-10, wave 16E) are here too, and they
    # are the pair worth noticing: `review_changes` and `check_records`
    # read a checkout on this PC, never GitHub, so they are in neither
    # FULL_ENABLED nor OFFERED_FRESH (both ship off - their own switch is the
    # only way in) and they are the only GitHub-group tools that raise NO card.
    "github_ci_status", "github_comment", "github_create_repo",
    "github_ci_status", "github_comment", "github_create_repo",
    "github_edit_pr", "github_fix_and_push", "github_issue_labels",
    "github_issue_state", "github_list", "github_merge_pr",
    "github_open_issue", "github_open_pr", "github_pr_detail",
    "github_pr_review", "github_pr_scan", "github_read_file",
    "github_rerun_workflow", "github_search", "github_workflow",
    "goal_add", "goal_done", "goal_progress", "goals_list",
    "home_control", "home_read", "memory_search", "my_files", "my_spending",
    "notes_search",
    # The pack tools (2026-11-05): list and inspect are read-only under the gate
    # action skill_list; install raises its one card inside jarvis_skills.install;
    # remove raises one card naming exactly the files in the pack ledger.
    "pack_inspect", "pack_install", "pack_list", "pack_remove",
    "phone_apps", "plugin_list", "plugin_switch",
    # The product check (2026-11-04, the owner's choice "wire the existing
    # product check"): ONE Amazon product page, one PC-only card, tier "ask".
    # NOT in FULL_ENABLED - `[product_check] enabled = false` ships, and the
    # tool is not even offered while it is off - and not in a cloud or
    # private-turn allow-list (both are empty by design).
    "product_check",
    # The read half of taking over dev work (2026-11-09): cardless, decided
    # under file_read's own `read_files_readonly` action, and ships OFF - so
    # it is here (the catalogue is where "a new tool landed" is recorded) but
    # not in FULL_ENABLED, OFFERED_FRESH, the cloud lane or a private turn.
    "project_read", "propose_plan",
    "protect_from_jarvis", "rea_investigate",
    "read_web_page",
    # Re-read Jarvis's own abilities (2026-11-03, the owner's ask to "refresh
    # its function and capabilities awareness"): read-only, no card, decided
    # under the gate's own `skill_list` action like feature_guide. Not in a
    # cloud or private-turn allow-list (both are empty by design).
    "refresh_abilities",
    # What Jarvis is made of (2026-11-03: "be aware of every setting, function
    # and ability it has"): read-only under `skill_list`, no card.
    "retirement_whatif", "review_changes", "run_data_script",
    "self_portrait",
    "send_email", "send_file_to_phone",
    # Texting a contact (2026-11-04, hands-free mode): a REAL message from the
    # owner's own phone, in their name, which cannot be unsent. In the shipped
    # template's list but withheld from every turn until the mode is on
    # (`offered_tools`), so it is not in FULL_ENABLED; it is here because a
    # cloud or private turn must never be offered it, and this list is where
    # that decision is recorded.
    "send_text_message",
    "set_reminder",
    "set_timer", "setup_quiz", "shell_exec", "stop_web_search_approval", "tidy_inbox",
    "todo_add", "todo_done",
    "web_search",
]

PASSED, FAILED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    SKIPPED.append(why)
    print(f"skip  {why}")


def _source(name: str) -> str:
    """One backend module's text, or "" when this tree does not carry it."""
    path = HERE / name
    return path.read_text(encoding="utf-8") if path.is_file() else ""


# --------------------------------------------------------------------------
#   The lists themselves
# --------------------------------------------------------------------------

def t_each_pinned_list_is_sorted_unique_and_real():
    for label, names in (("FULL_ENABLED", FULL_ENABLED),
                         ("CLOUD_ALLOWED", CLOUD_ALLOWED),
                         ("PRIVATE_CHAT_ALLOWED", PRIVATE_CHAT_ALLOWED),
                         ("OFFERED_FRESH", OFFERED_FRESH),
                         ("CATALOGUE", CATALOGUE)):
        check(f"{label} is written in sorted order (so a swap reads as a change)",
              names == sorted(names), names)
        check(f"...and has no duplicate name", len(names) == len(set(names)), names)
        if label == "CATALOGUE":
            continue
        unknown = [n for n in names if n not in CATALOGUE]
        check(f"...and every {label} name is in the pinned catalogue",
              unknown == [], unknown)


def t_the_three_policies_are_disjoint_and_accounted_for():
    enabled = set(FULL_ENABLED)
    check("the cloud lane's allowed list is explicitly empty", CLOUD_ALLOWED == [])
    check("the private turn's allowed list is explicitly empty",
          PRIVATE_CHAT_ALLOWED == [])
    check("no tool is in two policies at once",
          enabled.isdisjoint(CLOUD_ALLOWED)
          and enabled.isdisjoint(PRIVATE_CHAT_ALLOWED)
          and set(CLOUD_ALLOWED).isdisjoint(PRIVATE_CHAT_ALLOWED))
    check("the three policies together are exactly the enabled set (today: "
          "cloud and private add nothing)",
          sorted(enabled | set(CLOUD_ALLOWED) | set(PRIVATE_CHAT_ALLOWED))
          == FULL_ENABLED)


def t_the_catalogue_is_pinned_in_full():
    actual = sorted(AG.TOOLS)
    check("jarvis_agent.TOOLS is exactly the pinned catalogue",
          actual == CATALOGUE,
          "a tool was added or removed: add/remove it in CATALOGUE above and "
          "decide whether the cloud lane or a private turn may offer it\n"
          f"        only in TOOLS: {sorted(set(actual) - set(CATALOGUE))}\n"
          f"        only in CATALOGUE: {sorted(set(CATALOGUE) - set(actual))}")
    check("...and every catalogue name is a real tool object",
          all(name in AG.TOOLS for name in CATALOGUE))


# --------------------------------------------------------------------------
#   (a) a fresh install
# --------------------------------------------------------------------------

def _fresh_settings() -> Path:
    settings = TMP / "jarvis-framework.toml"
    settings.write_text(TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")
    return settings


def _with_fresh_settings(fn):
    settings = _fresh_settings()
    old = os.environ.get("JARVIS_FRAMEWORK_TOML")
    os.environ["JARVIS_FRAMEWORK_TOML"] = str(settings)
    try:
        return fn()
    finally:
        if old is None:
            os.environ.pop("JARVIS_FRAMEWORK_TOML", None)
        else:
            os.environ["JARVIS_FRAMEWORK_TOML"] = old


def t_a_fresh_install_enables_exactly_the_pinned_set():
    if tomllib is None:
        skip("no tomllib/tomli (Python < 3.11), so the template could not be parsed")
        return
    check("the repository's template exists", TEMPLATE.is_file(), str(TEMPLATE))
    check("the published base's copy exists", BASE.is_file(), str(BASE))
    check("the two templates are byte-identical (the two-file rule)",
          BASE.read_text(encoding="utf-8") == TEMPLATE.read_text(encoding="utf-8"))
    parsed = sorted(tomllib.loads(TEMPLATE.read_text(encoding="utf-8"))["tools"]["enabled"])
    check("the shipped template's own list is the pinned one", parsed == FULL_ENABLED,
          parsed)

    def read():
        return sorted(AG.enabled_tools_for_turn())

    got = _with_fresh_settings(read)
    check("a fresh install's turn enables exactly the nineteen pinned names",
          got == FULL_ENABLED, got)


def t_a_fresh_install_offers_exactly_the_pinned_list():
    real_folders = JD.folders
    try:
        JD.folders = lambda: []
        got = _with_fresh_settings(
            lambda: sorted(AG.offered_tools(AG.enabled_tools_for_turn())))
    finally:
        JD.folders = real_folders
    check("a fresh install (no folder listed) offers exactly nineteen names - "
          "the seventeen local defaults plus the grant ask and its stop, which "
          "ride with web search - with my_files withheld by its own rule",
          got == OFFERED_FRESH, got)
    check("...so my_files is enabled but not offered: the folder is the only "
          "thing keeping it out",
          "my_files" in FULL_ENABLED and "my_files" not in OFFERED_FRESH)


# --------------------------------------------------------------------------
#   (b) the cloud lane: no tools, and the source still says so
# --------------------------------------------------------------------------

#: A name that assigns a cloud tool allow-list. None exists today; if one
#: appears, this suite fails and the author must pin it in CLOUD_ALLOWED.
_CLOUD_TOOL_SET = re.compile(
    r"^\s*(?:CLOUD|cloud)[A-Za-z_]*(?:TOOL|tool)[A-Za-z_]*\s*=", re.M)
#: The same shape for a private turn.
_PRIVATE_TOOL_SET = re.compile(
    r"^\s*(?:PRIVATE|private)[A-Za-z_]*(?:TOOL|tool)[A-Za-z_]*\s*=", re.M)


def _sets_named(pattern) -> list:
    hits = []
    for path in sorted(HERE.glob("*.py")):
        if path.name.startswith("test_"):
            continue
        if pattern.search(path.read_text(encoding="utf-8")):
            hits.append(path.name)
    return hits


def t_the_cloud_lane_is_offered_no_tools():
    check("offering the pinned cloud list offers nothing",
          AG.offered_tools(set(CLOUD_ALLOWED)) == [],
          AG.offered_tools(set(CLOUD_ALLOWED)))
    found = _sets_named(_CLOUD_TOOL_SET)
    check("no backend module defines a cloud tool allow-list (if this fails, "
          "pin it in CLOUD_ALLOWED and decide it)", found == [], found)
    agent_src = _source("jarvis_agent.py")
    check("jarvis_agent.py still says the tool loop is never called for a "
          "cloud lane",
          "This is never called for a cloud lane." in agent_src)
    chatbot_src = _source("jarvis_chatbot_api.py")
    check("jarvis_chatbot_api.py still says no cloud lane offers tools today",
          "No cloud lane offers tools today" in chatbot_src)


# --------------------------------------------------------------------------
#   (c) a private turn: no tools, and no path to offer them here yet
# --------------------------------------------------------------------------

def t_a_private_turn_is_offered_no_tools():
    check("offering the pinned private-turn list offers nothing",
          AG.offered_tools(set(PRIVATE_CHAT_ALLOWED)) == [],
          AG.offered_tools(set(PRIVATE_CHAT_ALLOWED)))
    found = _sets_named(_PRIVATE_TOOL_SET)
    check("no backend module defines a private-turn tool allow-list yet "
          "(when the private-chat slice lands, pin its set in "
          "PRIVATE_CHAT_ALLOWED and decide it)", found == [], found)
    names = sorted(n for n in dir(AG)
                   if "private" in n.lower() and "tool" in n.lower())
    check("...and jarvis_agent exposes no private-turn tool list either",
          names == [], names)


def main():
    print(f"--- tool contract --- ({AG.__file__})")
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"--- {name} ---")
            try:
                fn()
            except Exception as exc:  # pragma: no cover
                traceback.print_exc()
                check(f"{name} ran without crashing", False, repr(exc))
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
