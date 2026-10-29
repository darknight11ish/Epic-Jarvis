# Settings: simpler and searchable

Written 2026-10-09 for the owner's request: *"make the settings page in both
jarvis on desktop and jarvis on android a lot more visually simple, with a
search bar in settings. I still want everything adjustable, just easier to
find and more efficient."*

**The answer, up front:** the search bar is the whole of the win, and it is
the only part that is unambiguous. The desktop Settings page is one scroll of
38 cards; the phone's is 22 sections. A search box that filters what is on
screen as you type is buildable without asking anything, changes no setting,
and cannot make anything harder to find - because clearing the box puts the
page back exactly as it was. The *rest* of "visually simpler" - merging
bands, hiding advanced cards behind a fold - is a set of trade-offs only the
owner can choose, so those are questions at the end, not decisions taken here.

## What changes

- **A search box at the top of Settings, on both apps**, above the "Jump to:"
  list. Typing filters the page live; every card that does not match is
  hidden.
- **It matches the label and the detail text** of every switch and every
  row - the words on the switch, and the paragraph under it that says what
  it does.
- **The group headings stay out of the results while a search is on.** This
  used to say the three frequency bands kept their headings so the page still
  said *where* a thing lived; the bands were removed on 2026-10-27 (see the
  amendment below), the page's one remaining heading is "What Jarvis does", and
  a ranked list with a category heading partway down it is two orders at once.
  So a search puts that heading away with the "Jump to:" list and brings both
  back when the box is empty.
- **The "Jump to:" list hides itself while a search is on** and comes back,
  unchanged, the moment the box is empty. While searching, the search *is*
  the map.
- **A real empty state**: "Nothing here matches "xyz"." plus a one-line
  reminder that clearing the box brings everything back, so a no-match never
  reads as "this setting does not exist".
- **A live count** ("3 settings match."), announced to a screen reader, and a
  Clear button. On the desktop, **Ctrl+F or Alt+F jumps to the box from
  anywhere on the page**; Escape clears it.
- **Matching text is marked** with a `<mark>`-style highlight, so it is
  visible *why* a row stayed.
- **Cases are folded and accents are ignored** (`text-transform`-ish
  behaviour): "Wi Fi", "wifi" and "wi-fi" all find the same rows.

## The words on the screen find the thing, in both apps (2026-10-13)

The row above - "it matches the label and the detail text of every switch" -
was true of the desktop from the start and **was not true of the phone** until
2026-10-13. The owner found it on his own phone: the switch titled exactly
**"Hide memory lists and chat history"** (Security -> "Lock and fingerprint
settings") returned **"Nothing here matches that."** for its own words.

The cause, and the two halves of it:

- The **desktop matches the page's own text** at the moment of the search
  (`settings-search.js` reads each card's parts out of the DOM), so a switch is
  found by whatever it currently says. It never had this defect.
- The **phone matched a hand-kept index** (`SettingsSearch.kt`), and that index
  held each section's heading, its prose and the names Jarvis answers to - and
  none of the names printed on the switches. `FindAnything.kt` reads the same
  index, so both of the phone's boxes were blind in the same way.

The fix is `SettingsSearch.Row.titles`: the names of the controls a section
prints, each one checked by `SettingsSearchTest` against the file that draws it
and against every `SwitchRow(title = ...)` in that file, so the index cannot
promise a switch the screen does not have and cannot forget one it does.

**The two apps name the same setting differently, and that is not a defect.**

| | The switch that hides the memory lists and the chat history |
| --- | --- |
| Desktop (`settings.html#sec-private`) | "Windows Hello for memory lists and chat history" |
| Phone (`SecurityScreen.kt`) | "Hide memory lists and chat history" |

The desktop's name says what it asks for (Windows Hello); the phone's says what
it does (hide), because the phone's check is its fingerprint or PIN. Each app is
searched by the words **it** prints, so this is one setting with two honest
names rather than a gap: typing "chat history" finds it on both. Neither name
may be changed to match the other without changing what that app really does.

## What deliberately does not change

- **No setting is added, removed, renamed, moved or hidden permanently.**
  With the box empty the page is byte-for-byte the page it is today: same 38
  cards, same order, same ids, same words, same bands. Search is a view.
- **Search never writes anything.** It does not call Rust, does not touch
  `localStorage`, does not reach the backend, and raises no approval card.
  `settings-search.js` contains no `invoke(`, no `fetch(` - the palette
  suite's own rule, applied here.
- **Search never changes a value**, and a control that is on screen behaves
  exactly as it did.
- **A card already hidden by "Show or hide menus" stays hidden**, whether or
  not it matches. Hiding and searching are two separate facts about a card
  and are now stored separately (`data-menu-hidden` vs the `hidden`
  attribute); the search cannot un-hide a menu the owner hid, and clearing
  the search cannot un-hide one either.
- **The classification bands are gone** (2026-10-27; the owner answered
  question 1 below by removing them). Every card, id, anchor and jump link is
  unchanged, and "What Jarvis does" stays as the one heading because it is a
  fact about those cards, not a guess about how often they are needed.
- **The desktop's four other windows, the HUD, the widget and the Jarvis bar
  are untouched.**

## What it costs

- **One new desktop module** (`settings-search.js`, ~300 lines with its own
  notes), one CSS block, ~35 lines of markup, and the `data-search-row`
  attribute on 43 rows (the 19 toggles, the 11 field blocks, the 7 labelled
  fields and the 6 theme lists). **The generator that will splice toggle rows
  in from `jarvis_settings_registry.py` must emit `data-search-row` and keep
  each row's own id** - that is the one thing to tell whoever owns
  `tools/gen_settings_cases.py`. A generated row WITHOUT the attribute is not
  broken: it is simply matched as part of its card's text instead of as a row
  of its own.
- **The phone gained a search field and a pure index** (`SettingsSearch.kt`,
  `SettingsSearchWords`, `SettingsJump.SEARCH_KEY`), one new row in
  `SETTINGS_ITEM_INDEX` (the box is row 0, so every section number moved down
  by one), and 20 one-line guards on the screen's own rows.
- **Two new tests**: `jarvis-desktop/tests/settings-search.mjs` (9 checks) and
  the phone's `SettingsSearchTest` (10), plus `SettingsJumpTest` learning that
  a row key may be a `SettingsJump` constant rather than a quoted string.
- **Search is client-side and text-based only.** It finds what is written in
  the index (the phone) or on the page (the desktop). A setting whose words do
  not contain what the owner typed will not be found - that is what a
  keywords/hidden-synonyms list would fix, and it is question 3. **Since
  2026-10-13 the phone's index carries the words printed on each switch**
  (`titles`, above), so "what is written in the index" now includes what the
  owner can read on the screen - which it did not before, and that was the
  defect.
- **Risk: low.** Nothing can be lost by typing in the box, and clearing it
  restores the page. The two real risks are a generated row losing its id
  (which the existing tests already catch) and the two `hidden` owners
  drifting apart - which is why the menu's decision is now recorded in
  `data-menu-hidden` instead of being read back off `hidden`.

## What the prior art actually says

| What well-regarded settings do | Evidence | What this build does |
| --- | --- | --- |
| One box, filters as you type | Android's Universal search indexes every setting's title, summary and keywords, so a query reaches any screen from one field ([AOSP](https://source.android.com/docs/core/settings/universal-search)); macOS System Settings has had a search field in the toolbar for years ([macmost](https://macmost.com/search-inside-system-preferences.html)) | Same: one box at the top, filtering live |
| Match the summary, not just the title | AOSP's index explicitly carries title + summary + keywords | Same: label and detail text both searched |
| Keep the grouping visible | macOS and GNOME both keep their category list and reveal matched panes rather than flattening results into one list | The list is ranked by the words that matched (2026-10-27), so a flat result list is the point; one category heading was left, and it is put away during a search |
| Show *why* it matched | VS Code's settings editor shades the matched substring and has `@modified`-style scopes ([Steve Kinney](https://stevekinney.com/courses/visual-studio-code/editing-settings-through-the-vs-code-ui)) | Same: matched text is marked |
| Keyboard-first | macOS Settings, GNOME and KDE all let you reach the box and leave it without the mouse | Desktop: Ctrl+F / Alt+F to focus, Escape to clear |
| A real empty state | Empty states are a named pattern with their own guidance, not a blank panel ([Octopus Design System](https://www.octopus.design/latest/patterns/ui-patterns/layouts/empty-state-YMQIoJ84)) | A written no-match line plus a way back |

**Where the evidence is thin, honestly:** I could not fetch the AOSP page's
own body text (the fetch came back as navigation chrome only), and GNOME's
search-in-the-shell design is documented in blog posts and code rather than a
specification anyone maintains. The KDE and iOS claims in my searches came
back as translated wiki pages and support articles, not documentation of the
search behaviour itself - so nothing above rests on those. The six rows in
the table are the ones I could stand behind; the pattern they agree on is
consistent enough to build against.

## Questions only the owner can answer

**1. The "Rare" band.** *Answered 2026-10-27: both frequency bands were removed
- see the amendment above.* The question was asked when the page had three
headings - Everyday, Rare, What Jarvis does - and Rare was where the
machine-level cards lived (security, voices, hardware, the second graphics
card, backups, updates).

- **Leave the three bands as they are** (recommended). Search is what makes
  things findable; the bands cost one line of screen and still tell you what
  kind of thing you are looking at.
- **Fold Rare into one collapsed "Rare and advanced" group**, closed by
  default, so the page opens showing Everyday only.

**2. What happens when you press Enter on a search.**

- **Nothing - the list is already filtered, so you just scroll and read**
  (recommended, and what is built).
- **Jump to the single best match and flash it**, so a one-result search
  takes you straight there.

**3. Words that are not on the page.** Searching "night" will not find
"Quiet hours"; searching "privacy" will not find "Security".

- **Leave it - search what is written** (recommended). Nothing to maintain,
  nothing to go stale.
- **Add a small hand-written synonyms list per card** (say 100 lines),
  which has to be kept up to date every time a card changes.

**4. The phone's "Jump to:" row.** It is 20 buttons over four lines at the
top of Settings.

- **Keep it, and put the search box above it** (recommended) - the buttons
  are still the fastest way to a section you already know.
- **Replace it with the search box**, so the phone's Settings opens with one
  text field and nothing else.

## Amendment, 2026-10-27: no Everyday/Rare bands, and the search ranks what it finds

The owner, after using the page: *"when i search update in the settings page on
the jarvis desktop, updates is not the first thing that comes up, its considered
rare in the settings, get rid of the general clasification of everyday settings
with things like everyday or rare in settings, search bar should search for
matching terms"*.

Three things changed, and one deliberately did not:

- **The Everyday and Rare bands are gone** from `settings.html` and from its
  jump list, with their two headings and two labels. Every card, section id,
  anchor and jump link is unchanged; the jump list is one unlabelled group of
  the editable cards, then the one labelled "What Jarvis does" group. The
  heading that is left says what those cards do (report, not change), which is
  a fact on the page rather than a claim about how often the owner needs them.
  Question 1 below is therefore answered: the bands are removed, not folded.
- **Results are ranked by where the words matched.** Card title or a name the
  menus catalogue already answers to for it first (exact, prefix, typo), then
  its labelled rows, then its detail text; ties go to the shorter title, then
  the title itself. Nothing reads the section, the old band, or document order.
  This is the desktop's own ordering rule; the phone's `SettingsSearch` matching
  contract (the tiers, budgets and prefix guard) is untouched.
- **The page's one heading and the jump list are put away while a search is
  on**, because a ranked list with a category heading in the middle of it is
  two orders at once. They come back, with the page in its original order, when
  the box is cleared.
- **What did not change** is the rest of this document: search is still a view
  that writes nothing, changes no setting, clears back to the same page, and a
  card hidden through "Show or hide menus" stays hidden. The "update" alias for
  the Updates card lives in `backend/jarvis_menus.py` - the catalogue the rest
  of the app already matches cards by - not in a second list kept here.

## Claims

Added to `docs/CLAIMS.tsv`, so the statement cannot rot:

```
S01  both apps' settings can be searched, desktop and phone   grep:jarvis-desktop/src/settings.html:id="settings-search"   built   docs/SETTINGS-UX-DESIGN.md
S02  the phone's settings search uses the same words as the desktop's   grep:jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/SettingsSearch.kt:SettingsSearchWords.LABEL   built   docs/SETTINGS-UX-DESIGN.md
```

Nothing else here needs a row: "no setting was removed" is not a claim a grep
can make honestly, and the existing desktop suites (19 of them read
`settings.html`) already hold the ids and words that matter.

## Amendment, 2026-10-28: the phone answers with the sections that NAME the words, and its Settings keeps room for the approvals line

Two defects found on the owner's phone by Gemini's review (`F4`), both in the
phone's Settings screen. Neither changes a setting, a row, a jump target or the
desktop's page.

- **A passing mention no longer answers while something names the word.** The
  phone's box filters in the screen's own draw order and never ranked, and
  every field was one bag of words, so typing **"pair"** returned VOICE,
  APPEARANCE, DEVICES: the first two only *print* the conditional line "Pair
  with your desktop first - these settings live on it.", Devices carries the
  button "Pair with your PC", and all three hits were the same weakest tier. A
  section's heading, the names of the controls drawn on it (`Row.titles`) and
  the index's own synonyms (`Row.label`) are now the words it **NAMES**; the
  sentences it prints (`Row.quotes`) are not, and a mention-only match answers
  **only while no section names what was typed** (`SettingsSearch.namesIt`, the
  rule in `matching`). So "pair" answers Devices alone, "pair with your pc" and
  "unpair" find it too, and "pair with your desktop" still finds the two
  sections that print it. Devices' card now indexes both of its buttons, so the
  section is findable by the words on them, the same rule the 2026-10-13
  switch-title defect established for `SwitchRow`s. **This is not the desktop's
  ordering rule** - the desktop sorts every match by rank
  (`compareMatches`); the phone cannot re-cut a `LazyColumn`'s items, so the one
  thing a fixed-order screen can do is refuse to answer with the weaker source.
  The four tiers, the edit budgets, the prefix guard and `rankPart` are
  untouched, so the shared cross-app fixture still holds both engines to one
  rule set, and the phone's own `FindAnything` (which already scores its rows)
  is untouched.
- **Room for a fixed overlay is measured, not typed in.** The phone's "Needs
  your OK" line is drawn OVER every screen but Home, so it takes no room from
  the screen under it; the list's 16 dp bottom padding left the last card's
  last control under it, and "Unpair & clear the token" showed as a 6 px sliver
  (the button at `[90,2058][990,2202]`, the line's top at `y=2064` on a
  1080x2412 phone). `MainActivity` now measures the drawn line
  (`onSizeChanged` - it wraps the PC's own card title, so its height is not a
  constant) and `BottomReserve` turns that into the room a scrolling screen
  keeps: the line, its 12 dp edge gap and 10 dp of air, added to Settings' own
  padding. Nothing is reserved when no card waits. A screen that gains a fixed
  overlay later follows the same rule: reserve the *drawn* height plus the gap,
  and opt in, because reserving room an overlay does not use is blank space.
  `BottomReserveTest` holds the arithmetic and the wiring; a Compose layout
  cannot be measured in the JVM suite, and the test says so rather than implying
  a rendered-pixel check.

