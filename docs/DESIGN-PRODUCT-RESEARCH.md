# Design: the product check engine (offline analysis, slice 1)

**Status: slice 1 is built, offline and NOT wired to anything.** This is the
analysis engine only: it reads a list of review records that some other part of
Jarvis (the screen read or a paste, in a later slice) has already extracted from
a page, and returns a report as plain Python data. There is **no route, no chat
tool, no approval card, no Settings row, no app surface and no network call** in
this slice - the same shape as the price radar's F1 (`docs/DESIGN-PRICE-RADAR.md`).
The design contract is the owner's product-research document, revision 2
(`product_research_for_jarvis_2026_10_26.md`, on the Lead's Desktop rather than
in this repository); sections 4, 5, 8 and 9 of that document are the contract
followed here.

| item | state |
|---|---|
| The engine | `backend/jarvis_product_research.py` (+ byte-identical `jarvis-backend/` twin, shipped whole): review-record normaliser, eight deterministic signals, model-output validator and quote validator, report builder. |
| New dependencies | **None.** Standard library only (`hashlib`, `json`, `re`, `collections`). |
| Network | **None, anywhere.** No `urllib`, no socket, no subprocess. The suite patches socket/urlopen and proves no call is made; a second check reads the source and proves the imports are not there. |
| Why not a per-review verdict | The contract's measured reason: people and LLMs are at chance telling AI-written reviews from real ones (50.8% for people). A "fake/real" label per review would be false precision, so the report shows **patterns, counts and reasons** instead. |
| Why no trust score | A single number would hide which rule fired and would invite over-trust. Every signal carries counts, thresholds, examples and the reviews it flagged; the verdict is a small named rule summary with its reasons and what would change it. |
| Tests | `backend/test_product_research.py`, 97 checks, synthetic fixtures only, no network. |

## 1. What the report contains

`build_report(reviews, listing=..., product=..., model=...)` returns a stable,
JSON-able dict (and `json_report(...)` returns the same as stable JSON text):

* **`engine`** - name, version, `network: false`, `read_only: true`.
* **`sample`** - the caveat first: *"This is what Amazon chose to show, not all
  of the reviews"*; how many reviews were supplied/readable/skipped, how many
  have text, dates, a verified badge and a Vine label. A supplied listing's own
  review count is carried when there is one.
* **`signals`** - the eight deterministic evidence objects (below), in a fixed
  order. Each has `signal`, `available`, `why` (when it cannot be checked),
  `counts`, `thresholds`, a few `examples`, the reviews it `flags`, and a plain
  `note`.
* **`aspects`** - what buyers agree and complain about. This is **the local
  model's reading, validated**: aspect label, `positive`/`negative`/`mixed`
  stance, and quotes that must be real substrings of a review. The engine
  computes the mention count itself (word match over the readable reviews and
  the accepted quotes), so the model cannot report a count the sample does not
  support.
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
| `vine_share` | Vine-labelled reviews and their share | Vine is disclosed and legitimate; it is listed so the owner can include or exclude it |
| `incentive_language` | reviews whose own words mention free product, an exchange, being asked to review, a discount code, a gift, or an affiliate link | honest reviewers mention gifts too; a mention does not say the words were shaped by it |
| `near_duplicate_wording` | groups of reviews sharing at least 60% of their 5-word runs (exact Jaccard; a deterministic MinHash shortlists pairs, never decides them); only reviews with 12+ words are compared | templates and honest repeated phrases look alike; short reviews are excluded on purpose |
| `date_burstiness` | days covered, busiest day, busiest 7-day window, median day, and the listing's own per-day baseline when supplied | a genuine launch creates real spikes |
| `rating_histogram` | the listing's histogram if supplied, otherwise the sample's; average, 5-star share, 1-2 star share, J-shape flag | Amazon's displayed rating is machine-generated, and J-shapes are common for real products |
| `stylometry` | per 100 words: stopwords, first person, exclamation marks, superlatives, concrete specification words; only reviews with 20+ words | the classic cues were measured on old balanced research sets and modern model-written text defeats them |
| `review_product_mismatch` | reviews dated before the product's release/first-available date, and reviews naming a different variant token | variation pages are reused, and a reviewer may mention another size they own |

Thresholds are module constants (`MIN_REVIEWS`, `DUPLICATE_JACCARD`,
`BURST_MIN_DAY_REVIEWS`, `SUPERLATIVE_PER_100_FLAG`, ...) so every report and
test can quote the exact number that made a flag fire.

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

* a quote is accepted only when its whitespace-normalised form is a **real
  substring** of a review's title or text (case and punctuation must match, so
  a paraphrase is not a quote); invented quotes are dropped and counted
  (`quotes_dropped`);
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
reviews, include real words, include dates). The sample caveat, counts and
"what could not be checked" are still present, so an empty or thin sample is
reported honestly rather than as a clean result.

## 5. What is deliberately not built yet

* **No page reading.** Extracting reviews from the owner's screen or a paste,
  choosing the review list, scrolling, and signing in are the later read-path
  slice. This engine only consumes records.
* **No Amazon automation, ever.** The design contract's revision 2 decision:
  the owner browses, Jarvis reads and analyses. No crawler, no CAPTCHA work,
  no Agent Terms fight. Jarvis's own visible browser remains a separate,
  explicitly carded possibility for the owner to choose, never a background
  crawler.
* **No route, chat tool, card, Settings row or app surface.** Nothing imports
  this module yet, so a backend without it behaves exactly as before. Wiring it
  to "Look at this" or a chat intent is a later slice with its own approval
  shape.
* **No per-review authenticity label and no numeric trust score.** Deliberate,
  for the measured reason in the contract.
* **No dataset, model or training.** The engine uses no labelled dataset (the
  public ones are share-alike licensed and old). Its rules are readable and
  reviewable; that is the whole method.
* **No storage, cache, logging or learning.** The report exists in memory; this
  module reads no file and writes none. Nothing about a review or the owner is
  kept.
* **No live network check.** This is a pure module; the network spy in the
  suite is the evidence that it cannot dial out.

## 6. Honest limits

* **The signals are cues, not measurements of intent.** Copy-paste templates,
  honest repeated phrases, a genuine launch spike, a Vine-heavy early batch and
  a suspicious one can look identical to these rules. The report says so in its
  notes and never calls a review fake.
* **The sample is curated.** Amazon's default list is its own ranking; the
  caveat is in every report because the engine cannot see what was left out.
* **The model can be wrong.** Its aspect labels and set-aside reasons are
  reading suggestions; only its quotes are machine-validated, and the
  deterministic signals are what the verdict is built from.
* **No calibration against real data.** The thresholds are chosen to be
  conservative and explained, not fitted to a dataset. The synthetic fixtures
  prove the rules fire as written, not that they match reality.
* **Not measured on the owner's PC with real pages.** No page reading exists
  yet, so no real review sample has been run through it. That measurement
  belongs to the read-path slice, and its report should update this file.
* **Review dates and badges depend on the later extractor.** Missing fields are
  counted as unknown and the relevant signals say they cannot be checked; a
  thin extraction therefore produces a weaker but still honest report.

## 7. Validation

```
py -3 -B backend/test_product_research.py
py -3 -B backend/test_base_matches_repo.py
py -3 -B backend/test_base_regeneration.py
py -3 -B tools/check_stale_twins.py
```

The suite uses only synthetic reviews written for this repository. It proves
the tolerant schema, determinism and non-mutation, each signal and its
"cannot check" case, the caveat words, the not-enough-data outcome, the
set-aside list without removal, the model contract and quote validator bites,
the no-network spy and source scan, and that a clean synthetic sample is not
flagged while a deliberately patterned one is.
