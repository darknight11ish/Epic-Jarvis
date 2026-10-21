"""test_price_sources.py - the F2 scaffold: local SearXNG price mentions and
the two-persona steering probe (owner-approved anti-surveillance stack,
2026-10-21; Gemini doc Slice 2 item 2 / architecture Layer 3).

    python3 backend/test_price_sources.py   (run it through backend/run_suites.py)

Every network call is mocked; nothing here opens a socket, runs a container,
or touches the owner's real settings/audit log. The suite is hermetic: its
config, home and log folders are its own temp dir, and it refuses to run if
those names do not point inside it.

What it proves:
  * DEFAULTS AND THE SWITCH: the SearXNG address is the verified loopback
    127.0.0.1:8888 (equal to `jarvis_search.DEFAULT_SEARXNG_URL`), a
    non-local override falls back to it, and the feature is OFF by default -
    off means ZERO fetches, with one plain sentence;
  * SEARXNG PRICES: one mocked JSON answer -> titles/snippets parsed to
    INTEGER CENTS by `jarvis_tellme`'s own extractor (no second parser),
    results deduped by host+identity URL (tracking parameters ignored), the
    result cap honoured, and the honest failure sentences for down / JSON-off
    / unreadable / no-results;
  * OUTSIDE TEXT: a successful read sets the project's page-watch taint latch
    (`why="price_radar"`); a refused/off read sets nothing;
  * STEERING: two mocked product pages -> `steering_detected` only when BOTH
    probes read a price and they differ; delta in whole cents (negative =
    comparison-shopper view cheaper), `which_persona_lower` named, equal
    prices are not "steering", a failed probe or a page without a readable
    price never guesses, and both probes fetch the SAME canonical URL;
  * DECOUPLING: probe A carries `Referer: https://www.google.com/`, probe B
    carries none, and NEITHER may carry Cookie/ETag/If-None-Match/
    If-Modified-Since/If-Match - even when the injected profile is full of
    them - while both send `Cache-Control: no-cache`;
  * READ-ONLY + SSRF: cart/checkout/order/account URLs are refused before a
    fetch, and private/loopback target addresses are refused by the existing
    `jarvis_local_http.private_fetch_problem` guard before a fetch;
  * NO NEW DEPENDENCE ON SLICE 1: when the decoupled-profile provider is not
    available, the honest "not available yet" answer is returned and nothing
    is fetched (the provider is injectable).
  * RULING 10.3 (the accepted hard contract, 2026-10-21): no checkout/cart/
    seat-hold path and no write method (checked with `ast`, never a
    source-text pin); no Authorization/cookie/conditional header on either
    probe; a 403/429/challenge answer stops the check and marks `stale: True`
    with `reason: "blocked_by_site_challenge"` and NO retry; SSRF refusals
    cover private/link-local/CGNAT/TEST-NET targets; the disclosure wording is
    Ruling 10.3's sentences word for word; and the poll floor (+/-30% jitter)
    is Slice 1's scheduler, not a second cadence.
"""
from __future__ import annotations

import ast
import json
import os
import shutil
import sys
import tempfile
import time
import traceback
import types
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-price-sources-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["OPENJARVIS_HOME"] = str(_TMP / "home")
os.environ["JARVIS_HOME"] = str(_TMP / "home")
os.environ["JARVIS_LOG_DIR"] = str(_TMP / "logs")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

PASSED: list = []
FAILED: list = []
SKIPPED: list = []


def check(name, cond, detail=""):
    if cond:
        PASSED.append(name)
        print(f"ok    {name}")
    else:
        FAILED.append(name)
        print(f"FAIL  {name}" + (f"  [{detail}]" if detail else ""))


def skip(why):
    SKIPPED.append(why)
    print(f"skip  {why}  (not a pass)")


def _inside_tmp(value: str) -> bool:
    try:
        Path(value).resolve().relative_to(_TMP.resolve())
        return True
    except ValueError:
        return False


def _require_own_places() -> None:
    for name in ("OPENJARVIS_CONFIG_DIR", "OPENJARVIS_HOME", "JARVIS_HOME", "JARVIS_LOG_DIR"):
        value = os.environ.get(name, "")
        if not value or not _inside_tmp(value):
            raise SystemExit(
                f"refusing to run: {name}={value!r} is not inside this suite's own temp "
                f"folder {_TMP}. A suite must never write the owner's real audit log or "
                f"read their real settings.")


_require_own_places()

import jarvis_price_sources as P                            # noqa: E402
import jarvis_local_http as LH                              # noqa: E402
import jarvis_search as S                                   # noqa: E402
import jarvis_tellme as T                                   # noqa: E402


ON = {"enabled": True, "searxng_url": P.DEFAULT_SEARXNG_URL}
OFF = {"enabled": False}
#: A public IP literal: the real SSRF guard runs (no DNS needed in CI) and the
#: injected fetch means no connection is made.
PUBLIC_URL = "https://93.184.216.34/product/1"


class Recorder:
    """A fake fetch: records every call and answers from a list of callables."""

    def __init__(self, *answers):
        self.calls = []
        self.answers = list(answers)

    def __call__(self, *args):
        self.calls.append(args)
        answer = self.answers.pop(0) if self.answers else self.answers_default()
        if callable(answer):
            return answer(*args)
        return answer

    @staticmethod
    def answers_default():
        raise AssertionError("unexpected extra fetch")


def _searxng_json(results) -> bytes:
    return json.dumps({"results": results}, ensure_ascii=False).encode("utf-8")


def _product_html(price_text: str, currency: str = "USD") -> bytes:
    return (f'<html><head><script type="application/ld+json">'
            f'{{"@type":"Product","name":"Widget",'
            f'"offers":{{"@type":"Offer","price":"{price_text}",'
            f'"priceCurrency":"{currency}"}}}}</script></head>'
            f'<body><h1>Widget</h1><span>${price_text}</span></body></html>').encode("utf-8")


def _desktop_profile() -> dict:
    return {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/140.0",
            "Accept-Language": "en-US,en;q=0.9", "Accept": "text/html",
            "Cookie": "session=abc", "ETag": '"tracking-etag"',
            "If-None-Match": '"tracking-etag"',
            "If-Modified-Since": "Wed, 21 Oct 2026 07:28:00 GMT",
            "Referer": "https://tracker.example/click", "Origin": "https://tracker.example",
            "Authorization": "Bearer sk-test-123", "Proxy-Authorization": "Basic abcdef"}


def _mobile_profile() -> dict:
    return {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
                          "AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1",
            "Accept-Language": "en-US,en;q=0.8", "Accept": "text/html",
            "Cookie": "uid=zzz", "If-None-Match": '"mobile-etag"',
            "ETag": '"mobile-etag"', "Authorization": "Bearer m-test"}


def _headers_for(persona: str) -> dict:
    return _desktop_profile() if persona == P.PERSONA_COMPARISON else _mobile_profile()


def t_defaults_and_switch_off_fetches_nothing():
    check("the SearXNG address is the verified loopback 127.0.0.1:8888",
          P.DEFAULT_SEARXNG_URL == "http://127.0.0.1:8888", P.DEFAULT_SEARXNG_URL)
    check("... the same address jarvis_search already calls",
          P.DEFAULT_SEARXNG_URL == S.DEFAULT_SEARXNG_URL,
          (P.DEFAULT_SEARXNG_URL, S.DEFAULT_SEARXNG_URL))
    check("a non-local SearXNG override falls back to the shipped default",
          P.searxng_url({"enabled": True, "searxng_url": "http://example.com:8888"})
          == P.DEFAULT_SEARXNG_URL,
          P.searxng_url({"enabled": True, "searxng_url": "http://example.com:8888"}))
    check("the feature is OFF unless the settings say otherwise",
          P.enabled({}) is False and P.enabled({"enabled": "no"}) is False
          and P.enabled({"enabled": True}) is True)
    fetch = Recorder()
    got = P.query_searxng_prices("widget price", cfg=OFF, fetch=fetch)
    check("switch off: no SearXNG fetch at all", fetch.calls == [], fetch.calls)
    check("... and one plain sentence says why", got.get("ok") is False
          and got.get("why") == "disabled" and got.get("words") == P.OFF_WORDS, got)
    fetch = Recorder()
    got = P.probe_steering(PUBLIC_URL, cfg=OFF, fetch=fetch, headers_for=_headers_for)
    check("switch off: no product fetch at all", fetch.calls == [], fetch.calls)
    check("... and the same plain sentence", got.get("ok") is False
          and got.get("words") == P.OFF_WORDS and got.get("steering_detected") is False, got)


def t_searxng_prices_are_integer_cents_and_deduped():
    body = _searxng_json([
        {"title": "Widget - $1,249.99", "url": "https://shop.example.com/p/1?utm_source=x",
         "content": "was $1,299.99, now £24.99"},
        {"title": "Widget again", "url": "https://SHOP.example.com/p/1/",
         "content": "$1,249.99"},
        {"title": "Cheap widget from $0.29", "url": "https://other.example.com/w",
         "content": "only slightly used"},
        {"title": "No price here", "url": "https://third.example.com/x", "content": "no"},
        {"title": "Not a page", "url": "javascript:alert(1)", "content": "$1"},
    ])
    fetch = Recorder((200, body))
    got = P.query_searxng_prices("widget price", cfg=ON, fetch=fetch)
    check("one request, to the SearXNG JSON endpoint, with the search words and categories",
          len(fetch.calls) == 1 and "format=json" in fetch.calls[0][0]
          and "q=widget+price" in fetch.calls[0][0]
          and "categories=general%2Cshopping" in fetch.calls[0][0],
          fetch.calls[:1])
    check("the results are reported", got.get("ok") is True and got.get("count") == 3, got)
    urls = [r["url"] for r in got.get("results") or []]
    check("the duplicate (same page, tracking parameters) counts once", len(urls) == 3, urls)
    first = (got.get("results") or [{}])[0]
    check("prices are exact whole cents, in page order",
          first.get("prices_cents") == [124999, 129999, 2499], first.get("prices_cents"))
    check("... and the cheapest reading is the minimum", first.get("min_cents") == 2499, first)
    check("host is named, and no non-http result is kept",
          first.get("host") == "shop.example.com"
          and all(u.startswith("https://") for u in urls), urls)
    check("the answer says these are outside words, not something learned",
          "outside text" in got.get("words", "").lower(), got.get("words"))


def t_searxng_failures_are_plain_and_fetch_nothing_more():
    cases = [
        ("down", Recorder(Exception("connection refused")), "unavailable",
         P.NO_SEARXNG_WORDS),
        ("json off", Recorder((403, b"")), "json_off", P.JSON_OFF_WORDS),
        ("http error", Recorder((500, b"oops")), "unavailable", P.NO_SEARXNG_WORDS),
        ("not json", Recorder((200, b"<html>not json</html>")), "unreadable",
         P.UNREADABLE_WORDS),
        ("wrong shape", Recorder((200, b'{"nope": 1}')), "unreadable", P.UNREADABLE_WORDS),
    ]
    for label, fetch, why, words in cases:
        got = P.query_searxng_prices("widget", cfg=ON, fetch=fetch)
        check(f"SearXNG {label}: plain words, no crash, one fetch at most",
              got.get("ok") is False and got.get("why") == why
              and got.get("words") == words and len(fetch.calls) <= 1, got)
    big = Recorder((200, b"x" * (P.SEARXNG_MAX_BYTES + 10)))
    got = P.query_searxng_prices("widget", cfg=ON, fetch=big)
    check("an answer over the size cap is refused, not parsed",
          got.get("ok") is False and got.get("why") == "unreadable", got)
    empty = Recorder((200, _searxng_json([])))
    got = P.query_searxng_prices("widget", cfg=ON, fetch=empty)
    check("an empty answer is honest (no prices read), not a crash",
          got.get("ok") is True and got.get("count") == 0
          and "no prices were read" in got.get("words", ""), got)


def _gate_spy():
    """Install a jarvis_gate stand-in whose latch_taint records calls."""
    state = types.SimpleNamespace(calls=[])
    real = sys.modules.get("jarvis_gate")
    sys.modules["jarvis_gate"] = types.SimpleNamespace(
        latch_taint=lambda **kw: state.calls.append(kw))
    return state, real


def _restore_gate(real):
    if real is None:
        sys.modules.pop("jarvis_gate", None)
    else:
        sys.modules["jarvis_gate"] = real


def t_outside_reads_latch_taint_and_refusals_do_not():
    state, real = _gate_spy()
    try:
        fetch = Recorder((200, _searxng_json(
            [{"title": "Widget $10.00", "url": "https://shop.example.com/w",
              "content": ""}])))
        got = P.query_searxng_prices("widget", cfg=ON, fetch=fetch)
    finally:
        _restore_gate(real)
    check("(set-up) the read succeeded", got.get("ok") is True, got)
    check("a successful SearXNG read sets the page-watch taint latch (price_radar)",
          [c.get("why") for c in state.calls] == ["price_radar"], state.calls)

    state, real = _gate_spy()
    try:
        P.query_searxng_prices("widget", cfg=ON, fetch=Recorder((500, b"")))
        P.query_searxng_prices("widget", cfg=OFF, fetch=Recorder())
    finally:
        _restore_gate(real)
    check("... but a failed read and a switched-off read latch nothing",
          state.calls == [], state.calls)


def t_steering_detected_with_exact_cents_and_decoupled_headers():
    fetch = Recorder((200, _product_html("1249.99"), "text/html"),
                     (200, _product_html("1299.99"), "text/html"))
    got = P.probe_steering(PUBLIC_URL, cfg=ON, fetch=fetch, headers_for=_headers_for)
    check("(set-up) two probes fetched the SAME canonical URL, A then B",
          len(fetch.calls) == 2 and fetch.calls[0][0] == fetch.calls[1][0],
          [c[0] for c in fetch.calls])
    check("the prices are exact whole cents", got.get("price_a_cents") == 124999
          and got.get("price_b_cents") == 129999,
          (got.get("price_a_cents"), got.get("price_b_cents")))
    check("steering is detected only when both readings differ",
          got.get("steering_detected") is True and got.get("ok") is True, got)
    check("the delta is a - b, in whole cents, and the cheaper persona is named",
          got.get("steering_delta_cents") == -5000
          and got.get("which_persona_lower") == P.PERSONA_COMPARISON, got)
    check("the answer says which view was cheaper, in plain words",
          "comparison-shopper" in got.get("words", "")
          and "1249.99" in got.get("words", "")
          and "1299.99" in got.get("words", ""), got.get("words"))
    a_headers, b_headers = fetch.calls[0][1], fetch.calls[1][1]
    check("probe A carries the Google referer; probe B carries none",
          a_headers.get("Referer") == "https://www.google.com/"
          and "Referer" not in b_headers, (a_headers.get("Referer"), b_headers.get("Referer")))
    stripped = ("Cookie", "cookie", "ETag", "If-None-Match", "If-Modified-Since",
                "If-Match", "If-Range", "Referer", "Origin")
    for label, headers in (("A", a_headers), ("B", b_headers)):
        check(f"probe {label} sends no Cookie/ETag/If-* header, even when its profile has them",
              not any(k in headers or k.lower() in {x.lower() for x in headers}
                      for k in ("Cookie", "ETag", "If-None-Match", "If-Modified-Since",
                                "If-Match", "If-Range")),
              {k: v for k, v in headers.items() if k not in ("Referer",)})
        check(f"probe {label} sends NO Authorization header (never authenticated scraping)",
              not any(k.lower() in ("authorization", "proxy-authorization")
                      for k in headers), headers) 
        check(f"probe {label} sends Cache-Control: no-cache",
              headers.get("Cache-Control") == "no-cache", headers.get("Cache-Control"))
        check(f"probe {label} keeps one internally consistent browser profile",
              "User-Agent" in headers and "Accept-Language" in headers, headers)
    check("probe A's user agent is the desktop profile",
          "Windows NT" in a_headers["User-Agent"], a_headers["User-Agent"])
    check("probe B's user agent is the mobile profile",
          "iPhone" in b_headers["User-Agent"], b_headers["User-Agent"])


def t_steering_not_detected_when_the_readings_are_equal():
    fetch = Recorder((200, _product_html("19.99"), "text/html"),
                     (200, _product_html("19.99"), "text/html"))
    got = P.probe_steering(PUBLIC_URL, cfg=ON, fetch=fetch, headers_for=_headers_for)
    check("equal readings are NOT steering",
          got.get("steering_detected") is False and got.get("steering_delta_cents") == 0
          and got.get("price_a_cents") == 1999 and got.get("price_b_cents") == 1999, got)
    check("... and the answer says both views showed the same price",
          got.get("words") == P.SAME_WORDS, got.get("words"))


def t_steering_never_guesses_from_one_probe_or_no_price():
    fetch = Recorder((200, _product_html("19.99"), "text/html"),
                     Exception("blocked"))
    got = P.probe_steering(PUBLIC_URL, cfg=ON, fetch=fetch, headers_for=_headers_for)
    check("one probe failing means NO steering claim and no guessed price",
          got.get("steering_detected") is False and got.get("price_b_cents") is None
          and got.get("ok") is False and got.get("words") == P.NO_B_PRICE_WORDS, got)
    fetch = Recorder(Exception("blocked"),
                     (200, _product_html("19.99"), "text/html"))
    got = P.probe_steering(PUBLIC_URL, cfg=ON, fetch=fetch, headers_for=_headers_for)
    check("... the same when the comparison-shopper probe fails",
          got.get("steering_detected") is False and got.get("price_a_cents") is None
          and got.get("words") == P.NO_A_PRICE_WORDS, got)
    no_price = b"<html><body>Widget - price on request</body></html>"
    got = P.probe_steering(PUBLIC_URL, cfg=ON, fetch=Recorder((200, no_price, "text/html"),
                                                              (200, no_price, "text/html")),
                           headers_for=_headers_for)
    check("a page with no readable price is never 'steering'",
          got.get("steering_detected") is False and got.get("price_a_cents") is None
          and got.get("price_b_cents") is None, got)


def t_steering_refuses_cart_and_private_targets_before_fetching():
    for url in ("https://93.184.216.34/cart/1", "https://93.184.216.34/checkout",
                "https://93.184.216.34/basket", "https://93.184.216.34/order/9",
                "https://93.184.216.34/payment", "https://93.184.216.34/signin",
                "https://93.184.216.34/my-account", "https://93.184.216.34/seat-select",
                "https://93.184.216.34/seats/1", "https://93.184.216.34/seat-hold"):
        fetch = Recorder()
        got = P.probe_steering(url, cfg=ON, fetch=fetch, headers_for=_headers_for)
        check(f"cart/checkout/account page refused before any fetch: {url}",
              got.get("ok") is False and got.get("why") == "not_product"
              and got.get("words") == P.NOT_PRODUCT_WORDS and fetch.calls == [], got)
    for url in ("http://127.0.0.1/product", "http://10.1.2.3/product",
                "http://192.168.1.50/product", "http://localhost/product"):
        fetch = Recorder()
        got = P.probe_steering(url, cfg=ON, fetch=fetch, headers_for=_headers_for)
        check(f"private target refused by the existing SSRF guard before any fetch: {url}",
              got.get("ok") is False and got.get("why") == "not_public"
              and fetch.calls == [] and P.NOT_PUBLIC_WORDS in got.get("words", ""), got)


def t_steering_without_the_profile_provider_is_honest():
    real = P._default_headers_for
    P._default_headers_for = lambda persona: None
    try:
        fetch = Recorder()
        got = P.probe_steering(PUBLIC_URL, cfg=ON, fetch=fetch)
    finally:
        P._default_headers_for = real
    check("without the decoupled-profile provider: honest words, no fetch",
          got.get("ok") is False and got.get("why") == "no_profiles"
          and got.get("words") == P.NO_PROFILES_WORDS and fetch.calls == [], got)


def t_price_reading_reuses_the_tellme_extractor():
    real = T.price_of
    calls = []

    def spy(body, content_type=""):
        calls.append(content_type)
        return 1249.99
    T.price_of = spy
    try:
        cents = P._price_of(b"<html>ignored</html>", "text/html")
    finally:
        T.price_of = real
    check("the product price is read by jarvis_tellme.price_of, once, not a second parser",
          calls == ["text/html"] and cents == 124999, (calls, cents))
    check("... and the integer-cents rounding is exact for awkward values",
          [P._cents(x) for x in (0.29, 19.99, 1249.99, 1.1, 1.10, 99.95)]
          == [29, 1999, 124999, 110, 110, 9995],
          [P._cents(x) for x in (0.29, 19.99, 1249.99, 1.1, 1.10, 99.95)])
    check("... a missing/odd price is None, never a fake 0",
          P._cents(None) is None and P._cents(0) is None and P._cents("nope") is None)


def t_a_long_page_is_capped_not_read_whole():
    html = _product_html("19.99") + b"x" * (P.PRODUCT_MAX_BYTES + 500)
    fetch = Recorder((200, html, "text/html"), (200, html, "text/html"))
    got = P.probe_steering(PUBLIC_URL, cfg=ON, fetch=fetch, headers_for=_headers_for)
    check("a page over the size cap is cut to the cap and its price still read",
          got.get("ok") is True and got.get("price_a_cents") == 1999
          and got.get("price_b_cents") == 1999, got)


def t_ruling_103_challenge_stops_with_no_retry_and_marks_stale():
    challenge = b"<html><title>Just a moment...</title>captcha challenge</html>"
    fetch = Recorder((403, challenge, "text/html"))
    got = P.probe_steering(PUBLIC_URL, cfg=ON, fetch=fetch, headers_for=_headers_for)
    check("a 403 marks the check stale with the fixed reason",
          got.get("stale") is True
          and got.get("reason") == P.BLOCKED_BY_SITE_CHALLENGE, got)
    check("... in the plain challenge sentence",
          got.get("words") == P.CHALLENGE_WORDS, got.get("words"))
    check("... and NO second probe was sent (no retry loop)", len(fetch.calls) == 1,
          len(fetch.calls))
    fetch = Recorder((200, challenge, "text/html"))
    got = P.probe_steering(PUBLIC_URL, cfg=ON, fetch=fetch, headers_for=_headers_for)
    check("a challenge page behind 200 is the same stop",
          got.get("stale") is True and got.get("reason") == P.BLOCKED_BY_SITE_CHALLENGE
          and len(fetch.calls) == 1, (got.get("stale"), len(fetch.calls)))
    fetch = Recorder((200, _product_html("9.99"), "text/html"), (429, b"", "text/html"))
    got = P.probe_steering(PUBLIC_URL, cfg=ON, fetch=fetch, headers_for=_headers_for)
    check("a 429 on the second probe stops there, keeps A's reading, marks stale",
          got.get("stale") is True and got.get("reason") == P.BLOCKED_BY_SITE_CHALLENGE
          and got.get("price_a_cents") == 999 and got.get("steering_detected") is False
          and len(fetch.calls) == 2, got)
    got = P.query_searxng_prices("widget", cfg=ON, fetch=Recorder((429, b"")))
    check("SearXNG's own 429 limiter is a stale challenge stop, not a retry",
          got.get("stale") is True
          and got.get("reason") == P.BLOCKED_BY_SITE_CHALLENGE, got)


def t_ruling_103_no_write_verbs_no_body_no_auth_imports():
    src = (HERE / "jarvis_price_sources.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    methods, bodies = [], []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg == "method":
                try:
                    methods.append(ast.literal_eval(kw.value))
                except Exception:
                    methods.append("?")
            if kw.arg == "data":
                bodies.append("data")
    check("the module issues no POST/PUT/PATCH/DELETE at all",
          not any(isinstance(m, str) and m.upper() in ("POST", "PUT", "PATCH", "DELETE")
                  for m in methods), methods)
    check("... and never sends a request body", bodies == [], bodies)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    forbidden = {"jarvis_vault", "jarvis_token_store", "win32cred", "keyring",
                 "requests", "httpx", "curl_cffi", "browserforge", "selenium"}
    check("... and imports no credential store, auth helper or scraping dependency",
          not (imports & forbidden), sorted(imports & forbidden))


def t_ruling_103_disclosure_wording_is_exact():
    check("the per-result footer is Ruling 10.3's sentence word for word",
          P.DISCLOSURE_NEW_VISITOR
          == "Checked as a new visitor (no cookies or account used).",
          P.DISCLOSURE_NEW_VISITOR)
    body = _searxng_json([{"title": "Widget $10.00",
                           "url": "https://shop.example.com/w", "content": ""}])
    got = P.query_searxng_prices("widget", cfg=ON, fetch=Recorder((200, body)))
    row = (got.get("results") or [{}])[0]
    check("... carried on every result row as its `footer`",
          row.get("footer") == P.DISCLOSURE_NEW_VISITOR
          and got.get("footer") == P.DISCLOSURE_NEW_VISITOR, row)
    got = P.probe_steering(PUBLIC_URL, cfg=ON,
                           fetch=Recorder((200, _product_html("1249.99"), "text/html"),
                                          (200, _product_html("1299.99"), "text/html")),
                           headers_for=_headers_for)
    check("the steering row is Ruling 10.3's sentence word for word",
          got.get("steering_row")
          == ("This store showed two different prices at the same time: $1249.99 "
              "(Desktop · via search referral) vs. $1299.99 (Mobile · direct)."),
          got.get("steering_row"))
    got = P.probe_steering(PUBLIC_URL, cfg=ON,
                           fetch=Recorder((200, _product_html("9.99"), "text/html"),
                                          (200, _product_html("9.99"), "text/html")),
                           headers_for=_headers_for)
    check("... and there is NO steering row when the readings are equal",
          got.get("steering_row") == "", got.get("steering_row"))
    check("the proxy tag is the fixed sentence, with the exit's label",
          P.proxy_tag("Tailscale exit")
          == "Checked via configured proxy (Tailscale exit).",
          P.proxy_tag("Tailscale exit"))


def t_ruling_103_poll_floor_and_owned_scheduler():
    check("the poll floor is at least 300 s", P.POLL_MIN_SECONDS >= 300,
          P.POLL_MIN_SECONDS)
    check("the jitter is the +/-30% the contract fixes",
          abs(P.POLL_JITTER - 0.30) < 1e-9, P.POLL_JITTER)
    check("without Slice 1's scheduler, no cadence is invented (None)",
          P.next_poll_seconds(600) is None, P.next_poll_seconds(600))
    had = hasattr(T, "next_poll_timestamp")
    real = getattr(T, "next_poll_timestamp", None)
    seen = []

    def fake(base, rng=None, now=None):
        seen.append((base, rng))
        return 1234.5
    T.next_poll_timestamp = fake
    try:
        got = P.next_poll_seconds(600, rng="RNG")
    finally:
        if had:
            T.next_poll_timestamp = real
        else:
            del T.next_poll_timestamp
    check("with Slice 1's scheduler present it DELEGATES (one implementation)",
          got == 1234.5 and seen and seen[0][0] == 600 and seen[0][1] == "RNG",
          (got, seen))


def t_ruling_103_ssrf_covers_private_link_local_and_cgnat():
    for url in ("http://127.0.0.1/product", "http://10.1.2.3/product",
                "http://172.16.5.5/product", "http://192.168.1.50/product",
                "http://169.254.1.1/product", "http://100.64.0.5/product",
                "http://[fe80::1]/product", "http://[fc00::1]/product",
                "http://0.0.0.0/product", "http://192.0.2.10/product"):
        fetch = Recorder()
        got = P.probe_steering(url, cfg=ON, fetch=fetch, headers_for=_headers_for)
        check(f"refused as a private/never-a-destination target before any fetch: {url}",
              got.get("ok") is False and got.get("why") == "not_public"
              and fetch.calls == [], got)


def t_ruling_103_the_target_fetch_uses_the_public_guarded_opener():
    captured = {}

    class FakeResp:
        status = 200
        headers = {"Content-Type": "text/html"}

        def read(self, n):
            return b"x" * 10

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    class FakeOpener:
        def open(self, req, timeout=None, **kw):
            captured["req"] = req
            captured["timeout"] = timeout
            return FakeResp()

    class FakeRedirect:
        pass

    real_public, real_redirect = LH.public_opener, T._PageRedirect
    T._PageRedirect = FakeRedirect

    def fake_public(*handlers):
        captured["handlers"] = handlers
        return FakeOpener()
    LH.public_opener = fake_public
    try:
        status, body, ctype = P._fetch_default(PUBLIC_URL, {"A": "b"})
    finally:
        LH.public_opener, T._PageRedirect = real_public, real_redirect
    req = captured.get("req")
    handlers = captured.get("handlers") or ()
    check("the product fetch goes through jarvis_local_http.public_opener "
          "(SSRF checked per connection)", captured.get("handlers") is not None
          and status == 200, (status, ctype))
    check("... with jarvis_tellme's own redirect refusal attached",
          len(handlers) == 1 and isinstance(handlers[0], FakeRedirect), handlers)
    check("... a GET only, with the page cap applied",
          getattr(req, "method", None) == "GET"
          and captured.get("timeout") == P.PRODUCT_TIMEOUT and len(body) == 10,
          (getattr(req, "method", None), captured.get("timeout")))


def t_ruling_103_missing_integer_cents_edges():
    values = (0.1, 0.29, 1.1, 1.10, 19.9, 19.99, 99.95, 1249.99, 1234567.89)
    check("integer cents are exact for the awkward two-decimal cases",
          [P._cents(x) for x in values]
          == [10, 29, 110, 110, 1990, 1999, 9995, 124999, 123456789],
          [P._cents(x) for x in values])
    real = T.price_of
    answers = iter([19, 19.9, 0.29, None])
    T.price_of = lambda body, content_type="": next(answers)
    try:
        got = [P._price_of(b"<html></html>", "text/html") for _ in range(4)]
    finally:
        T.price_of = real
    check("a whole-number price, a one-decimal price and a missing price all land right",
          got == [1900, 1990, 29, None], got)


def main():
    functions = [(name, fn) for name, fn in list(globals().items())
                 if name.startswith("t_") and callable(fn)]
    for name, fn in functions:
        print(f"\n--- {name} ---")
        try:
            fn()
        except Exception:
            FAILED.append(name)
            traceback.print_exc()
    shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if SKIPPED:
        print("skipped (NOT passes): " + ", ".join(SKIPPED))
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
