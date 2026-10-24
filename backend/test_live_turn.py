"""test_live_turn.py - one whole Live turn on the PC (Slice G, G2b).

    python3 backend/test_live_turn.py

What this proves, with every slow/private step stubbed except the network hop
itself, which runs on 127.0.0.1:

  1. THE PATH: a WAV goes into `hear()`, its words into the PC's own
     `/api/chat` with `live: true` and the phone's token, its answer into
     `say()`, and the answer's WAV leaves as the design's 64 ms PCM frames.
  2. THE SILENT OUTCOMES ARE SILENT: a voice that is not the owner, and a clip
     that made no words, produce NO answer and NO speech - never a guess.
  3. THE FAILURES ARE PLAIN: no voice engine, no chat, no token -> a plain
     sentence, no half turn.
  4. THE REAL LOOPBACK: a real HTTP server on 127.0.0.1, checked to receive
     the token header, the HUD client header and a message marked `live`, and
     to answer in the OpenAI-style SSE chunks the route really produces.
  5. The frame shape, the WAV header stripping, the shipped list and the base
     twin.

No model, no voice check, no TTS engine, no phone, and no audio ever written
to a file: the stand-ins are plain Python objects.
"""
from __future__ import annotations

import io
import json
import sys
import threading
import traceback
import types
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "rebuilt"))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
from _where import REPO, SHIPPED, require_shipped  # noqa: E402

require_shipped("jarvis_live.py")

if "jarvis_framework" not in sys.modules:
    fw = types.ModuleType("jarvis_framework")
    fw.CONFIG_DIR = HERE
    fw.LOG_DIR = HERE
    fw.load_framework = lambda: {}
    fw.audit_log = lambda event, detail=None, **k: None
    fw.action_tier = lambda action: "ask"
    sys.modules["jarvis_framework"] = fw

import jarvis_live_turn as T  # noqa: E402

PASSED, FAILED = [], []
SKIPPED = []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    SKIPPED.append(why)
    print(f"SKIP {why}")


def make_wav(pcm: bytes, rate: int = T.SAMPLE_RATE) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(pcm))
    return buf.getvalue()


class Heard:
    def __init__(self, *, owner=True, text="what time is it"):
        self.owner, self.text = owner, text

    def as_dict(self):
        return {"is_owner": self.owner, "owner": self.owner, "text": self.text}


def with_hooks(*, hear=None, chat=None, say=None):
    old = (T.HEAR, T.CHAT, T.SAY)
    T.HEAR = hear if hear is not None else (lambda wav: Heard())
    T.CHAT = chat if chat is not None else (
        lambda text, *, token, port: {"ok": True, "text": "It is nine."})
    T.SAY = say if say is not None else (lambda text: make_wav(b"\x05\x00" * 4096))
    return old


def restore(old):
    T.HEAR, T.CHAT, T.SAY = old


# ---------------------------------------------------------------- checks ----

def t_one_whole_turn_with_stubs():
    old = with_hooks(say=lambda text: make_wav(b"\x07\x00" * 3000))
    try:
        out = T.turn(b"RIFFxx", {"token": "t0ken", "port": 4321, "device": "phone"})
    finally:
        restore(old)
    check("a whole turn returns its answer words",
          out.get("ok") is True and out.get("text") == "It is nine.", out)
    check("the answer leaves as 2,048-byte PCM frames (last one short)",
          [len(f) for f in out.get("speech") or []] == [2048, 2048, 1904],
          [len(f) for f in out.get("speech") or []])
    check("the frames carry the WAV's samples, not its header",
          all(f[:2] == b"\x07\x00" for f in out.get("speech") or []),
          (out.get("speech") or [b""])[0][:4])


def t_not_owner_and_no_words_are_silent():
    old = with_hooks(hear=lambda wav: Heard(owner=False))
    try:
        out = T.turn(b"RIFFxx", {"token": "t", "port": 1})
    finally:
        restore(old)
    check("a voice that is not the owner is silent (no words, no answer)",
          out.get("ok") is True and out.get("not_owner") is True
          and out.get("speech") == [] and not out.get("text"), out)
    old = with_hooks(hear=lambda wav: Heard(text=""))
    try:
        out = T.turn(b"RIFFxx", {"token": "t", "port": 1})
    finally:
        restore(old)
    check("a clip that made no words is silent too",
          out.get("ok") is True and out.get("speech") == []
          and not out.get("not_owner"), out)


def t_failures_are_plain_and_never_half_a_turn():
    old = with_hooks(say=lambda text: None)
    try:
        out = T.turn(b"RIFFxx", {"token": "t", "port": 1})
    finally:
        restore(old)
    check("no text-to-speech engine: a plain sentence, no speech",
          out.get("ok") is False and "voice engine" in str(out.get("why"))
          and out.get("speech") == [], out)
    old = with_hooks(chat=lambda text, *, token, port: {"ok": False, "why": "chat down"})
    try:
        out = T.turn(b"RIFFxx", {"token": "t", "port": 1})
    finally:
        restore(old)
    check("a chat that failed: a plain sentence, no speech",
          out.get("ok") is False and "chat down" in str(out.get("why")), out)
    old = with_hooks()
    try:
        out = T.turn(b"RIFFxx", {})
    finally:
        restore(old)
    check("no token or port: it refuses instead of linking itself",
          out.get("ok") is False and "lost the link" in str(out.get("why")), out)


def t_wav_and_frames_helpers():
    pcm = bytes(range(256)) * 8
    check("pcm_from_wav strips a real mono 16-bit WAV's header",
          T.pcm_from_wav(make_wav(pcm)) == pcm)
    check("raw PCM is passed through untouched",
          T.pcm_from_wav(b"\x01\x02\x03") == b"\x01\x02\x03")
    check("a damaged RIFF file is refused, not guessed at",
          T.pcm_from_wav(b"RIFF" + b"\x00" * 40) == b"")
    frames = T.speech_frames(b"\x00\x00" * 3000)
    check("frames are 2,048 bytes and the last one is the remainder",
          [len(f) for f in frames] == [2048, 2048, 1904], [len(f) for f in frames])


class _ChatHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    seen = {}

    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        _ChatHandler.seen = {
            "path": self.path,
            "token": self.headers.get("X-Jarvis-Token"),
            "client": self.headers.get("X-Jarvis-Client"),
            "live": (body.get("messages") or [{}])[0].get("live"),
            "text": (body.get("messages") or [{}])[0].get("content"),
            "stream": body.get("stream"),
        }
        if self.path != "/api/chat" or not _ChatHandler.seen["token"]:
            self.send_response(401)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")
        self.end_headers()
        for line in (
            'data: {"choices":[{"delta":{"content":"It is "}}]}',
            'data: {"choices":[{"delta":{"content":"nine."}}]}',
            'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}',
            "data: [DONE]",
        ):
            self.wfile.write((line + "\n\n").encode("utf-8"))
        self.wfile.flush()


def t_the_real_loopback_chat_call():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _ChatHandler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        out = T.ask_pc("what time is it", token="phone-token", port=port)
        seen = _ChatHandler.seen
    finally:
        httpd.shutdown()
        httpd.server_close()
    check("the PC's own chat route is asked over 127.0.0.1",
          seen.get("path") == "/api/chat", seen)
    check("it carries the phone's token and the HUD client header",
          seen.get("token") == "phone-token" and seen.get("client") == "hud", seen)
    check("the message is marked live and asks for the streaming answer",
          seen.get("live") is True and seen.get("stream") is True
          and seen.get("text") == "what time is it", seen)
    check("the SSE chunks are joined into the answer",
          out.get("ok") is True and out.get("text") == "It is nine.", out)


def t_shipped_list_and_base_twin():
    check("the turn module is in the SHIPPED list", "jarvis_live_turn.py" in SHIPPED,
          "add it to backend/_where.py AND scripts/apply-patches.ps1 $SHIPPED")
    check("the published base carries the module file",
          (REPO / "jarvis-backend" / "jarvis_live_turn.py").is_file())
    check("the turn module has no logger and no audit channel",
          not any(hasattr(T, n) for n in ("logging", "audit_log", "_audit")))


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
