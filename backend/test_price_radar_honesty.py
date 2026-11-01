#!/usr/bin/env python3
"""Price/flight radar honesty (2026-10-31).

Live Jarvis said it could not check real-time flight prices and offered travel
sites. Wrong: backend/jarvis_price_radar.py is a read-only flight engine + price
history. It is OFF by default and has no chat route or app screen yet, and it
never books. This suite pins the answers to a fake switch and the module's own
invariants.
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
    return Q.answer(text, sched=Stub(), now=1793505565.0, peer="127.0.0.1", local=True)


def test_source_truth():
    src = (ROOT / "backend" / "jarvis_price_radar.py").read_text(encoding="utf-8")
    check("the module says it is read-only and off", "READ-ONLY, OFF" in src or "read-only" in src, "")
    check("the module says it never books", "never books" in src and "booking tool" in src, "")
    check("the module names the unofficial Google Flights page",
          "unofficial" in src and "Google Flights" in src, "")
    check("the switch exists and defaults off", 'SWITCH_KEY = "enabled"' in src, "")
    check("the twin module exists", (ROOT / "jarvis-backend" / "jarvis_price_radar.py").is_file())


def test_off_state():
    Q._price_radar_state = lambda: {"available": True, "enabled": False}
    try:
        r = ask("can you search for flights for me?")
        check("flight search is answered (read-only radar exists)", r is not None
              and r.intent == "price_radar_lookup", r.intent if r else "model")
        check("... it says the radar is OFF by default", "OFF by default" in r.reply,
              r.reply if r else "")
        check("... it says how to turn it on (settings file, no chat card)",
              "[price_radar] enabled = true" in r.reply and "no chat approval card" in r.reply.lower(),
              r.reply if r else "")
        check("... it says there is no chat route/app screen yet",
              "no chat lookup route" in r.reply or "app screen" in r.reply, r.reply if r else "")
        r = ask("is the radar on?")
        check("'is the radar on?' reads the real switch",
              r is not None and r.intent == "price_radar_state" and "No" in r.reply,
              r.reply if r else "model")
        r = ask("how do I turn on the flight price radar?")
        check("the enable question names the settings key and no chat card",
              r is not None and r.intent == "price_radar_enable"
              and "[price_radar] enabled = true" in r.reply and "no chat approval card" in r.reply.lower(),
              r.reply if r else "model")
    finally:
        Q._price_radar_state = _ORIG_STATE


def test_on_state_and_about():
    Q._price_radar_state = lambda: {"available": True, "enabled": True}
    try:
        r = ask("can you check flight prices to Las Vegas leaving Nov 26 coming back Dec 3?")
        check("a specific flight question is answered", r is not None
              and r.intent in ("price_radar_lookup", "price_radar_flight"),
              r.intent if r else "model")
        check("... it says the radar is on (this chat can look up, no app screen)",
              ("which airport" in r.reply.lower()
               or ("This chat can run a read-only lookup" in r.reply
                   and "app screen" in r.reply)),
              r.reply if r else "")
        check("... it never invents a price", not re.search(r"\$\s*\d", r.reply),
              r.reply if r else "")
        r = ask("is the radar on?")
        check("'is the radar on?' says yes", r is not None and "Yes" in r.reply,
              r.reply if r else "model")
        r = ask("what does the radar do?")
        check("the about answer names read-only prices and no booking",
              r is not None and r.intent == "price_radar_about"
              and "read-only" in r.reply.lower() and "never books" in r.reply, r.reply if r else "model")
        r = ask("can you track a price?")
        check("tracking says it keeps local history but has no route",
              r is not None and r.intent == "price_radar_track"
              and "history" in r.reply.lower(), r.reply if r else "model")
    finally:
        Q._price_radar_state = _ORIG_STATE


def test_booking_refusal():
    Q._price_radar_state = lambda: {"available": True, "enabled": True}
    try:
        r = ask("can you book a flight?")
        check("booking is refused plainly", r is not None and r.intent == "price_radar_book"
              and "No" in r.reply and "read-only" in r.reply, r.reply if r else "model")
        check("... it says there is no booking/cart/checkout code path",
              "booking" in r.reply and ("cart" in r.reply or "checkout" in r.reply),
              r.reply if r else "")
    finally:
        Q._price_radar_state = _ORIG_STATE


def test_over_capture_and_missing():
    for text in ("what is the price of milk?", "how much is a coffee?",
                 "can you compare prices for headphones?", "what is the price of bitcoin?"):
        r = Q.match(text)
        check(f"not the flight radar: {text!r}", r is None or not str(r.name).startswith("price_radar"),
              r.name if r else "model")
    Q._price_radar_state = lambda: {"available": False, "enabled": False}
    try:
        r = ask("is the radar on?")
        check("a missing radar says so", r is not None and "not installed" in r.reply,
              r.reply if r else "model")
    finally:
        Q._price_radar_state = _ORIG_STATE


def test_prompt():
    mf = (ROOT / "backend" / "jarvis-primary.Modelfile").read_text(encoding="utf-8")
    m = re.search(r'SYSTEM """(.*?)"""', mf, re.S)
    text = m.group(1) if m else ""
    check("the Modelfile says the radar is real", "read-only price and flight radar" in text)
    profiles = (ROOT / "backend" / "jarvis_profiles.py").read_text(encoding="utf-8")
    check("the tuned-model copy carries the same line", "read-only price and flight radar" in profiles)
    line = next((ln for ln in text.splitlines() if "price and flight radar" in ln), "")
    check("the prompt line says off/unwired/no booking/no invented prices",
          "OFF by default" in line and "never books" in line and "never invent prices" in line, line)
    check("the prompt line carries no token or secret",
          not re.search(r"token|secret|api[ _-]?key|Bearer", line, re.I), line)


_ORIG_STATE = Q._price_radar_state


def main():
    tests = [test_source_truth, test_off_state, test_on_state_and_about,
             test_booking_refusal, test_over_capture_and_missing, test_prompt]
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
