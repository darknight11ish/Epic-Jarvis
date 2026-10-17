"""test_stale_area.py - the audit-coverage checker tells the truth from anywhere.

`tools/check_stale_area.py` is wired into CI's `audit` job as a step that
**exits 0 while it has debt** - that is deliberate, and the reason is written
beside the step. The consequence is that a broken checker would be quiet: an
informational step that always succeeds is indistinguishable from one that
works, unless something checks the checker.

**This suite exists because that already happened once.** PR #486's first run
failed its own `audit` job with:

    stale-area: the area map could not be read: [Errno 2] No such file or
    directory: '.../jarvis-desktop/src-tauri/tools/stale-areas.tsv'

The step runs from `jarvis-desktop/src-tauri` (its own `python3 ../../tools/...`
says so), and `--root` defaulted to the **working directory**, so the tool went
looking for its map inside a Rust source folder. A checker whose answer depends
on where it was invoked reports on the wrong thing - the same class of defect as
a test that silently skips.

So the first two checks below are the regression: the tool must answer the same
from the repository root and from the subdirectory CI actually uses. The rest
prove it still bites, so this suite cannot pass by the tool having gone quiet.

No pytest, no network. Exit 0 = every check passed.
"""
import subprocess
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
TOOL = REPO / "tools" / "check_stale_area.py"
MAP = REPO / "tools" / "stale-areas.tsv"

PASSED, FAILED = [], []


def check(what: str, ok: bool, detail: str = "") -> None:
    (PASSED if ok else FAILED).append(what)
    print(("ok    " if ok else "FAIL  ") + what + (f"\n      says: {detail}" if detail and not ok else ""))


def run(args, cwd):
    """The tool, from `cwd`. Returns (exit code, combined output)."""
    done = subprocess.run([sys.executable, "-B", str(TOOL), *args],
                          cwd=str(cwd), capture_output=True, text=True, timeout=300)
    return done.returncode, (done.stdout or "") + (done.stderr or "")


# --------------------------------------------------------------------------
# The regression: where it is run from must not change the answer.
# --------------------------------------------------------------------------

def t_it_reads_its_map_from_the_checkout_it_lives_in():
    root_code, root_out = run(["--all"], REPO)
    sub = REPO / "jarvis-desktop" / "src-tauri"
    if not sub.is_dir():
        check("the checkout has the subdirectory CI runs the step from", False,
              f"{sub} is not a directory, so this regression cannot be checked")
        return
    sub_code, sub_out = run(["--all"], sub)

    check("from the repository root, the map is found", root_code == 0,
          f"exit {root_code}: {root_out.strip()[-400:]}")
    check("from the subdirectory the CI step uses, the map is found",
          sub_code == 0, f"exit {sub_code}: {sub_out.strip()[-400:]}")
    # The summary line is the answer; it must not depend on the cwd either.
    def summary(out: str) -> str:
        for line in out.splitlines():
            if "have moved since they were last audited" in line:
                return line.strip()
        return ""
    check("both runs give the same answer, not merely both zero",
          summary(root_out) == summary(sub_out) and summary(root_out) != "",
          f"root={summary(root_out)!r} sub={summary(sub_out)!r}")


def t_it_says_where_the_map_it_read_is():
    """A run that cannot find its map must say so, not answer about nothing."""
    code, out = run(["--all", "--root", str(REPO / "docs")], REPO)
    check("a root with no map is an error, not a clean report", code != 0,
          f"exit {code} with: {out.strip()[-400:]}")
    check("and the error names the map file it could not read",
          "stale-areas.tsv" in out, out.strip()[-400:])


# --------------------------------------------------------------------------
# It still bites. An informational step that cannot fail is a document.
# --------------------------------------------------------------------------

def t_a_map_that_cannot_be_read_fails_in_both_modes():
    """CI's shape (no --check) must STILL fail when the tool itself is broken."""
    code_ci, _ = run(["--all", "--map", "tools/no-such-map.tsv"], REPO)
    code_desk, _ = run(["--all", "--check", "--map", "tools/no-such-map.tsv"], REPO)
    check("a missing map fails the CI shape too - debt never fails, a broken "
          "tool does", code_ci != 0, f"exit {code_ci}")
    check("a missing map fails the desk shape", code_desk != 0, f"exit {code_desk}")


def t_an_empty_range_is_not_a_pass():
    """Nothing to check is not the same as nothing wrong.

    **`--since HEAD` is not decoration - it is the fix for a real CI failure.**
    This used to run a bare `--check` and assert `exit in (1, 2)`, on the
    comment "HEAD == origin/main in CI". That is true of a plain checkout and
    **false of the checkout GitHub builds a pull request in**, where HEAD is the
    merge ref: the range is not empty, the tool finds no debt in it, exits 0, and
    this check failed the required `backend` job on two unrelated pull requests
    (#491 and #493, 2026-10-16). A test whose answer depends on where it is run
    is the same defect as a checker whose answer does - so the range is now made
    empty on purpose and the tool is asked about that, wherever it runs.
    """
    code, out = run(["--check", "--since", "HEAD"], REPO)   # HEAD..HEAD, always
    check("--check on an empty range is not a vacuous pass", code == 2,
          f"exit {code}: {out.strip()[-300:]}")
    check("and it says so in words rather than printing nothing",
          "empty" in out.lower() or "nothing" in out.lower(), out.strip()[-300:])


def t_the_map_is_real_and_each_row_can_be_read():
    if not MAP.is_file():
        check("the area map is in the tree", False, f"{MAP} is absent")
        return
    rows = [ln for ln in MAP.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]
    check("the area map has rows", len(rows) > 0, f"{len(rows)} rows")
    check("every row has the same number of fields",
          len({r.count("\t") for r in rows}) == 1,
          f"field counts: {sorted({r.count(chr(9)) for r in rows})}")


TESTS = (
    t_it_reads_its_map_from_the_checkout_it_lives_in,
    t_it_says_where_the_map_it_read_is,
    t_a_map_that_cannot_be_read_fails_in_both_modes,
    t_an_empty_range_is_not_a_pass,
    t_the_map_is_real_and_each_row_can_be_read,
)


def main() -> int:
    for fn in TESTS:
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
