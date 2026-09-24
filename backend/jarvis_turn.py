"""jarvis_turn.py - has the owner finished speaking, or only paused?

NEW MODULE, shipped whole beside jarvis_hud.py (apply-patches.ps1 copies it).
`voice-turn.patch` adds the one route that calls it:

    POST /api/voice/turn    body: one WAV (the last few seconds of speech)
        -> 200 {"available": true, "complete": bool, "probability": 0..1,
                "threshold": 0.5, "ms": 12.3}
        -> 200 {"available": false, "why": "..."}   no model installed
        -> 400 {"error": "..."}                      not a WAV

WHAT IT IS FOR. Every listener in this project ends a sentence the same
crude way: when the sound has been quiet for about a second. That cuts
people off when they stop to think in the middle of a sentence ("can you
remind me to call my ... sister on Thursday"), and it makes every answer
wait a whole second after a sentence that was obviously finished. Smart
Turn is a small model trained for exactly this question: given the last few
seconds of someone speaking, did they FINISH, or only pause? A listener asks
it when a short pause starts; "finished" ends the recording at once, "not
finished" keeps recording (up to a hard limit, so it can never hang).

WHY THIS DOES NOT BREAK "A CLIENT MUST NOT DO SPEECH-TO-TEXT". It works on
sound, not words: its whole output is ONE number, the chance the speaker has
finished. It has no vocabulary and produces no text - the same argument
jarvis_wakeword.py makes for the wake-word spotter. The phone runs the same
model itself (jarvis-client voice/SmartTurn.kt), so its audio never leaves
it before the wake word; THIS route exists for the desktop app, whose
listener already sends every utterance to the Jarvis server on the same PC
over loopback (voice.rs refuses to listen otherwise), so asking the server
here moves no audio anywhere it was not already going.

THE MODEL. Smart Turn v3.2 by Daily / Pipecat (github.com/pipecat-ai/
smart-turn), BSD 2-Clause - code and weights. The CPU build, int8, one file
of 8.7 MB: `smart-turn-v3.2-cpu.onnx`. Whisper Tiny's encoder with a small
classifier on top, ~8 M parameters. It takes up to 8 s of 16 kHz audio as
Whisper's 80-band log-mel picture and returns the probability the turn is
complete. backend/README.md has the one-line install.

THE FEATURES are computed here, in numpy, exactly as the model expects:
Whisper's log-mel spectrogram (n_fft 400, hop 160, 80 Slaney mel bands,
log10, clamped to 8 below the max, then (x + 4) / 4), over the LAST 8 s of
audio, zero-padded at the FRONT when shorter, after the waveform is scaled
to zero mean and unit variance. That is Pipecat's own numpy port
(pipecat/audio/turn/smart_turn/_whisper_features.py, BSD-2) of the
HuggingFace transformers WhisperFeatureExtractor (Apache-2.0), rewritten
here; test_turn.py checks it against numbers computed with Pipecat's.

NOTHING IS KEPT. No audio, feature or score is written to disk or logged.
One clip in, one number out.
"""
from __future__ import annotations

import io
import os
import threading
import time
import wave
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

try:
    import numpy as np
except Exception:  # pragma: no cover - numpy comes with sherpa-onnx
    np = None  # type: ignore

try:
    import onnxruntime as ort
except Exception:
    ort = None  # type: ignore

try:
    import jarvis_framework as fw
except Exception:
    fw = None  # type: ignore

SAMPLE_RATE = 16000
#: The model looks at this much audio, at most. Longer: the END is kept.
WINDOW_SECONDS = 8
N_SAMPLES = SAMPLE_RATE * WINDOW_SECONDS
N_FFT = 400
HOP = 160
N_MELS = 80
MODEL_FILE = "smart-turn-v3.2-cpu.onnx"
#: The model's own cut-off (Pipecat uses 0.5).
DEFAULT_THRESHOLD = 0.5
#: A clip sent to the route: at most this long before it is refused. The
#: route only needs the last 8 s; more than this is a client bug.
MAX_SECONDS = 30.0


def _cfg(key: str, default=None):
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


def model_path() -> Path:
    configured = str(_cfg("turn_model", "") or "").strip()
    if configured:
        return Path(os.path.expanduser(configured))
    return _config_dir() / "voice-models" / "turn" / MODEL_FILE


def threshold() -> float:
    try:
        t = float(_cfg("turn_threshold", DEFAULT_THRESHOLD))
    except (TypeError, ValueError):
        return DEFAULT_THRESHOLD
    # Held inside the range anyone would mean: at 0.05 every pause ends the
    # sentence (the old behaviour), at 0.95 almost none does (every sentence
    # waits for the hard limit).
    return min(0.95, max(0.05, t))


def status() -> dict:
    """Cheap: file checks only, no model is loaded to answer."""
    p = model_path()
    if np is None or ort is None:
        why = ("the onnxruntime package is not installed in the Python that "
               "runs Jarvis (py -3 -m pip install onnxruntime)")
    elif not p.is_file():
        why = f"the Smart Turn model is not on disk yet (looked for {p})"
    else:
        why = ""
    return {"available": not why, "engine": "Smart Turn v3.2 (ONNX Runtime)",
            "threshold": threshold(), "why": why, "model": str(p)}


# --------------------------------------------------------------------------
#   Whisper's log-mel features, in numpy
# --------------------------------------------------------------------------

def _hz_to_mel(f):
    f = np.atleast_1d(np.asarray(f, dtype=np.float64))
    mel = 3.0 * f / 200.0
    hi = f >= 1000.0
    mel[hi] = 15.0 + np.log(f[hi] / 1000.0) * (27.0 / np.log(6.4))
    return mel


def _mel_to_hz(m):
    m = np.atleast_1d(np.asarray(m, dtype=np.float64))
    f = 200.0 * m / 3.0
    hi = m >= 15.0
    f[hi] = 1000.0 * np.exp((np.log(6.4) / 27.0) * (m[hi] - 15.0))
    return f


def _mel_filters():
    """(201, 80): Slaney-scale, Slaney-normalised triangles, 0..8 kHz."""
    bins = N_FFT // 2 + 1
    lo, hi = _hz_to_mel(0.0)[0], _hz_to_mel(SAMPLE_RATE / 2.0)[0]
    edges = _mel_to_hz(np.linspace(lo, hi, N_MELS + 2))
    fft_f = np.linspace(0, SAMPLE_RATE // 2, bins)
    diff = np.diff(edges)
    slopes = edges[None, :] - fft_f[:, None]
    down = -slopes[:, :-2] / diff[:-1]
    up = slopes[:, 2:] / diff[1:]
    fb = np.maximum(0.0, np.minimum(down, up))
    fb *= (2.0 / (edges[2:N_MELS + 2] - edges[:N_MELS]))[None, :]
    return fb


_FILTERS = None
_WINDOW = None


def _constants():
    global _FILTERS, _WINDOW
    if _FILTERS is None:
        _FILTERS = _mel_filters()
        _WINDOW = np.hanning(N_FFT + 1)[:-1]     # periodic Hann, as torch's
    return _FILTERS, _WINDOW


def last_window(samples):
    """The last 8 s of 16 kHz float audio, zero-padded at the FRONT."""
    x = np.asarray(samples, dtype=np.float32).reshape(-1)
    if len(x) >= N_SAMPLES:
        return x[-N_SAMPLES:]
    return np.concatenate([np.zeros(N_SAMPLES - len(x), dtype=np.float32), x])


def features(window):
    """8 s of 16 kHz audio (see last_window) -> float32 (80, 800)."""
    filters, win = _constants()
    x = np.asarray(window, dtype=np.float32)
    x = (x - x.mean()) / np.sqrt(x.var() + 1e-7)
    padded = np.pad(x.astype(np.float64), (N_FFT // 2, N_FFT // 2), mode="reflect")
    n_frames = 1 + (len(padded) - N_FFT) // HOP
    idx = np.arange(N_FFT)[None, :] + HOP * np.arange(n_frames)[:, None]
    spec = np.abs(np.fft.rfft(padded[idx] * win, axis=-1)) ** 2      # (frames, 201)
    mel = np.maximum(1e-10, spec @ filters).T                          # (80, frames)
    logm = np.log10(mel)[:, :-1]                                       # drop the last frame
    logm = np.maximum(logm, logm.max() - 8.0)
    return ((logm + 4.0) / 4.0).astype(np.float32)


# --------------------------------------------------------------------------
#   The model. Loaded once, on first real use.
# --------------------------------------------------------------------------

_LOCK = threading.Lock()
_UNSET = object()
_session = _UNSET


def _load():
    global _session
    with _LOCK:
        if _session is _UNSET:
            if not status()["available"]:
                _session = None
            else:
                try:
                    so = ort.SessionOptions()
                    so.intra_op_num_threads = max(1, min(4, int(_cfg("turn_threads", 1) or 1)))
                    so.inter_op_num_threads = 1
                    so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
                    s = ort.InferenceSession(str(model_path()), so,
                                             providers=["CPUExecutionProvider"])
                    _session = (s, s.get_inputs()[0].name)
                except Exception:
                    _session = None
        return _session


def reload() -> None:
    global _session
    with _LOCK:
        _session = _UNSET


@dataclass
class Turn:
    #: The model ran. False: no model, or it would not load.
    ran: bool
    complete: bool = False
    probability: float = 0.0
    threshold: float = DEFAULT_THRESHOLD
    ms: float = 0.0
    why: str = ""

    def as_dict(self) -> dict:
        d = asdict(self)
        d["available"] = d.pop("ran")
        return d


def _to_16k(samples, sample_rate: int):
    try:
        import jarvis_wakeword
        return jarvis_wakeword.to_16k(samples, sample_rate)
    except Exception:
        x = np.asarray(samples, dtype=np.float32)
        if not sample_rate or sample_rate == SAMPLE_RATE or len(x) < 2:
            return x
        n = int(round(len(x) * SAMPLE_RATE / sample_rate))
        return np.interp(np.arange(n) * (sample_rate / SAMPLE_RATE),
                         np.arange(len(x)), x).astype(np.float32)


def predict(samples, sample_rate: int = SAMPLE_RATE) -> Turn:
    """Has the speaker finished? `samples` are floats in -1..1, the speech so
    far (only the last 8 s are looked at)."""
    thr = threshold()
    if np is None:
        return Turn(False, threshold=thr, why="numpy is not installed")
    loaded = _load()
    if loaded is None:
        return Turn(False, threshold=thr,
                    why=status()["why"] or "the Smart Turn model could not be loaded")
    session, name = loaded
    t0 = time.perf_counter()
    x = _to_16k(samples, sample_rate)
    feats = features(last_window(x))[None, :, :]
    try:
        out = session.run(None, {name: feats})[0]
    except Exception as exc:
        return Turn(False, threshold=thr, why=f"the model failed ({type(exc).__name__})")
    p = float(np.asarray(out).reshape(-1)[0])
    if not np.isfinite(p):
        # Unknown is "not finished": the listener then waits for the hard
        # limit, which is the old behaviour - never a cut-off sentence.
        return Turn(True, complete=False, probability=0.0, threshold=thr,
                    ms=round((time.perf_counter() - t0) * 1000, 1), why="no usable score")
    return Turn(True, complete=p >= thr, probability=round(p, 4), threshold=thr,
                ms=round((time.perf_counter() - t0) * 1000, 1))


# --------------------------------------------------------------------------
#   The route
# --------------------------------------------------------------------------

def _read_wav(raw: bytes):
    """(float32 mono samples, rate) or a sentence saying what is wrong."""
    try:
        with wave.open(io.BytesIO(raw), "rb") as w:
            sr, width, ch = w.getframerate(), w.getsampwidth(), max(1, w.getnchannels())
            frames = w.readframes(w.getnframes())
    except Exception:
        return "send one 16-bit PCM WAV clip"
    if width != 2 or not frames:
        return "send one 16-bit PCM WAV clip"
    x = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    if ch > 1:
        x = x[:(len(x) // ch) * ch].reshape(-1, ch).mean(axis=1)
    if sr <= 0 or len(x) / float(sr) > MAX_SECONDS:
        return f"send at most {MAX_SECONDS:g} seconds - only the last 8 are used"
    return x, sr


def handle(raw: bytes) -> tuple:
    """POST /api/voice/turn -> (http_status, payload). Never raises for bad
    input; never echoes it."""
    if np is None:
        return 200, {"available": False, "why": "numpy is not installed"}
    parsed = _read_wav(raw or b"")
    if isinstance(parsed, str):
        return 400, {"error": parsed}
    x, sr = parsed
    return 200, predict(x, sr).as_dict()


if __name__ == "__main__":
    import sys
    for k, v in status().items():
        print(f"  {k:<10} {v}")
    for f in sys.argv[1:]:
        got = _read_wav(Path(f).read_bytes())
        if isinstance(got, str):
            print(f, got)
            continue
        t = predict(*got)
        print(f"{f}: {'finished' if t.complete else 'not finished'} "
              f"(p={t.probability:.3f}, {t.ms:.0f} ms)" if t.ran else f"{f}: {t.why}")
