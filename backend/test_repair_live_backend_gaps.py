"""test_repair_live_backend_gaps.py - proves the repair tool behaves safely.

The tool fixes three base-file pieces this PC's install never received:
the app builder's two `_RISK` rows in `jarvis_gate.py`, the
`/api/history/pin` + `/api/history/archive` POST routes in `jarvis_hud.py`,
and the owner's card timer (`expires_in`). The timer is TWO hunks of
`backend/show-card-timer.patch`: the block in `pending()` AND the SELECT line
that gives it a `waited_until` column. A tool that inserts only the block is a
silent no-op, so the tests below prove both hunks land and that a half-applied
file is REFUSED rather than written again.

It writes into the LIVE backend folder, so every failure path matters more
than the happy one: a missing or ambiguous anchor must refuse, an already
repaired file must be a no-op, a broken rewrite must be rolled back, and the
live folder must never be left half-written.

Run: python -B backend/test_repair_live_backend_gaps.py
"""
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


def a_live_folder(gate: str = None, hud: str = None) -> Path:
    d = Path(tempfile.mkdtemp(prefix="repair-gaps-"))
    (d / "jarvis_gate.py").write_text(
        gate if gate is not None else
        "_RISK: dict[str, tuple[str, str, str]] = {\n"
        '    "web_research": ("yes", "outbound", "a public query leaves the machine"),\n'
        "}\n"
        "def pending():\n"
        "    d = {}\n"
        "    sql = (\n"
        '            "SELECT id,action,tier,detail,prompt,created,raised FROM approvals"\n'
        "            \" WHERE state='pending' ORDER BY created\")\n"
        "    if d:\n"
        "        # Why this is being asked about at all, when the table said otherwise.\n"
        "        pass\n"
        "    return d\n",
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
    hud = (live / "jarvis_hud.py").read_text(encoding="utf-8")
    check("both history routes landed", '"/api/history/pin"' in hud
          and '"/api/history/archive"' in hud)
    check("the card timer landed in pending()",
          'd["expires_in"] = _whole' in gate and "_waited = d.pop" in gate)
    check("the anchor line was kept", '"/api/history/mark"' in hud)
    check("a backup of each written file exists",
          any(live.glob("jarvis_gate.py.before-repair-*"))
          and any(live.glob("jarvis_hud.py.before-repair-*")))
    check("nothing else was touched", sorted(p.name for p in live.iterdir()
                                              if not p.name.startswith("__pycache__")) ==
          sorted(["jarvis_gate.py", "jarvis_hud.py",
                  next(p.name for p in live.glob("jarvis_gate.py.before-repair-*")),
                  next(p.name for p in live.glob("jarvis_hud.py.before-repair-*"))]))


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


if __name__ == "__main__":
    sys.exit(main())
