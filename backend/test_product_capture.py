"""test_product_capture.py - the product-page capture seam
(jarvis_product_capture.py).

    py -3 -B backend/test_product_capture.py

FIXTURE HTML ONLY. Nothing in this suite opens a browser, starts a driver,
fetches a URL or writes a file: the capture seam takes an injected driver and
these tests inject fakes over hand-written pages. The real browser profile, the
one-time owner login and a real Amazon read are NOT-TESTABLE in this container
and are reported as such; the real driver is proved to be built WITHOUT fetching
anything, to use the browser module's public read seam, and to refuse a
read-only address before that seam is called.

The suite also proves the module's four states (product page, owner login,
challenge, not a product page), the read-only address policy, every refusal
path, no network, no storage, and an AST scan of the module's own source for
forbidden imports/calls.
"""
from __future__ import annotations

import ast
import http.client
import inspect
import socket
import sys
import traceback
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import jarvis_product_capture as CAP  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


PRODUCT_PAGE = """<!doctype html><html><head>
<title>Amazon.com: Synthetic Widget 3000: Home</title></head><body>
<span id="productTitle">Synthetic Widget 3000</span>
<span id="acrPopover" title="4.5 out of 5 stars"></span>
<span id="acrCustomerReviewText">1,234 ratings</span>
<div data-hook="review" id="customer_review-1">
 <span data-hook="review-body">The battery lasts nine hours and the case fits well.</span>
</div>
</body></html>"""

SIGNIN_PAGE = """<!doctype html><html><head><title>Amazon Sign-In</title></head>
<body><div id="authportal-main-section">
<h1>Sign in</h1><form action="/ap/signin">
<label>Email <input type="email" name="email"></label>
<label>Password <input type="password" name="password"></label>
<input type="submit" value="Sign in">
</form></div></body></html>"""

CHALLENGE_PAGE = """<!doctype html><html><head><title>Bot check</title></head>
<body><h4>Enter the characters you see below</h4>
<form action="/errors/validateCaptcha"><input id="captchacharacters"></form>
<p>Sorry, we just need to make sure you're not a robot.</p></body></html>"""

NOT_PRODUCT_PAGE = """<!doctype html><html><head>
<title>Amazon.com: Online Shopping</title></head><body>
<div id="nav-belt">Navigation</div>
<div data-component-type="s-search-result">A search result, not a product page.</div>
</body></html>"""


class FakeDriver:
    """The only shape the seam assumes: a callable/`get_html` returning HTML."""

    def __init__(self, html, *, login_calls=None):
        self.html = html
        self.urls = []
        self.login_calls = login_calls if login_calls is not None else []

    def get_html(self, url):
        self.urls.append(url)
        return self.html

    def open_owner_login(self):
        self.login_calls.append(True)


def t_classify_four_states():
    check("a product page is classified as a product page",
          CAP.classify_page(PRODUCT_PAGE) == "product_page")
    check("a sign-in page needs the owner, not a product read",
          CAP.classify_page(SIGNIN_PAGE) == "owner_login_required")
    check("a CAPTCHA page is a challenge, never solvable here",
          CAP.classify_page(CHALLENGE_PAGE) == "challenge")
    check("a search page is not a product page",
          CAP.classify_page(NOT_PRODUCT_PAGE) == "not_a_product_page")
    check("empty and non-string input is not a product page, never a crash",
          CAP.classify_page("") == "not_a_product_page"
          and CAP.classify_page(None) == "not_a_product_page"
          and CAP.classify_page(123) == "not_a_product_page")
    check("a page carrying both a title and a password box still asks the owner",
          CAP.classify_page(PRODUCT_PAGE.replace("</body>",
          '<input type="password" name="password"></body>')) == "owner_login_required")


def t_capture_with_a_fake_driver():
    driver = FakeDriver(PRODUCT_PAGE)
    html = CAP.capture_page("https://www.amazon.example/dp/B0TEST0001", driver=driver)
    check("a fake driver's product HTML is returned unchanged", html == PRODUCT_PAGE)
    check("the driver is asked for exactly the listing URL",
          driver.urls == ["https://www.amazon.example/dp/B0TEST0001"], driver.urls)
    check("capture is deterministic for the same page",
          CAP.capture_page("https://www.amazon.example/dp/B0TEST0001",
                           driver=FakeDriver(PRODUCT_PAGE)) == html)
    object_driver = FakeDriver(PRODUCT_PAGE)
    check("an object with get_html(url) is the same supported shape",
          CAP.capture_page("https://www.amazon.example/dp/B0TEST0001",
                           driver=object_driver) == PRODUCT_PAGE)


def t_capture_refuses_honestly():
    def raises(exc_type, driver, url="https://www.amazon.example/dp/B0TEST0001"):
        try:
            CAP.capture_page(url, driver=driver)
            return None
        except exc_type as exc:
            return exc
        except Exception:
            return "wrong-type"

    challenge = raises(CAP.ChallengeDetected, FakeDriver(CHALLENGE_PAGE))
    check("a challenge page raises ChallengeDetected with a plain message",
          isinstance(challenge, CAP.ChallengeDetected)
          and "captcha" in str(challenge).lower()
          and "does not solve" in str(challenge).lower(), challenge)
    login = raises(CAP.OwnerLoginRequired, FakeDriver(SIGNIN_PAGE))
    check("a sign-in page raises OwnerLoginRequired and names the owner",
          isinstance(login, CAP.OwnerLoginRequired)
          and "owner" in str(login).lower() and "sign in" in str(login).lower(), login)
    not_product = raises(CAP.CaptureUnavailable, FakeDriver(NOT_PRODUCT_PAGE))
    check("a non-product page raises CaptureUnavailable, not a report",
          isinstance(not_product, CAP.CaptureUnavailable)
          and "product page" in str(not_product).lower(), not_product)
    check("no driver at all is refused instead of fetching",
          isinstance(raises(CAP.CaptureUnavailable, None), CAP.CaptureUnavailable))
    check("a driver returning nothing is refused as unavailable",
          isinstance(raises(CAP.CaptureUnavailable, FakeDriver(None)),
                     CAP.CaptureUnavailable))
    check("a driver that raises is refused, never guessed at",
          isinstance(raises(CAP.CaptureUnavailable, lambda url: 1 / 0),
                     CAP.CaptureUnavailable))

    def broken_driver(url):
        raise RuntimeError("browser crashed")

    check("a driver's own exception becomes CaptureUnavailable",
          isinstance(raises(CAP.CaptureUnavailable, broken_driver),
                     CAP.CaptureUnavailable))
    check("an invalid listing address is refused before a driver is called",
          isinstance(raises(CAP.CaptureUnavailable, FakeDriver(PRODUCT_PAGE),
                            "not a url"), CAP.CaptureUnavailable))
    check("an address carrying credentials is refused",
          isinstance(raises(CAP.CaptureUnavailable, FakeDriver(PRODUCT_PAGE),
                            "https://user:pass@example.com/dp/X"),
                     CAP.CaptureUnavailable))
    object_without_getter = object()
    check("an object with no get_html is refused, not invented around",
          isinstance(raises(CAP.CaptureUnavailable, object_without_getter),
                     CAP.CaptureUnavailable))


def t_owner_login_seam():
    driver = FakeDriver(PRODUCT_PAGE)
    CAP.open_owner_login(driver)
    check("a driver's one-time login flow is called and returns cleanly",
          driver.login_calls == [True], driver.login_calls)
    try:
        CAP.open_owner_login()
        raised = None
    except CAP.OwnerLoginRequired as exc:
        raised = exc
    check("without a driver the login seam raises OwnerLoginRequired with instructions",
          isinstance(raised, CAP.OwnerLoginRequired)
          and "owner" in str(raised).lower()
          and "password" in str(raised).lower(), raised)
    tree = ast.parse(inspect.getsource(CAP))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    browser_api = {"playwright", "selenium", "webbrowser", "chromium", "launch"}
    check("the login seam never opens a browser by itself",
          not (names & browser_api), sorted(names & browser_api))
    try:
        CAP.open_owner_login(object())
        raised2 = None
    except CAP.OwnerLoginRequired as exc:
        raised2 = exc
    check("an object without a login flow still asks the owner", raised2 is not None)


def t_real_driver_is_a_read_only_browser_session_driver():
    driver = CAP.real_driver()
    check("the real driver is built without fetching or opening anything",
          hasattr(driver, "get_html") and callable(driver.get_html)
          and hasattr(driver, "open_owner_login")
          and callable(driver.open_owner_login))
    check("... and it is bound to the product-check session's persistent page",
          getattr(CAP.real_driver(), "session", "") == CAP.PRODUCT_SESSION
          == "product-check")
    # A fake reader/opener is the tests' own injection point: the REAL browser
    # is never called here, and the read-only policy is refused BEFORE either.
    calls = []

    def reader(session, url):
        calls.append(("read", session, url))
        return PRODUCT_PAGE

    def opener(session, url):
        calls.append(("login", session, url))
        return url

    fake = CAP.browser_driver(reader=reader, opener=opener)
    html = fake.get_html("https://www.amazon.com/dp/B0TEST0001")
    check("the driver hands the browser's own HTML back unchanged", html == PRODUCT_PAGE)
    check("... through the documented read seam with the session and the URL",
          calls == [("read", "product-check", "https://www.amazon.com/dp/B0TEST0001")],
          calls)
    fake.open_owner_login()
    check("the login seam opens the sign-in page for the owner, typing nothing",
          calls[-1] == ("login", "product-check", CAP.SIGNIN_URL), calls)
    calls.clear()
    for bad in ("https://www.amazon.com/gp/cart/view.html",
                "https://www.amazon.com/checkout/entry",
                "https://www.amazon.com/gp/your-account/order-history"):
        try:
            fake.get_html(bad)
            raised = None
        except CAP.CaptureUnavailable as exc:
            raised = exc
        check(f"the driver refuses {bad.split('amazon.com')[1]} before any read "
              f"({bad})", raised is not None and not calls,
              (str(raised), calls))
    calls.clear()
    try:
        fake.get_html("not an address")
        raised = None
    except CAP.CaptureUnavailable as exc:
        raised = exc
    check("the driver refuses a non-address before any read",
          raised is not None and not calls, (str(raised), calls))


def t_the_read_only_address_policy_is_before_anything_else():
    for url in ("https://www.amazon.com/gp/cart/view.html",
                "https://www.amazon.com/checkout/entry",
                "https://www.amazon.com/gp/buy/",
                "https://www.amazon.com/gp/your-account/order-history",
                "https://www.amazon.com/gp/css/order-history",
                "https://www.amazon.com/account",
                "https://www.amazon.com/payment",
                "https://www.amazon.com/gp/wallet",
                "https://www.amazon.com/ap/signin?openid.return_to=x"):
        why = CAP.readonly_problem(url)
        check(f"a read-only address is refused BEFORE a card: {url.split('amazon.com')[1]}",
              bool(why) and "cart, checkout, order, account, payment or sign-in" in why,
              why)
    # A product page whose own slug CONTAINS one of those words is still fine:
    # the policy reads WHOLE path segments, never a substring.
    for url in ("https://www.amazon.com/Some-Order-Book/dp/B0TEST0001",
                "https://www.amazon.com/Cartoon-History/dp/B0TEST0001/ref=cm_cr_arp",
                "https://www.amazon.com/dp/B0TEST0001?th=1&psc=1"):
        check(f"a product page is not refused for a word in its slug: {url.split('amazon.com')[1]}",
              CAP.readonly_problem(url) == "", CAP.readonly_problem(url))
    check("capture_page refuses a read-only address with no driver and no card",
          CAP.readonly_problem("https://www.amazon.com/gp/cart/view.html") != "")
    try:
        CAP.capture_page("https://www.amazon.com/gp/cart/view.html",
                         driver=FakeDriver(PRODUCT_PAGE))
        raised = None
    except CAP.CaptureUnavailable as exc:
        raised = exc
    check("... and the fake driver was never asked for a page",
          isinstance(raised, CAP.CaptureUnavailable)
          and "cart, checkout, order" in str(raised), raised)


def t_the_product_address_policy_is_amazon_only():
    good = ["https://www.amazon.com/dp/B0TEST0001",
            "https://www.amazon.co.uk/gp/product/B0TEST0001",
            "https://smile.amazon.com/dp/B0TEST0001"]
    bad = ["https://example.com/dp/B0TEST0001",
           "https://www.amazon.com/s?k=widget",
           "https://www.amazon.com/Some-Product",
           "https://amazon.evil.example/dp/B0TEST0001",
           "not an address",
           "https://user:pass@www.amazon.com/dp/B0TEST0001"]
    check("real Amazon product addresses pass the shape check",
          all(CAP.product_address_problem(u) == "" for u in good),
          [CAP.product_address_problem(u) for u in good])
    problems = [CAP.product_address_problem(u) for u in bad]
    check("a non-Amazon address, a search page, a page without an ASIN, a lookalike "
          "host, junk, and an address carrying credentials are all refused",
          all(problems), problems)
    check("the lookalike host is refused for the host, not by luck",
          "not an Amazon product address" in
          CAP.product_address_problem("https://amazon.evil.example/dp/B0TEST0001"),
          CAP.product_address_problem("https://amazon.evil.example/dp/B0TEST0001"))


def t_module_has_no_network_or_storage():
    calls = []
    real_socket, real_create = socket.socket, socket.create_connection
    real_urlopen, real_http = urllib.request.urlopen, http.client.HTTPConnection

    def spy(name):
        def _spy(*args, **kwargs):
            calls.append(name)
            raise AssertionError(f"capture tried to {name}")
        return _spy

    try:
        socket.socket = spy("socket")
        socket.create_connection = spy("connect")
        urllib.request.urlopen = spy("urlopen")
        http.client.HTTPConnection = spy("http")
        CAP.classify_page(PRODUCT_PAGE)
        CAP.capture_page("https://www.amazon.example/dp/B0TEST0001",
                         driver=FakeDriver(PRODUCT_PAGE))
        for call in (lambda: CAP.capture_page("https://www.amazon.example/dp/B0TEST0001"),
                     CAP.real_driver, CAP.open_owner_login):
            try:
                call()
            except (CAP.CaptureUnavailable, CAP.OwnerLoginRequired):
                pass
    finally:
        socket.socket, socket.create_connection = real_socket, real_create
        urllib.request.urlopen, http.client.HTTPConnection = real_urlopen, real_http
    check("classify/capture/real_driver/open_owner_login make no network call", calls == [], calls)


def t_source_imports_and_calls_are_clean():
    source = inspect.getsource(CAP)
    tree = ast.parse(source)

    def roots_of(nodes):
        roots = set()
        for node in nodes:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    roots.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module:
                roots.add(node.module.split(".")[0])
        return roots

    # TOP-LEVEL imports only: importing the capture module must never import
    # the browser (or Playwright). The real driver imports the browser module
    # LAZILY, inside the method that is about to open a window - so a machine
    # without Playwright can still import and classify fixture HTML.
    top = roots_of(tree.body)
    check("the module's top-level imports are only the read half (plus __future__)",
          top == {"__future__", "jarvis_product_read"}, sorted(top))
    nested = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for inner in ast.walk(node):
                if isinstance(inner, (ast.Import, ast.ImportFrom)):
                    nested |= roots_of([inner])
    roots = top | nested
    check("the browser module is imported lazily, inside the real driver's own "
          "methods, and nowhere else",
          "jarvis_browser_control" in nested and "jarvis_browser_control" not in top
          and "jarvis_browser_control" not in roots_of(tree.body),
          sorted(nested))
    forbidden_roots = {"socket", "urllib", "http", "requests", "subprocess", "os",
                       "pathlib", "playwright", "selenium", "webbrowser"}
    check("it imports no network, browser, storage or process module",
          not (roots & forbidden_roots), sorted(roots & forbidden_roots))
    calls = {node.func.id for node in ast.walk(tree)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    forbidden_calls = {"open", "urlopen", "system", "popen", "exec", "eval", "compile"}
    check("it never opens a file/URL and never runs a command",
          not (calls & forbidden_calls), sorted(calls & forbidden_calls))
    check("the module carries no token or secret literal",
          "token" not in source.lower() and "secret" not in source.lower())
    bad = ast.parse("import socket\nopen('x')\nsocket.socket()")
    bad_roots = {alias.name.split(".")[0] for node in ast.walk(bad)
                 if isinstance(node, ast.Import) for alias in node.names}
    bad_calls = {node.func.id for node in ast.walk(bad)
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    check("... and the scan would fail on a forbidden import or call",
          bool(bad_roots & forbidden_roots) and bool(bad_calls & forbidden_calls))


def t_classify_is_stateless():
    first = CAP.classify_page(PRODUCT_PAGE)
    second = CAP.classify_page(PRODUCT_PAGE)
    check("classification is deterministic and leaves no state", first == second == "product_page")


TESTS = (
    t_classify_four_states,
    t_capture_with_a_fake_driver,
    t_capture_refuses_honestly,
    t_owner_login_seam,
    t_real_driver_is_a_read_only_browser_session_driver,
    t_the_read_only_address_policy_is_before_anything_else,
    t_the_product_address_policy_is_amazon_only,
    t_module_has_no_network_or_storage,
    t_source_imports_and_calls_are_clean,
    t_classify_is_stateless,
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
