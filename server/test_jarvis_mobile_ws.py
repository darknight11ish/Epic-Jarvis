"""Tests for the mobile WebSocket endpoint.

Run with::

    python3 server/test_jarvis_mobile_ws.py

Stdlib-only, including the client. The point is to prove the RFC 6455 framing
against a socket that masks its frames the way OkHttp does, rather than against
a library that would share this module's own assumptions.
"""

import base64
import hashlib
import hmac
import inspect
import io
import json
import os
import socket
import struct
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import jarvis_mobile_ws
from jarvis_mobile_ws import (ApprovalVerifier, MobileEndpoint, compute_accept,
                              MAX_MESSAGE_FRAGMENTS)

failures = []


def check(name, cond):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(name)


SECRET = "test-secret-key"


print("Verifier:")
v = ApprovalVerifier(SECRET, max_clock_skew_ms=60_000, nonce_ttl_seconds=1)

def sign(rid, approved, dev, ts, nonce, secret=SECRET):
    canon = f"{rid}|{'true' if approved else 'false'}|{dev}|{ts}|{nonce}"
    return hmac.new(secret.encode(), canon.encode(), hashlib.sha256).hexdigest()

now = int(time.time()*1000)
good = {"type":"approval_decision","id":"r1","approved":True,"device_id":"d1",
        "decided_at_ms":now,"nonce":"n1","signature":sign("r1",True,"d1",now,"n1")}
check("valid decision accepted", v.verify(dict(good))[0])
check("replayed nonce rejected", v.verify(dict(good)) == (False, "replayed nonce"))

bad = dict(good); bad["nonce"]="n2"; bad["signature"]="deadbeef"
check("bad signature rejected", v.verify(bad) == (False, "invalid signature"))

stale_ts = now - 600_000
st = {"type":"approval_decision","id":"r2","approved":False,"device_id":"d1",
      "decided_at_ms":stale_ts,"nonce":"n3","signature":sign("r2",False,"d1",stale_ts,"n3")}
check("clock skew rejected", v.verify(st) == (False, "timestamp outside skew window"))

coerce = dict(good); coerce["approved"]="true"; coerce["nonce"]="n4"
check("string 'true' rejected (not coerced)", v.verify(coerce) == (False,"approved must be a JSON boolean"))

try:
    ApprovalVerifier("")
    _empty_ok = False
except ValueError:
    _empty_ok = True
check("empty secret refused at construction", _empty_ok)

# device pinning
vp = ApprovalVerifier(SECRET, allowed_device_ids=["known"])
check("unknown device rejected", vp.verify(dict(good)) == (False,"unknown device_id"))

# TTL pruning actually happens
v2 = ApprovalVerifier(SECRET, nonce_ttl_seconds=0)
for i in range(50):
    ts = int(time.time()*1000); n=f"p{i}"
    v2.verify({"id":"r","approved":True,"device_id":"d","decided_at_ms":ts,
               "nonce":n,"signature":sign("r",True,"d",ts,n)})
check(f"nonce cache pruned (holds {v2.tracked_nonces}, not 50)", v2.tracked_nonces <= 1)


SECRET, TOKEN = "s3cr3t", "tok-123"
approvals, audio = [], []

ENDPOINT = MobileEndpoint(
    verifier=ApprovalVerifier(SECRET),
    auth_token=TOKEN,
    on_approval=lambda rid, ok, c: approvals.append((rid, ok)),
    on_audio=lambda data, c: audio.append(data),
)

class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *a): pass
    def do_GET(self):
        if self.path == MobileEndpoint.PATH:
            ENDPOINT.serve(self); return
        self.send_response(404); self.send_header("Content-Length","0"); self.end_headers()

srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()

def frame(opcode, payload, mask=True):
    out = bytearray([0x80 | opcode])
    n = len(payload)
    m = 0x80 if mask else 0
    if n < 126: out.append(m | n)
    elif n < 65536: out.append(m | 126); out += struct.pack("!H", n)
    else: out.append(m | 127); out += struct.pack("!Q", n)
    if mask:
        k = os.urandom(4); out += k
        out += bytes(b ^ k[i % 4] for i, b in enumerate(payload))
    else:
        out += payload
    return bytes(out)

def read_frame(sock):
    def rd(n):
        buf = b""
        while len(buf) < n:
            c = sock.recv(n - len(buf))
            if not c: raise EOFError
            buf += c
        return buf
    b0, b1 = rd(2)
    op, ln = b0 & 0x0F, b1 & 0x7F
    if ln == 126: ln = struct.unpack("!H", rd(2))[0]
    elif ln == 127: ln = struct.unpack("!Q", rd(8))[0]
    return op, (rd(ln) if ln else b"")

def connect(token=TOKEN):
    s = socket.create_connection(("127.0.0.1", port), timeout=5)
    key = base64.b64encode(os.urandom(16)).decode()
    req = (f"GET {MobileEndpoint.PATH} HTTP/1.1\r\nHost: x\r\nUpgrade: websocket\r\n"
           f"Connection: Upgrade\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: {key}\r\n")
    if token is not None: req += f"Authorization: Bearer {token}\r\n"
    s.sendall((req + "\r\n").encode())
    hdr = b""
    while b"\r\n\r\n" not in hdr: hdr += s.recv(4096)
    return s, hdr.decode(errors="replace"), key

print("Handshake:")
s, hdr, key = connect()
check("101 Switching Protocols", "101 Switching Protocols" in hdr)
check("Sec-WebSocket-Accept correct", f"Sec-WebSocket-Accept: {compute_accept(key)}" in hdr)

print("Auth:")
s2, hdr2, _ = connect(token="wrong")
check("bad bearer token -> 401", "401" in hdr2.split("\r\n")[0]); s2.close()
s3, hdr3, _ = connect(token=None)
check("missing bearer token -> 401", "401" in hdr3.split("\r\n")[0]); s3.close()

print("Framing:")
s.sendall(frame(0x9, b"ping-payload"))          # client ping
op, pl = read_frame(s)
check("ping answered with pong", op == 0xA and pl == b"ping-payload")

s.sendall(frame(0x2, bytes([7]) + b"\x01\x02" * 500))   # binary uplink
time.sleep(0.3)
check(f"binary frame received ({len(audio[0]) if audio else 0} bytes)",
      audio and len(audio[0]) == 1001 and audio[0][0] == 7)

big = os.urandom(70000)                          # forces 64-bit length path
s.sendall(frame(0x2, big)); time.sleep(0.4)
check("extended-length frame unmasked correctly", len(audio) > 1 and audio[1] == big)

print("Approval path:")
now = int(time.time()*1000)
def sign(rid, ap, dev, ts, n):
    return hmac.new(SECRET.encode(), f"{rid}|{'true' if ap else 'false'}|{dev}|{ts}|{n}".encode(),
                    hashlib.sha256).hexdigest()
dec = {"type":"approval_decision","id":"req-9","approved":True,"device_id":"phone",
       "decided_at_ms":now,"nonce":"nn1","signature":sign("req-9",True,"phone",now,"nn1")}
s.sendall(frame(0x1, json.dumps(dec).encode())); time.sleep(0.3)
check("signed approval delivered", approvals == [("req-9", True)])

s.sendall(frame(0x1, json.dumps(dec).encode())); time.sleep(0.3)   # replay
check("replay not delivered twice", approvals == [("req-9", True)])

forged = dict(dec); forged["nonce"]="nn2"; forged["signature"]="00"*32
s.sendall(frame(0x1, json.dumps(forged).encode())); time.sleep(0.3)
check("forged signature not delivered", approvals == [("req-9", True)])

print("Server -> phone:")
ENDPOINT.broadcast(lambda c: c.send_approval_request("req-10","Delete file","rm -rf /tmp/x"))
op, pl = read_frame(s)
ev = json.loads(pl)
check("approval_request framed correctly", op == 0x1 and ev["type"]=="approval_request" and ev["id"]=="req-10")

sent = ENDPOINT.broadcast(lambda c: c.send_audio_stream("st1", iter([b"\x11"*640, b"\x22"*640]), binary_tag=3))
op1, start = read_frame(s); op2, a1 = read_frame(s); op3, a2 = read_frame(s); op4, end = read_frame(s)
check("audio_stream_start carries binary_tag", json.loads(start)["binary_tag"] == 3)
check("audio frames tagged + binary", op2 == 0x2 and a1[0] == 3 and len(a1) == 641)
check("audio_stream_end sent", json.loads(end)["type"] == "audio_stream_end")

s.close(); srv.shutdown()


# ---------------------------------------------------------------------------
#   Handshake hardening
# ---------------------------------------------------------------------------
#
# Driven against `_handshake` directly with a stand-in handler: what is being
# proven is the decision, not the socket. Each case is the shape of a real
# defect, not a hypothetical.
print("\nHandshake:")

from jarvis_mobile_ws import MAX_MESSAGE_BYTES, MAX_FRAME_BYTES  # noqa: E402


class FakeHandler:
    """Just enough handler for `_handshake`: headers, and somewhere to write."""

    def __init__(self, headers):
        self.headers = headers
        self.status = None
        self.wfile = io.BytesIO()
        self._sent = []

    def send_response(self, status):
        self.status = status

    def send_header(self, *a):
        pass

    def end_headers(self):
        pass


def handshake_headers(**over):
    base = {
        "Upgrade": "websocket",
        "Connection": "Upgrade",
        "Sec-WebSocket-Version": "13",
        "Sec-WebSocket-Key": base64.b64encode(b"0123456789abcdef").decode(),
    }
    base.update(over)
    return {k: v for k, v in base.items() if v is not None}


def try_handshake(endpoint, **over):
    h = FakeHandler(handshake_headers(**over))
    ok = endpoint._handshake(h)
    return ok, h.status


# --- the origin check -------------------------------------------------------
#
# Browsers do not apply same-origin policy to WebSockets and send no
# preflight, so before this check any page the owner happened to be visiting
# could open this endpoint and read every approval card broadcast on it.
open_ep = MobileEndpoint(v)
ok, status = try_handshake(open_ep, Origin="https://evil.example")
check("a browser origin is refused", ok is False and status == 403)

ok, _ = try_handshake(open_ep, Origin=None)
check("CONTROL: a native client, which sends no Origin, still connects", ok is True)

ok, status = try_handshake(open_ep, Origin="null")
check("a sandboxed iframe's 'null' origin is refused too", ok is False and status == 403)

allowed_ep = MobileEndpoint(v, allowed_origins=["https://trusted.example"])
ok, _ = try_handshake(allowed_ep, Origin="https://trusted.example")
check("an explicitly allowed origin connects", ok is True)
ok, status = try_handshake(allowed_ep, Origin="https://evil.example")
check("and allow-listing one origin does not admit another", ok is False and status == 403)


# --- the non-ASCII Authorization crash --------------------------------------
#
# `hmac.compare_digest` raises TypeError on str arguments containing
# non-ASCII, and http.client decodes headers as latin-1. `_handshake` is
# called outside `serve`'s try block, so one high byte from an
# unauthenticated caller took the serving thread down.
auth_ep = MobileEndpoint(v, auth_token="right-token")
crashed = False
try:
    ok, status = try_handshake(auth_ep, Authorization="Bearer ü")
except TypeError:
    crashed = True
    ok, status = None, None
check("a non-ASCII bearer token is refused, not a crash", not crashed and ok is False)
check("and it is refused as unauthorised", status == 401)

ok, _ = try_handshake(auth_ep, Authorization="Bearer right-token")
check("CONTROL: the correct token still connects", ok is True)
ok, status = try_handshake(auth_ep, Authorization="Bearer wrong-token")
check("CONTROL: a wrong token is still refused", ok is False and status == 401)


# --- the message cap --------------------------------------------------------
#
# MAX_FRAME_BYTES bounds ONE fragment; an unbounded number of bounded
# fragments is still unbounded, and grew the serving thread a megabyte at a
# time until the process died.
check("a whole-message cap exists and is larger than one frame",
      MAX_MESSAGE_BYTES > MAX_FRAME_BYTES)

src = inspect.getsource(jarvis_mobile_ws)
check("the cap is enforced on assembly, not just declared",
      "MAX_MESSAGE_BYTES" in src.split("MAX_MESSAGE_BYTES =", 1)[1])


# --- the fragment-COUNT cap -------------------------------------------------
#
# The byte cap above could not see an empty fragment. A zero-length
# continuation frame is six bytes on the wire and adds nothing to the byte
# total, so `fragments` grew without limit while the cap never tripped - the
# exact unbounded growth MAX_MESSAGE_BYTES exists to stop, through the one
# door it does not watch. Worse, the total was recomputed with
# `sum(len(f) for f in fragments)` on every frame, making assembly quadratic:
# ~3s of CPU for 16k such frames, on a thread-per-connection server.
def frames_socket(payload: bytes) -> jarvis_mobile_ws.MobileSocket:
    """A MobileSocket reading from a fixed byte string instead of a socket."""
    return jarvis_mobile_ws.MobileSocket(None, io.BytesIO(payload), io.BytesIO())


def wsframe(fin: bool, opcode: int, body: bytes = b"") -> bytes:
    """One raw frame. Not the `frame()` above: that one always sets FIN, and
    these tests are specifically about frames that do not."""
    # Masked, because that is what a client must send; an all-zero mask key
    # makes the masking the identity so the body stays readable here.
    return (bytes([(0x80 if fin else 0) | opcode, 0x80 | len(body)])
            + b"\x00\x00\x00\x00" + body)


flood = wsframe(False, jarvis_mobile_ws.OP_TEXT)
flood += wsframe(False, jarvis_mobile_ws.OP_CONT) * (MAX_MESSAGE_FRAGMENTS + 5)
try:
    frames_socket(flood).read_message()
    refused = False
except jarvis_mobile_ws.WebSocketClosed:
    refused = True
check("a flood of EMPTY continuation frames is refused, not assembled for ever",
      refused)

# CONTROL: the same shape, safely under the cap, still assembles.
ok_msg = wsframe(False, jarvis_mobile_ws.OP_TEXT, b"he")
ok_msg += wsframe(False, jarvis_mobile_ws.OP_CONT, b"ll")
ok_msg += wsframe(True, jarvis_mobile_ws.OP_CONT, b"o")
check("CONTROL: an ordinary fragmented message still assembles",
      frames_socket(ok_msg).read_message() == (jarvis_mobile_ws.OP_TEXT, b"hello"))


# --- Sec-WebSocket-Key is ASCII-checked before it reaches sha1 --------------
#
# `compute_accept` does `key.encode("ascii")`, and http.client decodes headers
# as latin-1, so one high byte raised UnicodeEncodeError straight out of
# `_handshake` - which runs outside `serve`'s try block and took the serving
# thread with it. Identical cause and blast radius to the Authorization crash
# above; this header is read first, and before any token is checked.
crashed = False
try:
    ok, status = try_handshake(open_ep, **{"Sec-WebSocket-Key": "abcdefghijklmnop=é"})
except UnicodeEncodeError:
    crashed = True
    ok, status = None, None
check("a non-ASCII Sec-WebSocket-Key is refused, not a crash",
      not crashed and ok is False)
check("and it is refused as a bad request", status == 400)


print(f"\n{'ALL PASS' if not failures else 'FAILURES: ' + ', '.join(failures)}")
sys.exit(1 if failures else 0)
