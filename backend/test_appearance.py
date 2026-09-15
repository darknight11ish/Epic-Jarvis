"""Exercise the appearance helpers against the real spec.

    python3 backend/test_appearance.py path/to/patched/jarvis_hud.py


`py_compile` said the patch was fine while `time` was unimported and the
palette walk found zero colours. Neither is a syntax error; both would have
shipped. So this extracts the four helpers and runs them.
"""
import json
import os, re, sys, time, tempfile
from pathlib import Path

SRC = Path(sys.argv[1] if len(sys.argv) > 1 else "jarvis_hud.py").read_text(encoding="utf-8")
SPEC = Path(__file__).resolve().parent.parent / "jarvis-desktop" / "src" / "jarvis-visual-spec.json"

# Pull the block from APPEARANCE_FILE to the end of _appearance_save.
start = SRC.index("APPEARANCE_FILE = CONFIG_DIR")
end = SRC.index("def _desktop_action")
block = SRC[start:end]

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
