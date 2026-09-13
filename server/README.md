# Desktop endpoint for Jarvis Mobile

`jarvis_mobile_ws.py` is a stdlib-only WebSocket endpoint for the Android
client. Drop it next to your desktop server and import it — there is nothing to
install.

## Why it hand-rolls the framing

`BaseHTTPRequestHandler` cannot speak WebSocket. The alternatives were to move
the server to `aiohttp` or to open a second listener on another port, and both
change more than this needs to. Instead the module hijacks the connection after
writing the 101 response and implements RFC 6455 framing directly, so the
endpoint stays on port 4719 where the phone already dials it.

## Wiring it in

```python
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from jarvis_mobile_ws import ApprovalVerifier, MobileEndpoint

PENDING = {}          # request_id -> your gate object

ENDPOINT = MobileEndpoint(
    verifier=ApprovalVerifier(
        secret=os.environ["JARVIS_SHARED_SECRET"],
        allowed_device_ids=[os.environ["JARVIS_DEVICE_ID"]],   # optional but advised
    ),
    auth_token=os.environ.get("JARVIS_AUTH_TOKEN"),
    on_approval=lambda request_id, approved, client: PENDING.pop(request_id).resolve(approved),
    on_audio=lambda pcm, client: transcriber.feed(pcm),        # 16kHz 16-bit mono
    is_pending=lambda request_id: request_id in PENDING,
)

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        if self.path == MobileEndpoint.PATH:
            ENDPOINT.serve(self)      # blocks for the life of the socket
            return
        ...   # your existing routes

ThreadingHTTPServer(("0.0.0.0", 4719), Handler).serve_forever()
```

`ThreadingHTTPServer` is required: `serve()` blocks its thread until the phone
disconnects.

## Pushing to the phone

```python
ENDPOINT.broadcast(lambda c: c.send_approval_request(
    "req-1", "Delete 12 files", "rm -rf ~/scratch", tier="ask",
))
ENDPOINT.broadcast(lambda c: c.send_desktop_telemetry(
    cpu_percent=41.2, gpu_temp_c=68.0, vram_used_mb=9100, vram_total_mb=24576,
))
ENDPOINT.broadcast(lambda c: c.send_audio_stream("tts-1", pcm_chunks, sample_rate=22050))
```

`send_audio_stream` uses tagged binary frames rather than base64, avoiding a 33%
payload inflation and a JSON parse per 20ms of speech.

## Generating the pairing secret

```python
from jarvis_mobile_ws import generate_shared_secret
print(generate_shared_secret())
```

Paste the value into the phone's **Pairing → Signing secret** field and export
the same value as `JARVIS_SHARED_SECRET`. Without it the phone refuses to send
decisions and `ApprovalVerifier` refuses to construct — both ends fail closed.

## What the verifier enforces

Signature first, so unauthenticated input never reaches the replay cache:

1. Field types, including `approved` as a real JSON boolean — a `"true"` string
   is rejected rather than coerced.
2. `device_id` against the allowlist, when one is configured.
3. HMAC-SHA256 over `{id}|{approved}|{device_id}|{decided_at_ms}|{nonce}`,
   compared in constant time.
4. `decided_at_ms` within the skew window (60s default).
5. The request is still pending, via your `is_pending` callback.
6. The nonce is unseen, claimed atomically under a lock. The cache prunes on the
   same path that fills it, so it cannot grow without bound.

## Tests

```
python3 server/test_jarvis_mobile_ws.py
```

Covers the verifier and drives a real handshake, masked client frames,
ping/pong, 64-bit length frames, replay and forgery rejection, and the
server-to-phone senders over a raw socket.
