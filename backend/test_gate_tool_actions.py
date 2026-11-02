"""The four tools that reached the gate with no action, and every tool after them.

    python3 backend/test_gate_tool_actions.py

WHY THIS ONE EXISTS (2026-11-01)

`jarvis_agent.TOOLS` offered four tools that had NO entry in
`jarvis_gate._TOOL_ACTIONS`: `send_file_to_phone`, `protect_from_jarvis`,
`connect_account` and `rea_investigate`. `action_for_tool()` therefore answered
`unclassified_tool` for every one of them.

That is fail-SAFE - the name takes `unknown_action_tier`, which is "ask" as
shipped, so nothing ran unattended - and it is still wrong: the card the owner
was shown was never the one the tool raises, `jarvis_reach`'s "What can Jarvis
reach" page listed each of them as unclassified, and a card nobody can act on
is how a real card gets ignored. No patch in `backend/` named any of the four,
so no run of `apply-patches.ps1` could ever have added them.

WHY IT IS A NEW SUITE AND NOT A LINE IN test_agent.py

`test_agent.py`'s own `t_every_tool_resolves_to_a_real_jarvis_gate_action` is
the check that found this, and in CI it prints `skip`: it needs
`import jarvis_gate`, and `jarvis_gate.py` is the owner's file - it is not in
`backend/`, and a plain clone has nothing to import it from. The one check
written for this defect could therefore only ever fail at his own desk.

This suite asks the same question with NO import. It rebuilds the table an
install really gets, from the two halves that produce it:

  1. `jarvis-backend/jarvis_gate.py`, this repository's published copy of the
     gate. It is meant to be the state AFTER the patches, so it already holds
     every line the stack has added - commit `b908d7368` says so in as many
     words ("The base is meant to be the state after the patches"), and it is
     the file `tools/check_stale_twins.py` keeps in step. A clone that runs
     from the base gets its gate from here.
  2. the `+` lines of every patch `scripts/apply-patches.ps1` applies, read in
     that order through `_stack.order()`. This is the half that reaches the
     OWNER's own `jarvis_gate.py` on the next deploy, and a line only the base
     carries would never arrive there.

Both halves are checked, because they fail differently: the base alone would
leave his PC unfixed, and a patch alone would leave a fresh clone unfixed.
That is also why `gate-tool-actions-gap.patch` and the base carry the same
four lines.

WHAT IS CHECKED

  1. The four tools are still in `jarvis_agent.TOOLS` under those names. If a
     rename makes this suite stop looking at them, that is a red check - never
     a quiet pass over a name that no longer exists.
  2. EVERY tool's gate lookup name is a key of the rebuilt table: the base's
     `_TOOL_ACTIONS` plus every patch's added entries. This is the general
     form of the defect, so the next tool someone adds is caught too.
  3. The four lookup names are added by a PATCH, not only by the base, and each
     maps to the action it is meant to map to.
  4. Each of those actions is a real gate action: a tier word, or a key of the
     SHIPPED `[autonomy.tiers]` in `backend/rebuilt/jarvis-framework.toml`.
     That is the gate's own rule - a name with no tier line is answered as an
     unknown action by fall-through - so a typo or an invented name is caught
     here rather than on his PC.
  5. The BITE. The same two halves are rebuilt as they were BEFORE the fix -
     the base with those four lines taken out, and the patches without
     `gate-tool-actions-gap.patch` - and check 2 must report exactly those four
     tools missing. A check that cannot fail on the tree that had the defect
     proves nothing about the tree that fixed it.

THE ONE EXCEPTION, AND IT IS test_agent.py's OWN

`web_search` is put to the gate under `jarvis_search.ACTION_SEARCH`
("search_the_web"), never through `action_for_tool`, so `_TOOL_ACTIONS` is the
wrong place to look for it. Same skip, same reason, same two files.
"""
import ast
import re
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
# ...and the ten modules this repository ships WHOLE, from backend/rebuilt/ -
# the same two lines test_agent.py uses, so `import jarvis_agent` here reads the
# copy run_suites.py stages for every suite in CI.
sys.path.insert(0, str(HERE / "rebuilt"))
from _where import REPO  # noqa: E402

try:
    import tomllib
except ImportError:                                   # Python < 3.11
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None

#: The published base's gate. `jarvis_gate.py` is the owner's file and is not
#: in `backend/`, so this repository's copy of it is the only one CI has.
BASE_GATE = REPO / "jarvis-backend" / "jarvis_gate.py"
#: The shipped tier table, the same file the gate would load on a fresh install.
SHIPPED_TOML = HERE / "rebuilt" / "jarvis-framework.toml"
#: The patch this fix lives in. Named so the bite proof can take it back out.
FIX_PATCH = "gate-tool-actions-gap.patch"

#: The four tools this suite was written for, and the action each must land on.
#: The evidence for every one is in the patch's own comment, and here it is in
#: one line each:
#:   send_file_to_phone  jarvis_send_file.ACTION and jarvis_agent.SEND_FILE_ACTION
#:                       both name it, and "send_file_to_phone = ask" ships.
#:   protect_from_jarvis jarvis_agent.PROTECT_ACTION / jarvis_protection.ACTION_PROTECT
#:                       are protect_item, whose shipped tier is "ask".
#:   connect_account     intercepted before the gate (_connect_call), so the
#:                       entry states the conservative answer for the Reach page;
#:                       change_own_config is the existing action that owns "ask".
#:   rea_investigate     jarvis_rea.py starts a local MCP program, and
#:                       jarvis_protection.py names it beside shell_exec and
#:                       run_data_script; run_shell_on_host ships as "ask".
FIXED = {
    "send_file_to_phone": "send_file_to_phone",
    "protect_from_jarvis": "protect_item",
    "connect_account": "change_own_config",
    "rea_investigate": "run_shell_on_host",
}

#: The tools whose lookup name is deliberately NOT a `_TOOL_ACTIONS` key - the
#: same single exception test_agent.py skips, for the same reason.
NOT_VIA_THE_TABLE = {"web_search"}

TIER_WORDS = frozenset({"auto", "notify", "ask", "never"})

#: One `_TOOL_ACTIONS` line, as a patch ADDS it: `+    "name": "value",`.
_ADDED_ENTRY = re.compile(r'^\+\s*"([a-z][a-z0-9_]*)":\s*"([a-z][a-z0-9_]*)"\s*,?\s*$')

PASSED, FAILED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(name, why):
    """An honest SKIP: the thing this check needs is not here to check.

    Never a silent pass - a check that passes without looking is worse than no
    check at all, and CI is the whole point of this suite.
    """
    SKIPPED.append(name)
    print(f"SKIP {name}\n        {why}")


def _table_of(source: str, name: str):
    """The dict literal assigned to `name` in `source`, or None.

    Parsed, never regexed: these tables carry comments and one-line pairs, and
    a regex over them is how a suite ends up measuring its own draft.
    """
    for node in ast.parse(source).body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) \
                and node.target.id == name and isinstance(node.value, ast.Dict):
            return ast.literal_eval(node.value)
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict) \
                and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
    return None


def _order():
    """The patches apply-patches.ps1 applies, in its order (paths under backend/)."""
    try:
        import _stack
        return list(_stack.order())
    except Exception:                                  # noqa: BLE001
        # _stack reads apply-patches.ps1; without it, every patch in the folder
        # is the honest wider net - it can only find MORE lines, never fewer.
        return sorted(p.name for p in HERE.glob("*.patch"))


def _added_entries(order, exclude=()):
    """{lookup name: action} from the `+` lines of those patches."""
    found = {}
    for name in order:
        if name in exclude:
            continue
        path = HERE / name
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            m = _ADDED_ENTRY.match(line)
            if m:
                found[m.group(1)] = m.group(2)
    return found


def _strip_lines(source: str, names) -> str:
    """`source` with every `"name":` line for those names taken out.

    Used only by the bite proof, to rebuild the gate as it was before the fix.
    """
    keep = []
    for line in source.splitlines(True):
        stripped = line.strip()
        if any(stripped.startswith(f'"{n}":') for n in names):
            continue
        keep.append(line)
    return "".join(keep)


def _tools():
    """({tool name: lookup name}, why-not) from the backend's jarvis_agent.py."""
    try:
        import jarvis_agent as AG
    except Exception as exc:                           # noqa: BLE001
        return None, (f"jarvis_agent.py would not import here ({exc!r}), so the "
                      "tool list could not be read.")
    tools = getattr(AG, "TOOLS", None)
    if not isinstance(tools, dict) or not tools:
        return None, "jarvis_agent.py imported but has no TOOLS table"
    out = {}
    for tname, tool in tools.items():
        fn = getattr(tool, "gate_lookup_name", None)
        try:
            out[tname] = (fn({}) if fn else tname) or tname
        except Exception:                              # noqa: BLE001
            out[tname] = tname
    return out, ""


def _shipped_tiers():
    """The SHIPPED [autonomy.tiers] as {action: tier}, or (None, why-not)."""
    if tomllib is None:
        return None, "no tomllib/tomli in this Python, so the tier table could not be read"
    if not SHIPPED_TOML.is_file():
        return None, f"there is no {SHIPPED_TOML}"
    cfg = tomllib.loads(SHIPPED_TOML.read_text(encoding="utf-8"))
    return dict((cfg.get("autonomy") or {}).get("tiers") or {}), ""


def _missing(effective, lookups):
    """The tools whose gate lookup name is not a key of `effective`."""
    return sorted(t for t, lookup in lookups.items()
                  if t not in NOT_VIA_THE_TABLE and lookup not in effective)


# --------------------------------------------------------------------------
#   1. the four tools are still the four tools
# --------------------------------------------------------------------------


def t_the_four_tools_are_still_offered():
    lookups, why = _tools()
    if lookups is None:
        return skip("the four tools are still in jarvis_agent.TOOLS", why)
    check("the four tools this suite was written for are still in TOOLS",
          set(FIXED) <= set(lookups),
          f"not offered any more: {sorted(set(FIXED) - set(lookups))}. If one was "
          "renamed on purpose, rename it here too - do not let this suite stop "
          "looking at it.")
    # Their lookup name is the TOOL's own name (none of the four carries a
    # `gate_lookup_name` of its own). Pinned so a future `gate_lookup_name`
    # cannot move the entry this suite checks without this line changing too.
    moved = {t: lookups[t] for t in FIXED if t in lookups and lookups[t] != t}
    check("... and each is looked up under its own name (no gate_lookup_name)", not moved, moved)


# --------------------------------------------------------------------------
#   2. every tool resolves, in the table an install really gets
# --------------------------------------------------------------------------


def t_every_tool_resolves_in_the_table_an_install_gets():
    if not BASE_GATE.is_file():
        return skip("every tool resolves to a real gate action", f"there is no {BASE_GATE}")
    lookups, why = _tools()
    if lookups is None:
        return skip("every tool resolves to a real gate action", why)
    base = _table_of(BASE_GATE.read_text(encoding="utf-8"), "_TOOL_ACTIONS")
    if not base:
        check("the published gate's _TOOL_ACTIONS table could be read", False,
              f"{BASE_GATE} has no _TOOL_ACTIONS dict")
        return
    added = _added_entries(_order())
    effective = {**base, **added}
    check("the table was found, not an empty one by a broken parse",
          len(base) >= 100 and len(added) >= 20,
          f"{len(base)} entries in the base, {len(added)} added by patches")
    missing = _missing(effective, lookups)
    check("every tool jarvis_agent offers resolves to a real gate action, built "
          "the way an install builds it (base + every patch's added line)",
          not missing,
          "no _TOOL_ACTIONS entry, so action_for_tool() answers "
          "'unclassified_tool' and the card is never the one the tool raises. Add "
          "each to jarvis_gate._TOOL_ACTIONS in a patch AND to "
          "jarvis-backend/jarvis_gate.py:\n        " + "\n        ".join(missing))
    print(f"        ({len(lookups)} tools, {len(base)} base entries, "
          f"{len(added)} added by patches, {len(effective)} resolved)")


# --------------------------------------------------------------------------
#   3. the four come from a PATCH, so his own PC gets them
# --------------------------------------------------------------------------


def t_the_four_are_added_by_a_patch():
    order = _order()
    if FIX_PATCH not in order:
        return skip("the four are added by a patch the installer applies",
                    f"{FIX_PATCH} is not in apply-patches.ps1's list, so no run of "
                    "it reaches the owner's own jarvis_gate.py")
    added = _added_entries(order)
    absent = sorted(t for t in FIXED if t not in added)
    check("a patch the installer applies ADDS an entry for each of the four",
          not absent,
          "the base may carry it, but a fresh base never reaches the owner's own "
          "PC - only a patch does:\n        " + "\n        ".join(absent))
    wrong = {t: added[t] for t in FIXED if t in added and added[t] != FIXED[t]}
    check("... and each maps to the action it is meant to map to", not wrong,
          f"expected {FIXED}, found {wrong}")
    # Guard against a copy-paste that leaves "missing" meaningful only because a
    # variable was mistyped: the same question asked the other way round.
    twice = _duplicated_with_two_values(order)
    check("... and no _TOOL_ACTIONS line is added twice with two different "
          "actions (the LAST one wins in the gate)", not twice, twice)


def _duplicated_with_two_values(order):
    """{name: [values]} for a name some patch adds with more than one action."""
    seen = {}
    for name in order:
        path = HERE / name
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            m = _ADDED_ENTRY.match(line)
            if m:
                seen.setdefault(m.group(1), set()).add(m.group(2))
    return {k: sorted(v) for k, v in seen.items() if len(v) > 1}


# --------------------------------------------------------------------------
#   4. the actions are real gate actions
# --------------------------------------------------------------------------


def t_their_actions_are_real_gate_actions():
    tiers, why = _shipped_tiers()
    if tiers is None:
        return skip("the four actions are real gate actions", why)
    # The same rule the gate itself applies: a value that is a tier word is a
    # tier; anything else must be a name [autonomy.tiers] gives a tier, or it is
    # answered as an unknown action by fall-through.
    invented = {t: a for t, a in FIXED.items()
                if a not in TIER_WORDS and a not in tiers}
    check("each action the four map to is a tier word or a line in the shipped "
          "[autonomy.tiers]", not invented,
          f"a name with neither is answered as an unknown action on a setting the "
          f"owner can loosen: {invented}")
    for tool, action in sorted(FIXED.items()):
        if action in TIER_WORDS:
            continue
        check(f"{tool} -> {action}, and {action} ships as 'ask'",
              tiers.get(action) == "ask", tiers.get(action))


# --------------------------------------------------------------------------
#   5. the published base says the same thing as the patch
# --------------------------------------------------------------------------


def t_the_published_base_carries_the_same_four():
    if not BASE_GATE.is_file():
        return skip("the published base carries the same four", f"there is no {BASE_GATE}")
    base = _table_of(BASE_GATE.read_text(encoding="utf-8"), "_TOOL_ACTIONS")
    if not base:
        check("the published gate's _TOOL_ACTIONS table could be read", False,
              f"{BASE_GATE} has no _TOOL_ACTIONS dict")
        return
    # "The base is meant to be the state after the patches" (b908d7368). A patch
    # line the base does not carry is the exact drift that commit had to fix.
    absent = sorted(t for t in FIXED if t not in base)
    check("the published base's gate carries an entry for each of the four", not absent,
          "the base is meant to be the state AFTER the patches, so a line only the "
          "patch carries leaves every clone that runs from the base unfixed:\n        "
          + "\n        ".join(absent))
    wrong = {t: base[t] for t in FIXED if t in base and base[t] != FIXED[t]}
    check("... and the base and the patch agree on which action each maps to",
          not wrong, f"expected {FIXED}, the base says {wrong}")


# --------------------------------------------------------------------------
#   6. the bite: this suite fails on the tree that had the defect
# --------------------------------------------------------------------------


def t_it_bites_on_the_pre_fix_tree():
    """The check must fail on the tree BEFORE the fix, or it proves nothing.

    Both halves are put back the way they were on 2026-11-01: the base with the
    four `_TOOL_ACTIONS` lines taken out, and the patch list without
    `gate-tool-actions-gap.patch`. The same `_missing()` call must then report
    exactly those four tools - no more (it is not just failing generally) and no
    fewer (it really does see them).
    """
    if not BASE_GATE.is_file():
        return skip("the check bites on the pre-fix tree", f"there is no {BASE_GATE}")
    lookups, why = _tools()
    if lookups is None:
        return skip("the check bites on the pre-fix tree", why)
    order = _order()
    if FIX_PATCH not in order:
        return skip("the check bites on the pre-fix tree",
                    f"{FIX_PATCH} is not in the installer's list")
    stripped = _strip_lines(BASE_GATE.read_text(encoding="utf-8"), FIXED)
    before = _table_of(stripped, "_TOOL_ACTIONS")
    check("the bite proof really took the four lines out of the base",
          before is not None and not any(t in before for t in FIXED),
          f"still in the stripped base: "
          f"{[t for t in FIXED if before and t in before]}")
    if not before:
        return
    pre = {**before, **_added_entries(order, exclude=(FIX_PATCH,))}
    got = set(_missing(pre, lookups))
    check("the same check reports exactly the four tools on the pre-fix tree",
          got == set(FIXED), f"reported {sorted(got)}, expected {sorted(FIXED)}")
    # And the assertion is not vacuous in the other direction: the real tree
    # resolves them, so the two answers genuinely differ.
    real = {**(_table_of(BASE_GATE.read_text(encoding="utf-8"), "_TOOL_ACTIONS") or {}),
            **_added_entries(order)}
    check("... and the tree as it stands resolves all four, so the two answers "
          "differ", not set(_missing(real, lookups)) & set(FIXED),
          f"still unresolved on the real tree: "
          f"{sorted(set(_missing(real, lookups)) & set(FIXED))}")


def main():
    for fn in (t_the_four_tools_are_still_offered,
               t_every_tool_resolves_in_the_table_an_install_gets,
               t_the_four_are_added_by_a_patch,
               t_their_actions_are_real_gate_actions,
               t_the_published_base_carries_the_same_four,
               t_it_bites_on_the_pre_fix_tree):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    line = f"\n{len(PASSED)} passed, {len(FAILED)} failed"
    if SKIPPED:
        line += f", {len(SKIPPED)} skipped"
    print(line)
    if SKIPPED:
        print("skipped (not proven here): " + ", ".join(SKIPPED))
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
