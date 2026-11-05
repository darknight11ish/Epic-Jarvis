"""jarvis_source_independence.py - one editorial source, and who profits from it.

WHAT THIS ANSWERS, AND WHAT IT REFUSES TO SAY
A product check that counts star ratings trusts every source the same. This
module reads ONE supplied page - a review, a roundup article or a video page -
and shows the evidence a person needs to weigh that source: whether the page
says it is sponsored or gifted, whether its links carry affiliate or tracking
markers, and what words it uses to create urgency. It returns a small, CLOSED
verdict per source (`disclosed_sponsored` / `likely_monetised_undisclosed` /
`affiliate_only` / `no_monetisation_evidence` / `cannot_tell`) with the exact
evidence behind it.

There is **no trust score, no probability and no percentage** anywhere in this
module, and there is no per-review "fake/real" label. The design contract
(`docs/DESIGN-PRODUCT-RESEARCH.md`) explains why: a single number would hide
which rule fired and would invite over-trust, and a per-review authenticity
label would be false precision. Every answer here is a sentence plus the words
or links that produced it, and `cannot_tell` is a real, first-class answer: an
empty page, a page that needs JavaScript, or a page with too little text is
reported as unchecked, never guessed as clean.

WHAT IT READS (tolerantly, from synthetic page shapes only in the tests)
* **Disclosures** - sponsorship, advertisement, gift, paid-partnership,
  commission and "includes paid promotion" wording, each with the matched
  phrase, a short snippet and where it was found (the article text, the page
  title, a page description, a label/attribute, or the page's own data). An
  explicit paid-promotion flag in a video page's data is recognised too.
  Negated wording ("not sponsored") is kept separately as the page's own
  independence claim, never counted as a disclosure.
* **Links** - every `<a href>` is checked for affiliate markers (`tag=` on a
  shop address, `aff_id`, `affiliate`, `associate`, `partner`), tracking
  markers (UTM tags, click ids such as `fbclid`/`gclid`), known shorteners and
  redirect wrappers. Each example keeps the host, the matched parameter and a
  truncated address; a shortened or wrapped link's real destination is NOT
  resolved, because resolving it would mean opening it.
* **Urgency wording** - "last chance", "today only", "only 3 left" and a
  countdown timer next to urgency words. This is a pressure tactic, not
  evidence of payment, so it is reported beside the verdict and deliberately
  does not change it.
* **A plain "what could not be checked" list** - the payment that was never
  mentioned, the owner's own financial interest, what each link really points
  at, and what a video actually says out loud.

WHY A CLOSED VOCABULARY AND NOT A SCORE
The owner's own request (2026-11-04) was to weigh quality across independent
sources instead of trusting a star rating. That needs each source's conflict of
interest stated as evidence, and then a plain count of which sources say the
same thing. `rank_sources()` does exactly that: it puts the most independent
sources first and reports how many sources with no monetisation evidence made
the same claim, beside the monetised sources that made it. It prints counts of
sources, never a score or a fake percentage.

BORROWED PATTERNS, WITH CREDIT
The link marker vocabularies (the shortener list, UTM tags and click ids, and
the affiliate parameter names) and the fake-urgency phrase list are a
Python-native port of patterns from **dakidarts/dark-radar** (MIT). No
JavaScript is vendored and no dark-radar file is shipped; the credit and the
MIT text are in `THIRD-PARTY-NOTICES.txt`. The patterns added on top of that
list (affiliate-network addresses, redirect wrappers, the shop-tag shape) are
this module's own and are named in the same notice.

STANDARD LIBRARY ONLY: `re` and `html.parser`. No network, no socket, no
subprocess, no file read or write, no browser automation. Nothing imports this
module yet: no route, no chat tool, no approval card, no Settings row and no
app surface, exactly like the product engine's own slices.

    py -3 -B backend/test_source_independence.py
"""
from __future__ import annotations

import re
from html.parser import HTMLParser

VERSION = 1

#: The closed vocabulary. A caller may switch on these strings; no other value
#: is ever returned by `analyse_source()`, and `rank_sources()` replaces an
#: unknown verdict with `cannot_tell` rather than trusting it.
VERDICT_DISCLOSED_SPONSORED = "disclosed_sponsored"
VERDICT_LIKELY_UNDISCLOSED = "likely_monetised_undisclosed"
VERDICT_AFFILIATE_ONLY = "affiliate_only"
VERDICT_NO_EVIDENCE = "no_monetisation_evidence"
VERDICT_CANNOT_TELL = "cannot_tell"

VERDICTS = (
    VERDICT_DISCLOSED_SPONSORED,
    VERDICT_LIKELY_UNDISCLOSED,
    VERDICT_AFFILIATE_ONLY,
    VERDICT_NO_EVIDENCE,
    VERDICT_CANNOT_TELL,
)

KIND_ARTICLE = "article"
KIND_VIDEO = "video"
KIND_REVIEWS = "reviews"
KIND_UNKNOWN = "unknown"
KINDS = (KIND_ARTICLE, KIND_VIDEO, KIND_REVIEWS, KIND_UNKNOWN)

#: Fewer readable words than this is not enough to say "no evidence found":
#: an empty page and a page that only loads its text with JavaScript both land
#: here, and both are `cannot_tell`, never a clean result.
MIN_TEXT_WORDS = 40

#: A longer page is read only up to here, and the report says so.
MAX_HTML_CHARS = 500_000

SNIPPET_CHARS = 160
URL_SNIPPET_CHARS = 120
MAX_DISCLOSURES = 20
MAX_EXAMPLES = 5
MAX_URGENCY = 10

#: Surfaces, in the order their findings are reported: the visible text first,
#: the page's own data last (a video description often lives there).
WHERE_TEXT = "text"
WHERE_TITLE = "title"
WHERE_META = "meta"
WHERE_ATTRIBUTES = "attributes"
WHERE_PAGE_DATA = "page_data"
WHERE_LINK = "link"

#: A disclosure's own strength. Only explicit wording decides the verdict; a
#: contextual word ("commission" on its own, "discount code") is shown as
#: evidence but never turns into an accusation by itself.
EXPLICIT = "explicit"
CONTEXTUAL = "contextual"

#: Tags that never wrap content (so they never deepen the element stack).
VOID_TAGS = frozenset({
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
})

# ---------------------------------------------------------------------------
#  Wording that discloses a commercial relationship, or claims independence
# ---------------------------------------------------------------------------

#: (category, strength, label, pattern). ORDER MATTERS: at one starting point
#: the earlier rule wins after the longest match, so a specific phrase is
#: reported instead of its bare word. Rules are matched case-insensitively.
_DISCLOSURE_RULES = (
    # -- a sponsor of the content ------------------------------------------
    ("sponsor", EXPLICIT, "sponsored", r"\bsponsored\b"),
    ("sponsor", EXPLICIT, "sponsor", r"\bsponsors?\b"),
    ("sponsor", EXPLICIT, "paid post", r"\bpaid posts?\b"),
    ("sponsor", EXPLICIT, "paid article", r"\bpaid (?:article|content|feature)\b"),
    ("sponsor", EXPLICIT, "brought to you by", r"\bbrought to you by\b"),
    ("sponsor", EXPLICIT, "presented by our sponsor", r"\bpresented by our sponsor\b"),
    # -- an advertisement label --------------------------------------------
    ("advertisement", EXPLICIT, "advertisement", r"\badvertisements?\b"),
    ("advertisement", EXPLICIT, "advertorial", r"\badvertorials?\b"),
    ("advertisement", EXPLICIT, "advertising feature", r"\badvertising feature\b"),
    ("advertisement", EXPLICIT, "#ad", r"(?<![\w#])#ad(?![\w])"),
    ("advertisement", EXPLICIT, "promoted post", r"\bpromoted (?:post|content|article)\b"),
    # -- the product was given, not bought ---------------------------------
    ("gift", EXPLICIT, "gifted", r"\bgifted\b"),
    ("gift", EXPLICIT, "free product", r"\bfree products?\b"),
    ("gift", EXPLICIT, "product was provided", r"\b(?:product|unit|item|sample)s? (?:was|were) provided\b"),
    ("gift", EXPLICIT, "provided for free", r"\bprovided (?:to me |to us )?for free\b"),
    ("gift", EXPLICIT, "sent for free", r"\bsent (?:to me |to us )?for free\b"),
    ("gift", EXPLICIT, "received it for free", r"\breceived (?:this|the|it)\b.{0,40}\bfor free\b"),
    ("gift", EXPLICIT, "in exchange for a review", r"\bin exchange for (?:an? )?(?:honest )?(?:review|mention|video)\b"),
    ("gift", EXPLICIT, "press sample", r"\bpress samples?\b"),
    ("gift", EXPLICIT, "review sample", r"\breview samples?\b"),
    ("gift", EXPLICIT, "complimentary copy", r"\bcomplimentary cop(?:y|ies)\b"),
    ("gift", EXPLICIT, "on loan from", r"\bon loan from\b"),
    # -- a partnership -----------------------------------------------------
    ("partnership", EXPLICIT, "paid partnership", r"\bpaid partnership\b"),
    ("partnership", EXPLICIT, "in partnership with", r"\bin partnership with\b"),
    ("partnership", EXPLICIT, "partnered with", r"\bpartnered with\b"),
    ("partnership", EXPLICIT, "brand partner", r"\bbrand partners?\b"),
    ("partnership", EXPLICIT, "brand ambassador", r"\bbrand ambassadors?\b"),
    ("partnership", EXPLICIT, "ambassador for", r"\bambassador for\b"),
    # -- the paid-promotion label (a video's own wording) -------------------
    ("paid_promotion", EXPLICIT, "includes paid promotion", r"\bincludes? (?:a )?paid promotion\b"),
    ("paid_promotion", EXPLICIT, "paid promotion", r"\bpaid promotion\b"),
    ("paid_promotion", EXPLICIT, "contains paid promotion", r"\bcontains? (?:a )?paid promotion\b"),
    # -- an affiliate or commission disclosure -----------------------------
    ("affiliate", EXPLICIT, "affiliate link", r"\baffiliate links?\b"),
    ("affiliate", EXPLICIT, "affiliate", r"\baffiliates?\b"),
    ("affiliate", EXPLICIT, "we may earn a commission", r"\bwe (?:may |might )?earn (?:a )?commission\b"),
    ("affiliate", EXPLICIT, "earn a commission", r"\bearn(?:s|ed)? (?:a )?commission\b"),
    ("affiliate", EXPLICIT, "commission from qualifying purchases", r"\bcommission from qualifying purchases\b"),
    ("affiliate", EXPLICIT, "at no extra cost to you", r"\bat no extra cost to you\b"),
    # -- words that are only contextual, never a disclosure on their own ----
    ("affiliate", CONTEXTUAL, "commission", r"\bcommissions?\b"),
    ("affiliate", CONTEXTUAL, "discount code", r"\b(?:discount|promo|coupon) codes?\b"),
    ("gift", CONTEXTUAL, "gift", r"\bgifts?\b"),
)

def _compiled(rules):
    """(category, strength, label, compiled pattern) for one rule table."""
    return tuple((category, strength, label, re.compile(pattern, re.I))
                 for category, strength, label, pattern in rules)


_COMPILED_DISCLOSURES = _compiled(_DISCLOSURE_RULES)


#: Wording that claims the page is NOT paid. It is the page's own claim, not
#: proof: it is listed as evidence and never turns into "this source is clean".
_INDEPENDENCE_RULES = (
    ("not sponsored", r"\bnot sponsored\b"),
    ("no sponsorship", r"\bno sponsor(?:ship|s)?\b"),
    ("not an ad", r"\bnot an ad\b"),
    ("not a paid post", r"\bnot a paid (?:post|article|placement|promotion)\b"),
    ("unpaid", r"\bunpaid\b"),
    ("we paid for this", r"\bwe (?:paid for|bought) (?:this|it)\b"),
    ("bought with our own money", r"\b(?:bought|purchased) (?:this|it) (?:with|using) (?:our )?own (?:money|funds)\b"),
    ("no affiliate links", r"\bno affiliate links?\b"),
    ("not affiliated", r"\bnot affiliated\b"),
    ("no free products", r"\bno free (?:products?|samples?)\b"),
    ("self-funded", r"\bself[- ]funded\b"),
)

#: A video page's own data can carry the paid-promotion flag instead of the
#: visible label. Synthetic fixtures only in this repository; no real video
#: page has been read, which is why the report says where the match was found.
_PAID_PROMOTION_FLAGS = (
    (r'"paidPromotion"\s*:\s*true', "paidPromotion: true"),
    (r'"isPaidPromotion"\s*:\s*true', "isPaidPromotion: true"),
)

#: Urgency wording: a pressure tactic, reported beside the verdict and never
#: part of it. Ported from dark-radar's forced-urgency list (MIT).
_URGENCY_RULES = (
    ("last chance", r"\blast chance\b"),
    ("act now", r"\bact now\b"),
    ("don't miss", r"\bdon'?t miss\b"),
    ("limited time", r"\blimited[- ]time\b"),
    ("exclusive offer", r"\bexclusive offer\b"),
    ("today only", r"\btoday only\b"),
    ("expires soon", r"\bexpires? soon\b"),
    ("final hours", r"\bfinal hours\b"),
    ("selling fast", r"\bselling fast\b"),
    ("almost gone", r"\balmost gone\b"),
    ("only n left", r"\bonly \d+ (?:left|remaining)\b"),
    ("claim now", r"\bclaim now\b"),
    ("hurry", r"\bhurry\b"),
    ("ends today", r"\bends today\b"),
    ("while stocks last", r"\bwhile stocks last\b"),
)

#: A countdown timer is only reported when urgency wording is also present:
#: on its own "12:34" is a video length, not a pressure tactic. dark-radar's
#: fake-countdown rule is the same two-part test (MIT).
_COUNTDOWN = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\b")

# ---------------------------------------------------------------------------
#  Link markers (affiliate, tracking, shortened, redirect-wrapped)
# ---------------------------------------------------------------------------

#: The shortener list ported from dakidarts/dark-radar (MIT), plus a few of
#: the same shape added here. A short address hides where it really goes.
SHORTENER_HOSTS = (
    "bit.ly", "tinyurl.com", "goo.gl", "t.co", "ow.ly",
    "buff.ly", "adf.ly", "rebrand.ly", "short.link",
    "bit.do", "is.gd", "v.gd", "cutt.ly", "rb.gy", "tiny.cc",
    "lnkd.in", "t.ly", "shorturl.at", "bl.ink", "amzn.to",
)

#: Addresses that exist to carry an affiliate redirect. Recognising the
#: network is stronger evidence than a parameter name: the link is not even
#: pretending to be a plain address. Added here; not from dark-radar.
AFFILIATE_HOSTS = (
    "go.redirectingat.com", "redirectingat.com", "skimresources.com",
    "rstyle.me", "shop-links.co", "howl.me", "liketk.it", "shopmy.us",
    "shareasale.com", "shareasale-analytics.com",
    "awin1.com", "tidd.ly", "zenaps.com",
    "click.linksynergy.com",
    "anrdoezrs.net", "dpbolvw.net", "jdoqocy.com", "kqzyfj.com", "tkqlhce.com",
    "prf.hn", "partnerize.com",
    "sjv.io", "pxf.io", "ojrq.net",
    "viglink.com", "sovrn.co", "amzn.to",
)

#: Parameter names that pay the link's owner. `tag` is handled separately,
#: because it is only an affiliate tag on a shop address (or in the shape of a
#: shop's associate tag), not on any page with a `tag=recipes` category link.
AFFILIATE_KEYS = frozenset({
    "aff", "aff_id", "affid", "affiliate", "affiliate_id", "associate",
    "associate_id", "partner", "partner_id", "tag_id", "irclickid",
})

#: Plain tracking markers, ported from dark-radar (MIT) and extended here.
#: These record where a visitor came from; they do NOT show that anyone was
#: paid, so they never decide the verdict on their own.
TRACKING_KEYS = frozenset({
    "fbclid", "gclid", "msclkid", "yclid", "twclid", "ttclid", "igshid",
    "mc_cid", "mc_eid", "_hsenc", "_hsmi", "_ga", "_gl", "vero_id",
    "wickedid", "oly_anon_id", "ref", "ref_", "referrer", "source",
    "campaign", "campaignid",
})
TRACKING_PREFIXES = ("utm_",)

#: Query keys a redirect wrapper uses to carry the address it really opens.
REDIRECT_KEYS = frozenset({
    "url", "u", "target", "redirect", "redirect_url", "redirect_uri",
    "goto", "out", "dest", "destination", "link", "to",
})

#: An Amazon-style associate tag: a name followed by a two-digit account id.
AMAZON_TAG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*-\d{2}$")
AMAZON_HOST_HINTS = ("amazon.", "amzn.")

#: "http://", "https://" or protocol-relative - what a redirect wrapper wraps.
_WRAPPED_URL = re.compile(r"^(?:https?:)?//", re.I)

_URL_RE = re.compile(
    r"^(?:(?P<scheme>[A-Za-z][A-Za-z0-9+.\-]*):)?"
    r"(?://(?P<authority>[^/?#]*))?"
    r"(?P<path>[^?#]*)"
    r"(?:\?(?P<query>[^#]*))?"
    r"(?:#(?P<fragment>.*))?$",
    re.S,
)

_NEGATION_BEFORE = re.compile(
    r"(?:\bnot|\bno|\bnever|\bwithout|\bisn't|\bis not|\bwasn't|\bwas not|"
    r"\baren't|\bare not|\bnon)[\s\-]*$",
    re.I,
)

#: Words a page's own data may hold but its visible text does not. Only a video
#: page's data decides a verdict, because that is where a description lives;
#: on any other page a match there is shown with a caveat, never used to judge.
#: (The rule is applied in `_find_disclosures`, where `kind` is known.)


# ---------------------------------------------------------------------------
#  Small text helpers (ASCII only, no third-party module)
# ---------------------------------------------------------------------------

def _clean(text) -> str:
    """Whitespace collapsed to single spaces; anything not text becomes ""."""
    return " ".join(str(text or "").split())


def _truncate(text, cap: int = SNIPPET_CHARS) -> str:
    text = _clean(text)
    if len(text) <= cap:
        return text
    return text[:max(0, cap - 3)].rstrip() + "..."


def _words(text) -> int:
    return len(re.findall(r"\S+", _clean(text)))


def _snippet(text: str, start: int, end: int, cap: int = SNIPPET_CHARS) -> str:
    """A short window around one match, with "..." where it was cut."""
    left = max(0, start - 32)
    right = min(len(text), max(end, start) + 96)
    piece = text[left:right]
    if left > 0:
        piece = "..." + piece
    if right < len(text):
        piece = piece + "..."
    return _truncate(piece, cap)


def _percent_decode(text: str) -> str:
    """Decode %XX once. One pass on purpose: decoding twice hides the trick."""
    decoded = re.sub(r"%([0-9A-Fa-f]{2})", lambda m: chr(int(m.group(1), 16)),
                     text or "")
    return decoded.replace("+", " ")


def _host_of(host: str, candidates) -> str:
    """The first candidate this host is, or a subdomain of, else ""."""
    host = (host or "").lower().rstrip(".")
    for candidate in candidates:
        if host == candidate or host.endswith("." + candidate):
            return candidate
    return ""


def _is_amazon_host(host: str) -> bool:
    return any(hint in (host or "") for hint in AMAZON_HOST_HINTS)


def _normalise_kind(kind) -> str:
    """One of KINDS. Anything else is "unknown" rather than an error: a caller
    that has no kind should still get both halves of the check."""
    text = _clean(kind).lower()
    return text if text in KINDS else KIND_UNKNOWN


# ---------------------------------------------------------------------------
#  URL reading (no urllib: a link's address is text, not a fetch)
# ---------------------------------------------------------------------------

def _url_parts(href):
    """The pieces of one href, or None for a non-web address.

    A relative link (`/p/1?aff_id=2`) comes back with an empty host and
    `relative` True; a `mailto:`, `javascript:` or `data:` address comes back
    as None, because it is not a web page address at all.
    """
    text = _clean(href)
    if not text:
        return None
    found = _URL_RE.match(text)
    if not found:
        return None
    scheme = (found.group("scheme") or "").lower()
    authority = found.group("authority")
    path = found.group("path") or ""
    query = found.group("query") or ""
    if scheme and scheme not in ("http", "https"):
        return None
    if authority is None and scheme:
        # "http:example.com" is not a web address; a web one always has "//".
        return None
    if authority is None:
        return {"host": "", "path": path, "query": query, "relative": True}
    host = authority.rsplit("@", 1)[-1]
    if host.startswith("["):
        host = host.split("]")[0] + "]"
    elif ":" in host:
        host = host.rsplit(":", 1)[0]
    host = host.strip().lower().rstrip(".")
    return {"host": host, "path": path, "query": query, "relative": False}


def _query_pairs(query: str):
    """[(lower-case key, decoded value)] in the order they are written."""
    pairs = []
    for piece in re.split(r"[&;]", query or ""):
        if not piece:
            continue
        if "=" in piece:
            key, value = piece.split("=", 1)
        else:
            key, value = piece, ""
        key = _percent_decode(key).strip().lower()
        value = _percent_decode(value).strip()
        if key:
            pairs.append((key, value))
    return pairs


def _looks_like_wrapped_url(value: str) -> bool:
    return bool(_WRAPPED_URL.match((value or "").strip()))


def _wrapped_host(value: str):
    parts = _url_parts(value)
    return parts["host"] if parts and parts["host"] else None


def _affiliate_markers_in(url_text):
    """Affiliate markers inside an address a redirect wrapper carries.

    A wrapper such as `.../away?url=<a shop address with tag=...>` hides an
    affiliate link behind a plain-looking address; the address is already in
    the page, so reading it is not a fetch and needs no redirect followed.
    """
    parts = _url_parts(url_text)
    if parts is None:
        return []
    host = parts["host"]
    markers = []
    network = _host_of(host, AFFILIATE_HOSTS)
    if network:
        markers.append({
            "parameter": "", "value": host, "class": "affiliate",
            "why": f"the wrapped address is a known affiliate redirect ({network})",
        })
    for key, value in _query_pairs(parts["query"]):
        if key == "tag" and (_is_amazon_host(host) or AMAZON_TAG.match(value)):
            markers.append({
                "parameter": key, "value": value, "class": "affiliate",
                "why": "the wrapped address carries a shop associate tag",
            })
        elif key in AFFILIATE_KEYS:
            markers.append({
                "parameter": key, "value": value, "class": "affiliate",
                "why": "the wrapped address names an affiliate or partner",
            })
    return markers


def _link_markers(href, source_host=""):
    """One link's markers, or None when it carries none.

    The returned dict names the strongest marker's class, keeps every matched
    parameter, and carries the wrapped destination's host when the link is a
    redirect (it is named, never opened).
    """
    parts = _url_parts(href)
    if parts is None:
        return None
    host = parts["host"] or (_clean(source_host) if parts["relative"] else "")
    markers = []

    network = _host_of(host, AFFILIATE_HOSTS)
    if network:
        markers.append({
            "parameter": "", "value": host, "class": "affiliate",
            "why": f"a known affiliate redirect address ({network})",
        })

    wrapped_host = None
    for key, value in _query_pairs(parts["query"]):
        if key == "tag" and (_is_amazon_host(host) or AMAZON_TAG.match(value)):
            markers.append({
                "parameter": key, "value": value, "class": "affiliate",
                "why": "a shop associate tag that pays the link's owner",
            })
        elif key in AFFILIATE_KEYS:
            markers.append({
                "parameter": key, "value": value, "class": "affiliate",
                "why": "a parameter that names an affiliate or partner",
            })
        elif key.startswith(TRACKING_PREFIXES) or key in TRACKING_KEYS:
            markers.append({
                "parameter": key, "value": value, "class": "tracking",
                "why": "a tracking marker that records where a visitor came from",
            })
        elif key in REDIRECT_KEYS and _looks_like_wrapped_url(value):
            markers.append({
                "parameter": key, "value": value, "class": "redirect_wrapper",
                "why": "a redirect wrapper: this link opens another address",
            })
            wrapped_host = wrapped_host or _wrapped_host(value)
            markers.extend(_affiliate_markers_in(value))
        elif (key == "q" and "redirect" in parts["path"].lower()
              and _looks_like_wrapped_url(value)):
            markers.append({
                "parameter": key, "value": value, "class": "redirect_wrapper",
                "why": "a redirect wrapper: this link opens another address",
            })
            wrapped_host = wrapped_host or _wrapped_host(value)
            markers.extend(_affiliate_markers_in(value))

    shortener = _host_of(host, SHORTENER_HOSTS)
    if shortener:
        markers.append({
            "parameter": "", "value": host, "class": "shortener",
            "why": f"a shortened address ({shortener}): where it goes is hidden",
        })

    if not markers:
        return None
    priority = {"affiliate": 3, "redirect_wrapper": 2, "shortener": 1,
                "tracking": 0}
    primary = max(markers, key=lambda marker: priority[marker["class"]])
    return {
        "host": host or None,
        "class": primary["class"],
        "parameter": primary["parameter"] or None,
        "marker": _truncate(primary["value"], 80) or None,
        "why": primary["why"],
        "markers": markers[:6],
        "wraps": wrapped_host,
    }


# ---------------------------------------------------------------------------
#  One tolerant HTML pass
# ---------------------------------------------------------------------------

def _where_words(where: str) -> str:
    """A plain-words name for one surface, for evidence sentences."""
    return {
        WHERE_TEXT: "in the article text",
        WHERE_TITLE: "in the page title",
        WHERE_META: "in a page description",
        WHERE_ATTRIBUTES: "in a page label or image description",
        WHERE_PAGE_DATA: "in the page's own data",
        WHERE_LINK: "on a link",
    }.get(where, "on the page")


class _SourceParser(HTMLParser):
    """One tolerant pass over a page's HTML.

    It keeps the visible text, the page title, page descriptions, label and
    image attributes, the page's script text (a video description lives there)
    and every link with its own words. Malformed markup cannot make it raise:
    the element stack is tracked by hand and whatever was collected is kept.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.script_depth = 0
        self.style_depth = 0
        self.title_depth = 0
        self.anchor = None
        self.text = []
        self.title = []
        self.scripts = []
        self.meta = []
        self.attributes = []
        self.links = []
        self.sponsored_links = []
        self.broken = False

    # -- capture helpers ---------------------------------------------------
    def _finish_anchor(self) -> None:
        anchor = self.anchor
        self.anchor = None
        if not anchor:
            return
        href = _clean(anchor["href"])
        words = _close_join(anchor["text"])
        if not href or href.startswith("#"):
            return
        self.links.append({"href": href, "text": words, "rel": anchor["rel"]})

    # -- HTMLParser hooks --------------------------------------------------
    def handle_starttag(self, tag, attrs):
        attributes = {}
        for key, value in attrs or []:
            attributes[key.lower()] = value if value is not None else ""
        is_void = tag in VOID_TAGS
        if not is_void:
            self.depth += 1

        if tag == "title":
            self.title_depth = self.depth
        elif tag == "script":
            if not self.script_depth:
                self.script_depth = self.depth
        elif tag == "style":
            if not self.style_depth:
                self.style_depth = self.depth
        elif tag == "meta":
            name = (attributes.get("name") or attributes.get("property")
                    or attributes.get("itemprop") or "").strip()
            content = attributes.get("content") or ""
            if content:
                self.meta.append((name + " " + content).strip())
        elif tag == "a":
            rel = attributes.get("rel", "").lower()
            if self.anchor is None:
                self.anchor = {"href": attributes.get("href", ""),
                               "text": [], "rel": rel, "depth": self.depth}
            if "sponsored" in rel.split():
                self.sponsored_links.append({
                    "href": _clean(attributes.get("href")),
                    "rel": rel,
                })
        for name in ("title", "aria-label", "alt", "data-ad-label"):
            value = attributes.get(name) or ""
            if value:
                self.attributes.append(value)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in VOID_TAGS or self.depth <= 0:
            return
        if tag == "a" and self.anchor is not None and self.depth == self.anchor["depth"]:
            self._finish_anchor()
        if tag == "script" and self.script_depth == self.depth:
            self.script_depth = 0
        if tag == "style" and self.style_depth == self.depth:
            self.style_depth = 0
        if tag == "title" and self.title_depth == self.depth:
            self.title_depth = 0
        self.depth -= 1

    def handle_data(self, data):
        if not data:
            return
        if self.script_depth:
            self.scripts.append(data)
            return
        if self.style_depth:
            return
        if self.title_depth:
            # The tab title is its own surface: it is not article text, and
            # counting it twice would report one disclosure in two places.
            self.title.append(data)
            return
        self.text.append(data)
        if self.anchor is not None:
            self.anchor["text"].append(data)

    def close(self):
        super().close()
        if self.anchor is not None:
            self._finish_anchor()
        self.script_depth = 0
        self.style_depth = 0
        self.title_depth = 0
        self.depth = 0


def _close_join(chunks) -> str:
    return _clean(" ".join(str(chunk) for chunk in chunks if chunk))


def _surfaces(parser: _SourceParser):
    """[(where, text)] in reporting order, empty surfaces left out."""
    out = []
    candidates = (
        (WHERE_TEXT, _close_join(parser.text)),
        (WHERE_TITLE, _close_join(parser.title)),
        (WHERE_META, _close_join(parser.meta)),
        (WHERE_ATTRIBUTES, _close_join(parser.attributes)),
        (WHERE_PAGE_DATA, _close_join(parser.scripts)),
    )
    for where, text in candidates:
        if text:
            out.append((where, text))
    return out


# ---------------------------------------------------------------------------
#  Wording: disclosures, independence claims, urgency
# ---------------------------------------------------------------------------

def _negated_before(text: str, start: int) -> bool:
    before = text[max(0, start - 24):start].lower()
    return bool(_NEGATION_BEFORE.search(before))


def _first_matches(text: str, rules):
    """One match per overlapping span, ordered by where it starts.

    The longest match at a point wins, then the earlier rule, so "affiliate
    link" is reported instead of just "affiliate". Negation is NOT decided
    here - the caller checks each match's own sentence, so "not sponsored" can
    be filed as the page's claim rather than as a disclosure.
    """
    found = []
    for order, (_, _, _, pattern) in enumerate(rules):
        for match in pattern.finditer(text):
            phrase = match.group(0).strip()
            if not phrase:
                continue
            found.append((match.start(), match.end(), order, phrase))
    found.sort(key=lambda item: (item[0], -(item[1] - item[0]), item[2]))
    kept, spans = [], []
    for start, end, order, phrase in found:
        if any(start < span_end and end > span_start for span_start, span_end in spans):
            continue
        spans.append((start, end))
        kept.append((start, end, order, phrase))
    return kept


def _find_disclosures(surfaces, kind: str):
    """(disclosures, independence_claims, notes) from every surface."""
    disclosures = []
    claims = []
    notes = []
    seen = set()
    for where, text in surfaces:
        for start, end, order, phrase in _first_matches(text, _COMPILED_DISCLOSURES):
            category, strength, _, _ = _COMPILED_DISCLOSURES[order]
            snippet = _snippet(text, start, end)
            if _negated_before(text, start):
                claims.append({
                    "phrase": phrase, "snippet": snippet, "where": where,
                    "kind": "the page's own words deny it",
                })
                continue
            key = (where, category, _clean(snippet).lower())
            if key in seen:
                continue
            seen.add(key)
            disclosures.append({
                "phrase": phrase,
                "category": category,
                "strength": strength,
                "where": where,
                "snippet": snippet,
                "decides": strength == EXPLICIT and (
                    where != WHERE_PAGE_DATA or kind == KIND_VIDEO),
            })
        for phrase, pattern in _INDEPENDENCE_RULES:
            for match in re.finditer(pattern, text, re.I):
                snippet = _snippet(text, match.start(), match.end())
                key = ("claim", where, _clean(snippet).lower())
                if key in seen:
                    continue
                seen.add(key)
                claims.append({
                    "phrase": match.group(0).strip(), "snippet": snippet,
                    "where": where, "kind": "the page says it was not paid",
                })

    # A video's own data may carry the flag instead of the visible label.
    for where, text in surfaces:
        if where != WHERE_PAGE_DATA:
            continue
        for pattern, label in _PAID_PROMOTION_FLAGS:
            for match in re.finditer(pattern, text, re.I):
                key = (where, "paid_promotion", label)
                if key in seen:
                    continue
                seen.add(key)
                disclosures.append({
                    "phrase": label,
                    "category": "paid_promotion",
                    "strength": EXPLICIT,
                    "where": where,
                    "snippet": _snippet(text, match.start(), match.end()),
                    "decides": kind == KIND_VIDEO,
                })

    if len(disclosures) > MAX_DISCLOSURES:
        notes.append(
            f"Only the first {MAX_DISCLOSURES} disclosure matches are shown; "
            f"{len(disclosures) - MAX_DISCLOSURES} more were found.")
        disclosures = disclosures[:MAX_DISCLOSURES]
    if kind != KIND_VIDEO and any(d["where"] == WHERE_PAGE_DATA for d in disclosures):
        notes.append(
            "Wording was found inside the page's own data but not in its "
            "visible text. On a page that is not a video that can be code "
            "rather than a disclosure, so it did not decide this answer.")
    return disclosures, claims, notes


def _find_urgency(text: str):
    """Urgency phrases, plus the two-part countdown test."""
    phrases = []
    spans = []
    for label, pattern in _URGENCY_RULES:
        for match in re.finditer(pattern, text, re.I):
            if any(match.start() < end and match.end() > start
                   for start, end in spans):
                continue
            spans.append((match.start(), match.end()))
            phrases.append({
                "phrase": match.group(0).strip(),
                "label": label,
                "where": WHERE_TEXT,
                "snippet": _snippet(text, match.start(), match.end()),
            })
            if len(phrases) >= MAX_URGENCY:
                break
        if len(phrases) >= MAX_URGENCY:
            break
    countdown = _COUNTDOWN.search(text)
    if countdown and phrases:
        phrases.append({
            "phrase": countdown.group(0),
            "label": "countdown timer with urgency wording",
            "where": WHERE_TEXT,
            "snippet": _snippet(text, countdown.start(), countdown.end()),
        })
    return phrases[:MAX_URGENCY]


# ---------------------------------------------------------------------------
#  The per-source verdict
# ---------------------------------------------------------------------------

def _verdict_of(disclosures, affiliate_links, words: int) -> str:
    """The closed verdict, strongest evidence first. Never a score."""
    deciding = [d for d in disclosures if d["decides"]]
    sponsor = [d for d in deciding if d["category"] != "affiliate"]
    affiliate = [d for d in deciding if d["category"] == "affiliate"]
    strong_links = [link for link in affiliate_links if link["class"] == "affiliate"]
    if sponsor:
        return VERDICT_DISCLOSED_SPONSORED
    if affiliate:
        return VERDICT_AFFILIATE_ONLY
    if strong_links:
        return VERDICT_LIKELY_UNDISCLOSED
    if words < MIN_TEXT_WORDS:
        return VERDICT_CANNOT_TELL
    return VERDICT_NO_EVIDENCE


def _verdict_evidence(verdict, disclosures, affiliate_links, claims, words,
                      link_count):
    """Plain sentences: what was found, in the order that decided it."""
    lines = []
    deciding = [d for d in disclosures if d["decides"]]
    contextual = [d for d in disclosures if not d["decides"]]
    strong_links = [link for link in affiliate_links if link["class"] == "affiliate"]
    sponsor = [d for d in deciding if d["category"] != "affiliate"]
    affiliate = [d for d in deciding if d["category"] == "affiliate"]

    if sponsor:
        for item in sponsor[:3]:
            lines.append(
                f"The page says \"{item['phrase']}\" {_where_words(item['where'])}: "
                f"\"{item['snippet']}\".")
    if affiliate:
        for item in affiliate[:2]:
            lines.append(
                f"The page discloses an affiliate or commission relationship "
                f"(\"{item['phrase']}\", {_where_words(item['where'])}).")
    if strong_links:
        first = strong_links[0]
        where = first["host"] or "this site"
        marker = first["marker"] or "a marker"
        lines.append(
            f"{len(strong_links)} link(s) carry an affiliate marker; the first "
            f"is {marker!r} on {where}.")
    if verdict == VERDICT_LIKELY_UNDISCLOSED:
        lines.append(
            "No disclosure of that relationship was found in the page's "
            "visible text.")
    if verdict == VERDICT_NO_EVIDENCE:
        lines.append(
            f"No disclosure wording and no affiliate markers were found in "
            f"{words} word(s) of readable text.")
    if verdict == VERDICT_CANNOT_TELL:
        if not words:
            lines.append("The page had no readable text at all.")
        elif link_count == 0:
            lines.append(
                f"Only {words} word(s) of readable text were found, and no "
                f"link; that is too little to check.")
        else:
            lines.append(
                f"Only {words} word(s) of readable text were found; that is "
                f"too little to check.")
    if contextual:
        first = contextual[0]
        if first["strength"] == CONTEXTUAL:
            lines.append(
                f"The page uses \"{first['phrase']}\", but that word alone "
                f"does not say money changed hands.")
        else:
            lines.append(
                f"The page's own data carries \"{first['phrase']}\" "
                f"({_where_words(first['where'])}), but that was not in its "
                f"visible words, so it did not decide this answer.")
    for item in claims[:2]:
        lines.append(
            f"The page's own words claim independence: \"{item['snippet']}\". "
            f"That is the page's claim, not proof.")
    if not lines:
        lines.append("Nothing on the page decided this answer.")
    return lines


def _verdict_why(verdict: str) -> str:
    return {
        VERDICT_DISCLOSED_SPONSORED:
            "The page itself says the content is paid, sponsored or gifted.",
        VERDICT_LIKELY_UNDISCLOSED:
            "The page carries affiliate markers but does not disclose that "
            "it earns from them.",
        VERDICT_AFFILIATE_ONLY:
            "The page earns a commission from its links and says so; no "
            "sponsorship of the content itself was found.",
        VERDICT_NO_EVIDENCE:
            "No disclosure wording and no affiliate markers were found in "
            "the readable text.",
        VERDICT_CANNOT_TELL:
            "There was not enough readable text to check, so no answer is "
            "guessed.",
    }[verdict]


def _verdict_would_change(verdict: str):
    return {
        VERDICT_DISCLOSED_SPONSORED: [
            "Nothing on this page would change it: the disclosure is the "
            "evidence.",
            "A page that drops the disclosure would look independent here; "
            "this check only reads the copy it is given.",
        ],
        VERDICT_LIKELY_UNDISCLOSED: [
            "A commission or sponsorship disclosure would show the "
            "relationship is disclosed.",
            "Removing the affiliate markers would remove this evidence.",
        ],
        VERDICT_AFFILIATE_ONLY: [
            "A sponsorship disclosure would make this disclosed_sponsored.",
            "A page with the commission wording removed would look "
            "independent unless its links still carry affiliate markers.",
        ],
        VERDICT_NO_EVIDENCE: [
            "A link that turns out to be an affiliate link when opened would "
            "add evidence this page does not show.",
            "A disclosure that only appears on a linked page is not seen "
            "here.",
        ],
        VERDICT_CANNOT_TELL: [
            "A capture that includes the article text, rather than a page "
            "that needs JavaScript or a sign-in, would let the wording be "
            "checked.",
            "A page with a disclosure or an affiliate link would show "
            "evidence even when the rest is unreadable.",
        ],
    }[verdict]


def _monetisation_summary(verdict, disclosures, affiliate_links, words):
    """One plain sentence naming the strongest evidence, never a number."""
    deciding = [d for d in disclosures if d["decides"]]
    sponsor = [d for d in deciding if d["category"] != "affiliate"]
    affiliate = [d for d in deciding if d["category"] == "affiliate"]
    strong_links = [link for link in affiliate_links if link["class"] == "affiliate"]
    if sponsor:
        item = sponsor[0]
        return (f"The page says \"{item['phrase']}\" "
                f"{_where_words(item['where'])}: \"{item['snippet']}\".")
    if affiliate:
        if strong_links:
            return (f"The page says it earns a commission "
                    f"(\"{affiliate[0]['phrase']}\"), and "
                    f"{len(strong_links)} link(s) carry an affiliate marker.")
        return (f"The page says it earns a commission "
                f"(\"{affiliate[0]['phrase']}\"); no affiliate marker was "
                f"found in its links, so the wording itself is the evidence.")
    if strong_links:
        first = strong_links[0]
        return (f"No disclosure was found, but {len(strong_links)} link(s) "
                f"carry an affiliate marker (first: {first['marker']!r} on "
                f"{first['host'] or 'this site'}), so the page can profit "
                f"from a sale without saying so.")
    if verdict == VERDICT_CANNOT_TELL:
        return (f"Only {words} word(s) of readable text were found, so this "
                f"page could not be checked.")
    contextual = [d for d in disclosures
                  if not d["decides"] and d["strength"] == CONTEXTUAL]
    if contextual:
        return (f"No disclosure was found; the page uses "
                f"\"{contextual[0]['phrase']}\", which does not say money "
                f"changed hands.")
    in_data = [d for d in disclosures
               if not d["decides"] and d["where"] == WHERE_PAGE_DATA]
    if in_data:
        return (f"No visible disclosure was found; the page's own data "
                f"contains \"{in_data[0]['phrase']}\", which did not decide "
                f"this answer.")
    return (f"No disclosure wording and no affiliate markers were found in "
            f"{words} word(s) of readable text.")


def _could_not_check(verdict, affiliate_links, claims, disclosures, kind,
                     words, link_count, truncated, parse_broken):
    """Fixed honest limits, then the ones this particular page earned."""
    lines = [
        "Whether money or a free product changed hands without being "
        "mentioned: a payment the page does not state cannot be seen here.",
        "Whether the writer, their employer or the site's owner has a "
        "financial interest the page does not state.",
    ]
    if link_count:
        lines.append(
            "What each link really opens: no link was opened or fetched, so "
            "a commission behind it is not verified.")
    if kind == KIND_VIDEO:
        lines.append(
            "What the video says out loud: only the page's title, text and "
            "data were read, because no video or audio was played or "
            "transcribed.")
    elif kind == KIND_REVIEWS:
        lines.append(
            "Whether the reviewers were given the product: only the page's "
            "own wording was read, not a reviewer's account or order history.")
    elif kind == KIND_ARTICLE:
        lines.append(
            "Whether the publication was paid for the article outside its "
            "own wording: a payment that was never disclosed cannot be seen.")
    else:
        lines.append(
            "What kind of source this is: no kind was given, so the same "
            "wording and link checks were used for an article, a video and a "
            "review page.")
    masked = [link for link in affiliate_links
              if link["class"] in ("shortener", "redirect_wrapper")]
    if masked:
        lines.append(
            f"{len(masked)} link(s) are shortened or wrapped in a redirect, "
            f"so their real destination could not be resolved without "
            f"opening them.")
    if any(link["class"] == "tracking" for link in affiliate_links):
        lines.append(
            "Plain tracking markers (UTM tags and click ids) were found; "
            "they record where a visitor came from, which is not evidence of "
            "payment, so they were not counted as monetisation.")
    contextual = [d for d in disclosures
                  if d["strength"] == CONTEXTUAL and not d["decides"]]
    if contextual and verdict == VERDICT_NO_EVIDENCE:
        lines.append(
            f"The word \"{contextual[0]['phrase']}\" appears, but the page "
            f"does not say money changed hands because of it, so it was not "
            f"counted as a disclosure.")
    if claims:
        lines.append(
            "Whether the page's claim that it was not paid is true: that is "
            "the page's own word, and nothing here checks it.")
    if truncated:
        lines.append(
            f"The page was longer than {MAX_HTML_CHARS} characters; only the "
            f"first part was read.")
    if parse_broken:
        lines.append(
            "The page's markup was damaged enough that the reader stopped "
            "early; whatever it had collected was used.")
    if verdict == VERDICT_CANNOT_TELL:
        lines.append(
            "The page did not contain readable article text: it may need "
            "JavaScript, or be a sign-in, block or error page.")
    if link_count == 0:
        lines.append(
            "The page had no links at all, so a link-based conflict of "
            "interest could not be seen even if one exists.")
    return lines


# ---------------------------------------------------------------------------
#  The public entry point
# ---------------------------------------------------------------------------

def analyse_source(html, url=None, kind=KIND_UNKNOWN) -> dict:
    """One supplied page -> the evidence about who profits from it.

    `html` is the page as a string (anything else is treated as an empty page,
    never an error), `url` is where it came from (kept for display, and never
    fetched), and `kind` is one of KINDS (anything else becomes "unknown").
    The return value is JSON-able and deterministic: same input, same output,
    and nothing in it is mutated. There is no score, no probability and no
    percentage anywhere in the result.
    """
    text = html if isinstance(html, str) else ""
    truncated = len(text) > MAX_HTML_CHARS
    if truncated:
        text = text[:MAX_HTML_CHARS]
    kind = _normalise_kind(kind)
    source_url = _clean(url) or None
    source_host = ""
    if source_url:
        parts = _url_parts(source_url)
        if parts:
            source_host = parts["host"]

    parser = _SourceParser()
    try:
        parser.feed(text)
        parser.close()
    except Exception:                       # noqa: BLE001 - tolerance, never a raise
        parser.broken = True

    surfaces = _surfaces(parser)
    visible = dict(surfaces).get(WHERE_TEXT, "")
    words = _words(visible)
    disclosures, claims, notes = _find_disclosures(surfaces, kind)

    # A `rel="sponsored"` link is the page declaring a paid placement, even
    # when the words around it say nothing. The same cap as the wording
    # matches keeps a page with hundreds of such links from flooding the list.
    for item in parser.sponsored_links:
        if len(disclosures) >= MAX_DISCLOSURES:
            break
        disclosures.append({
            "phrase": 'rel="sponsored"',
            "category": "sponsor",
            "strength": EXPLICIT,
            "where": WHERE_LINK,
            "snippet": _truncate(item["href"], URL_SNIPPET_CHARS) or "a link",
            "decides": True,
        })

    affiliate_links = []
    for link in parser.links:
        found = _link_markers(link["href"], source_host)
        if not found:
            continue
        found["url"] = _truncate(link["href"], URL_SNIPPET_CHARS)
        found["text"] = _truncate(link["text"], 80) or None
        affiliate_links.append(found)

    urgency = _find_urgency(visible)
    verdict = _verdict_of(disclosures, affiliate_links, words)
    affiliate_count = sum(1 for link in affiliate_links
                          if link["class"] == "affiliate")
    masked_count = sum(1 for link in affiliate_links
                       if link["class"] in ("shortener", "redirect_wrapper"))
    tracking_count = sum(1 for link in affiliate_links
                         if link["class"] == "tracking")

    could_not = _could_not_check(
        verdict, affiliate_links, claims, disclosures, kind, words,
        len(parser.links), truncated, parser.broken)
    could_not.extend(notes)

    categories = {}
    for item in disclosures:
        categories[item["category"]] = categories.get(item["category"], 0) + 1
    explicit = [d for d in disclosures if d["decides"]]
    contextual = [d for d in disclosures if not d["decides"]]
    strongest = None
    if explicit:
        item = explicit[0]
        strongest = {"kind": "disclosure", "category": item["category"],
                     "phrase": item["phrase"], "where": item["where"]}
    elif affiliate_count:
        item = next(link for link in affiliate_links
                    if link["class"] == "affiliate")
        strongest = {"kind": "affiliate_link", "category": "affiliate",
                     "phrase": item["marker"], "where": "link",
                     "host": item["host"]}
    elif contextual:
        item = contextual[0]
        strongest = {"kind": "contextual_wording",
                     "category": item["category"], "phrase": item["phrase"],
                     "where": item["where"]}
    elif verdict == VERDICT_CANNOT_TELL:
        strongest = {"kind": "unreadable", "category": None, "phrase": None,
                     "where": None}
    else:
        strongest = {"kind": "none", "category": None, "phrase": None,
                     "where": None}

    return {
        "engine": {"name": "jarvis_source_independence", "version": VERSION,
                   "network": False, "read_only": True},
        "source": {
            "url": source_url,
            "host": source_host or None,
            "kind": kind,
            "kinds": list(KINDS),
            "title": _truncate(dict(surfaces).get(WHERE_TITLE), 200) or None,
            "text_words": words,
            "links": len(parser.links),
            "truncated": truncated,
        },
        "disclosures": disclosures,
        "independence_claims": claims,
        "affiliate_links": {
            "count": len(affiliate_links),
            "affiliate_count": affiliate_count,
            "tracking_count": tracking_count,
            "masked_count": masked_count,
            "links_seen": len(parser.links),
            "examples": affiliate_links[:MAX_EXAMPLES],
            "by_class": {
                "affiliate": affiliate_count,
                "tracking": tracking_count,
                "shortener": sum(1 for link in affiliate_links
                                 if link["class"] == "shortener"),
                "redirect_wrapper": sum(1 for link in affiliate_links
                                        if link["class"] == "redirect_wrapper"),
            },
        },
        "urgency": {
            "count": len(urgency),
            "phrases": urgency,
            "note": ("Urgency wording is a pressure tactic, not evidence of "
                     "payment, so it does not change the verdict."),
        },
        "monetisation": {
            "summary": _monetisation_summary(
                verdict, disclosures, affiliate_links, words),
            "strongest": strongest,
            "categories": categories,
            "disclosures": len(disclosures),
            "affiliate_links": affiliate_count,
            "shortened_or_wrapped_links": masked_count,
            "tracking_only_links": tracking_count,
        },
        "per_source_verdict": {
            "verdict": verdict,
            "closed_vocabulary": list(VERDICTS),
            "evidence": _verdict_evidence(
                verdict, disclosures, affiliate_links, claims, words,
                len(parser.links)),
            "why": _verdict_why(verdict),
            "would_change": _verdict_would_change(verdict),
        },
        "what_could_not_be_checked": could_not,
        "counts": {
            "links": len(parser.links),
            "disclosures": len(disclosures),
            "explicit_disclosures": len(explicit),
            "contextual_disclosures": len(contextual),
            "independence_claims": len(claims),
            "affiliate_links": affiliate_count,
            "masked_links": masked_count,
            "tracking_links": tracking_count,
            "urgency_phrases": len(urgency),
            "text_words": words,
        },
    }


# ---------------------------------------------------------------------------
#  Ranking sources, and the plain-words agreement summary
# ---------------------------------------------------------------------------

#: Most independent first. A source that could not be read is NOT assumed
#: independent, so it sits below the ones that could be read; the ones we can
#: see are monetised sit below it. Nothing here is a number about a source's
#: quality - it is only where its evidence puts it.
_INDEPENDENCE_ORDER = {
    VERDICT_NO_EVIDENCE: 0,
    VERDICT_AFFILIATE_ONLY: 1,
    VERDICT_CANNOT_TELL: 2,
    VERDICT_LIKELY_UNDISCLOSED: 3,
    VERDICT_DISCLOSED_SPONSORED: 4,
}

_MONETISED_VERDICTS = (
    VERDICT_AFFILIATE_ONLY,
    VERDICT_LIKELY_UNDISCLOSED,
    VERDICT_DISCLOSED_SPONSORED,
)


def _claim_key(text) -> str:
    """A claim's comparison key: its words, lower-cased, with the ends tidied.

    Two sources agree only when they wrote the same claim; this deliberately
    does not try to understand meaning, and the note returned with the summary
    says so.
    """
    text = _clean(text).lower()
    text = text.strip(" .,;:!?\"'()[]")
    return " ".join(text.split())


def _analysis_of(record) -> dict:
    """The analysis for one source record, run here when it was not supplied."""
    analysis = record.get("analysis")
    if isinstance(analysis, dict) and isinstance(analysis.get("per_source_verdict"), dict):
        return analysis
    return analyse_source(record.get("html", ""), record.get("url"),
                          record.get("kind", KIND_UNKNOWN))


def _verdict_of_analysis(analysis) -> str:
    value = analysis.get("per_source_verdict", {}).get("verdict")
    return value if value in VERDICTS else VERDICT_CANNOT_TELL


def rank_sources(sources) -> dict:
    """Order the most independent sources first, then say what they agree on.

    Each entry in `sources` is a dict that may carry `url`, `kind`, `claim`
    (the thing the source said, one sentence) and either `html` (analysed here)
    or `analysis` (the result of `analyse_source()`). Anything else is read as
    an empty source and reported as `cannot_tell`; nothing raises.

    The answer counts sources, never a score: how many sources with no
    monetisation evidence made a given claim, beside the monetised sources that
    made it. Claims are compared word for word after normalising case and
    spacing, and the note says that, because two sources agreeing in different
    words is not something this module can prove.
    """
    records = []
    if not isinstance(sources, (list, tuple)):
        sources = []
    for index, raw in enumerate(sources):
        record = raw if isinstance(raw, dict) else {}
        analysis = _analysis_of(record)
        verdict = _verdict_of_analysis(analysis)
        source = analysis.get("source") if isinstance(analysis.get("source"), dict) else {}
        claim = _clean(record.get("claim") or record.get("says") or "")
        records.append({
            "index": index,
            "url": source.get("url") or _clean(record.get("url")) or None,
            "kind": source.get("kind", KIND_UNKNOWN),
            "claim": claim,
            "claim_key": _claim_key(claim),
            "verdict": verdict,
            "summary": (analysis.get("monetisation", {}).get("summary") or ""),
            "disclosures": len(analysis.get("disclosures") or []),
            "affiliate_links": (analysis.get("affiliate_links", {}).get("count") or 0),
        })

    order = sorted(range(len(records)),
                   key=lambda i: (_INDEPENDENCE_ORDER[records[i]["verdict"]], i))
    ranked = []
    for position, index in enumerate(order):
        item = dict(records[index])
        item["rank"] = position + 1
        ranked.append(item)

    independent = [r for r in ranked if r["verdict"] == VERDICT_NO_EVIDENCE]
    monetised = [r for r in ranked if r["verdict"] in _MONETISED_VERDICTS]
    unknown = [r for r in ranked if r["verdict"] == VERDICT_CANNOT_TELL]

    def _claims(group):
        out = []
        for item in group:
            if item["claim_key"]:
                out.append(item)
        return out

    independent_claims = _claims(independent)
    monetised_claims = _claims(monetised)
    unknown_claims = _claims(unknown)

    shared = {}
    for group, name in ((independent_claims, "independent"),
                        (monetised_claims, "monetised"),
                        (unknown_claims, "cannot_tell")):
        for item in group:
            row = shared.setdefault(item["claim_key"], {
                "claim": item["claim"], "independent": 0, "monetised": 0,
                "cannot_tell": 0,
            })
            row[name] += 1

    shared_claims = [row for row in shared.values()
                     if row["independent"] and row["monetised"]]

    compared = (f"{len(records)} source(s) were compared. "
                f"{len(independent)} had no sign of being paid, "
                f"{len(monetised)} showed some form of monetisation, and "
                f"{len(unknown)} could not be read.")
    readable_claims = bool(independent_claims or monetised_claims)
    if not records or not (independent or monetised or unknown):
        summary = "No sources were supplied, so there is nothing to compare."
    elif not readable_claims:
        if unknown_claims:
            summary = compared + (" None of the readable sources supplied a "
                                  "claim that could be compared.")
        else:
            summary = compared + (" None of them supplied a claim that could "
                                  "be compared.")
    elif shared_claims:
        said = []
        for row in shared_claims[:5]:
            said.append(
                f"{row['independent']} independent source(s) and "
                f"{row['monetised']} monetised source(s) say "
                f"\"{row['claim']}\"")
        summary = compared + " " + "; ".join(said) + "."
    else:
        summary = compared + (" No claim was made by both an independent "
                              "source and a monetised one.")
    if unknown and independent_claims:
        summary += (" A source that could not be read is not counted as "
                    "independent.")

    note = ("This compares the claims each source supplied, word for word "
            "after lowering case and collapsing spaces. Two sources that mean "
            "the same thing in different words do not count as agreeing. It "
            "is a count of sources, not a score, and no percentage is shown "
            "because a handful of sources cannot support one.")

    def _group(group):
        return {
            "count": len(group),
            "with_claim": len(_claims(group)),
            "claims": [item["claim"] for item in _claims(group)],
            "sources": [{key: item[key] for key in
                         ("index", "rank", "url", "kind", "claim", "verdict")}
                        for item in group],
        }

    return {
        "engine": {"name": "jarvis_source_independence", "version": VERSION,
                   "network": False, "read_only": True},
        "sources": [{key: value for key, value in item.items()
                     if key != "claim_key"} for item in ranked],
        "order": [item["index"] for item in ranked],
        "counts": {
            "sources": len(ranked),
            VERDICT_NO_EVIDENCE: len(independent),
            VERDICT_AFFILIATE_ONLY: sum(
                1 for r in ranked if r["verdict"] == VERDICT_AFFILIATE_ONLY),
            VERDICT_CANNOT_TELL: len(unknown),
            VERDICT_LIKELY_UNDISCLOSED: sum(
                1 for r in ranked if r["verdict"] == VERDICT_LIKELY_UNDISCLOSED),
            VERDICT_DISCLOSED_SPONSORED: sum(
                1 for r in ranked if r["verdict"] == VERDICT_DISCLOSED_SPONSORED),
        },
        "agreement": {
            "summary": summary,
            "shared_claims": shared_claims,
            "independent": _group(independent),
            "monetised": _group(monetised),
            "cannot_tell": _group(unknown),
            "note": note,
        },
    }
