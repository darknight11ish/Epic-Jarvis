"""test_product_research.py - the offline product-check engine
(jarvis_product_research.py; docs/DESIGN-PRODUCT-RESEARCH.md).

    py -3 -B backend/test_product_research.py

EVERY REVIEW IN THIS FILE IS SYNTHETIC. No real dataset text is vendored here:
the public review datasets are share-alike licensed, and a fake/real labelled
sample would also be a claim the engine does not make. The fixtures below are
written to contain the patterns the engine looks for (templated wording, one
day of five-star unverified reviews, incentive wording, Vine labels, generic
superlatives, wrong-variant dates) and a second set written to avoid them.

The suite is pure: no browser, no network, no backend. The network spy patches
socket/urllib at the top of one check and proves the engine never touches them;
a second check parses the module's own source with `ast` and proves it imports
no network or shell module and calls no file/URL opener.
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
import jarvis_product_research as PR  # noqa: E402

FAILED, PASSED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    SKIPPED.append(why)
    print(f"skip  {why}")


# ---------------------------------------------------------------------------
#   Fixtures: one "real-looking" set and one "patterned" set, both synthetic
# ---------------------------------------------------------------------------

#: Six varied reviews: concrete numbers, spread dates, all verified, varied
#: ratings, no incentive wording, no duplicated text, no superlatives. This is
#: what a healthy sample looks like to the rules (not a claim that any real
#: review is honest).
REAL_REVIEWS = [
    {"rating": 4, "date": "2026-08-02", "verified": True, "vine": False,
     "title": "Solid for the price",
     "text": "The battery lasts about 9 hours at half volume and the case fits in my "
             "jacket pocket. The buttons are easy to find in the dark."},
    {"rating": 5, "date": "2026-08-19", "verified": True, "vine": False,
     "title": "Good fit",
     "text": "I measured 14 cm across the palm and the large size fits exactly. The "
             "strap is 2 cm wide and does not slip."},
    {"rating": 3, "date": "2026-09-05", "verified": True, "vine": False,
     "title": "Mixed",
     "text": "Sound is clear but the charging port is loose after 3 months. Customer "
             "support answered in 2 days and sent a replacement cable."},
    {"rating": 2, "date": "2026-09-21", "verified": True, "vine": False,
     "title": "Broke early",
     "text": "The left hinge cracked after 6 weeks of light use. It came with a 1 year "
             "warranty but the return form wanted a 12 digit code."},
    {"rating": 5, "date": "2026-10-02", "verified": True, "vine": False,
     "title": "Works",
     "text": "Charges from 0 to 80 percent in 45 minutes. The 30 cm cable is short but "
             "the 1.5 m one in the box works fine."},
    {"rating": 4, "date": "2026-10-14", "verified": True, "vine": False,
     "title": "Fine",
     "text": "Weighs 240 g on my kitchen scale, close to the listing. The display is "
             "6 cm wide and readable outdoors."},
]

#: Eight synthetic reviews written to hit every rule the engine has: a cloned
#: template posted three times, five-star unverified reviews all on one day,
#: incentive wording, a Vine label, generic superlatives and exclamations.
PATTERNED_REVIEWS = [
    {"rating": 5, "date": "2026-10-20", "verified": False, "vine": False,
     "title": "Amazing",
     "text": "This product is absolutely amazing perfect incredible flawless best thing "
             "ever I love it so much it changed my life completely and everyone should "
             "buy it right now!!!"},
    {"rating": 5, "date": "2026-10-20", "verified": False, "vine": False,
     "title": "Amazing",
     "text": "This product is absolutely amazing perfect incredible flawless best thing "
             "ever I love it so much it changed my life completely and everyone should "
             "buy it right now!!!"},
    {"rating": 5, "date": "2026-10-20", "verified": False, "vine": False,
     "title": "Amazing",
     "text": "This product is absolutely amazing perfect incredible flawless best thing "
             "ever I love it so much it changed my life completely and everyone should "
             "buy it right now!!!"},
    {"rating": 5, "date": "2026-10-20", "verified": False, "vine": False,
     "title": "Free one",
     "text": "Received this product for free in exchange for an honest review. It is "
             "amazing and perfect."},
    {"rating": 5, "date": "2026-10-20", "verified": False, "vine": True,
     "title": "Vine one",
     "text": "The 20 hour battery and 1.5 m cable are good. Vine customer review of "
             "free product."},
    {"rating": 5, "date": "2026-10-20", "verified": False, "vine": False,
     "title": "Code one",
     "text": "Great product! Received a discount code and a free sample too. Works fine."},
    {"rating": 1, "date": "2026-09-01", "verified": True, "vine": False,
     "title": "Broke",
     "text": "The 10 cm strap broke after two weeks. The 2 year warranty was useless."},
    {"rating": 3, "date": "2026-08-15", "verified": True, "vine": False,
     "title": "Not as listed",
     "text": "Battery lasts 5 hours, not the 8 hours in the listing. The 1 m cable is fine."},
]


def _report(reviews=None, **kwargs):
    return PR.build_report(copy.deepcopy(REAL_REVIEWS if reviews is None else reviews), **kwargs)


# ---------------------------------------------------------------------------
# 1. Tolerant review-record schema
# ---------------------------------------------------------------------------

def t_schema_reads_what_it_can():
    record = PR.normalize_review({
        "rating": "4 stars", "date": "2026-10-01T12:30:00Z",
        "verified": "Verified Purchase", "vine": "Vine Customer Review of Free Product",
        "title": "  Nice   thing ", "text": "Line one.\nLine two.",
        "helpful": "12 people found this helpful", "variant": " XL ",
    }, 0)
    check("a full record is read, cleaning whitespace and control characters",
          record["rating"] == 4 and record["date"] == "2026-10-01"
          and record["verified"] is True and record["vine"] is True
          and record["title"] == "Nice thing" and record["text"] == "Line one. Line two."
          and record["helpful"] == 12 and record["variant"] == "XL", record)


def t_schema_tolerates_missing_and_bad_fields():
    record = PR.normalize_review({"rating": "not a rating", "date": "sometime",
                                  "verified": None, "vine": None, "text": "hello"}, 3)
    check("missing and unreadable fields become None, never a guessed value",
          record["rating"] is None and record["date"] is None
          and record["verified"] is None and record["vine"] is None
          and record["title"] == "" and record["variant"] is None, record)
    check("a record's label is its position, never a reviewer's name",
          record["reviewer"] == "Reviewer 4")
    check("long text is capped rather than accepted whole",
          len(PR.normalize_review({"text": "x" * 10000})["text"]) == 6000)


def t_schema_dates_and_flags():
    check("ISO date, ISO timestamp and a written date all normalise",
          PR.normalize_review({"date": "2026-10-01"})["date"] == "2026-10-01"
          and PR.normalize_review({"date": "2026-10-01T12:30:00Z"})["date"] == "2026-10-01"
          and PR.normalize_review({"date": "1 October 2026"})["date"] == "2026-10-01",
          [PR.normalize_review({"date": d})["date"] for d in
           ("2026-10-01", "2026-10-01T12:30:00Z", "1 October 2026")])
    check("an unreadable date is unknown, never defaulted to today",
          PR.normalize_review({"date": "not a date"})["date"] is None)
    check("an impossible calendar date is unknown, not accepted then crashed on",
          all(PR.normalize_review({"date": bad})["date"] is None for bad in
              ("2026-02-31", "31 February 2026", "2025-02-29", "2026-13-01",
               "2026-00-10", "2026-01-00")))
    check("a real leap day is still accepted",
          PR.normalize_review({"date": "2024-02-29"})["date"] == "2024-02-29"
          and PR.normalize_review({"date": "29 February 2024"})["date"] == "2024-02-29")
    check("verified and Vine are read from plain words too",
          PR.normalize_review({"verified": "unverified"})["verified"] is False
          and PR.normalize_review({"vine": "Vine Customer Review"})["vine"] is True
          and PR.normalize_review({"vine": "ordinary review"})["vine"] is False)
    check("an explicit 'No Vine' is an absence, not a Vine label",
          PR.normalize_review({"vine": "No Vine"})["vine"] is False
          and PR.normalize_review({"vine": "not a Vine review"})["vine"] is False)


def t_schema_counts_skips_and_wrapper():
    reviews, skipped = PR.normalize_reviews(
        {"reviews": [{"text": "one"}, "not a review", 3, {"rating": 5}]})
    check("a {reviews: [...]} wrapper is accepted and non-records are counted as skipped",
          len(reviews) == 2 and skipped == 2, (len(reviews), skipped))
    empty, skipped_empty = PR.normalize_reviews(None)
    check("bad input is an empty readable sample, not an exception",
          empty == [] and skipped_empty == 0)
    check("reviewer names supplied by an extractor never reach the report",
          "Jane Doe" not in json.dumps(_report([
              {"rating": 4, "text": "A real enough review with several words in it.",
               "reviewer": "Jane Doe"}])))


# ---------------------------------------------------------------------------
# 2. Determinism and no hidden state
# ---------------------------------------------------------------------------

def t_report_is_deterministic_and_does_not_mutate_input():
    reviews = copy.deepcopy(PATTERNED_REVIEWS)
    before = copy.deepcopy(reviews)
    first = PR.build_report(reviews)
    second = PR.build_report(reviews)
    check("the same input builds the same report twice",
          json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True))
    check("the input records are not changed by building the report",
          reviews == before)
    check("json_report is byte-stable for the same input",
          PR.json_report(reviews) == PR.json_report(reviews))
    check("the report is JSON-serialisable (no sets, tuples or NaN)",
          isinstance(json.dumps(first), str))
    model = {"aspects": [{"aspect": "battery life", "stance": "positive",
                          "quotes": ["The battery lasts about 9 hours at half volume"]}]}
    model_before = copy.deepcopy(model)
    PR.build_report(copy.deepcopy(REAL_REVIEWS), model=model)
    check("the model's answer is not changed either", model == model_before)


# ---------------------------------------------------------------------------
# 3. The signals: each is evidence, and each says when it cannot be checked
# ---------------------------------------------------------------------------

def t_verified_purchase_share():
    reviews = PR.normalize_reviews([
        {"rating": 5, "verified": True}, {"rating": 5, "verified": True},
        {"rating": 4, "verified": True}, {"rating": 5, "verified": False},
        {"rating": 3},
    ])[0]
    signal = PR.signal_verified_purchase_share(reviews)
    check("verified share counts known/unknown separately and flags an unverified 5-star",
          signal["available"] is True
          and signal["counts"]["state_known"] == 4
          and signal["counts"]["state_unknown"] == 1
          and signal["counts"]["verified"] == 3
          and signal["counts"]["verified_share"] == 0.75
          and any(flag["index"] == 3 for flag in signal["flags"]), signal)
    thin = PR.signal_verified_purchase_share(PR.normalize_reviews(
        [{"rating": 5, "verified": True}, {"rating": 4}])[0])
    check("fewer than three badges is 'cannot tell', not a zero share",
          thin["available"] is False and "fewer than 3" in thin["why"], thin)


def t_vine_share():
    reviews = PR.normalize_reviews([
        {"rating": 5, "vine": True}, {"rating": 4, "vine": False},
        {"rating": 3, "vine": False}, {"rating": 5, "vine": False},
    ])[0]
    signal = PR.signal_vine_share(reviews)
    check("Vine share is a count with each Vine review listed",
          signal["available"] is True and signal["counts"]["vine"] == 1
          and signal["counts"]["vine_share"] == 0.25
          and len(signal["flags"]) == 1, signal)
    unknown = PR.signal_vine_share(PR.normalize_reviews([{"rating": 5}])[0])
    check("a sample with no Vine field says it cannot tell", unknown["available"] is False)


def t_incentive_language():
    signal = PR.signal_incentive_language(PR.normalize_reviews([
        {"text": "I received this product for free in exchange for an honest review."},
        {"text": "They sent me a discount code, so I tried it."},
        {"text": "The battery lasts 9 hours and the fit is good."},
    ])[0])
    check("free-product and discount wording is matched and flagged",
          signal["counts"]["matches"] >= 2
          and any("incentive" in flag["reason"] for flag in signal["flags"]), signal)
    check("a matched phrase is quoted from the review, not invented",
          all("phrase" in example for example in signal["examples"]), signal["examples"])
    clean = PR.signal_incentive_language(PR.normalize_reviews(REAL_REVIEWS)[0])
    check("ordinary reviews raise no incentive pattern", clean["counts"]["matches"] == 0)


def t_near_duplicates():
    signal = PR.signal_near_duplicate_wording(PR.normalize_reviews(PATTERNED_REVIEWS)[0])
    check("three cloned reviews become one duplicate group with all three flagged",
          signal["available"] is True and signal["counts"]["duplicate_groups"] == 1
          and signal["counts"]["reviews_flagged"] == 3, signal["counts"])
    clean = PR.signal_near_duplicate_wording(PR.normalize_reviews(REAL_REVIEWS)[0])
    check("distinct reviews are not called duplicates",
          clean["available"] is True and clean["counts"]["duplicate_groups"] == 0,
          clean["counts"])
    short = PR.signal_near_duplicate_wording(PR.normalize_reviews([
        {"text": "It is good and works fine"},
        {"text": "It is good and works fine"},
    ])[0])
    check("short reviews are not compared (too easy to match by accident)",
          short["available"] is False, short)
    check("the shingle helper is deterministic and exact-identity is similarity 1",
          PR._minhash_signature(PR._shingles("one two three four five six seven"))
          == PR._minhash_signature(PR._shingles("one two three four five six seven"))
          and PR._jaccard(PR._shingles("one two three four five six seven"),
                          PR._shingles("one two three four five six seven")) == 1.0)
    two_same = PR.normalize_reviews([
        {"text": "one two three four five six seven eight nine ten eleven twelve thirteen"},
        {"text": "one two three four five six seven eight nine ten eleven twelve thirteen"},
    ])[0]
    counted = PR.signal_near_duplicate_wording(two_same)
    check("the pair count is the number actually compared, not every possible pair",
          counted["counts"]["pairs_possible"] == 1
          and counted["counts"]["pairs_shortlisted"] == 1
          and counted["counts"]["pairs_compared"] == 1
          and counted["counts"]["duplicate_pairs"] == 1, counted["counts"])


def t_date_burstiness():
    signal = PR.signal_date_burstiness(PR.normalize_reviews(PATTERNED_REVIEWS)[0],
                                       listing={"review_count": 100,
                                                "first_available": "2026-01-01"})
    check("one day with many reviews is a burst with its own baseline",
          signal["available"] is True
          and signal["counts"]["busiest_day"] == "2026-10-20"
          and signal["counts"]["max_same_day"] >= 4
          and signal["counts"]["burst_days"] >= 1, signal["counts"])
    check("the listing's review count is the baseline when one is supplied",
          signal["counts"]["baseline_per_day"] is not None
          and signal["counts"]["listing_review_count"] == 100, signal["counts"])
    thin = PR.signal_date_burstiness(PR.normalize_reviews(
        [{"date": "2026-10-01"}, {"date": None}])[0])
    check("fewer than three dates says it cannot tell", thin["available"] is False)
    clean = PR.signal_date_burstiness(PR.normalize_reviews(REAL_REVIEWS)[0])
    check("spread-out dates produce no burst days", clean["counts"]["burst_days"] == 0,
          clean["counts"])
    busy_listing = PR.signal_date_burstiness(PR.normalize_reviews([
        {"date": "2026-10-19", "text": "A body with several words for the sample."},
        {"date": "2026-10-20", "text": "A body with several words for the sample."},
        {"date": "2026-10-20", "text": "A body with several words for the sample."},
        {"date": "2026-10-20", "text": "A body with several words for the sample."},
        {"date": "2026-10-20", "text": "A body with several words for the sample."},
    ])[0], listing={"review_count": 1250, "first_available": "2026-10-19"})
    check("a listing averaging 625 reviews a day does not flag a four-review day",
          busy_listing["counts"]["baseline_per_day"] == 625.0
          and busy_listing["counts"]["burst_days"] == 0, busy_listing["counts"])
    genuine = PR.signal_date_burstiness(PR.normalize_reviews([
        {"date": "2026-05-01"}, {"date": "2026-05-02"}, {"date": "2026-05-03"},
        {"date": "2026-05-04"}, {"date": "2026-05-05"}, {"date": "2026-05-06"},
        {"date": "2026-10-20"}, {"date": "2026-10-20"}, {"date": "2026-10-20"},
        {"date": "2026-10-20"}, {"date": "2026-10-20"}, {"date": "2026-10-20"},
    ])[0], listing={"review_count": 30, "first_available": "2025-01-01"})
    check("a real burst on a quiet listing is flagged, using the stated baseline",
          genuine["counts"]["baseline_source"] == "listing"
          and genuine["counts"]["burst_days"] >= 1
          and genuine["counts"]["reviews_on_burst_days"] == 6, genuine["counts"])
    invalid_only = [{"index": 0, "reviewer": "Reviewer 1", "date": "2026-02-31",
                     "rating": None, "verified": None, "vine": None,
                     "title": "", "text": "", "helpful": None, "variant": None}]
    try:
        invalid_signal = PR.signal_date_burstiness(invalid_only)
        invalid_raised = None
    except Exception as exc:  # pragma: no cover - the bite is the exception path
        invalid_signal, invalid_raised = None, exc
    check("an invalid date given straight to the signal cannot crash it",
          invalid_raised is None and invalid_signal["available"] is False
          and invalid_signal["counts"]["invalid_dates"] == 1, invalid_raised)


def t_rating_histogram():
    reviews = PR.normalize_reviews(REAL_REVIEWS)[0]
    from_reviews = PR.signal_rating_histogram(reviews)
    check("a histogram from the reviews gives shares and a rounded average",
          from_reviews["available"] is True and from_reviews["counts"]["total"] == 6
          and from_reviews["counts"]["average"] == 3.83, from_reviews["counts"])
    from_listing = PR.signal_rating_histogram(reviews, listing={
        "rating_counts": {"5": 90, "4": 5, "3": 3, "2": 1, "1": 1}})
    check("the listing's histogram wins when supplied and is marked as such",
          from_listing["counts"]["source"] == "listing"
          and from_listing["counts"]["total"] == 100
          and from_listing["counts"]["five_star_share"] == 0.90, from_listing["counts"])
    check("a J-shaped listing histogram is called polarised, an even one is not",
          from_listing["counts"]["polarised"] is True
          and from_reviews["counts"]["polarised"] is False)
    thin = PR.signal_rating_histogram(PR.normalize_reviews(
        [{"rating": 5}, {"rating": None}])[0])
    check("fewer than three ratings says it cannot tell", thin["available"] is False)


def t_stylometry():
    signal = PR.signal_stylometry(PR.normalize_reviews(PATTERNED_REVIEWS)[0])
    check("generic superlatives with no concrete details are flagged",
          signal["available"] is True and signal["counts"]["measured"] >= 3
          and signal["counts"]["max_superlatives_per_100"] >= 3
          and any("superlatives" in flag["reason"] for flag in signal["flags"]), signal["counts"])
    clean = PR.signal_stylometry(PR.normalize_reviews(REAL_REVIEWS)[0])
    check("reviews with measurements are not flagged as generic",
          not any("no measurements" in flag["reason"] for flag in clean["flags"]),
          clean["flags"])
    thin = PR.signal_stylometry(PR.normalize_reviews([{"text": "Good."}])[0])
    check("reviews shorter than the minimum say it cannot tell", thin["available"] is False)


def t_product_mismatch():
    reviews = PR.normalize_reviews([
        {"date": "2024-01-01", "text": "The old one worked for a year."},
        {"date": "2026-10-01", "text": "This XL version fits well."},
        {"date": "2026-10-02", "text": "The M size is too small for me."},
    ])[0]
    signal = PR.signal_product_mismatch(reviews, product={
        "released": "2026-06-01", "variant": "XL", "variants": ["XL", "L", "M"]})
    check("a review dated before the release is flagged as a mismatch hint",
          signal["counts"]["before_release"] == 1
          and any("before the product" in flag["reason"] for flag in signal["flags"]), signal)
    check("a different variant token is flagged as a hint",
          signal["counts"]["conflicting_variant"] == 1
          and any("different variant" in flag["reason"] for flag in signal["flags"]), signal)
    unknown = PR.signal_product_mismatch(reviews)
    check("with no product facts the signal says it cannot tell",
          unknown["available"] is False, unknown)


def t_every_signal_has_evidence_shape():
    report = _report(PATTERNED_REVIEWS,
                     listing={"review_count": 10, "first_available": "2026-01-01"})
    check("the report carries all eight signals in a fixed order",
          list(report["signals"]) == list(PR.SIGNAL_NAMES))
    for name, signal in report["signals"].items():
        check(f"signal {name} is an evidence object (counts, thresholds, examples, flags)",
              isinstance(signal["counts"], dict) and isinstance(signal["thresholds"], dict)
              and isinstance(signal["examples"], list) and isinstance(signal["flags"], list)
              and signal["available"] in (True, False)
              and (signal["available"] or bool(signal["why"])), signal)


# ---------------------------------------------------------------------------
# 4. The report's plain-words sections and first-class outcomes
# ---------------------------------------------------------------------------

def t_caveat_is_always_present():
    for reviews in (REAL_REVIEWS, [], PATTERNED_REVIEWS):
        report = _report(reviews)
        caveat = report["sample"]["caveat"]
        check("the report says the sample is what Amazon chose to show, not all reviews",
              "what amazon chose to show" in caveat.lower()
              and "not all of the reviews" in caveat.lower(), caveat)
        check("the caveat is repeated in the plain-words sample lines",
              any("what amazon chose to show" in line.lower()
                  for line in report["plain_words"]["sample"]))


def t_not_enough_data_is_first_class():
    report = _report(PATTERNED_REVIEWS[:2])
    check("two reviews produce the not-enough-data outcome, not a summary",
          report["verdict"]["code"] == "not_enough_data"
          and report["verdict"]["words"].startswith("Not enough trustworthy data"), report["verdict"])
    check("... with what would change it, and no number that reads as a trust score",
          len(report["verdict"]["what_would_change_it"]) >= 2
          and not any(isinstance(value, (int, float))
                      for value in report["verdict"].values()), report["verdict"])
    five_short = [{"rating": 5, "text": "Good."} for _ in range(5)]
    report2 = _report(five_short)
    check("five one-word reviews are still not enough data to summarise",
          report2["verdict"]["code"] == "not_enough_data", report2["verdict"]["code"])
    check("the not-enough report still carries the sample caveat and what was not checked",
          report2["sample"]["caveat"] and report2["could_not_check"])


def t_what_buyers_agree_and_complain_about():
    model = {
        "aspects": [
            {"aspect": "battery life", "stance": "positive",
             "quotes": ["The battery lasts about 9 hours at half volume"]},
            {"aspect": "charging port", "stance": "negative",
             "quotes": ["the charging port is loose after 3 months"]},
            {"aspect": "strap", "stance": "mixed",
             "quotes": ["The strap is 2 cm wide"]},
        ],
    }
    report = _report(model=model)
    check("positive aspects are agreements, negative are complaints, mixed are their own list",
          [entry["aspect"] for entry in report["aspects"]["agreed"]] == ["battery life"]
          and [entry["aspect"] for entry in report["aspects"]["complained"]] == ["charging port"]
          and [entry["aspect"] for entry in report["aspects"]["mixed"]] == ["strap"],
          report["aspects"])
    check("every accepted aspect carries a validated quote and a word-match count",
          all(entry["quotes"] and isinstance(entry["mentioned_in"], int)
              and entry["of"] == 6 for entry in report["aspects"]["agreed"]))
    check("the plain words label a mixed stance Mixed, not Complain",
          report["plain_words"]["sample"][0] == PR.SAMPLE_CAVEAT
          and any(line.startswith("Agree:") for line in report["plain_words"]["agreed"])
          and any(line.startswith("Complain:") for line in report["plain_words"]["complained"])
          and any(line.startswith("Mixed:") for line in report["plain_words"]["mixed"]))


def t_no_aspects_without_a_model():
    report = _report(REAL_REVIEWS)
    check("without a reading model the aspect section says not checked",
          report["aspects"]["available"] is False
          and "not checked" in " ".join(report["plain_words"]["agreed"]).lower()
          and report["model"]["used"] is False, report["aspects"])


def t_set_aside_and_why_without_removing_anything():
    report = _report(PATTERNED_REVIEWS)
    check("every rule-noticed review is listed with its reasons and a snippet",
          report["set_aside"]["total"] >= 4
          and all(item["reasons"] and item["snippet"]
                  for item in report["set_aside"]["reviews"]), report["set_aside"])
    check("nothing is removed from the sample: the readable count is the input count",
          report["sample"]["readable"] == len(PATTERNED_REVIEWS))
    check("a flagged review is never labelled fake - only reasons are shown",
          not any("fake" in json.dumps(item).lower()
                  for item in report["set_aside"]["reviews"]))
    check("the plain words show the set-aside list too",
          isinstance(report["plain_words"]["set_aside"], list)
          and report["plain_words"]["set_aside"])


def t_could_not_check_is_explicit():
    report = _report(REAL_REVIEWS)
    lines = " ".join(report["could_not_check"]).lower()
    check("the report says reviewer profiles and undisclosed payment cannot be checked",
          "reviewer profiles" in lines and "paid or refunded" in lines)
    check("it says only the reviews the reader could see are included",
          "only the reviews you could read" in lines)
    check("the plain words carry the same list", report["plain_words"]["could_not_check"])


def t_no_numeric_trust_score_anywhere():
    report = _report(PATTERNED_REVIEWS, listing={"review_count": 50,
                                                 "first_available": "2026-01-01"},)
    banned = ("score", "probability", "confidence", "trust")

    def walk(obj, path=""):
        """Banned words anywhere in a path, and any NUMBER whose path is
        about a trust/score/probability/confidence or the verdict. A string
        that merely contains a banned word is not a score, so this looks at
        keys and numeric leaves, not at prose."""
        found = []
        if isinstance(obj, dict):
            for key, value in obj.items():
                key_path = f"{path}/{key}"
                lowered = str(key).lower()
                if any(word in lowered for word in banned):
                    found.append(key_path)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    if any(word in key_path.lower() for word in banned + ("verdict",)):
                        found.append(f"{key_path}={value}")
                found.extend(walk(value, key_path))
        elif isinstance(obj, list):
            for position, value in enumerate(obj):
                found.extend(walk(value, f"{path}[{position}]"))
        return found

    found = walk(report)
    check("the whole report JSON has no trust/score key and no numeric value on a trust path",
          found == [] and "trust_score" not in json.dumps(report), found)
    poisoned = {"verdict": {"trust_score": 0.93}, "signal": {"confidence": 0.5}}
    check("... and the scan really does bite on a numeric score under a benign name",
          walk(poisoned) != [], walk(poisoned))
    check("the verdict is a rule summary with no numeric fields",
          isinstance(report["verdict"]["words"], str)
          and isinstance(report["verdict"]["reasons"], list)
          and all(isinstance(reason, str) for reason in report["verdict"]["reasons"])
          and set(report["verdict"]) == {"code", "words", "reasons", "what_would_change_it"})


def t_engine_metadata():
    report = _report(REAL_REVIEWS)
    check("the engine names itself, its version and that it is read-only with no network",
          report["engine"]["name"] == "jarvis_product_research"
          and report["engine"]["version"] == PR.VERSION
          and report["engine"]["network"] is False
          and report["engine"]["read_only"] is True, report["engine"])


# ---------------------------------------------------------------------------
# 5. The local model contract and the quote validator
# ---------------------------------------------------------------------------

def t_model_contract_shape():
    output = PR.MODEL_CONTRACT["output"]
    check("the model contract asks for aspects with a label, a stance and quotes",
          "aspects" in output and "stance" in output["aspects"][0]
          and "quotes" in output["aspects"][0])
    check("the contract forbids a score and requires exact quotes",
          any("score" in rule.lower() for rule in PR.MODEL_CONTRACT["rules"])
          and any("exactly" in rule.lower() for rule in PR.MODEL_CONTRACT["rules"]))
    check("the stance values are fixed", PR.MODEL_STANCES == ("positive", "negative", "mixed"))


def t_quote_validator_bites():
    reviews = PR.normalize_reviews(REAL_REVIEWS)[0]
    check("a real quote is accepted",
          PR.quote_is_real("The battery lasts about 9 hours at half volume", reviews))
    check("a real quote with different whitespace is still accepted",
          PR.quote_is_real("The  battery lasts   about 9 hours at half volume", reviews))
    check("a quote from a review's title is accepted",
          PR.quote_is_real("Solid for the price", reviews))
    check("a quote with changed case is NOT accepted (not the reviewer's words)",
          not PR.quote_is_real("the battery lasts about 9 hours at half volume", reviews))
    check("a paraphrase is NOT accepted", not PR.quote_is_real(
        "The battery runs for around nine hours", reviews))
    check("an empty quote is NOT accepted", not PR.quote_is_real("   ", reviews))
    check("a reviewer's name is never a quote source", not PR.quote_is_real("Jane Doe", reviews))
    boundary = PR.normalize_reviews([{
        "rating": 4, "title": "Great",
        "text": "battery lasts about nine hours and the fit is good"}])[0][0]
    check("a quote spanning the title and body boundary is NOT accepted",
          not PR.quote_is_real("Great battery", [boundary]))
    check("the same words inside one field ARE accepted",
          PR.quote_is_real("battery lasts about", [boundary])
          and PR.quote_is_real("Great", [boundary]) is False)
    check("a one-character or four-character fragment is not a quote",
          not PR.quote_is_real("G", reviews) and not PR.quote_is_real("Good", reviews))


def t_model_output_validation_drops_invented_quotes():
    reviews = PR.normalize_reviews(REAL_REVIEWS)[0]
    validated = PR.validate_model_output({
        "aspects": [
            {"aspect": "battery life", "stance": "positive",
             "quotes": ["The battery lasts about 9 hours at half volume",
                        "This paragraph was never in any review at all"]},
            {"aspect": "invented aspect", "stance": "positive",
             "quotes": ["Only invented words here"]},
        ],
        "set_aside": [{"review": 2, "reason": "the wording repeats another review"},
                      {"review": 999, "reason": "no such review"},
                      {"review": 1, "reason": ""}],
        "could_not_check": ["whether the seller paid for the review"],
        "trust_score": 0.93,
        "confidence": "high",
        "verdict": "looks fake",
    }, reviews)
    check("one invented quote is dropped and counted; the real one is kept",
          validated["quotes_dropped"] == 2 and validated["quotes_accepted"] == 1, validated)
    check("an aspect left with no real quote is dropped and counted",
          validated["aspects_dropped"] == 1 and len(validated["aspects"]) == 1, validated)
    check("set-aside entries need a real review number and a reason",
          len(validated["set_aside"]) == 1
          and validated["set_aside"][0]["reviewer"] == "Reviewer 2", validated["set_aside"])
    check("the model's own score/confidence/verdict are ignored, not reported",
          "trust_score" not in json.dumps(_report(model={"trust_score": 0.93}))
          and "confidence" not in json.dumps(_report(model={"confidence": "high"})))


def t_aspect_validation_appears_in_the_report():
    model = {"aspects": [
        {"aspect": "battery life", "stance": "positive",
         "quotes": ["The battery lasts about 9 hours at half volume", "not a real quote"]},
    ], "could_not_check": ["whether the seller shaped the wording"]}
    report = _report(model=model)
    check("a dropped quote is counted in the report's model section",
          report["model"]["quotes_dropped"] == 1
          and report["model"]["quotes_accepted"] == 1, report["model"])
    check("the model's could-not-check line is carried into the report",
          "whether the seller shaped the wording" in report["could_not_check"])
    check("the accepted quote appears as evidence, the invented one does not",
          "The battery lasts about 9 hours at half volume"
          in json.dumps(report["aspects"])
          and "not a real quote" not in json.dumps(report["aspects"]))


# ---------------------------------------------------------------------------
# 6. Network: nothing dials out, and the module cannot
# ---------------------------------------------------------------------------

def t_network_spy():
    calls = []
    real_socket = socket.socket
    real_create = socket.create_connection
    real_urlopen = urllib.request.urlopen
    real_http = http.client.HTTPConnection

    def spy_socket(*args, **kwargs):
        calls.append("socket")
        raise AssertionError("the engine tried to open a socket")

    def spy_create(*args, **kwargs):
        calls.append("create_connection")
        raise AssertionError("the engine tried to connect somewhere")

    def spy_urlopen(*args, **kwargs):
        calls.append("urlopen")
        raise AssertionError("the engine tried to read a URL")

    def spy_http(*args, **kwargs):
        calls.append("http")
        raise AssertionError("the engine tried to build an HTTP connection")

    try:
        socket.socket = spy_socket
        socket.create_connection = spy_create
        urllib.request.urlopen = spy_urlopen
        http.client.HTTPConnection = spy_http
        _report(PATTERNED_REVIEWS, listing={"review_count": 10,
                                            "first_available": "2026-01-01"})
        PR.signals_for(PR.normalize_reviews(FAKE_FOR_NETWORK)[0])
        _report(REAL_REVIEWS, model={"aspects": [{"aspect": "battery life",
                                                  "stance": "positive",
                                                  "quotes": ["The battery lasts about "
                                                             "9 hours at half volume"]}]})
    finally:
        socket.socket = real_socket
        socket.create_connection = real_create
        urllib.request.urlopen = real_urlopen
        http.client.HTTPConnection = real_http
    check("the engine made no socket, connection, URL or HTTP call", calls == [], calls)


#: A tiny fixture for the network spy (kept separate from the main sets).
FAKE_FOR_NETWORK = [{"rating": 5, "text": "The battery lasts 9 hours and the fit is good."}]


def t_module_source_imports_and_calls_are_clean():
    # The stronger check the design claims: parse the module's OWN source and
    # look at every import and every call. A read_text() pin would go red on a
    # rename; this AST walk asks the question the claim is about.
    tree = ast.parse(inspect.getsource(PR))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    check("the engine source imports only datetime, hashlib, json, re and collections",
          roots == {"__future__", "datetime", "hashlib", "json", "re", "collections"},
          sorted(roots))
    forbidden_roots = {"socket", "urllib", "http", "requests", "subprocess", "os",
                       "pathlib", "playwright", "selenium", "webbrowser"}
    check("the source imports no network, browser, storage or process module",
          not (roots & forbidden_roots), sorted(roots & forbidden_roots))
    calls = {node.func.id for node in ast.walk(tree)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    forbidden_calls = {"open", "urlopen", "system", "popen", "exec", "eval", "compile"}
    check("the source calls no file/URL opener and no shell",
          not (calls & forbidden_calls), sorted(calls & forbidden_calls))
    # Prove the scan would catch a forbidden import/call, not just pass silently.
    bad_tree = ast.parse("import socket\nsocket.socket()\nopen('x')")
    bad_roots = {alias.name.split(".")[0] for node in ast.walk(bad_tree)
                 if isinstance(node, ast.Import) for alias in node.names}
    bad_calls = {node.func.id for node in ast.walk(bad_tree)
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    check("... and the same scan would fail on a forbidden import or call",
          bool(bad_roots & forbidden_roots) and bool(bad_calls & forbidden_calls),
          (bad_roots, bad_calls))


# ---------------------------------------------------------------------------
# 7. The known-pattern and known-clean fixtures behave as designed
# ---------------------------------------------------------------------------

def t_known_clean_fixture_is_not_flagged():
    report = _report(REAL_REVIEWS, listing={"review_count": 240,
                                            "first_available": "2025-01-01"})
    check("the synthetic clean sample reaches no manipulation threshold",
          report["verdict"]["code"] == "looks_solid", report["verdict"])
    check("... and it still says a clean-looking sample is not a guarantee",
          "not a guarantee" in report["verdict"]["words"].lower(), report["verdict"])


def t_known_patterned_fixture_is_flagged_with_reasons():
    report = _report(PATTERNED_REVIEWS,
                     listing={"review_count": 30, "first_available": "2026-01-01"})
    check("the patterned sample has several named reasons, and the verdict says why",
          report["verdict"]["code"] == "risky" and len(report["verdict"]["reasons"]) >= 2
          and "not proof" in report["verdict"]["words"].lower(), report["verdict"])
    check("the duplicated reviews are named by their reviewers in set-aside",
          any("wording overlaps" in reason
              for item in report["set_aside"]["reviews"] for reason in item["reasons"]))


# ---------------------------------------------------------------------------
#   Runner
# ---------------------------------------------------------------------------



def t_invalid_dates_never_crash_the_report():
    bad_dates = ("2026-02-31", "31 February 2026", "2025-02-29", "2026-13-01",
                 "2026-00-10", "2026-01-00")
    bad_reviews = [
        {"rating": 5, "date": raw,
         "title": "Title with a date", "text": "Body text with enough words to read."}
        for raw in bad_dates
    ]
    try:
        report = PR.build_report(bad_reviews)
        raised = None
    except Exception as exc:  # pragma: no cover - the bite is the exception path
        report, raised = None, exc
    check("a report full of impossible dates builds instead of raising", raised is None, raised)
    check("every impossible date is counted unknown, not dated",
          report is not None and report["sample"]["dated"] == 0
          and report["signals"]["date_burstiness"]["available"] is False,
          report and report["sample"])
    check("the impossible-date report still carries the caveat and what could not be checked",
          report is not None and report["sample"]["caveat"] and report["could_not_check"])
    leap = PR.build_report([
        {"rating": 5, "date": "2024-02-29",
         "title": "A real leap day", "text": "Body text with enough words to read."},
        {"rating": 4, "date": "2024-03-01",
         "title": "Another day", "text": "Body text with enough words to read."},
        {"rating": 3, "date": "2024-03-02",
         "title": "And another", "text": "Body text with enough words to read."},
        {"rating": 2, "date": "2024-03-03",
         "title": "Still another", "text": "Body text with enough words to read."},
        {"rating": 4, "date": "2024-03-04",
         "title": "One more day", "text": "Body text with enough words to read."},
    ])
    check("a real leap day is dated, not discarded", leap["sample"]["dated"] == 5,
          leap["sample"])


def t_short_and_cross_field_quotes_are_dropped():
    reviews = PR.normalize_reviews([{
        "rating": 4, "title": "Great",
        "text": "battery lasts about nine hours and the fit is good"}])[0]
    validated = PR.validate_model_output({
        "aspects": [
            {"aspect": "battery life", "stance": "positive",
             "quotes": ["Great battery", "battery lasts about nine hours"]},
            {"aspect": "tiny quote", "stance": "positive", "quotes": ["G"]},
        ],
    }, reviews)
    check("a cross-field quote and a one-character quote are both dropped and counted",
          validated["quotes_dropped"] == 2 and validated["quotes_accepted"] == 1, validated)
    check("the one real quote keeps its aspect; the short-only aspect is dropped",
          len(validated["aspects"]) == 1 and validated["aspects_dropped"] == 1
          and validated["aspects"][0]["quotes"] == ["battery lasts about nine hours"])


def t_with_text_counts_bodies_only():
    title_only = [{"rating": 4, "title": f"Title number {i}"} for i in range(6)]
    report = _report(title_only)
    check("title-only reviews do not count as having review text",
          report["sample"]["with_text"] == 0
          and "have review text" in report["plain_words"]["headline"], report["sample"])
    with_bodies = [{"rating": 4, "title": f"Title number {i}",
                    "text": "A body with several real words in it."} for i in range(6)]
    report2 = _report(with_bodies)
    check("a body counts for with_text; six bodies means six",
          report2["sample"]["with_text"] == 6, report2["sample"])

TESTS = (
    t_schema_reads_what_it_can,
    t_schema_tolerates_missing_and_bad_fields,
    t_schema_dates_and_flags,
    t_schema_counts_skips_and_wrapper,
    t_report_is_deterministic_and_does_not_mutate_input,
    t_verified_purchase_share,
    t_vine_share,
    t_incentive_language,
    t_near_duplicates,
    t_date_burstiness,
    t_rating_histogram,
    t_stylometry,
    t_product_mismatch,
    t_every_signal_has_evidence_shape,
    t_caveat_is_always_present,
    t_not_enough_data_is_first_class,
    t_what_buyers_agree_and_complain_about,
    t_no_aspects_without_a_model,
    t_set_aside_and_why_without_removing_anything,
    t_could_not_check_is_explicit,
    t_no_numeric_trust_score_anywhere,
    t_engine_metadata,
    t_model_contract_shape,
    t_quote_validator_bites,
    t_model_output_validation_drops_invented_quotes,
    t_aspect_validation_appears_in_the_report,
    t_network_spy,
    t_module_source_imports_and_calls_are_clean,
    t_invalid_dates_never_crash_the_report,
    t_short_and_cross_field_quotes_are_dropped,
    t_with_text_counts_bodies_only,
    t_known_clean_fixture_is_not_flagged,
    t_known_patterned_fixture_is_flagged_with_reasons,
)


def main() -> int:
    for test in TESTS:
        print(f"\n--- {test.__name__} ---")
        try:
            test()
        except Exception:
            FAILED.append(test.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
