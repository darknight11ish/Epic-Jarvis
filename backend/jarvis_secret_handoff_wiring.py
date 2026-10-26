"""jarvis_secret_handoff_wiring.py - the host half of the owner-secret hand-off.

WHAT THIS IS

`jarvis_secret_handoff.py` is the rule engine: the taint table, the card state
machine and the abort conditions. This module is the thin host layer the engine
was designed to be injected into. It does four things and nothing else:

  1. When the agent's UI-control plan contains a `type` request aimed at a
     password-masked control, it MEASURES that control with Windows UI
     Automation (pid, hwnd, window class, control identity, IsPassword=True) and
     raises one hand-off card with the agent's own `why` as the untrusted note.
  2. It keeps the measured descriptor (never a secret) beside the card, so the
     fill can re-measure the same window and control.
  3. It serves a host-only POST pair for the HUD (create / fill) plus a
     read-only GET for the pending card and a POST cancel. Token and loopback
     are checked before any body is read; the body is never logged or echoed.
  4. On fill it re-measures the stored target, builds a live
     VerifiedTargetSnapshot from that measurement, and calls
     `execute_owner_fill(..., from_this_pc=True)`. The engine - not this module
     - decides every void condition and whether anything is typed.

WHAT IS DELIBERATELY NOT WIRED (honest, 2026-10-26)

The browser path is NOT wired in this slice. `jarvis_browser_control.py` has no
session handle that the HUD can name: its sessions are created and named by the
browser tool itself, so a HUD poll has nothing stable to ask for. Desktop-only
is therefore what this module ships, and docs/ARCHITECTURE.md section 8 says so
plainly rather than inventing a HUD-owned browser session.

The focus note, said plainly: by the time the owner types into the card the HUD
has the OS focus, so a live snapshot cannot be "whatever is focused now" - it
would always be the HUD's own input. This module therefore re-measures the
STORED target window and control (same hwnd, same window class, same control
identity, still password-masked). The engine's `control_id` equality check is
what proves it is still the same control. This is the honest reading of the
design's "the focused control changed" rule for a card that is itself a window.

WHAT IS NEVER DONE, AND EACH IS TESTED

  * the secret is never put in a log line, an error message, a response body,
    a stored descriptor, a filename or the HUD DOM after submit;
  * the route never reads the body before the token and loopback checks pass;
  * the route never returns the request body back to the caller;
  * the engine is the only place a card is voided or a secret is refused; this
    module does not repeat those checks - it only measures, stores metadata and
    forwards to the engine.
"""
from __future__ import annotations

import ipaddress
import json
import threading
import time
from typing import Callable, Optional

from jarvis_secret_handoff import (  # noqa: F401 - the one place the rules live
    HANDOFF_CARD_TTL_S,
    SecretHandoffError,
    SecretHandoffVoidedError,
    VerifiedTargetSnapshot,
    clean_agent_purpose,
    create_handoff_card,
    execute_owner_fill,
    handoffs,
)

#: Routes this module installs round the server's Handler.
PENDING_PATH = "/api/secret-handoff/pending"
CREATE_PATH = "/api/secret-handoff/create"
FILL_PATH = "/api/secret-handoff/fill"
CANCEL_PATH = "/api/secret-handoff/cancel"
PATHS = (PENDING_PATH,)
POST_PATHS = (CREATE_PATH, FILL_PATH, CANCEL_PATH)

#: The largest JSON body this module will accept, in bytes. A secret is at most
#: SECRET_MAX_CHARS characters; the rest is one small handoff id.
MAX_BODY_BYTES = 16 * 1024

#: The one place a measured target descriptor lives. The values are metadata
#: about a window/control; the secret is never passed here and never stored.
_CARDS: dict = {}
_LOCK = threading.RLock()
_CARD_ORDER: list = []


# --------------------------------------------------------------------------
#   Where the measurement comes from
# --------------------------------------------------------------------------

def _ui():
    """`jarvis_ui_control`, imported lazily so this module is testable without
    a desktop and so the import order cannot cycle (ui_control calls back into
    this module only through a lazy import of its own)."""
    import jarvis_ui_control
    return jarvis_ui_control


def _descriptor_from_plan(window: str, index: int) -> dict:
    """Measure, with UIA, the password control a plan request pointed at.

    Raises RuntimeError (never returns a guessed target) when the window or the
    control cannot be measured, or the control is not password-masked.
    """
    return _ui().secret_handoff_descriptor(window, index)


def card_from_plan(*, window: str, index: int, purpose: object, goal: str = "") -> dict:
    """Raise one card for a password control an agent's plan asked to type in.

    Called by `jarvis_ui_control.plan()` when a `type` request targets a masked
    control. The agent's `why` is untrusted text; the target facts come from
    UIA, not from the model. Returns the card view the HUD polls for.
    """
    desc = _descriptor_from_plan(str(window), int(index))
    snap = VerifiedTargetSnapshot(
        target_key=desc["target_key"],
        kind="desktop_window",
        display_origin=desc["display_origin"],
        is_https=True,                       # the badge does not apply to a window
        is_password_field=True,
        control_id=desc["control_id"],
        agent_claimed_purpose=clean_agent_purpose(purpose),
    )
    card = create_handoff_card(snapshot=snap)
    with _LOCK:
        _CARDS[card["handoff_id"]] = {
            **desc, "goal": str(goal or ""), "at": time.time(),
            "view": _card_view(card), "purpose": snap.agent_claimed_purpose}
        _CARD_ORDER.append(card["handoff_id"])
    return card


def card_from_focused_target(purpose: object) -> dict:
    """Raise one card from the control that has focus RIGHT NOW.

    This is the `POST create` route's honest fallback, used by a caller that
    really is looking at the target (a test, or a host script) rather than by
    the HUD button, which would have moved focus to itself.
    """
    desc = _ui().secret_handoff_focused_descriptor()
    snap = VerifiedTargetSnapshot(
        target_key=desc["target_key"],
        kind="desktop_window",
        display_origin=desc["display_origin"],
        is_https=True,
        is_password_field=True,
        control_id=desc["control_id"],
        agent_claimed_purpose=clean_agent_purpose(purpose),
    )
    card = create_handoff_card(snapshot=snap)
    with _LOCK:
        _CARDS[card["handoff_id"]] = {
            **desc, "goal": "", "at": time.time(),
            "view": _card_view(card), "purpose": snap.agent_claimed_purpose}
        _CARD_ORDER.append(card["handoff_id"])
    return card


def _card_view(card: dict) -> dict:
    """The HUD's view of a card: two labelled boxes, no secret, ids only."""
    return {
        "handoff_id": card.get("handoff_id"),
        "verified_target": card.get("verified_target"),
        "target_kind": card.get("target_kind"),
        "is_https": bool(card.get("is_https")),
        "is_password_field": True,
        "agent_claimed_purpose": card.get("agent_claimed_purpose") or "",
        "agent_purpose_is_untrusted": True,
        "expires_in_seconds": int(card.get("expires_in_seconds") or 0),
    }


def pending_cards() -> list:
    """Cards waiting for the owner, newest metadata only (never a secret).

    Expiry is filtered with the engine's own HANDOFF_CARD_TTL_S. The engine
    still owns the real card state: a card that expired here is dropped by
    `execute_owner_fill` too if the HUD never got the update.
    """
    now = time.time()
    stale = []
    out = []
    with _LOCK:
        for hid in list(_CARD_ORDER):
            desc = _CARDS.get(hid)
            if not desc:
                stale.append(hid)
                continue
            if (now - float(desc.get("at") or 0)) > HANDOFF_CARD_TTL_S:
                stale.append(hid)
                continue
            view = dict(desc.get("view") or {})
            if not view:
                continue
            remaining = HANDOFF_CARD_TTL_S - (now - float(desc.get("at") or now))
            view["expires_in_seconds"] = max(0, int(remaining))
            out.append(view)
    for hid in stale:
        _drop(hid)
    return out


def _drop(handoff_id: str) -> None:
    with _LOCK:
        _CARDS.pop(handoff_id, None)
        try:
            _CARD_ORDER.remove(handoff_id)
        except ValueError:
            pass


# --------------------------------------------------------------------------
#   The fill
# --------------------------------------------------------------------------

def fill_card(handoff_id: str, secret_value: str) -> dict:
    """Re-measure the stored target, then let the ENGINE decide and type.

    The module does not pre-check the engine's abort conditions. If the target
    cannot be measured at all, that is a host measurement failure reported as
    such (nothing was typed); otherwise the live snapshot is handed to
    `execute_owner_fill`, which is the only authority on void/no-secret.
    """
    with _LOCK:
        desc = dict(_CARDS.get(str(handoff_id or "")) or {})
    if not desc:
        raise SecretHandoffVoidedError(
            "That secret hand-off card is unknown, used or expired; nothing was typed.")
    try:
        live = _ui().secret_handoff_live_snapshot(desc)
    except Exception as exc:  # noqa: BLE001 - measurement failure, not a void
        _drop(handoff_id)
        raise SecretHandoffError(
            "The host could not re-measure the target window, so nothing was "
            f"typed ({type(exc).__name__}).") from exc
    live_snap = VerifiedTargetSnapshot(
        target_key=live["target_key"],
        kind="desktop_window",
        display_origin=live["display_origin"],
        is_https=True,
        is_password_field=bool(live.get("is_password_field")),
        control_id=live["control_id"],
        agent_claimed_purpose=clean_agent_purpose(desc.get("purpose") or ""),
    )
    try:
        receipt = execute_owner_fill(
            str(handoff_id), secret_value,
            current_live_snapshot=live_snap,
            type_into_control_fn=lambda control_id, value: _ui().secret_handoff_type(
                desc, value),
            from_this_pc=True,
        )
    except SecretHandoffError:
        _drop(handoff_id)
        raise
    except Exception:
        # The engine taints BEFORE typing, so a typing failure still leaves the
        # target read-locked; the card is spent in the engine too.
        _drop(handoff_id)
        raise
    _drop(handoff_id)
    return receipt


def cancel_card(handoff_id: str) -> bool:
    """The owner pressed Cancel. Drops the engine card and its descriptor."""
    hid = str(handoff_id or "")
    with _LOCK:
        known = hid in _CARDS
    try:
        engine_aborted = bool(handoffs().abort_handoff(hid))
    except Exception:  # noqa: BLE001
        engine_aborted = False
    _drop(hid)
    return bool(known or engine_aborted)


# --------------------------------------------------------------------------
#   Routes - installed round the server's own Handler
# --------------------------------------------------------------------------

def _loopback(peer) -> bool:
    text = str(peer or "").strip().strip("[]")
    if not text:
        return False
    try:
        return ipaddress.ip_address(text).is_loopback
    except ValueError:
        return False


def _from_this_pc(peer, local) -> bool:
    """Peer is a loopback address (or exactly the local address on a loopback
    socket). Anything else is refused before its body is read."""
    if _loopback(peer):
        return True
    return bool(peer) and bool(local) and str(peer) == str(local) and _loopback(local)


def _refusal(code: int, words: str) -> tuple:
    return code, {"ok": False, "error": words}


def handle_get(path: str, *, peer=None, local=None) -> tuple:
    if path != PENDING_PATH:
        return _refusal(404, "no such route")
    if not _from_this_pc(peer, local):
        return _refusal(403, "the owner-secret hand-off card can only be shown on this PC")
    return 200, {"ok": True, "cards": pending_cards()}


def handle_post(path: str, body: dict, *, peer=None, local=None) -> tuple:
    if not _from_this_pc(peer, local):
        # Refused BEFORE any body is read: another machine gets at most its
        # own headers, and nothing is typed from here.
        return _refusal(403, "the owner-secret hand-off can only be answered on this PC")
    if not isinstance(body, dict):
        return _refusal(400, "send one small JSON object")
    if path == CANCEL_PATH:
        hid = str(body.get("handoff_id") or "")
        if not hid:
            return _refusal(400, "that request did not name a card")
        return 200, {"ok": True, "cancelled": cancel_card(hid)}
    if path == CREATE_PATH:
        purpose = body.get("purpose")
        try:
            card = card_from_focused_target(purpose)
        except SecretHandoffVoidedError as exc:
            return _refusal(409, str(exc))
        except SecretHandoffError as exc:
            return _refusal(409, str(exc))
        except Exception as exc:  # noqa: BLE001 - measurement failure
            return _refusal(409, "the host could not verify a password-masked "
                                 f"control ({type(exc).__name__})")
        return 200, {"ok": True, "card": _card_view(card)}
    if path == FILL_PATH:
        hid = str(body.get("handoff_id") or "")
        secret_value = body.get("secret")
        if not hid:
            return _refusal(400, "that request did not name a card")
        try:
            receipt = fill_card(hid, secret_value if isinstance(secret_value, str) else "")
        except SecretHandoffVoidedError as exc:
            return _refusal(409, str(exc))
        except SecretHandoffError as exc:
            return _refusal(409, str(exc))
        except Exception as exc:  # noqa: BLE001 - typing/measurement failure
            return _refusal(500, f"the fill failed ({type(exc).__name__}); the "
                                 "target is read-locked and the card is spent")
        return 200, receipt
    return _refusal(404, "no such route")


def install(handler_cls, *, origin_ok, token_ok, read_body=None) -> str:
    """Wrap do_GET/do_POST so this module's routes are answered after the
    server's own origin and token checks. Like every other installed route
    module, every other request goes to the original handler.

    The body is read only AFTER the origin, token and loopback checks pass, and
    it is never logged, echoed or kept beyond the one handler call.
    """
    if getattr(handler_cls.do_GET, "_jarvis_secret_handoff", False):
        return "  secrets    Owner-secret hand-off card: on (already)"
    get0 = handler_cls.do_GET
    post0 = getattr(handler_cls, "do_POST", None)

    def _route(self) -> str:
        path = str(getattr(self, "path", "") or "")
        return path.split("?", 1)[0].rstrip("/")

    def _peer_local(self) -> tuple:
        peer = local = None
        try:
            peer = self.client_address[0]
        except Exception:  # noqa: BLE001
            pass
        try:
            local = self.connection.getsockname()[0]
        except Exception:  # noqa: BLE001
            pass
        return peer, local

    def _allowed(self) -> bool:
        try:
            if not origin_ok(self):
                self._send(403, {"error": "cross-origin request refused"})
                return False
            if not token_ok(self):
                self._send(401, {"error": "bad or missing X-Jarvis-Token"})
                return False
        except Exception:  # noqa: BLE001
            self._send(401, {"error": "bad or missing X-Jarvis-Token"})
            return False
        return True

    def do_GET(self):
        route = _route(self)
        if route != PENDING_PATH:
            return get0(self)
        if not _allowed(self):
            return None
        peer, local = _peer_local(self)
        code, out = handle_get(route, peer=peer, local=local)
        return self._send(code, out)

    def do_POST(self):
        route = _route(self)
        if route not in POST_PATHS:
            if post0 is None:
                return self._send(405, {"error": "this server has no POST handler"})
            return post0(self)
        if not _allowed(self):
            return None
        peer, local = _peer_local(self)
        if not _from_this_pc(peer, local):
            return self._send(403, {"ok": False,
                                    "error": "the owner-secret hand-off can only be "
                                             "answered on this PC"})
        if read_body is None:
            return self._send(501, {"ok": False, "error": "this server has no request reader"})
        try:
            raw = read_body(self) or b"{}"
            if len(raw) > MAX_BODY_BYTES:
                return self._send(413, {"ok": False, "error": "that request is too big"})
            body = json.loads(raw)
        except Exception as exc:  # noqa: BLE001 - the exception NAME only
            return self._send(400, {"ok": False,
                                    "error": f"bad JSON ({type(exc).__name__})"})
        code, out = handle_post(route, body, peer=peer, local=local)
        return self._send(code, out)

    do_GET._jarvis_secret_handoff = True
    handler_cls.do_GET = do_GET
    if post0 is not None:
        handler_cls.do_POST = do_POST
    return "  secrets    Owner-secret hand-off card: on"

