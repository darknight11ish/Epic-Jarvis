#!/usr/bin/env python3
"""Check every claim in docs/CLAIMS.tsv against the code, in both directions.

    python3 tools/check_claims.py [--list] [-v] [--use-env-backend] [register.tsv]

The register is `docs/CLAIMS.tsv` unless a path is given; the argument is how
`backend/test_claims.py` points this check at one broken row at a time.

THE MACHINE'S OWN `JARVIS_BACKEND` IS IGNORED (2026-10-25), exactly as
`backend/run_suites.py:881-884` ignores it. That variable is set for the owner's
Windows account on this PC and names the LIVE backend folder, and
`backend/_where.py` puts that folder first on `sys.path` - so a `test:` row used
to run its suite against live code without anybody typing anything. On
2026-10-25 that made this checker report claim MED-01 as no longer holding
(`backend/test_medical_advocate.py exited 1: AssertionError:
MedicalStoreUnavailable not raised`) against a suite that is 95/95 green with the
variable removed: a red register, and a `main` that was never red. A check run is
about THIS CHECKOUT unless a person says otherwise. So each suite is started with
the variable removed (`_suite_env`), one line names the value that was ignored,
and `--use-env-backend` passes it through on purpose. That environment is passed
to `subprocess.run(env=...)` explicitly, so nothing inherited from a parent
process can put the value back.

AND EVERY SUITE IS STARTED OFFLINE (2026-11-13), with the same six switches
`backend/run_suites.py` forces (`OFFLINE_ENVS`). The runner's rule is that a model
download is never something a hermetic suite run may opt into, and this checker
did not hold it: on the owner's PC the Live settings parity suite (claim C101)
fetched five model files inside one turn and created an empty `memory.db`, which
tripped a check that a carded change writes no settings file - a desk red that CI,
where the runner forces the switches, never saw. With them the same suite runs
1042 checks green and fetches nothing.

AND A SUITE RUN LEAVES NO BYTECODE IN THE TREE (2026-11-13), for the same
reason and from the same place: `backend/run_suites.py:1452-1453` starts every
suite with `PYTHONDONTWRITEBYTECODE=1`. Without it, the desk's SECOND register
run was red on D06 - the first run's suites imported base-only modules and left
`jarvis-backend/__pycache__`, which `backend/test_base_matches_repo.py` refuses.
A check must not make the tree it is checking dirty for the next check.

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

AN ACCEPTED SKIP IS STILL PRINTED (2026-11-13). Being a limit of this machine
buys the row its proof; it does not buy silence. A row proven through
`ENVIRONMENT_SKIPS` was NOT looked at by the check that suite skipped, so every
run names the suite, quotes the skip line and counts the rows that rest on it -
whether or not `-v` was typed. That is the same rule as `docs/FIELD-TEST`'s
"BLOCKED and NOT-TESTABLE are never counted as passes", applied to a suite: the
row may stay proven, but the skip never reads as a pass.

WHAT COUNTS AS "THERE". Every path a row names is judged against the TRACKED
tree - `git ls-files` - and not against the folder this happens to run in. A
working copy carries files no clone has: agent scratch, build output, a
gitignored copy of a real file. Judging those answers a question about one
machine while reading as a claim about the repository, and it is how this check
went red at a desk while CI stayed green - an untracked file with the name a
`no-file:` row names is "still there" here and absent everywhere else. Outside
a git repository there is nothing to ask but the folder, so that fallback
exists, and it is the only one.

THE DECISION RECORD IS TWO PLACES SINCE 2026-10-28. A new owner decision is
written as ONE file under `decisions.d/` and rolled into `docs/DECISIONS.md`
later by `tools/roll_decisions.py` (`decisions.d/README.md` says how), so a row
that names the record reads BOTH: the rolled file and the fragments not yet
rolled. Without that, a claim added beside its own decision could not be checked
until somebody ran a roll - and an `absent:` row would stop seeing a sentence
the moment it came back as a fragment, which is the direction that must never go
quiet. The fragments are read through the same tracked-tree rule as everything
else: a scratch copy under `decisions.d/` is not evidence about the repository.

`--repo PATH` points this check at a copy of the repository, the same reason the
register path is an argument: `backend/test_claims.py` uses both to prove what a
`grep:` row does when the sentence lives only in a fragment, without writing a
fragment into the real tree.

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

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REGISTER = REPO / "docs" / "CLAIMS.tsv"

#: The decision record, repo-relative, as a row spells it - and the folder the
#: fragments not yet rolled into it live in. A `grep:`/`absent:` naming the
#: record reads both (see THE DECISION RECORD IS TWO PLACES in the docstring).
DECISION_RECORD = "docs/DECISIONS.md"
DECISION_FRAGMENTS = "decisions.d"

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

#: How long a `test:` row may run before it is a failure. The ceiling is for a
#: hang, not for a slow machine.
#:
#: RAISED 600 -> 900 s on the owner's 2026-11-10 00:05 PT Gemini ruling (Q2).
#: `backend/test_live_settings_parity.py` passed all 935 of its checks in
#: 606.6 s - 6.6 s over the old cap - because Jarvis grew to 62 switchable
#: tools and 180+ features across waves 8-14. The ruling's other half is that
#: the suite caches its repeated static reads to get back well under this
#: ceiling; the two changes together make the desk timeout permanent without
#: splitting claim row C101 or inventing an "environment-dependent" category.
TEST_TIMEOUT = 900

#: The explicit opt-in to run each `test:` row's suite against the backend folder
#: `JARVIS_BACKEND` names - the owner's LIVE folder on this PC. The same flag,
#: spelled the same way, as `backend/run_suites.py:830`: one word for one thing,
#: so nobody has to learn a second name for the choice they already made once.
USE_ENV_BACKEND_FLAG = "--use-env-backend"

#: The model loaders are OFFLINE in every suite's environment, with the same six
#: switches and the same values `backend/run_suites.py` forces on every run it
#: starts (`OFFLINE_ENVS`, added 2026-10-18). A claims check starts suites the
#: way the runner does; without this it did not, and on 2026-11-13 that was not
#: theoretical. Claim C101's Live settings parity suite imports the memory store,
#: and that store fetches its five model files from Hugging Face on a cold cache:
#: at the owner's desk it spent about two and a half minutes inside one turn and
#: created an empty `memory.db` in the suite's own config folder - which tripped a
#: check that a carded change writes no settings file. With the runner's own
#: offline switches the same suite is 1042 checks green and fetches nothing.
#: Forced, not defaulted: `run_suites.py`'s rule is that a download is never
#: something a hermetic suite run may opt into, so a caller's `HF_HUB_OFFLINE=0`
#: cannot switch it back on in a claims run either.
OFFLINE_ENVS = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "HF_DATASETS_OFFLINE": "1",
    "HF_HUB_DISABLE_TELEMETRY": "1",
    "DO_NOT_TRACK": "1",
    "ANONYMIZED_TELEMETRY": "False",
}

#: The runner also starts every suite with bytecode writing OFF
#: (`PYTHONDONTWRITEBYTECODE=1`, `backend/run_suites.py:1452-1453`), so a suite
#: run leaves no `.pyc` anywhere in the checkout it is checking. This checker did
#: not hold that rule either, and on 2026-11-13 it was measurable: the desk's
#: SECOND register run was red on D06, because the first run's suites had
#: imported base-only modules and left `jarvis-backend/__pycache__`, which
#: `backend/test_base_matches_repo.py` correctly refuses. Nothing a `test:` row
#: does may leave a file in the tree it is checking.
NO_BYTECODE_ENVS = {"PYTHONDONTWRITEBYTECODE": "1"}

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
#:   another OS; "this is not windows" and "does not enforce it": the two
#:   Windows-only probes the 2026-11-04 long-path backup fix added - one can
#:   only run on Windows at all, the other needs a filesystem that enforces the
#:   Windows path limit. Both are machine limits, not missing guards, and the
#:   Linux backend job prints them; the suite itself still counts them as skips,
#:   never as passes.
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
        "is not installed", "needs icacls", "is not nt",
        "this is not windows", "does not enforce it"),
    "backend/test_settings_tool.py": ("not importable in this environment",),
    # `backend/test_feedback_migration.py` used to need an entry here: it
    # copied the owner's live feedback.db and, on a CI runner with no such
    # file, printed "does not exist on this machine". Owner ruling Q9
    # (2026-11-09) replaced that with an explicit pre-v2 fixture built in
    # scratch, so the suite now runs in full everywhere and skips nothing -
    # there is no environmental skip left to allow.
    # The drag-and-drop suite (Wave 12, 2026-11-09) drives the REAL MarkItDown
    # converter in a child process when it can, and says so plainly when the
    # Python running the claims check has no MarkItDown installed. That is a
    # limitation of that Python environment, not a missing guard: the rest of
    # the suite still proves the one-file attachment path, the cap and the
    # refusals. Measured in the REQUIRED backend job's own environment on
    # 2026-11-09, where the optional package is absent.
    "backend/test_attached_file.py": ("markitdown is not installed",),
    # `backend/test_owner_check.py` (2026-11-13). On Windows the check that
    # would prove "off Windows there is no Windows Hello, so a risky approval
    # fails closed" cannot run: exercising the REAL path would raise a real
    # Windows Hello prompt, and no test may do that. The suite skips it and says
    # so in its own summary - a limit of the machine the suite is running on,
    # not a missing guard, because the same check runs in full on a machine that
    # is not Windows. Before this entry the skip withheld proof from claim C163
    # (the tool-switch approval card), so the register read red at the owner's
    # desk while nothing was wrong with the code. The skip is still printed by
    # every run, never counted as a pass (see ACCEPTED_ENVIRONMENT_SKIPS).
    "backend/test_owner_check.py": (
        "on windows the real check would raise a real prompt",),
}

#: The environment skips THIS RUN accepted: `(suite, line)` pairs, appended by
#: `check_test` and printed by `main`. A row proven through `ENVIRONMENT_SKIPS`
#: was NOT looked at by the check its suite skipped, so the skip is named on
#: every run - a skip that only shows with `-v` is a skip a reader of the plain
#: run never sees. Reset at the start of `main` (2026-11-13).
ACCEPTED_ENVIRONMENT_SKIPS: list[tuple[str, str]] = []

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
    """The tracked files under `path`, or None when the folder must be walked.

    Same filters as the folder walk below - SKIP, MAX_BYTES, and files that are
    not on disk here - so the two answer alike; what differs is which files
    they are asked about.

    None means "there is no tracked tree to ask": no repository here at all
    (`--repo` on a plain copy, or this checker run outside git), or a path that
    is not inside this repository. The old version answered `[]` in the first
    case, which made a directory `grep:` in a plain copy report "nothing
    readable under ..." instead of walking the folder - a silent no rather than
    the documented fallback. Fixed 2026-10-28, the day `--repo` made it
    reachable.
    """
    paths = tracked_paths()
    if paths is None:
        return None
    try:
        rel = path.relative_to(REPO).as_posix()
    except ValueError:
        return None
    prefix = "" if rel in ("", ".") else rel.rstrip("/") + "/"
    out = []
    for name in sorted(paths):
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


def is_decision_record(where: str) -> bool:
    """Does `where` name the decision record, in any spelling (separators, slashes)?"""
    return where.replace("\\", "/").strip("/") == DECISION_RECORD


def search(pattern: str, where: str):
    """(found at "path:line", why-not) for `pattern` under `where`.

    Plain substring, never a regular expression: a claim's check is written by
    hand from the sentence the claim came from, and a stray `.` or `(` in one
    silently matching something else is exactly the class of quiet wrongness
    this register exists to remove.

    `where` naming the decision record reads TWO places, because the record is
    two places since 2026-10-28: `docs/DECISIONS.md` and the fragments under
    `decisions.d/` not yet rolled into it. Both go through the tracked-tree
    rule, so neither a scratch copy nor an untracked one is evidence.
    """
    path = REPO / where
    if not in_the_tree(where):
        return None, f"no such path: {where}"
    candidates = list(text_files_under(path))
    if is_decision_record(where):
        candidates.extend(text_files_under(REPO / DECISION_FRAGMENTS))
    read_any = False
    for candidate in candidates:
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
        searched = (f"{where} or {DECISION_FRAGMENTS}/"
                    if is_decision_record(where) else where)
        return False, f"{pattern!r} is not in {searched}"
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


def accepted_environment_skips(suite: str, output: str) -> list[str]:
    """Every skip this machine's allow-list accepted, flattened to one line each.

    `skip_that_withholds_proof` answers "may this row be proven at all"; this
    answers "which skips did this machine have to accept", so the one place that
    decides can also be the one place that says it out loud. Returns [] when any
    skip withholds proof - that reason is `skip_that_withholds_proof`'s own, and
    it is printed as the row's failure instead.
    """
    if skip_that_withholds_proof(suite, output) is not None:
        return []
    return [" ".join(block.split()) for block in skip_blocks(output)]


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


def _suite_env(use_env_backend: bool = False) -> dict[str, str]:
    """The environment every `test:` row's suite is started with.

    THE DEFAULT IS HERMETIC, the contract `backend/run_suites.py:881-884` holds
    and this check did not. `JARVIS_BACKEND` is set for the owner's Windows
    account on this PC, pointing at the LIVE backend folder, and
    `backend/_where.py` puts that folder first on `sys.path` - so a `test:` row
    used to run its suite against live code without anyone typing anything. On
    2026-10-25 that reported claim MED-01 as no longer holding while the suite
    is 95/95 green against this checkout. So the ambient value is popped from
    the copy this returns and NEVER reaches a suite; `--use-env-backend` puts it
    back on purpose.

    THE MODEL LOADERS ARE OFFLINE IN EVERY RUN, the same six switches and values
    `backend/run_suites.py` forces (`OFFLINE_ENVS`, 2026-10-18). Without them a
    suite that imports the memory store could fetch a model from Hugging Face
    mid-run: on 2026-11-13 that spent two and a half minutes inside one turn of
    the Live settings parity suite and created an empty `memory.db`, which
    reddened claim C101 at the desk for something a suite run must never do.
    Forced, not defaulted - a download is not a choice a hermetic run gets.

    AND BYTECODE WRITING IS OFF (`NO_BYTECODE_ENVS`), the runner's own
    `PYTHONDONTWRITEBYTECODE=1` (run_suites.py:1452-1453). Without it a suite
    that imports a base-only module leaves `jarvis-backend/__pycache__`, and the
    very next check in the same sweep - `backend/test_base_matches_repo.py` -
    refuses a base carrying generated files. That was the desk's second register
    run red on D06 (2026-11-13): running the checks twice in a row must not make
    the second one fail.

    A line says which value was ignored, because silently ignoring a setting is
    its own surprise (the same sentence `run_suites.py` prints, adapted to this
    checker). Nothing here mutates `os.environ`: the caller passes the result to
    `subprocess.run(env=...)` for every suite, so a parent process cannot put the
    value back behind this function's own back.
    """
    env = dict(os.environ)
    env.update(OFFLINE_ENVS)
    env.update(NO_BYTECODE_ENVS)
    if use_env_backend:
        return env
    ambient = env.pop("JARVIS_BACKEND", None)
    if ambient:
        print(f"[check_claims] Note: ignoring ambient JARVIS_BACKEND=\"{ambient}\" "
              f"(running every test: row against this checkout; pass "
              f"{USE_ENV_BACKEND_FLAG} to test the live folder)")
    return env


def check_test(suite: str, env: dict[str, str] | None = None):
    """Run one suite. Exiting 0 is necessary, never sufficient: a suite that
    printed a skip about the code (not about this machine) did not run that
    check, so it did not prove the row. See A SKIP IS NOT PROOF in the module
    docstring.

    `env` is the environment to start the suite with - `main` builds it ONCE
    through `_suite_env`, so the note about the ignored ambient value is printed
    once rather than once per row. Nothing is inherited implicitly: `env=` is
    always passed, so the ambient `JARVIS_BACKEND` cannot reach a suite even
    from a parent process.
    """
    candidates = [REPO / suite, REPO / "backend" / suite]
    if not suite.endswith(".py"):
        candidates = [REPO / "backend" / (suite + ".py")] + candidates
    chosen = next((p for p in candidates if p.is_file()), None)
    if chosen is None:
        return False, f"no suite file called {suite!r}"
    if env is None:
        env = _suite_env()
    try:
        done = subprocess.run(
            [sys.executable, str(chosen)], cwd=str(REPO),
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=TEST_TIMEOUT, env=env)
    except subprocess.TimeoutExpired:
        return False, f"{suite} did not finish within {TEST_TIMEOUT}s"
    except OSError as err:
        return False, f"{suite} could not be run ({err})"
    if done.returncode == 0:
        suite_relative = relative(chosen)
        combined = (done.stdout or "") + "\n" + (done.stderr or "")
        why = skip_that_withholds_proof(suite_relative, combined)
        if why is not None:
            return False, f"{suite} exited 0 but SKIPPED: {why}"
        # An allowed skip is still a skip: collect it so `main` can name it and
        # count the rows that rest on it, whether or not `-v` was typed. The row
        # stays proven because the reason is a limit of this machine - but the
        # check it skipped did NOT run, and nothing here may read as a pass.
        accepted = accepted_environment_skips(suite_relative, combined)
        if accepted:
            line = " | ".join(accepted)
            ACCEPTED_ENVIRONMENT_SKIPS.append((suite_relative, line))
            return True, f"{suite} exits 0, with a skip this machine cannot run: {line}"
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


def run_row(row: dict, env: dict[str, str] | None = None):
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
        return check_test(*args, env=env)
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


def _parser() -> argparse.ArgumentParser:
    """The command line, in one place.

    A function rather than a few lines inside `main` so a test can ask the
    checker's OWN parser about `--use-env-backend` without running a single
    suite: the flag existing and the flag working are two different claims, and
    `backend/test_claims.py` proves both.
    """
    parser = argparse.ArgumentParser(
        prog="check_claims.py",
        description="Check every claim in docs/CLAIMS.tsv against the code, in "
                    "both directions.")
    parser.add_argument("--list", action="store_true", dest="listing",
                        help="print every row that was checked, so 'nothing is "
                             "wrong' can be told apart from 'nothing was looked "
                             "at'")
    parser.add_argument("-v", action="store_true", dest="verbose",
                        help="print one line per row (implied by --list)")
    parser.add_argument(USE_ENV_BACKEND_FLAG, action="store_true",
                        dest="use_env_backend",
                        help="run each test: row's suite against the backend "
                             "folder JARVIS_BACKEND names - the LIVE folder - "
                             "instead of this checkout. Without it that ambient "
                             "value is ignored, the way backend/run_suites.py "
                             "ignores it")
    # An optional path, defaulting to this repository's register. It exists so
    # backend/test_claims.py can point the check at a temporary file carrying
    # one broken row of each kind and prove both directions really do fail. A
    # path that is not there is a finding, never a quiet fallback to the real
    # register - that would be a green run that checked something else.
    parser.add_argument("register", nargs="?", default=None,
                        help="the register to check (default: docs/CLAIMS.tsv)")
    # A copy of the repository to judge paths against, defaulting to this
    # checkout. Added 2026-10-28 for one thing only: a temp repository where
    # `docs/DECISIONS.md` and a `decisions.d/` fragment disagree, so the rule
    # that the decision record is read in BOTH places is proved end to end
    # instead of asserted. Pointing this at the wrong folder cannot pass, only
    # fail differently - every row is then answered about that folder.
    parser.add_argument("--repo", default=None,
                        help="the repository to judge paths against (default: "
                             "this checkout)")
    return parser


def main() -> int:
    global REPO
    args = _parser().parse_args()
    listing = args.listing
    verbose = listing or args.verbose
    if args.repo:
        REPO = Path(args.repo).resolve()
    register = (Path(args.register) if args.register
                else REPO / "docs" / "CLAIMS.tsv")
    if not register.is_absolute():
        register = (Path.cwd() / register).resolve()

    # ONE environment for every `test:` row, built before any suite runs and
    # used only through `subprocess.run(env=...)`. The ambient `JARVIS_BACKEND`
    # is gone unless `--use-env-backend` asked for it, and one line says so when
    # it was there - the contract `backend/run_suites.py:881-884` has held since
    # 2026-10-21, which this check did not (2026-10-25). Built here, once, so
    # the note is printed once rather than once per row.
    suite_env = _suite_env(args.use_env_backend)
    # A second `main()` in one process (a test) starts with no skips carried over
    # from the first.
    ACCEPTED_ENVIRONMENT_SKIPS.clear()

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
    rows_on_environment_skips: list[tuple[dict, str, str]] = []

    for row in rows:
        counts[row["state"]] = counts.get(row["state"], 0) + 1
        if row["state"] == "unverifiable":
            if listing:
                print(f"  {row['id']:<7} unverifiable  {row['claim']}")
                print(f"          cannot be checked: {row['check']}")
            continue
        # Which skips this row's suite had to accept, if any: `check_test` collects
        # them, and the difference is this row's own (2026-11-13).
        accepted_before = len(ACCEPTED_ENVIRONMENT_SKIPS)
        passed, detail = run_row(row, env=suite_env)
        if len(ACCEPTED_ENVIRONMENT_SKIPS) > accepted_before:
            suite, line = ACCEPTED_ENVIRONMENT_SKIPS[-1]
            rows_on_environment_skips.append((row, suite, line))
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

    # A skip this machine cannot avoid still buys the row its proof - but it did
    # not run, and the project's rule is that a skip is never a pass. So it is
    # named here, with its reason, and the rows that rest on it are counted, on
    # EVERY run and not only with `-v` (2026-11-13).
    if rows_on_environment_skips:
        by_suite: dict[str, tuple[str, list[str]]] = {}
        for row, suite, line in rows_on_environment_skips:
            by_suite.setdefault(suite, (line, []))[1].append(row["id"])
        print(f"{len(rows_on_environment_skips)} claim row(s) name a suite that "
              f"SKIPPED a check this machine cannot run - that check was NOT "
              f"looked at, and it is NOT counted as a pass:")
        for suite, (line, ids) in by_suite.items():
            print(f"  {suite}  (rows {', '.join(ids)})")
            print(f"      skip:  {line}")

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
