"""jarvis_turn.py - has the owner finished speaking, or only paused?

NEW MODULE, shipped whole beside jarvis_hud.py (apply-patches.ps1 copies it).
`voice-turn.patch` adds the one route that calls it:

    POST /api/voice/turn    body: one WAV, or raw 16 kHz mono int16 PCM
                                 (the last few seconds of speech)
        -> 200 {"available": true, "complete": bool, "probability": 0..1,
                "threshold": 0.5, "ms": 12.3, "format": "wav"|"pcm16"}
        -> 200 {"available": false, "why": "..."}   no model installed
        -> 400 {"error": "..."}                      not audio

    The route itself is unchanged (same path, same origin and token checks);
    `handle()` now sniffs the body: a RIFF header is a WAV as before, and
    anything else is taken as raw little-endian int16 PCM at 16 kHz mono -
    no WAV header, no base64, no JSON. Old clients keep sending WAV. In
    process, `predict_pcm()` takes the same raw PCM directly and
    `TurnStream` builds the features as the audio arrives.

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
import math
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

# ONNX Runtime's own trace events are ON by default in Microsoft's builds
# (its docs/Privacy.md; on Windows they go to ETW and, with the owner's
# Windows diagnostic-data consent, may reach Microsoft). Rule 1: nothing about
# the owner leaves the PC, so they are switched off before any model loads.
# The switch is process-wide; a missing or older onnxruntime is harmless.
if ort is not None:
    try:
        ort.disable_telemetry_events()
    except Exception:
        pass

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
#   The fast path: raw PCM in process, and the features built as it arrives
# --------------------------------------------------------------------------

def pcm_to_samples(pcm, sample_rate: int = SAMPLE_RATE):
    """Raw audio in, (float32 samples in -1..1, the rate it is at).

    Takes little-endian int16 PCM bytes (the shape the desktop listener's
    ring buffer already has), an array('h'), a numpy array (any int ->
    int16 scale, float -> samples), or a list of floats. Raises ValueError
    for half a sample, which is always a client bug.
    """
    if np is None:
        raise ValueError("numpy is not installed")
    if isinstance(pcm, (bytes, bytearray, memoryview)):
        raw = bytes(pcm)
        if len(raw) % 2:
            raise ValueError("raw PCM must be a whole number of 16-bit samples")
        return (np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0,
                int(sample_rate))
    if isinstance(pcm, np.ndarray):
        arr = pcm.reshape(-1)
        if np.issubdtype(arr.dtype, np.integer):
            return arr.astype(np.float32) / 32768.0, int(sample_rate)
        return arr.astype(np.float32, copy=False), int(sample_rate)
    if hasattr(pcm, "typecode") and getattr(pcm, "typecode") == "h":
        return np.asarray(pcm, dtype=np.float32) / 32768.0, int(sample_rate)
    return np.asarray(list(pcm), dtype=np.float32).reshape(-1), int(sample_rate)


_HANN_FFT = None
_HANN_FFT_LOCK = threading.Lock()


def _hann_fft():
    """rfft(hann) - the one constant that makes a cached frame correctable."""
    global _HANN_FFT
    with _HANN_FFT_LOCK:
        if _HANN_FFT is None:
            _constants()
            _HANN_FFT = np.fft.rfft(_WINDOW).astype(np.complex128)
        return _HANN_FFT


def _frames_of(samples, starts, win):
    """One batched rfft of every (400-sample frame * window) at `starts`."""
    starts = np.asarray(starts, dtype=np.int64)
    idx = np.arange(N_FFT, dtype=np.int64)[None, :] + starts[:, None]
    return np.fft.rfft(np.asarray(samples, dtype=np.float64)[idx] * win, axis=-1)


class MelStream:
    """The same log-mel picture as `features()`, built as the audio arrives.

    WHY. `features()` FFTs the WHOLE 8 s window every time it is called (801
    frames). A listener that asks Smart Turn as the owner speaks asks it on a
    growing clip, so nearly all of that work is repeated. This class caches
    the FFT of every frame that a future window can still ask for, keyed by
    the frame's first sample, and serves `features()` from the cache: only
    the frames at the window's reflective edges (and any the caller's chunk
    sizes did not let it pre-compute) are FFT'd at the end.

    ONE PIECE OF MATHS makes that possible. The reference normalises the
    whole window (zero mean, unit variance) before the FFT, and the mean only
    exists at the end. For a cached raw frame `f` (400 samples), window
    function `h`, and end-time mean m / std s:

        FFT((f - m)/s * h) = (FFT(f*h) - m*FFT(h)) / s

    because the FFT is linear; the power spectrum is the squared magnitude of
    that. A frame that lies entirely inside the zeros the reference pads the
    FRONT of a short clip with is the same trick with `f = 0`. The frames
    that overlap the reflect-padded edges are computed directly from the
    normalised window, exactly as the reference does them.

    THE CHUNK RESIDUE. The window is the LAST 8 s, so a chunk whose length is
    not a multiple of the 10 ms hop shifts which absolute sample positions
    the frames start at. The class therefore pre-computes every frame whose
    start is congruent (mod 160) to a total this caller's chunk length can
    reach: five classes for a 32 ms VAD chunk (512 % 160 = 32), one for a
    hop-aligned caller. Past `MAX_RESIDUES` classes it stops pre-computing
    and simply computes the missing frames - the old cost, never a wrong
    answer.

    The class keeps only the last 8.4 s of audio and drops the cached frames
    that fall out of it; it holds no audio beyond one utterance, and nothing
    here is written or logged.
    """

    #: Residue classes kept. A 32 ms chunk makes 5; the cap stops an unusual
    #: caller turning the cache into a memory leak (each class is ~2.6 MB).
    MAX_RESIDUES = 16

    def __init__(self, sample_rate: int = SAMPLE_RATE):
        if int(sample_rate or SAMPLE_RATE) != SAMPLE_RATE:
            raise ValueError(f"MelStream takes {SAMPLE_RATE} Hz audio")
        self._buf = np.zeros(0, dtype=np.float32)
        self._base = 0            # absolute index of _buf[0]
        self._cache = {}          # absolute frame start -> complex128 spectrum
        self._residues = set()
        self._chunk = None        # last chunk length, for the residue cycle
        #: Test-mode work counters: how many frames were FFT'd and how many
        #: were served from the cache. The suites read these; nothing in
        #: production does.
        self.frames_computed = 0
        self.frames_reused = 0

    @property
    def total(self) -> int:
        return self._base + len(self._buf)

    @property
    def seconds(self) -> float:
        return self.total / float(SAMPLE_RATE)

    def feed(self, audio) -> dict:
        """Append one chunk (raw int16 PCM, samples, or (samples, rate))."""
        if isinstance(audio, tuple) and len(audio) == 2:
            x, rate = pcm_to_samples(audio[0], audio[1])
            if int(rate) != SAMPLE_RATE:
                x = _to_16k(x, int(rate))
        else:
            x, _rate = pcm_to_samples(audio)
        if len(x):
            self._buf = np.concatenate([self._buf, np.asarray(x, dtype=np.float32).reshape(-1)])
            self._chunk = len(x)
        self._trim()
        self._precompute()
        return {"seconds": round(self.seconds, 2),
                "frames_computed": self.frames_computed,
                "cached_residues": len(self._residues)}

    def _trim(self):
        """Keep only the audio an 8 s window can still use."""
        keep = N_SAMPLES + HOP * 4
        if len(self._buf) <= keep:
            return
        drop = len(self._buf) - keep
        drop -= drop % HOP
        if drop <= 0:
            return
        self._buf = self._buf[drop:]
        self._base += drop
        floor = self.total - keep - N_FFT
        for start in [s for s in self._cache if s < floor]:
            del self._cache[start]

    def _precompute(self):
        """Cache the FFT of every frame a future window can ask for."""
        if not len(self._buf):
            return
        win = _constants()[1]
        step = (self._chunk or len(self._buf)) % HOP
        cycle = HOP // math.gcd(step, HOP) if step else 1
        if cycle > self.MAX_RESIDUES:
            # Too many residues to be worth caching: features() computes the
            # missing frames itself, which is the old cost.
            self._residues = set()
            return
        # A frame at the end-of-turn window's offset i starts at
        # (T - 128200 + 160i); the constant 128200 is 40 above a hop grid,
        # so the class for a final total T is (T - 40) mod 160.
        residues = {(self.total - 40 + k * step) % HOP for k in range(cycle)}
        self._residues = residues
        lo = max(self._base, self.total - N_SAMPLES - N_FFT)
        hi = self.total - N_FFT
        if hi < lo:
            return
        want = []
        for res in residues:
            first = lo + ((res - lo) % HOP)
            for s in range(first, hi + 1, HOP):
                if int(s) not in self._cache:
                    want.append(int(s))
        if not want:
            return
        spectra = _frames_of(self._buf, [s - self._base for s in want], win)
        for s, spec in zip(want, spectra):
            self._cache[s] = np.asarray(spec, dtype=np.complex128)
        self.frames_computed += len(want)

    def features(self) -> np.ndarray:
        """The reference's (80, 800) float32 log-mel, mostly from the cache."""
        filters, win = _constants()
        H = _hann_fft()
        x = last_window(self._buf)
        m32 = x.mean()
        s32 = np.sqrt(x.var() + 1e-7)
        m, s = float(m32), float(s32)
        total = self.total
        # x's first sample is raw sample `window_start`; negative means
        # that part of x is the zeros the reference pads a short clip with.
        window_start = total - N_SAMPLES
        z = max(0, -window_start)                   # length of the front zeros
        n_frames = 1 + N_SAMPLES // HOP              # 801, as the reference
        rel = HOP * np.arange(n_frames, dtype=np.int64) - (N_FFT // 2)
        power = np.zeros((n_frames, N_FFT // 2 + 1), dtype=np.float64)
        direct = np.ones(n_frames, dtype=bool)
        # 1) frames entirely inside the front zero pad: f = 0, so the cached
        #    FFT is (-m/s) * FFT(hann), exactly.
        zeros = (rel + N_FFT) <= z
        if zeros.any():
            const = -m / s
            power[zeros] = (const * const) * (np.abs(H) ** 2)[None, :]
            direct[zeros] = False
        # 2) frames wholly inside real samples: the cached raw frame,
        #    corrected for the window's mean and variance.
        absolute = window_start + rel
        usable = (absolute >= 0) & (absolute + N_FFT <= total) & \
                 (rel >= 0) & (rel + N_FFT <= N_SAMPLES)
        reused = 0
        for i in np.nonzero(usable)[0]:
            spec = self._cache.get(int(absolute[i]))
            if spec is None:
                continue
            corr = (spec - m * H) / s
            power[i] = corr.real * corr.real + corr.imag * corr.imag
            direct[i] = False
            reused += 1
        self.frames_reused += reused
        # 3) everything else: the reflect-padded edges, the frames crossing
        #    the zero pad, and anything the cache did not cover.
        if direct.any():
            norm = ((x - m32) / s32).astype(np.float64)
            padded = np.pad(norm, (N_FFT // 2, N_FFT // 2), mode="reflect")
            starts = HOP * np.nonzero(direct)[0]
            idx = starts[:, None] + np.arange(N_FFT, dtype=np.int64)[None, :]
            spec = np.fft.rfft(padded[idx] * win, axis=-1)
            power[direct] = spec.real * spec.real + spec.imag * spec.imag
        self.frames_computed += int(direct.sum())
        mel = np.maximum(1e-10, power @ filters).T
        logm = np.log10(mel)[:, :-1]
        logm = np.maximum(logm, logm.max() - 8.0)
        return ((logm + 4.0) / 4.0).astype(np.float32)


class TurnStream:
    """One utterance's Smart Turn, fed as the audio arrives.

    `feed()` takes the same chunks the VAD already produces (raw int16 PCM at
    16 kHz), `predict()` asks the already-cached ONNX session once. No WAV,
    no base64, no HTTP, no second feature pass over the whole window.
    """

    def __init__(self, sample_rate: int = SAMPLE_RATE):
        self.stream = MelStream(sample_rate)
        self.last = {"frames_computed": 0, "frames_reused": 0}

    @property
    def seconds(self) -> float:
        return self.stream.seconds

    def feed(self, audio) -> dict:
        return self.stream.feed(audio)

    def predict(self) -> Turn:
        """(Turn, and the work counters in `.last`)."""
        before_c, before_r = self.stream.frames_computed, self.stream.frames_reused
        t0 = time.perf_counter()
        feats = self.stream.features()
        self.last = {"frames_computed": self.stream.frames_computed - before_c,
                     "frames_reused": self.stream.frames_reused - before_r}
        return _predict_features(feats, t0)


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


def _predict_features(feats, t0=None) -> Turn:
    """One (80, 800) picture through the cached session. Shared by the
    reference path and the streaming one, so the two cannot drift."""
    thr = threshold()
    if np is None:
        return Turn(False, threshold=thr, why="numpy is not installed")
    loaded = _load()
    if loaded is None:
        return Turn(False, threshold=thr,
                    why=status()["why"] or "the Smart Turn model could not be loaded")
    session, name = loaded
    if t0 is None:
        t0 = time.perf_counter()
    try:
        out = session.run(None, {name: np.asarray(feats, dtype=np.float32)[None, :, :]})[0]
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


def predict(samples, sample_rate: int = SAMPLE_RATE) -> Turn:
    """Has the speaker finished? `samples` are floats in -1..1, the speech so
    far (only the last 8 s are looked at). The reference path: the whole
    window's features are computed here, exactly as they always were."""
    t0 = time.perf_counter()
    if np is None:
        return Turn(False, threshold=threshold(), why="numpy is not installed")
    x = _to_16k(samples, sample_rate)
    return _predict_features(features(last_window(x)), t0)


def predict_pcm(pcm, sample_rate: int = SAMPLE_RATE) -> Turn:
    """The same question, from raw audio in process (no WAV round-trip).

    Accepts what `pcm_to_samples` accepts: int16 PCM bytes at 16 kHz, or any
    samples at `sample_rate`. Identical answer to `predict(...)` on the same
    audio; the features come from the streaming builder (`MelStream`), which
    is proven against the reference in tests.
    """
    t0 = time.perf_counter()
    if np is None:
        return Turn(False, threshold=threshold(), why="numpy is not installed")
    samples, rate = pcm_to_samples(pcm, sample_rate)
    if int(rate) != SAMPLE_RATE:
        samples = _to_16k(samples, int(rate))
    stream = MelStream(SAMPLE_RATE)
    stream.feed(samples)
    return _predict_features(stream.features(), t0)


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


#: The two ways audio arrives: a WAV (old clients), or raw 16 kHz mono
#: int16 PCM (no header, no base64 - the fast path, and what a caller with
#: the samples already in memory sends).
FORMAT_WAV = "wav"
FORMAT_PCM = "pcm16"
#: Shorter than this (10 ms) is not an utterance; refuse it rather than ask
#: the model about half a frame.
MIN_PCM_BYTES = 320


def _read_audio(raw: bytes):
    """(samples, rate, format) or a sentence saying what is wrong.

    Sniffed, not guessed from headers: the route is unchanged, old clients
    send a WAV (RIFF), and anything else is the raw PCM the fast path uses.
    """
    if raw[:4] == b"RIFF":
        parsed = _read_wav(raw)
        if isinstance(parsed, str):
            return parsed
        return parsed[0], parsed[1], FORMAT_WAV
    if raw[:1] in (b"{", b"["):
        # A JSON body is never audio; say what is expected, quote nothing.
        return ("send one 16-bit PCM WAV clip, or raw 16 kHz mono int16 PCM "
                "(no header)")
    if len(raw) > int(MAX_SECONDS * SAMPLE_RATE) * 2:
        return f"send at most {MAX_SECONDS:g} seconds - only the last 8 are used"
    if len(raw) < MIN_PCM_BYTES:
        return ("send one 16-bit PCM WAV clip, or raw 16 kHz mono int16 PCM "
                "(no header)")
    try:
        x, sr = pcm_to_samples(raw, SAMPLE_RATE)
    except ValueError as exc:
        return str(exc)
    return x, sr, FORMAT_PCM


def handle(raw: bytes) -> tuple:
    """POST /api/voice/turn -> (http_status, payload). Never raises for bad
    input; never echoes it.

    Takes a WAV body (as it always has) or raw 16 kHz mono int16 PCM. The
    route around this call is unchanged: same path, same origin and token
    checks, same PC-only rules - this only accepts the same sound in the
    shape a listener that already has the samples can hand it over.
    """
    if np is None:
        return 200, {"available": False, "why": "numpy is not installed"}
    got = _read_audio(bytes(raw or b""))
    if isinstance(got, str):
        return 400, {"error": got}
    x, sr, fmt = got
    t = predict(x, sr)
    if t.ran:
        # How long Smart Turn took, for the delay's numbers
        # (jarvis_voice_flow.py, /api/voice/status flow.timings). A number
        # only; a missing module changes nothing.
        try:
            import jarvis_voice_flow
            jarvis_voice_flow.note_smart_turn(t.ms)
        except Exception:
            pass
    out = t.as_dict()
    out["format"] = fmt
    return 200, out


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
