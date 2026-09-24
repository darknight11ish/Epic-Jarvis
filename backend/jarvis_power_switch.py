"""jarvis_power_switch.py - the Active / Quiet / Standby switch the apps lacked.

WHAT WAS MISSING
`/api/status` reports the power mode and a `power` event says when it
changes, but nothing could CHANGE it: the phone's quick-settings tile says
so in its own comment, and the desktop's FAQ explains Quiet and Standby
without anywhere to choose them. `jarvis_power.set_mode()` existed with no
route to it.

WHAT THIS DOES (power-mode.patch adds `POST /api/power`)
    {"mode": "active" | "quiet" | "standby"}

    active    answers, and may speak first.
    quiet     answers, but does not start things on its own.
    standby   also frees the graphics card: the loaded model is unloaded
              (what the desktop FAQ promises), so the next answer takes
              5-15 seconds while it loads again.

PERMISSION - the one model, and why it does not ask by default
It goes through jarvis_gate.check("power_manage", ...), like everything else.
The owner's jarvis-framework.toml sets `power_manage = "auto"`, with the
reason written next to it: "Putting Jarvis into quiet/standby, or waking it,
is the safe direction either way, so it does not interrupt you for a yes."
Nothing here overrides that: set the tier to "ask" in that file and a card
appears, and this waits for it. Both directions are treated the same because
that file says both are safe; waking only restores the ordinary state. The
apps hold WAKING on a stale link (rule 4) and let going quieter through.

What is still gated elsewhere and NOT reachable from here: the RULES that put
Jarvis under on their own (quiet hours, the idle timer) - that is
`change_own_config`, and there is no setter for it on purpose.

REFUSED
Standby while a multi-step task is running (unloading the model under it
would break it): stop the task first. With the tier set to "ask", that is
checked again AFTER the card is approved, before anything is unloaded - a
task may have started while the card waited.

A second change while a power card is still waiting (409): approve or deny
that one first. Otherwise two cards could be up at once, and the one
answered last - not the one asked for last - would decide the mode.
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Optional

MODES = ("active", "quiet", "standby")

_WORDS = {
    "active": "Active: Jarvis answers, and may speak first.",
    "quiet": "Quiet: Jarvis still answers you, but starts nothing on its own.",
    "standby": ("Standby: Jarvis frees the graphics card by unloading the model. The "
                "next answer takes 5-15 seconds while it loads again."),
}


def _gate_check(action: str, detail: dict, prompt: str):
    """jarvis_gate.check(), failing CLOSED on any error."""
    class _Refused:
        allowed = False
        outcome = "refused"

        def __init__(self, reason):
            self.reason = reason
    try:
        import jarvis_gate
    except Exception as exc:
        return _Refused(f"the approval gate is not available here ({exc})")
    try:
        return jarvis_gate.check(action, detail, prompt=prompt)
    except Exception as exc:
        return _Refused(f"the approval gate raised {type(exc).__name__}")


def _running_tasks() -> list:
    try:
        import jarvis_task_control
        return jarvis_task_control.running()
    except Exception:
        return []


def _unload_models(models) -> dict:
    """Unload whatever model is resident. Best-effort; says what happened."""
    try:
        if models is None:
            import jarvis_models as models
        names = list((getattr(models, "resident_models", lambda: [])() or []))
        unload = getattr(models, "unload", None)
    except Exception as exc:
        return {"unloaded": [], "note": f"could not ask which model is loaded ({exc})"}
    if unload is None:
        return {"unloaded": [], "note": "this backend's jarvis_models has no unload(); "
                                        "the model stays on the graphics card"}
    done = []
    for n in names:
        try:
            unload(n)
            done.append(n)
        except Exception:
            continue
    return {"unloaded": done}


_PENDING_LOCK = threading.Lock()
#: The one power card that may be waiting: {"mode", "since"}, or None.
_PENDING: dict = {}


def card_text(mode: str, current: str) -> str:
    return "\n".join([
        f"Switch Jarvis from {current} to {mode}.", "",
        _WORDS[mode], "",
        "Nothing leaves this PC. You can switch back at any time from either app.",
        "", "If you say no: Jarvis stays " + current + "."])


def set_mode(mode, *, by: str = "", gate_check: Optional[Callable] = None,
             power=None, models=None, wait_s: float = 1.5) -> tuple:
    """Change the power mode through the gate. Returns (http_status, body)."""
    mode = str(mode or "").strip().lower()
    if mode not in MODES:
        return 400, {"ok": False, "error": f"mode must be one of {', '.join(MODES)}"}
    try:
        if power is None:
            import jarvis_power as power
        current = str(power.current())
    except Exception as exc:
        return 503, {"ok": False, "available": False,
                     "error": f"the power module is not available here ({type(exc).__name__})"}
    if mode == current:
        return 200, {"ok": True, "mode": mode, "changed": False,
                     "message": f"Already {mode}."}
    if mode == "standby" and _running_tasks():
        return 409, {"ok": False, "error": "a task is running - stop it first, or it would "
                                           "lose the model it is using"}
    with _PENDING_LOCK:
        if _PENDING:
            return 409, {"ok": False, "waiting": True,
                         "error": (f"a card to switch to {_PENDING['mode']} is already "
                                   f"waiting on your PC or phone - approve or deny that one "
                                   f"first")}
        _PENDING.update(mode=mode, since=time.time())

    box: dict = {}

    def work():
        try:
            decide()
        finally:
            with _PENDING_LOCK:
                _PENDING.clear()

    def decide():
        verdict = (gate_check or _gate_check)(
            "power_manage", {"text": card_text(mode, current)},
            f"power mode {current} -> {mode}, asked from {by or 'an app'}")
        if not getattr(verdict, "allowed", False):
            box["out"] = (200, {"ok": False, "mode": current, "changed": False,
                                "outcome": str(getattr(verdict, "outcome", "refused")),
                                "message": f"Not changed - Jarvis stays {current}."})
            return
        if mode == "standby" and _running_tasks():
            # Checked again: with the tier at "ask" the card may have waited
            # minutes, and a task that started meanwhile would lose its model.
            box["out"] = (409, {"ok": False, "mode": current, "changed": False,
                                "outcome": "refused",
                                "message": (f"Not changed - a task started while the card "
                                            f"waited, and standby would unload the model it "
                                            f"is using. Jarvis stays {current}; stop the task "
                                            f"first.")})
            return
        power.set_mode(mode, why=f"the owner, from {by or 'an app'}")
        out = {"ok": True, "mode": mode, "changed": True, "message": _WORDS[mode]}
        if mode == "standby":
            out.update(_unload_models(models))
        box["out"] = (200, out)

    t = threading.Thread(target=work, name="jarvis-power-switch", daemon=True)
    try:
        t.start()
    except Exception:
        with _PENDING_LOCK:
            _PENDING.clear()
        return 503, {"ok": False, "error": "could not raise the approval card"}
    t.join(max(0.0, float(wait_s)))
    if "out" in box:
        return box["out"]
    return 202, {"ok": True, "mode": current, "changed": False, "waiting": True,
                 "message": "Waiting for your approval on your PC or phone. The mode "
                            "changes only if you approve it."}


def handle_post(body, *, by: str = "") -> tuple:
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "need a JSON object"}
    return set_mode(body.get("mode"), by=by)
