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

And on the real register, four things the checker cannot say about itself:

  * it exits 0 today, so the first run after this lands is green;
  * `--list` prints every row it checked - by id - so the happy line can be
    told apart from a run that looked at nothing;
  * every one of the five kinds in the vocabulary is used by at least one row
    (a kind nothing uses is a kind nothing tests);
  * every row's `source` names a file that exists and a line inside it, so a
    doc edit that moves the anchor is caught here rather than by a reader.

Needs nothing from the owner's PC, no network and no third-party package: the
checker itself is standard library only, and so is this.
"""
from __future__ import annotations

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

sys.path.insert(0, str(HERE))

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


HEADER = "# id\tclaim\tcheck\tstate\tsource\n"


def run(*args):
    """(exit code, output) for one run of the checker, from the repo root."""
    done = subprocess.run(
        [sys.executable, str(CHECKER), *args], cwd=str(REPO),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=600)
    return done.returncode, (done.stdout or "") + (done.stderr or "")


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
    code, out = run()
    check("the register passes today (the first run after it lands is green)",
          code == 0, out[-1500:])
    check("the green line says a number of rows, so 'nothing is wrong' cannot "
          "be confused with 'nothing was looked at'",
          bool(re.search(r"\d+ claim\(s\) checked", out)), out[-800:])
    check("the green line splits the register into built / still open / "
          "unverifiable",
          all(word in out for word in ("built", "still open", "unverifiable")),
          out[-800:])


def t_list_prints_every_row_it_checked():
    code, out = run("--list")
    check("--list still exits 0 on the real register", code == 0, out[-800:])
    rows = data_rows(REGISTER.read_text(encoding="utf-8"))
    missing = [row["id"] for row in rows if row["id"] not in out]
    check(f"every one of the {len(rows)} row ids is printed by --list", not missing,
          missing)
    check("--list says in words that all of them were looked at",
          f"all {len(rows)} row(s) were looked at" in out, out[-400:])


def t_the_vocabulary_is_actually_used():
    """A kind no row uses is a kind no test of this script would ever reach."""
    kinds = {row["check"].split(":", 1)[0] for row in
             data_rows(REGISTER.read_text(encoding="utf-8"))
             if row["state"] != "unverifiable"}
    for kind in ("file", "grep", "absent", "test", "number"):
        check(f"the register uses a `{kind}:` row", kind in kinds, sorted(kinds))


def t_every_source_points_at_a_real_line():
    """A register whose sources drift off their anchor is a register nobody
    can trace back to the sentence a claim came from."""
    bad = []
    for row in data_rows(REGISTER.read_text(encoding="utf-8")):
        path, _, line = row["source"].rpartition(":")
        target = REPO / path
        if not target.is_file():
            bad.append(f"{row['id']}: {path} is not a file")
            continue
        if not line.isdigit():
            bad.append(f"{row['id']}: {row['source']} does not end in a line number")
            continue
        total = len(target.read_text(encoding="utf-8", errors="replace").splitlines())
        if int(line) > total:
            bad.append(f"{row['id']}: {row['source']} is past the end of {path} "
                       f"({total} lines)")
    check("every source is a file and a line inside it", not bad, bad)


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
    check("... and names the five kinds that are allowed",
          "file, grep, absent, test, number" in out, out)


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


def t_the_five_kinds_all_answer_on_a_real_row():
    """One live row per kind, so a kind that stopped working is caught here and
    not by the register going red for a reason nobody can read.

    The `test:` row points at a throwaway suite rather than at a real one: a
    real suite can need packages this container has not installed, and pointing
    it at THIS file would run this file again, for ever.
    """
    suite = Path(tempfile.mkstemp(suffix=".py")[1])
    suite.write_text("import sys\nprint('a throwaway suite')\nsys.exit(0)\n",
                     encoding="utf-8")
    rows = {
        "file": "file:backend/jarvis_tidy.py",
        "grep": "grep:CLAUDE.md:Owner decisions recorded",
        "absent": "absent:CLAUDE.md:a sentence that was never written",
        "test": f"test:{suite}",
        "number": "number:CLAUDE.md:tools/shader_size.py:60,000",
    }
    for name, expr in rows.items():
        path = register_with(f"K-{name}\ta live {name} check\t{expr}\tbuilt\tCLAUDE.md:1\n")
        code, out = run(str(path))
        check(f"a live `{name}:` row passes", code == 0, out)


if __name__ == "__main__":
    for fn in (t_the_checker_exists, t_the_committed_register_is_green,
               t_list_prints_every_row_it_checked,
               t_the_vocabulary_is_actually_used,
               t_every_source_points_at_a_real_line,
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
               t_the_five_kinds_all_answer_on_a_real_row):
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
