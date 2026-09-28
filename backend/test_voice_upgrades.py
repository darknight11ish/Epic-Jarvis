"""The voice upgrades (2026-09-26): the speaking-speed setting, Pocket TTS
built but not switched on, the "hey Jarvis" candidate's checks, and the
bake-off that decides both.

    python3 test_voice_upgrades.py

Runs anywhere; no model downloads. The real wake-word files it uses are the
ones already in this repository (the phone's assets). With
JARVIS_TEST_VOICE_MODELS pointing at a voice-models folder that holds
pocket-tts\\, it also runs the real Pocket TTS once.

What it proves:

  - the speaking speed: three choices from the PC with their words; no card
    either way (the gate is never asked); saved, announced (`voices`
    event, audit line with the choice only), and used by the built-in voice,
    the custom voice and the "One moment." clip's cache key; bad bodies are
    refused; `[voice] tts_speed` still applies until the owner chooses.
  - Pocket TTS: NOT switched on (ZipVoice speaks; no "pocket" row on
    screen); every file hash-pinned and checked before loading, a changed
    file refused (fail closed); when it is chosen it speaks in the voice,
    with the voice's own recording, and replaces ZipVoice's row.
  - "hey Jarvis": the wake-word files' pins are the phone's files and the
    install line's hashes - one file, one hash, both apps; the candidate is
    refused without its manifest, from another livekit-wakeword commit, or
    when its hash changed; a model of the wrong shape is refused; spot()
    never uses the candidate.
  - the bake-off: both verdicts, rule by rule; the wake-up counter; the
    whole run with nothing installed ends in "keep what we have" and writes
    its two files; it calls nothing but this PC's own Ollama; no recording
    of the owner's voice is kept.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import BACKEND, REPO, require_shipped  # noqa: E402

for p in (HERE / "rebuilt",):
    if str(p) not in sys.path:
        sys.path.append(str(p))

require_shipped("jarvis_voices.py", "jarvis_speech.py", "jarvis_wakeword.py",
                "jarvis_bakeoff.py", "jarvis_voice_flow.py")

import numpy as np  # noqa: E402
import jarvis_voices as V  # noqa: E402
import jarvis_speech as S  # noqa: E402
import jarvis_wakeword as W  # noqa: E402
import jarvis_bakeoff as B  # noqa: E402
import jarvis_voice_flow as F  # noqa: E402

FAILED, PASSED = [], []
ASSETS = REPO / "jarvis-client" / "app" / "src" / "main" / "assets" / "wakeword"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def sha(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


# ------------------------------------------------------------------ stand-ins --

TMP = Path(tempfile.mkdtemp(prefix="jarvis-voice-upgrades-"))
CFG, AUDIT, EVENTS, CARDS = {}, [], [], []
_ORIG = {n: getattr(V, n) for n in ("_config_dir", "_cfg", "_audit", "_publish", "_gate",
                                    "PROCESSOR_ENGINE", "POCKET_FILES", "sherpa_onnx")}
_S_CFG = S._cfg
_S_PATHS = S._sherpa_tts_paths


class FakeKokoro:
    def __init__(self):
        self.speeds = []
        self.sids = []

    def generate(self, text, sid=0, speed=1.0):
        self.speeds.append(speed)
        self.sids.append(sid)
        return types.SimpleNamespace(samples=(0.05 * np.ones(24000)).astype(np.float32),
                                     sample_rate=24000)


class FakeZip:
    def __init__(self):
        self.speeds = []

    def generate(self, text, prompt_text, prompt_samples, sample_rate, speed, steps):
        self.speeds.append(speed)
        return types.SimpleNamespace(samples=(0.1 * np.ones(24000)).astype(np.float32),
                                     sample_rate=24000)


class FakePocket:
    """sherpa-onnx's Pocket TTS generate(text, GenerationConfig, callback)."""

    def __init__(self):
        self.calls = []

    def generate(self, text, gc, callback=None):
        self.calls.append((text, len(gc.reference_audio), gc.reference_sample_rate, gc.speed,
                           getattr(gc, "extra", None)))
        x = (0.1 * np.ones(24000)).astype(np.float32)
        if callback is not None:
            callback(x[:1000], 0.5)
        return types.SimpleNamespace(samples=x, sample_rate=24000)


def reset(face_voice=True):
    """A fresh config folder. `face_voice`: the "Voice follows the face"
    switch starts ON here, as most of these tests are about it working; it
    ships OFF (FACE_VOICE_DEFAULT, checked on its own with face_voice=None)."""
    V._reset_for_tests()
    d = Path(tempfile.mkdtemp(prefix="cfg-", dir=TMP))
    CFG.clear()
    AUDIT.clear()
    EVENTS.clear()
    CARDS.clear()
    V._config_dir = lambda: d
    V._cfg = lambda k, default=None: CFG.get(k, default)
    V._audit = lambda e, det: AUDIT.append((e, dict(det)))
    V._publish = lambda data: EVENTS.append(dict(data))

    def no_card(*a, **k):
        CARDS.append(a)
        raise AssertionError("the speaking speed must never raise a card")
    V._gate = no_card
    V.PROCESSOR_ENGINE = _ORIG["PROCESSOR_ENGINE"]
    V.POCKET_FILES = _ORIG["POCKET_FILES"]
    V.sherpa_onnx = _ORIG["sherpa_onnx"]
    V._ZIP.update(engine=FakeZip(), why="ready", built=True)
    S._tts_cache = FakeKokoro()
    S._cfg = lambda k, default=None: CFG.get(k, default)
    if face_voice is not None:
        V._write_state(face_voice=face_voice)
        AUDIT.clear()
        EVENTS.clear()
    return d


def tone(seconds=5.0, rate=24000):
    t = np.arange(int(seconds * rate)) / float(rate)
    x = 0.3 * np.sin(2 * np.pi * 150 * t)
    return np.concatenate([np.zeros(rate // 2), x, np.zeros(rate // 2)]).astype(np.float32)


def make_voice(d: Path, vid="grandpa"):
    """A voice on disk, as an approved card leaves it (the card is
    test_voices.py's business)."""
    folder = V.voices_dir() / vid
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "clip.wav").write_bytes(V.wav_bytes(tone(), 24000))
    (folder / "transcript.txt").write_text("The quick brown fox jumps over the lazy dog\n")
    (folder / "voice.json").write_text(json.dumps({
        "id": vid, "name": "Grandpa", "seconds": 5.0, "created": 1.0,
        "owner_check": {"ok": True, "why": "it does not sound like your voice",
                        "fingerprint": V.prints_fingerprint()}}))
    V._write_state(active=vid)
    return vid


# ------------------------------------------------------------ the speed --

def t_the_speed_choices_come_from_the_pc():
    reset()
    view = V.speed_view()
    check("three choices, in order, with their words",
          [c["id"] for c in view["choices"]] == ["slower", "normal", "faster"]
          and [c["label"] for c in view["choices"]] == ["Slower", "Normal", "Faster"], view)
    check("normal by default, and speed() is 1.0", view["choice"] == "normal"
          and V.speed() == 1.0 and not view["note"], view)
    check("the title and the detail say what it does, and that it never asks",
          view["title"] == "How fast Jarvis speaks" and "never asks" in view["detail"])
    check("GET /api/voice/voices carries it", V.status()["speed"] == V.speed_view())
    check("Slower is slower and Faster is faster",
          V.SPEED_VALUE["slower"] < 1.0 < V.SPEED_VALUE["faster"])


def t_setting_it_asks_nothing_and_says_so():
    reset()
    code, out = V.handle_post("/api/voice/voices/speed", {"speed": "faster"})
    check("POST speed: 200, at once", code == 200 and out["ok"] is True, (code, out))
    check("no card was raised", not CARDS)
    check("it is kept, and speed() follows it",
          V._read_state()["speed"] == "faster" and V.speed() == V.SPEED_VALUE["faster"])
    check("the answer says it in words and carries the new view",
          out["message"] == "Jarvis now speaks faster." and out["speed"]["choice"] == "faster")
    check("both apps are told to read again (a `voices` event, no words)",
          EVENTS == [{"what": "speed", "outcome": "set"}], EVENTS)
    check("the audit line has the choice only", AUDIT == [("voices.speed", {"speed": "faster"})],
          AUDIT)
    code, _ = V.handle_post("/api/voice/voices/speed", {"speed": "normal"})
    check("back to normal, also at once", code == 200 and V.speed() == 1.0 and not CARDS)


def t_bad_bodies_are_refused():
    reset()
    for bad in ({"speed": "fast"}, {"speed": 1.2}, {}, {"speed": "faster", "x": 1}, "faster",
                None, {"speed": None}, {"speed": ["faster"]}, {"speed": {"a": 1}}):
        code, out = V.set_speed(bad)
        check(f"refused: {bad!r}", code == 400 and out["ok"] is False and "speed" in out["error"],
              (code, out))
    check("and nothing was kept", V._read_state()["speed"] is None and V.speed() == 1.0)


def t_the_old_setting_applies_until_a_choice():
    reset()
    CFG["tts_speed"] = 1.3
    view = V.speed_view()
    check("[voice] tts_speed is used before any choice", V.speed() == 1.3)
    check("shown as set by hand, with no choice ticked",
          view["choice"] == "custom" and "tts_speed" in view["note"] and "1.3" in view["note"],
          view)
    CFG["tts_speed"] = 1.15
    check("a hand-set value equal to a choice shows as that choice",
          V.speed_view()["choice"] == "faster")
    CFG["tts_speed"] = 9
    check("an impossible hand-set value is ignored", V.speed() == 1.0)
    CFG["tts_speed"] = 1.3
    V.set_speed({"speed": "slower"})
    check("the owner's choice wins over the file", V.speed() == V.SPEED_VALUE["slower"])
    V._state_path().write_text(json.dumps({"active": "builtin", "speed": "warp"}))
    check("a damaged choice in state.json is no choice", V._read_state()["speed"] is None)
    V._state_path().write_text(json.dumps({"active": "builtin", "speed": ["faster"]}))
    check("...even one that is not a word at all (never a crash)",
          V._read_state()["speed"] is None and V.speed() == 1.3)


def t_every_voice_speaks_at_it():
    d = reset()
    V.set_speed({"speed": "slower"})
    S.say("Of course. I have added the dentist to Tuesday at ten.")
    check("the built-in voice (Kokoro) is given the owner's speed",
          S._tts_cache.speeds == [V.SPEED_VALUE["slower"]], S._tts_cache.speeds)
    check("jarvis_speech.tts_speed() is that one source", S.tts_speed() == V.SPEED_VALUE["slower"])
    make_voice(d)
    zip_ = V._ZIP["engine"]
    out = V.speak("Good morning.", check=lambda v: {"ok": True})
    check("the custom voice (ZipVoice) is given it too",
          out is not None and out.ok and zip_.speeds[-1] == V.SPEED_VALUE["slower"], zip_.speeds)


def t_the_one_moment_clip_follows_it():
    reset()
    k1 = F.moment_key()[0]
    V.set_speed({"speed": "faster"})
    k2 = F.moment_key()[0]
    check("a new speed makes a new \"One moment.\" clip (its key changes)", k1 != k2, (k1, k2))


# ------------------------------------------------------- which built-in voice --
# Ease-of-use audit row 13: which of Kokoro's own voices speaks - the same
# shape as speed above (no card either way, kept in state.json, `[voice]
# tts_speaker_id` applies until a choice is made).

def t_the_speaker_choices_come_from_the_pc():
    reset()
    view = V.speaker_view()
    check("eleven choices, in order, ids '0'..'10'",
          [c["id"] for c in view["choices"]] == [str(i) for i in range(11)], view)
    check("voice 0 by default, and speaker() is 0",
          view["choice"] == "0" and V.speaker() == 0 and not view["note"], view)
    check("only the two the repo's own file comment confirms are named the same way",
          V.SPEAKER_LABEL["0"] == "American (female)"
          and V.SPEAKER_LABEL["9"] == "British (male) - George")
    check("the title and the detail say what it is",
          view["title"] == "Jarvis's built-in voice" and "Kokoro" in view["detail"])
    check("GET /api/voice/voices carries it", V.status()["speaker"] == V.speaker_view())
    # The detail points at the "Voices" list, which both apps draw BELOW this
    # choice - it said "above" (play tester, 2026-09-27). Read from the two
    # screens themselves, so a reordering there shows up here.
    root = HERE.parent
    html = (root / "jarvis-desktop" / "src" / "settings.html").read_text(encoding="utf-8")
    kt = (root / "jarvis-client" / "app" / "src" / "main" / "java" / "com" / "jarvis"
          / "client" / "ui" / "screens" / "VoicesScreen.kt").read_text(encoding="utf-8")
    check("the detail says the recorded voices are under \"Voices\" below, and on both "
          "screens they are",
          view["detail"].endswith('stays under "Voices" below.')
          and html.index('id="cv-speaker"') < html.index('<h3 class="subhead">Voices</h3>')
          and kt.index("SpeakerPlate(sk") < kt.index('Text("Voices"'), view["detail"])


def t_setting_the_speaker_asks_nothing_and_says_so():
    reset()
    code, out = V.handle_post("/api/voice/voices/speaker", {"speaker": "9"})
    check("POST speaker: 200, at once", code == 200 and out["ok"] is True, (code, out))
    check("no card was raised", not CARDS)
    check("it is kept, and speaker() follows it",
          V._read_state()["speaker"] == "9" and V.speaker() == 9)
    check("the answer names the voice and carries the new view",
          out["message"] == "Jarvis's built-in voice is now British (male) - George."
          and out["speaker"]["choice"] == "9")
    check("both apps are told to read again (a `voices` event, no words)",
          EVENTS == [{"what": "speaker", "outcome": "set"}], EVENTS)
    check("the audit line has the choice only",
          AUDIT == [("voices.speaker", {"speaker": "9"})], AUDIT)


def t_bad_speaker_bodies_are_refused():
    reset()
    for bad in ({"speaker": "11"}, {"speaker": 9}, {}, {"speaker": "9", "x": 1}, "9",
                None, {"speaker": None}, {"speaker": ["9"]}, {"speaker": "-1"}):
        code, out = V.set_speaker(bad)
        check(f"refused: {bad!r}", code == 400 and out["ok"] is False, (code, out))
    check("and nothing was kept", V._read_state()["speaker"] is None and V.speaker() == 0)


def t_the_old_speaker_setting_applies_until_a_choice():
    reset()
    CFG["tts_speaker_id"] = 9
    check("[voice] tts_speaker_id is used before any choice", V.speaker() == 9)
    view = V.speaker_view()
    check("shown as that named voice, with no choice ticked yet",
          view["choice"] == "9" and not view["note"], view)
    CFG["tts_speaker_id"] = 40
    check("a hand-set value with no name of its own: shown as custom, said plainly",
          V.speaker_view()["choice"] == "custom" and "40" in V.speaker_view()["note"]
          and "tts_speaker_id" in V.speaker_view()["note"])
    CFG["tts_speaker_id"] = -1
    check("an impossible hand-set value is ignored", V.speaker() == 0)
    CFG["tts_speaker_id"] = 9
    V.set_speaker({"speaker": "3"})
    check("the owner's choice wins over the file", V.speaker() == 3)
    V._state_path().write_text(json.dumps({"active": "builtin", "speaker": "warp"}))
    check("a damaged choice in state.json is no choice", V._read_state()["speaker"] is None)


def t_the_built_in_voice_uses_the_chosen_speaker():
    reset()
    V.set_speaker({"speaker": "6"})
    S.say("Of course. I have added the dentist to Tuesday at ten.")
    check("the built-in voice (Kokoro) is given the owner's chosen speaker",
          S._tts_cache.sids == [6], S._tts_cache.sids)
    check("jarvis_speech.tts_speaker() is that one source", S.tts_speaker() == 6)


def t_the_one_moment_clip_follows_the_speaker_too():
    reset()
    k1 = F.moment_key()[0]
    V.set_speaker({"speaker": "7"})
    k2 = F.moment_key()[0]
    check("a new built-in voice makes a new \"One moment.\" clip (its key changes)",
          k1 != k2, (k1, k2))


# ------------------------------------------------------ voice follows the face --
# The owner's choice, 2026-09-27: with an animal face showing, the built-in
# voice becomes that animal's (a Kokoro voice, a pace, a small pitch rise).
# A switch, on by default, no card either way; a recorded voice still wins.

def _show_face(d: Path, face):
    (d / "appearance.json").write_text(json.dumps({"face": face, "bindings": {}}),
                                       encoding="utf-8")


def t_face_voice_needs_an_animal_face():
    d = reset(face_voice=None)
    check("off by default (the owner's 2026-09-28 decision)",
          V.face_voice_on() is False and V.FACE_VOICE_DEFAULT is False)
    check("the sea otter does not start on Kokoro's \"Sky\" voice",
          V.FACE_VOICES["seaotter"]["speaker"] != "4")
    V._write_state(face_voice=True)  # the rest of this test is about it switched on
    check("no appearance.json: no face, so the owner's built-in voice as before",
          V.face_voice() is None and V.builtin_voice() == (0, 1.0, 0.0, ""))
    view = V.face_voice_view()
    check("and the line says there is no face to follow",
          view["enabled"] and not view["speaking"] and "No face" in view["line"], view)
    _show_face(d, "nucleus")
    check("a face that is not an animal: still the owner's own voice",
          V.face_voice() is None and V.builtin_voice()[2] == 0.0)
    check("... and the line names the four animals",
          "Monkey" in V.face_voice_view()["line"])
    check("... the panda among them",
          "Red Panda" in V.face_voice_view()["line"])
    _show_face(d, ["redpanda"])
    check("a damaged face in appearance.json is no face", V.appearance_face() == "")
    check("GET /api/voice/voices carries it", V.status()["face_voice"] == V.face_voice_view())


def t_each_animal_speaks_in_its_own_voice():
    d = reset()
    for face, sid, pace, semis in (("redpanda", 1, 1.0, 2.0), ("pygmyowl", 2, 0.85, 1.0),
                                   ("seaotter", 3, 1.15, 3.0), ("monkey", 6, 1.0, 1.0)):
        _show_face(d, face)
        check(f"{face}: its own voice, pace and pitch",
              V.builtin_voice() == (sid, pace, semis, face), V.builtin_voice())
        check(f"{face}: jarvis_speech reads the same, from the one source",
              (S.tts_speaker(), S.tts_speed(), S.tts_pitch()) == (sid, pace, semis))
    _show_face(d, "redpanda")
    S._tts_cache = FakeKokoro()
    S.say("Of course. I have added the dentist to Tuesday at ten.")
    f = 2 ** (2 / 12)
    check("Kokoro speaks the panda's voice, slower by the pitch factor (so the pace "
          "comes out right once the pitch is raised)",
          S._tts_cache.sids == [1] and abs(S._tts_cache.speeds[0] - 1.0 / f) < 1e-9,
          (S._tts_cache.sids, S._tts_cache.speeds))
    V.set_speed({"speed": "faster"})
    _show_face(d, "pygmyowl")
    check("the owner's speaking speed still applies on top of the animal's pace",
          abs(V.builtin_voice()[1] - 0.85 * 1.15) < 1e-9, V.builtin_voice())
    V.set_speaker({"speaker": "9"})
    check("the owner's built-in choice does not override the face's voice",
          V.builtin_voice()[0] == 2)
    check("... and its row says why picking a voice there changes nothing now",
          "Pygmy Owl" in V.speaker_view()["note"], V.speaker_view()["note"])
    _show_face(d, "orbit")
    check("with any other face the owner's choice is back",
          V.builtin_voice()[0] == 9 and "Owl" not in V.speaker_view()["note"])


def t_the_pitch_rise():
    x = np.sin(2 * np.pi * 200 * np.arange(24000) / 24000).astype(np.float32)
    check("0 semitones: the very same samples", S.pitch_up(x, 0) is x)
    y = S.pitch_up(x, 12)
    check("12 semitones: half as long", len(y) == 12000, len(y))

    def crossings(a):
        return int(np.sum((a[:-1] < 0) & (a[1:] >= 0)))
    check("... and twice the pitch (200 Hz becomes 400 Hz)",
          abs(crossings(y) / (len(y) / 24000) - 400) < 3, crossings(y))
    k = FakeKokoro()
    got = S.kokoro_speak(k, "hi", 1, 1.0, 2.0)
    f = 2 ** (2 / 12)
    check("kokoro_speak: asks for slower speech, then raises it back to pace",
          abs(k.speeds[0] - 1 / f) < 1e-9 and len(got[0]) == int(24000 / f) and got[1] == 24000)
    check("kokoro_speak with no rise is Kokoro unchanged",
          len(S.kokoro_speak(FakeKokoro(), "hi", 1, 1.0, 0.0)[0]) == 24000)


def t_a_recorded_voice_still_wins():
    d = reset()
    _show_face(d, "seaotter")
    make_voice(voices_dir := V.voices_dir(), "grandpa")
    V._write_state(active="grandpa")
    view = V.face_voice_view()
    check("a chosen recorded voice wins over the face's voice, and the line says so",
          not view["speaking"] and "recorded" in view["line"], view)
    check("(the recorded voice is the one speak() uses; it never reads the face)",
          V._read_state()["active"] == "grandpa" and voices_dir.is_dir())
    V._write_state(active="ghost")
    view = V.face_voice_view()
    check("a chosen recorded voice that cannot be used falls back to the animal - "
          "and the line says so, rather than claiming the recorded voice speaks",
          view["speaking"] and "cannot be used right now" in view["line"]
          and S.tts_voice() == (3, 1.15, 3.0), (view, S.tts_voice()))


def t_the_voice_is_read_once_per_sentence():
    d = reset()
    _show_face(d, "pygmyowl")
    calls = []
    real = V.builtin_voice
    V.builtin_voice = lambda: calls.append(1) or real()
    try:
        S._tts_cache = FakeKokoro()
        S.say("Of course. I have added the dentist to Tuesday at ten.")
    finally:
        V.builtin_voice = real
    check("one sentence reads the built-in voice once, so a face change halfway "
          "cannot mix two animals", len(calls) == 1, calls)
    check("... and speaks the owl", S._tts_cache.sids == [2])
    _show_face(d, None)
    check("a saved face with no voice of its own is said plainly, not \"no face saved\"",
          "no voice of its own" in V.face_voice_view()["line"], V.face_voice_view())


def t_the_face_switch_asks_nothing_and_says_so():
    d = reset()
    _show_face(d, "redpanda")
    code, out = V.handle_post("/api/voice/voices/face", {"enabled": False})
    check("POST face off: 200, at once", code == 200 and out["ok"] is True, (code, out))
    check("no card was raised", not CARDS)
    check("it is kept, and the panda's voice stops",
          V._read_state()["face_voice"] is False and V.face_voice() is None
          and V.builtin_voice() == (0, 1.0, 0.0, ""))
    check("the answer says so and carries the new view",
          "stays the same" in out["message"] and out["face_voice"]["enabled"] is False
          and out["face_voice"]["line"].startswith("Off"))
    check("both apps are told to read again (a `voices` event, no words)",
          EVENTS == [{"what": "face_voice", "outcome": "off"}], EVENTS)
    check("the audit line has the choice only",
          AUDIT == [("voices.face_voice", {"enabled": False})], AUDIT)
    code, out = V.set_face_voice({"enabled": True})
    check("back on: at once too, no card",
          code == 200 and not CARDS and V.face_voice()["face"] == "redpanda")
    for bad in ({"enabled": "yes"}, {"enabled": 1}, {}, {"enabled": True, "x": 1}, True,
                None, {"enabled": None}):
        code, out = V.set_face_voice(bad)
        check(f"refused: {bad!r}", code == 400 and out["ok"] is False, (code, out))
    V._state_path().write_text(json.dumps({"active": "builtin", "face_voice": "no"}))
    check("a damaged switch in state.json is no choice (the default, off)",
          V._read_state()["face_voice"] is None and not V.face_voice_on())


def t_the_one_time_animal_voice_question():
    """The owner, 2026-09-28: the first time an animal face is picked, one
    line asks "The <Animal> has its own voice. Use it?" (Use it / Keep my
    voice), remembered per face; "Use it" turns the switch on; a face never
    changes the voice by itself; no card either way."""
    d = reset(face_voice=None)
    check("no face saved: no question", V.face_voice_view()["offer"] is None)
    _show_face(d, "nucleus")
    check("a face that is not an animal: no question", V.face_voice_view()["offer"] is None)
    _show_face(d, "redpanda")
    offer = V.face_voice_view()["offer"]
    check("an animal face, the switch off, never asked: the question, word for word",
          offer == {"face": "redpanda", "question": "The Red Panda has its own voice. Use it?",
                    "use": "Use it", "keep": "Keep my voice"}, offer)
    check("... and picking the face alone changed nothing (the owner's voice)",
          V.face_voice() is None and V.builtin_voice() == (0, 1.0, 0.0, ""))
    code, out = V.handle_post("/api/voice/voices/face_offer",
                              {"face": "redpanda", "answer": "keep"})
    check("Keep my voice: 200, at once, no card", code == 200 and out["ok"] is True
          and not CARDS, (code, out))
    check("... the switch stays off and the question is gone for the panda",
          V.face_voice_on() is False and out["face_voice"]["offer"] is None
          and V._read_state()["face_offered"] == ["redpanda"], out["face_voice"])
    check("... the voices event says so, with no words",
          EVENTS[-1] == {"what": "face_offer", "outcome": "keep"}, EVENTS)
    check("... and the audit line has the face and the answer only",
          AUDIT[-1] == ("voices.face_offer", {"face": "redpanda", "answer": "keep"}), AUDIT)
    _show_face(d, "pygmyowl")
    offer = V.face_voice_view()["offer"]
    check("another animal not asked yet: its own question",
          offer and offer["face"] == "pygmyowl"
          and offer["question"] == "The Pygmy Owl has its own voice. Use it?", offer)
    code, out = V.handle_post("/api/voice/voices/face_offer",
                              {"face": "pygmyowl", "answer": "use"})
    check("Use it: 200, no card, and the switch is on - the owl speaks",
          code == 200 and not CARDS and V.face_voice_on() is True
          and V.face_voice()["face"] == "pygmyowl", (code, out))
    check("... the answer carries the view, with no question left",
          out["face_voice"]["enabled"] is True and out["face_voice"]["offer"] is None
          and "Pygmy Owl" in out["message"], out)
    check("... remembered per face", V._read_state()["face_offered"] == ["redpanda", "pygmyowl"])
    V._write_state(face_voice=False)
    _show_face(d, "redpanda")
    check("a face already asked is never asked again, even with the switch off later",
          V.face_voice_view()["offer"] is None)
    _show_face(d, "seaotter")
    V._write_state(face_voice=True)
    check("with the switch already on, nothing is asked (the animal already speaks)",
          V.face_voice_view()["offer"] is None)
    for bad in ({"face": "redpanda"}, {"face": "nucleus", "answer": "use"},
                {"face": "redpanda", "answer": "yes"}, {"face": "redpanda", "answer": True},
                {"face": "redpanda", "answer": "use", "x": 1}, None, "use"):
        code, out = V.handle_post("/api/voice/voices/face_offer", bad)
        check(f"refused, in words: {bad!r}", code == 400 and out["ok"] is False
              and isinstance(out.get("error"), str) and out["error"], (code, out))
    V._state_path().write_text(json.dumps({"active": "builtin", "face_offered": "all"}))
    check("a damaged face_offered in state.json is no face asked (the safe reading)",
          V._read_state()["face_offered"] == [])
    V._state_path().write_text(json.dumps({"active": "builtin",
                                           "face_offered": ["redpanda", "ghost", 3]}))
    check("... and only real animal faces are kept from it",
          V._read_state()["face_offered"] == ["redpanda"])


def t_the_one_moment_clip_and_the_echo_check_follow_the_face():
    d = reset()
    k_none = F.moment_key()[0]
    _show_face(d, "nucleus")
    check("a face with no voice of its own leaves the clip's key exactly as before",
          F.moment_key()[0] == k_none)
    _show_face(d, "redpanda")
    k_panda = F.moment_key()[0]
    _show_face(d, "seaotter")
    k_otter = F.moment_key()[0]
    check("each animal makes its own \"One moment.\" clip (the key changes)",
          len({k_none, k_panda, k_otter}) == 3)
    try:
        S._sherpa_tts_paths = (lambda real: (lambda: dict(real(), model=__file__)))(
            _S_PATHS)
        keys = [k for k, _label, _load in F._reference_sources() if k[0] == "builtin"]
    finally:
        S._sherpa_tts_paths = _S_PATHS
    check("talking over the otter is checked against the otter's pitched voice",
          keys and keys[0][1] == "3" and keys[0][-1] == "3.0", keys)


# ------------------------------------------------------ each animal's voice --
# The owner's choice, 2026-09-28: for each animal, any built-in voice, a
# pitch from 3 steps deeper to 4 higher (half steps) and a pace. No card
# either way; "Reset to its own voice"; "Try it" plays a fixed line.

def t_each_animal_voice_can_be_changed():
    d = reset()
    _show_face(d, "redpanda")
    body = {"face": "redpanda", "speaker": "3", "semitones": -1.5, "pace": "faster"}
    code, out = V.handle_post("/api/voice/voices/face_animal", body)
    check("POST face_animal: 200, at once, no card", code == 200 and out["ok"] is True
          and not CARDS, (code, out))
    check("the answer says it plainly",
          out["message"] == "The Red Panda's voice is now Sarah, 1.5 steps deeper, "
                            "a little faster.", out["message"])
    check("the panda now speaks in it (the owner's speed still on top)",
          V.builtin_voice() == (3, 1.15, -1.5, "redpanda"), V.builtin_voice())
    check("... and jarvis_speech reads the same, deeper pitch included",
          S.tts_voice() == (3, 1.15, -1.5) and S.tts_pitch() == -1.5, S.tts_voice())
    check("kept in state.json, only for the animal that changed",
          V._read_state()["face_animals"] == {"redpanda": {"speaker": "3", "semitones": -1.5,
                                                            "pace": "faster"}})
    check("both apps are told to read again; the audit line has the choice only",
          EVENTS == [{"what": "face_animal", "outcome": "set"}]
          and AUDIT == [("voices.face_animal", {"face": "redpanda", "speaker": "3",
                                                "semitones": -1.5, "pace": "faster"})],
          (EVENTS, AUDIT))
    rows = {r["face"]: r for r in out["face_voice"]["animals"]}
    check("the view lists all four animals, the panda marked changed",
          list(rows) == ["redpanda", "pygmyowl", "seaotter", "monkey"] and rows["redpanda"]["changed"]
          and not rows["pygmyowl"]["changed"] and rows["redpanda"]["voice"] == "Sarah"
          and rows["redpanda"]["own"] == {"speaker": "1", "semitones": 2.0, "pace": "normal"},
          rows)
    check("each row has a line in words",
          rows["redpanda"]["line"] == "Sarah, 1.5 steps deeper, a little faster."
          and rows["pygmyowl"]["line"] == "Nicole, 1 step higher, a little slower."
          and rows["monkey"]["line"] == "Michael, 1 step higher, at normal pace.",
          [r["line"] for r in rows.values()])
    ch = out["face_voice"]["animal_choices"]
    check("the choices come from the PC: the 11 voices, three paces, the pitch range",
          len(ch["voices"]) == 11 and [p["id"] for p in ch["paces"]] == ["slower", "normal",
                                                                         "faster"]
          and ch["pitch"] == {"min": -3.0, "max": 4.0, "step": 0.5}, ch)
    check("the switch's line says deeper, not higher",
          V.face_voice_view()["line"] == "Speaking as the Red Panda: Sarah, a little deeper.")
    S._tts_cache = FakeKokoro()
    S.say("Of course. I have added the dentist to Tuesday at ten.")
    f = 2 ** (-1.5 / 12)
    check("Kokoro is asked for FASTER speech by the pitch factor, so once the sound is "
          "played slower (deeper) the pace comes out as chosen",
          S._tts_cache.sids == [3] and abs(S._tts_cache.speeds[0] - 1.15 / f) < 1e-9,
          (S._tts_cache.sids, S._tts_cache.speeds))
    V.set_speed({"speed": "slower"})
    check("the owner's speaking speed multiplies the animal's pace",
          abs(V.builtin_voice()[1] - 1.15 * 0.85) < 1e-9)
    _show_face(d, "pygmyowl")
    check("the other animals keep their own voices",
          V.builtin_voice() == (2, 0.85 * 0.85, 1.0, "pygmyowl"), V.builtin_voice())
    V.set_face_voice({"enabled": False})
    _show_face(d, "redpanda")
    check("switch off: the owner's single built-in voice for every face, choices kept",
          V.builtin_voice() == (0, 0.85, 0.0, "") and "redpanda" in V._read_state()["face_animals"])
    code, out = V.set_face_animal({"face": "seaotter", "speaker": "10", "semitones": 0,
                                   "pace": "normal"})
    check("changing an animal while the switch is off says it is heard once that is on",
          code == 200 and out["message"] == "The Sea Otter's voice is now Lewis, normal pitch, "
          "at normal pace. \"Voice follows the face\" is off, so you will hear it once that is on.",
          out["message"])


def t_reset_and_its_own_voice():
    d = reset()
    _show_face(d, "seaotter")
    V.set_face_animal({"face": "seaotter", "speaker": "9", "semitones": 4, "pace": "slower"})
    EVENTS.clear(); AUDIT.clear()
    code, out = V.handle_post("/api/voice/voices/face_animal", {"face": "seaotter", "reset": True})
    check("reset: 200, at once, no card, its own voice back",
          code == 200 and not CARDS and V.builtin_voice() == (3, 1.15, 3.0, "seaotter")
          and out["message"] == "The Sea Otter speaks in its own voice again.", (code, out))
    check("... nothing kept for it, and it is announced and audited without words",
          V._read_state()["face_animals"] == {}
          and EVENTS == [{"what": "face_animal", "outcome": "reset"}]
          and AUDIT == [("voices.face_animal", {"face": "seaotter", "reset": True})],
          (EVENTS, AUDIT))
    V.set_face_animal({"face": "seaotter", "speaker": "3", "semitones": 3.0, "pace": "faster"})
    check("choosing exactly its own voice keeps no choice (so it is not marked changed)",
          V._read_state()["face_animals"] == {}
          and not V.face_voice_view()["animals"][2]["changed"])


def t_bad_animal_bodies_are_refused():
    reset()
    good = {"face": "redpanda", "speaker": "3", "semitones": 1.5, "pace": "normal"}
    bads = [None, True, [], {}, dict(good, face="nucleus"), dict(good, face=1),
            {k: v for k, v in good.items() if k != "pace"}, dict(good, extra=1),
            dict(good, speaker="99"), dict(good, speaker=3), dict(good, semitones=4.5),
            dict(good, semitones=-3.5), dict(good, semitones=1.25), dict(good, semitones=True),
            dict(good, semitones="1"), dict(good, semitones=float("nan")),
            dict(good, semitones=float("inf")), dict(good, pace="fast"), dict(good, pace=1.0),
            {"face": "redpanda", "reset": False}, {"face": "redpanda", "reset": 1},
            {"face": "redpanda", "reset": True, "speaker": "3"}]
    for bad in bads:
        code, out = V.set_face_animal(bad)
        check(f"refused: {bad!r}", code == 400 and out["ok"] is False
              and isinstance(out["error"], str) and out["error"][:1].islower(), (code, out))
    check("nothing was kept, nothing announced", V._read_state()["face_animals"] == {}
          and not EVENTS and not AUDIT)
    check("the pitch refusal is in words",
          V.set_face_animal(dict(good, semitones=9))[1]["error"]
          == "the pitch must be from 3 steps deeper to 4 steps higher, in half steps")
    check("every half step in range is taken",
          all(V.set_face_animal(dict(good, semitones=x / 2))[0] == 200 for x in range(-6, 9)))
    V._state_path().write_text(json.dumps({"active": "builtin", "face_animals": {
        "redpanda": {"speaker": "99", "semitones": 1.0, "pace": "normal"},
        "pygmyowl": {"speaker": "5", "semitones": 9, "pace": "normal"},
        "seaotter": {"speaker": "5", "semitones": -2, "pace": "faster"},
        "orbit": {"speaker": "5", "semitones": 0, "pace": "normal"}}}))
    check("a damaged entry in state.json is no choice; a good one is kept",
          V._read_state()["face_animals"] == {"seaotter": {"speaker": "5", "semitones": -2.0,
                                                           "pace": "faster"}},
          V._read_state()["face_animals"])


def t_the_pitch_goes_down_too():
    x = np.sin(2 * np.pi * 200 * np.arange(24000) / 24000).astype(np.float32)
    y = S.pitch_up(x, -12)
    check("-12 semitones: twice as long", len(y) == 48000, len(y))

    def crossings(a):
        return int(np.sum((a[:-1] < 0) & (a[1:] >= 0)))
    check("... and half the pitch (200 Hz becomes 100 Hz)",
          abs(crossings(y) / (len(y) / 24000) - 100) < 3, crossings(y))
    k = FakeKokoro()
    got = S.kokoro_speak(k, "hi", 5, 1.0, -3.0)
    f = 2 ** (-3 / 12)
    check("kokoro_speak with a deeper pitch asks for FASTER speech, then lowers it back to pace",
          abs(k.speeds[0] - 1 / f) < 1e-9 and len(got[0]) == int(24000 / f), (k.speeds, len(got[0])))
    check("jarvis_speech holds a pitch to -3..+4 and treats nonsense as none",
          (S._pitch_range(-9), S._pitch_range(9), S._pitch_range("x"),
           S._pitch_range(float("nan"))) == (-3.0, 4.0, 0.0, 0.0))


def t_the_one_moment_clip_and_the_echo_check_follow_the_animal_choice():
    d = reset()
    _show_face(d, "redpanda")
    k_own = F.moment_key()[0]
    V.set_face_animal({"face": "redpanda", "speaker": "1", "semitones": -2, "pace": "normal"})
    k_deep = F.moment_key()[0]
    check("a new pitch for the showing animal makes a new \"One moment.\" clip",
          k_own != k_deep)
    try:
        S._sherpa_tts_paths = (lambda real: (lambda: dict(real(), model=__file__)))(_S_PATHS)
        keys = [k for k, _label, _load in F._reference_sources() if k[0] == "builtin"]
    finally:
        S._sherpa_tts_paths = _S_PATHS
    check("talking over the deeper panda is checked against the deeper voice",
          keys and keys[0][1] == "1" and keys[0][-1] == "-2.0", keys)


def t_try_it_plays_the_animal_as_it_is_now():
    d = reset()
    _show_face(d, "nucleus")
    V.set_face_animal({"face": "pygmyowl", "speaker": "6", "semitones": -1, "pace": "faster"})
    EVENTS.clear(); AUDIT.clear()
    before = V._state_path().read_bytes()
    S._tts_cache = FakeKokoro()
    code, wav = V.handle_post("/api/voice/voices/face_animal/try", {"face": "pygmyowl"})
    check("Try it: a WAV in the owl's voice as chosen, though another face is showing",
          code == 200 and isinstance(wav, bytes) and wav[:4] == b"RIFF"
          and S._tts_cache.sids == [6]
          and abs(S._tts_cache.speeds[0] - 1.15 / 2 ** (-1 / 12)) < 1e-9,
          (code, S._tts_cache.sids, S._tts_cache.speeds))
    x, sr = S._read_wav(wav)
    check("... played deeper: longer than Kokoro's own sound",
          sr == 24000 and len(x) == int(24000 / 2 ** (-1 / 12)), len(x))
    check("... changing nothing, announcing nothing, logging nothing",
          V._state_path().read_bytes() == before and not EVENTS and not AUDIT and not CARDS)
    V.set_face_voice({"enabled": False})
    S._tts_cache = FakeKokoro()
    check("it plays with the switch off too (it is a preview)",
          V.try_face_animal({"face": "seaotter"})[0] == 200 and S._tts_cache.sids == [3])
    for bad in ({}, {"face": "orbit"}, {"face": "redpanda", "text": "say this"}, None):
        code, out = V.try_face_animal(bad)
        check(f"refused: {bad!r} (an app never sends words to be spoken)",
              code == 400 and out["ok"] is False, (code, out))
    S._tts_cache = None
    code, out = V.try_face_animal({"face": "redpanda"})
    check("no built-in voice on this PC: 503 in words",
          code == 503 and out["error"] == "this PC has no built-in voice to play it with",
          (code, out))
    S._tts_cache = FakeKokoro()
    # One at a time: a second "Try it" while one is being made is refused
    # at once, in words, and the next one after it plays again.
    V._TRY_LOCK.acquire()
    try:
        code, out = V.try_face_animal({"face": "redpanda"})
    finally:
        V._TRY_LOCK.release()
    check("a Try it while another is being made: 429 in words, nothing made",
          code == 429 and out["ok"] is False and "Try it again in a moment" in out["error"],
          (code, out))
    check("a bad body is still a 400 while one is being made",
          V._TRY_LOCK.acquire(blocking=False)
          and (V.try_face_animal({"face": "orbit"})[0] == 400)
          and (V._TRY_LOCK.release() is None))
    check("the lock is let go after each Try it (and after a failure)",
          V.try_face_animal({"face": "redpanda"})[0] == 200
          and not V._TRY_LOCK.locked())
    S._tts_cache = None
    V.try_face_animal({"face": "redpanda"})
    check("... after a 503 too", not V._TRY_LOCK.locked())
    S._tts_cache = FakeKokoro()


# ---------------------------------------------------------- Pocket TTS --

def t_pocket_is_built_but_not_switched_on():
    d = reset()
    check("ZipVoice is the processor engine (the bake-off has not said replace)",
          V.PROCESSOR_ENGINE == "zipvoice")
    make_voice(d)
    out = V.speak("Good morning.", check=lambda v: {"ok": True})
    check("a custom voice is made by ZipVoice", out.engine == "zipvoice", out)
    st = V.status()
    check("no Pocket TTS row on screen - one processor engine only",
          "pocket" not in st["engines"] and "zipvoice" in st["engines"], list(st["engines"]))
    check("the switch card names ZipVoice",
          "(ZipVoice)" in V.describe_switch(V.load_voice("grandpa"), "the built-in voice", {}, {}))
    src = (BACKEND / "jarvis_voices.py").read_text(encoding="utf-8")
    check("there is no setting that picks the engine",
          '_cfg("processor_engine"' not in src and "custom_voice_engine" not in src)


def t_pocket_pins():
    check("seven files, each with a 64-character SHA-256",
          len(V.POCKET_FILES) == 7 and all(re.fullmatch(r"[0-9a-f]{64}", h)
                                           for _n, h in V.POCKET_FILES.values()))
    r = V.POCKET_RELEASE
    check("the release is recorded: publisher, version, archive, its hash and the licence",
          re.fullmatch(r"[0-9a-f]{64}", r["archive_sha256"]) and r["version"] in r["archive"]
          and "CC BY 4.0" in r["licence"] and "consent" in r["licence"] and "Kyutai" in r["publisher"])
    readme = (HERE / "README.md").read_text(encoding="utf-8")
    check("the install line checks the same archive hash",
          r["archive_sha256"].upper() in readme and r["url"] in readme)


def _fake_pocket_folder(d: Path, wrong: str = "") -> dict:
    folder = d / "voice-models" / "pocket-tts"
    folder.mkdir(parents=True, exist_ok=True)
    pins = {}
    for role, (name, _h) in _ORIG["POCKET_FILES"].items():
        data = f"stand-in {name}".encode()
        (folder / name).write_bytes(data)
        pins[role] = (name, hashlib.sha256(data).hexdigest())
    if wrong:
        (folder / pins[wrong][0]).write_bytes(b"something else")
    return pins


def t_pocket_fails_closed():
    d = reset()
    ok, why = V.pocket_state()
    check("missing files: not available, and it says where the install line is",
          not ok and "not on this PC" in why and "README" in why, why)
    V.POCKET_FILES = _fake_pocket_folder(d)
    ok, why = V.pocket_state()
    check("every pin matches: ready", ok and why == "ready", why)
    V.POCKET_FILES = _fake_pocket_folder(d, wrong="decoder")
    V._HASHES.clear()
    ok, why = V.pocket_state()
    check("one changed file: refused, named, never loaded",
          not ok and "decoder.int8.onnx" in why and "not the file" in why, why)
    V._POCKET.update(engine=None, why="", built=False)
    eng, why2 = V._pocket()
    check("_pocket() builds nothing from a changed file", eng is None and "not the file" in why2)
    V.sherpa_onnx = types.SimpleNamespace()
    ok, why = V.pocket_state()
    check("a sherpa-onnx without Pocket TTS says to upgrade", not ok and "upgrade" in why, why)


def t_pocket_speaks_when_chosen():
    d = reset()
    make_voice(d)
    V.PROCESSOR_ENGINE = "pocket"
    fake = FakePocket()
    V._POCKET.update(engine=fake, why="ready", built=True)
    V.sherpa_onnx = types.SimpleNamespace(GenerationConfig=lambda: types.SimpleNamespace())
    V.set_speed({"speed": "faster"})
    out = V.speak("Good morning. It is a bright day.", check=lambda v: {"ok": True})
    check("with PROCESSOR_ENGINE = \"pocket\", the custom voice is made by it",
          out.ok and out.engine == "pocket", out)
    call = fake.calls[-1]
    check("it copies the voice's own 24 kHz recording (no transcript needed)",
          call[2] == 24000 and 5.0 * 24000 <= call[1] <= 6.2 * 24000, call[:3])
    check("the speed is passed on (the bake-off measures that it is not followed)",
          call[3] == V.SPEED_VALUE["faster"])
    st = V.status()
    check("its row REPLACES ZipVoice's - never three engines on screen",
          "pocket" in st["engines"] and "zipvoice" not in st["engines"], list(st["engines"]))
    check("the speed note says Pocket voices keep normal speed",
          "Pocket TTS" in st["speed"]["note"])
    check("the switch card names it",
          "(Pocket TTS)" in V.describe_switch(V.load_voice("grandpa"), "x", {}, {}))
    marks = []
    V.pocket_generate("Hello there.", V.load_voice("grandpa"), 1.0,
                      first_audio=lambda: marks.append(1), seed=7)
    check("first_audio fires once; the seed goes in as sherpa-onnx's extra",
          marks == [1] and fake.calls[-1][4] == {"seed": "7"}, (marks, fake.calls[-1]))


def t_real_pocket():
    root = os.environ.get("JARVIS_TEST_VOICE_MODELS")
    folder = Path(root) / "pocket-tts" if root else None
    if not folder or not folder.is_dir() or _ORIG["sherpa_onnx"] is None:
        check("SKIP - no pocket-tts under JARVIS_TEST_VOICE_MODELS", True)
        return
    d = reset()
    V._ZIP.update(engine=None, why="", built=False)
    CFG["pocket_dir"] = str(folder)
    ok, why = V.pocket_state()
    check("the real files match every pin", ok, why)
    if not ok:
        return
    make_voice(d)
    v = V.load_voice("grandpa")
    a = V.pocket_generate("Of course. I have added the dentist to Tuesday at ten.", v, 1.0, seed=3)
    b = V.pocket_generate("Of course. I have added the dentist to Tuesday at ten.", v, 1.15, seed=3)
    check("the real Pocket TTS made sound", len(a[0]) > 24000, len(a[0]))
    check("KNOWN, measured: with one seed, speed 1.15 gives the same sound (speed is ignored)",
          len(a[0]) == len(b[0]) and np.allclose(a[0], b[0]), (len(a[0]), len(b[0])))


# ------------------------------------------------------------ "hey Jarvis" --

def t_one_file_one_hash_both_apps():
    for name, info in W.KNOWN_FILES.items():
        p = ASSETS / name
        check(f"the phone's {name} is the pinned file", p.is_file() and sha(p) == info["sha256"])
        check(f"{name}: publisher, version and licence recorded",
              info["publisher"] and info["version"] == "v0.5.1" and "CC BY-NC-SA" in info["licence"])
    readme = (HERE / "README.md").read_text(encoding="utf-8")
    check("the PC's install line checks the same hashes",
          all(i["sha256"].upper() in readme for i in W.KNOWN_FILES.values()))
    kt = (REPO / "jarvis-client/app/src/main/java/com/jarvis/client/voice/OrtWakeModels.kt"
          ).read_text(encoding="utf-8")
    check("the phone loads the pinned head by name",
          f'WAKE_FILE = "{W.PHRASE_MODELS["hey_jarvis"]}"' in kt)
    tool = (REPO / "tools" / "train_wakeword.py").read_text(encoding="utf-8")
    check("the training tool and the PC pin the same livekit-wakeword commit",
          f'LIVEKIT_COMMIT = "{W.LIVEKIT_COMMIT}"' in tool)


def _wake_dir(with_candidate=True, commit=None, bad_hash=False, manifest=True):
    d = Path(tempfile.mkdtemp(prefix="wake-", dir=TMP))
    for n in ("melspectrogram.onnx", "embedding_model.onnx", "hey_jarvis_v0.1.onnx"):
        shutil.copyfile(ASSETS / n, d / n)
    if with_candidate:
        # Today's own head stands in for a trained candidate: the right shape.
        shutil.copyfile(ASSETS / "hey_jarvis_v0.1.onnx", d / W.CANDIDATE_FILE)
        if manifest:
            (d / W.CANDIDATE_MANIFEST).write_text(json.dumps({
                "version": 1, "sha256": "0" * 64 if bad_hash else sha(d / W.CANDIDATE_FILE),
                "livekit_commit": commit or W.LIVEKIT_COMMIT, "threshold": 1.7,
                "created": "2026-09-26 10:00:00"}))
    W.model_dir = lambda: d
    return d


def t_the_candidate_fails_closed():
    orig = W.model_dir
    try:
        _wake_dir(with_candidate=False)
        st = W.candidate_status()
        check("no candidate: not present, and it says how to train one",
              not st["present"] and not st["ok"] and "trains it" in st["why"], st)
        _wake_dir(manifest=False)
        st = W.candidate_status()
        check("no manifest: refused, and it names the file", st["present"] and not st["ok"]
              and W.CANDIDATE_MANIFEST in st["why"], st)
        _wake_dir(commit="1" * 40)
        st = W.candidate_status()
        check("another livekit-wakeword commit: refused", not st["ok"] and "different" in st["why"], st)
        _wake_dir(bad_hash=True)
        st = W.candidate_status()
        check("a changed file: refused", not st["ok"] and "SHA-256" in st["why"], st)
        d = _wake_dir()
        st = W.candidate_status()
        check("the file the training wrote down: ok, threshold held inside 0.1-0.99",
              st["ok"] and st["threshold"] == 0.99 and st["sha256"] == sha(d / W.CANDIDATE_FILE), st)
        if W.ort is None:
            check("SKIP - onnxruntime is not installed", True)
            return
        m = W.load_head(d / W.CANDIDATE_FILE)
        check("a (1, 16, 96) -> (1, 1) model loads on today's front end", m is not None)
        try:
            W.load_head(d / "melspectrogram.onnx")
            check("a model of the wrong shape is refused", False)
        except ValueError as exc:
            check("a model of the wrong shape is refused, in words", "needs [1, 16, 96]" in str(exc),
                  str(exc))
        check("spot() never uses the candidate: today's model is the one loaded",
              W.model_paths()["wake"].endswith("hey_jarvis_v0.1.onnx"))
    finally:
        W.model_dir = orig
        W.reload()


def t_both_heads_score_the_same_windows():
    if W.ort is None:
        check("SKIP - onnxruntime is not installed", True)
        return
    orig = W.model_dir
    try:
        d = _wake_dir()
        W.reload()
        cur = W._load()
        cand = W.load_head(d / W.CANDIDATE_FILE)
        heads = B.Heads(W, cur, cand, 0.5, None)
        x = np.random.default_rng(0).standard_normal(16000 * 3).astype(np.float32) * 0.05
        sc = heads.score(x, 16000)
        check("the same model on the same windows gives the same scores",
              len(sc["cur"]) == len(sc["cand"]) > 20 and np.allclose(sc["cur"], sc["cand"]))
        check("the first five scores after a start are ignored, as upstream does",
              sc["cur"][:5] == [0.0] * 5)
        ref = W._clip_steps(cur, x, 16000)[0]
        check("today's scores are exactly spot()'s", np.allclose(ref, sc["cur"]))
        check("time per step is measured for both", all(v >= 0 for v in heads.ms_per_step()))
    finally:
        W.model_dir = orig
        W.reload()


# ------------------------------------------------------------- the bake-off --

GOOD_WAKE = {
    "candidate_ok": True,
    "owner": {"clips": 12, "cur_heard": 11, "cand_heard": 12, "cur_heard_v": 11,
              "cand_heard_v": 12, "verifier": True},
    "room": {"minutes": 61.0, "cur_wakes": 4, "cand_wakes": 1, "cur_per_hour": 3.9,
             "cand_per_hour": 1.0},
    "kokoro": {"hey": 44, "other": 66, "cur_hey": 44, "cand_hey": 44, "cur_other": 8,
               "cand_other": 2},
    "cand_head_ms": 0.3,
}


def _with(base, path, value):
    m = json.loads(json.dumps(base))
    cur = m
    for k in path[:-1]:
        cur = cur[k]
    cur[path[-1]] = value
    return m


def t_the_wake_verdict_rule_by_rule():
    v, why = B.wake_verdict(GOOD_WAKE)
    check("every rule met: replace", v == B.REPLACE, why)
    cases = [
        ("no candidate", {"candidate_ok": False, "candidate_why": "none trained"}),
        ("9 of the owner's clips", _with(GOOD_WAKE, ["owner", "clips"], 9)),
        ("59 minutes of the room", _with(GOOD_WAKE, ["room", "minutes"], 59.0)),
        ("hears fewer of the owner's clips", _with(GOOD_WAKE, ["owner", "cand_heard"], 10)),
        ("the owner's check lets fewer through",
         _with(GOOD_WAKE, ["owner", "cand_heard_v"], 10)),
        ("more false wakes in the room", _with(GOOD_WAKE, ["room", "cand_per_hour"], 4.0)),
        ("fewer built-in \"hey Jarvis\" heard", _with(GOOD_WAKE, ["kokoro", "cand_hey"], 43)),
        ("more built-in others woken on", _with(GOOD_WAKE, ["kokoro", "cand_other"], 9)),
        ("Kokoro missing", _with(GOOD_WAKE, ["kokoro"], {"hey": 0})),
        ("too costly per step", _with(GOOD_WAKE, ["cand_head_ms"], 2.5)),
        ("cost not measured", _with(GOOD_WAKE, ["cand_head_ms"], None)),
    ]
    for label, m in cases:
        v, why = B.wake_verdict(m)
        check(f"keep: {label}", v == B.KEEP and why, why)
    tie = _with(_with(GOOD_WAKE, ["owner", "cand_heard"], 11), ["room", "cand_wakes"], 3)
    v, why = B.wake_verdict(tie)
    check("keep: no clear win (a tie is not a reason to change)",
          v == B.KEEP and any("clear win" in w for w in why), why)
    quiet = _with(_with(GOOD_WAKE, ["owner", "cand_heard"], 11), ["room", "cur_wakes"], 0)
    v, _ = B.wake_verdict(_with(quiet, ["room", "cand_wakes"], 0))
    check("keep: today's never woke in the room, so halving it proves nothing", v == B.KEEP)
    no_ver = _with(_with(GOOD_WAKE, ["owner", "verifier"], False), ["owner", "cand_heard_v"], 0)
    check("without a trained check, that rule is not asked",
          B.wake_verdict(no_ver)[0] == B.REPLACE)


GOOD_VOICE = {
    "pocket_ok": True, "zipvoice_ok": True, "silent": [], "zipvoice_first": 2.0,
    "pocket_first": 1.0, "pocket_rtf": 0.7, "vram_rise_mb": 0, "chat_pushed_off": False,
    "ear": {"answered": 3, "pocket": 1, "same": 1, "zipvoice": 1},
    "speed": {"choice": "normal", "pocket_follows": False},
}


def t_the_voice_verdict_rule_by_rule():
    v, why = B.voice_verdict(GOOD_VOICE)
    check("every rule met: replace", v == B.REPLACE, why)
    cases = [
        ("Pocket not installed", _with(GOOD_VOICE, ["pocket_ok"], False)),
        ("ZipVoice not installed", _with(GOOD_VOICE, ["zipvoice_ok"], False)),
        ("a sentence made no sound", _with(GOOD_VOICE, ["silent"], ["pocket: \"x\""])),
        ("first sound only 15% faster", _with(GOOD_VOICE, ["pocket_first"], 1.7)),
        ("first sound not measured", _with(GOOD_VOICE, ["pocket_first"], None)),
        ("slower than speech", _with(GOOD_VOICE, ["pocket_rtf"], 1.2)),
        ("graphics memory not readable", _with(GOOD_VOICE, ["vram_rise_mb"], None)),
        ("graphics memory rose 300 MB", _with(GOOD_VOICE, ["vram_rise_mb"], 300)),
        ("the chat model lost room", _with(GOOD_VOICE, ["chat_pushed_off"], True)),
        ("not listened to", _with(GOOD_VOICE, ["ear"], {"answered": 0})),
        ("ZipVoice preferred twice",
         _with(GOOD_VOICE, ["ear"], {"answered": 3, "pocket": 1, "same": 0, "zipvoice": 2})),
        ("Faster chosen and not followed",
         _with(GOOD_VOICE, ["speed"], {"choice": "faster", "pocket_follows": False})),
    ]
    for label, m in cases:
        v, why = B.voice_verdict(m)
        check(f"keep: {label}", v == B.KEEP and why, why)
    ok = _with(GOOD_VOICE, ["speed"], {"choice": "slower", "pocket_follows": True})
    check("a speed it follows is fine", B.voice_verdict(ok)[0] == B.REPLACE)


def t_small_helpers():
    check("wake-ups are counted once per 2 seconds",
          B.count_wakes([0, .9, .9, .9, 0, 0] + [0] * 30 + [.8], 0.5, 25) == 2)
    check("nothing above the bar is no wake-up", B.count_wakes([0.4] * 100, 0.5) == 0)
    check("graphics memory rise: the biggest on any card",
          B.rise_mb([1000, 50], [1040, 300]) == 250 and B.rise_mb(None, [1]) is None
          and B.rise_mb([10], [5]) == 0)
    check("the middle value", B.median([3, 1, 2]) == 2 and B.median([]) is None)
    p = TMP / "x.wav"
    B.write_wav(p, np.linspace(-0.5, 0.5, 16000), 16000)
    x, r = B.read_wav(p)
    check("a WAV written and read back", r == 16000 and len(x) == 16000
          and abs(float(x[0]) + 0.5) < 1e-3)
    try:
        B.read_wav(TMP / "missing.wav")
        check("a missing WAV is refused in words", False)
    except ValueError as exc:
        check("a missing WAV is refused in words", "missing.wav" in str(exc))


def t_the_whole_run_with_nothing_installed():
    d = Path(tempfile.mkdtemp(prefix="bake-", dir=TMP))
    env = dict(os.environ, OPENJARVIS_CONFIG_DIR=str(d), JARVIS_CONFIG_DIR=str(d),
               PYTHONPATH=os.pathsep.join([str(BACKEND), str(HERE), str(HERE / "rebuilt")]))
    r = subprocess.run([sys.executable, str(BACKEND / "jarvis_bakeoff.py")], env=env,
                       stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=300)
    check("it finishes", r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:])
    runs = sorted((d / "voice" / "bakeoff").glob("2*")) if (d / "voice" / "bakeoff").is_dir() else []
    ok = bool(runs) and (runs[-1] / "results.txt").is_file() and (runs[-1] / "results.json").is_file()
    check("results.txt and results.json are written, and the path is printed",
          ok and str(runs[-1] / "results.txt") in r.stdout, r.stdout[-800:])
    if ok:
        doc = json.loads((runs[-1] / "results.json").read_text(encoding="utf-8"))
        check("both verdicts: keep what we have (nothing to compare)",
              doc["wake"]["verdict"] == B.KEEP and doc["voice"]["verdict"] == B.KEEP, doc)
        check("the rules are written into the results", doc["wake_rules"] == B.WAKE_RULES
              and doc["voice_rules"] == B.VOICE_RULES)
    check("it says nothing was switched on", "Nothing was switched on" in r.stdout)


def t_no_recording_of_the_owner_is_kept():
    written = []

    def fake_record(p, seconds):
        written.append(Path(p))
        B.write_wav(p, np.full(int(16000 * seconds), 0.1, np.float32), 16000)
    orig = (B.record_wav, B.ask)
    B.record_wav, B.ask = fake_record, (lambda prompt, default="": "")
    try:
        got = B.record_owner_clips(B.Out(), 3)
    finally:
        B.record_wav, B.ask = orig
    check("the recordings come back in memory", len(got) == 3 and all(r == 16000 for _x, r in got))
    check("and every file they passed through is gone, folder and all",
          written and not any(p.exists() or p.parent.exists() for p in written), written)


def t_nothing_leaves_the_pc():
    src = (BACKEND / "jarvis_bakeoff.py").read_text(encoding="utf-8")
    urls = set(re.findall(r"https?://[^\s\"')]+", src))
    check("the only address it calls is this PC's own Ollama",
          urls == {"http://127.0.0.1:11434/api/ps"}, urls)
    check("through jarvis_local_http (no proxy), never urllib's own urlopen",
          "H.urlopen(" in src and "urllib.request.urlopen" not in src and "socket" not in src)
    check("it changes no setting: it never writes Jarvis's state or config",
          "_write_state" not in src and "set_speed" not in src and ".toml" not in src)


def t_shipped_and_pinned():
    ps = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    import _where
    check("apply-patches.ps1 and _where.SHIPPED copy jarvis_bakeoff.py in",
          "'jarvis_bakeoff.py'" in ps and "jarvis_bakeoff.py" in _where.SHIPPED)
    req = (HERE / "requirements.txt").read_text(encoding="utf-8")
    check("requirements.txt has a sherpa-onnx floor with Pocket TTS in it",
          re.search(r"^sherpa-onnx>=1\.12\.26\b", req, re.M) is not None)
    routes = (HERE / "voices.patch").read_text(encoding="utf-8")
    check("voices.patch routes the speed POST", '"/api/voice/voices/speed"' in routes)
    check("voices.patch routes the one-time animal voice question's answer",
          '"/api/voice/voices/face_offer"' in routes)
    check("voices.patch routes each animal's voice and its Try it (a WAV)",
          '"/api/voice/voices/face_animal"' in routes
          and 'route == "/api/voice/voices/face_animal/try"' in routes
          and 'ctype="audio/wav"' in routes)


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("t_") and callable(v)]
    try:
        for fn in tests:
            print(f"\n--- {fn.__name__} ---")
            try:
                fn()
            except Exception:
                FAILED.append(fn.__name__)
                traceback.print_exc(file=sys.stdout)
    finally:
        for n, v in _ORIG.items():
            setattr(V, n, v)
        S._cfg = _S_CFG
        S._tts_cache = S._UNSET
        shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
