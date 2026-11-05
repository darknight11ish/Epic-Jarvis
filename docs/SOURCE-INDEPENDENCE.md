# Design: source independence - who profits from this review?

**Status: the layer is built and tested; it is NOT wired to anything.** There is
no route, no chat tool, no approval card, no Settings row and no app surface,
and nothing imports the module yet - the same shape as the product engine and
its read half (`docs/DESIGN-PRODUCT-RESEARCH.md`). The page is supplied as HTML
by a later, explicitly carded capture slice; this module only reads a string it
is given, and it never fetches a page, opens a link or plays a video.

The owner asked on 2026-11-04 for product research that "filters out products
that have been sponsored or the reviews have heavily been sponsored or bribes".
The existing product engine answers the *review-page* half of that question with
reasons, counts and examples. This module answers the other half: **for each
source, does the review, roundup or video show that somebody paid for it, and
what is the evidence?** The answer is evidence-only, and it is weighed across
sources instead of being collapsed into a star rating.

| item | state |
|---|---|
| The layer | `backend/jarvis_source_independence.py` (+ byte-identical `jarvis-backend/` twin, shipped whole): one tolerant HTML pass, disclosure wording, affiliate/tracking links, urgency wording, a closed per-source verdict with its evidence, and a plain "what could not be checked" list. |
| Ranking | `rank_sources(sources)`: most independent first, plus a plain-words agreement summary that counts how many sources with no monetisation evidence made the same claim, beside the monetised sources that made it. No score, no percentage. |
| New dependencies | **None.** Standard library only: `re` and `html.parser`. |
| Network | **None, anywhere.** No `urllib`, no socket, no subprocess, no browser automation import, no file read or write. The suite spies on socket/urlopen/HTTP and proves no call is made, and an **AST scan of the module's own source** proves it imports no network, browser, storage or process module. |
| Why no trust score | A single number would hide which rule fired and would invite over-trust, exactly as the product engine's contract says. Every answer is the words or links that produced it. |
| Why `cannot_tell` is real | An empty page, a page that needs JavaScript, or a page with too little text is reported as unchecked. A blank page is never a clean bill of health, and it is never guessed to be sponsored either. |
| Tests | `backend/test_source_independence.py` **150 checks**. Synthetic fixtures only, no network, no browser, no real page. |
| Credit | The link-marker vocabularies and the urgency phrase list are a Python-native port of patterns from **dakidarts/dark-radar** (MIT). No JavaScript is vendored; the MIT notice is in `THIRD-PARTY-NOTICES.txt`. |

## 1. What one source's answer contains

`analyse_source(html, url, kind)` returns a stable, JSON-able dict. `kind` is
one of `article` / `video` / `reviews` / `unknown`, and anything else becomes
`unknown` rather than an error. A non-string page is treated as an empty page.
The same input gives the same answer, and no input is mutated.

* **`disclosures`** - each match keeps the matched `phrase`, its `category`
  (`sponsor`, `advertisement`, `gift`, `partnership`, `paid_promotion`,
  `affiliate`), its `strength` (`explicit` or `contextual`), a short `snippet`
  of the page's own words, and `where` it was found: the visible text, the page
  title, a page description, a label/image description, a link, or the page's
  own data. A video page's `paidPromotion` flag is read from its data.
* **`independence_claims`** - the page's own words saying it was *not* paid
  ("not sponsored", "we bought this ourselves", "no affiliate links"). This is
  kept as the page's claim, not as proof, and it is never counted as a
  disclosure.
* **`affiliate_links`** - every `<a href>` carrying an affiliate, tracking,
  shortener or redirect-wrapper marker, with its `host`, the matched
  `parameter` and value, a class, and a truncated example address. There is a
  `count` of marked links, a breakdown by class (`affiliate`, `tracking`,
  `shortener`, `redirect_wrapper`) and at most five examples. A redirect
  wrapper's wrapped address is read for affiliate markers too, because it is
  already in the page; its destination is **named, never opened**.
* **`urgency`** - pressure wording ("last chance", "today only", "only 3 left")
  and a countdown timer only when urgency words are also present. Its own note
  says it is a pressure tactic, not evidence of payment, and it **does not
  change the verdict**.
* **`monetisation`** - one plain sentence naming the strongest evidence, the
  `strongest` evidence object, per-category counts, and separate counts for
  affiliate, shortened/wrapped and tracking-only links.
* **`per_source_verdict`** - the closed verdict, the whole closed vocabulary, a
  list of plain evidence sentences, a one-sentence `why`, and what would change
  the answer.
* **`what_could_not_be_checked`** - fixed honest limits (money or a free
  product that was never mentioned, the owner's own financial interest, what
  each link really opens) plus the ones this page earned (a shortened link that
  could not be resolved, tracking markers that are not evidence of payment, a
  contextual word such as "commission" that is not a disclosure, a page that
  was too long to read in full, a page that needs JavaScript).
* **`source`** - the URL and host it was told about, the normalised kind, the
  tab title, the readable word count, the link count and whether the page was
  truncated. **`counts`** carries the same numbers for a caller that draws a
  screen.

## 2. The closed vocabulary

There are exactly five verdicts. A caller can switch on them; nothing else is
ever returned.

| verdict | what it means | what produces it | what would change it |
|---|---|---|---|
| `disclosed_sponsored` | The page says the content is paid, sponsored or gifted. | An explicit sponsor, advertisement, gift, partnership or paid-promotion disclosure; a video's `Includes paid promotion` label or `paidPromotion` flag; a `rel="sponsored"` link. | Nothing on the page: the disclosure is the evidence. A page that drops it would look independent here. |
| `likely_monetised_undisclosed` | Affiliate links are there, and the page does not say it earns from them. | At least one strong affiliate marker (a shop `tag=`, `aff_id`/`affiliate`/`associate`/`partner`, a known affiliate-network address, or a redirect wrapper around one) and **no** disclosure. | A commission or sponsorship disclosure; removing the affiliate markers. |
| `affiliate_only` | The page earns a commission and says so; the content itself is not declared sponsored. | An explicit affiliate/commission disclosure and **no** sponsor, advertisement, gift, partnership or paid-promotion disclosure. | A sponsorship disclosure would make it `disclosed_sponsored`. |
| `no_monetisation_evidence` | At least 40 readable words, no disclosure and no affiliate marker. | The readable-text floor plus the absence of the evidence above. | An affiliate link that turns out to be one when opened; a disclosure that only appears on a linked page. |
| `cannot_tell` | There was not enough readable text to check. | An empty page, a JavaScript shell, a page with fewer than 40 readable words and no disclosure or affiliate link. | A capture that includes the article text, or a page that shows a disclosure or affiliate link even when the rest is unreadable. |

A **contextual** word never decides on its own: "the artist took a commission"
is shown as evidence with a caveat, and the verdict stays `no_monetisation_evidence`.
A plain tracking marker (`utm_*`, `fbclid`, `gclid`, `ref=`) is recorded as
tracking, not as affiliate evidence: it records where a visitor came from, not
that anyone was paid. A category tag such as `?tag=recipes` on an ordinary page
is not an affiliate tag; only a shop address or an Amazon-shaped associate tag
is.

## 3. Weighing sources, not scoring them

`rank_sources(sources)` takes a list of source records. Each record may carry:

```python
{"url": "https://example.test/review", "kind": "article",
 "claim": "the battery lasts about 9 hours",
 "html": "<html>...</html>"}          # analysed here
# or
{"analysis": analyse_source(...), "claim": "..."}   # an answer already built
```

It returns the sources ordered **most independent first**
(`no_monetisation_evidence`, then `affiliate_only`, then `cannot_tell`, then
`likely_monetised_undisclosed`, then `disclosed_sponsored`), each with its
original index and a rank. A source that could not be read is never put in the
independent group: unknown is not the same as clean.

The `agreement` block counts sources, never a score. It reports how many
sources with no monetisation evidence supplied the same claim, beside the
monetised sources that supplied it, and how many could not be read. Claims are
compared **word for word** after lowering case and collapsing spaces; the note
says so, because two sources agreeing in different words is something this
module cannot prove. No percentage is printed: a handful of sources cannot
support one, and a percentage would look like a measurement it is not.

## 4. What is deliberately not built

* **No aggregate trust score, probability or percentage.** Deliberate, for the
  product engine's own measured reason: a single number hides which rule fired.
* **No per-review authenticity label.** This layer is about the *source*, not
  about labelling a review fake.
* **No fetching, ever.** No URL is opened, no redirect is followed, no
  shortened link is resolved, no page is fetched and no video or audio is
  played or transcribed. A later capture slice, behind its own approval card,
  supplies the HTML.
* **No storage, cache, logging or learning.** The module works in memory; it
  reads no file and writes none.
* **No semantic claim matching.** Two sources agree only when they wrote the
  same claim; the module does not guess at meaning.
* **No wiring.** No route, tool, card, Settings row or app screen exists, and
  `docs/JARVIS-API.md` is deliberately untouched because there is no route.

## 5. Borrowed patterns and attribution

The shortener list, the tracking markers (UTM tags, click ids) and the
affiliate parameter names, and the fake-urgency phrase list, are ported to
Python from **[dakidarts/dark-radar](https://github.com/dakidarts/dark-radar)**
(MIT). Its pattern for a countdown timer that only counts when urgency wording
is present is ported the same way. **No dark-radar file is shipped and no
JavaScript is vendored.** The credit and the MIT licence text are in
`THIRD-PARTY-NOTICES.txt` under "CODE ADAPTED INTO THE PYTHON BACKEND".

Added here, on top of that list, and named in the same notice: the
affiliate-network address list, the redirect-wrapper check, the shop-tag shape,
and the negative-phrase handling ("not sponsored" is a claim, not a
disclosure). These are this module's own patterns, not ported code.

## 6. Honest limits

* **All evidence is synthetic.** No real article, video page or review page has
  ever been read by this code; every fixture in the tests is hand-written, and
  every address is on an `.example` host. Real markup and real disclosure
  wording will need fixture and pattern updates.
* **The wording lists are cues, not measurements of intent.** "Gifted" in a
  sentence about a gifted musician, "advertisement" in an article *about*
  advertising, or a sponsorship disclosure that is itself quoted from somebody
  else can look identical to these rules. The evidence sentence shows the
  page's own words so the owner can judge.
* **The `paidPromotion` flag is not verified against a real video page.** The
  shape is what a synthetic fixture says; a real page may carry a different
  flag or no flag at all, and the `Includes paid promotion` wording remains the
  primary check.
* **The affiliate-network list is public knowledge, not a measurement.** It
  will go stale as networks change; an unknown network is still caught by its
  parameter names when it uses one.
* **A shortened link stays unknown.** Its destination is named only when the
  wrapper carries it in the address; a true shortener is reported as masked,
  and the verdict is not changed by the guesswork it would take to resolve it.
* **Only the page's own text is read.** An advertorial whose disclosure appears
  on a different page, in a video's spoken words, or in a picture's pixels is
  not seen here, and the "what could not be checked" list says so.
* **A page over 500,000 characters is read only in part**, and the report says
  it was truncated.

## 7. Validation

```
py -3 -B backend/test_source_independence.py     # 150 checks
py -3 -B backend/run_suites.py test_source_independence.py
py -3 -B backend/test_shipped_modules.py
py -3 -B backend/test_base_matches_repo.py
py -3 -B backend/test_base_regeneration.py
py -3 -B tools/check_stale_twins.py
py -3 -B tools/check_parity.py
py -3 -B tools/check_docs_map.py
py -3 -B tools/roll_changelog.py --check
py -3 -B tools/roll_decisions.py --check
```

The suite proves the disclosure paths (present, absent, mixed, negated,
contextual, and on every surface), the link paths (affiliate, tracking-only,
shop tag versus category tag, shortener, redirect wrapper, a wrapper hiding an
affiliate link), the four kinds and each kind's honest limit, `cannot_tell` for
an empty page, a JavaScript shell and a page below the readable-text floor, the
closed vocabulary, the no-score/no-probability/no-percentage rule, ranking and
the agreement counts, determinism, non-mutation, the no-network spy, and an AST
scan that would fail on a forbidden import or call.
