"""test_news.py - news headlines in the morning briefing (jarvis_news.py,
news.patch; the owner's decision of 2026-09-27, feasibility I49).

    python3 backend/test_news.py

Runs anywhere; no model, no real network (fetches are injected). What it
proves:

1. The list is empty by default; a damaged file means no feeds, no news.
2. Adding: ONE card (change_own_config, tier "ask" only) that names the
   feed - only a person's "approved" adds it; refused for a bad address, a
   duplicate, and (with a fake resolver) an address that resolves to a
   private network. Removing is at once, and withdraws a waiting card for
   the same feed.
3. Headlines: RSS and Atom both parse, capped at MAX_HEADLINES_PER_FEED and
   MAX_HEADLINE_CHARS, a DOCTYPE/ENTITY document is refused outright, and a
   feed that will not parse gives no headlines rather than raising.
4. Reading a feed: refused at any tier but auto/notify (news does not raise
   a card per read), and refused again by the private-address check
   immediately before the fetch, not only when the feed was added.
5. read_news(): the briefing's section shape, aggregating every listed feed
   and saying how many did not answer without naming which.
6. jarvis_quick.py's fast path ("read me the news") marks the answer as
   having read outside text (news_read); jarvis_briefing.py's News section
   and its sources() line agree with jarvis_news's own state.
7. The route and the patch: install() answers /api/news, /api/news/add and
   /api/news/remove after the server's own checks and passes everything
   else on; news.patch applies after the rest of the stack and reverses;
   the module is shipped.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402
require_shipped("jarvis_news.py")
import _stack  # noqa: E402
import jarvis_news as NW  # noqa: E402
import jarvis_quick as Q  # noqa: E402

FAILED, PASSED = [], []
TMP = Path(tempfile.mkdtemp(prefix="jarvis-news-"))
CONF = TMP / "config"
CONF.mkdir()
NW._config_dir = lambda: CONF


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond
                                                        else ""))


class Verdict:
    def __init__(self, allowed, outcome, tier="ask"):
        self.allowed, self.outcome, self.tier = allowed, outcome, tier
        self.reason = outcome


def run_now(fn):
    fn()


def fresh():
    NW._reset_for_tests()
    try:
        NW.settings_path().unlink()
    except FileNotFoundError:
        pass


RSS = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>Example News</title>
<item><title>First headline</title><link>http://example.com/1</link></item>
<item><title>Second   headline</title></item>
<item><title>Third</title></item><item><title>Fourth</title></item>
<item><title>Fifth</title></item><item><title>Sixth (never shown - cap)</title></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>Atom Feed</title>
<entry><title>Atom headline one</title></entry>
<entry><title>Atom headline two</title></entry>
</feed>"""

DOCTYPE_BOMB = (b'<?xml version="1.0"?><!DOCTYPE rss [<!ENTITY x "y">]>'
                b"<rss><channel><item><title>&x;</title></item></channel></rss>")


def t_empty_by_default_and_damaged_is_none():
    fresh()
    check("no feeds at first", NW.feeds() == [])
    v = NW.view()
    check("view says available and empty", v["available"] and v["feeds"] == []
          and v["why"] == "")
    NW.settings_path().write_text("not json", encoding="utf-8")
    check("damaged file: no feeds, and why is said", NW.feeds() == []
          and NW.load()["why"] == NW._DAMAGED)
    fresh()


def t_check_feed():
    for bad in (None, "", "ftp://x", "not a url", "http://" + "x" * 600, "http://a\x00b"):
        try:
            NW.check_feed(bad)
            check(f"check_feed refuses {bad!r}", False)
        except ValueError:
            check(f"check_feed refuses {bad!r}", True)
    check("check_feed accepts a plain https address",
          NW.check_feed("https://example.com/feed.xml") == "https://example.com/feed.xml")


def t_adding_one_card_only_a_yes_adds():
    fresh()
    calls = []

    def gate_yes(action, detail, prompt):
        calls.append((action, detail))
        return Verdict(True, "approved", "ask")

    code, out = NW.request_add({"url": "https://example.com/feed.xml"}, gate=gate_yes,
                               tier_of=lambda a: "ask", spawn=run_now)
    check("202 and waiting", code == 202 and out["waiting"] is True)
    check("the gate was asked change_own_config, with the full address in the card",
          calls and calls[0][0] == NW.CARD_ACTION
          and "https://example.com/feed.xml" in calls[0][1]["text"])
    check("the card's detail says approving it leads off this PC",
          calls and calls[0][1].get("leaves_this_pc") is True)
    check("added", NW.feeds() == ["https://example.com/feed.xml"])
    check("last outcome is 'added'", NW._P_STATE["last"]["outcome"] == "added")

    # A duplicate is a no-op, not a second card.
    code2, out2 = NW.request_add({"url": "https://example.com/feed.xml"}, gate=gate_yes,
                                 tier_of=lambda a: "ask", spawn=run_now)
    check("adding the same address again changes nothing", code2 == 200
          and out2["changed"] is False)


def t_adding_a_no_or_a_timeout_adds_nothing():
    fresh()
    code, out = NW.request_add({"url": "https://example.com/no.xml"},
                               gate=lambda a, d, p: Verdict(False, "denied"),
                               tier_of=lambda a: "ask", spawn=run_now)
    check("denied: nothing added", NW.feeds() == []
          and NW._P_STATE["last"]["outcome"] == "denied")
    fresh()
    code, out = NW.request_add({"url": "https://example.com/timeout.xml"},
                               gate=lambda a, d, p: Verdict(False, "timed_out"),
                               tier_of=lambda a: "ask", spawn=run_now)
    check("timed out: nothing added", NW.feeds() == []
          and NW._P_STATE["last"]["outcome"] == "timed_out")


def t_adding_refuses_a_private_address():
    fresh()
    code, out = NW.request_add({"url": "http://127.0.0.1:9999/feed"},
                               gate=lambda a, d, p: Verdict(True, "approved", "ask"),
                               tier_of=lambda a: "ask", spawn=run_now)
    check("a loopback address is refused before any card", code == 400 and NW.feeds() == [])


def t_adding_needs_ask_tier():
    fresh()
    code, out = NW.request_add({"url": "https://example.com/feed.xml"},
                               gate=lambda a, d, p: Verdict(True, "approved", "auto"),
                               tier_of=lambda a: "auto", spawn=run_now)
    check("change_own_config must be tier ask, or the add is refused outright",
          code == 503 and NW.feeds() == [])


def t_removing_is_instant_and_withdraws_a_pending_card():
    fresh()
    held = {}

    def gate_hold(action, detail, prompt):
        held["path"] = detail
        return Verdict(True, "approved", "ask")

    NW.request_add({"url": "https://example.com/held.xml"}, gate=gate_hold,
                   tier_of=lambda a: "ask", spawn=lambda fn: held.setdefault("fn", fn))
    check("a card is pending", bool(NW._P_STATE["pending"]))
    code, out = NW.request_remove({"url": "https://example.com/held.xml"})
    check("removing while pending withdraws it", code == 200
          and NW._P_STATE["pending"] == {})
    held["fn"]()
    check("running the withdrawn decision adds nothing",
          NW.feeds() == [] and NW._P_STATE["last"]["outcome"] == "withdrawn")

    NW.request_add({"url": "https://example.com/real.xml"},
                   gate=lambda a, d, p: Verdict(True, "approved", "ask"),
                   tier_of=lambda a: "ask", spawn=run_now)
    code2, out2 = NW.request_remove({"url": "https://example.com/real.xml"})
    check("removing a real one is immediate", code2 == 200 and out2["changed"] is True
          and NW.feeds() == [])
    code3, out3 = NW.request_remove({"url": "https://example.com/real.xml"})
    check("removing again says it was not on the list", out3["changed"] is False)


def t_max_feeds():
    fresh()
    for i in range(NW.MAX_FEEDS):
        NW.request_add({"url": f"https://example.com/{i}.xml"},
                       gate=lambda a, d, p: Verdict(True, "approved", "ask"),
                       tier_of=lambda a: "ask", spawn=run_now)
    check(f"{NW.MAX_FEEDS} feeds fit", len(NW.feeds()) == NW.MAX_FEEDS)
    code, out = NW.request_add({"url": "https://example.com/one-too-many.xml"},
                               gate=lambda a, d, p: Verdict(True, "approved", "ask"),
                               tier_of=lambda a: "ask", spawn=run_now)
    check("one more is refused", code == 409 and len(NW.feeds()) == NW.MAX_FEEDS)
    fresh()


def t_feed_redirect_handler_refuses_a_private_target():
    """_FeedRedirect - the piece read_feed's own private-address check
    cannot see: a feed that answers with a 30x pointing somewhere the
    initial address's own check never covered."""
    import urllib.error
    import urllib.request
    import jarvis_local_http as LH
    h = NW._FeedRedirect()
    req = urllib.request.Request("https://example.com/feed.xml")
    real = LH.private_fetch_problem
    LH.private_fetch_problem = (
        lambda url: "faked as private" if url == "http://127.0.0.1/evil" else "")
    try:
        try:
            h.redirect_request(req, None, 302, "Found", {}, "http://127.0.0.1/evil")
            check("refuses a redirect to a private target", False)
        except urllib.error.HTTPError as exc:
            check("refuses a redirect to a private target", "faked as private" in str(exc))
        out = h.redirect_request(req, None, 302, "Found", {}, "https://example.com/next.xml")
        check("allows and follows a redirect to a public target",
              isinstance(out, urllib.request.Request)
              and out.full_url == "https://example.com/next.xml")
    finally:
        LH.private_fetch_problem = real


def t_parse_headlines():
    check("RSS titles, capped, whitespace collapsed",
          NW.parse_headlines(RSS) == ["First headline", "Second headline", "Third", "Fourth",
                                      "Fifth"])
    check("Atom entries too",
          NW.parse_headlines(ATOM) == ["Atom headline one", "Atom headline two"])
    check("a DOCTYPE/ENTITY document is refused outright, never parsed",
          NW.parse_headlines(DOCTYPE_BOMB) == [])
    check("not XML at all: no headlines, no raise", NW.parse_headlines(b"not xml") == [])
    long_title = ("x" * 500).encode()
    doc = b'<rss><channel><item><title>' + long_title + b'</title></item></channel></rss>'
    check("a very long title is capped", len(NW.parse_headlines(doc)[0]) == NW.MAX_HEADLINE_CHARS)
    check("feed_title reads the channel's own title",
          NW.feed_title(RSS) == "Example News" and NW.feed_title(ATOM) == "Atom Feed")
    check("feed_title also refuses a DOCTYPE document", NW.feed_title(DOCTYPE_BOMB) == "")
    # Security/privacy audit, 2026-09-27: the byte search missed a UTF-16
    # document (a zero byte after every letter), and ElementTree - which
    # reads UTF-16 - then expanded its entities.
    doc16 = ('<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE rss [<!ENTITY x "EXPANDED">]>'
             '<rss><channel><title>&x;</title><item><title>&x;</title></item></channel>'
             '</rss>').encode("utf-16")
    check("a UTF-16 DOCTYPE/ENTITY document is refused too, never parsed",
          NW.parse_headlines(doc16) == [] and NW.feed_title(doc16) == "",
          (NW.parse_headlines(doc16), NW.feed_title(doc16)))
    ok16 = ('<?xml version="1.0" encoding="UTF-16"?><rss><channel><item><title>Plain '
            'UTF-16</title></item></channel></rss>').encode("utf-16")
    check("... while an ordinary UTF-16 feed still reads",
          NW.parse_headlines(ok16) == ["Plain UTF-16"], NW.parse_headlines(ok16))


def t_read_feed_gating():
    deps = NW.Deps(tier_of=lambda a: "ask", fetch=lambda u: RSS)
    out = NW.read_feed("https://example.com/feed.xml", deps=deps)
    check("tier 'ask': refused, no fetch, no card raised",
          out["ok"] is False and "yes each time" in out["why"])

    deps2 = NW.Deps(tier_of=lambda a: "auto", fetch=lambda u: RSS)
    out2 = NW.read_feed("http://127.0.0.1/feed.xml", deps=deps2)
    check("a private address is refused before the fetch", out2["ok"] is False)

    calls = []

    def gate_yes(action, detail, prompt):
        calls.append(action)
        return Verdict(True, "approved", "auto")

    deps3 = NW.Deps(tier_of=lambda a: "auto", gate=gate_yes, fetch=lambda u: RSS)
    out3 = NW.read_feed("https://example.com/feed.xml", deps=deps3)
    check("tier 'auto': fetched, gated as news_read",
          out3["ok"] is True and calls == [NW.GATE_ACTION]
          and out3["headlines"][0] == "First headline")

    deps4 = NW.Deps(tier_of=lambda a: "notify", gate=lambda a, d, p: Verdict(True, "approved"),
                    fetch=lambda u: RSS)
    out4 = NW.read_feed("https://example.com/feed.xml", deps=deps4)
    check("tier 'notify' is accepted too (about once a day, like weather/calendar)",
          out4["ok"] is True)

    def boom(u):
        raise TimeoutError("no answer")

    deps5 = NW.Deps(tier_of=lambda a: "auto", gate=lambda a, d, p: Verdict(True, "approved"),
                    fetch=boom)
    out5 = NW.read_feed("https://example.com/dead.xml", deps=deps5)
    check("a fetch that raises says so plainly, never a traceback",
          out5["ok"] is False and "TimeoutError" in out5["why"])


def t_read_news_aggregates():
    fresh()
    check("no feeds: empty section", NW.read_news()["state"] == "empty")
    NW.request_add({"url": "https://example.com/a.xml"},
                   gate=lambda a, d, p: Verdict(True, "approved", "ask"),
                   tier_of=lambda a: "ask", spawn=run_now)
    NW.request_add({"url": "https://example.com/b.xml"},
                   gate=lambda a, d, p: Verdict(True, "approved", "ask"),
                   tier_of=lambda a: "ask", spawn=run_now)

    def fetch(u):
        return RSS if u.endswith("a.xml") else ATOM

    deps = NW.Deps(tier_of=lambda a: "auto", gate=lambda a, d, p: Verdict(True, "approved"),
                  fetch=fetch)
    sec = NW.read_news(deps=deps)
    check("both feeds' headlines are in one section, labelled by feed",
          sec["state"] == "ok" and len(sec["items"]) == 7
          and any(i.startswith("Example News:") for i in sec["items"]))

    def half_fetch(u):
        if u.endswith("a.xml"):
            raise OSError("down")
        return ATOM

    deps2 = NW.Deps(tier_of=lambda a: "auto", gate=lambda a, d, p: Verdict(True, "approved"),
                   fetch=half_fetch)
    sec2 = NW.read_news(deps=deps2)
    check("one feed down: the other's headlines still show, and the count says so",
          sec2["state"] == "ok" and "1 feed" in sec2["summary"]
          and len(sec2["items"]) == 2)
    fresh()


def t_sentence_marks_outside_text():
    fresh()
    NW.request_add({"url": "https://example.com/a.xml"},
                   gate=lambda a, d, p: Verdict(True, "approved", "ask"),
                   tier_of=lambda a: "ask", spawn=run_now)
    deps = NW.Deps(tier_of=lambda a: "auto", gate=lambda a, d, p: Verdict(True, "approved"),
                  fetch=lambda u: RSS)
    out = NW.sentence(deps=deps)
    check("the answer names the count and lists headlines",
          "First headline" in out["said"])
    check("read names news_read: headlines are outside text", out["read"] == [NW.GATE_ACTION])
    fresh()
    out2 = NW.sentence()
    check("with no feeds, read is empty (nothing was actually read)", out2["read"] == [])


def t_the_fast_path_understands():
    """"Add this feed: <url>", "remove that feed: <url>" and "read me the
    news" from either app, without a dedicated settings screen - the same
    conversational shape "tell me when" already uses."""
    for text, name in (("add this feed: https://example.com/rss.xml", "news_add"),
                       ("add https://example.com/rss.xml as a news feed", "news_add"),
                       ("follow this feed https://example.com/rss.xml", "news_add"),
                       ("remove that feed: https://example.com/rss.xml", "news_remove"),
                       ("what news feeds do i have", "news_list"),
                       ("list my news feeds", "news_list"),
                       ("read me the news", "news_read")):
        got = Q.match(text)
        check(f"{text!r} -> {name}", got is not None and got.name == name, repr(got))
    got = Q.match("add this feed")
    check("no address at all: not ours (nothing to add)", got is None)
    got2 = Q.match("add this feed: https://example.com/rss.xml")
    check("the URL keeps its own case, never lower-cased by normalise()",
          got2.f["url"] == "https://example.com/rss.xml")


def t_the_fast_path_adds_and_removes():
    fresh()
    intent = Q.Intent("news_add", {"url": "https://example.com/fast-path.xml"})
    res = Q.run(intent, None, 0.0)
    check("adding: the answer says a card is waiting, and names nothing back",
          res is not None and "approval card" in res.reply)
    # The list itself: answered without the model, and empty at first.
    res2 = Q.run(Q.Intent("news_list"), None, 0.0)
    check("listing with none actually added yet (the card above never ran)",
          res2 is not None and res2.reply == NW.EMPTY)
    # Clear the waiting card first: only one add is pending at a time, so the
    # second address was refused while the first card was still up and the list
    # stayed empty - the two checks below read as failures although the add
    # path was fine (2026-10-03).
    fresh()
    NW.request_add({"url": "https://example.com/added.xml"},
                   gate=lambda a, d, p: type("V", (), {"allowed": True, "outcome": "approved",
                                                        "tier": "ask"})(),
                   tier_of=lambda a: "ask", spawn=run_now)
    res3 = Q.run(Q.Intent("news_list"), None, 0.0)
    check("listing after a real add: the address is there",
          res3 is not None and "https://example.com/added.xml" in res3.reply)
    res4 = Q.run(Q.Intent("news_remove", {"url": "https://example.com/added.xml"}), None, 0.0)
    check("removing: immediate, no card", res4 is not None and "Removed" in res4.reply)
    check("really gone", NW.feeds() == [])
    fresh()


def t_install_wraps_the_routes():
    fresh()
    hits = []

    class H:
        def __init__(self):
            self.sent = None
            self._body = b"{}"

        def do_GET(self):
            hits.append("get0")

        def do_POST(self):
            hits.append("post0")

        def _send(self, code, out):
            self.sent = (code, out)
            return self.sent

    line = NW.install(H, origin_ok=lambda self: True, token_ok=lambda self: True,
                      read_body=lambda self: self._body)
    check("install returns a banner line naming the feature", "News feeds" in line)

    h = H()
    h.path = "/api/news"
    h.do_GET()
    check("GET /api/news is answered here", h.sent[0] == 200 and h.sent[1]["available"])

    h2 = H()
    h2.path = "/api/something/else"
    h2.do_GET()
    check("any other GET passes through to the original", hits == ["get0"])

    h3 = H()
    h3.path = NW.ADD_ROUTE
    import json as _json
    h3._body = _json.dumps({"url": "not-a-url"}).encode()
    NW._P_STATE["pending"].clear()
    h3.do_POST()
    check("POST /api/news/add is answered here (a bad address: 400)", h3.sent[0] == 400)

    h4 = H()
    h4.path = "/api/something/else"
    h4.do_POST()
    check("any other POST passes through to the original", "post0" in hits)


def _rehearse():
    order = _stack.order()
    if "news.patch" not in order:
        return False, "news.patch is not in apply-patches.ps1's list", None, None
    before_list = order[:order.index("news.patch")]
    patch = (HERE / "news.patch").read_text(encoding="utf-8")
    text, log = _stack.stand_in("jarvis_hud.py", before_list)
    if text is None:
        return False, "; ".join(log), None, None
    git = shutil.which("git")
    if not git:
        return False, "git is not installed", None, None
    d = Path(tempfile.mkdtemp(prefix="jarvis-news-patch-"))
    try:
        (d / "jarvis_hud.py").write_text(text, encoding="utf-8", newline="\n")
        (d / "p.patch").write_text(patch, encoding="utf-8", newline="\n")
        r = subprocess.run([git, "apply", "--include", "jarvis_hud.py", "p.patch"], cwd=d,
                           capture_output=True, text=True)
        if r.returncode != 0:
            return False, r.stderr, None, None
        after = (d / "jarvis_hud.py").read_text(encoding="utf-8")
        r = subprocess.run([git, "apply", "-R", "--include", "jarvis_hud.py", "p.patch"],
                           cwd=d, capture_output=True, text=True)
        if r.returncode != 0 or (d / "jarvis_hud.py").read_text(encoding="utf-8") != text:
            return False, f"does not reverse cleanly: {r.stderr}", None, None
    finally:
        shutil.rmtree(d, ignore_errors=True)
    return True, "", text, after


def t_the_patch():
    if not shutil.which("git"):
        return check("SKIP - git is not installed", True)
    ok, why, before, after = _rehearse()
    check("news.patch applies to what the earlier patches wrote, and reverses", ok, why)
    if not ok:
        return
    i = after.index("# news.patch")
    j = after.index("# Before the main socket", i)
    blk = after[i:j]
    check("the added block passes origin_ok/token_ok/read_body into jarvis_news.install",
          "import jarvis_news" in blk and "origin_ok=_origin_ok" in blk
          and "token_ok=_token_ok" in blk and "read_body=_read_body" in blk)
    try:
        compile("def f(self, bind, Handler):\n" + blk, "<patched block>", "exec")
        check("the patched block compiles", True)
    except SyntaxError as exc:
        check("the patched block compiles", False, str(exc))


if __name__ == "__main__":
    for fn in (t_empty_by_default_and_damaged_is_none, t_check_feed,
               t_adding_one_card_only_a_yes_adds, t_adding_a_no_or_a_timeout_adds_nothing,
               t_adding_refuses_a_private_address, t_adding_needs_ask_tier,
               t_removing_is_instant_and_withdraws_a_pending_card, t_max_feeds,
               t_feed_redirect_handler_refuses_a_private_target,
               t_parse_headlines, t_read_feed_gating, t_read_news_aggregates,
               t_sentence_marks_outside_text, t_the_fast_path_understands,
               t_the_fast_path_adds_and_removes, t_install_wraps_the_routes, t_the_patch):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
