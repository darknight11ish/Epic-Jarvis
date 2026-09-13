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
import json
import os
import socket
import struct
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from jarvis_mobile_ws import ApprovalVerifier, MobileEndpoint, compute_accept

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
print(f"\n{'ALL PASS' if not failures else 'FAILURES: ' + ', '.join(failures)}")
sys.exit(1 if failures else 0)
