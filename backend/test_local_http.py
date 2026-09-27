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


# --------------------------------------------------------------------------
# private_fetch_problem (I49/I67, 2026-09-27): the OPPOSITE question from
# plain_http_problem above - "does this address the owner typed, meant to
# be on the open internet, actually lead somewhere private?" - used by a
# news feed and "tell me when this page changes" before every fetch.
# --------------------------------------------------------------------------

def _fake_resolver(answers: dict):
    """Monkeypatches socket.getaddrinfo so a test never does a real DNS
    lookup. `answers`: {host: [ip, ...]} or {host: OSError} for NXDOMAIN."""
    import socket as _socket
    original = _socket.getaddrinfo

    def fake(host, *a, **kw):
        ans = answers.get(host)
        if ans is None:
            raise OSError("no such host (fake resolver)")
        if isinstance(ans, Exception):
            raise ans
        return [(_socket.AF_INET if "." in ip and ":" not in ip else _socket.AF_INET6,
                _socket.SOCK_STREAM, 6, "", (ip, 0)) for ip in ans]

    _socket.getaddrinfo = fake
    return original


def t_private_fetch_problem():
    import socket as _socket
    original = _socket.getaddrinfo
    try:
        check("a bare loopback address is refused",
              LH.private_fetch_problem("http://127.0.0.1/feed") != "")
        check("a home-network address is refused",
              LH.private_fetch_problem("http://192.168.1.5/feed") != "")
        check("a link-local address is refused",
              LH.private_fetch_problem("http://169.254.1.1/feed") != "")
        check("a public IPv4 literal is allowed",
              LH.private_fetch_problem("http://93.184.216.34/feed") == "")
        check("ftp:// is refused (not http/https)",
              LH.private_fetch_problem("ftp://example.com/feed") != "")
        check("no host at all is refused",
              LH.private_fetch_problem("http:///feed") != "")
        _fake_resolver({"feeds.example.com": ["93.184.216.34"]})
        check("a public-looking NAME that resolves to a public address is allowed",
              LH.private_fetch_problem("https://feeds.example.com/rss") == "")
        _fake_resolver({"feeds.example.com": ["10.0.0.5"]})
        check("the SAME name is refused once its DNS answer becomes private (SSRF/rebinding)",
              LH.private_fetch_problem("https://feeds.example.com/rss") != "")
        _fake_resolver({})
        check("a name that will not resolve at all is refused, not silently allowed",
              LH.private_fetch_problem("https://no-such-host.invalid/rss") != "")
    finally:
        _socket.getaddrinfo = original


def t_private_fetch_problem_checks_every_resolved_address():
    import socket as _socket
    original = _socket.getaddrinfo
    try:
        # Multi-A-record: even one private address among several public
        # ones is enough to refuse the whole address.
        _fake_resolver({"mixed.example.com": ["93.184.216.34", "10.1.2.3"]})
        check("one private address among several public ones is still refused",
              LH.private_fetch_problem("https://mixed.example.com/rss") != "")
    finally:
        _socket.getaddrinfo = original


def t_an_ipv4_mapped_dns_answer_is_judged_as_ipv4():
    """Security/privacy audit, 2026-09-27: a literal [::ffff:127.0.0.1] was
    refused, but the same address given as a DNS answer passed."""
    import socket as _socket
    original = _socket.getaddrinfo
    try:
        _fake_resolver({"mapped.example.com": ["::ffff:127.0.0.1"],
                        "mapped-home.example.com": ["::ffff:192.168.1.1"],
                        "mapped-public.example.com": ["::ffff:93.184.216.34"]})
        check("a DNS answer ::ffff:127.0.0.1 is refused (judged as 127.0.0.1)",
              "127.0.0.1" in LH.private_fetch_problem("https://mapped.example.com/rss"))
        check("... and ::ffff:192.168.1.1 too",
              LH.private_fetch_problem("https://mapped-home.example.com/rss") != "")
        check("... while a mapped PUBLIC address is still allowed",
              LH.private_fetch_problem("https://mapped-public.example.com/rss") == "")
    finally:
        _socket.getaddrinfo = original


class _Rebinding:
    """A resolver whose answer for one name changes on every lookup: a
    public address first, then this PC - the fast DNS rebinding the
    connection-time check exists for."""

    def __init__(self, name, answers):
        import socket as _socket
        self.name, self.answers, self.calls = name, list(answers), 0
        self.original = _socket.getaddrinfo

    def __call__(self, host, *a, **kw):
        import socket as _socket
        if host != self.name:
            return self.original(host, *a, **kw)
        ip = self.answers[min(self.calls, len(self.answers) - 1)]
        self.calls += 1
        port = a[0] if a and isinstance(a[0], int) else 0
        return [(_socket.AF_INET, _socket.SOCK_STREAM, 6, "", (ip, port))]


def t_public_urlopen_checks_the_address_it_connects_to():
    """The check and the connection used to do two separate lookups: an
    answer that changed in between reached this PC. public_urlopen's
    connection looks up once, checks, and connects to what it checked."""
    import socket as _socket
    import urllib.error
    import urllib.request
    before = len(SVC.seen)
    port = SVC.base.rsplit(":", 1)[1]
    for scheme in ("http", "https"):
        fake = _Rebinding("feed.rebind.example", ["93.184.216.34", "127.0.0.1"])
        _socket.getaddrinfo = fake
        try:
            check(f"{scheme}: the early check passes (the first answer is public)",
                  LH.private_fetch_problem(f"{scheme}://feed.rebind.example:{port}/rss") == "")
            try:
                LH.public_urlopen(urllib.request.Request(
                    f"{scheme}://feed.rebind.example:{port}/rss"), 5)
                got = "fetched"
            except urllib.error.URLError as exc:
                got = str(exc.reason)
            except Exception as exc:
                got = f"{type(exc).__name__}: {exc}"
        finally:
            _socket.getaddrinfo = fake.original
        check(f"{scheme}: the connection's own lookup, now 127.0.0.1, is refused",
              "127.0.0.1" in got and "private network" in got, got)
    check("... and this PC's service received nothing", len(SVC.seen) == before,
          SVC.seen[before:])
    # CONTROL: the plain opener, given the same rebinding name, does reach this PC.
    fake = _Rebinding("feed.rebind.example", ["93.184.216.34", "127.0.0.1"])
    _socket.getaddrinfo = fake
    try:
        LH.private_fetch_problem(f"http://feed.rebind.example:{port}/control-rebind")
        try:
            LH.urlopen(urllib.request.Request(
                f"http://feed.rebind.example:{port}/control-rebind"), 5).read()
        except Exception:
            pass
    finally:
        _socket.getaddrinfo = fake.original
    check("CONTROL: the old path (check, then a plain connect) did reach this PC",
          any("/control-rebind" in s for s in SVC.seen[before:]), SVC.seen[before:])


def t_public_urlopen_connects_to_the_checked_address():
    """When the answer is allowed, the connection goes to exactly the
    address that was checked - looked up once, not twice."""
    import socket as _socket
    import urllib.request
    port = SVC.base.rsplit(":", 1)[1]
    fake = _Rebinding("feed.ok.example", ["127.0.0.1", "10.9.9.9"])
    real_private = LH._is_private
    # Loopback stands in for "a public address" here, since a test cannot
    # reach the internet; the second answer would be private.
    LH._is_private = lambda ip: str(ip) != "127.0.0.1"
    _socket.getaddrinfo = fake
    before = len(SVC.seen)
    try:
        with LH.public_urlopen(urllib.request.Request(
                f"http://feed.ok.example:{port}/checked"), 5) as r:
            r.read()
        got = "fetched"
    except Exception as exc:
        got = f"{type(exc).__name__}: {exc}"
    finally:
        _socket.getaddrinfo = fake.original
        LH._is_private = real_private
    check("an allowed answer is fetched", got == "fetched", got)
    check("... from the address that was checked", any("/checked" in s
                                                      for s in SVC.seen[before:]))
    check("... with ONE lookup for the connection", fake.calls == 1, fake.calls)
    opener = LH.public_opener()
    check("public_opener has no proxy handler",
          not any(isinstance(h, urllib.request.ProxyHandler) for h in opener.handlers))


def t_news_and_page_watch_fetch_through_public_urlopen():
    """Read from the source, like SITES above: the two fetches of an address
    the owner typed must use the connection-time check."""
    for fname, fn in (("jarvis_news.py", "_default_fetch"),
                      ("jarvis_tellme.py", "_default_page_fetch")):
        tree = ast.parse((BACKEND / fname).read_text(encoding="utf-8"))
        node = next((n for n in ast.walk(tree)
                     if isinstance(n, ast.FunctionDef) and n.name == fn), None)
        calls = [ast.unparse(c.func) for c in ast.walk(node or ast.Module(body=[]))
                 if isinstance(c, ast.Call)]
        check(f"{fname} {fn}() opens through LH.public_urlopen, and nothing else",
              "LH.public_urlopen" in calls
              and not any(c.endswith(("urlopen", "build_opener")) and c != "LH.public_urlopen"
                          for c in calls), calls)


if __name__ == "__main__":
    for fn in (t_the_trap_is_real, t_every_call_site_skips_the_proxy,
               t_the_redirect_refusal_survived, t_the_helper_itself,
               t_no_call_site_goes_back_to_plain_urllib,
               t_private_fetch_problem, t_private_fetch_problem_checks_every_resolved_address,
               t_an_ipv4_mapped_dns_answer_is_judged_as_ipv4,
               t_public_urlopen_checks_the_address_it_connects_to,
               t_public_urlopen_connects_to_the_checked_address,
               t_news_and_page_watch_fetch_through_public_urlopen):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    sys.exit(1 if FAILED else 0)
