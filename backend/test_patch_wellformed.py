"""test_patch_wellformed.py - every patch the installer will run is a patch git
can actually read.

    python3 backend/test_patch_wellformed.py

WHY THIS EXISTS. `handoff-mode.patch` shipped to main on 2026-10-09 with its
FIRST HUNK HEADER ONE LINE SHORT:

    @@ -190,6 +190,7 @@        <- said 6 original lines
        "quiz_cloud_grade",
        "read_web_page",
        "raise_api_limit",
        "lower_api_limit",
    +   "handoff_keep_offering",
    })
    <blank>
    <blank>                     <- but the body supplied 7

`git apply` reads a hunk for exactly as many lines as the header claims, so it
finished the first hunk a line early, met the leftover blank line, then met
`@@ -840,4 +841,14 @@` and refused the whole file:

    error: patch fragment without header at handoff-mode.patch:12

The installer rehearses before it touches anything, so it failed safely and
changed nothing - but it failed on EVERY run, for everyone, and the owner's PC
could not be updated at all. One wrong integer blocked the whole update.

NO TEST COULD SEE IT, which is the real finding:

  * `test_apply_outcomes.py` (runs in CI) drives the installer against a
    stand-in repo holding TWO FAKE one-hunk patches. It proves how a run ENDS;
    it never reads the real list.
  * `test_handoff_mode.py` checks that the patch text MENTIONS the action and
    `jarvis_gate.py`. A string check cannot tell a patch that applies from one
    that does not.
  * Nothing anywhere parsed the 133 real patches.

So this file does the one cheap thing that would have caught it: it asks git to
parse each patch, and reports the patch and git's own words when one is
malformed. `--numstat` needs no target files and no clean tree - it reads the
patch and nothing else - so this runs anywhere, in about a second, with no
backend, no model and no owner's PC.

It is also the only check that the list and the folder agree. The installer
compares them at run time and calls a difference fatal; until now no test did,
so a patch could be named in `$PATCHES` without its file, or a file could be
dropped without its entry, and CI would stay green.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO  # noqa: E402

#: The staged tree puts the patches beside this file; a repo checkout keeps
#: them in backend/. Both are tried, so the suite runs either way.
PDIR = HERE / "backend" if (HERE / "backend").is_dir() else HERE

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, ok: bool, detail=None) -> None:
    if ok:
        PASSED.append(name)
        print(f"ok    {name}")
    else:
        FAILED.append(name)
        print(f"FAIL  {name}")
        if detail is not None:
            print(f"        {detail}")


def git_parse(path: Path) -> tuple[bool, str]:
    """True when git can read this patch. Returns git's own error when not."""
    p = subprocess.run(["git", "apply", "--numstat", str(path)],
                       cwd=str(REPO), capture_output=True, text=True)
    if p.returncode == 0:
        return True, p.stdout.strip()
    err = (p.stderr or p.stdout).strip()
    first = next((ln.strip() for ln in err.splitlines() if ln.strip()), err)
    return False, first


def listed_patches() -> list[str]:
    """The names in scripts/apply-patches.ps1's own $PATCHES array.

    ONLY WHOLE LINES COUNT. Many of the entries carry a comment above them
    naming OTHER patches ("... one block right after referee.patch"), and a
    loose search picks those up as entries - 189 matches for 133 entries.
    An entry is a line that is nothing but a quoted .patch name.
    """
    text = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    start = text.index("$PATCHES = @(")
    entry = re.compile(r"^\s*'([^']+\.patch)',?\s*$")
    names: list[str] = []
    for ln in text[start:].splitlines()[1:]:
        if re.match(r"^\s*\)\s*$", ln):
            break
        m = entry.match(ln)
        if m:
            names.append(m.group(1))
    return names


def on_disk() -> set[str]:
    """Every patch file the literal $PATCHES list could name."""
    return {p.name for p in PDIR.glob("*.patch")}


def rebuilt_halves() -> list[Path]:
    """backend/rebuilt-patches/*.patch.

    These are NOT in the literal $PATCHES list and should not be: the script
    swaps a superseded whole patch for its split half at run time
    (`$PATCHES = $swapped`). They are still patches git has to read, so they
    are parse-checked with the rest.
    """
    d = PDIR / "rebuilt-patches"
    return sorted(d.glob("*.patch")) if d.is_dir() else []


def t_the_list_and_the_folder_agree() -> None:
    names = listed_patches()
    check("$PATCHES was found and is a real list", len(names) >= 100, len(names))
    listed, disk = set(names), on_disk()
    check("every patch named in $PATCHES has a file", not (listed - disk),
          f"in the list, not on disk: {sorted(listed - disk)[:6]}")
    check("every patch file is named in $PATCHES", not (disk - listed),
          f"on disk, not in the list: {sorted(disk - listed)[:6]}")
    check("no patch is listed twice", len(names) == len(listed),
          f"{len(names)} names, {len(listed)} distinct")


def t_every_patch_parses() -> None:
    bad = []
    for name in listed_patches():
        path = PDIR / name
        if not path.is_file():
            continue  # the check above already reports it
        ok, detail = git_parse(path)
        if not ok:
            bad.append(f"{name}: {detail}")
    check("git can read every patch in $PATCHES", not bad,
          "; ".join(bad[:4]) if bad else None)

    halves = rebuilt_halves()
    check("the rebuilt halves are there to check", len(halves) >= 1, len(halves))
    bad_halves = []
    for path in halves:
        ok, detail = git_parse(path)
        if not ok:
            bad_halves.append(f"{path.name}: {detail}")
    check("git can read every rebuilt half too", not bad_halves,
          "; ".join(bad_halves[:4]) if bad_halves else None)


def t_the_check_is_sensitive_both_directions() -> None:
    """The control that makes the rest mean something.

    This reproduces handoff-mode.patch's exact defect, shrunk to two hunks: a
    first hunk whose header under-claims the original lines by one, with a
    second hunk following. Git reads the claimed lines, finds a leftover, and
    calls it a fragment rather than a hunk. The corrected version must pass,
    or this suite would be red on a healthy file.
    """
    body = (" a\n b\n+c\n d\n")
    good = ("--- a/x.py\n+++ b/x.py\n@@ -1,3 +1,4 @@\n" + body +
            "@@ -10,3 +11,4 @@\n e\n f\n+g\n h\n")
    bad = good.replace("@@ -1,3 +1,4 @@", "@@ -1,2 +1,3 @@")
    with tempfile.TemporaryDirectory() as tmp:
        g, b = Path(tmp) / "good.patch", Path(tmp) / "bad.patch"
        g.write_text(good, encoding="utf-8")
        b.write_text(bad, encoding="utf-8")
        ok_good, why_good = git_parse(g)
        ok_bad, why_bad = git_parse(b)
    check("CONTROL: a well-formed two-hunk patch is accepted", ok_good, why_good)
    check("CONTROL: a header one line short IS refused", not ok_bad, why_bad)
    check("CONTROL: and git names the reason, as it did on the real one",
          "fragment" in why_bad.lower(), why_bad)


def t_the_real_list_is_the_size_we_think() -> None:
    """A canary, not a rule: if the list shrinks a lot, something ate it."""
    n = len(listed_patches())
    check("the list still holds the whole stack (at least 100 patches)",
          n >= 100, n)


def main() -> int:
    for fn in (t_the_list_and_the_folder_agree,
               t_every_patch_parses,
               t_the_check_is_sensitive_both_directions,
               t_the_real_list_is_the_size_we_think):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
