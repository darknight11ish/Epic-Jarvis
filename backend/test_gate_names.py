"""Gate-name consistency: every name the gate is handed is a name the gate has.

    python3 test_gate_names.py

WHY THIS ONE EXISTS (the handoff's section 7, item 5)

Four suites broke in the 2026-10-03/04 pass for one reason, and it was the
same reason each time: a NAME on one side of the gate was not a name on the
other. Ten of `jarvis_agent.py`'s tools had a `gate_lookup_name` that was not
a key of `jarvis_gate._TOOL_ACTIONS`, so `action_for_tool()` fell through to
`unclassified_tool`, which is in no `[autonomy.tiers]` line and therefore
took `unknown_action_tier`. That is fail-SAFE - `unclassified_tool` resolves
to "ask" and nothing ran unattended - but it is silent, and it is wrong: the
card is not the card those tools were meant to raise, and a card nobody can
act on is how a real card gets ignored. `test_agent.py` covers its own tool
list; nothing covered the same question from the gate's side, or the other
direction (a test naming an action the live tier table no longer has).

WHAT IS CHECKED, AND AGAINST WHAT

The authority is the LIVE backend: `$JARVIS_BACKEND`'s `jarvis_gate.py` (the
table the running Jarvis actually reads) and `[autonomy.tiers]` in the
`jarvis-framework.toml` the gate itself would load - searched beside the gate,
then one folder up, the same two places `jarvis_framework.config_path()`
searches. Not a stub, and not this repository's copy: the whole point is to
compare what the suites say against what the owner's PC runs.

  1. Every tool `jarvis_agent.TOOLS` offers resolves to an action, not to
     the `unclassified_tool` fallback. The lookup name is read from the
     tool's own `gate_lookup_name`, never guessed from the function name.
     `web_search` is the one recorded exception: it is put to the gate under
     `jarvis_search.ACTION_SEARCH` ("search_the_web"), never through
     `action_for_tool` - see `jarvis_agent._web_search_call` and
     `test_agent.py`'s own skip for it.

  2. Every action a SUITE names - a string handed to the gate's `check()` /
     `gate_tool()` / `confirm_auto()` from any `backend/test_*.py`, and every
     `<...>ACTION<...> = "name"` constant the shipped modules define - is a
     name the LIVE gate can still resolve to a tier: an explicit line in the
     live tier table, a tier literal ("auto", "notify", "ask", "never"), an
     unclassified name, or one of the gate's own `_TOOL_ACTIONS` /
     `_NO_RULE_FROM_DENIAL` names (whose line is missing but whose name the
     gate still knows - check 3 reports each of those by name).

  3. Every action the LIVE GATE can resolve - each value of `_TOOL_ACTIONS`,
     each member of `_NO_RULE_FROM_DENIAL`, each key of `_RISK` - has an
     explicit line in the live tier table, unless it is one of the recorded
     fall-throughs below. This is the one that would have caught eleven names
     at once instead of three suites at a time.

  4. The repository's own shipped `[autonomy.tiers]` names nothing the live
     table does not have.

THE ONE THING THIS SUITE DOES NOT DO

It does not read the live tier table's VALUES. A policy question ("is
send_email still `ask`?") belongs to the suites that own that action, each of
which already asserts its own tier; this suite asks only whether the NAME
exists, so it fails for exactly one reason.

Runs on the owner's PC (set JARVIS_BACKEND) and in the dev container (unset:
BACKEND is this folder, where the modules are symlinked, and a name that
cannot be found is an honest SKIP, never a silent pass).
"""
import ast
import os
import re
import socket
import sys
import tempfile
import traceback
from pathlib import Path

# A temp config dir BEFORE any backend import: jarvis_gate opens its approval
# queue at import time, and this suite must not read or write the owner's own
# - the same guard test_gate_outcome.py uses.
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-gate-names-"))
os.environ.setdefault("OPENJARVIS_CONFIG_DIR", str(_TMP))
# No push: the topic is unset, so _push returns without opening a socket.
# Said explicitly, because a test that quietly posted to ntfy.sh would be the
# exact leak the gate exists to prevent.
os.environ["JARVIS_NTFY_TOPIC"] = ""

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
# BACKEND is where the modules under test live - this folder in the dev
# container, $JARVIS_BACKEND on a real install. REPO is this repository.
from _where import BACKEND, REPO, explain  # noqa: E402

try:
    import tomllib
except ImportError:                                  # Python < 3.11
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None

FAILED, PASSED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(name, why):
    """An honest SKIP: the thing this check needs is not here to check.

    Never a silent pass - the handoff's rule and this project's, because a
    check that passes without looking is worse than no check at all.
    """
    SKIPPED.append(name)
    print(f"SKIP {name}\n        {why}")


def _no_net():
    """Nothing below this line may open a socket."""
    def boom(*_a, **_k):
        raise OSError("this suite does not go on the network")
    socket.socket = boom
    socket.create_connection = boom


#: The tools whose lookup name is deliberately not a `_TOOL_ACTIONS` key, with
#: the reason. `web_search` is put to the gate under `jarvis_search.ACTION_SEARCH`
#: ("search_the_web"), which `web-search.patch` gives words in `_RISK`; it never
#: goes through `action_for_tool`, so the table is the wrong place to look for
#: it. `test_agent.py` skips the same one for the same reason.
NOT_VIA_THE_TABLE = {
    "web_search": "put to the gate under jarvis_search.ACTION_SEARCH (search_the_web), "
                  "never through action_for_tool - see jarvis_agent._web_search_call",
}

#: Actions the live gate can resolve and the live tier table has NO explicit
#: line for. Each one therefore takes `unknown_action_tier` ("ask" as shipped).
#: This is the fail-safe direction and none of them runs unattended because of
#: it - the "ask" they land on is, today, the tier each was meant to have.
#: Recorded here so a NEW one is a red check, not a silent fall-through of the
#: exact kind this suite exists for. Every one is reported by name in check 3's
#: output whether it passes or not. Read `dshwork/audit-2026-10-04/
#: audit-05-gate-names.md` for which of them are documented decisions and which
#: is an open finding.
RECORDED_FALL_THROUGHS = {
    "control_browser",          # README: the line "belongs with whoever writes that patch"
    "control_phone",            # README: "add explicit lines for both ... rather than
                                # relying on the fallback silently"
    "research_authenticated",   # the same README note, the same shape
    "run_plan",                 # jarvis_plan.py ships switched off until tools/tool_eval clears it
    "phone_notifications_read", # jarvis_phone_notifications.py's own ACTION; OPEN FINDING,
                                # see the audit note - no toml line anywhere in either copy
    "unclassified_tool",        # not an action at all: the fallback name itself
}

#: What the gate calls a tool it has no entry for. Named so a lookup that lands
#: here can be reported as a fallback rather than as an ordinary action.
UNCLASSIFIED = "unclassified_tool"

_GATE_CALLS = {"check", "gate_tool", "confirm_auto", "confirm"}
_CONST = re.compile(r"^([A-Z][A-Z0-9_]*)\s*=\s*\"([a-z][a-z0-9_]*)\"\s*(?:#.*)?$")
#: The shape every gate action in this project has. A test's own name for a
#: check ("a card is raised, and the reason says why") is a sentence, so it
#: never matches this and is never mistaken for an action.
_ACTION_NAME = re.compile(r"^[a-z][a-z0-9_]{2,40}$")
#: A module records the action it acts under in a constant whose NAME says so:
#: `ACTION`, `CARD_ACTION`, `RESTORE_ACTION`, `DRAFT_EMAIL_ACTION`, ...
_ACTION_CONST = re.compile(r"ACTION")


def _import_gate():
    """The live gate, or the reason it could not be read.

    Returns (module, why-not). `why-not` is a sentence fit to print after a
    SKIP.
    """
    if not (BACKEND / "jarvis_gate.py").is_file():
        return None, f"jarvis_gate.py is not in {BACKEND}. {explain()}"
    try:
        import jarvis_gate
    except Exception as exc:
        return None, (f"jarvis_gate.py is in {BACKEND} but would not import here "
                      f"({exc!r}), so the tables under test could not be read.")
    if Path(getattr(jarvis_gate, "__file__", "") or "").resolve() != (BACKEND / "jarvis_gate.py"):
        return None, (f"the jarvis_gate that imported is {jarvis_gate.__file__}, "
                      f"not {BACKEND / 'jarvis_gate.py'}")
    return jarvis_gate, ""


def _load_toml(path):
    """(tiers, unknown_action_tier) or (None, why-not)."""
    if tomllib is None:
        return None, "no tomllib/tomli in this Python, so no toml can be read"
    if path is None or not Path(path).is_file():
        return None, f"there is no {path}"
    try:
        cfg = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        return None, f"{path} would not parse as toml ({exc!r})"
    autonomy = (cfg.get("autonomy") or {})
    tiers = autonomy.get("tiers")
    if not isinstance(tiers, dict) or not tiers:
        return None, f"{path} has no [autonomy.tiers] table"
    return tiers, str(autonomy.get("unknown_action_tier", "ask"))


def _live_tier_path():
    """The toml the gate would load, from the same two places
    jarvis_framework.config_path() searches: beside the module, then its parent."""
    for p in (BACKEND / "jarvis-framework.toml",
              BACKEND.parent / "jarvis-framework.toml"):
        if p.is_file():
            return p
    return None


def _shipped_tier_path():
    """This repository's own shipped config, if it is here."""
    for p in (BACKEND / "rebuilt" / "jarvis-framework.toml",
              REPO / "backend" / "rebuilt" / "jarvis-framework.toml"):
        if p.is_file():
            return p
    return None


def _agent_tools():
    """(TOOLS, why-not) from the backend's own jarvis_agent.py."""
    if not (BACKEND / "jarvis_agent.py").is_file():
        return None, f"jarvis_agent.py is not in {BACKEND}. {explain()}"
    try:
        import jarvis_agent
    except Exception as exc:
        return None, (f"jarvis_agent.py is in {BACKEND} but would not import here "
                      f"({exc!r}), so its tool list could not be read.")
    tools = getattr(jarvis_agent, "TOOLS", None)
    if not isinstance(tools, dict) or not tools:
        return None, "jarvis_agent.py imported but has no TOOLS table"
    return tools, ""


def _lookup_name(tool, tname):
    """The name this tool is put to the gate under, read from the tool itself."""
    fn = getattr(tool, "gate_lookup_name", None)
    if not fn:
        return tname
    try:
        out = fn({})
    except Exception:
        return tname
    return out or tname


def _repo_gate_vocabulary():
    """Every gate action name that appears ANYWHERE in this repository.

    Read from the files, so it holds names the live table may since have
    dropped: every `[autonomy.tiers]` key in the shipped config, every value a
    `"_TOOL_ACTIONS"` entry or a `_NO_RULE_FROM_DENIAL` member is given in a
    patch, every `_RISK` key a patch adds, and every `backend/README.md` line
    of the `jarvis_<x>_run -> <action>` table. Used to tell a suite that is
    naming a real action from a suite's own short name for a check.
    """
    known = set()
    shipped = _shipped_tier_path()
    tiers, _why = _load_toml(shipped)
    if tiers:
        known |= set(tiers)
    for path in sorted(HERE.glob("*.patch")):
        # Added lines only, and only while the walk is inside one of the gate's
        # own tables: a patch's context lines are other files' text, and
        # gate-outcome.patch's own `_OUTCOMES` set holds `"approved",  # a human
        # said yes` - an outcome, not an action. A table starts at its name and
        # ends at a line that closes it (`})`, `}`, `)`, `]`).
        added = [ln[1:] for ln in path.read_text(encoding="utf-8", errors="replace").splitlines()
                 if ln.startswith("+") and not ln.startswith("+++")]
        table = None
        for body in added:
            stripped = body.strip()
            if "_TOOL_ACTIONS" in body:
                table = "_TOOL_ACTIONS"
            elif "_NO_RULE_FROM_DENIAL" in body:
                table = "_NO_RULE_FROM_DENIAL"
            elif "_RISK" in body:
                table = "_RISK"
            elif table and re.match(r'^[}\)\]]\s*$', stripped):
                table = None
            if table == "_TOOL_ACTIONS":
                for key, value in re.findall(r'"([a-z][a-z0-9_]*)"\s*:\s*"([a-z_]+)"', body):
                    known.add(key)
                    known.add(value)
            elif table == "_NO_RULE_FROM_DENIAL":
                m = re.match(r'^\s*"([a-z][a-z0-9_]*)"', body)
                if m:
                    known.add(m.group(1))
            elif table == "_RISK":
                m = re.match(r'^\s*"([a-z][a-z0-9_]*)"\s*:', body)
                if m:
                    known.add(m.group(1))
    readme = HERE / "README.md"
    if readme.is_file():
        text = readme.read_text(encoding="utf-8", errors="replace")
        # The `| jarvis_x_run | action | why |` table and the same pair written
        # as prose ("`jarvis_x_run -> action`"). Both name a real action; a
        # bare word is not taken from the README, or "approved" in a sentence
        # about a pairing state would be read as one.
        for _lookup, action in re.findall(
                r"(jarvis_[a-z_]+_run(?:_authenticated)?)`?\s*(?:->|\|)\s*`?([a-z_]+)`?", text):
            known.add(action)
        for action in re.findall(r"_TOOL_ACTIONS\[\"jarvis_[a-z_]+_run\"\] = \"([a-z_]+)\"", text):
            known.add(action)
    known -= {"auto", "notify", "ask", "never"}
    return {k for k in known if _ACTION_NAME.match(k)}


def _gate_aliases(tree):
    """The names this file binds `jarvis_gate` to ("G", "gate", ...).

    `test_gate_outcome.py` calls `G.check("send_email", ...)`; the suites' own
    helper is a plain `check("a long test name", cond)`. Reading the import is
    how the two are told apart without guessing at the receiver's name.
    """
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name == "jarvis_gate":
                    names.add(a.asname or "jarvis_gate")
        elif isinstance(node, ast.ImportFrom):
            if node.module == "jarvis_gate":
                for a in node.names:
                    names.add(a.asname or a.name)
    return names


def _suite_named_actions():
    """{action: [where it was seen]} for every action name a suite names.

    Three shapes, all read from the files rather than guessed:

      * `G.check("send_email", ...)` where `G` is bound to `jarvis_gate` by an
        import in the same file - a gate call, and its first argument really is
        an action name whatever it says.
      * `check("...", cond)`: the same method name on any other object, which
        in these suites is their own helper. Its first argument is only taken
        as an action when the REPOSITORY already knows the word as one
        (`_repo_gate_vocabulary`), because `check("added", ...)` is a test.
      * a module-level `<...>ACTION<...> = "name"` constant in a shipped
        `backend/jarvis_*.py` - how every module here records the action it
        acts under.
    """
    known = _repo_gate_vocabulary()
    found = {}

    def add(name, where):
        found.setdefault(name, []).append(where)

    for path in sorted(HERE.glob("test_*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError as exc:
            add(f"<{path.name} would not parse: {exc}>", path.name)
            continue
        aliases = _gate_aliases(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            fn = node.func
            if isinstance(fn, ast.Attribute):
                name, receiver = fn.attr, (fn.value.id if isinstance(fn.value, ast.Name) else None)
            elif isinstance(fn, ast.Name):
                name, receiver = fn.id, None
            else:
                continue
            if name not in _GATE_CALLS:
                continue
            a0 = node.args[0]
            if not (isinstance(a0, ast.Constant) and isinstance(a0.value, str)):
                continue
            if receiver is None:
                if a0.value not in known:
                    continue          # the suite's own check("a test name", cond)
            elif receiver not in aliases:
                continue              # somebody else's .check()
            add(a0.value, f"{path.name}:{node.lineno} {name}()")

    for path in sorted(HERE.glob("jarvis_*.py")):
        for i, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            m = _CONST.match(line.strip())
            if m and _ACTION_CONST.search(m.group(1)):
                add(m.group(2), f"{path.name}:{i} {m.group(1)}")
    return found


def _tier_literals(gate):
    """The words `action_for_tool` may return that are tiers, not actions.

    A table entry whose value is one of these is a tier of its own ("calculator"
    is "auto"), which is why it needs no line in `[autonomy.tiers]` - the gate
    keeps it in `_SYNTH_TIERS` for exactly that reason.
    """
    return set(gate._VALID_TIERS)


def _gate_member_actions(gate):
    """{action: what in the gate resolves to it} - everything the LIVE gate can
    produce as an action name, read from the gate's own tables."""
    found = {}
    for lookup, action in gate._TOOL_ACTIONS.items():
        found.setdefault(action, []).append(f"_TOOL_ACTIONS[{lookup!r}]")
    for action in getattr(gate, "_NO_RULE_FROM_DENIAL", ()):
        found.setdefault(action, []).append("_NO_RULE_FROM_DENIAL")
    for action in getattr(gate, "_RISK", {}):
        found.setdefault(action, []).append("_RISK")
    return found


# --------------------------------------------------------------------------
# 1. every tool resolves to a real action
# --------------------------------------------------------------------------

def t_every_tool_resolves_to_a_real_action():
    """A tool whose lookup name is not in `_TOOL_ACTIONS` is handed to the gate
    as something the gate has never heard of."""
    gate, why = _import_gate()
    if gate is None:
        return skip("every tool resolves to a real action", why)
    tools, why = _agent_tools()
    if tools is None:
        return skip("every tool resolves to a real action", why)
    _no_net()

    fall_throughs = []
    for tname in sorted(tools):
        if tname in NOT_VIA_THE_TABLE:
            continue
        lookup = _lookup_name(tools[tname], tname)
        action, _known = gate.action_for_tool(lookup, {})
        if action == UNCLASSIFIED:
            fall_throughs.append(f"{tname} -> lookup {lookup!r} -> {UNCLASSIFIED}")
    check("every tool jarvis_agent offers resolves to a real action, not "
          "unclassified_tool",
          not fall_throughs,
          "add each lookup name to jarvis_gate._TOOL_ACTIONS:\n        "
          + "\n        ".join(fall_throughs))
    check("the tool list was actually read (test setup)",
          len(tools) - len(NOT_VIA_THE_TABLE) > 0,
          f"{len(tools)} tools, {len(NOT_VIA_THE_TABLE)} recorded as not going through the table")


# --------------------------------------------------------------------------
# 2. every action a suite names is a name the live gate still knows
# --------------------------------------------------------------------------

def t_every_action_a_suite_names_has_a_live_tier_line():
    """The other direction. A suite that asks the gate for "send_email" when
    neither the live tier table nor any of the gate's own tables has that name
    is testing a name the running Jarvis answers as an unknown action."""
    gate, why = _import_gate()
    if gate is None:
        return skip("every action a suite names is a name the live gate knows", why)
    tiers, why = _load_toml(_live_tier_path())
    if tiers is None:
        return skip("every action a suite names is a name the live gate knows", why)
    _no_net()

    named = _suite_named_actions()
    # A parse error was recorded as a pseudo-name; it is a failure, not a name.
    broken = sorted(n for n in named if n.startswith("<") and n.endswith(">"))
    check("every backend/test_*.py parses, so the scan really saw it",
          not broken, "\n        ".join(broken))

    real = {n: w for n, w in named.items() if not n.startswith("<")}
    check("the scan found the suites' action names (not an empty list by a broken "
          "pattern)",
          len(real) >= 20,
          f"only {len(real)} names found: {sorted(real)}")

    # A name the live gate still knows - as a `_TOOL_ACTIONS` value or a
    # `_NO_RULE_FROM_DENIAL` member - resolves to a tier even with no toml
    # line of its own: it takes `unknown_action_tier`, and check 3 names every
    # one of those. What this check fails on is a name NOTHING in the live gate
    # has any more: the suite would be asserting an action the running Jarvis
    # can no longer produce.
    known_to_the_gate = set(_gate_member_actions(gate))
    missing = {n: w for n, w in real.items()
               if n not in tiers and n not in gate._VALID_TIERS
               and n not in known_to_the_gate
               and n not in (UNCLASSIFIED, "unclassified_action")}
    check("every action a suite names is one the live gate can still resolve a "
          "tier for (a toml line, a tier literal, or a name in the gate's own "
          "tables)",
          not missing,
          "the live gate has no line and no table entry for these, so the running "
          "Jarvis answers them as an unknown action - rename the suite's name, or "
          "put the action back in the backend's jarvis_gate.py:\n        "
          + "\n        ".join(f"{n}  (named at {', '.join(w[:3])})"
                              for n, w in sorted(missing.items())))
    print(f"        ({len(real)} action names named by the suites, "
          f"{len(tiers)} lines in {_live_tier_path()})")


# --------------------------------------------------------------------------
# 3. every action the LIVE gate can resolve has an explicit line
# --------------------------------------------------------------------------

def t_every_action_the_live_gate_resolves_has_a_live_tier_line():
    """Read from the gate itself, so a new action added to `_TOOL_ACTIONS` (or
    to the denial list) without its toml line is caught here rather than in
    whichever suite happens to exercise it."""
    gate, why = _import_gate()
    if gate is None:
        return skip("every action the live gate resolves has a live tier line", why)
    tiers, unknown_tier = _load_toml(_live_tier_path())
    if tiers is None:
        return skip("every action the live gate resolves has a live tier line",
                    unknown_tier)
    _no_net()

    members = _gate_member_actions(gate)
    check("the gate's tables were actually read (test setup)",
          len(gate._TOOL_ACTIONS) >= 50 and len(members) >= 50,
          f"{len(gate._TOOL_ACTIONS)} tool entries, {len(members)} distinct actions")

    literals = _tier_literals(gate)
    # Everything else takes unknown_action_tier, which is a real, silent
    # fall-through. A recorded one is a decision written down in this file; an
    # unrecorded one is the class of bug this suite is for.
    via_fallback = {a: w for a, w in members.items()
                    if a not in tiers and a not in literals}
    unrecorded = {a: w for a, w in via_fallback.items()
                  if a not in RECORDED_FALL_THROUGHS}
    check("every action the live gate can resolve is either a tier literal, a "
          "recorded fall-through, or a line in the live [autonomy.tiers]",
          not unrecorded,
          "these resolve through unknown_action_tier with no recorded reason; add "
          "the toml line, or record it in RECORDED_FALL_THROUGHS with why:\n        "
          + "\n        ".join(f"{a}  (from {', '.join(unrecorded[a][:2])})"
                              for a in sorted(unrecorded)))
    check("a recorded fall-through is only recorded because it really does fall "
          "through (test setup)",
          set(via_fallback) <= RECORDED_FALL_THROUGHS,
          f"not covered by a toml line or a tier literal, and not recorded: "
          f"{sorted(set(via_fallback) - RECORDED_FALL_THROUGHS)}")
    # Printed every run, pass or fail: these are the names that take
    # unknown_action_tier. A recorded one is a decision; a new one is red.
    print(f"        with no explicit [autonomy.tiers] line, so tier "
          f"{unknown_tier!r} from unknown_action_tier: "
          + (", ".join(sorted(via_fallback)) or "none"))


# --------------------------------------------------------------------------
# 4. the repository's own shipped tier table names nothing the live one lacks
# --------------------------------------------------------------------------

def t_the_shipped_tier_table_names_nothing_the_live_one_lacks():
    """Drift in the other direction: a `[autonomy.tiers]` line that is in this
    repository's shipped config but not in the one the owner's PC runs is an
    action that falls to `unknown_action_tier` on the real machine."""
    live, why = _load_toml(_live_tier_path())
    if live is None:
        return skip("the shipped tier table names nothing the live one lacks", why)
    shipped_path = _shipped_tier_path()
    shipped, why = _load_toml(shipped_path)
    if shipped is None:
        return skip("the shipped tier table names nothing the live one lacks", why)

    only_here = sorted(set(shipped) - set(live))
    check("every action in the repository's shipped [autonomy.tiers] has a line "
          "in the live one",
          not only_here,
          f"in {shipped_path} but not in {_live_tier_path()}:\n        "
          + "\n        ".join(only_here))
    bad = sorted(a for a, t in live.items()
                 if str(t).strip().lower() not in {"auto", "notify", "ask", "never"})
    check("every live tier line is one of auto / notify / ask / never",
          not bad, "\n        ".join(f"{a} = {live[a]!r}" for a in bad))
    print(f"        ({len(live)} live tier lines, {len(shipped)} shipped, "
          f"{len(set(live) & set(shipped))} in both)")


def main():
    for fn in (t_every_tool_resolves_to_a_real_action,
               t_every_action_a_suite_names_has_a_live_tier_line,
               t_every_action_the_live_gate_resolves_has_a_live_tier_line,
               t_the_shipped_tier_table_names_nothing_the_live_one_lacks):
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
