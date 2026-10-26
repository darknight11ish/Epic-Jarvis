"""test_product_read.py - the READ half of the product check
(jarvis_product_read.py; the engine it feeds is jarvis_product_research.py).

    py -3 -B backend/test_product_read.py

EVERY PAGE IN THIS FILE IS SYNTHETIC. No real Amazon page text is vendored and
no URL is fetched: the fixtures are hand-written page shapes with the hooks and
ids the parser reads. The suite proves the listing/review extraction, each
warning's bite, tolerance of malformed and truncated markup, determinism, the
engine integration (same report, same caveat, same quote validator), and that
the module imports nothing that can reach the network or a browser.

The module is the analysis read path only: nothing is wired to a route, tool,
card or app surface, and `capture_with_owner_browser()` deliberately raises
the documented owner-session error instead of pretending to fetch a page.
"""
from __future__ import annotations

import ast
import copy
import http.client
import inspect
import json
import socket
import sys
import traceback
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import jarvis_product_read as READ  # noqa: E402
import jarvis_product_research as ENGINE  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


# ---------------------------------------------------------------------------
#   Synthetic page fixtures
# ---------------------------------------------------------------------------

_HEAD = """<!doctype html>
<html><head>
<title>Amazon.com: Synthetic Widget 3000: Home and Kitchen</title>
<meta property="og:title" content="Synthetic Widget 3000">
<link rel="canonical" href="https://www.amazon.example/dp/B0TEST0001">
</head><body data-asin="B0TEST0001">
<span id="productTitle">Synthetic Widget 3000</span>
<span id="acrPopover" title="4.5 out of 5 stars"></span>
<span id="acrCustomerReviewText">1,234 ratings</span>
"""


def _review(number, star, title, date, body, *, verified=False, vine=False,
            helpful=None, variant=None):
    """One synthetic review block in the shape the parser reads. The star line
    lives inside the title anchor, which is one of the two real shapes."""
    badge = '<span data-hook="avp-badge">Verified Purchase</span>' if verified else ""
    vine_badge = ('<span data-hook="vine-review-badge">Vine Customer Review of '
                  'Free Product</span>') if vine else ""
    helpful_span = (f'<span data-hook="helpful-vote-statement">{helpful}</span>'
                    if helpful else "")
    variant_link = f'<a data-hook="format-strip">{variant}</a>' if variant else ""
    return f"""<div data-hook="review" id="customer_review-{number}">
<a data-hook="review-title"><i><span>{star} out of 5 stars</span></i>
<span>{title}</span></a>
<span data-hook="review-date">Reviewed in Testland on {date}</span>
{badge}{vine_badge}
<span data-hook="review-body">{body}</span>
{helpful_span}{variant_link}
</div>
"""


_FULL_REVIEWS = [
    _review(1, 4.0, "Solid for the price", "2 August 2026",
            "The battery lasts about 9 hours at half volume and the case fits "
            "in my jacket pocket.", verified=True, helpful="12 people found this helpful",
            variant="Colour: Blue"),
    _review(2, 5.0, "Good fit", "19 August 2026",
            "I measured 14 cm across the palm and the large size fits exactly.",
            verified=True, helpful="3 people found this helpful"),
    _review(3, 3.0, "Mixed feelings", "5 September 2026",
            "Sound is clear but the charging port is loose after 3 months.",
            verified=True),
    _review(4, 2.0, "Broke early", "21 September 2026",
            "The left hinge cracked after 6 weeks of light use and the return "
            "form wanted a 12 digit code.", verified=True),
    _review(5, 5.0, "Free sample", "2 October 2026",
            "Received this product for free in exchange for a review. It is "
            "light and the screen is 6 cm wide.", vine=True,
            helpful="One person found this helpful", variant="Size: Large"),
]

FULL_PAGE = _HEAD + "".join(_FULL_REVIEWS) + "</body></html>"

CHALLENGE_PAGE = """<!doctype html><html><body>
<h4>Enter the characters you see below</h4>
<form action="/errors/validateCaptcha"><input id="captchacharacters" name="field-keywords"></form>
<p>Sorry, we just need to make sure you're not a robot.</p>
</body></html>"""

NOT_PRODUCT_PAGE = """<!doctype html><html><head>
<title>Amazon.com: Online Shopping for Electronics, Apparel</title></head>
<body><div id="nav-belt">Navigation</div>
<div data-component-type="s-search-result">A search result, not a product page.</div>
</body></html>"""

NO_REVIEWS_PAGE = """<!doctype html><html><head>
<title>Amazon.com: Quiet Widget: Home</title></head><body>
<span id="productTitle">Quiet Widget</span>
<span id="acrPopover" title="4.0 out of 5 stars"></span>
<span id="acrCustomerReviewText">12 ratings</span>
</body></html>"""

MISSING_FIELDS_PAGE = """<!doctype html><html><head><title>Amazon.com: Bare Widget: Home</title></head><body>
<span id="productTitle">Bare Widget</span>
<div data-hook="review" id="customer_review-bare">
<span data-hook="review-body">A review with no star line, no date and no title shown.</span>
</div>
</body></html>"""

#: The full page cut after the last complete review: the capture stopped before
#: the page closed, which is what a partial capture looks like.
TRUNCATED_PAGE = FULL_PAGE.split("</body></html>")[0]

#: The full page cut in the middle of the fifth review: the review block is
#: still open when the input ends.
PARTIAL_REVIEW_PAGE = FULL_PAGE.split(
    '<div data-hook="review" id="customer_review-5">')[0] + (
    '<div data-hook="review" id="customer_review-5">'
    '<span data-hook="review-body">The capture ended in the middle of this review')

MALFORMED_PAGE = """<html><body><span id=productTitle>Malformed Widget
<div data-hook=review><span data-hook=review-title>Some title
<span data-hook=review-body>Body text with <b>bold and <i>unclosed tags
<a data-hook=review-date>Reviewed in Testland on 1 January 2026"""


def _codes(parsed):
    return [warning["code"] for warning in parsed["warnings"]]


# ---------------------------------------------------------------------------
# 1. Listing facts
# ---------------------------------------------------------------------------

def t_listing_facts_are_typed():
    parsed = READ.parse_product_page(FULL_PAGE,
                                     source_url="https://www.amazon.example/dp/B0TEST0001")
    listing = parsed["listing"]
    check("the title, star rating, rating count, URL and ASIN are read and typed",
          listing["title"] == "Synthetic Widget 3000"
          and listing["star_rating"] == 4.5
          and listing["rating_count"] == 1234
          and listing["url"] == "https://www.amazon.example/dp/B0TEST0001"
          and listing["asin"] == "B0TEST0001", listing)


def t_listing_falls_back_to_canonical_and_doc_title():
    no_source = READ.parse_product_page(FULL_PAGE)
    check("with no source_url the page's canonical link is used",
          no_source["listing"]["url"] == "https://www.amazon.example/dp/B0TEST0001",
          no_source["listing"]["url"])
    no_product_title = """<html><head><title>Amazon.com: Fallback Widget Name: Home</title>
<link rel="canonical" href="https://www.amazon.example/dp/B0FALLBACK"></head><body>
<span id="acrPopover" title="4.0 out of 5 stars"></span>
<span id="acrCustomerReviewText">9 ratings</span>
<div data-hook="review"><span data-hook="review-body">A review body with enough words to read.</span></div>
</body></html>"""
    fallback = READ.parse_product_page(no_product_title)
    check("the document title supplies the product name when #productTitle is absent",
          fallback["listing"]["title"] == "Fallback Widget Name", fallback["listing"])
    check("the ASIN is recovered from the canonical URL when no input element is there",
          fallback["listing"]["asin"] == "B0FALLBACK", fallback["listing"])


def t_unreadable_listing_values_are_none_not_guesswork():
    page = """<html><body><span id="productTitle">Only A Title</span>
<div data-hook="review"><span data-hook="review-body">A review body with several words.</span></div>
</body></html>"""
    parsed = READ.parse_product_page(page)
    check("a missing rating and count are None, never zero",
          parsed["listing"]["star_rating"] is None
          and parsed["listing"]["rating_count"] is None, parsed["listing"])


# ---------------------------------------------------------------------------
# 2. Review records, in the engine's own schema
# ---------------------------------------------------------------------------

def t_reviews_are_engine_records():
    parsed = READ.parse_product_page(FULL_PAGE)
    records = parsed["reviews"]
    check("all five review blocks become five records with no skips",
          len(records) == 5 and parsed["counts"]["reviews"] == 5, parsed["counts"])
    first = records[0]
    check("a review's rating, date, title, text, verified badge and helpful count are read",
          first["rating"] == 4 and first["date"] == "2026-08-02"
          and first["title"] == "Solid for the price"
          and first["verified"] is True
          and "battery lasts about 9 hours" in first["text"]
          and first["helpful"] == 12
          and first["variant"] == "Colour: Blue", first)
    check("the page's own date text is kept beside the parsed date",
          first["date_text"] == "Reviewed in Testland on 2 August 2026", first["date_text"])
    last = records[4]
    check("a Vine badge becomes vine True, absence of Verified is verified False",
          last["vine"] is True and last["verified"] is False, last)
    check("the page's 'One person found this helpful' wording becomes 1",
          last["helpful"] == 1, last["helpful"])


def t_records_pass_through_the_engine_schema():
    parsed = READ.parse_product_page(FULL_PAGE)
    normalised, skipped = ENGINE.normalize_reviews(parsed["reviews"])
    check("the engine accepts every record with no skips (one tolerant schema)",
          len(normalised) == 5 and skipped == 0, (len(normalised), skipped))
    check("the engine's normaliser keeps the fields the read path extracted",
          normalised[0]["rating"] == 4 and normalised[0]["date"] == "2026-08-02"
          and normalised[0]["verified"] is True and normalised[4]["vine"] is True,
          normalised[0])


def t_absent_fields_are_counted_not_invented():
    parsed = READ.parse_product_page(MISSING_FIELDS_PAGE)
    record = parsed["reviews"][0]
    check("a review with no rating/date/title has None for each, not invented values",
          record["rating"] is None and record["date"] is None
          and record["title"] == "" and record["date_text"] is None, record)
    check("the READ path reports which fields were missing",
          READ.WARN_MISSING_FIELDS in _codes(parsed), parsed["warnings"])


# ---------------------------------------------------------------------------
# 3. Each warning, with a fixture that makes it bite
# ---------------------------------------------------------------------------

def t_full_page_has_no_warnings():
    check("the healthy synthetic page produces no warnings",
          _codes(READ.parse_product_page(FULL_PAGE)) == [],
          READ.parse_product_page(FULL_PAGE)["warnings"])


def t_challenge_page_bite():
    parsed = READ.parse_product_page(CHALLENGE_PAGE)
    check("a CAPTCHA/sign-in page is named and no reviews are read",
          READ.WARN_CHALLENGE in _codes(parsed) and parsed["reviews"] == [],
          parsed["warnings"])
    check("the challenge message says there is nothing to read",
          "not a product page" in " ".join(
              warning["message"] for warning in parsed["warnings"]).lower())
    assembled = READ.assemble_report(CHALLENGE_PAGE)
    check("assembling a report from a challenge page gives not-enough-data, not an error",
          assembled["report"]["verdict"]["code"] == "not_enough_data")


def t_not_a_product_page_bite():
    parsed = READ.parse_product_page(NOT_PRODUCT_PAGE)
    check("a search/cart-like page is named as not a product page",
          READ.WARN_NOT_PRODUCT in _codes(parsed), parsed["warnings"])
    check("its document title is not treated as a product title",
          parsed["listing"]["title"] is None, parsed["listing"])


def t_no_reviews_bite():
    parsed = READ.parse_product_page(NO_REVIEWS_PAGE)
    check("a product page with no review blocks warns there are no reviews",
          READ.WARN_NO_REVIEWS in _codes(parsed) and parsed["counts"]["review_blocks"] == 0,
          parsed["warnings"])
    assembled = READ.assemble_report(NO_REVIEWS_PAGE)
    check("a no-review page still assembles the engine's not-enough-data report",
          assembled["report"]["verdict"]["code"] == "not_enough_data")


def t_truncated_page_bite():
    parsed = READ.parse_product_page(TRUNCATED_PAGE)
    check("a page that never closes warns that the capture is incomplete",
          READ.WARN_TRUNCATED in _codes(parsed), parsed["warnings"])
    check("the complete reviews before the cut are still returned",
          len(parsed["reviews"]) == 5, parsed["counts"])


def t_truncated_review_bite():
    parsed = READ.parse_product_page(PARTIAL_REVIEW_PAGE)
    check("a review block still open at the end of the capture is kept and reported",
          len(parsed["reviews"]) == 5 and parsed["counts"]["partial_blocks"] == 1,
          parsed["counts"])
    check("the partial review is reported with a truncation warning",
          READ.WARN_TRUNCATED_REVIEW in _codes(parsed), parsed["warnings"])


def t_missing_listing_fields_bite():
    parsed = READ.parse_product_page(MISSING_FIELDS_PAGE)
    codes = _codes(parsed)
    check("missing rating and count are reported separately from missing reviews",
          READ.WARN_RATING in codes and READ.WARN_RATING_COUNT in codes, codes)
    check("a present product title does not raise the title warning",
          READ.WARN_TITLE not in codes, codes)


def t_malformed_markup_is_tolerated():
    try:
        parsed = READ.parse_product_page(MALFORMED_PAGE)
        raised = None
    except Exception as exc:  # pragma: no cover - the bite is the exception path
        parsed, raised = None, exc
    check("unclosed and malformed tags do not raise", raised is None, raised)
    check("the reviews that are visible are still returned",
          parsed is not None and len(parsed["reviews"]) >= 1
          and parsed["listing"]["title"] == "Malformed Widget", parsed and parsed["listing"])
    check("a malformed capture that does not close says it was truncated",
          parsed is not None and READ.WARN_TRUNCATED in _codes(parsed),
          parsed and parsed["warnings"])


def t_empty_input_is_an_empty_page_not_an_exception():
    for value in (None, "", 123, "<html></html>"):
        try:
            parsed = READ.parse_product_page(value)
            ok = True
        except Exception:  # pragma: no cover
            ok = False
        check(f"parse_product_page({value!r}) returns a page instead of raising", ok)
    parsed = READ.parse_product_page(None)
    check("an empty page is not a product page and has no reviews",
          parsed["reviews"] == [] and READ.WARN_NOT_PRODUCT in _codes(parsed), parsed)


# ---------------------------------------------------------------------------
# 4. Determinism, non-mutation and stable output
# ---------------------------------------------------------------------------

def t_deterministic_and_non_mutating():
    page = FULL_PAGE
    first = READ.parse_product_page(page, source_url="https://x.example/dp/B0TEST0001",
                                    captured_at="2026-10-25T23:00:00Z")
    second = READ.parse_product_page(page, source_url="https://x.example/dp/B0TEST0001",
                                     captured_at="2026-10-25T23:00:00Z")
    check("the same page parses to the same JSON twice",
          json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True))
    check("the caller's source_url and captured_at are passed through untouched",
          first["source_url"] == "https://x.example/dp/B0TEST0001"
          and first["captured_at"] == "2026-10-25T23:00:00Z")
    before = copy.deepcopy(first)
    READ.parse_product_page(page)
    check("parsing another page does not mutate a previous result", first == before)


# ---------------------------------------------------------------------------
# 5. The capture seam never pretends to fetch
# ---------------------------------------------------------------------------

def t_capture_seam_raises_owner_session_error():
    try:
        READ.capture_with_owner_browser()
        raised = None
    except READ.CaptureNeedsOwnerBrowser as exc:
        raised = exc
    except Exception as exc:  # pragma: no cover
        raised = exc
    check("the capture seam raises CaptureNeedsOwnerBrowser",
          isinstance(raised, READ.CaptureNeedsOwnerBrowser), type(raised))
    message = str(raised or "").lower()
    check("the error says the owner's own browser session is needed",
          "owner" in message and "browser" in message and "session" in message, message)
    check("the error says this module does not fetch pages",
          "does not fetch" in message, message)
    check("the documented message is the one raised",
          READ.CAPTURE_MESSAGE == str(raised))
    try:
        READ.capture_with_owner_browser("https://www.amazon.example/dp/B0TEST0001")
        second = None
    except READ.CaptureNeedsOwnerBrowser as exc:
        second = exc
    check("even given a URL the seam raises instead of fetching", second is not None)


# ---------------------------------------------------------------------------
# 6. assemble_report: the engine report, with the records kept
# ---------------------------------------------------------------------------

def t_assemble_report_returns_engine_report_and_records():
    assembled = READ.assemble_report(FULL_PAGE,
                                     source_url="https://www.amazon.example/dp/B0TEST0001")
    check("assemble_report returns the report, records, listing and warnings",
          set(assembled) >= {"report", "records", "listing", "warnings",
                             "source_url", "captured_at", "parse"},
          sorted(assembled))
    report = assembled["report"]
    check("the report is the engine's own, with the Amazon sample caveat intact",
          report["sample"]["caveat"] == ENGINE.SAMPLE_CAVEAT
          and report["sample"]["readable"] == 5, report["sample"])
    check("the report was built from exactly the returned records",
          len(assembled["records"]) == 5
          and len({record["reviewer"] for record in assembled["records"]}) == 5)
    check("the healthy page is not reported as not-enough-data",
          report["verdict"]["code"] != "not_enough_data", report["verdict"])
    check("the pass-through engine metadata is in parse",
          assembled["parse"]["engine"]["name"] == "jarvis_product_read"
          and assembled["parse"]["counts"]["reviews"] == 5, assembled["parse"])


def t_engine_quote_validation_still_bites_from_a_page():
    model = {"aspects": [
        {"aspect": "battery life", "stance": "positive",
         "quotes": ["The battery lasts about 9 hours at half volume",
                    "an invented quote that is not on the page"]},
    ]}
    assembled = READ.assemble_report(FULL_PAGE, model=model)
    check("a real quote from the page is accepted by the engine's quote validator",
          assembled["report"]["model"]["quotes_accepted"] == 1
          and "The battery lasts about 9 hours at half volume"
          in json.dumps(assembled["report"]["aspects"]), assembled["report"]["model"])
    check("an invented quote is dropped and counted",
          assembled["report"]["model"]["quotes_dropped"] == 1,
          assembled["report"]["model"])
    check("the aspects section is available because a model reading was passed",
          assembled["report"]["aspects"]["available"] is True)


def t_page_warnings_travel_with_the_assembly():
    assembled = READ.assemble_report(NO_REVIEWS_PAGE)
    check("the assembly carries the page's incomplete-read warnings",
          READ.WARN_NO_REVIEWS in [w["code"] for w in assembled["warnings"]],
          assembled["warnings"])


# ---------------------------------------------------------------------------
# 7. No network, no browser, no storage, no subprocess
# ---------------------------------------------------------------------------

def t_network_spy():
    calls = []
    real_socket = socket.socket
    real_create = socket.create_connection
    real_urlopen = urllib.request.urlopen
    real_http = http.client.HTTPConnection

    def spy_socket(*args, **kwargs):
        calls.append("socket")
        raise AssertionError("the read path tried to open a socket")

    def spy_create(*args, **kwargs):
        calls.append("connect")
        raise AssertionError("the read path tried to connect")

    def spy_urlopen(*args, **kwargs):
        calls.append("urlopen")
        raise AssertionError("the read path tried to read a URL")

    def spy_http(*args, **kwargs):
        calls.append("http")
        raise AssertionError("the read path tried to build an HTTP connection")

    try:
        socket.socket = spy_socket
        socket.create_connection = spy_create
        urllib.request.urlopen = spy_urlopen
        http.client.HTTPConnection = spy_http
        READ.parse_product_page(FULL_PAGE)
        READ.assemble_report(FULL_PAGE)
        try:
            READ.capture_with_owner_browser()
        except READ.CaptureNeedsOwnerBrowser:
            pass
    finally:
        socket.socket = real_socket
        socket.create_connection = real_create
        urllib.request.urlopen = real_urlopen
        http.client.HTTPConnection = real_http
    check("no socket, connection, URL or HTTP call was made", calls == [], calls)


def t_imports_are_only_the_parser_re_and_the_engine():
    tree = ast.parse(inspect.getsource(READ))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    check("the module's only imports are html.parser, re and the engine module",
          roots == {"html", "re", "jarvis_product_research", "__future__"}, sorted(roots))
    forbidden = {"socket", "urllib", "http", "requests", "subprocess", "os",
                 "pathlib", "playwright", "selenium", "webbrowser", "browser"}
    check("it imports no network, browser, storage or process module",
          not (roots & forbidden), sorted(roots & forbidden))
    call_names = {node.func.id for node in ast.walk(tree)
                  if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    check("it never calls open()/urlopen() or a shell",
          not (call_names & {"open", "urlopen", "system", "popen", "exec", "eval"}),
          sorted(call_names & {"open", "urlopen", "system", "popen", "exec", "eval"}))


def t_runtime_namespace_has_no_browser_modules():
    present = [name for name in ("socket", "urllib", "http", "requests",
                                 "subprocess", "playwright", "selenium", "webbrowser")
               if name in vars(READ)]
    check("the module object holds no browser/network module in its namespace",
          present == [], present)
    imported = sorted({value.__name__ for value in vars(READ).values()
                       if type(value).__name__ == "module"})
    check("the only module objects in its namespace are the engine and re",
          imported == ["jarvis_product_research", "re"], imported)


# ---------------------------------------------------------------------------
# 8. The documented shape of the read path
# ---------------------------------------------------------------------------

def t_warning_codes_are_stable_names():
    codes = {READ.WARN_CHALLENGE, READ.WARN_NOT_PRODUCT, READ.WARN_TITLE,
             READ.WARN_RATING, READ.WARN_RATING_COUNT, READ.WARN_NO_REVIEWS,
             READ.WARN_TRUNCATED, READ.WARN_TRUNCATED_REVIEW,
             READ.WARN_MISSING_FIELDS}
    check("every warning has a stable, plain code",
          all(isinstance(code, str) and code == code.lower() and " " not in code
              for code in codes) and len(codes) == 9, sorted(codes))
    check("the capture error is a RuntimeError subclass",
          issubclass(READ.CaptureNeedsOwnerBrowser, RuntimeError))
    check("the module names itself and says it is offline and read-only",
          READ.parse_product_page(None)["engine"]["network"] is False
          and READ.parse_product_page(None)["engine"]["read_only"] is True)


TESTS = (
    t_listing_facts_are_typed,
    t_listing_falls_back_to_canonical_and_doc_title,
    t_unreadable_listing_values_are_none_not_guesswork,
    t_reviews_are_engine_records,
    t_records_pass_through_the_engine_schema,
    t_absent_fields_are_counted_not_invented,
    t_full_page_has_no_warnings,
    t_challenge_page_bite,
    t_not_a_product_page_bite,
    t_no_reviews_bite,
    t_truncated_page_bite,
    t_truncated_review_bite,
    t_missing_listing_fields_bite,
    t_malformed_markup_is_tolerated,
    t_empty_input_is_an_empty_page_not_an_exception,
    t_deterministic_and_non_mutating,
    t_capture_seam_raises_owner_session_error,
    t_assemble_report_returns_engine_report_and_records,
    t_engine_quote_validation_still_bites_from_a_page,
    t_page_warnings_travel_with_the_assembly,
    t_network_spy,
    t_imports_are_only_the_parser_re_and_the_engine,
    t_runtime_namespace_has_no_browser_modules,
    t_warning_codes_are_stable_names,
)


def main() -> int:
    for test in TESTS:
        print(f"\n--- {test.__name__} ---")
        try:
            test()
        except Exception:
            FAILED.append(test.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, 0 skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
