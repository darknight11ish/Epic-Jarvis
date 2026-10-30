"""Exercise the appearance helpers against the real spec.

    python3 backend/test_appearance.py path/to/patched/jarvis_hud.py


`py_compile` said the patch was fine while `time` was unimported and the
palette walk found zero colours. Neither is a syntax error; both would have
shipped. So this extracts the appearance helpers and runs them.

Since 2026-10-26 it also proves the MERGE: a save that names one key keeps
the other half's stored value, which is the defect a fresh phone pushing its
colours could hit (it sends `bindings` and leaves a blank face out, so the
old replace-everything write cleared the face the desktop was wearing).

WHERE THE HELPERS COME FROM. `jarvis_hud.py` is the owner's own file and is not
in this repository, so in CI this suite used to be skipped BY NAME and its 14
checks ran nowhere but the owner's PC (`backend/run_suites.py`'s NEEDS_OWNER
list). The block it reads - `APPEARANCE_FILE` through `_appearance_save` - is
written by `appearance.patch` alone, so the whole patch stack's text for that
file HAS it: `_hud_text()` below uses the real file when this machine has one
and the stand-in built by `backend/_stack.py` when it does not. Taking the
suite off that list is what puts these 14 checks in CI (2026-10-10).
"""
import json
import os, re, sys, time, tempfile
from pathlib import Path

HERE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE_DIR))
# BACKEND is where the modules under test actually live - this folder in
# the dev container, $JARVIS_BACKEND on a real install. REPO is this
# repository. They used to be the same path and are not on the machine
# that runs Jarvis.
from _where import BACKEND, REPO, missing, explain
HUD = Path(sys.argv[1]) if len(sys.argv) > 1 else BACKEND / "jarvis_hud.py"


def _hud_text() -> str:
    """`jarvis_hud.py`'s text: the real file if this machine has one, else the
    patch stack's stand-in for it (`backend/_stack.py`).

    A path given on the command line is used as given, and its absence is an
    error - the caller named it. Nobody named anything, so BACKEND is either
    this repository (CI: no such file) or a real install (the file is there).
    """
    if HUD.is_file():
        return HUD.read_text(encoding="utf-8")
    if len(sys.argv) > 1:
        raise SystemExit(f"no such file: {HUD}")
    import _stack
    text, log = _stack.stand_in("jarvis_hud.py")
    if not text:
        # No git, or a hunk that will not apply even to its own pre-image. A
        # skip with a reason, never a pass: the runner reads the summary line,
        # so "0 passed, 1 skipped" is honest and is not the shape it refuses
        # (exit 0 having reported nothing at all).
        print(f"skip  the appearance helpers - {HUD.name} is not here and the "
              f"patch stack could not be built: {'; '.join(log[-2:])}")
        print("\n0 passed, 1 skipped, 0 failed")
        sys.exit(0)
    return text


SRC = _hud_text()
SPEC = REPO / "jarvis-desktop" / "src" / "jarvis-visual-spec.json"

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
    ns["_appearance_save"]({"face": "orbit",
                            "bindings": {"idle": {"pattern": "solid", "color": "ice-3"}}})
    ns["_appearance_save"]({"face": "spiral"})
    kinds = [k for k, _ in ns.get("published", [])]
    assert kinds == ["appearance", "appearance"], kinds
    # The event carries the MERGED document: the desktop and the phone both
    # repaint from this body, so a face-only save that published a body with
    # no bindings would blank the colours on every open client.
    doc = ns["published"][-1][1]
    assert doc["face"] == "spiral", doc
    assert doc["bindings"]["idle"]["pattern"] == "solid", doc
check("a save publishes the merged document so the other client repaints", publishes)

# ---------------------------------------------------------------- the merge ----
#
# `_appearance_save` used to REPLACE the whole document, and that was a real
# defect rather than a style: three writers send three different shapes. The
# phone sends `bindings` and only sends `face` once its owner has picked one
# (`AppearanceStore.toSyncDocument`), so the first colour change from a fresh
# phone wrote `face: null` and erased the face the desktop was wearing. These
# checks pin the merge: a key that is present replaces, a key that is absent
# keeps its stored value, and clearing is the one thing that must be said out
# loud.

def face_only_keeps_the_colours():
    ns["_appearance_save"]({"face": "orbit",
                            "bindings": {"idle": {"pattern": "pulse", "color": "violet-4"},
                                         "thinking": {"pattern": "sweep",
                                                      "params": {"offset_deg": 246}}}})
    code, out = ns["_appearance_save"]({"face": "arc"})
    assert code == 200, (code, out)
    view = ns["_appearance_view"]()
    assert view["face"] == "arc", view
    assert view["bindings"]["idle"] == {"pattern": "pulse", "color": "violet-4"}, view
    assert view["bindings"]["thinking"]["pattern"] == "sweep", view
check("a face-only save changes the face and leaves every colour binding", face_only_keeps_the_colours)

def bindings_only_keeps_the_face():
    ns["_appearance_save"]({"face": "redpanda",
                            "bindings": {"idle": {"pattern": "solid", "color": "ice-3"}}})
    code, out = ns["_appearance_save"]({"bindings": {
        "thinking": {"pattern": "comet", "color": "amber-4"}}})
    assert code == 200, (code, out)
    view = ns["_appearance_view"]()
    # This is the pre-existing defect the merge fixes: the phone's fresh
    # colour push used to leave this None.
    assert view["face"] == "redpanda", view
    assert view["bindings"]["thinking"]["pattern"] == "comet", view
check("a bindings-only save keeps the face", bindings_only_keeps_the_face)

def null_clears_the_face():
    ns["_appearance_save"]({"face": "orbit",
                            "bindings": {"idle": {"pattern": "solid", "color": "ice-3"}}})
    code, out = ns["_appearance_save"]({"face": None})
    assert code == 200, (code, out)
    view = ns["_appearance_view"]()
    assert view["face"] is None, view
    assert view["bindings"]["idle"]["pattern"] == "solid", view
check("an explicit null clears the face and nothing else", null_clears_the_face)

def empty_bindings_clear_them():
    ns["_appearance_save"]({"face": "orbit",
                            "bindings": {"idle": {"pattern": "solid", "color": "ice-3"}}})
    code, out = ns["_appearance_save"]({"bindings": {}})
    assert code == 200, (code, out)
    view = ns["_appearance_view"]()
    assert view["bindings"] == {}, view
    assert view["face"] == "orbit", view
check("an explicit empty bindings clears them and keeps the face", empty_bindings_clear_them)

def unknown_fields_are_ignored():
    ns["_appearance_save"]({"face": "orbit",
                            "bindings": {"idle": {"pattern": "solid", "color": "ice-3"}}})
    before = ns["_appearance_view"]()
    code, out = ns["_appearance_save"]({"theme": "midnight"})
    assert code == 200, (code, out)
    after = ns["_appearance_view"]()
    assert after["face"] == before["face"], (before, after)
    assert after["bindings"] == before["bindings"], (before, after)
    assert after["updated"] > before["updated"], (before, after)
check("an unknown field is ignored and the stored document survives it",
      unknown_fields_are_ignored)

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

# -------------------------------------------------------- the Galaxy's look ----
#
# "Galaxy models": the owner's ask of 2026-10-28 was that the face model AND the
# Galaxy follow one another between the desktop and the phone. The look used to
# be a per-device `localStorage` key on the PC that nothing else could see; now
# it is a key in this same document, so it is one value both apps read, and the
# `appearance` event carries it to whichever app is open.
#
# These checks pin the part that is the SERVER's: the look list comes from the
# page module that builds the looks (never typed here), an id it does not know
# is refused, and the merge keeps the look when a save is about the face or the
# colours.

def galaxy_looks_are_the_modules_own():
    looks = ns["_galaxy_looks"]()
    assert looks, "no galaxy-presets.js found - the look cannot be checked"
    # The default first, then every built look, in the module's own order.
    assert looks[0] == "constellation", looks
    assert "planetary-orbit" in looks, looks
    assert "zen-ring" in looks, looks
    # Read from the module, not typed: the count is the module's own.
    js = (REPO / "jarvis-desktop" / "src" / "galaxy-presets.js").read_text(encoding="utf-8")
    built = js.split("BUILT_PRESETS = Object.freeze([", 1)[1].split("])", 1)[0]
    assert len(built.split("{ id:")) - 1 == len(looks) - 1, (looks, built[:80])
check("the galaxy look list is the page module's own", galaxy_looks_are_the_modules_own)

def a_known_look_is_kept():
    code, out = ns["_appearance_save"]({"galaxy": "planetary-orbit"})
    assert code == 200, (code, out)
    view = ns["_appearance_view"]()
    assert view["galaxy"] == "planetary-orbit", view
check("a galaxy look the module builds is stored", a_known_look_is_kept)

def an_unknown_look_is_refused():
    before = ns["_appearance_view"]()
    code, out = ns["_appearance_save"]({"galaxy": "hypercube"})
    assert code == 400, (code, out)
    assert "hypercube" in out.get("error", ""), out
    after = ns["_appearance_view"]()
    assert after["galaxy"] == before["galaxy"], (before, after)
    assert after["updated"] == before["updated"], "a refused save changed the file"
check("a galaxy look no renderer knows is refused, not dropped", an_unknown_look_is_refused)

def the_three_keys_do_not_erase_each_other():
    ns["_appearance_save"]({"face": "orbit",
                            "bindings": {"idle": {"pattern": "solid", "color": "ice-3"}},
                            "galaxy": "nebula"})
    # A face-only save, from the Faces window or the HUD's faces icon.
    code, out = ns["_appearance_save"]({"face": "redpanda"})
    assert code == 200, (code, out)
    # A look-only save, from the Look switch.
    code, out = ns["_appearance_save"]({"galaxy": "dna-helix"})
    assert code == 200, (code, out)
    # A colours-only save, from the phone.
    code, out = ns["_appearance_save"]({"bindings": {"thinking": {"pattern": "comet"}}})
    assert code == 200, (code, out)
    view = ns["_appearance_view"]()
    assert view["face"] == "redpanda", view
    assert view["galaxy"] == "dna-helix", view
    # `bindings` is the one key that replaces rather than merges inside itself:
    # the caller sends the map it means, and the phone sends all eight states.
    # That is the written rule, so this pins it rather than lamenting it.
    assert view["bindings"] == {"thinking": {"pattern": "comet"}}, view
check("the face, the look and the colours never erase one another",
      the_three_keys_do_not_erase_each_other)

def a_look_can_be_cleared():
    ns["_appearance_save"]({"face": "orbit", "bindings": {"idle": {"pattern": "solid"}},
                            "galaxy": "star-map"})
    code, out = ns["_appearance_save"]({"galaxy": None})
    assert code == 200, (code, out)
    view = ns["_appearance_view"]()
    assert view["galaxy"] is None, view
    # Clearing the look clears nothing else - the same rule as the face.
    assert view["face"] == "orbit", view
    assert view["bindings"]["idle"]["pattern"] == "solid", view
check("an explicit null clears the look and nothing else", a_look_can_be_cleared)

def the_event_carries_the_look():
    ns["published"] = []
    ns["_appearance_save"]({"galaxy": "radar-dome"})
    doc = ns["published"][-1][1]
    assert doc["galaxy"] == "radar-dome", doc
    # The event is the whole merged document, so a client that repaints from
    # it - which is every open client - never loses the face or the colours.
    assert "face" in doc and "bindings" in doc, doc
check("the appearance event carries the look with the rest of the document",
      the_event_carries_the_look)

print("" if not fails else f"\n{len(fails)} failed: {fails}")
sys.exit(1 if fails else 0)
