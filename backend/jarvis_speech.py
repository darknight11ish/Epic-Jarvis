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
    jarvis_speech.say(text)                -> bytes | None  (a WAV)
    jarvis_speech.set_wake_enabled(bool)   -> {"ok": bool, ...}

ORDER MATTERS, and this is the one invariant that must never move: `hear()`
verifies the SPEAKER through `jarvis_voice` before it ever runs speech-to-
text. "A voice that is not the owner's is never turned into words - refusing
after transcribing would leave a stranger's speech in memory on the way to
saying no" (the same comment already lives beside the route that calls this).
The safe failure is to say nothing back, not to say something quietly wrong.

Engine: sherpa-onnx, per docs/ARCHITECTURE.md §11 ("Decisions already
taken... sherpa-onnx for everything - STT, speaker verification, wake word,
Kokoro TTS, Silero VAD. 0 GB VRAM"). Speaker verification already lives in
`jarvis_voice.py`, rebuilt in an earlier pass; this file adds the other two:
speech-to-text and text-to-speech.

A DISAGREEMENT WORTH RECORDING RATHER THAN SILENTLY RESOLVING:
`jarvis-framework.toml`'s own `[voice]` section - the real, checked-in
config schema - reads

    stt_engine = "faster-whisper"
    stt_model = "small.en"

which is a different STT engine than the one this file implements, and
neither `faster_whisper` nor `openwakeword` (named in that section's own
comment as the wake-word engine) is installed anywhere this was written or
tested. Only `sherpa_onnx` is confirmed present. Rather than overwrite the
existing `stt_engine`/`stt_model` keys - which would silently break whatever
already reads them, and would be guessing at a reconciliation nobody asked
for - this file adds its OWN keys (`sherpa_stt_model`, `sherpa_stt_tokens`,
...) and only engages when `stt_engine = "sherpa-onnx"` is set explicitly.
Until that line is added to the TOML, `status()` says so plainly rather than
pretending to be the active engine. `tts_engine` has no such conflict - the
TOML has no TTS section at all - so it defaults to `"sherpa-onnx"` outright.

WHAT IS NOT HERE: model files. No STT model, no Kokoro voice, no Silero VAD
weight ships in this repository - they are tens to hundreds of megabytes of
binary ONNX assets, the kind of thing `backend/README.md` already says does
not belong in a patch stack. Every engine here is constructed lazily, on
first real use, from paths read out of `[voice]`; a missing or corrupt file
raises a real, caught `RuntimeError` (confirmed against the installed
`sherpa_onnx` package: pointing any of its three model configs at a
nonexistent path raises `RuntimeError`, it does not hang or abort the
process) and the caller gets an honest "not available" rather than a crash.

WHAT IS DELIBERATELY LEFT OUT: whether flipping `wake_word_enabled` should
first pass through the approval gate. The route comment above the wake-word
call says turning it on "is gated as change_own_config, because widening
where Jarvis listens is a change to its exposure and not a preference" - but
`jarvis_gate.py`'s real `check()`/`decide()` signature is not visible
anywhere in this repository (confirmed: every patch that touches it shows
only call sites, never a `def`), and guessing at it would be exactly the kind
of invented interface this project's own rules exist to prevent. So
`set_wake_enabled()` here takes effect immediately, in its own small state
file, the moment it is called - it does not queue an approval. Wiring a real
gate check in front of it is left for whoever holds `jarvis_gate.py`'s actual
source, the same gap already recorded for the secret-scan and denial-
constraint features in `backend/README.md`.
"""
from __future__ import annotations

import io
import json
import os
import threading
import time
import wave
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

try:
    import jarvis_framework as fw
except Exception:
    fw = None  # type: ignore

try:
    import jarvis_voice
except Exception:
    jarvis_voice = None  # type: ignore

try:
    import numpy as np
except Exception:
    np = None  # type: ignore

try:
    import sherpa_onnx
except Exception:
    sherpa_onnx = None  # type: ignore


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
                or (Path.home() / ".openjarvis"))


def _models_dir() -> Path:
    return _config_dir() / "voice-models"


def _wake_state_path() -> Path:
    return _config_dir() / "voice" / "wake_override.json"


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
#   Speech-to-text: sherpa-onnx SenseVoice. Lazy, cached, never crashes the
#   caller on a missing or corrupt model.
# --------------------------------------------------------------------------

_UNSET = object()
_LOCK = threading.RLock()
_stt_cache = _UNSET
_tts_cache = _UNSET


def _sherpa_stt_paths():
    default_dir = _models_dir() / "stt"
    model = str(_cfg("sherpa_stt_model", "") or default_dir / "model.onnx")
    tokens = str(_cfg("sherpa_stt_tokens", "") or default_dir / "tokens.txt")
    return model, tokens


def _build_stt_engine():
    if sherpa_onnx is None or str(_cfg("stt_engine", "faster-whisper")) != "sherpa-onnx":
        return None
    model, tokens = _sherpa_stt_paths()
    try:
        return sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=model,
            tokens=tokens,
            num_threads=1,
            use_itn=bool(_cfg("sherpa_stt_use_itn", True)),
            language=str(_cfg("sherpa_stt_language", "") or ""),
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
#   Text-to-speech: sherpa-onnx Kokoro.
# --------------------------------------------------------------------------

def _sherpa_tts_paths():
    default_dir = _models_dir() / "tts"
    return {
        "model": str(_cfg("tts_model", "") or default_dir / "model.onnx"),
        "voices": str(_cfg("tts_voices", "") or default_dir / "voices.bin"),
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
        model_cfg = sherpa_onnx.OfflineTtsModelConfig(kokoro=kokoro, num_threads=1)
        return sherpa_onnx.OfflineTts(sherpa_onnx.OfflineTtsConfig(model=model_cfg))
    except Exception:
        return None


def _tts_engine():
    global _tts_cache
    with _LOCK:
        if _tts_cache is _UNSET:
            _tts_cache = _build_tts_engine()
        return _tts_cache


def reload_engines() -> None:
    """Drop the cached STT/TTS engines so a config change - a new model path
    - takes effect on the next call rather than needing a restart. Mirrors
    `jarvis_framework.reload_framework()`; INFERRED, no surviving call site,
    same reasoning: something has to be able to act on a change without a
    restart, and nothing here does that automatically."""
    global _stt_cache, _tts_cache
    with _LOCK:
        _stt_cache = _tts_cache = _UNSET


# --------------------------------------------------------------------------
#   The wake-word switch: its own tiny state file, deliberately NOT the
#   framework TOML - see the module docstring for why writing there is out
#   of scope here.
# --------------------------------------------------------------------------

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


def set_wake_enabled(enabled: bool) -> dict:
    """Turns wake-word capture on or off, effective immediately.

    See the module docstring: this is NOT routed through an approval gate,
    because `jarvis_gate.py`'s real interface cannot be seen from here to be
    called correctly. It IS the owner's own explicit action reaching this
    function at all - the HTTP route already requires a valid pairing token
    - so "immediate" here is "as fast as any other setting toggle", not "no
    check happened".
    """
    p = _wake_state_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"enabled": bool(enabled), "set_at": time.time()}),
                     encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return {"ok": True, "enabled": bool(enabled)}


# --------------------------------------------------------------------------
#   status()
# --------------------------------------------------------------------------

def _files_present(*paths: str) -> bool:
    return all(p and Path(p).is_file() for p in paths)


def status() -> dict:
    """What the voice loop can actually do right now. Never overstates - a
    listed capability the owner then finds does not work is worse than one
    honestly reported missing."""
    voice = jarvis_voice.status() if jarvis_voice is not None else {
        "enabled": False, "mode": "owner", "enrolled": False, "samples": 0,
        "threshold": 0.35, "embedder": "none", "speaker_model": False,
        "note": "jarvis_voice is not importable here",
    }

    stt_engine_name = str(_cfg("stt_engine", "faster-whisper"))
    stt_wanted_sherpa = stt_engine_name == "sherpa-onnx"
    stt_model, stt_tokens = _sherpa_stt_paths()
    stt_files_ok = _files_present(stt_model, stt_tokens)

    tts_engine_name = str(_cfg("tts_engine", "sherpa-onnx"))
    tts_paths = _sherpa_tts_paths()
    tts_files_ok = _files_present(tts_paths["model"], tts_paths["voices"],
                                   tts_paths["tokens"])

    notes = []
    if voice.get("note"):
        notes.append(voice["note"])
    if not stt_wanted_sherpa:
        notes.append(
            f"stt_engine is {stt_engine_name!r} in jarvis-framework.toml; "
            "this module only speaks sherpa-onnx. Set stt_engine = "
            "\"sherpa-onnx\" and point sherpa_stt_model/sherpa_stt_tokens at "
            "a real model to turn on local transcription.")
    elif not stt_files_ok:
        notes.append(f"sherpa-onnx STT is selected but its model files are "
                      f"not on disk yet (looked for {stt_model} and "
                      f"{stt_tokens}).")
    if tts_engine_name == "sherpa-onnx" and not tts_files_ok:
        notes.append("Kokoro TTS model files are not on disk yet (looked "
                      f"under {Path(tts_paths['model']).parent}).")

    return {
        **voice,
        "stt_engine": stt_engine_name,
        "stt_available": stt_wanted_sherpa and stt_files_ok,
        "tts_engine": tts_engine_name,
        "tts_available": tts_engine_name == "sherpa-onnx" and tts_files_ok,
        "wake_word_enabled": _wake_enabled(),
        "wake_phrase": _cfg("wake_phrase", "hey_jarvis"),
        # The route's own comment explains why: a client that transcribed
        # locally would send text, and the owner-voice gate would have
        # nothing left to check.
        "local_stt_on_client_allowed": False,
        "note": " ".join(notes),
    }


# --------------------------------------------------------------------------
#   hear() / say()
# --------------------------------------------------------------------------

@dataclass
class Heard:
    is_owner: bool
    text: str = ""
    score: float = 0.0
    threshold: float = 0.0
    available: bool = True
    source: str = "push_to_talk"
    reason: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def hear(raw: bytes, source: str = "push_to_talk") -> Heard:
    """One complete WAV utterance in. Never transcribes before the speaker
    is checked - see the module docstring for why that order is load-
    bearing, not a style choice."""
    parsed = _read_wav(raw)
    if parsed is None:
        return Heard(False, source=source, available=False,
                      reason="could not read that as a 16-bit PCM WAV clip")
    samples, sample_rate = parsed

    if jarvis_voice is None:
        return Heard(False, source=source, available=False,
                      reason="jarvis_voice is not importable; refusing "
                             "rather than skipping the owner check")

    try:
        embedder = jarvis_voice.EcapaEmbedder()
    except Exception:
        embedder = jarvis_voice.Embedder()
    verdict = jarvis_voice.verify(samples, embedder)

    if not verdict.is_owner:
        return Heard(False, score=verdict.score, threshold=verdict.threshold,
                     source=source, reason=verdict.reason)

    if _stt_engine() is None:
        return Heard(True, score=verdict.score, threshold=verdict.threshold,
                     source=source, available=False,
                     reason="that was you, but no speech-to-text model is "
                            "installed here yet - see jarvis_speech.status()")

    try:
        text = _transcribe(samples, sample_rate)
    except Exception as exc:
        return Heard(True, score=verdict.score, threshold=verdict.threshold,
                     source=source, available=False,
                     reason=f"transcription failed ({type(exc).__name__})")

    return Heard(True, text=text, score=verdict.score,
                 threshold=verdict.threshold, source=source)


def say(text: str) -> Optional[bytes]:
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
    engine = _tts_engine()
    if engine is None:
        return None
    try:
        audio = engine.generate(
            text,
            sid=int(_cfg("tts_speaker_id", 0) or 0),
            speed=float(_cfg("tts_speed", 1.0) or 1.0),
        )
    except Exception:
        return None
    if audio is None or len(audio.samples) == 0:
        return None
    return _write_wav(audio.samples, audio.sample_rate)


if __name__ == "__main__":
    for k, v in status().items():
        print(f"  {k:<28} {v}")
