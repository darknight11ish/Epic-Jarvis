"""test_repair_live_backend_gaps.py - proves the repair tool behaves safely.

The tool puts back the base-file / patch-carried pieces this PC's install never
received: the app builder's two `_RISK` rows and the card timer in
`jarvis_gate.py`, the `/api/history/pin` + `/api/history/archive` POST routes in
`jarvis_hud.py`, the unclassified-action rule + the eight `_RISK` rows from
`unknown-risk-approvable.patch` (six disjoint pieces, applied as ONE write), and
the Obsidian notes editor's `edit_vault_note` `_RISK` row (PR #1350, missing
from the live gate measured 2026-11-19 - without it the owner's own note append
is classified as risky and its card demands Windows Hello, so a headless field
battery can never approve it), and the device list's `devices_cleanup` risk row
and `_NO_RULE_FROM_DENIAL` membership (Gemini's ruling 5.6, 2026-11-21 - without
them the owner's own cleanup card takes the unclassified fallback, says the
cleanup is permanent and outbound, and demands Windows Hello).

Two repairs carry MORE than one edit in one file, and both are proved below to
land as one write with one backup. The card timer is TWO hunks of
`backend/show-card-timer.patch`: the block in `pending()` AND the SELECT line
that gives it a `waited_until` column. A tool that inserts only the block is a
silent no-op, so the tests prove both hunks land and that a half-applied file
is REFUSED rather than written again. The unclassified-action rule is SIX
hunks of `unknown-risk-approvable.patch` (the sixth is DEF-021's file-wins
tier fix with its revised forced-ask block, added 2026-10-31), and the
repaired file must equal the published gate byte for byte.

The SAME repair also carries the LIVE lineage (Gemini ruling (a), 2026-10-31):
the 5-hunk #1008 gate (`3e9b8068…`) and the pre-#1008 gate are brought to the
#1023 post-image (`39a0c407…`) from stored, hash-keyed patches; a listed gate
whose bytes no longer match, or an unrecognised live-sized gate, is REFUSED
rather than guessed. `backend/fixtures/def-021-gate-39a0c407.txt.gz` is the
verified post-image; every accepted pre-image is derived from it and its hash
checked here, so this suite fails if the tool's stored table drifts.

One more input cannot be a stored patch at all: the owner's live gate measured on
2026-11-06 is PAST the #1023 post-image and already carries all twelve probes, so
it is pinned by its own exact hash in `LIVE_GATE_ALREADY_REPAIRED` - the
idempotent no-op, authorising no write. A file edited afterwards has a different
hash and falls back to the refusal, never to a guess.

It writes into the LIVE backend folder, so every failure path matters more
than the happy one: a missing or ambiguous anchor must refuse, an already
repaired file must be a no-op, a broken rewrite must be rolled back, and the
live folder must never be left half-written.

Run: python -B backend/test_repair_live_backend_gaps.py
"""
import ast
import importlib.util
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
TOOL = REPO / "tools" / "repair_live_backend_gaps.py"

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def load_tool():
    spec = importlib.util.spec_from_file_location("repair_gaps", TOOL)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["repair_gaps"] = mod  # dataclasses looks the module up by name
    spec.loader.exec_module(mod)
    return mod


def _literal_rows(text: str, name: str) -> dict:
    """The rows of a module-level `name: dict[...] = {...}` literal, read with `ast`.

    Two reasons this is `ast` and not a substring test, and the second one is
    the one that matters:

    1. `tools/check_no_source_pins.py` is a CEILING RATCHET and this suite is
       already at its ceiling (7, and it may only go down). A new check here
       cannot be another source-text pin.
    2. A substring test cannot tell "this row is a KEY of the table" from "this
       row appears somewhere in the file" - the old check had to hunt for the
       closing brace to approximate it, and any comment carrying the same words
       satisfied it. An `ast` walk answers the actual question: is it in the
       literal.

    Only string-to-string rows are returned; `_TOOL_ACTIONS` is
    `dict[str, str]`, and `_RISK` (whose values are tuples) is not read here.
    """
    for node in ast.walk(ast.parse(text)):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        if not isinstance(node.value, ast.Dict):
            continue
        targets = getattr(node, "targets", None) or [getattr(node, "target", None)]
        if not any(isinstance(t, ast.Name) and t.id == name for t in targets):
            continue
        return {k.value: v.value
                for k, v in zip(node.value.keys, node.value.values)
                if isinstance(k, ast.Constant) and isinstance(v, ast.Constant)}
    return {}


def a_live_folder(gate: str = None, hud: str = None) -> Path:
    d = Path(tempfile.mkdtemp(prefix="repair-gaps-"))
    (d / "jarvis_gate.py").write_text(
        gate if gate is not None else
        "_RISK: dict[str, tuple[str, str, str]] = {\n"
        '    "web_research": ("yes", "outbound", "a public query leaves the machine"),\n'
        "}\n"
        "\n"
        "# A live jarvis_gate.py always carries this table; the tool-actions\n"
        "# repair (2026-11-14) anchors on it, so the fabricated file must have it\n"
        "# or every repair in the loop below would be refused for the wrong\n"
        "# reason. Two rows are enough to prove an insertion at its top.\n"
        "_TOOL_ACTIONS: dict[str, str] = {\n"
        '    "calculator": "auto",\n'
        '    "send_file_to_phone": "send_file_to_phone",\n'
        "}\n"
        "\n"
        "# A live jarvis_gate.py always carries this table too: the\n"
        "# devices-cleanup repair (2026-11-21) anchors on it, the same way\n"
        "# the tool-actions repair anchors on the table above.\n"
        "_NO_RULE_FROM_DENIAL = frozenset({\n"
        '    "pair_device",\n'
        "})\n"
        "\n"
        'def _tiers(framework: Optional[dict] = None) -> dict:\n'
        '    """The tier table, validated. An unrecognised tier string - "Never" with a\n'
        '    capital, "aks", anything not in _VALID_TIERS - is treated as "never",\n'
        '    because a typo in a security policy should lock, not unlock."""\n'
        '    try:\n'
        '        f = framework if framework is not None else fw.load_framework()\n'
        '        raw = f.get("autonomy", {}).get("tiers", {}) or {}\n'
        '    except Exception:\n'
        '        return {}\n'
        '    out = {}\n'
        '    for k, v in raw.items():\n'
        '        v = str(v).strip().lower()\n'
        '        out[k] = v if v in _VALID_TIERS else "never"\n'
        '    out.update(_SYNTH_TIERS)\n'
        '    return out\n'
        "\n"
        "\n"
        '_UNKNOWN_RISK = ("no", "outbound",\n'
        '                 "not classified, so treated as irreversible and outbound")\n'
        "\n"
        "\n"
        "def risk_for(action: str) -> dict:\n"
        '    """Why this action is allowed, and what it costs.\n'
        "\n"
        "    decisions. The rest is there so a UI can EXPLAIN the decision rather than\n"
        '    just enforce it - a card that says "no undo: there is no unsend" teaches\n'
        "    the rule, and a card that silently refuses a swipe does not.\n"
        '    """\n'
        '    rev, reach, why = _RISK.get(action or "", _UNKNOWN_RISK)\n'
        "    return {}\n"
        "\n"
        "\n"
        "def notice_for(item: dict) -> dict:\n"
        '    r = item["risk"]\n'
        "    raised = False\n"
        '    heavy = (r["reversible"] == "no") or (r["reach"] != "local") or raised\n'
        "\n"
        '    bits = [r["why"]]\n'
        "    if raised:\n"
        "        # Said, never quoted. That something tried to rush you is the fact that\n"
        "        # changes your decision; its actual words are not needed to convey it,\n"
        "        pass\n"
        "    return {}\n"
        "\n"
        "\n"
        "def pending():\n"
        "    d = {}\n"
        "    sql = (\n"
        '            "SELECT id,action,tier,detail,prompt,created,raised FROM approvals"\n'
        "            \" WHERE state='pending' ORDER BY created\")\n"
        "    if d:\n"
        "        # Why this is being asked about at all, when the table said otherwise.\n"
        "        pass\n"
        "    return d\n"
        "\n"
        "\n"
        'def check(action: str, detail=None, prompt="") -> str:\n'
        "    try:\n"
        "        if not LAYERS:\n"
        '            # is no reading of "no policy" under which a tool call is safe.\n'
        '            raise RuntimeError("autonomy tier table is empty")\n'
        "        tier = tiers.get(action, UNKNOWN_TIER)\n"
        "    except Exception as exc:\n"
        "        # Cannot read the policy -> cannot claim the action is permitted.\n"
        '        _audit("gate.policy_unreadable", {"action": action, "error": str(exc)})\n'
        "    return tier\n",
        encoding="utf-8", newline="\n")
    (d / "jarvis_hud.py").write_text(
        hud if hud is not None else
        "def do_POST(self):\n"
        '    if route in ("/api/history/delete", "/api/history/settings",\n'
        '                 "/api/history/tags", "/api/history/tags/suggest", "/api/history/tag",\n'
        '                     "/api/history/fork", "/api/history/mark"):\n'
        "        return self._send(200, {})\n",
        encoding="utf-8", newline="\n")
    return d


def t_check_names_both_missing_then_apply_fixes_them():
    mod = load_tool()
    live = a_live_folder()
    original_gate = (live / "jarvis_gate.py").read_text(encoding="utf-8")
    for repair in mod.REPAIRS.values():
        check(f"{repair.name}: a fresh live file is reported missing",
              mod.check_one(live, repair) == "missing")
    for repair in mod.REPAIRS.values():
        check(f"{repair.name}: apply writes it",
              mod.apply_one(live, repair, stamp="test") == "applied")
    for repair in mod.REPAIRS.values():
        check(f"{repair.name}: a second apply is a no-op",
              mod.apply_one(live, repair, stamp="test") == "already")
    gate = (live / "jarvis_gate.py").read_text(encoding="utf-8")
    check("the two risk rows landed", '"app_build_android": ("no"' in gate
          and '"app_install_android": ("no"' in gate)
    table = _literal_rows(gate, "_TOOL_ACTIONS")
    check("the two tool->action rows landed, so action_for_tool() answers the "
          "specific action instead of unclassified_tool",
          table.get("app_build_android") == "app_build_android"
          and table.get("app_install_android") == "app_install_android",
          f"the literal's keys are {sorted(table)}")
    check("... inside the _TOOL_ACTIONS literal, not floating after the table",
          {"app_build_android", "app_install_android"} <= set(table),
          f"the literal's keys are {sorted(table)}")
    # The plan store's rows (2026-11-20, PM2): the eight typed tools map to
    # actions that already exist, and the one new _RISK row is what lets the
    # gate's own unclassified-action rule keep the five owner-direct writes
    # cardless on a clean turn. Both halves are in the same repair, one write.
    check("the plan store's eight tool->action rows landed",
          {name: table.get(name) for name in (
              "project_create", "work_item_add", "work_item_update_status",
              "work_item_link_dependency", "project_checkpoint_reflect",
              "project_seed_plan", "project_decompose_plan",
              "project_export_obsidian_hub")} == {
              "project_create": "todo_add",
              "work_item_add": "todo_add",
              "work_item_update_status": "todo_add",
              "work_item_link_dependency": "todo_add",
              "project_checkpoint_reflect": "todo_add",
              "project_seed_plan": "change_own_config",
              "project_decompose_plan": "change_own_config",
              "project_export_obsidian_hub": "edit_vault_note"},
          f"the literal's keys are {sorted(table)}")
    risk = risk_table(gate)
    check("... and the one new risk row for todo_add landed",
          risk.get("todo_add", ())[:2] == ("yes", "local"),
          risk.get("todo_add"))
    hud = (live / "jarvis_hud.py").read_text(encoding="utf-8")
    check("both history routes landed", '"/api/history/pin"' in hud
          and '"/api/history/archive"' in hud)
    check("the card timer landed in pending()",
          'd["expires_in"] = _whole' in gate and "_waited = d.pop" in gate)
    check("... including the timer's SELECT column",
          all(new in gate for _old, new in mod.REPAIRS["timer"].extra_edits))
    check("the unknown-risk rule landed all six pieces",
          all(piece.replace_with in gate
              for piece in mod.REPAIRS["unknown-risk"].parts()))
    check("the anchor line was kept", '"/api/history/mark"' in hud)
    check("a backup of each written file exists",
          any(live.glob("jarvis_gate.py.before-repair-*"))
          and any(live.glob("jarvis_hud.py.before-repair-*")))
    gate_backup = next(live.glob("jarvis_gate.py.before-repair-*"))
    hud_backup = next(live.glob("jarvis_hud.py.before-repair-*"))
    check("the one gate backup holds the file as it was BEFORE the run",
          gate_backup.read_text(encoding="utf-8") == original_gate,
          "three repairs write jarvis_gate.py; a later one must not overwrite the backup")
    check("nothing else was touched", sorted(p.name for p in live.iterdir()
                                              if not p.name.startswith("__pycache__")) ==
          sorted(["jarvis_gate.py", "jarvis_hud.py", gate_backup.name, hud_backup.name]))


def t_a_missing_anchor_refuses_and_writes_nothing():
    mod = load_tool()
    live = a_live_folder(gate="RISK = {}\n")  # no anchor at all
    before = (live / "jarvis_gate.py").read_text(encoding="utf-8")
    try:
        mod.apply_one(live, mod.REPAIRS["gate"], stamp="test")
        check("a missing anchor raises Refused", False, "no exception")
    except mod.Refused:
        check("a missing anchor raises Refused", True)
    check("... and the file is byte-identical afterwards",
          (live / "jarvis_gate.py").read_text(encoding="utf-8") == before)
    check("... and no backup was left behind",
          not any(live.glob("jarvis_gate.py.before-repair-*")))


def t_an_ambiguous_anchor_refuses():
    mod = load_tool()
    twice = ("_RISK: dict[str, tuple[str, str, str]] = {\n"
             '    "web_research": ("yes", "outbound", "x"),\n'
             "}\n_RISK: dict[str, tuple[str, str, str]] = {\n"
             '    "web_research": ("yes", "outbound", "x"),\n'
             "}\n")
    live = a_live_folder(gate=twice)
    before = (live / "jarvis_gate.py").read_text(encoding="utf-8")
    try:
        mod.apply_one(live, mod.REPAIRS["gate"], stamp="test")
        check("an anchor that appears twice raises Refused", False, "no exception")
    except mod.Refused:
        check("an anchor that appears twice raises Refused", True)
    check("... and the file is byte-identical afterwards",
          (live / "jarvis_gate.py").read_text(encoding="utf-8") == before)


def t_a_repair_whose_rewrite_does_not_compile_is_rolled_back():
    mod = load_tool()
    live = a_live_folder()
    before = (live / "jarvis_gate.py").read_text(encoding="utf-8")
    bad = mod.Repair(
        name="broken", filename="jarvis_gate.py", probes=("never-there",),
        anchor="_RISK: dict[str, tuple[str, str, str]] = {\n",
        replace_with="    this is not python(\n", why="a test fixture that must not stick")
    try:
        mod.apply_one(live, bad, stamp="test")
        check("a rewrite that will not compile raises Refused", False, "no exception")
    except mod.Refused:
        check("a rewrite that will not compile raises Refused", True)
    check("... and the original file was put back",
          (live / "jarvis_gate.py").read_text(encoding="utf-8") == before)
    check("... and the temporary file was removed",
          not any(p.name.endswith(".tmp") for p in live.iterdir()))


def t_already_present_is_a_no_op_even_if_anchor_is_gone():
    mod = load_tool()
    live = a_live_folder(
        gate=("RISK = {}\n"
              '"app_build_android": ("no", "x", "y"),\n'
              '"app_install_android": ("no", "x", "y"),\n'
              '_waited = d.pop("waited_until", None)\n'
              'd["expires_in"] = _whole\n'
              '            "SELECT id,action,tier,detail,prompt,created,raised,waited_until"\n'
              '            " FROM approvals"\n'))
    check("a file that already has the rows reports 'already'",
          mod.check_one(live, mod.REPAIRS["gate"]) == "already")
    check("... and a file with both timer hunks reports 'already' too",
          mod.check_one(live, mod.REPAIRS["timer"]) == "already")


def t_the_timer_repair_carries_both_hunks():
    """The 2026-10-30 miss this test exists for.

    `backend/show-card-timer.patch` has two functional hunks: the `expires_in`
    block, and the `pending()` SELECT line that gives the block a `waited_until`
    column. A repair that inserts only the block is a silent no-op - the row has
    no such column, so `d.pop("waited_until", None)` is always None - while its
    own probes still report it applied. These assertions fail on that tool.
    """
    mod = load_tool()
    repair = mod.REPAIRS["timer"]
    old_select = ('            "SELECT id,action,tier,detail,prompt,created,'
                  'raised FROM approvals"\n')
    # The patch's own post-image: it splits the one string into two literals so
    # the SELECT stays valid Python with a FROM clause on the second line.
    new_select = ('            "SELECT id,action,tier,detail,prompt,created,'
                  'raised,waited_until"\n'
                  '            " FROM approvals"\n')
    check("the timer repair inserts the expires_in block",
          'd["expires_in"] = _whole' in repair.replace_with)
    check("... and carries pending()'s SELECT change in the SAME repair",
          repair.extra_edits == ((old_select, new_select),))
    check("... the new text is the old one with the column and a split literal",
          old_select.replace('raised FROM approvals"',
                             'raised,waited_until"\n            " FROM approvals"')
          == new_select)
    live = a_live_folder()
    stub = (live / "jarvis_gate.py").read_bytes().decode("utf-8")
    check("... a live-shaped stub starts without the column",
          new_select not in stub and old_select in stub)
    check("... so the tool reports the timer missing",
          mod.check_one(live, repair) == "missing")
    check("... ONE apply writes both hunks",
          mod.apply_one(live, repair, stamp="test") == "applied")
    repaired = (live / "jarvis_gate.py").read_bytes().decode("utf-8")
    check("... pending() now asks for waited_until",
          new_select in repaired and old_select not in repaired)
    check("... the block is in exactly once",
          repaired.count('d["expires_in"] = _whole') == 1)
    check("... a second apply is a no-op",
          mod.apply_one(live, repair, stamp="test2") == "already")
    check("... with exactly one backup for the one write",
          len(list(live.glob("jarvis_gate.py.before-repair-*"))) == 1)


def t_a_half_applied_timer_repair_is_refused_not_duplicated():
    """The old, incomplete tool's output: the block is in, the SELECT is not.

    Re-running the insertion there would put a SECOND copy of the block in the
    live file, so the tool must refuse instead of calling it missing."""
    mod = load_tool()
    old_tool_output = (
        "_RISK: dict[str, tuple[str, str, str]] = {\n"
        '    "web_research": ("yes", "outbound", "a public query leaves the machine"),\n'
        "}\n"
        "def pending():\n"
        "    d = {}\n"
        "    sql = (\n"
        '            "SELECT id,action,tier,detail,prompt,created,raised FROM approvals"\n'
        "            \" WHERE state='pending' ORDER BY created\")\n"
        "    if d:\n"
        '        _waited = d.pop("waited_until", None)\n'
        '        d["expires_in"] = _whole\n'
        "        # Why this is being asked about at all, when the table said otherwise.\n"
        "        pass\n"
        "    return d\n")
    live = a_live_folder(gate=old_tool_output)
    before = (live / "jarvis_gate.py").read_bytes().decode("utf-8")
    try:
        mod.apply_one(live, mod.REPAIRS["timer"], stamp="test")
        check("a half-applied timer repair is REFUSED", False, "no exception")
    except mod.Refused:
        check("a half-applied timer repair is REFUSED", True)
    check("... and the file is byte-identical afterwards",
          (live / "jarvis_gate.py").read_bytes().decode("utf-8") == before)
    check("... and no backup was left behind",
          not any(live.glob("jarvis_gate.py.before-repair-*")))


def t_the_real_bases_carry_both_pieces():
    """The rows/routes the tool inserts must match what the repository's own
    published base carries - so a repaired install equals a fresh one."""
    gate = (REPO / "jarvis-backend" / "jarvis_gate.py").read_text(encoding="utf-8")
    check("the published base has both risk rows",
          '"app_build_android": ("no"' in gate and '"app_install_android": ("no"' in gate)
    # The history routes are patch content, not base content: a fresh install
    # gets them by applying chat-history.patch, this PC could not.
    patch = (REPO / "backend" / "chat-history.patch").read_text(encoding="utf-8")
    check("chat-history.patch names both routes", "/api/history/pin" in patch
          and "/api/history/archive" in patch)


def _denial_actions(text: str) -> set:
    """The actions `_NO_RULE_FROM_DENIAL` really holds, read with `ast`.

    The table is built as a `frozenset({...})` plus module-level
    `_NO_RULE_FROM_DENIAL | {...}` unions (one per feature that adds a row),
    so a literal-only reader misses every row a later feature added.
    """
    found = set()
    for node in ast.parse(text).body:
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        if not any(isinstance(t, ast.Name) and t.id == "_NO_RULE_FROM_DENIAL"
                   for t in targets):
            continue
        for sub in ast.walk(value):
            if isinstance(sub, ast.Set):
                found |= {e.value for e in sub.elts
                          if isinstance(e, ast.Constant) and isinstance(e.value, str)}
    return found


def t_the_devices_cleanup_rows_repair_a_live_gate_without_them():
    """Gemini's ruling 5.6 (2026-11-21): the device-list cleanup card.

    Without the row `risk_for("devices_cleanup")` answers the unclassified
    fallback - permanent and outbound - so the owner's own local, reversible
    cleanup demands Windows Hello and its card says things that are false. The
    repair must insert the published base's own row and give the action its
    `_NO_RULE_FROM_DENIAL` membership, in ONE write, and must be a no-op on a
    gate that already carries both.
    """
    mod = load_tool()
    repair = mod.REPAIRS["devices-cleanup"]
    base = (REPO / "jarvis-backend" / "jarvis_gate.py").read_text(encoding="utf-8")
    base_rows = risk_table(base)
    base_row = base_rows.get("devices_cleanup")
    check("the published base carries the action's risk row",
          isinstance(base_row, tuple) and base_row[:2] == ("yes", "local"),
          repr(base_row))
    check("... and its denial is not a standing rule",
          "devices_cleanup" in _denial_actions(base),
          sorted(_denial_actions(base))[-5:])
    live = a_live_folder()
    check("a live-shaped gate without the rows has no entry to classify",
          "devices_cleanup" not in risk_table(
              (live / "jarvis_gate.py").read_text(encoding="utf-8")))
    check("the tool reports the cleanup rows missing",
          mod.check_one(live, repair) == "missing")
    check("... and one apply writes them",
          mod.apply_one(live, repair, stamp="test") == "applied")
    gate_after = (live / "jarvis_gate.py").read_text(encoding="utf-8")
    check("the repaired _RISK table is the base's own row",
          risk_table(gate_after).get("devices_cleanup") == base_row,
          repr(risk_table(gate_after).get("devices_cleanup")))
    check("... and the denial membership landed with it",
          "devices_cleanup" in _denial_actions(gate_after),
          sorted(_denial_actions(gate_after))[-5:])
    check("... exactly once each", risk_key_uses(gate_after, "devices_cleanup") == 2,
          risk_key_uses(gate_after, "devices_cleanup"))
    check("... a second apply is the idempotent no-op",
          mod.apply_one(live, repair, stamp="test-2") == "already")
    check("... it did not insert a second copy",
          risk_key_uses((live / "jarvis_gate.py").read_text(encoding="utf-8"),
                        "devices_cleanup") == 2)
    check("... with exactly one backup for the one write",
          len(list(live.glob("jarvis_gate.py.before-repair-*"))) == 1)


def load_reconcile():
    """The deploy tool, for its own patch-hunk parser - the parser a deploy uses."""
    spec = importlib.util.spec_from_file_location(
        "reconcile_for_repair_test", REPO / "tools" / "reconcile_live_backend.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["reconcile_for_repair_test"] = mod  # dataclasses looks it up by name
    spec.loader.exec_module(mod)
    return mod


def t_the_unknown_risk_repair_puts_the_published_gate_back_exactly():
    """A repaired install must EQUAL a fresh one, not merely get new text.

    The published base already carries the patch's six hunks (the fifth and
    sixth are DEF-021's 2026-10-31 `_tiers()`/`_file_tier_names()` fix and its
    revised forced-ask block). Reverse them out of it with the deploy tool's
    own parser (so the pre-image is the one the
    deploy itself expects), apply the repair to that pre-image, and the result
    must be the published base BYTE FOR BYTE. This is the proof this repo uses
    for a patch-carried change; it does not trust the repair's probe list.
    """
    mod = load_tool()
    R = load_reconcile()
    patch = (REPO / "backend" / "unknown-risk-approvable.patch").read_text(
        encoding="utf-8")
    base = (REPO / "jarvis-backend" / "jarvis_gate.py").read_text(encoding="utf-8")
    hunks = R.patch_hunks(patch, "jarvis_gate.py")
    check("the unknown-risk patch has the six hunks this repair carries",
          len(hunks) == 6, len(hunks))
    check("... and the repair carries one piece per hunk, including DEF-021's",
          len(mod.REPAIRS["unknown-risk"].parts()) == len(hunks),
          len(mod.REPAIRS["unknown-risk"].parts()))
    pre = base
    reversed_ok = True
    for hunk in reversed(hunks):
        new = "\n".join(hunk["new"])
        if pre.count(new) != 1:
            reversed_ok = False
            break
        pre = pre.replace(new, "\n".join(hunk["old"]), 1)
    check("the patch reverses out of the published base exactly once per hunk",
          reversed_ok)
    live = a_live_folder(gate=pre)
    check("the repair reports the patch's pre-image missing",
          mod.check_one(live, mod.REPAIRS["unknown-risk"]) == "missing")
    check("the repair applies to the pre-image",
          mod.apply_one(live, mod.REPAIRS["unknown-risk"], stamp="test") == "applied")
    restored = (live / "jarvis_gate.py").read_text(encoding="utf-8")
    check("the repaired gate equals the published base BYTE FOR BYTE",
          restored == base,
          f"repaired {len(restored)} B vs base {len(base)} B")
    check("every probe the repair checks for is a line the patch ADDS",
          all(probe in patch for probe in mod.REPAIRS["unknown-risk"].probes))
    fresh = a_live_folder(gate=base)
    check("a gate that already carries the change is a no-op",
          mod.apply_one(fresh, mod.REPAIRS["unknown-risk"], stamp="test") == "already")



FIXTURE_TARGET = REPO / "backend" / "fixtures" / "def-021-gate-39a0c407.txt.gz"


def live_target_gate() -> str:
    """The verified #1023 post-image, from the committed gzip fixture."""
    import gzip
    return gzip.decompress(FIXTURE_TARGET.read_bytes()).decode("utf-8")


def a_live_folder_with_exact_bytes(text: str) -> Path:
    """A repair folder whose jarvis_gate.py is text's EXACT bytes (LF, no CRLF).

    `a_live_folder` writes through text mode, which would make the hashes in
    this test meaningless on Windows; the live lineage is hash-addressed."""
    live = a_live_folder(gate=text)
    (live / "jarvis_gate.py").write_bytes(text.encode("utf-8"))
    return live


def t_live_lineage_gates_repair_to_the_1023_post_image():
    """Every accepted live gate, the idempotent no-op, and the refusal.

    The ruling names the live 5-hunk #1008 gate and the pre-#1008 gate; this
    tool also keeps the three real backups of that lineage. Each is derived by
    reversing its stored patch out of the verified post-image, so the pre-image
    bytes are the ones the tool's own table promises, not typed fixtures.
    """
    mod = load_tool()
    target = live_target_gate()
    check("the gzip fixture is the verified #1023 post-image",
          mod._sha256_text(target) == mod.LIVE_GATE_TARGET_SHA256)
    check("the repair accepts more than one live lineage",
          len(mod.LIVE_LEGACY_GATES) >= 2,
          len(mod.LIVE_LEGACY_GATES))
    for digest, _blob in mod.LIVE_LEGACY_GATES.items():
        patch = mod._legacy_patch(digest)
        check(f"{digest[:12]}… has a stored patch", bool(patch))
        pre = mod._reverse_unified_diff(target, patch)
        check(f"{digest[:12]}… reverses out of the post-image",
              mod._sha256_text(pre) == digest)
        live = a_live_folder_with_exact_bytes(pre)
        check(f"{digest[:12]}… is reported missing, not refused",
              mod.check_one(live, mod.REPAIRS["unknown-risk"]) == "missing")
        check(f"{digest[:12]}… applies",
              mod.apply_one(live, mod.REPAIRS["unknown-risk"], stamp="test") == "applied")
        landed = (live / "jarvis_gate.py").read_text(encoding="utf-8")
        check(f"{digest[:12]}… lands on the post-image BYTE FOR BYTE",
              landed == target)
        again = mod.apply_one(live, mod.REPAIRS["unknown-risk"], stamp="test-2")
        check(f"{digest[:12]}… is then the idempotent no-op", again == "already")

    fresh = a_live_folder_with_exact_bytes(target)
    check("a gate already at the post-image is a no-op",
          mod.apply_one(fresh, mod.REPAIRS["unknown-risk"], stamp="test") == "already")

    # an unrecognised live-sized gate: same anchors, one byte changed
    digest = next(iter(mod.LIVE_LEGACY_GATES))
    pre = mod._reverse_unified_diff(target, mod._legacy_patch(digest))
    unknown = pre.replace("out.update(_SYNTH_TIERS)", "out.update(_SYNTH_TIERS_unknown)", 1)
    check("the mutation really changed the bytes", unknown != pre)
    check("the unknown gate is still the right size for the guard",
          len(unknown.encode("utf-8")) >= mod.LIVE_LINEAGE_MIN_BYTES)
    live = a_live_folder_with_exact_bytes(unknown)
    before = (live / "jarvis_gate.py").read_bytes()
    refused = False
    try:
        mod.check_one(live, mod.REPAIRS["unknown-risk"])
    except mod.Refused as exc:
        refused = "not recognise" in str(exc) or "sha256" in str(exc)
    check("an unrecognised live-lineage gate is REFUSED, not guessed", refused)
    refused_write = False
    try:
        mod.apply_one(live, mod.REPAIRS["unknown-risk"], stamp="test")
    except mod.Refused:
        refused_write = True
    check("... and a refused write leaves the file and no backup",
          refused_write and (live / "jarvis_gate.py").read_bytes() == before
          and not any(live.glob("jarvis_gate.py.before-repair-*")))
    check("the published-base path is still its own (six pieces), not this one",
          len(mod.REPAIRS["unknown-risk"].parts()) == 6)


def t_a_gate_pinned_as_already_repaired_is_a_no_op():
    """The owner's live gate is a POST-#1023 shape: every probe the repair looks
    for is already in it, so the only correct answer is the idempotent no-op.
    The pin is by exact hash and it authorises no write."""
    mod = load_tool()
    live_hash = "61a34b1eff2627d9c50b7589c1f4bb4a07b0a887559fd246bc3de2507e8df0f1"
    check("the live gate's hash is pinned as already repaired",
          live_hash in mod.LIVE_GATE_ALREADY_REPAIRED)
    check("... and it is NOT in LIVE_LEGACY_GATES (those are PRE-images)",
          live_hash not in mod.LIVE_LEGACY_GATES)
    # A synthetic live-sized file proves the mechanism without shipping the
    # owner's private file. Reassign the module constant for this test only.
    synthetic = "x" * (mod.LIVE_LINEAGE_MIN_BYTES + 1)
    digest = mod._sha256_text(synthetic)
    check("a synthetic live-sized file is not pinned by accident",
          digest not in mod.LIVE_GATE_ALREADY_REPAIRED)
    mod.LIVE_GATE_ALREADY_REPAIRED = frozenset({digest})
    try:
        live = a_live_folder_with_exact_bytes(synthetic)
        before = (live / "jarvis_gate.py").read_bytes()
        check("a pinned already-repaired hash is reported already",
              mod.check_one(live, mod.REPAIRS["unknown-risk"]) == "already")
        check("... apply is the same no-op",
              mod.apply_one(live, mod.REPAIRS["unknown-risk"], stamp="test") == "already")
        check("... and nothing was written or backed up",
              not any(live.glob("jarvis_gate.py.before-repair-*")))
        check("... the file is byte-identical",
              (live / "jarvis_gate.py").read_bytes() == before)
    finally:
        mod.LIVE_GATE_ALREADY_REPAIRED = frozenset({live_hash})


def _tuple_rows(node) -> dict:
    """The str -> tuple rows of one `{...}` literal node, read with `ast`."""
    out = {}
    if not isinstance(node, ast.Dict):
        return out
    for key, value in zip(node.keys, node.values):
        if not isinstance(key, ast.Constant):
            continue
        if isinstance(value, ast.Tuple):
            try:
                out[key.value] = tuple(elt.value for elt in value.elts)
            except AttributeError:
                continue
    return out


def risk_table(text: str) -> dict:
    """Every `_RISK` row Python would build from `text` - the table the gate RUNS.

    The literal's own rows plus every module-level `_RISK.update({...})` call,
    folded in file order. This is deliberately the table Python builds and not a
    text match: `backend/test_gate_tool_actions.py` and
    `backend/test_def068_entry.py` both had to fold these calls in for the same
    reason (CLAUDE.md records the false "row missing" finding that a grep-only
    test produced on a tree where the gate answered correctly).
    """
    rows = {}
    for node in ast.parse(text).body:
        if (isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
                and node.target.id == "_RISK" and isinstance(node.value, ast.Dict)):
            rows.update(_tuple_rows(node.value))
            continue
        expr = node.value if isinstance(node, ast.Expr) else None
        call = expr if isinstance(expr, ast.Call) else None
        if call is None or not isinstance(call.func, ast.Attribute):
            continue
        owner = call.func.value
        if (call.func.attr != "update" or not isinstance(owner, ast.Name)
                or owner.id != "_RISK" or not call.args):
            continue
        rows.update(_tuple_rows(call.args[0]))
    return rows


def load_owner_check():
    """The published base's own approval-check module, loaded read-only.

    The point of the test below is the real rule that decides whether a card
    asks for Windows Hello (`jarvis_owner_check.is_risky`), not a retyped copy
    of it. The module imports nothing but the standard library.
    """
    path = REPO / "jarvis-backend" / "jarvis_owner_check.py"
    spec = importlib.util.spec_from_file_location("owner_check_for_repair_test", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["owner_check_for_repair_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def risk_key_uses(text: str, key: str) -> int:
    """How many times `key` appears as a string constant in `text`, by `ast`.

    A repair that inserted the same row twice would read 2. An AST walk cannot
    be fooled by a comment or a docstring that merely mentions the name, and it
    is not a source-text pin: this suite's own ceiling only turns down.
    """
    return sum(1 for node in ast.walk(ast.parse(text))
               if isinstance(node, ast.Constant) and node.value == key)


#: The risk record the gate gives an action with no `_RISK` row
#: (`jarvis_gate.risk_for`'s unclassified fallback, read in the base). This is
#: what the live gate handed the approval check on 2026-11-19, and why
#: `POST /api/approve` demanded Windows Hello.
UNCLASSIFIED_RISK = {"classified": False, "reversible": "no", "reach": "outbound"}


def t_the_note_edit_row_repairs_a_live_gate_without_it():
    """The measured 2026-11-19 failure: a live gate with no `edit_vault_note` row.

    Without it `risk_for("edit_vault_note")` returns the unclassified fallback,
    so the approval check treats the owner's own note append as risky and asks
    Windows Hello - which a headless battery can never answer. The repair must
    insert the published base's row byte for byte, and the result must be the
    classified `("yes", "local")` pair the base carries.
    """
    mod = load_tool()
    repair = mod.REPAIRS["note-edit"]
    owner = load_owner_check()
    base = (REPO / "jarvis-backend" / "jarvis_gate.py").read_text(encoding="utf-8")
    base_row = risk_table(base).get("edit_vault_note")
    check("the published base carries the action's risk row",
          isinstance(base_row, tuple) and base_row[:2] == ("yes", "local"),
          repr(base_row))
    base_line = next((line for line in base.splitlines()
                      if line.startswith('    "edit_vault_note": ("yes", "local",')),
                     "")
    check("... and the repair inserts that line byte for byte, not a retyped copy",
          bool(base_line) and (base_line + "\n") in repair.replace_with)
    check("... with the row itself as the positive probe",
          repair.probes == ('"edit_vault_note": ("yes", "local",',), repair.probes)

    unrepaired = a_live_folder()
    live_rows = risk_table((unrepaired / "jarvis_gate.py").read_text(encoding="utf-8"))
    check("a live-shaped gate without the row has no entry to classify",
          live_rows.get("edit_vault_note") is None)
    check("... so an unclassified card is RISKY - the Windows Hello demand the "
          "battery could not answer",
          owner.is_risky({"risk": dict(UNCLASSIFIED_RISK)}) is True)

    check("the tool reports the note-edit row missing",
          mod.check_one(unrepaired, repair) == "missing")
    check("... and one apply writes it",
          mod.apply_one(unrepaired, repair, stamp="test") == "applied")
    gate_after = (unrepaired / "jarvis_gate.py").read_text(encoding="utf-8")
    check("the repaired gate's _RISK table is the base's own row",
          risk_table(gate_after).get("edit_vault_note") == base_row,
          repr(risk_table(gate_after).get("edit_vault_note")))
    landed = risk_table(gate_after)["edit_vault_note"]
    classified = {"classified": True, "reversible": landed[0], "reach": landed[1]}
    check("... which is classified local and reversible",
          classified["classified"] is True and classified["reversible"] == "yes"
          and classified["reach"] == "local", repr(classified))
    check("... so the owner's own note-append card no longer demands Windows "
          "Hello (the real approval rule answers not-risky)",
          owner.is_risky({"risk": classified}) is False)
    check("... and exactly one row was inserted",
          risk_key_uses(gate_after, "edit_vault_note") == 1,
          risk_key_uses(gate_after, "edit_vault_note"))
    check("... a second apply is the idempotent no-op",
          mod.apply_one(unrepaired, repair, stamp="test-2") == "already")
    gate_after_again = (unrepaired / "jarvis_gate.py").read_text(encoding="utf-8")
    check("... it did not insert a second copy",
          risk_key_uses(gate_after_again, "edit_vault_note") == 1,
          risk_key_uses(gate_after_again, "edit_vault_note"))
    check("... with exactly one backup for the one write",
          len(list(unrepaired.glob("jarvis_gate.py.before-repair-*"))) == 1)


def t_a_gate_that_already_has_the_note_edit_row_is_a_no_op():
    """The published base already carries the row: nothing may be staged.

    This is the "no double insert" control. The base is used as the fixture, so
    a repair that looked for the wrong probe (or inserted unconditionally) would
    show up as a write here.
    """
    mod = load_tool()
    repair = mod.REPAIRS["note-edit"]
    base = (REPO / "jarvis-backend" / "jarvis_gate.py").read_text(encoding="utf-8")
    live = a_live_folder(gate=base)
    before = (live / "jarvis_gate.py").read_bytes()
    check("a gate that already has the row is reported already",
          mod.check_one(live, repair) == "already")
    check("... apply is the same no-op", mod.apply_one(live, repair, stamp="test") == "already")
    check("... and nothing was written",
          (live / "jarvis_gate.py").read_bytes() == before)
    check("... and no backup was left behind",
          not any(live.glob("jarvis_gate.py.before-repair-*")))
    check("... and the row is still there exactly once",
          # The count is of the RISK ROW, not of the bare name: the gate's
          # `_TOOL_ACTIONS` table legitimately carries `"edit_vault_note"` as
          # the action for the hub-note tool since 2026-11-20 (PM2), so a bare
          # name count would read 2 on a correct file.
          (live / "jarvis_gate.py").read_text(encoding="utf-8")
          .count('"edit_vault_note": ("yes", "local"') == 1)


def t_a_gate_with_the_wrong_shape_refuses_the_note_edit_row():
    """An anchor the tool cannot prove is REFUSED, and nothing is written."""
    mod = load_tool()
    repair = mod.REPAIRS["note-edit"]
    live = a_live_folder(gate="RISK = {}\n")     # no `_RISK` literal to anchor on
    before = (live / "jarvis_gate.py").read_bytes()
    refused = False
    try:
        mod.apply_one(live, repair, stamp="test")
    except mod.Refused as exc:
        refused = "anchor" in str(exc).lower() or "appear" in str(exc).lower()
    check("a gate with no expected anchor is REFUSED, not guessed", refused)
    check("... and the file is byte-identical afterwards",
          (live / "jarvis_gate.py").read_bytes() == before)
    check("... and no backup was left behind",
          not any(live.glob("jarvis_gate.py.before-repair-*")))


def main():
    try:
        for name, fn in list(globals().items()):
            if name.startswith("t_") and callable(fn):
                print(f"--- {name} ---")
                try:
                    fn()
                except Exception as exc:  # pragma: no cover
                    traceback.print_exc()
                    check(f"{name} ran without crashing", False, repr(exc))
    finally:
        pass
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


def t_the_connect_mail_row_repairs_a_live_gate_without_it():
    """DEF-096 (2026-11-25): the mailbox connect card's own action.

    The card itself works without the row - a name with no `[autonomy.tiers]`
    line takes `unknown_action_tier`, "ask" on this PC - so this repair is about
    the GATE'S OWN RECORD: without it `risk_for("connect_mail")` answers the
    unclassified fallback, "permanent and able to leave this PC", which is false
    of a Credential Manager write and one IMAP count. The repair must insert the
    published base's row byte for byte, in one write, and be a no-op afterwards.
    """
    mod = load_tool()
    repair = mod.REPAIRS["connect-mail"]
    owner = load_owner_check()
    base = (REPO / "jarvis-backend" / "jarvis_gate.py").read_text(encoding="utf-8")
    base_row = risk_table(base).get("connect_mail")
    check("the published base carries the action's risk row",
          isinstance(base_row, tuple) and base_row[:2] == ("yes", "local"),
          repr(base_row))
    base_line = next((line for line in base.splitlines()
                      if line.startswith('    "connect_mail": ("yes", "local",')),
                     "")
    check("... and the repair inserts that line byte for byte, not a retyped copy",
          bool(base_line) and (base_line + "\n") in repair.replace_with)
    check("... with the row itself as the positive probe",
          repair.probes == ('"connect_mail": ("yes", "local"',), repair.probes)

    unrepaired = a_live_folder()
    live_rows = risk_table((unrepaired / "jarvis_gate.py").read_text(encoding="utf-8"))
    check("a live-shaped gate without the row has no entry to classify",
          live_rows.get("connect_mail") is None)
    check("... so an unclassified card would be RISKY, which this action is not",
          owner.is_risky({"risk": dict(UNCLASSIFIED_RISK)}) is True)

    check("the tool reports the connect-mail row missing",
          mod.check_one(unrepaired, repair) == "missing")
    check("... and one apply writes it",
          mod.apply_one(unrepaired, repair, stamp="test") == "applied")
    gate_after = (unrepaired / "jarvis_gate.py").read_text(encoding="utf-8")
    check("the repaired gate's _RISK table is the base's own row",
          risk_table(gate_after).get("connect_mail") == base_row,
          repr(risk_table(gate_after).get("connect_mail")))
    landed = risk_table(gate_after)["connect_mail"]
    classified = {"classified": True, "reversible": landed[0], "reach": landed[1]}
    check("... which is classified local and reversible",
          classified["reversible"] == "yes" and classified["reach"] == "local",
          repr(classified))
    check("... so a card for it is not treated as permanent and outbound",
          owner.is_risky({"risk": classified}) is False)
    check("... and exactly one row was inserted",
          risk_key_uses(gate_after, "connect_mail") == 1,
          risk_key_uses(gate_after, "connect_mail"))
    check("... a second apply is the idempotent no-op",
          mod.apply_one(unrepaired, repair, stamp="test-2") == "already")
    check("... it did not insert a second copy",
          risk_key_uses((unrepaired / "jarvis_gate.py").read_text(encoding="utf-8"),
                        "connect_mail") == 1)
    check("... with exactly one backup for the one write",
          len(list(unrepaired.glob("jarvis_gate.py.before-repair-*"))) == 1)


if __name__ == "__main__":
    sys.exit(main())
