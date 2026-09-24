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
    jarvis_speech.set_wake_enabled(bool)   -> {"ok": bool, ...}

ORDER MATTERS, and this is the one invariant that must never move: `hear()`
verifies the SPEAKER through `jarvis_voice` before it ever runs speech-to-
text. "A voice that is not the owner's is never turned into words - refusing
after transcribing would leave a stranger's speech in memory on the way to
saying no" (the same comment already lives beside the route that calls this).
The safe failure is to say nothing back, not to say something quietly wrong.

The whole order, since 2026-09-23 (each step can only refuse, never add):

    1. read the WAV                      bad file        -> refused
    2. Silero VAD: is there speech?      only noise      -> refused, nothing else runs
    3. wake word (source=wake_word only): is it switched on, and is
       "hey Jarvis" in the clip?         no              -> refused, not checked, not transcribed
       (once "Train my voice" has built it, the owner's own verifier
       has the last word here - jarvis_wakeword.py, "THE OWNER'S OWN")
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
                or os.environ.get("JARVIS_CONFIG_DIR")
                or (Path.home() / ".openjarvis"))


def _models_dir() -> Path:
    return _config_dir() / "voice-models"


def _wake_state_path() -> Path:
    return _config_dir() / "voice" / "wake_override.json"


def _threads(key: str) -> int:
    try:
        return max(1, min(8, int(_cfg(key, 2))))
    except (TypeError, ValueError):
        return 2


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

def _vad_path() -> str:
    return str(_cfg("vad_model", "") or (_models_dir() / "vad" / "silero_vad.onnx"))


def _vad_wanted() -> bool:
    return bool(_cfg("vad_enabled", True))


def _build_vad_config():
    if sherpa_onnx is None or not _vad_wanted() or not Path(_vad_path()).is_file():
        return None
    try:
        cfg = sherpa_onnx.VadModelConfig(
            silero_vad=sherpa_onnx.SileroVadModelConfig(
                model=_vad_path(), threshold=0.5, min_silence_duration=0.25,
                min_speech_duration=0.1, window_size=512),
            sample_rate=16000, num_threads=1)
        # Built once here so a broken file shows up now, not mid-request.
        sherpa_onnx.VoiceActivityDetector(cfg, buffer_size_in_seconds=1)
        return cfg
    except Exception:
        return None


def _vad_config():
    global _vad_cache
    with _LOCK:
        if _vad_cache is _UNSET:
            _vad_cache = _build_vad_config()
        return _vad_cache


#: Kept either side of the speech the VAD found, so a soft first consonant
#: or a trailing "s" is not cut off.
VAD_PAD_SECONDS = 0.3


def _speech_span(samples, sample_rate: int):
    """(start, end) in samples of `samples` holding speech, None when the
    VAD found none, or "skip" when there is no VAD to ask."""
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
        model_cfg = sherpa_onnx.OfflineTtsModelConfig(
            kokoro=kokoro, num_threads=_threads("tts_threads"))
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
    """Drop the cached STT/TTS/VAD engines (and the wake-word models) so a
    config change - a new model path - takes effect on the next call rather
    than needing a restart."""
    global _stt_cache, _tts_cache, _vad_cache
    with _LOCK:
        _stt_cache = _tts_cache = _vad_cache = _UNSET
    if jarvis_wakeword is not None:
        jarvis_wakeword.reload()
    try:
        import jarvis_turn
        jarvis_turn.reload()
    except Exception:
        pass


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
            left = max(0, int(_WAKE_PENDING["since"] + _WAKE_PENDING["timeout"] - time.time()))
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
        _WAKE_PENDING = {"id": pid, "since": time.time(), "timeout": _wake_timeout(),
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
            out["expires_in"] = max(0, int(p["since"] + p["timeout"] - time.time()))
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
# --------------------------------------------------------------------------

_AWAKE_LOCK = threading.Lock()
_AWAKE_UNTIL = 0.0


def _awake_seconds() -> float:
    try:
        return max(2.0, min(30.0, float(_cfg("awake_timeout_s", 8))))
    except (TypeError, ValueError):
        return 8.0


def _open_awake() -> float:
    global _AWAKE_UNTIL
    secs = _awake_seconds()
    with _AWAKE_LOCK:
        _AWAKE_UNTIL = time.monotonic() + secs
    return secs


def _take_awake() -> bool:
    """True, once, if a window is open - and closes it."""
    global _AWAKE_UNTIL
    with _AWAKE_LOCK:
        live = time.monotonic() < _AWAKE_UNTIL
        _AWAKE_UNTIL = 0.0
    return live


def _close_awake() -> None:
    global _AWAKE_UNTIL
    with _AWAKE_LOCK:
        _AWAKE_UNTIL = 0.0


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
    """gate.strictness / privacy / settings / models / cohort / repeat, from
    jarvis_voice.status(); the strict defaults, and `models` saying nothing
    is known, for a jarvis_voice.py older than them. Never raises."""
    st = voice.get("settings") if isinstance(voice.get("settings"), dict) else {}
    strict = str(voice.get("strictness") or "very_strict")
    return {
        "strictness": strict,
        "privacy": str(voice.get("privacy") or "private_on_screen"),
        "settings": st or {"strictness": strict, "privacy": "private_on_screen",
                           "voice_is_enough_allowed": strict == "very_strict",
                           "min_command_seconds": 0.0},
        "models": voice.get("models") if isinstance(voice.get("models"), dict) else {},
        "cohort": voice.get("cohort") if isinstance(voice.get("cohort"), dict) else {},
        "repeat": voice.get("repeat") if isinstance(voice.get("repeat"), dict) else {},
    }


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

    Cheap: file checks only. No model is loaded to answer this.

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

    vad_file = Path(_vad_path()).is_file()
    vad_ok = vad_file and _vad_wanted() and sherpa_onnx is not None
    if not _vad_wanted():
        vad_status = "switched off ([voice] vad_enabled = false)"
    elif not vad_file:
        vad_status = f"not installed (looked for {_vad_path()})"
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
        },
        "vad": {"engine": "silero (sherpa-onnx)", "available": vad_ok,
                "status": vad_status},
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
        },
        "audio_in": dict(AUDIO_IN),
        # "Finished, or only paused?" - see _turn_state().
        "turn": _turn_state(),
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
    }


# --------------------------------------------------------------------------
#   hear() / say()
# --------------------------------------------------------------------------

SOURCE_WAKE_WORD = "wake_word"

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
    #: The strictness the voice was checked at: "very_strict" or "balanced"
    #: ("" when no check ran).
    strictness: str = ""
    #: May an answer that draws on email, calendar, notes or memory be READ
    #: ALOUD for this request? (jarvis_voice.may_speak, from the owner's
    #: "private answers" setting.) False: show such an answer on screen only.
    private_aloud: bool = False
    #: The words asked about something private (the router's private-topic
    #: backstop). A hint for the app, not a guarantee - see JARVIS-API.md.
    question_private: bool = False

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


def _too_short_reason(spoken: float, need: float) -> str:
    return (f"that was too short to be sure it was you ({spoken:.1f} seconds of "
            f"speech; a command needs at least {need:.1f}) - say a little more")


def hear(raw: bytes, source: str = "push_to_talk", mic: str = "") -> Heard:
    """One complete WAV utterance in. Never transcribes before the speaker
    is checked - see the module docstring for the whole order and why it is
    load-bearing, not a style choice.

    `mic`: "phone" or "desktop" (anything else counts as none named) - the
    clip is checked against that microphone's own voice print, and its own
    "hey Jarvis" verifier, falling back as jarvis_voice.lookup_order says."""
    mic = str(mic or "").strip().lower()
    if mic not in ("phone", "desktop"):
        mic = ""
    parsed = _read_wav(raw)
    if parsed is None:
        return Heard(False, source=source, available=False,
                      reason="could not read that as a 16-bit PCM WAV clip")
    samples, sample_rate = parsed
    seconds = round(len(samples) / float(sample_rate or 16000), 2)
    wake = source == SOURCE_WAKE_WORD

    # 2. Is there any speech at all? Silero VAD, when installed. A cough, a
    #    door, the fan: refused here, before anything else looks at it.
    span = _speech_span(samples, sample_rate)
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
    spot = None
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
        if _take_awake():
            via_window = True
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

    # 3b. Long enough to be sure it is the owner? (2026-09-24.) A speaker
    #     model has little to go on in a second of speech, so a command
    #     that short is refused HERE - before the owner check, never
    #     transcribed - and the owner is asked to say a little more. The one
    #     exception is a "hey Jarvis" clip, which is the wake path, not a
    #     command: it may open the listening window (step 6), and nothing
    #     more - a command inside a clip that short is refused after all.
    if short and (not wake or via_window):
        _note_short(mic)
        return Heard(False, source=source, seconds=seconds, too_short=True,
                     min_seconds=need, reason=_too_short_reason(spoken, need))

    if jarvis_voice is None:
        return Heard(False, source=source, available=False, seconds=seconds,
                      reason="jarvis_voice is not importable; refusing "
                             "rather than skipping the owner check")

    # 4. The owner check.
    try:
        embedder = jarvis_voice.EcapaEmbedder()
    except Exception:
        embedder = jarvis_voice.Embedder()
    # The real sample rate goes with the clip. Both clients send 16 kHz now,
    # but an older desktop (before 2026-09-24) sent its microphone's own
    # rate, and the speaker model resamples when told it.
    # Only to a jarvis_voice.py that takes it - an older copy on the PC
    # would raise TypeError here, and this call is not wrapped.
    kw = {}
    if _takes_rate(jarvis_voice.verify):
        kw["sample_rate"] = sample_rate
    if mic and _takes(jarvis_voice.verify, "mic"):
        kw["mic"] = mic
    verdict = jarvis_voice.verify(samples, embedder, **kw)
    common = dict(score=verdict.score, threshold=verdict.threshold,
                  source=source, mode=verdict.mode, seconds=seconds,
                  wake_score=spot.score if spot else 0.0,
                  voice_print=str(getattr(verdict, "voice_print", "") or ""),
                  strictness=str(getattr(verdict, "strictness", "") or ""),
                  private_aloud=_private_aloud())

    if not verdict.is_owner:
        return Heard(False, reason=verdict.reason, **common)

    if _stt_engine() is None:
        return Heard(True, available=False, wake_heard=wake,
                     reason="that was you, but no speech-to-text model is "
                            "installed here yet - see jarvis_speech.status()",
                     **common)

    # 5. The words.
    try:
        text = _transcribe(samples, sample_rate)
    except Exception as exc:
        return Heard(True, available=False, wake_heard=wake,
                     reason=f"transcription failed ({type(exc).__name__})",
                     **common)
    engine = f"{STT_ENGINE}:{_stt_files()[0]}"

    if not wake or via_window:
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
        secs = _open_awake()
        return Heard(True, text="", engine=engine, wake_heard=True, awake=True,
                     awake_seconds=secs, reason="listening", **common)
    if short:
        # "Hey Jarvis" was allowed through as the wake path only (step 3b);
        # a command in a clip this short is not taken.
        _note_short(mic)
        return Heard(True, text="", engine=engine, wake_heard=True, too_short=True,
                     min_seconds=need, reason=_too_short_reason(spoken, need), **common)
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
