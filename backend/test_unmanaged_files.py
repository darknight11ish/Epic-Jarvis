"""test_unmanaged_files.py - the bite, and the agreement, for the new checker.

    python3 backend/test_unmanaged_files.py

`tools/check_unmanaged_files.py` says every `.py` in the published base is
delivered to the owner's PC by a patch the installer applies, or by `$SHIPPED`,
or is recorded in its own `UNMANAGED` dict with the reason it is not. Nothing
was behind that rule until now, and this repository has found the same class
three times by audit rather than by a check: `apply-patches.ps1`'s own record of
the owner's folder (2026-10-11), `backend/test_shipped_modules.py`'s OWNER_ONLY
entry for `jarvis_style` ("not in backend/, so never shipped"), and the
installer measurement of 2026-10-14 that left a copy of the base missing
`jarvis_style.py` while restoring `jarvis_accounts.py`. A rule with nothing
behind it is the habit again.

WHAT IT PROVES
  1. The checker exits 0 on the tree as it stands and says how much it looked
     at, so "nothing is wrong" cannot be read as "nothing was examined".
  2. It prints its own verdict for `jarvis_style.py` - the file this tool was
     built for - whatever that verdict is. The founding case cannot drop out of
     its output without this suite noticing.
  3. Every file it reported as NEITHER is in its own `UNMANAGED` record, and
     every recorded name was reported: on a green run the two are the same set.
     A green run therefore cannot be green by having reported nothing.
  4. THE BITE. A `.py` file written into `jarvis-backend/` that no patch names
     and `$SHIPPED` does not list takes the checker RED - exit 1, naming the
     file - and deleting it makes the checker green again. That file is written
     into the real base folder, because that is the folder the checker
     classifies, and it is removed in a `finally`: the same run proves the tree
     is back where it started.
  5. It reads the REAL lists and not a copy of them: the tool's `$SHIPPED` is
     compared with `backend/test_shipped_modules.py`'s own parse of the script
     and with `_where.SHIPPED`, and its patch-header reading is compared with
     that suite's. Two parsers that must agree are checked against each other
     here rather than trusted.
"""
from __future__ import annotations

import os
import subprocess
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "tools"))
import _where                       # noqa: E402
import check_unmanaged_files as C   # noqa: E402
import test_shipped_modules as S    # noqa: E402

#: The stand-in written into the published base for the bite. Deliberately a
#: name no real module could have, and one written nowhere else: it is created
#: and deleted inside `t_an_undelivered_file_takes_it_red` alone.
BIT_PROOF = "zz_bite_proof_undelivered.py"

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def run_checker():
    """(exit code, what it printed) for one run of the checker, as its own process.

    A subprocess, not a call to `main()`: the exit code IS the guard, and CI
    reads it that way. `JARVIS_BACKEND` is dropped from the environment on
    purpose - the checker classifies the published base in this repository and
    has no business reading a real backend folder, and the standing rule for
    measuring anything about this repository is that the variable is unset.
    """
    env = dict(os.environ)
    env.pop("JARVIS_BACKEND", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    done = subprocess.run([sys.executable, "-B", str(Path(C.__file__))], cwd=REPO,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=env)
    return done.returncode, (done.stdout or "") + (done.stderr or "")


def reported_neither(out: str):
    """(the count on the checker's own NEITHER line, the names on it).

    Read back from the output rather than from the checker's dict: the point is
    what a reader is shown. The line is `<indent>NEITHER  <count>  <a>, <b>`,
    and a set of zero prints no names after the count - which is why the count
    is returned as well as the names. An empty set is a legitimate end state
    (every one of these files promoted by the owner, one at a time), and it
    must not read as "the checker printed nothing".
    """
    for line in out.splitlines():
        parts = line.split(None, 2)
        if parts and parts[0] == "NEITHER":
            names = [n.strip() for n in parts[2].split(",")] if len(parts) > 2 else []
            return int(parts[1]), [n for n in names if n]
    return None, []


def t_the_checker_is_green_and_says_what_it_looked_at():
    code, out = run_checker()
    check("the unmanaged-file check exits 0 on this tree", code == 0, out[-1200:])
    check("... and says how many .py files in the published base it classified, so "
          "'nothing is wrong' cannot be read as 'nothing was examined'",
          "classified one by one" in out and " passed, " in out, out[-1200:])
    check(f"... and prints its own verdict for {C.FOUNDING_CASE}, the file this "
          f"tool was built for", f"{C.FOUNDING_CASE} -> " in out, out[-1200:])
    check(f"... and that verdict names the bucket, not just the file",
          any(f"{C.FOUNDING_CASE} -> {b}" in out
              for b in ("patched", "shipped", "both", "NEITHER", "not in")),
          out[-1200:])


def t_the_reported_set_is_the_recorded_set():
    """On a green run these are one set, and that is the whole claim.

    NEITHER is what the checker FOUND; `UNMANAGED` is what it was TOLD to
    expect. Equality in both directions is what makes a green run mean "every
    undelivered file is known and reasoned about" rather than "nothing was
    undelivered today, or nothing was looked at".
    """
    code, out = run_checker()
    count, names = reported_neither(out)
    check("the checker's NEITHER line was found and read", count is not None, out[-1200:])
    check("every file reported as NEITHER is recorded in the checker's UNMANAGED dict",
          set(names) <= set(C.UNMANAGED),
          f"reported: {sorted(names)}; recorded: {sorted(C.UNMANAGED)}")
    check("... and every recorded name was reported, so the record has no stale entry",
          set(names) >= set(C.UNMANAGED),
          f"recorded but not reported: {sorted(set(C.UNMANAGED) - set(names))}")
    check("every recorded name is a real file in the published base",
          all((C.BASE / n).is_file() for n in C.UNMANAGED),
          f"not in {C.BASE}: "
          f"{[n for n in C.UNMANAGED if not (C.BASE / n).is_file()]}")
    check("the line's own count, the names on it and the recorded set all agree",
          count is not None and count == len(names) == len(C.UNMANAGED),
          f"count {count}, names {names}, recorded {sorted(C.UNMANAGED)}")
    check("... and the run that produced them was green", code == 0, out[-1200:])
    check("a NEITHER line with no names on it reads as a count of zero, not as a line "
          "that is missing", reported_neither("    NEITHER    0") == (0, []),
          f"{reported_neither('    NEITHER    0')!r}")


def t_an_undelivered_file_takes_it_red():
    """The bite, in the folder the checker actually classifies.

    `jarvis-backend/` is deliberately the real folder rather than a copy: the
    bug this tool is for is a file sitting there, and a test against a copy
    would prove the copy is watched. The file is removed in a `finally`, and the
    last three checks are the proof that it was - a base left holding it would
    fail `backend/test_base_matches_repo.py` in the same job.
    """
    victim = C.BASE / BIT_PROOF
    victim.unlink(missing_ok=True)
    before, before_out = run_checker()
    check("the check is green before the file is added", before == 0, before_out[-800:])

    try:
        victim.write_text("# a .py file in the published base that nothing delivers\n",
                          encoding="utf-8")
        code, out = run_checker()
        check(f"a .py file in jarvis-backend/ that no patch names and $SHIPPED does "
              f"not list exits 1", code == 1, out[-1500:])
        check(f"... and the message names it: {BIT_PROOF}", BIT_PROOF in out, out[-1500:])
        check("... and it is the only failure, so the bite is this file and not "
              "something else that was already wrong",
              "1 failed" in out, out[-1500:])
    finally:
        victim.unlink(missing_ok=True)

    after, after_out = run_checker()
    check("with the file deleted the check exits 0 again", after == 0, after_out[-800:])
    check(f"... and {BIT_PROOF} is gone from what it printed",
          BIT_PROOF not in after_out, after_out[-800:])
    check(f"... and the published base is back where it started, with no {BIT_PROOF} "
          f"left in it", not victim.exists())


def t_the_tool_reads_the_real_lists():
    """The tool's four facts, against the suites that own them.

    `$SHIPPED` is parsed from `scripts/apply-patches.ps1` by this tool and by
    `backend/test_shipped_modules.py`; `_where.SHIPPED` is the list the suites
    run against, and that suite asserts the script's block and `_where.py` are
    one list. If the tool's parse ever stopped matching either, every bucket it
    prints would be built on a different question from the one the repository
    asks - the failure mode this whole file exists to make impossible.
    """
    tool_shipped = list(C.ps1_list("SHIPPED"))
    check("the tool's $SHIPPED is the script's own list, as "
          "backend/test_shipped_modules.py reads it",
          tool_shipped == list(S.SHIPPED),
          f"the tool read {len(tool_shipped)}, the suite {len(S.SHIPPED)}")
    check("... and that is _where.SHIPPED, which every suite runs against",
          tool_shipped == list(_where.SHIPPED),
          f"only in the tool: {sorted(set(tool_shipped) - set(_where.SHIPPED))}; "
          f"only in _where.py: {sorted(set(_where.SHIPPED) - set(tool_shipped))}")

    targets = set()
    for path in sorted(C.PATCH_DIR.glob("*.patch")):
        targets |= C.patch_targets(path)
    suite_targets = set()
    for path in sorted(HERE.glob("*.patch")):
        suite_targets |= S.patch_targets(path)
    suite_targets = {t.rsplit("/", 1)[-1] for t in suite_targets}
    check("the tool's patch-header reading is the same as "
          "backend/test_shipped_modules.py's own",
          targets == suite_targets,
          f"only the tool: {sorted(targets - suite_targets)}; "
          f"only the suite: {sorted(suite_targets - targets)}")

    names = C.ps1_list("PATCHES")
    superseded = C.ps1_superseded()
    applied, left_out = C.installed_patches(names, superseded)
    check("the installer's own patch list and supersede table were read from the "
          "script, not copied here", len(names) > 100 and bool(superseded),
          f"{len(names)} patches, {len(superseded)} superseded")
    check("every superseded patch is either applied as its rebuilt half or left out "
          "whole - never dropped without being named",
          len(applied) + len(left_out) == len(names),
          f"{len(applied)} applied + {len(left_out)} left out != {len(names)}")
    check("... and which of the two it is comes from the half on disk",
          all(n in left_out for n in superseded if not (C.HALF_DIR / n).is_file())
          and all(n not in left_out for n in superseded if (C.HALF_DIR / n).is_file()),
          f"left out whole: {left_out}")


if __name__ == "__main__":
    for fn in (t_the_checker_is_green_and_says_what_it_looked_at,
               t_the_reported_set_is_the_recorded_set,
               t_an_undelivered_file_takes_it_red,
               t_the_tool_reads_the_real_lists):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
