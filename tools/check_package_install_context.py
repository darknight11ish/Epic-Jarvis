#!/usr/bin/env python3
"""A package install must not write into this repository.

    python3 tools/check_package_install_context.py --manager pip
    python3 tools/check_package_install_context.py --manager uv
    python3 tools/check_package_install_context.py --run -- python3 -m pip install -r backend/requirements.txt

WHY THIS EXISTS. On 2026-11-18 a delegated agent ran `pip` with the repository
root as its working directory and TMP/TEMP pointing inside the tree. Pip left
seventeen `pip-metadata-*` and `pip-unpack-*` folders sitting at the root,
untracked; they sat there until somebody noticed by accident, and one `git add
-A` would have committed them. It is not the first time a temp folder inside
this checkout has cost a night: on 2026-10-08 an environment whose TMPDIR
pointed inside the repository made a dozen suites assert against an EMPTY
stand-in file (the story is in `backend/_gitapply.py`'s docstring). The class
is old; what was missing was a guard that refuses the install BEFORE it runs.

WHAT IT REFUSES (exit 1), for `pip` and for `uv`:

  * the working directory IS the repository root - the checkout the tool lives
    in. A subdirectory is allowed, because the audit job's own pip step runs
    from `jarvis-desktop/src-tauri`; the root is where a stray wheel, a
    `--target .` install or uv's `.venv` lands in the repository itself.
  * TMP, TEMP, TMPDIR or TEMPDIR resolves INSIDE the repository, at the root
    or in a subfolder. That is exactly how the seventeen folders arrived.
  * a folder the manager itself would use resolves inside the repository:
    `PIP_CACHE_DIR` for pip; `UV_CACHE_DIR`, `UV_PYTHON_INSTALL_DIR` and
    `UV_TOOL_DIR` for uv.

Every refusal names the offending folder and says the fix, in these words:
"run the install from a scratch directory, or set TMP/TEMP outside the repo".

NOT CHECKED IS NOT A PASS (exit 3). When the guard cannot tell, it prints
"not checked: <why>" in those words and exits 3, so no run can read silence as
agreement (the project's BLOCKED-is-never-a-pass rule). That happens when the
platform is neither Windows nor POSIX (its temporary-folder rules are not
known here), the working directory cannot be read, or no package manager is
named - an install of `conda` or some other manager is outside what this guard
can judge. It says so instead of guessing.

A CI RUNNER IS CHECKED, NOT ASSUMED. On a GitHub runner this checks the
runner's own checkout and temporary folder and says so in one line; it does
not claim to have checked the owner's PC. The copy of the check that protects
the owner's machine is the one a person or a delegate runs before installing -
`backend/test_package_install_guards.py` proves every branch below can fail on
fixtures the suite makes and removes itself.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent

#: Exit codes, and the reason each one exists:
#:   0 - the context was checked and is safe, so the install may run.
#:   1 - REFUSED: a package install here would write into the repository.
#:   3 - NOT CHECKED: this guard cannot tell, and that is neither a pass nor a
#:       failure of the tree. 2 is left alone because the deploy tools use it
#:       for "refused before writing", and this guard never writes.
PASS, REFUSED, NOT_CHECKED = 0, 1, 3

#: The two managers this guard knows. Anything else is NOT CHECKED.
MANAGERS = ("pip", "uv")

#: The variables a temporary folder is named by, in the order a person reads.
TEMP_VARS = ("TMP", "TEMP", "TMPDIR", "TEMPDIR")

#: The folders each manager would create for itself, when its own variable
#: names them. `TMP`/`TEMP` above applies to both managers.
MANAGER_DIR_VARS = {
    "pip": ("PIP_CACHE_DIR",),
    "uv": ("UV_CACHE_DIR", "UV_PYTHON_INSTALL_DIR", "UV_TOOL_DIR"),
}

#: The one sentence a refusal must carry, in these words. A reader who copies
#: the fix from the message gets a context this guard passes.
FIX = "run the install from a scratch directory, or set TMP/TEMP outside the repo"


def _norm(path):
    """A path safe to compare: absolute, symlinks followed, case folded.

    Windows is case-insensitive and both the environment and `git` hand back
    paths in the case they were typed, so `/users/PC/Repo` and
    `C:\\Users\\pc\\Repo` must compare equal. `realpath` is asked without
    `strict`, so a temp folder that does not exist yet still compares.
    """
    text = os.path.expanduser(str(path))
    try:
        return os.path.normcase(os.path.realpath(os.path.abspath(text)))
    except (OSError, ValueError):
        return os.path.normcase(os.path.abspath(text))


def _inside(path, parent):
    """True when `path` is `parent` itself or anywhere under it."""
    child, root = _norm(path), _norm(parent)
    if child == root:
        return True
    try:
        return os.path.commonpath([child, root]) == root
    except ValueError:
        # Different drives on Windows: no common path, so not inside.
        return False


def _command_name(token):
    """The last path part of one command word, whichever slash it was written with.

    Both separators are split on, not just this platform's: a command line
    handed to a guard can spell a path in the other platform's style, and this
    guard runs on Linux in CI as well as on the owner's Windows PC. The whole
    point is a case the suite pins - `C:\\Python312\\Scripts\\pip.exe` must read
    as `pip` on a POSIX runner too. `Path(token).name` follows only THIS
    platform's separator, so on POSIX it hands back the whole string and the
    manager is missed.
    """
    return re.split(r"[\\/]", str(token))[-1].lower()


def manager_from_command(command):
    """"pip" or "uv" when the command line says which manager will run.

    Reads what the words mean, not what the file is called: `python -m pip`,
    `pip`, `pip3` and `uv pip install` / `uv sync` all answer. A command that
    names neither is None, and the caller reports NOT CHECKED rather than
    running it.
    """
    tokens = [str(token) for token in command]
    for index, token in enumerate(tokens):
        name = _command_name(token)
        if name.endswith(".exe"):
            name = name[:-4]
        if name in ("pip", "pip3"):
            return "pip"
        if name == "uv":
            return "uv"
        if token in ("-m", "--module") and index + 1 < len(tokens):
            module = tokens[index + 1].lower()
            if module in MANAGERS:
                return module
    return None


def _temp_folders(manager, environ):
    """[(variable or phrase, value)] for every folder an install would write in.

    The named variables win because they are what the manager reads. The
    folder `tempfile` resolves on its own is added too, because on a machine
    where none of the four is set (a plain Linux shell) that is where the
    folders really go - and a `tempfile.tempdir` set inside the repository by
    a caller is exactly the 2026-10-08 failure.
    """
    folders, seen = [], set()
    for name in TEMP_VARS + MANAGER_DIR_VARS.get(manager, ()):
        value = str(environ.get(name) or "").strip()
        if not value:
            continue
        key = _norm(value)
        if key in seen:
            continue
        seen.add(key)
        folders.append((name, value))
    try:
        system = tempfile.gettempdir()
    except (OSError, RuntimeError):
        system = ""
    if system and _norm(system) not in seen:
        folders.append(("the system temporary folder", system))
    return folders


def evaluate(manager, *, cwd=None, environ=None, repo=None, platform=None):
    """One verdict and its lines: ("pass" | "refused" | "not checked", [str]).

    Every input is a parameter so `backend/test_package_install_guards.py` can
    drive the refusal on this machine's real folders without moving any folder
    or changing any environment variable for the next test.
    """
    manager = str(manager or "").lower()
    env = dict(os.environ if environ is None else environ)
    root = Path(repo) if repo is not None else REPO
    system = platform if platform is not None else os.name

    if manager not in MANAGERS:
        return "not checked", [
            f'not checked: "{manager}" is not pip or uv, so where it writes on '
            f"this machine cannot be told"]
    if system not in ("posix", "nt"):
        return "not checked", [
            f"not checked: this platform ({system}) is neither Windows nor "
            f"POSIX, so its temporary-folder rules are unknown here"]
    try:
        where = Path(cwd if cwd is not None else os.getcwd()).resolve()
    except OSError as exc:
        return "not checked", [
            f"not checked: the working directory could not be read ({exc})"]

    refused = []
    if _norm(where) == _norm(root):
        refused.append(f"the working directory is the repository root: {where}")
    # A subdirectory is allowed: the audit job's own pip step runs from
    # `jarvis-desktop/src-tauri`, and only the root is the class the
    # 2026-11-18 incident belongs to.
    checked = []
    for name, value in _temp_folders(manager, env):
        if _inside(value, root):
            refused.append(f"{name} is inside the repository: {value} "
                           f"(the repository is {root})")
        else:
            checked.append(f"{name} = {value}")

    if refused:
        return "refused", refused
    if not checked:
        return "not checked", [
            f"not checked: no temporary folder could be named for a {manager} "
            f"install and the system temporary folder could not be read, so "
            f"where it would write cannot be told"]
    lines = [f"the working directory ({where}) is not the repository root "
             f"({root})",
             "temporary folders outside it: " + "; ".join(checked)]
    return "pass", lines


def _print_verdict(manager, verdict, lines):
    if verdict == "pass":
        print(f"ok    a {manager} install would not write into the repository")
        for line in lines:
            print("      " + line)
        if os.environ.get("GITHUB_ACTIONS"):
            print("      on a CI runner (GITHUB_ACTIONS is set): this checked "
                  "the runner's own throwaway checkout, not the owner's PC")
        return PASS
    if verdict == "refused":
        print(f"FAIL  a {manager} install would write into the repository")
        for line in lines:
            print("      " + line)
        print("      " + FIX)
        print("      nothing was installed; this is a refusal, not a warning")
        return REFUSED
    for line in lines:
        print(line)
    return NOT_CHECKED


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Refuse a pip or uv install that would write into this "
                    "repository (the checkout this script lives in).")
    parser.add_argument(
        "--manager", default="auto",
        help="which package manager is about to run - pip or uv; 'auto' reads "
             "it from the command given to --run (default: auto); any other "
             "name is reported as NOT CHECKED, never as a pass")
    parser.add_argument(
        "--run", action="store_true",
        help="run the command after '--' only when the context is safe; never "
             "run it when the guard refuses or cannot tell")
    parser.add_argument(
        "command", nargs=argparse.REMAINDER,
        help="the install command to run, after '--' (e.g. -- python3 -m pip "
             "install -r backend/requirements.txt)")
    args = parser.parse_args(argv)

    command = list(args.command)
    while command and command[0] == "--":
        command.pop(0)

    manager = args.manager
    if manager == "auto":
        manager = manager_from_command(command) if args.run else ""
    if not manager:
        print("not checked: no package-manager command was given, so which "
              "manager is about to run cannot be told; pass --manager pip or "
              "--manager uv (this is not a pass)")
        return NOT_CHECKED

    verdict, lines = evaluate(manager)
    code = _print_verdict(manager, verdict, lines)
    if code != PASS:
        return code
    if not args.run:
        return PASS
    if not command:
        print("not checked: --run was given with no command after '--', so "
              "there is nothing to run and nothing to check (not a pass)")
        return NOT_CHECKED
    print("      running: " + " ".join(command))
    sys.stdout.flush()
    try:
        return subprocess.run(command).returncode
    except OSError as exc:
        print(f"not checked: the command could not be started ({exc})")
        return NOT_CHECKED


if __name__ == "__main__":
    sys.exit(main())
