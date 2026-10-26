"""jarvis_product_capture.py - the SEAM for reading one Amazon product page
from Jarvis's own browser session, and the honest refusal when it cannot.

WHAT THIS MODULE IS, AND WHAT IT IS NOT
The product check already has its read half (`jarvis_product_read.py`: one
page's HTML -> listing facts + review records + warnings) and its engine
(`jarvis_product_research.py`: records -> reasons report). This module is the
small piece between the browser and that read half: it names the capture, it
classifies the page it was given, and it says refusal in words instead of
pretending.

IT IS NOT WIRED TO THE LIVE BROWSER YET, ON PURPOSE. The repository's browser
automation is `jarvis_browser_control.py` (visible Playwright Chromium, one page
per named session) and `jarvis_browser_engine.py` (which engine to use). Neither
exposes a public "give me this URL's HTML" call: the readable page HTML is
produced inside `jarvis_browser_control._page_for()` with a private
`page.evaluate(_MAIN_CONTENT_JS, ...)`, and that module's default is a VISIBLE
window. `jarvis_browser_engine.wants_a_person()` is a pure classifier, not a
reader. So this slice does NOT open a browser, does NOT invent a driver
interface the repo does not have, and does NOT fetch anything: a caller that has
a real driver must inject it. `real_driver()` says that plainly.

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
`open_owner_login()` is the one-time-login seam: it raises
`OwnerLoginRequired` with the plain instruction, unless a driver supplies the
flow.

WHAT IS NOT TESTED HERE, PLAINLY
No real Amazon page, no real browser session, no one-time login has been
exercised: this module's tests use fixture HTML only and never open a window or
make a network call. The real driver, the persistent browser profile and the
owner's login are NOT-TESTABLE in this development container.

Standard library only plus the project's own read module: `re`,
`jarvis_product_read`. No network, no browser import, no subprocess, no file is
read or written, and nothing here logs.

    py -3 -B backend/test_product_capture.py
"""
from __future__ import annotations

import re

import jarvis_product_read as READ

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

_TAG = re.compile(r"<[^>]+>", re.S)


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
    starts a browser, opens a window or fetches a URL itself. A sign-in page
    raises `OwnerLoginRequired`; a challenge raises `ChallengeDetected`; any
    other non-product page raises `CaptureUnavailable`. On success the HTML is
    returned unchanged so `jarvis_product_read.parse_product_page()` can read
    it."""
    problem = _url_problem(url)
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
    password. A caller that has a real login driver may pass it, and its
    `open_owner_login()` is called. Without one, this raises
    `OwnerLoginRequired` with the plain instruction - it does not open a
    browser by itself."""
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


def real_driver() -> None:
    """The real browser-session driver does not exist as an importable HTML
    reader yet; say so instead of pretending. This is the point the later
    wiring slice fills, after the owner has signed in once in Jarvis's own
    browser profile. NOT-TESTABLE here: no window, no network, no profile."""
    raise CaptureUnavailable(
        "The real browser-session capture driver is not built yet. The "
        "repository's browser automation can classify pages "
        "(jarvis_browser_engine.wants_a_person) and drive an approved visible "
        "session, but it exposes no public URL-to-HTML reader, so this slice "
        "does not open a window or fetch anything. Pass your own driver to "
        "capture_page() to wire the later slice.")
