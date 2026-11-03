"""jarvis_storage_health.py - what is on this PC, and what can safely be cleared.

    python backend/test_storage_health.py       # proves every rule below

THE OWNER'S ASK (2026-11-03)

    "I would also like the ability for jarvis to selfscan it's ... take
    inventory of storage and to see if it can clear any temporary files up
    safely also refresh its function and capabilities awareness."

So this module does three things, and refuses to do a fourth:

  1. `scan()` - a bounded inventory: the disks, the folders Jarvis itself uses,
     and a CANDIDATE list of things that look temporary (Python cache, Jarvis's
     own logs, old deploy snapshots and .before-/.backup-/.old- copies, and
     temporary files it made in %TEMP%), each with exact bytes, file counts and
     oldest/newest times. It also names the build caches it will NOT touch
     (node_modules, target, build, out, dist, .gradle) as "regenerable, slow to
     rebuild". It never follows a symlink, junction or other reparse point: it
     skips them and says so in `notes`.
  2. `plan_cleanup()` - a DRY RUN. It builds the exact list of absolute paths
     from a short, explicit allowlist, and touches nothing. Every item is
     re-checked against `check_path()` before it is planned. It refuses
     anything outside the live Jarvis folder, the repository and %TEMP%; all of
     `~/.openjarvis` (memory, chat history, approvals, receipts, the voiceprint
     and projects); anything the repository tracks in git; the Downloads
     folder; and the live program's own files. A `.pyc` under a `__pycache__`
     is the only thing defaulted in; logs and old deploy snapshots are offered
     but never planned unless the owner asks for them by name.
  3. `apply_cleanup(categories, confirm_token)` - the execution half. It
     refuses to run without the exact confirmation token minted by the plan
     that a person approved, and it is single-use. Before every deletion it
     re-scans the item and stops the whole run at the first item that changed,
     vanished, became a link or stopped looking like what was planned; a file
     another program has open is SKIPPED and counted, never forced. Pycache
     and %TEMP% files are DELETED. Logs and old deploy snapshots are MOVED -
     never deleted - into `<CONFIG_DIR>\\storage-quarantine\\jarvis-quarantine-
     <date>` (`JARVIS_STORAGE_QUARANTINE` overrides the folder), which is the
     same shape jarvis_skills.py already uses for `skills-quarantine`: a
     config folder OUTSIDE the live tree and outside every cleanup root, so
     the next scan can never plan to delete its own quarantine, and a move is
     a same-disk rename, never a copy across disks. One `_why-quarantined.json`
     in each run folder says why every item is there.

THE RULES THIS FOLLOWS (the 2026-11-03 storage prior-art research,
`.dsh-scratch/F6-2026-11-03/STORAGE-RESEARCH.md`)

  * The default category is only Python cache, and Jarvis's own %TEMP%
    leftovers are age-gated: at least 7 days old on BOTH the creation time and
    the modification time (Windows copies preserve the modified time, so an
    old mtime alone would delete a file copied a minute ago).
  * Private stores are on a DENYLIST, always: nothing under `~/.openjarvis`
    (memory, chat history, approvals, receipts, the voiceprint, projects,
    backups) is ever deleted or moved, because that would bypass Forget and
    the receipts' "cannot be undone" promise.
  * Each item is re-validated at delete time: canonical path still under the
    allowlisted root, NOT a reparse point (junction / OneDrive placeholder /
    symlink), same size, same created time and same modified time as the
    plan - anything changed after the plan began is left alone.
  * Package-manager caches (pip/npm/cargo) are only ever removed by their own
    purge commands, so they are not this module's business; build caches
    (node_modules, target, build, out, dist, .gradle) are reported as
    regenerable and never planned; Ollama models, encrypted backups, the
    owner's backup folder, .git, synced folders, Windows/Program Files, the
    Recycle Bin, browser profiles and the HuggingFace/PyTorch caches are never
    candidates (most are unreachable because the roots are this PC's Jarvis
    folders, and `check_path()` refuses the rest in words).
  * One approval card, one plan, one run. There is no bulk card and no
    recurring/automatic cleanup in version 1 - the research calls that an open
    owner decision, so it is deliberately left out.

THE ONE APPROVAL CARD

`request_apply()` is the POST half: it builds a fresh plan, refuses any tier but
"ask" (the same rule jarvis_forget_range.py applies to its own action), and
raises ONE approval card through `jarvis_gate.check(action="storage_cleanup")`.
The card names the folders it looked at, the categories and counts and bytes,
lists every path in full, and says what saying no costs, because a card that
summarises the thing it authorises is not a card. Nothing is deleted or moved
unless a person answers yes; denial, timeout or a refused gate changes nothing.
One plan is in flight at a time (409 while one waits), and the plan expires
after 15 minutes.

WHAT THIS MODULE NEVER DOES

  * No network, no socket, no subprocess except a read-only `git ls-files`
    used to refuse tracked files, and no elevation.
  * No writes at import time. Its only writes are the deletions and moves a
    person approved.
  * It never deletes a file the plan did not name, and never touches the
    owner's data: the tests prove the user-data folder is byte-identical
    before and after a cleanup.

WHY NOT `jarvis_storage.py`

`jarvis_storage.py` (2026-10-10) answers "can this PC hold another model?" -
tiers, free space, the download gate. This module answers "what is on this PC
and what temporary files are safe to clear?" They do not overlap, and this one
imports nothing from the other.

Standard library only.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import stat as _stat
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import parse_qs

#: The one shape this answer has. A client that does not know a newer number
#: ignores what it does not understand instead of guessing.
SCHEMA = "jarvis-storage-health/1"

#: Read the inventory, and the dry-run plan.
SCAN_PATH = "/api/storage/scan"
PLAN_PATH = "/api/storage/cleanup/plan"
#: The POST that raises ONE approval card and, only on a person's yes, runs it.
APPLY_PATH = "/api/storage/cleanup"

#: Every route `install()`-style wiring has to answer. A path not in here goes
#: straight to the server's own handler, so this module cannot shadow one.
GET_ROUTES = (SCAN_PATH, PLAN_PATH)
POST_ROUTES = (APPLY_PATH,)
#: The same routes as rows a wiring worker can read without guessing: method,
#: path, and which function answers it.
ROUTES = (
    {"method": "GET", "path": SCAN_PATH, "handler": "handle_get",
     "what": "inventory of storage and the cleanup candidates"},
    {"method": "GET", "path": PLAN_PATH, "handler": "handle_get",
     "what": "dry-run cleanup plan for ?categories= (default: pycache)"},
    {"method": "POST", "path": APPLY_PATH, "handler": "handle_post",
     "what": "raise ONE approval card for the plan; only a person's yes runs it"},
)

#: The gate action the cleanup card is raised under. It must be tier "ask" in
#: jarvis-framework.toml; any other tier is refused rather than obeyed, the
#: same rule jarvis_forget_range.py and jarvis_self_portrait.py apply.
CLEANUP_ACTION = "storage_cleanup"

#: The tool names the model gets, in jarvis_asks_first.TOOL_GROUPS' own shape:
#: (group title, (tool names...)). The wiring worker adds this row to
#: TOOL_GROUPS and the two names to HARD_LIMITS / MUST_ASK (a cleanup is
#: deletion, so it must never be loosened from an app).
TOOL_ROWS = (
    ("Storage and space", ("storage_scan", "storage_cleanup")),
)

# ---------------------------------------------------------------------------
#   The four folders this module knows about
# ---------------------------------------------------------------------------

LIVE = "live"
REPO = "repo"
USERDATA = "userdata"
OLLAMA = "ollama"
TEMP = "temp"

#: Environment overrides. Tests hand `roots=` instead; these exist so a person
#: or another module can point the scan somewhere without editing code.
ENV_LIVE = "JARVIS_STORAGE_LIVE_DIR"
ENV_REPO = "JARVIS_STORAGE_REPO_DIR"
ENV_USERDATA = "JARVIS_STORAGE_USERDATA_DIR"
ENV_OLLAMA = "JARVIS_STORAGE_OLLAMA_DIR"
ENV_TEMP = "JARVIS_STORAGE_TEMP_DIR"

#: The folders a candidate may live under, per category. This is the whole
#: allowlist: nothing outside these is ever planned.
ALLOWED_FOR = {
    "pycache": (LIVE, REPO),
    "logs": (LIVE,),
    "old_deploy_snapshots": (LIVE,),
    "temp_files": (TEMP,),
}

# ---------------------------------------------------------------------------
#   The candidate categories
# ---------------------------------------------------------------------------

#: `default` means "planned when the caller names no categories". Only Python
#: cache is safe enough to be the default; the other two are offered, never
#: assumed. `action` is what apply does with an item: "delete" frees the bytes,
#: "quarantine" moves them aside so they can be put back by hand.
CATEGORY_INFO = {
    "pycache": {
        "label": "Python cache files (__pycache__ folders and .pyc files)",
        "action": "delete",
        "default": True,
        "plain": "Python writes these so imports are faster. They rebuild by "
                 "themselves the next time Jarvis runs, so deleting them is safe.",
    },
    "logs": {
        "label": "Jarvis's own log files (_jarvis-logs)",
        "action": "quarantine",
        "default": False,
        "plain": "Jarvis's own records of what it did. They are moved into a "
                 "quarantine folder, never deleted, so you can look at them first.",
    },
    "old_deploy_snapshots": {
        "label": "Old deploy backups and .before- / .backup- / .old- copies",
        "action": "quarantine",
        "default": False,
        "plain": "Copies an update left behind. They are moved into a quarantine "
                 "folder, never deleted, so you can look at them first.",
    },
    "temp_files": {
        "label": "Temporary files Jarvis made in %TEMP%",
        "action": "delete",
        "default": False,
        "plain": "Scratch files with Jarvis's own prefixes (jarvis-, f6-, "
                 "openjarvis-). Nothing else in %TEMP% is touched.",
    },
}
ALL_CATEGORIES = tuple(CATEGORY_INFO)
#: Only Python cache is planned when the caller names no categories (the
#: owner's rule: propose the others, never default them).
DEFAULT_CATEGORIES = tuple(c for c in ALL_CATEGORIES if CATEGORY_INFO[c]["default"])

#: The name of the folder old logs and snapshots are moved into. The date is
#: the day the move happens, so two runs on two days never mix. The base is a
#: config folder OUTSIDE the live program tree and outside every cleanup
#: candidate root, so the next scan can never plan to delete its own quarantine
#: (the pattern backend/jarvis_skills.py already uses for `skills-quarantine`).
QUARANTINE_PREFIX = "_jarvis-quarantine-"
QUARANTINE_DIRNAME = "storage-quarantine"
QUARANTINE_ENV = "JARVIS_STORAGE_QUARANTINE"
#: One small file inside a quarantine run, saying why each item was moved
#: instead of deleted - the `_why-refused.json` shape jarvis_skills.py uses.
QUARANTINE_WHY = "_why-quarantined.json"
#: Jarvis's own %TEMP% leftovers must be at least this old on BOTH their
#: creation time and their modification time: Windows copies preserve the
#: modified time, so "old mtime" alone would delete a file copied seconds ago.
TEMP_MIN_AGE_SECONDS = 7 * 24 * 60 * 60
#: Never clear anything whose path has one of these components (besides the
#: ~/.openjarvis check below, which uses the real path rather than a name).
DENY_PARTS = frozenset({
    ".openjarvis", ".git", "onedrive", "$recycle.bin",
    "program files", "program files (x86)",
})

#: A file an update left behind. Deliberately narrow: `.bak` files are NOT
#: here, because a `.bak` may be the only copy of something.
_SNAPSHOT_FILE = re.compile(r"(?:\.before-[^\\/]*|\.backup-[^\\/]*|\.old-[^\\/]*|\.old)$",
                            re.IGNORECASE)
#: Directory names an update left behind.
_SNAPSHOT_DIR = re.compile(r"^_jarvis-deploy-backup-")
#: Prefixes of throw-away files and folders Jarvis itself makes in %TEMP%.
_TEMP_PREFIXES = ("jarvis-", "f6-", "openjarvis-")
#: Build output. Reported as regenerable, never planned (rebuilding can take
#: tens of minutes, so it is the owner's call, not a "temporary file").
BUILD_CACHE_NAMES = ("node_modules", "target", "build", "out", "dist", ".gradle")

#: Folders skipped by the general walk of a root. `.git` and `.dsh-scratch` are
#: huge and are not Jarvis's own files; the build caches are counted separately
#: as regenerable. The skipped names are said out loud in `notes`.
REPO_WALK_SKIP = (".git", ".dsh-scratch") + BUILD_CACHE_NAMES

#: How much walking one scan may do before it says it stopped. A scan is not a
#: walk of a whole disk: the counts are exact for what fits the budget and
#: `bounded` says when one did not.
MAX_WALK_ENTRIES = 20000
MAX_WALK_SECONDS = 1.5
MAX_ROOT_DEPTH = 6
MAX_PYCACHE_DEPTH = 4
MAX_TOP_SUBFOLDERS = 5
MAX_TOP_SUBFOLDER_SCAN = 40
TOP_SUBFOLDER_SECONDS = 0.8
MAX_TEMP_DIR_FILES = 2000
MAX_PLAN_ITEMS = 60
MAX_BUILD_CACHES = 12

#: One plan may be carried out within this window; after that the owner plans
#: again (the card and the paths may be stale).
PLAN_TTL_SECONDS = 900
#: How long a built inventory is reused. The scan is bounded, but a HUD that
#: reads it on a timer should not walk the folders every second.
SCAN_TTL_SECONDS = 30

MB = 1024 ** 2
GB = 1024 ** 3

#: The per-process secret a plan token is signed with. It is never written down
#: and never leaves this process: a token cannot be replayed after a restart.
_SECRET = secrets.token_hex(16)

#: One plan at a time, and the last outcome - for the route and the suites.
_LOCK = threading.Lock()
_PENDING: dict = {"plan": None}
_LAST: dict = {"result": None}
_SCAN_CACHE: dict = {"at": 0.0, "inventory": None}

#: A link or junction: Windows marks it with a reparse attribute, POSIX with a
#: symlink mode. Either way this module skips it rather than following it.
_REPARSE_ATTR = getattr(_stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


def _now() -> float:
    """This module's clock, so the tests can fix it."""
    return time.time()


def _env_path(name: str) -> Optional[Path]:
    raw = os.environ.get(name)
    if not raw or not str(raw).strip():
        return None
    try:
        return Path(str(raw).strip())
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------------------
#   Which folders exist on this PC
# ---------------------------------------------------------------------------

def live_dir() -> Optional[Path]:
    """The folder Jarvis's own program runs from, or None.

    When this module is deployed it sits in that folder beside jarvis_hud.py;
    in the repository it sits in backend/, so the running jarvis_hud module
    (when there is one) names the folder instead. Nothing is guessed: an
    unknown folder is None and every live category then says why it is empty.
    """
    env = _env_path(ENV_LIVE)
    if env is not None:
        return env
    here = Path(__file__).resolve().parent
    if (here / "jarvis_hud.py").is_file():
        return here
    hud = sys.modules.get("jarvis_hud")
    hud_file = getattr(hud, "__file__", None)
    if hud_file:
        try:
            return Path(hud_file).resolve().parent
        except (OSError, ValueError):
            return None
    return None


def repo_dir() -> Optional[Path]:
    """The repository checkout, or None (a deployed backend has no repo)."""
    env = _env_path(ENV_REPO)
    if env is not None:
        return env
    here = Path(__file__).resolve().parent
    parent = here.parent
    if (here / "_where.py").is_file() and (parent / "jarvis-backend").is_dir():
        return parent
    return None


def userdata_dir() -> Path:
    """Where the owner's saved data lives: `~/.openjarvis` (the documented
    default). Never scanned for cleanup candidates; named so it can be refused."""
    env = _env_path(ENV_USERDATA)
    if env is not None:
        return env
    return Path.home() / ".openjarvis"


def ollama_dir() -> Optional[Path]:
    """Ollama's model store, when it is there (models are never candidates)."""
    env = _env_path(ENV_OLLAMA)
    if env is not None:
        return env
    folder = Path.home() / ".ollama" / "models"
    return folder if folder.is_dir() else None


def temp_dir() -> Optional[Path]:
    """The Windows temporary folder."""
    env = _env_path(ENV_TEMP)
    if env is not None:
        return env
    try:
        return Path(tempfile.gettempdir())
    except OSError:
        return None


def default_roots() -> tuple:
    """The five folders the inventory knows, in the order it reports them."""
    return (
        {"id": LIVE, "label": "Jarvis's own folder", "path": live_dir()},
        {"id": REPO, "label": "The Epic-Jarvis repository", "path": repo_dir()},
        {"id": USERDATA, "label": "Jarvis's saved data (memory, history, receipts)",
         "path": userdata_dir()},
        {"id": OLLAMA, "label": "Ollama's models", "path": ollama_dir()},
        {"id": TEMP, "label": "The Windows temporary folder", "path": temp_dir()},
    )


def _root_list(roots=None) -> list:
    """Normalise caller roots to [{"id","label","path": Path|None}]."""
    raw = default_roots() if roots is None else roots
    out = []
    for i, r in enumerate(raw or ()):
        if isinstance(r, dict):
            path = r.get("path")
            rid = str(r.get("id") or r.get("label") or "root{0}".format(i))
            label = str(r.get("label") or rid)
        else:
            path, rid, label = r, "root{0}".format(i), "root{0}".format(i)
        p = None
        if path is not None:
            try:
                p = Path(path)
            except (OSError, ValueError, TypeError):
                p = None
        out.append({"id": rid, "label": label, "path": p})
    return out


def _roots_map(roots=None) -> dict:
    """{root id: Path} for the roots that have a path."""
    out: dict = {}
    for entry in _root_list(roots):
        if entry["path"] is not None:
            out.setdefault(entry["id"], entry["path"])
    return out


def _root_of(rmap: dict, rid: str) -> Optional[Path]:
    return rmap.get(rid)


# ---------------------------------------------------------------------------
#   Safety: may this exact path ever be cleared?
# ---------------------------------------------------------------------------

def _is_reparse(path) -> bool:
    """True for a symlink, junction or other reparse point - and True when it
    cannot be told, because "cannot tell" must never mean "follow it"."""
    try:
        raw = os.fspath(path)
        st = os.lstat(raw)
    except (OSError, TypeError, ValueError):
        return True
    if getattr(st, "st_file_attributes", 0) & _REPARSE_ATTR:
        return True
    try:
        if _stat.S_ISLNK(st.st_mode) or os.path.islink(raw):
            return True
    except OSError:
        return True
    return False


def _inside(child, root) -> bool:
    """True when `child` resolves inside `root` (the real paths, case folded)."""
    try:
        c = os.path.normcase(os.path.realpath(os.fspath(child)))
        r = os.path.normcase(os.path.realpath(os.fspath(root)))
    except (OSError, TypeError, ValueError):
        return False
    return c == r or c.startswith(r + os.sep)


def _code(value) -> str:
    """A case-folded path for comparisons."""
    return os.path.normcase(os.fspath(value))


def _has_reparse_in_chain(root, path) -> bool:
    """True when any part from `root` down to `path` is a link or junction."""
    try:
        rel = os.path.relpath(os.fspath(path), os.fspath(root))
    except (OSError, ValueError):
        return True
    if rel == "." or rel.startswith(".."):
        return False
    parts = Path(rel).parts
    cursor = os.fspath(root)
    if _is_reparse(cursor):
        return True
    for part in parts:
        cursor = os.path.join(cursor, part)
        if _is_reparse(cursor):
            return True
    return False


def _downloads_dir() -> Optional[Path]:
    try:
        folder = Path.home() / "Downloads"
        return folder if folder.is_dir() else None
    except (OSError, RuntimeError):
        return None


def allowed_roots(category: str, rmap: dict) -> list:
    """The root paths a category may clear under."""
    return [rmap[rid] for rid in ALLOWED_FOR.get(str(category), ()) if rid in rmap]


def check_path(path, roots=None, *, category=None) -> tuple:
    """(may it be cleared, or why not) - the one safety question.

    Every path is re-asked this question when it is planned AND again when it
    is deleted or moved. The hard refusals come first and cannot be undone by
    passing a root in: `~/.openjarvis` (memory, chat history, approvals,
    receipts, the voiceprint, projects), the Downloads folder, a relative path,
    a `..` step, a link or junction anywhere between the root and the file, or
    a path outside the allowlisted folders for its category.
    """
    if path is None or not str(path).strip():
        return False, "there is no path to check"
    try:
        raw = os.fspath(path)
    except TypeError:
        return False, "that is not a file path"
    if not os.path.isabs(raw):
        return False, "only an absolute path is ever cleared"
    if ".." in Path(raw).parts:
        return False, "a path with a '..' step in it is never cleared"
    try:
        norm = os.path.normpath(raw)
    except (OSError, ValueError):
        return False, "that path cannot be read"
    if ".." in Path(norm).parts:
        return False, "a path with a '..' step in it is never cleared"
    for part in Path(norm).parts:
        if str(part).lower() in DENY_PARTS:
            return False, "that path is in a place Jarvis never clears ({0})".format(part)

    rmap = _roots_map(roots)
    userdata = rmap.get(USERDATA) or userdata_dir()
    if _inside(norm, userdata):
        return False, ("Jarvis's saved data folder holds your memory, chat history, "
                       "approvals, receipts and voiceprint, and is never cleared")
    downloads = _downloads_dir()
    if downloads is not None and _inside(norm, downloads):
        return False, "the Downloads folder holds your own files, so it is never cleared"

    candidates = allowed_roots(category, rmap) if category else [p for p in rmap.values()]
    candidates = [c for c in candidates if _inside(norm, c)]
    if not candidates:
        return False, "that is outside the folders Jarvis is allowed to clean"
    root = candidates[0]
    if _has_reparse_in_chain(root, norm):
        return False, "a link or junction is in the way, so it is not safe to clear"
    if _is_reparse(norm):
        return False, "a link or junction is in the way, so it is not safe to clear"
    if not os.path.exists(norm):
        return False, "it is not there any more"
    return True, ""


def _shape_ok(category: str, path) -> bool:
    """The allowlist's shape: a path is only a candidate if it LOOKS like one.

    This is checked when the plan is built and again when it is carried out, so
    even a plan object that was tampered with cannot name the owner's files.
    """
    name = os.path.basename(os.path.normpath(os.fspath(path)))
    try:
        is_dir = os.path.isdir(path) and not _is_reparse(path)
    except OSError:
        is_dir = False
    if category == "pycache":
        if is_dir:
            return name == "__pycache__"
        return bool(re.match(r"^.+\.py[co]$", name, re.IGNORECASE))
    if category == "logs":
        return is_dir and name == "_jarvis-logs"
    if category == "old_deploy_snapshots":
        if is_dir:
            return bool(_SNAPSHOT_DIR.search(name))
        return (not _is_reparse(path)) and bool(_SNAPSHOT_FILE.search(name))
    if category == "temp_files":
        return any(name.startswith(prefix) for prefix in _TEMP_PREFIXES)
    return False


# ---------------------------------------------------------------------------
#   Reading: a bounded walk, never following a link
# ---------------------------------------------------------------------------

def _walk(root, *, max_depth=MAX_ROOT_DEPTH, max_entries=MAX_WALK_ENTRIES,
          max_seconds=MAX_WALK_SECONDS, skip_names=()) -> dict:
    """Count files/bytes under `root` without following a reparse point.

    Returns the counts, the oldest and newest mtime seen, how many links were
    skipped, how many folders could not be read, and `bounded`: True when the
    budget stopped the walk early, so a caller never presents a truncated count
    as exact.
    """
    stats = {"files": 0, "bytes": 0, "newest_ns": 0, "oldest_ns": 0,
             "skipped_reparse": 0, "unreadable": 0, "bounded": False}
    try:
        start = os.fspath(root)
    except TypeError:
        return stats
    deadline = time.monotonic() + max(0.05, float(max_seconds))
    stack = [(start, 0)]
    seen = 0
    while stack:
        if time.monotonic() > deadline or seen > max_entries:
            stats["bounded"] = True
            break
        folder, depth = stack.pop()
        try:
            entries = list(os.scandir(folder))
        except OSError:
            stats["unreadable"] += 1
            continue
        for entry in entries:
            seen += 1
            if seen > max_entries:
                stats["bounded"] = True
                break
            try:
                if _is_reparse(entry.path):
                    stats["skipped_reparse"] += 1
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if entry.name in skip_names:
                        continue
                    if depth + 1 <= max_depth:
                        stack.append((entry.path, depth + 1))
                elif entry.is_file(follow_symlinks=False):
                    st = entry.stat(follow_symlinks=False)
                    ns = int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9)))
                    stats["files"] += 1
                    stats["bytes"] += int(st.st_size)
                    if ns and (not stats["oldest_ns"] or ns < stats["oldest_ns"]):
                        stats["oldest_ns"] = ns
                    if ns > stats["newest_ns"]:
                        stats["newest_ns"] = ns
            except OSError:
                stats["unreadable"] += 1
    return stats


def _iso(ns: int) -> Optional[str]:
    if not ns:
        return None
    try:
        return datetime.fromtimestamp(ns / 1e9, tz=timezone.utc).isoformat(timespec="seconds")
    except (OSError, OverflowError, ValueError):
        return None


def _size(num) -> str:
    """Bytes in plain words the owner reads."""
    try:
        n = float(num or 0)
    except (TypeError, ValueError):
        n = 0.0
    if n >= GB:
        return "{0:.1f} GB".format(n / GB)
    if n >= MB:
        return "{0:.1f} MB".format(n / MB)
    if n >= 1024:
        return "{0:.0f} KB".format(n / 1024)
    return "{0} bytes".format(int(n))


def _snapshot_item(path, kind: str) -> dict:
    """The bytes, file count, created/modified times of one candidate.

    `newest_ns` is the newest modification time inside the item; `created_ns`
    is its own creation time on Windows (the change time elsewhere). Both are
    kept because the age rules need both: a copied file can carry an old
    modification time and still have just been created.
    """
    if kind == "file":
        try:
            st = os.stat(path)
            ns = int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9)))
            created = int(getattr(st, "st_ctime_ns", int(st.st_ctime * 1e9)))
            size = int(st.st_size)
        except OSError:
            ns, created, size = 0, 0, 0
        return {"files": 1, "bytes": size, "newest_ns": ns, "oldest_ns": ns,
                "created_ns": created}
    stats = _walk(path, max_depth=6, max_entries=MAX_TEMP_DIR_FILES,
                  max_seconds=0.5)
    try:
        st = os.stat(path)
        created = int(getattr(st, "st_ctime_ns", int(st.st_ctime * 1e9)))
    except OSError:
        created = 0
    return {"files": stats["files"], "bytes": stats["bytes"],
            "newest_ns": stats["newest_ns"], "oldest_ns": stats["oldest_ns"],
            "created_ns": created, "bounded": stats["bounded"]}


def _item(path, category: str, action: str) -> dict:
    """One candidate, with its exact numbers."""
    norm = os.path.normpath(os.fspath(path))
    kind = "dir" if os.path.isdir(norm) and not _is_reparse(norm) else "file"
    snap = _snapshot_item(norm, kind)
    return {
        "path": norm,
        "name": os.path.basename(norm),
        "category": category,
        "action": action,
        "kind": kind,
        "bytes": int(snap.get("bytes") or 0),
        "file_count": int(snap.get("files") or 0),
        "oldest": _iso(int(snap.get("oldest_ns") or 0)),
        "newest": _iso(int(snap.get("newest_ns") or 0)),
        "created": _iso(int(snap.get("created_ns") or 0)),
        "bounded": bool(snap.get("bounded")),
        "check": {"files": int(snap.get("files") or 0),
                  "bytes": int(snap.get("bytes") or 0),
                  "newest_ns": int(snap.get("newest_ns") or 0),
                  "created_ns": int(snap.get("created_ns") or 0)},
    }


# ---------------------------------------------------------------------------
#   Finding the candidates (bounded, and nothing outside the allowlist)
# ---------------------------------------------------------------------------

def _find_pycache(root, out: list, unsafe: list, skip_names=()) -> None:
    """Every `__pycache__` folder and loose `.pyc` under `root`, bounded.

    A __pycache__ folder is reported whole (one item); a .pyc outside one is its
    own item. A link is named as not-safe instead of followed. The repository
    walk skips `.git`, `.dsh-scratch` and the build caches, and stops at a time
    and directory budget, so this is never a walk of the whole checkout.
    """
    try:
        start = os.fspath(root)
    except TypeError:
        return
    deadline = time.monotonic() + MAX_WALK_SECONDS
    stack = [(start, 0)]
    seen = 0
    while stack and seen < MAX_WALK_ENTRIES and time.monotonic() <= deadline:
        folder, depth = stack.pop()
        try:
            entries = list(os.scandir(folder))
        except OSError:
            continue
        for entry in entries:
            seen += 1
            if seen > MAX_WALK_ENTRIES:
                break
            try:
                if _is_reparse(entry.path):
                    unsafe.append({"path": entry.path,
                                   "why": "a link or junction - Jarvis never follows one"})
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if entry.name == "__pycache__":
                        out.append(entry.path)
                        continue
                    if entry.name in skip_names:
                        continue
                    if depth + 1 <= MAX_PYCACHE_DEPTH:
                        stack.append((entry.path, depth + 1))
                elif entry.is_file(follow_symlinks=False):
                    if entry.name.lower().endswith((".pyc", ".pyo")):
                        parent = os.path.basename(folder)
                        if parent != "__pycache__":
                            out.append(entry.path)
            except OSError:
                continue


def _find_snapshot_items(live: Path, out: list) -> None:
    """Old deploy backups and .before-/.backup-/.old- copies at the top of the
    live folder. Top level only: a file further down is the owner's business."""
    try:
        entries = list(os.scandir(live))
    except OSError:
        return
    for entry in entries:
        try:
            if _is_reparse(entry.path):
                continue
            if entry.is_dir(follow_symlinks=False):
                if _SNAPSHOT_DIR.search(entry.name):
                    out.append(entry.path)
            elif entry.is_file(follow_symlinks=False):
                if _SNAPSHOT_FILE.search(entry.name):
                    out.append(entry.path)
        except OSError:
            continue


def _no_reparse_inside(path, *, max_entries=400, max_seconds=0.15) -> bool:
    """True when nothing under `path` is a link or junction (bounded).

    A folder too large to check inside that budget answers False: "not safe to
    clear automatically" is the right answer when the check could not finish,
    and the item is reported in `not_safe_to_clear` instead of skipped.
    """
    try:
        start = os.fspath(path)
    except TypeError:
        return False
    deadline = time.monotonic() + max(0.02, float(max_seconds))
    seen = 0
    stack = [start]
    while stack:
        if time.monotonic() > deadline or seen > max_entries:
            return False
        folder = stack.pop()
        try:
            entries = list(os.scandir(folder))
        except OSError:
            return False
        for entry in entries:
            seen += 1
            if seen > max_entries:
                return False
            if _is_reparse(entry.path):
                return False
            try:
                if entry.is_dir(follow_symlinks=False):
                    stack.append(entry.path)
            except OSError:
                return False
    return True


def _find_temp_items(temp: Path, out: list, unsafe: list) -> None:
    """Files/folders Jarvis itself made in %TEMP%: the three fixed prefixes."""
    try:
        entries = list(os.scandir(temp))
    except OSError:
        return
    for entry in entries:
        if not any(str(entry.name).startswith(prefix) for prefix in _TEMP_PREFIXES):
            continue
        try:
            if _is_reparse(entry.path):
                unsafe.append({"path": entry.path,
                               "why": "a link or junction - Jarvis never follows one"})
                continue
            if entry.is_dir(follow_symlinks=False):
                if not _no_reparse_inside(entry.path):
                    unsafe.append({"path": entry.path,
                                   "why": "the folder holds a link or junction, so it is not safe to clear"})
                    continue
                out.append(entry.path)
            elif entry.is_file(follow_symlinks=False):
                out.append(entry.path)
        except OSError:
            continue


def candidates(roots=None) -> dict:
    """The candidate categories, each with exact counts, bytes and items."""
    rmap = _roots_map(roots)
    live, repo, temp = rmap.get(LIVE), rmap.get(REPO), rmap.get(TEMP)
    found: dict = {cat: [] for cat in ALL_CATEGORIES}
    unsafe: list = []
    if live is not None:
        _find_pycache(live, found["pycache"], unsafe)
        logs = live / "_jarvis-logs"
        try:
            if logs.is_dir() and not _is_reparse(logs):
                found["logs"].append(logs)
        except OSError:
            pass
        _find_snapshot_items(live, found["old_deploy_snapshots"])
    if repo is not None:
        _find_pycache(repo, found["pycache"], unsafe, skip_names=REPO_WALK_SKIP)
    if temp is not None:
        _find_temp_items(temp, found["temp_files"], unsafe)

    out: dict = {}
    seen_paths = set()
    for cat in ALL_CATEGORIES:
        info = CATEGORY_INFO[cat]
        items = []
        for path in sorted(found[cat], key=lambda p: (str(p).lower())):
            key = _code(path)
            if key in seen_paths:
                continue
            seen_paths.add(key)
            try:
                items.append(_item(path, cat, info["action"]))
            except (OSError, ValueError):
                continue
        out[cat] = {
            "category": cat,
            "label": info["label"],
            "plain": info["plain"],
            "action": info["action"],
            "default": bool(info["default"]),
            "count": len(items),
            "bytes": sum(i["bytes"] for i in items),
            "bounded": any(i.get("bounded") for i in items),
            "oldest": min((i["oldest"] for i in items if i["oldest"]), default=None),
            "newest": max((i["newest"] for i in items if i["newest"]), default=None),
            "items": items,
        }
    out["_unsafe"] = unsafe
    return out


# ---------------------------------------------------------------------------
#   The scan: what is on this PC
# ---------------------------------------------------------------------------

def _top_subfolders(root, skip_names=(), *, budget_seconds=TOP_SUBFOLDER_SECONDS,
                    max_children=MAX_TOP_SUBFOLDER_SCAN) -> tuple:
    """(the biggest first-level folders, whether the list had to be cut short).

    Bounded on purpose: each child gets a small slice and the whole list a
    shared budget, so a %TEMP% holding hundreds of folders does not turn the
    scan into a walk of all of them. The caller says `top_subfolders_bounded`
    rather than presenting a partial list as complete.
    """
    try:
        children = [e for e in os.scandir(root)
                    if not _is_reparse(e.path)
                    and e.is_dir(follow_symlinks=False)
                    and e.name not in skip_names]
    except OSError:
        return [], True
    children.sort(key=lambda e: e.name.lower())
    deadline = time.monotonic() + max(0.05, float(budget_seconds))
    bounded = len(children) > max_children
    subs = []
    for child in children[:max_children]:
        if time.monotonic() > deadline:
            bounded = True
            break
        try:
            sub = _walk(child.path, max_depth=3, max_entries=1000, max_seconds=0.12,
                        skip_names=skip_names)
            subs.append({"name": child.name, "bytes": sub["bytes"],
                         "files": sub["files"], "bounded": sub["bounded"]})
        except OSError:
            bounded = True
    subs.sort(key=lambda s: (-s["bytes"], s["name"].lower()))
    return subs[:MAX_TOP_SUBFOLDERS], bounded


def _scan_root(entry: dict) -> dict:
    path = entry["path"]
    out = {"id": entry["id"], "label": entry["label"],
           "path": None if path is None else os.fspath(path),
           "exists": False, "files": 0, "bytes": 0, "top_subfolders": [],
           "top_subfolders_bounded": False,
           "oldest": None, "newest": None, "bounded": False,
           "skipped_reparse": 0, "unreadable": 0, "why_not": ""}
    if path is None:
        out["why_not"] = "this folder is not on this PC"
        return out
    try:
        exists = path.is_dir()
    except OSError:
        exists = False
    if not exists:
        out["why_not"] = "this folder is not on this PC"
        return out
    out["exists"] = True
    skip = REPO_WALK_SKIP if entry["id"] == REPO else ()
    stats = _walk(path, skip_names=skip)
    out.update({"files": stats["files"], "bytes": stats["bytes"],
                "oldest": _iso(stats["oldest_ns"]), "newest": _iso(stats["newest_ns"]),
                "bounded": stats["bounded"], "skipped_reparse": stats["skipped_reparse"],
                "unreadable": stats["unreadable"]})
    subs, subs_bounded = _top_subfolders(path, skip)
    out["top_subfolders"] = subs
    out["top_subfolders_bounded"] = subs_bounded
    return out


def _regenerable(repo: Optional[Path]) -> list:
    """Build caches in the repository: named, measured, NEVER planned."""
    if repo is None:
        return []
    found: list = []
    stack = [(os.fspath(repo), 0)]
    while stack and len(found) < MAX_BUILD_CACHES:
        folder, depth = stack.pop(0)
        try:
            entries = list(os.scandir(folder))
        except OSError:
            continue
        for entry in entries:
            try:
                if _is_reparse(entry.path):
                    continue
                if not entry.is_dir(follow_symlinks=False):
                    continue
                if entry.name in BUILD_CACHE_NAMES:
                    stats = _walk(entry.path, max_depth=6, max_entries=6000,
                                  max_seconds=1.0)
                    found.append({
                        "path": os.path.normpath(entry.path),
                        "name": entry.name,
                        "bytes": stats["bytes"],
                        "file_count": stats["files"],
                        "bytes_known": not stats["bounded"],
                        "why": "regenerable, slow to rebuild - Jarvis will not plan to delete it",
                    })
                elif depth < 2 and entry.name not in REPO_WALK_SKIP and entry.name != "__pycache__":
                    stack.append((entry.path, depth + 1))
            except OSError:
                continue
    found.sort(key=lambda f: (-f["bytes"], f["path"].lower()))
    return found[:MAX_BUILD_CACHES]


def _disks(entries: list) -> list:
    """The disks holding the scanned roots: total, free and used."""
    seen: dict = {}
    for entry in entries:
        path = entry["path"]
        if path is None:
            continue
        try:
            if not path.is_dir():
                continue
            anchor = os.path.splitdrive(os.fspath(path))[0] or os.sep
            key = os.path.normcase(anchor)
        except (OSError, ValueError):
            continue
        if key in seen:
            continue
        try:
            usage = shutil.disk_usage(anchor)
        except OSError:
            seen[key] = {"path": anchor, "total_bytes": 0, "free_bytes": 0,
                         "used_bytes": 0, "why_not": "the disk could not be read"}
            continue
        seen[key] = {"path": anchor, "total_bytes": int(usage.total),
                     "free_bytes": int(usage.free), "used_bytes": int(usage.used),
                     "why_not": ""}
    return list(seen.values())


def summary_line(inv: dict) -> str:
    """One plain sentence for a status line or a model's answer."""
    roots = inv.get("roots") or []
    total = 0
    for root in roots:
        try:
            if str(root.get("id")) == TEMP:
                continue
            total += int(root.get("bytes") or 0)
        except (TypeError, ValueError):
            continue
    clearable = 0
    for candidate in (inv.get("candidates") or {}).values():
        if not isinstance(candidate, dict):
            continue
        if candidate.get("action") == "delete":
            try:
                clearable += int(candidate.get("bytes") or 0)
            except (TypeError, ValueError):
                continue
    if clearable <= 0:
        return ("Jarvis is using {0}; nothing it is allowed to clear is temporary "
                "right now.".format(_size(total)))
    return ("Jarvis is using {0}; about {1} of temporary files can be cleared "
            "safely.".format(_size(total), _size(clearable)))


def scan(roots=None, *, now=None, refresh=False) -> dict:
    """The inventory: disks, folders and cleanup candidates - read-only.

    Bounded on purpose: it is a scan, not a walk of the whole disk. A folder
    that hits the budget says `bounded`; a link or junction is skipped and
    counted; nothing is ever followed.
    """
    now = _now() if now is None else float(now)
    if roots is None and not refresh:
        with _LOCK:
            cached = _SCAN_CACHE.get("inventory")
            age = now - float(_SCAN_CACHE.get("at") or 0)
        if cached is not None and 0 <= age <= SCAN_TTL_SECONDS:
            return cached
    entries = _root_list(roots)
    built_roots = [_scan_root(entry) for entry in entries]
    cands = candidates(entries)
    unsafe = list(cands.pop("_unsafe", []) or [])
    build = _regenerable(_roots_map(entries).get(REPO))
    notes = []
    skipped = sum(r["skipped_reparse"] for r in built_roots)
    if skipped:
        notes.append("{0} link(s) or junction(s) were skipped during the scan; "
                     "Jarvis never follows them.".format(skipped))
    bounded = [r["label"] for r in built_roots if r["bounded"]]
    if bounded:
        notes.append("The scan reached its time/size budget in: {0}. Those counts "
                     "are not exact.".format(", ".join(bounded)))
    if any(r["id"] == REPO for r in built_roots):
        notes.append("Repository totals leave out .git, .dsh-scratch and the "
                     "regenerable build caches listed under `regenerable`.")
    if build:
        notes.append("{0} build cache(s) are reported as regenerable and are never "
                     "planned for deletion.".format(len(build)))
    inventory = {
        "schema": SCHEMA,
        "generated_at": _iso(int(now * 1e9)),
        "disks": _disks(entries),
        "roots": built_roots,
        "candidates": cands,
        "regenerable": build,
        "not_safe_to_clear": unsafe,
        "notes": notes,
        "summary": summary_line({"roots": built_roots, "candidates": cands}),
        "wrote_anything": False,
    }
    if roots is None:
        with _LOCK:
            _SCAN_CACHE.update({"at": now, "inventory": inventory})
    return inventory


# ---------------------------------------------------------------------------
#   Planning: the dry run
# ---------------------------------------------------------------------------

#: Set of real paths (normcase) the repository tracks in git, per repo root.
_TRACKED_CACHE: dict = {}


def _tracked_files(repo: Optional[Path]):
    """The paths git tracks in the repository, or None when that cannot be known.

    None means "cannot prove it is not tracked", and the plan then refuses the
    item rather than guessing. A folder that is not a git work tree tracks
    nothing, so it answers an empty set.
    """
    if repo is None:
        return frozenset()
    key = _code(repo)
    if key in _TRACKED_CACHE:
        return _TRACKED_CACHE[key]
    answer = None
    try:
        import subprocess
        try:
            import jarvis_child_env
            child_env = jarvis_child_env.inherited()
        except Exception:                       # noqa: BLE001 - older install
            child_env = {}
        done = subprocess.run(
            ["git", "-C", os.fspath(repo), "ls-files", "-z"],
            capture_output=True, timeout=10, env=child_env)
    except (OSError, ValueError, ImportError):
        done = None
    if done is not None and done.returncode == 0:
        answer = set()
        for raw in (done.stdout or b"").split(b"\0"):
            if not raw:
                continue
            try:
                rel = raw.decode("utf-8", "replace")
            except Exception:                   # noqa: BLE001 - cannot decode
                rel = raw.decode("latin-1", "replace")
            try:
                answer.add(_code(os.path.normpath(os.path.join(os.fspath(repo), rel))))
            except (OSError, ValueError):
                continue
        answer = frozenset(answer)
    elif done is not None and done.returncode == 128:
        # "not a git repository", or a repository git refuses to read: there is
        # no tracked file to protect, so the empty set is the honest answer.
        answer = frozenset()
    _TRACKED_CACHE[key] = answer
    return answer


def _parse_categories(categories) -> list:
    """Normalise a category list; raise ValueError for a name not on the list."""
    if categories is None:
        return list(DEFAULT_CATEGORIES)
    if isinstance(categories, str):
        raw = [c.strip() for c in categories.split(",") if c.strip()]
    elif isinstance(categories, (list, tuple)):
        raw = [str(c).strip() for c in categories if str(c).strip()]
    else:
        raise ValueError("categories must be a list of names, or one comma-separated string")
    unknown = [c for c in raw if c not in ALL_CATEGORIES]
    if unknown:
        raise ValueError("unknown cleanup category {0!r}; the categories are: {1}".format(
            unknown[0], ", ".join(ALL_CATEGORIES)))
    out: list = []
    for c in raw:
        if c not in out:
            out.append(c)
    if not out:
        raise ValueError("choose at least one category")
    return out


def _old_enough(item: dict, now: float, min_age: float) -> tuple:
    """(is it older than `min_age` on BOTH times, or why not).

    Windows copies preserve the modified time, so a file copied a minute ago
    can look a year old. Requiring the creation time as well is what stops
    "old" from meaning "freshly copied".
    """
    check = item.get("check") or {}
    cut = float(now) - float(min_age)
    try:
        created = int(check.get("created_ns") or 0) / 1e9
        newest = int(check.get("newest_ns") or 0) / 1e9
    except (TypeError, ValueError):
        return False, "its age could not be read"
    if created <= 0 or newest <= 0:
        return False, "its age could not be read"
    if created > cut or newest > cut:
        return False, "it is younger than {0} days".format(int(min_age // 86400))
    return True, ""


def _token_for(items: list, categories: list) -> str:
    """A single-use token over the exact plan. Signed in memory only."""
    payload = json.dumps(
        {"categories": list(categories),
         "items": [[i["path"], int(i["bytes"]), int(i["file_count"]),
                    int((i.get("check") or {}).get("newest_ns") or 0),
                    int((i.get("check") or {}).get("created_ns") or 0)] for i in items]},
        sort_keys=True, separators=(",", ":"))
    return hmac.new(_SECRET.encode("ascii"), payload.encode("utf-8"),
                    hashlib.sha256).hexdigest()[:32]


def quarantine_base(rmap: Optional[dict] = None) -> Path:
    """Where a move goes: a config folder, never the live tree.

    `CONFIG_DIR/storage-quarantine` by default (env-overridable with
    JARVIS_STORAGE_QUARANTINE), copied from the pattern jarvis_skills.py
    already uses for `skills-quarantine`. It is deliberately not inside the
    live program folder: a quarantine beside the files it came from would be
    planned for deletion by the next scan, and a deploy would read it as drift.
    """
    env = _env_path(QUARANTINE_ENV)
    if env is not None:
        return env
    rmap = rmap or {}
    return (rmap.get(USERDATA) or userdata_dir()) / QUARANTINE_DIRNAME


def _quarantine_dir(base: Optional[Path], now: float) -> Optional[str]:
    if base is None:
        return None
    try:
        stamp = time.strftime("%Y-%m-%d_%H%M%S", time.localtime(float(now)))
    except (OSError, OverflowError, ValueError):
        stamp = "unknown-date"
    return os.path.normpath(os.path.join(os.fspath(base), QUARANTINE_PREFIX.strip("_") + "-" + stamp))


def _same_volume(a, b) -> bool:
    """True when both paths are on the same disk (a move is a rename, not a copy)."""
    try:
        drive_a = os.path.splitdrive(os.path.abspath(os.fspath(a)))[0]
        drive_b = os.path.splitdrive(os.path.abspath(os.fspath(b)))[0]
    except (OSError, TypeError, ValueError):
        return False
    return os.path.normcase(drive_a) == os.path.normcase(drive_b)


def plan_cleanup(categories=None, roots=None, *, now=None, store: bool = True) -> dict:
    """The DRY RUN: exactly what would be deleted or moved, and nothing else.

    Returns `ok`, the items (absolute paths, bytes, category, action), the
    categories, a single-use `token` (expires in 15 minutes), and `refused`:
    every candidate that failed a safety check, with the reason - "not safe to
    clear automatically" rather than silently dropped. Planning touches
    nothing: there are no writes on this path at all.

    `store=False` makes it a PREVIEW ONLY: no pending plan is left behind, so
    a `GET /api/storage/cleanup/plan` can never block the cleanup card (the
    defect the 2026-11-03 audit reproduced: preview -> POST -> 409 "a cleanup
    card is already waiting", with no card ever raised). Only the real cleanup
    request, through the one card, stores a plan to carry out.
    """
    now = _now() if now is None else float(now)
    cats = _parse_categories(categories)
    entries = _root_list(roots)
    rmap = _roots_map(entries)
    repo = rmap.get(REPO)
    qbase = quarantine_base(rmap)
    found = candidates(entries)
    refused = []
    for uns in found.get("_unsafe", ()) or ():
        refused.append({"path": str(uns.get("path")), "why": str(uns.get("why") or "")})
    tracked = _tracked_files(repo) if repo is not None else frozenset()
    items: list = []
    for cat in cats:
        info = CATEGORY_INFO[cat]
        for raw in (found.get(cat) or {}).get("items", ()):
            path = raw["path"]
            ok, why = check_path(path, entries, category=cat)
            if ok and not _shape_ok(cat, path):
                ok, why = False, "it does not look like a file this category clears"
            if ok and cat == "pycache" and repo is not None and _inside(path, repo):
                if tracked is None:
                    ok, why = False, ("Jarvis cannot prove this repository does not track "
                                      "this file, so it will not clear it")
                elif _code(path) in tracked:
                    ok, why = False, "the repository tracks this file, so it is never cleared"
            if ok and cat == "temp_files":
                ok, why = _old_enough(raw, now, TEMP_MIN_AGE_SECONDS)
            if ok and info["action"] == "quarantine":
                if not _same_volume(path, qbase):
                    ok, why = False, ("the quarantine folder is on another disk; moving "
                                      "across disks copies the bytes, which could fill the "
                                      "disk being cleaned")
            if not ok:
                refused.append({"path": path, "why": why})
                continue
            item = dict(raw)
            item["action"] = info["action"]
            item["category"] = cat
            items.append(item)
    items.sort(key=lambda i: (i["category"], i["path"].lower()))
    total = sum(int(i["bytes"]) for i in items)
    quarantine = (_quarantine_dir(qbase, now)
                  if any(i["action"] == "quarantine" for i in items) else None)
    if len(items) > MAX_PLAN_ITEMS:
        return {"schema": SCHEMA, "ok": False, "dry_run": True,
                "error": ("There are {0} things to clear, which is too many to show on "
                          "one card (at most {1}). Clear one category at a time.").format(
                              len(items), MAX_PLAN_ITEMS),
                "categories": cats, "count": len(items), "bytes": total,
                "items": [], "refused": refused, "token": None,
                "quarantine_dir": quarantine,
                "message": "Nothing has been deleted or moved."}
    token = _token_for(items, cats)
    plan = {
        "schema": SCHEMA,
        "ok": True,
        "dry_run": True,
        "generated_at": _iso(int(now * 1e9)),
        "categories": cats,
        "count": len(items),
        "bytes": total,
        "by_category": {cat: {"count": sum(1 for i in items if i["category"] == cat),
                              "bytes": sum(int(i["bytes"]) for i in items
                                           if i["category"] == cat)}
                        for cat in cats},
        "items": items,
        "refused": refused,
        "roots": [os.fspath(rmap[rid]) for rid in (LIVE, REPO, TEMP) if rid in rmap],
        "quarantine_dir": quarantine,
        "token": token,
        "expires_at": _iso(int((now + PLAN_TTL_SECONDS) * 1e9)),
        "message": ("Dry run only. Nothing has been deleted or moved. A person "
                    "approving the card is what runs it."),
    }
    with _LOCK:
        if store:
            _PENDING["plan"] = {"plan": plan, "at": now,
                                "expires_at": now + PLAN_TTL_SECONDS,
                                "roots": {rid: os.fspath(p) for rid, p in rmap.items()},
                                "token": token, "categories": list(cats),
                                "items": [dict(i) for i in items],
                                "quarantine_dir": quarantine}
    return plan


# ---------------------------------------------------------------------------
#   Applying: only what was planned, only after a person said yes
# ---------------------------------------------------------------------------

def _quarantine_target(dest_parent: Path, name: str) -> Path:
    target = dest_parent / name
    if not os.path.exists(target):
        return target
    stem, suffix = os.path.splitext(name)
    for n in range(2, 100):
        candidate = dest_parent / ("{0}-{1}{2}".format(stem, n, suffix))
        if not os.path.exists(candidate):
            return candidate
    raise OSError("no free name in the quarantine folder")


def _delete_pycache_dir(path) -> None:
    """Delete ONE __pycache__ folder after proving it holds only cache files."""
    if _is_reparse(path):
        raise OSError("a link or junction is in the way")
    try:
        entries = list(os.scandir(path))
    except OSError as exc:
        raise OSError("the folder could not be read ({0})".format(type(exc).__name__))
    for entry in entries:
        if _is_reparse(entry.path):
            raise OSError("a __pycache__ folder holds a link or junction")
        if entry.is_dir(follow_symlinks=False):
            raise OSError("a __pycache__ folder holds a subfolder that is not a cache file")
        if not str(entry.name).lower().endswith((".pyc", ".pyo")):
            raise OSError("a __pycache__ folder holds something that is not a cache file")
    shutil.rmtree(path)


def _delete_temp_item(path, kind: str) -> None:
    """Delete ONE %TEMP% item after proving it holds no link or junction."""
    if _is_reparse(path):
        raise OSError("a link or junction is in the way")
    if kind == "file":
        os.remove(path)
        return
    if not _no_reparse_inside(path):
        raise OSError("the folder holds a link or junction")
    shutil.rmtree(path)


def _stop(result: dict, path, why: str, changed: bool = False) -> dict:
    result["ok"] = False
    result["stopped_at"] = os.fspath(path)
    result["error"] = why
    if changed:
        result["changed"] = True
        result["message"] = ("Something changed since the plan was made, so Jarvis "
                             "stopped. Nothing after {0} was touched; plan a fresh "
                             "cleanup.").format(os.fspath(path))
    else:
        result["message"] = ("Something went wrong, so Jarvis stopped. Nothing after "
                             "{0} was touched.").format(os.fspath(path))
    return result


def apply_cleanup(categories, confirm_token, *, now=None) -> dict:
    """Carry out the plan a person approved - never anything else.

    Refuses without the exact single-use token minted by `plan_cleanup()` and
    consumed by the approved card, refuses if the categories differ, refuses an
    expired plan, and re-checks every item (location, shape, link, and - for a
    deletion - that its size and newest time are exactly what was planned)
    immediately before touching it. The first discrepancy stops the run; the
    result says where and what was already done. `freed_bytes` counts only
    what was really deleted; moved-into-quarantine bytes are reported
    separately because they are still on disk.
    """
    now = _now() if now is None else float(now)
    try:
        cats = _parse_categories(categories)
    except ValueError as exc:
        return {"schema": SCHEMA, "ok": False, "error": str(exc),
                "freed_bytes": 0, "moved_bytes": 0, "deleted": [],
                "quarantined": [], "message": "Nothing was touched."}
    with _LOCK:
        pending = _PENDING.get("plan")
        if not pending or not isinstance(pending.get("plan"), dict):
            return {"schema": SCHEMA, "ok": False,
                    "error": ("There is no plan on this PC waiting to be carried out. "
                              "Plan a cleanup and approve its card first."),
                    "freed_bytes": 0, "moved_bytes": 0, "deleted": [],
                    "quarantined": [], "message": "Nothing was touched."}
        if not isinstance(confirm_token, str) or len(confirm_token) < 16:
            return {"schema": SCHEMA, "ok": False,
                    "error": "This cleanup needs the confirmation from your approval card.",
                    "freed_bytes": 0, "moved_bytes": 0, "deleted": [],
                    "quarantined": [], "message": "Nothing was touched."}
        if not hmac.compare_digest(str(pending.get("token") or ""), confirm_token):
            return {"schema": SCHEMA, "ok": False,
                    "error": ("That is not the confirmation for this plan. Plan the "
                              "cleanup again and approve its card."),
                    "freed_bytes": 0, "moved_bytes": 0, "deleted": [],
                    "quarantined": [], "message": "Nothing was touched."}
        if cats != list(pending.get("categories") or ()):
            return {"schema": SCHEMA, "ok": False,
                    "error": "The categories changed after the card was made, so nothing is cleared.",
                    "freed_bytes": 0, "moved_bytes": 0, "deleted": [],
                    "quarantined": [], "message": "Nothing was touched."}
        if now > float(pending.get("expires_at") or 0):
            _PENDING["plan"] = None
            return {"schema": SCHEMA, "ok": False,
                    "error": ("That plan is more than {0} minutes old. The card and the "
                              "paths may be stale, so nothing is cleared - plan it "
                              "again.").format(PLAN_TTL_SECONDS // 60),
                    "freed_bytes": 0, "moved_bytes": 0, "deleted": [],
                    "quarantined": [], "message": "Nothing was touched."}
        # Consume the plan BEFORE touching anything: one approval, one run.
        _PENDING["plan"] = None
        roots = {rid: Path(p) for rid, p in (pending.get("roots") or {}).items()}
        planned_items = [dict(i) for i in pending.get("items") or ()]
        quarantine = pending.get("quarantine_dir")
    result = {
        "schema": SCHEMA,
        "ok": True,
        "freed_bytes": 0,
        "moved_bytes": 0,
        "deleted": [],
        "quarantined": [],
        "skipped": [],
        "quarantine_dir": quarantine,
        "stopped_at": None,
        "changed": False,
        "error": None,
        "categories": cats,
        "message": "Nothing has been done yet.",
    }
    for item in planned_items:
        path = item.get("path")
        category = str(item.get("category") or "")
        action = str(item.get("action") or "")
        if category not in CATEGORY_INFO or action not in ("delete", "quarantine"):
            return _stop(result, path, "the plan named something this module does not know how to clear")
        if not _shape_ok(category, path):
            return _stop(result, path, "it no longer looks like a file this category clears",
                         changed=True)
        ok, why = check_path(path, [{"id": rid, "path": p, "label": rid}
                                    for rid, p in roots.items()],
                             category=category)
        if not ok:
            return _stop(result, path, why, changed=True)
        if action == "delete":
            try:
                fresh = _snapshot_item(path, str(item.get("kind") or "file"))
            except OSError as exc:
                return _stop(result, path, "it could not be read ({0})".format(type(exc).__name__))
            planned_check = item.get("check") or {}
            if (int(fresh.get("files") or 0) != int(planned_check.get("files") or 0)
                    or int(fresh.get("bytes") or 0) != int(planned_check.get("bytes") or 0)
                    or int(fresh.get("newest_ns") or 0) != int(planned_check.get("newest_ns") or 0)
                    or int(fresh.get("created_ns") or 0) != int(planned_check.get("created_ns") or 0)):
                return _stop(result, path,
                             "it changed since the plan was made", changed=True)
            try:
                if category == "pycache" and item.get("kind") == "dir":
                    _delete_pycache_dir(path)
                else:
                    _delete_temp_item(path, str(item.get("kind") or "file"))
            except PermissionError:
                # A file another program has open is SKIPPED and counted, never
                # forced: the owner's running programs outrank this cleanup.
                result["skipped"].append({"path": os.fspath(path),
                                          "why": "it is open or in use, so it was left alone"})
                continue
            except OSError as exc:
                return _stop(result, path, "it could not be deleted ({0})".format(exc))
            except Exception as exc:            # noqa: BLE001 - stop, never continue
                return _stop(result, path, "it could not be deleted ({0})".format(
                    type(exc).__name__))
            result["freed_bytes"] += int(item.get("bytes") or 0)
            result["deleted"].append(os.fspath(path))
        else:
            if not quarantine:
                return _stop(result, path, "there is nowhere to quarantine it")
            if not _same_volume(path, quarantine):
                return _stop(result, path,
                             "the quarantine folder is on another disk, so moving would copy "
                             "the bytes; nothing is moved across disks")
            dest_parent = Path(quarantine) / category
            try:
                dest_parent.mkdir(parents=True, exist_ok=True)
                target = _quarantine_target(dest_parent, str(item.get("name") or "item"))
                shutil.move(os.fspath(path), os.fspath(target))
            except OSError as exc:
                return _stop(result, path, "it could not be moved ({0})".format(exc))
            result["moved_bytes"] += int(item.get("bytes") or 0)
            result["quarantined"].append({"path": os.fspath(path),
                                          "moved_to": os.fspath(target),
                                          "why": "moved, never deleted: {0}".format(
                                              CATEGORY_INFO[category]["plain"])})
    if result["quarantined"] and quarantine:
        _write_quarantine_manifest(quarantine, result["quarantined"], now)
    result["message"] = _done_words(result)
    with _LOCK:
        _LAST["result"] = result
    return result


def _write_quarantine_manifest(quarantine: str, moved: list, now: float) -> None:
    """One small file inside the run folder, saying why each item was moved.

    The `_why-refused.json` shape jarvis_skills.py already uses: a person (or a
    later audit) can read the folder and know where every path came from and
    that it was moved rather than deleted. A failure to write it never fails
    the cleanup - the bytes are already safe in the quarantine.
    """
    try:
        payload = {
            "schema": SCHEMA,
            "moved_at": _iso(int(float(now) * 1e9)),
            "why": ("These were moved, never deleted, so the owner can look at "
                    "them or put them back. The original path is in `from`."),
            "items": [{"from": q.get("path"), "to": q.get("moved_to"),
                       "reason": q.get("why")} for q in moved],
        }
        folder = Path(quarantine)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / QUARANTINE_WHY).write_text(
            json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    except OSError:
        pass


def _done_words(result: dict) -> str:
    freed = _size(result["freed_bytes"])
    moved = _size(result["moved_bytes"])
    parts = []
    if result["deleted"]:
        parts.append("{0} deleted, freeing {1}".format(
            _count(len(result["deleted"]), "item"), freed))
    if result["quarantined"]:
        parts.append("{0} moved into {1} ({2}, still on disk)".format(
            _count(len(result["quarantined"]), "item"), result["quarantine_dir"], moved))
    if result.get("skipped"):
        parts.append("{0} left alone because another program is using it".format(
            _count(len(result["skipped"]), "item")))
    if not parts:
        return "Nothing was cleared."
    return "Done: {0}.".format("; ".join(parts))


def _count(n: int, one: str, many: Optional[str] = None) -> str:
    return "{0} {1}".format(n, one if n == 1 else (many or one + "s"))


# ---------------------------------------------------------------------------
#   The one approval card
# ---------------------------------------------------------------------------

def _tier(action: str) -> str:
    """The action's shipped tier. "ask" when it cannot be read - never "auto".

    `jarvis_framework` may not be importable in a test or an older install; the
    safe answer in both cases is the one that makes the card happen.
    """
    try:
        import jarvis_framework as fw
        return str(fw.action_tier(action))
    except Exception:                           # noqa: BLE001 - module absent
        return "ask"


def _gate(action: str, detail: dict, prompt: str):
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def _spawn(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="jarvis-storage-health-card", daemon=True).start()


def _person_said_yes(verdict) -> bool:
    """Only a person's yes at the "ask" tier counts - never a looser tier."""
    outcome = getattr(verdict, "outcome", None)
    tier = getattr(verdict, "tier", None)
    return outcome == "approved" and tier == "ask"


def card_text(plan: dict) -> str:
    """What the person reads: the folders, every path in full, and the cost of no."""
    lines = ["Clear temporary files from this PC?", ""]
    roots = plan.get("roots") or []
    if roots:
        lines.append("Looking at: {0}".format(", ".join(roots)))
        lines.append("")
    for cat in plan.get("categories") or ():
        info = CATEGORY_INFO.get(cat) or {}
        counts = (plan.get("by_category") or {}).get(cat) or {}
        lines.append("{0}: {1}, about {2}.".format(
            info.get("label", cat), _count(int(counts.get("count") or 0), "item"),
            _size(counts.get("bytes"))))
        if info.get("plain"):
            lines.append("    {0}".format(info["plain"]))
    lines.append("")
    lines.append("Exactly this, nothing else:")
    for item in plan.get("items") or ():
        if item.get("action") == "delete":
            lines.append("  delete  {0}  ({1})".format(item.get("path"), _size(item.get("bytes"))))
        else:
            lines.append("  move    {0}  ->  {1}".format(
                item.get("path"), plan.get("quarantine_dir")))
    lines.append("")
    lines.append("A deleted file cannot be undone. Moved files are kept in the "
                 "quarantine folder above so you can put them back.")
    lines.append("Nothing of yours - no memory, chat history, approvals, receipts or "
                 "notes - is touched.")
    lines.append("What saying no costs: nothing changes at all, and this PC keeps the "
                 "{0} these files are using.".format(_size(plan.get("bytes"))))
    return "\n".join(lines)


def _finish(token_items: int, outcome: str, why: str = "", message: str = "",
            result: Optional[dict] = None) -> None:
    with _LOCK:
        _PENDING["plan"] = None
        _LAST["result"] = {
            "schema": SCHEMA,
            "ok": outcome == "done",
            "outcome": outcome,
            "why": why[:200] if why else "",
            "message": message or _OUTCOME_WORDS.get(outcome, "Nothing was cleared."),
            "freed_bytes": int((result or {}).get("freed_bytes") or 0),
            "moved_bytes": int((result or {}).get("moved_bytes") or 0),
            "deleted": list((result or {}).get("deleted") or []),
            "quarantined": list((result or {}).get("quarantined") or []),
        }


_OUTCOME_WORDS = {
    "done": "Done - the approved items were cleared.",
    "denied": "You said no, so nothing was deleted or moved.",
    "timed_out": "Nobody answered the card, so nothing was deleted or moved.",
    "refused": "The approval card could not be used, so nothing was deleted or moved.",
    "failed": "Something went wrong, so nothing was deleted or moved.",
}


def _decide(job: dict, gate: Callable, tier_of: Callable) -> None:
    """Wait for the one card, then act - exactly as the plan said."""
    text = job["text"]
    detail = {
        "text": text,
        "what": "delete or quarantine temporary files from this PC",
        "categories": list(job["categories"]),
        "items": int(job["count"]),
        "bytes": int(job["bytes"]),
        "quarantine_dir": job.get("quarantine_dir") or "",
        "leaves_this_pc": False,
    }
    try:
        verdict = gate(CLEANUP_ACTION, detail, text)
    except Exception as exc:                    # noqa: BLE001 - never act on a failure
        return _finish(job["count"], "refused",
                       "the approval gate failed ({0})".format(type(exc).__name__))
    if getattr(verdict, "tier", "unknown") != "ask" or tier_of(CLEANUP_ACTION) != "ask":
        return _finish(job["count"], "refused",
                       "the gate answered at a tier that is not a person saying yes")
    if not _person_said_yes(verdict):
        outcome = getattr(verdict, "outcome", "refused")
        if outcome in ("denied", "timed_out"):
            return _finish(job["count"], outcome)
        return _finish(job["count"], "refused",
                       str(getattr(verdict, "reason", "refused"))[:200])
    try:
        result = apply_cleanup(job["categories"], job["token"], now=job.get("now"))
    except Exception as exc:                    # noqa: BLE001 - a card must not crash
        return _finish(job["count"], "failed", type(exc).__name__,
                       message="Something went wrong. Only the items named on the card "
                               "could have been touched.")
    if result.get("ok"):
        return _finish(job["count"], "done", result=result)
    return _finish(job["count"], "failed", str(result.get("error") or ""),
                   message=str(result.get("message") or ""))


def request_apply(body, *, gate=None, tier_of=None, spawn=None, roots=None,
                  now=None) -> tuple:
    """The POST: plan, then ONE card. 202 while it waits; nothing acts by itself.

    Returns (status, json). 400 for a bad category, 409 while a card already
    waits, 503 when the action's tier is not "ask", 200 when there is nothing
    to clear (no card is raised for an empty plan), 202 when the card is up.
    """
    now = _now() if now is None else float(now)
    gate = gate or _gate
    tier_of = tier_of or _tier
    spawn = spawn or _spawn
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "Send a JSON object with a categories list."}
    try:
        cats = _parse_categories(body.get("categories"))
    except ValueError as exc:
        return 400, {"ok": False, "error": str(exc)}
    tier = tier_of(CLEANUP_ACTION)
    if tier != "ask":
        return 503, {"ok": False, "error": (
            "{0} is tier {1!r} in jarvis-framework.toml; clearing files needs a person "
            "to say yes, so it must be 'ask'").format(CLEANUP_ACTION, tier)}
    with _LOCK:
        if _PENDING.get("plan") is not None:
            return 409, {"ok": False,
                         "error": "A cleanup card is already waiting - answer it first."}
    try:
        plan = plan_cleanup(cats, roots=roots, now=now)
    except ValueError as exc:
        return 400, {"ok": False, "error": str(exc)}
    except OSError as exc:
        return 503, {"ok": False, "error": "The storage scan failed ({0}).".format(
            type(exc).__name__)}
    if not plan.get("ok"):
        # plan_cleanup stored a pending plan before we knew it could be used;
        # a plan that cannot be carried out must not block the next request.
        with _LOCK:
            _PENDING["plan"] = None
        return 400, {"ok": False, "error": str(plan.get("error") or "the plan failed")}
    if not plan.get("items"):
        with _LOCK:
            _PENDING["plan"] = None
        return 200, {"ok": True, "nothing_to_clear": True, "categories": cats,
                     "refused": plan.get("refused") or [],
                     "message": "There is nothing safe to clear in that category right now."}
    text = card_text(plan)
    token = plan["token"]
    job = {"token": token, "categories": cats, "count": plan["count"],
           "bytes": plan["bytes"], "quarantine_dir": plan.get("quarantine_dir"),
           "text": text, "now": now}
    try:
        spawn(lambda: _decide(job, gate, tier_of))
    except Exception:                           # noqa: BLE001 - no card, no act
        with _LOCK:
            _PENDING["plan"] = None
        return 503, {"ok": False, "error": "could not raise the approval card"}
    return 202, {"ok": True, "waiting": True, "categories": cats,
                 "count": plan["count"], "bytes": plan["bytes"],
                 "quarantine_dir": plan.get("quarantine_dir"),
                 "refused": plan.get("refused") or [],
                 "message": ("Waiting for your approval. Nothing is deleted or moved "
                             "unless you approve the card.")}


# ---------------------------------------------------------------------------
#   Routes: the wiring worker adds these in two lines
# ---------------------------------------------------------------------------

def handle_get(path, query="", *, roots=None, now=None) -> tuple:
    """GET the inventory, or the dry-run plan. Never returns the plan token:
    a plan token is minted by the card path, so a dry run cannot be replayed.
    The plan is a PREVIEW: it stores no pending plan (`store=False`), so a
    preview followed by the cleanup request raises the card instead of the
    409 "a cleanup card is already waiting" that no card could ever clear."""
    route = str(path or "").split("?", 1)[0].rstrip("/") or "/"
    if route == SCAN_PATH:
        try:
            return 200, scan(roots=roots, now=now, refresh=True)
        except Exception as exc:                # noqa: BLE001 - a route must not crash
            return 503, {"ok": False, "error": "the scan failed ({0})".format(
                type(exc).__name__)}
    if route == PLAN_PATH:
        raw = ""
        try:
            parts = parse_qs(query or "")
            raw = (parts.get("categories") or [""])[0]
        except Exception:                       # noqa: BLE001 - bad query is not fatal
            raw = ""
        try:
            plan = plan_cleanup(raw or None, roots=roots, now=now, store=False)
        except ValueError as exc:
            return 400, {"ok": False, "error": str(exc)}
        out = dict(plan)
        out.pop("token", None)
        out["token_omitted"] = ("A plan token comes from the approval card path, "
                                "not from a dry run.")
        return (200 if out.get("ok") else 400), out
    return 404, {"ok": False, "error": "no such storage route"}


def handle_post(path, body, *, gate=None, tier_of=None, spawn=None, roots=None,
                now=None) -> tuple:
    route = str(path or "").split("?", 1)[0].rstrip("/") or "/"
    if route != APPLY_PATH:
        return 404, {"ok": False, "error": "no such storage route"}
    try:
        return request_apply(body, gate=gate, tier_of=tier_of, spawn=spawn,
                             roots=roots, now=now)
    except Exception as exc:                    # noqa: BLE001 - a route must not crash
        return 503, {"ok": False, "error": "the cleanup request failed ({0})".format(
            type(exc).__name__)}


def status(*, now=None) -> dict:
    """What is pending and what happened last - for a route and the suites."""
    now = _now() if now is None else float(now)
    with _LOCK:
        pending = _PENDING.get("plan")
        plan = (pending or {}).get("plan") or {}
        out = {"schema": SCHEMA,
               "waiting": bool(pending),
               "categories": list((pending or {}).get("categories") or ()),
               "count": int(plan.get("count") or 0),
               "bytes": int(plan.get("bytes") or 0),
               "expires_in": (max(0, int(float(pending.get("expires_at") or 0) - now))
                              if pending else None),
               "last": _LAST.get("result")}
        return out


def _reset_for_tests() -> None:
    """A cold cache and no pending plan. Never called by a route."""
    with _LOCK:
        _PENDING["plan"] = None
        _LAST["result"] = None
        _SCAN_CACHE.update({"at": 0.0, "inventory": None})
    _TRACKED_CACHE.clear()


if __name__ == "__main__":
    inv = scan(refresh=True)
    print(summary_line(inv))
    for root in inv["roots"]:
        print("  {0:<10} {1:>8}  {2}".format(
            root["id"], _size(root["bytes"]),
            "there" if root["exists"] else (root.get("why_not") or "absent")))
    for cat, cand in inv["candidates"].items():
        if cand["count"]:
            print("  {0:<22} {1:>4} item(s)  {2:>8}".format(
                cat, cand["count"], _size(cand["bytes"])))
    for note in inv["notes"]:
        print("note: " + note)
    sys.exit(0)
