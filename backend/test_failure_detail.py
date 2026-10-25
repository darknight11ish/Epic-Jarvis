"""test_failure_detail.py - a failed suite shows the line that says WHY.

WHY THIS EXISTS. On 2026-10-25 the backup suite failed once in eleven runs and
the report was `493 passed, 1 failed`, with the cause written nowhere. The cause
was a Python traceback - `PermissionError: [WinError 5] Access is denied` on a
file swap, re-raised as `RestoreError: could not replace a file` - and a whole
traceback goes to STDERR. Two things threw it away:

  * `tools/check_claims.py` built a `test:` row's failure detail from
    `done.stdout` only, so a suite that died on an exception was reported as
    `exited 1: Traceback (most recent call last):` and nothing else;
  * `backend/run_suites.py` echoed only lines starting `FAIL`, containing
    `Traceback`, or containing `failed:`, so even a CI log showed the header
    and never the exception line.

Both now also echo the exception line(s). This file pins that, and pins that no
verdict moved: the same failing input is still `FAIL`, a passing run is still
`ok` with no detail, and the reason is ADDED to the detail rather than replacing
what the suite printed.

THE CONTROL is the old filters, reproduced below on the same sample. With the
rules as they were, the sample's `PermissionError` line appears in neither
detail - so these checks fail against the old code. The sample also carries a
harmless line and two traceback headers, and none of those may become the
reason: a fix that echoed every stderr line would trade a missing cause for a
wall of noise.
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys
from types import SimpleNamespace

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent

PASSED: list[str] = []
FAILED: list[str] = []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def _load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


C = _load("check_claims_under_test", ROOT / "tools" / "check_claims.py")
R = _load("run_suites_under_test", ROOT / "backend" / "run_suites.py")

# The shape of the failure that started this: a summary on stdout and a
# traceback whose last line is the reason, on stderr - exactly what the real
# 2026-10-25 flake produced.
SAMPLE_STDOUT = "493 passed, 1 failed\n"
SAMPLE_STDERR = "\n".join([
    "Traceback (most recent call last):",
    '  File "...\\backend\\test_backup.py", line 812, in t_a_restore_reopens_the_decks',
    "    _apply_restore(archive, target)",
    '  File "...\\backend\\jarvis_backup.py", line 3085, in _apply_restore',
    '    raise RestoreError("could not replace a file (PermissionError)")',
    "PermissionError: [WinError 5] Access is denied: "
    "'...\\backend\\rebuilt\\jarvis-framework.toml.tmp-1'",
    "",
    "During handling of the above exception, another exception occurred:",
    "",
    "Traceback (most recent call last):",
    '  File "...\\backend\\jarvis_backup.py", line 3085, in _apply_restore',
    '    raise RestoreError("could not replace a file (PermissionError)")',
    "jarvis_backup.RestoreError: could not replace a file (PermissionError)",
]) + "\n"
PERMISSION = "PermissionError: [WinError 5] Access is denied"
RESTORE = "jarvis_backup.RestoreError: could not replace a file (PermissionError)"
HARMLESS = "booting the test backend from the temporary staging folder"

# --- the two tools now agree on what a reason looks like -------------------

found = C.exception_lines(SAMPLE_STDERR)
check("check_claims sees both exception lines, in the order they were written",
      len(found) == 2 and found[0].startswith(PERMISSION) and found[1] == RESTORE,
      repr(found))
check("the traceback header is never the reason",
      not any("Traceback (most recent call last)" in line for line in found),
      repr(found))
check("limit=1 keeps only the last line (the detail stays one readable line)",
      C.exception_lines(SAMPLE_STDERR, limit=1) == [RESTORE],
      repr(C.exception_lines(SAMPLE_STDERR, limit=1)))
check("a harmless stderr line is not an exception",
      C.exception_lines(HARMLESS + "\n") == [], repr(C.exception_lines(HARMLESS)))
check("no stderr at all is not an error",
      C.exception_lines("") == [] and C.exception_lines(None) == [])

# THE CONTROL: the old stdout-only detail, on the same sample.
old_tail = [line for line in SAMPLE_STDOUT.strip().splitlines()[-3:] if line.strip()]
old_detail = "backend/test_backup.py exited 1: " + " | ".join(old_tail)
check("THE CONTROL: the old stdout-only detail never carried the reason",
      PERMISSION not in old_detail and RESTORE not in old_detail, old_detail)

# And the real function, with its subprocess answer stood in for.
real_run = C.subprocess.run
C.subprocess.run = lambda *a, **k: SimpleNamespace(
    returncode=1, stdout=SAMPLE_STDOUT, stderr=SAMPLE_STDERR)
try:
    ok, detail = C.check_test("backend/test_backup.py")
finally:
    C.subprocess.run = real_run
check("a crashed suite is still a FAILURE", ok is False, detail)
check("and its message now names the reason", PERMISSION in detail and RESTORE in detail,
      detail)

# --- the runner's echoed detail -------------------------------------------

# THE CONTROL: the old filter, on the same output.
old_echo = ["      " + line for line in (SAMPLE_STDOUT + SAMPLE_STDERR).splitlines()
            if line.startswith("FAIL") or "Traceback" in line or "failed:" in line]
check("THE CONTROL: the old runner echo was the header and nothing else",
      any("Traceback" in line for line in old_echo)
      and not any(PERMISSION in line or RESTORE in line for line in old_echo),
      repr(old_echo))

status, counts, annotation, echo = R.suite_result(
    "test_backup.py", "82.3s", 1, SAMPLE_STDOUT, SAMPLE_STDERR)
check("the runner still calls a crashed suite FAIL", status == "FAIL", f"{status} {annotation}")
check("the runner's echoed detail now names the reason",
      any(PERMISSION in line for line in echo) and any(RESTORE in line for line in echo),
      repr(echo))
check("the GitHub annotation is still capped and still starts with FAIL",
      annotation.startswith("FAIL") and len(annotation) <= 200, annotation)
check("the counts still come from the suite's own summary",
      counts["passed"] == 493 and counts["failed"] == 1, repr(counts))

status, counts, annotation, echo = R.suite_result(
    "test_green.py", "0.4s", 0, "5 passed, 0 failed\n", "")
check("a green suite is still ok and adds no detail",
      status == "ok" and echo == [], f"{status} {echo!r}")

print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
sys.exit(1 if FAILED else 0)
