#!/usr/bin/env python3
"""Writes jarvis-client/app/src/test/resources/contract/phone-voice-cases.json:
what the PC REALLY answers for the phone's voice screens, in named cases.

    python3 tools/gen_phone_voice_cases.py            # write the file
    python3 tools/gen_phone_voice_cases.py --check    # compare only

Two halves, both the backend's own code run with the outside world replaced:

  strict   The stricter voice check (docs/JARVIS-API.md section 16).
           GET /api/voice/status is backend/jarvis_speech.status() itself;
           POST /api/voice/enroll's answers are jarvis_voice_enroll.stage()
           itself - training in rounds, "train more", cancel, the two
           settings, the guided repeat test. The voice prints are made by the
           real jarvis_voice.enroll().
  voices   Custom voices (section 15). GET /api/voice/voices is
           backend/jarvis_voices.status(); the POST answers are its create(),
           switch(), delete() and set_better(). The "sounds like you"
           refusal is the real owner_check() against a print the real
           jarvis_voice.enroll() made from the same voice.

WHAT IS A STAND-IN. The two speaker models (a stand-in that turns a tone
into a fixed vector, under the names of the two models whose bars were
measured - so the bars, the notes and the labels are the real ones), the
ZipVoice and Kokoro engines (a quiet tone of the right length), the second
graphics card's detection, and the approval card (answered at once, or held
by never starting its thread). Every answer and every status is otherwise
the module's own.

WHAT IS CHANGED AFTER THE RUN, and only this, so the file is the same on
every machine: the temporary folder becomes `~/.openjarvis`, moments in time
become one fixed number, seconds left on a card become 170, and how long a
say() took (a measured time) becomes 0.5 s.

Nothing in the file is written by hand. Re-run this after changing any of
the modules above; `--check` fails when the committed file is stale.
"""
import array
import base64
import io
import json
import math
import os
import sys
import tempfile
import types
import wave
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
FIXTURE = (ROOT / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract"
           / "phone-voice-cases.json")
for p in (BACKEND, BACKEND / "rebuilt"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import numpy as np  # noqa: E402
import jarvis_speech as S  # noqa: E402
import jarvis_turn as T  # noqa: E402
import jarvis_voice as V  # noqa: E402
import jarvis_voice_enroll as E  # noqa: E402
import jarvis_voices as VS  # noqa: E402
import jarvis_wakeword as W  # noqa: E402

FIXED_TIME = 1790000000.0
FIXED_EXPIRES_IN = 170
FIXED_TOOK = 0.5
HOME_WORDS = "~/.openjarvis"

#: The two models whose bars were measured (jarvis_voice.MODEL_BARS).
SMALL_NAME = "sherpa-onnx:357a834f702b"
STRONG_NAME = "sherpa-onnx:d51abcf31717"


def unit(v):
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v]


OWNER = unit([1.0, 0.2, 0.0, 0.0, 0.1, 0.0, 0.0, 0.0])
STRANGER = unit([0.0, 0.0, 1.0, 0.0, 0.0, 0.3, 0.0, 0.0])
THIRD = unit([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.4])


def tone_wav(freq: float, seconds: float = 2.5, rate: int = 16000, amp: float = 0.4) -> bytes:
    n = int(seconds * rate)
    s = array.array("h", [int(amp * 32767 * math.sin(2 * math.pi * freq * i / rate))
                          for i in range(n)])
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(s.tobytes())
    return b.getvalue()


def b64(clips):
    return [base64.b64encode(c).decode() for c in clips]


class Speaker(V.Embedder):
    """A stand-in speaker model: a tone under 600 Hz is the owner (a little
    different for each pitch, so the owner's clips are alike but not the
    same), up to 2 kHz somebody else, and higher a third person."""
    semantic = True
    dim = 8

    def __init__(self, name):
        self.name = name

    def embed(self, audio):
        x = V._pcm(audio)[:8000]
        if len(x) < 2:
            return []
        zc = sum(1 for a, b in zip(x, x[1:]) if (a < 0) != (b < 0))
        f = zc / 2.0 / (len(x) / 16000.0)
        base = OWNER if f < 600 else STRANGER if f < 2000 else THIRD
        return unit([b + 0.03 * math.sin(f * (k + 1) / 50.0) for k, b in enumerate(base)])


class Verdict:
    def __init__(self, outcome="approved", tier="ask"):
        self.tier, self.outcome = tier, outcome
        self.allowed = outcome == "approved"
        self.request_id, self.reason = "rq-1", outcome


def gate(outcome="approved"):
    return lambda action, detail, prompt: Verdict(outcome)


def run_now(fn):
    fn()


def never(fn):
    """A card raised and never answered: its thread is not started."""


def ask(_a):
    return "ask"


# --------------------------------------------------------------- the world --

class World:
    """A temporary config folder for every voice module, with `models`
    ("none", "small" or "both") speaker models standing in."""

    def __init__(self, models="both"):
        self.models = models

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.dir = d
        profile = d / "voice" / "owner.json"
        profile.parent.mkdir(parents=True)
        self.small = Speaker(SMALL_NAME)
        self.strong = Speaker(STRONG_NAME) if self.models == "both" else None
        ps = [
            mock.patch.object(S, "_config_dir", return_value=d),
            mock.patch.object(V, "PROFILE_PATH", profile),
            mock.patch.object(W, "model_dir", return_value=d / "voice-models" / "wakeword"),
            mock.patch.object(T, "model_path", return_value=d / "voice-models" / "turn" / T.MODEL_FILE),
            mock.patch.object(E, "_audit", lambda *a: None),
            mock.patch.object(E, "_timeout", lambda: 180.0),
            mock.patch.object(VS, "_config_dir", lambda: d),
            mock.patch.object(VS, "_cfg", lambda k, default=None: default),
            mock.patch.object(VS, "_audit", lambda *a: None),
            mock.patch.object(VS, "_publish", lambda *a: None),
            mock.patch.object(VS, "_start_reaper", lambda: None),
            mock.patch.object(VS, "_timeout", lambda: 180.0),
            mock.patch.object(VS, "_second_card", lambda: {
                "capable": False, "why": "only one graphics card found (the NVIDIA GeForce "
                                         "RTX 2080 SUPER)",
                "uuid": None, "name": None, "free_mb": None, "big_model": None}),
        ]
        if self.models != "none":
            small, strong = self.small, self.strong
            ps.append(mock.patch.object(V, "EcapaEmbedder", lambda: small))
            ps.append(mock.patch.object(V, "strong_embedder", lambda *a: strong))
        self.patches = ps
        for p in ps:
            p.start()
        S.reload_engines()
        E._reset_for_tests()
        S._reset_wake_for_tests()
        V._reset_repeat_for_tests()
        VS._reset_for_tests()
        with S._TIMINGS_LOCK:
            S._TIMINGS.clear()
        return self

    def __exit__(self, *a):
        for p in reversed(self.patches):
            p.stop()
        E._reset_for_tests()
        VS._reset_for_tests()
        S._reset_wake_for_tests()
        with S._TIMINGS_LOCK:
            S._TIMINGS.clear()
        self.tmp.cleanup()
        S.reload_engines()


def post(body: dict, g=None, spawn=run_now, **kw):
    """POST /api/voice/enroll through the real stage()."""
    return E.stage(json.dumps(body).encode(), gate=g or gate(), tier_of=ask, spawn=spawn, **kw)


def owner_round(n: int, count: int = 12, odd=()):
    """`count` of the owner's sentences for round `n`; clip numbers in `odd`
    (from 1) are somebody else's, so enrolment leaves them out."""
    return [tone_wav(900.0 + 40 * i if i + 1 in odd else 150.0 + 11 * n + 7 * i, 2.5)
            for i in range(count)]


def train(rounds: dict, add=False, g=None, spawn=run_now):
    """Sends rounds {n: clips} the way the phone does - held, then finish on
    the last - and returns every answer."""
    out = []
    keys = sorted(rounds)
    for n in keys:
        body = {"mode": "train", "round": n, "mic": "phone", "add": add,
                "clips": b64(rounds[n])}
        if n == keys[-1]:
            body["finish"] = True
        out.append(post(body, g=g, spawn=spawn,
                        wake_check=lambda c, m, keep_old=False: "not built: no wake-word model"))
    return out


def answer(code_body):
    code, body = code_body
    return {"status": code, "body": body}


# ------------------------------------------------------------- scrubbing --

TIME_KEYS = ("created", "at", "since", "changed")


def scrub(value, world):
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if k in TIME_KEYS and isinstance(v, (int, float)) and not isinstance(v, bool) and v:
                out[k] = FIXED_TIME
            elif k == "expires_in" and isinstance(v, int):
                out[k] = FIXED_EXPIRES_IN
            elif k in ("seconds", "rtf") and "engine" in value and isinstance(v, float):
                # A say() timing row: how long it took is a measured time.
                out[k] = FIXED_TOOK if k == "seconds" else (
                    round(FIXED_TOOK / value["audio_seconds"], 3) if value.get("audio_seconds") else None)
            else:
                out[k] = scrub(v, world)
        return out
    if isinstance(value, list):
        return [scrub(v, world) for v in value]
    if isinstance(value, str):
        named = False
        # This run's temporary folder, and the real config folder - which
        # backend/run_suites.py points somewhere temporary too.
        folders = {str(world.dir), str(Path.home() / ".openjarvis")}
        for key in ("OPENJARVIS_CONFIG_DIR", "JARVIS_CONFIG_DIR"):
            if os.environ.get(key):
                folders.add(os.environ[key])
        try:
            folders.add(str(V._profile_dir().parent))
        except Exception:
            pass
        for folder in sorted((f for f in folders if f), key=len, reverse=True):
            if folder in value:
                value = value.replace(folder, HOME_WORDS)
                named = True
        return value.replace("\\", "/") if named else value
    return value


# ---------------------------------------------------------------- strict --

def strict_cases():
    status, answers = {}, {}

    with World("none") as w:
        status["no_model"] = scrub(S.status(), w)
        answers["train_needs_model"] = scrub(answer(post(
            {"mode": "train", "round": 1, "mic": "phone", "clips": b64(owner_round(1, 3))})), w)

    with World("small") as w:
        train({1: owner_round(1)})
        status["small_model_only"] = scrub(S.status(), w)

    with World("both") as w:
        status["strong_untrained"] = scrub(S.status(), w)
        # Round 1 held: no card, nothing changed.
        answers["train_round_held"] = scrub(answer(post(
            {"mode": "train", "round": 1, "mic": "phone", "add": False,
             "clips": b64(owner_round(1))})), w)
        status["round_held"] = scrub(S.status(), w)
        answers["train_other_session"] = scrub(answer(post(
            {"mode": "train", "round": 1, "mic": "phone", "add": True,
             "clips": b64(owner_round(1, 3))})), w)
        answers["train_bad_clip"] = scrub(answer(post(
            {"mode": "train", "round": 2, "mic": "phone", "add": False,
             "clips": b64([tone_wav(200.0, 0.5)] * 3)})), w)
        answers["train_cancel"] = scrub(answer(post({"mode": "train", "cancel": True})), w)
        answers["train_cancel_nothing"] = scrub(answer(post({"mode": "train", "cancel": True})), w)
        status["cancelled"] = scrub(S.status(), w)
        answers["train_finish_nothing"] = scrub(answer(post(
            {"mode": "train", "round": 3, "mic": "phone", "finish": True})), w)

        # Extended training: three rounds, one card, approved at once. One
        # clip in round 2 (clip 5) is somebody else's, so it is left out.
        got = train({1: owner_round(1), 2: owner_round(2, odd=(5,)), 3: owner_round(3)})
        answers["train_round2_held"] = scrub(answer(got[1]), w)
        answers["train_finish"] = scrub(answer(got[2]), w)
        status["trained_three_rounds"] = scrub(S.status(), w)

        # "Train more": one round, added to the print.
        got = train({2: owner_round(2, count=3)}, add=True)
        answers["train_more_finish"] = scrub(answer(got[0]), w)
        status["trained_more"] = scrub(S.status(), w)

        # The guided repeat test: 20 of the owner's sentences, some short,
        # a few that do not sound like the owner.
        clips = ([tone_wav(160.0 + 3 * i, 2.6) for i in range(14)]
                 + [tone_wav(170.0 + 3 * i, 1.7) for i in range(3)]
                 + [tone_wav(950.0 + 20 * i, 2.6) for i in range(3)])
        with mock.patch.object(E, "_speech_seconds", lambda pcm: len(pcm) / 2 / 16000.0):
            answers["measure"] = scrub(answer(post(
                {"mode": "measure", "mic": "phone", "clips": b64(clips)})), w)
        status["measured"] = scrub(S.status(), w)
        answers["measure_too_many"] = scrub(answer(post(
            {"mode": "measure", "mic": "phone", "clips": b64([tone_wav(160.0)] * 21)})), w)

        # The two settings.
        answers["strictness_same"] = scrub(answer(post(
            {"mode": "strictness", "value": "very_strict"})), w)
        answers["privacy_loosen"] = scrub(answer(post(
            {"mode": "privacy", "value": "voice_is_enough"}, spawn=never)), w)
        status["setting_waiting"] = scrub(S.status(), w)
        answers["setting_card_waiting"] = scrub(answer(post(
            {"mode": "strictness", "value": "balanced"}, spawn=never)), w)
        answers["train_card_waiting"] = scrub(answer(post(
            {"mode": "train", "round": 1, "mic": "phone", "clips": b64(owner_round(1, 3))})), w)
        # Tightening while that card waits: at once, and the card is withdrawn.
        answers["privacy_tighten"] = scrub(answer(post(
            {"mode": "privacy", "value": "private_on_screen"})), w)
        E._reset_for_tests()
        answers["privacy_loosen_approved"] = scrub(answer(post(
            {"mode": "privacy", "value": "voice_is_enough"})), w)
        status["voice_is_enough"] = scrub(S.status(), w)
        answers["strictness_loosen"] = scrub(answer(post(
            {"mode": "strictness", "value": "balanced"})), w)
        status["balanced"] = scrub(S.status(), w)
        answers["privacy_while_balanced"] = scrub(answer(post(
            {"mode": "privacy", "value": "voice_is_enough"})), w)
        answers["strictness_tighten"] = scrub(answer(post(
            {"mode": "strictness", "value": "very_strict"})), w)
        answers["strictness_loosen_denied"] = scrub(answer(post(
            {"mode": "strictness", "value": "balanced"}, g=gate("denied"))), w)
        status["loosen_denied"] = scrub(S.status(), w)

    with World("both") as w:
        # The card for three rounds, raised and not answered yet.
        got = train({1: owner_round(1), 2: owner_round(2), 3: owner_round(3)}, spawn=never)
        answers["train_finish_waiting"] = scrub(answer(got[2]), w)
        status["training_card_waiting"] = scrub(S.status(), w)

    with World("both") as w:
        # Most clips unlike the rest (three people): the enrolment fails,
        # and says which clips.
        clips = ([tone_wav(160.0 + 5 * i, 2.5) for i in range(2)]
                 + [tone_wav(900.0 + 40 * i, 2.5) for i in range(2)]
                 + [tone_wav(3000.0 + 90 * i, 2.5) for i in range(2)])
        train({1: clips})
        status["failed_outliers"] = scrub(S.status(), w)

    return status, answers


# ---------------------------------------------------------------- voices --

WORDS = VS.SENTENCES[1]


class FakeZip:
    def generate(self, text, prompt_text, prompt_samples, sample_rate, speed, steps):
        n = int(24000 * max(0.5, len(text) / 15.0))
        return types.SimpleNamespace(samples=(0.1 * np.ones(n)).astype(np.float32),
                                     sample_rate=24000)


class FakeKokoro:
    def generate(self, text, sid=0, speed=1.0):
        return types.SimpleNamespace(samples=(0.05 * np.ones(24000)).astype(np.float32),
                                     sample_rate=24000)


def voice_clip(f0=150.0, seconds=5.0, rate=24000):
    t = np.arange(int(seconds * rate)) / float(rate)
    x = 0.3 * (np.sin(2 * np.pi * f0 * t) + 0.5 * np.sin(2 * np.pi * 2.3 * f0 * t))
    pad = np.zeros(int(0.5 * rate))
    y = np.concatenate([pad, x / 1.5, pad])
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wv:
        wv.setnchannels(1)
        wv.setsampwidth(2)
        wv.setframerate(rate)
        wv.writeframes((np.clip(y, -1, 1) * 32767).astype("<i2").tobytes())
    return buf.getvalue()


def create_body(name="Grandpa", words=WORDS, clip=None):
    return {"name": name, "clip": base64.b64encode(clip or voice_clip()).decode(),
            "transcript": words}


NOT_OWNER = None


def not_owner(samples):
    return {"ok": True, "checked": 1, "why": "it does not sound like your voice (its closest "
                                             "score was 0.12; 0.40 or more is refused)",
            "fingerprint": VS.prints_fingerprint(), "score": 0.12, "bar": 0.4}


CAPABLE = {"capable": True, "why": "", "uuid": "GPU-8b7e2d44-1c9a-4f3e-a2b6-5e9d0c7f1a23",
           "name": "NVIDIA GeForce RTX 2060", "free_mb": 11000, "big_model": None}


class VoicesWorld(World):
    def __init__(self, zipvoice=True):
        super().__init__("none")
        self.zipvoice = zipvoice

    def __enter__(self):
        super().__enter__()
        if self.zipvoice:
            VS._ZIP.update(engine=FakeZip(), why="ready", built=True)
        else:
            VS._ZIP.update(engine=None, built=True,
                           why="ZipVoice could not be loaded (RuntimeError)")
        # The built-in voice's files, as jarvis_speech checks them.
        self.kokoro = [mock.patch.object(S, "_tts_cache", FakeKokoro()),
                       mock.patch.object(S, "sherpa_onnx", S.sherpa_onnx or object()),
                       mock.patch.object(S, "_files_present", lambda *a: True)]
        for p in self.kokoro:
            p.start()
        return self

    def __exit__(self, *a):
        for p in reversed(self.kokoro):
            p.stop()
        super().__exit__(*a)


def vpost(fn, body, g=None, spawn=run_now, check=not_owner):
    kw = {"gate": g or gate(), "tier_of": ask, "spawn": spawn}
    if fn in (VS.create, VS.switch):
        kw["check"] = check
    if fn is VS.delete:
        return fn(body)
    return fn(body, **kw)


def voices_cases():
    status, answers = {}, {}

    with VoicesWorld() as w:
        status["empty"] = scrub(VS.status(), w)
        answers["create"] = scrub(answer(vpost(VS.create, create_body())), w)
        status["one_voice"] = scrub(VS.status(), w)
        answers["create_name_taken"] = scrub(answer(vpost(VS.create, create_body())), w)
        answers["create_words_do_not_fit"] = scrub(answer(vpost(
            VS.create, create_body("Aunt May", words="Hi"))), w)
        answers["create_too_short"] = scrub(answer(vpost(
            VS.create, create_body("Aunt May", words="Hello there", clip=voice_clip(seconds=1.5)))), w)
        vid = "grandpa"
        answers["active_custom"] = scrub(answer(vpost(VS.switch, {"voice": vid})), w)
        answers["active_already"] = scrub(answer(vpost(VS.switch, {"voice": vid})), w)
        S.say("Of course. I have added the dentist to Tuesday at ten.")
        status["speaking_custom"] = scrub(VS.status(), w)
        answers["active_builtin"] = scrub(answer(vpost(VS.switch, {"voice": "builtin"})), w)
        answers["active_unknown"] = scrub(answer(vpost(VS.switch, {"voice": "nobody"})), w)
        # A card raised and not answered yet.
        answers["create_waiting"] = scrub(answer(vpost(
            VS.create, create_body("Aunt May"), spawn=never)), w)
        status["create_waiting"] = scrub(VS.status(), w)
        answers["create_card_waiting"] = scrub(answer(vpost(
            VS.create, create_body("Uncle Bob"), spawn=never)), w)
        VS._reset_for_tests()
        VS._ZIP.update(engine=FakeZip(), why="ready", built=True)
        vpost(VS.create, create_body("Aunt May"), g=gate("denied"))
        status["last_denied"] = scrub(VS.status(), w)
        answers["delete"] = scrub(answer(vpost(VS.delete, {"voice": vid})), w)
        answers["delete_builtin"] = scrub(answer(vpost(VS.delete, {"voice": "builtin"})), w)
        answers["delete_unknown"] = scrub(answer(vpost(VS.delete, {"voice": vid})), w)
        # The better voice without a capable second card.
        answers["better_no_card"] = scrub(answer(vpost(VS.set_better, {"enabled": True})), w)
        answers["better_off"] = scrub(answer(vpost(VS.set_better, {"enabled": False})), w)
        with mock.patch.object(VS, "_second_card", lambda: dict(CAPABLE)):
            status["better_can_turn_on"] = scrub(VS.status(), w)
            answers["better_on"] = scrub(answer(vpost(VS.set_better, {"enabled": True},
                                                      spawn=never)), w)
            status["better_waiting"] = scrub(VS.status(), w)
            answers["better_waiting"] = scrub(answer(vpost(VS.set_better, {"enabled": True},
                                                           spawn=never)), w)
            vpost(VS.set_better, {"enabled": False})
            vpost(VS.set_better, {"enabled": True})
            status["better_on"] = scrub(VS.status(), w)

    with VoicesWorld(zipvoice=False) as w:
        vpost(VS.create, create_body())
        vpost(VS.switch, {"voice": "grandpa"})
        S.say("Hello there, this is a test.")
        status["fallback"] = scrub(VS.status(), w)
        # A folder with no recording in it.
        (VS.voices_dir() / "broken").mkdir(parents=True)
        status["broken_folder"] = scrub(VS.status(), w)

    with VoicesWorld() as w:
        # The owner's own voice, refused through the real voice check: a
        # print made by jarvis_voice.enroll() (the basic check - no model is
        # installed here) from the same person, then offered as a voice.
        owner = np.frombuffer(voice_clip(130.0, 8.0, 16000)[44:], dtype="<i2")
        clips = [owner[(i + 1) * 16000:(i + 4) * 16000].tobytes() for i in range(3)]
        V.enroll(clips, embedder=VS._embedder(V), sample_rate=16000, mic="phone")
        answers["create_owner_voice"] = scrub(answer(VS.create(
            create_body("Me", clip=voice_clip(130.0, 5.0)), gate=gate(), tier_of=ask,
            spawn=run_now)), w)

    return status, answers


def render() -> str:
    s_status, s_answers = strict_cases()
    v_status, v_answers = voices_cases()
    body = {
        "_about": ("Real output of the backend's voice modules for the phone's voice screens, "
                   "made by tools/gen_phone_voice_cases.py: strict.status = "
                   "jarvis_speech.status() (GET /api/voice/status), strict.answers = "
                   "jarvis_voice_enroll.stage() (POST /api/voice/enroll), voices.status = "
                   "jarvis_voices.status() (GET /api/voice/voices), voices.answers = its "
                   "create/switch/delete/set_better (the POST routes). Speaker models, speech "
                   "engines, the second card and the approval card are stand-ins. Folders, "
                   "times and measured durations are made the same on every machine. Do not "
                   "edit by hand: re-run the tool."),
        "strict": {"status": s_status, "answers": s_answers},
        "voices": {"status": v_status, "answers": v_answers},
    }
    return json.dumps(body, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv) -> int:
    text = render()
    if "--check" in argv:
        have = FIXTURE.read_text(encoding="utf-8") if FIXTURE.is_file() else ""
        if have.replace("\r\n", "\n") != text:
            print(f"{FIXTURE.relative_to(ROOT)} is out of date: run "
                  f"python3 tools/gen_phone_voice_cases.py")
            return 1
        print("phone-voice-cases.json matches the producer.")
        return 0
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {FIXTURE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
