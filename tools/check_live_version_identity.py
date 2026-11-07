#!/usr/bin/env python3
"""check_live_version_identity.py - the live backend and the desktop must agree on the version.

    py -3 -B tools/check_live_version_identity.py                  # this PC
    py -3 -B tools/check_live_version_identity.py --backend-path "<live>" --desktop-exe "<exe>"

WHY THIS EXISTS
    Wave 6 was deployed correctly and still showed the wrong version to the owner.
    On 2026-11-06 the live `VERSION` file said 0.2.421 while the installed desktop
    was 0.2.433, and the HUD said "MISMATCH: the backend 0.2.421, but this HUD
    expects 0.2.433". Unit tests and route probes both missed it: the backend was
    healthy, its routes answered, and the one stale thing was the marker file
    beside it. `tools/reconcile_live_backend.py` now CARRIES that marker (step 2b
    of its docstring), and this is the separate, read-only proof that the two
    identity numbers agree after a deploy and a restart.

WHAT IT READS (read-only: nothing is written, started or stopped)
    * the live `VERSION` file beside the backend (`--backend-path`);
    * the installed desktop's `FileVersion` (`--desktop-exe`), through
      PowerShell's `VersionInfo.FileVersion` - the same field the in-app updater
      writes into that `VERSION` file, and the same value the HUD compares.

THE THREE ANSWERS, and why an unreadable one is never a pass
    exit 0  the two agree, and one line says both values;
    exit 1  they DIFFER, and the line names both values;
    exit 2  one of them could not be read (no file, an empty value, no
            PowerShell, a non-Windows host).

    Exit 2 is the project's BLOCKED-is-never-a-pass rule in a checker: a run that
    cannot read the evidence says so and fails, rather than reporting a match it
    never measured. THE ONE FAILURE MODE IT CANNOT SEE: if the deploy forgot the
    `VERSION` write AND the desktop was never updated, both sides are equally
    stale and this agrees with itself. It answers "do these two agree", not "is
    this the release the runbook named" - the runbook's `/api/self/version` ref
    check is the second witness for that.

DEFAULTS
    `--backend-path` is the owner's live folder; `--desktop-exe` is
    `%LOCALAPPDATA%\\Jarvis Desktop\\jarvis-desktop.exe`, and `JARVIS_DESKTOP_EXE`
    overrides it - the same variable `tools/reconcile_live_backend.py` uses, so
    the deploy and the check always name the same desktop.

THE RUNTIME-TREE MODE (the owner's Q6 ruling, 2026-11-06)
    Version identity alone forces a desktop AND phone reinstall for a commit that
    changed no runtime byte at all - a test, a doc, a tool, a CI line. Q6: what
    must be equal is the RUNTIME TREE, so this checker also answers "are the four
    runtime trees of the deployed commit and of current main the same?".

        py -3 -B tools/check_live_version_identity.py --deployed-ref <sha>
        py -3 -B tools/check_live_version_identity.py --main-ref origin/main

    * `--deployed-ref` defaults to the live `_jarvis-state.json`'s
      `resealed.ref` (or `resealed.commit`) under `--backend-path` - the ref
      `tools/reseal_live_install.py` records. `--main-ref` defaults to
      `origin/main`. `--repo` names the checkout to compare in (default: this
      tool's own repository).
    * It runs `git diff <deployed>..<main> -- jarvis-backend/
      jarvis-desktop/src/ jarvis-desktop/src-tauri/src/
      jarvis-client/app/src/main/`. If that is EMPTY it prints exactly
      `PASS (runtime tree identical to deployed ref <short-sha>)` and exits 0:
      no reinstall is forced for a test-only, docs-only, tools-only or CI-only
      merge.
    * A NON-empty diff exits 1 with one line naming the changed runtime files and
      saying a deploy is required. Git, or either ref, unreadable -> exit 2 with
      an UNREADABLE sentence: never a pass on unreadable evidence - the same
      rule as the identity half.
    * When there is NO deployed ref to compare (a freshly deployed tree has no
      `resealed` key - `apply-patches.ps1` drops it on its next finished run),
      the command behaves EXACTLY as it always did: live `VERSION` against the
      installed desktop's FileVersion, 0/1/2. That keeps the deploy gate
      unchanged and puts Q6 where it is meant to be used - the re-check after a
      reseal.

TESTS
    `backend/test_check_live_version_identity.py` proves match -> 0, mismatch -> 1
    and unreadable -> 2 on temporary folders, with the desktop reader injected so
    no test reads this PC's installed app; and proves Q6 on temporary git
    repositories: an identical runtime tree -> 0 with the exact PASS sentence, a
    changed runtime file -> 1 naming it, an unknown ref -> 2, and the default
    (no deployed ref) -> the identity check, unchanged.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

#: The owner's live backend folder: where `jarvis_hud.py` and the `VERSION` file
#: the updater writes both sit. `--backend-path` overrides it.
DEFAULT_BACKEND_PATH = Path(
    "C:/Users/pcadmin/Documents/Claude/Open jarvis files/Desktop program")

#: The installed desktop app, whose FileVersion is the release identity.
#: `JARVIS_DESKTOP_EXE` overrides it; `--desktop-exe` overrides both.
DESKTOP_EXE_ENV = "JARVIS_DESKTOP_EXE"
DEFAULT_DESKTOP_DIR = "Jarvis Desktop"
DESKTOP_EXE_NAME = "jarvis-desktop.exe"

#: The file beside the backend the in-app updater writes.
VERSION_FILE = "VERSION"

#: The deploy record beside the backend. `resealed.ref` is the commit
#: `tools/reseal_live_install.py` last put the live folder on; `apply-patches.ps1`
#: drops that key on its next finished run, which is exactly why a freshly
#: deployed tree falls back to the identity check (see the docstring).
STATE_FILE = "_jarvis-state.json"

#: The four trees that ARE the runtime. A commit that changes only tests, docs,
#: tools, CI or the patch files does not need a desktop or phone reinstall: the
#: bytes the owner runs are identical (the owner's Q6 ruling, 2026-11-06).
RUNTIME_PATHS = ("jarvis-backend/", "jarvis-desktop/src/",
                 "jarvis-desktop/src-tauri/src/",
                 "jarvis-client/app/src/main/")

#: The ref the runtime tree is compared with unless `--main-ref` says otherwise.
DEFAULT_MAIN_REF = "origin/main"

#: Exit codes, named so the tests and the runbook read the same numbers.
MATCH = 0
MISMATCH = 1
UNREADABLE = 2


def desktop_exe_path(override=None) -> Path:
    """An explicit override, else JARVIS_DESKTOP_EXE, else the installed default."""
    if override:
        return Path(override)
    env = os.environ.get(DESKTOP_EXE_ENV, "").strip()
    if env:
        return Path(env)
    local = os.environ.get("LOCALAPPDATA", "").strip()
    base = Path(local) if local else Path(os.path.expanduser("~")) / "AppData" / "Local"
    return base / DEFAULT_DESKTOP_DIR / DESKTOP_EXE_NAME


def _powershell() -> str:
    for exe in ("powershell", "powershell.exe", "pwsh", "pwsh.exe"):
        found = shutil.which(exe)
        if found:
            return found
    return ""


def read_live_version(backend_path) -> str:
    """The live `VERSION` file's text, stripped; "" when it cannot be read.

    An empty file is "" too: that is unreadable evidence, never version "". The
    value is read as text with replacement, so a broken encoding is reported, not
    raised - the caller turns "" into exit 2."""
    try:
        path = Path(backend_path) / VERSION_FILE
        if not path.is_file():
            return ""
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def read_desktop_file_version(path) -> str:
    """The installed exe's FileVersion, read-only; "" when it cannot be read.

    Windows only: the field lives in the PE's version resource, and PowerShell's
    `VersionInfo.FileVersion` is how this project already reads it
    (`tools/reconcile_live_backend.py`'s `read_desktop_version`). Any failure -
    no file, no PowerShell, a non-Windows host, a blank field - returns "", and
    the caller exits 2 rather than reporting a pass."""
    path = Path(path)
    if os.name != "nt" or not path.is_file():
        return ""
    exe = _powershell()
    if not exe:
        return ""
    quoted = str(path).replace("'", "''")
    script = f"(Get-Item -LiteralPath '{quoted}').VersionInfo.FileVersion"
    try:
        proc = subprocess.run([exe, "-NoProfile", "-NonInteractive", "-Command", script],
                              capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return ""
    return (proc.stdout or "").strip()


def check(backend_path, desktop_exe=None, *, version_reader: Optional[Callable] = None,
          exe_reader: Optional[Callable] = None, out: Optional[Callable] = None) -> int:
    """Compare the two identity values, print ONE line, return the exit code.

    `version_reader` and `exe_reader` are the tests' own seam; by default they are
    the two real readers above, so a run on this PC reads the real files and a test
    never touches the owner's installed app."""
    out = out or print
    read_version = version_reader or read_live_version
    read_exe = exe_reader or read_desktop_file_version
    live = Path(backend_path)
    exe = desktop_exe_path(desktop_exe)
    live_version = str(read_version(live) or "").strip()
    if not live_version:
        out(f"UNREADABLE: no VERSION file to read at {live / VERSION_FILE} - "
            f"cannot prove the identity, and that is not a pass.")
        return UNREADABLE
    exe_version = str(read_exe(exe) or "").strip()
    if not exe_version:
        out(f"UNREADABLE: no FileVersion could be read from {exe} - "
            f"cannot prove the identity, and that is not a pass.")
        return UNREADABLE
    if live_version != exe_version:
        out(f"MISMATCH: the live VERSION says {live_version}, but the installed "
            f"desktop is {exe_version} - run the deploy's release-marker step, then "
            f"restart Jarvis.")
        return MISMATCH
    out(f"MATCH: the live VERSION and the installed desktop are both {live_version}.")
    return MATCH


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare the live backend's VERSION file with the installed "
                    "desktop's FileVersion (read-only), or - with a deployed ref - "
                    "the runtime trees of the deployed commit and current main.")
    parser.add_argument("--backend-path", default=str(DEFAULT_BACKEND_PATH),
                        help="the folder holding the live VERSION file and "
                             f"jarvis_hud.py (default: {DEFAULT_BACKEND_PATH})")
    parser.add_argument("--desktop-exe", default="",
                        help="the installed desktop program whose FileVersion is "
                             "the release identity (default: "
                             "%%LOCALAPPDATA%%\\Jarvis Desktop\\jarvis-desktop.exe, "
                             f"or ${DESKTOP_EXE_ENV})")
    parser.add_argument("--deployed-ref", default="",
                        help="the commit the live backend was sealed from; a "
                             "runtime tree identical to it needs no reinstall. "
                             "Default: read from "
                             f"{STATE_FILE}'s resealed.ref under --backend-path")
    parser.add_argument("--main-ref", default=DEFAULT_MAIN_REF,
                        help="the ref the runtime tree is compared with "
                             f"(default: {DEFAULT_MAIN_REF})")
    parser.add_argument("--repo", default="",
                        help="the git checkout to compare in (default: this "
                             "tool's own repository)")
    ns = parser.parse_args(argv)
    deployed = str(ns.deployed_ref or "").strip() or read_deployed_ref(ns.backend_path)
    if deployed:
        repo = Path(ns.repo) if ns.repo else repo_root()
        return check_runtime_tree(repo, deployed, ns.main_ref)
    return check(ns.backend_path, ns.desktop_exe)


# ==========================================================================
#   Q6: the runtime-tree check (the owner's ruling, 2026-11-06)
# ==========================================================================

def repo_root() -> Path:
    """This repository: the tool lives in `tools/`, so its parent is the root."""
    return Path(__file__).resolve().parent.parent


def read_deployed_ref(backend_path) -> str:
    """`resealed.ref` (else `resealed.commit`) from the live record - or "".

    "" is an honest "there is no deployed ref to compare", never an error: a
    freshly deployed tree has no `resealed` key, and the caller then falls back
    to the identity check exactly as before. A file that is not JSON, or a
    record without the key, reads as "" too - there is nothing to prove.
    """
    try:
        path = Path(backend_path) / STATE_FILE
        if not path.is_file():
            return ""
        doc = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return ""
    sealed = doc.get("resealed") if isinstance(doc, dict) else None
    if not isinstance(sealed, dict):
        return ""
    for key in ("ref", "commit"):
        got = str(sealed.get(key) or "").strip()
        if got:
            return got
    return ""


def _git(repo, *args):
    """Run one read-only git command in `repo`; a non-zero exit is returned."""
    return subprocess.run(["git", "-C", str(repo)] + list(args),
                          capture_output=True, text=True)


def resolve_ref(repo, ref) -> str:
    """The full commit sha `ref` names, or "" when git cannot resolve it."""
    try:
        got = _git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    except OSError:
        return ""
    return (got.stdout or "").strip() if got.returncode == 0 else ""


def changed_runtime_files(repo, deployed_ref, main_ref):
    """("identical"|"changed"|"unreadable", [paths] or why).

    The diff is taken over RUNTIME_PATHS only, so a test, doc, tool or CI commit
    is "identical" on purpose - that is the whole point of Q6.
    """
    deployed = resolve_ref(repo, deployed_ref)
    main = resolve_ref(repo, main_ref)
    if not deployed:
        return "unreadable", (f"git cannot resolve the deployed ref "
                              f"{deployed_ref!r} in {repo}")
    if not main:
        return "unreadable", (f"git cannot resolve the main ref {main_ref!r} "
                              f"in {repo}")
    try:
        got = _git(repo, "diff", "--name-only", f"{deployed}..{main}", "--",
                   *RUNTIME_PATHS)
    except OSError:
        return "unreadable", f"git could not be run in {repo}"
    if got.returncode != 0:
        return "unreadable", ("git diff failed: "
                              + (got.stderr or "").strip()[:300])
    files = [line.strip() for line in (got.stdout or "").splitlines() if line.strip()]
    return ("changed" if files else "identical"), files


def check_runtime_tree(repo, deployed_ref, main_ref, *,
                       out: Optional[Callable] = None) -> int:
    """Q6's answer: ONE line, and 0 identical / 1 changed / 2 unreadable."""
    out = out or print
    state, detail = changed_runtime_files(repo, deployed_ref, main_ref)
    if state == "unreadable":
        out(f"UNREADABLE: {detail} - the runtime trees cannot be compared, "
            f"and that is not a pass.")
        return UNREADABLE
    deployed = resolve_ref(repo, deployed_ref)
    short = deployed[:7] or str(deployed_ref)[:7]
    if state == "identical":
        out(f"PASS (runtime tree identical to deployed ref {short})")
        return MATCH
    shown = ", ".join(detail[:5]) + (" ..." if len(detail) > 5 else "")
    out(f"CHANGED: {len(detail)} runtime file(s) differ between {short} and "
        f"{main_ref} ({shown}) - a deploy is required.")
    return MISMATCH


if __name__ == "__main__":
    sys.exit(main())
