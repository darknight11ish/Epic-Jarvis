"""Smart Turn: "has the owner finished speaking, or only paused?"

    python3 test_turn.py

    # and, where the model files exist (the dev container used for this, or
    # the owner's PC once installed), the real model too:
    JARVIS_TEST_VOICE_MODELS=<folder holding turn/ tts/> python3 test_turn.py

No network, no microphone. What it proves:
  1. The features the model is fed are Pipecat's own, number for number
     (reference values computed with pipecat-ai 1.11.0's
     _whisper_features.py on 2026-09-24 - the 0.0 difference was measured
     over four clip lengths), and the phone's golden file is the PC's.
  2. The window: the last 8 s, zero-padded at the FRONT when shorter.
  3. predict(): threshold, a NaN score is "not finished", no model is said.
  4. The route's handler: a bad clip is a 400 that quotes nothing, a clip
     too long is refused, stereo 48 kHz is taken, no model is a 200 with
     available: false.
  5. Nothing is written or logged by the module.
  6. voice-turn.patch applies on top of voice-enroll.patch's route and
     reverses; the route checks origin and token before reading the body
     and never quotes an exception.
  7. status() carries `turn` with the owner's switch and the pause rule.
  8. With the real model and Kokoro: complete sentences read as finished
     and hesitant fragments ("..., um,") mostly do not.
"""
import array
import ast
import io
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import traceback
import wave
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

sys.path.insert(0, str(HERE / "rebuilt"))
sys.path.insert(0, str(HERE))
require_shipped("jarvis_turn.py", "jarvis_speech.py")
import numpy as np  # noqa: E402
import jarvis_turn as T  # noqa: E402
import jarvis_speech as S  # noqa: E402
import _skeleton  # noqa: E402

FAILED, PASSED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def skip(name, why):
    SKIPPED.append(name)
    print(f"skip  {name} - {why}")


def signal_pcm() -> np.ndarray:
    """The golden signal: 3 s, as 16-bit PCM, back to floats."""
    n = 48000
    t = np.arange(n, dtype=np.float64) / 16000
    x = (0.3 * np.sin(2 * np.pi * 180 * t) * (0.5 + 0.5 * np.sin(2 * np.pi * 3 * t))
         + 0.05 * np.sin(2 * np.pi * 1234 * t)).astype(np.float32)
    return np.round(x * 32767).astype(np.int16).astype(np.float32) / 32768.0


def wav(samples, rate=16000, channels=1) -> bytes:
    x = np.clip(np.asarray(samples, dtype=np.float32), -1, 1)
    pcm = (x * 32767).astype("<i2")
    if channels > 1:
        pcm = np.repeat(pcm, channels)
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    return b.getvalue()


# ------------------------------------------------------------- 1. features --

#: [mel, frame, value], from Pipecat's compute_whisper_log_mel_features on
#: signal_pcm() padded to 8 s. See the module docstring.
PIPECAT = [(0, 0, -0.156543), (0, 799, 0.91466), (40, 500, 0.716003), (79, 799, -0.156543),
           (10, 700, 0.373318), (5, 600, 1.600705), (60, 650, -0.156543), (20, 777, -0.09371)]


def t_features_are_pipecats():
    f = T.features(T.last_window(signal_pcm()))
    check("features are 80 x 800 float32", f.shape == (80, 800) and f.dtype == np.float32,
          f"{f.shape} {f.dtype}")
    worst = max(abs(float(f[m, fr]) - v) for m, fr, v in PIPECAT)
    check("every reference point matches Pipecat's (to 1e-5)", worst < 1e-5, worst)
    check("and the mean", abs(float(f.mean()) - (-0.053441)) < 1e-5, float(f.mean()))
    golden = REPO / "jarvis-client" / "app" / "src" / "test" / "resources" / "smart-turn-golden.json"
    g = json.loads(golden.read_text(encoding="utf-8"))
    worst = max(abs(float(f[m, fr]) - v) for m, fr, v in g["points"])
    check("the phone's golden file is this function's output (SmartTurnTest reads it)",
          worst < 1e-5 and abs(float(f.mean()) - g["mean"]) < 1e-5, worst)


def t_the_window():
    short = np.full(100, 0.25, dtype=np.float32)
    w = T.last_window(short)
    check("short audio: 8 s long, zeros in FRONT", len(w) == T.N_SAMPLES and w[0] == 0.0
          and w[-1] == 0.25)
    long = np.concatenate([np.full(500, 0.1, np.float32), np.full(T.N_SAMPLES, 0.2, np.float32)])
    check("long audio: the END is kept", T.last_window(long)[0] == np.float32(0.2))


# ------------------------------------------------------------ 3. predict --

class FakeSession:
    def __init__(self, p):
        self.p, self.shapes = p, []

    def run(self, _, feeds):
        x = next(iter(feeds.values()))
        self.shapes.append(x.shape)
        return [np.array([[self.p]], dtype=np.float32)]


def t_predict():
    x = signal_pcm()
    for p, want in ((0.93, True), (0.2, False), (float("nan"), False)):
        s = FakeSession(p)
        with mock.patch.object(T, "_load", return_value=(s, "input_features")):
            t = T.predict(x)
        check(f"p={p}: complete is {want}", t.ran and t.complete is want, t)
        check(f"p={p}: the model got [1, 80, 800]", s.shapes == [(1, 80, 800)], s.shapes)
    with mock.patch.object(T, "_load", return_value=None), \
            mock.patch.object(T, "model_path", return_value=Path("/nowhere/x.onnx")):
        t = T.predict(x)
    check("no model: did not run, and says where it looked", not t.ran and "/nowhere" in t.why,
          t)
    s = FakeSession(0.6)
    with mock.patch.object(T, "_load", return_value=(s, "input_features")), \
            mock.patch.object(T, "_cfg", side_effect=lambda k, d=None:
                              0.8 if k == "turn_threshold" else d):
        t = T.predict(x)
    check("[voice] turn_threshold is the bar (0.6 < 0.8: not finished)",
          t.threshold == 0.8 and t.complete is False, t)
    with mock.patch.object(T, "_cfg", side_effect=lambda k, d=None:
                           5.0 if k == "turn_threshold" else d):
        check("a silly threshold is held in range", T.threshold() == 0.95)


# -------------------------------------------------------------- 4. route --

def t_handle():
    code, out = T.handle(b"not a wav at all")
    check("garbage: 400, and the reply quotes nothing it was sent",
          code == 400 and "not a wav" not in json.dumps(out), (code, out))
    code, out = T.handle(wav(np.zeros(int(16000 * 31))))
    check("longer than 30 s: 400", code == 400, (code, out))
    s = FakeSession(0.9)
    with mock.patch.object(T, "_load", return_value=(s, "input_features")):
        code, out = T.handle(wav(signal_pcm()[:24000], rate=48000, channels=2))
    check("stereo 48 kHz is taken, and the answer has the fields voice.rs reads",
          code == 200 and out["available"] is True and out["complete"] is True
          and isinstance(out["probability"], float), (code, out))
    with mock.patch.object(T, "_load", return_value=None):
        code, out = T.handle(wav(signal_pcm()))
    check("no model: 200, available false, with a reason", code == 200
          and out["available"] is False and out["why"], (code, out))


def t_nothing_is_written_or_logged():
    tree = ast.parse((HERE / "jarvis_turn.py").read_text(encoding="utf-8"))
    main = next((n for n in tree.body if isinstance(n, ast.If)
                 and "__main__" in ast.unparse(n.test)), None)
    bad = []
    for node in ast.walk(tree):
        if main is not None and any(node is m for m in ast.walk(main)):
            continue
        if isinstance(node, ast.Call):
            name = ast.unparse(node.func)
            if name in ("print", "open") or name.startswith(("logging.", "log.")) \
                    or name.endswith((".write_bytes", ".write_text", ".save")):
                bad.append(name)
    check("no print, open, log or file write outside `__main__`", not bad, bad)


# -------------------------------------------------------------- 6. patch --

def _added(patch: str) -> str:
    return "\n".join(l[1:] for l in (HERE / patch).read_text(encoding="utf-8").splitlines()
                     if l.startswith("+") and not l.startswith("+++"))


def t_the_patch():
    added = _added("voice-turn.patch")
    check("origin and token are checked before the body is read",
          added.index("_origin_ok(self)") < added.index("_read_body(self)")
          and added.index("_token_ok(self)") < added.index("_read_body(self)"))
    check("nothing logged, no header read, no exception quoted",
          "print(" not in added and "self.headers" not in added and "str(exc)" not in added
          and "{exc}" not in added, added)
    check("it only calls jarvis_turn.handle", "jarvis_turn.handle(raw)" in added)
    git = shutil.which("git")
    if not git:
        return skip("the patch rehearsal", "git is not installed")
    import test_voice_enroll as TE  # its stand-in for what voice-enroll patches
    d = Path(tempfile.mkdtemp(prefix="jarvis-turn-skel-"))
    try:
        with open(d / "jarvis_hud.py", "w", encoding="utf-8", newline="\n") as f:
            f.write(TE._stand_in())
        for name, steps in (("voice-enroll.patch", (["apply"],)),
                            ("voice-turn.patch", (["apply", "--check"], ["apply"],
                                                  ["apply", "--check", "--reverse"]))):
            lf = d / name
            lf.write_bytes((HERE / name).read_bytes().replace(b"\r\n", b"\n"))
            for args in steps:
                r = subprocess.run([git] + args + [str(lf)], cwd=d, capture_output=True,
                                   text=True)
                if r.returncode != 0:
                    return check(f"{name}: git {' '.join(args)}", False,
                                 r.stderr.strip() or r.stdout.strip())
        out = (d / "jarvis_hud.py").read_text(encoding="utf-8")
        check("voice-turn.patch applies after voice-enroll.patch, and reverses", True)
        check("the route sits after /api/voice/enroll and before the models tuple",
              out.index('route == "/api/voice/enroll"') < out.index('route == "/api/voice/turn"')
              < out.index('if route in ("/api/models/install"'))
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ------------------------------------------------------------- 7. status --

def t_status_carries_turn():
    with mock.patch.object(S, "_config_dir", return_value=Path(tempfile.mkdtemp())):
        st = S.status()
    turn = st.get("turn", {})
    check("status has turn with the pause rule the clients use",
          turn.get("ask_after_ms") == 200 and turn.get("max_pause_ms") == 2000
          and turn.get("enabled") is True and "available" in turn, turn)
    with mock.patch.object(S, "_cfg", side_effect=lambda k, d=None:
                           False if k == "turn_enabled" else d):
        off = S._turn_state()
    check("[voice] turn_enabled = false is reported, with why",
          off["enabled"] is False and "turn_enabled" in off["why"], off)
    with mock.patch.dict(sys.modules, {"jarvis_turn": None}):
        gone = S._turn_state()
    check("no jarvis_turn.py: not available, and says so",
          gone["available"] is False and "jarvis_turn.py" in gone["why"], gone)


# -------------------------------------------------------- 8. real model --

def t_real_model():
    root = os.environ.get("JARVIS_TEST_VOICE_MODELS")
    if not root or not (Path(root) / "turn" / T.MODEL_FILE).is_file():
        return skip("real model", "set JARVIS_TEST_VOICE_MODELS to a folder with turn/ "
                    "and tts/ to run this")
    root = Path(root)
    cfg = {"turn_model": str(root / "turn" / T.MODEL_FILE),
           "tts_model": str(root / "tts" / "model.onnx"),
           "tts_voices": str(root / "tts" / "voices.bin"),
           "tts_tokens": str(root / "tts" / "tokens.txt"),
           "tts_data_dir": str(root / "tts" / "espeak-ng-data")}
    real_s, real_t = S._cfg, T._cfg

    def fake(real):
        return lambda k, d=None: cfg[k] if k in cfg else real(k, d)
    pairs = (("Can you remind me to call my sister on Thursday afternoon?",
              "Can you remind me to call my, um,"),
             ("I want to book a table for four people tomorrow night.",
              "I want to book a table for..."),
             ("Send a message to Sam saying I will be late.", "Send a message to Sam saying that,"),
             ("How long does it take to drive to the airport?", "How long does it take to, um,"))
    with mock.patch.object(S, "_cfg", fake(real_s)), mock.patch.object(T, "_cfg", fake(real_t)):
        S.reload_engines()
        if not T.status()["available"]:
            return check("the real model loads", False, T.status())
        done, frag = [], []
        for full, part in pairs:
            for text, into in ((full, done), (part, frag)):
                x, sr = S._read_wav(S.say(text))
                x = T._to_16k(x, sr)
                loud = np.where(np.abs(x) > 0.01)[0]
                x = x[: loud[-1] + 1]
                x = np.concatenate([x, np.zeros(3200, np.float32)])  # the 0.2 s pause
                into.append(T.predict(x).probability)
    S.reload_engines()
    check(f"complete sentences read as finished ({[round(p, 2) for p in done]})",
          all(p >= 0.5 for p in done), done)
    check(f"hesitant fragments mostly do not ({[round(p, 2) for p in frag]})",
          sum(p < 0.5 for p in frag) >= 3, frag)


if __name__ == "__main__":
    for fn in (t_features_are_pipecats, t_the_window, t_predict, t_handle,
               t_nothing_is_written_or_logged, t_the_patch, t_status_carries_turn,
               t_real_model):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed, {len(SKIPPED)} skipped")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
