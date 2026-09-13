"""WebSocket endpoint for the Jarvis Mobile Android client.

Drop-in for a desktop server already built on ``http.server``. No third-party
dependencies: ``BaseHTTPRequestHandler`` cannot speak WebSocket, so this hijacks
the connection after the 101 response and implements RFC 6455 framing directly.
That keeps the endpoint on the same port the phone already dials rather than
forcing a migration to aiohttp or a second listener.

Wire up in your handler's ``do_GET``::

    from jarvis_mobile_ws import MobileEndpoint, ApprovalVerifier

    ENDPOINT = MobileEndpoint(
        verifier=ApprovalVerifier(secret=os.environ["JARVIS_SHARED_SECRET"]),
        auth_token=os.environ.get("JARVIS_AUTH_TOKEN"),
    )

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self):
            if self.path == MobileEndpoint.PATH:
                ENDPOINT.serve(self)      # blocks for the life of the socket
                return
            ...

Serve it from ``ThreadingHTTPServer``; each phone occupies one thread.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import socket
import struct
import threading
import time
from typing import Any, Callable, Iterable, Iterator

log = logging.getLogger("jarvis.mobile")

_WS_GUID = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

OP_CONT = 0x0
OP_TEXT = 0x1
OP_BINARY = 0x2
OP_CLOSE = 0x8
OP_PING = 0x9
OP_PONG = 0xA

# The phone sends 20ms PCM chunks; anything approaching this is malformed.
MAX_FRAME_BYTES = 1 << 20

# The client pings every 25s. Three missed intervals means the peer is gone.
READ_TIMEOUT_SECONDS = 90.0


# --------------------------------------------------------------- approvals ----


class ApprovalVerifier:
    """Verifies the signed approval envelope the phone returns.

    Signed payload::

        {id}|{approved}|{device_id}|{decided_at_ms}|{nonce}

    Checks run signature-first so unauthenticated input never reaches the
    replay cache, and the nonce is claimed atomically: two threads racing the
    same replayed decision must not both win.
    """

    def __init__(
        self,
        secret: str,
        *,
        allowed_device_ids: Iterable[str] | None = None,
        max_clock_skew_ms: int = 60_000,
        nonce_ttl_seconds: int = 300,
    ) -> None:
        if not secret:
            # Fail closed at construction. A server that starts without a key
            # would otherwise accept whatever the phone refuses to sign.
            raise ValueError("ApprovalVerifier requires a non-empty shared secret")
        self._secret = secret.encode("utf-8")
        self._allowed = set(allowed_device_ids) if allowed_device_ids else None
        self._max_skew_ms = max_clock_skew_ms
        self._ttl = nonce_ttl_seconds
        self._nonces: dict[str, float] = {}
        self._lock = threading.Lock()

    def verify(
        self,
        payload: dict[str, Any],
        *,
        is_pending: Callable[[str], bool] | None = None,
    ) -> tuple[bool, str]:
        """Returns ``(ok, reason)``. Consumes the nonce only on success."""
        request_id = payload.get("id")
        approved = payload.get("approved")
        device_id = payload.get("device_id")
        decided_at = payload.get("decided_at_ms")
        nonce = payload.get("nonce")
        signature = payload.get("signature")

        if not isinstance(request_id, str) or not request_id:
            return False, "missing id"
        # Explicit bool test: a JSON string "true" must not coerce into a
        # decision, and `approved is True` alone would silently read it as
        # a rejection rather than rejecting the payload.
        if not isinstance(approved, bool):
            return False, "approved must be a JSON boolean"
        if not isinstance(device_id, str) or not device_id:
            return False, "missing device_id"
        if not isinstance(decided_at, int):
            return False, "missing decided_at_ms"
        if not isinstance(nonce, str) or not nonce:
            return False, "missing nonce"
        if not isinstance(signature, str) or not signature:
            return False, "missing signature"

        if self._allowed is not None and device_id not in self._allowed:
            return False, "unknown device_id"

        canonical = f"{request_id}|{'true' if approved else 'false'}|{device_id}|{decided_at}|{nonce}"
        expected = hmac.new(
            self._secret, canonical.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return False, "invalid signature"

        now_ms = int(time.time() * 1000)
        if abs(now_ms - decided_at) > self._max_skew_ms:
            return False, "timestamp outside skew window"

        if is_pending is not None and not is_pending(request_id):
            return False, "no such pending approval"

        if not self._claim_nonce(nonce):
            return False, "replayed nonce"

        return True, "verified"

    def _claim_nonce(self, nonce: str) -> bool:
        now = time.monotonic()
        with self._lock:
            # Prune here rather than on a timer: the cache only grows on the
            # same code path that cleans it.
            if self._nonces:
                cutoff = now - self._ttl
                stale = [k for k, seen in self._nonces.items() if seen < cutoff]
                for key in stale:
                    del self._nonces[key]
            if nonce in self._nonces:
                return False
            self._nonces[nonce] = now
            return True

    @property
    def tracked_nonces(self) -> int:
        with self._lock:
            return len(self._nonces)


# -------------------------------------------------------------- ws framing ----


class WebSocketClosed(Exception):
    pass


class MobileSocket:
    """One connected handset. Send methods are safe from any thread."""

    def __init__(self, connection: socket.socket, rfile, wfile) -> None:
        self._conn = connection
        self._rfile = rfile
        self._wfile = wfile
        self._write_lock = threading.Lock()
        self._closed = False

    # -- reading ---------------------------------------------------------

    def read_message(self) -> tuple[int, bytes] | None:
        """Blocks for one complete data message. ``None`` once the peer goes."""
        fragments: list[bytes] = []
        message_op: int | None = None

        while True:
            frame = self._read_frame()
            if frame is None:
                return None
            fin, opcode, payload = frame

            if opcode == OP_CLOSE:
                self._safe_send(OP_CLOSE, payload[:2])
                self._closed = True
                return None
            if opcode == OP_PING:
                # Mandatory: OkHttp fails the connection if its ping goes
                # unanswered within the ping interval.
                self._safe_send(OP_PONG, payload)
                continue
            if opcode == OP_PONG:
                continue

            if opcode == OP_CONT:
                if message_op is None:
                    raise WebSocketClosed("continuation without a start frame")
                fragments.append(payload)
            elif opcode in (OP_TEXT, OP_BINARY):
                message_op = opcode
                fragments = [payload]
            else:
                raise WebSocketClosed(f"reserved opcode {opcode:#x}")

            if fin:
                assert message_op is not None
                return message_op, b"".join(fragments)

    def _read_frame(self) -> tuple[bool, int, bytes] | None:
        header = self._read_exact(2)
        if header is None:
            return None
        b0, b1 = header[0], header[1]
        fin = bool(b0 & 0x80)
        opcode = b0 & 0x0F
        masked = bool(b1 & 0x80)
        length = b1 & 0x7F

        if length == 126:
            raw = self._read_exact(2)
            if raw is None:
                return None
            length = struct.unpack("!H", raw)[0]
        elif length == 127:
            raw = self._read_exact(8)
            if raw is None:
                return None
            length = struct.unpack("!Q", raw)[0]

        if length > MAX_FRAME_BYTES:
            raise WebSocketClosed(f"frame of {length} bytes exceeds cap")
        if not masked:
            # RFC 6455 §5.1: every client frame must be masked.
            raise WebSocketClosed("unmasked frame from client")

        mask = self._read_exact(4)
        if mask is None:
            return None
        payload = self._read_exact(length) if length else b""
        if payload is None:
            return None

        return fin, opcode, _apply_mask(payload, mask)

    def _read_exact(self, count: int) -> bytes | None:
        chunks: list[bytes] = []
        remaining = count
        while remaining > 0:
            try:
                chunk = self._rfile.read(remaining)
            except (socket.timeout, TimeoutError):
                raise WebSocketClosed("read timed out; peer is gone")
            except OSError as exc:
                raise WebSocketClosed(f"read failed: {exc}")
            if not chunk:
                return None
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    # -- writing ---------------------------------------------------------

    def send_text(self, text: str) -> None:
        self._send(OP_TEXT, text.encode("utf-8"))

    def send_json(self, payload: dict[str, Any]) -> None:
        self.send_text(json.dumps(payload, separators=(",", ":")))

    def send_binary(self, data: bytes) -> None:
        self._send(OP_BINARY, data)

    def close(self, code: int = 1000) -> None:
        self._safe_send(OP_CLOSE, struct.pack("!H", code))
        self._closed = True

    def _send(self, opcode: int, payload: bytes) -> None:
        if self._closed:
            raise WebSocketClosed("socket already closed")
        header = bytearray()
        header.append(0x80 | opcode)
        size = len(payload)
        if size < 126:
            header.append(size)
        elif size < 65_536:
            header.append(126)
            header += struct.pack("!H", size)
        else:
            header.append(127)
            header += struct.pack("!Q", size)

        with self._write_lock:
            try:
                self._wfile.write(bytes(header) + payload)
                self._wfile.flush()
            except OSError as exc:
                self._closed = True
                raise WebSocketClosed(f"write failed: {exc}")

    def _safe_send(self, opcode: int, payload: bytes) -> None:
        try:
            self._send(opcode, payload)
        except WebSocketClosed:
            pass

    # -- protocol helpers ------------------------------------------------

    def send_approval_request(
        self,
        request_id: str,
        title: str,
        summary: str = "",
        tier: str = "ask",
        detail: str | None = None,
        expires_at_ms: int | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "type": "approval_request",
            "id": request_id,
            "title": title,
            "summary": summary,
            "tier": tier,
        }
        if detail is not None:
            payload["detail"] = detail
        if expires_at_ms is not None:
            payload["expires_at_ms"] = expires_at_ms
        self.send_json(payload)

    def send_approval_resolved(self, request_id: str, approved: bool) -> None:
        self.send_json(
            {"type": "approval_resolved", "id": request_id, "approved": approved}
        )

    def send_status(self, text: str) -> None:
        self.send_json({"type": "status", "text": text})

    def send_desktop_telemetry(self, **fields: float | None) -> None:
        payload: dict[str, Any] = {"type": "desktop_telemetry"}
        payload.update({k: v for k, v in fields.items() if v is not None})
        self.send_json(payload)

    def send_device_command(
        self, command_id: str, action: str, params: dict[str, Any] | None = None
    ) -> None:
        self.send_json(
            {
                "type": "device_command",
                "id": command_id,
                "action": action,
                "params": params or {},
            }
        )

    def send_audio_stream(
        self,
        stream_id: str,
        chunks: Iterator[bytes],
        sample_rate: int = 22_050,
        channels: int = 1,
        binary_tag: int = 1,
    ) -> None:
        """Streams PCM as tagged binary frames, avoiding base64 inflation."""
        if not 0 <= binary_tag <= 255:
            raise ValueError("binary_tag must fit in one byte")
        prefix = bytes([binary_tag])
        self.send_json(
            {
                "type": "audio_stream_start",
                "stream_id": stream_id,
                "sample_rate": sample_rate,
                "channels": channels,
                "encoding": "pcm16",
                "binary_tag": binary_tag,
            }
        )
        try:
            for chunk in chunks:
                if chunk:
                    self.send_binary(prefix + chunk)
        finally:
            self.send_json({"type": "audio_stream_end", "stream_id": stream_id})


def _apply_mask(payload: bytes, mask: bytes) -> bytes:
    if not payload:
        return payload
    # Big-integer XOR beats a per-byte Python loop by a wide margin, which
    # matters at 32 KB/s of continuous uplink PCM.
    size = len(payload)
    repeats, remainder = divmod(size, 4)
    full_mask = mask * repeats + mask[:remainder]
    return (
        int.from_bytes(payload, "big") ^ int.from_bytes(full_mask, "big")
    ).to_bytes(size, "big")


def compute_accept(key: str) -> str:
    digest = hashlib.sha1(key.encode("ascii") + _WS_GUID).digest()
    return base64.b64encode(digest).decode("ascii")


# ---------------------------------------------------------------- endpoint ----


class MobileEndpoint:
    """Handles the upgrade and the message loop for one connected phone."""

    PATH = "/api/mobile/ws"

    def __init__(
        self,
        verifier: ApprovalVerifier,
        *,
        auth_token: str | None = None,
        on_approval: Callable[[str, bool, MobileSocket], None] | None = None,
        on_audio: Callable[[bytes, MobileSocket], None] | None = None,
        on_event: Callable[[dict[str, Any], MobileSocket], None] | None = None,
        is_pending: Callable[[str], bool] | None = None,
    ) -> None:
        self._verifier = verifier
        self._auth_token = auth_token or None
        self._on_approval = on_approval
        self._on_audio = on_audio
        self._on_event = on_event
        self._is_pending = is_pending
        self._clients: set[MobileSocket] = set()
        self._clients_lock = threading.Lock()

    @property
    def clients(self) -> list[MobileSocket]:
        with self._clients_lock:
            return list(self._clients)

    def broadcast(self, send: Callable[[MobileSocket], None]) -> int:
        """Applies ``send`` to every live client; returns how many succeeded."""
        delivered = 0
        for client in self.clients:
            try:
                send(client)
                delivered += 1
            except WebSocketClosed:
                self._drop(client)
        return delivered

    def serve(self, handler) -> None:
        """Upgrades and runs the read loop. Blocks until the phone disconnects."""
        if not self._handshake(handler):
            return

        handler.close_connection = True
        try:
            handler.connection.settimeout(READ_TIMEOUT_SECONDS)
        except OSError:
            pass

        client = MobileSocket(handler.connection, handler.rfile, handler.wfile)
        with self._clients_lock:
            self._clients.add(client)

        try:
            self._pump(client)
        except WebSocketClosed as exc:
            log.info("mobile client closed: %s", exc)
        except Exception:
            log.exception("mobile client failed")
        finally:
            self._drop(client)

    def _pump(self, client: MobileSocket) -> None:
        while True:
            message = client.read_message()
            if message is None:
                return
            opcode, payload = message

            if opcode == OP_BINARY:
                if self._on_audio is not None:
                    self._on_audio(payload, client)
                continue

            try:
                event = json.loads(payload.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                log.warning("dropping unparseable text frame")
                continue
            if not isinstance(event, dict):
                continue

            if event.get("type") == "ping":
                # Echo the phone's own clock reading back untouched: it measures
                # the round trip itself, so the two clocks need not agree.
                sent_at = event.get("sent_at_ms")
                if isinstance(sent_at, int):
                    try:
                        client.send_json({"type": "pong", "sent_at_ms": sent_at})
                    except WebSocketClosed:
                        return
                continue

            if event.get("type") == "approval_decision":
                ok, reason = self._verifier.verify(event, is_pending=self._is_pending)
                if not ok:
                    log.warning(
                        "rejected approval %s: %s", event.get("id"), reason
                    )
                    continue
                if self._on_approval is not None:
                    self._on_approval(event["id"], event["approved"], client)
                continue

            if self._on_event is not None:
                self._on_event(event, client)

    def _handshake(self, handler) -> bool:
        headers = handler.headers

        if (headers.get("Upgrade") or "").lower() != "websocket":
            self._refuse(handler, 400, "expected a websocket upgrade")
            return False
        if "upgrade" not in (headers.get("Connection") or "").lower():
            self._refuse(handler, 400, "missing Connection: Upgrade")
            return False
        if (headers.get("Sec-WebSocket-Version") or "").strip() != "13":
            self._refuse(handler, 426, "unsupported websocket version")
            return False

        key = (headers.get("Sec-WebSocket-Key") or "").strip()
        if not key:
            self._refuse(handler, 400, "missing Sec-WebSocket-Key")
            return False

        # Rejecting here drops the TCP stream before any WebSocket state is
        # allocated, which a token carried in the first frame cannot do.
        if self._auth_token is not None:
            presented = (headers.get("Authorization") or "").strip()
            expected = f"Bearer {self._auth_token}"
            if not hmac.compare_digest(presented, expected):
                self._refuse(handler, 401, "bad or missing bearer token")
                return False

        response = (
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {compute_accept(key)}\r\n"
            "\r\n"
        )
        handler.wfile.write(response.encode("ascii"))
        handler.wfile.flush()
        return True

    @staticmethod
    def _refuse(handler, status: int, reason: str) -> None:
        body = reason.encode("utf-8")
        handler.send_response(status)
        handler.send_header("Content-Type", "text/plain; charset=utf-8")
        handler.send_header("Content-Length", str(len(body)))
        handler.send_header("Connection", "close")
        handler.end_headers()
        handler.wfile.write(body)
        handler.close_connection = True

    def _drop(self, client: MobileSocket) -> None:
        with self._clients_lock:
            self._clients.discard(client)
        try:
            client.close()
        except WebSocketClosed:
            pass


def generate_shared_secret() -> str:
    """A 256-bit key, hex encoded, to paste into the phone's Pairing field."""
    return os.urandom(32).hex()
