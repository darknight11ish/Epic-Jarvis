"""test_tellme_watches.py - the "Watches" group of 2026-09-28 in
jarvis_tellme.py: "tell me when a search shows something new", "tell me when
the price on <url> drops below X", GitHub watches (CI finishing or failing, a
pull request merging), and "tell me once when a watch breaks".

    python3 backend/test_tellme_watches.py

What it proves, with a clock the test moves by hand, real SQLite files in a
temporary folder, the REAL jarvis_schedule.py, jarvis_tellme.py,
jarvis_search.py and jarvis_quick.py (the search service, the web page,
GitHub and the gate are fakes; no socket opens):

  - each new source is ONE schedule_repeat card that says what is watched,
    where each look goes and what is kept; nothing is looked at before a yes;
  - a search watch goes through the ONE web search the owner chose - never
    another one when it is down (no silent fallback) - its provider is the
    one in Settings, never one an app sent; search words holding a key are
    refused before any card; "Ask before every web search" or web search
    set to "never" refuse it; only fingerprints of result addresses are kept;
  - a price is read by plain code (schema.org JSON-LD, a price <meta> tag,
    else the first price shown), and a match only notifies - nothing buys;
  - a GitHub watch asks api.github.com only, read-only, through the gate as
    github_read; the GitHub key goes in that request's header only and is
    never in the card, an error, the audit log, an event or what is kept;
  - a watch that cannot look tells the owner ONCE (a `broken` event with no
    words), groups the same problem, holds repeats back for hours, and
    clears by itself at the next good look; an urgent watch still rings
    for a match and never for a breakage;
  - the fast path understands the new sentences.

No pytest, no network, no model.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import time
import traceback
import types
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

require_shipped("jarvis_schedule.py", "jarvis_tellme.py", "jarvis_quick.py",
                "jarvis_search.py", "jarvis_local_http.py")

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-tellme-watches-"))
fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = _TMP
fw.LOG_DIR = _TMP
fw.load_framework = lambda: {}
fw.audit_log = lambda *a, **k: None
fw.action_tier = lambda action: "ask"
sys.modules["jarvis_framework"] = fw

import jarvis_schedule as S  # noqa: E402
import jarvis_tellme as TM  # noqa: E402
import jarvis_quick as Q  # noqa: E402
import jarvis_search as WS  # noqa: E402
import jarvis_local_http as LH  # noqa: E402

PASSED, FAILED = [], []
_AUDIT = []
S._audit = lambda event, detail: _AUDIT.append((event, detail))
TM._audit = lambda event, detail: _AUDIT.append((event, detail))

#: Public-looking addresses are "public" here without a real DNS lookup.
_REAL_PRIVATE = LH.private_fetch_problem
LH.private_fetch_problem = lambda url: ("that address leads to this PC" if "127.0.0.1" in url
                                        else "")

def _no_socket(*a, **k):
    raise ConnectionRefusedError("a test never opens a socket")


def _no_http(req, *, local):
    raise ConnectionRefusedError("a test never opens a socket")


WS._HTTP = _no_http

TOKEN = "ghp_TESTtokenNEVERtoBEseen0123456789abcd"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def local(y, mo, d, hh, mm):
    return S.wall_to_epoch(y, mo, d, hh, mm)


def _raises(fn, exc, word=""):
    try:
        fn()
    except exc as e:
        return word.lower() in str(e).lower()
    return False


class Clock:
    def __init__(self, t):
        self.t = float(t)

    def __call__(self):
        return self.t


class Verdict:
    def __init__(self, allowed, tier, outcome):
        self.allowed, self.tier, self.outcome = allowed, tier, outcome


class World:
    """A scheduler with a hand-moved clock and a gate that records, wired
    into jarvis_tellme. `tiers`: a read action's tier (default "auto")."""

    def __init__(self, t, *, answer="approved", name="w", tiers=None):
        self.clock = Clock(t)
        self.events, self.cards, self.reads = [], [], []
        self.answer = answer
        self.tiers = dict(tiers or {})
        path = _TMP / f"{name}-{len(os.listdir(_TMP))}.db"
        self.s = S.Scheduler(path, clock=self.clock, gate=self.gate,
                             tier_of=lambda a: "ask", spawn=lambda fn: fn(),
                             publish=lambda k, d: self.events.append((k, d)))
        S._SCHED = self.s
        # Every way out is a fake that refuses unless a test sets its own:
        # no test here ever opens a socket.
        TM.DEPS = TM.Deps(tier_of=self.tier_of, gate=self.read_gate,
                          tools_enabled=lambda: set(),
                          publish=lambda k, d: self.events.append((k, d)),
                          sched=lambda: self.s, page_fetch=_no_socket,
                          price_fetch=_no_socket, github_get=_no_socket)

    def tier_of(self, action):
        return self.tiers.get(action, "auto")

    def gate(self, action, detail, prompt):
        self.cards.append((action, detail, prompt))
        if self.answer == "approved":
            return Verdict(True, "ask", "approved")
        return Verdict(False, "ask", self.answer)

    def read_gate(self, action, detail, prompt):
        self.reads.append((action, prompt))
        t = self.tier_of(action)
        return Verdict(t == "auto", t, "auto")

    def of(self, state):
        return [d for k, d in self.events if k == "schedule" and d.get("state") == state]

    def look(self, job_id):
        return TM.look(job_id, deps=TM.DEPS, sched=self.s)


def search_settings(**kw):
    """The owner's web search settings file, written as the app would."""
    doc = {"provider": "searxng", "searxng_url": WS.DEFAULT_SEARXNG_URL,
           "ask_every_time": False}
    doc.update(kw)
    WS.settings_path().write_text(json.dumps(doc), encoding="utf-8")


def _results(*urls):
    return {"ok": True, "provider": "searxng", "query": "x",
            "results": [{"title": "t", "url": u, "snippet": "s"} for u in urls]}


# --------------------------------------------------------------------------
#   The words and the rule
# --------------------------------------------------------------------------

def t_minutes_said_as_hours_and_days():
    rw = S.rule_words
    check("every 5 minutes stays", rw({"every": "minutes", "minutes": 5}) == "every 5 minutes")
    check("60 minutes is every hour", rw({"every": "minutes", "minutes": 60}) == "every hour")
    check("360 minutes is every 6 hours",
          rw({"every": "minutes", "minutes": 360}) == "every 6 hours")
    check("1440 minutes is every day", rw({"every": "minutes", "minutes": 1440}) == "every day")
    check("10080 minutes is every 7 days",
          rw({"every": "minutes", "minutes": 10080}) == "every 7 days")
    check("90 minutes stays in minutes", rw({"every": "minutes", "minutes": 90})
          == "every 90 minutes")


def t_the_rule_for_each_new_source():
    now = local(2026, 9, 28, 12, 0)
    search = {"source": "search", "words": "kokoro voices"}
    r = TM.check_rule({"every": "minutes", "watch": search}, now)
    check("a search looks once a day by default", r["minutes"] == 24 * 60)
    check("... every 6 hours at the most often",
          _raises(lambda: TM.check_rule({"every": "minutes", "minutes": 300, "watch": search},
                                        now), ValueError, "every 6 hours"))
    check("... once a week at the least",
          _raises(lambda: TM.check_rule({"every": "minutes", "minutes": 7 * 1440 + 60,
                                         "watch": search}, now), ValueError, "every 7 days"))
    price = {"source": "price", "url": "https://shop.example.com/kettle", "below": 25}
    check("a price looks every hour by default",
          TM.check_rule({"every": "minutes", "watch": price}, now)["minutes"] == 60)
    gh = {"source": "github", "repo": "darknight11ish/Epic-Jarvis", "event": "ci_failed"}
    r = TM.check_rule({"every": "minutes", "watch": gh}, now)
    check("GitHub every 10 minutes by default and at the most often",
          r["minutes"] == 10 and _raises(lambda: TM.check_rule(
              {"every": "minutes", "minutes": 5, "watch": gh}, now), ValueError))


def t_check_watch_new_sources():
    w = TM.check_watch({"source": "search", "words": '  "Kokoro   voices" ', "urgent": True})
    check("search: the words tidied, quotes off", w["words"] == "Kokoro voices"
          and w["urgent"] is True and w["once"] is True)
    check("search: empty words refused",
          _raises(lambda: TM.check_watch({"source": "search", "words": " "}), ValueError))
    check("search: an unknown provider refused",
          _raises(lambda: TM.check_watch({"source": "search", "words": "x",
                                          "provider": "bing"}), ValueError))
    p = TM.check_watch({"source": "price", "url": "https://shop.example.com/k",
                        "below": "1,299.99", "currency": "£"})
    check("price: '1,299.99' read as a number, the sign kept for the words",
          p["below"] == 1299.99 and p["currency"] == "£")
    for bad in ({"source": "price", "url": "https://x.example/", "below": 0},
                {"source": "price", "url": "https://x.example/", "below": "cheap"},
                {"source": "price", "url": "ftp://x.example/", "below": 3},
                {"source": "price", "url": "https://x.example/ a", "below": 3}):
        check(f"price: refused {bad!r}", _raises(lambda: TM.check_watch(bad), ValueError))
    g = TM.check_watch({"source": "github", "repo": "https://github.com/o-1/r.x.git",
                        "event": "ci_done", "branch": "feature/x"})
    check("github: a github.com address or .git is tidied to owner/name",
          g["repo"] == "o-1/r.x" and g["branch"] == "feature/x")
    pr = TM.check_watch({"source": "github", "repo": "o/r", "event": "pr_merged", "pr": "#12",
                         "once": False})
    check("github: a pull request is by number, and always tells once",
          pr["pr"] == 12 and pr["once"] is True and "branch" not in pr)
    for bad in ({"source": "github", "repo": "o", "event": "ci_done"},
                {"source": "github", "repo": "o/../r", "event": "ci_done"},
                {"source": "github", "repo": "o/r", "event": "deploy"},
                {"source": "github", "repo": "o/r", "event": "pr_merged"},
                {"source": "github", "repo": "o/r", "event": "ci_done", "branch": "a..b"},
                {"source": "github", "repo": "o/r", "event": "ci_done", "branch": "-x"}):
        check(f"github: refused {bad!r}", _raises(lambda: TM.check_watch(bad), ValueError))


def t_parse_number_and_price_of():
    cases = {"25": 25.0, "1,299.99": 1299.99, "1.299,99": 1299.99, "24,99": 24.99,
             "1,299": 1299.0, "£30": 30.0, "30 EUR": 30.0, "0.99": 0.99, "cheap": None,
             "": None, "1.299": 1299.0}
    for text, want in cases.items():
        check(f"parse_number({text!r}) == {want}", TM.parse_number(text) == want,
              TM.parse_number(text))
    ld = (b'<html><head><script type="application/ld+json">{"@context":"https://schema.org",'
          b'"@type":"Product","name":"Kettle","offers":{"@type":"Offer","price":"29.99",'
          b'"priceCurrency":"GBP"}}</script></head><body><p>Was \xc2\xa350</p></body></html>')
    check("the price marked for machines wins over a price shown in the text",
          TM.price_of(ld, "text/html; charset=utf-8") == 29.99)
    graph = (b'<script type="application/ld+json">{"@graph":[{"@type":"WebPage"},'
             b'{"@type":"Product","offers":[{"@type":"AggregateOffer","lowPrice":12.5}]}]}'
             b'</script>')
    check("... also inside @graph, and an AggregateOffer's lowPrice",
          TM.price_of(graph, "text/html") == 12.5)
    meta = b'<html><head><meta content="45.00" property="product:price:amount"></head></html>'
    check("a price <meta> tag, attributes in either order", TM.price_of(meta, "text/html") == 45)
    shown = (b"<html><body><h1>Kettle</h1><script>var p='\xc2\xa31';</script>"
             b"<p>Now \xc2\xa324.50 - free delivery over \xc2\xa320</p></body></html>")
    check("else the first price SHOWN (never one inside a script)",
          TM.price_of(shown, "text/html; charset=utf-8") == 24.5)
    check("no price: None", TM.price_of(b"<p>Sold out</p>", "text/html") is None)
    check("broken JSON-LD is skipped, not a crash",
          TM.price_of(b'<script type="application/ld+json">{nope</script><p>$9</p>',
                      "text/html") == 9)


# --------------------------------------------------------------------------
#   A search
# --------------------------------------------------------------------------

def t_search_one_card_and_its_words():
    search_settings()
    now = local(2026, 9, 28, 12, 0)
    w = World(now, name="scard")
    j = TM.add({"source": "search", "words": "Kokoro voices", "provider": "brave"}, sched=w.s)
    check("ONE schedule_repeat card", len(w.cards) == 1 and w.cards[0][0] == "schedule_repeat")
    prompt = w.cards[0][2]
    check("the card: the exact words, the provider, once a day, what leaves, what is kept",
          "“Kokoro voices”" in prompt and "SearXNG" in prompt
          and "every day" in prompt and "127.0.0.1:8888" in prompt
          and "fingerprint of each address" in prompt and "outside text" in prompt
          and "never sent to the AI model" in prompt, prompt)
    _r, rule, watch = TM._watch_of(j["id"], w.s)
    check("the provider is the one chosen in Settings, never the one an app sent",
          watch["provider"] == "searxng", watch)
    check("its words in Coming up",
          w.s.job(j["id"])["text"] == "a search for “Kokoro voices” shows something new")
    w2 = World(now, name="ssecret")
    check("search words holding a key are refused before any card",
          _raises(lambda: TM.add({"source": "search", "words": f"token {TOKEN}"}, sched=w2.s),
                  ValueError) and w2.cards == [])
    search_settings(ask_every_time=True)
    w3 = World(now, name="sask")
    check("'Ask before every web search' on: refused, with the reason, no card",
          _raises(lambda: TM.add({"source": "search", "words": "x y"}, sched=w3.s),
                  OverflowError, "ask before every web search") and w3.cards == [])
    search_settings()
    w4 = World(now, name="snever", tiers={WS.ACTION_SEARCH: "never"})
    check("web search set to never: refused, no card",
          _raises(lambda: TM.add({"source": "search", "words": "x y"}, sched=w4.s),
                  OverflowError, "switched off") and w4.cards == [])
    search_settings(provider="brave")
    w5 = World(now, name="skey")
    check("Brave chosen but no key saved: refused with the provider's own reason",
          _raises(lambda: TM.add({"source": "search", "words": "x y"}, sched=w5.s),
                  OverflowError, "key") and w5.cards == [])
    search_settings()
    w6 = World(now, name="smax")
    w6.s._spawn = lambda fn: None
    for i in range(TM.MAX_SEARCH_WATCHES):
        TM.add({"source": "search", "words": f"thing {i}"}, sched=w6.s)
    check(f"at most {TM.MAX_SEARCH_WATCHES} search watches",
          _raises(lambda: TM.add({"source": "search", "words": "one more"}, sched=w6.s),
                  OverflowError, "watching a web search"))
    S._SCHED = None


def t_search_a_new_address_only_notifies():
    search_settings()
    now = local(2026, 9, 28, 12, 0)
    w = World(now, name="slook")
    answers = {"out": _results("https://example.com/a", "https://www.example.org/b/")}
    asked = []
    TM.DEPS.search_run = lambda plan: (asked.append((plan.provider, plan.query))
                                       or answers["out"])
    j = TM.add({"source": "search", "words": "kokoro voices", "urgent": True, "once": False},
               sched=w.s)
    jid = j["id"]
    out = w.look(jid)
    check("the first look only notes what is there", out["matched"] == 0 and w.of("matched") == [])
    check("... with the owner's words, through the chosen provider",
          asked == [("searxng", "kokoro voices")], asked)
    st = TM._state(jid, w.s)["last_state"]
    check("only fingerprints are kept - no address, no title",
          st.startswith("s1:searxng:") and "example" not in st and "http" not in st, st)
    answers["out"] = _results("http://example.com/a?utm_source=x", "https://example.org/b")
    check("the same pages, spelt differently (www, https, a closing /, tracking tags): "
          "nothing new", w.look(jid)["matched"] == 0 and w.of("matched") == [])
    answers["out"] = _results("https://example.com/a", "https://new.example.net/c",
                              "https://new.example.net/d")
    out = w.look(jid)
    check("two new addresses: ONE match, and it only notifies",
          out["matched"] == 2 and len(w.of("matched")) == 1
          and w.of("matched")[0] == {"id": jid, "kind": "tellme", "state": "matched",
                                     "urgent": True}, w.events)
    f = TM.fields(jid)
    check("the notice is the owner's words, never a result's",
          f["alert"] == "Your search for “kokoro voices” shows 2 new results."
          and "example" not in f["alert"], f)
    answers["out"] = _results("https://new.example.net/c")
    check("an address seen before, back again: not new", w.look(jid)["matched"] == 0)
    search_settings(provider="duckduckgo")
    answers["out"] = _results("https://other.example/z")
    TM.DEPS.search_run = lambda plan: answers["out"]
    import jarvis_search as _ws
    _ws._ddgs_installed = lambda: True
    check("the owner chose another web search: that one is used, and the look only "
          "re-records (another provider's results are not comparable)",
          w.look(jid)["matched"] == 0
          and TM._state(jid, w.s)["last_state"].startswith("s1:duckduckgo:"))
    check("results are never learned from: no memory or learning module is touched",
          "jarvis_memory" not in (HERE / "jarvis_tellme.py").read_text(encoding="utf-8")
          and "jarvis_auto_learn" not in (HERE / "jarvis_tellme.py").read_text(encoding="utf-8"))
    search_settings()
    TM.DEPS.search_run = None
    S._SCHED = None


def t_search_never_falls_back_to_another_provider():
    """The owner's rule (2026-09-25): no silent fallback. SearXNG is down:
    the look says so and offers to switch; nothing is sent anywhere else."""
    search_settings()
    now = local(2026, 9, 28, 12, 0)
    w = World(now, name="sdown")
    sent = []

    def http(req, *, local):
        sent.append(req.full_url)
        raise ConnectionRefusedError("nothing listening")

    WS._HTTP = http
    try:
        j = TM.add({"source": "search", "words": "kokoro voices"}, sched=w.s)
        out = w.look(j["id"])
        said = TM._state(j["id"], w.s)["look_said"]
        check("the look says the chosen provider is down, and offers to switch",
              out["matched"] == 0 and said.startswith("Could not look: SearXNG isn't running")
              and "Switch web search to DuckDuckGo?" in said, said)
        check("only SearXNG was asked - no other search service",
              sent and all(u.startswith(WS.DEFAULT_SEARXNG_URL) for u in sent), sent)
        check("a daily watch that cannot look tells the owner at once (a `broken` event, "
              "no words)", w.of("broken") == [{"id": j["id"], "kind": "tellme",
                                               "state": "broken"}], w.events)
        f = TM.fields(j["id"])
        check("... its notice names the watch in the owner's words and the reason",
              f["broken"].startswith("Your \"tell me when\" (a search for “kokoro voices"
                                     "” shows something new) cannot look right now. "
                                     "SearXNG isn't running")
              and f["broken_at"] == now, f)
    finally:
        WS._HTTP = _no_http
        S._SCHED = None


# --------------------------------------------------------------------------
#   A price
# --------------------------------------------------------------------------

def t_price_card_and_look():
    now = local(2026, 9, 28, 12, 0)
    w = World(now, name="price")
    page = {"price": 30.0}
    TM.DEPS.price_fetch = lambda url: page["price"]
    try:
        check("a private address is refused before any card",
              _raises(lambda: TM.add({"source": "price", "url": "http://127.0.0.1/x",
                                      "below": 5}, sched=w.s), ValueError) and w.cards == [])
        j = TM.add({"source": "price", "url": "https://shop.example.com/kettle", "below": 25,
                    "currency": "£", "once": False}, sched=w.s)
        prompt = w.cards[-1][2]
        check("the card: the address, the number, plain code, never buys",
              "https://shop.example.com/kettle" in prompt and "below £25" in prompt
              and "plain code, never the AI model" in prompt and "never buys" in prompt,
              prompt)
        jid = j["id"]
        check("above the number: nothing", w.look(jid)["matched"] == 0)
        check("each look goes through the gate as page_read",
              w.reads and w.reads[-1][0] == "page_read")
        check("the line under it shows the price it read",
              "Price at the last look: £30." in TM.note(jid), TM.note(jid))
        page["price"] = 22.5
        check("below it now: ONE match", w.look(jid)["matched"] == 1 and len(w.of("matched")) == 1)
        check("the notice says the owner's number and the one read",
              TM.fields(jid)["alert"] == "The price on https://shop.example.com/kettle is below "
                                         "£25. It is now £22.50.", TM.fields(jid))
        check("still below: not told again", w.look(jid)["matched"] == 0)
        page["price"] = 26
        w.look(jid)
        page["price"] = 20
        check("up, then below again: told again (every time)", w.look(jid)["matched"] == 1)
        page["price"] = None
        w.look(jid)
        check("no price on the page: said under the watch",
              TM._state(jid, w.s)["look_said"] == "Could not look: Jarvis could not find a "
                                                 "price on that page.")
        w2 = World(now, name="price2")
        TM.DEPS.price_fetch = lambda url: 10.0
        j2 = TM.add({"source": "price", "url": "https://shop.example.com/b", "below": 12},
                    sched=w2.s)
        check("already below at the first look: told at once",
              w2.look(j2["id"])["matched"] == 1)
        w3 = World(now, name="pricemax")
        w3.s._spawn = lambda fn: None
        for i in range(TM.MAX_PAGE_WATCHES - 1):
            TM.add({"source": "page", "url": f"https://example.com/{i}"}, sched=w3.s)
        TM.add({"source": "price", "url": "https://example.com/p", "below": 3}, sched=w3.s)
        check("page and price watches share the limit of 5 (each fetches someone else's "
              "server)", _raises(lambda: TM.add({"source": "price", "url": "https://e.com/q",
                                                  "below": 3}, sched=w3.s), OverflowError))
    finally:
        TM.DEPS.price_fetch = _no_socket
        S._SCHED = None


# --------------------------------------------------------------------------
#   GitHub
# --------------------------------------------------------------------------

class GitHub:
    """api.github.com, faked: url -> (status, doc)."""

    def __init__(self):
        self.answer = (200, {"workflow_runs": []})
        self.asked = []

    def get(self, url):
        self.asked.append(url)
        return self.answer


def runs(*rows):
    return (200, {"workflow_runs": [{"head_sha": sha, "status": status, "conclusion": concl}
                                    for sha, status, concl in rows]})


def t_github_card_never_shows_the_key():
    now = local(2026, 9, 28, 12, 0)
    os.environ[TM.GITHUB_TOKEN_ENV] = TOKEN
    try:
        w = World(now, name="ghcard")
        TM.add({"source": "github", "repo": "darknight11ish/Epic-Jarvis", "event": "ci_failed",
                "branch": "main"}, sched=w.s)
        prompt = w.cards[-1][2]
        check("the card: the one GET in full, read-only, the key's rule - never the key",
              "GET https://api.github.com/repos/darknight11ish/Epic-Jarvis/actions/runs?"
              "per_page=20&branch=main" in prompt and "Nothing on GitHub is changed" in prompt
              and "api.github.com only" in prompt and TOKEN not in prompt, prompt)
        w2 = World(now, name="ghtier", tiers={"github_read": "ask"})
        check("github_read not 'auto': refused, and it says which line to add",
              _raises(lambda: TM.add({"source": "github", "repo": "o/r", "event": "ci_done"},
                                     sched=w2.s), OverflowError, 'github_read = "auto"')
              and w2.cards == [])
        del os.environ[TM.GITHUB_TOKEN_ENV]
        w3 = World(now, name="ghnokey")
        TM.add({"source": "github", "repo": "o/r", "event": "pr_merged", "pr": 7}, sched=w3.s)
        check("no key: the card says only public repositories can be seen",
              "only public repositories" in w3.cards[-1][2])
    finally:
        os.environ.pop(TM.GITHUB_TOKEN_ENV, None)
        S._SCHED = None


def t_github_ci_finishes_and_fails():
    now = local(2026, 9, 28, 12, 0)
    w = World(now, name="ghci")
    gh = GitHub()
    TM.DEPS.github_get = gh.get
    try:
        done = TM.add({"source": "github", "repo": "o/r", "event": "ci_done", "branch": "main",
                       "once": False}, sched=w.s)["id"]
        fail = TM.add({"source": "github", "repo": "o/r", "event": "ci_failed"}, sched=w.s)["id"]
        gh.answer = runs(("aaaa1111", "in_progress", None), ("aaaa1111", "completed", "success"))
        check("first looks only record", w.look(done)["matched"] == 0
              and w.look(fail)["matched"] == 0)
        check("each look goes through the gate as github_read, to api.github.com",
              all(a == "github_read" for a, _p in w.reads)
              and all(u.startswith("https://api.github.com/repos/o/r/") for u in gh.asked))
        gh.answer = runs(("aaaa1111", "completed", "failure"),
                         ("aaaa1111", "completed", "success"))
        check("every run for the commit finished: 'finishes' matches once",
              w.look(done)["matched"] == 1)
        check("... and says something failed - fixed words, never GitHub's own",
              TM.fields(done)["alert"] == "CI finished on o/r (branch main): something "
                                         "failed.", TM.fields(done))
        check("a run failed: 'fails' matches", w.look(fail)["matched"] == 1
              and TM.fields(fail)["alert"] == "CI failed on o/r.")
        check("... and, told once, it ends", w.s.job(fail)["state"] != "active")
        check("same commit, same result: not told again", w.look(done)["matched"] == 0)
        gh.answer = runs(("bbbb2222", "queued", None))
        check("a new commit, still running: nothing", w.look(done)["matched"] == 0)
        gh.answer = runs(("bbbb2222", "completed", "success"))
        check("it finishes: told again, 'everything passed'", w.look(done)["matched"] == 1
              and TM.fields(done)["alert"].endswith("everything passed."))
        st = TM._state(done, w.s)["last_state"]
        check("only the commit's start and fixed words are kept", st == "g1:bbbb2222:done:ok", st)
    finally:
        TM.DEPS.github_get = _no_socket
        S._SCHED = None


def t_github_pull_request():
    now = local(2026, 9, 28, 12, 0)
    w = World(now, name="ghpr")
    gh = GitHub()
    TM.DEPS.github_get = gh.get
    try:
        jid = TM.add({"source": "github", "repo": "o/r", "event": "pr_merged", "pr": 12},
                     sched=w.s)["id"]
        gh.answer = (200, {"state": "open", "merged": False})
        check("open: nothing", w.look(jid)["matched"] == 0)
        check("it asks /pulls/12", gh.asked[-1] == "https://api.github.com/repos/o/r/pulls/12")
        gh.answer = (200, {"state": "closed", "merged": True})
        check("merged: ONE match", w.look(jid)["matched"] == 1 and len(w.of("matched")) == 1)
        check("the notice", TM.fields(jid)["alert"] == "Pull request #12 on o/r was merged.")
        w2 = World(now, name="ghpr2")
        TM.DEPS.github_get = gh.get
        j2 = TM.add({"source": "github", "repo": "o/r", "event": "pr_merged", "pr": 13},
                    sched=w2.s)["id"]
        gh.answer = (200, {"state": "closed", "merged": False})
        check("closed without merging: told too (it never will merge)",
              w2.look(j2)["matched"] == 1 and TM.fields(j2)["alert"]
              == "Pull request #13 on o/r was closed without being merged.")
        w3 = World(now, name="ghpr404")
        TM.DEPS.github_get = gh.get
        j3 = TM.add({"source": "github", "repo": "o/private", "event": "pr_merged", "pr": 1},
                    sched=w3.s)["id"]
        gh.answer = (404, None)
        w3.look(j3)
        said = TM._state(j3, w3.s)["look_said"]
        check("404: said in plain words - it may be private with no key",
              said.startswith("Could not look: GitHub says there is no such repository")
              and "private" in said, said)
    finally:
        TM.DEPS.github_get = _no_socket
        S._SCHED = None


class _Resp:
    status = 200

    def __init__(self, body):
        self.body = body

    def read(self, n=-1):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def t_github_key_goes_to_api_github_com_only_and_is_never_logged():
    sent = []

    class Opener:
        def open(self, req, timeout=None):
            sent.append((req.full_url, dict(req.header_items())))
            return _Resp(b'{"state": "open", "merged": false}')

    real = LH.opener_for
    LH.opener_for = lambda url, *h: Opener()
    os.environ[TM.GITHUB_TOKEN_ENV] = TOKEN
    try:
        status, doc = TM._default_github_get("https://api.github.com/repos/o/r/pulls/1")
        headers = sent[-1][1]
        check("the key goes in that request's Authorization header",
              status == 200 and headers.get("Authorization") == f"Bearer {TOKEN}", headers)
        check("any other address is refused before anything is sent",
              _raises(lambda: TM._default_github_get("https://evil.example/repos/o/r"),
                      ValueError) and len(sent) == 1)
        h = TM._GitHubNoRedirect()
        req = urllib.request.Request("https://api.github.com/repos/o/r/pulls/1")
        check("a redirect is refused, never followed (it would carry the key)",
              _raises(lambda: h.redirect_request(req, None, 302, "Found", {},
                                                 "https://evil.example/"), Exception))
        # A whole watch's life with the key set: nothing of it anywhere.
        now = local(2026, 9, 28, 12, 0)
        w = World(now, name="ghkey")
        answers = iter([(200, {"state": "open"}), (500, None), (500, None),
                        (200, {"merged": True})])
        TM.DEPS.github_get = lambda url: next(answers)
        _AUDIT.clear()
        jid = TM.add({"source": "github", "repo": "o/r", "event": "pr_merged", "pr": 2},
                     sched=w.s)["id"]
        for _ in range(4):
            w.look(jid)
        blob = json.dumps([_AUDIT, w.events, w.cards, w.reads, TM.note(jid), TM.fields(jid),
                           TM._state(jid, w.s)], default=str)
        check("the key is in no card, audit line, event, note, field or kept state",
              TOKEN not in blob and "Bearer" not in blob)
        db = (Path(w.s.path)).read_bytes()
        check("... and not in schedule.db", TOKEN.encode() not in db)
    finally:
        LH.opener_for = real
        os.environ.pop(TM.GITHUB_TOKEN_ENV, None)
        TM.DEPS.github_get = _no_socket
        S._SCHED = None


# --------------------------------------------------------------------------
#   A watch that breaks
# --------------------------------------------------------------------------

def t_a_broken_watch_is_told_once_and_clears():
    now = local(2026, 9, 28, 12, 0)
    w = World(now, name="broken")
    page = {"fail": None, "print": "t1:aaa"}

    def fetch(url):
        if page["fail"]:
            raise page["fail"]
        return page["print"]

    TM.DEPS.page_fetch = fetch
    try:
        jid = TM.add({"source": "page", "url": "https://example.com/news", "urgent": True},
                     sched=w.s)["id"]
        w.look(jid)
        page["fail"] = TimeoutError()
        w.clock.t += 1800
        w.look(jid)
        check("one failed look of a watch that looks every 30 minutes: not told yet",
              w.of("broken") == [])
        page["fail"] = ConnectionRefusedError()
        w.clock.t += 1800
        w.look(jid)
        check("the same problem again (another bracketed detail): told ONCE, with no words",
              w.of("broken") == [{"id": jid, "kind": "tellme", "state": "broken"}], w.events)
        check("... and it never rings, even on an urgent watch",
              "urgent" not in w.of("broken")[0])
        f = TM.fields(jid)
        check("its words, by id", f["broken"] == "Your \"tell me when\" (https://example.com/news "
              "changes) cannot look right now. The page did not answer (ConnectionRefusedError).",
              f)
        check("the line under it says it told you, and that it clears by itself",
              "that it cannot look; that clears by itself" in TM.note(jid), TM.note(jid))
        for _ in range(5):
            w.clock.t += 1800
            w.look(jid)
        check("still broken for hours: repeats held back", len(w.of("broken")) == 1)
        w.clock.t += TM.BROKEN_AGAIN_HOURS * 3600
        w.look(jid)
        check(f"after {TM.BROKEN_AGAIN_HOURS} hours still broken: told again",
              len(w.of("broken")) == 2)
        page["fail"] = None
        w.clock.t += 1800
        w.look(jid)
        st = TM._state(jid, w.s)
        check("the next good look clears it silently",
              st["broken_kind"] is None and st["broken_told"] is None and len(w.of("broken")) == 2
              and "broken" not in TM.fields(jid))
        check("... and the audit log says so, without words",
              any(e == "tellme.broken.cleared" and d == {"id": jid, "source": "page"}
                  for e, d in _AUDIT))
        page["fail"] = TimeoutError()
        for _ in range(2):
            w.clock.t += 1800
            w.look(jid)
        check("broken again later: a new notice (the old one was cleared)",
              len(w.of("broken")) == 3)
        TM.DEPS.page_fetch = lambda url: (_ for _ in ()).throw(TimeoutError())
        w.tiers["page_read"] = "ask"
        w.clock.t += 1800
        w.look(jid)
        w.clock.t += 1800
        w.look(jid)
        check("a different problem (the setting changed): told about that one",
              len(w.of("broken")) == 4)
        page["fail"] = None
        w.tiers["page_read"] = "auto"
        TM.DEPS.page_fetch = lambda url: "t1:bbb"
        w.clock.t += 1800
        out = w.look(jid)
        check("an urgent match still rings as before",
              out["matched"] == 1 and w.of("matched")[-1]["urgent"] is True)
    finally:
        TM.DEPS.page_fetch = _no_socket
        S._SCHED = None


def t_an_older_table_gets_the_new_columns():
    path = _TMP / "old-schedule.db"
    c = sqlite3.connect(path)
    c.executescript("""
        CREATE TABLE tellme (id TEXT PRIMARY KEY, base_uid INTEGER, uidvalidity INTEGER,
            last_state TEXT, looked_at REAL, look_said TEXT NOT NULL DEFAULT '',
            matched_at REAL, matched_n INTEGER NOT NULL DEFAULT 0,
            alert_count INTEGER NOT NULL DEFAULT 0);
        INSERT INTO tellme (id, last_state) VALUES ('s0123456789', 'on');
    """)
    c.commit()
    c.close()
    fake = types.SimpleNamespace(path=str(path))
    TM._save("s0123456789", fake, broken_kind="x", broken_n=1)
    st = TM._state("s0123456789", fake)
    check("a PC that already had watches keeps them, and gains the new columns",
          st["last_state"] == "on" and st["broken_kind"] == "x" and st["broken_n"] == 1, st)


# --------------------------------------------------------------------------
#   Said or typed
# --------------------------------------------------------------------------

def t_the_fast_path_understands_the_new_watches():
    now = local(2026, 9, 28, 12, 0)
    cases = {
        "tell me when a search for Kokoro voices shows something new":
            ("tellme_search", {"words": "Kokoro voices", "minutes": None}),
        'let me know when a web search for "RTX 2060 12GB price" finds anything new, '
        "every 12 hours": ("tellme_search", {"words": "RTX 2060 12GB price", "minutes": 720}),
        "tell me when there's something new about Tauri 3":
            ("tellme_search", {"words": "Tauri 3"}),
        "tell me when the price on https://shop.example.com/Kettle drops below £25":
            ("tellme_price", {"url": "https://shop.example.com/Kettle", "below": "25",
                              "currency": "£"}),
        "tell me when https://shop.example.com/k goes under 1,299.99 dollars":
            ("tellme_price", {"below": "1,299.99"}),
        "tell me when CI fails on darknight11ish/Epic-Jarvis":
            ("tellme_github", {"repo": "darknight11ish/Epic-Jarvis", "event": "ci_failed",
                               "branch": ""}),
        "urgently tell me when the build on darknight11ish/Epic-Jarvis branch Dev finishes":
            ("tellme_github", {"event": "ci_done", "branch": "Dev", "urgent": True}),
        "tell me when CI finishes on o/r main":
            ("tellme_github", {"repo": "o/r", "event": "ci_done", "branch": "main"}),
        "tell me when PR #12 on darknight11ish/Epic-Jarvis merges":
            ("tellme_github", {"event": "pr_merged", "pr": 12}),
        "tell me when https://github.com/o/r/pull/9 is merged":
            ("tellme_github", {"repo": "o/r", "pr": 9}),
        "tell me when PR 12 merges": ("tellme_help", {"why": "repo"}),
        "tell me when a search for it shows something new": ("tellme_help", {"why": "search"}),
    }
    for text, (name, want) in cases.items():
        got = Q.match(text, now)
        ok = got is not None and got.name == name and all(got.f.get(k) == v
                                                           for k, v in want.items())
        check(f"understood: {text!r}", ok, got and (got.name, got.f))
    for text in ("tell me when the build finishes", "tell me when the tests pass",
                 "tell me when you find something new"):
        got = Q.match(text, now)
        check(f"not a watch: {text!r}", got is None or got.name not in (
            "tellme_github", "tellme_search", "tellme_price"), got and got.name)


def t_the_fast_path_sets_them_up():
    search_settings()
    now = local(2026, 9, 28, 12, 0)
    w = World(now, name="quick")
    w.s._spawn = lambda fn: None
    res = Q.answer("tell me when a search for Kokoro voices shows something new", sched=w.s,
                   now=now)
    j = w.s.listed()[-1]
    check("a search watch: waiting for its card, looks every day",
          j["kind"] == "tellme" and j["state"] == "waiting" and "every day" in res.reply,
          res.reply)
    res = Q.answer("tell me when a search for Kokoro shows something new every 2 hours",
                   sched=w.s, now=now)
    check("too often: said plainly, nothing set up",
          res is not None and len(w.s.listed()) == 1, res and res.reply)
    res = Q.answer("tell me when CI fails on darknight11ish/Epic-Jarvis", sched=w.s, now=now)
    check("a GitHub watch: every 10 minutes",
          w.s.listed()[-1]["text"] == "CI fails on darknight11ish/Epic-Jarvis"
          and "every 10 minutes" in res.reply, (w.s.listed()[-1], res.reply))
    res = Q.answer("tell me when the price on https://shop.example.com/k drops below 25",
                   sched=w.s, now=now)
    check("a price watch: the owner's number", w.s.listed()[-1]["text"]
          == "the price on https://shop.example.com/k drops below 25", w.s.listed()[-1])
    S._SCHED = None


def t_shipped_and_worded_in_both_apps():
    toml = (HERE / "rebuilt" / "jarvis-framework.toml").read_text(encoding="utf-8")
    check("github_read ships as \"auto\" in the settings file",
          any(l.split("#")[0].replace(" ", "") == 'github_read="auto"'
              for l in toml.splitlines()))
    import jarvis_card_words as CW
    check("github_read has a plain title on cards", "github_read" in CW.TITLES
          if hasattr(CW, "TITLES") else "github_read" in (HERE / "jarvis_card_words.py")
          .read_text(encoding="utf-8"))
    for rel in ("jarvis-desktop/src/coming-up.js",
                "jarvis-desktop/src-tauri/src/brain/schedule.rs",
                "jarvis-client/app/src/main/java/com/jarvis/client/net/Schedule.kt"):
        text = (REPO / rel).read_text(encoding="utf-8")
        check(f"{rel.rsplit('/', 1)[-1]} carries the broken-watch lock-screen words",
              TM.BROKEN_LOCK_SCREEN.replace('"', '\\"') in text
              or TM.BROKEN_LOCK_SCREEN in text)


def main():
    orig_tz = os.environ.get("TZ")
    os.environ["TZ"] = "Europe/London"
    if hasattr(time, "tzset"):
        time.tzset()
    try:
        for name, fn in list(globals().items()):
            if name.startswith("t_") and callable(fn):
                print(f"--- {name} ---")
                try:
                    fn()
                except Exception as exc:  # pragma: no cover
                    traceback.print_exc()
                    check(f"{name} ran without crashing", False, repr(exc))
    finally:
        S._SCHED = None
        LH.private_fetch_problem = _REAL_PRIVATE
        if orig_tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = orig_tz
        if hasattr(time, "tzset"):
            time.tzset()
        import shutil
        shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
