"""test_surface_origin.py - "where am I talking from?" answered from the header.

    python3 backend/test_surface_origin.py

THE OWNER'S FIELD TEST (2026-11-01). The desktop HUD was asked "where am I
talking from?" and answered as if it were a physical-location question ("I
don't have access to your location data or GPS"). The phone answered it
correctly only by luck of its model. The app is already known: both clients
send `X-Jarvis-Surface`, and jarvis_surface reads it once per request. This
suite proves the new deterministic lane on top of that one fact:

  * every question shape the owner used gets the desktop sentence when the
    request came from the desktop program, the phone sentence when it came
    from the Android app, and ONE honest sentence ("this request did not say
    which app it came from") when no header came - never a guess, and never a
    word about GPS or a place;
  * a leading "hey"/"jarvis" and a trailing "?" are the same question;
  * the near-misses ("where am I", "where am I located", "where am I right
    now", "what is my location", "where is my phone", "which apps do you
    support", "which app can use the second card", "which app opens my
    notes") are NOT answered by this lane - a miss goes to the model, which
    is the old behaviour;
  * the same request twice gives the same sentence;
  * the lane raises no card, changes nothing, and only reads the header.

Fake headers are given to `jarvis_surface.remember()`, the same door the
shipped origin gate uses, and to `set_current()`; every one is reset
afterwards. The quick path imports the scheduler on its first answer, so this
runs against a throwaway database, never the owner's own schedule.
"""
from __future__ import annotations

import os
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
REPO = HERE.parent

WORK = Path(tempfile.mkdtemp(prefix="jarvis-surface-origin-"))
os.environ["JARVIS_SCHEDULE_DB"] = str(WORK / "schedule.db")
os.environ["OPENJARVIS_HOME"] = str(WORK)
os.environ["OPENJARVIS_CONFIG_DIR"] = str(WORK)
os.environ.pop("JARVIS_BACKEND", None)

#: The owner's requirement, word for word. The constants below are checked
#: against these, not the other way round, so an edit to the product's own
#: words has to be a deliberate edit here too.
DESKTOP_WORDS = "You are talking to me from the desktop program on your PC."
PHONE_WORDS = "You are talking to me from the Jarvis app on your Android phone."
UNKNOWN_WORDS = ("This request did not say which app it came from, so I cannot "
                 "tell whether you are talking to me from the phone or the "
                 "desktop program.")

#: Every question shape the owner used (2026-11-01), written without the
#: leading "hey"/"jarvis" and without "?" - those are separate checks below.
ASKED = (
    "where am i talking from",
    "where am i talking from right now",
    "where am i talking to you from",
    "where am i asking from",
    "where am i chatting from",
    "which app am i talking from",
    "which app am i using",
    "which app am i on",
    "what app am i using",
    "what app am i on",
    "which device am i using",
    "which device am i talking from",
    "what device am i on",
    "am i on my phone or pc",
    "am i on my phone or my pc",
    "am i talking from my phone or my pc",
    "am i talking from the phone or the pc",
    "am i on the phone or the desktop",
    "am i talking from the desktop or the phone",
    "am i on the pc or the phone",
)

#: Must NOT be answered by this lane. The first six are location questions
#: that keep going to the model; the last two belong to existing lanes (the
#: phone's ring and the feature guide) and stay there.
NEAR_MISSES = (
    "where am i",
    "where am i located",
    "where am i right now",
    "what is my location",
    "where is my phone",
    "which apps do you support",
    "which app can use the second card",
    "which app opens my notes",
)

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(("ok   " if cond else "FAIL ") + name
          + (("\n        " + detail) if detail and not cond else ""))


def _body(text):
    return {"messages": [{"role": "user", "content": text, "provenance": "typed"}],
            "conversation_id": "abcdefgh-surface-origin"}


def main():
    import jarvis_schedule as SCH
    import jarvis_quick as Q
    import jarvis_surface as S

    sched = SCH.Scheduler(WORK / "schedule.db")

    def ask(text):
        return Q.answer_turn(_body(text), sched=sched)

    # --- 1. The three sentences are the owner's requirement. ----------------
    check("words: the desktop sentence is the pinned one",
          Q.SURFACE_ORIGIN_DESKTOP == DESKTOP_WORDS, Q.SURFACE_ORIGIN_DESKTOP)
    check("words: the phone sentence is the pinned one",
          Q.SURFACE_ORIGIN_PHONE == PHONE_WORDS, Q.SURFACE_ORIGIN_PHONE)
    check("words: the unknown sentence is the pinned one",
          Q.SURFACE_ORIGIN_UNKNOWN == UNKNOWN_WORDS, Q.SURFACE_ORIGIN_UNKNOWN)
    check("words: the unknown sentence never claims a place or a GPS",
          "gps" not in UNKNOWN_WORDS.lower()
          and "location" not in UNKNOWN_WORDS.lower()
          and "did not say which app" in UNKNOWN_WORDS)
    check("words: the unknown sentence is ONE sentence",
          UNKNOWN_WORDS.count(".") == 1 and "?" not in UNKNOWN_WORDS)

    # --- 2. From the desktop program, every shape says the desktop. ---------
    S.set_current(S.DESKTOP)
    try:
        for text in ASKED:
            r = ask(text)
            check(f"desktop: {text!r}", r is not None
                  and r.intent == "surface_origin" and r.reply == DESKTOP_WORDS,
                  f"intent={getattr(r, 'intent', None)!r} "
                  f"reply={getattr(r, 'reply', None)!r}")
    finally:
        S.reset()

    # --- 3. From the Android app (via the header door), every shape says the
    # phone. `remember()` is the same function the shipped origin gate calls.
    try:
        for text in ASKED:
            surface = S.remember({"X-Jarvis-Surface": "phone"})
            r = ask(text)
            check(f"phone: {text!r} (remembered {surface})",
                  surface == S.PHONE and r is not None
                  and r.intent == "surface_origin" and r.reply == PHONE_WORDS,
                  f"surface={surface!r} reply={getattr(r, 'reply', None)!r}")
    finally:
        S.reset()

    # --- 4. With no header, the answer says so - it does not guess. ---------
    try:
        S.remember({})
        for text in ASKED:
            r = ask(text)
            check(f"unknown: {text!r}", r is not None
                  and r.intent == "surface_origin" and r.reply == UNKNOWN_WORDS,
                  f"intent={getattr(r, 'intent', None)!r} "
                  f"reply={getattr(r, 'reply', None)!r}")
    finally:
        S.reset()

    # --- 5. A leading "hey"/"jarvis" and a trailing "?" are the same. -------
    S.set_current(S.DESKTOP)
    try:
        for text in ("Hey Jarvis, where am I talking from?",
                     "jarvis which app am i using",
                     "Where am I talking from right now?"):
            r = ask(text)
            check(f"same question: {text!r}", r is not None
                  and r.intent == "surface_origin" and r.reply == DESKTOP_WORDS,
                  getattr(r, "reply", None))
    finally:
        S.reset()

    # --- 6. The near-misses are NOT this lane's. ----------------------------
    # `Q.match` decides the intent before `run()`; this lane answers only the
    # "surface_origin" name, so a near-miss that matches something else (or
    # nothing) cannot reach it. Where nothing matches, the turn must still go
    # to the model (None) - the old behaviour.
    for text in NEAR_MISSES:
        got = Q.match(text)
        check(f"near-miss: {text!r} is not the surface lane",
              got is None or got.name != "surface_origin",
              f"got {getattr(got, 'name', None)!r}")
        check(f"near-miss: {text!r} is not matched by the surface regex",
              Q._surface_origin(Q.normalize_spoken_command(text)) is None)
        if got is None:
            r = ask(text)
            check(f"near-miss end to end: {text!r} goes to the model",
                  r is None, f"got intent={getattr(r, 'intent', None)!r}")

    # --- 7. Deterministic: the same request twice, same words. --------------
    S.set_current(S.PHONE)
    try:
        first = ask("where am i talking from")
        second = ask("where am i talking from")
    finally:
        S.reset()
    check("deterministic: the same phone request answers the same twice",
          first is not None and second is not None
          and first.reply == second.reply == PHONE_WORDS,
          f"{getattr(first, 'reply', None)!r} vs {getattr(second, 'reply', None)!r}")

    # --- 8. Read-only: no card, no receipt, nothing to undo. ----------------
    check("read-only: the intent is in READ_ONLY_INTENTS",
          "surface_origin" in Q.READ_ONLY_INTENTS)
    S.set_current(S.DESKTOP)
    try:
        r = ask("which device am i using")
    finally:
        S.reset()
    check("read-only: the answer changed nothing",
          r is not None and r.intent == "surface_origin"
          and r.made == [] and r.ids == [] and r.open_settings is None,
          f"made={getattr(r, 'made', None)!r} ids={getattr(r, 'ids', None)!r}")

    # --- 9. The shipped twin is byte-identical. -----------------------------
    a = (REPO / "backend" / "jarvis_quick.py").read_bytes()
    b = (REPO / "jarvis-backend" / "jarvis_quick.py").read_bytes()
    check("twin: jarvis_quick.py is identical in both copies", a == b)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        FAILED.append("the suite itself raised")
    print()
    if FAILED:
        print(f"{len(PASSED)} passed, {len(FAILED)} FAILED")
        for name in FAILED:
            print(f"  FAIL {name}")
        sys.exit(1)
    print(f"{len(PASSED)} passed, 0 failed")
