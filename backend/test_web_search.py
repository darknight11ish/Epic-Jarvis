"""test_web_search.py - web search with a choice of six providers.

    python3 backend/test_web_search.py

The owner's decisions of 2026-09-25 (CLAUDE.md, "Web search with a choice of
providers" and "When a search asks first"; docs/JARVIS-API.md section
23). What it proves, with local stand-in servers on 127.0.0.1 only - nothing
here reaches the internet, and nothing reaches a real SearXNG, DuckDuckGo,
Exa, Tavily, Brave or DeepSeek:

  - the six "why use this one" lines: said plainly (JSON off by default,
    Docker, the internet address still seen, never "anonymous"), Whoogle
    left out with its reason, and the SAME words in the desktop's and the
    phone's copies;
  - plan() opens no socket; a search whose words hold a password or key is
    refused outright, naming the kind and never the value;
  - SearXNG: results normalised and capped, through NO proxy (a fake proxy
    sees nothing), redirects refused, a huge answer refused; not running and
    JSON off (403) are said plainly with an offer to switch - and NOTHING is
    sent to any other provider (no silent fallback);
  - its address: this PC or the owner's own networks only;
  - Exa, Tavily and Brave: the key goes in its own header to its own address
    only, never after a redirect, never into a plan, a card, an error, an
    answer or the log (the scrubber hides it by value); no key, a refused
    key, credits used up and rate limits each said plainly;
  - DeepSeek (added 2026-10-23, opt-in): its POST body and Bearer key reach
    api.deepseek.com only; the answer's summary/snippet become the result,
    a null date is harmless, an empty `results` list is a normal "found
    nothing", a 401/402/429/408/5xx each gets its own plain words, its 128
    character query bound refuses before any socket, and no key is a
    readable refusal with no socket;
  - the keys: Credential Manager names match the desktop's, no route takes a
    key, and the owner's command line never echoes one;
  - DuckDuckGo: ddgs with backend="duckduckgo" ONLY; a ddgs without that
    engine is refused before anything is sent; not installed says the pip
    line; searches are paced;
  - the settings: defaults, a damaged file fails closed, one change per
    request, "Ask before every web search" on at once and off only through
    ONE approval card;
  - the chat loop: no card for a search straight from the owner's own typed
    question; a card with the EXACT words after email/files/notes/outside
    text, for a pasted message, for the app's own text, and with "ask every
    time" on; only a person's yes runs it; "never" switches it off; the card
    limit holds; results are outside text and mark the turn;
  - saved memories (the owner's decision of 2026-09-25, after the creativity
    audit): a pinned or recalled fact alone no longer asks - a card only
    when the search words repeat a fact in the turn (a word, a number, a
    name or nickname from the names layer that the owner did not say
    themselves) or a sensitive fact was used; the card names the fact, but
    never a sensitive fact's own words; when the check cannot run, it asks;
  - "which search should I use?" answered without the model, from the same
    words;
  - web-search.patch applies to what the earlier patches wrote, reverses,
    and its blocks run.
"""
from __future__ import annotations

import http.server
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import types
import urllib.request
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-websearch-"))
# Before anything imports jarvis_framework: its CONFIG_DIR is read once.
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

require_shipped("jarvis_search.py", "jarvis_agent.py", "jarvis_quick.py",
                "jarvis_local_http.py", "jarvis_scrub.py", "rebuilt/jarvis_router.py")

if str(HERE / "rebuilt") not in sys.path:
    sys.path.append(str(HERE / "rebuilt"))

import jarvis_search as WS  # noqa: E402
import jarvis_agent as AG  # noqa: E402
import jarvis_quick as Q  # noqa: E402
import jarvis_scrub  # noqa: E402
import _stack  # noqa: E402

AG._publish_step = lambda step: None
AG._record_chain = lambda steps: None

PASSED, FAILED = [], []
SKIPPED = []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: printed as `skip`, counted on its own,
    never as a pass. (It used to be check("SKIP - ...", True) - a condition of
    the constant True, so it printed as a pass and was counted as one.)"""
    SKIPPED.append(why)
    print(f"skip  {why}")


# Fake keys, built by concatenation so nothing here is shaped like a real one.
FAKE_TAVILY = "tv" + "ly-" + "fake" + "0123456789ab"
FAKE_EXA = "exa" + "-fake-" + "0123456789abcdef"
FAKE_BRAVE = "BS" + "Afake" + "0123456789abcdef"
FAKE_DEEPSEEK = "ds" + "-fake-" + "0123456789abcdef"
FAKE_AWS = "AK" + "IA" + "Q" * 16


def reset(**settings):
    """A fresh settings file (or none), fresh card state, no fakes."""
    WS._reset_for_tests()
    WS._HTTP = None
    WS._DDGS_MODULE = None
    p = WS.settings_path()
    if p.exists():
        p.unlink()
    if settings:
        p.parent.mkdir(parents=True, exist_ok=True)
        base = {"provider": "searxng", "searxng_url": WS.DEFAULT_SEARXNG_URL,
                "ask_every_time": False}
        base.update(settings)
        p.write_text(json.dumps(base), encoding="utf-8")


class FakeStore:
    """Credential Manager, in memory: target -> value."""
    DATA: dict = {}

    def __init__(self, target):
        self.target = target

    def read(self):
        return FakeStore.DATA.get(self.target)

    def write(self, value):
        FakeStore.DATA[self.target] = value

    def delete(self):
        FakeStore.DATA.pop(self.target, None)


WS._STORE_FACTORY = FakeStore


class NoSockets:
    """Every way out of this process made to fail, and counted."""

    def __enter__(self):
        self.tried = []
        self.saved = (socket.socket.connect, socket.create_connection)

        def refuse(*a, **k):
            self.tried.append(a[:1])
            raise AssertionError("a socket was opened")
        socket.socket.connect = refuse
        socket.create_connection = refuse
        return self

    def __exit__(self, *exc):
        socket.socket.connect, socket.create_connection = self.saved


class StandIn:
    """A local HTTP server on 127.0.0.1 answering from a script:
    path-prefix -> (status, headers, body). Records every request."""

    def __init__(self, routes):
        self.routes = routes
        self.seen = []
        outer = self

        class H(http.server.BaseHTTPRequestHandler):
            def _answer(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(n) if n else b""
                outer.seen.append({"method": self.command, "path": self.path,
                                   "headers": {k.lower(): v for k, v in self.headers.items()},
                                   "body": body})
                for prefix, (status, headers, out) in outer.routes.items():
                    if self.path.startswith(prefix) or prefix == "*":
                        self.send_response(status)
                        for k, v in headers.items():
                            self.send_header(k, v)
                        self.send_header("Content-Length", str(len(out)))
                        self.end_headers()
                        self.wfile.write(out)
                        return
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()

            do_GET = do_POST = _answer

            def log_message(self, *a):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.server.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def searxng_json(n=7, extra=None):
    rows = [{"url": f"https://example.org/{i}", "title": f"Result <b>{i}</b>",
             "content": "word " * 200, "engine": "x"} for i in range(n)]
    rows.insert(0, {"url": "javascript:alert(1)", "title": "bad", "content": "bad"})
    doc = {"query": "q", "results": rows}
    doc.update(extra or {})
    return json.dumps(doc).encode()


# --------------------------------------------------------------------------
#   1. The words
# --------------------------------------------------------------------------

def _sentences(text):
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]


def t_the_why_lines():
    check("six providers, SearXNG the default",
          WS.PROVIDERS == ("searxng", "duckduckgo", "exa", "tavily", "brave", "deepseek")
          and WS.DEFAULT_PROVIDER == "searxng" and WS.DEFAULT_SEARXNG_URL == "http://127.0.0.1:8888")
    for pid in WS.PROVIDERS:
        line = WS.WHY[pid]
        check(f"{pid}: one or two sentences", 1 <= len(_sentences(line)) <= 2, line)
        check(f"{pid}: never called anonymous or private", not re.search(
            r"anonym|untrack|no one (?:can )?see|nobody (?:can )?see", line, re.I), line)
    s = WS.WHY["searxng"]
    check("SearXNG: Docker, JSON to switch on, and the engines still see the address",
          "Docker" in s and "JSON" in s and "internet address" in s and "no key" in s)
    d = WS.WHY["duckduckgo"]
    check("DuckDuckGo: ddgs, no official way in, can break, still sees the address",
          "ddgs" in d and "no official way in" in d and "stop working" in d
          and "internet address" in d)
    t = WS.WHY["tavily"]
    check("Tavily: 1,000 free credits a month, a key, sees the searches",
          "1,000" in t and "key" in t and "sees what you search" in t)
    e = WS.WHY["exa"]
    check("Exa: by meaning, passages, about $10 a month, no payment card, a key, sees the searches",
          "meaning" in e and "passages" in e and "$10" in e and "no payment card" in e
          and "key" in e and "sees what you search" in e)
    b = WS.WHY["brave"]
    check("Brave: about $5 a month, and says plainly that a card is charged past it",
          "$5" in b and "payment card that is charged" in b and "key" in b
          and "sees what you search" in b, b)
    d = WS.WHY["deepseek"]
    check("DeepSeek: $0.75 for 1,000 searches, empty searches not charged, a key",
          "$0.75" in d and "1,000" in d and "not charged" in d and "key" in d
          and "sees what you search" in d, d)
    check("DeepSeek is opt-in, needs a key, and its label says so",
          "deepseek" in WS.NEEDS_KEY and WS.LABEL["deepseek"] ==
          "DeepSeek web search (needs a key)"
          and WS.KEY_TARGETS["deepseek"] == "Jarvis Backend/DeepSeek Search key"
          and WS.KEY_WHERE["deepseek"].startswith("https://platform.deepseek.com/api_keys"))
    w = WS.LEFT_OUT[0]
    check("Whoogle is left out, and says why (Google, 2025)",
          w["id"] == "whoogle" and "2025" in w["why"] and "JavaScript" in w["why"])
    check("only Whoogle is left out", [x["id"] for x in WS.LEFT_OUT] == ["whoogle"])


def _literal_forms(text: str) -> list:
    """How `text` is written as one string literal in JS and in Kotlin."""
    js = json.dumps(text, ensure_ascii=False)
    kt = js.replace("$", "\\$")
    return [js, kt]


def t_both_apps_say_the_same_words():
    desk = (REPO / "jarvis-desktop" / "src" / "web-search.js").read_text(encoding="utf-8")
    phone = (REPO / "jarvis-client" / "app" / "src" / "main" / "java" / "com" / "jarvis"
             / "client" / "net" / "WebSearch.kt").read_text(encoding="utf-8")
    words = dict(("why " + p, WS.WHY[p]) for p in WS.PROVIDERS)
    words.update({"label " + p: WS.LABEL[p] for p in WS.PROVIDERS})
    words.update({"whoogle": WS.LEFT_OUT[0]["why"],
                  "default why": WS.DEFAULT_WHY,
                  "ask label": WS.ASK_EVERY_TIME_LABEL, "ask detail": WS.ASK_EVERY_TIME_DETAIL,
                  "enabled label": WS.ENABLED_LABEL, "enabled detail": WS.ENABLED_DETAIL,
                  "key entry": WS.KEY_ENTRY})
    for name, text in words.items():
        js, kt = _literal_forms(text)
        check(f"the desktop's web-search.js has the PC's {name} word for word", js in desk, text)
        check(f"the phone's WebSearch.kt has the PC's {name} word for word", kt in phone, text)
    for name, body in (("desktop", desk), ("phone", phone)):
        check(f"the {name} offers the six in the PC's order",
              re.search(r'"searxng",\s*"duckduckgo",\s*"exa",\s*"tavily",\s*"brave",'
                        r'\s*"deepseek"\s*[\])]', body) is not None)


# --------------------------------------------------------------------------
#   2. The plan: no socket, and no secret
# --------------------------------------------------------------------------

def t_plan_opens_no_socket_and_refuses_a_secret():
    reset()
    with NoSockets() as ns:
        p = WS.plan("best walking boots 2026")
        text = WS.describe(p)
    check("plan() and describe() open no socket", not ns.tried)
    check("the card shows the exact words and where they go",
          "“best walking boots 2026”" in text and "127.0.0.1:8888" in text
          and "If you say no" in text, text)
    p = WS.plan(f"why does my key {FAKE_AWS} not work")
    check("search words holding a key are refused outright", p.state == "secret"
          and "an AWS access key" in p.problem, p.problem)
    check("... naming the kind, never the value (nor its first letters)",
          FAKE_AWS not in p.problem and FAKE_AWS[:6] not in p.problem, p.problem)
    out = WS.run(p, approved=True)
    check("... and run() sends nothing for it", out["ok"] is False and out["state"] == "secret")
    FakeStore.DATA[WS.KEY_TARGETS["tavily"]] = FAKE_TAVILY
    WS._key("tavily")                           # registers it with the scrubber
    p = WS.plan(f"is {FAKE_TAVILY} still valid")
    check("a key this PC holds, by value, is refused too", p.state == "secret"
          and FAKE_TAVILY not in p.problem, p.problem)
    check("empty and over-long words send nothing",
          WS.plan("   ").problem and WS.plan("x " * 200).problem)
    check("control characters are taken out of the words",
          WS.plan("a\x00b\nc").query == "a b c", WS.plan("a\x00b\nc").query)
    check("not approved: nothing is sent", WS.run(WS.plan("x"), approved=False)["ok"] is False)


# --------------------------------------------------------------------------
#   3. SearXNG
# --------------------------------------------------------------------------

def t_searxng_results_no_proxy_no_redirect():
    srv = StandIn({"/search": (200, {"Content-Type": "application/json"}, searxng_json())})
    proxy = StandIn({"*": (200, {}, b"{}")})
    reset(searxng_url=srv.url)
    saved = {k: os.environ.get(k) for k in ("HTTP_PROXY", "http_proxy", "NO_PROXY", "no_proxy")}
    os.environ["HTTP_PROXY"] = os.environ["http_proxy"] = proxy.url
    os.environ.pop("NO_PROXY", None)
    os.environ.pop("no_proxy", None)
    try:
        out = WS.run(WS.plan("walking boots"), approved=True)
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    check("SearXNG answers: ok, results", out.get("ok") is True, out)
    r = out.get("results") or []
    check(f"at most {WS.MAX_RESULTS} results, the javascript: link dropped",
          len(r) == WS.MAX_RESULTS and all(x["url"].startswith("https://") for x in r), r)
    check("titles lose their tags, snippets are cut to length",
          r and r[0]["title"] == "Result 0" and len(r[0]["snippet"]) <= WS.SNIPPET_CHARS, r[:1])
    check("the request went straight to SearXNG, with format=json",
          len(srv.seen) >= 2 and srv.seen[0]["path"] == "/"
          and any("format=json" in r["path"] and "walking+boots" in r["path"]
                  for r in srv.seen[1:]), srv.seen)
    check("the machine's proxy saw nothing (jarvis_local_http, no proxy)", not proxy.seen,
          proxy.seen)
    proxy.close()
    srv.close()
    # A redirect is not followed.
    target = StandIn({"*": (200, {}, searxng_json())})
    srv = StandIn({"/search": (302, {"Location": target.url + "/search?q=x"}, b"")})
    reset(searxng_url=srv.url)
    out = WS.run(WS.plan("x"), approved=True)
    check("a redirect is refused, never followed", out["ok"] is False and not target.seen,
          (out, target.seen))
    target.close()
    srv.close()
    # A huge answer is refused.
    srv = StandIn({"/search": (200, {}, b"{\"results\": [" + b" " * (WS.MAX_BODY + 10) + b"]}")})
    reset(searxng_url=srv.url)
    out = WS.run(WS.plan("x"), approved=True)
    check("an answer over the size cap is refused", out["ok"] is False and "KB" in out["error"],
          out)
    srv.close()


def t_searxng_down_says_so_and_never_falls_back():
    tavily = StandIn({"*": (200, {}, b'{"results": []}')})
    WS.TAVILY_URL_SAVED = WS.TAVILY_URL
    WS.TAVILY_URL = tavily.url + "/search"
    ddg_calls = []
    WS._DDGS_MODULE = None
    fake = fake_ddgs(ddg_calls)
    try:
        reset(searxng_url=f"http://127.0.0.1:{free_port()}")
        WS._DDGS_MODULE = fake
        FakeStore.DATA[WS.KEY_TARGETS["tavily"]] = FAKE_TAVILY
        out = WS.run(WS.plan("walking boots"), approved=True)
        check("SearXNG not running: said plainly", out["ok"] is False
              and out["state"] == "not_running" and "isn't running" in out["error"], out)
        check("... with an offer to switch to DuckDuckGo", "DuckDuckGo" in out.get("offer", ""),
              out)
        check("... and NOTHING was sent anywhere else (no silent fallback)",
              not ddg_calls and not tavily.seen, (ddg_calls, tavily.seen))
        told = WS.tool_result(out)
        check("the model is told to say it and not to search another way",
              "Do not try to search another way" in told["tell_the_owner"]
              and "Switch web search to DuckDuckGo?" in told["error"], told)
        srv = StandIn({"/search": (403, {}, b"<h1>Forbidden</h1>")})
        reset(searxng_url=srv.url)
        WS._DDGS_MODULE = fake
        out = WS.run(WS.plan("walking boots"), approved=True)
        check("JSON output off (403): said plainly, with the fix", out["state"] == "json_off"
              and "settings.yml" in out["error"] and "json" in out["error"], out)
        check("... still nothing sent elsewhere", not ddg_calls and not tavily.seen)
        srv.close()
    finally:
        WS.TAVILY_URL = WS.TAVILY_URL_SAVED
        tavily.close()
        WS._DDGS_MODULE = None


class StalledPort:
    """A local port that ACCEPTS and then says nothing: a cold Docker Desktop
    proxy on the owner's PC. The connection is held open and never written to,
    so only the client's own timeout can end the wait."""

    def __init__(self):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(8)
        self.url = f"http://127.0.0.1:{self.sock.getsockname()[1]}"
        self.conns = []
        self._stop = False
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        self.sock.settimeout(0.2)
        while not self._stop:
            try:
                c, _ = self.sock.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            self.conns.append(c)          # accepted, never answered

    def close(self):
        self._stop = True
        for c in self.conns:
            try:
                c.close()
            except Exception:
                pass
        try:
            self.sock.close()
        except Exception:
            pass


def t_a_stalled_searxng_is_reported_fast_and_honestly():
    """The owner's morning: Docker Desktop is still starting, its port accepts
    the connection and then answers nothing. Before the bounded preflight this
    waited TIMEOUT (15 s) inside the model turn. It must be the SAME honest
    "isn't running" words, in well under 2 s, with nothing sent anywhere else
    and the model told to say it rather than guess."""
    stalled = StalledPort()
    ddg_calls = []
    WS._DDGS_MODULE = fake_ddgs(ddg_calls)
    reset(searxng_url=stalled.url)
    try:
        started = time.monotonic()
        out = WS.run(WS.plan("walking boots"), approved=True)
        took = time.monotonic() - started
        check("a stalled local port is reported in well under 2 s",
              took < 2.0, f"{took:.2f}s")
        check("... with the same plain words as a closed one", out.get("ok") is False
              and out.get("state") == "not_running"
              and "SearXNG isn't running on this PC" in out.get("error", "")
              and "Start it in Docker Desktop" in out.get("error", ""), out)
        check("... and NOTHING was tried anywhere else (no silent fallback)",
              not ddg_calls, ddg_calls)
        told = WS.tool_result(out)
        check("... and the model is told to say it, never to guess or search another way",
              "Do not try to search another way" in told["tell_the_owner"], told)
    finally:
        WS._DDGS_MODULE = None
        stalled.close()
    # A closed port is the same answer, and fast for the same reason.
    reset(searxng_url=f"http://127.0.0.1:{free_port()}")
    started = time.monotonic()
    out = WS.run(WS.plan("walking boots"), approved=True)
    took = time.monotonic() - started
    check("a closed local port is the same honest answer, just as fast",
          out.get("state") == "not_running" and took < 2.0
          and "isn't running" in out.get("error", ""), (took, out))
    # A healthy SearXNG is unchanged: the preflight answers at once and the
    # real search keeps its own budget and returns results.
    srv = StandIn({"/search": (200, {"Content-Type": "application/json"}, searxng_json())})
    reset(searxng_url=srv.url)
    try:
        out = WS.run(WS.plan("walking boots"), approved=True)
        check("a healthy SearXNG still searches normally - the preflight costs it nothing",
              out.get("ok") is True and len(out.get("results") or []) > 0, out)
        check("... the preflight asked the address first, then the real search",
              len(srv.seen) >= 2 and srv.seen[0]["path"] == "/"
              and any("format=json" in r["path"] for r in srv.seen[1:]), srv.seen)
    finally:
        srv.close()
    # readiness() itself still opens NO socket: the bounded ask is the SEND
    # step, never the settings screen's own report.
    with NoSockets() as ns:
        state, said = WS.readiness("searxng")
    check("readiness() still opens no socket - the bounded ask belongs to the send",
          state == "" and not ns.tried, (state, said, ns.tried))


def t_searxng_answering_with_nothing_is_never_a_silent_empty_answer():
    """SearXNG up, every engine behind it failed: that must be SAID, not handed
    back as an empty result list.

    2026-10-13, on the owner's own PC: DNS inside the Docker container was dead,
    all five engines were timing out, SearXNG answered HTTP 200 with
    "results": [], and Jarvis answered every research question with nothing at
    all - and readiness("searxng") still said nothing stood in the way."""
    ddg_calls = []
    WS._DDGS_MODULE = fake_ddgs(ddg_calls)

    body = json.dumps({"query": "q", "results": [],
                       "unresponsive_engines": [["wikipedia", "timeout"],
                                                ["brave", "too many requests"]]}).encode()
    srv = StandIn({"/search": (200, {"Content-Type": "application/json"}, body)})
    reset(searxng_url=srv.url)
    try:
        out = WS.run(WS.plan("iceland population"), approved=True)
        check("zero results WITH failed engines is an error, not a silent empty answer",
              out.get("state") == "engines_down", out)
        said = out.get("error") or ""
        check("... it names the engines and what each of them said",
              "wikipedia (timeout)" in said and "brave (too many requests)" in said, said)
        check("... and it says this is the container's own network, not the search words",
              "DNS" in said and "Nothing was sent to another provider" in said, said)
        check("... and nothing was sent to DuckDuckGo instead (no silent fallback)",
              not ddg_calls, ddg_calls)
    finally:
        srv.close()

    # CONTROL 1 - the same empty list with every engine fine is a real
    # "nothing matched those words", and must stay a normal answer.
    srv = StandIn({"/search": (200, {"Content-Type": "application/json"},
                                json.dumps({"query": "q", "results": [],
                                            "unresponsive_engines": []}).encode())})
    reset(searxng_url=srv.url)
    try:
        out = WS.run(WS.plan("zzqqxx"), approved=True)
        check("zero results with every engine fine is still a normal empty answer",
              out.get("state") != "engines_down", out)
    finally:
        srv.close()

    # CONTROL 2 - results present: unchanged success.
    srv = StandIn({"/search": (200, {"Content-Type": "application/json"}, searxng_json(3))})
    reset(searxng_url=srv.url)
    try:
        out = WS.run(WS.plan("walking boots"), approved=True)
        check("results present is still a success",
              bool(out.get("results")) and out.get("state") != "engines_down", out)
    finally:
        srv.close()
        WS._DDGS_MODULE = None


def t_the_searxng_address_is_the_owners_own():
    ok = ["http://127.0.0.1:8888", "http://localhost:8080", "http://192.168.1.20:8888",
          "http://nas.local:8888/searxng", "http://100.101.102.103:8888",
          "https://searx.tailnet-abc.ts.net"]
    bad = ["http://example.com:8888", "https://searx.be", "http://8.8.8.8:8888",
           "ftp://127.0.0.1", "http://me:pw@127.0.0.1:8888", "http://127.0.0.1:8888/?q=x",
           "http://127.0.0.1:99999", "", "http://127.0.0.1:8888 x",
           "http://3232235777.example.com"]
    for u in ok:
        check(f"allowed: {u}", WS.searxng_url_problem(u) == "", WS.searxng_url_problem(u))
    for u in bad:
        check(f"refused: {u!r}", WS.searxng_url_problem(u) != "")
    reset()
    code, out = WS.handle_settings({"searxng_url": "https://searx.be"})
    check("POST refuses an address on the internet, and saves nothing",
          code == 400 and WS.settings()["searxng_url"] == WS.DEFAULT_SEARXNG_URL, out)
    code, out = WS.handle_settings({"searxng_url": "http://192.168.1.20:8888/"})
    check("... and saves one on the home network", code == 200
          and WS.settings()["searxng_url"] == "http://192.168.1.20:8888", out)
    code, out = WS.handle_settings({"searxng_url": ""})
    check("an empty address puts the default back",
          code == 200 and WS.settings()["searxng_url"] == WS.DEFAULT_SEARXNG_URL)


# --------------------------------------------------------------------------
#   4. The keyed providers: Exa, Tavily, Brave and DeepSeek
# --------------------------------------------------------------------------

def _with_cloud(provider, routes, fn):
    srv = StandIn(routes)
    attr = {"tavily": "TAVILY_URL", "exa": "EXA_URL", "brave": "BRAVE_URL",
            "deepseek": "DEEPSEEK_URL"}[provider]
    suffix = {"brave": "/res/v1/web/search", "deepseek": "/v1/tools/search"}.get(
        provider, "/search")
    saved = getattr(WS, attr)
    setattr(WS, attr, srv.url + suffix)
    try:
        return fn(srv)
    finally:
        setattr(WS, attr, saved)
        srv.close()


def t_tavily_key_goes_only_to_tavily():
    reset(provider="tavily")
    FakeStore.DATA.clear()
    with NoSockets() as ns:
        p = WS.plan("walking boots")
    check("no key: refused before any socket, and says where to add one",
          p.state == "key_missing" and "Settings, Web search" in p.problem and not ns.tried,
          p.problem)
    FakeStore.DATA[WS.KEY_TARGETS["tavily"]] = FAKE_TAVILY
    body = json.dumps({"results": [{"title": "T", "url": "https://t.example/1",
                                    "content": "snippet"}]}).encode()

    def go(srv):
        p = WS.plan("walking boots")
        card = WS.describe(p)
        out = WS.run(p, approved=True)
        return p, card, out, srv.seen
    p, card, out, seen = _with_cloud("tavily", {"/search": (200, {}, body)}, go)
    check("Tavily answers", out.get("ok") and out["results"][0]["url"] == "https://t.example/1",
          out)
    req = seen[0] if seen else {}
    check("the key went as `Authorization: Bearer <key>`, a POST with the words in JSON",
          req.get("method") == "POST" and req["headers"].get("authorization")
          == f"Bearer {FAKE_TAVILY}" and json.loads(req["body"])["query"] == "walking boots",
          req)
    everything = json.dumps([p.as_dict(), card, out])
    check("the key is in no plan, card or answer", FAKE_TAVILY not in everything)
    check("the card says a key goes, and to where", "with your Tavily key" in card
          and "goes to" in card, card)
    for status, state in ((401, "key_refused"), (432, "quota_used"), (433, "quota_used"),
                          (429, "rate_limited"), (500, "failed")):
        out = _with_cloud("tavily", {"/search": (status, {}, b'{"detail": "x"}')},
                          lambda srv: WS.run(WS.plan("x"), approved=True))
        check(f"Tavily {status} -> {state}, said plainly, no key in it",
              out["state"] == state and FAKE_TAVILY not in json.dumps(out), out)
    # A redirect never carries the key.
    target = StandIn({"*": (200, {}, body)})
    out = _with_cloud("tavily", {"/search": (307, {"Location": target.url + "/steal"}, b"")},
                      lambda srv: WS.run(WS.plan("x"), approved=True))
    check("a redirect is refused: the key never reaches another address",
          out["ok"] is False and not target.seen, target.seen)
    target.close()
    # The log scrubber hides it by value.
    WS._key("tavily")
    check("the log scrubber hides the key by value",
          FAKE_TAVILY not in jarvis_scrub.scrub_text(f"sending {FAKE_TAVILY} now"))


def t_exa_key_goes_only_to_exa():
    reset(provider="exa")
    FakeStore.DATA.clear()
    with NoSockets() as ns:
        p = WS.plan("walking boots")
    check("Exa, no key: refused before any socket, and says where to add one",
          p.state == "key_missing" and "No Exa key" in p.problem and not ns.tried, p.problem)
    FakeStore.DATA[WS.KEY_TARGETS["exa"]] = FAKE_EXA
    long_text = "page text " * 400
    body = json.dumps({"results": [
        {"title": "E <b>x</b>", "url": "https://e.example/1", "text": long_text,
         "highlights": ["first useful passage.", "second &amp; last."]},
        {"title": None, "url": "https://e.example/2", "text": long_text},
        {"title": "bad", "url": "javascript:alert(1)", "highlights": ["x"]},
    ] + [{"title": f"n{i}", "url": f"https://e.example/n{i}", "text": "t"} for i in range(9)],
        "requestId": "r"}).encode()

    def go(srv):
        p = WS.plan("walking boots")
        card = WS.describe(p)
        return p, card, WS.run(p, approved=True), srv.seen
    p, card, out, seen = _with_cloud("exa", {"/search": (200, {}, body)}, go)
    r = out.get("results") or []
    check("Exa answers: highlights joined into the snippet, tags and entities cleaned",
          out.get("ok") and r[0] == {"title": "E x", "url": "https://e.example/1",
                                    "snippet": "first useful passage. ... second & last."}, r[:1])
    check("... no highlights: the start of the page text, cut to 300; no title: the link",
          len(r) > 1 and r[1]["title"] == "https://e.example/2"
          and len(r[1]["snippet"]) <= WS.SNIPPET_CHARS and r[1]["snippet"].startswith("page text"),
          r[1:2])
    check(f"... at most {WS.MAX_RESULTS} results, the javascript: link dropped",
          len(r) == WS.MAX_RESULTS and all(x["url"].startswith("https://") for x in r))
    req = seen[0] if seen else {}
    sent = json.loads(req.get("body") or b"{}")
    check("the key went as x-api-key, a POST with query, numResults 5 and highlights",
          req.get("method") == "POST" and req["headers"].get("x-api-key") == FAKE_EXA
          and sent == {"query": "walking boots", "numResults": 5,
                       "contents": {"highlights": True}}, (req.get("headers"), sent))
    check("... and not as Authorization", "authorization" not in req.get("headers", {}))
    check("the key is in no plan, card or answer",
          FAKE_EXA not in json.dumps([p.as_dict(), card, out]))
    check("the card says a key goes, to api.exa.ai's address only", "with your Exa key" in card)
    for status, state in ((401, "key_refused"), (403, "key_refused"), (402, "quota_used"),
                          (429, "rate_limited"), (500, "failed")):
        out = _with_cloud("exa", {"/search": (status, {}, b'{"error": "x"}')},
                          lambda srv: WS.run(WS.plan("x"), approved=True))
        check(f"Exa {status} -> {state}, said plainly, no key in it",
              out["state"] == state and FAKE_EXA not in json.dumps(out), out)
    target = StandIn({"*": (200, {}, body)})
    out = _with_cloud("exa", {"/search": (307, {"Location": target.url + "/steal"}, b"")},
                      lambda srv: WS.run(WS.plan("x"), approved=True))
    check("Exa: a redirect is refused: the key never reaches another address",
          out["ok"] is False and not target.seen, target.seen)
    target.close()
    srv_big = b'{"results": [' + b" " * (WS.MAX_BODY + 10) + b"]}"
    out = _with_cloud("exa", {"/search": (200, {}, srv_big)},
                      lambda srv: WS.run(WS.plan("x"), approved=True))
    check("Exa: an answer over the size cap is refused", out["ok"] is False, out)
    check("the real address is Exa's own, over https", WS.EXA_URL == "https://api.exa.ai/search")
    WS._key("exa")
    check("the log scrubber hides the Exa key by value",
          FAKE_EXA not in jarvis_scrub.scrub_text(f"sending {FAKE_EXA} now"))


def t_brave_key_goes_only_to_brave():
    reset(provider="brave")
    FakeStore.DATA.clear()
    with NoSockets() as ns:
        p = WS.plan("walking boots")
    check("Brave, no key: refused before any socket, and says where to add one",
          p.state == "key_missing" and "No Brave Search key" in p.problem and not ns.tried,
          p.problem)
    FakeStore.DATA[WS.KEY_TARGETS["brave"]] = FAKE_BRAVE
    body = json.dumps({"web": {"results": [{"title": "B <strong>x</strong>",
                                            "url": "https://b.example/1",
                                            "description": "a <strong>b</strong> &amp; c"}]}}).encode()

    def go(srv):
        p = WS.plan("walking boots")
        card = WS.describe(p)
        return p, card, WS.run(p, approved=True), srv.seen
    p, card, out, seen = _with_cloud("brave", {"/res/v1/web/search": (200, {}, body)}, go)
    req = seen[0] if seen else {}
    check("Brave answers, tags and entities cleaned",
          out.get("ok") and out["results"][0] == {"title": "B x", "url": "https://b.example/1",
                                                  "snippet": "a b & c"}, out)
    check("the key went as X-Subscription-Token, a GET with the words and count=5",
          req.get("method") == "GET" and req["headers"].get("x-subscription-token") == FAKE_BRAVE
          and "count=5" in req["path"] and "walking+boots" in req["path"], req)
    check("... and not as Authorization", "authorization" not in req.get("headers", {}))
    check("the Brave key is in no plan, card or answer",
          FAKE_BRAVE not in json.dumps([p.as_dict(), card, out]))
    for status, state in ((401, "key_refused"), (422, "key_refused"), (402, "quota_used"),
                          (429, "rate_limited"), (500, "failed")):
        out = _with_cloud("brave", {"/res/v1/web/search": (status, {}, b"{}")},
                          lambda srv: WS.run(WS.plan("x"), approved=True))
        check(f"Brave {status} -> {state}, no key in it", out["state"] == state
              and FAKE_BRAVE not in json.dumps(out), out)
    out = _with_cloud("brave", {"/res/v1/web/search": (402, {}, b"{}")},
                      lambda srv: WS.run(WS.plan("x"), approved=True))
    check("Brave 402 says more searches would be charged to the card",
          "charged to your card" in out["error"], out["error"])
    target = StandIn({"*": (200, {}, body)})
    out = _with_cloud("brave", {"/res/v1/web/search": (302, {"Location": target.url + "/x"}, b"")},
                      lambda srv: WS.run(WS.plan("x"), approved=True))
    check("Brave: a redirect is refused: the key never reaches another address",
          out["ok"] is False and not target.seen, target.seen)
    target.close()
    check("the real address is Brave's own, over https",
          WS.BRAVE_URL == "https://api.search.brave.com/res/v1/web/search")
    WS._key("brave")
    check("the log scrubber hides the Brave key by value",
          FAKE_BRAVE not in jarvis_scrub.scrub_text(f"sending {FAKE_BRAVE} now"))
    reset(provider="brave")
    check("a saved \"brave\" is simply Brave", WS.settings()["provider"] == "brave"
          and WS.settings()["why"] == "")
    FakeStore.DATA.clear()
    said = []
    rc = WS._main(["key", "brave"], ask_secret=lambda prompt: FAKE_BRAVE, out=said.append)
    check("py -3 jarvis_search.py key brave saves it, and never prints it",
          rc == 0 and FakeStore.DATA.get(WS.KEY_TARGETS["brave"]) == FAKE_BRAVE
          and FAKE_BRAVE not in "\n".join(said), said)


def t_deepseek_parser_errors_and_no_key():
    # 1. No key: a readable refusal, before any socket.
    reset(provider="deepseek")
    FakeStore.DATA.clear()
    with NoSockets() as ns:
        p = WS.plan("walking boots")
        card = WS.describe(p)
        out = WS.run(p, approved=True)
    check("DeepSeek, no key: refused before any socket, and says where to add one",
          p.state == "key_missing" and "No DeepSeek Search key" in p.problem
          and "Settings, Web search" in p.problem and not ns.tried, p.problem)
    check("... the refusal is readable, not a crash, and run() sends nothing",
          out["ok"] is False and out["state"] == "key_missing"
          and "Traceback" not in json.dumps(out), out)
    check("... the refusal names the service and where a key is made, never a key",
          "DeepSeek Search" in card and "platform.deepseek.com/api_keys" in card, card)

    # 2. A recorded answer: two results, one with an RFC3339 date and one null.
    FakeStore.DATA[WS.KEY_TARGETS["deepseek"]] = FAKE_DEEPSEEK
    deepseek_body = json.dumps({"results": [
        {"rerank_score": 2.4, "title": "DS <b>one</b>", "url": "https://ds.example/1",
         "snippet": "short one", "summary": "long summary one", "content": "",
         "site_name": "Example", "site_icon": None,
         "date": "2026-06-01T00:00:00+00:00", "authority": 3},
        {"rerank_score": 1.1, "title": None, "url": "https://ds.example/2",
         "snippet": "short two", "summary": "", "content": "",
         "site_name": None, "site_icon": None, "date": None, "authority": -1},
        {"title": "bad", "url": "javascript:alert(1)", "date": None},
    ]}).encode()

    def go(srv):
        p = WS.plan("walking boots")
        return p, WS.describe(p), WS.run(p, approved=True), srv.seen
    p, card, out, seen = _with_cloud(
        "deepseek", {"/v1/tools/search": (200, {}, deepseek_body)}, go)
    r = out.get("results") or []
    check("DeepSeek answers: tag cleaned, the summary is the snippet, the link kept",
          out.get("ok") and r and r[0] == {"title": "DS one", "url": "https://ds.example/1",
                                          "snippet": "long summary one"}, r[:1])
    check("... a null title falls back to the link, and a null date is harmless",
          len(r) == 2 and r[1] == {"title": "https://ds.example/2",
                                   "url": "https://ds.example/2", "snippet": "short two"}, r)
    check("... the javascript: link is dropped", all(x["url"].startswith("https://") for x in r))
    req = seen[0] if seen else {}
    sent = json.loads(req.get("body") or b"{}")
    check("DeepSeek: a POST to /v1/tools/search with query, count 5, no content",
          req.get("method") == "POST" and req["headers"].get("authorization")
          == f"Bearer {FAKE_DEEPSEEK}" and sent == {"query": "walking boots", "count": 5,
                                                    "need_content": False}, (req, sent))
    check("... and not as any other key header", "x-api-key" not in req.get("headers", {})
          and "x-subscription-token" not in req.get("headers", {}))
    check("the key is in no plan, card or answer",
          FAKE_DEEPSEEK not in json.dumps([p.as_dict(), card, out]))
    check("the card says a key goes, to that address only",
          "with your DeepSeek Search key" in card and "goes to" in card, card)

    # 3. An empty `results` list is a normal search that found nothing.
    out = _with_cloud("deepseek", {"/v1/tools/search": (200, {}, b'{"results": []}')},
                      lambda srv: WS.run(WS.plan("zzqqxx"), approved=True))
    check("DeepSeek: an empty results list is a normal 'found nothing', not an error",
          out.get("ok") is True and out.get("results") == []
          and "found nothing" in out.get("note", ""), out)

    # 4. Every documented error code, in plain words, with no key in the answer.
    for status, state, words in (
            (401, "key_refused", "refused your key"),
            (402, "quota_used", "out of balance"),
            (429, "rate_limited", "too many searches"),
            (408, "timeout", "did not answer in time"),
            (504, "timeout", "did not answer in time"),
            (500, "failed", "problem on its side"),
            (400, "failed", "would not accept those search words")):
        out = _with_cloud("deepseek", {"/v1/tools/search": (status, {}, b'{"error": "x"}')},
                          lambda srv: WS.run(WS.plan("x"), approved=True))
        check(f"DeepSeek {status} -> {state}, said plainly, no key in it",
              out["state"] == state and words in out["error"]
              and FAKE_DEEPSEEK not in json.dumps(out), out)
    out = _with_cloud("deepseek", {"/v1/tools/search": (402, {}, b"{}")},
                      lambda srv: WS.run(WS.plan("x"), approved=True))
    check("... 402 offers no silent retry and says where to add credit",
          "platform.deepseek.com" in out["error"] and out["ok"] is False, out)

    # 5. A redirect never carries the key.
    target = StandIn({"*": (200, {}, deepseek_body)})
    out = _with_cloud("deepseek",
                      {"/v1/tools/search": (307, {"Location": target.url + "/steal"}, b"")},
                      lambda srv: WS.run(WS.plan("x"), approved=True))
    check("DeepSeek: a redirect is refused; the key never reaches another address",
          out["ok"] is False and not target.seen, target.seen)
    target.close()
    # 6. An oversized answer is refused.
    big = b'{"results": [' + b" " * (WS.MAX_BODY + 10) + b"]}"
    out = _with_cloud("deepseek", {"/v1/tools/search": (200, {}, big)},
                      lambda srv: WS.run(WS.plan("x"), approved=True))
    check("DeepSeek: an answer over the size cap is refused", out["ok"] is False, out)

    # 7. The query bound (its guide: 1 to 128 characters) refuses before sending.
    FakeStore.DATA.clear()
    with NoSockets() as ns:
        p = WS.plan("x" * (WS.DEEPSEEK_QUERY_CHARS + 1))
    check("DeepSeek: over 128 characters is refused before any socket",
          p.state == "empty" and "128" in p.problem and not ns.tried, p.problem)
    with NoSockets() as ns:
        p = WS.plan("x" * WS.DEEPSEEK_QUERY_CHARS)
    check("... exactly 128 is not refused for its length", "128 characters" not in p.problem)
    direct = WS.Plan(query="x" * (WS.DEEPSEEK_QUERY_CHARS + 1), provider="deepseek",
                     label="DeepSeek", host="api.deepseek.com", keyed=True)
    try:
        WS._deepseek(direct)
        refused = False
    except WS.SearchError as exc:
        refused = exc.state == "empty" and "128" in exc.said
    check("... and the provider itself refuses one built by hand", refused)
    check("the real address is DeepSeek's own, over https",
          WS.DEEPSEEK_URL == "https://api.deepseek.com/v1/tools/search")
    WS._key("deepseek")
    check("the log scrubber hides the DeepSeek key by value",
          FAKE_DEEPSEEK not in jarvis_scrub.scrub_text(f"sending {FAKE_DEEPSEEK} now"))
    reset(provider="deepseek")
    check("a saved \"deepseek\" is simply DeepSeek, and still the sixth",
          WS.settings()["provider"] == "deepseek" and WS.settings()["why"] == ""
          and WS.PROVIDERS.index("deepseek") == len(WS.PROVIDERS) - 1)
    FakeStore.DATA.clear()


def t_the_keys_stay_on_the_pc():
    rs = (REPO / "jarvis-desktop" / "src-tauri" / "src" / "token_store.rs").read_text(encoding="utf-8")
    for pid, target in WS.KEY_TARGETS.items():
        check(f"the desktop writes the {pid} key under the name the PC reads ({target})",
              json.dumps(target) in rs)
    check("the key names are not environment variables (so jarvis_child_env cannot pass "
          "them on, and nothing tells the owner to setx one)",
          "environ" not in Path(WS.__file__).read_text(encoding="utf-8").split("def _key", 1)[1]
          .split("def key_saved", 1)[0])
    reset()
    code, out = WS.handle_settings({"tavily_key": FAKE_TAVILY})
    check("the settings route takes no key", code == 400 and FAKE_TAVILY not in json.dumps(out))
    patch = (HERE / "web-search.patch").read_text(encoding="utf-8")
    check("web-search.patch adds no route that takes a key",
          not re.search(r'route\s*==\s*"/api/search/key', patch)
          and "/api/search/key" not in patch)
    view = json.dumps(WS.view())
    FakeStore.DATA[WS.KEY_TARGETS["tavily"]] = FAKE_TAVILY
    view = json.dumps(WS.view())
    check("GET /api/search says a key is saved, never what it is",
          FAKE_TAVILY not in view and '"key_saved": true' in view)
    FakeStore.DATA.clear()
    said = []
    rc = WS._main(["key", "tavily"], ask_secret=lambda prompt: FAKE_TAVILY, out=said.append)
    check("the owner's command saves the key in Credential Manager",
          rc == 0 and FakeStore.DATA.get(WS.KEY_TARGETS["tavily"]) == FAKE_TAVILY, said)
    check("... and never prints it", FAKE_TAVILY not in "\n".join(said))
    rc = WS._main(["key", "tavily"], ask_secret=lambda prompt: "has space x", out=said.append)
    check("a key with a space is refused", rc == 1)
    WS._main(["status"], out=said.append)
    check("status says saved, not what", FAKE_TAVILY not in "\n".join(said)
          and any("Tavily key: saved" in s for s in said), said)
    rc = WS._main(["forget-key", "tavily"], out=said.append)
    check("forget-key removes it", rc == 0 and WS.KEY_TARGETS["tavily"] not in FakeStore.DATA)


# --------------------------------------------------------------------------
#   5. DuckDuckGo (ddgs)
# --------------------------------------------------------------------------

def fake_ddgs(calls, *, engines=("duckduckgo", "bing", "google"), rows=None, raise_=None):
    mod = types.ModuleType("ddgs")
    mod.engines = types.SimpleNamespace(ENGINES={"text": {e: object for e in engines}})

    class DDGS:
        def __init__(self, proxy=None, timeout=5, **kw):
            calls.append(("init", proxy, timeout))

        def text(self, query, **kw):
            calls.append(("text", query, kw, time.monotonic()))
            if raise_ is not None:
                raise raise_
            return rows if rows is not None else [
                {"title": "D", "href": "https://d.example/1", "body": "snippet"}]
    mod.DDGS = DDGS
    return mod


def t_duckduckgo_only_and_paced():
    reset(provider="duckduckgo")
    calls = []
    WS._DDGS_MODULE = fake_ddgs(calls)
    saved_gap = WS.DDG_GAP
    WS.DDG_GAP = 0.3
    try:
        # plan() asks whether ddgs is installed; the fake stands in for it.
        saved = WS._ddgs_installed
        WS._ddgs_installed = lambda: True
        out1 = WS.run(WS.plan("walking boots"), approved=True)
        out2 = WS.run(WS.plan("walking boots"), approved=True)
        texts = [c for c in calls if c[0] == "text"]
        check("DuckDuckGo answers", out1.get("ok") and out1["results"][0]["url"]
              == "https://d.example/1", out1)
        check("ddgs is asked with backend=\"duckduckgo\" ONLY, never its \"auto\" mix",
              texts and all(c[2].get("backend") == "duckduckgo" for c in texts), texts)
        check("no proxy is handed to ddgs by Jarvis", all(c[1] is None for c in calls
                                                        if c[0] == "init"))
        check(f"two searches are at least {WS.DDG_GAP}s apart (paced)",
              len(texts) == 2 and texts[1][3] - texts[0][3] >= WS.DDG_GAP - 0.01,
              [t[3] for t in texts])
        calls.clear()
        WS._DDGS_MODULE = fake_ddgs(calls, engines=("bing", "google"))
        out = WS.run(WS.plan("walking boots"), approved=True)
        check("a ddgs without its DuckDuckGo engine is refused BEFORE anything is sent "
              "(it would have fallen back to other engines)",
              out["ok"] is False and not [c for c in calls if c[0] == "text"]
              and "DuckDuckGo" in out["error"], out)

        class RatelimitException(Exception):
            pass
        for exc, state in ((RatelimitException("202 Ratelimit"), "rate_limited"),
                           (Exception("No results found."), "no_results"),
                           (TimeoutError("timed out"), "timeout")):
            WS._DDGS_MODULE = fake_ddgs([], raise_=exc)
            out = WS.run(WS.plan("walking boots"), approved=True)
            check(f"ddgs {type(exc).__name__}({exc}) -> {state}", out["state"] == state, out)
        WS._ddgs_installed = lambda: False
        p = WS.plan("walking boots")
        check("ddgs not installed: says so, with the pip line",
              p.state == "not_installed" and WS.PIP_LINE in p.problem, p.problem)
        WS._ddgs_installed = saved
    finally:
        WS.DDG_GAP = saved_gap
        WS._DDGS_MODULE = None


# --------------------------------------------------------------------------
#   6. The settings
# --------------------------------------------------------------------------

class Verdict:
    def __init__(self, allowed, tier, outcome, reason="", action=""):
        self.allowed, self.tier, self.outcome = allowed, tier, outcome
        self.reason, self.action, self.request_id = reason, action, None


def t_settings_and_the_card_to_ask_less():
    reset()
    s = WS.settings()
    check("no file: SearXNG on this PC, asking only when private things could slip in",
          s == {"provider": "searxng", "searxng_url": "http://127.0.0.1:8888",
                "ask_every_time": False, "enabled": True, "why": ""}, s)
    WS.settings_path().parent.mkdir(parents=True, exist_ok=True)
    WS.settings_path().write_text("{nope", encoding="utf-8")
    s = WS.settings()
    check("a damaged file fails closed: no provider, and ask every time",
          s["provider"] is None and s["ask_every_time"] is True and s["why"], s)
    p = WS.plan("x")
    check("... so nothing is searched, and it says why", p.state == "settings_damaged", p)
    WS.handle_settings({"ask_every_time": True})
    check("... and changing another setting does not quietly pick a provider",
          WS.settings()["provider"] is None and WS.plan("x").state == "settings_damaged",
          WS.settings())
    # D8 (2026-10-25): choosing a provider now TESTS it first and keeps the
    # old one if the test fails - so this check stubs the test as working.
    # `t_choosing_a_provider_tests_it_first` below proves the refusing half.
    real_test = WS.live_test
    WS.live_test = lambda provider, *, s=None: {"ok": True, "results": 5,
                                                "provider": provider, "tested": True}
    try:
        code, out = WS.handle_settings({"provider": "duckduckgo"})
    finally:
        WS.live_test = real_test
    check("... choosing one rewrites it", code == 200 and WS.settings()["provider"] == "duckduckgo"
          and WS.settings()["why"] == "")
    reset()
    code, out = WS.handle_settings({"provider": "exa", "ask_every_time": True})
    check("one change per request", code == 400)
    code, out = WS.handle_settings({"provider": "whoogle"})
    check("Whoogle cannot be chosen", code == 400)
    FakeStore.DATA.clear()
    code, out = WS.handle_settings({"provider": "exa"})
    check("choosing a provider is immediate, and says what is missing",
          code == 200 and WS.settings()["provider"] == "exa" and "No Exa key" in
          out["said"], out.get("said"))
    code, out = WS.handle_settings({"ask_every_time": True})
    check("\"Ask before every web search\" ON is immediate", code == 200
          and WS.settings()["ask_every_time"] is True)
    cards = []
    answer = {"v": Verdict(True, "ask", "approved")}

    def gate(action, detail, prompt):
        cards.append((action, detail))
        return answer["v"]
    code, out = WS.request_ask_every_time(False, gate=gate, tier_of=lambda a: "ask",
                                          spawn=lambda fn: fn())
    check("OFF raises ONE card (stop_asking_before_every_web_search) and is on only after a yes",
          code == 202 and len(cards) == 1 and cards[0][0] == "stop_asking_before_every_web_search"
          and WS.settings()["ask_every_time"] is False, (code, cards))
    check("... the card says what changes and what saying no costs",
          "If you say no" in cards[0][1]["text"] and "exact words" in cards[0][1]["text"])
    WS.handle_settings({"ask_every_time": True})
    answer["v"] = Verdict(False, "ask", "denied")
    WS.request_ask_every_time(False, gate=gate, tier_of=lambda a: "ask", spawn=lambda fn: fn())
    check("a denied card leaves it on", WS.settings()["ask_every_time"] is True
          and WS.card_state()["last"]["outcome"] == "denied")
    answer["v"] = Verdict(True, "auto", "auto")
    code, out = WS.request_ask_every_time(False, gate=gate, tier_of=lambda a: "auto",
                                          spawn=lambda fn: fn())
    check("a tier other than ask is refused (503), never an automatic yes",
          code == 503 and WS.settings()["ask_every_time"] is True, out)
    later = []
    code, out = WS.request_ask_every_time(False, gate=gate, tier_of=lambda a: "ask",
                                          spawn=later.append)
    check("while the card waits, the answer says so", code == 202 and WS.card_state()["waiting"])
    WS.handle_settings({"ask_every_time": True})
    answer["v"] = Verdict(True, "ask", "approved")
    later[0]()
    check("turning it on while the card waited withdraws the card",
          WS.settings()["ask_every_time"] is True
          and WS.card_state()["last"]["outcome"] == "withdrawn", WS.card_state())


def t_test_search_reports_plainly():
    srv = StandIn({"/search": (200, {}, searxng_json(3))})
    reset(searxng_url=srv.url)
    code, out = WS.handle_test({})
    check("Test search: works, with a count", out["ok"] and out["state"] == "works"
          and "3 results" in out["said"], out)
    check("... for the fixed harmless word only",
          len(srv.seen) >= 2 and all(f"q={WS.TEST_QUERY}" in r["path"]
                                     for r in srv.seen[1:]), srv.seen)
    srv.close()
    reset(searxng_url=f"http://127.0.0.1:{free_port()}")
    code, out = WS.handle_test({})
    check("Test search: not running", out["state"] == "not_running", out)
    reset(provider="tavily")
    FakeStore.DATA.clear()
    with NoSockets() as ns:
        code, out = WS.handle_test({})
    check("Test search: key missing, with no socket", out["state"] == "key_missing"
          and not ns.tried, out)


# --------------------------------------------------------------------------
#   7. The chat loop: when a search asks first
# --------------------------------------------------------------------------

def _turn(user_text="find walking boots", *, provenance="typed", facts=False, gate=None,
          before_tools=(), tainted=False, query="walking boots", app_system=False,
          pinned=0, names=None):
    """One turn in which the model asks for web_search. Returns (gate calls,
    what the model was told, turn summary, stand-in's requests)."""
    srv = StandIn({"/search": (200, {}, searxng_json(2))})
    s = WS.settings()
    if s["provider"] is not None:
        # A file with no provider in use (damaged) is left as it is: the
        # turn must meet it.
        WS._save(searxng_url=srv.url, provider=s["provider"],
                 ask_every_time=s["ask_every_time"])
    gate_calls = []

    def watching(action, detail, prompt):
        gate_calls.append((action, detail))
        return (gate or (lambda *a: Verdict(True, "ask", "approved")))(action, detail, prompt)
    calls = []
    for i, (tname, targs) in enumerate(before_tools):
        calls.append({"id": f"b{i}", "function": {"name": tname, "arguments": json.dumps(targs)}})
    calls.append({"id": "w", "function": {"name": "web_search",
                                          "arguments": json.dumps({"query": query})}})
    responses = [{"choices": [{"message": {"role": "assistant", "tool_calls": calls}}]},
                 {"choices": [{"message": {"role": "assistant", "content": "done"}}]}]
    it = iter(responses)
    sent = []

    def post(url, payload):
        sent.append(payload)
        return next(it)
    messages = [{"role": "user", "content": user_text}]
    if facts:
        # True: one sensitive fact - another person's health (an everyday
        # fact about someone, "Owner's sister is called Priya", is a normal
        # fact since the owner's decision of 2026-09-26). A list: those
        # facts, pinned first under memory-profile.patch's heading when
        # `pinned` names how many of them are pinned.
        lines = (["Owner's dad has diabetes."] if facts is True else list(facts))
        body = "\n".join(f"- [2026-09-20] {f}" for f in lines)
        if pinned:
            body = ("Always keep in mind (the owner pinned these):\n"
                    + "\n".join(f"- [2026-09-20] {f}" for f in lines[:pinned])
                    + ("\nRecalled for this question:\n"
                       + "\n".join(f"- [2026-09-20] {f}" for f in lines[pinned:])
                       if lines[pinned:] else ""))
        messages.insert(0, {"role": "system", "content":
                            "Things you know about the user.\n---FACTS---\n"
                            + body + "\n---END FACTS---"})
    req_msgs = [{"role": "user", "content": user_text, "provenance": provenance}]
    if app_system:
        req_msgs.insert(0, {"role": "system", "content": "clipboard: something"})
    saved_taint = AG._conversation_tainted
    AG._conversation_tainted = lambda cid, messages=None: tainted
    saved_names = WS.names_for_facts
    WS.names_for_facts = lambda fs: dict(names or {})
    try:
        summary = AG.run_local_turn(
            messages, "m", ollama_url="http://127.0.0.1:11434", stream_out=lambda b: None,
            post=post, gate_check=watching, enabled_tools={"web_search", "memory_search"},
            record_chain=lambda s: None, context_length=8192,
            request={"messages": req_msgs, "conversation_id": "c1"})
    finally:
        AG._conversation_tainted = saved_taint
        WS.names_for_facts = saved_names
        srv.close()
    told = [m for m in sent[-1]["messages"] if m.get("role") == "tool"]
    return gate_calls, told, summary, srv.seen


def _searched(seen):
    return bool(seen)


def t_no_card_for_the_owners_own_question():
    reset()
    gates, told, summary, seen = _turn()
    check("a search straight from the owner's own typed question: no card", not gates, gates)
    check("... and it searched", _searched(seen) and "web_search" in summary["tools_ran"])
    last = json.loads(told[-1]["content"])
    check("the results reach the model labelled as outside text",
          last.get(AG.OUTSIDE_FIELD) == AG.OUTSIDE_LABEL and last.get("ok") is True, last)
    reset()
    gates, told, summary, seen = _turn(provenance="voice")
    check("said to the talk button: no card either", not gates and _searched(seen))


def _card_case(label, want_line, **kw):
    reset()
    gates, told, summary, seen = _turn(**kw)
    ws = [g for g in gates if g[0] == WS.ACTION_SEARCH]
    text = ws[0][1]["text"] if ws else ""
    check(f"{label}: ONE card, under {WS.ACTION_SEARCH}", len(ws) == 1, gates)
    check(f"{label}: the card shows the EXACT search words and why it asks",
          f"“{kw.get('query', 'walking boots')}”" in text and want_line in text, text)
    check(f"{label}: searched after the yes", _searched(seen))
    return text


def t_a_card_when_private_things_could_slip_in():
    _card_case("a sensitive saved fact recalled", "Jarvis used a saved fact about someone "
               "else's health", facts=True)
    _card_case("the conversation read outside text before", AG.WEB_SEARCH_READ, tainted=True)
    _card_case("a pasted message", "was pasted in", provenance="pasted")
    _card_case("the app's own text", AG.WEB_SEARCH_APP, app_system=True)
    # Another tool read something first in this turn (memory_search here -
    # "saved memories were read" the other way).
    saved_run = AG.TOOLS["memory_search"].execute
    AG.TOOLS["memory_search"].execute = lambda a, s, **k: {"ok": True, "facts": ["x"]}
    try:
        _card_case("memory_search ran first", AG.WEB_SEARCH_READ,
                   before_tools=[("memory_search", {"query": "sister"})])
    finally:
        AG.TOOLS["memory_search"].execute = saved_run
    reset(ask_every_time=True)
    gates, told, summary, seen = _turn()
    ws = [g for g in gates if g[0] == WS.ACTION_SEARCH]
    check("\"Ask before every web search\" on: a card even for the owner's own question",
          len(ws) == 1 and AG.WEB_SEARCH_EVERY in ws[0][1]["text"], gates)


def _mem_case(label, card, *, facts, query, user_text, want=(), not_want=(), names=None,
              pinned=0):
    """One turn with saved facts in its context: a card or not, and what the
    card says (and must not say)."""
    reset()
    gates, told, summary, seen = _turn(user_text, facts=facts, query=query, names=names,
                                       pinned=pinned)
    ws = [g for g in gates if g[0] == WS.ACTION_SEARCH]
    text = ws[0][1]["text"] if ws else ""
    if not card:
        check(f"{label}: no card", not ws, text)
        check(f"{label}: ... and it searched", _searched(seen))
        return text
    check(f"{label}: ONE card", len(ws) == 1, gates)
    check(f"{label}: the card shows the exact search words", f"“{query}”" in text,
          text)
    for w in want:
        check(f"{label}: the card says {w!r}", w in text, text)
    for w in not_want:
        check(f"{label}: the card does not show {w!r}", w not in text, text)
    check(f"{label}: searched after the yes", _searched(seen))
    return text


def t_saved_facts_ask_only_when_repeated_or_sensitive():
    """The owner's decision of 2026-09-25, after the creativity audit: saved
    memories make a search ask only when the search words repeat a saved
    fact, or a sensitive fact was used."""
    plain = ["Owner lives in Leeds", "Owner is learning Rust"]
    _mem_case("two pinned facts, a search about something else", False, facts=plain,
              pinned=2, query="walking boots", user_text="find walking boots")
    _mem_case("a recalled fact, a search about something else", False, facts=plain,
              query="best walking boots for winter", user_text="which walking boots are best?")
    _mem_case("the search words repeat where the owner lives", True, facts=plain, pinned=2,
              query="vegan restaurants Leeds", user_text="any good vegan places near me?",
              want=("The search words repeat something you told Jarvis (“Leeds”)",
                    "The saved fact: “Owner lives in Leeds”"),
              not_want=("learning Rust",))
    _mem_case("the owner said Leeds themselves: their own words, no card", False,
              facts=plain, pinned=2, query="vegan restaurants Leeds",
              user_text="vegan restaurants in Leeds")
    _mem_case("Rust in the owner's own question", False, facts=plain,
              query="Rust 1.80 release notes", user_text="what is new in Rust 1.80?")
    _mem_case("a plural still repeats (chickens / chicken)", True,
              facts=["Owner keeps chickens"], query="chicken coop plans",
              user_text="what should I build this weekend?", want=("“chicken”",))
    _mem_case("a place from a fact that is not sensitive", True,
              facts=["Owner's gym is PureGym Headingley"], query="PureGym Headingley opening times",
              user_text="when does my gym open on Sunday?",
              want=("“PureGym”", "“Headingley”",
                    "The saved fact: “Owner's gym is PureGym Headingley”"))
    # Sensitive facts: a card whatever the search says - and the fact's own
    # words are never put on the card beyond what the search holds.
    _mem_case("a sensitive fact (health) used, the search about something else", True,
              facts=["Owner has type 2 diabetes"], query="walking boots",
              user_text="find walking boots",
              want=("Jarvis used a saved fact about health",), not_want=("diabetes",))
    _mem_case("a pinned sensitive fact among plain ones", True,
              facts=["Owner has type 2 diabetes"] + plain, pinned=3, query="walking boots",
              user_text="find walking boots", want=("about health",),
              not_want=("diabetes", "Leeds"))
    # An everyday fact about someone is a normal fact (the owner's decision
    # of 2026-09-26): it asks only because the search repeats it, and the
    # card shows it like any other normal fact.
    _mem_case("the search repeats the sister's name", True,
              facts=["Owner's sister is called Priya"], query="Priya Sharma LinkedIn",
              user_text="can you look her up?",
              want=("(“Priya”)", "The saved fact: “Owner's sister is called Priya”"),
              not_want=("about another person", "that fact's own words are not shown"))
    _mem_case("an everyday fact about someone, the search about something else", False,
              facts=["Owner's sister is called Priya"], query="walking boots",
              user_text="find walking boots")
    _mem_case("the search repeats a private fact about someone", True,
              facts=["Owner's brother Tom owes the bank money"], query="Tom debt advice",
              user_text="where can he get help?",
              want=("(“Tom”)", "about someone else's money",
                    "that fact's own words are not shown here"),
              not_want=("owes the bank",))
    _mem_case("the search repeats a phone number from a fact", True,
              facts=["Owner's plumber Dave's number is 07700 900123"],
              query="07700900123 who called", user_text="who keeps calling me?",
              want=("“07700900123”",), not_want=("plumber", "Dave"))
    _mem_case("the search repeats part of an address from a fact", True,
              facts=["Owner lives at 14 Elm Street, Headingley"],
              query="Elm Street Headingley parking permit",
              user_text="how do I get a parking permit?",
              want=("“Elm”", "where someone can be found"), not_want=("14 Elm",))
    # The names layer: a nickname linked to the fact's name, not in the
    # fact's own words.
    dog = ["Owner's dog is called Biscuit"]
    _mem_case("a nickname from the names layer", True, facts=dog,
              names={0: ["Biscuit", "Bizzy"]}, query="Bizzy harness size",
              user_text="what harness should I get for the dog?",
              want=("“Bizzy”",
                    "The saved fact: “Owner's dog is called Biscuit”"))
    _mem_case("CONTROL: without the names layer, that nickname is not seen", False,
              facts=dog, query="Bizzy harness size",
              user_text="what harness should I get for the dog?")
    # The honest limit, pinned so it is not forgotten: a reworded fact is not
    # caught by comparing words (docs/JARVIS-API.md 23.3).
    _mem_case("KNOWN LIMIT: a reworded fact (vegetarian / meat-free) is not caught", False,
              facts=["Owner is vegetarian"], query="meat-free recipes",
              user_text="what should I cook tonight?")
    # "Ask before every web search" still asks, facts or not.
    reset(ask_every_time=True)
    gates, told, summary, seen = _turn(facts=plain, pinned=2)
    ws = [g for g in gates if g[0] == WS.ACTION_SEARCH]
    check("\"Ask before every web search\" on, pinned facts not in the words: still a card",
          len(ws) == 1 and AG.WEB_SEARCH_EVERY in ws[0][1]["text"], gates)
    # After outside text: still a card, as before.
    reset()
    gates, told, summary, seen = _turn(facts=plain, pinned=2, tainted=True)
    ws = [g for g in gates if g[0] == WS.ACTION_SEARCH]
    check("pinned facts not in the words, but the conversation read outside text: a card",
          len(ws) == 1 and AG.WEB_SEARCH_READ in ws[0][1]["text"], gates)


def t_when_in_doubt_it_asks():
    # The comparison fails: a card, never a quiet search.
    saved = WS.repeated_facts
    WS.repeated_facts = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    try:
        reset()
        gates, told, summary, seen = _turn(facts=["Owner lives in Leeds"])
    finally:
        WS.repeated_facts = saved
    ws = [g for g in gates if g[0] == WS.ACTION_SEARCH]
    check("the check cannot run: a card saying so",
          len(ws) == 1 and AG.WEB_SEARCH_UNCHECKED in ws[0][1]["text"], gates)
    # The sensitive check cannot run: every fact counts as sensitive.
    saved_mod = sys.modules.get("jarvis_sensitive")
    sys.modules["jarvis_sensitive"] = None
    try:
        topic = WS.fact_topic("Owner lives in Leeds")
    finally:
        if saved_mod is None:
            sys.modules.pop("jarvis_sensitive", None)
        else:
            sys.modules["jarvis_sensitive"] = saved_mod
    check("without jarvis_sensitive, a fact counts as sensitive (fails closed)",
          topic == "a topic Jarvis could not check", topic)
    check("no search words at all: saved memories ask",
          AG.web_search_memory_lines(["Owner lives in Leeds"], None) == [AG.WEB_SEARCH_UNCHECKED])
    check("a FACTS block with nothing that reads as a fact: it asks",
          AG.web_search_memory_lines([], "walking boots") == [AG.WEB_SEARCH_UNCHECKED])


def t_the_word_comparison():
    R = WS.repeated_facts
    check("everyday words never count (best, near, today, owner, lives)",
          R("what is good near me today", ["Owner lives near the best one, always"]) == [])
    check("a year is not a sign of a fact",
          R("best laptops 2026", ["Owner is moving house in 2026"]) == [])
    check("a short house number alone is not either",
          R("top 14 films", ["Owner lives at number 14"]) == [])
    hit = R("call 0113 496 0000", ["Owner's dentist is on 0113 496 0000"])
    check("a phone number written with spaces is found, as the search writes it",
          len(hit) == 1 and hit[0]["words"] == ["0113 496 0000"], hit)
    hit = R("zoe birthday ideas", ["Owner's friend is Zoë"])
    check("accents do not hide a name (Zoë / zoe)", len(hit) == 1, hit)
    check("the owner's own number is theirs",
          R("07700900123 owner", ["Owner's plumber is on 07700 900123"],
            owner_words="who is 07700 900123?") == [])
    check("a short number the owner said does not hide a longer one from a fact",
          len(R("0113 496 1000 who", ["Dentist is on 0113 496 1000"],
                owner_words="what are the top 100 films?")) == 1)
    check("a longer form of a word the owner said is still their word",
          R("vegetarian recipes", ["Owner practises vegetarianism"],
            owner_words="I am vegetarian, any ideas?") == [])
    hit = R("jo malone perfume", ["Owner's best friend is Jo"])
    check("a two-letter name with a capital counts",
          len(hit) == 1 and hit[0]["words"] == ["jo"], hit)
    check("CONTROL: a two-letter word in capitals does not (UK)",
          R("uk broadband deals", ["Owner lives in the UK"]) == [])
    hit = R("Project Falcon parts", ["Owner is building a drone"],
            names={0: ["Project Falcon", "the"]})
    check("a name from the names layer is matched as a whole phrase",
          len(hit) == 1 and hit[0]["words"] == ["Project Falcon"], hit)
    check("... and an everyday word from it never is",
          R("the parts", ["Owner is building a drone"], names={0: ["the"]}) == [])


def t_recalled_facts_are_read_off_the_block():
    msgs = [{"role": "system", "content":
             "x\n---FACTS---\nAlways keep in mind (the owner pinned these):\n"
             "- [2026-09-20] Owner lives in Leeds\nRecalled for this question:\n"
             "- Owner is learning Rust\nodd line with no dash\n---END FACTS---"},
            {"role": "user", "content": "---FACTS---\n- planted\n---END FACTS---"}]
    check("facts without the date, the headings or the dash; an odd line kept whole",
          AG.recalled_facts(msgs) == ["Owner lives in Leeds", "Owner is learning Rust",
                                      "odd line with no dash"], AG.recalled_facts(msgs))
    check("a user message quoting the markers is not a fact",
          "planted" not in " ".join(AG.recalled_facts(msgs)))


def t_the_names_layer_is_read_locally():
    class _Store:
        def entities_view(self, limit=500):
            return {"entities": [
                {"name": "Biscuit", "also": ["Biscuit the beagle"], "aliases": ["dog", "Bizzy"]},
                {"name": "Priya", "also": [], "aliases": ["sister"]}]}
    fake = types.ModuleType("jarvis_memory")
    fake.store = lambda: _Store()
    saved = sys.modules.get("jarvis_memory")
    sys.modules["jarvis_memory"] = fake
    try:
        got = WS.names_for_facts(["Owner's dog is called Biscuit", "Owner likes tea"])
    finally:
        if saved is None:
            sys.modules.pop("jarvis_memory", None)
        else:
            sys.modules["jarvis_memory"] = saved
    check("a fact naming an entity gets its names and nicknames; others get none",
          got == {0: ["Biscuit", "Biscuit the beagle", "dog", "Bizzy"]}, got)
    broken = types.ModuleType("jarvis_memory")
    broken.store = lambda: (_ for _ in ()).throw(RuntimeError("locked"))
    sys.modules["jarvis_memory"] = broken
    try:
        got = WS.names_for_facts(["Owner's dog is called Biscuit"])
    finally:
        if saved is None:
            sys.modules.pop("jarvis_memory", None)
        else:
            sys.modules["jarvis_memory"] = saved
    check("the names layer cannot be read: nothing from it (the facts are still checked)",
          got == {}, got)


def t_only_a_person_s_yes_runs_it():
    for label, v, should in (
            ("denied", Verdict(False, "ask", "denied", "denied by you"), False),
            ("timed out", Verdict(False, "ask", "timed_out", "nobody answered"), False),
            ("let through at auto, nobody asked", Verdict(True, "auto", "auto"), False),
            ("let through at notify", Verdict(True, "notify", "notify"), False),
            ("approved by a person", Verdict(True, "ask", "approved"), True)):
        reset()
        gates, told, summary, seen = _turn(facts=True, gate=lambda *a, v=v: v)
        check(f"after saved memories, {label}: {'searched' if should else 'nothing sent'}",
              _searched(seen) == should, (seen, told[-1]["content"][:300] if told else ""))
        if label.startswith("let through"):
            check(f"... {label}: the model is told which line to set to ask",
                  "without asking anyone" in told[-1]["content"]
                  and WS.ACTION_SEARCH in told[-1]["content"])


def t_refusals_that_never_ask():
    reset()
    gates, told, summary, seen = _turn(facts=True, query=f"is {FAKE_AWS} a real key")
    out = json.loads(told[-1]["content"])
    check("a secret in the words: refused, no card, nothing sent",
          not gates and not _searched(seen) and "AWS access key" in out["error"], out)
    check("... the model never sees the value echoed back", FAKE_AWS not in told[-1]["content"])
    saved = AG._tier_of
    AG._tier_of = lambda a: "never" if a == WS.ACTION_SEARCH else saved(a)
    try:
        reset()
        gates, told, summary, seen = _turn()
    finally:
        AG._tier_of = saved
    check("search_the_web = \"never\": switched off, nothing sent, no card",
          not gates and not _searched(seen) and "switched off" in told[-1]["content"])
    reset(provider="tavily")
    FakeStore.DATA.clear()
    gates, told, summary, seen = _turn(facts=True)
    check("no key: no card is raised for a search that cannot run", not gates
          and "No Tavily key" in told[-1]["content"], told[-1]["content"][:300])
    # The card limit.
    reset()
    watch = AG._TurnWatch([{"role": "user", "content": "x"}],
                          {"messages": [{"role": "user", "content": "x", "provenance": "typed"}]},
                          tainted=True)
    watch.cards = AG.CARDS_PER_TURN
    convo, steps, lines = [], [], []
    out = AG._Out(lambda b: None, sse=False)
    AG._web_search_call({"query": "x"}, {"id": "1"}, convo, steps,
                        lambda *a: (_ for _ in ()).throw(AssertionError("asked")), None, out,
                        lambda *a, **k: None, watch=watch, tell_owner=lines.append)
    check("past the card limit: refused before anyone is asked",
          steps[-1]["outcome"] == "refused" and "most one answer may ask" in convo[-1]["content"],
          (steps, convo))


def t_recalled_memory_is_read_off_the_facts_block():
    check("a FACTS block with a fact counts",
          AG.recalled_memory([{"role": "system", "content": "x\n---FACTS---\n- a\n---END FACTS---"}]))
    check("an empty block does not", not AG.recalled_memory(
        [{"role": "system", "content": "x\n---FACTS---\n\n---END FACTS---"}]))
    check("a temporary chat's line does not", not AG.recalled_memory(
        [{"role": "system", "content": "This is a temporary chat. You have no saved facts"}]))
    check("a user message quoting the marker does not", not AG.recalled_memory(
        [{"role": "user", "content": "---FACTS---\n- a"}]))


# --------------------------------------------------------------------------
#   8. Without the model
# --------------------------------------------------------------------------

class _Sched:
    def mark_command(self, t):
        pass


def t_which_search_without_the_model():
    reset()
    for said, which in (("Which search should I use?", None), ("why SearXNG?", "searxng"),
                        ("what about Tavily for web search", "tavily"), ("why exa", "exa"),
                        ("why brave", "brave"), ("why whoogle", "whoogle"),
                        ("why not whoogle", "whoogle"),
                        ("what about DeepSeek for web search", "deepseek"),
                        ("why deepseek for web search", "deepseek"),
                        ("what search engine are you using", None)):
        i = Q.match(said)
        check(f"{said!r} is answered without the model", i is not None
              and i.name == "search_explain" and i.f.get("which") == which, i and i.f)
    for said in ("search for walking boots", "what is brave", "why is the sky blue",
                 "use your judgement", "what is deepseek", "why deepseek"):
        check(f"{said!r} goes to the model", Q.match(said) is None or
              not Q.match(said).name.startswith("search_"))
    r = Q.answer("which search should I use", sched=_Sched())
    check("the answer is the PC's own words, all six and Whoogle",
          all(WS.WHY[p] in r.reply for p in WS.PROVIDERS)
          and all(x["why"] in r.reply for x in WS.LEFT_OUT))
    FakeStore.DATA.clear()
    r = Q.answer("use brave for web search", sched=_Sched())
    check("\"use Brave for web search\" switches, and says the key is missing",
          WS.settings()["provider"] == "brave" and "No Brave Search key" in r.reply, r.reply)
    r = Q.answer("why brave", sched=_Sched())
    check("\"why Brave?\" says it can cost money", "payment card that is charged" in r.reply,
          r.reply)
    before = WS.settings()["provider"]
    r = Q.answer("use whoogle for web search", sched=_Sched())
    check("\"use Whoogle\" says why not, and changes nothing",
          "2025" in r.reply and WS.settings()["provider"] == before, r.reply)
    FakeStore.DATA.clear()
    r = Q.answer("use exa for web search", sched=_Sched())
    check("\"use Exa for web search\" switches, and says the key is missing",
          WS.settings()["provider"] == "exa" and "No Exa key" in r.reply, r.reply)
    r = Q.answer("use deepseek for web search", sched=_Sched())
    check("\"use DeepSeek for web search\" switches, and says the key is missing",
          WS.settings()["provider"] == "deepseek"
          and "No DeepSeek Search key" in r.reply, r.reply)
    r = Q.answer("why searxng", sched=_Sched())
    check("\"why SearXNG?\" says why it is the default", WS.DEFAULT_WHY in r.reply)
    # D8 (2026-10-25): choosing a provider now TESTS it first, so this one
    # really does send one search for the fixed test word - the switch's own
    # words are what is under test here, so the test result is stubbed as
    # working. t_choosing_a_provider_tests_it_first_and_keeps_the_old_one
    # proves the refusing half; the no-socket guarantee is kept where it can
    # be, and checked just below with a key that is missing.
    real_test = WS.live_test
    WS.live_test = lambda provider, *, s=None: {"ok": True, "results": 5,
                                                "provider": provider, "tested": True}
    try:
        r = Q.answer("use duckduckgo for web search", sched=_Sched())
    finally:
        WS.live_test = real_test
    check("\"use DuckDuckGo for web search\" switches, and says so",
          WS.settings()["provider"] == "duckduckgo" and "DuckDuckGo" in r.reply, r.reply)
    FakeStore.DATA.clear()
    with NoSockets() as ns:
        r = Q.answer("use exa for web search", sched=_Sched())
    check("a provider whose key is missing is not tested, so nothing is sent",
          WS.settings()["provider"] == "exa" and not ns.tried and "No Exa key" in r.reply,
          (r.reply, ns.tried))
    body = {"messages": [{"role": "user", "content": "use brave for web search",
                          "provenance": "pasted"}]}
    check("only the owner's own words switch it (a pasted one goes to the model)",
          Q.answer_turn(body, sched=_Sched()) is None)


# --------------------------------------------------------------------------
#   9. web-search.patch
# --------------------------------------------------------------------------

def _rehearse():
    order = _stack.order()
    if "web-search.patch" not in order:
        return False, "web-search.patch is not in apply-patches.ps1's list", {}
    before = order[:order.index("web-search.patch")]
    patch = (HERE / "web-search.patch").read_text(encoding="utf-8")
    afters = {}
    git = shutil.which("git")
    for target in ("jarvis_hud.py", "jarvis_gate.py"):
        text, log = _stack.stand_in(target, before)
        if text is None:
            return False, "; ".join(log), {}
        d = Path(tempfile.mkdtemp(prefix="jarvis-ws-patch-"))
        try:
            (d / target).write_text(text, encoding="utf-8", newline="\n")
            (d / "p.patch").write_text(patch, encoding="utf-8", newline="\n")
            r = subprocess.run([git, "apply", "--include", target, "p.patch"], cwd=d,
                               capture_output=True, text=True)
            if r.returncode != 0:
                return False, f"{target}: {r.stderr}", {}
            afters[target] = (d / target).read_text(encoding="utf-8")
            r = subprocess.run([git, "apply", "-R", "--include", target, "p.patch"], cwd=d,
                               capture_output=True, text=True)
            if r.returncode != 0 or (d / target).read_text(encoding="utf-8") != text:
                return False, f"{target}: does not reverse cleanly: {r.stderr}", {}
        finally:
            shutil.rmtree(d, ignore_errors=True)
    return True, "", afters


class _Handler:
    def __init__(self):
        self.sent = None

    def _send(self, code, out):
        self.sent = (code, out)
        return self.sent


def t_the_patch():
    if not shutil.which("git"):
        return skip("git is not installed")
    ok, why, after = _rehearse()
    check("web-search.patch applies to what the earlier patches wrote, and reverses", ok, why)
    if not ok:
        return
    hud, gate = after["jarvis_hud.py"], after["jarvis_gate.py"]
    i = hud.index('        if path == "/api/search":')
    get_blk = hud[i:hud.index('        if path == "/api/schedule":', i)]
    i = hud.index('        if route in ("/api/search/settings", "/api/search/test"):')
    post_blk = hud[i:hud.index('        if route in ("/api/schedule/add"', i)]
    for name, b in (("GET", get_blk), ("POST", post_blk)):
        check(f"{name} checks origin and token", "_origin_ok(self)" in b and "_token_ok(self)" in b)
    reset()
    ns = {}
    exec(compile("def f(self, path, _origin_ok, _token_ok):\n" + get_blk, "<GET>", "exec"), ns)
    h = _Handler()
    ns["f"](h, "/api/search", lambda s: True, lambda s: True)
    check("GET runs and answers the six providers and Whoogle",
          h.sent[0] == 200 and [p["id"] for p in h.sent[1]["providers"]] == list(WS.PROVIDERS)
          and h.sent[1]["left_out"][0]["id"] == "whoogle", h.sent)
    ns["f"](h, "/api/search", lambda s: True, lambda s: False)
    check("... 401 without the token", h.sent[0] == 401)
    ns = {"json": json}
    exec(compile("def f(self, route, _origin_ok, _token_ok, _read_body):\n" + post_blk,
                 "<POST>", "exec"), ns)
    h = _Handler()
    ns["f"](h, "/api/search/settings", lambda s: True, lambda s: True,
            lambda s: b'{"provider": "tavily"}')
    check("POST settings runs: one change, at once", h.sent[0] == 200
          and WS.settings()["provider"] == "tavily", h.sent)
    ns["f"](h, "/api/search/settings", lambda s: True, lambda s: True, lambda s: b"{nope")
    check("... not JSON is 400", h.sent[0] == 400)
    ns["f"](h, "/api/search/test", lambda s: True, lambda s: False, lambda s: b"{}")
    check("... 401 without the token", h.sent[0] == 401)
    check("the gate's words: search_the_web outbound, stop_asking_before_every_web_search local",
          '"search_the_web": ("yes", "outbound",' in gate
          and '"stop_asking_before_every_web_search": ("yes", "local",' in gate)
    check("a \"no\" on either card proposes no memory rule",
          '    "search_the_web",         #' in gate and '    "stop_asking_before_every_web_search",    #' in gate)
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    start = ps1.index("$PATCHES = @(")
    names = [l.strip().strip("'") for l in ps1[start:ps1.index("\n)", start)].splitlines()
             if l.strip().startswith("'")]
    check("apply-patches.ps1 applies web-search.patch after the patches it builds on",
          all(names.index(p) < names.index("web-search.patch")
              for p in ("hardware.patch", "schedule.patch")))
    toml = (HERE / "rebuilt" / "jarvis-framework.toml").read_text(encoding="utf-8")
    check("the shipped settings file asks for both",
          re.search(r'^search_the_web\s*=\s*"ask"', toml, re.M)
          and re.search(r'^stop_asking_before_every_web_search\s*=\s*"ask"', toml, re.M))


def t_both_apps_read_the_current_contract():
    # The same shape as test_asks_first.py's: nothing else ran this
    # producer's --check automatically (quality audit 2026-09-27).
    r = subprocess.run([sys.executable, str(REPO / "tools" / "gen_web_search_cases.py"),
                        "--check"], capture_output=True, text=True, timeout=120,
                       env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    check("web-search-cases.json (desktop and phone) is what the backend says today "
          "(python3 tools/gen_web_search_cases.py)", r.returncode == 0, r.stdout + r.stderr)


# --------------------------------------------------------------------------
#   6b. D8 - the picture says what the last LIVE test said, and a switch is
#       tested before it is made (the live campaign of 2026-10-25)
# --------------------------------------------------------------------------

def _ddg_row():
    return next(p for p in WS.view()["providers"] if p["id"] == "duckduckgo")


def t_the_picture_says_what_the_last_live_test_said():
    reset()
    saved = WS._ddgs_installed
    WS._ddgs_installed = lambda: True
    try:
        row = _ddg_row()
        check("DuckDuckGo installed but never tested is NOT ready (D8: it used to be)",
              row["ready"] is False and row["state"] == "untested"
              and "not tested" in row["said"] and row["at_risk"] is True, row)
        check("...and readiness() itself is unchanged, so a search is never blocked by it",
              WS.readiness("duckduckgo") == ("", ""), WS.readiness("duckduckgo"))
        WS.record_test("duckduckgo", False, "no_results")
        row = _ddg_row()
        check("after a live test that found nothing, the picture says so, and when",
              row["ready"] is False and row["state"] == "at_risk"
              and "did not work" in row["said"] and "no results" in row["said"]
              and row["last_test"]["ok"] is False and row["last_test"]["when"], row)
        check("...and it offers the one that works, from the module's own words",
              "SearXNG" in row["said"], row["said"])
        WS.record_test("duckduckgo", True, "works", 5)
        row = _ddg_row()
        check("after a live test that worked, it is ready again",
              row["ready"] is True and row["state"] == "" and row["at_risk"] is False
              and row["last_test"]["ok"] is True and row["last_test"]["results"] == 5, row)
    finally:
        WS._ddgs_installed = saved
    check("a provider's own readiness still wins (Exa with no key is not 'ready')",
          next(p for p in WS.view()["providers"] if p["id"] == "exa")["state"] == "key_missing")
    check("SearXNG is still the default", WS.DEFAULT_PROVIDER == "searxng"
          and WS.view()["default"] == "searxng")
    rec = WS.last_test("duckduckgo")
    check("the record holds a result and a time - never search words, never a key",
          set(rec) == {"ok", "state", "results", "at"}, rec)
    check("it is kept on disk beside the settings, so a restart does not forget it",
          json.loads(WS.last_test_path().read_text(encoding="utf-8"))["duckduckgo"]["ok"] is True)
    WS.forget_last_tests()
    check("...and it can be dropped", WS.last_test("duckduckgo") is None)


def t_choosing_a_provider_tests_it_first_and_keeps_the_old_one():
    reset()
    real = WS.live_test
    saved = WS._ddgs_installed
    calls = []

    def failing(provider, *, s=None):
        calls.append(provider)
        return {"ok": False, "state": "no_results",
                "error": "DuckDuckGo sent back no results.",
                "offer": 'Switch web search to SearXNG (on this PC)? Say "use SearXNG for web '
                         'search".', "tested": True}

    def working(provider, *, s=None):
        calls.append(provider)
        return {"ok": True, "state": "works", "results": 5, "provider": provider,
                "tested": True}
    WS._ddgs_installed = lambda: True
    try:
        WS.live_test = failing
        code, out = WS.handle_settings({"provider": "duckduckgo"})
        check("a switch whose test fails keeps the old provider",
              code == 200 and out["ok"] is False and WS.settings()["provider"] == "searxng"
              and calls == ["duckduckgo"], (code, out, WS.settings()))
        check("...and says why, and that nothing changed",
              "no results" in out["said"] and "still uses SearXNG" in out["said"], out.get("said"))
        check("...and offers the one that works", "SearXNG" in out.get("offer", ""), out)
        calls.clear()
        WS.live_test = working
        code, out = WS.handle_settings({"provider": "duckduckgo"})
        check("a switch whose test works goes through, tested first",
              code == 200 and out["ok"] is True and WS.settings()["provider"] == "duckduckgo"
              and calls == ["duckduckgo"], (code, out, calls))
        calls.clear()
        code, out = WS.handle_settings({"provider": "duckduckgo"})
        check("choosing the one already in use tests nothing", calls == [], calls)
        FakeStore.DATA.clear()
        code, out = WS.handle_settings({"provider": "exa"})
        check("a missing key is not a test: it is chosen, and says what is missing",
              code == 200 and WS.settings()["provider"] == "exa" and "No Exa key" in out["said"],
              out.get("said"))
    finally:
        WS.live_test = real
        WS._ddgs_installed = saved


if __name__ == "__main__":
    for fn in (t_the_why_lines, t_both_apps_say_the_same_words,
               t_plan_opens_no_socket_and_refuses_a_secret,
               t_searxng_results_no_proxy_no_redirect, t_searxng_down_says_so_and_never_falls_back,
               t_a_stalled_searxng_is_reported_fast_and_honestly,
               t_searxng_answering_with_nothing_is_never_a_silent_empty_answer,
               t_the_searxng_address_is_the_owners_own, t_tavily_key_goes_only_to_tavily,
               t_exa_key_goes_only_to_exa, t_brave_key_goes_only_to_brave,
               t_deepseek_parser_errors_and_no_key,
               t_the_keys_stay_on_the_pc,
               t_duckduckgo_only_and_paced, t_settings_and_the_card_to_ask_less,
               t_the_picture_says_what_the_last_live_test_said,
               t_choosing_a_provider_tests_it_first_and_keeps_the_old_one,
               t_test_search_reports_plainly, t_no_card_for_the_owners_own_question,
               t_a_card_when_private_things_could_slip_in, t_only_a_person_s_yes_runs_it,
               t_refusals_that_never_ask, t_recalled_memory_is_read_off_the_facts_block,
               t_saved_facts_ask_only_when_repeated_or_sensitive, t_when_in_doubt_it_asks,
               t_the_word_comparison, t_recalled_facts_are_read_off_the_block,
               t_the_names_layer_is_read_locally,
               t_which_search_without_the_model, t_the_patch,
               t_both_apps_read_the_current_contract):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
