""""Stop" while Jarvis talks: the stop head, and where hear() asks it.

    python3 test_stopword.py

    # and, where the model files exist (the dev container used for this, or
    # the owner's PC once installed), the real models too:
    JARVIS_TEST_VOICE_MODELS=<folder holding wakeword/ tts/ vad/> python3 test_stopword.py

No network, no microphone. What it proves:
  1. The file format: the shipped head reads, and anything else (wrong
     magic, wrong shape, cut short, a NaN) is refused.
  2. The arithmetic: a head whose last layer is zero says sigmoid(bias);
     LayerNorm makes the first layer's scale irrelevant, as it should.
  3. The PC and the phone hold the same numbers: the phone's asset is
     jarvis_stopword.py's head byte for byte, its golden file is this code's
     output, and StopHead.THRESHOLD (StopWord.kt) is THRESHOLD.
  4. spot_stop(): no head or no models is said, not crashed; the first
     scores after a start (primed on silence) never count.
  5. hear(): a SHORT wake-word clip that is "stop" answers stop and nothing
     else - no "hey Jarvis" spotter, no owner check, no speech-to-text. A
     longer clip is never asked; push-to-talk is never asked; switched off
     asks nothing; "stop" just after Jarvis itself said "stop" is ignored.
  6. status() reports the stop word; nothing is written or logged.
  7. With the real models: Kokoro saying "Stop." is heard, and through
     hear() answers stop; ordinary sentences are not.
"""
import array
import io
import json
import math
import os
import re
import struct
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
require_shipped("jarvis_wakeword.py", "jarvis_speech.py", "jarvis_stopword.py")
import numpy as np  # noqa: E402
import jarvis_wakeword as W  # noqa: E402
import jarvis_speech as S  # noqa: E402
import jarvis_stopword as SW  # noqa: E402
import jarvis_voice as V  # noqa: E402

FAILED, PASSED, SKIPPED = [], [], []
D = W.EMB_WINDOW * 96


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if not cond else ""))


def skip(name, why):
    SKIPPED.append(name)
    print(f"skip  {name} - {why}")


def tone(freq=220.0, seconds=1.0, rate=16000, amp=0.4) -> bytes:
    s = array.array("h", [int(amp * 32767 * math.sin(2 * math.pi * freq * i / rate))
                          for i in range(int(seconds * rate))])
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(s.tobytes())
    return b.getvalue()


def boom(what):
    def f(*a, **k):
        raise AssertionError(f"{what} ran, and must not have")
    return f


def make_head(h=4, seed=0, w3_zero=False, b3=0.0) -> bytes:
    rng = np.random.default_rng(seed)
    parts = [rng.normal(0, 0.05, (D, h)), rng.normal(0, 0.1, h), np.ones(h), np.zeros(h),
             rng.normal(0, 0.3, (h, h)), rng.normal(0, 0.1, h), np.ones(h), np.zeros(h),
             np.zeros((h, 1)) if w3_zero else rng.normal(0, 0.5, (h, 1)), np.array([b3])]
    return W.STOP_MAGIC + struct.pack("<ii", h, D) + b"".join(
        np.ascontiguousarray(p, dtype="<f4").tobytes() for p in parts)


class Env:
    """Temp config dir; the wake word ON through its card; windows closed."""

    def __init__(self, on=True):
        self.on = on

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.patches = [mock.patch.object(S, "_config_dir", return_value=d),
                        mock.patch.object(W, "_config_dir", return_value=d),
                        mock.patch.object(V, "PROFILE_PATH", d / "owner.json")]
        for p in self.patches:
            p.start()
        S.reload_engines()
        S._reset_wake_for_tests()
        with S._SAYS_LOCK:
            S._RECENT_SAYS.clear()
        if self.on:
            S.set_wake_enabled(True, gate=lambda *a: type("V", (), {
                "allowed": True, "tier": "ask", "outcome": "approved", "request_id": "r",
                "reason": ""})(), tier_of=lambda a: "ask", spawn=lambda fn: fn())
        return self

    def __exit__(self, *a):
        S._reset_wake_for_tests()
        with S._SAYS_LOCK:
            S._RECENT_SAYS.clear()
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()
        S.reload_engines()


# ------------------------------------------------------------ 1. format --

def t_the_format():
    raw = SW.head_bytes()
    head = W.parse_stop_head(raw)
    check("the shipped head reads", head["W1"].shape == (D, SW.HIDDEN), head["W1"].shape)
    check("its threshold is a probability", 0.0 < SW.THRESHOLD < 1.0, SW.THRESHOLD)

    def refused(b):
        try:
            W.parse_stop_head(b)
        except ValueError:
            return True
        return False
    bad_shape = bytearray(raw)
    bad_shape[12:16] = struct.pack("<i", D - 1)
    nan = bytearray(raw)
    nan[16:20] = struct.pack("<f", float("nan"))
    check("wrong magic, wrong shape, cut short, a NaN, nothing: all refused",
          refused(b"XSTOP1\x00\x00" + raw[8:]) and refused(bytes(bad_shape))
          and refused(raw[:-4]) and refused(bytes(nan)) and refused(b""))


# -------------------------------------------------------- 2. arithmetic --

def t_the_arithmetic():
    x = np.random.default_rng(3).normal(0, 1, (5, D))
    head = W.parse_stop_head(make_head(w3_zero=True, b3=1.25))
    p = W.stop_probabilities(head, x)
    check("a zero last layer says sigmoid(bias) for every window",
          np.allclose(p, 1 / (1 + math.exp(-1.25)), atol=1e-6), p.tolist())
    a = W.parse_stop_head(make_head(seed=7))
    b = {k: v.copy() for k, v in a.items()}
    b["W1"] *= 3.0
    b["b1"] *= 3.0
    pa, pb = W.stop_probabilities(a, x), W.stop_probabilities(b, x)
    check("LayerNorm: scaling the first layer changes nothing",
          np.allclose(pa, pb, atol=1e-4), (pa.tolist(), pb.tolist()))
    check("16 x 96 windows and flat 1,536 ones are the same thing",
          np.allclose(W.stop_probabilities(a, x.reshape(5, 16, 96)), pa))


# ----------------------------------------------------- 3. PC == phone --

def t_the_phone_has_the_same_numbers():
    asset = REPO / "jarvis-client" / "app" / "src" / "main" / "assets" / "wakeword" / "stop_head.bin"
    check("the phone's stop_head.bin is jarvis_stopword.py's head, byte for byte",
          asset.is_file() and asset.read_bytes() == SW.head_bytes())
    golden = json.loads((REPO / "jarvis-client" / "app" / "src" / "test" / "resources"
                         / "stop-golden.json").read_text(encoding="utf-8"))
    head = W.parse_stop_head(SW.head_bytes())
    worst = 0.0
    for c in golden["cases"]:
        k = c["k"]
        x = np.array([2.5 * math.sin(0.0137 * (i + 1) * (k + 1) + 0.5 * k) for i in range(D)], np.float32)
        worst = max(worst, abs(float(W.stop_probabilities(head, x[None])[0]) - c["p"]))
    real = np.array(golden["stop_window"], np.float32)
    worst = max(worst, abs(float(W.stop_probabilities(head, real[None])[0]) - golden["stop_p"]))
    check("the phone's golden file is this code's output (StopWordTest reads it)",
          worst < 1e-6 and golden["threshold"] == SW.THRESHOLD and golden["bytes"] == len(SW.head_bytes()),
          worst)
    check("...and its real 'stop' window is heard", golden["stop_p"] >= SW.THRESHOLD, golden["stop_p"])
    kt = (REPO / "jarvis-client" / "app" / "src" / "main" / "java" / "com" / "jarvis" / "client"
          / "voice" / "StopWord.kt").read_text(encoding="utf-8")
    m = re.search(r"const val THRESHOLD = ([0-9.]+)f", kt)
    check("StopHead.THRESHOLD on the phone is THRESHOLD here",
          m is not None and float(m.group(1)) == SW.THRESHOLD, m and m.group(0))


# ---------------------------------------------------------- 4. spot_stop --

def t_spot_stop():
    with mock.patch.object(W, "_STOP_CACHE", {"head": None}):
        s = W.spot_stop(np.zeros(1000, np.float32))
    check("no head: said, not crashed", not s.ran and "jarvis_stopword" in s.why, s)
    with mock.patch.object(W, "_load", return_value=None):
        W._STOP_CACHE.clear()
        s = W.spot_stop(np.zeros(1000, np.float32))
    check("no wake-word models: said, not crashed", not s.ran and s.why, s)
    sure = (W.parse_stop_head(make_head(w3_zero=True, b3=6.0)), 0.5)
    wins = [np.zeros((16, 96), np.float32)] * 8
    with mock.patch.object(W, "_STOP_CACHE", {"head": sure}), \
            mock.patch.object(W, "_load", return_value=object()), \
            mock.patch.object(W, "_clip_steps", lambda m, x, r: (np.zeros(8, np.float32), wins)):
        s = W.spot_stop(np.zeros(1000, np.float32))
    check("a sure head is heard - but never on the first scores after a start",
          s.ran and s.heard and s.score > 0.99
          and s.at == round(max(0.0, (W.WARMUP_SCORES + 1) * W.CHUNK / W.SAMPLE_RATE
                                - W.LEAD_IN_SECONDS), 2), s)
    few = [np.zeros((16, 96), np.float32)] * W.WARMUP_SCORES
    with mock.patch.object(W, "_STOP_CACHE", {"head": sure}), \
            mock.patch.object(W, "_load", return_value=object()), \
            mock.patch.object(W, "_clip_steps", lambda m, x, r: (np.zeros(len(few), np.float32), few)):
        s = W.spot_stop(np.zeros(1000, np.float32))
    check("...so a clip only as long as the warm-up is not a stop", s.ran and not s.heard, s)
    W._STOP_CACHE.clear()
    W.reload()
    check("reload() forgets the head", "head" not in W._STOP_CACHE)


# ------------------------------------------------------------- 5. hear --

def heard_stop(*a, **k):
    return W.Spot(True, heard=True, score=0.97, threshold=SW.THRESHOLD)


def t_hear_short_stop_does_nothing_else():
    with Env():
        with mock.patch.object(W, "spot_stop", heard_stop), \
                mock.patch.object(W, "spot", boom("the 'hey Jarvis' spotter")), \
                mock.patch.object(V, "verify", boom("the owner check")), \
                mock.patch.object(S, "_transcribe", boom("speech-to-text")):
            h = S.hear(tone(seconds=1.0), source="wake_word")
        d = h.as_dict()
        check("a short 'stop': stop, and nothing else ran",
              d["stop"] and not d["ok"] and not d["owner"] and not d["wake_heard"]
              and d["text"] == "" and d["threshold"] == 0, d)
        check("...and it did not use up a follow-up window", not S._take_awake())


def t_hear_long_clip_is_never_a_stop():
    with Env():
        with mock.patch.object(W, "spot_stop", boom("the stop word")), \
                mock.patch.object(W, "spot", return_value=W.Spot(True, heard=False, score=0.01)), \
                mock.patch.object(S, "_transcribe", boom("speech-to-text")):
            h = S.hear(tone(seconds=S.STOP_MAX_SECONDS + 0.5), source="wake_word")
        check("a clip longer than STOP_MAX_SECONDS is never asked, and goes the usual way",
              not h.stop and not h.wake_heard, h)
        # With the VAD, it is the SPEECH that counts, not the clip.
        with mock.patch.object(S, "_speech_span", lambda x, sr: (0, int(sr * 1.2))), \
                mock.patch.object(W, "spot_stop", heard_stop):
            h = S.hear(tone(seconds=4.0), source="wake_word")
        check("a 4 s clip with 1.2 s of speech in it is asked", h.stop, h)


def t_hear_push_to_talk_and_off_never_ask():
    with Env():
        with mock.patch.object(W, "spot_stop", boom("the stop word")):
            h = S.hear(tone(), source="push_to_talk")
        check("push-to-talk never asks the stop word", not h.stop, h)
    with Env(on=False):
        with mock.patch.object(W, "spot_stop", boom("the stop word")):
            h = S.hear(tone(), source="wake_word")
        check("wake word switched off: the stop word is not asked either",
              not h.stop and not h.available, h)


def t_hear_ignores_jarvis_saying_stop():
    with Env():
        with mock.patch.object(S, "_tts_engine", return_value=None):
            S.say("I will stop the timer now.")
        with mock.patch.object(W, "spot_stop", heard_stop), \
                mock.patch.object(W, "spot", boom("the 'hey Jarvis' spotter")), \
                mock.patch.object(S, "_transcribe", boom("speech-to-text")):
            h = S.hear(tone(), source="wake_word")
        check("'stop' just after Jarvis said 'stop' itself: ignored, and said why",
              not h.stop and "itself" in h.reason, h)
        with S._SAYS_LOCK:
            S._RECENT_SAYS[:] = [(t - S.STOP_ECHO_SECONDS - 1, s, m)
                                 for t, s, m in S._RECENT_SAYS]
        with mock.patch.object(W, "spot_stop", heard_stop):
            h = S.hear(tone(), source="wake_word")
        check("...but only for STOP_ECHO_SECONDS", h.stop, h)


def t_only_the_whole_word_stop_counts():
    # T11: r"\bstop" matched "stopped", "stopwatch", "stops"; the owner's own
    # "stop" was then ignored for 30 s after any such sentence.
    for said, want in (("The download stopped.", False), ("Your stopwatch is at 3 minutes.", False),
                       ("It stops at nine.", False), ("Non-stop flights only.", True),
                       ("The bus stop is on Main Street.", True), ("Stop.", True)):
        with Env():
            with mock.patch.object(S, "_tts_engine", return_value=None):
                S.say(said)
            got = S._jarvis_said_stop() is not None
            check(f"Jarvis said {said!r}: counts as saying 'stop' = {want}", got == want)
    with Env():
        with mock.patch.object(S, "_tts_engine", return_value=None):
            S.say("The download stopped.")
        with mock.patch.object(W, "spot_stop", heard_stop):
            h = S.hear(tone(), source="wake_word")
        check("after 'The download stopped.', the owner's 'stop' is acted on at once",
              h.stop and not h.stop_ignored, h)


def t_the_stop_echo_window_is_per_app():
    with Env():
        with mock.patch.object(S, "_tts_engine", return_value=None):
            S.say("I will stop the timer now.", mic="phone")
        with mock.patch.object(W, "spot_stop", heard_stop):
            desk = S.hear(tone(), source="wake_word", mic="desktop")
            phone = S.hear(tone(), source="wake_word", mic="phone")
            unnamed = S.hear(tone(), source="wake_word")
        check("Jarvis said 'stop' on the phone: the desktop's stop is still acted on",
              desk.stop and not desk.stop_ignored, desk)
        check("... the phone's is ignored, with the reason as a field and in words",
              not phone.stop and phone.stop_ignored and "said the word \"stop\" itself" in
              phone.reason and "Say it again in" in phone.reason
              and phone.as_dict()["stop_ignored"] is True, phone)
        check("... and a clip with no microphone named is checked against everything",
              not unnamed.stop and unnamed.stop_ignored, unnamed)
    with Env():
        with mock.patch.object(S, "_tts_engine", return_value=None):
            S.say("Stop means stop.")          # no app named: what the route does today
        with mock.patch.object(W, "spot_stop", heard_stop):
            h = S.hear(tone(), source="wake_word", mic="desktop")
        check("words said with no app named still count for both apps",
              not h.stop and h.stop_ignored, h)


def t_hear_not_stop_goes_on_as_before():
    with Env():
        order = []

        def stop(*a, **k):
            order.append("stop")
            return W.Spot(True, heard=False, score=0.02)

        def spot(*a, **k):
            order.append("spot")
            return W.Spot(True, heard=False, score=0.02)
        with mock.patch.object(W, "spot_stop", stop), mock.patch.object(W, "spot", spot), \
                mock.patch.object(V, "verify", boom("the owner check")):
            h = S.hear(tone(), source="wake_word")
        check("not 'stop': the stop word first, then the 'hey Jarvis' spotter as before",
              order == ["stop", "spot"] and not h.stop and not h.wake_heard, order)


# ---------------------------------------------------------- 6. status --

def t_status_and_quiet():
    with Env():
        st = S.status()
    sw = st["wake"].get("stop_word", {})
    check("status: wake.stop_word with its threshold",
          "available" in sw and sw.get("threshold") in (SW.THRESHOLD, 0.0), sw)
    src = (HERE / "jarvis_stopword.py").read_text(encoding="utf-8")
    bad = [w for w in ("print(", "open(", "logging", "write") if w in src]
    check("jarvis_stopword.py prints, logs and writes nothing", not bad, bad)


# ---------------------------------------------------------- 7. real --

def t_real_models():
    root = os.environ.get("JARVIS_TEST_VOICE_MODELS")
    if not root:
        skip("real models", "JARVIS_TEST_VOICE_MODELS is not set")
        return
    root = Path(root)
    cfg = {"wake_model_dir": str(root / "wakeword"),
           "tts_model": str(root / "tts" / "model.onnx"),
           "tts_voices": str(root / "tts" / "voices.bin"),
           "tts_tokens": str(root / "tts" / "tokens.txt"),
           "tts_data_dir": str(root / "tts" / "espeak-ng-data"),
           "vad_model": str(root / "vad" / "silero_vad.onnx")}
    real_s, real_w = S._cfg, W._cfg

    def fake(k, d=None):
        return cfg[k] if k in cfg else real_s(k, d)
    with mock.patch.object(S, "_cfg", fake), \
            mock.patch.object(W, "_cfg", lambda k, d=None: cfg[k] if k in cfg else real_w(k, d)):
        S.reload_engines()
        W.reload()
        if S._tts_engine() is None or W._load() is None:
            skip("real models", f"no tts/ or wakeword/ under {root}")
            return

        def said(text, sid):
            with mock.patch.object(S, "_cfg", lambda k, d=None: sid if k == "tts_speaker_id" else fake(k, d)):
                return S._read_wav(S.say(text))
        hits = [W.spot_stop(*said(t, sid)) for t in ("Stop.", "Stop!") for sid in (0, 6)]
        check(f"Kokoro saying 'stop' is heard ({[h.score for h in hits]})",
              all(h.heard for h in hits), hits)
        quiet = [W.spot_stop(*said(t, 5)) for t in (
            "The shop on the corner closes at six.", "Your next meeting is at three o'clock.",
            "Top.")]
        check(f"...and ordinary words are not ({[q.score for q in quiet]})",
              not any(q.heard for q in quiet), quiet)
        # The known weak spot, shown rather than asserted: a single word that
        # sounds like "stop" on its own ("stuff", "stomp", "top") fires one
        # time in six to eight on synthetic voices (jarvis_stopword.py). Harmless
        # - it only stops speech - but it is not a pass.
        weak = W.spot_stop(*said("Stuff.", 5))
        print(f"note  sound-alike 'Stuff.' (Kokoro 5) scores {weak.score} "
              f"({'fires' if weak.heard else 'does not fire'}) - a known weak spot")
        with Env():
            with mock.patch.object(S, "_cfg", lambda k, d=None: 6 if k == "tts_speaker_id" else fake(k, d)):
                wav = S.say("Stop.")
            with S._SAYS_LOCK:
                S._RECENT_SAYS.clear()  # that was the test speaking, not Jarvis
            with mock.patch.object(S, "_cfg", fake), \
                    mock.patch.object(V, "verify", boom("the owner check")), \
                    mock.patch.object(S, "_transcribe", boom("speech-to-text")):
                h = S.hear(wav, source="wake_word")
            check("hear(): a real 'Stop.' answers stop, before any owner check", h.stop, h)
    S.reload_engines()
    W.reload()


if __name__ == "__main__":
    for fn in (t_the_format, t_the_arithmetic, t_the_phone_has_the_same_numbers, t_spot_stop,
               t_hear_short_stop_does_nothing_else, t_hear_long_clip_is_never_a_stop,
               t_hear_push_to_talk_and_off_never_ask, t_hear_ignores_jarvis_saying_stop,
               t_only_the_whole_word_stop_counts, t_the_stop_echo_window_is_per_app,
               t_hear_not_stop_goes_on_as_before, t_status_and_quiet, t_real_models):
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
