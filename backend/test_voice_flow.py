"""Interrupting Jarvis by talking, the delay in numbers, and "One moment."
(jarvis_voice_flow.py, voice-flow.patch - the owner's three decisions of
2026-09-24).

    python3 test_voice_flow.py

No pytest, no network, no microphone, no model files. The speaker model is
a stand-in that returns chosen vectors; the voice print, the barge-in
decision, the timing rows, the clip cache and the route blocks are the REAL
code. What it proves:

  1. A barge-in clip is NEVER transcribed: speech-to-text (and the voice
     check that counts towards the owner's repeat rate) is booby-trapped for
     every case below, through barge_in() and through hear().
  2. It stops for the owner's voice, and does NOT stop for a stranger, for
     Jarvis's own custom voice coming back through the speakers (even one
     close enough to the owner to pass the print), for too little speech,
     in broad mode, or with the switch off. "stop" said by anyone stops it,
     except right after Jarvis itself said the word.
  3. The route (voice-flow.patch, rehearsed on the whole patch stack):
     `source=barge_in` answers barge_in()'s dict and never reaches hear(),
     even with an older jarvis_speech.py; `waited_ms` reaches hear().
  4. The timings: a spoken turn makes one row - owner check, speech-to-text,
     Smart Turn, the chat's first word and first sentence (through the real
     run_local_turn), the first sound (through the real say()) - with NO
     words in it; a refused clip makes none.
  5. "One moment.": made once per voice and handed out from memory, made
     again when the voice changes, never starting the better voice's
     program, off with its switch; the GET route block answers a WAV.
  6. The warm-up: runs each engine on sound made here, only once, not at
     all with its switch off or with nothing installed.
"""
import array
import io
import json
import math
import shutil
import sys
import tempfile
import traceback
import wave
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

sys.path.insert(0, str(HERE / "rebuilt"))
sys.path.insert(0, str(HERE))
require_shipped("jarvis_voice_flow.py", "jarvis_speech.py", "jarvis_voices.py",
                "jarvis_agent.py", "jarvis_turn.py", "rebuilt/jarvis_voice.py")
import jarvis_voice as V  # noqa: E402
import jarvis_speech as S  # noqa: E402
import jarvis_voice_flow as F  # noqa: E402
import jarvis_voices as VS  # noqa: E402
import jarvis_agent as AG  # noqa: E402
import jarvis_turn as T  # noqa: E402
import _ollama_wire as OW  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


# ---------------------------------------------------------------- helpers --

def unit(v):
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v]


OWNER = unit([1.0, 0.2, 0.0, 0.0, 0.1, 0.0, 0.0, 0.0])
STRANGER = unit([0.0, 0.0, 1.0, 0.0, 0.0, 0.3, 0.0, 0.0])
#: Jarvis's custom voice: close enough to the owner to pass the print
#: (cosine 0.70 against a bar of 0.35) - the case the comparison is for.
JARVIS = unit([0.75, 0.2, 0.0, 0.62, 0.1, 0.0, 0.0, 0.0])
AMP = {"owner": 0.8, "jarvis": 0.55, "stranger": 0.3}
MODEL = "sherpa-onnx:357a834f702b"          # the small model: bar 0.35 at balanced


def _tag(audio):
    x = V._pcm(audio)
    if not x:
        return None
    peak = max(abs(v) for v in x[:4000])
    return "owner" if peak > 0.7 else ("jarvis" if peak > 0.45 else "stranger")


class Table(V.Embedder):
    """A speaker model that returns the vector chosen for each voice (the
    clip's loudness says whose it is - see AMP)."""
    semantic = True

    def __init__(self, table=None):
        self.name = MODEL
        self.table = table or {"owner": OWNER, "stranger": STRANGER, "jarvis": JARVIS}

    def embed(self, audio):
        key = audio if isinstance(audio, str) else _tag(audio)
        return list(self.table.get(key, []))


def tone(seconds, amp, rate=16000, freq=200.0):
    return [amp * math.sin(2 * math.pi * freq * i / rate) for i in range(int(seconds * rate))]


def wav(seconds, who="owner", rate=16000) -> bytes:
    s = array.array("h", [int(v * 32767) for v in tone(seconds, AMP[who], rate)])
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(s.tobytes())
    return b.getvalue()


class Trap:
    """Every way a clip could become words, booby-trapped and counted."""

    def __init__(self):
        self.calls = []

    def hit(self, name):
        def f(*a, **k):
            self.calls.append(name)
            raise AssertionError(f"{name} was called")
        return f

    def patches(self):
        out = [mock.patch.object(S, "_transcribe", self.hit("speech-to-text")),
               mock.patch.object(S, "_stt_engine", self.hit("the speech-to-text engine")),
               mock.patch.object(V, "verify", self.hit("verify (counted as a command)"))]
        if S.sherpa_onnx is not None:
            out.append(mock.patch.object(S.sherpa_onnx, "OfflineRecognizer",
                                         self.hit("sherpa-onnx's recogniser")))
        return out


class World:
    """A temporary folder for the voice print and the custom voices; the
    owner's print trained; no VAD (the whole clip is the speech)."""

    def __init__(self, cfg=None, custom=False):
        self.cfg, self.custom = dict(cfg or {}), custom

    def __enter__(self):
        self.dir = Path(tempfile.mkdtemp(prefix="jarvis-flow-"))
        self.keep = V.PROFILE_PATH
        V.PROFILE_PATH = self.dir / "voice" / "owner.json"
        V.PROFILE_PATH.parent.mkdir(parents=True)
        V._reset_repeat_for_tests()
        F._reset_for_tests()
        emb = Table({"a": OWNER, "b": OWNER, "c": OWNER})
        V.enroll(["a", "b", "c"], embedder=emb)
        cfg = self.cfg

        def fcfg(k, d=None):
            return cfg.get(k, d)
        vcfg_orig = V._cfg

        def vcfg(k, d=None):
            return cfg[k] if k in cfg else vcfg_orig(k, d)
        self.p = [mock.patch.object(S, "_speech_span", return_value="skip"),
                  mock.patch.object(F, "_cfg", fcfg),
                  mock.patch.object(V, "_cfg", vcfg),
                  mock.patch.object(V, "strong_embedder", lambda *a: None),
                  mock.patch.object(VS, "voices_dir", return_value=self.dir / "voices"),
                  mock.patch.object(F, "_spawn", lambda fn: None)]
        for p in self.p:
            p.start()
        if self.custom:
            self.add_custom_voice()
        return self

    def add_custom_voice(self, vid="butler"):
        d = self.dir / "voices" / vid
        d.mkdir(parents=True)
        x = tone(4.0, AMP["jarvis"], rate=VS.SAMPLE_RATE)
        (d / "clip.wav").write_bytes(VS.wav_bytes(x, VS.SAMPLE_RATE))
        (d / "transcript.txt").write_text("The quick brown fox.\n", encoding="utf-8")
        (d / "voice.json").write_text(json.dumps({"id": vid, "name": "Butler", "seconds": 4.0,
                                                  "created": 1790000000.0}), encoding="utf-8")
        VS._write_state(active=vid)

    def __exit__(self, *a):
        for p in reversed(self.p):
            p.stop()
        V.PROFILE_PATH = self.keep
        V._reset_repeat_for_tests()
        F._reset_for_tests()
        shutil.rmtree(self.dir, ignore_errors=True)


def barge(raw, trap=None, **kw):
    trap = trap or Trap()
    ps = trap.patches()
    for p in ps:
        p.start()
    try:
        return F.barge_in(raw, embedder=Table(), strong=False, **kw), trap
    finally:
        for p in reversed(ps):
            p.stop()


# ------------------------------------------------ 1 + 2. the barge-in rule --

def t_it_stops_for_the_owner_only():
    with World():
        r, trap = barge(wav(1.5, "owner"))
        check("the owner's voice: stop", r["stop"] is True and r["why"] == "owner_voice", r)
        check("...with nothing transcribed and no command counted", trap.calls == []
              and V.repeat_counts()["balanced"]["accepted"] == 0, (trap.calls, V.repeat_counts()))
        r, trap = barge(wav(1.5, "stranger"))
        check("someone else (the TV, a visitor): no stop", r["stop"] is False
              and r["why"] == "not_owner" and trap.calls == [], r)
        r, _ = barge(wav(0.6, "owner"))
        check("too little speech to tell whose voice: no stop", r["stop"] is False
              and r["why"] == "too_short", r)
        r, _ = barge(b"not a wav")
        check("not a WAV: no stop", r["stop"] is False and r["why"] == "unreadable", r)
        check("the answer carries no words, only these fields",
              set(r) == {"stop", "available", "source", "why", "reason", "seconds", "ms"}, r)


def t_it_does_not_stop_for_jarvis_own_voice():
    with World(custom=True):
        r, trap = barge(wav(1.5, "jarvis"))
        check("Jarvis's custom voice through the speakers: no stop, although it passes the "
              "owner's print", r["stop"] is False and r["why"] == "jarvis_voice"
              and trap.calls == [], r)
        verdict, _v, _m = V.judge(V._pcm(S._read_wav(wav(1.5, "jarvis"))[0]), Table(),
                                  strictness=V.BALANCED, strong=False)
        check("(it really does pass the print on its own)", verdict.is_owner, verdict)
        r, _ = barge(wav(1.5, "owner"))
        check("the owner still stops it with that voice active", r["stop"] is True, r)
    with World():
        r, _ = barge(wav(1.5, "jarvis"))
        check("the same clip with no custom voice active DOES stop (so the comparison is "
              "what said no)", r["stop"] is True, r)
    with World():
        # The "One moment." clip is Jarvis's voice too, once it is made.
        with mock.patch.object(S, "_synthesise", lambda text, **k: (
                tone(1.5, AMP["jarvis"]), 16000, "kokoro", "builtin", "", "", "")):
            F.moment()
        r, _ = barge(wav(1.5, "jarvis"))
        check("the cached \"One moment.\" clip counts as Jarvis's voice", r["stop"] is False
              and r["why"] == "jarvis_voice", r)


def t_the_word_stop_and_its_echo_guard():
    class Spot:
        ran, heard, score = True, True, 0.9
    with World(), mock.patch.object(S.jarvis_wakeword, "spot_stop", lambda *a, **k: Spot()):
        with S._SAYS_LOCK:
            S._RECENT_SAYS.clear()
        r, trap = barge(wav(1.2, "stranger"))
        check("\"stop\" said by anyone stops it (as it always has)", r["stop"] is True
              and r["why"] == "stop_word" and trap.calls == [], r)
        S._remember_said("I will stop the timer now.")
        r, _ = barge(wav(1.2, "stranger"))
        check("...but not right after Jarvis said the word itself", r["stop"] is False
              and r["why"] == "stop_ignored", r)
        with S._SAYS_LOCK:
            S._RECENT_SAYS.clear()


def t_switches_and_modes():
    with World({"barge_in_enabled": False}):
        r, trap = barge(wav(1.5, "owner"))
        check("switched off ([voice] barge_in_enabled = false): no stop, not available",
              r["stop"] is False and r["available"] is False and r["why"] == "off"
              and trap.calls == [], r)
        check("status says so", F.barge_state()["enabled"] is False)
    with World({"mode": "broad"}):
        r, _ = barge(wav(1.5, "owner"))
        check("broad mode (any voice accepted) never stops it - the TV would", r["stop"] is False
              and r["available"] is False, r)
        v, vec, _m = V.judge(V._pcm(S._read_wav(wav(1.5, "stranger"))[0]), Table(),
                             strong=False)
        check("...and the voice check itself says no in broad mode (verify() says yes)",
              v.is_owner is False and vec is None and "broad" in v.reason, v)
    with World():
        V.PROFILE_PATH.unlink()
        r, _ = barge(wav(1.5, "owner"))
        check("no voice print yet: no stop, and says to train", r["stop"] is False
              and "Train my voice" in r["reason"], r)
    with World():
        r = F.barge_in(wav(1.5, "owner"), embedder=V.Embedder(), strong=False)
        check("the basic check only (no voice-ID model): no stop, and says why",
              r["stop"] is False and "voice-ID model" in r["reason"], r)


def t_hear_never_transcribes_a_barge_in_clip():
    with World():
        trap = Trap()
        ps = trap.patches() + [mock.patch.object(V, "EcapaEmbedder", Table)]
        for p in ps:
            p.start()
        try:
            h = S.hear(wav(1.5, "owner"), source="barge_in")
            h2 = S.hear(wav(1.5, "stranger"), source="barge_in")
        finally:
            for p in reversed(ps):
                p.stop()
        check("hear(source=barge_in) answers stop and no words", h.stop is True
              and h.text == "" and h.is_owner is False and h.as_dict()["ok"] is False, h)
        check("...and does not stop for someone else", h2.stop is False, h2)
        check("...with no speech-to-text and no command counted", trap.calls == [], trap.calls)


# ------------------------------------------------------------ 3. the route --

def _stand_in():
    import _stack
    text, log = _stack.stand_in("jarvis_hud.py")
    return text, log


def _block(text, start, end):
    a = text.index(start)
    b = text.index(end, a)
    return text[a:b]


def _as_function(block, args, indent):
    body = "\n".join(l[indent:] if l.strip() else "" for l in block.splitlines())
    return f"def handler({args}):\n" + "\n".join("    " + l for l in body.splitlines())


class Handler:
    def __init__(self, path):
        self.path, self.sent = path, []

    def _send(self, code, body, ctype=None):
        self.sent.append((code, body, ctype))
        return code


def t_the_route():
    text, log = _stand_in()
    check("the whole patch stack builds with voice-flow.patch last", text is not None
          and not any("voice-flow" in l for l in log), [l for l in log if "voice-flow" in l])
    if text is None:
        return
    block = _block(text, "            try:\n                # Which microphone (voice-mic.patch)",
                   '                return self._send(500, {"error": type(exc).__name__})')
    block += '                return self._send(500, {"error": type(exc).__name__})\n'
    src = _as_function(block, "self, src, raw, jarvis_speech", 12) + "\n    return ('heard', heard)\n"
    ns = {}
    exec(compile(src, "<utterance block>", "exec"), ns)
    handler = ns["handler"]

    class Speech:
        TAKES_MIC = TAKES_WAIT = True

        def __init__(self):
            self.heard = []

        def hear(self, raw, **kw):
            self.heard.append(kw)
            return "HEARD"

        def barge_in(self, raw, mic=""):
            return {"stop": True, "reason": "your voice", "mic": mic}

    sp, h = Speech(), Handler("/api/voice/utterance?source=barge_in&mic=desktop")
    handler(h, "barge_in", b"RIFF", sp)
    check("source=barge_in answers barge_in()'s dict, with the microphone",
          h.sent == [(200, {"stop": True, "reason": "your voice", "mic": "desktop"}, None)], h.sent)
    check("...and never reaches hear()", sp.heard == [], sp.heard)

    class Older:
        """A jarvis_speech.py from before barge-in: hear() and mic only."""
        TAKES_MIC = True

        def __init__(self):
            self.heard = []

        def hear(self, raw, **kw):
            self.heard.append(kw)
            return "HEARD"
    old = Older()
    h = Handler("/api/voice/utterance?source=barge_in")
    handler(h, "barge_in", b"RIFF", old)
    check("an older jarvis_speech.py: \"do not stop\", and still never hear()",
          h.sent and h.sent[0][1]["stop"] is False and old.heard == [], (h.sent, old.heard))

    sp, h = Speech(), Handler("/api/voice/utterance?source=push_to_talk&mic=phone&waited_ms=640")
    got = handler(h, "push_to_talk", b"RIFF", sp)
    check("push-to-talk still goes to hear(), with mic and waited_ms",
          got == ("heard", "HEARD") and sp.heard == [{"source": "push_to_talk", "mic": "phone",
                                                       "waited_ms": "640"}], sp.heard)

    moment = _block(text, '        if path == "/api/voice/moment":',
                    '        if path in ("/api/memory/pending"')
    src = _as_function(moment, "self, path", 8) + "\n    return None\n"
    g = {"_origin_ok": lambda s: True, "_token_ok": lambda s: True,
         "_no_speech": lambda *a, **k: (503, {}), "_SAY_FALLBACK": ""}
    exec(compile(src, "<moment block>", "exec"), g)

    class Mod:
        @staticmethod
        def moment_reply():
            return 200, b"RIFFwav"
    with mock.patch.dict(sys.modules, {"jarvis_speech": Mod}):
        h = Handler("/api/voice/moment")
        g["handler"](h, "/api/voice/moment")
    check("GET /api/voice/moment answers the WAV as audio/wav",
          h.sent == [(200, b"RIFFwav", "audio/wav")], h.sent)

    class Missing:
        @staticmethod
        def moment_reply():
            return 503, {"available": False, "why": "switched off"}
    with mock.patch.dict(sys.modules, {"jarvis_speech": Missing}):
        h = Handler("/api/voice/moment")
        g["handler"](h, "/api/voice/moment")
    check("...and 503 with the reason when there is none",
          h.sent == [(503, {"available": False, "why": "switched off"}, None)], h.sent)
    g["_token_ok"] = lambda s: False
    h = Handler("/api/voice/moment")
    g["handler"](h, "/api/voice/moment")
    check("...and 401 without the token, like every other route", h.sent[0][0] == 401, h.sent)


# ------------------------------------------------------------ 4. timings --

WORDS = ("what", "time", "tomorrow", "Sure", "quarter", "meeting")


def _spoken_turn(waited="480"):
    """The real hear() (owner check stood in, speech-to-text stood in), the
    real run_local_turn with a scripted model, and the real say()."""
    with mock.patch.object(V, "EcapaEmbedder", Table), \
            mock.patch.object(S, "_stt_engine", return_value=object()), \
            mock.patch.object(S, "_transcribe", return_value="what time is my meeting tomorrow"):
        T.handle(wav(1.0, "owner"))            # Smart Turn, asked by the desktop
        h = S.hear(wav(2.5, "owner"), mic="desktop", waited_ms=waited)
    body = OW.stream([("content", "Sure"), ("content", ", a quarter"), ("content", " past nine."),
                      ("content", " Your meeting is at ten."), ("done", "stop")])
    AG.run_local_turn([{"role": "user", "content": h.text}], "jarvis-primary",
                      ollama_url="http://127.0.0.1:11434", stream_out=lambda b: None,
                      open_stream=lambda url, p: OW.FakeResponse(body), context_length=16384,
                      keepalive_seconds=1000, gate_check=lambda *a: None)
    with mock.patch.object(S, "_synthesise", lambda text, **k: (
            tone(1.0, 0.3), 16000, "kokoro", "builtin", "", "", "")):
        wav1 = S.say("Sure, a quarter past nine.")
        S.say("Your meeting is at ten.")
    return h, wav1


def t_one_row_of_numbers_per_spoken_turn():
    with World():
        with mock.patch.object(T, "predict", lambda x, sr=16000: T.Turn(True, complete=True,
                                                                        ms=37.0)):
            h, wav1 = _spoken_turn()
        rows = F.timings()
        check("the turn was heard, and spoken", h.text and wav1, h)
        check("one row", len(rows) == 1, rows)
        if not rows:
            return
        r = rows[0]
        check("every step has its number", all(isinstance(r[k], (int, float)) for k in (
            "vad_ms", "owner_check_ms", "stt_ms", "heard_ms", "chat_ms", "first_token_ms",
            "first_sentence_ms", "say_start_ms", "say_ms", "first_audio_ms", "total_ms")), r)
        check("the app's own wait and Smart Turn are in it", r["end_wait_ms"] == 480.0
              and r["turn_ms"] == 37.0 and r["mic"] == "desktop", r)
        check("in order: words, then first word, first sentence, first sound",
              r["heard_ms"] <= r["chat_ms"] <= r["first_token_ms"] <= r["first_sentence_ms"]
              <= r["say_start_ms"] <= r["first_audio_ms"], r)
        check("only the FIRST sentence's sound is counted",
              len([x for x in S.say_timings()]) >= 2 and r["say_ms"] is not None, r)
        check("the fields are exactly the documented ones", list(r) == list(F.FIELDS), list(r))
        everything = json.dumps({"rows": rows, "status": S.status()["flow"]})
        check("NO words anywhere: not the question, not the answer",
              not any(w.lower() in everything.lower() for w in WORDS), everything[:600])
        s = {x["step"]: x for x in F.summary()}
        check("the summary has one line per step, with its median",
              s["stt_ms"]["turns"] == 1 and s["total_ms"]["median_ms"] == r["total_ms"], s)


def t_no_row_without_words():
    with World():
        with mock.patch.object(V, "EcapaEmbedder", Table), \
                mock.patch.object(S, "_stt_engine", return_value=object()), \
                mock.patch.object(S, "_transcribe", return_value="hello"):
            S.hear(wav(2.5, "stranger"))
        check("a refused clip (a stranger) makes no row", F.timings() == [])
        with mock.patch.object(S, "_synthesise", lambda text, **k: (
                tone(1.0, 0.3), 16000, "kokoro", "builtin", "", "", "")):
            S.say("Hello.")
        check("a say() with no spoken turn before it marks nothing", F.timings() == [])
        check("waited_ms is a number or nothing", F.clean_wait("640") == 640.0
              and F.clean_wait("-3") is None and F.clean_wait("lots") is None
              and F.clean_wait(True) is None and F.clean_wait("999999") is None)


def t_timing_never_breaks_a_turn():
    with World(), mock.patch.object(F, "note_heard", side_effect=RuntimeError("boom")), \
            mock.patch.object(V, "EcapaEmbedder", Table), \
            mock.patch.object(S, "_stt_engine", return_value=object()), \
            mock.patch.object(S, "_transcribe", return_value="hello there"):
        h = S.hear(wav(2.5, "owner"))
    check("the timing failing does not fail the turn", h.text == "hello there", h)
    vt = {"mark": type("M", (), {"first_token": lambda s: 1 / 0})(), "tail": "", "word": False,
          "sentence": False}
    AG._voice_timing(vt, "Hi.")
    check("...nor the answer", vt["mark"] is None)


# ------------------------------------------------------- 5. "One moment." --

def t_one_moment_is_cached_per_voice():
    made = []

    def synth(text, **kw):
        made.append((text, kw))
        return tone(0.7, 0.4), 16000, "kokoro", "builtin", "", "", ""
    with World(), mock.patch.object(S, "_synthesise", synth):
        brief = {"active": "builtin", "name": "Built-in voice", "engine": "kokoro",
                 "fallback": ""}
        with mock.patch.object(VS, "brief", lambda: dict(brief)):
            a = F.moment()
            b = F.moment()
            code, body = S.moment_reply()
            check("made once, then handed out from memory", len(made) == 1 and a["ok"]
                  and b["wav"] == a["wav"] and code == 200 and body == a["wav"], made)
            check("its words are \"One moment.\", and it never starts the better voice",
                  made[0] == ("One moment.", {"start_better": False}), made)
            st = F.moment_state()
            check("status: ready, with its key", st["ready"] and st["key"] == a["key"]
                  and st["text"] == "One moment.", st)
            brief.update(active="butler", engine="zipvoice", name="Butler")
            st = F.moment_state()
            check("the voice changes: status says it is not ready (a new key)",
                  not st["ready"] and st["key"] != a["key"], st)
            c = F.moment()
            check("...and it is made again, in the new voice", len(made) == 2
                  and c["key"] == st["key"] and c["voice"] == "butler", c)
    with World({"one_moment_enabled": False}), mock.patch.object(S, "_synthesise", synth):
        n = len(made)
        code, body = S.moment_reply()
        check("switched off: 503 with the reason, nothing made", code == 503
              and "one_moment_enabled" in body["why"] and len(made) == n, body)


def t_the_better_voice_is_never_started_for_it():
    calls = []

    class F5:
        state = "off"

        def speak(self, *a):
            calls.append("f5")
            return None, "loading"

        def alive(self):
            return False
    v = VS.Voice(id="butler", name="Butler", transcript="x", seconds=4.0, created=1.0,
                 folder=Path("."))
    with mock.patch.object(VS, "_read_state", lambda: {"active": "butler", "better_voice": True}), \
            mock.patch.object(VS, "load_voice", lambda vid: v), \
            mock.patch.object(VS, "_current_check", lambda v, c=None: {"ok": True}), \
            mock.patch.object(VS, "_F5", F5()), \
            mock.patch.object(VS, "_slow_now", lambda: ""), \
            mock.patch.object(VS, "zipvoice_generate", lambda t, v, s: (tone(0.5, 0.3), 24000, 0.1)):
        got = VS.speak("One moment.", start_better=False)
        check("start_better=False: ZipVoice makes it, the F5 program is not started",
              calls == [] and got.engine == "zipvoice", (calls, got))
        VS.speak("A real sentence.")
        check("a real sentence still starts it, as before", calls == ["f5"], calls)


# ------------------------------------------------------------ 6. warm-up --

def t_warm_up():
    seen = []

    def transcribe(samples, rate):
        seen.append(("stt", float(max(abs(x) for x in samples) if len(samples) else 0.0)))
        return ""
    with World(), mock.patch.object(S, "_stt_engine", return_value=object()), \
            mock.patch.object(S, "_transcribe", transcribe), \
            mock.patch.object(S, "_synthesise", lambda text, **k: (
                tone(0.5, 0.3), 16000, "kokoro", "builtin", "", "", "")), \
            mock.patch.object(V, "EcapaEmbedder", Table):
        st = F.warm(True)
        check("each engine is run once and timed", st["state"] == "ready"
              and {"speech_check", "speech_to_text", "voice", "voice_check"} <= set(st["steps"]),
              st)
        check("speech-to-text was run on silence made here, nothing else",
              seen == [("stt", 0.0)], seen)
        check("the \"One moment.\" clip is made by the warm-up", F.moment_state()["ready"])
    started = []
    with World(), mock.patch.object(F, "_anything_installed", lambda: True):
        F.ensure_warm(spawn=started.append)
        F.ensure_warm(spawn=started.append)
        check("started once, in the background", len(started) == 1, started)
    with World({"warm_engines": False}), mock.patch.object(F, "_anything_installed", lambda: True):
        started.clear()
        F.ensure_warm(spawn=started.append)
        check("[voice] warm_engines = false: not started", started == []
              and F.warm_state()["state"] == "off")
    with World():
        started.clear()
        F.ensure_warm(spawn=started.append)
        check("nothing installed: nothing to warm", started == [])


def t_status_block():
    with World():
        st = S.status()
        flow = st.get("flow") or {}
        check("status() has the flow block", {"barge_in", "moment", "warm", "timings", "summary"}
              <= set(flow), flow)
        check("barge-in is available once a print and a voice-ID model are there",
              F.barge_state(voice={"speaker_model": True})["available"] is True)
    with mock.patch.dict(sys.modules, {"jarvis_voice_flow": None}):
        got = S._flow_status()
        check("without jarvis_voice_flow.py: the same shape, all off",
              got["available"] is False and got["barge_in"]["available"] is False
              and got["timings"] == [], got)
        b = S.barge_in(wav(1.5))
        check("...and barge-in answers \"do not stop\"", b["stop"] is False
              and b["why"] == "not_installed", b)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
