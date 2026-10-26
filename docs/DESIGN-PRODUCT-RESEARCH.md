# Design: the product check (offline engine + read half)

**Status: the engine and read half are built, plus a capture SEAM; none of it is
wired to anything.** The engine
turns review records into a reasons-based report, and the read half turns the
HTML of one Amazon product page into those records plus honest warnings about
what could not be read. There is **no route, no chat tool, no approval card, no
Settings row, no app surface, no browser automation and no network call** in
this work, and nothing imports either module yet - the same shape as the price
radar's F1 (`docs/DESIGN-PRICE-RADAR.md`). The design contract is the owner's
product-research document, revision 2
(`product_research_for_jarvis_2026_10_26.md`, on the Lead's Desktop rather than
in this repository); sections 4, 5, 8 and 9 of that document are the contract
followed here.

The page is **supplied as HTML** by a later, explicitly carded capture slice: the
read half only parses a string it is given. `capture_with_owner_browser()` is the
named seam for that later capture and it raises
`CaptureNeedsOwnerBrowser` with the sentence that reading a page needs the
owner's own browser session - it never pretends to fetch. No real Amazon page
has ever been parsed by this code; every fixture in the tests is synthetic.

| item | state |
|---|---|
| The engine | `backend/jarvis_product_research.py` (+ byte-identical `jarvis-backend/` twin, shipped whole): review-record normaliser, eight deterministic signals, model-output validator and quote validator, report builder. |
| The read half | `backend/jarvis_product_read.py` (+ byte-identical `jarvis-backend/` twin): one tolerant HTML pass, listing facts and review records in the engine's own schema, warnings for an unreadable page, and `assemble_report()` which returns the engine report with the records kept for debugging. |
| The capture seam | `backend/jarvis_product_capture.py` (+ byte-identical `jarvis-backend/` twin): classifies a supplied page string as product / owner-login / challenge / not-a-product, takes an INJECTED driver so the later browser slice can supply the HTML, and refuses with `CaptureUnavailable` / `OwnerLoginRequired` / `ChallengeDetected` instead of fetching. No real driver, route or surface is built. |
| New dependencies | **None.** Standard library only: engine `datetime`, `hashlib`, `json`, `re`, `collections`; read half `datetime`, `html.parser`, `re`, and the engine module. |
| Network | **None, anywhere.** No `urllib`, no socket, no subprocess, no browser automation import. The engine suite patches socket/urlopen and proves no call is made, and an **AST scan of the module's own source** proves it imports no network/shell module and calls no file/URL opener; the read suite does the same for its module. |
| Why not a per-review verdict | The contract's measured reason: people and LLMs are at chance telling AI-written reviews from real ones (50.8% for people). A "fake/real" label per review would be false precision, so the report shows **patterns, counts and reasons** instead. |
| Why no trust score | A single number would hide which rule fired and would invite over-trust. Every signal carries counts, thresholds, examples and the reviews it flagged; the verdict is a small named rule summary with its reasons and what would change it. |
| Tests | `backend/test_product_research.py` **118 checks**, `backend/test_product_read.py` **67 checks** and `backend/test_product_capture.py` **33 checks**; synthetic fixtures only, no network, no browser. |

## 1. What the report contains

`build_report(reviews, listing=..., product=..., model=...)` returns a stable,
JSON-able dict (and `json_report(...)` returns the same as stable JSON text):

* **`engine`** - name, version, `network: false`, `read_only: true`.
* **`sample`** - the caveat first: *"This is what Amazon chose to show, not all
  of the reviews"*; how many reviews were supplied/readable/skipped, how many
  have a **review body** (`with_text` counts a body, never a title alone),
  dates, a verified badge and a Vine label. A supplied listing's own review
  count is carried when there is one.
* **`signals`** - the eight deterministic evidence objects (below), in a fixed
  order. Each has `signal`, `available`, `why` (when it cannot be checked),
  `counts`, `thresholds`, a few `examples`, the reviews it `flags`, and a plain
  `note`.
* **`aspects`** - what buyers agree and complain about. This is **the local
  model's reading, validated**: aspect label, `positive`/`negative`/`mixed`
  stance, and quotes that must be real substrings of one review. The report
  keeps three lists - `agreed`, `complained` and **`mixed`** - and the plain
  words say "Agree:", "Complain:" and "Mixed:" rather than filing a mixed
  stance under complaints. The engine computes the mention count itself (word
  match over the readable reviews and the accepted quotes), so the model cannot
  report a count the sample does not support.
* **`set_aside`** - every review a rule noticed, with every reason and a short
  snippet: Vine label, incentive wording, duplicate wording, burst date,
  unverified 5-star, generic stylometry, mismatch hints, or a reason the reading
  model suggested. **Nothing is removed from the sample**: the counts include
  these reviews, and the owner can overrule any flag.
* **`verdict`** - one of `looks_solid` / `mixed` / `risky` /
  `not_enough_data`, in plain words, with the named reasons that fired and a
  "what would change this" list. It is a summary of the rules, never a
  probability about a review.
* **`could_not_check`** - fixed honest limits (reviewer profiles, undisclosed
  payment, the full review set, hidden orders, Amazon's own rating model) plus
  anything the model said it could not check.
* **`model`** - whether a model answer was used, and how many proposed quotes
  and aspects were dropped after validation.
* **`plain_words`** - the same report as lines of English, ready for a screen
  or a chat answer. The caveat is always the first sample line.

## 2. The eight signals (all deterministic, all evidence-only)

| signal | what it counts | a flag is not proof because |
|---|---|---|
| `verified_purchase_share` | verified / unverified / unknown badges, verified share, verified negative share | a seller can refund a verified buyer after the review; a badge is a purchase check, not an honesty check |
| `vine_share` | Vine-labelled reviews and their share; "No Vine" is an absence, not a label | Vine is disclosed and legitimate; it is listed so the owner can include or exclude it |
| `incentive_language` | reviews whose own words mention free product, an exchange, being asked to review, a discount code, a gift, or an affiliate link | honest reviewers mention gifts too; a mention does not say the words were shaped by it |
| `near_duplicate_wording` | groups of reviews sharing at least 60% of their 5-word runs (exact Jaccard; a deterministic MinHash shortlists pairs, never decides them); only reviews with 12+ words are compared. Counts say how many pairs were *possible*, *shortlisted* and *actually compared*, so nothing overstates the work | templates and honest repeated phrases look alike; short reviews are excluded on purpose |
| `date_burstiness` | days covered, busiest day, busiest 7-day window, and the baseline **the flags use**: the listing's own per-day average when supplied, otherwise the sample's average without the day being tested. A day is flagged only when it has at least 4 reviews AND at least 3x that baseline | a genuine launch creates real spikes; a listing averaging thousands of reviews a day does not flag a four-review day |
| `rating_histogram` | the listing's histogram if supplied, otherwise the sample's; average, 5-star share, 1-2 star share, J-shape flag | Amazon's displayed rating is machine-generated, and J-shapes are common for real products |
| `stylometry` | per 100 words: stopwords, first person, exclamation marks, superlatives, concrete specification words; only reviews with 20+ words | the classic cues were measured on old balanced research sets and modern model-written text defeats them |
| `review_product_mismatch` | reviews dated before the product's release/first-available date, and reviews naming a different variant token | variation pages are reused, and a reviewer may mention another size they own |

Dates are **calendar-validated** in both the engine and the read half: a shape
that looks like a date but is impossible (`2026-02-31`, `31 February 2026`,
`29 February 2025`, month 13, day 0) is unknown and counted, never accepted and
then crashed on. The report path is total: no review record can raise out of
`build_report`.

Thresholds are module constants (`MIN_REVIEWS`, `DUPLICATE_JACCARD`,
`BURST_MIN_DAY_REVIEWS`, `SUPERLATIVE_PER_100_FLAG`, `MIN_QUOTE_CHARS`, ...) so
every report and test can quote the exact number that made a flag fire.

## 3. The model contract and the quote validator

`MODEL_CONTRACT` is the exact JSON shape the local model is asked to fill:

```json
{
  "aspects": [{"aspect": "battery life", "stance": "positive",
               "quotes": ["The battery lasts about 9 hours at half volume"]}],
  "set_aside": [{"review": 3, "reason": "the wording repeats another review"}],
  "could_not_check": ["whether the seller shaped the wording"]
}
```

`validate_model_output()` accepts only what code can check:

* a quote is accepted only when it is **at least 8 characters** after whitespace
  normalisation and is a **real substring of ONE review's title OR its body**
  (checked separately: a phrase formed across the title/body boundary is
  rejected), with case and punctuation matching; invented, short and
  boundary-crossing quotes are dropped and counted (`quotes_dropped`);
* an aspect left with no real quote is dropped and counted (`aspects_dropped`);
* a set-aside entry needs a review number that exists and a short reason; an
  optional quote there is checked against that review;
* `could_not_check` lines are length-bounded plain sentences;
* anything else the model returns - including a score, a confidence or its own
  verdict - is **ignored**, because the contract asks for none and the report
  has no place to put one.

The engine may be given no model output at all; the aspect section then says
plainly that it was not checked, rather than inventing agreements.

## 4. "Not enough trustworthy data" is a first-class outcome

`MIN_REVIEWS = 5` and `MIN_TEXT_WORDS_TOTAL = 80`: below either, the verdict is
`not_enough_data` with words starting *"Not enough trustworthy data to
summarise this product"* and a list of what would change it (read or paste more
reviews, include real body text, include dates). The word count uses review
**bodies**, not titles, and `with_text` counts bodies too. The sample caveat,
counts and "what could not be checked" are still present, so an empty or thin
sample is reported honestly rather than as a clean result.

## 5. The read half

`parse_product_page(html, *, source_url=None, captured_at=None)` does one
tolerant `html.parser` pass over the supplied string. It returns:

* **listing facts** the page states: product title, star rating, rating count,
  the page's canonical/source URL, and the ASIN when present. A shop-name
  document title is not promoted to a product title.
* **reviews** in the engine's own schema: rating, date text plus a parsed ISO
  date when the text can be read, title, body, Verified Purchase badge, Vine
  label, helpful-vote count and variant line. The records go through the
  engine's `normalize_reviews()`, so there is one tolerant schema, not a
  parallel one.
* **warnings** with stable codes and plain sentences: a CAPTCHA/sign-in/
  challenge page, a page that is not a product page, a missing listing title/
  rating/count, no reviews, a truncated page, a truncated/partial review block,
  and reviews with missing fields. Each warning is bite-tested on its own
  fixture.

`assemble_report(html, ...)` is the convenience: it returns the engine's reasons
report (caveat and quote validation intact) with the records, listing,
warnings, `source_url` and `captured_at` kept for debugging.

`capture_with_owner_browser()` in the read module is deliberately a named error,
not a fetch: it raises `CaptureNeedsOwnerBrowser` with the plain sentence that
reading a page needs the owner's own signed-in browser session. The separate
capture seam module (`backend/jarvis_product_capture.py`) classifies a supplied
page string and names the injection point: `capture_page(url, driver=...)` calls
an injected driver (a callable or an object with `get_html(url)`), then raises
`ChallengeDetected` on a CAPTCHA page, `OwnerLoginRequired` on a sign-in page and
`CaptureUnavailable` for anything else unreadable. `open_owner_login()` is the
one-time login seam; the owner signs in and Jarvis never sees the password.
`real_driver()` says plainly that the real browser-session driver is not built
yet - the repository's browser automation exposes no public URL-to-HTML reader,
so nothing here opens a window or fetches a page.

## 6. What is deliberately not built yet

* **No live capture driver, route or wiring.** No route, chat tool, approval
  card, Settings row or app surface exists; nothing imports these modules. The
  page must be supplied as HTML by the later capture slice, which owns the
  one-time owner login. `jarvis_product_capture.py` is the classification/seam
  half only; `real_driver()` and `capture_with_owner_browser()` raising are the
  honest placeholders.
* **No Amazon automation, ever.** The design contract's revision 2 decision:
  the owner browses, Jarvis reads and analyses. No crawler, no CAPTCHA work,
  no Agent Terms fight. Jarvis's own visible browser remains a separate,
  explicitly carded possibility for the owner to choose, never a background
  crawler.
* **No per-review authenticity label and no numeric trust score.** Deliberate,
  for the measured reason in the contract.
* **No dataset, model or training.** The engine uses no labelled dataset (the
  public ones are share-alike licensed and old). Its rules are readable and
  reviewable; that is the whole method.
* **No storage, cache, logging or learning.** Both modules work in memory; they
  read no file and write none. Nothing about a review or the owner is kept.
* **No live network check.** These are pure modules; the network spies and AST
  source scans in the suites are the evidence that they cannot dial out.

## 7. Honest limits

* **All evidence is synthetic.** No real Amazon page, browser session or real
  review sample has ever been run through either half. The HTML fixtures are
  hand-written page shapes; real markup changes will need fixture and parser
  updates.
* **The signals are cues, not measurements of intent.** Copy-paste templates,
  honest repeated phrases, a genuine launch spike, a Vine-heavy early batch and
  a suspicious one can look identical to these rules. The report says so in its
  notes and never calls a review fake.
* **The sample is curated.** Amazon's default list is its own ranking; the
  caveat is in every report because the engine cannot see what was left out.
* **The model can be wrong.** Its aspect labels and set-aside reasons are
  reading suggestions; only its quotes are machine-validated, and the
  deterministic signals are what the verdict is built from.
* **No calibration against real data.** The thresholds are conservative,
  readable rules, not fitted to a dataset; the synthetic fixtures prove the
  rules fire as written, not that they match reality.
* **The capture seam is a placeholder.** Real page reading needs the real
  browser-session driver and the owner's one-time login in Jarvis's own browser;
  until that captured HTML is supplied, the seam's only evidence is fixture
  HTML. The live driver, the persistent profile, the one-time login and a real
  Amazon read are NOT-TESTABLE in this development container.
* **Review dates and badges depend on the extractor's page shape.** Missing or
  impossible values are counted as unknown and the relevant signals say they
  cannot be checked; a thin extraction therefore produces a weaker but still
  honest report.

## 8. Validation

```
py -3 -B backend/test_product_research.py      # 118 checks
py -3 -B backend/test_product_read.py          #  67 checks
py -3 -B backend/test_product_capture.py       #  33 checks
py -3 -B backend/run_suites.py test_product_research.py test_product_read.py test_product_capture.py
py -3 -B backend/test_base_matches_repo.py
py -3 -B backend/test_base_regeneration.py
py -3 -B tools/check_stale_twins.py
py -3 -B tools/roll_changelog.py --check
py -3 -B tools/check_docs_map.py
```

The suites use only synthetic reviews and HTML written for this repository.
They prove the tolerant schemas and total date handling, determinism and
non-mutation, each signal and its "cannot check" case, the calendar-invalid
date regressions, the per-field/minimum-length quote rules, the burst baseline
in use, the body-only `with_text`, the mixed-stance list, the exact
duplicate-pair counts, the caveat words, the not-enough-data outcome, the
set-aside list without removal, the model contract and quote-validator bites,
the read half's listing/review/warning paths and the capture seam's four
classification states and refusals, the no-network
spies, and AST source scans that would fail on a forbidden import or call.
