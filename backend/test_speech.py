"""jarvis_speech.py: the voice loop, tested end to end against the real
sherpa_onnx package (installed in this container) and the real jarvis_voice
owner gate (rebuilt in an earlier pass, also real here) - no mocks for either.

What CANNOT be tested here, and why: no speech-to-text model, Kokoro voice or
Silero VAD weight ships in this repository or this container (they are large
binary ONNX assets that belong on the owner's own machine, never in git), and
there is no real microphone or speaker attached to this sandbox. So this
suite proves three things instead, each with real code:

  1. A missing/corrupt model file makes sherpa_onnx raise RuntimeError -
     really, not by assumption - and jarvis_speech swallows it into an honest
     "not available" rather than a crash or a hang.
  2. hear() never reaches speech-to-text for a voice that fails the owner
     check - proven by making the STT path raise if it is ever called, then
     driving hear() with a clip that does not match any enrolled profile.
  3. WAV bytes in, WAV bytes out is exact: encode, decode, compare samples.

Run it beside the backend:

    python3 backend/test_speech.py
"""
import array
import io
import json
import math
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _where import BACKEND, REPO, explain, missing  # noqa: E402

REBUILT = Path(__file__).resolve().parent / "rebuilt"
sys.path.insert(0, str(REBUILT))

import jarvis_speech as S  # noqa: E402


def _tone_wav(freq=440.0, seconds=0.5, sample_rate=16000, amplitude=0.4) -> bytes:
    """A real mono 16-bit PCM WAV, synthesised, no fixture file needed."""
    n = int(seconds * sample_rate)
    samples = array.array("h", [
        int(amplitude * 32767.0 * math.sin(2 * math.pi * freq * i / sample_rate))
        for i in range(n)
    ])
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(samples.tobytes())
    return buf.getvalue()


class ReloadsBetweenTests(unittest.TestCase):
    """Every test gets a clean engine cache and a clean wake-state file, so
    one test's config override cannot leak into the next."""

    def setUp(self):
        S.reload_engines()
        self._tmp = tempfile.TemporaryDirectory()
        self._cfg_patch = mock.patch.object(S, "_config_dir",
                                             return_value=Path(self._tmp.name))
        self._cfg_patch.start()

    def tearDown(self):
        self._cfg_patch.stop()
        self._tmp.cleanup()
        S.reload_engines()

    def _with_cfg(self, overrides: dict):
        """Patches jarvis_speech._cfg so `key` in `overrides` wins, anything
        else falls through to the real reader (the shipped TOML default)."""
        real = S._cfg
        def fake(key, default=None):
            if key in overrides:
                return overrides[key]
            return real(key, default)
        return mock.patch.object(S, "_cfg", side_effect=fake)


class WavRoundTrip(ReloadsBetweenTests):
    """The one piece of this file with no external dependency at all."""

    def test_encode_decode_round_trips_within_quantisation_error(self):
        raw = _tone_wav(freq=220.0, seconds=0.2, sample_rate=16000)
        parsed = S._read_wav(raw)
        self.assertIsNotNone(parsed)
        samples, sr = parsed
        self.assertEqual(sr, 16000)
        self.assertGreater(len(samples), 0)

        rewritten = S._write_wav(samples, sr)
        reparsed = S._read_wav(rewritten)
        self.assertIsNotNone(reparsed)
        samples2, sr2 = reparsed
        self.assertEqual(sr2, sr)
        self.assertEqual(len(samples), len(samples2))
        # int16 quantisation, not exact float equality.
        worst = max(abs(a - b) for a, b in zip(samples[:200], samples2[:200]))
        self.assertLess(worst, 1.0 / 32767.0 * 2)

    def test_garbage_bytes_are_not_a_wav(self):
        self.assertIsNone(S._read_wav(b"not a wav file at all"))

    def test_stereo_is_downmixed_to_mono(self):
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(16000)
            frames = array.array("h", [1000, -1000] * 100)
            w.writeframes(frames.tobytes())
        samples, sr = S._read_wav(buf.getvalue())
        self.assertEqual(sr, 16000)
        # Left +1000, right -1000 -> mono average is silence.
        self.assertTrue(all(abs(x) < 1e-6 for x in samples))


class EngineConstructionIsHonest(ReloadsBetweenTests):
    """Real sherpa_onnx, real missing files, real RuntimeError - caught."""

    def test_stt_reports_unavailable_when_engine_is_not_sherpa(self):
        with self._with_cfg({"stt_engine": "faster-whisper"}):
            self.assertIsNone(S._stt_engine())

    def test_stt_reports_unavailable_when_model_files_do_not_exist(self):
        with self._with_cfg({
            "stt_engine": "sherpa-onnx",
            "sherpa_stt_model": "/nonexistent/model.onnx",
            "sherpa_stt_tokens": "/nonexistent/tokens.txt",
        }):
            # This is the real sherpa_onnx.OfflineRecognizer.from_sense_voice
            # call, against files that do not exist. It must not raise out
            # of this module, and it does not - confirmed separately by hand
            # against the bare API before this test was written.
            self.assertIsNone(S._stt_engine())

    def test_tts_reports_unavailable_when_model_files_do_not_exist(self):
        with self._with_cfg({
            "tts_engine": "sherpa-onnx",
            "tts_model": "/nonexistent/model.onnx",
            "tts_voices": "/nonexistent/voices.bin",
            "tts_tokens": "/nonexistent/tokens.txt",
            "tts_data_dir": "/nonexistent/espeak-ng-data",
        }):
            self.assertIsNone(S._tts_engine())

    def test_engine_construction_is_cached(self):
        calls = {"n": 0}
        real_build = S._build_stt_engine
        def counting():
            calls["n"] += 1
            return real_build()
        with mock.patch.object(S, "_build_stt_engine", side_effect=counting):
            S._stt_engine()
            S._stt_engine()
            S._stt_engine()
        self.assertEqual(calls["n"], 1, "the engine was rebuilt on every call")

    def test_reload_engines_drops_the_cache(self):
        calls = {"n": 0}
        real_build = S._build_stt_engine
        def counting():
            calls["n"] += 1
            return real_build()
        with mock.patch.object(S, "_build_stt_engine", side_effect=counting):
            S._stt_engine()
            S.reload_engines()
            S._stt_engine()
        self.assertEqual(calls["n"], 2)


class HearNeverTranscribesAStranger(ReloadsBetweenTests):
    """The one invariant the whole module exists to protect."""

    def test_a_voice_with_no_enrolled_profile_is_refused(self):
        heard = S.hear(_tone_wav(440.0), source="push_to_talk")
        self.assertFalse(heard.is_owner)
        self.assertEqual(heard.text, "")
        self.assertIn("no enrolled voice profile", heard.reason)

    def test_garbage_input_is_refused_without_touching_the_voice_gate(self):
        heard = S.hear(b"not audio", source="push_to_talk")
        self.assertFalse(heard.is_owner)
        self.assertFalse(heard.available)
        self.assertIn("could not read", heard.reason)

    def test_stt_is_never_called_for_a_voice_that_fails_the_gate(self):
        # If hear() ever reached transcription before the gate passed, this
        # would raise and fail the test - which is the point.
        with mock.patch.object(S, "_transcribe",
                                side_effect=AssertionError("STT ran on a stranger")):
            heard = S.hear(_tone_wav(440.0), source="push_to_talk")
        self.assertFalse(heard.is_owner)

    def test_an_enrolled_voice_passes_the_gate_and_is_reported_owner(self):
        import jarvis_voice as V
        clip = _tone_wav(440.0, seconds=1.0)
        samples, _sr = S._read_wav(clip)
        profile_path = Path(self._tmp.name) / "owner.json"
        V.enroll([samples, samples, samples], embedder=V.Embedder(), path=profile_path)
        with mock.patch.object(V, "PROFILE_PATH", profile_path):
            heard = S.hear(clip, source="push_to_talk")
        self.assertTrue(heard.is_owner, heard.reason)
        # No STT model is installed anywhere in this container, so the
        # honest answer is "recognised, but cannot transcribe yet" -
        # exactly what a real install with no model files downloaded yet
        # would also see.
        self.assertFalse(heard.available)
        self.assertIn("no speech-to-text model", heard.reason)

    def test_a_different_voice_than_the_enrolled_one_is_refused(self):
        import jarvis_voice as V
        enroll_clip = _tone_wav(220.0, seconds=1.0)
        stranger_clip = _tone_wav(880.0, seconds=1.0)
        enroll_samples, _ = S._read_wav(enroll_clip)
        profile_path = Path(self._tmp.name) / "owner.json"
        V.enroll([enroll_samples] * 3, embedder=V.Embedder(), path=profile_path)
        with mock.patch.object(V, "PROFILE_PATH", profile_path):
            heard = S.hear(stranger_clip, source="push_to_talk")
        self.assertFalse(heard.is_owner)
        self.assertEqual(heard.text, "")


class Say(ReloadsBetweenTests):
    def test_empty_text_returns_nothing_to_speak(self):
        self.assertIsNone(S.say(""))
        self.assertIsNone(S.say("   "))

    def test_no_engine_installed_returns_none_not_an_exception(self):
        # Default config: tts_engine is sherpa-onnx but no model files exist
        # anywhere in this container.
        self.assertIsNone(S.say("hello there"))


class WakeToggle(ReloadsBetweenTests):
    """Since 2026-09-23 turning the wake word ON raises an approval card and
    changes nothing itself; OFF is immediate. The card flows (denied, timed
    out, wrong tier, withdrawn, ...) are in test_wakeword.py."""

    def setUp(self):
        super().setUp()
        S._reset_wake_for_tests()

    def tearDown(self):
        S._reset_wake_for_tests()
        super().tearDown()

    @staticmethod
    def _approve(action, detail, prompt):
        return type("V", (), {"allowed": True, "tier": "ask",
                              "outcome": "approved", "request_id": "t"})()

    def test_defaults_to_the_config_value(self):
        with self._with_cfg({"wake_word_enabled": False}):
            self.assertFalse(S._wake_enabled())

    def test_on_needs_the_card_and_off_is_at_once(self):
        r = S.set_wake_enabled(True, gate=self._approve, tier_of=lambda a: "ask",
                               spawn=lambda fn: fn())
        self.assertTrue(r["ok"])
        self.assertTrue(r["pending"], "ON must be reported as a card raised, not as done")
        self.assertTrue(S._wake_enabled(), "the approved card did not turn it on")
        self.assertTrue(S.status()["wake_word_enabled"])

        r = S.set_wake_enabled(False)
        self.assertTrue(r["ok"])
        self.assertFalse(r["pending"])
        self.assertFalse(S._wake_enabled())

    def test_on_without_an_answer_changes_nothing(self):
        r = S.set_wake_enabled(True, gate=self._approve, tier_of=lambda a: "ask",
                               spawn=lambda fn: None)      # the card is never answered
        self.assertTrue(r["pending"])
        self.assertFalse(S._wake_enabled())
        self.assertTrue(S.status()["listening"]["wake_word_pending"])

    def test_a_write_failure_is_reported_rather_than_raised(self):
        # Put a FILE where the state directory needs to be a directory, so
        # mkdir(parents=True) fails with a real OSError.
        blocker = Path(self._tmp.name) / "voice"
        blocker.write_text("not a directory")
        r = S.set_wake_enabled(False)
        self.assertFalse(r["ok"])
        self.assertIn("error", r)
        # And an approved card that cannot write says "failed", not "enabled".
        S.set_wake_enabled(True, gate=self._approve, tier_of=lambda a: "ask",
                           spawn=lambda fn: fn())
        self.assertEqual(S.wake_state()["last"]["outcome"], "failed")
        self.assertFalse(S._wake_enabled())


class StatusNeverOverstates(ReloadsBetweenTests):
    def test_a_toml_still_naming_faster_whisper_is_told_which_line_to_change(self):
        # The shipped TOML said this until 2026-09-23, and the owner's copy
        # may still. No code in Jarvis speaks faster-whisper.
        with self._with_cfg({"stt_engine": "faster-whisper"}):
            out = S.status()
        self.assertEqual(out["stt_engine"], "faster-whisper")
        self.assertFalse(out["stt_available"])
        self.assertIn('stt_engine = "sherpa-onnx"', out["note"])

    def test_the_default_engine_is_the_one_the_code_speaks(self):
        with self._with_cfg({"stt_engine": None}):
            self.assertEqual(S._stt_engine_name(), "sherpa-onnx")
        shipped = (REBUILT / "jarvis-framework.toml").read_text(encoding="utf-8")
        self.assertIn('stt_engine = "sherpa-onnx"', shipped)
        self.assertNotIn('stt_engine = "faster-whisper"', shipped)

    def test_the_model_kind_is_recognised_from_the_files(self):
        d = Path(self._tmp.name) / "voice-models" / "stt"
        d.mkdir(parents=True)
        (d / "tokens.txt").write_text("a 0\n")
        with self._with_cfg({"sherpa_stt_kind": None}):
            self.assertEqual(S._stt_files()[0], "sense_voice")
            for n in ("encoder.int8.onnx", "decoder.int8.onnx", "joiner.int8.onnx"):
                (d / n).write_bytes(b"x")
            kind, files = S._stt_files()
        self.assertEqual(kind, "nemo_transducer")
        self.assertTrue(files["encoder"].endswith("encoder.int8.onnx"))
        with self._with_cfg({"sherpa_stt_kind": "sense_voice"}):
            self.assertEqual(S._stt_files()[0], "sense_voice")

    def test_reports_sherpa_selected_but_files_missing(self):
        with self._with_cfg({"stt_engine": "sherpa-onnx"}):
            out = S.status()
        self.assertFalse(out["stt_available"])
        self.assertIn("not on disk yet", out["note"])

    def test_local_client_side_stt_is_never_reported_allowed(self):
        # The route's own comment: a client that transcribed locally would
        # send text and the owner-voice gate would have nothing left to
        # check. This field must never flip to True from here.
        self.assertFalse(S.status()["local_stt_on_client_allowed"])

    def test_status_does_not_construct_the_engine_just_to_report_on_it(self):
        # A status poll happens often (a settings page, a health check) and
        # must not pay the cost of loading a real model just to say whether
        # one is configured.
        with mock.patch.object(S, "_build_stt_engine",
                                side_effect=AssertionError("engine built on status()")):
            with mock.patch.object(S, "_build_tts_engine",
                                    side_effect=AssertionError("engine built on status()")):
                S.status()


if __name__ == "__main__":
    unittest.main(verbosity=2)
