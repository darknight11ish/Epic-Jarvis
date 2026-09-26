#!/usr/bin/env python3
"""
Writes backend/patch-history/: every EARLIER committed version of every patch
scripts/apply-patches.ps1 can apply, so the script can recognise one on the
owner's backend and replace it.

WHY

apply-patches.ps1 works out what is already on a backend by reversing patches
(`git apply --reverse`). That only works with the exact text that went on. A
patch that was edited after the owner applied it cannot take its own older
version off, so the script used to stop with "patch(es) will not apply" and
the owner was stuck. With every older text kept here, the script tries them,
newest first, and takes off whichever one is really there.

WHAT IT WRITES

    backend/patch-history/<name>/<short-sha>.patch
    backend/patch-history/rebuilt-patches/<name>/<short-sha>.patch
    backend/patch-history/index.tsv

<name> is the patch's file name without ".patch". <short-sha> is the commit
that FIRST had that exact text. A text identical to the current file is left
out (the script already has it). index.tsv lists every version, per patch,
newest first - the order the script tries them in. It is tab-separated so
Windows PowerShell 5.1 reads it with no JSON parser.

RUN IT after editing any patch, BEFORE committing the edit:

    python3 tools/build_patch_history.py

It reads `git log` from the commit you are on and the patch files as they are
on disk, so the version you are replacing is already in the log and lands
here. backend/test_patch_history.py fails when this folder is out of date, and
CI runs that test.

    python3 tools/build_patch_history.py --check    # compare only, write nothing
    python3 tools/build_patch_history.py --out DIR  # write somewhere else
"""
import argparse
import filecmp
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
HISTORY = BACKEND / "patch-history"

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
import _stack  # noqa: E402

_TARGET_RE = re.compile(r"^\+\+\+ b/(\S+)", re.MULTILINE)

INDEX_HEADER = (
    "# Every earlier committed version of each patch, newest first per patch.\n"
    "# Written by tools/build_patch_history.py - do not edit by hand.\n"
    "# Columns: patch, file (under backend/patch-history/), commit, date, subject\n"
)


class NoHistory(RuntimeError):
    """git, or the full history, is not available here."""


def git(*args: str) -> bytes:
    try:
        r = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, check=False)
    except FileNotFoundError as e:
        raise NoHistory("git is not installed") from e
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.decode(errors='replace').strip()}")
    return r.stdout


def require_full_history() -> None:
    try:
        inside = git("rev-parse", "--is-inside-work-tree").strip()
    except RuntimeError as e:
        raise NoHistory("this folder is not a git checkout") from e
    if inside != b"true":
        raise NoHistory("this folder is not a git checkout")
    if git("rev-parse", "--is-shallow-repository").strip() == b"true":
        raise NoHistory("this is a shallow clone (only recent commits are here); "
                        "run `git fetch --unshallow` first")


def lf(data: bytes) -> bytes:
    # The same normalisation apply-patches.ps1 does before applying anything.
    return data.replace(b"\r\n", b"\n")


def current_patches() -> list:
    """[(key, path)] for every patch the script can apply. key uses '/'."""
    out = [(p.name, p) for p in sorted(BACKEND.glob("*.patch"))]
    out += [(f"rebuilt-patches/{p.name}", p) for p in sorted((BACKEND / "rebuilt-patches").glob("*.patch"))]
    return out


def well_formed(text: bytes) -> bool:
    """False when some hunk in `text` will not apply even to a pre-image
    built purely from its own context/removed lines - `_stack`'s own test
    for a corrupt patch (an `@@` header whose line counts do not match the
    lines that actually follow it; `git apply` rejects this before it even
    looks at a real file). A text that fails this could never have gone onto
    anyone's real backend, so it must never be archived as an "earlier
    version" the owner's PC might carry: `versions()` calls this so a text
    like that is skipped, not written to backend/patch-history, where it
    would make `git apply --reverse` fail for good, on a version that was
    never really installable anywhere (found the hard way: a crisis-help-line
    patch's own header claimed 20 new lines and had 24, 2026-09-27).

    Without git on PATH, nothing here can be checked - returns True rather
    than block the whole run on an environment gap unrelated to any patch."""
    git_bin = shutil.which("git")
    if not git_bin:
        return True
    decoded = text.decode("utf-8", errors="replace")
    targets = sorted(set(_TARGET_RE.findall(decoded)))
    if not targets:
        return True  # no "+++ b/..." line at all - not a file patch this script reads
    d = Path(tempfile.mkdtemp(prefix="jarvis-patch-check-"))
    try:
        for target in targets:
            f = d / target
            for hunk, pre in _stack.hunks(decoded, target):
                f.write_text("\n".join(pre) + ("\n" if pre else ""), encoding="utf-8", newline="\n")
                if not _stack._apply(git_bin, d, target, hunk):
                    return False
        return True
    finally:
        shutil.rmtree(d, ignore_errors=True)


def log_versions(rel: str) -> list:
    """[(commit, date, subject)] newest first: every commit that changed `rel`.

    Deliberately NOT `git log --follow`. No patch here has ever been renamed,
    and --follow's rename GUESSING, tried on this repository, walked from
    rebuilt-patches/extraction-wiring.patch into the history of the full
    extraction-wiring.patch because the two texts are similar. That made the
    output depend on git's similarity heuristics, and so on the git version.
    (The script tries the full patch's versions for a split half on its own,
    on purpose - see apply-patches.ps1.) If a patch is ever renamed, keep the
    old name's history by hand, or the script cannot recognise it.
    """
    raw = git("log", "--format=%x00%H%x09%cI%x09%s", "--", rel)
    out = []
    for block in raw.split(b"\x00")[1:]:
        line = block.decode("utf-8", errors="replace").strip()
        if line:
            sha, date, subject = (line.split("\t", 2) + ["", ""])[:3]
            out.append((sha, date, subject))
    return out


def versions(key: str, path: Path) -> list:
    """Distinct earlier texts of one patch, newest first.

    [(first_commit, date, subject, bytes)]: the commit that INTRODUCED the text
    (its oldest appearance), ordered by the text's NEWEST appearance - so a
    text that was current until yesterday is tried before one from last week.

    A text that fails `well_formed()` (a corrupt hunk header) is left out
    entirely, and printed to stderr so an out-of-date `--check` failure is
    not the only sign of it - it was never really installable anywhere, so
    there is no backend it could need to be recognised on.
    """
    rel = path.relative_to(ROOT).as_posix()
    current = lf(path.read_bytes())
    seen = {}     # text -> [commit, date, subject] of its oldest appearance
    order = []    # texts, by newest appearance
    for sha, date, subject in log_versions(rel):
        try:
            text = lf(git("cat-file", "blob", f"{sha}:{rel}"))
        except RuntimeError:
            continue  # the commit deleted it
        if text == current:
            continue
        if not well_formed(text):
            print(f"{key}: leaving out the version from {sha[:7]} - a hunk header's "
                  f"line counts do not match its own lines (corrupt; could never "
                  f"have applied to any real backend)", file=sys.stderr)
            continue
        if text not in seen:
            order.append(text)
        seen[text] = (sha, date, subject)  # keeps overwriting: ends on the oldest
    return [(*seen[t], t) for t in order]


def build(out_dir: Path) -> int:
    require_full_history()
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    rows, total = [], 0
    for key, path in current_patches():
        stem = key[: -len(".patch")]
        used = set()
        for sha, date, subject, text in versions(key, path):
            short = sha[:7]
            n = 7
            while short in used:  # two texts first seen in one commit: impossible, but cheap
                n += 1
                short = sha[:n]
            used.add(short)
            rel = f"{stem}/{short}.patch"
            dest = out_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(text)
            subject = " ".join(subject.replace("\t", " ").split())
            rows.append(f"{key}\t{rel}\t{sha}\t{date}\t{subject}\n")
            total += 1
    with open(out_dir / "index.tsv", "w", encoding="utf-8", newline="\n") as f:
        f.write(INDEX_HEADER)
        f.writelines(rows)
    return total


def differences(a: Path, b: Path) -> list:
    """Relative paths that differ between two trees (missing on either side too)."""
    def files(d: Path) -> set:
        return {p.relative_to(d).as_posix() for p in d.rglob("*") if p.is_file()} if d.exists() else set()
    fa, fb = files(a), files(b)
    out = sorted(fa ^ fb)
    out += sorted(r for r in fa & fb if not filecmp.cmp(a / r, b / r, shallow=False))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="compare with backend/patch-history, write nothing")
    ap.add_argument("--out", type=Path, default=HISTORY)
    a = ap.parse_args()
    try:
        if a.check:
            with tempfile.TemporaryDirectory() as tmp:
                fresh = Path(tmp) / "patch-history"
                build(fresh)
                diff = differences(fresh, HISTORY)
            if diff:
                print("backend/patch-history is out of date. Differs:")
                for d in diff:
                    print(f"  {d}")
                print("Fix: python3 tools/build_patch_history.py, then commit the result.")
                return 1
            print("backend/patch-history is up to date.")
            return 0
        n = build(a.out)
    except NoHistory as e:
        print(f"Cannot read the patches' history: {e}.")
        return 2
    print(f"Wrote {n} earlier version(s) to {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
