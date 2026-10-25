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
  * `test:<suite>` - running this suite exits 0 AND it printed no skip that is
    about the code rather than this machine (a bare `backend/...` name, a
    repo-relative `*.py`, or a bare file name resolved under `backend/`; the
    skip rule is the next paragraph);
  * `number:<doc>:<path>:<value>` - the figure `<value>` is written in `<doc>`
    AND the same number appears in `<path>`, comparing digits only so
    `7,680` and `7680` and `60_000` are the same figure.

A claim that needs judgement goes in as `unverifiable` with the reason in the
`check` column - never as a guess. A reason that begins with one of the five
kinds is refused, because a row that names a definite check cannot be
unverifiable.

A SKIP IS NOT PROOF. `test:` used to read success from the exit code alone, and
a suite can exit 0 having deliberately not run a check.
`backend/test_data_backup.py` prints `skip  ...` and returns 0 when
`refuse_write_into_a_locker` is absent from the tool, so removing that safety
guard left claim F11 printed as built. This check therefore reads the skip
lines a suite prints and, unless the reason is a limitation of THIS MACHINE,
withholds proof from every row that names the suite.

Why not "any skip is a failure": `backend/test_data_backup.py` prints one
unconditionally - the fixture that needs `icacls` - so that rule would turn its
four green rows (F06, F08, F10, F11) red on every platform, not because a claim
stopped holding but because this machine cannot build the fixture. So the skip
reasons that are about the machine are listed per suite in
`ENVIRONMENT_SKIPS`, and anything else - including the missing-guard reason
this rule exists for - is unproven. Two limits, written down rather than hoped
away: a skip in a suite withholds proof from every row naming that suite (a row
names the suite as its evidence, not one check inside it), and a new
environmental skip with a new wording makes its row red until its reason is
added to that list - loud, never silent. A suite that skips in a convention it
never prints, and prints no summary this check can read, can still hide one;
nothing can read what a suite does not say.

WHAT COUNTS AS "THERE". Every path a row names is judged against the TRACKED
tree - `git ls-files` - and not against the folder this happens to run in. A
working copy carries files no clone has: agent scratch, build output, a
gitignored copy of a real file. Judging those answers a question about one
machine while reading as a claim about the repository, and it is how this check
went red at a desk while CI stayed green - an untracked file with the name a
`no-file:` row names is "still there" here and absent everywhere else. Outside
a git repository there is nothing to ask but the folder, so that fallback
exists, and it is the only one.

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

#: How the shipped suites print a skip. Three shapes are real in this tree
#: (measured 2026-10-24): `skip  <why>` (test_api_doc, test_media_index,
#: test_fault_probes, ...), `skip  <name> - <why>` (test_data_backup) and
#: `SKIP  <name>` followed by an indented reason (test_settings_tool). The word
#: boundary is `backend/run_suites.py`'s own (`_LINE["skipped"]`), so a check
#: named "skipped-this-week ..." is not read as a skip: the word has to end
#: there or be followed by a space, a tab or a colon. Matched at column 0 on
#: purpose - `check()`'s failure detail is indented by eight spaces, and a
#: detail that begins with the word "skip" is not a skip marker.
SKIP_MARKER = re.compile(r"^skip(ped)?(?=[ \t:]|$)", re.IGNORECASE)

#: The skip reasons that are a limitation of THIS MACHINE, keyed by the suite's
#: repo-relative path, so a skip carrying one of them leaves its row PROVEN.
#: Each was read off the suite that prints it (2026-10-24) and matched
#: case-insensitively against the skip line and any indented reason under it:
#:
#: * test_data_backup - "is not installed": the `cryptography` package, whose
#:   absence the suite itself tests the fallback for; "needs icacls": the ACL
#:   fixture cannot be built without Windows' icacls and the account's own name,
#:   and it is printed UNCONDITIONALLY - without this entry four green rows go
#:   red on every platform; "is not nt": a Windows-only question asked on
#:   another OS.
#: * test_settings_tool - "not importable in this environment": a setter's
#:   module is not installed in this interpreter; the suite prints the count and
#:   never counts it as a pass.
#:
#: Everything else - including the `refuse_write_into_a_locker` skip this rule
#: exists for ("this build of the tool has no ...", "the guard is not in this
#: tree") - withholds proof. A new environmental skip needs its reason added
#: here; until it is, its row is red, which is the honest direction.
ENVIRONMENT_SKIPS = {
    "backend/test_data_backup.py": (
        "is not installed", "needs icacls", "is not nt"),
    "backend/test_settings_tool.py": ("not importable in this environment",),
}

#: The summary line a suite may print for itself - `N passed, M skipped,
#: K failed` in any order (test_media_index prints the skipped count last).
#: `SUMMARY_LINE` is `backend/run_suites.py`'s own shape, so a sentence that
#: merely contains those words is not read as a suite's totals. Only used to
#: catch a suite that says it skipped more checks than it printed a readable
#: reason for: that row is unproven too.
SUMMARY_LINE = re.compile(r"^\s*\d+\s+(?:passed|failed)\b", re.IGNORECASE)
SKIP_SUMMARY = re.compile(r"\b(\d+)\s+skipped\b", re.IGNORECASE)

#: The line a Python traceback ENDS on, at column 0 where Python writes it -
#: `PermissionError: [WinError 5] Access is denied: ...`,
#: `jarvis_backup.RestoreError: could not replace a file (PermissionError)`.
#: See `exception_lines`: this is the half of a failure that a check reading
#: only `stdout` never saw.
TRACEBACK_EXCEPTION = re.compile(
    r"^[A-Za-z_][\w.]*(?:Error|Exception|Interrupt|Exit)\b.*$")


def relative(path: Path) -> str:
    try:
        return path.relative_to(REPO).as_posix()
    except ValueError:
        return path.as_posix()


# ---------------------------------------------------------------------------
#   What this check judges: the TRACKED tree, not the folder it is sitting in
# ---------------------------------------------------------------------------
# A working copy carries files no clone has: agent scratch, build output, a
# gitignored copy of a real file. Judging those answers a question about THIS
# folder while reading as a claim about the repository, and it is how this
# checker went red at a desk while CI stayed green - an untracked file with the
# name a `no-file:` row names is "still there" here and absent everywhere else.
# (It is how `dshwork/` and `.dsh-scratch/` made this file's sibling checkers
# red too; see `.gitignore`'s note on both.)
#
# So a path is judged by what `git ls-files` reports. The fallback is the whole
# folder walk, and it happens ONLY where there is no tracked tree to ask about:
# outside a git repository, or for an absolute path that is not inside this one.
# A plain copy of the files is a shape this check has to keep working in - a
# register is a list of repo-relative paths, and nothing about reading one needs
# git - and when git will not answer, the run SAYS SO rather than passing
# quietly on a judgement it never made.
_TRACKED: set[str] | None = None
_TRACKED_ASKED = False


def tracked_paths() -> set[str] | None:
    """Every repo-relative path `git ls-files` reports, or None when there is no
    repository here to ask.

    Asked once per run. `-z` rather than newline-separated output: a path with a
    space or a quote in it comes back quoted and unparseable without it, and a
    path this check cannot name is a path it cannot judge.
    """
    global _TRACKED, _TRACKED_ASKED
    if not _TRACKED_ASKED:
        _TRACKED_ASKED = True
        try:
            done = subprocess.run(
                ["git", "ls-files", "-z"], cwd=str(REPO), capture_output=True,
                text=True, encoding="utf-8", errors="replace")
            if done.returncode == 0:
                _TRACKED = {p for p in done.stdout.split("\0") if p}
        except OSError:
            _TRACKED = None
    return _TRACKED


def tracked_entry(where: str) -> str | None:
    """"file", "dir" or None - how the tree holds `where`.

    "dir" is a folder that carries tracked files: `file:docs` is a directory,
    not a file, and the old `is_file()`/`exists()` pair said so. A path the
    tracked tree does not hold at all is None, whatever is lying on the disk
    under that name.

    Outside a git repository the filesystem answers instead, which is the only
    thing there is to ask.
    """
    name = where.replace("\\", "/").strip("/")
    paths = tracked_paths()
    if paths is None or Path(where).is_absolute():
        # No repository to ask, or a path that is not inside this one at all.
        # The filesystem is then the only thing that can answer, and it is what
        # this check asked before the tracked tree was consulted.
        path = REPO / where
        if path.is_file():
            return "file"
        return "dir" if path.is_dir() else None
    if not name:
        return "dir"
    if name in paths:
        return "file"
    if any(p.startswith(name + "/") for p in paths):
        return "dir"
    return None


def in_the_tree(where: str) -> bool:
    """Is `where` part of the tracked tree at all (either kind of entry)?"""
    return tracked_entry(where) is not None


def tracked_files_under(path: Path) -> list[Path] | None:
    """The tracked files under `path`, or None when `path` is outside REPO.

    Same filters as the folder walk below - SKIP, MAX_BYTES, and files that are
    not on disk here - so the two answer alike; what differs is which files
    they are asked about.
    """
    try:
        rel = path.relative_to(REPO).as_posix()
    except ValueError:
        return None
    prefix = "" if rel in ("", ".") else rel.rstrip("/") + "/"
    out = []
    for name in sorted(tracked_paths() or ()):
        if not name.startswith(prefix):
            continue
        if any(part in SKIP for part in name.split("/")[:-1]):
            continue
        candidate = REPO / name
        try:
            if not candidate.is_file() or candidate.stat().st_size > MAX_BYTES:
                continue
        except OSError:
            continue
        out.append(candidate)
    return out


def text_files_under(path: Path):
    """Every file a directory `grep` reads, skipping SKIP and the oversized.

    Inside a repository this is the TRACKED files under `path`, so a pattern
    that only a scratch copy carries is not read as evidence about the
    repository, and neither is one a scratch copy has made `absent:` fail on.
    """
    if path.is_file():
        yield path
        return
    tracked = tracked_files_under(path)
    if tracked is not None:
        yield from tracked
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
    if not in_the_tree(where):
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
    """Is this file in the TRACKED tree? The message is unchanged; what changed
    is who is asked (`git ls-files`, not the folder - see `tracked_entry`).

    One deliberate consequence: a tracked file whose deletion is not staged in
    the copy in front of this run still counts as present, because a clone gets
    it. The alternative reads as a claim about the repository and answers a
    question about one working copy, which is the defect this fixes.
    """
    kind = tracked_entry(where)
    if kind == "file":
        return True, f"{where} exists"
    if kind == "dir":
        return False, f"{where} is a directory, not a file"
    return False, f"{where} does not exist"


def check_no_file(where: str):
    """The mirror of `check_file`: this file (or directory) is gone FROM THE TREE.

    Both kinds of entry count on purpose - a claim that something was removed is
    not satisfied by leaving a folder of the same name behind. Nothing here
    confirms the removal was *wanted*; that is the claim's business, not this
    check's.

    A file that is only on this disk - agent scratch, a gitignored copy - is
    NOT the file: it is not in a clone, so a `no-file:` row about it is honest
    and this check says the claim holds. That was the whole report: a scratch
    file made a green register red on the machine that had the scratch.
    """
    if tracked_entry(where) is None:
        return True, f"{where} is gone"
    return False, f"{where} is still there"


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


def skip_blocks(output: str) -> list[str]:
    """Every skip a suite printed, one string each, marker plus its reason.

    `test_settings_tool` puts the reason on the next line and indents it, so
    indented lines after a marker belong to that marker; the lowercase shapes
    carry the reason on the same line. Matched at column 0 (see SKIP_MARKER).
    """
    lines = output.splitlines()
    blocks: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if SKIP_MARKER.match(line) is None:
            index += 1
            continue
        block = [line]
        index += 1
        while (index < len(lines) and lines[index].strip()
               and lines[index][:1].isspace()):
            block.append(lines[index])
            index += 1
        blocks.append("\n".join(block))
    return blocks


def reported_skips(output: str) -> int | None:
    """The skip count in the suite's own last summary line, or None.

    A suite with no summary (or an unreadable one) answers None, and the skip
    lines it printed are then the only evidence there is. Requiring the line to
    START like a summary keeps a sentence about skipped rows from being read as
    a total of skipped checks.
    """
    found = None
    for line in output.splitlines():
        if SUMMARY_LINE.match(line) is None:
            continue
        match = SKIP_SUMMARY.search(line)
        if match is not None:
            found = int(match.group(1))
    return found


def skip_that_withholds_proof(suite: str, output: str) -> str | None:
    """Why this suite's output leaves its row unproven, or None if it does not.

    `suite` is the repo-relative path, which is what `ENVIRONMENT_SKIPS` is
    keyed by; a suite outside the repository has no entry and is judged
    strictly (the bite tests in `backend/test_claims.py` point this check at a
    throwaway one). Returns the skip line to print, or a sentence about skips
    the suite counted for itself but never itemised with a reason this check
    can read.
    """
    allowed = ENVIRONMENT_SKIPS.get(suite, ())
    blocks = skip_blocks(output)
    for block in blocks:
        flat = " ".join(block.lower().split())
        if not any(reason in flat for reason in allowed):
            return block.splitlines()[0].strip()
    reported = reported_skips(output)
    if reported is not None and reported > len(blocks):
        return (f"{reported} skipped check(s) according to its own summary, and "
                f"only {len(blocks)} printed a reason this check can read")
    return None


def exception_lines(text: str, limit: int = 2) -> list[str]:
    """The line(s) a Python traceback ENDS on, from a suite's stderr.

    `PermissionError: [WinError 5] Access is denied: '...'`,
    `jarvis_backup.RestoreError: could not replace a file (PermissionError)`.
    Python writes these to STDERR, and this check used to read `stdout` only, so
    a failed suite was reported as `exited 1: Traceback (most recent call last):`
    - the header, never the reason (2026-10-25). Matched at column 0, where
    Python writes them; `limit` keeps the detail one readable line.
    """
    found: list[str] = []
    for line in (text or "").splitlines():
        if TRACEBACK_EXCEPTION.match(line) and line.strip() not in found:
            found.append(line.strip())
    return found[-limit:]


def check_test(suite: str):
    """Run one suite. Exiting 0 is necessary, never sufficient: a suite that
    printed a skip about the code (not about this machine) did not run that
    check, so it did not prove the row. See A SKIP IS NOT PROOF in the module
    docstring."""
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
        why = skip_that_withholds_proof(
            relative(chosen), (done.stdout or "") + "\n" + (done.stderr or ""))
        if why is not None:
            return False, f"{suite} exited 0 but SKIPPED: {why}"
        return True, f"{suite} exits 0"
    tail = [line for line in (done.stdout or "").strip().splitlines()[-3:]
            if line.strip()]
    # And the reason itself, which is on stderr - `stdout` alone reports a
    # failure as `Traceback (most recent call last):` and nothing else.
    for line in exception_lines(done.stderr):
        if line not in [t.strip() for t in tail]:
            tail.append(line)
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
    seen_bodies: dict[tuple, int] = {}
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
        # A row repeated under a DIFFERENT id is one claim counted twice, so
        # the register reads as two claims and the summary counts two - and the
        # id check just above cannot see it, because the ids differ. That is how
        # it shipped: on 2026-10-14 `a348f6e8` inserted a byte-identical copy of
        # E04 as E05 - 743 characters each, differing only in the id - and this
        # tool exited 0 while reporting one claim as two. The count it prints is
        # the number a reader trusts, so this is the more dangerous miss.
        # EVERY column must match, the id aside: a row differing only in its
        # source is still one claim counted twice.
        body = tuple(parts[1:])
        if body in seen_bodies:
            problems.append(
                f"{relative(register)}:{number}  {row['id']} repeats the claim "
                f"on line {seen_bodies[body]} - every column but the id is "
                f"identical, so the register counts one claim twice")
        else:
            seen_bodies[body] = number
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

    # Said once, and only when it is true: a run that could not ask git judged
    # the folder in front of it instead of the tracked tree, and a reader has to
    # know which question was answered. Never a silent substitution.
    if tracked_paths() is None:
        print("note: no git repository answered here, so every path was judged "
              "against THIS folder rather than the tracked tree (`git ls-files`) "
              "- the answer is about the copy in front of you, not a clone.")

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
