"""What one answer cost the graphics card, in joules - numbers only.

WHAT IT IS FOR

A local assistant that runs on the owner's own graphics card has a running
cost that no screen shows: watts, minute after minute. This module reads the
card's own power draw while an answer is being written and turns the answer
into a single honest figure - joules per token - so "is the bigger model worth
it" can be answered with a number instead of a feeling.

The idea comes from OpenJarvis's `telemetry/energy_monitor.py` (Apache-2.0).
No code was copied from it; this is written fresh for Epic-Jarvis. OpenJarvis
uploads its telemetry to a service. That is exactly the part not taken.

OFF UNTIL ASKED

Nothing is read and nothing is written unless `[energy] enabled = true` is in
the framework config (`jarvis-framework.toml`) or `JARVIS_ENERGY=1` is set in
the environment. `enabled()` says which. The switch is off by default because
polling the card costs a little power of its own, and because a measurement
nobody asked for is a measurement that should not exist.

WHAT IT KEEPS, AND WHAT IT NEVER KEEPS

Numbers only: watts, megabytes of card memory, a utilisation percentage, a
duration, a token count, and the joules worked out from them. NEVER a prompt,
an answer, or a word of a fact. There is no field that could hold text, and
`record()` builds its own row rather than accepting one, so a caller cannot
put words in it by mistake. Nothing leaves the PC: the only program this
module ever runs is `nvidia-smi`, which is on this machine and talks to the
card in this machine. There is no upload, no leaderboard and no analytics.

WHERE IT GOES

`energy.jsonl`, in the same settings folder everything else in Jarvis uses -
`jarvis_framework.CONFIG_DIR` if the framework is importable, else
`OPENJARVIS_CONFIG_DIR`, else `JARVIS_CONFIG_DIR`, else `~/.openjarvis` -
exactly the rule `jarvis_speed.py` follows, so both files sit side by side.

The file is capped at the most recent 500 rows: an energy row is small, but
this is a curiosity, not a ledger, and a file that grows for years is a file
nobody reads.

SAFE WHEN THE CARD OR THE TOOL IS MISSING

That is the normal case on a machine without an NVIDIA card, and it is the
normal case in CI. `available()` is False, `sample()` returns `{}`, `record()`
writes nothing and returns `{}`, and `status()` explains in one plain sentence
what is missing. Nothing in this module ever raises.
"""
from __future__ import annotations

import json
import math
import os
import shutil
import statistics
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, Iterable, Optional

SCHEMA = 1
FILE_NAME = "energy.jsonl"
#: How many rows the file keeps. The oldest are dropped from the front when a
#: new row would go past this - see `EnergyLog.append()`.
MAX_ROWS = 500
#: The one query this module asks nvidia-smi. CSV, no header line, no unit
#: suffixes, so every field is a plain number.
QUERY = "power.draw,memory.used,utilization.gpu"
#: The environment override that turns the feature on without editing the toml
#: (`JARVIS_ENERGY=1`).
ENV_SWITCH = "JARVIS_ENERGY"
#: A card reading is a small subprocess; it is never given long to answer.
_TIMEOUT_S = 4.0
#: The refresh a watcher should use between samples, in seconds. Reading the
#: card costs a little power of its own, so this is not 0.05.
SAMPLE_EVERY_S = 1.0

#: Said by `status()["why"]` when there is nothing to explain. A plain
#: sentence, never an empty string, so a screen has something to show.
_WORKING = "the graphics card's energy is being measured"


def _config_dir() -> Path:
    """Same rule as jarvis_speed._config_dir() and import_history: the real
    framework's CONFIG_DIR if importable, otherwise OPENJARVIS_CONFIG_DIR,
    otherwise JARVIS_CONFIG_DIR, otherwise ~/.openjarvis."""
    try:
        import jarvis_framework as fw  # type: ignore
        if getattr(fw, "CONFIG_DIR", None):
            return Path(fw.CONFIG_DIR)
    except Exception:
        pass
    env = os.environ.get("OPENJARVIS_CONFIG_DIR") or os.environ.get("JARVIS_CONFIG_DIR")
    if env:
        return Path(os.path.expanduser(env))
    return Path(os.path.expanduser("~")) / ".openjarvis"


def default_path() -> Path:
    return _config_dir() / FILE_NAME


def _framework_setting(key: str, default=None):
    """`[energy] <key>` from the framework config, or `default` when the
    framework cannot be imported, the section is missing, or the value is not
    the shape asked for. Never raises - a config that cannot be read must not
    be able to stop an answer."""
    try:
        import jarvis_framework as fw  # type: ignore
        section = (fw.load_framework() or {}).get("energy") or {}
        if not isinstance(section, dict):
            return default
        val = section.get(key, default)
        return default if val is None else val
    except Exception:
        return default


def enabled() -> bool:
    """Is energy measurement switched on? `[energy] enabled = true` in the
    framework config, or `JARVIS_ENERGY=1`. Off unless one of them says so."""
    try:
        env = (os.environ.get(ENV_SWITCH) or "").strip().lower()
        if env in ("1", "true", "yes", "on"):
            return True
        return _framework_setting("enabled", False) is True
    except Exception:
        return False


def available() -> bool:
    """Is `nvidia-smi` on PATH? False on a machine with no NVIDIA card, which
    is the normal case in CI and needs no explanation beyond `status()`."""
    try:
        return bool(shutil.which("nvidia-smi"))
    except Exception:
        return False


def _clean_sample(row) -> dict:
    """A reading, with only the four number fields that may be in one. A text
    field, a missing field or a nonsense value is dropped, never stored."""
    out: dict = {}
    if not isinstance(row, dict):
        return out
    for key in ("power_w", "mem_mb", "util_pct"):
        val = row.get(key)
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            continue
        if not math.isfinite(float(val)) or val < 0:
            continue
        out[key] = float(round(val, 3))
    at = row.get("at")
    if isinstance(at, bool) or not isinstance(at, (int, float)) or not math.isfinite(float(at)):
        return {}
    out["at"] = int(at)
    # Nothing was actually read: a row of bare timestamps is not a reading.
    if not any(k in out for k in ("power_w", "mem_mb", "util_pct")):
        return {}
    return out


def _default_run(argv: list) -> str:
    """Run nvidia-smi and hand back its stdout as text. Never raises; a
    missing program or a refusal comes back as an empty string."""
    try:
        done = subprocess.run(argv, capture_output=True, timeout=_TIMEOUT_S,
                              check=False)
    except (OSError, subprocess.SubprocessError):
        return ""
    out = done.stdout or b""
    if isinstance(out, bytes):
        return out.decode("utf-8", "replace")
    return str(out)


def _numbers_in(text: str) -> list:
    """Every number in one CSV line, in order. nvidia-smi writes `[N/A]` for a
    value it cannot read (a card in a virtual machine, an old driver), and
    that field is skipped rather than guessed at."""
    vals = []
    for piece in str(text or "").split(","):
        piece = piece.strip()
        if not piece:
            continue
        cleaned = piece.split()[0]          # drop any unit nvidia-smi printed
        try:
            n = float(cleaned)
        except (TypeError, ValueError):
            continue
        if math.isfinite(n) and n >= 0:
            vals.append(n)
    return vals


def sample(which: Optional[int] = None, *,
           run: Optional[Callable[[list], str]] = None) -> dict:
    """One reading from the card: `{"power_w", "mem_mb", "util_pct", "at"}`.

    `which` is nvidia-smi's own card number (0 for the first card); None asks
    about the first card it lists, which on the owner's PC is the one with the
    monitor. `run` takes the argument list and returns nvidia-smi's stdout -
    the tests hand in a fake one, so nothing here ever needs a graphics card.

    Returns `{}` when the card cannot be read: no nvidia-smi, a card that
    reports `[N/A]`, a driver that takes too long, or anything else at all.
    This function does not raise, ever.
    """
    try:
        argv = ["nvidia-smi", f"--query-gpu={QUERY}", "--format=csv,noheader,nounits"]
        if which is not None:
            try:
                argv += ["-i", str(int(which))]
            except (TypeError, ValueError):
                pass
        text = (run or _default_run)(argv)
        line = ""
        for candidate in str(text or "").splitlines():
            if candidate.strip():
                line = candidate
                break
        if not line:
            return {}
        nums = _numbers_in(line)
        row: dict = {"at": int(time.time())}
        if len(nums) > 0:
            row["power_w"] = nums[0]
        if len(nums) > 1:
            row["mem_mb"] = nums[1]
        if len(nums) > 2:
            row["util_pct"] = nums[2]
        return _clean_sample(row)
    except Exception:
        return {}


def _mean_watts(samples: Iterable) -> Optional[float]:
    """The mean power draw of the readings that carry one. None when none do."""
    try:
        vals = [s["power_w"] for s in (samples or [])
                if isinstance(s, dict) and isinstance(s.get("power_w"), (int, float))
                and not isinstance(s.get("power_w"), bool) and s["power_w"] >= 0]
    except Exception:
        return None
    if not vals:
        return None
    return statistics.fmean(vals)


def _any_number(*vals) -> bool:
    for v in vals:
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            return False
        if not math.isfinite(float(v)) or v < 0:
            return False
    return True


class EnergyLog:
    """Append-only JSON lines, capped at the most recent `MAX_ROWS` rows.

    Never raises: an energy note that can break an answer is worse than no
    energy note. The cap is enforced on write - the file is rewritten only
    when it has actually gone over - so the common case is one cheap append.
    """

    _lock = threading.Lock()

    def __init__(self, path: Optional[Path] = None, *, max_rows: int = MAX_ROWS):
        self.path = Path(path) if path else default_path()
        self.max_rows = max(1, int(max_rows))

    def append(self, row: dict) -> bool:
        try:
            with self._lock:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n")
                self._trim()
            return True
        except OSError:
            return False

    def _trim(self) -> None:
        """Keep the last `max_rows` lines. Silent about anything that goes
        wrong: a file that could not be trimmed is still a file."""
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            over = len(lines) - self.max_rows
            if over <= 0:
                return
            with open(self.path, "w", encoding="utf-8") as f:
                f.writelines(lines[over:])
        except OSError:
            return

    def tail(self, n: Optional[int] = None) -> list:
        """The last `n` rows, oldest first - or all of them, up to the cap."""
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except OSError:
            return []
        rows = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict):
                rows.append(row)
        return rows if not n or n <= 0 else rows[-n:]


def record(tokens, seconds, *, samples=None, which: Optional[int] = None,
           log: Optional[EnergyLog] = None,
           run: Optional[Callable[[list], str]] = None) -> dict:
    """One finished answer, as energy.

        joules            mean watts x seconds
        joules_per_token  joules / tokens
        tokens_per_joule  tokens / joules
        tokens_per_second tokens / seconds

    `samples` are the readings taken while the answer was written (the mean of
    their power draw is used); with none given, one reading is taken now, with
    `run` if a caller handed one in. `tokens` and `seconds` may both be None -
    a figure that cannot be worked out from them is left out of the row rather
    than guessed at.

    Returns the row: what was appended, and what `status()` will call "last".
    Returns `{}` and writes nothing when the feature is off, when nvidia-smi
    is missing, when no power draw could be read, or when the file cannot be
    written (the row returned is the row on file, so an unwritable file gives
    no row rather than a figure that only looks recorded). Never raises.
    """
    try:
        if not enabled() or not available():
            return {}
        mean_w = _mean_watts(samples)
        if mean_w is None:
            one = sample(which, run=run)
            if not one:
                return {}
            mean_w = one.get("power_w")
        if mean_w is None:
            return {}

        tok = None
        if isinstance(tokens, (int, float)) and not isinstance(tokens, bool):
            if math.isfinite(float(tokens)) and tokens > 0:
                tok = float(tokens)
        secs = None
        if isinstance(seconds, (int, float)) and not isinstance(seconds, bool):
            if math.isfinite(float(seconds)) and seconds > 0:
                secs = float(seconds)

        joules = float(mean_w) * secs if secs is not None else None
        row: dict = {
            "v": SCHEMA,
            "at": int(time.time()),
            "power_w": round(float(mean_w), 3),
        }
        if tok is not None:
            row["tokens"] = int(round(tok))
        if secs is not None:
            row["seconds"] = round(secs, 3)
        if joules is not None:
            row["joules"] = round(joules, 3)
            if tok is not None:
                row["joules_per_token"] = round(joules / tok, 6)
                row["tokens_per_joule"] = round(tok / joules, 6) if joules > 0 else None
        if secs is not None and tok is not None:
            row["tokens_per_second"] = round(tok / secs, 3)
        row = {k: v for k, v in row.items() if v is not None}
        # The row returned is the row on file, so a file that could not be
        # written answers `{}` like every other failure here - rather than a
        # figure that looks recorded and is not.
        if not (log or EnergyLog()).append(row):
            return {}
        return row
    except Exception:
        return {}


def status(log: Optional[EnergyLog] = None) -> dict:
    """What a screen needs to explain this feature, in one call.

        enabled  is the switch on?
        available  is nvidia-smi here?
        why      ONE plain sentence naming what is missing, or what is off
        last     the most recent row on file, or None
        mean_joules_per_token  the mean over the rows that carry one, or None
        n        how many rows are on file

    Never raises, and never returns a bare False without a sentence saying
    why - a switch that is off for an unknown reason is the thing this is
    meant to avoid.
    """
    out = {"enabled": False, "available": False, "why": "",
           "last": None, "mean_joules_per_token": None, "n": 0}
    try:
        out["enabled"] = enabled()
        out["available"] = available()
        try:
            lg = log or EnergyLog()
            rows = lg.tail(MAX_ROWS)
            n = len(rows)
            out["n"] = n
            out["last"] = rows[-1] if rows else None
            vals = [r.get("joules_per_token") for r in rows
                    if isinstance(r.get("joules_per_token"), (int, float))
                    and not isinstance(r.get("joules_per_token"), bool)]
            if vals:
                out["mean_joules_per_token"] = round(statistics.fmean(vals), 6)
        except Exception:
            pass

        if not out["available"]:
            out["why"] = "the card's power draw cannot be read on this PC"
        elif not out["enabled"]:
            out["why"] = ("energy measurement is off; set [energy] enabled = true "
                          "in the framework config to turn it on")
        else:
            out["why"] = _WORKING
        return out
    except Exception:
        out["why"] = "the card's power draw cannot be read on this PC"
        return out
