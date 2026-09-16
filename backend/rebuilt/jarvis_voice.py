"""jarvis_voice.py - is this the owner speaking?

REBUILT. The original is gone. jarvis_speech.py is the only caller and it
fixes the interface exactly:

    embedder = jarvis_voice.EcapaEmbedder()      # preferred
    embedder = jarvis_voice.Embedder()           # fallback, on any exception
    verdict  = jarvis_voice.verify(audio, embedder)
    verdict.is_owner / .score / .threshold / .mode / .reason
    v = jarvis_voice.status()
    load_profile(...)   VoiceProfile(...)   _cfg(...)

and `[voice]` in the config supplies every number:

    mode = "owner"        "only your enrolled voice may command it (the
                           default, because THE SAFE FAILURE IS TO IGNORE A
                           STRANGER)". "broad" accepts anyone.
    threshold = 0.35      cosine-similarity bar
                          "Enrolment lowers it automatically if your own
                           sample clips are loosely clustered, so a strict
                           value here cannot lock you out."

WHICH DIRECTION THIS FAILS IN, and why every branch below goes the same way.

A voice gate has two failure modes and they are not equal. Refusing the owner
is an annoyance: say it again, or use the keyboard. Accepting a stranger hands
the microphone of a machine with an approval queue to whoever is in the room.
So: no profile means refuse, an unreadable profile means refuse, a broken
embedder means refuse, a NaN score means refuse. The only thing that returns
is_owner=True is a real comparison against a real enrolment that really
cleared the bar.

The one exception is `mode = "broad"`, which is the owner explicitly choosing
otherwise, and it is reported in every verdict so nothing can be accepted
without it being visible why.

WHAT IS NOT HERE: the ECAPA model. `EcapaEmbedder` needs speechbrain or an
ONNX model file, and neither is installed by this file. jarvis_speech already
expects that - it wraps the constructor in try/except and falls back - so the
fallback is the honest path rather than a stub pretending to be a neural
speaker embedder. The fallback is spectral and it says `semantic = False`.
"""
from __future__ import annotations

import array
import json
import math
import os
import time
import wave
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional

try:
    import jarvis_framework as fw
except Exception:
    fw = None  # type: ignore


def _cfg(key: str, default=None):
    """Read `[voice]`. Same shape as jarvis_speech._cfg on purpose - its own
    docstring says "the two modules read the same section and must not
    disagree about where it lives"."""
    if fw is None:
        return default
    try:
        return fw.load_framework().get("voice", {}).get(key, default)
    except Exception:
        return default


def _profile_dir() -> Path:
    base = Path(fw.CONFIG_DIR) if fw is not None else Path.home() / ".openjarvis"
    return base / "voice"


PROFILE_PATH = Path(os.environ.get("JARVIS_VOICE_PROFILE")
                    or (_profile_dir() / "owner.json"))


# --------------------------------------------------------------------------
#   Embedders
# --------------------------------------------------------------------------

def _pcm(audio) -> list:
    """Whatever jarvis_speech handed us, as floats in -1..1.

    It may pass bytes of 16-bit PCM, a path to a wav, an array, or a list.
    Accepting all of them here rather than guessing one is the difference
    between a gate that works and a gate that throws and gets caught by the
    caller's except - which would read as "not the owner" for the wrong
    reason.
    """
    if audio is None:
        return []
    if isinstance(audio, (str, Path)) and Path(audio).is_file():
        try:
            with wave.open(str(audio), "rb") as w:
                raw = w.readframes(w.getnframes())
                width = w.getsampwidth()
        except Exception:
            return []
        if width != 2:
            return []
        a = array.array("h")
        a.frombytes(raw)
        return [x / 32768.0 for x in a]
    if isinstance(audio, (bytes, bytearray, memoryview)):
        b = bytes(audio)
        if len(b) % 2:
            b = b[:-1]
        a = array.array("h")
        a.frombytes(b)
        return [x / 32768.0 for x in a]
    try:
        vals = [float(x) for x in audio]
    except Exception:
        return []
    if vals and max(abs(v) for v in vals) > 1.5:
        return [v / 32768.0 for v in vals]      # looked like raw int16
    return vals


def _spectrum(x: list) -> list:
    """Magnitude spectrum via an iterative radix-2 FFT. Standard library only.

    len(x) must be a power of two; the caller guarantees it. Returns the first
    half (the rest is the mirror of a real signal).
    """
    n = len(x)
    re = list(x)
    im = [0.0] * n
    # bit-reversal permutation
    j = 0
    for i in range(1, n):
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j |= bit
        if i < j:
            re[i], re[j] = re[j], re[i]
            im[i], im[j] = im[j], im[i]
    size = 2
    while size <= n:
        ang = -2 * math.pi / size
        wr, wi = math.cos(ang), math.sin(ang)
        for start in range(0, n, size):
            cr, ci = 1.0, 0.0
            for k in range(start, start + size // 2):
                l = k + size // 2
                tr = re[l] * cr - im[l] * ci
                ti = re[l] * ci + im[l] * cr
                re[l], im[l] = re[k] - tr, im[k] - ti
                re[k], im[k] = re[k] + tr, im[k] + ti
                cr, ci = cr * wr - ci * wi, cr * wi + ci * wr
        size *= 2
    return [re[k] * re[k] + im[k] * im[k] for k in range(n // 2)]


def _norm(v: list) -> list:
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v] if n > 1e-12 else []


class Embedder:
    """The fallback: a coarse spectral signature. NOT a speaker model.

    `semantic = False` and `status()` reports it, because the difference
    matters to the owner: this distinguishes voices that are obviously
    different and will not reliably separate two similar ones. It exists so
    the microphone path works at all on a machine with no model - not so the
    gate can be described as working.

    A band-energy profile over a plain DFT. No numpy: the backend is
    standard-library-only and this runs on a two-second clip.
    """

    name = "spectral-v1"
    dim = 24
    semantic = False
    #: Whether a model is actually loaded. The surviving test's stub sets
    #: `available = True` on its subclass, so the real class has this and
    #: something reads it. False here would be a lie - the spectral path needs
    #: no model and always works - but it is NOT the same as `semantic`.
    available = True

    def embed(self, audio) -> list:
        x = _pcm(audio)
        if len(x) < 512:
            return []
        # Downsample by averaging so the transform stays cheap on a clip that
        # may be 16 kHz for several seconds.
        step = max(1, len(x) // 2048)
        x = [sum(x[i:i + step]) / step for i in range(0, len(x) - step, step)]
        n = 1
        while n * 2 <= min(len(x), 2048):
            n *= 2
        if n < 64:
            return []
        x = x[:n]
        # Hann window, or the band edges smear into each other.
        x = [v * (0.5 - 0.5 * math.cos(2 * math.pi * i / (n - 1)))
             for i, v in enumerate(x)]

        # A REAL FFT, because the hand-rolled band DFT that was here ALIASED.
        # It evaluated each bin with `for i in range(0, n, 8)` - striding the
        # INPUT by 8 - which with n=2048 uses 256 samples and makes bin k
        # identical to bin k+256. Measured: E(3) == E(259) exactly. The 24
        # "bands" therefore held 256 distinct frequencies repeated four times,
        # and a 120 Hz tone scored 0.61 against white noise. Nothing that
        # aliased could separate two voices, which is the only thing this
        # class is for.
        mags = _spectrum(x)
        half = len(mags)
        edges = [int(half * (b / self.dim) ** 1.5) for b in range(self.dim + 1)]
        bands = []
        for b in range(self.dim):
            lo, hi = edges[b], max(edges[b] + 1, edges[b + 1])
            bands.append(math.log1p(sum(mags[lo:min(hi, half)])))
        return _norm(bands)

    def embed_many(self, clips: list) -> list:
        """Several clips. Named separately because `embed` takes ONE.

        THE MISTAKE THIS FIXES. This class first had `embed(clips) ->
        [vector]`, matching jarvis_memory's embedder. It is the other shape
        here, and the surviving test proves it - test_speech.py's stub is

            class FakeEmbedder(V.Embedder):
                def embed(self, audio): return self.vec

        one clip in, one vector out. With the list signature the stub was
        never called at all: verify() went through the inherited spectral
        path, produced a 24-value vector against the fake's 4-value profile,
        and refused the owner on a length mismatch. The test caught it as
        "the owner was still identified" - failing SAFE, which is why it was
        a wrong answer rather than an open door.
        """
        return [self.embed(c) for c in clips]

    def status(self) -> str:
        """A short name for this embedder. The test's stub returns "fake"."""
        return self.name


class EcapaEmbedder(Embedder):
    """The real speaker model, if speechbrain is installed.

    RAISES from __init__ when it is not, and that is required rather than
    sloppy: jarvis_speech does

        try:    embedder = jarvis_voice.EcapaEmbedder()
        except: embedder = jarvis_voice.Embedder()

    so a constructor that quietly returned a working-looking object with
    spectral behaviour would make the fallback unreachable and mislabel every
    verdict as ECAPA.
    """

    name = "ecapa"
    dim = 192
    semantic = True

    def __init__(self, source: str = "speechbrain/spkrec-ecapa-voxceleb") -> None:
        from speechbrain.inference.speaker import EncoderClassifier  # noqa
        import torch  # noqa
        self._torch = torch
        self._m = EncoderClassifier.from_hparams(source=source)

    def embed(self, audio) -> list:
        x = _pcm(audio)
        if len(x) < 512:
            return []
        t = self._torch.tensor([x], dtype=self._torch.float32)
        with self._torch.no_grad():
            v = self._m.encode_batch(t).squeeze().tolist()
        return _norm([float(i) for i in (v if isinstance(v, list) else [v])])


# --------------------------------------------------------------------------
#   The enrolled profile
# --------------------------------------------------------------------------

@dataclass
class VoiceProfile:
    name: str = "owner"
    embedder: str = ""
    centroid: list = field(default_factory=list)
    threshold: float = 0.35
    samples: int = 0
    created: float = 0.0

    def as_dict(self) -> dict:
        return asdict(self)

    @property
    def usable(self) -> bool:
        return bool(self.centroid) and self.samples > 0

    def save(self, path: Optional[Path] = None) -> Path:
        p = Path(path or PROFILE_PATH)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.as_dict()), encoding="utf-8")
        return p


#: The lowest bar that still means anything. A cosine of 0 accepts every
#: vector that is not actively opposite; a negative one accepts everything.
#: Both were storable: a config or a hand-written profile saying
#: `threshold = -1` turned the gate off while still reading as "owner" mode.
MIN_THRESHOLD = 0.05


def _clamp_threshold(v) -> float:
    """A usable similarity bar, whatever was in the config or the profile."""
    try:
        t = float(v)
    except (TypeError, ValueError):
        return 0.35
    if not math.isfinite(t):
        return 0.35
    return max(MIN_THRESHOLD, min(1.0, t))


def load_profile(path: Optional[Path] = None) -> Optional[VoiceProfile]:
    """The enrolled voice, or None. Nine call sites.

    None on anything wrong - missing, unreadable, wrong shape. Every caller
    must treat None as "refuse", which is why this never returns an empty
    VoiceProfile: a profile object with no centroid could be compared against
    and would score 0.0 against everything, and a caller checking only for
    None would sail past it.
    """
    p = Path(path or PROFILE_PATH)
    if not p.is_file():
        return None
    try:
        raw = json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    # A LIST of numbers, specifically. `not raw.get("centroid")` only tested
    # truthiness, so a centroid of the STRING "1234" became [1.0,2.0,3.0,4.0]
    # and a dict {"0":1,...} iterated its keys - both built a usable profile,
    # and combined with the unnormalised cosine both accepted a stranger.
    if not isinstance(raw, dict):
        # A JSON list or string parses fine and is not a profile. Dropping
        # this guard while tightening the centroid check turned "refuse" into
        # AttributeError - caught by the suite, which is what it is for.
        return None
    cent = raw.get("centroid")
    if not isinstance(cent, (list, tuple)) or not cent:
        return None
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) for x in cent):
        return None
    try:
        prof = VoiceProfile(
            name=str(raw.get("name", "owner")),
            embedder=str(raw.get("embedder", "")),
            centroid=[float(x) for x in raw["centroid"]],
            threshold=_clamp_threshold(
                raw.get("threshold", _cfg("threshold", 0.35) or 0.35)),
            samples=int(raw.get("samples", 0)),
            created=float(raw.get("created", 0.0)))
    except (TypeError, ValueError):
        return None
    return prof if prof.usable else None


def enroll(clips: list, embedder=None, path: Optional[Path] = None) -> VoiceProfile:
    """Build a profile from sample clips.

    Implements the config's promise: "Enrolment lowers it automatically if
    your own sample clips are loosely clustered, so a strict value here cannot
    lock you out." The floor is the tightest measured self-similarity, minus a
    margin - never RAISED above the configured value, because loosening on
    your own account is a convenience and tightening silently would be a
    policy change nobody asked for.
    """
    emb = embedder or Embedder()
    vecs = [v for v in (emb.embed(c) for c in clips) if v]
    if not vecs:
        raise ValueError("no usable audio in those clips")

    dim = len(vecs[0])
    # One width. Mixed widths either raised IndexError or - worse, when the
    # short clip came first - silently truncated everyone to the shortest,
    # producing a 2-value "voice print" with no warning.
    vecs = [v for v in vecs if len(v) == dim]
    centroid = _norm([sum(v[i] for v in vecs) / len(vecs) for i in range(dim)])
    if not centroid:
        # All-zero or non-finite clips. Saving this reports enrolment as a
        # success and then locks the owner out for ever, because load_profile
        # correctly refuses it on every subsequent call.
        raise ValueError("those clips produced no usable voice print")

    configured = _clamp_threshold(_cfg("threshold", 0.35) or 0.35)
    if len(vecs) > 1:
        sims = [cosine(v, centroid) for v in vecs]
        loosest = min(sims)
        threshold = min(configured, round(max(MIN_THRESHOLD, loosest - 0.05), 4))
    else:
        threshold = configured

    prof = VoiceProfile(embedder=emb.name, centroid=centroid,
                        threshold=threshold, samples=len(vecs),
                        created=time.time())
    prof.save(path)
    return prof


# --------------------------------------------------------------------------
#   The verdict
# --------------------------------------------------------------------------

def cosine(a: list, b: list) -> float:
    """A real cosine: the dot product DIVIDED BY BOTH NORMS.

    THE BUG THIS FIXES, and it opened the gate. This was a clamped dot
    product that assumed both inputs were unit vectors:

        cosine([10, 0], [0.1, 0.995])  ->  1.0      (the true cosine is 0.10)

    Nothing in the embedder contract requires embed() to normalise -
    jarvis_speech.hear(raw, embedder=...) accepts any object with .embed - so
    any embedder returning its model's raw output scored 1.0 against
    everything and `verify` answered "recognised" to a stranger. An embedder
    stuck on a constant vector did the same.

    Clamping is still here for floating-point overshoot, but it can no longer
    hide an unnormalised input, because the division has already happened.
    """
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = na = nb = 0.0
    for x, y in zip(a, b):
        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            return 0.0
        dot += x * y
        na += x * x
        nb += y * y
    if not (math.isfinite(dot) and math.isfinite(na) and math.isfinite(nb)):
        return 0.0
    if na <= 1e-12 or nb <= 1e-12:
        return 0.0
    return max(-1.0, min(1.0, dot / (math.sqrt(na) * math.sqrt(nb))))


@dataclass
class Verdict:
    is_owner: bool
    score: float = 0.0
    threshold: float = 0.0
    mode: str = "owner"
    reason: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def verify(audio, embedder=None) -> Verdict:
    """Is this the owner? Called by jarvis_speech before any transcription.

    ORDER MATTERS. jarvis_speech's own comment explains why this must answer
    before a transcript exists: "A voice that is not the owner's is never
    turned into words - refusing after transcribing would leave a stranger's
    speech in memory on the way to saying no."

    Every path that is not a clean pass returns is_owner=False with a reason.
    """
    mode = str(_cfg("mode", "owner") or "owner").strip().lower()

    if not bool(_cfg("enabled", True)):
        return Verdict(False, mode=mode, reason="voice is switched off in the config")

    if mode == "broad":
        # The owner's explicit choice, reported every time so it is never a
        # silent state. No embedding is computed: there is nothing to check.
        return Verdict(True, score=1.0, threshold=0.0, mode="broad",
                       reason="mode is broad: any voice is accepted")

    prof = load_profile()
    if prof is None:
        return Verdict(False, mode=mode,
                       reason="no enrolled voice profile - run enrolment first")

    emb = embedder or Embedder()
    if prof.embedder and emb.name != prof.embedder:
        # Vectors from two different models are not comparable, and comparing
        # them anyway produces a plausible number that means nothing. The same
        # trap jarvis_memory handles by rebuilding on an embedder change; here
        # there is nothing to rebuild without the owner's voice, so it refuses.
        return Verdict(False, threshold=prof.threshold, mode=mode,
                       reason=(f"profile was enrolled with {prof.embedder!r} but "
                               f"{emb.name!r} is loaded - re-enrol to use it"))

    try:
        vec = emb.embed(audio)
        # Anything not list-shaped: a scalar, a string, a generator. len() on
        # a float raised TypeError straight out of verify(), and
        # jarvis_speech.hear() does not wrap this call - so a bad embedder
        # crashed the request instead of refusing, contradicting "every path
        # that is not a clean pass returns is_owner=False".
        if isinstance(vec, (str, bytes)) or not hasattr(vec, "__len__"):
            vec = list(vec) if hasattr(vec, "__iter__") and not isinstance(vec, (str, bytes)) else []
        vec = [float(x) for x in vec]
    except Exception as exc:
        return Verdict(False, threshold=prof.threshold, mode=mode,
                       reason=f"could not read the audio ({type(exc).__name__})")
    if not vec:
        return Verdict(False, threshold=prof.threshold, mode=mode,
                       reason="clip too short or silent to identify a voice")
    if len(vec) != len(prof.centroid):
        return Verdict(False, threshold=prof.threshold, mode=mode,
                       reason="profile and embedder disagree about vector size")

    score = cosine(vec, prof.centroid)
    if not math.isfinite(score):
        return Verdict(False, threshold=prof.threshold, mode=mode,
                       reason="comparison produced no usable score")

    ok = score >= prof.threshold
    return Verdict(ok, score=round(score, 4), threshold=prof.threshold, mode=mode,
                   reason=("recognised" if ok else
                           f"does not match the enrolled voice "
                           f"({score:.2f} < {prof.threshold:.2f})"))


def status() -> dict:
    """What the voice gate can actually do right now. Read by jarvis_speech
    and reported to clients as a capability, so it must not overstate."""
    prof = load_profile()
    try:
        EcapaEmbedder()
        model = "ecapa"
    except Exception:
        model = "spectral-v1"
    return {
        "enabled": bool(_cfg("enabled", True)),
        "mode": str(_cfg("mode", "owner") or "owner"),
        "enrolled": prof is not None,
        "samples": prof.samples if prof else 0,
        "threshold": prof.threshold if prof else _clamp_threshold(_cfg("threshold", 0.35)),
        "embedder": model,
        "speaker_model": model == "ecapa",
        "wake_phrase": _cfg("wake_phrase", "hey_jarvis"),
        "wake_word_enabled": bool(_cfg("wake_word_enabled", False)),
        "note": ("" if model == "ecapa" else
                 "no speaker model installed: the fallback is a coarse "
                 "spectral signature and will not reliably separate similar "
                 "voices"),
    }


if __name__ == "__main__":
    for k, v in status().items():
        print(f"  {k:<20} {v}")
