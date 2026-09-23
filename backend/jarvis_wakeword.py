"""jarvis_wakeword.py - listens for "hey Jarvis" in a clip, and for nothing else.

NEW MODULE, shipped whole beside jarvis_hud.py (apply-patches.ps1 copies it).
jarvis_speech.hear() calls it for every clip that arrives as
`source=wake_word`, BEFORE the owner check and before any speech-to-text:

    clip -> [is "hey Jarvis" in it?] -> [is it the owner?] -> [words]
              this module                jarvis_voice        jarvis_speech

A keyword spotter is not speech-to-text. It turns audio into ONE number - how
much this sounds like "hey Jarvis" - and has no vocabulary, no words, nothing
it could write down. That is why it may run before the owner check: it
learns nothing about what was said.

WHICH SPOTTER, AND WHY THIS ONE
openWakeWord's pre-trained "hey jarvis" model (github.com/dscripka/openWakeWord,
release v0.5.1). Three small ONNX files, 3.7 MB in all:

    melspectrogram.onnx   audio -> a picture of its pitch over time
    embedding_model.onnx  that picture -> 96 numbers per 80 ms (Google's
                          speech_embedding, Apache-2.0)
    hey_jarvis_v0.1.onnx  the last 16 of those -> one score, 0..1

The config already named it - `[voice] wake_phrase = "hey_jarvis"` and
`wake_threshold = 0.5` are openWakeWord's own model name and default
threshold, and the section's comment says "nothing is transcribed until the
openWakeWord 'hey jarvis' model fires". docs/WAKE-WORD.md chose it too. The
phone runs the SAME three files through the same steps (jarvis-client
voice/WakeSpotter.kt), so one threshold means one thing on both.

The pre-trained models are CC BY-NC-SA 4.0 (non-commercial, share-alike,
attribution) - allowed by rule 5, recorded in THIRD-PARTY-NOTICES.txt.

The other candidate, sherpa-onnx's own open-vocabulary keyword spotter, was
measured against the same clips (backend/README.md, "the wake word"): fewer
false alarms, more misses - and there is no sherpa-onnx library for Android
on Maven Central or Google's repository, which is where the phone's build
may fetch from. ONNX Runtime is on both pip and Maven Central.

THE ALGORITHM, exactly as openWakeWord's own `AudioFeatures` streams it
(openwakeword/utils.py), so the scores match the published model:
  every 1280 samples (80 ms at 16 kHz):
    mel   = melspectrogram(last 1760 samples) / 10 + 2   -> 8 new frames x 32
    emb   = embedding(last 76 mel frames)                -> 1 x 96
    score = wake_model(last 16 embeddings)               -> 0..1
  the first 5 scores after a (re)start are ignored, as upstream does.
Audio goes in as 16-bit sample VALUES (-32768..32767) in float32, not
scaled to -1..1 - that is what the mel model was exported with.

NOTHING IS KEPT. No audio, score history or clip is written to disk or
logged. A clip goes in, one verdict comes out.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
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

#: 80 ms at 16 kHz - the model's own step.
CHUNK = 1280
#: 1280 new samples plus 3 x 160 of the previous chunk: the mel model's
#: 512-sample window with a 160 hop turns exactly this many into 8 frames.
MEL_INPUT = CHUNK + 480
MEL_WINDOW = 76
EMB_WINDOW = 16
#: Upstream ignores the first five scores after a start.
WARMUP_SCORES = 5
SAMPLE_RATE = 16000
#: Silence put in front of a clip before scoring it. The model looks at the
#: last ~2 s, so a clip that starts with "hey Jarvis" needs something ahead
#: of it for the first scores to mean anything.
LEAD_IN_SECONDS = 1.5

MODEL_FILES = {
    "melspectrogram": "melspectrogram.onnx",
    "embedding": "embedding_model.onnx",
}
#: `wake_phrase` in [voice] -> the model file for it. Only one exists.
PHRASE_MODELS = {"hey_jarvis": "hey_jarvis_v0.1.onnx"}


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
    import os
    return Path(os.environ.get("OPENJARVIS_CONFIG_DIR")
                or os.environ.get("JARVIS_CONFIG_DIR")
                or (Path.home() / ".openjarvis"))


def model_dir() -> Path:
    return Path(str(_cfg("wake_model_dir", "") or (_config_dir() / "voice-models" / "wakeword")))


def phrase() -> str:
    return str(_cfg("wake_phrase", "hey_jarvis") or "hey_jarvis").strip().lower()


def threshold() -> float:
    try:
        t = float(_cfg("wake_threshold", 0.5))
    except (TypeError, ValueError):
        return 0.5
    # Below 0.1 almost anything fires; above 0.99 almost nothing does. Neither
    # is a setting anyone means, so it is held inside the useful range.
    return min(0.99, max(0.1, t))


def model_paths() -> dict:
    d = model_dir()
    wake = str(_cfg("wake_model", "") or "")
    if not wake:
        name = PHRASE_MODELS.get(phrase())
        wake = str(d / name) if name else ""
    return {"melspectrogram": str(d / MODEL_FILES["melspectrogram"]),
            "embedding": str(d / MODEL_FILES["embedding"]),
            "wake": wake}


def status() -> dict:
    """Cheap: file checks only, no model is loaded to answer."""
    paths = model_paths()
    missing = [k for k, p in paths.items() if not p or not Path(p).is_file()]
    if ort is None or np is None:
        why = ("the onnxruntime package is not installed in the Python that "
               "runs Jarvis (python -m pip install onnxruntime)")
    elif not paths["wake"]:
        why = (f"there is no model for wake_phrase = {phrase()!r}; the only "
               f"one available is \"hey_jarvis\"")
    elif missing:
        why = (f"the wake-word model files are not on disk yet (looked in "
               f"{model_dir()})")
    else:
        why = ""
    return {"available": not why, "engine": "openWakeWord (ONNX Runtime)",
            "phrase": phrase(), "threshold": threshold(), "why": why,
            "model_dir": str(model_dir())}


# --------------------------------------------------------------------------
#   The models. Loaded once, on first real use, never to answer status().
# --------------------------------------------------------------------------

_LOCK = threading.RLock()
_UNSET = object()
_models = _UNSET


class _Models:
    def __init__(self, paths: dict):
        so = ort.SessionOptions()
        # One thread each: a clip of a few seconds is ~40 steps of three tiny
        # models, and more threads cost more to start than they save.
        so.intra_op_num_threads = 1
        so.inter_op_num_threads = 1
        prov = ["CPUExecutionProvider"]
        self.mel = ort.InferenceSession(paths["melspectrogram"], so, providers=prov)
        self.emb = ort.InferenceSession(paths["embedding"], so, providers=prov)
        self.wake = ort.InferenceSession(paths["wake"], so, providers=prov)
        self.mel_in = self.mel.get_inputs()[0].name
        self.emb_in = self.emb.get_inputs()[0].name
        self.wake_in = self.wake.get_inputs()[0].name

    def melspec(self, x):
        out = self.mel.run(None, {self.mel_in: x[None, :].astype(np.float32)})[0]
        return np.squeeze(out, axis=(0, 1)) / 10.0 + 2.0

    def embed(self, frames):
        out = self.emb.run(None, {self.emb_in: frames[None, :, :, None].astype(np.float32)})[0]
        return out.reshape(-1, 96)

    def score(self, feats):
        return float(self.wake.run(None, {self.wake_in: feats[None].astype(np.float32)})[0].reshape(-1)[0])


def _load():
    global _models
    with _LOCK:
        if _models is _UNSET:
            if not status()["available"]:
                _models = None
            else:
                try:
                    _models = _Models(model_paths())
                except Exception:
                    # A corrupt or wrong file: no spotter, said by status()'s
                    # caller as "could not load", never a crash.
                    _models = None
        return _models


def reload() -> None:
    global _models
    with _LOCK:
        _models = _UNSET


class Spotter:
    """openWakeWord's streaming front end, fed 16 kHz int16-valued samples.

    `feed()` takes any number of samples and returns one score per full
    80 ms step completed. Stateful, one per stream; not thread-safe.
    """

    def __init__(self, models: "_Models"):
        self.m = models
        self.reset()

    def reset(self) -> None:
        self.raw = np.zeros(480, dtype=np.float32)
        self.pending = np.zeros(0, dtype=np.float32)
        self.mel = np.ones((MEL_WINDOW, 32), dtype=np.float32)
        # Upstream fills the embedding buffer from 4 s of low noise; silence
        # does the same job (the first scores are ignored either way) and is
        # the same on every device, which noise from a random generator is not.
        spec = self.m.melspec(np.zeros(SAMPLE_RATE * 4, dtype=np.float32))
        wins = np.stack([spec[i:i + MEL_WINDOW]
                         for i in range(0, spec.shape[0] - MEL_WINDOW + 1, 8)])
        self.feats = self.m.emb.run(None, {self.m.emb_in: wins[..., None].astype(np.float32)})[0].reshape(-1, 96)
        self.steps = 0

    def feed(self, samples) -> list:
        x = np.concatenate([self.pending, np.asarray(samples, dtype=np.float32)])
        scores = []
        n = (len(x) // CHUNK) * CHUNK
        for i in range(0, n, CHUNK):
            self.raw = np.concatenate([self.raw, x[i:i + CHUNK]])[-MEL_INPUT:]
            self.mel = np.vstack([self.mel, self.m.melspec(self.raw)])[-(MEL_WINDOW + 8 * 10):]
            self.feats = np.vstack([self.feats, self.m.embed(self.mel[-MEL_WINDOW:])])[-(EMB_WINDOW * 2):]
            s = self.m.score(self.feats[-EMB_WINDOW:])
            self.steps += 1
            scores.append(0.0 if self.steps <= WARMUP_SCORES else s)
        self.pending = x[n:]
        return scores


# --------------------------------------------------------------------------
#   Resampling - the desktop records at its microphone's own rate.
# --------------------------------------------------------------------------

def to_16k(samples, sample_rate: int):
    """float samples at `sample_rate` -> float samples at 16 kHz.

    A windowed-sinc low-pass first, so a 48 kHz microphone's energy above
    8 kHz is removed rather than folded down into the speech band, then
    linear interpolation onto the 16 kHz grid.
    """
    x = np.asarray(samples, dtype=np.float32)
    sr = int(sample_rate or SAMPLE_RATE)
    if sr == SAMPLE_RATE or len(x) == 0:
        return x
    if sr > SAMPLE_RATE:
        cutoff = 0.45 * SAMPLE_RATE / sr          # cycles per input sample
        taps = 63
        n = np.arange(taps) - (taps - 1) / 2
        h = 2 * cutoff * np.sinc(2 * cutoff * n) * np.hanning(taps)
        h /= h.sum()
        x = np.convolve(x, h.astype(np.float32), mode="same")
    n_out = int(round(len(x) * SAMPLE_RATE / sr))
    if n_out <= 1:
        return x[:1]
    pos = np.arange(n_out) * (sr / SAMPLE_RATE)
    return np.interp(pos, np.arange(len(x)), x).astype(np.float32)


# --------------------------------------------------------------------------
#   One clip
# --------------------------------------------------------------------------

@dataclass
class Spot:
    #: A spotter ran on the clip. False: no models, or they failed to load.
    ran: bool
    heard: bool = False
    score: float = 0.0
    #: Seconds into the clip where the best score landed (end of the phrase).
    at: float = 0.0
    threshold: float = 0.5
    why: str = ""


def spot(samples, sample_rate: int = SAMPLE_RATE) -> Spot:
    """Is "hey Jarvis" anywhere in this clip? `samples` are floats in -1..1."""
    thr = threshold()
    if np is None:
        return Spot(False, threshold=thr, why="numpy is not installed")
    models = _load()
    if models is None:
        why = status()["why"] or "the wake-word models could not be loaded"
        return Spot(False, threshold=thr, why=why)
    x = to_16k(samples, sample_rate)
    lead = np.zeros(int(LEAD_IN_SECONDS * SAMPLE_RATE), dtype=np.float32)
    # Half a second of silence after, so a phrase at the very end of the clip
    # has its last step scored.
    tail = np.zeros(SAMPLE_RATE // 2, dtype=np.float32)
    pcm = np.clip(np.concatenate([lead, x, tail]), -1.0, 1.0) * 32767.0
    with _LOCK:
        scores = Spotter(models).feed(pcm)
    if not scores:
        return Spot(True, threshold=thr)
    best = int(np.argmax(scores))
    score = float(scores[best])
    at = max(0.0, (best + 1) * CHUNK / SAMPLE_RATE - LEAD_IN_SECONDS)
    return Spot(True, heard=score >= thr, score=round(score, 4),
                at=round(at, 2), threshold=thr)


# --------------------------------------------------------------------------
#   The words, once the owner check has passed and the clip is transcribed.
# --------------------------------------------------------------------------

import re  # noqa: E402

#: How speech-to-text writes "Jarvis" when it mishears it. Measured on the
#: synthesised clips in backend/README.md: "Javis", "Jervis" and "Jarvis".
_NAME = re.compile(r"^(j[ae]r?v[iu]s|jarvis's|jervis)$")
_CUES = {"hey", "hi", "hello", "ok", "okay", "yo", "oi", "hay", "a"}


def split_wake(text: str) -> tuple:
    """(was the wake phrase at the start of this?, the words after it).

    The spotter only says a clip SOUNDED like "hey Jarvis". The transcript is
    the second opinion, and the one that stops "the computer in that film was
    called Jarvis" from counting: the name must be the first or second word,
    or come straight after "hey"/"hi"/"okay". The phone's clip includes a
    little audio from before the phrase, so the second rule matters.
    """
    text = text or ""
    words = list(re.finditer(r"[A-Za-z']+", text))
    for i, m in enumerate(words):
        if not _NAME.match(m.group(0).lower()):
            continue
        prev = words[i - 1].group(0).lower() if i else ""
        if i <= 1 or prev in _CUES:
            rest = re.sub(r"^[\s,.;:!?\-]+", "", text[m.end():]).strip()
            if not re.search(r"[A-Za-z0-9]", rest):
                rest = ""
            return True, rest
        return False, ""
    return False, ""


if __name__ == "__main__":
    for k, v in status().items():
        print(f"  {k:<12} {v}")
