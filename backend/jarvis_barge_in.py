"""jarvis_barge_in.py - true barge-in with echo cancellation: PHASE 1 PROTOTYPE.

OFF BY DEFAULT, NOT WIRED, AND IT CHANGES NOTHING ON THE OWNER'S PC. This
module is the prototype half of Voice Slice F (2026-10-21): a reference-
subtraction echo canceller and a barge-in decision, built so the design in
``docs/DESIGN-VOICE-BARGE-IN.md`` can be tested deterministically before
anything touches the live microphone path. No live module imports it; no
route calls it; no switch it reads is on. The owner's ``[voice] aec_barge_in``
switch (default **false**) is the one the real wiring will read; here it only
decides whether the detector will process a frame at all.

WHAT IT DOES, IN ONE PARAGRAPH. Jarvis's own speech can be taken out of what
the microphone hears, because we made it: ``jarvis_speech.say()`` already has
the exact 16-bit PCM it is about to play. A normalized least-mean-squares
(NLMS) adaptive filter, fed that PCM as its reference, learns the echo path
(device latency, attenuation, a little room reflection) and subtracts it from
each microphone frame. What is left is the residual. When the residual holds
at least ``MIN_SPEECH_S`` (350 ms) of speech-shaped sound, and a supplied
owner check (CAM++ in the real design; a callable here) says the residual is
the owner's voice, the detector returns ONE decision dict saying
"should_stop". It does not stop anything; the design says the future wiring
would cut the reply and treat the interruption as the next turn.

WHY NO NEW DEPENDENCY YET. The exact-TTS-PCM reference is a perfect reference
for Jarvis's own voice, and a small NLMS filter over numpy (already needed by
every voice module) is enough to be measured deterministically. speexdsp or
the WebRTC canceller is only justified if this prototype fails the numbers in
the design (residual echo level, false-cut rate, barge-in latency); adding one
is a dependency and a ``requirements.lock`` change, so it is a decision for
the owner with evidence, not a convenience here.

THE PRIVACY RULE, AND WHAT IS ACTUALLY KEPT. The residual is audio from the
microphone, so it is treated like every other clip in this project:

  * it stays in memory only - nothing is written to disk, and this module has
    no file, network or logging call at all;
  * it is kept only for the speech run being judged (bounded: never more than
    ``MAX_RUN_S`` seconds), handed once to the owner check, and discarded in
    the same call; ``reset()``/``close()`` leave zero samples behind and the
    tests prove it;
  * nothing is transcribed, and no words are stored - the owner check is a
    speaker-embedding comparison on the residual, exactly as
    ``jarvis_voice_flow.barge_in()`` does today;
  * the reference is Jarvis's own voice, not the owner's.

WHY IT IS SEPARATE FROM THE SHIPPED BARGE-IN. ``jarvis_voice_flow.barge_in()``
(2026-09-24) answers "should Jarvis stop talking?" for a 2-second clip the
desktop sends when it thinks the owner is talking over a reply. That path is
already live and unchanged: the desktop's own loudness trigger, Windows'
communications echo cancelling when the machine has it (``aec.rs``), the
server's owner-print check, its "Jarvis's own voices" comparison, and the
``_SPEAKING_UNTIL`` self-echo gate in ``jarvis_speech``. This prototype is the
next step the audit asked for: use the EXACT reference we generate so the
residual is clean enough to judge 350 ms of speech and cut in one round trip
instead of two seconds, INCLUDING on open speakers where the driver's echo
canceller may not be there. The design doc carries the premise assessment and
what each path catches today.

WHAT "PROVEN" MEANS HERE. ``backend/test_barge_in.py`` drives synthetic
signals only (a synthetic reference, a delayed/attenuated echo, synthetic
speech and synthetic noise), so every number is labelled SYNTHETIC. Real
open-speaker barge-in needs the owner's microphone and speakers; until that
measurement it is NOT-MEASURED, and the module stays off and unwired.
"""
from __future__ import annotations

from typing import Callable, Optional

try:                    # the same framework the voice modules read
    import jarvis_framework as fw
except Exception:       # pragma: no cover - a backend without the framework
    fw = None  # type: ignore

try:                    # numpy is already required by the voice modules
    import numpy as np
except Exception:       # pragma: no cover - reported, never guessed
    np = None  # type: ignore


# ==========================================================================
#   The switch, and the numbers
# ==========================================================================

#: The config section and key the future wiring will read. Default FALSE: the
#: whole slice is off until the owner's hardware measures it (the project's
#: "own switch, off until measured" rule). Turning it on is one
#: ``change_own_config`` approval card; off is immediate.
SWITCH_SECTION = "voice"
SWITCH_KEY = "aec_barge_in"
SWITCH_DEFAULT = False

#: The voice path's rate. Both apps send 16 kHz; TTS PCM is resampled to this.
SAMPLE_RATE = 16000

#: One decision frame. 20 ms is the window the voice modules already use.
FRAME = 320

#: Least speech-shaped residual sound that may count as an interruption. The
#: shipped barge-in clip needs about a second; this is the 350 ms the design
#: promises once the echo is gone, and a false stop only cuts a reply short.
MIN_SPEECH_S = 0.35

#: Quiet frames that end a speech run (200 ms - the same idea as the caller's
#: loudness trigger, so a normal mid-sentence pause does not split the run).
HANG_FRAMES = 10

#: Frames at the start of an utterance that only WARM UP the canceller and the
#: echo-only floor. No decision can be made before this: the filter is still
#: learning the room, so its subtraction error is largest here and a music-like
#: sound during that moment could otherwise look like speech.
WARMUP_FRAMES = 30

#: The adaptive filter's length: 16 ms of reference history. It has to cover
#: the echo path's delay plus a little room tail; the design's measurement
#: plan tunes this on the owner's PC, and this value is only what makes the
#: synthetic harness work.
TAPS = 256

#: NLMS step size. Below 1 for stability; the step is normalized by the
#: reference power, so the filter cannot blow up on a loud sentence.
MU = 0.5

#: The smallest reference power the update is divided by. Without it a
#: quiet moment in the sentence (the TTS envelope dips towards zero) makes
#: the normalized step enormous and the filter's weights diverge - the
#: synthetic harness showed the prediction reaching 3x the echo it models.
POWER_FLOOR = 1e-4

#: Never divide by exactly zero when the reference is silent.
EPS = 1e-9

#: A residual frame is a speech CANDIDATE only when its RMS is this many times
#: the echo-only residual floor - the subtraction error that is left when
#: only Jarvis's voice is in the room. Someone speaking over it lifts the
#: residual far above that floor; the filter's own echo estimate is NOT used
#: for this test, because during double talk the filter must not adapt.
SPEECH_OVER_FLOOR = 3.0

#: ... and its RMS must clear this absolute floor, so a silent room with a
#: tiny error cannot be read as speech.
ABS_FLOOR = 0.010

#: Speech-shaped checks on the residual frame. Voiced speech has a low
#: zero-crossing rate and a harmonic (not flat) spectrum; a syllable envelope
#: makes the frame RMS move at 2-8 Hz. Music/TV-like sound fails at least one
#: of these in the synthetic harness - the real tuning needs the owner's room,
#: which is why the synthetic thresholds are deliberately generous and the
#: measurement plan lists false cuts as the number to watch.
ZCR_MIN = 0.004
ZCR_MAX = 0.30
FLATNESS_MAX = 0.35
MODULATION_MIN = 0.20

#: Frames of residual RMS kept for the modulation check: 300 ms.
MOD_WINDOW = 15

#: Echo-only residual RMS values the adaptive floor is taken from. Numbers
#: only (never audio): the median of the last ~800 ms of frames that were not
#: speech candidates. 40 frames is long enough to ignore the filter's first
#: noisy moments and short enough to follow a quiet room.
FLOOR_FRAMES = 40

#: A speech run is never held longer than this (3 s) - bounded memory, and a
#: run that long is not a barge-in, it is the owner talking while Jarvis talks.
MAX_RUN_S = 3.0
MAX_RUN_FRAMES = int(MAX_RUN_S * SAMPLE_RATE / FRAME)

#: The reasons a decision can carry. Only ``owner_voice`` may say
#: ``should_stop: true``; every other one fails closed.
REASON_OWNER = "owner_voice"
REASON_NOT_OWNER = "not_owner"
REASON_UNVERIFIED = "verify_unavailable"
REASON_VERIFY_ERROR = "verify_error"


def _switch_value(default: bool = SWITCH_DEFAULT):
    """The raw ``[voice] aec_barge_in`` value, or ``default`` if it cannot be read.

    Read fresh on every call, like every other voice switch: a config change
    takes effect for the next utterance without a restart. A framework that is
    missing, unreadable or raising means the default, never a guess.
    """
    if fw is None:
        return default
    try:
        section = fw.load_framework().get(SWITCH_SECTION) or {}
        return section.get(SWITCH_KEY, default)
    except Exception:
        return default


def _as_bool(value, default: bool = SWITCH_DEFAULT) -> bool:
    """The project's switch spelling: absent/broken is the default; a string
    is false for "", "false", "0", "no", "off" (case-insensitive)."""
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() not in ("false", "0", "no", "off", "")
    return bool(value)


def enabled() -> bool:
    """True only when ``[voice] aec_barge_in`` is explicitly on. Default: False."""
    return _as_bool(_switch_value(SWITCH_DEFAULT), SWITCH_DEFAULT)


# ==========================================================================
#   The echo canceller (NLMS over the reference we generated)
# ==========================================================================

class EchoCanceller:
    """One adaptive echo path, learned from Jarvis's own reference PCM.

    ``cancel_frame(mic, ref)`` returns the residual for one frame and updates
    the filter. The reference history is kept because the echo path has a
    delay (the player queues the sound, then the device plays it); ``taps``
    samples of history are enough for a small delay plus a room tail.

    ``adapt=False`` freezes the filter for the frame: called while the owner
    is judged to be speaking (double talk), so the filter cannot learn the
    owner's voice as if it were echo.

    Nothing here keeps the microphone: the residual frame is returned to the
    caller, and the only state is the filter weights plus the reference
    history (fixed size). ``reset()`` drops both.
    """

    def __init__(self, taps: int = TAPS, mu: float = MU, eps: float = EPS):
        self.taps = max(1, int(taps))
        self.mu = float(mu)
        self.eps = float(eps)
        self._w = None
        self._hist = None
        #: RMS of the filter's prediction for the last frame - a NUMBER, the
        #: filter's own estimate of the echo; never audio.
        self.last_prediction_rms = 0.0
        self.reset()

    def reset(self) -> None:
        """Forget the learned path and the reference history."""
        self.last_prediction_rms = 0.0
        if np is None:
            self._w = None
            self._hist = None
            return
        self._w = np.zeros(self.taps, dtype=np.float64)
        self._hist = np.zeros(self.taps, dtype=np.float64)

    @property
    def weights(self):
        """The learned path, as a copy (tests and the measured plan read it).
        Never audio: the filter's taps are the echo path, not the microphone."""
        if self._w is None:
            return None
        return self._w.copy()

    @property
    def reference_samples(self) -> int:
        """The fixed reference history's length (the history is overwritten in
        place, so this is a constant reminder that no clip grows here)."""
        return 0 if self._hist is None else int(self._hist.size)

    def cancel_frame(self, mic_frame, ref_frame, *, adapt: bool = True):
        """Return the residual frame after subtracting the learned echo."""
        if np is None:
            raise RuntimeError("numpy is not importable beside this module")
        mic = np.asarray(mic_frame, dtype=np.float64).reshape(-1)
        ref = np.asarray(ref_frame, dtype=np.float64).reshape(-1)
        if mic.size != ref.size or mic.size == 0:
            raise ValueError("mic and reference frames must be the same non-zero length")
        out = np.empty(mic.size, dtype=np.float64)
        preds = np.empty(mic.size, dtype=np.float64)
        w, hist = self._w, self._hist
        taps = self.taps
        for i in range(mic.size):
            # Shift the reference history and append this sample. The echo
            # path's delay lives inside this window, so the filter can learn
            # latency as well as attenuation.
            if taps > 1:
                hist[:-1] = hist[1:]
            hist[-1] = ref[i]
            pred = float(np.dot(w, hist))
            preds[i] = pred
            err = mic[i] - pred
            if adapt:
                power = max(float(np.dot(hist, hist)), POWER_FLOOR) + self.eps
                w += (self.mu * err / power) * hist
            out[i] = err
        self.last_prediction_rms = _frame_rms(preds)
        return out


# ==========================================================================
#   The decision
# ==========================================================================

def _frame_rms(x) -> float:
    if x is None or len(x) == 0:
        return 0.0
    x = np.asarray(x, dtype=np.float64)
    return float(np.sqrt(np.mean(x * x)))


def _zero_crossing_rate(x) -> float:
    x = np.asarray(x, dtype=np.float64)
    if x.size < 2:
        return 0.0
    return float(np.count_nonzero(np.signbit(x[1:]) != np.signbit(x[:-1]))
                 / (x.size - 1))


def _spectral_flatness(x) -> float:
    """Geometric / arithmetic mean of the frame's magnitude spectrum: high for
    noise (flat), low for a tone or voiced speech (peaky)."""
    x = np.asarray(x, dtype=np.float64)
    if x.size < 8:
        return 1.0
    spec = np.abs(np.fft.rfft(x * np.hanning(x.size))) + 1e-12
    geo = float(np.exp(np.mean(np.log(spec))))
    arith = float(np.mean(spec))
    return 1.0 if arith <= 0 else min(1.0, geo / arith)


def _modulation(frame_rms) -> float:
    """Coefficient of variation of the recent frame RMS: a syllable envelope
    moves it; a steady tone or noise does not."""
    if len(frame_rms) < 4:
        return 0.0
    x = np.asarray(frame_rms, dtype=np.float64)
    mean = float(np.mean(x))
    if mean <= 1e-12:
        return 0.0
    return float(np.std(x) / mean)


class BargeInDetector:
    """Frame feeder -> one barge-in decision (or None), never an action.

    Build one per utterance. ``feed(mic_frame, ref_frame)`` consumes 20 ms
    frames at ``sample_rate`` and returns a decision dict only when 350 ms of
    speech-shaped residual has built up and the supplied ``verifier`` said it
    is the owner. It never stops playback, never calls the voice modules and
    never logs; the future wiring owns those.

    ``verifier`` is the CAM++ hook: ``verifier(residual_audio, sample_rate) ->
    bool``. No verifier means no stop (fail closed), not "assume the owner".
    ``enabled`` is for tests only; the product reads the switch at
    construction (off immediately, no restart needed).
    """

    def __init__(self, *, verifier: Optional[Callable] = None,
                 enabled: Optional[bool] = None,
                 sample_rate: int = SAMPLE_RATE,
                 min_speech_s: float = MIN_SPEECH_S,
                 taps: int = TAPS):
        self.sample_rate = int(sample_rate)
        self.enabled = bool(self.switch()) if enabled is None else bool(enabled)
        self.verifier = verifier
        self.min_speech_s = float(min_speech_s)
        self.frame_samples = max(1, int(round(self.sample_rate * FRAME / SAMPLE_RATE)))
        self._min_frames = max(1, int(round(self.min_speech_s * self.sample_rate
                                            / float(self.frame_samples))))
        self._canceller = EchoCanceller(taps=taps) if (self.enabled and np is not None) else None
        self._closed = False
        self._frames_seen = 0
        self._run = []              # residual frames (numpy) of the active run
        self._run_frames = 0        # speech-shaped frames seen in this run
        self._quiet = 0
        self._echo_like = True      # previous frame looked like echo: safe to adapt
        self._rms_hist = []         # numbers only: recent residual RMS
        self._floor_hist = []       # numbers only: recent echo-only residual RMS
        self._echo_acc = 0.0        # prediction power sums (the ERLE proxy)
        self._res_acc = 0.0
        self._acc_n = 0
        self._last_residual_rms = 0.0
        self._last_echo_rms = 0.0
        self._last_erle_db: Optional[float] = None
        self._emitted = False

    # -- the switch --------------------------------------------------------
    @staticmethod
    def switch() -> bool:
        """The product switch read at construction. False by default."""
        return enabled()

    # -- public state (numbers only) ---------------------------------------
    @property
    def buffered_samples(self) -> int:
        """Residual samples currently held for the run being judged. Must be 0
        after a decision, ``reset()`` or ``close()``: no audio outlives the
        utterance it was heard in."""
        return 0 if not self._run else int(sum(f.size for f in self._run))

    @property
    def frames_seen(self) -> int:
        return int(self._frames_seen)

    def metrics(self) -> dict:
        """The numbers the design's measurement plan needs, all synthetic
        here. No audio anywhere in this dict."""
        return {
            "enabled": bool(self.enabled),
            "closed": bool(self._closed),
            "frames": int(self._frames_seen),
            "speech_ms": round(self._run_frames * 1000.0 * self.frame_samples
                               / float(self.sample_rate), 1),
            "retained_samples": int(self.buffered_samples),
            "last_residual_rms": round(float(self._last_residual_rms), 5),
            "last_echo_rms": round(float(self._last_echo_rms), 5),
            "erle_db": (None if self._last_erle_db is None
                        else round(float(self._last_erle_db), 2)),
        }

    # -- feeding -----------------------------------------------------------
    def feed(self, mic_frame, ref_frame) -> Optional[dict]:
        """Consume one frame; return a decision dict or None. Never raises for
        a bad frame (returns None), never acts, never logs."""
        if not self.enabled or self._closed or np is None:
            return None
        if self._emitted:
            # One decision per utterance. The caller resets (or builds a new
            # detector) for the next one; after this point no residual from the
            # judged run is stored anywhere.
            return None
        if self._canceller is None:
            return None
        try:
            mic = np.asarray(mic_frame, dtype=np.float64).reshape(-1)
            ref = np.asarray(ref_frame, dtype=np.float64).reshape(-1)
        except Exception:
            return None
        if mic.size == 0 or mic.size != ref.size:
            return None
        try:
            residual = self._canceller.cancel_frame(mic, ref, adapt=self._echo_like)
        except Exception:
            return None
        self._frames_seen += 1
        res_rms = _frame_rms(residual)
        echo_rms = float(self._canceller.last_prediction_rms)
        self._last_residual_rms = res_rms
        self._last_echo_rms = echo_rms
        if self._frames_seen <= WARMUP_FRAMES:
            # Warm-up: learn the room and build the echo-only floor. No
            # candidate, no decision; the residual level here is a number.
            self._floor_hist.append(res_rms)
            if len(self._floor_hist) > FLOOR_FRAMES:
                del self._floor_hist[:-FLOOR_FRAMES]
            self._rms_hist.append(res_rms)
            if len(self._rms_hist) > MOD_WINDOW:
                del self._rms_hist[:-MOD_WINDOW]
            return None
        # The echo-only floor is built ONLY from frames that look like echo:
        # a frame that already lifts the residual far above the floor must not
        # be added to it, or the owner's own speech (and every dip in its
        # syllable envelope) would raise the bar it has to clear.
        floor = self._residual_floor()
        ratio = res_rms >= SPEECH_OVER_FLOOR * (floor if floor is not None else ABS_FLOOR)
        echo_like = not ratio
        candidate = self._is_speech_candidate(residual, res_rms, ratio)
        self._echo_like = echo_like
        if candidate:
            self._run.append(residual.copy())
            self._run_frames += 1
            self._quiet = 0
            if self._run_frames > MAX_RUN_FRAMES:
                # Bounded: drop the oldest, keep judging (never unbounded audio).
                keep = MAX_RUN_FRAMES
                self._run = self._run[-keep:]
                self._run_frames = keep
        else:
            if echo_like:
                self._floor_hist.append(res_rms)
                if len(self._floor_hist) > FLOOR_FRAMES:
                    del self._floor_hist[:-FLOOR_FRAMES]
            if self._run:
                self._quiet += 1
                if self._quiet >= HANG_FRAMES:
                    self._drop_run()
        # ERLE proxy: how much quieter the echo-only residual is than the
        # filter's own echo estimate. Echo-like frames only.
        if echo_like:
            self._echo_acc += echo_rms * echo_rms
            self._res_acc += res_rms * res_rms
            self._acc_n += 1
            if self._acc_n >= 20:
                echo_e, res_e = self._echo_acc / self._acc_n, self._res_acc / self._acc_n
                if res_e > 1e-18:
                    self._last_erle_db = 10.0 * float(np.log10(max(echo_e, 1e-18) / res_e))
        self._rms_hist.append(res_rms)
        if len(self._rms_hist) > MOD_WINDOW:
            del self._rms_hist[:-MOD_WINDOW]
        # One decision per utterance: after it, the caller resets (or builds a
        # new detector) before another can be made.
        if (not self._emitted) and self._run_frames >= self._min_frames:
            return self._decide()
        return None

    # -- the judgement (private) ------------------------------------------
    def _residual_floor(self):
        """The echo-only residual level (a median), or None until there is
        enough history. NOT clamped up to the absolute floor: the floor is
        the subtraction error, which can be far quieter than the absolute
        gate - clamping it would hide a quiet owner's voice behind the gate."""
        if len(self._floor_hist) < 8:
            return None
        vals = sorted(self._floor_hist)
        mid = len(vals) // 2
        med = vals[mid] if len(vals) % 2 else 0.5 * (vals[mid - 1] + vals[mid])
        return max(float(med), 1e-6)

    def _is_speech_candidate(self, residual, res_rms: float, ratio: bool) -> bool:
        if not ratio or res_rms < ABS_FLOOR:
            return False
        zcr = _zero_crossing_rate(residual)
        if not (ZCR_MIN <= zcr <= ZCR_MAX):
            return False
        if _spectral_flatness(residual) > FLATNESS_MAX:
            return False
        return _modulation(self._rms_hist) >= MODULATION_MIN

    def _decide(self) -> dict:
        self._emitted = True
        audio = np.concatenate(self._run) if self._run else np.zeros(0)
        speech_ms = round(self._run_frames * 1000.0 * self.frame_samples
                          / float(self.sample_rate), 1)
        reason, verified = self._verify(audio)
        should_stop = bool(reason == REASON_OWNER and verified)
        event = {
            "barge_in": True,
            "should_stop": should_stop,
            "reason": reason,
            "verified": bool(verified),
            "speech_ms": speech_ms,
            "frames": int(self._run_frames),
            "residual_rms": round(float(_frame_rms(audio)), 5),
            "echo_rms": round(float(self._last_echo_rms), 5),
            "erle_db": (None if self._last_erle_db is None
                        else round(float(self._last_erle_db), 2)),
            "at_s": round(self._frames_seen * self.frame_samples
                          / float(self.sample_rate), 3),
            "residual_samples": int(audio.size),
        }
        # The residual's whole reason to exist was this decision: zero the
        # buffer the verifier saw, then drop the frames - now, not at the
        # caller's convenience.
        audio.fill(0.0)
        self._drop_run()
        return event

    def _verify(self, audio):
        if self.verifier is None:
            return REASON_UNVERIFIED, False
        try:
            answer = self.verifier(audio, self.sample_rate)
        except Exception:
            return REASON_VERIFY_ERROR, False
        return (REASON_OWNER if answer else REASON_NOT_OWNER), bool(answer)

    # -- lifetime ----------------------------------------------------------
    def _drop_run(self) -> None:
        # ZERO the residual frames before letting them go: the buffer is
        # memory-only and per-utterance, and nothing of it is left readable in
        # this process either. (The canceller's fixed reference history is
        # zeroed by reset()/close(); `_run` is the only other place audio lives.)
        for frame in self._run:
            try:
                frame.fill(0.0)
            except Exception:
                pass
        self._run = []
        self._run_frames = 0
        self._quiet = 0

    def reset(self) -> None:
        """Start a fresh utterance: no residual, reference history or decided
        state survives."""
        if self._canceller is not None:
            self._canceller.reset()
        self._drop_run()
        self._in_speech = False
        self._rms_hist = []
        self._floor_hist = []
        self._echo_acc = 0.0
        self._res_acc = 0.0
        self._acc_n = 0
        self._last_residual_rms = 0.0
        self._last_echo_rms = 0.0
        self._last_erle_db = None
        self._emitted = False

    def close(self) -> None:
        """Done with this detector: everything the utterance held is gone."""
        self._closed = True
        if self._canceller is not None:
            self._canceller.reset()
        self._drop_run()
        self._in_speech = False
        self._rms_hist = []
        self._floor_hist = []
        self._echo_acc = 0.0
        self._res_acc = 0.0
        self._acc_n = 0
        self._last_residual_rms = 0.0
        self._last_echo_rms = 0.0
        self._last_erle_db = None
        self._emitted = True


def frames(samples, frame_samples: int = FRAME):
    """Split a signal into frames (a test/measurement helper; no audio kept)."""
    if np is None:
        raise RuntimeError("numpy is not importable beside this module")
    x = np.asarray(samples, dtype=np.float64).reshape(-1)
    return [x[i:i + frame_samples] for i in range(0, x.size - frame_samples + 1,
                                                  frame_samples)]


def cancel_echo(mic, ref, *, taps: int = TAPS):
    """Run the canceller over two whole signals (measurement helper).

    Returns ``(residual, erle_db)`` where ERLE is measured on the last third,
    after the filter has had time to converge. Used by the suite and by the
    design's measurement plan; no audio is written anywhere.
    """
    if np is None:
        raise RuntimeError("numpy is not importable beside this module")
    mic = np.asarray(mic, dtype=np.float64).reshape(-1)
    ref = np.asarray(ref, dtype=np.float64).reshape(-1)
    n = min(mic.size, ref.size)
    if n == 0:
        return np.zeros(0), None
    canceller = EchoCanceller(taps=taps)
    residual = np.empty(n, dtype=np.float64)
    for start in range(0, n, FRAME):
        stop = min(n, start + FRAME)
        residual[start:stop] = canceller.cancel_frame(mic[start:stop], ref[start:stop])
    tail = max(1, n // 3)
    res_e = float(np.mean(residual[-tail:] ** 2))
    echo_e = float(np.mean(mic[-tail:] ** 2))
    erle = None if res_e <= 1e-18 else 10.0 * float(np.log10(max(echo_e, 1e-18) / res_e))
    return residual, erle
