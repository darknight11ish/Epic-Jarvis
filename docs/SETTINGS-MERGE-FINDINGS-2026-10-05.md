# Settings merge: the four CI breaks, and what a correct merge must satisfy

**Read this before redoing the 33-cards-to-20 merge.** A merge of the desktop
Settings page was built on 2026-10-05 and a second agent reviewed it read-only,
finding the defects below. **The merge was then parked by the owner and the page
was put back exactly as it was** - see the update note immediately below. The
findings that follow are the constraints a correct retry has to satisfy. The
reviewer wrote nothing to the file.

The reviewer's own snapshot of the in-flight file (kept outside the repo):
`%TEMP%\settings-snapshot-other-agent.html`, sha256 `08F514CB…`, 127,826 bytes.

## Update, 2026-10-05: the merge was parked, and the page was put back

**This is what actually happened, and it changes how to read the rest of this
page.** Everything below is still the record of what the merge attempt got wrong;
what is new is that the attempt is **not** going to be finished as it stands.

1. **The merge was built** - the version of the desktop Settings page
   (`jarvis-desktop\src\settings.html`) that took 33 cards down toward 20.
2. **A second agent reviewed it read-only** and found the defects recorded below.
   Two of them were serious enough to stop it: the four Playwright-gated test
   suites it breaks, and `#security` swallowing six unrelated cards.
3. **The owner chose to park it.** Not fix it forward, not finish it - park it.
4. **The page was restored to its pristine version.** It is byte-for-byte the page
   the project already had: sha256
   `0AF77329E81652C37B7D6A12AFD5128F01DD284CCD27F2901A452B07B5C1B4FD`, 127,375
   bytes. Checked on 2026-10-05: the file on disk hashes to exactly that, and git
   reports no change to it (`git status --porcelain -- jarvis-desktop/src/settings.html`
   lists nothing), so what is on disk is what is committed.

**The parked attempt also never landed the DOM nesting.** The restructure that
would have moved headings, jump links and closing tags around is gone with it.
So **the Settings page is unchanged in appearance and in behaviour** - the owner
sees exactly the page they saw before the merge was tried, with the same 33
`section.card` elements it has always had. Nothing needs re-testing and nothing
was half-applied.

**What this page is for now.** It is the **constraint list for a correct retry**,
not a description of the current page. Read the sections below as "what a merge
must satisfy", and read the current page's facts from the page itself.

**One thing worth knowing before trusting the suite references below.** In this
container these suites **cannot be run**, so no claim below rests on having run
one. Checked on 2026-10-05, reading the test files directly rather than assuming:
of the four suites named, **only `animal-settings.mjs` imports Playwright at all**
(it tries the import, and if that fails it prints `SKIP  the Settings part -
Playwright is not installed (npm i -D playwright)` and carries on without testing
the page). `asks-first.mjs`, `reach.mjs`, `big-model.mjs` and `security.mjs` do not
import it. Whatever else that means, it means **the line references below are what
CI is expected to ask for, and never evidence of a run that happened here** - and
the sentence just below, which says all four are Playwright-gated, is the earlier
note's own claim rather than something this check confirmed.

## The four breaks that CI will catch and nothing local can

All four suites are Playwright-gated, so they **cannot run in this container**
(no Playwright installed - they exit 2 with "These UI tests need Playwright").
Nothing local sees these; CI will.

| Suite | Needs | In-flight file |
|---|---|---|
| `asks-first.mjs:90` | the literal `<h2>What asks first</h2>` | **missing** - rewritten as `<h3>` |
| `reach.mjs:55` | the literal `<h2>What Jarvis can reach</h2>` | **missing** - rewritten as `<h3>` |
| `big-model.mjs:99-101` | `section.card h2` order: "Second graphics card" then "Big model (slow)" | **missing** - both `<h3>` |
| `animal-settings.mjs:108` | a jump link `a[href="#animal-options"]` | **missing** - the nav dropped from 31 links to 23 |
| `security.mjs:65-70` | `section.card h2` order: "Shortcuts" then "Security" | ok (both stay top level) |

**Cause:** the merge script rewrites every absorbed card's `<h2>` to
`<h3 class="subhead">` and drops the jump links to absorbed parts. The nine links
lost are: animal-options, second-card, big-model, screen-look, browser-engine,
tool-updates, more-options, reach, email-sending.

## The structural defect, which the owner would see

**`#security` now encloses six unrelated cards.** `#screen-look` and
`#browser-engine` sit ~700 lines below `#security`, so moving Security's closing
tag down past them makes Security's fold swallow, in order: "How Jarvis sounds",
"Web search", "Accounts", "Graphics cards and models", "Folders Jarvis may look
in", "Spending". That is the opposite of merging by subject - and a collapsed
Security card would hide all six.

## Honest arithmetic

The instructed merges give **22 `section.card`, not 20.** The audit's 20 counted
three *sub-headings* as if they were cards: "Sun, moon and weather", "Each
animal's voice", "The better voice". Report 22 and say why.

Also: absorbed cards keep `class="card"`, so `<section class="card">` stays 33 and
**no count drops at all** - the reduction is invisible both to the audit's own
metric and to `applyVisibility`'s selector. A merge whose whole point was fewer
cards that does not change the count should be reconsidered, not quietly shipped.

## What the merge got right, and must not lose

**Every card id survives** - all 31 registry ids plus `more-options` and the new
`startup-log`: none missing. That was the hardest requirement ("a break here is
worse than no merge") and it was met.

## The constraints a correct merge must satisfy (read from the suites, not guessed)

- `asks-first.mjs:90` and `reach.mjs:55` assert those two literal `<h2>`s, and both
  strings come from generated fixtures mirroring the phone (`AsksFirst.kt`,
  `ReachPlate.kt`). Keeping them as `<h3>` means updating those two suites **in
  step** - and the fixture half is generated, so change the generator.
- `big-model.mjs:99-101` reads `querySelectorAll("section.card h2")` and needs
  "Second graphics card" immediately followed by "Big model (slow)". Nested
  `<h2>`s inside an outer `section.card` satisfy it; `<h3>`s do not.
- `animal-settings.mjs:102-108` needs `getElementById("animal-options").contains(getElementById("sky"))` **and** a jump link to `#animal-options`. The sky block stays inside Animal options.
- `spending.mjs:635-639` needs the `#spending` link inside the nav's Rare group.
- `a11y.mjs:159-178` needs settings.html's first heading to be the H1.
- `applyVisibility()` already reads `card.dataset.menuId || "settings."+card.id`,
  which is why the `data-menu-id` trick needs no change there. The alternative -
  absorbed cards as plain `<section id=...>` with no `class="card"` - makes the
  count visibly drop but requires teaching `applyVisibility` to walk nested
  sections, or absorbed parts silently stop being hideable.
- **CSS gap:** `settings.css` has `.card` (:61), `.card h2` (:164) and the
  `.card.card-collapsed > :not(h2)…` rule (:1186) but **no `.card .card` rule**, so
  nested cards double-box (own border, background and padding), and a collapsed
  outer card hides its nested cards entirely instead of folding them.

## Still outstanding in this area, and safe to do on their own

- the four wording fixes, changed at their shared sources and regenerated;
- the quiet-hours sentence, which must now say that alarms and approval cards are
  **never** silenced;
- the `forced-colors: active` block for `settings.css` and `brain.css` - it exists
  in `style.css` (:2859, :2862) and `widget.css` (:641, :1106, :1109) and in
  neither of these;
- `p.note { max-width: 46em }` - `settings.css` has two separate `.note` rules
  (:173 and :501) and no max-width on either;
- a test asserting every jump link resolves and every registry card id exists.
