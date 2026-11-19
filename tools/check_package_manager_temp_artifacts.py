#!/usr/bin/env python3
"""No package manager's temporary folders are sitting in the repository root.

    python3 tools/check_package_manager_temp_artifacts.py

WHY THIS EXISTS. On 2026-11-18 a delegated agent ran `pip` with the repository
root as its working directory and TMP/TEMP inside the tree. Pip left seventeen
folders at the root - `pip-metadata-*` and `pip-unpack-*` - untracked and
unremarked, until somebody noticed by accident. One `git add -A` and they were
in the repository for good, a third version of the failure `.gitignore`'s own
history records (`dshwork/`, `.dsh-scratch/`). `tools/check_package_install_
context.py` is the guard that should stop that install. This is the second
half: if the guard is ever bypassed, this says what is lying there and how to
remove it, instead of waiting for an accident.

WHAT IT LOOKS AT. Only the TOP LEVEL of the repository this script lives in,
which is where a temp folder appears when the install runs there. A name is a
finding when it matches:

  * `pip-metadata-*` - the metadata temporary folder pip made;
  * `pip-unpack-*` - the unpack temporary folder pip made;
  * `pip-*` with a random suffix - the rest of pip's family
    (`pip-build-env-<random>`, `pip-install-<random>`,
    `pip-req-build-<random>`); the suffix must be 8+ random characters, so a
    real name like `pip-notes.md`, `pip-tools` or `pip-requirements.txt` is
    not a finding;
  * `*.dist-info` at the root - the metadata folder an install leaves behind
    when it writes into a folder it was pointed at;
  * `node_modules` at the root - `.gitignore` line 36 already hides an
    untracked one, so only a TRACKED `node_modules` is reported.

It is a checker, not a cleaner: it never deletes or moves anything. It prints
each path it found, says whether it is tracked or untracked, and prints the
commands that remove it.

WHAT IT DOES NOT REPORT, and why that is correct rather than blind:

  * a `pip-*` name INSIDE the tree - a test fixture such as
    `backend/tests/fixtures/pip-unpack-abc12345/` is legitimate, and a fixture
    is not the class this guards. Only the root is searched.
  * anything `.gitignore` already hides, which cannot reach a commit: that is
    why an untracked `node_modules/` at the root is not a finding (the ignore
    rule is line 36), and why `.dsh-scratch/` - ignored - is never read.
  * a matching path that is not tracked and not ignored is a finding even if
    it is empty: pip can leave an empty shell behind.

NOT CHECKED IS NOT A PASS (exit 3). The check asks `git` whether a matching
path is tracked, so it prints "not checked: <why>" in those words and exits 3
when git is unavailable or the folder is not a work tree - silence must never
read as agreement. The exit codes are 0 clean, 1 artifacts found, 3 not
checked.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent

#: A pip temporary folder's random suffix is `tempfile`'s eight [a-z0-9_]
#: characters (measured in pip's own source: `tempfile.mkdtemp` names every
#: one of the seventeen folders in the 2026-11-18 incident). Eight is the
#: floor, not the exact length, so a manager that changes the length is still
#: caught.
_RANDOM = r"[A-Za-z0-9_]{8,}"

#: (pattern, what it is). Order matters only for the message: the two named
#: folders pip created get their own words, and the general family follows.
PATTERNS = (
    (re.compile(r"^pip-metadata-" + _RANDOM + r"$"), "a pip metadata temporary folder"),
    (re.compile(r"^pip-unpack-" + _RANDOM + r"$"), "a pip unpack temporary folder"),
    (re.compile(r"^pip-(?:[A-Za-z0-9]+-)*" + _RANDOM + r"$"),
     "a pip temporary folder with a random suffix"),
    (re.compile(r"^[^/\\]+\.dist-info$"), "an installed package's metadata folder"),
    (re.compile(r"^node_modules$"), "a node_modules folder at the root"),
)

#: Removed with the same words on every platform, and printed per finding.
REMOVE_UNTRACKED = (
    "untracked: Remove-Item -Recurse -Force '<name>'   (PowerShell), or\n"
    "                   rm -rf -- '<name>'   (Linux or macOS)"
)
REMOVE_TRACKED = (
    "tracked:   git rm -r --cached -- '<name>'   (keeps it on disk), then "
    "delete the folder"
)


def artifact_reason(name):
    """What the top-level `name` is, or None when it is not a temp artifact."""
    for pattern, why in PATTERNS:
        if pattern.search(str(name)):
            return why
    return None


def _git(root, *args):
    """The finished `git -C root ...` run, or None when git cannot be run."""
    try:
        return subprocess.run(["git", "-C", str(root), *args],
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None


def _tracked_top_level(root):
    """The top-level names git tracks, or None when there is no work tree.

    `git ls-files -z` lists paths from the root with `/` separators; the first
    component of each is the top-level entry, which is all this check reads.
    """
    done = _git(root, "ls-files", "-z", "--", ".")
    if done is None or done.returncode != 0:
        return None
    names = set()
    for path in done.stdout.split("\0"):
        if path:
            names.add(path.replace("\\", "/").split("/")[0])
    return names


def _ignored(root, name):
    """True when `.gitignore` hides `name` at the root of this work tree."""
    done = _git(root, "check-ignore", "-q", "--", name)
    return done is not None and done.returncode == 0


def scan(root=REPO):
    """(findings, entries_checked) for the top level of `root`.

    Each finding is (name, why, "tracked" | "untracked"). Raises RuntimeError
    with the reason when tracked-from-untracked cannot be told, which the
    caller reports as NOT CHECKED rather than as a pass.
    """
    root = Path(root)
    if not root.is_dir():
        raise RuntimeError(f"{root} is not a folder, so there is no repository "
                           f"root to check")
    tracked = _tracked_top_level(root)
    if tracked is None:
        raise RuntimeError(
            f"git is not available, or {root} is not a git work tree, so a "
            f"matching path cannot be told from one a commit would carry")
    try:
        entries = sorted(root.iterdir(), key=lambda item: item.name)
    except OSError as exc:
        raise RuntimeError(f"the top level of {root} could not be listed "
                           f"({exc})") from exc

    findings = []
    for entry in entries:
        if entry.name == ".git":
            continue
        why = artifact_reason(entry.name)
        if not why:
            continue
        if entry.name in tracked:
            findings.append((entry.name, why, "tracked"))
        elif _ignored(root, entry.name):
            # .gitignore already keeps it out of a commit (node_modules line
            # 36 is the case the brief names as "already covered").
            continue
        else:
            findings.append((entry.name, why, "untracked"))
    return findings, len([e for e in entries if e.name != ".git"])


def _print_findings(root, findings):
    print(f"FAIL  package-manager temporary folders are in the repository root:"
          f" {root}")
    for name, why, kind in findings:
        print(f"      {name!r} - {why} ({kind})")
    print("      how to remove them:")
    for name, _why, kind in findings:
        print("        " + (REMOVE_TRACKED if kind == "tracked"
                            else REMOVE_UNTRACKED).replace("<name>", name))
    print("      then re-run: python -B tools/check_package_manager_temp_artifacts.py")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Fail when a package manager's temporary folder is "
                    "sitting at the root of this repository.")
    parser.add_argument(
        "--root", default=str(REPO),
        help="the repository root to check (default: the checkout this script "
             "lives in; for the tests and for a copy of the tree)")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    try:
        findings, entries = scan(root)
    except RuntimeError as exc:
        print(f"not checked: {exc} - this run is NOT a pass")
        return 3
    if findings:
        _print_findings(root, findings)
        return 1
    print(f"ok    no package-manager temporary folder is in the repository "
          f"root: {root}")
    print(f"      checked {entries} top-level entries; a matching name inside "
          f"the tree (a test fixture, .dsh-scratch) is not this check's class")
    return 0


if __name__ == "__main__":
    sys.exit(main())
