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


class FakeKokoro:
    def __init__(self):
        self.speeds = []

    def generate(self, text, sid=0, speed=1.0):
        self.speeds.append(speed)
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


def reset():
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
