"""jarvis_price_radar.py - the flight half of the price radar: READ-ONLY, OFF.

F1 of the anti-surveillance price/flight radar (owner-approved 2026-10-21).
This module is the **flight engine and the price history store**, and nothing
else:

  * a pure-stdlib builder for Google Flights' ``tfs`` protobuf query
    parameter, adapted from the MIT-licensed `punitarani/fli` (the Python
    reference) and `AWeirdDev/flights` (``fast-flights``) projects - see
    ATTRIBUTION below for the exact files and lines;
  * one tolerant parser for the public search page's inlined result payload;
  * a SQLite price history store with target prices, a last-known-good
    snapshot, stale-on-failure semantics and an outside-text diff;
  * a feature switch that is **off by default** (``[price_radar] enabled =
    false``, in both shipped ``jarvis-framework.toml`` copies).

WHAT IT NEVER DOES. It never books, holds a seat, adds to a cart, starts a
checkout, or touches a PNR/booking endpoint - there is no such code path in
this module at all, only ONE read-only GET of a public search page. It never
logs in, never sends cookies, saved logins or tracking tags, never retries a
blocked request, and never follows a redirect. The endpoint is **unofficial**:
it is Google's public search page, not a published API, and it can change or
break at any time. **"Flight radar" is not a booking tool.**

WHY THE PUBLIC PAGE, NOT THE RPC. Since 2026-08 Google's
``FlightsFrontendService`` RPCs need an ``x-goog-batchexecute-bgr`` header
bound to the exact request bytes, which only the page's own JavaScript can
produce (``punitarani/fli`` documents this in ``fli/search/_tfs.py``). The
public ``/travel/flights`` page is not gated that way: it serves the same rows
inside an ``AF_initDataCallback`` blob keyed ``ds:1``. This module builds the
page's ``tfs`` parameter and reads that blob.

THE SWITCH, AND WHAT "OFF" MEANS. ``[price_radar] enabled`` is read fresh,
defaults to **false**, and with it off every check answers without building a
request or opening a socket (the suite spies on the opener and proves it).
Turning it on is one ``change_own_config`` approval card; turning it off is
immediate (it only takes something away). No scheduled checks run until the
owner turns it on.

THE HARD REFUSAL INVARIANTS (baked in, each tested):

  1. no checkout/cart-add/seat-hold/PNR endpoints - only the single
     read-only search-page GET exists; there is no POST/PUT anywhere;
  2. no authenticated or login-walled scraping - the request carries no
     Cookie/Authorization/credential and the module never reads the vault;
  3. no CAPTCHA solving and no challenge bypass - HTTP 403/429 raises
     :class:`BlockedBySiteChallenge`, the snapshot is recorded ``stale`` with
     reason ``blocked_by_site_challenge``, and there is NO retry loop;
  4. strict SSRF block - :func:`page_problem` accepts only the exact public
     Google search-page URL shape (https, that one host, that one path, only
     the query keys we write), so loopback/RFC1918/link-local/CGNAT and any
     other target is refused before a request is built; redirects are refused
     outright (the page has no business redirecting us);
  5. no proxy support in F1 (``proxy_urls`` and exit labels are F3's);
  6. hard poll floor - :func:`next_check_at` is at least
     :data:`POLL_FLOOR_SECONDS` (300 s) and carries seeded +/-30% jitter.

PRIVACY. Page/flight words are outside text: a recorded change latches
``jarvis_gate.latch_taint(why="price_radar")`` exactly like ``jarvis_tellme``
does for a page watch. The module keeps typed numbers (price in whole cents,
airline code, stops, duration), never the page and never its prose, and
nothing is logged: the disclosure lines below are the words the owner sees on
a card/footer (F2/F3 reuse them verbatim through the constants).

WHAT F2/F3 WIRE IN (and this module does NOT import). The multi-source item
checker lives in its own shipped module ``backend/jarvis_price_sources.py``
(F2), and proxy/multi-exit work is F3. F1 exposes the integration points:

  * :func:`set_sources` - the F2 sources list (objects with ``name``,
    ``fetch()``, ``render()``); :func:`sources` reads it back;
  * :func:`register_alert_renderer` - the function F2/F3 installs to turn a
    :class:`PriceStore` diff into the owner's card words; without it the core
    words are used;
  * :class:`PriceStore` - constructed explicitly by the caller
    (``PriceStore()`` uses ``price-radar.db`` in the settings folder) and
    passed to F2's sources; F2 calls ``add_route``/``record_stale``/
    ``record``/``diff`` on it;
  * the disclosure constants:
    :data:`DISCLOSURE`, :data:`RESULT_FOOTER`, :data:`STEERING_ROW_FORMAT`,
    :data:`PROXY_FOOTER_FORMAT`.

ATTRIBUTION (both MIT; full text already in THIRD-PARTY-NOTICES.txt):

  * ``punitarani/fli`` (MIT, Copyright (c) 2025 Punit Arani):
    ``fli/search/_proto.py`` - the protobuf wire helpers, the ``tfs`` field
    layout (its comment block at the "tfs is the itinerary parameter" note),
    ``encode_tfs_segment`` and ``encode_tfs_payload``;
    ``fli/search/_tfs.py`` - ``build_tfs``/``page_url``/``extract_payload``
    and the page-transport reasoning;
    ``fli/search/_decoders.py`` - the row positions this parser reads
    (``parse_flight_row``, ``_parse_price_info``).
    Pinned from ``main`` (commit ``881aee5`` when read, 2026-10-21).
  * ``AWeirdDev/flights`` (``fast-flights``, MIT, Copyright (c) 2024
    AWeirdDev): ``fast_flights/parser.py`` - its ``parse_js`` documents the
    same inline-blob row layout (fare at ``k[1][0][1]``, legs at
    ``flight[2]``, duration at ``[11]``) and is the second source for the
    tolerant parser's tolerance.

No code is copied verbatim: the wire format is reimplemented in this module
from those documents, and the test suite stores their recorded ``tfs`` golden
values and asserts **byte parity**.

NOT MEASURED. No live request is made by the suite or by this module in F1;
the endpoint's stability is unproven and explicitly not claimed.
"""
from __future__ import annotations

import base64
import json
import os
import re
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

try:                                    # optional, like every voice/tellme module
    import jarvis_framework as fw
except Exception:                       # pragma: no cover - tests/repo mode
    fw = None  # type: ignore

try:                                    # the central sqlite helper (#673)
    import jarvis_sqlite as _sqlite
except Exception:                       # pragma: no cover
    _sqlite = None  # type: ignore


# ==========================================================================
#   The switch, the endpoint, the wording
# ==========================================================================

SWITCH_SECTION = "price_radar"
SWITCH_KEY = "enabled"
SWITCH_DEFAULT = False

#: ONE host and ONE path. Every request this module can build is this page.
SEARCH_HOST = "www.google.com"
SEARCH_PATH = "/travel/flights"
PAGE_TEMPLATE = "https://www.google.com/travel/flights"

#: Query keys the page URL is allowed to carry. Anything else is refused
#: (a tracker parameter added to the URL is the same mistake as a cookie).
ALLOWED_QUERY_KEYS = frozenset({"tfs", "hl", "gl", "curr"})

#: Hard poll floor, in seconds, and the +/- jitter around it (ruling 10.3).
POLL_FLOOR_SECONDS = 300
POLL_JITTER_FRACTION = 0.30

#: The stale reason recorded when a challenge stops a check. Never retried.
BLOCKED_REASON = "blocked_by_site_challenge"
FETCH_FAILED = "fetch_failed"
UNAVAILABLE = "unavailable"

#: The exact disclosure words the owner sees (F2/F3 reuse these verbatim).
DISCLOSURE = (
    "Checks public product and flight prices without sending cookies, saved "
    "logins, or tracking tags, using standard browser headers so repeated checks "
    "aren't linked together. It only reads public prices and never logs in, "
    "holds seats, or starts a checkout."
)
RESULT_FOOTER = "Checked as a new visitor (no cookies or account used)."
STEERING_ROW_FORMAT = (
    "This store showed two different prices at the same time: ${x} "
    "(Desktop · via search referral) vs. ${y} (Mobile · direct)."
)
PROXY_FOOTER_FORMAT = "Checked via configured proxy ({exit_label})."

#: The ONE endpoint notice every card/PR/doc repeats. It is unofficial, and
#: "flight radar" is NOT a booking tool - said in those words, every time.
UNOFFICIAL_NOTE = (
    "This reads Google Flights' public search page. That is an unofficial, "
    "unstable interface - it can change or break without notice. It is NOT a "
    "booking tool: it only reads public prices."
)

#: Cabin codes on the wire (and the names our callers use).
CABINS = {"economy": 1, "premium_economy": 2, "business": 3, "first": 4}
CABIN_NAMES = {v: k for k, v in CABINS.items()}

#: Passenger wire codes: 1 adult, 2 child, 3 infant on lap, 4 infant in own
#: seat (punitarani/fli, ``_proto.py``'s ``_PASSENGER_FIELDS``; getting the two
#: infant codes the wrong way round is a plausible wrong fare, not an error).
PASSENGER_CODES = {"adults": 1, "children": 2, "infants_on_lap": 3,
                   "infants_in_seat": 4}
MAX_PASSENGERS = 9

#: Max stops on the wire is zero-based: 0 = non-stop, 1 = one stop or fewer.
STOPS_ANY = 0


def _config_enabled() -> bool:
    """``[price_radar] enabled`` read fresh; False when it cannot be read."""
    if fw is None:
        return SWITCH_DEFAULT
    try:
        section = fw.load_framework().get(SWITCH_SECTION) or {}
        value = section.get(SWITCH_KEY, SWITCH_DEFAULT)
    except Exception:
        return SWITCH_DEFAULT
    if isinstance(value, str):
        return value.strip().lower() not in ("false", "0", "no", "off", "")
    return bool(value)


def enabled() -> bool:
    """True only when the owner turned the radar on. Default: False."""
    return _config_enabled()


# ==========================================================================
#   The tfs protobuf builder (adapted from punitarani/fli, MIT)
# ==========================================================================

def _varint(value: int) -> bytes:
    if value < 0:
        raise ValueError("varint encoder takes non-negative ints only")
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _tag(field: int, wire: int) -> bytes:
    return _varint((field << 3) | wire)


def _length_delim(field: int, payload: bytes) -> bytes:
    return _tag(field, 2) + _varint(len(payload)) + payload


def _varint_field(field: int, value: int) -> bytes:
    return _tag(field, 0) + _varint(value)


def _urlsafe_b64(data: bytes) -> str:
    """URL-safe base64 WITHOUT padding - the form the page's own URLs carry."""
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def iata(code: str) -> str:
    """A bare IATA code: upper-case, 3 letters. Refuses anything else."""
    value = str(code or "").strip().upper()
    if not (len(value) == 3 and value.isalpha() and value.isascii()):
        raise ValueError(f"not an IATA code: {code!r}")
    return value


def passenger_codes(*, adults: int = 1, children: int = 0,
                    infants_on_lap: int = 0, infants_in_seat: int = 0) -> list:
    """One field-8 code per traveller, in Google's order (adult, child, lap
    infant, seat infant), refusing an all-zero mix and over-9 totals."""
    counts = ((1, adults), (2, children), (3, infants_on_lap), (4, infants_in_seat))
    total = 0
    for code, count in counts:
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError("passenger counts must be non-negative ints")
        total += count
    if total == 0:
        raise ValueError("a search needs at least one traveller")
    if total > MAX_PASSENGERS:
        raise ValueError(f"{total} travellers is over Google's {MAX_PASSENGERS} limit")
    return [code for code, count in counts for _ in range(count)]


def encode_segment(origins: Sequence[str], dests: Sequence[str], date: str, *,
                   max_stops: Optional[int] = None,
                   carriers: Sequence[str] = (),
                   carriers_exclude: Sequence[str] = (),
                   selected_legs: Sequence[dict] = (),
                   layover_airports: Sequence[str] = (),
                   min_layover: Optional[int] = None,
                   max_layover: Optional[int] = None) -> bytes:
    """One travel direction, as the length-delimited field 3 message.

    Field positions are punitarani/fli's ``encode_tfs_segment``: 2 date,
    4 selected leg (repeated), 5 stop ceiling, 6/7 carrier include/exclude,
    13 origin ``[1, code]``, 14 destination ``[1, code]``, 15 layover
    airport, 17/18 layover minute bounds. MAX STOPS IS ZERO-BASED: ``None``
    leaves it unconstrained and writing ``0`` for "any" would pin every
    search to non-stop, so only an explicit ceiling is written.
    """
    body = _length_delim(2, str(date).encode("ascii"))
    if max_stops is not None:
        body += _varint_field(5, int(max_stops))
    for code in carriers:
        body += _length_delim(6, str(code).encode("ascii"))
    for code in carriers_exclude:
        body += _length_delim(7, str(code).encode("ascii"))
    for leg in selected_legs:
        body += _length_delim(
            4,
            _length_delim(1, iata(leg["origin"]).encode("ascii"))
            + _length_delim(2, str(leg["date"]).encode("ascii"))
            + _length_delim(3, iata(leg["dest"]).encode("ascii"))
            + _length_delim(5, str(leg["airline"]).encode("ascii"))
            + _length_delim(6, str(leg["flight_number"]).encode("ascii")),
        )
    for code in origins:
        body += _length_delim(13, _varint_field(1, 1) + _length_delim(2, iata(code).encode()))
    for code in dests:
        body += _length_delim(14, _varint_field(1, 1) + _length_delim(2, iata(code).encode()))
    for code in layover_airports:
        body += _length_delim(15, iata(code).encode("ascii"))
    if min_layover is not None:
        body += _varint_field(17, int(min_layover))
    if max_layover is not None:
        body += _varint_field(18, int(max_layover))
    return _length_delim(3, body)


def encode_tfs(segments: Sequence[bytes], *, one_way: bool, passengers: Sequence[int] = (1,),
               cabin: int = 1) -> str:
    """Wrap encoded segments in the ``tfs`` envelope and base64 them.

    Envelope positions are punitarani/fli's ``encode_tfs_payload``: field 1 =
    28 constant, field 2 = 2 constant, field 3 = repeated segments, field 8 =
    one passenger code per traveller, field 9 = cabin, field 14 = 1 constant,
    field 19 = 2 one-way / 1 round-trip.
    """
    if not segments:
        raise ValueError("at least one segment is required")
    if not passengers:
        passengers = (1,)
    payload = _varint_field(1, 28) + _varint_field(2, 2) + b"".join(segments)
    for code in passengers:
        payload += _varint_field(8, int(code))
    payload += _varint_field(9, int(cabin)) + _varint_field(14, 1)
    payload += _varint_field(19, 2 if one_way else 1)
    return _urlsafe_b64(payload)


def build_tfs(origins: Sequence[str], dests: Sequence[str], date: str, *,
              return_date: Optional[str] = None, cabin: str = "economy",
              max_stops: Optional[int] = None, adults: int = 1, children: int = 0,
              infants_on_lap: int = 0, infants_in_seat: int = 0,
              alliances: Sequence[str] = (),
              alliances_exclude: Sequence[str] = (),
              layover_airports: Sequence[str] = (),
              min_layover: Optional[int] = None,
              max_layover: Optional[int] = None,
              selected_legs: Sequence[dict] = ()) -> str:
    """The ``tfs`` token for ONE one-way or round-trip route.

    ``cabin`` is one of :data:`CABINS`; ``max_stops`` is zero-based (None =
    any, 0 = non-stop, 1 = one stop or fewer); ``return_date`` makes it a
    round trip. Alliance names ride in the same carrier lists Google uses
    (e.g. ``"ONEWORLD"``).
    """
    try:
        wire_cabin = CABINS[str(cabin).strip().lower()]
    except KeyError:
        raise ValueError(f"cabin must be one of {sorted(CABINS)}") from None
    codes = passenger_codes(adults=adults, children=children,
                            infants_on_lap=infants_on_lap,
                            infants_in_seat=infants_in_seat)
    out = encode_segment(list(origins), list(dests), date, max_stops=max_stops,
                         carriers=list(alliances),
                         carriers_exclude=list(alliances_exclude),
                         selected_legs=selected_legs,
                         layover_airports=list(layover_airports),
                         min_layover=min_layover, max_layover=max_layover)
    if return_date:
        out += encode_segment(list(dests), list(origins), return_date,
                              max_stops=max_stops,
                              carriers=list(alliances),
                              carriers_exclude=list(alliances_exclude),
                              layover_airports=list(layover_airports),
                              min_layover=min_layover, max_layover=max_layover)
    return encode_tfs([out], one_way=not return_date, passengers=codes,
                      cabin=wire_cabin)


def date_window(date: str, days: int = 3) -> list:
    """The dates within +/- ``days`` of ``date`` (a date sweeps this window).

    Google's search page takes ONE departure date, so a window is N separate
    read-only GETs, one per date - never a burst: the caller spaces them by
    :func:`next_check_at` and stops at the first good answer for the target.
    """
    import datetime as _dt
    try:
        centre = _dt.date.fromisoformat(str(date))
    except ValueError:
        raise ValueError("date must be YYYY-MM-DD") from None
    span = max(0, int(days))
    return [(centre + _dt.timedelta(days=offset)).isoformat()
            for offset in range(-span, span + 1)]


def page_url(tfs: str, *, language: str = "en", country: str = "US",
             currency: Optional[str] = None) -> str:
    """The ONE page URL this module may request, from a token and locale."""
    params = [f"tfs={tfs}", f"hl={language or 'en'}", f"gl={country or 'US'}"]
    if currency:
        params.append(f"curr={currency}")
    return f"{PAGE_TEMPLATE}?{'&'.join(params)}"


# ==========================================================================
#   SSRF allowlist and the one read-only fetch
# ==========================================================================

class PriceRadarRefused(Exception):
    """Something was refused before any request was built (SSRF/allowlist)."""


class BlockedBySiteChallenge(Exception):
    """The page answered a challenge (403/429). Never retried."""


class FetchFailed(Exception):
    """The page could not be read (network/HTTP error). No invented price."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse every redirect: the page has no business sending us elsewhere
    (the ruling: no auto cross-host redirects; safest form is none at all)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(
            req.full_url, code,
            f"refused to follow a redirect to {newurl}", headers, fp)


def page_problem(url: str) -> str:
    """Why ``url`` is not the single allowed page URL, or "" when it is.

    Strict by construction: https only; exactly :data:`SEARCH_HOST`; no
    port, userinfo or fragment; exactly :data:`SEARCH_PATH`; and only the
    query keys in :data:`ALLOWED_QUERY_KEYS` with a non-empty ``tfs``. This is
    the whole SSRF guard - if the URL has any other shape it is refused
    before a request is built, so loopback/RFC1918/link-local/CGNAT, other
    hosts, other paths, proxies and redirect targets can never be requested.
    """
    from urllib.parse import urlsplit, parse_qsl
    if not isinstance(url, str) or not url:
        return "no URL"
    try:
        split = urlsplit(url)
    except Exception:
        return "the URL cannot be parsed"
    if split.scheme != "https":
        return f"only https is allowed, not {split.scheme or 'no scheme'}"
    if split.hostname != SEARCH_HOST:
        return f"only {SEARCH_HOST} is allowed, not {split.hostname or 'no host'}"
    if split.username or split.password or split.port is not None:
        return "an address with a username, password or port is not the page"
    if split.fragment:
        return "the page URL carries a fragment"
    if split.path != SEARCH_PATH:
        return f"only {SEARCH_PATH} is allowed, not {split.path}"
    keys = [k for k, _v in parse_qsl(split.query, keep_blank_values=True)]
    unknown = sorted(set(keys) - ALLOWED_QUERY_KEYS)
    if unknown:
        return f"the page URL carries unexpected parameters: {', '.join(unknown)}"
    if not dict(parse_qsl(split.query, keep_blank_values=True)).get("tfs"):
        return "the page URL carries no tfs token"
    return ""


#: The browser-shaped headers the disclosure describes: standard, fixed,
#: and deliberately without Cookie/Authorization/tracking or cache validators.
DEFAULT_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/128.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
}
FORBIDDEN_HEADERS = ("Cookie", "Authorization", "If-None-Match", "If-Modified-Since")

#: Body cap: the page is ~100-250 KB; more than this is not a search page.
PAGE_MAX_BYTES = 2_000_000
PAGE_TIMEOUT_SECONDS = 15


def _request_headers() -> dict:
    """The fixed headers above, with every identity/tracking header absent -
    asserted here so a future edit cannot quietly add one."""
    headers = dict(DEFAULT_HEADERS)
    for name in FORBIDDEN_HEADERS:
        headers.pop(name, None)
    return headers


def _default_open(req: urllib.request.Request, timeout: float,
                  handlers: Sequence) -> Any:
    import jarvis_local_http as LH
    return LH.public_urlopen(req, timeout, *handlers)


def fetch_page(url: str, *, opener: Optional[Callable] = None,
               timeout: float = PAGE_TIMEOUT_SECONDS) -> str:
    """ONE read-only GET of the allowed page URL, and nothing else.

    ``opener`` is for the suite only: a callable
    ``opener(request, timeout, handlers)`` returning a response-like object.
    The default goes through ``jarvis_local_http.public_urlopen`` (which
    re-checks private addresses at the connection - the DNS-rebinding
    defence ``jarvis_tellme`` uses) with a redirect-refusing handler.
    403/429 raise :class:`BlockedBySiteChallenge`; other HTTP errors and
    network errors raise :class:`FetchFailed`. No cookies, no auth, no
    retries, no redirects.
    """
    problem = page_problem(url)
    if problem:
        raise PriceRadarRefused(problem)
    req = urllib.request.Request(url, headers=_request_headers())
    open_url = opener or _default_open
    try:
        with open_url(req, timeout, (_NoRedirect(),)) as resp:
            status = int(getattr(resp, "status", 200) or 200)
            if status in (403, 429):
                raise BlockedBySiteChallenge(
                    f"the site answered HTTP {status}; not retried")
            if status >= 400:
                raise FetchFailed(f"the site answered HTTP {status}")
            body = resp.read(PAGE_MAX_BYTES + 1)
    except BlockedBySiteChallenge:
        raise
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 429):
            raise BlockedBySiteChallenge(
                f"the site answered HTTP {exc.code}; not retried") from exc
        raise FetchFailed(f"the site answered HTTP {exc.code}") from exc
    except PriceRadarRefused:
        raise
    except Exception as exc:                      # network, TLS, timeout...
        raise FetchFailed(str(exc) or "the page could not be read") from exc
    if len(body) > PAGE_MAX_BYTES:
        raise FetchFailed("the page was larger than a search page can be")
    return body.decode("utf-8", errors="replace")


# ==========================================================================
#   The tolerant parser (the page's inline ds:1 payload)
# ==========================================================================

#: ``AF_initDataCallback({key: 'ds:1', hash: '..', data:[...], sideChannel: {}});``
_DS_BLOB = re.compile(r"AF_initDataCallback\((\{.*?\})\);", re.S)
_DS_KEY = re.compile(r"key:\s*'([^']+)'")
_DS_DATA = re.compile(r"data:(.*?), sideChannel", re.S)

#: Currencies whose minor unit is 1/100 of the written price; every currency
#: not in this map makes the parser answer ``unknown_currency`` rather than
#: invent a cents number from a wrong exponent.
TWO_DECIMAL_CURRENCIES = frozenset({"USD", "EUR", "GBP", "CAD", "AUD", "CHF", "CNY",
                                    "HKD", "SGD", "NZD", "SEK", "NOK", "DKK", "PLN",
                                    "BRL", "MXN", "INR", "ZAR", "TRY", "THB", "QAR",
                                    "SAR", "AED", "ILS", "RON", "BGN", "HUF", "CZK"})
ZERO_DECIMAL_CURRENCIES = frozenset({"JPY", "KRW", "VND", "CLP", "IDR", "HUF"})


def extract_payload(html: str) -> Any:
    """The ``ds:1`` payload out of a rendered search page, or None.

    Ported from punitarani/fli's ``extract_payload``: walk every
    ``AF_initDataCallback`` block, keep the one whose key is ``ds:1``, and
    JSON-decode its ``data``. A missing/unparseable blob is None (the caller
    says "unavailable"), never an exception.
    """
    if not isinstance(html, str) or not html:
        return None
    for match in _DS_BLOB.finditer(html):
        blob = match.group(1)
        key = _DS_KEY.search(blob)
        if not key or key.group(1) != "ds:1":
            continue
        data = _DS_DATA.search(blob)
        if not data:
            continue
        try:
            return json.loads(data.group(1))
        except (ValueError, TypeError):
            return None
    return None


def _safe_list(node: Any) -> list:
    return node if isinstance(node, list) else []


def _safe_str(node: Any) -> str:
    return node.strip() if isinstance(node, str) else ""


def _safe_int(node: Any) -> Optional[int]:
    if isinstance(node, bool) or not isinstance(node, (int, float)):
        return None
    try:
        value = int(node)
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


def to_cents(price: Any, currency: str) -> Optional[int]:
    """A page price in integer whole cents, or None when that cannot be TRUE.

    Only a numeric price in a currency whose minor unit this module knows is
    converted; anything else is None (the caller records ``unavailable`` -
    a fake 0 or a guessed exponent is worse than no number).
    """
    if isinstance(price, bool) or not isinstance(price, (int, float)):
        return None
    code = str(currency or "").upper()
    if code in ZERO_DECIMAL_CURRENCIES:
        if float(price) != int(price):
            return None
        return int(price)
    if code in TWO_DECIMAL_CURRENCIES:
        cents = int(round(float(price) * 100.0))
        return cents if cents >= 0 else None
    return None


def _price_from_row(row: list) -> tuple:
    """The row's price; returns (price_or_None, currency_token_or_None).

    Ported from fli's ``_parse_price_info``/``fast_flights``' ``parse_js``:
    the fare block is ``row[1]``; its head is ``row[1][0]`` and the number is
    the head's last element. An empty head is Google saying "no shopping-list
    price for this row" - that is None, never zero.
    """
    block = _safe_list(row[1]) if len(row) > 1 else []
    if not block:
        raise ValueError("price block missing")
    head = _safe_list(block[0])
    token = _safe_str(block[1]) if len(block) > 1 else ""
    if not head:
        return None, token or None
    raw = head[-1]
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise ValueError("price field is not numeric")
    return float(raw), token or None


def _legs_of(detail: list) -> list:
    return [leg for leg in _safe_list(detail[2]) if isinstance(leg, list)]


def _airline_of(detail: list, legs: list) -> str:
    code = _safe_str(detail[0]) if len(detail) > 0 else ""
    if not code and legs:
        info = _safe_list(legs[0][22]) if len(legs[0]) > 22 else []
        code = _safe_str(info[0]) if info else ""
    if code and code.lower() != "multi":
        return code.upper()
    return ""


def _duration_of(detail: list, legs: list) -> Optional[int]:
    value = _safe_int(detail[9]) if len(detail) > 9 else None
    if value is not None:
        return value
    total = 0
    for leg in legs:
        part = _safe_int(leg[11]) if len(leg) > 11 else None
        if part is not None:
            total += part
    return total or None


def _price_level(payload: list) -> Optional[str]:
    """The page's low/typical/high insight, when the payload carries one.

    Known-position first (fli's decoder notes no stable page position for it;
    the RPC carried it elsewhere), then a bounded scan of the top-level
    insight block. It is deliberately OPTIONAL: most captures have no such
    field in the payload this module reads, and None is the honest answer -
    never a label guessed from the page's prose.
    """
    if not isinstance(payload, list):
        return None
    for index in (5, 4, 6):
        if len(payload) <= index:
            continue
        block = payload[index]
        candidate = None
        if isinstance(block, str):
            candidate = block
        elif isinstance(block, list) and block and isinstance(block[0], str):
            candidate = block[0]
        if isinstance(candidate, str) and candidate.strip().lower() in ("low", "typical", "high"):
            return candidate.strip().lower()
    return None


def parse_payload(payload: Any, *, currency: str = "USD") -> dict:
    """The page payload -> typed itineraries, tolerantly.

    Returns ``{"ok", "currency", "itineraries", "lowest_price_cents", "why"}``.
    Every row is its own try/except: one odd row is skipped, not fatal; a
    malformed/empty payload is ``ok: False`` with a reason, never a crash and
    never a fake price. Row positions are fli's ``parse_flight_row`` (detail
    ``row[0]``, price block ``row[1]``, legs ``detail[2]``, duration
    ``detail[9]``) cross-checked with ``fast_flights/parser.py``.
    """
    out = {"ok": False, "currency": str(currency or "").upper(),
           "itineraries": [], "lowest_price_cents": None, "why": UNAVAILABLE,
           "price_level": None}
    if not isinstance(payload, list):
        out["why"] = "payload is not the page structure"
        return out
    groups = []
    for section in payload[2:4]:
        # fast_flights/parser.py: a section's [0] holds the rows; a section
        # that is not that shape is skipped rather than guessed at.
        if isinstance(section, list) and section:
            inner = section[0]
            if isinstance(inner, list):
                groups.extend(inner)
    level = _price_level(payload)
    out["price_level"] = level
    rows = []
    for row in groups:
        try:
            if not isinstance(row, list) or not row:
                continue
            detail = _safe_list(row[0])
            if not detail:
                continue
            price, _token = _price_from_row(row)
            cents = to_cents(price, out["currency"]) if price is not None else None
            legs = _legs_of(detail)
            rows.append({
                "price_cents": cents,
                "airline": _airline_of(detail, legs),
                "stops": max(len(legs) - 1, 0),
                "duration_minutes": _duration_of(detail, legs),
                "price_level": level,
            })
        except Exception:
            continue                      # one odd row never kills the page
    out["itineraries"] = rows
    priced = [r["price_cents"] for r in rows if r["price_cents"] is not None]
    if priced:
        out["lowest_price_cents"] = min(priced)
        out["ok"] = True
        out["why"] = ""
    elif rows:
        out["why"] = "no usable price in the page"
    else:
        out["why"] = "no flight rows in the page"
    return out


def parse_page(html: str, *, currency: str = "USD") -> dict:
    """A rendered page -> parse_payload's dict; no page -> unavailable."""
    payload = extract_payload(html)
    if payload is None:
        return {"ok": False, "currency": str(currency or "").upper(),
                "itineraries": [], "lowest_price_cents": None,
                "why": "no ds:1 payload (the page changed, or it is a challenge)"}
    return parse_payload(payload, currency=currency)


# ==========================================================================
#   The poll floor (hard: >= 300 s, seeded +/-30% jitter)
# ==========================================================================

def next_check_at(now: float, *, rng: Optional[Any] = None,
                  floor: int = POLL_FLOOR_SECONDS) -> float:
    """The earliest next check: ``floor`` seconds out, +/-30% jitter.

    The floor is HARD (the ruling): an interval below
    :data:`POLL_FLOOR_SECONDS` is raised to it, so no caller can poll faster
    than once every five minutes, and the jitter is seeded when ``rng`` is
    given (deterministic in tests). Checks never fire on a robotic tick.
    """
    try:
        base = float(floor)
    except (TypeError, ValueError):
        base = float(POLL_FLOOR_SECONDS)
    base = max(base, float(POLL_FLOOR_SECONDS))
    spread = base * POLL_JITTER_FRACTION
    if rng is None:
        import random
        offset = random.uniform(-spread, spread)
    else:
        offset = rng.uniform(-spread, spread)
    return float(now) + base + offset


# ==========================================================================
#   The store (SQLite; whole cents; last-known-good + stale)
# ==========================================================================

SCHEMA_VERSION = 1


def _config_dir() -> Path:
    """The settings folder, read live like every other module's."""
    env = os.environ.get("OPENJARVIS_CONFIG_DIR") or os.environ.get("JARVIS_CONFIG_DIR")
    if env:
        return Path(os.path.expanduser(env))
    mod = sys.modules.get("jarvis_framework")
    if mod is not None:
        try:
            return Path(mod.CONFIG_DIR)
        except Exception:
            pass
    return Path(os.path.expanduser("~")) / ".openjarvis"


def store_path() -> Path:
    """``price-radar.db`` in the settings folder - the one place it is named."""
    return _config_dir() / "price-radar.db"


def _format_usd(cents: Optional[int]) -> str:
    if cents is None:
        return "no price"
    dollars, remainder = divmod(int(cents), 100)
    return f"${dollars:,}.{remainder:02d}"


class PriceStore:
    """The price history: routes, snapshots, last-known-good and the diff.

    Created explicitly by the caller (F2 passes one store to its sources):

        store = PriceStore()                       # price-radar.db in settings
        route = store.add_route("JFK", "LAX", "2030-09-15",
                                target_price_cents=25000)
        store.record(route["id"], parsed)           # a successful check
        store.record_stale(route["id"], BLOCKED_REASON)  # a failed/challenged one
        change = store.diff(route["id"])            # outside text or ""

    A failed check NEVER overwrites the last good snapshot (tellme's rule),
    never alerts, and never invents a price. The diff's text is outside text:
    a real change latches the gate's conversation taint, exactly like
    ``jarvis_tellme`` does for a page watch.

    Connections follow #673: one short-lived connection per call through
    ``jarvis_sqlite.connect`` (the closing connection with WAL/synchronous/
    busy_timeout/temp_store pragmas), never a long-lived handle.
    """

    def __init__(self, path: Optional[str] = None):
        self.path = Path(path) if path else store_path()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        self._migrate()

    def _open(self):
        """One connection for one call (#673 pragmas; closes on the way out)."""
        if _sqlite is None:
            raise RuntimeError(
                "jarvis_sqlite.py is not beside this module, so the closing "
                "connection this store needs is missing - nothing is written")
        conn = _sqlite.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        return conn

    def close(self) -> None:
        """Nothing is held between calls; kept so callers have a close()."""
        return None

    # -- schema ----------------------------------------------------------
    def _migrate(self) -> None:
        """Idempotent schema: ``PRAGMA user_version`` says which migration has
        run; re-running on the same file executes nothing."""
        with self._open() as db:
            current = int(db.execute("PRAGMA user_version").fetchone()[0])
            if current >= SCHEMA_VERSION:
                return
            db.executescript(
                "CREATE TABLE IF NOT EXISTS routes ("
                " id INTEGER PRIMARY KEY AUTOINCREMENT,"
                " origin TEXT NOT NULL, destination TEXT NOT NULL,"
                " depart_date TEXT NOT NULL, return_date TEXT,"
                " cabin TEXT NOT NULL DEFAULT 'economy',"
                " max_stops INTEGER, currency TEXT NOT NULL DEFAULT 'USD',"
                " target_price_cents INTEGER,"
                " created_at TEXT NOT NULL, next_check_at REAL NOT NULL,"
                " UNIQUE(origin, destination, depart_date, return_date, cabin, max_stops));"
                "CREATE TABLE IF NOT EXISTS snapshots ("
                " id INTEGER PRIMARY KEY AUTOINCREMENT,"
                " route_id INTEGER NOT NULL REFERENCES routes(id),"
                " checked_at TEXT NOT NULL,"
                " lowest_price_cents INTEGER, airline TEXT, stops INTEGER,"
                " duration_minutes INTEGER, price_level TEXT,"
                " stale INTEGER NOT NULL DEFAULT 0, stale_reason TEXT);"
                "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);"
                "CREATE INDEX IF NOT EXISTS snapshots_route ON snapshots(route_id, id);"
            )
            db.execute("PRAGMA user_version = %d" % SCHEMA_VERSION)

    # -- routes ----------------------------------------------------------
    def add_route(self, origin: str, destination: str, depart_date: str, *,
                  return_date: Optional[str] = None, cabin: str = "economy",
                  max_stops: Optional[int] = None, currency: str = "USD",
                  target_price_cents: Optional[int] = None,
                  now: Optional[float] = None) -> dict:
        """Register a tracked route; the same route twice is the same row."""
        origin, destination = iata(origin), iata(destination)
        cabin = str(cabin).strip().lower()
        if cabin not in CABINS:
            raise ValueError(f"cabin must be one of {sorted(CABINS)}")
        if target_price_cents is not None and (
                isinstance(target_price_cents, bool)
                or not isinstance(target_price_cents, int)
                or target_price_cents < 0):
            raise ValueError("target_price_cents must be a non-negative int (whole cents)")
        stamp = _iso_now(now)
        due = next_check_at(now if now is not None else _now())
        with self._open() as db:
            # SQLite's UNIQUE treats NULLs as distinct, so "the same route
            # twice" cannot rely on INSERT OR IGNORE: look first, then insert.
            row = db.execute(
                "SELECT * FROM routes WHERE origin=? AND destination=? AND depart_date=?"
                " AND return_date IS ? AND cabin=? AND max_stops IS ?",
                (origin, destination, str(depart_date), return_date, cabin, max_stops)
            ).fetchone()
            if row is None:
                db.execute(
                    "INSERT INTO routes (origin, destination, depart_date,"
                    " return_date, cabin, max_stops, currency, target_price_cents,"
                    " created_at, next_check_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (origin, destination, str(depart_date), return_date, cabin,
                     max_stops, str(currency or "USD").upper(), target_price_cents,
                     stamp, due))
                row = db.execute(
                    "SELECT * FROM routes WHERE origin=? AND destination=? AND depart_date=?"
                    " AND return_date IS ? AND cabin=? AND max_stops IS ?",
                    (origin, destination, str(depart_date), return_date, cabin,
                     max_stops)).fetchone()
        return dict(row) if row is not None else {}

    def routes(self) -> list:
        with self._open() as db:
            return [dict(r) for r in db.execute("SELECT * FROM routes ORDER BY id")]

    def due(self, route_id: int, *, now: Optional[float] = None) -> bool:
        """True only when the route's floor+jitter window has passed."""
        stamp = _now() if now is None else float(now)
        with self._open() as db:
            row = db.execute("SELECT next_check_at FROM routes WHERE id=?",
                             (route_id,)).fetchone()
        if row is None:
            return False
        return float(row["next_check_at"] or 0.0) <= stamp

    # -- snapshots -------------------------------------------------------
    def record(self, route_id: int, parsed: dict, *,
               now: Optional[float] = None) -> dict:
        """A successful parse: one snapshot, last-known-good updated.

        A parse that found no price is recorded as stale ``unavailable`` -
        never as a price - and keeps the previous good snapshot.
        """
        stamp = _iso_now(now)
        if not isinstance(parsed, dict) or not parsed.get("ok") or \
                parsed.get("lowest_price_cents") is None:
            return self.record_stale(route_id, UNAVAILABLE, now=now)
        best = parsed.get("lowest_price_cents")
        airline, stops, duration = "", None, None
        for item in _safe_list(parsed.get("itineraries")):
            if item.get("price_cents") == best:
                airline = str(item.get("airline") or "")
                stops = item.get("stops")
                duration = item.get("duration_minutes")
                break
        with self._open() as db:
            db.execute(
                "INSERT INTO snapshots (route_id, checked_at, lowest_price_cents,"
                " airline, stops, duration_minutes, price_level, stale, stale_reason)"
                " VALUES (?,?,?,?,?,?,?,0,NULL)",
                (route_id, stamp, int(best), airline, stops, duration,
                 parsed.get("price_level")))
            self._reschedule(db, route_id, now=now)
        return {"ok": True, "stale": False, "lowest_price_cents": int(best),
                "airline": airline, "stops": stops, "duration_minutes": duration,
                "price_level": parsed.get("price_level"), "checked_at": stamp}

    def record_stale(self, route_id: int, reason: str, *,
                     now: Optional[float] = None) -> dict:
        """A failed/challenged/unavailable check: stale, NO price invented,
        the last good snapshot untouched (tellme's semantics)."""
        stamp = _iso_now(now)
        with self._open() as db:
            db.execute(
                "INSERT INTO snapshots (route_id, checked_at, lowest_price_cents,"
                " stale, stale_reason) VALUES (?,?,NULL,1,?)",
                (route_id, stamp, str(reason or UNAVAILABLE)))
            self._reschedule(db, route_id, now=now)
        return {"ok": False, "stale": True, "reason": str(reason or UNAVAILABLE),
                "checked_at": stamp}

    def _reschedule(self, db, route_id: int, *, now: Optional[float]) -> None:
        stamp = _now() if now is None else float(now)
        db.execute("UPDATE routes SET next_check_at=? WHERE id=?",
                   (next_check_at(stamp), route_id))

    def latest(self, route_id: int, *, good_only: bool = False) -> Optional[dict]:
        sql = "SELECT * FROM snapshots WHERE route_id=?"
        if good_only:
            sql += " AND stale=0 AND lowest_price_cents IS NOT NULL"
        sql += " ORDER BY id DESC LIMIT 1"
        with self._open() as db:
            row = db.execute(sql, (route_id,)).fetchone()
        return dict(row) if row is not None else None

    def _previous_good(self, route_id: int, before_id: Optional[int] = None) -> Optional[dict]:
        """The newest good snapshot BEFORE ``before_id`` (or the newest good
        when no bound is given). This is what a change is compared against -
        never the newest row itself (which is the new price)."""
        sql = ("SELECT * FROM snapshots WHERE route_id=? AND stale=0"
               " AND lowest_price_cents IS NOT NULL")
        params: list = [route_id]
        if before_id is not None:
            sql += " AND id < ?"
            params.append(int(before_id))
        sql += " ORDER BY id DESC LIMIT 1"
        with self._open() as db:
            row = db.execute(sql, params).fetchone()
        return dict(row) if row is not None else None

    def target_price_cents(self, route_id: int) -> Optional[int]:
        """The route's target, whole cents, or None."""
        with self._open() as db:
            row = db.execute("SELECT target_price_cents FROM routes WHERE id=?",
                             (route_id,)).fetchone()
        if row is None or row["target_price_cents"] is None:
            return None
        return int(row["target_price_cents"])

    def last_good_at(self, route_id: int) -> Optional[str]:
        row = self.latest(route_id, good_only=True)
        return row["checked_at"] if row else None

    # -- the outside-text diff ------------------------------------------
    def diff(self, route_id: int) -> dict:
        """Compare the newest check with the last good one BEFORE it.

        Returns ``{"changed", "stale", "price_delta_cents", "text", "words"}``.
        ``text`` is outside text (the caller/card says so; a changed answer
        latches the gate taint here). A stale failure changes nothing and has
        no text; a completely new route's first price is not a "change".
        """
        new = self.latest(route_id)
        out = {"changed": False, "stale": True, "price_delta_cents": None,
               "text": "", "words": []}
        if new is None:
            return out
        out["stale"] = bool(new.get("stale"))
        if out["stale"] or new.get("lowest_price_cents") is None:
            return out
        old = self._previous_good(route_id, before_id=new.get("id"))
        new_price = int(new["lowest_price_cents"])
        words = []
        if old is None:
            words.append(f"The lowest price is now {_format_usd(new_price)}.")
        else:
            old_price = int(old["lowest_price_cents"])
            if new_price < old_price:
                out["price_delta_cents"] = new_price - old_price
                words.append(f"The price dropped from {_format_usd(old_price)} "
                             f"to {_format_usd(new_price)}.")
            elif new_price > old_price:
                out["price_delta_cents"] = new_price - old_price
                words.append(f"The price rose from {_format_usd(old_price)} "
                             f"to {_format_usd(new_price)}.")
            elif old.get("airline") != new.get("airline") and new.get("airline"):
                words.append(f"The airline changed to {new['airline']}.")
            elif old.get("stops") != new.get("stops") and new.get("stops") is not None:
                words.append(f"The number of stops changed to {new['stops']}.")
            elif (old.get("duration_minutes") != new.get("duration_minutes")
                  and new.get("duration_minutes")):
                words.append(f"The duration changed to {new['duration_minutes']} minutes.")
        # The target and the low-price note are said only when there IS a
        # change (or the first price): an unchanged check is [SILENT], the
        # same watermark rule jarvis_tellme keeps for a page watch.
        if words:
            target = self.target_price_cents(route_id)
            if target is not None and new_price <= int(target):
                words.append(f"That is at or below your target of {_format_usd(int(target))}.")
            if (new.get("price_level") or "") == "low" and not any(
                    "low price" in word for word in words):
                words.append("Google marks this as a low price right now.")
        if words:
            out["changed"] = True
            out["words"] = words
            out["text"] = " ".join(words) + " " + RESULT_FOOTER
            self._latch()
        return out

    @staticmethod
    def _latch() -> bool:
        return _latch_gate()


def _now() -> float:
    import time
    return time.time()


def _iso_now(now: Optional[float]) -> str:
    import datetime as _dt
    stamp = _now() if now is None else float(now)
    return _dt.datetime.fromtimestamp(stamp, _dt.timezone.utc).isoformat(
        timespec="seconds")


def _latch_gate() -> bool:
    """A real change was outside text: latch the conversation taint, exactly
    as ``jarvis_tellme`` does for a page watch. Optional: repo-mode tests may
    not have jarvis_gate beside the modules."""
    try:
        import jarvis_gate
        return bool(jarvis_gate.latch_taint(why="price_radar"))
    except Exception:
        return False


# ==========================================================================
#   The check: switch -> floor -> ONE GET -> parse -> store -> (diff, outside)
# ==========================================================================

def check_route(store: PriceStore, route: dict, *,
                opener: Optional[Callable] = None,
                enabled: Optional[bool] = None,
                now: Optional[float] = None,
                language: str = "en", country: str = "US") -> dict:
    """Check ONE route, read-only, and return a plain result dict.

    Order: the switch (off = ZERO network, no request built), the poll floor
    (not due = no network), then ONE GET, then the tolerant parse, then the
    store. A challenge records ``blocked_by_site_challenge`` and stops - no
    retry; any failure records stale and keeps the last good price.
    """
    on = _config_enabled() if enabled is None else bool(enabled)
    route_id = int((route or {}).get("id") or 0)
    if not on:
        return {"checked": False, "network": False, "reason": "switched_off"}
    if route_id <= 0 or not store.due(route_id, now=now):
        return {"checked": False, "network": False, "reason": "not_due"}
    try:
        tfs = build_tfs(
            [route["origin"]], [route["destination"]], route["depart_date"],
            return_date=route.get("return_date"), cabin=route.get("cabin") or "economy",
            max_stops=route.get("max_stops"))
    except (KeyError, TypeError, ValueError) as exc:
        return {"checked": False, "network": False, "reason": f"bad route: {exc}"}
    currency = str(route.get("currency") or "USD").upper()
    url = page_url(tfs, language=language, country=country, currency=currency)
    try:
        html = fetch_page(url, opener=opener)
    except BlockedBySiteChallenge as exc:
        store.record_stale(route_id, BLOCKED_REASON, now=now)
        return {"checked": True, "network": True, "ok": False, "stale": True,
                "reason": BLOCKED_REASON, "why": str(exc)}
    except (FetchFailed, PriceRadarRefused) as exc:
        store.record_stale(route_id, FETCH_FAILED, now=now)
        return {"checked": True, "network": True, "ok": False, "stale": True,
                "reason": FETCH_FAILED, "why": str(exc)}
    parsed = parse_page(html, currency=currency)
    snapshot = store.record(route_id, parsed, now=now)
    change = store.diff(route_id)
    return {"checked": True, "network": True, "ok": bool(snapshot.get("ok")),
            "stale": bool(snapshot.get("stale")), "snapshot": snapshot,
            "change": change, "why": parsed.get("why") or ""}


# ==========================================================================
#   F2/F3 integration points (this module imports NOTHING from them)
# ==========================================================================

_SOURCES: list = []
_RENDERER: Optional[Callable] = None


def set_sources(sources: Sequence) -> None:
    """Install the F2 sources (``jarvis_price_sources.py``): objects with
    ``name``, ``fetch()`` and ``render()``. The core never imports them."""
    global _SOURCES
    _SOURCES = list(sources or [])


def sources() -> tuple:
    return tuple(_SOURCES)


def register_alert_renderer(renderer: Optional[Callable]) -> None:
    """Install F2/F3's card renderer; ``alert_text`` uses it when present."""
    global _RENDERER
    _RENDERER = renderer if callable(renderer) else None


def alert_text(store: PriceStore, route_id: int) -> str:
    """The owner-facing text for a route's latest change (outside text).

    Uses the registered renderer when one is installed; otherwise the core
    words: the diff, the result footer and the unofficial-endpoint note.
    """
    change = store.diff(route_id)
    if not change.get("changed"):
        return ""
    body = change.get("text") or ""
    if _RENDERER is not None:
        try:
            rendered = _RENDERER(store, route_id, change)
            if isinstance(rendered, str) and rendered.strip():
                return rendered.strip()
        except Exception:
            pass
    return f"{body} {UNOFFICIAL_NOTE}"


def steering_row(x_cents: int, y_cents: int) -> str:
    """The F2/F3 steering disclosure, in the exact words the owner approved."""
    return STEERING_ROW_FORMAT.format(x=_format_usd(x_cents).lstrip("$"),
                                      y=_format_usd(y_cents).lstrip("$"))


def proxy_note(exit_label: str) -> str:
    """The F3 proxy disclosure, in the exact approved words."""
    return PROXY_FOOTER_FORMAT.format(exit_label=str(exit_label or "configured exit"))
