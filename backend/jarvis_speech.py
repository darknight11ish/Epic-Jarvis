"""jarvis_speech.py - hear it, verify it's the owner, say it back.

NEW MODULE, not a patch. `jarvis_speech.py` does not exist anywhere handed
over (docs/ARCHITECTURE.md §10 says so plainly), so there is nothing here to
patch against - this ships as a whole file, the way `jarvis_research.py` did.

It exists to make real the interface `jarvis_hud.py`'s four `/api/voice/*`
routes already expect (see `backend/voice-503.patch` and
`backend/test_voice_503.py`, both written before this file existed, against a
missing module):

    jarvis_speech.status()                 -> dict
    jarvis_speech.hear(raw, source=...)    -> Heard  (raw = one complete WAV)
    jarvis_speech.hear(raw, source=..., mic="phone"|"desktop")   since 2026-09-24:
        which microphone, so the clip is checked against that microphone's
        own voice print (voice-mic.patch passes `?mic=`; TAKES_MIC says so)
    jarvis_speech.say(text)                -> bytes | None  (a WAV)
        since 2026-09-28 a Kokoro WAV may end with a "jmth" chunk after its
        sound: the animals' mouth shapes from Kokoro's own timing
        (jarvis_mouth.py, docs/LIPSYNC.md) - on Kokoro v1.0 as well since
        2026-09-29; status()'s tts.mouth says if they can be made on this
        PC, or why not
        since 2026-09-24 in the owner's chosen custom voice when there is one
        (jarvis_voices.py: ZipVoice on the processor, or F5-TTS on the second
        card), falling back to Kokoro with the reason recorded; every call's
        timing is kept in memory (say_timings(), status()'s tts.timings)
    jarvis_speech.set_wake_enabled(bool)   -> {"ok": bool, ...}
    jarvis_speech.barge_in(raw, mic=...)   -> {"stop": bool, "reason", ...}
        since 2026-09-24 (voice-flow.patch, ?source=barge_in): while Jarvis
        talks, "is that the owner's voice (or the word stop)? then stop" -
        NEVER transcribed; jarvis_voice_flow.py decides
    jarvis_speech.moment_reply()           -> (200, WAV) | (503, dict)
        the "One moment." clip in the voice in use now (GET /api/voice/moment)
    hear(..., waited_ms=...)               TAKES_WAIT: the app's own wait for the
        owner to finish, kept only as a number in status()'s flow.timings

ORDER MATTERS, and this is the one invariant that must never move: `hear()`
verifies the SPEAKER through `jarvis_voice` before it ever runs speech-to-
text. "A voice that is not the owner's is never turned into words - refusing
after transcribing would leave a stranger's speech in memory on the way to
saying no" (the same comment already lives beside the route that calls this).
The safe failure is to say nothing back, not to say something quietly wrong.

The whole order, since 2026-09-23 (each step can only refuse, never add):

    0. source=barge_in (2026-09-24): Jarvis is talking; barge_in() answers
       "stop or not" and NOTHING below runs - no speech-to-text, ever
       source=talk_to_type (2026-09-28): with the owner's talk-to-type
       switch off, refused here and NOTHING below runs; with it on, every
       step below runs as for the talk button, and the words come back
       cleaned of "um"/"uh" and are never noted for chat history
    1. read the WAV                      bad file        -> refused
    2. Silero VAD: is there speech?      only noise      -> refused, nothing else runs
    3. wake word (source=wake_word only): is it switched on, and is
       "hey Jarvis" in the clip?         no              -> refused, not checked, not transcribed
       (once "Train my voice" has built it, the owner's own verifier
       has the last word here - jarvis_wakeword.py, "THE OWNER'S OWN")
       3a, since 2026-09-28 ("Better voice"), only with the owner's
       `wake_confirm = "both"`: a second, differently-built detector
       (microWakeWord, jarvis_microwake.py) must hear it too, within a
       second -> else refused, not checked, not transcribed. It can only
       say no. Not installed: the first decides alone, and status() says so.
       Just before it, since 2026-09-24: a SHORT clip that is the stop
       word ("stop", "Jarvis, stop") answers `stop: true` and nothing
       else - the desktop silences Jarvis's reply. Stopping speech is
       harmless, so it needs no voice check; it is never transcribed, never
       sent to the chat, and does nothing but stop the speaking.
       3b, since 2026-09-24 (the stricter check): less speech than a
       command needs (jarvis_voice.MIN_COMMAND_SECONDS: 2 s very strict,
       1.5 s balanced) -> refused, not checked, not transcribed: "say a
       little more". A short wake-word clip that is only "hey Jarvis"
       still goes on (it opens the listening window, step 6); a short one
       with a command in it is refused after step 5, its words dropped.
    4. the owner check (jarvis_voice)    not the owner   -> refused, not transcribed
    5. speech-to-text
    6. wake word only: does the transcript START with "hey Jarvis"? The
       spotter heard something like it; this is the second opinion that
       stops "the computer in that film was called Jarvis" counting.
    7. wake word only, since 2026-09-27: the same words heard by the
       owner's OTHER device (a passing clip from another microphone,
       within SAME_WAKE_SECONDS) and already acted on there -> refused
       with `other_device`, no words kept. And the listening window step
       6 opens belongs to the microphone that opened it.

JARVIS LIVE, since 2026-09-28 (jarvis_live.py, docs/LIVE-DESIGN.md): a
conversation the owner starts and stops. A clip sent with `source=live`
needs no "hey Jarvis" - and that is the ONLY difference. Before step 1 it
is refused, never looked at, unless a Live session is on for THAT
microphone and not paused (a card waiting, or too many other voices);
then every step above runs in the same order: speech found, long enough
(3b - "say a bit more", the short line at most once a minute), THE OWNER
CHECK, and only then speech-to-text. Its words may end Live ("that's all
for now") or extend it ("20 more minutes") - jarvis_live.phrase(), only
after the owner check. "Hey Jarvis, let's talk" (or the talk button's
"let's talk") starts Live on the device that heard it, also only after the
owner check. While Live is on one device, the OTHER device's "hey Jarvis"
clips are dropped before the spotter (`other_device`, "Live is on your
phone"). The owner's answer of 2026-09-28: under "only trust the talk
button" a Live clip is trusted like the talk button unless the voice
setting `hands_free_live` says otherwise (jarvis_voice.hands_free_trusted).

Engines: sherpa-onnx for speech-to-text, Kokoro speech and Silero VAD, per
docs/ARCHITECTURE.md §11; the owner check is `jarvis_voice.py`; the wake word
is `jarvis_wakeword.py` (openWakeWord's "hey jarvis" model on ONNX Runtime -
that module says why that one). Nothing here uses the graphics card.

SPEECH-TO-TEXT: sherpa-onnx, and nothing else. The shipped TOML used to say
`stt_engine = "faster-whisper"` / `stt_model = "small.en"` - an engine no code
in this project has ever spoken. That line was the reason push-to-talk could
never be transcribed. The default is now "sherpa-onnx"; a config still
naming faster-whisper gets a status note that says which line to change
(backend/README.md's install step changes it for you). The model on disk is
recognised by its files, so the install is "put the files in the folder":

    voice-models/stt/encoder*.onnx + decoder*.onnx + joiner*.onnx + tokens.txt
        -> NeMo Parakeet TDT 0.6B v2 (the recommended one: English, with
           punctuation, ~0.1x real time on a 4-core CPU here)
    voice-models/stt/model*.onnx + tokens.txt
        -> SenseVoice (smaller, multilingual)
    `sherpa_stt_kind` under [voice] overrides the guess.

THE WAKE-WORD SWITCH IS AN APPROVAL CARD, since 2026-09-23. Turning it ON
widens where Jarvis listens - `change_own_config`, tier "ask" - so
`set_wake_enabled(True)` raises one card through `jarvis_gate.check()` on a
background thread, exactly the way jarvis_voice_enroll.py raises its "replace
my voice" card, and changes nothing itself. The tier is checked before the
card and again on the answer; only tier "ask" with outcome "approved" turns it
on. Turning it OFF is immediate and never waits for a card: it only narrows
what Jarvis hears, and an off switch that could time out would leave a
microphone open. Before this, the docstring here said it applied at once
"because jarvis_gate.py's interface was not visible" - the interface
jarvis_voice_enroll.py and jarvis_skill_discovery.py already call is the one
used here.

WHAT IS NOT HERE: model files. They are tens to hundreds of megabytes of
ONNX that belong on the owner's machine, not in git. backend/README.md's
"Voice: install the models" section has one PowerShell line per model, each
checked against a SHA-256 measured from the real download. Every engine is
built lazily on first use; a missing or corrupt file is an honest "not
available" in status(), never a crash.
"""
from __future__ import annotations

import io
import json
import os
import re
import threading
import time
import uuid
import wave
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable, Optional

try:
    import jarvis_framework as fw
except Exception:
    fw = None  # type: ignore

try:
    import jarvis_voice
except Exception:
    jarvis_voice = None  # type: ignore

try:
    import jarvis_wakeword
except Exception:
    jarvis_wakeword = None  # type: ignore

try:
    import jarvis_microwake
except Exception:
    jarvis_microwake = None  # type: ignore

try:
    import numpy as np
except Exception:
    np = None  # type: ignore

try:
    import sherpa_onnx
except Exception:
    sherpa_onnx = None  # type: ignore

try:
    import jarvis_live
except Exception:
    jarvis_live = None  # type: ignore


def _left_s(p: dict) -> float:
    """Seconds left of a waiting card's time, by the MONOTONIC clock: a clock
    that is set or synced while a card waits must not shorten or stretch it
    (time audit, 2026-09-30). `since` (wall clock) stays for display; a record
    made before this change has no `since_m` and falls back to it."""
    m = p.get("since_m")
    if isinstance(m, (int, float)) and not isinstance(m, bool):
        return p["timeout"] - (time.monotonic() - m)
    return p["since"] + p["timeout"] - time.time()


def _cfg(key: str, default=None):
    """Read `[voice]`. Same section jarvis_voice reads - its own docstring
    says the two modules "must not disagree about where it lives"."""
    if fw is None:
        return default
    try:
        return fw.load_framework().get("voice", {}).get(key, default)
    except Exception:
        return default


def _config_dir() -> Path:
    if fw is not None:
        return Path(fw.CONFIG_DIR)
    return Path(os.environ.get("OPENJARVIS_CONFIG_DIR")
                or os.environ.get("JARVIS_CONFIG_DIR")
                or (Path.home() / ".openjarvis"))


def _models_dir() -> Path:
    return _config_dir() / "voice-models"


def _wake_state_path() -> Path:
    return _config_dir() / "voice" / "wake_override.json"


#: Processor threads for speech-to-text and the voice when the owner has not
#: set `stt_threads` / `tts_threads`. 4 on a PC with cores to spare (the
#: owner's 12-core Ryzen is mostly idle while the graphics card thinks), 2 on
#: a small one. Measured 2026-09-28 (research audit, section 1.5), 2 -> 4
#: threads: a short spoken phrase 1.13 s -> 0.86 s, a 97-character sentence
#: 2.51 s -> 1.80 s, speech-to-text on a 4 s clip 0.45 s -> 0.36 s. The wake
#: word and the voice check keep one thread each (they run all the time).
DEFAULT_THREADS = max(2, min(4, (os.cpu_count() or 4) // 3))


def _threads(key: str) -> int:
    try:
        return max(1, min(8, int(_cfg(key, DEFAULT_THREADS))))
    except (TypeError, ValueError):
        return DEFAULT_THREADS


# --------------------------------------------------------------------------
#   Audio: WAV bytes in, WAV bytes out. No numpy dependency of our own - if
#   sherpa_onnx imported, numpy did too, since sherpa_onnx requires it.
# --------------------------------------------------------------------------

def _read_wav(raw: bytes):
    """One complete WAV utterance -> (float32 samples in -1..1, sample_rate).

    Returns None on anything that is not a readable 16-bit PCM WAV, rather
    than raising - `hear()` turns that into an honest Heard(False, ...)
    instead of a 500, matching "every path that is not a clean pass returns
    is_owner=False" from jarvis_voice.
    """
    if np is None:
        return None
    try:
        with wave.open(io.BytesIO(raw), "rb") as w:
            sr = w.getframerate()
            width = w.getsampwidth()
            channels = max(1, w.getnchannels())
            frames = w.readframes(w.getnframes())
    except Exception:
        return None
    if width != 2 or not frames:
        # 16-bit PCM only, matching jarvis_voice._pcm's own assumption - a
        # float/8-bit/24-bit WAV is rare from a real capture path and wrong
        # is a safer answer than a silently mis-scaled one.
        return None
    samples = np.frombuffer(frames, dtype="<i2").astype("float32") / 32768.0
    if channels > 1:
        usable = (len(samples) // channels) * channels
        samples = samples[:usable].reshape(-1, channels).mean(axis=1)
    return samples, sr


def _write_wav(samples, sample_rate: int) -> bytes:
    """float32 samples in -1..1 -> a mono 16-bit PCM WAV, in memory."""
    pcm = np.clip(samples, -1.0, 1.0)
    pcm = (pcm * 32767.0).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(sample_rate))
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


# --------------------------------------------------------------------------
#   Speech-to-text: sherpa-onnx. Lazy, cached, never crashes the caller on a
#   missing or corrupt model.
# --------------------------------------------------------------------------

_UNSET = object()
_LOCK = threading.RLock()
_stt_cache = _UNSET
_tts_cache = _UNSET
_vad_cache = _UNSET

#: What the code speaks. The TOML's old "faster-whisper" is recognised only
#: to say what to change.
STT_ENGINE = "sherpa-onnx"
STT_KINDS = ("nemo_transducer", "transducer", "sense_voice")


def _stt_engine_name() -> str:
    return str(_cfg("stt_engine", STT_ENGINE) or STT_ENGINE).strip()


def _stt_dir() -> Path:
    return Path(str(_cfg("sherpa_stt_dir", "") or (_models_dir() / "stt")))


def _first(d: Path, *names: str) -> str:
    """The first of `names` that exists in `d`, else the first name - so a
    status message can still say what it looked for."""
    for n in names:
        if (d / n).is_file():
            return str(d / n)
    return str(d / names[0])


def _glob1(d: Path, pattern: str, fallback: str) -> str:
    """The one file matching `pattern` in `d` (int8 preferred), else fallback.
    Model folders name their files by training run
    (encoder-epoch-99-avg-1.int8.onnx), so an exact name cannot be assumed."""
    try:
        hits = sorted(d.glob(pattern), key=lambda p: (".int8." not in p.name, p.name))
    except OSError:
        hits = []
    return str(hits[0]) if hits else str(d / fallback)


def _stt_files() -> tuple:
    """(kind, {role: path}). The kind is recognised from what is on disk
    unless `sherpa_stt_kind` names one."""
    d = _stt_dir()
    kind = str(_cfg("sherpa_stt_kind", "") or "").strip().lower().replace("-", "_")
    trans = {"encoder": _glob1(d, "encoder*.onnx", "encoder.int8.onnx"),
             "decoder": _glob1(d, "decoder*.onnx", "decoder.int8.onnx"),
             "joiner": _glob1(d, "joiner*.onnx", "joiner.int8.onnx"),
             "tokens": str(d / "tokens.txt")}
    sense = {"model": str(_cfg("sherpa_stt_model", "") or
                          _first(d, "model.int8.onnx", "model.onnx")),
             "tokens": str(_cfg("sherpa_stt_tokens", "") or d / "tokens.txt")}
    if kind not in STT_KINDS:
        kind = "nemo_transducer" if _files_present(*trans.values()) else "sense_voice"
    return kind, (sense if kind == "sense_voice" else trans)


def _sherpa_stt_paths():
    """(model, tokens) - kept for anything that read the old name. For a
    transducer the "model" is its encoder."""
    kind, files = _stt_files()
    return files.get("model") or files.get("encoder"), files["tokens"]


def _build_stt_engine():
    if sherpa_onnx is None or _stt_engine_name() != STT_ENGINE:
        return None
    kind, f = _stt_files()
    try:
        if kind == "sense_voice":
            return sherpa_onnx.OfflineRecognizer.from_sense_voice(
                model=f["model"], tokens=f["tokens"],
                num_threads=_threads("stt_threads"),
                use_itn=bool(_cfg("sherpa_stt_use_itn", True)),
                language=str(_cfg("sherpa_stt_language", "") or ""),
            )
        return sherpa_onnx.OfflineRecognizer.from_transducer(
            encoder=f["encoder"], decoder=f["decoder"], joiner=f["joiner"],
            tokens=f["tokens"], num_threads=_threads("stt_threads"),
            model_type="nemo_transducer" if kind == "nemo_transducer" else "",
        )
    except Exception:
        # A missing file, a corrupt ONNX graph, a tokens file that does not
        # parse - all the same answer: no STT right now, told honestly by
        # status()/hear() rather than raised into the request.
        return None


def _stt_engine():
    global _stt_cache
    with _LOCK:
        if _stt_cache is _UNSET:
            _stt_cache = _build_stt_engine()
        return _stt_cache


def _transcribe(samples, sample_rate: int) -> str:
    engine = _stt_engine()
    if engine is None:
        return ""
    stream = engine.create_stream()
    stream.accept_waveform(sample_rate, samples)
    engine.decode_stream(stream)
    return (stream.result.text or "").strip()


# --------------------------------------------------------------------------
#   Silero VAD: is there any speech in the clip, and where.
# --------------------------------------------------------------------------

#: The two Silero VAD files Jarvis knows, by the `vad_version` line under
#: [voice] ("Better voice", 2026-09-28).
#:
#:   v4  silero_vad.onnx - what the install line has always downloaded (the
#:       sherpa-onnx "asr-models" release). Its own metadata says "silero-vad
#:       v4 exported to onnx by k2-fsa". The default.
#:   v6  silero_vad_v6.onnx - upstream's silero_vad.onnx at tag v6.2.3
#:       (github.com/snakers4/silero-vad, MIT), the model changed in v6.2.
#:       Its inputs are (input, state, sr), the v5 layout, which sherpa-onnx
#:       1.13.8 detects by itself (silero-vad-model.cc: three inputs and two
#:       outputs -> is_v5_, which requires window_size 512 - what
#:       _build_vad_config already sends).
#:
#: v6 is used only when `vad_version = "v6"` is set AND the file is exactly
#: the pinned one: sherpa-onnx ends the whole process (SHERPA_ONNX_EXIT) on
#: a VAD file whose layout it does not know, so a wrong file must never
#: reach it. Otherwise v4 is used, as before, and status() says why. Which
#: one to keep is measured on the PC first (jarvis_bakeoff.py --vad); the
#: default stays v4 until then. An explicit `vad_model` path still wins
#: over both, unchecked, as it always has.
VAD_FILES = {
    "v4": {"file": "silero_vad.onnx",
           "sha256": "9e2449e1087496d8d4caba907f23e0bd3f78d91fa552479bb9c23ac09cbb1fd6"},
    "v6": {"file": "silero_vad_v6.onnx",
           "sha256": "1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3"},
}
DEFAULT_VAD_VERSION = "v4"
_VAD_HASH: dict = {}


def _file_sha256(p: Path) -> str:
    """SHA-256 of a small file, cached by (path, size, modified time)."""
    try:
        st = p.stat()
    except OSError:
        return ""
    key = (str(p), st.st_size, st.st_mtime_ns)
    got = _VAD_HASH.get(key)
    if got is None:
        import hashlib
        try:
            got = hashlib.sha256(p.read_bytes()).hexdigest()
        except OSError:
            return ""
        for old in [k for k in _VAD_HASH if k[0] == key[0]]:
            del _VAD_HASH[old]
        _VAD_HASH[key] = got
    return got


def vad_choice() -> dict:
    """Which speech detector file is used, and why. {"chosen": "v4"|"v6",
    "in_use": "v4"|"v6"|"configured", "path", "note"}. `note` is "" unless
    the choice could not be honoured."""
    raw = str(_cfg("vad_version", DEFAULT_VAD_VERSION) or DEFAULT_VAD_VERSION).strip().lower()
    chosen = raw if raw in VAD_FILES else DEFAULT_VAD_VERSION
    note = "" if raw == chosen else (f"vad_version = {raw[:12]!r} is not one Jarvis knows "
                                     f"(\"v4\" or \"v6\"), so v4 is used")
    configured = str(_cfg("vad_model", "") or "").strip()
    if configured:
        return {"chosen": chosen, "in_use": "configured", "path": configured,
                "note": "vad_model is set, so that file is used"}
    d = _models_dir() / "vad"
    v4 = str(d / VAD_FILES["v4"]["file"])
    if chosen == "v6":
        p = d / VAD_FILES["v6"]["file"]
        if not p.is_file():
            return {"chosen": chosen, "in_use": "v4", "path": v4,
                    "note": (f"the newer speech detector (v6) is chosen but not installed "
                             f"(looked for {p}), so v4 is used")}
        if _file_sha256(p) != VAD_FILES["v6"]["sha256"]:
            return {"chosen": chosen, "in_use": "v4", "path": v4,
                    "note": (f"{p.name} is not the expected file (its SHA-256 is "
                             f"different), so it is not used and v4 is - download it "
                             f"again with the line in backend/README.md")}
        return {"chosen": chosen, "in_use": "v6", "path": str(p), "note": ""}
    return {"chosen": chosen, "in_use": "v4", "path": v4, "note": note}


def _vad_path() -> str:
    return vad_choice()["path"]


def _vad_wanted() -> bool:
    return bool(_cfg("vad_enabled", True))


def vad_config_for(path: str):
    """A sherpa-onnx VAD config for the Silero file at `path` - Jarvis's own
    settings - or None when it cannot be built. The bake-off builds one per
    file to compare them on the same clips."""
    if sherpa_onnx is None or not Path(path).is_file():
        return None
    try:
        cfg = sherpa_onnx.VadModelConfig(
            silero_vad=sherpa_onnx.SileroVadModelConfig(
                model=str(path), threshold=0.5, min_silence_duration=0.25,
                min_speech_duration=0.1, window_size=512),
            sample_rate=16000, num_threads=1)
        # Built once here so a broken file shows up now, not mid-request.
        sherpa_onnx.VoiceActivityDetector(cfg, buffer_size_in_seconds=1)
        return cfg
    except Exception:
        return None


def _build_vad_config():
    if not _vad_wanted():
        return None
    return vad_config_for(_vad_path())


def _vad_config():
    global _vad_cache
    with _LOCK:
        if _vad_cache is _UNSET:
            _vad_cache = _build_vad_config()
        return _vad_cache


#: Kept either side of the speech the VAD found, so a soft first consonant
#: or a trailing "s" is not cut off.
VAD_PAD_SECONDS = 0.3


def _speech_span(samples, sample_rate: int, cfg=_UNSET):
    """(start, end) in samples of `samples` holding speech, None when the
    VAD found none, or "skip" when there is no VAD to ask. `cfg`: another
    VAD config (vad_config_for) - the bake-off's; hear() uses Jarvis's own."""
    if cfg is _UNSET:
        cfg = _vad_config()
    if cfg is None or jarvis_wakeword is None:
        return "skip"
    x = jarvis_wakeword.to_16k(samples, sample_rate)
    try:
        vad = sherpa_onnx.VoiceActivityDetector(
            cfg, buffer_size_in_seconds=max(2.0, len(x) / 16000 + 1))
        for i in range(0, len(x) - 511, 512):
            vad.accept_waveform(x[i:i + 512])
        vad.flush()
        first = last = None
        while not vad.empty():
            seg = vad.front
            s, e = seg.start, seg.start + len(seg.samples)
            first = s if first is None else min(first, s)
            last = e if last is None else max(last, e)
            vad.pop()
    except Exception:
        return "skip"
    if first is None:
        return None
    scale = sample_rate / 16000.0
    pad = int(VAD_PAD_SECONDS * 16000)
    start = int(max(0, first - pad) * scale)
    end = int(min(len(x), last + pad) * scale)
    return start, min(end, len(samples))


# --------------------------------------------------------------------------
#   Text-to-speech: sherpa-onnx Kokoro.
# --------------------------------------------------------------------------

def _default_voices(default_dir) -> str:
    """The voices file to load when `[voice] tts_voices` names none: the
    pinned blend file (Ashby and Clara, jarvis_kokoro.BLEND_FILE) when it sits
    beside the pack's own voices.bin and is exactly the file it should be, else
    voices.bin itself. Never raises."""
    plain = default_dir / "voices.bin"
    try:
        import jarvis_kokoro
        blend = jarvis_kokoro.blend_file_beside(plain)
        if jarvis_kokoro.kind_of_file(plain) == jarvis_kokoro.V1 \
                and jarvis_kokoro.blend_ok(blend):
            return blend
    except Exception:
        pass
    return str(plain)


def _sherpa_tts_paths():
    default_dir = _models_dir() / "tts"
    return {
        "model": str(_cfg("tts_model", "") or default_dir / "model.onnx"),
        "voices": str(_cfg("tts_voices", "") or _default_voices(default_dir)),
        "tokens": str(_cfg("tts_tokens", "") or default_dir / "tokens.txt"),
        "data_dir": str(_cfg("tts_data_dir", "") or default_dir / "espeak-ng-data"),
        "lexicon": str(_cfg("tts_lexicon", "") or ""),
        "dict_dir": str(_cfg("tts_dict_dir", "") or ""),
    }


def _build_tts_engine():
    if sherpa_onnx is None or str(_cfg("tts_engine", "sherpa-onnx")) != "sherpa-onnx":
        return None
    paths = _sherpa_tts_paths()
    try:
        kokoro = sherpa_onnx.OfflineTtsKokoroModelConfig(
            model=paths["model"],
            voices=paths["voices"],
            tokens=paths["tokens"],
            lexicon=paths["lexicon"],
            data_dir=paths["data_dir"],
            dict_dir=paths["dict_dir"],
            lang=str(_cfg("tts_lang", "en-us") or "en-us"),
        )
        model_cfg = sherpa_onnx.OfflineTtsModelConfig(
            kokoro=kokoro, num_threads=_threads("tts_threads"))
        config = sherpa_onnx.OfflineTtsConfig(model=model_cfg)
        engine = sherpa_onnx.OfflineTts(config)
    except Exception:
        return None
    # Which voices file this engine was built with: jarvis_voices reads it, so
    # a blend file made later is not believed until an engine has loaded it.
    global _TTS_VOICES
    _TTS_VOICES = paths["voices"]
    # How much sherpa-onnx shortens Kokoro's pauses (its own setting, read
    # from the config it was built with): the mouth timing shortens them
    # the same way itself (jarvis_mouth.speak).
    global _TTS_SILENCE_SCALE
    try:
        _TTS_SILENCE_SCALE = float(config.silence_scale)
    except Exception:
        _TTS_SILENCE_SCALE = 0.2
    _mouth("warm", paths)
    return engine


#: sherpa-onnx's silence_scale for the built engine (0.2 is its default).
_TTS_SILENCE_SCALE = 0.2

#: The voices file the built engine loaded ("" until one is built).
_TTS_VOICES = ""


def _mouth(name: str, *args, **kwargs):
    """jarvis_mouth.<name>(...), or None when that file is missing or the
    call fails - the mouth shapes are an extra, never a reason to fail."""
    try:
        import jarvis_mouth
        return getattr(jarvis_mouth, name)(*args, **kwargs)
    except Exception:
        return None


def _tts_engine():
    global _tts_cache
    with _LOCK:
        if _tts_cache is _UNSET:
            _tts_cache = _build_tts_engine()
        return _tts_cache


def reload_engines() -> None:
    """Drop the cached STT/TTS/VAD engines (and the wake-word models) so a
    config change - a new model path - takes effect on the next call rather
    than needing a restart."""
    global _stt_cache, _tts_cache, _vad_cache, _TTS_VOICES
    with _LOCK:
        _stt_cache = _tts_cache = _vad_cache = _UNSET
        _TTS_VOICES = ""
    if jarvis_wakeword is not None:
        jarvis_wakeword.reload()
    if jarvis_microwake is not None:
        jarvis_microwake.reload()
    try:
        import jarvis_turn
        jarvis_turn.reload()
    except Exception:
        pass
    # The warm-up and the "One moment." clip were made with the old ones.
    _flow("reset_warm")


# --------------------------------------------------------------------------
#   The wake-word switch.
#
#   Its value lives in its own small state file, not the framework TOML (no
#   route may write that). ON goes through ONE approval card; OFF is at once.
# --------------------------------------------------------------------------

#: The gate action - the one the TOML's own [voice] comment names for
#: "widening where Jarvis listens".
WAKE_ACTION = "change_own_config"

_WAKE_LOCK = threading.Lock()
_WAKE_PENDING: Optional[dict] = None      # {"id", "since", "timeout", "withdrawn"}
_WAKE_LAST: Optional[dict] = None         # how the last card ended
#: Every card switched off while it waited and not yet answered, by its id.
#: A SET, not a flag on _WAKE_PENDING: a new ON replaces _WAKE_PENDING, and
#: the flag went with it - after two ON/OFF rounds, approving the FIRST card
#: turned the wake word on although the owner's last word was OFF.
_WAKE_WITHDRAWN: set = set()


def _wake_enabled() -> bool:
    p = _wake_state_path()
    if p.is_file():
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and isinstance(raw.get("enabled"), bool):
                return raw["enabled"]
        except Exception:
            pass
    return bool(_cfg("wake_word_enabled", False))


def _write_wake(enabled: bool) -> Optional[str]:
    """Writes the switch. None on success, else the error in words."""
    p = _wake_state_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"enabled": bool(enabled), "set_at": time.time()}),
                     encoding="utf-8")
    except OSError as exc:
        return f"{type(exc).__name__}: {exc}"
    return None


def describe_wake_on() -> str:
    """The card. Every word from here; what refusing costs is on it."""
    return (
        "Turn on \"hey Jarvis\"?\n\n"
        "If you say yes: the PC will accept recordings that start with \"hey "
        "Jarvis\". The desktop app and the phone each still need their own "
        "listening switched on before anything listens - that stays off until "
        "you turn it on there, and the phone shows a notification the whole "
        "time it listens.\n\n"
        "The wake word is heard on the device itself. No sound is sent "
        "anywhere until it hears \"hey Jarvis\", and then only to this PC, "
        "where your voice is checked before any words are written down.\n\n"
        "If you did not just ask for this, say no.\n\n"
        "If you say no: nothing changes. Push-to-talk keeps working."
    )


def _wake_tier(action: str) -> str:
    return str(fw.action_tier(action)) if fw is not None else "unknown"


def _wake_gate(action: str, detail: dict, prompt: str):
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def _wake_timeout() -> float:
    try:
        return float(fw.load_framework().get("autonomy", {})
                     .get("approval_timeout_seconds", 180))
    except Exception:
        return 180.0


def _audit(event: str, detail: dict) -> None:
    try:
        if fw is not None:
            fw.audit_log(event, detail)
    except Exception:
        pass


def _spawn(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="jarvis-wake-card", daemon=True).start()


def _wake_finish(pid: str, outcome: str, **extra) -> dict:
    global _WAKE_PENDING, _WAKE_LAST
    with _WAKE_LOCK:
        if _WAKE_PENDING is not None and _WAKE_PENDING["id"] == pid:
            _WAKE_PENDING = None
        _WAKE_WITHDRAWN.discard(pid)
        _WAKE_LAST = {"outcome": outcome, "at": time.time(),
                      **{k: v for k, v in extra.items() if k in ("reason",)}}
        last = dict(_WAKE_LAST)
    _audit("voice.wake_word.decided", {"outcome": outcome,
                                       **{k: v for k, v in extra.items()
                                          if k == "request_id"}})
    return last


def _wake_decide(pid: str, gate: Callable) -> dict:
    """Raise the card, wait for the answer, act on it. Blocks - runs on its
    own thread. Only tier "ask" + outcome "approved" turns the wake word on."""
    text = describe_wake_on()
    detail = {"text": text, "what": "turn on the \"hey Jarvis\" wake word",
              "setting": "[voice] wake_word_enabled", "to": True}
    try:
        v = gate(WAKE_ACTION, detail, text)
    except Exception as exc:
        return _wake_finish(pid, "refused",
                            reason=f"the approval gate failed ({type(exc).__name__})")
    vtier = getattr(v, "tier", "unknown")
    allowed = getattr(v, "allowed", False) is True
    outcome = getattr(v, "outcome", None)
    if outcome is None:
        # A gate from before gate-outcome.patch: only allowed-on-ask can be
        # read as a person saying yes.
        outcome = "approved" if (allowed and vtier == "ask") else "refused"
    rid = getattr(v, "request_id", None)
    if vtier != "ask":
        return _wake_finish(pid, "refused", request_id=rid,
                            reason=f"the gate answered at tier {vtier!r}, which is "
                                   f"not a person saying yes")
    if not (allowed and outcome == "approved"):
        if outcome in ("denied", "timed_out"):
            return _wake_finish(pid, outcome, request_id=rid)
        return _wake_finish(pid, "refused", request_id=rid,
                            reason=str(getattr(v, "reason", "refused"))[:200])
    with _WAKE_LOCK:
        withdrawn = pid in _WAKE_WITHDRAWN
    if withdrawn:
        # Switched off again while the card waited: the later "off" wins, so
        # approving a stale card cannot turn the microphone back on.
        return _wake_finish(pid, "withdrawn", request_id=rid,
                            reason="you turned it off while the card was waiting")
    err = _write_wake(True)
    if err:
        return _wake_finish(pid, "failed", request_id=rid, reason=err[:200])
    return _wake_finish(pid, "enabled", request_id=rid)


def set_wake_enabled(enabled: bool, *, gate: Optional[Callable] = None,
                     tier_of: Optional[Callable[[str], str]] = None,
                     spawn: Optional[Callable] = None) -> dict:
    """POST /api/voice/wake. OFF: at once. ON: raises one approval card and
    returns straight away - `pending: true` means a card is up, NOT that the
    wake word is on. Re-read status() for that.

    `ok` keeps its old meaning for the route: true when the request was
    accepted (applied, or a card raised), false when it was refused.
    """
    global _WAKE_PENDING
    gate = gate or _wake_gate
    tier_of = tier_of or _wake_tier
    spawn = spawn or _spawn

    if not enabled:
        with _WAKE_LOCK:
            if _WAKE_PENDING is not None:
                _WAKE_PENDING["withdrawn"] = True
                _WAKE_WITHDRAWN.add(_WAKE_PENDING["id"])
        err = _write_wake(False)
        _close_awake()
        if err:
            return {"ok": False, "enabled": _wake_enabled(), "pending": False,
                    "error": err}
        _audit("voice.wake_word.off", {})
        return {"ok": True, "enabled": False, "pending": False, "applied": True,
                "message": "The wake word is off. Nothing listens for it now."}

    if _wake_enabled():
        return {"ok": True, "enabled": True, "pending": False, "applied": True,
                "message": "The wake word is already on."}

    with _WAKE_LOCK:
        if _WAKE_PENDING is not None and not _WAKE_PENDING.get("withdrawn"):
            left = max(0, int(_left_s(_WAKE_PENDING)))
            return {"ok": False, "enabled": False, "pending": True, "expires_in": left,
                    "error": ("a card to turn on the wake word is already waiting - "
                              "approve or deny that one")}

    try:
        tier = tier_of(WAKE_ACTION)
    except Exception as exc:
        tier = f"unreadable ({type(exc).__name__})"
    if tier != "ask":
        # Checked BEFORE a card is raised: a card that could not end in a
        # person deciding should not be raised at all.
        return {"ok": False, "enabled": False, "pending": False,
                "error": (f"{WAKE_ACTION} is tier {tier!r} in jarvis-framework.toml; "
                          f"turning on the wake word needs a person to say yes, so "
                          f"it must be 'ask'")}

    pid = uuid.uuid4().hex
    with _WAKE_LOCK:
        if _WAKE_PENDING is not None and not _WAKE_PENDING.get("withdrawn"):
            return {"ok": False, "enabled": False, "pending": True,
                    "error": "a card to turn on the wake word is already waiting"}
        _WAKE_PENDING = {"id": pid, "since": time.time(), "since_m": time.monotonic(), "timeout": _wake_timeout(),
                         "withdrawn": False}
    _audit("voice.wake_word.asked", {})

    def work():
        try:
            _wake_decide(pid, gate)
        except Exception:
            _wake_finish(pid, "failed", reason="unexpected error")

    try:
        spawn(work)
    except Exception as exc:
        _wake_finish(pid, "failed", reason=f"could not start ({type(exc).__name__})")
        return {"ok": False, "enabled": False, "pending": False,
                "error": "could not raise the approval card"}
    return {"ok": True, "enabled": False, "pending": True, "applied": False,
            "message": ("Approve the card on your PC or phone to turn it on. "
                        "Nothing changes until you do.")}


def wake_state() -> dict:
    """For status(): the switch, a card waiting, how the last one ended."""
    with _WAKE_LOCK:
        p = _WAKE_PENDING if (_WAKE_PENDING and not _WAKE_PENDING.get("withdrawn")) else None
        out = {"enabled": _wake_enabled(), "pending": p is not None}
        if p is not None:
            out["expires_in"] = max(0, int(_left_s(p)))
        if _WAKE_LAST is not None:
            out["last"] = {k: _WAKE_LAST[k] for k in ("outcome", "at", "reason")
                           if k in _WAKE_LAST}
    return out


def _reset_wake_for_tests() -> None:
    global _WAKE_PENDING, _WAKE_LAST
    with _WAKE_LOCK:
        _WAKE_PENDING = None
        _WAKE_LAST = None
        _WAKE_WITHDRAWN.clear()
    _close_awake()


# --------------------------------------------------------------------------
#   "Hey Jarvis." ... "what time is it?" - the follow-up window.
#
#   A clip that held ONLY the wake phrase opens a short window in which the
#   next wake-word clip needs no phrase of its own. Opened only after the
#   owner check passed; used once; `awake_timeout_s` long (8 s shipped).
#
#   One window PER MICROPHONE (the voice play test, 2026-09-27): "Hey
#   Jarvis." said to the desktop opens the desktop's window only. It used to
#   be one value for the whole PC, so the phone - hearing the same words
#   across the room - could use the desktop's window up, and the owner's real
#   question to the desktop then needed the phrase again and was dropped.
#   Keyed by the route's `mic` ("phone", "desktop", or "" when none is
#   named - an older app); there is no finer device id on the route yet.
# --------------------------------------------------------------------------

_AWAKE_LOCK = threading.Lock()
_AWAKE_UNTIL: dict = {}          # mic -> time.monotonic() the window closes


def _awake_seconds() -> float:
    try:
        return max(2.0, min(30.0, float(_cfg("awake_timeout_s", 8))))
    except (TypeError, ValueError):
        return 8.0


def _open_awake(mic: str = "") -> float:
    """Opens `mic`'s window (only that microphone's clips may use it)."""
    secs = _awake_seconds()
    with _AWAKE_LOCK:
        _AWAKE_UNTIL[_norm_mic(mic)] = time.monotonic() + secs
    return secs


def _take_awake(mic: Optional[str] = None) -> bool:
    """True, once, if `mic`'s window is open - and closes it. Another
    microphone's window is left as it is. `None` (tests, and nothing in
    hear()): any window at all, and every one is closed."""
    now = time.monotonic()
    with _AWAKE_LOCK:
        if mic is None:
            live = any(now < until for until in _AWAKE_UNTIL.values())
            _AWAKE_UNTIL.clear()
            return live
        until = _AWAKE_UNTIL.pop(_norm_mic(mic), 0.0)
    return now < until


def _close_awake() -> None:
    with _AWAKE_LOCK:
        _AWAKE_UNTIL.clear()
    _close_question()
    with _SAME_WAKE_LOCK:
        _SAME_WAKE.clear()


# --------------------------------------------------------------------------
#   One "hey Jarvis", two microphones (the voice play test, 2026-09-27).
#
#   With hands-free on both the phone and the desktop, one "Hey Jarvis,
#   set a timer for ten minutes" is heard by BOTH, and both send it here.
#   Each passes the owner check - it is the owner - so, before this, both
#   were answered: two answers, and an action that needs no card (a timer,
#   the next song) done twice.
#
#   So: a wake-word clip that passed the owner check and is about to be
#   acted on (words to answer, or "Hey Jarvis." opening a window) CLAIMS
#   that moment for its microphone. A passing wake-word clip from a
#   DIFFERENT microphone that arrived within SAME_WAKE_SECONDS of the
#   claimed one is the same words heard twice: it gets `other_device` true,
#   no words, `wake_heard` false - which both apps already drop without a
#   word (WakeRules.verdict IGNORE on the phone, voice.rs on the desktop) -
#   and nothing is kept from it. Whichever clip claims first is answered.
#
#   It only ever refuses more: a clip that would have been refused anyway
#   is refused as before, and the owner check still comes first (it runs
#   before any claim, and speech-to-text only after it). Two clips from the
#   SAME microphone are never matched (that is the owner talking again),
#   nor is the talk button (one deliberate press, on one device).
# --------------------------------------------------------------------------

#: Two microphones' passing "hey Jarvis" clips this close together (by when
#: each arrived) are one utterance heard twice. A first guess, to be
#: measured on the owner's two devices.
SAME_WAKE_SECONDS = 1.5

#: What the second copy's reply says. Neither app shows it (they drop a
#: wake-word reply with `wake_heard` false silently); it is for the logs and
#: for an app that wants to say it.
OTHER_DEVICE_REASON = "answered on your other device"

_SAME_WAKE_LOCK = threading.Lock()
_SAME_WAKE: dict = {}            # {"mic", "at"}: the last claimed clip


def _claim_wake(mic: str, arrived: float) -> bool:
    """True: act on this passing wake-word clip from `mic`, which arrived at
    `arrived` (time.monotonic()). False: another microphone's clip, arrived
    within SAME_WAKE_SECONDS of this one, was already acted on."""
    mic = _norm_mic(mic)
    with _SAME_WAKE_LOCK:
        if _SAME_WAKE and _SAME_WAKE["mic"] != mic \
                and abs(arrived - _SAME_WAKE["at"]) <= SAME_WAKE_SECONDS:
            return False
        _SAME_WAKE.clear()
        _SAME_WAKE.update(mic=mic, at=arrived)
        return True


# --------------------------------------------------------------------------
#   Jarvis asked a question aloud: the same window, without "hey Jarvis"
#   (the owner's decision of 2026-09-25, docs/JARVIS-API.md section 17, 5).
#
#   When the LAST sentence Jarvis spoke (say()) ends with a question mark -
#   "?", the full-width "？", or the Greek question mark U+037E - the next
#   wake-word clip needs no phrase of its own, like after "Hey Jarvis." on
#   its own. A later sentence that is not a question closes it: the answer
#   went on, so the question was not the last thing said. It lasts
#   `awake_timeout_s` from when the question should have finished playing:
#   the sound was made at `at` and lasts `seconds`; the sentence before it
#   may still have been playing then (the apps ask for the next sentence's
#   sound while the current one plays), so that one's length is allowed too.
#   Kept per app like the stop-word echo guard: a question said to the
#   phone opens it for the phone's clips only.
#
#   The owner check still runs on that clip, before any words exist, and a
#   clip that fails it does NOT use the window up (Jarvis's own voice or the
#   TV heard through the microphone would otherwise take it); the first clip
#   that passes does. It is a wake-word clip in every other way: under
#   "Only trust the talk button" it is trusted like any "hey Jarvis" clip.
# --------------------------------------------------------------------------

#: The marks that end a question: ASCII, full-width, and the Greek question
#: mark (U+037E, which looks like a semicolon). The apps use the same list
#: (jarvis-desktop tests/fixtures/voice-flow-cases.json, `question_marks`).
QUESTION_MARKS = ("?", "\uff1f", "\u037e")
_QUESTION: dict = {}              # {"at", "seconds", "prev", "mic"} or empty
_QUESTION_LOCK = threading.Lock()
_LAST_SAY: dict = {"at": -1e9, "seconds": 0.0}


_GREEK = re.compile("[\u0370-\u03ff\u1f00-\u1fff]")


def ends_with_question(text: str) -> bool:
    """Does `text` end with a question mark (closing quotes and brackets
    after it allowed)? A plain ";" counts only in Greek: Unicode folds the
    Greek question mark into it, so Greek text often ends a question that
    way - and anywhere else it is only a semicolon."""
    t = (text or "").rstrip().rstrip("\"'\u201d\u2019)]\u00bb").rstrip()
    if not t:
        return False
    return t[-1] in QUESTION_MARKS or (t[-1] == ";" and bool(_GREEK.search(t)))


def _note_said(text: str, seconds: float, mic: str = "") -> None:
    """say() made the sound of one sentence: open the question window when
    it asks something, close it when it does not."""
    now = time.monotonic()
    with _QUESTION_LOCK:
        prev = _LAST_SAY["seconds"] if now - _LAST_SAY["at"] < 60.0 else 0.0
        _LAST_SAY["at"], _LAST_SAY["seconds"] = now, float(seconds or 0.0)
        _QUESTION.clear()
        if ends_with_question(text):
            _QUESTION.update(at=now, seconds=float(seconds or 0.0), prev=min(prev, 30.0),
                             mic=_norm_mic(mic))


def _question_open(mic: str = "") -> bool:
    """The window after a question is open for a clip from `mic`."""
    mic = _norm_mic(mic)
    with _QUESTION_LOCK:
        if not _QUESTION:
            return False
        if mic and _QUESTION.get("mic") and _QUESTION["mic"] != mic:
            return False
        ends = (_QUESTION["at"] + _QUESTION["prev"] + _QUESTION["seconds"]
                + _awake_seconds())
        return time.monotonic() < ends


def _close_question() -> None:
    with _QUESTION_LOCK:
        _QUESTION.clear()


def _wake_spotter_state() -> dict:
    if jarvis_wakeword is None:
        return {"available": False, "engine": "openWakeWord (ONNX Runtime)",
                "phrase": str(_cfg("wake_phrase", "hey_jarvis")),
                "threshold": float(_cfg("wake_threshold", 0.5) or 0.5),
                "why": "jarvis_wakeword.py is not in the backend folder",
                "model_dir": ""}
    try:
        return jarvis_wakeword.status()
    except Exception as exc:
        return {"available": False, "engine": "openWakeWord (ONNX Runtime)",
                "phrase": "", "threshold": 0.5, "model_dir": "",
                "why": f"could not read it ({type(exc).__name__})"}


def _stop_state() -> dict:
    if jarvis_wakeword is None or not hasattr(jarvis_wakeword, "stop_status"):
        return {"available": False, "threshold": 0.0,
                "why": "jarvis_wakeword.py is missing or older than the stop word"}
    try:
        return jarvis_wakeword.stop_status()
    except Exception as exc:
        return {"available": False, "threshold": 0.0,
                "why": f"could not read it ({type(exc).__name__})"}


def _prints(voice: dict) -> dict:
    """gate.prints: {phone, desktop, general}, each {trained, samples,
    threshold, created, needs_retraining}. Never raises."""
    blank = {"trained": False, "samples": 0, "threshold": 0.0, "created": 0.0,
             "needs_retraining": False,
             # Since 2026-09-24 (the stricter check): the recording
             # conditions in the print, whether the stronger model has a
             # print of its own in it, and the owner's own bar for it.
             "subprints": [], "strong_trained": False, "strong_threshold": 0.0}
    got = voice.get("prints") if isinstance(voice.get("prints"), dict) else {}
    out = {}
    for k in ("phone", "desktop", "general"):
        p = got.get(k) if isinstance(got.get(k), dict) else {}
        out[k] = {**blank, **{f: p[f] for f in blank if f in p}}
    return out


def _strict_state(voice: dict) -> dict:
    """gate.strictness / privacy / memory / sensitive_memory / hands_free /
    hands_free_screen / hands_free_live / settings / models / cohort / repeat, from
    jarvis_voice.status(); the strict defaults, and `models` saying nothing
    is known, for a jarvis_voice.py older than them. Never raises."""
    st = voice.get("settings") if isinstance(voice.get("settings"), dict) else {}
    strict = str(voice.get("strictness") or "very_strict")
    return {
        "strictness": strict,
        "privacy": str(voice.get("privacy") or "private_on_screen"),
        # "" from a jarvis_voice.py older than the memory setting: the apps
        # then do not offer it.
        "memory": str(voice.get("memory") or ""),
        # The same for the fourth setting (answers that use a SENSITIVE saved
        # fact, the owner's decision of 2026-09-24): "" from an older
        # jarvis_voice.py, and the apps then do not offer it.
        "sensitive_memory": str(voice.get("sensitive_memory") or ""),
        # The fifth (how far "hey Jarvis" is trusted, the owner's decision of
        # 2026-09-24): "" from an older jarvis_voice.py - not offered.
        "hands_free": str(voice.get("hands_free") or ""),
        # The sixth (answers about the screen after "hey Jarvis", under
        # "only trust the talk button" - the owner's decision of
        # 2026-09-28): "" from an older jarvis_voice.py - not offered.
        "hands_free_screen": str(voice.get("hands_free_screen") or ""),
        # The seventh (how far a Jarvis Live turn is trusted under "only
        # trust the talk button" - the owner's answer of 2026-09-28): "" from
        # an older jarvis_voice.py - not offered.
        "hands_free_live": str(voice.get("hands_free_live") or ""),
        # The eighth (when App lock ends Jarvis Live on the PC - the owner's
        # decision of 2026-09-28): "" from an older jarvis_voice.py - the
        # desktop then does not offer it.
        "live_end": str(voice.get("live_end") or ""),
        # Talk-to-type on the PC (2026-09-28): "off" or "on"; "" from an
        # older jarvis_voice.py - the desktop then does not offer it.
        "talk_to_type": str(voice.get("talk_to_type") or ""),
        # "Better voice" (2026-09-28): "one"/"both" and "titanet"/"resnet221";
        # "" from an older jarvis_voice.py - the apps then do not offer them.
        "wake_confirm": str(voice.get("wake_confirm") or ""),
        "voice_id_model": str(voice.get("voice_id_model") or ""),
        "settings": st or {"strictness": strict, "privacy": "private_on_screen",
                           "voice_is_enough_allowed": strict == "very_strict",
                           "min_command_seconds": 0.0},
        "models": voice.get("models") if isinstance(voice.get("models"), dict) else {},
        "cohort": voice.get("cohort") if isinstance(voice.get("cohort"), dict) else {},
        "repeat": voice.get("repeat") if isinstance(voice.get("repeat"), dict) else {},
    }


def _live_brief() -> dict:
    """{"available", "on", "device"} for status(). Never raises."""
    if jarvis_live is None:
        return {"available": False, "on": False, "device": None,
                "why": "jarvis_live.py is not in the backend folder"}
    try:
        st = jarvis_live.ENGINE.status()
        return {"available": True, "on": bool(st.get("on")), "device": st.get("device")}
    except Exception as exc:
        return {"available": False, "on": False, "device": None,
                "why": f"could not read it ({type(exc).__name__})"}


def _verifier_state() -> dict:
    """{trained, positives, why} - never raises."""
    if jarvis_wakeword is None or not hasattr(jarvis_wakeword, "verifier_status"):
        return {"trained": False, "positives": 0,
                "why": "jarvis_wakeword.py is missing or older than the verifier"}
    try:
        return jarvis_wakeword.verifier_status()
    except Exception as exc:
        return {"trained": False, "positives": 0,
                "why": f"could not read it ({type(exc).__name__})"}


# --------------------------------------------------------------------------
#   status()
# --------------------------------------------------------------------------

def _files_present(*paths: str) -> bool:
    return all(p and Path(p).is_file() for p in paths)


#: What `/api/voice/utterance` asks for: see docs/JARVIS-API.md §5. Both
#: clients send exactly this - the phone resamples (Recorder.kt), and the
#: desktop averages its channels and resamples before sending (voice.rs
#: `to_server_format`). The server is more forgiving than this says: a
#: 16-bit WAV at another rate or with more channels is still read
#: (`_read_wav` averages the channels, and the real rate is passed on to
#: the models, which resample). `max_seconds` is what the phone uses as its
#: recording cap.
AUDIO_IN = {
    "format": "WAV, 16-bit mono PCM",
    "sample_rate": 16000,
    "max_seconds": 30.0,
    "client_stt_allowed": False,
    "why": ("the voice check can only check a voice if it is given the voice; "
            "a client that turned speech into text itself would send words, "
            "and there would be nothing left to check"),
}


def _training_state() -> dict:
    """The "Train my voice" card, as the phone shows it. Never raises: a
    missing jarvis_voice_enroll.py means the feature is not installed, which
    is an answer, not an error."""
    try:
        import jarvis_voice_enroll
    except Exception:
        return {"available": False, "pending": False, "calibrate": False,
                "why": "jarvis_voice_enroll.py is not in the backend folder"}
    try:
        return jarvis_voice_enroll.state()
    except Exception as exc:
        return {"available": False, "pending": False, "calibrate": False,
                "why": f"could not read it ({type(exc).__name__})"}


#: Smart Turn's pause rule, sent in status() so both listeners use one:
#: after this much quiet the model is asked "finished?"; a pause it called
#: unfinished is kept for up to TURN_MAX_PAUSE_MS. The phone (SmartTurn.kt
#: TurnEnd) and the desktop (voice.rs pause_step) hold the same numbers.
TURN_ASK_AFTER_MS = 200
TURN_MAX_PAUSE_MS = 2000


def _turn_state() -> dict:
    """Smart Turn, for status(). `enabled` is the owner's switch ([voice]
    turn_enabled, on unless set false) and governs the phone too, which runs
    its own copy of the model; `available` is whether THIS PC has the model
    (the desktop app asks this PC). Never raises."""
    enabled = bool(_cfg("turn_enabled", True))
    base = {"enabled": enabled, "available": False, "engine": "Smart Turn v3.2",
            "threshold": 0.5, "why": "", "ask_after_ms": TURN_ASK_AFTER_MS,
            "max_pause_ms": TURN_MAX_PAUSE_MS}
    try:
        import jarvis_turn
    except Exception:
        return {**base, "why": "jarvis_turn.py is not in the backend folder"}
    try:
        st = jarvis_turn.status()
    except Exception as exc:
        return {**base, "why": f"could not read it ({type(exc).__name__})"}
    why = str(st.get("why", ""))
    if not enabled:
        why = "switched off ([voice] turn_enabled = false)"
    return {**base, "available": bool(st.get("available")),
            "engine": str(st.get("engine", base["engine"])),
            "threshold": float(st.get("threshold", 0.5)), "why": why}


def _push_to_talk(voice: dict, stt_ok: bool, voice_loaded: bool):
    """(can a push-to-talk clip actually get an answer?, why not).

    The phone shows its talk button only when this is True, so it must mean
    "end to end": the owner check can pass AND there is something to turn
    the words into text. The first thing in the way is the one reported,
    in words the owner can act on.

    Not enrolled, in owner mode, is a NO: verify() refuses every voice when
    there is no profile, so a button would only ever answer "that didn't
    sound like you" - which reads as the product being broken. The phone
    points at "Train my voice" instead, using this `why`.
    """
    if not voice_loaded:
        return False, "The voice check (jarvis_voice.py) is missing on the PC."
    if not voice.get("enabled", False):
        return False, "Voice is switched off in the PC's settings ([voice] enabled)."
    broad = str(voice.get("mode", "owner")).strip().lower() == "broad"
    if not broad and voice.get("speaker_model") is False:
        # Since 2026-09-24 the basic check refuses every voice in owner mode
        # (jarvis_voice, hole 1), so a button would only ever say no.
        return False, ("The PC has no voice-ID model installed, so it cannot tell your "
                       "voice from anyone else's. Install it (backend/README.md, "
                       "\"Install the better voice check\").")
    if not broad and voice.get("needs_retraining"):
        return False, ("The PC's voice check changed since you trained it. "
                       "Train your voice again.")
    if not broad and not voice.get("enrolled"):
        return False, ("Jarvis has not learned your voice yet. Use Train my "
                       "voice on the Checks screen.")
    if not stt_ok:
        return False, ("The PC has no speech-to-text set up yet, so it cannot "
                       "turn what you say into words.")
    return True, ""


def _stt_state() -> tuple:
    """(available, status sentence, note or "")."""
    name = _stt_engine_name()
    kind, files = _stt_files()
    if sherpa_onnx is None:
        return (False, "not set up: the sherpa-onnx package is not installed",
                "sherpa-onnx is not installed in the Python that runs Jarvis "
                "(python -m pip install sherpa-onnx).")
    if name != STT_ENGINE:
        return (False, f"not set up: stt_engine is {name!r}; set it to \"sherpa-onnx\"",
                f"Your jarvis-framework.toml says stt_engine = {name!r}. Jarvis "
                f"has no code for that engine and never had - change that line to "
                f"stt_engine = \"sherpa-onnx\" (backend/README.md's speech-to-text "
                f"install step does it for you).")
    if not _files_present(*files.values()):
        return (False, "sherpa-onnx is selected but its model files are not on disk yet",
                f"sherpa-onnx speech-to-text is selected but its model files are "
                f"not on disk yet (looked in {_stt_dir()}).")
    return True, f"ready ({kind})", ""


def status() -> dict:
    """What the voice loop can actually do right now. Never overstates - a
    listed capability the owner then finds does not work is worse than one
    honestly reported missing.

    Cheap: file checks only. No model is loaded to answer this. (Since
    2026-09-24 the first call also STARTS jarvis_voice_flow's warm-up and
    the "One moment." clip on a thread of their own - this reply does not
    wait for either; `[voice] warm_engines = false` stops the first.)

    TWO SHAPES IN ONE REPLY, on purpose. The flat keys (enabled, enrolled,
    stt_available, ...) are what this module always returned. The nested
    ones - listening, stt, tts, audio_in, gate, wake, vad, turn - are what the
    phone reads (jarvis-client net/VoiceModels.kt). test_voice_contract.py
    reads the phone's own data classes and fails if a field goes missing.
    """
    voice_loaded = jarvis_voice is not None
    voice = jarvis_voice.status() if voice_loaded else {
        "enabled": False, "mode": "owner", "enrolled": False, "samples": 0,
        "threshold": 0.35, "embedder": "none", "speaker_model": False,
        "note": "jarvis_voice is not importable here",
    }

    stt_engine_name = _stt_engine_name()
    stt_ok, stt_status, stt_note = _stt_state()

    tts_engine_name = str(_cfg("tts_engine", "sherpa-onnx"))
    tts_paths = _sherpa_tts_paths()
    tts_files_ok = _files_present(tts_paths["model"], tts_paths["voices"],
                                   tts_paths["tokens"])

    notes = []
    if voice.get("note"):
        notes.append(voice["note"])
    if stt_note:
        notes.append(stt_note)
    if tts_engine_name == "sherpa-onnx" and not tts_files_ok:
        notes.append("Kokoro TTS model files are not on disk yet (looked "
                      f"under {Path(tts_paths['model']).parent}).")

    tts_ok = tts_engine_name == "sherpa-onnx" and tts_files_ok and sherpa_onnx is not None
    wake = wake_state()
    wake_on = wake["enabled"]
    spotter = _wake_spotter_state()
    ptt, ptt_why = _push_to_talk(voice, stt_ok, voice_loaded)

    vad_pick = vad_choice()
    vad_file = Path(vad_pick["path"]).is_file()
    vad_ok = vad_file and _vad_wanted() and sherpa_onnx is not None
    if not _vad_wanted():
        vad_status = "switched off ([voice] vad_enabled = false)"
    elif not vad_file:
        vad_status = f"not installed (looked for {vad_pick['path']})"
    elif sherpa_onnx is None:
        vad_status = "the sherpa-onnx package is not installed"
    else:
        vad_status = "ready"

    if wake_on and not spotter["available"]:
        wake_why = ("switched on, but the PC cannot hear it yet: " + spotter["why"])
    elif wake_on:
        wake_why = "switched on"
    elif wake["pending"]:
        wake_why = "waiting for you to approve the card"
    else:
        wake_why = ("off unless you turn it on: a phone's microphone goes "
                    "wherever you do")

    return {
        **voice,
        "stt_engine": stt_engine_name,
        "stt_available": stt_ok,
        "tts_engine": tts_engine_name,
        "tts_available": tts_ok,
        "wake_word_enabled": wake_on,
        "wake_phrase": _cfg("wake_phrase", "hey_jarvis"),
        # The route's own comment explains why: a client that transcribed
        # locally would send text, and the owner-voice gate would have
        # nothing left to check.
        "local_stt_on_client_allowed": False,
        "note": " ".join(notes),

        # ---- the nested shape the phone reads (VoiceModels.kt) ----------
        "available": True,
        "listening": {
            "push_to_talk": ptt,
            "push_to_talk_why": ptt_why,
            "wake_word": wake_on,
            "wake_word_why": wake_why,
            "wake_word_pending": bool(wake["pending"]),
        },
        "stt": {
            "engine": stt_engine_name,
            "available": stt_ok,
            "status": stt_status,
            # Never. Recognising speech on the client is the one thing that
            # would disarm the owner check.
            "client_fallback_ok": False,
        },
        "tts": {
            "engine": tts_engine_name,
            "available": tts_ok,
            "status": ("ready" if tts_ok else
                       "no Kokoro model files on disk yet"),
            # The same answer /api/voice/say gives with its 503: the client
            # may speak text it already holds, with an ON-DEVICE voice only.
            "client_fallback_ok": True,
            # Which voice Jarvis speaks in (a custom one, jarvis_voices.py)
            # and why the built-in one is used instead, if it is; and how
            # long the last few say() calls took. GET /api/voice/voices has
            # the whole picture.
            "voice": _custom_voice_brief(),
            "timings": say_timings()[-5:],
            # The animals' mouths timed by Kokoro itself (jarvis_mouth.py):
            # ready, or why not in plain words (a one-time step to run).
            "mouth": _mouth_status(),
        },
        # `version`: the Silero file in use ("v4", "v6", or "configured"
        # for a `vad_model` path); `chosen`: the `vad_version` line; `note`:
        # why the chosen one is not in use ("" when it is). Section 80.
        "vad": {"engine": "silero (sherpa-onnx)", "available": vad_ok,
                "status": vad_status, "version": vad_pick["in_use"],
                "chosen": vad_pick["chosen"], "note": vad_pick["note"]},
        "wake": {
            **wake,
            "phrase": spotter.get("phrase", "hey_jarvis"),
            "threshold": float(spotter.get("threshold", 0.5)),
            "awake_seconds": _awake_seconds(),
            # Whether THIS PC can hear "hey Jarvis" in a clip (the desktop
            # app's listening needs it). The phone spots on its own.
            "spotter": {"available": bool(spotter.get("available")),
                        "engine": str(spotter.get("engine", "")),
                        "why": str(spotter.get("why", ""))},
            # The owner's own "hey Jarvis" check (jarvis_wakeword's
            # verifier), built on the PC when "Train my voice" is approved.
            "verifier": _verifier_state(),
            # "Stop" while Jarvis speaks (jarvis_wakeword.spot_stop).
            "stop_word": _stop_state(),
            # The second "hey Jarvis" detector (jarvis_microwake.py) and the
            # owner's "both must agree" setting. Section 80.
            "confirm": _wake_confirm_state(),
        },
        "audio_in": dict(AUDIO_IN),
        # "Finished, or only paused?" - see _turn_state().
        "turn": _turn_state(),
        # Jarvis Live (2026-09-28): whether this PC has it, and the session.
        # GET /api/voice/live has the whole status; this says only enough for
        # an app to offer the Live button.
        "live": _live_brief(),
        "gate": {
            "mode": voice.get("mode", "owner"),
            "enabled": bool(voice.get("enabled", False)),
            "enrolled": bool(voice.get("enrolled", False)),
            "samples": int(voice.get("samples", 0) or 0),
            "threshold": float(voice.get("threshold", 0.0) or 0.0),
            "embedder": str(voice.get("embedder", "none")),
            "speaker_model": bool(voice.get("speaker_model", False)),
            "needs_retraining": bool(voice.get("needs_retraining", False)),
            "note": str(voice.get("note", "")),
            "training": _training_state(),
            # One voice print per microphone (jarvis_voice.py, "ONE VOICE
            # PRINT PER MICROPHONE"); every one untrained from an older
            # jarvis_voice.py that does not report them.
            "prints": _prints(voice),
            # The stricter check (2026-09-24) - see _strict_state().
            **_strict_state(voice),
        },
        # Since 2026-09-24 (jarvis_voice_flow.py, docs/JARVIS-API.md
        # section 17): interrupting Jarvis by talking, the "One moment."
        # clip, the engines kept warm, and each spoken turn's delay in
        # numbers. Reading it the first time starts the warm-up in the
        # background; this reply does not wait for it.
        "flow": _flow_status(voice),
    }


# --------------------------------------------------------------------------
#   hear() / say()
# --------------------------------------------------------------------------

SOURCE_WAKE_WORD = "wake_word"
#: A Jarvis Live clip (jarvis_live.py): no "hey Jarvis" needed while that
#: device's session is on; refused, unchecked, otherwise.
SOURCE_LIVE = "live"
#: Talk-to-type on the PC (the owner's decision, 2026-09-27; docs/JARVIS-API.md
#: section 72): the desktop app holds a key, records, and TYPES the words
#: into the program in front instead of sending them to the chat. The same
#: order as every clip - speech, the owner check, only then the words - plus
#: three differences, all in hear(): refused before anything runs while the
#: owner's switch (jarvis_voice `talk_to_type`) is off; the words are never
#: noted for chat history or the delay table (they are not a chat turn); and
#: they come back cleaned of "um"/"uh" (clean_dictation, below).
SOURCE_TALK_TYPE = "talk_to_type"
TALK_TYPE_OFF_REASON = ("talk-to-type is switched off on this PC - turn it on in "
                        "Settings, Voice (it shows you an approval card first)")


def _talk_type_on() -> bool:
    """The owner's talk-to-type switch. A jarvis_voice.py older than it, or
    one that cannot answer: off (fail closed - nothing is typed)."""
    fn = getattr(jarvis_voice, "talk_to_type_on", None) if jarvis_voice is not None else None
    if fn is None:
        return False
    try:
        return bool(fn())
    except Exception:
        return False


def _wake_confirm_wanted() -> bool:
    """The owner's "both detectors must agree" setting (jarvis_voice
    settings `wake_confirm`). A jarvis_voice.py older than it: no."""
    if jarvis_voice is None or not hasattr(jarvis_voice, "WAKE_BOTH"):
        return False
    try:
        return jarvis_voice.settings().get("wake_confirm") == jarvis_voice.WAKE_BOTH
    except Exception:
        return False


def _wake_confirm(samples, sample_rate: int, first_at: float) -> str:
    """"off" (the setting is not on), "agreed", "disagreed", or
    "unavailable" (on, but the second detector cannot run here - the first
    one then decides alone, as before, and status() says so)."""
    if not _wake_confirm_wanted():
        return "off"
    if jarvis_microwake is None:
        return "unavailable"
    try:
        verdict, _spot = jarvis_microwake.confirm(samples, sample_rate, first_at)
    except Exception:
        return "unavailable"
    return verdict if verdict in ("agreed", "disagreed") else "unavailable"


def _wake_confirm_state() -> dict:
    """status()'s wake.confirm: the setting, and whether the second
    detector can run. Cheap (jarvis_microwake.status loads no model)."""
    wanted = _wake_confirm_wanted()
    if jarvis_microwake is None:
        st = {"available": False,
              "why": "jarvis_microwake.py is not in the backend folder (run the patch script)"}
    else:
        try:
            st = jarvis_microwake.status()
        except Exception as exc:
            st = {"available": False, "why": f"it could not be asked ({type(exc).__name__})"}
    active = wanted and bool(st.get("available"))
    if active:
        note = ""
    elif wanted:
        note = ("both detectors are chosen, but the second one cannot run on this PC ("
                + str(st.get("why") or "unknown reason").rstrip(".")
                + "), so the first one decides alone, as before")
    else:
        note = ""
    return {"setting": "both" if wanted else "one", "active": active,
            "available": bool(st.get("available")), "why": str(st.get("why") or ""),
            "engine": "microWakeWord (pymicro-wakeword)",
            "agree_seconds": getattr(jarvis_microwake, "AGREE_SECONDS", 1.0)
            if jarvis_microwake is not None else 1.0,
            "note": note}


# ---------------------------------------------------------------------------
# clean_dictation() - adapted from Handy (https://github.com/cjpais/Handy,
# src-tauri/src/audio_toolkit/text.rs: remove_filler_words,
# collapse_stutters, normalize_transcription_output), ported from Rust to
# Python. MIT License, Copyright (c) 2025 CJ Pais - the full notice is in
# THIRD-PARTY-NOTICES.txt at the top of this repository. Only the English
# lists are used: the speech-to-text model on this PC is English.
# ---------------------------------------------------------------------------

#: Handy's UNIVERSAL_FILLER_WORDS (never a real word in any language) plus
#: its English-only list ("um", "ah", "eh").
_FILLER_WORDS = ("uh", "uhm", "umm", "uhh", "uhhh", "ehh", "ehm", "ahm", "hmm", "hm",
                 "mmm", "um", "ah", "eh")
_FILLER_PATTERNS = tuple(re.compile(r"\b" + re.escape(w) + r"\b[,.]?", re.IGNORECASE)
                         for w in _FILLER_WORDS)
_MULTI_SPACE = re.compile(r"\s{2,}")


def _opens_sentence(kept: str) -> bool:
    t = kept.rstrip()
    return not t or t[-1] in ".!?…"


def _remove_filler_matches(text: str, pattern) -> str:
    """Deletes every match; a capitalised filler that opened a sentence
    hands its capital on ("Um, so I think" -> "So I think")."""
    kept = []
    owed = False
    resume = 0

    def push(segment: str) -> None:
        nonlocal owed
        if owed:
            for i, ch in enumerate(segment):
                if ch.isalnum():
                    owed = False
                    kept.append(segment[:i] + ch.upper() + segment[i + 1:])
                    return
        kept.append(segment)

    for m in pattern.finditer(text):
        push(text[resume:m.start()])
        if m.group(0)[:1].isupper() and _opens_sentence("".join(kept)):
            owed = True
        resume = m.end()
    push(text[resume:])
    return "".join(kept)


def _collapse_stutters(text: str) -> str:
    """Three or more of the same word in a row become one ("I I I" -> "I")."""
    words = text.split()
    if not words:
        return text
    out, i = [], 0
    while i < len(words):
        w = words[i]
        low = w.lower()
        n = 1
        if low.isalpha():
            while i + n < len(words) and words[i + n].lower() == low:
                n += 1
        out.append(w)
        i += n if n >= 3 else 1
    return " ".join(out)


def clean_dictation(text: str) -> str:
    """What talk-to-type types: the words without "um"/"uh", a stutter
    collapsed, spaces tidied. Never adds a word."""
    out = str(text or "")
    for pattern in _FILLER_PATTERNS:
        out = _remove_filler_matches(out, pattern)
    out = _collapse_stutters(out)
    return _MULTI_SPACE.sub(" ", out).strip()

#: A clip longer than this (the VAD's speech span, which keeps 0.3 s either
#: side - so about 1.4 s of words) is never a stop: "Hey Jarvis, stop the
#: timer" is a request, and goes through every check.
STOP_MAX_SECONDS = 2.0
#: While Jarvis itself said "stop" this recently (its own voice may reach
#: the microphone), the stop word is not trusted.
STOP_ECHO_SECONDS = 30.0
_RECENT_SAYS: list = []           # [(monotonic time, text, mic)], newest last
_SAYS_LOCK = threading.Lock()
#: The WHOLE word (T11). r"\bstop" also matched "stopped", "stops",
#: "stopwatch", so any sentence with one of those made the owner's real
#: "stop" be ignored for 30 seconds.
_STOP_WORD = re.compile(r"\bstop\b", re.I)
#: say() takes `mic`: the route can say which app will play the words, so
#: Jarvis saying "stop" to the phone does not silence the desktop's stop word.
SAY_TAKES_MIC = True


def _norm_mic(mic) -> str:
    mic = str(mic or "").strip().lower()
    return mic if mic in ("phone", "desktop") else ""


def _jarvis_said_stop(mic: str = "") -> Optional[tuple]:
    """(seconds ago, what Jarvis said) when Jarvis itself said the word
    "stop" within STOP_ECHO_SECONDS, where its voice could reach `mic`;
    else None. Kept per app: words said for one app ("phone" or "desktop")
    only count against that app's microphone. Words said with no app named
    (what the say route does today) count against both, and a clip with no
    microphone named is checked against everything."""
    mic = _norm_mic(mic)
    now = time.monotonic()
    with _SAYS_LOCK:
        for t, s, said_to in reversed(_RECENT_SAYS):
            if now - t >= STOP_ECHO_SECONDS or not _STOP_WORD.search(s):
                continue
            if mic and said_to and said_to != mic:
                continue
            return now - t, s
    return None


def _remember_said(text: str, mic: str = "") -> None:
    now = time.monotonic()
    with _SAYS_LOCK:
        _RECENT_SAYS.append((now, text[:500], _norm_mic(mic)))
        del _RECENT_SAYS[:-20]

#: hear() takes `mic` (voice-mic.patch checks for this before passing it, so
#: a jarvis_hud.py patched against a newer jarvis_speech.py never calls an
#: older one with an argument it does not know).
TAKES_MIC = True


@dataclass
class Heard:
    is_owner: bool
    text: str = ""
    score: float = 0.0
    threshold: float = 0.0
    available: bool = True
    source: str = "push_to_talk"
    reason: str = ""
    mode: str = "owner"
    seconds: float = 0.0
    engine: str = ""
    #: source=wake_word only: "hey Jarvis" was in this clip (spotter AND
    #: transcript), or the clip came inside the follow-up window. False on a
    #: wake-word clip means "not for Jarvis": a client drops it silently.
    wake_heard: bool = False
    wake_score: float = 0.0
    #: The clip held only "hey Jarvis": the next wake-word clip within
    #: `awake_seconds` needs no phrase of its own.
    awake: bool = False
    awake_seconds: float = 0.0
    #: Which voice print decided: "phone", "desktop", "general" (the old
    #: single print) or "" - see jarvis_voice.py, "ONE VOICE PRINT PER
    #: MICROPHONE". Shown, never branched on by a client.
    voice_print: str = ""
    #: source=wake_word only: the clip was the stop word. Silence the reply
    #: being spoken and do nothing else (no words, no owner check).
    stop: bool = False
    #: source=wake_word only: the clip sounded like "stop", but Jarvis had
    #: just said the word itself, so it was NOT acted on. `reason` says so,
    #: in words an app can show as they are.
    stop_ignored: bool = False
    #: Since 2026-09-24 (the stricter voice check). The clip had less speech
    #: than a command needs (`min_seconds`, jarvis_voice.MIN_COMMAND_SECONDS)
    #: and was refused before any voice check - "say a little more".
    too_short: bool = False
    min_seconds: float = 0.0
    #: source=wake_word only (2026-09-27): the owner's "hey Jarvis" clip,
    #: but another microphone's copy of the same words (within
    #: SAME_WAKE_SECONDS) was already acted on. No words, `wake_heard`
    #: false: both apps drop it without a word.
    other_device: bool = False
    #: The strictness the voice was checked at: "very_strict" or "balanced"
    #: ("" when no check ran).
    strictness: str = ""
    #: May an answer that draws on email, calendar, notes or memory be READ
    #: ALOUD for this request? (jarvis_voice.may_speak, from the owner's
    #: "private answers" setting.) False: show such an answer on screen only.
    private_aloud: bool = False
    #: May an answer that uses what Jarvis REMEMBERS (the chat route's
    #: `injected_facts`) be read aloud, when nothing else about it is
    #: private? jarvis_voice.memory_aloud(): yes by default (the owner's
    #: choice, 2026-09-24), no with the "memory_on_screen" setting. An app
    #: that finds no such field (an older PC) treats it as false.
    memory_aloud: bool = False
    #: May an answer that uses a SENSITIVE saved fact (the chat route's
    #: `injected_sensitive` > 0) be read aloud? True only when the owner chose
    #: "sensitive_aloud" (jarvis_voice.sensitive_aloud()) AND this voice
    #: passed a real check - never in broad mode. Not implied by
    #: memory_aloud or private_aloud (the owner's decision, 2026-09-24). An
    #: app that finds no such field treats it as false.
    #: All three *_aloud are false, too, when the owner chose "only trust the
    #: talk button" (jarvis_voice `hands_free: button_only`) and this clip's
    #: source is not `push_to_talk` - "hey Jarvis", or no source said.
    sensitive_aloud: bool = False
    #: May an answer about the SCREEN (the `read_screen` read, "Look at
    #: this" / "Watch with me") be read aloud for this request, as far as
    #: the hands-free settings go? jarvis_voice.screen_aloud(source): true
    #: for the talk button, and for every clip under "same as the talk
    #: button" (the default); under "only trust the talk button", true for
    #: any other clip only when the owner chose `screen_aloud` (the owner's
    #: decision, 2026-09-28). Every earlier rule (a sensitive fact, a private
    #: question or tool) still comes first in the apps. An app that finds no
    #: such field (an older PC) treats it as false.
    screen_aloud: bool = False
    #: The words asked about something private (the router's private-topic
    #: backstop). A hint for the app, not a guarantee - see JARVIS-API.md.
    question_private: bool = False
    #: Jarvis Live (since 2026-09-28, jarvis_live.py). "" for a clip that has
    #: nothing to do with Live. For a `live` clip: the session after it -
    #: "on", "paused" (the clip was not looked at), "off" (no session on this
    #: device: `available` is false too - stop sending), "ended" (the owner's
    #: words ended it). For any clip whose words started Live: "started" -
    #: or "refused", with `reason` in words, when Live could not start (no
    #: real voice check yet, or standby).
    live: str = ""
    #: Why Live is paused, when it is: "card" or "other_voices"
    #: (jarvis_live.PAUSE_WORDS). The app shows the words, not this code.
    live_pause: str = ""
    #: "other_voices" after a few clips in a row that were not the owner's.
    live_hint: str = ""
    #: A FIXED line for the app to say now (jarvis_live.LINES): "I'm
    #: listening.", "Say a bit more, so I can tell it's you." (at most once a
    #: minute), "Okay. Live ended.", "Okay, 20 more minutes.". Never anything
    #: heard, so it is safe in any room and says nothing private.
    live_say: str = ""
    #: Why Live ended with this clip ("bye"), from jarvis_live.END_WORDS.
    live_ended: str = ""
    #: A too-short Live clip, put to the voice check only (NEVER to
    #: speech-to-text): "owner" - probably the owner, so both apps show
    #: "Didn't catch that - say a bit more"; "other" - counted as another
    #: voice, and nothing is shown or said.
    live_short: str = ""
    #: The owner's "hey Jarvis" at THIS device while Live is on the OTHER one
    #: ("phone" / "desktop"): the app offers "Live is on your phone - move it
    #: here?" instead of answering. `other_device` is true with it.
    live_elsewhere: str = ""

    def as_dict(self) -> dict:
        """What /api/voice/utterance sends back - assuming, as the desktop's
        voice.rs also does, that the route sends this dict as it is (the
        route's reply line is not in this repository to check).

        Carries BOTH clients' names for the same facts. The desktop reads
        `is_owner` / `available` (voice.rs HeardRaw). The phone reads `ok` /
        `owner` (VoiceModels.kt Heard). `ok` means a transcript was actually
        produced: the owner check passed AND there was an engine to turn the
        words into text. The phone tells "that didn't sound like you" apart
        from "too short" by `threshold > 0`, which only a clip that reached
        the voice check has.
        """
        d = asdict(self)
        d["owner"] = bool(self.is_owner)
        d["ok"] = bool(self.is_owner and self.available)
        return d


def _takes(fn, name: str) -> bool:
    """Whether `fn` accepts keyword `name` - jarvis_voice / jarvis_wakeword on
    the PC may be older than this file (`sample_rate` came 2026-09-23,
    `mic` 2026-09-24)."""
    try:
        import inspect
        return name in inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False


def _takes_rate(fn) -> bool:
    return _takes(fn, "sample_rate")


def _min_command_seconds() -> float:
    """The least speech a command needs (jarvis_voice, "MIN_COMMAND_SECONDS"),
    or 0 - no minimum - for a jarvis_voice.py older than it, or in broad
    mode, where no voice is being checked."""
    if jarvis_voice is None or not hasattr(jarvis_voice, "min_command_seconds"):
        return 0.0
    if str(_cfg("mode", "owner") or "owner").strip().lower() == "broad":
        return 0.0
    try:
        return float(jarvis_voice.min_command_seconds())
    except Exception:
        return 0.0


def _has_print(mic: str) -> bool:
    try:
        return jarvis_voice.find_profile(mic)[0] is not None
    except Exception:
        return False


def _note_short(mic: str) -> None:
    """Counts a too-short clip towards the owner's repeat rate."""
    try:
        jarvis_voice.note_outcome(False, jarvis_voice.settings()["strictness"], mic,
                                  too_short=True)
    except Exception:
        pass


def _note_for_history(words: str, verdict, embedder, source: str = "") -> None:
    """Tell the chat history (jarvis_chat_log) that THIS PC's speech route
    produced these words from a voice that passed the check, so the chat
    turn that carries them is recorded as "voice" rather than
    "voice_unverified". A hash is kept, never the words (see
    jarvis_chat_log.note_transcript). Never raises: history must never be
    the reason a spoken turn fails.

    `source` - how the clip started, "push_to_talk" or "wake_word" - goes
    with it (since 2026-09-24), so automatic learning can honour the
    owner's "hands-free" voice setting (jarvis_auto_learn.check_voice). A
    jarvis_chat_log.py older than that is not given it."""
    try:
        import jarvis_chat_log
        kw = {}
        if _takes(jarvis_chat_log.note_transcript, "source"):
            kw["source"] = str(source or "")
        jarvis_chat_log.note_transcript(
            words, strictness=str(getattr(verdict, "strictness", "") or ""),
            model=_deciding_model(verdict, embedder),
            mode=str(getattr(verdict, "mode", "") or ""), **kw)
    except Exception:
        pass


def _deciding_model(verdict, embedder) -> str:
    """Which speaker model decided the check, in words: the model of the
    verdict's last check (jarvis_voice.plan lists the deciding one last) -
    "the stronger voice-ID model" when that was it. `embedder` is only the
    SMALL model hear() built, so its name said "small" even when the
    stronger one decided, and automatic learning (which trusts voice only
    when the stronger model decided, very strict, mode owner - GUARDS L8)
    could not tell. Falls back to the embedder's name."""
    try:
        checks = list(getattr(verdict, "checks", None) or [])
        last = checks[-1] if checks else None
        if isinstance(last, dict) and last.get("model"):
            return str(last["model"])
    except Exception:
        pass
    return str(getattr(embedder, "name", "") or "")


def _really_checked(verdict, *, very: bool = False) -> bool:
    """Did the owner's voice pass a real check - not broad mode, which lets
    every voice in - and, with `very`, at the very strict setting?"""
    if str(getattr(verdict, "mode", "") or "") == "broad":
        return False
    strictness = str(getattr(verdict, "strictness", "") or "")
    if very:
        return strictness == "very_strict"
    return bool(strictness)


def _memory_aloud() -> bool:
    try:
        return bool(jarvis_voice.memory_aloud())
    except Exception:
        return False


def _sensitive_aloud() -> bool:
    try:
        return bool(jarvis_voice.sensitive_aloud())
    except Exception:
        return False                # an older jarvis_voice.py: on screen


def _source_trusted(source: str) -> bool:
    """Is a clip from `source` trusted like the talk button? (The owner's
    "hands-free" voice setting, jarvis_voice.hands_free_trusted.) A
    jarvis_voice.py older than that setting: yes, as it always was. One that
    cannot answer: no - the answer stays on screen."""
    fn = getattr(jarvis_voice, "hands_free_trusted", None)
    if fn is None:
        return True
    try:
        return bool(fn(source))
    except Exception:
        return False


def _screen_aloud(source: str, trusted: bool) -> bool:
    """May an answer about the screen be read aloud for a clip from
    `source`? (jarvis_voice.screen_aloud, the owner's decision of
    2026-09-28.) A jarvis_voice.py older than that setting: the same as the
    hands-free trust (`trusted`) - the setting is not there, so it is off.
    One that cannot answer: no - the answer stays on screen."""
    fn = getattr(jarvis_voice, "screen_aloud", None)
    if fn is None:
        return bool(trusted)
    try:
        return bool(fn(source))
    except Exception:
        return False


def _private_aloud() -> bool:
    try:
        return bool(jarvis_voice.may_speak(True, "voice")["speak"])
    except Exception:
        return False


def _question_private(text: str) -> bool:
    try:
        return bool(jarvis_voice.looks_private(text))
    except Exception:
        return False


def _live_fields(mic: str) -> dict:
    """The Live session as a clip's reply carries it: state, pause, hint."""
    if jarvis_live is None:
        return {"live": "off"}
    try:
        st = jarvis_live.ENGINE.status()
    except Exception:
        return {"live": "off"}
    on = bool(st.get("on")) and st.get("device") == _norm_mic(mic)
    return {"live": (str(st.get("state") or "off") if on else
                     ("ended" if st.get("state") == "ended" else "off")),
            "live_pause": str(st.get("paused") or "") if on else "",
            "live_hint": str(st.get("hint") or "") if on else ""}


def _live_refusal(mic: str, source: str) -> tuple:
    """(refusal or None, check-only). A `live` clip is looked at only while
    THIS microphone's Live session is on and not paused; anything else is
    refused here - before the file is read, before any speech is looked for,
    never checked, never turned into words. The one exception is a VOICE
    pause (other voices, or trouble with the owner's voice): then the clip
    may be put to the voice check - check-only is True - so the owner's own
    voice carries Live on without a tap. Still never transcribed unless it
    passes."""
    if jarvis_live is None:
        return Heard(False, source=source, available=False, live="off",
                     reason="jarvis_live.py is not in the backend folder"), False
    try:
        acc = jarvis_live.ENGINE.accepts(mic)
    except Exception as exc:
        return Heard(False, source=source, available=False, live="off",
                     reason=f"Jarvis Live could not be read ({type(exc).__name__})"), False
    if acc.get("ok"):
        return None, False
    if acc.get("check"):
        return None, True
    if acc.get("state") == "paused":
        return Heard(False, source=source, live="paused", live_pause=str(acc.get("code") or ""),
                     live_hint=_live_fields(mic).get("live_hint", ""),
                     reason=str(acc.get("words") or "")), False
    return Heard(False, source=source, available=False, live="off",
                 reason=str(acc.get("words") or "")), False


def _near_miss(verdict) -> bool:
    """A refusal close to the bar: probably the owner, recognised badly."""
    try:
        th, sc = float(verdict.threshold or 0.0), float(verdict.score or 0.0)
    except (TypeError, ValueError):
        return False
    return th > 0 and sc < th and sc >= th * jarvis_live.NEAR_MISS


def _live_elsewhere(mic: str) -> str:
    """The device Live is on, when that is not `mic`'s; else ""."""
    if jarvis_live is None:
        return ""
    try:
        return jarvis_live.ENGINE.on_elsewhere(mic)
    except Exception:
        return ""


def _offer_move(mic: str, engine: str, common: dict) -> Optional[Heard]:
    """The owner said "hey Jarvis" to THIS device while Live runs on the
    OTHER one: not answered here - the app offers "Live is on your phone -
    move it here?" (a tap moves it). Never silently dropped (the voice play
    test, 2026-09-28). Nothing from the words is kept."""
    elsewhere = _live_elsewhere(mic)
    if not elsewhere:
        return None
    return Heard(True, text="", engine=engine, wake_heard=False, other_device=True,
                 live_elsewhere=elsewhere,
                 reason=f"Live is on your {jarvis_live.device_words(elsewhere)}", **common)


def _live_phrase(text: str):
    if jarvis_live is None:
        return None
    try:
        return jarvis_live.phrase(text)
    except Exception:
        return None


def _live_start(mic: str) -> Optional[dict]:
    """Starts Live on `mic` (the owner's own words, checked; `started_by`
    voice). None when there is nothing to start it on - no device named (an
    older app), or no jarvis_live.py; else jarvis_live's answer, which says
    why it did not start (no real voice check, standby) when it did not."""
    if jarvis_live is None or not _norm_mic(mic):
        return None
    try:
        return jarvis_live.ENGINE.start(mic, by="voice")
    except Exception:
        return None


def _live_trust_source(mic: str) -> str:
    try:
        return jarvis_live.ENGINE.trust_source(mic)
    except Exception:
        return "live_voice"          # cannot tell how it started: the stricter


def _live_started(out: dict, engine: str, wake: bool, common: dict) -> Heard:
    """The reply to "let's talk": started, or refused in words."""
    if out.get("ok"):
        return Heard(True, text="", engine=engine, wake_heard=wake, live="started",
                     live_say=str(out.get("say") or jarvis_live.SAY_STARTED),
                     reason="Jarvis Live started", **common)
    return Heard(True, text="", engine=engine, wake_heard=wake, live="refused",
                 reason=str(out.get("error") or "Jarvis Live could not start"), **common)


def _too_short_reason(spoken: float, need: float) -> str:
    return (f"that was too short to be sure it was you ({spoken:.1f} seconds of "
            f"speech; a command needs at least {need:.1f}) - say a little more")


def hear(raw: bytes, source: str = "push_to_talk", mic: str = "",
         waited_ms=None) -> Heard:
    """One complete WAV utterance in. Never transcribes before the speaker
    is checked - see the module docstring for the whole order and why it is
    load-bearing, not a style choice.

    `mic`: "phone" or "desktop" (anything else counts as none named) - the
    clip is checked against that microphone's own voice print, and its own
    "hey Jarvis" verifier, falling back as jarvis_voice.lookup_order says.

    `source="barge_in"` (since 2026-09-24): Jarvis is talking and the app
    heard speech. Answered by barge_in() - stop or not - and NEVER
    transcribed; voice-flow.patch sends those clips there without coming
    here, and this is the same answer for a route that does not.

    `waited_ms`: how long the app waited for the owner to finish before
    sending (its Smart Turn wait), for the delay's numbers only."""
    mic = str(mic or "").strip().lower()
    if mic not in ("phone", "desktop"):
        mic = ""
    if source == SOURCE_BARGE_IN:
        b = barge_in(raw, mic=mic)
        return Heard(False, source=source, available=bool(b.get("available")),
                     stop=bool(b.get("stop")), reason=str(b.get("reason") or ""),
                     seconds=float(b.get("seconds") or 0.0))
    live = source == SOURCE_LIVE
    check_only = False
    if live:
        # Jarvis Live: only while THIS microphone's session is on and not
        # paused. Otherwise nothing below runs - no speech found, no voice
        # check, no words. During a voice pause the clip is CHECKED (not
        # transcribed) so the owner's own voice carries Live on.
        refused, check_only = _live_refusal(mic, source)
        if refused is not None:
            return refused
    talk_type = source == SOURCE_TALK_TYPE
    if talk_type and not _talk_type_on():
        # Before the WAV is even read: with the owner's switch off, a
        # talk-to-type clip is not checked, not transcribed, not kept.
        return Heard(False, source=source, available=False, reason=TALK_TYPE_OFF_REASON)
    t_in = time.monotonic()
    steps = {}
    cold = _stt_cache is _UNSET
    parsed = _read_wav(raw)
    if parsed is None:
        return Heard(False, source=source, available=False,
                      reason="could not read that as a 16-bit PCM WAV clip")
    samples, sample_rate = parsed
    seconds = round(len(samples) / float(sample_rate or 16000), 2)
    wake = source == SOURCE_WAKE_WORD

    # 2. Is there any speech at all? Silero VAD, when installed. A cough, a
    #    door, the fan: refused here, before anything else looks at it.
    t = time.monotonic()
    span = _speech_span(samples, sample_rate)
    steps["vad"] = (time.monotonic() - t) * 1000.0
    if span is None:
        return Heard(False, source=source, seconds=seconds,
                     reason="no speech in that recording")
    if span != "skip":
        samples = samples[span[0]:span[1]]
    # How much was said: the VAD's span, or (no VAD installed) the whole
    # clip, which the client already cut at a pause.
    spoken = len(samples) / float(sample_rate or 16000)
    need = _min_command_seconds()
    # Only once there is a print to check against: with none, the owner
    # needs "train your voice first", not "say a little more".
    short = need > 0 and spoken < need and _has_print(mic)

    # 3. The wake word. Switched on? Then: is "hey Jarvis" in it?
    via_window = False
    via_question = False
    spot = None
    t = time.monotonic()
    if wake:
        if not _wake_enabled():
            # available=False: not "this clip was not for Jarvis" but "this
            # PC takes no wake-word clips" - both clients stop listening on it.
            return Heard(False, source=source, available=False, seconds=seconds,
                         reason="the wake word is switched off on the PC")
        if spoken <= STOP_MAX_SECONDS and jarvis_wakeword is not None \
                and hasattr(jarvis_wakeword, "spot_stop"):
            stop = jarvis_wakeword.spot_stop(samples, sample_rate)
            if stop.ran and stop.heard:
                echo = _jarvis_said_stop(mic)
                if echo is not None:
                    # Jarvis's own voice said "stop" a moment ago; this may be
                    # that, heard through the speakers. Not acted on.
                    ago, said = echo
                    left = max(1, int(round(STOP_ECHO_SECONDS - ago)))
                    return Heard(False, source=source, seconds=seconds, stop_ignored=True,
                                 reason=(f"that sounded like \"stop\", but Jarvis said the "
                                         f"word \"stop\" itself {int(ago)} seconds ago "
                                         f"(\"{said[:80]}\"), and its own voice may have "
                                         f"reached the microphone, so it was ignored. Say "
                                         f"it again in {left} seconds, or press stop"))
                return Heard(False, source=source, seconds=seconds, stop=True,
                             reason="stop")
        if _take_awake(mic):
            via_window = True
        elif _question_open(mic):
            # Jarvis's last sentence asked something (see _note_said): no
            # phrase needed. Used up only by a clip that passes the owner
            # check (below), never by Jarvis's own voice or the TV.
            via_window = via_question = True
        else:
            if jarvis_wakeword is None:
                return Heard(False, source=source, available=False, seconds=seconds,
                             reason="jarvis_wakeword.py is not in the backend folder")
            if mic and _takes(jarvis_wakeword.spot, "mic"):
                spot = jarvis_wakeword.spot(samples, sample_rate, mic=mic)
            else:
                spot = jarvis_wakeword.spot(samples, sample_rate)
            if not spot.ran:
                return Heard(False, source=source, available=False, seconds=seconds,
                             reason="the PC cannot listen for \"hey Jarvis\": " + spot.why)
            if not spot.heard:
                # Not for Jarvis. Not checked, not transcribed, not kept.
                return Heard(False, source=source, seconds=seconds,
                             wake_score=spot.score,
                             reason="no \"hey Jarvis\" in that recording")
            # 3a (2026-09-28, "Better voice"). With the owner's "both
            # detectors" setting, the second, differently-built detector
            # must have heard it too, within a second of the first. It can
            # only say no - never make a wake out of nothing - and it runs
            # before the voice check and before any words exist, like the
            # first. Not installed: the first decides alone, as before, and
            # status() says so (the setting could not be chosen then).
            confirm = _wake_confirm(samples, sample_rate, spot.at)
            if confirm == "disagreed":
                return Heard(False, source=source, seconds=seconds,
                             wake_score=spot.score,
                             reason=("the second \"hey Jarvis\" detector did not hear it, "
                                     "so it was not taken as \"hey Jarvis\""))
        steps["wake"] = (time.monotonic() - t) * 1000.0

    # Jarvis Live: "stop" in a short clip silences Jarvis, exactly as it
    # does for a "hey Jarvis" clip - no voice check needed to stop speech,
    # never transcribed, nothing else done.
    if live and spoken <= STOP_MAX_SECONDS and jarvis_wakeword is not None \
            and hasattr(jarvis_wakeword, "spot_stop"):
        stop = jarvis_wakeword.spot_stop(samples, sample_rate)
        if stop.ran and stop.heard and _jarvis_said_stop(mic) is None:
            return Heard(False, source=source, seconds=seconds, stop=True, reason="stop",
                         **_live_fields(mic))

    if jarvis_voice is None:
        return Heard(False, source=source, available=False, seconds=seconds,
                      reason="jarvis_voice is not importable; refusing "
                             "rather than skipping the owner check")

    def check_owner():
        # 4. The owner check.
        try:
            emb = jarvis_voice.EcapaEmbedder()
        except Exception:
            emb = jarvis_voice.Embedder()
        # The real sample rate goes with the clip. Both clients send 16 kHz
        # now, but an older desktop (before 2026-09-24) sent its
        # microphone's own rate, and the speaker model resamples when told.
        # Only to a jarvis_voice.py that takes it - an older copy on the PC
        # would raise TypeError here, and this call is not wrapped.
        kw = {}
        if _takes_rate(jarvis_voice.verify):
            kw["sample_rate"] = sample_rate
        if mic and _takes(jarvis_voice.verify, "mic"):
            kw["mic"] = mic
        return jarvis_voice.verify(samples, emb, **kw), emb

    # 3b. Long enough to be sure it is the owner? (2026-09-24.) A speaker
    #     model has little to go on in a second of speech, so a command
    #     that short is refused HERE - before the owner check, never
    #     transcribed - and the owner is asked to say a little more. The one
    #     exception is a "hey Jarvis" clip, which is the wake path, not a
    #     command: it may open the listening window (step 6), and nothing
    #     more - a command inside a clip that short is refused after all.
    if short and (not wake or via_window):
        _note_short(mic)
        extra = {}
        if live:
            # Jarvis Live (the voice play test, 2026-09-28): the clip is put
            # to the voice check ONLY - never to speech-to-text - to decide
            # whether it was probably the owner. The owner hears "say a bit
            # more" at most once a minute and sees "Didn't catch that" every
            # time; anyone else (the TV) makes Jarvis say nothing and counts
            # as another voice. The reason stays as the caption.
            extra = _live_fields(mic)
            try:
                v_short, _ = check_owner()
            except Exception:
                v_short = None
            if v_short is not None and v_short.is_owner and _really_checked(v_short):
                extra["live_short"] = "owner"
                try:
                    jarvis_live.ENGINE.carry_on_by_voice(mic)
                    if jarvis_live.ENGINE.short_line_due():
                        extra["live_say"] = jarvis_live.SAY_SHORT
                except Exception:
                    pass
            else:
                extra["live_short"] = "other"
                try:
                    jarvis_live.ENGINE.note_refused(
                        mic, near_miss=v_short is not None and _near_miss(v_short))
                except Exception:
                    pass
            extra.update({k: v for k, v in _live_fields(mic).items() if k != "live"})
        return Heard(False, source=source, seconds=seconds, too_short=True,
                     min_seconds=need, reason=_too_short_reason(spoken, need), **extra)

    t = time.monotonic()
    verdict, embedder = check_owner()
    steps["owner_check"] = (time.monotonic() - t) * 1000.0
    # What this clip is trusted as. A Live clip asks as "live" when the owner
    # pressed Start, or like "hey Jarvis" when Live was started by voice
    # (jarvis_live.trust_source - one switch there decides).
    trust_src = _live_trust_source(mic) if live else source
    trusted = _source_trusted(trust_src)
    common = dict(score=verdict.score, threshold=verdict.threshold,
                  source=source, mode=verdict.mode, seconds=seconds,
                  wake_score=spot.score if spot else 0.0,
                  voice_print=str(getattr(verdict, "voice_print", "") or ""),
                  strictness=str(getattr(verdict, "strictness", "") or ""),
                  # Only after a REAL check of the owner's voice: in broad
                  # mode verify() lets every voice in, and "voice check is
                  # enough" (the card the owner approved) says "whenever your
                  # voice passes the very strict check". Nothing private is
                  # read aloud to a voice nobody checked (voice audit,
                  # 2026-09-24).
                  #
                  # And only for a clip the owner's "hands-free" setting
                  # trusts: under "only trust the talk button", a clip that
                  # did not come from the talk button (hey Jarvis, or no
                  # source said) reads none of these aloud - a recording of
                  # the owner played near the microphone passes the voice
                  # check (the owner's decision, 2026-09-24).
                  private_aloud=(_private_aloud() and _really_checked(verdict, very=True)
                                 and trusted),
                  memory_aloud=_memory_aloud() and _really_checked(verdict) and trusted,
                  sensitive_aloud=(_sensitive_aloud() and _really_checked(verdict)
                                   and trusted),
                  # An answer about the screen is read aloud like a web
                  # search's - no voice check asked of it, as before - but
                  # under "only trust the talk button" a clip from anywhere
                  # else keeps it on screen unless the owner allowed it (the
                  # owner's decision, 2026-09-28).
                  screen_aloud=_screen_aloud(trust_src, trusted))

    if not verdict.is_owner:
        if live:
            # Not the owner's voice: counted (the sign says so after a few,
            # and Live pauses after many), never turned into words, and the
            # quiet clock does not move - the TV cannot keep Live open.
            try:
                jarvis_live.ENGINE.note_refused(mic, near_miss=_near_miss(verdict))
            except Exception:
                pass
            return Heard(False, reason=verdict.reason, **common, **_live_fields(mic))
        return Heard(False, reason=verdict.reason, **common)
    if check_only:
        # A voice pause, and this was the owner: Live carries on without a
        # tap, and this sentence is taken like any other.
        try:
            jarvis_live.ENGINE.carry_on_by_voice(mic)
        except Exception:
            pass

    # A Live clip that was the owner's but could not become words keeps the
    # session's fields, so the app keeps listening and says so rather than
    # taking "not available" as Live being over (bug 2 of the review,
    # 2026-09-28).
    live_extra = _live_fields(mic) if live else {}
    if _stt_engine() is None:
        return Heard(True, available=False, wake_heard=wake,
                     reason="that was you, but no speech-to-text model is "
                            "installed here yet - see jarvis_speech.status()",
                     **common, **live_extra)

    # 5. The words.
    t = time.monotonic()
    try:
        text = _transcribe(samples, sample_rate)
    except Exception as exc:
        return Heard(True, available=False, wake_heard=wake,
                     reason=f"transcription failed ({type(exc).__name__})",
                     **common, **live_extra)
    steps["stt"] = (time.monotonic() - t) * 1000.0
    engine = f"{STT_ENGINE}:{_stt_files()[0]}"

    def timed(words: str) -> None:
        # One row of numbers for the delay (jarvis_voice_flow): only for a
        # clip that became words, which is a turn the owner waits on.
        if words:
            _flow("note_heard", t_in, steps, source=source, mic=mic,
                  waited_ms=waited_ms, cold=cold)
            _note_for_history(words, verdict, embedder, trust_src)

    def other_device() -> Heard:
        # The same words, heard by the owner's other device and already
        # acted on there. Nothing from this copy is kept.
        return Heard(True, text="", engine=engine, wake_heard=False, other_device=True,
                     reason=OTHER_DEVICE_REASON, **common)

    if live:
        # Jarvis Live: the owner's words (step 4 passed). "Hey Jarvis" said
        # anyway is taken off. Live's own phrases are answered here, on the
        # device that heard them, and go no further; anything else is a
        # spoken question like any other.
        try:
            found, rest = jarvis_wakeword.split_wake(text)
        except Exception:
            found, rest = False, text
        if found and rest:
            text = rest
        said = _live_phrase(text)
        if said is not None and said[0] == "end":
            try:
                jarvis_live.ENGINE.stop("bye", device=mic)
            except Exception:
                pass
            return Heard(True, text="", engine=engine, live="ended", live_ended="bye",
                         live_say=jarvis_live.SAY_BYE, reason="Jarvis Live ended", **common)
        if said is not None and said[0] == "extend":
            try:
                out = jarvis_live.ENGINE.extend(said[1])
            except Exception:
                out = {"ok": False}
            fields = _live_fields(mic)
            if out.get("ok"):
                fields["live_say"] = jarvis_live.SAY_EXTENDED.format(n=out.get("minutes"))
            return Heard(True, text="", engine=engine, reason="more time", **common, **fields)
        if said is not None and said[0] == "start":
            # Already on: nothing to start, and not a question either.
            return Heard(True, text="", engine=engine, reason="Jarvis Live is already on",
                         **common, **_live_fields(mic))
        try:
            jarvis_live.ENGINE.note_owner(mic)
        except Exception:
            pass
        timed(text)
        return Heard(True, text=text, engine=engine,
                     question_private=_question_private(text), **common, **_live_fields(mic))

    if talk_type:
        # Typed into another program, never a chat turn: not noted for chat
        # history, not a row in the delay table, nothing read aloud. The
        # words go back to the desktop app once, in this reply, and are not
        # kept here.
        quiet = {**common, "private_aloud": False, "memory_aloud": False,
                 "sensitive_aloud": False, "screen_aloud": False}
        return Heard(True, text=clean_dictation(text), engine=engine, **quiet)

    if not wake or via_window:
        if via_question:
            _close_question()
            # "Hey Jarvis, ..." said anyway: the words after it are the answer.
            try:
                found, rest = jarvis_wakeword.split_wake(text)
            except Exception:
                found, rest = False, text
            if found and rest:
                text = rest
        if wake and text.strip() and not _claim_wake(mic, t_in):
            return other_device()
        said = _live_phrase(text)
        started = _live_start(mic) if said is not None and said[0] == "start" else None
        if started is not None:
            # "Let's talk" - with the talk button, or in the window after a
            # bare "Hey Jarvis." - starts Live on this device. No card: the
            # owner's own act, and the owner check just passed.
            return _live_started(started, engine, wake, common)
        if wake and text.strip():
            offer = _offer_move(mic, engine, common)
            if offer is not None:
                return offer
        timed(text)
        return Heard(True, text=text, engine=engine, wake_heard=wake,
                     question_private=_question_private(text), **common)

    # 6. Wake word: the transcript must start with it. The words are the
    #    owner's own (step 4 passed); a clip that was not addressed to
    #    Jarvis is dropped, not answered.
    found, rest = jarvis_wakeword.split_wake(text)
    if not found:
        return Heard(True, text="", engine=engine,
                     reason="that did not start with \"hey Jarvis\", so it was ignored",
                     **common)
    if not rest:
        # "Hey Jarvis." on its own, heard by two devices: only the first
        # opens a window (its own), so the owner's next sentence is taken by
        # that device alone.
        if not _claim_wake(mic, t_in):
            return other_device()
        offer = _offer_move(mic, engine, common)
        if offer is not None:
            return offer
        secs = _open_awake(mic)
        return Heard(True, text="", engine=engine, wake_heard=True, awake=True,
                     awake_seconds=secs, reason="listening", **common)
    if short:
        # "Hey Jarvis" was allowed through as the wake path only (step 3b);
        # a command in a clip this short is not taken.
        _note_short(mic)
        return Heard(True, text="", engine=engine, wake_heard=True, too_short=True,
                     min_seconds=need, reason=_too_short_reason(spoken, need), **common)
    if not _claim_wake(mic, t_in):
        return other_device()
    said = _live_phrase(rest)
    started = _live_start(mic) if said is not None and said[0] == "start" else None
    if started is not None:
        # "Hey Jarvis, let's talk": Jarvis Live starts on the device that
        # heard it (docs/LIVE-DESIGN.md section 2). No card.
        return _live_started(started, engine, True, common)
    offer = _offer_move(mic, engine, common)
    if offer is not None:
        return offer
    timed(rest)
    return Heard(True, text=rest, engine=engine, wake_heard=True,
                 question_private=_question_private(rest), **common)


def say(text: str, mic: str = "") -> Optional[bytes]:
    """Text in, one WAV out - or None, meaning "no engine", which the route
    turns into a 503 the client may answer with its own on-device voice.

    Empty text also returns None. It is a client bug rather than a real
    request to speak nothing, and folding it into the same "nothing to send
    back" answer the route already has is simpler than inventing a third
    outcome for a case that should not occur in practice.
    """
    text = (text or "").strip()
    if not text:
        return None
    # Remembered (in memory, for STOP_ECHO_SECONDS) only so Jarvis saying
    # "stop" itself is not taken for the owner's stop word. `mic`: which app
    # plays it ("phone" / "desktop"), when the route says; "" counts for both.
    _remember_said(text, mic)
    t0 = time.monotonic()
    # Anything said closes the window after a question until this sentence's
    # sound is known (a sentence without sound leaves it closed).
    _close_question()
    # The delay (jarvis_voice_flow): the first sentence of a spoken turn's
    # answer marks when its first sound was ready. Numbers only.
    mark = _flow("say_started")
    mouth: list = []
    # A crisis answer is said in the plain built-in voice, not an animal's
    # (plain_voice_now; the owner's decision of 2026-09-28). The mouth track
    # is made the same either way.
    samples, rate, engine, voice, fallback, note, failed = _synthesise(
        text, mouth=mouth, plain=plain_voice_now(text))
    if samples is None:
        _note_timing("none", voice, text, t0, 0.0, fallback, note, failed=failed)
        return None
    _note_timing(engine, voice, text, t0, len(samples) / float(rate), fallback, note)
    # Jarvis asked something aloud: the next wake-word clip needs no phrase.
    _note_said(text, len(samples) / float(rate or 16000), mic)
    # Jarvis Live's quiet clock starts again from Jarvis speaking - but not
    # from "Say a bit more": asking for more words is no conversation.
    if jarvis_live is not None:
        try:
            jarvis_live.ENGINE.note_spoke(mic, text)
        except Exception:
            pass
    wav = _write_wav(samples, rate)
    if mouth and mouth[0]:
        # The mouth shapes from Kokoro's own timing, as a "jmth" block after
        # the sound (jarvis_mouth.py; docs/JARVIS-API.md). None: no block.
        wav = _mouth("add_chunk", wav, mouth[0]) or wav
    if mark is not None:
        try:
            mark.audio_ready((time.monotonic() - t0) * 1000.0)
        except Exception:
            pass
    return wav


def _voices_mod(voices_module=None):
    if voices_module is not None:
        return voices_module
    try:
        import jarvis_voices
        return jarvis_voices
    except Exception:
        return None


def plain_voice_now(text: str = "") -> bool:
    """Say `text` in the PLAIN built-in voice - the owner's own choice, no
    animal voice, no pitch rise? True while a crisis answer is being given
    or spoken, and for the crisis help message's own words
    (jarvis_wellbeing.speak_plainly: "At serious moments the animals drop
    the cute gestures", the owner's decision of 2026-09-28). A missing or
    older jarvis_wellbeing.py answers False - the voice as before. Never
    raises."""
    try:
        import jarvis_wellbeing
        fn = getattr(jarvis_wellbeing, "speak_plainly", None)
        return bool(fn(text)) if fn is not None else False
    except Exception:
        return False


def tts_voice(voices_module=None, *, plain: bool = False) -> tuple:
    """(Kokoro voice number, speed, pitch rise) for the built-in voice, read
    ONCE - so one sentence never mixes two faces' settings if the face
    changes halfway through reading them. `plain=True` (a crisis answer,
    plain_voice_now): the face left out - the owner's own built-in choice
    and speaking speed (jarvis_voices.speaker/speed), no pitch rise. Never
    raises."""
    V = _voices_mod(voices_module)
    if plain:
        if V is not None and hasattr(V, "speaker") and hasattr(V, "speed"):
            try:
                # (speaker_speed: the speaking speed times the chosen voice's
                # own pace - Ashby's 0.95; an older jarvis_voices has speed().)
                pace = getattr(V, "speaker_speed", V.speed)
                return int(V.speaker()), float(pace()), 0.0
            except Exception:
                pass
        # No jarvis_voices to ask: the config's own speaker and speed,
        # never an animal's.
        try:
            sid = int(_cfg("tts_speaker_id", 0) or 0)
        except Exception:
            sid = 0
        try:
            pace = float(_cfg("tts_speed", 1.0) or 1.0)
        except Exception:
            pace = 1.0
        return max(0, sid), (pace if 0.5 <= pace <= 2.0 else 1.0), 0.0
    if V is not None and hasattr(V, "builtin_voice"):
        try:
            sid, speed, semis, _face = V.builtin_voice()
            return int(sid), float(speed), _pitch_range(semis)
        except Exception:
            pass
    return tts_speaker(V), tts_speed(V), 0.0


def tts_pitch(voices_module=None) -> float:
    """How many semitones higher (below 0: deeper) the built-in voice
    speaks: 0, except while "Voice follows the face" speaks for an animal
    face (jarvis_voices.builtin_voice()), then that animal's pitch - its own,
    or the one the owner picked for it. Never raises."""
    V = _voices_mod(voices_module)
    if V is not None and hasattr(V, "builtin_voice"):
        try:
            return _pitch_range(V.builtin_voice()[2])
        except Exception:
            pass
    return 0.0


#: The pitch the built-in voice may be moved by, in semitones - the range
#: the owner may pick per animal (jarvis_voices.MIN_SEMITONES/MAX_SEMITONES).
PITCH_MIN, PITCH_MAX = -3.0, 4.0


def _pitch_range(semis) -> float:
    """`semis` held to PITCH_MIN..PITCH_MAX; anything that is not a finite
    number is 0 (no change). Never raises."""
    try:
        v = float(semis)
    except (TypeError, ValueError):
        return 0.0
    if v != v or v in (float("inf"), float("-inf")):
        return 0.0
    return max(PITCH_MIN, min(PITCH_MAX, v))


def pitch_up(samples, semitones: float):
    """The sound `semitones` higher, by playing it faster: every frequency
    rises by 2^(semitones/12) and the sound gets shorter by the same factor
    (which is also what makes a voice sound SMALLER - the cute part). Below
    0 it is the other way round: played slower, deeper and longer, by the
    same rule (f below 1). The caller asks Kokoro for slower (or, deeper,
    faster) speech first (kokoro_speak), so the pace comes out as chosen,
    and jarvis_mouth divides its times by the same f. numpy only,
    milliseconds. 0, or no numpy, hands the samples back untouched."""
    if np is None or not semitones:
        return samples
    x = np.asarray(samples, dtype=np.float32)
    if len(x) < 2:
        return x
    f = 2.0 ** (float(semitones) / 12.0)
    n = int(len(x) / f)
    return np.interp(np.arange(n, dtype=np.float64) * f,
                     np.arange(len(x), dtype=np.float64), x).astype(np.float32)


def kokoro_speak(engine, text: str, sid: int, speed: float, semitones: float = 0.0,
                 mouth: Optional[list] = None):
    """(samples, sample_rate) from Kokoro in the built-in voice, with the
    animal's pitch applied (higher, or below 0 deeper) - or None. THE one
    way the built-in voice is made: the spoken answer (_synthesise) and
    jarvis_voice_flow's two copies of it (the "One moment." clip and the
    barge-in reference voice) all come through here, so all three sound the
    same - and so does an animal's "Try it" (jarvis_voices.try_face_animal).

    `mouth`: a list to receive the mouth shapes (jarvis_mouth.py) - the
    "jmth" payload, or None - when the caller wants them (say() does). The
    sound is the same either way: jarvis_mouth asks sherpa-onnx for it with
    its pause-shortening off and shortens the pauses with an exact copy of
    sherpa-onnx's own (checked byte for byte, docs/LIPSYNC.md); whenever it
    cannot, this speaks exactly as it always did."""
    if mouth is not None:
        try:
            import jarvis_mouth
            # Kokoro v1.0's British voices are read with (and asked of
            # sherpa-onnx as) their own espeak voice, exactly as
            # _kokoro_generate asks; every other voice, and all of v0.19,
            # is read with the engine's own language as before.
            accent = accent_lang(sid)
            got = jarvis_mouth.speak(engine, text, sid, speed, semitones, pitch_up=pitch_up,
                                     silence_scale=_TTS_SILENCE_SCALE,
                                     lang=accent or str(_cfg("tts_lang", "en-us") or "en-us"),
                                     paths=_sherpa_tts_paths(), extra_lang=accent)
        except Exception:
            got = False  # anything at all: speak exactly as before
        if got is None:
            return None
        if got:
            mouth.append(got[2])
            return got[0], got[1]
    f = 2.0 ** (float(semitones or 0.0) / 12.0)
    audio = _kokoro_generate(engine, text, int(sid), float(speed) / f)
    if audio is None or len(audio.samples) == 0:
        return None
    return pitch_up(audio.samples, semitones), audio.sample_rate


def accent_lang(sid: int) -> Optional[str]:
    """The espeak voice to ask Kokoro for with voice number `sid`, or None
    for the engine's own default: Kokoro v1.0's British voices are asked for
    British English (jarvis_voices.accent_lang -> jarvis_kokoro), everything
    else - the old pack, an American voice, a PC with no jarvis_voices.py -
    is spoken exactly as before. Never raises."""
    V = _voices_mod()
    fn = getattr(V, "accent_lang", None) if V is not None else None
    if fn is None:
        return None
    try:
        lang = fn(int(sid))
    except Exception:
        return None
    return lang if isinstance(lang, str) and lang.strip() else None


def _kokoro_generate(engine, text: str, sid: int, speed: float):
    """engine.generate(...) for one sentence, asking for the voice's accent
    when it has one (a per-call `lang`, Kokoro v1.0 only). Falls back to the
    plain call - the engine's own language - when this sherpa-onnx cannot be
    asked (no GenerationConfig) or answers with no sound for the accent."""
    lang = accent_lang(sid)
    if lang:
        try:
            cfg = sherpa_onnx.GenerationConfig()
            cfg.sid = int(sid)
            cfg.speed = float(speed)
            cfg.extra = {"lang": lang}
            audio = engine.generate(text, cfg)
            if audio is not None and len(audio.samples) > 0:
                return audio
        except Exception:
            pass  # speak as before, in the engine's own language
    return engine.generate(text, sid=int(sid), speed=float(speed))


def tts_speed(voices_module=None) -> float:
    """How fast the built-in voice speaks: the owner's speaking-speed setting
    (jarvis_voices.speed(), both apps' "How fast Jarvis speaks") - times the
    animal's own pace while "Voice follows the face" speaks for an animal
    face (jarvis_voices.builtin_voice()) - or, with an older
    jarvis_voices.py, or none, `[voice] tts_speed`, as before."""
    V = _voices_mod(voices_module)
    if V is not None and hasattr(V, "builtin_voice"):
        try:
            return float(V.builtin_voice()[1])
        except Exception:
            pass
    if V is not None and hasattr(V, "speed"):
        try:
            return float(V.speed())
        except Exception:
            pass
    try:
        v = float(_cfg("tts_speed", 1.0) or 1.0)
    except (TypeError, ValueError):
        return 1.0
    return v if 0.5 <= v <= 2.0 else 1.0


def tts_speaker(voices_module=None) -> int:
    """Which of Kokoro's own voices the built-in voice uses: the owner's
    voice-choice setting (jarvis_voices.speaker(), both apps' "Jarvis's
    built-in voice") - or the animal's own voice while "Voice follows the
    face" speaks for an animal face (jarvis_voices.builtin_voice()) - or,
    with an older jarvis_voices.py, or none, `[voice] tts_speaker_id`, as
    before (ease-of-use audit row 13)."""
    V = _voices_mod(voices_module)
    if V is not None and hasattr(V, "builtin_voice"):
        try:
            return int(V.builtin_voice()[0])
        except Exception:
            pass
    if V is not None and hasattr(V, "speaker"):
        try:
            return int(V.speaker())
        except Exception:
            pass
    try:
        v = int(_cfg("tts_speaker_id", 0) or 0)
    except (TypeError, ValueError):
        return 0
    return v if v >= 0 else 0


def _synthesise(text: str, *, start_better: bool = True,
                mouth: Optional[list] = None, plain: bool = False) -> tuple:
    """The sound for `text`, and nothing else - no timing row, nothing
    remembered: (samples | None, sample_rate, engine, voice, fallback, note,
    failed). say() is this plus its bookkeeping; jarvis_voice_flow makes the
    "One moment." clip with it.

    A custom voice first (jarvis_voices.py, since 2026-09-24). None means
    the built-in voice is the one chosen; a result without audio means the
    custom voice could not be used, and says why - then Kokoro speaks.
    `start_better=False` never STARTS the better voice's program on the
    second card for this sound (it is used if it is already running).
    `mouth`: a list that receives the Kokoro mouth shapes' payload (say()
    only; kokoro_speak) - nothing is added for a custom voice.
    `plain=True` (say(), for a crisis answer - plain_voice_now): the
    built-in voice without the face's animal voice and pitch rise. A custom
    voice the owner chose still speaks first, as always."""
    voice, fallback, note = "builtin", "", ""
    try:
        import jarvis_voices
    except Exception:
        jarvis_voices = None
    if jarvis_voices is not None:
        try:
            if not start_better and _takes(jarvis_voices.speak, "start_better"):
                custom = jarvis_voices.speak(text, start_better=False)
            else:
                custom = jarvis_voices.speak(text)
        except Exception as exc:
            custom = None
            fallback = f"the custom voice failed ({type(exc).__name__})"
        if custom is not None:
            voice, note = custom.voice, custom.note
            if custom.ok:
                return (custom.samples, custom.sample_rate, custom.engine, voice, "",
                        note, "")
            fallback = custom.why
    engine = _tts_engine()
    if engine is None:
        return None, 0, "none", voice, fallback, note, "no Kokoro voice is installed"
    try:
        # The animal's pitch rise (tts_pitch) is 0 unless "Voice follows the
        # face" speaks for an animal face - and never for a crisis answer
        # (`plain`), which the owner's own built-in voice says.
        # (`plain` is passed only when set, so a stand-in tts_voice with the
        # older one-argument shape still works for every other sentence.)
        voice_now = tts_voice(jarvis_voices, plain=True) if plain else tts_voice(jarvis_voices)
        audio = kokoro_speak(engine, text, *voice_now, mouth=mouth)
    except Exception:
        return None, 0, "none", voice, fallback, note, "Kokoro failed"
    if audio is None:
        return None, 0, "none", voice, fallback, note, "Kokoro made no sound"
    return audio[0], audio[1], "kokoro", voice, fallback, note, ""


# --------------------------------------------------------------------------
#   jarvis_voice_flow.py: interrupting by talking, the delay, "One moment."
# --------------------------------------------------------------------------

SOURCE_BARGE_IN = "barge_in"
#: hear() takes `waited_ms` (voice-flow.patch checks this before passing it).
TAKES_WAIT = True


def _flow(name: str, *args, **kwargs):
    """Calls jarvis_voice_flow.<name>, or None when that file is missing or
    the call fails - the delay is bookkeeping, and bookkeeping must never be
    the reason a voice turn fails."""
    try:
        import jarvis_voice_flow
        return getattr(jarvis_voice_flow, name)(*args, **kwargs)
    except Exception:
        return None


def barge_in(raw: bytes, mic: str = "") -> dict:
    """POST /api/voice/utterance?source=barge_in: "should Jarvis stop
    talking?" - `{"stop": bool, "available": bool, "why", "reason", ...}`,
    never words. jarvis_voice_flow.barge_in says how it decides. Without
    that file the answer is always "do not stop"."""
    try:
        import jarvis_voice_flow
    except Exception:
        return {"stop": False, "available": False, "source": SOURCE_BARGE_IN,
                "why": "not_installed", "seconds": 0.0, "ms": 0.0,
                "reason": "jarvis_voice_flow.py is not in the backend folder"}
    return jarvis_voice_flow.barge_in(raw, mic=mic)


def moment_reply() -> tuple:
    """GET /api/voice/moment -> (200, WAV bytes) or (503, {"available":
    false, "error", "why"}). The "One moment." clip in the voice in use now."""
    try:
        import jarvis_voice_flow
    except Exception:
        return 503, {"available": False, "error": "the \"One moment.\" clip is not installed "
                     "on this PC", "why": "jarvis_voice_flow.py is not in the backend folder"}
    got = jarvis_voice_flow.moment()
    if got.get("ok") and got.get("wav"):
        return 200, got["wav"]
    return 503, {"available": False, "error": "no \"One moment.\" clip right now",
                 "why": str(got.get("why") or "")}


def _flow_status(voice: Optional[dict] = None) -> dict:
    """status()'s `flow` block; the same shape, all off, without the file."""
    got = _flow("status", voice=voice)
    if isinstance(got, dict):
        return got
    why = "jarvis_voice_flow.py is not in the backend folder"
    return {"available": False,
            "barge_in": {"enabled": False, "available": False, "why": why, "min_seconds": 0.0,
                         "bar": "", "stop_word": False},
            "moment": {"enabled": False, "text": "", "key": "", "ready": False, "voice": "",
                       "engine": "", "seconds": None, "after_ms": 0, "why": why},
            "warm": {"enabled": False, "state": "off", "seconds": None, "steps": {}},
            "timings": [], "summary": []}


# --------------------------------------------------------------------------
#   How long say() took - numbers only, in memory
# --------------------------------------------------------------------------

#: The last say() calls, newest last: which engine spoke, how many
#: characters, how long it took to make the sound, and how long the sound
#: lasts. Never the text. Read by status() (tts.timings),
#: jarvis_voices.status() and `python jarvis_voices.py --time`, and by
#: whatever later works on cutting the delay before Jarvis speaks.
TIMINGS_KEPT = 20
_TIMINGS: list = []
_TIMINGS_LOCK = threading.Lock()


def _note_timing(engine: str, voice: str, text: str, t0: float, audio_seconds: float,
                 fallback: str = "", note: str = "", failed: str = "") -> None:
    """One row. `engine`: "kokoro", "zipvoice", "f5", or "none" (nothing was
    said - `failed` says why). `fallback`: why the chosen custom voice was
    not used, when it was not. `seconds`: from say() being called to the
    sound being ready, loading included - what a listener waits."""
    took = time.monotonic() - t0
    row = {"at": int(time.time()), "engine": engine, "voice": voice, "chars": len(text),
           "seconds": round(took, 3), "audio_seconds": round(audio_seconds, 3),
           "rtf": round(took / audio_seconds, 3) if audio_seconds > 0 else None,
           "fallback": str(fallback or "")[:300], "note": str(note or "")[:300],
           "failed": str(failed or "")[:300]}
    with _TIMINGS_LOCK:
        _TIMINGS.append(row)
        del _TIMINGS[:-TIMINGS_KEPT]


def say_timings() -> list:
    """Copies of the timing rows, oldest first."""
    with _TIMINGS_LOCK:
        return [dict(r) for r in _TIMINGS]


def _mouth_status() -> dict:
    got = _mouth("status")
    if isinstance(got, dict):
        return got
    return {"available": False, "made": 0, "skipped": 0, "last_skip_why": "", "last_ms": None,
            "status": "jarvis_mouth.py is not in the backend folder: the apps work the "
                      "mouth out from the sound"}


def _custom_voice_brief() -> dict:
    try:
        import jarvis_voices
        return jarvis_voices.brief()
    except Exception:
        return {"active": "builtin", "name": "Built-in voice", "engine": "kokoro",
                "fallback": ""}


def _self_test() -> int:
    """`python jarvis_speech.py --test`: speaks a sentence with the installed
    voice, then hears it back with the installed speech-to-text - the owner
    check is skipped for this one clip ONLY because the clip is Jarvis's own
    synthetic voice, made here, never a recording. Prints what it heard and
    where it saved the WAV. Nothing is sent anywhere."""
    sentence = "Hey Jarvis, what is the weather like tomorrow?"
    print(f"1. Speaking: {sentence!r}")
    t = time.time()
    wav = say(sentence)
    if not wav:
        print("   No voice: the Kokoro files are not installed (see status below).")
        return 1
    out = _config_dir() / "voice" / "self-test.wav"
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(wav)
    except OSError:
        out = None
    print(f"   ok, {len(wav)} bytes in {time.time() - t:.1f} s"
          + (f" - saved to {out}" if out else ""))
    samples, sr = _read_wav(wav)
    if jarvis_wakeword is not None:
        s = jarvis_wakeword.spot(samples, sr)
        print(f"2. Wake word: {'HEARD' if s.heard else 'not heard'} "
              f"(score {s.score:.2f}, needs {s.threshold:.2f})" if s.ran
              else f"2. Wake word: cannot listen - {s.why}")
    print("3. Speech-to-text:")
    if _stt_engine() is None:
        print("   No speech-to-text: " + _stt_state()[2])
        return 1
    t = time.time()
    heard = _transcribe(samples, sr)
    print(f"   heard {heard!r} in {time.time() - t:.1f} s")
    return 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        code = _self_test()
        print()
    else:
        code = 0
    for k, v in status().items():
        print(f"  {k:<28} {v}")
    raise SystemExit(code)
