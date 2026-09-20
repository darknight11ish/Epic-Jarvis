"""Where the backend actually is, so the tests run on the owner's machine too.

THE PROBLEM THIS SOLVES

Every test in this directory was written assuming the backend modules sit
beside it:

    HERE = Path(__file__).resolve().parent
    sys.path.insert(0, str(HERE))
    import jarvis_memory          # only works if jarvis_memory.py is HERE

That is true in the development container, where the modules are symlinked
into this folder. It is false on the machine that actually runs Jarvis, where
the backend lives somewhere like

    C:\\Users\\pcadmin\\Documents\\Claude\\Open jarvis files\\Desktop program

and this repository is cloned somewhere else entirely. So the suites could be
run by one person in one place, which is the opposite of what a test is for —
and `apply-patches.ps1` offered to run them straight after patching, which
would have produced eighteen import errors that look exactly like the patches
having broken something.

TWO ROOTS, NOT ONE

The tests need two different places and were using `HERE` for both:

    BACKEND   the Python modules being tested. Elsewhere, on a real install.
    REPO      this repository: the patches, and the desktop client source
              that several tests read to check a route has a caller.

`REPO` is always the parent of this file's directory — the tests live in the
repo, so that cannot be wrong. `BACKEND` is `JARVIS_BACKEND` if it is set,
and otherwise this directory, which keeps the container working exactly as
before with no flag.

USAGE

    from _where import BACKEND, REPO

    HUD = BACKEND / "jarvis_hud.py"          # a backend source file
    BRAIN_JS = REPO / "jarvis-desktop" / "src" / "brain.js"

Importing this module also puts `BACKEND` on `sys.path`, so `import
jarvis_memory` works without each test repeating it.
"""
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent

#: This repository. The tests are in it, so its location is never in doubt.
REPO = _HERE.parent

#: The folder holding jarvis_hud.py, jarvis_memory.py and the rest.
#:
#: Set JARVIS_BACKEND to run the suites against a real install:
#:
#:     $env:JARVIS_BACKEND = "C:\\...\\Desktop program"; python backend\\test_memory_safety.py
#:
#: Unset, it is this directory - which is where the dev container symlinks
#: them, so nothing there needs the variable.
BACKEND = Path(os.environ.get("JARVIS_BACKEND") or _HERE).resolve()

# Prepended, not appended: if a stale copy of a module is ever left in this
# folder, the one in BACKEND is the one under test and must win.
_b = str(BACKEND)
if _b in sys.path:
    sys.path.remove(_b)
sys.path.insert(0, _b)


def missing(*names: str) -> list[str]:
    """Which of these backend files are not where BACKEND says they are.

    Tests call this to skip honestly rather than fail. A suite reporting
    "jarvis_hud.py is not in <path>" is a configuration problem; the same
    suite reporting nine assertion failures looks like the patches broke the
    product, which is the wrong thing to be told after applying them.
    """
    return [n for n in names if not (BACKEND / n).is_file()]


def explain() -> str:
    """One line a person can act on, for when a file is not there."""
    where = "JARVIS_BACKEND" if os.environ.get("JARVIS_BACKEND") else "this folder"
    return (f"Backend modules were looked for in {BACKEND} ({where}). "
            f"Set JARVIS_BACKEND to the folder holding jarvis_hud.py.")
