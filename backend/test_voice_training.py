"""test_voice_training.py - the 2026-10-18 voice-training redesign (backend).

    python3 backend/test_voice_training.py

What it proves:
 1. PHRASES: a phonetically balanced, varied reading set (vowel/consonant
    coverage, short/medium/long), 2-3 natural free-speech prompts, and a
    SEPARATE fixed wake-word set - never mixed into voice-print material.
 2. CONDITION ROUNDS: close; 2-3 m on a table; background noise; another
    room/time. Old stored names map forwards. Enrollment reports four rounds
    and exposes the plan + limits through state().
 3. LIVE ADAPTATION: only after a clean, high-confidence Live verification;
    never from side talk, refusals, crisis turns, short clips or non-Live
    sources; per-condition and total caps; a drift guard; a re-anchor; the
    owner-visible count and reset.
 4. PER-CONDITION THRESHOLDS + HELD-OUT EER/FRR: computed only from score rows;
    insufficient rows get no number and no threshold is applied by measure.
 5. mode=measure carries the held-out report shape and says it applied nothing.
"""
from __future__ import annotations

import base64
import io
import json
import os
import sys
import tempfile
import traceback
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_voice_training.py", "jarvis_voice_enroll.py")

import jarvis_voice_training as T  # noqa: E402
import jarvis_voice_enroll as E  # noqa: E402

PASSED, FAILED = [], []
TMP = Path(tempfile.mkdtemp(prefix="jarvis-voice-training-"))
os.environ["JARVIS_VOICE_TRAINING_DIR"] = str(TMP)


def check(name, cond, detail=""):
    ok = bool(cond)
    (PASSED if ok else FAILED).append(name)
    print(f"{'ok   ' if ok else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not ok else ""))


def fresh():
    for p in TMP.iterdir():
        if p.is_file():
            p.unlink()


def wav_b64(seconds=1.0):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as h:
        h.setnchannels(1)
        h.setsampwidth(2)
        h.setframerate(16000)
        h.writeframes(b"\x00\x40" * int(16000 * seconds))
    return base64.b64encode(buf.getvalue()).decode("ascii")


# ============================================================ 1. phrases


def t_phrases_are_balanced_varied_and_separate_from_wake_words():
    plan = T.plan()
    read = plan["read_phrases"]
    free = plan["free_speech"]
    wake = plan["wake_phrases"]
    check("at least 12 varied reading phrases", len(read) >= 12, len(read))
    texts = [p["text"] for p in read]
    check("no repeated reading phrase (the old repeated sentence is gone)",
          len(set(texts)) == len(texts), len(texts) - len(set(texts)))
    foci = {f for p in read for f in p.get("focus", ())}
    check("covers vowels", "vowels" in foci, foci)
    check("...and consonants/clusters", bool({"consonants", "clusters"} & foci), foci)
    lengths = set()
    for p in read:
        n = len(p["text"].split())
        lengths.add("short" if n <= 4 else "long" if n >= 12 else "medium")
    check("spans short, medium and long sentences", lengths == {"short", "medium", "long"},
          lengths)
    check("2-3 natural free-speech prompts", 2 <= len(free) <= 3, len(free))
    check("...each with a plain prompt and a real length window",
          all(p.get("text") and isinstance(p.get("seconds"), tuple)
              and 5 <= p["seconds"][0] < p["seconds"][1] <= 60 for p in free), free)
    check("free speech asks for real speaking style, not reading only",
          any("own words" in p["text"] for p in free), free)
    check("the wake words are a SEPARATE fixed set", wake == ["hey Jarvis"], wake)
    check("...and no training prompt is only the wake words",
          all("hey jarvis" not in p["text"].lower() for p in read + free),
          read + free)
    check("the plan says its limits and that the wake words are separate",
          plan["max_clips_per_round"] == 12 and plan["min_clips"] == 3
          and "wake words are kept separate" in plan["words"], plan["words"])


# ============================================================ 2. conditions/rounds


def t_condition_rounds_and_enrollment_state():
    ids = [c["id"] for c in T.CONDITIONS]
    check("four condition rounds, in training order",
          ids == ["close", "table", "noise", "room"], ids)
    asks = " ".join(c["ask"] for c in T.CONDITIONS).lower()
    check("far condition says 2-3 m on a table", "two to three metres" in asks
          and "table" in asks, asks)
    check("...noise says fan or TV", "fan" in asks and "tv" in asks, asks)
    check("...room says another room or time", "another room" in asks
          and "different time" in asks, asks)
    check("old stored names map forwards",
          T.clean_condition("far") == "table" and T.clean_condition("general") == "close"
          and T.clean_condition("room") == "room", 
          (T.clean_condition("far"), T.clean_condition("general")))
    check("the enrollment's rounds are the four conditions",
          len(E.ROUNDS) == 4 and [E.ROUNDS[i][0] for i in sorted(E.ROUNDS)]
          == ["close", "table", "noise", "room"], E.ROUNDS)
    state = E.state()
    check("state() exposes the phrase/free-speech/condition plan",
          state.get("training", {}).get("read_phrases")
          and state["training"].get("free_speech")
          and state["training"].get("wake_phrases") == ["hey Jarvis"], state.get("training"))
    check("...and the owner-visible adaptation count and caps",
          state.get("adaptation", {}).get("caps")
          == {"per_condition": T.MAX_PER_CONDITION, "total": T.MAX_TOTAL},
          state.get("adaptation"))
    check("limits name four rounds", state["limits"]["rounds"] == 4, state["limits"])


# ============================================================ 3. live adaptation


def t_adaptation_gate_never_takes_bad_context():
    good = dict(owner=True, score=0.80, threshold=0.55, condition="noise",
                seconds=3.0, live=True)
    check("a clean high-confidence Live owner clip may adapt",
          T.should_adapt(**good).get("ok") is True, T.should_adapt(**good))
    bad_cases = {
        "a non-owner": dict(good, owner=False),
        "a refusal": dict(good, refused=True),
        "a crisis turn": dict(good, crisis=True),
        "side talk": dict(good, side_talk=True),
        "a non-Live source": dict(good, live=False),
        "a short clip": dict(good, seconds=1.0),
        "a score only just over the bar": dict(good, score=0.56),
    }
    for why, kwargs in bad_cases.items():
        got = T.should_adapt(**kwargs)
        check(f"never adapts from {why}", got.get("ok") is False, got)
    check("high_confidence needs the margin", T.high_confidence(0.62, 0.55) is False
          and T.high_confidence(0.64, 0.55) is True)


def t_caps_drift_reanchor_and_reset():
    fresh()
    vector = [1.0, 0.0, 0.0]
    anchor = [1.0, 0.0, 0.0]
    for n in range(T.MAX_PER_CONDITION):
        got = T.record_adaptation(vector, condition="close", score=0.9,
                                  threshold=0.5, anchor=anchor)
        check(f"live addition {n + 1} is accepted", got.get("ok") is True, got)
    got = T.record_adaptation(vector, condition="close", score=0.9,
                              threshold=0.5, anchor=anchor)
    check("the per-condition cap is enforced", got.get("ok") is False
          and "already has" in got.get("why", ""), got)
    got = T.record_adaptation([0.0, 1.0, 0.0], condition="noise", score=0.9,
                              threshold=0.5, anchor=anchor)
    check("a drifted clip is refused before any count changes",
          got.get("ok") is False and "sounds different" in got.get("why", ""), got)
    state = T.read_state()
    check("the drift refusal did not bump the counts",
          state["counts"].get("noise") is None, state)
    check("the owner-visible status counts the additions",
          T.status()["counts"].get("close") == T.MAX_PER_CONDITION, T.status())
    T.reset_adaptation("close")
    check("the owner's reset zeroes that condition", "close" not in T.read_state()["counts"],
          T.read_state())
    check("...and records that a reset happened", T.status()["resets"] >= 1, T.status())
    got = T.reanchor()
    check("re-anchor zeroes every condition and records it",
          got.get("ok") is True and T.read_state()["counts"] == {}
          and T.status()["reanchors"] >= 1, T.status())


def t_adaptation_reset_mode_exists():
    got = E.reset_adaptation("noise")
    check("mode adapt-reset is accepted and answers 200", got[0] == 200, got)
    check("...and reports the zeroed adaptation state",
          isinstance(got[1].get("adaptation"), dict), got[1])


# ============================================================ 4. measurement math


def t_held_out_eer_frr_and_thresholds():
    rows = []
    # close: owner clearly higher than others
    for n in range(12):
        rows.append({"condition": "close", "owner": True, "score": 0.82 + n * 0.005})
        rows.append({"condition": "close", "owner": False, "score": 0.30 - n * 0.002})
    # noise: overlapping, but enough rows
    for n in range(12):
        rows.append({"condition": "noise", "owner": True, "score": 0.55 + n * 0.01})
        rows.append({"condition": "noise", "owner": False, "score": 0.48 + n * 0.01})
    report = T.held_out(rows)
    check("the held-out report is available with enough rows",
          report.get("available") is True, report)
    close = report["conditions"]["close"]
    check("a cleanly separated condition has a low EER",
          close["available"] and close["eer"] <= 0.1, close)
    check("...and its FRR/FAR are reported as numbers",
          isinstance(close["frr"], (int, float)) and isinstance(close["far"], (int, float)),
          close)
    noise = report["conditions"]["noise"]
    check("an overlapping condition gets a real, non-zero EER",
          noise["available"] and noise["eer"] > 0.0, noise)
    check("a condition with no rows is absent, not guessed",
          "room" not in report["conditions"], report["conditions"])
    thin = [{"condition": "close", "owner": True, "score": 0.9},
            {"condition": "close", "owner": False, "score": 0.2}]
    thin_report = T.held_out(thin)
    check("too few rows is 'insufficient', not a number",
          thin_report["conditions"]["close"]["available"] is False
          and "not enough measured rows" in thin_report["conditions"]["close"]["why"],
          thin_report)
    sug = T.suggest_thresholds(rows)
    check("the measured suggestion returns one threshold per measured condition",
          sug.get("ok") is True and set(sug["thresholds"]) == {"close", "noise"}, sug)
    check("...and each is a usable bar", all(0.05 <= v <= 0.99
          for v in sug["thresholds"].values()), sug)
    check("insufficient data never suggests a threshold",
          T.suggest_thresholds(thin).get("ok") is False, T.suggest_thresholds(thin))


def t_measure_reports_held_out_and_applies_nothing():
    clips = [wav_b64(1.0) for _ in range(4)]
    conditions = ["close", "table", "noise", "room"]

    def fake_measure(pcm, mic):
        return {"ok": True, "clips": 4, "strong_model": False,
                "per_clip": [{"seconds": 1.0, "score": 0.82, "very_strict": True,
                              "balanced": True} for _ in range(4)],
                "very_strict": {"passed": 4, "of": 4, "too_short": 0, "repeat_rate": 0.0},
                "balanced": {"passed": 4, "of": 4, "too_short": 0, "repeat_rate": 0.0},
                "other_scores": [0.30, 0.32, 0.28, 0.35]}

    code, body = E.measure({"clips": clips, "mic": "phone", "conditions": conditions},
                           measure_fn=fake_measure)
    check("mode=measure with conditions answers 200", code == 200, (code, body))
    check("...and carries the held-out report shape",
          isinstance(body.get("held_out"), dict)
          and "conditions" in body["held_out"], body.get("held_out"))
    check("...and says the thresholds were NOT applied",
          body.get("thresholds_applied") is False, body.get("thresholds_applied"))
    check("...with a measured-suggestion field that is explicit either way",
          isinstance(body.get("suggested_thresholds"), dict), body.get("suggested_thresholds"))


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn) and fn.__module__ == "__main__":
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
