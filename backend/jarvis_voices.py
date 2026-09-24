"""jarvis_voices.py - custom voices: Jarvis speaking in a voice you recorded.

NEW MODULE, shipped whole beside jarvis_hud.py (apply-patches.ps1 copies it).
`voices.patch` adds the routes that call it; `jarvis_speech.say()` asks it
first, before the built-in Kokoro voice.

WHAT IT DOES, in plain words. The owner (or someone with their permission)
records 3-10 seconds of a person reading a sentence Jarvis shows, or uploads a
clip and types exactly what is said in it. After an approval card, the clip
is kept on this PC and Jarvis can speak in that voice. Two engines make the
voice:

    ZipVoice   (sherpa-onnx, on the PROCESSOR). Always the one used first.
               Model files in <config dir>/voice-models/zipvoice/.
    F5-TTS     (PyTorch, on the SECOND graphics card). Better, optional, OFF
               by default: the "better voice" switch. Its own process
               (jarvis_f5_worker.py), started only when Jarvis is about to
               speak in a custom voice, stopped after idle minutes, in
               standby and when the switch goes off. While it loads, ZipVoice
               speaks in the same voice - never silence.

If the custom voice is missing, fails or is too slow, say() uses the normal
Kokoro voice and status() says why (`fallback`).

THE ROUTES (voices.patch):

    GET  /api/voice/voices           status()
    POST /api/voice/voices/create    {"name", "clip": "<base64 WAV>", "transcript"}
    POST /api/voice/voices/active    {"voice": "<id>" | "builtin"}
    POST /api/voice/voices/delete    {"voice": "<id>"}
    POST /api/voice/voices/better    {"enabled": true | false}

THE PERMISSION MODEL (docs/ARCHITECTURE.md section 3). Creating a voice and
switching Jarvis to one each raise ONE approval card through jarvis_gate,
action `custom_voice`, tier "ask" (checked before the card and again on the
answer; only "ask" + "approved" does anything). Switching back to the
built-in voice and deleting a voice are immediate: both only narrow what
Jarvis does. The better-voice switch is its own action,
`better_voice_enable`, the same shape as the second card's switches: ON is a
card, OFF is immediate. Nothing here auto-approves (rule 4).

WHERE THE AUDIO GOES (rule 1). Nowhere. The uploaded clip is held in this
process's memory until the card is answered; approved, it is written to
<config dir>/voices/<id>/ (clip.wav - mono, 24 kHz, 16-bit - transcript.txt
and voice.json); denied, timed out or refused, it is dropped. There is no
network call in this module and none in jarvis_f5_worker.py
(test_voices.py scans both); the F5 process is spoken to through pipes, not a
port. The clip, the transcript and the text Jarvis speaks are never logged,
never put in an audit line, and never in an event.

THE SAFETY RULE (the owner's decision 4). A voice that sounds like the
OWNER's is refused: the clip is scored against every trained voice print
(jarvis_voice.py) and refused at or above that print's threshold minus a
margin ([voice] custom_voice_margin, 0.10). The reason is not vanity: Jarvis
speaking through the speakers in the owner's voice could pass its own "is it
the owner talking?" check. The check runs when the voice is created, when
Jarvis is switched to it, and again before the first word after any voice
print changes (a voice made before the owner trained a print is checked
against it the moment one exists).

Standard library plus numpy and sherpa-onnx (both already needed for voice).
Never prints except as a command-line tool (`python jarvis_voices.py --time`).
"""
from __future__ import annotations

import atexit
import base64
import binascii
import hashlib
import io
import json
import math
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid as _uuid
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

try:
    import jarvis_framework as fw
except Exception:
    fw = None  # type: ignore

try:
    import numpy as np
except Exception:
    np = None  # type: ignore

try:
    import sherpa_onnx
except Exception:
    sherpa_onnx = None  # type: ignore


# --------------------------------------------------------------------------
#   Constants
# --------------------------------------------------------------------------

#: The gate action for creating a voice and for switching Jarvis to one.
ACTION = "custom_voice"
#: The gate action for the better voice (F5-TTS on the second card).
BETTER_ACTION = "better_voice_enable"
#: The built-in voice's id. Never a folder name.
BUILTIN = "builtin"
BUILTIN_NAME = "Built-in voice"

#: What a stored clip is: mono, 24 kHz (both engines' own rate), 16-bit.
SAMPLE_RATE = 24000
#: Seconds of SPEECH, after silence at either end is trimmed.
MIN_SECONDS = 3.0
MAX_SECONDS = 10.0
#: The WAV as sent, before base64. jarvis_hud's MAX_BODY is 4 MB and base64
#: adds a third, so a bigger clip could not arrive anyway.
MAX_CLIP_BYTES = 2_900_000
#: Quieter than this at its loudest is a microphone that recorded nothing.
MIN_PEAK = 0.02
MAX_TRANSCRIPT = 300
MAX_NAME = 40
MAX_VOICES = 20
#: The words must fit the recording: fewer than this many words a second is
#: a transcript of something else (or of half the clip).
MIN_WORDS_PER_SECOND = 0.5
MAX_WORDS_PER_SECOND = 8.0

#: The safety margin under a voice print's threshold (see the docstring).
OWNER_MARGIN = 0.10
#: The owner check also scores every 3-second stretch of the clip, at 16 kHz.
WINDOW = 3 * 16000
#: ZipVoice counts as "too slow" when it takes more than this many seconds to
#: make each second of speech ("RTF", real-time factor) on SLOW_RUN calls in a
#: row. Then the built-in voice is used for SLOW_PAUSE_SECONDS, and status
#: says why. [voice] custom_voice_max_rtf changes it. Measured here (a busy
#: 4-core container, not the owner's PC): 0.4 to 3.0, depending on how busy
#: the machine was - so this is a guess until the owner's timing line has run.
MAX_RTF = 1.5
SLOW_RUN = 3
SLOW_PAUSE_SECONDS = 600.0

#: F5-TTS. NOT MEASURED: nothing in this project has run F5-TTS on a graphics
#: card. The model is ~336 million numbers (1.35 GB as fp32), plus the
#: vocoder, plus PyTorch's own CUDA start-up; 3 GB is a guess with room, to be
#: replaced by what nvidia-smi says on the owner's PC.
F5_NEED_MB = 3072
F5_IDLE_MINUTES = 10
F5_LOAD_SECONDS = 300.0
F5_CALL_SECONDS = 60.0
F5_RETRY_SECONDS = 300.0
F5_MODEL = "F5TTS_v1_Base"
F5_CHECKPOINT = "model_1250000.safetensors"

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")

#: Sentences for the owner to read when recording, shown by the apps. Short
#: enough for 3-10 seconds, with most English sounds in them. The transcript
#: sent back must be the sentence read, exactly.
SENTENCES = (
    "Good morning. I checked your calendar, and you have two meetings this afternoon.",
    "The quick brown fox jumps over the lazy dog, then runs back home for dinner.",
    "It is a bright, cool day, with a gentle breeze coming in from the sea.",
    "Your parcel arrived at noon, and I left a reminder to open it this evening.",
    "Would you like me to read that again, a little more slowly this time?",
)


class BadInput(ValueError):
    """Something the person has to fix. The message is shown as it is."""


# --------------------------------------------------------------------------
#   Things the tests replace
# --------------------------------------------------------------------------

_popen = subprocess.Popen


def _mono() -> float:
    return time.monotonic()


def _spawn(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="jarvis-voices", daemon=True).start()


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


# --------------------------------------------------------------------------
#   Settings and places
# --------------------------------------------------------------------------

def _cfg(key: str, default=None):
    """`[voice]`, the section jarvis_speech and jarvis_voice read."""
    if fw is None:
        return default
    try:
        return (fw.load_framework().get("voice") or {}).get(key, default)
    except Exception:
        return default


def _num(key: str, default: float, lo: float, hi: float) -> float:
    try:
        v = float(_cfg(key, default))
    except (TypeError, ValueError):
        return default
    return v if math.isfinite(v) and lo <= v <= hi else default


def _config_dir() -> Path:
    if fw is not None and getattr(fw, "CONFIG_DIR", None):
        return Path(fw.CONFIG_DIR)
    return Path(os.environ.get("OPENJARVIS_CONFIG_DIR")
                or os.environ.get("JARVIS_CONFIG_DIR")
                or (Path.home() / ".openjarvis"))


def voices_dir() -> Path:
    """<config dir>/voices - one folder per voice, plus state.json."""
    return _config_dir() / "voices"


def _state_path() -> Path:
    return voices_dir() / "state.json"


def _models_dir() -> Path:
    return _config_dir() / "voice-models"


def _owner_margin() -> float:
    return _num("custom_voice_margin", OWNER_MARGIN, 0.0, 0.5)


def _max_rtf() -> float:
    return _num("custom_voice_max_rtf", MAX_RTF, 0.1, 10.0)


def _f5_idle_minutes() -> int:
    return int(_num("f5_idle_minutes", F5_IDLE_MINUTES, 1, 240))


def _speed() -> float:
    return _num("tts_speed", 1.0, 0.5, 2.0)


def _audit(event: str, detail: dict) -> None:
    """Counts, ids and outcomes only - never audio, a transcript or text."""
    try:
        if fw is not None:
            fw.audit_log(event, detail)
    except Exception:
        pass


def _publish(data: dict) -> None:
    """A `voices` event, so both apps read the status again. No names, no
    words: {"what", "outcome"} only."""
    try:
        import jarvis_events
        jarvis_events.BUS.publish("voices", data)
    except Exception:
        pass


def _tier(action: str) -> str:
    return str(fw.action_tier(action)) if fw is not None else "unknown"


def _gate(action: str, detail: dict, prompt: str):
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def _timeout() -> float:
    try:
        return float(fw.load_framework().get("autonomy", {})
                     .get("approval_timeout_seconds", 180))
    except Exception:
        return 180.0


# --------------------------------------------------------------------------
#   The owner's switches: which voice, and the better voice
# --------------------------------------------------------------------------

_STATE_LOCK = threading.RLock()


def _read_state() -> dict:
    """{"active": id, "better_voice": bool}. Missing or broken is the
    built-in voice and the better voice off - the safe reading."""
    out = {"active": BUILTIN, "better_voice": False}
    try:
        raw = json.loads(_state_path().read_text(encoding="utf-8"))
    except Exception:
        return out
    if not isinstance(raw, dict):
        return out
    a = raw.get("active")
    if isinstance(a, str) and (a == BUILTIN or _ID_RE.match(a)):
        out["active"] = a
    out["better_voice"] = raw.get("better_voice") is True
    return out


def _write_state(**changes) -> Optional[str]:
    """None on success, else the error in words."""
    with _STATE_LOCK:
        cur = _read_state()
        cur.update(changes)
        p = _state_path()
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_name(p.name + ".tmp")
            tmp.write_text(json.dumps({**cur, "set_at": int(time.time())}, indent=1),
                           encoding="utf-8")
            tmp.replace(p)
        except OSError as exc:
            return f"could not save the setting ({type(exc).__name__})"
    return None


# --------------------------------------------------------------------------
#   Audio: WAV in, mono 24 kHz out
# --------------------------------------------------------------------------

def _need_numpy() -> None:
    if np is None:
        raise BadInput("numpy is not installed in the Python that runs Jarvis, so "
                       "recordings cannot be read (py -3 -m pip install numpy)")


def decode_wav(raw: bytes):
    """(float32 mono samples, sample rate), or BadInput with the reason.
    16- or 24-bit PCM, 8-48 kHz, one or two channels."""
    _need_numpy()
    if not raw:
        raise BadInput("the recording is empty - record it again")
    if len(raw) > MAX_CLIP_BYTES:
        raise BadInput(f"the recording is too big ({len(raw) / 1e6:.1f} MB; at most "
                       f"{MAX_CLIP_BYTES / 1e6:.1f} MB). Keep it to {MAX_SECONDS:g} seconds, "
                       f"mono if you can")
    try:
        with wave.open(io.BytesIO(raw), "rb") as w:
            rate, width, chans = w.getframerate(), w.getsampwidth(), w.getnchannels()
            frames = w.readframes(w.getnframes())
    except (wave.Error, EOFError, ValueError, OSError):
        raise BadInput("that is not a WAV recording Jarvis can read - save it as a "
                       "16-bit WAV file and try again") from None
    if width not in (2, 3):
        raise BadInput(f"the recording is {width * 8}-bit; save it as a 16-bit WAV file")
    if chans not in (1, 2):
        raise BadInput(f"the recording has {chans} channels; save it as mono or stereo")
    if not 8000 <= rate <= 48000:
        raise BadInput(f"the recording is {rate} Hz; use 16,000 to 48,000 Hz")
    if width == 2:
        n = len(frames) // 2 * 2
        x = np.frombuffer(frames[:n], dtype="<i2").astype(np.float32) / 32768.0
    else:
        n = len(frames) // 3 * 3
        b = np.frombuffer(frames[:n], dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        v = np.where(v & 0x800000, v - 0x1000000, v)
        x = v.astype(np.float32) / 8388608.0
    if chans == 2:
        x = x[: len(x) // 2 * 2].reshape(-1, 2).mean(axis=1)
    return x.astype(np.float32), int(rate)


def resample(x, rate: int, to: int):
    """Band-limited resampling by Fourier transform: exact for a clip this
    short, and needs nothing beyond numpy."""
    if rate == to or len(x) == 0:
        return np.asarray(x, dtype=np.float32)
    n_out = max(1, int(round(len(x) * to / float(rate))))
    spec = np.fft.rfft(np.asarray(x, dtype=np.float64))
    out = np.zeros(n_out // 2 + 1, dtype=np.complex128)
    k = min(len(spec), len(out))
    out[:k] = spec[:k]
    y = np.fft.irfft(out, n_out) * (n_out / float(len(x)))
    return y.astype(np.float32)


def trim(x, rate: int):
    """Silence off both ends (20 ms frames quieter than -45 dBFS), keeping
    0.15 s either side of the speech."""
    frame = max(1, int(rate * 0.02))
    n = len(x) // frame
    if n == 0:
        return x[:0]
    rms = np.sqrt(np.mean(np.square(x[: n * frame].reshape(n, frame)), axis=1))
    loud = np.nonzero(rms > 10 ** (-45 / 20.0))[0]
    if len(loud) == 0:
        return x[:0]
    pad = int(0.15 * rate)
    start = max(0, int(loud[0]) * frame - pad)
    end = min(len(x), (int(loud[-1]) + 1) * frame + pad)
    return x[start:end]


def normalise(raw: bytes):
    """A recording as sent -> (mono 24 kHz float32 samples, seconds), or
    BadInput. What is stored, and what both engines are given."""
    x, rate = decode_wav(raw)
    x = trim(x, rate)
    if len(x) == 0 or float(np.max(np.abs(x))) < MIN_PEAK:
        raise BadInput("the recording is silent - check the microphone and record it again")
    seconds = len(x) / float(rate)
    if seconds < MIN_SECONDS:
        raise BadInput(f"the recording has {seconds:.1f} seconds of speech; it needs at "
                       f"least {MIN_SECONDS:g} - read the whole sentence")
    if seconds > MAX_SECONDS:
        raise BadInput(f"the recording has {seconds:.1f} seconds of speech; the most is "
                       f"{MAX_SECONDS:g} - use a shorter piece")
    y = np.clip(resample(x, rate, SAMPLE_RATE), -1.0, 1.0).astype(np.float32)
    return y, round(len(y) / float(SAMPLE_RATE), 2)


def wav_bytes(samples, rate: int) -> bytes:
    pcm = (np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0) * 32767.0).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(rate))
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


# --------------------------------------------------------------------------
#   Names, transcripts, ids
# --------------------------------------------------------------------------

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def clean_name(v) -> str:
    if not isinstance(v, str):
        raise BadInput("give the voice a name")
    s = " ".join(_CONTROL.sub(" ", v).split())
    if not s:
        raise BadInput("give the voice a name")
    if len(s) > MAX_NAME:
        raise BadInput(f"the name is {len(s)} characters; the most is {MAX_NAME}")
    if any(c in s for c in "/\\<>\"`"):
        raise BadInput("the name cannot have / \\ < > \" or ` in it")
    return s


def clean_transcript(v) -> str:
    if not isinstance(v, str):
        raise BadInput("type exactly what is said in the recording")
    s = " ".join(_CONTROL.sub(" ", v).split())
    if not re.search(r"\w", s):
        raise BadInput("type exactly what is said in the recording")
    if len(s) > MAX_TRANSCRIPT:
        raise BadInput(f"the words are {len(s)} characters; the most is {MAX_TRANSCRIPT}")
    return s


_WORD = re.compile(r"[぀-ヿ㐀-鿿가-힯]|[^\W぀-ヿ㐀-鿿가-힯]+")


def count_words(text: str) -> int:
    """Words, with each Chinese, Japanese or Korean character counted as one
    (those are written without spaces, and one character is about one
    syllable - close enough for "do the words fit the recording?")."""
    return len(_WORD.findall(text))


def id_for(name: str, taken=()) -> str:
    """A folder-safe id from the name: lower case letters, digits, dashes."""
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:28].strip("-")
    if not base or base == BUILTIN:
        base = "voice"
    vid, n = base, 2
    while vid in taken or vid == BUILTIN:
        vid = f"{base}-{n}"
        n += 1
    return vid


def _voice_path(vid: str) -> Optional[Path]:
    """The voice's folder, only for a well-formed id, and only inside
    voices_dir()."""
    if not isinstance(vid, str) or vid == BUILTIN or not _ID_RE.match(vid):
        return None
    root = voices_dir().resolve()
    p = (root / vid).resolve()
    if p.parent != root:
        return None
    return p


# --------------------------------------------------------------------------
#   Voices on disk
# --------------------------------------------------------------------------

@dataclass
class Voice:
    id: str
    name: str
    transcript: str
    seconds: float
    created: float
    folder: Path
    check: dict = field(default_factory=dict)

    @property
    def clip(self) -> Path:
        return self.folder / "clip.wav"


def load_voice(vid: str) -> Optional[Voice]:
    p = _voice_path(vid)
    if p is None or not (p / "clip.wav").is_file():
        return None
    try:
        meta = json.loads((p / "voice.json").read_text(encoding="utf-8"))
        transcript = (p / "transcript.txt").read_text(encoding="utf-8").strip()
    except Exception:
        return None
    if not isinstance(meta, dict) or not transcript:
        return None
    return Voice(id=vid, name=str(meta.get("name") or vid)[:MAX_NAME],
                 transcript=transcript[:MAX_TRANSCRIPT],
                 seconds=float(meta.get("seconds") or 0.0),
                 created=float(meta.get("created") or 0.0), folder=p,
                 check=meta.get("owner_check") if isinstance(meta.get("owner_check"), dict)
                 else {})


def _ids_on_disk() -> list:
    try:
        return sorted(d.name for d in voices_dir().iterdir()
                      if d.is_dir() and _ID_RE.match(d.name))
    except OSError:
        return []


def list_voices() -> list:
    """Every folder in voices/, readable or not (an unreadable one says why)."""
    out = []
    for vid in _ids_on_disk():
        v = load_voice(vid)
        if v is None:
            out.append({"id": vid, "name": vid, "builtin": False, "ready": False,
                        "why": "its recording or its words are missing from "
                               f"{voices_dir() / vid}; delete it and add it again"})
        else:
            out.append({"id": v.id, "name": v.name, "builtin": False, "ready": True,
                        "why": "", "seconds": v.seconds, "created": int(v.created),
                        "transcript": v.transcript})
    return out


_CLIP_CACHE: dict = {}      # vid -> (mtime_ns, samples)
_CLIP_LOCK = threading.Lock()


def _clip_samples(v: Voice):
    """The stored clip as float32 at 24 kHz, read once per file version."""
    try:
        mt = v.clip.stat().st_mtime_ns
    except OSError:
        return None
    with _CLIP_LOCK:
        hit = _CLIP_CACHE.get(v.id)
        if hit and hit[0] == mt:
            return hit[1]
    try:
        x, rate = decode_wav(v.clip.read_bytes())
    except (BadInput, OSError):
        return None
    if rate != SAMPLE_RATE:
        x = resample(x, rate, SAMPLE_RATE)
    with _CLIP_LOCK:
        _CLIP_CACHE[v.id] = (mt, x)
    return x


def _write_voice(vid: str, name: str, transcript: str, samples, seconds: float,
                 check: dict) -> None:
    """Writes the voice into a temporary folder, then renames it into place,
    so a half-written voice never appears. Raises OSError."""
    root = voices_dir()
    root.mkdir(parents=True, exist_ok=True)
    final = _voice_path(vid)
    if final is None:
        raise OSError("bad voice id")
    tmp = root / f".{vid}.{_uuid.uuid4().hex[:8]}.tmp"
    tmp.mkdir()
    try:
        (tmp / "clip.wav").write_bytes(wav_bytes(samples, SAMPLE_RATE))
        (tmp / "transcript.txt").write_text(transcript + "\n", encoding="utf-8")
        (tmp / "voice.json").write_text(json.dumps({
            "id": vid, "name": name, "seconds": seconds, "sample_rate": SAMPLE_RATE,
            "created": time.time(), "owner_check": check}, indent=1), encoding="utf-8")
        tmp.rename(final)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


def _save_check(v: Voice, check: dict) -> None:
    try:
        p = v.folder / "voice.json"
        meta = json.loads(p.read_text(encoding="utf-8"))
        meta["owner_check"] = check
        tmp = p.with_name("voice.json.tmp")
        tmp.write_text(json.dumps(meta, indent=1), encoding="utf-8")
        tmp.replace(p)
    except Exception:
        pass
    v.check = check


# --------------------------------------------------------------------------
#   Is it the owner's voice?
# --------------------------------------------------------------------------

def _voice_mod():
    import jarvis_voice
    return jarvis_voice


def _embedder(V):
    """The same choice jarvis_speech.hear() makes, so scores mean the same."""
    try:
        return V.EcapaEmbedder()
    except Exception:
        return V.Embedder()


def _embed(V, emb, x16):
    fn = getattr(V, "_embed", None)
    if fn is not None:
        return fn(emb, x16, 16000)
    return emb.embed(x16)


def prints_fingerprint() -> str:
    """Changes whenever a voice print, or the speaker model, changes - the
    cue to check every custom voice again."""
    try:
        V = _voice_mod()
        paths = [p for _, p in V.lookup_order("")]
        try:
            paths.append(V.speaker_model_path())
        except Exception:
            pass
    except Exception:
        return "no-voice-check"
    parts = []
    for p in paths:
        try:
            st = Path(p).stat()
            parts.append(f"{p}|{st.st_mtime_ns}|{st.st_size}")
        except OSError:
            parts.append(f"{p}|-")
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:16]


def owner_check(samples, margin: Optional[float] = None) -> dict:
    """Does this 24 kHz clip sound like the OWNER? Scored against every
    trained voice print, each at its own threshold minus the margin.

    {"ok": True} means "not the owner's voice as far as the prints can tell"
    - it may be used. {"ok": False, "why": ...} refuses, and every path that
    cannot compare against a print that could be compared refuses too."""
    margin = _owner_margin() if margin is None else float(margin)
    fp = prints_fingerprint()
    try:
        V = _voice_mod()
    except Exception:
        return {"ok": False, "refused": "no_voice_check", "fingerprint": fp,
                "why": ("the voice check (jarvis_voice.py) is not installed on this PC, so "
                        "Jarvis cannot make sure this is not your own voice")}
    profs = []
    for label, path in V.lookup_order(""):
        try:
            prof = V.load_profile(path)
        except Exception:
            prof = None
        if prof is not None:
            profs.append((label, prof))
    if not profs:
        return {"ok": True, "checked": 0, "fingerprint": fp, "prints": [],
                "why": ("your own voice has not been trained yet, so there was nothing to "
                        "compare with. It is checked again as soon as you train it")}
    try:
        x16 = resample(np.asarray(samples, dtype=np.float32), SAMPLE_RATE, 16000)
        emb = _embedder(V)
        # The whole clip, and every 3-second stretch of it (half overlapping):
        # a voice print is trained on short sentences, and the fallback voice
        # check in particular reads a clip differently by its length. The
        # HIGHEST score counts, so this only ever refuses more.
        pieces = [x16] + [x16[i:i + WINDOW] for i in
                          range(0, max(0, len(x16) - WINDOW) + 1, WINDOW // 2)]
        vecs = []
        for piece in pieces:
            vec = [float(v) for v in (_embed(V, emb, piece) or [])]
            if vec and all(math.isfinite(v) for v in vec):
                vecs.append(vec)
    except Exception as exc:
        return {"ok": False, "refused": "owner_check_failed", "fingerprint": fp,
                "why": (f"the recording could not be compared with your voice print "
                        f"({type(exc).__name__}), so it was refused")}
    if not vecs:
        return {"ok": False, "refused": "owner_check_failed", "fingerprint": fp,
                "why": ("the recording could not be compared with your voice print (too "
                        "quiet or too short), so it was refused")}
    name = str(getattr(emb, "name", ""))
    rows = []
    for label, prof in profs:
        usable = [v for v in vecs if len(v) == len(prof.centroid)]
        if (prof.embedder and prof.embedder != name) or not usable:
            rows.append({"print": label, "compared": False})
            continue
        score = max(float(V.cosine(v, prof.centroid)) for v in usable)
        bar = round(max(float(getattr(V, "MIN_THRESHOLD", 0.05)),
                        float(prof.threshold) - margin), 4)
        rows.append({"print": label, "compared": True, "score": round(score, 4),
                     "threshold": float(prof.threshold), "bar": bar,
                     "match": bool(score >= bar)})
    compared = [r for r in rows if r["compared"]]
    matched = [r for r in compared if r["match"]]
    if matched:
        r = max(matched, key=lambda r: r["score"] - r["bar"])
        where = {"general": "", "phone": "phone ", "desktop": "PC "}.get(r["print"], "")
        return {"ok": False, "refused": "owner_voice", "fingerprint": fp, "prints": rows,
                "score": r["score"], "bar": r["bar"],
                "why": (f"this recording sounds too much like YOUR voice (it scored "
                        f"{r['score']:.2f} against your {where}voice print; anything from "
                        f"{r['bar']:.2f} up is refused). Jarvis will not speak in your voice: "
                        f"its own speech through the speakers could then pass the check that "
                        f"makes sure it is you talking. Use a recording of someone else")}
    if not compared:
        return {"ok": True, "checked": 0, "fingerprint": fp, "prints": rows,
                "why": ("your voice print was made with a different voice check than the one "
                        "installed now, so it could not be compared. It is checked again as "
                        "soon as you train your voice again")}
    top = max(compared, key=lambda r: r["score"])
    return {"ok": True, "checked": len(compared), "fingerprint": fp, "prints": rows,
            "score": top["score"], "bar": top["bar"],
            "why": (f"it does not sound like your voice (its closest score was "
                    f"{top['score']:.2f}; {top['bar']:.2f} or more is refused)")}


def _current_check(v: Voice, check: Optional[Callable] = None) -> dict:
    """The voice's owner check, run again if the voice prints have changed
    since it was last run."""
    fp = prints_fingerprint()
    if v.check.get("fingerprint") == fp and "ok" in v.check:
        return v.check
    samples = _clip_samples(v)
    if samples is None:
        return {"ok": False, "why": "its recording could not be read"}
    chk = (check or owner_check)(samples)
    _save_check(v, {k: chk[k] for k in ("ok", "why", "fingerprint", "score", "bar",
                                         "checked", "refused") if k in chk})
    return chk


# --------------------------------------------------------------------------
#   ZipVoice, on the processor (sherpa-onnx)
# --------------------------------------------------------------------------

def zipvoice_dir() -> Path:
    return Path(str(_cfg("zipvoice_dir", "") or (_models_dir() / "zipvoice")))


def _glob1(d: Path, pattern: str, prefer: str = "int8") -> str:
    try:
        hits = sorted(d.glob(pattern))
    except OSError:
        hits = []
    for h in hits:
        if prefer in h.name:
            return str(h)
    return str(hits[0]) if hits else str(d / pattern.replace("*", ""))


def zipvoice_files() -> dict:
    d = zipvoice_dir()
    return {"tokens": str(d / "tokens.txt"), "encoder": _glob1(d, "encoder*.onnx"),
            "decoder": _glob1(d, "decoder*.onnx"), "vocoder": _glob1(d, "vocos*.onnx"),
            "data_dir": str(d / "espeak-ng-data"), "lexicon": str(d / "lexicon.txt")}


def zipvoice_state() -> tuple:
    """(available, why) from file checks only - nothing is loaded."""
    if sherpa_onnx is None:
        return False, ("the sherpa-onnx package is not installed in the Python that runs "
                       "Jarvis (py -3 -m pip install sherpa-onnx)")
    if not hasattr(sherpa_onnx, "OfflineTtsZipvoiceModelConfig"):
        return False, ("this sherpa-onnx has no ZipVoice (1.13.8 has it; that is the version "
                       "this was tested with): "
                       "py -3 -m pip install --upgrade sherpa-onnx")
    f = zipvoice_files()
    missing = [k for k in ("tokens", "encoder", "decoder", "vocoder") if not Path(f[k]).is_file()]
    if not Path(f["data_dir"]).is_dir():
        missing.append("espeak-ng-data")
    if missing:
        return False, (f"the ZipVoice model files are not on this PC yet (missing "
                       f"{', '.join(missing)} in {zipvoice_dir()}); backend/README.md, "
                       f"\"Custom voices\", has the one-line install")
    return True, "ready"


_ZIP = {"engine": None, "why": "", "built": False}
_ZIP_LOCK = threading.Lock()       # building, and one generate() at a time


def _zipvoice():
    """(engine, why). Built once, on first use."""
    with _ZIP_LOCK:
        if _ZIP["built"]:
            return _ZIP["engine"], _ZIP["why"]
        ok, why = zipvoice_state()
        eng = None
        if ok:
            f = zipvoice_files()
            try:
                zc = sherpa_onnx.OfflineTtsZipvoiceModelConfig(
                    tokens=f["tokens"], encoder=f["encoder"], decoder=f["decoder"],
                    vocoder=f["vocoder"], data_dir=f["data_dir"],
                    lexicon=f["lexicon"] if Path(f["lexicon"]).is_file() else "")
                mc = sherpa_onnx.OfflineTtsModelConfig(
                    zipvoice=zc, num_threads=int(_num("zipvoice_threads", 4, 1, 16)))
                eng = sherpa_onnx.OfflineTts(sherpa_onnx.OfflineTtsConfig(model=mc))
                why = "ready"
            except Exception as exc:
                eng, why = None, f"ZipVoice could not be loaded ({type(exc).__name__})"
        _ZIP.update(engine=eng, why=why, built=True)
        return eng, why


def reload() -> None:
    """Forget the loaded ZipVoice (a new model folder takes effect next call)."""
    with _ZIP_LOCK:
        _ZIP.update(engine=None, why="", built=False)
    with _CLIP_LOCK:
        _CLIP_CACHE.clear()


_SLOW = {"rtfs": [], "until": -1e9, "why": ""}
_SLOW_LOCK = threading.Lock()


def _note_speed(rtf: float) -> None:
    with _SLOW_LOCK:
        _SLOW["rtfs"] = (_SLOW["rtfs"] + [rtf])[-SLOW_RUN:]
        if len(_SLOW["rtfs"]) == SLOW_RUN and all(r > _max_rtf() for r in _SLOW["rtfs"]):
            _SLOW["until"] = _mono() + SLOW_PAUSE_SECONDS
            _SLOW["why"] = (f"the custom voice was too slow on this PC (the last {SLOW_RUN} "
                            f"times it took {', '.join(f'{r:.1f}' for r in _SLOW['rtfs'])} "
                            f"seconds for each second of speech), so the built-in voice is "
                            f"used for {int(SLOW_PAUSE_SECONDS // 60)} minutes before it is "
                            f"tried again")
            _SLOW["rtfs"] = []


def _slow_now() -> str:
    with _SLOW_LOCK:
        return _SLOW["why"] if _mono() < _SLOW["until"] else ""


class Unavailable(RuntimeError):
    """The custom voice cannot speak; the message says why, in words."""


#: ZipVoice makes a whole piece of text in one go, sized from the recording:
#: its working memory grows with the square of the length. A long answer is
#: therefore made a few sentences at a time. (Seen here: a transcript that
#: did not match its recording made it ask for 48 GB and fail.)
CHUNK_CHARS = 200
_SENTENCE_END = re.compile(r"(?<=[.!?;:。！？])\s+|\n+")


def chunks(text: str, limit: int = CHUNK_CHARS) -> list:
    """The text in pieces of at most about `limit` characters, cut at the
    ends of sentences (or, for one very long sentence, at spaces)."""
    out, cur = [], ""
    for sent in (s.strip() for s in _SENTENCE_END.split(text)):
        if not sent:
            continue
        while len(sent) > limit:
            cut = sent.rfind(" ", 0, limit)
            cut = cut if cut > limit // 3 else limit
            piece, sent = sent[:cut].strip(), sent[cut:].strip()
            if cur:
                out.append(cur)
                cur = ""
            out.append(piece)
        if cur and len(cur) + 1 + len(sent) > limit:
            out.append(cur)
            cur = sent
        else:
            cur = f"{cur} {sent}".strip()
    if cur:
        out.append(cur)
    return out


def zipvoice_generate(text: str, v: Voice, speed: float = 1.0):
    """(samples, sample_rate, seconds taken). Raises Unavailable(why) when it
    cannot run; anything else the engine raises is passed on."""
    eng, why = _zipvoice()
    if eng is None:
        raise Unavailable(why)
    prompt = _clip_samples(v)
    if prompt is None:
        raise Unavailable(f"the recording for \"{v.name}\" could not be read")
    steps = int(_num("zipvoice_steps", 4, 1, 32))
    prompt_list = prompt.tolist()
    parts, rate, took = [], SAMPLE_RATE, 0.0
    for piece in chunks(text):
        with _ZIP_LOCK:
            t = _mono()
            audio = eng.generate(piece, v.transcript, prompt_list, SAMPLE_RATE,
                                 float(speed), steps)
            took += _mono() - t
        s = np.asarray(getattr(audio, "samples", []), dtype=np.float32)
        if s.size:
            rate = int(getattr(audio, "sample_rate", SAMPLE_RATE))
            if parts:
                parts.append(np.zeros(int(0.15 * rate), dtype=np.float32))
            parts.append(s)
    if not parts:
        raise Unavailable("ZipVoice made no sound for that text")
    return np.concatenate(parts), rate, took


# --------------------------------------------------------------------------
#   F5-TTS, the better voice, on the second card (jarvis_f5_worker.py)
# --------------------------------------------------------------------------

def f5_dir() -> Path:
    return Path(str(_cfg("f5_dir", "") or (_models_dir() / "f5-tts")))


def f5_files() -> dict:
    d = f5_dir()
    return {"checkpoint": str(d / F5_CHECKPOINT), "vocoder": str(d / "vocos")}


def _f5_files_state() -> tuple:
    f = f5_files()
    missing = []
    if not Path(f["checkpoint"]).is_file():
        missing.append(F5_CHECKPOINT)
    if not (Path(f["vocoder"]) / "config.yaml").is_file() or \
            not (Path(f["vocoder"]) / "pytorch_model.bin").is_file():
        missing.append("vocos/config.yaml and vocos/pytorch_model.bin")
    if missing:
        return False, (f"the F5-TTS model files are not on this PC yet (missing "
                       f"{', '.join(missing)} in {f5_dir()}); backend/README.md, "
                       f"\"The better voice\", has the install")
    return True, ""


def _second_card() -> dict:
    """{"capable", "why", "uuid", "name", "free_mb", "big_model"} - never raises."""
    out = {"capable": False, "why": "the second-card module is not installed",
           "uuid": None, "name": None, "free_mb": None, "big_model": None}
    try:
        import jarvis_second_card as sc
        det = sc.detect()
    except Exception:
        return out
    s = det.get("second") or {}
    out.update(capable=bool(det.get("capable")), why=str(det.get("why") or ""),
               uuid=s.get("uuid"), name=s.get("name"))
    for row in det.get("cards") or []:
        if s.get("uuid") and row.get("uuid") == s.get("uuid"):
            out["free_mb"] = row.get("free_mb")
    if out["uuid"]:
        try:
            held = sc.big_model_holds(out["uuid"], out["name"] or "second card")
        except Exception:
            held = None
        out["big_model"] = held
    return out


def _f5_python() -> list:
    p = str(_cfg("f5_python", "") or "").strip()
    return [p] if p else [sys.executable]


def _worker_command() -> list:
    """The F5 process's command line. Replaced in tests."""
    f = f5_files()
    return _f5_python() + [str(Path(__file__).with_name("jarvis_f5_worker.py")),
                           "--checkpoint", f["checkpoint"], "--vocoder", f["vocoder"],
                           "--model", F5_MODEL,
                           "--nfe", str(int(_num("f5_steps", 32, 4, 64)))]


def worker_env(uuid: str, base: Optional[dict] = None) -> dict:
    """What the F5 process inherits: an allowlist (jarvis_child_env.py), no
    token or key, the second card by its id and nothing else, and the
    Hugging Face libraries told they are offline (the model files are
    local; nothing is fetched)."""
    if not re.fullmatch(r"GPU-[0-9A-Fa-f-]{8,64}", str(uuid or "")):
        raise ValueError("a card is only ever chosen by its id (GPU-...)")
    try:
        import jarvis_child_env
        env = jarvis_child_env.inherited(base, prefixes=("CUDA_",))
    except Exception:
        env = {k: v for k, v in (base or os.environ).items()
               if k.upper() in ("PATH", "SYSTEMROOT", "TEMP", "TMP", "HOME", "USERPROFILE")}
    env.update({
        "CUDA_VISIBLE_DEVICES": uuid, "CUDA_DEVICE_ORDER": "PCI_BUS_ID",
        "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "HF_DATASETS_OFFLINE": "1",
        "HF_HUB_DISABLE_TELEMETRY": "1", "PYTHONUNBUFFERED": "1",
        "PYTHONIOENCODING": "utf-8",
    })
    return env


def _kill_tree(p) -> None:
    """Stops the F5 process this module started, and anything it started."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"],
                           capture_output=True, timeout=10)
        else:
            import signal
            try:
                os.killpg(os.getpgid(p.pid), signal.SIGTERM)
            except Exception:
                p.terminate()
        p.wait(timeout=10)
    except Exception:
        try:
            p.kill()
        except Exception:
            pass


_ASLEEP = {"on": False, "why": ""}


def sleep(why: str = "Jarvis is on standby") -> dict:
    """Standby: stop the F5 process, freeing the second card, and keep it
    stopped until Jarvis leaves standby. Custom voices keep working, on the
    processor (ZipVoice). {"stopped", "sentence"}. Never raises."""
    try:
        _ASLEEP.update(on=True, why=f"asleep: {why}")
        running = _F5.proc is not None or _F5.state in ("loading", "ready")
        if running:
            _F5.stop(_ASLEEP["why"])
        _audit("voices.f5.sleep", {"stopped": running})
        return {"stopped": running,
                "sentence": "The better voice was stopped too." if running else ""}
    except Exception as exc:
        return {"stopped": False,
                "sentence": f"Could not stop the better voice ({type(exc).__name__})."}


def wake() -> None:
    _ASLEEP.update(on=False, why="")


def _still_asleep() -> bool:
    """Asleep until Jarvis has left standby. A power module that cannot be
    read leaves it asleep: the safe side of a promise to free the card."""
    if not _ASLEEP["on"]:
        return False
    try:
        import jarvis_power
        if str(jarvis_power.current()) != "standby":
            wake()
            return False
    except Exception:
        pass
    return True


def f5_blocked(state: Optional[dict] = None) -> str:
    """Why the F5 process may not start now, in words; "" when it may."""
    st = state if state is not None else _read_state()
    if not st["better_voice"]:
        return "the better-voice switch is off"
    if _still_asleep():
        return "Jarvis is on standby, so the second graphics card is kept free"
    ok, why = _f5_files_state()
    if not ok:
        return why
    sc = _second_card()
    if not sc["capable"]:
        return f"no capable second graphics card: {sc['why']}"
    if sc["big_model"]:
        return f"not now: {sc['big_model']}"
    free = sc.get("free_mb")
    if isinstance(free, (int, float)) and free < F5_NEED_MB:
        return (f"the {sc['name']} has {free:,} MB free and the better voice needs about "
                f"{F5_NEED_MB:,} MB (an estimate, not measured); it tries again later")
    return ""


class _F5Engine:
    """The one F5 process this module started, or none. Talked to through
    its stdin and stdout - one JSON line each way per request, no port."""

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.call_lock = threading.Lock()
        self.state = "off"
        self.why = "not running - it starts when Jarvis speaks in a custom voice"
        self.proc = None
        self.lines: Optional[queue.Queue] = None
        self.gen = 0
        self.seq = 0
        self.last_used = 0.0
        self.failed_at = -1e9
        self.since: Optional[float] = None
        self.card: Optional[str] = None
        self.load_seconds: Optional[float] = None
        self.reaper = False

    def alive(self) -> bool:
        p = self.proc
        try:
            return p is not None and p.poll() is None
        except Exception:
            return False

    def _fail(self, why: str) -> None:
        self.state, self.why, self.failed_at = "failed", why, _mono()

    def ensure(self) -> None:
        """Start the process if it may run and is not running. Never waits
        for it to load."""
        with self.lock:
            if self.state in ("loading", "ready") and self.alive():
                return
            if self.state in ("loading", "ready") and not self.alive():
                code = self._exit_code()
                self._stop_proc()
                self._fail(f"the better voice stopped by itself (exit code {code}); it is "
                           f"tried again in {int(F5_RETRY_SECONDS // 60)} minutes")
                return
            blocked = f5_blocked()
            if blocked:
                # Not a failure: something the owner can see and change (the
                # switch, standby, the card's memory). Said as the reason.
                self.state, self.why = "off", blocked
                return
            if self.state == "failed" and _mono() - self.failed_at < F5_RETRY_SECONDS:
                return
            self._start()

    def _exit_code(self):
        try:
            return self.proc.poll()
        except Exception:
            return "unknown"

    def _start(self) -> None:
        sc = _second_card()
        try:
            env = worker_env(str(sc["uuid"] or ""))
        except ValueError as exc:
            return self._fail(str(exc))
        kwargs: dict = {"stdin": subprocess.PIPE, "stdout": subprocess.PIPE,
                        "stderr": subprocess.DEVNULL, "env": env, "text": True,
                        "encoding": "utf-8", "bufsize": 1}
        if os.name == "nt":
            kwargs["creationflags"] = 0x08000000 | 0x00000200
        else:
            kwargs["start_new_session"] = True
        try:
            self.proc = _popen(_worker_command(), **kwargs)
        except Exception as exc:
            self.proc = None
            return self._fail(f"the better voice could not be started ({type(exc).__name__})")
        self.gen += 1
        gen = self.gen
        self.lines = queue.Queue()
        self.card = sc["name"]
        self.state, self.since, self.load_seconds = "loading", time.time(), None
        self.last_used = _mono()
        self.why = (f"loading F5-TTS on the {sc['name']} - Jarvis speaks with ZipVoice, in "
                    f"the same voice, until it is ready")
        proc, lines = self.proc, self.lines
        threading.Thread(target=self._read, args=(proc, lines), daemon=True,
                         name="jarvis-f5-read").start()
        _spawn(lambda: self._wait_ready(gen, lines))
        if not self.reaper:
            self.reaper = True
            try:
                _start_reaper()
            except Exception:
                pass
        _audit("voices.f5.start", {"card": sc["name"]})

    @staticmethod
    def _read(proc, lines: queue.Queue) -> None:
        try:
            for line in proc.stdout:
                lines.put(line)
        except Exception:
            pass
        lines.put(None)

    def _wait_ready(self, gen: int, lines: queue.Queue) -> None:
        t0 = _mono()
        try:
            line = lines.get(timeout=F5_LOAD_SECONDS)
        except queue.Empty:
            line = ""
        with self.lock:
            if gen != self.gen or self.state != "loading":
                return
            msg = _parse_line(line)
            if msg.get("ready") is True:
                self.state, self.since = "ready", time.time()
                self.load_seconds = round(_mono() - t0, 1)
                self.last_used = _mono()
                self.why = (f"running on the {self.card}; it stops after "
                            f"{_f5_idle_minutes()} minutes with nothing to say")
                return
            if line is None or (line == "" and not self.alive()):
                why = "the better voice stopped while loading"
            elif line == "":
                why = (f"the better voice did not finish loading within "
                       f"{int(F5_LOAD_SECONDS)} seconds")
            else:
                why = "the better voice could not load: " + str(msg.get("error") or
                                                             "no reason given")[:200]
            self._stop_proc()
            self._fail(why + f"; it is tried again in {int(F5_RETRY_SECONDS // 60)} minutes")

    def speak(self, text: str, v: Voice, speed: float):
        """(samples, rate, seconds) or (None, why). Starts the process when
        needed and never waits for it to load."""
        self.ensure()
        if self.state != "ready":
            return None, self.why
        if not self.call_lock.acquire(timeout=0.5):
            return None, "the better voice was busy with another sentence"
        try:
            with self.lock:
                if self.state != "ready" or not self.alive():
                    return None, self.why
                self.seq += 1
                rid, proc, lines, gen = self.seq, self.proc, self.lines, self.gen
            req = {"id": rid, "text": text, "ref_audio": str(v.clip),
                   "ref_text": v.transcript, "speed": float(speed)}
            t = _mono()
            try:
                proc.stdin.write(json.dumps(req) + "\n")
                proc.stdin.flush()
            except Exception as exc:
                return self._broke(gen, f"the better voice could not be reached "
                                        f"({type(exc).__name__})")
            deadline = t + F5_CALL_SECONDS
            while True:
                left = deadline - _mono()
                if left <= 0:
                    return self._broke(gen, f"the better voice did not answer within "
                                            f"{int(F5_CALL_SECONDS)} seconds")
                try:
                    line = lines.get(timeout=left)
                except queue.Empty:
                    continue
                if line is None:
                    return self._broke(gen, "the better voice stopped by itself")
                msg = _parse_line(line)
                if msg.get("id") != rid:
                    continue            # an answer to a request that timed out earlier
                break
            took = _mono() - t
            self.last_used = _mono()
            if not msg.get("ok"):
                return None, ("the better voice failed on that sentence ("
                              + str(msg.get("error") or "no reason")[:60] + ")")
            try:
                pcm = base64.b64decode(str(msg.get("audio") or ""), validate=True)
                samples = np.frombuffer(pcm[: len(pcm) // 2 * 2], dtype="<i2") \
                    .astype(np.float32) / 32768.0
                rate = int(msg.get("sample_rate") or SAMPLE_RATE)
            except (binascii.Error, ValueError, TypeError):
                return None, "the better voice sent back something that is not audio"
            if samples.size == 0 or not 8000 <= rate <= 48000:
                return None, "the better voice made no sound for that text"
            return samples, rate, took
        finally:
            self.call_lock.release()

    def _broke(self, gen: int, why: str):
        with self.lock:
            if gen == self.gen:
                self._stop_proc()
                self._fail(why + f"; it is tried again in {int(F5_RETRY_SECONDS // 60)} minutes")
        return None, why

    def _stop_proc(self) -> None:
        p, self.proc = self.proc, None
        self.gen += 1
        self.card = None
        if p is None:
            return
        try:
            if p.poll() is None:
                try:
                    p.stdin.write(json.dumps({"cmd": "quit"}) + "\n")
                    p.stdin.flush()
                except Exception:
                    pass
                _kill_tree(p)
        except Exception:
            pass

    def stop(self, why: str) -> None:
        with self.lock:
            self._stop_proc()
            self.state, self.why, self.since = "off", why, None

    def check_idle(self, now: Optional[float] = None) -> bool:
        """Stops a ready process that has said nothing for the idle minutes,
        and any process whose switch went off. True if it stopped one."""
        now = _mono() if now is None else now
        with self.lock:
            if self.state not in ("loading", "ready") and self.proc is None:
                return False
            if not _read_state()["better_voice"]:
                self.stop("the better-voice switch is off")
                return True
            if _still_asleep():
                self.stop(_ASLEEP["why"])
                return True
            if self.state != "ready" or self.call_lock.locked():
                return False
            if now - self.last_used < _f5_idle_minutes() * 60:
                return False
            self.stop(f"stopped after {_f5_idle_minutes()} minutes with nothing to say, to "
                      f"free the second graphics card; it starts again when Jarvis next "
                      f"speaks in a custom voice")
            return True


def _parse_line(line) -> dict:
    try:
        out = json.loads(line) if line else {}
    except (TypeError, ValueError):
        return {}
    return out if isinstance(out, dict) else {}


_F5 = _F5Engine()


def _start_reaper() -> None:
    """The thread that stops an idle F5 process. Replaced in tests."""
    def loop():
        while True:
            _sleep(30)
            try:
                _F5.check_idle()
            except Exception:
                pass
    threading.Thread(target=loop, name="jarvis-f5-idle", daemon=True).start()


def shutdown() -> None:
    try:
        _F5.stop("Jarvis is shutting down")
    except Exception:
        pass


atexit.register(shutdown)


def f5_card() -> Optional[dict]:
    """The card the F5 process is on right now, or None. Reads only."""
    if _F5.state in ("loading", "ready") and _F5.card:
        return {"name": _F5.card, "state": _F5.state}
    return None


# --------------------------------------------------------------------------
#   speak() - what jarvis_speech.say() asks first
# --------------------------------------------------------------------------

@dataclass
class Spoken:
    """What speak() made. `samples` None: use the built-in voice, and `why`
    says why. `note`: something worth showing even though it worked (the
    better voice was still loading, say)."""
    voice: str = BUILTIN
    samples: object = None
    sample_rate: int = 0
    engine: str = ""
    seconds: float = 0.0
    why: str = ""
    note: str = ""

    @property
    def ok(self) -> bool:
        return self.samples is not None and len(self.samples) > 0


def speak(text: str, speed: Optional[float] = None, *,
          check: Optional[Callable] = None, start_better: bool = True) -> Optional[Spoken]:
    """None: the built-in voice is the one chosen - carry on as before.
    Otherwise a Spoken: with audio, use it; without, use the built-in voice
    because of `why`. Never raises for anything expected.

    `start_better=False` (the "One moment." clip, jarvis_voice_flow.py,
    made in the background): the better voice is used only if its program
    is already running and ready - that clip never STARTS it on the second
    card; ZipVoice makes it instead."""
    st = _read_state()
    vid = st["active"]
    if vid == BUILTIN:
        return None
    speed = _speed() if speed is None else float(speed)
    if np is None:
        return Spoken(voice=vid, why="numpy is not installed, so the custom voice cannot run")
    v = load_voice(vid)
    if v is None:
        return Spoken(voice=vid, why=(f"the custom voice \"{vid}\" is missing its recording "
                                      f"or its words (looked in {voices_dir() / vid})"))
    chk = _current_check(v, check)
    if not chk.get("ok"):
        return Spoken(voice=vid, why=f"the custom voice \"{v.name}\" is not used: "
                                     + str(chk.get("why") or "it failed the owner check"))
    note = ""
    if st["better_voice"] and (start_better or (_F5.state == "ready" and _F5.alive())):
        out = _F5.speak(text, v, speed)
        if out[0] is not None:
            samples, rate, took = out
            return Spoken(voice=vid, samples=samples, sample_rate=rate, engine="f5",
                          seconds=round(took, 3))
        note = "better voice not used: " + str(out[1])
    slow = _slow_now()
    if slow:
        return Spoken(voice=vid, why=slow, note=note)
    try:
        samples, rate, took = zipvoice_generate(text, v, speed)
    except Unavailable as exc:
        return Spoken(voice=vid, why=str(exc), note=note)
    except Exception as exc:
        return Spoken(voice=vid, why=f"the custom voice failed ({type(exc).__name__})",
                      note=note)
    audio = len(samples) / float(rate)
    if audio > 0:
        _note_speed(took / audio)
    return Spoken(voice=vid, samples=samples, sample_rate=rate, engine="zipvoice",
                  seconds=round(took, 3), note=note)


# --------------------------------------------------------------------------
#   Status
# --------------------------------------------------------------------------

def _timings() -> list:
    try:
        import jarvis_speech
        return list(jarvis_speech.say_timings())
    except Exception:
        return []


def _kokoro_state() -> tuple:
    """The built-in voice, by the same file checks jarvis_speech.status()
    makes (not by calling it: that would ask this module again)."""
    try:
        import jarvis_speech as S
        paths = S._sherpa_tts_paths()
        name = str(S._cfg("tts_engine", "sherpa-onnx"))
        ok = (name == "sherpa-onnx" and S.sherpa_onnx is not None
              and S._files_present(paths["model"], paths["voices"], paths["tokens"]))
    except Exception as exc:
        return False, f"jarvis_speech could not be read ({type(exc).__name__})"
    if ok:
        return True, "ready"
    return False, ("the built-in voice's Kokoro files are not on this PC yet (looked under "
                   f"{Path(paths['model']).parent})")


def _predict(st: dict, voices: list) -> tuple:
    """(engine the next sentence would use, why the built-in voice would be
    used instead, or ""). Cheap: file checks and what is already known."""
    vid = st["active"]
    if vid == BUILTIN:
        return "kokoro", ""
    row = next((r for r in voices if r["id"] == vid), None)
    if row is None or not row["ready"]:
        return "kokoro", (f"the custom voice \"{vid}\" is missing its recording or its words "
                          f"(looked in {voices_dir() / vid})")
    v = load_voice(vid)
    if v is not None and v.check and v.check.get("fingerprint") == prints_fingerprint() \
            and not v.check.get("ok"):
        return "kokoro", f"the custom voice \"{v.name}\" is not used: {v.check.get('why')}"
    if st["better_voice"] and _F5.state == "ready" and _F5.alive():
        return "f5", ""
    slow = _slow_now()
    if slow:
        return "kokoro", slow
    if _ZIP["built"]:
        return ("zipvoice", "") if _ZIP["engine"] is not None else ("kokoro", _ZIP["why"])
    ok, why = zipvoice_state()
    return ("zipvoice", "") if ok else ("kokoro", why)


def _better_row(st: dict) -> dict:
    blocked = f5_blocked(st) if st["better_voice"] else ""
    sc = _second_card()
    with _PENDING_LOCK:
        pending = _BPENDING.get("id") is not None and not _BPENDING.get("withdrawn")
        last = dict(_BLAST) if _BLAST else None
    if not sc["capable"]:
        can, why = False, f"needs a capable second graphics card: {sc['why']}"
    else:
        can, why = True, (f"F5-TTS on the {sc['name']}: a better copy of the custom voice. "
                          f"It starts when Jarvis speaks in a custom voice and stops after "
                          f"{_f5_idle_minutes()} idle minutes")
    files_ok, files_why = _f5_files_state()
    return {"enabled": st["better_voice"], "pending": pending, "can_turn_on": can,
            "why": why, "files": files_ok, "files_why": files_why,
            "state": _F5.state, "state_why": blocked or _F5.why,
            "card": sc["name"], "idle_minutes": _f5_idle_minutes(),
            "load_seconds": _F5.load_seconds, "need_mb": F5_NEED_MB,
            "need_mb_measured": False, "last": last}


def brief() -> dict:
    """For /api/voice/status's tts block: which voice, cheaply."""
    st = _read_state()
    voices = list_voices()
    engine, fallback = _predict(st, voices)
    name = BUILTIN_NAME
    for r in voices:
        if r["id"] == st["active"]:
            name = r["name"]
    return {"active": st["active"], "name": name, "engine": engine, "fallback": fallback}


def status() -> dict:
    """GET /api/voice/voices. Cheap: no model is loaded to answer this."""
    try:
        _F5.check_idle()
    except Exception:
        pass
    st = _read_state()
    voices = list_voices()
    engine, fallback = _predict(st, voices)
    k_ok, k_why = _kokoro_state()
    if _ZIP["built"]:
        z_ok, z_why = _ZIP["engine"] is not None, _ZIP["why"]
    else:
        z_ok, z_why = zipvoice_state()
    active_name = BUILTIN_NAME
    for r in voices:
        if r["id"] == st["active"]:
            active_name = r["name"]
    with _PENDING_LOCK:
        p = dict(_PENDING) if _PENDING else None
        last = dict(_LAST) if _LAST else None
    pending = None
    if p:
        pending = {"kind": p["kind"], "voice": p["voice"], "name": p["name"],
                   "expires_in": max(0, int(p["since"] + p["timeout"] - time.time()))}
    return {
        "available": True,
        "active": st["active"],
        "active_name": active_name,
        "speaking_with": engine,
        "fallback": fallback,
        "voices": [{"id": BUILTIN, "name": BUILTIN_NAME, "builtin": True, "ready": k_ok,
                    "why": "" if k_ok else k_why}] + voices,
        "engines": {
            "kokoro": {"available": k_ok, "why": "" if k_ok else k_why},
            "zipvoice": {"available": z_ok, "why": "" if z_ok else z_why,
                         "where": "this PC's processor"},
            "f5": {"available": _F5.state == "ready", "why": _F5.why,
                   "where": "the second graphics card"},
        },
        "better_voice": _better_row(st),
        "pending": pending,
        "last": last,
        "timings": _timings(),
        "sentences": list(SENTENCES),
        "limits": {"min_seconds": MIN_SECONDS, "max_seconds": MAX_SECONDS,
                   "max_clip_bytes": MAX_CLIP_BYTES, "max_transcript_chars": MAX_TRANSCRIPT,
                   "max_name_chars": MAX_NAME, "max_voices": MAX_VOICES},
    }


# --------------------------------------------------------------------------
#   The cards: create a voice, switch to a voice
# --------------------------------------------------------------------------

_PENDING_LOCK = threading.Lock()
#: The one voice card that may be waiting (create or switch), or {}.
_PENDING: dict = {}
_LAST: dict = {}
#: Switch cards withdrawn (the owner went back to the built-in voice, or
#: deleted the voice) while they waited. Approving one afterwards does nothing.
_WITHDRAWN: set = set()
#: The better-voice card: {"id", "since", "withdrawn"} and how the last ended.
_BPENDING: dict = {}
_BLAST: dict = {}


def _last_words(kind: str, name: str, outcome: str, reason: str) -> str:
    reason = str(reason or "").strip().rstrip(".")
    what = {"create": f"The voice \"{name}\"", "switch": f"Speaking in \"{name}\""}[kind]
    # Mid-sentence, only the first letter changes case - .lower() on the
    # whole phrase used to print the voice's own name in lower case too.
    mid = what[0].lower() + what[1:]
    if outcome == "created":
        return f"The voice \"{name}\" was added. Switch to it to hear it."
    if outcome == "switched":
        return f"Jarvis now speaks in \"{name}\"."
    if outcome == "denied":
        return f"You said no, so nothing changed ({mid} was not " \
               f"{'added' if kind == 'create' else 'turned on'})."
    if outcome == "timed_out":
        return "Nobody answered the card in time, so nothing changed."
    if outcome == "withdrawn":
        return ("You changed the voice while the card was waiting, so approving that card "
                "changed nothing.")
    return f"{what} was not {'added' if kind == 'create' else 'turned on'}: " \
           f"{reason or 'refused'}."


def _finish(pid: str, outcome: str, reason: str = "", request_id=None) -> dict:
    """Records how a voice card ended and DROPS ANY HELD AUDIO. Every card
    ends here."""
    with _PENDING_LOCK:
        p = _PENDING if _PENDING.get("id") == pid else {}
        kind, vid, name = p.get("kind", "create"), p.get("voice", ""), p.get("name", "")
        if p:
            p.pop("samples", None)
            _PENDING.clear()
        _WITHDRAWN.discard(pid)
        _LAST.clear()
        _LAST.update(kind=kind, voice=vid, outcome=outcome, at=int(time.time()),
                     why=_last_words(kind, name, outcome, reason))
        last = dict(_LAST)
    _audit("voices.decided", {"kind": kind, "outcome": outcome,
                              **({"request_id": request_id} if request_id else {})})
    _publish({"what": kind, "outcome": outcome})
    return last


def _verdict(v) -> tuple:
    """(outcome, reason, request_id) from a gate verdict, the same reading
    jarvis_voice_enroll uses: only tier "ask" + "approved" is a yes."""
    vtier = getattr(v, "tier", "unknown")
    allowed = getattr(v, "allowed", False) is True
    outcome = getattr(v, "outcome", None)
    if outcome is None:
        outcome = "approved" if (allowed and vtier == "ask") else "refused"
    rid = getattr(v, "request_id", None)
    if vtier != "ask":
        return "refused", (f"the gate answered at tier {vtier!r}, which is not a person "
                           f"saying yes"), rid
    if allowed and outcome == "approved":
        return "approved", "", rid
    if outcome in ("denied", "timed_out"):
        return outcome, "", rid
    return "refused", str(getattr(v, "reason", "refused"))[:200], rid


def _check_line(chk: dict) -> str:
    return "Checked against your own voice: " + str(chk.get("why") or "") + "."


def describe_create(name: str, vid: str, seconds: float, transcript: str, chk: dict) -> str:
    """The card for adding a voice. Every word from here; the transcript in
    full (it is what the voice will be built from); what saying no costs."""
    return (
        f"Add a voice called \"{name}\" that Jarvis can speak in?\n\n"
        f"The recording: {seconds:.1f} seconds, and the words said in it:\n\"{transcript}\"\n\n"
        f"If you say yes: the recording and those words are kept on this PC, in "
        f"{voices_dir() / vid}. Nothing is sent anywhere. Jarvis does not start speaking in "
        f"this voice yet - switching to it is its own card.\n\n"
        f"A copied voice sounds like a real person. Only add the voice of someone who has "
        f"agreed to it.\n\n"
        f"{_check_line(chk)}\n\n"
        f"If you did not just do this, say no.\n\n"
        f"If you say no: nothing is kept, and the recording is deleted.")


def describe_switch(v: Voice, current: str, chk: dict, st: dict) -> str:
    how = "on this PC's processor (ZipVoice)"
    if st.get("better_voice"):
        how += (", or on the second graphics card (F5-TTS, the better voice) once that "
                "has loaded")
    return (
        f"Make Jarvis speak in the voice \"{v.name}\"?\n\n"
        f"If you say yes: everything Jarvis says aloud, on this PC and on your phone, "
        f"sounds like the person in that recording. It is made {how}; nothing is sent "
        f"anywhere. If the voice cannot be made (missing, failing or too slow), Jarvis uses "
        f"its built-in voice and says why. You can switch back at any time, and switching "
        f"back never asks.\n\n"
        f"{_check_line(chk)}\n\n"
        f"If you did not just do this, say no.\n\n"
        f"If you say no: Jarvis keeps speaking in {current}.")


def create(body, *, gate: Optional[Callable] = None, tier_of: Optional[Callable] = None,
           spawn: Optional[Callable] = None, check: Optional[Callable] = None) -> tuple:
    """POST /api/voice/voices/create. (http code, body). Checks everything,
    holds the clip in memory, raises ONE card, returns at once. Saves nothing."""
    gate, tier_of, spawn = gate or _gate, tier_of or _tier, spawn or _spawn
    check = check or owner_check
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "send {\"name\", \"clip\", \"transcript\"}"}
    with _PENDING_LOCK:
        if _PENDING:
            return 409, {"ok": False, "pending": True,
                         "error": "a voice card is already waiting - approve or deny it first"}
    try:
        name = clean_name(body.get("name"))
        transcript = clean_transcript(body.get("transcript"))
        clip = body.get("clip")
        if not isinstance(clip, str) or not clip:
            raise BadInput("send the recording as base64 text in \"clip\"")
        if len(clip) > (MAX_CLIP_BYTES * 4) // 3 + 8:
            raise BadInput(f"the recording is too big (at most {MAX_CLIP_BYTES / 1e6:.1f} MB)")
        try:
            raw = base64.b64decode(clip, validate=True)
        except (binascii.Error, ValueError):
            raise BadInput("the recording is not valid base64") from None
        samples, seconds = normalise(raw)
        raw = b""
        words = count_words(transcript)
        rate = words / seconds
        if not MIN_WORDS_PER_SECOND <= rate <= MAX_WORDS_PER_SECOND:
            raise BadInput(f"the words do not fit the recording ({words} words in "
                           f"{seconds:.1f} seconds of speech). Type exactly what is said in "
                           f"it, all of it and nothing else")
    except BadInput as exc:
        return 400, {"ok": False, "error": str(exc)}
    taken = set(_ids_on_disk())
    if len(taken) >= MAX_VOICES:
        return 409, {"ok": False, "error": (f"there are already {MAX_VOICES} voices; delete "
                                            f"one first")}
    names = set()
    for t in taken:
        got = load_voice(t)
        names.add((got.name if got else t).lower())
    if name.lower() in names:
        return 409, {"ok": False, "error": f"there is already a voice called \"{name}\""}
    vid = id_for(name, taken)
    chk = check(samples)
    if not chk.get("ok"):
        _audit("voices.refused", {"kind": "create", "refused": chk.get("refused", "")})
        return 409, {"ok": False, "refused": chk.get("refused", "owner_check"),
                     "error": str(chk.get("why"))}
    try:
        tier = tier_of(ACTION)
    except Exception as exc:
        tier = f"unreadable ({type(exc).__name__})"
    if tier != "ask":
        return 409, {"ok": False, "pending": False,
                     "error": (f"{ACTION} is tier {tier!r} in jarvis-framework.toml; adding a "
                               f"voice needs a person to say yes, so it must be 'ask'")}
    pid = _uuid.uuid4().hex
    with _PENDING_LOCK:
        if _PENDING:
            return 409, {"ok": False, "pending": True,
                         "error": "a voice card is already waiting - approve or deny it first"}
        _PENDING.update(id=pid, kind="create", voice=vid, name=name, samples=samples,
                        transcript=transcript, seconds=seconds, check=chk,
                        since=time.time(), timeout=_timeout())
    _audit("voices.asked", {"kind": "create", "seconds": seconds})

    def work():
        try:
            _decide_create(pid, gate, check)
        except Exception:
            _finish(pid, "failed", "unexpected error")

    try:
        spawn(work)
    except Exception:
        _finish(pid, "failed", "could not start")
        return 503, {"ok": False, "error": "could not raise the approval card"}
    return 202, {"ok": True, "pending": True, "voice": vid, "name": name, "seconds": seconds,
                 "message": ("Approve the card on your PC or phone to add the voice. Nothing "
                             "is kept until you do.")}


def _decide_create(pid: str, gate: Callable, check: Callable) -> dict:
    with _PENDING_LOCK:
        if _PENDING.get("id") != pid:
            return {"outcome": "gone"}
        vid, name, seconds = _PENDING["voice"], _PENDING["name"], _PENDING["seconds"]
        transcript, chk = _PENDING["transcript"], _PENDING["check"]
    text = describe_create(name, vid, seconds, transcript, chk)
    detail = {"text": text, "what": "add a custom voice for Jarvis to speak in",
              "voice": vid, "seconds": seconds, "kept_in": str(voices_dir() / vid),
              "leaves_this_pc": False}
    try:
        v = gate(ACTION, detail, text)
    except Exception as exc:
        return _finish(pid, "refused", f"the approval gate failed ({type(exc).__name__})")
    outcome, reason, rid = _verdict(v)
    if outcome != "approved":
        return _finish(pid, outcome, reason, rid)
    with _PENDING_LOCK:
        samples = _PENDING.get("samples") if _PENDING.get("id") == pid else None
    if samples is None:
        return _finish(pid, "failed", "the recording was gone", rid)
    if _voice_path(vid) is None or _voice_path(vid).exists():
        return _finish(pid, "failed", "a voice with that name was added meanwhile", rid)
    # Checked again now: a voice print may have been trained while it waited.
    chk = check(samples)
    if not chk.get("ok"):
        return _finish(pid, "refused", str(chk.get("why")), rid)
    try:
        _write_voice(vid, name, transcript, samples, seconds,
                     {k: chk[k] for k in ("ok", "why", "fingerprint", "score", "bar",
                                          "checked") if k in chk})
    except OSError as exc:
        return _finish(pid, "failed", f"it could not be saved ({type(exc).__name__})", rid)
    return _finish(pid, "created", "", rid)


def switch(body, *, gate: Optional[Callable] = None, tier_of: Optional[Callable] = None,
           spawn: Optional[Callable] = None, check: Optional[Callable] = None) -> tuple:
    """POST /api/voice/voices/active. The built-in voice: at once. A custom
    voice: ONE card; nothing changes until it is approved."""
    gate, tier_of, spawn = gate or _gate, tier_of or _tier, spawn or _spawn
    if not isinstance(body, dict) or not isinstance(body.get("voice"), str):
        return 400, {"ok": False, "error": "send {\"voice\": \"<id>\" or \"builtin\"}"}
    vid = body["voice"].strip()
    st = _read_state()
    if vid == BUILTIN:
        with _PENDING_LOCK:
            if _PENDING.get("kind") == "switch":
                _PENDING["withdrawn"] = True
                _WITHDRAWN.add(_PENDING["id"])
        err = _write_state(active=BUILTIN)
        if err:
            return 500, {"ok": False, "error": err}
        _F5.stop("Jarvis is speaking in its built-in voice")
        _audit("voices.builtin", {})
        _publish({"what": "switch", "outcome": "builtin"})
        return 200, {"ok": True, "active": BUILTIN, "pending": False,
                     "message": "Jarvis speaks in its built-in voice."}
    v = load_voice(vid)
    if v is None:
        return 404, {"ok": False, "error": "there is no voice with that id"}
    if st["active"] == vid:
        return 200, {"ok": True, "active": vid, "pending": False,
                     "message": f"Jarvis already speaks in \"{v.name}\"."}
    with _PENDING_LOCK:
        if _PENDING:
            return 409, {"ok": False, "pending": True,
                         "error": "a voice card is already waiting - approve or deny it first"}
    samples = _clip_samples(v)
    if samples is None:
        return 409, {"ok": False, "error": f"the recording for \"{v.name}\" cannot be read; "
                                           f"delete the voice and add it again"}
    chk = (check or owner_check)(samples)
    _save_check(v, {k: chk[k] for k in ("ok", "why", "fingerprint", "score", "bar",
                                        "checked", "refused") if k in chk})
    if not chk.get("ok"):
        _audit("voices.refused", {"kind": "switch", "refused": chk.get("refused", "")})
        return 409, {"ok": False, "refused": chk.get("refused", "owner_check"),
                     "error": str(chk.get("why"))}
    try:
        tier = tier_of(ACTION)
    except Exception as exc:
        tier = f"unreadable ({type(exc).__name__})"
    if tier != "ask":
        return 409, {"ok": False, "pending": False,
                     "error": (f"{ACTION} is tier {tier!r} in jarvis-framework.toml; switching "
                               f"Jarvis's voice needs a person to say yes, so it must be 'ask'")}
    pid = _uuid.uuid4().hex
    current = "its built-in voice"
    if st["active"] != BUILTIN:
        cur = load_voice(st["active"])
        current = f"\"{cur.name}\"" if cur else "its built-in voice"
    with _PENDING_LOCK:
        if _PENDING:
            return 409, {"ok": False, "pending": True,
                         "error": "a voice card is already waiting - approve or deny it first"}
        _PENDING.update(id=pid, kind="switch", voice=vid, name=v.name, check=chk,
                        current=current, since=time.time(), timeout=_timeout(),
                        withdrawn=False)
    _audit("voices.asked", {"kind": "switch"})

    def work():
        try:
            _decide_switch(pid, gate, check)
        except Exception:
            _finish(pid, "failed", "unexpected error")

    try:
        spawn(work)
    except Exception:
        _finish(pid, "failed", "could not start")
        return 503, {"ok": False, "error": "could not raise the approval card"}
    return 202, {"ok": True, "pending": True, "voice": vid,
                 "message": ("Approve the card on your PC or phone to switch. Nothing changes "
                             "until you do.")}


def _decide_switch(pid: str, gate: Callable, check: Optional[Callable]) -> dict:
    with _PENDING_LOCK:
        if _PENDING.get("id") != pid:
            return {"outcome": "gone"}
        vid, chk, current = _PENDING["voice"], _PENDING["check"], _PENDING["current"]
    v = load_voice(vid)
    if v is None:
        return _finish(pid, "failed", "the voice was deleted")
    text = describe_switch(v, current, chk, _read_state())
    detail = {"text": text, "what": "make Jarvis speak in a custom voice", "voice": vid,
              "leaves_this_pc": False}
    try:
        verdict = gate(ACTION, detail, text)
    except Exception as exc:
        return _finish(pid, "refused", f"the approval gate failed ({type(exc).__name__})")
    outcome, reason, rid = _verdict(verdict)
    if outcome != "approved":
        return _finish(pid, outcome, reason, rid)
    with _PENDING_LOCK:
        withdrawn = pid in _WITHDRAWN
    if withdrawn:
        return _finish(pid, "withdrawn", "", rid)
    v = load_voice(vid)
    if v is None:
        return _finish(pid, "failed", "the voice was deleted while the card waited", rid)
    samples = _clip_samples(v)
    chk = (check or owner_check)(samples) if samples is not None else \
        {"ok": False, "why": "its recording could not be read"}
    if not chk.get("ok"):
        return _finish(pid, "refused", str(chk.get("why")), rid)
    err = _write_state(active=vid)
    if err:
        return _finish(pid, "failed", err, rid)
    return _finish(pid, "switched", "", rid)


def delete(body) -> tuple:
    """POST /api/voice/voices/delete. Immediate: it only takes a voice away.
    If Jarvis was speaking in it, it goes back to the built-in voice."""
    if not isinstance(body, dict) or not isinstance(body.get("voice"), str):
        return 400, {"ok": False, "error": "send {\"voice\": \"<id>\"}"}
    vid = body["voice"].strip()
    if vid == BUILTIN:
        return 400, {"ok": False, "error": "the built-in voice cannot be deleted"}
    p = _voice_path(vid)
    if p is None or not p.is_dir():
        return 404, {"ok": False, "error": "there is no voice with that id"}
    with _PENDING_LOCK:
        if _PENDING.get("kind") == "switch" and _PENDING.get("voice") == vid:
            _PENDING["withdrawn"] = True
            _WITHDRAWN.add(_PENDING["id"])
    st = _read_state()
    if st["active"] == vid:
        err = _write_state(active=BUILTIN)
        if err:
            return 500, {"ok": False, "error": err}
        _F5.stop("the voice it was speaking in was deleted")
    try:
        shutil.rmtree(p)
    except OSError as exc:
        return 500, {"ok": False, "error": f"it could not be deleted ({type(exc).__name__}); "
                                           f"close anything that has {p} open"}
    with _CLIP_LOCK:
        _CLIP_CACHE.pop(vid, None)
    _audit("voices.deleted", {})
    _publish({"what": "delete", "outcome": "deleted"})
    return 200, {"ok": True, "deleted": vid, "active": _read_state()["active"]}


# --------------------------------------------------------------------------
#   The better-voice switch (F5-TTS on the second card)
# --------------------------------------------------------------------------

def describe_better(sc: dict) -> str:
    return (
        "Turn on the better voice on the second graphics card?\n\n"
        f"Which card: the {sc['name']} (id {sc['uuid']}).\n\n"
        f"If you say yes: when Jarvis speaks in a custom voice, it starts F5-TTS on that "
        f"card, in its own program, and uses it for a more natural copy of the voice. It "
        f"needs about {F5_NEED_MB:,} MB of the card's memory (an estimate - not measured "
        f"yet). It stops after {_f5_idle_minutes()} minutes with nothing to say, in standby, "
        f"and when you turn this off. While it loads, Jarvis speaks with the processor's "
        f"copy of the same voice. It talks to Jarvis through pipes, not the network; "
        f"nothing leaves this PC. F5-TTS's model is for non-commercial use only.\n\n"
        f"If you did not just ask for this, say no.\n\n"
        f"If you say no: nothing changes. Custom voices keep working on the processor.")


def set_better(body, *, gate: Optional[Callable] = None, tier_of: Optional[Callable] = None,
               spawn: Optional[Callable] = None) -> tuple:
    """POST /api/voice/voices/better. OFF at once; ON one card."""
    gate, tier_of, spawn = gate or _gate, tier_of or _tier, spawn or _spawn
    enabled = body.get("enabled") if isinstance(body, dict) else None
    if not isinstance(enabled, bool):
        return 400, {"ok": False, "error": "send {\"enabled\": true or false}"}
    if not enabled:
        with _PENDING_LOCK:
            if _BPENDING.get("id"):
                _BPENDING["withdrawn"] = True
        err = _write_state(better_voice=False)
        if err:
            return 500, {"ok": False, "error": err}
        _F5.stop("the better-voice switch is off")
        _audit("voices.better.off", {})
        _publish({"what": "better", "outcome": "off"})
        return 200, {"ok": True, "enabled": False, "pending": False,
                     "message": "The better voice is off."}
    if _read_state()["better_voice"]:
        return 200, {"ok": True, "enabled": True, "pending": False,
                     "message": "The better voice is already on."}
    with _PENDING_LOCK:
        if _BPENDING.get("id") and not _BPENDING.get("withdrawn"):
            return 409, {"ok": False, "pending": True,
                         "error": "a card to turn on the better voice is already waiting"}
    sc = _second_card()
    if not sc["capable"]:
        return 503, {"ok": False, "error": ("the better voice cannot be turned on: it needs a "
                                            f"capable second graphics card ({sc['why']})")}
    try:
        tier = tier_of(BETTER_ACTION)
    except Exception as exc:
        tier = f"unreadable ({type(exc).__name__})"
    if tier != "ask":
        return 503, {"ok": False, "error": (f"{BETTER_ACTION} is tier {tier!r} in "
                                            f"jarvis-framework.toml; turning this on needs a "
                                            f"person to say yes, so it must be 'ask'")}
    pid = _uuid.uuid4().hex
    with _PENDING_LOCK:
        if _BPENDING.get("id") and not _BPENDING.get("withdrawn"):
            return 409, {"ok": False, "pending": True,
                         "error": "a card to turn on the better voice is already waiting"}
        _BPENDING.clear()
        _BPENDING.update(id=pid, since=time.time(), withdrawn=False)
    _audit("voices.better.asked", {})

    def work():
        try:
            _decide_better(pid, gate)
        except Exception:
            _finish_better(pid, "failed", "unexpected error")

    try:
        spawn(work)
    except Exception:
        _finish_better(pid, "failed", "could not start")
        return 503, {"ok": False, "error": "could not raise the approval card"}
    return 202, {"ok": True, "enabled": False, "pending": True,
                 "message": ("Approve the card on your PC or phone to turn it on. Nothing "
                             "changes until you do.")}


def _finish_better(pid: str, outcome: str, reason: str = "", request_id=None) -> None:
    words = {"enabled": "The better voice was turned on.",
             "denied": "You said no, so the better voice stays off.",
             "timed_out": "Nobody answered the card in time, so the better voice stays off.",
             "withdrawn": ("You turned the better voice off while its card was waiting, so "
                           "approving that card changed nothing.")}
    with _PENDING_LOCK:
        if _BPENDING.get("id") == pid:
            _BPENDING.clear()
        _BLAST.clear()
        _BLAST.update(outcome=outcome, at=int(time.time()),
                      why=words.get(outcome) or ("The better voice was not turned on: "
                                                 + (reason.rstrip(".") or "refused") + "."))
    _audit("voices.better.decided", {"outcome": outcome,
                                     **({"request_id": request_id} if request_id else {})})
    _publish({"what": "better", "outcome": outcome})


def _decide_better(pid: str, gate: Callable) -> None:
    sc = _second_card()
    if not sc["capable"]:
        return _finish_better(pid, "refused", f"no capable second card: {sc['why']}")
    text = describe_better(sc)
    detail = {"text": text, "what": "turn on the better voice (F5-TTS) on the second card",
              "card": sc["name"], "card_id": sc["uuid"], "memory_mb": F5_NEED_MB,
              "leaves_this_pc": False}
    try:
        v = gate(BETTER_ACTION, detail, text)
    except Exception as exc:
        return _finish_better(pid, "refused", f"the approval gate failed ({type(exc).__name__})")
    outcome, reason, rid = _verdict(v)
    if outcome != "approved":
        return _finish_better(pid, outcome, reason, rid)
    with _PENDING_LOCK:
        withdrawn = _BPENDING.get("id") != pid or bool(_BPENDING.get("withdrawn"))
    if withdrawn:
        return _finish_better(pid, "withdrawn", "", rid)
    err = _write_state(better_voice=True)
    if err:
        return _finish_better(pid, "failed", err, rid)
    _finish_better(pid, "enabled", "", rid)


# --------------------------------------------------------------------------
#   The routes' one entry point
# --------------------------------------------------------------------------

ROUTES = {"/api/voice/voices/create": create, "/api/voice/voices/active": switch,
          "/api/voice/voices/delete": delete, "/api/voice/voices/better": set_better}


def handle_post(route: str, body) -> tuple:
    fn = ROUTES.get(route)
    if fn is None:
        return 404, {"ok": False, "error": "no such voice route"}
    return fn(body)


def _reset_for_tests() -> None:
    global _F5
    with _PENDING_LOCK:
        _PENDING.clear()
        _LAST.clear()
        _WITHDRAWN.clear()
        _BPENDING.clear()
        _BLAST.clear()
    with _SLOW_LOCK:
        _SLOW.update(rtfs=[], until=-1e9, why="")
    wake()
    try:
        _F5.stop("reset")
    except Exception:
        pass
    _F5 = _F5Engine()
    reload()


# --------------------------------------------------------------------------
#   `python jarvis_voices.py --time`: the owner's timing command
# --------------------------------------------------------------------------

def _time_cli(sentences: list) -> int:
    import jarvis_speech
    st = _read_state()
    print(f"Voice: {st['active']}   better voice switch: "
          f"{'on' if st['better_voice'] else 'off'}")

    def one(s: str) -> dict:
        wav = jarvis_speech.say(s)
        t = (jarvis_speech.say_timings() or [{}])[-1]
        print(f"  {t.get('engine', '?'):<9} {t.get('chars', 0):>4} characters  "
              f"{t.get('seconds', 0):6.2f} s to make  {t.get('audio_seconds', 0):5.2f} s of "
              f"speech  ({t.get('rtf', 0):.2f} s per second of speech)"
              + (f"\n            built-in voice used because: {t['fallback']}"
                 if t.get("fallback") else "")
              + (f"\n            {t['note']}" if t.get("note") else ""))
        if wav:
            out = _config_dir() / "voice" / "timing-test.wav"
            try:
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(wav)
            except OSError:
                pass
        return t
    print("The first one includes loading the voice:")
    for s in sentences:
        one(s)
    if st["better_voice"] and _F5.state == "loading":
        print("The better voice was still loading; waiting for it (up to "
              f"{int(F5_LOAD_SECONDS)} s)...")
        end = _mono() + F5_LOAD_SECONDS
        while _F5.state == "loading" and _mono() < end:
            _sleep(2)
        print(f"  {_F5.state}: {_F5.why}")
        for s in sentences[1:]:
            one(s)
    print(f"The last sentence is saved in {_config_dir() / 'voice' / 'timing-test.wav'}")
    shutdown()
    return 0


if __name__ == "__main__":
    # The module by its own name: jarvis_speech.say() imports
    # `jarvis_voices`, and this file run as a script is a different copy
    # (`__main__`) whose better-voice process say() would never see.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import jarvis_voices as _this
    if "--time" in sys.argv:
        rest = [a for a in sys.argv[1:] if a != "--time"]
        first = rest[0] if rest else "Of course. I have added the dentist to Tuesday at ten."
        raise SystemExit(_this._time_cli([
            first, first,
            "The weather tomorrow looks mild, with light rain in the afternoon, so you may "
            "want a coat when you head out."]))
    print(json.dumps(_this.status(), indent=2))
