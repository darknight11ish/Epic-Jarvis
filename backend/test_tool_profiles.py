"""jarvis_tool_profiles.py: one truthful dossier per tool, and no invented ability.

    py -3 -B backend/test_tool_profiles.py

WHAT THIS SUITE PROVES, AND WHY EACH HALF EXISTS

  1. COVERAGE. Every name in the REAL `jarvis_agent.TOOLS` dict has exactly one
     profile, no profile exists that is not a real tool, and the capability
     families between them own every tool exactly once. The tool names are read
     by importing `jarvis_agent` itself - not by re-typing a list here, because a
     re-typed list is the thing that goes stale.

  2. SHAPE. Required keys, non-empty fields, the plain-words minimums (at least
     two `gives`, a `what` of at least 60 characters) and that every `sources`
     path really exists. The minimums are deliberately loose: they are there to
     catch an empty or truncated profile, not to freeze a sentence.

  3. TRUTH, AGAINST THE REAL SOURCES. This is the half that matters. A profile
     that invents an ability is worse than no profile at all, so:
       * every `tier` is re-derived from the SHIPPED config path - the
         `[tools].enabled` list in backend/rebuilt/jarvis-framework.toml,
         `jarvis_asks_first.TIER_A/TIER_B` (the in-app switches) and each
         module's own switch - and must equal what the profile claims;
       * every `off-by-default` tool must really be absent from the shipped
         tool list AND its own switch must really ship off (`[rea] enabled =
         false`, and the sandbox switch is OFF with no settings file);
       * every `combines` name is a real tool, never itself;
       * the load-bearing `touches` claims are checked in the module that would
         have to do the touching: REA's `HARD_DENY` really refuses live process
         capture, `shell_exec` really runs a subprocess, the sandbox really
         imports no network module, and the screen/phone tools really read the
         accessibility tree and really send adb commands.

  4. BEHAVIOUR. The six phrasings the owner is expected to use are answered,
     an unrelated question is NOT answered (None, so the model answers instead),
     and `context_for` never exceeds its character cap for any name.

WHAT THIS SUITE DOES NOT CLAIM. `tier` describes the SHIPPED state of a fresh
install, not this particular PC: on the owner's machine the sandbox switch is
already on, and the profile says "off until you turn on its own switch", which
is true of the shipped state and honest about the switch existing. The runtime
approval decision is made by `jarvis_gate.py`, which is NOT in this repository
(the owner's live backend holds it), so no check here claims a card was raised.
"""
from __future__ import annotations

import ast
import os
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent

# The same two paths every suite here uses: the backend's own modules, and the
# ten the repository ships whole from backend/rebuilt/ (flattened beside them by
# apply-patches.ps1 and by run_suites.py).
sys.path.insert(0, str(HERE / "rebuilt"))
sys.path.insert(0, str(HERE))

import jarvis_agent as A                # noqa: E402 - after sys.path
import jarvis_asks_first as AF          # noqa: E402 - after sys.path
import jarvis_tool_profiles as T        # noqa: E402 - after sys.path

PASSED, FAILED = [], []
TOML = HERE / "rebuilt" / "jarvis-framework.toml"

#: The two tools whose own module switch - not a line in `[tools].enabled` -
#: decides whether they are offered at all. Everything else off by default is
#: simply absent from the shipped list.
OWN_SWITCH_TOOLS = {"run_data_script", "rea_investigate"}


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


# --------------------------------------------------------------------------
#   Reading the real sources
# --------------------------------------------------------------------------
def shipped_config() -> dict:
    """The settings file a fresh install starts from, parsed as TOML."""
    import tomllib
    with open(TOML, "rb") as fh:
        return tomllib.load(fh)


def shipped_tools() -> set:
    return {str(n) for n in shipped_config()["tools"]["enabled"]}


def expected_tier(name: str, shipped: set) -> str:
    """The tier the SHIPPED config path really puts this tool in.

    The order is the decision order: a tool that is already in the shipped list
    needs no action, a tool with its own module switch is governed by that
    switch before anything else, then the in-app switches, then the rest."""
    if name in shipped or name in A.GRANT_ASK_TOOLS:
        return "always-available"
    if name in OWN_SWITCH_TOOLS:
        return "off-by-default"
    if name in AF.TOOLS_SWITCHABLE:
        return "switchable"
    return "settings-file"


def tree_for(rel: str) -> ast.Module:
    """Parse one repository file. Never kept as module-level source text, so
    this suite adds no source pin (tools/check_no_source_pins.py)."""
    return ast.parse((REPO / rel).read_text(encoding="utf-8"))


def string_set(tree: ast.Module, name: str):
    """The strings in `NAME = {...}` / `STATE = frozenset({...})`, or None."""
    for node in tree.body:
        targets = []
        if isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target.id]
        if name not in targets:
            continue
        value = node.value
        if isinstance(value, ast.Call) and value.args:
            value = value.args[0]
        if isinstance(value, ast.Set):
            elts = value.elts
        elif isinstance(value, (ast.Tuple, ast.List)):
            elts = value.elts
        else:
            return None
        return {e.value for e in elts
                if isinstance(e, ast.Constant) and isinstance(e.value, str)}
    return None


def touch_tokens(word: str) -> list:
    """`files, phone` -> ["files", "phone"]; the module's own small vocabulary."""
    return [part.strip() for part in str(word).split(",") if part.strip()]


def function_named(tree: ast.Module, name: str):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def imports_in(node) -> set:
    """Every module named by an import inside this node."""
    found = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Import):
            found.update(alias.name.split(".")[0] for alias in sub.names)
        elif isinstance(sub, ast.ImportFrom) and sub.module:
            found.add(sub.module.split(".")[0])
    return found


def calls_subprocess_shell(func) -> bool:
    """Does this function really run `subprocess.run(..., shell=True, ...)`?"""
    for node in ast.walk(func):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        owner = node.func.value
        if not (isinstance(owner, ast.Name) and owner.id == "subprocess"
                and node.func.attr == "run"):
            continue
        for kw in node.keywords:
            if (kw.arg == "shell" and isinstance(kw.value, ast.Constant)
                    and kw.value.value is True):
                return True
    return False


def sandbox_ships_off() -> tuple:
    """Call the sandbox's own switch with an empty config folder.

    The shipped default is what a fresh install has: no sandbox.json at all. The
    module resolves its folder from the environment, so the owner's real state is
    never read and never changed."""
    import jarvis_sandbox_exec as S
    saved = {k: os.environ.get(k)
             for k in ("OPENJARVIS_CONFIG_DIR", "JARVIS_CONFIG_DIR")}
    folder = tempfile.mkdtemp(prefix="toolprofiles-sandbox-")
    try:
        os.environ.pop("OPENJARVIS_CONFIG_DIR", None)
        os.environ["JARVIS_CONFIG_DIR"] = folder
        return (S.enabled() is False), S.settings()
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


# --------------------------------------------------------------------------
#   1. Coverage
# --------------------------------------------------------------------------
def t_coverage_against_the_real_tool_dict():
    real = list(A.TOOLS)
    check("the real jarvis_agent.TOOLS was read, not a re-typed list",
          len(real) >= 40, f"only {len(real)} tools came back from jarvis_agent")
    profiles = set(T.PROFILES)
    check("every real tool has exactly one profile",
          set(real) <= profiles, f"missing: {sorted(set(real) - profiles)}")
    check("no profile exists that is not a real tool",
          profiles <= set(real), f"extra: {sorted(profiles - set(real))}")
    check("the number of profiles equals the number of tools",
          len(T.PROFILES) == len(real),
          f"{len(T.PROFILES)} profiles vs {len(real)} tools")
    wrong = [n for n, p in T.PROFILES.items() if p.get("id") != n]
    check("each profile's own id matches its key", not wrong, str(wrong))
    print(f"       ({len(real)} tools, {len(T.FAMILIES)} families)")


def t_families_own_every_tool_once():
    check("no family id is also a tool id",
          not (set(T.FAMILIES) & set(T.PROFILES)),
          str(sorted(set(T.FAMILIES) & set(T.PROFILES))))
    check("there are 8 to 12 families", 8 <= len(T.FAMILIES) <= 12,
          f"{len(T.FAMILIES)}")
    owned = [tool for family in T.FAMILIES.values() for tool in family["tools"]]
    dupes = sorted({tool for tool in owned if owned.count(tool) > 1})
    check("no tool is claimed by two families", not dupes, str(dupes))
    check("every real tool is owned by exactly one family",
          set(owned) == set(A.TOOLS),
          f"unowned: {sorted(set(A.TOOLS) - set(owned))}; "
          f"unknown: {sorted(set(owned) - set(A.TOOLS))}")
    check("the families name only real tools",
          set(owned) <= set(A.TOOLS),
          str(sorted(set(owned) - set(A.TOOLS))))
    for family_id, family in T.FAMILIES.items():
        check(f"family {family_id} has a title, what, impact and 1-3 limits",
              bool(family.get("title")) and len(str(family.get("what", ""))) >= 60
              and len(str(family.get("impact", ""))) >= 200
              and 1 <= len(family.get("limits") or []) <= 3,
              f"what={len(str(family.get('what', '')))} "
              f"impact={len(str(family.get('impact', '')))} "
              f"limits={len(family.get('limits') or [])}")


def t_names_and_profile():
    expected = sorted(list(T.PROFILES) + list(T.FAMILIES))
    check("names() lists every tool id and family id, sorted",
          T.names() == expected, f"{T.names()[:5]}...")
    check("profile() answers a real tool", T.profile("calculator") is
          T.PROFILES["calculator"])
    check("profile() answers a family", T.profile("files") is T.FAMILIES["files"])
    check("profile() answers None for a name that is neither",
          T.profile("no_such_tool") is None and T.profile(None) is None)


# --------------------------------------------------------------------------
#   2. Shape
# --------------------------------------------------------------------------
REQUIRED = ("id", "title", "what", "gives", "touches", "limits", "combines",
            "tier", "enable_hint", "sources")


def t_profile_shape():
    problems = []
    for name, p in T.PROFILES.items():
        missing = [k for k in REQUIRED if k not in p]
        if missing:
            problems.append(f"{name}: missing {missing}")
            continue
        if len(str(p["what"])) < 60:
            problems.append(f"{name}: what is {len(str(p['what']))} chars")
        if not 2 <= len(p["gives"]) <= 6:
            problems.append(f"{name}: {len(p['gives'])} gives")
        if not 1 <= len(p["limits"]) <= 4:
            problems.append(f"{name}: {len(p['limits'])} limits")
        if not 0 <= len(p["combines"]) <= 3:
            problems.append(f"{name}: {len(p['combines'])} combines")
        if p["tier"] not in T.TIER_VALUES:
            problems.append(f"{name}: tier {p['tier']!r}")
        tokens = touch_tokens(p["touches"])
        if not tokens or any(t not in T.ALLOWED_TOUCH for t in tokens):
            problems.append(f"{name}: touches {p['touches']!r}")
        elif "none" in tokens and len(tokens) > 1:
            problems.append(f"{name}: 'none' alongside {tokens}")
        if len(str(p["enable_hint"])) < 20:
            problems.append(f"{name}: enable_hint too short")
        if not p["sources"]:
            problems.append(f"{name}: no sources")
        for word in list(p["gives"]) + list(p["limits"]):
            if not isinstance(word, str) or len(word.strip()) < 15:
                problems.append(f"{name}: thin list item {word!r}")
    check("every profile has the required keys and usable, non-empty fields",
          not problems, "\n        ".join(problems[:12]))


def t_sources_exist_and_name_the_tool_dict():
    missing, no_agent = [], []
    for name, p in T.PROFILES.items():
        for rel in p["sources"]:
            if not (REPO / rel).is_file():
                missing.append(f"{name}: {rel}")
        if "backend/jarvis_agent.py" not in p["sources"]:
            no_agent.append(name)
    check("every source path in every profile really exists",
          not missing, "\n        ".join(missing[:12]))
    check("every profile cites the file that declares the tool",
          not no_agent, str(no_agent))


def t_combines_are_real_tools():
    bad, alone = [], []
    for name, p in T.PROFILES.items():
        for other, why in p["combines"].items():
            if other not in A.TOOLS:
                bad.append(f"{name} -> {other}")
            if other == name:
                bad.append(f"{name} combines with itself")
            if not isinstance(why, str) or len(why.strip()) < 20:
                bad.append(f"{name} -> {other}: no sentence")
        if not p["combines"]:
            if not any("alone" in line for line in p["limits"]):
                alone.append(name)
    check("every name in `combines` is another real tool, with a real sentence",
          not bad, "\n        ".join(bad[:12]))
    check("a tool with no combination says so in its limits",
          not alone, str(alone))


# --------------------------------------------------------------------------
#   3. Truth, against the real sources
# --------------------------------------------------------------------------
def t_tiers_agree_with_the_shipped_switch():
    shipped = shipped_tools()
    wrong = []
    for name, p in T.PROFILES.items():
        want = expected_tier(name, shipped)
        if p["tier"] != want:
            wrong.append(f"{name}: says {p['tier']!r}, shipped path says {want!r}")
    check("every tier agrees with the shipped config path and the asks-first tiers",
          not wrong, "\n        ".join(wrong))
    claimed = {p["tier"] for p in T.PROFILES.values()}
    # 2026-11-04, main's 71d4d6a01: every tool the model can be offered now has
    # an in-app switch (jarvis_asks_first.TOOLS_SWITCHABLE, 49 of them, all but
    # NOT_A_SWITCH's three), so no tool's only way in is a name typed into the
    # settings file any more. `settings-file` is therefore a real state with
    # nothing in it. It is named HERE, rather than the check being dropped, so
    # that a tool which genuinely needs the file again fails this line and gets
    # its own sentence, instead of coming back silently while a reader is still
    # told the state exists.
    check("every tier value is used except settings-file, which no tool needs now",
          claimed == set(T.TIER_VALUES) - {"settings-file"}, f"{sorted(claimed)}")


def t_always_available_really_is():
    shipped = shipped_tools()
    bad = []
    for name, p in T.PROFILES.items():
        if p["tier"] != "always-available":
            continue
        if name in shipped:
            continue
        if name in A.GRANT_ASK_TOOLS and "web_search" in shipped:
            continue            # offered whenever web search is (jarvis_agent)
        bad.append(name)
    check("every always-available tool is in the shipped list, or rides with one",
          not bad, str(bad))
    check("the two search-approval tools ride with web search, not a switch",
          A.GRANT_ASK_TOOLS == ("approve_web_search_for_conversation",
                                "stop_web_search_approval")
          and not (set(A.GRANT_ASK_TOOLS) & set(AF.TOOLS_SWITCHABLE)),
          str(A.GRANT_ASK_TOOLS))


def t_switchable_matches_the_in_app_switches():
    shipped = shipped_tools()
    switchable = {n for n, p in T.PROFILES.items() if p["tier"] == "switchable"}
    check("every switchable profile is a real in-app switch (TIER_A or TIER_B)",
          switchable <= set(AF.TOOLS_SWITCHABLE),
          f"claimed but not switchable: {sorted(switchable - set(AF.TOOLS_SWITCHABLE))}")
    # The equivalence this line used to assert - "every in-app switch is a
    # `switchable` profile" - is the half main's 71d4d6a01 made FALSE, and it is
    # false in the DATA, not merely awkward here: 13 of the 48 switchable tools
    # are already ON in the shipped [tools].enabled list, so the decision order
    # above (and the truth) gives them `always-available` - no action needed, and
    # the page can still switch them OFF - and `rea_investigate` is
    # `off-by-default` because its own `[rea] enabled` ships false and outranks
    # the tool list. Holding the old shape would force 14 profiles to state
    # something untrue, which is the one thing this suite exists to stop.
    #
    # What is a real bug - and was exactly the bug on this branch, 13 profiles
    # claiming "no in-app switch" - is a switchable tool whose profile can only
    # say "there is no switch". So the check now asserts the three answers are
    # EXHAUSTIVE: every in-app switch is either off until you turn it on, or
    # already on, or gated by its own module switch. Each of those is a true
    # sentence for the tools that hold it, and a profile that says "no in-app
    # switch" for a switchable tool falls out of all three. It reads the TIER,
    # never the shipped list, so a wrong tier cannot hide behind the list.
    already_on = {n for n, p in T.PROFILES.items() if p["tier"] == "always-available"}
    own_switch = {n for n, p in T.PROFILES.items() if p["tier"] == "off-by-default"}
    check("every in-app switch is off until switched, already on, or own-switch gated",
          set(AF.TOOLS_SWITCHABLE) <= (switchable | already_on | own_switch),
          f"neither, and so claimed to have no switch: "
          f"{sorted(set(AF.TOOLS_SWITCHABLE) - (switchable | already_on | own_switch))}")
    check("no switchable tool is already on in the shipped list",
          not (switchable & shipped), str(sorted(switchable & shipped)))


def t_settings_file_really_is():
    shipped = shipped_tools()
    bad = []
    for name, p in T.PROFILES.items():
        if p["tier"] != "settings-file":
            continue
        if name in shipped or name in AF.TOOLS_SWITCHABLE or name in OWN_SWITCH_TOOLS:
            bad.append(name)
    check("every settings-file tool is absent from the shipped list and has no "
          "in-app switch", not bad, str(bad))


def t_off_by_default_really_ships_off():
    shipped = shipped_tools()
    config = shipped_config()
    rea = [n for n, p in T.PROFILES.items() if p["tier"] == "off-by-default"]
    check("exactly the two own-switch tools claim off-by-default",
          set(rea) == OWN_SWITCH_TOOLS, str(sorted(rea)))
    check("neither off-by-default tool is in the shipped [tools].enabled list",
          not (set(rea) & shipped), str(sorted(set(rea) & shipped)))
    check("the REA module's own switch really ships false ([rea] enabled)",
          config.get("rea", {}).get("enabled") is False,
          str(config.get("rea")))
    ok, settings = sandbox_ships_off()
    check("the data sandbox's own switch is OFF with no settings file",
          ok, str(settings))


def t_rea_matches_its_own_hard_deny():
    tree = tree_for("backend/jarvis_rea.py")
    hard_deny = string_set(tree, "HARD_DENY")
    allowed = string_set(tree, "ALLOWED_CALL_TOOLS")
    check("jarvis_rea.HARD_DENY is really readable as a set of tool names",
          bool(hard_deny), str(hard_deny))
    mutators = {"install_adb_package", "uninstall_adb_package", "push_adb_file",
                "start_adb_app", "start_adb_activity", "stop_adb_app"}
    check("the hard deny is exactly the six phone-mutating commands - the owner's "
          "full-toolbox decision keeps every read and every capture",
          (hard_deny or set()) == mutators, str(sorted(hard_deny or set())))
    check("no hard-denied tool can ever be sent",
          not ((hard_deny or set()) & (allowed or set())),
          f"also allowed: {sorted((hard_deny or set()) & (allowed or set()))}")
    live = {"capture_process_scenario", "capture_browser_scenario",
            "capture_electron_scenario", "capture_native_ui_scenario"}
    literals = {node.value for node in ast.walk(tree)
                if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    check("the four live-capture tools are ordinary card-gated actions, not a "
          "denied lane",
          not (live & (hard_deny or set())) and live <= literals,
          f"missing: {sorted(live - literals)}")
    rea = T.PROFILES["rea_investigate"]
    check("the REA profile claims files AND processes, because live capture is "
          "allowed behind its cards",
          "files" in rea["touches"] and "process" in rea["touches"],
          rea["touches"])
    check("... and says plainly what the module still refuses",
          any("refuses by name" in line.lower() for line in rea["limits"]),
          str(rea["limits"]))


def t_touches_match_the_modules():
    # control_computer reads another program's accessibility tree.
    ui = tree_for("backend/jarvis_ui_control.py")
    ui_doc = (ast.get_docstring(ui) or "").lower()
    check("control_computer touches the screen, and says so",
          "screen" in T.PROFILES["control_computer"]["touches"])
    check("jarvis_ui_control really reads the accessibility tree",
          "accessibility" in ui_doc and function_named(ui, "plan") is not None
          and function_named(ui, "run") is not None)

    # control_phone sends individual adb commands.
    android = tree_for("backend/jarvis_android_control.py")
    android_doc = (ast.get_docstring(android) or "").lower()
    check("control_phone touches the phone, and says so",
          "phone" in T.PROFILES["control_phone"]["touches"])
    check("jarvis_android_control really drives the phone with adb",
          "adb" in android_doc and function_named(android, "plan") is not None)

    # shell_exec really runs a subprocess (so "process" is not a guess).
    agent = tree_for("backend/jarvis_agent.py")
    runner = function_named(agent, "_run_shell_exec")
    check("shell_exec touches a process, and the code really starts one",
          "process" in T.PROFILES["shell_exec"]["touches"]
          and runner is not None and calls_subprocess_shell(runner))

    # The sandbox: files only, and the child really cannot reach the network.
    # The proof is the module's own import allow-list, not the imports of the
    # module itself (which uses urllib.parse to read a URL in an error sentence
    # and opens no socket doing it).
    sandbox = tree_for("backend/jarvis_sandbox_exec.py")
    allowed = string_set(sandbox, "ALLOWED_IMPORTS")
    check("run_data_script claims files only",
          touch_tokens(T.PROFILES["run_data_script"]["touches"]) == ["files"])
    check("jarvis_sandbox_exec really has an import allow-list",
          bool(allowed), str(allowed))
    check("... and that allow-list keeps the nine documented modules",
          {"math", "statistics", "decimal", "fractions", "datetime",
           "collections", "itertools", "re", "json", "csv"} <= (allowed or set()),
          str(sorted((allowed or set())))
          )
    check("... and it refuses every way of reaching the network",
          not ({"socket", "urllib", "http", "requests", "httpx", "asyncio"}
               & (allowed or set())),
          str(sorted({"socket", "urllib", "http", "requests", "httpx", "asyncio"}
                     & (allowed or set()))))
    check("jarvis_sandbox_exec really exposes the one entry point the tool names",
          function_named(sandbox, "run_data_script") is not None)

    # Memory: the claim is that memory_search reads the memory store.
    mem = function_named(agent, "_run_memory_search")
    check("memory_search claims the memory store, and really imports it",
          T.PROFILES["memory_search"]["touches"] == "memory"
          and mem is not None and "jarvis_memory" in imports_in(mem))

    # A read-only tool must not claim to write.
    for name in ("calendar_read", "email_check", "notes_search", "home_read",
                 "conversation_find", "conversation_open", "goals_list",
                 "coming_up", "plugin_list", "feature_guide"):
        text = " ".join(T.PROFILES[name]["limits"]).lower()
        check(f"{name} says plainly that it only reads",
              "read-only" in text or "read only" in text or "never writes" in text
              or "changes nothing" in text or "never marks" in text)


def t_the_numbers_in_the_profiles_match_the_code():
    """A number in a dossier is a claim like any other, so it is measured here.

    The feature guide's own module docstring says 140 rows; the catalogue this
    tree actually ships holds 175 in nine groups. A docstring is not the
    catalogue, so the profile states the measured count and this check keeps it
    honest as features are added."""
    import jarvis_feature_catalogue as C
    rows, groups = len(C.FEATURES), len(C.GROUPS)
    text = T.PROFILES["feature_guide"]["what"]
    check(f"the feature guide's row count is the catalogue's real one ({rows})",
          str(rows) in text, f"{rows} rows in the catalogue; profile says: {text}")
    check(f"... and its group count is the real one ({groups})",
          str(groups) in text, text)
    counts = T.PROFILES["setup_quiz"]["what"]
    import jarvis_setup as SU
    questions = len(SU.QUESTIONS) if hasattr(SU, "QUESTIONS") else None
    check("the setup quiz's question count is the real one",
          questions is not None and str(questions) in counts,
          f"{questions} questions; profile says: {counts}")


def t_no_profile_claims_an_ungated_way_out():
    """Anything that reaches off this PC or runs a program must say it is carded."""
    carded = {"shell_exec", "control_computer", "control_phone", "browser_control",
              "send_email", "draft_email", "tidy_inbox", "read_web_page",
              "github_search", "send_file_to_phone", "connect_account",
              "home_control", "propose_plan", "rea_investigate"}
    bad = []
    for name in carded:
        text = " ".join(T.PROFILES[name]["limits"]).lower()
        if not any(word in text for word in ("card", "ask", "approv", "person's yes")):
            bad.append(name)
    check("every tool that leaves the PC or runs code says it is carded",
          not bad, str(bad))


# --------------------------------------------------------------------------
#   4. Behaviour
# --------------------------------------------------------------------------
PHRASINGS = (
    ("tell me about the github tool", "github_search"),
    ("what can the screen tool do", "control_computer"),
    ("how does rea_investigate change what you can do", "rea_investigate"),
    ("what is reverse engineering", "rea_investigate"),
    ("how does github help you", "github_search"),
    ("what would you use screen control for", "control_computer"),
)


def t_answer_about_the_expected_phrasings():
    for question, tool in PHRASINGS:
        answer = T.answer_about(question)
        ok = isinstance(answer, str) and tool in answer and len(answer) > 200
        check(f"answer_about({question!r}) answers about {tool}", ok,
              repr(answer)[:200])
        block = T.context_for(question)
        check(f"context_for({question!r}) gives a block naming {tool}",
              isinstance(block, str) and tool in block, repr(block)[:200])


def t_answer_about_the_document_question():
    answer = T.answer_about("which tools work together for a document")
    check("'which tools work together for a document' is answered as the files family",
          isinstance(answer, str) and T.FAMILIES["files"]["title"] in answer,
          repr(answer)[:200])
    named = [t for t in T.FAMILIES["files"]["tools"] if t in (answer or "")]
    check("... and the answer actually names the tools that work together",
          len(named) >= 2, str(named))
    check("the same question produces the same answer twice (deterministic)",
          T.answer_about("which tools work together for a document") == answer)


def t_no_tool_named_means_no_answer():
    for question in ("what's the weather like today",
                     "can you write me a poem about the sea",
                     "how tall is mount everest", ""):
        check(f"answer_about({question!r}) returns None, so the model answers",
              T.answer_about(question) is None)
        check(f"context_for({question!r}) returns None",
              T.context_for(question) is None)
    check("answer_about(None) returns None, it does not crash",
          T.answer_about(None) is None)


def t_context_blocks_stay_inside_the_cap():
    over, empty, missing = [], [], []
    for name in T.names():
        block = T.context_for(name)
        if block is None:
            empty.append(name)
            continue
        if len(block) > T.CONTEXT_LIMIT:
            over.append(f"{name}: {len(block)}")
        kinds = T.PROFILES.get(name) or T.FAMILIES.get(name)
        if not any(str(s).split("/")[-1] in block
                   for s in kinds.get("sources") or []):
            if name in T.PROFILES:
                missing.append(name)
    check("every tool and family has a context block", not empty, str(empty))
    check(f"no context block is over the {T.CONTEXT_LIMIT}-character cap",
          not over, str(over[:8]))
    check("every tool's context block cites at least one source file name",
          not missing, str(missing[:8]))


def t_context_block_carries_the_dossier():
    block = T.context_for("control_phone") or ""
    p = T.PROFILES["control_phone"]
    check("the context block carries the title and the id",
          p["title"] in block and "control_phone" in block)
    check("... the first real ability", p["gives"][0] in block)
    check("... a real limit", any(line in block for line in p["limits"]))
    check("... how to switch it on", p["enable_hint"].split(" - ")[0][:25] in block)
    check("... and a real combination",
          any(other in block for other in p["combines"]))


# --------------------------------------------------------------------------
def main():
    groups = (
        ("coverage", (t_coverage_against_the_real_tool_dict,
                      t_families_own_every_tool_once,
                      t_names_and_profile)),
        ("shape", (t_profile_shape, t_sources_exist_and_name_the_tool_dict,
                   t_combines_are_real_tools)),
        ("truth", (t_tiers_agree_with_the_shipped_switch,
                   t_always_available_really_is,
                   t_switchable_matches_the_in_app_switches,
                   t_settings_file_really_is,
                   t_off_by_default_really_ships_off,
                   t_rea_matches_its_own_hard_deny,
                   t_touches_match_the_modules,
                   t_the_numbers_in_the_profiles_match_the_code,
                   t_no_profile_claims_an_ungated_way_out)),
        ("behaviour", (t_answer_about_the_expected_phrasings,
                       t_answer_about_the_document_question,
                       t_no_tool_named_means_no_answer,
                       t_context_blocks_stay_inside_the_cap,
                       t_context_block_carries_the_dossier)),
    )
    for title, tests in groups:
        print(f"\n--- {title} ---")
        for fn in tests:
            try:
                fn()
            except Exception:
                FAILED.append(fn.__name__)
                traceback.print_exc()
    print(f"\nPASS {len(PASSED)}   FAIL {len(FAILED)}")
    print(f"tools: {len(T.PROFILES)}   families: {len(T.FAMILIES)}   "
          f"checks: {len(PASSED) + len(FAILED)}")
    if FAILED:
        print("FAILED:")
        for name in FAILED:
            print(f"  {name}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
