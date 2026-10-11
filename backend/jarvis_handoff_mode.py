"""jarvis_handoff_mode.py - how long "Solve it here" stays on offer.

NEW MODULE, shipped whole (no patch): `jarvis_handoff.py` reads it, and
`jarvis_chatbot_routes.py` (already installed) answers its one route.

THE OWNER'S DECISION (CLAUDE.md, made 2026-10-08, his own words: "make this a
setting for both options with 1 as the default"; `docs/CAPTCHA-HANDOFF-DESIGN.md`
section 5). Until today the captcha hand-off ended after `IDLE_S` = 45 s with
no picture asked for, and `MOST_S` = 15 minutes however it went - both chosen,
neither measured. The owner's two choices:

  * "Stop early" (the DEFAULT, and the stricter one): about a minute of no
    interaction ends the hand-off, and the PC says plainly that Jarvis is
    stuck on a puzzle in that window, naming it, leaving the window for the
    owner to solve there. The PC's own window is the fallback this feature
    already promises (`WORDS["may_refuse"]`), so the owner is never left
    without a way through.
  * "Keep offering it": the live picture stays on offer for the full
    15-minute ceiling, so the owner can pick their phone up late.

WHY "KEEP OFFERING IT" IS GATED, AND "STOP EARLY" IS NOT (the repo's own rule
for a setting that increases exposure - `docs/ARCHITECTURE.md` section 3, one
permission model, one place approval cards come from; the same shape as
`jarvis_voice`'s `live_end`, `jarvis_watch_notify.py` and every other
card-plus-Windows-Hello switch here):

  * a live picture of the owner's own browser window - which may hold their
    own account details, a support chat's order page - staying on offer for
    fifteen minutes instead of one is MORE exposure, never less. Choosing it
    is ONE approval card (`handoff_keep_offering`, tier "ask"), and it is also
    on `jarvis_owner_check.PC_ONLY_ACTIONS`: the card is decided on the PC,
    with Windows Hello, and the PC refuses it from any other device.
  * going back to "Stop early" narrows what the owner's window may be seen,
    so it is immediate, from either app, never a card, and never held on a
    stale link.

FAIL CLOSED. No file at all is the owner's default ("Stop early"). A file that
is unreadable, is not JSON, or holds anything but the two names reads as "Stop
early" too, with `why` saying so - a damaged file must never quietly leave the
window on offer for fifteen minutes.

WHAT IS NEVER KEPT. One word ("stop_early" or "keep_offering") and the time it
changed. No picture, no page, no site, no token, no typed character - this
module never touches the hand-off's own picture or input path at all.
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

#: The gate action that decides "Keep offering it". Must stay "ask" in
#: jarvis-framework.toml, and must be in jarvis_owner_check.PC_ONLY_ACTIONS
#: (Windows Hello, PC only): anything else and this module refuses to apply it.
ACTION = "handoff_keep_offering"

#: The route both apps read and set it on. NOT one of the hand-off's own
#: picture or input routes (`/api/chatbot/handoff/...`): the desktop must never
#: name one of those (tests/handoff.mjs checks), because it has the real window
#: and never pictures or taps anything.
PATH = "/api/chatbot/handoff_mode"

#: The two values, exactly as the owner was promised.
STOP_EARLY = "stop_early"
KEEP_OFFERING = "keep_offering"
MODES = (STOP_EARLY, KEEP_OFFERING)
#: The default, and the value every damaged or missing file reads as.
DEFAULT = STOP_EARLY
#: The value that needs the approval card.
LOOSER = KEEP_OFFERING

#: What each value is called, and its one line, in BOTH apps, word for word
#: (tools/gen_handoff_cases.py carries them into both apps' contract file).
WORDS = {
    "title": "When the phone does not answer",
    "detail": ("When Jarvis is stuck on a captcha or a sign-in page, your phone can show a live "
               "picture of that one window. This chooses how long Jarvis keeps offering it."),
    "stop_early": "Stop early",
    "stop_early_detail": ("After about a minute with nobody looking, the hand-off ends and the "
                          "PC says which window Jarvis is stuck on, so you can solve it there."),
    "keep_offering": "Keep offering it",
    "keep_offering_detail": ("The live picture stays on offer for the full 15 minutes, so you can "
                             "pick your phone up late. That is more time for that window to be "
                             "seen, so turning this on asks for your approval."),
    "opens_windows_hello": "Turning \"Keep offering it\" on asks for your approval on the PC.",
    "waiting": ("Waiting for your approval. The hand-off keeps stopping early until you approve "
                "the card."),
    "off_now": "Done. The hand-off stops early again when nobody is looking.",
    "damaged": ("the hand-off settings file is damaged, so the hand-off stops early when nobody "
                "is looking. Choose \"Keep offering it\" again to rewrite it"),
}

LAST_WORDS = {
    "on": "You approved the card, so the offer stays for the full 15 minutes.",
    "denied": "The card was turned down, so the hand-off still stops early.",
    "timed_out": "Nobody answered the card in time, so the hand-off still stops early.",
    "refused": "Your PC's settings do not let this be approved, so it still stops early.",
    "withdrawn": "You chose \"Stop early\" while the card waited, so approving it changes nothing.",
    "failed": "It was approved, but the setting could not be saved, so it still stops early.",
}
GATE_FAILED_WORDS = "The approval card could not be raised, so the hand-off still stops early."

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
    return _config_dir() / "handoff-mode.json"


_SETTINGS_LOCK = threading.Lock()


def settings() -> dict:
    """{"mode", "why"}. No file, or one that never had "mode": the owner's
    default, "Stop early". A file that cannot be read, is not JSON, or holds
    anything but the two names: "Stop early", and `why` says so (fail closed -
    the safe direction here is ending the offer early)."""
    try:
        raw = settings_path().read_text(encoding="utf-8")
    except FileNotFoundError:
        return {"mode": DEFAULT, "why": ""}
    except OSError as exc:
        return {"mode": DEFAULT,
                "why": f"the hand-off settings file could not be read "
                       f"({type(exc).__name__}), so the hand-off stops early when nobody is "
                       f"looking"}
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
        raise ValueError("the hand-off setting must be one of: " + ", ".join(MODES))
    return dict(_save(mode), ok=True)


def is_patient() -> bool:
    """True only when the owner chose "Keep offering it" AND it is really
    saved. A damaged file reads as False (settings() already says why)."""
    return settings()["mode"] == KEEP_OFFERING


def idle_seconds() -> float:
    """How long with nobody looking before the hand-off ends: the owner's
    "about a minute" for "Stop early", or the full ceiling for
    "Keep offering it" (a later ask for a picture can always refresh it)."""
    return CEILING_S if is_patient() else STOP_AFTER_S


def ceiling_seconds() -> float:
    """However it goes, a hand-off ends after this long. The 15-minute ceiling
    is the same for both choices: "Keep offering it" moves the IDLE clock, not
    the ceiling, which is exactly what the owner was promised."""
    return CEILING_S


#: "About a minute" - the owner's own words for the quick cut-off.
STOP_AFTER_S = 60.0
#: The 15-minute ceiling both choices share.
CEILING_S = 15 * 60.0


def view() -> dict:
    """GET /api/chatbot/handoff_mode: the owner's choice, every word both apps
    show, and whether a card is waiting - never a picture, never a page."""
    st = settings()
    live = state()
    out = {"mode": st["mode"], "default": DEFAULT, "modes": list(MODES),
           "mode_name": st["mode"], "words": dict(WORDS),
           "patient": st["mode"] == KEEP_OFFERING,
           "idle_s": idle_seconds(), "ceiling_s": CEILING_S,
           "waiting": live["waiting"], "last": live["last"],
           "pc_only": True}
    if st["why"]:
        out["why"] = st["why"]
    return out


# --------------------------------------------------------------------------
#   The approval card (the same shape as jarvis_watch_notify.py's)
# --------------------------------------------------------------------------
_LOCK = threading.Lock()
_PENDING: dict = {}          # {"id", "since"} while a "Keep offering it" card waits
_WITHDRAWN: set = set()
_LAST: dict = {}
_LATEST: dict = {}
_SWITCH = threading.Lock()


def card_text() -> str:
    return "\n".join([
        "Keep offering the live picture of a browser window to your phone for the full 15 "
        "minutes?",
        "",
        "Jarvis pauses at a captcha or a sign-in page and your phone can show a live picture of "
        "that one window, so you can solve it from your phone. Right now, if nobody looks at the "
        "picture for about a minute, the hand-off ends and the PC says which window Jarvis is "
        "stuck on.",
        "",
        "With this on, the picture stays on offer for the full 15 minutes instead - useful if you "
        "pick your phone up late, and more time for a window showing your own account details to "
        "be seen.",
        "",
        "Your taps and typing still go to that one window only, and only while Jarvis is paused "
        "there. The picture is still never saved. Jarvis never solves a captcha for you, and the "
        "PC also says which window it is stuck on either way.",
        "",
        "You can go back to \"Stop early\" at any time, from either app, and that is instant.",
        "",
        "If you say no: nothing changes - the hand-off keeps stopping early after about a minute.",
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
    threading.Thread(target=fn, name="jarvis-handoff-mode-card", daemon=True).start()


def _audit(event: str, detail: dict) -> None:
    try:
        import jarvis_framework as fw
        fw.audit_log("chatbot.handoff_mode", {"event": event, **detail})
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
        v = gate(ACTION, {"text": text, "what": "keep offering the hand-off for 15 minutes",
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
                           "you chose \"Stop early\" while the card was waiting")
        # Last check, on the way in: if the owner went back to "Stop early"
        # while this card waited, the OFF path already marked it withdrawn
        # (checked just above) - and the choice is re-read here, so an older
        # jarvis_handoff_mode.py cannot be talked into the looser value.
        try:
            set_mode(KEEP_OFFERING)
        except Exception as exc:
            return _finish(pid, "failed", f"{type(exc).__name__}")
        _finish(pid, "on")


def request(mode, *, gate: Optional[Callable] = None,
            tier_of: Optional[Callable[[str], str]] = None,
            spawn: Optional[Callable] = None) -> tuple:
    """POST /api/chatbot/handoff_mode {"mode": "stop_early"|"keep_offering"}.
    Returns (http code, body). "Stop early" is at once; "Keep offering it"
    raises ONE approval card and changes nothing until a person says yes."""
    gate = gate or _gate
    tier_of = tier_of or _tier
    spawn = spawn or _spawn
    mode = str(mode or "")
    if mode not in MODES:
        return 400, {"ok": False,
                     "error": "Choose \"Stop early\" or \"Keep offering it\"."}
    if mode == STOP_EARLY:
        with _SWITCH:
            with _LOCK:
                if _PENDING:
                    _WITHDRAWN.add(_PENDING["id"])
                    _PENDING.clear()
            out = dict(set_mode(STOP_EARLY))
        out.update(waiting=False, message=WORDS["off_now"])
        _audit("stop_early", {})
        return 200, out
    if settings()["mode"] == KEEP_OFFERING:
        return 200, {"ok": True, "mode": KEEP_OFFERING, "waiting": False,
                     "message": "It is already set to keep offering the hand-off."}
    tier = tier_of(ACTION)
    if tier != "ask":
        return 503, {"ok": False, "error": (
            f"{ACTION} is tier {tier!r} in jarvis-framework.toml; keeping the hand-off on "
            f"offer for the full 15 minutes needs a person to say yes, so it must be 'ask'")}
    with _LOCK:
        if _PENDING:
            return 202, {"ok": True, "waiting": True, "mode": STOP_EARLY,
                         "message": "A card to keep offering the hand-off is already waiting "
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
    return 202, {"ok": True, "waiting": True, "mode": STOP_EARLY,
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
    print(f"  Hand-off when nobody answers: {WORDS[st['mode']]}"
          + (f" ({st['why']})" if st["why"] else ""))
