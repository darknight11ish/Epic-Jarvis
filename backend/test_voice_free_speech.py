""""Free-speech prompts": which prompt a training clip answers (2026-10-19).

    python3 test_voice_free_speech.py

No pytest, no network, no microphone. Clips are synthesised WAVs; the gate is
a stand-in that records the one card it is asked; the enrolment is a recorder
function, except in the last test, which runs the REAL `jarvis_voice.enroll()`
into a temporary folder.

What it proves:
  1. The plan is the ONLY source of the allowed ids, and `/api/voice/status`
     advertises the field (`gate.training.free_speech`) so a screen can check
     before sending - an older PC has no flag and would ignore the list.
  2. A body WITHOUT the field is exactly the body every screen sent before
     this change: the same card words, the same stored detail keys, the same
     held/session/last shapes and the same audit lines.
  3. `mode=train` accepts one label per clip; the label is held with its round
     (and follows the round's replace / cancel / expiry rules), the ONE card
     still carries only counts, and on approval only the per-prompt COUNT is
     kept - on the card's stored detail row, in the audit trail and in
     `state()["last"]`. Nothing is invented and no extra card is raised.
  4. Deny, timeout, cancel and expiry drop the labels with the audio.
  5. The one-shot body and `mode=measure` accept the field too.
  6. Every refusal is a 400 in plain words - not a list, wrong length, an
     unknown prompt, a non-string entry, labels on a finish with no clips -
     nothing is held, and the refused text itself is never echoed back.
  7. The prompt names never reach the voice profile. It is not biometric: the
     profile keeps vectors and scores, and the receipt keeps counts.
"""
import array
import base64
import io
import json
import math
import os
import sys
import tempfile
import time
import traceback
import wave
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

# jarvis_voice_enroll.py / jarvis_voice_training.py and jarvis_voice.py (a
# rebuilt module) from this repository, as the suite's own folders.
sys.path.insert(0, str(HERE / "rebuilt"))
sys.path.insert(0, str(HERE))
require_shipped("jarvis_voice_enroll.py", "jarvis_voice_training.py",
                "rebuilt/jarvis_voice.py")
import jarvis_voice as V  # noqa: E402
import jarvis_voice_enroll as E  # noqa: E402
import jarvis_voice_training as T  # noqa: E402
from _voice_test import semantic_voice  # noqa: E402
os.environ.setdefault("JARVIS_TEST_UNSEALED_FIXTURES", "1")

# The suite never writes the PC's real audit log: a test that cares records
# `_audit` itself with audited(); everywhere else it is a no-op.
E._audit = lambda event, detail=None: None

FAILED, PASSED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(name, why):
    SKIPPED.append(name)
    print(f"skip  {name} - {why}")


# ---------------------------------------------------------------- helpers --

def wav(seconds=2.0, freq=180.0, rate=16000) -> bytes:
    n = int(seconds * rate)
    s = array.array("h", [int(0.4 * 32767 * math.sin(2 * math.pi * freq * i / rate))
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


def clips(n, seconds=2.0, base=180):
    return [wav(seconds, base + i) for i in range(n)]


class Verdict:
    def __init__(self, allowed, tier="ask", outcome=None, rid="req-1", reason=""):
        self.allowed, self.tier, self.outcome = allowed, tier, outcome
        self.request_id, self.reason = rid, reason


class Gate:
    """The stand-in gate: records the one card, keeps the staged label list
    itself so the test can prove it is cleared with the audio."""

    def __init__(self, verdict):
        self.verdict, self.calls = verdict, []
        self.labels = None

    def __call__(self, action, detail, prompt):
        self.calls.append((action, detail, prompt))
        pending = E._PENDING or {}
        self.labels = pending.get("free_speech")
        return self.verdict


class Rec:
    """An enrol stand-in that records exactly what it was given."""

    def __init__(self):
        self.calls = []

    def __call__(self, pcm, mic="", conditions=None, add=False):
        self.calls.append({"n": len(pcm), "mic": mic,
                           "conditions": list(conditions or []), "add": add})
        return type("P", (), {"samples": len(pcm), "embedder": "x",
                              "outliers": []})()


def run_sync(fn):
    fn()


def ask(_a):
    return "ask"


class Temp:
    """A fresh folder for the voice print (the real-enrolment test writes
    one); every other test keeps nothing on disk."""

    def __enter__(self):
        self.keep = V.PROFILE_PATH
        self.dir = Path(tempfile.mkdtemp(prefix="jarvis-free-speech-"))
        V.PROFILE_PATH = self.dir / "owner.json"
        E._reset_for_tests()
        return self

    def __exit__(self, *a):
        V.PROFILE_PATH = self.keep
        E._reset_for_tests()


def body(n=1, pcm=None, labels=None, finish=False, mic="phone", add=False):
    """A mode=train body. `labels` None means the field is ABSENT."""
    doc = {"mode": "train", "round": n, "mic": mic, "add": add}
    if pcm is not None:
        doc["clips"] = b64(pcm)
    if labels is not None:
        doc["free_speech"] = labels
    if finish:
        doc["finish"] = True
    return json.dumps(doc).encode()


def send(raw, gate=None, rec=None):
    """Run one body through the real stage(); returns (http code, payload).
    `gate` and `rec` are kept by the caller, which reads their record of what
    happened."""
    gate = gate or Gate(Verdict(True, outcome="approved"))
    rec = rec or Rec()
    return E.stage(raw, gate=gate, tier_of=ask, spawn=run_sync,
                   enroll=rec, wake_check=lambda c, m: "skipped")


def audited():
    """Records `_audit` calls in this block (and keeps them off the PC)."""
    calls = []

    def record(event, detail=None):
        calls.append((event, detail))

    return calls, mock.patch.object(E, "_audit", record)


def at(calls, event):
    return [d for e, d in calls if e == event]


def stage_of(out):
    return (out.get("held") or {}).get("rounds") or []


def one_round_of(out, r=1):
    return next((x for x in stage_of(out) if x.get("round") == r), {})


# --------------------------------------- 1. the plan, the flag, the ids --

def t_the_plan_names_the_ids_and_status_advertises_the_field():
    plan_ids = tuple(p["id"] for p in T.FREE_SPEECH)
    check("the PC's plan names the prompts the screens show",
          plan_ids == ("introduce", "day", "passage"), plan_ids)
    check("the allowed ids are READ from the plan, never copied into this module",
          E._free_speech_ids() == plan_ids, E._free_speech_ids())
    with Temp():
        st = E.state()
        check("status advertises the field so a screen checks before sending",
              st.get("free_speech") is True, st.get("free_speech"))
        check("...beside the capability flags that were already there",
              st["rounds"] is True and st["measure"] is True
              and st["calibrate"] is True and st["settings"] is True, st)
    # A rename in the plan has to reach the field: it is read, not hard-coded.
    renamed = tuple(dict(p, id="renamed-" + p["id"]) for p in T.FREE_SPEECH)
    with Temp(), mock.patch.object(T, "FREE_SPEECH", renamed):
        ids = tuple(n["id"] for n in renamed)
        check("a renamed prompt is accepted under its new name",
              E._free_speech({"free_speech": ["renamed-day"]}, 1) == ["renamed-day"])
        check("...and the old name is refused", E._free_speech_ids() == ids, E._free_speech_ids())
    with Temp(), mock.patch.object(T, "FREE_SPEECH", ()):
        check("a PC with no prompts says so in the flag", E.state()["free_speech"] is False)
        check("...and refuses a prompt name in words, not by dropping it",
              "no free-speech prompts" in _refusal({"free_speech": ["introduce"]}, 1))
    with Temp(), mock.patch.object(E, "TRAINING", None):
        check("a design module older than FREE_SPEECH: the flag is false, not a guess",
              E.state()["free_speech"] is False)


def _refusal(labels, n_clips):
    """The 400 sentence for one bad `free_speech` list on a full clip count."""
    try:
        E._free_speech({"free_speech": labels}, n_clips)
    except E.BadClip as exc:
        return str(exc)
    return ""


# ------------------------- 2. a body without the field is the old body --

def t_a_body_without_the_field_is_exactly_the_old_body():
    with Temp():
        gate, rec = Gate(Verdict(True, outcome="approved")), Rec()
        calls, patched = audited()
        with patched:
            code, out = send(body(1, clips(3)), gate=gate, rec=rec)
            check("a round without the field is held, with today's shape",
                  code == 200 and set(one_round_of(out)) ==
                  {"round", "condition", "clips", "seconds"}, (code, out))
            check("...and status.session shows it in today's shape",
                  set(E.state()["session"]["rounds"][0]) ==
                  {"round", "condition", "clips", "seconds"}, E.state()["session"])
            code, out = send(body(1, None, finish=True), gate=gate, rec=rec)
        check("the old body still raises exactly ONE card, for one round",
              code == 202 and len(gate.calls) == 1, (code, gate.calls))
        detail, text = gate.calls[0][1], gate.calls[0][2]
        check("the card's stored detail has exactly today's keys - none added",
              set(detail) == {"text", "clips", "seconds", "mic", "rounds", "add",
                              "what"}, set(detail))
        check("the card's words are today's words",
              text == E.describe(3, 6.0, "phone", rounds=1, add=False), text)
        staged = at(calls, "voice.training.staged")
        check("the staged audit line is today's line",
              staged and set(staged[0]) == {"clips", "seconds", "rounds", "add"},
              staged)
        check("approved: enrolled once, from the same clips and no labels",
              len(rec.calls) == 1 and rec.calls[0]["conditions"] == ["close"] * 3,
              rec.calls)
        last = E.state()["last"]
        check("the outcome carries no free_speech key", "free_speech" not in last
              and last["outcome"] == "enrolled", last)
        decided = at(calls, "voice.training.decided")
        check("the decided audit line is today's line",
              decided and set(decided[0]) == {"outcome", "samples", "request_id"},
              decided)
        check("nothing is held and no audio or labels remain",
              E._PENDING is None and E._SESSION is None)


# -------------------------------- 3. train: labels held with their round --

def t_train_holds_each_label_with_its_round():
    with Temp():
        gate, rec = Gate(Verdict(True, outcome="approved")), Rec()
        code, out = send(body(1, clips(5), ["", None, "introduce", "", "day"]),
                         gate=gate, rec=rec)
        check("a round labels its clips: counts per prompt, in the plan's order",
              code == 200
              and one_round_of(out).get("free_speech") == {"introduce": 1, "day": 1},
              (code, out))
        check("...and it is the same in status.session",
              E.state()["session"]["rounds"][0].get("free_speech") ==
              {"introduce": 1, "day": 1}, E.state()["session"])
        old_labels = E._SESSION["free_speech"][1]
        old_clips = E._SESSION["rounds"][1]
        code, out = send(body(1, clips(3), ["day", "day", "day"]), gate=gate, rec=rec)
        check("a round sent again replaces its labels with the new take's",
              code == 200 and one_round_of(out).get("free_speech") == {"day": 3}
              and not old_labels and not old_clips, (code, out, old_labels))
        held_labels = E._SESSION["free_speech"][1]
        code, out = E.stage(json.dumps({"mode": "train", "cancel": True}).encode())
        check("cancel drops the labels with the clips",
              code == 200 and out["cancelled"] and not held_labels
              and E._SESSION is None, (code, out, held_labels))

        # A round with no labels on a training that has a labelled one: the
        # unlabelled round simply has no key, so the old shape is untouched.
        send(body(1, clips(3), ["passage", None, None]))
        code, out = send(body(2, clips(3)))
        check("an unlabelled round beside a labelled one keeps the old row shape",
              code == 200 and "free_speech" not in one_round_of(out, 2)
              and one_round_of(out, 1).get("free_speech") == {"passage": 1},
              (code, out))


# --------------------- 4. ONE card, and only COUNTS reach the receipt --

def t_the_one_card_carries_counts_and_only_counts():
    with Temp():
        gate, rec = Gate(Verdict(True, outcome="approved")), Rec()
        calls, patched = audited()
        with patched:
            send(body(1, clips(3), ["introduce", None, None]), gate=gate, rec=rec)
            send(body(2, clips(3), [None, "day", None]), gate=gate, rec=rec)
            code, out = send(body(3, clips(3), [None, None, "passage"], finish=True),
                             gate=gate, rec=rec)
        check("the whole training is still exactly ONE approval card",
              code == 202 and len(gate.calls) == 1, (code, gate.calls))
        check("that card is still under change_own_config - no new tier",
              gate.calls[0][0] == E.ACTION == "change_own_config", gate.calls[0][0])
        detail = gate.calls[0][1]
        check("the card's stored detail carries counts per prompt",
              detail.get("free_speech") == {"introduce": 1, "day": 1, "passage": 1},
              detail)
        check("the card's WORDS do not name a prompt or the field",
              gate.calls[0][2] == E.describe(9, 18.0, "phone", rounds=3, add=False)
              and "introduce" not in gate.calls[0][2]
              and "free_speech" not in gate.calls[0][2], gate.calls[0][2])
        staged = at(calls, "voice.training.staged")
        check("the staged audit line carries the counts",
              staged and staged[-1].get("free_speech") ==
              {"introduce": 1, "day": 1, "passage": 1}, staged)
        check("approved: enrolled ONCE, each clip still under its round's condition",
              len(rec.calls) == 1 and rec.calls[0]["conditions"] ==
              ["close"] * 3 + ["table"] * 3 + ["noise"] * 3, rec.calls)
        last = E.state()["last"]
        check("the outcome the phone reads carries the counts",
              last["outcome"] == "enrolled"
              and last.get("free_speech") == {"introduce": 1, "day": 1, "passage": 1},
              last)
        decided = at(calls, "voice.training.decided")
        check("the decided audit line carries the counts, not the audio",
              decided and decided[0].get("free_speech") ==
              {"introduce": 1, "day": 1, "passage": 1}
              and decided[0].get("outcome") == "enrolled", decided)
        check("the staged labels are dropped with the audio",
              E._PENDING is None and gate.labels == [], gate.labels)
        check("nothing held after the card is answered", E._SESSION is None)


# ------------------- 5. deny / timeout / cancel / expiry drop labels --

def t_deny_timeout_and_expiry_drop_the_labels():
    for label, verdict in (("denied", Verdict(False, outcome="denied")),
                           ("timed out", Verdict(False, outcome="timed_out"))):
        with Temp():
            gate, rec = Gate(verdict), Rec()
            code, out = send(body(1, clips(3), ["day", None, None], finish=True),
                             gate=gate, rec=rec)
            last = E.state()["last"]
            check(f"{label}: nothing enrolled and the labels are gone",
                  code == 202 and not rec.calls and E._PENDING is None
                  and gate.labels == [] and "free_speech" not in last, (code, last))
    with Temp():
        send(body(1, clips(3), ["day", None, None]))
        held = E._SESSION["free_speech"][1]
        E.expire_sessions(now=time.time() + E.SESSION_SECONDS + 5)
        check("15 minutes with no new round: the labels go with the clips",
              E._SESSION is None and not held and
              E.state()["last"]["outcome"] == "expired", held)


# ------------------ 6. the other two bodies accept it as well --------

def t_the_one_shot_body_and_measure_accept_it():
    with Temp():
        gate, rec = Gate(Verdict(True, outcome="approved")), Rec()
        raw = json.dumps({"mic": "phone", "clips": b64(clips(3)),
                          "free_speech": [None, "", "passage"]}).encode()
        calls, patched = audited()
        with patched:
            code, out = send(raw, gate=gate, rec=rec)
        check("the one-shot body (no mode) accepts the field and keeps ONE card",
              code == 202 and len(gate.calls) == 1
              and gate.calls[0][1].get("free_speech") == {"passage": 1}, (code, gate.calls))
        check("...and the approved outcome carries the count",
              E.state()["last"].get("free_speech") == {"passage": 1},
              E.state()["last"])

        seen = {"n": 0}

        def fake_measure(pcm, mic):
            seen["n"] += 1
            return {"ok": True, "clips": len(pcm), "strong_model": False,
                    "very_strict": {"passed": 2, "of": 2, "too_short": 0,
                                    "repeat_rate": 0.0},
                    "balanced": {"passed": 2, "of": 2, "too_short": 0,
                                 "repeat_rate": 0.0},
                    "per_clip": [{"score": 0.7}] * len(pcm)}

        raw = json.dumps({"mode": "measure", "mic": "phone", "clips": b64(clips(2)),
                          "free_speech": ["day", "day"]}).encode()
        code, out = E.stage(raw, measure_fn=fake_measure)
        check("mode=measure accepts the field and answers the counts",
              code == 200 and out.get("free_speech") == {"day": 2}
              and seen["n"] == 1, (code, out.get("free_speech")))
        check("...and keeps only those counts in measure_last",
              E.state()["measure_last"].get("free_speech") == {"day": 2},
              E.state()["measure_last"])
        code, out = E.stage(json.dumps({"mode": "measure", "mic": "phone",
                                        "clips": b64(clips(2))}).encode(),
                            measure_fn=fake_measure)
        check("a measure body without the field is the old answer, key for key",
              code == 200 and "free_speech" not in out
              and "free_speech" not in E.state()["measure_last"], out.keys())
        code, out = E.stage(json.dumps({"mode": "measure", "mic": "phone",
                                        "clips": b64(clips(2)),
                                        "free_speech": ["poem", None]}).encode(),
                            measure_fn=fake_measure)
        check("measure refuses an unknown prompt in words, not silently",
              code == 400 and "does not know" in out["error"]
              and str(T.FREE_SPEECH[0]["id"]) in out["error"], (code, out))


# ----------------------------- 7. plain-language refusals -------------

def t_every_bad_list_is_a_400_in_plain_words():
    cases = [
        ("not a list", "introduce",
         lambda e: "one entry per clip" in e),
        ("wrong length", [None, "day"],
         lambda e: "2 entries" in e and "3 clips" in e),
        ("an unknown prompt", [None, None, "poem"],
         lambda e: "does not know" in e and "introduce" in e and "day" in e
         and "passage" in e),
        ("a number for a prompt", [None, None, 5],
         lambda e: "not a prompt name" in e),
        ("an object for a prompt", [None, None, {"id": "day"}],
         lambda e: "not a prompt name" in e),
    ]
    with Temp():
        for label, value, want in cases:
            code, out = send(body(1, clips(3), value))
            check(f"{label}: 400, nothing held",
                  code == 400 and E._SESSION is None and not E._PENDING,
                  (code, out))
            check(f"{label}: the sentence says what to send",
                  want(out.get("error", "")), out)
            check(f"{label}: the refused value itself is not echoed back",
                  "poem" not in out.get("error", ""), out.get("error"))
    with Temp():
        code, out = send(body(1, clips(3), ["", "", ""], finish=True))
        check("an all-empty list is the old body: one card, no counts",
              code == 202 and "free_speech" not in E.state()["last"], (code, out))
        code, out = send(body(1, None, ["day"], finish=True))
        check("labels on a finish with no clips: 400 in words",
              code == 400 and "beside" in out["error"], (code, out))
        gate, rec = Gate(Verdict(True, outcome="approved")), Rec()
        code, out = send(body(1, clips(3), ["poem", None, None]), gate=gate, rec=rec)
        check("a bad list raises no card and enrols nothing",
              code == 400 and not gate.calls and not rec.calls, (code, gate.calls))
    with Temp(), mock.patch.object(T, "FREE_SPEECH", ()):
        code, out = send(body(1, clips(3), ["introduce", None, None]))
        check("a PC with no prompts refuses the field in words", code == 400
              and "no free-speech prompts" in out["error"], (code, out))


# -------------------- 8. never in the sealed voice profile ------------

def t_the_prompt_names_never_reach_the_voice_profile():
    with Temp(), semantic_voice(V):
        gate = Gate(Verdict(True, outcome="approved"))
        calls, patched = audited()
        raw = json.dumps({"mode": "train", "round": 1, "mic": "phone",
                          "clips": b64(clips(5)),
                          "free_speech": [None, None, "introduce", "day", "passage"],
                          "finish": True}).encode()
        with patched:
            code, out = E.stage(raw, gate=gate, tier_of=ask, spawn=run_sync,
                                wake_check=lambda c, m: "skipped in this test")
        prof = V.profile_path("phone")
        check("approved: the REAL enrolment wrote the phone's voice profile",
              code == 202 and prof.is_file(), (code, prof))
        raw = prof.read_bytes()
        check("the profile holds no prompt name and no free_speech field - it is "
              "not biometric material",
              b"introduce" not in raw and b"passage" not in raw
              and b"free_speech" not in raw, raw[:160])
        check("the receipt still has the counts, on the card's stored detail",
              gate.calls and gate.calls[0][1].get("free_speech") ==
              {"introduce": 1, "day": 1, "passage": 1}, gate.calls[0][1]
              if gate.calls else None)
        staged = at(calls, "voice.training.staged")
        check("the audit trail has the counts too",
              staged and staged[0].get("free_speech") ==
              {"introduce": 1, "day": 1, "passage": 1}, staged)
        check("the enrolled outcome has the counts; the audio is gone",
              E.state()["last"].get("free_speech") ==
              {"introduce": 1, "day": 1, "passage": 1} and E._PENDING is None,
              E.state()["last"])


if __name__ == "__main__":
    for fn in (t_the_plan_names_the_ids_and_status_advertises_the_field,
               t_a_body_without_the_field_is_exactly_the_old_body,
               t_train_holds_each_label_with_its_round,
               t_the_one_card_carries_counts_and_only_counts,
               t_deny_timeout_and_expiry_drop_the_labels,
               t_the_one_shot_body_and_measure_accept_it,
               t_every_bad_list_is_a_400_in_plain_words,
               t_the_prompt_names_never_reach_the_voice_profile):
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
