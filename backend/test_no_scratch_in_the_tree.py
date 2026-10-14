"""test_no_scratch_in_the_tree.py - the scratch guard's own guard.

    python3 backend/test_no_scratch_in_the_tree.py

`tools/check_no_scratch_in_the_tree.py` says the agent's scratch folders
(`.dsh-scratch-tools/` and `scratchpad/`) must not be tracked. A guard that is
never itself guarded is how it would quietly stop guarding: this repository has
found the same failure three times (`.gitignore`'s own notes record `dshwork/`
and `.dsh-scratch/`, and five files under these two were tracked until
2026-10-14), and each time the answer was a rule rather than a habit. A rule
with nothing behind it is the habit again.

WHAT IT PROVES, WITHOUT TOUCHING THE REAL INDEX
  1. The checker exits 0 on the tree as it stands, and reports a number of
     checks - so "nothing is tracked" cannot be confused with "nothing was
     looked at".
  2. A tracked scratch path takes it RED, naming the path, for either folder.
     The answer `git ls-files` would give is injected rather than staged, so
     this suite cannot leave the checkout's index dirty for the suites that run
     after it (the required `backend` job runs them one after another in one
     checkout, and `tools/check_claims.py` now reads `git ls-files` too).
  3. The `.gitignore` rules are guarded as well, because untracking the files
     is only half of it: without the rule the next `git add -A` sweeps them
     back in, which is how all five arrived.
  4. No git repository is a SKIP that says so - never a silent pass, which is
     the shape this project has a whole checker for
     (`tools/check_vacuous_checks.py`).
"""
from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "tools"))

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def run_checker(tracked=None, repo=None):
    """(exit code, what it printed) for one run of the checker's own main().

    `tracked` replaces the answer `git ls-files` would give, and `repo`
    replaces the folder a `.gitignore` is read from. Both are put back
    whatever happens, so one case cannot leak into the next.
    """
    import check_no_scratch_in_the_tree as C
    saved_tracked, saved_repo = C.tracked, C.REPO
    if tracked is not None:
        C.tracked = tracked
    if repo is not None:
        C.REPO = repo
    printed = io.StringIO()
    try:
        with contextlib.redirect_stdout(printed):
            code = C.main()
    finally:
        C.tracked, C.REPO = saved_tracked, saved_repo
    return code, printed.getvalue()


def t_the_checker_is_green_on_this_tree():
    code, out = run_checker()
    check("the scratch check exits 0 on this tree", code == 0, out[-800:])
    check("... and says how many checks it made, so 'nothing is wrong' cannot "
          "be read as 'nothing was looked at'",
          " passed, " in out, out[-800:])


def t_a_tracked_scratch_file_takes_it_red():
    """The bite. Both folders, because a rule covering one of them is how this
    started: `.dsh-scratch/` was ignored and `.dsh-scratch-tools/` was not.
    """
    for folder, path in ((".dsh-scratch-tools/", ".dsh-scratch-tools/make_picture_card_patch.py"),
                         ("scratchpad/", "scratchpad/admem/budget_measure.py")):
        code, out = run_checker(tracked=lambda *patterns, p=path: [p])
        check(f"a tracked file under {folder} exits 1", code == 1, out[-800:])
        check(f"... and the message names it: {path}", path in out, out[-800:])


def t_the_gitignore_rules_are_guarded_too():
    with tempfile.TemporaryDirectory(prefix="no-scratch-") as tmp:
        (Path(tmp) / ".gitignore").write_text("# nothing ignored here\n",
                                              encoding="utf-8")
        code, out = run_checker(tracked=lambda *patterns: [], repo=Path(tmp))
        check("a .gitignore without the rules exits 1", code == 1, out[-800:])
        for folder in (".dsh-scratch-tools/", "scratchpad/"):
            check(f"... and says the rule for {folder} is gone",
                  folder in out and ".gitignore" in out, out[-800:])


def t_no_repository_is_a_stated_skip():
    code, out = run_checker(tracked=lambda *patterns: None)
    check("with no repository to ask, the check exits 0", code == 0, out[-800:])
    check("... and says out loud that it did NOT look, rather than passing "
          "quietly", "skip" in out, out[-800:])
    check("... and reports no check as passing",
          "passed" not in out, out[-800:])


if __name__ == "__main__":
    for fn in (t_the_checker_is_green_on_this_tree,
               t_a_tracked_scratch_file_takes_it_red,
               t_the_gitignore_rules_are_guarded_too,
               t_no_repository_is_a_stated_skip):
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
