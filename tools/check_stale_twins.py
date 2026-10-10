#!/usr/bin/env python3
"""Name the twins under `jarvis-backend/` that no longer match `backend/`, in seconds.

    py -3 tools/check_stale_twins.py
    py -3 tools/check_stale_twins.py --root <a checkout>

WHY THIS EXISTS

`backend/test_base_matches_repo.py` requires the modules this repository ships
whole to have a byte-identical twin under `jarvis-backend/`, line endings
ignored - 181 pairs on 2026-10-10: the 180 `SHIPPED` entries, every module in
`backend/rebuilt/`, and its `jarvis-framework.toml`. That suite is the
authority on WHICH files those are and on when two
files count as the same, and it is right to be - but it reports in CI's
`backend` job, which starts only after the `frontend` job has taken its time.
Measured on 2026-10-10: three pull requests failed CI for this one reason
(#167 with two stale twins, #173 with one, #175 with one), and because the
claims register's row D06 takes its evidence from
`test:backend/test_base_matches_repo.py`, each failure also turned
`backend/test_claims.py` and the `audit` job red behind it. A one-file omission
therefore looked like a systemic failure and cost a full CI round trip to find.

This tool is the same question asked locally, in about a second, before a push:
which files drifted, with both byte sizes so the message is actionable.

WHAT IT REUSES, SO IT CANNOT DISAGREE BY ACCIDENT

It does not re-state the rule. It loads the rule's own code from the checkout it
is checking:

  * `backend/test_base_matches_repo.py`'s `shipped_pairs()` - WHICH files must
    match. That reads `backend/_where.py`'s SHIPPED list plus every module in
    `backend/rebuilt/`, plus `backend/rebuilt/jarvis-framework.toml`, so a
    module added to SHIPPED is checked here with no edit to this file.
  * the same file's `same_text()` - WHEN two files count as the same. It is
    `_where._same_text()`'s rule: `.gitattributes` is `eol=lf`, a Windows clone
    may hold CRLF, so line endings do not count.

`backend/test_base_matches_repo.py`'s own
`t_the_stale_twin_check_agrees_with_the_rule` holds the agreement: it builds a
deliberately perturbed copy of the two folders and fails unless this tool names
exactly the files the rule names - and it fails too if this tool is absent, or
reports nothing, or goes red on a difference that is only line endings.

WHAT IT DELIBERATELY DOES NOT DO

It is not a second opinion and not a substitute for the suite. It checks only
the shipped-twin half of `test_base_matches_repo.py`; that suite also checks
that the base's own imports close, that the non-Python files its code reads are
beside it, and that no private or generated file was swept in. Green here means
"the twins match", never "the `backend` job will pass".

WHICH SIDE IS NEWER IS NOT KNOWABLE FROM HERE, so nothing here claims it.
`apply-patches.ps1` step 3 copies `backend/<name>` over the base, and a
`backend/` copy that is ahead looks exactly like a `jarvis-backend/` copy that
is ahead. A red run means: read both files (the sizes are printed), decide,
copy the right one over the other, and run this again.

Exit code: 0 when every twin matches, 1 otherwise. A twin missing from
`jarvis-backend/` is red too - the suite fails for that as well.
"""
from __future__ import annotations

import sys
from pathlib import Path

#: Where this checkout is. `--root` overrides it, which is how the suite in
#: `backend/` points this tool at a perturbed copy it made in a temp folder.
REPO = Path(__file__).resolve().parent.parent

#: The prefixes the suite's own failure line uses, kept so a reader of either
#: one sees the same words.
DIFFERS = "stale twin: "
MISSING = "missing twin: "

#: What a person should do about a red run. `shipped_pairs()` maps a
#: `rebuilt/x.py` entry onto the base as a bare `x.py`, so the repository side
#: of a pair can be `backend/` or `backend/rebuilt/` - the line says which.
FIX = ("copy the repository's copy over jarvis-backend/ "
       "(a rebuilt/ module lands as its bare name), then run this again")


def load_rule(root: Path):
    """The rule itself, read from `root` rather than re-stated here.

    Both modules are removed from `sys.modules` first and loaded from `root`, so
    checking a copy cannot silently use the paths of the checkout this file
    lives in: `backend/_where.py` computes `REPO` from its own location, and
    `test_base_matches_repo.py` binds `BACKEND`/`BASE` from that at import.

    Raises `RuleUnreadable` when either file is not there or will not import -
    a check that cannot read its rule must say so, never pass.
    """
    backend = root / "backend"
    for name in ("_where", "test_base_matches_repo"):
        sys.modules.pop(name, None)
    sys.path.insert(0, str(backend))
    try:
        import test_base_matches_repo as rule           # noqa: PLC0415
    except Exception as err:                            # noqa: BLE001
        raise RuleUnreadable(
            f"{backend / 'test_base_matches_repo.py'} could not be read as the "
            f"rule ({type(err).__name__}: {err}). This check reuses that "
            f"suite's own rule; it will not guess at one.") from err
    finally:
        sys.path.remove(str(backend))
        for name in ("_where", "test_base_matches_repo"):
            sys.modules.pop(name, None)
    return rule


class RuleUnreadable(Exception):
    """The rule could not be read, so nothing was checked."""


def drifted(rule) -> tuple[list[tuple[str, Path, Path, int, int]], list[str]]:
    """(twins whose text differs, twins with no copy in the base).

    Every judgement here is the rule's: the pair list is `rule.shipped_pairs()`
    and sameness is `rule.same_text()`. The only thing this function adds is
    the reporting - a leaf name and both byte sizes instead of one long string.
    """
    differs: list[tuple[str, Path, Path, int, int]] = []
    missing: list[str] = []
    for leaf, ours in rule.shipped_pairs():
        theirs = rule.BASE / leaf
        if not theirs.is_file() or not ours.is_file():
            missing.append(leaf)
            continue
        if not rule.same_text(theirs, ours):
            differs.append((leaf, theirs, ours,
                            theirs.stat().st_size, ours.stat().st_size))
    return differs, missing


def _rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:                                  # pragma: no cover
        return path.as_posix()


def main() -> int:
    args = sys.argv[1:]
    root = REPO
    if "--root" in args:
        at = args.index("--root")
        if at + 1 >= len(args):
            print("--root needs the checkout to check, e.g. --root C:\\tmp\\copy")
            return 1
        root = Path(args[at + 1]).resolve()

    try:
        rule = load_rule(root)
    except RuleUnreadable as err:
        print(f"::error::{err}")
        return 1

    pairs = rule.shipped_pairs()
    differs, missing = drifted(rule)

    for leaf, theirs, ours, their_size, our_size in differs:
        print(f"{DIFFERS}{leaf}  {_rel(theirs, root)} {their_size} B, "
              f"{_rel(ours, root)} {our_size} B")
    for leaf in missing:
        print(f"{MISSING}{leaf}  no copy on one side (the suite fails for this "
              f"too)")

    if differs or missing:
        names = ", ".join([leaf for leaf, *_ in differs] + missing)
        print(f"{len(differs) + len(missing)} stale twin(s) under "
              f"{_rel(rule.BASE, root)}/: {names} - {FIX}")
        print("Which side is newer is not knowable from here: read both files "
              "(above) and decide. `py -3 tools/check_stale_twins.py` exits 0 "
              "when they match again.")
        return 1

    print(f"{_rel(rule.BASE, root)}/ is this repository's copy: all "
          f"{len(pairs)} modules this repository ships whole match, line "
          f"endings ignored ({len(rule._where.SHIPPED)} SHIPPED entries plus "
          f"backend/rebuilt/).")
    print("This is the shipped-twin half of backend/test_base_matches_repo.py "
          "only; that suite also checks the base's imports, the files beside "
          "its code and that nothing private was swept in.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
