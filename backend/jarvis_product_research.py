"""jarvis_product_research.py - the offline engine for a product check: read
the reviews a person could see, show the patterns that are actually
observable, and say plainly what could not be checked.

WHAT THIS IS
This is the analysis engine (docs/DESIGN-PRODUCT-RESEARCH.md; the design
contract is the owner's product-research document, revision 2). It has no
route, no chat tool, no card, no Settings row, no app surface and no network
of any kind: it takes a list of review records, or the page hand-off from
`jarvis_product_read.py`, and returns a report as plain Python data. Nothing
here fetches, stores, logs or learns anything.

WHY THE REPORT IS REASONS, NOT A VERDICT ABOUT EACH REVIEW
The research in the design contract is unambiguous: individual review
authenticity is near chance for people and for LLMs (2026 study, 50.8% human
accuracy), so a per-review "fake/real" label would be false precision. What
IS observable is shown as evidence with counts and examples: verified-purchase
share, Vine-label share, incentive wording, near-duplicate wording, date
burstiness, the rating histogram's shape, stylometry and review-versus-product
mismatch hints. Each signal returns an evidence object (counts, thresholds and
examples) - never a probability, never a single trust number. A review that a
rule notices is "set aside, and why", not deleted and not called fake: the
owner sees every flagged review and can overrule any of it.

THE SAMPLE CAVEAT IS PART OF THE PRODUCT
The reviews a screen or paste can show are the ones Amazon chose to show, not
all reviews. `SAMPLE_CAVEAT` is in every report, at the top, in plain words.

WHAT THE LOCAL MODEL MAY ADD, AND HOW IT IS CHECKED
The local model does only the reading: aspect-level agreement/complaint labels
with quotes, a short reason per review it suggests setting aside, and what it
could not check. `MODEL_CONTRACT` is the exact JSON shape it is asked to fill.
Every proposed quote must be at least 8 characters and match ONE review's
title OR its body exactly after whitespace normalisation; a quote that spans
the two fields, is shorter, or was invented is dropped and counted, and an
aspect left with no real quote is dropped too. The engine never accepts a
model's numeric trust score, because the contract asks for none.

WHY THE TOLERANT REVIEW RECORD
Page structures change and a later extractor may not find every field, so
`normalize_review` accepts a dict of any shape and fills only what it can
read: rating, date, verified purchase, Vine flag, title, text, helpful votes,
variant. A field it cannot read stays None and the report says which counts
are unknown instead of guessing. Reviewer names are never kept: reviews are
labelled "Reviewer 1", "Reviewer 2", ... by their order in the input, because
reviewer identities are public but unnecessary.

NO NUMBER THAT LOOKS LIKE A TRUST SCORE
There is no probability, confidence or trust number anywhere in the report.
Shares and counts are plain arithmetic about the sample; the verdict is a
small set of named rules with the reasons that fired, plus what would change
it. "Not enough trustworthy data" is a first-class outcome, not an error.

STANDARD LIBRARY ONLY: `datetime`, `hashlib`, `json`, `re` and `collections`.
No network, no subprocess, no dependency, no file is read or written.

    py -3 -B backend/test_product_research.py
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
from collections import Counter, defaultdict

VERSION = 2

# ---------------------------------------------------------------------------
#   Words and thresholds, named so the report and the tests can quote them
# ---------------------------------------------------------------------------

#: Shown at the top of every report. The sample is a curated view, not data.
SAMPLE_CAVEAT = (
    "This is what Amazon chose to show, not all of the reviews. The default "
    "review list is Amazon's own ranking, so the sample can be missing reviews "
    "in ways this report cannot see."
)

#: Below these, the report says "not enough trustworthy data" instead of
#: summarising. They are chosen to require a few reviews with real words, not
#: to imply statistical power.
MIN_REVIEWS = 5
MIN_TEXT_WORDS_TOTAL = 80

#: A quote shorter than this is not a quote: the model is asked for a real
#: phrase from the review, and a one-word fragment proves nothing.
MIN_QUOTE_CHARS = 8

#: A review needs this many words to be compared for near-duplicate wording:
#: short genuine reviews repeat common phrases and would form false groups.
MIN_WORDS_FOR_DUPLICATES = 12
DUPLICATE_JACCARD = 0.60
MINHASH_PERMUTATIONS = 32

#: Text needs this many words before its densities are used: ratios from very
#: short reviews are noise.
STYLOMETRY_MIN_WORDS = 20
SUPERLATIVE_PER_100_FLAG = 3.0
EXCLAMATION_PER_100_FLAG = 5.0
FIRST_PERSON_PER_100_FLAG = 8.0

#: A day is a "burst day" when it has at least this many reviews AND at least
#: this multiple of the baseline the report states (a listing's own per-day
#: average when supplied, otherwise the sample's average without that day).
#: Both must hold, so a quiet sample with four reviews on one day is not
#: automatically a burst, and a listing that averages thousands of reviews a
#: day does not flag a four-review day.
BURST_MIN_DAY_REVIEWS = 4
BURST_RATE_MULTIPLE = 3.0
BURST_WINDOW_DAYS = 7

#: Shares used only as named thresholds in the evidence, never as a score.
LOW_VERIFIED_SHARE = 0.50
HIGH_VINE_SHARE = 0.30
POLARISED_FIVE_STAR_SHARE = 0.75
POLARISED_LOW_STAR_SHARE = 0.05

#: How many examples one signal carries by default (the counts are complete;
#: the examples are a short tail the owner can read).
EXAMPLES_PER_SIGNAL = 3

#: The longest snippet of review text shown in a report or a flagged review.
SNIPPET_CHARS = 160

#: Reviews that can be listed as "set aside". Above this the report shows the
#: first ones and says how many more the rules flagged (never hides the count).
MAX_SET_ASIDE = 40

#: The model's proposal limits, mirrored by validate_model_output().
MODEL_MAX_ASPECTS = 12
MODEL_QUOTES_PER_ASPECT = 2
MODEL_MAX_SET_ASIDE = 20
MODEL_MAX_COULD_NOT_CHECK = 8

_ALWAYS_COULD_NOT_CHECK = (
    "reviewer profiles and review histories: Amazon's review list needs a "
    "sign-in and its rules disallow profile pages, so this report does not "
    "see who wrote what elsewhere",
    "whether a reviewer was paid or refunded outside the Vine label: that "
    "cannot be seen from a page",
    "all reviews: only the reviews you could read are included, and Amazon "
    "chooses which ones to show",
    "hidden orders and undisclosed incentives: a page does not show them",
    "the star rating's own calculation: Amazon says its rating is generated "
    "by a machine-learned model, not by a plain average",
)

#: Incentive / disclosure wording. Each entry is (name, regex, plain words).
#: These are deliberately coarse: an honest reviewer can mention a gift too, so
#: a match is a pattern to look at, never a finding.
INCENTIVE_PATTERNS = (
    ("free product", re.compile(
        r"\b(?:received|got|was sent|was given)\b[^.!?\n]{0,60}\b(?:for free|free of charge|"
        r"at no cost|complimentary)\b", re.I),
     "says a product was received for free"),
    ("in exchange", re.compile(
        r"\bin exchange for\b[^.!?\n]{0,60}\b(?:review|honest|unbiased|feedback|rating)\b",
        re.I),
     "says something was in exchange for a review"),
    ("asked to review", re.compile(
        r"\b(?:asked|invited|encouraged|told)\b[^.!?\n]{0,40}\b(?:to|me)\b[^.!?\n]{0,30}"
        r"\breview\b", re.I),
     "says the reviewer was asked to review it"),
    ("discount code", re.compile(
        r"\b(?:discount|promo(?:tion)?|coupon|voucher)\b[^.!?\n]{0,25}\b(?:code|offer)\b",
        re.I),
     "mentions a discount or promo code"),
    ("gift", re.compile(
        r"\b(?:gifted|gift|free sample|sample provided)\b", re.I),
     "mentions a gift or a provided sample"),
    ("affiliate link", re.compile(
        r"\b(?:affiliate|referral)\b[^.!?\n]{0,25}\b(?:link|code)\b", re.I),
     "mentions an affiliate or referral link"),
)

#: Words that carry no product information in a density measure.
STOPWORDS = frozenset("""
a about above after again against all am an and any are as at be because been
before being below between both but by can could did do does doing down during
each few for from further had has have having he her here hers herself him
himself his how i if in into is it its itself just me more most my myself no
nor not now of off on once only or other our ours ourselves out over own same
she should so some such than that the their theirs them themselves then there
these they this those through to too under until up very was we were what when
where which while who whom why will with would you your yours yourself
yourselves
""".split())

#: Praise words. A density of these with no concrete details is the generic
#: review pattern the literature describes; one on its own means nothing.
SUPERLATIVES = frozenset("""
amazing awesome best brilliant excellent exceptional fantastic flawless
impeccable incredible love loved must-have outstanding perfect phenomenal
superb terrific unbeatable unbelievable wonderful worst terrible horrible
awful disastrous useless garbage
""".split())

FIRST_PERSON = frozenset(("i", "me", "my", "mine", "we", "us", "our", "ours"))

#: Concrete-detail markers: digits, and units/model numbers beside them.
_SPEC_WORD = re.compile(
    r"\b\d+(?:\.\d+)?\s?(?:%|gb|tb|mb|mah|wh|w|kw|v|hz|ghz|mm|cm|m|in|inch|"
    r"inches|ft|g|kg|lb|lbs|oz|ml|l|h|hr|hrs|hour|hours|min|mins|minute|"
    r"minutes|day|days|month|months|year|years|mp|fps|db|dba|psi|bar|°c|"
    r"°f|battery|charger|port|cable)\b",
    re.I,
)

_ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_ANY_DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")

#: The review fields this module reads. Unknown keys are ignored; a missing
#: field is shown as unknown, never guessed.
REVIEW_FIELDS = (
    "rating", "date", "verified", "vine", "title", "text", "helpful", "variant",
)


def _round(value, places=3):
    """A stable rounded float in the report (never a probability)."""
    try:
        return round(float(value), places)
    except (TypeError, ValueError):
        return None


def normalize_whitespace(text) -> str:
    """Collapse all runs of whitespace to one space, and trim.

    This is the ONLY normalisation the quote validator applies: a quote is
    accepted when its whitespace-normalised form is a real substring of a
    review's whitespace-normalised title+text. Case and punctuation must match,
    so a paraphrase is never accepted as a quote."""
    return " ".join(str(text or "").split())


def _clean_text(raw, cap: int) -> str:
    """Plain text with control characters removed and a hard length cap."""
    if raw is None:
        return ""
    text = str(raw)
    text = "".join(ch if (ch.isprintable() or ch == "\n" or ch == "\t") else " " for ch in text)
    text = " ".join(text.split())
    return text[:cap]


def _valid_date(year: int, month: int, day: int) -> bool:
    """True only for a real calendar date (2026-02-31 is not one)."""
    try:
        _dt.date(year, month, day)
    except (TypeError, ValueError):
        return False
    return True


def _parse_date(raw):
    """A review date as YYYY-MM-DD, or None.

    A page may show a full timestamp, a date, or a human date. The tolerant
    rule accepts the ISO forms and a few common written forms, but the day must
    exist in that month: "2026-02-31" and "31 February 2026" are unknown, not
    guessed dates. Anything unreadable is counted as unknown."""
    if raw is None:
        return None
    text = normalize_whitespace(raw)
    if not text:
        return None
    m = _ISO_DATE.match(text) or _ANY_DATE.search(text)
    if m:
        try:
            year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
        except ValueError:
            return None
        if (1900 <= year <= 2100 and _valid_date(year, month, day)):
            return f"{year:04d}-{month:02d}-{day:02d}"
        return None
    for fmt in ("%d %B %Y", "%B %d, %Y", "%d %b %Y", "%b %d, %Y", "%Y/%m/%d"):
        try:
            return _dt.datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _parse_bool(raw):
    """True/False when the record says, None when it does not."""
    if raw is True or raw is False:
        return raw
    if raw is None:
        return None
    text = normalize_whitespace(raw).lower()
    if not text:
        return None
    if "not verified" in text or "unverified" in text:
        return False
    if "verified" in text:
        return True
    if text in ("true", "yes", "1"):
        return True
    if text in ("false", "no", "0"):
        return False
    return None


def _parse_vine(raw):
    """True when the Vine badge is present, False when it is explicitly
    absent from a record that carries the badge field, None when unknown.

    "No Vine" is an explicit absence, not a Vine label: a page that says the
    review is not Vine must not inflate the Vine share."""
    if raw is True or raw is False:
        return raw
    if raw is None:
        return None
    text = normalize_whitespace(raw).lower()
    if not text:
        return None
    if text in ("false", "no", "none"):
        return False
    if "no vine" in text or "not vine" in text or "not a vine" in text:
        return False
    return "vine" in text


def _parse_rating(raw):
    """A whole 1..5 star rating, or None."""
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        value = float(raw)
    else:
        m = re.search(r"\d(?:\.\d)?", normalize_whitespace(raw))
        if not m:
            return None
        value = float(m.group(0))
    if not (1.0 <= value <= 5.0):
        return None
    return int(round(value))


def _parse_helpful(raw):
    """A non-negative whole number of helpful votes, or None."""
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        value = int(raw)
    else:
        m = re.search(r"\d+", normalize_whitespace(raw))
        if not m:
            return None
        value = int(m.group(0))
    return value if value >= 0 else None


def normalize_review(raw, index: int = 0) -> dict:
    """One review, tolerant: every known field is read if it can be, and is
    None when it cannot. Reviewer names are never kept - the label comes from
    the review's position in the input."""
    data = raw if isinstance(raw, dict) else {}
    rating = _parse_rating(data.get("rating"))
    date = _parse_date(data.get("date"))
    verified = _parse_bool(data.get("verified") if "verified" in data
                           else data.get("verified_purchase"))
    vine = _parse_vine(data.get("vine") if "vine" in data else data.get("badge"))
    title = _clean_text(data.get("title"), 200)
    text = _clean_text(data.get("text"), 6000)
    helpful = _parse_helpful(data.get("helpful") if "helpful" in data
                             else data.get("helpful_votes"))
    variant = _clean_text(data.get("variant"), 80)
    return {
        "index": index,
        "reviewer": f"Reviewer {index + 1}",
        "rating": rating,
        "date": date,
        "verified": verified,
        "vine": vine,
        "title": title,
        "text": text,
        "helpful": helpful,
        "variant": variant or None,
    }


def normalize_reviews(raw) -> tuple:
    """(records, skipped) from a list (or a {"reviews": [...]} wrapper).

    Anything that is not a review object is skipped and counted; this never
    raises for bad input, so a partial extraction still produces an honest
    report."""
    items = []
    if isinstance(raw, dict) and isinstance(raw.get("reviews"), list):
        items = raw["reviews"]
    elif isinstance(raw, list):
        items = raw
    records = []
    skipped = 0
    for item in items:
        if not isinstance(item, dict):
            skipped += 1
            continue
        if not any(isinstance(item.get(k), (str, int, float, bool)) for k in REVIEW_FIELDS):
            skipped += 1
            continue
        records.append(normalize_review(item, len(records)))
    return records, skipped


def review_title(record: dict) -> str:
    """The review's title, whitespace-normalised, on its own."""
    return normalize_whitespace(record.get("title") or "")


def review_body(record: dict) -> str:
    """The review's body text, whitespace-normalised, on its own. A title is
    not a body: `with_text` and the quote validator treat them separately."""
    return normalize_whitespace(record.get("text") or "")


def review_text(record: dict) -> str:
    """A review's title and text joined for display and word matching (never
    for the quote validator, which checks each field on its own)."""
    return normalize_whitespace(f"{review_title(record)} {review_body(record)}")


def _snippet(record: dict, cap: int = SNIPPET_CHARS) -> str:
    text = review_text(record)
    if len(text) <= cap:
        return text
    return text[: max(0, cap - 1)].rstrip() + "\u2026"


def _words(text: str) -> list:
    return re.findall(r"[a-z0-9']+", normalize_whitespace(text).lower())


def _word_count(text: str) -> int:
    return len(_words(text))


def _example(record: dict, why: str) -> dict:
    return {"reviewer": record["reviewer"], "why": why, "snippet": _snippet(record)}


def _evidence(signal, *, available=True, why="", counts=None, thresholds=None,
              examples=None, flags=None, note=""):
    """One evidence object: the only shape a signal returns.

    It carries counts, the thresholds that make a count noticeable, a few
    examples and the reviews a rule put on the "set aside" list. It never
    carries a probability or a trust number."""
    return {
        "signal": signal,
        "available": bool(available),
        "why": why,
        "counts": counts or {},
        "thresholds": thresholds or {},
        "examples": list(examples or [])[:EXAMPLES_PER_SIGNAL],
        "flags": list(flags or []),
        "note": note,
    }


# ---------------------------------------------------------------------------
#   Signal 1: verified-purchase share
# ---------------------------------------------------------------------------

def signal_verified_purchase_share(reviews) -> dict:
    """How many readable reviews say the purchase was verified.

    This is the one factor the literature still treats as meaningful, and it is
    still not proof: a seller can refund a verified buyer after the review, and
    Amazon checks a purchase, not honesty. Reviews whose badge could not be
    read are counted as unknown, not as unverified."""
    known = [r for r in reviews if r["verified"] is not None]
    verified = [r for r in known if r["verified"] is True]
    unverified = [r for r in known if r["verified"] is False]
    negatives = [r for r in known if r["rating"] is not None and r["rating"] <= 2]
    negative_verified = [r for r in negatives if r["verified"] is True]
    counts = {
        "reviews": len(reviews),
        "state_known": len(known),
        "state_unknown": len(reviews) - len(known),
        "verified": len(verified),
        "unverified": len(unverified),
        "negative_reviews": len(negatives),
        "negative_verified": len(negative_verified),
    }
    if len(known) >= 1:
        counts["verified_share"] = _round(len(verified) / len(known))
    if negatives:
        counts["negative_verified_share"] = _round(len(negative_verified) / len(negatives))
    thresholds = {"min_state_known": 3, "low_share_below": LOW_VERIFIED_SHARE}
    if len(known) < 3:
        return _evidence(
            "verified_purchase_share", available=False,
            why="fewer than 3 readable reviews say whether the purchase was verified",
            counts=counts, thresholds=thresholds,
            note="Verified Purchase is a badge Amazon adds; it is not proof the reviewer paid, "
                 "because a refund after the review cannot be seen.")
    flags = [{"index": r["index"], "reason": "unverified purchase with 5 stars"}
             for r in unverified if r["rating"] == 5]
    examples = [_example(r, "unverified purchase")
                for r in (unverified or verified)[:EXAMPLES_PER_SIGNAL]]
    note = ("Verified Purchase is a badge Amazon adds; it is not proof the reviewer paid, "
            "because a refund after the review cannot be seen.")
    if counts.get("verified_share", 1) < LOW_VERIFIED_SHARE:
        note += " Fewer than half of the reviews that say are verified purchases."
    return _evidence("verified_purchase_share", counts=counts, thresholds=thresholds,
                     examples=examples, flags=flags, note=note)


# ---------------------------------------------------------------------------
#   Signal 2: Vine-label share
# ---------------------------------------------------------------------------

def signal_vine_share(reviews) -> dict:
    """How many readable reviews carry the disclosed free-product Vine label.

    Vine is not a cash payment and is not hidden manipulation: it is the one
    incentive Amazon labels. Leaving those reviews in or out changes the
    picture, so its share is shown and each one is listed in "set aside"."""
    known = [r for r in reviews if r["vine"] is not None]
    vine = [r for r in known if r["vine"] is True]
    counts = {
        "reviews": len(reviews),
        "state_known": len(known),
        "state_unknown": len(reviews) - len(known),
        "vine": len(vine),
    }
    if known:
        counts["vine_share"] = _round(len(vine) / len(known))
    thresholds = {"min_state_known": 3, "high_share_above": HIGH_VINE_SHARE}
    if len(known) < 3:
        return _evidence(
            "vine_share", available=False,
            why="fewer than 3 readable reviews say whether a Vine label is present",
            counts=counts, thresholds=thresholds)
    flags = [{"index": r["index"], "reason": "Vine label: a free product was disclosed"}
             for r in vine]
    note = ("Vine is Amazon's disclosed free-product programme, not a cash payment; "
            "each Vine review is listed below so you can decide whether to count it.")
    if counts.get("vine_share", 0) >= HIGH_VINE_SHARE:
        note += " A large share of the readable reviews carry the Vine label."
    return _evidence("vine_share", counts=counts, thresholds=thresholds,
                     examples=[_example(r, "Vine review") for r in vine[:EXAMPLES_PER_SIGNAL]],
                     flags=flags, note=note)


# ---------------------------------------------------------------------------
#   Signal 3: incentive / disclosure language
# ---------------------------------------------------------------------------

def signal_incentive_language(reviews) -> dict:
    """Reviews whose own words mention a free product, an exchange, a discount
    code, a gift, or an affiliate link.

    This is low precision on purpose: honest reviewers mention gifts too, and
    a match is not proof of a paid review. A match is only ever a pattern the
    report shows, with the phrase quoted from the review."""
    matches = []
    pattern_counts = Counter()
    flags = []
    examples = []
    for record in reviews:
        text = review_text(record)
        if _word_count(text) < 6:
            continue
        for name, pattern, words in INCENTIVE_PATTERNS:
            found = pattern.search(text)
            if not found:
                continue
            pattern_counts[name] += 1
            flags.append({"index": record["index"],
                          "reason": f"incentive wording: {words}"})
            matches.append({"reviewer": record["reviewer"], "pattern": name,
                            "phrase": _snippet_text(found.group(0), 80), "why": words})
            break
    counts = {
        "reviews": len(reviews),
        "matches": len(matches),
        "reviews_flagged": len({m["reviewer"] for m in matches}),
    }
    counts.update({f"pattern:{k}": v for k, v in sorted(pattern_counts.items())})
    examples = matches[:EXAMPLES_PER_SIGNAL]
    thresholds = {"min_words_in_review": 6}
    if not reviews:
        return _evidence("incentive_language", available=False,
                         why="no readable reviews were passed in", counts=counts,
                         thresholds=thresholds)
    note = ("A mention is a pattern to look at, not proof: honest reviewers mention gifts "
            "and samples too, and a disclosure does not say whether the words were shaped "
            "by it.")
    return _evidence("incentive_language", counts=counts, thresholds=thresholds,
                     examples=examples, flags=_dedupe_flags(flags), note=note)


def _snippet_text(text: str, cap: int) -> str:
    text = normalize_whitespace(text)
    return text if len(text) <= cap else text[: max(0, cap - 1)].rstrip() + "\u2026"


def _dedupe_flags(flags) -> list:
    """One reason per review, in review order, no duplicates."""
    by_index = defaultdict(list)
    for flag in flags:
        if flag["reason"] not in by_index[flag["index"]]:
            by_index[flag["index"]].append(flag["reason"])
    return [{"index": index, "reason": "; ".join(reasons)}
            for index, reasons in sorted(by_index.items())]


# ---------------------------------------------------------------------------
#   Signal 4: near-duplicate wording (own shingles + MinHash, no dependency)
# ---------------------------------------------------------------------------

def _shingles(text: str, size: int = 5) -> frozenset:
    """All word shingles of `size` words in the text, lower-cased."""
    words = _words(text)
    if len(words) < size:
        return frozenset()
    return frozenset(" ".join(words[i:i + size]) for i in range(len(words) - size + 1))


def _minhash_signature(shingles: frozenset, permutations: int = MINHASH_PERMUTATIONS) -> tuple:
    """A deterministic MinHash signature.

    The shingle set is the input; hashing it with `permutations` distinct salts
    gives a collision pattern such that two sets with high Jaccard tend to share
    signature positions. It is only a shortlisting aid here: the pair's verdict
    is the exact Jaccard below, so a hash collision can never turn two unlike
    reviews into a duplicate."""
    if not shingles:
        return tuple()
    signature = []
    for salt in range(permutations):
        best = None
        for shingle in shingles:
            digest = hashlib.sha256(f"{salt}\x00{shingle}".encode("utf-8")).digest()
            value = int.from_bytes(digest[:8], "big")
            if best is None or value < best:
                best = value
        signature.append(best)
    return tuple(signature)


def _jaccard(a: frozenset, b: frozenset) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def signal_near_duplicate_wording(reviews) -> dict:
    """Groups of reviews that share most of their wording.

    Word shingles (5-word runs) are compared with exact Jaccard similarity; a
    deterministic MinHash signature shortlists candidate pairs first. Only
    reviews with at least 12 words are compared, because two short genuine
    reviews can share most of a tiny wording set. A group is a reason to look,
    never a label: copy-paste templates and honest repeated phrases look alike."""
    eligible = [r for r in reviews if _word_count(review_text(r)) >= MIN_WORDS_FOR_DUPLICATES]
    shingle_sets = [_shingles(review_text(r)) for r in eligible]
    signatures = [_minhash_signature(s) for s in shingle_sets]
    pairs = []
    pairs_shortlisted = 0
    pairs_compared = 0
    for i in range(len(eligible)):
        for j in range(i + 1, len(eligible)):
            # Shortlist only: the exact Jaccard decides every pair.
            shared_positions = sum(1 for a, b in zip(signatures[i], signatures[j]) if a == b)
            if shared_positions < 2:
                continue
            pairs_shortlisted += 1
            pairs_compared += 1
            similarity = _jaccard(shingle_sets[i], shingle_sets[j])
            if similarity >= DUPLICATE_JACCARD:
                pairs.append((i, j, similarity))
    parent = list(range(len(eligible)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i, j, _similarity in pairs:
        union(i, j)
    groups = defaultdict(list)
    for position in range(len(eligible)):
        groups[find(position)].append(position)
    groups = [sorted(g) for g in groups.values() if len(g) > 1]
    groups.sort(key=lambda g: (-len(g), g[0]))
    flagged = set()
    flags = []
    examples = []
    for group in groups:
        members = [eligible[p]["reviewer"] for p in group]
        for p in group:
            others = [m for m in members if m != eligible[p]["reviewer"]]
            flags.append({"index": eligible[p]["index"],
                          "reason": f"wording overlaps review(s) {', '.join(others)}"})
            flagged.add(eligible[p]["index"])
        examples.append({
            "reviewers": members,
            "why": "these reviews share at least "
                   f"{int(DUPLICATE_JACCARD * 100)}% of their 5-word runs",
            "snippets": [_snippet(eligible[p], 100) for p in group[:2]],
        })
    counts = {
        "reviews": len(reviews),
        "reviews_compared": len(eligible),
        "pairs_possible": len(eligible) * (len(eligible) - 1) // 2,
        "pairs_shortlisted": pairs_shortlisted,
        "pairs_compared": pairs_compared,
        "duplicate_pairs": len(pairs),
        "duplicate_groups": len(groups),
        "reviews_flagged": len(flagged),
    }
    thresholds = {"min_words_for_compare": MIN_WORDS_FOR_DUPLICATES,
                  "jaccard_at_or_above": DUPLICATE_JACCARD}
    if len(eligible) < 2:
        return _evidence("near_duplicate_wording", available=False,
                         why="fewer than 2 readable reviews are long enough to compare",
                         counts=counts, thresholds=thresholds)
    note = ("A shared wording pattern is a reason to look, not a finding: templates and "
            "honest repeated phrases can look alike, and only reviews with enough words "
            "are compared.")
    return _evidence("near_duplicate_wording", counts=counts, thresholds=thresholds,
                     examples=examples[:EXAMPLES_PER_SIGNAL],
                     flags=_dedupe_flags(flags), note=note)


# ---------------------------------------------------------------------------
#   Signal 5: date burstiness against the listing baseline
# ---------------------------------------------------------------------------

def _median(values):
    ordered = sorted(values)
    if not ordered:
        return 0.0
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def signal_date_burstiness(reviews, *, listing=None) -> dict:
    """Reviews per day against the baseline the flags actually use.

    The evidence is simple arithmetic: how many days the dated reviews cover,
    the busiest day, the busiest 7-day window, and how far the busiest day is
    from the baseline. That baseline is the listing's own per-day average when
    a review count and first date are supplied; otherwise it is the sample's
    average WITHOUT the day being tested, so one busy day cannot hide itself.
    A day is flagged only when it has at least 4 reviews AND at least 3x that
    baseline -- so a listing that averages thousands of reviews a day does not
    flag a four-review day. A genuine launch can still create a real spike, so
    a burst is never a verdict."""
    dated = []
    invalid_dates = 0
    for record in reviews:
        if not record["date"]:
            continue
        if _safe_ordinal(record["date"]) is None:
            invalid_dates += 1
        else:
            dated.append(record)
    counts = {
        "reviews": len(reviews),
        "dated": len(dated),
        "undated": len(reviews) - len(dated) - invalid_dates,
        "invalid_dates": invalid_dates,
    }
    thresholds = {"min_dated": 3, "burst_min_day_reviews": BURST_MIN_DAY_REVIEWS,
                  "burst_rate_multiple": BURST_RATE_MULTIPLE,
                  "window_days": BURST_WINDOW_DAYS}
    if len(dated) < 3:
        return _evidence("date_burstiness", available=False,
                         why="fewer than 3 readable reviews carry a real date",
                         counts=counts, thresholds=thresholds)
    by_day = Counter(r["date"] for r in dated)
    days = sorted(by_day)
    first, last = days[0], days[-1]
    span_days = max(1, _safe_ordinal(last) - _safe_ordinal(first) + 1)
    busiest_day = max(days, key=lambda d: (by_day[d], d))
    busiest_count = by_day[busiest_day]
    mean_day = len(dated) / span_days
    window_start, window_count = None, 0
    for start in days:
        end = _date_add(start, BURST_WINDOW_DAYS - 1)
        count = sum(n for d, n in by_day.items() if start <= d <= end)
        if count > window_count:
            window_start, window_count = start, count
    baseline = {"source": "sample", "reviews": len(dated), "days": span_days,
                "per_day": _round(mean_day)}
    listing = listing if isinstance(listing, dict) else {}
    if isinstance(listing.get("review_count"), int) and listing["review_count"] > 0 \
            and listing.get("first_available"):
        first_available = _parse_date(listing.get("first_available"))
        first_ordinal = _safe_ordinal(first_available) if first_available else None
        if first_ordinal is not None:
            baseline_days = max(1, _safe_ordinal(last) - first_ordinal + 1)
            baseline = {"source": "listing", "reviews": int(listing["review_count"]),
                        "days": baseline_days,
                        "per_day": _round(int(listing["review_count"]) / baseline_days)}
    flags = []
    burst_days = []
    busiest_base = 0.0
    busiest_threshold = 0.0
    for day in days:
        if baseline["source"] == "listing":
            day_base = float(baseline["per_day"] or 0.0)
        else:
            others = len(dated) - by_day[day]
            day_base = others / max(1, span_days - 1)
        threshold = max(float(BURST_MIN_DAY_REVIEWS), day_base * BURST_RATE_MULTIPLE)
        if day == busiest_day:
            busiest_base = day_base
            busiest_threshold = threshold
        if by_day[day] >= BURST_MIN_DAY_REVIEWS and by_day[day] >= threshold:
            burst_days.append(day)
            for record in dated:
                if record["date"] == day:
                    flags.append({"index": record["index"],
                                  "reason": f"posted on {day}, a day with {by_day[day]} "
                                            f"of the {len(dated)} dated reviews"})
    counts.update({
        "days_covered": span_days,
        "max_same_day": busiest_count,
        "busiest_day": busiest_day,
        "max_in_window": window_count,
        "window_start": window_start,
        "mean_per_day": _round(mean_day),
        "baseline_source": baseline["source"],
        "baseline_per_day": baseline["per_day"],
        "baseline_used_for_busiest_day": _round(busiest_base),
        "flag_threshold_for_busiest_day": _round(busiest_threshold),
        "listing_review_count": baseline.get("reviews") if baseline["source"] == "listing" else None,
        "burst_days": len(burst_days),
        "reviews_on_burst_days": sum(by_day[d] for d in burst_days),
    })
    examples = [{"day": day, "reviews": by_day[day], "why": "burst day"}
                for day in sorted(burst_days, key=lambda d: (-by_day[d], d))[:EXAMPLES_PER_SIGNAL]]
    note = ("The flag compares each day with the baseline in the counts: the listing's per-day "
            "average when supplied, otherwise the sample's average without that day. A day must "
            "have at least 4 reviews and at least 3x the baseline, so a genuine launch can still "
            "create a real spike; a burst says nothing about any single review.")
    if baseline["source"] == "listing":
        note += (" The baseline here is the listing's own review count over the days from its "
                 "first available date to the newest dated review.")
    else:
        note += (" No listing baseline was passed in, so each day is compared with the sample's "
                 "average over its dated range without that day.")
    return _evidence("date_burstiness", counts=counts, thresholds=thresholds,
                     examples=examples, flags=_dedupe_flags(flags), note=note)


def _safe_ordinal(day):
    """The date's ordinal, or None when the value is not a real calendar date."""
    try:
        return _dt.date.fromisoformat(str(day)).toordinal()
    except (TypeError, ValueError):
        return None


def _date_add(day: str, days: int) -> str:
    return (_dt.date.fromisoformat(day) + _dt.timedelta(days=days)).isoformat()


# ---------------------------------------------------------------------------
#   Signal 6: rating histogram shape
# ---------------------------------------------------------------------------

def _histogram_from_listing(listing) -> dict:
    """{1..5: count} from a listing's supplied histogram, or {} when unusable."""
    if not isinstance(listing, dict):
        return {}
    raw = listing.get("rating_counts") or listing.get("rating_histogram")
    if not isinstance(raw, dict):
        return {}
    out = {}
    for key, value in raw.items():
        try:
            star = int(str(key).strip())
        except (TypeError, ValueError):
            continue
        if 1 <= star <= 5 and isinstance(value, int) and value >= 0:
            out[star] = value
    return out if out else {}


def signal_rating_histogram(reviews, *, listing=None) -> dict:
    """The shape of the star histogram: average, 5-star share, 1-2 star share,
    and whether it is J-shaped (almost all 5 stars, almost no low stars).

    Amazon says its displayed star rating is generated by a machine-learned
    model, not a plain average, so when the histogram comes from the listing it
    is shown as "what Amazon shows"; when it is counted from the readable
    reviews it is shown as the sample's own count. Neither is raw data."""
    from_listing = _histogram_from_listing(listing)
    if from_listing:
        histogram = from_listing
        source = "listing"
    else:
        histogram = Counter(r["rating"] for r in reviews if r["rating"] is not None)
        source = "reviews"
    total = sum(histogram.values())
    counts = {"source": source, "total": total}
    for star in range(1, 6):
        counts[f"stars_{star}"] = int(histogram.get(star, 0))
    if total:
        average = sum(star * n for star, n in histogram.items()) / total
        counts["average"] = _round(average, 2)
        counts["five_star_share"] = _round(histogram.get(5, 0) / total)
        counts["one_two_star_share"] = _round((histogram.get(1, 0)
                                               + histogram.get(2, 0)) / total)
        counts["extreme_share"] = _round((histogram.get(5, 0)
                                          + histogram.get(1, 0)) / total)
    thresholds = {"min_ratings": 3,
                  "polarised_five_star_share_at_or_above": POLARISED_FIVE_STAR_SHARE,
                  "polarised_low_star_share_at_or_below": POLARISED_LOW_STAR_SHARE}
    if total < 3:
        return _evidence("rating_histogram", available=False,
                         why="fewer than 3 ratings are readable",
                         counts=counts, thresholds=thresholds)
    polarised = (counts.get("five_star_share", 0) >= POLARISED_FIVE_STAR_SHARE
                 and counts.get("one_two_star_share", 1) <= POLARISED_LOW_STAR_SHARE)
    counts["polarised"] = polarised
    note = ("A J-shaped histogram is common for genuine products too, and Amazon's own rating is "
            "generated by a model, so read this as the shape of what is shown, not as a "
            "measurement of manipulation.")
    if source == "listing":
        note += " The histogram came from the listing, not from the readable reviews."
    return _evidence("rating_histogram", counts=counts, thresholds=thresholds, note=note)


# ---------------------------------------------------------------------------
#   Signal 7: stylometry (density measures, never a classifier)
# ---------------------------------------------------------------------------

def _density(count: int, words: int, per: int = 100) -> float:
    return _round((count * per) / words, 2) if words else 0.0


def _stylometry_row(record: dict) -> dict:
    text = review_text(record)
    words = _words(text)
    total = len(words)
    stopword_count = sum(1 for w in words if w in STOPWORDS)
    first_person = sum(1 for w in words if w in FIRST_PERSON)
    exclamations = text.count("!")
    superlatives = sum(1 for w in words if w in SUPERLATIVES)
    spec_tokens = len(_SPEC_WORD.findall(text))
    return {
        "reviewer": record["reviewer"],
        "index": record["index"],
        "words": total,
        "stopword_share": _round(stopword_count / total) if total else 0.0,
        "first_person_per_100": _density(first_person, total),
        "exclamations_per_100": _density(exclamations, total),
        "superlatives_per_100": _density(superlatives, total),
        "spec_words_per_100": _density(spec_tokens, total),
    }


def signal_stylometry(reviews) -> dict:
    """Density measures over reviews with enough words to mean something:
    stopword share, first-person density, exclamation marks, superlatives and
    concrete specification words (numbers and units), per 100 words.

    These are the cues the classic deceptive-opinion study found (deceptive
    reviews: more first-person, fewer concrete details), but that classifier
    reached its accuracy on a balanced research set and modern LLM-written text
    defeats it. So a flagged review is a pattern to inspect, never a label."""
    rows = [_stylometry_row(r) for r in reviews if _word_count(review_text(r)) >= STYLOMETRY_MIN_WORDS]
    thresholds = {"min_words_for_density": STYLOMETRY_MIN_WORDS,
                  "superlatives_per_100_at_or_above": SUPERLATIVE_PER_100_FLAG,
                  "exclamations_per_100_at_or_above": EXCLAMATION_PER_100_FLAG,
                  "first_person_per_100_at_or_above": FIRST_PERSON_PER_100_FLAG}
    if not rows:
        return _evidence("stylometry", available=False,
                         why=f"no readable review has {STYLOMETRY_MIN_WORDS} or more words",
                         counts={"reviews": len(reviews), "measured": 0},
                         thresholds=thresholds)
    counts = {"reviews": len(reviews), "measured": len(rows)}
    for field in ("stopword_share", "first_person_per_100", "exclamations_per_100",
                  "superlatives_per_100", "spec_words_per_100"):
        values = [row[field] for row in rows]
        counts[f"mean_{field}"] = _round(sum(values) / len(values), 2)
        counts[f"max_{field}"] = _round(max(values), 2)
    flags = []
    for row in rows:
        reasons = []
        if row["superlatives_per_100"] >= SUPERLATIVE_PER_100_FLAG and \
                row["spec_words_per_100"] == 0:
            reasons.append("generic praise: many superlatives, no measurements")
        if row["first_person_per_100"] >= FIRST_PERSON_PER_100_FLAG and \
                row["spec_words_per_100"] == 0:
            reasons.append("talks about the reviewer more than concrete product details")
        if row["exclamations_per_100"] >= EXCLAMATION_PER_100_FLAG:
            reasons.append("many exclamation marks for its length")
        if reasons:
            flags.append({"index": row["index"], "reason": "; ".join(reasons)})
    note = ("Short genuine reviews can look like this too, and the older research result was "
            "measured on a balanced set; these densities are cues, not a classifier.")
    return _evidence("stylometry", counts=counts, thresholds=thresholds,
                     examples=rows[:EXAMPLES_PER_SIGNAL], flags=_dedupe_flags(flags),
                     note=note)


# ---------------------------------------------------------------------------
#   Signal 8: review-versus-product mismatch hints
# ---------------------------------------------------------------------------

def _product_facts(product, listing) -> dict:
    facts = {}
    if isinstance(product, dict):
        facts.update(product)
    if isinstance(listing, dict):
        for key in ("title", "variant", "variants", "released", "first_available",
                    "model", "keywords"):
            if key not in facts and key in listing:
                facts[key] = listing[key]
    return facts


def signal_product_mismatch(reviews, *, product=None, listing=None) -> dict:
    """Hints that a review may be about a different product or variant:

    * its date is before the product's own first-available/release date, or
    * it names a variant token that the product facts list as a *different*
      variant (for example the product is XL and the review says M).

    Both are hints only: variation pages are legitimately reused, and a review
    may mention another size the reviewer also owns. When neither a release
    date nor a variant list is supplied, the signal says it cannot be checked
    rather than guessing."""
    facts = _product_facts(product, listing)
    released = _parse_date(facts.get("released") or facts.get("first_available"))
    variants = []
    if isinstance(facts.get("variants"), list):
        variants = [_clean_text(v, 40).lower() for v in facts["variants"]
                    if _clean_text(v, 40)]
    current_variant = _clean_text(facts.get("variant"), 40).lower()
    keywords = []
    if isinstance(facts.get("keywords"), list):
        keywords = [_clean_text(k, 40).lower() for k in facts["keywords"]
                    if _clean_text(k, 40)]
    counts = {"reviews": len(reviews), "dated": sum(1 for r in reviews if r["date"]),
              "before_release": 0, "conflicting_variant": 0,
              "mentions_unknown_variant": 0}
    thresholds = {"needs_release_date_or_variants": True}
    if not released and not (variants and current_variant):
        return _evidence("review_product_mismatch", available=False,
                         why="no release date and no variant list were supplied, so a "
                             "review-versus-product match cannot be checked",
                         counts=counts, thresholds=thresholds)
    flags = []
    examples = []
    for record in reviews:
        text = review_text(record).lower()
        if released and record["date"] and record["date"] < released:
            counts["before_release"] += 1
            flags.append({"index": record["index"],
                          "reason": f"dated {record['date']}, before the product's "
                                    f"first available date {released}"})
            examples.append(_example(record, "older than the product"))
        if variants and current_variant:
            mentioned_other = [v for v in variants if v != current_variant
                               and re.search(rf"\b{re.escape(v)}\b", text)]
            if mentioned_other:
                counts["conflicting_variant"] += 1
                flags.append({"index": record["index"],
                              "reason": "names a different variant: "
                                        + ", ".join(sorted(mentioned_other))})
                examples.append(_example(record, "different variant"))
        if keywords:
            mentioned = [k for k in keywords if k in text]
            if not mentioned:
                counts["mentions_unknown_variant"] += 1
    note = ("Variation pages are reused legitimately and a reviewer may mention another size "
            "they also own, so these are hints to check, not findings.")
    return _evidence("review_product_mismatch", counts=counts, thresholds=thresholds,
                     examples=examples[:EXAMPLES_PER_SIGNAL],
                     flags=_dedupe_flags(flags), note=note)


# ---------------------------------------------------------------------------
#   All signals
# ---------------------------------------------------------------------------

#: The order signals appear in the report, samples and tests.
SIGNAL_NAMES = (
    "verified_purchase_share",
    "vine_share",
    "incentive_language",
    "near_duplicate_wording",
    "date_burstiness",
    "rating_histogram",
    "stylometry",
    "review_product_mismatch",
)


def signals_for(reviews, *, listing=None, product=None) -> dict:
    """Every deterministic signal, in a fixed order, as evidence objects."""
    return {
        "verified_purchase_share": signal_verified_purchase_share(reviews),
        "vine_share": signal_vine_share(reviews),
        "incentive_language": signal_incentive_language(reviews),
        "near_duplicate_wording": signal_near_duplicate_wording(reviews),
        "date_burstiness": signal_date_burstiness(reviews, listing=listing),
        "rating_histogram": signal_rating_histogram(reviews, listing=listing),
        "stylometry": signal_stylometry(reviews),
        "review_product_mismatch": signal_product_mismatch(
            reviews, product=product, listing=listing),
    }


# ---------------------------------------------------------------------------
#   The local model's contract and the quote validator
# ---------------------------------------------------------------------------

#: The exact shape the local model is asked to fill. Nothing here is trusted
#: until validate_model_output() has checked it: every quote must be a real
#: substring of a review, and the engine computes its own counts and verdict.
MODEL_CONTRACT = {
    "task": ("Read the reviews and describe what buyers agree on and complain about, "
             "with quotes copied exactly from the reviews. Do not judge whether any "
             "review is fake. Do not give a score or a probability."),
    "output": {
        "aspects": [
            {
                "aspect": "short plain label, 3-80 characters (for example 'battery life')",
                "stance": "positive | negative | mixed",
                "quotes": ["1-2 exact word-for-word quotes from the reviews"],
            }
        ],
        "set_aside": [
            {"review": "the review number as printed", "reason": "short plain reason, ≤160 characters"}
        ],
        "could_not_check": ["one short plain sentence each, ≤200 characters"],
    },
    "rules": [
        "Every quote must be copied exactly from one review's title or text; a paraphrase or a "
        "phrase joined across the title and body is not a quote, and a quote must be at least "
        "8 characters.",
        "Do not call a review fake; say what you noticed and leave the judgement to the owner.",
        "Do not include a score, a probability or a trust number.",
        "Keep each aspect label short and plain; one aspect per line.",
        "It is fine to return no aspects when the reviews do not support any.",
    ],
}

MODEL_STANCES = ("positive", "negative", "mixed")


def quote_is_real(quote, reviews) -> bool:
    """True only when the quote is a real substring of ONE review's title OR
    body after whitespace normalisation (case and punctuation must match), and
    long enough to be a meaningful quote.

    The title and body are checked separately on purpose: joining them would
    accept an invented phrase made from the end of the title and the start of
    the body."""
    wanted = normalize_whitespace(quote)
    if len(wanted) < MIN_QUOTE_CHARS:
        return False
    for record in reviews:
        if wanted in review_title(record) or wanted in review_body(record):
            return True
    return False


def _valid_quote(quote, reviews) -> str:
    text = normalize_whitespace(quote)
    if not text or len(text) < MIN_QUOTE_CHARS or len(text) > 300:
        return ""
    return text if quote_is_real(text, reviews) else ""


def validate_model_output(model, reviews) -> dict:
    """Check what the local model proposed, accept only what is real.

    Quotes: a proposed quote is accepted only when it is a real substring of a
    review after whitespace normalisation; invented quotes are dropped and
    counted (`quotes_dropped`). An aspect with no real quote is dropped and
    counted (`aspects_dropped`). Set-aside entries need a review number that
    exists and a short reason; a proposed quote there is checked against that
    review. `could_not_check` lines are length-bounded plain sentences.

    Nothing here trusts a model number: the contract asks for no score, and
    any extra numeric fields the model returns are ignored."""
    result = {
        "used": False,
        "why": "",
        "aspects": [],
        "set_aside": [],
        "could_not_check": [],
        "quotes_accepted": 0,
        "quotes_dropped": 0,
        "aspects_dropped": 0,
        "set_aside_dropped": 0,
    }
    if not isinstance(model, dict):
        result["why"] = "no reading-model output was passed in"
        return result
    result["used"] = True
    by_index = {record["index"]: record for record in reviews}
    aspects = model.get("aspects")
    if isinstance(aspects, list):
        for proposed in aspects[:MODEL_MAX_ASPECTS]:
            if not isinstance(proposed, dict):
                result["aspects_dropped"] += 1
                continue
            label = _clean_text(proposed.get("aspect"), 80)
            stance = normalize_whitespace(proposed.get("stance")).lower()
            if len(label) < 3 or stance not in MODEL_STANCES:
                result["aspects_dropped"] += 1
                continue
            quotes = proposed.get("quotes")
            accepted = []
            if isinstance(quotes, list):
                for quote in quotes[:MODEL_QUOTES_PER_ASPECT]:
                    checked = _valid_quote(quote, reviews)
                    if checked:
                        accepted.append(checked)
                        result["quotes_accepted"] += 1
                    else:
                        result["quotes_dropped"] += 1
            if not accepted:
                result["aspects_dropped"] += 1
                continue
            result["aspects"].append({"aspect": label, "stance": stance,
                                      "quotes": accepted})
    set_aside = model.get("set_aside")
    if isinstance(set_aside, list):
        for proposed in set_aside[:MODEL_MAX_SET_ASIDE]:
            if not isinstance(proposed, dict):
                result["set_aside_dropped"] += 1
                continue
            try:
                number = int(proposed.get("review"))
            except (TypeError, ValueError):
                result["set_aside_dropped"] += 1
                continue
            index = number - 1
            reason = _clean_text(proposed.get("reason"), 160)
            if index not in by_index or len(reason) < 3:
                result["set_aside_dropped"] += 1
                continue
            proposed_quote = _clean_text(proposed.get("quote"), 300)
            if proposed_quote:
                target = by_index[index]
                checked = _valid_quote(proposed_quote, [target])
                if checked:
                    result["quotes_accepted"] += 1
                    quote = checked
                else:
                    result["quotes_dropped"] += 1
                    quote = ""
            else:
                quote = ""
            result["set_aside"].append({"review_index": index,
                                        "reviewer": by_index[index]["reviewer"],
                                        "reason": reason, "quote": quote or None})
    lines = model.get("could_not_check")
    if isinstance(lines, list):
        for line in lines[:MODEL_MAX_COULD_NOT_CHECK]:
            text = _clean_text(line, 200)
            if len(text) >= 3:
                result["could_not_check"].append(text)
    if not (result["aspects"] or result["set_aside"] or result["could_not_check"]):
        result["why"] = "the model's answer had nothing that could be checked"
    return result


def aspect_mentions(reviews, aspect: str, quotes=()) -> int:
    """How many readable reviews mention an aspect, deterministically.

    A review counts when its words contain one of the aspect label's longer
    words (at least 4 letters, not a stopword) or one of the accepted quotes.
    This is a word match, not a sentiment judgement; the report says so."""
    tokens = {w for w in _words(aspect) if len(w) >= 4 and w not in STOPWORDS}
    accepted = [normalize_whitespace(q) for q in quotes if normalize_whitespace(q)]
    count = 0
    for record in reviews:
        text = review_text(record).lower()
        if any(token in text for token in tokens):
            count += 1
        elif any(quote in review_text(record) for quote in accepted):
            count += 1
    return count


# ---------------------------------------------------------------------------
#   Flags: every review the rules noticed, with the rule that noticed it
# ---------------------------------------------------------------------------

def collect_flags(reviews, signals, validated) -> list:
    """One entry per review a rule noticed, with every reason, in input order.

    This is the "set aside, and why" list: nothing is removed from the sample,
    the owner sees each flagged review with its snippet, and the model's own
    suggestions are only appended to the deterministic reasons. A flagged
    review is never called fake or paid."""
    by_index = defaultdict(list)
    for signal in signals.values():
        for flag in signal.get("flags", []):
            if 0 <= flag["index"] < len(reviews):
                by_index[flag["index"]].append(flag["reason"])
    for suggestion in validated.get("set_aside", []):
        index = suggestion["review_index"]
        if 0 <= index < len(reviews):
            by_index[index].append("the reading model suggested a closer look: "
                                   + suggestion["reason"])
    out = []
    for index in sorted(by_index):
        record = reviews[index]
        out.append({
            "reviewer": record["reviewer"],
            "rating": record["rating"],
            "verified": record["verified"],
            "vine": record["vine"],
            "date": record["date"],
            "reasons": by_index[index],
            "snippet": _snippet(record),
        })
    return out


# ---------------------------------------------------------------------------
#   The report builder
# ---------------------------------------------------------------------------

def _enough_data(reviews, signals) -> bool:
    """Enough readable reviews and real body words to summarise honestly.
    A title alone is not review text, so title-only records do not count."""
    words = sum(_word_count(review_body(r)) for r in reviews)
    return len(reviews) >= MIN_REVIEWS and words >= MIN_TEXT_WORDS_TOTAL


def _aspects_section(validated, reviews) -> dict:
    if not validated.get("used"):
        return {"available": False, "why": validated.get("why") or "no model output",
                "agreed": [], "complained": [], "mixed": []}
    agreed, complained, mixed = [], [], []
    for aspect in validated.get("aspects", []):
        entry = {
            "aspect": aspect["aspect"],
            "stance": aspect["stance"],
            "quotes": aspect["quotes"],
            "mentioned_in": aspect_mentions(reviews, aspect["aspect"], aspect["quotes"]),
            "of": len(reviews),
        }
        if aspect["stance"] == "positive":
            agreed.append(entry)
        elif aspect["stance"] == "negative":
            complained.append(entry)
        else:
            mixed.append(entry)
    return {"available": True, "why": "", "agreed": agreed,
            "complained": complained, "mixed": mixed}


def _verdict(reviews, signals, flags, enough, aspects) -> dict:
    """A small, deterministic summary OF THE RULES, never a trust number."""
    risks = []
    if not enough:
        return {
            "code": "not_enough_data",
            "words": ("Not enough trustworthy data to summarise this product: only "
                      f"{len(reviews)} readable review(s). Read or paste more reviews, "
                      "then run the check again."),
            "reasons": [],
            "what_would_change_it": [
                f"read or paste at least {MIN_REVIEWS} reviews",
                "include reviews with more than a title, so there are real words to compare",
                "include the review dates that are shown on the page",
            ],
        }
    duplicate = signals.get("near_duplicate_wording", {}).get("counts", {})
    incentive = signals.get("incentive_language", {}).get("counts", {})
    verified = signals.get("verified_purchase_share", {}).get("counts", {})
    vine = signals.get("vine_share", {}).get("counts", {})
    burst = signals.get("date_burstiness", {}).get("counts", {})
    mismatch = signals.get("review_product_mismatch", {}).get("counts", {})
    stylometry = signals.get("stylometry", {}).get("counts", {})
    if duplicate.get("duplicate_groups", 0) >= 1 and \
            duplicate.get("reviews_flagged", 0) >= max(2, int(0.25 * len(reviews))):
        risks.append("a group of reviews shares most of its wording")
    if incentive.get("reviews_flagged", 0) >= 2:
        risks.append("more than one review mentions an incentive or discount")
    if burst.get("reviews_on_burst_days", 0) >= max(2, int(0.25 * len(reviews))):
        risks.append("several reviews sit in a short burst of dates")
    if vine.get("vine_share") is not None and vine["vine_share"] >= HIGH_VINE_SHARE:
        risks.append("a large share of the reviews carry the Vine free-product label")
    if verified.get("verified_share") is not None and \
            verified["verified_share"] < LOW_VERIFIED_SHARE:
        risks.append("fewer than half of the reviews that say are verified purchases")
    if mismatch.get("before_release", 0) or mismatch.get("conflicting_variant", 0):
        risks.append("some reviews may describe a different product or variant")
    if stylometry.get("max_superlatives_per_100", 0) >= SUPERLATIVE_PER_100_FLAG:
        risks.append("at least one review is mostly superlatives without concrete details")
    if not risks:
        code = "looks_solid"
        words = ("No manipulation pattern reached the report's thresholds in the reviews you "
                 "could read. That is not a guarantee: the sample is only what Amazon chose to "
                 "show, and paid reviews can leave no visible pattern.")
    elif len(risks) == 1:
        code = "mixed"
        words = ("The report found one reason to look more closely: " + risks[0] + ". "
                 "One pattern is not a finding about any review.")
    else:
        code = "risky"
        words = ("The report found several reasons to look more closely: "
                 + "; ".join(risks) + ". These are patterns in the sample, not proof "
                 "that any review was paid for.")
    return {
        "code": code,
        "words": words,
        "reasons": risks,
        "what_would_change_it": [
            "read more reviews, especially recent ones and verified purchases",
            "paste the full review list you browsed instead of one page of it",
            "check independent sources (editorial reviews, other shops) through the "
            "existing readers",
            "look at the price history for a discount that never existed",
        ],
    }


def _could_not_check(validated) -> list:
    lines = list(_ALWAYS_COULD_NOT_CHECK)
    lines.extend(validated.get("could_not_check", []))
    return lines


def _plain_words(report) -> dict:
    sample = report["sample"]
    counts = sample
    headline = (f"Read {counts['readable']} review(s)"
                + (f" out of {counts['raw']} supplied" if counts["skipped"] else "")
                + f". {counts['with_text']} have review text, {counts['dated']} have dates, "
                  f"{counts['verified_known']} say whether the purchase was verified, and "
                  f"{counts['vine_known']} say whether a Vine label is present.")
    sample_lines = [SAMPLE_CAVEAT, headline]
    aspect_lines = []
    for entry in report["aspects"]["agreed"]:
        aspect_lines.append(
            f"Agree: {entry['aspect']} - {entry['mentioned_in']} of {entry['of']} readable "
            f"reviews mention it (word match). Quoted: "
            + " | ".join(f'"{_snippet_text(q, 140)}"' for q in entry["quotes"]))
    for entry in report["aspects"]["complained"]:
        aspect_lines.append(
            f"Complain: {entry['aspect']} - {entry['mentioned_in']} of {entry['of']} readable "
            f"reviews mention it (word match). Quoted: "
            + " | ".join(f'"{_snippet_text(q, 140)}"' for q in entry["quotes"]))
    for entry in report["aspects"]["mixed"]:
        aspect_lines.append(
            f"Mixed: {entry['aspect']} - {entry['mentioned_in']} of {entry['of']} readable "
            f"reviews mention it (word match). Quoted: "
            + " | ".join(f'"{_snippet_text(q, 140)}"' for q in entry["quotes"]))
    if not report["aspects"]["available"]:
        aspect_lines = [report["aspects"]["why"]]
    set_aside = [f"{item['reviewer']}: " + "; ".join(item["reasons"])
                 for item in report["set_aside"]["reviews"]]
    if not set_aside:
        set_aside = ["No review was set aside by the engine's rules."]
    return {
        "headline": headline,
        "sample": sample_lines,
        "agreed": [line for line in aspect_lines if line.startswith("Agree:")]
        or (["Not checked: " + report["aspects"]["why"]] if not report["aspects"]["available"]
            else ["No agreement reached the model's reading."]),
        "complained": [line for line in aspect_lines if line.startswith("Complain:")]
        or (["Not checked: " + report["aspects"]["why"]] if not report["aspects"]["available"]
            else ["No complaint reached the model's reading."]),
        "mixed": [line for line in aspect_lines if line.startswith("Mixed:")]
        or (["Not checked: " + report["aspects"]["why"]] if not report["aspects"]["available"]
            else ["No mixed aspect reached the model's reading."]),
        "set_aside": set_aside,
        "verdict": [report["verdict"]["words"]]
        + [f"What would change this: {item}" for item in report["verdict"]["what_would_change_it"]],
        "could_not_check": report["could_not_check"],
    }


def build_report(raw_reviews, *, listing=None, product=None, model=None) -> dict:
    """The whole report: a stable JSON-able dict plus plain-words lines.

    `raw_reviews` is a list of review records (or {"reviews": [...]}); it is
    read, never mutated. `listing` may carry review_count, rating_counts,
    first_available and title; `product` may carry released, variant, variants
    and keywords; `model` is the local model's reading (validated by
    `validate_model_output`). Nothing here raises for bad input: unreadable
    reviews are skipped and counted, and too few reviews produce the
    first-class "not enough data" outcome instead of a summary."""
    reviews, skipped = normalize_reviews(raw_reviews)
    listing = listing if isinstance(listing, dict) else {}
    product = product if isinstance(product, dict) else {}
    signals = signals_for(reviews, listing=listing, product=product)
    validated = validate_model_output(model, reviews)
    flags = collect_flags(reviews, signals, validated)
    aspects = _aspects_section(validated, reviews)
    enough = _enough_data(reviews, signals)
    verdict = _verdict(reviews, signals, flags, enough, aspects)
    with_text = sum(1 for r in reviews if review_body(r))
    sample = {
        "caveat": SAMPLE_CAVEAT,
        "raw": len(raw_reviews) if isinstance(raw_reviews, list)
        else len(raw_reviews.get("reviews", [])) if isinstance(raw_reviews, dict) else 0,
        "readable": len(reviews),
        "skipped": skipped,
        "with_text": with_text,
        "dated": sum(1 for r in reviews if r["date"]),
        "verified_known": sum(1 for r in reviews if r["verified"] is not None),
        "vine_known": sum(1 for r in reviews if r["vine"] is not None),
        "listing_review_count": listing.get("review_count")
        if isinstance(listing.get("review_count"), int) else None,
    }
    if sample["raw"] and sample["raw"] < sample["readable"]:
        sample["raw"] = sample["readable"]
    report = {
        "engine": {"name": "jarvis_product_research", "version": VERSION,
                   "network": False, "read_only": True,
                   "model": "rule-based signals + validated model reading"},
        "sample": sample,
        "signals": signals,
        "aspects": aspects,
        "set_aside": {"reviews": flags[:MAX_SET_ASIDE], "total": len(flags),
                      "more": max(0, len(flags) - MAX_SET_ASIDE)},
        "verdict": verdict,
        "could_not_check": _could_not_check(validated),
        "model": {key: validated[key] for key in
                  ("used", "why", "quotes_accepted", "quotes_dropped",
                   "aspects_dropped", "set_aside_dropped")},
        "plain_words": {},
    }
    report["plain_words"] = _plain_words(report)
    return report


def json_report(raw_reviews, *, listing=None, product=None, model=None) -> str:
    """The report as stable JSON text: same inputs, same bytes.

    Sorted keys and rounded floats only; nothing here is a trust score, and
    the strings include the caveat and the model's dropped-quote count."""
    return json.dumps(build_report(raw_reviews, listing=listing, product=product,
                                   model=model),
                      sort_keys=True, ensure_ascii=True, indent=2)
