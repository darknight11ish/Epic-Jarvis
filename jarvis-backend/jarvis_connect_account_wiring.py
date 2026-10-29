"""jarvis_connect_account_wiring.py - the host-only routes behind the
connect-account card.

WHAT THIS IS

`jarvis_connect_account.py` is the service table and the card state machine.
This module is the thin host half: three routes, and nothing else.

  GET  /api/connect-account/pending   the waiting card (metadata only)
  POST /api/connect-account/save      ONE card id + its field values
  POST /api/connect-account/cancel    ONE card id

It is installed by `jarvis_secret_handoff_wiring.install()`, the one entry
point `secret-handoff.patch` already calls - so this feature needs no patch of
its own and a backend without it behaves exactly as before.

WHAT IS NEVER DONE, AND EACH IS TESTED

  * The body is read only AFTER the origin, token and loopback checks pass, and
    it is never logged, echoed, stored or returned - the answer is the receipt
    from `jarvis_connect_account.save_card`, which is built from store entry
    NAMES and a verdict and cannot contain a value.
  * Another machine gets a refusal before its body is read: the value is typed
    on this PC only, and the phone has no card to type it into.
  * The value is written by `jarvis_token_store.store_secret` - Windows
    Credential Manager and nowhere else. A store failure is reported as such
    and nothing is written elsewhere.
"""
from __future__ import annotations

import ipaddress
import json
from typing import Optional

from jarvis_connect_account import (  # noqa: F401 - the one place the rules live
    ConnectAccountError,
    ConnectAccountVoided,
    cancel_card,
    pending_cards,
    save_card,
)

PENDING_PATH = "/api/connect-account/pending"
SAVE_PATH = "/api/connect-account/save"
CANCEL_PATH = "/api/connect-account/cancel"
PATHS = (PENDING_PATH,)
POST_PATHS = (SAVE_PATH, CANCEL_PATH)

#: The largest body this module accepts, in bytes: a card id, up to four field
#: names and their values (each capped at MAX_VALUE_CHARS by the engine).
MAX_BODY_BYTES = 32 * 1024


def _loopback(peer) -> bool:
    text = str(peer or "").strip().strip("[]")
    if not text:
        return False
    try:
        return ipaddress.ip_address(text).is_loopback
    except ValueError:
        return False


def _from_this_pc(peer, local) -> bool:
    if _loopback(peer):
        return True
    return bool(peer) and bool(local) and str(peer) == str(local) and _loopback(local)


def _refusal(code: int, words: str) -> tuple:
    return code, {"ok": False, "error": words}


def handle_get(path: str, *, peer=None, local=None) -> tuple:
    if path != PENDING_PATH:
        return _refusal(404, "no such route")
    if not _from_this_pc(peer, local):
        return _refusal(403, "a connect card can only be shown on this PC")
    return 200, {"ok": True, "cards": pending_cards()}


def handle_post(path: str, body: dict, *, peer=None, local=None) -> tuple:
    if not _from_this_pc(peer, local):
        return _refusal(403, "a connect card can only be answered on this PC")
    if not isinstance(body, dict):
        return _refusal(400, "send one small JSON object")
    if path == CANCEL_PATH:
        card_id = str(body.get("card_id") or "")
        if not card_id:
            return _refusal(400, "that request did not name a card")
        return 200, {"ok": True, "cancelled": cancel_card(card_id)}
    if path == SAVE_PATH:
        card_id = str(body.get("card_id") or "")
        if not card_id:
            return _refusal(400, "that request did not name a card")
        try:
            receipt = save_card(card_id, body.get("values"))
        except ConnectAccountVoided as exc:
            return _refusal(409, str(exc))
        except ConnectAccountError as exc:
            return _refusal(409, str(exc))
        except Exception as exc:            # noqa: BLE001 - the NAME only
            # Never the value and never a third-party sentence that could echo
            # one: the exception's own type, and a fixed sentence.
            return _refusal(500, f"the save failed ({type(exc).__name__}); nothing "
                                 "else was written")
        return 200, receipt
    return _refusal(404, "no such route")


def install(handler_cls, *, origin_ok, token_ok, read_body=None) -> str:
    """Wrap do_GET/do_POST so this module's routes are answered after the
    server's own origin and token checks. Every other request goes to the
    handler that was there before (which may itself be another module's
    wrapper, and ultimately the server's own).

    The body is read only AFTER the origin, token and loopback checks pass, and
    it is never logged, echoed or kept beyond the one handler call.
    """
    if getattr(handler_cls.do_GET, "_jarvis_connect_account", False):
        return "  connect    Connect-account card: on (already)"
    get0 = handler_cls.do_GET
    post0 = getattr(handler_cls, "do_POST", None)

    def _route(self) -> str:
        path = str(getattr(self, "path", "") or "")
        return path.split("?", 1)[0].rstrip("/")

    def _peer_local(self) -> tuple:
        peer = local = None
        try:
            peer = self.client_address[0]
        except Exception:                   # noqa: BLE001
            pass
        try:
            local = self.connection.getsockname()[0]
        except Exception:                   # noqa: BLE001
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
        except Exception:                   # noqa: BLE001
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
                                    "error": "a connect card can only be answered on "
                                             "this PC"})
        if read_body is None:
            return self._send(501, {"ok": False, "error": "this server has no request reader"})
        try:
            raw = read_body(self) or b"{}"
            if len(raw) > MAX_BODY_BYTES:
                return self._send(413, {"ok": False, "error": "that request is too big"})
            body = json.loads(raw)
        except Exception as exc:            # noqa: BLE001 - the exception NAME only
            return self._send(400, {"ok": False,
                                    "error": f"bad JSON ({type(exc).__name__})"})
        code, out = handle_post(route, body, peer=peer, local=local)
        return self._send(code, out)

    do_GET._jarvis_connect_account = True
    handler_cls.do_GET = do_GET
    if post0 is not None:
        handler_cls.do_POST = do_POST
    return "  connect    Connect-account card: on"


__all__ = ["PENDING_PATH", "SAVE_PATH", "CANCEL_PATH", "PATHS", "POST_PATHS",
           "MAX_BODY_BYTES", "handle_get", "handle_post", "install"]
