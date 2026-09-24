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

THE OWNER'S OWN "HEY JARVIS" (added 2026-09-24). openWakeWord's answer to
"it fires on other people" is a "custom verifier": a second, tiny model
trained on ONE person's "hey Jarvis" that runs only when the first model
is at least a little interested (score >= 0.1) and then decides instead of
it. It is a logistic regression - 1,536 weights and a bias - over the same
16 x 96 numbers the first model looks at. openWakeWord trains it with
scikit-learn; this file trains the same shape with a few lines of numpy
(train_verifier), because scikit-learn is 30 MB of dependency for one
dot product.

What it learns from:
  positive  the moments the spotter fires in the owner's own "Train my
            voice" sentences that start with "hey Jarvis"
  negative  everything else the owner said in the same training, and a
            BANK of other voices saying "hey Jarvis" (jarvis_wakebank.py:
            voices synthesised with Piper's LibriTTS-R model, never the
            owner, shipped as numbers, not audio)
The bank is what makes it about the owner's VOICE rather than about the
phrase: trained on the owner alone it still let 55% of other (synthetic)
voices through; with the bank, 6% - while letting every one of the owners'
own through (backend/README.md, "Voice, part two").

It is built on the PC when the "Train my voice" card is approved, from the
same clips (build_verifier, here), and saved next to the voice print
(voice/wake-verifier*.json) by jarvis_voice_enroll.py - this module still
writes nothing itself.
It is used on the PC only: the phone's own spotter has no verifier, and
every clip the phone sends is checked here, with it, before anything else.
No verifier file means the first model decides alone, exactly as before.

"STOP" (added 2026-09-24, spot_stop). A second tiny model on the same 16 x
96 window, openWakeWord's own head shape (1,536 -> 32 -> 32 -> 1), trained
here for one word - "stop" (and "Jarvis, stop", "okay, stop") - on
synthetic voices (jarvis_stopword.py holds its numbers; the phone ships the
same numbers in assets/wakeword/stop_head.bin). Like the wake word it hears
sound and returns one number; it knows no other word. It is used only to
silence Jarvis while it is speaking: stopping speech is harmless, so it may
act before the voice check, and it does nothing else.
"""
from __future__ import annotations

import json
import math
import threading
import time
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
    _STOP_CACHE.clear()


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

    def feed(self, samples, windows: Optional[list] = None) -> list:
        """`windows`, if given, gets the 16 x 96 window each score was made
        from, in step with the scores (for the verifier)."""
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
            if windows is not None:
                windows.append(self.feats[-EMB_WINDOW:].copy())
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
    #: The owner's verifier decided (there is one, and the first model was
    #: at least a little interested). Its best probability is
    #: `verifier_score`; `score` stays the first model's.
    verified: bool = False
    verifier_score: float = 0.0


def _clip_steps(models, samples, sample_rate: int):
    """(scores, windows) for one clip, streamed exactly as spot() does."""
    x = to_16k(samples, sample_rate)
    lead = np.zeros(int(LEAD_IN_SECONDS * SAMPLE_RATE), dtype=np.float32)
    # Half a second of silence after, so a phrase at the very end of the clip
    # has its last step scored.
    tail = np.zeros(SAMPLE_RATE // 2, dtype=np.float32)
    pcm = np.clip(np.concatenate([lead, x, tail]), -1.0, 1.0) * 32767.0
    windows: list = []
    with _LOCK:
        scores = Spotter(models).feed(pcm, windows)
    return np.asarray(scores, dtype=np.float32), windows


def spot(samples, sample_rate: int = SAMPLE_RATE, mic: str = "") -> Spot:
    """Is "hey Jarvis" anywhere in this clip? `samples` are floats in -1..1.

    With the owner's verifier for `mic` (or the one without a mic), it has
    the last word on every step where the first model scored at least
    VERIFIER_GATE - openWakeWord's own rule for custom verifiers."""
    thr = threshold()
    if np is None:
        return Spot(False, threshold=thr, why="numpy is not installed")
    models = _load()
    if models is None:
        why = status()["why"] or "the wake-word models could not be loaded"
        return Spot(False, threshold=thr, why=why)
    scores, windows = _clip_steps(models, samples, sample_rate)
    if not len(scores):
        return Spot(True, threshold=thr)
    best = int(np.argmax(scores))
    score = float(scores[best])
    at = max(0.0, (best + 1) * CHUNK / SAMPLE_RATE - LEAD_IN_SECONDS)
    ver = load_verifier(mic)
    gated = [i for i, s in enumerate(scores) if s >= VERIFIER_GATE]
    if ver is None or not gated:
        return Spot(True, heard=score >= thr, score=round(score, 4),
                    at=round(at, 2), threshold=thr)
    probs = ver.probabilities(np.stack([windows[i] for i in gated]))
    k = int(np.argmax(probs))
    v = float(probs[k])
    at = max(0.0, (gated[k] + 1) * CHUNK / SAMPLE_RATE - LEAD_IN_SECONDS)
    return Spot(True, heard=v >= ver.threshold, score=round(score, 4), at=round(at, 2),
                threshold=thr, verified=True, verifier_score=round(v, 4))


# --------------------------------------------------------------------------
#   "Stop": a second head on the same sound fingerprint
# --------------------------------------------------------------------------

STOP_MAGIC = b"JSTOP1\x00\x00"


def parse_stop_head(raw: bytes) -> dict:
    """The stop head's numbers from its file format (shared with the phone's
    assets/wakeword/stop_head.bin): 8-byte magic, int32 hidden size, int32
    input size (1536), then float32 little-endian W1 b1 g1 c1 W2 b2 g2 c2 W3
    b3 (W as [in][out]). Raises ValueError on anything else."""
    if len(raw) < 16 or raw[:8] != STOP_MAGIC:
        raise ValueError("not a stop-word head")
    h = int.from_bytes(raw[8:12], "little")
    d = int.from_bytes(raw[12:16], "little")
    if not (1 <= h <= 512 and d == EMB_WINDOW * 96):
        raise ValueError("stop-word head has the wrong shape")
    shapes = [("W1", (d, h)), ("b1", (h,)), ("g1", (h,)), ("c1", (h,)),
              ("W2", (h, h)), ("b2", (h,)), ("g2", (h,)), ("c2", (h,)),
              ("W3", (h, 1)), ("b3", (1,))]
    need = sum(int(np.prod(s)) for _, s in shapes) * 4
    if len(raw) != 16 + need:
        raise ValueError("stop-word head is the wrong length")
    flat = np.frombuffer(raw[16:], dtype="<f4")
    if not np.all(np.isfinite(flat)):
        raise ValueError("stop-word head holds a non-number")
    out, at = {}, 0
    for name, shape in shapes:
        n = int(np.prod(shape))
        out[name] = flat[at:at + n].reshape(shape).astype(np.float64)
        at += n
    return out


def stop_probabilities(head: dict, windows):
    """The head's forward pass: two Linear -> LayerNorm -> ReLU, a Linear, a
    sigmoid - the same arithmetic as the phone's StopWord.kt."""
    x = np.asarray(windows, dtype=np.float64).reshape(len(windows), -1)

    def ln(a, g, c):
        mu = a.mean(axis=1, keepdims=True)
        var = a.var(axis=1, keepdims=True)
        return (a - mu) / np.sqrt(var + 1e-5) * g + c
    r1 = np.maximum(ln(x @ head["W1"] + head["b1"], head["g1"], head["c1"]), 0)
    r2 = np.maximum(ln(r1 @ head["W2"] + head["b2"], head["g2"], head["c2"]), 0)
    z = np.clip((r2 @ head["W3"] + head["b3"]).reshape(-1), -60, 60)
    return 1.0 / (1.0 + np.exp(-z))


_STOP_CACHE: dict = {}


def _stop_head():
    """(head, threshold) from jarvis_stopword.py, or None."""
    if "head" not in _STOP_CACHE:
        try:
            import jarvis_stopword
            _STOP_CACHE["head"] = (parse_stop_head(jarvis_stopword.head_bytes()),
                                   float(jarvis_stopword.THRESHOLD))
        except Exception:
            _STOP_CACHE["head"] = None
    return _STOP_CACHE["head"]


def stop_status() -> dict:
    loaded = _stop_head() if np is not None else None
    if loaded is None:
        return {"available": False, "threshold": 0.0,
                "why": "jarvis_stopword.py is missing or unreadable"}
    return {"available": bool(status()["available"]), "threshold": loaded[1],
            "why": "" if status()["available"] else status()["why"]}


def spot_stop(samples, sample_rate: int = SAMPLE_RATE) -> Spot:
    """Is the stop word in this clip? One number per 80 ms step, the best is
    `score`. Only the caller decides what a short clip with it means."""
    loaded = _stop_head() if np is not None else None
    if loaded is None:
        return Spot(False, why="the stop-word model is not installed (jarvis_stopword.py)")
    head, thr = loaded
    models = _load()
    if models is None:
        return Spot(False, threshold=thr,
                    why=status()["why"] or "the wake-word models could not be loaded")
    scores, windows = _clip_steps(models, samples, sample_rate)
    if not windows:
        return Spot(True, threshold=thr)
    # The first scores after a start are primed on silence (WARMUP_SCORES).
    probs = stop_probabilities(head, np.stack(windows))
    probs[:WARMUP_SCORES] = 0.0
    best = int(np.argmax(probs))
    p = float(probs[best])
    at = max(0.0, (best + 1) * CHUNK / SAMPLE_RATE - LEAD_IN_SECONDS)
    return Spot(True, heard=p >= thr, score=round(p, 4), at=round(at, 2), threshold=thr)


# --------------------------------------------------------------------------
#   The owner's verifier: a second stage that knows the owner's "hey Jarvis"
# --------------------------------------------------------------------------

#: The first model must score at least this for the verifier to be asked
#: (openWakeWord's `custom_verifier_threshold`).
VERIFIER_GATE = 0.1
#: The verifier's own bar. 0.4, not openWakeWord's 0.5: with every Kokoro
#: voice in turn as "the owner", 0.4 let all 33 of the owners' own "hey
#: Jarvis" clips through and 21 of 330 other voices'; 0.5 turned 4 of the
#: owners away (13 of 330 others through). Refusing the owner is the
#: failure people notice, and the full voice check still follows.
VERIFIER_THRESHOLD = 0.4
VERIFIER_VERSION = 1
#: Fewer "hey Jarvis" training sentences than this that the spotter heard,
#: and no verifier is built - it would learn one recording, not a voice.
MIN_VERIFIER_CLIPS = 2
#: openWakeWord's own C for its verifier's logistic regression is 0.001 (a
#: lot of smoothing). With the bank of other voices, 0.01 separated the
#: owner from the others best at the bar above; 0.003 needed a bar so low
#: (0.2) to keep every owner that 38 of 330 others got through. Measured on
#: synthetic voices - backend/README.md, "Voice, part two".
VERIFIER_C = 0.01
#: A "hey Jarvis" sentence's windows this many steps (80 ms each) after
#: the phrase are the owner saying something else - negatives.
_AFTER_PHRASE = 20


def _voice_dir() -> Path:
    """The folder the voice print is in (jarvis_voice.PROFILE_PATH's), so
    the verifier always sits beside the voice it was trained with - also
    when a test points the voice print somewhere temporary."""
    try:
        import jarvis_voice
        return Path(jarvis_voice.PROFILE_PATH).parent
    except Exception:
        return _config_dir() / "voice"


def verifier_path(mic: str = "") -> Path:
    """voice/wake-verifier.json, or wake-verifier-<mic>.json - beside the
    voice print, which is where the rest of the owner's voice lives."""
    safe = "".join(c for c in str(mic or "").lower() if c.isalnum())[:16]
    name = f"wake-verifier-{safe}.json" if safe else "wake-verifier.json"
    return _voice_dir() / name


class Verifier:
    """A loaded verifier: logit = window . w + b, over the flattened 16 x 96
    window (the standard-scaling is folded into w and b when saved)."""

    def __init__(self, doc: dict):
        w = np.asarray(doc["w"], dtype=np.float64)
        if w.shape != (EMB_WINDOW * 96,) or not np.all(np.isfinite(w)):
            raise ValueError("verifier weights have the wrong shape")
        self.w = w
        self.b = float(doc["b"])
        if not math.isfinite(self.b):
            raise ValueError("verifier bias is not a number")
        self.threshold = min(0.99, max(0.05, float(doc.get("threshold", VERIFIER_THRESHOLD))))
        self.positives = int(doc.get("positives", 0))
        self.mic = str(doc.get("mic", ""))

    def probabilities(self, windows):
        x = np.asarray(windows, dtype=np.float64).reshape(len(windows), -1)
        z = np.clip(x @ self.w + self.b, -60, 60)
        return 1.0 / (1.0 + np.exp(-z))


_VER_CACHE: dict = {}


def _read_verifier(p: Path) -> Optional[Verifier]:
    try:
        st = p.stat()
    except OSError:
        return None
    key = (str(p), st.st_size, st.st_mtime_ns)
    with _LOCK:
        if key in _VER_CACHE:
            return _VER_CACHE[key]
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(doc, dict) or doc.get("version") != VERIFIER_VERSION:
            raise ValueError("not a verifier this version reads")
        ver = Verifier(doc)
    except Exception:
        # Unreadable: the first model decides alone, as it did before any
        # verifier existed. verifier_status() says so.
        ver = None
    with _LOCK:
        _VER_CACHE.clear()
        _VER_CACHE[key] = ver
    return ver


def _verifier_order(mic: str = "") -> list:
    """The verifiers a clip from `mic` is checked with, in order - the same
    order as the voice prints they were trained beside (jarvis_voice
    .lookup_order): its own microphone's first, then the others."""
    m = str(mic or "").strip().lower()
    if m == "desktop":
        names = ("desktop", "phone", "")
    elif m == "phone":
        names = ("phone", "", "desktop")
    else:
        names = ("", "phone", "desktop")
    return [verifier_path(n) for n in names]


def load_verifier(mic: str = "") -> Optional[Verifier]:
    """The first verifier in `mic`'s order that exists, else None."""
    for p in _verifier_order(mic):
        if p.is_file():
            return _read_verifier(p)
    return None


def verifier_status(mic: str = "") -> dict:
    """For status(): is there a verifier, from how much, and is it readable."""
    for p in _verifier_order(mic):
        if p.is_file():
            ver = _read_verifier(p)
            if ver is None:
                return {"trained": False, "positives": 0,
                        "why": f"{p.name} could not be read - train your voice again"}
            return {"trained": True, "positives": ver.positives, "why": ""}
    return {"trained": False, "positives": 0,
            "why": ("not trained yet - it is built when you train your voice, from the "
                    "sentences that start with \"hey Jarvis\"")}


def _fit_logistic(x, y, c: float = VERIFIER_C, iters: int = 3000):
    """L2 logistic regression by gradient descent on standardised inputs -
    scikit-learn's LogisticRegression(C=c) objective, without scikit-learn.
    Returns (w, b) for the RAW inputs, the scaling folded in."""
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    mu = x.mean(axis=0)
    sd = x.std(axis=0) + 1e-6
    z = (x - mu) / sd
    n = len(y)
    w = np.zeros(z.shape[1])
    b = 0.0
    lam = 1.0 / (c * n)
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-np.clip(z @ w + b, -60, 60)))
        w -= 0.1 * (z.T @ (p - y) / n + lam * w)
        b -= 0.1 * float(np.mean(p - y))
    w_raw = w / sd
    return w_raw, b - float(mu @ w_raw)


def _bank():
    """Other voices' "hey Jarvis" windows (float32, n x 1536), or None."""
    try:
        import jarvis_wakebank
        return jarvis_wakebank.windows()
    except Exception:
        return None


def build_verifier(clips, sample_rate: int = SAMPLE_RATE, mic: str = "") -> dict:
    """Builds the owner's verifier from the "Train my voice" clips (float
    samples in -1..1, one array per sentence). Never raises, never writes:
    the answer says whether it was built (`doc` is then the file's content,
    for jarvis_voice_enroll to save) and, if not, why in plain words.

    Positives are the windows where the spotter fires (>= its threshold) in
    the clips it fires on at all; negatives are every window of the other
    clips, the windows well after the phrase in the "hey Jarvis" ones, and
    the bank of other voices."""
    if np is None:
        return {"built": False, "why": "numpy is not installed"}
    models = _load()
    if models is None:
        return {"built": False, "why": status()["why"] or "the wake-word models could not be loaded"}
    thr = threshold()
    pos, neg, heard = [], [], 0
    for c in clips:
        scores, windows = _clip_steps(models, c, sample_rate)
        if not len(scores):
            continue
        if float(scores.max()) >= thr:
            heard += 1
            pos += [windows[i] for i in np.where(scores >= thr)[0]]
            neg += windows[int(np.argmax(scores)) + _AFTER_PHRASE:]
        else:
            neg += windows
    if heard < MIN_VERIFIER_CLIPS:
        return {"built": False, "clips": heard,
                "why": (f"\"hey Jarvis\" was heard in {heard} of the sentences; it needs "
                        f"at least {MIN_VERIFIER_CLIPS}")}
    bank = _bank()
    x = [np.asarray(w, dtype=np.float32).reshape(-1) for w in pos + neg]
    y = [1] * len(pos) + [0] * len(neg)
    if bank is not None and len(bank):
        x += list(np.asarray(bank, dtype=np.float32))
        y += [0] * len(bank)
    w, b = _fit_logistic(np.stack(x), np.asarray(y))
    doc = {"version": VERIFIER_VERSION, "model": PHRASE_MODELS.get(phrase(), ""),
           "mic": str(mic or ""), "w": [round(float(v), 7) for v in w], "b": float(b),
           "threshold": VERIFIER_THRESHOLD, "gate": VERIFIER_GATE,
           "positives": len(pos), "negatives": len(y) - len(pos), "clips": heard,
           "bank": int(len(bank)) if bank is not None else 0, "created": time.time()}
    return {"built": True, "clips": heard, "positives": len(pos), "bank": doc["bank"],
            "doc": doc}


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
