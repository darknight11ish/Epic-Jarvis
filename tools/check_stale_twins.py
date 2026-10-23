#!/usr/bin/env python3
"""Name the twins under `jarvis-backend/` that no longer match their source, in seconds.

    py -3 tools/check_stale_twins.py
    py -3 tools/check_stale_twins.py --root <a checkout>

WHY THIS EXISTS

`backend/test_base_matches_repo.py` requires every file the base is re-taken
from to have a copy under `jarvis-backend/` holding the same text, line endings
ignored - 191 modules on 2026-10-13 (the `SHIPPED` entries, every module in
`backend/rebuilt/`, and its `jarvis-framework.toml`), plus the BESIDE-files
`tools/gen_base_from_backend.py` re-takes from this repository that the modules
do not already cover (`requirements.lock`, `quiz_grader_cases.json`,
`rust-crates.lock`). That suite is the authority on WHICH files those are and on
when two files count as the same, and it is right to be - but it reports in
CI's `backend` job, which starts only after the `frontend` job has taken its
time. Measured on 2026-10-10: three pull requests failed CI for this one reason
(#167 with two stale twins, #173 with one, #175 with one), and because the
claims register's row D06 takes its evidence from
`test:backend/test_base_matches_repo.py`, each failure also turned
`backend/test_claims.py` and the `audit` job red behind it. A one-file omission
therefore looked like a systemic failure and cost a full CI round trip to find.

This tool is the same question asked locally, in about a second, before a push:
which files drifted, with both byte sizes so the message is actionable.

THE GAP IT HAD, AND WHAT IT COST (2026-10-13)

It used to check the modules only, and the beside-files were not modules. PR #390
added `rapidocr` to `backend/requirements.lock` and left
`jarvis-backend/requirements.lock` alone; this tool reported "all 191 shipped
modules match" and CI went red on two jobs at once - `backend` and `audit` - on
`FAIL ... these differ (or are absent): requirements.lock`, a line
`backend/test_base_regeneration.py` prints. A green local run and a red CI run,
over one file, was the whole of the failure. It now compares every file the
re-take rule keeps equal, so that cannot happen again silently.

THE SECOND GAP IT HAD (2026-10-23), IN THE OVERLAP OF THE TWO LISTS

Two files are named in both the SHIPPED list and the BESIDE table, and they are
not the same shape: `jarvis-framework.toml` is the same path in both lists, but
`jarvis_hud.html` is `backend/jarvis_hud.html` in SHIPPED and
`jarvis-desktop/src/jarvis_hud.html` in BESIDE - three copies in all once the
base's own is counted. `twin_pairs()` used to keep only the first pair it saw
for a leaf, which is the SHIPPED one, so this tool compared
`backend/jarvis_hud.html` with the base and never looked at the desktop page the
base is re-taken FROM. A desktop page that drifted stayed green here and only
went red in CI's `backend` job. The rule now keeps a leaf from two different
sources as two pairs, and this tool compares EVERY repository copy of every
leaf against the base - so all three copies of the page are covered.

WHAT IT REUSES, SO IT CANNOT DISAGREE BY ACCIDENT

It does not re-state the rule. It loads the rule's own code from the checkout it
is checking:

  * `backend/test_base_matches_repo.py`'s `twin_pairs()` - WHICH files must
    match, which is `shipped_pairs()` (that reads `backend/_where.py`'s SHIPPED
    list plus every module in `backend/rebuilt/`, plus
    `backend/rebuilt/jarvis-framework.toml`) plus `beside_pairs()` (that reads
    the BESIDE table out of `tools/gen_base_from_backend.py`, the re-take rule
    itself). So a module added to SHIPPED, or a beside-file added to that table,
    is checked here with no edit to this file.
  * the same file's `same_text()` - WHEN two files count as the same. It is
    `_where._same_text()`'s rule: `.gitattributes` is `eol=lf`, a Windows clone
    may hold CRLF, so line endings do not count.

`backend/test_base_matches_repo.py`'s own
`t_the_stale_twin_check_agrees_with_the_rule` holds the agreement: it builds a
deliberately perturbed copy of the two folders - one shipped module drifted, one
beside-file drifted at a time, and one desktop-only drift of the overlapped
`jarvis_hud.html` - and fails unless this tool names exactly the files the rule
names. It fails too if this tool is absent, or reports nothing, or goes red on a
difference that is only line endings.

WHAT IT DELIBERATELY DOES NOT DO

It is not a second opinion and not a substitute for the suite. It checks the
files the base must hold verbatim; `test_base_matches_repo.py` also checks that
the base's own imports close and that no private or generated file was swept in,
and `backend/test_base_regeneration.py` checks the one file that is NOT compared
this way - `jarvis-backend/_where.py`, which is DERIVED as
`backend/_where.py` plus `BASE_WHERE_TRAILER`, so it differs by design and is
compared by its own rule there, never by `same_text()`. It also cannot see
`jarvis-visual-spec.json`, which is re-taken from the owner's live backend
folder: there is no copy of it in this repository to compare against, in CI or
anywhere else. Green here means "the files the base holds verbatim match",
never "the `backend` job will pass".

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

#: What a person should do about a red run. `twin_pairs()` maps a
#: `rebuilt/x.py` entry onto the base as a bare `x.py`, and a beside-file onto
#: the base as its own name, so the repository side of a pair can be `backend/`,
#: `backend/rebuilt/`, `jarvis-desktop/src/` or `jarvis-desktop/src-tauri/` -
#: the line says which.
FIX = ("copy the repository's copy over jarvis-backend/ "
       "(a rebuilt/ module lands as its bare name), then run this again")

#: The two files the re-take rule keeps equal that this tool cannot compare with
#: `same_text()`, and where each IS checked. Printed on a green run, so a green
#: run never reads as more coverage than it is.
NOT_COMPARED = (
    ("_where.py",
     "the base's copy is DERIVED - backend/_where.py plus BASE_WHERE_TRAILER - so it "
     "differs by design; backend/test_base_regeneration.py compares it with that rule"),
    ("jarvis-visual-spec.json",
     "re-taken from the owner's live backend folder, and there is no copy of it in "
     "this repository to compare against"),
)


def load_rule(root: Path):
    """The rule itself, read from `root` rather than re-stated here.

    Both modules are removed from `sys.modules` first and loaded from `root`, so
    checking a copy cannot silently use the paths of the checkout this file
    lives in: `backend/_where.py` computes `REPO` from its own location, and
    `test_base_matches_repo.py` binds `BACKEND`/`BASE` from that at import.

    Raises `RuleUnreadable` when either file is not there or will not import -
    a check that cannot read its rule must say so, never pass. It is raised for
    a rule that has no `twin_pairs()` too: that is a checkout from before
    2026-10-13, whose rule cannot answer the beside-file half of the question,
    and checking less than the reader believes is the failure this tool exists
    to stop.
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
    if not callable(getattr(rule, "twin_pairs", None)):
        raise RuleUnreadable(
            f"{backend / 'test_base_matches_repo.py'} has no twin_pairs(), so it "
            f"cannot say which beside-files the base must hold. This is a "
            f"checkout from before 2026-10-13, when the rule covered the shipped "
            f"modules only - and `requirements.lock` went stale under exactly "
            f"that gap (PR #390). Update the checkout this --root points at.")
    return rule


class RuleUnreadable(Exception):
    """The rule could not be read, so nothing was checked."""


def copies_by_leaf(rule) -> dict:
    """Every repository copy the rule names for each file in the base.

    `rule.twin_pairs()` is the rule's list of (leaf in the base, this
    repository's copy) pairs, in its own order. Since 2026-10-23 it keeps the
    same leaf from two different sources when two lists name it - `jarvis_hud.html`
    is both a SHIPPED module and a BESIDE file - which is exactly the overlap
    this tool used to drop. Grouping by leaf is how the report can print WHICH
    copy drifted; a dict keeps the rule's order, and a path named twice by the
    rule is compared once.
    """
    groups: dict[str, list[Path]] = {}
    for leaf, ours in rule.twin_pairs():
        sources = groups.setdefault(leaf, [])
        if ours not in sources:
            sources.append(ours)
    return groups


def drifted(rule) -> tuple[list[tuple[str, Path, Path, int, int]], list[str]]:
    """(copies whose text differs, twins with no copy on one side).

    Every judgement here is the rule's: which files are twins and when two
    files count as the same text. The only thing this function adds is the
    reporting - a leaf name and both byte sizes instead of one long string.

    EVERY repository copy of a leaf is compared against the base, not just the
    one pair `twin_pairs()` happens to name first: `jarvis_hud.html` is named
    by both the SHIPPED list and the BESIDE table, and a desktop page that
    drifted while `backend/` and the base still agreed stayed green here until
    2026-10-23. One drifted copy is enough for a red run.
    """
    differs: list[tuple[str, Path, Path, int, int]] = []
    missing: list[str] = []
    for leaf, sources in copies_by_leaf(rule).items():
        theirs = rule.BASE / leaf
        for ours in sources:
            if not theirs.is_file() or not ours.is_file():
                if leaf not in missing:
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

    groups = copies_by_leaf(rule)
    differs, missing = drifted(rule)

    for leaf, theirs, ours, their_size, our_size in differs:
        print(f"{DIFFERS}{leaf}  {_rel(theirs, root)} {their_size} B, "
              f"{_rel(ours, root)} {our_size} B")
    for leaf in missing:
        print(f"{MISSING}{leaf}  no copy on one side (the suite fails for this "
              f"too)")

    if differs or missing:
        names = sorted({leaf for leaf, *_ in differs} | set(missing))
        print(f"{len(differs) + len(missing)} stale twin copy(ies) under "
              f"{_rel(rule.BASE, root)}/: {', '.join(names)} - {FIX}")
        print("Which side is newer is not knowable from here: read both files "
              "(above) and decide. `py -3 tools/check_stale_twins.py` exits 0 "
              "when they match again.")
        return 1

    shipped_leaves = {leaf for leaf, _ours in rule.shipped_pairs()}
    extra = [leaf for leaf, _ours in rule.beside_pairs() if leaf not in shipped_leaves]
    copies = sum(len(sources) for sources in groups.values())
    print(f"{_rel(rule.BASE, root)}/ is this repository's copy: all "
          f"{len(groups)} files the base is re-taken from match ({copies} "
          f"repository copies, every one compared), line endings ignored.")
    print(f"     {len(shipped_leaves)} modules this repository ships whole"
          + (f", plus {len(extra)} file(s) it owns beside them: "
             f"{', '.join(extra)}." if extra else "."))
    multi = sorted(leaf for leaf, sources in groups.items() if len(sources) > 1)
    if multi:
        print(f"     Every copy of a file named by two lists is compared too: "
              f"{', '.join(multi)}.")
    print("This is the verbatim-copy half of backend/test_base_matches_repo.py "
          "only; that suite also checks the base's imports and that nothing "
          "private was swept in.")
    for name, why in NOT_COMPARED:
        print(f"Not compared here, on purpose: {name} - {why}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
