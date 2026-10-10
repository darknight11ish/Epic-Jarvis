"""jarvis_handoff_front.py - does a captcha bring its browser window forward?

NEW MODULE, shipped whole (no patch): `jarvis_handoff.py` (already installed)
reads it, and `jarvis_chatbot_routes.py` (already installed) answers its one
route.

THE OWNER'S DECISION (2026-10-09), in his words: *"1 by default with the option
for 2 in the settings of Jarvis"*. When a captcha or a sign-in page blocks the
browser Jarvis is driving, there are two things Jarvis may do about the window
on the PC, and the owner chose which:

  * "Leave it where it is" (`LEAVE_IN_PLACE`, the DEFAULT, and the stricter
    one): the window is not touched - it keeps whatever size, position and
    stacking it already had - and the PC says plainly WHICH window is stuck
    ("{site} is waiting on this PC", `jarvis_handoff.STUCK`), so the owner
    solves it there when they are ready. Nothing appears, moves or takes the
    keyboard from under the owner.
  * "Bring it to the front" (`BRING_TO_FRONT`): that one window is raised and
    activated the moment Jarvis gets stuck, so it is in front and ready to
    type into.

WHY "BRING IT TO THE FRONT" IS GATED, AND "LEAVE IT WHERE IT IS" IS NOT (the
repo's own rule for a setting that takes something over that was not taken
before - `docs/ARCHITECTURE.md` section 3, one permission model, one place
approval cards come from; the same shape as `jarvis_handoff_mode.py`'s own
"Keep offering it", `jarvis_voice`'s `live_end` and `jarvis_watch_notify.py`):

  * raising and ACTIVATING a window takes the owner's screen attention and
    their keyboard focus away from whatever they were doing, whenever it
    happens - possibly in the middle of typing somewhere else, possibly into
    an account page of their own. That is MORE than Jarvis was doing before,
    so choosing it is ONE approval card (`handoff_bring_to_front`, tier
    "ask"), and it is also on `jarvis_owner_check.PC_ONLY_ACTIONS`: the card
    is decided on the PC, with Windows Hello, and the PC refuses it from any
    other device.
  * going back to "Leave it where it is" does less - nothing is raised, and
    the same plain line still names the window - so it is immediate, from
    either app, never a card, and never held on a stale link.

WHAT THIS MODULE NEVER DOES. It raises no window itself: it stores ONE word and
answers whether that word is the raising choice. The window belongs to the
hand-off, and `jarvis_handoff.py` is where a real raise would be asked for, on
the PC that has the window. Nothing here pictures a page, moves a mouse, types
a character, or reads a title - the two fixed site words the PC already
promises (`jarvis_handoff.STUCK`) are the only thing ever named.

FAIL CLOSED. No file at all is the owner's default ("Leave it where it is"). A
file that is unreadable, is not JSON, or holds anything but the two names reads
as the default too, with `why` saying so - a damaged file must never quietly
start taking the owner's screen.

WHAT IS KEPT. One word ("leave_in_place" or "bring_to_front") and the time it
changed.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import uuid as _uuid
from pathlib import Path
from typing import Callable, Optional

#: The gate action that decides "Bring it to the front". Must stay "ask" in
#: jarvis-framework.toml, and must be in jarvis_owner_check.PC_ONLY_ACTIONS
#: (Windows Hello, PC only): anything else and this module refuses to apply it.
ACTION = "handoff_bring_to_front"

#: The route both apps read and set it on. NOT one of the hand-off's own
#: picture or input routes (`/api/chatbot/handoff/...`): the desktop must never
#: name one of those (tests/handoff.mjs checks), because it has the real window
#: and never pictures or taps anything.
PATH = "/api/chatbot/handoff_front"

#: The two values, exactly as the owner was promised.
LEAVE_IN_PLACE = "leave_in_place"
BRING_TO_FRONT = "bring_to_front"
MODES = (LEAVE_IN_PLACE, BRING_TO_FRONT)
#: The default, and the value every damaged or missing file reads as.
DEFAULT = LEAVE_IN_PLACE
#: The value that needs the approval card.
LOOSER = BRING_TO_FRONT

#: The settings file's name. Deliberately NOT the hand-off's own
#: "handoff-mode.json": the two settings are read and written by two modules,
#: and one damaged file must not be able to change the other's answer.
FILE_NAME = "handoff-front.json"

#: What each value is called, and its one line, in BOTH apps, word for word
#: (tools/gen_handoff_cases.py carries them into both apps' contract file).
WORDS = {
    "title": "When a captcha stops Jarvis",
    "detail": ("When Jarvis is stuck on a captcha or a sign-in page, it can leave that browser "
               "window exactly where it is - or bring it to the front so you can type into it. "
               "Either way the PC says which window is stuck."),
    "leave_in_place": "Leave it where it is",
    "leave_in_place_detail": ("The window is not touched: it keeps its size, its place and whatever "
                              "is in front of it. The PC says which window Jarvis is stuck on, and "
                              "you solve it there when you are ready."),
    "bring_to_front": "Bring it to the front",
    "bring_to_front_detail": ("That one window is raised and activated the moment Jarvis is stuck, "
                              "so it is in front and ready to type into. It takes your screen and "
                              "your keyboard away from whatever you were doing, so turning this on "
                              "asks for your approval."),
    "opens_windows_hello": "Turning \"Bring it to the front\" on asks for your approval on the PC.",
    "waiting": ("Waiting for your approval. The window stays where it is until you approve the "
                "card."),
    "off_now": "Done. The window stays where it is again.",
    "damaged": ("the captcha window setting is damaged, so the window stays where it is. Choose "
                "\"Bring it to the front\" again to rewrite it"),
}

LAST_WORDS = {
    "on": "You approved the card, so the window comes to the front when a captcha stops Jarvis.",
    "denied": "The card was turned down, so the window still stays where it is.",
    "timed_out": "Nobody answered the card in time, so the window still stays where it is.",
    "refused": "Your PC's settings do not let this be approved, so the window still stays where it "
               "is.",
    "withdrawn": ("You chose \"Leave it where it is\" while the card waited, so approving it "
                  "changes nothing."),
    "failed": ("It was approved, but the setting could not be saved, so the window still stays "
               "where it is."),
}
GATE_FAILED_WORDS = "The approval card could not be raised, so the window still stays where it is."

_ARMED = False


# --------------------------------------------------------------------------
#   The setting itself
# --------------------------------------------------------------------------

def _config_dir() -> Path:
    """The same folder every other switch here uses, found the same way."""
    fw = sys.modules.get("jarvis_framework")
    if fw is None:
        try:
            import jarvis_framework as fw  # type: ignore
        except Exception:
            fw = None
    if fw is not None:
        try:
            return Path(fw.CONFIG_DIR)
        except Exception:
            pass
    env = os.environ.get("OPENJARVIS_CONFIG_DIR")
    if env:
        return Path(os.path.expanduser(env))
    return Path(os.path.expanduser("~")) / ".openjarvis"


def settings_path() -> Path:
    return _config_dir() / FILE_NAME


_SETTINGS_LOCK = threading.Lock()


def settings() -> dict:
    """{"mode", "why"}. No file, or one that never had "mode": the owner's
    default, "Leave it where it is". A file that cannot be read, is not JSON,
    or holds anything but the two names: the default, and `why` says so (fail
    closed - the safe direction here is not touching the owner's screen)."""
    try:
        raw = settings_path().read_text(encoding="utf-8")
    except FileNotFoundError:
        return {"mode": DEFAULT, "why": ""}
    except OSError as exc:
        return {"mode": DEFAULT,
                "why": f"the captcha window settings file could not be read "
                       f"({type(exc).__name__}), so the window stays where it is"}
    try:
        doc = json.loads(raw)
        if not isinstance(doc, dict):
            raise ValueError
    except Exception:
        return {"mode": DEFAULT, "why": WORDS["damaged"]}
    mode = doc.get("mode", DEFAULT)
    if mode not in MODES:
        return {"mode": DEFAULT, "why": WORDS["damaged"]}
    return {"mode": mode, "why": ""}


def _save(mode: str) -> dict:
    with _SETTINGS_LOCK:
        p = settings_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps({"mode": mode, "changed": time.time()}), encoding="utf-8")
        os.replace(tmp, p)
    return settings()


def set_mode(mode: str) -> dict:
    """Writes one of the two names. Raises ValueError for anything else."""
    if mode not in MODES:
        raise ValueError("the captcha window setting must be one of: " + ", ".join(MODES))
    return dict(_save(mode), ok=True)


def brings_to_front() -> bool:
    """True only when the owner chose "Bring it to the front" AND it is really
    saved. A damaged file reads as False (settings() already says why).

    This is the ONE question the hand-off asks: `jarvis_handoff.py` calls it
    where it already names the window it is stuck on, so the raising choice
    cannot be read from anywhere else and cannot drift from the setting."""
    return settings()["mode"] == BRING_TO_FRONT


def should_raise_now(*, stuck: bool, handoff_active: bool) -> bool:
    """Should the PC raise that window at THIS moment?

    Only when all three are true, so an old setting can never make the PC act
    on its own:

      * the owner chose "Bring it to the front";
      * a captcha or sign-in page really is waiting for the owner (`stuck`);
      * and the hand-off is NOT active (`handoff_active` is False) - while the
        phone is showing the live picture the owner is solving it there, so
        there is nothing to raise, and raising it would take the screen for a
        job that is already being done.

    A caller that cannot tell whether the hand-off is active passes True for
    `handoff_active`: the window is then left alone, which is the safe
    direction.
    """
    return bool(stuck) and not bool(handoff_active) and brings_to_front()


def view() -> dict:
    """GET /api/chatbot/handoff_front: the owner's choice, every word both apps
    show, and whether a card is waiting - never a picture, never a page."""
    st = settings()
    live = state()
    out = {"mode": st["mode"], "default": DEFAULT, "modes": list(MODES),
           "mode_name": st["mode"], "words": dict(WORDS),
           "brings_to_front": st["mode"] == BRING_TO_FRONT,
           "waiting": live["waiting"], "last": live["last"],
           "pc_only": True}
    if st["why"]:
        out["why"] = st["why"]
    return out


# --------------------------------------------------------------------------
#   The approval card (the same shape as jarvis_handoff_mode.py's)
# --------------------------------------------------------------------------
_LOCK = threading.Lock()
_PENDING: dict = {}          # {"id", "since"} while a "Bring it to the front" card waits
_WITHDRAWN: set = set()
_LAST: dict = {}
_LATEST: dict = {}
_SWITCH = threading.Lock()


def card_text() -> str:
    return "\n".join([
        "Bring that browser window to the front when a captcha stops Jarvis?",
        "",
        "When Jarvis is stuck on a captcha or a sign-in page in a browser window it is driving, "
        "the window is left exactly where it is today: it keeps its size, its place and whatever "
        "is in front of it, and the PC says plainly which window is stuck so you can solve it "
        "there.",
        "",
        "With this on, that one window is raised and activated the moment Jarvis is stuck, so it "
        "is in front and ready to type into.",
        "",
        "What it costs: it takes your screen and your keyboard away from whatever you are doing, "
        "whenever it happens - possibly in the middle of typing somewhere else, and that window "
        "may be showing your own account details.",
        "",
        "What it never does: Jarvis still never solves a captcha for you, and no page, picture or "
        "typed word is read or kept by this setting. The PC still says which window it is stuck "
        "on either way.",
        "",
        "You can go back to \"Leave it where it is\" at any time, from either app, and that is "
        "instant.",
        "",
        "If you say no: nothing changes - the window stays where it is.",
    ])


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
    threading.Thread(target=fn, name="jarvis-handoff-front-card", daemon=True).start()


def _audit(event: str, detail: dict) -> None:
    try:
        import jarvis_framework as fw
        fw.audit_log("chatbot.handoff_front", {"event": event, **detail})
    except Exception:
        pass


def _finish(pid: str, outcome: str, why: str = "", message: Optional[str] = None) -> None:
    with _LOCK:
        if _PENDING.get("id") == pid:
            _PENDING.clear()
        _WITHDRAWN.discard(pid)
        if _LATEST.get("id") not in (None, pid):
            return
        _LAST.clear()
        _LAST.update(outcome=outcome, why=why, at=time.time(),
                     message=message or LAST_WORDS.get(outcome, ""))
    _audit("card", {"outcome": outcome})


def _decide(pid: str, gate: Callable, tier_of: Callable[[str], str]) -> None:
    text = card_text()
    try:
        v = gate(ACTION, {"text": text, "what": "bring the stuck browser window to the front",
                          "leaves_this_pc": False}, text)
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
        with _LOCK:
            withdrawn = pid in _WITHDRAWN
        if withdrawn:
            return _finish(pid, "withdrawn",
                           "you chose \"Leave it where it is\" while the card was waiting")
        # Last check, on the way in: if the owner went back to the default
        # while this card waited, the OFF path already marked it withdrawn
        # (checked just above) - and the choice is re-read here, so an older
        # jarvis_handoff_front.py cannot be talked into the looser value.
        try:
            set_mode(BRING_TO_FRONT)
        except Exception as exc:
            return _finish(pid, "failed", f"{type(exc).__name__}")
        _finish(pid, "on")


def request(mode, *, gate: Optional[Callable] = None,
            tier_of: Optional[Callable[[str], str]] = None,
            spawn: Optional[Callable] = None) -> tuple:
    """POST /api/chatbot/handoff_front {"mode": "leave_in_place"|"bring_to_front"}.
    Returns (http code, body). "Leave it where it is" is at once; "Bring it to
    the front" raises ONE approval card and changes nothing until a person says
    yes."""
    gate = gate or _gate
    tier_of = tier_of or _tier
    spawn = spawn or _spawn
    mode = str(mode or "")
    if mode not in MODES:
        return 400, {"ok": False,
                     "error": "Choose \"Leave it where it is\" or \"Bring it to the front\"."}
    if mode == LEAVE_IN_PLACE:
        with _SWITCH:
            with _LOCK:
                if _PENDING:
                    _WITHDRAWN.add(_PENDING["id"])
                    _PENDING.clear()
            out = dict(set_mode(LEAVE_IN_PLACE))
        out.update(waiting=False, message=WORDS["off_now"])
        _audit("leave_in_place", {})
        return 200, out
    if settings()["mode"] == BRING_TO_FRONT:
        return 200, {"ok": True, "mode": BRING_TO_FRONT, "waiting": False,
                     "message": "It is already set to bring the window to the front."}
    tier = tier_of(ACTION)
    if tier != "ask":
        return 503, {"ok": False, "error": (
            f"{ACTION} is tier {tier!r} in jarvis-framework.toml; bringing a window to the front "
            f"takes your screen and your keyboard, which needs a person to say yes, so it must be "
            f"'ask'")}
    with _LOCK:
        if _PENDING:
            return 202, {"ok": True, "waiting": True, "mode": LEAVE_IN_PLACE,
                         "message": "A card to bring the window to the front is already waiting "
                                    "for your approval."}
        pid = _uuid.uuid4().hex
        _PENDING.update(id=pid, since=time.time())
        _LATEST["id"] = pid
    try:
        spawn(lambda: _decide(pid, gate, tier_of))
    except Exception:
        with _LOCK:
            _PENDING.clear()
        return 503, {"ok": False, "error": "could not raise the approval card"}
    return 202, {"ok": True, "waiting": True, "mode": LEAVE_IN_PLACE,
                 "message": WORDS["waiting"]}


def state() -> dict:
    """{"waiting": bool, "last": {...} | None} for the view above."""
    with _LOCK:
        return {"waiting": bool(_PENDING), "last": dict(_LAST) or None}


def _reset_for_tests() -> None:
    global _ARMED
    with _LOCK:
        _PENDING.clear()
        _WITHDRAWN.clear()
        _LAST.clear()
        _LATEST.clear()
    _ARMED = False


if __name__ == "__main__":
    st = settings()
    print(f"  A captcha's browser window: {WORDS[st['mode']]}"
          + (f" ({st['why']})" if st["why"] else ""))
