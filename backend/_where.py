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


#: Modules this repository ships WHOLE, for the owner's backend folder:
#: apply-patches.ps1 copies each one beside jarvis_hud.py (a "rebuilt/" entry
#: lands there too, by file name). Every import of one of these is wrapped,
#: so a backend without the file runs - with that feature quietly off.
#:
#: The SAME list, in the same order, as `$SHIPPED` in scripts/apply-patches.ps1.
#: test_shipped_modules.py fails if they differ, and if any module a shipped
#: file or a patch imports is in neither this list nor its exemptions. This
#: tuple once lagged the script by seven modules and the script once lagged
#: jarvis_agent.py by seven more.
SHIPPED = (
    # the ten rebuilt modules
    "rebuilt/jarvis_compute.py", "rebuilt/jarvis_events.py",
    "rebuilt/jarvis_framework.py", "rebuilt/jarvis_initiative.py",
    "rebuilt/jarvis_memory.py", "rebuilt/jarvis_power.py",
    "rebuilt/jarvis_recall.py", "rebuilt/jarvis_router.py",
    "rebuilt/jarvis_sleep.py", "rebuilt/jarvis_voice.py",
    # modules the patches call
    "jarvis_intake.py", "jarvis_feedback.py", "jarvis_skill_discovery.py",
    "jarvis_speed.py", "jarvis_owned_tables.py", "jarvis_agent.py",
    "jarvis_voice_enroll.py", "jarvis_speech.py",
    "jarvis_task_control.py", "jarvis_note_capture.py", "jarvis_power_switch.py",
    "jarvis_wakeword.py",
    "jarvis_token_store.py",
    "jarvis_second_card.py",
    "jarvis_wiki.py",
    "jarvis_big_model.py",
    "jarvis_turn.py", "jarvis_wakebank.py", "jarvis_stopword.py",
    "jarvis_local_http.py", "jarvis_child_env.py",
    "jarvis_voicebank.py",
    # the tools jarvis_agent.py offers
    "jarvis_research.py", "jarvis_ui_control.py", "jarvis_android_control.py",
    "jarvis_browser_control.py", "jarvis_calendar.py", "jarvis_email.py",
    "jarvis_notes.py", "jarvis_home.py",
)


def _same_text(a: Path, b: Path) -> bool:
    # Line endings do not count: a Windows clone may hold CRLF copies of
    # files that are LF here, and Python reads both the same.
    return (a.read_bytes().replace(b"\r\n", b"\n")
            == b.read_bytes().replace(b"\r\n", b"\n"))


def require_shipped(*names: str) -> None:
    """Stop the suite, plainly, if the backend's copy of a shipped module is
    missing or is not the one in this repository.

    Only when JARVIS_BACKEND is set - that is, when the suite is being run
    against a real install. Without this, the suite imported THIS folder's
    copy whenever the backend had none (every suite also puts this folder on
    sys.path), passed, and said nothing about the copy the backend actually
    runs. In the dev container BACKEND is this folder, so there is nothing
    to compare and nothing happens.
    """
    if not os.environ.get("JARVIS_BACKEND") or BACKEND == _HERE:
        return
    problems = []
    for n in names:
        # "rebuilt/jarvis_memory.py" is this repository's path; on the PC the
        # file sits beside jarvis_hud.py under its own name.
        leaf = n.rsplit("/", 1)[-1]
        theirs, ours = BACKEND / leaf, _HERE / n
        shown = "backend\\" + n.replace("/", "\\")
        if not theirs.is_file():
            problems.append(f"{leaf} is not in {BACKEND}, so the feature it carries "
                            f"is switched off there. Copy {shown} into the "
                            f"backend folder (apply-patches.ps1 does this for you).")
        elif ours.is_file() and not _same_text(theirs, ours):
            problems.append(f"{leaf} in {BACKEND} is not the copy in this repository "
                            f"(an older one, most likely). Copy {shown} into "
                            f"the backend folder (apply-patches.ps1 does this for you).")
    if problems:
        for p in problems:
            print("FAIL  " + p)
        print("\nNot run: this suite would have tested this repository's copy "
              "instead of the one your backend uses.")
        sys.exit(1)
