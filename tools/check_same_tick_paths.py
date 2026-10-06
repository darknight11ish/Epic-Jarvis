#!/usr/bin/env python3
"""Find a filesystem path named from a clock, then created without `exist_ok`.

    python3 tools/check_same_tick_paths.py [-v] [path ...]

THE BUG THIS EXISTS FOR. A name taken from a clock is much less unique than it
looks, because on Windows the clock does not move on every call:

  * `time.time_ns()` is `GetSystemTimeAsFileTime`: 100-nanosecond UNITS, but the
    value only changes on the system timer tick - 15.6 ms by default. Two calls
    inside one tick return the SAME number. Measured on the owner's PC
    (2026-10-05): 399 of 399 consecutive `time.time_ns()` calls were identical,
    and one throwaway name asked for twice in a row came out the same 200 times
    out of 200.
  * `time.time()` and `time.monotonic()` move with that same tick, and only to
    about a millisecond.
  * `time.strftime("%Y%m%d-%H%M%S")` and `datetime.now()` are good for ONE
    SECOND - a loop, or two helpers called back to back, land inside the same
    second.

`time.perf_counter()` is in the list as well even though Windows measures it
with `QueryPerformanceCounter`, which really is fine-grained: a path named from
ANY clock is the shape this check exists to stop, and the safe fix for all of
them is the same one. That is the only entry here that is not tick-coarse.

So `d = tmp / f"job{time.time_ns()}"; d.mkdir()` does not make a fresh folder.
Called twice inside one tick, the second call asks for the folder the first one
just made, and `mkdir` raises `FileExistsError: [WinError 183]` - or, with
`exist_ok=True`, the second caller silently shares the first caller's folder.

This is not hypothetical. It broke three Windows CI suites for real:

  test_note_capture.py     graph()      -> `(_TMP / f"graph{ns}") / "logseq"`
  test_obsidian_notes.py   vault(), _graph()
  test_backup.py           fresh_conf()

each dying with `FileExistsError: [WinError 183]` on a `mkdir(parents=True)`
line (run 37349552106 job 111896626984, and run 37369387182 job 111962928099
for test_backup.py). None of it reproduced on the owner's PC, where the timer
tick is about 0.5 ms. All three were fixed with `tempfile.mkdtemp`, which asks
the filesystem for a free name instead of asking the clock for one.

WHAT IT LOOKS FOR, exactly:

  1. a COARSE CLOCK call - `time.time`, `time.time_ns`, `time.monotonic`,
     `time.monotonic_ns`, `time.perf_counter`, `time.perf_counter_ns`,
     `time.strftime`, `time.gmtime`, `time.localtime`, `datetime.now`,
     `datetime.utcnow`, `datetime.today`, or a local `now()` / `clock()` /
     `today()` helper (the test doubles that fake a clock are called these);
  2. whose result reaches a FILESYSTEM NAME - directly, or through a name that
     was assigned from it EARLIER IN THE SAME SCOPE, so
     `stamp = time.strftime(...)` then `d = root / stamp` then `d.mkdir()` is
     caught as well as the one-liner. Re-binding the name to something that is
     not from a clock clears it again, which is what keeps `v = mkdtemp()` and
     a later `v = ...time.time_ns()...` in one file from being confused;
  3. and that name is CREATED without `exist_ok`: `.mkdir(...)`,
     `os.makedirs(...)`, or `open(name, "x")` / `.open("x")` (the
     exclusive-create modes, which raise `FileExistsError` by contract).

WHAT IT DELIBERATELY DOES NOT FLAG, and why that is the point of the check:

  * a clock used only as a LABEL - `{"created": time.time()}` in a row, a
    timestamp inside a log line, an `at`/`since`/`deadline` value, a cache key
    tuple like `(size, st_mtime_ns)`. None of these is a name, and two equal
    ones are harmless.
  * a clock-named file that is OPENED FOR APPEND or OVERWRITE (`"a"`, `"w"`).
    Two calls inside one tick share the file, which may be wrong for other
    reasons, but nothing is created exclusively and nothing raises.
  * a clock-named path whose creation passes `exist_ok`, or whose creation is
    `tempfile.mkdtemp` / `NamedTemporaryFile` / `TemporaryDirectory` - the
    fixes themselves, which ask the filesystem for a free name.
  * `x.parent.mkdir(...)`: a clock in the LEAF name does not make the parent
    directory clock-named, so a state file called `f"{ns}.json"` must not make
    the fixed folder holding it a finding.
  * a name that came in as a function PARAMETER. Whether the caller named it
    from a clock is not visible from here, and guessing would be this check
    inventing a violation. That is the one shape this check can miss, and it is
    written down rather than papered over.

THE POWERSHELL HALF, and why it is not the same bug. `scripts/apply-patches.ps1`
- the one script the owner runs by hand after every merge - named its throwaway
folders from the clock the same way, in one variable:

    $Stamp     = Get-Date -Format 'yyyy-MM-dd-HHmmss'
    $rehearsal = Join-Path ([IO.Path]::GetTempPath()) "jarvis-rehearsal-$Stamp"
    Remove-Item -LiteralPath $rehearsal -Recurse -Force

Two runs started in the same second therefore did not merely fail to create one
folder: the second run DELETED the first run's folder out from under it while the
first run was still applying patches in it. Measured on this script, 2026-10-06,
with a doubled clock forcing both runs into one second: one run ended
`jarvis-rehearsal-2026-01-01-000000' because it is being used by another
process`, and both runs wrote one transcript file. A run that loses its rehearsal
half-way is the one step that can leave the owner's install half-patched.
`backend/test_apply_run_isolation.py` is the behaviour regression; this is the
guard that catches the next one by reading, before anyone runs it.

So a `.ps1` file is read LINE BY LINE - not parsed. PowerShell is not Python, and
a half-parser pretending to be one would be worse than a documented narrow rule.
The rule is the same two parts:

  1. a variable assigned from a coarse clock (`Get-Date`, `[datetime]::Now`,
     `[datetime]::UtcNow`, `[datetime]::Today`), or from another variable that
     was, so `$Stamp` then `$rehearsal = ...$Stamp...` is caught as well as a
     one-liner. A GUID (`[guid]::NewGuid()`, `GetRandomFileName`), `$PID`, or
     `Get-Random` in the same expression really does make the name unique and
     clears it. A MILLISECOND FORMAT DOES NOT: `Get-Date -Format '...fff'` reads
     the same tick-coarse clock the Python half documents above.
  2. and a line that CREATES or DELETES a path - `New-Item`, `mkdir`/`md`,
     `[IO.Directory]::CreateDirectory`, `Remove-Item`, `Start-Transcript` -
     naming such a variable, with no unique token on that line.

  Deliberately not flagged, for the same kind of reason as the list above: a
  full-line comment (a comment creates and deletes nothing - the fix for the
  script above is explained in one); a clock used as a LABEL or in a message
  (`Say "copied to _jarvis-backup-$Stamp"`); a name that came in as a function
  PARAMETER, the same written-down blind spot the Python half has; and a FIXED
  name in a shared temp folder, which has no clock in it - a different bug, and
  not one this check can see.

The output is a plain list, and the exit code is non-zero only when there is a
real violation - so a red run means something to fix, not something to read
past. `-v` adds the clock-named files that were examined and are safe, with the
names it decided on, so a wrong decision is visible rather than mysterious.
"""
from __future__ import annotations

import ast
import re
import subprocess
import sys
import warnings
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Directories that hold no source of ours. The same list the other structural
# guards use, plus the audit pass's own scratch, which holds whole copies of the
# backend that no clone carries (`tools/check_literal_keys.py` documents why a
# gitignored scratch copy must not make a guard red on one machine only).
SKIP = {".git", "node_modules", "__pycache__", ".venv", "venv", "target",
        "dist", "build", ".mypy_cache", ".pytest_cache", ".ruff_cache",
        "dshwork", "scratchpad"}

#: Read off the CALLED name, not what it was imported from: `time.time()`,
#: `_time.time()` and `datetime.datetime.now()` are all here, and so is a
#: `clock()` test double. Being too generous costs a line in the report that a
#: human reads; being too narrow costs the bug.
CLOCK_ATTRS = {"time", "time_ns", "monotonic", "monotonic_ns",
               "perf_counter", "perf_counter_ns",
               "strftime", "gmtime", "localtime",
               "now", "utcnow", "today"}
#: A local helper that returns the time. The test doubles that fake a clock are
#: all named one of these, and a faked clock is the worst case: it returns the
#: SAME value on every call, on every platform.
CLOCK_FUNCS = {"now", "_now", "clock", "_clock", "today", "_today",
               "utcnow", "_utcnow"}
#: `open` modes that CREATE a file and refuse an existing one.
EXCLUSIVE_MODES = {"x", "xb", "xt", "xb+", "x+t", "x+b", "xt+"}


def gitignored_paths() -> tuple[set[str], str]:
    """(paths git ignores, why they could not be worked out).

    The same one git call `tools/check_literal_keys.py` makes, for the same
    reason: a path git ignores is scratch this repository does not carry, and a
    guard that fires on an uncommitted copy of a backend file is red on one
    machine and green on CI, which proves nothing. If git cannot say, nothing is
    skipped - a scope this check cannot work out is not a scope it may quietly
    invent.
    """
    try:
        done = subprocess.run(
            ["git", "-C", str(REPO), "ls-files", "--others", "--ignored",
             "--exclude-standard"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=120)
    except (OSError, subprocess.SubprocessError) as err:
        return set(), f"git could not be run ({err})"
    if done.returncode != 0:
        first = (done.stderr or "").strip().splitlines()
        return set(), (f"git exited {done.returncode}"
                       + (f": {first[0]}" if first else ""))
    return {line for line in done.stdout.splitlines() if line}, ""


def is_clock_call(node: ast.AST) -> bool:
    """Is this node a call to a clock that two calls can agree on?"""
    if not isinstance(node, ast.Call):
        return False
    fn = node.func
    if isinstance(fn, ast.Attribute):
        return fn.attr in CLOCK_ATTRS
    if isinstance(fn, ast.Name):
        return fn.id in CLOCK_FUNCS
    return False


def from_clock(node: ast.AST | None, live: set[str]) -> bool:
    """Does this expression read a clock, or a name that is clock-named?"""
    if node is None:
        return False
    for sub in ast.walk(node):
        if is_clock_call(sub):
            return True
        if isinstance(sub, ast.Name) and sub.id in live:
            return True
    return False


def named_targets(node: ast.stmt) -> list[ast.expr]:
    """What this statement binds, when it binds from its own value."""
    if isinstance(node, ast.Assign):
        return list(node.targets)
    if isinstance(node, (ast.AnnAssign, ast.NamedExpr)):
        return [node.target]
    return []


def _bind(targets: list[ast.expr], derived: bool, live: set[str]) -> None:
    """Add or clear each plain name, so a re-binding clears clock-ness.

    Only `ast.Name` targets are tracked. `self.p` / `d["k"]` are not names this
    walk can follow without following the attribute too, and inventing one
    would be worse than missing it - which is why the report says so.
    """
    for target in targets:
        if isinstance(target, ast.Name):
            if derived:
                live.add(target.id)
            else:
                live.discard(target.id)


def _exist_ok(node: ast.Call, positional_index: int) -> bool:
    """Is `exist_ok` given - by keyword, or in its own position?

    Any `exist_ok` counts, not only the literal `True`: an author who passes
    `exist_ok=force` has thought about what a second call does, and guessing
    that the value is False would be this check inventing a violation. The calls
    this check was written for passed `parents=True` and no `exist_ok` at all.
    """
    if any(kw.arg == "exist_ok" for kw in node.keywords):
        return True
    return len(node.args) > positional_index


def _literal_mode(node: ast.Call, positional_index: int) -> str:
    """The literal mode of an `open` call, "" when it is not a plain string."""
    if len(node.args) > positional_index and isinstance(
            node.args[positional_index], ast.Constant):
        value = node.args[positional_index].value
        return value if isinstance(value, str) else ""
    for kw in node.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
            value = kw.value.value
            return value if isinstance(value, str) else ""
    return ""


def _receiver_is_clock_named(node: ast.AST, live: set[str]) -> bool:
    """Is the thing `.mkdir(...)` is called on named from a clock?

    `x.parent` is excluded: a clock in a file's LEAF name does not make its
    containing folder clock-named, so
    `state = tmp / f"{time.time_ns()}.json"; state.parent.mkdir(parents=True)`
    is about `tmp`, which is not named from a clock. That is the one shape this
    rule would otherwise report on every backend module holding a settings file.
    """
    if isinstance(node, ast.Attribute) and node.attr == "parent":
        return False
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "dirname"):
        return False
    return from_clock(node, live)


def _source(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:                                    # pragma: no cover
        return "?"


class Scanner:
    """One file: the creates it makes, judged with the names live at that line.

    Statements are read in SOURCE ORDER, which is the whole point - a name is
    clock-named from the line that assigned it a clock until the line that
    assigns it something else, and not across either boundary.
    """

    def __init__(self) -> None:
        self.problems: list[tuple[int, str]] = []
        #: Clock-named paths this file DOES create, and creates safely (`-v`
        #: prints these). They are the sites a reader should be able to see were
        #: considered and left alone, rather than merely absent from a list of
        #: failures - "no violation" and "nothing looked at" read the same
        #: otherwise, which is the mistake check-tokens.py writes down.
        self.safe: list[tuple[int, str]] = []

    # -- statements ---------------------------------------------------------

    def body(self, statements: list[ast.stmt], live: set[str]) -> None:
        for node in statements:
            self.statement(node, live)

    def statement(self, node: ast.stmt, live: set[str]) -> None:
        # A walrus binds inside its own statement (`(p := TMP / f"{ns}").mkdir()`),
        # so it is applied before the creates in that statement are judged.
        for sub in ast.walk(node):
            if isinstance(sub, ast.NamedExpr):
                _bind([sub.target], from_clock(sub.value, live), live)
        self.check_creates(node, live)
        derived = from_clock(getattr(node, "value", None), live)
        _bind(named_targets(node), derived, live)
        self.into(node, live)

    def into(self, node: ast.stmt, live: set[str]) -> None:
        """Walk the bodies a statement contains, in order.

        A function or class gets its own copy: names live at the `def` are
        readable inside it (a closure), and what it assigns does not leak back
        out. `with ... as d` and `for x in ...` bind names that are NOT from a
        clock, so those are cleared.
        """
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            inner = set(live)
            for arg in getattr(node.args, "args", []) if hasattr(node, "args") else []:
                inner.discard(arg.arg)
            self.body(node.body, inner)
            return
        if isinstance(node, ast.With):
            for item in node.items:
                if item.optional_vars is not None:
                    _bind([item.optional_vars], False, live)
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            _bind([node.target], False, live)
        elif isinstance(node, ast.Try):
            for handler in node.handlers:
                if handler.name:
                    live.discard(handler.name)
        elif isinstance(node, ast.Global) or isinstance(node, ast.Nonlocal):
            return
        for field in ("body", "orelse", "finalbody"):
            block = getattr(node, field, None)
            if isinstance(block, list):
                self.body(block, live)
        if isinstance(node, ast.Try):
            for handler in node.handlers:
                self.body(handler.body, live)

    # -- the creates --------------------------------------------------------

    def check_creates(self, node: ast.stmt, live: set[str]) -> None:
        for call in ast.walk(node):
            if not isinstance(call, ast.Call):
                continue
            fn = call.func
            if isinstance(fn, ast.Attribute) and fn.attr == "mkdir":
                # `Path.mkdir(mode=0o777, parents=False, exist_ok=False)`: the
                # third position is exist_ok, so three arguments IS exist_ok.
                if _receiver_is_clock_named(fn.value, live):
                    what = f"{_source(fn.value)}.mkdir(...)"
                    self.judge(call, what, _exist_ok(call, 2))
            elif isinstance(fn, ast.Attribute) and fn.attr == "makedirs":
                if from_clock(fn.value, live):
                    what = f"{_source(fn.value)}.makedirs(...)"
                    self.judge(call, what, _exist_ok(call, 2))
            elif isinstance(fn, ast.Attribute) and fn.attr == "open":
                # `Path.open(mode=...)`: the mode is the FIRST argument.
                if from_clock(fn.value, live):
                    self.judge_open(call, _source(fn.value), _literal_mode(call, 0))
            elif isinstance(fn, ast.Name) and fn.id == "open":
                # `open(name, "x")`: the mode is the SECOND argument.
                if call.args and from_clock(call.args[0], live):
                    self.judge_open(call, f"open({_source(call.args[0])}, ...)",
                                    _literal_mode(call, 1))
            elif isinstance(fn, ast.Name) and fn.id == "makedirs":
                if call.args and from_clock(call.args[0], live):
                    what = "os.makedirs(...)"
                    self.judge(call, what, _exist_ok(call, 2))

    def judge(self, call: ast.Call, what: str, exists_ok: bool) -> None:
        if exists_ok:
            self.safe.append((call.lineno, f"{what} with exist_ok"))
        else:
            self.problems.append((call.lineno, f"{what} without exist_ok"))

    def judge_open(self, call: ast.Call, what: str, mode: str) -> None:
        """An exclusive mode creates and refuses an existing file; the rest do
        not, so two calls inside one tick merely share the file."""
        if mode in EXCLUSIVE_MODES:
            self.problems.append((call.lineno, f'{what}.open("{mode}")'))
        else:
            self.safe.append((call.lineno, f'{what} opened as "{mode or "r"}"'))


def scan(text: str) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    """(violations, clock-named paths this file creates safely)."""
    with warnings.catch_warnings():
        # A file with `"\\p"` in a regex raises a SyntaxWarning while it parses -
        # real, but not this check's news, and it buries the list that is.
        warnings.simplefilter("ignore", SyntaxWarning)
        tree = ast.parse(text)
    scanner = Scanner()
    scanner.body(tree.body, set())
    return scanner.problems, scanner.safe


# ---------------------------------------------------------------------------
#   `backend/*.patch` - this repository's shipped backend
# ---------------------------------------------------------------------------

def is_clock_line(line: str) -> bool:
    """The line-based half of `is_clock_call`, for text that is not Python."""
    return any(f"{attr}(" in line for attr in
               ("time.time", "time_ns", "monotonic", "perf_counter",
                "strftime", "gmtime", "localtime", "datetime.now", "utcnow",
                "now(", "clock("))


def patch_findings(text: str) -> list[tuple[int, str]]:
    """The same rule for `backend/*.patch`, read as a diff rather than as code.

    This repository's shipped backend IS these patches, so a clock-named folder
    made in one of them is product code, not test code. A hunk is not a
    parseable module - and a context line is not even this repository's code -
    so the rule is applied to ADDED lines only, in the two shapes a person
    actually writes: the whole thing on one line, or the name assigned on the
    line immediately above. That is deliberately narrow: it is here to catch a
    shipped copy of this bug, not to be a second, worse Python parser.
    """
    out: list[tuple[int, str]] = []
    previous: tuple[int, str] | None = None
    for number, line in enumerate(text.splitlines(), 1):
        if not line.startswith("+"):
            previous = None
            continue
        body = line[1:]
        creates = (".mkdir(" in body or "makedirs(" in body) and "exist_ok" not in body
        exclusive = "open(" in body and ('"x"' in body or "'x'" in body)
        if (creates or exclusive) and (is_clock_line(body)
                                      or (previous is not None
                                          and is_clock_line(previous[1]))):
            out.append((number, body.strip()))
        previous = (number, body)
    return out


# ---------------------------------------------------------------------------
#   `*.ps1` - the scripts the owner runs by hand
# ---------------------------------------------------------------------------

#: PowerShell commands that CREATE or DELETE a path. `Remove-Item` is the one
#: that makes this half worse than the Python half: the second caller does not
#: fail to create, it deletes the first caller's folder.
PS_PATH_COMMANDS = re.compile(
    r"\b(new-item|remove-item|mkdir|md|start-transcript)\b"
    r"|\[io\.directory\]::createdirectory", re.I)
#: A call that is a coarse clock in PowerShell. `Get-Date` reads the same system
#: clock `time.time_ns()` does - the tool's own numbers above are why a
#: millisecond format string is NOT accepted as a uniqueness token below.
PS_CLOCKS = re.compile(r"get-date|\[datetime\]::(now|utcnow|today)", re.I)
#: What really does make a name unique, whatever the clock says. `$PID` is in
#: here even though a process id outlives nothing: it is genuinely unique among
#: the runs that could collide, so flagging it would be this check crying wolf.
PS_UNIQUE = re.compile(
    r"newguid|\[guid\]|getrandomfilename|mkdtemp|\$pid\b|\$random\b|get-random"
    r"|new-temporaryfile", re.I)
#: `$Name = ...`, the only binding this line-based read follows. `$env:X = ` is
#: not a name in a path and is left alone.
PS_ASSIGN = re.compile(r"^\s*\$(?P<name>[A-Za-z_]\w*)\s*=(?!=)")
PS_VAR = re.compile(r"\$(?P<name>[A-Za-z_]\w*)")


def ps1_findings(text: str) -> list[tuple[int, str]]:
    """The same rule for the repository's `*.ps1`, read line by line.

    Statements are read in SOURCE ORDER, like the Python half: a name is
    clock-named from the line that assigns it a clock until the line that
    assigns it something else. A full-line comment is skipped - it cannot create
    or delete anything, and the script's own explanation of this very bug must
    not be reported as the bug."""
    out: list[tuple[int, str]] = []
    live: set[str] = set()
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        names = {m.group("name").lower() for m in PS_VAR.finditer(line)}
        # A `$env:TEMP` or an automatic variable is not a name this walk binds,
        # and `$PID` is a token rather than a name from a clock.
        clock = bool(PS_CLOCKS.search(line)) or bool(names & live)
        unique = bool(PS_UNIQUE.search(line))
        if clock and not unique and PS_PATH_COMMANDS.search(line):
            out.append((number, line))
        assigned = PS_ASSIGN.match(raw)
        if assigned:
            name = assigned.group("name").lower()
            if clock and not unique:
                live.add(name)
            else:
                live.discard(name)
    return out


# ---------------------------------------------------------------------------
#   The run
# ---------------------------------------------------------------------------

def _rel(path: Path) -> str:
    try:
        return path.relative_to(REPO).as_posix()
    except ValueError:
        return path.as_posix()


def repo_files(ignored: set[str]) -> list[Path]:
    """Every `*.py`, `*.patch` and `*.ps1` this repository carries, in a stable
    order. `.ps1` because the scripts the owner runs by hand are where this cost
    the most (`ps1_findings` above has the measured collision)."""
    kept = []
    for pattern in ("*.py", "*.patch", "*.ps1"):
        for path in sorted(REPO.rglob(pattern)):
            if not path.is_file():
                continue
            rel = path.relative_to(REPO)
            if any(part in SKIP for part in rel.parts[:-1]):
                continue
            if ignored and rel.as_posix() in ignored:
                continue
            kept.append(path)
    return kept


def main() -> int:
    verbose = "-v" in sys.argv
    given = [a for a in sys.argv[1:] if not a.startswith("-")]
    ignored, why = (set(), "asked not to with --no-git") if "--no-git" in sys.argv \
        else gitignored_paths()

    if given:
        files = [Path(a) if Path(a).is_absolute() else REPO / a for a in given]
    else:
        files = repo_files(ignored)

    problems: list[tuple[str, int, str]] = []
    unreadable: list[tuple[str, str]] = []
    safe_clocks: list[tuple[str, int, str]] = []
    read = 0

    for path in files:
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as err:
            unreadable.append((_rel(path), str(err)))
            continue
        read += 1
        if path.suffix == ".patch":
            for line, what in patch_findings(text):
                problems.append((_rel(path), line, what))
            continue
        if path.suffix == ".ps1":
            for line, what in ps1_findings(text):
                problems.append((_rel(path), line, what))
            continue
        try:
            found, safe = scan(text)
        except SyntaxError as err:
            # A file whose names cannot be read is NOT a pass: saying nothing
            # about it is exactly how a check ends up green having checked
            # nothing (the lesson check-tokens.py writes down about itself).
            unreadable.append((_rel(path), f"line {err.lineno}: {err.msg}"))
            continue
        for line, what in found:
            problems.append((_rel(path), line, what))
        if safe and not found:
            for line, what in safe:
                safe_clocks.append((_rel(path), line, what))

    if why:
        print(f"::warning::git could not list the paths it ignores ({why}), so "
              f"NOTHING was skipped - every *.py, *.patch and *.ps1 in this "
              f"checkout was read, including any scratch copy of a backend file "
              f"that no clone carries. Fix the checkout rather than this check.")

    if problems:
        print("::error::a filesystem path is named from a clock and then created "
              "(or deleted) as if that name were unique. Two calls inside one timer "
              "tick (Windows, about 15.6 ms) return the same name, so the second "
              "creation raises FileExistsError [WinError 183], the second run "
              "quietly shares the first caller's folder - or, in a `Remove-Item`, "
              "deletes it. In Python name it with tempfile.mkdtemp, or pass "
              "exist_ok=True where sharing is genuinely what is meant; in "
              "PowerShell put [guid]::NewGuid() in the name:")
        for name, line, what in sorted(problems):
            print(f"  {name}:{line}  {what}")
    if unreadable:
        print("::error::a file could not be read, so its names were NOT checked - "
              "silence here would be this check passing having checked nothing:")
        for name, exc in unreadable:
            print(f"  {name}  {exc}")

    if problems or unreadable:
        return 1

    print(f"{read} Python, patch and PowerShell file(s) read; no filesystem path is "
          f"named from a coarse clock and then created or deleted as if that name "
          f"were unique.")
    print("A name from time.time_ns()/time.strftime()/datetime.now()/Get-Date is not "
          "unique: on Windows those only move on the system timer tick (about "
          "15.6 ms; measured on the owner's PC, 399 of 399 consecutive "
          "time.time_ns() calls were identical, and one throwaway name asked for "
          "twice in a row came out the same 200 times out of 200). tempfile.mkdtemp "
          "or [guid]::NewGuid() asks for a name from nothing instead, which is what "
          "every fixed site now uses.")
    if verbose:
        if safe_clocks:
            print("  clock-named paths this checkout creates, and creates safely "
                  "(with exist_ok, or opened to append or overwrite - two calls in "
                  "one tick share them, which is what the code means):")
            for name, line, what in sorted(safe_clocks):
                print(f"    {name}:{line}  {what}")
        else:
            print("  no Python file in this checkout creates a path named from a "
                  "clock at all - every clock read is used as a value or a label.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
