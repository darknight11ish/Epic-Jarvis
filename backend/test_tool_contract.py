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
      folder, exactly as `test_tool_defaults.py` does it. Six names today.
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
    "calculator", "change_setting", "feature_guide", "memory_search",
    "my_files", "web_search",
]

#: (b) Tools a cloud lane may be offered. NONE: the tool loop is local-only
#: and the cloud lane's request builder sends no tools. Pinned empty.
CLOUD_ALLOWED = []

#: (c) Tools a private turn may be offered. NONE: no private-turn path is on
#: this tree yet (the private-chat slice is a separate branch). Pinned empty
#: so the decision is recorded here rather than assumed.
PRIVATE_CHAT_ALLOWED = []

#: What those enabled six become when a turn is built: `my_files` is dropped
#: while no folder is listed (the model is never offered a tool that could
#: read nothing), so a fresh PC offers five. Sorted.
OFFERED_FRESH = [
    "calculator", "change_setting", "feature_guide", "memory_search",
    "web_search",
]

#: (d) Every tool that exists, pinned in full. A future tool must be added
#: here, which forces the three lists above to be looked at in the same edit.
CATALOGUE = [
    "append_logseq_journal", "append_obsidian_daily", "browser_control",
    "calculator", "calendar_read", "change_setting", "coming_up",
    "control_computer", "control_phone", "create_joplin_note", "draft_email",
    "email_check", "feature_guide", "file_read", "github_search",
    "home_control", "home_read", "memory_search", "my_files", "my_spending",
    "notes_search", "propose_plan", "rea_investigate", "read_web_page",
    "retirement_whatif", "run_data_script", "send_email", "set_reminder",
    "set_timer", "shell_exec", "tidy_inbox", "todo_add", "todo_done",
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
    check("a fresh install's turn enables exactly the six pinned names",
          got == FULL_ENABLED, got)


def t_a_fresh_install_offers_exactly_the_pinned_list():
    real_folders = JD.folders
    try:
        JD.folders = lambda: []
        got = _with_fresh_settings(
            lambda: sorted(AG.offered_tools(AG.enabled_tools_for_turn())))
    finally:
        JD.folders = real_folders
    check("a fresh install (no folder listed) offers exactly five names, "
          "my_files withheld by its own rule", got == OFFERED_FRESH, got)
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
