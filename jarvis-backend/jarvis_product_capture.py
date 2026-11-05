"""jarvis_product_capture.py - reading one Amazon product page from Jarvis's
own browser session, and the honest refusal when it cannot.

WHAT THIS MODULE IS, AND WHAT IT IS NOT
The product check already has its read half (`jarvis_product_read.py`: one
page's HTML -> listing facts + review records + warnings) and its engine
(`jarvis_product_research.py`: records -> reasons report). This module is the
small piece between the browser and that read half: it names the capture, it
classifies the page it was given, and it says refusal in words instead of
pretending.

THE REAL DRIVER IS HERE NOW (2026-11-04, the wiring slice). `real_driver()`
returns a driver backed by the repository's own visible browser session:
`jarvis_browser_control.read_page_html()` in the browser module's public,
documented, read-only seam. The window is the owner's own signed-in Chromium
(the persistent profile lives in the config folder), so reading a product
page reuses the sign-in the owner completed once; `open_owner_login()` opens
the sign-in page and leaves it on screen, and Jarvis never sees or types the
password. The driver is still INJECTED into `capture_page()`, so every test
can (and does) supply a fake one and no test opens a window or fetches a page.

READ-ONLY, BEFORE ANYTHING IS FETCHED. `readonly_problem(url)` refuses a cart,
checkout, order, account, payment or sign-in address by its SHAPE, with no
network call - the tool refuses such an address before a card is even raised,
and the driver checks it again as the belt. A challenge page is still never
solved, never retried and never typed into: `capture_page()` raises
`ChallengeDetected` and the owner is told to open the page themselves.

The page it is given is classified into four states by `classify_page()`:
  * "product_page"          - the read half found a product title/rating/reviews;
  * "owner_login_required"  - a sign-in page: the owner must sign in once in the
                              browser; Jarvis never sees the password and never
                              types it;
  * "challenge"             - a CAPTCHA / "are you human" page: stop; never solve
                              it, never retry in a loop;
  * "not_a_product_page"    - not an Amazon product page.
`capture_page()` calls an injected driver and refuses with one of the three
documented errors: `CaptureUnavailable`, `OwnerLoginRequired`, `ChallengeDetected`.
`open_owner_login()` is the one-time-login seam: with the real driver it opens
the sign-in page in the persistent window; without one it raises
`OwnerLoginRequired` with the plain instruction.

WHAT IS NOT TESTED HERE, PLAINLY
No real Amazon page, no real browser session and no one-time login has been
exercised by a test: this module's tests use fixture HTML, a fake driver and a
fake reader, and never open a window or make a network call. The real driver,
the persistent browser profile and the owner's login are NOT-TESTABLE in this
development container; `real_driver()` builds the driver without fetching
anything, and only a real call in the browser window would use Playwright.

Only the project's own modules: `jarvis_product_read`, and - lazily, on a real
read only - `jarvis_browser_control`. No top-level network, no browser import,
no subprocess, no file is read or written, and nothing here logs.

One honest limit about the classification: a product page that carries a sign-in
form anywhere in its HTML (a password field, or the sign-in phrases) is refused
as `owner_login_required` before the read half looks at it, because the login
check runs first. That is the conservative choice - a page that wants a sign-in
is not read - and it means a product page with a sign-in modal is refused too.

    py -3 -B backend/test_product_capture.py
"""
from __future__ import annotations

import jarvis_product_read as READ

#: The session name the product check's browser page is kept under. One page,
#: never shared with a `browser_control` plan's session.
PRODUCT_SESSION = "product-check"

#: Where the one-time sign-in page is opened. The owner signs in; Jarvis types
#: nothing and keeps nothing of it. This is Amazon's own public sign-in address.
SIGNIN_URL = "https://www.amazon.com/ap/signin"

#: A browser that is not installed, or could not open the page, is said in
#: these words - never silently turned into "no reviews found".
BROWSER_UNAVAILABLE_MESSAGE = (
    "The browser session could not open that page, so nothing was fetched and "
    "nothing was stored. Jarvis reads a product page in its own visible browser "
    "window; if Playwright is not installed on this PC it cannot open one (the "
    "browser-control feature needs it). Try again, or open the page yourself.")


#: The one instruction the owner needs for the one-time login. It is also the
#: `OwnerLoginRequired` message when no login driver has been supplied.
OWNER_LOGIN_MESSAGE = (
    "Reading a product page needs the owner's own browser session: sign in to "
    "Amazon once in Jarvis's browser window, then run the product check again. "
    "Jarvis never sees or types the password, and it never solves a CAPTCHA."
)

#: What a caller sees when no browser driver has been supplied at all.
UNAVAILABLE_MESSAGE = (
    "No browser driver is wired to this capture seam yet. The page HTML must "
    "come from Jarvis's own signed-in browser session; this module does not "
    "fetch pages, open windows or start a browser by itself."
)

#: What a caller sees when the injected driver itself could not produce HTML.
DRIVER_FAILED_MESSAGE = (
    "The browser session could not return the page HTML. Nothing was fetched "
    "or stored; try again from the owner's signed-in browser window."
)

#: What a caller sees for HTML that is not a product page at all.
NOT_A_PRODUCT_MESSAGE = (
    "The supplied HTML does not look like an Amazon product page: the product "
    "title, rating and review list were not found, so there is nothing to "
    "analyse."
)

#: What a caller sees when a challenge page is recognised.
CHALLENGE_MESSAGE = (
    "This page is a CAPTCHA or 'are you human' challenge. Jarvis does not solve "
    "challenges and did not retry: open the product page yourself in the "
    "browser, complete the challenge once, then run the check again."
)

#: Sign-in phrases seen on Amazon's sign-in page. Checked BEFORE the read half,
#: because a sign-in page is not a product page and the owner needs the login
#: action, not a list of warnings.
_SIGNIN_MARKERS = (
    "amazon sign-in",
    "amazon sign in",
    "sign in to continue",
    "authportal-main-section",
    "ap_signin",
    "/ap/signin",
)

#: Reuse the read half's own challenge markers (single source of truth) rather
#: than keeping a second list that can drift: these are the phrases its warning
#: already recognises as a challenge/sign-in page.
_CHALLENGE_MARKERS = (
    "captchacharacters",
    "amazon-captcha",
    "validatecaptcha",
    "robot check",
    "enter the characters you see",
    "type the characters you see",
    "not a robot",
)


class CaptureUnavailable(RuntimeError):
    """No page HTML could be obtained, honestly."""


class OwnerLoginRequired(RuntimeError):
    """The owner must sign in once in Jarvis's own browser before a read."""


class ChallengeDetected(RuntimeError):
    """A CAPTCHA / bot challenge is in the way; it is never solved here."""


def _plain_html(html) -> str:
    return html if isinstance(html, str) else ""


def _has_signin_page(html: str) -> bool:
    """A sign-in page needs the owner, not a product read.

    A password field is the decisive signal; the phrases cover the pages where
    the password is only filled on the next step."""
    lowered = html.lower()
    if 'type="password"' in lowered or "type='password'" in lowered:
        return True
    if "<input" in lowered and ("password" in lowered or "passwd" in lowered):
        return True
    return any(marker in lowered for marker in _SIGNIN_MARKERS)


def _has_challenge_page(html: str) -> bool:
    lowered = html.lower()
    return any(marker in lowered for marker in _CHALLENGE_MARKERS)


def classify_page(html, *, source_url=None) -> str:
    """Classify one supplied page string, WITHOUT fetching anything.

    Returns exactly one of `"product_page"`, `"owner_login_required"`,
    `"challenge"` or `"not_a_product_page"`. The sign-in and challenge checks
    come first: a page can contain a product title while also asking for a
    person. The read half's own parser supplies the product-page decision and
    its two warnings, so this module does not keep a second page model."""
    text = _plain_html(html)
    if _has_challenge_page(text):
        return "challenge"
    if _has_signin_page(text):
        return "owner_login_required"
    parsed = READ.parse_product_page(text, source_url=source_url)
    codes = {warning["code"] for warning in parsed.get("warnings", [])}
    if READ.WARN_CHALLENGE in codes:
        return "challenge"
    if READ.WARN_NOT_PRODUCT in codes:
        return "not_a_product_page"
    listing = parsed.get("listing", {})
    if listing.get("title") or listing.get("star_rating") is not None \
            or parsed.get("reviews"):
        return "product_page"
    return "not_a_product_page"


def _url_problem(url) -> str:
    if not isinstance(url, str):
        return "the listing address is not text"
    cleaned = url.strip()
    if not cleaned:
        return "the listing address is empty"
    lowered = cleaned.lower()
    if not (lowered.startswith("https://") or lowered.startswith("http://")):
        return "the listing address is not an http(s) address"
    try:
        host = cleaned.split("://", 1)[1].split("/", 1)[0]
    except IndexError:
        return "the listing address is not an http(s) address"
    if "@" in host:
        return "the listing address contains credentials"
    return ""


#: Path segments that are never a product page to READ: the owner's cart, the
#: checkout, order history, the account pages, payment and the sign-in page
#: itself. Tested as WHOLE segments, never as a substring: a product page's own
#: slug may contain one of these words ("Some-Order-Book/dp/..."), and a read
#: policy that refuses by substring would refuse honest product pages.
_BLOCKED_SEGMENTS = frozenset({
    "cart", "checkout", "order", "orders", "order-history", "account",
    "account-orders", "payment", "payments", "wallet", "signin", "sign-in",
    "buy", "buy-now", "purchase", "place-order", "add-to-cart",
})
#: Two-segment Amazon shapes for the same pages ("gp/cart", "gp/buy").
_BLOCKED_PAIRS = frozenset({
    "gp/cart", "gp/checkout", "gp/buy", "gp/order", "gp/orders",
    "gp/css/order-history", "gp/your-account", "gp/wallet", "gp/payment",
    "ap/signin",
})


def _path_segments(url: str) -> list:
    """The URL's path as whole, lower-case segments - no imports, no parsing
    library, and no network: this module stays a plain string classifier."""
    text = str(url or "").strip().lower()
    if "://" not in text:
        return []
    rest = text.split("://", 1)[1]
    if "/" not in rest:
        return []
    path = "/" + rest.split("/", 1)[1]
    path = path.split("?", 1)[0].split("#", 1)[0]
    return [part for part in path.split("/") if part]


def readonly_problem(url) -> str:
    """Why this address must not be READ, or "" when it may be.

    A cart, checkout, order, account, payment or sign-in address is refused by
    its SHAPE before anything is fetched: the product check reads one product
    page and never presses, buys or pays for anything. Pure string work - no
    DNS lookup, no network call, no browser - so the refusal happens before a
    window is even opened."""
    segments = _path_segments(url)
    if not segments:
        return ""
    for segment in segments:
        if segment in _BLOCKED_SEGMENTS:
            return ("That is a cart, checkout, order, account, payment or sign-in "
                    "address, not a product page. The product check reads one "
                    "product page and never buys, orders, signs in or adds to a "
                    "cart, so nothing was opened.")
    for index in range(len(segments) - 1):
        pair = segments[index] + "/" + segments[index + 1]
        if pair in _BLOCKED_PAIRS:
            return ("That is a cart, checkout, order, account, payment or sign-in "
                    "address, not a product page. The product check reads one "
                    "product page and never buys, orders, signs in or adds to a "
                    "cart, so nothing was opened.")
    return ""


#: Amazon's own public shop domains. A product check reads Amazon product
#: pages only (that is the page shape the read half understands), and the list
#: is explicit so a lookalike host ("amazon.evil.example") cannot pass.
_AMAZON_HOSTS = (
    "amazon.com", "amazon.co.uk", "amazon.de", "amazon.fr", "amazon.ca",
    "amazon.com.au", "amazon.co.jp", "amazon.in", "amazon.it", "amazon.es",
    "amazon.nl", "amazon.se", "amazon.pl", "amazon.ae", "amazon.sa",
    "amazon.sg", "amazon.com.br", "amazon.com.mx", "amazon.com.tr",
    "amazon.eg", "amazon.be",
)
#: One product page carries its ASIN either as /dp/<ASIN> or /gp/product/<ASIN>.
_AMAZON_ASIN_MARKERS = ("/dp/", "/gp/product/", "/gp/aw/d/")


def _host_of(url: str) -> str:
    text = str(url or "").strip().lower()
    if "://" not in text:
        return ""
    host = text.split("://", 1)[1].split("/", 1)[0]
    return host.split(":", 1)[0]


def product_address_problem(url) -> str:
    """Why this address is not one Amazon product page to read, or "".

    Used BEFORE a card is raised: a shape check, then the read-only policy,
    then the Amazon host and ASIN shape. No network, no browser and no page
    read happen here, so a bad address never becomes a card and never opens a
    window."""
    problem = _url_problem(url)
    if problem:
        return problem
    problem = readonly_problem(url)
    if problem:
        return problem
    host = _host_of(url)
    if not any(host == name or host.endswith("." + name) for name in _AMAZON_HOSTS):
        return ("That is not an Amazon product address. This check reads Amazon "
                "product pages, because that is the page Amazon's own review "
                "list is written in; nothing was opened.")
    lowered = str(url).strip().lower()
    if not any(marker in lowered for marker in _AMAZON_ASIN_MARKERS):
        return ("That Amazon address is not one product page - a product page "
                "carries its ASIN in the address (/dp/<ASIN> or "
                "/gp/product/<ASIN>). Nothing was opened.")
    return ""


def _driver_html(driver, url: str) -> str:
    """Call the injected driver. The ONLY shape this seam assumes is one
    callable (or object with `get_html`) taking the listing URL and returning
    a page string; the real session/profile is the caller's business."""
    if driver is None:
        raise CaptureUnavailable(UNAVAILABLE_MESSAGE)
    getter = driver if callable(driver) else getattr(driver, "get_html", None)
    if not callable(getter):
        raise CaptureUnavailable(
            "The supplied browser driver has no callable get_html(url); this "
            "seam does not invent a driver interface the repository does not have.")
    try:
        html = getter(url)
    except (OwnerLoginRequired, ChallengeDetected, CaptureUnavailable):
        raise
    except Exception as exc:  # a driver failure is refused, never guessed at
        raise CaptureUnavailable(DRIVER_FAILED_MESSAGE) from exc
    if not isinstance(html, str) or not html:
        raise CaptureUnavailable(DRIVER_FAILED_MESSAGE)
    return html


def capture_page(url, *, driver=None, source_url=None) -> str:
    """Get one page's HTML from `driver`, then classify and refuse honestly.

    `driver` is the caller's browser-session object or callable; when it is
    absent the capture is refused with `CaptureUnavailable` - this module never
    starts a browser, opens a window or fetches a URL itself. An address that
    is a cart/checkout/order/account/payment/sign-in page is refused by its
    shape before the driver is called at all. A sign-in page raises
    `OwnerLoginRequired`; a challenge raises `ChallengeDetected`; any other
    non-product page raises `CaptureUnavailable`. On success the HTML is
    returned unchanged so `jarvis_product_read.parse_product_page()` can read
    it."""
    problem = _url_problem(url) or readonly_problem(url)
    if problem:
        raise CaptureUnavailable(problem)
    html = _driver_html(driver, url)
    state = classify_page(html, source_url=source_url or url)
    if state == "challenge":
        raise ChallengeDetected(CHALLENGE_MESSAGE)
    if state == "owner_login_required":
        raise OwnerLoginRequired(OWNER_LOGIN_MESSAGE)
    if state == "not_a_product_page":
        raise CaptureUnavailable(NOT_A_PRODUCT_MESSAGE)
    return html


def open_owner_login(driver=None) -> None:
    """The one-time-login seam: the OWNER signs in; Jarvis never sees the
    password. A caller that has a real driver may pass it, and its
    `open_owner_login()` is called - `real_driver()` does, by opening the
    site's sign-in page in the persistent browser window and leaving it there
    for the owner. Without one, this raises `OwnerLoginRequired` with the plain
    instruction - it does not open a browser by itself."""
    if driver is not None:
        opener = getattr(driver, "open_owner_login", None)
        if callable(opener):
            try:
                opener()
            except (OwnerLoginRequired, ChallengeDetected, CaptureUnavailable):
                raise
            except Exception as exc:  # a login failure is reported, not retried
                raise CaptureUnavailable(DRIVER_FAILED_MESSAGE) from exc
            return
    raise OwnerLoginRequired(OWNER_LOGIN_MESSAGE)


class BrowserSessionDriver:
    """The real driver: one page's HTML from Jarvis's own signed-in browser.

    It is injected into `capture_page()` like any other driver (a `get_html`
    callable is the only shape that seam assumes), so nothing else changes and
    every test can pass a fake instead. The browser work is
    `jarvis_browser_control.read_page_html()` - the browser module's own
    public, documented, read-only seam - imported LAZILY the first time a real
    read is asked for, so importing this module never imports Playwright.

    `reader(session, url) -> html` and `opener(url) -> final url` may be
    injected, which is how the wiring suite proves the driver's refusal order
    and its sign-in seam without opening a window. A read-only address is
    refused BEFORE either is called."""

    def __init__(self, session: str = PRODUCT_SESSION, *, reader=None, opener=None):
        self.session = str(session or PRODUCT_SESSION)
        self._reader = reader
        self._opener = opener

    def get_html(self, url) -> str:
        problem = _url_problem(url) or readonly_problem(url)
        if problem:
            raise CaptureUnavailable(problem)
        reader = self._reader
        if reader is None:
            try:
                import jarvis_browser_control as BROWSER
            except Exception as exc:
                raise CaptureUnavailable(BROWSER_UNAVAILABLE_MESSAGE) from exc
            reader = BROWSER.read_page_html
        try:
            html = reader(self.session, url)
        except (OwnerLoginRequired, ChallengeDetected, CaptureUnavailable):
            raise
        except Exception as exc:
            raise CaptureUnavailable(BROWSER_UNAVAILABLE_MESSAGE) from exc
        if not isinstance(html, str) or not html:
            raise CaptureUnavailable(DRIVER_FAILED_MESSAGE)
        return html

    def open_owner_login(self) -> None:
        """Open the site's sign-in page for the OWNER; Jarvis types nothing.

        The page stays on screen in the visible persistent window, so the
        owner signs in once and the next read is signed in. A failure is
        reported as `CaptureUnavailable`; a challenge is never solved."""
        opener = self._opener
        if opener is None:
            try:
                import jarvis_browser_control as BROWSER
            except Exception as exc:
                raise CaptureUnavailable(BROWSER_UNAVAILABLE_MESSAGE) from exc
            opener = BROWSER.open_page_for_owner
        try:
            opener(self.session, SIGNIN_URL)
        except (OwnerLoginRequired, ChallengeDetected, CaptureUnavailable):
            raise
        except Exception as exc:
            raise CaptureUnavailable(BROWSER_UNAVAILABLE_MESSAGE) from exc


def browser_driver(*, session: str = PRODUCT_SESSION, reader=None, opener=None):
    """Build the real driver, optionally with a stand-in reader/opener (the
    tests' injection point). Building one fetches nothing and opens no window:
    the browser is touched only when `get_html()` or `open_owner_login()` is
    actually called."""
    return BrowserSessionDriver(session, reader=reader, opener=opener)


def real_driver(*, session: str = PRODUCT_SESSION, reader=None, opener=None):
    """The real browser-session driver, backed by the repository's own visible
    signed-in browser (`jarvis_browser_control.read_page_html`).

    Nothing is opened or fetched by this call. On the owner's PC the first
    real read opens the persistent visible window, using the profile the
    owner signed in to once; a machine without Playwright gets one plain
    `CaptureUnavailable` naming that instead of a crash. NOT-TESTABLE in CI:
    no window, no network and no Amazon sign-in are exercised by any test."""
    return browser_driver(session=session, reader=reader, opener=opener)
