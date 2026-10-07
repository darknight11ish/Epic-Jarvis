"""jarvis_phone_notifications.py - the "read my phone's notifications"
setting.

NEW MODULE, shipped whole (phone-notifications.patch wraps the running
server's `do_GET`/`do_POST`, like `jarvis_watch_notify.install()` and
`jarvis_documents.install()` do, rather than adding an inline route block -
`jarvis_hud.py`'s real text is not in this repository, so a new route can
only be added by wrapping the handler after it is built, which needs no
context inside the file at all). Same shape as `jarvis_watch_notify.py`,
copied deliberately: this is the second setting whose owner has already
decided "off by default, ON is one card, OFF is instant, only the phone
ever acts on it" (docs/ARCHITECTURE.md §3, "A second DOOR to the same
gates, never a second gate" / one permission model, one place cards come
from).

THE OWNER'S DECISION (CLAUDE.md, 2026-09-26, queued after the four
cutting-edge groups and the security audit; built 2026-09-28):

"reading phone notifications is added as an option. The safe version
only: off by default, turning it on raises an approval card, turning it
off is immediate; only apps the owner chooses (never banking); one-time
codes hidden before anything reaches the model; treated as outside text -
never makes Jarvis act and is never saved as a fact; shown or summarised
only when the owner asks; nothing leaves the owner's own devices. Never
text messages (SMS), and Jarvis never replies or sends."

WHAT THIS MODULE ACTUALLY IS, AND WHAT IT IS NOT

This is the ON/OFF switch and its one approval card - nothing else. Every
other half of the feature (capturing a notification with Android's
`NotificationListenerService`, the one-time-code redaction, the per-app
allow list, and never touching SMS) runs entirely on the phone, in
`jarvis-client/`, and is proved by that app's own tests
(`NotificationRedactorTest.kt`, `NotificationAllowListTest.kt`) - the same
division `jarvis_watch_notify.py`'s own docstring draws for the smartwatch
setting, which is Android-only in exactly the same way. This module never
sees a notification's text: nothing it does could, since notifications are
captured and stored on the phone, never sent to this PC on their own.

WHY THIS LIVES ON THE PC, NOT ONLY ON THE PHONE

Every switch of this shape - "Learn automatically", "Also remember
sensitive topics automatically", the smartwatch setting - is decided on the
PC and read by both apps, even when only one app's behaviour changes
because of it (docs/ARCHITECTURE.md §3). Reading phone notifications is
Android-only, so only the phone ever asks for this setting or acts on it -
but it is still a decision the owner makes with the SAME approval card
every other risky-sounding change gets, not a bare Android switch a stolen
or borrowed phone could flip on its own. See docs/ARCHITECTURE.md §8, "On
the phone, kept off the desktop", for the one-sided half of this.

WHAT TURNING THIS ON ACTUALLY MEANS

There is no new lane out of the PC here (docs/ARCHITECTURE.md §4): this
setting does not send anything anywhere by itself. It only tells the
phone it MAY start using Android's `NotificationListenerService` - a
separate, OS-level permission the owner still has to grant by hand, in
Android's own Settings, because Android treats it as unusually broad
(every notification on the device, from every app, unless the phone's own
per-app allow list - empty by default - narrows it first). Turning this
setting OFF does not revoke that OS permission (only Android's own
Settings screen can); it tells the phone to stop reading notifications and
to stop offering them to Jarvis, at once.

Reading a captured notification INTO a chat, so the model can see it, is
not this route at all: it rides the existing "shared text" mechanism
(`docs/JARVIS-API.md` §18, `ChatSession.send`'s `shared` parameter) the
Share sheet and the desktop's clipboard hotkey already use - the owner
taps "Attach recent notifications" next to the chat box, the phone puts
the redacted text in as its own message tagged `shared`, and the backend's
own outside-text rule (only `typed` and `voice` are the owner's own words)
already marks it as outside text, taints the conversation, and keeps it
out of the learner - with no new plumbing on this side at all. That is a
deliberate choice, not an oversight: docs/JARVIS-API.md §61 has the
reasoning.

THE SHAPE (the same as jarvis_watch_notify.py)
    ON   one approval card, action `phone_notifications_read`, and this
         returns at once with 202 {"waiting": true, ...} - not "it is on".
         The card is decided on its own thread; only tier "ask" with
         outcome "approved" turns it on. Denied, timed out, refused, or
         turned off while the card waited: nothing changes.
    OFF  immediate, never a card - it only narrows what the phone may do,
         and an off switch that could time out would leave reading running.
         Turning it off while an ON card waits also withdraws that card.
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
from urllib.parse import urlsplit

ACTION = "phone_notifications_read"

PATH = "/api/notifications/phone"

CARD_TEXT = "\n".join([
    "Let Jarvis read notifications from apps you choose, on your phone.",
    "",
    "Right now Jarvis never sees a phone notification. Turning this on lets "
    "your phone save the notifications from apps YOU add to a list - "
    "nothing is read until you add at least one app, and the list starts "
    "empty.",
    "",
    "A one-time code (like a 6-digit login code) is blanked out before it "
    "is ever saved, using a pattern match - it is a good-faith check, not a "
    "guarantee for every app's wording. Text messages (SMS) are never "
    "read, even if you try to add your Messages app.",
    "",
    "Jarvis cannot always tell a banking app from any other. Known banking "
    "and payment apps are blocked from the list on this phone; for "
    "anything else, please do not add a banking app.",
    "",
    "Saved notifications stay on your phone. Jarvis only sees one when you "
    "ask about it in chat, and it never replies to one, dismisses one, or "
    "acts on one - and it is never saved as a remembered fact.",
    "",
    "You can turn this off again at any time, from either app, and that is "
    "instant.",
    "",
    "If you say no: nothing about your notifications changes.",
])

_LOCK = threading.Lock()
_PENDING: dict = {}          # {"id", "since"} while an ON card waits
_WITHDRAWN: set = set()
_LAST: dict = {}             # {"outcome", "why", "at"} - how the last card ended
_LATEST: dict = {}           # {"id"} - the card raised most recently; only it sets _LAST
#: Held from an approved card's "was it withdrawn?" check through
#: _save(enabled=True), and from OFF's withdrawing through _save(enabled=False):
#: the lesson of jarvis_learning_switch.py's own R5 (also drawn on by
#: jarvis_watch_notify.py, which this module copies).
_SWITCH = threading.Lock()

LAST_WORDS = {
    "enabled": "You approved the card, so your phone may read notifications from apps you choose.",
    "denied": "The card was turned down, so nothing about your notifications changed.",
    "timed_out": "Nobody answered the card in time, so nothing about your notifications changed.",
    "refused": "Your PC's settings do not let this be approved, so it stayed off.",
    "withdrawn": "You turned this off while the card waited, so approving it changed nothing.",
    "failed": "It was approved, but the setting could not be saved, so it stayed off.",
}
GATE_FAILED_WORDS = "The approval card could not be raised, so it stayed off."

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
    return _config_dir() / "phone-notifications.json"


_SETTINGS_LOCK = threading.Lock()

_DAMAGED = ("the phone notifications settings file is damaged, so nothing about your "
            "notifications changed. Turn this on again to rewrite it")


def settings() -> dict:
    """{"enabled", "why"}. No file, or one that never had "enabled": OFF -
    the owner's default. A file that cannot be read, is not JSON, or holds
    anything but true/false: OFF, and `why` says so (fail closed - the safe
    direction here is not reading notifications)."""
    try:
        raw = settings_path().read_text(encoding="utf-8")
    except FileNotFoundError:
        return {"enabled": False, "why": ""}
    except OSError as exc:
        return {"enabled": False,
                "why": f"the phone notifications settings file could not be read "
                       f"({type(exc).__name__}), so nothing about your notifications changed"}
    try:
        doc = json.loads(raw)
        if not isinstance(doc, dict):
            raise ValueError
    except Exception:
        return {"enabled": False, "why": _DAMAGED}
    enabled = doc.get("enabled", False)
    if not isinstance(enabled, bool):
        return {"enabled": False, "why": _DAMAGED}
    return {"enabled": enabled, "why": ""}


def _save(enabled: bool) -> dict:
    with _SETTINGS_LOCK:
        p = settings_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps({"enabled": bool(enabled), "changed": time.time()}),
                       encoding="utf-8")
        os.replace(tmp, p)
    return settings()


def set_enabled(on: bool) -> dict:
    return dict(_save(bool(on)), ok=True)


# --------------------------------------------------------------------------
#   The approval card
# --------------------------------------------------------------------------

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
    threading.Thread(target=fn, name="jarvis-phone-notifications-card", daemon=True).start()


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
            return
        _LAST.clear()
        _LAST.update(outcome=outcome, why=why, at=time.time(),
                     message=message or LAST_WORDS.get(outcome, ""))
    _audit("phone_notifications.card", {"outcome": outcome})


def _decide(pid: str, apply: Callable[[bool], dict], gate: Callable,
            tier_of: Callable[[str], str]) -> None:
    try:
        v = gate(ACTION, {"text": CARD_TEXT, "what": "read notifications from apps you choose",
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
        with _LOCK:
            withdrawn = pid in _WITHDRAWN
        if withdrawn:
            return _finish(pid, "withdrawn", "you turned this off while the card was waiting")
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
    """POST /api/notifications/phone. Returns (http code, body). `apply` is
    the backend's own set_enabled(on) -> dict."""
    gate = gate or _gate
    tier_of = tier_of or _tier
    spawn = spawn or _spawn
    if not isinstance(enabled, bool):
        return 400, {"error": 'need {"enabled": true|false}'}
    if not enabled:
        with _SWITCH:
            with _LOCK:
                if _PENDING:
                    _WITHDRAWN.add(_PENDING["id"])
                    _PENDING.clear()
            out = dict(apply(False) or {})
        out.setdefault("ok", True)
        out.update(waiting=False, message="Nothing about your notifications changed.")
        _audit("phone_notifications.off", {})
        return 200, out
    tier = tier_of(ACTION)
    if tier != "ask":
        return 503, {"ok": False, "error": (
            f"{ACTION} is tier {tier!r} in jarvis-framework.toml; reading phone notifications "
            f"needs a person to say yes, so it must be 'ask'")}
    with _LOCK:
        if _PENDING:
            return 202, {"ok": True, "waiting": True, "enabled": False,
                         "message": "A card to allow reading phone notifications is already "
                                    "waiting for your approval."}
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
                 "message": "Waiting for your approval. Your phone reads notifications only if "
                            "you approve the card, on your PC or phone."}


def state() -> dict:
    """{"waiting": bool, "last": {...} | None} for the status route."""
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


# --------------------------------------------------------------------------
#   The route - wrapped round the handler, like jarvis_watch_notify.install()
# --------------------------------------------------------------------------

def armed() -> bool:
    """True once install() has wrapped the running server's do_GET/do_POST."""
    return _ARMED


def _view() -> dict:
    st = settings()
    live = state()
    out = {"enabled": st["enabled"], "waiting": live["waiting"], "last": live["last"]}
    if st["why"]:
        out["why"] = st["why"]
    return out


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls.do_GET` and `do_POST` so GET/POST /api/notifications/phone
    are answered here, after the server's own origin and token checks. Every
    other request goes straight to the original. Returns the banner line."""
    global _ARMED
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(post0, "_jarvis_phone_notifications", False):
        _ARMED = True
        return "  notif      Phone notifications answers at /api/notifications/phone (already on)"

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
        route = urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if route != PATH:
            return get0(self)
        if not _allowed(self):
            return None
        try:
            out = _view()
        except Exception as exc:
            return self._send(503, {"error": type(exc).__name__})
        return self._send(200, out)

    def do_POST(self):
        route = urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if route != PATH:
            return post0(self)
        if not _allowed(self):
            return None
        try:
            body = json.loads(read_body(self) or b"{}")
        except Exception as exc:
            return self._send(400, {"error": type(exc).__name__})
        try:
            code, out = request(body.get("enabled"), set_enabled)
        except Exception as exc:
            code, out = 503, {"ok": False, "error": type(exc).__name__}
        return self._send(code, out)

    do_GET._jarvis_phone_notifications = True
    do_POST._jarvis_phone_notifications = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    _ARMED = True
    on = settings()["enabled"]
    return ("  notif      Phone notifications: "
            + ("on - the phone may read them" if on else "off - never read"))


if __name__ == "__main__":
    st = settings()
    print(f"  Phone notifications: {'on' if st['enabled'] else 'off'}"
          + (f" ({st['why']})" if st["why"] else ""))
