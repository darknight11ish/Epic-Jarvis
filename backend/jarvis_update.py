"""jarvis_update.py - "update Jarvis" asked for and approved from the phone.

NEW MODULE, shipped whole beside `jarvis_hud.py` (`scripts/apply-patches.ps1`
copies it, and `jarvis-backend/` carries the published twin). The two routes
come from this module's own `install()`, called by the drop-in folder
`plugins/ready/update/` - the loader's route, so **no patch and no core change**:

    GET  /api/update/status          -> status()          read-only, no card
    POST /api/update/request         -> request()         ONE card, tier "ask"

WHY THIS EXISTS. `scripts/update-jarvis.ps1` already does the whole update
safely - it closes Jarvis, runs `apply-patches.ps1`, installs the signed
desktop build, starts Jarvis again and runs the live check - and it never
approves anything itself. What was missing was a way to ASK for it from the
phone, with the owner's own fingerprint deciding the card. This module is that
ask. It adds no second updater: the only thing it ever runs is that one script,
with arguments this file builds and the request cannot touch.

THE THREE THINGS THIS FILE WILL NEVER DO

  * It never approves anything. The card is raised through `jarvis_gate.check`
    at tier "ask" and the update starts only on a verdict that is a person
    saying yes (`allowed` AND `outcome == "approved"` AND tier "ask"). A
    loosened tier line is refused in words before a card exists, so a settings
    edit cannot turn this into "updates install themselves".
  * It never invents an argument. The child is
    `powershell -NoProfile -ExecutionPolicy Bypass -File <the one script>
     -BackendPath <the folder this module found> -Force`. Nothing from the
    request body reaches it: there is no field for a command, a path or a
    version. `-Force` closes a running Jarvis rather than waiting for the owner
    to, which is the whole point of doing it from the phone.
  * It never runs the updater in the server process. The updater CLOSES the
    backend it is asked from, so the worker has to be a DETACHED process that
    survives that restart - `helper_main()` below, started with
    DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP on Windows.

THE VERSIONS, AND WHAT "CANNOT TELL" MEANS. Two numbers are compared:

  * installed - the version of the Jarvis Desktop app on this PC, read from
    the same Windows uninstall entry the updater's own `Get-InstalledDesktop`
    reads (the HIGHEST of the entries: an old install leaves its row behind,
    and this PC has 0.2.294 and 0.2.297 beside 0.2.456). Nothing is guessed:
    no entry, or one with no DisplayVersion, is "cannot tell".
  * published - the newest release's version, from the public manifest the
    desktop app's own updater reads. The read is `jarvis_quick._release_manifest`,
    reused rather than copied, so the phone is told the same version the
    desktop's Settings card says.

Either number unreadable is "cannot tell", and a request refuses in words: an
update nobody can prove is newer is not offered. `newer` in the status is
`true`, `false` or `null` (cannot tell) - never a guess.

THE PHASES. The updater prints its own numbered steps, and `phase_for_line()`
maps them to the six words this module reports: closing, patching, installing,
restarting, checking, then done or failed. The mapping is a pure function so a
test can prove every phase, and the words shown are `PHASE_WORDS` - one plain
sentence each, no jargon.

THE STATE FILE. `<config dir>/update-state.json`, a few hundred bytes:
{"phase", "pid", "started_at", "updated_at", "finished_at", "from", "to",
 "exit", "reason", "tail"}. It is written beside and renamed over, so a reader
never sees half a file, and `status()` reads it back even after the restart the
update itself caused. `tail` is the last few lines the script printed - bounded,
so the file stays small - which is what makes a failure diagnosable from the
phone.

ONE UPDATE AT A TIME, IN THREE PLACES. A second request refuses cleanly:

  * in the backend - one card may be waiting at a time (`_PENDING`), and a
    state file whose phase is still in flight with a LIVE pid is "running";
  * in the helper - `<config dir>/update-helper.lock` is created with
    `O_CREAT | O_EXCL`, and a second helper that finds a live pid exits without
    touching the first one's state;
  * on the PC - the same `update-in-progress.lock` the desktop's own
    "update both halves" writes. The helper holds it (heartbeat refreshed, so a
    long patch does not look stale) and sets `JARVIS_INSIDE_PATCHER=1` for its
    child, which is how `backend/run_suites.py` knows the suite sweep belongs
    to the update that is running. So the desktop's updater refuses while this
    one runs, and this one refuses while the desktop's runs.

WHAT THIS DELIBERATELY DOES NOT DO. It does not download anything itself, build
anything itself, patch anything itself, or keep a copy of the update. Every one
of those is `scripts/update-jarvis.ps1`'s job, and its own header says what it
checks before it changes anything. This module's whole job is the ask, the card,
the detached launch, and the honest progress report.

NOTHING HERE IS IN THE PHONE'S UI YET. The two routes are the backend half; the
phone half is a later piece of work (docs/ARCHITECTURE.md section 8 records that
one-sidedness, as it must for every feature that lands on one side first).
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

#: The gate action. ONE name, used by the card, the framework's tier table
#: (absent there on purpose - an unclassified action is forced to "ask", and
#: `jarvis_asks_first.MUST_ASK` names it so a later loosening cannot run it),
#: and `jarvis_agent.NEEDS_A_PERSON`. Nothing else spells it.
ACTION = "update_jarvis"

#: The state file's name in the folder Jarvis keeps its own data in - the same
#: folder rule `jarvis_framework._config_dir`, `tools/update_backend.py` and the
#: desktop's `backend_update.rs` use.
STATE_NAME = "update-state.json"
#: The helper's own lock, created O_CREAT | O_EXCL so two helpers cannot run.
HELPER_LOCK_NAME = "update-helper.lock"
#: The lock the desktop's "update both halves" already writes and reads: the
#: two update paths must not run at once on one PC.
SHARED_LOCK_NAME = "update-in-progress.lock"
#: The environment variable `backend/run_suites.py` reads to know the suite
#: sweep belongs to the update that is running (it refuses beside a valid lock
#: otherwise, including our own).
PATCHER_ENV = "JARVIS_INSIDE_PATCHER"

#: The one program allowed to change the backend folder, relative to the repo.
SCRIPT_REL = ("scripts", "update-jarvis.ps1")
BACKEND_MARKER = "jarvis_hud.py"

#: The phases, in the order the updater reaches them. Any of these means "an
#: update is in flight"; `done` and `failed` are the two endings.
PHASES = ("closing", "patching", "installing", "restarting", "checking")
DONE = "done"
FAILED = "failed"
IDLE = "idle"

#: One plain sentence per phase, for the phone to show as-is. No jargon: "the
#: new build" is the desktop app, and the words say what the PC is doing.
PHASE_WORDS = {
    IDLE: "Nothing is updating.",
    "closing": "Jarvis on the PC is closing so the update can be applied.",
    "patching": "The backend on the PC is being patched.",
    "installing": "The new build of Jarvis is being installed on the PC.",
    "restarting": "Jarvis is starting again on the PC.",
    "checking": "Jarvis is checking itself after the update.",
    DONE: "The update finished. Jarvis is on the new version.",
    FAILED: "The update did not finish - see the reason below.",
}

#: The updater's own step titles -> this module's phase words. Pure data, so a
#: test can walk every phase without running anything.
_STEP_MARKERS = (
    ("closing jarvis", "closing"),
    ("patching the backend", "patching"),
    ("updating the desktop app", "installing"),
    ("starting jarvis and checking it", "restarting"),
    ("running the live check", "checking"),
)

#: The shared lock's numbers, word for word with `tools/update_backend.py` and
#: the desktop's `backend_update.rs`.
LOCK_HEARTBEAT_SECONDS = 1800.0
LOCK_CEILING_SECONDS = 10_800.0
LOCK_CLOCK_SKEW_SECONDS = 60.0
LOCK_MAX_BYTES = 64 * 1024
#: A helper that has been in flight this long without finishing is not trusted
#: to be a live update any more (its pid is the authority; this is the guard
#: for a pid that was reused by something else).
HELPER_CEILING_SECONDS = 10_800.0
#: How many of the script's last lines the state keeps for a failure report.
TAIL_LINES = 12
TAIL_CHARS = 2000

_LOCK = threading.Lock()
_STATE_LOCK = threading.Lock()
_PENDING: Optional[dict] = None      # the one card waiting, if any
_LAST: Optional[dict] = None         # the last outcome, for the phone


# --------------------------------------------------------------------------
#   Where things live
# --------------------------------------------------------------------------

def config_dir() -> Path:
    """The folder Jarvis keeps its own data in.

    The same order every other part of this PC uses: `OPENJARVIS_CONFIG_DIR`,
    then `JARVIS_CONFIG_DIR`, then `jarvis_framework.CONFIG_DIR`, then
    `~/.openjarvis`. Read fresh on every call so a test can move it, and so a
    helper started with the variable set agrees with the server that started
    it.
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
    """Where the helper writes progress and `status()` reads it."""
    return config_dir() / STATE_NAME


def helper_lock_path() -> Path:
    return config_dir() / HELPER_LOCK_NAME


def shared_lock_path() -> Path:
    return config_dir() / SHARED_LOCK_NAME


def backend_folder() -> Optional[Path]:
    """The folder holding `jarvis_hud.py`, or None when this run cannot tell.

    `JARVIS_BACKEND` when it names a real backend folder - `scripts/install-backend.ps1`
    is the documented way that gets set, and it is what the updater's own
    `-BackendPath` default reads too. Otherwise this module's own folder, which
    on the owner's PC IS the backend folder. The repository's `backend/` (this
    file's twin, where there is no `jarvis_hud.py`) is therefore honestly "not
    found" rather than mistaken for a backend.
    """
    for candidate in (_env_path("JARVIS_BACKEND"), Path(__file__).resolve().parent):
        if candidate is not None and (candidate / BACKEND_MARKER).is_file():
            return candidate
    return None


def repo_folder() -> Optional[Path]:
    """The folder this repository is cloned into, or None when this run cannot tell.

    Three sources, in the order of "most explicit first", and no disk search -
    the same doctrine as the desktop's own `backend_update.rs`, which refuses
    rather than guesses at a security-relevant path:

      1. `JARVIS_REPO`, for a terminal or a script that wants to say it outright;
      2. `updates.repo_folder` in the desktop app's own settings file - the box
         on Settings -> Updates, already filled in on a PC that has used the
         updater from the app. Read-only, and the SAME value that button uses,
         so the two paths cannot disagree about where the repository is;
      3. this module's parent folder, which is the repository when the suite
         runs from a checkout.

    A candidate only counts when it really holds `scripts/update-jarvis.ps1`.
    """
    candidates = [
        _env_path("JARVIS_REPO"),
        _desktop_settings_repo(),
        Path(__file__).resolve().parent.parent,
    ]
    for candidate in candidates:
        if candidate is not None and (candidate.joinpath(*SCRIPT_REL)).is_file():
            return candidate
    return None


def script_path() -> Optional[Path]:
    """The one updater this module is allowed to run, or None."""
    repo = repo_folder()
    return repo.joinpath(*SCRIPT_REL) if repo is not None else None


def _env_path(name: str) -> Optional[Path]:
    raw = os.environ.get(name)
    if not raw or not str(raw).strip():
        return None
    try:
        return Path(os.path.expanduser(str(raw).strip()))
    except Exception:                                   # noqa: BLE001
        return None


def _desktop_settings_repo() -> Optional[Path]:
    """`updates.repo_folder` from the desktop app's own store, or None.

    The Tauri app keeps its settings in `%APPDATA%\\com.jarvis.desktop\\`
    (`tauri.conf.json`'s identifier) under `jarvis-desktop.json`; the key is
    `backend_update.REPO_KEY`. Never raises: a missing file, a file that is not
    JSON, or a value that is not a string is simply "no answer from there".
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
    if isinstance(updates, dict):
        value = updates.get("repo_folder")
    else:
        # A flat key is what a hand-edited store can look like.
        value = doc.get("updates.repo_folder")
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return Path(os.path.expanduser(value.strip()))
    except Exception:                                   # noqa: BLE001
        return None


# --------------------------------------------------------------------------
#   The two versions
# --------------------------------------------------------------------------

def _version_parts(version) -> Optional[tuple]:
    """(0, 2, 456) for "0.2.456"; None when it is not a version.

    The release stamps `major.minor.<run number>` (`desktop-release.yml`), so
    numbers are compared as numbers and never as strings - "0.2.99" is older
    than "0.2.100", which a string comparison gets backwards. The rule is
    `jarvis_quick._version_parts`' own; this copy exists only so the module
    still compares versions on a PC whose `jarvis_quick.py` is older.
    """
    try:
        import jarvis_quick
        return jarvis_quick._version_parts(version)
    except Exception:                                   # noqa: BLE001
        pass
    import re
    text = str(version or "").strip().lstrip("vV")
    if not re.fullmatch(r"\d{1,9}(?:\.\d{1,9}){0,3}", text):
        return None
    parts = [int(p) for p in text.split(".")]
    while len(parts) < 4:
        parts.append(0)
    return tuple(parts)


def _registry_versions() -> list:
    """Every "Jarvis Desktop" version the uninstall entries name, newest first.

    Read-only. Windows only; anywhere else the list is empty and the caller
    says "cannot tell". An old install leaves its row behind, which is why this
    returns a LIST and the caller takes the highest - the first row is not the
    installed app (this PC carries 0.2.294 and 0.2.297 beside 0.2.456).
    """
    if os.name != "nt":
        return []
    try:
        import winreg
    except Exception:                                   # noqa: BLE001
        return []
    roots = (
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    )
    found = []
    for root, sub in roots:
        try:
            key = winreg.OpenKey(root, sub)
        except OSError:
            continue
        try:
            index = 0
            while True:
                try:
                    child = winreg.EnumKey(key, index)
                except OSError:
                    break
                index += 1
                try:
                    with winreg.OpenKey(key, child) as row:
                        try:
                            name, _ = winreg.QueryValueEx(row, "DisplayName")
                        except OSError:
                            continue
                        if "jarvis desktop" not in str(name or "").lower():
                            continue
                        try:
                            version, _ = winreg.QueryValueEx(row, "DisplayVersion")
                        except OSError:
                            continue
                        text = str(version or "").strip()
                        if _version_parts(text) is not None:
                            found.append(text)
                except OSError:
                    continue
        finally:
            try:
                key.Close()
            except Exception:                           # noqa: BLE001
                pass
    found.sort(key=lambda v: _version_parts(v) or (0, 0, 0, 0), reverse=True)
    return found


def installed() -> dict:
    """{"version": str|None, "why": str} - the Jarvis Desktop app on this PC.

    `why` is "" or a plain "cannot tell: ..." sentence. No network, nothing
    written.
    """
    versions = _registry_versions()
    if versions:
        return {"version": versions[0], "why": "", "others": versions[1:4]}
    return {"version": None,
            "why": "cannot tell: no installed Jarvis Desktop version is recorded on this PC"}


def published() -> dict:
    """{"version": str|None, "why": str} - the newest published release.

    One public read, and it is `jarvis_quick`'s own manifest read, reused so
    the phone and the desktop's Settings card can never disagree. A missing or
    older `jarvis_quick.py` is "cannot tell", never a made-up number.
    """
    try:
        import jarvis_quick
        read = getattr(jarvis_quick, "_release_manifest", None)
        if not callable(read):
            raise AttributeError("this PC's jarvis_quick.py has no release read")
        manifest, why = read()
    except Exception as exc:                            # noqa: BLE001
        return {"version": None,
                "why": f"cannot tell: the release list could not be read ({type(exc).__name__})"}
    if not manifest:
        return {"version": None,
                "why": f"cannot tell: the release list could not be read ({why or 'no reason given'})"}
    if not isinstance(manifest, dict):
        return {"version": None, "why": "cannot tell: the release list was not in the expected shape"}
    version = str(manifest.get("version") or "").strip()
    if _version_parts(version) is None:
        return {"version": None,
                "why": "cannot tell: the release list named no version this PC understands"}
    return {"version": version, "why": ""}


def compare(installed_version, published_version) -> Optional[bool]:
    """True when the published version is newer; None when either is unreadable."""
    here, there = _version_parts(installed_version), _version_parts(published_version)
    if here is None or there is None:
        return None
    return there > here


# --------------------------------------------------------------------------
#   The state file - progress the status route reads, across the restart
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
    update down; the phase is reported from memory then."""
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


def read_state() -> dict:
    """The last progress the helper wrote, or {} when it has never run."""
    return _read_json(state_path())


def _pid_alive(pid) -> bool:
    """Is this a running process on this machine?

    `os.kill(pid, 0)` is the documented existence probe and sends nothing.
    A PermissionError means the process EXISTS and belongs to someone else -
    the same answer Rust's OpenProcess path gives - so it counts as alive.
    """
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
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
    A state file with no pid (written by an older version) is not trusted as a
    live update either.
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
#   The desktop's own update lock - so the two update paths cannot both run
# --------------------------------------------------------------------------

def desktop_lock_words(now: Optional[float] = None) -> str:
    """The plain refusal when the desktop's own update holds the shared lock,
    else "".

    The rules are `tools/update_backend.py`'s, word for word: a live pid, a
    heartbeat under 30 minutes old, a start under 3 hours old, and no timestamp
    further than a minute into the future (a clock that moved is not evidence of
    a live update). A lock that is stale, unreadable or absent answers "" - the
    lock is advisory, and a reader that cannot tell must not block an update the
    owner asked for.
    """
    doc = _read_json(shared_lock_path())
    if not doc:
        return ""
    pid = doc.get("pid")
    started = doc.get("started_at")
    updated = doc.get("updated_at")
    if (not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0
            or not isinstance(started, (int, float)) or isinstance(started, bool)
            or not isinstance(updated, (int, float)) or isinstance(updated, bool)):
        return ""
    now = time.time() if now is None else now
    if started > now + LOCK_CLOCK_SKEW_SECONDS or updated > now + LOCK_CLOCK_SKEW_SECONDS:
        return ""
    if not _pid_alive(pid):
        return ""
    if now - updated > LOCK_HEARTBEAT_SECONDS:
        return ""
    if now - started > LOCK_CEILING_SECONDS:
        return ""
    pace = doc.get("pace") if isinstance(doc.get("pace"), str) else "an update"
    return (f"the PC is already updating Jarvis ({pace}), started "
            f"{_words_ago(now - float(started))}; wait for that one to finish")


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


# --------------------------------------------------------------------------
#   The card
# --------------------------------------------------------------------------

def describe(installed_version: str, target_version: str) -> str:
    """The card's text. Five facts, in plain words, and both directions said.

    What it moves to; that Jarvis on the PC closes for about a minute; that
    this phone's link drops and comes back; that the installer's signature is
    checked; and that nothing else on the PC changes. `docs/ARCHITECTURE.md`
    section 3 asks what refusing costs to be on every card, so "if you say no"
    is the last line.
    """
    here = str(installed_version or "").strip()
    move = (f"from {here} to {target_version}" if here else f"to {target_version}")
    return (
        f"Update Jarvis on the PC {move}?\n\n"
        "If you say yes: Jarvis on the PC closes for about a minute while the "
        "update is applied, then starts again on the new version. This phone's "
        "link will drop while that happens and come back by itself - you do not "
        "need to reconnect or pair again.\n\n"
        "The desktop app's installer is checked against Jarvis's own signing key "
        "before it is run, and the backend folder is patched with this "
        "repository's own patcher, which rehearses every patch on a throwaway "
        "copy first.\n\n"
        "Nothing else on the PC changes: no other program is installed, and none "
        "of your documents, mail, notes, photos or saved memory is touched. Only "
        "Jarvis's own files and its logs are written.\n\n"
        "If you say no: nothing changes, and nothing is downloaded."
    )


def _tier_of(action: str) -> str:
    import jarvis_framework as FW
    return str(FW.action_tier(action))


def _gate(action: str, detail: dict, prompt: str):
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def _timeout() -> float:
    try:
        import jarvis_framework as FW
        return float(FW.load_framework().get("autonomy", {})
                     .get("approval_timeout_seconds", 900))
    except Exception:                                   # noqa: BLE001
        return 900.0


def _left_s(p: dict) -> float:
    """Seconds left of the waiting card, by the MONOTONIC clock (a clock that
    is set while a card waits must not shorten or stretch it)."""
    mark = p.get("since_m")
    if isinstance(mark, (int, float)) and not isinstance(mark, bool):
        return p["timeout"] - (time.monotonic() - mark)
    return p["since"] + p["timeout"] - time.time()


def _spawn(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="jarvis-update-card", daemon=True).start()


# --------------------------------------------------------------------------
#   The request - ONE card, and nothing starts until a person says yes
# --------------------------------------------------------------------------

def _refusal(code: int, error: str, **extra) -> tuple:
    out = {"ok": False, "error": error}
    out.update(extra)
    return code, out


def request(body=None, *, gate: Optional[Callable] = None,
            tier_of: Optional[Callable[[str], str]] = None,
            spawn: Optional[Callable] = None,
            backend: Optional[Callable[[], Optional[Path]]] = None,
            script: Optional[Callable[[], Optional[Path]]] = None,
            installed_now: Optional[Callable[[], dict]] = None,
            published_now: Optional[Callable[[], dict]] = None,
            spawn_helper: Optional[Callable[[dict], None]] = None) -> tuple:
    """POST /api/update/request. Returns (http_status, payload).

    Refuses, in words, when there is nothing newer, when an update is already
    running, when the backend folder cannot be found, or when the updater
    cannot be found. Otherwise raises exactly ONE card on a background thread
    and returns at once; the update itself starts only if that card is approved.

    `body` is read for nothing: the route takes no argument that could change
    what runs. It is accepted so the route's own call is uniform with its
    neighbours (and so a future version can report what it ignored without a
    new signature).
    """
    global _PENDING
    gate = gate or _gate
    tier_of = tier_of or _tier_of
    spawn = spawn or _spawn
    backend = backend or backend_folder
    script = script or script_path
    installed_now = installed_now or installed
    published_now = published_now or published

    with _LOCK:
        if _PENDING is not None:
            left = max(0, int(_left_s(_PENDING)))
            return _refusal(409,
                            "an update request is already waiting for approval - "
                            "approve or deny that card first",
                            pending=True, expires_in=left)

    state = read_state()
    if running(state):
        return _refusal(409,
                        "an update is already running on the PC",
                        phase=str(state.get("phase") or ""),
                        what=PHASE_WORDS.get(str(state.get("phase") or ""), ""))

    busy = desktop_lock_words()
    if busy:
        return _refusal(409, f"an update is already running: {busy}")

    folder = backend()
    if folder is None:
        return _refusal(409,
                        "I cannot find the Jarvis backend folder on this PC",
                        reason=("the folder holding jarvis_hud.py was not found; set "
                                "JARVIS_BACKEND to it (scripts\\install-backend.ps1 "
                                "does that) and ask again"))
    updater = script()
    if updater is None:
        return _refusal(409,
                        "I cannot find the folder this repository is cloned into",
                        reason=("scripts\\update-jarvis.ps1 was not found; set "
                                "JARVIS_REPO to the repository folder, or fill in the "
                                "repository box on Settings -> Updates in the desktop app"))

    here = installed_now()
    there = published_now()
    here_version = here.get("version") if isinstance(here, dict) else None
    there_version = there.get("version") if isinstance(there, dict) else None
    newer = compare(here_version, there_version)
    if newer is None:
        why = (here.get("why") if isinstance(here, dict) else "") or \
              (there.get("why") if isinstance(there, dict) else "") or \
              "the two versions could not be compared"
        return _refusal(409,
                        "I cannot tell whether there is a newer version",
                        installed=here_version, published=there_version,
                        reason=why)
    if not newer:
        return _refusal(409,
                        "there is nothing newer to install",
                        installed=here_version, published=there_version,
                        reason=(f"this PC is on {here_version}, and the newest "
                                f"published is {there_version}"))

    try:
        tier = tier_of(ACTION)
    except Exception as exc:                            # noqa: BLE001
        tier = f"unreadable ({type(exc).__name__})"
    if tier != "ask":
        # Checked BEFORE a card is raised: a card that could not end in a person
        # deciding must not be raised at all.
        return _refusal(409,
                        f"{ACTION} is tier {tier!r} in jarvis-framework.toml; "
                        "updating Jarvis needs a person to say yes, so it must be "
                        "'ask'",
                        pending=False)

    pid = uuid.uuid4().hex
    with _LOCK:
        if _PENDING is not None:                        # lost a race with another request
            return _refusal(409,
                            "an update request is already waiting for approval - "
                            "approve or deny that card first",
                            pending=True)
        _PENDING = {"id": pid, "from": here_version, "to": there_version,
                    "script": str(updater), "backend": str(folder),
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
        _finish_request(pid, "failed", reason=f"could not raise the card ({type(exc).__name__})")
        return _refusal(500, "could not raise the approval card")

    with _LOCK:
        waiting = _PENDING is not None and _PENDING["id"] == pid
    return 202, {
        "ok": True, "pending": waiting,
        "installed": here_version, "published": there_version,
        "to": there_version,
        "message": ("Approve the card on your PC or phone to start the update. "
                    "Nothing is downloaded or changed until you do."),
    }


def _decide(pid: str, *, gate: Callable, spawn_helper: Optional[Callable]) -> None:
    """Raise the card for staged request `pid`, wait, and act on the answer.

    Blocks - it runs on the thread `request()` started. Nothing starts unless a
    person said yes on THIS card at tier "ask".
    """
    with _LOCK:
        p = _PENDING if (_PENDING and _PENDING["id"] == pid) else None
        if p is None:
            return
        here, there = p.get("from"), p.get("to")
        script, backend = p.get("script"), p.get("backend")
    text = describe(here, there)
    detail = {"text": text, "from": here, "to": there,
              "what": "update Jarvis on this PC from the phone",
              "script": script, "backend": backend}
    try:
        verdict = gate(ACTION, detail, text)
    except Exception as exc:                            # noqa: BLE001
        _finish_request(pid, "refused", reason=f"the approval gate failed ({type(exc).__name__})")
        return
    vtier = getattr(verdict, "tier", "unknown")
    allowed = getattr(verdict, "allowed", False) is True
    outcome = getattr(verdict, "outcome", None)
    if outcome is None:
        outcome = "approved" if (allowed and vtier == "ask") else "refused"
    rid = getattr(verdict, "request_id", None)
    if vtier != "ask":
        _finish_request(pid, "refused", request_id=rid,
                        reason=f"the gate answered at tier {vtier!r}, which is not "
                               "a person saying yes")
        return
    if not (allowed and outcome == "approved"):
        _finish_request(pid, outcome if outcome in ("denied", "timed_out") else "refused",
                        request_id=rid,
                        reason=str(getattr(verdict, "reason", "refused"))[:200])
        return

    doc = {"phase": "closing", "pid": None, "from": here, "to": there,
           "started_at": time.time(), "updated_at": time.time(),
           "finished_at": None, "request_id": rid}
    try:
        if spawn_helper is not None:
            spawn_helper(doc)
        else:
            _start_helper(dict(doc), script=script, backend=backend)
    except Exception as exc:                            # noqa: BLE001
        _write_state({**doc, "phase": FAILED, "finished_at": time.time(),
                      "reason": f"the update could not be started ({type(exc).__name__})"})
        _finish_request(pid, "failed", request_id=rid,
                        reason=f"the update could not be started ({type(exc).__name__})")
        return
    _finish_request(pid, "started", request_id=rid, to=there)


def _finish_request(pid: str, outcome: str, **extra) -> dict:
    """Record the card's outcome, clear the waiting slot, and return it."""
    global _PENDING, _LAST
    with _LOCK:
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

def helper_argv(*, state: Path, script: Path, backend: Path,
                from_version: str = "", to_version: str = "") -> list:
    """The child's whole command line, built here and nowhere else.

    Fixed: the Python that is running this module, one `-c` that runs
    `helper_main()`, and four `--name value` pairs this module resolved. No
    part of it comes from the request, and there is no field that could add an
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


def _start_helper(doc: dict, *, script, backend) -> None:
    """Start the detached worker that runs the updater.

    On Windows the child gets `DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP` and
    no inherited handles, so the `Stop-Process` the updater itself performs on
    the backend does not take it down - it has to outlive the process that
    started it, because that is the process the update closes.
    """
    argv = helper_argv(state=state_path(), script=Path(script), backend=Path(backend),
                       from_version=str(doc.get("from") or ""),
                       to_version=str(doc.get("to") or ""))
    env = os.environ.copy()
    # The suite sweep the patcher runs must not refuse because of the lock this
    # helper is holding: it belongs to the update that is running.
    env[PATCHER_ENV] = "1"
    env.setdefault("PYTHONIOENCODING", "utf-8")
    kwargs = {
        "cwd": str(backend),
        "env": env,
        "close_fds": True,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name == "nt":
        kwargs["creationflags"] = (getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
                                   | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200))
    else:
        kwargs["start_new_session"] = True
    proc = subprocess.Popen(argv, **kwargs)
    # The child writes its own pid into the state as its first act. Recording
    # the spawn here too means a status read in the gap sees "closing" rather
    # than "nothing", and a child that dies before writing is still visible.
    _write_state({"phase": "closing", "pid": proc.pid,
                  "started_at": doc.get("started_at") or time.time(),
                  "updated_at": time.time(), "finished_at": None,
                  "from": doc.get("from"), "to": doc.get("to"),
                  "request_id": doc.get("request_id")})


def phase_for_line(line: str) -> Optional[str]:
    """The phase an updater output line names, or None.

    The updater prints `[3/6] Closing Jarvis` and its siblings; the titles are
    the contract here, so the numbers (which a `-SkipDesktop` run changes) are
    not read. Case-insensitive and tolerant of prefix decoration, because this
    is a reader of another program's prose - but the words it looks for are
    its own, never a guess at "something happened".
    """
    text = str(line or "").lower()
    if not text:
        return None
    for marker, phase in _STEP_MARKERS:
        if marker in text:
            return phase
    return None


def outcome_from(exit_code: int, output: str) -> tuple:
    """(phase, reason) for a finished script: done, or FAILED with plain words.

    Exit code first (`update-jarvis.ps1` exits 1 for "NOT DONE" and for
    "DONE WITH PROBLEMS"); then the script's own final banner, because a
    successful exit code with "the desktop app was NOT updated" on it is not a
    finished update - the card promised the new build. A failure is NEVER
    reported as done.
    """
    tail = str(output or "")
    low = tail.lower()
    if "done with problems" in low:
        return FAILED, ("the update ran into problems - the script's own last screen "
                        "says which, and its log has the detail")
    if "not done" in low:
        return FAILED, ("the update stopped before changing anything - the script's "
                        "own last screen says why")
    if "the desktop app was not updated" in low:
        return FAILED, ("the backend was patched, but the new desktop build was not "
                        "installed - the script's notes say why")
    if int(exit_code) != 0:
        return FAILED, (f"the update script stopped with exit code {int(exit_code)} - "
                        "its own log says why")
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
        os.write(fd, json.dumps({"pid": os.getpid(), "at": time.time()}).encode("utf-8"))
    finally:
        os.close(fd)
    return True


def _release_helper_lock() -> None:
    """Remove the helper lock, but only when it is OUR pid's."""
    doc = _read_json(helper_lock_path())
    if doc.get("pid") == os.getpid():
        _delete(helper_lock_path())


def _write_shared_lock(pid: int) -> None:
    """Hold the same lock the desktop's "update both halves" writes.

    `pace` is "phone" rather than one of the desktop's three: an unknown pace is
    still a live lock to every reader (the desktop's `parse_update_lock` says so
    in its own comment), and it says truthfully which half asked for the run.
    """
    now = time.time()
    _write_json(shared_lock_path(), {"pid": int(pid), "started_at": now,
                                     "updated_at": now, "pace": "phone"})


def _release_shared_lock(pid: int) -> None:
    doc = _read_json(shared_lock_path())
    if doc.get("pid") == pid:
        _delete(shared_lock_path())


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
    started = time.time()
    stop = threading.Event()

    def heartbeat():
        while not stop.wait(60.0):
            doc = _read_json(state)
            if str(doc.get("phase") or "") not in PHASES:
                return
            doc["updated_at"] = time.time()
            with _STATE_LOCK:
                _write_json(state, doc)
            lock = _read_json(shared_lock_path())
            if lock.get("pid") == os.getpid():
                lock["updated_at"] = time.time()
                _write_json(shared_lock_path(), lock)

    beat = threading.Thread(target=heartbeat, name="jarvis-update-heartbeat", daemon=True)
    phase = "closing"
    tail = collections.deque(maxlen=TAIL_LINES)
    exit_code = None
    reason = ""
    try:
        _write_shared_lock(os.getpid())
        with _STATE_LOCK:
            _write_json(state, {"phase": phase, "pid": os.getpid(),
                                "started_at": started, "updated_at": started,
                                "finished_at": None, "from": args.from_version,
                                "to": args.to_version})
        beat.start()
        argv_child = _updater_argv(Path(args.script), Path(args.backend))
        env = os.environ.copy()
        env[PATCHER_ENV] = "1"
        env.setdefault("PYTHONIOENCODING", "utf-8")
        proc = subprocess.Popen(argv_child, cwd=str(args.backend), env=env,
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
                    with _STATE_LOCK:
                        _write_json(state, {"phase": phase, "pid": os.getpid(),
                                            "started_at": started,
                                            "updated_at": time.time(),
                                            "finished_at": None,
                                            "from": args.from_version,
                                            "to": args.to_version,
                                            "tail": "\n".join(tail)[-TAIL_CHARS:]})
        finally:
            try:
                exit_code = proc.wait(timeout=30)
            except Exception:                           # noqa: BLE001
                exit_code = proc.poll()
        phase, reason = outcome_from(int(exit_code if exit_code is not None else 1),
                                     "\n".join(tail))
    except Exception as exc:                            # noqa: BLE001
        phase, reason = FAILED, f"the update helper could not run the script ({type(exc).__name__})"
    finally:
        stop.set()
        with _STATE_LOCK:
            _write_json(state, {"phase": phase, "pid": os.getpid(),
                                "started_at": started, "updated_at": time.time(),
                                "finished_at": time.time(),
                                "from": args.from_version, "to": args.to_version,
                                "exit": exit_code, "reason": reason,
                                "tail": "\n".join(tail)[-TAIL_CHARS:]})
        _release_shared_lock(os.getpid())
        _release_helper_lock()
    return 0 if phase == DONE else 1


def _updater_argv(script: Path, backend: Path) -> list:
    """`scripts/update-jarvis.ps1` with the arguments this module owns.

    `-Force` closes a running Jarvis instead of waiting 90 seconds for a person
    at the PC - which is exactly what "update it from my phone" means. Nothing
    else is passed: no `-SkipTests` (the update must be proven), no
    `-SkipDesktop` (the card promised the new build), no `-NoCheck` (the live
    check is the last thing the card says happens).
    """
    powershell = "powershell.exe"
    return [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass",
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


# --------------------------------------------------------------------------
#   The status the phone polls
# --------------------------------------------------------------------------

def status(*, state: Optional[dict] = None,
           installed_now: Optional[Callable[[], dict]] = None,
           published_now: Optional[Callable[[], dict]] = None,
           tier_of: Optional[Callable[[str], str]] = None,
           backend: Optional[Callable[[], Optional[Path]]] = None,
           script: Optional[Callable[[], Optional[Path]]] = None) -> dict:
    """GET /api/update/status. Read-only: no card, no write, no download.

    Answers, in plain words: what version is installed, what version is
    published ("cannot tell: ..." when it cannot be read), and the phase of any
    update in flight or just finished. `can_request` and `why_not` are the same
    answers `request()` would give, so a screen can grey the button out with the
    reason already on it instead of finding out on the tap.
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

    out = {
        "available": True,
        "installed": here_version,
        "installed_why": str(here.get("why") or ""),
        "published": there_version,
        "published_why": str(there.get("why") or ""),
        "newer": newer,
        "phase": FAILED if dead else phase,
        "what": PHASE_WORDS.get(FAILED if dead else phase, PHASE_WORDS[IDLE]),
        "running": live,
        "can_request": False,
        "why_not": "",
        "started_at": st.get("started_at"),
        "updated_at": st.get("updated_at"),
        "finished_at": st.get("finished_at"),
        "from": st.get("from"),
        "to": st.get("to"),
    }
    with _LOCK:
        pending = _PENDING
        if pending is not None:
            out["waiting_for_approval"] = True
            out["expires_in"] = max(0, int(_left_s(pending)))
            out["to"] = pending.get("to")
        else:
            out["waiting_for_approval"] = False
        if _LAST is not None:
            out["last"] = {k: _LAST.get(k) for k in
                           ("outcome", "at", "reason", "request_id") if _LAST.get(k) is not None}

    # The same refusals request() would give, so the button and its reason agree.
    if live:
        out["why_not"] = "an update is already running on the PC"
    elif dead:
        out["why_not"] = str(st.get("reason") or "the update stopped without finishing")
    elif out["waiting_for_approval"]:
        out["why_not"] = "the card is waiting for you to approve or deny it"
    elif backend() is None:
        out["why_not"] = "the Jarvis backend folder could not be found on this PC"
    elif script() is None:
        out["why_not"] = "the folder this repository is cloned into could not be found"
    else:
        busy = desktop_lock_words()
        if busy:
            out["why_not"] = f"an update is already running: {busy}"
        elif newer is None:
            out["why_not"] = (str(here.get("why") or "") or str(there.get("why") or "")
                              or "the two versions could not be compared")
        elif not newer:
            out["why_not"] = "there is nothing newer to install"
        else:
            try:
                tier = tier_of(ACTION)
            except Exception as exc:                    # noqa: BLE001
                tier = f"unreadable ({type(exc).__name__})"
            if tier != "ask":
                out["why_not"] = (f"{ACTION} is tier {tier!r} in jarvis-framework.toml; "
                                  "updating Jarvis needs a person to say yes")
            else:
                out["can_request"] = True
    return out


# --------------------------------------------------------------------------
#   The two routes - a drop-in, so there is no patch and no core change
# --------------------------------------------------------------------------
#
# WHY A DROP-IN RATHER THAN A PATCH. `jarvis_hud.py` is not a shipped module; it
# is delivered by the patch stack, so a new route normally costs a patch - and a
# patch costs the whole ordering bookkeeping (every suite that enumerates "the
# patches written after me", `plugins/registry.json`, `_stack.py`'s ratchet and
# `plugin-loader.patch` having to stay last of all). The loader exists for
# exactly this case: `plugins/ready/update/plugin.json` names this module and
# `jarvis_plugins.install()` makes the call a patch would have made, which is
# the same route `plugins/ready/read-aloud` and `plugins/ready/antislop` take.
# So the two routes are added by wrapping the handler here, and the core file is
# untouched. On the PC the folder is copied in by `scripts/add-plugin.ps1`
# (or the deploy tool's ready-plug-in step), the same way every other drop-in
# feature arrives.

#: The read-only route: versions and phase.
STATUS_PATH = "/api/update/status"
#: The one write: raise the card. Nothing starts until it is approved.
REQUEST_PATH = "/api/update/request"


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls.do_GET`/`do_POST` so this module answers its own routes.

    Every other request goes straight to the original, untouched - the same
    shape `jarvis_read_aloud.install()` uses. Both routes do their own origin
    and token check, because they never reach the core's dispatch; a refusal is
    the same 403/401 body every other route sends, so a client sees one rule
    and not two.
    """
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(get0, "_jarvis_update", False):
        return "update       update Jarvis from the phone (already on)"

    from urllib.parse import urlsplit

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
