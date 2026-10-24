"""test_live_stream.py - the PC transport for the phone's persistent Live
stream (Slice G, G2 of `docs/DESIGN-PHONE-LIVE-STREAM.md`).

    python3 backend/test_live_stream.py

What this proves, with a REAL loopback HTTP server and a REAL `socket` client -
no phone, no microphone, no model, no network beyond 127.0.0.1:

  1. THE SWITCH IS THE GATE: while `[live] stream` is OFF the frozen 501 stub
     still answers and an upgrade request is refused; while it is ON and the
     token is missing, the handshake is refused 401 BEFORE any frame is read.
  2. THE HANDSHAKE: a token-carrying RFC 6455 upgrade gets 101 with the correct
     `Sec-WebSocket-Accept`; a request without the upgrade headers gets 400.
  3. THE WIRE: `hello` (session gate) -> `ready` with a random epoch byte;
     binary audio frames carry `<varint length> | epoch | u32 sequence | PCM`;
     `end_turn` hands ONE complete WAV to the injected sink and streams the
     answer back as control messages plus PCM frames; `bye` ends it cleanly.
  4. THE REFUSALS: a replayed sequence, a stale epoch, an unmasked client
     frame, an oversized frame, control-before-hello, a session the engine does
     not accept, and a sink that is not wired yet - each gets a plain-English
     sentence and a close, never silence and never a half turn.
  5. THE BOUNDS: the ring is capped and a WAV is built only from RAM; no file
     is written anywhere by this module (a source check bites if one appears).

No network, no model, no microphone. The speech sink is a stand-in that records
the WAV it was handed and returns fixed text/speech - the real `hear()` wiring
is the next slice and is NOT claimed here.
"""
from __future__ import annotations

import base64
import json
import os
import socket
import struct
import sys
import threading
import traceback
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "rebuilt"))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
from _where import REPO, SHIPPED, require_shipped  # noqa: E402

require_shipped("jarvis_live.py")

_TMP = Path(os.environ.get("TEMP") or ".") / "jarvis-live-stream-test"
if "jarvis_framework" not in sys.modules:
    fw = types.ModuleType("jarvis_framework")
    fw.CONFIG_DIR = _TMP
    fw.LOG_DIR = _TMP
    fw.load_framework = lambda: {}
    fw.audit_log = lambda event, detail=None, **k: None
    fw.action_tier = lambda action: "ask"
    sys.modules["jarvis_framework"] = fw

import jarvis_live as L  # noqa: E402
import jarvis_live_stream as S  # noqa: E402

TOKEN = "stream-test-token"
PASSED, FAILED = [], []
SKIPPED = []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    SKIPPED.append(why)
    print(f"SKIP {why}")


# --------------------------------------------------------------- harness ----

class FakeEngine:
    def __init__(self, ok=True):
        self.ok = ok
        self.seen = []

    def accepts(self, device):
        self.seen.append(device)
        return {"ok": self.ok, "why": "on" if self.ok else "off"}


class _Base(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._send(404, {"error": "not here"})

    def do_POST(self):
        self._send(404, {"error": "not here"})


class Server:
    """A real ThreadingHTTPServer with the Live wrapper installed on a fresh
    handler class, so several servers in one process cannot double-wrap."""

    def __init__(self, *, switch=True, engine=None, sink="unset"):
        cls = type("H", (_Base,), {})
        L.install(cls, origin_ok=lambda h: True,
                  token_ok=lambda h: h.headers.get("X-Jarvis-Token") == TOKEN,
                  read_body=lambda h: b"{}")
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), cls)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self._old = (L.stream_enabled, L.ENGINE, L._STREAM_SINK)
        L.stream_enabled = (lambda: True) if switch else (lambda: False)
        L.ENGINE = engine if engine is not None else FakeEngine()
        L._STREAM_SINK = None if sink == "none" else (sink if sink != "unset" else None)
        self.thread.start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        L.stream_enabled, L.ENGINE, L._STREAM_SINK = self._old


def _read_until_headers(s):
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = s.recv(1)
        if not chunk:
            break
        buf += chunk
    return buf


def ws_connect(port, *, token=TOKEN, upgrade=True, extra=""):
    s = socket.create_connection(("127.0.0.1", port), timeout=5)
    key = base64.b64encode(os.urandom(16)).decode()
    lines = ["GET /api/live/stream HTTP/1.1", f"Host: 127.0.0.1:{port}"]
    if upgrade:
        lines += ["Upgrade: websocket", "Connection: Upgrade",
                  f"Sec-WebSocket-Key: {key}", "Sec-WebSocket-Version: 13"]
    lines += ["X-Jarvis-Client: hud"]
    if token:
        lines.append(f"X-Jarvis-Token: {token}")
    req = "\r\n".join(lines) + "\r\n" + extra + "\r\n"
    s.sendall(req.encode("ascii"))
    head = _read_until_headers(s)
    return s, head, key


def _mask(payload: bytes, mask=b"\x11\x22\x33\x44") -> bytes:
    return bytes(b ^ mask[i % 4] for i, b in enumerate(payload))


def send_frame(s, opcode, payload=b"", *, mask_it=True):
    payload = bytes(payload)
    head = bytearray([0x80 | (opcode & 0x0F)])
    n = len(payload)
    flag = 0x80 if mask_it else 0
    if n < 126:
        head.append(flag | n)
    elif n < 65536:
        head.append(flag | 126)
        head.extend(struct.pack(">H", n))
    else:
        head.append(flag | 127)
        head.extend(struct.pack(">Q", n))
    if mask_it:
        head.extend(b"\x11\x22\x33\x44")
        payload = _mask(payload)
    s.sendall(bytes(head) + payload)


def send_json(s, obj):
    send_frame(s, 0x1, json.dumps(obj).encode("utf-8"))


def _recv_exact(s, n):
    buf = b""
    while len(buf) < n:
        chunk = s.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("closed")
        buf += chunk
    return buf


def recv_frame(s):
    b0, b1 = _recv_exact(s, 2)
    opcode = b0 & 0x0F
    n = b1 & 0x7F
    if n == 126:
        n = struct.unpack(">H", _recv_exact(s, 2))[0]
    elif n == 127:
        n = struct.unpack(">Q", _recv_exact(s, 8))[0]
    payload = _recv_exact(s, n)
    return opcode, payload


def recv_json(s):
    op, payload = recv_frame(s)
    if op != 0x1:
        raise AssertionError(f"expected a text control message, got opcode {op}")
    return json.loads(payload.decode("utf-8"))


def hello(s, device="phone"):
    send_json(s, {"t": "hello", "device": device, "live_id": "stream-test"})
    return recv_json(s)


def audio(s, epoch, seq, pcm_len=2048, byte=0x00):
    inner = S.audio_payload(epoch, seq, bytes([byte]) * pcm_len)
    send_frame(s, 0x2, S.put_varint(len(inner)) + inner)


class Sink:
    def __init__(self, *, speech=((b"\x01\x00" * 1024),), ok=True):
        self.wavs = []
        self.speech = speech
        self.ok = ok

    def __call__(self, wav: bytes):
        self.wavs.append(wav)
        if not self.ok:
            return {"ok": False, "why": L.STREAM_NOT_BUILT_REASON}
        return {"ok": True, "speech": list(self.speech)}


# ---------------------------------------------------------------- checks ----

def t_switch_off_keeps_the_frozen_stub_and_refuses_the_upgrade():
    srv = Server(switch=False)
    try:
        s, head, _ = ws_connect(srv.port)
        check("switch OFF: an upgrade request gets the frozen 501, not 101",
              head.startswith(b"HTTP/1.1 501"), head[:50])
        body = b""
        try:
            body = s.recv(4096)
        except Exception:
            pass
        check("switch OFF: the 501 body says the stream is off",
              b'"stream": "off"' in body or b'"stream":"off"' in body, body[:200])
        s.close()
    finally:
        srv.close()


def t_missing_token_is_refused_before_any_frame():
    srv = Server(switch=True)
    try:
        s, head, _ = ws_connect(srv.port, token=None)
        check("switch ON, no token: 401, never 101",
              head.startswith(b"HTTP/1.1 401"), head[:50])
        s.close()
    finally:
        srv.close()


def t_bad_upgrade_headers_get_400():
    srv = Server(switch=True)
    try:
        s, head, _ = ws_connect(srv.port, upgrade=False)
        check("switch ON, token but no upgrade headers: 400",
              head.startswith(b"HTTP/1.1 400"), head[:50])
        s.close()
    finally:
        srv.close()


def t_handshake_ready_and_one_turn_end_to_end():
    sink = Sink(speech=(b"\x02\x00" * 1024,))
    engine = FakeEngine()
    srv = Server(switch=True, engine=engine, sink=sink)
    try:
        s, head, key = ws_connect(srv.port)
        check("the upgrade is accepted with the RFC 6455 accept key",
              head.startswith(b"HTTP/1.1 101")
              and S.accept_key(key).encode() in head, head[:120])
        ready = hello(s)
        check("hello answers ready with a random epoch byte and the frame shape",
              ready.get("t") == "ready" and 1 <= int(ready.get("epoch", 0)) <= 255
              and ready.get("frame_ms") == 64 and ready.get("rate") == S.SAMPLE_RATE,
              ready)
        check("the session gate saw the device name", engine.seen == ["phone"], engine.seen)
        epoch = int(ready["epoch"])
        for seq in (1, 2, 3):
            audio(s, epoch, seq, byte=seq)
        send_json(s, {"t": "end_turn"})
        msg = recv_json(s)
        check("end_turn starts a turn", msg.get("t") == "turn_started", msg)
        check("the sink received ONE complete WAV of the ring",
              len(sink.wavs) == 1 and sink.wavs[0].startswith(b"RIFF")
              and sink.wavs[0][8:12] == b"WAVE", sink.wavs[:1])
        start = recv_json(s)
        op, payload = recv_frame(s)
        end = recv_json(s)
        check("the answer streams speech_start / binary PCM / speech_end",
              start.get("t") == "speech_start" and op == 0x2
              and payload.startswith(b"\x00") is False
              and decode_speech(payload) == b"\x02\x00" * 1024
              and end.get("t") == "speech_end", (start, op, len(payload), end))
        send_json(s, {"t": "bye"})
        bye = recv_json(s)
        check("bye ends the stream in plain words",
              bye.get("t") == "bye" and "You ended it" in str(bye.get("why")), bye)
        s.close()
    finally:
        srv.close()


def decode_speech(payload: bytes) -> bytes:
    n, pos = S.get_varint(payload)
    return payload[pos:pos + n]


def t_replayed_sequence_and_stale_epoch_are_refused():
    srv = Server(switch=True, sink=Sink())
    try:
        s, _, _ = ws_connect(srv.port)
        epoch = int(hello(s)["epoch"])
        audio(s, epoch, 7)
        audio(s, epoch, 7)                       # replay the same sequence
        bye = recv_json(s)
        check("a replayed audio sequence is refused in plain words",
              bye.get("t") == "bye" and "could not read" in str(bye.get("why")), bye)
        s.close()

        s, _, _ = ws_connect(srv.port)
        epoch = int(hello(s)["epoch"])
        audio(s, (epoch % 255) + 1, 1)           # a different epoch
        bye = recv_json(s)
        check("a frame from a stale epoch is refused in plain words",
              bye.get("t") == "bye" and "could not read" in str(bye.get("why")), bye)
        s.close()
    finally:
        srv.close()


def t_unmasked_and_oversized_frames_are_refused():
    srv = Server(switch=True, sink=Sink())
    try:
        s, _, _ = ws_connect(srv.port)
        epoch = int(hello(s)["epoch"])
        payload = S.put_varint(5) + S.audio_payload(epoch, 1, b"\x00\x00")
        send_frame(s, 0x2, payload, mask_it=False)
        bye = recv_json(s)
        check("an unmasked client frame is refused",
              bye.get("t") == "bye", bye)
        s.close()

        s, _, _ = ws_connect(srv.port)
        hello(s)
        send_frame(s, 0x2, bytes(70000))         # over the 64 KiB cap
        try:
            bye = recv_json(s)
            refused = bye.get("t") == "bye"
        except Exception:
            refused = True                       # server closed before the body
        check("an oversized frame is refused before it is read", refused)
        s.close()
    finally:
        srv.close()


def t_control_before_hello_and_bad_session_are_refused():
    srv = Server(switch=True, sink=Sink())
    try:
        s, _, _ = ws_connect(srv.port)
        audio(s, 1, 1)                           # audio before hello
        bye = recv_json(s)
        check("audio before hello is refused with the start-again sentence",
              bye.get("t") == "bye" and "could not start" in str(bye.get("why")), bye)
        s.close()
    finally:
        srv.close()
    srv = Server(switch=True, engine=FakeEngine(ok=False), sink=Sink())
    try:
        s, _, _ = ws_connect(srv.port)
        send_json(s, {"t": "hello", "device": "phone", "live_id": "x"})
        bye = recv_json(s)
        check("a session the engine does not accept is refused in plain words",
              bye.get("t") == "bye" and "not on for this device" in str(bye.get("why")), bye)
        s.close()
    finally:
        srv.close()


def t_unwired_sink_refuses_the_turn_honestly():
    srv = Server(switch=True, sink="none")
    try:
        s, _, _ = ws_connect(srv.port)
        epoch = int(hello(s)["epoch"])
        audio(s, epoch, 1)
        send_json(s, {"t": "end_turn"})
        bye = recv_json(s)
        check("with no speech hand-off wired, a turn is refused, not faked",
              bye.get("t") == "bye" and "not built" in str(bye.get("why")), bye)
        s.close()
    finally:
        srv.close()


def t_cancel_clears_the_ring_and_a_silent_turn_is_empty():
    sink = Sink()
    srv = Server(switch=True, sink=sink)
    try:
        s, _, _ = ws_connect(srv.port)
        epoch = int(hello(s)["epoch"])
        audio(s, epoch, 1)
        send_json(s, {"t": "cancel"})
        msg = recv_json(s)
        check("cancel acknowledges with the design's 'say that again' line",
              msg.get("t") == "dropped" and "say that again" in str(msg.get("why")), msg)
        send_json(s, {"t": "end_turn"})
        recv_json(s)                             # turn_started
        check("the ring really was cleared by cancel",
              len(sink.wavs) == 1 and len(sink.wavs[0]) == 44,
              (len(sink.wavs), len(sink.wavs[0]) if sink.wavs else None))
        s.close()
    finally:
        srv.close()


def t_bounds_and_ram_only():
    st = S.StreamState(epoch=5)
    step = S.FRAME_BYTES
    for seq in range(0, 40):                     # 40 x 64 ms > the 2 s ring
        st.accept_audio(S.put_varint(5 + step)
                        + S.audio_payload(5, seq, b"\x00" * step))
    check("the ring never grows past its cap", len(st.ring) <= S.RING_BYTES, len(st.ring))
    wav = st.end_turn()
    check("end_turn empties the ring", len(st.ring) == 0)
    check("the WAV is a real mono 16 kHz 16-bit WAV",
          wav.startswith(b"RIFF") and wav[8:12] == b"WAVE"
          and struct.unpack("<H", wav[22:24])[0] == 1
          and struct.unpack("<I", wav[24:28])[0] == S.SAMPLE_RATE
          and struct.unpack("<H", wav[34:36])[0] == 16, wav[:44])
    # Behaviour, not source text: no file may be opened while a turn is built.
    import builtins
    real_open = builtins.open
    opened = []

    def no_files(path, *a, **k):
        opened.append(str(path))
        raise AssertionError("this module must not open a file")

    builtins.open = no_files
    try:
        quiet = S.StreamState(epoch=6)
        quiet.accept_audio(S.put_varint(5 + S.FRAME_BYTES)
                           + S.audio_payload(6, 1, b"\x00" * S.FRAME_BYTES))
        wav2 = quiet.end_turn()
    finally:
        builtins.open = real_open
    check("a whole turn builds its WAV with no file opened", wav2.startswith(b"RIFF")
          and not opened, opened)
    check("this module loads no logger and no audit channel",
          not any(hasattr(S, n) for n in ("logging", "audit_log", "_audit")),
          "a log/audit name appeared in jarvis_live_stream.py")


def t_varint_and_audio_payload_roundtrip():
    for n in (0, 1, 127, 128, 300, 16_384, 65_535):
        raw = S.put_varint(n)
        got, pos = S.get_varint(raw)
        check(f"varint round-trips {n}", got == n and pos == len(raw), (raw, got, pos))
    for bad in (b"\x80", b"\x80\x80\x80\x80\x80"):
        try:
            S.get_varint(bad)
            refused = False
        except ValueError:
            refused = True
        check(f"varint refuses a malformed prefix {bad!r}", refused)
    pcm = b"\x01\x02" * 64
    inner = S.audio_payload(9, 1234, pcm)
    epoch, seq, back = S.decode_audio_payload(S.put_varint(len(inner)) + inner)
    check("an audio payload round-trips epoch, sequence and PCM",
          (epoch, seq, back) == (9, 1234, pcm), (epoch, seq, len(back)))
    for bad in (S.put_varint(len(inner)) + inner + b"\x00",
                S.put_varint(3) + inner):
        try:
            S.decode_audio_payload(bad)
            refused = False
        except S.StreamRefused:
            refused = True
        check("a length prefix that lies is refused", refused)
    try:
        S.decode_audio_payload(S.put_varint(len(inner)) + inner.replace(inner, b"\x09" + inner[1:] + b"\x00\x00"))
        odd = False
    except S.StreamRefused:
        odd = True
    check("an odd number of PCM bytes is refused", odd)


def t_shipped_and_switch_state():
    check("the new module is in the SHIPPED list", "jarvis_live_stream.py" in SHIPPED,
          "add it to backend/_where.py AND scripts/apply-patches.ps1 $SHIPPED")
    twin = REPO / "jarvis-backend" / "jarvis_live_stream.py"
    check("the published base carries a byte-identical copy", twin.is_file()
          and twin.read_bytes() == (HERE / "jarvis_live_stream.py").read_bytes())
    framework = (REPO / "backend" / "rebuilt" / "jarvis-framework.toml").read_text(
        encoding="utf-8")
    check("the shipped switch is still [live] stream = false",
          "stream = false" in framework)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn) and fn.__module__ == "__main__":
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
