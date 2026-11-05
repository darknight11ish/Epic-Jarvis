"""test_source_independence.py - the per-source independence layer
(jarvis_source_independence.py).

    py -3 -B backend/test_source_independence.py

EVERY PAGE IN THIS FILE IS SYNTHETIC. No real article, video page or link is
vendored, no URL is fetched and nothing is opened: the fixtures are hand-written
page shapes, and every address is on an `.example` host. The suite proves the
disclosure paths (present, absent, mixed, negated, contextual), the link paths
(affiliate, tracking-only, shop tag, shortener, redirect wrapper), the four
source kinds, `cannot_tell` for an empty page and a JavaScript shell, the closed
verdict vocabulary, the no-score rule, ranking and the plain-words agreement
summary, determinism and non-mutation, and that the module imports nothing that
can reach the network, a browser, a file or a process.

WHAT THIS FILE DELIBERATELY DOES NOT DO
It does not pin a probability, a percentage or a trust score, because there is
none to pin: the module's own no-score test fails on one. It does not fetch a
page, resolve a shortened link or open a redirect - that is exactly what the
module reports it cannot do.
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
import jarvis_source_independence as SOURCE  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


# ---------------------------------------------------------------------------
#  Synthetic page fixtures
# ---------------------------------------------------------------------------

#: Enough readable words to be checked rather than reported as too thin.
BODY = ("This independent review covered the widget for three weeks of daily "
        "use. ") * 8


def _page(body="", *, title="Widget review", description="", script="",
          head_extra="", tail=""):
    """One synthetic page. The title is just the tab title, never article text."""
    meta = (f'<meta name="description" content="{description}">'
            if description else "")
    return (f"""<!doctype html>
<html><head>
<title>{title}</title>
{meta}{head_extra}
</head><body>
<p>{BODY}</p>
{body}
{script}
{tail}
</body></html>""")


def _link(href, text="the shop"):
    return f'<a href="{href}">{text}</a>'


CLEAN = _page("")

SPONSORED = _page(
    "<p>This post is sponsored by Acme.</p>"
    "<p>Acme paid for the testing bench.</p>")

GIFTED = _page(
    "<p>They gifted this unit to us.</p>"
    "<p>We also received a free product for the follow-up piece.</p>")

AD_LABEL = _page('<p>Our verdict is below.</p><p>#ad</p>')

MIXED = _page(
    "<p>This post is sponsored by Acme.</p>"
    "<p>They gifted us the unit, and #ad appears in the caption.</p>")

AFFILIATE_LINK = 'https://www.amazon.example/dp/B0TEST0001?tag=jarvis-20'
AFFILIATE = _page(f"<p>Read the full verdict below.</p>{_link(AFFILIATE_LINK)}")

AFFILIATE_DISCLOSED = _page(
    "<p>We may earn a commission from the links below.</p>"
    + _link(AFFILIATE_LINK))

TRACKING = _page(
    "<p>The roundup is below.</p>"
    + _link("https://shop.example/p/1?utm_source=newsletter&utm_medium=email",
            "shop one")
    + _link("https://shop.example/p/2?fbclid=abc123", "shop two")
    + _link("https://shop.example/p/3?gclid=xyz", "shop three"))

SHORTENED = _page("<p>The roundup is below.</p>"
                  + _link("https://bit.ly/abc123", "the winner"))

REDIRECT = _page(
    "<p>The roundup is below.</p>"
    + _link("https://go.example/away?url=https%3A%2F%2Fshop.example%2Fp%2F1",
            "the winner"))

REDIRECT_AFFILIATE = _page(
    "<p>The roundup is below.</p>"
    + _link("https://go.example/away?url=https%3A%2F%2Fwww.amazon.example"
            "%2Fdp%2FB0TEST0001%3Ftag%3Djarvis-20", "the winner"))

VIDEO_PROMOTION = _page("<p>Includes paid promotion</p>",
                        title="Widget review - video")

VIDEO_FLAG = _page(
    "<p>Watch the whole test.</p>",
    script='<script>var ytInitialPlayerResponse = {"paidPromotion":true};</script>',
    title="Widget review - video")

REL_SPONSORED = _page(
    '<p>Our pick is below.</p><a href="/buy" rel="sponsored nofollow">the pick</a>')

NEGATED = _page(
    "<p>This is not sponsored. We bought this ourselves, and there are "
    "no affiliate links here.</p>")

CONTEXTUAL = _page("<p>The artist took a commission for the sculpture.</p>")

SURFACES = _page(
    '<p>Our verdict is below.</p>'
    '<img alt="Gifted by Acme" src="widget.jpg">'
    '<a href="/buy" rel="sponsored">the pick</a>',
    title="Sponsored: widget roundup",
    description="This is an advertisement for the widget.")

URGENCY = _page(
    "<p>Last chance. Today only. Hurry, only 3 left!</p>"
    "<p>The countdown says 01:23:45.</p>")

JS_SHELL = """<!doctype html>
<html><head><title>Best widgets 2026</title></head>
<body><div id="root"></div><script src="app.js"></script></body></html>"""


# ---------------------------------------------------------------------------
#  Small shared helpers for the suite
# ---------------------------------------------------------------------------

def _verdict(html, url="https://reviews.example/p", kind="article"):
    return SOURCE.analyse_source(html, url, kind)


def _where_set(analysis):
    return {d["where"] for d in analysis["disclosures"]}


def _all_keys(value, prefix=""):
    """Every dict key and every list index path, recursively."""
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}"
            yield path, key
            yield from _all_keys(item, path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _all_keys(item, f"{prefix}[{index}]")


def _all_values(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from _all_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _all_values(item)
    else:
        yield value


def _all_floats(value):
    return [item for item in _all_values(value)
            if isinstance(item, float)]


SCORE_KEYS = ("score", "trust", "probability", "confidence", "percent",
              "percentage", "rank_score")


# ---------------------------------------------------------------------------
#  1. Disclosures: absent, present, mixed, negated, contextual
# ---------------------------------------------------------------------------

def t_a_plain_page_has_no_disclosure():
    result = _verdict(CLEAN)
    check("a plain page reports no disclosure",
          result["disclosures"] == [], result["disclosures"])
    check("a plain page reports no affiliate link",
          result["affiliate_links"]["count"] == 0)
    check("a plain page is no_monetisation_evidence",
          result["per_source_verdict"]["verdict"]
          == SOURCE.VERDICT_NO_EVIDENCE,
          result["per_source_verdict"]["verdict"])
    check("its answer says what was checked",
          "readable text" in result["monetisation"]["summary"],
          result["monetisation"]["summary"])


def t_a_sponsorship_disclosure_carries_its_evidence():
    result = _verdict(SPONSORED)
    found = [d for d in result["disclosures"] if d["category"] == "sponsor"]
    check("sponsored wording is found as a sponsor disclosure",
          bool(found), result["disclosures"])
    if found:
        first = found[0]
        check("it keeps the matched phrase",
              "sponsor" in first["phrase"].lower(), first)
        check("it keeps a short snippet of the page's own words",
              "sponsor" in first["snippet"].lower(), first)
        check("it says where the words were found",
              first["where"] == "text", first)
        check("it is marked explicit, not contextual",
              first["strength"] == "explicit", first)
    check("the source is disclosed_sponsored",
          result["per_source_verdict"]["verdict"]
          == SOURCE.VERDICT_DISCLOSED_SPONSORED,
          result["per_source_verdict"]["verdict"])
    check("the evidence sentence names the disclosure",
          any("sponsor" in line.lower()
              for line in result["per_source_verdict"]["evidence"]),
          result["per_source_verdict"]["evidence"])


def t_mixed_disclosures_are_all_listed():
    result = _verdict(MIXED)
    categories = {d["category"] for d in result["disclosures"]}
    check("sponsor and gift wording on one page are both listed",
          {"sponsor", "gift"} <= categories, categories)
    check("#ad is found as an advertisement label",
          "advertisement" in categories, categories)
    check("a page with several disclosures is still disclosed_sponsored",
          result["per_source_verdict"]["verdict"]
          == SOURCE.VERDICT_DISCLOSED_SPONSORED,
          result["per_source_verdict"]["verdict"])
    check("the category counts agree with the disclosure list",
          result["monetisation"]["categories"].get("sponsor", 0) >= 1
          and result["monetisation"]["categories"].get("gift", 0) >= 1,
          result["monetisation"]["categories"])


def t_gift_wording_is_its_own_category():
    result = _verdict(GIFTED)
    gifts = [d for d in result["disclosures"] if d["category"] == "gift"]
    check("gifted and free-product wording are gift disclosures",
          len(gifts) >= 2, result["disclosures"])
    check("a gift disclosure is disclosed_sponsored",
          result["per_source_verdict"]["verdict"]
          == SOURCE.VERDICT_DISCLOSED_SPONSORED,
          result["per_source_verdict"]["verdict"])


def t_a_negated_disclosure_is_the_pages_own_claim():
    result = _verdict(NEGATED)
    check("'not sponsored' is not filed as a disclosure",
          result["disclosures"] == [], result["disclosures"])
    check("it is kept as the page's own independence claim",
          len(result["independence_claims"]) >= 2,
          result["independence_claims"])
    check("the page is still judged on the rest of its evidence",
          result["per_source_verdict"]["verdict"]
          == SOURCE.VERDICT_NO_EVIDENCE,
          result["per_source_verdict"]["verdict"])
    check("the evidence says the claim is the page's word, not proof",
          any("claim independence" in line
              for line in result["per_source_verdict"]["evidence"]),
          result["per_source_verdict"]["evidence"])


def t_contextual_wording_does_not_decide():
    result = _verdict(CONTEXTUAL)
    contextual = [d for d in result["disclosures"]
                  if d["strength"] == "contextual"]
    check("a bare 'commission' is kept as contextual wording",
          bool(contextual), result["disclosures"])
    check("it does not make the source affiliate_only",
          result["per_source_verdict"]["verdict"]
          == SOURCE.VERDICT_NO_EVIDENCE,
          result["per_source_verdict"]["verdict"])
    check("the caveat says what the word does not prove",
          any("commission" in line and "not counted" in line
              for line in result["what_could_not_be_checked"]),
          result["what_could_not_be_checked"])


def t_disclosures_are_found_on_every_surface():
    result = _verdict(SURFACES)
    wheres = _where_set(result)
    check("a disclosure in the tab title is found there",
          "title" in wheres, wheres)
    check("a disclosure in a page description is found there",
          "meta" in wheres, wheres)
    check("a disclosure in an image description is found there",
          "attributes" in wheres, wheres)
    check("a rel=sponsored link is a disclosure on the link",
          "link" in wheres, wheres)
    link_evidence = [d for d in result["disclosures"] if d["where"] == "link"]
    check("the rel=sponsored evidence names the attribute",
          link_evidence and "sponsored" in link_evidence[0]["phrase"],
          link_evidence)


# ---------------------------------------------------------------------------
#  2. Links: affiliate, tracking-only, shop tag, shortener, redirect wrapper
# ---------------------------------------------------------------------------

def t_affiliate_only_is_disclosed():
    result = _verdict(AFFILIATE_DISCLOSED)
    check("the commission wording is an affiliate disclosure",
          any(d["category"] == "affiliate" and d["strength"] == "explicit"
              for d in result["disclosures"]), result["disclosures"])
    check("an affiliate link is counted",
          result["affiliate_links"]["affiliate_count"] == 1,
          result["affiliate_links"])
    check("a disclosed affiliate source is affiliate_only",
          result["per_source_verdict"]["verdict"]
          == SOURCE.VERDICT_AFFILIATE_ONLY,
          result["per_source_verdict"]["verdict"])


def t_affiliate_without_disclosure_is_likely_monetised():
    result = _verdict(AFFILIATE)
    check("the shop tag is counted as an affiliate marker",
          result["affiliate_links"]["affiliate_count"] == 1,
          result["affiliate_links"])
    check("no disclosure is reported",
          result["disclosures"] == [], result["disclosures"])
    check("an undisclosed affiliate source is likely_monetised_undisclosed",
          result["per_source_verdict"]["verdict"]
          == SOURCE.VERDICT_LIKELY_UNDISCLOSED,
          result["per_source_verdict"]["verdict"])
    check("the evidence says the relationship is not disclosed",
          any("No disclosure" in line
              for line in result["per_source_verdict"]["evidence"]),
          result["per_source_verdict"]["evidence"])
    check("the summary says the page can profit without saying so",
          "profit" in result["monetisation"]["summary"],
          result["monetisation"]["summary"])


def t_utm_only_is_tracking_not_affiliate():
    result = _verdict(TRACKING)
    check("all three marked links are listed",
          result["affiliate_links"]["count"] == 3,
          result["affiliate_links"])
    check("none of them is counted as affiliate",
          result["affiliate_links"]["affiliate_count"] == 0,
          result["affiliate_links"])
    check("all three are tracked as plain tracking markers",
          result["affiliate_links"]["by_class"]["tracking"] == 3,
          result["affiliate_links"]["by_class"])
    check("utm and click ids do not decide the verdict",
          result["per_source_verdict"]["verdict"]
          == SOURCE.VERDICT_NO_EVIDENCE,
          result["per_source_verdict"]["verdict"])
    check("the caveat names tracking as not evidence of payment",
          any("tracking markers" in line
              for line in result["what_could_not_be_checked"]),
          result["what_could_not_be_checked"])


def t_a_shop_tag_is_affiliate_but_a_category_tag_is_not():
    shop = _verdict(_page("<p>Our pick is below.</p>"
                          + _link("https://www.amazon.example/dp/B1?tag=abc-20")))
    category = _verdict(
        _page("<p>Our pick is below.</p>"
              + _link("https://blog.example/posts?tag=recipes")))
    check("a shop associate tag is affiliate evidence",
          shop["affiliate_links"]["affiliate_count"] == 1,
          shop["affiliate_links"])
    check("a category tag on an ordinary page is not affiliate evidence",
          category["affiliate_links"]["affiliate_count"] == 0,
          category["affiliate_links"])
    check("the category tag alone leaves the source clean",
          category["per_source_verdict"]["verdict"]
          == SOURCE.VERDICT_NO_EVIDENCE,
          category["per_source_verdict"]["verdict"])


def t_a_shortened_link_is_masked_not_resolved():
    result = _verdict(SHORTENED)
    examples = result["affiliate_links"]["examples"]
    check("the shortened link is listed",
          result["affiliate_links"]["count"] == 1, examples)
    check("it is classed as a shortener",
          examples and examples[0]["class"] == "shortener", examples)
    check("its real destination is left unresolved, not guessed",
          examples and examples[0]["wraps"] is None, examples)
    check("the caveat says the destination could not be resolved",
          any("shortened or wrapped" in line
              for line in result["what_could_not_be_checked"]),
          result["what_could_not_be_checked"])
    check("a shortener alone does not become an accusation",
          result["per_source_verdict"]["verdict"]
          == SOURCE.VERDICT_NO_EVIDENCE,
          result["per_source_verdict"]["verdict"])


def t_a_redirect_wrapper_names_what_it_wraps():
    result = _verdict(REDIRECT)
    examples = result["affiliate_links"]["examples"]
    check("the wrapper is listed as a redirect",
          examples and examples[0]["class"] == "redirect_wrapper", examples)
    check("the wrapped host is named without opening it",
          examples and examples[0]["wraps"] == "shop.example", examples)
    check("the matched parameter is kept",
          examples and examples[0]["parameter"] == "url", examples)
    check("a plain redirect wrapper does not decide the verdict",
          result["per_source_verdict"]["verdict"]
          == SOURCE.VERDICT_NO_EVIDENCE,
          result["per_source_verdict"]["verdict"])


def t_a_redirect_wrapper_can_hide_an_affiliate_link():
    result = _verdict(REDIRECT_AFFILIATE)
    examples = result["affiliate_links"]["examples"]
    check("the address it wraps is read for affiliate markers",
          examples and examples[0]["class"] == "affiliate", examples)
    check("the wrapped shop tag is named",
          examples and examples[0]["marker"] == "jarvis-20", examples)
    check("the wrapped destination's host is kept",
          examples and examples[0]["wraps"] == "www.amazon.example", examples)
    check("a hidden affiliate link is likely_monetised_undisclosed",
          result["per_source_verdict"]["verdict"]
          == SOURCE.VERDICT_LIKELY_UNDISCLOSED,
          result["per_source_verdict"]["verdict"])


def t_affiliate_examples_are_bounded():
    links = "".join(
        _link(f"https://www.amazon.example/dp/B{i}?tag=jarvis-20", f"pick {i}")
        for i in range(8))
    result = _verdict(_page(f"<p>Our picks are below.</p>{links}"))
    check("every marked link is counted",
          result["affiliate_links"]["count"] == 8, result["affiliate_links"])
    check("only a few examples are kept",
          len(result["affiliate_links"]["examples"])
          == SOURCE.MAX_EXAMPLES, result["affiliate_links"]["examples"])
    check("an example address is truncated",
          all(len(example["url"]) <= SOURCE.URL_SNIPPET_CHARS
              for example in result["affiliate_links"]["examples"]),
          [len(example["url"]) for example in result["affiliate_links"]["examples"]])


# ---------------------------------------------------------------------------
#  3. Kinds, and the video's own paid-promotion label
# ---------------------------------------------------------------------------

def t_youtube_includes_paid_promotion():
    result = _verdict(VIDEO_PROMOTION, "https://www.youtube.example/watch?v=1",
                      "video")
    check("the video's paid-promotion label is found",
          any(d["category"] == "paid_promotion" for d in result["disclosures"]),
          result["disclosures"])
    check("it is reported as disclosed_sponsored",
          result["per_source_verdict"]["verdict"]
          == SOURCE.VERDICT_DISCLOSED_SPONSORED,
          result["per_source_verdict"]["verdict"])
    check("the video kind is kept",
          result["source"]["kind"] == "video", result["source"])


def t_a_video_page_data_flag_is_read_but_only_decides_on_a_video():
    video = _verdict(VIDEO_FLAG, "https://www.youtube.example/watch?v=1", "video")
    article = _verdict(VIDEO_FLAG, "https://reviews.example/p", "article")
    check("the paidPromotion flag in the page's data is found",
          any(d["where"] == "page_data" and d["category"] == "paid_promotion"
              for d in video["disclosures"]), video["disclosures"])
    check("on a video page it decides the verdict",
          video["per_source_verdict"]["verdict"]
          == SOURCE.VERDICT_DISCLOSED_SPONSORED,
          video["per_source_verdict"]["verdict"])
    check("on an article page the same data does not decide",
          article["per_source_verdict"]["verdict"]
          == SOURCE.VERDICT_NO_EVIDENCE,
          article["per_source_verdict"]["verdict"])
    check("the article caveat says the wording was in the page's data",
          any("own data" in line
              for line in article["what_could_not_be_checked"]),
          article["what_could_not_be_checked"])
    check("the article summary says the data did not decide, not that it is clean",
          "own data" in article["monetisation"]["summary"]
          and "did not decide" in article["monetisation"]["summary"],
          article["monetisation"]["summary"])


def t_each_kind_gets_its_own_honest_limit():
    video = _verdict(CLEAN, "https://v.example/1", "video")
    reviews = _verdict(CLEAN, "https://r.example/1", "reviews")
    article = _verdict(CLEAN, "https://a.example/1", "article")
    unknown = _verdict(CLEAN, "https://u.example/1", "podcast")
    check("a video says its spoken words were not transcribed",
          any("out loud" in line for line in video["what_could_not_be_checked"]),
          video["what_could_not_be_checked"])
    check("a review page says reviewer accounts were not read",
          any("reviewers" in line for line in reviews["what_could_not_be_checked"]),
          reviews["what_could_not_be_checked"])
    check("an article says an undisclosed payment cannot be seen",
          any("publication" in line for line in article["what_could_not_be_checked"]),
          article["what_could_not_be_checked"])
    check("an unrecognised kind becomes unknown, not an error",
          unknown["source"]["kind"] == "unknown", unknown["source"])
    check("an unknown kind says the same checks were used for every kind",
          any("no kind was given" in line
              for line in unknown["what_could_not_be_checked"]),
          unknown["what_could_not_be_checked"])


# ---------------------------------------------------------------------------
#  4. cannot_tell is a first-class answer
# ---------------------------------------------------------------------------

def t_an_empty_or_non_text_page_is_cannot_tell():
    for value in ("", None, 123, b"<html></html>", []):
        result = SOURCE.analyse_source(value, "https://e.example/p", "article")
        check(f"an unreadable input ({type(value).__name__}) is cannot_tell",
              result["per_source_verdict"]["verdict"]
              == SOURCE.VERDICT_CANNOT_TELL,
              result["per_source_verdict"]["verdict"])
        check(f"an unreadable input ({type(value).__name__}) says it is unchecked",
              any("readable article text" in line
                  for line in result["what_could_not_be_checked"]),
              result["what_could_not_be_checked"])


def t_a_javascript_shell_is_cannot_tell():
    result = _verdict(JS_SHELL)
    check("a page with no article text is cannot_tell",
          result["per_source_verdict"]["verdict"]
          == SOURCE.VERDICT_CANNOT_TELL,
          result["per_source_verdict"]["verdict"])
    check("it is not guessed to be clean",
          result["per_source_verdict"]["verdict"]
          != SOURCE.VERDICT_NO_EVIDENCE,
          result["per_source_verdict"]["verdict"])
    check("the evidence says how little text there was",
          any("word(s)" in line or "no readable text" in line
              for line in result["per_source_verdict"]["evidence"]),
          result["per_source_verdict"]["evidence"])
    check("the caveat names JavaScript or a sign-in page",
          any("JavaScript" in line
              for line in result["what_could_not_be_checked"]),
          result["what_could_not_be_checked"])


def t_a_page_with_too_little_text_is_cannot_tell():
    result = _verdict(
        "<html><body><p>A quick look at the widget.</p></body></html>")
    check("a page below the readable-text floor is cannot_tell",
          result["per_source_verdict"]["verdict"]
          == SOURCE.VERDICT_CANNOT_TELL,
          result["per_source_verdict"]["verdict"])
    check("the floor is a module constant the test can quote",
          isinstance(SOURCE.MIN_TEXT_WORDS, int)
          and SOURCE.MIN_TEXT_WORDS > 0, SOURCE.MIN_TEXT_WORDS)


# ---------------------------------------------------------------------------
#  5. Urgency wording sits beside the verdict, never inside it
# ---------------------------------------------------------------------------

def t_urgency_is_reported_but_does_not_decide():
    result = _verdict(URGENCY)
    phrases = [item["phrase"].lower() for item in result["urgency"]["phrases"]]
    check("urgency phrases are found",
          any("last chance" in phrase for phrase in phrases), phrases)
    check("the two-part countdown rule fires with urgency wording",
          any(item["label"] == "countdown timer with urgency wording"
              for item in result["urgency"]["phrases"]),
          result["urgency"]["phrases"])
    check("the verdict is not changed by urgency wording",
          result["per_source_verdict"]["verdict"]
          == SOURCE.VERDICT_NO_EVIDENCE,
          result["per_source_verdict"]["verdict"])
    check("the note says urgency is not evidence of payment",
          "does not change the verdict" in result["urgency"]["note"],
          result["urgency"]["note"])


def t_a_countdown_alone_is_not_urgency():
    result = _verdict(_page("<p>Watch the 12:34 walkthrough below.</p>"))
    check("a timer without urgency words is not reported",
          result["urgency"]["count"] == 0, result["urgency"])


# ---------------------------------------------------------------------------
#  6. No score, no probability, no percentage - ever
# ---------------------------------------------------------------------------

def t_no_score_no_probability_no_percentage():
    samples = [CLEAN, SPONSORED, MIXED, AFFILIATE, AFFILIATE_DISCLOSED,
               TRACKING, SHORTENED, REDIRECT, URGENCY, JS_SHELL,
               VIDEO_PROMOTION, VIDEO_FLAG, NEGATED, CONTEXTUAL, SURFACES]
    problems = []
    for page in samples:
        result = _verdict(page)
        for path, key in _all_keys(result):
            if any(word in key.lower() for word in SCORE_KEYS):
                problems.append(f"{path} is a score key")
        if _all_floats(result):
            problems.append("a float appeared (a probability would be one)")
        ranked = SOURCE.rank_sources([{"html": page, "claim": "it is good"}])
        for path, key in _all_keys(ranked):
            if any(word in key.lower() for word in SCORE_KEYS):
                problems.append(f"rank {path} is a score key")
        if _all_floats(ranked):
            problems.append("rank returned a float")
        prose = ([result["monetisation"]["summary"],
                  result["per_source_verdict"]["why"],
                  ranked["agreement"]["summary"],
                  ranked["agreement"]["note"]]
                 + result["per_source_verdict"]["evidence"]
                 + result["what_could_not_be_checked"])
        if any("%" in line for line in prose):
            problems.append("a percentage sign appeared in plain words")
    check("no analysis or ranking carries a score, a probability or a percentage",
          not problems, problems[:6])


def t_no_developer_confidence_words_in_the_answers():
    result = _verdict(SPONSORED)
    text = " ".join(result["per_source_verdict"]["evidence"]).lower()
    text += " " + result["per_source_verdict"]["why"].lower()
    text += " " + result["monetisation"]["summary"].lower()
    forbidden = ("confidence", "probability", "p-value", "percent")
    check("the answers never offer a confidence or a probability",
          not any(word in text for word in forbidden), text[:200])


# ---------------------------------------------------------------------------
#  7. The closed vocabulary, and the shape of the answer
# ---------------------------------------------------------------------------

def t_the_verdict_vocabulary_is_closed():
    check("the vocabulary is exactly the five designed verdicts",
          SOURCE.VERDICTS == ("disclosed_sponsored",
                              "likely_monetised_undisclosed",
                              "affiliate_only",
                              "no_monetisation_evidence",
                              "cannot_tell"),
          SOURCE.VERDICTS)
    samples = {
        SPONSORED: "disclosed_sponsored",
        AFFILIATE: "likely_monetised_undisclosed",
        AFFILIATE_DISCLOSED: "affiliate_only",
        CLEAN: "no_monetisation_evidence",
        JS_SHELL: "cannot_tell",
    }
    for page, expected in samples.items():
        result = _verdict(page)
        check(f"the page that should be {expected} says so",
              result["per_source_verdict"]["verdict"] == expected,
              result["per_source_verdict"]["verdict"])
        check(f"the answer for {expected} lists the closed vocabulary",
              result["per_source_verdict"]["closed_vocabulary"]
              == list(SOURCE.VERDICTS),
              result["per_source_verdict"]["closed_vocabulary"])


def t_the_source_metadata_is_honest():
    result = _verdict(CLEAN, "https://reviews.example/best/widgets", "article")
    check("the source URL is kept", result["source"]["url"]
          == "https://reviews.example/best/widgets", result["source"])
    check("the source host is read from it",
          result["source"]["host"] == "reviews.example", result["source"])
    check("the page title is kept",
          result["source"]["title"] == "Widget review", result["source"])
    check("the readable word count is reported",
          result["source"]["text_words"] >= SOURCE.MIN_TEXT_WORDS,
          result["source"])
    check("the engine block says it never dials out",
          result["engine"]["network"] is False
          and result["engine"]["read_only"] is True, result["engine"])
    check("a page with no URL does not invent one",
          SOURCE.analyse_source(CLEAN)["source"]["url"] is None)


def t_what_could_not_be_checked_is_always_answered():
    problems = []
    for page in (CLEAN, SPONSORED, AFFILIATE, TRACKING, SHORTENED, JS_SHELL,
                 VIDEO_PROMOTION, URGENCY):
        lines = _verdict(page)["what_could_not_be_checked"]
        if not lines:
            problems.append("an empty list")
        if not all(isinstance(line, str) and len(line) > 20 for line in lines):
            problems.append("a line that is not a plain sentence")
    check("every answer carries a real what-could-not-be-checked list",
          not problems, problems[:4])


def t_the_answer_is_json_able_and_deterministic():
    first = _verdict(SPONSORED)
    second = _verdict(SPONSORED)
    check("the same page gives the same answer twice", first == second)
    try:
        json.dumps(first)
        encoded = True
    except (TypeError, ValueError):
        encoded = False
    check("the answer is JSON-able", encoded)


def t_the_module_is_ascii_only():
    path = Path(inspect.getfile(SOURCE))
    try:
        path.read_bytes().decode("ascii")
        ascii_only = True
    except UnicodeDecodeError:
        ascii_only = False
    check("the module's source is plain ASCII", ascii_only, path.name)


# ---------------------------------------------------------------------------
#  8. rank_sources: most independent first, and the agreement summary
# ---------------------------------------------------------------------------

def t_ranking_puts_the_most_independent_first():
    sources = [
        {"html": SPONSORED, "claim": "it is the best"},
        {"html": CLEAN, "claim": "it is the best"},
        {"html": AFFILIATE_DISCLOSED, "claim": "it is the best"},
        {"html": AFFILIATE, "claim": "it is the best"},
        {"html": JS_SHELL, "claim": "it is the best"},
    ]
    ranked = SOURCE.rank_sources(sources)
    verdicts = [item["verdict"] for item in ranked["sources"]]
    check("the clean source is first",
          verdicts[0] == SOURCE.VERDICT_NO_EVIDENCE, verdicts)
    check("a disclosed affiliate source comes before an undisclosed one",
          verdicts.index(SOURCE.VERDICT_AFFILIATE_ONLY)
          < verdicts.index(SOURCE.VERDICT_LIKELY_UNDISCLOSED), verdicts)
    check("a source that could not be read is never put first",
          verdicts[0] != SOURCE.VERDICT_CANNOT_TELL, verdicts)
    check("a disclosed sponsor is last",
          verdicts[-1] == SOURCE.VERDICT_DISCLOSED_SPONSORED, verdicts)
    check("each source carries its position",
          [item["rank"] for item in ranked["sources"]] == [1, 2, 3, 4, 5],
          [item["rank"] for item in ranked["sources"]])
    check("the order lists the original indexes",
          sorted(ranked["order"]) == [0, 1, 2, 3, 4], ranked["order"])


def t_agreement_counts_the_sources_that_say_the_same_thing():
    sources = [
        {"html": CLEAN, "claim": "the battery lasts about 9 hours"},
        {"html": CLEAN, "claim": "The battery lasts about 9 hours."},
        {"html": SPONSORED, "claim": "the battery lasts about 9 hours"},
        {"html": JS_SHELL, "claim": "the battery lasts about 9 hours"},
    ]
    ranked = SOURCE.rank_sources(sources)
    shared = ranked["agreement"]["shared_claims"]
    check("the shared claim is reported once",
          len(shared) == 1, shared)
    check("two independent sources are counted on it",
          shared and shared[0]["independent"] == 2, shared)
    check("one monetised source is counted on it",
          shared and shared[0]["monetised"] == 1, shared)
    check("the unreadable source is counted separately, not as independent",
          shared and shared[0]["cannot_tell"] == 1, shared)
    summary = ranked["agreement"]["summary"]
    check("the summary counts both groups in plain words",
          "2 independent source(s)" in summary
          and "1 monetised source(s)" in summary, summary)
    check("the summary never prints a percentage",
          "%" not in summary, summary)
    check("the note says claims were compared word for word",
          "word for word" in ranked["agreement"]["note"],
          ranked["agreement"]["note"])
    check("the counts block adds up to the number of sources",
          sum(ranked["counts"][name] for name in SOURCE.VERDICTS)
          == len(sources), ranked["counts"])


def t_agreement_says_so_when_nothing_is_shared():
    ranked = SOURCE.rank_sources([
        {"html": CLEAN, "claim": "the battery lasts about 9 hours"},
        {"html": SPONSORED, "claim": "the app crashes on start"},
    ])
    check("no shared claim is reported",
          ranked["agreement"]["shared_claims"] == [],
          ranked["agreement"]["shared_claims"])
    check("the summary says no claim was made by both groups",
          "No claim was made by both" in ranked["agreement"]["summary"],
          ranked["agreement"]["summary"])
    unreadable = SOURCE.rank_sources([
        {"html": JS_SHELL, "claim": "it is good"},
        {"html": "", "claim": "it is good"},
    ])
    check("when every source is unreadable the summary says so",
          "could not be read" in unreadable["agreement"]["summary"]
          and "None of the readable sources" in unreadable["agreement"]["summary"],
          unreadable["agreement"]["summary"])
    check("no unreadable source is counted as independent",
          unreadable["agreement"]["independent"]["count"] == 0,
          unreadable["agreement"]["independent"])


def t_an_unknown_verdict_is_not_trusted():
    injected = {"per_source_verdict": {"verdict": "definitely_trustworthy"},
                "source": {"url": "https://x.example/p", "kind": "article"},
                "monetisation": {"summary": "looks fine"},
                "disclosures": [], "affiliate_links": {"count": 0}}
    ranked = SOURCE.rank_sources([
        {"analysis": injected, "claim": "it is good"},
    ])
    check("an unknown verdict becomes cannot_tell",
          ranked["sources"][0]["verdict"] == SOURCE.VERDICT_CANNOT_TELL,
          ranked["sources"][0]["verdict"])
    check("it is not counted as independent",
          ranked["agreement"]["independent"]["count"] == 0,
          ranked["agreement"]["independent"])


def t_ranking_tolerates_odd_input():
    check("no sources is an empty answer, not an error",
          SOURCE.rank_sources([])["counts"]["sources"] == 0)
    check("None is the same as no sources",
          SOURCE.rank_sources(None)["counts"]["sources"] == 0)
    check("a non-list is the same as no sources",
          SOURCE.rank_sources("nope")["counts"]["sources"] == 0)
    ranked = SOURCE.rank_sources([{}, "not a record", 42, {"html": CLEAN}])
    check("odd entries are reported as cannot_tell, never raised",
          ranked["counts"]["sources"] == 4
          and ranked["counts"]["cannot_tell"] == 3, ranked["counts"])
    check("one good entry is still read normally",
          any(item["verdict"] == SOURCE.VERDICT_NO_EVIDENCE
              for item in ranked["sources"]), ranked["sources"])


def t_ranking_does_not_mutate_its_input():
    sources = [{"html": SPONSORED, "claim": "it is good",
                "url": "https://reviews.example/p", "kind": "article"},
               {"html": CLEAN, "claim": "it is good"}]
    snapshot = copy.deepcopy(sources)
    SOURCE.rank_sources(sources)
    check("the caller's source records are unchanged", sources == snapshot,
          sources)


# ---------------------------------------------------------------------------
#  9. No network, no browser, no storage, no process
# ---------------------------------------------------------------------------

def t_network_spy():
    calls = []
    real_socket = socket.socket
    real_create = socket.create_connection
    real_urlopen = urllib.request.urlopen
    real_http = http.client.HTTPConnection

    def spy_socket(*args, **kwargs):
        calls.append("socket")
        raise AssertionError("the source check tried to open a socket")

    def spy_create(*args, **kwargs):
        calls.append("connect")
        raise AssertionError("the source check tried to connect")

    def spy_urlopen(*args, **kwargs):
        calls.append("urlopen")
        raise AssertionError("the source check tried to read a URL")

    def spy_http(*args, **kwargs):
        calls.append("http")
        raise AssertionError("the source check tried to build an HTTP connection")

    try:
        socket.socket = spy_socket
        socket.create_connection = spy_create
        urllib.request.urlopen = spy_urlopen
        http.client.HTTPConnection = spy_http
        for page in (CLEAN, SPONSORED, AFFILIATE, TRACKING, SHORTENED,
                     REDIRECT, URGENCY, JS_SHELL):
            SOURCE.analyse_source(page, "https://reviews.example/p", "article")
        SOURCE.rank_sources([{"html": CLEAN, "claim": "it is good"},
                             {"html": SPONSORED, "claim": "it is good"}])
    finally:
        socket.socket = real_socket
        socket.create_connection = real_create
        urllib.request.urlopen = real_urlopen
        http.client.HTTPConnection = real_http
    check("no socket, connection, URL or HTTP call was made", calls == [], calls)


def t_imports_are_only_re_and_the_parser():
    tree = ast.parse(inspect.getsource(SOURCE))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    check("the module's only imports are re and html.parser",
          roots == {"re", "html", "__future__"}, sorted(roots))
    forbidden = {"socket", "urllib", "http", "requests", "subprocess", "os",
                 "pathlib", "json", "playwright", "selenium", "webbrowser",
                 "browser"}
    check("it imports no network, browser, storage or process module",
          not (roots & forbidden), sorted(roots & forbidden))
    call_names = {node.func.id for node in ast.walk(tree)
                  if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    check("it never calls open()/urlopen() or a shell",
          not (call_names & {"open", "urlopen", "system", "popen", "exec", "eval"}),
          sorted(call_names & {"open", "urlopen", "system", "popen", "exec", "eval"}))


def t_runtime_namespace_has_no_network_modules():
    present = [name for name in ("socket", "urllib", "http", "requests",
                                 "subprocess", "playwright", "selenium",
                                 "webbrowser")
               if name in vars(SOURCE)]
    check("the module object holds no network or browser module",
          present == [], present)
    imported = sorted({value.__name__ for value in vars(SOURCE).values()
                       if type(value).__name__ == "module"})
    check("the only module objects in its namespace are re and html",
          all(name.split(".")[0] in ("re", "html") for name in imported),
          imported)


# ---------------------------------------------------------------------------
#  Runner
# ---------------------------------------------------------------------------

TESTS = (
    t_a_plain_page_has_no_disclosure,
    t_a_sponsorship_disclosure_carries_its_evidence,
    t_mixed_disclosures_are_all_listed,
    t_gift_wording_is_its_own_category,
    t_a_negated_disclosure_is_the_pages_own_claim,
    t_contextual_wording_does_not_decide,
    t_disclosures_are_found_on_every_surface,
    t_affiliate_only_is_disclosed,
    t_affiliate_without_disclosure_is_likely_monetised,
    t_utm_only_is_tracking_not_affiliate,
    t_a_shop_tag_is_affiliate_but_a_category_tag_is_not,
    t_a_shortened_link_is_masked_not_resolved,
    t_a_redirect_wrapper_names_what_it_wraps,
    t_a_redirect_wrapper_can_hide_an_affiliate_link,
    t_affiliate_examples_are_bounded,
    t_youtube_includes_paid_promotion,
    t_a_video_page_data_flag_is_read_but_only_decides_on_a_video,
    t_each_kind_gets_its_own_honest_limit,
    t_an_empty_or_non_text_page_is_cannot_tell,
    t_a_javascript_shell_is_cannot_tell,
    t_a_page_with_too_little_text_is_cannot_tell,
    t_urgency_is_reported_but_does_not_decide,
    t_a_countdown_alone_is_not_urgency,
    t_no_score_no_probability_no_percentage,
    t_no_developer_confidence_words_in_the_answers,
    t_the_verdict_vocabulary_is_closed,
    t_the_source_metadata_is_honest,
    t_what_could_not_be_checked_is_always_answered,
    t_the_answer_is_json_able_and_deterministic,
    t_the_module_is_ascii_only,
    t_ranking_puts_the_most_independent_first,
    t_agreement_counts_the_sources_that_say_the_same_thing,
    t_agreement_says_so_when_nothing_is_shared,
    t_an_unknown_verdict_is_not_trusted,
    t_ranking_tolerates_odd_input,
    t_ranking_does_not_mutate_its_input,
    t_network_spy,
    t_imports_are_only_re_and_the_parser,
    t_runtime_namespace_has_no_network_modules,
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
