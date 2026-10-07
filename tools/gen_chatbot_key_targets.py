"""gen_chatbot_key_targets.py - regenerate the ONE canonical list of the six
chatbot API keys' Windows Credential Manager names.

    python tools/gen_chatbot_key_targets.py           # write the file
    python tools/gen_chatbot_key_targets.py --check   # fail if it is stale

WHY THIS FILE EXISTS
The Python side owns these names. `jarvis_chatbot_api.py` builds each one
from its own `PRESETS` table:

    KEY_TARGETS = {pid: f"Jarvis Backend/{PRESETS[pid].company} API key" for pid in PRESETS}

The desktop app has to write its keys under exactly those names, and it
cannot import Python to find them out - so it keeps its own small table
(`jarvis-desktop/src-tauri/src/token_store.rs`, `CHATBOT_API_KEY_TARGETS`).
Two hand-kept copies of one list is how a silent failure starts: the page
says "Saved" under a name the backend never reads.

So the list is generated HERE, from the Python side itself, into one file
both sides point at:

    backend/tests/fixtures/chatbot-api-key-targets.json

`backend/tests/fixtures` is the Python copy of
`jarvis-desktop/tests/fixtures`, the same shared-fixture convention the other
cross-app contracts in this repository use (`test_chatbot_api.py`'s own
`same_fixture` check enforces that the two copies stay identical).

Who reads it:
  * `backend/test_chatbot_keys.py` - regenerates the same text in memory and
    compares it with the committed file, and checks each target against
    `jarvis_chatbot_api.KEY_TARGETS` itself. A drift on the Python side, or
    a hand-edited fixture, fails here.
  * `token_store.rs`'s `the_six_chatbot_targets_are_the_python_sides_own` -
    `include_str!`s the desktop copy and compares it with the Rust table,
    so a drift between the desktop and the fixture fails at `cargo test`.

Run this after ANY change to `PRESETS` (a new service, a renamed company)
and commit the regenerated file. Standard library only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
BACKEND = REPO / "backend"
sys.path.insert(0, str(BACKEND))

#: The generated file, in both apps' own fixture folders. A tuple: the first
#: is the one written; the second is checked to be identical to it.
FIXTURES = (
    BACKEND / "tests" / "fixtures" / "chatbot-api-key-targets.json",
    REPO / "jarvis-desktop" / "tests" / "fixtures" / "chatbot-api-key-targets.json",
)


def canonical() -> str:
    """The exact text of the fixture, from the Python side's live tables.

    `source` names the expression the targets are built from, so that a
    reader (and the desktop test) can tell this really is the Python side's
    own list and not a second hand-typed one.
    """
    import jarvis_chatbot_api as API  # noqa: E402

    rows = []
    for pid, preset in API.PRESETS.items():
        want = f"Jarvis Backend/{preset.company} API key"
        got = API.KEY_TARGETS[pid]
        if got != want:
            raise SystemExit(
                f"KEY_TARGETS[{pid}] is {got!r}, but the documented rule builds {want!r} - "
                "fix jarvis_chatbot_api.py first (this generator will not guess)."
            )
        rows.append(
            {
                "id": pid,
                "short": preset.short,
                "company": preset.company,
                "target": got,
                "key_where": preset.key_where,
            }
        )
    rows.sort(key=lambda r: r["short"])
    doc = {
        "about": (
            "The six chatbot API services and the Windows Credential Manager name each "
            "key is kept under. Generated from jarvis_chatbot_api.PRESETS; do not edit "
            "by hand - run tools/gen_chatbot_key_targets.py instead."
        ),
        "source": "jarvis_chatbot_api.KEY_TARGETS",
        "rule": "Jarvis Backend/{company} API key",
        "targets": rows,
    }
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def main(argv: list) -> int:
    check = "--check" in argv
    text = canonical()
    stale = []
    for path in FIXTURES:
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current == text:
            print(f"ok   {path.relative_to(REPO)}")
            continue
        if check:
            stale.append(str(path.relative_to(REPO)))
            print(f"FAIL {path.relative_to(REPO)} is not what the Python side says")
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"wrote {path.relative_to(REPO)}")
    if stale:
        print("Regenerate with: python tools/gen_chatbot_key_targets.py")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
