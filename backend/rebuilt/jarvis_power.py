"""jarvis_power.py - is Jarvis awake, quiet, or asleep.

REBUILT. The original is gone; see jarvis_framework.py for the search.

Two call sites, and they are the whole contract:

    jarvis_arbiter.py:178   mode = jarvis_power.current()
    jarvis_hud.py:2157      jarvis_power.unload_for_exit()

Everything else here is INFERRED from `[power]` in jarvis-framework.toml and
from `power_manage = "auto"` in the tier table, whose comment explains the
design: "Putting Jarvis into quiet/standby, or waking it, is the safe
direction either way, so it does not interrupt you for a yes. Changing the
rules that put it under on their OWN (quiet hours, the idle timer) is a config
change and waits."

So: changing MODE is free, changing the RULES is gated. This module does the
first and never the second - there is no setter here for quiet hours, on
purpose.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, time as _time
from typing import Optional

try:
    import jarvis_framework as fw
except Exception:
    fw = None  # type: ignore

#: Weakest to deepest. `active` answers; `quiet` answers but does not speak
#: first; `standby` has unloaded the model and wakes on demand.
MODES = ("active", "quiet", "standby")

_LOCK = threading.RLock()
_state = {"mode": "active", "since": time.time(), "why": "startup",
          "last_seen": time.time()}


def _cfg(key: str, default=None):
    if fw is None:
        return default
    try:
        return fw.load_framework().get("power", {}).get(key, default)
    except Exception:
        return default


def _parse_hhmm(s: str) -> Optional[_time]:
    try:
        h, m = str(s).split(":")
        return _time(int(h), int(m))
    except Exception:
        return None


def in_quiet_hours(now: Optional[datetime] = None) -> bool:
    """Is the clock inside the configured quiet window?

    Handles a window that crosses midnight (22:00-07:00), which is the normal
    case and the one a naive `start <= t <= end` gets silently wrong - it
    would return False all night, every night, and the setting would look
    like it did nothing.
    """
    start = _parse_hhmm(_cfg("quiet_hours_start", ""))
    end = _parse_hhmm(_cfg("quiet_hours_end", ""))
    if not start or not end:
        return False
    t = (now or datetime.now()).time()
    if start <= end:
        return start <= t < end
    return t >= start or t < end


def current() -> str:
    """The mode right now, as a string. Called by jarvis_arbiter.

    Quiet hours are applied here rather than by a timer, so there is nothing
    to fall out of step: the answer is computed from the clock every time it
    is asked for. A background thread flipping a variable would be a second
    source of truth.
    """
    with _LOCK:
        mode = _state["mode"]
    if mode == "active" and in_quiet_hours():
        return "quiet"
    return mode


def set_mode(mode: str, why: str = "") -> str:
    """Change mode. Tier `power_manage` = auto, so this never asks.

    An unknown mode is refused rather than stored: a caller that set
    "sleeping" and got it back would believe Jarvis was in a state that
    nothing else in the codebase recognises.
    """
    mode = str(mode).strip().lower()
    if mode not in MODES:
        raise ValueError(f"unknown power mode {mode!r}; expected one of {MODES}")
    with _LOCK:
        if _state["mode"] != mode:
            _state.update({"mode": mode, "since": time.time(), "why": why or "asked"})
    _announce()
    return mode


def touch() -> None:
    """Note that the owner is present. Resets the idle timer."""
    with _LOCK:
        _state["last_seen"] = time.time()


def idle_seconds() -> float:
    with _LOCK:
        return time.time() - _state["last_seen"]


def should_standby() -> bool:
    mins = _cfg("idle_standby_minutes", 0)
    try:
        mins = float(mins)
    except (TypeError, ValueError):
        return False
    return mins > 0 and idle_seconds() >= mins * 60


def _announce() -> None:
    try:
        import jarvis_events
        jarvis_events.BUS.note("power", current(), "power")
    except Exception:
        pass


def unload_for_exit() -> dict:
    """Release the model before the process exits. Called by jarvis_hud.

    Best-effort by design: this runs on the way out, and an exception here
    would turn a clean shutdown into a traceback the owner cannot act on -
    the process is going away regardless.

    It asks Ollama to drop the resident model rather than killing anything. A
    model left resident holds several gigabytes of VRAM after Jarvis has
    gone, which shows up as "my graphics card is full and nothing is running".
    """
    freed = []
    try:
        import jarvis_models
        for name in (getattr(jarvis_models, "resident_models", lambda: [])() or []):
            try:
                jarvis_models.unload(name)
                freed.append(name)
            except Exception:
                continue
    except Exception:
        pass
    with _LOCK:
        _state.update({"mode": "standby", "since": time.time(), "why": "exit"})
    return {"unloaded": freed}


def status() -> dict:
    with _LOCK:
        s = dict(_state)
    s["mode"] = current()
    s["quiet_hours"] = in_quiet_hours()
    s["idle_seconds"] = round(idle_seconds(), 1)
    return s


if __name__ == "__main__":
    for k, v in status().items():
        print(f"  {k:<14} {v}")
