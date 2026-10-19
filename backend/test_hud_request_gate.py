"""N3 server hardening, tested at the server seam (SECPRIV audit 2026-10-18).

    python3 backend/test_hud_request_gate.py

The three behaviours are the three "named bites" of this patch; each is written
so that REMOVING the behaviour makes it fail, not just so that the code runs:

  (a) a socket that sends half a request line and then stops is closed by the
      10 s header deadline (the test shortens the constant to 0.4 s);
  (b) while 32 handlers are held open, the 33rd request is answered with a
      minimal 503 + Retry-After: 2 WITHOUT a 33rd handler thread (a bounded
      semaphore, not an unbounded thread spawn);
  (c) the 11th invalid-token request from one peer inside 60 s is refused by
      the pure TokenFailureLimiter, `_request_gate._send` turns that route's
      401 into a 429 + Retry-After: 60, and one valid token resets the peer.

The gate helper and the `_HudServer` class are lifted out of
`backend/hud-request-gate.patch`'s own added lines, so this runs on a clean
checkout with no owner PC and no live HUD. `jarvis_owner_check` is imported
directly for the limiter (it is a tracked $SHIPPED module). What this cannot
prove: that the owner's installed jarvis_hud.py has the patch applied - only
apply-patches.ps1 there can do that, and nothing in this repository applies
patches to a live backend.
"""
from __future__ import annotations

import ast
import re
import socket
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import jarvis_owner_check as OC  # noqa: E402

PATCH = HERE / "hud-request-gate.patch"
PS1 = HERE.parent / "scripts" / "apply-patches.ps1"
FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (FAILED if not cond else PASSED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


class Quiet(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")


def _patch_text() -> str:
    return PATCH.read_text(encoding="utf-8") if PATCH.is_file() else ""


def _added_block(start_prefix: str, indented: bool = False) -> str:
    """One contiguous block of patch-added lines beginning with a prefix."""
    lines = _patch_text().splitlines()
    out, inside = [], False
    body_prefix = "+        " if indented else "+"
    for line in lines:
        if not inside and line.startswith(start_prefix):
            inside = True
        if inside:
            if line.startswith("+"):
                out.append(line[1:])
                continue
            break
    return "\n".join(out) + "\n" if out else ""


def _gate_namespace(header_timeout=None, request_timeout=None):
    source = _added_block("+_HUD_HEADER_TIMEOUT_SECONDS")
    assert source, "no timeout constants in the patch"
    ns = {"sys": sys}
    exec(compile(source, "<patch-gate>", "exec"), ns)
    if header_timeout is not None:
        ns["_HUD_HEADER_TIMEOUT_SECONDS"] = header_timeout
    if request_timeout is not None:
        ns["_HUD_REQUEST_TIMEOUT_SECONDS"] = request_timeout
    return ns


def _server_class():
    # The N3 patch adds the class's METHODS, while its header,
    # allow_reuse_address and server_bind are context lines from the N4 patch.
    # Lift the added methods verbatim (they are the behaviour under test), and
    # give them the N4 header the patch context carries.
    added = []
    for line in _patch_text().splitlines():
        if line.startswith("+"):
            added.append(line[1:])
    blocks = {}
    order = []
    cur = None
    for line in added:
        stripped = line.lstrip()
        if stripped.startswith("def "):
            name = stripped.split("(", 1)[0][4:].strip()
            cur = []
            blocks[name] = cur
            order.append(name)
            cur.append(line[4:] if line.startswith("    ") else stripped)
        elif cur is not None:
            if line.strip() and not line.startswith("        "):
                cur = None           # main()'s own `Handler = ...` line
                continue
            cur.append(line[4:] if line.startswith("    ") else line)
    wanted = ("__init__", "process_request", "process_request_thread", "_refuse_busy")
    assert all(w in blocks for w in wanted), sorted(blocks)
    header = ("class _HudServer(ThreadingHTTPServer):\n"
              "    allow_reuse_address = False\n"
              "    max_request_slots = 32\n\n"
              "    def server_bind(self):\n"
              "        super().server_bind()\n\n")
    body = "\n".join("\n".join(blocks[w]).rstrip() for w in wanted) + "\n"
    source = header + body
    ns = {"ThreadingHTTPServer": ThreadingHTTPServer, "threading": threading,
          "socket": socket, "os": __import__("os")}
    exec(compile(source, "<patch-server>", "exec"), ns)
    return ns["_HudServer"]


# ---------------------------------------------------------------- (a) header

def t_a_slow_header_is_closed_by_the_deadline():
    ns = _gate_namespace(header_timeout=0.4, request_timeout=10.0)
    gated = ns["_request_gate"](Quiet)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), gated)
    srv.daemon_threads = True
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    port = srv.server_address[1]
    try:
        started = time.monotonic()
        slow = socket.create_connection(("127.0.0.1", port), timeout=5)
        slow.sendall(b"GET / HTTP/1.1\r\n")     # half a request line, no end
        slow.settimeout(5)
        closed = False
        try:
            data = slow.recv(64)
            closed = data == b""
        except (ConnectionResetError, TimeoutError, OSError):
            closed = True
        elapsed = time.monotonic() - started
        slow.close()
        check("(a) a slow-header socket is closed by the header deadline",
              closed and elapsed < 3.0, f"closed={closed} after {elapsed:.2f}s")
        # CONTROL: a complete request still answers normally.
        quick = socket.create_connection(("127.0.0.1", port), timeout=5)
        quick.sendall(b"GET / HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
        reply = b""
        try:
            while True:
                chunk = quick.recv(4096)
                if not chunk:
                    break
                reply += chunk
        finally:
            quick.close()
        check("(a) control: a normal request still answers 200",
              reply.startswith(b"HTTP/1.0 200") or reply.startswith(b"HTTP/1.1 200"),
              reply[:80])
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=3)


# ----------------------------------------------------------- (b) 33rd request

def t_the_33rd_concurrent_request_gets_503_without_a_thread():
    server_class = _server_class()
    assert server_class.max_request_slots == 32, server_class.max_request_slots
    release = threading.Event()
    started = threading.Semaphore(0)

    class Held(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            started.release()
            release.wait(15)
            try:
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"ok")
            except OSError:
                pass

    srv = server_class(("127.0.0.1", 0), Held)
    srv.daemon_threads = True
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    port = srv.server_address[1]
    clients = []
    try:
        for _ in range(32):
            s = socket.create_connection(("127.0.0.1", port), timeout=10)
            s.sendall(b"GET / HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
            clients.append(s)
        held = 0
        for _ in range(32):
            if started.acquire(timeout=10):
                held += 1
        check("(b) 32 handlers are really held open", held == 32, held)
        third = socket.create_connection(("127.0.0.1", port), timeout=10)
        try:
            third.sendall(b"GET / HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
            third.settimeout(10)
            head = b""
            while b"\r\n\r\n" not in head:
                chunk = third.recv(4096)
                if not chunk:
                    break
                head += chunk
        finally:
            third.close()
        check("(b) the 33rd request gets 503 Service Unavailable",
              head.startswith(b"HTTP/1.1 503"), head[:120])
        check("(b) ... with Retry-After: 2 before any 33rd thread exists",
              b"Retry-After: 2" in head, head[:200])
    finally:
        release.set()
        for s in clients:
            try:
                s.close()
            except OSError:
                pass
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=5)


# --------------------------------------------------------------- (c) limiter

def t_the_11th_bad_token_is_429_and_a_valid_one_resets():
    now = [1000.0]
    lim = OC.TokenFailureLimiter(max_failures=10, window_s=60.0,
                                clock=lambda: now[0])
    peer = "100.64.0.9"
    for i in range(10):
        lim.failed(peer)
    check("(c) 10 bad tokens are not blocked yet", lim.blocked(peer) is False)
    lim.failed(peer)
    check("(c) the 11th bad token inside 60 s blocks that peer",
          lim.blocked(peer) is True)
    check("(c) another peer is not punished for it",
          lim.blocked("127.0.0.1") is False)
    now[0] += 61.0
    check("(c) the window passes and the peer is unblocked again",
          lim.blocked(peer) is False)
    for _ in range(10):
        lim.failed(peer)
    lim.succeeded(peer)
    check("(c) one valid token resets the peer at once", lim.blocked(peer) is False)

    class H:
        def __init__(self, headers=None, path="/"):
            self.headers = dict(headers or {})
            self.path = path

    check("(c) a request with no token at all is not counted",
          OC.request_carries_token(H()) is False)
    check("(c) a normal unauthenticated status poll is not counted",
          OC.request_carries_token(H({}, "/api/status")) is False)
    check("(c) a path that merely CONTAINS 'token' is not a presentation",
          OC.request_carries_token(H({}, "/api/token-store/info")) is False)
    check("(c) a cookie VALUE that looks like a token name is not a presentation",
          OC.request_carries_token(H({"Cookie": "other=jarvis_token=guess"})) is False)
    check("(c) a request presenting a token is counted (header)",
          OC.request_carries_token(H({"X-Jarvis-Token": "wrong"})) is True)
    check("(c) ... and via the cookie too",
          OC.request_carries_token(H({"Cookie": "a=b; jarvis_token=wrong"})) is True)
    check("(c) ... and via the one-time query token",
          OC.request_carries_token(H({}, "/?token=wrong")) is True)
    # 2026-10-18 security-wave follow-up (MEDIUM): the HUD decodes the query
    # with parse_qs, so `tok%65n=` IS the ?token= bootstrap to it. Counting
    # only the raw spelling let an encoded guess get a 401 without ever
    # filling the bucket.
    check("(c) a percent-encoded ?tok%65n= guess IS counted (no bucket bypass)",
          OC.request_carries_token(H({}, "/?tok%65n=guess")) is True)
    check("(c) ... and so is a fully encoded token name",
          OC.request_carries_token(H({}, "/api/x?%74oken=guess")) is True)


def t_the_401_becomes_429_only_when_the_bucket_is_full():
    ns = _gate_namespace(header_timeout=1.0, request_timeout=10.0)
    sent = []

    class Base:
        client_address = ("100.64.0.9", 5000)

        def _send(self, code, body, ctype="application/json; charset=utf-8",
                  extra_headers=None):
            sent.append((code, body, extra_headers))
            return "sent"

    Gated = ns["_request_gate"](Base)

    class Fake(Gated):
        def __init__(self):
            self.client_address = ("100.64.0.9", 5000)

    handler = Fake()
    real = OC.TOKEN_FAILURES
    try:
        OC.TOKEN_FAILURES = OC.TokenFailureLimiter(max_failures=1,
                                                   clock=lambda: 0.0)
        OC.TOKEN_FAILURES.failed("100.64.0.9")
        OC.TOKEN_FAILURES.failed("100.64.0.9")   # "over 1" means the second
        handler._send(401, {"error": "bad token"})
        check("(c) a full bucket turns the route's 401 into 429",
              sent and sent[-1][0] == 429, sent[-1] if sent else None)
        check("(c) ... and says Retry-After: 60",
              sent and ("Retry-After", "60") in (sent[-1][2] or []), sent[-1] if sent else None)
        OC.TOKEN_FAILURES = OC.TokenFailureLimiter(max_failures=100,
                                                   clock=lambda: 0.0)
        handler._send(401, {"error": "bad token"})
        check("(c) a normal 401 stays a 401 with no Retry-After",
              sent[-1][0] == 401 and not sent[-1][2], sent[-1])
    finally:
        OC.TOKEN_FAILURES = real


def _main_hunk_lines() -> list:
    """The patch's main() body lines: context and additions, no removals."""
    hunks, cur = [], None
    for line in _patch_text().splitlines():
        if line.startswith("@@"):
            cur = []
            hunks.append(cur)
            continue
        if cur is not None:
            cur.append(line)
    hunk = next((h for h in hunks if any("_HudServer" in l for l in h)),
                None)
    assert hunk is not None, "no main() hunk in the patch"
    return [line[1:] if len(line) > 1 else "" for line in hunk
            if not line.startswith("-")]


def t_main_does_not_shadow_a_name_it_loads_earlier():
    """The live-deploy break this test exists for (2026-10-19).

    hud-request-gate.patch used to add `Handler = _request_gate(Handler)`
    inside main(). A later assignment makes `Handler` local to main() for the
    WHOLE function in Python, so every earlier `install(Handler, ...)` line
    raised UnboundLocalError and the HUD refused to start. The patch now
    wraps into `RequestHandler` and passes that to _HudServer.

    This checks the generic rule, not one spelling: in a main() body built
    from the patch's own lines (with an `install(Handler)` before them, as the
    real file has), no name may be STORED after it was LOADed - that is
    exactly the local-shadowing trap. It also compiles the fragment and checks
    the added lines by name. The full HUD boot smoke is only possible on the
    owner's PC (the real jarvis_hud.py is not in this repository).
    """
    text = _patch_text()
    check("the patch never assigns the global Handler inside main()",
          not re.search(r"^\+\s{4}Handler\s*=", text, re.M), "found +    Handler =")
    check("... it wraps into RequestHandler instead",
          "+    RequestHandler = _request_gate(Handler)" in text)
    check("... and the server uses RequestHandler",
          "+    httpd = _HudServer((bind, HUD_PORT), RequestHandler)" in text)
    check("... the old server line is replaced, not kept as context",
          "     httpd = _HudServer((bind, HUD_PORT), Handler)" not in text)

    # Simple statement lines the patch adds to main() (skip class/def blocks,
    # whose bodies live in later hunks and would be a syntax fragment on
    # their own). The lines we are testing are exactly these assignments.
    body = [line[1:] for line in text.splitlines()
            if line.startswith("+    ")
            and ("_HudServer" in line or "RequestHandler" in line
                 or "Handler =" in line)]
    snippet = ("def install(name):\n    return name\n\n\n"
               "def main():\n"
               "    install(Handler)\n"
               + "\n".join(body) + "\n")
    try:
        tree = ast.parse(snippet)
        compile(snippet, "<patched-main-fragment>", "exec")
        parse_ok = True
    except SyntaxError as exc:
        parse_ok = False
        tree = None
        detail = str(exc)
    else:
        detail = ""
    check("the patched main() fragment parses and py_compiles", parse_ok, detail)
    if tree is None:
        return
    fn = tree.body[-1]
    first_load, first_store = {}, {}
    for node in ast.walk(fn):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Load, ast.Store)):
            table = first_load if isinstance(node.ctx, ast.Load) else first_store
            table.setdefault(node.id, node.lineno)
    shadowed = sorted(name for name in first_store
                      if name in first_load and first_store[name] > first_load[name])
    check("no name in main() is stored after it is loaded (local-shadowing rule)",
          not shadowed, shadowed)


def t_the_patch_is_wired_into_the_stack():
    text = _patch_text()
    check("the request-gate patch ships", PATCH.is_file(), PATCH)
    check("... with the 10 s header deadline", "_HUD_HEADER_TIMEOUT_SECONDS = 10.0" in text)
    check("... and 32 bounded request slots", "max_request_slots = 32" in text)
    check("... answering 503 with Retry-After: 2", "Retry-After: 2" in text)
    ps1 = PS1.read_text(encoding="utf-8")
    start = ps1.index("$PATCHES = @(")
    block = ps1[start:ps1.index(chr(10) + ")", start)]
    names = [line.strip().strip("'") for line in block.splitlines()
             if line.strip().startswith("'")]
    check("apply-patches.ps1 applies it after hud-exclusive-bind and before "
          "plugin-loader.patch (still last)",
          "hud-request-gate.patch" in names
          and names.index("hud-exclusive-bind.patch") < names.index("hud-request-gate.patch")
          < names.index("plugin-loader.patch"))


if __name__ == "__main__":
    for fn in (t_main_does_not_shadow_a_name_it_loads_earlier,
               t_the_patch_is_wired_into_the_stack,
               t_a_slow_header_is_closed_by_the_deadline,
               t_the_33rd_concurrent_request_gets_503_without_a_thread,
               t_the_11th_bad_token_is_429_and_a_valid_one_resets,
               t_the_401_becomes_429_only_when_the_bucket_is_full):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, 0 skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
