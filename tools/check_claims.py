#!/usr/bin/env python3
"""Check every claim in docs/CLAIMS.tsv against the code, in both directions.

    python3 tools/check_claims.py [--list] [-v] [register.tsv]

The register is `docs/CLAIMS.tsv` unless a path is given; the argument is how
`backend/test_claims.py` points this check at one broken row at a time.

WHY THIS EXISTS. This project writes down what it knows in prose - a decision
log, audit reports, design docs - and for a long time nothing checked any of
it. On 2026-10-05 five false statements reached the owner in one day, and every
one of them was a sentence somebody had trusted instead of re-checking:

  * `CLAUDE.md`'s "Owner decisions recorded, not yet built" queue listed
    tap-to-talk on the phone, which had been built on 2026-10-01 (`eabca34d`);
  * the owner was told the phone's read-only past-approvals list did not exist,
    which `docs/audit-reports-2026-09-29-30/49-audit-a1ef1de0.md:53` had
    already recorded as *"It is built. It is only reachable via Inbox."*;
  * docs and product strings said the second graphics card "is not installed",
    which `nvidia-smi` on the owner's PC contradicts (an RTX 2060 12 GB);
  * a design doc promised a phone screen that appears nowhere in the tree.

The knowledge was in the repository. Nothing surfaced it. This is what
surfaces it: one row per claim, each with a check a machine can run.

WHAT A ROW MEANS. Five tab-separated columns - id, claim, check, state,
source. The `check` is evidence FOR the statement the row makes, so:

  * `state` is `built` and the check PASSES - the claim still holds;
  * `state` is `open` and the check FAILS - a real gap, still open;
  * `state` is `unverifiable` - no definite check exists, and the `check`
    column carries the reason instead. Nothing is guessed.

IT FAILS IN TWO DIRECTIONS, and the second is the whole point:

  1. a `built` row whose check now FAILS - the thing regressed, or the claim
     was wrong when it was written;
  2. an `open` row whose check now PASSES - the gap CLOSED and this register is
     stale, so the row must be updated (usually to `built`).

Without the second direction the register rots exactly like the prose it
replaced: a row that says "not built" outlives the build, and the next reader
trusts it. That is how tap-to-talk was reported as missing on 2026-10-05.

A `check` is written the way it should read when the claim is TRUE, which is
why an `open` row often carries a `grep` for the thing that does not exist yet,
and a row about stale prose carries an `absent` for the wrong sentence. When
somebody fixes that prose the `absent` starts passing, and rule 2 above tells
the next reader to flip the row.

THE SIX KINDS, each with a definite answer:

  * `file:<path>` - this file exists (repo-relative, `/` separators);
  * `no-file:<path>` - this file is NOT there. `file:`'s mirror, and it was
    added on 2026-10-05 for a real claim the first register could not write
    down: `docs/README.md` records `docs/SOURCE-BUNDLE.md` as "Removed
    2026-10-05" while the file is still in the tree, tracked. `absent:` cannot
    carry that row, because it needs the path to exist in order to look inside
    it - so a claim that something was deleted had no kind at all, and a
    finding with no kind is a finding that gets dropped;
  * `grep:<path>:<pattern>` - this text is present. `<path>` may be a
    file or a directory (then every text file under it is read);
  * `absent:<path>:<pattern>` - this text is NOT present;
  * `test:<suite>` - running this suite exits 0 (a bare `backend/...` name, a
    repo-relative `*.py`, or a bare file name resolved under `backend/`);
  * `number:<doc>:<path>:<value>` - the figure `<value>` is written in `<doc>`
    AND the same number appears in `<path>`, comparing digits only so
    `7,680` and `7680` and `60_000` are the same figure.

A claim that needs judgement goes in as `unverifiable` with the reason in the
`check` column - never as a guess. A reason that begins with one of the five
kinds is refused, because a row that names a definite check cannot be
unverifiable.

`--list` prints every row it checked, so "nothing is wrong" can be told apart
from "nothing was looked at" (the lesson `check-tokens.py` writes down about
its own missing files). The summary line prints the counts either way.

Exit code is non-zero only for a real violation: a broken direction above, or
a register this check cannot read (a missing column, an unknown kind or state,
a duplicate id, a row whose `check` is a kind it does not know). A malformed
register is never a silent skip - a row nobody can evaluate is a row nobody
checked.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REGISTER = REPO / "docs" / "CLAIMS.tsv"

#: Columns, in order. A row with any other number is refused rather than
#: guessed at, because a register whose shape is uncertain cannot be checked.
COLUMNS = ("id", "claim", "check", "state", "source")

#: The six kinds a `check` may be, each with a definite answer.
KINDS = ("file", "no-file", "grep", "absent", "test", "number")

#: The three states a row may carry.
STATES = ("built", "open", "unverifiable")

#: Directories a directory-wide `grep`/`absent` never reads: build output,
#: caches, vendored packages and the audit pass's own scratch. The last is
#: gitignored and holds whole copies of backend files, so reading it would
#: make this check answer a question about files no clone carries.
SKIP = {".git", "node_modules", "__pycache__", ".venv", "venv", "target",
        "dist", "build", ".mypy_cache", ".pytest_cache", ".ruff_cache",
        "dshwork"}

#: A file larger than this is not read, and SAYS SO rather than passing. The
#: repository's biggest text file is 13.5 MB; a pattern that only matches
#: inside one of those is not a check anyone can rely on.
MAX_BYTES = 8 * 1024 * 1024

#: How long a `test:` row may run before it is a failure. The suite this
#: register names takes about 2 seconds; the ceiling is for a hang, not for a
#: slow machine.
TEST_TIMEOUT = 600


def relative(path: Path) -> str:
    try:
        return path.relative_to(REPO).as_posix()
    except ValueError:
        return path.as_posix()


def text_files_under(path: Path):
    """Every file a directory `grep` reads, skipping SKIP and the oversized."""
    if path.is_file():
        yield path
        return
    for candidate in sorted(path.rglob("*")):
        try:
            rel = candidate.relative_to(REPO)
        except ValueError:
            rel = candidate
        if any(part in SKIP for part in rel.parts[:-1]) or not candidate.is_file():
            continue
        try:
            if candidate.stat().st_size > MAX_BYTES:
                continue
        except OSError:
            continue
        yield candidate


def read_text(path: Path):
    """(text, why-not) for one file. Binary files answer "not text"."""
    try:
        head = path.open("rb").read(4096)
    except OSError as err:
        return None, f"could not be read ({err})"
    if b"\x00" in head:
        return None, None                      # binary: silently not a match
    try:
        return path.read_text(encoding="utf-8", errors="replace"), None
    except OSError as err:
        return None, f"could not be read ({err})"


def search(pattern: str, where: str):
    """(found at "path:line", why-not) for `pattern` under `where`.

    Plain substring, never a regular expression: a claim's check is written by
    hand from the sentence the claim came from, and a stray `.` or `(` in one
    silently matching something else is exactly the class of quiet wrongness
    this register exists to remove.
    """
    path = REPO / where
    if not path.exists():
        return None, f"no such path: {where}"
    read_any = False
    for candidate in text_files_under(path):
        text, why = read_text(candidate)
        if why:
            return None, f"{relative(candidate)} {why}"
        if text is None:
            continue
        read_any = True
        at = text.find(pattern)
        if at >= 0:
            line = text.count("\n", 0, at) + 1
            return f"{relative(candidate)}:{line}", ""
    if not read_any:
        return None, f"nothing readable under {where}"
    return None, ""


def check_file(where: str):
    path = REPO / where
    if path.is_file():
        return True, f"{where} exists"
    if path.exists():
        return False, f"{where} is a directory, not a file"
    return False, f"{where} does not exist"


def check_no_file(where: str):
    """The mirror of `check_file`: this file (or directory) is gone.

    `exists()` rather than `is_file()` on purpose - a claim that something was
    removed is not satisfied by leaving an empty directory of the same name in
    its place. Nothing here confirms the removal was *wanted*; that is the
    claim's business, not this check's.
    """
    path = REPO / where
    if path.exists():
        return False, f"{where} is still there"
    return True, f"{where} is gone"


def check_grep(where: str, pattern: str, want: bool):
    found, why = search(pattern, where)
    if why:
        return False, why
    if want:
        if found:
            return True, f"{pattern!r} is at {found}"
        return False, f"{pattern!r} is not in {where}"
    if found:
        return False, f"{pattern!r} is still at {found}"
    return True, f"{pattern!r} is gone from {where}"


def check_number(doc: str, path: str, value: str):
    """The figure in a document against the same figure where it is used.

    Digits only, so the thousands separator, the underscore and the unit a
    writer chose do not decide whether two places agree - `7,680`, `7680` and
    `60_000` are the same figure. What is compared is a number, not a spelling.
    """
    digits = re.sub(r"[,_]", "", value)
    if not digits.isdigit():
        return False, f"{value!r} is not a number this check can compare"
    doc_path = REPO / doc
    if not doc_path.is_file():
        return False, f"{doc} does not exist"
    doc_text, why = read_text(doc_path)
    if why:
        return False, f"{doc} {why}"
    if value not in doc_text:
        return False, f"{value!r} is not written in {doc}"
    where = REPO / path
    if not where.is_file():
        return False, f"{path} does not exist"
    text, why = read_text(where)
    if why:
        return False, f"{path} {why}"
    if digits not in re.sub(r"[,_]", "", text):
        return False, f"{digits} is not in {path}"
    return True, f"{value} in {doc} agrees with {digits} in {path}"


def check_test(suite: str):
    """Run one suite. Its exit code is the answer; nothing is inferred from it."""
    candidates = [REPO / suite, REPO / "backend" / suite]
    if not suite.endswith(".py"):
        candidates = [REPO / "backend" / (suite + ".py")] + candidates
    chosen = next((p for p in candidates if p.is_file()), None)
    if chosen is None:
        return False, f"no suite file called {suite!r}"
    try:
        done = subprocess.run(
            [sys.executable, str(chosen)], cwd=str(REPO),
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=TEST_TIMEOUT)
    except subprocess.TimeoutExpired:
        return False, f"{suite} did not finish within {TEST_TIMEOUT}s"
    except OSError as err:
        return False, f"{suite} could not be run ({err})"
    if done.returncode == 0:
        return True, f"{suite} exits 0"
    tail = [line for line in (done.stdout or "").strip().splitlines()[-3:]
            if line.strip()]
    return False, (f"{suite} exited {done.returncode}"
                   + (f": {' | '.join(tail)}" if tail else ""))


def parse_check(check: str):
    """(kind, args, why-not). A kind this check does not know is a violation."""
    kind, _, rest = check.partition(":")
    kind = kind.strip()
    if kind not in KINDS:
        return None, None, (f"{check!r} is not one of the {len(KINDS)} kinds "
                            f"({', '.join(KINDS)})")
    if kind == "file":
        if not rest.strip():
            return None, None, "file: names no path"
        return kind, (rest.strip(),), ""
    if kind == "no-file":
        if not rest.strip():
            return None, None, "no-file: names no path"
        return kind, (rest.strip(),), ""
    if kind in ("grep", "absent"):
        where, sep, pattern = rest.partition(":")
        if not sep or not where.strip() or not pattern:
            return None, None, f"{kind}: needs <path>:<pattern>"
        return kind, (where.strip(), pattern), ""
    if kind == "test":
        if not rest.strip():
            return None, None, "test: names no suite"
        return kind, (rest.strip(),), ""
    # number:<doc>:<path>:<value>
    doc, sep, rem = rest.partition(":")
    path, sep2, value = rem.partition(":")
    if not (sep and sep2 and doc.strip() and path.strip() and value):
        return None, None, "number: needs <doc>:<path>:<value>"
    return kind, (doc.strip(), path.strip(), value), ""


def run_row(row: dict):
    """(passed, detail) - or (None, reason) for an unverifiable row."""
    kind, args, why = parse_check(row["check"])
    if why:
        return None, why
    if kind == "file":
        return check_file(*args)
    if kind == "no-file":
        return check_no_file(*args)
    if kind == "grep":
        return check_grep(args[0], args[1], True)
    if kind == "absent":
        return check_grep(args[0], args[1], False)
    if kind == "test":
        return check_test(*args)
    return check_number(*args)


def read_register(register: Path = REGISTER):
    """(rows, problems). Every problem is reported, never skipped silently.

    `register` is a parameter rather than the module constant so the test in
    `backend/test_claims.py` can point this check at a temporary file carrying
    one broken row of each kind, and prove both directions really do fail.
    """
    rows: list[dict] = []
    problems: list[str] = []
    if not register.is_file():
        return rows, [f"{relative(register)} does not exist"]
    seen: dict[str, int] = {}
    for number, raw in enumerate(
            register.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        parts = raw.split("\t")
        if len(parts) != len(COLUMNS):
            problems.append(
                f"{relative(register)}:{number}  has {len(parts)} column(s), "
                f"not {len(COLUMNS)} ({', '.join(COLUMNS)})")
            continue
        row = dict(zip(COLUMNS, parts))
        row["line"] = number
        for column in COLUMNS:
            if not row[column].strip():
                problems.append(f"{relative(register)}:{number}  the "
                                f"{column} column is empty")
        if row["state"] not in STATES:
            problems.append(f"{relative(register)}:{number}  {row['id']}: state "
                            f"{row['state']!r} is not one of {', '.join(STATES)}")
        if row["id"] in seen:
            problems.append(f"{relative(register)}:{number}  the id "
                            f"{row['id']!r} was already used on line "
                            f"{seen[row['id']]}")
        seen[row["id"]] = number
        if row["state"] == "unverifiable":
            first = row["check"].split(":", 1)[0].strip()
            if first in KINDS:
                problems.append(
                    f"{relative(register)}:{number}  {row['id']}: a row is "
                    f"unverifiable only when NO definite check exists, and this "
                    f"one's reason starts with `{first}:`, which is a check")
        rows.append(row)
    return rows, problems


def main() -> int:
    listing = "--list" in sys.argv
    verbose = listing or "-v" in sys.argv
    # An optional path, defaulting to this repository's register. It exists so
    # backend/test_claims.py can point the check at a temporary file carrying
    # one broken row of each kind and prove both directions really do fail. A
    # path that is not there is a finding, never a quiet fallback to the real
    # register - that would be a green run that checked something else.
    given = [arg for arg in sys.argv[1:] if not arg.startswith("-")]
    register = Path(given[0]) if given else REGISTER
    if not register.is_absolute():
        register = (Path.cwd() / register).resolve()

    rows, problems = read_register(register)
    if not rows and not problems:
        print(f"::error::{relative(register)} holds no rows at all - this check "
              f"would pass having checked nothing")
        return 1

    counts = {"built": 0, "open": 0, "unverifiable": 0}
    regressed: list[tuple[dict, str]] = []
    closed: list[tuple[dict, str]] = []
    unclear: list[tuple[dict, str]] = []

    for row in rows:
        counts[row["state"]] = counts.get(row["state"], 0) + 1
        if row["state"] == "unverifiable":
            if listing:
                print(f"  {row['id']:<7} unverifiable  {row['claim']}")
                print(f"          cannot be checked: {row['check']}")
            continue
        passed, detail = run_row(row)
        if passed is None:
            unclear.append((row, detail))
            if listing:
                print(f"  {row['id']:<7} {row['state']:<12} UNCLEAR   {detail}")
            continue
        if verbose:
            print(f"  {row['id']:<7} {row['state']:<12} "
                  f"{'holds' if passed else 'does not hold':<12} {detail}")
        if row["state"] == "built" and not passed:
            regressed.append((row, detail))
        elif row["state"] == "open" and passed:
            closed.append((row, detail))

    # A row this check cannot evaluate is a violation in its own right: its
    # claim was NOT checked, and silence about that is how a register ends up
    # green having looked at nothing.
    for row, detail in unclear:
        problems.append(f"{row['id']} (line {row['line']}): {detail}")

    if regressed:
        print("::error::a claim written down as BUILT no longer holds - either "
              "the thing regressed, or the row was wrong when it was written. "
              "Re-check it by hand and fix the claim, the code or the row:")
        for row, detail in regressed:
            print(f"  {row['id']}  {row['claim']}")
            print(f"      check: {row['check']}")
            print(f"      says:  {detail}")
            print(f"      source: {row['source']}")
    if closed:
        print("::error::a claim written down as OPEN now PASSES - the gap closed "
              "and this register is stale. Update the row (usually to `built`, "
              "or to a check of what is left), because a row that says \"not "
              "built\" outlives the build and the next reader trusts it:")
        for row, detail in closed:
            print(f"  {row['id']}  {row['claim']}")
            print(f"      check: {row['check']}")
            print(f"      now:   {detail}")
            print(f"      source: {row['source']}")
    if problems:
        print("::error::this register could not be read whole - a row nobody can "
              "evaluate is a row nobody checked:")
        for problem in problems:
            print(f"  {problem}")

    if regressed or closed or problems:
        return 1

    print(f"{len(rows)} claim(s) checked against the code: "
          f"{counts['built']} built, {counts['open']} still open, "
          f"{counts['unverifiable']} unverifiable (the reason is in each row).")
    print("Every `built` claim still holds, and every `open` one is still a real "
          "gap. The second half is the point: when a gap closes this check says "
          "so, so the row cannot outlive the build the way "
          "CLAUDE.md's \"not yet built\" queue outlived tap-to-talk.")
    if counts["unverifiable"]:
        print(f"{counts['unverifiable']} row(s) name no definite check and are "
              f"NOT verified by this run - they are listed in the register with "
              f"their reason, and `--list` prints every one.")
    if listing:
        print(f"\nall {len(rows)} row(s) were looked at:")
        for row in rows:
            print(f"  {row['id']:<7} {row['state']:<12} {row['check']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
