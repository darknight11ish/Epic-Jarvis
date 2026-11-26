"""test_claims.py - tools/check_claims.py, the claims register's own guard.

    python3 backend/test_claims.py

WHAT THIS IS FOR. `tools/check_claims.py` reads `docs/CLAIMS.tsv` and fails in
two directions: a `built` row whose check stopped passing, and an `open` row
whose gap has closed (which means the ROW is stale, not the code). A guard that
is never itself guarded is how the register would quietly stop working - the
script could lose a direction, a kind, or its `--list`, and every run would
still print a happy line.

So this proves each direction on a temporary register holding exactly one
broken row, never on the real one:

  * a `built` row whose check fails -> exit 1, and the message says the claim
    no longer holds and names the row and its source;
  * an `open` row whose check passes -> exit 1, and the message says the gap
    closed and the row is stale;
  * an `open` row whose check still fails -> exit 0 (the direction must not
    fire on a real gap, or every `open` row would be red forever);
  * a register the check cannot read whole -> exit 1, never a silent skip:
    the wrong column count, an unknown check kind, an unknown state, a
    duplicated id, and an `unverifiable` row whose "reason" is actually a
    definite check;
  * an empty register -> exit 1, because "nothing was wrong" and "nothing was
    looked at" must not print the same line.

And the skip honesty added 2026-10-24, for the hole the audit filed as T-1:
claim F11 named `test:backend/test_data_backup.py`, and that suite exits 0
after printing `skip  ...` when `refuse_write_into_a_locker` is not in the tree,
so deleting the safety guard still read as built. So this file now proves:

  * a `built` row whose suite exits 0 AFTER SKIPPING a substantive check -> exit
    1, and the line quoted is the skip, never "holds";
  * the companion: a clean suite still proves its row, and the environment skips
    this repository's own suites print (the `icacls` fixture, a missing package)
    still do not - a rule that reddened those would red four green rows;
  * a suite that merely COUNTS a skip in its summary, with no reason printed,
    is not proof either;
  * the allow-list is keyed to the suite that needs it: an `icacls` reason
    proves a `test_data_backup` row and proves nothing for another suite's row.

  * and an allowed skip is never silent (2026-11-13). `backend/test_owner_check.py`
    skips the one check it cannot run on Windows - the REAL Windows Hello path
    would raise a real prompt - and the owner's desk read claim C163 red because
    that reason was not in the allow-list. So this file also proves the entry is
    there, that it accepts the reason the suite really prints, and that the run
    NAMES the suite, quotes the skip and counts the rows it did not look at,
    whether or not `-v` was typed.

And the environment the suites are started with (2026-10-25). `JARVIS_BACKEND`
is set for the owner's Windows account on this PC and names the LIVE backend
folder, and `backend/_where.py` puts that folder first on `sys.path`, so the
checker used to start every suite against live code: on 2026-10-25 that made it
report claim MED-01 as no longer holding (`backend/test_medical_advocate.py
exited 1: AssertionError: MedicalStoreUnavailable not raised`) on a `main` that
was never red - the same suite is 95/95 green with the variable removed.
`backend/run_suites.py:881-884` had ignored that ambient value since 2026-10-21.
So this file also proves the checker holds the same contract:

  * its own parser offers `--use-env-backend`, off unless it is typed;
  * with the variable set and no flag, the environment handed to a suite carries
    no `JARVIS_BACKEND`, and one line names the value that was ignored;
  * with the flag, the value is passed through unchanged;
  * end to end, on one throwaway suite that fails on purpose (so its output is
    quoted rather than swallowed): the child does not see the ambient value, and
    does see it when the flag asks for it.

And the AMBIENT REPOSITORY OVERRIDES are ignored too (architect ruling B,
2026-11-25). `JARVIS_REVIEW_REPO` and `JARVIS_DEFECT_REGISTER` are set at USER
level on this PC (the first names the MAIN checkout) and absent in CI, so a
`test:` row's suite that read them judged a different tree at the desk than on a
runner - measured before the fix, a probe suite the checker started printed the
main checkout's path from inside a worktree. They now reach a suite only when
`--repo` names the repository to judge, and one line names what was ignored. So
this file also proves the env is stripped, that `--repo` points both at that
copy, that the process's own environment is never mutated, and end to end that a
set-but-unpassed `JARVIS_REVIEW_REPO` no longer changes a suite's result.

And the suites run OFFLINE (2026-11-13), with the same six switches
`backend/run_suites.py` forces. Without them the Live settings parity suite
fetched five model files from Hugging Face inside one turn, and the empty
`memory.db` it created tripped its own check that a carded change writes no
settings file - claim C101 read red at the desk while CI, whose runner forces the
switches, was green. So this file also proves the checker's `OFFLINE_ENVS` IS the
runner's dictionary, that a caller's own `HF_HUB_OFFLINE=0` cannot switch a
download back on, and end to end that a suite the checker starts sees
`HF_HUB_OFFLINE=1`.

And a suite RUN leaves no bytecode behind (2026-11-13), the runner's other
hermetic switch (`PYTHONDONTWRITEBYTECODE=1`, `backend/run_suites.py:1452-1453`).
Without it the desk's SECOND register run was red on D06: the first run's suites
imported base-only modules and left `jarvis-backend/__pycache__`, which
`backend/test_base_matches_repo.py` refuses. So this file also proves the checker
forces that switch, and end to end that a suite it starts can import a module
and leave no `__pycache__` behind.

And a suite that PASSED NOTHING is not a pass (2026-11-18, external review).
The skip rule reads what a suite PRINTS, so a suite that exits 0 having run no
check at all - and so printed no skip either - used to prove its row, which is
the one hole the whole claims register exists to keep shut. `backend/run_suites.py`
already fails that shape everywhere it runs a suite (`passed == 0`, no allowlist,
2026-10-27); the claims checker is the caller it never reached. So this file also
proves:

  * a `built` row whose suite exits 0 having PASSED NOTHING -> exit 1, naming the
    suite, its counts, and the two legitimate fixes (make the suite run a check,
    or record the environment skip with a reason and a date);
  * the same fixture - nothing passed - is PROVEN when the suite's whole body is
    a skip this machine's `ENVIRONMENT_SKIPS` entry covers and the suite really
    printed it, and NOT proven when the entry exists but the suite printed
    nothing: an entry records why a skip happened, not that one happened;
  * a suite that prints a skip AND passes checks is unchanged, and a normal
    passing suite is unchanged;
  * the counts are `backend/run_suites.py`'s own parser, imported rather than
    copied, and the zero predicate is the runner's `passed == 0`;
  * the real register's run REPORTS the totals it watched, so a green run cannot
    be read as one that watched no check.

And on the real register, four things the checker cannot say about itself:

  * it exits 0 today, so the first run after this lands is green;
  * `--list` prints every row it checked - by id - so the happy line can be
    told apart from a run that looked at nothing;
  * every one of the eight kinds in the vocabulary is exercised (a kind nothing
    uses is a kind nothing tests): the seven CHECK kinds by a real row, and
    `changelog:` by the twelve `source` cells added on 2026-11-25 - no claim is
    PROVED by the changelog sentence that announced it, so no row carries it as
    a check, and the kind's two halves are bitten on a throwaway repository
    instead;
  * every row's `source` names a file that exists and either a line inside it or
    a symbol/heading/changelog title it really carries, so a doc edit that moves
    the anchor (or a renamed function, or a reworded changelog title) is caught
    here rather than by a reader.

And the decision record became TWO places on 2026-10-28. A new owner decision is
one file under `decisions.d/`, rolled into `docs/DECISIONS.md` later
(`decisions.d/README.md`; `tools/roll_decisions.py`), so this suite also proves:

  * a `source` may name either place - a fragment is a real file with real lines
    until the roll removes it - and a pointer that names a fragment which is no
    longer there says to cite the record instead of blaming the reader;
  * a `grep:`/`absent:` that names the record is answered by BOTH places, end to
    end, in a throwaway `--repo`: text that lives only in a fragment makes a
    `grep:` row hold, and makes an `absent:` row fail (the direction that must
    never go quiet).

Needs nothing from the owner's PC, no network and no third-party package: the
checker itself is standard library only, and so is this.
"""
from __future__ import annotations

import contextlib
import io
import os
import re
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
CHECKER = REPO / "tools" / "check_claims.py"
REGISTER = REPO / "docs" / "CLAIMS.tsv"

#: The decision record, and the folder a decision is written in before the roll
#: folds it in. Both are spelled as a `source` cell spells them; this reader
#: keeps its own copy on purpose, rather than importing the checker's, so a
#: source is judged by something that does not share that parser.
DECISION_RECORD = "docs/DECISIONS.md"
DECISION_FRAGMENTS = "decisions.d"

sys.path.insert(0, str(HERE))

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


HEADER = "# id\tclaim\tcheck\tstate\tsource\n"

#: How long ONE run of the WHOLE register may take here, in seconds. The
#: checker's own ceiling is 900 s for ONE suite (`tools/check_claims.py`'s
#: TEST_TIMEOUT), and the register has more than a hundred `test:` rows, so this
#: harness ceiling has to sit well above the whole sweep. Its history is the
#: reason for the number, and the number is measured rather than guessed:
#:
#:   * 600 s was the first ceiling, and it expired before the first full run
#:     finished (measured 2026-11-13 on a loaded PC);
#:   * 1800 s replaced it. By 2026-11-25 the sweep on the owner's own PC
#:     measured 1740-1830 s, so the suite failed at its own ceiling while the
#:     direct command exited 0 - a check that cannot pass on the one machine it
#:     most needs to pass on. A ceiling chosen above the measured cost is the
#:     only kind that is a test rather than a coin toss;
#:   * 3600 s is about twice the worst of those measurements. It also sits above
#:     `backend/run_suites.py`'s own 2400 s per-suite limit, so on the runner
#:     path this ceiling is not the one that would fire first; on the direct
#:     `py -3 -B backend/test_claims.py` path it is the only limit, and about
#:     twice the measured worst is the headroom it exists to give.
#:
#: AND THE SUITE RUNS THE SWEEP ONCE, NOT TWICE (2026-11-25). The green-line and
#: `--list` checks used to start the whole register separately - about 2 x 30
#: minutes on the desk, and together over the runner's own 2400 s. `--list`
#: prints the summary line as well as every row, so ONE run proves both; see
#: `the_register_run`.
REGISTER_TIMEOUT = 3600


def run(*args, env=None, timeout=600):
    """(exit code, output) for one run of the checker, from the repo root.

    `env` is the environment the CHECKER is started with; None inherits this
    process's own, which is what every check except the `JARVIS_BACKEND` ones
    wants. Those pass a dict so the ambient value is a value this test chose,
    not whatever the machine happens to carry.

    `timeout` is this harness's own ceiling. The ONE call that checks the whole
    real register (`the_register_run`) passes `REGISTER_TIMEOUT`, because 600 s
    is shorter than the checker's own per-suite ceiling and can expire while it
    is still working; everything else drives one or two throwaway rows and
    stays at 600 s.
    """
    done = subprocess.run(
        [sys.executable, str(CHECKER), *args], cwd=str(REPO),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, env=env)
    return done.returncode, (done.stdout or "") + (done.stderr or "")


#: The one run of the whole real register. A list rather than a module global
#: so the cache is visible in the code that fills it, and so a failed start is
#: cached too - a second 30-minute attempt would tell a reader nothing new.
_REGISTER_RUN: list = []


def the_register_run():
    """(exit code, output) for ONE `--list` run of the whole real register.

    `--list` implies `-v` and prints its summary line after the rows, so this
    one run is the evidence for both checks that need the whole sweep: the
    green line with its suite counts, and every row id. Started once, on the
    first caller; `REGISTER_TIMEOUT`'s comment says why that matters.
    """
    if not _REGISTER_RUN:
        _REGISTER_RUN.append(run("--list", timeout=REGISTER_TIMEOUT))
    return _REGISTER_RUN[0]


def register_with(rows: str) -> Path:
    """A throwaway register holding exactly `rows`."""
    handle = tempfile.NamedTemporaryFile(
        "w", suffix=".tsv", delete=False, encoding="utf-8")
    handle.write(HEADER + rows)
    handle.close()
    return Path(handle.name)


def data_rows(text: str):
    """Every row of a register, as dicts - this test's own tiny reader, so it
    does not agree with the checker by sharing its parser."""
    out = []
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split("\t")
        out.append(dict(zip(("id", "claim", "check", "state", "source"), parts)))
    return out


# ---------------------------------------------------------------------------
#   The real register
# ---------------------------------------------------------------------------

def t_the_checker_exists():
    check("tools/check_claims.py exists", CHECKER.is_file())
    check("docs/CLAIMS.tsv exists", REGISTER.is_file())


def t_the_committed_register_is_green():
    # The whole-register run is `--list` (see `the_register_run`): its output
    # carries this summary line AFTER the rows, so one sweep proves both checks.
    code, out = the_register_run()
    check("the register passes today (the first run after it lands is green)",
          code == 0, out[-1500:])
    check("the green line says a number of rows, so 'nothing is wrong' cannot "
          "be confused with 'nothing was looked at'",
          bool(re.search(r"\d+ claim\(s\) checked", out)), out[-800:])
    check("the green line splits the register into built / still open / "
          "unverifiable",
          all(word in out for word in ("built", "still open", "unverifiable")),
          out[-800:])
    # The zero-check rule (2026-11-18) is decided one suite at a time; this is
    # the same fact at the scale of the run, so a green register cannot be read
    # as one whose suites watched nothing. It is also how many checks the change
    # was measured against, which is the number the report quotes.
    check("the run reports how many checks the `test:` rows actually watched, "
          "with the passed / skipped / failed split",
          re.search(r"\d+ suite run\(s\) behind the `test:` rows reported "
                    r"\d+ check\(s\): \d+ passed, \d+ skipped, \d+ failed\.", out)
          is not None, out[-1500:])


def t_list_prints_every_row_it_checked():
    code, out = the_register_run()
    check("--list still exits 0 on the real register", code == 0, out[-800:])
    rows = data_rows(REGISTER.read_text(encoding="utf-8"))
    missing = [row["id"] for row in rows if row["id"] not in out]
    check(f"every one of the {len(rows)} row ids is printed by --list", not missing,
          missing)
    check("--list says in words that all of them were looked at",
          f"all {len(rows)} row(s) were looked at" in out, out[-400:])


def t_the_whole_register_is_swept_once():
    """The suite's own cost, which is what made it fail on the owner's PC.

    The whole-register sweep measured 1740-1830 s there on 2026-11-25, and CI
    gives ONE suite 2400 s (`backend/run_suites.py`). The green-line and
    `--list` checks used to start the sweep separately - nearly an hour of the
    desk's time and over the runner's own ceiling - so both now read ONE run.
    This proves the NUMBER of sweeps, with the checker itself stubbed out and
    the two inner checks' verdicts both silenced and NOT counted: the real
    verdicts are the two tests above, and a stub cannot prove a register.
    """
    rows = data_rows(REGISTER.read_text(encoding="utf-8"))
    states = [sum(1 for row in rows if row["state"] == state)
              for state in ("built", "open", "unverifiable")]
    canned = (f"{len(rows)} claim(s) checked against the code: {states[0]} "
              f"built, {states[1]} still open, {states[2]} unverifiable (the "
              f"reason is in each row).\n"
              f"3 suite run(s) behind the `test:` rows reported 9 check(s): 9 "
              f"passed, 0 skipped, 0 failed.\n\nall {len(rows)} row(s) were "
              f"looked at:\n"
              + "\n".join(f"  {row['id']:<7} {row['state']}" for row in rows))
    calls = []
    real_run = run
    real_passed, real_failed = list(PASSED), list(FAILED)

    def stub(*args, **kwargs):
        calls.append((args, kwargs.get("timeout")))
        return 0, canned

    # `run` is looked up by name inside the two checks, so replacing the module
    # global is what they call.
    globals()["run"] = stub
    _REGISTER_RUN.clear()
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            t_the_committed_register_is_green()
            t_list_prints_every_row_it_checked()
    finally:
        globals()["run"] = real_run
        _REGISTER_RUN.clear()
        PASSED[:] = real_passed
        FAILED[:] = real_failed
    check("the whole register is swept ONCE for both checks, not twice",
          len(calls) == 1, calls)
    check("... and that one call gets the ceiling with real headroom",
          bool(calls) and calls[0][1] == REGISTER_TIMEOUT, calls)
    check("... where the ceiling is at least twice the 1800 s one it replaces, "
          "which is about twice the desk's measured worst (1830 s) - a ceiling "
          "under the real cost is not a test",
          REGISTER_TIMEOUT >= 3600, REGISTER_TIMEOUT)


def t_the_vocabulary_is_actually_used():
    """A kind no row uses is a kind no test of this script would ever reach.

    `symbol:` joined the vocabulary on 2026-11-25 (architect ruling A). Row C54
    uses it as its check - the same `faceSerious` declaration `grep:` used to
    name - so the kind is exercised through a real row as well as through the
    throwaway bite test below.

    `changelog:` joined the same day, for the rolled changelog bullets no
    heading and no declaration can name. It is exercised by the register in its
    OTHER role: twelve rows cite a bullet's bold title as their `source`. No row
    carries it as a CHECK, and none should - a claim is proved by the code, not
    by the changelog sentence that announced it - so the check half of the kind
    is proved on a throwaway repository
    (`t_a_changelog_row_bites_on_a_temp_repository`) instead of being demanded
    from a real row.
    """
    rows = data_rows(REGISTER.read_text(encoding="utf-8"))
    kinds = {row["check"].split(":", 1)[0] for row in rows
             if row["state"] != "unverifiable"}
    for kind in ("file", "no-file", "grep", "absent", "test", "number",
                 "symbol"):
        check(f"the register uses a `{kind}:` row", kind in kinds, sorted(kinds))
    cited = [row["id"] for row in rows
             if row["source"].startswith("changelog:")]
    check("the register cites a changelog bullet by its bold title, so the "
          "`changelog:` kind is exercised too", bool(cited), cited)
    check("... and all twelve of the rows the 2026-11-25 sweep migrated say so",
          len(cited) == 12, cited)


def source_problems(rows, repo: Path = REPO) -> list:
    """Every row whose `source` does not trace to what it names.

    Four forms are accepted since the 2026-11-25 ruling: `path:line`,
    `path::symbol`, `doc.md#heading` and `changelog:"<bold title>"`. The durable
    three are verified by the checker's own `check_claims.source_problem`, so
    this suite and the checker cannot disagree about what a citation means - a
    symbol, heading or changelog title is looked up in the file, not merely
    typed into the cell.

    Since 2026-10-28 a decision may be recorded as ONE file under
    `decisions.d/` and rolled into `docs/DECISIONS.md` later, so a `:line` source
    may name EITHER place - both are files with lines, and neither is treated
    specially here. What is special is the failure: the roll removes a fragment
    after folding it in, so a pointer that names one that is no longer there is
    told to cite the record, rather than reported as a typo. The roll rewrites
    those cells itself (`tools/roll_decisions.py`), which is what keeps this
    check from ever having to guess where the entry went.
    """
    sys.path.insert(0, str(REPO / "tools"))
    import check_claims
    bad = []
    for row in rows:
        source = row["source"]
        problem = check_claims.source_problem(source, repo=repo)
        if problem is None:
            continue
        durable = ("::" in source or "#" in source
                   or source.startswith("changelog:"))
        path, _, _line = source.rpartition(":")
        if (not durable
                and path.replace("\\", "/").startswith(DECISION_FRAGMENTS + "/")
                and not (repo / path).is_file()):
            problem += (f" - a fragment is removed when it is rolled into "
                        f"{DECISION_RECORD}; cite the record instead")
        bad.append(f"{row['id']}: {problem}")
    return bad


def t_every_source_points_at_a_real_line():
    """A register whose sources drift off their anchor is a register nobody
    can trace back to the sentence a claim came from.

    Since the 2026-11-25 ruling a source may name a symbol, a heading or a
    changelog bullet's bold title instead of a line, and the CHECKER verifies
    that the named thing is really there - so the migrated rows are proved here
    in the required `backend` job as well as by `tools/check_claims.py`."""
    bad = source_problems(data_rows(REGISTER.read_text(encoding="utf-8")))
    check("every source is a file and a line inside it, or a symbol, heading or "
          "changelog title that file really has", not bad, bad)


def t_a_source_may_name_a_decisions_fragment():
    """The record is two places now (2026-10-28), and a source may point at
    either: a fragment is a real file with real lines until it is rolled."""
    root = Path(tempfile.mkdtemp(prefix="claims-fragment-source-"))
    (root / DECISION_FRAGMENTS).mkdir()
    (root / DECISION_FRAGMENTS / "2026-10-28-only-a-fragment.md").write_text(
        "- **2026-10-28 \u2014 Only a fragment:** one.\n\nmore prose on a "
        "second paragraph.\n", encoding="utf-8")
    good = {"id": "S1", "source": "decisions.d/2026-10-28-only-a-fragment.md:1"}
    late = {"id": "S2", "source": "decisions.d/2026-10-28-only-a-fragment.md:9"}
    gone = {"id": "S3", "source": "decisions.d/2026-10-27-rolled-away.md:1"}
    check("a source that names a fragment in the tree is accepted",
          source_problems([good], root) == [], source_problems([good], root))
    past = source_problems([late], root)
    check("a source past the end of its fragment is reported",
          len(past) == 1 and "past the end" in past[0], past)
    rolled = source_problems([gone], root)
    check("a source that names a rolled-away fragment says to cite the record",
          len(rolled) == 1 and "cite the record instead" in rolled[0]
          and DECISION_RECORD in rolled[0], rolled)


def t_a_source_may_name_a_symbol_or_a_heading():
    """Architect ruling A (2026-11-25): a citation can name a declaration or a
    heading, and the checker verifies the named thing is really in the file -
    so a renamed function or a reworded heading is caught, instead of a line
    number quietly pointing at somebody else's sentence."""
    root = Path(tempfile.mkdtemp(prefix="claims-citation-"))
    (root / "mod.py").write_text(
        "def present():\n    return 1\n\n\nclass PresentThing:\n    pass\n",
        encoding="utf-8")
    (root / "doc.md").write_text(
        "# A document\n\n## The heading a claim cites\n\nWords.\n", encoding="utf-8")
    good = [
        {"id": "S1", "source": "mod.py::present"},
        {"id": "S2", "source": "mod.py::PresentThing"},
        {"id": "S3", "source": "doc.md#The heading a claim cites"},
    ]
    check("a source may name a declaration and a heading the file really has",
          source_problems(good, root) == [], source_problems(good, root))
    check("... a heading is matched case-insensitively",
          source_problems([{"id": "S4", "source": "doc.md#the HEADING a claim cites"}],
                          root) == [],
          source_problems([{"id": "S4", "source": "doc.md#the HEADING a claim cites"}], root))
    missing = source_problems([{"id": "S5", "source": "mod.py::gone"}], root)
    check("a source naming a symbol that is not declared is reported",
          len(missing) == 1 and "not declared" in missing[0], missing)
    missing = source_problems([{"id": "S6", "source": "doc.md#A heading now gone"}], root)
    check("a source naming a heading that is not there is reported",
          len(missing) == 1 and "no heading" in missing[0], missing)
    missing = source_problems([{"id": "S7", "source": "gone.py::present"}], root)
    check("a source naming a file that is not there is still reported",
          len(missing) == 1 and "not a file" in missing[0], missing)
    # The bite: the same citation passes, then the declaration is removed and
    # the SAME row fails. A form that cannot fail verifies nothing.
    (root / "mod.py").write_text("def something_else():\n    pass\n", encoding="utf-8")
    bite = source_problems([{"id": "S8", "source": "mod.py::present"}], root)
    check("... and a declaration that was removed makes the same source fail",
          len(bite) == 1 and "not declared" in bite[0], bite)


def t_a_symbol_row_bites_on_a_temp_repository():
    """The `symbol:` CHECK, end to end through the checker in a throwaway
    repository: it passes while the declaration or heading is there and fails
    the moment it is gone. The source names a DIFFERENT, still-present symbol,
    so the failure is the check's own and cannot be the citation's."""
    root = Path(tempfile.mkdtemp(prefix="claims-symbol-repo-"))
    (root / "mod.py").write_text(
        "def present():\n    return 1\n\n\nclass PresentThing:\n    pass\n",
        encoding="utf-8")
    (root / "doc.md").write_text(
        "# A document\n\n## The heading the claim cites\n\nWords.\n", encoding="utf-8")
    register = root / "CLAIMS.tsv"

    def one(check, source="mod.py::present"):
        register.write_text(
            HEADER + f"S1\ta symbol claim\t{check}\tbuilt\t{source}\n",
            encoding="utf-8")
        return run("--repo", str(root), str(register))

    code, out = one("symbol:mod.py::present")
    check("a `symbol:` row passes when the declaration is there", code == 0, out)
    code, out = one("symbol:mod.py::absent")
    check("... and FAILS when the symbol is not declared",
          code == 1 and "not declared" in out, out)
    code, out = one("symbol:doc.md#The heading the claim cites")
    check("a `symbol:` heading row passes when the heading is there", code == 0, out)
    code, out = one("symbol:doc.md#The heading the claim cites".replace(
        "The heading", "the HEADING"))
    check("... matched case-insensitively", code == 0, out)
    code, out = one("symbol:doc.md#A heading that is gone")
    check("... and FAILS when the heading is gone",
          code == 1 and "no heading" in out, out)
    (root / "mod.py").write_text("def something_else():\n    pass\n", encoding="utf-8")
    code, out = one("symbol:mod.py::present", source="mod.py::something_else")
    check("... and the same row FAILS once the declaration is removed", code == 1, out)


def t_a_source_may_name_a_changelog_bullet():
    """A rolled changelog bullet has NO heading and NO declaration, so neither
    `doc.md#heading` nor `path::symbol` can name it - which is why the twelve
    rows this migrated kept a bare line number after the 2026-11-25 sweep
    (2026-11-25). Its own bold title can, and the checker verifies the bullet is
    really there, so a reworded or removed title fails instead of leaving a
    citation that points at somebody else's entry."""
    root = Path(tempfile.mkdtemp(prefix="claims-changelog-source-"))
    (root / "CHANGELOG.md").write_text(
        "## Not in a numbered version yet\n"
        "\n"
        "- **The phone's Galaxy gets a read-only \"at a glance\" band "
        "(2026-10-23).** What changed.\n"
        "- **A title that wraps across the line break,\n"
        "  and still names itself (2026-10-22).** Prose.\n"
        "- **The serve decision #814 landed on the server (2026-10-25).** "
        "Prose.\n"
        "- A bullet with **a bold phrase in the middle** of its prose.\n",
        encoding="utf-8")
    good = [
        {"id": "S1", "source": 'changelog:"The phone\'s Galaxy gets a read-only '
                               '"at a glance" band (2026-10-23)."'},
        {"id": "S2", "source": 'changelog:"A title that wraps across the line '
                               'break, and still names itself (2026-10-22)."'},
        # A `#` inside the title is part of the TITLE, not the heading form -
        # this passes only because the changelog form is read first.
        {"id": "S3", "source": 'changelog:"The serve decision #814 landed on the '
                               'server (2026-10-25)."'},
    ]
    check("a source may name a changelog bullet by its own bold title - quotes, "
          "a wrapped line and a `#` inside the title all keep working",
          source_problems(good, root) == [], source_problems(good, root))
    missing = source_problems(
        [{"id": "S4", "source": 'changelog:"The phone\'s Galaxy gets a read-only '
                                '"At a glance" band (2026-10-23)."'}], root)
    check("a title whose CASE changed is reported - 'the exact bold title'",
          len(missing) == 1 and "no bullet" in missing[0], missing)
    missing = source_problems(
        [{"id": "S5", "source": 'changelog:"A band about a Galaxy (2026-10-23)."'}], root)
    check("a title that is not there is reported",
          len(missing) == 1 and "no bullet" in missing[0], missing)
    missing = source_problems(
        [{"id": "S6", "source": 'changelog:"a bold phrase in the middle"'}], root)
    check("a bold phrase in the middle of a bullet's prose is NOT a title",
          len(missing) == 1 and "no bullet" in missing[0], missing)
    missing = source_problems(
        [{"id": "S7", "source": 'changelog:The phone\'s Galaxy'}], root)
    check("an UNQUOTED title is refused rather than half-matched",
          len(missing) == 1 and "QUOTED" in missing[0], missing)
    # The bite: the same citation passes, then the bullet's title is reworded
    # and the SAME row fails.
    (root / "CHANGELOG.md").write_text(
        "- **The phone's Galaxy gets a read-only \"at a glance\" strip "
        "(2026-10-23).** What changed.\n", encoding="utf-8")
    bite = source_problems(good[:1], root)
    check("... and a title reworded above the citation makes the same source fail",
          len(bite) == 1 and "no bullet" in bite[0], bite)


def t_a_changelog_row_bites_on_a_temp_repository():
    """The `changelog:` CHECK, end to end through the checker in a throwaway
    repository: it passes while the bold title is there and fails the moment it
    is reworded. The source is an ordinary line into the same file, so the
    failure is the CHECK's own and cannot be the citation's."""
    root = Path(tempfile.mkdtemp(prefix="claims-changelog-repo-"))
    (root / "CHANGELOG.md").write_text(
        "## Not in a numbered version yet\n\n"
        "- **A bullet a claim can cite (2026-11-25).** Prose.\n",
        encoding="utf-8")
    register = root / "CLAIMS.tsv"

    def one(kind, title, source="CHANGELOG.md:1"):
        register.write_text(
            HEADER + f"S1\ta changelog claim\t{kind}:\"{title}\"\tbuilt\t"
                     f"{source}\n", encoding="utf-8")
        return run("--repo", str(root), str(register))

    code, out = one("changelog", "A bullet a claim can cite (2026-11-25).")
    check("a `changelog:` row passes when the bold title is there", code == 0, out)
    code, out = one("changelog", "A bullet a claim cannot cite (2026-11-25).")
    check("... and FAILS when no bullet carries that title",
          code == 1 and "no bullet" in out, out)
    (root / "CHANGELOG.md").write_text(
        "- **A bullet a claim can cite, reworded (2026-11-25).** Prose.\n",
        encoding="utf-8")
    code, out = one("changelog", "A bullet a claim can cite (2026-11-25).")
    check("... and the same row FAILS once the title is reworded", code == 1, out)


def t_the_about_generator_accepts_the_durable_kinds():
    """`tools/gen_about_claims.py` counts the register through the checker's own
    `read_register`, so a `symbol:` or `changelog:` row must count like any
    other - and a symbol/heading/changelog SOURCE must not make the About page
    unreadable. The rulings name this tool, so it is proved here rather than
    assumed."""
    tools = REPO / "tools"
    sys.path.insert(0, str(tools))
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "gen_about_claims_probe", tools / "gen_about_claims.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    path = register_with(
        "S1\ta symbol row is counted\tsymbol:backend/jarvis_agent.py::with_manner_note"
        "\tbuilt\tbackend/jarvis_agent.py::with_manner_note\n"
        "S2\ta changelog row is counted\t"
        'changelog:"Cloud in the Presets menu, and one switch that lets Jarvis '
        'escalate without asking first (2026-10-27)."'
        "\tbuilt\t"
        'changelog:"Cloud in the Presets menu, and one switch that lets Jarvis '
        'escalate without asking first (2026-10-27)."\n')
    values = module.counts(Path(path))
    check("gen_about_claims counts the durable kinds and their sources",
          values == {"rows": 2, "built": 2, "open": 0, "unverifiable": 0}, values)



def t_the_record_grep_is_answered_by_both_places():
    """End to end, in a throwaway `--repo`: the decision record is
    `docs/DECISIONS.md` plus the fragments not yet rolled into it, so a row that
    greps the record sees a decision the day it is written - and an `absent:`
    row notices when the sentence comes back as a fragment."""
    root = Path(tempfile.mkdtemp(prefix="claims-record-"))
    (root / "docs").mkdir()
    (root / DECISION_FRAGMENTS).mkdir()
    (root / "docs" / "DECISIONS.md").write_text(
        "# The record\n\nonly the rolled text is here.\n", encoding="utf-8")
    (root / DECISION_FRAGMENTS / "2026-10-28-only-a-fragment.md").write_text(
        "- **2026-10-28 \u2014 Only a fragment:** this sentence is nowhere "
        "else.\n", encoding="utf-8")
    register = root / "docs" / "CLAIMS.tsv"
    register.write_text(
        HEADER
        + "R1\ta decision written as a fragment is evidence the day it is "
          "written\tgrep:docs/DECISIONS.md:this sentence is nowhere else\t"
          "built\tdecisions.d/2026-10-28-only-a-fragment.md:1\n",
        encoding="utf-8")
    code, out = run("--repo", str(root), str(register), "--list")
    check("a `grep:` on the record finds a sentence that lives only in a fragment",
          code == 0 and "is at decisions.d/" in out, out)
    register.write_text(
        HEADER
        + "R2\tthe sentence is supposed to be gone from the record\t"
          "absent:docs/DECISIONS.md:this sentence is nowhere else\t"
          "built\tdecisions.d/2026-10-28-only-a-fragment.md:1\n",
        encoding="utf-8")
    code, out = run("--repo", str(root), str(register), "--list")
    check("an `absent:` on the record FAILS when the sentence comes back in a "
          "fragment", code == 1, out)
    check("... and names the fragment it came back in",
          "decisions.d/2026-10-28-only-a-fragment.md" in out, out)


# ---------------------------------------------------------------------------
#   The About page's six copies of the register's totals
# ---------------------------------------------------------------------------

#: Every place `docs/ABOUT-JARVIS.md` prints the register's own totals, with
#: which figure each capture holds. The truth is never restated here - it is
#: counted from `docs/CLAIMS.tsv` on every run - so this check follows the
#: register instead of becoming a seventh stale copy of it. A checker holding
#: 131/101 would go red on a merge that merely removed one row (PR #462 does);
#: this one goes red only when the PAGE is out of date, which is the thing
#: being checked.
ABOUT_COUNT_SPOTS = (
    ("the row count beside the register's name",
     r"\(`docs/CLAIMS\.tsv`, (\d+) rows\)",
     ("rows",)),
    ("the sentence spelling out all four totals",
     r"\*\*(\d+) claims: (\d+) built, (\d+) still open, (\d+) unverifiable\*\*",
     ("rows", "built", "open", "unverifiable")),
    ("the section 5 sentence about what is still open",
     r"(\d+) of the (\d+) claims in `docs/CLAIMS\.tsv` are still marked open",
     ("open", "rows")),
    ("the section 6 table row for the register",
     r"\*\*(\d+) rows\*\*, (\d+) built / (\d+) open / (\d+) unverifiable",
     ("rows", "built", "open", "unverifiable")),
    ("the quoted output of the checker itself",
     # `tools/check_claims.py` prints the summary line with its own closing
     # words - "... 8 unverifiable (the reason is in each row)." - so a page
     # that quotes the checker verbatim ends its backtick after that
     # parenthetical, not after "unverifiable". Both the full quotation and the
     # older abbreviated one are the same line, and the test's own docstring
     # says a reworded page is re-anchored rather than allowed to stop looking;
     # anything else still fails.
     r"`(\d+) claim\(s\) checked [^`]*?(\d+) built, (\d+) still open, "
     r"(\d+) unverifiable(?: \(the reason is in each row\)\.)?`",
     ("rows", "built", "open", "unverifiable")),
    ("the honest caution about unverifiable rows",
     r"(\d+) of the (\d+) rows are `unverifiable`",
     ("unverifiable", "rows")),
)


def t_the_about_page_quotes_the_register_it_describes():
    """`docs/ABOUT-JARVIS.md` prints the register's totals in six places, and
    all six were stale when this check was written: the page said 127 rows,
    128 claims and 98 built against a register of 131 rows, 131 claims and
    101 built (measured on 6db0df06, 2026-10-15).

    The totals are counted here from `docs/CLAIMS.tsv`, never written down a
    second time, so this check follows the register. It fails when the page is
    out of date - which is the point, and is why a merge that changes the
    register must carry the page's own update with it - and it also fails when
    a pattern stops matching at all, so a page reworded until this check can no
    longer see it has to be re-anchored rather than passing because it stopped
    looking.
    """
    page = REPO / "docs" / "ABOUT-JARVIS.md"
    check("docs/ABOUT-JARVIS.md is there to be checked", page.is_file(), page)
    if not page.is_file():
        return
    rows = data_rows(REGISTER.read_text(encoding="utf-8"))
    measured = {"rows": len(rows)}
    for state in ("built", "open", "unverifiable"):
        measured[state] = sum(1 for row in rows if row["state"] == state)
    check("the register's three states add up to its rows",
          measured["built"] + measured["open"] + measured["unverifiable"]
          == measured["rows"], measured)

    flat = " ".join(page.read_text(encoding="utf-8").split())
    for name, pattern, fields in ABOUT_COUNT_SPOTS:
        wanted = tuple(measured[field] for field in fields)
        found = re.search(pattern, flat)
        got = tuple(int(g) for g in found.groups()) if found else None
        says = ", ".join(f"{field}={measured[field]}" for field in fields)
        check(f"the About page quotes the register's real {says} at {name}",
              got == wanted,
              f"the page says {got}, docs/CLAIMS.tsv holds {wanted}"
              if found else
              f"nothing on the page matches {pattern!r} any more - re-anchor "
              f"this check when the page is reworded; do not let it stop "
              f"looking")


# ---------------------------------------------------------------------------
#   Direction 1: a `built` row that stopped holding
# ---------------------------------------------------------------------------

def t_a_built_row_that_stopped_holding_fails():
    path = register_with(
        "X1\tthis sentence is not in the project at all\t"
        "grep:CLAUDE.md:a sentence that was never written\tbuilt\tCLAUDE.md:1\n")
    code, out = run(str(path))
    check("a `built` row whose check fails exits 1", code == 1, out)
    check("... and says the claim no longer holds", "no longer holds" in out, out)
    check("... and names the row and where it came from",
          "X1" in out and "CLAUDE.md:1" in out, out)


# ---------------------------------------------------------------------------
#   Direction 2: an `open` row whose gap closed - the whole point
# ---------------------------------------------------------------------------

def t_an_open_row_whose_gap_closed_fails():
    path = register_with(
        "X2\tthis gap is claimed open but the file is right there\t"
        "file:backend/jarvis_tidy.py\topen\tCLAUDE.md:1\n")
    code, out = run(str(path))
    check("an `open` row whose check PASSES exits 1", code == 1, out)
    check("... and says the gap closed and the register is stale",
          "gap closed" in out and "stale" in out, out)
    check("... and names the row", "X2" in out, out)


def t_an_open_row_that_is_still_open_is_green():
    path = register_with(
        "X3\ta gap that is still a gap\tgrep:tools:reads original text\t"
        "open\tCLAUDE.md:1\n")
    code, out = run(str(path))
    check("an `open` row whose check still fails exits 0 - the direction must "
          "not fire on a real gap", code == 0, out)


# ---------------------------------------------------------------------------
#   A register the check cannot read whole
# ---------------------------------------------------------------------------

def t_a_row_with_too_few_columns_is_refused():
    path = register_with("X4\tmissing the source\tfile:CLAUDE.md\tbuilt\n")
    code, out = run(str(path))
    check("a row with the wrong number of columns exits 1", code == 1, out)
    check("... and says how many it found and how many it wanted",
          "column" in out and "5" in out, out)


def t_a_check_kind_nobody_knows_is_refused():
    path = register_with("X5\tan invented kind\tfuzzy:CLAUDE.md:something\t"
                         "built\tCLAUDE.md:1\n")
    code, out = run(str(path))
    check("a check kind outside the vocabulary exits 1", code == 1, out)
    # Each kind by name. The old assertion looked for one contiguous phrase and
    # was satisfied by "no-file, grep" containing "file, grep" - it never named
    # all of them, and it would not have noticed a kind missing from the list.
    check("... and names every kind that is allowed",
          all(kind in out for kind in ("file", "no-file", "grep", "absent",
                                       "test", "number", "symbol",
                                       "changelog")), out)


def t_an_unknown_state_is_refused():
    path = register_with("X6\ta state nobody defined\tfile:CLAUDE.md\tmostly\t"
                         "CLAUDE.md:1\n")
    code, out = run(str(path))
    check("an unknown state exits 1", code == 1, out)
    check("... and says which states exist", "built, open, unverifiable" in out, out)


def t_a_duplicated_id_is_refused():
    path = register_with("X7\tfirst\tfile:CLAUDE.md\tbuilt\tCLAUDE.md:1\n"
                         "X7\tsecond\tfile:CLAUDE.md\tbuilt\tCLAUDE.md:1\n")
    code, out = run(str(path))
    check("a duplicated id exits 1", code == 1, out)
    check("... and says where the id was first used", "already used" in out, out)


def t_an_unverifiable_row_may_not_name_a_check():
    path = register_with("X8\tsomething still to do\tgrep:tools:a marker\t"
                         "unverifiable\tCLAUDE.md:1\n")
    code, out = run(str(path))
    check("an `unverifiable` row whose reason is a definite check exits 1",
          code == 1, out)
    check("... and says a definite check means the row is not unverifiable",
          "unverifiable only when NO definite check exists" in out, out)


def t_an_unverifiable_row_with_a_reason_is_green():
    path = register_with("X9\tsomething nobody can check yet\t"
                         "no definite check: the queue does not say what would "
                         "mark this built\tunverifiable\tCLAUDE.md:1\n")
    code, out = run(str(path))
    check("an `unverifiable` row with a reason exits 0 and is NOT verified",
          code == 0 and "unverifiable" in out, out)


def t_an_empty_register_is_not_a_pass():
    path = register_with("")
    code, out = run(str(path))
    check("a register with no rows exits 1", code == 1, out)
    check("... and says it would have passed having checked nothing",
          "checked nothing" in out, out)


def t_a_no_file_row_answers_both_ways():
    """`no-file:` is `file:`'s mirror, added 2026-10-05 for a real claim the
    first register could not write down: `docs/README.md` records the source
    bundle as removed while the file is still tracked. The test proves both
    answers on throwaway registers, and that removing the kind breaks it: an
    unknown kind exits 1 with the vocabulary in the message, so the "gone"
    case below would fail rather than pass quietly.
    """
    path = register_with(
        "X10\tthis file was supposed to be deleted and was\t"
        "no-file:docs/no-such-file-in-this-repo.md\tbuilt\tCLAUDE.md:1\n")
    code, out = run(str(path))
    check("a `no-file:` row for a file that really is gone exits 0", code == 0, out)
    path = register_with(
        "X11\tthis file was supposed to be deleted and was not\t"
        "no-file:backend/jarvis_tidy.py\tbuilt\tCLAUDE.md:1\n")
    code, out = run(str(path))
    check("a `no-file:` row for a file that is still there exits 1", code == 1, out)
    check("... and says the file is still there",
          "is still there" in out, out)


def t_a_missing_register_is_not_a_pass():
    code, out = run(str(REPO / "docs" / "no-such-register.tsv"))
    check("a register that is not there exits 1", code == 1, out)
    check("... and never falls back to the real one",
          "does not exist" in out, out)


def t_every_kind_all_answers_on_a_real_row():
    """One live row per kind, so a kind that stopped working is caught here and
    not by the register going red for a reason nobody can read.

    `symbol:` is the seventh kind (architect ruling A, 2026-11-25): its live row
    names a declaration `backend/jarvis_agent.py` really carries, so the kind is
    proved against the tree a run actually reads, not only against a fixture.
    `changelog:` is the eighth (2026-11-25), and its live row names a rolled
    CHANGELOG.md bullet by its bold title - one of the twelve sources this same
    change migrated, so a reworded title is caught here as well as by the
    register.

    The `test:` row points at a throwaway suite rather than at a real one: a
    real suite can need packages this container has not installed, and pointing
    it at THIS file would run this file again, for ever. It prints one real pass
    in its own summary, because since 2026-11-18 a suite that exits 0 having
    PASSED NOTHING is not proof - the zero-check rule would (correctly) fail a
    fixture that reported no check, and this row is about the `test:` KIND
    answering at all, not about the zero rule (which has its own tests below).
    """
    suite = Path(tempfile.mkstemp(suffix=".py")[1])
    suite.write_text("import sys\n"
                     "print('ok  a throwaway check')\n"
                     "print('1 passed, 0 skipped, 0 failed')\n"
                     "sys.exit(0)\n",
                     encoding="utf-8")
    rows = {
        "file": "file:backend/jarvis_tidy.py",
        # The live rows point at the file that really holds the text: the owner's
        # dated decisions moved out of CLAUDE.md into docs/DECISIONS.md on
        # 2026-10-12 ("Owner decisions recorded" and the 60,000 shader budget are
        # both in the record now), so a probe left on CLAUDE.md would fail for a
        # reason that has nothing to do with the checker.
        "grep": "grep:docs/DECISIONS.md:Owner decisions recorded",
        "absent": "absent:CLAUDE.md:a sentence that was never written",
        "test": f"test:{suite}",
        "number": "number:docs/DECISIONS.md:tools/shader_size.py:60,000",
        "symbol": "symbol:backend/jarvis_agent.py::with_manner_note",
        "changelog": 'changelog:"Cloud in the Presets menu, and one switch that '
                     'lets Jarvis escalate without asking first (2026-10-27)."',
    }
    for name, expr in rows.items():
        path = register_with(f"K-{name}\ta live {name} check\t{expr}\tbuilt\tCLAUDE.md:1\n")
        code, out = run(str(path))
        check(f"a live `{name}:` row passes", code == 0, out)


# ---------------------------------------------------------------------------
#   A `test:` row cannot be proven by a suite that skipped its substance
# ---------------------------------------------------------------------------

#: The skip `backend/test_data_backup.py` really prints when the NordLocker
#: guard is absent - the line claim F11 could not hear before 2026-10-24. Kept
#: as the suite prints it, so a reworded reason is a visible test change rather
#: than a quiet widening of what this checker accepts.
SKIPPED_GUARD = (
    "skip  a NordLocker locker destination is refused - this build of the tool "
    "has no refuse_write_into_a_locker - the guard is not in this tree, so "
    "there is nothing to check")


def fake_suite(body: str) -> Path:
    """A throwaway suite in the temp folder that prints `body` and exits 0.

    It sits outside the repository on purpose: the environment-skip allow-list
    is keyed by repo-relative suite path, so this one is judged strictly and can
    be proven only by a clean run.
    """
    suite = Path(tempfile.mkstemp(suffix=".py")[1])
    suite.write_text("import sys\n" + body + "\nsys.exit(0)\n", encoding="utf-8")
    return suite


def t_a_skipped_substance_is_not_proof():
    """The bite: exit 0, and the suite says out loud that it skipped the guard."""
    suite = fake_suite(
        f"print({SKIPPED_GUARD!r})\nprint('')\n"
        "print('1 passed, 1 skipped, 0 failed')")
    path = register_with(
        f"X12\tthe backup refuses a locker\ttest:{suite}\tbuilt\tCLAUDE.md:1\n")
    code, out = run(str(path))
    check("a `built` row whose suite exits 0 after skipping the guard exits 1",
          code == 1, out)
    check("... and says the suite exited 0 but SKIPPED",
          "exited 0 but SKIPPED" in out, out)
    check("... and quotes the skip line, naming the absent guard",
          "a NordLocker locker destination is refused" in out
          and "refuse_write_into_a_locker" in out, out)
    check("... and never prints the happy 'still holds' line",
          "still holds" not in out, out)


def t_a_clean_suite_still_proves_a_row():
    """The companion: nothing skipped, the row is proven exactly as before."""
    suite = fake_suite(
        "print('a clean suite')\nprint('3 passed, 0 skipped, 0 failed')")
    path = register_with(
        f"X13\ta claim a clean suite proves\ttest:{suite}\tbuilt\tCLAUDE.md:1\n")
    code, out = run(str(path))
    check("a `built` row whose suite exits 0 with no skip still exits 0",
          code == 0, out)
    check("... and is counted as built, not withheld", "1 built" in out, out)


def t_a_skip_count_with_no_reason_is_not_proof():
    """A suite's own summary can out a skip the marker scan could not read."""
    suite = fake_suite("print('1 passed, 1 skipped, 0 failed')")
    path = register_with(
        f"X14\ta claim a summary says was skipped\ttest:{suite}\tbuilt\t"
        f"CLAUDE.md:1\n")
    code, out = run(str(path))
    check("a `built` row whose suite reports a skip it did not itemise exits 1",
          code == 1, out)
    check("... and says how many were reported and how many could be read",
          "1 skipped check(s) according to its own summary" in out, out)



def t_the_skip_allow_list_is_keyed_to_the_suite_that_needs_it():
    """The bounded half, tested directly: the same `icacls` reason is a machine
    limit for the suite whose fixture needs it, and no excuse for another
    suite's row. Without the keying, a substantive skip could hide behind an
    environment phrase in a suite nobody measured."""
    sys.path.insert(0, str(REPO / "tools"))
    import check_claims

    icacls = ("skip  a directory whose Windows permissions really refuse a write "
              "- making one needs icacls and this account's own name\n"
              "1 passed, 1 skipped, 0 failed")
    check("an `icacls` environment skip leaves its own suite's row proven",
          check_claims.skip_that_withholds_proof(
              "backend/test_data_backup.py", icacls) is None, icacls)
    check("... the same line proves nothing for a suite that never needed it",
          check_claims.skip_that_withholds_proof(
              "backend/test_api_doc.py", icacls) is not None, icacls)
    check("... and the missing-guard skip is never allowed, even for its own "
          "suite",
          check_claims.skip_that_withholds_proof(
              "backend/test_data_backup.py",
              SKIPPED_GUARD + "\n1 passed, 1 skipped, 0 failed") is not None)
    # The two reasons that only appear on a machine unlike this one: no
    # cryptography installed, and an OS where os.name is not nt. Neither can be
    # reached on the owner's Windows PC, so pinning the exact text here is the
    # only thing that stops a reworded skip silently reddening the audit job.
    crypto = ("skip  a sealed snapshot round trips - the `cryptography` package "
              "is not installed")
    check("... a missing package's skip is a machine limit for its own suite",
          check_claims.skip_that_withholds_proof(
              "backend/test_data_backup.py", crypto) is None, crypto)
    platform = ("skip  the other-drive note - it is a Windows question; "
                "os.name is not nt")
    check("... a platform's skip is a machine limit for its own suite",
          check_claims.skip_that_withholds_proof(
              "backend/test_data_backup.py", platform) is None, platform)
    # `test_settings_tool` prints `SKIP  <name>` and indents the reason under
    # it, so a parser that reads only the marker line would lose the reason and
    # red F01 wherever a setter's module is not importable.
    settings = ("SKIP  a switch's setter imports jarvis_x\n"
                "        not importable in this environment")
    check("... an indented reason under a SKIP marker is read, not lost",
          check_claims.skip_that_withholds_proof(
              "backend/test_settings_tool.py", settings) is None, settings)


#: The skip `backend/test_owner_check.py` really prints on Windows, measured
#: 2026-11-13, kept exactly as the suite prints it - the word `skip`, then TWO
#: spaces, then the suite's own reason. The suite skips the one check it cannot
#: run on Windows: it proves "off Windows there is no Windows Hello, so a risky
#: approval fails closed" by driving the REAL path, and on Windows that path
#: raises a real Windows Hello prompt, which no test may do. Pinned here so a
#: reworded reason is a visible test change rather than a quiet widening of what
#: the checker accepts.
OWNER_CHECK_SKIP = (
    "skip  off Windows there is no Windows Hello so a risky approval fails "
    "closed: on Windows the real check would raise a real prompt, so this test "
    "does not run it. It did NOT run, and it did NOT pass.")


def t_the_owner_check_skip_is_named_and_not_counted_as_a_pass():
    """C163 read red at the owner's desk (2026-11-13) because one machine-limit
    skip withheld the row's proof. The entry that fixes it must accept the reason
    the suite really prints - and an accepted skip must still be named and
    counted, never read as a pass."""
    sys.path.insert(0, str(REPO / "tools"))
    import check_claims

    suite = REPO / "backend" / "test_owner_check.py"
    # The suite's own source, with adjacent string literals joined the way Python
    # joins them, so this pin is the text a reader of the source sees and not a
    # copy of the output that could drift from it.
    source = " ".join(re.sub(r'"\s*\n\s*"', "",
                             suite.read_text(encoding="utf-8")).split())
    reason = " ".join(OWNER_CHECK_SKIP.split())[len("skip "):]
    check("the skip this test pins is what backend/test_owner_check.py prints",
          reason in source,
          "the suite no longer prints the pinned reason - change this pin and "
          "ENVIRONMENT_SKIPS together")
    check("the entry is in ENVIRONMENT_SKIPS, keyed to that one suite",
          "backend/test_owner_check.py" in check_claims.ENVIRONMENT_SKIPS,
          sorted(check_claims.ENVIRONMENT_SKIPS))
    check("... and it accepts the reason the suite really prints, so C163 is "
          "proven again", check_claims.skip_that_withholds_proof(
              "backend/test_owner_check.py", OWNER_CHECK_SKIP) is None,
          OWNER_CHECK_SKIP)
    check("... while the same skip proves nothing for a suite that never needed "
          "it, so the allow-list is still keyed to one suite",
          check_claims.skip_that_withholds_proof(
              "backend/test_api_doc.py", OWNER_CHECK_SKIP) is not None,
          OWNER_CHECK_SKIP)
    # End to end on a PLAIN run (`-v` not typed), because a skip a reader only
    # sees with `-v` is exactly the silence this test exists to stop. The suite
    # sits in a throwaway `--repo` under the same repo-relative path, because
    # that path is what the allow-list is keyed by - so the REAL entry is what
    # accepts it, and removing the entry reddens this row.
    fake_repo = Path(tempfile.mkdtemp(prefix="claims-owner-check-"))
    (fake_repo / "backend").mkdir()
    # The register's `source` is `CLAUDE.md:1`, and since the 2026-11-25 ruling
    # the checker verifies every source against the repository it judges - so a
    # throwaway `--repo` must carry the file its register cites, exactly as a
    # real copy of the repository would.
    (fake_repo / "CLAUDE.md").write_text("# CLAUDE.md\n", encoding="utf-8")
    (fake_repo / "backend" / "test_owner_check.py").write_text(
        f"print({OWNER_CHECK_SKIP!r})\n"
        f"print('252 passed, 1 skipped, 0 failed')\n", encoding="utf-8")
    path = register_with(
        "C163\tthe tool-switch approval card works on the phone too\t"
        "test:backend/test_owner_check.py\tbuilt\tCLAUDE.md:1\n")
    code, out = run("--repo", str(fake_repo), str(path))
    check("a row whose only suite skipped a machine-limit check still exits 0, "
          "so the desk is not red for a limit of the machine", code == 0,
          out[-1200:])
    check("... and the plain run NAMES the suite it skipped",
          "backend/test_owner_check.py" in out, out[-1200:])
    check("... quotes the skip's own reason, so a reader can judge it",
          "on Windows the real check would raise a real prompt" in out,
          out[-1200:])
    check("... and counts the row that was NOT looked at by that check",
          "1 claim row(s) name a suite that SKIPPED" in out and "C163" in out,
          out[-1200:])
    check("... and says out loud that the skipped check is NOT a pass",
          "NOT counted as a pass" in out, out[-1200:])

# ---------------------------------------------------------------------------
#   A `test:` row cannot be proven by a suite that PASSED NOTHING (2026-11-18)
# ---------------------------------------------------------------------------
# The skip rule above reads the skips a suite PRINTS. A suite that exits 0
# having run no check at all prints no skip either, so before this rule it was
# indistinguishable from one that verified the claim - the one hole the register
# exists to keep shut. backend/run_suites.py already failed this shape
# everywhere it runs a suite (2026-10-27); the claims checker is the caller that
# rule never reached.

def t_a_suite_that_passed_nothing_is_not_proof():
    """The bite, in the two shapes a suite can pass nothing: it prints its own
    zero summary, or it prints nothing at all. Both exited 0 and both read as
    proven before 2026-11-18."""
    for label, body in (
            ("prints a zero summary",
             "print('0 passed, 0 skipped, 0 failed')"),
            ("prints nothing at all",
             "print('a suite whose checks all vanished')")):
        suite = fake_suite(body)
        path = register_with(
            f"X18\ta claim an empty suite cannot prove\ttest:{suite}\tbuilt\t"
            f"CLAUDE.md:1\n")
        code, out = run(str(path))
        check(f"a `built` row whose suite exits 0 having passed NOTHING "
              f"({label}) exits 1", code == 1, out)
        check(f"... and names the suite ({label})", str(suite) in out, out)
        check(f"... and says it PASSED NOTHING, with the counts it reported "
              f"({label})", "PASSED NOTHING" in out
              and "0 passed, 0 skipped, 0 failed" in out, out)
        check(f"... and gives the first legitimate fix: make the suite run a "
              f"check ({label})", "make the suite run a check" in out, out)
        check(f"... and the second: record the environment skip, with its "
              f"reason and the date ({label})",
              "record the environment skip" in out
              and "reason and the date" in out
              and "ENVIRONMENT_SKIPS" in out, out)
        check(f"... and never prints the happy 'still holds' line ({label})",
              "still holds" not in out, out)


def t_a_documented_environment_skip_is_the_zero_check_exemption():
    """The ruling's other half, end to end through the REAL allow-list.

    The fixture lives at a repo-relative path the allow-list is keyed to, inside
    a throwaway `--repo`, so this proves the checker's own `ENVIRONMENT_SKIPS`
    entry is what excuses a suite that passed nothing - without touching the real
    tree.

    Three cases, and the third is the boundary: an entry excuses a suite that
    PRINTED the skip it covers, never a suite that printed nothing. An entry
    records why a skip happened; it cannot document a skip that never happened.
    """
    fake_repo = Path(tempfile.mkdtemp(prefix="claims-zero-guard-"))
    (fake_repo / "backend").mkdir()
    # Same reason as the owner-check fake repository above: a `--repo` copy is
    # judged whole, citations included, so it carries the file its rows cite.
    (fake_repo / "CLAUDE.md").write_text("# CLAUDE.md\n", encoding="utf-8")
    suite = fake_repo / "backend" / "test_owner_check.py"

    # 1. The whole body is the documented machine-limit skip: the
    #    ENVIRONMENT_SKIPS case, not a hole, so the row stays proven.
    suite.write_text(f"print({OWNER_CHECK_SKIP!r})\n"
                     f"print('0 passed, 1 skipped, 0 failed')\n",
                     encoding="utf-8")
    path = register_with(
        "X19\ta claim proven by a whole-body documented skip\t"
        "test:backend/test_owner_check.py\tbuilt\tCLAUDE.md:1\n")
    code, out = run("--repo", str(fake_repo), str(path))
    check("a `built` row whose suite passed nothing because its whole body is a "
          "documented machine-limit skip exits 0 (the ENVIRONMENT_SKIPS case, "
          "not a hole)", code == 0, out[-1200:])
    check("... and is counted as built, not withheld", "1 built" in out,
          out[-1200:])
    check("... and the plain run still NAMES the suite and quotes the skip",
          "backend/test_owner_check.py" in out
          and "on Windows the real check would raise a real prompt" in out,
          out[-1200:])
    check("... and still says the skipped check is NOT counted as a pass",
          "NOT counted as a pass" in out, out[-1200:])

    # 2. A skip beside checks that really ran: unchanged by the zero rule.
    suite.write_text(f"print({OWNER_CHECK_SKIP!r})\n"
                     f"print('5 passed, 1 skipped, 0 failed')\n",
                     encoding="utf-8")
    code, out = run("--repo", str(fake_repo), str(path))
    check("a suite that prints a skip AND passes checks is unchanged: exits 0",
          code == 0, out[-1200:])
    check("... and its row is built", "1 built" in out, out[-1200:])

    # 3. The entry alone is not a licence for silence: the same keyed path, the
    #    same entry, and a suite that prints nothing is still not a pass.
    suite.write_text("print('a suite that skipped everything without saying "
                     "so')\n", encoding="utf-8")
    code, out = run("--repo", str(fake_repo), str(path))
    check("an ENVIRONMENT_SKIPS entry alone does NOT excuse a silent suite that "
          "passed nothing: the row exits 1", code == 1, out[-1200:])
    check("... and the message is the zero-check sentence, not a skip one",
          "PASSED NOTHING" in out and "exited 0 but SKIPPED" not in out,
          out[-1200:])


def t_the_zero_check_rule_reads_the_runners_own_parser():
    """The counts and the `passed == 0` predicate are backend/run_suites.py's,
    imported - never re-written here. Two parsers would drift, and the drift
    would decide whether a claim is proven."""
    sys.path.insert(0, str(REPO / "tools"))
    import check_claims
    sys.path.insert(0, str(REPO / "backend"))
    import run_suites

    sample = "5 passed, 2 skipped, 1 failed"
    check("the counts a claim's suite is judged by are the runner's own answer",
          check_claims.suite_counts(sample) == run_suites.counts(sample),
          (check_claims.suite_counts(sample), run_suites.counts(sample)))
    check("... and it is the runner's very function, not a copy that can drift",
          check_claims._RUNNER_COUNTS is run_suites.counts,
          check_claims._RUNNER_COUNTS)
    check("... its zero rule is the runner's: a summary with no pass is a "
          "failure", check_claims.passed_nothing(
              "backend/test_x.py", "0 passed, 0 skipped, 0 failed") is not None)
    check("... while any real pass at all proves the row",
          check_claims.passed_nothing(
              "backend/test_x.py", "1 passed, 0 skipped, 0 failed") is None)


# ---------------------------------------------------------------------------
#   What environment a `test:` row's suite is started with
# ---------------------------------------------------------------------------
# `JARVIS_BACKEND` is set for the owner's Windows account on this PC and names
# the LIVE backend folder, and `backend/_where.py` puts that folder first on
# `sys.path`. The checker used to pass the variable straight to every suite, so
# each one ran against live code: on 2026-10-25 that made the register report
# claim MED-01 as no longer holding on a `main` that was never red.
# `backend/run_suites.py:881-884` has ignored that ambient value since
# 2026-10-21. The checks below are the checker holding the same contract.

#: A value that is plainly not this checkout, so a suite printing it proves the
#: ambient variable reached the CHILD and not merely this test's own dict.
LOOKS_LIVE = r"C:\a\pretend live backend"

#: The same shape for the repository overrides (architect ruling B, 2026-11-25).
LOOKS_OTHER = r"C:\a\pretend other checkout"


def env_with_ambient(value=None):
    """This process's environment, carrying `JARVIS_BACKEND` `value` (or not).

    Built by filtering rather than by assignment so there is exactly ONE entry
    for the name: Windows treats environment names case-insensitively, and a
    dict holding both `JARVIS_BACKEND` and some other spelling of it would be a
    test of which one wins, not of the checker.
    """
    env = {key: item for key, item in os.environ.items()
           if key.upper() != "JARVIS_BACKEND"}
    if value is not None:
        env["JARVIS_BACKEND"] = value
    return env


def env_without(*names):
    """This process's environment with exactly `names` removed, in any spelling.

    Windows treats environment names case-insensitively, so filtering the whole
    name set (not just one key) means a test cannot pass because two spellings
    both happened to be present.
    """
    upper = {name.upper() for name in names}
    return {key: value for key, value in os.environ.items()
            if key.upper() not in upper}


def t_the_parser_offers_the_opt_in_flag():
    """The flag exists on the checker's OWN parser, is spelled the same word
    `backend/run_suites.py` uses, and is off unless it is typed."""
    sys.path.insert(0, str(REPO / "tools"))
    import check_claims

    parser = check_claims._parser()
    check("the checker's parser knows --use-env-backend",
          parser.parse_args(["--use-env-backend"]).use_env_backend is True)
    check("... and a run that does not type it leaves the ambient value ignored",
          parser.parse_args([]).use_env_backend is False)
    check("... spelled the same word the runner uses for the same choice",
          check_claims.USE_ENV_BACKEND_FLAG == "--use-env-backend",
          check_claims.USE_ENV_BACKEND_FLAG)
    help_text = " ".join(parser.format_help().split())
    check("... and its help says what it does, naming the live folder",
          "--use-env-backend" in help_text and "JARVIS_BACKEND" in help_text
          and "LIVE" in help_text, help_text)
    check("... and a register path still parses after the flag",
          parser.parse_args(["--use-env-backend", "some.tsv"]).register
          == "some.tsv")


def t_the_ambient_backend_variable_is_ignored_unless_asked_for():
    """The environment handed to a suite carries no `JARVIS_BACKEND` unless the
    flag asked for it; the one line names the value it ignored; and the
    process's own environment is never mutated to achieve either."""
    sys.path.insert(0, str(REPO / "tools"))
    import check_claims

    before = os.environ.get("JARVIS_BACKEND")
    os.environ["JARVIS_BACKEND"] = LOOKS_LIVE
    try:
        note = io.StringIO()
        with contextlib.redirect_stdout(note):
            ignored = check_claims._suite_env(False)
        with contextlib.redirect_stdout(io.StringIO()):
            passed_through = check_claims._suite_env(True)
        still_there = os.environ.get("JARVIS_BACKEND")
    finally:
        if before is None:
            os.environ.pop("JARVIS_BACKEND", None)
        else:
            os.environ["JARVIS_BACKEND"] = before
    check("without the flag the environment a suite is given has no "
          "JARVIS_BACKEND", "JARVIS_BACKEND" not in ignored, sorted(ignored))
    check("... and one line names the value that was ignored",
          "ignoring ambient JARVIS_BACKEND" in note.getvalue()
          and LOOKS_LIVE in note.getvalue(), note.getvalue())
    check("with the flag the value is passed through unchanged",
          passed_through.get("JARVIS_BACKEND") == LOOKS_LIVE,
          passed_through.get("JARVIS_BACKEND"))
    check("... and neither call mutates this process's own environment",
          still_there == LOOKS_LIVE, still_there)


def t_the_ambient_repository_overrides_are_ignored_unless_a_repo_is_named():
    """Architect ruling B, second half (2026-11-25): `JARVIS_REVIEW_REPO` and
    `JARVIS_DEFECT_REGISTER` are set at USER level on this PC (the first names
    the MAIN checkout) and absent in CI. A `test:` row's suite that reads them
    used to judge a different tree at the desk than on a runner. They are now
    removed unless `--repo` names the repository to judge.

    Measured before the fix, with a probe suite started by this checker from a
    worktree: it printed the main checkout's path. The same probe is what the
    end-to-end checks below drive.
    """
    sys.path.insert(0, str(REPO / "tools"))
    import check_claims

    before = {name: os.environ.get(name) for name in check_claims.AMBIENT_REPO_ENVS}
    os.environ["JARVIS_REVIEW_REPO"] = LOOKS_OTHER
    os.environ["JARVIS_DEFECT_REGISTER"] = LOOKS_OTHER + r"\docs\defect-register.tsv"
    try:
        note = io.StringIO()
        with contextlib.redirect_stdout(note):
            ignored = check_claims._suite_env(False)
        with contextlib.redirect_stdout(io.StringIO()):
            named = check_claims._suite_env(False, repo=Path(r"C:\a\named repo"))
        still = {name: os.environ.get(name) for name in check_claims.AMBIENT_REPO_ENVS}
    finally:
        for name, value in before.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
    check("without --repo the environment a suite is given carries neither "
          "ambient repository override",
          not any(name in ignored for name in check_claims.AMBIENT_REPO_ENVS),
          {k: ignored.get(k) for k in check_claims.AMBIENT_REPO_ENVS})
    check("... and one line names every value that was ignored",
          "ignoring ambient" in note.getvalue()
          and "JARVIS_REVIEW_REPO" in note.getvalue()
          and "JARVIS_DEFECT_REGISTER" in note.getvalue()
          and LOOKS_OTHER in note.getvalue(), note.getvalue())
    check("with --repo the suite is told THAT repository, not the machine's",
          named.get("JARVIS_REVIEW_REPO") == r"C:\a\named repo"
          and named.get("JARVIS_DEFECT_REGISTER")
          == str(Path(r"C:\a\named repo") / "docs" / "defect-register.tsv"),
          {k: named.get(k) for k in check_claims.AMBIENT_REPO_ENVS})
    check("... and neither call mutates this process's own environment",
          still["JARVIS_REVIEW_REPO"] == LOOKS_OTHER, still["JARVIS_REVIEW_REPO"])

    # End to end: a suite whose PASS/FAIL is decided by the variable. With the
    # ambient value set and no --repo the row still passes, so the value did not
    # change the result.
    suite = Path(tempfile.mkstemp(suffix=".py")[1])
    suite.write_text(
        "import os, sys\n"
        "print('SEEN=' + str(os.environ.get('JARVIS_REVIEW_REPO')))\n"
        "print('ok  the ambient repository value is gone')\n"
        "print('1 passed, 0 skipped, 0 failed')\n"
        "sys.exit(0 if os.environ.get('JARVIS_REVIEW_REPO') is None else 1)\n",
        encoding="utf-8")
    path = register_with(
        f"X18\tthe suite must judge this checkout\ttest:{suite}\tbuilt\t"
        f"CLAUDE.md:1\n")
    code, out = run(str(path), env=env_without(
        "JARVIS_BACKEND", *check_claims.AMBIENT_REPO_ENVS)
        | {"JARVIS_REVIEW_REPO": LOOKS_OTHER,
           "JARVIS_DEFECT_REGISTER": LOOKS_OTHER + r"\docs\defect-register.tsv"})
    check("a set-but-unpassed JARVIS_REVIEW_REPO no longer changes the result",
          code == 0, out)
    # ...and the child really saw nothing, read off its own output: the suite
    # FAILS on purpose so the checker quotes what it printed.
    probe = Path(tempfile.mkstemp(suffix=".py")[1])
    probe.write_text(
        "import os, sys\n"
        "print('SEEN=' + str(os.environ.get('JARVIS_REVIEW_REPO')))\n"
        "print('DEFECT=' + str(os.environ.get('JARVIS_DEFECT_REGISTER')))\n"
        "sys.exit(1)\n", encoding="utf-8")
    path = register_with(
        f"X19\tthe suite must print what it saw\ttest:{probe}\tbuilt\tCLAUDE.md:1\n")
    code, out = run(str(path), env=env_without(
        "JARVIS_BACKEND", *check_claims.AMBIENT_REPO_ENVS)
        | {"JARVIS_REVIEW_REPO": LOOKS_OTHER})
    check("... and a suite the checker starts sees SEEN=None from its own print",
          "SEEN=None" in out and "ignoring ambient" in out, out)


def t_the_model_loaders_are_forced_offline_like_the_runner():
    """C101 (2026-11-13): the checker used to start suites with the caller's own
    network settings, so the Live settings parity suite fetched five model files
    inside one turn, and the empty `memory.db` that created tripped a check that
    a carded change writes no settings file - a desk red CI never saw, because
    `backend/run_suites.py` has forced the model loaders offline since
    2026-10-18. The checker now holds the runner's own rule."""
    sys.path.insert(0, str(REPO / "tools"))
    import check_claims
    sys.path.insert(0, str(REPO / "backend"))
    import run_suites

    check("the checker's OFFLINE_ENVS is the runner's dictionary, not a second "
          "list that can drift",
          check_claims.OFFLINE_ENVS == run_suites.OFFLINE_ENVS,
          (check_claims.OFFLINE_ENVS, run_suites.OFFLINE_ENVS))
    check("... all six switch names and values",
          len(check_claims.OFFLINE_ENVS) == 6,
          sorted(check_claims.OFFLINE_ENVS))
    # Forced, not defaulted: a caller who sets one of them to 0 cannot switch a
    # download back on. This process's own environment is restored afterwards.
    before = {key: os.environ.get(key) for key in check_claims.OFFLINE_ENVS}
    os.environ["HF_HUB_OFFLINE"] = "0"
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            env = check_claims._suite_env()
    finally:
        for key, value in before.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    check("... and a caller's own HF_HUB_OFFLINE=0 cannot switch a download "
          "back on", all(env.get(k) == v
                         for k, v in check_claims.OFFLINE_ENVS.items()),
          {k: env.get(k) for k in check_claims.OFFLINE_ENVS})
    # End to end, on ONE throwaway suite that FAILS on purpose so the checker
    # quotes what the child saw: the environment the checker hands a suite is
    # offline whatever the checker's own parent carries.
    suite = Path(tempfile.mkstemp(suffix=".py")[1])
    suite.write_text(
        "import os, sys\n"
        "print('HF=' + str(os.environ.get('HF_HUB_OFFLINE')))\n"
        "sys.exit(1)\n", encoding="utf-8")
    path = register_with(
        f"X16\ta suite must not fetch a model\ttest:{suite}\tbuilt\t"
        f"CLAUDE.md:1\n")
    code, out = run(str(path), env=env_with_ambient() | {"HF_HUB_OFFLINE": "0"})
    check("a suite the checker starts sees HF_HUB_OFFLINE=1", "HF=1" in out, out)


def t_a_suite_leaves_no_bytecode_in_the_tree():
    """D06 went red on the desk's SECOND register run (2026-11-13): the first
    run's suites imported base-only modules without the runner's
    `PYTHONDONTWRITEBYTECODE=1`, left `jarvis-backend/__pycache__`, and
    `backend/test_base_matches_repo.py` refused a base carrying generated files.
    A check must not dirty the tree it is checking for the next check."""
    sys.path.insert(0, str(REPO / "tools"))
    import check_claims

    check("the checker's NO_BYTECODE_ENVS is the runner's one switch",
          check_claims.NO_BYTECODE_ENVS == {"PYTHONDONTWRITEBYTECODE": "1"},
          check_claims.NO_BYTECODE_ENVS)
    # Forced, not defaulted: a caller who sets it to 0 cannot switch bytecode
    # writing back on. This process's own environment is restored afterwards.
    before = os.environ.get("PYTHONDONTWRITEBYTECODE")
    os.environ["PYTHONDONTWRITEBYTECODE"] = "0"
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            env = check_claims._suite_env()
    finally:
        if before is None:
            os.environ.pop("PYTHONDONTWRITEBYTECODE", None)
        else:
            os.environ["PYTHONDONTWRITEBYTECODE"] = before
    check("... and a caller's own 0 cannot switch bytecode writing back on",
          env.get("PYTHONDONTWRITEBYTECODE") == "1",
          env.get("PYTHONDONTWRITEBYTECODE"))
    # End to end: a suite that IMPORTS a module of its own, started by the
    # checker, must leave no __pycache__ behind. It fails on purpose so the
    # checker quotes what the child saw rather than swallowing it.
    scratch = Path(tempfile.mkdtemp(prefix="claims-bytecode-"))
    (scratch / "claims_probe_module.py").write_text("VALUE = 1\n",
                                                    encoding="utf-8")
    suite = Path(tempfile.mkstemp(suffix=".py")[1])
    suite.write_text(
        "import os, sys\n"
        f"sys.path.insert(0, {str(scratch)!r})\n"
        "import claims_probe_module\n"
        "print('BYTECODE=' + str(os.environ.get('PYTHONDONTWRITEBYTECODE')))\n"
        "sys.exit(1)\n", encoding="utf-8")
    path = register_with(
        f"X17\ta suite must not write bytecode into the tree\ttest:{suite}\tbuilt\t"
        f"CLAUDE.md:1\n")
    code, out = run(str(path), env=env_with_ambient())
    check("a suite the checker starts sees PYTHONDONTWRITEBYTECODE=1",
          "BYTECODE=1" in out, out)
    check("... and importing a module in that run wrote no __pycache__",
          not (scratch / "__pycache__").exists(),
          sorted(p.name for p in scratch.iterdir()))


def t_a_suite_the_checker_runs_does_not_see_the_ambient_value():
    """End to end, on ONE throwaway suite: the checker starts it with `env=`
    explicitly, so the value its parent carries does not reach it - and with the
    flag it does.

    The suite FAILS on purpose, because a passing suite's output is never
    printed; a failing one's last lines are quoted in the checker's own report,
    so what the child saw is read off the checker's output rather than assumed.
    """
    suite = Path(tempfile.mkstemp(suffix=".py")[1])
    suite.write_text(
        "import os, sys\n"
        "print('SEEN=' + str(os.environ.get('JARVIS_BACKEND')))\n"
        "sys.exit(1)\n", encoding="utf-8")
    path = register_with(
        f"X15\tthe suite must not read the live folder\ttest:{suite}\tbuilt\t"
        f"CLAUDE.md:1\n")
    code, out = run(str(path), env=env_with_ambient(LOOKS_LIVE))
    check("a suite the checker starts does NOT see the ambient JARVIS_BACKEND",
          "SEEN=None" in out, out)
    check("... and that run says one line naming the value it ignored",
          "ignoring ambient JARVIS_BACKEND" in out and LOOKS_LIVE in out, out)
    code, out = run(str(path), "--use-env-backend",
                    env=env_with_ambient(LOOKS_LIVE))
    check("with --use-env-backend the suite DOES see the value, unchanged",
          f"SEEN={LOOKS_LIVE}" in out, out)
    code, out = run(str(path), "--use-env-backend", env=env_with_ambient())
    check("... and with no value on the machine there is nothing to pass, and "
          "no crash", "SEEN=None" in out, out)


if __name__ == "__main__":
    for fn in (t_the_checker_exists, t_the_committed_register_is_green,
               t_list_prints_every_row_it_checked,
               t_the_whole_register_is_swept_once,
               t_the_vocabulary_is_actually_used,
               t_every_source_points_at_a_real_line,
               t_a_source_may_name_a_decisions_fragment,
               t_a_source_may_name_a_symbol_or_a_heading,
               t_a_source_may_name_a_changelog_bullet,
               t_a_symbol_row_bites_on_a_temp_repository,
               t_a_changelog_row_bites_on_a_temp_repository,
               t_the_about_generator_accepts_the_durable_kinds,
               t_the_record_grep_is_answered_by_both_places,
               t_the_about_page_quotes_the_register_it_describes,
               t_a_built_row_that_stopped_holding_fails,
               t_an_open_row_whose_gap_closed_fails,
               t_an_open_row_that_is_still_open_is_green,
               t_a_row_with_too_few_columns_is_refused,
               t_a_no_file_row_answers_both_ways,
               t_a_check_kind_nobody_knows_is_refused,
               t_an_unknown_state_is_refused,
               t_a_duplicated_id_is_refused,
               t_an_unverifiable_row_may_not_name_a_check,
               t_an_unverifiable_row_with_a_reason_is_green,
               t_an_empty_register_is_not_a_pass,
               t_a_missing_register_is_not_a_pass,
               t_every_kind_all_answers_on_a_real_row,
               t_a_skipped_substance_is_not_proof,
               t_a_clean_suite_still_proves_a_row,
               t_a_skip_count_with_no_reason_is_not_proof,
               t_the_skip_allow_list_is_keyed_to_the_suite_that_needs_it,
               t_the_owner_check_skip_is_named_and_not_counted_as_a_pass,
               t_a_suite_that_passed_nothing_is_not_proof,
               t_a_documented_environment_skip_is_the_zero_check_exemption,
               t_the_zero_check_rule_reads_the_runners_own_parser,
               t_the_parser_offers_the_opt_in_flag,
               t_the_ambient_backend_variable_is_ignored_unless_asked_for,
               t_the_ambient_repository_overrides_are_ignored_unless_a_repo_is_named,
               t_the_model_loaders_are_forced_offline_like_the_runner,
               t_a_suite_leaves_no_bytecode_in_the_tree,
               t_a_suite_the_checker_runs_does_not_see_the_ambient_value):
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
