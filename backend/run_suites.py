"""Run every backend suite that can run without the owner's PC, and skip - by
name, with the reason - the ones that cannot. This is what CI runs.

    python3 backend/run_suites.py

WHY A RUNNER AND NOT JUST A LOOP. About twenty suites test a patch against the
file it patches - jarvis_hud.py, jarvis_gate.py, jarvis_extract.py,
jarvis_models.py - and those files live only on the owner's PC, never in this
repository (backend/.gitignore refuses them). Run anywhere else, those suites
fail with an ImportError that looks exactly like a broken patch. A CI job
that is always red teaches everyone to ignore it, so those suites are
SKIPPED here, each one named with the files it is waiting for - and only
while those files are absent. Every other suite must pass.

THE BACKEND IT RUNS AGAINST. Not this folder: a temporary folder holding a
copy of every module apply-patches.ps1 ships (backend/_where.py SHIPPED),
side by side, the way they sit on the owner's PC - rebuilt/ flattened in.
So the suites exercise the shipped LAYOUT, not the repository's folders, and
a module that only works because of where it sits in this repository fails
here. Set JARVIS_BACKEND to run against a real backend instead; then nothing
is staged, and a suite is skipped only if its files are really not there.

THE OWNER'S STATE IS LEFT ALONE. The suites run real code that writes -
the audit log, approval queues, switch files - so each run gets a temporary
config folder and audit log (private_state below), deleted afterwards.
apply-patches.ps1 asks for the same variables with `--state-env DIR`.

The skip list is explicit, not guessed from a failure: a suite that is not in
it and fails is a failure, and a suite in it whose files ARE present runs.

    python3 backend/run_suites.py --jobs 14

`--jobs N` runs N suites at once. **The default is 1, and CI uses the
default**, so the output of the ordinary run is what it has always been. The
updater is the only caller that asks for more (`tools/update_backend.py`, the
owner's own choice of how hard the update should work), and it changes ONLY
the number of workers: the suite list is the same glob in every mode, so a
"quick" update and a "safe" one run exactly the same checks. Each worker gets
its own config folder, audit log and scratch folder inside the same run root,
because the suites write real state and two of them writing into one folder
is not a check either of them asked for.

THE UPDATE LOCK. A backend update holds `update-in-progress.lock` in the
folder Jarvis keeps its own data in (`OPENJARVIS_CONFIG_DIR`, then
`JARVIS_CONFIG_DIR`, then `~/.openjarvis`). While that lock is VALID (live pid,
heartbeat under 30 minutes, run under 3 hours), this runner REFUSES immediately
with exit 3, naming the lock's pid, pace and start time - a sweep beside an
update starves the CPU and skews the update's timing. The update's own suite
phase is the one exception: `tools/update_backend.py` passes
`--ignore-update-lock`, and `JARVIS_INSIDE_PATCHER=1` does the same for a
caller that must set an environment instead. The lock rules and reading live
in `tools/update_backend.py`'s lock section (one implementation, so the tool,
this runner and the desktop cannot disagree); a checkout without that tool
simply cannot check, and this runner never claims it did.
"""
import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _where  # noqa: E402

# Suite -> the backend files it needs. Found by running each suite in a
# checkout without them and reading which import or file read failed first,
# then reading the suite for its other imports and BACKEND / "..." reads.
# Every entry names at least one file that only the owner's PC has
# (OWNER_FILES), which is what makes it skip here; the rebuilt modules it
# also uses are listed for completeness. test_embedding_guard.py is NOT here:
# it needs only jarvis_memory.py, the staged rebuilt copy satisfies it, and
# it passes against that copy - so it runs.
#
# A SUITE THAT CAN BUILD WHAT IT NEEDS DOES NOT BELONG HERE. test_appearance.py
# was on this list until 2026-10-10 for `jarvis_hud.py`, and it did not need
# the whole file - only the block `appearance.patch` writes, which the patch
# stack's own stand-in carries (`backend/_stack.py`). Sitting here meant its 14
# checks were skipped in CI and ran only on the owner's PC. It now reads the
# real file when there is one and the stand-in when there is not, so it is not
# listed. The three suites that could run PART of themselves were taken off the
# same day, for the same reason, and each one names as a skip whatever still
# needs the owner's whole file:
#
#   * test_voice_503.py - 11 of its 20 checks execute `_no_speech()` and read
#     `_SAY_FALLBACK`, both written whole by voice-503.patch, so the stand-in
#     has them. The other 9 read whole-file route statements with ast.
#   * test_memory_pane.py - 13 of its 49 checks (the learning switch and the
#     query-string reader) come out of the stand-in the same way. The other 36
#     read whole-file route statements.
#   * test_documents_honesty.py - 1 of its 19. MEASURED, not assumed: the two
#     checks that EXECUTE `_has_table` cannot be lifted, because it calls
#     `_ro_sqlite`, which the owner wrote and no patch does - the stand-in has
#     that function's `def` line and the first line of its docstring and none
#     of its body (`mode=ro` and `as_uri` appear nowhere in it), so `_has_table`
#     run from the stand-in raises NameError instead of answering. Passing in a
#     helper of our own would be a paraphrase of the code under test. What is
#     left in CI is the check that a failed documents read is REPORTED - both
#     sentences are written by the patch - which is one real guard where there
#     were none.
#
# Naming the skips, rather than leaving the whole suite listed, is the point:
# the runner prints "N passed, M skipped" beside each of them, so a reader sees
# how much of the suite actually ran.
NEEDS_OWNER = {
    "test_approval_notice.py": ("jarvis_gate.py", "jarvis_events.py"),
    "test_bitemporal.py": ("jarvis_hud.py", "jarvis_memory.py"),
    "test_decide_once.py": ("jarvis_extract.py", "jarvis_hud.py", "jarvis_memory.py"),
    "test_degrade_filter.py": ("jarvis_hud.py",),
    "test_events_pump.py": ("jarvis_hud.py", "jarvis_events.py"),
    "test_extraction_wiring.py": ("jarvis_hud.py", "jarvis_events.py"),
    "test_gate_egress.py": ("jarvis_gate.py", "jarvis_hud.py", "jarvis_events.py"),
    "test_gate_outcome.py": ("jarvis_gate.py",),
    "test_gate_push.py": ("jarvis_gate.py",),
    "test_gpu_offload.py": ("jarvis_hud.py", "jarvis_models.py"),
    "test_import_history.py": ("jarvis_extract.py", "jarvis_memory.py"),
    "test_memory_noise.py": ("jarvis_extract.py", "jarvis_hud.py", "jarvis_memory.py"),
    "test_memory_prefix.py": ("jarvis_hud.py",),
    "test_memory_safety.py": ("jarvis_extract.py", "jarvis_memory.py"),
    # It lifts the real `_completions_url` and `_auth_headers` out of
    # jarvis_hud.py, so it needs that file - and, since 2026-10-06, the real
    # jarvis_chatbot_api too (the cloud lane's resolver): without it the
    # module-level `import jarvis_chatbot_api` inside the lifted function
    # fails and every cloud check would read as "no lane".
    "test_ollama_direct.py": ("jarvis_hud.py",),
    "test_token_file.py": ("jarvis_hud.py",),
}

# The files only the owner's PC has. Checked below: every NEEDS_OWNER entry
# must name one, so the list cannot be used to skip a suite that could run.
OWNER_FILES = {"jarvis_hud.py", "jarvis_gate.py", "jarvis_extract.py", "jarvis_models.py",
               "jarvis_skills.py"}


CONFIG_NAME = "jarvis-framework.toml"

# --- where a run's own folders live, and how they are taken away ------------
#
# WHY THIS IS NOT JUST mkdtemp AND A rmtree AT THE END (2026-10-11). A run used
# to leave TWO folders under %TEMP% - `jarvis-staged-backend-<random>` (a copy
# of every shipped module, measured at 10 MB) and `jarvis-suite-state-<random>`
# (the config folder and audit log the suites write, 64 MB in one measured
# case) - and both rmtree calls sat at the END of main(), outside any
# try/finally. A run that was killed, Ctrl-C'd, cancelled by CI, or wedged
# until the 900-second suite timeout skipped both. Twenty thousand of them
# reached 123.6 GB and took C: from 165 GB free down to 34 GB. A 131 GB hand
# cleanup followed; the mechanism did not change.
#
# It was worse than those two folders. EVERY suite in this folder makes its own
# `jarvis-<suite>-<random>` at import time with `tempfile.mkdtemp` (296 of them
# do today - `jarvis-enrol-`, `jarvis-big-model-`, `jarvis-referee-`, ...) and
# most never remove it, which is one folder per suite per run: the bulk of the
# twenty thousand. Fixing only the runner's own two folders would have left
# that in place, so the sweep root below owns the suites' scratch as well.
#
# Four things hold now:
#
#   1. ONE FOLDER PER RUN. The staged backend, the config/audit state and the
#      suites' own scratch all live inside a single `jarvis-sweep-<random>`
#      root, removed in a `finally` however main() leaves - a normal return, a
#      failed suite, or an exception.
#
#   2. THE SUITES' SCRATCH GOES THERE TOO. The children are given TMPDIR, TEMP
#      and TMP pointing into the sweep root; `tempfile.gettempdir()` reads
#      exactly those, so every `mkdtemp` a suite makes lands inside the root
#      and goes with it.
#
#   3. A REAPER FOR WHAT A KILL LEAVES. A terminated process runs no `finally`
#      at all, so a killed run's root stays. Each root carries an `_owner.json`
#      marker (pid, start time, kind) and the run that made it holds an
#      exclusive LOCK on that file for its whole life - the operating system
#      drops the lock when the process ends, however it ends. The start of
#      every run reaps roots whose lock can be taken (so no run is using them)
#      and which are older than REAP_AFTER.
#
#   4. A LIVE FOLDER IS NEVER TOUCHED. A folder whose lock is still held
#      belongs to a running sweep, and deleting its staging underneath it is a
#      worse bug than the litter. Two sweeps really were running when this was
#      written (both on the old code, both holding a staged-backend and a
#      suite-state folder), which is why the lock, and not the pid, is what
#      answers "is the owner still alive".
SWEEP_PREFIX = "jarvis-sweep-"
#: A DIRECT run's root - `python backend/<suite>.py` with no runner - claimed by
#: `_where._stage_a_direct_run()` with the same marker and lock as a sweep, so
#: one mechanism covers both and a killed direct run is reapable by the reaper
#: below. It is one folder per direct process instead of one per suite.
DIRECT_PREFIX = "jarvis-direct-"
STAGE_PREFIX = "jarvis-staged-backend-"
BACKEND_NAME = "backend"
STATE_NAME = "state"
SUITE_TEMP_NAME = "tmp"
OWNER_MARKER = "_owner.json"
#: A marked folder - one this runner made - may be reaped once its owner is
#: gone and it is at least this old.
REAP_AFTER = 3600.0
#: A folder with NO marker (an older run's, from before markers existed) cannot
#: be asked about its owner at all, so age is the only proof available and it
#: has to be long: a suite is killed at 900 s and this is far beyond any sweep,
#: so nothing can still be writing into a folder this old.
REAP_AFTER_UNMARKED = 86400.0
#: What is even a candidate: a folder under the system temp folder whose NAME
#: is the shape this runner or a suite builds - `jarvis-<something>-<random>`,
#: where the random tail is the one `tempfile.mkdtemp` appends. Deliberately a
#: SHAPE and not a list of suite names: suites are added and removed constantly,
#: and a fixed list would stop protecting them the day after it was written.
#: The tail is 6+ characters of the alphabet mkdtemp uses and carries no dot, so
#: a data file that merely starts with `jarvis-` (jarvis-framework.toml) and a
#: folder with no random tail at all are both left alone - the rule only ever
#: claims the throwaway folders, never a name a person chose.
REAPABLE = re.compile(r"^jarvis-[A-Za-z0-9_.-]+-[A-Za-z0-9_-]{6,}$")
#: This process's own wall-clock start, written into every marker so a reader
#: can tell one run's folder from the next run's.
_STARTED = time.time()

#: "N passed" / "N skipped" / "N failed" as a suite prints them at the end.
#: Looked up by the word, not by position: every harness in this folder prints
#: the three, but the older ones print them in a different order.
_SUMMARY = {"passed": re.compile(r"(\d+)\s+passed\b"),
            "skipped": re.compile(r"(\d+)\s+skipped\b"),
            "failed": re.compile(r"(\d+)\s+failed\b")}

#: What a reader counts by eye, for a suite that prints no summary at all:
#: `ok` and `FAIL` from check(), `skip` from skip() (or an older harness's own
#: "SKIP  <name>"). The word has to end there or be followed by a space or a
#: colon - test_topics.py has a real check named "skipped-this-week is a number
#: per topic", and counting a check as a skip would be this bug in reverse.
_LINE = {"passed": re.compile(r"^ok\b"),
         "skipped": re.compile(r"^skip(ped)?(?=[ \t:]|$)", re.I),
         "failed": re.compile(r"^FAIL\b")}

#: unittest's own summary, for the three suites built on it (test_rebuilt.py,
#: test_speech.py, test_thinking.py). Without this the three of them reported as
#: "0 passed, 0 skipped, 0 failed" - the same numbers a suite that printed
#: nothing at all gives, which is the one shape this runner must never confuse
#: with a pass. It matters two ways round: unittest exits 0 just as happily
#: having run NO tests (every method renamed away, or a TestCase that stopped
#: matching `unittest.main()`'s default), and a suite that prints nothing is
#: exactly the class `tools/check_vacuous_checks.py` exists for one level down.
#: unittest counts a skipped test inside "Ran N tests", so the passes are what
#: is left after the skips and the failures, not the total on its own.
_UNITTEST_RAN = re.compile(r"^Ran (\d+) tests? in ", re.M)
_UNITTEST_BAD = re.compile(r"^FAILED \(([^)]*)\)", re.M)
_UNITTEST_SKIPPED = re.compile(r"skipped=(\d+)")

#: A line that LOOKS like a suite's own summary: a count, then "passed" or
#: "failed". Used to find the summary anywhere in the output rather than only in
#: its last four lines - see `_last_summary_line`.
_SUMMARY_LINE = re.compile(r"^\s*\d+\s+(?:passed|failed)\b")


def _last_summary_line(out: str) -> str:
    """The last line of `out` that carries a suite's own summary, or "".

    WHY NOT THE LAST FOUR LINES. That is what this used to read, and a suite
    that prints a traceback AFTER its summary pushed the summary out of the
    window: `test_news.py` failed with a traceback on stderr and the runner
    printed "FAIL test_news.py (exit 1) 65 passed, 0 skipped, 0 failed" beside
    it. The verdict was still right - it comes from the exit code - but the
    numbers were wrong, and the numbers are what a reader believes. The last
    line that looks like a summary is the suite's own last word whatever
    happens after it."""
    last = ""
    for line in out.splitlines():
        if _SUMMARY_LINE.match(line):
            last = line
    return last


def counts(out: str) -> dict:
    """{'passed': n, 'skipped': n, 'failed': n} for one suite's output.

    The suite's OWN final line is believed when it has one: it knows what it
    counted, and a `skip()` no longer lands in its "passed". A unittest suite
    is believed through unittest's own summary. Only a suite that prints
    neither is counted from its own lines."""
    summary = _last_summary_line(out)
    got = {}
    for word, pat in _SUMMARY.items():
        m = pat.search(summary)
        got[word] = int(m.group(1)) if m else None
    if got["passed"] is not None and got["failed"] is not None:
        return {"passed": got["passed"], "skipped": got["skipped"] or 0,
                "failed": got["failed"]}
    m = _UNITTEST_RAN.search(out)
    if m:
        total = int(m.group(1))
        bad = _UNITTEST_BAD.search(out)
        failed = 0
        if bad:
            for _kind, number in re.findall(r"(failures|errors)=(\d+)", bad.group(1)):
                failed += int(number)
        skipped = _UNITTEST_SKIPPED.search(out)
        skipped = int(skipped.group(1)) if skipped else 0
        return {"passed": max(0, total - skipped - failed), "skipped": skipped,
                "failed": failed}
    counted = {w: 0 for w in _LINE}
    for line in out.splitlines():
        for word, pat in _LINE.items():
            if pat.match(line):
                counted[word] += 1
                break
    return counted


def _config_the_suites_would_read(env: dict, backend: Path):
    """The jarvis-framework.toml jarvis_framework.config_path() would find for
    a suite, BEFORE the config folder is moved: the override, the config
    folder, beside the modules, one folder up - and last this repository's
    rebuilt/ copy, which is what a suite that imports rebuilt/ directly
    (test_voice_enroll, test_speech, ...) finds beside jarvis_framework.py.
    Its log_directory is ~/.openjarvis/logs/ too."""
    raw = env.get("JARVIS_FRAMEWORK_TOML")
    home_cfg = env.get("OPENJARVIS_CONFIG_DIR") or env.get("JARVIS_CONFIG_DIR")
    cfg_dir = Path(os.path.expanduser(home_cfg)) if home_cfg \
        else Path(os.path.expanduser("~")) / ".openjarvis"
    for c in (Path(os.path.expanduser(raw)) if raw else None, cfg_dir / CONFIG_NAME,
              backend / CONFIG_NAME, backend.parent / CONFIG_NAME,
              HERE / "rebuilt" / CONFIG_NAME):
        if c is not None and c.is_file():
            return c
    return None


def _with_log_directory(toml: str, where: Path) -> str:
    """`toml` with [logging].log_directory set to `where` - a TOML literal
    string, forward slashes, so a Windows path needs no escaping."""
    line = f"log_directory = '{where.as_posix()}'"
    lines = toml.splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if l.strip() == "[logging]")
    except StopIteration:
        return toml.rstrip("\n") + f"\n\n[logging]\n{line}\n"
    end = next((i for i in range(start + 1, len(lines)) if lines[i].lstrip().startswith("[")),
               len(lines))
    for i in range(start + 1, end):
        if lines[i].split("=", 1)[0].strip() == "log_directory":
            lines[i] = line
            break
    else:
        lines.insert(start + 1, line)
    return "\n".join(lines) + "\n"


def private_state(env: dict, backend: Path, where: Path) -> dict:
    """`env`, changed so the suites write their state under `where`, never
    into the owner's real config folder.

    Several suites run real code that writes: the audit log (131 fake
    events - "voice.training.decided", "wiki.asked", "task.stop" - landed
    in ~/.openjarvis/logs in one run), approval queues, switch files. That
    folder is jarvis_framework._config_dir(): OPENJARVIS_CONFIG_DIR, then
    JARVIS_CONFIG_DIR, then ~/.openjarvis. Both variables now point at a
    temporary folder.

    That alone is not enough on the owner's PC: the config beside the
    modules sets [logging].log_directory = "~/.openjarvis/logs/", which the
    audit log honours over the config folder. So that config is copied into
    the temporary folder with only log_directory changed, and
    JARVIS_FRAMEWORK_TOML points at the copy. A suite that sets
    JARVIS_FRAMEWORK_TOML itself (test_rebuilt, test_router_private_terms)
    still reads the file it chose.

    PYTHONIOENCODING is set here too, and it is not about state: it is a
    bug this runner had on Windows. A Windows console (and a pipe) defaults
    Python's stdout to the ANSI code page, cp1252 here, and 56 of the
    suites print a non-ASCII character that cp1252 cannot encode - the
    Cyrillic host test_youtube.py refuses, an em dash, a curly quote. The
    print raises UnicodeEncodeError, the suite exits 1, and it is reported
    as a FAILING SUITE when the check itself passed. test_youtube.py failed
    that way in both the 15:48 and the 19:09 runs on 2026-10-03, for a link
    its parser had correctly refused. jarvis_voices.py:2490 and
    backend/README.md's own preflight line already set this variable for
    the same reason; the runners simply never did."""
    out = dict(env)
    out["PYTHONIOENCODING"] = "utf-8"
    cfg = where / "config"
    logs = where / "logs"
    cfg.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    found = _config_the_suites_would_read(env, backend)
    out["OPENJARVIS_CONFIG_DIR"] = str(cfg)
    out["JARVIS_CONFIG_DIR"] = str(cfg)
    if found is not None:
        copy = cfg / CONFIG_NAME
        copy.write_text(_with_log_directory(found.read_text(encoding="utf-8"), logs),
                        encoding="utf-8")
        out["JARVIS_FRAMEWORK_TOML"] = str(copy)
    return out


def stage(root: Path = None) -> Path:
    """A folder holding every module apply-patches.ps1 ships, flattened.

    With `root`, it is made INSIDE that folder, so it goes when the run's own
    folder goes (see SWEEP_PREFIX above). With no root it is its own %TEMP%
    folder, which is what the suites that stage a backend for themselves ask
    for - `test_suite_state.py` calls `stage()` twice and removes each one
    itself, so it must keep working exactly as it did."""
    if root is None:
        d = Path(tempfile.mkdtemp(prefix=STAGE_PREFIX))
    else:
        d = root / BACKEND_NAME
        d.mkdir(parents=True, exist_ok=True)
    for rel in _where.SHIPPED:
        shutil.copy2(HERE / rel, d / rel.rsplit("/", 1)[-1])
    return d


def _lock_nb(fd: int) -> bool:
    """An exclusive, non-blocking lock on an open file: True if we got it.

    `msvcrt` on Windows and `fcntl` everywhere else, both standard library.
    This is what makes "is the owner of this folder still running?" answerable.
    The owner holds the lock for its whole life and the operating system drops
    it when that process ends - returned, raised, or killed outright - so the
    answer survives every way a run can die, and cannot be fooled by a pid
    being reused (which is why a pid alone is not enough).

    If neither module is importable the answer is False, "still owned", so a
    folder is never removed on a guess."""
    try:
        import msvcrt
    except ImportError:
        pass
    else:
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False
    try:
        import fcntl
    except ImportError:
        return False
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def claim(root: Path, kind: str):
    """Write `root`'s owner marker and lock it; the descriptor is returned.

    THE DESCRIPTOR MUST STAY OPEN for as long as the folder is to count as
    live, and must be CLOSED before the folder is removed - on Windows a file
    this process still holds open cannot be deleted, so removing the folder
    first would silently leave the marker (and the folder) behind. Returns None
    if the lock could not be taken, which means someone else owns it."""
    info = {"pid": os.getpid(), "started": _STARTED, "kind": kind, "folder": root.name}
    marker = root / OWNER_MARKER
    marker.write_text(json.dumps(info, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    fd = os.open(str(marker), os.O_RDWR)
    if not _lock_nb(fd):
        os.close(fd)
        return None
    return fd


def _owner_gone(folder: Path) -> bool:
    """True only when `folder` carries a marker whose lock can be taken, which
    means the run that made it has ended. A folder with no marker, or one whose
    marker cannot be opened, is NOT gone - never a reason to delete."""
    marker = folder / OWNER_MARKER
    if not marker.is_file():
        return False
    try:
        fd = os.open(str(marker), os.O_RDWR)
    except OSError:
        return False
    try:
        return _lock_nb(fd)
    finally:
        os.close(fd)            # releases the lock we just took, if we took one


def _older_than(folder: Path, seconds: float) -> bool:
    """True when nothing has changed in `folder` for `seconds`.

    THE MODIFICATION TIME, AND NOT THE CREATION TIME TOO (measured 2026-10-11).
    `st_ctime` reads as the creation time on Windows and as the inode-change
    time on Linux, and on both it is set to NOW by `os.utime` - so a rule
    demanding BOTH timestamps be old is a rule no test can set up, which makes
    it a guard that is never exercised and fails silently the day it matters.
    mtime is also the better question: "has anything touched this folder
    recently?" is exactly what says whether a run might still be using it, and
    it is the one timestamp a person with `touch -t` can reproduce.

    The lock, not this, is what protects a LIVE run's folder (see
    `_owner_gone`); this is the second gate, and the only one available for a
    folder from a run old enough to have no marker."""
    try:
        return (time.time() - folder.stat().st_mtime) > seconds
    except OSError:
        return False


def reap_orphans(temp=None, keep=()) -> list:
    """Remove staging folders an ended run left under the temp folder, and name
    the ones removed.

    Only a DIRECTORY directly under the temp folder, whose name is the shape
    this runner or a suite builds (REAPABLE), is ever considered - never a
    symlink, never anything else's folder. A marked folder goes only when its
    lock can be taken (no run is using it) AND it is older than REAP_AFTER; a
    folder with no marker, left by an older run, must be older than
    REAP_AFTER_UNMARKED, because there is nothing to ask about its owner. The
    current run's own folder is passed in `keep` and is never a candidate.

    Nothing here raises. A folder that cannot be listed or removed is left
    alone, because the only thing at stake is litter."""
    temp = Path(temp) if temp is not None else Path(tempfile.gettempdir())
    keep = {str(Path(k)) for k in keep}
    gone = []
    try:
        entries = sorted(temp.iterdir())
    except OSError:
        return gone
    for d in entries:
        try:
            if not d.is_dir() or d.is_symlink() or not REAPABLE.match(d.name):
                continue
            if str(d) in keep:
                continue
            marked = (d / OWNER_MARKER).is_file()
            if not _older_than(d, REAP_AFTER if marked else REAP_AFTER_UNMARKED):
                continue
            if marked and not _owner_gone(d):
                continue                     # a live run: never touched
            shutil.rmtree(d, ignore_errors=True)
            if not d.exists():
                gone.append(d.name)
        except OSError:
            continue
    return gone


def suite_temp_env(env: dict, root: Path) -> dict:
    """`env` with the suites' OWN scratch pointed inside this run's folder.

    Every suite here makes `jarvis-<suite>-<random>` at import time with
    `tempfile.mkdtemp` and most never remove it. `tempfile.gettempdir()` reads
    TMPDIR, then TEMP, then TMP, so pointing all three into the sweep root is
    what keeps those out of the machine's real temp folder - and so out of the
    count that reached 20,633. The folder is made here because Python falls
    back to the WORKING DIRECTORY for a temp directory it cannot write to,
    which would put a suite's scratch inside the checkout instead."""
    tmp = root / SUITE_TEMP_NAME
    tmp.mkdir(parents=True, exist_ok=True)
    out = dict(env)
    for name in ("TMPDIR", "TEMP", "TMP"):
        out[name] = str(tmp)
    return out


def remove_tree(path: Path, what: str) -> None:
    """Remove `path`, and SAY SO if anything is left behind.

    `shutil.rmtree(..., ignore_errors=True)` is how 123.6 GB went unnoticed: a
    folder a killed child still holds open is not removed and nothing says so.
    One retry first (the handle is usually gone a moment later), then a plain
    line naming what stayed, so a leak can never again be silent."""
    for _ in range(2):
        shutil.rmtree(path, ignore_errors=True)
        if not path.exists():
            return
        time.sleep(0.2)
    try:
        left = sorted(p.name for p in path.iterdir())
    except OSError:
        left = []
    print(f"NOTE  {what} could not be fully removed: {path}"
          + (f" (still holds: {', '.join(left[:5])})" if left else "")
          + ". A later run's reaper removes it once nothing holds it open.")


def suite_result(name: str, took: str, code, stdout, stderr, why="") -> tuple:
    """How one finished suite is reported: ("ok"|"FAIL", counts, the line, the
    lines to echo under it). Every suite is reported, including the one that
    printed nothing at all - which is why `stdout`/`stderr` may be None and
    are read as empty text, never assumed to be a string. That None is not
    hypothetical: it is what subprocess leaves behind when a suite is killed
    by a signal, or when the spawn itself fails. Reading it as a string
    raised TypeError at `r.stdout + r.stderr` and ended the whole sweep, so
    the results of every suite after it were never printed.

    `why` is the runner's own reason for a suite that never produced a line of
    its own - a spawn that raised, say. The suite's counts are honestly zero,
    so the reason is what says the suite did not run at all.

    A suite that exits 0 having reported NO checks at all is the one shape this
    runner must never call a pass. It cannot be told apart from a suite whose
    checks all vanished - a loop over an empty list, a guard that can never be
    true, a main() that returns before printing - and the browser suite found on
    2026-10-05 did exactly that: it exited 0 having run nothing, and stayed
    green. So exit 0 with every count zero is reported as failed, and the reason
    says which shape it was.

    Only exit 0 is "ok". Anything else is reported as failed - including a
    suite the runner could not read an exit code for at all, which is why
    the check is `code == 0` and not `code == 0 or code is None`."""
    out = (stdout or "") + (stderr or "")
    n = counts(out)
    said = f"{n['passed']} passed, {n['skipped']} skipped, {n['failed']} failed"
    silent = code == 0 and not any(n.values())
    if silent:
        code = "printed no checks"
    if code == 0:
        # The numbers are shown whenever they are not already on the suite's
        # own last line: a suite that skipped something (its own line would
        # have said so), or one that prints no "N passed" summary of its own -
        # the three unittest suites, and the older harnesses counted from
        # their own `ok` lines. Otherwise a reader sees
        # `ok  test_speech.py  2.0s` with no idea whether 25 checks ran or
        # none did, which is the blind spot this runner closed.
        tail = "\n".join(out.strip().splitlines()[-4:])
        own_summary = _SUMMARY["passed"].search(tail)
        note = f"  {said}" if (n["skipped"] or not own_summary) else ""
        return "ok", n, f"ok    {name:<34} {took}{note}", []
    if not out.strip() and not why:
        # a suite that said nothing is still reported in full: which suite,
        # what it exited with, and that there was no output to quote.
        said += "  (no output)"
    line = f"FAIL  {name:<34} {took}  (exit {code})  {said}"
    echo = [f"      {why}"] if why else []
    if silent:
        echo.append("      it exited 0 having printed no `ok`, `FAIL` or `skip` line "
                    "and no summary - so nothing here proves that any check ran. A "
                    "check that cannot fail, one level up.")
    echo += ["      " + l for l in out.splitlines()
             if l.startswith("FAIL") or "Traceback" in l or "failed:" in l]
    # One GitHub annotation is built from this line, and a spawn failure
    # carries the operating system's whole sentence. Capped so the suite's
    # name and its exit code are never pushed out of the annotation; the full
    # text is echoed under the line.
    return "FAIL", n, line[:200], echo


# ---------------------------------------------------------------------------
#   The update lock - never run a suite sweep beside a live backend update
# ---------------------------------------------------------------------------
#
# An update patches the backend and then runs these very suites; a second
# sweep beside it (or the desktop's watchdog restarting the backend mid-run)
# starves the CPU and doubles the wall time a real update measured at 2h8m.
# The update tool writes `update-in-progress.lock` in the folder Jarvis keeps
# its own data in; this runner refuses to start while that lock is VALID
# (live pid, fresh heartbeat, under the 3-hour ceiling) unless the caller is
# the update's own suite phase: `--ignore-update-lock` or
# JARVIS_INSIDE_PATCHER=1. The rules and the reading live in ONE place,
# `tools/update_backend.py`'s lock section, so the tool, this runner and the
# desktop app cannot disagree about what "stale" means.
LOCK_BYPASS_ENV = "JARVIS_INSIDE_PATCHER"
LOCK_BYPASS_FLAG = "--ignore-update-lock"


def _update_lock_api():
    """`tools/update_backend.py`, imported for its lock section - or None.

    Guarded, and deliberately quiet when absent: a checkout without the update
    tool (or an import that fails) means this runner CANNOT know about a lock,
    and must not print a line claiming it checked for one. The lock is advisory;
    a missing reader is not a pass.
    """
    try:
        tools = HERE.parent / "tools"
        if not (tools / "update_backend.py").is_file():
            return None
        if str(tools) not in sys.path:
            sys.path.insert(0, str(tools))
        import update_backend          # noqa: PLC0415 - one guarded import
        return update_backend
    except Exception:                  # noqa: BLE001 - never a crash
        return None


def update_lock_refusal(ignore: bool = False) -> str:
    """The plain refusal when a VALID update lock is held, else "".

    `ignore` is `--ignore-update-lock`; the environment variable is the other
    way the update's own suite phase says who it is. A lock that is stale, a
    lock file that is unreadable, or no update tool to read it with all answer
    "" - nothing is enforced there, and nothing claims it was.
    """
    if ignore:
        return ""
    if str(os.environ.get(LOCK_BYPASS_ENV) or "").strip() == "1":
        return ""
    api = _update_lock_api()
    if api is None:
        return ""
    try:
        state = api.read_lock(api.lock_path())
    except Exception:                  # noqa: BLE001 - a read never blocks a run
        return ""
    return api.lock_refusal_words(state) if state.get("valid") else ""


def main(only=(), jobs: int = 1, ignore_update_lock: bool = False) -> int:
    """Every suite, or only the ones named (`run_suites.py test_x.py ...`).

    Refuses immediately (exit 3, nothing staged, no suite started) while a
    valid backend-update lock is held; see `update_lock_refusal`. The update's
    own suite phase passes `ignore_update_lock=True` (or sets
    JARVIS_INSIDE_PATCHER=1), which is the only thing that bypasses it.

    `jobs` is how many suites to run at once: **1 by default, and that is what
    CI runs**, so the ordinary output is byte-for-byte what it has always been.
    The updater (the owner's own "how hard should this update work" choice) is
    the only caller that passes more; which suites run never changes, only how
    many are in flight.

    A name given on the command line that is not a suite here is a FAILURE, not
    an empty run: a sweep that prints "0 passed, 0 skipped, 0 failed" and exits
    0 for a mistyped name is the same lie one level up from the suites this
    runner exists to distrust (`backend/test_jobs.py` is named in the docs but
    lives only on the owner's PC, so a typo there was easy to make).

    THIS IS THE FOLDER THAT MUST NOT BE LEFT BEHIND. Everything the run makes
    lives inside `root`, and `root` is removed in a `finally` - so an exception
    (a suite's output that will not decode, a KeyboardInterrupt) cleans up
    exactly as a normal end does. A kill cannot run a `finally` at all, which
    is what the reaper at the start of `_sweep` is for: next time it finds this
    folder by its `_owner.json` marker, whose lock this process no longer
    holds, and removes it."""
    refusal = update_lock_refusal(ignore_update_lock)
    if refusal:
        # Immediately, before a folder is made: this is a "come back later",
        # not a run that tried and failed.
        print(f"REFUSED  {refusal}", file=sys.stderr)
        print("Not run: nothing was staged and no suite was started.", file=sys.stderr)
        return 3
    jobs = max(1, int(jobs))
    root = Path(tempfile.mkdtemp(prefix=SWEEP_PREFIX))
    lock = claim(root, "sweep")
    try:
        return _sweep(root, only, jobs)
    finally:
        # The lock goes FIRST: on Windows a file this process still holds open
        # cannot be deleted, so the marker would keep the whole folder alive -
        # the exact silent leak this change exists to end.
        if lock is not None:
            os.close(lock)
        remove_tree(root, "this run's own staging folder")


def _suite_job(s: Path, backend: Path, env: dict) -> dict:
    """Run ONE suite and hand back what to print. Never prints.

    Split out of `_sweep` for `--jobs`: with more than one worker the jobs
    finish in a different order than the list, and a job that printed from
    inside a thread would interleave another suite's lines into its own
    failure block. The caller owns the printing. The result carries exactly
    the same four things a single-worker run printed, so the two paths cannot
    disagree about what a suite means."""
    need = NEEDS_OWNER.get(s.name, ())
    absent = [f for f in need if not (backend / f).is_file()]
    if absent:
        return {"name": s.name, "status": "skip",
                "counts": {"passed": 0, "skipped": 0, "failed": 0},
                "line": f"skip  {s.name:<34} needs the owner's {', '.join(absent)}",
                "echo": [], "tail": []}
    t0 = time.time()
    why = ""
    try:
        # errors="replace" and an explicit utf-8 decode: the child is run
        # with PYTHONIOENCODING=utf-8 (see private_state), so decoding its
        # output with the console's own code page raised
        # UnicodeDecodeError INSIDE subprocess's reader thread, which left
        # r.stdout as None and crashed this whole runner with
        # "unsupported operand type(s) for +: 'NoneType' and 'str'" - one
        # suite's non-ASCII output taking the entire run down with it.
        # That happened on 2026-10-03, at test_mail_mask.py.
        r = subprocess.run([sys.executable, str(s)], cwd=HERE, env=env,
                           capture_output=True, text=True, timeout=900,
                           encoding="utf-8", errors="replace")
        code, got_out, got_err = r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        code, got_out, got_err = "timeout", "", ""
    except OSError as exc:
        # The child never started at all - an executable that cannot run,
        # a path that is gone, a permission the sandbox refuses. The suite
        # has no exit code to compare with 0, so it is FAILED and the
        # reason is carried into the report; continuing is the point,
        # because the suites after this one still have results worth
        # printing.
        code, got_out, got_err = None, "", ""
        why = f"the suite could not be started: {exc}"
    took = f"{time.time() - t0:5.1f}s"
    status, n, line, echo = suite_result(s.name, took, code, got_out, got_err, why)
    tail = ((got_out or "") + (got_err or "")).strip().splitlines()[-40:]
    return {"name": s.name, "status": status, "counts": n, "line": line,
            "echo": echo, "tail": tail}


def _print_job(got: dict, ran: dict, passed: list, failed: list,
               skipped: list) -> None:
    """Print one finished suite exactly as the one-at-a-time run always has."""
    if got["status"] == "skip":
        skipped.append(got["name"])
        print(got["line"])
        return
    for word in ran:
        ran[word] += got["counts"][word]
    if got["status"] == "ok":
        passed.append(got["name"])
        print(got["line"])
        return
    failed.append(got["name"])
    print(got["line"])
    for line in got["echo"]:
        print(line)
    print("\n".join("      " + line for line in got["tail"]))


def _sweep_parallel(suites: list, backend: Path, worker_envs: list, ran: dict,
                    passed: list, failed: list, skipped: list) -> None:
    """The same suites, `len(worker_envs)` at a time.

    The only thing the extra workers change is the ORDER the finished lines are
    printed in - and that is deliberate: the updater reads them as they arrive
    to refine its ETA. Which suites run, what each result means and the final
    counts are the same code (`_suite_job`) as the one-at-a-time path.

    Each worker owns one private state folder (made in `_sweep`), so two
    suites never write their config folder, audit log or scratch into one
    another. A job that raises is reported as a FAILED suite with its error
    rather than taking the other 300 results down with it."""
    free = list(worker_envs)
    guard = threading.Lock()
    print_lock = threading.Lock()

    def work(suite: Path) -> dict:
        with guard:
            env = free.pop()
        try:
            return _suite_job(suite, backend, env)
        finally:
            with guard:
                free.append(env)

    futures = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(worker_envs)) as pool:
        for suite in suites:
            futures[pool.submit(work, suite)] = suite
        for future in concurrent.futures.as_completed(futures):
            try:
                got = future.result()
            except Exception as exc:            # noqa: BLE001 - one job's bug
                name = futures[future].name
                got = {"name": name, "status": "FAIL",
                       "counts": {"passed": 0, "skipped": 0, "failed": 1},
                       "line": f"FAIL  {name:<34}  (worker error)  the job "
                               f"raised {type(exc).__name__}: {exc}",
                       "echo": [], "tail": []}
            with print_lock:
                _print_job(got, ran, passed, failed, skipped)


def _sweep(root: Path, only=(), jobs: int = 1) -> int:
    """One run, inside `root`: reap what a dead run left, stage, run each
    suite, report. Never called except from `main`, which owns `root`."""
    jobs = max(1, int(jobs))
    reaped = reap_orphans(keep=(root,))
    if reaped:
        print(f"reaped {len(reaped)} staging folder(s) an earlier run left behind: "
              + ", ".join(reaped))
    real = os.environ.get("JARVIS_BACKEND")
    backend = Path(real).resolve() if real else stage(root)
    print(f"backend: {backend}" + ("" if real else "  (staged: every shipped module, flattened)"))
    known = sorted(HERE.glob("test_*.py"))
    suites = [s for s in known if s.name in only] if only else known
    names = {s.name for s in suites}
    unknown = [n for n in only if n not in {s.name for s in known}]
    stale = [] if only else sorted(set(NEEDS_OWNER) - names)
    passed, failed, skipped = [], [], []
    # The checks inside the suites that ran, summed from what each suite
    # reported. A suite that exits 0 having skipped every check it has is still
    # "ok" here - the numbers beside it are what say so.
    ran = {"passed": 0, "skipped": 0, "failed": 0}
    if unknown:
        print(f"FAIL  no suite here is named: {', '.join(unknown)}")
        failed += unknown
    if stale:
        print(f"FAIL  run_suites.py lists suites that do not exist: {stale}")
        failed += stale
    no_owner = sorted(k for k, v in NEEDS_OWNER.items() if not set(v) & OWNER_FILES)
    if no_owner:
        print(f"FAIL  run_suites.py skips suites that need nothing from the owner's PC: {no_owner}")
        failed += no_owner
    base = dict(os.environ, JARVIS_BACKEND=str(backend),
                PYTHONDONTWRITEBYTECODE="1")
    if jobs == 1:
        state = root / STATE_NAME
        worker_envs = [suite_temp_env(private_state(base, backend, state), root)]
        print(f"state: {state}  (config folder and audit log for this run, not yours)")
        for suite in suites:
            _print_job(_suite_job(suite, backend, worker_envs[0]),
                       ran, passed, failed, skipped)
    else:
        worker_envs = []
        for index in range(jobs):
            state = root / f"{STATE_NAME}-{index + 1}"
            worker_envs.append(suite_temp_env(
                private_state(dict(base), backend, state), state))
        print(f"state: {root / STATE_NAME}-1 .. -{jobs}  ({jobs} worker folders: "
              f"config folder and audit log for this run, not yours)")
        _sweep_parallel(suites, backend, worker_envs, ran, passed, failed, skipped)
    # No rmtree here any more: `root` - which holds the staged backend (unless
    # JARVIS_BACKEND named a real one), the state folder and the suites' own
    # scratch - is removed by main()'s `finally`, on every path out of here.
    print(f"\n{ran['passed']} passed, {ran['skipped']} skipped, {ran['failed']} failed")
    if ran["skipped"] or skipped:
        print(f"      (a skip is a check that could not run here: {ran['skipped']} inside the "
              f"suites above, {len(skipped)} whole suite(s) that need files which live only on "
              f"the owner's PC)")
    if failed:
        shown = sorted(failed) if jobs > 1 else failed
        print("failed: " + ", ".join(shown))
    return 1 if failed else 0


def state_env(where: str) -> int:
    """`--state-env DIR`: print, one KEY=VALUE a line, the variables that send
    the suites' state to DIR. apply-patches.ps1 runs the suites itself, one by
    one, and sets these first - so the two runners cannot disagree about
    where test state goes.

    PYTHONIOENCODING is printed here for a different reason: apply-patches.ps1
    runs each suite as its own process, so without it in this list the suites
    it runs would still be on the console's code page and still crash on a
    non-ASCII suite name (see private_state). A variable already set to this
    value is not printed, which is fine - the script's own copy is the same."""
    backend = Path(os.environ.get("JARVIS_BACKEND") or HERE).resolve()
    env = private_state(dict(os.environ), backend, Path(where))
    for k in ("OPENJARVIS_CONFIG_DIR", "JARVIS_CONFIG_DIR", "JARVIS_FRAMEWORK_TOML",
              "PYTHONIOENCODING"):
        if env.get(k) and env.get(k) != os.environ.get(k):
            print(f"{k}={env[k]}")
    return 0


if __name__ == "__main__":
    args = list(sys.argv[1:])
    jobs = 1
    ignore_update_lock = False
    if LOCK_BYPASS_FLAG in args:
        # The update's own suite phase: it holds the lock, so it must not
        # refuse itself. Any other caller asking for this is saying "I know an
        # update is running and I want to add to the CPU load anyway".
        ignore_update_lock = True
        args.remove(LOCK_BYPASS_FLAG)
    if "--jobs" in args:
        at = args.index("--jobs")
        try:
            jobs = int(args[at + 1])
        except (IndexError, ValueError):
            print("FAIL  --jobs needs a whole number of workers, e.g. --jobs 14",
                  file=sys.stderr)
            sys.exit(2)
        del args[at:at + 2]
    if len(args) == 2 and args[0] == "--state-env":
        sys.exit(state_env(args[1]))
    sys.exit(main(tuple(a for a in args if a.startswith("test_")),
                  max(1, jobs), ignore_update_lock=ignore_update_lock))
