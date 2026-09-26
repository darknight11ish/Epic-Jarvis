"""jarvis_local_http.py - requests to this PC's own services never use a proxy.

    python3 test_local_http.py

THE BUG (bug audit 3, CONN-1). urllib sends a request through whatever proxy
HTTP_PROXY, or on Windows the system proxy, names - "127.0.0.1" included.
The audit pointed HTTP_PROXY at a fake proxy and it received
`GET http://127.0.0.1:41184/search?...&token=<the Joplin token>`.

WHAT THIS PINS, for every call site that talks to a service on this PC:
  - with HTTP_PROXY (and http_proxy) pointing at a trap, and NO_PROXY unset,
    the trap receives NOTHING and the real service receives the request;
  - jarvis_notes and jarvis_note_capture still refuse a redirect (their
    `_RefuseRedirect` survived the change);
  - none of those functions calls `urllib.request.urlopen` or builds its own
    opener any more, read from the source, so a new call site in them cannot
    quietly go back to the proxied path.

Real sockets on 127.0.0.1 only. Nothing leaves this machine.
"""
import ast
import json
import os
import socket
import sys
import threading
import traceback
import types
import tempfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import BACKEND, require_shipped  # noqa: E402

require_shipped("jarvis_local_http.py", "jarvis_notes.py", "jarvis_note_capture.py",
                "jarvis_second_card.py", "jarvis_wiki.py", "jarvis_agent.py")

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-local-http-"))
if "jarvis_framework" not in sys.modules:
    fw = types.ModuleType("jarvis_framework")
    fw.CONFIG_DIR = _TMP
    fw.LOG_DIR = _TMP
    fw.load_framework = lambda: {}
    fw.audit_log = lambda e, d: None
    sys.modules["jarvis_framework"] = fw

import jarvis_agent as AG  # noqa: E402
import jarvis_local_http as LH  # noqa: E402
import jarvis_note_capture as NC  # noqa: E402
import jarvis_notes as N  # noqa: E402
import jarvis_second_card as SC  # noqa: E402
import jarvis_wiki as W  # noqa: E402

FAILED, PASSED = [], []
TOKEN = "JOPLIN-SECRET-123"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


# ------------------------------------------------------------------ the trap --

class Trap:
    """A 'proxy' that records the first line of anything sent to it."""

    def __init__(self):
        self.got = []
        self.srv = socket.socket()
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(16)
        self.port = self.srv.getsockname()[1]
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        while True:
            try:
                c, _ = self.srv.accept()
            except OSError:
                return
            try:
                c.settimeout(2)
                data = c.recv(4096).decode("latin-1", "replace")
                self.got.append(data.splitlines()[0] if data else "(connected, sent nothing)")
                c.sendall(b"HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n\r\n{}")
            except OSError:
                pass
            finally:
                c.close()


class Service:
    """The real local service: answers JSON, or a redirect when asked to."""

    def __init__(self):
        self.seen = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def _answer(self):
                n = int(self.headers.get("Content-Length") or 0)
                if n:
                    self.rfile.read(n)
                outer.seen.append(f"{self.command} {self.path}")
                if self.path.startswith("/redirect"):
                    self.send_response(302)
                    self.send_header("Location", "http://192.0.2.1/elsewhere")
                    self.end_headers()
                    return
                body = b'{"items": [], "version": "0", "models": [], "message": {"content": "{}"}}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            do_GET = do_POST = _answer

            def log_message(self, *a):
                pass

        self.httpd = HTTPServer(("127.0.0.1", 0), H)
        self.port = self.httpd.server_address[1]
        self.base = f"http://127.0.0.1:{self.port}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()


TRAP = Trap()
SVC = Service()
for k in ("NO_PROXY", "no_proxy"):
    os.environ.pop(k, None)
for k in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ[k] = f"http://127.0.0.1:{TRAP.port}"
os.environ[N.JOPLIN_TOKEN_ENV] = TOKEN


def t_the_trap_is_real():
    # CONTROL: plain urllib, the way the five call sites used to do it, DOES
    # go to the trap. Without this, "the trap got nothing" could mean the
    # trap was never reachable.
    import urllib.request
    before = len(TRAP.got)
    try:
        with urllib.request.urlopen(f"{SVC.base}/control", timeout=5) as r:
            r.read()
    except Exception:
        pass
    check("CONTROL: plain urllib.request.urlopen goes through HTTP_PROXY (the old path)",
          len(TRAP.got) == before + 1 and "/control" in TRAP.got[-1], repr(TRAP.got[before:]))


def _through(name, call, want_path):
    before_trap, before_svc = len(TRAP.got), len(SVC.seen)
    err = None
    try:
        call()
    except Exception as exc:  # the answer's shape is not what is tested here
        err = f"{type(exc).__name__}: {exc}"
    trapped = TRAP.got[before_trap:]
    seen = SVC.seen[before_svc:]
    check(f"{name}: the proxy received nothing", not trapped, repr(trapped))
    check(f"{name}: the request went straight to the service",
          any(want_path in s for s in seen), f"service saw {seen!r}; error {err}")
    check(f"{name}: the token never reached the proxy",
          not any(TOKEN in t for t in trapped), repr(trapped))


def t_every_call_site_skips_the_proxy():
    plan = N.Plan(backend="joplin", query="groceries", limit=5,
                  url=f"{SVC.base}/search?query=groceries", if_refused="x")
    _through("jarvis_notes._default_fetch", lambda: N._default_fetch(plan), "/search")
    _through("jarvis_note_capture._joplin_call",
             lambda: NC._joplin_call("GET", SVC.base, "/folders", {}), "/folders")
    _through("jarvis_second_card._http_json (GET)",
             lambda: SC._http_json(f"{SVC.base}/api/version"), "/api/version")
    _through("jarvis_second_card._http_json (POST)",
             lambda: SC._http_json(f"{SVC.base}/api/generate", {"x": 1}), "/api/generate")
    _through("jarvis_wiki._post_json",
             lambda: W._post_json(f"{SVC.base}/api/chat", {"x": 1}), "/api/chat")
    _through("jarvis_agent._post",
             lambda: AG._post(f"{SVC.base}/v1/chat/completions", {"x": 1}), "/v1/chat/completions")

    def stream():
        with AG._open_stream(f"{SVC.base}/v1/stream", {"x": 1}) as r:
            r.read()
    _through("jarvis_agent._open_stream", stream, "/v1/stream")
    _through("jarvis_agent._get_json (GET)", lambda: AG._get_json(f"{SVC.base}/api/ps"), "/api/ps")
    _through("jarvis_agent._get_json (POST)",
             lambda: AG._get_json(f"{SVC.base}/api/show", {"model": "m"}), "/api/show")


def t_the_redirect_refusal_survived():
    import urllib.error
    plan = N.Plan(backend="joplin", query="q", limit=5, url=f"{SVC.base}/redirect", if_refused="x")
    try:
        N._default_fetch(plan)
        got = "followed"
    except urllib.error.HTTPError as exc:
        got = str(exc)
    except Exception as exc:
        got = f"{type(exc).__name__}: {exc}"
    check("jarvis_notes still refuses a redirect", "refused to follow a redirect" in got, got)
    try:
        NC._joplin_call("GET", SVC.base, "/redirect", {})
        got = "followed"
    except urllib.error.HTTPError as exc:
        got = str(exc)
    except Exception as exc:
        got = f"{type(exc).__name__}: {exc}"
    check("jarvis_note_capture still refuses a redirect", "redirected" in got, got)
    check("...and neither message carries the token", TOKEN not in got, got)


def t_the_helper_itself():
    o = LH.opener()
    import urllib.request
    proxies = [h for h in o.handlers if isinstance(h, urllib.request.ProxyHandler)]
    # An empty ProxyHandler has no *_open methods, so build_opener drops it -
    # and, because one was passed, does not add the default one that reads
    # HTTP_PROXY and the registry. So: no ProxyHandler at all.
    check("opener() has no proxy handler (the environment's is never added)",
          proxies == [], repr([p.proxies for p in proxies]))
    check("CONTROL: a plain build_opener() does have one, reading HTTP_PROXY",
          any(isinstance(h, urllib.request.ProxyHandler) and h.proxies.get("http")
              for h in urllib.request.build_opener().handlers))
    o2 = LH.opener(N._RefuseRedirect)
    check("opener(handler) keeps the handler it was given",
          any(isinstance(h, N._RefuseRedirect) for h in o2.handlers))


# The functions that must use the helper, by file. Read from the source, so a
# new urlopen() in one of them fails here even if no test calls it.
SITES = {
    "jarvis_notes.py": ("_default_fetch",),
    "jarvis_note_capture.py": ("_joplin_call",),
    "jarvis_second_card.py": ("_http_json",),
    "jarvis_wiki.py": ("_post_json",),
    "jarvis_agent.py": ("_post", "_open_stream", "_get_json"),
}


def t_no_call_site_goes_back_to_plain_urllib():
    for fname, funcs in SITES.items():
        tree = ast.parse((BACKEND / fname).read_text(encoding="utf-8"))
        defs = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        for fn in funcs:
            node = defs.get(fn)
            if node is None:
                check(f"{fname} still has {fn}()", False, "renamed? update SITES")
                continue
            bad = [ast.unparse(c.func) for c in ast.walk(node) if isinstance(c, ast.Call)
                   and ast.unparse(c.func).endswith(("urlopen", "build_opener"))
                   and not ast.unparse(c.func).startswith("jarvis_local_http.")]
            uses = any(isinstance(c, ast.Call) and ast.unparse(c.func).startswith("jarvis_local_http.")
                       for c in ast.walk(node))
            check(f"{fname} {fn}() opens through jarvis_local_http, not plain urllib",
                  uses and not bad, f"plain calls: {bad}")


if __name__ == "__main__":
    for fn in (t_the_trap_is_real, t_every_call_site_skips_the_proxy,
               t_the_redirect_refusal_survived, t_the_helper_itself,
               t_no_call_site_goes_back_to_plain_urllib):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    sys.exit(1 if FAILED else 0)
