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

WHAT IS NOT HERE: the speaker model itself. `EcapaEmbedder` needs either a
sherpa-onnx speaker-embedding model file (preferred: one ~30 MB file, no
PyTorch) or speechbrain, and neither is installed by this file. jarvis_speech
already expects that - it wraps the constructor in try/except and falls back -
so the fallback is the honest path rather than a stub pretending to be a
neural speaker embedder. The fallback is spectral and it says
`semantic = False`.

Where the model file is looked for (added 2026-09-23 with "Train my voice"):
`[voice] speaker_model` if set, otherwise
`<config dir>/voice-models/speaker/model.onnx` - the same `voice-models`
folder jarvis_speech reads its speech-to-text and Kokoro files from. The
model this was tested with is 3D-Speaker's CAM++ English VoxCeleb export
from the sherpa-onnx releases
(`3dspeaker_speech_campplus_sv_en_voxceleb_16k.onnx`); backend/README.md has
the one-line install. The class keeps its old name because jarvis_speech
constructs it by that name.

ONE VOICE PRINT PER MICROPHONE (added 2026-09-24). A phone held at arm's
length and a desk microphone across the room make the same voice sound
different, and a print trained on one scores the other lower. So each
microphone can have its own: `owner-phone.json` and `owner-desktop.json`
beside the old `owner.json`. The clients say which microphone a clip came
from (`mic=phone` / `mic=desktop` on /api/voice/utterance, voice-mic.patch;
`"mic"` in the training body). A clip is checked against its own
microphone's print and, when that one has not been trained, falls back:

    phone:    owner-phone.json -> owner.json -> owner-desktop.json
    desktop:  owner-desktop.json -> owner-phone.json -> owner.json
    unnamed:  owner.json -> owner-phone.json -> owner-desktop.json

`owner.json` is every print made before this change - all of them from the
phone - so it keeps working untouched, for both, until the phone is
trained again; that training replaces it (the card says so), which is why
it moves to `owner-phone.json` then rather than being kept beside it.
Nothing is migrated in place: an old print is only ever read.

Each print also keeps its own training clips' scores against it
(`self_scores`, numbers only) so the "someone else" check can suggest a
threshold from them later (suggest_threshold) - never applied without a
card.

THE STRICTER OWNER-ONLY CHECK (added 2026-09-24). Two holes, and what
closes each:

  1. With no speaker model installed, the spectral fallback could still
     answer is_owner=True. It cannot tell two people apart (backend/
     README.md measured every synthetic voice above 0.9 against every
     other), so in owner mode it now refuses every clip with a plain
     reason: "install the voice-ID model". `broad` mode is unchanged.
  2. enroll() lowered the bar to (loosest own clip - 0.05), floor 0.05,
     whenever one training clip was noisy - one bad clip could make the
     check accept almost anyone, silently. Now no bar is ever below the
     model's own floor (MODEL_BARS), and a clip that does not sound like
     the others is left out of the print and REPORTED (`outliers`), so
     the app can ask for it to be recorded again.

On top of that, the owner's decisions of 2026-09-24:

  * Two strictness settings, `very_strict` (the default) and `balanced`,
    in voice-settings.json beside the prints (settings()). Very strict
    needs BOTH the small model (model.onnx) AND a stronger one
    (strong.onnx, `[voice] speaker_model_strong`) to pass, and a longer
    sentence. Balanced asks the stronger one alone, at a lower bar, when
    it is installed - measured, the small model alone lets far too many
    other people in (MODEL_BARS says how much). Without the strong model
    both use the small one and status() says so. Loosening either
    setting needs an approval card (jarvis_voice_enroll.py); tightening
    is immediate. plan() says which model is asked, when.
  * Private answers: `private_on_screen` (the default) or
    `voice_is_enough`, which may only be chosen while very strict.
    may_speak() answers "may this be read aloud?".
  * Comparison voices (a "cohort"): a clip must be clearly closer to the
    owner than to a bank of other speakers' voice prints (numbers only,
    never audio) - adaptive score normalisation, as_norm().
  * Several sub-prints per microphone, one per recording condition
    ("close", "far", "room"): a clip is compared with the nearest.
    Training more ADDS to a print instead of replacing it.
  * The owner's repeat rate: in-memory counts of refusals, and of a
    refusal followed by an acceptance within REPEAT_WINDOW seconds
    (repeat_counts()). Numbers only; nothing is written.

No clip is ever written to disk by anything in this file: a print, a
bank and the settings are numbers.
"""
from __future__ import annotations

import array
import base64
import hashlib
import json
import math
import os
import threading
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

#: The microphones that may have a print of their own. Anything else is
#: "no microphone named", which reads the prints in the old order.
MICS = ("phone", "desktop")


def clean_mic(mic) -> str:
    m = str(mic or "").strip().lower()
    return m if m in MICS else ""


def profile_path(mic: str = "") -> Path:
    """Where `mic`'s own print lives; the old owner.json for no mic."""
    m = clean_mic(mic)
    base = Path(PROFILE_PATH)
    return base.with_name(f"owner-{m}.json") if m else base


def lookup_order(mic: str = "") -> list:
    """[(label, path)] in the order a clip from `mic` is checked against -
    see the module docstring. The label is what verdicts and status call
    the print: "phone", "desktop", or "general" (the old owner.json)."""
    general = ("general", Path(PROFILE_PATH))
    phone = ("phone", profile_path("phone"))
    desk = ("desktop", profile_path("desktop"))
    m = clean_mic(mic)
    if m == "desktop":
        return [desk, phone, general]
    if m == "phone":
        return [phone, general, desk]
    return [general, phone, desk]


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


def speaker_model_path() -> Path:
    """Where the sherpa-onnx speaker model is looked for. Whether it is THERE
    is a separate question - see `EcapaEmbedder`. `[voice] speaker_model`
    wins; otherwise the file sits beside jarvis_speech's other models."""
    configured = str(_cfg("speaker_model", "") or "").strip()
    if configured:
        return Path(os.path.expanduser(configured))
    return _profile_dir().parent / "voice-models" / "speaker" / "model.onnx"


def strong_model_path() -> Path:
    """Where the STRONGER speaker model is looked for (very strict needs it
    as well as the small one). `[voice] speaker_model_strong` wins;
    otherwise strong.onnx beside model.onnx."""
    configured = str(_cfg("speaker_model_strong", "") or "").strip()
    if configured:
        return Path(os.path.expanduser(configured))
    return speaker_model_path().with_name("strong.onnx")


#: Loaded models, reused. jarvis_speech builds an EcapaEmbedder for every
#: utterance and status() builds one for every status read, so loading a
#: 30 MB model each time would put a second of disk and CPU in front of
#: every answer. Keyed on the file's size and modification time, so dropping
#: a different model in place is noticed without a restart. Up to three
#: (the small model and the strong one, plus one being swapped in): this
#: held ONE until 2026-09-24, and with two models in use each would have
#: pushed the other out on every clip.
_SHERPA: dict = {}
_SHERPA_LOCK = threading.Lock()
_SHERPA_MAX = 3

#: Why the model file, if present, could not be used - shown by status() so
#: "I put the file there and nothing changed" has an answer on screen.
_speaker_model_error = ""
_strong_model_error = ""


def _sherpa_extractor(path: Path):
    """(extractor, name) for the model file at `path`. Raises if sherpa_onnx
    is missing or the file will not load. For a missing or corrupt file the
    real package raises RuntimeError - checked, it does not abort the
    process."""
    import sherpa_onnx  # noqa: raises ImportError when not installed
    st = path.stat()
    key = (str(path), st.st_size, st.st_mtime_ns)
    with _SHERPA_LOCK:
        hit = _SHERPA.get(key)
        if hit is not None:
            return hit
        cfg = sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(path),
                                                         num_threads=1)
        ext = sherpa_onnx.SpeakerEmbeddingExtractor(cfg)
        # The NAME goes into every saved profile, and verify() refuses a
        # profile made by a different embedder. So it must change when the
        # model changes: two different models both called "sherpa-onnx"
        # would compare vectors that mean different things. A short hash of
        # the file does that; the file name does not (it is model.onnx by
        # default whatever is inside).
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        hit = (ext, "sherpa-onnx:" + h.hexdigest()[:12])
        for old in [k for k in _SHERPA if k[0] == key[0]]:
            del _SHERPA[old]            # the same path, an older file
        while len(_SHERPA) >= _SHERPA_MAX:
            del _SHERPA[next(iter(_SHERPA))]
        _SHERPA[key] = hit
        return hit


class EcapaEmbedder(Embedder):
    """The real speaker model: a sherpa-onnx model file if there is one,
    otherwise speechbrain's ECAPA if that is installed.

    RAISES from __init__ when neither is available, and that is required
    rather than sloppy: jarvis_speech does

        try:    embedder = jarvis_voice.EcapaEmbedder()
        except: embedder = jarvis_voice.Embedder()

    so a constructor that quietly returned a working-looking object with
    spectral behaviour would make the fallback unreachable and mislabel every
    verdict as a speaker model.
    """

    name = "ecapa"
    dim = 192
    semantic = True
    #: embed() accepts the clip's sample rate. The sherpa model resamples to
    #: what it was trained on when told the real rate; told nothing, it would
    #: read a 48 kHz desktop clip as 16 kHz and embed nonsense. The spectral
    #: fallback and the tests' stubs take one argument, so verify() and
    #: enroll() only pass the rate to an embedder that says it takes one.
    takes_rate = True

    def __init__(self, source: str = "speechbrain/spkrec-ecapa-voxceleb") -> None:
        global _speaker_model_error
        self._kind = ""
        path = speaker_model_path()
        if path.is_file():
            try:
                self._ext, self.name = _sherpa_extractor(path)
                self.dim = int(self._ext.dim)
                self._kind = "sherpa-onnx"
                _speaker_model_error = ""
                return
            except ImportError:
                _speaker_model_error = ("the speaker model file is there but "
                                        "the sherpa-onnx package is not "
                                        "installed: pip install sherpa-onnx")
            except Exception as exc:
                _speaker_model_error = (f"the speaker model file at {path} "
                                        f"would not load ({type(exc).__name__})")
        from speechbrain.inference.speaker import EncoderClassifier  # noqa
        import torch  # noqa
        self._torch = torch
        self._m = EncoderClassifier.from_hparams(source=source)
        self._kind = "speechbrain"

    def embed(self, audio, sample_rate: Optional[int] = None) -> list:
        x = _pcm(audio)
        if len(x) < 512:
            return []
        if self._kind == "sherpa-onnx":
            import numpy as np  # sherpa_onnx requires it, so it is there
            stream = self._ext.create_stream()
            stream.accept_waveform(int(sample_rate or 16000),
                                   np.asarray(x, dtype=np.float32))
            stream.input_finished()
            if not self._ext.is_ready(stream):
                return []
            return _norm([float(i) for i in self._ext.compute(stream)])
        t = self._torch.tensor([x], dtype=self._torch.float32)
        with self._torch.no_grad():
            v = self._m.encode_batch(t).squeeze().tolist()
        return _norm([float(i) for i in (v if isinstance(v, list) else [v])])


class StrongEmbedder(EcapaEmbedder):
    """The STRONGER speaker model, for "very strict": strong.onnx (see
    strong_model_path). A sherpa-onnx file only - no speechbrain fallback,
    because "the strong model" must mean one known file. Raises when it is
    not installed; strong_embedder() turns that into None."""

    def __init__(self) -> None:          # noqa: D401 - no super(): no fallback
        global _strong_model_error
        self._kind = ""
        path = strong_model_path()
        if not path.is_file():
            _strong_model_error = ""
            raise FileNotFoundError(f"no stronger voice-ID model at {path}")
        try:
            self._ext, self.name = _sherpa_extractor(path)
        except ImportError:
            _strong_model_error = ("the stronger model file is there but the "
                                   "sherpa-onnx package is not installed")
            raise
        except Exception as exc:
            _strong_model_error = (f"the stronger model file at {path} would "
                                   f"not load ({type(exc).__name__})")
            raise
        self.dim = int(self._ext.dim)
        self._kind = "sherpa-onnx"
        _strong_model_error = ""


def strong_embedder(primary=None):
    """The stronger model, or None when it is not installed (or is the same
    file as the small one - two copies of one model are one opinion, not
    two)."""
    try:
        s = StrongEmbedder()
    except Exception:
        return None
    if primary is not None and getattr(primary, "name", None) == s.name:
        return None
    return s


def _embed(emb, audio, sample_rate: Optional[int]):
    """One clip through `emb`, with the sample rate only for an embedder that
    says it takes one (see EcapaEmbedder.takes_rate)."""
    if sample_rate and getattr(emb, "takes_rate", False):
        return emb.embed(audio, sample_rate=sample_rate)
    return emb.embed(audio)


def _as_vector(vec) -> list:
    """Whatever an embedder returned, as a list of floats, or [] - never
    raises. A scalar, a string or a generator must refuse, not crash:
    jarvis_speech.hear() does not wrap verify()."""
    try:
        if isinstance(vec, (str, bytes)) or not hasattr(vec, "__len__"):
            vec = list(vec) if hasattr(vec, "__iter__") and not isinstance(vec, (str, bytes)) else []
        return [float(x) for x in vec]
    except Exception:
        return []


# --------------------------------------------------------------------------
#   How strict: the two settings, and the bars each model is held to
# --------------------------------------------------------------------------

VERY_STRICT = "very_strict"
BALANCED = "balanced"
STRICTNESS = (VERY_STRICT, BALANCED)
PRIVATE_ON_SCREEN = "private_on_screen"
VOICE_IS_ENOUGH = "voice_is_enough"
PRIVACY = (PRIVATE_ON_SCREEN, VOICE_IS_ENOUGH)
#: Answers that use what Jarvis REMEMBERS about the owner (the recalled-facts
#: block, `injected_facts` on the chat route), asked by voice. The owner's
#: choice, 2026-09-24: "looser now, with a setting to make it more strict" -
#: so these are read aloud by default, and `memory_on_screen` keeps them on
#: the screen like email, the calendar and notes. A QUESTION about a private
#: topic (health, money, email...) still stays on screen either way.
MEMORY_ALOUD = "memory_aloud"
MEMORY_ON_SCREEN = "memory_on_screen"
MEMORY = (MEMORY_ALOUD, MEMORY_ON_SCREEN)
#: Answers that use a SENSITIVE saved fact - health, money, passwords and
#: account details, other people (jarvis_auto_learn.sensitivity(); the chat
#: route's `injected_sensitive`) - asked by voice. The owner's decision,
#: 2026-09-24: kept on screen by default, EVEN when memory answers or
#: private answers are read aloud; `sensitive_aloud` lets them be read aloud
#: after a real voice check, and choosing it raises the voice approval card.
SENSITIVE_ON_SCREEN = "sensitive_on_screen"
SENSITIVE_ALOUD = "sensitive_aloud"
SENSITIVE_MEMORY = (SENSITIVE_ON_SCREEN, SENSITIVE_ALOUD)
#: How far a question started HANDS-FREE ("hey Jarvis", `source=wake_word`)
#: is trusted. The owner's decision, 2026-09-24: "as trusted as the talk
#: button by default, with a setting to make it stricter". The voice check
#: tells the owner's voice from other people's; it cannot tell it from a
#: recording or a copy played near the microphone, and the hands-free path
#: is the one such a recording can reach without anyone touching a device.
#: `button_only`: a turn that did not come from the talk button
#: (`source=push_to_talk`) - including one whose source is missing or
#: unknown - reads nothing private, remembered or sensitive aloud, and
#: automatic learning never saves a fact from it without a card.
SAME_AS_BUTTON = "same_as_button"
BUTTON_ONLY = "button_only"
HANDS_FREE = (SAME_AS_BUTTON, BUTTON_ONLY)
#: The one source the talk button sends (jarvis_speech.hear's `source`).
PUSH_TO_TALK = "push_to_talk"
#: The default of each setting. For strictness, privacy and sensitive_memory
#: it is the strict value, also used for a missing, unreadable or unknown
#: one. For memory and hands_free the default is the owner's looser choice;
#: an unknown VALUE (a damaged file) still falls back to the strict one -
#: see settings().
DEFAULTS = {"strictness": VERY_STRICT, "privacy": PRIVATE_ON_SCREEN,
            "memory": MEMORY_ALOUD, "sensitive_memory": SENSITIVE_ON_SCREEN,
            "hands_free": SAME_AS_BUTTON}
_CHOICES = {"strictness": STRICTNESS, "privacy": PRIVACY, "memory": MEMORY,
            "sensitive_memory": SENSITIVE_MEMORY, "hands_free": HANDS_FREE}
#: The LOOSER value of each: choosing it needs an approval card.
LOOSER = {"strictness": BALANCED, "privacy": VOICE_IS_ENOUGH, "memory": MEMORY_ALOUD,
          "sensitive_memory": SENSITIVE_ALOUD, "hands_free": SAME_AS_BUTTON}
#: The settings whose DEFAULT is the looser value, and the strict value each
#: falls back to when the file is unreadable or holds a value that is not
#: one of its choices. Only a file that never had the key gets the default.
_STRICT_WHEN_DAMAGED = {"memory": MEMORY_ON_SCREEN, "hands_free": BUTTON_ONLY}
_SETTINGS_LOCK = threading.Lock()

#: The least speech a COMMAND must have, in seconds (the VAD's span, which
#: keeps 0.3 s of quiet either side). A speaker model has little to go on in
#: a second of speech - measured in backend/README.md, "The stricter voice
#: check" - so a shorter clip is refused before the voice check and the
#: owner is asked to say a little more. A clip that is only "hey Jarvis" is
#: the wake path, not a command: jarvis_speech.hear() lets it open the
#: listening window, and nothing more.
MIN_COMMAND_SECONDS = {VERY_STRICT: 2.0, BALANCED: 1.5}


def settings_path() -> Path:
    """voice-settings.json beside the voice prints."""
    return Path(PROFILE_PATH).with_name("voice-settings.json")


def settings() -> dict:
    """{"strictness", "privacy", "memory", "sensitive_memory", "hands_free",
    "changed"}. The strict value for anything missing, unreadable or
    unknown - except that a file with no "memory" or no "hands_free" in it
    (every file written before 2026-09-24, and no file at all) gets the
    owner's default for it: MEMORY_ALOUD, SAME_AS_BUTTON. The one rule
    applied on every read as well as every write: private answers may be
    read aloud only while the check is very strict."""
    out = {**DEFAULTS, "changed": 0.0}
    p = settings_path()
    try:
        raw = json.loads(p.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        raw = {}
    except Exception:
        raw = None                      # there, but unreadable: strict
    if not isinstance(raw, dict):
        out.update(_STRICT_WHEN_DAMAGED)
        raw = {}
    for key, choices in _CHOICES.items():
        if raw.get(key) in choices:
            out[key] = raw[key]
        elif key in _STRICT_WHEN_DAMAGED and key in raw:
            # Present but not a known value: the strict one, as for the
            # others. Only a file that never had it gets the default.
            out[key] = _STRICT_WHEN_DAMAGED[key]
    ch = raw.get("changed")
    if isinstance(ch, (int, float)) and not isinstance(ch, bool) and math.isfinite(ch):
        out["changed"] = float(ch)
    if out["strictness"] != VERY_STRICT:
        out["privacy"] = PRIVATE_ON_SCREEN
    return out


def is_loosening(key: str, value: str) -> bool:
    """Whether setting `key` to `value` would loosen what is set now."""
    return key in LOOSER and value == LOOSER[key] and settings().get(key) != value


def set_setting(key: str, value: str, *, approved: bool = False) -> dict:
    """Changes one setting and returns settings(). Raises ValueError, in
    words, when it may not.

    Tightening is immediate. Loosening only with `approved=True`, which
    only jarvis_voice_enroll passes, after an approval card said yes - and
    even then `voice_is_enough` is refused unless the check is very strict
    at that moment (it may have been loosened while the card waited).
    Choosing `balanced` also puts private answers back on screen."""
    if key not in _CHOICES:
        raise ValueError(f"there is no voice setting called {str(key)[:30]!r}")
    if value not in _CHOICES[key]:
        raise ValueError(f"{key} must be one of: " + ", ".join(_CHOICES[key]))
    with _SETTINGS_LOCK:
        cur = settings()
        if value == LOOSER[key] and cur[key] != value and not approved:
            raise ValueError("making the voice check looser needs an approval card")
        if key == "privacy" and value == VOICE_IS_ENOUGH and cur["strictness"] != VERY_STRICT:
            raise ValueError("private answers can only be read aloud while the voice "
                             "check is very strict")
        new = {"strictness": cur["strictness"], "privacy": cur["privacy"],
               "memory": cur["memory"], "sensitive_memory": cur["sensitive_memory"],
               "hands_free": cur["hands_free"], key: value}
        if new["strictness"] != VERY_STRICT:
            new["privacy"] = PRIVATE_ON_SCREEN
        new["changed"] = time.time()
        p = settings_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(new), encoding="utf-8")
        tmp.replace(p)
    return settings()


def min_command_seconds(strictness: Optional[str] = None) -> float:
    s = strictness if strictness in STRICTNESS else settings()["strictness"]
    return MIN_COMMAND_SECONDS[s]


#: The bars each speaker model is held to, by the short hash of its file
#: (the end of the embedder's name): (raw similarity bar, bar on the score
#: after comparison with other voices - as_norm - or None for "not asked").
#:
#:   balanced / very_strict   the model deciding ALONE at that setting
#:   paired                   the model as one of the two very strict asks
#:
#: A print's own threshold (the "someone else" check's card) can make a raw
#: bar HIGHER, never lower. Where every number came from, and what it
#: costs: backend/README.md, "The stricter voice check" - measured on real
#: voices (Speech Commands, CC BY 4.0), short word-by-word clips with
#: made-up "far" and "room" conditions, NOT on the owner or on sentences.
#:
#: Why the small model is asked so gently when paired, and is not asked at
#: all in balanced when the stronger one is installed: measured here, it
#: tells people apart poorly (at 0.35 it let in more than half of the other
#: speakers' clips; the stronger model at 0.40, 3%). Its comparison with other voices
#: cost the owner more than it caught, so when paired it is not asked to do
#: that - the stronger model does it.
MODEL_BARS = {
    # 3D-Speaker CAM++, English VoxCeleb (model.onnx) - "the small model"
    "357a834f702b": {"label": "the small voice-ID model",
                     "balanced": (0.35, 0.0), "very_strict": (0.40, 1.0),
                     "paired": (0.30, None)},
    # NeMo TitaNet-Large, English (strong.onnx) - "the stronger model"
    "d51abcf31717": {"label": "the stronger voice-ID model",
                     "balanced": (0.40, 2.0), "very_strict": (0.50, 3.0),
                     "paired": (0.50, 3.0)},
}
#: Any other model. Its raw numbers mean nothing known (one model measured
#: here put EVERY voice above 0.9), so only the comparison with other voices
#: - which does not depend on a model's scale - can say much, and there is
#: no bank for an unknown model unless one is built on this PC. status()
#: says so.
GENERIC_BARS = {"label": "a voice-ID model whose bars were not measured here",
                "balanced": (0.35, 2.0), "very_strict": (0.45, 3.0),
                "paired": (0.45, 2.0)}


def _short(name: str) -> str:
    return str(name or "").rsplit(":", 1)[-1][:12].lower()


def bars_for(name: str) -> dict:
    """The bars for the embedder called `name`, and whether they were
    measured for it (`known`)."""
    got = MODEL_BARS.get(_short(name))
    return {**(got or GENERIC_BARS), "known": got is not None}


def bar_for(name: str, role: str) -> tuple:
    """(raw bar, comparison bar or None) for `name` in `role` - "balanced",
    "very_strict" (deciding alone) or "paired"."""
    b = bars_for(name)
    raw, norm = b.get(role, b[VERY_STRICT])
    return float(raw), (None if norm is None else float(norm))


def floor_for(name: str, strictness: str) -> float:
    """The lowest raw bar `name` may ever be held to when it decides alone
    at `strictness` - so no enrolment and no card can go below it."""
    return bar_for(name, strictness if strictness in STRICTNESS else VERY_STRICT)[0]


# --------------------------------------------------------------------------
#   Other voices: the comparison bank ("cohort")
# --------------------------------------------------------------------------
#
# A clip passes only if it is CLEARLY closer to the owner than to other
# people. "Other people" is a bank of voice prints - one averaged vector per
# speaker, numbers only, never audio - for the same model file. The score
# is then normalised against how well the clip, and the owner's print,
# match their nearest others (adaptive symmetric normalisation, "AS-norm"):
#
#     z = ((s - mean_top_k(clip vs bank)) / sd  +  (s - mean_top_k(print vs bank)) / sd) / 2
#
# It is an EXTRA bar, never a replacement for the raw one: a bank that does
# not match real voices well can make the check refuse more often, never
# accept someone the raw bar would have refused.
#
# Where a bank comes from, first found wins:
#   1. <voice folder>/cohort/<model hash>.json - built on this PC from real
#      recordings (LibriSpeech, say): `py -3 jarvis_voice.py --build-cohort
#      <folder>`. It keeps the shipped voices too, and adds these.
#   2. jarvis_voicebank.py, shipped - 300 real speakers of Google's Speech
#      Commands (CC BY 4.0), generated by tools/gen_voicebank.py. Short
#      words, joined; better than nothing, and far from a perfect match
#      for a whole sentence said in a room.
#
# What it was measured to do (backend/README.md, "The stricter voice
# check"): with the stronger model, next to nothing - that model's own
# bar already refuses what the comparison would. With the small model
# alone, it halved the other speakers let in (59% to 27%), and refused the
# owner more often (8% to 24%).

COHORT_K = 50
_BANKS: dict = {}
_BANKS_LOCK = threading.Lock()


def cohort_path(name: str) -> Path:
    return Path(PROFILE_PATH).parent / "cohort" / f"{_short(name)}.json"


def encode_bank(name: str, vectors: list, source: str) -> dict:
    """A bank as a small JSON document: 8 bits per number, one scale per
    dimension. `vectors` are unit vectors, one per speaker."""
    dim = len(vectors[0])
    scale = [max(abs(v[i]) for v in vectors) / 127.0 or 1e-9 for i in range(dim)]
    q = array.array("b", [max(-127, min(127, int(round(v[i] / scale[i]))))
                          for v in vectors for i in range(dim)])
    return {"model": name, "dim": dim, "speakers": len(vectors), "source": source,
            "scale": [round(s, 9) for s in scale],
            "vectors": base64.b64encode(q.tobytes()).decode("ascii")}


def decode_bank(doc) -> list:
    """The vectors in a bank document, or [] for anything malformed."""
    try:
        dim, n = int(doc["dim"]), int(doc["speakers"])
        scale = [float(s) for s in doc["scale"]]
        raw = doc["vectors"]
        if isinstance(raw, (list, tuple)):
            raw = "".join(raw)           # the shipped bank keeps it in short lines
        q = array.array("b")
        q.frombytes(base64.b64decode(raw))
        if dim < 2 or n < 1 or len(scale) != dim or len(q) != dim * n:
            return []
        out = []
        for k in range(n):
            v = _norm([q[k * dim + i] * scale[i] for i in range(dim)])
            if v:
                out.append(v)
        return out
    except Exception:
        return []


def cohort_for(name: str):
    """(vectors, info) for the model called `name`, or (None, why)."""
    if not name or not str(name).startswith("sherpa-onnx:"):
        return None, "no comparison voices for this voice check"
    p = cohort_path(name)
    try:
        st = p.stat()
        key = (str(p), st.st_size, st.st_mtime_ns)
    except OSError:
        key = None
    with _BANKS_LOCK:
        if key is not None:
            hit = _BANKS.get(key)
            if hit is None:
                try:
                    doc = json.loads(p.read_text(encoding="utf-8"))
                except Exception:
                    doc = {}
                vecs = decode_bank(doc) if doc.get("model") == name else []
                hit = (vecs, {"speakers": len(vecs), "source": str(doc.get("source", ""))[:200],
                              "where": "built on this PC"})
                _BANKS[key] = hit
            if hit[0]:
                return hit
    try:
        import jarvis_voicebank
        doc = jarvis_voicebank.BANKS.get(name)
    except Exception:
        doc = None
    if not doc:
        return None, "no comparison voices for this model yet"
    with _BANKS_LOCK:
        hit = _BANKS.get(("shipped", name))
        if hit is None:
            vecs = decode_bank(doc)
            hit = (vecs, {"speakers": len(vecs), "source": str(doc.get("source", ""))[:200],
                          "where": "shipped with Jarvis"})
            _BANKS[("shipped", name)] = hit
    return hit if hit[0] else (None, "the comparison voices could not be read")


def _topk_stats(v: list, bank: list, k: int) -> tuple:
    """(mean, sd) of `v`'s k best similarities in `bank` (unit vectors)."""
    try:
        import numpy as np
        m = np.asarray(bank, dtype=np.float32) @ np.asarray(v, dtype=np.float32)
        top = np.sort(m)[::-1][:k]
        return float(top.mean()), float(top.std())
    except ImportError:
        sims = sorted((sum(a * b for a, b in zip(v, u)) for u in bank), reverse=True)[:k]
        mean = sum(sims) / len(sims)
        return mean, math.sqrt(sum((s - mean) ** 2 for s in sims) / len(sims))


def as_norm(score: float, clip: list, owner: list, bank: list, k: int = COHORT_K) -> float:
    """The score, normalised against other voices (see above). Large means
    "clearly closer to the owner than to anyone in the bank"."""
    k = max(1, min(k, len(bank) // 2 or 1))
    mt, st = _topk_stats(clip, bank, k)
    me, se = _topk_stats(owner, bank, k)
    return 0.5 * ((score - mt) / max(st, 1e-3) + (score - me) / max(se, 1e-3))


# --------------------------------------------------------------------------
#   The enrolled profile
# --------------------------------------------------------------------------

#: The recording conditions a sub-print can be for. "general" is a print
#: made before sub-prints existed, or with no condition named.
CONDITIONS = ("close", "far", "room", "general")


def clean_condition(c) -> str:
    c = str(c or "").strip().lower()
    return c if c in CONDITIONS else "general"


@dataclass
class VoiceProfile:
    name: str = "owner"
    embedder: str = ""
    centroid: list = field(default_factory=list)
    threshold: float = 0.35
    samples: int = 0
    created: float = 0.0
    #: "phone", "desktop" or "" - the microphone it was trained on.
    mic: str = ""
    #: Each training clip's score against this print (numbers, no audio):
    #: what "you" look like, for the "someone else" check.
    self_scores: list = field(default_factory=list)
    #: Since 2026-09-24: {embedder name: [sub-print, ...]}, one sub-print
    #: per recording condition - {"condition", "centroid", "samples",
    #: "self_scores"}. The fields above stay the SMALL model's whole print,
    #: so a jarvis_voice.py from before this still reads the file.
    models: dict = field(default_factory=dict)
    #: The owner's own raw bar for each OTHER model (the stronger one),
    #: set only by the "someone else" check's card. `threshold` above is
    #: the small model's.
    thresholds: dict = field(default_factory=dict)
    updated: float = 0.0
    version: int = 2
    #: Training clips left out because they did not sound like the rest
    #: (0-based, in the order they were given). Not saved.
    outliers: list = field(default_factory=list)

    def as_dict(self) -> dict:
        d = asdict(self)
        d.pop("outliers", None)
        return d

    @property
    def usable(self) -> bool:
        return bool(self.centroid) and self.samples > 0

    def subprints(self, name: str) -> list:
        """The sub-prints for embedder `name`: its own, or - for the model
        the old single print was made with - that print as one "general"
        sub-print."""
        got = self.models.get(name) if isinstance(self.models, dict) else None
        if got:
            return got
        if name and (name == self.embedder or not self.embedder) and self.centroid:
            return [{"condition": "general", "centroid": self.centroid,
                     "samples": self.samples, "self_scores": self.self_scores}]
        return []

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


def _finite_list(x) -> bool:
    return isinstance(x, (list, tuple)) and bool(x) and not any(
        isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
        for v in x)


def _clean_models(raw) -> dict:
    """The `models` section, keeping only well-formed sub-prints. A bad one
    is dropped, never guessed at - comparing against it would mean nothing."""
    out = {}
    if not isinstance(raw, dict):
        return out
    for name, subs in list(raw.items())[:4]:
        if not isinstance(name, str) or not isinstance(subs, list):
            continue
        keep, dim = [], None
        for sp in subs[:8]:
            if not isinstance(sp, dict) or not _finite_list(sp.get("centroid")):
                continue
            c = [float(x) for x in sp["centroid"]]
            if dim is None:
                dim = len(c)
            if len(c) != dim or not _norm(c):
                continue
            n = sp.get("samples", 0)
            if isinstance(n, bool) or not isinstance(n, int) or n < 1:
                continue
            ss = sp.get("self_scores", [])
            ss = [float(x) for x in ss][:64] if _finite_list(ss) else []
            keep.append({"condition": clean_condition(sp.get("condition")),
                         "centroid": c, "samples": n, "self_scores": ss})
        if keep:
            out[name] = keep
    return out


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
    if any(isinstance(x, bool) or not isinstance(x, (int, float))
           or not math.isfinite(x) for x in cent):
        # NaN/Infinity are floats, so the check above alone let them through.
        # json.loads accepts the bare tokens NaN/Infinity/-Infinity as a
        # Python-specific extension, so a truncated or corrupted write of the
        # profile file could pass every earlier check and build a
        # VoiceProfile that reports itself enrolled and usable. It still
        # fails SAFE at verify() time - cosine()'s isfinite guard scores it
        # 0.0 - so this was never a false accept. It was a silent, permanent
        # lockout: status() said "enrolled": True, load_profile()'s own
        # docstring promises None on "anything wrong", and the owner had no
        # way to learn "your profile is corrupt, re-enrol" from either.
        return None
    scores = raw.get("self_scores", [])
    if not isinstance(scores, list) or any(
            isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x)
            for x in scores):
        # Only ever advisory (the "someone else" check), so a bad list is
        # dropped rather than the whole print refused.
        scores = []
    try:
        prof = VoiceProfile(
            name=str(raw.get("name", "owner")),
            embedder=str(raw.get("embedder", "")),
            centroid=[float(x) for x in raw["centroid"]],
            threshold=_clamp_threshold(
                raw.get("threshold", _cfg("threshold", 0.35) or 0.35)),
            samples=int(raw.get("samples", 0)),
            created=float(raw.get("created", 0.0)),
            mic=clean_mic(raw.get("mic", "")),
            self_scores=[float(x) for x in scores][:64],
            models=_clean_models(raw.get("models")),
            thresholds={str(k): _clamp_threshold(v)
                        for k, v in (raw.get("thresholds") or {}).items()
                        if isinstance(v, (int, float)) and not isinstance(v, bool)}
            if isinstance(raw.get("thresholds"), dict) else {},
            updated=float(raw.get("updated", 0.0) or 0.0))
    except (TypeError, ValueError):
        return None
    return prof if prof.usable else None


def find_profile(mic: str = ""):
    """(profile, label) - the first usable print in `mic`'s lookup order, or
    (None, ""). A print that exists but will not load is skipped, never
    guessed at; load_profile's None means "refuse", and the next one in the
    order is a different, real print."""
    for label, p in lookup_order(mic):
        prof = load_profile(p)
        if prof is not None:
            return prof, label
    return None, ""


class EnrolError(ValueError):
    """Enrolment could not make a print. The message is shown to the owner;
    `outliers` lists the clips (0-based) that did not sound like the rest."""

    def __init__(self, message: str, outliers: Optional[list] = None):
        super().__init__(message)
        self.outliers = list(outliers or [])


def _mean_unit(vecs: list) -> list:
    dim = len(vecs[0])
    return _norm([sum(v[i] for v in vecs) / len(vecs) for i in range(dim)])


def _loo_scores(vecs: list) -> list:
    """Each vector's similarity to the mean of the OTHERS (leave one out).
    Including a clip in the mean it is scored against flatters it - most of
    all in a small group, where it is a third of the mean."""
    if len(vecs) < 2:
        return [1.0] * len(vecs)
    dim = len(vecs[0])
    total = [sum(v[i] for v in vecs) for i in range(dim)]
    return [round(cosine(v, [total[i] - v[i] for i in range(dim)]), 4) for v in vecs]


def enroll(clips: list, embedder=None, path: Optional[Path] = None,
           sample_rate: Optional[int] = None, mic: str = "",
           conditions: Optional[list] = None, add: bool = False,
           strong=None) -> VoiceProfile:
    """Build a voice print from sample clips (and save it).

    `conditions` names each clip's recording condition ("close", "far",
    "room"); one sub-print is made per condition, per model - the small one
    (`embedder`) and, when given, the stronger one (`strong`).

    THE BAR IS NEVER LOWERED to fit the clips (2026-09-24). It used to drop
    to (loosest own clip - 0.05), floor 0.05, so one noisy clip could make
    the check accept almost anyone, silently. Now the print's bar is the
    configured one, raised to the model's own floor if it is lower, and a
    clip that does not sound like the others - its similarity to the rest
    below that bar - is LEFT OUT and reported in `outliers`, so the app can
    ask for it again. More than half of them like that is an EnrolError.

    `add`: keep the print already there and add these clips to it (merged
    into the sub-print for the same condition, or a new one) instead of
    replacing it.
    """
    emb = embedder or Embedder()
    n = len(clips)
    conds = [clean_condition(c) for c in (conditions or [])][:n]
    conds += ["general"] * (n - len(conds))
    models = [emb] + ([strong] if strong is not None
                      and getattr(strong, "name", None) != emb.name else [])

    m = clean_mic(mic)
    target = Path(path or profile_path(m))
    old = None
    if add:
        old = load_profile(target)
        if old is None and path is None and m == "phone":
            old = load_profile(PROFILE_PATH)        # the old single print was the phone's
        if old is not None and old.embedder and old.embedder != emb.name:
            raise EnrolError("your voice print was made with a different voice check, so "
                             "these recordings cannot be added to it - train your voice "
                             "again from the start instead")

    vecs = {}
    for mod in models:
        vs = [_as_vector(_embed(mod, c, sample_rate)) for c in clips]
        good = [v for v in vs if v]
        dim = len(good[0]) if good else 0
        # One width. Mixed widths either raised IndexError or - worse, when
        # the short clip came first - silently truncated everyone to the
        # shortest, producing a 2-value "voice print" with no warning.
        vecs[mod.name] = [v if (v and len(v) == dim and _norm(v)) else [] for v in vs]
    usable = [i for i in range(n) if vecs[emb.name][i]]
    if not usable:
        raise EnrolError("no usable audio in those clips")

    # Outliers: each clip against the others of the same condition (all of
    # them when a condition has fewer than three), judged by the best model
    # given - the stronger one when there is one (the small one's own
    # scores are too noisy to single a clip out: measured, it scored 8% of
    # the owner's own clips under its bar) - at that model's balanced bar.
    outliers = set()
    judge = models[-1]
    for mod in (judge,):
        if not getattr(mod, "semantic", False):
            # The basic check's numbers say nothing about who is speaking
            # (it even changes with a clip's length), so there is nothing to
            # judge a clip by - and a print made with it is never used to
            # let anyone in (verify() refuses the basic check outright).
            continue
        bar = floor_for(mod.name, BALANCED)
        if mod is emb:
            bar = max(bar, _clamp_threshold(_cfg("threshold", 0.35) or 0.35))
        idx = [i for i in usable if vecs[mod.name][i]]
        for cond in set(conds[i] for i in idx):
            group = [i for i in idx if conds[i] == cond]
            ref = group if len(group) >= 3 else idx
            if len(ref) < 2:
                continue
            for i in group:
                others = [vecs[mod.name][j] for j in ref if j != i]
                if cosine(vecs[mod.name][i], _mean_unit(others)) < bar:
                    outliers.add(i)
    keep = [i for i in usable if i not in outliers]
    if len(keep) * 2 < len(usable) or not keep:
        raise EnrolError(
            "most of those recordings did not sound like the same voice - record them "
            "again somewhere quieter, holding the microphone the same way",
            sorted(outliers))

    now = time.time()
    new_models = {k: [dict(sp) for sp in v] for k, v in (old.models.items() if old else [])}
    if old is not None and emb.name not in new_models:
        new_models[emb.name] = [dict(sp) for sp in old.subprints(emb.name)]
    for mod in models:
        subs = new_models.setdefault(mod.name, [])
        for cond in sorted(set(conds[i] for i in keep), key=CONDITIONS.index):
            group = [vecs[mod.name][i] for i in keep if conds[i] == cond and vecs[mod.name][i]]
            if not group:
                continue
            loo = _loo_scores(group)
            mean = _mean_unit(group)
            if not mean:
                continue
            same = next((sp for sp in subs if sp["condition"] == cond), None)
            if same is not None:
                w = int(same["samples"])
                dim = len(mean)
                if len(same["centroid"]) != dim:
                    raise EnrolError("those recordings do not match the voice print "
                                     "already there - train your voice again from the start")
                merged = _norm([same["centroid"][i] * w + mean[i] * len(group)
                                for i in range(dim)])
                same.update(centroid=merged, samples=w + len(group),
                            self_scores=(list(same.get("self_scores", [])) + loo)[-64:])
            else:
                subs.append({"condition": cond, "centroid": mean, "samples": len(group),
                             "self_scores": loo})
        del subs[:-len(CONDITIONS)]
    subs = new_models.get(emb.name) or []
    if not subs:
        raise EnrolError("those clips produced no usable voice print")
    # The fields every older reader uses: the small model's whole print.
    dim = len(subs[0]["centroid"])
    centroid = _norm([sum(sp["centroid"][i] * sp["samples"] for sp in subs)
                      for i in range(dim)])
    if not centroid:
        # All-zero or non-finite clips. Saving this reports enrolment as a
        # success and then locks the owner out for ever, because load_profile
        # correctly refuses it on every subsequent call.
        raise EnrolError("those clips produced no usable voice print")
    configured = _clamp_threshold(_cfg("threshold", 0.35) or 0.35)
    threshold = old.threshold if old is not None else configured
    threshold = max(threshold, floor_for(emb.name, BALANCED))
    prof = VoiceProfile(embedder=emb.name, centroid=centroid,
                        threshold=round(threshold, 4),
                        samples=sum(int(sp["samples"]) for sp in subs),
                        created=old.created if old is not None else now, mic=m,
                        self_scores=[s for sp in subs for s in sp.get("self_scores", [])][-64:],
                        models=new_models, updated=now, outliers=sorted(outliers),
                        thresholds=dict(old.thresholds) if old is not None else {})
    prof.save(target)
    if path is None and m == "phone" and Path(PROFILE_PATH).is_file():
        # Every print before per-microphone prints came from the phone, so
        # a new phone print is what replaces it - the card said "any voice
        # trained before is replaced". Left behind, it would keep deciding
        # for clips that name no microphone. (Adding to it, it was read
        # above and is part of the new print.)
        try:
            Path(PROFILE_PATH).unlink()
        except OSError:
            pass
    return prof


def score_clips(clips: list, embedder=None, sample_rate: Optional[int] = None,
                mic: str = "", strong=None) -> dict:
    """How each clip scores against `mic`'s print - for the "someone else"
    check. Numbers only; changes nothing, stores nothing.

    `scores` are the DECIDING model's raw similarity to the nearest
    sub-print (plan(): the stronger model when it is installed and in the
    print, else the small one) - what the threshold card's bar is set for,
    named in `model` ("small" or "strong"). `passed` says whether each clip
    would have been let in, with everything the current strictness uses."""
    prof, label = find_profile(mic)
    if prof is None:
        return {"ok": False, "why": "no voice has been trained yet"}
    emb = embedder or Embedder()
    if prof.embedder and emb.name != prof.embedder:
        return {"ok": False, "why": "your voice was trained with a different voice check; "
                                    "train it again first"}
    strictness = settings()["strictness"]
    strong = _pick_strong(strong, emb, strictness)
    steps = plan(strictness, emb, strong, prof)
    dec, role = steps[-1]
    if not prof.subprints(dec.name):
        dec, role = emb, strictness            # a print from before the strong model
    scores, passed = [], []
    for c in clips:
        vecs = _vectors(c, emb, strong, sample_rate)
        v = vecs.get(dec.name) or []
        s, _sp = _nearest(v, prof.subprints(dec.name))
        scores.append(round(s, 4) if v else None)
        passed.append(bool(v) and _judge(vecs, prof, emb, strong, strictness)[0].is_owner)
    own = [x for sp in prof.subprints(dec.name) for x in sp.get("self_scores", [])]
    return {"ok": True, "scores": scores, "threshold": raw_bar(prof, dec.name, role),
            "owner_scores": own or list(prof.self_scores), "print": label, "passed": passed,
            "strictness": strictness, "model": "strong" if dec is strong else "small",
            "floor": floor_for(dec.name, BALANCED)}


#: Never suggest a bar above this: a real voice varies more than a
#: synthetic one, and a print that refuses its owner half the time is
#: worse than useless.
MAX_SUGGESTED = 0.9


def suggest_threshold(owner_scores: list, other_scores: list, floor: float = MIN_THRESHOLD) -> dict:
    """A bar between how the owner scores and how someone else scores.

    Only when the two are apart: the owner's LOWEST training clip must beat
    the other person's HIGHEST clip. Then the suggestion is halfway between
    them - never below `floor` (the model's own). Otherwise there is no safe
    number - raising the bar far enough to refuse the other person would
    refuse the owner too - and it says so.
    """
    own = [float(s) for s in owner_scores if isinstance(s, (int, float))]
    other = [float(s) for s in other_scores if isinstance(s, (int, float))]
    if not own or not other:
        return {"separated": False, "suggested": None,
                "why": "not enough to compare (train your voice again to record your own scores)"}
    low, high = min(own), max(other)
    if high >= low:
        return {"separated": False, "suggested": None, "owner_low": round(low, 4),
                "others_high": round(high, 4),
                "why": ("someone else scored as high as you did, so a stricter setting would "
                        "refuse you too")}
    suggested = round(min(MAX_SUGGESTED, max(MIN_THRESHOLD, floor, (low + high) / 2)), 2)
    return {"separated": True, "suggested": suggested, "owner_low": round(low, 4),
            "others_high": round(high, 4), "why": ""}


def set_threshold(value: float, mic: str = "", model: str = "") -> VoiceProfile:
    """Writes a new bar into `mic`'s own print (or the one it falls back
    to), for the model named `model` (an embedder name; the small model's
    when empty). Called ONLY after an approval card said yes - see
    jarvis_voice_enroll.stage_threshold. Raises ValueError, in words, when
    there is nothing to change - or when the bar would be below the
    model's own floor, which no card can lower it past."""
    prof, label = find_profile(mic)
    if prof is None:
        raise ValueError("no voice has been trained yet")
    name = model or prof.embedder
    lowest = floor_for(name, BALANCED)
    if _clamp_threshold(value) < lowest:
        raise ValueError(f"the lowest this voice check allows is {lowest:.2f}")
    if not model or model == prof.embedder:
        prof.threshold = _clamp_threshold(value)
    else:
        if not prof.subprints(model):
            raise ValueError("your voice print has nothing from that voice-ID model yet - "
                             "train your voice again first")
        prof.thresholds[model] = _clamp_threshold(value)
    path = Path(PROFILE_PATH) if label == "general" else profile_path(label)
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
    #: Which print decided: "phone", "desktop", "general" (the old
    #: owner.json), or "" when none did.
    voice_print: str = ""
    #: Since 2026-09-24: the strictness this was judged at, and one line per
    #: model that was asked - {"model", "score", "bar", "norm", "norm_bar",
    #: "condition", "passed"} (`norm` is None with no comparison voices).
    strictness: str = ""
    checks: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


#: Said when no speaker model is installed. The fallback cannot tell two
#: people apart, so it never decides who is the owner.
NO_MODEL_REASON = ("no voice-ID model is installed, so Jarvis cannot tell your voice from "
                   "anyone else's and will not take spoken commands - install the voice-ID "
                   "model (backend/README.md, \"Install the better voice check\")")


def _nearest(v: list, subs: list) -> tuple:
    """(best similarity, that sub-print) - the nearest sub-print wins."""
    best, which = 0.0, None
    for sp in subs:
        s = cosine(v, sp["centroid"])
        if which is None or s > best:
            best, which = s, sp
    return best, which


def _vectors(audio, emb, strong, sample_rate) -> dict:
    """{embedder name: vector} for the small model and, if given, the strong
    one. A failure is an empty vector, never an exception."""
    out = {}
    for mod in (emb, strong):
        if mod is None or getattr(mod, "name", None) in out:
            continue
        try:
            out[mod.name] = _as_vector(_embed(mod, audio, sample_rate))
        except Exception:
            out[mod.name] = []
    return out


def plan(strictness: str, emb, strong, prof: Optional[VoiceProfile] = None) -> list:
    """[(model, role)] - which model a clip is put to, and at which bar:

        stronger model installed (and in the print)  the strong one alone,
                                                     at the strictness's bar
        otherwise                                    the small one alone

    THE OWNER'S DECISION, 2026-09-24: very strict uses the stronger model
    ALONE, at its very-strict bar - not both models together. Measured here
    (backend/README.md, "The stricter voice check"), the stronger model alone
    at 0.50 turned the owner away 5.8% of the time against 10.5% for the
    pair, and let in about the same strangers (0.49% against 0.40%). The
    "paired" bars stay in MODEL_BARS for the record; nothing asks for them.

    A print trained before the stronger model was installed has no
    sub-print for it: very strict still asks the stronger model, which then
    refuses with "train your voice again" - it never quietly falls back to
    the weaker small model. Balanced does fall back, as it always did.

    The last one listed is the one that "decides" (the "someone else"
    check measures it)."""
    if strictness == VERY_STRICT:
        return [(strong, VERY_STRICT)] if strong is not None else [(emb, VERY_STRICT)]
    if strong is not None and (prof is None or prof.subprints(strong.name)):
        return [(strong, BALANCED)]
    return [(emb, BALANCED)]


def raw_bar(prof: VoiceProfile, name: str, role: str) -> float:
    """The raw bar for model `name` in `role`: the measured one, raised by
    the owner's own bar for that model (the "someone else" card) - except
    for the small model when it is paired, where the stronger model is the
    one the owner's bar was measured on."""
    table = bar_for(name, role)[0]
    if name == prof.embedder or not prof.embedder:
        own = prof.threshold if role != "paired" else 0.0
    else:
        own = float(prof.thresholds.get(name, 0.0) or 0.0)
    return max(table, own)


def _judge(vecs: dict, prof: VoiceProfile, emb, strong, strictness: str) -> tuple:
    """(Verdict, compared) - the comparison itself: no settings read, no
    counting, no side effects; verify(), measure() and score_clips() all
    use it. `compared` is whether any voice was actually compared (not
    refused before that, for a silent clip or a missing sub-print)."""
    checks, first_fail, compared = [], "", False
    for mod, role in plan(strictness, emb, strong, prof):
        v = vecs.get(mod.name) or []
        label = bars_for(mod.name)["label"]
        bar = raw_bar(prof, mod.name, role)
        nbar = bar_for(mod.name, role)[1]
        subs = prof.subprints(mod.name)
        blank = {"model": label, "role": role, "score": 0.0, "bar": round(bar, 4),
                 "norm": None, "norm_bar": None, "condition": "", "passed": False}
        if not subs:
            checks.append(blank)
            first_fail = first_fail or (
                "your voice print was made before the stronger voice-ID model was "
                "installed - train your voice again")
            continue
        if not v:
            checks.append(blank)
            first_fail = first_fail or "clip too short or silent to identify a voice"
            continue
        if len(v) != len(subs[0]["centroid"]):
            checks.append(blank)
            first_fail = first_fail or "profile and embedder disagree about vector size"
            continue
        s, sp = _nearest(v, subs)
        if not math.isfinite(s):
            s = 0.0
        compared = True
        norm = None
        if nbar is not None:
            bank, _info = cohort_for(mod.name)
            # A bank of another width is not for this model (a wrong or
            # damaged file): it can say nothing, so it is not used - the raw
            # bar still applies - and status() says so (cohort ... "matches").
            if bank and len(bank[0]) == len(v):
                try:
                    norm = as_norm(s, v, sp["centroid"], bank)
                except Exception:
                    norm = None
                if norm is not None and not math.isfinite(norm):
                    norm = None
        ok = s >= bar and (norm is None or norm >= nbar)
        checks.append({**blank, "score": round(s, 4),
                       "norm": None if norm is None else round(norm, 2),
                       "norm_bar": None if norm is None else nbar,
                       "condition": sp.get("condition", ""), "passed": ok})
        if not ok and not first_fail:
            if s < bar:
                first_fail = (f"does not match the enrolled voice ({s:.2f} < {bar:.2f})"
                              + (", on the stronger voice-ID model"
                                 if strong is not None and mod is strong else ""))
            else:
                first_fail = ("does not match the enrolled voice clearly enough: it is "
                              f"not much closer to yours than to other people's "
                              f"({norm:.1f} < {nbar:.1f})")
    ok = bool(checks) and all(c["passed"] for c in checks)
    # The number shown is the check that failed, or the deciding one.
    head = next((c for c in checks if not c["passed"]), checks[-1] if checks else None)
    head = head or {"score": 0.0, "bar": prof.threshold}
    return Verdict(ok, score=head["score"], threshold=head["bar"],
                   reason="recognised" if ok else first_fail, strictness=strictness,
                   checks=checks), compared


def _pick_strong(strong, emb, strictness: str = ""):
    """The stronger model to use: a test's own, none (False), or - None -
    the installed one (both settings use it; see plan())."""
    if strong is False:
        return None
    if strong is None:
        return strong_embedder(emb)
    return strong


def verify(audio, embedder=None, sample_rate: Optional[int] = None,
           mic: str = "", strong=None) -> Verdict:
    """Is this the owner? Called by jarvis_speech before any transcription.

    ORDER MATTERS. jarvis_speech's own comment explains why this must answer
    before a transcript exists: "A voice that is not the owner's is never
    turned into words - refusing after transcribing would leave a stranger's
    speech in memory on the way to saying no."

    Every path that is not a clean pass returns is_owner=False with a reason.

    `strong`: the stronger model, for very strict. None means "load it if it
    is installed" (strong_embedder); a test passes its own, or False for
    "there is none".
    """
    mode = str(_cfg("mode", "owner") or "owner").strip().lower()

    if not bool(_cfg("enabled", True)):
        return Verdict(False, mode=mode, reason="voice is switched off in the config")

    if mode == "broad":
        # The owner's explicit choice, reported every time so it is never a
        # silent state. No embedding is computed: there is nothing to check.
        return Verdict(True, score=1.0, threshold=0.0, mode="broad",
                       reason="mode is broad: any voice is accepted")

    prof, label = find_profile(mic)
    if prof is None:
        return Verdict(False, mode=mode,
                       reason="no enrolled voice profile - run enrolment first")

    emb = embedder or Embedder()
    if not getattr(emb, "semantic", False):
        # HOLE 1 (2026-09-24). The spectral fallback cannot tell two people
        # apart, and it used to answer is_owner=True for anyone close enough
        # to the print - which, measured, was everyone.
        return Verdict(False, threshold=prof.threshold, mode=mode, reason=NO_MODEL_REASON)
    if prof.embedder and emb.name != prof.embedder:
        # Vectors from two different models are not comparable, and comparing
        # them anyway produces a plausible number that means nothing. The same
        # trap jarvis_memory handles by rebuilding on an embedder change; here
        # there is nothing to rebuild without the owner's voice, so it refuses.
        return Verdict(False, threshold=prof.threshold, mode=mode,
                       reason=(f"profile was enrolled with {prof.embedder!r} but "
                               f"{emb.name!r} is loaded - re-enrol to use it"))

    strictness = settings()["strictness"]
    strong = _pick_strong(strong, emb, strictness)
    # Only the models this clip is put to (balanced with the stronger model
    # asks that one alone) - each is ~30-110 ms of processor time.
    asked = [m for m, _role in plan(strictness, emb, strong, prof)]
    try:
        vecs = _vectors(audio, asked[0], asked[1] if len(asked) > 1 else None,
                        sample_rate)
    except Exception as exc:
        return Verdict(False, threshold=prof.threshold, mode=mode,
                       reason=f"could not read the audio ({type(exc).__name__})")
    v, compared = _judge(vecs, prof, emb, strong, strictness)
    v.mode = mode
    if compared:
        v.voice_print = label
        note_outcome(v.is_owner, strictness, mic)
    return v


def embed_with(model, audio, sample_rate: Optional[int] = None) -> list:
    """One clip through one model, as a plain list of floats ([] when it
    cannot be read) - never raises. For comparing a clip with something
    that is not a voice print (jarvis_voice_flow compares it with Jarvis's
    own voice)."""
    try:
        return _as_vector(_embed(model, audio, sample_rate))
    except Exception:
        return []


def judge(audio, embedder=None, sample_rate: Optional[int] = None, mic: str = "",
          strictness: str = BALANCED, strong=None) -> tuple:
    """(Verdict, the clip's vector, the model that decided) - "does this
    sound like the owner's voice print?", and nothing else.

    For interrupting Jarvis by talking (jarvis_voice_flow.barge_in), where
    the only thing a yes can do is stop Jarvis speaking. So, unlike
    verify(): it is not counted towards the owner's repeat rate (it is not
    a command they had to say again), and `broad` mode is a NO - "any voice
    is accepted" would let the TV stop Jarvis, which is exactly what this
    must not do. Every other refusal is verify()'s own, in its words.

    `strictness`: which bar (balanced by default: a stop that should not
    have happened only cuts a reply short). The vector and model are None
    whenever no voice was compared."""
    mode = str(_cfg("mode", "owner") or "owner").strip().lower()
    if not bool(_cfg("enabled", True)):
        return Verdict(False, mode=mode, reason="voice is switched off in the config"), None, None
    if mode == "broad":
        return (Verdict(False, mode=mode,
                        reason=("the voice check is in broad mode (any voice is accepted), so "
                                "it cannot tell your voice from anyone else's")), None, None)
    prof, label = find_profile(mic)
    if prof is None:
        return (Verdict(False, mode=mode,
                        reason="no enrolled voice profile - run enrolment first"), None, None)
    emb = embedder or Embedder()
    if not getattr(emb, "semantic", False):
        return Verdict(False, threshold=prof.threshold, mode=mode, reason=NO_MODEL_REASON), None, None
    if prof.embedder and emb.name != prof.embedder:
        return (Verdict(False, threshold=prof.threshold, mode=mode,
                        reason=(f"profile was enrolled with {prof.embedder!r} but "
                                f"{emb.name!r} is loaded - re-enrol to use it")), None, None)
    if strictness not in STRICTNESS:
        strictness = BALANCED
    strong = _pick_strong(strong, emb, strictness)
    asked = [m for m, _role in plan(strictness, emb, strong, prof)]
    try:
        vecs = _vectors(audio, asked[0], asked[1] if len(asked) > 1 else None, sample_rate)
    except Exception as exc:
        return (Verdict(False, threshold=prof.threshold, mode=mode,
                        reason=f"could not read the audio ({type(exc).__name__})"), None, None)
    v, compared = _judge(vecs, prof, emb, strong, strictness)
    v.mode = mode
    if not compared:
        return v, None, None
    v.voice_print = label
    decider = asked[-1]
    return v, vecs.get(decider.name) or None, decider


def measure(clips: list, embedder=None, sample_rate: Optional[int] = None,
            mic: str = "", strong=None, seconds: Optional[list] = None) -> dict:
    """The guided "how often would I have to repeat myself?" test: the
    owner's own sentences, each judged at BOTH strictness settings (and
    each setting's shortest sentence). Numbers only; nothing stored,
    nothing counted towards repeat_counts()."""
    prof, label = find_profile(mic)
    if prof is None:
        return {"ok": False, "why": "no voice has been trained yet"}
    emb = embedder or Embedder()
    if not getattr(emb, "semantic", False):
        return {"ok": False, "why": NO_MODEL_REASON}
    if prof.embedder and emb.name != prof.embedder:
        return {"ok": False, "why": "your voice was trained with a different voice check; "
                                    "train it again first"}
    strong = _pick_strong(strong, emb, VERY_STRICT)
    rate = int(sample_rate or 16000)
    per, totals = [], {s: {"passed": 0, "too_short": 0} for s in STRICTNESS}
    for n, c in enumerate(clips):
        secs = (seconds[n] if seconds and n < len(seconds)
                else len(_pcm(c)) / float(rate))
        vecs = _vectors(c, emb, strong, sample_rate)
        row = {"seconds": round(secs, 2)}
        for s in STRICTNESS:
            short = secs < MIN_COMMAND_SECONDS[s]
            v, _compared = _judge(vecs, prof, emb, strong, s)
            ok = v.is_owner and not short
            row[s] = ok
            totals[s]["passed"] += ok
            totals[s]["too_short"] += short
            if s == VERY_STRICT:
                row["score"] = v.score
        per.append(row)
    n = len(per)
    return {"ok": True, "clips": n, "print": label,
            "strong_model": strong is not None,
            **{s: {**totals[s], "of": n,
                   "repeat_rate": round(1 - totals[s]["passed"] / n, 3) if n else 0.0}
               for s in STRICTNESS},
            "per_clip": per}


# --------------------------------------------------------------------------
#   How often the owner has to say it twice - counted, in memory
# --------------------------------------------------------------------------

#: A refusal followed by an acceptance within this many seconds is counted
#: as "you had to say it again".
REPEAT_WINDOW = 10.0
_REPEAT_LOCK = threading.Lock()
_REPEAT: dict = {}
_REPEAT_SINCE = time.time()
_LAST_REFUSAL: dict = {}


def _blank_counts() -> dict:
    return {"accepted": 0, "refused": 0, "too_short": 0, "refused_then_accepted": 0}


def note_outcome(accepted: bool, strictness: str, mic: str = "",
                 too_short: bool = False, now: Optional[float] = None) -> None:
    """Counts one voice check. Never raises; numbers only."""
    t = time.monotonic() if now is None else now
    s = strictness if strictness in STRICTNESS else VERY_STRICT
    m = clean_mic(mic)
    with _REPEAT_LOCK:
        c = _REPEAT.setdefault(s, _blank_counts())
        if accepted:
            c["accepted"] += 1
            last = _LAST_REFUSAL.pop(m, None)
            if last is not None and t - last <= REPEAT_WINDOW:
                c["refused_then_accepted"] += 1
        else:
            c["too_short" if too_short else "refused"] += 1
            _LAST_REFUSAL[m] = t


def repeat_counts() -> dict:
    """{"window_seconds", "since", "very_strict": {...}, "balanced": {...}}
    - each {accepted, refused, too_short, refused_then_accepted,
    repeat_rate}. Since this process started; nothing is kept on disk."""
    with _REPEAT_LOCK:
        out = {"window_seconds": REPEAT_WINDOW, "since": _REPEAT_SINCE}
        for s in STRICTNESS:
            c = dict(_REPEAT.get(s) or _blank_counts())
            c["repeat_rate"] = (round(c["refused_then_accepted"] / c["accepted"], 3)
                                if c["accepted"] else 0.0)
            out[s] = c
    return out


def _reset_repeat_for_tests() -> None:
    global _REPEAT_SINCE
    with _REPEAT_LOCK:
        _REPEAT.clear()
        _LAST_REFUSAL.clear()
        _REPEAT_SINCE = time.time()


# --------------------------------------------------------------------------
#   "May this answer be read aloud?"
# --------------------------------------------------------------------------

#: What counts as private for reading aloud: email, calendar, notes, and
#: what Jarvis remembers. A backstop list for when jarvis_router (which has
#: the full one) cannot be imported.
_PRIVATE_WORDS = ("email", "e-mail", "inbox", "calendar", "appointment", "meeting",
                  "note", "notes", "journal",
                  # Health and money: both apps promise a question about these
                  # stays on screen (the "read memories aloud" choice). The
                  # router's list only had narrower words (medical, bank,
                  # salary...), so "how much money do I have left" was spoken
                  # (fit audit, 2026-09-24).
                  "health", "doctor", "doctors", "medicine", "medication", "medications",
                  "pills", "therapy", "therapist", "hospital", "symptoms",
                  "money", "debt", "debts", "loan", "loans", "mortgage", "savings",
                  "income", "spending", "budget",
                  "password", "passwords", "pin")
#: Asking about what Jarvis remembers counts as private only while the owner
#: keeps memory answers on screen (the "memory" setting).
_MEMORY_WORDS = ("remember", "memory", "memories")


def looks_private(text: str) -> bool:
    """Whether a question is about something private (the router's own
    private-topic backstop, plus notes and memory)."""
    t = str(text or "").lower()
    try:
        import jarvis_router
        if jarvis_router.is_private(t):
            return True
    except Exception:
        pass
    words = set("".join(ch if ch.isalnum() or ch == "-" else " " for ch in t).split())
    if any(w in words for w in _PRIVATE_WORDS):
        return True
    return not memory_aloud() and any(w in words for w in _MEMORY_WORDS)


def memory_aloud() -> bool:
    """May an answer that uses what Jarvis remembers (and asks about nothing
    else private) be read aloud when asked by voice? Yes by default (the
    owner's choice); no with `memory_on_screen`. `voice_is_enough` - every
    private answer aloud - implies yes."""
    s = settings()
    if s["privacy"] == VOICE_IS_ENOUGH and s["strictness"] == VERY_STRICT:
        return True
    return s["memory"] == MEMORY_ALOUD


def sensitive_aloud() -> bool:
    """May an answer that uses a SENSITIVE saved fact be read aloud when
    asked by voice? Only with the `sensitive_aloud` setting - not implied by
    `memory_aloud` or `voice_is_enough` (the owner's decision, 2026-09-24).
    jarvis_speech adds the other half: only after a real voice check."""
    return settings()["sensitive_memory"] == SENSITIVE_ALOUD


def hands_free_trusted(source) -> bool:
    """Is a voice turn that came from `source` trusted like the talk button -
    may its answers be read aloud under the other settings, and may
    automatic learning save from it without a card?

    The talk button (`push_to_talk`): always. Anything else - `wake_word`,
    and a source that is missing or not known (fail closed) - only while
    the owner keeps the default, `same_as_button`."""
    if str(source or "").strip().lower() == PUSH_TO_TALK:
        return True
    return settings()["hands_free"] == SAME_AS_BUTTON


def may_speak(private: bool, origin: str = "voice") -> dict:
    """{"speak": bool, "why": str} - may an answer be read aloud?

    `private`: the answer draws on email, calendar, notes or memory.
    `origin`: "typed" or "tapped" (on the owner's own unlocked device), or
    "voice". Anything else counts as voice.

    Not private: yes. Asked on the owner's own device: yes. Asked by voice:
    only when the owner chose `voice_is_enough` - which can only be set
    while the check is very strict."""
    if not private:
        return {"speak": True, "why": ""}
    if str(origin or "").strip().lower() in ("typed", "tapped"):
        return {"speak": True, "why": "asked on your own device"}
    s = settings()
    if s["privacy"] == VOICE_IS_ENOUGH and s["strictness"] == VERY_STRICT:
        return {"speak": True, "why": "you chose: your voice is enough for private answers"}
    return {"speak": False,
            "why": ("private answers (email, calendar, notes, memory) are shown on your "
                    "screen, not read aloud, when you ask by voice")}


# --------------------------------------------------------------------------
#   status()
# --------------------------------------------------------------------------

def _prints_status(model: str, strong_name: str) -> dict:
    prints = {}
    for label, p in lookup_order(""):
        pr = load_profile(p)
        prints[label] = {
            "trained": pr is not None,
            "samples": pr.samples if pr else 0,
            "threshold": pr.threshold if pr else 0.0,
            "created": pr.created if pr else 0.0,
            "needs_retraining": bool(pr and pr.embedder and pr.embedder != model),
            # Since 2026-09-24: the recording conditions it holds, and
            # whether the stronger model has a print of its own in it.
            "subprints": ([{"condition": sp["condition"], "samples": sp["samples"]}
                           for sp in pr.subprints(pr.embedder or model)] if pr else []),
            "strong_trained": bool(pr and strong_name and pr.subprints(strong_name)),
            "strong_threshold": (pr.thresholds.get(strong_name, 0.0)
                                 if pr and strong_name else 0.0),
        }
    return prints


def status() -> dict:
    """What the voice gate can actually do right now. Read by jarvis_speech
    and reported to clients as a capability, so it must not overstate."""
    prof, _label = find_profile("")
    try:
        # "ecapa" for speechbrain, "sherpa-onnx:<hash>" for a model file.
        primary = EcapaEmbedder()
        model = primary.name
    except Exception:
        primary, model = None, "spectral-v1"
    speaker_model = model != "spectral-v1"
    strong = strong_embedder(primary) if primary is not None else None
    strong_name = strong.name if strong is not None else ""
    s = settings()
    very = s["strictness"] == VERY_STRICT
    prints = _prints_status(model, strong_name)
    # A profile made with one embedder cannot be checked with another -
    # verify() refuses it, correctly. That is exactly what happens the day
    # the better model is installed over a profile trained on the basic
    # check, and without this the owner would read "trained" and be refused.
    retrain = bool(prof and prof.embedder and prof.embedder != model)
    # Very strict with the strong model installed refuses a print that has
    # no strong sub-print: the same "train again", for the same reason.
    strong_missing_in_print = bool(prof and very and strong_name
                                   and not prof.subprints(strong_name))
    notes = []
    if not speaker_model:
        n = ("no voice-ID model is installed: spoken commands are refused until it is "
             "(the basic check that stands in cannot tell two people apart)")
        if _speaker_model_error:
            n += f" ({_speaker_model_error})"
        notes.append(n)
    elif strong is None:
        n = ("only the small voice-ID model is installed, so " +
             ("very strict is using it instead of the stronger one, and will turn you "
              "away far more often" if very else "balanced is using it alone") +
             " - and measured here, it alone does not reliably keep other people out. "
             f"Install the stronger one (looked for {strong_model_path()})")
        if _strong_model_error:
            n += f" - {_strong_model_error}"
        notes.append(n)
    if speaker_model and not bars_for(model)["known"]:
        notes.append("the voice-ID model installed is not one whose bars were measured, so "
                     "Jarvis cannot say how well it keeps other people out")
    if retrain:
        notes.append("your voice was trained with a different voice check than the one "
                     "installed now, so it will be refused until you train it again")
    elif strong_missing_in_print:
        notes.append("your voice print was made before the stronger voice-ID model was "
                     "installed, so very strict refuses it until you train your voice again")

    def _bank(name, emb):
        if not name:
            return None
        vecs, info = cohort_for(name)
        if not vecs:
            return None
        dim = getattr(emb, "dim", 0)
        return {"speakers": info["speakers"], "source": info["source"],
                "where": info["where"],
                # False: the bank is not the model's width, so it is not used.
                "matches": not dim or len(vecs[0]) == int(dim)}

    return {
        "enabled": bool(_cfg("enabled", True)),
        "mode": str(_cfg("mode", "owner") or "owner"),
        "enrolled": prof is not None,
        "samples": prof.samples if prof else 0,
        "threshold": prof.threshold if prof else _clamp_threshold(_cfg("threshold", 0.35)),
        "embedder": model,
        "speaker_model": speaker_model,
        "profile_embedder": prof.embedder if prof else "",
        "needs_retraining": retrain or strong_missing_in_print,
        "speaker_model_path": str(speaker_model_path()),
        "wake_phrase": _cfg("wake_phrase", "hey_jarvis"),
        "wake_word_enabled": bool(_cfg("wake_word_enabled", False)),
        "note": ". ".join(notes),
        # One print per microphone ("general" is the old owner.json).
        "prints": prints,
        # ---- the stricter check (2026-09-24) -----------------------------
        "strictness": s["strictness"],
        "privacy": s["privacy"],
        "memory": s["memory"],
        "sensitive_memory": s["sensitive_memory"],
        "hands_free": s["hands_free"],
        "settings": {
            "strictness": s["strictness"], "privacy": s["privacy"],
            "memory": s["memory"], "sensitive_memory": s["sensitive_memory"],
            "hands_free": s["hands_free"],
            "changed": s["changed"],
            "voice_is_enough_allowed": very,
            "min_command_seconds": MIN_COMMAND_SECONDS[s["strictness"]],
            "choices": {"strictness": list(STRICTNESS), "privacy": list(PRIVACY),
                        "memory": list(MEMORY),
                        "sensitive_memory": list(SENSITIVE_MEMORY),
                        "hands_free": list(HANDS_FREE)},
            "defaults": dict(DEFAULTS),
        },
        "models": {
            "small": {"installed": speaker_model, "name": model if speaker_model else "",
                      "label": bars_for(model)["label"] if speaker_model else "",
                      "bars_measured": bool(speaker_model and bars_for(model)["known"]),
                      "path": str(speaker_model_path())},
            "strong": {"installed": strong is not None, "name": strong_name,
                       "label": bars_for(strong_name)["label"] if strong_name else "",
                       "bars_measured": bool(strong_name and bars_for(strong_name)["known"]),
                       "path": str(strong_model_path()),
                       "why": _strong_model_error},
            # How many models very strict asks right now, and which one
            # balanced asks ("strong", "small", or "" with none installed).
            # Since 2026-09-24 very strict asks ONE model (the stronger one
            # alone when it is installed); very_strict_model says which.
            "very_strict_uses": 1 if speaker_model else 0,
            "very_strict_model": ("" if not speaker_model else
                                  "strong" if strong is not None else "small"),
            "balanced_uses": ("" if not speaker_model else
                              "strong" if strong is not None and (
                                  prof is None or prof.subprints(strong_name)) else "small"),
        },
        "cohort": {"small": _bank(model if speaker_model else "", primary),
                   "strong": _bank(strong_name, strong)},
        "repeat": repeat_counts(),
    }


# --------------------------------------------------------------------------
#   Building a bank of other voices from real recordings, on the owner's PC
# --------------------------------------------------------------------------

def _read_audio_file(p: Path):
    """(float samples, rate) from a 16-bit WAV, or a FLAC when the soundfile
    package is installed; None otherwise."""
    if p.suffix.lower() == ".wav":
        try:
            with wave.open(str(p), "rb") as w:
                if w.getsampwidth() != 2:
                    return None
                raw, rate, ch = w.readframes(w.getnframes()), w.getframerate(), w.getnchannels()
        except Exception:
            return None
        a = array.array("h")
        a.frombytes(raw[: len(raw) // 2 * 2])
        x = [v / 32768.0 for v in a]
        if ch > 1:
            x = [sum(x[i:i + ch]) / ch for i in range(0, len(x) - ch + 1, ch)]
        return x, rate
    if p.suffix.lower() == ".flac":
        try:
            import soundfile
            data, rate = soundfile.read(str(p), dtype="float32", always_2d=True)
        except Exception:
            return None
        return [float(v) for v in data.mean(axis=1)], int(rate)
    return None


def build_cohort(folder, embedders: Optional[list] = None, speakers: int = 300,
                 per_speaker: int = 3, out_dir: Optional[Path] = None) -> dict:
    """Builds a bank of other voices from a folder with one sub-folder per
    speaker (LibriSpeech's layout: <speaker>/<chapter>/<clip>.flac). For
    each installed model: one averaged, unit-length vector per speaker,
    written to cohort/<model hash>.json beside the voice prints. The audio
    is only read; nothing of it is kept but those numbers."""
    root = Path(folder)
    if embedders is None:
        embedders = []
        try:
            embedders.append(EcapaEmbedder())
        except Exception:
            pass
        st = strong_embedder(embedders[0] if embedders else None)
        if st is not None:
            embedders.append(st)
    embedders = [e for e in embedders if getattr(e, "semantic", False)]
    if not embedders:
        return {"ok": False, "why": NO_MODEL_REASON}
    dirs = sorted(d for d in root.iterdir() if d.is_dir()) if root.is_dir() else []
    if not dirs:
        return {"ok": False, "why": f"no speaker folders in {root}"}
    banks = {e.name: [] for e in embedders}
    used = 0
    for d in dirs:
        if used >= speakers:
            break
        files = sorted(f for f in d.rglob("*") if f.suffix.lower() in (".wav", ".flac"))
        got = {e.name: [] for e in embedders}
        for f in files:
            if len(next(iter(got.values()))) >= per_speaker:
                break
            read = _read_audio_file(f)
            if read is None or len(read[0]) < read[1]:         # under a second
                continue
            for e in embedders:
                v = _as_vector(_embed(e, read[0], read[1]))
                if v:
                    got[e.name].append(v)
        if all(got[e.name] for e in embedders):
            for e in embedders:
                banks[e.name].append(_mean_unit(got[e.name]))
            used += 1
    if used < 10:
        return {"ok": False, "why": f"only {used} speakers could be read from {root}; "
                                    f"at least 10 are needed"}
    written = {}
    for e in embedders:
        vecs = banks[e.name]
        try:
            import jarvis_voicebank
            shipped = decode_bank(jarvis_voicebank.BANKS.get(e.name) or {})
        except Exception:
            shipped = []
        source = f"{len(vecs)} real speakers from {root.name}"
        if shipped:
            source += f" + {len(shipped)} voices shipped with Jarvis (Speech Commands)"
        doc = encode_bank(e.name, vecs + shipped, source)
        p = (Path(out_dir) / f"{_short(e.name)}.json") if out_dir else cohort_path(e.name)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(doc), encoding="utf-8")
        tmp.replace(p)
        written[bars_for(e.name)["label"]] = {"speakers": doc["speakers"], "path": str(p)}
    with _BANKS_LOCK:
        _BANKS.clear()
    return {"ok": True, "speakers": used, "written": written}


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 3 and sys.argv[1] == "--build-cohort":
        out = build_cohort(sys.argv[2])
        if out.get("ok"):
            print(f"  OK - {out['speakers']} other voices read.")
            for label, w in out["written"].items():
                print(f"  {label}: {w['speakers']} voices -> {w['path']}")
        else:
            print("  Not built: " + out.get("why", ""))
        sys.exit(0 if out.get("ok") else 1)
    for k, v in status().items():
        print(f"  {k:<20} {v}")
