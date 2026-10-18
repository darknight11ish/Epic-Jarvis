"""tools/update_backend.py - the owner's one backend update, at a chosen pace.

    python -B tools/update_backend.py --repo <clone> --backend <backend folder> --mode responsive

WHY THIS EXISTS

The desktop's "Update both halves" button used to run
`scripts/apply-patches.ps1` and let that script run the test suites too, one at
a time. That works, and it is slow: every check waits for the one before it,
so an update that could be finished while the owner makes a coffee instead
sits there for the length of the whole list. This tool keeps the patcher
exactly as it is - it is the one program allowed to change the backend folder -
and adds the missing piece: **apply the patches with `-SkipTests`, then run the
same suite list from `backend/run_suites.py` with a chosen number of workers.**

Three paces, and all three run the SAME checks:

    mode        workers   what it means
    max_speed   20 - 22   nearly the whole PC while it checks: quickest
    responsive  12 - 16   about half the PC: quick, and the PC stays usable
    safe         1        one check at a time: slowest, safest on a busy PC

`responsive` (14 workers) is the default and the recommended one. `max_speed`
is clamped to 20-22 and `responsive` to 12-16, so a caller cannot ask for more
than the mode promises; `safe` is clamped to 1 and can never run in parallel.
An unknown mode is refused before anything runs.

WHAT IT DOES, IN ORDER

1. `scripts/apply-patches.ps1 -BackendPath <backend> -SkipTests` - the same
   script, the same backups (`_jarvis-backup-<stamp>`), the same rehearsal
   rule. This tool never patches a file itself.
2. **Verifies the live files.** Every module the repository ships whole is
   compared, byte for byte (line endings normalised), with the copy in
   `jarvis-backend/`. A mismatch is a failed update, not a warning: it is the
   state where the folder on this PC is not the code this repository says it
   is.
3. `backend/run_suites.py --jobs <workers>` - the SAME suite list CI runs,
   with the chosen worker count. `run_suites.py`'s default is 1, so CI is
   untouched.
4. Records each suite's own time in `<backend>/_jarvis-logs/update-timings.json`
   **per pace** - the same suites take different wall time at 22 workers and at
   1, so a `safe` run is not evidence for `max_speed`. A pace that has not
   completed a run yet says "unmeasured for this pace" and shows a wide range;
   the first run of each pace measures it.

THE UPDATE LOCK (exclusive update, one PC)

Before a file is patched, this tool takes `update-in-progress.lock` in the
folder Jarvis keeps its own data in (`OPENJARVIS_CONFIG_DIR`, then
`JARVIS_CONFIG_DIR`, then `~/.openjarvis`), holding
`{pid, started_at, updated_at, pace}`. The take is atomic (one winner; an
existing live file is never overwritten). The suites this update starts are told
to ignore it (`--ignore-update-lock`); everything else on the PC is not:
`backend/run_suites.py` refuses while a valid lock is held - once at the start
and again just before the first suite - and the desktop's backend watchdog, its
`update_both` press and every backend start path obey it (`sidecar.rs`,
`update.rs`). Validity is: the pid is really running, the heartbeat
(`updated_at`) is less than 30 minutes old. The heartbeat is refreshed as each
suite finishes AND through the patch phase's progress lines (at most every five
minutes), so a long patch or a two-hour `safe` run never expires its own lock.
The 3-hour `started_at` window is a PID-REUSE guard only: a live run renews it
while it keeps heartbeating, so a legitimately long run is not treated as
stale; a dead pid is stale at once, so a crashed update never keeps the next one
out. Non-finite or future timestamps mean the PC's clock moved and are read as
stale, the same rule the Rust reader applies.

THE SAFE FALLBACK (mandatory)

A quick mode is an optimisation, never a promise. Any failed or ambiguous
suite, a worker that crashes, or a live-file mismatch in `max_speed` or
`responsive` means the quick result is not trusted: the tool restores every
file from the newest `_jarvis-backup-*` folder (copying back; the backup is
never deleted), then runs the whole thing again as `safe` - one check at a
time. The card says "quick check hit a problem - re-running the safe way, new
ETA", and the safe pass is what the update is judged by. A failure in `safe`
mode itself is reported and not re-run, because re-running the same checks the
same way is not a second opinion.

WHAT IT WRITES, AND WHAT IT DOES NOT

- Writes: the patcher's own `_jarvis-backup-*` folders (by the patcher), its
  own logs (by the patcher), `update-timings.json` beside them, and the
  `update-in-progress.lock` in the folder Jarvis keeps its own data in (it is
  removed when the update ends; a crash leaves it to the dead-pid rule).
  Nothing else, nowhere else.
- Does NOT write: `scripts/apply-patches.ps1` or any other repository file,
  the desktop app's settings, or anything else in the owner's
  `~/.openjarvis`.
- Does NOT talk to the network. The only process it starts are PowerShell (the
  patcher) and Python (`run_suites.py`).

THE EVENTS

The desktop card is already event-driven: it tails this tool's output and
`update_progress.rs` reads it. So besides plain lines for the log, this tool
prints one `JARVIS-EVENT {json}` line per progress change - phase, counts, the
refined ETA, the mode, and whether the safe fallback is now running. The
desktop shows those; a terminal shows them too, and they are the only machine
interface.

`--modes-json` prints the three modes and their current ETA ranges as one JSON
object (that is what the desktop's Updates card reads before the owner picks a
pace). It runs nothing.
"""
from __future__ import annotations

import ast
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

KIND = "update_backend"
EVENT_PREFIX = "JARVIS-EVENT "
TIMINGS_NAME = "update-timings.json"
LOG_DIR = "_jarvis-logs"
BACKUP_PREFIX = "_jarvis-backup-"
PATCHER_REL = Path("scripts") / "apply-patches.ps1"
SUITES_REL = Path("backend") / "run_suites.py"
WHERE_REL = Path("backend") / "_where.py"
BASE_REL = Path("jarvis-backend")

#: The three paces. `plain` is what the owner reads on the card; `effect` is
#: the one-line honest description of what the PC will feel like.
MODES = {
    "max_speed": {
        "workers_low": 20, "workers_high": 22, "workers": 22,
        "label": "Fastest",
        "plain": "It uses nearly the whole PC while it checks. Quickest, but "
                 "the PC will be busy until it is done.",
        "recommended": False,
    },
    "responsive": {
        "workers_low": 12, "workers_high": 16, "workers": 14,
        "label": "Balanced",
        "plain": "It uses about half the PC while it checks. Still quick, and "
                 "the PC stays usable.",
        "recommended": True,
    },
    "safe": {
        "workers_low": 1, "workers_high": 1, "workers": 1,
        "label": "Safest",
        "plain": "One check at a time. Slowest, and nothing else on the PC is "
                 "competing with it.",
        "recommended": False,
    },
}
MODE_ORDER = ("max_speed", "responsive", "safe")
DEFAULT_MODE = "responsive"

#: First-run placeholders: this project treats every number picked before it
#: was measured as `N_placeholder`. A suite averages a couple of seconds and
#: the patch phase is the script's own work; both are replaced by the recorded
#: timings after the first real run.
PLACEHOLDER_SUITE_SECONDS = 1.5
PLACEHOLDER_PATCH_SECONDS = 120.0
#: Parallel work is never perfectly free: process start-up, the GIL-free parts
#: of the runner and the disk all cost something. Added as a fraction of the
#: one-at-a-time work so `safe` stays the honest worst case.
PARALLEL_OVERHEAD = 0.02
#: How wide the first-run range is, and how much a measured estimate still
#: moves. Deliberately wide when nothing has been measured: a narrow number
#: invented before the first run is exactly the sort of claim this project
#: does not make.
UNMEASURED_LOW, UNMEASURED_HIGH = 0.5, 2.5
MEASURED_LOW, MEASURED_HIGH = 0.85, 1.15
#: A timing set counts as measured when this much of the suite list has a time
#: AND the patch phase has one too. Below it, the estimate still says so.
MEASURED_COVERAGE = 0.8

MODES_WORD = "max_speed, responsive, safe"


class UpdateRefused(Exception):
    """A refusal that is the caller's or the PC's state, not a crash.

    `code` is a stable word (what tests and the card key on); `message` is the
    plain sentence the owner would read.
    """

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# ---------------------------------------------------------------------------
#   The update lock - one update at a time, on this PC
# ---------------------------------------------------------------------------
#
# WHY IT EXISTS. An update patches the backend and then runs several hundred
# suites against it. Two things must not happen at once: a second update (it
# would patch files the first is proving), and a test run or the desktop's
# watchdog starting the backend in the middle of it (the watchdog restarted the
# backend twice during a real 2h8m update, and the restarted process refused the
# port while the first one still held it).
#
# THE FILE. `update-in-progress.lock` in the folder Jarvis keeps its own data
# in: OPENJARVIS_CONFIG_DIR, then JARVIS_CONFIG_DIR, then `~/.openjarvis` - the
# same order `jarvis_framework._config_dir`, `backup.rs` and every other reader
# uses. It holds one JSON object:
#
#     {"pid": 12345, "started_at": 1760000000.0,
#      "updated_at": 1760000300.0, "pace": "responsive"}
#
# WHAT MAKES IT VALID. The lock is trusted only while its writer is really
# running AND it is being kept fresh:
#   * a DEAD pid is stale immediately - no waiting after a crash;
#   * otherwise stale when `now - updated_at > LOCK_HEARTBEAT_SECONDS` (the
#     writer refreshes it as each suite finishes and, bounded, as the patcher
#     makes progress), or when `now - started_at > LOCK_CEILING_SECONDS`.
#   * the ceiling is a PID-REUSE guard only: a live writer renews `started_at`
#     as it heartbeats, so a real long run is never stale by accident;
#   * non-finite or future timestamps mean the clock moved - stale, and the
#     same rule in Rust so both readers agree about one file.
# THE TAKE is ATOMIC: the new file is published whole and an existing file is
# never overwritten (unique temp + hard-link/`O_EXCL`), so two updates starting
# at the same instant have exactly one winner and the other is refused.
# It is advisory, and it says so: a lock that cannot be written or read is
# reported, never enforced by pretending.
LOCK_NAME = "update-in-progress.lock"
#: Stale when no suite has finished for this long. `N_placeholder` (design
#: section: 30 minutes), calibrated against a real `safe` run later.
LOCK_HEARTBEAT_SECONDS = 1800.0
#: Stale when the run started longer ago than this, whatever the heartbeat
#: says - a ceiling above the longest measured run (`N_placeholder`). Since the
#: S2 review it is a PID-REUSE guard only: a live run that keeps heartbeating
#: renews its own `started_at` before this can lapse (see `refresh_lock`), so
#: this can only end a lock whose writer has stopped proving it is alive.
LOCK_CEILING_SECONDS = 10800.0
#: The patch phase refreshes the lock through its own progress lines, at most
#: once per this many seconds (S1): the patcher can run for a long time before
#: the first suite finishes, and "no finished suite" must not mean "abandoned".
LOCK_PATCH_HEARTBEAT_SECONDS = 300.0
#: Reading a lock recorded more than this far in the future means the PC's
#: clock moved (S6); Python and Rust both reject it, so they agree about a file
#: written before a clock correction.
LOCK_CLOCK_SKEW_SECONDS = 60.0
#: A lock file larger than this is not a lock (S7): bounded so a corrupt or
#: hostile file can never make the desktop's watchdog or a test run read a
#: whole disk's worth of bytes.
LOCK_MAX_BYTES = 64 * 1024
#: How many read/replace attempts `acquire_lock` makes when another updater
#: publishes at the same instant (S3). Each attempt either wins or sees the
#: winner's complete file; four is far more than a real race needs.
LOCK_ACQUIRE_ATTEMPTS = 4
#: The bypass for the update's OWN child suite run (its suites are supposed to
#: run while the lock is held - they are what the lock protects).
LOCK_BYPASS_ENV = "JARVIS_INSIDE_PATCHER"
LOCK_BYPASS_FLAG = "--ignore-update-lock"


def settings_dir() -> Path:
    """The folder Jarvis keeps its own data in - the repository's real rule.

    `OPENJARVIS_CONFIG_DIR`, then `JARVIS_CONFIG_DIR`, then `~/.openjarvis`.
    The lock lives here, not in the clone or the backend folder: it is about
    this PC, and the desktop app, the update tool and `run_suites.py` all have
    to find the same file.
    """
    for name in ("OPENJARVIS_CONFIG_DIR", "JARVIS_CONFIG_DIR"):
        value = os.environ.get(name)
        if value:
            return Path(os.path.expanduser(value))
    return Path(os.path.expanduser("~")) / ".openjarvis"


def lock_path(settings=None) -> Path:
    """The lock file's path: `settings` when a caller names one (the tests),
    else the folder rule above."""
    return (Path(settings) if settings else settings_dir()) / LOCK_NAME


def pid_alive(pid) -> bool:
    """Is `pid` a running process on THIS machine? Never raises.

    Windows answers through OpenProcess/GetExitCodeProcess rather than
    `os.kill(pid, 0)`: on Windows `os.kill` is not an existence probe - it ends
    processes - and the wrong signal here would kill the update it is checking.
    POSIX uses `kill(pid, 0)`, the documented existence probe.
    """
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes
            kernel32 = ctypes.windll.kernel32
            kernel32.OpenProcess.restype = wintypes.HANDLE
            kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL,
                                             wintypes.DWORD]
            kernel32.GetExitCodeProcess.restype = wintypes.BOOL
            kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE,
                                                    ctypes.POINTER(wintypes.DWORD)]
            kernel32.CloseHandle.restype = wintypes.BOOL
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            # PROCESS_QUERY_LIMITED_INFORMATION (0x1000) is enough to ask about
            # the process; SYNCHRONIZE (0x00100000) is kept because it was the
            # pair the design named. A pid that has ended gives no handle.
            handle = kernel32.OpenProcess(0x1000 | 0x00100000, False, pid)
            if not handle:
                return False
            try:
                code = wintypes.DWORD()
                if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                    return True        # it exists; we just cannot read its code
                return code.value == 259      # STILL_ACTIVE
            finally:
                kernel32.CloseHandle(handle)
        except Exception:                  # noqa: BLE001 - never a crash
            return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True                        # it exists, we cannot signal it
    except OSError:
        return False


def _lock_blank(path: Path) -> dict:
    return {"path": str(path), "present": False, "valid": False, "stale": False,
            "pid": None, "started_at": None, "updated_at": None,
            "pace": "", "why": "no backend update is running"}


def _lock_words(time_value) -> str:
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(float(time_value)))
    except (TypeError, ValueError, OSError):
        return "an unreadable time"


def lock_words(lock: dict) -> str:
    """The plain sentence naming a HELD lock: pid, pace and when it started."""
    pace = str((lock or {}).get("pace") or "")
    if pace in MODES:
        pace = f"{pace} ({MODES[pace]['label']})"
    return (f"A Jarvis backend update is already running (pid "
            f"{(lock or {}).get('pid')}, pace {pace or 'unknown'}, started "
            f"{_lock_words((lock or {}).get('started_at'))}).")


def lock_refusal_words(lock: dict) -> str:
    """The same sentence, plus what the reader can do about it."""
    return (lock_words(lock)
            + " Wait for it to finish. Pass `--ignore-update-lock` (or set "
              f"{LOCK_BYPASS_ENV}=1) only when this run is that update's own "
              "suite phase.")


def _read_lock_bytes(target: Path):
    """The lock file's first `LOCK_MAX_BYTES + 1` bytes, or None. Never raises."""
    try:
        with target.open("rb") as handle:
            return handle.read(LOCK_MAX_BYTES + 1)
    except OSError:
        return None


def read_lock(path=None, *, now=None, alive=None) -> dict:
    """The lock's state, read without ever raising.

    Returns a dict that always answers `present`, `valid`, `stale` and *why*.
    A missing file, a file full of binary junk, a file that is not a lock, a
    file too large to be one, a directory at that path - and a JSON document
    nested so deeply that the parser would recurse (S7) - are all "no valid
    lock", never an exception on a path the desktop's watchdog and the test
    runner both read. Times must be real numbers (NaN and Infinity are rejected,
    S6) and not in the future (a clock change is not evidence of a live update).
    """
    target = Path(path) if path is not None else lock_path()
    state = _lock_blank(target)
    raw = _read_lock_bytes(target)
    if raw is None:
        return state
    state["present"] = True
    if len(raw) > LOCK_MAX_BYTES:
        state.update(stale=True, why="the update lock file is too large to be one, "
                                      "so it is treated as stale")
        return state
    try:
        # Bytes, then a replacing decode: binary junk is "unreadable", which is
        # a stale lock - not a Unicode exception on a file two readers share.
        # The broad catch is deliberate: `json.loads` raises RecursionError on a
        # deeply nested document, and the promise here is never to raise (S7).
        data = json.loads(raw.decode("utf-8", "replace"))
    except Exception:                      # noqa: BLE001 - never a crash
        state.update(stale=True, why="the update lock file is unreadable, "
                                      "so it is treated as stale")
        return state
    if not isinstance(data, dict):
        state.update(stale=True, why="the update lock file is unreadable, "
                                      "so it is treated as stale")
        return state
    pid = data.get("pid")
    started = data.get("started_at")
    updated = data.get("updated_at")
    pace = data.get("pace")
    numbers_ok = (
        isinstance(pid, int) and not isinstance(pid, bool) and pid > 0
        and isinstance(started, (int, float)) and not isinstance(started, bool)
        and isinstance(updated, (int, float)) and not isinstance(updated, bool)
        and math.isfinite(float(started)) and math.isfinite(float(updated))
        and isinstance(pace, str)
    )
    if not numbers_ok:
        state.update(pid=pid if isinstance(pid, int) and not isinstance(pid, bool)
                     else None,
                     stale=True,
                     why="the update lock file is missing its pid, real times or "
                         "pace, so it is treated as stale")
        return state
    started, updated = float(started), float(updated)
    now = time.time() if now is None else float(now)
    state.update(pid=int(pid), started_at=started, updated_at=updated, pace=pace)
    if (started > now + LOCK_CLOCK_SKEW_SECONDS
            or updated > now + LOCK_CLOCK_SKEW_SECONDS):
        state.update(stale=True, why="the update lock records a time in the future, "
                                      "so the PC's clock has changed; it is treated "
                                      "as stale")
        return state
    check_alive = alive if callable(alive) else pid_alive
    try:
        running = bool(check_alive(int(pid)))
    except Exception:                      # noqa: BLE001 - never a crash
        running = False
    if not running:
        state.update(stale=True, why=f"the update process (pid {pid}) is no longer "
                                      "running, so the lock is stale")
        return state
    if now - updated > LOCK_HEARTBEAT_SECONDS:
        minutes = int(LOCK_HEARTBEAT_SECONDS // 60)
        state.update(stale=True, why=f"the update has not updated its lock for over "
                                      f"{minutes} minutes, so it is treated as stale")
        return state
    if now - started > LOCK_CEILING_SECONDS:
        hours = int(LOCK_CEILING_SECONDS // 3600)
        state.update(stale=True, why=f"the update started over {hours} hours ago "
                                      "without renewing that window, so the lock is "
                                      "treated as stale (the pid may have been reused)")
        return state
    state.update(valid=True, why="")
    return state


def lock_held(path=None, *, now=None, alive=None) -> bool:
    """True while a valid update lock is held. The one question every reader asks."""
    return bool(read_lock(path, now=now, alive=alive).get("valid"))


def _write_lock(target: Path, data: dict) -> bool:
    """Replace the lock atomically, with a UNIQUE temp name (S3).

    False when it cannot be written (never raises). The unique name matters on
    its own: two writers sharing one `.tmp` path made the loser fail for the
    wrong reason, and made a writable folder look unwritable.
    """
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(data, indent=1, sort_keys=True) + "\n"
        fd, temp_name = tempfile.mkstemp(prefix=target.name + ".",
                                         suffix=".tmp", dir=str(target.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
            os.replace(temp_name, target)
        finally:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
        return True
    except OSError:
        return False


def _published_ours(target: Path, owner: int) -> bool:
    """Is the complete lock file at `target` the one this call published?"""
    raw = _read_lock_bytes(target)
    if raw is None:
        return False
    try:
        data = json.loads(raw.decode("utf-8", "replace"))
    except Exception:                      # noqa: BLE001 - never a crash
        return False
    return isinstance(data, dict) and data.get("pid") == owner


def _publish_new_lock(target: Path, data: dict) -> bool:
    """Create the lock only if it does not exist. True = won, False = taken.

    The bytes go to a unique temp file first and `os.link` publishes THAT file:
    atomic, refuses an existing destination, and a reader never sees a
    half-written lock, so two updaters starting at the same instant cannot both
    win (S3). Filesystems without hard links fall back to an exclusive
    `O_CREAT|O_EXCL` create, which still guarantees one winner. Raises OSError
    only when the folder itself cannot be written.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(data, indent=1, sort_keys=True) + "\n").encode("utf-8")
    fd, temp_name = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp",
                                     dir=str(target.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
        try:
            os.link(temp_name, target)
            return True
        except FileExistsError:
            return False
        except OSError:
            pass                            # no hard links here: O_EXCL fallback
        try:
            fresh = os.open(str(target), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            return False
        try:
            os.write(fresh, payload)
        finally:
            os.close(fresh)
        return True
    finally:
        try:
            os.unlink(temp_name)
        except OSError:
            pass


def acquire_lock(pace: str, *, path=None, now=None, pid=None, alive=None) -> dict:
    """Take the lock for this update, or refuse when a live one is held.

    The take is ATOMIC (S3): the file is published whole and an existing file
    can never be overwritten, so of two updaters starting at the same instant
    exactly one gets `ok: True` - the other gets `UpdateRefused` with a plain
    reason, never a false "the folder is unwritable". A STALE lock (dead pid,
    silent heartbeat, ceiling passed) is removed and replaced, so a crashed
    patcher never keeps the next update out. If the folder really cannot be
    written the update still runs with `ok` False and a `why` that says the lock
    is NOT protecting it: a lock nobody enforced is said, never pretended.
    """
    target = Path(path) if path is not None else lock_path()
    now = time.time() if now is None else float(now)
    owner = os.getpid() if pid is None else int(pid)
    for _attempt in range(LOCK_ACQUIRE_ATTEMPTS):
        current = read_lock(target, now=now, alive=alive)
        if current["valid"]:
            raise UpdateRefused("update_running", lock_refusal_words(current))
        if current["present"]:
            # A stale lock is replaced, but one remover at a time: unlink, then
            # loop so a racer's just-published lock is read and respected.
            try:
                target.unlink()
            except FileNotFoundError:
                pass
            except OSError as exc:
                return {"ok": False, "lock": current, "pid": owner,
                        "why": f"the stale update lock at {target} could not be "
                               f"removed ({exc.strerror or exc}), so this update is "
                               "NOT locked: other test runs and the desktop may start "
                               "work beside it"}
            continue
        data = {"pid": owner, "started_at": now, "updated_at": now,
                "pace": str(pace)}
        try:
            created = _publish_new_lock(target, data)
        except OSError as exc:
            return {"ok": False, "lock": current, "pid": owner,
                    "why": f"the update lock could not be written to {target} "
                           f"({exc.strerror or exc}), so other test runs and the "
                           "desktop will not know this update is running"}
        if not created:
            continue                        # someone else published first
        if _published_ours(target, owner):
            return {"ok": True,
                    "lock": read_lock(target, now=now, alive=alive or pid_alive),
                    "pid": owner, "why": ""}
        # The complete file was replaced or removed in the same instant: this
        # update did not get the lock. Say so plainly and do not run beside it.
        raise UpdateRefused(
            "update_running",
            "Another Jarvis backend update started at the same moment and holds "
            "the lock. Wait for it to finish; nothing was patched here.")
    raise UpdateRefused(
        "update_running",
        "Another Jarvis backend update is starting at the same moment. Wait a "
        "moment and try again; nothing was patched here.")


def refresh_lock(*, path=None, now=None, pid=None) -> bool:
    """Move `updated_at` forward - the heartbeat - and renew the ceiling (S2).

    While this process is alive it also renews `started_at` one heartbeat window
    before the 3-hour PID-REUSE guard could lapse, so a legitimately long run
    (the measured 2h8m, or a quick pass plus its safe fallback) is never treated
    as stale while it is alive; a dead or reused pid cannot renew anything, so
    the guard still ends that lock. False when there is no lock to refresh, when
    the file cannot be written, or when the lock belongs to another pid. Never
    raises, so a heartbeat failure cannot take the update down.
    """
    target = Path(path) if path is not None else lock_path()
    now = time.time() if now is None else float(now)
    owner = os.getpid() if pid is None else int(pid)
    state = read_lock(target, now=now)
    if not state["present"] or state["pid"] is None:
        return False
    if int(state["pid"]) != owner:
        return False
    started = float(state["started_at"])
    if now - started > LOCK_CEILING_SECONDS - LOCK_HEARTBEAT_SECONDS:
        started = now
    data = {"pid": int(state["pid"]), "started_at": started,
            "updated_at": now, "pace": str(state["pace"] or "")}
    return _write_lock(target, data)


def release_lock(*, path=None, pid=None) -> bool:
    """Remove the lock, but only when this pid owns it. Never raises.

    A crash never reaches this line - that is what the dead-pid rule is for.
    Removing another update's lock is the one thing this must not do, so the
    owner is read back first and a mismatch leaves the file alone.
    """
    target = Path(path) if path is not None else lock_path()
    owner = os.getpid() if pid is None else int(pid)
    state = read_lock(target)
    if state["present"] and state["pid"] is not None and int(state["pid"]) != owner:
        return False
    try:
        target.unlink()
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
#   Modes and workers - pure, and the only place a pace is decided
# ---------------------------------------------------------------------------

def mode_spec(mode: str) -> dict:
    """This mode's table entry. An unknown mode is refused, never defaulted.

    Silently treating an unknown mode as `responsive` would mean a caller that
    asked for something this build does not have got a different update than
    it asked for, with nothing said - which is the class of mistake this
    project's bite tests exist for."""
    spec = MODES.get(mode)
    if spec is None:
        raise UpdateRefused(
            "unknown_mode",
            f"There is no update pace called {mode!r}. The three are: {MODES_WORD}.",
        )
    return spec


def workers_for(mode: str, requested=None) -> int:
    """How many suites this mode may run at once. Clamped, never refused.

    `requested` is honoured only inside the mode's own band, so a caller can
    ask for fewer workers in `max_speed` (a gentler run) but can never turn
    `safe` into a parallel run or `responsive` into 24: the bands ARE the
    promise the card makes to the owner. A non-integer request is refused
    (that is a programming mistake, not a preference).
    """
    spec = mode_spec(mode)
    low, high = spec["workers_low"], spec["workers_high"]
    if requested is None:
        return int(spec["workers"])
    if isinstance(requested, bool) or not isinstance(requested, int):
        raise UpdateRefused("bad_workers",
                            "--workers needs a whole number of suites to run at once.")
    if high == 1:
        return 1                       # safe is sequential whatever is asked
    return max(low, min(high, requested))


# ---------------------------------------------------------------------------
#   Recorded timings and the ETA maths - one implementation, used by both the
#   card (through --modes-json) and the run
# ---------------------------------------------------------------------------

def timings_path_for(backend) -> Path:
    return Path(backend) / LOG_DIR / TIMINGS_NAME


def _blank_pace() -> dict:
    """One pace's own timing record: patch phase, per-suite seconds, run count."""
    return {"patch_seconds": None, "suites": {}, "runs": 0}


def _blank_timings() -> dict:
    """The v2 timing file: a record PER PACE, because a pace changes the wall
    time a suite takes and a `safe` measurement is not a `max_speed` one. A
    pace with no record says "unmeasured for this pace" (wide range), never
    inherits another pace's numbers."""
    return {"kind": KIND, "version": 2,
            "paces": {mode: _blank_pace() for mode in MODE_ORDER}, "runs": 0}


def load_timings(path) -> dict:
    """The recorded timings, per pace, or a blank set. A corrupt file is a
    blank set.

    Version 1 (the first merged tool's single shared set) is deliberately NOT
    read as a measurement: it was recorded at an unknown pace, so it cannot say
    any named pace is measured. The owner loses one estimate range and gains a
    claim that is true; the first run of each pace measures it again.

    Never raises: a broken timing file costs an estimate, not an update.
    """
    blank = _blank_timings()
    try:
        raw = Path(path).read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, ValueError):
        return blank
    if not isinstance(data, dict) or data.get("version") != 2:
        return blank
    out = _blank_timings()
    paces = data.get("paces")
    if not isinstance(paces, dict):
        return blank
    for mode in MODE_ORDER:
        got = paces.get(mode)
        if not isinstance(got, dict):
            continue
        pace = out["paces"][mode]
        patch = got.get("patch_seconds")
        if isinstance(patch, (int, float)) and patch >= 0 and not isinstance(patch, bool):
            pace["patch_seconds"] = float(patch)
        suites = got.get("suites")
        if isinstance(suites, dict):
            for name, seconds in suites.items():
                if (isinstance(name, str) and isinstance(seconds, (int, float))
                        and not isinstance(seconds, bool) and seconds >= 0):
                    pace["suites"][name] = float(seconds)
        runs = got.get("runs")
        if isinstance(runs, int) and not isinstance(runs, bool) and runs >= 0:
            pace["runs"] = runs
    runs = data.get("runs")
    if isinstance(runs, int) and not isinstance(runs, bool) and runs >= 0:
        out["runs"] = runs
    return out


def pace_timings(timings: dict, mode: str) -> dict:
    """One pace's records, in the shape `estimate`/`live_eta` take.

    This is the only bridge between the file's per-pace structure and the maths:
    every caller that asks "what would this pace take?" gets its own pace's
    numbers, so `max_speed` cannot report a `safe` measurement as its own.
    """
    paces = (timings or {}).get("paces")
    got = (paces or {}).get(mode) if isinstance(paces, dict) else None
    if not isinstance(got, dict):
        return _blank_pace()
    suites = got.get("suites")
    return {"patch_seconds": got.get("patch_seconds"),
            "suites": dict(suites) if isinstance(suites, dict) else {},
            "runs": int(got.get("runs") or 0)}


def save_timings(path, *, mode: str, patch_seconds=None, durations=None) -> dict:
    """Merge this run's times into the records FOR ITS PACE, atomically.

    `mode` is the pace that actually ran (the safe fallback records under
    `safe`, because that is the pass the numbers came from). The other paces'
    records are left exactly as they were.

    Returns the stored set. **Never raises into the update**: a timing file that
    cannot be written must not fail the update it was measuring - it only costs
    the next estimate. The file is written beside itself and moved into place,
    so a crash mid-write leaves the previous times intact rather than a half
    file.
    """
    path = Path(path)
    stored = load_timings(path)
    mode = mode if mode in MODES else DEFAULT_MODE
    pace = stored["paces"][mode]
    if isinstance(patch_seconds, (int, float)) and not isinstance(patch_seconds, bool):
        pace["patch_seconds"] = float(patch_seconds)
    for name, seconds in (durations or {}).items():
        if isinstance(name, str) and isinstance(seconds, (int, float)):
            pace["suites"][name] = float(seconds)
    pace["runs"] = int(pace.get("runs") or 0) + 1
    stored["runs"] = int(stored.get("runs") or 0) + 1
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(path.name + ".tmp")
        temp.write_text(json.dumps(stored, indent=1, sort_keys=True) + "\n",
                        encoding="utf-8")
        os.replace(temp, path)
    except OSError:
        return stored
    return stored


def suite_names(repo) -> list:
    """The exact suite list every mode runs: the same glob run_suites.py uses.

    Sorted, so the estimate is computed over a stable list and the same names
    are used regardless of the order the filesystem returns them in."""
    return sorted(p.name for p in (Path(repo) / "backend").glob("test_*.py"))


def _measured(timings: dict, names: list) -> bool:
    if timings.get("patch_seconds") is None:
        return False
    if not names:
        return False
    known = sum(1 for name in names if name in timings.get("suites", {}))
    return known / len(names) >= MEASURED_COVERAGE


def _suite_work_seconds(timings: dict, names: list) -> float:
    suites = timings.get("suites", {})
    return float(sum(float(suites.get(name, PLACEHOLDER_SUITE_SECONDS))
                     for name in names))


def _parallel_factor(workers: int) -> float:
    return 1.0 if workers <= 1 else 1.0 / workers + PARALLEL_OVERHEAD


def _range(total: float, measured: bool) -> tuple:
    low = max(1.0, total * (MEASURED_LOW if measured else UNMEASURED_LOW))
    high = max(low, total * (MEASURED_HIGH if measured else UNMEASURED_HIGH))
    return int(round(low)), int(round(high))


def estimate(mode: str, names: list, timings: dict, *, requested=None) -> dict:
    """What this mode would take, from the recorded times (or placeholders).

    The arithmetic is deliberately simple and the same for every mode:
    patch phase (one process, always) + suite work / parallel factor. The
    first run has no recorded times, so `measured` is False and the range is
    wide; after a run the recorded per-suite times narrow it.

    Monotonic by construction: more workers only lower the suite term, so
    `max_speed` <= `responsive` <= `safe` for the same inputs.
    """
    workers = workers_for(mode, requested)
    measured = _measured(timings, names)
    patch_seconds = timings.get("patch_seconds")
    if patch_seconds is None:
        patch_seconds = PLACEHOLDER_PATCH_SECONDS
    suite_seconds = _suite_work_seconds(timings, names) * _parallel_factor(workers)
    total = float(patch_seconds) + suite_seconds
    low, high = _range(total, measured)
    return {
        "mode": mode,
        "workers": workers,
        "suite_count": len(names),
        "eta_seconds": int(round(total)),
        "eta_low_seconds": low,
        "eta_high_seconds": high,
        "measured": measured,
    }


def live_eta(mode: str, names: list, timings: dict, done, durations,
             *, requested=None) -> dict:
    """The remaining time once a few suites have really finished.

    Every finished suite is a measurement, and the ratio between what actually
    took and what was predicted is applied to the ones still to come (clamped,
    so one odd suite cannot swing the answer). Returns `eta_seconds` 0 when
    nothing is left.

    This is still an estimate and says so in the same words as the first-run
    one: the card shows a range, never a fake single number.
    """
    workers = workers_for(mode, requested)
    done_set = set(done or ())
    recorded = {name: seconds for name, seconds in (durations or {}).items()
                if name in set(names)}
    predicted_done = sum(float(timings.get("suites", {}).get(name,
                                                          PLACEHOLDER_SUITE_SECONDS))
                         for name in recorded)
    actual_done = sum(float(seconds) for seconds in recorded.values())
    ratio = 1.0
    if predicted_done > 0 and actual_done > 0:
        ratio = max(0.25, min(4.0, actual_done / predicted_done))
    remaining = [name for name in names if name not in done_set]
    remaining_seconds = 0.0
    for name in remaining:
        base = timings.get("suites", {}).get(name)
        if base is None:
            base = PLACEHOLDER_SUITE_SECONDS * ratio
        remaining_seconds += float(base)
    remaining_seconds *= _parallel_factor(workers)
    total = max(0.0, remaining_seconds)
    low, high = _range(total, bool(recorded)) if remaining else (0, 0)
    return {
        "mode": mode,
        "workers": workers,
        "eta_seconds": int(round(total)),
        "eta_low_seconds": low,
        "eta_high_seconds": high,
        "done": len(done or ()),
        "total": len(names),
        "measured": bool(recorded),
    }


def mode_plan(repo, backend, *, timings_path=None, requested=None) -> dict:
    """The three modes as the choice card needs them: words, workers, ETAs.

    One implementation of the maths, called by `--modes-json` (which the
    desktop's status command runs). The card is honest about what it does not
    know: each pace's `measured` is False until THAT pace has been timed on this
    PC (a `safe` measurement is not a `max_speed` one, because the wall time a
    suite takes changes with the worker count), and the card shows a range
    either way.
    """
    names = suite_names(repo)
    whole = load_timings(timings_path or timings_path_for(backend))
    rows = []
    for mode in MODE_ORDER:
        spec = mode_spec(mode)
        row = estimate(mode, names, pace_timings(whole, mode), requested=requested)
        row["id"] = mode
        row["label"] = spec["label"]
        row["plain"] = spec["plain"]
        row["recommended"] = bool(spec["recommended"])
        rows.append(row)
    return {"kind": KIND, "version": 1, "modes": rows,
            "suite_count": len(names),
            "measured": any(bool(row["measured"]) for row in rows),
            "default": DEFAULT_MODE}


# ---------------------------------------------------------------------------
#   Real progress for the bar: weighted completed work, never a timer
# ---------------------------------------------------------------------------

def suite_weights(names: list, timings: dict) -> dict:
    """Each suite's share of the checking time: recorded seconds, else the
    first-run placeholder. The progress bar is weighted by THIS, so a few slow
    suites are worth more of the bar than many fast ones - a count of finished
    files would make the bar jump while most of the work is still ahead."""
    recorded = timings.get("suites", {})
    return {name: float(recorded.get(name, PLACEHOLDER_SUITE_SECONDS))
            for name in names}


def patch_share(timings: dict, names: list, workers: int) -> float:
    """What fraction of the total estimate belongs to the patch phase.

    The patch phase runs first and is one process, so its estimated seconds are
    its share of the whole update. Capped at 0.95: the bar must have room to
    move through the checks, and it must never touch 100% before the final
    verdict."""
    patch_seconds = timings.get("patch_seconds")
    if patch_seconds is None:
        patch_seconds = PLACEHOLDER_PATCH_SECONDS
    suite_seconds = _suite_work_seconds(timings, names) * _parallel_factor(workers)
    total = float(patch_seconds) + suite_seconds
    if total <= 0:
        return 0.0
    return max(0.0, min(0.95, float(patch_seconds) / total))


def plan_split(timings: dict, names: list, workers: int) -> tuple:
    """(patch seconds, suite seconds, patch share) for the progress bar.

    The two phases have very different lengths, and a bar that treated "patch
    finished" as "half done" would lie about a phase that is most of the wait
    on this PC. The share comes from the SAME estimate the card shows, through
    the one `patch_share` implementation, so the bar and the ETA cannot
    disagree."""
    patch_seconds = timings.get("patch_seconds")
    if patch_seconds is None:
        patch_seconds = PLACEHOLDER_PATCH_SECONDS
    suite_seconds = _suite_work_seconds(timings, names) * _parallel_factor(workers)
    return (int(round(float(patch_seconds))), int(round(suite_seconds)),
            patch_share(timings, names, workers))


def phase_fraction(phase: str, *, patch_share: float = 0.0,
                   patch_done: int = 0, patch_total=None,
                   weight_done: float = 0.0, weight_total: float = 0.0) -> float:
    """The bar's real fraction, from completed work and the estimate split.

    - patching: the patcher's own count of applied items / its own total;
    - verifying: the patch phase's share is done;
    - testing: the patch share plus the rest, scaled by the WEIGHT of finished
      suites (recorded times, else placeholders) - not by how many lines have
      been printed;
    - every phase except the final `done` is capped below 1.0, so 100% can only
      come from the tool's own verdict. Pure, so the rule is a test.
    """
    if phase == "done":
        return 1.0
    if phase in ("patching", "rehearsing", "applying"):
        done_fraction = (min(1.0, patch_done / patch_total)
                         if patch_total else 0.0)
        raw = patch_share * done_fraction
    elif phase in ("verifying", "fallback"):
        raw = patch_share
    elif phase == "testing":
        done_fraction = (min(1.0, weight_done / weight_total)
                         if weight_total > 0 else 0.0)
        raw = patch_share + (0.99 - patch_share) * done_fraction
    else:
        raw = 0.0
    return round(max(0.0, min(0.99, raw)), 4)


# ---------------------------------------------------------------------------
#   The commands this tool runs - and everything it refuses to guess
# ---------------------------------------------------------------------------

def patcher_command(repo, backend) -> list:
    """The patcher, exactly as the documented line runs it, plus -SkipTests.

    Nothing about patching is reimplemented here: this is the script the owner
    would paste into PowerShell himself, with the suite phase left to step 3 of
    this tool (which runs the same suites, in parallel when asked)."""
    return [
        "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
        str(Path(repo) / PATCHER_REL), "-BackendPath", str(Path(backend)),
        "-SkipTests",
    ]


def suites_command(repo, workers: int) -> list:
    """run_suites.py with ONLY the worker count changed. Default stays 1.

    A mode that changed which suites run would not be a pace, it would be a
    different update; the list is the same glob for all three.

    `--ignore-update-lock` is passed because this IS the update's own suite
    phase: the update holds the lock (see `acquire_lock`), and its own checks
    are exactly what the lock exists to protect. Without it, run_suites.py
    would refuse the very run that holds the lock."""
    return [sys.executable, "-B", str(Path(repo) / SUITES_REL),
            "--jobs", str(int(workers)), LOCK_BYPASS_FLAG]


def preflight(repo, backend) -> None:
    """Refuse, before anything runs, when this PC does not have what an update
    needs. The same two paths the desktop card already checks, checked again
    here because this tool is also reachable by hand."""
    repo = Path(repo)
    backend = Path(backend)
    if not repo.is_dir():
        raise UpdateRefused("no_repo", f"There is no folder at {repo} to update from.")
    if not (repo / PATCHER_REL).is_file():
        raise UpdateRefused(
            "no_patcher",
            f"{repo} does not contain {PATCHER_REL}, so this is not the Jarvis "
            "program folder.")
    if not (repo / SUITES_REL).is_file():
        raise UpdateRefused("no_runner",
                            f"{repo / SUITES_REL} is missing, so the checks cannot run.")
    if not backend.is_dir():
        raise UpdateRefused("no_backend", f"There is no folder at {backend} to update.")
    if not (backend / "jarvis_hud.py").is_file():
        raise UpdateRefused(
            "no_backend",
            f"{backend} does not contain jarvis_hud.py, so it is not the Jarvis "
            "backend folder.")


# ---------------------------------------------------------------------------
#   Live-file verification: is the folder really the code this repo says?
# ---------------------------------------------------------------------------

def _same_bytes(one: bytes, other: bytes) -> bool:
    # Line endings do not count: a Windows checkout may hold CRLF copies of
    # files that are LF in the repository, and the checks read both the same.
    return one.replace(b"\r\n", b"\n") == other.replace(b"\r\n", b"\n")


def shipped_leaves(repo) -> list:
    """The file names `backend/_where.py`'s SHIPPED tuple says reach the PC.

    Read by parsing the tuple (`ast`), never by importing `_where`: importing it
    stages a scratch folder and sets TEMP, which is a test-runner behaviour this
    update tool has no business triggering. A `_where.py` without the tuple is
    a refusal rather than an empty check that would pass everything.
    """
    source = (Path(repo) / WHERE_REL).read_text(encoding="utf-8")
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise UpdateRefused("no_shipped_list",
                            f"{WHERE_REL} does not parse: {exc}") from exc
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "SHIPPED"
                   for target in node.targets):
            continue
        if not isinstance(node.value, (ast.Tuple, ast.List)):
            continue
        rels = [element.value for element in node.value.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)]
        if rels:
            return [rel.rsplit("/", 1)[-1] for rel in rels]
    raise UpdateRefused("no_shipped_list",
                        f"{WHERE_REL} has no SHIPPED list, so the live files "
                        "cannot be verified.")


def verify_live_files(repo, backend) -> list:
    """Every shipped file on the PC against its twin in this repository.

    A shipped file is copied whole by the patcher, so after a good update the
    two are byte-identical (modulo line endings). A difference means the folder
    is not the code this repository says - which is why it is a fallback
    trigger rather than a warning. The owner-only files a patch writes
    (`jarvis_gate.py`, `jarvis_hud.py`) are not in SHIPPED and are not
    compared: this repository has no version of them to compare against.
    """
    repo = Path(repo)
    backend = Path(backend)
    problems = []
    for leaf in shipped_leaves(repo):
        live = backend / leaf
        twin = repo / BASE_REL / leaf
        if not twin.is_file():
            continue                       # e.g. a resource this clone lacks
        if not live.is_file():
            problems.append({"file": leaf, "why": "missing"})
            continue
        try:
            live_bytes = live.read_bytes()
            twin_bytes = twin.read_bytes()
        except OSError:
            problems.append({"file": leaf, "why": "unreadable"})
            continue
        if not _same_bytes(live_bytes, twin_bytes):
            problems.append({"file": leaf, "why": "differs"})
    return problems


# ---------------------------------------------------------------------------
#   The backups the patcher makes: restore them, never delete them
# ---------------------------------------------------------------------------

def backup_dirs(backend) -> list:
    """The patcher's `_jarvis-backup-*` folders, newest first.

    Both kinds are included: `_jarvis-backup-<stamp>` (the files a patch
    touches) and `_jarvis-backup-<stamp>-endings` (line-ending conversions).
    The script's own restore line copies from both, and this must match it.
    """
    backend = Path(backend)
    try:
        found = [entry for entry in backend.iterdir()
                 if entry.is_dir() and entry.name.startswith(BACKUP_PREFIX)]
    except OSError:
        return []
    # Newest first. The name breaks a tie: the patcher's stamp is the date and
    # time of the run, so a later stamp is a later run even when two folders
    # were made inside the same filesystem tick (which is what a test does).
    return sorted(found, key=lambda path: (path.stat().st_mtime, path.name),
                  reverse=True)


def newest_backup_set(backend) -> list:
    """The newest backup stamp's folders: the run's own restore set, or []."""
    dirs = backup_dirs(backend)
    if not dirs:
        return []
    for candidate in dirs:
        stamp = candidate.name[len(BACKUP_PREFIX):]
        if stamp.endswith("-endings"):
            continue
        return [entry for entry in dirs
                if entry.name in (BACKUP_PREFIX + stamp,
                                  BACKUP_PREFIX + stamp + "-endings")]
    return [dirs[0]]


def restore_backup(backend) -> dict:
    """Copy the newest backup set back over the backend folder.

    Every file is copied with its own relative path, exactly the shape the
    patcher's printed restore line uses. **The backup folders are never
    deleted** - an owner may still need them by hand, and a restore that
    destroys its own evidence is the second failure. Returns what it did so the
    card can say it in words.

    The BYTES are what is put back, not the backup's metadata: copying a
    read-only backup file's mode onto the live file would hand the safe pass a
    backend it cannot patch. For the same reason a live file the owner or
    Windows has made read-only is cleared for the copy (what the patcher's own
    `Copy-Item -Force` restore line does) - the clear happens on the LIVE file
    only; the backup that supplies the bytes is never altered."""
    backend = Path(backend)
    folders = newest_backup_set(backend)
    if not folders:
        return {"ok": False, "restored": 0, "folders": [],
                "why": "there is no _jarvis-backup-* folder to restore from"}
    restored = 0
    try:
        for folder in folders:
            for source in folder.rglob("*"):
                if not source.is_file():
                    continue
                target = backend / source.relative_to(folder)
                target.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copyfile(source, target)
                except PermissionError:
                    # A read-only live file (Windows attribute, or a POSIX
                    # owner chmod). Make the destination writable, then copy:
                    # the backup is only ever READ.
                    os.chmod(target, 0o666)
                    shutil.copyfile(source, target)
                restored += 1
    except OSError as exc:
        return {"ok": False, "restored": restored,
                "folders": [folder.name for folder in folders],
                "why": f"a file could not be put back: {exc}"}
    return {"ok": True, "restored": restored,
            "folders": [folder.name for folder in folders], "why": ""}


# ---------------------------------------------------------------------------
#   Reading the two programs' own lines
# ---------------------------------------------------------------------------

_SUITE_LINE = re.compile(r"^(ok|FAIL)\s+(\S+)\s+([0-9]+(?:\.[0-9]+)?)s\b")
_SUMMARY = re.compile(r"^(\d+) passed, (\d+) skipped, (\d+) failed$")
_ITEM = re.compile(r"^\s+(ok|FAIL|skip)\s+(\S+\.(?:patch|py))\b")


def parse_suite_line(line: str):
    """(name, seconds) for a finished suite's line, else None."""
    match = _SUITE_LINE.match(line)
    if not match:
        return None
    return match.group(2), float(match.group(3))


def parse_summary(line: str):
    """(passed, skipped, failed) from run_suites.py's final summary, else None."""
    match = _SUMMARY.match(line.strip())
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def patcher_result(exit_code, lines) -> dict:
    """What the patcher's own last lines say. Read, never guessed.

    Same three answers the desktop already reads off its output: did it
    finish, did it prove it, and did it warn that files were changed before it
    went wrong. `-SkipTests` alone can be a clean finish and can never be
    `proven`; the suites in step 3 are what prove this update.
    """
    text = "\n".join(lines)
    lower = text.lower()
    problems = ("DONE WITH PROBLEMS" in text
                or "patch(es) will not apply" in text)
    half_updated = ("half updated" in lower
                    or "were changed before this went wrong" in lower)
    return {
        "ok": exit_code == 0 and not problems,
        "problems": problems,
        "half_updated": half_updated,
        "touched_nothing": "nothing was changed" in lower
                           or "none of your backend files were changed" in lower,
        "lines": lines,
    }


def suite_result(exit_code, lines) -> dict:
    """What the suite run says, in counts. An unreadable answer is ambiguous.

    `ambiguous` is the honest third state the caller must treat as a failure:
    a run that printed no summary, or a worker that could not be watched, did
    not prove anything - the project's BLOCKED-is-never-a-pass rule.
    """
    failed_names = []
    for line in lines:
        match = re.match(r"^FAIL\s+(\S+)", line)
        if match is not None:
            failed_names.append(match.group(1))
    skipped_suites = []
    for line in lines:
        match = re.match(r"^skip\s+(\S+)", line)
        if match is not None:
            skipped_suites.append(match.group(1))
    summary = None
    for line in reversed(lines):
        got = parse_summary(line)
        if got is not None:
            summary = got
            break
    ambiguous = exit_code is None or summary is None
    failed = bool(failed_names) or (summary is not None and summary[2] > 0)
    unproven = bool(skipped_suites) or (summary is not None and summary[1] > 0)
    return {
        "ok": exit_code == 0 and not failed and not ambiguous,
        "failed": failed,
        "failed_names": failed_names,
        "skipped_suites": skipped_suites,
        "ambiguous": ambiguous,
        "unproven": unproven,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
#   Events - the one machine interface the desktop card reads
# ---------------------------------------------------------------------------

def emit_event(say, phase: str, **fields) -> dict:
    """Print one `JARVIS-EVENT {json}` line and return the payload.

    `None` fields are left out rather than serialised as null: the desktop's
    parser treats a missing field as "not said", and a null it has to special
    case is the kind of shape that grows a bug later.
    """
    payload = {"kind": KIND, "phase": phase}
    payload.update({key: value for key, value in fields.items() if value is not None})
    say(EVENT_PREFIX + json.dumps(payload, sort_keys=True))
    return payload


# ---------------------------------------------------------------------------
#   Running a child and reading it as it goes
# ---------------------------------------------------------------------------

def _run(cmd, cwd, on_line) -> "int | None":
    """Run one child, hand every line to `on_line`, return its exit code.

    stdout and stderr share one pipe, so the order the programs printed in is
    the order the card shows. `None` means the child could not be watched to
    its end - the caller treats that as ambiguous, never as a pass."""
    try:
        child = subprocess.Popen(
            [str(part) for part in cmd], cwd=str(cwd),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
        )
    except OSError as exc:
        on_line(f"the program could not be started: {exc}")
        return None
    try:
        if child.stdout is not None:
            for line in child.stdout:
                on_line(line.rstrip("\r\n"))
        return child.wait()
    except Exception as exc:               # noqa: BLE001 - never a crash
        try:
            child.kill()
        except OSError:
            pass
        on_line(f"the program could not be watched to its end: {exc}")
        return None


# ---------------------------------------------------------------------------
#   The update itself
# ---------------------------------------------------------------------------

class _PatchCounter:
    """Live count for the patcher's own phase, from its own lines.

    The shapes are the ones `update_progress.rs` already reads (`Rehearsing all
    N`, then one indented `ok`/`FAIL`/`skip` line per patch or module), so the
    tool and the Rust parser cannot disagree about what a line means.
    """

    def __init__(self):
        self.phase = "reading"
        self.total = None
        self.done = 0
        self.failed = 0

    def feed(self, line: str) -> None:
        trimmed = line.strip()
        if trimmed.startswith("Rehearsing all "):
            count = trimmed[len("Rehearsing all "):].split()
            if count and count[0].isdigit():
                self.phase = "rehearsing"
                self.total = int(count[0])
                self.done = 0
                self.failed = 0
        elif trimmed.startswith("Rehearsing again:") or trimmed.startswith("Taking off "):
            self.phase = "rehearsing"
            self.done = 0
            self.failed = 0
        elif trimmed.startswith("Applying "):
            self.phase = "applying"
            self.done = 0
            self.failed = 0
        match = _ITEM.match(line)
        if match is not None:
            kind, name = match.group(1), match.group(2)
            if name.endswith(".patch") or name.endswith(".py"):
                self.done += 1
                if kind == "FAIL":
                    self.failed += 1


def _fallback_words(restore: dict) -> str:
    """The card's own sentence: the exact promise the owner is shown.

    It names the NEW PASS, because the bar resets for it and a reset without
    a label would read as a backwards bar."""
    head = ("quick check hit a problem - re-running the safe way, new ETA. "
            "Second pass (safe mode) started.")
    if restore.get("ok"):
        where = restore["folders"][0] if restore["folders"] else "the backup"
        return (f"{head} Every file was put back from {where} first, so the safe "
                "pass starts from before the update.")
    return (f"{head} The backup could not be put back "
            f"({restore.get('why') or 'no backup'}), so read the log before "
            "trusting the result.")


def update(repo, backend, mode: str, *, requested_workers=None, timings_path=None,
           say=print, run=_run, clock=time.time, lock_file=None) -> int:
    """Run one backend update at `mode`'s pace; return 0 only when it proved it.

    The whole state machine is in `_update_locked`, so the fallback can be
    driven end to end with a fake runner: patch, verify, test; if a quick mode
    cannot prove itself, restore the newest backup and do the same three steps
    with one worker, and judge the update by that second pass.

    THE EXCLUSIVE LOCK is taken HERE, before a file is patched and before the
    suites start, and released on every way out (the `finally`); the suites this
    very update starts are told about it (`suites_command` passes
    `--ignore-update-lock`), everything else on the PC is not. A live lock held
    by another update is a refusal (`UpdateRefused("update_running", ...)`)
    naming its pid, pace and start time. `lock_file` overrides the path; when
    only `timings_path` is given (a caller naming its own state folder, which is
    how the tests keep the owner's `~/.openjarvis` untouched), the lock sits
    BESIDE that file rather than in the shared settings folder.

    Exit codes: 0 = no problems (proven or, with skips, unproven - the words
    say which), 1 = problems/ambiguous/failed. The desktop's `read_verdict`
    already distinguishes proven from unproven off the final words.
    """
    repo = Path(repo)
    backend = Path(backend)
    mode_spec(mode)                        # unknown mode: refused here, first
    requested_workers = workers_for(mode, requested_workers)
    preflight(repo, backend)
    if lock_file is not None:
        target = Path(lock_file)
    elif timings_path is not None:
        target = Path(timings_path).with_name(LOCK_NAME)
    else:
        target = lock_path()
    try:
        taken = acquire_lock(mode, path=target, now=clock())
    except UpdateRefused:
        raise
    except Exception as exc:               # noqa: BLE001 - a weird lock file must not
        # stop an update before it patches (S7): say plainly that it is NOT
        # protected, and let the patch/verify/check state machine run as before.
        taken = {"ok": False,
                 "why": f"the update lock could not be checked "
                        f"({type(exc).__name__}: {exc}), so this update is NOT "
                        "protected by it"}
    if taken.get("ok"):
        say(f"Update lock held: {target} (pid {taken['pid']}, pace {mode}). "
            "Other test runs will wait while this update is running.")
    else:
        say(f"NOTE  {taken.get('why') or 'the update lock is not held'}.")
    try:
        return _update_locked(repo, backend, mode,
                              requested_workers=requested_workers,
                              timings_path=timings_path, say=say, run=run,
                              clock=clock,
                              lock_file=target if taken.get("ok") else None)
    finally:
        if taken.get("ok"):
            released = release_lock(path=target)
            if not released:
                say("NOTE  the update lock could not be removed. A later run will "
                    "treat it as stale once this update's process is gone.")


def _update_locked(repo, backend, mode: str, *, requested_workers,
                   timings_path=None, say=print, run=_run, clock=time.time,
                   lock_file=None) -> int:
    """The update itself. The lock is already held by `update()`; `lock_file`
    is refreshed as suites finish (the heartbeat) and released by the caller."""
    repo = Path(repo)
    backend = Path(backend)
    spec = mode_spec(mode)                 # unknown mode: refused here, first
    names = suite_names(repo)
    path = Path(timings_path) if timings_path is not None else timings_path_for(backend)
    timings = pace_timings(load_timings(path), mode)
    plan = estimate(mode, names, timings, requested=requested_workers)
    first_patch, first_suite, first_share = plan_split(timings, names, requested_workers)
    emit_event(say, "reading", mode=mode, workers=requested_workers,
               suiteCount=len(names), measured=plan["measured"],
               fraction=0.0)
    emit_event(say, "plan", mode=mode, workers=requested_workers,
               etaSeconds=plan["eta_seconds"], etaLowSeconds=plan["eta_low_seconds"],
               etaHighSeconds=plan["eta_high_seconds"], measured=plan["measured"],
               suiteCount=len(names), patchSeconds=first_patch,
               suiteSeconds=first_suite, patchShare=round(first_share, 4),
               fraction=0.0)
    say(f"Update pace: {spec['label']} ({mode}), {requested_workers} suite(s) at a time.")
    if plan["measured"]:
        say(f"Estimated from the times recorded on this PC: about "
            f"{_minutes(plan['eta_low_seconds'])}-{_minutes(plan['eta_high_seconds'])}.")
    else:
        say(f"First run: no times recorded on this PC yet, so this is a guess "
            f"({_minutes(plan['eta_low_seconds'])}-{_minutes(plan['eta_high_seconds'])}), "
            "not a measurement. It will be measured and refined as the checks finish.")

    attempt_mode = mode
    attempt_number = 0
    fell_back = False
    while True:
        attempt_number += 1
        workers = workers_for(attempt_mode, requested_workers)
        attempt_timings = pace_timings(load_timings(path), attempt_mode)
        plan = estimate(attempt_mode, names, attempt_timings)
        patch_est, suite_est, this_share = plan_split(attempt_timings, names, workers)
        weights = suite_weights(names, attempt_timings)
        weight_total = sum(weights.values())
        weight_done = [0.0]
        pass_max = [0.0]
        pass_label = "second pass (safe mode)" if fell_back else None
        measured_now = plan["measured"]

        def emit_progress(phase: str, **fields) -> dict:
            """One progress event with the bar's real fraction clamped by the
            pass's own rule: never down, never at 100% before the final verdict.
            A new pass starts here with `pass_max` at zero and the label on."""
            fallback_flag = fields.pop("fallback", fell_back)
            raw = fields.pop("fraction", None)
            if raw is not None:
                cap = 1.0 if phase == "done" else 0.99
                pass_max[0] = max(pass_max[0], min(cap, float(raw)))
            fields["fraction"] = round(pass_max[0], 4)
            if pass_label is not None:
                fields["passLabel"] = pass_label
            return emit_event(say, phase, mode=attempt_mode, workers=workers,
                              fallback=fallback_flag, **fields)

        emit_progress("plan", etaSeconds=plan["eta_seconds"],
                      etaLowSeconds=plan["eta_low_seconds"],
                      etaHighSeconds=plan["eta_high_seconds"],
                      measured=measured_now, suiteCount=len(names),
                      patchSeconds=patch_est, suiteSeconds=suite_est,
                      patchShare=round(this_share, 4), fraction=0.0)

        # ---- 1. patch ----------------------------------------------------
        patch_start = clock()
        counter = _PatchCounter()
        patch_lines = []
        last_patch_event = [None]
        # S1: the patch phase can run for a long time before the first suite
        # finishes, so its own progress lines heartbeat the lock (bounded, not
        # one file write per printed line).
        last_heartbeat = [patch_start]

        def on_patch(line: str) -> None:
            patch_lines.append(line)
            say(line)
            counter.feed(line)
            if (lock_file is not None
                    and clock() - last_heartbeat[0] >= LOCK_PATCH_HEARTBEAT_SECONDS):
                refresh_lock(path=lock_file, now=clock())
                last_heartbeat[0] = clock()
            patch_estimate = (attempt_timings.get("patch_seconds")
                              or PLACEHOLDER_PATCH_SECONDS)
            remaining = None
            if counter.total:
                done = min(counter.done, counter.total)
                remaining = max(0.0, patch_estimate * (counter.total - done) / counter.total)
            key = (counter.phase, counter.done, counter.total, counter.failed)
            if key == last_patch_event[0]:
                return                     # nothing new to say
            last_patch_event[0] = key
            emit_progress(
                "patching", done=counter.done, total=counter.total,
                failed=counter.failed,
                etaSeconds=None if remaining is None else int(round(remaining)),
                measured=attempt_timings.get("patch_seconds") is not None,
                fraction=phase_fraction("patching", patch_share=this_share,
                                        patch_done=counter.done,
                                        patch_total=counter.total),
            )

        exit_code = _call(run, patcher_command(repo, backend), repo, on_patch)
        patch_seconds = max(0.0, clock() - patch_start)
        if lock_file is not None:
            # The patch phase can be minutes long; put a fresh heartbeat down
            # before the suite phase so a slow patch never looks abandoned.
            refresh_lock(path=lock_file, now=clock())
        verdict = patcher_result(exit_code, patch_lines)
        if not verdict["ok"]:
            came_back = None
            if verdict["half_updated"] or verdict["touched_nothing"]:
                came_back = restore_backup(backend)
                if came_back.get("ok"):
                    say(f"The patch program did not finish; {came_back['restored']} file(s) "
                        f"were put back from {came_back['folders'][0] if came_back['folders'] else 'the backup'}.")
            emit_progress("done", verdict="problems", fallback=fell_back,
                          note="the patch program did not finish; nothing is claimed as updated",
                          restored=bool(came_back and came_back.get("ok")),
                          fraction=None)
            say("")
            say("DONE WITH PROBLEMS - do not trust this update yet")
            return 1

        # ---- 2. verify the live files -----------------------------------
        emit_progress("verifying", measured=measured_now,
                      fraction=phase_fraction("verifying", patch_share=this_share))
        problems = verify_live_files(repo, backend)
        if problems and attempt_mode != "safe":
            fell_back = True
            pass_label = "second pass (safe mode)"
            restore = restore_backup(backend)
            pass_max[0] = 0.0             # a visible new pass may start at zero
            emit_progress("fallback", reason="live_file_mismatch",
                          note=_fallback_words(restore),
                          files=[p["file"] for p in problems[:8]],
                          fraction=0.0)
            say(_fallback_words(restore))
            attempt_mode = "safe"
            continue
        if problems:
            emit_progress("done", verdict="problems", fallback=fell_back,
                          note="the live backend files do not match this repository: "
                               + ", ".join(p["file"] for p in problems[:8]),
                          fraction=None)
            say("")
            say("DONE WITH PROBLEMS - do not trust this update yet")
            return 1

        # ---- 3. the same suites, at this pace ---------------------------
        emit_progress("testing", done=0, total=len(names), failed=0, skipped=0,
                      weightDone=0.0, weightTotal=round(weight_total, 3),
                      etaSeconds=plan["eta_seconds"],
                      measured=measured_now,
                      fraction=phase_fraction("testing", patch_share=this_share,
                                              weight_done=0.0,
                                              weight_total=weight_total))
        durations = {}
        suite_lines = []
        done_names = []

        def on_suite(line: str) -> None:
            suite_lines.append(line)
            say(line)
            got = parse_suite_line(line)
            if got is not None:
                name, seconds = got
                durations[name] = seconds
                done_names.append(name)
                if lock_file is not None:
                    # THE HEARTBEAT: every finished suite says this update is
                    # still alive, so a 2-hour safe run never expires its own
                    # lock at minute 31 (the design's one crucial refinement).
                    refresh_lock(path=lock_file, now=clock())
                weight_done[0] += weights.get(name, PLACEHOLDER_SUITE_SECONDS)
                eta = live_eta(attempt_mode, names, attempt_timings, done_names,
                               durations, requested=requested_workers)
                emit_progress(
                    "testing", done=eta["done"], total=len(names),
                    failed=_failed_count(suite_lines),
                    weightDone=round(weight_done[0], 3),
                    weightTotal=round(weight_total, 3),
                    etaSeconds=eta["eta_seconds"],
                    etaLowSeconds=eta["eta_low_seconds"],
                    etaHighSeconds=eta["eta_high_seconds"],
                    measured=eta["measured"],
                    fraction=phase_fraction("testing", patch_share=this_share,
                                            weight_done=weight_done[0],
                                            weight_total=weight_total))

        suites_exit = _call(run, suites_command(repo, workers), repo, on_suite)
        result = suite_result(suites_exit, suite_lines)
        if not result["ok"]:
            if attempt_mode != "safe":
                fell_back = True
                pass_label = "second pass (safe mode)"
                restore = restore_backup(backend)
                reason = ("worker_ambiguous" if result["ambiguous"]
                          else "suite_failed")
                pass_max[0] = 0.0     # the safe pass is a new, labelled pass
                emit_progress("fallback", reason=reason,
                              note=_fallback_words(restore),
                              failed=len(result["failed_names"]),
                              files=result["failed_names"][:8],
                              fraction=0.0)
                say(_fallback_words(restore))
                attempt_mode = "safe"
                continue
            save_timings(path, mode=attempt_mode, patch_seconds=patch_seconds, durations=durations)
            emit_progress("done", verdict="problems", fallback=fell_back,
                          failed=len(result["failed_names"]),
                          ambiguous=result["ambiguous"],
                          note="the safe pass did not prove this update either",
                          fraction=None)
            say("")
            say("DONE WITH PROBLEMS - do not trust this update yet")
            return 1

        # ---- it proved itself -------------------------------------------
        save_timings(path, mode=attempt_mode, patch_seconds=patch_seconds, durations=durations)
        unproven = result["unproven"]
        fallback_note = ("The quick check hit a problem, so it was re-run the safe "
                         "way; this result is that safe pass." if fell_back else None)
        emit_progress("done", verdict="unproven" if unproven else "ok",
                      fallback=fell_back, note=fallback_note,
                      measured=bool(durations), fraction=1.0)
        say("")
        if fell_back:
            say("The quick check hit a problem, so it was re-run the safe way, and "
                "this result is that safe pass.")
        if unproven:
            say("DONE - no problems, but NOT fully proven (see below)")
            if result["skipped_suites"]:
                say(f"  note: {len(result['skipped_suites'])} suite(s) need files that "
                    "live only on the owner's PC and were skipped: "
                    + ", ".join(result["skipped_suites"][:5]))
            say("  note: The checks were not all run to the end, so this update is "
                "applied but NOT proven.")
        else:
            say("ALL DONE - the backend is patched and proven")
        return 0


def _call(run, cmd, cwd, on_line):
    """Call the injected runner, turning its own crash into an ambiguous exit.

    A runner that raises is a worker crash; the caller treats an ambiguous
    result as a fallback trigger in a quick mode and as a failure in `safe`."""
    try:
        return run(cmd, cwd, on_line)
    except Exception as exc:               # noqa: BLE001 - never a crash
        on_line(f"the runner itself failed: {type(exc).__name__}: {exc}")
        return None


def _failed_count(lines) -> int:
    return sum(1 for line in lines if line.startswith("FAIL  "))


def _minutes(seconds: int) -> str:
    seconds = max(0, int(seconds))
    if seconds < 90:
        return f"{seconds} second(s)"
    return f"{max(1, int(round(seconds / 60.0)))} minute(s)"


# ---------------------------------------------------------------------------
#   The command line
# ---------------------------------------------------------------------------

def _usage() -> str:
    return ("usage: update_backend.py --repo <program folder> --backend <backend folder> "
            "[--mode max_speed|responsive|safe] [--workers N] [--modes-json] "
            "[--timings PATH]")


def parse_args(argv) -> dict:
    """A small hand-rolled parser: every refusal is a plain sentence.

    `argparse` would exit on its own with a usage line; this tool's refusals are
    read by the owner, so they are written like the rest of the card's words."""
    out = {"mode": DEFAULT_MODE, "workers": None, "modes_json": False,
           "repo": None, "backend": None, "timings": None}
    rest = list(argv)
    while rest:
        word = rest.pop(0)
        if word in ("--help", "-h"):
            print(_usage())
            raise SystemExit(0)
        if word == "--modes-json":
            out["modes_json"] = True
            continue
        if word in ("--repo", "--backend", "--mode", "--workers", "--timings"):
            if not rest:
                raise UpdateRefused("bad_argument", f"{word} needs a value after it.")
            value = rest.pop(0)
            key = word[2:].replace("-", "_")
            out[key] = value
            continue
        if word.startswith("--"):
            raise UpdateRefused("bad_argument", f"I do not know the option {word!r}.")
        raise UpdateRefused("bad_argument", f"I do not know what to do with {word!r}.")
    if not out["repo"]:
        raise UpdateRefused("bad_argument", "--repo is needed: the folder that holds "
                                           "scripts\\apply-patches.ps1.")
    if not out["backend"]:
        raise UpdateRefused("bad_argument", "--backend is needed: the folder that holds "
                                           "jarvis_hud.py.")
    if out["workers"] is not None:
        try:
            out["workers"] = int(out["workers"])
        except (TypeError, ValueError):
            raise UpdateRefused("bad_workers",
                                "--workers needs a whole number of suites to run at once.")
    return out


def card_shape(plan: dict) -> dict:
    """The choice card's JSON: the same numbers, camelCase for the desktop.

    One shape, one implementation: the Rust `ModeInfo` struct and the page read
    exactly these keys, and the fields are the plan's own (no second maths).
    """
    modes = []
    for row in plan["modes"]:
        modes.append({
            "id": row["id"],
            "label": row["label"],
            "plain": row["plain"],
            "workers": row["workers"],
            "etaSeconds": row["eta_seconds"],
            "etaLowSeconds": row["eta_low_seconds"],
            "etaHighSeconds": row["eta_high_seconds"],
            "measured": row["measured"],
            "recommended": row["recommended"],
            "suiteCount": row["suite_count"],
        })
    return {"kind": plan["kind"], "version": plan["version"], "modes": modes,
            "suiteCount": plan["suite_count"], "measured": plan["measured"],
            "default": plan["default"]}


def main(argv=None, *, say=print, run=_run) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    try:
        args = parse_args(argv)
        mode_spec(args["mode"])            # unknown mode refused before anything
        if args["modes_json"]:
            data = mode_plan(args["repo"], args["backend"],
                             timings_path=args["timings"],
                             requested=args["workers"])
            say(json.dumps(card_shape(data), indent=1, sort_keys=True))
            return 0
        return update(args["repo"], args["backend"], args["mode"],
                      requested_workers=args["workers"],
                      timings_path=args["timings"], say=say, run=run)
    except UpdateRefused as exc:
        print(f"REFUSED  {exc.message}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
