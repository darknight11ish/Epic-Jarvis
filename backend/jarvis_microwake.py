"""jarvis_microwake.py - a SECOND "hey Jarvis" detector, used only to confirm.

NEW MODULE, shipped whole beside jarvis_hud.py (apply-patches.ps1 copies it).
Part of "Better voice", the owner's choice of 2026-09-28.

WHAT IT IS. microWakeWord's own "hey Jarvis" model, run by the
`pymicro-wakeword` package (Apache-2.0, github.com/OHF-Voice/pymicro-wakeword,
version 2.5.0; its sound front end is `pymicro-features`, Apache-2.0). The
package ships a 52 KB TensorFlow Lite model, hey_jarvis.tflite, by Kevin
Ahrendt - byte-identical to the one in ESPHome's micro-wake-word-models
repository (Apache-2.0), checked 2026-09-28 by SHA-256 - and a TensorFlow
Lite runtime for Windows (tensorflowlite_c.dll) inside the wheel.

Like openWakeWord (jarvis_wakeword.py) it hears SOUND and returns one
number - how much this sounds like "hey Jarvis". It has no vocabulary and
writes no words down, so it may run before the voice check, like the first
detector.

WHY A SECOND ONE. It has a different front end (40 log-mel-style
features every 10 ms, from TensorFlow's micro front end) and a different
model, trained on different data, from openWakeWord's (Google's speech
embedding). Two detectors built differently rarely wake on the same wrong
sound. So with the owner's setting `wake_confirm = "both"`
(jarvis_voice.settings()), jarvis_speech.hear() takes a "hey Jarvis" only
when BOTH heard it within AGREE_SECONDS of each other. Fewer false
wake-ups; possibly more missed ones. Its authors publish no false-alarm
numbers for "hey Jarvis", so it is measured on this PC first
(jarvis_bakeoff.py --wake2) - and it is OFF until the owner chooses it.

ONLY EVER A "NO". confirm() can turn a wake the first detector heard into
"not heard"; it can never make a wake out of nothing. It runs only after
openWakeWord said yes, and only on the PC.

FAIL CLOSED ON THE MODEL, OPEN ON THE PACKAGE. The model file must be the
pinned one (MODEL_SHA256): a different file is never used, and status()
says why. When the package is missing (or the model is not the pinned one),
the setting cannot be switched on (jarvis_voice.setting_blocker), and if it
was on before, "hey Jarvis" works as it did before this module - openWakeWord
alone - and status() says so plainly. The voice check still runs after
either way: waking is not permission to do anything.

NOTHING IS KEPT. No audio, score or clip is written or logged.
"""
from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    import numpy as np
except Exception:  # pragma: no cover - numpy comes with sherpa-onnx
    np = None  # type: ignore

#: The package and the version this was written and measured against.
PACKAGE = "pymicro-wakeword"
VERSION = "2.5.0"
#: hey_jarvis.tflite inside pymicro-wakeword 2.5.0 (every wheel), and in
#: github.com/esphome/micro-wake-word-models, models/v2/ - 52,272 bytes.
MODEL_FILE = "hey_jarvis.tflite"
MODEL_SHA256 = "21a7976add39ee24ec96c63d96b7aaa18e24d1d9824b963e451da8feb4b78b77"
#: The model's own bar (its hey_jarvis.json, "probability_cutoff"): the mean
#: of the last few scores must be ABOVE it. Not changed here.
CUTOFF = 0.97
#: How far apart, in seconds, the two detectors' "heard it" may be and still
#: count as hearing the same "hey Jarvis". openWakeWord's moment is where its
#: best score landed (about the end of the phrase); microWakeWord's are the
#: 10 ms steps whose score was over its bar. Measured in the dev container on
#: Kokoro's 11 voices (backend/README.md, "Better voice"): on all 42 clips
#: both heard, the two landed within 0.08 s of each other; 1.0 s leaves room
#: for a real voice and a real room without letting a second, unrelated
#: sound a few seconds away count.
AGREE_SECONDS = 1.0
SAMPLE_RATE = 16000
#: Quiet put before and after a clip, so the model's first steps (which
#: need a few frames of history) and its last ones are scored.
LEAD_IN_SECONDS = 0.5
TAIL_SECONDS = 0.5
#: One feature step: 10 ms.
STEP_SECONDS = 0.01

_LOCK = threading.RLock()
_UNSET = object()
_model = _UNSET
_why_not = ""
_HASH: dict = {}


def _package():
    """The pymicro_wakeword module, or raises ImportError."""
    import pymicro_wakeword  # noqa: raises ImportError when not installed
    return pymicro_wakeword


def _version() -> str:
    try:
        from importlib.metadata import version
        return version(PACKAGE)
    except Exception:
        return ""


def model_path() -> Optional[Path]:
    """Where the package keeps its hey_jarvis model, or None."""
    try:
        pkg = _package()
    except Exception:
        return None
    return Path(pkg.__file__).resolve().parent / "models" / MODEL_FILE


def _sha256(p: Path) -> str:
    try:
        st = p.stat()
    except OSError:
        return ""
    key = (str(p), st.st_size, st.st_mtime_ns)
    got = _HASH.get(key)
    if got is None:
        try:
            got = hashlib.sha256(p.read_bytes()).hexdigest()
        except OSError:
            return ""
        _HASH.clear()
        _HASH[key] = got
    return got


def status() -> dict:
    """Can the second detector be used here? Cheap: an import and one hash
    of a 52 KB file; no model is loaded to answer. {"available", "why",
    "engine", "version", "cutoff", "agree_seconds"}."""
    out = {"available": False, "why": "", "engine": "microWakeWord (pymicro-wakeword)",
           "version": "", "cutoff": CUTOFF, "agree_seconds": AGREE_SECONDS}
    if np is None:
        out["why"] = "numpy is not installed in the Python that runs Jarvis"
        return out
    try:
        _package()
    except Exception:
        out["why"] = ("the pymicro-wakeword package is not installed in the Python that "
                      "runs Jarvis - backend/README.md, \"Better voice\", has the one line "
                      "that installs it")
        return out
    out["version"] = _version()
    p = model_path()
    if p is None or not p.is_file():
        out["why"] = (f"pymicro-wakeword {out['version'] or '?'} has no {MODEL_FILE} "
                      f"model, so it cannot hear \"hey Jarvis\"")
        return out
    if _sha256(p) != MODEL_SHA256:
        out["why"] = (f"the {MODEL_FILE} inside pymicro-wakeword {out['version'] or '?'} is "
                      f"not the one this was measured with (its SHA-256 is different), so "
                      f"it is not used - install version {VERSION} with the line in "
                      f"backend/README.md")
        return out
    with _LOCK:
        if _model is None and _why_not:
            out["why"] = _why_not
            return out
    out["available"] = True
    return out


def _load():
    """The loaded model, or None (and _why_not says why). Loaded once."""
    global _model, _why_not
    with _LOCK:
        if _model is _UNSET:
            st = status()
            if not st["available"]:
                _model, _why_not = None, st["why"]
            else:
                try:
                    pkg = _package()
                    _model = pkg.MicroWakeWord.from_config(model_path().with_suffix(".json"))
                    _why_not = ""
                except Exception as exc:
                    _model = None
                    _why_not = (f"microWakeWord's model would not load "
                                f"({type(exc).__name__})")
        return _model


def reload() -> None:
    """Forget the loaded model (and why it failed), so the next use looks
    again - after the package is installed, say."""
    global _model, _why_not
    with _LOCK:
        _model, _why_not = _UNSET, ""


@dataclass
class MicroSpot:
    #: The detector ran on the clip. False: not installed, or it failed.
    ran: bool
    heard: bool = False
    #: The best score (the model's own running mean), 0..1.
    score: float = 0.0
    #: Seconds into the clip of the FIRST step over the bar.
    at: float = 0.0
    #: Seconds into the clip of every step over the bar.
    times: list = field(default_factory=list)
    cutoff: float = CUTOFF
    why: str = ""


def _to_int16_bytes(samples, sample_rate: int) -> bytes:
    """float samples in -1..1 at `sample_rate` -> 16 kHz 16-bit mono bytes,
    with quiet before and after (see LEAD_IN_SECONDS)."""
    try:
        import jarvis_wakeword
        x = jarvis_wakeword.to_16k(samples, sample_rate)
    except Exception:
        x = np.asarray(samples, dtype=np.float32)
        if int(sample_rate or SAMPLE_RATE) != SAMPLE_RATE and len(x):
            n = int(round(len(x) * SAMPLE_RATE / float(sample_rate)))
            x = np.interp(np.arange(n) * (sample_rate / SAMPLE_RATE),
                          np.arange(len(x)), x).astype(np.float32)
    lead = np.zeros(int(LEAD_IN_SECONDS * SAMPLE_RATE), dtype=np.float32)
    tail = np.zeros(int(TAIL_SECONDS * SAMPLE_RATE), dtype=np.float32)
    pcm = np.clip(np.concatenate([lead, np.asarray(x, dtype=np.float32), tail]), -1.0, 1.0)
    return (pcm * 32767.0).astype("<i2").tobytes()


def scores(model, samples, sample_rate: int = SAMPLE_RATE) -> list:
    """[(seconds into the clip, score)] - one per 10 ms feature step, from a
    fresh model state. `model` is a loaded MicroWakeWord (or a test's
    stand-in with `reset()` and `process_streaming_prob(features)`)."""
    pkg = _package()
    feats = pkg.MicroWakeWordFeatures()
    model.reset()
    out = []
    k = 0
    for f in feats.process_streaming(_to_int16_bytes(samples, sample_rate)):
        p = model.process_streaming_prob(f)
        k += 1
        t = k * STEP_SECONDS - LEAD_IN_SECONDS
        out.append((round(t, 3), float(p or 0.0)))
    return out


def spot(samples, sample_rate: int = SAMPLE_RATE) -> MicroSpot:
    """Did microWakeWord hear "hey Jarvis" anywhere in this clip?"""
    if np is None:
        return MicroSpot(False, why="numpy is not installed")
    with _LOCK:
        m = _load()
        if m is None:
            return MicroSpot(False, why=_why_not or "microWakeWord could not be loaded")
        try:
            sc = scores(m, samples, sample_rate)
        except Exception as exc:
            return MicroSpot(False, why=f"microWakeWord failed on this clip "
                                        f"({type(exc).__name__})")
    over = [max(0.0, t) for t, p in sc if p > CUTOFF]
    best = max((p for _t, p in sc), default=0.0)
    return MicroSpot(True, heard=bool(over), score=round(best, 4),
                     at=over[0] if over else 0.0, times=over)


def agree(first_at: float, second: MicroSpot, window: float = AGREE_SECONDS) -> bool:
    """Did the second detector hear "hey Jarvis" within `window` seconds of
    the moment the first one did (`first_at`, seconds into the same clip)?"""
    if not second.ran or not second.heard:
        return False
    return any(abs(float(t) - float(first_at)) <= window for t in second.times)


def confirm(samples, sample_rate: int, first_at: float) -> tuple:
    """(verdict, MicroSpot) for a clip openWakeWord already heard "hey
    Jarvis" in, at `first_at` seconds. verdict: "agreed", "disagreed", or
    "unavailable" (the detector could not run - the caller then decides as
    before, openWakeWord alone, and says so)."""
    s = spot(samples, sample_rate)
    if not s.ran:
        return "unavailable", s
    return ("agreed" if agree(first_at, s) else "disagreed"), s


if __name__ == "__main__":
    import sys
    for k, v in status().items():
        print(f"  {k:<14} {v}")
    sys.exit(0 if status()["available"] else 1)
