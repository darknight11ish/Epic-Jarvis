"""The stricter owner-only voice check (2026-09-24).

    python3 test_voice_strict.py

No pytest, no network, no microphone. The speaker models are stand-ins that
return chosen vectors (so every number here is one the test picked); the
voice print, the settings, the staging and the cards are the REAL
jarvis_voice / jarvis_voice_enroll / jarvis_speech code, writing into a
temporary folder.

What it proves:
  1. HOLE 1: with only the basic (spectral) check, owner mode lets nobody
     in - verify(), hear(), the talk button and a training all say
     "install the voice-ID model". (Before the fix it answered
     is_owner=True for a close enough clip.)
  2. HOLE 2: one noisy training clip no longer drags the bar down. The bar
     never goes below the model's floor - not by enrolment, not by a card -
     and the odd clip is left out and reported, so the app can ask for it
     again. (Before the fix the bar fell to 0.05 and a stranger passed.)
  3. The two settings: strict by default; tightening is immediate;
     loosening needs a card, and deny / timeout / wrong tier change
     nothing; voice_is_enough only while very strict; choosing balanced
     puts private answers back on screen; tightening withdraws a waiting
     loosening card.
  4. may_speak(): private answers are not read aloud for a voice request
     unless the owner chose voice_is_enough.
  5. Very strict = BOTH models must pass; balanced = the small one alone;
     the strong model not installed = one model, and status says so; a
     print made before the strong model = "train again".
  6. Comparison voices (AS-norm): the maths against a hand computation, a
     "hub" voice that clears the raw bar but is refused, the bank's
     round trip, and that the bank can only ever refuse more, never less.
  7. Training in rounds: held with no card, ONE card at the end, every
     held clip dropped on deny, timeout, cancel, expiry.
  8. Sub-prints, one per condition: the nearest decides; "train more" ADDS.
  9. The repeat counters: a refusal and an acceptance within 10 s.
 10. The guided repeat test and the "someone else" check.
 11. The minimum command length, and "hey Jarvis" alone as the wake path.
 12. No audio is written to disk: every file a whole session wrote is
     scanned for the clips' bytes.
 13. With the real model files (JARVIS_TEST_SPEAKER_MODEL and
     JARVIS_TEST_STRONG_MODEL, only where they exist): both load, their
     bars are the measured ones, and a check asks both.
"""
import array
import base64
import io
import json
import math
import os
import random
import sys
import tempfile
import threading
import traceback
import wave
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

sys.path.insert(0, str(HERE / "rebuilt"))
sys.path.insert(0, str(HERE))
require_shipped("jarvis_voice_enroll.py", "jarvis_speech.py", "rebuilt/jarvis_voice.py")
import jarvis_voice as V  # noqa: E402
import jarvis_voice_enroll as E  # noqa: E402
import jarvis_speech as S  # noqa: E402

FAILED, PASSED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def skip(name, why):
    SKIPPED.append(name)
    print(f"skip  {name} - {why}")


# ---------------------------------------------------------------- helpers --

class Table(V.Embedder):
    """A speaker model that returns the vector the test chose for each clip.
    A clip is any hashable token (or real audio, for the hear() tests: then
    the first sample decides which vector)."""
    semantic = True

    def __init__(self, name, table):
        self.name, self.table = name, dict(table)

    def embed(self, audio):
        key = audio if isinstance(audio, (str, int, tuple)) else _tag(audio)
        return list(self.table.get(key, []))


def _tag(audio):
    """hear()'s clips: a loud tone is the owner, a quiet one a stranger
    (see _clip)."""
    x = V._pcm(audio)
    if not x:
        return None
    return "loud" if max(abs(v) for v in x[:4000]) > 0.5 else "quiet"


def unit(v):
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v]


def near(v, noise, rng):
    return unit([x + rng.gauss(0, noise) for x in v])


class Verdict:
    def __init__(self, allowed, tier="ask", outcome=None, rid="req-1", reason=""):
        self.allowed, self.tier, self.outcome = allowed, tier, outcome
        self.request_id, self.reason = rid, reason


class Gate:
    def __init__(self, verdict):
        self.verdict, self.calls = verdict, []

    def __call__(self, action, detail, prompt):
        self.calls.append((action, detail, prompt))
        return self.verdict


class HeldGate(Gate):
    def __init__(self, verdict):
        super().__init__(verdict)
        self.release, self.asked = threading.Event(), threading.Event()

    def __call__(self, action, detail, prompt):
        self.calls.append((action, detail, prompt))
        self.asked.set()
        self.release.wait(10)
        return self.verdict


def run_sync(fn):
    fn()


def ask(_a):
    return "ask"


def wav(seconds=2.0, freq=180.0, amp=0.4, rate=16000) -> bytes:
    n = int(seconds * rate)
    s = array.array("h", [int(amp * 32767 * (0.6 * math.sin(2 * math.pi * freq * i / rate)
                                             + 0.3 * math.sin(4 * math.pi * freq * i / rate)))
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


class Temp:
    """A fresh folder for the prints, the settings and the banks."""

    def __enter__(self):
        self.keep = V.PROFILE_PATH
        self.dir = Path(tempfile.mkdtemp(prefix="jarvis-strict-"))
        V.PROFILE_PATH = self.dir / "owner.json"
        E._reset_for_tests()
        V._reset_repeat_for_tests()
        with V._BANKS_LOCK:
            V._BANKS.clear()
        return self

    def __exit__(self, *a):
        V.PROFILE_PATH = self.keep
        E._reset_for_tests()
        with V._BANKS_LOCK:
            V._BANKS.clear()


OWNER = unit([1.0, 0.2, 0.0, 0.0, 0.1, 0.0, 0.0, 0.0])
FAR = unit([0.3, 1.0, 0.0, 0.2, 0.0, 0.0, 0.0, 0.0])        # the owner, far from the mic
STRANGER = unit([0.0, 0.0, 1.0, 0.0, 0.0, 0.3, 0.0, 0.0])


# ------------------------------------------------------------ 1. hole one --

def t_hole_one_the_basic_check_lets_nobody_in():
    with Temp():
        emb = V.Embedder()
        clips = [wav(2.0, 180 + i) for i in range(3)]
        pcm = [E._read_clip(1, c)[0] for c in clips]
        V.enroll(pcm, embedder=emb, sample_rate=16000)
        v = V.verify(E._read_clip(1, wav(2.0, 181))[0], emb, sample_rate=16000, strong=False)
        check("owner mode, basic check: the owner's own voice is refused",
              not v.is_owner, v)
        check("...with the plain reason: install the voice-ID model",
              "install the voice-ID model" in v.reason, v.reason)
        with mock.patch.object(V, "_cfg", lambda k, d=None: "broad" if k == "mode" else d):
            check("broad mode (the owner's explicit choice) is unchanged",
                  V.verify(b"x", emb).is_owner)
        st = S.status()
        check("the talk button is hidden, and says to install the model",
              st["listening"]["push_to_talk"] is False
              and "voice-ID model" in st["listening"]["push_to_talk_why"], st["listening"])
        code, out = E.stage(json.dumps({"clips": b64([wav(2.0, 180 + i) for i in range(3)])}).encode(),
                            gate=Gate(Verdict(True, outcome="approved")), tier_of=ask,
                            spawn=run_sync)
        check("a training is refused before any card, saying why",
              code == 409 and out.get("needs_model") and "voice-ID model" in out["error"]
              and E._PENDING is None, (code, out))


# ------------------------------------------------------------ 2. hole two --

def t_hole_two_one_noisy_clip():
    with Temp():
        good = [unit([1.0, 0.0, 0.0]), unit([0.98, 0.1, 0.0]), unit([0.97, 0.0, 0.1]),
                unit([0.99, 0.05, 0.05])]
        outlier = unit([-0.3, 0.2, 0.93])
        emb = Table("sherpa-onnx:357a834f702b", {i: v for i, v in enumerate(good + [outlier])})
        prof = V.enroll(list(range(5)), embedder=emb)
        floor = V.floor_for(emb.name, V.BALANCED)
        check("the bar is not lowered to fit the noisy clip (the old code: 0.05)",
              prof.threshold >= floor and prof.threshold >= 0.35, prof.threshold)
        check("the noisy clip is left out, and reported by number", prof.outliers == [4],
              prof.outliers)
        check("it is not in the print", prof.samples == 4, prof.samples)
        stranger = unit([0.35, 0.5, 0.79])
        emb.table["stranger"] = stranger
        v = V.verify("stranger", emb, strong=False)
        check("a stranger who passed the old, lowered bar is refused", not v.is_owner, v)

        bad = Table("sherpa-onnx:357a834f702b",
                    {0: good[0], 1: unit([0, 1, 0]), 2: unit([0, 0, 1]), 3: unit([0, -1, 0])})
        try:
            V.enroll([0, 1, 2, 3], embedder=bad, path=V.PROFILE_PATH.with_name("x.json"))
            check("mostly odd clips: refused, not saved", False)
        except V.EnrolError as exc:
            check("mostly odd clips: refused, not saved, and the odd ones named",
                  exc.outliers and "did not sound like the same voice" in str(exc)
                  and not V.PROFILE_PATH.with_name("x.json").exists(), (exc, exc.outliers))

        try:
            V.set_threshold(floor - 0.1)
            check("a card cannot set a bar under the floor either", False)
        except ValueError as exc:
            check("a card cannot set a bar under the floor either", "lowest" in str(exc), exc)
        gate = Gate(Verdict(True, outcome="approved"))
        code, out = E.stage(json.dumps({"mode": "threshold", "threshold": 0.1}).encode(),
                            gate=gate, tier_of=ask, spawn=run_sync)
        check("...and the route says so before any card",
              code == 400 and not gate.calls and "lowest" in out["error"], (code, out))
        with mock.patch.object(V, "_cfg", lambda k, d=None: 0.05 if k == "threshold" else d):
            p2 = V.enroll(list(range(4)), embedder=emb, path=V.PROFILE_PATH.with_name("y.json"))
        check("a config bar under the floor is raised to the floor",
              p2.threshold == floor, p2.threshold)


# ------------------------------------------------------------ 3. settings --

def _setting(mode, value, verdict=None, tier="ask", gate=None):
    gate = gate or Gate(verdict or Verdict(True, outcome="approved"))
    code, out = E.stage(json.dumps({"mode": mode, "value": value}).encode(),
                        gate=gate, tier_of=lambda a: tier, spawn=run_sync)
    return code, out, gate


def t_settings_tighten_now_loosen_with_a_card():
    with Temp():
        s = V.settings()
        check("defaults: very strict, private answers on screen",
              s["strictness"] == "very_strict" and s["privacy"] == "private_on_screen", s)
        V.settings_path().write_text("{not json", encoding="utf-8")
        check("an unreadable settings file means the strict defaults",
              V.settings()["strictness"] == "very_strict")
        V.settings_path().write_text(json.dumps({"strictness": "balanced",
                                                 "privacy": "voice_is_enough"}))
        check("a file saying balanced + voice_is_enough is read as private_on_screen",
              V.settings()["privacy"] == "private_on_screen")
        V.settings_path().unlink()

        for outcome, verdict in (("denied", Verdict(False, outcome="denied")),
                                 ("timed_out", Verdict(False, outcome="timed_out")),
                                 ("refused", Verdict(True, tier="auto", outcome="approved"))):
            E._reset_for_tests()
            code, out, gate = _setting("strictness", "balanced", verdict)
            check(f"loosening raises ONE card; {outcome}: nothing changes",
                  code == 202 and len(gate.calls) == 1
                  and gate.calls[0][0] == "change_own_config"
                  and V.settings()["strictness"] == "very_strict"
                  and E.state()["last"]["outcome"] == outcome, (code, out, E.state().get("last")))
        E._reset_for_tests()
        code, out, gate = _setting("strictness", "balanced", tier="notify")
        check("tier not 'ask': 409, no card", code == 409 and not gate.calls, (code, out))
        E._reset_for_tests()
        code, out, gate = _setting("strictness", "balanced")
        card = gate.calls[0][2]
        check("the card says what it costs, both ways, and that private answers go on screen",
              "less strict" in card and "If you say no" in card and "on screen" in card, card)
        check("approved: balanced", V.settings()["strictness"] == "balanced"
              and E.state()["last"]["outcome"] == "setting_changed")

        E._reset_for_tests()
        code, out, gate = _setting("privacy", "voice_is_enough")
        check("voice_is_enough while balanced: refused, no card",
              code == 409 and not gate.calls and "very strict" in out["error"], (code, out))
        try:
            V.set_setting("privacy", "voice_is_enough", approved=True)
            check("...and refused by jarvis_voice itself, card or not", False)
        except ValueError:
            check("...and refused by jarvis_voice itself, card or not", True)

        E._reset_for_tests()
        code, out, gate = _setting("strictness", "very_strict")
        check("tightening is immediate: 200, no card",
              code == 200 and not gate.calls and V.settings()["strictness"] == "very_strict",
              (code, out))
        E._reset_for_tests()
        code, out, gate = _setting("privacy", "voice_is_enough")
        check("voice_is_enough while very strict: a card, then on",
              code == 202 and gate.calls and V.settings()["privacy"] == "voice_is_enough",
              (code, out))
        E._reset_for_tests()
        _setting("strictness", "balanced")
        check("choosing balanced puts private answers back on screen",
              V.settings() ["privacy"] == "private_on_screen"
              and V.settings()["strictness"] == "balanced", V.settings())
        try:
            V.set_setting("strictness", "balanced")
            V.set_setting("strictness", "very_strict")
            V.set_setting("strictness", "balanced")
            check("loosening without approved=True is refused in jarvis_voice", False)
        except ValueError as exc:
            check("loosening without approved=True is refused in jarvis_voice",
                  "approval card" in str(exc), exc)

        # Tightening while a loosening card waits withdraws it.
        E._reset_for_tests()
        V.set_setting("strictness", "very_strict")
        held = HeldGate(Verdict(True, outcome="approved"))
        code, out = E.stage(json.dumps({"mode": "strictness", "value": "balanced"}).encode(),
                            gate=held, tier_of=ask)
        held.asked.wait(5)
        code2, out2, g2 = _setting("strictness", "very_strict")
        check("tightening while a loosening card waits: at once, no second card",
              code == 202 and code2 == 200 and not g2.calls, (code, code2, out2))
        held.release.set()
        for _ in range(100):
            if not E.state()["pending"]:
                break
            threading.Event().wait(0.05)
        check("...and approving the old card afterwards does nothing",
              V.settings()["strictness"] == "very_strict"
              and E.state()["last"]["outcome"] == "withdrawn", E.state().get("last"))
        st = S.status()["gate"]
        check("status carries both settings and the rule",
              st["strictness"] == "very_strict" and st["privacy"] == "private_on_screen"
              and st["settings"]["voice_is_enough_allowed"] is True
              and st["settings"]["min_command_seconds"] == V.MIN_COMMAND_SECONDS["very_strict"],
              st.get("settings"))
        check("the training status says this PC understands the settings",
              E.state()["settings"] is True and E.state()["rounds"] is True
              and E.state()["measure"] is True)


# ------------------------------------------------------------ 4. may_speak --

def t_may_speak():
    with Temp():
        check("not private: spoken", V.may_speak(False, "voice")["speak"])
        check("private, by voice, private_on_screen: NOT spoken",
              not V.may_speak(True, "voice")["speak"])
        check("private, typed on the owner's device: spoken", V.may_speak(True, "typed")["speak"])
        check("an unknown origin counts as voice", not V.may_speak(True, "robot")["speak"])
        V.set_setting("privacy", "voice_is_enough", approved=True)
        check("voice_is_enough: spoken", V.may_speak(True, "voice")["speak"])
        V.set_setting("strictness", "balanced", approved=True)
        check("balanced forces it off again", not V.may_speak(True, "voice")["speak"])
        check("the router's private words count",
              V.looks_private("what's in my inbox") and V.looks_private("read my notes")
              and not V.looks_private("what is the capital of France"))


# ------------------------------------------------------ 5. two models: AND --

def _two(rng=None):
    small = Table("sherpa-onnx:357a834f702b", {
        "e1": OWNER, "e2": OWNER, "e3": OWNER,
        "ok": OWNER, "strong_says_no": OWNER, "small_says_no": STRANGER})
    strong = Table("sherpa-onnx:d51abcf31717", {
        "e1": FAR, "e2": FAR, "e3": FAR,
        "ok": FAR, "strong_says_no": STRANGER, "small_says_no": FAR})
    return small, strong


def t_two_models_must_both_pass():
    with Temp():
        small, strong = _two()
        prof = V.enroll(["e1", "e2", "e3"], embedder=small, strong=strong)
        check("one print holds both models' sub-prints",
              prof.subprints(small.name) and prof.subprints(strong.name), prof.models.keys())
        v = V.verify("ok", small, strong=strong)
        check("both pass: the owner", v.is_owner and len(v.checks) == 2, v)
        v = V.verify("strong_says_no", small, strong=strong)
        check("the small one passes, the strong one does not: REFUSED (very strict)",
              not v.is_owner and "stronger" in v.reason, v)
        v = V.verify("small_says_no", small, strong=strong)
        check("the strong one passes, the small one does not: refused", not v.is_owner, v)
        V.set_setting("strictness", "balanced", approved=True)
        v = V.verify("small_says_no", small, strong=strong)
        check("balanced asks the STRONGER model alone (measured: the small one alone lets "
              "too many people in)", v.is_owner and len(v.checks) == 1
              and v.checks[0]["model"] == "the stronger voice-ID model", v)
        v = V.verify("strong_says_no", small, strong=strong)
        check("...so what the stronger model refuses, balanced refuses", not v.is_owner, v)
        v = V.verify("strong_says_no", small, strong=False)
        check("balanced with no stronger model: the small one alone",
              v.is_owner and v.checks[0]["model"] == "the small voice-ID model", v)
        V.set_setting("strictness", "very_strict")
        check("very strict holds the small model gently when paired, the strong one hard",
              v.checks and V.bar_for(small.name, "paired")[0] < V.bar_for(small.name, "balanced")[0]
              and V.bar_for(strong.name, "paired")[0] > V.bar_for(strong.name, "balanced")[0])

        v = V.verify("strong_says_no", small, strong=False)
        check("no strong model installed: very strict uses the one it has",
              v.is_owner and len(v.checks) == 1, v)
        with mock.patch.object(V, "EcapaEmbedder", lambda: small), \
                mock.patch.object(V, "strong_embedder", lambda *a: None):
            st = V.status()
        check("...and status says so, in words",
              st["models"]["very_strict_uses"] == 1 and st["models"]["strong"]["installed"] is False
              and "one model instead of two" in st["note"], (st["models"], st["note"]))

        only_small = V.enroll(["e1", "e2", "e3"], embedder=small,
                              path=V.PROFILE_PATH.with_name("owner-desktop.json"), mic="desktop")
        v = V.verify("ok", small, strong=strong, mic="desktop")
        check("a print made before the strong model was installed: refused, 'train again'",
              not only_small.subprints(strong.name) and not v.is_owner
              and "train your voice again" in v.reason, v)
        with mock.patch.object(V, "EcapaEmbedder", lambda: small), \
                mock.patch.object(V, "strong_embedder", lambda *a: strong), \
                mock.patch.object(V, "lookup_order",
                                  lambda mic="": [("desktop", V.profile_path("desktop"))]):
            st = V.status()
        check("...and status says train again (the talk button then hides)",
              st["needs_retraining"] and "stronger" in st["note"], st["note"])
        check("the measured bars: stricter at very strict, for both models",
              V.floor_for(small.name, "very_strict") > V.floor_for(small.name, "balanced")
              and V.floor_for(strong.name, "very_strict") > V.floor_for(strong.name, "balanced")
              and V.bars_for(small.name)["known"] and V.bars_for(strong.name)["known"])


# ------------------------------------------------------ 6. comparison voices --

def t_cohort_maths():
    rng = random.Random(7)
    dim = 16
    bank = [unit([rng.gauss(0, 1) for _ in range(dim)]) for _ in range(200)]
    clip = unit([rng.gauss(0, 1) for _ in range(dim)])
    owner = unit([c + rng.gauss(0, 0.3) for c in clip])
    s = V.cosine(clip, owner)
    k = 50

    def stats(v):
        sims = sorted((sum(a * b for a, b in zip(v, u)) for u in bank), reverse=True)[:k]
        m = sum(sims) / k
        return m, math.sqrt(sum((x - m) ** 2 for x in sims) / k)
    mt, st = stats(clip)
    me, se = stats(owner)
    by_hand = 0.5 * ((s - mt) / st + (s - me) / se)
    got = V.as_norm(s, clip, owner, bank, k=k)
    check("as_norm matches the formula worked by hand", abs(got - by_hand) < 1e-4,
          (got, by_hand))

    # A "hub": a voice that is close to the owner AND to everyone else.
    # Raw similarity clears the bar; normalised, it is not clearly the owner.
    with Temp() as t:
        name = "sherpa-onnx:0123456789ab"
        centre = unit([1.0] + [0.0] * (dim - 1))
        crowd = [unit([1.0] + [rng.gauss(0, 0.35) for _ in range(dim - 1)]) for _ in range(150)]
        crowd += [unit([rng.gauss(0, 1) for _ in range(dim)]) for _ in range(50)]
        own = unit([0.6] + [0.8] + [0.0] * (dim - 2))
        genuine = unit([0.55, 0.83] + [rng.gauss(0, 0.05) for _ in range(dim - 2)])
        hub = centre
        doc = V.encode_bank(name, crowd, "test voices")
        back = V.decode_bank(doc)
        err = max(abs(a - b) for u, w in zip(crowd, back) for a, b in zip(u, w))
        check("a bank survives 8-bit storage (numbers only, no audio)",
              len(back) == len(crowd) and err < 0.02 and "vectors" in doc, err)
        emb = Table(name, {"e1": own, "e2": own, "e3": own, "genuine": genuine, "hub": hub})
        V.enroll(["e1", "e2", "e3"], embedder=emb)
        raw_hub = V.cosine(hub, own)
        no_bank = V.verify("hub", emb, strong=False)
        V.cohort_path(name).parent.mkdir(parents=True, exist_ok=True)
        V.cohort_path(name).write_text(json.dumps(doc))
        with_bank = V.verify("hub", emb, strong=False)
        g = V.verify("genuine", emb, strong=False)
        check("the hub clears the raw bar without comparison voices",
              raw_hub >= with_bank.threshold and no_bank.is_owner, (raw_hub, no_bank))
        check("...and is refused once it is compared with other voices",
              not with_bank.is_owner and "clearly" in with_bank.reason, with_bank)
        check("the owner still passes", g.is_owner and g.checks[0]["norm"] is not None, g)
        low = unit([0.9, -0.44] + [0.0] * (dim - 2))
        emb.table["low"] = low
        v = V.verify("low", emb, strong=False)
        check("the comparison is an EXTRA bar: under the raw bar is refused however it "
              "normalises", not v.is_owner and v.checks[0]["score"] < v.checks[0]["bar"], v)
        st = V.cohort_for(name)
        check("the bank built on this PC is the one used", st[0] and st[1]["speakers"] == 200
              and st[1]["where"] == "built on this PC", st[1])
        V.cohort_path(name).write_text('{"model": "' + name + '", "dim": 3}')
        with V._BANKS_LOCK:
            V._BANKS.clear()
        check("a malformed bank is not used (and is never a pass)",
              V.cohort_for(name)[0] is None or not V.cohort_for(name)[0])


def t_a_bank_of_the_wrong_width_is_not_used():
    with Temp():
        name = "sherpa-onnx:abcdefabcdef"
        rng = random.Random(2)
        wide = [unit([rng.gauss(0, 1) for _ in range(16)]) for _ in range(40)]
        V.cohort_path(name).parent.mkdir(parents=True, exist_ok=True)
        V.cohort_path(name).write_text(json.dumps(V.encode_bank(name, wide, "x")))
        emb = Table(name, {"a": OWNER, "b": OWNER, "c": OWNER, "ok": OWNER})
        V.enroll(["a", "b", "c"], embedder=emb)
        v = V.verify("ok", emb, strong=False)
        check("a bank of another width is ignored, never a crash (the raw bar still decides)",
              v.is_owner and v.checks[0]["norm"] is None, v)


def t_building_a_bank_on_this_pc():
    import _voice_test
    with Temp() as t:
        root = t.dir / "voices"
        for n in range(12):
            d = root / f"spk{n:02d}" / "ch1"
            d.mkdir(parents=True)
            for k in range(2):
                (d / f"u{k}.wav").write_bytes(wav(2.0, 120 + 25 * n + k))
        emb = _voice_test.stand_in(V)()
        out = V.build_cohort(root, embedders=[emb], out_dir=t.dir / "banks")
        written = list((t.dir / "banks").glob("*.json"))
        doc = json.loads(written[0].read_text()) if written else {}
        check("--build-cohort reads a folder per speaker and writes numbers only",
              out["ok"] and out["speakers"] == 12 and len(written) == 1
              and doc.get("model") == emb.name and doc.get("speakers", 0) >= 12
              and set(doc) == {"model", "dim", "speakers", "source", "scale", "vectors"}, out)
        check("fewer than 10 speakers: refused, in words",
              not V.build_cohort(root / "spk00", embedders=[emb])["ok"])
        check("no voice-ID model: refused, in words",
              "voice-ID model" in V.build_cohort(root, embedders=[V.Embedder()])["why"])


def t_the_shipped_bank():
    try:
        import jarvis_voicebank as B
    except ImportError:
        return check("jarvis_voicebank.py is shipped beside jarvis_voice.py", False)
    check("the shipped bank holds the small and the strong model's voices",
          set(B.BANKS) >= {"sherpa-onnx:357a834f702b", "sherpa-onnx:d51abcf31717"},
          sorted(B.BANKS))
    for name, doc in B.BANKS.items():
        vecs = V.decode_bank(doc)
        check(f"{name}: {len(vecs)} voices, unit length, the right width",
              len(vecs) >= 100 and all(abs(sum(x * x for x in v) - 1) < 1e-6 for v in vecs[:20])
              and len(vecs[0]) == doc["dim"], len(vecs))
    src = (HERE / "jarvis_voicebank.py").read_text(encoding="utf-8")
    check("it says where the voices came from and under which licence",
          "Speech Commands" in src and "CC BY 4.0" in src)


# ------------------------------------------------------------ 7. rounds --

def _round(n, clips, finish=False, mic="phone", add=False, gate=None, enroll=None, **kw):
    body = {"mode": "train", "round": n, "mic": mic, "add": add}
    if clips is not None:
        body["clips"] = b64(clips)
    if finish:
        body["finish"] = True
    return E.stage(json.dumps(body).encode(), gate=gate or Gate(Verdict(True, outcome="approved")),
                   tier_of=ask, enroll=enroll or (lambda c, m, conditions=None, add=False: None),
                   spawn=run_sync, wake_check=lambda c, m: "skipped", **kw)


class Rec:
    """An enroll stand-in that records what it was given."""

    def __init__(self):
        self.calls = []

    def __call__(self, clips, mic, conditions=None, add=False):
        self.calls.append({"n": len(clips), "mic": mic, "conditions": list(conditions or []),
                           "add": add})
        return type("P", (), {"samples": len(clips), "embedder": "x", "outliers": [2]})()


def t_training_in_rounds():
    with Temp():
        gate, rec = Gate(Verdict(True, outcome="approved")), Rec()
        r1 = [wav(2.0, 180 + i) for i in range(4)]
        code, out = _round(1, r1, gate=gate, enroll=rec)
        check("round 1 is held: 200, no card, nothing enrolled",
              code == 200 and not gate.calls and not rec.calls and E._PENDING is None
              and out["held"]["clips"] == 4 and out["next_round"] == 2, (code, out))
        st = json.dumps(E.state())
        check("status shows what is held - counts only, no audio",
              '"session"' in st and b64(r1)[0][:40] not in st and len(st) < 2500,
              E.state()["session"])
        held = E._SESSION["rounds"][1]
        code, out = _round(1, [wav(2.0, 190 + i) for i in range(3)], gate=gate, enroll=rec)
        check("a round sent again replaces the first take (and drops it)",
              code == 200 and out["held"]["rounds"][0]["clips"] == 3 and not held, out)
        code, out = _round(2, [wav(2.0, 200 + i) for i in range(3)], gate=gate, enroll=rec)
        code, out = _round(1, [wav(2.0, 180)] * 3, mic="desktop", gate=gate, enroll=rec)
        check("another microphone while one is held: 409, says finish or cancel",
              code == 409 and "cancel" in out["error"], (code, out))
        code, out = _round(3, [wav(2.0, 210 + i) for i in range(5)], finish=True,
                           gate=gate, enroll=rec)
        check("finish: ONE card, for all three rounds",
              code == 202 and len(gate.calls) == 1 and out["rounds"] == 3
              and out["clips"] == 11 and "3 rounds" in gate.calls[0][2], (code, out))
        check("approved: enrolled ONCE with each clip's condition",
              len(rec.calls) == 1 and rec.calls[0]["conditions"]
              == ["close"] * 3 + ["far"] * 3 + ["room"] * 5, rec.calls)
        last = E.state()["last"]
        check("the odd clip comes back as round and clip number",
              last["outcome"] == "enrolled" and last["outliers"] == [{"round": 1, "clip": 3}],
              last)
        check("nothing held afterwards", E._SESSION is None and E._PENDING is None)

        for label, verdict in (("denied", Verdict(False, outcome="denied")),
                               ("timed out", Verdict(False, outcome="timed_out"))):
            E._reset_for_tests()
            rec = Rec()
            _round(1, [wav(2.0, 180 + i) for i in range(3)], enroll=rec)
            h1 = E._SESSION["rounds"][1]
            _round(2, [wav(2.0, 200 + i) for i in range(3)], enroll=rec)
            h2 = E._SESSION["rounds"][2]
            staged = []
            real_start = E._start_card

            def spy(*a, **k):
                out = real_start(*a, **k)
                return out
            g = Gate(verdict)
            with mock.patch.object(E, "_spawn", run_sync):
                code, out = _round(3, None, finish=True, gate=g, enroll=rec)
            check(f"{label}: one card, nothing enrolled, every held clip dropped",
                  code == 202 and len(g.calls) == 1 and not rec.calls and not h1 and not h2
                  and E._PENDING is None and E._SESSION is None, (code, out, staged))

        E._reset_for_tests()
        _round(1, [wav(2.0, 180 + i) for i in range(3)])
        h = E._SESSION["rounds"][1]
        code, out = E.stage(json.dumps({"mode": "train", "cancel": True}).encode())
        check("cancel: every held clip dropped", code == 200 and out["cancelled"]
              and not h and E._SESSION is None, out)
        _round(1, [wav(2.0, 180 + i) for i in range(3)])
        h = E._SESSION["rounds"][1]
        import time as _t
        check("15 minutes with no new round: dropped",
              E.expire_sessions(now=_t.time() + E.SESSION_SECONDS + 5) and not h
              and E._SESSION is None and E.state()["last"]["outcome"] == "expired")
        code, out = _round(1, None, finish=True)
        check("finish with nothing held: 400", code == 400, (code, out))
        E._reset_for_tests()
        held_gate = HeldGate(Verdict(False, outcome="denied"))
        E.stage(json.dumps({"clips": b64([wav(2.0, 180 + i) for i in range(3)])}).encode(),
                gate=held_gate, tier_of=ask, enroll=Rec())
        held_gate.asked.wait(5)
        code, out = _round(1, [wav(2.0, 180 + i) for i in range(3)])
        check("a round while a card waits: 409", code == 409, (code, out))
        held_gate.release.set()


def t_rounds_make_subprints_and_add_adds():
    with Temp():
        small, strong = _two()
        rng = random.Random(3)
        small.table.update({f"c{i}": near(OWNER, 0.05, rng) for i in range(3)})
        small.table.update({f"f{i}": near(FAR, 0.05, rng) for i in range(3)})
        small.table["far_clip"] = near(FAR, 0.05, rng)
        prof = V.enroll(["c0", "c1", "c2", "f0", "f1", "f2"], embedder=small,
                        conditions=["close"] * 3 + ["far"] * 3, mic="phone")
        conds = [sp["condition"] for sp in prof.subprints(small.name)]
        check("one sub-print per condition", conds == ["close", "far"], conds)
        whole = V.cosine(small.table["far_clip"], prof.centroid)
        v = V.verify("far_clip", small, strong=False, mic="phone")
        check("the nearest sub-print decides: a far clip passes on the far one",
              v.is_owner and v.checks[0]["condition"] == "far"
              and v.checks[0]["score"] > whole, (v, whole))
        created = prof.created
        small.table.update({f"r{i}": near(OWNER, 0.05, rng) for i in range(3)})
        more = V.enroll(["r0", "r1", "r2"], embedder=small, conditions=["room"] * 3,
                        mic="phone", add=True)
        conds = [sp["condition"] for sp in more.subprints(small.name)]
        check("'train more' ADDS: the old sub-prints stay, a new one joins",
              conds == ["close", "far", "room"] and more.samples == 9
              and more.created == created, (conds, more.samples))
        again = V.enroll(["c0", "c1", "c2"], embedder=small, conditions=["close"] * 3,
                         mic="phone", add=True)
        close = next(sp for sp in again.subprints(small.name) if sp["condition"] == "close")
        check("adding the same condition merges into its sub-print",
              close["samples"] == 6 and len(again.subprints(small.name)) == 3, close["samples"])
        with mock.patch.object(V, "EcapaEmbedder", lambda: small), \
                mock.patch.object(V, "strong_embedder", lambda *a: None):
            ph = S.status()["gate"]["prints"]["phone"]
        check("the status shows each print's sub-prints to the apps",
              [x["condition"] for x in ph["subprints"]] == ["close", "far", "room"]
              and ph["strong_trained"] is False, ph)
        other = Table("sherpa-onnx:ffffffffffff", {"c0": OWNER, "c1": OWNER, "c2": OWNER})
        try:
            V.enroll(["c0", "c1", "c2"], embedder=other, mic="phone", add=True)
            check("adding with a different voice check is refused", False)
        except ValueError as exc:
            check("adding with a different voice check is refused", "from the start" in str(exc))

        gate = Gate(Verdict(True, outcome="approved"))
        E._reset_for_tests()
        _round(1, [wav(2.0, 180 + i) for i in range(3)], add=True, gate=gate, enroll=Rec(),
               finish=True)
        check("the add card says Add, and that nothing is deleted",
              gate.calls and gate.calls[0][2].startswith("Add the recordings")
              and "Nothing it had is deleted" in gate.calls[0][2], gate.calls[:1])
        old = V.VoiceProfile(embedder=small.name, centroid=OWNER, threshold=0.4, samples=5)
        old.save(V.PROFILE_PATH.with_name("legacy.json"))
        back = V.load_profile(V.PROFILE_PATH.with_name("legacy.json"))
        check("a print from before sub-prints reads as one 'general' sub-print",
              [sp["condition"] for sp in back.subprints(small.name)] == ["general"])


# ------------------------------------------------------------ 9. repeats --

def t_repeat_counters():
    with Temp():
        V.note_outcome(False, "very_strict", "phone", now=100.0)
        V.note_outcome(True, "very_strict", "phone", now=105.0)
        V.note_outcome(False, "very_strict", "phone", now=200.0)
        V.note_outcome(True, "very_strict", "phone", now=211.0)
        V.note_outcome(False, "balanced", "desktop", too_short=True, now=300.0)
        V.note_outcome(True, "balanced", "desktop", now=302.0)
        c = V.repeat_counts()
        check("refused then accepted within 10 s: counted; after 11 s: not",
              c["very_strict"]["refused_then_accepted"] == 1
              and c["very_strict"]["refused"] == 2 and c["very_strict"]["accepted"] == 2
              and c["very_strict"]["repeat_rate"] == 0.5, c)
        check("a too-short clip counts too, per strictness",
              c["balanced"]["too_short"] == 1 and c["balanced"]["refused_then_accepted"] == 1, c)
        V._reset_repeat_for_tests()
        small, strong = _two()
        V.enroll(["e1", "e2", "e3"], embedder=small, strong=strong)
        V.verify("strong_says_no", small, strong=strong)
        V.verify("ok", small, strong=strong)
        c = V.repeat_counts()["very_strict"]
        check("verify() counts real checks", c["refused"] == 1 and c["accepted"] == 1
              and c["refused_then_accepted"] == 1, c)
        V.verify("nothing-at-all", small, strong=strong)
        check("a clip with no vector is not counted as a refusal of the owner",
              V.repeat_counts()["very_strict"]["refused"] == 1)
        check("status carries the counts",
              S.status()["gate"]["repeat"]["window_seconds"] == V.REPEAT_WINDOW)


# ------------------------------------------- 10. measure and someone else --

def t_measure_and_someone_else():
    with Temp():
        small, strong = _two()
        V.enroll(["e1", "e2", "e3"], embedder=small, strong=strong)
        got = V.measure(["ok", "strong_says_no", "small_says_no", "ok"], small, strong=strong,
                        seconds=[3.0, 3.0, 3.0, 1.6])
        check("the guided test: each sentence judged at both settings",
              got["ok"] and got["very_strict"]["passed"] == 1
              and got["balanced"]["passed"] == 3, got)
        check("...with the shortest sentence each allows",
              got["very_strict"]["too_short"] == 1 and got["balanced"]["too_short"] == 0, got)
        check("...and it is not counted as real use",
              V.repeat_counts()["very_strict"]["accepted"] == 0)
        seen = {}

        def fake(pcm, mic):
            seen["n"] = len(pcm)
            return {"ok": True, "clips": len(pcm), "strong_model": True,
                    "very_strict": {"passed": 15, "of": 20, "too_short": 2, "repeat_rate": 0.25},
                    "balanced": {"passed": 19, "of": 20, "too_short": 0, "repeat_rate": 0.05},
                    "per_clip": []}
        gate = Gate(Verdict(True, outcome="approved"))
        code, out = E.stage(json.dumps({"mode": "measure", "mic": "phone",
                                        "clips": b64([wav(2.0, 180)] * 20)}).encode(),
                            gate=gate, tier_of=ask, measure_fn=fake)
        check("mode measure: 200, 20 sentences, no card", code == 200 and seen["n"] == 20
              and not gate.calls and "15 of 20" in out["message"], (code, out))
        check("...and the last result's counts are in the status",
              E.state()["measure_last"]["very_strict"]["passed"] == 15)
        code, out = E.stage(json.dumps({"mode": "measure",
                                        "clips": b64([wav(2.0, 180)] * 21)}).encode(),
                            measure_fn=fake)
        check("more than 20: 400", code == 400, (code, out))
        sc = V.score_clips(["strong_says_no", "small_says_no"], small, strong=strong)
        check("the 'someone else' check scores the deciding (stronger) model, and says "
              "what really passed", sc["ok"] and sc["model"] == "strong"
              and sc["passed"] == [False, False] and sc["scores"] == [0.0, 1.0]
              and sc["floor"] == V.floor_for(strong.name, "balanced"), sc)
        V.set_threshold(0.6, model=strong.name)
        p = V.find_profile("")[0]
        check("a threshold card for the stronger model raises ITS bar only",
              p.thresholds[strong.name] == 0.6 and V.raw_bar(p, strong.name, "paired") == 0.6
              and V.raw_bar(p, small.name, "paired") == V.bar_for(small.name, "paired")[0], p)
        try:
            V.set_threshold(0.2, model=strong.name)
            check("...never under that model's floor", False)
        except ValueError:
            check("...never under that model's floor", True)
        s = V.suggest_threshold([0.8, 0.7], [0.1, 0.2], floor=0.5)
        check("a suggestion is never below the model's floor", s["suggested"] >= 0.5, s)


# ------------------------------------------------ 11. the shortest command --

def _clip(who, seconds):
    """A tone that the Table stand-in reads as `who` (see _tag)."""
    return wav(seconds, 200.0, amp=0.8 if who == "owner" else 0.3)


def t_minimum_command_length():
    with Temp():
        small = Table("sherpa-onnx:357a834f702b", {"loud": OWNER, "quiet": STRANGER})
        V.enroll(["a", "b", "c"], embedder=Table(small.name, {"a": OWNER, "b": OWNER,
                                                               "c": OWNER}))
        boom = mock.Mock(side_effect=AssertionError("the voice check ran"))
        with mock.patch.object(V, "EcapaEmbedder", lambda: small), \
                mock.patch.object(V, "strong_embedder", lambda *a: None), \
                mock.patch.object(S, "_speech_span", return_value="skip"):
            with mock.patch.object(V, "verify", boom), \
                    mock.patch.object(S, "_transcribe", boom):
                h = S.hear(_clip("owner", 1.2), mic="phone")
            check("a 1.2 s command: refused before the voice check, never transcribed",
                  not h.is_owner and h.too_short and h.min_seconds == 2.0
                  and "say a little more" in h.reason and h.threshold == 0, h)
            check("...and counted as a repeat", V.repeat_counts()["very_strict"]["too_short"] == 1)
            with mock.patch.object(S, "_stt_engine", return_value=object()), \
                    mock.patch.object(S, "_transcribe", return_value="what is the time"):
                h = S.hear(_clip("owner", 2.5), mic="phone")
            check("2.5 s: checked, and the owner is heard", h.is_owner and h.text
                  and h.strictness == "very_strict" and not h.too_short, h)
            V.set_setting("strictness", "balanced", approved=True)
            with mock.patch.object(S, "_stt_engine", return_value=object()), \
                    mock.patch.object(S, "_transcribe", return_value="what is the time"):
                h = S.hear(_clip("owner", 1.7), mic="phone")
            check("balanced takes a shorter command (1.7 s)", h.is_owner and h.text, h)
            V.set_setting("strictness", "very_strict")

            import jarvis_wakeword as W
            S.set_wake_enabled(True, gate=lambda *a: Verdict(True, outcome="approved"),
                               tier_of=ask, spawn=run_sync)
            try:
                with mock.patch.object(W, "spot", return_value=W.Spot(True, heard=True, score=0.9)), \
                        mock.patch.object(S, "_stt_engine", return_value=object()), \
                        mock.patch.object(S, "_transcribe", return_value="Hey Jarvis."):
                    h = S.hear(_clip("owner", 1.0), source="wake_word", mic="phone")
                check("'hey Jarvis' alone in a short clip: the wake path, the window opens",
                      h.awake and h.is_owner and not h.too_short, h)
                with mock.patch.object(S, "_stt_engine", return_value=object()), \
                        mock.patch.object(S, "_transcribe", return_value="lights off"), \
                        mock.patch.object(V, "verify", boom):
                    h = S.hear(_clip("owner", 1.0), source="wake_word", mic="phone")
                check("...but a short COMMAND inside the window is refused, unchecked",
                      h.too_short and not h.text, h)
                with mock.patch.object(W, "spot", return_value=W.Spot(True, heard=True, score=0.9)), \
                        mock.patch.object(S, "_stt_engine", return_value=object()), \
                        mock.patch.object(S, "_transcribe", return_value="Hey Jarvis, unlock the door"):
                    h = S.hear(_clip("owner", 1.4), source="wake_word", mic="phone")
                check("a short clip with 'hey Jarvis' AND a command: the command is not taken",
                      h.too_short and h.text == "" and h.wake_heard, h)
                with mock.patch.object(W, "spot", return_value=W.Spot(True, heard=True, score=0.9)), \
                        mock.patch.object(S, "_transcribe",
                                          side_effect=AssertionError("a stranger transcribed")):
                    h = S.hear(_clip("stranger", 1.0), source="wake_word", mic="phone")
                check("a stranger's short 'hey Jarvis': refused by the voice check, never "
                      "transcribed", not h.is_owner and not h.awake, h)
            finally:
                S.set_wake_enabled(False)
                S._close_awake()


def t_private_fields_on_the_reply():
    with Temp():
        small = Table("sherpa-onnx:357a834f702b", {"loud": OWNER})
        V.enroll(["a", "b", "c"], embedder=Table(small.name, {"a": OWNER, "b": OWNER,
                                                               "c": OWNER}))
        with mock.patch.object(V, "EcapaEmbedder", lambda: small), \
                mock.patch.object(V, "strong_embedder", lambda *a: None), \
                mock.patch.object(S, "_speech_span", return_value="skip"), \
                mock.patch.object(S, "_stt_engine", return_value=object()), \
                mock.patch.object(S, "_transcribe", return_value="read me my last email"):
            h = S.hear(_clip("owner", 2.5)).as_dict()
            check("a private question by voice: private_aloud false, question_private true",
                  h["ok"] and h["private_aloud"] is False and h["question_private"] is True, h)
            V.set_setting("privacy", "voice_is_enough", approved=True)
            h = S.hear(_clip("owner", 2.5)).as_dict()
            check("voice_is_enough: private_aloud true", h["private_aloud"] is True, h)


# ------------------------------------------------ 12. nothing on the disk --

def t_no_audio_is_written():
    with Temp() as t:
        clips = [wav(2.0, 170 + 7 * i) for i in range(12)]
        pcm = [E._read_clip(1, c)[0] for c in clips]
        small = Table("sherpa-onnx:357a834f702b", {})

        class ByLen(Table):
            def embed(self, audio):
                x = V._pcm(audio)
                return near(OWNER, 0.02, random.Random(len(x))) if x else []
        emb = ByLen(small.name, {})

        def enrol(c, m, conditions=None, add=False):
            return V.enroll(c, embedder=emb, mic=m, conditions=conditions, add=add)
        gate = Gate(Verdict(True, outcome="approved"))
        _round(1, clips[:4], gate=gate, enroll=enrol)
        _round(2, clips[4:8], gate=gate, enroll=enrol)
        _round(3, clips[8:], finish=True, gate=gate, enroll=enrol)
        E.stage(json.dumps({"mode": "calibrate", "mic": "phone",
                            "clips": b64(clips[:2])}).encode())
        E.stage(json.dumps({"mode": "measure", "mic": "phone", "clips": b64(clips[:3])}).encode(),
                measure_fn=lambda p, m: V.measure(p, emb, 16000, m, strong=False))
        V.set_setting("strictness", "balanced", approved=True)
        written = [p for p in t.dir.rglob("*") if p.is_file()]
        blobs = b"".join(p.read_bytes() for p in written)
        needles = [c[2000:2064] for c in pcm] + [b64([c])[0][2000:2064].encode() for c in pcm]
        check("a whole training, a check, a test and a setting wrote files",
              any(p.name == "owner-phone.json" for p in written), [p.name for p in written])
        check("...and none of them holds any of the recordings, raw or as base64",
              not any(n in blobs for n in needles))
        check("...and they are small (numbers, not sound)",
              all(p.stat().st_size < 64_000 for p in written),
              [(p.name, p.stat().st_size) for p in written])
    src = (HERE / "rebuilt" / "jarvis_voice.py").read_text(encoding="utf-8")
    check("jarvis_voice.py writes only prints, settings and banks (every write_text is one)",
          src.count("write_text(") == 3, src.count("write_text("))


# ------------------------------------------------ 13. the real model files --

def t_real_models():
    small_p = os.environ.get("JARVIS_TEST_SPEAKER_MODEL", "")
    strong_p = os.environ.get("JARVIS_TEST_STRONG_MODEL", "")
    if not (small_p and strong_p and Path(small_p).is_file() and Path(strong_p).is_file()):
        return skip("real models", "set JARVIS_TEST_SPEAKER_MODEL and JARVIS_TEST_STRONG_MODEL "
                                   "to the two .onnx files to run these")
    try:
        import sherpa_onnx  # noqa: F401
    except ImportError:
        return skip("real models", "sherpa-onnx is not installed")
    cfg = {"speaker_model": small_p, "speaker_model_strong": strong_p, "enabled": True,
           "mode": "owner"}
    with Temp(), mock.patch.object(V, "_cfg", lambda k, d=None: cfg.get(k, d)):
        small = V.EcapaEmbedder()
        strong = V.strong_embedder(small)
        check("both real models load, as two different models",
              strong is not None and small.name != strong.name, (small.name, strong))
        check("their bars are the measured ones",
              V.bars_for(small.name)["known"] and V.bars_for(strong.name)["known"],
              (small.name, strong.name))
        clips = [E._read_clip(1, wav(3.0, 150 + 3 * i))[0] for i in range(6)]
        V.enroll(clips, embedder=small, strong=strong, sample_rate=16000,
                 conditions=["close"] * 6)
        v = V.verify(clips[0], small, sample_rate=16000)
        check("a very strict check asks both real models", len(v.checks) == 2, v.checks)
        st = V.status()
        check("status names both, and very strict uses two",
              st["models"]["very_strict_uses"] == 2 and st["models"]["strong"]["installed"],
              st["models"])


if __name__ == "__main__":
    for fn in (t_hole_one_the_basic_check_lets_nobody_in, t_hole_two_one_noisy_clip,
               t_settings_tighten_now_loosen_with_a_card, t_may_speak,
               t_two_models_must_both_pass, t_cohort_maths,
               t_a_bank_of_the_wrong_width_is_not_used, t_building_a_bank_on_this_pc,
               t_the_shipped_bank,
               t_training_in_rounds, t_rounds_make_subprints_and_add_adds,
               t_repeat_counters, t_measure_and_someone_else, t_minimum_command_length,
               t_private_fields_on_the_reply, t_no_audio_is_written, t_real_models):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed, {len(SKIPPED)} skipped")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
