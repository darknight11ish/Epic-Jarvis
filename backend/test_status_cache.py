"""DEF-002: /api/status answers from a cache, never by probing on the caller's thread.

    python3 test_status_cache.py

WHY THIS EXISTS. `/api/status` ran three or four live upstream probes inline on
every request - `_reachable(JARVIS/health)`, `_http_json(JARVIS/v1/models)`,
`_reachable(OLLAMA/api/tags)` and `_reachable(PROXY/health)` - and each carries
its own 1.5-2.0 s timeout. The register (`docs/DEFECT-REGISTER.md`,
`docs/defect-register.tsv`, DEF-002) has the measurement: **4,598 ms for
/api/status against 9 ms for /api/pending**, which is only a database read. The
HUD's own status card therefore paid seconds for facts that had not changed.

The fix is a shape, not a speed-up: one daemon thread does the probing every
`_STATUS_POLL_SECONDS`, and the route returns what the last poll found. The
local half of the payload - the config read, the budget, the lanes - stays live,
because those are the parts a person has just changed.

WHAT THIS CHECKS. Two things that must both hold, and each one bites:

  1. **No probe call is left inside the route**, in this repository's copy AND in
     the whole patch stack's (`_stack.stand_in`). A future edit that reaches for
     `_reachable()` in the handler again is the regression this is for.
  2. **The route does not touch the network when the cache is warm.** Proven
     with counters on `_reachable`/`_http_json`, not by reading the clock: a
     timing assertion would pass on a fast machine with the probes still there.

It also pins that `?force=1` re-probes, and that importing this module does NOT
start the poller - about twenty suites import it, and one that quietly began
reaching for a network would be a trap for whoever runs the suite offline.
"""
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
HUD = REPO / "jarvis-backend" / "jarvis_hud.py"

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(("ok    " if cond else "FAIL  ") + name
          + (("\n      " + str(detail)) if (detail and not cond) else ""))


def route_block(text: str, marker='if path == "/api/status":'):
    """The /api/status handler's own words, from its `if` to the 404 that ends do_GET."""
    start = text.index(marker)
    end = text.index("return self._send(404", start)
    return text[start:end]


class Fake:
    """Just enough of a BaseHTTPRequestHandler for the /api/status branch."""

    def __init__(self, path):
        self.path = path
        self._headers_sent = False
        self.headers = {}
        self.client_address = ("127.0.0.1", 5)
        self.sent = []

    def _send(self, code, obj):
        self.sent.append((code, obj))
        return code, obj


def main() -> int:
    if not HUD.is_file():
        print("skip  jarvis-backend/jarvis_hud.py is not here")
        return 0

    base = HUD.read_text(encoding="utf-8")
    block = route_block(base)

    # ---- 1. no probe call is left in the route, in either copy --------------
    check("this repository's /api/status makes no _reachable() call",
          "_reachable(" not in block,
          "the route is probing inline again - that is the 4,598 ms DEF-002 is about")
    check("... and no _http_json() call either",
          "_http_json(" not in block,
          "the route is probing inline again")
    check("... it reads the poller's cache instead",
          "_STATUS_CACHE" in block and "_status_poll_once()" in block,
          "the route does not read _STATUS_CACHE / _status_poll_once")
    check("... and ?force=1 is still a way to ask for a probe right now",
          "force" in block,
          "?force=1 was dropped")
    check("... and the response keys are unchanged",
          all(f'"{k}"' in block for k in
              ("routing", "jarvis_injects_memory", "budget", "jarvis", "ollama",
               "proxy", "models", "lanes", "default_model", "tools")),
          "the payload lost a key another client reads")

    # ---- the shipped base IS what the owner runs ---------------------------
    # `_stack.stand_in` is a fragment chain, not a whole file: it holds what the
    # patches write plus the pre-images they had to invent, so the route is not
    # in it. What makes the words above the INSTALLED words is that no patch has
    # a hunk on this route - checked here, because the day one does, the caching
    # property has to be re-proven against the patched text.
    touching = [p.name for p in sorted((REPO / "backend").glob("*.patch"))
                if any(line.rstrip().endswith('if path == "/api/status":')
                       for line in p.read_text(encoding="utf-8", errors="replace").splitlines())]
    check("no patch rewrites the /api/status route, so the shipped base is the installed one",
          not touching,
          f"these patches now carry a hunk on the route: {touching} - "
          "re-check that the cached route survived them")

    check("the poller is started from main(), and only from main()",
          base.count("_status_start_poller()") == 2,
          "expected exactly two mentions: the def and the call in main(); "
          f"found {base.count('_status_start_poller()')}")

    # ---- 2. warm cache means no network on the request thread ---------------
    sys.path.insert(0, str(HUD.parent))
    import jarvis_hud as mod

    check("importing the module does NOT start the poller thread",
          not any(t.name == "jarvis-status-poll" for t in threading.enumerate()),
          "a suite that imports this file must not find a thread reaching for a network")

    if not (hasattr(mod, "_STATUS_CACHE") and hasattr(mod, "_status_poll_once")):
        check("the module carries the poller's cache and its probe helper",
              False,
              "jarvis_hud has no _STATUS_CACHE/_status_poll_once, so the route is "
              "still probing inline - which is the 4,598 ms DEF-002 is about")
        print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
        print("failed: " + ", ".join(FAILED))
        return 1

    calls = {"reachable": 0, "http": 0}

    def fake_reachable(url, timeout=1.5):
        calls["reachable"] += 1
        return True

    def fake_http_json(url, timeout=2.0):
        calls["http"] += 1
        return {"data": [{"id": "qwen3.5:9b"}, {"id": "qwen3-vl:4b"}]}

    real_reachable, real_http = mod._reachable, mod._http_json
    real_origin, real_token = mod._origin_ok, mod._token_ok
    try:
        mod._reachable, mod._http_json = fake_reachable, fake_http_json
        mod._origin_ok = lambda _self: True
        mod._token_ok = lambda _self: True
        mod._STATUS_CACHE.clear()

        mod._status_poll_once()
        first = dict(calls)
        check("one poll probes the three services (and the model list once)",
              first == {"reachable": 3, "http": 1}, first)

        mod._STATUS_CACHE.clear()
        mod._STATUS_CACHE.update({"jarvis": True, "ollama": False, "proxy": True,
                                  "models": ["cached-model"], "polled_at": 1.0})
        calls.update(reachable=0, http=0)
        h = Fake("/api/status")
        mod.Handler.do_GET(h)
        check("a warm cache answers /api/status with NO network call at all",
              calls == {"reachable": 0, "http": 0}, calls)
        check("... and the answer came from the cache, not the services",
              h.sent and h.sent[0][0] == 200
              and h.sent[0][1]["models"] == ["cached-model"]
              and h.sent[0][1]["ollama"] is False
              and h.sent[0][1]["proxy"] is True,
              h.sent)

        calls.update(reachable=0, http=0)
        h2 = Fake("/api/status?force=1")
        mod.Handler.do_GET(h2)
        check("?force=1 probes again, on purpose",
              calls == {"reachable": 3, "http": 1}, calls)
        check("... and the forced answer is the fresh one",
              h2.sent and h2.sent[0][1]["models"] == ["qwen3.5:9b", "qwen3-vl:4b"],
              h2.sent)

        mod._STATUS_CACHE.clear()
        calls.update(reachable=0, http=0)
        h3 = Fake("/api/status")
        mod.Handler.do_GET(h3)
        check("an empty cache (no poller has run) still answers, live",
              h3.sent and h3.sent[0][0] == 200 and calls["reachable"] == 3, calls)

        def all_down(url, timeout=1.5):
            calls["reachable"] += 1
            return False

        mod._reachable = all_down
        mod._STATUS_CACHE.clear()
        calls.update(reachable=0, http=0)
        mod._status_poll_once()
        check("a service that is down is reported down, and its model list is not asked for",
              mod._STATUS_CACHE["jarvis"] is False and calls["http"] == 0,
              dict(mod._STATUS_CACHE))

        # ---- D12: loopback CONNECT timeout + concurrent status probes ------
        # A dead loopback port used to hold the caller for the full 1.5 s
        # read timeout (measured 3.1 s for two dead services). The connect is
        # capped at 0.20 s; the read timeout is unchanged, so a slow-but-alive
        # local service is still given its normal time. The three independent
        # probes run together, so the whole forced poll stays under 250 ms.
        real_conn = mod.socket.create_connection
        real_open = mod.urllib.request.urlopen
        connects, opens = [], []
        mod._reachable = real_reachable       # the real helper, with a fake socket
        class _Sock:
            def close(self):
                return None

        def dead_conn(addr, timeout=None):
            connects.append((addr, timeout))
            time.sleep(timeout or 0)
            raise TimeoutError("loopback test")

        def dead_open(req, timeout=None):
            opens.append(timeout)
            raise mod.urllib.error.URLError("test down")
        mod.socket.create_connection = dead_conn
        mod.urllib.request.urlopen = dead_open
        try:
            started = time.perf_counter()
            ok = mod._reachable("http://127.0.0.1:8000/health")
            elapsed = time.perf_counter() - started
            check("a loopback probe uses a 0.20 s socket CONNECT timeout",
                  connects and connects[-1][0] == ("127.0.0.1", 8000)
                  and connects[-1][1] == 0.20, connects)
            check("... a dead loopback probe returns in under 250 ms",
                  ok is False and elapsed < 0.25, elapsed)
            connects.clear()
            opens.clear()
            mod._reachable("http://example.invalid/health", timeout=1.5)
            check("a non-loopback probe does NOT use the loopback connect path",
                  connects == [], connects)
            check("... and its own HTTP timeout is unchanged",
                  opens and opens[-1] == 1.5, opens)
        finally:
            mod.socket.create_connection = real_conn
            mod.urllib.request.urlopen = real_open

        real_slow_reach = mod._reachable

        def slow_loopback(url, timeout=1.5):
            if "127.0.0.1" in url or "localhost" in url:
                time.sleep(0.20)
                return False
            return True
        mod._reachable = slow_loopback
        mod._STATUS_CACHE.clear()
        started = time.perf_counter()
        mod._status_poll_once()
        elapsed = time.perf_counter() - started
        check("the three loopback probes run concurrently, so ?force=1's "
              "probe stays under 250 ms", elapsed < 0.25, elapsed)
        mod._reachable = real_slow_reach
    finally:
        mod._reachable, mod._http_json = real_reachable, real_http
        mod._origin_ok, mod._token_ok = real_origin, real_token
        mod._STATUS_CACHE.clear()

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
