"""jarvis_voice_training.py - the backend half of the voice-training redesign.

Owner-approved build, 2026-10-18: DIVERSE phrase material, CONDITION rounds,
LIVE adaptation after high-confidence Live verification, PER-CONDITION
thresholds chosen only from measured numbers, and a held-out EER/FRR evaluation
in `mode=measure`. The training SCREENS (desktop and phone) are the next slice;
this module is what they will read and what the backend owns today.

WHAT THIS MODULE OWNS

  * `plan()` - the phrase material the apps will show:
      - `read_phrases`: a phonetically balanced, varied set (every English vowel
        and the common consonant clusters, short / medium / long sentences),
        written to be read aloud, not the old repeated sentence.
      - `free_speech`: 2-3 prompts ("introduce yourself", "describe your day",
        "read this passage") so enrollment hears the owner's real speaking
        style, not only reading voice.
      - `wake_phrases`: a SEPARATE, fixed set. The wake detector has its own
        words and they are not mixed into the voice-print material.
  * `CONDITIONS` - close; 2-3 m away on a table; background noise (fan/TV);
    another room/time. Old stored names map forwards ("far" -> "table").
  * live adaptation RULES and small state, pure and local:
      - only after a high-confidence, clean Live verification (owner, score
        above the bar by a margin, Live source, not side talk, not a crisis
        turn, not a refusal, not too short);
      - per-condition caps and a total cap;
      - a drift guard (a clip below the cosine floor to the enrollment anchor
        is refused, so one noisy day cannot become the print);
      - a periodic re-anchor back to the original enrollment;
      - an owner-visible count and reset.
  * `held_out()` / `suggest_thresholds()` - score rows in, per-condition
    FRR/FAR/EER out. Thresholds are RETURNED only when every condition has
    enough owner and other-voice rows; nothing here changes a default by
    itself. `mode=measure` reports this shape; the owner's "use measured
    numbers" card is the caller.

WHAT THIS MODULE DOES NOT DO

  * It does not load, embed or store audio: vectors in, numbers out.
  * It does not write the voice profile itself. `jarvis_voice_enroll` (and a
    later Live call site) call it, then write through the EXISTING sealed
    profile writer.
  * It does not decide a condition from audio: the caller says which condition
    the clip belongs to (a condition round in training, or the Live session's
    own context). A live condition detector is not built.
  * The current voice check still applies ONE global threshold at verify time:
    the per-condition numbers are selected here and reported by measure, and a
    later slice must pass the clip's condition into the check to use them.

Standard library only. Local numbers only; no network, no audio at rest here.
"""
from __future__ import annotations

import json
import math
import os
import tempfile
import time
from pathlib import Path
from typing import Optional

# --------------------------------------------------------------------------
#   Phrase material (the apps show these; the wake words stay separate)
# --------------------------------------------------------------------------

#: The fixed wake words. The wake detector has its own vocabulary; these are
#: NOT training prompts and must never be mixed into the voice-print set.
WAKE_PHRASES = ("hey Jarvis",)

#: Phonetically balanced, varied reading material. `focus` is what the phrase
#: exercises, kept honest and small: every English vowel, the consonant
#: clusters that matter for a phone microphone, and a spread of lengths.
READ_PHRASES = (
    {"id": "vowel-1", "text": "The blue boat floats slowly over the cold deep water.",
     "focus": ("vowels", "long"), "words": 10},
    {"id": "vowel-2", "text": "Please speak clearly about the meeting on Thursday.",
     "focus": ("vowels", "consonants"), "words": 7},
    {"id": "vowel-3", "text": "My eyes see a bright fire by the white gate.",
     "focus": ("vowels", "diphthongs"), "words": 10},
    {"id": "consonant-1", "text": "She sells fresh fish from the shelf by the shore.",
     "focus": ("consonants", "fricatives"), "words": 10},
    {"id": "consonant-2", "text": "Six thick sticks stand beside the strong tree.",
     "focus": ("consonants", "clusters"), "words": 8},
    {"id": "consonant-3", "text": "Judge the quick brown fox before the jazz band.",
     "focus": ("consonants", "clusters", "short"), "words": 9},
    {"id": "short-1", "text": "Light the lamp.", "focus": ("short", "consonants"), "words": 3},
    {"id": "medium-1", "text": "Rain falls on the roof while the kettle sings.",
     "focus": ("medium", "vowels"), "words": 9},
    {"id": "medium-2", "text": "The train to town leaves at half past eight.",
     "focus": ("medium", "diphthongs"), "words": 9},
    {"id": "long-1", "text": ("On the way home I stopped at the market and bought "
                              "apples, bread and a small paper bag of rice."),
     "focus": ("long", "varied"), "words": 15},
    {"id": "long-2", "text": ("Please remember to bring the green folder to my "
                              "office before the morning meeting on Friday."),
     "focus": ("long", "varied"), "words": 13},
    {"id": "natural-1", "text": "It was a cold morning, and the car would not start.",
     "focus": ("natural", "varied"), "words": 9},
)

#: 2-3 natural free-speech prompts: real speaking style, not reading aloud.
FREE_SPEECH = (
    {"id": "introduce", "text": "Introduce yourself in your own words: who you are, "
                                "what you do, and something you like.",
     "seconds": (10, 30), "why": "natural rhythm and everyday words"},
    {"id": "day", "text": "Describe your day so far in your own words - what you "
                          "did, what you saw, what you are planning next.",
     "seconds": (10, 30), "why": "connected speech, not one short sentence"},
    {"id": "passage", "text": "Read this aloud, slowly: The morning train was late "
                              "again, so I stood at the window and watched the rain "
                              "move across the empty platform.",
     "seconds": (8, 25), "why": "a varied passage with long and short sounds"},
)

#: The condition rounds. Order matters to the training screens. `legacy` names
#: the older stored condition this one continues.
CONDITIONS = (
    {"id": "close", "label": "Close", "legacy": "general",
     "ask": "normal, close to the microphone"},
    {"id": "table", "label": "On a table, 2-3 m away", "legacy": "far",
     "ask": "about two to three metres away, on a table"},
    {"id": "noise", "label": "With background noise", "legacy": "",
     "ask": "with the fan or the TV on, as it usually is"},
    {"id": "room", "label": "Another room or time", "legacy": "room",
     "ask": "in another room, or at a different time of day"},
)
CONDITION_IDS = tuple(c["id"] for c in CONDITIONS)
_LEGACY = {c["legacy"]: c["id"] for c in CONDITIONS if c["legacy"]}
_LEGACY["general"] = "close"


def clean_condition(value) -> str:
    c = str(value or "").strip().lower()
    if c in CONDITION_IDS:
        return c
    return _LEGACY.get(c, "close")


def plan() -> dict:
    """The apps' training plan: phrases, free-speech prompts, wake words and
    conditions. Stable shape; a screen reads it and shows it."""
    return {"version": 1,
            "read_phrases": [dict(p) for p in READ_PHRASES],
            "free_speech": [dict(p) for p in FREE_SPEECH],
            "wake_phrases": list(WAKE_PHRASES),
            "conditions": [dict(c) for c in CONDITIONS],
            "min_clips": 3, "max_clips_per_round": 12,
            "words": ("Read the short sentences aloud, then speak about yourself "
                      "in your own words. Each round is recorded in a different "
                      "condition; the wake words are kept separate.")}


# --------------------------------------------------------------------------
#   Live adaptation: rules, caps, drift guard, re-anchor, counters
# --------------------------------------------------------------------------

ADAPT_FILE = "voice-adapt.json"

#: Caps: at most this many live sub-prints per condition and in total. The
#: enrollment's own sub-prints are not counted - adaptation is always a small
#: addition, never a replacement.
MAX_PER_CONDITION = 4
MAX_TOTAL = 12
#: High-confidence = above the bar by this margin, before anything is added.
HIGH_MARGIN = 0.08
#: A live clip must be at least this long to carry a usable voice.
MIN_LIVE_SECONDS = 1.5
#: The drift guard: below this cosine to the enrollment anchor it is not the
#: same voice in a different condition, it is a different voice - refuse.
DRIFT_FLOOR = 0.55
#: Re-anchor after this many live additions for one condition (back to the
#: original enrollment sub-print), and/or after this many days without one.
REANCHOR_EVERY = 8
REANCHOR_DAYS = 30.0

_EMPTY = {"version": 1, "counts": {}, "total": 0, "reanchors": 0,
          "resets": 0, "last_at": 0.0, "last_reanchor": 0.0, "reset_at": 0.0}


def _base_dir() -> Path:
    if os.environ.get("JARVIS_VOICE_TRAINING_DIR"):
        return Path(os.environ["JARVIS_VOICE_TRAINING_DIR"])
    try:
        import jarvis_framework as fw
        return Path(fw.CONFIG_DIR)
    except Exception:
        return Path(os.environ.get("OPENJARVIS_CONFIG_DIR")
                    or os.environ.get("JARVIS_CONFIG_DIR")
                    or (Path.home() / ".openjarvis"))


def adapt_path() -> Path:
    return _base_dir() / ADAPT_FILE


def _normalise(doc) -> dict:
    out = dict(_EMPTY)
    if not isinstance(doc, dict):
        return out
    counts = doc.get("counts")
    clean = {}
    if isinstance(counts, dict):
        for key, value in counts.items():
            if key in CONDITION_IDS:
                try:
                    clean[key] = max(0, int(value))
                except (TypeError, ValueError):
                    pass
    out["counts"] = clean
    for key in ("total", "reanchors", "resets"):
        try:
            out[key] = max(0, int(doc.get(key, 0)))
        except (TypeError, ValueError):
            out[key] = 0
    for key in ("last_at", "last_reanchor", "reset_at"):
        try:
            out[key] = max(0.0, float(doc.get(key, 0.0)))
        except (TypeError, ValueError):
            out[key] = 0.0
    return out


def read_state() -> dict:
    try:
        got = json.loads(adapt_path().read_text(encoding="utf-8"))
    except Exception:
        got = {}
    return _normalise(got)


def _write_state(state: dict) -> None:
    path = adapt_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp",
                              dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(_normalise(state), handle, ensure_ascii=False, indent=1,
                      sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _cosine(a, b) -> Optional[float]:
    try:
        va = [float(x) for x in a]
        vb = [float(x) for x in b]
        if not va or len(va) != len(vb):
            return None
        dot = sum(x * y for x, y in zip(va, vb))
        na = math.sqrt(sum(x * x for x in va))
        nb = math.sqrt(sum(y * y for y in vb))
        if not na or not nb:
            return None
        return max(-1.0, min(1.0, dot / (na * nb)))
    except (TypeError, ValueError):
        return None


def high_confidence(score, threshold, *, margin: float = HIGH_MARGIN) -> bool:
    """Is this a clearly-owner score, not one at the edge of the bar?"""
    try:
        s = float(score)
        t = float(threshold)
    except (TypeError, ValueError):
        return False
    if not math.isfinite(s) or not math.isfinite(t) or t <= 0:
        return False
    return s >= t + margin


def should_adapt(*, owner, score, threshold, condition, seconds,
                 live=True, side_talk=False, crisis=False, refused=False,
                 too_short=False, transcript="") -> dict:
    """The gate for one Live verification's clip. NEVER adapts on:
    a non-owner, a refusal, a crisis turn, side talk, a short clip, a non-Live
    source or a score that is only just over the bar."""
    why = ""
    if owner is not True:
        why = "the clip was not confirmed as the owner"
    elif refused or crisis:
        why = "refusals and crisis turns are never used to adapt"
    elif side_talk:
        why = "side talk is not the owner addressing Jarvis"
    elif not live:
        why = "only a Live verification may adapt the print"
    elif too_short or (isinstance(seconds, (int, float)) and seconds < MIN_LIVE_SECONDS):
        why = "the clip is too short to carry a usable voice"
    elif not high_confidence(score, threshold):
        why = "the score is not clearly above the bar"
    elif str(condition or "") and clean_condition(condition) not in CONDITION_IDS:
        why = "that is not a known recording condition"
    if why:
        return {"ok": False, "why": why}
    return {"ok": True, "condition": clean_condition(condition),
            "why": "a clean, high-confidence Live verification"}


def record_adaptation(vector, *, condition, score, threshold, anchor=None,
                      state: Optional[dict] = None,
                      now: Optional[float] = None) -> dict:
    """One high-confidence Live clip's vector, counted (and drift-checked) for
    one condition. Does NOT write the profile; the caller appends the vector
    through the existing enrollment writer and calls this for the counters.

    `anchor` is the enrollment centroid for this condition, when the caller has
    it: a vector too far from it is refused so one noisy day cannot dominate.
    """
    condition = clean_condition(condition)
    current = _normalise(state if state is not None else read_state())
    stamp = float(now if isinstance(now, (int, float)) and not isinstance(now, bool)
                  else time.time())
    count = current["counts"].get(condition, 0)
    if count >= MAX_PER_CONDITION:
        return {"ok": False, "why": f"this condition already has {MAX_PER_CONDITION} "
                                    f"live additions; re-anchor it first",
                "state": current}
    if current["total"] >= MAX_TOTAL:
        return {"ok": False, "why": f"the live additions are capped at {MAX_TOTAL}",
                "state": current}
    if anchor is not None:
        got = _cosine(vector, anchor)
        if got is not None and got < DRIFT_FLOOR:
            return {"ok": False, "why": (f"that clip sounds different from the "
                                          f"enrolled voice (closeness {got:.2f}), "
                                          f"so it was not added"), "state": current}
    reanchor = False
    if count + 1 >= REANCHOR_EVERY or (current["last_reanchor"] and
                                        (stamp - current["last_reanchor"]) >=
                                        REANCHOR_DAYS * 86400):
        reanchor = True
    current["counts"][condition] = 0 if reanchor else count + 1
    current["total"] = 0 if reanchor else current["total"] + 1
    current["last_at"] = stamp
    if reanchor:
        current["reanchors"] += 1
        current["last_reanchor"] = stamp
    _write_state(current)
    return {"ok": True, "condition": condition, "reanchor": reanchor,
            "state": current}


def reanchor(now: Optional[float] = None) -> dict:
    """Back to the original enrollment for every condition: counts zero, a
    re-anchor recorded. The caller removes the live sub-prints; enrollment
    sub-prints were never counted here."""
    current = _normalise(read_state())
    current["counts"] = {}
    current["total"] = 0
    current["reanchors"] += 1
    current["last_reanchor"] = float(now if isinstance(now, (int, float))
                                     and not isinstance(now, bool) else time.time())
    _write_state(current)
    return {"ok": True, "reanchors": current["reanchors"]}


def reset_adaptation(condition=None, now: Optional[float] = None) -> dict:
    """The owner's reset: zero the counts (and the caller drops the live
    sub-prints). Resetting one condition leaves the others alone."""
    current = _normalise(read_state())
    if condition is not None:
        current["counts"].pop(clean_condition(condition), None)
    else:
        current["counts"] = {}
    current["total"] = sum(current["counts"].values())
    current["resets"] += 1
    current["reset_at"] = float(now if isinstance(now, (int, float))
                                and not isinstance(now, bool) else time.time())
    _write_state(current)
    return {"ok": True, "state": current}


def status() -> dict:
    """The owner-visible count: per condition, caps, re-anchor and reset times."""
    current = _normalise(read_state())
    return {"available": True, "counts": dict(current["counts"]),
            "count": current["total"], "caps": {"per_condition": MAX_PER_CONDITION,
                                                 "total": MAX_TOTAL},
            "reanchors": current["reanchors"], "last_reanchor": current["last_reanchor"],
            "resets": current["resets"], "reset_at": current["reset_at"],
            "last_at": current["last_at"],
            "words": ("No Live additions yet." if not current["total"] else
                      ", ".join(f"{c}: {n}" for c, n in
                                sorted(current["counts"].items())) + " Live additions.")}


# --------------------------------------------------------------------------
#   Per-condition thresholds, and the held-out EER/FRR evaluation
# --------------------------------------------------------------------------

#: Enough rows before a condition's threshold may be suggested. Below this the
#: answer is "not enough measured data", never a guess.
MEASURE_MIN_OWNER = 10
MEASURE_MIN_OTHER = 10
THRESHOLDS = tuple(round(0.05 * i, 2) for i in range(1, 20))   # 0.05 .. 0.95


def _rates(owner_scores, other_scores, threshold) -> tuple:
    frr = (sum(1 for s in owner_scores if s < threshold) / len(owner_scores)
           if owner_scores else None)
    far = (sum(1 for s in other_scores if s >= threshold) / len(other_scores)
           if other_scores else None)
    return frr, far


def held_out(rows: list, *, thresholds: Optional[dict] = None) -> dict:
    """Per-condition FRR/FAR/EER from score rows.

    `rows` is [{"condition", "owner": true|false, "score": float}]. EER is the
    point where FRR and FAR are closest, searched over THRESHOLDS; the answer
    says how many rows each side had, and a condition with too few rows is
    reported as insufficient rather than given a number.
    """
    by = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        try:
            score = float(row.get("score"))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(score):
            continue
        cond = clean_condition(row.get("condition"))
        bucket = by.setdefault(cond, {"owner": [], "other": []})
        bucket["owner" if row.get("owner") is True else "other"].append(score)
    conditions = {}
    any_available = False
    for cond in CONDITION_IDS:
        bucket = by.get(cond)
        if not bucket:
            continue
        owner, other = bucket["owner"], bucket["other"]
        row = {"owner_rows": len(owner), "other_rows": len(other),
               "threshold": float((thresholds or {}).get(cond, 0.0)) or None}
        if len(owner) < MEASURE_MIN_OWNER or len(other) < MEASURE_MIN_OTHER:
            row.update({"available": False,
                        "why": ("not enough measured rows for this condition "
                                f"(owner {len(owner)}/{MEASURE_MIN_OWNER}, other "
                                f"{len(other)}/{MEASURE_MIN_OTHER})")})
            conditions[cond] = row
            continue
        best = None
        for t in THRESHOLDS:
            frr, far = _rates(owner, other, t)
            gap = abs((frr or 0.0) - (far or 0.0))
            if best is None or gap < best[0]:
                best = (gap, t, frr, far)
        _gap, eer_t, eer_frr, eer_far = best
        # FRR/FAR are reported at the condition's own configured bar when the
        # caller passed one, otherwise at the EER point this report found - so
        # a measured report always carries both numbers, never a blank next to
        # a threshold nobody set.
        at = row["threshold"] if row["threshold"] else eer_t
        frr, far = _rates(owner, other, at)
        row.update({"available": True, "eer": round((eer_frr + eer_far) / 2, 3),
                    "eer_threshold": eer_t, "frr": None if frr is None else round(frr, 3),
                    "far": None if far is None else round(far, 3)})
        conditions[cond] = row
        any_available = True
    return {"ok": True, "available": any_available, "conditions": conditions,
            "thresholds": {c: r["eer_threshold"] for c, r in conditions.items()
                           if r.get("available")},
            "words": ("Per-condition measured numbers." if any_available else
                      "Not enough held-out scores yet; no threshold was chosen.")}


def suggest_thresholds(rows: list, *, floor: float = 0.05) -> dict:
    """The measured suggestion, one threshold per condition. Refuses unless
    every condition with rows has enough; nothing is applied here."""
    report = held_out(rows)
    usable = {c: r for c, r in report["conditions"].items() if r.get("available")}
    if not usable:
        return {"ok": False, "why": report["words"], "report": report}
    thresholds = {}
    for cond, row in usable.items():
        thresholds[cond] = max(float(floor), min(0.99, float(row["eer_threshold"])))
    return {"ok": True, "thresholds": thresholds, "report": report,
            "words": ("Measured against held-out owner and other-voice clips; "
                      "use this only with the owner's yes.")}
