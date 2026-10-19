"""Generate the preset contract both apps render: backend/fixtures/work_presets.json."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
import jarvis_presets as P  # noqa: E402

OUT = ROOT / "backend" / "fixtures" / "work_presets.json"


def doc() -> dict:
    return {"version": 1, "generated_by": "tools/gen_work_presets.py",
            "source": "backend/jarvis_presets.py",
            "note": "both apps render these same words; regenerate, never hand-edit",
            **P.view()}


def main() -> int:
    want = json.dumps(doc(), indent=2, ensure_ascii=False) + "\n"
    if "--check" in sys.argv:
        got = OUT.read_text(encoding="utf-8") if OUT.is_file() else ""
        if got != want:
            print(f"FAIL {OUT} is stale: run py -3 tools/gen_work_cases.py")
            return 1
        print(f"ok   {OUT} is what the presets say")
        return 0
    OUT.write_text(want, encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
