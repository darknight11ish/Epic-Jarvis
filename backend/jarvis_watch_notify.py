"""jarvis_watch_notify.py - the smartwatch notification setting.

NEW MODULE, shipped whole (watch-notifications.patch wraps the running
server's `do_GET`/`do_POST`, like `jarvis_documents.install()` and
`jarvis_stop_all.install()` do, rather than adding an inline route block -
`jarvis_hud.py`'s real text is not in this repository, so a new route can
only be added by wrapping the handler after it is built, which needs no
context inside the file at all).

THE OWNER'S DECISION (CLAUDE.md, 2026-09-25, the competitiveness audit;
reconfirmed 2026-09-27, `docs/OWNER-QUESTIONS-2026-09-27.md` Q17)

"Smartwatch: every notification stays on the phone by default, with a
setting to let them all show on a compatible watch (turning it on raises a
card, turning it off is instant)." An overnight fix already made every
Jarvis notification `.setLocalOnly(true)` - Android bridges a phone's
notifications to a paired watch by default, and that call is what refuses
it. What was missing is the SETTING itself: a way to turn bridging back on,
with the same permission model as every other switch here.

WHY THIS LIVES ON THE PC, NOT ONLY ON THE PHONE

Every other switch with this exact shape - "Learn automatically", "Also
remember sensitive topics automatically", the voice settings - is settled
on the PC and read by both apps, even when only one app's behaviour changes
because of it (`docs/ARCHITECTURE.md` section 3: one permission model, one
place approval cards come from). A smartwatch is Android-only, so only the
phone ever reads this setting or acts on it - but it is still a decision
the owner makes with the SAME approval card and Windows Hello check every
other risky change gets, not a bare Android switch a stolen or borrowed
phone could flip on its own. See `docs/ARCHITECTURE.md` section 8,
"On the phone, kept off the desktop", for the one-sided half of this.

WHAT "SHOWING ON A WATCH" ACTUALLY MEANS HERE

There is no Jarvis watch app, and the competitiveness audit says plainly
that one is "not for Jarvis" (a Wear OS app would sync through Google's own
servers - rule 1). This setting does not build one. It only chooses what
`.setLocalOnly(...)` the phone's own `NotificationCompat.Builder` calls get:
`true` (the default) keeps Android's own, already-built-in notification
bridging from ever reaching a paired watch; turning this ON simply stops
refusing it, so Android's own bridging (Bluetooth to a paired companion
device, no Jarvis code in the middle) does the rest, exactly as it would
for any other app that has not opted out. Turning it OFF refuses it again,
at once.

THE SHAPE (the same as `jarvis_learning_switch.py`)
    ON   one approval card, action `watch_notifications_enable`, and this
         returns at once with 202 {"waiting": true, ...} - not "it is on".
         The card is decided on its own thread; only tier "ask" with
         outcome "approved" turns it on. Denied, timed out, refused, or
         turned off while the card waited: nothing changes.
    OFF  immediate, never a card - it only narrows what a phone may do, and
         an off switch that could time out would leave bridging running.
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

ACTION = "watch_notifications_enable"

PATH = "/api/notifications/watch"

CARD_TEXT = "\n".join([
    "Show Jarvis's notifications on a paired smartwatch.",
    "",
    "Right now every notification - approval cards, timers, reminders, "
    "\"tell me when\" alerts - stays on your phone. Turning this on lets "
    "your phone's own notification bridging copy them to a compatible "
    "watch too, the same as any other app that has not opted out.",
    "",
    "Jarvis does not build or need a watch app for this - it is your "
    "phone's own feature. Nothing changes on this PC.",
    "",
    "You can turn it off again at any time, from either app, and that is "
    "instant.",
    "",
    "If you say no: notifications stay on the phone only.",
])

_LOCK = threading.Lock()
_PENDING: dict = {}          # {"id", "since"} while an ON card waits
_WITHDRAWN: set = set()
_LAST: dict = {}             # {"outcome", "why", "at"} - how the last card ended
_LATEST: dict = {}           # {"id"} - the card raised most recently; only it sets _LAST
#: Held from an approved card's "was it withdrawn?" check through
#: _save(enabled=True), and from OFF's withdrawing through _save(enabled=False):
#: the lesson of jarvis_learning_switch.py's own R5.
_SWITCH = threading.Lock()

LAST_WORDS = {
    "enabled": "You approved the card, so notifications may show on a watch.",
    "denied": "The card was turned down, so notifications stay on the phone only.",
    "timed_out": "Nobody answered the card in time, so notifications stay on the phone only.",
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
    return _config_dir() / "watch-notifications.json"


_SETTINGS_LOCK = threading.Lock()

_DAMAGED = ("the smartwatch notifications settings file is damaged, so notifications "
            "stay on the phone only. Turn this on again to rewrite it")


def settings() -> dict:
    """{"enabled", "why"}. No file, or one that never had "enabled": OFF -
    the owner's default. A file that cannot be read, is not JSON, or holds
    anything but true/false: OFF, and `why` says so (fail closed - the safe
    direction here is staying on the phone only)."""
    try:
        raw = settings_path().read_text(encoding="utf-8")
    except FileNotFoundError:
        return {"enabled": False, "why": ""}
    except OSError as exc:
        return {"enabled": False,
                "why": f"the smartwatch notifications settings file could not be read "
                       f"({type(exc).__name__}), so notifications stay on the phone only"}
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
    threading.Thread(target=fn, name="jarvis-watch-notify-card", daemon=True).start()


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
    _audit("watch_notify.card", {"outcome": outcome})


def _decide(pid: str, apply: Callable[[bool], dict], gate: Callable,
            tier_of: Callable[[str], str]) -> None:
    try:
        v = gate(ACTION, {"text": CARD_TEXT, "what": "show notifications on a watch",
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
    """POST /api/notifications/watch. Returns (http code, body). `apply` is
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
        out.update(waiting=False, message="Notifications stay on the phone only.")
        _audit("watch_notify.off", {})
        return 200, out
    tier = tier_of(ACTION)
    if tier != "ask":
        return 503, {"ok": False, "error": (
            f"{ACTION} is tier {tier!r} in jarvis-framework.toml; letting notifications "
            f"show on a watch needs a person to say yes, so it must be 'ask'")}
    with _LOCK:
        if _PENDING:
            return 202, {"ok": True, "waiting": True, "enabled": False,
                         "message": "A card to allow notifications on a watch is already "
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
                 "message": "Waiting for your approval. Notifications reach a watch only if "
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
#   The route - wrapped round the handler, like jarvis_documents.install()
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
    """Wrap `handler_cls.do_GET` and `do_POST` so GET/POST /api/notifications/watch
    are answered here, after the server's own origin and token checks. Every
    other request goes straight to the original. Returns the banner line."""
    global _ARMED
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(post0, "_jarvis_watch_notify", False):
        _ARMED = True
        return "  watch      Smartwatch notifications answers at /api/notifications/watch (already on)"

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

    do_GET._jarvis_watch_notify = True
    do_POST._jarvis_watch_notify = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    _ARMED = True
    on = settings()["enabled"]
    return ("  watch      Smartwatch notifications: "
            + ("on - a watch may show them" if on else "off - phone only"))


if __name__ == "__main__":
    st = settings()
    print(f"  Smartwatch notifications: {'on' if st['enabled'] else 'off'}"
          + (f" ({st['why']})" if st["why"] else ""))
