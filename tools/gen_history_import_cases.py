#!/usr/bin/env python3
"""Writes "Bring in old chats"'s golden file, and checks it.

    python3 tools/gen_history_import_cases.py            # write it
    python3 tools/gen_history_import_cases.py --check    # compare only

jarvis-desktop/tests/fixtures/history-import-cases.json: what GET
/api/memory/import_chats really answers (jarvis_history_import.view()), in
named situations, made by the real code with made-up counts and a fixed
clock. The desktop's tests/history-import.mjs builds against it. The phone
has no copy: it has no button for this (ARCHITECTURE.md section 8).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import jarvis_history_import as H  # noqa: E402

DESKTOP = ROOT / "jarvis-desktop" / "tests" / "fixtures" / "history-import-cases.json"

#: Monday 28 September 2026, 10:00 UTC.
NOW = 1790589600.0


def _case(here=True, **state) -> dict:
    H._reset_for_tests()
    with H._LOCK:
        H._STATE.update(state)
    return H.view(here=here)


def cases() -> dict:
    counts = {"read": 412, "before": 0, "offered": 412, "nothing": 9, "waiting": 37}
    out = {
        "idle": _case(),
        "idle_not_here": _case(here=False),
        "looking": _case(state="running", started=NOW),
        "running": _case(state="running", kind="chatgpt", started=NOW, read=120, offered=120,
                         nothing=3, waiting=9),
        "stopping": _case(state="stopping", kind="chatgpt", started=NOW, read=121,
                          offered=121, nothing=3, waiting=9),
        "done": _case(state="finished", outcome="done", kind="chatgpt", started=NOW,
                      finished=NOW + 5400, **counts),
        "done_again": _case(state="finished", outcome="done", kind="claude", started=NOW,
                            finished=NOW + 60, read=50, before=50, offered=0, waiting=0),
        "queue_full": _case(state="finished", outcome="queue_full", kind="gemini",
                            started=NOW, finished=NOW + 900, read=80, offered=80,
                            waiting=50),
        "cancelled": _case(state="finished", outcome="cancelled", kind="chatgpt",
                           started=NOW, finished=NOW + 300, read=40, offered=40, waiting=4),
        "no_model": _case(state="finished", outcome="no_model", kind="deepseek",
                          started=NOW, finished=NOW + 600, read=30, offered=30, waiting=6),
        "not_export": _case(state="finished", outcome="not_export", started=NOW,
                            finished=NOW + 1),
        "failed": _case(state="finished", outcome="failed", kind="chatgpt", started=NOW,
                        finished=NOW + 2, why="the file could not be read (BadZipFile)"),
    }
    H._reset_for_tests()
    return {"about": "Real jarvis_history_import.view() answers, made by "
                     "tools/gen_history_import_cases.py. Counts are made up.",
            "cases": out}


def text() -> str:
    return json.dumps(cases(), indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main() -> int:
    want = text()
    if "--check" in sys.argv:
        have = DESKTOP.read_text(encoding="utf-8") if DESKTOP.is_file() else ""
        if have != want:
            print(f"{DESKTOP.relative_to(ROOT)} is out of date: run "
                  f"python3 tools/gen_history_import_cases.py")
            return 1
        print("history-import-cases.json is up to date.")
        return 0
    DESKTOP.parent.mkdir(parents=True, exist_ok=True)
    # newline="\n": without it this writes CRLF on Windows and LF elsewhere
    # (the repository is LF everywhere - .gitattributes).
    DESKTOP.write_text(want, encoding="utf-8", newline="\n")
    print(f"wrote {DESKTOP.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
