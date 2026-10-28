"""The published base's copy of the owner's own files, when this run has none.

WHY THIS EXISTS (2026-10-27, the partner test-health corrections, item 1)

A handful of suites test the owner's own backend files - `jarvis_hud.py`,
`jarvis_gate.py`, `jarvis_extract.py`, `jarvis_models.py`, `jarvis_skills.py`.
Those files live only on his PC (`backend/.gitignore` refuses them), so in CI
every one of those suites used to skip, and a suite that skips every check
proves nothing: the required `backend` job was green while the wildcard-bind
refusal order, the HUD's Origin check and the approval-egress enumeration had
not been looked at.

THIS REPOSITORY ALREADY HOLDS THE STATE THOSE FILES ARE IN. `jarvis-backend/`
is the published base - `tools/gen_base_from_backend.py` derives it from the
owner's folder, so it carries `jarvis_hud.py` and the other four, at the state
the whole patch stack left them when the base was last re-taken. It is a real
file with the real functions in it, not a stub, which is exactly what a suite
that lifts `_origin_ok` or `_refuse_every_interface` out with `ast` needs.

SO: A SUITE THAT NEEDS ONE OF THOSE FILES FALLS BACK TO THE BASE, AND SAYS SO.

    from _where import BACKEND, explain
    import _base
    BASE = _base.folder("jarvis_hud.py")
    if BASE is not None:
        BACKEND = BASE                 # read the published base instead
        print(f"base: {_base.which(BACKEND, 'jarvis_hud.py')}")
    sys.path.append(str(BASE)) if BASE is not None else None

Three rules, in this order - the base never shadows a real file:

  1. EVERY NAME ASKED FOR IS ALREADY IN THE FOLDER THIS RUN READS (`BACKEND`:
     `JARVIS_BACKEND` when it is set, `backend/` otherwise - a dev container
     symlinks the owner's files there). Return None: read that file.
  2. EVERY NAME IS IN `jarvis-backend/`: return that folder.
  3. Otherwise None, and the suite says what it is missing and skips - honestly,
     in its own SKIPPED list, never as a pass.

RULE 1 IS NOT "JARVIS_BACKEND MEANS THE OWNER'S INSTALL", and that distinction
is the whole reason this is a function and not a variable test.
`backend/run_suites.py` ALWAYS sets `JARVIS_BACKEND`, to the throwaway folder
it staged - so a rule keyed on that variable alone would never fire in the one
job this exists for. What matters is whether the file is in the folder the run
is really reading. On the owner's PC with `--use-env-backend` it is, and his
file wins. In the required `backend` job the staged folder has none of the five,
and the base answers.

WHAT IT DOES NOT CLAIM. The base is the state at the LAST RE-TAKE, not the
owner's live file. A patch newer than that re-take is not in it, so a check
that reads the base can be behind the owner's PC - and this module is not a
substitute for running the suite there with `JARVIS_BACKEND` set. It is the
difference between a required check that reads real code and one that reads
nothing at all, and every suite using it prints which folder it read.

Not a test (no `test_` prefix). Standard library only, and no patch: it is
test plumbing, listed in `backend/test_shipped_modules.py`'s NOT_SHIPPED.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
#: The published base - `tools/gen_base_from_backend.py` writes it, and it
#: carries the five files the owner's backend folder has and this repository
#: otherwise does not.
BASE = REPO / "jarvis-backend"

#: The words a suite prints, so a reader of the log knows which folder answered.
WHY = ("the published base (jarvis-backend/), which is the state the whole patch "
       "stack left when it was last re-taken - NOT the owner's live file")


def folder(*names: str):
    """`jarvis-backend/` when it holds every one of `names` and nothing real
    was named; otherwise None. See the four rules in this module's docstring.

    `names` are bare file names (`"jarvis_hud.py"`), the way a suite writes
    them. Every one of them has to be in one folder or the other: a run that
    has `jarvis_gate.py` but not `jarvis_hud.py` is not a run this should guess
    about.
    """
    if not names:
        return None
    here = install()
    if all((here / n).is_file() for n in names):
        return None
    if all((BASE / n).is_file() for n in names):
        return BASE
    return None


def install() -> Path:
    """The folder this run was told to read: `JARVIS_BACKEND`, else `backend/`.

    Read from the environment each time rather than at import, because the
    runner hands every suite its staged folder in that variable and a suite may
    be imported before it is set (a rehearsal, a test of a test)."""
    return Path(os.environ.get("JARVIS_BACKEND") or HERE).resolve()


def which(path, name: str = "") -> str:
    """One line naming the folder a suite read, for its own header.

    Says `the published base` for `jarvis-backend/`, and for anything else
    names the folder and whether it is the throwaway one the runner staged, so
    a log reader never has to guess whether a green line was earned against the
    owner's live file, a staged copy, or this repository's copy of an older one.
    """
    path = Path(path)
    shown = (path / name) if name else path
    if path.resolve() == BASE.resolve():
        return f"the published base (jarvis-backend/): {shown}"
    staged = os.environ.get("JARVIS_BACKEND")
    word = "the folder JARVIS_BACKEND names" if staged else "this folder"
    return f"{word} {path}: {shown}"


def missing(folder, *names: str) -> list:
    """`_where.missing`, asked of the folder a suite really reads.

    A suite that took the fallback has `BACKEND` pointing at the base, and
    `_where.missing` would still answer about `backend/` - reporting a file as
    absent while it is being read. Same shape, same words, one folder."""
    return [n for n in names if not (Path(folder) / n).is_file()]


def say(path, name: str = "") -> None:
    """Print `which()` for a suite that wants it on its own output."""
    print(f"  file  {which(path, name)}")


def put_on_path(path) -> None:
    """Let `import jarvis_gate` find the base's copy - APPENDED, never first.

    `_where` puts `backend/rebuilt/` and `backend/` at the FRONT of sys.path,
    and they must stay in front: the base carries its own copies of the shipped
    modules, and importing one of those instead of the copy this repository
    tests would quietly swap the code under the suite. Appending means an
    owner file the base holds is found only when nothing earlier has it.
    """
    if path is None:
        return
    entry = str(Path(path))
    if entry not in sys.path:
        sys.path.append(entry)
