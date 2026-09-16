"""jarvis_framework.py - the config every other module reads.

REBUILT, NOT RECOVERED. READ THIS FIRST.

The original of this file does not exist anywhere. Not on the owner's machine,
not in any installer or package, not in a 104 MB export of every claude.ai
conversation, not in any local transcript store. It was searched for and it is
gone.

This is a reconstruction from three things that DO exist:

  1. `jarvis-framework.toml` - 979 lines, the exact file this module parses.
  2. `JARVIS-FRAMEWORK.md` - its written twin, which opens by saying
     "everything below is also written into jarvis-framework.toml, which the
     code actually reads."
  3. Fifty-six call sites across the fifteen surviving modules that import it.

Those call sites are the specification, and they are narrow. The whole of what
this module must provide is:

    load_framework()   the parsed config, as a dict
    action_tier(name)  which tier an action falls in
    audit_log(e, d)    one JSON line on disk
    CONFIG_DIR         where state lives
    LOG_DIR            where the log lives

Nothing else is referenced by anything. Where the original did more, that more
is not reconstructible and is not here. Anything below that could not be
derived from a call site or from the config is marked INFERRED, so a later
reader can tell what is known from what is guessed.

WHY IT MATTERS THAT THIS ONE IS FIRST

Fifteen of the sixteen surviving modules import it, `jarvis_gate` among them.
Until this file exists, `import jarvis_gate` raises ModuleNotFoundError and
nothing else in the backend can even be loaded, let alone tested. It is the
bottom of the stack.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Optional

# tomllib is stdlib from Python 3.11. The backend's own __pycache__ says
# cpython-312, so it is there. tomli is accepted as a fallback rather than
# assumed absent, because a config parser that dies on import takes the whole
# backend with it.
try:
    import tomllib as _toml
except ModuleNotFoundError:  # pragma: no cover - 3.10 and earlier
    try:
        import tomli as _toml  # type: ignore
    except ModuleNotFoundError:
        _toml = None  # type: ignore


# --------------------------------------------------------------------------
#   Where things live
# --------------------------------------------------------------------------
#
# `~/.openjarvis` is not a guess. The surviving code and docs put five separate
# things there by name: appearance.json, memory.db, the HUD token, holds.db and
# approvals.db. backend/README.md also records that the environment variable is
# read "because the backend does - reading a different directory from the
# backend would be worse than not reading one at all".

def _config_dir() -> Path:
    env = os.environ.get("OPENJARVIS_CONFIG_DIR") or os.environ.get("JARVIS_CONFIG_DIR")
    if env:
        return Path(os.path.expanduser(env))
    return Path(os.path.expanduser("~")) / ".openjarvis"


#: Where state lives. Used as `Path(fw.CONFIG_DIR)` in some call sites and as
#: `fw.CONFIG_DIR / "approvals.db"` in others, so it has to BE a Path - a str
#: would satisfy the first and raise TypeError on the second.
CONFIG_DIR: Path = _config_dir()

#: Where the audit log is written. `[logging].log_directory` in the config can
#: override it per call; this is the fallback, and two call sites read it
#: directly as `Path(fw.LOG_DIR)`.
LOG_DIR: Path = CONFIG_DIR / "logs"

#: The name of the config file, looked for in several places below.
CONFIG_NAME = "jarvis-framework.toml"


def config_path() -> Optional[Path]:
    """Where jarvis-framework.toml actually is, or None.

    Four places, in order of how specific they are. The owner's own copy sits
    BESIDE the modules and also one directory up - both were present in the
    folder - so both are searched rather than picking one and being right half
    the time.
    """
    here = Path(__file__).resolve().parent
    candidates = [
        Path(os.path.expanduser(os.environ["JARVIS_FRAMEWORK_TOML"]))
        if os.environ.get("JARVIS_FRAMEWORK_TOML") else None,
        CONFIG_DIR / CONFIG_NAME,
        here / CONFIG_NAME,
        here.parent / CONFIG_NAME,
    ]
    for c in candidates:
        if c and c.is_file():
            return c
    return None


# --------------------------------------------------------------------------
#   The config
# --------------------------------------------------------------------------

_LOCK = threading.RLock()
_CACHE: Optional[dict] = None
_CACHE_KEY: Optional[tuple] = None
_WARNED = False


def _warn_once(msg: str) -> None:
    """Say it to stderr, once. A config problem that prints on every one of
    fifty-six calls is noise nobody reads; one that prints never is a silent
    default nobody notices. Once is the only useful number."""
    global _WARNED
    if not _WARNED:
        _WARNED = True
        print(f"jarvis_framework: {msg}", file=sys.stderr)


def load_framework(*_args: Any, **_kwargs: Any) -> dict:
    """The parsed config, as a plain dict of sections.

    Takes and ignores arguments. That is not laziness - the surviving test
    suites wrap this function and forward whatever they were given:

        _orig_load = fw.load_framework
        def _patched_load(*a, **k):
            d = _orig_load(*a, **k)
            d.setdefault("logging", {})["log_directory"] = _TMP
            return d

    A signature of `()` would break every one of those on the first call.

    RETURNS A FRESH COPY EVERY TIME, and that is load-bearing rather than
    tidy. The wrapper above MUTATES what it is handed. If this returned the
    cached object, that `setdefault(...)["log_directory"] = _TMP` would write
    the test's temp path into the shared cache and leak into every module
    loaded afterwards - a test that quietly reconfigures the process. The
    parse is cached; the dict handed out is not the cached one.
    """
    global _CACHE, _CACHE_KEY
    with _LOCK:
        path = config_path()
        # Re-read when the file changes on disk. `change_own_config` is an
        # approvable action in [autonomy.tiers], so the config is expected to
        # be edited while the backend runs; a cache with no invalidation would
        # make an approved change appear to do nothing until a restart.
        key: tuple
        if path is None:
            key = ("missing",)
        else:
            try:
                st = path.stat()
                key = (str(path), st.st_mtime_ns, st.st_size)
            except OSError:
                key = (str(path), None, None)

        if _CACHE is not None and key == _CACHE_KEY:
            return deepcopy(_CACHE)

        data: dict = {}
        if path is None:
            _warn_once(
                f"no {CONFIG_NAME} found (looked in {CONFIG_DIR}, "
                f"{Path(__file__).resolve().parent} and its parent). "
                "Every setting falls back to its default.")
        elif _toml is None:
            _warn_once(
                "no TOML parser available (needs Python 3.11+, or `pip install "
                f"tomli`). {path} is NOT being read.")
        else:
            try:
                with open(path, "rb") as fh:
                    data = _toml.load(fh)
            except Exception as exc:
                # Never raise. Fifteen modules call this at import time; an
                # exception here means the whole backend fails to start over a
                # stray character in a config file, with a traceback pointing
                # at whichever module happened to import first.
                _warn_once(f"{path} could not be parsed ({type(exc).__name__}: "
                           f"{exc}). Every setting falls back to its default.")
                data = {}

        _CACHE, _CACHE_KEY = data, key
        return deepcopy(data)


def reload_framework() -> dict:
    """Drop the cache and read from disk. INFERRED - no surviving call site
    uses this. It exists because `change_own_config` is an approvable action,
    and something has to be able to act on an approval without a restart."""
    global _CACHE, _CACHE_KEY
    with _LOCK:
        _CACHE = _CACHE_KEY = None
    return load_framework()


def section(name: str) -> dict:
    """One section, always a dict. INFERRED helper - the surviving code writes
    `fw.load_framework().get("logging", {})` by hand at seventeen sites, which
    is what this would have replaced."""
    val = load_framework().get(name)
    return val if isinstance(val, dict) else {}


# --------------------------------------------------------------------------
#   Tiers
# --------------------------------------------------------------------------

#: The four tiers, weakest first. `jarvis_gate` has its own copy of this order
#: (`_RANK`) for resolving a prompt that matches several patterns; this one is
#: here so an unrecognised value in the config can be rejected rather than
#: passed through to a caller that will compare it against these names.
TIERS = ("auto", "notify", "ask", "never")

#: What an unclassified action gets when the config does not say. The config's
#: own comment is the argument: "an action nobody classified is not thereby
#: safe." Both this and the config default to "ask", so the fallback chain
#: cannot bottom out in something permissive.
DEFAULT_UNKNOWN_TIER = "ask"


def unknown_action_tier() -> str:
    """The tier for an action that is in no table. Read from
    `[autonomy].unknown_action_tier`, and "ask" if that is missing or invalid.

    Fails closed twice over, deliberately: a config that says
    `unknown_action_tier = "auto"` is almost certainly a mistake or an attack,
    but this is not the place to refuse it - the gate decides policy. What is
    refused here is a value that is not a tier at all, because passing
    "definitely" back to a caller that compares against "never" would read as
    permission.
    """
    val = section("autonomy").get("unknown_action_tier", DEFAULT_UNKNOWN_TIER)
    val = str(val).strip().lower()
    if val not in TIERS:
        _warn_once(f"[autonomy].unknown_action_tier is {val!r}, which is not "
                   f"one of {TIERS}. Using {DEFAULT_UNKNOWN_TIER!r}.")
        return DEFAULT_UNKNOWN_TIER
    return val


def action_tier(action: str) -> str:
    """Which tier an action falls in: "auto", "notify", "ask" or "never".

    The contract is pinned by a surviving test, which is the only reason this
    function's behaviour is known rather than guessed - test_jobs.py:253:

        self.assertEqual(fw.action_tier("web_research"), "auto")

    and `jarvis-framework.toml` has `web_research = "auto"` under
    `[autonomy.tiers]`, so the lookup is that table, keyed by the action name
    exactly as written.

    An action that is not in the table gets `unknown_action_tier`. An action
    that is in the table with a value that is not a tier is treated as absent
    and warned about - a typo'd tier must not silently become permission.
    """
    tiers = section("autonomy").get("tiers")
    if not isinstance(tiers, dict):
        # [autonomy.tiers] is a sub-table of [autonomy], so a TOML parse gives
        # it back nested. If it is missing entirely, every action is unknown,
        # which fails closed - and is worth saying out loud, because a config
        # that lost its tier table looks identical from the outside to one
        # where every action really is unclassified.
        return unknown_action_tier()

    raw = tiers.get(str(action))
    if raw is None:
        return unknown_action_tier()

    val = str(raw).strip().lower()
    if val not in TIERS:
        _warn_once(f"[autonomy.tiers].{action} is {raw!r}, which is not one of "
                   f"{TIERS}. Treating it as unclassified.")
        return unknown_action_tier()
    return val


def all_tiers() -> dict:
    """Every classified action and its tier. INFERRED - no surviving caller,
    but `jarvis_gate --review` and the HUD's autonomy pane both need a way to
    show the table, and reaching into load_framework() twice for it is the
    thing this module exists to avoid."""
    tiers = section("autonomy").get("tiers")
    if not isinstance(tiers, dict):
        return {}
    return {k: str(v).strip().lower() for k, v in tiers.items()
            if str(v).strip().lower() in TIERS}


# --------------------------------------------------------------------------
#   The audit log
# --------------------------------------------------------------------------
#
# What the config promises, and therefore what this has to do:
#
#   log_directory = "~/.openjarvis/logs/"      -> expanduser, and honour it
#   persistence_implemented = true             -> "one JSON line each"
#   log_write_failures_are_visible = true      -> "A failed log write now
#                                                 prints once to stderr
#                                                 instead of vanishing."
#
# That last line is a requirement, not a description, and it is the reason
# this function is more than three lines long.

_LOG_LOCK = threading.Lock()
_LOG_FAILED = False


def log_dir() -> Path:
    """Where the log goes, honouring `[logging].log_directory`.

    Read fresh each call rather than resolved once at import. The surviving
    test suites redirect logging by patching `load_framework` to rewrite
    log_directory to a temp folder - if this were captured at import time,
    that patch would do nothing and every test run would write into the real
    ~/.openjarvis/logs.
    """
    cfg = section("logging")
    raw = cfg.get("log_directory")
    if raw:
        return Path(os.path.expanduser(str(raw)))
    return Path(LOG_DIR)


def logging_enabled() -> bool:
    cfg = section("logging")
    # Default true: the config ships with enabled = true, and a missing config
    # should not silently turn the audit trail off. A log that is not written
    # is indistinguishable from an event that did not happen.
    return bool(cfg.get("enabled", True))


def audit_log(event: str, detail: Optional[dict] = None) -> bool:
    """Append one JSON line to the audit log. Returns whether it was written.

    Called twelve times across the surviving modules, always as
    `fw.audit_log(event, detail)`, and always inside a `try: ... except:
    pass`. So callers already treat it as best-effort - but that is exactly
    why the failure has to be visible HERE. Every caller swallowing the
    exception plus this function raising silently equals an audit trail that
    stops working and tells nobody.

    WHAT IS NOT DONE HERE. This does not redact. `jarvis_gate._redact` is
    applied by the caller before the dict arrives, and `backend/README.md`
    records why that must not move: redaction is per-destination, and a
    redactor shared between a local log and an outbound push is how the same
    bug was shipped three times. A log-level redactor here would be a fourth.
    """
    global _LOG_FAILED
    if not logging_enabled():
        return False

    row = {
        "t": round(time.time(), 3),
        "iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "Z",
        "event": str(event),
        "detail": detail if isinstance(detail, dict) else {"value": detail},
    }
    try:
        # default=str so a Path, a datetime or a set cannot make the line
        # unserialisable. Losing the audit entry to a TypeError over a value's
        # type is a worse outcome than logging its repr.
        line = json.dumps(row, default=str, ensure_ascii=False)
    except Exception:
        line = json.dumps({"t": row["t"], "event": row["event"],
                           "detail": "<unserialisable>"})

    where = log_dir()
    try:
        with _LOG_LOCK:
            where.mkdir(parents=True, exist_ok=True)
            # One file per day. The config keeps 90 days; rotating by name
            # makes retention a matter of deleting files rather than rewriting
            # one growing file, which cannot be done safely while appending.
            name = f"jarvis-{time.strftime('%Y-%m-%d', time.gmtime())}.jsonl"
            with open(where / name, "a", encoding="utf-8", newline="\n") as fh:
                fh.write(line + "\n")
        _LOG_FAILED = False
        return True
    except Exception as exc:
        # "log_write_failures_are_visible = true". Once per outage, not once
        # per call: a disk that is full fails on every write, and a hundred
        # identical lines on stderr buries whatever the program was actually
        # doing.
        if not _LOG_FAILED:
            _LOG_FAILED = True
            print(f"jarvis_framework: audit log write FAILED ({type(exc).__name__}: "
                  f"{exc}) to {where}. Events are not being recorded.",
                  file=sys.stderr)
        return False


def prune_logs(days: Optional[int] = None) -> int:
    """Delete log files older than the retention window. Returns how many.

    INFERRED - nothing surviving calls this. It is here because
    `[logging].retention_days = 90` is a promise the config makes and nothing
    else in the backend can keep: a retention setting with no code behind it
    is precisely the "control that doesn't do anything" JARVIS-FRAMEWORK.md
    warns about.
    """
    keep = days if days is not None else section("logging").get("retention_days", 90)
    try:
        keep = int(keep)
    except (TypeError, ValueError):
        return 0
    if keep <= 0:
        return 0

    cutoff = time.time() - keep * 86400
    removed = 0
    where = log_dir()
    try:
        entries = list(where.glob("jarvis-*.jsonl"))
    except OSError:
        return 0
    for f in entries:
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
                removed += 1
        except OSError:
            continue
    return removed


# --------------------------------------------------------------------------
#   Told-you-so
# --------------------------------------------------------------------------

def status() -> dict:
    """What this module actually loaded. INFERRED, and worth having: the
    failure mode of a config layer is looking like it is working while every
    value is a default."""
    path = config_path()
    data = load_framework()
    return {
        "config_file": str(path) if path else None,
        "config_loaded": bool(data),
        "sections": sorted(data.keys()),
        "config_dir": str(CONFIG_DIR),
        "log_dir": str(log_dir()),
        "logging_enabled": logging_enabled(),
        "classified_actions": len(all_tiers()),
        "unknown_action_tier": unknown_action_tier(),
        "toml_parser": getattr(_toml, "__name__", None),
    }


if __name__ == "__main__":
    for k, v in status().items():
        print(f"  {k:<22} {v}")
