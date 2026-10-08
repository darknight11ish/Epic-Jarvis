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
