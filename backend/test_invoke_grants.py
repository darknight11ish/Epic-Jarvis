"""test_invoke_grants.py - the grants checker must see the ONE shared budget road.

WHY. The desktop's silent-failure rule sends every command through
`jarvis-desktop/src/invoke-budget.js`'s `call()`, and `tools/check_invoke_grants.py`
decides whether the window whose page makes a call is GRANTED it. That checker used
to read only `TAURI.core.invoke(...)` spellings, so the newest writes that go through
the shared module - `hud_set_face`, `apply_focus_preset`, the Learning card's two
commands - were never checked at all (2026-10-28 audit, B1 finding 6). These checks
pin the fix: the shared module counts as the IPC, a same-file command CONSTANT is
followed, and a `call(` in a file that did not import the module is not IPC.

    python3 test_invoke_grants.py
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import check_invoke_grants as C  # noqa: E402


def main():
    passed = failed = 0

    def ok(what, cond, detail=""):
        nonlocal passed, failed
        print(("ok    " if cond else "FAIL  ") + what)
        if not cond:
            print("      " + str(detail))
            failed += 1
        else:
            passed += 1

    hud = (REPO / "jarvis-desktop" / "src" / "hud-presets.js").read_text(encoding="utf-8")
    names = [arg for _line, _at, arg in C.calls(hud)]
    ok("hud-presets.js's shared-module call sites are read as IPC",
       any("hud_set_face" in a for a in names), names[:5])
    ok("... and the preset apply is too",
       any("apply_focus_preset" in a for a in names), names[:5])

    learning = (REPO / "jarvis-desktop" / "src" / "learning-settings.js").read_text(encoding="utf-8")
    ok("the shared module is recognised by its import, not by a bare name",
       bool(C.BUDGET_IMPORT.search(learning)))

    bridge = (REPO / "jarvis-desktop" / "src" / "focus-presets-bridge.js").read_text(encoding="utf-8")
    consts = C.constants(bridge)
    ok("a same-file command CONSTANT is resolved",
       C.command_names("READ_COMMAND", consts) == (["get_focus_presets"], False),
       C.command_names("READ_COMMAND", consts))
    ok("... and an unknown identifier stays opaque (no guessed grant)",
       C.command_names("someOtherName", consts) == ([], True))

    # A plain `call(...)` in a page that does NOT import the module is not IPC.
    plain = 'function f(cb) { return cb.call(null, "serve_up"); }\n'
    ok("a file that did not import the module gets no IPC sites",
       C.calls(plain) == [], C.calls(plain))

    print(f"\n{passed} passed, {failed} failed")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
