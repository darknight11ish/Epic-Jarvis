"""test_vacuous_checks.py - the checker that catches a skip counted as a pass.

    python3 backend/test_vacuous_checks.py

WHY THIS SUITE IS IN `backend/` AND NOT UNDER `tools/`

`tools/check_vacuous_checks.py` has run in the `audit` job since the five
checkers were wired, and `audit` is INFORMATIONAL - a red one does not gate a
merge (CLAUDE.md). The rules it enforces are about the required `backend` job's
own honesty, so the rules have to be checked in the REQUIRED job. Every
`backend/test_*.py` is run there by `backend/run_suites.py`, which is why this
file is here: it is the required job's assertion that the checker exists, that
its new rule bites, and that the tree is clean today. `.github/workflows/ci.yml`
also runs the checker as its own fail-fast step in that job, so a reader of the
job's steps sees it without reading the sweep.

WHAT IT PROVES, IN THE ORDER IT MATTERS

  1. THE OLD SHAPE IS CAUGHT. `PASSED.append(name)` inside a local `skip()` is
     the exact line that made `backend/test_public_tunnel_refusal_order.py`
     print `2 passed, 0 failed` having read nothing (audit F-01) and
     `backend/test_origin_hud_header.py` do the same (F-03). The source below is
     built from the REAL pre-fix text of those two suites, reconstructed by
     substitution from the files as they are today - so the test fails the day
     the rule stops seeing the shape that was actually shipped.
  2. THE OTHER SHAPES OF THE SAME LIE ARE CAUGHT: `skip()` incrementing a
     counter (`passed += 1`), `skip()` extending the pass list, and `skip()`
     calling the suite's own `check(name, True)`.
  3. THE FIXED SUITES ARE CLEAN, and the whole tree is clean: the checker exits
     0 over every `backend/test_*.py` and `backend/eval_*.py`.
  4. THE CHECKER EXITS 1 ON A BAD SUITE - the end-to-end exit code, not just a
     finding in a list, because that is what CI reads.
  5. IT IS WIRED INTO THE REQUIRED JOB: `ci.yml`'s `backend` job runs both this
     suite (through the sweep) and the checker (as its own step).

WHAT A GREEN RUN MEANS, AND WHAT IT DOES NOT. It means no suite in this folder
counts a skip as a pass in a way the AST can see, and that the checker is in the
required job. It does not mean a suite's checks are any good; that is what each
suite's own assertions are for.
"""
from __future__ import annotations

import ast
import contextlib
import importlib.util
import io
import os
import re
import sys
import tempfile
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO  # noqa: E402

CHECKER = REPO / "tools" / "check_vacuous_checks.py"
CI = REPO / ".github" / "workflows" / "ci.yml"

FAILED, PASSED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (FAILED if not cond else PASSED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(name, why):
    """A check this machine cannot make. NOT a pass: counted in its own list."""
    SKIPPED.append(name)
    print(f"SKIP  {name}  (not a pass)\n        {why}")


def checker_module():
    """`tools/check_vacuous_checks.py` as a module, so its rules can be called
    one at a time instead of through its command line."""
    spec = importlib.util.spec_from_file_location("check_vacuous_checks", CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


#: The harness every suite in this folder writes, plus the OLD `skip()` - the
#: shape `backend/test_public_tunnel_refusal_order.py:58-60` and
#: `backend/test_origin_hud_header.py:62-64` shipped until 2026-10-27.
HARNESS = '''FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (FAILED if not cond else PASSED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}")


'''

OLD_SKIP = '''def skip(name, why):
    PASSED.append(name)
    print(f"SKIP  {name}")
'''

FIXED_SKIP = '''def skip(name, why):
    SKIPPED.append(name)
    print(f"SKIP  {name}  (not a pass)")
'''

COUNTER_SKIP = '''def skip(name, why):
    global passed
    passed += 1
'''

EXTEND_SKIP = '''def skip(name, why):
    PASSED.extend([name])
'''

VIA_CHECK_SKIP = '''def skip(name, why):
    check(name, True)
'''

#: `backend/test_public_tunnel_refusal_order.py` and
#: `backend/test_origin_hud_header.py`, the two suites the audit named. Read
#: here rather than pasted, so the test follows the files if they move.
FIXED_SUITES = ("test_public_tunnel_refusal_order.py", "test_origin_hud_header.py")


def _findings(module, source):
    return module.findings(ast.parse(source), "<self-test>")


def t_the_old_shape_is_caught():
    module = checker_module()
    problems, unreadable, _accepted = _findings(module, HARNESS + OLD_SKIP)
    check("the old `PASSED.append(name)` inside skip() is reported",
          len(problems) == 1, problems)
    check("...and the rule named is the skip-counted-as-a-pass one",
          bool(problems) and "skip()" in problems[0][2] and "PASS" in problems[0][2],
          problems)
    # The line is computed from the source, not guessed: a hard-coded number
    # here would be one more figure that silently drifts.
    wanted = (HARNESS + OLD_SKIP).splitlines().index("    PASSED.append(name)") + 1
    check("...and it is reported at the line the append is on",
          bool(problems) and problems[0][1] == wanted, (problems, wanted))
    check("nothing was unreadable about it", not unreadable, unreadable)


def t_the_other_shapes_are_caught():
    module = checker_module()
    for label, source in (("a counter (`passed += 1`)", COUNTER_SKIP),
                          ("`PASSED.extend([name])`", EXTEND_SKIP),
                          ("`check(name, True)` from skip()", VIA_CHECK_SKIP)):
        problems, _unreadable, _accepted = _findings(module, HARNESS + source)
        check(f"skip() that counts a pass by {label} is reported",
              len(problems) == 1, problems)


def t_the_fixed_shape_is_clean():
    module = checker_module()
    problems, unreadable, _accepted = _findings(module, HARNESS + FIXED_SKIP)
    check("a skip() that appends to SKIPPED is not reported", not problems, problems)
    check("...and the file is readable", not unreadable, unreadable)


def t_the_two_real_suites_are_clean_and_would_have_been_caught():
    """The suites the audit named: clean as they are, and CAUGHT as they were.

    The old text is rebuilt from the real file by substituting its own
    `SKIPPED.append(name)` line back to `PASSED.append(name)`, and only when
    that line really is there - so this test cannot pass by accident on a file
    that was rewritten in some other shape."""
    module = checker_module()
    for name in FIXED_SUITES:
        path = HERE / name
        if not path.is_file():
            skip(f"{name}: its skip() is not counted as a pass",
                 f"{path} is not here")
            continue
        text = path.read_text(encoding="utf-8")
        check(f"{name}: its own source has no finding", not _findings(module, text)[0],
              _findings(module, text)[0])
        check(f"{name}: its skip() appends to SKIPPED, which is the fixed shape",
              "SKIPPED.append(name)" in text, "SKIPPED.append(name) is not in it")
        old = text.replace("    SKIPPED.append(name)", "    PASSED.append(name)", 1)
        check(f"{name}: with that one line back, the checker reports it",
              len(_findings(module, old)[0]) == 1, _findings(module, old)[0])


def t_the_whole_tree_is_clean_and_the_checker_says_so():
    """The checker itself, over every suite: exit 0 and its own count line."""
    module = checker_module()
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = module.main()
    text = out.getvalue()
    check("the checker over the whole tree exits 0", code == 0, text[-800:])
    check("...and says how many suite files it read",
          re.search(r"\d+ suite file\(s\) read", text) is not None, text[-400:])
    check("...and says no skip() counts a pass",
          "no skip() counts a pass" in text, text[-400:])
    check("...and says how many check() calls it looked at",
          re.search(r"\d+ check\(\) call\(s\) looked at", text) is not None, text[-400:])


def t_the_checker_exits_1_on_a_bad_suite():
    """End to end: a folder with the old shape in it makes the checker exit 1.

    The exit code is what CI reads, and it is one step removed from the rule -
    a rule that reports a problem into a list nobody returns is still a green
    job. `BACKEND`/`REPO` are pointed at one temporary folder so this cannot
    depend on what the tree contains today."""
    module = checker_module()
    # A UNIQUE FOLDER MADE WITH A PLAIN mkdir, not `tempfile.mkdtemp`: on
    # Windows, `mkdtemp` creates its folder with mode 0o700, which Python turns
    # into an explicit DACL - and on a machine whose sandbox grants rights by
    # inheritance the folder is then unwritable by the process that just made it
    # (measured at this desk, 2026-10-27: `os.mkdir(d, 0o700)` then a write gives
    # PermissionError, `os.mkdir(d, 0o777)` works). A test that cannot create its
    # own fixture folder on a supported platform is a test that skips on that
    # platform, and this one is meant to run everywhere the required job does.
    folder = Path(tempfile.gettempdir()) / f"vacuous-check-{os.getpid()}-{time.time_ns()}"
    folder.mkdir(parents=False, exist_ok=False)
    try:
        (folder / "test_bad_skip.py").write_text(HARNESS + OLD_SKIP, encoding="utf-8")
        module.BACKEND = folder
        module.REPO = folder
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = module.main()
        text = out.getvalue()
        check("a suite that counts its skip as a pass makes the checker exit 1",
              code == 1, text[-600:])
        check("...and the finding names the file and the rule",
              "test_bad_skip.py" in text and "skip()" in text, text[-600:])
        (folder / "test_bad_skip.py").write_text(HARNESS + FIXED_SKIP, encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = module.main()
        check("...and the same file fixed makes it exit 0",
              code == 0, out.getvalue()[-600:])
    finally:
        import shutil
        shutil.rmtree(folder, ignore_errors=True)


def t_the_required_job_runs_it():
    """`ci.yml`: the checker and this suite reach the REQUIRED backend job.

    Nothing here re-reads YAML semantics; it asks for the two facts that make
    the check required rather than informational - the command inside the
    `backend` job's own block, and the audit job still running it too."""
    if not CI.is_file():
        return skip("the checker runs in the required backend job",
                    f"{CI} is not here")
    text = CI.read_text(encoding="utf-8")
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip() == "backend:"), None)
    if start is None:
        return check("the required backend job exists in ci.yml", False,
                     "no `backend:` job found")
    end = next((i for i in range(start + 1, len(lines))
                if re.match(r"^  [a-z0-9-]+:$", lines[i])), len(lines))
    job = "\n".join(lines[start:end])
    check("the required backend job runs tools/check_vacuous_checks.py",
          "tools/check_vacuous_checks.py" in job,
          "the command is not in the backend job's steps")
    check("...and the audit job still runs it too",
          text.count("tools/check_vacuous_checks.py") >= 2,
          text.count("tools/check_vacuous_checks.py"))
    check("...and this suite is a backend/test_*.py, so the sweep runs it here",
          (HERE / "test_vacuous_checks.py").is_file())


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if SKIPPED:
        print("skipped, and NOT passes: " + ", ".join(SKIPPED))
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
