# HUD edit parity: one main screen, chosen once, drawn by both apps

**Owner's requirement (2026-10-29, their own words):** *"for features that I
would like EASILY accessible in jarvis desk jarvis Android app, make sure I can
add them to the main screen through the edit jarvis hud on desktop and make an
equivalent edit android hud for the android app."*

Status: **desktop half built in this PR; the shared route and the phone half are
NOT built.** Section 7 is the work order for the phone, and section 4 marks
exactly which half of the persistence exists today.

---

## 1. What exists today, and why it does not do this yet

Read in this worktree (`feat/hud-edit-parity-2026-10-29`, taken from
`origin/main` at `caaff3e3a`).

**The desktop already has an Edit HUD screen.** `jarvis-desktop/src/hud-edit.js`
is the editor, `hud-layout.js` is the data. It is genuinely good: one reducer
(`applyAction`) is the only way a layout changes, 18 cards in `CARD_REGISTRY`,
seven built-in presets, three drag regions, offline-safe saving.

**But it can only rearrange the cards that are already there.** Three specific
walls, each verified in the source:

1. **`MOVABLE_IDS` is a hand-written list of 11 ids** (`hud-edit.js:77-89`).
   A card that is not in that list cannot be moved, resized or hidden, and the
   toolbar says only *"This part of the HUD stays where it is."* (`FIXED_REASON`,
   line 116).
2. **A card that is not in the layout has no presence at all.** `ensureShells()`
   (line 462) walks `layout.cards`; a card absent from the document is never
   drawn, so there is no control that could add it back. `setVisible` hides and
   shows a card that is already in the document — it cannot create one.
3. **The registry is HUD structure, not features.** Its 18 entries are regions
   of the HUD page (nav, lanes, telemetry, approvals, conversation…). Not one of
   them is a Jarvis *feature* the owner would name — there is no Calendar card,
   no Health card, no Pictures card, no Today card. The four "stage" rows
   (`galaxy`, `reminders`, `memory`, `conversation`) are stage *tabs*, and
   `hud-edit.js`'s own header says stage editing is "H3/H4 territory"
   (lines 25-28).

**The phone has a home layout model but no editor and no main screen that obeys
it.** `jarvis-client/.../net/HudLayout.kt` (453 lines, 2026-10-22) is a real
model — four sections, five presets, a reducer, protection, JSON. It is stored
in the phone's own `SharedPreferences` (`MenuPrefs.kt` `KEY_HUD_LAYOUT`), and
nothing in `ui/` or `MainActivity.kt` reads `MenuPrefs.hudLayout`
(a `git grep` for `hudLayout|applyLayout` under `ui/` and `MainActivity.kt`
returns nothing). So today the phone's model is **not wired to any screen**, and
even when it is, it will be a *second, separate* choice: the phone's sections
(`top_strip`/`hero`/`body`/`composer`) and card ids are its own, and nothing in
the phone's storage is readable from the PC.

**So the gap is exactly what the owner said.** Adding a feature to the main
screen does not exist on either app, and "the same choices apply on its main
screen" is impossible today because the two apps store two unrelated documents
in two unrelated places.

## 2. The decision, in plain words

**One catalogue of feature cards, one shared choice, two screens that draw it.**

- **One catalogue.** Every feature that makes sense as a main-screen card gets a
  *key*, and the key is the feature's own id in `features/features.json` — the
  list both apps already ship (`jarvis-desktop/src/features.json`,
  `jarvis-client/.../assets/features.json`, byte-identical, checked by
  `tools/check_feature_list.py`). So a card cannot name a feature that does not
  exist, and "one id is one feature in both apps" is the same rule
  `MenuCatalog` already runs on.
- **One shared choice.** The choice — which cards, in what order, on or off — is
  ONE document, saved on the PC's backend so both apps read the same thing. Not
  per app, not per device: the owner asked for *the same choices*.
- **Two screens.** The desktop draws it in the HUD's main screen. The phone
  draws the same keys, in the same order, in its own geometry (its four
  sections, one column below 600 dp). Neither app stores its own copy of the
  choice; the phone's existing `SharedPreferences` layout stays as a *fallback*
  for "the PC has never been asked", never as the truth once it has.

## 3. The card catalogue

The catalogue lives in `jarvis-desktop/src/home-cards.js` as `HOME_CARDS`,
mirrored to the phone as JSON. A card is in it when **all** of these hold:

- it is a thing the owner opens and uses, not a settings row and not a
  warning (so `what-asks-first`, `app-lock`, `stop-everything` and the other
  safety surfaces are **not** cards: ruling 25 says a safety surface is never
  editable, never hiddenable, never movable, and that rule is older than this
  request);
- it works on at least one of the two apps (`apps`);
- it has a place of its own to open (`opens`), so a card is a door, not a
  duplicate of a panel that is already permanently on screen.

`calendar` is `surface: "desktop"` in `features.json`, so its card is
`apps: ["desktop"]` and the phone will not draw it. **Health is not a feature
yet** — there is no `health` id in `features.json`; the closest real ones are
`crisis-help` and `sensitive-facts`, which are not the same thing. No card is
invented for it. §7.4 is the three-line recipe for adding it the day its
backend lands, and the test suite uses `health` as its *stub key* to prove that
a brand-new feature key can be added to the main screen and appears.

Columns: `key` (also the `features.json` id), `label` (the owner's words),
`about` (one plain sentence), `apps`, `default_on`, `size` (the size it is added
at), `min_size` (the smallest size the editor will let it be), `opens` (where
the card takes you). Sizes are the editor's existing four: `S` = 4 columns,
`M` = 6, `L` = 12 wide, `T` = 12 wide and 2 rows tall. On the phone the same
`min_size` means "one column" for `S`/`M` and "full width" for `L`/`T`.

The 24 cards, with the defaults this PR ships:

| key | label | apps | default | size | min |
|---|---|---|---|---|---|
| `today` | Today | both | **on** | M | S |
| `coming-up` | Coming up | both | **on** | M | S |
| `now` | Right now | both | **on** | S | S |
| `settings-entry` | Settings | both | **on** | S | S |
| `calendar` | Calendar | desktop | off | M | S |
| `briefing` | Morning briefing | both | off | M | S |
| `memory-tab` | Memory | both | off | M | S |
| `pinned-facts` | Always keep in mind | both | off | S | S |
| `topics` | Topics | both | off | S | S |
| `wiki` | Wiki | both | off | M | S |
| `galaxy` | Galaxy | both | off | T | L |
| `pictures` | Pictures | both | off | M | S |
| `quiz` | Quiz me on a text | both | off | M | S |
| `decks` | Study decks | both | off | M | S |
| `focus` | Focus session | both | off | S | S |
| `jobs` | Background jobs | both | off | M | S |
| `undo` | Undo shelf | both | off | S | S |
| `voice-check` | Voice check | both | off | S | S |
| `models` | Models | both | off | M | S |
| `compute` | Compute | both | off | S | S |
| `skills` | Skills | both | off | S | S |
| `spending` | Spending | both | off | M | S |
| `retirement` | Retirement what-if | both | off | M | S |
| `projects` | Projects | both | off | M | S |

`today`, `coming-up`, `now` and `settings-entry` are on by default because they
are the four the HUD's own main screen already answers to (the Today tab, the
right-rail "Cards waiting"/telemetry pair, and the menu's Settings row), so a
fresh install looks like it does today and nothing is added that the owner did
not ask for.

## 4. Where the choice is kept — and why no new permission tier

**The document.** One JSON object:

```json
{ "version": 1,
  "cards": [ { "key": "today", "on": true, "order": 0 } ],
  "updated_at": 1790000000 }
```

Closed world, exactly like `hud-layout.js`'s `normalizeLayout`: an unknown `key`
is dropped, a duplicate `key` keeps its first place, `order` is re-numbered
0..n-1, `on` is a boolean, a wrong or missing `version` reads as the default
document, and a card that is in the catalogue but *not* in the list is simply
not on the main screen (removed). Removal is therefore "absent from `cards`",
never a third state.

**Where it is saved.**

- **Desktop, built now:** the HUD window's own store, under one key
  (`jarvis.hud.home_cards.v1`), read once at boot and written after every
  change. It is a real store - the same one the HUD's first-paint preview
  already uses (`hud-layout-store.js`'s `PREVIEW_KEY`) - and a refused write is
  reported as "Not saved", never painted as saved.
- **Desktop, NOT built yet:** moving the document into the PC's settings store
  (`jarvis-desktop.json`, beside `hud_layout`, so it survives a webview wipe and
  can be published for the phone). That needs `home_cards` carried through both
  closed-world normalizers - `hud-layout.js::normalizeLayout` and
  `hud_layout.rs::sanitise` - which is the one piece of this contract that is
  deliberately not in this PR.
- **Shared with the phone, NOT built yet:** `GET`/`POST /api/home-cards` on the
  PC's backend, serving that same document, and the desktop writing it through
  one narrow Rust command (the HUD page holds no token, so it cannot POST
  itself). **The phone cannot be built without this route.** It is the first
  item of section 7.
- **Neither app invents state:** until the route exists the phone keeps its own
  stored layout (today's `MenuPrefs` key) and says so; the first time the
  desktop saves through the route, that copy becomes the answer for both.

**Why this needs no new permission tier, proved rather than asserted.**

1. It changes nothing about what Jarvis *does*. The document says which doors
   are drawn on a screen and in what order; every door it draws is a door both
   apps already have, opening the same screen it opens today.
2. It raises no approval card because it is not a loosening: nothing is
   switched on, nothing is granted, no model is changed, no file is read. It is
   the same class as `theme` and `hud_layout`, which the design already records
   as *"an appearance-class document, not a dumping ground"*
   (`hud-layout.js:76-82`) and which is saved with **no backend call, no pairing
   token and no approval card** (`hud-layout-store.js:5-9`).
3. It cannot be used to hide a safety surface. `approvals`, `emergency_stop`
   and the connection/stale-link warnings are **not in the catalogue at all**,
   so there is no key an owner (or a hand-edited file, or a hostile document)
   could add, remove, reorder or switch off. The rule that a layout may never
   dismiss a warning (ruling 25, and `HudLayout.kt:36-38` on the phone) is kept
   by the catalogue's shape, not by a check that could be forgotten.
4. It is bounded: the catalogue is 24 keys and the document holds at most one
   entry per key, so the document cannot grow without a code change.

## 5. The off state — never blank, never raw JSON

A card must always say something true. `cardState()` in `home-cards.js` gives
the editor and both screens the same three words:

| state | when | what is drawn |
|---|---|---|
| `on` | the feature is available | the card's own tile: its label, its one-line `about`, and an Open button |
| `off` | the feature exists but its switch is off, or its backend is disabled | the label, then **"<Label> is turned off. Turn it on in Settings."** — no blank, no console text |
| `missing` | the PC does not have this feature at all (older backend, or the app is not the one it runs on) | the label, then **"<Label> is not on this PC yet."** |

`unknown` is deliberately **not** treated as off: when the screen has not asked
yet it draws the card, because "I have not checked" is not "turned off". That is
the same honesty rule the rest of the project runs on (`/api/status`'s `null`
for a latch, "not said" is not "not latched").

## 6. What the desktop half does (this PR)

1. **Edit HUD gains a "Main screen" panel** at the top of the stage while
   editing (`#hud-home-cards-editor`). It lists the whole catalogue in two
   groups — **On the main screen** (with ↑ ↓ Remove) and **Not on the main
   screen** (with Add) — and each row says which apps draw it and its smallest
   size. Add, remove and reorder all go through **one** function,
   `applyHomeAction`, the same one-writer rule `applyAction` already follows.
2. **The HUD's main screen obeys it.** A new strip above the conversation
   (`#hud-home-cards`, `data-hud-home` region) draws the chosen cards in the
   chosen order, each as a real tile: label, one plain sentence, an Open button
   that goes to the place that card stands for. A removed card is gone; a card
   whose feature is off shows the sentence from §5; nothing is ever blank.
3. **Saved in the HUD window's own store.** A save that did not happen is
   reported as not saved, never as saved (`hud-layout-store.js`'s rule). The
   PC-settings-store move and the shared `/api/home-cards` route are the next
   slice, not this one.
4. **The three vendored copies of the HUD page stay byte-identical**
   (`jarvis-desktop/src/`, `backend/`, `jarvis-backend/`), and
   `python -B tools/check_stale_twins.py` is clean.

## 7. What the Android agent must do (the phone half)

**7.1 Read one route, store nothing of its own.**

- `GET /api/home-cards` → `{ "available": true, "version": 1, "cards":
  [ { "key": "today", "on": true, "order": 0 } ], "catalogue": [ … ] }`.
  The `catalogue` array is the same 24 entries with their `apps`, `size` and
  `min_size`, so the phone never hard-codes a list that could drift.
- `POST /api/home-cards` with `{ "version": 1, "cards": [ … ] }` → the stored
  document. A stale event stream refuses it, like every other write (rule 4);
  a layout write raises **no approval card** (§4).
- Put both calls in a new `net/HomeCards.kt` beside `HudLayout.kt`, with the
  same `JarvisApi` client and the same `X-Jarvis-Client: phone` header.
- `404` (an older PC) is **not** an error: fall back to `MenuPrefs`'s stored
  `hud_layout`, and say on the edit screen: *"This PC's Jarvis does not have
  the shared main screen yet. Update the backend by running apply-patches.ps1."*

**7.2 Draw the same list on Home.** Home's main screen draws the document's
cards in `order`, filtering out any whose catalogue entry does not include
`"phone"`. Reuse what `HomeScreen.kt` already draws for each key — this slice
adds no new plate, no new route and no new control. A card in the `off`/
`missing` state uses the exact sentences in §5, never an empty plate.

**7.3 The equivalent Edit Android HUD screen.** A new settings plate
(`ui/screens/HomeCardsPlate.kt`), reached from the existing Settings list, with
the same two groups as the desktop panel:

- **On the main screen** — one row per chosen card: its label, "Move up"/"Move
  down" buttons and a "Remove" button. TalkBack on every control (the phone's
  standing rule), a confirmation only for Remove ("Remove Today from the main
  screen?" — the owner keeps such questions for anything they cannot undo in
  one tap).
- **Not on the main screen** — one row per remaining card the phone can draw:
  its label, its one-line `about`, and an "Add" button.
- A "Reset to the usual four" row at the bottom.
- One writer: `HudLayout.apply` extended with `Add`/`Remove`, or the shared
  document's own reducer mirrored — **one** path, exactly as the desktop's
  `applyAction` and the phone's existing `HudLayout.apply` already are. Drag is
  optional; the buttons are the required interface (WCAG 2.2 SC 2.5.7, the same
  claim the desktop editor makes).
- The screen never writes `SharedPreferences`: it posts the document and shows
  what the PC answered.

**7.4 Adding a feature later (this is how `health` lands).** Three lines in
`home-cards.js`: one entry in `HOME_CARDS` (`key: "health"`, its label, `apps`,
`default_on: false`, `size`, `min_size`, `opens`), and the generated JSON the
phone reads. Nothing else changes — the editor, both screens and the tests pick
it up. `tests/home-cards.mjs` proves this today by adding a stub `health` key
and checking it appears in the catalogue, can be added, is drawn, and shows its
off state.

## 8. What this PR does **not** do

- It does not touch a single Kotlin file (the phone half is §7).
- It does not build the calendar or health features, or change what any feature
  does. Every card is a door to a screen that already exists.
- It does not replace the desktop's `hud-layout.js` registry. The two are
  different questions: `hud-layout.js` arranges the HUD's own panels;
  `home-cards.js` chooses *which features* are on the main screen. A card in
  one is not a card in the other, and the design says so in both files.
