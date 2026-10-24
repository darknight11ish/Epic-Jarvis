#!/usr/bin/env python3
"""jarvis_live_stream.py - the persistent Live audio stream (Slice G, G2).

WHAT THIS IS. `docs/DESIGN-PHONE-LIVE-STREAM.md` (2026-10-21, owner's answers
recorded) replaces the phone's one-shot "record a clip, POST it" Live path with
ONE persistent stream: the phone sends 16 kHz mono int16 PCM frames and gets
speech frames plus small control messages back, on one socket. This module is
the PC half of that transport - the smallest honest RFC 6455 server the design
needs - and nothing else.

IT IS SWITCHED OFF, ALWAYS, UNTIL THE OWNER TURNS IT ON. The route and the
switch were frozen in an earlier slice: `jarvis_live.STREAM_ROUTE`,
`jarvis_live.stream_enabled()` reads `[live] stream` (OFF by default, a missing
key is OFF). While the switch is OFF, `jarvis_live` keeps answering its 501 stub
and this module is never called. While the switch is ON but before the speech
hand-off slice lands, a served stream still refuses a turn with a plain
sentence - it never silently pretends to answer.

WHY A HAND-ROLLED SERVER. The PC backend is stdlib-only (`ThreadingHTTPServer`)
and `backend/requirements.lock` carries no WebSocket library, and the
documented lock recipe cannot regenerate that file, so adding a dependency was
not an option. The handshake/frame subset implemented here is the one the
design needs: server role, no extensions, no subprotocols, masked client
frames, text + binary messages, ping/pong and close. The pieces a general
library would add (permessage-deflate, fragmentation reassembly, HTTP/2) are
deliberately REFUSED rather than half-supported.

SECURITY SHAPE (the gate is the caller's, before any of this runs):
  * `jarvis_live.install` checks the same origin and `X-Jarvis-Token` as every
    Live request BEFORE the upgrade, then hands the request here;
  * the tailnet bind rule is the server's (the same listener every other route
    uses) - this module opens no listener of its own;
  * audio is RAM only: a 2 s ring for the pre-roll, then a WAV handed to the
    one-shot speech path. No file, no log of audio, no transcript written here;
  * the wire refuses replayed or stale frames: every stream gets a random epoch
    byte and every audio frame a strictly increasing 32-bit sequence number.

WIRE SHAPE (matching the design's §3.2/§7 tables):
  binary, any direction : <varint length> | <epoch byte> | <seq: u32 BE> | PCM16
  text, phone -> PC     : {"t":"hello","device":...,"live_id":...}, end_turn,
                          cancel, mute
  text, PC -> phone     : ready, turn_started, speech_start/end, not_owner,
                          refused, dropped, pause, bye
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import random
import socket
import struct
import time
import wave

#: RFC 6455 handshake GUID.
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
#: The design's audio frame: 64 ms at 16 kHz mono int16 = 1,024 samples.
SAMPLE_RATE = 16000
FRAME_SAMPLES = 1024
FRAME_BYTES = FRAME_SAMPLES * 2
#: Caps. A frame can never make the process allocate more than this.
MAX_FRAME_BYTES = 64 * 1024
MAX_CONTROL_BYTES = 8 * 1024
#: 2 s pre-roll ring (the design's "last ~2 s, for the pre-roll").
RING_BYTES = SAMPLE_RATE * 2 * 2
#: One turn is bounded; a phone left talking forever is not a turn.
MAX_TURN_SECONDS = 120
#: Idle socket timeout (seconds) and the heartbeat interval.
IDLE_TIMEOUT_S = 30.0
HEARTBEAT_S = 5.0

#: Plain sentences. The phone shows these; the design's words are reused where
#: it fixed them, and every one says what happens next.
WORDS = {
    "not_built": "Jarvis can't answer over the stream yet - the speech hand-off "
                 "is not built.",
    "not_owner": "That did not sound like you - say it again.",
    "bad_frame": "The stream sent something Jarvis could not read - Live carries "
                 "on when the link is back.",
    "bad_hello": "Live could not start on this stream - start Live again.",
    "no_session": "Live is not on for this device - press Live, then talk.",
    "dropped": "Connection dropped - say that again.",
    "busy": "Jarvis is busy - Live will start when it is free.",
    "idle": "Live went quiet, so the stream closed - press Live again.",
    "by_owner": "You ended it.",
}

#: Refusal reasons that are safe to say to the owner.
REFUSED = frozenset(WORDS)


class StreamRefused(Exception):
    """A request/route refusal with a plain sentence for the owner."""

    def __init__(self, why: str, *, status: int = 400):
        self.why = why if why in REFUSED else "bad_frame"
        self.status = status
        super().__init__(self.why)


# ------------------------------------------------------------------ varint ----

def put_varint(n: int) -> bytes:
    """The design's length prefix: a little, portable varint (LEB128)."""
    if n < 0:
        raise ValueError("length cannot be negative")
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def get_varint(raw: bytes, pos: int = 0) -> tuple:
    """(value, next_position). Refuses a prefix longer than five bytes."""
    value = 0
    shift = 0
    for i in range(5):
        if pos >= len(raw):
            raise ValueError("truncated varint")
        b = raw[pos]
        pos += 1
        value |= (b & 0x7F) << shift
        if not b & 0x80:
            return value, pos
        shift += 7
    raise ValueError("varint too long")


# --------------------------------------------------------------- handshake ----

def accept_key(client_key: str) -> str:
    """The `Sec-WebSocket-Accept` value for a client key (RFC 6455 §4.2.2)."""
    return base64.b64encode(
        hashlib.sha1((client_key + WS_GUID).encode("ascii")).digest()).decode("ascii")


def handshake_headers(headers) -> str:
    """Validate an upgrade request's headers and return the accept value.

    Raises `StreamRefused` with a plain reason; nothing is written here.
    """
    upgrade = str(headers.get("Upgrade") or "").strip().lower()
    connection = str(headers.get("Connection") or "").strip().lower()
    version = str(headers.get("Sec-WebSocket-Version") or "").strip()
    key = str(headers.get("Sec-WebSocket-Key") or "").strip()
    if upgrade != "websocket":
        raise StreamRefused("bad_frame")
    if "upgrade" not in [p.strip() for p in connection.split(",")]:
        raise StreamRefused("bad_frame")
    if version != "13":
        raise StreamRefused("bad_frame")
    try:
        raw_key = base64.b64decode(key.encode("ascii"), validate=True)
    except Exception:
        raise StreamRefused("bad_frame")
    if len(raw_key) != 16:
        raise StreamRefused("bad_frame")
    return accept_key(key)


def write_handshake(handler, accept: str) -> None:
    """Write the 101 response. Only called once the caller's auth passed."""
    body = ("HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {accept}\r\n\r\n").encode("ascii")
    handler.wfile.write(body)
    try:
        handler.wfile.flush()
    except Exception:
        pass


# ------------------------------------------------------------------ frames ----

def _recv_exact(sock, n: int, *, timeout: float) -> bytes:
    sock.settimeout(timeout)
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("socket closed")
        buf.extend(chunk)
    return bytes(buf)


def read_frame(sock, *, require_mask: bool = True, timeout: float = IDLE_TIMEOUT_S):
    """One WebSocket frame -> (opcode, payload).

    Server role: client frames MUST be masked and must not set RSV bits; a
    fragmented message is refused rather than half-reassembled (the design
    sends one frame per message). Sizes are capped before anything is read.
    """
    head = _recv_exact(sock, 2, timeout=timeout)
    b0, b1 = head[0], head[1]
    fin = bool(b0 & 0x80)
    rsv = b0 & 0x70
    opcode = b0 & 0x0F
    masked = bool(b1 & 0x80)
    length = b1 & 0x7F
    if rsv:
        raise StreamRefused("bad_frame")
    if not fin:
        raise StreamRefused("bad_frame")
    if masked != bool(require_mask):
        raise StreamRefused("bad_frame")
    if opcode not in (0x1, 0x2, 0x8, 0x9, 0xA):
        raise StreamRefused("bad_frame")
    if length == 126:
        length = struct.unpack(">H", _recv_exact(sock, 2, timeout=timeout))[0]
    elif length == 127:
        length = struct.unpack(">Q", _recv_exact(sock, 8, timeout=timeout))[0]
    cap = MAX_FRAME_BYTES
    if opcode in (0x1, 0x8, 0x9, 0xA):
        cap = MAX_CONTROL_BYTES
    if length > cap:
        raise StreamRefused("bad_frame")
    mask = _recv_exact(sock, 4, timeout=timeout) if masked else b""
    raw = bytearray(_recv_exact(sock, length, timeout=timeout))
    if masked:
        for i in range(length):
            raw[i] ^= mask[i % 4]
    return opcode, bytes(raw)


def write_frame(sock, opcode: int, payload: bytes) -> None:
    """One unmasked server->client frame (server frames are never masked)."""
    if not isinstance(payload, (bytes, bytearray)):
        payload = bytes(payload)
    if len(payload) > MAX_FRAME_BYTES:
        raise ValueError("payload too large")
    head = bytearray([0x80 | (opcode & 0x0F)])
    n = len(payload)
    if n < 126:
        head.append(n)
    elif n < 65536:
        head.extend([126])
        head.extend(struct.pack(">H", n))
    else:
        head.extend([127])
        head.extend(struct.pack(">Q", n))
    sock.sendall(bytes(head) + bytes(payload))


def write_json(sock, obj: dict) -> None:
    write_frame(sock, 0x1, json.dumps(obj, separators=(",", ":")).encode("utf-8"))


def close_stream(sock, code: int = 1000, why: str = "") -> None:
    try:
        write_frame(sock, 0x8, struct.pack(">H", int(code)) + why.encode("utf-8"))
    except Exception:
        pass


# ------------------------------------------------------------ audio frames ----

def audio_payload(epoch: int, seq: int, pcm: bytes) -> bytes:
    """The inner audio message: epoch byte + u32 BE sequence + PCM16 LE."""
    if not 1 <= int(epoch) <= 255:
        raise ValueError("epoch must be 1..255")
    if int(seq) < 0 or int(seq) > 0xFFFFFFFF:
        raise ValueError("sequence out of range")
    return bytes([int(epoch)]) + struct.pack(">I", int(seq)) + bytes(pcm)


def decode_audio_payload(payload: bytes) -> tuple:
    """(epoch, seq, pcm) from an inner audio message, with the varint prefix."""
    length, pos = get_varint(payload)
    if length != len(payload) - pos:
        raise StreamRefused("bad_frame")
    inner = payload[pos:]
    if len(inner) < 5:
        raise StreamRefused("bad_frame")
    epoch = inner[0]
    if not 1 <= epoch <= 255:
        raise StreamRefused("bad_frame")
    seq = struct.unpack(">I", inner[1:5])[0]
    pcm = inner[5:]
    if len(pcm) % 2:
        raise StreamRefused("bad_frame")
    return epoch, seq, pcm


def pcm_to_wav(pcm: bytes, *, rate: int = SAMPLE_RATE) -> bytes:
    """A complete mono 16-bit WAV of the ring, for the one-shot speech path."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(pcm))
    return buf.getvalue()


class StreamState:
    """One open stream: epoch, sequence, and the 2 s RAM ring."""

    def __init__(self, *, epoch: int | None = None, ring_bytes: int = RING_BYTES):
        self.epoch = epoch if epoch is not None else random.SystemRandom().randint(1, 255)
        self.last_seq = -1
        self.ring = bytearray()
        self.ring_bytes = int(ring_bytes)
        self.turn_bytes = 0
        self.hello = False
        self.ended = False

    def reset_ring(self) -> None:
        self.ring.clear()
        self.turn_bytes = 0

    def accept_audio(self, payload: bytes) -> None:
        epoch, seq, pcm = decode_audio_payload(payload)
        if epoch != self.epoch:
            # A frame from a dead epoch is refused for the life of the stream.
            raise StreamRefused("bad_frame")
        if seq <= self.last_seq:
            raise StreamRefused("bad_frame")
        self.last_seq = seq
        self.ring.extend(pcm)
        self.turn_bytes += len(pcm)
        if self.turn_bytes > MAX_TURN_SECONDS * SAMPLE_RATE * 2:
            raise StreamRefused("dropped")
        over = len(self.ring) - self.ring_bytes
        if over > 0:
            del self.ring[:over]

    def wav(self) -> bytes:
        return pcm_to_wav(bytes(self.ring))

    def end_turn(self) -> bytes:
        wav = self.wav()
        self.reset_ring()
        return wav


# --------------------------------------------------------------- the serve ----

def _plain_refusal(sock, why: str, code: int = 1008) -> None:
    try:
        write_json(sock, {"t": "bye", "why": WORDS[why] if why in WORDS else WORDS["bad_frame"]})
    except Exception:
        pass
    close_stream(sock, code)


def serve(handler, *, engine=None, sink=None,
          idle_timeout: float = IDLE_TIMEOUT_S) -> bool:
    """Serve one upgraded Live stream. Returns True when it was served.

    The caller (`jarvis_live.install`) has ALREADY checked origin + token and
    ALREADY decided the switch is on. Nothing here reads a frame before the
    handshake, and nothing is written anywhere except the socket.

    `engine` is the live session engine (duck-typed: `accepts(device)` and
    `status()`); `sink(wav_bytes, ctx) -> dict` performs one turn and is
    injected so this transport can be tested without speech models. `ctx`
    carries the request facts the turn needs - the token the stream arrived
    with (for the PC's own loopback chat call), this server's port and the
    device name - and is never logged. `sink=None` refuses every turn in plain
    words."""
    try:
        accept = handshake_headers(handler.headers)
    except StreamRefused as exc:
        try:
            handler.send_response(exc.status)
            handler.send_header("Content-Length", "0")
            handler.end_headers()
        except Exception:
            pass
        return False
    write_handshake(handler, accept)
    sock = handler.connection
    state = StreamState()
    device = ""
    token = str(handler.headers.get("X-Jarvis-Token") or "")
    try:
        port = int((handler.server.server_address or (None, 0))[1])
    except Exception:
        port = 0
    try:
        sock.settimeout(idle_timeout)
        while not state.ended:
            try:
                opcode, payload = read_frame(sock, timeout=idle_timeout)
            except socket.timeout:
                _plain_refusal(sock, "idle")
                break
            except (ConnectionError, OSError):
                break
            except StreamRefused as exc:
                _plain_refusal(sock, exc.why, code=1002)
                break
            if opcode == 0x8:            # close
                try:
                    close_stream(sock, 1000)
                except Exception:
                    pass
                break
            if opcode == 0x9:            # ping -> pong
                try:
                    write_frame(sock, 0xA, payload)
                except Exception:
                    break
                continue
            if opcode == 0xA:            # pong: heartbeat answered
                continue
            if opcode == 0x1:            # text control
                try:
                    msg = json.loads(payload.decode("utf-8"))
                except Exception:
                    _plain_refusal(sock, "bad_frame")
                    break
                if not isinstance(msg, dict):
                    _plain_refusal(sock, "bad_frame")
                    break
                kind = str(msg.get("t") or "")
                if not state.hello:
                    if kind != "hello":
                        _plain_refusal(sock, "bad_hello")
                        break
                    device = str(msg.get("device") or "").strip()[:64]
                    if engine is not None and hasattr(engine, "accepts"):
                        try:
                            out = engine.accepts(device) or {}
                        except Exception:
                            out = {}
                        if not out.get("ok", False):
                            why = "no_session" if out.get("why") in (
                                "off", "not_started", "unknown", None) else "busy"
                            _plain_refusal(sock, why)
                            break
                    state.hello = True
                    write_json(sock, {"t": "ready", "epoch": state.epoch,
                                      "frame_ms": 64, "rate": SAMPLE_RATE})
                    continue
                if kind == "end_turn":
                    if sink is None:
                        _plain_refusal(sock, "not_built")
                        break
                    wav = state.end_turn()
                    try:
                        out = sink(wav, {"token": token, "port": port,
                                         "device": device}) or {}
                    except StreamRefused as exc:
                        write_json(sock, {"t": "refused", "why": WORDS[exc.why]})
                        continue
                    except Exception:
                        write_json(sock, {"t": "refused", "why": WORDS["not_built"]})
                        continue
                    if not out.get("ok", True):
                        write_json(sock, {"t": "refused",
                                          "why": str(out.get("why") or WORDS["busy"])})
                        continue
                    write_json(sock, {"t": "turn_started"})
                    seq = 0
                    for chunk in (out.get("speech") or []):
                        if not chunk:
                            continue
                        write_json(sock, {"t": "speech_start", "seq": seq})
                        write_frame(sock, 0x2, put_varint(len(chunk)) + chunk)
                        write_json(sock, {"t": "speech_end", "seq": seq})
                        seq += 1
                    if out.get("not_owner"):
                        write_json(sock, {"t": "not_owner", "why": WORDS["not_owner"]})
                    continue
                if kind == "cancel":
                    state.reset_ring()
                    write_json(sock, {"t": "dropped", "why": WORDS["dropped"]})
                    continue
                if kind == "mute":
                    continue
                if kind == "bye":
                    state.ended = True
                    write_json(sock, {"t": "bye", "why": WORDS["by_owner"]})
                    close_stream(sock, 1000, "bye")
                    break
                _plain_refusal(sock, "bad_frame")
                break
            if opcode == 0x2:            # audio
                if not state.hello:
                    _plain_refusal(sock, "bad_hello")
                    break
                try:
                    state.accept_audio(payload)
                except StreamRefused as exc:
                    if exc.why == "dropped":
                        state.reset_ring()
                        write_json(sock, {"t": "dropped", "why": WORDS["dropped"]})
                        continue
                    _plain_refusal(sock, exc.why, code=1002)
                    break
    finally:
        try:
            handler.close_connection = True
        except Exception:
            pass
    return True
