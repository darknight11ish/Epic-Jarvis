"""test_find_phone.py - "ring my phone" (jarvis_find_phone.py; the owner's
choice of the research audit's idea 7, 2026-09-28).

    python3 backend/test_find_phone.py

Runs anywhere; the event bus is a list here. What it proves:

1. ONE event, `ring_phone`, carrying no words at all - an id, "ring" or
   "stop", when it was sent, until when, and for how long - so a phone can
   refuse one that is stale or replayed (net/FindPhone.kt).
2. Saying it twice in quick succession sends one ring, not two; "stop
   ringing" sends a stop for that ring only while it could still ring.
3. The answer never pretends: every connected phone rings (they share one
   pairing key), and naming a phone says so.
4. The fast path answers it without the AI model and with no card, and
   "where's my phone" is ours but "find my phone charger" is not.
5. jarvis_find_phone.py never imports jarvis_gate: there is no card to ask
   for, by construction.
"""
from __future__ import annotations

import ast
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_find_phone.py", "jarvis_quick.py")
import os  # noqa: E402
import tempfile  # noqa: E402
_TMP = tempfile.mkdtemp(prefix="jarvis-find-phone-")
os.environ["JARVIS_SCHEDULE_DB"] = os.path.join(_TMP, "schedule.db")
os.environ["OPENJARVIS_CONFIG_DIR"] = _TMP
import jarvis_find_phone as FP  # noqa: E402
import jarvis_quick as Q  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def t_one_event_with_no_words():
    FP._reset_for_tests()
    sent = []
    out = FP.ring(now=1000.0, publish=lambda k, d: sent.append((k, d)))
    check("one event", len(sent) == 1 and sent[0][0] == FP.EVENT == "ring_phone")
    d = sent[0][1]
    check("its fields: an id, ring, when, until when, how long - nothing else",
          set(d) == {"id", "state", "at", "until", "seconds"} and d["state"] == "ring"
          and d["at"] == 1000.0 and d["until"] == 1000.0 + FP.RING_SECONDS
          and d["seconds"] == FP.RING_SECONDS and d["id"].startswith("r"), str(d))
    check("the answer says it rings for a minute, even on silent, with Stop",
          out["ok"] and out["said"] == FP.RINGING and "silent" in out["said"]
          and "Stop" in out["said"])
    again = FP.ring(now=1002.0, publish=lambda k, d: sent.append((k, d)))
    check("said twice in a moment: one ring", len(sent) == 1 and again["said"] == FP.ALREADY)
    FP.ring(now=1000.0 + FP.AGAIN_AFTER + 1, publish=lambda k, d: sent.append((k, d)))
    check("said again later: a new ring, a new id", len(sent) == 2
          and sent[1][1]["id"] != sent[0][1]["id"])


def t_stop():
    FP._reset_for_tests()
    sent = []
    check("nothing ringing: says so, sends nothing",
          FP.stop(now=5.0, publish=lambda k, d: sent.append((k, d)))["said"] == FP.NOT_RINGING
          and sent == [])
    FP.ring(now=10.0, publish=lambda k, d: sent.append((k, d)))
    out = FP.stop(now=20.0, publish=lambda k, d: sent.append((k, d)))
    check("stop: for that ring only", out["said"] == FP.STOPPED and sent[-1][1]["state"] == "stop"
          and sent[-1][1]["id"] == sent[0][1]["id"])
    check("a second stop sends nothing more",
          FP.stop(now=21.0, publish=lambda k, d: sent.append((k, d)))["said"] == FP.NOT_RINGING
          and len(sent) == 2)
    FP.ring(now=100.0, publish=lambda k, d: sent.append((k, d)))
    check("after its minute it is not ringing any more",
          FP.stop(now=100.0 + FP.RING_SECONDS + 1,
                  publish=lambda k, d: sent.append((k, d)))["said"] == FP.NOT_RINGING)


def t_honest_about_which_phone():
    FP._reset_for_tests()
    out = FP.ring(named=True, now=1.0, publish=lambda k, d: None)
    check("naming a phone: says every connected phone rings",
          out["said"] == FP.RINGING_NAMED and "cannot tell your phones apart" in out["said"])

    def broken(k, d):
        raise RuntimeError("no bus")
    FP._reset_for_tests()
    out = FP.ring(now=1.0, publish=broken)
    check("no bus: a plain sentence, never a raise", out["ok"] is False and out["said"] == FP.NO_BUS)


def t_the_fast_path():
    for said, name, named in (("ring my phone", "phone_ring", False),
                              ("find my phone", "phone_ring", False),
                              ("Where's my phone?", "phone_ring", False),
                              ("I can't find my phone", "phone_ring", False),
                              ("ring my work phone", "phone_ring", True),
                              ("stop ringing my phone", "phone_stop", None)):
        i = Q.match(said)
        check(f"ours: {said!r}", i is not None and i.name == name
              and (named is None or i.f.get("named") is named), str(i and (i.name, i.f)))
    for said in ("call my mum's phone", "ring my sister's mobile", "call my mum phone",
                 "find my dad's phone"):
        i = Q.match(said)
        check(f"someone else's phone is not the owner's: {said!r}",
              i is None or i.name != "phone_ring", str(i and (i.name, i.f)))
    for said in ("find my phone charger", "call my mum", "ring the doctor"):
        i = Q.match(said)
        check(f"not ours: {said!r}", i is None or not i.name.startswith("phone_"))
    FP._reset_for_tests()
    sent = []
    real = FP._default_publish
    FP._default_publish = lambda k, d: sent.append((k, d))
    try:
        res = Q.answer("ring my phone")
    finally:
        FP._default_publish = real
    check("answered without the model, no card, one event",
          res is not None and res.reply == FP.RINGING and len(sent) == 1)
    route = Q.route_fields(res)
    check("the route says it was answered here", route["lane"] == Q.LANE and route["quick"] ==
          "phone_ring")


def t_never_a_card_by_construction():
    src = (HERE / "jarvis_find_phone.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    names = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names} | {
        n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    check("jarvis_find_phone.py never imports jarvis_gate", "jarvis_gate" not in names)
    check("... nor opens a socket", "socket" not in names and "urllib" not in src)


if __name__ == "__main__":
    for fn in (t_one_event_with_no_words, t_stop, t_honest_about_which_phone, t_the_fast_path,
               t_never_a_card_by_construction):
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
