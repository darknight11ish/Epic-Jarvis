# Galaxy "facts behind this dot" panel: design (2026-09-30)

Status: **built** (re-checked 2026-10-05: the desktop panel is
`jarvis-desktop/src/galaxy-panel.js`, documented in JARVIS-API section 106.4;
this page called itself a design until the claims register re-checked it).
Queue item 8 (JARVIS-API section 106, shared with
the "new section here" marker in `docs/OVERNIGHT-TAGS-DESIGN.md`). The owner ticked
"a Galaxy facts panel" on 2026-09-30.

In one sentence: in the Galaxy, when you pick a dot (a person, pet, place or
thing), a panel lists the saved facts that name it, in their own words, newest
first, so you can see *why* that dot exists.

## 1. What is there today

- The Galaxy (Brain -> Advanced -> Galaxy, `jarvis-desktop/src/galaxy-view.js`,
  drawn by `brain.js`) is built from `GET /api/memory/entities` (JARVIS-API
  section 6 and 71.3). Each entry has `id`, `name`, `kind`, `also`, `aliases`,
  `fact_ids` (newest first) and `facts` (a count). **No fact's words** are in that
  list.
- Picking a dot (`select(node)` in `brain.js`) shows counts, names and one button,
  "About <name>", which jumps to the Memory tab where the facts are read word for
  word.
- The facts' words are read by id from `GET /api/memory/used?ids=` (1-100 ids;
  `brain/used.rs`), which is already hidden while private lists are hidden.
- **The phone has no Galaxy.** CLAUDE.md: "do not build ... the memory graph ...
  on the phone". `/api/memory/entities` is classified "no - by rule" in
  JARVIS-API section 6, and section 71.3 ends "The phone has no Galaxy".

## 2. Decisions (the rules the build must keep)

1. **The only source is the facts store.** The panel uses the dot's `fact_ids`
   and nothing else: no chat ids, no document ids, no note text, no email, no
   `/api/graph`, no web. It never opens History or chat history.
2. **No new backend route and no new library.** It reads the two routes above
   that already exist. No JavaScript library is added (the desktop has no bundler;
   nothing new in `brain.html` `<script src>`), and the layout is plain HTML rows,
   like the "About <name>" page. A test checks both.
3. **Read-only.** The panel changes nothing: no Forget, Erase, Pin or edit buttons
   in it (they stay in Memory -> About, one click away). So there is **no gate
   action and no tier** to add. Facts are shown exactly as the Memory tab shows
   them: the panel never shows more than that tab.
4. **Hidden with the other memory lists.** The words come through `memory_used`,
   which Rust already empties while Windows Hello hides the memory lists (the
   Galaxy itself is empty then, so no dot can be picked). If the lists become
   hidden while the panel is open, it is cleared at once and says `Hidden. Show
   memory lists to see these facts.` Words are never cached on the page after
   that.
5. **Erased and retired facts.** An erased fact comes back with empty text: the
   row reads `Erased. Only the dates are kept.` and shows the dates. A fact that
   is no longer current (`current` false) is marked `Forgotten` and sorted after
   the current ones, matching the Memory tab. Facts hidden by an Off topic
   (section 107) must not appear: the builder **checks** that `memory_used` /
   the entity list already leave them out and adds a test; if `memory_used`
   would return one, the panel drops it and says `{n} hidden by topic settings`
   (a count only).
6. **Paged, not dumped.** The first 20 facts (newest first). A `Show 20 more`
   button reads the next 20 ids (one `memory_used` call each, never more than 100
   ids, never all at once). A dot with 500 facts stays quick.
7. **Numbers come from code.** The heading count is `fact_ids.length` from the
   list, not anything the model said. No model is involved anywhere.
8. **Sensitive facts** are shown as the Memory tab shows them (words, since the
   owner is looking at their own list, on screen only). Nothing here is read
   aloud, saved or sent anywhere.

## 3. What the owner sees (desktop)

Picking a dot opens the existing side panel. Under the current lines it gains a
section:

- Heading `Facts behind this dot ({count})`.
- A list, one row per fact: the fact's words, the date it was saved, and marks
  `Pinned` / `Forgotten` where they apply.
- `Show 20 more` while there are more; the line `Showing 20 of 43` beside it.
- `About <name>` stays where it is, and each row has a small `Open in Memory`
  button that goes to the same "About" page.
- Loading: `Reading the facts...`; a failed read: `Your PC could not read these
  facts.` with `Try again`. Empty list (all erased): `No facts to show.`

Shared words (word for word; new keys `galaxy_panel*` in a shared fixture the
desktop test reads): `Facts behind this dot ({count})`, `Show 20 more`, `Showing
{n} of {total}`, `Reading the facts...`, `Erased. Only the dates are kept.`,
`Forgotten`, `Pinned`, `Hidden. Show memory lists to see these facts.`, `No facts
to show.`, `Your PC could not read these facts.`, `Try again`, `Open in Memory`.

Accessibility: the section is a labelled region; the list is a real list; after
`Show 20 more` focus goes to the first new row and `Showing 40 of 43` is announced
politely; the selection announcement already made by `select()` is unchanged;
nothing is drawn only on the canvas. Reduced motion and forced colours: nothing
new animates.

## 4. Both apps: the honest answer

The brief asked for both apps. The standing rule says the memory graph stays off
the phone, and the Galaxy *is* that graph, so the panel (which hangs off a dot)
has nothing to hang on there. Two choices are in question 1 below. Until the owner
chooses, the design is **desktop only**, and the reason goes into ARCHITECTURE
section 8 "One-sided on purpose" and `check_parity.py`'s note for
`/api/memory/entities` (already `no - by rule`; add the panel to the sentence).

If the owner picks the phone list (option B), the phone gets **no picture and no
links**, only a list, so the "memory graph" rule stays true in spirit:

- Brain -> Memory -> **People and things**: rows `{name}, {kind}, {n} facts`; tap
  one to open the same fact list (same words, same paging, `memory_used` by id).
- Needs `/api/memory/entities` taken off the phone's "no - by rule" list (a
  deliberate rule change, recorded in JARVIS-API section 6 and CLAUDE.md), a
  reader in `net/` (`MemoryEntities.kt`, new), `JarvisApi.kt` /
  `JarvisRuntime.kt` calls, a plate `ui/screens/PeopleThingsPlate.kt`, and the
  phone's existing hide-lists behaviour ("Hide memory lists and chat history"
  shows `N names, hidden` and reads nothing). Screenshots stay blocked under App
  lock or that setting, as today.
- Parity row for `/api/memory/entities` changes from `no - by rule` to `ported`,
  with the desktop's Galaxy noted as picture-only there.

**Standing rule changed (owner, 2026-09-30):** option B was chosen, so the phone reads `/api/memory/entities` for a plain "People and things" list (built: `net/Entities.kt`, `ui/screens/EntitiesPlate.kt`, `EntitiesTest.kt`); the phone still has no map, picture or links.

## 5. Gate, routes, parity summary

| Item | Desktop | Phone (option A) | Phone (option B) |
|---|---|---|---|
| Gate action / tier | none (read only) | none | none |
| Routes used | `GET /api/memory/entities`, `GET /api/memory/used` (both exist) | none | same two, new phone callers |
| New routes | none | none | none |
| Hidden lists | Rust empties both reads | n/a | phone hides the list |
| `check_parity.py` | no new row | note added to the existing row | row flips to `ported` |
| Docs | JARVIS-API section 106 (Galaxy part), section 71.3 sentence added | ARCHITECTURE section 8 one-sided entry | plus section 6 row edited |

## 6. Tests

Desktop (`jarvis-desktop/tests/galaxy-panel.mjs`, new; pure helpers in
`galaxy-view.js` so they run without a window):

1. `pageOfFactIds(node, page)` returns the right 20 ids, never more than 100, and
   the next page starts where the last stopped;
2. rows are built from a fake `memory_used` answer: current, forgotten, pinned,
   erased (empty text), and a `missing` id (skipped without an error);
3. an Off-topic fact is never shown (or is counted as hidden), per decision 5;
4. lists hidden: no `memory_used` call is made; an open panel is cleared and shows
   the hidden line; no words remain in the DOM after (assert the panel text);
5. the panel code never calls a chat, history, document or graph route (grep the
   source of the new functions), and `brain.html` gains no `<script src>`;
6. `Show 20 more` moves focus and announces; a failed read shows the error and
   `Try again`, and a retry works; words match the fixture keys.
Rust: the existing test that keeps `memory_entities` and `memory_used` on the
private-lists list still passes (no new command is added, so nothing else changes).
Backend: no new backend code, but `test_memory_entities.py` gets one added check
that an erased fact's id in `fact_ids` reads back with empty text through
`used_view()`, so the panel's assumption is pinned.
Phone (option B only): `PeopleThingsTest.kt` for the reader and the paging, reading
the same fixture words.
The feature audit runs with the build (bugs, both apps or the written reason,
fit).

## 7. Frozen contract for builders

(Frozen when the owner answers question 1. Where this and sections 1-6 differ,
this wins.)

- **Reads:** `GET /api/memory/entities` (already read by `memory-entities.js`,
  supplies `factIds` per node) and `GET /api/memory/used?ids=a,b,c` (up to 100,
  answer `{"facts": [{"id", "text", "current", "pinned", "created", "valid_to",
  "erased_at"}], "missing": [...]}`). **No other route, no other id type, no
  library.**
- **Desktop:** `galaxy-view.js` gains pure helpers `factPage(node, page, size=20)`
  and `factRow(fact)`; `brain.js` `select(node)` paints the section and owns paging,
  focus and clearing on lock; `brain.html` / `brain.css` gain the region and its
  rows using the existing tokens. No `lib.rs` change (no new command).
- **Words:** the `galaxy_panel*` keys in section 3, in a shared fixture the
  desktop test reads (and the phone test, if option B).
- **Docs:** JARVIS-API section 106 (Galaxy part), one sentence added to 71.3,
  ARCHITECTURE section 8 entry, `check_parity.py` note.

## 8. Question for the owner

**Question 1. The phone has no Galaxy picture (a standing rule). What should the
phone get for "facts behind this dot"?**

- **Nothing; PC only** (recommended). Keeps the rule. The phone can already show
  your saved facts in Brain -> Memory. Least to build.
- **A plain "People and things" list**, no picture, no links. Tap a name to see the
  facts that name it. This needs one written rule changed (the phone reads
  `/api/memory/entities`), and it hides itself with the other memory lists.
