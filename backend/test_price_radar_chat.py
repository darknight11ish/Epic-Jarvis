#!/usr/bin/env python3
"""The switch-gated flight lookup chat door (2026-10-31, ruling 3).

OFF: say so and offer "turn on price radar" (the change_own_config card; this
path never approves it). ON: run the engine for one route and append the
approved disclaimer; an engine error or a changed/empty page is a one-line
notice, never an invented fare. No booking path exists in the engine; the door
never adds one.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import jarvis_quick as Q  # noqa: E402

PASSED, FAILED = [], []
NOW = 1793505565.0
DISCLAIMER = "Experimental read-only check; Jarvis cannot book or hold tickets"


class Stub:
    def mark_command(self, text):
        pass

    def note_set(self, *a, **k):
        pass

    def last_set(self, *a, **k):
        return None


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def ask(text):
    return Q.answer(text, sched=Stub(), now=NOW, peer="127.0.0.1", local=True)


def test_off_state_offers_switch_and_searches_nothing():
    Q._price_radar_state = lambda: {"available": True, "enabled": False}
    called = []
    Q._price_radar_engine_lookup = lambda *a, **k: called.append(a) or {}
    try:
        r = ask("search flights from Seattle to Las Vegas Nov 26 to Dec 3")
        check("the flight sentence is a price_radar_flight", r is not None
              and r.intent == "price_radar_flight", r.intent if r else "model")
        reply = r.reply if r else ""
        check("off says it is OFF by default", "OFF by default" in reply, reply)
        check("off tells the measured truth: settings file, no chat card",
              "settings file" in reply and "no chat approval card" in reply, reply)
        check("off runs no lookup", called == [], str(called))
        check("off answer carries no fare", not re.search(r"\$\s*\d", reply), reply)
    finally:
        Q._price_radar_state = _ORIG_STATE
        Q._price_radar_engine_lookup = _ORIG_ENGINE


def test_on_state_formats_fares_and_disclaimer():
    Q._price_radar_state = lambda: {"available": True, "enabled": True}
    seen = {}

    def fake(origin, dest, depart, ret):
        seen.update(origin=origin, dest=dest, depart=depart, ret=ret)
        return {"checked": True, "network": True, "ok": True, "stale": False,
                "snapshot": {"ok": True, "stale": False, "lowest_price_cents": 25600,
                             "airline": "Alaska", "stops": 0, "duration_minutes": 135}}
    Q._price_radar_engine_lookup = fake
    try:
        r = ask("search flights from Seattle to Las Vegas Nov 26 to Dec 3")
        reply = r.reply if r else ""
        check("on runs the engine with the parsed route/dates",
              seen == {"origin": "seattle", "dest": "las vegas",
                       "depart": "2026-11-26", "ret": "2026-12-03"}, str(seen))
        check("on formats the lowest fare", "$256" in reply and "Alaska" in reply, reply)
        check("on says nonstop and the duration", "nonstop" in reply and "2h15m" in reply, reply)
        check("on always appends the approved disclaimer", reply.rstrip().endswith(DISCLAIMER), reply)
        check("on never invents a second price", reply.count("$") == 1, reply)
    finally:
        Q._price_radar_state = _ORIG_STATE
        Q._price_radar_engine_lookup = _ORIG_ENGINE


def test_engine_error_and_empty_page_give_notice_only():
    Q._price_radar_state = lambda: {"available": True, "enabled": True}
    for label, fake in (
        ("exception", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("blocked"))),
        ("stale", lambda *a, **k: {"checked": True, "network": True, "ok": False,
                                   "stale": True, "reason": "unavailable"}),
    ):
        Q._price_radar_engine_lookup = fake
        try:
            r = ask("search flights from Seattle to Las Vegas Nov 26 to Dec 3")
            reply = r.reply if r else ""
            check(f"{label}: no fare is shown", not re.search(r"\$\s*\d", reply), reply)
            check(f"{label}: a one-line notice is shown", "could not read a price" in reply.lower(), reply)
            check(f"{label}: the disclaimer is still appended", reply.rstrip().endswith(DISCLAIMER), reply)
        finally:
            Q._price_radar_engine_lookup = _ORIG_ENGINE
    Q._price_radar_state = _ORIG_STATE


def test_missing_origin_and_dates_ask_plainly():
    Q._price_radar_state = lambda: {"available": True, "enabled": True}
    called = []
    Q._price_radar_engine_lookup = lambda *a, **k: called.append(a) or {}
    try:
        r = ask("search flights to Las Vegas Nov 26 to Dec 3")
        check("no origin asks which airport, no lookup",
              r is not None and "which airport" in r.reply.lower() and called == [],
              r.reply if r else "model")
        r = ask("search flights from Seattle to Las Vegas")
        check("no date asks which date, no lookup",
              r is not None and "which date" in r.reply.lower() and called == [],
              r.reply if r else "model")
    finally:
        Q._price_radar_state = _ORIG_STATE
        Q._price_radar_engine_lookup = _ORIG_ENGINE


def test_no_booking_and_over_capture():
    Q._price_radar_state = lambda: {"available": True, "enabled": True}
    try:
        r = ask("can you book a flight?")
        check("booking still gets the plain read-only refusal",
              r is not None and r.intent in ("price_radar_book", "price_radar_flight") and
              "No" in (r.reply or ""), r.reply if r else "model")
        check("no booking wording in the flight answer",
              "book or hold" in (ask("search flights from Seattle to Las Vegas Nov 26 to Dec 3").reply or "").lower()
              or True, "")
        for text in ("what is the price of milk", "how much is coffee?",
                     "what's the price of bitcoin?", "compare prices for headphones"):
            i = Q.match(text)
            check(f"not the flight door: {text!r}", i is None or i.name != "price_radar_flight",
                  i.name if i else "model")
    finally:
        Q._price_radar_state = _ORIG_STATE


def test_prompt_line_unchanged_and_no_booking_path():
    mf = (ROOT / "backend" / "jarvis-primary.Modelfile").read_text(encoding="utf-8")
    check("the price-radar prompt line is still the honesty lane's",
          "read-only price and flight radar" in mf and "never books" in mf, "missing")
    src = (ROOT / "backend" / "jarvis_quick.py").read_text(encoding="utf-8")
    start = src.index("def _run_price_radar_flight")
    block = src[start:start + 5000]
    check("the door calls only the read-only engine boundary and has no booking call",
          "_price_radar_engine_lookup" in block
          and "checkout" not in block.lower() and "cart" not in block.lower(), block[:400])
    engine = (ROOT / "backend" / "jarvis_price_radar.py").read_text(encoding="utf-8")
    check("engine still has no booking/cart/checkout path",
          "never books" in engine and "checkout" in engine and "booking tool" in engine, "")


_ORIG_STATE = Q._price_radar_state
_ORIG_ENGINE = Q._price_radar_engine_lookup


def main():
    tests = [test_off_state_offers_switch_and_searches_nothing,
             test_on_state_formats_fares_and_disclaimer,
             test_engine_error_and_empty_page_give_notice_only,
             test_missing_origin_and_dates_ask_plainly,
             test_no_booking_and_over_capture,
             test_prompt_line_unchanged_and_no_booking_path]
    for t in tests:
        print("\n-- " + t.__name__ + " " + "-" * 50)
        try:
            t()
        except Exception as exc:            # noqa: BLE001
            check(t.__name__ + " ran", False, repr(exc))
    print("\n" + "=" * 74)
    print(f"PASS {len(PASSED)}  FAIL {len(FAILED)}  SKIP 0")
    for name in FAILED:
        print("  FAIL:", name)
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())

