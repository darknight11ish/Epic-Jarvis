#!/usr/bin/env python3
"""Writes "Animal options"'s contract file for both apps, and checks it.

    python3 tools/gen_animal_cases.py            # write both copies
    python3 tools/gen_animal_cases.py --check    # compare only

Made by the real code (backend/jarvis_animal.py) - nothing is written by
hand:

    jarvis-desktop/tests/fixtures/animal-cases.json
    jarvis-client/app/src/test/resources/contract/animal-cases.json

(byte-identical). It holds:

  * what GET /api/animal answers on a PC nobody has changed (`view`), so
    both apps' fallback words (animal-shared.js SWITCHES, the phone's
    AnimalOptions.SWITCHES) are the PC's word for word;
  * `step_device` for every change in every starting tuning (`steps`), so
    the desktop's stepTuning and the phone's AnimalOptions.step make the
    same change from the same `face_tuning` header value;
  * what Jarvis says for each (`device_said`) and the words for an older PC.

The desktop's tests/animal-settings.mjs and the phone's AnimalOptionsTest
read it.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
_TMP = tempfile.mkdtemp(prefix="jarvis-animal-cases-")
os.environ["OPENJARVIS_CONFIG_DIR"] = _TMP
for p in (BACKEND, BACKEND / "rebuilt"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import jarvis_animal as AN  # noqa: E402

AN._config_dir = lambda: Path(_TMP)

DESKTOP = ROOT / "jarvis-desktop" / "tests" / "fixtures" / "animal-cases.json"
PHONE = (ROOT / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract"
         / "animal-cases.json")

#: Starting points: the default, each end, and a few in between.
TUNINGS = [
    {"quality": "high", "frameRate": "auto", "autoAdjust": True},
    {"quality": "low", "frameRate": "30", "autoAdjust": False},
    {"quality": "medium", "frameRate": "60", "autoAdjust": False},
    {"quality": "max", "frameRate": "max", "autoAdjust": False},
    {"quality": "high", "frameRate": "auto", "autoAdjust": False},
    {"quality": "low", "frameRate": "120", "autoAdjust": True},
]


def render() -> str:
    view = AN.view()
    steps = [{"from": t, "change": c, **AN.step_device(t, c)}
             for t in TUNINGS for c in AN.DEVICE_CHANGES]
    doc = {"view": view, "missing": AN.MISSING, "defaults": AN.DEFAULTS,
           "device_changes": list(AN.DEVICE_CHANGES), "device_said": AN.DEVICE_SAID,
           "steps": steps}
    return json.dumps(doc, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv) -> int:
    text = render()
    if "--check" in argv:
        stale = [str(p.relative_to(ROOT)) for p in (DESKTOP, PHONE)
                 if not p.exists() or p.read_text(encoding="utf-8") != text]
        if stale:
            print("out of date - run python3 tools/gen_animal_cases.py:\n  " + "\n  ".join(stale))
            return 1
        print("animal cases: up to date")
        return 0
    for p in (DESKTOP, PHONE):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        print(f"wrote {p.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
