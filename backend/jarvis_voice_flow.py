"""jarvis_voice_flow.py - around one spoken turn: interrupting Jarvis by
talking, how long each step took, and a short "One moment." clip.

NEW MODULE, shipped whole beside jarvis_hud.py (apply-patches.ps1 copies
it). jarvis_speech.py calls it (hear(), say(), status()); jarvis_agent.py
tells it when the model's first word and first sentence arrive;
jarvis_turn.py tells it how long Smart Turn took. `voice-flow.patch` adds
the two route changes. Every call into it is wrapped: without this file
the voice works exactly as before, with these three things missing.

THE OWNER'S THREE DECISIONS (2026-09-24), in plain words:

1. INTERRUPT BY TALKING. While Jarvis speaks, the app may send what its
   microphone hears as `/api/voice/utterance?source=barge_in`. barge_in()
   answers ONE question - "should Jarvis stop talking?" - and nothing else:

       {"stop": bool, "available": bool, "source": "barge_in", "why": <code>,
        "reason": <a sentence>, "seconds": <clip length>, "ms": <time taken>}

   It stops for the OWNER's voice (the voice print, at the balanced bar -
   a stop that should not have happened only cuts a reply short), and for
   the word "stop" said by anyone (the same stop-word model and the same
   30-second echo guard as a wake-word clip). It does NOT stop for the TV
   or other people (the voice print), nor for Jarvis's own voice coming
   back through the speakers: the clip is also compared with Jarvis's
   voices - the active custom voice's recording, the cached "One moment."
   clip, and a sentence of the built-in voice made on this PC - and a clip
   at least as close to one of them as to the owner's print is not the
   owner.

   NEVER TRANSCRIBED. There is no speech-to-text anywhere in this path (the
   tests spy on it), no words in the answer, nothing kept, nothing logged,
   and a yes does nothing on the PC: the app silences its own playback.
   A barge-in clip is not a command. "Hey Jarvis, ..." said over a reply
   stops the reply here and is otherwise dropped; the app sends the same
   clip as `source=wake_word` if it wants the question answered, and that
   path makes every check it always made.

2. THE DELAY, MEASURED AND CUT. For each spoken turn that produced words,
   one row of NUMBERS (never words): the app's own wait for the owner to
   finish (`waited_ms`, when the app sends it), Smart Turn on this PC,
   finding the speech, the owner check, speech-to-text, the chat request
   arriving, the model's first word, the first complete sentence, making
   the first sentence's sound, and the first sound ready. The last 20, in
   memory, in /api/voice/status (`flow.timings` and `flow.summary`).

   The rows are joined by TIME, not by an id the apps send: a chat turn
   that starts within CHAT_WINDOW seconds of a voice turn is taken as its
   answer, and the first say() after that as its first sound. Numbers
   only, so a wrong guess costs a wrong number, nothing more. Only the
   local model's turns are timed (jarvis_agent.run_local_turn).

   What was cut: the engines are loaded and run once in the background
   the first time an app reads /api/voice/status (`warm()`), instead of
   inside the owner's first spoken turn. Measured in this repository's
   container (NOT the owner's PC; backend/README.md, "The voice flow"),
   the first question's words went from 3.3-3.6 s to 0.42-0.59 s, and its
   first sentence of sound from 2.4-3.2 s to 1.3-1.6 s.
   `[voice] warm_engines = false` turns it off.
   What was checked and NOT changed: both apps already ask for each
   sentence's sound as soon as that sentence is complete; the owner check
   still runs before speech-to-text, always (running them side by side
   would transcribe a stranger's words on the way to refusing them).

3. "ONE MOMENT." If no sound has started about a second after the owner
   finished, the apps may play a short clip: "One moment.", in the voice
   Jarvis is speaking in now (custom voices too), made once and kept in
   memory until the voice changes (moment(), GET /api/voice/moment). The
   apps decide when to play it and must never play it over the reply.

SWITCHES, in `[voice]` of jarvis-framework.toml (like `turn_enabled`, read
here, never written by a route; each app keeps its own per-device switch
for whether to use them):

    barge_in_enabled   = true     the PC answers barge_in clips
    one_moment_enabled = true     the PC makes and hands out the clip
    warm_engines       = true     load the voice engines before they are needed

None of the three acts on the world or sends anything anywhere, so none
is an approval card: barge-in only stops Jarvis's own speech, and a switch
turned off here only takes something away.

Standard library plus numpy (already needed for voice). Prints only as a
command-line tool (`py -3 jarvis_voice_flow.py --measure`).
"""
from __future__ import annotations

import hashlib
import io
import json
import threading
import time
import wave
from typing import Callable, Optional

try:
    import jarvis_framework as fw
except Exception:
    fw = None  # type: ignore

try:
    import numpy as np
except Exception:
    np = None  # type: ignore


def _cfg(key: str, default=None):
    """`[voice]` - the section jarvis_speech and jarvis_voice read."""
    if fw is None:
        return default
    try:
        return (fw.load_framework().get("voice") or {}).get(key, default)
    except Exception:
        return default


def _switch(key: str, default: bool = True) -> bool:
    v = _cfg(key, default)
    if isinstance(v, str):
        return v.strip().lower() not in ("false", "0", "no", "off", "")
    return bool(v)


def _spawn(fn: Callable[[], None]) -> None:
    # NOT a daemon thread: the warm-up runs the ONNX engines, and a daemon
    # thread still inside one when Python exits aborts the process
    # ("terminate called without an active exception"). A non-daemon one
    # is waited for instead - a few seconds at most, and only while it runs.
    threading.Thread(target=fn, name="jarvis-voice-flow", daemon=False).start()


def _speech():
    try:
        import jarvis_speech
        return jarvis_speech
    except Exception:
        return None


def _voice():
    try:
        import jarvis_voice
        return jarvis_voice
    except Exception:
        return None


def _voices():
    try:
        import jarvis_voices
        return jarvis_voices
    except Exception:
        return None


def _to16k(samples, rate: int):
    try:
        import jarvis_wakeword
        return jarvis_wakeword.to_16k(samples, rate)
    except Exception:
        pass
    V = _voices()
    if V is not None and hasattr(V, "resample"):
        return V.resample(samples, rate, 16000)
    return samples if int(rate) == 16000 else None


def _wav_samples(wav: bytes):
    """A mono 16-bit WAV (what jarvis_speech writes) -> float32, rate."""
    with wave.open(io.BytesIO(wav), "rb") as w:
        rate, frames = w.getframerate(), w.readframes(w.getnframes())
    return np.frombuffer(frames, dtype="<i2").astype("float32") / 32768.0, rate


# ==========================================================================
#   1. Interrupting Jarvis by talking
# ==========================================================================

SOURCE = "barge_in"
#: Least speech a barge-in clip needs, measured the way hear() measures it -
#: the VAD's span, which keeps 0.3 s of quiet either side, so about 0.4 s of
#: words. Shorter than a command needs (1.5-2 s): a false stop only cuts a
#: reply short.
MIN_SECONDS = 1.0
#: The bar a barge-in clip is held to. Balanced, whatever the owner chose
#: for commands: the only thing a yes can do is stop Jarvis talking.
BAR = "balanced"
#: A sentence of the built-in voice, made once on this PC, to know Jarvis's
#: own voice when it comes back through the speakers. Jarvis's words, never
#: the owner's.
REFERENCE_TEXT = ("Good evening. Here is what I found for you, and there is a little "
                  "more on your screen if you want it.")

_REF_LOCK = threading.Lock()
#: key -> {"label", "x16": samples at 16 kHz, "vecs": {model name: vector}}
_REFS: dict = {}


def _embedder(V):
    """The same choice hear() makes, so the numbers mean the same."""
    try:
        return V.EcapaEmbedder()
    except Exception:
        return V.Embedder()


def barge_state(mic: str = "", voice: Optional[dict] = None, check_model: bool = True) -> dict:
    """{enabled, available, why} - can the PC tell the owner's voice while
    Jarvis talks? Cheap: settings and files, no model run. `voice`:
    jarvis_voice.status(), when the caller already has it (then its
    `speaker_model` says whether a voice-ID model is installed, the same
    answer the talk button uses)."""
    enabled = _switch("barge_in_enabled", True)
    base = {"enabled": enabled, "available": False, "why": "", "min_seconds": MIN_SECONDS,
            "bar": BAR, "stop_word": False}
    S = _speech()
    if S is not None:
        try:
            base["stop_word"] = bool(S._stop_state().get("available"))
        except Exception:
            pass
    if not enabled:
        return {**base, "why": ("switched off on the PC ([voice] barge_in_enabled = false in "
                                "jarvis-framework.toml)")}
    V = _voice()
    if V is None or not hasattr(V, "judge"):
        return {**base, "why": ("the voice check (jarvis_voice.py) is missing on the PC or "
                                "older than interrupting by talking")}
    mode = str(V._cfg("mode", "owner") or "owner").strip().lower()
    if not bool(V._cfg("enabled", True)):
        return {**base, "why": "voice is switched off in the PC's settings ([voice] enabled)"}
    if mode == "broad":
        return {**base, "why": ("the voice check is in broad mode (any voice is accepted), so "
                                "it cannot tell your voice from the TV's")}
    try:
        prof, _label = V.find_profile(mic)
    except Exception:
        prof = None
    if prof is None:
        return {**base, "why": ("Jarvis has not learned your voice yet. Use Train my voice; "
                                "until then only \"stop\" interrupts it")}
    if not check_model:
        model_ok = True             # barge_in() asks the loaded model itself
    elif isinstance(voice, dict) and "speaker_model" in voice:
        model_ok = bool(voice.get("speaker_model"))
    else:
        try:
            # A voice-ID model file (the basic check cannot tell two people
            # apart). speechbrain, the other thing EcapaEmbedder can load,
            # is not looked for here: this answers from files, not loading.
            model_ok = V.speaker_model_path().is_file() or V.strong_model_path().is_file()
        except Exception:
            model_ok = False
    if not model_ok:
        return {**base, "why": V.NO_MODEL_REASON}
    return {**base, "available": True}


def _stop_word(S, samples, rate: int, spoken: float, mic: str):
    """None, or (stop, why, reason) for a clip that is the word "stop" -
    exactly as hear() treats one inside a wake-word clip."""
    W = getattr(S, "jarvis_wakeword", None)
    if W is None or not hasattr(W, "spot_stop") or spoken > S.STOP_MAX_SECONDS:
        return None
    try:
        got = W.spot_stop(samples, rate)
    except Exception:
        return None
    if not (got.ran and got.heard):
        return None
    echo = S._jarvis_said_stop(mic)
    if echo is not None:
        ago, _said = echo
        left = max(1, int(round(S.STOP_ECHO_SECONDS - ago)))
        return (False, "stop_ignored",
                f"that sounded like \"stop\", but Jarvis said the word \"stop\" itself "
                f"{int(ago)} seconds ago and its own voice may have reached the microphone, "
                f"so it was ignored. Say it again in {left} seconds")
    return True, "stop_word", "stop"


def _reference_sources() -> list:
    """[(key, label, loader)] - every voice Jarvis may be speaking in now.
    Each loader returns (samples, rate) or None. Cheap to list; loading
    happens once per key."""
    out = []
    Vs = _voices()
    if Vs is not None:
        try:
            st = Vs._read_state()
            vid = st.get("active")
            if vid and vid != Vs.BUILTIN:
                v = Vs.load_voice(vid)
                if v is not None:
                    def load_custom(v=v):
                        x = Vs._clip_samples(v)
                        return None if x is None else (x, Vs.SAMPLE_RATE)
                    out.append((("custom", v.id, round(v.created, 3)), "your custom voice",
                                load_custom))
        except Exception:
            pass
    with _MOMENT_LOCK:
        m = dict(_MOMENT)
    if m.get("wav"):
        def load_moment(wav=m["wav"]):
            return _wav_samples(wav)
        out.append((("moment", m.get("key")), "the \"One moment.\" clip", load_moment))
    S = _speech()
    if S is not None:
        try:
            paths = S._sherpa_tts_paths()
            size = __import__("os").path.getsize(paths["model"])
        except Exception:
            size = -1
        if size > 0:
            sid = S._cfg("tts_speaker_id", 0) or 0

            def load_builtin(S=S, sid=sid):
                engine = S._tts_engine()
                if engine is None:
                    return None
                audio = engine.generate(REFERENCE_TEXT, sid=int(sid),
                                        speed=float(S._cfg("tts_speed", 1.0) or 1.0))
                if audio is None or len(audio.samples) == 0:
                    return None
                return np.asarray(audio.samples, dtype=np.float32), int(audio.sample_rate)
            out.append((("builtin", str(sid), size), "the built-in voice", load_builtin))
    return out


def _reference_vectors(model, V) -> list:
    """[(label, vector)] for `model`, each voice loaded and embedded once."""
    if model is None or np is None:
        return []
    name = str(getattr(model, "name", ""))
    out = []
    for key, label, load in _reference_sources():
        with _REF_LOCK:
            ref = _REFS.get(key)
        if ref is None:
            try:
                got = load()
            except Exception:
                got = None
            x16 = _to16k(got[0], got[1]) if got is not None else None
            ref = {"label": label, "x16": x16, "vecs": {}}
            with _REF_LOCK:
                # Keys go stale when a voice changes; keep the table small.
                while len(_REFS) >= 8:
                    del _REFS[next(iter(_REFS))]
                _REFS[key] = ref
        if ref["x16"] is None or len(ref["x16"]) < 512:
            continue
        vec = ref["vecs"].get(name)
        if vec is None:
            vec = V.embed_with(model, ref["x16"], 16000)
            ref["vecs"][name] = vec
        if vec:
            out.append((label, vec))
    return out


def barge_in(raw: bytes, mic: str = "", *, embedder=None, strong=None) -> dict:
    """POST /api/voice/utterance?source=barge_in -> the answer above.

    Order: the switch, the WAV, the speech check (VAD), "stop" (anyone),
    enough speech, the owner's print, then Jarvis's own voices. Each step
    can only say "do not stop"; only the last two can say "stop". Never
    transcribes, never raises for bad input."""
    t0 = time.perf_counter()
    secs = {"v": 0.0}

    def done(stop: bool, why: str, reason: str, available: bool = True) -> dict:
        return {"stop": bool(stop), "available": bool(available), "source": SOURCE,
                "why": why, "reason": reason, "seconds": round(secs["v"], 2),
                "ms": round((time.perf_counter() - t0) * 1000.0, 1)}

    if not _switch("barge_in_enabled", True):
        return done(False, "off", barge_state()["why"], available=False)
    S = _speech()
    if S is None or np is None:
        return done(False, "not_installed",
                    "the speech module (jarvis_speech.py) or numpy is missing on the PC",
                    available=False)
    mic = S._norm_mic(mic)
    parsed = S._read_wav(raw)
    if parsed is None:
        return done(False, "unreadable", "could not read that as a 16-bit PCM WAV clip")
    samples, rate = parsed
    secs["v"] = len(samples) / float(rate or 16000)
    span = S._speech_span(samples, rate)
    if span is None:
        return done(False, "no_speech", "no speech in that recording")
    if span != "skip":
        samples = samples[span[0]:span[1]]
    spoken = len(samples) / float(rate or 16000)

    said = _stop_word(S, samples, rate, spoken, mic)
    if said is not None:
        return done(*said)

    state = barge_state(mic, check_model=False)
    if not state["available"]:
        return done(False, "not_ready", state["why"], available=False)
    if spoken < MIN_SECONDS:
        return done(False, "too_short",
                    f"too short to tell whose voice it is ({spoken:.1f} seconds of speech; "
                    f"at least {MIN_SECONDS:.1f} is needed)")
    V = _voice()
    emb = embedder or _embedder(V)
    verdict, vec, model = V.judge(samples, emb, sample_rate=rate, mic=mic,
                                  strictness=V.BALANCED, strong=strong)
    if not verdict.is_owner:
        if vec is None and "clip too short or silent" not in verdict.reason:
            return done(False, "not_ready", verdict.reason, available=False)
        return done(False, "not_owner",
                    f"that did not sound like you ({verdict.reason}), so Jarvis kept talking")
    closest = None
    for label, ref in _reference_vectors(model, V):
        s = float(V.cosine(vec, ref))
        if closest is None or s > closest[0]:
            closest = (s, label)
    if closest is not None and closest[0] >= verdict.score:
        return done(False, "jarvis_voice",
                    f"that sounded at least as much like Jarvis's own voice ({closest[1]}, "
                    f"{closest[0]:.2f}) as like yours ({verdict.score:.2f}), so Jarvis kept "
                    f"talking")
    return done(True, "owner_voice", "your voice")


# ==========================================================================
#   2. The delay, one row of numbers per spoken turn
# ==========================================================================

KEPT = 20
#: A chat turn starting this soon after a voice turn's words is its answer.
CHAT_WINDOW = 20.0
#: The first say() this soon after that answer began is its first sound.
SAY_WINDOW = 120.0
#: Smart Turn asked this soon before a clip arrived counts for that clip.
TURN_WINDOW = 5.0

#: Every field of a row, in order: numbers, booleans or null - no words.
FIELDS = ("at", "mic", "source", "cold", "end_wait_ms", "turn_ms", "vad_ms", "wake_ms",
          "owner_check_ms", "stt_ms", "heard_ms", "chat_ms", "first_token_ms",
          "first_sentence_ms", "say_start_ms", "say_ms", "first_audio_ms", "total_ms")

_T_LOCK = threading.Lock()
_ROWS: list = []                 # [(t0 monotonic, row dict)], newest last
_SMART: dict = {"t": -1e9, "ms": None}


def _ms(v) -> Optional[float]:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return round(v, 1) if v == v and 0 <= v < 3.6e6 else None


def clean_wait(v) -> Optional[float]:
    """The app's `waited_ms`: a number from 0 to 60000, else None."""
    if isinstance(v, bool):
        return None
    got = _ms(v if not isinstance(v, str) else (v.strip() or None))
    return got if got is not None and got <= 60000 else None


def note_smart_turn(ms) -> None:
    """jarvis_turn.handle(): Smart Turn answered this PC's desktop app."""
    with _T_LOCK:
        _SMART["t"], _SMART["ms"] = time.monotonic(), _ms(ms)


def note_heard(t0: float, steps: dict, *, source: str, mic: str, waited_ms=None,
               cold: bool = False) -> None:
    """hear() produced words: one new row. `t0` is time.monotonic() when the
    clip arrived; `steps` holds vad/wake/owner_check/stt in milliseconds."""
    now = time.monotonic()
    with _T_LOCK:
        smart = _SMART["ms"] if 0 <= t0 - _SMART["t"] <= TURN_WINDOW else None
        row = {k: None for k in FIELDS}
        row.update({"at": int(time.time()),
                    "mic": mic if mic in ("phone", "desktop") else "",
                    "source": source if source in ("push_to_talk", "wake_word") else "",
                    "cold": bool(cold), "end_wait_ms": clean_wait(waited_ms),
                    "turn_ms": smart, "heard_ms": _ms((now - t0) * 1000.0)})
        for k in ("vad", "wake", "owner_check", "stt"):
            if k in steps:
                row[k + "_ms"] = _ms(steps[k])
        _ROWS.append((t0, row))
        del _ROWS[:-KEPT]


class _Mark:
    """What the chat turn and say() hold while they run: marks one row."""

    def __init__(self, t0: float, row: dict):
        self._t0, self._row = t0, row

    def _set(self, key: str, value) -> None:
        with _T_LOCK:
            if self._row.get(key) is None:
                self._row[key] = _ms(value)

    def since(self) -> float:
        return (time.monotonic() - self._t0) * 1000.0

    def first_token(self) -> None:
        self._set("first_token_ms", self.since())

    def first_sentence(self) -> None:
        self._set("first_sentence_ms", self.since())

    def audio_ready(self, say_ms: float) -> None:
        with _T_LOCK:
            if self._row.get("first_audio_ms") is not None:
                return
            self._row["say_ms"] = _ms(say_ms)
            self._row["first_audio_ms"] = _ms(self.since())
            w = self._row.get("end_wait_ms")
            if w is not None and self._row["first_audio_ms"] is not None:
                self._row["total_ms"] = round(w + self._row["first_audio_ms"], 1)


def chat_started() -> Optional[_Mark]:
    """jarvis_agent.run_local_turn is starting: the newest voice turn with no
    answer yet, if its words came within CHAT_WINDOW seconds."""
    now = time.monotonic()
    with _T_LOCK:
        for t0, row in reversed(_ROWS):
            if row["chat_ms"] is not None:
                break
            ended = t0 + (row["heard_ms"] or 0) / 1000.0
            if now - ended <= CHAT_WINDOW:
                row["chat_ms"] = _ms((now - t0) * 1000.0)
                return _Mark(t0, row)
            break
    return None


def say_started() -> Optional[_Mark]:
    """say() is starting: the newest voice turn whose answer has begun and
    has no sound yet, within SAY_WINDOW seconds."""
    now = time.monotonic()
    with _T_LOCK:
        for t0, row in reversed(_ROWS):
            if row["chat_ms"] is None or row["say_start_ms"] is not None:
                break
            if now - t0 <= SAY_WINDOW:
                row["say_start_ms"] = _ms((now - t0) * 1000.0)
                return _Mark(t0, row)
            break
    return None


def timings() -> list:
    """Copies of the rows, oldest first."""
    with _T_LOCK:
        return [dict(r) for _t, r in _ROWS]


#: The summary's steps: (name, words for a person, how to get it from a row).
STEPS = (
    ("end_wait_ms", "waiting for you to finish (in the app)", lambda r: r["end_wait_ms"]),
    ("turn_ms", "Smart Turn on this PC", lambda r: r["turn_ms"]),
    ("vad_ms", "finding the speech", lambda r: r["vad_ms"]),
    ("owner_check_ms", "checking it is you", lambda r: r["owner_check_ms"]),
    ("stt_ms", "speech to text", lambda r: r["stt_ms"]),
    ("to_chat_ms", "the app passing the words to the chat",
     lambda r: _diff(r["chat_ms"], r["heard_ms"])),
    ("model_first_word_ms", "the model's first word",
     lambda r: _diff(r["first_token_ms"], r["chat_ms"])),
    ("first_sentence_ms", "the rest of the first sentence",
     lambda r: _diff(r["first_sentence_ms"], r["first_token_ms"])),
    ("say_ms", "making the first sentence's sound", lambda r: r["say_ms"]),
    ("first_audio_ms", "on this PC: from your words arriving to the first sound ready",
     lambda r: r["first_audio_ms"]),
    ("total_ms", "in all: from you finishing to the first sound ready",
     lambda r: r["total_ms"]),
)


def _diff(a, b):
    return round(a - b, 1) if a is not None and b is not None else None


def summary(rows: Optional[list] = None) -> list:
    """[{step, label, turns, median_ms, worst_ms}] over the kept rows - one
    line per step, for a person (the one-line PowerShell in
    docs/JARVIS-API.md section 17 prints it)."""
    rows = timings() if rows is None else rows
    out = []
    for name, label, get in STEPS:
        vals = sorted(v for v in (get(r) for r in rows) if v is not None)
        n = len(vals)
        med = None
        if n:
            med = vals[n // 2] if n % 2 else round((vals[n // 2 - 1] + vals[n // 2]) / 2, 1)
        out.append({"step": name, "label": label, "turns": n, "median_ms": med,
                    "worst_ms": vals[-1] if n else None})
    return out


# ==========================================================================
#   3. "One moment."
# ==========================================================================

MOMENT_TEXT = "One moment."
#: A suggestion only - the apps decide when to play it.
MOMENT_AFTER_MS = 1000

_MOMENT_LOCK = threading.Lock()
_MAKE_LOCK = threading.Lock()          # one clip made at a time
_MOMENT: dict = {"key": "", "wav": None, "seconds": 0.0, "voice": "", "engine": "",
                 "why": "", "busy": False,
                 "failed_key": "", "failed_at": -1e9}


def _brief() -> dict:
    Vs = _voices()
    try:
        return Vs.brief() if Vs is not None else {}
    except Exception:
        return {}


def moment_key() -> tuple:
    """(key, active voice id, engine it would be made with) - the key
    changes whenever the clip would sound different: another voice, another
    engine, another built-in speaker or speed, another model file."""
    b = _brief()
    active = str(b.get("active") or "builtin")
    engine = str(b.get("engine") or "kokoro")
    parts = [MOMENT_TEXT, active, engine]
    Vs = _voices()
    if Vs is not None and active != "builtin":
        try:
            v = Vs.load_voice(active)
            parts.append(round(v.created, 3) if v is not None else "missing")
        except Exception:
            parts.append("unreadable")
    S = _speech()
    if S is not None:
        parts += [str(S._cfg("tts_speaker_id", 0) or 0), str(S._cfg("tts_speed", 1.0) or 1.0)]
        try:
            parts.append(__import__("os").path.getsize(S._sherpa_tts_paths()["model"]))
        except Exception:
            parts.append(-1)
    key = hashlib.sha256(json.dumps(parts).encode("utf-8")).hexdigest()[:12]
    return key, active, engine


def moment() -> dict:
    """The clip for the voice in use now: {"ok", "wav", "key", "voice",
    "engine", "seconds", "why"}. Made on the first ask after the voice
    changed, then handed out from memory. Never raises."""
    if not _switch("one_moment_enabled", True):
        return {"ok": False, "wav": None, "key": "", "voice": "", "engine": "", "seconds": 0.0,
                "why": ("switched off on the PC ([voice] one_moment_enabled = false in "
                        "jarvis-framework.toml)")}
    key, active, _engine = moment_key()
    with _MOMENT_LOCK:
        if _MOMENT["key"] == key and _MOMENT["wav"]:
            return {"ok": True, **{k: _MOMENT[k] for k in ("wav", "key", "voice", "engine",
                                                          "seconds", "why")}}
    with _MAKE_LOCK:
        with _MOMENT_LOCK:
            if _MOMENT["key"] == key and _MOMENT["wav"]:
                return {"ok": True, **{k: _MOMENT[k] for k in ("wav", "key", "voice",
                                                              "engine", "seconds", "why")}}
            _MOMENT["busy"] = True
        wav, engine, why, seconds = None, "", "", 0.0
        S = _speech()
        try:
            if S is None or not hasattr(S, "_synthesise"):
                why = "the speech module (jarvis_speech.py) is missing or older than this"
            else:
                got = S._synthesise(MOMENT_TEXT, start_better=False)
                samples, rate, engine = got[0], got[1], got[2]
                if samples is None:
                    why = got[6] or "nothing can speak on this PC yet"
                else:
                    wav = S._write_wav(samples, rate)
                    seconds = round(len(samples) / float(rate), 2)
        except Exception as exc:
            why = f"it could not be made ({type(exc).__name__})"
        with _MOMENT_LOCK:
            _MOMENT.update(busy=False, why=why)
            if wav:
                _MOMENT.update(key=key, wav=wav, seconds=seconds, voice=active, engine=engine,
                               failed_key="")
            else:
                _MOMENT.update(failed_key=key, failed_at=time.monotonic())
            out = {"ok": bool(wav), "wav": wav, "key": key if wav else "", "voice": active,
                   "engine": engine, "seconds": seconds, "why": why}
    return out


def moment_state(spawn: Optional[Callable] = None) -> dict:
    """For status(): the clip for the voice in use now, and whether it is
    ready. When it is not (the voice changed), it is made in the background
    so it is ready before the app asks."""
    on = _switch("one_moment_enabled", True)
    key, active, engine = moment_key() if on else ("", "", "")
    can = on and _anything_installed()
    with _MOMENT_LOCK:
        ready = on and _MOMENT["key"] == key and bool(_MOMENT["wav"])
        busy = _MOMENT["busy"]
        seconds = _MOMENT["seconds"] if ready else None
        why = "" if ready else _MOMENT["why"]
        # A clip that could not be made is not tried again for the same
        # voice for a minute: status() is read often.
        tried = (_MOMENT["failed_key"] == key
                 and time.monotonic() - _MOMENT["failed_at"] < 60.0)
        if can and not ready and not busy and not tried:
            _MOMENT["busy"] = True
            kick = True
        else:
            kick = False
    if kick:
        def work():
            try:
                moment()
            finally:
                with _MOMENT_LOCK:
                    _MOMENT["busy"] = False
        try:
            (spawn or _spawn)(work)
        except Exception:
            with _MOMENT_LOCK:
                _MOMENT["busy"] = False
    if not on:
        why = ("switched off on the PC ([voice] one_moment_enabled = false in "
               "jarvis-framework.toml)")
    return {"enabled": on, "text": MOMENT_TEXT, "key": key, "ready": ready, "voice": active,
            "engine": engine, "seconds": seconds, "after_ms": MOMENT_AFTER_MS, "why": why}


# ==========================================================================
#   Keeping the engines warm
# ==========================================================================

_WARM_LOCK = threading.Lock()
_WARM: dict = {"asked": False, "state": "waiting", "seconds": None, "steps": {}}


def _silence(seconds: float = 0.5):
    return np.zeros(int(16000 * seconds), dtype=np.float32)


def _noise(seconds: float = 1.0):
    rng = np.random.default_rng(0)
    return (0.01 * rng.standard_normal(int(16000 * seconds))).astype(np.float32)


def warm(wait: bool = True, spawn: Optional[Callable] = None) -> dict:
    """Loads every voice engine this PC has and runs each once, on sound
    made here (silence and faint noise - nobody's voice), so the owner's
    first spoken turn does not pay for it. Each step is timed; nothing is
    kept but the engines. `wait=False` runs it in the background."""
    if not wait:
        (spawn or _spawn)(lambda: warm(True))
        return warm_state()
    t_all = time.perf_counter()
    steps: dict = {}
    with _WARM_LOCK:
        _WARM.update(asked=True, state="warming")

    def step(name: str, fn: Callable[[], object]) -> None:
        """Times one engine. None: it is not installed here (fn returned
        False) or it failed - either way there was nothing to warm."""
        t = time.perf_counter()
        try:
            ran = fn()
        except Exception:
            ran = False
        steps[name] = None if ran is False else round((time.perf_counter() - t) * 1000.0, 1)

    S, V = _speech(), _voice()
    if S is not None and np is not None:
        step("speech_check", lambda: S._vad_config() is not None
             and S._speech_span(_noise(), 16000) is not False)
        # Speech-to-text on half a second of SILENCE made here: it loads the
        # model and runs it once. No clip from anyone is involved.
        step("speech_to_text", lambda: S._stt_engine() is not None
             and S._transcribe(_silence(), 16000) is not None)
        W = getattr(S, "jarvis_wakeword", None)
        if S._wake_enabled() and W is not None:
            step("wake_word", lambda: bool(W.spot(_silence(1.0), 16000).ran))
            if hasattr(W, "spot_stop"):
                step("stop_word", lambda: bool(W.spot_stop(_silence(1.0), 16000).ran))
        # The voice Jarvis speaks in now: making the "One moment." clip
        # loads it (or one word, when the clip is switched off).
        if _switch("one_moment_enabled", True):
            step("voice", lambda: bool(moment().get("ok")))
        else:
            step("voice", lambda: S._synthesise("Ready.", start_better=False)[0] is not None)
    if V is not None and np is not None:
        models = {}

        def voice_check():
            emb = _embedder(V)
            if not getattr(emb, "semantic", False):
                return False
            V.embed_with(emb, _noise(), 16000)
            models["small"] = emb
            strong = V.strong_embedder(emb) if hasattr(V, "strong_embedder") else None
            if strong is not None:
                V.embed_with(strong, _noise(), 16000)
                models["strong"] = strong
            return True
        step("voice_check", voice_check)
        if models and barge_state()["available"]:
            # Jarvis's own voices, for barge-in (made and embedded once).
            step("jarvis_voice", lambda: bool(
                [_reference_vectors(m, V) for m in models.values()]))
    if S is not None and bool(S._cfg("turn_enabled", True)):
        def smart_turn():
            import jarvis_turn
            return bool(jarvis_turn.predict(_silence(1.0), 16000).ran)
        step("smart_turn", smart_turn)
    with _WARM_LOCK:
        _WARM.update(state="ready", steps=steps,
                     seconds=round(time.perf_counter() - t_all, 2))
    return warm_state()


def _anything_installed() -> bool:
    """Whether any voice engine's model file is on this PC - with none,
    there is nothing to warm (and a test's stand-in folder stays quiet)."""
    S, V = _speech(), _voice()
    try:
        if S is not None:
            paths = S._sherpa_tts_paths()
            if S._files_present(paths["model"], paths["voices"], paths["tokens"]):
                return True
            if S._files_present(*S._stt_files()[1].values()):
                return True
            if __import__("os").path.isfile(S._vad_path()):
                return True
        if V is not None and V.speaker_model_path().is_file():
            return True
    except Exception:
        return False
    return False


def ensure_warm(spawn: Optional[Callable] = None) -> None:
    """Starts warm() in the background once (again after reset_warm())."""
    if not _switch("warm_engines", True) or np is None or not _anything_installed():
        return
    with _WARM_LOCK:
        if _WARM["asked"]:
            return
        _WARM.update(asked=True, state="warming")
    try:
        (spawn or _spawn)(lambda: warm(True))
    except Exception:
        with _WARM_LOCK:
            _WARM.update(asked=False, state="waiting")


def reset_warm() -> None:
    """jarvis_speech.reload_engines() dropped the engines: warm again."""
    with _WARM_LOCK:
        _WARM.update(asked=False, state="waiting", seconds=None, steps={})
    with _REF_LOCK:
        _REFS.clear()
    with _MOMENT_LOCK:
        if not _MOMENT["busy"]:
            _MOMENT.update(key="", wav=None, seconds=0.0, voice="", engine="", why="")


def warm_state() -> dict:
    on = _switch("warm_engines", True)
    with _WARM_LOCK:
        return {"enabled": on, "state": _WARM["state"] if on else "off",
                "seconds": _WARM["seconds"], "steps": dict(_WARM["steps"])}


# ==========================================================================
#   status() and tests
# ==========================================================================

def status(spawn: Optional[Callable] = None, voice: Optional[dict] = None) -> dict:
    """/api/voice/status's `flow` block. Answers at once; the first call
    starts the warm-up and, when needed, the "One moment." clip - both in
    the background (`spawn`). `voice`: jarvis_voice.status(), if the caller
    has it already."""
    ensure_warm(spawn)
    return {"available": True,
            "barge_in": barge_state(voice=voice),
            "moment": moment_state(spawn),
            "warm": warm_state(),
            "timings": timings(),
            "summary": summary()}


def _reset_for_tests() -> None:
    with _T_LOCK:
        _ROWS.clear()
        _SMART.update(t=-1e9, ms=None)
    with _MOMENT_LOCK:
        _MOMENT["busy"] = False
    reset_warm()


def _measure() -> int:
    """`py -3 jarvis_voice_flow.py --measure`, in the backend folder: loads
    each voice engine and times it, twice - the first pass is what the
    owner's first spoken turn used to wait for, the second what a warm one
    waits. Silence and faint noise only; nothing is recorded."""
    first = warm(True)
    with _MOMENT_LOCK:                   # so the voice is timed again, not the cache
        _MOMENT.update(key="", wav=None)
    second = warm(True)
    print("How long each voice engine takes on this PC (milliseconds)")
    print(f"  {'step':<16} {'first (loading)':>16} {'again (warm)':>14}")
    for name in first["steps"]:
        a, b = first["steps"].get(name), second["steps"].get(name)
        fa = "n/a" if a is None else f"{a:.0f}"
        fb = "n/a" if b is None else f"{b:.0f}"
        print(f"  {name:<16} {fa:>16} {fb:>14}")
    print(f"  {'in all':<16} {first['seconds'] * 1000:>16.0f} {second['seconds'] * 1000:>14.0f}")
    print("n/a: not installed on this PC, or switched off. jarvis_voice (Jarvis's own voices, for\n"
          "interrupting by talking) is made once and kept, so its second number is near 0.")
    return 0


if __name__ == "__main__":
    import sys
    if "--measure" in sys.argv:
        raise SystemExit(_measure())
    print(json.dumps({k: v for k, v in status(spawn=lambda fn: None).items()}, indent=1))
