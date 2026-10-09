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
- **The band headings (Everyday / Rare / What Jarvis does) stay visible**
  whenever anything under them survives a search, exactly so the page still
  says *where* the thing you found lives. A band with nothing left in it is
  hidden with its cards.
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
- **The three bands stay.** Whether they *should* is question 1 below.
- **The desktop's four other windows, the HUD, the widget and the Jarvis bar
  are untouched.**

## What it costs

- **One new desktop module** (`settings-search.js`, ~200 lines), one CSS
  block, ~40 lines of markup, and the `data-search-row` attribute on the 19
  toggle rows and the theme rows. **The generator that will splice toggle
  rows in from `jarvis_settings_registry.py` must emit `data-search-row` and
  keep the row's own id** - that is the one thing to tell whoever owns
  `tools/gen_settings_cases.py`.
- **One new phone file's worth of logic** in `SettingsScreen.kt` plus a small
  pure Kotlin object (`SettingsSearch.kt`) with the same matching rules, so
  the two apps cannot drift and a unit test can hold them together.
- **Search is client-side and text-based only.** It finds what is written on
  the page. A setting whose words do not contain what the owner typed will
  not be found - that is what a keywords/hidden-synonyms list would fix, and
  it is question 3.
- **Risk: low.** Nothing can be lost by typing in the box, and clearing it
  restores the page. The real risk is a *stale* generated row losing its id -
  which the existing tests already catch.

## What the prior art actually says

| What well-regarded settings do | Evidence | What this build does |
| --- | --- | --- |
| One box, filters as you type | Android's Universal search indexes every setting's title, summary and keywords, so a query reaches any screen from one field ([AOSP](https://source.android.com/docs/core/settings/universal-search)); macOS System Settings has had a search field in the toolbar for years ([macmost](https://macmost.com/search-inside-system-preferences.html)) | Same: one box at the top, filtering live |
| Match the summary, not just the title | AOSP's index explicitly carries title + summary + keywords | Same: label and detail text both searched |
| Keep the grouping visible | macOS and GNOME both keep their category list and reveal matched panes rather than flattening results into one list | Same: bands act as headings over what survived |
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

**1. The "Rare" band.** Today the page has three headings - Everyday, Rare,
What Jarvis does - and Rare is where the machine-level cards live (security,
voices, hardware, the second graphics card, backups, updates).

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

## Claims

Added to `docs/CLAIMS.tsv`, so the statement cannot rot:

```
S01  both apps' settings can be searched, desktop and phone   grep:jarvis-desktop/src/settings.html:id="settings-search"   built   docs/SETTINGS-UX-DESIGN.md
S02  the phone's settings search uses the same words as the desktop's   grep:jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/SettingsSearch.kt:SettingsSearchWords.LABEL   built   docs/SETTINGS-UX-DESIGN.md
```

Nothing else here needs a row: "no setting was removed" is not a claim a grep
can make honestly, and the existing desktop suites (19 of them read
`settings.html`) already hold the ids and words that matter.
