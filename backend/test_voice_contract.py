"""The voice routes' JSON, checked against the field names the clients read.

    python3 test_voice_contract.py

WHY THIS EXISTS. The phone's `VoiceStatus` (jarvis-client net/VoiceModels.kt)
reads `/api/voice/status` as {available, listening: {push_to_talk, ...},
stt, tts, audio_in, gate}, and shows its talk button only when
`listening.push_to_talk` is true. jarvis_speech.status() returned a FLAT
dict with none of those keys, so the button never appeared - and nothing
could notice, because every phone field has a default. The utterance reply
had the same gap: the phone reads `ok`/`owner`, jarvis_speech sent
`is_owner`.

So this suite reads the clients' OWN SOURCE - the Kotlin data classes and the
desktop's Rust struct - and checks the backend's real output against them:
every field a client declares must be in the JSON, with a matching type. A
field added to either client, or renamed on the backend, fails here.

No network, no microphone: clips are synthesised, and the one enrolled
voice uses the spectral fallback into a temp folder.
"""
import array
import io
import json
import math
import re
import sys
import tempfile
import traceback
import wave
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO  # noqa: E402

sys.path.insert(0, str(HERE / "rebuilt"))
sys.path.insert(0, str(HERE))
# On a real install (JARVIS_BACKEND set), the backend's own copies must be
# these - otherwise this would test the repository's copy, not the one the
# phone is talking to. See _where.require_shipped.
from _where import require_shipped  # noqa: E402
require_shipped("jarvis_speech.py", "jarvis_voice_enroll.py")
import jarvis_speech as S  # noqa: E402
import jarvis_voice as V  # noqa: E402
import jarvis_voice_enroll as E  # noqa: E402
from _voice_test import semantic_voice  # noqa: E402

KT = REPO / "jarvis-client" / "app" / "src" / "main" / "java" / "com" / "jarvis" / "client" / "net" / "VoiceModels.kt"
RS = REPO / "jarvis-desktop" / "src-tauri" / "src" / "voice.rs"
FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


# ------------------------------------------------ reading the client code --

def kotlin_classes(path: Path) -> dict:
    """{ClassName: [(json_key, kotlin_type), ...]} for every `data class` in
    the file. Comments are stripped first, so a `val` in a doc comment is
    not read as a field."""
    src = path.read_text(encoding="utf-8")
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    src = re.sub(r"//[^\n]*", "", src)
    out = {}
    for m in re.finditer(r"data class (\w+)\((.*?)\n\)", src, flags=re.S):
        fields = []
        for f in re.finditer(r'(?:@SerialName\("([^"]+)"\)\s*)?val (\w+)\s*:\s*([\w.<>?]+)',
                             m.group(2)):
            fields.append((f.group(1) or f.group(2), f.group(3)))
        out[m.group(1)] = fields
    return out


def rust_struct(path: Path, name: str) -> list:
    """[(field, rust_type, required)] for `struct <name> { ... }`. A field is
    required unless it carries #[serde(default...)]."""
    src = path.read_text(encoding="utf-8")
    m = re.search(r"struct " + name + r"\s*\{(.*?)\n\}", src, flags=re.S)
    if not m:
        return []
    fields, default = [], False
    for line in m.group(1).splitlines():
        line = line.strip()
        if line.startswith("#[serde(default"):
            default = True
            continue
        f = re.match(r"(?:pub\s+)?(\w+)\s*:\s*([\w<>]+)\s*,", line)
        if f:
            fields.append((f.group(1), f.group(2), not default))
            default = False
    return fields


def type_ok(value, ktype: str, classes: dict) -> bool:
    t = ktype.rstrip("?")
    if value is None:
        return ktype.endswith("?")
    if t == "Boolean" or t == "bool":
        return isinstance(value, bool)
    if t in ("String",):
        return isinstance(value, str)
    if t in ("Int", "Long"):
        return isinstance(value, int) and not isinstance(value, bool)
    if t in ("Double", "Float", "f64", "f32"):
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if t in classes:
        return isinstance(value, dict)
    return True        # a type this reader does not know: not its business


def conforms(obj: dict, cls: str, classes: dict, where: str, optional=()) -> None:
    """Every field `cls` declares is in `obj`, with a matching type. Recurses
    into nested data classes. `optional` names, by FULL path, fields a
    client declares that the backend sends only sometimes - each with the
    reason at the call site."""
    for key, ktype in classes[cls]:
        path = f"{where}.{key}"
        if key not in obj:
            check(f"{path} is sent", path in optional,
                  f"{cls} declares `{key}` and the backend does not send it")
            continue
        v = obj[key]
        check(f"{path} is a {ktype}", type_ok(v, ktype, classes), f"got {v!r}")
        t = ktype.rstrip("?")
        if t in classes and isinstance(v, dict):
            conforms(v, t, classes, path, optional)


# ---------------------------------------------------------------- helpers --

def tone(freq=220.0, seconds=1.0, rate=16000) -> bytes:
    s = array.array("h", [int(0.4 * 32767 * math.sin(2 * math.pi * freq * i / rate))
                          for i in range(int(seconds * rate))])
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(s.tobytes())
    return b.getvalue()


class Env:
    """A temp config dir for jarvis_speech and a temp profile for jarvis_voice."""

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.profile = d / "owner.json"
        self.patches = [mock.patch.object(S, "_config_dir", return_value=d),
                        mock.patch.object(V, "PROFILE_PATH", self.profile),
                        # These are shapes, not the minimum length (that is
                        # test_voice_strict.py): no minimum, so the suite's
                        # one-second tones reach the voice check.
                        mock.patch.object(S, "_min_command_seconds", return_value=0.0)]
        for p in self.patches:
            p.start()
        # A stand-in speaker model (_voice_test.py): since 2026-09-24 the
        # basic check lets nobody in, so "the owner" needs a real-ish one.
        self._voice = semantic_voice(V, settings_dir=d)
        self.voiceish = self._voice.__enter__()
        S.reload_engines()
        E._reset_for_tests()
        return self

    def __exit__(self, *a):
        self._voice.__exit__(None, None, None)
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()
        S.reload_engines()
        E._reset_for_tests()


# ------------------------------------------------------------------ tests --

def t_the_client_files_are_readable():
    classes = kotlin_classes(KT)
    for c in ("VoiceStatus", "VoiceListening", "VoiceEngine", "VoiceAudioIn", "VoiceGate",
              "VoiceTrainingState", "VoiceTrainingLast", "VoiceTrainingReply", "Heard",
              "VoiceWake", "VoiceSpotter", "VoiceTurn", "VoicePrints", "VoicePrint",
              "VoiceCalibration"):
        check(f"VoiceModels.kt declares {c}", c in classes and classes[c], f"{sorted(classes)}")
    check("VoiceListening reads push_to_talk (the field that hid the button)",
          ("push_to_talk", "Boolean") in classes.get("VoiceListening", []))
    raw = rust_struct(RS, "HeardRaw")
    check("voice.rs declares HeardRaw, with is_owner required",
          ("is_owner", "bool", True) in raw, f"{raw}")
    check("both clients read wake_heard and awake (the wake word's two answers)",
          ("wake_heard", "Boolean") in classes.get("Heard", [])
          and ("awake", "Boolean") in classes.get("Heard", [])
          and ("wake_heard", "bool", False) in raw and ("awake", "bool", False) in raw,
          f"{classes.get('Heard')} / {raw}")
    check("the phone reads listening.wake_word_pending (a card is waiting)",
          ("wake_word_pending", "Boolean") in classes.get("VoiceListening", []))


def t_status_has_every_field_the_phone_reads():
    classes = kotlin_classes(KT)
    with Env():
        st = json.loads(json.dumps(S.status()))     # exactly what goes on the wire
        # `error` is only sent by the route when the module failed to load.
        # The training block's clips/expires_in exist only while a card
        # waits, `last` only once one has been answered, `why` only when the
        # feature is not installed - each covered by the next test.
        conforms(st, "VoiceStatus", classes, "status",
                 optional=("status.error", "status.gate.training.clips",
                           "status.gate.training.expires_in", "status.gate.training.last",
                           "status.gate.training.why"))
        check("the flat keys are still there for anything that read them",
              all(k in st for k in ("enabled", "mode", "enrolled", "samples", "embedder",
                                    "stt_available", "tts_available", "wake_word_enabled")))
        check("the phone may not transcribe", st["audio_in"]["client_stt_allowed"] is False)
        check("nor fall back to its own speech-to-text", st["stt"]["client_fallback_ok"] is False)


def t_push_to_talk_means_it_can_work():
    with Env() as env:
        st = S.status()
        check("not trained: no talk button", st["listening"]["push_to_talk"] is False)
        check("and the reason points at Train my voice",
              "Train my voice" in st["listening"]["push_to_talk_why"], st["listening"])

        clip = tone(220.0)
        samples, _ = S._read_wav(clip)
        V.enroll([samples] * 3, embedder=env.voiceish(), path=env.profile)
        st = S.status()
        check("trained: the gate says so", st["gate"]["enrolled"] is True and st["gate"]["samples"] == 3,
              st["gate"])
        check("trained, but no speech-to-text here: still no button, and it says why",
              st["listening"]["push_to_talk"] is False
              and "speech-to-text" in st["listening"]["push_to_talk_why"], st["listening"])

        with mock.patch.object(S, "_files_present", return_value=True), \
                mock.patch.object(S, "_cfg", side_effect=lambda k, d=None:
                                  "sherpa-onnx" if k == "stt_engine" else d):
            st = S.status()
        check("trained AND speech-to-text: the button shows",
              st["listening"]["push_to_talk"] is True and st["listening"]["push_to_talk_why"] == "",
              st["listening"])

        with mock.patch.object(V, "_cfg", side_effect=lambda k, d=None:
                               "broad" if k == "mode" else d), \
                mock.patch.object(V, "PROFILE_PATH", env.profile.with_name("none.json")):
            st = S.status()
        check("broad mode needs no training (the owner chose it)",
              "not learned" not in st["listening"]["push_to_talk_why"], st["listening"])

        env.profile.write_text(json.dumps({"centroid": [1.0, 0.0], "samples": 5,
                                           "embedder": "sherpa-onnx:0123456789ab"}))
        st = S.status()
        check("a profile from a different voice check: retrain, and no button",
              st["gate"]["needs_retraining"] is True and st["listening"]["push_to_talk"] is False
              and "again" in st["listening"]["push_to_talk_why"], st["gate"])


def t_training_state_in_every_shape():
    classes = kotlin_classes(KT)
    with Env():
        st = S.status()["gate"]["training"]
        conforms(st, "VoiceTrainingState", classes, "idle",
                 optional=("idle.clips", "idle.expires_in", "idle.last", "idle.why"))

        class Held:
            def __init__(self):
                import threading
                self.go = threading.Event()

            def __call__(self, action, detail, prompt):
                self.go.wait(10)
                return type("V", (), {"allowed": False, "tier": "ask", "outcome": "denied",
                                      "request_id": "r"})()
        gate = Held()
        body = json.dumps({"clips": [__import__("base64").b64encode(tone(200 + i * 5, 2.0)).decode()
                                     for i in range(3)]}).encode()
        code, reply = E.stage(body, gate=gate, tier_of=lambda a: "ask", enroll=lambda c: None)
        check("the stage reply conforms to VoiceTrainingReply", code == 202, f"{code} {reply}")
        # `error` and `expires_in` come only with a refusal (checked below).
        conforms(reply, "VoiceTrainingReply", classes, "reply",
                 optional=("reply.error", "reply.expires_in"))
        waiting = S.status()["gate"]["training"]
        conforms(waiting, "VoiceTrainingState", classes, "pending",
                 optional=("pending.last", "pending.why"))
        check("while a card waits, the phone can see it", waiting["pending"] is True
              and waiting["clips"] == 3, waiting)
        code, busy = E.stage(body, gate=gate, tier_of=lambda a: "ask", enroll=lambda c: None)
        check("a refusal carries `error` and `expires_in`",
              code == 409 and isinstance(busy.get("error"), str)
              and isinstance(busy.get("expires_in"), int), busy)
        gate.go.set()
        for _ in range(100):
            if not E.state()["pending"]:
                break
            __import__("time").sleep(0.05)
        done = S.status()["gate"]["training"]
        # A denial has no samples and no reason to give.
        conforms(done, "VoiceTrainingState", classes, "answered",
                 optional=("answered.clips", "answered.expires_in", "answered.why",
                           "answered.last.samples", "answered.last.reason",
                           # only a training that enrolled has a wake check,
                           # only a threshold card that passed has a bar
                           "answered.last.wake_check", "answered.last.threshold"))
        check("the last outcome is readable", done.get("last", {}).get("outcome") == "denied", done)

    with mock.patch.dict(sys.modules, {"jarvis_voice_enroll": None}):
        st = S._training_state()
    conforms(st, "VoiceTrainingState", classes, "not-installed",
             optional=("not-installed.clips", "not-installed.expires_in", "not-installed.last"))
    check("not installed says so", st["available"] is False and st["why"], st)


def t_the_utterance_reply_serves_both_clients():
    classes = kotlin_classes(KT)
    desktop = rust_struct(RS, "HeardRaw")
    with Env() as env:
        cases = {"garbage": S.hear(b"not a wav"),
                 "no profile": S.hear(tone(440.0))}
        samples, _ = S._read_wav(tone(220.0))
        V.enroll([samples] * 3, embedder=env.voiceish(), path=env.profile)
        cases["the owner, no engine"] = S.hear(tone(220.0))
        cases["a stranger"] = S.hear(tone(880.0))
        with mock.patch.object(S, "_stt_engine", return_value=object()), \
                mock.patch.object(S, "_transcribe", return_value="what is waiting for me"):
            cases["the owner, transcribed"] = S.hear(tone(220.0))
        # The wake word's shapes: on (through its card), a clip with the
        # phrase, one without, and "hey Jarvis." alone.
        import jarvis_wakeword as W
        S.set_wake_enabled(True, gate=lambda *a: type("V", (), {
            "allowed": True, "tier": "ask", "outcome": "approved", "request_id": "r"})(),
            tier_of=lambda a: "ask", spawn=lambda fn: fn())
        with mock.patch.object(W, "spot", return_value=W.Spot(True, heard=False, score=0.01)):
            cases["wake word, not addressed to Jarvis"] = S.hear(tone(220.0), source="wake_word")
        with mock.patch.object(W, "spot", return_value=W.Spot(True, heard=True, score=0.98)), \
                mock.patch.object(S, "_stt_engine", return_value=object()), \
                mock.patch.object(S, "_transcribe", return_value="Hey Jarvis, what time is it?"):
            cases["wake word, the owner"] = S.hear(tone(220.0), source="wake_word")
        with mock.patch.object(W, "spot", return_value=W.Spot(True, heard=True, score=0.98)), \
                mock.patch.object(S, "_stt_engine", return_value=object()), \
                mock.patch.object(S, "_transcribe", return_value="Hey Jarvis."):
            cases["wake word, awake"] = S.hear(tone(220.0), source="wake_word")
        # "Stop" while Jarvis talks: the desktop reads `stop`, the phone
        # ignores it (a clip it sends is never one it wants stopped by).
        with mock.patch.object(W, "spot_stop", return_value=W.Spot(True, heard=True, score=0.93)):
            cases["wake word, stop"] = S.hear(tone(220.0), source="wake_word")
        check("a stop clip says stop, and nothing else",
              cases["wake word, stop"].stop and not cases["wake word, stop"].is_owner
              and cases["wake word, stop"].text == "", cases["wake word, stop"])
        S.set_wake_enabled(False)
        cases["wake word, switched off"] = S.hear(tone(220.0), source="wake_word")
        S._reset_wake_for_tests()

    for label, heard in cases.items():
        wire = json.loads(json.dumps(heard.as_dict()))
        conforms(wire, "Heard", classes, f"utterance[{label}]")
        for field, rtype, required in desktop:
            if required:
                check(f"utterance[{label}] has the desktop's required {field}", field in wire)
            if field in wire:
                check(f"utterance[{label}].{field} is a {rtype}",
                      type_ok(wire[field], {"bool": "Boolean", "String": "String",
                                            "f64": "Double"}.get(rtype, rtype), classes))

    def outcome(w):
        """The phone's own Heard.outcome, restated (VoiceModels.kt)."""
        if w["ok"] and w["owner"]:
            return "TRANSCRIBED"
        if w["owner"]:
            return "NO_ENGINE"
        if w["threshold"] > 0:
            return "NOT_THE_OWNER"
        return "REFUSED"
    wires = {k: h.as_dict() for k, h in cases.items()}
    check("garbage reads as REFUSED on the phone", outcome(wires["garbage"]) == "REFUSED")
    check("the owner with no engine reads as NO_ENGINE",
          outcome(wires["the owner, no engine"]) == "NO_ENGINE", wires["the owner, no engine"])
    check("a stranger reads as NOT_THE_OWNER", outcome(wires["a stranger"]) == "NOT_THE_OWNER",
          wires["a stranger"])
    check("a transcript reads as TRANSCRIBED, with the words",
          outcome(wires["the owner, transcribed"]) == "TRANSCRIBED"
          and wires["the owner, transcribed"]["text"] == "what is waiting for me",
          wires["the owner, transcribed"])
    check("a stranger's reply carries no words", wires["a stranger"]["text"] == "")

    def phone_wake(w):
        """The phone's own WakeRules.verdict, restated (voice/WakeRules.kt)."""
        if not w["available"]:
            return "STOP"
        if w["awake"] and w["owner"]:
            return "AWAKE"
        if w["wake_heard"] and w["owner"]:
            return "ANSWER"
        return "IGNORE"
    for label, want in (("wake word, not addressed to Jarvis", "IGNORE"),
                        ("wake word, the owner", "ANSWER"),
                        ("wake word, awake", "AWAKE"),
                        ("wake word, switched off", "STOP")):
        check(f"{label} reads as {want} on the phone", phone_wake(wires[label]) == want,
              wires[label])
    check("the owner's wake-word text has the phrase taken off",
          wires["wake word, the owner"]["text"] == "what time is it?", wires["wake word, the owner"])
    check("seconds is the clip's real length", abs(wires["a stranger"]["seconds"] - 1.0) < 0.01)


def t_the_someone_else_reply_serves_the_phone():
    """mode calibrate's answer, against the phone's VoiceCalibration."""
    import base64
    classes = kotlin_classes(KT)
    with Env() as env:
        samples, _ = S._read_wav(tone(220.0, 2.0))
        V.enroll([samples, samples * 0.9, samples * 0.8], embedder=env.voiceish(),
                 path=env.profile)
        body = json.dumps({"mode": "calibrate", "mic": "phone",
                           "clips": [base64.b64encode(tone(700.0, 2.0)).decode()]}).encode()
        code, reply = E.stage(body)
        wire = json.loads(json.dumps(reply))
        check("the check answers 200", code == 200, (code, reply))
        conforms(wire, "VoiceCalibration", classes, "calibrate", optional=("calibrate.error",))
        code, refused = E.stage(json.dumps({"mode": "calibrate", "clips": []}).encode())
        conforms(json.loads(json.dumps(refused)), "VoiceCalibration", classes, "refused",
                 optional=tuple(f"refused.{k}" for k, _ in classes["VoiceCalibration"]
                                if k not in ("ok", "error")))
        check("a refusal carries the phone's `error`", code == 400 and refused["error"], refused)
        st = S.status()
        check("status says this PC understands the check (the phone waits for it)",
              st["gate"]["training"]["calibrate"] is True)
        check("status lists the prints; this one is the old single print",
              st["gate"]["prints"]["general"]["trained"] is True
              and st["gate"]["prints"]["phone"]["trained"] is False, st["gate"]["prints"])


def t_the_turn_answer_serves_the_desktop():
    """voice.rs TurnRaw reads the /api/voice/turn reply (jarvis_turn.handle)."""
    import jarvis_turn as T
    raw = rust_struct(RS, "TurnRaw")
    check("voice.rs declares TurnRaw with available and complete",
          {f for f, _, _ in raw} >= {"available", "complete"}, raw)
    fake = type("S", (), {"run": lambda self, _o, _f: [[[0.9]]]})()
    with mock.patch.object(T, "_load", return_value=(fake, "input_features")):
        code, out = T.handle(tone(220.0, 2.0))
    wire = json.loads(json.dumps(out))
    for field, rtype, _ in raw:
        check(f"turn reply has {field} as {rtype}", field in wire and type_ok(
            wire[field], {"bool": "Boolean", "f64": "Double"}.get(rtype, rtype), {}), wire)
    with mock.patch.object(T, "_load", return_value=None):
        code, out = T.handle(tone(220.0, 2.0))
    check("no model: available is false, so voice.rs stops asking",
          code == 200 and out["available"] is False, out)


def t_an_older_jarvis_voice_still_works():
    """jarvis_speech.py is copied to the PC by apply-patches.ps1; the PC's
    jarvis_voice.py may be older and not take `sample_rate`. hear() must not
    turn that into a TypeError (its verify() call is not wrapped)."""
    real = V.verify

    def old_verify(audio, embedder=None):
        return real(audio, embedder)
    with Env(), mock.patch.object(V, "verify", old_verify):
        try:
            heard = S.hear(tone(440.0))
            ok = heard.is_owner is False and "no enrolled" in heard.reason
        except TypeError as exc:
            ok, heard = False, exc
    check("hear() works with a verify() that has no sample_rate", ok, f"{heard}")


def t_the_desktop_fixture_is_fresh():
    """jarvis-desktop/tests/fixtures/voice-status-cases.json is what the
    desktop's Settings -> Voice is tested against (tests/voice-settings.mjs,
    and voice.rs's own tests). It must be this backend's real output, so a
    renamed or dropped field fails here rather than as a quiet blank line."""
    sys.path.insert(0, str(REPO / "tools"))
    import gen_voice_status_cases as G
    check("voice-status-cases.json equals a fresh run of the producer",
          G.main(["--check"]) == 0, "run python3 tools/gen_voice_status_cases.py")
    # The training and custom-voice screens are tested against their own
    # file (tests/voice-training.mjs). Nothing checked it, so a backend
    # change left it stale unseen (the voice-flow merge did exactly that).
    import gen_voice_training_cases as T
    check("voice-training-cases.json equals a fresh run of the producer",
          T.main(["--check"]) == 0, "run python3 tools/gen_voice_training_cases.py")
    # The phone's voice screens read their own copy of the PC's answers.
    import gen_phone_voice_cases as P
    check("phone-voice-cases.json equals a fresh run of the producer",
          P.main(["--check"]) == 0, "run python3 tools/gen_phone_voice_cases.py")


if __name__ == "__main__":
    for fn in (t_the_client_files_are_readable, t_status_has_every_field_the_phone_reads,
               t_push_to_talk_means_it_can_work, t_training_state_in_every_shape,
               t_the_utterance_reply_serves_both_clients, t_the_turn_answer_serves_the_desktop,
               t_the_someone_else_reply_serves_the_phone,
               t_an_older_jarvis_voice_still_works, t_the_desktop_fixture_is_fresh):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
