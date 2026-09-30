#!/usr/bin/env python3
"""Writes the "Retirement what-if" contract file for both apps, and checks it.

    python3 tools/gen_retirement_cases.py            # write both copies
    python3 tools/gen_retirement_cases.py --check    # compare only

What the backend really answers (backend/jarvis_retirement.py; JARVIS-API
section 103; docs/FINANCE-DESIGN.md "Retirement contract (frozen)"), in named
situations, made by the real code - nothing written by hand:

    jarvis-desktop/tests/fixtures/retirement-cases.json
    jarvis-client/app/src/test/resources/contract/retirement-cases.json

(byte-identical). The desktop's tests/retirement.mjs and the phone's
RetirementTest read the SAME file, so the two apps are tested against one
source of words and figures. The file only changes when the backend's answer
does (fixed random seed, so the figures are the same every time).

Cases: `defaults` (GET /api/retirement/defaults), `mixed` (40 now, stop at 65,
100,000 saved, 12,000 a year, spend 30,000, everything else the placeholders),
`never_runs_out`, `always_runs_out`, `not_enough_to_say`, one entry in `errors`
per error code, and the two busy / too-slow refusals.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
import jarvis_retirement as R  # noqa: E402

DESKTOP = ROOT / "jarvis-desktop" / "tests" / "fixtures" / "retirement-cases.json"
PHONE = (ROOT / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract"
         / "retirement-cases.json")
COPIES = (DESKTOP, PHONE)

BASE = {"current_age": "40", "retirement_age": "65", "savings": "100,000",
        "yearly_saving": "12,000", "yearly_spending": "30,000"}


def _post(**changes):
    body = dict(BASE)
    for k, v in changes.items():
        if v is None:
            body.pop(k, None)
        else:
            body[k] = v
    code, out = R.handle_post(R.PATH_RUN, body)
    return {"status": code, "body": out}


def _too_slow():
    real = R.run

    def slow(*a, **k):
        raise TimeoutError("too slow")
    R.run = slow
    try:
        code, out = R.handle_post(R.PATH_RUN, dict(BASE))
    finally:
        R.run = real
    return {"status": code, "body": out}


def _busy():
    R._RUN_LOCK.acquire()
    try:
        code, out = R.handle_post(R.PATH_RUN, dict(BASE))
    finally:
        R._RUN_LOCK.release()
    return {"status": code, "body": out}


def cases() -> dict:
    code, defaults = R.handle_get(R.PATH_DEFAULTS)
    return {
        "_note": ("Made by the real backend/jarvis_retirement.py (handle_get / handle_post) with "
                  "tools/gen_retirement_cases.py, for both apps' tests. Not shipped in the app."),
        "defaults": {"status": code, "body": defaults},
        "mixed": _post(),
        "never_runs_out": _post(savings="100,000,000"),
        "always_runs_out": _post(savings="1,000", yearly_saving="0", yearly_spending="90,000"),
        "not_enough_to_say": _post(yearly_spending="0"),
        "errors": {
            "missing": _post(current_age=None),
            "bad_number": _post(current_age="abc"),
            "negative": _post(savings="-5"),
            "out_of_range": _post(current_age="200"),
            "plan_not_after": _post(plan_to_age="60"),
            "too_many_years": _post(current_age="18", retirement_age="60", plan_to_age="109"),
            "unknown_field": _post(zzz="1"),
        },
        "busy": _busy(),
        "too_slow": _too_slow(),
    }


def render() -> str:
    return json.dumps(cases(), ensure_ascii=False, indent=1, allow_nan=False) + "\n"


def main(argv) -> int:
    text = render()
    if "--check" in argv:
        stale = [str(c.relative_to(ROOT)) for c in COPIES
                 if not c.exists() or c.read_text(encoding="utf-8") != text]
        if stale:
            print("STALE " + ", ".join(stale) + " - run python3 tools/gen_retirement_cases.py")
            return 1
        print("retirement-cases.json: both copies match")
        return 0
    for c in COPIES:
        c.parent.mkdir(parents=True, exist_ok=True)
        c.write_text(text, encoding="utf-8", newline="\n")
        print("wrote", c.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
