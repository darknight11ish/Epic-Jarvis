"""test_tool_defaults.py - the tools a FRESH INSTALL is offered.

    python -B backend/test_tool_defaults.py

THE FINDING (post-install field test, 2026-10-20). The shipped
`[tools].enabled` named only `web_search`, `change_setting` and
`feature_guide`. On a fresh install that meant `calculator`, `memory_search`
and `my_files` were never offered to the model - even though "search my
recordings" (docs/JARVIS-API.md section 149) needs `my_files`, whose
`search_media` action is where that chat path lives. That is a default this
repository chose, not the owner: the template is what
`scripts/apply-patches.ps1` copies to the PC when there is no settings file.

WHAT THIS PINS
  1. BOTH SHIPPED TEMPLATES name the six defaults. The repository's copy
     (`backend/rebuilt/jarvis-framework.toml`) and the published base's copy
     (`jarvis-backend/jarvis-framework.toml`) are byte-identical, and every
     name in the list is a real tool (`jarvis_agent.TOOLS`) - a name that is
     not a tool here is dropped in silence by `offered_tools`, which is how a
     default can look on and do nothing.
  2. A FRESH INSTALL OFFERS THEM. The template copied in as the settings file
     (exactly what apply-patches.ps1 installs) makes a turn's enabled set the
     six, and the model is offered calculator, memory_search, web_search,
     change_setting and feature_guide.
  3. my_files IS STILL HIDDEN WITH NO FOLDER. It is in the list, but with no
     folder in "Folders Jarvis may look in" `offered_tools` omits it, so a
     fresh PC pays no tokens for it and reads nothing; once a folder is listed
     it is offered.
  4. NO CONTROL, BROWSER OR MAIL TOOL IS TURNED ON by this default list.
  5. THE DOCS SAY THE SAME. JARVIS-API.md section 149 names this default list
     and says why `my_files` still needs a folder - the old sentence that
     named only the first three is gone.

No model runs, no network, no real settings file is touched: the settings file
read here is a copy of the shipped template in a temp folder, and the config
folder is a temp one, so a run on the owner's own PC cannot read or write the
owner's real state.
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

# Hermetic before any shipped module reads a config: the owner's real
# ~/.openjarvis must never decide what this suite sees (run_suites.py sets
# these too; a direct run does not, so the suite sets them itself).
TMP = Path(tempfile.mkdtemp(prefix="jarvis-tool-defaults-"))
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

#: The shipped default list, in the order the template names it. Pinned
#: exactly: the template's own comments explain the first three in that order,
#: so appending is the change that keeps those comments true; the SET is what
#: a fresh install is offered.
DEFAULT_ENABLED = ["web_search", "change_setting", "feature_guide",
                   "calculator", "memory_search", "my_files"]

#: What a fresh PC (no folder listed) is offered, in `jarvis_agent.TOOLS`
#: order - `offered_tools` returns TOOLS order, never the file's order.
OFFERED_NO_FOLDER = ["calculator", "memory_search", "web_search",
                     "change_setting", "feature_guide"]

#: What a PC with at least one folder listed is offered: my_files joins it.
OFFERED_WITH_FOLDER = ["calculator", "memory_search", "web_search",
                       "my_files", "change_setting", "feature_guide"]

#: Every tool that reaches off this PC, another program, an account or a file
#: must stay OUT of the shipped list: a fresh install reads nothing and
#: controls nothing. (The calculator, memory search and my_files only became
#: defaults because each one stays local and narrow - see the template.)
FORBIDDEN = (
    "control_computer", "control_phone", "browser_control", "propose_plan",
    "send_email", "draft_email", "tidy_inbox", "read_web_page",
    "email_check", "shell_exec", "file_read", "run_data_script",
    "rea_investigate", "calendar_read", "notes_search", "home_read",
    "home_control", "my_spending", "retirement_whatif",
)

TEMPLATE = REPO / "backend" / "rebuilt" / "jarvis-framework.toml"
BASE = REPO / "jarvis-backend" / "jarvis-framework.toml"
DOCS_MD = REPO / "docs" / "JARVIS-API.md"

PASSED, FAILED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    SKIPPED.append(why)
    print(f"skip  {why}")


def _enabled_in(path: Path):
    """`[tools].enabled` from one template, or None when no parser exists."""
    if tomllib is None:
        return None
    return tomllib.loads(path.read_text(encoding="utf-8"))["tools"]["enabled"]


# --------------------------------------------------------------------------
#   1. the two shipped templates and the list itself
# --------------------------------------------------------------------------

def t_both_shipped_templates_name_the_same_defaults():
    if tomllib is None:
        skip("no tomllib/tomli (Python < 3.11), so the templates could not be "
             "parsed - this suite did NOT verify the default list")
        return
    check("the repository's template exists", TEMPLATE.is_file(), str(TEMPLATE))
    check("the published base's copy exists", BASE.is_file(), str(BASE))
    text = TEMPLATE.read_text(encoding="utf-8")
    check("the twins are byte-identical (the two-file rule)",
          BASE.read_text(encoding="utf-8") == text)
    for path in (TEMPLATE, BASE):
        enabled = _enabled_in(path)
        check(f"`[tools].enabled` in {path.parent.name}/{path.name} is the "
              f"pinned default list", enabled == DEFAULT_ENABLED, enabled)
        check(f"...no duplicate tool names ({path.parent.name})",
              len(enabled) == len(set(enabled)), enabled)
        missing = [n for n in enabled if n not in AG.TOOLS]
        check(f"...every name is a real tool ({path.parent.name})",
              missing == [], missing)
    check("...and the list is written on ONE line: the app's own tool switch "
          "refuses an array split over several lines (JARVIS-API.md 43.3)",
          re.search(r"^enabled = \[[^\n]*\]$", text, re.M) is not None)


# --------------------------------------------------------------------------
#   2. what a fresh install is actually offered
# --------------------------------------------------------------------------

def t_a_fresh_install_offers_the_defaults():
    if tomllib is None:
        skip("no tomllib/tomli, so the template could not be read")
        return
    settings = TMP / "jarvis-framework.toml"
    settings.write_text(TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")
    old = os.environ.get("JARVIS_FRAMEWORK_TOML")
    os.environ["JARVIS_FRAMEWORK_TOML"] = str(settings)
    try:
        enabled = AG.enabled_tools_for_turn()
        check("a fresh install's turn reads the six-name enabled set",
              enabled == set(DEFAULT_ENABLED), enabled)
        offered = AG.offered_tools(enabled)
        check("...and the model is offered calculator, memory_search and the "
              "three tools that were already offered, in TOOLS order",
              offered == OFFERED_NO_FOLDER, offered)
        check("...with my_files NOT offered while no folder is listed",
              "my_files" not in offered, offered)
        check("...but my_files IS in the enabled set: the missing folder is the "
              "only thing keeping it out", "my_files" in enabled, enabled)
    finally:
        if old is None:
            os.environ.pop("JARVIS_FRAMEWORK_TOML", None)
        else:
            os.environ["JARVIS_FRAMEWORK_TOML"] = old


def t_my_files_is_hidden_until_a_folder_is_listed():
    real = JD.folders
    try:
        JD.folders = lambda: []
        check("no folder listed: my_files is not offered",
              "my_files" not in AG.offered_tools(set(DEFAULT_ENABLED)))
        JD.folders = lambda: [{"path": str(TMP), "added": 1.0}]
        offered = AG.offered_tools(set(DEFAULT_ENABLED))
        check("a folder listed: my_files is offered", "my_files" in offered, offered)
        check("...and the whole offered list is the expected one",
              offered == OFFERED_WITH_FOLDER, offered)
    finally:
        JD.folders = real


# --------------------------------------------------------------------------
#   3. nothing that reaches out, controls, or reads mail is on by default
# --------------------------------------------------------------------------

def t_no_control_browser_or_mail_tool_ships_on():
    on = set(DEFAULT_ENABLED)
    check("no control, browser, mail or other reaching tool is in the shipped "
          "default list", on.isdisjoint(FORBIDDEN), sorted(on & set(FORBIDDEN)))
    offered = set(AG.offered_tools(on))
    check("...and none of them is offered by a fresh install",
          offered.isdisjoint(FORBIDDEN), sorted(offered & set(FORBIDDEN)))
    check("...their tools still exist, so this list is the only thing keeping "
          "them off (their own switches still decide)",
          all(n in AG.TOOLS for n in FORBIDDEN),
          [n for n in FORBIDDEN if n not in AG.TOOLS])


# --------------------------------------------------------------------------
#   4. the docs say the same as the template
# --------------------------------------------------------------------------

def t_the_docs_say_the_same_as_the_template():
    text = DOCS_MD.read_text(encoding="utf-8")
    section = text.split("## 149.", 1)[1][:14000] if "## 149." in text else ""
    flat = re.sub(r"\s+", " ", section)
    check("JARVIS-API.md section 149 is there", bool(section))
    check("it names the shipped default list, all six, in order",
          "`web_search`, `change_setting`, `feature_guide`, `calculator`, "
          "`memory_search` and `my_files`" in flat, flat[:240])
    check("it says the shipped template now lists them",
          "shipped template now lists" in flat)
    check("it still names the folder requirement",
          "at least one folder in \"Folders Jarvis may look in\"" in flat)
    check("it says offered_tools omits my_files with no folder, and why",
          "omits `my_files` entirely" in flat
          and "that omission is on purpose" in flat)
    old = ("the shipped template lists only `web_search`, `change_setting` "
           "and `feature_guide`")
    check("the old, now-false sentence is gone", old not in flat)
    whole = re.sub(r"\s+", " ", text)
    check("no other line in JARVIS-API.md still says only web_search ships on",
          "like every tool but `web_search`" not in whole
          and "the one tool on by default" not in whole)


if __name__ == "__main__":
    for fn in (t_both_shipped_templates_name_the_same_defaults,
               t_a_fresh_install_offers_the_defaults,
               t_my_files_is_hidden_until_a_folder_is_listed,
               t_no_control_browser_or_mail_tool_ships_on,
               t_the_docs_say_the_same_as_the_template):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed, {len(SKIPPED)} skipped")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
