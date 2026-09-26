#!/usr/bin/env python3
"""Writes jarvis-desktop/tests/fixtures/voice-training-cases.json: what the
backend really answers for the desktop's voice training, strictness and
private-answer settings, guided test and custom voices.

    python3 tools/gen_voice_training_cases.py            # write the file
    python3 tools/gen_voice_training_cases.py --check    # compare only

A sibling of tools/gen_voice_status_cases.py, built the same way. Every
entry is the backend's own code, run with the outside world replaced:

  statuses   backend/jarvis_speech.status()      GET /api/voice/status
  enroll     backend/jarvis_voice_enroll.stage() POST /api/voice/enroll
             (training in rounds, cancel, strictness, privacy, measure),
             each as {"code": <HTTP code>, "body": <what the route sends>}
  voices     backend/jarvis_voices.status()      GET /api/voice/voices
  voice_posts backend/jarvis_voices.handle_post() POST /api/voice/voices/*

What is replaced, and only this: a temporary config folder; the two
voice-ID models by stand-ins (the real class, `semantic`, with a name like
a real model's) that turn a loud clip into a stranger's voice and a normal
one into the owner's, so an odd recording, an owner-voice refusal and a
guided test come out of the real arithmetic; the approval card, answered
"approved" at once or never; ZipVoice's and Kokoro's engines by stand-ins
that make a quiet tone; and nvidia-smi / Ollama through
tools/gen_second_card_cases.py's World, so "a capable second card" is
jarvis_second_card's own reading of the owner's two cards.

WHAT IS CHANGED AFTER THE RUN, and only this, so the file is the same on
every machine: the temporary folder and the home folder in the backend's
sentences become `~/.openjarvis`; the moments something happened (`at`,
`created`, `since`, `changed`) and a card's `expires_in` become fixed
numbers; and in a say() timing row, the clock-measured `seconds` (and the
`rtf` made from it) become a fixed 0.84 s - it is how long this machine
took, not something the code decides.

No backend suite checks this file yet: backend/test_voice_contract.py runs
gen_voice_status_cases.py --check, and should run this one's too.
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
FIXTURE = ROOT / "jarvis-desktop" / "tests" / "fixtures" / "voice-training-cases.json"
for p in (BACKEND, BACKEND / "rebuilt", ROOT / "tools"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import numpy as np  # noqa: E402
import jarvis_speech as S  # noqa: E402
import jarvis_turn as T  # noqa: E402
import jarvis_voice as V  # noqa: E402
import jarvis_voice_enroll as E  # noqa: E402
import jarvis_voices as VO  # noqa: E402
import jarvis_wakeword as W  # noqa: E402
import gen_second_card_cases as SCG  # noqa: E402

FIXED_TIME = 1790000000.0
FIXED_EXPIRES_IN = 170
FIXED_TOOK = 0.84
HOME_WORDS = "~/.openjarvis"

OWNER = [1.0, 0.2, 0.0, 0.0, 0.1, 0.0, 0.0, 0.0]
STRANGER = [0.0, 0.0, 1.0, 0.0, 0.0, 0.3, 0.0, 0.0]
OTHER = [0.0, 0.0, 0.0, 0.0, 0.2, 0.0, 1.0, 0.3]


def _unit(v):
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v]


def _samples(audio) -> list:
    if isinstance(audio, np.ndarray):
        return [float(x) for x in audio[:4000]]
    return V._pcm(audio)[:4000]


class _Fixture(V.Embedder):
    """A voice-ID model stand-in: the real class, flagged as a real model.
    A clip peaking above 0.7 is "a stranger", one above 0.5 "someone
    else again", anything quieter "the owner" (with a small, repeatable
    wobble from its pitch, so no two clips are identical)."""
    semantic = True
    available = True
    dim = 8

    def embed(self, audio, sample_rate=None):
        x = _samples(audio)
        if not x:
            return []
        peak = max(abs(v) for v in x)
        crossings = sum(1 for a, b in zip(x, x[1:]) if (a < 0) != (b < 0))
        base = STRANGER if peak > 0.7 else OTHER if peak > 0.5 else OWNER
        wobble = 0.01 * (crossings % 7)
        return _unit([b + (wobble if i == 3 else 0.0) for i, b in enumerate(base)])


class SmallModel(_Fixture):
    name = "sherpa-onnx:fixture00000"


class StrongModel(_Fixture):
    name = "sherpa-onnx:fixturestrong"


def tone_wav(freq: float, seconds: float = 2.0, amp: float = 0.4, rate: int = 16000) -> bytes:
    """One tone as a 16-bit mono WAV - what the desktop sends, at 16 kHz."""
    s = array.array("h", [int(amp * 32767 * math.sin(2 * math.pi * freq * i / rate))
                          for i in range(int(seconds * rate))])
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(s.tobytes())
    return b.getvalue()


def b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def clips(n: int, freq: float = 180.0, loud=(), seconds: float = 2.0, other=()) -> list:
    """n clips; the (0-based) ones in `loud` sound like a stranger, the
    ones in `other` like a third person."""
    return [b64(tone_wav(freq + 3 * i, seconds,
                         amp=0.9 if i in loud else 0.6 if i in other else 0.4))
            for i in range(n)]


class Verdict:
    def __init__(self, outcome="approved"):
        self.tier, self.outcome = "ask", outcome
        self.allowed = outcome == "approved"
        self.request_id, self.reason = "r", outcome


def approved(*_a):
    return Verdict("approved")


def denied(*_a):
    return Verdict("denied")


def ask(_action):
    return "ask"


def now(fn):
    fn()


def never(_fn):
    """The card is raised and nobody answers it: `waiting`."""


class FakeZip:
    def generate(self, text, prompt_text, prompt_samples, sample_rate, speed, steps):
        n = int(24000 * max(0.5, len(text) / 15.0))
        return type("A", (), {"samples": (0.1 * np.ones(n)).astype(np.float32),
                              "sample_rate": 24000})()


class FakeKokoro:
    def generate(self, text, sid=0, speed=1.0):
        return type("A", (), {"samples": (0.05 * np.ones(48000)).astype(np.float32),
                              "sample_rate": 24000})()


class StandInSherpa:
    """Where the sherpa-onnx package would be: only its presence is read
    (and that it has ZipVoice), so the file checks below it - the real
    ones - say the same on a machine without the package."""
    OfflineTtsZipvoiceModelConfig = object


class World:
    """A temporary config folder for every voice module, the stand-in
    models, and the jarvis_voices hooks test_voices.py replaces."""

    def __init__(self, models: str = "both"):
        self.models = models            # "both", "small" or "none"

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.dir = d
        profile = d / "voice" / "owner.json"
        profile.parent.mkdir(parents=True)
        self.patches = [
            mock.patch.object(S, "_config_dir", return_value=d),
            mock.patch.object(V, "PROFILE_PATH", profile),
            mock.patch.object(W, "model_dir", return_value=d / "voice-models" / "wakeword"),
            mock.patch.object(T, "model_path", return_value=d / "voice-models" / "turn" / "x.onnx"),
            mock.patch.object(VO, "_config_dir", return_value=d),
            mock.patch.object(VO, "_cfg", side_effect=lambda k, default=None: default),
            mock.patch.object(VO, "_audit", side_effect=lambda e, det: None),
            mock.patch.object(VO, "_publish", side_effect=lambda data: None),
            mock.patch.object(VO, "_start_reaper", side_effect=lambda: None),
            mock.patch.object(VO, "sherpa_onnx", StandInSherpa),
            mock.patch.object(E, "_audit", side_effect=lambda e, det: None),
            mock.patch.object(E, "_arm_expiry", side_effect=lambda: None),
        ]
        if self.models in ("both", "small"):
            self.patches.append(mock.patch.object(V, "EcapaEmbedder", SmallModel))
        strong = StrongModel() if self.models == "both" else None
        self.patches.append(mock.patch.object(V, "strong_embedder", lambda *a: strong))
        for p in self.patches:
            p.start()
        S.reload_engines()
        E._reset_for_tests()
        S._reset_wake_for_tests()
        V._reset_repeat_for_tests()
        VO._reset_for_tests()
        with S._TIMINGS_LOCK:
            S._TIMINGS.clear()
        return self

    def small(self):
        return SmallModel() if self.models in ("both", "small") else V.Embedder()

    def strong(self):
        return StrongModel() if self.models == "both" else None

    def train(self, mic: str, n: int = 3):
        """A voice print for `mic`, straight through jarvis_voice.enroll."""
        pcm = [E._read_clip(i + 1, tone_wav(200.0 + 5 * i))[0] for i in range(n)]
        V.enroll(pcm, embedder=self.small(), sample_rate=16000, mic=mic,
                 strong=self.strong())

    def speaking(self):
        """The built-in voice's files present and its engine a stand-in, and
        ZipVoice built with a stand-in engine: Jarvis can speak."""
        for p in (mock.patch.object(S, "sherpa_onnx", StandInSherpa),
                  mock.patch.object(S, "_files_present", return_value=True)):
            p.start()
            self.patches.append(p)
        S._tts_cache = FakeKokoro()
        VO._ZIP.update(engine=FakeZip(), why="ready", built=True)

    def stage(self, body: dict, gate=approved, spawn=now, **kw):
        code, out = E.stage(json.dumps(body).encode(), gate=gate, tier_of=ask, spawn=spawn,
                            **kw)
        return {"code": code, "body": out}

    def __exit__(self, *a):
        for p in reversed(self.patches):
            p.stop()
        S._reset_wake_for_tests()
        E._reset_for_tests()
        VO._reset_for_tests()
        with S._TIMINGS_LOCK:
            S._TIMINGS.clear()
        self.tmp.cleanup()
        S.reload_engines()


def train_round(r: int, n: int, *, mic="desktop", add=False, finish=False, loud=(),
                other=()) -> dict:
    body = {"mode": "train", "round": r, "mic": mic, "add": add,
            "clips": clips(n, loud=loud, other=other)}
    if finish:
        body["finish"] = True
    return body


# ----------------------------------------------------------------- scrubbing --

def scrub(value, folders: list):
    if isinstance(value, dict):
        out = {}
        timing = "audio_seconds" in value and "chars" in value
        for k, v in value.items():
            if k in ("created", "at", "since", "changed") and isinstance(v, (int, float)) \
                    and not isinstance(v, bool) and v:
                out[k] = FIXED_TIME
            elif k == "expires_in" and isinstance(v, int):
                out[k] = FIXED_EXPIRES_IN
            elif timing and k == "seconds":
                out[k] = FIXED_TOOK
            elif timing and k == "rtf":
                a = value.get("audio_seconds") or 0
                out[k] = round(FIXED_TOOK / a, 3) if a > 0 else None
            else:
                out[k] = scrub(v, folders)
        return out
    if isinstance(value, list):
        return [scrub(v, folders) for v in value]
    if isinstance(value, str):
        named = False
        for folder in folders:
            if folder in value:
                value = value.replace(folder, HOME_WORDS)
                named = True
        return value.replace("\\", "/") if named else value
    return value


def folders_of(world: World) -> list:
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


# --------------------------------------------------------------------- cases --

def training_cases():
    statuses, enroll = {}, {}

    def keep(world, name, value, into):
        into[name] = scrub(value, folders_of(world))

    # Both voice-ID models, both microphones trained with them: very strict
    # uses the stronger model.
    with World("both") as w:
        w.train("phone")
        w.train("desktop", 4)
        keep(w, "strong_ready", S.status(), statuses)

    # Only the small model: very strict falls back to it, and says so.
    with World("small") as w:
        w.train("phone")
        keep(w, "small_only", S.status(), statuses)

    # No voice-ID model: nothing can be trained, every command refused.
    with World("none") as w:
        keep(w, "no_model", S.status(), statuses)
        keep(w, "needs_model", w.stage(train_round(1, 3)), enroll)

    # A print from before the stronger model was installed: made with the
    # small model alone, read with both installed.
    with World("both") as w:
        pcm = [E._read_clip(i + 1, tone_wav(200.0 + 5 * i))[0] for i in range(3)]
        V.enroll(pcm, embedder=SmallModel(), sample_rate=16000, mic="desktop")
        keep(w, "needs_retraining_strong", S.status(), statuses)

    # Training in three rounds from the desktop, round by round.
    with World("both") as w:
        w.train("phone")
        keep(w, "round_held", w.stage(train_round(1, 12)), enroll)
        keep(w, "session_held", S.status(), statuses)
        keep(w, "round_other_mic", w.stage(train_round(2, 3, mic="phone")), enroll)
        keep(w, "round_bad_clip", w.stage({"mode": "train", "round": 2, "mic": "desktop",
                                           "add": False,
                                           "clips": clips(2) + [b64(tone_wav(200, 0.5))]}),
             enroll)
        keep(w, "round_2_held", w.stage(train_round(2, 12)), enroll)
        keep(w, "round_finish", w.stage(train_round(3, 12, finish=True), spawn=never), enroll)
        keep(w, "training_waiting", S.status(), statuses)
        keep(w, "card_waiting", w.stage(train_round(1, 3)), enroll)

    # The phone is in the middle of its own training.
    with World("both") as w:
        w.stage(train_round(1, 3, mic="phone"))
        keep(w, "phone_session_held", S.status(), statuses)

    with World("both") as w:
        w.stage(train_round(1, 3))
        keep(w, "cancel", w.stage({"mode": "train", "cancel": True}), enroll)
        keep(w, "cancelled", S.status(), statuses)
        keep(w, "cancel_nothing", w.stage({"mode": "train", "cancel": True}), enroll)
        keep(w, "finish_nothing", w.stage({"mode": "train", "round": 1, "mic": "desktop",
                                           "finish": True}), enroll)

    # Approved, with two recordings left out because they did not sound
    # like the rest: round 2, clips 2 and 5 (counted from 1).
    with World("both") as w:
        w.stage(train_round(1, 6))
        w.stage(train_round(2, 6, loud=(1, 4)))
        w.stage(train_round(3, 6, finish=True))
        keep(w, "trained_outliers", S.status(), statuses)

    # "Train more": adds to the print; approved, nothing left out.
    with World("both") as w:
        w.train("desktop")
        keep(w, "add_finish", w.stage(train_round(1, 4, add=True, finish=True)), enroll)
        keep(w, "trained_added", S.status(), statuses)

    # Three people's recordings mixed: most did not sound like one voice,
    # so the training failed and nothing was saved.
    with World("both") as w:
        w.stage(train_round(1, 6, loud=(0, 1), other=(2, 3), finish=True))
        keep(w, "training_failed", S.status(), statuses)

    # The one-shot training every older app sends: one round, one card.
    with World("both") as w:
        keep(w, "legacy_accepted", w.stage({"mic": "desktop", "clips": clips(12)},
                                           spawn=never), enroll)

    # Denied on the card.
    with World("both") as w:
        w.stage(train_round(1, 3, finish=True), gate=denied)
        keep(w, "training_denied", S.status(), statuses)

    # Strictness and private answers.
    with World("both") as w:
        w.train("desktop")
        keep(w, "tighten_already", w.stage({"mode": "strictness", "value": "very_strict"}),
             enroll)
        keep(w, "loosen_strictness", w.stage({"mode": "strictness", "value": "balanced"},
                                             spawn=never), enroll)
        keep(w, "setting_waiting", S.status(), statuses)
        keep(w, "setting_card_waiting", w.stage({"mode": "privacy", "value": "voice_is_enough"}),
             enroll)
    with World("both") as w:
        w.train("desktop")
        w.stage({"mode": "strictness", "value": "balanced"})
        keep(w, "balanced", S.status(), statuses)
        keep(w, "privacy_while_balanced", w.stage({"mode": "privacy",
                                                   "value": "voice_is_enough"}), enroll)
        keep(w, "tighten_strictness", w.stage({"mode": "strictness", "value": "very_strict"}),
             enroll)
        keep(w, "tightened", S.status(), statuses)
    with World("both") as w:
        w.train("desktop")
        keep(w, "loosen_privacy", w.stage({"mode": "privacy", "value": "voice_is_enough"},
                                          spawn=never), enroll)
    with World("both") as w:
        w.train("desktop")
        w.stage({"mode": "privacy", "value": "voice_is_enough"})
        keep(w, "voice_is_enough", S.status(), statuses)
        keep(w, "tighten_privacy", w.stage({"mode": "privacy", "value": "private_on_screen"}),
             enroll)

    # The guided test: 20 sentences, three from someone else (turned away at
    # both settings) and two of 1.7 s (long enough for balanced's 1.5 s, too
    # short for very strict's 2.0 s). And the "asked you to repeat" counts.
    with World("both") as w:
        w.train("desktop")
        body = {"mode": "measure", "mic": "desktop",
                "clips": (clips(15, seconds=2.4) + clips(3, loud=(0, 1, 2), seconds=2.4)
                          + clips(2, seconds=1.7))}
        keep(w, "measure", w.stage(body), enroll)
        for accepted, t in ((False, 100.0), (True, 104.0), (True, 300.0), (True, 400.0),
                            (False, 500.0), (True, 503.0), (True, 700.0), (False, 800.0)):
            V.note_outcome(accepted, "very_strict", "desktop", now=t)
        V.note_outcome(False, "very_strict", "phone", too_short=True, now=900.0)
        keep(w, "measured_and_counted", S.status(), statuses)
        keep(w, "measure_too_many", w.stage({"mode": "measure", "mic": "desktop",
                                             "clips": clips(21, seconds=1.2)}), enroll)
    return statuses, enroll


def voices_cases():
    statuses, posts = {}, {}

    def keep(world, name, value, into):
        into[name] = scrub(value, folders_of(world))

    def post(route, body, **kw):
        fn = VO.ROUTES[route]
        code, out = fn(body, **kw) if kw else VO.handle_post(route, body)
        return {"code": code, "body": out}

    kw = dict(gate=approved, tier_of=ask, spawn=now)

    def voice_body(name, amp=0.9, seconds=5.0,
                   words="The quick brown fox jumps over the lazy dog then runs back home"):
        rate = 24000
        t = np.arange(int(seconds * rate)) / float(rate)
        x = amp * np.sin(2 * np.pi * 170.0 * t)
        return {"name": name, "clip": b64(VO.wav_bytes(x, rate)), "transcript": words}

    # Nothing installed: the built-in voice, no ZipVoice files, one card.
    with World("both") as w:
        keep(w, "builtin_nothing_installed", VO.status(), statuses)

    # A voice added and approved; ZipVoice and Kokoro running (stand-ins).
    with World("both") as w, SCG.World(SCG.SMI["one_card"]):
        w.speaking()
        w.train("phone")
        keep(w, "create_accepted", post("/api/voice/voices/create",
                                        voice_body("Grandpa"), **kw), posts)
        keep(w, "voice_added", VO.status(), statuses)
        vid = posts["create_accepted"]["body"]["voice"]
        keep(w, "create_owner_voice", post("/api/voice/voices/create",
                                           voice_body("Me", amp=0.4), **kw), posts)
        keep(w, "create_words_do_not_fit", post("/api/voice/voices/create",
                                                voice_body("Short", words="Hello"), **kw), posts)
        keep(w, "create_name_taken", post("/api/voice/voices/create",
                                          voice_body("grandpa"), **kw), posts)
        keep(w, "switch_pending", post("/api/voice/voices/active", {"voice": vid},
                                       gate=approved, tier_of=ask, spawn=never), posts)
        keep(w, "switch_waiting", VO.status(), statuses)
        keep(w, "switch_card_waiting", post("/api/voice/voices/create",
                                            voice_body("Aunt May"), **kw), posts)
        keep(w, "builtin", post("/api/voice/voices/active", {"voice": "builtin"}), posts)
        # The switch card is still on screen; approving it now changes
        # nothing (the real decision, answered "approved").
        VO._decide_switch(VO._PENDING["id"], approved, None)
        keep(w, "switch_withdrawn", VO.status(), statuses)
        post("/api/voice/voices/active", {"voice": vid}, **kw)
        S.say("Of course. I have added the dentist to Tuesday at ten.")
        S.say("Done.")
        keep(w, "speaking_custom", VO.status(), statuses)
        keep(w, "already_active", post("/api/voice/voices/active", {"voice": vid}), posts)
        keep(w, "delete", post("/api/voice/voices/delete", {"voice": vid}), posts)
        keep(w, "delete_unknown", post("/api/voice/voices/delete", {"voice": vid}), posts)
        keep(w, "delete_builtin", post("/api/voice/voices/delete", {"voice": "builtin"}), posts)
        keep(w, "after_delete", VO.status(), statuses)
        keep(w, "better_no_card", post("/api/voice/voices/better", {"enabled": True}, **kw),
             posts)
        keep(w, "better_off", post("/api/voice/voices/better", {"enabled": False}), posts)
        # The speaking speed: at once, no card either way.
        keep(w, "speed_faster", post("/api/voice/voices/speed", {"speed": "faster"}), posts)
        keep(w, "speed_chosen", VO.status(), statuses)
        keep(w, "speed_bad", post("/api/voice/voices/speed", {"speed": "warp"}), posts)

    # A custom voice chosen, but ZipVoice's files are not on this PC: the
    # built-in voice speaks, and says why.
    with World("both") as w:
        w.speaking()
        post("/api/voice/voices/create", voice_body("Grandpa"), **kw)
        post("/api/voice/voices/active", {"voice": "grandpa"}, **kw)
        VO.reload()
        S.say("Good morning.")
        keep(w, "fallback", VO.status(), statuses)

    # The owner's two cards: the better voice may be turned on; its card
    # waits, then is approved.
    with World("both") as w, SCG.World(SCG.SMI["2080s_2060"], windows=True):
        keep(w, "better_capable", VO.status(), statuses)
        keep(w, "better_on_pending", post("/api/voice/voices/better", {"enabled": True},
                                          gate=approved, tier_of=ask, spawn=never), posts)
        keep(w, "better_waiting", VO.status(), statuses)
        keep(w, "better_on_again", post("/api/voice/voices/better", {"enabled": True},
                                        gate=approved, tier_of=ask, spawn=never), posts)
    with World("both") as w, SCG.World(SCG.SMI["2080s_2060"], windows=True):
        post("/api/voice/voices/better", {"enabled": True}, **kw)
        keep(w, "better_on", VO.status(), statuses)

    # A voice card denied.
    with World("both") as w:
        post("/api/voice/voices/create", voice_body("Grandpa"), gate=denied, tier_of=ask,
             spawn=now)
        keep(w, "create_denied", VO.status(), statuses)
    return statuses, posts


def render() -> str:
    t_status, t_enroll = training_cases()
    v_status, v_posts = voices_cases()
    body = {
        "_about": ("Real output of the backend for the desktop's voice training, "
                   "settings, guided test and custom voices, made by "
                   "tools/gen_voice_training_cases.py: jarvis_speech.status() under "
                   "`statuses`, jarvis_voice_enroll.stage() under `enroll`, "
                   "jarvis_voices.status() under `voices`, and the voices routes under "
                   "`voice_posts` ({code, body}). The voice-ID models, the speech engines "
                   "and the cards are stand-ins; folders, times and measured seconds are "
                   "made the same on every machine. Do not edit by hand: re-run the tool."),
        "statuses": t_status,
        "enroll": t_enroll,
        "voices": v_status,
        "voice_posts": v_posts,
    }
    return json.dumps(body, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv) -> int:
    text = render()
    if "--check" in argv:
        have = FIXTURE.read_text(encoding="utf-8") if FIXTURE.is_file() else ""
        if have.replace("\r\n", "\n") != text:
            print(f"{FIXTURE.relative_to(ROOT)} is out of date: run "
                  f"python3 tools/gen_voice_training_cases.py")
            return 1
        print("voice-training-cases.json matches the producer.")
        return 0
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {FIXTURE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
