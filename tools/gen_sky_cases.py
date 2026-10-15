#!/usr/bin/env python3
"""Writes "Sun, moon and weather"'s contract file for both apps, and checks it.

    python3 tools/gen_sky_cases.py            # write both copies
    python3 tools/gen_sky_cases.py --check    # compare only

What GET /api/sky really answers (backend/jarvis_sky.py), in named
situations, made by the real code - nothing is written by hand:

    jarvis-desktop/tests/fixtures/sky-cases.json
    jarvis-client/app/src/test/resources/contract/sky-cases.json

(byte-identical). The desktop's tests/sky.mjs and the phone's
SkySettingsTest read it, so both apps show the PC's words and read the
weather numbers the same way. No network: the weather is put straight into
the module's cache, and nothing is ever fetched.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
_TMP = tempfile.mkdtemp(prefix="jarvis-sky-cases-")
os.environ["OPENJARVIS_CONFIG_DIR"] = _TMP
for p in (BACKEND, BACKEND / "rebuilt"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import jarvis_sky as SK  # noqa: E402

SK._config_dir = lambda: Path(_TMP)
SK._audit = lambda *a: None

DESKTOP = ROOT / "jarvis-desktop" / "tests" / "fixtures" / "sky-cases.json"
PHONE = (ROOT / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract"
         / "sky-cases.json")


class _Yes:
    allowed, outcome, tier, reason = True, "approved", "ask", "approved"


def _fresh():
    SK._reset_for_tests()
    try:
        SK.settings_path().unlink()
    except FileNotFoundError:
        pass


def cases() -> dict:
    out = {}
    _fresh()
    out["off"] = SK.view(here=True)
    SK.handle_post({"show": True}, here=True)
    SK.handle_post({"place": "Denver"}, here=True)
    out["town_on_the_pc"] = SK.view(here=True)
    out["town_on_the_phone"] = SK.view(here=False)
    held = []
    SK.request_weather("open_meteo", gate=lambda *a: _Yes(), tier_of=lambda a: "ask",
                       spawn=held.append)
    out["open_meteo_waiting"] = SK.view(here=False)
    if not held:
        # `held[0]()` on an empty list is an IndexError with nothing to read,
        # and that is exactly how this reached CI on 2026-10-07 (audit D8): the
        # two `handle_post` calls above discard their return codes, so a
        # throwaway config folder that cannot be written stores no town,
        # `request_weather` answers 409 BEFORE it ever reaches `spawn`, and the
        # run died as `gen_sky_cases.py  code=1  IndexError: list index out of
        # range` instead of saying what was wrong. The other two paths that do
        # not spawn (a card already waiting, a tier that is not "ask") end the
        # same way. Say which, in a sentence, and exit non-zero.
        raise SystemExit(
            "sky cases: the Open-Meteo request never reached `spawn`, so no card "
            "was queued to resolve. It does not spawn when no town is stored - "
            "which is what a throwaway config folder that cannot be written "
            "leaves behind - and it does not spawn when a card is already "
            "waiting or when the tier of that card is not 'ask'. Nothing was "
            "written; the fixtures are untouched.")
    held[0]()
    t = [1759000000.0]
    deps = SK.Deps(open_meteo_fetch=lambda url: json.dumps({"current": {
        "weather_code": 63, "cloud_cover": 90, "wind_speed_10m": 7.0,
        "wind_direction_10m": 270}}).encode(), clock=lambda: t[0], spawn=lambda f: f())
    SK.refresh(deps)
    out["open_meteo_rain"] = SK.view(here=False)
    SK.request_weather("home_assistant")
    SK._reset_for_tests()
    deps2 = SK.Deps(home_ready=lambda: {"state": "off", "said": ""}, clock=lambda: t[0],
                    spawn=lambda f: f())
    SK.refresh(deps2)
    out["home_assistant_not_set_up"] = SK.view(here=False)
    _fresh()
    return {"cases": out, "missing": SK.MISSING, "sources": list(SK.SOURCES),
            "choices": [dict(c) for c in SK.CHOICES]}


def render() -> str:
    doc = cases()
    # The "last" card outcome carries a time; it is not part of the contract.
    for v in doc["cases"].values():
        last = v["weather"].get("last")
        if last:
            last["at"] = 0
    return json.dumps(doc, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv) -> int:
    text = render()
    if "--check" in argv:
        stale = [str(p.relative_to(ROOT)) for p in (DESKTOP, PHONE)
                 if not p.exists() or p.read_text(encoding="utf-8") != text]
        if stale:
            print("out of date - run python3 tools/gen_sky_cases.py:\n  " + "\n  ".join(stale))
            return 1
        print("sky cases: up to date")
        return 0
    for p in (DESKTOP, PHONE):
        p.parent.mkdir(parents=True, exist_ok=True)
        # newline="\n": without it this writes CRLF on Windows and LF elsewhere
        # (the repository is LF everywhere - .gitattributes).
        p.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {p.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
