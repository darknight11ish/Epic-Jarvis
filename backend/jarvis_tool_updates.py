"""jarvis_tool_updates.py - "Check for tool updates", on request: is each
Python package, Rust building block and pinned GitHub-hosted tool Jarvis is
built from still the newest version, or is a newer one out.

NEW MODULE, shipped whole. tool-updates.patch adds one call at start-up,
`install(Handler, ...)` (the same shape as jarvis_news.py, jarvis_media.py
and jarvis_stop_all.py), which answers GET /api/tool_updates and POST
/api/tool_updates/check. docs/JARVIS-API.md section 53; backend/README.md
"Checking for tool updates".

THE OWNER'S REQUEST (asked directly, not from the feasibility backlog):
"a feature that allows me to run it on request that looks for updates of
current tools that are integrated into Jarvis already (through GitHub)."

REPORT ONLY - NEVER AN UPDATE ITSELF
This never runs `pip install`, `cargo update`, or anything else that changes
a file (the house rule the feasibility audit's I92 already wrote down for
Windows' own `winget` updates, not built yet: "Updating stays a line the
owner runs; never 'update all'"). It lists what is outdated and the exact
command to run - `py -3 -m pip install --upgrade <name>` or
`cargo update -p <name>` - and stops there. It never says "vulnerable" or
anything about safety: that is `tools/check_python_advisories.py`'s job (a
different check, already built); this is purely "is it current".

ONE APPROVAL CARD, EVER - THEN NEVER AGAIN
This is a new named way out of the PC (docs/ARCHITECTURE.md section 4): it
calls PyPI, crates.io and (if `GITHUB_TOOLS` below is ever non-empty)
GitHub's API, over the internet. The owner decided: ask with a card the
FIRST time this check is ever run; once approved, `tool_updates.json` in the
Jarvis settings folder remembers it (`{"approved": true, "changed": epoch}`)
and every later run skips the card - the shape
`jarvis_asks_first.loosen_what_asks_first` uses for "ask once, remember the
answer, never ask that same thing again", simplified: there is no ON/OFF
here, only ever-approved-or-not, so there is no withdraw-a-waiting-card race
to guard (nothing here can be turned back off from either app). What leaves
the PC, ever: package and crate NAMES and PINNED VERSION NUMBERS only -
never a file path, never anything about the owner. Nothing here opens a
socket in anything read-only; the check itself only runs after a person's
yes, from `request_check`'s own gate call.

WHAT IS CHECKED, AND WHY
1. Python packages - `backend/requirements.lock` (the SAME hash-locked file
   `tools/check_python_advisories.py` already parses, copied beside
   `jarvis_hud.py` by `apply-patches.ps1` for this purpose) names every
   pinned package. For each one, the version actually installed in THIS
   Python process (`importlib.metadata.version`, standard library) is
   compared against PyPI's own `.../pypi/<name>/json` `info.version` - the
   real installed version, not merely the lock file's, because
   `apply-patches.ps1` installs from `requirements.txt` (`>=`), not the
   hash-locked file (a known, documented gap - `requirements.lock`'s own
   header says "NOT YET what scripts/apply-patches.ps1 installs from"), so
   the two can already disagree. The lock is only where the LIST of names
   comes from; when a package cannot be found installed at all (this
   process is not the real backend, or it was never installed), its pinned
   lock version is shown instead, said plainly.
2. Rust crates - `jarvis-desktop/src-tauri/Cargo.lock` (NOT `Cargo.toml` -
   the lock file has the exact resolved versions actually built), copied
   beside `jarvis_hud.py` as `rust-crates.lock` for the same reason as
   above (this backend module has no other way to reach a file in a
   different part of the repository on the owner's PC). Every `[[package]]`
   entry whose `source` is the crates.io registry is checked against
   `https://crates.io/api/v1/crates/<name>`'s `max_stable_version` (or
   `newest_version` if a crate has never had a stable release). The one
   package with no `source` at all is `jarvis-desktop` itself (a local
   path, not a downloaded crate) and is skipped.
3. GitHub-hosted tools, hand-installed (never through pip or cargo),
   PINNED TO A SPECIFIC RELEASE - `GITHUB_TOOLS` below, checked against
   `GET https://api.github.com/repos/<owner>/<repo>/releases/latest`
   (unauthenticated, 60 requests an hour; a 403/429 becomes one WARN line
   in the report, never a crash).

GITHUB TOOLS: WHY THE LIST BELOW IS EMPTY TODAY
The brief's own two candidates were checked against the real docs, and
neither actually fits this shape, so nothing is hand-written here as a
guess:
  * **Everything / `es.exe` (voidtools)** is NOT integrated into Jarvis at
    all - `backend/README.md` ("Owner steps") and `docs/JARVIS-API.md`
    section 35.6 both say so plainly: "'Where's that file?' does not use
    Everything (`es.exe`)... it is a separate program to install and keep
    updated, and it could not be tried here." (It is feasibility idea I39,
    queued, not built.) There is nothing installed to check the version of.
  * **colibri** (`JustVugg/colibri`, the big model's engine) IS integrated,
    but `docs/BIG-MODEL.md` step 1 tells the owner to download "the newest
    release" every time, by design - there is no PINNED version to compare
    against; it is always current by construction. Comparing it to
    "GitHub's latest release" would always say "up to date" and add
    nothing a real check could ever catch.
  * **livekit-wakeword** (`livekit/livekit-wakeword`, the "hey Jarvis"
    detector's optional training step) IS integrated and IS pinned - but to
    a COMMIT (`95448a7559c453fcd87645bd67b247ffb45f85b0`,
    `backend/README.md`, "Train my voice"), not a named release. GitHub's
    `/releases/latest` says nothing about whether a commit pin is behind:
    a repo can cut releases on a branch the pinned commit never touches, or
    have no releases at all. Checking it against "the latest release"
    would be comparing two different things and could tell the owner
    something false with a confident-sounding number attached to it, so it
    is left out rather than guessed at.
Sherpa-onnx's and openWakeWord's model-weight downloads (also from GitHub
releases) are deliberately NOT here either: they are pip-installed
(sherpa-onnx) or SHA-256 hash-pinned data files whose whole point is that
they do NOT quietly follow "the latest" (the voice upgrades are "each
measured before it replaces anything", CLAUDE.md, 2026-09-26) - a plain
version-bump suggestion for one of these would be actively wrong advice.
Add a real one here as a `GithubTool(name, "owner/repo", pinned, where)`
tuple entry once one exists; the checking code below already handles it,
tested with a fake entry injected (`test_tool_updates.py`).

STANDARD LIBRARY ONLY. `urllib.request`, `json`, `importlib.metadata` -
matching `tools/check_python_advisories.py`'s own house style. Nothing here
adds a new Python or npm dependency.

    python3 test_tool_updates.py
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

try:
    import jarvis_framework as fw
except Exception:  # pragma: no cover - shipped beside it on the PC
    fw = None  # type: ignore

try:
    import tomllib as _toml
except ModuleNotFoundError:  # pragma: no cover - Python before 3.11
    try:
        import tomli as _toml  # type: ignore
    except ModuleNotFoundError:
        _toml = None  # type: ignore

try:
    import importlib.metadata as _im
except ImportError:  # pragma: no cover - Python before 3.8
    _im = None  # type: ignore

PATH = "/api/tool_updates"
CHECK_ROUTE = "/api/tool_updates/check"
ACTION = "check_tool_updates"

# ---------------------------------------------------------------------------
#   Words both apps show - desktop only, CLAUDE.md's standing rule against
#   deep config/dev tooling on the phone (docs/ARCHITECTURE.md section 8)
# ---------------------------------------------------------------------------

TITLE = "Check for tool updates"
DETAIL = ("Jarvis can look up whether the Python packages, the Rust building blocks and any "
          "pinned GitHub-hosted tool it is built from have a newer version out. It only "
          "reports - it never installs or changes anything itself; it shows the exact command "
          "to run yourself. The first time you run this, Jarvis asks once, because it means "
          "reaching the websites that publish them (PyPI for Python, crates.io for Rust, and "
          "GitHub) over the internet; after that one yes it never asks again.")
MISSING = "Your PC's Jarvis cannot check for tool updates yet - run apply-patches.ps1 on this PC."
BUTTON_LABEL = "Check for tool updates"
WAITING = "Waiting for your yes on the approval card."

CARD = "\n".join([
    "Let Jarvis check for tool updates?",
    "",
    "Jarvis will ask three services, on the open internet, which version of each tool it is "
    "built from is newest: PyPI (pypi.org) for its Python packages, crates.io for the Rust "
    "building blocks in Jarvis Desktop, and GitHub (api.github.com) for any pinned tool "
    "installed from there. Only a tool or package's NAME and the version number it is pinned "
    "to are ever sent - never a file path, a folder name, or anything about you.",
    "",
    "This only reports. Jarvis never installs, upgrades or changes a file by itself - it "
    "shows you the exact command to run yourself, and stops there.",
    "",
    "This is the only time you are asked: once you say yes, later checks (the same button) "
    "never raise this card again.",
    "",
    "If you did not just do this, say no.",
    "",
    "If you say no: nothing is checked, and nothing changes.",
])

#: How the last card went, in words the apps show.
LAST_WORDS = {
    "approved": "You said yes. Jarvis is checking now, and will not ask again.",
    "denied": "The card was turned down, so nothing was checked.",
    "timed_out": "Nobody answered the card in time, so nothing was checked.",
    "refused": "Your PC's settings do not let this be approved, so nothing was checked.",
    "failed": "It was approved, but the setting could not be saved, so it may ask again next "
              "time.",
}

# ---------------------------------------------------------------------------
#   The GitHub tools registry - see the module docstring for why this is
#   empty today, and how to add a real one later.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GithubTool:
    """One hand-installed, GitHub-released tool pinned to a fixed version."""
    name: str        # plain words for the report, e.g. "Everything (es.exe)"
    repo: str        # "owner/repo"
    pinned: str      # the version/tag named in the docs today
    where: str       # which doc names the pin, e.g. "docs/BIG-MODEL.md"


#: Empty by design - see "GITHUB TOOLS: WHY THE LIST BELOW IS EMPTY TODAY"
#: in the module docstring. A maintainer adds one entry here when a real
#: one exists; nothing else in this module needs to change.
GITHUB_TOOLS: tuple = ()

GITHUB_TOOLS_NOTE = ("No hand-installed tool pinned to one fixed GitHub release is checked "
                      "yet. Everything (es.exe) is not actually used by Jarvis today; colibri "
                      "always installs \"the newest release\", so there is no pinned version "
                      "to compare; livekit-wakeword is pinned to a commit, not a release, which "
                      "this check cannot honestly compare against \"the latest release\". See "
                      "jarvis_tool_updates.py's own notes for the full reasoning.")

# ---------------------------------------------------------------------------
#   What is read, and the gate - replaceable, so the tests open nothing
# ---------------------------------------------------------------------------


def _config_dir() -> Path:
    if fw is not None:
        try:
            return Path(fw.CONFIG_DIR)
        except Exception:
            pass
    env = os.environ.get("OPENJARVIS_CONFIG_DIR") or os.environ.get("JARVIS_CONFIG_DIR")
    if env:
        return Path(os.path.expanduser(env))
    return Path(os.path.expanduser("~")) / ".openjarvis"


def settings_path() -> Path:
    return _config_dir() / "tool_updates.json"


def _tier(action: str) -> str:
    try:
        return str(fw.action_tier(action)) if fw is not None else "ask"
    except Exception:
        return "ask"


def _gate(action: str, detail: dict, prompt: str):
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def _spawn(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="jarvis-tool-updates-card", daemon=True).start()


def _audit(event: str, detail: dict) -> None:
    try:
        if fw is not None:
            fw.audit_log(event, detail)
    except Exception:
        pass


def _lockdown_on() -> bool:
    """Lockdown (jarvis_asks_first.py): False without that module; if it
    cannot be read, True - the card is shown rather than skipped."""
    try:
        import jarvis_asks_first
    except Exception:
        return False
    try:
        return bool(jarvis_asks_first.lockdown_on())
    except Exception:
        return True


def _person_said_yes(v) -> bool:
    if getattr(v, "allowed", False) is not True:
        return False
    outcome = getattr(v, "outcome", None)
    if outcome is not None:
        return outcome == "approved" and getattr(v, "tier", "ask") == "ask"
    return getattr(v, "tier", None) == "ask"


# ---------------------------------------------------------------------------
#   The one persisted flag: has the owner ever said yes?
# ---------------------------------------------------------------------------

_S_LOCK = threading.Lock()


def approved() -> bool:
    """No file, an unreadable file, damaged JSON, or anything but a literal
    `true`: not approved (fails closed - a damaged file must never skip the
    one card this feature is built around)."""
    with _S_LOCK:
        try:
            raw = settings_path().read_text(encoding="utf-8")
        except OSError:
            return False
    try:
        doc = json.loads(raw)
        return isinstance(doc, dict) and doc.get("approved") is True
    except Exception:
        return False


def _set_approved() -> None:
    """Written only by an approved card - see request_check()."""
    with _S_LOCK:
        p = settings_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps({"approved": True, "changed": time.time()}),
                       encoding="utf-8")
        os.replace(tmp, p)


# ---------------------------------------------------------------------------
#   Fetching - stdlib only, one User-Agent per service naming this tool as
#   local and non-commercial - a name of its own, not a bare HTTP library's,
#   as crates.io's data-access policy asks. It used to add the owner's own
#   GitHub address as a contact; the card promises "never ... anything
#   about you", and that address named the owner to three services on every
#   check, together with their internet address (security/privacy audit,
#   2026-09-27). Checked that day: crates.io answers this User-Agent
#   (HTTP 200 for /api/v1/crates/serde); its policy text was not re-read.
#   Nothing here is called from a read-only path: only run_check() (itself
#   only reached after a person's yes) opens a socket.
# ---------------------------------------------------------------------------

_PYPI_UA = "Jarvis-tool-update-check/1 (local, non-commercial)"
_CRATES_UA = "Jarvis-tool-update-check/1 (local, non-commercial)"
_GITHUB_UA = "Jarvis-tool-update-check/1 (local, non-commercial)"
_TIMEOUT = 20.0


class GithubRateLimited(Exception):
    """GitHub's unauthenticated 60/hour limit was hit (403 or 429). Caught
    by _github_group and turned into one WARN line, never a crash."""


def _get_json(url: str, *, user_agent: str, accept: str = "application/json",
              attempts: int = 2) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": user_agent, "Accept": accept})
    last: Optional[BaseException] = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise
            last = exc
        except Exception as exc:  # a network hiccup: try once more
            last = exc
        if attempt + 1 < attempts:
            time.sleep(1.5 * (attempt + 1))
    raise last  # type: ignore[misc]


def _default_pypi_fetch(url: str) -> dict:
    return _get_json(url, user_agent=_PYPI_UA)


def _default_crates_fetch(url: str) -> dict:
    return _get_json(url, user_agent=_CRATES_UA)


def _default_github_fetch(url: str) -> dict:
    return _get_json(url, user_agent=_GITHUB_UA, accept="application/vnd.github+json")


def _problem_words(exc: BaseException) -> str:
    """A network problem, in one short, plain sentence - never a stack trace,
    never the raw exception text (which could quote a URL oddly)."""
    if isinstance(exc, GithubRateLimited):
        return str(exc)
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code in (403, 429):
            return "rate-limited right now - try again later"
        if exc.code == 404:
            return "not found there any more"
        return f"the server answered with an error ({exc.code})"
    if isinstance(exc, urllib.error.URLError):
        return "could not be reached (no network, or it is down)"
    s = str(exc).strip() or type(exc).__name__
    return s[:200]


def _pypi_latest(name: str, *, fetch: Optional[Callable] = None) -> str:
    fetch = fetch or _default_pypi_fetch
    url = f"https://pypi.org/pypi/{urllib.parse.quote(name)}/json"
    data = fetch(url)
    v = (data.get("info") or {}).get("version") if isinstance(data, dict) else None
    if not isinstance(v, str) or not v:
        raise ValueError("PyPI's answer had no version in it")
    return v


def _crates_latest(name: str, *, fetch: Optional[Callable] = None) -> str:
    fetch = fetch or _default_crates_fetch
    url = f"https://crates.io/api/v1/crates/{urllib.parse.quote(name)}"
    data = fetch(url)
    crate = (data.get("crate") or {}) if isinstance(data, dict) else {}
    v = crate.get("max_stable_version") or crate.get("newest_version")
    if not isinstance(v, str) or not v:
        raise ValueError("crates.io's answer had no version in it")
    return v


def _github_latest_release(repo: str, *, fetch: Optional[Callable] = None) -> str:
    fetch = fetch or _default_github_fetch
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    try:
        data = fetch(url)
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 429):
            raise GithubRateLimited(
                "GitHub's API is rate-limited right now (60 checks an hour with no sign-in) "
                "- try again in a while") from exc
        raise
    tag = data.get("tag_name") if isinstance(data, dict) else None
    if not isinstance(tag, str) or not tag:
        raise ValueError("GitHub's answer had no release tag in it")
    return tag


def _installed_version(dist_name: str) -> Optional[str]:
    """The version really installed in THIS Python process, by distribution
    name (never the import name) - `None` when it cannot be found, so the
    caller falls back to the lock file's own pinned version."""
    if _im is None:
        return None
    try:
        return _im.version(dist_name)
    except Exception:
        return None


def _version_key(v: str) -> tuple:
    """A loose, digits-only sort key - good enough to say "is a newer
    number out", not a real PEP 440/semver comparison (adding a library for
    that is against this module's stdlib-only rule, and a friendly "is it
    current" hint does not need one). A version with no digits sorts as
    (0,), so it never looks newer than a real one."""
    parts = re.findall(r"\d+", v or "")
    return tuple(int(p) for p in parts) if parts else (0,)


# ---------------------------------------------------------------------------
#   Parsing the two lock files
# ---------------------------------------------------------------------------

_PIP_PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;\\]+)")


def _join_logical_lines(text: str) -> list:
    """requirements.lock's backslash-continued lines, joined - the same
    join tools/check_python_advisories.py's lock_entries() does, without
    its hash bookkeeping (this module never checks a hash)."""
    logical, cur = [], ""
    for raw in text.splitlines():
        s = raw.split(" #", 1)[0].rstrip() if not raw.lstrip().startswith("#") else ""
        if not s.strip():
            if cur:
                logical.append(cur)
                cur = ""
            continue
        if s.endswith("\\"):
            cur += s[:-1] + " "
            continue
        logical.append(cur + s)
        cur = ""
    if cur:
        logical.append(cur)
    return logical


def parse_python_lock(text: str) -> dict:
    """{canonical name: (original name, pinned version)} - one entry per
    package. When the lock pins two versions for different Python versions
    (a marker such as `python_full_version >= '3.11'`), the LAST one seen
    wins; this is only ever used as a fallback (see `_installed_version`
    above), never as the number actually shown when the package is really
    installed here."""
    out: dict = {}
    for line in _join_logical_lines(text):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        m = _PIP_PIN.match(s)
        if not m:
            continue
        name, version = m.group(1), m.group(2)
        out[re.sub(r"[-_.]+", "-", name).lower()] = (name, version)
    return out


def parse_cargo_lock(text: str) -> Optional[list]:
    """[(name, version), ...] - every `[[package]]` entry whose `source` is
    the crates.io registry (a local path package, such as jarvis-desktop
    itself, has no `source` and is skipped; a git-sourced one would be too,
    though none exist in this project's Cargo.lock today). `None` - never
    an empty list - when the file cannot be parsed at all (no `tomllib`
    and no `tomli`, or genuinely malformed TOML): "cannot be read" must not
    look like "nothing to check"."""
    if _toml is None:
        return None
    try:
        doc = _toml.loads(text)
    except Exception:
        return None
    out = []
    for pkg in doc.get("package") or []:
        if not isinstance(pkg, dict):
            continue
        name, version, source = pkg.get("name"), pkg.get("version"), pkg.get("source")
        if not isinstance(name, str) or not isinstance(version, str):
            continue
        if not isinstance(source, str) or "crates.io-index" not in source:
            continue
        out.append((name, version))
    return out


# ---------------------------------------------------------------------------
#   The report itself
# ---------------------------------------------------------------------------


def _backend_dir() -> Path:
    return Path(__file__).resolve().parent


def _python_group(backend_dir: Path, pypi_fetch: Optional[Callable],
                  installed_version: Callable[[str], Optional[str]]) -> dict:
    path = backend_dir / "requirements.lock"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {"ecosystem": "Python packages", "available": False,
                "why": "requirements.lock is not beside jarvis_hud.py - run apply-patches.ps1 "
                       "on this PC.", "items": [], "unreachable": []}
    pins = parse_python_lock(text)
    items, unreachable = [], []
    for _canon, (orig, lock_version) in sorted(pins.items()):
        real = installed_version(orig)
        current = real or lock_version
        note = (None if real else "not installed in this Python right now - showing the "
                                   "version this project's lock file pins")
        try:
            latest = _pypi_latest(orig, fetch=pypi_fetch)
        except Exception as exc:
            unreachable.append({"name": orig, "current": current, "why": _problem_words(exc)})
            continue
        outdated = _version_key(latest) > _version_key(current)
        item = {"name": orig, "current": current, "latest": latest, "outdated": outdated,
                "command": f"py -3 -m pip install --upgrade {orig}" if outdated else None}
        if note:
            item["note"] = note
        items.append(item)
    return {"ecosystem": "Python packages", "available": True, "why": "", "items": items,
            "unreachable": unreachable}


def _rust_group(backend_dir: Path, crates_fetch: Optional[Callable]) -> dict:
    path = backend_dir / "rust-crates.lock"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {"ecosystem": "Rust crates", "available": False,
                "why": "rust-crates.lock is not beside jarvis_hud.py - run apply-patches.ps1 "
                       "on this PC.", "items": [], "unreachable": []}
    pins = parse_cargo_lock(text)
    if pins is None:
        return {"ecosystem": "Rust crates", "available": False,
                "why": "this Python cannot read rust-crates.lock (it needs Python 3.11 or "
                       "newer, or the tomli package)", "items": [], "unreachable": []}
    items, unreachable = [], []
    latest_by_name: dict = {}
    # `cargo update -p <name>` refuses with "the specification is ambiguous"
    # the moment a name is pinned at two or more versions at once (a
    # transitive-dependency situation, not a mistake) - 61 of 576 names in
    # this project's own lock file, today. `-p <name>@<version>` is the one
    # cargo accepts (bug audit 2026-09-27, backend finding #6).
    name_counts = Counter(name for name, _ in pins)
    for name, version in sorted(pins):
        if name not in latest_by_name:
            try:
                latest_by_name[name] = ("ok", _crates_latest(name, fetch=crates_fetch))
            except Exception as exc:
                latest_by_name[name] = ("err", _problem_words(exc))
        kind, val = latest_by_name[name]
        if kind == "err":
            unreachable.append({"name": name, "current": version, "why": val})
            continue
        outdated = _version_key(val) > _version_key(version)
        spec = f"{name}@{version}" if name_counts[name] > 1 else name
        items.append({"name": name, "current": version, "latest": val, "outdated": outdated,
                      "command": (f"cd jarvis-desktop\\src-tauri; cargo update -p {spec}"
                                  if outdated else None)})
    return {"ecosystem": "Rust crates", "available": True, "why": "", "items": items,
            "unreachable": unreachable}


def _github_group(github_fetch: Optional[Callable], tools: tuple = GITHUB_TOOLS) -> dict:
    items, unreachable = [], []
    for tool in tools:
        try:
            latest = _github_latest_release(tool.repo, fetch=github_fetch)
        except Exception as exc:
            unreachable.append({"name": tool.name, "current": tool.pinned,
                                "why": _problem_words(exc)})
            continue
        outdated = latest != tool.pinned
        items.append({"name": tool.name, "current": tool.pinned, "latest": latest,
                      "outdated": outdated, "command": None,
                      "note": f"pinned in {tool.where}" if outdated else None})
    return {"ecosystem": "GitHub tools", "available": True,
            "why": "" if tools else GITHUB_TOOLS_NOTE, "items": items,
            "unreachable": unreachable}


def _summary(outdated: int, checked: int, unreachable: int) -> str:
    if checked == 0 and unreachable == 0:
        return "Jarvis has nothing to check yet."
    parts = []
    if checked:
        s = "s" if checked != 1 else ""
        parts.append(f"All {checked} of your tool{s} are on their latest version" if not outdated
                     else f"{outdated} of your {checked} tool{s} have a newer version")
    if unreachable:
        parts.append(f"{unreachable} could not be checked (see below)")
    return ". ".join(parts) + "."


def run_check(*, backend_dir: Optional[Path] = None, pypi_fetch: Optional[Callable] = None,
             crates_fetch: Optional[Callable] = None, github_fetch: Optional[Callable] = None,
             installed_version: Optional[Callable[[str], Optional[str]]] = None,
             github_tools: tuple = GITHUB_TOOLS, clock: Optional[Callable[[], float]] = None
             ) -> dict:
    """The whole report: {"checked_at", "summary", "total_checked",
    "total_outdated", "groups": [...]}. Never raises for a network problem
    (each item that could not be checked lands in that group's
    "unreachable" list instead) - only a genuine bug here would raise."""
    clock = clock or time.time
    backend_dir = backend_dir or _backend_dir()
    installed_version = installed_version or _installed_version
    groups = [
        _python_group(backend_dir, pypi_fetch, installed_version),
        _rust_group(backend_dir, crates_fetch),
        _github_group(github_fetch, github_tools),
    ]
    total_checked = sum(len(g["items"]) for g in groups)
    total_outdated = sum(1 for g in groups for it in g["items"] if it["outdated"])
    total_unreachable = sum(len(g["unreachable"]) for g in groups)
    return {"checked_at": clock(), "summary": _summary(total_outdated, total_checked,
                                                        total_unreachable),
            "total_checked": total_checked, "total_outdated": total_outdated,
            "total_unreachable": total_unreachable, "groups": groups}


# ---------------------------------------------------------------------------
#   The one-time card, then the check itself
# ---------------------------------------------------------------------------

_P_LOCK = threading.Lock()
_P_STATE: dict = {"pending": {}, "last": {}, "latest": {}}
_R_LOCK = threading.Lock()
_R_STATE: dict = {"report": None}
#: Whether a check is running right now, in the background - never inside
#: the HTTP request that asked for it. A real check asks crates.io once per
#: crate NAME in Cargo.lock (576 of them in this project alone today) plus
#: PyPI once per Python package, one request at a time; that can genuinely
#: take a few minutes on a slow connection, so nothing here ever blocks a
#: request waiting for it - the button's press starts it and returns at
#: once, and the page polls GET /api/tool_updates until "checking" is false
#: and a fresh "report" has arrived (the same "start it, poll for it" shape
#: hardware-panel.js already uses for measuring the graphics cards).
_C_LOCK = threading.Lock()
_C_STATE: dict = {"running": False}
CHECKING_MESSAGE = ("Checking now - this can take a few minutes the first time. Come back to "
                    "this page in a bit.")


def last_report() -> Optional[dict]:
    with _R_LOCK:
        return _R_STATE["report"]


def checking() -> bool:
    with _C_LOCK:
        return bool(_C_STATE["running"])


def _finish(pid: str, outcome: str, why: str = "") -> None:
    with _P_LOCK:
        if _P_STATE["pending"].get("id") == pid:
            _P_STATE["pending"].clear()
        if _P_STATE["latest"].get("id") not in (None, pid):
            return
        _P_STATE["last"].clear()
        _P_STATE["last"].update(outcome=outcome, why=why, at=time.time(),
                                message=LAST_WORDS.get(outcome, ""))
    _audit("tool_updates.card", {"outcome": outcome})


def _run_in_background(run: Callable[[], dict]) -> None:
    """Runs `run()` off the request thread and stores whatever it returns as
    the last report - a genuine failure (a bug, not a single package's own
    network problem, which `run_check` already turns into an "unreachable"
    line) simply leaves the last report as it was, rather than raising
    somewhere nobody is listening. Always clears the "checking" flag,
    whatever happens, so a bug here can never wedge the button off forever."""
    try:
        report = run()
    except Exception:
        report = None
    finally:
        with _C_LOCK:
            _C_STATE["running"] = False
    if report is not None:
        with _R_LOCK:
            _R_STATE["report"] = report


def _decide(pid: str, gate: Callable, tier_of: Callable, write: Callable[[], None],
           run: Callable[[], dict]) -> None:
    detail = {"text": CARD, "what": "check PyPI, crates.io and GitHub for newer versions of "
                                    "the tools Jarvis is built from",
              # True: approving it is what lets Jarvis ask PyPI, crates.io and
              # GitHub over the internet.
              "leaves_this_pc": True}
    try:
        v = gate(ACTION, detail, CARD)
    except Exception as exc:
        return _finish(pid, "refused", f"the approval gate failed ({type(exc).__name__})")
    vtier = getattr(v, "tier", "unknown")
    outcome = getattr(v, "outcome", None)
    if vtier != "ask" or tier_of(ACTION) != "ask":
        return _finish(pid, "refused", f"the gate answered at tier {vtier!r}, which is not a "
                                       f"person saying yes")
    if not _person_said_yes(v):
        if outcome in ("denied", "timed_out"):
            return _finish(pid, outcome)
        return _finish(pid, "refused", str(getattr(v, "reason", "refused"))[:200])
    try:
        write()
    except Exception as exc:
        return _finish(pid, "failed", type(exc).__name__)
    _audit("tool_updates.approved", {})
    with _C_LOCK:
        _C_STATE["running"] = True
    _finish(pid, "approved")
    # Already off the request thread (this whole function runs inside the
    # thread request_check() spawned for the card) - no second thread needed.
    _run_in_background(run)


def request_check(body=None, *, gate: Optional[Callable] = None,
                  tier_of: Optional[Callable[[str], str]] = None,
                  spawn: Optional[Callable] = None, write: Optional[Callable[[], None]] = None,
                  run: Optional[Callable[[], dict]] = None) -> tuple:
    """POST /api/tool_updates/check. (code, body). Never blocks on the check
    itself: approved already starts it in the background and returns at
    once (202, "checking"); not yet approved raises the ONE card and
    returns 202 "waiting" - the card's own background thread starts the
    check once approved. Either way, GET /api/tool_updates is where the
    finished report shows up."""
    gate = gate or _gate
    tier_of = tier_of or _tier
    spawn = spawn or _spawn
    write = write or _set_approved
    run = run or run_check
    # Bug audit 2026-09-27, finding #4: read first, every time - not only
    # before the FIRST ever approval. Without this, a later "never" (or
    # "notify") in jarvis-framework.toml stopped meaning anything the
    # moment the owner had said yes once: "What asks first" would say the
    # feature was switched off while this button still reached PyPI,
    # crates.io and GitHub. The same refusal, in the same words, whether or
    # not this has ever run before.
    t = tier_of(ACTION)
    if t != "ask":
        return 503, {"ok": False, "error": (
            f"{ACTION} is tier {t!r} in jarvis-framework.toml; the check "
            f"needs a person to say yes, so it must be 'ask'")}
    if approved() and not _lockdown_on():
        # (While Lockdown is on - jarvis_asks_first.py, 2026-09-28 - the one
        # "yes" from long ago does not count: every way out of this PC asks
        # first, so this raises its card again, below.)
        # `view()` (below) calls `checking()`, which takes _C_LOCK itself -
        # never called while THIS function still holds it, or a thread
        # deadlocks on its own non-reentrant lock.
        already_running = False
        with _C_LOCK:
            if _C_STATE["running"]:
                already_running = True
            else:
                _C_STATE["running"] = True
        if already_running:
            return 202, {"ok": True, "checking": True, "view": view(),
                         "message": CHECKING_MESSAGE}
        try:
            spawn(lambda: _run_in_background(run))
        except Exception:
            with _C_LOCK:
                _C_STATE["running"] = False
            return 503, {"ok": False, "error": "could not start the check"}
        return 202, {"ok": True, "checking": True, "view": view(), "message": CHECKING_MESSAGE}
    with _P_LOCK:
        if _P_STATE["pending"]:
            return 202, {"ok": True, "waiting": True, "view": view(),
                         "message": "A card is already waiting - answer it first."}
        pid = uuid.uuid4().hex
        _P_STATE["pending"].update(id=pid, since=time.time())
        _P_STATE["latest"]["id"] = pid
    try:
        spawn(lambda: _decide(pid, gate, tier_of, write, run))
    except Exception:
        with _P_LOCK:
            _P_STATE["pending"].clear()
        return 503, {"ok": False, "error": "could not raise the approval card"}
    return 202, {"ok": True, "waiting": True, "view": view(),
                 "message": "Waiting for your approval. Nothing is checked unless you say "
                            "yes, and this is the only time you are asked."}


def view() -> dict:
    """GET /api/tool_updates."""
    with _P_LOCK:
        pending = dict(_P_STATE["pending"])
        last = dict(_P_STATE["last"]) or None
    return {"available": True, "title": TITLE, "detail": DETAIL, "button_label": BUTTON_LABEL,
            "approved": approved(), "waiting": bool(pending), "checking": checking(),
            "last": last, "report": last_report()}


def handle_get() -> tuple:
    return 200, view()


def handle_post(route: str, body) -> tuple:  # route is always CHECK_ROUTE - install() checked
    return request_check(body)


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls.do_GET` and `do_POST` so the tool-update routes are
    answered here, after the server's own origin and token checks. Every
    other request goes straight to the original - the same shape as
    jarvis_news.install/jarvis_media.install."""
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(post0, "_jarvis_tool_updates", False):
        return "  tool-updates  Check for tool updates (already on)"

    def _allowed(self) -> bool:
        try:
            if not origin_ok(self):
                self._send(403, {"error": "cross-origin request refused"})
                return False
            if not token_ok(self):
                self._send(401, {"error": "bad or missing X-Jarvis-Token"})
                return False
        except Exception:
            self._send(401, {"error": "bad or missing X-Jarvis-Token"})
            return False
        return True

    def do_GET(self):
        from urllib.parse import urlsplit
        route = urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if route != PATH:
            return get0(self)
        if not _allowed(self):
            return None
        try:
            code, out = handle_get()
        except Exception as exc:
            code, out = 503, {"available": False, "error": type(exc).__name__}
        return self._send(code, out)

    def do_POST(self):
        from urllib.parse import urlsplit
        route = urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if route != CHECK_ROUTE:
            return post0(self)
        if not _allowed(self):
            return None
        try:
            body = json.loads(read_body(self) or b"{}")
        except Exception as exc:
            return self._send(400, {"error": type(exc).__name__})
        try:
            code, out = handle_post(route, body)
        except Exception as exc:
            code, out = 503, {"available": False, "error": type(exc).__name__}
        return self._send(code, out)

    do_GET._jarvis_tool_updates = True
    do_POST._jarvis_tool_updates = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    return "  tool-updates  Check for tool updates: ready"


def _reset_for_tests() -> None:
    with _P_LOCK:
        _P_STATE["pending"].clear()
        _P_STATE["last"].clear()
        _P_STATE["latest"].clear()
    with _R_LOCK:
        _R_STATE["report"] = None
    with _C_LOCK:
        _C_STATE["running"] = False
