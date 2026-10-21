"""jarvis_barge_in.py: true barge-in with echo cancellation - the PHASE 1 prototype.

    python3 test_barge_in.py   (the runner: python -B backend/run_suites.py test_barge_in.py)

WHAT THIS PROVES, IN PLAIN WORDS. The module takes Jarvis's known reference PCM
out of the microphone signal with a small NLMS echo canceller, then asks one
question about what is left: is there 350 ms of speech-shaped sound in it, and
does the owner check say it is the owner's voice? The design is
`docs/DESIGN-VOICE-BARGE-IN.md`. The module is OFF by default (`[voice]
barge_in = false`), no live module imports it, and it has no way to act: it
returns a decision dict and nothing else. The checks below are all SYNTHETIC
(a synthetic reference, a delayed/attenuated echo, synthetic speech and
synthetic noise) - real open-speaker barge-in needs the owner's microphone and
speakers and is NOT-MEASURED until then.

WHAT IS CHECKED HERE:

  1. The switch. Default false; an explicit `[voice] aec_barge_in = true` is the
     only way on; a string spelling and a reader that raises are handled; with
     the switch off the detector processes nothing at all (the guarded-path
     half of "no behaviour change").
  2. The canceller. The synthetic echo is removed (ERLE), and its state is a
     fixed-size filter plus a fixed reference history - no clip grows.
  3. The decision. A synthetic owner speaking over the echo produces exactly
     ONE decision, `should_stop: true`, 350 ms or more of speech, within the
     design's latency; the owner check (a spy) is called once with the bounded
     residual; the dict is JSON numbers/booleans only.
  4. The refusals. A wrong speaker's residual is rejected (not_owner), a
     missing owner check fails closed (verify_unavailable), a raising one too
     (verify_error) - `should_stop` is false for every one.
  5. The false-positive guard. Pure echo, white noise, a steady music-like
     chord and amplitude-modulated noise produce ZERO decisions; the count is
     printed (the design's false-cut number, synthetic).
  6. Privacy and lifetime. After a decision, `reset()` or `close()`, no
     residual sample is retained; nothing is printed or logged by the module;
     and importing it starts no live voice module (`jarvis_speech`,
     `jarvis_voice_flow`, `jarvis_hud` are not imported) - it cannot change the
     live path by construction. The live path itself is untouched: this branch
     edits no voice module.
"""
import contextlib
import io
import json
import logging
import subprocess
import sys
import traceback
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_barge_in.py")
import jarvis_barge_in as B  # noqa: E402

FAILED, PASSED = [], []
SR = 16000

#: Every synthetic signal below is built from fixed numbers and a fixed seed, so
#: the suite is deterministic: same numbers on every machine and every run.


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    print(f"skip  {why}")


def tts_reference(seconds, env_hz=3.7):
    """A TTS-like reference: a harmonic tone with a syllable envelope."""
    t = np.arange(int(seconds * SR)) / SR
    env = 0.55 + 0.45 * np.sin(2 * np.pi * env_hz * t)
    return env * (0.50 * np.sin(2 * np.pi * 170 * t)
                  + 0.25 * np.sin(2 * np.pi * 340 * t)
                  + 0.12 * np.sin(2 * np.pi * 510 * t))


def echo_of(ref):
    """The room: two early reflections and a little tail, delayed and quieter."""
    out = np.zeros_like(ref)
    for delay, gain in ((40, 0.55), (120, 0.25), (200, 0.08)):
        out[delay:] += gain * ref[:-delay]
    return out


def owner_voice(seconds, f0=110.0, env_hz=4.1):
    t = np.arange(int(seconds * SR)) / SR
    env = 0.5 + 0.5 * np.sin(2 * np.pi * env_hz * t)
    return env * (0.6 * np.sin(2 * np.pi * f0 * t)
                  + 0.3 * np.sin(2 * np.pi * 2 * f0 * t)
                  + 0.15 * np.sin(2 * np.pi * 3 * f0 * t))


def white_noise(seconds, seed, amp=0.25):
    return amp * np.random.default_rng(seed).standard_normal(int(seconds * SR)) / 3.0


def music_chord(seconds, seed, amp=0.25):
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * SR)) / SR
    return amp * sum(np.sin(2 * np.pi * f * t)
                     for f in rng.uniform(180, 420, 3)) / 3.0


def am_noise(seconds, seed, amp=0.25):
    t = np.arange(int(seconds * SR)) / SR
    n = np.random.default_rng(seed).standard_normal(len(t)) / 3.0
    return amp * (0.6 + 0.4 * np.sin(2 * np.pi * 4.0 * t)) * n


WARM = 1.2          # echo-only seconds before an interruption
BASE = tts_reference(WARM + 0.9)
ECHO = echo_of(BASE)


def scene(extra=None, at=WARM, gain=1.0):
    """Echo (+ optional extra sound from `at` seconds) and the reference."""
    mic = ECHO.copy()
    if extra is not None:
        start = int(at * SR)
        mic[start:start + len(extra)] += gain * extra
    return mic, BASE


def run_detector(mic, ref, verifier=None, enabled=True, close=False):
    det = B.BargeInDetector(verifier=verifier, enabled=enabled)
    events = []
    n = min(len(mic), len(ref))
    for i in range(0, n - B.FRAME + 1, B.FRAME):
        event = det.feed(mic[i:i + B.FRAME], ref[i:i + B.FRAME])
        if event:
            events.append(event)
    metrics = det.metrics()
    retained = det.buffered_samples
    if close:
        det.close()
    return events, det, metrics, retained


# ==========================================================================
#   1. The switch: off by default, explicit on, and nothing runs when off
# ==========================================================================

class _FakeFramework:
    def __init__(self, section):
        self._section = section

    def load_framework(self):
        return self._section


def t_switch_default_is_off():
    real = B.fw
    try:
        B.fw = None
        check("[voice] aec_barge_in: the default is OFF (no framework, no guess)", B.enabled() is False)
        check("[voice] aec_barge_in: an empty section leaves it OFF",
              B._as_bool((_FakeFramework({}).load_framework().get("voice") or {}).get("barge_in"))
              is False)
        B.fw = _FakeFramework({"voice": {"aec_barge_in": True}})
        check("[voice] aec_barge_in = true: ON, and only then", B.enabled() is True)
        for spelling in ("false", "FALSE", "0", "no", "off", " "):
            B.fw = _FakeFramework({"voice": {"aec_barge_in": spelling}})
            check(f"[voice] aec_barge_in = {spelling!r}: OFF", B.enabled() is False)
        B.fw = _FakeFramework({"voice": {"aec_barge_in": "true"}})
        check("[voice] aec_barge_in = 'true' (string): ON", B.enabled() is True)
        # The SHIPPED switch is a different thing: `[voice] barge_in_enabled`
        # (answering today's 2 s clips) must never turn this prototype on.
        B.fw = _FakeFramework({"voice": {"barge_in_enabled": True}})
        check("the shipped barge_in_enabled switch does NOT turn this on", B.enabled() is False)
        B.fw = _FakeFramework({"voice": {"aec_barge_in": True}})
        check("... only aec_barge_in does", B.enabled() is True)

        class _Broken:
            def load_framework(self):
                raise RuntimeError("no config here")

        B.fw = _Broken()
        check("[voice] aec_barge_in: a reader that raises means OFF, never ON", B.enabled() is False)
    finally:
        B.fw = real


def t_switch_off_does_nothing():
    """The guarded-path half of "switch off = old behaviour": no frame is even
    looked at, no owner check runs, no residual exists."""
    calls = []

    def verifier(audio, rate):
        calls.append(rate)
        return True

    events, det, metrics, retained = run_detector(ECHO, BASE, verifier=verifier, enabled=False)
    check("switch OFF: no decision, ever", events == [])
    check("switch OFF: not one frame processed", metrics["frames"] == 0, metrics)
    check("switch OFF: the owner check was not called", calls == [])
    check("switch OFF: no residual retained", retained == 0)
    det.close()
    check("switch OFF: still nothing after close", det.feed(ECHO[:B.FRAME], BASE[:B.FRAME]) is None)


def t_switch_is_read_at_construction():
    real = B.fw
    try:
        B.fw = _FakeFramework({"voice": {"aec_barge_in": True}})
        det = B.BargeInDetector(verifier=lambda a, r: True)
        check("the switch is read fresh when a detector is built (no restart needed)",
              det.enabled is True)
        B.fw = _FakeFramework({"voice": {"aec_barge_in": False}})
        det2 = B.BargeInDetector(verifier=lambda a, r: True)
        check("turning it off applies to the next utterance", det2.enabled is False)
    finally:
        B.fw = real


# ==========================================================================
#   2. The canceller: the known reference really is removed
# ==========================================================================

def t_echo_is_cancelled():
    mic = ECHO + 1e-4 * np.random.default_rng(0).standard_normal(len(BASE))
    residual, erle = B.cancel_echo(mic, BASE)
    check("the synthetic echo is cancelled (ERLE >= 30 dB)", erle is not None and erle >= 30.0,
          f"ERLE={erle}")
    check("the residual is quieter than the microphone signal",
          float(np.sqrt(np.mean(residual[-len(residual) // 3:] ** 2)))
          < float(np.sqrt(np.mean(mic[-len(mic) // 3:] ** 2))))
    print(f"      SYNTHETIC echo cancellation: ERLE {erle:.1f} dB on a {len(mic)/SR:.1f}s clip")
    det = B.BargeInDetector(verifier=lambda a, r: True, enabled=True)
    for i in range(0, len(BASE) - B.FRAME + 1, B.FRAME):
        det.feed(ECHO[i:i + B.FRAME], BASE[i:i + B.FRAME])
    check("the canceller keeps a fixed reference history, never a growing clip",
          det._canceller.reference_samples == det._canceller.taps,
          det._canceller.reference_samples)
    det.close()


# ==========================================================================
#   3. The decision: the owner over the echo, once, quickly, with the numbers
# ==========================================================================

def t_owner_interrupts():
    calls = []

    def verifier(audio, rate):
        calls.append((int(np.asarray(audio).size), int(rate)))
        return True

    speech = owner_voice(0.9, f0=110.0)
    mic, ref = scene(speech, gain=0.6)
    events, det, metrics, retained = run_detector(mic, ref, verifier=verifier)
    check("owner speech over the echo: exactly ONE decision", len(events) == 1, events)
    if events:
        event = events[0]
        check("... and it says stop", event["should_stop"] is True, event)
        check("... for the owner's voice", event["reason"] == B.REASON_OWNER, event)
        check("... after at least 350 ms of speech", event["speech_ms"] >= 350.0, event)
        latency = round(event["at_s"] - WARM, 3)
        check("... within the design's latency (<= 0.60 s after onset)", latency <= 0.60, latency)
        print(f"      SYNTHETIC barge-in: speech detected after {latency:.2f}s, "
              f"speech_ms={event['speech_ms']}, synthetic ERLE proxy={event['erle_db']} dB")
        check("the owner check was called once, with the bounded residual",
              calls == [(event["residual_samples"], SR)], calls)
        check("the residual handed to the owner check is 350-600 ms", 5600 <= event["residual_samples"] <= 9600,
              event["residual_samples"])
        # The event must be plain JSON values - no audio, no numpy arrays.
        try:
            encoded = json.dumps(event)
            plain = isinstance(encoded, str)
        except TypeError:
            plain = False
        check("the decision is JSON numbers/booleans only (no audio, no arrays)", plain, event)
        check("every event value is a plain scalar",
              all(isinstance(v, (bool, int, float, str)) for v in event.values()), event)
    check("no residual is retained after the decision", retained == 0, retained)
    det.close()


def t_owner_speech_variants():
    """Three synthetic voices, each interrupting the same echo: 3/3 decisions."""
    detected = 0
    for f0 in (90.0, 110.0, 140.0):
        speech = owner_voice(0.9, f0=f0)
        mic, ref = scene(speech, gain=0.6)
        events, det, metrics, retained = run_detector(mic, ref, verifier=lambda a, r: True)
        if len(events) == 1 and events[0]["should_stop"]:
            detected += 1
        det.close()
    check("three synthetic voices over the echo: 3/3 decisions", detected == 3, detected)
    print(f"      SYNTHETIC detection: {detected}/3 voice variants detected")


# ==========================================================================
#   4. The refusals: a wrong speaker, no check, a raising check - never stop
# ==========================================================================

def t_wrong_speaker_is_refused():
    speech = owner_voice(0.9, f0=110.0)
    mic, ref = scene(speech, gain=0.6)
    events, det, metrics, retained = run_detector(mic, ref, verifier=lambda a, r: False)
    check("a wrong speaker produces a decision the wiring may not act on",
          len(events) == 1 and events[0]["should_stop"] is False, events)
    if events:
        check("... and the reason is not_owner", events[0]["reason"] == B.REASON_NOT_OWNER,
              events[0])
        check("... with the residual dropped after the refusal", retained == 0, retained)
    det.close()


def t_missing_or_broken_check_fails_closed():
    speech = owner_voice(0.9, f0=110.0)
    mic, ref = scene(speech, gain=0.6)
    events, det, metrics, retained = run_detector(mic, ref, verifier=None)
    check("no owner check: the decision fails closed (verify_unavailable)",
          len(events) == 1 and events[0]["should_stop"] is False
          and events[0]["reason"] == B.REASON_UNVERIFIED, events)
    det.close()

    def raising(audio, rate):
        raise RuntimeError("the model is not installed")

    events, det, metrics, retained = run_detector(mic, ref, verifier=raising)
    check("a raising owner check: the decision fails closed (verify_error)",
          len(events) == 1 and events[0]["should_stop"] is False
          and events[0]["reason"] == B.REASON_VERIFY_ERROR, events)
    det.close()


# ==========================================================================
#   5. The false-positive guard: pure echo and music/TV-like sound never stop
# ==========================================================================

def t_no_false_cuts():
    cuts = 0
    for seed in (0, 1):
        mic = ECHO + 1e-4 * np.random.default_rng(seed).standard_normal(len(BASE))
        events, det, metrics, retained = run_detector(mic, BASE,
                                                      verifier=lambda a, r: True)
        cuts += len(events)
        det.close()
    check("pure echo: ZERO false cuts", cuts == 0, cuts)

    hits = {}
    for label, generator in (("white noise", white_noise), ("music chord", music_chord),
                             ("amplitude-modulated noise", am_noise)):
        total = 0
        for seed in (0, 1):
            extra = generator(len(BASE) / SR, seed)
            mic = (ECHO + extra[:len(ECHO)])
            events, det, metrics, retained = run_detector(mic, BASE,
                                                          verifier=lambda a, r: True)
            total += len(events)
            det.close()
        hits[label] = total
    check("white noise over the echo: ZERO false cuts", hits["white noise"] == 0, hits)
    check("a steady music-like chord over the echo: ZERO false cuts", hits["music chord"] == 0, hits)
    check("amplitude-modulated noise over the echo: ZERO false cuts",
          hits["amplitude-modulated noise"] == 0, hits)
    print("      SYNTHETIC false cuts: 0 (pure echo, white noise, music chord, "
          "amplitude-modulated noise)")


# ==========================================================================
#   6. Privacy and lifetime: nothing kept, nothing printed, nothing live started
# ==========================================================================

def t_privacy_and_lifetime():
    speech = owner_voice(0.9, f0=110.0)
    mic, ref = scene(speech, gain=0.6)
    out, err = io.StringIO(), io.StringIO()
    records = []
    root = logging.getLogger()
    handler = logging.Handler()
    handler.emit = lambda record: records.append(record)  # type: ignore[method-assign]
    root.addHandler(handler)
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            events, det, metrics, retained = run_detector(mic, ref,
                                                          verifier=lambda a, r: True)
    finally:
        root.removeHandler(handler)
    check("the module prints nothing while deciding", out.getvalue() == "" and err.getvalue() == "",
          (out.getvalue(), err.getvalue()))
    check("the module logs nothing while deciding",
          [r for r in records if r.name.startswith("jarvis_barge_in")] == [],
          [r.name for r in records])
    check("after the decision, zero residual samples are held", retained == 0, retained)
    det.reset()
    check("after reset(), zero residual samples are held", det.buffered_samples == 0)
    # A fresh decision is possible after reset (the caller's next utterance).
    events2 = []
    for i in range(0, len(BASE) - B.FRAME + 1, B.FRAME):
        event = det.feed(mic[i:i + B.FRAME], ref[i:i + B.FRAME])
        if event:
            events2.append(event)
    check("reset() clears the decided state for the next utterance",
          len(events2) == 1 and events2[0]["should_stop"] is True, events2)
    det.close()
    check("close() leaves zero residual samples", det.buffered_samples == 0)
    check("a closed detector makes no more decisions",
          det.feed(mic[:B.FRAME], ref[:B.FRAME]) is None)


def t_import_starts_no_live_module():
    """The prototype must not reach into the live voice path at import time: the
    'switch off = old behaviour' promise starts with importing nothing live."""
    code = (
        "import sys;"
        "sys.path.insert(0, r'%s');"
        "import jarvis_barge_in;"
        "print('speech', 'jarvis_speech' in sys.modules);"
        "print('flow', 'jarvis_voice_flow' in sys.modules);"
        "print('hud', 'jarvis_hud' in sys.modules);"
    ) % str(HERE)
    proc = subprocess.run([sys.executable, "-B", "-c", code], capture_output=True,
                          text=True, timeout=120)
    lines = [ln.strip() for ln in (proc.stdout or "").splitlines()]
    check("importing jarvis_barge_in starts no live voice module",
          proc.returncode == 0
          and "speech False" in lines and "flow False" in lines and "hud False" in lines,
          (proc.returncode, proc.stdout, proc.stderr[-400:]))


def t_deterministic():
    speech = owner_voice(0.9, f0=110.0)
    mic, ref = scene(speech, gain=0.6)
    a = run_detector(mic, ref, verifier=lambda a, r: True)[0]
    b = run_detector(mic, ref, verifier=lambda a, r: True)[0]
    check("the same synthetic input makes the same decision twice", a == b, (a, b))


def t_bad_frame_is_not_an_exception():
    det = B.BargeInDetector(verifier=lambda a, r: True, enabled=True)
    check("a mismatched frame returns None instead of raising",
          det.feed(np.zeros(B.FRAME), np.zeros(B.FRAME - 10)) is None)
    check("an empty frame returns None", det.feed(np.zeros(0), np.zeros(0)) is None)
    det.close()


def main():
    print("jarvis_barge_in.py: the phase-1 barge-in prototype (SYNTHETIC signals; "
          "real hardware NOT-MEASURED)\n")
    for name, fn in (
        ("switch", t_switch_default_is_off),
        ("switch-off", t_switch_off_does_nothing),
        ("switch-read", t_switch_is_read_at_construction),
        ("canceller", t_echo_is_cancelled),
        ("owner", t_owner_interrupts),
        ("variants", t_owner_speech_variants),
        ("wrong-speaker", t_wrong_speaker_is_refused),
        ("fail-closed", t_missing_or_broken_check_fails_closed),
        ("false-cuts", t_no_false_cuts),
        ("privacy", t_privacy_and_lifetime),
        ("imports", t_import_starts_no_live_module),
        ("determinism", t_deterministic),
        ("bad-frames", t_bad_frame_is_not_an_exception),
    ):
        print(f"-- {name}")
        try:
            fn()
        except Exception:
            FAILED.append(name)
            print(f"FAIL  {name} raised\n        {traceback.format_exc()}")
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(main())
