#!/usr/bin/env python3
"""Writes the "Folders Jarvis may look in" contract file for both apps, and
checks it.

    python3 tools/gen_folders_cases.py            # write both copies
    python3 tools/gen_folders_cases.py --check    # compare only

What GET /api/folders really answers (backend/jarvis_documents.py,
documents.patch), in named situations, and what the add, remove and import
routes answer - made by the real code, nothing written by hand:

    jarvis-desktop/tests/fixtures/folders-cases.json
    jarvis-client/app/src/test/resources/contract/folders-cases.json

(byte-identical). The desktop's Rust and JavaScript tests and the phone's
FoldersTest build against it. The folders are made-up Windows paths; the
times are fixed, so the file only changes when the backend's answer does.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
_CONF = tempfile.mkdtemp(prefix="jarvis-folders-cases-")
os.environ["OPENJARVIS_CONFIG_DIR"] = _CONF
for p in (BACKEND, BACKEND / "rebuilt"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import jarvis_documents as D  # noqa: E402

D._config_dir = lambda: Path(_CONF)

DESKTOP = ROOT / "jarvis-desktop" / "tests" / "fixtures" / "folders-cases.json"
PHONE = (ROOT / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract"
         / "folders-cases.json")
COPIES = (DESKTOP, PHONE)

DOCS = "C:\\Users\\owner\\Documents"
NOTES = "C:\\Users\\owner\\Notes\\Notion"
AT = 1790000000.0


def _state(folders=(), pending=None, last=None, damaged=False):
    D._reset_for_tests()
    path = D.settings_path()
    if damaged:
        path.write_text("{not json", encoding="utf-8")
    elif folders:
        D._save([{"path": f, "added": AT} for f in folders])
    elif path.exists():
        path.unlink()
    if pending:
        D._P_STATE["pending"].update(id="p1", path=pending, since=AT)
    if last:
        D._P_STATE["last"].update(outcome=last, why="", at=AT,
                                  message=D.LAST_WORDS[last])


def cases() -> dict:
    out = {}
    _state()
    out["empty_phone"] = D.view(here=False, ready=True)
    out["empty_pc"] = D.view(here=True, ready=True)
    _state([DOCS, NOTES])
    out["two_folders_pc"] = D.view(here=True, ready=True)
    out["two_folders_phone"] = D.view(here=False, ready=True)
    out["no_converter"] = D.view(here=True, ready=False)
    _state([DOCS], pending=NOTES)
    out["waiting"] = D.view(here=True, ready=True)
    _state([DOCS], last="added")
    out["last_added"] = D.view(here=True, ready=True)
    _state(last="denied")
    out["last_denied"] = D.view(here=True, ready=True)
    _state(damaged=True)
    out["damaged"] = D.view(here=False, ready=True)
    _state()
    code, body = D.request_add({"path": DOCS}, here=False)
    add_phone = {"status": code, "body": body}
    code, body = D.request_import({"zip": "C:\\x.zip", "into": DOCS}, here=False)
    import_phone = {"status": code, "body": body}
    D._reset_for_tests()
    return {"cases": out,
            # The routes' refusals from the phone (both apps show the PC's words).
            "add_from_phone": add_phone,
            "import_from_phone": import_phone,
            # A backend without jarvis_documents.py / documents.patch.
            "missing": {"status": 404, "body": {"error": "not found"}},
            "example_card": D.card(DOCS),
            "limits": {"folders": D.MAX_FOLDERS, "part_tokens": D.PART_TOKENS,
                       "parts_per_turn": D.PARTS_PER_TURN}}


def render() -> str:
    return json.dumps(cases(), indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv) -> int:
    text = render()
    if "--check" in argv:
        stale = []
        for path in COPIES:
            have = path.read_text(encoding="utf-8") if path.is_file() else ""
            if have.replace("\r\n", "\n") != text:
                stale.append(path)
        for path in stale:
            print(f"{path.relative_to(ROOT)} is out of date: run "
                  f"python3 tools/gen_folders_cases.py")
        if stale:
            return 1
        print("folders-cases.json matches the producer (desktop and phone copies).")
        return 0
    for path in COPIES:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
