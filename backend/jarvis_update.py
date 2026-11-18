"""jarvis_update.py - the phone asks Jarvis to update itself; ONE card decides.

WHAT THE OWNER ASKED FOR (2026-11-18): the desktop program can already update
itself, but only at the PC, after Windows Hello there. The phone should be able
to ask for the SAME update, and answer its card with the phone's own
fingerprint.

    GET  /api/update/status     what is installed, what is published, and
                                whether an update is running - read-only
    POST /api/update/request    raise the ONE card and return; nothing else

THE ACTION IS THE ONE THAT ALREADY EXISTS. `desktop_update`
(`jarvis_quick.UPDATE_ACTION`) is the gate's name for "update Jarvis itself",
tier "ask" in both shipped settings copies and in `jarvis_asks_first.MUST_ASK`
and `.NEEDS_A_PERSON`. This module does not add a second name: it raises the
same card, under the same action, with the same written words
(`jarvis_card_words`: "update Jarvis, then restart it"). What changed is only
WHERE the card may be answered - `jarvis_owner_check.PC_ONLY_ACTIONS` no longer
holds it, exactly as the chatbot spending-limit card was taken out on
2026-10-11 for the owner's "let the phone raise it too, with its own
fingerprint". The two halves of the old rule both remain, and neither is
weakened:

  * ON THE PC it still asks Windows Hello, because `is_risky` sends every
    unclassified-and-outbound card there, and this one is outbound (it fetches
    the release) and cannot be undone (there is no rollback);
  * ON THE PHONE it needs that phone's own signed approval - a fresh fingerprint
    or PIN over a one-use challenge (`jarvis_devices.check_signed_approval`) -
    and a phone with no approval key is refused with "no_approval_key" so it can
    offer to turn signing on.

WHO RUNS THE UPDATE, AND WHY IT IS NOT A SECOND UPDATER. On the PC the answer
to the card is sent by the desktop shell's own `answer_approval`, and its
`run_approved_update` then runs `update_both` - that path is untouched. A
PHONE's approval never reaches that command, so the thing that runs after a
phone's yes is `scripts/update-jarvis.ps1`: the repository's own updater for
both halves, the same one the owner runs by hand, which installs the same
signed release and runs the same patcher. There is no third implementation, no
installer built here, and no argument the request can influence.

THE THREE THINGS THIS FILE WILL NEVER DO

  * It never approves anything. The card is raised through `jarvis_gate.check`
    at tier "ask", and the update starts only on a verdict that is a person
    saying yes: `allowed` True, `outcome` "approved", `tier` "ask". A loosened
    tier line is refused IN WORDS before a card exists, so a settings edit
    cannot turn this into "updates install themselves". Nothing in the module
    can approve in bulk or clear a rush latch - it raises one card, one time.
  * It never downloads or installs anything itself. It does not fetch an
    installer, does not run one, and does not patch anything: every one of those
    is the script's job, and its own header says what it checks first. Nothing
    is downloaded before the yes.
  * It never invents an argument. The child is built in `_updater_argv` from
    values this module resolved: `powershell -NoProfile -ExecutionPolicy Bypass
    -File <the one script> -BackendPath <the folder it found> -Force`. The
    request body has no field for a command, a path or a version, and it is
    read for nothing. `-Force` closes a running Jarvis rather than waiting for
    a person at the PC, which is what doing it from the phone means; no
    `-SkipTests`, no `-SkipDesktop`, no `-NoCheck` - the card promised both
    halves and a proven update.

THE DETACHED HELPER. The updater CLOSES the backend it is called from, so the
work has to outlive that process: `helper_main()` runs in its own detached
process (DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP on Windows), writes
`update-state.json` as it goes, and leaves a final `done` or `failed` there. The
status route reads that file back - after the restart it caused - so the phone
gets the real ending rather than a guess. Both children - the helper, and the
updater script the helper runs - get `child_env()`: an allowlist of the names
they actually read, never a copy of this process's environment, so the pairing
token cannot ride along into a process nothing watches.

ONE UPDATE AT A TIME, IN THREE PLACES. A second request refuses cleanly:

  * in this module - one card may be waiting at a time (`_PENDING`), and a
    state file still in flight with a LIVE pid is "running";
  * in the helper - `update-helper.lock` is created O_CREAT | O_EXCL, so two
    helpers cannot both run;
  * on the PC - the same `update-in-progress.lock` the desktop's own "update
    both halves" writes and reads. The helper TAKES it with the tool's own
    rules (a live pid, a heartbeat under 30 minutes, a start under 3 hours) and
    REFUSES to take a lock somebody else holds; a lock it does hold is refreshed
    every minute, so a long patch never looks stale. That one lock is what keeps
    a PC approval (the desktop runs its own updater) and a phone approval from
    patching the machine twice at the same moment. The helper also sets
    `JARVIS_INSIDE_PATCHER=1` for its child, which is how `backend/run_suites.py`
    knows the suite sweep belongs to the update that is running.

WHY A DROP-IN FOLDER, AND NOT A PATCH. `jarvis_hud.py` is delivered by the patch
stack, so a new route normally costs a patch - and a patch costs the ordering
bookkeeping every test that enumerates the stack keeps. `plugins/ready/update/`
carries this module's `plugin.json`, and the loader's one startup call runs
`install()` - the same route `plugins/ready/send-file` and its neighbours take.
The core file is untouched.

WHAT IS NOT HERE. The phone's own screen (Kotlin, `jarvis-client`) is a separate
piece of work; `docs/ARCHITECTURE.md` section 8 records that one-sidedness, in
its own words and for now. The backend half is complete: both routes, the card,
the phone's fingerprint approval, the runner and its locks.

Standard library only. Written to be read on a machine with no Jarvis install:
every path, every clock and every program call can be injected, which is what
`backend/test_phone_authorized_update.py` does - it never downloads, never
installs and never starts a PowerShell.
"""
from __future__ import annotations

import collections
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlsplit

# --------------------------------------------------------------------------
#   The names, and the one action
# --------------------------------------------------------------------------

#: The gate's action for "update Jarvis itself". REUSED, never re-spelled: this
#: is `jarvis_quick.UPDATE_ACTION`, `jarvis_card_words`' own card, the
#: framework's `desktop_update = "ask"` line, `jarvis_asks_first.MUST_ASK` /
#: `.NEEDS_A_PERSON`, and the desktop's `is_update_card`. A second name for this
#: ability was the old attempt's first fault; the test holds the two equal.
ACTION = "desktop_update"

#: The two routes. Neither takes a path, a version or a command.
STATUS_PATH = "/api/update/status"
REQUEST_PATH = "/api/update/request"

#: The backend folder is the folder holding this file's neighbour, exactly as
#: `scripts/install-backend.ps1` and the updater's own `-BackendPath` decide it.
BACKEND_MARKER = "jarvis_hud.py"
BACKEND_MARKER_ENV = "JARVIS_BACKEND"

#: The one program this module is allowed to run, relative to the repository.
SCRIPT_REL = ("scripts", "update-jarvis.ps1")
SCRIPT_NAME = "update-jarvis.ps1"
REPO_ENV = "JARVIS_REPO"

#: The folder Jarvis keeps its own data in, and the three files this module
#: keeps there. `update-in-progress.lock` is NOT ours: `tools/update_backend.py`
#: and the desktop's `backend_update.rs` write the same one, which is the point.
STATE_NAME = "update-state.json"
HELPER_LOCK_NAME = "update-helper.lock"
SHARED_LOCK_NAME = "update-in-progress.lock"

#: `backend/run_suites.py` reads this to know the suite sweep belongs to the
#: update that is running, rather than to a person running tests beside a lock.
PATCHER_ENV = "JARVIS_INSIDE_PATCHER"

#: The phases, in the order the updater reaches them - the script's own step
#: titles, mapped. `starting` covers its first two steps (finding the backend
#: folder, getting the newest code) so a phone is never told "closing" while
#: nothing is closing. Any of these means "an update is in flight"; `done` and
#: `failed` are the two endings.
PHASES = ("starting", "closing", "patching", "installing", "restarting", "checking")
DONE = "done"
FAILED = "failed"
IDLE = "idle"

#: One plain sentence per phase, for the phone to show as-is. No jargon: "the
#: new build" is the desktop app, and every line says what the PC is doing.
PHASE_WORDS = {
    IDLE: "Nothing is updating.",
    "starting": "Jarvis on the PC is getting the update ready.",
    "closing": "Jarvis on the PC is closing so the update can be applied.",
    "patching": "The backend on the PC is being patched.",
    "installing": "The new build of Jarvis is being installed on the PC.",
    "restarting": "Jarvis is starting again on the PC.",
    "checking": "Jarvis is checking itself after the update.",
    DONE: "The update finished - the script's own last line is below.",
    FAILED: "The update did not finish - the reason is below.",
}

#: The updater's own step titles -> this module's phases. Verified against
#: `scripts/update-jarvis.ps1` by `test_phone_authorized_update.py`, which reads
#: the script and fails if a title it maps is no longer there - so a renamed
#: step cannot leave the phone stuck on a phase nobody updates.
_STEP_MARKERS = (
    ("finding the backend folder", "starting"),
    ("getting the newest code", "starting"),
    ("closing jarvis", "closing"),
    ("patching the backend", "patching"),
    ("updating the desktop app", "installing"),
    ("starting jarvis and checking it", "restarting"),
    ("running the live check", "checking"),
)

#: The shared lock's numbers, word for word with `tools/update_backend.py` and
#: the desktop's `backend_update.rs`: valid while the pid is really running and
#: the heartbeat is under 30 minutes old; stale when the start is over 3 hours
#: old (a pid-reuse guard only - a live writer renews `started_at`); a clock
#: that moved gives a non-finite or future timestamp, which is stale.
LOCK_HEARTBEAT_SECONDS = 1800.0
LOCK_CEILING_SECONDS = 10_800.0
LOCK_CLOCK_SKEW_SECONDS = 60.0
LOCK_MAX_BYTES = 64 * 1024

#: A helper in flight this long without finishing is not trusted to be a live
#: update any more. Its pid is the authority; this is the guard for a pid that
#: was reused by something else.
HELPER_CEILING_SECONDS = 10_800.0

#: How much of the script's own output a failure keeps for the phone.
TAIL_LINES = 12
TAIL_CHARS = 2000

#: How often the helper renews its heartbeat (and the lock's).
_HEARTBEAT_SECONDS = 60.0

_PENDING_LOCK = threading.Lock()
_STATE_LOCK = threading.Lock()

#: The one card waiting, if any: {"id", "from", "to", "script", "backend",
#: "since", "since_m", "timeout"}. Memory only - a card dies with the process
#: that is waiting for it, which is the gate's own behaviour.
_PENDING: Optional[dict] = None
#: The last card's outcome, so a status read after a restart still says how the
#: last ask went. Memory only, and never a licence for anything.
_LAST: Optional[dict] = None


# --------------------------------------------------------------------------
#   Where things live
# --------------------------------------------------------------------------

def config_dir() -> Path:
    """The folder Jarvis keeps its own data in.

    The same order every other part of this PC uses: `OPENJARVIS_CONFIG_DIR`,
    then `JARVIS_CONFIG_DIR`, then `jarvis_framework.CONFIG_DIR`, then
    `~/.openjarvis`. Read fresh on every call, so a test can move it and so a
    helper started with the variable set agrees with the server that started it.
    """
    env = os.environ.get("OPENJARVIS_CONFIG_DIR") or os.environ.get("JARVIS_CONFIG_DIR")
    if env:
        return Path(os.path.expanduser(env))
    try:
        import jarvis_framework as FW
        folder = getattr(FW, "CONFIG_DIR", None)
        if folder:
            return Path(folder)
    except Exception:                                   # noqa: BLE001
        pass
    return Path(os.path.expanduser("~")) / ".openjarvis"


def state_path() -> Path:
    """Where the helper writes progress and `status()` reads it back."""
    return config_dir() / STATE_NAME


def helper_lock_path() -> Path:
    """The helper's own lock - one helper at a time."""
    return config_dir() / HELPER_LOCK_NAME


def shared_lock_path() -> Path:
    """The PC's one update lock, shared with the desktop's own updater."""
    return config_dir() / SHARED_LOCK_NAME


def _env_path(name: str) -> Optional[Path]:
    raw = os.environ.get(name)
    if not raw or not str(raw).strip():
        return None
    try:
        return Path(os.path.expanduser(str(raw).strip()))
    except Exception:                                   # noqa: BLE001
        return None


def backend_folder() -> Optional[Path]:
    """The folder holding `jarvis_hud.py`, or None when this run cannot tell.

    `JARVIS_BACKEND` when it names a real backend folder - `scripts/
    install-backend.ps1` is the documented way that gets set, and the updater's
    own `-BackendPath` default reads the same one. Otherwise this module's own
    folder, which on the owner's PC IS the backend folder. This repository's
    `backend/` (where there is no `jarvis_hud.py`) is therefore honestly "not
    found" rather than mistaken for a backend.
    """
    for candidate in (_env_path(BACKEND_MARKER_ENV), Path(__file__).resolve().parent):
        if candidate is not None and (candidate / BACKEND_MARKER).is_file():
            return candidate
    return None


def _desktop_settings_repo() -> Optional[Path]:
    """`updates.repo_folder` from the desktop app's own store, or None.

    The Tauri app keeps its settings in `%APPDATA%\\com.jarvis.desktop\\`
    (`tauri.conf.json`'s identifier) under `jarvis-desktop.json`, and the
    repository box on Settings -> Updates writes this key. Read-only, and the
    SAME value that button uses, so the two paths cannot disagree about where
    the repository is. Never raises: a missing file, a file that is not JSON, or
    a value that is not a string is simply "no answer from there".
    """
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    path = Path(appdata) / "com.jarvis.desktop" / "jarvis-desktop.json"
    try:
        if not path.is_file() or path.stat().st_size > 4 * 1024 * 1024:
            return None
        doc = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:                                   # noqa: BLE001
        return None
    if not isinstance(doc, dict):
        return None
    updates = doc.get("updates")
    value = updates.get("repo_folder") if isinstance(updates, dict) \
        else doc.get("updates.repo_folder")
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return Path(os.path.expanduser(value.strip()))
    except Exception:                                   # noqa: BLE001
        return None


def repo_folder() -> Optional[Path]:
    """The folder this repository is cloned into, or None when it cannot tell.

    Three sources, most explicit first, and NO disk search - the same doctrine
    as the desktop's own `backend_update.rs`, which refuses rather than guessing
    at a path an update depends on:

      1. `JARVIS_REPO`, for a terminal or a script that says it outright;
      2. the repository box on the desktop's Settings -> Updates page;
      3. this module's parent folder, which is the repository in a checkout.

    A candidate only counts when it really holds `scripts/update-jarvis.ps1`.
    """
    for candidate in (_env_path(REPO_ENV), _desktop_settings_repo(),
                      Path(__file__).resolve().parent.parent):
        if candidate is not None and candidate.joinpath(*SCRIPT_REL).is_file():
            return candidate
    return None


def script_path() -> Optional[Path]:
    """The one updater this module is allowed to run, or None."""
    repo = repo_folder()
    return repo.joinpath(*SCRIPT_REL) if repo is not None else None


# --------------------------------------------------------------------------
#   The two versions (what is here, what is published)
# --------------------------------------------------------------------------

def _version_parts(version) -> Optional[tuple]:
    """(0, 2, 456) for "0.2.456"; None for anything that is not a version.

    The release stamps `major.minor.<run number>` (`desktop-release.yml`), so
    numbers are compared as numbers: "0.2.99" is older than "0.2.100", which a
    string comparison gets backwards.
    """
    import re
    text = str(version or "").strip().lstrip("vV")
    if not re.fullmatch(r"\d{1,9}(?:\.\d{1,9}){0,3}", text):
        return None
    parts = [int(p) for p in text.split(".")]
    while len(parts) < 4:
        parts.append(0)
    return tuple(parts)


def _registry_versions() -> list:
    """Every Jarvis Desktop version Windows' uninstall list records, newest first.

    It is the same list the updater's own `Get-InstalledDesktop` reads, and it
    has to be a LIST because an old install leaves its row behind: this PC has
    carried several at once, and the newest is the one running. Non-Windows, or
    a registry that cannot be read, answers [] - never a guess.
    """
    if os.name != "nt":
        return []
    import winreg
    found = []
    roots = (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE)
    for root in roots:
        try:
            base = winreg.OpenKey(
                root,
                r"Software\Microsoft\Windows\CurrentVersion\Uninstall")
        except OSError:
            continue
        try:
            index = 0
            while True:
                try:
                    name = winreg.EnumKey(base, index)
                except OSError:
                    break
                index += 1
                try:
                    row = winreg.OpenKey(base, name)
                except OSError:
                    continue
                try:
                    try:
                        display = str(winreg.QueryValueEx(row, "DisplayName")[0] or "")
                    except OSError:
                        continue
                    if "jarvis" not in display.lower():
                        continue
                    try:
                        version, _ = winreg.QueryValueEx(row, "DisplayVersion")
                    except OSError:
                        continue
                    text = str(version or "").strip()
                    if _version_parts(text) is not None:
                        found.append(text)
                finally:
                    try:
                        row.Close()
                    except Exception:                   # noqa: BLE001
                        pass
        finally:
            try:
                base.Close()
            except Exception:                           # noqa: BLE001
                pass
    found.sort(key=lambda v: _version_parts(v) or (0, 0, 0, 0), reverse=True)
    return found


def installed() -> dict:
    """{"version": str|None, "why": str} - the Jarvis Desktop app on this PC.

    `why` is "" or a plain "cannot tell: ..." sentence. No network, nothing
    written, nothing started.
    """
    versions = _registry_versions()
    if versions:
        return {"version": versions[0], "why": ""}
    return {"version": None,
            "why": ("cannot tell: no installed Jarvis Desktop version is recorded "
                    "on this PC")}


def published() -> dict:
    """{"version": str|None, "why": str} - the newest published release.

    One public read, and it is `jarvis_quick`'s own manifest read, reused so the
    phone and the desktop's Settings card can never disagree about which
    release is newest. A missing or older `jarvis_quick.py` is "cannot tell",
    never a made-up number.
    """
    try:
        import jarvis_quick
        read = getattr(jarvis_quick, "_release_manifest", None)
        if not callable(read):
            raise AttributeError("this PC's jarvis_quick.py has no release read")
        manifest, why = read()
    except Exception as exc:                            # noqa: BLE001
        return {"version": None,
                "why": (f"cannot tell: the release list could not be read "
                        f"({type(exc).__name__})")}
    if not manifest:
        return {"version": None,
                "why": (f"cannot tell: the release list could not be read "
                        f"({why or 'no reason given'})")}
    if not isinstance(manifest, dict):
        return {"version": None,
                "why": ("cannot tell: the release list was not in the expected "
                        "shape")}
    version = str(manifest.get("version") or "").strip()
    if _version_parts(version) is None:
        return {"version": None,
                "why": ("cannot tell: the release list named no version this PC "
                        "understands")}
    return {"version": version, "why": ""}


def compare(installed_version, published_version) -> Optional[bool]:
    """True when the published version is newer; None when either is unreadable."""
    here, there = _version_parts(installed_version), _version_parts(published_version)
    if here is None or there is None:
        return None
    return there > here


# --------------------------------------------------------------------------
#   The state file - progress that survives the restart the update causes
# --------------------------------------------------------------------------

def _read_json(path: Path) -> dict:
    """One small JSON object from `path`, or {} - never raises, never huge."""
    try:
        if not path.is_file():
            return {}
        if path.stat().st_size > LOCK_MAX_BYTES:
            return {}
        doc = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:                                   # noqa: BLE001
        return {}
    return doc if isinstance(doc, dict) else {}


def _write_json(path: Path, doc: dict) -> None:
    """Write `doc` beside `path` and rename it over: a reader never sees half a
    file. Best effort - a state file that cannot be written must not take the
    update down; the phase is still reported from the file's last good version."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(doc, indent=1), encoding="utf-8")
        tmp.replace(path)
    except Exception:                                   # noqa: BLE001
        pass


def _delete(path: Path) -> None:
    try:
        path.unlink()
    except (FileNotFoundError, OSError):
        pass


def _write_state(phase: str, **fields) -> dict:
    """Record ONE phase, keeping the fields every reader expects."""
    now = time.time()
    doc = {"phase": phase, "pid": fields.pop("pid", None),
           "started_at": fields.pop("started_at", now),
           "updated_at": now, "finished_at": fields.pop("finished_at", None),
           "from": fields.pop("from_version", None),
           "to": fields.pop("to_version", None),
           "pace": "phone"}
    doc.update(fields)
    with _STATE_LOCK:
        _write_json(state_path(), doc)
    return doc


def read_state() -> dict:
    """The last progress the helper wrote, or {} when it has never run."""
    return _read_json(state_path())


def _pid_alive(pid) -> bool:
    """Is this a running process on this machine? Never ends one.

    WINDOWS IS ASKED THE WINDOWS WAY, and that is not a detail: on Windows
    `os.kill(pid, 0)` is not an existence probe - any signal but the two
    console events ends the process - so the obvious probe would kill the very
    update it is checking (`tools/update_backend.py` says the same in its own
    words, and its OpenProcess/GetExitCodeProcess pair is the one copied here).
    POSIX uses `kill(pid, 0)`, the documented existence probe.
    """
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
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
            # PROCESS_QUERY_LIMITED_INFORMATION is enough to ask about the
            # process; a pid that has ended gives no handle.
            handle = kernel32.OpenProcess(0x1000, False, int(pid))
            if not handle:
                # Access denied means it EXISTS and belongs to someone else.
                return kernel32.GetLastError() == 5      # ERROR_ACCESS_DENIED
            try:
                code = wintypes.DWORD()
                if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                    return True     # it exists; its exit code just cannot be read
                return code.value == 259                     # STILL_ACTIVE
            finally:
                kernel32.CloseHandle(handle)
        except Exception:                               # noqa: BLE001
            return False
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True
    except (OSError, ValueError, OverflowError):
        return False
    return True


def running(state: Optional[dict] = None) -> bool:
    """Is an update in flight right now?

    The phase must be one of `PHASES` AND its pid must be alive: a helper that
    was killed is not an update, and its state must not block the next request.
    A state file with no pid is not trusted as a live update either.
    """
    st = read_state() if state is None else state
    return str(st.get("phase") or "") in PHASES and _pid_alive(st.get("pid"))


def stale(state: Optional[dict] = None) -> bool:
    """The state says in flight but its writer is gone - the update DIED.

    Reported as a failure, never left looking like progress: a phone that
    waited on a dead pid would wait forever.
    """
    st = read_state() if state is None else state
    return str(st.get("phase") or "") in PHASES and not _pid_alive(st.get("pid"))


# --------------------------------------------------------------------------
#   The PC's own update lock - so the two roads cannot patch it at once
# --------------------------------------------------------------------------

def _number(value) -> Optional[float]:
    """`value` as a finite float, or None. A clock that moved is not a number."""
    import math
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def held_lock(now: Optional[float] = None) -> Optional[dict]:
    """The lock somebody is holding right now, or None.

    The rules are `tools/update_backend.py`'s, word for word: a live pid, a
    heartbeat under 30 minutes old, a start under 3 hours old, and no timestamp
    that is non-finite or in the future. A lock written by a dead process, or
    one whose clock cannot be read, is STALE - it never blocks an update for
    ever, and a stale lock is not trusted as "an update is running".
    """
    doc = _read_json(shared_lock_path())
    if not doc:
        return None
    at = time.time() if now is None else float(now)
    pid = doc.get("pid")
    started = _number(doc.get("started_at"))
    updated = _number(doc.get("updated_at"))
    if not _pid_alive(pid):
        return None
    if started is None or updated is None:
        return None
    if started > at + LOCK_CLOCK_SKEW_SECONDS or updated > at + LOCK_CLOCK_SKEW_SECONDS:
        return None
    if at - updated > LOCK_HEARTBEAT_SECONDS:
        return None
    if at - started > LOCK_CEILING_SECONDS:
        return None
    return doc


def _words_ago(seconds: float) -> str:
    """'4 minutes ago' - a number a person can read, not 241.7 seconds."""
    seconds = max(0.0, float(seconds))
    if seconds < 90:
        return "just now"
    minutes = int(round(seconds / 60.0))
    if minutes < 90:
        return f"about {minutes} minute{'s' if minutes != 1 else ''} ago"
    hours = int(round(minutes / 60.0))
    return f"about {hours} hour{'s' if hours != 1 else ''} ago"


def desktop_lock_words(now: Optional[float] = None) -> str:
    """The plain refusal when the PC's own update lock is held, else ""."""
    lock = held_lock(now)
    if not lock:
        return ""
    at = time.time() if now is None else float(now)
    started = _number(lock.get("started_at")) or at
    pace = lock.get("pace") if isinstance(lock.get("pace"), str) else "an update"
    return (f"the PC is already updating Jarvis ({pace}), started "
            f"{_words_ago(at - started)}; wait for that one to finish")


def take_shared_lock(pid: int, now: Optional[float] = None) -> bool:
    """Hold the PC's update lock for `pid`; False when somebody else holds it.

    REFUSES TO TAKE A LIVE LOCK, which is the whole point of it being shared:
    the desktop's "update both halves" takes the same file, and an update that
    overwrote a live lock would be the second patcher running at once. A lock
    whose writer is gone IS replaced - a killed update must not block every
    later one.
    """
    if held_lock(now) is not None:
        return False
    at = time.time() if now is None else float(now)
    with _STATE_LOCK:
        _write_json(shared_lock_path(), {"pid": int(pid), "started_at": at,
                                         "updated_at": at, "pace": "phone"})
    return True


def release_shared_lock(pid: int) -> None:
    """Remove the shared lock, but only when it is OUR pid's."""
    doc = _read_json(shared_lock_path())
    if doc.get("pid") == pid:
        _delete(shared_lock_path())


def refresh_shared_lock(pid: int) -> None:
    """Renew OUR lock's heartbeat. Never touches anyone else's."""
    doc = _read_json(shared_lock_path())
    if doc.get("pid") != pid:
        return
    now = time.time()
    doc["updated_at"] = now
    # A live writer renews the start too, so the ceiling is a pid-reuse guard
    # and never ends a legitimate long run (`tools/update_backend.py`).
    doc["started_at"] = now
    with _STATE_LOCK:
        _write_json(shared_lock_path(), doc)


# --------------------------------------------------------------------------
#   The card's words
# --------------------------------------------------------------------------

#: What the card says the action is, in four words, beside the gate's own title
#: ("update Jarvis, then restart it") and summary ("update Jarvis itself - the
#: backend first, then this app", both in `jarvis_card_words`).
CARD_WHAT = ("update Jarvis on this PC from the phone: the backend first, then the "
             "desktop app, then a restart")


def describe(installed_version: str, target_version: str) -> str:
    """The card's words. Five facts, in plain words, and both directions said.

    What it moves to; that Jarvis on the PC closes while the update is applied
    and then starts again; that this phone's link drops and comes back by
    itself; that the installer's signature is checked and the backend's own
    changes are rehearsed and tested first; and that nothing else on the PC
    changes. `docs/ARCHITECTURE.md` section 3 asks what refusing costs to be on
    every card, so "if you say no" is the last line.

    ONE PLACE, because the phone, the Windows Hello prompt and the PC's own
    notification all read this string - `test_phone_authorized_update.py`
    asserts it word for word, so it cannot drift into jargon.
    """
    here = str(installed_version or "").strip()
    move = f"from {here} to {target_version}" if here else f"to {target_version}"
    return (
        f"Update Jarvis on the PC {move}?\n\n"
        "If you say yes: Jarvis on the PC closes while the update is applied - a "
        "few minutes, because every change is tried on a throwaway copy first "
        "and the tests run - and then starts again on the new version. This "
        "phone's link drops while that happens and comes back by itself; you do "
        "not need to pair again.\n\n"
        "The desktop app's installer is checked against Jarvis's own signing key "
        "before it is run, and the backend folder is changed only by this "
        "repository's own update script, which keeps a backup and refuses to "
        "leave it half done.\n\n"
        "Nothing else on the PC changes: no other program is installed, and none "
        "of your documents, mail, notes, photos or saved memory is touched. Only "
        "Jarvis's own files and its logs are written.\n\n"
        "If you say no: nothing changes, and nothing is downloaded."
    )


def _tier_of(action: str) -> str:
    """The tier "What asks first" has for the card, read before it is raised.

    An unreadable framework answers "ask" - the same default
    `jarvis_quick._update_tier` uses, and the safe direction: it never turns a
    card into an automatic action.
    """
    try:
        import jarvis_framework as FW
        return str(FW.action_tier(action))
    except Exception:                                   # noqa: BLE001
        return "ask"


def _gate(action: str, detail: dict, prompt: str):
    """`jarvis_gate.check` - the one gate every card goes through."""
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def _timeout() -> float:
    """How long the card waits, from the owner's own settings."""
    try:
        import jarvis_framework as FW
        return float(FW.load_framework().get("autonomy", {})
                     .get("approval_timeout_seconds", 900))
    except Exception:                                   # noqa: BLE001
        return 900.0


def _left_s(p: dict) -> float:
    """Seconds left of the waiting card, by the MONOTONIC clock (a clock that is
    set while a card waits must not shorten or stretch it)."""
    mark = p.get("since_m")
    if isinstance(mark, (int, float)) and not isinstance(mark, bool):
        return p["timeout"] - (time.monotonic() - mark)
    return p["since"] + p["timeout"] - time.time()


def _spawn(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="jarvis-update-card", daemon=True).start()


# --------------------------------------------------------------------------
#   The one place a refusal is decided - request() and status() both read it
# --------------------------------------------------------------------------

def _refusal(code: int, error: str, **extra) -> tuple:
    out = {"ok": False, "error": error}
    out.update(extra)
    return code, out


def obstacle(*, installed_now=None, published_now=None, tier_of=None,
             backend=None, script=None, state=None, now=None,
             pending: Optional[dict] = None) -> Optional[tuple]:
    """(http_status, payload) for the FIRST reason a card cannot be raised.

    ONE function, so `request()`'s refusal and `status()`'s `why_not` are the
    same sentence and the same order - a greying-out button that names a
    different reason from the tap is how a phone learns not to trust either.

    Nothing here writes, starts or downloads; everything it needs is injectable
    so a test can walk every arm without a release, a lock or a script.
    """
    backend = backend or backend_folder
    script = script or script_path
    installed_now = installed_now or installed
    published_now = published_now or published
    tier_of = tier_of or _tier_of
    state = read_state() if state is None else state
    if pending is None:
        with _PENDING_LOCK:
            pending = _PENDING

    if pending is not None:
        return _refusal(409,
                        "an update request is already waiting for approval - "
                        "approve or deny that card first",
                        pending=True, expires_in=max(0, int(_left_s(pending))))
    if running(state):
        phase = str(state.get("phase") or "")
        return _refusal(409, "an update is already running on the PC",
                        phase=phase, what=PHASE_WORDS.get(phase, ""))
    busy = desktop_lock_words(now)
    if busy:
        return _refusal(409, f"an update is already running: {busy}")
    if backend() is None:
        return _refusal(409, "I cannot find the Jarvis backend folder on this PC",
                        reason=("the folder Jarvis runs from was not found. Run the "
                                "installer's backend step once - it tells Jarvis where "
                                "that folder is - then ask again"))
    if script() is None:
        return _refusal(409,
                        "I cannot find the folder this repository is cloned into",
                        reason=("the updater was not found in this repository. Fill in "
                                "the repository folder on the desktop app's Settings -> "
                                "Updates page, then ask again"))
    here = installed_now()
    there = published_now()
    here_version = here.get("version") if isinstance(here, dict) else None
    there_version = there.get("version") if isinstance(there, dict) else None
    newer = compare(here_version, there_version)
    if newer is None:
        why = ((here.get("why") if isinstance(here, dict) else "")
               or (there.get("why") if isinstance(there, dict) else "")
               or "the two versions could not be compared")
        return _refusal(409, "I cannot tell whether there is a newer version",
                        installed=here_version, published=there_version, reason=why)
    if not newer:
        return _refusal(409, "there is nothing newer to install",
                        installed=here_version, published=there_version,
                        reason=(f"this PC is on {here_version}, and the newest "
                                f"published is {there_version}"))
    try:
        tier = tier_of(ACTION)
    except Exception as exc:                            # noqa: BLE001
        tier = f"unreadable ({type(exc).__name__})"
    if tier != "ask":
        # Before a card exists: a card that could not end in a person deciding
        # must not be raised at all.
        return _refusal(409,
                        f"{ACTION} is tier {tier!r} in jarvis-framework.toml; "
                        "updating Jarvis needs a person to say yes, so it must be "
                        "'ask'",
                        pending=False)
    return None


# --------------------------------------------------------------------------
#   POST /api/update/request - ONE card, and nothing before the yes
# --------------------------------------------------------------------------

def request(body=None, *, gate: Optional[Callable] = None,
            tier_of: Optional[Callable[[str], str]] = None,
            spawn: Optional[Callable] = None,
            backend: Optional[Callable[[], Optional[Path]]] = None,
            script: Optional[Callable[[], Optional[Path]]] = None,
            installed_now: Optional[Callable[[], dict]] = None,
            published_now: Optional[Callable[[], dict]] = None,
            spawn_helper: Optional[Callable[[dict], None]] = None,
            state: Optional[dict] = None) -> tuple:
    """POST /api/update/request. Returns (http_status, payload).

    Refuses, in words, when there is nothing newer, when an update is already
    waiting or running, when the backend folder or the updater cannot be found,
    or when the action's tier is not "ask". Otherwise raises exactly ONE card on
    a background thread and returns at once; the update itself starts only if
    that card is approved.

    `body` is read for NOTHING: the route takes no argument that could change
    what runs. It is accepted so the route's own call is uniform with its
    neighbours, and so a future version can report what it ignored without a new
    signature.
    """
    global _PENDING
    gate = gate or _gate
    tier_of = tier_of or _tier_of
    spawn = spawn or _spawn
    backend = backend or backend_folder
    script = script or script_path
    installed_now = installed_now or installed
    published_now = published_now or published
    state = read_state() if state is None else state

    # Read the two versions ONCE and let `obstacle` read the same answers: a
    # second manifest read inside one request is a second round trip for a
    # number that cannot have changed in between.
    here, there = installed_now(), published_now()
    refused = obstacle(installed_now=lambda: here, published_now=lambda: there,
                       tier_of=tier_of, backend=backend, script=script,
                       state=state)
    if refused is not None:
        return refused

    here_version = here.get("version") if isinstance(here, dict) else None
    there_version = there.get("version") if isinstance(there, dict) else None
    pid = uuid.uuid4().hex
    with _PENDING_LOCK:
        if _PENDING is not None:                        # lost a race with another ask
            return _refusal(409,
                            "an update request is already waiting for approval - "
                            "approve or deny that card first", pending=True)
        _PENDING = {"id": pid, "from": here_version, "to": there_version,
                    "script": str(script()), "backend": str(backend()),
                    "since": time.time(), "since_m": time.monotonic(),
                    "timeout": _timeout()}

    def work():
        try:
            _decide(pid, gate=gate, spawn_helper=spawn_helper)
        except Exception:                               # noqa: BLE001
            _finish_request(pid, "failed", reason="an unexpected error")

    try:
        spawn(work)
    except Exception as exc:                            # noqa: BLE001
        _finish_request(pid, "failed",
                        reason=f"could not raise the card ({type(exc).__name__})")
        return _refusal(500, "could not raise the approval card")

    return 202, {
        "ok": True, "pending": True, "action": ACTION,
        "installed": here_version, "published": there_version, "to": there_version,
        "message": ("One card is waiting for your yes. It can be approved on this "
                    "PC with Windows Hello, or on your phone with its fingerprint "
                    "or PIN. Nothing is downloaded or changed until then."),
    }


def _decide(pid: str, *, gate: Callable, spawn_helper: Optional[Callable]) -> None:
    """Raise the card for staged request `pid`, wait, and act on the answer.

    Blocks - it runs on the thread `request()` started. Nothing starts unless a
    person said yes on THIS card, at tier "ask".
    """
    with _PENDING_LOCK:
        p = _PENDING if (_PENDING and _PENDING["id"] == pid) else None
        if p is None:
            return
        here, there = p.get("from"), p.get("to")
        script, backend = p.get("script"), p.get("backend")
    text = describe(here, there)
    detail = {"text": text, "from": here, "to": there, "what": CARD_WHAT,
              # The update fetches the signed release from GitHub, so this card
              # does leave this PC - the same public read the app's own check
              # already makes.
              "leaves_this_pc": True,
              # No path and no argument here: the child's command line is built
              # in `_start_helper` from the staged request, so nothing a card
              # shows can become something that runs.
              "raised_by": "phone"}
    try:
        verdict = gate(ACTION, detail, text)
    except Exception as exc:                            # noqa: BLE001
        _finish_request(pid, "refused",
                        reason=f"the approval gate failed ({type(exc).__name__})")
        return
    vtier = getattr(verdict, "tier", "unknown")
    allowed = getattr(verdict, "allowed", False) is True
    outcome = getattr(verdict, "outcome", None)
    if outcome is None:
        outcome = "approved" if (allowed and vtier == "ask") else "refused"
    rid = getattr(verdict, "request_id", None)
    if vtier != "ask":
        _finish_request(pid, "refused", request_id=rid,
                        reason=(f"the gate answered at tier {vtier!r}, which is not "
                                "a person saying yes"))
        return
    if not (allowed and outcome == "approved"):
        _finish_request(pid,
                        outcome if outcome in ("denied", "timed_out") else "refused",
                        request_id=rid,
                        reason=str(getattr(verdict, "reason", "refused"))[:200])
        return

    # THE PERSON SAID YES, ON THIS ONE CARD. Only now may the PC be touched.
    doc = {"phase": "starting", "pid": None, "from": here, "to": there,
           "started_at": time.time(), "updated_at": time.time(),
           "finished_at": None, "request_id": rid, "script": script,
           "backend": backend}
    try:
        why = (spawn_helper or _start_helper)(dict(doc))
    except Exception as exc:                            # noqa: BLE001
        _write_state(FAILED, finished_at=time.time(),
                     reason=f"the update could not be started ({type(exc).__name__})",
                     from_version=here, to_version=there, request_id=rid)
        _finish_request(pid, "failed", request_id=rid,
                        reason=f"the update could not be started "
                               f"({type(exc).__name__})")
        return
    if why:
        # A yes is not enough on its own: the PC may already be updating. The
        # state file already says why; the card's outcome says nothing ran.
        _finish_request(pid, "failed", request_id=rid, reason=str(why)[:200])
        return
    _finish_request(pid, "started", request_id=rid, to=there)


def _finish_request(pid: str, outcome: str, **extra) -> dict:
    """Record the card's outcome, clear the waiting slot, and return it."""
    global _PENDING, _LAST
    with _PENDING_LOCK:
        if _PENDING is not None and _PENDING["id"] == pid:
            _PENDING = None
        _LAST = {"outcome": outcome, "at": time.time(), **extra}
        last = dict(_LAST)
    try:
        import jarvis_framework as FW
        FW.audit_log("update.requested", {"outcome": outcome,
                                          "to": last.get("to"),
                                          "request_id": last.get("request_id")})
    except Exception:                                   # noqa: BLE001
        pass
    return last


# --------------------------------------------------------------------------
#   The detached helper - the only part that survives the restart
# --------------------------------------------------------------------------

#: The only names the updater's children are given beyond the OS basics
#: `jarvis_child_env.inherited()` already carries (PATH, SystemRoot, TEMP,
#: USERPROFILE, ProgramFiles, ...). Every one is read by this module or by the
#: programs it starts: `JARVIS_BACKEND`, `JARVIS_REPO`, `JARVIS_CONFIG_DIR` and
#: `OPENJARVIS_CONFIG_DIR` here and in `scripts/update-jarvis.ps1`;
#: `JARVIS_FRAMEWORK_TOML` and `GIT_CEILING_DIRECTORIES` in
#: `scripts/apply-patches.ps1`; `PYTHONIOENCODING` because the script's output
#: is read as text. The pairing token is NOT here and never will be - which is
#: the whole point of building the environment instead of copying this one.
CHILD_ENV_NAMES = (
    "JARVIS_BACKEND", "JARVIS_REPO", "JARVIS_CONFIG_DIR",
    "OPENJARVIS_CONFIG_DIR", "JARVIS_FRAMEWORK_TOML",
    "GIT_CEILING_DIRECTORIES", "PYTHONIOENCODING",
)


def child_env() -> dict:
    """The environment both children are started with - an allowlist, not a copy.

    A detached helper (and the updater script it runs) outlives the backend that
    started it and nothing watches it, so a copy of this process's environment
    would hand the pairing token (`HUD_TOKEN`/`JARVIS_TOKEN`) to a long-lived
    child. `jarvis_child_env.inherited()` starts from nothing, copies only the
    OS names a program needs to start and find its files plus `CHILD_ENV_NAMES`
    by name, and drops even an allowed name that looks like a secret. That is
    the same allowlist every other program Jarvis starts is given.

    `PATCHER_ENV` is set because the suite sweep the updater runs belongs to
    this update and must not refuse because of the lock this helper holds.
    """
    import jarvis_child_env
    env = jarvis_child_env.inherited(names=CHILD_ENV_NAMES)
    env[PATCHER_ENV] = "1"
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


def helper_argv(*, state: Path, script: Path, backend: Path,
                from_version: str = "", to_version: str = "") -> list:
    """The child's whole command line, built here and nowhere else.

    Fixed: the Python that is running this module, one `-c` that runs
    `helper_main()`, and four `--name value` pairs this module resolved. No part
    of it comes from the request, and there is no field that could add an
    argument.
    """
    return [
        sys.executable, "-c", "import jarvis_update; jarvis_update.helper_main()",
        "--state", str(state),
        "--script", str(script),
        "--backend", str(backend),
        "--from", str(from_version or ""),
        "--to", str(to_version or ""),
    ]


def _start_helper(doc: dict) -> Optional[str]:
    """Start the detached worker that runs the updater.

    Returns "" (None) when the worker was started, or a plain sentence saying
    why it was not - the PC may already be updating, and then nothing is
    started and this call changes nothing.

    On Windows the child gets `DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP` and
    no inherited handles, so the `Stop-Process` the updater itself performs on
    the backend does not take it down - it has to outlive the process that
    started it, because that IS the process the update closes.
    """
    script, backend = doc.get("script"), doc.get("backend")
    if not script or not backend:
        raise ValueError("the helper needs the script and the backend folder")
    busy = desktop_lock_words()
    if busy:
        # The desktop's own updater (or another helper) is already patching the
        # PC. Nothing is started and the state says why; this is the arm that
        # stops a PC approval and a phone approval patching twice at once.
        reason = f"an update was already running: {busy}"
        _write_state(FAILED, finished_at=time.time(), reason=reason,
                     from_version=doc.get("from"), to_version=doc.get("to"),
                     request_id=doc.get("request_id"))
        return reason
    argv = helper_argv(state=state_path(), script=Path(script), backend=Path(backend),
                       from_version=str(doc.get("from") or ""),
                       to_version=str(doc.get("to") or ""))
    kwargs = {
        "cwd": str(backend),
        "close_fds": True,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name == "nt":
        kwargs["creationflags"] = (
            getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200))
    else:
        kwargs["start_new_session"] = True
    # `env=` is written out here, not hidden in `kwargs`: the child is given
    # `child_env()`'s allowlist, never this process's environment.
    proc = subprocess.Popen(argv, env=child_env(), **kwargs)
    # The child writes its own pid into the state as its first act. Recording
    # the spawn here too means a status read in that gap sees "starting" rather
    # than "nothing", and a child that dies before writing is still visible.
    _write_state("starting", pid=proc.pid,
                 started_at=doc.get("started_at") or time.time(),
                 from_version=doc.get("from"), to_version=doc.get("to"),
                 request_id=doc.get("request_id"))
    return None


def _updater_argv(script: Path, backend: Path) -> list:
    """`scripts/update-jarvis.ps1` with the arguments this module owns.

    `-Force` closes a running Jarvis instead of waiting 90 seconds for a person
    at the PC - which is exactly what "update it from my phone" means. Nothing
    else is passed: no `-SkipTests` (the update must be proven), no
    `-SkipDesktop` (the card promised the new build), no `-NoCheck` (the live
    check is the last thing the card says happens).
    """
    return ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(script), "-BackendPath", str(backend), "-Force"]


class _HelperArgs:
    __slots__ = ("state", "script", "backend", "from_version", "to_version")

    def __init__(self, **kw):
        for name in self.__slots__:
            setattr(self, name, kw.get(name, ""))


def _helper_args(argv=None) -> _HelperArgs:
    """Parse `helper_argv`'s four pairs - stdlib only, no argparse import cost.

    An unknown or missing pair is a failure the caller reports: the helper only
    ever runs what `helper_argv` built, so a malformed one means this module and
    its child disagree.
    """
    raw = list(sys.argv[1:] if argv is None else argv)
    known = {"--state": "state", "--script": "script", "--backend": "backend",
             "--from": "from_version", "--to": "to_version"}
    got = {}
    i = 0
    while i + 1 < len(raw):
        name, value = raw[i], raw[i + 1]
        if name in known:
            got[known[name]] = value
            i += 2
        else:
            i += 1
    missing = [name for name in ("state", "script", "backend") if not got.get(name)]
    if missing:
        raise SystemExit(f"jarvis_update.helper_main: missing {', '.join(missing)}")
    return _HelperArgs(**got)


def phase_for_line(line: str) -> Optional[str]:
    """The phase an updater output line names, or None.

    The updater prints `[3/6] Closing Jarvis` and its siblings; its own titles
    are the contract here, so the numbers (which a switched-off step changes)
    are not read. Case-insensitive and tolerant of prefix decoration, because
    this reads another program's prose - but the words it looks for are its own,
    never a guess at "something happened".
    """
    text = str(line or "").lower()
    if not text:
        return None
    for marker, phase in _STEP_MARKERS:
        if marker in text:
            return phase
    return None


def _last_line(output: str) -> str:
    """The last line of the script's own output that says anything."""
    for line in reversed(str(output or "").splitlines()):
        if line.strip():
            return line.strip()[:200]
    return ""


def outcome_from(exit_code: int, output: str) -> tuple:
    """(phase, reason) for a finished script: done, or FAILED with plain words.

    Exit code first (`update-jarvis.ps1` exits 1 for "NOT DONE" and for "DONE
    WITH PROBLEMS"); then the script's own final banner, because a successful
    exit code with "the desktop app was NOT updated" on it is not a finished
    update - the card promised the new build. A failure is NEVER reported as
    done. The banners checked here are the script's own, quoted, and
    `test_phone_authorized_update.py` reads them out of it.
    """
    tail = str(output or "")
    low = tail.lower()
    if "done with problems" in low:
        return FAILED, ("the update ran into problems - the script's own last "
                        "screen says which, and its log has the detail")
    if "not done" in low:
        return FAILED, ("the update stopped before changing anything - the "
                        "script's own last screen says why")
    if "the desktop app was not updated" in low:
        return FAILED, ("the backend was patched, but the new desktop build was "
                        "not installed - the script's notes say why")
    try:
        code = int(exit_code)
    except (TypeError, ValueError):
        code = 1
    if code != 0:
        return FAILED, (f"the update script stopped with exit code {code} - its "
                        "own log says why")
    return DONE, ""


def _claim_helper_lock() -> bool:
    """Take the helper's exclusive lock; False when another live helper holds it.

    Created with `O_CREAT | O_EXCL`, so two helpers starting in the same
    millisecond cannot both win. A lock whose pid is gone is reclaimed - a
    killed helper must not block every later update.
    """
    path = helper_lock_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        doc = _read_json(path)
        if _pid_alive(doc.get("pid")):
            return False
        _delete(path)
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except OSError:
            return False
    except OSError:
        return False
    try:
        os.write(fd, json.dumps({"pid": os.getpid(),
                                 "at": time.time()}).encode("utf-8"))
    finally:
        os.close(fd)
    return True


def _release_helper_lock() -> None:
    """Remove the helper lock, but only when it is OUR pid's."""
    doc = _read_json(helper_lock_path())
    if doc.get("pid") == os.getpid():
        _delete(helper_lock_path())


def helper_main(argv=None) -> int:
    """The detached worker: run the one updater, report progress, exit.

    Its own process, its own lock, its own state writes. It never raises to the
    caller (there is no caller) and it always leaves a final `done` or `failed`
    in the state file - a helper that died silently would leave the phone
    waiting on a phase that never ends.
    """
    args = _helper_args(argv)
    if not _claim_helper_lock():
        # Another helper is running. Do NOT touch its state file: it is the one
        # reporting, and a second writer would make the phone's progress jump.
        return 2
    state = Path(args.state)
    # The card's own id, written by `_start_helper` before this process existed:
    # carried through every write so the audit line after the restart can name
    # the card that was approved.
    request_id = str(_read_json(state).get("request_id") or "")
    started = time.time()
    stop = threading.Event()
    phase = "starting"
    exit_code = None
    reason = ""
    ending = ""
    tail = collections.deque(maxlen=TAIL_LINES)

    # THE PC'S OWN LOCK IS TAKEN BEFORE THE TRY, so a refusal here is a FULL
    # refusal: it writes the failure and returns without reaching the block
    # whose `finally` closes out a run. The first version of this had the check
    # INSIDE the try, and its `return` still ran the `finally` - which wrote a
    # fresh "starting" over the failure it had just recorded and released the
    # lock it had just refused to take.
    busy = desktop_lock_words()
    if not take_shared_lock(os.getpid()):
        # The desktop's own updater (or another run) holds the PC's lock.
        # Starting a second patcher would be two updates at once.
        _write_state(FAILED, finished_at=time.time(),
                     reason=(f"an update was already running: "
                             f"{busy or 'the PC is updating'}"),
                     from_version=args.from_version,
                     to_version=args.to_version, request_id=request_id)
        _release_helper_lock()
        return 3

    def heartbeat():
        while not stop.wait(_HEARTBEAT_SECONDS):
            doc = _read_json(state)
            if str(doc.get("phase") or "") not in PHASES:
                return
            doc["updated_at"] = time.time()
            with _STATE_LOCK:
                _write_json(state, doc)
            refresh_shared_lock(os.getpid())

    beat = threading.Thread(target=heartbeat, name="jarvis-update-heartbeat",
                            daemon=True)
    try:
        _write_state(phase, pid=os.getpid(), started_at=started,
                     from_version=args.from_version,
                     to_version=args.to_version, request_id=request_id)
        beat.start()
        # The same allowlist the detached helper itself was given: the script
        # needs PATH and the settings named in `CHILD_ENV_NAMES`, and nothing
        # else this process inherited (`HUD_TOKEN` included) rides along.
        proc = subprocess.Popen(
            _updater_argv(Path(args.script), Path(args.backend)),
            cwd=str(args.backend), env=child_env(),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, errors="replace", bufsize=1,
            creationflags=(getattr(subprocess, "CREATE_NO_WINDOW", 0)
                           if os.name == "nt" else 0))
        try:
            for line in proc.stdout or ():
                tail.append(str(line).rstrip())
                found = phase_for_line(line)
                if found and found != phase:
                    phase = found
                    _write_state(phase, pid=os.getpid(), started_at=started,
                                 from_version=args.from_version,
                                 to_version=args.to_version,
                                 request_id=request_id,
                                 tail="\n".join(tail)[-TAIL_CHARS:])
        finally:
            try:
                exit_code = proc.wait(timeout=30)
            except Exception:                           # noqa: BLE001
                exit_code = proc.poll()
        output = "\n".join(tail)
        ending = _last_line(output)
        phase, reason = outcome_from(
            int(exit_code if exit_code is not None else 1), output)
    except Exception as exc:                            # noqa: BLE001
        phase, reason = FAILED, (f"the update helper could not run the script "
                                 f"({type(exc).__name__})")
    finally:
        stop.set()
        _write_state(phase, pid=os.getpid(), started_at=started,
                     finished_at=time.time(), from_version=args.from_version,
                     to_version=args.to_version, exit=exit_code, reason=reason,
                     ending=ending, tail="\n".join(tail)[-TAIL_CHARS:],
                     request_id=request_id)
        release_shared_lock(os.getpid())
        _release_helper_lock()
    return 0 if phase == DONE else 1


# --------------------------------------------------------------------------
#   GET /api/update/status - what the phone reads, and never changes
# --------------------------------------------------------------------------

def status(*, state: Optional[dict] = None,
           installed_now: Optional[Callable[[], dict]] = None,
           published_now: Optional[Callable[[], dict]] = None,
           tier_of: Optional[Callable[[str], str]] = None,
           backend: Optional[Callable[[], Optional[Path]]] = None,
           script: Optional[Callable[[], Optional[Path]]] = None,
           now: Optional[float] = None) -> dict:
    """GET /api/update/status. Read-only: no card, no write, no download.

    Answers, in plain words: what version is installed, what version is
    published ("cannot tell: ..." when it cannot be read), and the phase of any
    update in flight or just finished. `can_request` and `why_not` are the same
    answers `request()` would give - one function, `obstacle()` - so a screen can
    grey the button out with the reason already on it instead of finding out on
    the tap.
    """
    installed_now = installed_now or installed
    published_now = published_now or published
    tier_of = tier_of or _tier_of
    backend = backend or backend_folder
    script = script or script_path

    here = installed_now()
    there = published_now()
    here_version = here.get("version") if isinstance(here, dict) else None
    there_version = there.get("version") if isinstance(there, dict) else None
    newer = compare(here_version, there_version)

    st = read_state() if state is None else state
    phase = str(st.get("phase") or IDLE)
    if phase not in PHASE_WORDS:
        phase = IDLE
    live = running(st)
    dead = stale(st)
    shown = FAILED if dead else phase
    out = {
        "ok": True,
        "action": ACTION,
        "pc_only": False,
        "installed": here_version,
        "why_installed": str(here.get("why") or ""),
        "published": there_version,
        "why_published": str(there.get("why") or ""),
        "newer": newer,
        "phase": shown,
        "what": PHASE_WORDS.get(shown, PHASE_WORDS[IDLE]),
        "running": live,
        "can_request": False,
        "why_not": "",
        "started_at": st.get("started_at"),
        "updated_at": st.get("updated_at"),
        "finished_at": st.get("finished_at"),
        "from": st.get("from"),
        "to": st.get("to"),
        "ending": str(st.get("ending") or ""),
        "reason": str(st.get("reason") or ""),
        "tail": str(st.get("tail") or "")[-TAIL_CHARS:],
    }
    with _PENDING_LOCK:
        pending = _PENDING
        last = dict(_LAST) if _LAST is not None else None
    if pending is not None:
        out["waiting_for_approval"] = True
        out["expires_in"] = max(0, int(_left_s(pending)))
        out["to"] = pending.get("to")
    else:
        out["waiting_for_approval"] = False
    if last is not None:
        out["last"] = {k: last[k] for k in
                       ("outcome", "at", "reason", "request_id") if last.get(k) is not None}

    refused = obstacle(installed_now=lambda: here, published_now=lambda: there,
                       tier_of=tier_of, backend=backend, script=script,
                       state=st, now=now, pending=pending)
    if refused is None:
        out["can_request"] = True
    else:
        out["why_not"] = str(refused[1].get("error") or "")
        if isinstance(refused[1].get("reason"), str):
            out["why_not_detail"] = refused[1]["reason"]
    return out


# --------------------------------------------------------------------------
#   The two routes - a drop-in folder, so there is no patch and no core change
# --------------------------------------------------------------------------

def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls.do_GET`/`do_POST` so this module answers its own routes.

    Every other request goes straight to the original, untouched - the same
    shape `jarvis_read_aloud.install()` uses and the loader's own contract. Both
    routes do their own origin and token check first, because they never reach
    the core's dispatch; a refusal is the same 403/401 body every other route
    sends, so a client sees one rule and not two. There is no keyless route
    here and no separate allow-list to keep in step: a paired phone's own key
    is the credential, and the core's `token_ok` is the one that checks it.
    """
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(get0, "_jarvis_update", False):
        return "update       ask for a desktop update (already on)"

    def _allowed(self) -> bool:
        try:
            if not origin_ok(self):
                self._send(403, {"error": "cross-origin request refused"})
                return False
            if not token_ok(self):
                self._send(401, {"error": "bad or missing X-Jarvis-Token"})
                return False
        except Exception:                       # noqa: BLE001 - never a traceback page
            self._send(401, {"error": "bad or missing X-Jarvis-Token"})
            return False
        return True

    def do_GET(self):
        parts = urlsplit(str(getattr(self, "path", "") or ""))
        if parts.path.rstrip("/") != STATUS_PATH:
            return get0(self)
        if not _allowed(self):
            return None
        try:
            return self._send(200, status())
        except Exception as exc:                # noqa: BLE001 - never a traceback page
            return self._send(500, {"error": f"{type(exc).__name__}: {exc}"})

    def do_POST(self):
        parts = urlsplit(str(getattr(self, "path", "") or ""))
        if parts.path.rstrip("/") != REQUEST_PATH:
            return post0(self)
        if not _allowed(self):
            return None
        try:
            raw = read_body(self) or b"{}"
            body = json.loads(raw)
        except Exception:                       # noqa: BLE001 - it is read for nothing
            body = {}
        try:
            code, out = request(body if isinstance(body, dict) else {})
        except Exception as exc:                # noqa: BLE001 - never a traceback page
            code, out = 500, {"error": f"{type(exc).__name__}: {exc}"}
        return self._send(code, out)

    do_GET._jarvis_update = True
    do_POST._jarvis_update = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    return "update       GET status, POST request - one card, nothing before it"


# --------------------------------------------------------------------------
#   A command line for a person at the PC (not the phone path)
# --------------------------------------------------------------------------

def main(argv=None) -> int:
    """`python jarvis_update.py` prints the status; `--helper` is internal."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "--helper":
        return helper_main(argv[1:])
    print(json.dumps(status(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
