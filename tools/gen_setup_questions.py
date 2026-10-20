"""Generate the setup questionnaire both apps render: backend/fixtures/setup_questions.json.

    py -3 tools/gen_setup_questions.py
    py -3 tools/gen_setup_questions.py --check

`backend/jarvis_setup.py`'s `QUESTIONS` tuple is the one table behind the PC's
`GET /api/setup` answer, the desktop's Settings card and the phone's read-only
card. This tool writes that table's question half out as the fixture both apps'
tests read, so a test can hold the UI to the PC's real questions rather than to
a hand-written idea of them.

WHY A FIXTURE AND NOT THE WHOLE ANSWER. `state()` also reads THIS PC: the
current values of every setting, the last accepted answers and when they were
accepted. None of that belongs in a shared file. Only the questions - ids,
titles, help lines, choices and whether a question takes several answers - are
the same everywhere, and those are what a UI test needs.

REGENERATE, NEVER HAND-EDIT. An option reworded in `jarvis_setup.py` should fail
the desktop suite (`jarvis-desktop/tests/setup-questionnaire.mjs` runs
`--check`) until this file is regenerated - the same rule `gen_work_presets.py`
follows.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
import jarvis_setup as S  # noqa: E402

OUT = ROOT / "backend" / "fixtures" / "setup_questions.json"


def questions() -> list:
    """`GET /api/setup`'s `questions`, in the PC's order and the PC's words."""
    return [
        {
            "id": q["id"],
            "title": q["title"],
            "help": q["help"],
            "multi": bool(q["multi"]),
            "options": [
                {"id": o["id"], "label": o["label"], "detail": o.get("detail", "")}
                for o in q["options"]
            ],
            "all_none": bool(q["multi"]),
        }
        for q in S.QUESTIONS
    ]


def doc() -> dict:
    rows = questions()
    return {
        "version": 1,
        "generated_by": "tools/gen_setup_questions.py",
        "source": "backend/jarvis_setup.py",
        "note": "both apps render these same questions; regenerate, never hand-edit",
        "count": len(rows),
        "questions": rows,
    }


def main() -> int:
    want = json.dumps(doc(), indent=2, ensure_ascii=False) + "\n"
    if "--check" in sys.argv:
        got = OUT.read_text(encoding="utf-8") if OUT.is_file() else ""
        if got != want:
            print(f"FAIL {OUT} is stale: run py -3 tools/gen_setup_questions.py")
            return 1
        print(f"ok   {OUT} is what the setup questionnaire says")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    # LF everywhere: .gitattributes is eol=lf, and a Windows working copy that
    # wrote CRLF here would make `--check` disagree with a Linux checkout.
    OUT.write_text(want, encoding="utf-8", newline="\n")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
