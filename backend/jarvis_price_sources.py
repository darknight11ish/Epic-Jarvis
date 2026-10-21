"""jarvis_price_sources.py - the multi-source half of the price radar: local
SearXNG price mentions, and the two-persona steering probe. INTERNAL MODULE,
NO ROUTE YET (2026-10-21, F2 scaffold).

WHAT IT IS FOR. The owner approved the anti-surveillance price/flight radar
(2026-10-21; Gemini doc `deepseek_anti_surveillance_price_and_flight_radar_2026_10_21.md`
Slice 2 item 2 / architecture Layer 3). This file is the part that reads
prices from sources that are NOT the merchant's own session:

  1. `query_searxng_prices(query)` asks the SearXNG instance already running
     on this PC (`docker/searxng/`, host address 127.0.0.1:8888 - the docker
     compose binds `127.0.0.1:8888:8080`, so it is loopback-only) for one
     search across its engines, and reads price mentions out of the result
     titles/snippets. It is ONE request; nothing is opened on the merchant's
     site, and no browser profile exists to correlate.
  2. `probe_steering(url)` fetches ONE product page twice, with two DECOUPLED
     request profiles, and compares the prices the store serves:
       * Probe A "comparison shopper": desktop browser profile + a Google
         referer (the visitor a shop believes came from a price-comparison
         search);
       * Probe B "mobile direct": mobile profile, no referer (the visitor
         who typed the address).
     If the two readings differ, the store is price-steering by visitor
     profile. `steering_detected` is True ONLY when BOTH probes produced a
     price from the page's own machine/served markings - never from one
     reading, and never from a guess.

WHY THESE TWO. Layer 1 of that architecture ("never hit the merchant first")
and Layer 3 ("referrer/persona decoupling + dual-persona audit"). This module
does not implement the flight RPC (F1's `jarvis_price_radar.py`), the alert
wording/Today card, a background schedule, proxies, or any new dependency.

BOUNDARIES, said plainly:

  * READ-ONLY PRODUCT PAGES ONLY. `probe_steering` refuses cart, checkout,
    basket, order, payment, sign-in and account URLs BEFORE fetching
    (`_readonly_problem`), so it can never enter a purchase flow.
  * NO COOKIE, NO ETAG, NO CONDITIONAL REQUEST. `_decoupled` strips `Cookie`,
    `ETag`, `If-None-Match`, `If-Modified-Since`, `If-Match` and `If-Range`
    from whatever profile it is handed, and sends `Cache-Control: no-cache`.
    A tracking ETag is a cookie-less supercookie; the project never sends one
    on a price request.
  * PUBLIC TARGETS ONLY for the product probes: the target URL must pass
    `jarvis_local_http.private_fetch_problem` - the SAME guard "Tell me when
    this page changes" already uses - so a product URL can never make this
    PC fetch itself or the home network. The SEARXNG request is the one
    loopback request: its address is validated by `jarvis_search`'s own
    `searxng_url_problem`, and it never leaves this PC.
  * OUTSIDE TEXT. Everything read (titles, snippets, page prices) is other
    people's words. It goes to a caller that treats it as outside text; this
    module never learns it, never logs it, and never stores it. `_latch()`
    sets the project's existing page-watch taint latch (`why="price_radar"`)
    after a successful outside read, exactly as `jarvis_tellme` does for a
    page watch.
  * NO NEW DEPENDENCIES. Standard library, `jarvis_local_http` for the
    network, and `jarvis_search`/`jarvis_tellme` for the pieces they already
    own: the SearXNG address rule, the integer-cents extractor
    (`jarvis_tellme.extract_watch_signals`, `jarvis_tellme.price_of`), the
    page-body cap and the redirect refusal. Nothing here re-implements
    cents parsing - a price read by two different parsers is a bug waiting
    to happen.
  * OFF BY DEFAULT. `[price_radar] enabled` (F1 owns the section; this
    module reads it defensively and treats a missing/unknown section as OFF).
    Both entry points return a plain "switched off" answer and fetch nothing
    when it is off.
  * NO ROUTE, NO APP SURFACE YET. Nothing imports this module in production
    until F1's `jarvis_price_radar.py` wiring; that is why the contract lives
    in this docstring rather than a JARVIS-API route section (Lead-approved
    for this scaffold: there is no user surface to document yet - F1's wiring
    adds the config keys, the alert words and the docs with it). The tests are
    `backend/test_price_sources.py`.

HARD REFUSALS (Ruling 10.3, 2026-10-21 - the owner's accepted contract for
this stack). Every one is enforced here and held by a test:

  * NO CHECKOUT / CART / SEAT-HOLD PATH, and NEVER a write method. The path
    refusal list below refuses cart/basket/bag/checkout/order/payment/
    purchase/account/seat-hold addresses BEFORE a request, and this module
    has no POST or PUT anywhere: the only HTTP verb it can issue is GET
    (`_one_probe` -> `_fetch_default`; the tests hold that with an `ast`
    check, not a source-text pin).
  * NO AUTHENTICATED / LOGIN-WALLED SCRAPING. `_decoupled` strips `Cookie`,
    `Authorization`, `Proxy-Authorization`, `ETag` and every conditional
    (If-*) header from whatever profile it is handed, so a price check can
    never carry a session, a token or a vault credential. This module does
    not import the vault or the token store at all.
  * NO CAPTCHA SOLVING, NO RETRY LOOPS. A 403, 429 or a challenge page is
    `stale: True, reason: "blocked_by_site_challenge"` and the probe STOPS
    (the second probe is not even sent after the first is challenged); there
    is no retry, no backoff loop, no solving attempt. F1's history keeps the
    last-known-good price and shows `stale` rather than inventing one.
  * STRICT SSRF. The ONE allowed loopback request is the local SearXNG
    (127.0.0.1:8888, owner's own program, its own validator); every product
    target must pass `jarvis_local_http.private_fetch_problem` - which
    refuses this PC, private LAN, link-local (169.254/16, fe80::/10),
    Tailscale/NordVPN CGNAT (100.64/10), NAT64-wrapped private addresses and
    the reserved ranges - and the actual fetch uses the project's
    `public_opener`, whose per-connection check also covers REDIRECTS, plus
    `jarvis_tellme`'s redirect refusal (no redirect is followed at all).
  * NO PROXY LIST. This module sends every request directly (the loopback
    SearXNG through the project's proxy-less opener, product pages through
    `public_opener`, which never uses a proxy). An owner-configured proxy is
    a LATER, explicitly-switched slice; nothing here reads a public proxy
    list, and there is no proxy setting to misconfigure.
  * POLL FLOOR. This module has no scheduler: `POLL_MIN_SECONDS` (300 s) and
    `POLL_JITTER` (±30%) are mirrored here for F1/whoever schedules a check,
    and `next_poll_seconds()` DELEGATES to Slice 1's jittered scheduler
    (`jarvis_tellme.next_poll_timestamp`) rather than inventing a cadence of
    its own - absent that, it says so and returns None.

THE HEADER CONTRACT. The decoupled profile table itself is Slice 1's
(`jarvis_tellme.build_decoupled_headers`); this module never carries a second
copy of a browser profile. Both entry points take the profile provider as an
argument (`headers_for`) so tests need no import of that module and this file
has NO import-time dependency on the Slice 1 PR. When it is not supplied, the
default resolves that function lazily; if the install does not have it yet,
the honest "needs the page-watch update" sentence is returned and nothing is
fetched.
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from typing import Callable, Optional

#: The address the shipped `docker/searxng/docker-compose.yml` publishes this
#: PC only: `127.0.0.1:8888` on the host -> the image's own 8080. Kept equal to
#: `jarvis_search.DEFAULT_SEARXNG_URL` by the tests - the Gemini document that
#: proposed this feature said 8080, which is the CONTAINER's port, not the
#: address anything on this PC dials.
DEFAULT_SEARXNG_URL = "http://127.0.0.1:8888"

#: The two faces compared. These are OUR words for the two request profiles,
#: never a browser brand: what a page may not know is that one person asked.
PERSONA_COMPARISON = "comparison_shopper"
PERSONA_MOBILE = "mobile_direct"
PERSONAS = (PERSONA_COMPARISON, PERSONA_MOBILE)

#: Slice 1's profile table order (its own `_HEADER_PROFILES`: 0 Windows
#: Chrome, 1 Windows Edge, 2 macOS Safari, 3 macOS Chrome, 4 Windows Firefox,
#: 5 iOS Safari, 6 Android Chrome): the two indexes this module asks for. Only
#: used by the default provider when Slice 1 (#702) has landed; a tree without
#: it returns the honest "not available yet" answer instead.
PERSONA_INDEX = {PERSONA_COMPARISON: 0, PERSONA_MOBILE: 5}

#: One search, and at most this many results read.
MAX_RESULTS = 8
MAX_QUERY_CHARS = 300
#: Bounds, not promises: one SearXNG answer and one product page.
SEARXNG_TIMEOUT = 5.0
PRODUCT_TIMEOUT = 10.0
SEARXNG_MAX_BYTES = 1_000_000
PRODUCT_MAX_BYTES = 2_000_000

#: Query parameters that exist to carry a visitor's identity, not a product's.
#: A URL differing only by these is the SAME page for the purposes of one
#: comparison (Slice 1's canonicaliser is the full answer; this is the list
#: this module must have even before that lands, stated once).
TRACKING_PARAMS = (
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "gclid", "gbraid", "wbraid", "fbclid", "msclkid", "twclid",
    "igshid", "_ga", "_gl", "mc_eid", "mc_cid", "ref", "ref_", "referrer",
    "tag", "ascsubtag", "psc", "pf_rd_m", "pf_rd_s", "pf_rd_r", "pf_rd_t",
    "pf_rd_p", "pd_rd_r", "pd_rd_w", "pd_rd_wg", "spm", "affid", "aff_id",
)

#: The paths that mean "this is a purchase/account flow, not a product page".
#: `seat`/`seats`/`seat-hold` are the airline seat-hold flow Ruling 10.3
#: forbids outright; nothing here may ever enter one.
_READONLY_BAD = re.compile(
    r"(?:^|/)(?:cart|basket|bag|checkout|check-?out|payment|pay|order|orders|"
    r"purchase|buy|signin|sign-in|login|log-in|account|my-?account|wishlist|"
    r"gift-?card|redeem|seat(?:s|-?select|-?hold)?)(?:[/?#.]|$)", re.IGNORECASE)

#: The decoupled-header keys this module removes unconditionally. Compared
#: lower-cased, so a profile that spells them differently cannot slip through.
#: `referer`/`origin` are here too: a profile may not smuggle a third-party
#: referral through; probe A sets the ONE google referer it is supposed to
#: send, probe B sends none. `authorization`/`proxy-authorization` are the
#: authenticated-scraping refusal (Ruling 10.3): no session, token or vault
#: credential may travel on a price read.
_DECOUPLING_STRIP = ("cookie", "cookie2", "etag", "if-none-match",
                     "if-modified-since", "if-match", "if-range", "if-unmodified-since",
                     "referer", "referrer", "origin",
                     "authorization", "proxy-authorization")

#: The reason a site challenge is reported with (Ruling 10.3's fixed word),
#: never a retry loop and never a solve attempt.
BLOCKED_BY_SITE_CHALLENGE = "blocked_by_site_challenge"

#: Hard poll floor and jitter, mirrored for F1/whoever schedules a check.
#: This module has no scheduler of its own; `next_poll_seconds()` delegates
#: to Slice 1's jittered scheduler, so the cadence has ONE owner.
POLL_MIN_SECONDS = 300
POLL_JITTER = 0.30

#: The disclosure wording Ruling 10.3 fixes, word for word. F1 renders them;
#: this module supplies them so there is ONE copy of each sentence.
DISCLOSURE_NEW_VISITOR = "Checked as a new visitor (no cookies or account used)."
STEERING_ROW = ("This store showed two different prices at the same time: "
                "${a:.2f} (Desktop · via search referral) vs. "
                "${b:.2f} (Mobile · direct).")
PROXY_TAG = "Checked via configured proxy ({exit_label})."

_LATCH_WHY = "price_radar"

#: Plain sentences (the caller shows these; they carry no page words).
OFF_WORDS = ("The price radar is switched off, so nothing was looked up. Turn it on "
             "on the PC first.")
NO_SEARXNG_WORDS = ("SearXNG isn't answering on this PC at 127.0.0.1:8888, so no prices "
                    "were looked up. Nothing was sent to another provider.")
JSON_OFF_WORDS = ("SearXNG is running but its JSON output is switched off (it answered 403), "
                  "so no prices were read - backend/README.md, \"Web search\", has the fix.")
UNREADABLE_WORDS = ("SearXNG answered, but the answer could not be read as search results, so "
                    "no prices were read.")
NO_PROFILES_WORDS = ("This PC's Jarvis does not have the decoupled request profiles yet "
                     "(the page-watch update), so the two views were not compared and "
                     "nothing was fetched.")
NOT_PUBLIC_WORDS = "That address is this PC or a private network address, so it was not fetched."
NOT_PRODUCT_WORDS = ("That address is a cart, checkout, order or account page, so it was not "
                     "fetched - the steering check reads product pages only.")
NO_A_PRICE_WORDS = ("The comparison-shopper view did not show a price this PC could read, so "
                    "nothing was compared.")
NO_B_PRICE_WORDS = ("The mobile view did not show a price this PC could read, so nothing was "
                    "compared.")
SAME_WORDS = "Both views showed the same price, so no price steering was seen."
LOWER_WORDS = "The {lower} view showed the lower price."
CHALLENGE_WORDS = ("The site refused this check with a bot challenge (or a 403/429), so no "
                   "price comparison was made. Jarvis does not solve challenges and did not "
                   "retry; the last known price stays marked stale.")
CHALLENGE_RATE_WORDS = ("SearXNG refused this check (its rate limiter answered 429), so no "
                        "prices were read. No retry was made - wait a minute or turn its "
                        "limiter off in settings.yml.")


# --------------------------------------------------------------------------
#   Settings (defensive: F1 owns the [price_radar] section)
# --------------------------------------------------------------------------

def _framework():
    """The backend framework module, or None - the same optional-import shape
    every shipped module in this backend uses. Never raises."""
    try:
        import jarvis_framework as fw
    except Exception:
        return None
    return fw


def _price_cfg() -> dict:
    """`[price_radar]` as a dict, or {} when the section/file is missing.

    `enabled` defaults to False and a damaged value counts as False (the
    switch is off until the owner turns it on - the same default-on-failure
    rule every optional feature in this backend follows)."""
    fw = _framework()
    if fw is None:
        return {}
    try:
        section = fw.load_framework().get("price_radar")
    except Exception:
        return {}
    return dict(section) if isinstance(section, dict) else {}


def _as_bool(value, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return default


def enabled(cfg: Optional[dict] = None) -> bool:
    """Is the price radar switched on? OFF unless the owner's settings say so."""
    return _as_bool((cfg if cfg is not None else _price_cfg()).get("enabled"), False)


def searxng_url(cfg: Optional[dict] = None) -> str:
    """The SearXNG address to dial: `[price_radar] searxng_url` when it is a
    valid local address, else the shipped default. `jarvis_search`'s own
    validator decides - this module does not carry a second address rule."""
    section = cfg if cfg is not None else _price_cfg()
    url = section.get("searxng_url") if isinstance(section, dict) else None
    url = url.strip().rstrip("/") if isinstance(url, str) else ""
    if not url:
        return DEFAULT_SEARXNG_URL
    try:
        import jarvis_search as S
        bad = S.searxng_url_problem(url)
    except Exception:
        bad = ""
    return DEFAULT_SEARXNG_URL if bad else url


# --------------------------------------------------------------------------
#   Small shared helpers
# --------------------------------------------------------------------------

def _latch() -> bool:
    """Set the project's page-watch taint latch for an outside read, exactly as
    `jarvis_tellme` does for a page watch. Never raises; returns whether it
    took (a test asserts it is called, not that it is fatal)."""
    try:
        import jarvis_gate
        return bool(jarvis_gate.latch_taint(why=_LATCH_WHY))
    except Exception:
        return False


def _cents(price) -> Optional[int]:
    """An integer whole-cent value from a price `jarvis_tellme` read, or None.

    tellme's own extractor already produces integer cents for page words
    (`extract_watch_signals()["prices_cents"]`); `price_of()` returns the
    number as people write it, so it is rounded to cents HERE with the same
    `int(round(value * 100))` rule tellme uses, never a float kept as one."""
    try:
        value = float(price)
    except (TypeError, ValueError):
        return None
    if not (0 < value < 1_000_000_000):
        return None
    cents = int(round(value * 100))
    return cents if cents > 0 else None


def _price_of(body: bytes, content_type: str = "") -> Optional[int]:
    """The page's own price in integer cents through tellme's extractor, or
    None. `jarvis_tellme.price_of` prefers the machine-marked price
    (schema.org JSON-LD, then a price meta tag) and falls back to the first
    visible one - the project's existing definition of "the price this page
    serves", not a second parser."""
    try:
        import jarvis_tellme as T
        price = T.price_of(body, content_type)
    except Exception:
        return None
    return _cents(price)


def _snippet_cents(text: str) -> list:
    """Every integer-cent amount in a chunk of page words, through tellme's
    SAME extractor (`extract_watch_signals`), keeping order and duplicates."""
    if not text:
        return []
    try:
        import jarvis_tellme as T
        got = T.extract_watch_signals(str(text))
    except Exception:
        return []
    return [int(c) for c in (got.get("prices_cents") or []) if isinstance(c, int)]


def _decode(body: bytes, content_type: str = "") -> str:
    """The body's text, decoded the way tellme decodes a page (charset from
    the Content-Type, UTF-8 otherwise, replacement on bad bytes)."""
    try:
        import jarvis_tellme as T
        return T._decode_body(body, content_type)
    except Exception:
        return body.decode("utf-8", "replace")


#: What a bot challenge looks like in the first part of a page, after a
#: 403/429/503 or behind a 200. Only markers a real challenge page carries -
#: never a word as loose as "blocked".
_CHALLENGE_MARKERS = ("captcha", "cf-chl", "cf-challenge", "challenge-platform",
                      "just a moment", "checking your browser", "unusual traffic",
                      "enable javascript and cookies", "attention required")


def _is_challenge(status, body) -> bool:
    """Is this answer a site challenge (Ruling 10.3: stop, mark stale, no
    retry) rather than a normal page? A 403/429/503 IS one by status; a 200
    is one only when the page carries a challenge marker in its first words."""
    try:
        code = int(status)
    except (TypeError, ValueError):
        code = 0
    if code in (403, 429, 503):
        return True
    if not isinstance(body, (bytes, bytearray)) or not body:
        return False
    head = _decode(bytes(body[:64_000])).casefold()
    return any(marker in head for marker in _CHALLENGE_MARKERS)


def proxy_tag(exit_label) -> str:
    """The proxy tag Ruling 10.3 fixes, with the configured exit's label.
    This module does not proxy anything yet - this is the ONE copy of the
    sentence a later owner-configured proxy slice renders."""
    label = str(exit_label or "").strip() or "unnamed exit"
    return PROXY_TAG.format(exit_label=label)


def next_poll_seconds(base_interval_s, rng=None):
    """When the next check is due, from Slice 1's jittered scheduler
    (`jarvis_tellme.next_poll_timestamp`: >= POLL_MIN_SECONDS, +/-30%), or
    None when this install has no such scheduler yet - this module must not
    invent a cadence of its own (POLL_MIN_SECONDS/POLL_JITTER mirror the
    contract; the ONE implementation is Slice 1's)."""
    try:
        import jarvis_tellme as T
        fn = getattr(T, "next_poll_timestamp", None)
        if not callable(fn):
            return None
        return fn(base_interval_s, rng=rng)
    except Exception:
        return None


def _canonical_key(url: str) -> str:
    """host + identity-only URL, lower-cased: two results that differ only by
    tracking parameters are the same page and count once. Uses
    `jarvis_tellme.canonicalize_watch_url` when that (Slice 1) function is
    present; otherwise the local rule above is applied - one statement of the
    parameter list, so a result cannot count twice either way."""
    raw = str(url or "").strip()
    canonical = raw
    try:
        import jarvis_tellme as T
        fn = getattr(T, "canonicalize_watch_url", None)
        if callable(fn):
            canonical = str(fn(raw) or raw)
    except Exception:
        canonical = raw
    try:
        parts = urllib.parse.urlsplit(canonical)
    except ValueError:
        return raw.lower()
    host = (parts.hostname or "").lower()
    pairs = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    kept = [(k, v) for k, v in pairs if k.lower() not in TRACKING_PARAMS]
    query = urllib.parse.urlencode(sorted(kept))
    path = parts.path.rstrip("/") or "/"
    return f"{host}{path}" + (f"?{query}" if query else "")


def _result_url(raw) -> str:
    url = str(raw or "").strip()
    return url if url.lower().startswith(("http://", "https://")) else ""


def _decoupled(headers: Optional[dict], *, referer: str = "") -> dict:
    """The request headers for one probe: the profile's headers with every
    tracking/conditional key removed, `Cache-Control: no-cache` added, and
    the referer set only when one is asked for (B: none at all)."""
    out = {}
    for key, value in dict(headers or {}).items():
        if str(key).lower() in _DECOUPLING_STRIP:
            continue
        out[str(key)] = str(value)
    out["Cache-Control"] = "no-cache"
    if referer:
        out["Referer"] = referer
    return out


def _readonly_problem(url: str) -> str:
    """"" when `url` is a product page this module may read, else the plain
    reason. A cart/checkout/order/account address is refused before any
    request, so the steering check can never enter a purchase flow."""
    try:
        parts = urllib.parse.urlsplit(str(url or ""))
    except ValueError:
        return "That address could not be read."
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        return "That address must be a product page starting with http:// or https://."
    if _READONLY_BAD.search(parts.path or ""):
        return NOT_PRODUCT_WORDS
    return ""


def _default_headers_for(persona: str) -> Optional[dict]:
    """The default decoupled profile provider: Slice 1's table, lazily. None
    when this install does not have it yet (nothing is then fetched).

    Slice 1 (#702) is `build_decoupled_headers(persona_index=None,
    referer_mode="")`; the comparison-shopper probe asks it for the search
    referer itself (`"search_comparison"`) so the referer comes from ONE
    place, and `_decoupled` still strips/re-adds what this module needs.
    A build that only takes `persona_index` is used without the referer
    argument (probe A then gets the one google referer `_decoupled` adds)."""
    index = PERSONA_INDEX.get(persona)
    if index is None:
        return None
    try:
        import jarvis_tellme as T
    except Exception:
        return None
    fn = getattr(T, "build_decoupled_headers", None)
    if not callable(fn):
        return None
    mode = "search_comparison" if persona == PERSONA_COMPARISON else ""
    try:
        return dict(fn(persona_index=index, referer_mode=mode))
    except TypeError:
        try:
            return dict(fn(persona_index=index))
        except Exception:
            return None
    except Exception:
        return None


def _fetch_default(url: str, headers: dict) -> tuple:
    """(status, body, content-type) for ONE product-page GET: the project's
    public opener (proxy-aware for https only through `public_opener`), a
    refusal to follow redirects, and the page cap. The URL has already passed
    `private_fetch_problem` before this is called."""
    import jarvis_local_http as LH
    try:
        import jarvis_tellme as T
        redirect = T._PageRedirect()
    except Exception:
        redirect = None
    opener = LH.public_opener(redirect) if redirect is not None else LH.public_opener()
    req = urllib.request.Request(url, headers=dict(headers or {}), method="GET")
    with opener.open(req, timeout=PRODUCT_TIMEOUT) as resp:
        body = resp.read(PRODUCT_MAX_BYTES + 1)
        content_type = resp.headers.get("Content-Type", "") if resp.headers else ""
        return int(getattr(resp, "status", 200) or 200), body[:PRODUCT_MAX_BYTES], content_type


def _fetch_searxng(url: str) -> tuple:
    """(status, body) for the ONE local SearXNG request - loopback, no proxy,
    through `jarvis_local_http` (the same transport `jarvis_search` uses)."""
    import jarvis_local_http as LH
    req = urllib.request.Request(url, headers={"Accept": "application/json",
                                               "User-Agent": "jarvis-price-radar"})
    with LH.urlopen(req, SEARXNG_TIMEOUT) as resp:
        return int(getattr(resp, "status", 200) or 200), resp.read(SEARXNG_MAX_BYTES + 1)


# --------------------------------------------------------------------------
#   1. Local SearXNG: price mentions across its engines
# --------------------------------------------------------------------------

def query_searxng_prices(query, *, categories=("general", "shopping"),
                         fetch: Optional[Callable] = None,
                         cfg: Optional[dict] = None) -> dict:
    """One local SearXNG search, with every price mention it carries.

    Returns a dict:
      {"ok": True, "query", "categories", "results": [
          {"title", "url", "host", "prices_cents", "min_cents",
           "footer"} ...],
       "count", "stale": False, "reason": "", "footer", "words"}
    or {"ok": False, "why": "disabled"|"unavailable"|"json_off"|"unreadable"|
                            "no_results", "stale", "reason", "footer", "words"}
    - a plain sentence and NO result words for every failure. `stale` is True
    only for Ruling 10.3's "blocked_by_site_challenge" stop (403/429 from a
    target site); `reason` is the fixed code the caller/audit uses. Every
    result carries the fixed per-result disclosure footer. No model, no
    merchant request, nothing stored; a successful read sets the page-watch
    taint latch. `fetch` is injectable so tests need no socket.
    """
    section = cfg if cfg is not None else _price_cfg()
    if isinstance(section, dict) and not _as_bool(section.get("enabled"), False):
        return {"ok": False, "why": "disabled", "stale": False, "reason": "disabled",
                "footer": DISCLOSURE_NEW_VISITOR, "words": OFF_WORDS}
    q = str(query or "").strip()
    if not q or len(q) > MAX_QUERY_CHARS:
        return {"ok": False, "why": "unreadable", "stale": False, "reason": "unreadable",
                "footer": DISCLOSURE_NEW_VISITOR,
                "words": "That search needs between 1 and "
                         f"{MAX_QUERY_CHARS} characters."}
    base = searxng_url(section if isinstance(section, dict) else None)
    params = {"q": q, "format": "json"}
    cats = [str(c) for c in (categories or ()) if c]
    if cats:
        params["categories"] = ",".join(cats)
    url = f"{base}/search?{urllib.parse.urlencode(params)}"
    fetcher = fetch or _fetch_searxng
    try:
        status, body = fetcher(url)
    except Exception:
        return {"ok": False, "why": "unavailable", "stale": False, "reason": "unavailable",
                "footer": DISCLOSURE_NEW_VISITOR, "words": NO_SEARXNG_WORDS}
    if status == 403:
        return {"ok": False, "why": "json_off", "stale": False, "reason": "json_off",
                "footer": DISCLOSURE_NEW_VISITOR, "words": JSON_OFF_WORDS}
    if status == 429:
        # Ruling 10.3: a challenge/limiter stops the check, marks stale, and
        # never retries. SearXNG's own limiter is the local case of it.
        return {"ok": False, "why": "blocked_by_site_challenge", "stale": True,
                "reason": BLOCKED_BY_SITE_CHALLENGE,
                "footer": DISCLOSURE_NEW_VISITOR, "words": CHALLENGE_RATE_WORDS}
    if status != 200:
        return {"ok": False, "why": "unavailable", "stale": False, "reason": "unavailable",
                "footer": DISCLOSURE_NEW_VISITOR, "words": NO_SEARXNG_WORDS}
    if len(body) > SEARXNG_MAX_BYTES:
        return {"ok": False, "why": "unreadable", "stale": False, "reason": "unreadable",
                "footer": DISCLOSURE_NEW_VISITOR, "words": UNREADABLE_WORDS}
    try:
        doc = json.loads(body.decode("utf-8", "replace"))
    except ValueError:
        return {"ok": False, "why": "unreadable", "stale": False, "reason": "unreadable",
                "footer": DISCLOSURE_NEW_VISITOR, "words": UNREADABLE_WORDS}
    if not isinstance(doc, dict) or not isinstance(doc.get("results"), list):
        return {"ok": False, "why": "unreadable", "stale": False, "reason": "unreadable",
                "footer": DISCLOSURE_NEW_VISITOR, "words": UNREADABLE_WORDS}

    results, seen = [], set()
    for row in doc["results"]:
        if not isinstance(row, dict):
            continue
        link = _result_url(row.get("url"))
        if not link:
            continue
        key = _canonical_key(link)
        if key in seen:
            continue
        seen.add(key)
        title = str(row.get("title") or "").strip()
        snippet = str(row.get("content") or row.get("snippet") or "").strip()
        prices = _snippet_cents(f"{title} {snippet}")
        host = ""
        try:
            host = (urllib.parse.urlsplit(link).hostname or "").lower()
        except ValueError:
            host = ""
        results.append({"title": title[:300], "url": link[:500], "host": host,
                        "prices_cents": prices,
                        "min_cents": min(prices) if prices else None,
                        "footer": DISCLOSURE_NEW_VISITOR})
        if len(results) >= MAX_RESULTS:
            break
    if not results:
        return {"ok": True, "query": q, "categories": cats, "results": [],
                "count": 0, "stale": False, "reason": "",
                "footer": DISCLOSURE_NEW_VISITOR,
                "words": ("SearXNG answered but returned no usable results, so no prices "
                          "were read. This is usually the container's own engines failing "
                          "- backend/README.md, \"Web search\", step 3a, has the checks.")}
    _latch()
    priced = [r for r in results if r["min_cents"] is not None]
    words = (f"{len(results)} result{'s' if len(results) != 1 else ''} from SearXNG, "
             f"{len(priced)} with a price shown. These are other people's words - "
             f"outside text, not something Jarvis learned.")
    return {"ok": True, "query": q, "categories": cats, "results": results,
            "count": len(results), "stale": False, "reason": "",
            "footer": DISCLOSURE_NEW_VISITOR, "words": words}


# --------------------------------------------------------------------------
#   2. The dual-persona steering probe
# --------------------------------------------------------------------------

def _probe_result(ok, why, url, words, *, stale=False, **kw) -> dict:
    """One probe answer in the fixed contract shape. `reason` is a fixed code
    (Ruling 10.3's `blocked_by_site_challenge` included), never a page word."""
    out = {"ok": bool(ok), "why": str(why), "url": url, "words": words,
           "stale": bool(stale),
           "reason": BLOCKED_BY_SITE_CHALLENGE if stale else str(why or ""),
           "footer": DISCLOSURE_NEW_VISITOR, "steering_row": "",
           "price_a_cents": None, "price_b_cents": None,
           "steering_delta_cents": None, "which_persona_lower": "",
           "steering_detected": False, "probes": []}
    out.update(kw)
    return out


def _one_probe(url: str, headers: dict, fetch: Callable) -> dict:
    """One GET of `url` with `headers`, decoded to a page price. Never raises;
    the dict says what happened in plain fields. A challenge answer (403/429/
    a challenge page) is reported as such - the caller stops there, because
    Ruling 10.3 forbids solving it or retrying."""
    try:
        status, body, content_type = fetch(url, dict(headers))
    except Exception:
        return {"ok": False, "status": 0, "price_cents": None,
                "why": "fetch_failed", "challenged": False}
    if _is_challenge(status, body):
        return {"ok": False, "status": status, "price_cents": None,
                "why": BLOCKED_BY_SITE_CHALLENGE, "challenged": True}
    if status != 200:
        return {"ok": False, "status": status, "price_cents": None,
                "why": "status", "challenged": False}
    if not isinstance(body, (bytes, bytearray)):
        return {"ok": False, "status": status, "price_cents": None,
                "why": "unreadable", "challenged": False}
    cents = _price_of(bytes(body[:PRODUCT_MAX_BYTES]), str(content_type or ""))
    if cents is None:
        return {"ok": False, "status": status, "price_cents": None,
                "why": "no_price", "challenged": False}
    _latch()
    return {"ok": True, "status": status, "price_cents": cents,
            "why": "", "challenged": False}


def probe_steering(url, *, headers_for: Optional[Callable] = None,
                   fetch: Optional[Callable] = None,
                   cfg: Optional[dict] = None) -> dict:
    """Read ONE product page as two different visitors and compare the prices.

    Returns the fixed contract shape:
      {"ok", "why", "url", "words", "stale", "reason",
       "footer" (Ruling 10.3's per-result disclosure, word for word),
       "steering_row" (Ruling 10.3's sentence, ONLY when steering is detected),
       "price_a_cents", "price_b_cents", "steering_delta_cents",
       "which_persona_lower", "steering_detected",
       "probes": [{"persona", "ok", "status", "price_cents", "why"} ...]}

    `steering_detected` is True ONLY when both probes produced a price this
    PC could read from the page (`price_of`) AND the two differ. One reading,
    a failed probe, or a page with no readable price can never produce it.
    `price_a_cents` is the comparison-shopper view; `price_b_cents` the mobile
    direct view; `steering_delta_cents` is a - b (negative means the
    comparison-shopper view was CHEAPER, i.e. the store showed the other
    visitor a higher price).

    A 403, 429 or challenge page STOPS the check (Ruling 10.3): the result is
    `stale: True, reason: "blocked_by_site_challenge"`, the second probe is
    not sent after the first is challenged, and there is no retry.

    `headers_for(persona)` is injectable (tests, and Slice 1's table); when it
    is not given, Slice 1's `jarvis_tellme.build_decoupled_headers` is tried
    and the honest "not available yet" answer is returned when absent.
    `fetch(url, headers)` is injectable for the same reason - tests never open
    a socket. `cfg` lets a caller pass the switch state it already read.
    """
    section = cfg if cfg is not None else _price_cfg()
    target = str(url or "").strip()
    if isinstance(section, dict) and not _as_bool(section.get("enabled"), False):
        return _probe_result(False, "disabled", target, OFF_WORDS)
    bad = _readonly_problem(target)
    if bad:
        return _probe_result(False, "not_product", target, bad)
    try:
        import jarvis_local_http as LH
        not_public = LH.private_fetch_problem(target)
    except Exception:
        not_public = ""
    if not_public:
        return _probe_result(False, "not_public", target,
                             NOT_PUBLIC_WORDS + " " + not_public)
    provider = headers_for or _default_headers_for
    raw_a = provider(PERSONA_COMPARISON)
    raw_b = provider(PERSONA_MOBILE)
    if raw_a is None or raw_b is None:
        return _probe_result(False, "no_profiles", target, NO_PROFILES_WORDS)
    # The SAME canonical url for both, so the only difference is the visitor.
    canonical = target
    try:
        import jarvis_tellme as T
        fn = getattr(T, "canonicalize_watch_url", None)
        if callable(fn):
            canonical = str(fn(target) or target)
    except Exception:
        canonical = target
    headers_a = _decoupled(raw_a, referer="https://www.google.com/")
    headers_b = _decoupled(raw_b, referer="")
    getter = fetch or _fetch_default
    probe_a = _one_probe(canonical, headers_a, getter)
    if probe_a.get("challenged"):
        return _probe_result(False, BLOCKED_BY_SITE_CHALLENGE, canonical,
                             CHALLENGE_WORDS, stale=True,
                             probes=[dict(probe_a, persona=PERSONA_COMPARISON)])
    probe_b = _one_probe(canonical, headers_b, getter)
    probes = [dict(probe_a, persona=PERSONA_COMPARISON),
              dict(probe_b, persona=PERSONA_MOBILE)]
    if probe_b.get("challenged"):
        return _probe_result(False, BLOCKED_BY_SITE_CHALLENGE, canonical,
                             CHALLENGE_WORDS, stale=True, probes=probes,
                             price_a_cents=probe_a.get("price_cents"))
    a, b = probe_a.get("price_cents"), probe_b.get("price_cents")
    if a is None and b is None:
        return _probe_result(False, "no_price", canonical, NO_A_PRICE_WORDS, probes=probes)
    if a is None:
        return _probe_result(False, "no_price_a", canonical, NO_A_PRICE_WORDS, probes=probes)
    if b is None:
        return _probe_result(False, "no_price_b", canonical, NO_B_PRICE_WORDS,
                             probes=probes, price_a_cents=a)
    delta = a - b
    if delta == 0:
        return _probe_result(True, "", canonical, SAME_WORDS, probes=probes,
                             price_a_cents=a, price_b_cents=b,
                             steering_delta_cents=0)
    lower = PERSONA_COMPARISON if delta < 0 else PERSONA_MOBILE
    row = STEERING_ROW.format(a=a / 100.0, b=b / 100.0)
    words = (f"Two readings of the same page: the comparison-shopper view showed "
             f"{a / 100:.2f} and the mobile view showed {b / 100:.2f} - they "
             f"differ, so this store appears to steer prices by visitor "
             f"profile. " + LOWER_WORDS.format(
                 lower="comparison-shopper" if lower == PERSONA_COMPARISON else "mobile"))
    return _probe_result(True, "", canonical, words, probes=probes,
                         price_a_cents=a, price_b_cents=b,
                         steering_delta_cents=delta,
                         which_persona_lower=lower,
                         steering_detected=True, steering_row=row)
