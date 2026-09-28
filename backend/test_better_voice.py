""""Better voice" (the owner's group of 2026-09-28; JARVIS-API.md section 80).

    python3 test_better_voice.py

No pytest, no network, no microphone. The same stand-ins as
test_voice_strict.py; the settings, the card, hear() and the bake-off's
verdicts are the REAL jarvis_voice / jarvis_voice_enroll / jarvis_speech /
jarvis_microwake / jarvis_bakeoff code, writing into temporary folders.

What it proves:
  1. Both new settings start where nothing changes: one "hey Jarvis"
     detector, the measured stronger voice-ID model. A damaged settings file
     reads as the strict value of each.
  2. "Both detectors" is at once (it only narrows), and cannot be chosen
     while microWakeWord is not installed (refused before any card, in
     words). Going back to one detector is ONE card.
  3. The newer voice-ID model is ONE card, cannot be chosen while its file
     is missing or is not the pinned file (checked by SHA-256), and falls
     back to the measured model - never the small one - if its file goes.
  4. hear(): with "both", the second detector runs AFTER the first said yes
     and BEFORE the voice check; it can only refuse. With "one" it never
     runs. Not installed: the first decides alone, and status() says so.
  5. The two detectors must agree within a second.
  6. jarvis_microwake: package missing, wrong model file, and the scores
     walk (with a stand-in package).
  7. The speech detector choice: v4 by default; v6 only when chosen AND the
     pinned file; a missing or wrong file falls back to v4 with a reason.
  8. Training puts the other installed stronger model into the print too.
  9. The bake-off's three new verdicts, by their fixed rules.
 10. With JARVIS_TEST_VOICE_MODELS (and pymicro-wakeword installed), the
     real files: both VAD files load, and the real second detector hears a
     Kokoro "hey Jarvis" and not a sentence without it.
"""
import hashlib
import json
import os
import sys
import tempfile
import traceback
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "rebuilt"))
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402

import test_voice_strict as T  # noqa: E402  (its helpers; its own suite runs only as __main__)
from test_voice_strict import (V, E, S, Gate, HeldGate, OWNER, STRANGER, Table,  # noqa: E402
                               Temp, Verdict, _clip, check, skip)
import jarvis_microwake as M  # noqa: E402
import jarvis_wakeword as W  # noqa: E402
import jarvis_bakeoff as B  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="jarvis-better-voice-"))


def _stage(mode, value, verdict=None, tier="ask", gate=None, spawn=T.run_sync):
    gate = gate or Gate(verdict or Verdict(True, outcome="approved"))
    code, out = E.stage(json.dumps({"mode": mode, "value": value}).encode(),
                        gate=gate, tier_of=lambda a: tier, spawn=spawn)
    return code, out, gate


MW_OK = {"available": True, "why": "", "version": "2.5.0"}
MW_MISSING = {"available": False, "why": "the pymicro-wakeword package is not installed"}


class Speaker:
    """A folder with model.onnx / strong.onnx / resnet221.onnx stand-ins."""

    def __enter__(self):
        self.dir = Path(tempfile.mkdtemp(prefix="spk-", dir=TMP))
        self.p = mock.patch.object(V, "speaker_model_path", lambda: self.dir / "model.onnx")
        self.p.start()
        (self.dir / "strong.onnx").write_bytes(b"titanet stand-in")
        return self

    def resnet(self, good=True):
        body = b"resnet stand-in" if good else b"something else"
        (self.dir / "resnet221.onnx").write_bytes(body)
        return mock.patch.object(V, "RESNET_SHA256",
                                 hashlib.sha256(b"resnet stand-in").hexdigest())

    def __exit__(self, *a):
        self.p.stop()


# ----------------------------------------------------------- 1. defaults --

def t_defaults():
    with Temp():
        s = V.settings()
        check("one detector and the measured model by default",
              s["wake_confirm"] == "one" and s["voice_id_model"] == "titanet", s)
        V.settings_path().write_text("{not json", encoding="utf-8")
        s = V.settings()
        check("an unreadable file: both detectors (the strict value), the measured model",
              s["wake_confirm"] == "both" and s["voice_id_model"] == "titanet", s)
        V.settings_path().write_text(json.dumps({"wake_confirm": "maybe",
                                                 "voice_id_model": "other"}))
        s = V.settings()
        check("unknown values: the strict value of each",
              s["wake_confirm"] == "both" and s["voice_id_model"] == "titanet", s)
        V.settings_path().write_text(json.dumps({"strictness": "balanced"}))
        check("a file from before these settings: today's behaviour",
              V.settings()["wake_confirm"] == "one")
        check("the looser values are the card ones",
              V.LOOSER["wake_confirm"] == "one" and V.LOOSER["voice_id_model"] == "resnet221")


# ------------------------------------------------- 2. both detectors ----

def t_wake_confirm_setting():
    with Temp():
        with mock.patch.object(V, "_microwake_status", return_value=MW_MISSING):
            code, out, gate = _stage("wake_confirm", "both")
            check("not installed: refused before any card, in words",
                  code == 409 and not gate.calls and "not installed" in out["error"]
                  and V.settings()["wake_confirm"] == "one", (code, out))
            try:
                V.set_setting("wake_confirm", "both")
                check("set_setting refuses it too", False)
            except ValueError as exc:
                check("set_setting refuses it too", "microWakeWord" in str(exc), str(exc))
        with mock.patch.object(V, "_microwake_status", return_value=MW_OK):
            code, out, gate = _stage("wake_confirm", "both")
            check("installed: both detectors at once, no card",
                  code == 200 and not gate.calls and out["changed"] is True
                  and V.settings()["wake_confirm"] == "both"
                  and out["settings"]["wake_confirm"] == "both", (code, out))
            E._reset_for_tests()
            code, out, gate = _stage("wake_confirm", "one", Verdict(False, outcome="denied"))
            check("back to one: ONE card; denied - still both",
                  code == 202 and len(gate.calls) == 1
                  and gate.calls[0][0] == "change_own_config"
                  and V.settings()["wake_confirm"] == "both", (code, out))
            E._reset_for_tests()
            code, out, gate = _stage("wake_confirm", "one")
            _a, detail, prompt = gate.calls[0]
            check("approved: one detector again",
                  V.settings()["wake_confirm"] == "one"
                  and E.state()["last"]["outcome"] == "setting_changed", E.state().get("last"))
            check("the card says what it is, plainly",
                  detail["what"] == "go back to one \"hey Jarvis\" detector"
                  and "Your voice is still checked" in prompt and "If you say no" in prompt,
                  detail)
            # Withdrawn: back to both while the card to go to one waits.
            V.set_setting("wake_confirm", "both")
            held = HeldGate(Verdict(True, outcome="approved"))
            threads = []

            def spawn(fn):
                th = T.threading.Thread(target=fn)
                threads.append(th)
                th.start()
            E._reset_for_tests()
            code, _o, _g = _stage("wake_confirm", "one", gate=held, spawn=spawn)
            held.asked.wait(5)
            code2, _o2, gate2 = _stage("wake_confirm", "both")
            held.release.set()
            for th in threads:
                th.join(5)
            check("choosing both again while the card waits: approving it changes nothing",
                  code == 202 and code2 == 200 and not gate2.calls
                  and V.settings()["wake_confirm"] == "both"
                  and E.state()["last"]["outcome"] == "withdrawn", E.state().get("last"))
        check("the other voice settings are untouched",
              V.settings()["strictness"] == "very_strict"
              and V.settings()["hands_free"] == "same_as_button")


# ------------------------------------------------ 3. the newer model -----

def t_voice_id_model_setting():
    with Temp(), Speaker() as sp:
        code, out, gate = _stage("voice_id_model", "resnet221")
        check("not installed: refused before any card, saying where it looked",
              code == 409 and not gate.calls and "not installed" in out["error"]
              and "resnet221.onnx" in out["error"], (code, out))
        with sp.resnet(good=False):
            code, out, gate = _stage("voice_id_model", "resnet221")
            check("a file that is not the pinned one (SHA-256): refused, never used",
                  code == 409 and not gate.calls and "not the expected file" in out["error"]
                  and V.strong_model_path().name == "strong.onnx", (code, out))
        with sp.resnet(good=True):
            E._reset_for_tests()
            code, out, gate = _stage("voice_id_model", "resnet221")
            check("the pinned file but NOT measured: refused before any card, saying why",
                  code == 409 and not gate.calls and "not measured" in out["error"]
                  and "step 7" in out["error"]
                  and V.settings()["voice_id_model"] == "titanet", (code, out))
        # Measured: its own MODEL_BARS row exists (as TitaNet's was added),
        # keyed by the stand-in file's hash, which sp.resnet() pins.
        with sp.resnet(good=True):
            measured = dict(V.MODEL_BARS)
            measured[V.RESNET_SHA256[:12]] = {"label": "the newer voice-ID model",
                                              "balanced": (0.40, 2.0),
                                              "very_strict": (0.50, 3.0),
                                              "paired": (0.50, 3.0)}
        with sp.resnet(good=True), mock.patch.object(V, "MODEL_BARS", measured):
            E._reset_for_tests()
            code, out, gate = _stage("voice_id_model", "resnet221",
                                     Verdict(False, outcome="timed_out"))
            check("the pinned file: ONE card; timed out - the measured model stays",
                  code == 202 and len(gate.calls) == 1
                  and V.settings()["voice_id_model"] == "titanet"
                  and V.strong_model_path().name == "strong.onnx", (code, out))
            E._reset_for_tests()
            code, out, gate = _stage("voice_id_model", "resnet221")
            _a, detail, prompt = gate.calls[0]
            check("approved: the newer model is the stronger one in use",
                  V.settings()["voice_id_model"] == "resnet221"
                  and V.strong_model_path().name == "resnet221.onnx", V.strong_model_path())
            check("the card says it is unmeasured, and that no voice check can tell a "
                  "recording from you",
                  "NOT been measured" in prompt and "recording or a copy" in prompt
                  and detail["what"] == "use the newer, unmeasured voice-ID model", prompt)
            check("the other installed model is trained into prints too",
                  [p.name for p in V.other_strong_paths()] == ["strong.onnx"])
        # The file goes away while it is chosen: the MEASURED model, not the small one.
        (sp.dir / "resnet221.onnx").unlink()
        check("chosen but gone: the measured stronger model is used, not the small one",
              V.strong_model_path().name == "strong.onnx")
        with mock.patch.object(V, "strong_embedder", lambda *a: None), \
                mock.patch.object(V, "EcapaEmbedder", side_effect=RuntimeError):
            st = V.status()
        check("...and status() says so, with where it looked",
              "you chose the newer voice-ID model" in st["note"]
              and "resnet221.onnx" in st["note"], st["note"])
        check("status carries the choice", st["voice_id_model"] == "resnet221"
              and st["settings"]["choices"]["voice_id_model"] == ["titanet", "resnet221"]
              and st["models"]["choice"]["chosen"] == "resnet221"
              and st["models"]["choice"]["resnet221"]["installed"] is False, st["models"])
        code, out, gate = _stage("voice_id_model", "titanet")
        check("back to the measured model: at once, no card",
              code == 200 and not gate.calls and V.settings()["voice_id_model"] == "titanet",
              (code, out))
        with mock.patch.object(V, "_cfg", lambda k, d=None: "C:/my.onnx"
                               if k == "speaker_model_strong" else d):
            check("speaker_model_strong in the settings file wins, and the choice says so",
                  "speaker_model_strong" in V.setting_blocker("voice_id_model", "resnet221")
                  and str(V.strong_model_path()).endswith("my.onnx"))


# ------------------------------------------- 4. hear() and the AND gate --

def _wake_setup():
    small = Table("sherpa-onnx:357a834f702b", {"loud": OWNER, "quiet": STRANGER})
    V.enroll(["a", "b", "c"], embedder=Table(small.name, {"a": OWNER, "b": OWNER,
                                                           "c": OWNER}))
    return small


def _hear_wake(first_heard=True, confirm=None, confirm_boom=False):
    """hear() on a wake-word clip with a fake first detector (heard at 1.0 s)
    and a fake second one. Returns (Heard, calls to the second detector,
    whether the voice check ran)."""
    small = _wake_setup()
    calls, verified = [], []
    real_verify = V.verify

    def fake_confirm(samples, rate, first_at):
        calls.append(first_at)
        if confirm_boom:
            raise AssertionError("the second detector ran")
        return confirm, M.MicroSpot(True, heard=confirm == "agreed")

    def watch_verify(*a, **kw):
        verified.append(1)
        return real_verify(*a, **kw)
    spot = W.Spot(True, heard=first_heard, score=0.9 if first_heard else 0.1, at=1.0)
    with mock.patch.object(V, "EcapaEmbedder", lambda: small), \
            mock.patch.object(V, "strong_embedder", lambda *a: None), \
            mock.patch.object(S, "_speech_span", return_value="skip"), \
            mock.patch.object(S, "_wake_enabled", return_value=True), \
            mock.patch.object(S, "_take_awake", return_value=False), \
            mock.patch.object(S, "_question_open", return_value=False), \
            mock.patch.object(W, "spot", lambda *a, **k: spot), \
            mock.patch.object(W, "spot_stop", lambda *a, **k: W.Spot(True, heard=False)), \
            mock.patch.object(M, "confirm", fake_confirm), \
            mock.patch.object(V, "verify", watch_verify), \
            mock.patch.object(S, "_stt_engine", return_value=object()), \
            mock.patch.object(S, "_note_for_history", lambda *a, **k: None), \
            mock.patch.object(S, "_flow", lambda *a, **k: None), \
            mock.patch.object(S, "_transcribe", return_value="hey Jarvis what time is it"):
        h = S.hear(_clip("owner", 2.5), source="wake_word", mic="desktop")
    return h, calls, bool(verified)


def t_hear_and_gate():
    with Temp():
        h, calls, verified = _hear_wake(confirm_boom=True)
        check("setting 'one': the second detector never runs, the wake goes on as before",
              not calls and verified and h.is_owner and h.text == "what time is it", h)
        with mock.patch.object(V, "_microwake_status", return_value=MW_OK):
            V.set_setting("wake_confirm", "both")
        h, calls, verified = _hear_wake(confirm="disagreed")
        check("'both', the second did not hear it: refused BEFORE the voice check, no words",
              calls == [1.0] and not verified and not h.is_owner and h.text == ""
              and "second \"hey Jarvis\" detector did not hear it" in h.reason, h)
        h, calls, verified = _hear_wake(confirm="agreed")
        check("'both', both heard it: on to the voice check and the words, as before",
              calls == [1.0] and verified and h.is_owner and h.text == "what time is it", h)
        h, calls, verified = _hear_wake(first_heard=False, confirm_boom=True)
        check("the first did not hear it: refused, and the second is never asked "
              "(it can only say no, never make a wake)",
              not calls and not verified and not h.is_owner
              and "no \"hey Jarvis\"" in h.reason, h)
        h, calls, verified = _hear_wake(confirm="unavailable")
        check("'both' but the second cannot run: the first decides alone, as before",
              calls == [1.0] and verified and h.is_owner, h)
        with mock.patch.object(S, "jarvis_microwake", None):
            st = S._wake_confirm_state()
            check("...and the status says so, plainly",
                  st["setting"] == "both" and st["active"] is False
                  and "first one decides alone" in st["note"], st)
            check("with no module at all, the gate is 'unavailable', never an error",
                  S._wake_confirm(np.zeros(16000, np.float32), 16000, 0.5) == "unavailable")
        with mock.patch.object(S, "jarvis_voice", None):
            check("a voice module older than the setting: never both",
                  S._wake_confirm_wanted() is False)


def t_agreement_window():
    s = M.MicroSpot(True, heard=True, times=[2.0, 2.01, 2.02])
    check("within a second: agreed", M.agree(1.2, s) and M.agree(2.9, s))
    check("more than a second apart: not the same \"hey Jarvis\"",
          not M.agree(0.9, s) and not M.agree(3.1, s))
    check("the second did not hear it, or did not run: never agreed",
          not M.agree(2.0, M.MicroSpot(True, heard=False))
          and not M.agree(2.0, M.MicroSpot(False, why="x")))


# ---------------------------------------------------- 6. jarvis_microwake --

class FakeFeatures:
    def process_streaming(self, audio_bytes):
        for i in range(0, len(audio_bytes) - 319, 320):
            yield np.full((1, 1, 40), 1.0 if audio_bytes[i:i + 320] != bytes(320) else 0.0)


class FakeModel:
    """Scores 0.99 on sound, 0 on silence."""

    def reset(self):
        pass

    def process_streaming_prob(self, f):
        return 0.99 if float(np.max(f)) > 0 else 0.0


def t_microwake_module():
    with mock.patch.object(M, "_package", side_effect=ImportError("no")):
        st = M.status()
        check("package missing: not available, and it says how to install",
              st["available"] is False and "not installed" in st["why"]
              and "Better voice" in st["why"], st)
        M.reload()
        sp = M.spot(np.zeros(16000, np.float32), 16000)
        check("package missing: spot() did not run, with the reason", not sp.ran and sp.why, sp)
        v, _s = M.confirm(np.zeros(16000, np.float32), 16000, 0.5)
        check("package missing: confirm() is 'unavailable'", v == "unavailable")
    fake_dir = TMP / "pkg" / "pymicro_wakeword"
    (fake_dir / "models").mkdir(parents=True, exist_ok=True)
    (fake_dir / "__init__.py").write_text("")
    (fake_dir / "models" / M.MODEL_FILE).write_bytes(b"not the model")
    fake = mock.Mock(__file__=str(fake_dir / "__init__.py"))
    with mock.patch.object(M, "_package", return_value=fake):
        M.reload()
        st = M.status()
        check("a model file that is not the pinned one: never used, and it says why",
              st["available"] is False and "not the one this was measured with" in st["why"],
              st)
    fake.MicroWakeWordFeatures = FakeFeatures
    x = np.concatenate([np.zeros(16000, np.float32),
                        np.full(8000, 0.3, np.float32), np.zeros(8000, np.float32)])
    with mock.patch.object(M, "_package", return_value=fake):
        sc = M.scores(FakeModel(), x, 16000)
    over = [t for t, p in sc if p > M.CUTOFF]
    check("scores: one per 10 ms step, timed from the clip's own start",
          over and abs(over[0] - 1.0) < 0.02 and abs(over[-1] - 1.5) < 0.02, over[:3])
    M.reload()


# ------------------------------------------------ 7. the speech detector --

def t_vad_choice():
    d = TMP / "vadcfg"
    (d / "voice-models" / "vad").mkdir(parents=True, exist_ok=True)
    v6 = d / "voice-models" / "vad" / "silero_vad_v6.onnx"
    cfg = {}
    with mock.patch.object(S, "_models_dir", lambda: d / "voice-models"), \
            mock.patch.object(S, "_cfg", lambda k, default=None: cfg.get(k, default)):
        c = S.vad_choice()
        check("v4 by default, the file the install line has always downloaded",
              c["in_use"] == "v4" and c["path"].endswith("silero_vad.onnx") and not c["note"], c)
        cfg["vad_version"] = "v6"
        c = S.vad_choice()
        check("v6 chosen but not installed: v4, with the reason",
              c["in_use"] == "v4" and "not installed" in c["note"], c)
        v6.write_bytes(b"not silero v6")
        c = S.vad_choice()
        check("v6 chosen, but not the pinned file (SHA-256): v4, never handed to sherpa-onnx",
              c["in_use"] == "v4" and "not the expected file" in c["note"]
              and S._vad_path().endswith("silero_vad.onnx"), c)
        with mock.patch.dict(S.VAD_FILES["v6"], sha256=hashlib.sha256(b"not silero v6")
                             .hexdigest()):
            c = S.vad_choice()
            check("v6 chosen and the pinned file: v6", c["in_use"] == "v6"
                  and c["path"].endswith("silero_vad_v6.onnx") and not c["note"], c)
        cfg["vad_version"] = "v9"
        c = S.vad_choice()
        check("an unknown version: v4, and it says so", c["in_use"] == "v4"
              and "not one Jarvis knows" in c["note"], c)
        cfg["vad_model"] = "C:/my/vad.onnx"
        c = S.vad_choice()
        check("an explicit vad_model path still wins, as it always has",
              c["in_use"] == "configured" and c["path"] == "C:/my/vad.onnx", c)
        st = S.status()["vad"]
        check("status says which file is used, and why", st["version"] == "configured"
              and "chosen" in st and "note" in st, st)
    check("the pinned hashes are the measured ones",
          S.VAD_FILES["v4"]["sha256"].startswith("9e2449e1")
          and S.VAD_FILES["v6"]["sha256"].startswith("1a153a22"))


# ---------------------------------- 8. training puts both models in ------

def t_enroll_extra_models():
    with Temp():
        small = Table("sherpa-onnx:357a834f702b", {"a": OWNER, "b": OWNER, "c": OWNER})
        strong = Table("sherpa-onnx:d51abcf31717", {"a": OWNER, "b": OWNER, "c": OWNER})
        other = Table("sherpa-onnx:182f4ae144d7", {"a": OWNER, "b": OWNER, "c": OWNER})
        prof = V.enroll(["a", "b", "c"], embedder=small, strong=strong, extra=[other])
        check("the print has sub-prints from all three models",
              all(prof.subprints(n) for n in (small.name, strong.name, other.name)),
              list(prof.models))
        prof = V.enroll(["a", "b", "c"], embedder=small, strong=strong, extra=[strong, small])
        check("a model given twice is trained once", len(prof.models) == 2, list(prof.models))


def t_newer_model_never_falls_back_to_the_small_one():
    with Temp():
        small = Table("sherpa-onnx:357a834f702b", {"a": OWNER, "b": OWNER, "c": OWNER,
                                                    "x": OWNER, "s": STRANGER})
        titanet = Table("sherpa-onnx:d51abcf31717", {"a": OWNER, "b": OWNER, "c": OWNER,
                                                      "x": OWNER, "s": STRANGER})
        resnet = Table("sherpa-onnx:" + V.RESNET_SHA256[:12], {"x": OWNER, "s": STRANGER})
        prof = V.enroll(["a", "b", "c"], embedder=small, strong=titanet)
        check("a print from before the newer model has no sub-print for it",
              not prof.subprints(resnet.name))
        check("balanced with TitaNet missing from the print: the old fallback, unchanged",
              V.plan(V.BALANCED, small, Table("sherpa-onnx:d51abcf31717", {}),
                     V.VoiceProfile(embedder=small.name, centroid=OWNER, threshold=0.35,
                                    samples=3)) [0][0].name == small.name)
        plan = V.plan(V.BALANCED, small, resnet, prof)
        check("balanced with the newer model chosen: it is asked, never the small one",
              [m.name for m, _r in plan] == [resnet.name], plan)
        V.set_setting("strictness", "balanced", approved=True)
        v = V.verify("x", small, strong=resnet)
        check("...so an old print is refused with 'train your voice again', not let in "
              "by the weak small model", not v.is_owner and "train your voice again" in v.reason
              and "newer voice-ID model" in v.reason, v.reason)


# --------------------------------------------------- 9. the bake-off -----

def t_bakeoff_verdicts():
    good = {"second_ok": True, "owner": {"clips": 12, "first": 12, "second": 11, "both": 11},
            "room": {"minutes": 60.0, "first_wakes": 4, "both_wakes": 1},
            "kokoro": {"hey": 44, "other": 66, "first_other": 7, "both_other": 1}}
    v, why = B.wake2_verdict(good)
    check("two detectors: every rule met -> turn on", v == B.TURN_ON, why)
    bad = json.loads(json.dumps(good))
    bad["owner"]["both"] = 9
    check("two detectors: more than 1 in 10 more of the owner's missed -> keep one",
          B.wake2_verdict(bad)[0] == B.KEEP_ONE)
    bad = json.loads(json.dumps(good))
    bad["room"]["both_wakes"] = 3
    check("two detectors: not a clear win in the room -> keep one",
          B.wake2_verdict(bad)[0] == B.KEEP_ONE)
    bad = json.loads(json.dumps(good))
    bad["room"]["first_wakes"] = 0
    bad["room"]["both_wakes"] = 0
    check("two detectors: today's never woke by mistake -> nothing to win, keep one",
          B.wake2_verdict(bad)[0] == B.KEEP_ONE)
    check("two detectors: not installed -> keep one, saying why",
          B.wake2_verdict({"second_ok": False, "second_why": "x"})[0] == B.KEEP_ONE)

    vad = {"v6_ok": True, "owner": {"clips": 12, "v4_found": 12, "v6_found": 12,
                                    "checked": True, "v4_passed": 10, "v6_passed": 10},
           "kokoro": {"clips": 110, "v4_found": 110, "v6_found": 110, "v4_cut": 0, "v6_cut": 0},
           "noisy": {"clips": 330, "v4_found": 324, "v6_found": 329},
           "noise": {"clips": 7, "v4_found": 0, "v6_found": 0}}
    check("speech detector: no worse anywhere -> use v6", B.vad_verdict(vad)[0] == B.USE_V6,
          B.vad_verdict(vad))
    for path, value in ((("noise", "v6_found"), 1), (("owner", "v6_passed"), 9),
                        (("kokoro", "v6_cut"), 1), (("owner", "v6_found"), 11),
                        (("owner", "clips"), 9)):
        worse = json.loads(json.dumps(vad))
        worse[path[0]][path[1]] = value
        check(f"speech detector: worse on {path} -> keep v4", B.vad_verdict(worse)[0] == B.KEEP_V4)
    check("speech detector: v6 not installed -> keep v4",
          B.vad_verdict({"v6_ok": False})[0] == B.KEEP_V4)

    check("voice-ID: enough of both -> ready for its bars",
          B.voiceid_verdict({"resnet_ok": True, "owner_clips": 20, "other_clips": 50})[0]
          == B.ROWS_READY)
    check("voice-ID: built-in voices alone are never enough",
          B.voiceid_verdict({"resnet_ok": True, "owner_clips": 30, "other_clips": 0,
                             "synthetic_clips": 110})[0] == B.ROWS_NOT_READY)
    rows = B.sweep([0.8, 0.7, 0.6, 0.5], [0.1, 0.2, 0.55, 0.3], bars=[0.3, 0.5, 0.6])
    check("the sweep: refused and let-in shares per bar",
          rows == [(0.3, 0.0, 0.5), (0.5, 0.0, 0.25), (0.6, 0.25, 0.0)], rows)
    check("the matching bar: the lowest that keeps others out as well",
          B.matching_bar(rows, 0.0) == (0.6, 0.25, 0.0) and B.matching_bar(rows, -1) is None)
    check("event clustering: the 2-second wait",
          B.cluster_times([0.1, 0.5, 2.0, 5.0, 5.1]) == [0.1, 5.0]
          and B.matched_events([1.0, 10.0], [1.5, 30.0], 1.0) == [1.0])
    check("the rules are fixed and written down",
          B.WAKE2_RULES["min_owner_clips"] == 10 and B.VAD_RULES["min_owner_clips"] == 10
          and B.VOICE_ID_RULES["min_other_clips"] == 50 and len(B.NOISE_SNRS) == 3)


def t_bakeoff_new_parts_run_only_when_asked():
    d = Path(tempfile.mkdtemp(prefix="bake2-", dir=TMP))
    env = dict(os.environ, OPENJARVIS_CONFIG_DIR=str(d), JARVIS_CONFIG_DIR=str(d),
               PYTHONPATH=os.pathsep.join([str(HERE), str(HERE / "rebuilt")]))
    import subprocess
    r = subprocess.run([sys.executable, str(HERE / "jarvis_bakeoff.py"), "--vad", "--wake2",
                        "--voice-id"], env=env, stdin=subprocess.DEVNULL, capture_output=True,
                       text=True, timeout=300)
    check("--vad --wake2 --voice-id finish with nothing installed", r.returncode == 0,
          r.stdout[-1500:] + r.stderr[-1500:])
    runs = sorted((d / "voice" / "bakeoff").glob("2*"))
    doc = json.loads((runs[-1] / "results.json").read_text(encoding="utf-8")) if runs else {}
    check("each ends in its 'keep' verdict, and the older two parts did not run",
          doc.get("vad", {}).get("verdict") == B.KEEP_V4
          and doc.get("wake2", {}).get("verdict") == B.KEEP_ONE
          and doc.get("voice_id", {}).get("verdict") == B.ROWS_NOT_READY
          and "wake" not in doc and "voice" not in doc, list(doc))
    src = (HERE / "jarvis_bakeoff.py").read_text(encoding="utf-8")
    check("the bake-off still changes no setting", "set_setting" not in src
          and ".toml" not in src and "_write_state" not in src)


def t_status_shapes():
    with Temp():
        st = S.status()
        g = st["gate"]
        check("gate carries both settings, their choices, defaults and why one is blocked",
              g["wake_confirm"] == "one" and g["voice_id_model"] == "titanet"
              and g["settings"]["choices"]["wake_confirm"] == ["one", "both"]
              and g["settings"]["defaults"]["voice_id_model"] == "titanet"
              and set(g["settings"]["blocked"]) == {"wake_confirm", "voice_id_model"}, g["settings"])
        c = st["wake"]["confirm"]
        check("wake.confirm says the setting and whether the second detector can run",
              {"setting", "active", "available", "why", "note", "agree_seconds"} <= set(c), c)
        check("the enroll route's own view carries both",
              E.settings_view()["wake_confirm"] == "one"
              and E.settings_view()["voice_id_model"] == "titanet")
        check("an older voice module: \"\" - the apps do not offer them",
              S._strict_state({})["wake_confirm"] == "" and S._strict_state({})["voice_id_model"] == "")


# ------------------------------------------------ 10. the real files -----

def t_real_files():
    root = os.environ.get("JARVIS_TEST_VOICE_MODELS")
    if not root:
        skip("real files", "set JARVIS_TEST_VOICE_MODELS to a folder with vad/ (both files), "
                           "wakeword/ and tts/, and install pymicro-wakeword, to run these")
        return
    vad = Path(root) / "vad"
    for v in ("v4", "v6"):
        p = vad / S.VAD_FILES[v]["file"]
        if p.is_file():
            check(f"Silero {v}: the pinned file", S._file_sha256(p) == S.VAD_FILES[v]["sha256"])
            check(f"Silero {v}: sherpa-onnx loads it with Jarvis's own settings",
                  S.vad_config_for(str(p)) is not None)
    if not M.status()["available"]:
        skip("the real second detector", M.status()["why"])
        return
    tts = Path(root) / "tts"
    if not (tts / "model.onnx").is_file():
        skip("the real second detector", "no Kokoro in tts/")
        return
    with mock.patch.object(S, "_models_dir", lambda: Path(root)):
        S.reload_engines()
        eng = S._tts_engine()
        a = eng.generate("Hey Jarvis, what time is it?", sid=0, speed=1.0)
        b = eng.generate("Put the jar of jam back on the top shelf.", sid=0, speed=1.0)
    ha = M.spot(np.asarray(a.samples, np.float32), a.sample_rate)
    hb = M.spot(np.asarray(b.samples, np.float32), b.sample_rate)
    check("the real second detector hears a Kokoro \"hey Jarvis\"", ha.ran and ha.heard, ha)
    check("...and not a sentence without it", hb.ran and not hb.heard, hb)


if __name__ == "__main__":
    for fn in (t_defaults, t_wake_confirm_setting, t_voice_id_model_setting, t_hear_and_gate,
               t_agreement_window, t_microwake_module, t_vad_choice, t_enroll_extra_models,
               t_newer_model_never_falls_back_to_the_small_one,
               t_bakeoff_verdicts, t_bakeoff_new_parts_run_only_when_asked, t_status_shapes,
               t_real_files):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            T.FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(T.PASSED)} passed, {len(T.FAILED)} failed, {len(T.SKIPPED)} skipped")
    if T.FAILED:
        print("failed: " + ", ".join(T.FAILED))
    sys.exit(1 if T.FAILED else 0)
