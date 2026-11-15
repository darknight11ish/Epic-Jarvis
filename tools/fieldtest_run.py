#!/usr/bin/env python3
"""fieldtest_run.py - run the six field-test checks and write the one honest report.

    py -3 -B tools/fieldtest_run.py --check 2
    py -3 -B tools/fieldtest_run.py --check 2 --check 6
    py -3 -B tools/fieldtest_run.py --all
    py -3 -B tools/fieldtest_run.py --all --allow-stale

WHY THIS EXISTS
    A field test is only worth the evidence behind it. The old way was to open
    the report in a text editor and type PASS beside six remembered checks, and a
    row written from memory is worth nothing: this repository's standing rule is
    that a feature that was not driven on the real desktop or the real phone is
    BLOCKED, PARTIAL or NOT-TESTABLE, and that **BLOCKED is never counted as a
    pass** (`docs/DECISIONS.md`, 2026-10-11). This runner writes the report from
    what it actually ran: every numbered check gets a verdict, the command that
    was run, and that command's output, so the next reader can repeat it.

THE STALE GATE (it refuses before it runs anything)
    A field test on a stale backend says nothing about `origin/main`, so the
    runner first reads the commit the live install was sealed from - the
    `resealed.commit` that `tools/reseal_live_install.py` writes into
    `_jarvis-state.json` beside the backend - and compares it with
    `git rev-parse origin/main`. **If they differ, nothing runs**: it names both
    commits and exits 2, because a refusal is a blocked run, not a pass. Pass
    `--allow-stale` when a known-stale build is deliberately being tested; the
    report then says so at the top and every row below is about that build.

    An UNREADABLE record is refused too, and `--allow-stale` does not cover it:
    `--allow-stale` permits a known difference, never an unknown. The message
    names the file to fix (`tools/reseal_live_install.py` is what writes it).

THE SIX CHECKS
    1. Coder chat window                 - needs the owner's hands
    2. GitHub CI truth + merge truth      - this runner runs it
    3. The 2 GiB send-to-phone path       - needs the phone
    4. Phone Local-AI truth               - needs the phone
    5. Paired-device awareness            - needs the phone
    6. Preflight + provenance             - this runner runs it

    A check that needs the phone or the owner's hands is recorded BLOCKED with
    the reason, never PASS - the runner cannot see a window, send a file, press
    Approve, or read the handset's own model. Those rows are the point of the
    tool as much as the two it can settle: the report is honest about the four
    it cannot, instead of quietly calling them green.

    What the two automated checks do:
      * 2 reads the newest merge on `origin/main` with git, asks `gh` for that
        pull request's state, its merge commit and its check rollup, and passes
        only when the PR is MERGED, its merge commit IS the commit on
        `origin/main`, and all seven checks the GitHub ruleset requires
        (`rust`, `frontend`, `backend`, `backend-windows`, `credential-manager`,
        `powershell-5`, `phone-unit-tests` - measured from ruleset 24677804)
        report SUCCESS. A missing check cannot be proved, so it is BLOCKED; a
        red one is FAIL.
      * 6 runs the live `backend/selftest.py --preflight` (with `JARVIS_BACKEND`
        set to `--backend-path`, the same folder the gate read) and compares the
        live `VERSION` file with the installed desktop's FileVersion, the one
        pair that has silently disagreed before (wave 6, 2026-11-06). PASS needs
        0 preflight failures AND the two version numbers equal; either could not
        be read -> BLOCKED; a contradiction -> FAIL.

THE FOUR VERDICTS AND THE EXIT CODE
    PASS     the check was driven and its evidence is in this report;
    FAIL     the check was driven and the thing it checks is wrong;
    BLOCKED  it could not be driven (phone, owner's hands, unreadable evidence);
    PARTIAL  part of it was driven and part could not be.

        exit 0   every requested check is PASS
        exit 1   any requested check FAILED (even if others were BLOCKED)
        exit 2   any requested check is BLOCKED or PARTIAL and none FAILED -
                 and also the stale/refusal exit, because a run that never
                 started is not a pass either.

    A PASS with no command and no output is refused when its Result is built:
    a report row may not claim a pass it cannot show.

THE REPORT
    `C:\\Users\\pcadmin\\Downloads\\FIELD-TEST-<YYYY-MM-DD-HHMM>.md`
    (`--out-dir` moves it). It always has SIX rows - a check that was not
    requested in this run says `not requested` and is never counted - then an
    evidence index with one numbered entry per command and per conclusion. If a
    report for the same minute already exists it is never overwritten: the new
    one takes `-2`, `-3`, and the path this run prints is the path it wrote.

TESTS
    `backend/test_fieldtest_run.py` proves the stale refusal and its
    `--allow-stale` override, the exit-code contract (a blocked check is 2 and
    never 0), that a PASS row carries its command and output in the evidence
    index, the six-row shape, and the report path - with every reader and every
    check injected, so no test calls the live backend, the network, `gh`, or a
    real check.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, Sequence

#: The owner's live backend folder: the one holding `jarvis_hud.py` and the
#: `_jarvis-state.json` record this runner reads. `--backend-path` overrides it.
DEFAULT_BACKEND_PATH = Path(
    "C:/Users/pcadmin/Documents/Claude/Open jarvis files/Desktop program")

#: Where the report lands: the owner reads Downloads, and the earlier field-test
#: records live there too. `--out-dir` overrides it.
DEFAULT_OUT_DIR = Path("C:/Users/pcadmin/Downloads")

#: The ref the live commit is compared with. `--main-ref` overrides it.
DEFAULT_MAIN_REF = "origin/main"

#: The deploy record beside the live backend. `resealed.commit` is the commit
#: `tools/reseal_live_install.py` last sealed the folder from.
STATE_FILE = "_jarvis-state.json"

#: The file the in-app updater writes; check 6 compares it with the desktop's
#: FileVersion. Both names are the ones `tools/check_live_version_identity.py`
#: uses, so the two tools always compare the same pair.
VERSION_FILE = "VERSION"
DESKTOP_EXE_ENV = "JARVIS_DESKTOP_EXE"
DEFAULT_DESKTOP_DIR = "Jarvis Desktop"
DESKTOP_EXE_NAME = "jarvis-desktop.exe"

REPORT_PREFIX = "FIELD-TEST"

#: How long one command may take. The preflight asks the model a question, so it
#: is the slow one; a timeout is BLOCKED, never a pass.
COMMAND_TIMEOUT = 600

#: Most characters of one command's output kept in the evidence index. The full
#: output is on the terminal the run was started from.
EVIDENCE_LIMIT = 8000

#: The four verdicts. There is no fifth: "not run" is BLOCKED with a reason.
PASS = "PASS"
FAIL = "FAIL"
BLOCKED = "BLOCKED"
PARTIAL = "PARTIAL"
VERDICTS = (PASS, FAIL, BLOCKED, PARTIAL)

#: The seven checks the GitHub ruleset requires before a pull request may merge
#: (ruleset 24677804, "protect", read from the ruleset itself on 2026-10-27).
#: Check 2 does not trust a merge because GitHub allowed it; it verifies these
#: seven really reported SUCCESS on the merged pull request.
REQUIRED_CHECKS = (
    "rust", "frontend", "backend", "backend-windows",
    "credential-manager", "powershell-5", "phone-unit-tests",
)

#: The word that marks a git subject as a GitHub pull-request merge.
MERGE_SUBJECT = re.compile(r"Merge pull request #(\d+)")

#: A commit-ish the live record may carry: full or short hex, never a ref name
#: like `origin/main` (which names whatever that ref is NOW, not what was sealed).
HEX_COMMIT = re.compile(r"[0-9a-fA-F]{7,40}")


@dataclass(frozen=True)
class Check:
    """One numbered check: what it is called, and what driving it needs."""

    number: int
    title: str
    #: "this PC" when the runner can drive it itself; otherwise the thing whose
    #: absence makes the row BLOCKED, worded for a reader.
    needs: str
    #: Required for a check this runner cannot drive; the report's evidence entry
    #: for a BLOCKED row is this text, verbatim.
    blocked: str = ""


CHECKS = (
    Check(1, "Coder chat window", "the owner's hands",
          "Needs the desktop app and the owner's eyes: open Atlas, select the "
          "Coding preset in the chat window and ask one coding question. The "
          "runner cannot see a window or judge an answer, and an unobserved "
          "window is not a pass. Put the window title, the model the reply names "
          "and the answer into the report by hand."),
    Check(2, "GitHub CI truth + merge truth", "this PC"),
    Check(3, "The 2 GiB send-to-phone path", "the phone",
          "Needs the phone and an owner-approved card: send a file from the "
          "phone (any type, up to 2 GiB); the `receive_uploaded_document` card "
          "must be approved on the phone by the owner - a machine must never "
          "press Approve - and the file must land. The runner will not send, "
          "approve or read the phone, so this row waits for your hands."),
    Check(4, "Phone Local-AI truth", "the phone",
          "Needs the installed phone: whether a Local-AI answer is really "
          "produced on the handset cannot be observed from the PC. Select "
          "Local-AI on the phone, ask one question, and check the answer against "
          "the phone's own model. Nothing the runner can run proves this."),
    Check(5, "Paired-device awareness", "the phone",
          "Needs the paired phone, powered and reachable: awareness is the "
          "desktop seeing the handset in its device list. The runner has no "
          "paired device to look at, and will not invent one."),
    Check(6, "Preflight + provenance", "this PC"),
)

CHECKS_BY_NUMBER = {check.number: check for check in CHECKS}


@dataclass(frozen=True)
class LiveIdentity:
    """What the live install's own record says it was sealed from."""

    commit: str
    resealed_at: str = ""
    tool: str = ""
    source: str = ""


@dataclass(frozen=True)
class Run:
    """One command that was actually run, with the output it produced."""

    command: str
    exit_code: int
    output: str


@dataclass(frozen=True)
class Result:
    """One check's verdict, its evidence, and why.

    The contract is enforced here rather than trusted: a PASS without a command
    and its output cannot be constructed, and every non-PASS has to say why. A
    check that raises is turned into BLOCKED by `collect`, so a bug in a check
    can never become a green row.
    """

    status: str
    reason: str = ""
    runs: tuple = ()

    def __post_init__(self):
        if self.status not in VERDICTS:
            raise ValueError(
                f"unknown verdict {self.status!r}; the four are {', '.join(VERDICTS)}")
        if self.status == PASS and not self.runs:
            raise ValueError(
                "a PASS must carry the command it ran and that command's output; "
                "a pass with no evidence is not a pass")
        if self.status != PASS and not str(self.reason).strip():
            raise ValueError(f"a {self.status} must say why")


@dataclass(frozen=True)
class Context:
    """Everything a check may read: the paths, the commits, and the stale flag."""

    backend_path: Path
    repo: Path
    live: LiveIdentity
    main_commit: str
    stale_allowed: bool
    main_ref: str = DEFAULT_MAIN_REF
    desktop_exe: Path = Path("")


# ==========================================================================
#   Reading the evidence the reports are built from
# ==========================================================================

def repo_root() -> Path:
    """This repository: the tool lives in `tools/`, so its parent is the root."""
    return Path(__file__).resolve().parent.parent


def read_live_identity(backend_path) -> Optional[LiveIdentity]:
    """The live record's sealed commit, or None when there is nothing to prove.

    `resealed.commit` is preferred because it is a commit, not a ref name. The
    `resealed.ref` fallback is used only when it is a hex commit - a record
    saying `origin/main` says what main was at some time, not which commit the
    folder holds, and resolving that ref now would claim a freshness nobody
    measured. A missing file, broken JSON, a record with no `resealed` block and
    an empty value all read as None: unreadable evidence, never a pass.
    """
    path = Path(backend_path) / STATE_FILE
    try:
        if not path.is_file():
            return None
        doc = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return None
    sealed = doc.get("resealed") if isinstance(doc, dict) else None
    if not isinstance(sealed, dict):
        return None
    commit = str(sealed.get("commit") or "").strip()
    if not commit:
        candidate = str(sealed.get("ref") or "").strip()
        commit = candidate if HEX_COMMIT.fullmatch(candidate) else ""
    if not HEX_COMMIT.fullmatch(commit):
        return None
    return LiveIdentity(commit=commit,
                        resealed_at=str(sealed.get("at") or "").strip(),
                        tool=str(sealed.get("tool") or "").strip(),
                        source=str(path))


def read_main_commit(repo, ref=DEFAULT_MAIN_REF) -> str:
    """The full commit `ref` names in `repo`, or "" when git cannot resolve it."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--verify", "--quiet",
             f"{ref}^{{commit}}"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=60)
    except (OSError, subprocess.SubprocessError):
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""


def same_commit(one: str, other: str) -> bool:
    """True when two hex commits name the same commit, short or full."""
    one, other = str(one).strip().lower(), str(other).strip().lower()
    if not one or not other:
        return False
    if one == other:
        return True
    short, longer = (one, other) if len(one) <= len(other) else (other, one)
    return len(short) >= 7 and longer.startswith(short)


def desktop_exe_path() -> Path:
    """The installed desktop whose FileVersion is the release identity.

    The same default and the same `JARVIS_DESKTOP_EXE` override as
    `tools/check_live_version_identity.py`, so the deploy's identity check and
    this provenance row always read the same program.
    """
    env = os.environ.get(DESKTOP_EXE_ENV, "").strip()
    if env:
        return Path(env)
    local = os.environ.get("LOCALAPPDATA", "").strip()
    base = Path(local) if local else Path(os.path.expanduser("~")) / "AppData" / "Local"
    return base / DEFAULT_DESKTOP_DIR / DESKTOP_EXE_NAME


# ==========================================================================
#   Running one command, with its output kept for the evidence index
# ==========================================================================

def _display(argv) -> str:
    """The command as a person can paste it back into a terminal."""
    args = [str(part) for part in argv]
    return subprocess.list2cmdline(args) if os.name == "nt" else shlex.join(args)


def _invoke(argv, *, cwd=None, timeout=COMMAND_TIMEOUT, env=None):
    """Run one command; return (shown command, exit code, stdout, error text).

    Never raises: a missing program is exit 127, an unstartable one 126 and a
    timeout 124, each with a sentence saying which, because those become the
    report's evidence instead of a traceback.
    """
    shown = _display(argv)
    try:
        proc = subprocess.run(
            [str(part) for part in argv],
            cwd=str(cwd) if cwd else None,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, env=env)
    except FileNotFoundError:
        return shown, 127, "", f"{argv[0]} is not on PATH"
    except subprocess.TimeoutExpired as exc:
        partial = exc.stdout or ""
        if isinstance(partial, bytes):
            partial = partial.decode("utf-8", "replace")
        return (shown, 124, str(partial),
                f"timed out after {timeout} seconds")
    except (OSError, subprocess.SubprocessError) as exc:
        return shown, 126, "", f"could not be started: {exc}"
    return shown, proc.returncode, proc.stdout or "", proc.stderr or ""


def run_command(argv, *, cwd=None, timeout=COMMAND_TIMEOUT, env=None) -> Run:
    """One command as a Run; stdout and stderr are kept together for the report."""
    command, code, stdout, stderr = _invoke(argv, cwd=cwd, timeout=timeout, env=env)
    output = (stdout + stderr).strip()
    return Run(command, code, output)


def run_json(argv, *, cwd=None, timeout=COMMAND_TIMEOUT, env=None):
    """One command that should print JSON; returns (Run, parsed object or None).

    stdout is parsed alone, so a warning on stderr cannot corrupt a good answer.
    """
    command, code, stdout, stderr = _invoke(argv, cwd=cwd, timeout=timeout, env=env)
    run = Run(command, code, (stdout + stderr).strip())
    doc = None
    if code == 0 and stdout.strip():
        try:
            doc = json.loads(stdout)
        except ValueError:
            doc = None
    return run, doc


# ==========================================================================
#   Check 2: GitHub's story against git's own record
# ==========================================================================

def _check_verdict(entry) -> str:
    """A rollup entry's SUCCESS/FAILURE/SKIPPED, whichever field carries it."""
    if not isinstance(entry, dict):
        return ""
    for key in ("conclusion", "state"):
        got = str(entry.get(key) or "").strip().upper()
        if got:
            return got
    return ""


def check_github(ctx: Context) -> Result:
    """PR state + merge commit + the seven required checks, verified not trusted."""
    git = ["git", "-C", str(ctx.repo)]
    runs = []

    main = run_command(git + ["rev-parse", "--verify", f"{ctx.main_ref}^{{commit}}"])
    runs.append(main)
    if main.exit_code != 0 or not main.output:
        return Result(BLOCKED,
                      f"git cannot resolve {ctx.main_ref} in {ctx.repo}, so there is "
                      "no merge truth to compare GitHub with.", tuple(runs))
    main_sha = main.output.splitlines()[0].strip()

    merge = run_command(git + ["log", "--merges", "-1", "--format=%H %s", main_sha])
    runs.append(merge)
    if merge.exit_code != 0:
        return Result(BLOCKED, f"git cannot list the merges on {ctx.main_ref}: "
                               f"{merge.output[:300]}", tuple(runs))
    first = merge.output.splitlines()[0].strip() if merge.output else ""
    parts = first.split(" ", 1)
    if not first or not parts[0]:
        return Result(BLOCKED,
                      f"{ctx.main_ref} has no merge commit to check - GitHub CI and "
                      "merge truth cannot be proved from it.", tuple(runs))
    merge_sha, subject = parts[0], (parts[1] if len(parts) > 1 else "")
    found = MERGE_SUBJECT.search(subject)
    if not found:
        return Result(BLOCKED,
                      f"the newest merge on {ctx.main_ref} is {merge_sha} with the "
                      f"subject {subject!r}, which names no pull request.", tuple(runs))
    number = int(found.group(1))

    pr_run, doc = run_json(
        ["gh", "pr", "view", str(number), "--json",
         "number,state,mergeCommit,mergedAt,statusCheckRollup"],
        cwd=ctx.repo)
    runs.append(pr_run)
    if pr_run.exit_code != 0:
        return Result(BLOCKED,
                      "gh could not read the pull request, so GitHub's own claim "
                      "cannot be checked (is gh installed and signed in?): "
                      f"{pr_run.output[:300]}", tuple(runs))
    if not isinstance(doc, dict):
        return Result(BLOCKED,
                      f"gh answered for PR #{number} with something that is not JSON.",
                      tuple(runs))

    if str(doc.get("state") or "").upper() != "MERGED":
        return Result(FAIL,
                      f"GitHub says PR #{number} is {doc.get('state')!r}, not MERGED, "
                      "while its merge commit is what the newest merge on "
                      f"{ctx.main_ref} points at.", tuple(runs))

    merged = doc.get("mergeCommit") if isinstance(doc.get("mergeCommit"), dict) else {}
    merged_sha = str(merged.get("oid") or "").strip()
    if not merged_sha:
        return Result(BLOCKED,
                      f"GitHub did not name a merge commit for PR #{number}, so the "
                      "merge truth cannot be checked.", tuple(runs))
    if not same_commit(merged_sha, merge_sha):
        return Result(FAIL,
                      f"GitHub says PR #{number} merged as {merged_sha}, but the "
                      f"newest merge on {ctx.main_ref} is {merge_sha} - the checked "
                      "commit is not the one that landed.", tuple(runs))

    rollup = doc.get("statusCheckRollup")
    entries = rollup if isinstance(rollup, list) else []
    verdicts = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or entry.get("context") or "").strip()
        if name:
            verdicts[name] = _check_verdict(entry)
    missing = [name for name in REQUIRED_CHECKS if name not in verdicts]
    if missing:
        return Result(BLOCKED,
                      f"GitHub's rollup for PR #{number} does not name "
                      f"{', '.join(missing)} - a check that cannot be read cannot be "
                      "proved to have passed.", tuple(runs))
    red = [f"{name}={verdicts[name] or 'no conclusion'}" for name in REQUIRED_CHECKS
           if verdicts[name] != "SUCCESS"]
    if red:
        return Result(FAIL,
                      f"PR #{number} is merged as {merge_sha}, but the required "
                      f"checks did not all succeed: {', '.join(red)}.", tuple(runs))

    return Result(PASS,
                  f"PR #{number} is MERGED as {merge_sha}, the same commit the newest "
                  f"merge on {ctx.main_ref} points at, and all seven required checks "
                  "report SUCCESS.", tuple(runs))


# ==========================================================================
#   Check 6: the preflight the deploy already trusts, plus where the build came from
# ==========================================================================

PREFLIGHT_SUMMARY = re.compile(
    r"(\d+)\s+pass\s*[,/]\s*(\d+)\s+fail\s*[,/]\s*(\d+)\s+warn", re.IGNORECASE)


def _powershell() -> str:
    for exe in ("powershell", "powershell.exe", "pwsh", "pwsh.exe"):
        found = shutil.which(exe)
        if found:
            return found
    return ""


def read_version_pair(ctx: Context):
    """Two real commands that read the live VERSION and the desktop's FileVersion.

    Each is its own PowerShell invocation so the evidence index shows a command a
    person can paste, rather than an in-process file read nobody can repeat.
    """
    ps = _powershell()
    if not ps:
        command = "powershell -NoProfile -Command \"...\""
        return (Run(command, 127, "no PowerShell on this host, so neither identity "
                                  "number can be read"),
                Run(command, 127, "no PowerShell on this host"))
    live_version = Path(ctx.backend_path) / VERSION_FILE
    quoted_live = str(live_version).replace("'", "''")
    quoted_exe = str(ctx.desktop_exe).replace("'", "''")
    first = run_command(
        [ps, "-NoProfile", "-NonInteractive", "-Command",
         f"Get-Content -LiteralPath '{quoted_live}' -Raw"], timeout=60)
    second = run_command(
        [ps, "-NoProfile", "-NonInteractive", "-Command",
         f"(Get-Item -LiteralPath '{quoted_exe}').VersionInfo.FileVersion"],
        timeout=60)
    return first, second


def check_preflight(ctx: Context) -> Result:
    """Preflight failures and an identity contradiction are the two ways this fails."""
    failures = []
    blocked = []
    runs = []

    version_run, exe_run = read_version_pair(ctx)
    runs.extend((version_run, exe_run))
    live_version = version_run.output.strip() if version_run.exit_code == 0 else ""
    exe_version = exe_run.output.strip() if exe_run.exit_code == 0 else ""
    if not live_version:
        blocked.append(f"the live {VERSION_FILE} could not be read at "
                       f"{Path(ctx.backend_path) / VERSION_FILE}")
    if not exe_version:
        blocked.append(f"the installed desktop's FileVersion could not be read at "
                       f"{ctx.desktop_exe}")
    if live_version and exe_version and live_version != exe_version:
        failures.append(f"the live {VERSION_FILE} says {live_version}, but the "
                        f"installed desktop is {exe_version} - the identity "
                        "mismatch the HUD shows as a banner")

    # The preflight's own patch and module rows read JARVIS_BACKEND; point them at
    # the same folder the stale gate just read from, so the two halves agree.
    preflight_env = dict(os.environ)
    preflight_env["JARVIS_BACKEND"] = str(ctx.backend_path)
    preflight = run_command(
        [sys.executable, "-B", "backend/selftest.py", "--preflight"],
        cwd=ctx.repo, env=preflight_env)
    runs.append(preflight)
    parsed = PREFLIGHT_SUMMARY.search(preflight.output)
    if parsed:
        _passed, failed, warned = (int(part) for part in parsed.groups())
        if failed or preflight.exit_code != 0:
            failures.append(f"the preflight reported {failed} failing check(s) "
                            f"(exit {preflight.exit_code})")
    elif preflight.exit_code == 0:
        blocked.append("the preflight's summary line could not be read, so 0 "
                       "failures cannot be proved")
    else:
        blocked.append(f"the preflight exited {preflight.exit_code} without a "
                       "readable summary")

    if failures:
        return Result(FAIL, "; ".join(failures + blocked), tuple(runs))
    if blocked:
        return Result(BLOCKED, "; ".join(blocked), tuple(runs))
    return Result(PASS,
                  f"the preflight reported {parsed.group(1)} pass / 0 fail "
                  f"({parsed.group(3)} warn), and the live {VERSION_FILE} "
                  f"{live_version} agrees with the installed desktop. Provenance: "
                  f"resealed at {ctx.live.resealed_at or 'an unrecorded time'} from "
                  f"{ctx.live.commit}.", tuple(runs))


def run_check(check: Check, ctx: Context) -> Result:
    """The real dispatcher: two checks are driven here, four wait for hands."""
    if check.number == 2:
        return check_github(ctx)
    if check.number == 6:
        return check_preflight(ctx)
    return Result(BLOCKED, check.blocked)


def collect(check: Check, ctx: Context,
            runner: Callable[[Check, Context], Result]) -> Result:
    """Run one check and turn a crash into BLOCKED - never into a pass."""
    try:
        result = runner(check, ctx)
    except Exception as exc:  # noqa: BLE001 - a check must not take the report down
        return Result(BLOCKED,
                      f"the check raised {type(exc).__name__}: {exc}; a check that "
                      "could not finish is BLOCKED, never a pass.")
    if not isinstance(result, Result):
        return Result(BLOCKED,
                      f"the check returned {type(result).__name__}, not a Result; "
                      "no verdict can be read from it, so it is BLOCKED.")
    return result


# ==========================================================================
#   The exit-code contract, in one place
# ==========================================================================

def exit_code_for(statuses: Sequence[str]) -> int:
    """0 all PASS, 1 any FAIL, 2 any BLOCKED/PARTIAL - FAIL outranks BLOCKED."""
    statuses = list(statuses)
    if FAIL in statuses:
        return 1
    if BLOCKED in statuses or PARTIAL in statuses:
        return 2
    return 0


def exit_sentence(code: int) -> str:
    if code == 1:
        return "a requested check FAILED."
    if code == 2:
        return ("a requested check was BLOCKED or PARTIAL and none failed - "
                "blocked is never a pass.")
    return "every requested check is PASS."


# ==========================================================================
#   The report
# ==========================================================================

def report_path(out_dir, now: datetime) -> Path:
    """`<out_dir>/FIELD-TEST-<YYYY-MM-DD-HHMM>.md` - the path this run writes."""
    return Path(out_dir) / f"{REPORT_PREFIX}-{now:%Y-%m-%d-%H%M}.md"


def next_report_path(out_dir, now: datetime) -> Path:
    """The report path, moved to `-2`, `-3`... rather than overwriting evidence."""
    path = report_path(out_dir, now)
    if not path.exists():
        return path
    number = 2
    while True:
        alternative = path.with_name(f"{path.stem}-{number}{path.suffix}")
        if not alternative.exists():
            return alternative
        number += 1


def _cell(text) -> str:
    """One markdown table cell: no newlines, no column-breaking pipes."""
    return " ".join(str(text).split()).replace("|", "\\|")


def _short(sha: str) -> str:
    return sha[:12] if len(sha) > 12 else sha


def _clip(text: str, limit: int = EVIDENCE_LIMIT) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + (f"\n... [truncated {len(text) - limit} more characters; "
                           "the full output is on the terminal that ran this]")


def _fence(text: str) -> str:
    """A backtick fence longer than any run of backticks inside the output."""
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    return "`" * max(3, longest + 1)


def render_report(*, now: datetime, backend_path, live: LiveIdentity,
                  main_commit: str, main_ref: str, repo, stale_allowed: bool,
                  requested: Sequence[int], results, exit_code: int,
                  path: Path) -> str:
    """The whole report: six rows, the counts, the evidence index, nothing invented."""
    requested = list(requested)
    counts = {verdict: 0 for verdict in VERDICTS}
    for number in requested:
        counts[results[number].status] += 1

    # Evidence is numbered in check order: each command, then each conclusion.
    entries = []          # (id, heading, run or None, reason or None)
    by_check = {}         # check number -> [evidence id]
    for number in requested:
        result = results[number]
        title = CHECKS_BY_NUMBER[number].title
        ids = []
        for run in result.runs:
            identifier = f"E{len(entries) + 1}"
            ids.append(identifier)
            entries.append((identifier, f"check {number} ({title}): the command it ran",
                            run, None))
        if result.reason:
            identifier = f"E{len(entries) + 1}"
            ids.append(identifier)
            entries.append((identifier,
                            f"check {number} ({title}): why this is {result.status}",
                            None, result.reason))
        by_check[number] = ids

    if stale_allowed:
        stale_line = (f"- **Stale allowed:** **yes** — this run measured a build "
                      f"that is NOT {main_ref}'s commit; every row below is about "
                      f"{_short(live.commit)}, not main.")
    else:
        stale_line = (f"- **Stale allowed:** no — the live backend is exactly "
                      f"{main_ref}'s commit.")
    if live.resealed_at:
        live_line = (f"- **Live backend:** `{backend_path}` at "
                     f"**{_short(live.commit)}**, resealed {live.resealed_at}"
                     + (f" by `{live.tool}`" if live.tool else "") + ".")
    else:
        live_line = (f"- **Live backend:** `{backend_path}` at "
                     f"**{_short(live.commit)}** (the record names no reseal time).")
    requested_line = ("- **Requested:** all six checks."
                      if len(requested) == len(CHECKS)
                      else "- **Requested:** check(s) "
                           + ", ".join(str(number) for number in requested) + ".")

    lines = [
        f"# FIELD TEST — {now:%Y-%m-%d %H:%M} (local time)",
        "",
        "A field test records what was driven on this PC and the real phone. A PASS "
        "is only something the runner observed itself: a check that needs the phone "
        "or the owner's hands is BLOCKED with the reason, and BLOCKED is never a "
        "pass.",
        "",
        live_line,
        f"- **{main_ref}:** **{_short(main_commit)}** in `{repo}`.",
        stale_line,
        requested_line,
        f"- **Report written:** `{path}`",
        f"- **Exit code:** {exit_code} — {exit_sentence(exit_code)}",
        "",
        "## The six rows",
        "",
        "| # | check | verdict | evidence |",
        "|---|---|---|---|",
    ]
    for check in CHECKS:
        if check.number in requested:
            result = results[check.number]
            evidence = ", ".join(by_check[check.number]) or "—"
            lines.append(f"| {check.number} | {check.title} | "
                         f"**{result.status}** | {_cell(evidence)} |")
        else:
            lines.append(f"| {check.number} | {check.title} | not requested | — |")
    lines += [
        "",
        "**Counts, over the requested checks:** "
        f"{counts[PASS]} PASS / {counts[FAIL]} FAIL / {counts[BLOCKED]} BLOCKED / "
        f"{counts[PARTIAL]} PARTIAL.",
        "",
        f"**Exit code {exit_code}:** {exit_sentence(exit_code)}",
        "",
        "## Evidence index",
        "",
        "Every entry below is something this run actually produced: a command as "
        "it was run with its exit code and output, or the reason a row could not "
        "be driven. Nothing here was reconstructed afterwards.",
    ]
    for identifier, heading, run, reason in entries:
        lines += ["", f"### {identifier} — {heading}", ""]
        if run is not None:
            lines += [f"    {run.command}", f"    exit {run.exit_code}", ""]
            output = _clip(run.output) if run.output else "(no output)"
            fence = _fence(output)
            lines += [fence + "text", output, fence]
        else:
            lines += [reason]
    lines.append("")
    return "\n".join(lines)


def write_report(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# ==========================================================================
#   The run
# ==========================================================================

def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the six field-test checks, refuse a stale backend, and "
                    "write the FIELD-TEST report to Downloads.",
        epilog="Exit 0 only when every requested check is PASS; 1 when any FAILED; "
               "2 when any was BLOCKED or PARTIAL and none failed, or when the "
               "stale gate refused the run.")
    parser.add_argument("--check", action="append", type=int,
                        choices=[check.number for check in CHECKS], default=None,
                        help="the check to run (1-6); repeat for more than one")
    parser.add_argument("--all", action="store_true",
                        help="run all six checks")
    parser.add_argument("--allow-stale", action="store_true",
                        help="run even though the live backend's commit differs "
                             "from origin/main; the report says so")
    parser.add_argument("--backend-path", default=str(DEFAULT_BACKEND_PATH),
                        help=f"the live backend folder holding {STATE_FILE} "
                             f"(default: {DEFAULT_BACKEND_PATH})")
    parser.add_argument("--main-ref", default=DEFAULT_MAIN_REF,
                        help=f"the ref the live commit is compared with "
                             f"(default: {DEFAULT_MAIN_REF})")
    parser.add_argument("--repo", default="",
                        help="the git checkout the ref is resolved in (default: "
                             "this tool's own repository)")
    parser.add_argument("--desktop-exe", default="",
                        help="the installed desktop whose FileVersion is the "
                             "release identity (default: the same path "
                             "tools/check_live_version_identity.py uses)")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR),
                        help=f"where the report lands (default: {DEFAULT_OUT_DIR})")
    return parser


def run(argv: Optional[Sequence[str]] = None, *,
        live_reader: Optional[Callable] = None,
        main_reader: Optional[Callable] = None,
        runner: Optional[Callable] = None,
        now: Optional[datetime] = None,
        out: Optional[Callable] = None) -> int:
    """The whole job: gate, checks, report, exit code. Every reader is injectable.

    `live_reader(backend_path)`, `main_reader(repo, ref)`, `runner(check, context)`
    and `now` are the tests' seams; with none of them given this reads the real
    record, the real git and runs the two real checks.
    """
    out = out or print
    now = now or datetime.now()
    namespace = _parser().parse_args(list(argv) if argv is not None else None)

    if namespace.all and namespace.check:
        out("choose one of --check N or --all, not both.")
        return 2
    if namespace.all:
        requested = [check.number for check in CHECKS]
    else:
        requested = sorted(set(namespace.check or ()))
    if not requested:
        out("choose --check N (1-6) or --all: this runner will not guess which "
            "checks to run.")
        return 2

    backend_path = Path(namespace.backend_path)
    repo = Path(namespace.repo) if namespace.repo else repo_root()
    read_live = live_reader or read_live_identity
    read_main = main_reader or read_main_commit

    live = read_live(backend_path)
    if live is None:
        out(f"REFUSED: no live commit can be read from "
            f"{backend_path / STATE_FILE} (no usable `resealed.commit`). A field "
            f"test that cannot name what is running proves nothing, so nothing ran. "
            f"Re-seal the live install (tools/reseal_live_install.py) and re-run; "
            f"--allow-stale does not cover an unknown build.")
        return 2
    main_commit = read_main(repo, namespace.main_ref)
    if not main_commit:
        out(f"REFUSED: git cannot resolve {namespace.main_ref} in {repo}, so the "
            f"live commit cannot be compared with it. Nothing ran.")
        return 2
    if not same_commit(live.commit, main_commit) and not namespace.allow_stale:
        out(f"REFUSED: the live backend is at {live.commit}, but "
            f"{namespace.main_ref} is {main_commit}. A field test on a stale backend "
            f"says nothing about {namespace.main_ref}, so nothing ran. Deploy first "
            f"(tools/reconcile_live_backend.py), or pass --allow-stale to measure the "
            f"gap on purpose.")
        return 2

    context = Context(
        backend_path=backend_path, repo=repo, live=live,
        main_commit=main_commit, stale_allowed=namespace.allow_stale,
        main_ref=namespace.main_ref,
        desktop_exe=Path(namespace.desktop_exe) if namespace.desktop_exe
        else desktop_exe_path())

    out(f"FIELD TEST — {now:%Y-%m-%d %H:%M} (local time)")
    out(f"Live backend: {_short(live.commit)}   {namespace.main_ref}: "
        f"{_short(main_commit)}"
        + ("   (STALE, allowed)" if namespace.allow_stale
           and not same_commit(live.commit, main_commit) else ""))
    out("")

    results = {}
    run_one = runner or run_check
    for number in requested:
        check = CHECKS_BY_NUMBER[number]
        result = collect(check, context, run_one)
        results[number] = result
        detail = f" — {result.reason.splitlines()[0][:160]}" if result.reason else ""
        out(f"[{number}] {check.title} ... {result.status}{detail}")
    out("")

    code = exit_code_for([results[number].status for number in requested])
    counts = {verdict: 0 for verdict in VERDICTS}
    for number in requested:
        counts[results[number].status] += 1
    out(f"Verdicts: {counts[PASS]} PASS / {counts[FAIL]} FAIL / "
        f"{counts[BLOCKED]} BLOCKED / {counts[PARTIAL]} PARTIAL")
    out(f"Exit code: {code} — {exit_sentence(code)}")

    path = next_report_path(Path(namespace.out_dir), now)
    text = render_report(now=now, backend_path=backend_path, live=live,
                         main_commit=main_commit, main_ref=namespace.main_ref,
                         repo=repo, stale_allowed=namespace.allow_stale,
                         requested=requested, results=results, exit_code=code,
                         path=path)
    try:
        write_report(path, text)
    except OSError as exc:
        out(f"REFUSED: the report could not be written to {path}: {exc}. A run whose "
            f"evidence cannot be saved is not a finished run.")
        return 2
    out(f"Report: {path}")
    return code


def main(argv: Optional[Sequence[str]] = None, **seams) -> int:
    """The command line, with the same seams `run` takes for the tests."""
    return run(argv, **seams)


if __name__ == "__main__":
    sys.exit(main())
