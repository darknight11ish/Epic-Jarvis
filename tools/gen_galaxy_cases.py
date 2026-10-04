#!/usr/bin/env python3
"""Writes the Galaxy "facts behind this dot" words for both apps, and checks them.

    python3 tools/gen_galaxy_cases.py            # write both copies
    python3 tools/gen_galaxy_cases.py --check    # compare only (exit 1 on drift)

docs/GALAXY-PANEL-DESIGN.md section 3 fixes the words word for word. They live
here (there is no backend text for them) and go to a byte-identical file in each
app, so the desktop test and any phone test read ONE source:

    jarvis-desktop/tests/fixtures/galaxy-cases.json
    jarvis-client/app/src/test/resources/contract/galaxy-cases.json

`{count}`, `{n}` and `{total}` are filled in by the app from numbers it counted.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COPIES = (
    ROOT / "jarvis-desktop" / "tests" / "fixtures" / "galaxy-cases.json",
    ROOT / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract" / "galaxy-cases.json",
)

WORDS = {
    "galaxy_panel": "Facts behind this dot ({count})",
    "galaxy_panel_more": "Show 20 more",
    "galaxy_panel_showing": "Showing {n} of {total}",
    "galaxy_panel_reading": "Reading the facts...",
    "galaxy_panel_erased": "Erased. Only the dates are kept.",
    "galaxy_panel_forgotten": "Forgotten",
    "galaxy_panel_pinned": "Pinned",
    "galaxy_panel_hidden": "Hidden. Show memory lists to see these facts.",
    "galaxy_panel_empty": "No facts to show.",
    "galaxy_panel_failed": "Your PC could not read these facts.",
    "galaxy_panel_retry": "Try again",
    "galaxy_panel_open": "Open in Memory",
    "galaxy_panel_topics_hidden": "{n} hidden by topic settings",
}


def cases() -> dict:
    return {
        "_comment": ("Made by tools/gen_galaxy_cases.py from docs/GALAXY-PANEL-DESIGN.md "
                     "section 3. Do not edit by hand. Not shipped in the app."),
        "page_size": 20,
        "max_ids_per_read": 100,
        "words": WORDS,
    }


def render() -> str:
    return json.dumps(cases(), indent=2, ensure_ascii=False) + "\n"


def main(argv) -> int:
    text = render()
    if "--check" in argv:
        bad = [str(p) for p in COPIES if not p.exists() or p.read_text(encoding="utf-8") != text]
        for b in bad:
            print(f"out of date: {b}")
        return 1 if bad else 0
    for p in COPIES:
        p.parent.mkdir(parents=True, exist_ok=True)
        # newline="\n": without it this writes CRLF on Windows and LF elsewhere
        # (the repository is LF everywhere - .gitattributes).
        p.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {p.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
