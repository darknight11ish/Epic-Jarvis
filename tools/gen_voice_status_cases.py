#!/usr/bin/env python3
"""Writes jarvis-desktop/tests/fixtures/voice-status-cases.json: what
GET /api/voice/status really answers in a few named situations, and what
POST /api/voice/wake really answers when turned on and off.

    python3 tools/gen_voice_status_cases.py            # write the file
    python3 tools/gen_voice_status_cases.py --check    # compare only

Every case is backend/jarvis_speech.status() itself (and set_wake_enabled()
for the two POST answers), run with the outside world replaced: a temporary
config folder, voice prints trained from synthesised tones with the basic
(spectral) check, empty stand-in model files where a case needs the PC to
"have" a model, and a stand-in for starting the approval card's thread.
Nothing in a status is written by hand, so the desktop's Settings -> Voice
builds against the producer's real output. backend/test_voice_contract.py
fails when the committed file differs from a fresh run.

WHAT IS CHANGED AFTER THE RUN, and only this, so the file is the same on
every machine: the temporary folder and the home folder in the backend's
own sentences become `~/.openjarvis`, and the moments a print was made, a
card will expire or a card was answered become fixed numbers.
"""
import array
import base64
import io
import json
import math
import os
import sys
import tempfile
import wave
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
FIXTURE = ROOT / "jarvis-desktop" / "tests" / "fixtures" / "voice-status-cases.json"
for p in (BACKEND, BACKEND / "rebuilt"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import jarvis_speech as S  # noqa: E402
import jarvis_turn as T  # noqa: E402
import jarvis_voice as V  # noqa: E402
import jarvis_voice_enroll as E  # noqa: E402
import jarvis_wakeword as W  # noqa: E402

#: The fixed values the changing ones are replaced with (see the docstring).
FIXED_TIME = 1790000000.0
FIXED_EXPIRES_IN = 170
HOME_WORDS = "~/.openjarvis"


def tone_wav(freq: float, seconds: float = 1.5, rate: int = 16000) -> bytes:
    """One sine tone as a WAV - a "voice" the basic check can learn."""
    s = array.array("h", [int(0.4 * 32767 * math.sin(2 * math.pi * freq * i / rate))
                          for i in range(int(seconds * rate))])
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(s.tobytes())
    return b.getvalue()


def tone(freq: float, seconds: float = 1.5) -> list:
    samples, _ = S._read_wav(tone_wav(freq, seconds))
    return samples


class World:
    """A temporary config folder for jarvis_speech, jarvis_wakeword and
    jarvis_turn, and a temporary folder for the voice prints."""

    def __init__(self, models: bool = False):
        self.models = models

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.dir = d
        self.profile = d / "voice" / "owner.json"
        self.profile.parent.mkdir(parents=True)
        wake_dir = d / "voice-models" / "wakeword"
        turn_file = d / "voice-models" / "turn" / T.MODEL_FILE
        self.patches = [
            mock.patch.object(S, "_config_dir", return_value=d),
            mock.patch.object(V, "PROFILE_PATH", self.profile),
            mock.patch.object(W, "model_dir", return_value=wake_dir),
            mock.patch.object(T, "model_path", return_value=turn_file),
        ]
        for p in self.patches:
            p.start()
        if self.models:
            # Empty stand-ins: status() only checks that the files are there.
            for name in list(W.MODEL_FILES.values()) + list(W.PHRASE_MODELS.values()):
                (wake_dir / name).parent.mkdir(parents=True, exist_ok=True)
                (wake_dir / name).write_bytes(b"")
            turn_file.parent.mkdir(parents=True, exist_ok=True)
            turn_file.write_bytes(b"")
        S.reload_engines()
        E._reset_for_tests()
        S._reset_wake_for_tests()
        return self

    def train(self, mic: str, freq: float, clips: int = 3):
        V.enroll([tone(freq + i) for i in range(clips)], embedder=V.Embedder(), mic=mic)

    def verifier(self, mic: str, positives: int):
        """A readable "hey Jarvis" check for `mic`, in the file format
        jarvis_wakeword reads (all-zero weights: nothing here scores audio)."""
        doc = {"version": W.VERIFIER_VERSION, "w": [0.0] * (W.EMB_WINDOW * 96), "b": 0.0,
               "threshold": 0.4, "positives": positives, "mic": mic}
        W.verifier_path(mic).write_text(json.dumps(doc), encoding="utf-8")

    def __exit__(self, *a):
        for p in reversed(self.patches):
            p.stop()
        S._reset_wake_for_tests()
        self.tmp.cleanup()
        S.reload_engines()
        E._reset_for_tests()


def speech_to_text_ready():
    """The PC has its speech-to-text files (the same stand-in
    backend/test_voice_contract.py uses for "trained AND speech-to-text")."""
    return [mock.patch.object(S, "_files_present", return_value=True),
            mock.patch.object(S, "_cfg", side_effect=lambda k, d=None:
                              "sherpa-onnx" if k == "stt_engine" else d)]


def held_card():
    """set_wake_enabled's approval card, raised and never answered."""
    return dict(gate=lambda *a: None, tier_of=lambda a: "ask", spawn=lambda fn: None)


def scrub(value, world: World):
    """The machine-specific parts, made the same everywhere (see the docstring)."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if k in ("created", "at") and isinstance(v, (int, float)) and v:
                out[k] = FIXED_TIME
            elif k == "expires_in" and isinstance(v, int):
                out[k] = FIXED_EXPIRES_IN
            else:
                out[k] = scrub(v, world)
        return out
    if isinstance(value, list):
        return [scrub(v, world) for v in value]
    if isinstance(value, str):
        named = False
        for folder in config_folders(world):
            if folder in value:
                value = value.replace(folder, HOME_WORDS)
                named = True
        # On Windows the rest of the path has backslashes; the file is the
        # same on every machine, so they become forward slashes.
        return value.replace("\\", "/") if named else value
    return value


def config_folders(world: World) -> list:
    """Every folder the backend's sentences may name as its config folder:
    this run's temporary one, and the real one - which backend/run_suites.py
    points somewhere temporary too (OPENJARVIS_CONFIG_DIR). Longest first,
    so a folder inside another is replaced whole."""
    found = {str(world.dir), str(Path.home() / ".openjarvis")}
    for key in ("OPENJARVIS_CONFIG_DIR", "JARVIS_CONFIG_DIR"):
        if os.environ.get(key):
            found.add(os.environ[key])
    for module in (W, T):
        try:
            found.add(str(module._config_dir()))
        except Exception:
            pass
    return sorted((f for f in found if f), key=len, reverse=True)


def cases() -> dict:
    out = {}

    with World() as w:
        out["not_trained"] = scrub(S.status(), w)

    with World() as w:
        w.train("phone", 220.0)
        out["phone_trained"] = scrub(S.status(), w)

    with World() as w:
        # Before voice prints were per microphone: the one owner.json.
        V.enroll([tone(230.0 + i) for i in range(4)], embedder=V.Embedder(),
                 path=w.profile)
        out["older_single_print"] = scrub(S.status(), w)

    with World() as w:
        # Trained with a different voice check than the one installed now.
        w.profile.write_text(json.dumps({"centroid": [1.0, 0.0], "samples": 5,
                                         "embedder": "sherpa-onnx:0123456789ab"}))
        out["needs_retraining"] = scrub(S.status(), w)

    with World(models=True) as w:
        w.train("phone", 220.0)
        w.train("desktop", 240.0, clips=4)
        w.verifier("phone", 4)
        S._write_wake(True)
        ready = speech_to_text_ready()
        for p in ready:
            p.start()
        try:
            out["ready_wake_on"] = scrub(S.status(), w)
        finally:
            for p in reversed(ready):
                p.stop()

    with World() as w:
        # "Train my voice" from the phone, approved on its card: the real
        # stage() and enrolment, with the card answered "approved" at once.
        approved = type("Verdict", (), {"allowed": True, "tier": "ask",
                                        "outcome": "approved", "request_id": "r"})()
        body = json.dumps({"mic": "phone", "clips": [
            base64.b64encode(tone_wav(210.0 + 7 * i, 2.0)).decode() for i in range(3)]})
        code, _ = E.stage(body.encode(), gate=lambda *a: approved, tier_of=lambda a: "ask",
                          spawn=lambda fn: fn())
        assert code == 202, code
        out["trained_by_card"] = scrub(S.status(), w)

    with World() as w:
        w.train("phone", 220.0)
        on = S.set_wake_enabled(True, **held_card())
        out["wake_waiting"] = scrub(S.status(), w)
        answers = {"wake_on_pending": scrub(on, w)}
        answers["wake_off"] = scrub(S.set_wake_enabled(False), w)
        out["wake_off_after_waiting"] = scrub(S.status(), w)
    return out, answers


def render() -> str:
    statuses, answers = cases()
    body = {
        "_about": ("Real output of backend/jarvis_speech.status() (GET /api/voice/status) "
                   "in named cases, and of set_wake_enabled() (POST /api/voice/wake) under "
                   "`answers`, made by tools/gen_voice_status_cases.py. Voice prints are "
                   "trained from synthesised tones with the basic check; model files are "
                   "empty stand-ins. Folders and times are made the same on every machine. "
                   "Do not edit by hand: re-run the tool."),
        "cases": statuses,
        "answers": answers,
    }
    return json.dumps(body, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv) -> int:
    text = render()
    if "--check" in argv:
        have = FIXTURE.read_text(encoding="utf-8") if FIXTURE.is_file() else ""
        if have.replace("\r\n", "\n") != text:
            print(f"{FIXTURE.relative_to(ROOT)} is out of date: run "
                  f"python3 tools/gen_voice_status_cases.py")
            return 1
        print("voice-status-cases.json matches the producer.")
        return 0
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {FIXTURE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
