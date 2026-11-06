"""jarvis_power.py - is Jarvis awake, quiet, or asleep.

REBUILT. The original is gone; see jarvis_framework.py for the search.

The call sites, and the whole contract:

    jarvis_arbiter.py:181   mode = jarvis_power.current()
    jarvis_hud.py           jarvis_power.unload_for_exit() on the way out
    jarvis_power_switch.py  current() before a change, set_mode() after
    this module             enforce() - the clock's answer, made real

Everything else here is INFERRED from `[power]` in jarvis-framework.toml and
from `power_manage = "auto"` in the tier table, whose comment explains the
design: "Putting Jarvis into quiet/standby, or waking it, is the safe
direction either way, so it does not interrupt you for a yes. Changing the
rules that put it under on their OWN (quiet hours, the idle timer) is a config
change and waits."

So: changing MODE is free, changing the RULES is gated. This module does the
first and never the second - there is no setter here for quiet hours, on
purpose. The rows that DO write the rules are `jarvis_limits.LIMITS`' four
`standby_hours_*` rows, and `always_asks` on them is what puts the config change
to the owner on a card.

THE TWO RULES, AND WHAT THEY NOW DROP TO (2026-11-03)
Until this change `current()` returned a hard-coded "quiet" whenever the clock
was inside `[power]`'s window, and `should_standby()` was never called by
`current()` at all. `schedule_mode` and `idle_mode` - both in the shipped file,
both documented as what a window "drops TO" - were read by nothing, which the
file itself said out loud in a comment ("# not read"). So the shipped settings
file described a power this program did not have: the owner could not use the
hours to free a graphics card, and a window he set could never be anything but
Quiet.

Now:

  * inside `[power] schedule_enabled`'s window, `current()` returns
    `schedule_mode` ("quiet" or "standby");
  * when `[power] idle_enabled` has been idle for `idle_minutes`, it returns
    `idle_mode`;
  * a mode the owner CHOSE always wins. The rules only ever apply on top of
    "active", so an explicit Standby is never quietly turned into a shallower
    Quiet, and Quiet chosen by hand is not deepened to Standby behind the
    owner's back.

THE MODE IS STILL COMPUTED FROM THE CLOCK EVERY TIME. There is no background
thread flipping a variable, and there is deliberately no second copy of the
mode anywhere: `current()` recomputes from the clock on every call, so two
readers in the same second cannot disagree and nothing goes stale overnight.

`enforce()` IS THE OTHER HALF, AND IT IS NOT A SECOND SOURCE OF TRUTH.
A pure function can say "standby" but it cannot free a graphics card - a card
stays occupied until somebody asks Ollama to drop the model. So `enforce()`
exists to make the clock's answer REAL: when the rules say standby and the
stored mode is not standby yet, it asks `jarvis_power_switch.set_mode()` - the
ONE place in this repository that unloads a model, the same call a tap on the
Standby button makes - and every model it frees, and every one it could not, is
reported back and kept in `status()["last_unload"]`. `jarvis_limits`' rows are
what the owner changes; this is what happens when the hour arrives.

NOTHING IS UNLOADED WHILE SOMETHING IS USING IT. See `in_flight()`: a
multi-step task, a turn being answered, a Live conversation, or an approval
card waiting all hold it off, because unloading the model under any of them
kills the thing the owner is looking at. `enforce()` then does nothing at all
and says why; the next tick tries again. The check is in the code, not in a
document, because the failure it prevents is a blank answer at 23:00.

WHY A THREAD LIVES HERE AT ALL, WHEN ARCHITECTURE SECTION 12 SAYS "THE ONE
SCHEDULER". Section 12 is about things the owner SEES and DELETES - a job row
with a name in Coming up. The hours are a setting: no row, no identity, no
delete, and the owner's own toml is where they live. The job-shaped way to do
this already exists and is unchanged (`jarvis_standby_schedule.py`, kind
"standby"); the window is the config-shaped one the shipped toml already
promised. The thread is started ONLY when the hours are switched on - a PC that
never touches the setting runs exactly the code it ran before - and it never
sets the mode itself: it calls `enforce()`, which goes through set_mode().
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

#: What a rule is allowed to drop to. "active" is not a drop: a window whose
#: `schedule_mode` says "active" is a window that does nothing, which is a
#: sensible thing to write in a settings file and must not raise.
DEEP = ("quiet", "standby")

#: What `status()["why"]` says when this module's own clock rules made the
#: change. Deliberately NOT "the owner, from ..." (a tap it is not) and not
#: "the standby schedule" (that is `jarvis_standby_schedule.WHY`, a different
#: trigger with its own window): `jarvis_standby_schedule.who_set()` reads an
#: unrecognised `why` as "other" and then leaves the mode alone at its own
#: window's end, which is exactly right - each trigger wakes only what it put
#: to sleep, and `enforce()` below is what wakes this one.
WHY = "the standby hours"

#: How often the keeper asks whether the clock has crossed an edge. A small
#: number of seconds because the whole point is "at 23:00", not "some time
#: after 23:00"; it costs one dict lookup and a clock read per tick when the
#: feature is off, and it is not started at all then.
KEEPER_SECONDS = 30.0

_LOCK = threading.RLock()
_state = {"mode": "active", "since": time.time(), "why": "startup",
          "last_seen": time.time(),
          #: Somebody OTHER than this module's clock last chose the mode. The
          #: window then leaves the mode alone until the clock's answer next
          #: CHANGES (see `_edge`), so a tap on Active inside the owner's own
          #: hours is not overruled a few seconds later by the keeper.
          "manual": False,
          #: The rule's answer as of the last tick, or None before the first.
          "rule_seen": None}

#: Tests set this to False so no thread is started under them.
_KEEPER_AUTOSTART = True
_keeper_started = False


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

    THE KEY NAMES ARE THE ONES IN THE FILE. This read `quiet_hours_start` and
    `quiet_hours_end`; the shipped `[power]` section has `quiet_start` and
    `quiet_end`. Every lookup returned the default, so quiet hours never fired
    at any time of day - a setting that looked configured and did nothing.
    Measured against the real config: False at 00:30, 03:30, 06:30, 22:30 and
    23:30 with a 23:00-07:00 window.

    Handles a window that crosses midnight (22:00-07:00), which is the normal
    case and the one a naive `start <= t <= end` gets silently wrong - it
    would return False all night, every night, and the setting would look
    like it did nothing.
    """
    # `schedule_enabled` is also in the config and was also ignored. Fixing
    # only the names would have switched quiet hours ON while the config says
    # the schedule is off - a different wrong answer, arrived at by fixing
    # half the bug.
    if not bool(_cfg("enabled", True)) or not bool(_cfg("schedule_enabled", False)):
        return False
    start = _parse_hhmm(_cfg("quiet_start", ""))
    end = _parse_hhmm(_cfg("quiet_end", ""))
    if not start or not end:
        return False
    t = (now or datetime.now()).time()
    if start <= end:
        return start <= t < end
    return t >= start or t < end


# ---------------------------------------------------------------------------
#   What the two rules ask for
# ---------------------------------------------------------------------------
def _drop(key: str) -> str:
    """The mode `key` names, clamped to the two a rule may drop to.

    A missing key, an empty one, a typo or "active" all read as "quiet" - the
    behaviour every version of this file has had, and the shallower of the two
    choices. Refusing to act on a word the file cannot mean is better than
    guessing "standby" from a spelling mistake and freeing a card the owner
    did not ask to free.
    """
    want = str(_cfg(key, "quiet") or "quiet").strip().lower()
    return want if want in DEEP else "quiet"


def schedule_drop(now: Optional[datetime] = None) -> Optional[str]:
    """What the quiet-hours window asks for right now: "quiet"/"standby"/None.

    This is the one place `schedule_mode` is read. It is public so the decision
    table can be tested without a clock, a config file or a model.
    """
    if not in_quiet_hours(now):
        return None
    return _drop("schedule_mode")


def should_standby() -> bool:
    """Has the idle timer run out? (Named for the only drop it used to mean.)

    `idle_minutes`, gated by `idle_enabled` - both real keys, neither read
    before. The old name `idle_standby_minutes` is in no config anywhere.
    """
    if not bool(_cfg("enabled", True)) or not bool(_cfg("idle_enabled", False)):
        return False
    mins = _cfg("idle_minutes", 0)
    try:
        mins = float(mins)
    except (TypeError, ValueError):
        return False
    return mins > 0 and idle_seconds() >= mins * 60


def idle_drop() -> Optional[str]:
    """What the idle timer asks for right now: "quiet"/"standby"/None."""
    return _drop("idle_mode") if should_standby() else None


def rule(now: Optional[datetime] = None) -> tuple:
    """(mode, why) the clock asks for, or (None, "") when no rule applies.

    The quiet-hours window is asked first: it is the one the owner set a time
    for. The idle timer can then only ever add to it, never override it, so
    two rules in force at once cannot fight over the same minute.
    """
    if not bool(_cfg("enabled", True)):
        return (None, "")
    got = schedule_drop(now)
    if got:
        return (got, WHY)
    got = idle_drop()
    if got:
        return (got, "the idle timer")
    return (None, "")


def current() -> str:
    """The mode right now, as a string. Called by jarvis_arbiter.

    The rules are applied here rather than by a timer, so there is nothing to
    fall out of step: the answer is computed from the clock every time it is
    asked for. A background thread flipping a variable would be a second
    source of truth.

    A mode the owner CHOSE wins over a rule. `_state["mode"]` is only what
    somebody asked for through set_mode(); when it is anything but "active" the
    owner (or the standby schedule, or a task) meant it, and a clock window
    must not quietly soften or deepen it.

    The keeper is started from here as well as from `status()`, so the hours
    work on a PC with neither app open: `current()` is what the arbiter and
    several feature modules already call, and it is the one function this
    module can be sure is reached. Starting it changes nothing about the
    answer - the mode above is computed from the clock either way - and it is
    one attribute read once the thread exists.
    """
    with _LOCK:
        mode = _state["mode"]
        manual = bool(_state["manual"])
    if mode == "active" and not manual:
        # A rule only ever applies on top of "active": a mode somebody chose -
        # by hand, by the standby schedule, by the idle rule - is left alone.
        got, _ = rule()
        mode = got or mode
    _maybe_start_keeper()
    return mode


def set_mode(mode: str, why: str = "") -> str:
    """Change mode. Tier `power_manage` = auto, so this never asks.

    An unknown mode is refused rather than stored: a caller that set
    "sleeping" and got it back would believe Jarvis was in a state that
    nothing else in the codebase recognises.

    A change made by anything but this module's own clock marks the mode as
    `manual`, which stops the window overruling it until the clock's answer
    next changes. `enforce()` passes `why=WHY`; a tap in either app passes
    "the owner, from ...", and the standby schedule passes its own words.
    """
    mode = str(mode).strip().lower()
    if mode not in MODES:
        raise ValueError(f"unknown power mode {mode!r}; expected one of {MODES}")
    with _LOCK:
        if _state["mode"] != mode:
            _state.update({"mode": mode, "since": time.time(), "why": why or "asked"})
            if (why or "") != WHY:
                _state["manual"] = True
    _announce()
    _maybe_start_keeper()
    return mode


def touch() -> None:
    """Note that the owner is present. Resets the idle timer."""
    with _LOCK:
        _state["last_seen"] = time.time()


def idle_seconds() -> float:
    with _LOCK:
        return time.time() - _state["last_seen"]


# ---------------------------------------------------------------------------
#   What is using the machine right now
# ---------------------------------------------------------------------------
#: Activity states that mean something is being answered or done. Any other
#: state ("idle", "" or a state a later module invents) does not hold standby
#: off: this is an allowlist of BUSY, not of free, because a new state that
#: nobody classified is far more likely to be a quiet one than a turn.
_BUSY_ACTIVITY = ("thinking", "speaking", "working")


def in_flight(include_tasks: bool = True) -> Optional[str]:
    """A plain-words reason NOT to unload right now, or None.

    Every branch is a real signal in this codebase, not an assumption:

      * `jarvis_task_control.running()` - a multi-step task continues on its
        own between turns, and the model it is using would disappear under it.
        `include_tasks=False` skips this one branch, for `jarvis_power_switch`,
        which keeps its own task check and every word of it.
      * `jarvis_events.activity()` - the HUD sets "thinking" when a turn starts,
        "speaking"/"working" while it runs and "idle" when it ends. That is the
        same signal both apps show the owner, so a guard built on it cannot
        disagree with what he can see. A busy mark that has shown no progress
        for `jarvis_events.ACTIVITY_STALE_SECONDS` is a LEFTOVER from a turn
        that ended without clearing it (the owner's ruling of 2026-11-06), so
        it is auto-cleared here - the one definition of "stale" lives in
        jarvis_events - and this branch then sees "idle". A leftover must not
        hold standby for hours either.
      * a Live conversation - `jarvis_chatbot`'s session, in the states the
        routes themselves treat as live, plus the comparison and support lanes,
        whose own `live()` predicates are the ones the routes already refuse a
        second start with.
      * `jarvis_gate.pending()` - a card on screen is a question being asked.

    Never raises: a module that is not installed is not a reason to stay awake
    for ever, and a guard that raises would be a guard that unloads.
    """
    if include_tasks:
        try:
            import jarvis_task_control
            if jarvis_task_control.running():
                return "a task is running"
        except Exception:
            pass
    try:
        import jarvis_events
        # The one definition of "a stale busy mark" and the one place that
        # clears it: a clear here is announced, audited and logged once.
        try:
            jarvis_events.clear_if_stale()
        except AttributeError:
            pass                      # an older jarvis_events: nothing to do
        state = str((jarvis_events.activity() or {}).get("state") or "").strip().lower()
        if state in _BUSY_ACTIVITY:
            return f"Jarvis is {state} right now"
    except Exception:
        pass
    try:
        import jarvis_chatbot
        # The session states the routes themselves treat as a live session
        # (jarvis_chatbot_routes.LIVE), read from there when it is importable so
        # this guard cannot drift from the one that refuses a second start.
        try:
            from jarvis_chatbot_routes import LIVE as _LIVE_STATES
        except Exception:
            _LIVE_STATES = ("asking", "approved", "running", "paused")
        session = (jarvis_chatbot.view("") or {}).get("session")
        if isinstance(session, dict) and session.get("state") in _LIVE_STATES:
            return "a Live conversation is running"
    except Exception:
        pass
    for name, live in (("jarvis_chatbot_compare", "live"), ("jarvis_support", "live")):
        try:
            mod = __import__(name)
            if getattr(mod, live)():
                return "another conversation is running"
        except Exception:
            continue
    try:
        import jarvis_gate
        if jarvis_gate.pending():
            return "an approval card is waiting"
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
#   Making the clock's answer real
# ---------------------------------------------------------------------------
def _audit(event: str, detail: dict) -> None:
    try:
        import jarvis_framework as _fw
        _fw.audit_log(event, detail)
    except Exception:
        pass


def _edge(got: Optional[str]) -> bool:
    """Note the rule's answer, and forget a manual choice when it CHANGES.

    Returns True when a manual choice is still in force. On a change of the
    clock's answer - the window opening, the window closing, the idle timer
    firing - the owner's earlier choice stops applying: whatever the new
    answer is, it is the setting he made, and he has just had the boundary the
    window was waiting for.
    """
    with _LOCK:
        seen = _state["rule_seen"]
        if seen != got:
            _state["rule_seen"] = got
            if seen is not None:
                _state["manual"] = False
        return bool(_state["manual"])


def _run(now: Optional[datetime], wait_s: float) -> dict:
    """Do one edge. Returns {"changed": bool, ...} and never raises."""
    got, why = rule(now)
    if _edge(got):
        with _LOCK:
            chose = str(_state.get("why") or "")
        return {"changed": False, "manual": True, "said":
                (f"Nothing changed: that is the mode you or another trigger chose "
                 f"({chose or 'by hand'}) until the hours next change.")}
    with _LOCK:
        stored = str(_state["mode"])
        who = str(_state.get("why") or "")
    # Going UNDER: the rules want standby and the stored mode is not standby.
    if got == "standby" and stored != "standby":
        held = in_flight()
        if held:
            said = {"changed": False, "held": held,
                    "said": f"Left the graphics cards loaded: {held}."}
            with _LOCK:
                _state["last_hold"] = dict(said, at=time.time())
            return said
        return _switch("standby", wait_s)
    # COMING BACK UP: only a standby this module's own rules made.
    if got != "standby" and stored == "standby" and who == WHY:
        return _switch("active", wait_s)
    return {"changed": False, "said": ""}


def _switch(mode: str, wait_s: float) -> dict:
    """set_mode() through the one module that unloads, best-effort."""
    try:
        import jarvis_power_switch as switch
        code, out = switch.set_mode(mode, by=WHY, why=WHY, wait_s=wait_s, force=True)
    except Exception as exc:  # never let a clock edge crash a turn
        return {"changed": False, "said": f"Nothing changed ({type(exc).__name__})."}
    out = out if isinstance(out, dict) else {}
    if code == 200 and out.get("changed"):
        said = str(out.get("message") or "")
        out = dict(out, changed=True, said=said, at=time.time())
        if mode == "standby":
            with _LOCK:
                _state["last_unload"] = {k: out.get(k) for k in
                                         ("unloaded", "still_loaded", "also", "note", "at")
                                         if out.get(k) is not None}
        _audit("power.hours", {"to": mode, "unloaded": out.get("unloaded") or []})
        return out
    return {"changed": False, "said": str(out.get("message") or out.get("error") or "")}


def enforce(now: Optional[datetime] = None, *, wait_s: float = 30.0) -> dict:
    """Make the clock's answer real, now. The one entry point for both edges.

    Called by the keeper below, and safe to call from anywhere: it returns a
    small dict saying what it did (or why it did nothing) and never raises.
    Idempotent - asking twice in the same minute does nothing the second time,
    because it acts on the STORED mode, which is the one set_mode() changes.

    `force` is passed to set_mode because inside the window `current()` already
    READS "standby" (the window itself is what makes it standby) while the
    stored mode is still "active". Without it, set_mode would answer "Already
    standby" and free nothing - the exact bug this feature exists to avoid.
    """
    try:
        return _run(now, wait_s)
    except Exception as exc:  # a clock edge must never crash a turn
        return {"changed": False, "said": f"Nothing changed ({type(exc).__name__})."}


def _keeper() -> None:
    while True:
        try:
            enforce()
        except Exception:
            pass
        time.sleep(KEEPER_SECONDS)


def _hours_on() -> bool:
    return bool(_cfg("enabled", True)) and bool(_cfg("schedule_enabled", False))


def start_keeper() -> bool:
    """Start the one keeper thread, if the hours are switched on. Idempotent.

    Returns whether a thread is running afterwards. Off means off: a PC whose
    `schedule_enabled` is false (the shipped value) never starts it, so nothing
    about that PC's timing changes.
    """
    global _keeper_started
    with _LOCK:
        if _keeper_started:
            return True
        if not _KEEPER_AUTOSTART or not _hours_on():
            return False
        _keeper_started = True
    try:
        threading.Thread(target=_keeper, name="jarvis-standby-hours",
                         daemon=True).start()
        return True
    except Exception:
        with _LOCK:
            _keeper_started = False
        return False


def _maybe_start_keeper() -> None:
    """Cheap guard so the hot paths below do not pay for a config read."""
    if _keeper_started or not _KEEPER_AUTOSTART:
        return
    start_keeper()


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
    got, why = rule()
    s["mode"] = current()
    s["asked_for"] = got or ""
    s["asked_why"] = why
    s["quiet_hours"] = in_quiet_hours()
    s["schedule_enabled"] = bool(_cfg("schedule_enabled", False))
    s["schedule_mode"] = _drop("schedule_mode")
    s["idle_enabled"] = bool(_cfg("idle_enabled", False))
    s["idle_mode"] = _drop("idle_mode")
    s["idle_seconds"] = round(idle_seconds(), 1)
    s["keeper"] = bool(_keeper_started)
    _maybe_start_keeper()
    return s


if __name__ == "__main__":
    for k, v in status().items():
        print(f"  {k:<14} {v}")
