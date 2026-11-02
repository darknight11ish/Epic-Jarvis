"""Resetting the phone app never changes the PC's chosen voice.

    python -B backend/test_phone_reset_voice.py

THE OWNER'S REPORT (2026-11-02), in his words: *"when I reset the jarvis
Android app it changes the voice to the default. it doesn't seem to remember
what I changed it to. fix it"*

WHAT "RESET" IS, on the phone. The one app-level reset is Settings, Devices,
**"Unpair & clear the token"** (`jarvis-client`'s `Devices.UNPAIR_BUTTON`,
`DevicesPlate.kt`, which calls `JarvisRuntime.unpairAndClearToken()`): it asks
the PC to remove this device, then clears the phone's Keystore token, the
saved address, the resume point and the event stream. On the PC that is
`POST /api/devices/remove` -> `jarvis_devices.remove()`, which writes the
device registry and NOTHING else. The owner's voice is a PC-wide setting in
`voices/state.json` (`jarvis_voices`) and the reset is not supposed to touch
it - and a fresh install has to be told the stored choice again when it
pairs.

WHAT THIS SUITE PROVES, all through the REAL functions on both sides (the
phone's own `jarvis_devices` reset and re-pair path, and the real
`jarvis_voices` the PC's voice screens read and write; a temporary settings
folder stands in for `~/.openjarvis`):

  1. The reset happens -> the voice choice is unchanged, and
     `voices/state.json` is byte-for-byte the same file. The owner's rule,
     as a regression test.
  2. A fresh install / re-pair (a NEW device id, exactly what `_mint` writes
     after the pairing card is approved) still gets the stored choice: the
     `GET /api/voice/voices` answer names it, and the PC still speaks it.
  3. A reset on a phone that never chose a voice still gives the pack
     default - the phone is not left with nothing to show.
  4. The choice survives a backend restart (a fresh import of the module,
     reading the file again).
  5. A voice store that exists but cannot be read is REFUSED, not silently
     rewritten from the defaults (`_write_state`): that rewrite is what turns
     a one-key change into "the voice went back to the default", and it is
     the same rule `jarvis_manner` already follows (data-integrity audit F3).
  6. `speaker_view()["saved"]` still names the owner's own choice when the
     installed voice pack cannot speak it, so an app can say "you chose X,
     Y speaks until then" instead of presenting the default as the choice.

NOT tested here, and never counted as tested: a real phone, a real PC and a
real voice pack. The JVM suite covers the phone's own words
(`DevicesTest`, `CustomVoicesTest`); this suite is the PC side.

Runs anywhere: no voices pack has to exist (whatever pack this PC reports is
used, and every check is written against it), no model, no graphics card.
"""
import importlib
import json
import sys
import tempfile
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_voices.py", "jarvis_devices.py")

PASSED, FAILED = [], []
SKIPPED = []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: its own tally, never a pass."""
    SKIPPED.append(why)
    print(f"skip  {why}")


# ---------------------------------------------------------------------------
# The settings folder both modules share (the PC's own `~/.openjarvis`)
# ---------------------------------------------------------------------------

TMP = Path(tempfile.mkdtemp(prefix="jarvis-phone-reset-"))
fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = TMP
fw.LOG_DIR = TMP
fw.load_framework = lambda: {}
fw.audit_log = lambda *a, **k: None
fw.action_tier = lambda action: "ask"
sys.modules.setdefault("jarvis_framework", fw)

import jarvis_devices as D  # noqa: E402
import jarvis_kokoro as K  # noqa: E402
import jarvis_voices as V  # noqa: E402

AUDIT, EVENTS, DEVICE_EVENTS = [], [], []
_ORIG = {n: getattr(V, n) for n in ("_config_dir", "_cfg", "_audit", "_publish",
                                    "_second_card", "_start_reaper")}
_D_ORIG = {n: getattr(D, n) for n in ("_publish",)}

CFG = {}


def reset():
    """A new, empty settings folder; both modules pointed at it."""
    d = Path(tempfile.mkdtemp(prefix="cfg-", dir=TMP))
    fw.CONFIG_DIR = d
    CFG.clear()
    AUDIT.clear()
    EVENTS.clear()
    DEVICE_EVENTS.clear()
    V._config_dir = lambda: d
    V._cfg = lambda k, default=None: CFG.get(k, default)
    V._audit = lambda e, det: AUDIT.append((e, dict(det)))
    V._publish = lambda data: EVENTS.append(dict(data))
    V._second_card = lambda: {"capable": False, "why": "only one graphics card found",
                              "uuid": None, "name": None, "free_mb": None,
                              "big_model": None}
    V._start_reaper = lambda: None
    D._publish = lambda kind, data: DEVICE_EVENTS.append((kind, dict(data)))
    D._reset_for_tests()
    return d


def state_file(d):
    return Path(d) / "voices" / "state.json"


def view():
    """The exact answer `GET /api/voice/voices` gives both apps."""
    return V.status()


def speaker_view():
    return view()["speaker"]


def a_voice_that_is_not_the_default():
    """A real voice in THIS PC's pack, that is not its default, and not a
    blend (a blend asks for a voice-print check this suite is not about)."""
    sk = speaker_view()
    default = sk["default"]
    for row in sk["choices"]:
        if row["id"] != default and row["id"] not in K.MIX:
            return row["id"]
    return None


def choose(name):
    code, out = V.set_speaker({"speaker": name})
    assert code == 200, (code, out)
    return out


def mint_device(name="OnePlus"):
    """A paired phone, exactly as approving the pairing card writes it
    (`jarvis_devices.collect` -> `_mint`)."""
    return D._mint(name, "phone")


def reset_the_phone(device_id):
    """`JarvisRuntime.unpairAndClearToken()`'s PC half: POST
    /api/devices/remove for this device. Returns (code, body)."""
    return D.remove({"id": device_id}, you=device_id)


# ---------------------------------------------------------------------------
# 1. The reset leaves the voice alone
# ---------------------------------------------------------------------------

def t_the_reset_does_not_touch_the_voice():
    d = reset()
    chosen = a_voice_that_is_not_the_default()
    if chosen is None:
        skip("this PC's voice pack offers no second voice to choose")
        return
    choose(chosen)
    path = state_file(d)
    before = path.read_bytes()
    # Only what the RESET does is measured from here: the choice itself rang
    # its own `voices` event and wrote its own audit line, by design.
    AUDIT.clear()
    EVENTS.clear()
    dev, _token = mint_device()
    code, out = reset_the_phone(dev)
    check("the reset itself answers 200 and removed this phone",
          code == 200 and out.get("was_this_device") is True, (code, out))
    check("the reset leaves voices/state.json byte for byte the same",
          path.read_bytes() == before)
    check("the chosen voice is still the one the PC reads",
          V.speaker_view()["choice"] == chosen, V.speaker_view())
    check("the reset rings no voices event (only the device list moved)",
          [e for e in EVENTS if e.get("what") in ("speaker", "speed", "delete", "switch")] == [],
          EVENTS)
    check("the reset's audit lines are the device's only",
          {e for e, _ in AUDIT} <= {"devices.removed"}, AUDIT)


# ---------------------------------------------------------------------------
# 2. A fresh install / re-pair still gets the stored choice
# ---------------------------------------------------------------------------

def t_a_repaired_phone_still_gets_the_stored_choice():
    d = reset()
    chosen = a_voice_that_is_not_the_default()
    if chosen is None:
        skip("this PC's voice pack offers no second voice to choose")
        return
    choose(chosen)
    old, _ = mint_device()
    reset_the_phone(old)
    # What a fresh install does after its pairing card is approved: a NEW
    # device row and key (jarvis_devices._mint), never the old id again.
    new, _token = mint_device()
    check("the re-pair really is a new device", new != old, (old, new))
    check("the re-paired phone still gets the stored choice",
          V.speaker_view()["choice"] == chosen, V.speaker_view())
    check("and the PC still speaks it", V.speaker_view()["value"] == V.speaker(),
          (V.speaker_view(), V.speaker()))
    check("nothing was written to voices/state.json by the re-pair",
          json.loads(state_file(d).read_text(encoding="utf-8"))["speaker"] == chosen,
          state_file(d).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 3. A phone that never chose a voice still gets the default
# ---------------------------------------------------------------------------

def t_a_phone_that_never_chose_still_gets_the_default():
    d = reset()
    dev, _ = mint_device()
    reset_the_phone(dev)
    v = V.speaker_view()
    check("with no choice saved, the app is given the pack's default",
          v["choice"] == v["default"] and v["default"] == K.default_name(V.table_kind()),
          v)
    check("and that default is what the PC speaks", V.speaker() == K.default_sid(V.table_kind()),
          (V.speaker(), K.default_sid(V.table_kind())))
    check("nothing is invented as the owner's saved choice", v.get("saved") is None, v)
    check("no voices/state.json was created by reading it", not state_file(d).exists(),
          state_file(d))


# ---------------------------------------------------------------------------
# 4. The choice survives a restart
# ---------------------------------------------------------------------------

def t_the_choice_survives_a_restart():
    d = reset()
    chosen = a_voice_that_is_not_the_default()
    if chosen is None:
        skip("this PC's voice pack offers no second voice to choose")
        return
    choose(chosen)
    # A real restart: the module is thrown away and imported again, so every
    # value it had in memory is gone and the file is the only record.
    fresh = importlib.reload(V)
    try:
        fresh._config_dir = lambda: d
        fresh._cfg = lambda k, default=None: CFG.get(k, default)
        fresh._audit = lambda e, det: AUDIT.append((e, dict(det)))
        fresh._publish = lambda data: EVENTS.append(dict(data))
        fresh._second_card = V._second_card
        fresh._start_reaper = lambda: None
        v = fresh.status()["speaker"]
        check("after a restart the chosen voice is still the one read",
              v["choice"] == chosen and v["saved"] == chosen, v)
        check("and the PC still speaks it", fresh.speaker() == fresh.speaker_view()["value"])
    finally:
        importlib.reload(V)
        for name, fn in _ORIG.items():
            setattr(V, name, fn)
        fw.CONFIG_DIR = d


# ---------------------------------------------------------------------------
# 5. A store that cannot be read is refused, not flattened to the defaults
# ---------------------------------------------------------------------------

def t_a_damaged_voice_store_is_refused_not_flattened():
    d = reset()
    chosen = a_voice_that_is_not_the_default()
    if chosen is None:
        skip("this PC's voice pack offers no second voice to choose")
        return
    choose(chosen)
    path = state_file(d)
    good = path.read_text(encoding="utf-8")
    damaged = good[: max(1, len(good) // 2)]          # a half-written file
    path.write_text(damaged, encoding="utf-8")
    before = path.read_bytes()
    code, out = V.set_speaker({"speaker": chosen})
    check("a write to a damaged voice store is refused, in words",
          code == 500 and "state.json" in str(out.get("error", "")), (code, out))
    check("and the damaged file is left exactly as it was, to be fixed",
          path.read_bytes() == before)
    # The one-key write is refused too: this is the shape that used to turn a
    # speed change into "the voice went back to the default".
    err = V._write_state(speed="faster")
    check("a one-key write to a damaged store is refused too", bool(err), err)
    check("and still nothing was written over it", path.read_bytes() == before)
    path.write_text(good, encoding="utf-8")
    check("once the file is readable again the choice is there",
          V.speaker_view()["choice"] == chosen, V.speaker_view())


def t_a_voice_store_that_is_not_an_object_is_refused():
    d = reset()
    path = state_file(d)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[]", encoding="utf-8")
    before = path.read_bytes()
    err = V._write_state(speed="faster")
    check("a list where the voice store should be is refused", bool(err), err)
    check("and it is not overwritten with defaults", path.read_bytes() == before)


# ---------------------------------------------------------------------------
# 6. The saved choice is named even when the pack cannot speak it
# ---------------------------------------------------------------------------

def t_the_saved_choice_is_named_when_the_pack_falls_back():
    d = reset()
    kind = V.table_kind()
    # A real Kokoro voice name this installed pack CANNOT resolve - so the PC
    # has to fall back to the pack's default while it speaks. Searched in both
    # packs' own lists, so the check runs on a PC with either pack, or none.
    foreign = next((c for c in (K.V1_PICK + K.V019_PICK)
                    if K.resolve(kind, c) is None), None)
    if foreign is None:
        skip(f"this PC's pack ({kind or 'none'}) resolves every name it lists")
        return
    path = state_file(d)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"speaker": foreign}), encoding="utf-8")
    v = V.speaker_view()
    check("a saved voice the pack lacks falls back to the default that speaks",
          v["choice"] == v["default"] and v["choice"] != foreign, v)
    check("but the owner's saved choice is still reported as his",
          v.get("saved") == foreign, v)
    check("and the note says which he chose and which speaks",
          bool(v.get("saved")) and K.label_of(v["saved"]) in v["note"]
          and K.label_of(v["choice"]) in v["note"], v["note"])


# ---------------------------------------------------------------------------

def main():
    for fn in (t_the_reset_does_not_touch_the_voice,
               t_a_repaired_phone_still_gets_the_stored_choice,
               t_a_phone_that_never_chose_still_gets_the_default,
               t_the_choice_survives_a_restart,
               t_a_damaged_voice_store_is_refused_not_flattened,
               t_a_voice_store_that_is_not_an_object_is_refused,
               t_the_saved_choice_is_named_when_the_pack_falls_back):
        print(f"\n{fn.__name__}")
        try:
            fn()
        except Exception:
            import traceback
            traceback.print_exc()
            check(f"{fn.__name__} ran without raising", False)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed, {len(SKIPPED)} skipped")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
