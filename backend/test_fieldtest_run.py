"""test_fieldtest_run.py - the field-test runner's own contract.

    py -3 -B backend/test_fieldtest_run.py

WHY THIS EXISTS. `tools/fieldtest_run.py` writes the report that says whether a
deploy may be called field-tested, so its honesty is the product: a stale backend
must be refused before anything runs, a check that needs the phone or the owner's
hands must be BLOCKED and never a pass, and a PASS row must carry the command it
ran and that command's output. This suite pins exactly those four promises, plus
the report's path and its six-row shape.

WHAT IS PROVED HERE, all with every reader and every check injected:

  1. a live commit that differs from origin/main REFUSES the run - exit 2, both
     commits named, no check run and no report written - and `--allow-stale` is
     the only thing that lets it proceed, with the report saying so;
  2. an unreadable live record and an unresolvable origin/main are refusals too:
     an unknown build is never a pass, and `--allow-stale` does not cover it;
  3. a BLOCKED check is exit 2 and never 0, a PARTIAL is exit 2 as well, and a
     FAIL is exit 1 even when another row was BLOCKED;
  4. a PASS row carries its command and its output into the evidence index, and
     a PASS with no evidence cannot be built at all - a check that raises or
     returns a non-PASS Result becomes BLOCKED, never a green row;
  5. the report is `FIELD-TEST-<YYYY-MM-DD-HHMM>.md`, the path it prints is the
     path it wrote, and a second run in the same minute takes `-2` instead of
     overwriting evidence;
  6. the report always has SIX rows, a check that was not requested says so, and
     the counts only cover what was requested.

NOTHING HERE TOUCHES THE LIVE BACKEND, THE NETWORK, `gh`, OR A REAL CHECK. Every
live-commit read, origin/main read and check execution is a lambda in this file;
the only subprocess is the tool's own `--help`, which runs no check.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO  # noqa: E402

sys.path.insert(0, str(REPO / "tools"))
import fieldtest_run as F  # noqa: E402

FAILED, PASSED = [], []

#: Two commit-ish values that are different but both look like commits.
LIVE = "a" * 40
MAIN = "b" * 40
FIXED_NOW = datetime(2026, 11, 15, 12, 51)


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def tmpdir(prefix="fieldtest-run-test-"):
    return Path(tempfile.mkdtemp(prefix=prefix))


def state(live=LIVE):
    """A live record whose sealed commit is `live`."""
    return F.LiveIdentity(commit=live, resealed_at="2026-11-15T00:03:11",
                          tool="tools/reseal_live_install.py")


def ok(check_number=0, command="git -C fake log -1 --format=%h", output="abc1234"):
    """A PASS Result with real-looking evidence."""
    return F.Result(F.PASS, reason=f"check {check_number} was driven",
                    runs=(F.Run(command, 0, output),))


def results_for(one=None, default=F.PASS):
    """One Result per check number: `one` maps specific numbers to a Result."""
    made = {}
    for check_number in range(1, 7):
        made[check_number] = (one or {}).get(check_number) or (
            ok(check_number) if default == F.PASS
            else F.Result(default, reason=f"fake {default} for check {check_number}"))
    return made


def run_tool(argv, results, *, live=None, main=MAIN, now=FIXED_NOW):
    """Call the CLI with every reader and the check runner injected."""
    seen, lines = [], []
    live = state() if live is None else live

    def runner(which, context):
        seen.append((which.number, context))
        return results[which.number]

    code = F.main(list(argv),
                  live_reader=lambda _backend: live,
                  main_reader=lambda _repo, _ref: main,
                  runner=runner, now=now, out=lines.append)
    return code, lines, seen


def reports(out_dir):
    return sorted(Path(out_dir).glob("FIELD-TEST-*.md"))


def read(path):
    return Path(path).read_text(encoding="utf-8")


def row(report, number):
    """The six-row table's line for one check, or "" when it is missing."""
    for line in report.splitlines():
        if line.startswith(f"| {number} |"):
            return line
    return ""


def evidence_ids(report):
    """The ids named in the verdict table's evidence column, in row order."""
    found = []
    for line in report.splitlines():
        if not re.match(r"^\| \d+ \|", line):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 4:
            found.extend(re.findall(r"E\d+", cells[3]))
    return found


# --------------------------------------------------------------------------
#   1. the stale gate
# --------------------------------------------------------------------------

def t_a_stale_backend_refuses_and_names_both_commits():
    root = tmpdir()
    try:
        out = root / "out"
        code, lines, seen = run_tool(["--check", "2", "--out-dir", str(out)],
                                     results_for({2: ok(2)}))
        said = "\n".join(lines)
        check("stale: the run is refused with exit 2", code == 2, code)
        check("stale: the refusal says REFUSED", "REFUSED" in said, said)
        check("stale: ... and names the live commit", LIVE in said, said)
        check("stale: ... and names origin/main's commit", MAIN in said, said)
        check("stale: ... and says nothing ran", "nothing ran" in said, said)
        check("stale: no check was run", seen == [], seen)
        check("stale: no report was written", reports(out) == [], reports(out))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_allow_stale_runs_and_the_report_says_so():
    root = tmpdir()
    try:
        out = root / "out"
        code, lines, seen = run_tool(
            ["--check", "2", "--allow-stale", "--out-dir", str(out)],
            results_for({2: ok(2)}))
        said = "\n".join(lines)
        check("allow-stale: the run proceeds", code == 0, (code, said))
        check("allow-stale: the requested check ran exactly once",
              [number for number, _context in seen] == [2], seen)
        check("allow-stale: the terminal says STALE, allowed",
              "STALE, allowed" in said, said)
        written = reports(out)
        check("allow-stale: a report was written", len(written) == 1, written)
        if written:
            report = read(written[0])
            check("allow-stale: the report says stale was allowed",
                  "Stale allowed:** **yes**" in report, report[:600])
            check("allow-stale: ... and names the build every row is about",
                  LIVE[:12] in report or "aaaaaaaaaaaa" in report, report[:600])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_an_unreadable_live_record_refuses_even_with_allow_stale():
    root = tmpdir()
    try:
        out = root / "out"
        seen, lines = [], []

        def runner(which, _context):
            seen.append(which.number)
            return ok(which.number)

        code = F.main(["--check", "2", "--allow-stale", "--out-dir", str(out)],
                      live_reader=lambda _backend: None,
                      main_reader=lambda _repo, _ref: MAIN,
                      runner=runner, now=FIXED_NOW, out=lines.append)
        said = "\n".join(lines)
        check("unreadable live: exit 2 even with --allow-stale", code == 2, code)
        check("unreadable live: ... names the state file", F.STATE_FILE in said, said)
        check("unreadable live: ... says nothing ran", "nothing ran" in said, said)
        check("unreadable live: ... and says --allow-stale does not cover it",
              "--allow-stale does not cover" in said, said)
        check("unreadable live: no check ran", seen == [], seen)
        check("unreadable live: no report was written", reports(out) == [], reports(out))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_an_unresolvable_origin_main_refuses():
    root = tmpdir()
    try:
        out = root / "out"
        code, lines, seen = run_tool(["--check", "2", "--out-dir", str(out)],
                                     results_for({2: ok(2)}), main="")
        said = "\n".join(lines)
        check("unreadable main: exit 2", code == 2, code)
        check("unreadable main: ... names origin/main", F.DEFAULT_MAIN_REF in said, said)
        check("unreadable main: no check ran and no report exists",
              seen == [] and reports(out) == [], (seen, reports(out)))
    finally:
        shutil.rmtree(root, ignore_errors=True)


# --------------------------------------------------------------------------
#   2. the exit-code contract: blocked is never a pass
# --------------------------------------------------------------------------

def t_a_blocked_check_is_exit_2_never_0():
    root = tmpdir()
    try:
        out = root / "out"
        blocked = F.Result(F.BLOCKED, reason=F.CHECKS[2].blocked)
        code, lines, seen = run_tool(["--check", "3", "--out-dir", str(out)],
                                     results_for({3: blocked}), live=state(MAIN))
        said = "\n".join(lines)
        check("blocked: exit code is 2, never 0", code == 2, code)
        check("blocked: the terminal names it BLOCKED", "BLOCKED" in said, said)
        check("blocked: ... and the exit line says blocked is never a pass",
              "blocked is never a pass" in said, said)
        written = reports(out)
        check("blocked: the report was written", len(written) == 1, written)
        if written:
            report = read(written[0])
            line = row(report, 3)
            check("blocked: the row is BLOCKED", "**BLOCKED**" in line, line)
            check("blocked: the row is not PASS", "PASS" not in line, line)
            check("blocked: the row carries evidence for its reason",
                  re.search(r"E\d+", line) is not None, line)
            check("blocked: its evidence entry carries the reason",
                  "owner-approved card" in report, report[-1500:])
            check("blocked: the counts say 0 PASS / 0 FAIL / 1 BLOCKED",
                  "0 PASS / 0 FAIL / 1 BLOCKED / 0 PARTIAL" in report,
                  [l for l in report.splitlines() if "Counts" in l])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_a_partial_check_is_exit_2_too():
    root = tmpdir()
    try:
        out = root / "out"
        partial = F.Result(F.PARTIAL, reason="the PC half ran; the phone half needs hands")
        code, lines, _seen = run_tool(["--check", "6", "--out-dir", str(out)],
                                      results_for({6: partial}), live=state(MAIN))
        check("partial: exit code is 2", code == 2, code)
        check("partial: the exit line never calls it a pass",
              "blocked is never a pass" in "\n".join(lines), lines)
        written = reports(out)
        if written:
            check("partial: the row is **PARTIAL**", "**PARTIAL**" in row(read(written[0]), 6),
                  row(read(written[0]), 6))
        else:
            check("partial: a report was written", False, written)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_a_fail_is_exit_1_even_with_a_blocked_row():
    root = tmpdir()
    try:
        out = root / "out"
        results = results_for({
            1: F.Result(F.BLOCKED, reason="needs the owner's hands"),
            2: F.Result(F.FAIL, reason="the checks did not all succeed",
                        runs=(F.Run("gh pr checks 1272", 1, "backend FAILURE"),)),
        })
        code, lines, seen = run_tool(["--all", "--out-dir", str(out)], results,
                                     live=state(MAIN))
        check("fail: exit code is 1", code == 1, code)
        check("fail: FAIL outranks BLOCKED", "FAILED" in "\n".join(lines), lines)
        check("fail: all six checks ran", len(seen) == 6, [n for n, _c in seen])
        written = reports(out)
        if written:
            report = read(written[0])
            check("fail: the counts are 4 PASS / 1 FAIL / 1 BLOCKED",
                  "4 PASS / 1 FAIL / 1 BLOCKED / 0 PARTIAL" in report, report[:400])
            check("fail: the FAIL row carries its command",
                  "gh pr checks 1272" in report, report[-1200:])
        else:
            check("fail: a report was written", False, written)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_all_pass_is_exit_0():
    root = tmpdir()
    try:
        out = root / "out"
        code, lines, seen = run_tool(["--all", "--out-dir", str(out)],
                                     results_for(), live=state(MAIN))
        check("all pass: exit 0", code == 0, (code, lines))
        check("all pass: every check ran once",
              [number for number, _c in seen] == [1, 2, 3, 4, 5, 6],
              [number for number, _c in seen])
        written = reports(out)
        check("all pass: a report was written", len(written) == 1, written)
        if written:
            report = read(written[0])
            check("all pass: the counts say six PASS",
                  "6 PASS / 0 FAIL / 0 BLOCKED / 0 PARTIAL" in report, report[:400])
            check("all pass: every row is PASS", all(
                "**PASS**" in row(report, number) for number in range(1, 7)),
                [row(report, number) for number in range(1, 7)])
    finally:
        shutil.rmtree(root, ignore_errors=True)


# --------------------------------------------------------------------------
#   3. a PASS means evidence, and a broken check means BLOCKED
# --------------------------------------------------------------------------

def t_a_pass_row_carries_the_command_and_its_output():
    root = tmpdir()
    try:
        out = root / "out"
        command = "gh pr view 1272 --json state,mergeCommit,statusCheckRollup"
        output = '{"number": 1272, "state": "MERGED"}'
        results = results_for({2: F.Result(
            F.PASS, reason="PR #1272 is MERGED as " + MAIN + ".",
            runs=(F.Run(command, 0, output),))})
        code, _lines, _seen = run_tool(["--check", "2", "--out-dir", str(out)],
                                       results, live=state(MAIN))
        check("pass evidence: exit 0", code == 0, code)
        written = reports(out)
        check("pass evidence: a report was written", len(written) == 1, written)
        if not written:
            return
        report = read(written[0])
        line = row(report, 2)
        check("pass evidence: the row names an evidence id", re.search(r"E\d+", line), line)
        check("pass evidence: the report has an evidence index",
              "## Evidence index" in report, report[:800])
        check("pass evidence: the exact command is in the report", command in report,
              report[-1500:])
        check("pass evidence: the command's exit code is in the report",
              "exit 0" in report, report[-1500:])
        check("pass evidence: the command's output is in the report", output in report,
              report[-1500:])
        ids = evidence_ids(report)
        check("pass evidence: every id in a row has its own entry",
              all(f"### {identifier} —" in report for identifier in ids),
              [identifier for identifier in ids
               if f"### {identifier} —" not in report])
        headings = re.findall(r"^### (E\d+) —", report, re.MULTILINE)
        check("pass evidence: every entry is named by a row",
              sorted(headings) == sorted(ids), (ids, headings))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_a_pass_with_no_evidence_cannot_be_built():
    raised = ""
    try:
        F.Result(F.PASS)
    except ValueError as exc:
        raised = str(exc)
    check("no evidence: a bare PASS raises ValueError", bool(raised), raised)
    check("no evidence: ... and the message says a pass needs evidence",
          "evidence" in raised or "not a pass" in raised, raised)

    root = tmpdir()
    try:
        out = root / "out"

        def runner(which, _context):
            return F.Result(F.PASS)  # raises inside the check

        code = F.main(["--check", "2", "--out-dir", str(out)],
                      live_reader=lambda _backend: state(MAIN),
                      main_reader=lambda _repo, _ref: MAIN,
                      runner=runner, now=FIXED_NOW, out=lambda _m: None)
        check("no evidence: a check that tries it becomes exit 2", code == 2, code)
        written = reports(out)
        if written:
            report = read(written[0])
            check("no evidence: its row is BLOCKED, never PASS",
                  "**BLOCKED**" in row(report, 2), row(report, 2))
        else:
            check("no evidence: a report was written", False, written)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_a_check_that_raises_is_blocked_never_a_pass():
    root = tmpdir()
    try:
        out = root / "out"

        def runner(_which, _context):
            raise RuntimeError("boom in the check")

        code = F.main(["--check", "2", "--out-dir", str(out)],
                      live_reader=lambda _backend: state(MAIN),
                      main_reader=lambda _repo, _ref: MAIN,
                      runner=runner, now=FIXED_NOW, out=lambda _m: None)
        check("raises: exit code is 2", code == 2, code)
        written = reports(out)
        if written:
            report = read(written[0])
            check("raises: the row is BLOCKED", "**BLOCKED**" in row(report, 2),
                  row(report, 2))
            check("raises: the report names the exception", "boom in the check" in report,
                  report[-1200:])
            check("raises: ... and says a check that could not finish is not a pass",
                  "never a pass" in report, report[-1200:])
        else:
            check("raises: a report was written", False, written)
    finally:
        shutil.rmtree(root, ignore_errors=True)


# --------------------------------------------------------------------------
#   4. the report path, the six rows, and the evidence index shape
# --------------------------------------------------------------------------

def t_the_report_path_is_the_documented_one():
    expected = Path("C:/Users/pcadmin/Downloads/FIELD-TEST-2026-11-15-1251.md")
    check("path: the default location is the owner's Downloads folder",
          F.DEFAULT_OUT_DIR == Path("C:/Users/pcadmin/Downloads"), F.DEFAULT_OUT_DIR)
    check("path: <YYYY-MM-DD-HHMM> is the whole suffix",
          F.report_path(Path("C:/Users/pcadmin/Downloads"), FIXED_NOW) == expected,
          F.report_path(Path("C:/Users/pcadmin/Downloads"), FIXED_NOW))

    root = tmpdir()
    try:
        out = root / "out"
        _code, lines, _seen = run_tool(["--check", "2", "--out-dir", str(out)],
                                       results_for({2: ok(2)}), live=state(MAIN))
        written = reports(out)
        check("path: --out-dir moves the report", len(written) == 1, written)
        said = "\n".join(lines)
        check("path: the tool prints the path it wrote",
              f"Report: {written[0]}" in said if written else False, said)
        if written:
            check("path: the printed path IS a file", written[0].is_file(), written[0])
            first = read(written[0]).splitlines()[0]
            check("path: the title carries the same timestamp",
                  "2026-11-15 12:51" in first, first)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_a_second_report_in_the_same_minute_is_not_overwritten():
    root = tmpdir()
    try:
        out = root / "out"
        run_tool(["--check", "2", "--out-dir", str(out)],
                 results_for({2: ok(2)}), live=state(MAIN))
        first = reports(out)
        run_tool(["--check", "2", "--out-dir", str(out)],
                 results_for({2: ok(2, output="a second run")}), live=state(MAIN))
        both = reports(out)
        check("same minute: two runs leave two reports", len(both) == 2, both)
        check("same minute: the first report keeps its own name",
              first and first[0] in both, (first, both))
        check("same minute: the first report was not overwritten",
              first and "a second run" not in read(first[0]), first)
        if len(both) == 2:
            second = out / "FIELD-TEST-2026-11-15-1251-2.md"
            check("same minute: the second takes the -2 name", second.is_file(),
                  (second, both))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_the_report_always_has_six_rows_and_says_what_was_not_requested():
    root = tmpdir()
    try:
        out = root / "out"
        code, _lines, seen = run_tool(["--check", "2", "--out-dir", str(out)],
                                      results_for({2: ok(2)}), live=state(MAIN))
        check("six rows: only the requested check ran", code == 0 and len(seen) == 1,
              (code, seen))
        written = reports(out)
        if not written:
            check("six rows: a report was written", False, written)
            return
        report = read(written[0])
        rows = [line for line in report.splitlines() if re.match(r"^\| \d+ \|", line)]
        check("six rows: the table has six rows", len(rows) == 6, rows)
        check("six rows: the requested one is PASS", "**PASS**" in row(report, 2),
              row(report, 2))
        for number in (1, 3, 4, 5, 6):
            check(f"six rows: check {number} says not requested",
                  "not requested" in row(report, number), row(report, number))
        check("six rows: an unrequested row is never PASS", all(
            "PASS" not in row(report, number) for number in (1, 3, 4, 5, 6)),
            [row(report, number) for number in (1, 3, 4, 5, 6)])
        check("six rows: the counts only cover the requested check",
              "1 PASS / 0 FAIL / 0 BLOCKED / 0 PARTIAL" in report,
              [line for line in report.splitlines() if "Counts" in line])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_the_six_checks_are_the_named_six():
    titles = [which.title for which in F.CHECKS]
    check("checks: there are six, numbered 1-6",
          [which.number for which in F.CHECKS] == [1, 2, 3, 4, 5, 6],
          [which.number for which in F.CHECKS])
    check("checks: the titles are the brief's six", titles == [
        "Coder chat window",
        "GitHub CI truth + merge truth",
        "The 2 GiB send-to-phone path",
        "Phone Local-AI truth",
        "Paired-device awareness",
        "Preflight + provenance",
    ], titles)
    for check_number in (1, 3, 4, 5):
        which = F.CHECKS[check_number - 1]
        check(f"checks: {check_number} is recorded as needing hands/phone",
              which.needs in ("the phone", "the owner's hands"), which.needs)
        check(f"checks: {check_number} carries the reason it is BLOCKED",
              len(which.blocked) > 40, which.blocked)
    for check_number in (2, 6):
        which = F.CHECKS[check_number - 1]
        check(f"checks: {check_number} is one this runner drives", which.needs == "this PC",
              which.needs)


# --------------------------------------------------------------------------
#   5. the pieces the gate is built from
# --------------------------------------------------------------------------

def t_the_live_record_is_read_from_the_state_file():
    root = tmpdir()
    try:
        live = root / "live"

        def put(doc):
            live.mkdir(parents=True, exist_ok=True)
            (live / F.STATE_FILE).write_text(doc, encoding="utf-8")

        put('{"resealed": {"commit": "%s", "at": "2026-11-15T00:03:11", '
            '"tool": "tools/reseal_live_install.py"}}' % LIVE)
        got = F.read_live_identity(live)
        check("record: resealed.commit is the live commit",
              got is not None and got.commit == LIVE, got)
        check("record: resealed.at and tool are kept",
              got is not None and got.resealed_at and got.tool, got)

        put('{"resealed": {"ref": "%s"}}' % LIVE)
        got = F.read_live_identity(live)
        check("record: a hex resealed.ref is a usable fallback",
              got is not None and got.commit == LIVE, got)

        put('{"resealed": {"ref": "origin/main", "commit": "%s"}}' % LIVE)
        got = F.read_live_identity(live)
        check("record: commit wins over the ref name",
              got is not None and got.commit == LIVE, got)

        put('{"resealed": {"ref": "origin/main"}}')
        check("record: a ref NAME is not a commit, so it reads as no record",
              F.read_live_identity(live) is None, F.read_live_identity(live))

        put('{"patches": {}}')
        check("record: a record with no resealed block is no record",
              F.read_live_identity(live) is None)

        put('{not json')
        check("record: broken JSON is no record", F.read_live_identity(live) is None)

        shutil.rmtree(live, ignore_errors=True)
        check("record: a missing file is no record",
              F.read_live_identity(root / "absent") is None)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_the_gate_compares_commits_by_value():
    check("same: a full sha equals itself", F.same_commit(LIVE, LIVE))
    check("same: a short sha equals its full form", F.same_commit(LIVE[:12], LIVE))
    check("same: the comparison ignores case", F.same_commit(LIVE.upper(), LIVE))
    check("same: two different commits differ", not F.same_commit(LIVE, MAIN))
    check("same: nothing equals an empty value",
          not F.same_commit("", LIVE) and not F.same_commit(LIVE, ""))
    check("same: a 6-character stub is not a commit", not F.same_commit(LIVE[:6], LIVE))


def t_the_exit_code_contract_is_exact():
    check("exit: PASS alone is 0", F.exit_code_for([F.PASS]) == 0)
    check("exit: a BLOCKED is 2", F.exit_code_for([F.PASS, F.BLOCKED]) == 2)
    check("exit: a PARTIAL is 2", F.exit_code_for([F.PASS, F.PARTIAL]) == 2)
    check("exit: a FAIL is 1", F.exit_code_for([F.PASS, F.FAIL]) == 1)
    check("exit: FAIL outranks BLOCKED",
          F.exit_code_for([F.BLOCKED, F.FAIL]) == 1)
    check("exit: the four verdicts are the only ones",
          set(F.VERDICTS) == {F.PASS, F.FAIL, F.BLOCKED, F.PARTIAL}, F.VERDICTS)


def t_the_selected_checks_and_the_context_reach_the_runner():
    root = tmpdir()
    try:
        out = root / "out"
        live = state(MAIN)
        code, _lines, seen = run_tool(
            ["--check", "6", "--check", "2", "--allow-stale", "--out-dir", str(out)],
            results_for(), live=live)
        check("selection: checks run in number order",
              [number for number, _c in seen] == [2, 6],
              [number for number, _c in seen])
        check("selection: exit 0 when both pass", code == 0, code)
        if seen:
            context = seen[0][1]
            check("context: the live commit is the record's",
                  context.live.commit == MAIN, context.live)
            check("context: origin/main is the resolved commit",
                  context.main_commit == MAIN, context.main_commit)
            check("context: --allow-stale reaches the check",
                  context.stale_allowed is True, context.stale_allowed)
            check("context: the out dir is not the repo's business",
                  context.backend_path == F.DEFAULT_BACKEND_PATH, context.backend_path)

        seen2, lines2 = [], []
        code2 = F.main(["--check", "2", "--repo", str(root), "--backend-path", str(root),
                        "--out-dir", str(out)],
                       live_reader=lambda _backend: state(MAIN),
                       main_reader=lambda repo, ref: MAIN,
                       runner=lambda which, context: (seen2.append((which.number, context))
                                                      or results_for()[which.number]),
                       now=FIXED_NOW, out=lines2.append)
        check("context: --repo and --backend-path are threaded",
              code2 == 0 and seen2 and seen2[0][1].repo == root
              and seen2[0][1].backend_path == root,
              (code2, seen2[:1]))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_no_selector_refuses():
    root = tmpdir()
    try:
        lines = []
        code = F.main(["--out-dir", str(root)], out=lines.append)
        said = "\n".join(lines)
        check("usage: no selector exits 2", code == 2, code)
        check("usage: ... and asks for --check or --all",
              "--check" in said and "--all" in said, said)

        lines2 = []
        code2 = F.main(["--check", "2", "--all", "--out-dir", str(root)],
                       out=lines2.append)
        check("usage: --check with --all exits 2", code2 == 2, code2)
        check("usage: ... and says not both",
              "not both" in "\n".join(lines2), lines2)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_the_help_text_runs():
    tool = REPO / "tools" / "fieldtest_run.py"
    proc = subprocess.run([sys.executable, "-B", str(tool), "--help"],
                          capture_output=True, text=True, timeout=60)
    check("--help: exits 0", proc.returncode == 0, (proc.returncode, proc.stderr[-400:]))
    check("--help: prints the usage line",
          "usage: fieldtest_run.py" in proc.stdout, proc.stdout[:200])
    flat = " ".join(proc.stdout.split())
    check("--help: names the Downloads default without a format crash",
          "C:\\Users\\pcadmin\\Downloads" in flat, flat[-300:])


def main():
    for function in (
            t_a_stale_backend_refuses_and_names_both_commits,
            t_allow_stale_runs_and_the_report_says_so,
            t_an_unreadable_live_record_refuses_even_with_allow_stale,
            t_an_unresolvable_origin_main_refuses,
            t_a_blocked_check_is_exit_2_never_0,
            t_a_partial_check_is_exit_2_too,
            t_a_fail_is_exit_1_even_with_a_blocked_row,
            t_all_pass_is_exit_0,
            t_a_pass_row_carries_the_command_and_its_output,
            t_a_pass_with_no_evidence_cannot_be_built,
            t_a_check_that_raises_is_blocked_never_a_pass,
            t_the_report_path_is_the_documented_one,
            t_a_second_report_in_the_same_minute_is_not_overwritten,
            t_the_report_always_has_six_rows_and_says_what_was_not_requested,
            t_the_six_checks_are_the_named_six,
            t_the_live_record_is_read_from_the_state_file,
            t_the_gate_compares_commits_by_value,
            t_the_exit_code_contract_is_exact,
            t_the_selected_checks_and_the_context_reach_the_runner,
            t_no_selector_refuses,
            t_the_help_text_runs,
    ):
        function()
    print()
    if FAILED:
        print(f"{len(FAILED)} FAILED, {len(PASSED)} passed")
        for name in FAILED:
            print(f"  - {name}")
        return 1
    print(f"all {len(PASSED)} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
