"""test_product_check_wiring.py - the product check WIRED: one tool, one card,
one PC-only route, and the report in plain words.

    py -3 -B backend/test_product_check_wiring.py

WHY THIS SUITE EXISTS (2026-11-04). The engine, the read half and the capture
seam shipped between 2026-10-25 and 2026-10-26 and **nothing imported them**:
no route, no chat tool, no approval card, no app surface. The owner's choice on
2026-11-04 was "wire the existing product check into Jarvis", so this suite is
the proof that the door exists and that it cannot act like a different feature:

  1. ONE model tool (`product_check`), offered ONLY while the feature's own
     `[product_check] enabled` line is true, at tier "ask", PC-only, and in
     NEEDS_A_PERSON - a person's yes, every time, whatever the settings file
     says;
  2. ONE card, naming the page in full and saying "read-only; nothing is
     bought or added to a cart";
  3. ONE address: a cart/checkout/order/account/payment/sign-in address is
     refused BEFORE a card, and a non-Amazon address or one without an ASIN is
     refused too;
  4. a challenge page and an owner-login page are refused in plain words, never
     retried, never typed into, never solved;
  5. the report: the engine's SAMPLE caveat FIRST, the eight signals with
     counts and examples, every set-aside review with its reasons, and what
     could not be checked - and NEVER a trust score and NEVER a per-review
     fake/real verdict, pinned structurally and in the answer;
  6. the route: POST /api/product/check, PC-only (403 before the body), off by
     default, one card, then the JSON report;
  7. the words: the card words exist for the action, the feature catalogue row
     exists, and the action is registered in the shipped gate table and tier
     line - proven from the FILES, because `jarvis_gate.py` is the owner's own
     file and is not in `backend/`.

FIXTURES ONLY. Every check injects a fake driver or fake gate; no browser, no
network, no real settings file and no model. Socket and urlopen are spied for
the whole run, so a real fetch would fail the suite by name.
"""
from __future__ import annotations

import ast
import http.client
import io
import json
import os
import socket
import sys
import tempfile
import traceback
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent

# Hermetic before any shipped module reads a config: the owner's real
# ~/.openjarvis must never decide what this suite sees.
TMP = Path(tempfile.mkdtemp(prefix="jarvis-product-check-"))
CONFIG_DIR = TMP / "config"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
os.environ["OPENJARVIS_CONFIG_DIR"] = str(CONFIG_DIR)
os.environ["JARVIS_CONFIG_DIR"] = str(CONFIG_DIR)
os.environ["JARVIS_FRAMEWORK_TOML"] = str(TMP / "jarvis-framework.toml")

sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "rebuilt"))

import jarvis_card_words as WORDS  # noqa: E402
import jarvis_product_capture as CAPTURE  # noqa: E402
import jarvis_product_check as PC  # noqa: E402
import jarvis_product_research as ENGINE  # noqa: E402
import jarvis_agent as AG  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
#   Synthetic page fixtures - hand-written, never fetched
# ---------------------------------------------------------------------------

_HEAD = """<!doctype html>
<html><head>
<title>Amazon.com: Synthetic Widget 3000: Home and Kitchen</title>
<link rel="canonical" href="https://www.amazon.com/dp/B0TEST0001">
</head><body data-asin="B0TEST0001">
<span id="productTitle">Synthetic Widget 3000</span>
<span id="acrPopover" title="4.3 out of 5 stars"></span>
<span id="acrCustomerReviewText">1,234 ratings</span>
"""


def _review(number, star, title, date, body, *, verified=False, vine=False):
    badge = '<span data-hook="avp-badge">Verified Purchase</span>' if verified else ""
    vine_badge = ('<span data-hook="vine-review-badge">Vine Customer Review of Free '
                  'Product</span>') if vine else ""
    return f"""<div data-hook="review" id="customer_review-{number}">
<a data-hook="review-title"><i><span>{star} out of 5 stars</span></i>
<span>{title}</span></a>
<span data-hook="review-date">Reviewed in Testland on {date}</span>
{badge}{vine_badge}
<span data-hook="review-body">{body}</span>
</div>
"""


_INCENTIVE = ("Received this product for free in exchange for a review. It is light "
              "and the screen is six cm wide.")
_DUPLICATE = ("The battery lasts about nine hours at half volume and the case fits in "
              "my jacket pocket every day.")
_REVIEWS = [
    _review(1, 4.0, "Solid for the price", "2 August 2026", _DUPLICATE, verified=True),
    _review(2, 5.0, "Good fit", "19 August 2026",
            "I measured fourteen cm across the palm and the large size fits exactly "
            "right for my hand.", verified=True),
    _review(3, 3.0, "Mixed feelings", "5 September 2026",
            "Sound is clear but the charging port is loose after three months of "
            "careful use.", verified=True),
    _review(4, 2.0, "Broke early", "21 September 2026",
            "The left hinge cracked after six weeks of light use and the return form "
            "wanted a twelve digit code.", verified=True),
    _review(5, 5.0, "Free sample", "2 October 2026", _INCENTIVE, vine=True),
    # The same body again: near-duplicate wording, and an unverified 5-star. It
    # must appear in the set-aside list with BOTH reasons and stay counted.
    _review(6, 5.0, "Amazing", "2 October 2026", _INCENTIVE),
]
PRODUCT_PAGE = _HEAD + "".join(_REVIEWS) + "</body></html>"
CHALLENGE_PAGE = """<!doctype html><html><body>
<h4>Enter the characters you see below</h4>
<form action="/errors/validateCaptcha"><input id="captchacharacters"></form>
<p>Sorry, we just need to make sure you're not a robot.</p></body></html>"""
SIGNIN_PAGE = """<!doctype html><html><head><title>Amazon Sign-In</title></head>
<body><div id="authportal-main-section"><h1>Sign in</h1>
<form action="/ap/signin"><label>Password <input type="password" name="password">
</label></form></div></body></html>"""
NOT_A_PRODUCT_PAGE = """<!doctype html><html><head><title>Amazon.com: Online Shopping
</title></head><body><div id="nav-belt">Navigation</div></body></html>"""

URL = "https://www.amazon.com/dp/B0TEST0001"


class FakeDriver:
    """The capture seam's injection point: a `get_html(url)` and no browser."""

    def __init__(self, html=PRODUCT_PAGE, *, fail=None):
        self.html = html
        self.fail = fail
        self.urls = []

    def get_html(self, url):
        self.urls.append(url)
        if self.fail is not None:
            raise self.fail
        return self.html

    def open_owner_login(self):
        raise CAPTURE.OwnerLoginRequired(CAPTURE.OWNER_LOGIN_MESSAGE)


class FakeVerdict:
    def __init__(self, allowed=True, tier="ask", outcome="approved",
                 action=PC.ACTION, reason="the owner said yes"):
        self.allowed = allowed
        self.tier = tier
        self.outcome = outcome
        self.action = action
        self.reason = reason


class FakeGate:
    """Records what the route asked, and answers with a chosen verdict."""

    def __init__(self, verdict=None, *, raises=None):
        self.calls = []
        self.verdict = verdict if verdict is not None else FakeVerdict()
        self.raises = raises

    def __call__(self, action, detail=None, prompt=""):
        self.calls.append((action, dict(detail or {}), prompt))
        if self.raises is not None:
            raise self.raises
        return self.verdict


def _write_settings(enabled):
    """A real settings file holding the feature's own switch line."""
    path = Path(os.environ["JARVIS_FRAMEWORK_TOML"])
    path.write_text(
        "[autonomy.tiers]\nproduct_check = \"ask\"\n\n"
        f"[product_check]\nenabled = {'true' if enabled else 'false'}\n",
        encoding="utf-8")
    # jarvis_framework caches the parse (invalidated by mtime+size): a test
    # that rewrites a same-size file in the same instant must not read the
    # previous answer.
    try:
        import jarvis_framework as FW
        FW._CACHE = None
        FW._CACHE_KEY = None
    except Exception:
        pass
    return path


# ---------------------------------------------------------------------------
#   1. the switch
# ---------------------------------------------------------------------------


def t_the_feature_is_off_by_default_and_reads_the_line_fresh():
    _write_settings(False)
    check("the feature is OFF when the line says false", PC.enabled() is False)
    check("... and the tool is NOT offered to the model while it is off",
          PC.TOOL_NAME not in AG.offered_tools({PC.TOOL_NAME, "calculator"}),
          AG.offered_tools({PC.TOOL_NAME, "calculator"}))
    _write_settings(True)
    check("the feature is ON when the line says true", PC.enabled() is True)
    check("... and the tool IS offered then",
          PC.TOOL_NAME in AG.offered_tools({PC.TOOL_NAME}),
          AG.offered_tools({PC.TOOL_NAME}))
    check("... and a tool list that does not name it offers nothing extra",
          PC.TOOL_NAME not in AG.offered_tools({"calculator"}))
    # A missing section, a broken file and a value that is not a real true are
    # all OFF, fail closed.
    Path(os.environ["JARVIS_FRAMEWORK_TOML"]).write_text("[autonomy.tiers]\n",
                                                         encoding="utf-8")
    check("a settings file with no [product_check] section is OFF", PC.enabled() is False)
    Path(os.environ["JARVIS_FRAMEWORK_TOML"]).write_text("[product_check\nbroken",
                                                         encoding="utf-8")
    check("an unreadable settings file is OFF", PC.enabled() is False)
    Path(os.environ["JARVIS_FRAMEWORK_TOML"]).write_text(
        "[product_check]\nenabled = \"yes\"\n", encoding="utf-8")
    check("a value that is not a real true is OFF", PC.enabled() is False)
    _write_settings(True)


def t_both_shipped_templates_carry_the_switch_and_the_tier():
    template = _read(REPO / "backend" / "rebuilt" / "jarvis-framework.toml")
    base = _read(REPO / "jarvis-backend" / "jarvis-framework.toml")
    check("the repository's template and the published base are byte-identical",
          template == base)
    check("both carry the OFF-by-default section",
          "[product_check]" in template and "enabled = false" in template)
    check("both carry the action's own ask tier",
          "product_check" in template and 'product_check              = "ask"'
          in template)
    # The section really is off in the shipped template, parsed, not assumed.
    try:
        import tomllib
        parsed = tomllib.loads(template)
        check("the shipped section parses and says false",
              parsed["product_check"]["enabled"] is False)
        check("the shipped tier table says ask",
              parsed["autonomy"]["tiers"]["product_check"] == "ask")
    except ImportError:                                   # pragma: no cover
        check("tomllib is available to parse the template", False)


# ---------------------------------------------------------------------------
#   2. the plan: one Amazon product page, and nothing else
# ---------------------------------------------------------------------------


def t_plan_accepts_one_amazon_product_page():
    plan = PC.plan("  " + URL + "  ")
    check("a real Amazon product address becomes a plan", plan.url == URL, plan.url)
    card = PC.card_text(plan)
    check("the card asks the owner's own question, word for word",
          PC.CARD_QUESTION in card, card[:200])
    check("... says read-only and that nothing is bought or added to a cart",
          "Read-only" in card and "nothing is bought" in card
          and "added to a cart" in card)
    check("... names the page in full", URL in card)
    check("... says the page's words are outside text, never learned or acted on",
          "outside text" in card and "never learned" in card)
    check("... and says the report has no trust score and no per-review verdict",
          "never a trust score" in card and "fake/real verdict" in card)


def t_plan_refuses_what_the_check_must_never_read():
    for bad, needle in (
            ("", "full address"),
            (None, "full address"),
            ("not an address", "http(s)"),
            ("https://www.amazon.com/gp/cart/view.html", "cart, checkout, order"),
            ("https://www.amazon.com/checkout/entry", "cart, checkout, order"),
            ("https://www.amazon.com/gp/buy/", "cart, checkout, order"),
            ("https://www.amazon.com/gp/your-account/order-history",
             "cart, checkout, order"),
            ("https://www.amazon.com/account", "cart, checkout, order"),
            ("https://www.amazon.com/payment", "cart, checkout, order"),
            ("https://www.amazon.com/ap/signin?openid.return_to=x",
             "cart, checkout, order"),
            ("https://example.com/dp/B0TEST0001", "not an Amazon product address"),
            ("https://www.amazon.com/s?k=widget", "not one product page"),
            ("https://amazon.evil.example/dp/B0TEST0001",
             "not an Amazon product address"),
            ("https://user:pass@www.amazon.com/dp/B0TEST0001", "credentials"),
    ):
        try:
            PC.plan(bad)
            raised = None
        except PC.CheckRefused as exc:
            raised = exc
        check(f"plan refuses {bad!r} with no card and no read",
              raised is not None and needle in raised.why,
              (str(raised), needle))
    # A product page whose own slug contains one of the blocked words is NOT a
    # cart page: the policy reads whole path segments.
    check("an honest product page is not refused for a word in its slug",
          PC.plan("https://www.amazon.com/Some-Order-Book/dp/B0TEST0001").url
          == "https://www.amazon.com/Some-Order-Book/dp/B0TEST0001")


# ---------------------------------------------------------------------------
#   3. run: the report, and the honest refusals
# ---------------------------------------------------------------------------


def t_run_builds_the_reasons_report():
    driver = FakeDriver()
    report = PC.run(PC.plan(URL), driver=driver)
    check("the driver was asked for exactly the card's address", driver.urls == [URL],
          driver.urls)
    check("the report says it succeeded", report.get("ok") is True)
    check("the report is the ENGINE's own report, unchanged in its own fields",
          report["engine"]["name"] == "jarvis_product_research"
          and report["engine"]["network"] is False
          and report["engine"]["read_only"] is True)
    check("the SAMPLE CAVEAT is the sample block's FIRST field",
          list(report["sample"])[0] == "caveat")
    check("... and it is the engine's own caveat words",
          report["sample"]["caveat"] == ENGINE.SAMPLE_CAVEAT)
    check("every one of the eight signals is in the report, in the engine's order",
          list(report["signals"]) == list(ENGINE.SIGNAL_NAMES),
          list(report["signals"]))
    for name, signal in report["signals"].items():
        check(f"signal {name} carries counts, its thresholds and a plain note",
              isinstance(signal.get("counts"), dict) and signal["counts"]
              and isinstance(signal.get("thresholds"), dict)
              and isinstance(signal.get("note"), str))
    check("the listing facts came through", report["listing"]["title"]
          == "Synthetic Widget 3000")
    check("what could not be checked is a non-empty list",
          isinstance(report["could_not_check"], list)
          and len(report["could_not_check"]) >= 3, report["could_not_check"])
    check("the verdict is one of the engine's four named codes",
          report["verdict"]["code"] in
          ("looks_solid", "mixed", "risky", "not_enough_data"),
          report["verdict"]["code"])
    check("the capture block says read-only, not stored and no network",
          report["capture"] == {"browser": "the owner's own signed-in browser session, "
                                           "one page",
                                "read_only": True, "stored": False, "network": False})
    check("the raw review records are NOT in the report (no page words ride out)",
          "records" not in report and "parse" not in report)


def t_every_set_aside_review_is_visible_with_its_reasons():
    report = PC.run(PC.plan(URL), driver=FakeDriver())
    block = report["set_aside"]
    check("at least one review was set aside by the rules", block["total"] >= 1,
          block["total"])
    for item in block["reviews"]:
        check("a set-aside review keeps its label, its reasons and a snippet",
              item.get("reviewer") and isinstance(item.get("reasons"), list)
              and item["reasons"] and item.get("snippet"))
    # The duplicated + incentivised review: BOTH reasons, and never removed
    # from the sample's own counts.
    reasons = [r for item in block["reviews"] for r in item["reasons"]]
    check("the duplicate wording is one of the recorded reasons",
          any("overlap" in r for r in reasons), reasons)
    check("the unverified 5-star is one of the recorded reasons",
          any("verified" in r or "5" in r for r in reasons), reasons)
    check("every set-aside review is still counted in the sample",
          report["sample"]["readable"] == 6, report["sample"]["readable"])


def t_no_trust_score_and_no_per_review_verdict():
    report = PC.run(PC.plan(URL), driver=FakeDriver())

    def keys_of(obj, out, depth=0):
        if depth > 6:
            return
        if isinstance(obj, dict):
            for key, value in obj.items():
                out.add(str(key).lower())
                keys_of(value, out, depth + 1)
        elif isinstance(obj, list):
            for value in obj[:50]:
                keys_of(value, out, depth + 1)

    keys = set()
    keys_of(report, keys)
    forbidden = {"score", "trust", "trust_score", "confidence", "probability",
                 "fake", "real", "authenticity", "fake_probability"}
    check("no score/trust/confidence/fake/real key anywhere in the report",
          not (keys & forbidden), sorted(keys & forbidden))
    check("the top-level verdict is the engine's NAMED RULE SUMMARY, with reasons",
          set(report["verdict"]) >= {"code", "words", "reasons",
                                     "what_would_change_it"})
    for item in report["set_aside"]["reviews"]:
        check("a set-aside review has exactly its own fields - no verdict field",
              set(item) == {"reviewer", "rating", "verified", "vine", "date",
                            "reasons", "snippet"}, sorted(item))
    answer = PC.chat_answer(report)
    check("the answer starts with the SAMPLE CAVEAT, line one",
          answer.splitlines()[0] == ENGINE.SAMPLE_CAVEAT,
          answer.splitlines()[0][:100])
    check("... and ends with the no-score line, word for word",
          PC.NO_SCORE_LINE in answer.splitlines()[-1], answer.splitlines()[-1])
    check("... and it names the verdict as a summary in words, never a number",
          "What all this adds up to:" in answer)
    check("the answer lists each signal by a plain name with counts",
          all(label in answer for label in ("Verified Purchase badges",
                                            "Vine reviews",
                                            "Incentive wording in the reviews",
                                            "Near-duplicate wording")))
    check("the answer lists the set-aside reviews and their reasons",
          "Reviews set aside, and why" in answer
          and "overlap" in answer and "snippet" not in answer)
    check("the answer says plainly there is no trust score",
          "No trust score and no fake/real verdict for any review" in answer)


def t_an_owner_login_page_is_refused_in_plain_words():
    try:
        PC.run(PC.plan(URL), driver=FakeDriver(SIGNIN_PAGE))
        raised = None
    except PC.CheckRefused as exc:
        raised = exc
    check("a sign-in page is refused, never read", raised is not None)
    check("... with the capture seam's own plain sentence",
          raised is not None and "sign in to Amazon once in Jarvis's browser window"
          in raised.why, getattr(raised, "why", ""))
    check("... the kind says the owner must sign in",
          getattr(raised, "kind", "") == "owner_login_required")
    check("... and it says Jarvis never sees or types the password, and to try again",
          raised is not None and "never sees or types the password" in raised.why
          and "ask for the check again" in raised.why)


def t_a_challenge_page_is_refused_and_never_retried():
    driver = FakeDriver(CHALLENGE_PAGE)
    try:
        PC.run(PC.plan(URL), driver=driver)
        raised = None
    except PC.CheckRefused as exc:
        raised = exc
    check("a CAPTCHA page is refused, never solved", raised is not None)
    check("... with the challenge sentence",
          raised is not None and "CAPTCHA" in raised.why
          and "does not solve" in raised.why, getattr(raised, "why", ""))
    check("... the kind is challenge", getattr(raised, "kind", "") == "challenge")
    check("... the browser was asked exactly ONCE - no retry loop",
          driver.urls == [URL], driver.urls)


def t_a_page_that_is_not_a_product_is_refused():
    try:
        PC.run(PC.plan(URL), driver=FakeDriver(NOT_A_PRODUCT_PAGE))
        raised = None
    except PC.CheckRefused as exc:
        raised = exc
    check("a page that is not a product page is refused, never reported as a product",
          raised is not None and "does not look like an Amazon product page"
          in raised.why, getattr(raised, "why", ""))
    check("... with kind unavailable", getattr(raised, "kind", "") == "unavailable")


def t_a_browser_that_cannot_open_is_refused():
    try:
        PC.run(PC.plan(URL), driver=FakeDriver(fail=RuntimeError("no Playwright")))
        raised = None
    except PC.CheckRefused as exc:
        raised = exc
    check("a browser error becomes one plain sentence, never a crash",
          raised is not None and "could not return the page HTML" in raised.why,
          getattr(raised, "why", ""))
    check("... and the answer says nothing was fetched or stored",
          raised is not None and "Nothing was fetched" in raised.why)


# ---------------------------------------------------------------------------
#   4. the route
# ---------------------------------------------------------------------------


def t_the_route_is_pc_only_and_off_by_default():
    driver = FakeDriver()
    gate = FakeGate()
    code, body = PC.handle_post({"url": URL}, here=False, gate=gate,
                                tier_of=lambda a: "ask", driver=driver)
    check("a request from another device is refused PC-only, before anything runs",
          code == 403 and body.get("pc_only") is True
          and "only the PC can run it" in body.get("error", ""), (code, body))
    check("... the gate was never asked and nothing was opened",
          gate.calls == [] and driver.urls == [])
    _write_settings(False)
    code, body = PC.handle_post({"url": URL}, here=True, gate=gate,
                                tier_of=lambda a: "ask", driver=driver)
    check("with the switch off the route answers 503 in the feature's own words",
          code == 503 and body.get("enabled") is False
          and "switched off" in body.get("error", ""), (code, body))
    check("... again with no card and no browser", gate.calls == [] and driver.urls == [])
    _write_settings(True)


def t_the_route_refuses_before_any_card():
    gate = FakeGate()
    driver = FakeDriver()
    for body_in, needle in (
            ({"url": "https://www.amazon.com/gp/cart/view.html"}, "cart, checkout"),
            ({"url": "https://example.com/dp/B0TEST0001"}, "not an Amazon product"),
            ({"url": ""}, "full address"),
            ({}, "full address"),
            ("not a dict", "JSON object"),
    ):
        code, body = PC.handle_post(body_in, here=True, gate=gate,
                                    tier_of=lambda a: "ask", driver=driver)
        check(f"the route refuses {body_in!r} with 400 and no card",
              code == 400 and needle in body.get("error", ""), (code, body))
    check("... no card was raised and no browser opened for any of them",
          gate.calls == [] and driver.urls == [])


def t_the_route_raises_one_card_then_returns_the_report():
    _write_settings(True)
    gate = FakeGate()
    driver = FakeDriver()
    code, report = PC.handle_post({"url": URL}, here=True, gate=gate,
                                  tier_of=lambda a: "ask", driver=driver)
    check("an approved card returns 200 and the report", code == 200
          and report.get("ok") is True, (code, report if code != 200 else ""))
    check("exactly ONE card was raised", len(gate.calls) == 1, gate.calls)
    action, detail, prompt = gate.calls[0]
    check("... under the product check's own action", action == PC.ACTION, action)
    check("... naming the page in full", URL in detail.get("text", ""))
    check("... with the read-only question on it",
          PC.CARD_QUESTION in detail.get("text", ""))
    check("... and the page is not said to leave the PC",
          detail.get("leaves_this_pc") is False)
    check("the browser was asked once, for the card's address", driver.urls == [URL])
    check("the report came back through the route unchanged in shape",
          list(report["sample"])[0] == "caveat"
          and list(report["signals"]) == list(ENGINE.SIGNAL_NAMES))


def t_the_route_refuses_a_denial_a_lapse_and_a_loosened_tier():
    _write_settings(True)
    driver = FakeDriver()
    for verdict, want in (
            (FakeVerdict(allowed=False, outcome="denied"), 403),
            (FakeVerdict(allowed=False, outcome="timed_out"), 403),
            (FakeVerdict(allowed=False, outcome="refused"), 403),
    ):
        gate = FakeGate(verdict)
        code, body = PC.handle_post({"url": URL}, here=True, gate=gate,
                                    tier_of=lambda a: "ask", driver=driver)
        check(f"a card answered {verdict.outcome!r} is {want} and reads nothing",
              code == want and driver.urls == [], (code, body, driver.urls))
    # A card allowed at a looser tier is NOT a person saying yes.
    for verdict in (FakeVerdict(allowed=True, tier="auto", outcome="auto"),
                    FakeVerdict(allowed=True, tier="notify", outcome="notify")):
        gate = FakeGate(verdict)
        code, body = PC.handle_post({"url": URL}, here=True, gate=gate,
                                    tier_of=lambda a: "ask", driver=driver)
        check(f"a verdict at tier {verdict.tier!r} is refused (nobody was asked)",
              code == 503 and driver.urls == [], (code, body))
    gate = FakeGate()
    code, body = PC.handle_post({"url": URL}, here=True, gate=gate,
                                tier_of=lambda a: "auto", driver=driver)
    check("a settings file that loosened the action to auto raises no card and "
          "reads nothing", code == 503 and gate.calls == [] and driver.urls == [],
          (code, body))
    gate = FakeGate(raises=RuntimeError("queue is down"))
    code, body = PC.handle_post({"url": URL}, here=True, gate=gate,
                                tier_of=lambda a: "ask", driver=driver)
    check("a gate that cannot raise the card refuses in plain words, and reads nothing",
          code == 503 and "could not be raised" in body.get("error", "")
          and driver.urls == [], (code, body))


def t_install_wraps_only_the_one_route():
    sent = []

    def make_handler():
        """A FRESH class per install: install() is idempotent by its own flag,
        so the server's origin/token callbacks are fixed at the first wrap."""
        class FakeHandler:
            def __init__(self, path, body=b"{}", peer="127.0.0.1"):
                self.path = path
                self._body = body
                self.client_address = (peer, 50000)
                self.sent = sent

            def _send(self, code, out):
                self.sent.append((code, out))

            def do_POST(self):
                self.sent.append(("original", None))

        return FakeHandler

    Handler = make_handler()
    sent.clear()
    banner = PC.install(Handler, origin_ok=lambda h: True,
                        token_ok=lambda h: True, read_body=lambda h: h._body)
    check("install() returns its own banner line", "product check" in banner.lower(),
          banner)
    check("... and marks the handler's do_POST so a second install is a no-op",
          getattr(Handler.do_POST, "_jarvis_product_check", False) is True)
    again = PC.install(Handler, origin_ok=lambda h: True,
                       token_ok=lambda h: True, read_body=lambda h: h._body)
    check("... the second install says it is already on", "already on" in again, again)

    _write_settings(True)
    real_card = PC._gate_card
    real_driver = PC.CAPTURE.real_driver
    PC._gate_card = lambda: (FakeGate(), lambda action: "ask")   # no real gate here
    # The route's real path builds the browser driver itself; substitute the
    # fake so no window is opened, and only HERE (the module stays untouched).
    PC.CAPTURE.real_driver = lambda **kwargs: FakeDriver()
    try:
        handler = Handler(PC.PATH + "/", body=json.dumps({"url": URL}).encode())
        handler.do_POST()
        check("POST /api/product/check is answered by this module, not the original",
              handler.sent and handler.sent[-1][0] == 200, handler.sent)
        sent.clear()
        other = Handler("/api/something-else", body=b"{}")
        other.do_POST()
        check("every other route still goes to the original handler",
              other.sent == [("original", None)], other.sent)
        sent.clear()
        not_origin = make_handler()
        PC.install(not_origin, origin_ok=lambda h: False, token_ok=lambda h: True,
                   read_body=lambda h: h._body)
        refused = not_origin(PC.PATH)
        refused.do_POST()
        check("the server's own origin check still runs first",
              refused.sent and refused.sent[-1][0] == 403, refused.sent)
        no_token = make_handler()
        PC.install(no_token, origin_ok=lambda h: True, token_ok=lambda h: False,
                   read_body=lambda h: h._body)
        untokened = no_token(PC.PATH)
        untokened.do_POST()
        check("... and its token check too",
              untokened.sent and untokened.sent[-1][0] == 401, untokened.sent)
        # PC-only through the real peer parsing: a remote address is refused
        # before the body is read.
        sent.clear()
        remote_handler = make_handler()
        PC.install(remote_handler, origin_ok=lambda h: True, token_ok=lambda h: True,
                   read_body=lambda h: h._body)
        real = PC._from_this_pc
        PC._from_this_pc = lambda p, l: False
        try:
            remote = remote_handler(PC.PATH,
                                    body=json.dumps({"url": URL}).encode(),
                                    peer="203.0.113.7")
            remote.do_POST()
            check("a remote caller gets 403 pc_only from the route's own door",
                  remote.sent and remote.sent[-1][0] == 403
                  and remote.sent[-1][1].get("pc_only") is True, remote.sent)
        finally:
            PC._from_this_pc = real
    finally:
        PC._gate_card = real_card
        PC.CAPTURE.real_driver = real_driver


# ---------------------------------------------------------------------------
#   5. the model tool, and the gate rows it depends on
# ---------------------------------------------------------------------------


def t_the_tool_is_registered_with_one_url_and_one_purpose():
    tool = AG.TOOLS.get(PC.TOOL_NAME)
    check("product_check is a real model tool", tool is not None)
    if tool is None:
        return
    check("its schema takes exactly one required URL",
          tool.parameters.get("required") == ["url"]
          and "url" in tool.parameters.get("properties", {}))
    check("its description says it is one Amazon page and never a verdict",
          "one Amazon product page" in tool.description
          and "never a trust score" in tool.description
          and "fake/real verdict" in tool.description)
    check("its lookup name is the action's own name",
          (tool.gate_lookup_name({}) if tool.gate_lookup_name else PC.TOOL_NAME)
          == PC.ACTION == "product_check")
    check("the tool is in NEEDS_A_PERSON: a person's yes, whatever the tier says",
          PC.TOOL_NAME in AG.NEEDS_A_PERSON, sorted(AG.NEEDS_A_PERSON))
    check("... and it is in exactly one tool group (so the short list can reach it)",
          sum(1 for _name, _why, members in AG.TOOL_GROUPS
              if PC.TOOL_NAME in members) == 1,
          [(n, m) for n, _w, m in AG.TOOL_GROUPS if PC.TOOL_NAME in m])


def t_the_tool_prepares_a_plan_or_refuses_with_no_card():
    state, text = AG._prepare_product_check({"url": URL})
    check("a good address prepares the plan and the card text",
          isinstance(state, PC.ProductPagePlan) and URL in text
          and PC.CARD_QUESTION in text)
    for bad in ("", "https://www.amazon.com/gp/cart/view.html",
                "https://example.com/dp/B0TEST0001"):
        state, _text = AG._prepare_product_check({"url": bad})
        check(f"prepare refuses {bad!r} as a marker, so no card is raised",
              isinstance(state, AG._ProductCheckRefused), type(state).__name__)


def t_the_tool_runs_the_same_plan_the_card_showed():
    plan = PC.plan(URL)
    real = PC.run
    seen = {}

    def fake_run(plan_obj, *, driver=None):
        seen["url"] = plan_obj.url
        return real(plan_obj, driver=FakeDriver())

    PC.run = fake_run
    try:
        result = AG._run_product_check({"url": "https://example.com/other"}, plan)
    finally:
        PC.run = real
    check("execute uses the CARD's plan, never a fresh one from the model's args",
          seen.get("url") == URL, seen)
    check("the result says the check ran and carries the report for delivery",
          result.get("ok") is True and result.get("checked") is True
          and isinstance(result.get("_product_report"), dict))
    report = result["_product_report"]["report"]
    check("... the full report is inside, with the caveat first",
          list(report["sample"])[0] == "caveat")
    answer = result["_product_report"]["answer"]
    check("... and the code-written answer, caveat first, is what the owner reads",
          answer.splitlines()[0] == ENGINE.SAMPLE_CAVEAT)
    check("the model-facing result carries no score field and no per-review "
          "verdict - only the instruction not to add one",
          not ({"score", "trust", "trust_score", "confidence", "probability",
                "fake", "real", "verdict_score"} & set(result))
          and "no trust score" in result.get("note", "")
          and "fake/real verdict" in result.get("note", ""), sorted(result))


def t_the_gate_rows_really_exist_in_the_shipped_files():
    gate_src = _read(REPO / "jarvis-backend" / "jarvis_gate.py")
    tier_src = _read(REPO / "backend" / "rebuilt" / "jarvis-framework.toml")
    patch = _read(REPO / "backend" / "product-check.patch")
    check("the published gate maps the tool to its action",
          re.search(r'^\s*"product_check":\s*"product_check",\s*$', gate_src, re.M)
          is not None)
    check("the published gate classifies the action with its own risk row",
          re.search(r'^\s*"product_check":\s*\("yes",\s*"outbound",', gate_src,
                    re.M) is not None)
    check("... and a denial of it proposes no standing rule",
          re.search(r'^\s*"product_check",\s*#.*denial', gate_src, re.M) is not None)
    check("product-check.patch adds the same three things for the owner's own PC",
          '"product_check": "product_check"' in patch
          and '"product_check": ("yes", "outbound",' in patch
          and re.search(r'^\+\s*"product_check",\s*#.*denial', patch, re.M)
          is not None)
    check("the shipped tier table sets the action to ask",
          re.search(r'^product_check\s*=\s*"ask"', tier_src, re.M) is not None)
    check("the action is PC-only, so only this PC can approve it",
          '"product_check"' in _read(REPO / "backend" / "jarvis_owner_check.py")
          and "product_check" in _read(REPO / "jarvis-backend" / "jarvis_owner_check.py"))
    owner_src = _read(REPO / "backend" / "jarvis_owner_check.py")
    block = owner_src[owner_src.index("PC_ONLY_ACTIONS = frozenset"):]
    block = block[:block.index("})") + 2]
    check("... in the PC_ONLY_ACTIONS set itself, not a comment",
          '"product_check"' in block, block[-80:])
    check("... and the phone's copy knows it too, so it draws no Approve button",
          '"product_check"' in _read(REPO / "jarvis-client" / "app" / "src" /
                                     "main" / "java" / "com" / "jarvis" / "client" /
                                     "net" / "ApiModels.kt"))


def t_the_card_words_exist_for_the_action():
    check("the action has a written card title",
          WORDS.has_written_title(PC.ACTION) is True)
    title = WORDS.title_for(PC.ACTION)
    check("... and it reads as words a person understands",
          "product page" in title and "_" not in title, title)
    check("... and a short summary on the same card",
          "product page" in WORDS.summary_for(PC.ACTION),
          WORDS.summary_for(PC.ACTION))


def t_the_feature_row_and_the_route_doc_exist():
    features = json.loads(_read(REPO / "features" / "features.json"))
    row = next((r for r in features if r.get("id") == "product-check"), None)
    check("the feature catalogue has a product-check row", row is not None)
    if row is not None:
        check("... it says the card and the limits plainly",
              "Read this product page" in row["asks"]
              and "no trust score" in row["limit"]
              and "OFF" in row["limit"].upper())
        check("... it is desktop-only WITH its reason",
              row["surface"] == "desktop" and bool(row.get("surface_reason")))
        check("... and it names the gate action behind the card",
              row.get("gate") == [PC.ACTION], row.get("gate"))
    api = _read(REPO / "docs" / "JARVIS-API.md")
    check("JARVIS-API documents POST /api/product/check", PC.PATH in api)
    check("... and the product_check tool", "product_check" in api)
    check("the three copies of features.json are byte-identical",
          _read(REPO / "features" / "features.json")
          == _read(REPO / "jarvis-desktop" / "src" / "features.json")
          == _read(REPO / "jarvis-client" / "app" / "src" / "main" /
                   "assets" / "features.json"))


# ---------------------------------------------------------------------------
#   6. no network, no browser, no storage
# ---------------------------------------------------------------------------


def t_nothing_in_the_wiring_makes_a_network_call():
    calls = []
    real_socket, real_create = socket.socket, socket.create_connection
    real_urlopen, real_http = urllib.request.urlopen, http.client.HTTPConnection

    def spy(name):
        def _spy(*args, **kwargs):
            calls.append(name)
            raise AssertionError(f"the product check tried to {name}")
        return _spy

    try:
        socket.socket = spy("socket")
        socket.create_connection = spy("connect")
        urllib.request.urlopen = spy("urlopen")
        http.client.HTTPConnection = spy("http")
        _write_settings(True)
        plan = PC.plan(URL)
        report = PC.run(plan, driver=FakeDriver())
        PC.chat_answer(report)
        PC.handle_post({"url": URL}, here=True,
                       gate=FakeGate(), tier_of=lambda a: "ask",
                       driver=FakeDriver())
        for bad in ("https://www.amazon.com/gp/cart/view.html",
                    "https://example.com/dp/B0TEST0001"):
            try:
                PC.plan(bad)
            except PC.CheckRefused:
                pass
        AG._prepare_product_check({"url": URL})
        AG._prepare_product_check({"url": "https://example.com/dp/B0TEST0001"})
    finally:
        socket.socket, socket.create_connection = real_socket, real_create
        urllib.request.urlopen, http.client.HTTPConnection = real_urlopen, real_http
    check("plan/run/route/prepare make no network call at all", calls == [], calls)


def t_the_wiring_module_is_read_only_by_its_own_source():
    source = (HERE / "jarvis_product_check.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = {node.func.id for node in ast.walk(tree)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    check("jarvis_product_check.py opens no file and runs no command",
          not ({"open", "urlopen", "system", "popen", "exec", "eval"} & calls),
          sorted({"open", "urlopen", "system", "popen", "exec", "eval"} & calls))
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    check("... it never names a browser module (its driver is injected)",
          "playwright" not in names and "jarvis_browser_control" not in
          {node.module for node in ast.walk(tree)
           if isinstance(node, ast.ImportFrom) and node.module})
    check("... and it never writes a page or a report anywhere",
          "write_text" not in {node.attr for node in ast.walk(tree)
                               if isinstance(node, ast.Attribute)})


def t_the_two_file_rule_holds_for_the_new_module():
    for name in ("jarvis_product_check.py", "jarvis_product_capture.py",
                 "jarvis_browser_control.py", "jarvis_owner_check.py",
                 "jarvis_agent.py", "jarvis_card_words.py"):
        pair = (REPO / "backend" / name, REPO / "jarvis-backend" / name)
        check(f"{name} is byte-identical in both shipped folders",
              pair[0].read_bytes() == pair[1].read_bytes())
    where = _read(REPO / "backend" / "_where.py")
    ps1 = _read(REPO / "scripts" / "apply-patches.ps1")
    check("the new module is in both SHIPPED lists",
          '"jarvis_product_check.py"' in where
          and "'jarvis_product_check.py'" in ps1)
    plugin = REPO / "plugins" / "ready" / "product-check" / "plugin.json"
    check("the drop-in folder exists with the module the loader calls",
          plugin.is_file() and json.loads(_read(plugin)).get("module")
          == "jarvis_product_check")


# ---------------------------------------------------------------------------


TESTS = (
    t_the_feature_is_off_by_default_and_reads_the_line_fresh,
    t_both_shipped_templates_carry_the_switch_and_the_tier,
    t_plan_accepts_one_amazon_product_page,
    t_plan_refuses_what_the_check_must_never_read,
    t_run_builds_the_reasons_report,
    t_every_set_aside_review_is_visible_with_its_reasons,
    t_no_trust_score_and_no_per_review_verdict,
    t_an_owner_login_page_is_refused_in_plain_words,
    t_a_challenge_page_is_refused_and_never_retried,
    t_a_page_that_is_not_a_product_is_refused,
    t_a_browser_that_cannot_open_is_refused,
    t_the_route_is_pc_only_and_off_by_default,
    t_the_route_refuses_before_any_card,
    t_the_route_raises_one_card_then_returns_the_report,
    t_the_route_refuses_a_denial_a_lapse_and_a_loosened_tier,
    t_install_wraps_only_the_one_route,
    t_the_tool_is_registered_with_one_url_and_one_purpose,
    t_the_tool_prepares_a_plan_or_refuses_with_no_card,
    t_the_tool_runs_the_same_plan_the_card_showed,
    t_the_gate_rows_really_exist_in_the_shipped_files,
    t_the_card_words_exist_for_the_action,
    t_the_feature_row_and_the_route_doc_exist,
    t_nothing_in_the_wiring_makes_a_network_call,
    t_the_wiring_module_is_read_only_by_its_own_source,
    t_the_two_file_rule_holds_for_the_new_module,
)

# `re` is used by one check; imported here so the module list above reads as
# the suite's own contents.
import re  # noqa: E402


def main():
    for test in TESTS:
        print(f"\n--- {test.__name__} ---")
        try:
            test()
        except Exception:
            FAILED.append(test.__name__)
            print("FAIL  " + test.__name__ + " raised")
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
