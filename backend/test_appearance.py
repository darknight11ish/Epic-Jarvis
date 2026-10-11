"""Exercise the appearance helpers against the real spec.

    python3 backend/test_appearance.py path/to/patched/jarvis_hud.py


`py_compile` said the patch was fine while `time` was unimported and the
palette walk found zero colours. Neither is a syntax error; both would have
shipped. So this extracts the four helpers and runs them.
"""
import json
import os, re, sys, time, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# BACKEND is where the modules under test actually live - this folder in
# the dev container, $JARVIS_BACKEND on a real install. REPO is this
# repository. They used to be the same path and are not on the machine
# that runs Jarvis.
from _where import BACKEND, REPO, missing, explain, hud_block
SPEC = REPO / "jarvis-desktop" / "src" / "jarvis-visual-spec.json"

# THE APPEARANCE HELPERS, OUT OF THE PATCHED jarvis_hud.py.
#
# jarvis_hud.py is the entry point scripts/apply-patches.ps1 edits IN PLACE, so
# a clone's backend/ does not hold it and this read used to be a
# FileNotFoundError before one check - a suite that reported a broken patch
# when what it was missing was one file only the owner's PC has.
#
# This suite never looks at the surrounding file: it drives one self-contained
# block of it (four helpers) against the repository's real spec. That block is
# the text the patch stack itself writes, so in a clone this reads the block
# from the stack's own stand-in and SAYS SO - see _where.hud_block, which also
# refuses a block the stack could not rebuild whole. Everything a stand-in
# cannot honestly give (a route that must still be wired into main(), an
# import that must still sit inside a try:) is a different suite's business,
# and those skip instead.
START, END = "APPEARANCE_FILE = CONFIG_DIR", "def _desktop_action"
if len(sys.argv) > 1:
    # A person naming a built file, which is what the docstring above offers:
    # taken at their word, so a path that is wrong or a file without the block
    # is a real error rather than something skipped quietly.
    WHERE = sys.argv[1]
    SRC = Path(WHERE).read_text(encoding="utf-8")
    try:
        block = SRC[SRC.index(START):SRC.index(END)]
    except ValueError:
        raise SystemExit(f"FAIL  {WHERE} does not hold both `{START}` and `{END}`, "
                         f"so it is not a patched jarvis_hud.py")
else:
    block, WHERE = hud_block(START, END)
    if block is None:
        print(f"skip  the four appearance helpers are read out of jarvis_hud.py, "
              f"and {WHERE}")
        print("\n0 passed, 1 skipped, 0 failed")
        sys.exit(0)
    if WHERE != str(BACKEND / "jarvis_hud.py"):
        print(f"note  no jarvis_hud.py in {BACKEND}, so this run drives the block "
              f"the patch stack itself writes - {WHERE}. The same four helpers, "
              f"against the same real spec; read _where.hud_block for what that "
              f"does and does not prove. {explain()}")


tmp = Path(tempfile.mkdtemp())
ns = {
    # `os` because _visual_spec consults JARVIS_VISUAL_SPEC before the
    # filesystem candidates - an explicit path is the only thing that survives
    # someone moving either tree.
    "json": json, "time": time, "Path": Path, "os": os,
    "CONFIG_DIR": tmp, "HERE": SPEC.parent,
    "_publish": lambda kind, data: ns.setdefault("published", []).append((kind, data)),
}
exec(compile(block, "helpers", "exec"), ns)

fails = []
def check(name, fn):
    try:
        fn(); print(f"ok    {name}")
    except AssertionError as e:
        fails.append(name); print(f"FAIL  {name}\n      {e}")

def check_(body):
    return ns["_appearance_check"](body)

def assert_(cond, msg=""):
    assert cond, msg
    return True

def spec_found():
    spec = ns["_visual_spec"]()
    assert spec, "no spec found"
    assert len(spec["palette"]["colors"]) == 50, len(spec["palette"]["colors"])
check("the spec is found and carries all fifty colours", spec_found)

check("an empty document is valid", lambda: assert_(check_({}) == ""))

check("a good binding is accepted", lambda: assert_(
    check_({"face": "orbit", "bindings": {"idle": {"pattern": "breathe", "color": "ice-3"}}}) == "",
    check_({"face": "orbit", "bindings": {"idle": {"pattern": "breathe", "color": "ice-3"}}})))

check("an unknown colour is REFUSED, not dropped", lambda: assert_(
    "chartreuse-9" in check_({"bindings": {"idle": {"pattern": "solid", "color": "chartreuse-9"}}}),
    f'got {check_({"bindings": {"idle": {"pattern": "solid", "color": "chartreuse-9"}}})!r}'))

check("an unknown pattern is refused", lambda: assert_(
    "wobble" in check_({"bindings": {"idle": {"pattern": "wobble"}}})))

check("an unknown face is refused", lambda: assert_(
    "zorb" in check_({"face": "zorb", "bindings": {}})))

check("an unknown state is refused", lambda: assert_(
    "daydreaming" in check_({"bindings": {"daydreaming": {"pattern": "solid"}}})))

check("banked is a state this server accepts", lambda: assert_(
    check_({"bindings": {"banked": {"pattern": "solid", "color": "neutral-2"}}}) == ""))

check("a binding with no pattern is refused", lambda: assert_(
    "needs a pattern" in check_({"bindings": {"idle": {"color": "ice-3"}}})))

def round_trip():
    code, out = ns["_appearance_save"]({"face": "orbit",
                                        "bindings": {"idle": {"pattern": "pulse", "color": "violet-4"}}})
    assert code == 200, (code, out)
    assert out["ok"] and out["updated"] > 0, out
    # No "stored without checking" note: the spec was found.
    assert "note" not in out, out
    view = ns["_appearance_view"]()
    assert view["available"] is True
    assert view["face"] == "orbit", view
    assert view["bindings"]["idle"]["pattern"] == "pulse", view
    assert view["updated"] == out["updated"], view
check("a save round-trips through the file", round_trip)

def rejected_writes_nothing():
    before = ns["_appearance_view"]()
    code, out = ns["_appearance_save"]({"bindings": {"idle": {"pattern": "nope"}}})
    assert code == 400, (code, out)
    after = ns["_appearance_view"]()
    assert after["updated"] == before["updated"], "a refused save changed the file"
check("a refused save leaves the stored document alone", rejected_writes_nothing)

def publishes():
    ns["published"] = []
    ns["_appearance_save"]({"bindings": {"idle": {"pattern": "solid", "color": "ice-3"}}})
    kinds = [k for k, _ in ns.get("published", [])]
    assert kinds == ["appearance"], kinds
check("a save publishes an event so the other client repaints", publishes)

def no_spec_says_so():
    ns2 = dict(ns); ns2["CONFIG_DIR"] = Path(tempfile.mkdtemp()); ns2["HERE"] = Path("/nonexistent")
    exec(compile(block, "helpers", "exec"), ns2)
    code, out = ns2["_appearance_save"]({"bindings": {"idle": {"pattern": "anything-at-all"}}})
    # Stored, because refusing every write on a machine without the spec would
    # brick the feature — but it says it could not check.
    assert code == 200, (code, out)
    assert "without checking" in out.get("note", ""), out
check("with no spec it stores and says it could not validate", no_spec_says_so)

def corrupt_file_recovers():
    d = Path(tempfile.mkdtemp())
    (d / "appearance.json").write_text("{not json", encoding="utf-8")
    ns3 = dict(ns); ns3["CONFIG_DIR"] = d
    exec(compile(block, "helpers", "exec"), ns3)
    view = ns3["_appearance_view"]()
    assert view["available"] is True and "error" in view, view
    assert view["bindings"] == {}, view
check("a corrupt file reports itself instead of taking the surface down", corrupt_file_recovers)

print("" if not fails else f"\n{len(fails)} failed: {fails}")
sys.exit(1 if fails else 0)
