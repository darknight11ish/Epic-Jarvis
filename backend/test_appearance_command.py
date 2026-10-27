"""Ask Jarvis for a face, and the face changes on both apps (2026-10-26).

    python3 backend/test_appearance_command.py

WHAT THIS PROVES, AND AGAINST WHICH TEXT

The owner's request: *"I'd like to be able to ask Jarvis on desktop to change
the Jarvis face model ... and it would change it on my phone and desktop,
including if I ask on the android app."* The face and its state colours already
lived in one document both clients follow; what was missing was a way to ASK.
The pieces are:

  `_appearance_faces()` / `_appearance_set_face()`   backend/appearance.patch
  `ChoiceSetting("face")` / `set_face()`             backend/jarvis_settings_registry.py
  the phrases                                        backend/jarvis_quick.py

`jarvis_hud.py` is the owner's file and is not in this repository, so this
builds the patch stack's stand-in for it (the same `backend/_stack.py` walk
`test_appearance.py` uses) and installs it as the `jarvis_hud` module the
registry looks for - exactly the module a running server is. Nothing here
claims the owner's installed backend has the patch: `set_face`'s own
"run apply-patches.ps1" answer is checked below, because that is the honest
answer on a PC that has not applied it yet.

The six sentences the owner asked for are checked one by one, and so is the
refusal of a face that does not exist - with the REAL list, never a guess.
"""
import json
import os
import sys
import threading
import time
import tempfile
import types
from pathlib import Path

HERE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE_DIR))
from _where import REPO  # noqa: E402

import _stack  # noqa: E402

SPEC = REPO / "jarvis-desktop" / "src" / "jarvis-visual-spec.json"

SRC, LOG = _stack.stand_in("jarvis_hud.py")
if not SRC:
    print("skip  the face-by-asking checks - the patch stack could not be built: "
          + "; ".join(LOG[-2:]))
    print("\n0 passed, 1 skipped, 0 failed")
    sys.exit(0)

# The block appearance.patch writes: APPEARANCE_FILE through _appearance_save
# and the two functions this feature adds, ending where _desktop_action begins.
START = SRC.index("APPEARANCE_FILE = CONFIG_DIR")
END = SRC.index("def _desktop_action")
BLOCK = SRC[START:END]


def namespace(*, here, config_dir):
    """The appearance helpers, exec'd with a temp store and a real spec."""
    ns = {
        "json": json, "time": time, "Path": Path, "os": os,
        "threading": threading,
        "CONFIG_DIR": config_dir, "HERE": here,
        "_publish": lambda kind, data: ns.setdefault("published", []).append((kind, data)),
    }
    exec(compile(BLOCK, "appearance_helpers", "exec"), ns)
    return ns


def install(ns, name="jarvis_hud"):
    """Make `ns` the `jarvis_hud` module (what a running server is), and return
    the previous module so a check can put it back."""
    mod = types.ModuleType(name)
    for key, value in ns.items():
        if not key.startswith("__"):
            setattr(mod, key, value)
    previous = sys.modules.get(name)
    sys.modules[name] = mod
    return previous


TMP = Path(tempfile.mkdtemp())
NS = namespace(here=SPEC.parent, config_dir=TMP)
PREVIOUS = install(NS)

import jarvis_quick as Q          # noqa: E402  (after the stub is installed)
import jarvis_settings_registry as R  # noqa: E402

FAILS = []


def check(name, fn):
    try:
        fn()
        print(f"ok    {name}")
    except AssertionError as exc:
        FAILS.append(name)
        print(f"FAIL  {name}\n      {exc}")


def spec_faces():
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    return [(str(f["id"]), str(f.get("name") or f["id"])) for f in spec["faces"]]


def a_full_document():
    """A stored document with a face and the phone's colour bindings in it."""
    code, out = NS["_appearance_save"]({
        "face": "orbit",
        "bindings": {"idle": {"pattern": "solid", "color": "ice-3"},
                     "thinking": {"pattern": "sweep",
                                  "params": {"offset_deg": 246, "span_deg": 58}}},
    })
    assert code == 200, (code, out)
    return NS["_appearance_view"]()


def recorded_save():
    """Replace `_appearance_save` with a recorder; returns its list of bodies."""
    bodies = []
    original = NS["_appearance_save"]

    def record(body):
        bodies.append(json.loads(json.dumps(body)))
        return original(body)

    NS["_appearance_save"] = record
    # `_appearance_set_face` calls it through the namespace, so the recorder is
    # the one it reaches; the module attribute has to agree for the registry's
    # lookups that go through the module.
    setattr(sys.modules["jarvis_hud"], "_appearance_save", record)
    return bodies


def restore_save(_bodies):
    NS["_appearance_save"] = _ORIGINAL_SAVE
    setattr(sys.modules["jarvis_hud"], "_appearance_save", _ORIGINAL_SAVE)


_ORIGINAL_SAVE = NS["_appearance_save"]


# ---------------------------------------------------------------- the patch ---

def t_the_face_list_is_the_spec_s_own():
    faces = NS["_appearance_faces"]()
    assert [(f["id"], f["name"]) for f in faces] == spec_faces(), faces


check("the face list is the visual spec's own, ids and display names",
      t_the_face_list_is_the_spec_s_own)


def t_the_registry_reads_the_s_rvers_list():
    ids = {f["id"] for f in NS["_appearance_faces"]()}
    assert set(R._face_choices().values()) == ids, R._face_choices()
    assert R._face_label("redpanda") == "Red Panda", R._face_label("redpanda")


check("the registry's valid list is the patch's own list, not a second copy",
      t_the_registry_reads_the_s_rvers_list)


def t_the_contract_records_the_measured_face_list():
    """The contract's options map is a RECORD of what the owner can say - so it
    is pinned to the measured list, not trusted to stay in step by hand."""
    contract = json.loads((REPO / "contract" / "feature-controls.json")
                          .read_text(encoding="utf-8"))
    row = next((x for x in contract.get("choice_settings") or []
                if x.get("key") == "face"), None)
    assert row is not None, "the face is missing from the contract's choice_settings"
    assert row.get("status") == "enforced", row
    measured = dict(sorted(R._choice("face").options().items()))
    assert row.get("options") == measured, (row.get("options"), measured)
    assert set(measured.values()) == {f["id"] for f in NS["_appearance_faces"]()}, measured


check("the contract's face list is the measured one, not a hand-typed copy",
      t_the_contract_records_the_measured_face_list)


def t_one_face_write_keeps_the_colours():
    before = a_full_document()
    code, out = NS["_appearance_set_face"]("spiral")
    assert code == 200, (code, out)
    after = NS["_appearance_view"]()
    assert after["face"] == "spiral", after
    assert after["bindings"] == before["bindings"], (before, after)


check("one face write changes only `face` and keeps every colour binding",
      t_one_face_write_keeps_the_colours)


def t_the_event_carries_the_merged_document():
    a_full_document()
    NS["published"] = []
    NS["_appearance_set_face"]("redpanda")
    kinds = [k for k, _ in NS["published"]]
    assert kinds == ["appearance"], kinds
    doc = NS["published"][-1][1]
    assert doc["face"] == "redpanda", doc
    assert doc["bindings"]["idle"]["pattern"] == "solid", doc


check("the appearance event carries the merged document both apps repaint from",
      t_the_event_carries_the_merged_document)


def t_an_unknown_face_is_refused_with_the_real_names():
    before = a_full_document()
    code, out = NS["_appearance_set_face"]("zorb")
    assert code == 400, (code, out)
    names = out.get("faces") or []
    assert "Red Panda" in names and "Spiral" in names and len(names) == len(spec_faces()), names
    assert NS["_appearance_view"]()["updated"] == before["updated"], "a refused face changed the file"


check("an unknown face is refused with the real names and writes nothing",
      t_an_unknown_face_is_refused_with_the_real_names)


def t_no_spec_refuses_rather_than_guessing():
    ns2 = namespace(here=Path(tempfile.mkdtemp()), config_dir=Path(tempfile.mkdtemp()))
    previous = install(ns2)
    try:
        assert ns2["_appearance_faces"]() == [], ns2["_appearance_faces"]()
        code, out = ns2["_appearance_set_face"]("spiral")
        assert code == 503, (code, out)
        assert "jarvis-visual-spec.json" in str(out.get("reason") or ""), out
    finally:
        if previous is not None:
            sys.modules["jarvis_hud"] = previous
        else:
            sys.modules.pop("jarvis_hud", None)


check("a PC with no spec refuses in words rather than storing a guess",
      t_no_spec_refuses_rather_than_guessing)


# ------------------------------------------------------------- the setter ----

def t_the_answer_names_the_face_both_apps_and_the_voice():
    a_full_document()
    bodies = recorded_save()
    try:
        out = R.set_face("spiral")
    finally:
        restore_save(bodies)
    assert out.ok, out
    said = out.said
    assert "Spiral" in said, said
    assert "both apps" in said, said
    assert "voice" in said.lower() and ("stayed" in said or "unchanged" in said), said
    assert bodies == [{"face": "spiral"}], bodies


check("the answer names the face, says both apps changed and says the voice did not",
      t_the_answer_names_the_face_both_apps_and_the_voice)


def t_without_the_patch_it_says_so():
    ns3 = namespace(here=SPEC.parent, config_dir=Path(tempfile.mkdtemp()))
    previous = install(ns3)
    try:
        sys.modules["jarvis_hud"]._appearance_set_face = None
        sys.modules["jarvis_hud"]._appearance_view = None
        out = R.set_face("spiral")
        cannot_read = R.face_words()
        # A server WITH the patch, but a stored file it cannot read just now,
        # is the same honest answer - not "no face has been chosen".
        sys.modules["jarvis_hud"]._appearance_view = lambda: {
            "face": None, "bindings": {}, "updated": 0.0, "readable": False}
        unreadable = R.face_words()
    finally:
        if previous is not None:
            sys.modules["jarvis_hud"] = previous
        else:
            sys.modules.pop("jarvis_hud", None)
    assert not out.ok, out
    assert "apply-patches.ps1" in out.said, out.said
    assert "Nothing was changed" in out.said, out.said
    assert "cannot read" in cannot_read.lower(), cannot_read
    assert "apply-patches.ps1" in cannot_read, cannot_read
    assert "No face has been chosen" not in cannot_read, cannot_read
    assert "cannot read" in unreadable.lower(), unreadable


check("a server that has not applied the patch answers in words, not a traceback",
      t_without_the_patch_it_says_so)


# ------------------------------------------------------------ the phrases ----

ASKED = (
    ("change your face to Spiral", "spiral"),
    ("use the Orbit face", "orbit"),
    ("switch the face to the red panda", "redpanda"),
    ("make your face the accretion face", "accretion"),
    ("put the spiral face on", "spiral"),
)


def t_every_asked_sentence_resolves_to_the_face():
    for phrase, face_id in ASKED:
        got = Q.match(phrase)
        assert got is not None, phrase
        assert got.name in ("control_set", "settings_choice"), (phrase, got.name)
        assert got.f.get("key") == "face", (phrase, got.f)
        assert got.f.get("value") == face_id, (phrase, got.f)
    got = Q.match("what face are you using?")
    assert got is not None and got.name == "face_ask", got


check("all six sentences the owner asked for resolve to the face, cardless",
      t_every_asked_sentence_resolves_to_the_face)


def t_a_sentence_changes_the_face_through_the_one_route():
    a_full_document()
    bodies = recorded_save()
    try:
        got = Q.match("change your face to Spiral")
        result = Q.run(got, None, time.time())
    finally:
        restore_save(bodies)
    assert result is not None, "the sentence was handed to the model"
    assert "Spiral" in result.reply, result.reply
    assert NS["_appearance_view"]()["face"] == "spiral", NS["_appearance_view"]()
    assert bodies == [{"face": "spiral"}], bodies


check("a typed sentence changes the face through the same one write, no card",
      t_a_sentence_changes_the_face_through_the_one_route)


def t_an_unknown_face_sentence_is_a_helpful_refusal():
    before = a_full_document()
    got = Q.match("change your face to zorb")
    assert got is not None and got.name == "control_bad", got
    result = Q.run(got, None, time.time())
    assert result is not None, got
    assert "zorb" in result.reply, result.reply
    assert any(name in result.reply for name, _ in spec_faces()), result.reply
    # ... and the same through the other shape, which lists the choices. It
    # does not echo the bad word - the list is the useful half.
    got = Q.match("use the zorb face")
    assert got is not None and got.name == "settings_choice_bad", got
    result = Q.run(got, None, time.time())
    assert result is not None, got
    assert "not one of the choices" in result.reply.lower(), result.reply
    assert any(name in result.reply for name, _ in spec_faces()), result.reply
    assert NS["_appearance_view"]()["updated"] == before["updated"], "a refused sentence changed the file"


check("an unknown face is a helpful refusal that changes nothing",
      t_an_unknown_face_sentence_is_a_helpful_refusal)


def t_the_questions_name_the_current_face():
    a_full_document()
    NS["_appearance_set_face"]("redpanda")
    here = R.control_current_words(R._choice("face"))
    assert here == "Red Panda", here
    result = Q.run(Q.match("what face are you using?"), None, time.time())
    assert result is not None and "Red Panda" in result.reply, result.reply
    # "change the face" with no value asks; it must not guess one.
    got = Q.match("change the face")
    assert got is not None and got.name == "control_ask", got
    asked = Q.run(got, None, time.time())
    assert asked is not None and "Red Panda" in asked.reply, asked.reply


check("the questions name the real current face", t_the_questions_name_the_current_face)


def t_the_settings_that_still_cannot_be_asked_keep_their_words():
    """Adding the face to the grammar must not soften the settings that really
    are Settings-only. "Turn on App lock" still names the screen and row."""
    got = Q.match("turn on app lock")
    assert got is not None and got.name == "settings_not_by_asking", got
    result = Q.run(got, None, time.time())
    assert result is not None, got
    assert "Settings" in result.reply and "App lock" in result.reply, result.reply
    assert "cannot change it by asking" in result.reply, result.reply


check("the settings that still cannot be asked keep their honest refusal",
      t_the_settings_that_still_cannot_be_asked_keep_their_words)


def t_the_model_tool_s_refusal_points_at_the_sentence():
    """The model-facing change_setting tool takes on/off only. When the model
    names a CHOICE, that refusal must not claim the setting cannot be asked
    for - it can, by naming a value (the face made that contradiction
    reachable, 2026-10-26). A setting that really cannot be asked keeps the
    plain lead."""
    said = R.cannot_change_setting_words("the face")
    assert said.startswith('"the face" is a choice'), said
    assert "set the face to" in said, said
    plain = R.cannot_change_setting_words("app lock")
    assert plain.startswith('I cannot change "app lock" by asking'), plain


check("the model tool's refusal for a choice names the sentence that works",
      t_the_model_tool_s_refusal_points_at_the_sentence)


def t_the_voice_is_never_written():
    """The one write this feature makes carries `face` and nothing else.

    The voice lives in jarvis_voices' own store, which this path cannot reach:
    no function here imports it, and the recorded bodies prove the only
    document written is the appearance one with one key in it.
    """
    a_full_document()
    bodies = recorded_save()
    try:
        R.set_face("monkey")
        Q.run(Q.match("put the spiral face on"), None, time.time())
    finally:
        restore_save(bodies)
    assert bodies == [{"face": "monkey"}, {"face": "spiral"}], bodies


check("no voice binding is written - the only change is the face key",
      t_the_voice_is_never_written)


if PREVIOUS is not None:
    sys.modules["jarvis_hud"] = PREVIOUS
else:
    sys.modules.pop("jarvis_hud", None)

print("" if not FAILS else f"\n{len(FAILS)} failed: {FAILS}")
sys.exit(1 if FAILS else 0)
