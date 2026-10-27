# "Everything Jarvis can do" — one list, both apps (design note, 2026-10-08)

The owner asked, on 2026-10-08: *"is there a button where I can find the entire
feature set of Jarvis on my desktop or android phone? It's important I can know
all the features, with an extend button on each feature where I can get
additional info."*

There is nothing like it today. Tutorials, FAQ and PC help exist in both apps
and each covers a subset. The only complete inventory of what Jarvis can do
lives in the code — 249 backend routes on the desktop, 222 on the phone, with
`tools/check_parity.py` already proving the two agree. The owner chose: both
apps, one shared list, and a test that fails when a feature exists but is not
listed.

## What it is

One page per app — **"Everything Jarvis can do"** — reachable by a real button:

* Desktop: a row in Settings, plus a tray menu item, opening `src/features.html`.
* Phone: a row on Home next to Tutorials, opening a new `FeaturesScreen`.

Each feature is one row with an **extend button** (the repo's own `<details>`
pattern on the desktop; the app's Plate/Quick idiom on the phone). Opened, a row
shows four things and nothing else:

| Field | Meaning | Example |
|---|---|---|
| `what` | one plain sentence, what it does | "Reads the text on your screen and answers about it." |
| `where` | how to reach it, concretely | "Press Alt+Shift+S, or ask 'look at this'." |
| `asks` | whether it asks first, and what kind of card | "One approval card, every time." |
| `limit` | a real limit, or empty | "Needs the 12 GB card for pictures; the words always work." |

Rows are grouped by area (Talking · Memory · Screen and pictures · Notes and
files · Money and health · Home · Phone · The PC itself · Safety), and each app
shows its own surface's features first, with the other app's marked "on your
phone" / "on your PC".

### The row's other fields

Beyond the four a person reads, a row may carry:

| Field | Meaning |
|---|---|
| `surface` | `both`, `desktop` or `phone` - which apps have the feature |
| `surface_reason` | for a one-sided row: one sentence saying WHY the other app has none (rule 5, both directions since 2026-10-26) |
| `covers` | the Settings sections, menu ids and lessons this row accounts for |
| `must_mention` | 1-3 words its lesson really uses (rule 7) |
| `aliases` | other names the owner says for THIS one feature, e.g. "customer support" for "Deal with customer support for me". Added 2026-10-26: 30 rows carry 55 of them. They are matched exactly, like the id and the title, and nothing else uses them |

`aliases` and `surface_reason` are there because the list is now SPOKEN as well
as drawn: chat answers "what is <feature>", "where is it", "how do I use it",
"can I change it" and "is it on" from these rows (`docs/JARVIS-API.md`, the
`feature_guide` section), and a one-sided answer says why the phone has none. A
checked-in copy of the list travels to the PC as `jarvis_feature_catalogue.py`,
written by `tools/gen_feature_guide_catalogue.py`; an unknown row key is refused
there, so a new field cannot be added without being looked at.

## The source of truth, and why it cannot rot

`features/features.json` is the list, checked in. Copies live where each app can
read them without a bundler or a build step:

* `features/features.json` (the source),
* `jarvis-desktop/src/features.json` (the desktop reads it as a page asset),
* `jarvis-client/app/src/main/assets/features.json` (the phone reads it from assets).

`test_feature_list.py` asserts the three copies are byte-identical — the same
rule `test_base_matches_repo.py` already applies to the backend copies, so there
is one precedent rather than a new idea.

`tools/check_feature_list.py` is the completeness test the owner asked for, and
it checks **both directions**:

1. Every route section the desktop serves (`jarvis-desktop/src-tauri/src/brain/routes.rs`)
   and every menu entry either app draws (`jarvis-client/.../ui/MenuPlaces.kt`,
   `jarvis-desktop/src/menu-visibility-settings.js`) is either named by some
   entry's `covers` list or named in `INTERNAL` with a one-line reason. A new
   feature that nobody listed **fails the build**.
2. Every `covers` id in the list still exists in the code, and every entry has
   a non-empty `what`, `where` and `asks`. A removed feature cannot linger as a
   lie on the page.

It also holds the **teaching** side (rules 6 and 7), because "the page lists the
feature" and "the lesson teaches it" are two different claims:

* every lesson in `backend/jarvis_tutorials.py` is named by a feature row, or
  exempt in `LESSON_UNCOVERED` with the reason it is deliberately not a
  feature. A lesson whose row was removed fails, and so does a feature with no
  lesson and no written reason (`docs/EDUCATION-TAB-DESIGN.md` section 8).
* every taught row says which words its lesson really uses. `must_mention`
  holds 1-3 lowercase words or short phrases, and each one must occur, whole
  word and case-insensitively, in the step `title`+`body` text of the lessons
  that row names. A row that names a lesson which never mentions the feature
  now fails, naming the feature, the lesson and the missing word. The rows
  whose lesson genuinely does not teach them YET are recorded in
  `TEACHING_GAP`, one line each saying what that lesson leaves out — a work
  list for the teaching side, never a silence: a row that gains `must_mention`
  fails until its gap line is deleted.

The 14 rows recorded on 2026-10-25, as a work order for the teaching side. The
checker's `TEACHING_GAP` is the authority and prints this same list on every
run, so it cannot grow silently; the table is the list in readable form, and
each row names the lesson it is taught by and what that lesson leaves out.

| feature row | lesson it names | what the lesson leaves out |
| --- | --- | --- |
| `talk-to-type` | `how-it-talks` | holding a key to type what you say |
| `about` | `intro` | the About page's version, licences and credits |
| `photo-reminder` | `screens-and-pictures` | reading dates off a photo and offering a reminder |
| `live-camera` | `phone-live` | the word camera appears in no step (the row says the feature is not built yet) |
| `github-watchlist` | `work-and-attention` | "github", "watch" and "topic" in neither lesson the row names |
| `email-drafts` | `home-calendar-email` | saving a draft to the owner's Drafts folder |
| `inbox-tidy` | `home-calendar-email` | archiving, starring, marking read, Trash and tidying |
| `news-and-page-watches` | `work-and-attention` | feeds and watched pages (only the briefing's own "news" line exists) |
| `updates` | `limits-and-notes` | an update, a version or a release page |
| `tool-updates` | `model-page` | checking a package is out of date |
| `app-lock` | `phone-limits` | App lock, a fingerprint, a PIN (the nearest sentence is in the sibling lesson `phone-stays-on-pc`, which the row does not name) |
| `captcha-handoff` | `phone-approvals` | a captcha, the solve-it-here hand-off and a stuck browser window |
| `stale-link` | `when-something-is-wrong` | the stale event stream and the block on acting |
| `rush-latch` | `when-something-is-wrong` | the rush-latch banner and the fact that no control clears it |

Closing a gap is two edits in one commit: teach the step, then delete its line
here. Keeping the gaps honest needs a person to read the lesson — the checker
can see a word occurs, not that the gap is still real.

Run through `backend/run_suites.py test_feature_list.py` so it runs in CI with
the other Python suites.

## Both apps' tests

* Desktop: `jarvis-desktop/tests/features.mjs`, on the existing harness — the
  page lists every group, each row's expander reveals all four fields, a row
  with an empty `limit` draws no limit line, and the page's own count matches
  the file's.
* Phone: a JVM test (`FeaturesListTest.kt`) — the asset parses, every entry has
  the four fields, the grouping is stable, and the screen's row count equals the
  file's.
* The completeness test above, which is the one that matters.

## Deliberately not in this

* No new backend route, no model involvement: the text is static, written by
  hand, and never generated at runtime.
* Nothing secret: the list names features, never keys, tokens, addresses or
  the owner's data.
* It is not a tutorial: Tutorials stay as they are, for "how do I do this".
  This answers "what can Jarvis do, and does it ask first?"
* Deep config editing is still off the phone (standing rule) — the page is
  read-only on both apps.

## Honest limit of the first version

249 routes are not 249 features to a human; several are plumbing. The list is
therefore curated for reading, and the `INTERNAL` allow-list with its reasons is
what keeps "curated" from meaning "incomplete". The two apps' entries are
written once in the shared file, so the phone and the PC can never disagree
about what a feature does — which is the same guarantee the shared contract
fixtures already give for cards.

Rule 7 has its own version of that limit, and it is worth saying plainly: the
checker can see that a word OCCURS in a lesson, and it cannot see that the word
is the RIGHT word. `["card"]` occurs in 28 of the 36 lessons, so a row could
satisfy the letter of the rule with a word that proves nothing. Two things keep
that honest: the list is 1-3 plain words a person reads in the diff, and a row
whose lesson does not teach it at all is recorded in `TEACHING_GAP` instead of
being given a nearby word. That list is the measured answer to "what does this
gate still not know" — 14 rows on 2026-10-25, each naming what its lesson leaves
out.
