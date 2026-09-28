""""Hey Jarvis": the spotter, the order in hear(), and the switch's card.

    python3 test_wakeword.py

    # and, where the model files exist (the dev container used for this, or
    # the owner's PC once installed), the real models too:
    JARVIS_TEST_VOICE_MODELS=<folder holding wakeword/ stt/ tts/ vad/> python3 test_wakeword.py

No network, no microphone. What it proves:
  1. The spotter's streaming is chunk-size independent and ignores its first
     five scores, as openWakeWord does (a stand-in model, so this runs
     without the model files).
  2. The transcript check: "hey Jarvis, ..." counts, "...called Jarvis" does
     not, and the words after the phrase are what Jarvis is asked.
  3. The ORDER in hear() for a wake-word clip - each later step is made to
     raise if it is reached: switched off -> nothing runs; no phrase -> no
     owner check, no speech-to-text; not the owner -> no speech-to-text.
  4. "Hey Jarvis." on its own opens ONE follow-up window, owner-checked,
     for the microphone that heard it only; and one "hey Jarvis" heard by
     the phone AND the PC is answered once (the voice play test, F2,
     2026-09-27) - the other copy is `other_device`, no words kept.
  5. The switch: ON is one approval card and nothing else - denied, timed
     out, refused, a verdict at the wrong tier, the tier not "ask", a second
     request while one waits, and "off" while the card waits all leave it
     off. OFF never waits. The card says what saying no costs.
  6. Nothing is written or logged by the spotter module.
  7. 48 kHz audio (the desktop's microphone) is filtered, not folded.
  8. With the real models: synthesised "hey Jarvis" clips are heard and
     ordinary sentences are not; speech-to-text hears the command.
  9. The owner's verifier: it is built only from clips the spotter heard
     "hey Jarvis" in, holds numbers and never audio, decides on every step
     the first model is at least a little interested in (and only those),
     falls back to the first model when missing or unreadable, and - with
     the real models - keeps its owner while turning other voices away.
"""
import array
import ast
import io
import math
import os
import sys
import tempfile
import threading
import traceback
import wave
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

sys.path.insert(0, str(HERE / "rebuilt"))
sys.path.insert(0, str(HERE))
require_shipped("jarvis_wakeword.py", "jarvis_speech.py", "jarvis_voices.py")
import numpy as np  # noqa: E402
import jarvis_wakeword as W  # noqa: E402
import jarvis_speech as S  # noqa: E402
import jarvis_voice as V  # noqa: E402
import jarvis_voices as VC  # noqa: E402
from _voice_test import semantic_voice  # noqa: E402

FAILED, PASSED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


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


class Env:
    """Temp config dir; wake switch reset; the follow-up window closed."""

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.patches = [mock.patch.object(S, "_config_dir", return_value=d),
                        mock.patch.object(W, "_config_dir", return_value=d),
                        mock.patch.object(V, "PROFILE_PATH", d / "owner.json"),
                        # The order of the checks, not the minimum length of a
                        # command (test_voice_strict.py has that, with the
                        # wake word): no minimum for these one-second tones.
                        mock.patch.object(S, "_min_command_seconds", return_value=0.0)]
        for p in self.patches:
            p.start()
        # A stand-in speaker model (_voice_test.py): since 2026-09-24 the
        # basic check lets nobody in. V.EcapaEmbedder() is it, in here.
        self._voice = semantic_voice(V, settings_dir=d)
        self._voice.__enter__()
        S.reload_engines()
        S._reset_wake_for_tests()
        return self

    def __exit__(self, *a):
        self._voice.__exit__(None, None, None)
        S._reset_wake_for_tests()
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()
        S.reload_engines()


def verdict(allowed=True, tier="ask", outcome="approved"):
    return type("V", (), {"allowed": allowed, "tier": tier, "outcome": outcome,
                          "request_id": "rq", "reason": "because"})()


def turn_on():
    return S.set_wake_enabled(True, gate=lambda *a: verdict(), tier_of=lambda a: "ask",
                              spawn=lambda fn: fn())


# -------------------------------------------------------------- 1. stream --

class FakeModels:
    """Stands in for the three ONNX files: deterministic, shape-correct."""
    mel_in = emb_in = wake_in = "x"

    def __init__(self):
        outer = self

        class Emb:
            def run(self, _o, feed):
                x = feed[outer.emb_in]
                return [x.reshape(x.shape[0], -1)[:, :96].mean(axis=1, keepdims=True)
                        .repeat(96, axis=1).reshape(-1, 1, 1, 96)]
        self.emb = Emb()

    def melspec(self, x):
        n = (len(x) - 512) // 160 + 1
        frames = np.array([x[i * 160:i * 160 + 512].mean() for i in range(n)], dtype=np.float32)
        return np.repeat(frames[:, None], 32, axis=1) / 1000.0

    def embed(self, frames):
        return frames.mean(axis=0, keepdims=True)[:, :1].repeat(96, axis=1)

    def score(self, feats):
        return float(1 / (1 + math.exp(-feats[-1, 0])))


def t_streaming_does_not_depend_on_chunk_size():
    rng = np.random.default_rng(3)
    x = rng.normal(0, 3000, 16000 * 3).astype(np.float32)
    one = W.Spotter(FakeModels()).feed(x)
    sp = W.Spotter(FakeModels())
    many, i = [], 0
    while i < len(x):
        n = int(rng.integers(1, 3000))
        many += sp.feed(x[i:i + n])
        i += n
    check("one score per 80 ms step", len(one) == len(x) // W.CHUNK, f"{len(one)}")
    check("feeding in odd-sized pieces gives the same scores",
          len(one) == len(many) and np.allclose(one, many), f"{one[:6]} vs {many[:6]}")
    check("the first five scores are ignored, as upstream does",
          one[:W.WARMUP_SCORES] == [0.0] * W.WARMUP_SCORES and any(s > 0 for s in one[5:]))
    check("the raw window is exactly the 1760 samples that make 8 mel frames",
          W.MEL_INPUT == 1760 and (1760 - 512) // 160 + 1 == 8)


# --------------------------------------------------------- 2. the words --

def t_the_transcript_check():
    cases = {
        "Hey Jarvis, what time is it?": (True, "what time is it?"),
        "Hey, Jarvis. Turn off the lights.": (True, "Turn off the lights."),
        "Jarvis what's on today": (True, "what's on today"),
        "Hey Javis turn off the lights in the kitchen.": (True, "turn off the lights in the kitchen."),
        "Okay Jarvis": (True, ""),
        "Hey Jarvis.": (True, ""),
        "so anyway hey Jarvis what's the weather": (True, "what's the weather"),
        "I watched a film where the computer was called Jarvis.": (False, ""),
        "Put the jar of jam on the shelf, please.": (False, ""),
        "Hey Jason, are you coming to dinner tonight?": (False, ""),
        "": (False, ""),
    }
    for text, want in cases.items():
        got = W.split_wake(text)
        check(f"split_wake({text!r}) -> {want}", got == want, f"got {got}")


# ------------------------------------------------------------ 3. order --

def t_order_wake_switched_off_runs_nothing():
    with Env():
        with mock.patch.object(W, "spot", boom("the spotter")), \
                mock.patch.object(V, "verify", boom("the owner check")), \
                mock.patch.object(S, "_transcribe", boom("speech-to-text")):
            h = S.hear(tone(), source="wake_word")
        check("wake word off: refused before the spotter, the owner check or STT",
              not h.is_owner and "switched off" in h.reason, h)


def t_order_no_phrase_no_owner_check():
    with Env():
        turn_on()
        with mock.patch.object(W, "spot", return_value=W.Spot(True, heard=False, score=0.02)), \
                mock.patch.object(V, "verify", boom("the owner check")), \
                mock.patch.object(S, "_transcribe", boom("speech-to-text")):
            h = S.hear(tone(), source="wake_word")
        d = h.as_dict()
        check("no 'hey Jarvis': not owner-checked, not transcribed, dropped",
              not d["owner"] and not d["ok"] and not d["wake_heard"] and d["threshold"] == 0
              and d["wake_score"] == 0.02, d)


def t_order_not_the_owner_is_never_transcribed():
    with Env():
        turn_on()
        samples, _ = S._read_wav(tone(220.0))
        V.enroll([samples] * 3, embedder=V.EcapaEmbedder(), path=V.PROFILE_PATH)
        with mock.patch.object(W, "spot", return_value=W.Spot(True, heard=True, score=0.99)), \
                mock.patch.object(S, "_transcribe", boom("speech-to-text")):
            h = S.hear(tone(880.0), source="wake_word")
        check("'hey Jarvis' from a stranger: refused by the owner check, never transcribed",
              not h.is_owner and h.threshold > 0 and h.text == "", h)


def t_order_the_owner_is_heard_and_the_phrase_removed():
    with Env():
        turn_on()
        samples, _ = S._read_wav(tone(220.0))
        V.enroll([samples] * 3, embedder=V.EcapaEmbedder(), path=V.PROFILE_PATH)
        order = []
        real_verify = V.verify

        def spot(*a, **k):
            order.append("spot")
            return W.Spot(True, heard=True, score=0.97)

        def verify(*a, **k):
            order.append("verify")
            return real_verify(*a, **k)

        def stt(*a, **k):
            order.append("stt")
            return "Hey Jarvis, what is on my calendar?"
        with mock.patch.object(W, "spot", spot), mock.patch.object(V, "verify", verify), \
                mock.patch.object(S, "_stt_engine", return_value=object()), \
                mock.patch.object(S, "_transcribe", stt):
            h = S.hear(tone(220.0), source="wake_word")
        d = h.as_dict()
        check("spotter, then owner check, then speech-to-text - in that order",
              order == ["spot", "verify", "stt"], order)
        check("the command without the wake phrase is what comes back",
              d["ok"] and d["wake_heard"] and d["text"] == "what is on my calendar?"
              and d["wake_score"] == 0.97, d)

        with mock.patch.object(W, "spot", return_value=W.Spot(True, heard=True, score=0.9)), \
                mock.patch.object(S, "_stt_engine", return_value=object()), \
                mock.patch.object(S, "_transcribe",
                                  return_value="The computer in that film was called Jarvis."):
            h = S.hear(tone(220.0), source="wake_word").as_dict()
        check("a sentence that merely MENTIONS Jarvis is dropped, words and all",
              h["owner"] and not h["wake_heard"] and h["text"] == "" and "ignored" in h["reason"], h)


def t_follow_up_window():
    with Env():
        turn_on()
        samples, _ = S._read_wav(tone(220.0))
        V.enroll([samples] * 3, embedder=V.EcapaEmbedder(), path=V.PROFILE_PATH)
        with mock.patch.object(W, "spot", return_value=W.Spot(True, heard=True, score=0.9)), \
                mock.patch.object(S, "_stt_engine", return_value=object()), \
                mock.patch.object(S, "_transcribe", return_value="Hey Jarvis."):
            first = S.hear(tone(220.0), source="wake_word").as_dict()
        check("'Hey Jarvis.' alone opens the follow-up window",
              first["awake"] and first["wake_heard"] and first["text"] == ""
              and first["awake_seconds"] > 0, first)
        with mock.patch.object(W, "spot", boom("the spotter")), \
                mock.patch.object(S, "_stt_engine", return_value=object()), \
                mock.patch.object(S, "_transcribe", return_value="What time is it?"):
            second = S.hear(tone(220.0), source="wake_word").as_dict()
        check("the next clip needs no phrase of its own", second["ok"] and second["wake_heard"]
              and second["text"] == "What time is it?", second)
        with mock.patch.object(W, "spot", return_value=W.Spot(True, heard=False, score=0.01)), \
                mock.patch.object(S, "_transcribe", boom("speech-to-text")):
            third = S.hear(tone(220.0), source="wake_word").as_dict()
        check("the window is used once", not third["ok"] and not third["wake_heard"], third)

        # A stranger does not get to open or use it.
        with mock.patch.object(W, "spot", return_value=W.Spot(True, heard=True, score=0.9)), \
                mock.patch.object(S, "_transcribe", boom("speech-to-text")):
            S.hear(tone(880.0), source="wake_word")
        check("a stranger's 'hey Jarvis' opens no window", not S._take_awake())
        with mock.patch.object(W, "spot", return_value=W.Spot(True, heard=True, score=0.9)), \
                mock.patch.object(S, "_stt_engine", return_value=object()), \
                mock.patch.object(S, "_transcribe", return_value="Hey Jarvis"):
            S.hear(tone(220.0), source="wake_word")
        S.set_wake_enabled(False)
        check("turning the wake word off closes an open window", not S._take_awake())


def _owner_wake(transcript, heard=True):
    """The spotter hears (or not) "hey Jarvis", and speech-to-text says
    `transcript` - for the owner's enrolled 220 Hz voice."""
    return (mock.patch.object(W, "spot", return_value=W.Spot(True, heard=heard,
                                                             score=0.9 if heard else 0.01)),
            mock.patch.object(S, "_stt_engine", return_value=object()),
            mock.patch.object(S, "_transcribe", return_value=transcript))


def _hear(transcript, mic, heard=True, freq=220.0):
    a, b, c = _owner_wake(transcript, heard)
    with a, b, c:
        return S.hear(tone(freq), source="wake_word", mic=mic).as_dict()


def _phone_verdict(w):
    """The phone's own WakeRules.verdict, restated (voice/WakeRules.kt)."""
    if not w["available"]:
        return "STOP"
    if w["too_short"] and w["wake_heard"]:
        return "TOO_SHORT"
    if w["too_short"]:
        return "IGNORE"
    if w["awake"] and w["owner"]:
        return "AWAKE"
    if w["wake_heard"] and w["owner"]:
        return "ANSWER"
    return "IGNORE"


def _desktop_drops(w):
    """voice.rs, the wake-word listener: a reply that is available, not
    `stop` and not `wake_heard` is dropped without a word."""
    return w["available"] and not w["stop"] and not w["wake_heard"]


def t_the_follow_up_window_is_per_device():
    """The voice play test's F2 (2026-09-27): "Hey Jarvis." opens a window
    for the microphone that heard it, not for the whole PC."""
    with Env():
        turn_on()
        samples, _ = S._read_wav(tone(220.0))
        V.enroll([samples] * 3, embedder=V.EcapaEmbedder(), path=V.PROFILE_PATH)
        first = _hear("Hey Jarvis.", "desktop")
        check("'Hey Jarvis.' to the desktop opens a window", first["awake"], first)
        S._SAME_WAKE.clear()          # not the same words heard twice: a later clip
        phone = _hear("What time is it?", "phone", heard=False)
        check("the phone's clip without the phrase does not use the desktop's window",
              not phone["ok"] and not phone["wake_heard"] and phone["text"] == "", phone)
        with mock.patch.object(W, "spot", boom("the spotter")), \
                mock.patch.object(S, "_stt_engine", return_value=object()), \
                mock.patch.object(S, "_transcribe", return_value="What time is it?"):
            desk = S.hear(tone(220.0), source="wake_word", mic="desktop").as_dict()
        check("... so the owner's question to the desktop still gets through",
              desk["ok"] and desk["wake_heard"] and desk["text"] == "What time is it?", desk)
        check("used once, as before", not S._take_awake("desktop"))

        S._reset_wake_for_tests()
        turn_on()
        S._open_awake("phone")
        check("a phone window is the phone's only",
              not S._take_awake("desktop") and S._take_awake("phone"))
        S._open_awake("")
        check("an unnamed app's window is not a named one's",
              not S._take_awake("phone") and not S._take_awake("desktop") and S._take_awake(""))
        S._open_awake("desktop")
        S._open_awake("phone")
        check("_take_awake() with no microphone (tests) takes any, and closes all",
              S._take_awake() and not S._take_awake("phone") and not S._take_awake("desktop"))
        S._open_awake("desktop")
        S.set_wake_enabled(False)
        check("turning the wake word off closes every window", not S._take_awake("desktop"))


def t_one_hey_jarvis_heard_by_two_devices():
    """The voice play test's F2 (2026-09-27), reproduced with this file's own
    harness (the tester's repro_two_devices.py): both the phone and the PC
    hear one "Hey Jarvis". Before the fix both were answered, or the second
    copy used the window up and the real question was dropped."""
    with Env():
        turn_on()
        samples, _ = S._read_wav(tone(220.0))
        V.enroll([samples] * 3, embedder=V.EcapaEmbedder(), path=V.PROFILE_PATH)
        # 1. "Hey Jarvis, what time is it?" - one answer.
        pc = _hear("Hey Jarvis, what time is it?", "desktop")
        order = []
        real_verify = V.verify

        def verify(*a, **k):
            order.append("verify")
            return real_verify(*a, **k)

        def stt(*a, **k):
            order.append("stt")
            return "Hey Jarvis, what time is it?"
        history = []
        with mock.patch.object(W, "spot", return_value=W.Spot(True, heard=True, score=0.9)), \
                mock.patch.object(V, "verify", verify), \
                mock.patch.object(S, "_stt_engine", return_value=object()), \
                mock.patch.object(S, "_transcribe", stt), \
                mock.patch.object(S, "_note_for_history", lambda *a, **k: history.append(a)):
            phone = S.hear(tone(220.0), source="wake_word", mic="phone").as_dict()
        check("the PC's copy is answered", pc["ok"] and pc["text"] == "what time is it?", pc)
        check("the phone's copy: no words, `other_device`, the plain reason",
              phone["text"] == "" and phone["other_device"] is True
              and phone["reason"] == "answered on your other device" and not phone["awake"], phone)
        check("... and the voice check still came before any speech-to-text",
              order == ["verify", "stt"], order)
        check("... and nothing from it went to chat history", history == [], history)
        check("the phone drops it without a word (WakeRules IGNORE)",
              _phone_verdict(phone) == "IGNORE", phone)
        check("the desktop would drop it without a word too (voice.rs)", _desktop_drops(phone), phone)
        check("the one that WAS answered says nothing about another device",
              pc["other_device"] is False, pc)

        # 2. "Hey Jarvis." on its own, heard by both, then the question.
        S._reset_wake_for_tests()
        turn_on()
        a = _hear("Hey Jarvis.", "desktop")
        b = _hear("Hey Jarvis.", "phone")
        check("the first 'Hey Jarvis.' opens its device's window", a["awake"], a)
        check("the second copy opens none, and says why",
              not b["awake"] and b["other_device"] and _phone_verdict(b) == "IGNORE", b)
        check("the phone has no window to use", not S._take_awake("phone"))
        c = _hear("What time is it?", "desktop", heard=False)
        check("the owner's real question to the PC is answered (it used to be dropped)",
              c["ok"] and c["wake_heard"] and c["text"] == "What time is it?", c)

        # 3. Whichever arrives first is answered - the phone, this time.
        S._reset_wake_for_tests()
        turn_on()
        first = _hear("Hey Jarvis, next song.", "phone")
        second = _hear("Hey Jarvis, next song.", "desktop")
        check("the phone first: the phone answers, the PC does not",
              first["text"] == "next song." and second["other_device"] and second["text"] == "",
              (first, second))

        # 4. What is NOT matched.
        S._reset_wake_for_tests()
        turn_on()
        one = _hear("Hey Jarvis, what time is it?", "desktop")
        two = _hear("Hey Jarvis, and the date?", "desktop")
        check("the same microphone twice is the owner talking again: both answered",
              one["text"] and two["text"] == "and the date?" and not two["other_device"], two)
        S._SAME_WAKE["at"] -= S.SAME_WAKE_SECONDS + 0.5
        late = _hear("Hey Jarvis, set a timer.", "phone")
        check(f"another device more than {S.SAME_WAKE_SECONDS} s later is answered",
              late["text"] == "set a timer." and not late["other_device"], late)
        with mock.patch.object(S, "_stt_engine", return_value=object()), \
                mock.patch.object(S, "_transcribe", return_value="what is the weather"):
            push = S.hear(tone(220.0), source="push_to_talk", mic="desktop").as_dict()
        check("the talk button is never matched (one deliberate press)",
              push["ok"] and push["text"] == "what is the weather" and not push["other_device"], push)
        S._reset_wake_for_tests()
        turn_on()
        a, b2, c2 = _owner_wake("Hey Jarvis, what time is it?")
        with a, b2, mock.patch.object(S, "_transcribe", boom("speech-to-text")):
            stranger = S.hear(tone(880.0), source="wake_word", mic="phone").as_dict()
        owner = _hear("Hey Jarvis, what time is it?", "desktop")
        check("a stranger's clip claims nothing: refused as before, not transcribed",
              not stranger["ok"] and not stranger["other_device"], stranger)
        check("... and the owner's own clip right after it is answered",
              owner["text"] == "what time is it?" and not owner["other_device"], owner)
        S._reset_wake_for_tests()
        turn_on()
        noted = _hear("The computer in that film was called Jarvis.", "desktop")
        after = _hear("Hey Jarvis, what time is it?", "phone")
        check("a clip that was not addressed to Jarvis claims nothing",
              noted["text"] == "" and not noted["other_device"]
              and after["text"] == "what time is it?" and not after["other_device"], (noted, after))


def t_two_devices_at_once():
    """Both copies arrive together (two request threads): exactly one is
    answered."""
    with Env():
        turn_on()
        samples, _ = S._read_wav(tone(220.0))
        V.enroll([samples] * 3, embedder=V.EcapaEmbedder(), path=V.PROFILE_PATH)
        out = {}
        gate = threading.Barrier(2)

        def one(mic):
            gate.wait()
            out[mic] = S.hear(tone(220.0), source="wake_word", mic=mic).as_dict()
        a, b, c = _owner_wake("Hey Jarvis, set a timer for ten minutes.")
        with a, b, c:
            ts = [threading.Thread(target=one, args=(m,)) for m in ("phone", "desktop")]
            for t in ts:
                t.start()
            for t in ts:
                t.join(30)
        answered = [m for m, w in out.items() if w["text"]]
        other = [m for m, w in out.items() if w["other_device"]]
        check("exactly one device's copy is answered, the other is 'other device'",
              len(answered) == 1 and len(other) == 1 and set(answered + other) == {"phone", "desktop"},
              out)


def _said(text, mic=""):
    """What say() does for one sentence, with a stand-in voice (0.5 s)."""
    sound = (np.zeros(12000, dtype=np.float32), 24000, "kokoro", "builtin", "", "", "")
    with mock.patch.object(S, "_synthesise", return_value=sound):
        return S.say(text, mic=mic)


def t_after_a_question():
    """Keep listening after a question (the owner's decision of 2026-09-25):
    when the last sentence Jarvis spoke asks something, the next wake-word
    clip needs no phrase - the owner check still runs, and only a clip that
    passes it uses the window up."""
    import json as _json
    from _where import REPO
    cases = _json.loads((REPO / "jarvis-desktop" / "tests" / "fixtures"
                         / "voice-flow-cases.json").read_text(encoding="utf-8"))
    check("the question marks are the apps' own list",
          list(S.QUESTION_MARKS) == cases["question_marks"], S.QUESTION_MARKS)
    for c in cases["question_cases"]:
        check(f"ends with a question: {c['text']!r} -> {c['question']}",
              S.ends_with_question(c["text"]) is c["question"])

    with Env():
        turn_on()
        samples, _ = S._read_wav(tone(220.0))
        V.enroll([samples] * 3, embedder=V.EcapaEmbedder(), path=V.PROFILE_PATH)
        owner = mock.patch.object(S, "_stt_engine", return_value=object())

        check("a sentence that asks nothing opens nothing",
              _said("It is ten o'clock.") is not None and not S._question_open())
        _said("Shall I book the table?")
        check("a question said aloud opens the window", S._question_open())
        # Jarvis's own voice, the TV, anyone else: not the owner - and the
        # window is NOT used up by them.
        with mock.patch.object(W, "spot", boom("the spotter")), \
                mock.patch.object(S, "_transcribe", boom("speech-to-text")):
            other = S.hear(tone(880.0), source="wake_word").as_dict()
        check("a clip that is not the owner is not transcribed", not other["ok"], other)
        check("...and leaves the window open", S._question_open())
        with mock.patch.object(W, "spot", boom("the spotter")), owner, \
                mock.patch.object(S, "_transcribe", return_value="Yes please, at eight."):
            reply = S.hear(tone(220.0), source="wake_word").as_dict()
        check("the owner's answer needs no \"hey Jarvis\"", reply["ok"] and reply["wake_heard"]
              and reply["text"] == "Yes please, at eight.", reply)
        check("used once", not S._question_open())

        _said("Shall I book the table?")
        _said("Or I can wait until you decide.")
        check("a sentence after the question closes it: the question was not the last word",
              not S._question_open())

        _said("Shall I book it?", mic="phone")
        check("a question said to the phone opens it for the phone only",
              S._question_open("phone") and not S._question_open("desktop"))
        with mock.patch.object(W, "spot", return_value=W.Spot(True, heard=False, score=0.01)), \
                mock.patch.object(S, "_transcribe", boom("speech-to-text")):
            desk = S.hear(tone(220.0), source="wake_word", mic="desktop").as_dict()
        check("the desktop's clip still needs the phrase", not desk["ok"], desk)

        _said("Shall I book it?")
        with mock.patch.object(W, "spot", boom("the spotter")), owner, \
                mock.patch.object(S, "_transcribe", return_value="Hey Jarvis, yes."):
            said_it = S.hear(tone(220.0), source="wake_word").as_dict()
        check("\"hey Jarvis\" said anyway: the words after it are the answer",
              said_it["ok"] and said_it["text"] == "yes.", said_it)

        _said("Shall I book it?")
        S._QUESTION["at"] -= 3600
        check("it closes on its own: the awake time after the question has played",
              not S._question_open())

        _said("Shall I book it?")
        with mock.patch.object(S, "_transcribe", boom("speech-to-text")):
            push = S.hear(tone(220.0), source="push_to_talk")
        check("push-to-talk is unchanged and does not use it", S._question_open(), push)
        S.set_wake_enabled(False)
        check("turning the wake word off closes it", not S._question_open())


def t_no_spotter_is_said_not_crashed():
    with Env():
        turn_on()
        with mock.patch.object(V, "verify", boom("the owner check")):
            h = S.hear(tone(), source="wake_word")   # no model files in the temp dir
        check("no wake-word models: refused, not available, and says why",
              not h.is_owner and not h.available and "hey Jarvis" in h.reason, h)
        st = S.status()
        check("status says the PC cannot hear it, and why",
              st["wake"]["spotter"]["available"] is False and st["wake"]["spotter"]["why"]
              and "cannot hear it yet" in st["listening"]["wake_word_why"], st["wake"])


def t_push_to_talk_is_unchanged():
    with Env():
        with mock.patch.object(W, "spot", boom("the spotter")):
            h = S.hear(tone(440.0), source="push_to_talk")
        check("push-to-talk never runs the spotter", not h.is_owner and "no enrolled" in h.reason, h)


# ------------------------------------------------------------ 5. switch --

def t_the_switch_is_one_card():
    cases = {
        "denied": (verdict(False, "ask", "denied"), "denied"),
        "timed out": (verdict(False, "ask", "timed_out"), "timed_out"),
        "refused": (verdict(False, "ask", "refused"), "refused"),
        "allowed at tier auto (nobody asked)": (verdict(True, "auto", "approved"), "refused"),
        "allowed at tier notify": (verdict(True, "notify", None), "refused"),
    }
    for label, (v, want) in cases.items():
        with Env():
            r = S.set_wake_enabled(True, gate=lambda *a, v=v: v, tier_of=lambda a: "ask",
                                   spawn=lambda fn: fn())
            st = S.wake_state()
            check(f"{label}: stays off, recorded as {want}",
                  r["ok"] and not S._wake_enabled() and st["last"]["outcome"] == want, (r, st))
    with Env():
        def gate_raises(*a):
            raise RuntimeError("no gate")
        S.set_wake_enabled(True, gate=gate_raises, tier_of=lambda a: "ask", spawn=lambda fn: fn())
        check("a gate that fails: stays off", not S._wake_enabled()
              and S.wake_state()["last"]["outcome"] == "refused")

    with Env():
        r = S.set_wake_enabled(True, gate=boom("the card"), tier_of=lambda a: "auto",
                               spawn=lambda fn: fn())
        check("tier not 'ask': no card is raised at all, and it says why",
              not r["ok"] and "'ask'" in r["error"] and not S._wake_enabled(), r)

    with Env():
        seen = {}

        def gate(action, detail, prompt):
            seen.update(action=action, detail=detail, prompt=prompt)
            return verdict()
        turn_on_r = S.set_wake_enabled(True, gate=gate, tier_of=lambda a: "ask",
                                       spawn=lambda fn: fn())
        check("the card is change_own_config", seen.get("action") == "change_own_config", seen)
        check("the card says what saying no costs, and that no sound leaves before the phrase",
              "If you say no" in seen.get("prompt", "") and "No sound is sent" in seen["prompt"])
        check("approved: on, and the reply still says a card was raised (not 'done')",
              S._wake_enabled() and turn_on_r["pending"] is True)

    with Env():
        held = threading.Event()
        release = threading.Event()

        def slow_gate(*a):
            held.set()
            release.wait(5)
            return verdict()
        r1 = S.set_wake_enabled(True, gate=slow_gate, tier_of=lambda a: "ask")
        held.wait(5)
        r2 = S.set_wake_enabled(True, gate=boom("a second card"), tier_of=lambda a: "ask")
        check("a second ON while a card waits is refused, not a second card",
              r1["pending"] and not r2["ok"] and r2["pending"], (r1, r2))
        check("status shows the card waiting", S.status()["listening"]["wake_word_pending"] is True)
        off = S.set_wake_enabled(False)
        check("OFF is immediate, even with a card waiting", off["ok"] and not S._wake_enabled())
        release.set()
        for _ in range(100):
            if S.wake_state().get("last"):
                break
            __import__("time").sleep(0.02)
        check("approving the stale card afterwards does NOT turn it back on",
              not S._wake_enabled() and S.wake_state()["last"]["outcome"] == "withdrawn",
              S.wake_state())

    # AP-5: two full rounds. The second ON replaced the pending record and
    # the first card's "withdrawn" flag went with it.
    with Env():
        cards = []
        ask = lambda: S.set_wake_enabled(True, gate=lambda *a: verdict(),
                                         tier_of=lambda a: "ask", spawn=cards.append)
        ask(); S.set_wake_enabled(False); ask(); S.set_wake_enabled(False)
        check("two ON/OFF rounds: two cards were raised", len(cards) == 2)
        cards[0]()
        check("two rounds, the FIRST card approved last: the later OFF still wins",
              not S._wake_enabled() and S.wake_state()["last"]["outcome"] == "withdrawn",
              S.wake_state())
        cards[1]()
        check("... and the second card too", not S._wake_enabled()
              and S.wake_state()["last"]["outcome"] == "withdrawn")


# ------------------------------------------------------------ 6. quiet --

def t_the_spotter_module_writes_and_logs_nothing():
    src = (HERE / "jarvis_wakeword.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    main_block = [n for n in tree.body if isinstance(n, ast.If)
                  and "__main__" in ast.unparse(n.test)]
    body = [n for n in tree.body if n not in main_block]
    calls = {ast.unparse(n.func) for m in body for n in ast.walk(m) if isinstance(n, ast.Call)}
    bad = {c for c in calls if c in ("print", "open") or c.startswith(("logging.", "log."))
           or c.endswith((".write_text", ".write_bytes", ".write"))}
    check("jarvis_wakeword.py prints, logs and writes nothing (outside __main__)", not bad, bad)


# --------------------------------------------------------- 7. resample --

def t_48k_is_filtered_not_folded():
    def level(freq):
        x = np.sin(2 * np.pi * freq * np.arange(48000) / 48000).astype(np.float32)
        y = W.to_16k(x, 48000)[1000:-1000]
        return float(np.sqrt(np.mean(y ** 2)) / np.sqrt(0.5)), len(W.to_16k(x, 48000))
    speech, n = level(1000.0)
    alias, _ = level(10000.0)      # would fold down to 6 kHz unfiltered
    check("48 kHz -> 16 kHz keeps the length right", n == 16000, n)
    check("a 1 kHz tone passes (> 0.9)", speech > 0.9, speech)
    check("a 10 kHz tone is removed rather than folded into the speech band (< 0.05)",
          alias < 0.05, alias)


# ----------------------------------------------------- 8. real models --

# ------------------------------------------------------- 9. verifier --

def _fake_steps(table):
    """_clip_steps stand-in: each clip is an int naming (scores, windows)."""
    def f(models, clip, rate):
        scores, wins = table[int(clip[0])]
        return np.asarray(scores, dtype=np.float32), list(wins)
    return f


def _win(v):
    return np.full((W.EMB_WINDOW, 96), v, dtype=np.float32)


def t_the_verifier():
    rng = np.random.default_rng(3)
    own = lambda: _win(1.0) + rng.normal(0, 0.05, (16, 96)).astype(np.float32)   # noqa: E731
    other = lambda: _win(-1.0) + rng.normal(0, 0.05, (16, 96)).astype(np.float32)  # noqa: E731
    # Clips 0-2: "hey Jarvis" (the spotter fires on two steps); 3-5: other speech.
    table = {i: ([0.0, 0.9, 0.8, 0.0] + [0.0] * 25, [other(), own(), own()] + [other()] * 26)
             for i in range(3)}
    table.update({i: ([0.0] * 20, [other() for _ in range(20)]) for i in range(3, 6)})
    clips = [np.full(10, i, dtype=np.float32) for i in range(6)]
    with Env(), mock.patch.object(W, "_load", return_value=object()),             mock.patch.object(W, "_clip_steps", _fake_steps(table)),             mock.patch.object(W, "_bank", return_value=np.stack([other().reshape(-1)] * 5)):
        out = W.build_verifier(clips)
        check("built from the three clips the spotter heard", out["built"] and out["clips"] == 3
              and out["positives"] == 6 and out["bank"] == 5, {k: out[k] for k in out if k != "doc"})
        doc = out["doc"]
        check("the file is weights and counts - 1,536 numbers, a bias, no audio",
              len(doc["w"]) == 1536 and isinstance(doc["b"], float)
              and set(doc) == {"version", "model", "mic", "w", "b", "threshold", "gate",
                               "positives", "negatives", "clips", "bank", "created"}, sorted(doc))
        few = W.build_verifier(clips[:1] + clips[3:])
        check("one 'hey Jarvis' sentence is not enough, and says why",
              not few["built"] and "1 of the sentences" in few["why"], few)
        with mock.patch.object(W, "_load", return_value=None):
            nomodel = W.build_verifier(clips)
        check("no wake-word model: not built, and says why", not nomodel["built"]
              and nomodel["why"], nomodel)

        p = W.verifier_path("")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(__import__("json").dumps(doc), encoding="utf-8")
        ver = W.load_verifier("phone")
        check("a mic with no verifier of its own falls back to the general one", ver is not None)
        check("the verifier tells the owner from the others",
              ver.probabilities(np.stack([own(), own()])).min() > 0.9
              and ver.probabilities(np.stack([other(), other()])).max() < 0.1)
        st = W.verifier_status()
        check("status says trained, from how many windows", st["trained"] and st["positives"] == 6, st)

        # spot(): first model interested (>= 0.1) on step 1 only.
        def steps_for(win_at_1, base=0.3):
            return (np.asarray([0.0, base, 0.05], np.float32), [other(), win_at_1, own()])
        with mock.patch.object(W, "_clip_steps", lambda m, c, r: steps_for(own())):
            s = W.spot(np.zeros(100, np.float32))
        check("the owner at a weak first score (0.3 < 0.5) is heard, through the verifier",
              s.heard and s.verified and s.verifier_score > 0.9 and s.score == 0.3, s)
        with mock.patch.object(W, "_clip_steps", lambda m, c, r: steps_for(other(), base=0.95)):
            s = W.spot(np.zeros(100, np.float32))
        check("another voice at a strong first score (0.95) is turned away",
              not s.heard and s.verified and s.verifier_score < 0.1, s)
        with mock.patch.object(W, "_clip_steps", lambda m, c, r: (
                np.asarray([0.05, 0.02], np.float32), [own(), own()])):
            s = W.spot(np.zeros(100, np.float32))
        check("below the 0.1 gate the verifier is not asked (openWakeWord's rule)",
              not s.heard and not s.verified, s)

        p.write_text("{not json", encoding="utf-8")
        with mock.patch.object(W, "_clip_steps", lambda m, c, r: steps_for(other(), base=0.95)):
            s = W.spot(np.zeros(100, np.float32))
        check("an unreadable verifier: the first model decides alone, as before",
              s.heard and not s.verified, s)
        check("...and status says to train again", not W.verifier_status()["trained"]
              and "train" in W.verifier_status()["why"], W.verifier_status())
        p.write_text(__import__("json").dumps({**doc, "w": doc["w"][:10]}), encoding="utf-8")
        check("weights of the wrong size are refused", W.load_verifier() is None)
        p.unlink()
        check("no verifier file: the first model decides alone", W.load_verifier() is None)
        check("status carries the verifier for the phone and desktop",
              S.status()["wake"]["verifier"]["trained"] is False)


def t_enrolment_builds_and_replaces_the_verifier():
    import json
    import jarvis_voice_enroll as E
    good = {"built": True, "clips": 3, "positives": 6, "bank": 5,
            "doc": {"version": 1, "w": [0.0] * 1536, "b": 0.0, "positives": 6}}
    with Env():
        p = W.verifier_path("")
        with mock.patch.object(W, "build_verifier", return_value=good):
            line = E._wake_verifier([b"\x00\x01" * 1600] * 3)
        check("an approved training saves the verifier beside the voice print",
              p.is_file() and json.loads(p.read_text())["positives"] == 6
              and p.parent == V.PROFILE_PATH.parent and "built from 3" in line, line)
        with mock.patch.object(W, "build_verifier",
                               return_value={"built": False, "why": "no hey Jarvis heard"}):
            line = E._wake_verifier([b"\x00\x01" * 1600] * 3)
        check("a new voice print with no verifier deletes the OLD one (it was the old voice's)",
              not p.exists() and "no hey Jarvis heard" in line, line)
        with mock.patch.object(W, "build_verifier", side_effect=RuntimeError("boom")):
            line = E._wake_verifier([b"\x00\x01" * 1600] * 3)
        check("a crash in building it is named, not raised", "RuntimeError" in line, line)


def t_real_models():
    root = os.environ.get("JARVIS_TEST_VOICE_MODELS")
    if not root:
        skip("real models", "set JARVIS_TEST_VOICE_MODELS to a folder with wakeword/ "
             "stt/ tts/ vad/ to run these")
        return
    root = Path(root)
    cfg = {"wake_model_dir": str(root / "wakeword"), "sherpa_stt_dir": str(root / "stt"),
           "tts_model": str(root / "tts" / "model.onnx"),
           "tts_voices": str(root / "tts" / "voices.bin"),
           "tts_tokens": str(root / "tts" / "tokens.txt"),
           "tts_data_dir": str(root / "tts" / "espeak-ng-data"),
           "vad_model": str(root / "vad" / "silero_vad.onnx"), "stt_engine": "sherpa-onnx"}
    real_s, real_w = S._cfg, W._cfg

    def fake(real):
        return lambda k, d=None: cfg[k] if k in cfg else real(k, d)

    import contextlib

    @contextlib.contextmanager
    def kokoro_voice(sid):
        # Two things read which Kokoro voice speaks: jarvis_speech's own
        # `_cfg("tts_speaker_id")` (mocked below, as before) AND - since
        # the built-in-voice-choice setting (2026-09-27) - jarvis_voices.
        # speaker(), which S.tts_speaker() now prefers when jarvis_voices
        # is importable (as it always is on a real PC). Patching only
        # `_cfg` would leave every `say()` here speaking in whatever voice
        # the owner (or nobody) chose, not the `sid` this loop means to
        # exercise - so both are patched, together.
        with mock.patch.object(S, "_cfg", lambda k, d=None, sid=sid:
                               sid if k == "tts_speaker_id" else fake(real_s)(k, d)), \
             mock.patch.object(VC, "speaker", lambda sid=sid: sid), \
             mock.patch.object(VC, "face_voice", lambda: None, create=True):
            # ...and "Voice follows the face" (2026-09-27) is held off: with
            # an animal face showing on the owner's PC, its voice would
            # otherwise win over `sid`.
            yield
    with mock.patch.object(S, "_cfg", fake(real_s)), mock.patch.object(W, "_cfg", fake(real_w)):
        S.reload_engines()
        st = S.status()
        check("status: speech-to-text, voice, VAD and spotter all ready",
              st["stt"]["available"] and st["tts"]["available"] and st["vad"]["available"]
              and st["wake"]["spotter"]["available"], (st["stt"], st["tts"], st["vad"], st["wake"]))
        hits, misses = [], []
        for sid in (0, 9):
            for text, want in (("Hey Jarvis, what time is it?", True),
                               ("Hey Jarvis, turn off the lights.", True),
                               ("Let's move the meeting to Thursday afternoon.", False),
                               ("Hey Jason, are you coming to dinner tonight?", False)):
                with kokoro_voice(sid):
                    wav = S.say(text)
                x, sr = S._read_wav(wav)
                s = W.spot(x, sr)
                (hits if s.heard == want else misses).append((sid, text, s.score))
                if want and sid == 0:
                    heard = S._transcribe(x, sr)
                    found, rest = W.split_wake(heard)
                    check(f"speech-to-text hears {text!r}", found and rest,
                          f"heard {heard!r}")
                if want and sid == 9:
                    x48 = np.interp(np.arange(int(len(x) * 2)) / 2.0, np.arange(len(x)), x)
                    s48 = W.spot(x48.astype(np.float32), sr * 2)
                    check(f"...and at 48 kHz too ({text!r})", s48.heard, s48)
        check("the spotter: every 'hey Jarvis' heard, no ordinary sentence",
              not misses, misses)
        noise = (np.random.default_rng(1).normal(0, 0.01, 32000)).astype(np.float32)
        check("the VAD finds no speech in noise", S._speech_span(noise, 16000) is None)

        # The owner's verifier, end to end: "Train my voice" sentences from
        # one voice (Kokoro 9), then "hey Jarvis" from it and from two others.
        # None of Kokoro's voices is in the bank (that is Piper's).
        def said(text, sid):
            with kokoro_voice(sid):
                return S._read_wav(S.say(text))
        training = ("Hey Jarvis, what's on my calendar today?",
                    "The quick brown fox jumps over the lazy dog.",
                    "Hey Jarvis, turn the lights down a little.",
                    "Please remind me to call my sister on Thursday.",
                    "Hey Jarvis, play some quiet music.",
                    "What is the weather going to be like this weekend?",
                    "Hey Jarvis, set a timer for ten minutes.",
                    "Six thick thistle sticks stood by the gate.")
        clips = [W.to_16k(*said(t, 9)) for t in training]
        out = W.build_verifier(clips)
        check("a verifier is built from the four 'hey Jarvis' sentences",
              out["built"] and out["clips"] >= 3 and out["bank"] > 100,
              {k: v for k, v in out.items() if k != "doc"})
        if out.get("built"):
            with Env():
                p = W.verifier_path("")
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(__import__("json").dumps(out["doc"]), encoding="utf-8")
                own = W.spot(*said("Hey Jarvis, what time is it?", 9))
                others = [W.spot(*said("Hey Jarvis, what time is it?", sid)) for sid in (0, 5)]
            check(f"...which lets its owner through ({own.verifier_score:.2f})",
                  own.heard and own.verified, own)
            check("...and turns two other voices away "
                  f"({[round(o.verifier_score, 2) for o in others]}, their first scores "
                  f"{[round(o.score, 2) for o in others]})",
                  not any(o.heard for o in others), others)
    S.reload_engines()


if __name__ == "__main__":
    for fn in (t_streaming_does_not_depend_on_chunk_size, t_the_transcript_check,
               t_order_wake_switched_off_runs_nothing, t_order_no_phrase_no_owner_check,
               t_order_not_the_owner_is_never_transcribed,
               t_order_the_owner_is_heard_and_the_phrase_removed, t_follow_up_window,
               t_the_follow_up_window_is_per_device, t_one_hey_jarvis_heard_by_two_devices,
               t_two_devices_at_once,
               t_after_a_question,
               t_no_spotter_is_said_not_crashed, t_push_to_talk_is_unchanged,
               t_the_switch_is_one_card, t_the_spotter_module_writes_and_logs_nothing,
               t_48k_is_filtered_not_folded, t_the_verifier,
               t_enrolment_builds_and_replaces_the_verifier, t_real_models):
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
