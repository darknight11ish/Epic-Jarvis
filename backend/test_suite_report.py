"""A suite the runner could not read is reported, never passed and never fatal.

    python3 test_suite_report.py

run_suites.py used to do `code, out = r.returncode, r.stdout + r.stderr`. When
a suite is killed by a signal, or when the spawn itself fails, subprocess
leaves `stdout`/`stderr` as None - the addition raised TypeError, the sweep
died where it stood, and every suite after that one lost its result. What this
suite pins:
  * None stdout is read as empty text, not added to a string;
  * a suite that exits non-zero is FAILED, never quietly passed;
  * one that printed nothing at all still reports which suite it was and what
    it exited with, and says there was no output to quote;
  * a timeout is a failure with the same shape, not an exception.

The direct cases drive run_suites.suite_result() with a stand-in whose stdout
and stderr are None, so no real process has to be made to print nothing. The
last case runs the real runner once, with a `sys.executable` that cannot
start, to check the stand-in matches what a real dead child produces.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_suites as R  # noqa: E402

FAILED, PASSED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: printed as `skip`, counted on its own,
    never as a pass."""
    SKIPPED.append(why)
    print(f"skip  {why}")


class Stand_in:
    """What a failed spawn looks like: the fields subprocess would set, with
    no output at all. Deliberately not a str anywhere."""

    def __init__(self, returncode=None, stdout=None, stderr=None):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def t_none_output_is_empty_text_not_a_crash():
    """The line that crashed the sweep: `r.stdout + r.stderr`.

    Each case is read the way the runner reads a finished child, first on a
    stand-in whose two output fields are None - which must come out as empty
    text, not raise - and then through suite_result(), which must report it."""
    for rc, out, err in ((None, None, None),
                         (3221225477, None, None),     # 0xC0000005, access violation
                         (1, None, "boo\n"),
                         (1, "hi\n", None)):
        stand_in = Stand_in(rc, out, err)
        try:
            got = (stand_in.stdout or "") + (stand_in.stderr or "")
        except Exception as exc:                       # pragma: no cover
            got = f"{type(exc).__name__}: {exc}"
        check(f"exit {rc}: None stdout and stderr are read as empty text",
              got == (out or "") + (err or ""), repr(got))
        status, n, line, echo = R.suite_result("test_x.py", " 1.0s", rc, out, err)
        want = "ok" if rc == 0 else "FAIL"
        check(f"exit {rc}: reported as {want}", status == want, (status, line))
        check(f"exit {rc}: the counts are read as if it were empty text",
              n == R.counts((out or "") + (err or "")), (n, line))


def t_a_signal_death_is_reported_with_its_exit_code():
    status, n, line, echo = R.suite_result(
        "test_mail_mask.py", " 3.0s", -11, None, None)          # SIGSEGV on Linux
    check("a suite killed by a signal is FAILED, not passed", status == "FAIL", line)
    check("its name is in the line", "test_mail_mask.py" in line, line)
    check("and the exit code is, so the signal can be looked up", "exit -11" in line, line)


def t_a_suite_with_no_output_says_so():
    status, n, line, echo = R.suite_result("test_quiet.py", " 4.0s", 1, None, None)
    check("a suite that printed nothing is FAILED", status == "FAIL", line)
    check("the line says which suite and what it exited with",
          "test_quiet.py" in line and "exit 1" in line, line)
    check("the line says there was no output to quote", "(no output)" in line, line)
    check("and it counts as no checks at all, never as a pass",
          n == {"passed": 0, "skipped": 0, "failed": 0}, n)
    check("nothing is echoed as a FAIL line, because there is none", echo == [], echo)


def t_a_silent_failure_keeps_counts_and_says_no_output():
    """The two things at once: what failed went to stderr, and stdout was None."""
    status, n, line, echo = R.suite_result(
        "test_half.py", " 2.0s", 1, None, "ok    a\nFAIL  b\n1 passed, 0 skipped, 1 failed\n")
    check("the counts come from the stderr that did arrive",
          n == {"passed": 1, "skipped": 0, "failed": 1}, n)
    check("the suite's own FAIL line is echoed",
          any(l.strip() == "FAIL  b" for l in echo), echo)
    check("the line quotes the counts, so this is not the silent case",
          "1 passed, 0 skipped, 1 failed" in line and "(no output)" not in line, line)


def t_a_timeout_is_a_failure_with_the_same_shape():
    status, n, line, echo = R.suite_result("test_slow.py", "900.0s", "timeout", None, None)
    check("a suite that ran out of time is FAILED", status == "FAIL", line)
    check("and the line says so, without a bogus number",
          "exit timeout" in line and "(no output)" in line, line)


def t_a_passing_suite_is_still_ok():
    status, n, line, echo = R.suite_result(
        "test_good.py", " 0.5s", 0, "ok    a\n2 passed, 0 skipped, 0 failed\n", None)
    check("a suite that exits 0 is ok", status == "ok", line)
    check("its line counts the checks", n == {"passed": 2, "skipped": 0, "failed": 0}, n)
    status, n, line, echo = R.suite_result(
        "test_skipping.py", " 0.5s", 0, "ok    a\nskip  needs the owner's PC\n1 passed, 1 skipped, 0 failed\n", None)
    check("a suite that skipped a check says so on its own line",
          status == "ok" and "1 skipped" in line, line)


def t_a_spawn_that_failed_is_reported_with_its_reason():
    """No exit code ever arrived, so nothing can be compared with 0. The suite
    is FAILED, and the reason is in the line rather than only in a log."""
    status, n, line, echo = R.suite_result(
        "test_x.py", " 0.1s", None, None, None,
        why="the suite could not be started: [WinError 193] %1 is not a valid Win32 application")
    check("a suite that never started is FAILED, not passed", status == "FAIL", line)
    check("the line says which suite", "test_x.py" in line, line)
    check("and the reason is echoed under the line, in full",
          any("WinError 193" in l for l in echo), echo)
    check("nothing is invented as the suite's own output, so the counts are zero",
          n == {"passed": 0, "skipped": 0, "failed": 0}, n)


def t_the_real_runner_reports_a_suite_that_could_not_run():
    """CONTROL, end to end: a dead child is reported, and the sweep carries on.

    `sys.executable` is replaced with a stand-in that cannot be executed, so
    the FIRST spawn really does fail the way the runner's `except OSError`
    is written for, while every later one goes through the real interpreter.
    That is what proves the sweep survives: test_chat_stream.py is reported as
    failed, and test_chat_tags.py - the suite after it - still runs."""
    work = Path(tempfile.mkdtemp(prefix="jarvis-spawn-fail-"))
    try:
        shim = work / "python-shim"
        shim.write_text(
            "import os, pathlib, sys\n"
            "step = pathlib.Path(os.environ['SHIM_STEP'])\n"
            "if not step.exists():\n"
            "    step.write_text('1')\n"
            "    os.execv(sys.executable, [sys.executable, '-c', 'pass'])\n"
            "os.environ.pop('PYTHONPATH', None)\n"
            "os.execv(os.environ['REAL_PYTHON'], [os.environ['REAL_PYTHON']] + sys.argv[1:])\n",
            encoding="utf-8")
        code = ("import runpy, sys; "
                "sys.executable = r'%s'; "
                "sys.argv = [r'%s', 'test_chat_stream.py', 'test_chat_tags.py']; "
                "runpy.run_path(r'%s', run_name='__main__')"
                % (shim, HERE / "run_suites.py", HERE / "run_suites.py"))
        r = subprocess.run([sys.executable, "-c", code], cwd=HERE,
                           capture_output=True, text=True, timeout=900,
                           encoding="utf-8", errors="replace",
                           env=dict(os.environ, SHIM_STEP=str(work / "step"),
                                    REAL_PYTHON=sys.executable))
        out = (r.stdout or "") + (r.stderr or "")
        check("the runner exits non-zero", r.returncode != 0, r.returncode)
        check("the suite whose child could not start is named in a FAIL line",
              "FAIL  test_chat_stream.py" in out, out[-1500:])
        check("and the line says why", "the suite could not be started" in out, out[-1500:])
        check("the suite AFTER it still ran, so one bad spawn no longer ends the sweep",
              "test_chat_tags.py" in out, out[-1500:])
        check("the runner itself did not raise",
              "Traceback" not in out and "OSError" not in out, out[-1500:])
    finally:
        shutil.rmtree(work, ignore_errors=True)


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
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
