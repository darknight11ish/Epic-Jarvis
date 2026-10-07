"""jarvis_learning_switch.py - turning background learning ON asks first.

NEW MODULE, shipped whole (learning-asks.patch routes POST
/api/memory/learning through it).

WHAT WAS WRONG
memory-pane.patch answered POST /api/memory/learning {"enabled": true} with
`set_learning(True)` straight away: it wrote learning.json and started the
learner, with no card. The owner chose, on 2026-09-24, that turning learning
on asks first - the same as the second card, the big model and the wake
word. Learning reads what is said to Jarvis and proposes facts about the
owner; every proposal still needs its own yes, but starting that reading is
a change the owner decides, not one a tap on a stale screen makes.

THE SHAPE (the same as jarvis_second_card.request_change)
    ON   one approval card, action `learning_enable`, and this returns at
         once with 202 {"waiting": true, ...} - NOT "it is on". The card is
         decided on its own thread; only tier "ask" with outcome "approved"
         calls set_learning(True). Denied, timed out, refused, or turned off
         while the card waited: nothing changes.
    OFF  immediate, never a card. It only narrows what Jarvis does, and an
         off switch that could time out would leave learning running.
         Turning it off while an ON card waits also withdraws that card's
         effect.

The tier is checked before the card and again on the answer. A toml that
sets `learning_enable` to "auto" does not get an automatic yes: this module
refuses (503) rather than let a config line become the owner's yes.
"""
from __future__ import annotations

import threading
import time
import uuid as _uuid
from typing import Callable, Optional

ACTION = "learning_enable"

CARD_TEXT = "\n".join([
    "Turn on learning.",
    "",
    "Jarvis will read what you type or say to it, in the background on this "
    "PC, and learn facts about you. With \"Learn automatically\" on, facts "
    "from your own words are saved without asking - each one is listed with "
    "a Forget - and everything else, including sensitive topics, waits for "
    "your yes in the Memory review.",
    "",
    "Nothing leaves this PC. You can turn learning off at any time from either "
    "app, and that is instant.",
    "",
    "If you say no: learning stays off.",
])

_LOCK = threading.Lock()
_PENDING: dict = {}          # {"id", "since"} while an ON card waits
_WITHDRAWN: set = set()
_LAST: dict = {}             # {"outcome", "why", "at"} - how the last card ended
_LATEST: dict = {}           # {"id"} - the card raised most recently; only it sets _LAST
#: Held from an approved card's "was it withdrawn?" check through
#: set_learning(True), and from OFF's withdrawing through set_learning(False):
#: an OFF pressed in between used to be answered "Learning is off." and then
#: overwritten by the card (red team R5). Always taken BEFORE _LOCK.
_SWITCH = threading.Lock()

#: How the last card ended, in plain words for the apps - `message` beside
#: the technical `why` in learning_last (fit audit item 28).
LAST_WORDS = {
    "enabled": "You approved the card, so learning is on.",
    "denied": "The card was turned down, so learning stayed off.",
    "timed_out": "Nobody answered the card in time, so learning stayed off.",
    "refused": "Your PC's settings do not let this be approved, so it stayed off.",
    "withdrawn": "You turned learning off while the card waited, so approving it changed "
                 "nothing.",
    "failed": "It was approved, but learning could not be started, so it stayed off.",
}
GATE_FAILED_WORDS = "The approval card could not be raised, so learning stayed off."


def _gate(action: str, detail: dict, prompt: str):
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def _tier(action: str) -> str:
    try:
        import jarvis_framework as fw
        return str(fw.action_tier(action))
    except Exception as exc:
        return f"unreadable ({type(exc).__name__})"


def _spawn(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="jarvis-learning-card", daemon=True).start()


def _audit(event: str, detail: dict) -> None:
    try:
        import jarvis_framework as fw
        fw.audit_log(event, detail)
    except Exception:
        pass


def _finish(pid: str, outcome: str, why: str = "", message: Optional[str] = None) -> None:
    with _LOCK:
        if _PENDING.get("id") == pid:
            _PENDING.clear()
        _WITHDRAWN.discard(pid)
        if _LATEST.get("id") not in (None, pid):
            # An older, withdrawn card answered after a newer one was raised:
            # its outcome must not be shown as the newer card's.
            return
        _LAST.clear()
        _LAST.update(outcome=outcome, why=why, at=time.time(),
                     message=message or LAST_WORDS.get(outcome, ""))
    _audit("learning.card", {"outcome": outcome})


def _decide(pid: str, apply: Callable[[bool], dict], gate: Callable,
            tier_of: Callable[[str], str]) -> None:
    try:
        v = gate(ACTION, {"text": CARD_TEXT, "what": "turn on learning",
                          "leaves_this_pc": False}, CARD_TEXT)
    except Exception as exc:
        return _finish(pid, "refused", f"the approval gate failed ({type(exc).__name__})",
                       GATE_FAILED_WORDS)
    vtier = getattr(v, "tier", "unknown")
    allowed = getattr(v, "allowed", False) is True
    outcome = getattr(v, "outcome", None)
    if outcome is None:
        outcome = "approved" if (allowed and vtier == "ask") else "refused"
    if vtier != "ask" or tier_of(ACTION) != "ask":
        return _finish(pid, "refused",
                       f"the gate answered at tier {vtier!r}, which is not a person saying yes")
    if not (allowed and outcome == "approved"):
        if outcome in ("denied", "timed_out"):
            return _finish(pid, outcome)
        return _finish(pid, "refused", str(getattr(v, "reason", "refused")))
    with _SWITCH:
        # Held until learning is on and _LAST says so: an OFF pressed
        # meanwhile waits for it, then turns learning off (R5).
        with _LOCK:
            withdrawn = pid in _WITHDRAWN
        if withdrawn:
            return _finish(pid, "withdrawn", "you turned learning off while the card was waiting")
        try:
            out = apply(True) or {}
        except Exception as exc:
            return _finish(pid, "failed", f"{type(exc).__name__}")
        if out.get("ok") is False:
            return _finish(pid, "failed", str(out.get("error", "")))
        _finish(pid, "enabled")


def request(enabled, apply: Callable[[bool], dict], *, gate: Optional[Callable] = None,
            tier_of: Optional[Callable[[str], str]] = None,
            spawn: Optional[Callable] = None) -> tuple:
    """POST /api/memory/learning. Returns (http code, body). `apply` is the
    backend's own set_learning(on) -> dict."""
    gate = gate or _gate
    tier_of = tier_of or _tier
    spawn = spawn or _spawn
    if not isinstance(enabled, bool):
        return 400, {"error": 'need {"enabled": true|false}'}
    if not enabled:
        with _SWITCH:
            # The lock an approved card holds from its withdrawn check to
            # set_learning(True): this OFF is never overwritten by it (R5).
            with _LOCK:
                if _PENDING:
                    # Withdrawn AND no longer the waiting card: approving it
                    # does nothing, and a later ON raises a fresh card instead
                    # of pointing at this one (chat history audit, 2026-09-24).
                    _WITHDRAWN.add(_PENDING["id"])
                    _PENDING.clear()
            out = dict(apply(False) or {})
        out.setdefault("ok", True)
        out.update(waiting=False, message="Learning is off.")
        _audit("learning.off", {})
        return 200, out
    tier = tier_of(ACTION)
    if tier != "ask":
        return 503, {"ok": False, "error": (
            f"{ACTION} is tier {tier!r} in jarvis-framework.toml; turning learning on "
            f"needs a person to say yes, so it must be 'ask'")}
    with _LOCK:
        if _PENDING:
            return 202, {"ok": True, "waiting": True, "enabled": False,
                         "message": "A card to turn learning on is already waiting for "
                                    "your approval."}
        pid = _uuid.uuid4().hex
        _PENDING.update(id=pid, since=time.time())
        _LATEST["id"] = pid
    try:
        spawn(lambda: _decide(pid, apply, gate, tier_of))
    except Exception:
        with _LOCK:
            _PENDING.clear()
        return 503, {"ok": False, "error": "could not raise the approval card"}
    return 202, {"ok": True, "waiting": True, "enabled": False,
                 "message": "Waiting for your approval. Learning turns on only if you "
                            "approve the card, on your PC or phone."}


def state() -> dict:
    """{"waiting": bool, "last": {...} | None} for the status routes."""
    with _LOCK:
        return {"waiting": bool(_PENDING), "last": dict(_LAST) or None}


def _reset_for_tests() -> None:
    with _LOCK:
        _PENDING.clear()
        _WITHDRAWN.clear()
        _LAST.clear()
        _LATEST.clear()
