"""jarvis_product_read.py - the READ half of the product check: turn the HTML
of an Amazon product page into tolerant review records and the reasons report
the offline engine already knows how to build.

WHERE THIS SITS (slice 2, 2026-10-26)
The engine (`backend/jarvis_product_research.py`, PR #849) takes review records
and returns a reasons-based report. This module is the missing read path: it
takes ONE string - the HTML of a product page captured from Jarvis's own
browser session after the owner has signed in once - and produces
(a) the listing facts the page states, (b) review records in the engine's own
schema, (c) honest warnings about what could not be read, and (d) a small
`assemble_report()` convenience that hands (b) to the engine and returns its
report with the records kept for debugging.

NOT WIRED TO ANYTHING, BY DESIGN
Nothing imports this module yet. It has **no route, no chat tool, no approval
card, no Settings row and no app surface**, exactly like the hand-off engine
slice. It imports nothing that can reach the network, open a browser, read or
write a file, or run a command: `html.parser`, `re`, and the engine module.
The one seam that a later wiring slice will fill is
`capture_with_owner_browser()`: it raises `CaptureNeedsOwnerBrowser` with the
plain sentence that reading a page needs the owner's own session. It does NOT
pretend to fetch anything - pretending would be the one thing this project's
local-first rule cannot allow.

WHAT IT PARSES (tolerantly, from synthetic page shapes only in the tests)
* Listing: the product title, the star rating, the rating count, the page's
  own canonical/source URL and the ASIN when present.
* Reviews: each review block's star rating, date (the page's date text AND a
  parsed ISO date when the text can be read), title, body, Verified Purchase
  badge, Vine label, helpful-vote count and variant line. A missing field is
  reported as missing, never guessed. Incentive wording is preserved verbatim
  in the body, where the ENGINE's own `incentive_language` signal reads it:
  there is no second flag here competing with the engine's judgement. The
  records go through the ENGINE's own `normalize_reviews()`, so there is ONE
  tolerant schema in this project, not a parallel one: an unrecognised field
  is ignored and an unreadable value becomes None exactly as the engine
  already does.
* Warnings, each a code plus a plain sentence: a sign-in/CAPTCHA/challenge
  page, a page that is not a product page, a missing listing title/rating/count,
  no reviews, a truncated page or review block, and reviews with missing
  fields. The caller can show them; this module never hides a gap.

WHY "WHAT AMAZON CHOSE TO SHOW" IS IN THE REPORT
The engine's sample caveat stays in every report (`assemble_report` returns the
engine's report unchanged, records kept beside it). A captured page is never
all reviews; it is the list Amazon served into the browser.

WHY A CAPTURE ERROR INSTEAD OF A FETCH
Amazon's review list needs a signed-in session, and this project does not run a
crawler. The capture lives in a later, explicitly carded slice that reads the
page from the owner's own browser. This module names that seam so the wiring
cannot silently "just fetch it".

STANDARD LIBRARY ONLY: `html.parser`, `re`, and the project's engine module. No
`json`, no `open()`, no socket, no subprocess, no browser automation library.

    py -3 -B backend/test_product_read.py
"""
from __future__ import annotations

import re
from html.parser import HTMLParser

import jarvis_product_research as ENGINE

VERSION = 1

#: The sentence the capture seam raises. It is documentation as much as an
#: error: the read path never fetches a page itself.
CAPTURE_MESSAGE = (
    "Reading a product page needs the owner's own browser session: sign in, "
    "open the product page, and hand Jarvis the page HTML it can capture from "
    "that window. This module does not fetch pages, so there is nothing to "
    "read yet."
)

#: Warning codes the caller can switch on; every message is plain English.
WARN_CHALLENGE = "challenge_or_login_page"
WARN_NOT_PRODUCT = "not_a_product_page"
WARN_TITLE = "listing_title_missing"
WARN_RATING = "listing_rating_missing"
WARN_RATING_COUNT = "listing_rating_count_missing"
WARN_NO_REVIEWS = "no_reviews"
WARN_TRUNCATED = "truncated_page"
WARN_TRUNCATED_REVIEW = "truncated_review"
WARN_MISSING_FIELDS = "review_fields_missing"

#: Tags that never wrap content (so they never deepen the element stack).
VOID_TAGS = frozenset({
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
})

#: What a challenge/sign-in page says instead of a product. Matched against the
#: lower-cased raw HTML; each entry is a shape seen in synthetic fixtures of a
#: challenge page, not a real page's words.
_CHALLENGE_MARKERS = (
    "captchacharacters",
    "amazon-captcha",
    "validatecaptcha",
    "robot check",
    "enter the characters you see",
    "type the characters you see",
    "not a robot",
    "authportal-main-section",
    "amazon sign-in",
)

#: Hooks inside one review block, mapped to the field they fill.
_REVIEW_HOOKS = {
    "review-star-rating": "rating",
    "cmps-review-star-rating": "rating",
    "review-date": "date",
    "review-title": "title",
    "review-body": "body",
    "avp-badge": "verified",
    "vine-review-badge": "vine",
    "helpful-vote-statement": "helpful",
    "format-strip": "variant",
    "format-strip-linkless": "variant",
}

#: Hooks that carry listing facts (not review fields).
_LISTING_HOOKS = {
    "rating-out-of-text": "listing_rating",
    "average-star-rating": "listing_rating",
    "total-review-count": "rating_count",
}

#: Written date forms inside a review date line, e.g.
#: "Reviewed in the United States on 12 October 2026".
_DATE_PATTERNS = (
    re.compile(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})"),
    re.compile(r"([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})"),
    re.compile(r"(\d{4})-(\d{2})-(\d{2})"),
)
_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

_STAR_RATING = re.compile(r"([0-5](?:\.\d+)?)\s*out\s+of\s+5", re.I)
_ANY_NUMBER = re.compile(r"(\d+(?:,\d{3})*)")
_ASIN_IN_URL = re.compile(r"/(?:dp|gp/product)/([A-Z0-9]{10})", re.I)
_HELPFUL = re.compile(r"(\d+(?:,\d{3})*)\s+(?:people|person|others?)\s+found", re.I)


class CaptureNeedsOwnerBrowser(RuntimeError):
    """The page capture is the owner's, not this module's.

    Raised by `capture_with_owner_browser()`. Nothing here starts a browser,
    signs in, or fetches a URL: the later wired slice fills this seam with a
    capture from Jarvis's own browser session, and until then the honest answer
    is this error, never a silent network call."""


def capture_with_owner_browser(*_args, **_kwargs) -> str:
    """The named seam where a real page capture will be plugged in.

    It always raises `CaptureNeedsOwnerBrowser`: this slice is offline and has
    no browser, no session and no network, so it cannot produce HTML. A caller
    that sees this error should show the owner the sentence in
    `CAPTURE_MESSAGE` and offer the existing screen-read/paste path instead of
    retrying."""
    raise CaptureNeedsOwnerBrowser(CAPTURE_MESSAGE)


def _clean(text) -> str:
    return " ".join(str(text or "").split())


def _warning(code: str, message: str, **counts) -> dict:
    out = {"code": code, "message": message}
    if counts:
        out["counts"] = counts
    return out


def _extract_rating(text):
    """A 0..5 star value from "4.5 out of 5 stars", or None."""
    if not text:
        return None
    found = _STAR_RATING.search(_clean(text))
    if not found:
        return None
    try:
        value = float(found.group(1))
    except ValueError:
        return None
    if 0.0 <= value <= 5.0:
        return value
    return None


def _extract_count(text):
    """The first whole number in a text such as "1,234 ratings", or None."""
    if not text:
        return None
    found = _ANY_NUMBER.search(_clean(text))
    if not found:
        return None
    try:
        return int(found.group(1).replace(",", ""))
    except ValueError:
        return None


def _extract_date(raw) -> str:
    """An ISO date from a page's review-date text, or "" when unreadable.

    The full text is kept separately as `date_text`: this only recognises the
    written forms the page uses, and an unreadable date is left unknown for the
    engine to count - never defaulted to today."""
    text = _clean(raw)
    if not text:
        return ""
    for pattern in _DATE_PATTERNS:
        found = pattern.search(text)
        if not found:
            continue
        groups = found.groups()
        try:
            if len(groups) == 3 and groups[0].isdigit() and len(groups[0]) == 4:
                year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
            elif groups[0].isdigit():
                day, month_name, year = int(groups[0]), groups[1].lower(), int(groups[2])
                month = _MONTHS.get(month_name)
            else:
                month_name, day, year = groups[0].lower(), int(groups[1]), int(groups[2])
                month = _MONTHS.get(month_name)
            if month and 1 <= day <= 31 and 1900 <= year <= 2100:
                return f"{year:04d}-{month:02d}-{day:02d}"
        except (TypeError, ValueError):
            continue
    return ""


def _helpful_count(text):
    """A helpful-vote count, including the page's "One person found this
    helpful" wording, or None."""
    text = _clean(text)
    if not text:
        return None
    found = _HELPFUL.search(text)
    if found:
        return int(found.group(1).replace(",", ""))
    lowered = text.lower()
    words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
             "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
    for word, value in words.items():
        if lowered.startswith(word + " "):
            return value
    return None


def _title_from_doc(doc_title: str) -> str:
    """A product name from a document <title>, for pages that have no
    #productTitle. "Amazon.com: Synthetic Widget: Home" -> "Synthetic Widget";
    a title that is only the shop name is not a product name."""
    text = _clean(doc_title)
    if not text:
        return ""
    lowered = text.lower()
    if "amazon." in lowered:
        parts = [part.strip() for part in text.split(":")]
        if len(parts) >= 2:
            candidate = parts[1]
            if candidate and candidate.lower() not in ("amazon.com", "amazon"):
                return candidate
        return ""
    return text


class _ProductPageParser(HTMLParser):
    """One tolerant pass over a page's HTML.

    It tracks the element stack itself so malformed or unclosed tags cannot
    make it raise; text is collected into the field being captured (a review
    title, a body, a listing title...), and a review is finalised only when its
    root element closes. At end of input an unclosed review is kept and the
    caller is told it is partial."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.captures = []          # [{"field", "depth", "chunks"}]
        self.listing = {
            "title": "", "rating_text": "", "rating_count_text": "",
            "canonical_url": "", "asin": "", "doc_title": "",
        }
        self.product_signals = False
        self.reviews = []           # raw review dicts, in page order
        self.partial_reviews = 0
        self._in_review = False
        self._review_depth = 0
        self._current = None

    # -- capture helpers ---------------------------------------------------
    def _begin(self, field: str) -> None:
        self.captures.append({"field": field, "depth": self.depth, "chunks": []})

    def _field_open(self, field: str) -> bool:
        return any(capture["field"] == field for capture in self.captures)

    def _assign(self, capture: dict) -> None:
        text = _clean(" ".join(capture["chunks"]))
        field = capture["field"]
        if self._in_review and self._current is not None:
            if field == "verified":
                self._current["verified"] = True
                self._current["_content"] = True
            elif field == "vine":
                self._current["vine"] = True
                self._current["_content"] = True
            elif field == "block":
                self._current["block"] = text
            elif field in ("rating", "date", "title", "body", "helpful", "variant"):
                self._current[field].append(text)
                if text:
                    self._current["_content"] = True
            return
        if field == "listing_title":
            if text and not self.listing["title"]:
                self.listing["title"] = text
        elif field == "listing_rating":
            if text and not self.listing["rating_text"]:
                self.listing["rating_text"] = text
        elif field == "rating_count":
            if text and not self.listing["rating_count_text"]:
                self.listing["rating_count_text"] = text
        elif field == "doc_title":
            if text and not self.listing["doc_title"]:
                self.listing["doc_title"] = text

    def _start_review(self) -> None:
        if self._in_review:
            return
        # A malformed page can open a review without closing a page-level
        # element; keep what it already said about the listing before the
        # capture context switches to the review.
        while self.captures:
            self._assign(self.captures.pop())
        self._in_review = True
        self._review_depth = self.depth
        self.product_signals = True
        self._current = {
            "rating": [], "date": [], "title": [], "body": [], "helpful": [],
            "variant": [], "block": "", "verified": False, "vine": False,
            "_content": False,
        }
        self._begin("block")

    def _finish_review(self, partial: bool = False) -> None:
        current = self._current or {}
        rating_text = " ".join(current.get("rating") or [])
        date_text = " ".join(current.get("date") or [])
        title_text = " ".join(current.get("title") or [])
        body_text = " ".join(current.get("body") or [])
        block_text = current.get("block") or ""
        # A review-title anchor often carries the star line before the words.
        title_rating_text = title_text
        title_text = re.sub(r"^[\s\d.]*out of 5 stars\s*", "", title_text, flags=re.I)
        helpful_text = " ".join(current.get("helpful") or [])
        variant_text = " ".join(current.get("variant") or [])
        vine = bool(current.get("vine")) or "vine customer review" in (
            block_text + " " + title_text + " " + body_text).lower()
        # The star line often lives inside the review-title anchor rather than
        # in a separate star element; the page still states the rating, so use
        # it from either place.
        rating = (_extract_rating(rating_text)
                  or _extract_rating(title_rating_text))
        raw = {
            "rating": rating,
            "date": _extract_date(date_text) or None,
            "date_text": date_text or None,
            "verified": True if current.get("verified") else False,
            "vine": vine,
            "title": _clean(title_text) or None,
            "text": _clean(body_text) or None,
            "helpful": _helpful_count(helpful_text),
            "variant": _clean(variant_text) or None,
            "_content": bool(current.get("_content")),
            "_partial": partial,
        }
        self.reviews.append(raw)
        if partial:
            self.partial_reviews += 1
        self._current = None
        self._in_review = False
        self._review_depth = 0

    # -- HTMLParser hooks --------------------------------------------------
    def handle_starttag(self, tag, attrs):
        attributes = {}
        for key, value in attrs or []:
            attributes[key.lower()] = value if value is not None else ""
        is_void = tag in VOID_TAGS
        if not is_void:
            self.depth += 1

        # Attributes that carry a fact on their own element.
        identifier = attributes.get("id", "")
        hook = attributes.get("data-hook", "")
        prop = attributes.get("property", "").lower()
        rel = attributes.get("rel", "").lower()
        if prop in ("og:title", "og:site_name") and attributes.get("content"):
            if prop == "og:title" and not self.listing["title"]:
                self.listing["title"] = _clean(attributes["content"])
                self.product_signals = True
        if tag == "link" and "canonical" in rel and attributes.get("href"):
            if not self.listing["canonical_url"]:
                self.listing["canonical_url"] = _clean(attributes["href"])
        if tag == "body" and attributes.get("data-asin"):
            if not self.listing["asin"]:
                self.listing["asin"] = _clean(attributes["data-asin"]).upper()
            self.product_signals = True
        if tag == "input" and identifier.upper() == "ASIN" and attributes.get("value"):
            if not self.listing["asin"]:
                self.listing["asin"] = _clean(attributes["value"]).upper()

        in_review = self._in_review
        if in_review:
            if hook in _REVIEW_HOOKS:
                field = _REVIEW_HOOKS[hook]
                if field in ("verified", "vine"):
                    # A badge is presence, and its own text is not needed; the
                    # capture keeps the text for the block search below.
                    self._current[field] = True
                    self._current["_content"] = True
                elif not self._field_open(field):
                    self._begin(field)
            return

        # Not in a review: listing hooks and the product-title element.
        if tag == "title":
            self._begin("doc_title")
        elif identifier == "productTitle":
            self._begin("listing_title")
            self.product_signals = True
        elif identifier == "acrPopover":
            if attributes.get("title"):
                self.listing["rating_text"] = _clean(attributes["title"])
            self.product_signals = True
        elif identifier == "acrCustomerReviewText":
            self._begin("rating_count")
            self.product_signals = True
        elif hook in _LISTING_HOOKS:
            field = _LISTING_HOOKS[hook]
            if not self._field_open(field):
                self._begin(field)
            self.product_signals = True
        elif identifier in ("averageCustomerReviews", "title"):
            self.product_signals = True

        if tag == "div" and (hook in ("review", "review-card")
                             or identifier.startswith("customer_review-")):
            self._start_review()

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in VOID_TAGS or self.depth <= 0:
            return
        while self.captures and self.captures[-1]["depth"] == self.depth:
            self._assign(self.captures.pop())
        if self._in_review and self.depth == self._review_depth:
            self._finish_review(partial=False)
        self.depth -= 1

    def handle_data(self, data):
        if not data:
            return
        for capture in self.captures:
            capture["chunks"].append(data)

    def close(self):
        super().close()
        # End of input can arrive in the middle of a tag or a review: keep what
        # was read, close captures in stack order and mark open reviews partial.
        while self.captures:
            self._assign(self.captures.pop())
        if self._in_review:
            self._finish_review(partial=True)
        self.depth = 0


def _looks_like_challenge(html: str) -> bool:
    lowered = html.lower()
    return any(marker in lowered for marker in _CHALLENGE_MARKERS)


def _finalise_listing(parser: _ProductPageParser, source_url):
    raw = parser.listing
    title = raw["title"] or (
        _title_from_doc(raw["doc_title"]) if parser.product_signals else "")
    rating_text = raw["rating_text"]
    rating = _extract_rating(rating_text)
    count = _extract_count(raw["rating_count_text"])
    url = _clean(source_url or "") or raw["canonical_url"] or None
    asin = raw["asin"] or ""
    if not asin and url:
        found = _ASIN_IN_URL.search(url)
        if found:
            asin = found.group(1).upper()
    return {
        "title": title or None,
        "star_rating": rating,
        "rating_count": count,
        "url": url,
        "asin": asin or None,
    }


def _records_from_raw(raw_reviews, warnings: list) -> list:
    """Route the parser's raw dicts through the ENGINE's own normaliser, so
    there is exactly one tolerant review schema in this project."""
    records = []
    empty = 0
    missing = {"rating": 0, "date": 0, "title": 0, "text": 0}
    for raw in raw_reviews:
        if not raw.get("_content"):
            empty += 1
            continue
        normalised = ENGINE.normalize_review(raw, index=len(records))
        normalised["date_text"] = raw.get("date_text")
        records.append(normalised)
        if normalised["rating"] is None:
            missing["rating"] += 1
        if normalised["date"] is None:
            missing["date"] += 1
        if not normalised["title"]:
            missing["title"] += 1
        if not normalised["text"]:
            missing["text"] += 1
    if empty:
        warnings.append(_warning(
            WARN_TRUNCATED_REVIEW,
            f"{empty} review block(s) ended before any of their fields could be read"))
    if any(missing.values()):
        warnings.append(_warning(
            WARN_MISSING_FIELDS,
            "some reviews did not show every field: "
            + ", ".join(f"{name} {value}" for name, value in missing.items() if value),
            **{name: value for name, value in missing.items() if value}))
    return records


def parse_product_page(html, *, source_url=None, captured_at=None) -> dict:
    """One product page's HTML -> listing facts, review records and warnings.

    `html` is the page as captured; a non-string is treated as an empty page
    rather than raising. `source_url` is what the browser window was on (the
    page itself may carry a canonical link as a fallback), and `captured_at` is
    passed through for the caller's own records. Nothing here mutates its
    inputs, dials out, or reads a file."""
    text = html if isinstance(html, str) else ""
    parser = _ProductPageParser()
    parser.feed(text)
    parser.close()
    listing = _finalise_listing(parser, source_url)
    warnings: list = []
    challenge = _looks_like_challenge(text)
    if challenge:
        warnings.append(_warning(
            WARN_CHALLENGE,
            "this page is a sign-in or challenge page, not a product page, so "
            "there are no reviews to read"))
    elif not parser.product_signals:
        warnings.append(_warning(
            WARN_NOT_PRODUCT,
            "this does not look like an Amazon product page: the product title, "
            "rating and review list were not found"))
    else:
        if not listing["title"]:
            warnings.append(_warning(WARN_TITLE, "the page did not show a product title"))
        if listing["star_rating"] is None:
            warnings.append(_warning(WARN_RATING,
                                     "the page did not show a star rating"))
        if listing["rating_count"] is None:
            warnings.append(_warning(WARN_RATING_COUNT,
                                     "the page did not show how many ratings there are"))
        if not parser.reviews:
            warnings.append(_warning(WARN_NO_REVIEWS,
                                     "the page did not show any reviews to read"))
    truncated = "<html" in text.lower() and "</html>" not in text.lower()
    if truncated:
        warnings.append(_warning(WARN_TRUNCATED,
                                 "the captured page is incomplete: it does not close, "
                                 "so later reviews may be missing"))
    if parser.partial_reviews:
        warnings.append(_warning(
            WARN_TRUNCATED_REVIEW,
            f"{parser.partial_reviews} review block(s) were still open when the "
            "capture ended; they were kept, but they may be missing their last fields"))
    records = _records_from_raw(parser.reviews, warnings)
    counts = {
        "review_blocks": len(parser.reviews),
        "reviews": len(records),
        "partial_blocks": parser.partial_reviews,
    }
    return {
        "engine": {"name": "jarvis_product_read", "version": VERSION,
                   "network": False, "read_only": True,
                   "capture": "owner's browser session (not fetched here)"},
        "source_url": source_url,
        "captured_at": captured_at,
        "listing": listing,
        "reviews": records,
        "warnings": warnings,
        "counts": counts,
    }


def assemble_report(html, *, source_url=None, captured_at=None, model=None) -> dict:
    """The whole convenience: page HTML -> engine report + the records used.

    Returns `{"report", "records", "listing", "warnings", "source_url",
    "captured_at", "parse"}`. `report` is the engine's own reasons-based report
    (caveat, signals, validated aspects, set-aside list, "not enough
    trustworthy data", what could not be checked) - this module does not
    reshape it. `records` is the debug half: exactly the review records the
    report was built from."""
    parsed = parse_product_page(html, source_url=source_url, captured_at=captured_at)
    listing = {}
    if parsed["listing"]["title"]:
        listing["title"] = parsed["listing"]["title"]
    if isinstance(parsed["listing"]["rating_count"], int):
        listing["review_count"] = parsed["listing"]["rating_count"]
    report = ENGINE.build_report(parsed["reviews"], listing=listing, model=model)
    return {
        "report": report,
        "records": parsed["reviews"],
        "listing": parsed["listing"],
        "warnings": parsed["warnings"],
        "source_url": source_url,
        "captured_at": captured_at,
        "parse": {"engine": parsed["engine"], "counts": parsed["counts"]},
    }
