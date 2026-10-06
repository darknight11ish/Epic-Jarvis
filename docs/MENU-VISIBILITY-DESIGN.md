# Menu visibility: hide and collapse menus (design, 2026-09-30)

Status: **built** (2026-09-30; `backend/jarvis_menus.py`, `backend/test_menu_visibility.py`, JARVIS-API section 109). Owner's request (2026-09-30): "make sure I can
hide settings or collapse them to make them more compact. If I don't care about
the finance features I can hide the menu (and unhide it reasonably easily too)."
The owner's answers are in `docs/BUILD-QUEUE-2026-09-30.md` ("Menu and section
visibility", item 11). Section 12 lists what the owner must still answer.

This design was written from a code survey done on 2026-09-30. Line numbers below
are approximate and each thing built on must be re-read before building. Nothing
here was run on Windows, on a phone, or in CI.

---

## In short

- Two states per menu: **collapsed** (title stays, body folds to one line) and
  **hidden** (gone from the rail, the list and the jump links).
- Hiding only **tidies**. Nothing is turned off, no card, no Windows Hello,
  either way. The feature still works if the owner asks Jarvis.
- ONE list, "Show or hide menus", in Settings, in both apps. A switch per menu.
  Where a hidden menu used to be, a small line: "3 hidden - Show".
- **Per device** (recommended): each app remembers its own choices. No new server
  route, no parity work. The one thing Jarvis-by-voice needs is one small new
  "quick intent" (section 6).
- Some things can **never** be hidden (section 5). A test fails the build if one
  is ever put on the hideable list.
- A link that points at a hidden menu (`open_settings`, `open_brain`, "take me to
  X") still works: it shows the menu **for that visit only**, with a banner "Shown
  for now - Keep it visible / Hide again".
- "Finance" does not exist as a menu yet. Its group is empty and is not listed
  until it is built.

---

## 1. Per device or shared (decision)

**Recommendation: per device.**

Why, in plain words: the desktop and the phone do not have the same menus. The
desktop has Settings cards, a Brain rail and Work cards; the phone has Brain
plates, Settings rows and whole screens. The only id list the two apps share is
`jarvis_settings_registry.py` `SECTIONS`, and it covers desktop Settings cards
only. Brain sections have no shared ids. A person may also want a tidy small phone
and a full desktop, which per-device gives for free.

What a shared version would cost (so the owner can choose it knowingly):

1. A common id list for Brain sections and phone plates (new, must be kept in step).
2. A backend route (say `GET/POST /api/menus`) plus a live-update event on the
   event stream, like `/api/animal`.
3. A patch to the owner's backend (it lives outside this repo), a
   `docs/JARVIS-API.md` section 108, `tools/check_parity.py` classification, and
   tests in both apps.
4. A rule for an id one app does not have (ignore it).
5. A stale-link rule: a hidden-menu change made while disconnected would need
   holding and merging.

Precedent: animal options are shared (`/api/animal`); face sharpness and frame
rate are per device. Menu layout is closer to the second kind: it depends on the
screen in your hand.

Consequence to say plainly in the app: "This hides menus on this device only."
When the owner says "hide the Finance menu" to Jarvis (section 6), the reply says
which device(s) changed.

---

## 2. Two states per menu

| State | Meaning | Where remembered | How to undo |
|---|---|---|---|
| **Visible** | Default. Nothing changes. | (nothing stored) | n/a |
| **Collapsed** | Header stays, body folds to one line. Reopens on one tap. | set of collapsed ids | tap the header |
| **Hidden** | Gone from the rail / list / jump links. Listed in "Show or hide menus". | set of hidden ids | switch in the list, the "N hidden - Show" line, or ask Jarvis |

Rules:

- Collapsed is for sections that stay on the list but take too much room. It is
  offered on sections with a body (cards, plates). It is per-section and does not
  touch the hidden list.
- Hidden is for whole menus or feature groups.
- A hidden menu is also treated as collapsed if it is later shown again (it comes
  back as it was, unless "Show everything" is used).
- Neither state changes what the feature does. A hidden Quiz menu does not stop
  quiz reminders. A hidden Goals plate does not stop a goal's weekly check-in.
  (A reminder or alert that is *due* still shows through its normal channel.)

---

## 3. What can be hidden or collapsed

Key: **H** hideable, **C** collapsible, **N** never hideable (reason given).
Collapsible is generally allowed on everything that has a body, including N rows,
except where a collapsed body could hide a warning (marked "C-no").

The exact list is fixed at build time by reading the real markup. This table is
the starting point from the 2026-09-30 survey.

### 3a. Desktop Settings cards (`settings.html`, section ids)

Grouped as the page already groups them: Everyday, Rare, What Jarvis does.

| Card / area | State | Reason |
|---|---|---|
| Appearance, faces, animal options | H, C | Cosmetic. |
| Voice (talk, read aloud, hands-free) | H, C | Everyday but not safety. |
| Wake word, sounds ("I heard you") | H, C | |
| Search providers, browser engine | H, C | |
| Briefing, focus, timers settings | H, C | |
| Backups, folders, email sending, home, calendar | H, C | Off-switch state stays visible inside; hiding does not turn anything off. |
| Second graphics card and third card switches | H, C (group "Graphics cards") | Power user. |
| Talk-to-type, Live settings | H, C | |
| Chatbots and comparison settings | H, C | |
| Devices and pairing list | C only | Removing a lost phone must stay reachable. |
| **What asks first** | **N** | Safety. |
| **Security / App lock / Windows Hello** | **N** | Safety. |
| **Connection, pairing key, server address, stale-link status** | **N** | Rule 4: acting is blocked when the link is stale. |
| **Show or hide menus (the new control)** | **N** | Otherwise nothing could be unhidden. |
| `#more-options` (`<details>`) | C (already) | Already a fold. |
| `#settings-jump` link list | follows the cards | A hidden card loses its jump link. |

### 3b. Desktop Brain rail (`brain.html` `#rail-nav`)

| View | State | Reason |
|---|---|---|
| Memory | H* | *Default landing view. Fallback rules in section 8. |
| History | H | |
| Model (`faculties`) | H | |
| Work | H | Its cards are hideable separately (3c). |
| Projects | H | Group "Goals and projects". |
| Galaxy | H (already Advanced-hidden) | |
| Now | H (already Advanced-hidden) | |
| **Trust** | **N** | Holds pending approval attention (section 8). |
| **Watch** | **N** | Same reason. |

Advanced-hidden tabs keep today's behaviour (Advanced switch). "Hidden by the
owner" is a second, independent reason a tab can be missing. Both must be off for
the tab to show.

### 3c. Desktop Brain: Work cards (`.card.card-wide`)

| Card | State |
|---|---|
| Focus, Chatbot, Today, Widgets, Coming up | H, C (Coming up: C only if it holds a due-alert list) |
| Goals | H, C (group "Goals and projects") |
| Quiz | H, C (group "Study") |
| Morning briefing | H, C |
| Background jobs | H, C |
| Undo shelf | C only. Undo is a safety net; hiding it could strand a 10-minute Undo. |
| Activity | H, C |

New items to include: **Quiz** and **Review decks** (Study), **Goals**,
**Projects**, **Chat tags editor** and **Topics** (History area), **second-card
switches** (Graphics cards). Where an item does not exist yet at build time, it is
simply not in the list (section 4).

### 3d. Tray and HUD items (desktop)

| Item | State |
|---|---|
| Stop everything | **N** |
| Approvals / Show approvals | **N** |
| Connection status | **N** |
| Faces, spotlight, widget, floating, Live, Watch, chat history | H (v2 only, see section 9) |
| Open Settings, Open Brain, Quit | **N** |

### 3e. Phone Brain items (`BrainScreen.kt` plates, group headings)

| Plate | State |
|---|---|
| Model, Models cache, Second card, Third card | H, C (group "Graphics cards", where shown) |
| Goals, Coming up | H, C |
| Quiz / decks, Topics, Chat tags | H, C |
| Phone notifications plate | H, C. The switch inside stays where it is. |
| Memory lists | H, C (also has the privacy hide; the two are separate) |
| **Security / attention / approvals plates** | **N** |

### 3f. Phone Settings items (`SettingsScreen.kt`)

Same rule as 3a: cosmetic and feature settings H/C; security, App lock, connection,
"What asks first", the Show-or-hide item itself N.

### 3g. Phone screens (`Screen` enum)

| Screen | State |
|---|---|
| HOME, BRAIN, SETTINGS, INBOX (approvals), SECURITY, LIVE (Stop) | **N** |
| CHECKS, APPEARANCE, FAQ, VOICES, VOICE_CHECK, HISTORY | H as *entry points* (a row on a list), never as a route. The screen still exists so deep links work. |

Crisis help is not a menu. It appears in the answer itself and is unaffected by
any of this (also listed in section 5).

---

## 4. Feature groups (one switch hides a family)

A **group** is a named set of menu ids, defined in one small data file per app.
The Show-or-hide list shows a group as one switch with the members under it (a
per-member switch is allowed underneath).

| Group id | Members (when they exist) | Note |
|---|---|---|
| `study` | Quiz, Review decks, Topics (if study-only) | From STUDY-FROM-TEXT-DESIGN. |
| `goals-projects` | Goals, Projects | Goals feeds Projects. |
| `graphics-cards` | Second-card switches, third-card section, Models cache | For one-card owners. |
| `chatbots` | Chatbot driver, comparison, support chats settings | |
| `finance` | Spending profile card, retirement calculator | **Empty today.** Not shown until at least one member is built. |
| `home` | Home status, smart-home settings | |

Rules:

- The list only shows a group if at least one member exists in that app. Hiding
  `finance` today would be a no-op with nothing to show, so it is not offered.
- Asking Jarvis "hide the Finance menu" when the group is empty gets an honest
  answer: "There is no Finance menu yet."
- A member may be in one group only. Group ids follow the id rules in section 5.
- Hiding a group stores the **group id** (not each member). A new member added to
  the group later is therefore hidden too, which is what the owner wants ("I don't
  care about finance"). Showing the group clears the group id and any member ids.

---

## 5. Ids, storage, defaults, migration, reset, never-hideable

### Ids

- Stable, lowercase, dot-free strings, e.g. `settings.voice`, `brain.work.quiz`,
  `group.study`. Prefix says where it lives.
- **Never reused and never renamed.** A retired menu keeps its id retired.
- A stored id that no longer exists is **ignored**, silently, and dropped the next
  time the list is saved.
- Desktop Settings ids reuse the existing card ids from `jarvis_settings_registry.py`
  `SECTIONS` where they exist, so the quick intent (section 6) and deep links
  agree. Brain and phone ids are new.

### Storage

- Per device: a **set of hidden ids** and a **set of collapsed ids**, both as
  strings. Desktop: `localStorage` keys `jarvis.menus.hidden` and
  `jarvis.menus.collapsed` (JSON arrays), wrapped in try/catch, page renders
  correctly if storage is empty or blocked. Phone: `data/MenuPrefs.kt`, modelled
  on `HistoryViewPrefs.kt` ("open unless listed").
- A version number beside them (`jarvis.menus.v = 1`) so a later format can migrate.
- Nothing about menus is ever sent anywhere. No approval card.

### Defaults and migration

- **Everything visible.** Advanced tabs as today.
- There is nothing to migrate from: no previous choice exists. The existing
  `#more-options` fold and Advanced switch keep their own storage; the new store
  does not read or replace them.

### Reset

- "Show everything" button at the bottom of the list. It clears hidden and
  collapsed sets. It asks nothing (it only ever reveals things).

### Never hideable (fixed list)

1. Approvals and the approval widget/notification path.
2. Security, App lock, Windows Hello / screen lock settings.
3. "What asks first".
4. Connection status, pairing, server address, and any stale-link banner (rule 4).
5. Crisis help (it lives in answers, not menus; also kept in this list so nobody
   adds a menu for it and then hides it).
6. Stop everything (hotkey, tray entry, phone control).
7. Settings and Help themselves (the entry points).
8. The "Show or hide menus" control and the "N hidden - Show" line.
9. Trust and Watch on the Brain rail (attention badges; section 8).

The list lives in ONE array per app (`NEVER_HIDE`). The hideable registry cannot
contain any id in it (test in section 10). Collapsing a never-hideable row is also
refused where its body holds a warning ("C-no"): the stale-link banner and
approval attention cannot be folded away.

---

## 6. Deep links, places, and asking Jarvis

### Deep links to a hidden menu

Applies to `open_settings`, `open_brain`, the desktop place keys
(`SETTINGS_PLACE_KEY` `jarvis.settings.place`, Brain place events from
`windows.rs` `show_brain_at`), and the phone's `OpenPlace` `PLACES`.

Behaviour (the owner's rule: open for the visit, with a way to keep it):

1. The link **un-hides that one menu for this visit** (not stored). Its parent
   group is not un-hidden; only the target.
2. A one-line banner at the top of the menu: "Shown for now. **Keep it visible** ·
   **Hide again**". "Keep it visible" removes the id from the hidden set. "Hide
   again" restores the hidden state at once. Leaving the screen also restores it.
3. Nothing is announced or asked. It is not a card.
4. If the target is inside a hidden **Brain tab**, the tab is shown for the visit.
   If the target is a **collapsed** section it is expanded for the visit.
5. The banner is announced politely to screen readers ("Shown for now").

### Changes to existing code (design only)

- Desktop `goToPlace` (`settings.js`): today it silently does nothing when the
  target is `display:none` or removed. New order: (a) ask `menu-visibility.js`
  whether the id is hidden; (b) if so, call `showForVisit(id)`; (c) open closed
  `<details>`, scroll and focus as before. A target that truly does not exist
  still does nothing.
- Phone `OpenPlace.kt`: `PLACES` stays complete (hidden or not). The screen that
  renders the target consults `MenuPrefs` and applies the same "for this visit"
  rule. `OpenPlaceTest` keeps checking literal `item(key = ...)` text, so keys stay
  literal; the hidden filter wraps the item, it does not rename it.
- `SETTINGS_ITEM_INDEX` (hand-kept, went stale once): a hidden item shifts list
  positions, so scrolling by index breaks. Scroll **by key** for hideable items.
  A build test compares the index against the literal keys as it does now.

### Asking Jarvis

Owner's answer: "show the Finance menu" works. Proposal: **one new quick intent**
in `backend/jarvis_quick.py`, answered with no model.

- Phrases (fixed grammar, in the same style as `_OPEN_SETTINGS`):
  `hide|show|collapse|expand (the )?<name> (menu|section)`, and "show everything /
  show all my menus".
- Intent name: `menu_visibility`. Route field in the response header:
  `menu_visibility` with `{"action": "hide|show|collapse|expand|reset", "target":
  "<id or group id>"}`. Both apps handle it in the same place they handle
  `open_settings` (desktop chat handler; phone `ChatSession` reading
  `X-Jarvis-Route`).
- Names resolve through a small alias table (`finance`, `spending`, `quiz`, ...).
  Unknown name: "I don't know a menu called that." Never guess.
- **The backend does not know which app asked.** The reply is the same for both,
  so the words say so plainly: "Done. On the devices that are open, the Finance
  menu is hidden." Each app applies it to itself. A device that is off or
  disconnected does not change. The owner is told in the Show-or-hide screen's
  help line: "Asking Jarvis changes every device that hears it."
- Hiding by voice or text is **immediate, no card, never**. Showing is immediate
  too. Neither goes near the gate.
- **Never-hideable ids are refused by the app** and the reply says "That one stays
  visible so you can always reach it." (The backend also refuses them in the
  alias table, belt and braces.)
- A hidden-menu feature asked for by name still works: "start a quiz" runs a quiz
  whether or not the Quiz menu is hidden.

### The "what can I say" list (8-sentence maximum)

`backend/jarvis_sayable.py` `SENTENCES` must hold 5-8 sentences and
`test_sayable.py` checks every one against `jarvis_quick.match()`. Do **not** add a
ninth sentence. If the list is already 8, either replace the weakest sentence with
"hide the Finance menu" (owner's call, question Q3) or leave the phrase off the
list and document it in the Show-or-hide screen's own help line. Also note it in
`tools/gen_sayable_cases.py` if the fixtures need regenerating, and re-run it.

### JARVIS-API

Reserve **section 108** ONLY for the quick intent's route field (documented shape,
that the backend is app-blind, and the reply wording). If the owner declines the
voice piece, no route is added and 108 stays free. No new HTTP route in any case
(per-device storage), so `tools/check_parity.py` should stay clean; re-run it
anyway, and if the route field is treated as a new "route" by that tool, classify
it as `both`.

---

## 7. Accessibility

- **Show or hide menus** is a plain list of native checkboxes (or switches with
  `role="switch"` and an `aria-checked` the browser keeps in step). Every row has
  a text label and a one-line description ("Hides Quiz and Review decks"). No
  colour-only state. Groups use `<fieldset><legend>`.
- Tab order follows visual order; arrow keys are not required.
- Collapsible headers are real `<button>` elements with `aria-expanded` and
  `aria-controls` pointing at the body. The phone uses `Modifier.semantics`
  with an expanded/collapsed state description ("Expanded", "Collapsed") and a
  click action.
- **Focus after hiding:** when a menu is hidden from the list, focus stays on its
  switch (the list does not reflow under the pointer). When hidden from the menu
  itself (a "Hide" action on its header, if built), focus moves to the next
  visible sibling, else to the "N hidden - Show" line.
- **"N hidden - Show"**: a real button, reads "3 menus hidden. Show or hide menus."
  Shown in the place where hidden items were (bottom of the rail or list, top of
  Settings). Hidden when N is 0. Its count updates through a polite live region.
- Reduced motion: collapse animation off (instant) when the system asks.
- The banner for a deep link (section 6) is a polite live region and its two
  buttons are reachable by keyboard.

---

## 8. Brain rail specifics (desktop)

Problems found in the survey and their fixes:

1. **Roving tabindex assumes Memory is tabindex 0.** New rule: the tab with
   tabindex 0 is the **first visible tab** in `visibleTabOrder()`. `visibleTabOrder()`
   is the one place that filters (Advanced switch AND owner-hidden set). Arrow
   keys move through visible tabs only.
2. **Default view.** If Memory is hidden, the landing view is the first visible
   tab. A place event for a hidden tab shows it for the visit (section 6).
3. **Badge counts.** `countAdvanced` surfaces pending Trust/Watch attention. Trust
   and Watch are **never hideable** (section 5), so their attention cannot vanish.
   For hideable tabs that carry a count (History, Work, Projects), a hidden tab's
   count folds into the "N hidden - Show" line as "N hidden (2 need you)", so a
   waiting item is never fully invisible. Pending *approvals* are separately
   surfaced by the approval widget and are unaffected.
4. **Panels.** A hidden tab's `#view-<key>` stays in the DOM but is `hidden` and
   not focusable; scripts that expect it to exist keep working. Removing nodes is
   avoided so existing code and tests do not break.
5. **Work cards** hide and collapse by a class on the card; `.card.card-wide`
   layout is not otherwise touched.

---

## 9. Tray items

The tray (`src-tauri/src/tray.rs`) is built once and its handles are held in a
struct. Hiding a tray item means rebuilding or toggling visibility at runtime,
across the JS and Rust boundary.

**Recommendation: leave the tray alone in v1**, and say so in the app: "The
system-tray menu is not affected." Reason: the tray is the safety exit (Stop
everything, approvals, connection status, Quit) and its extras are few. Hiding
them adds Rust changes, a JS-to-Rust command, and a test that cannot run here
(`cargo test` needs Windows).

**v2, only if the owner wants it:** allow hiding only Faces, spotlight, widget,
floating, Live, Watch and chat history, by making those handles' visibility
depend on a Rust-side copy of the hidden set, updated by a new Tauri command when
the list changes. Stop everything, approvals, status, Settings, Brain and Quit stay
fixed. Checked with `cargo fmt`, `cargo check` and `cargo clippy` against
`x86_64-pc-windows-msvc` with the newest stable Rust, as CLAUDE.md says.

The HUD window follows the same rule: never hide its status or approval area.

---

## 10. Tests

### New tests

1. **Never-hide guard (both apps):** every id in `NEVER_HIDE` is absent from the
   hideable registry, and no registry entry has a parent in `NEVER_HIDE`. Fails
   the build if someone adds a safety id. Phone: `MenuPrefsTest`. Desktop:
   `tests/menu-visibility.mjs`.
2. **Every hideable id exists:** desktop, each id is found in `settings.html` /
   `brain.html` markup (an element with that id) and, for Settings cards, in
   `jarvis_settings_registry.SECTIONS`. Phone, each id matches a literal
   `item(key = "...")` in the source, like `OpenPlaceTest`.
3. **Stale id ignored:** unknown ids in storage neither crash nor show.
4. **Group rules:** an empty group is not listed; a member belongs to one group.
5. **Deep-link visit:** `showForVisit(id)` reveals without storing; "Keep" stores
   the change; "Hide again" restores.
6. **Rail fallback:** with Memory hidden, first visible tab has tabindex 0 and
   receives focus; Trust/Watch cannot be added to the hidden set.
7. **Quick intent:** `backend/test_quick_menu_visibility.py` covers the phrases,
   unknown names, never-hideable refusal and the app-blind reply text.
8. **Storage failure:** with `localStorage` throwing, the page renders everything
   visible.

### Existing tests likely to break (check each, update only what must change)

- Desktop: `tests/a11y.mjs`, `tests/ia.mjs`, `tests/big-model.mjs:81` (card order),
  `tests/animal-settings.mjs:108` and `tests/browser-engine.mjs:170` (jump links).
  If a new "Show or hide menus" card is inserted, fix these by order, not by
  loosening the checks. Playwright cannot download Chromium in this container, so
  they are unexecuted here.
- Backend: `test_settings_registry.py` (new card id, if it is registered),
  `test_sayable.py` (only if a sentence changes), `test_quick.py` for the new intent.
- Phone: `OpenPlaceTest`, and the `SETTINGS_ITEM_INDEX` check.
- `tools/check_parity.py` only if a route is added (none planned).
- If any `backend/*.patch` changes, run `git fetch --unshallow origin` and then
  `python3 tools/build_patch_history.py` before committing.

---

## 11. Files and modules

### Desktop

- New `jarvis-desktop/src/menu-visibility.js`: **pure module** (no DOM). Holds
  the registry, `NEVER_HIDE`, group table, `isHidden(id)`, `hide(id)`, `show(id)`,
  `showForVisit(id)`, `collapse/expand`, `reset()`, `hiddenCount()`, storage with
  try/catch. Unit-testable in Node.
- `settings.js`: `goToPlace` change, the Show-or-hide card, collapse buttons on
  headers, jump-link filtering.
- `settings.html`: the new card (last in "Everyday" or first in "Rare"; owner picks,
  Q2); a wrapper attribute `data-menu-id` on each hideable card.
- `brain.js`: `visibleTabOrder()`, roving tabindex, default view, badge folding,
  Work-card hide/collapse.
- Chat handler that reads the route header: apply `menu_visibility`.
- Rust: **none in v1** (tray unchanged, section 9).

### Phone

- New `data/MenuPrefs.kt` (like `HistoryViewPrefs.kt`): hidden set, collapsed set,
  version, `visitOverride` in memory only.
- `ui/screens/MenuVisibilityPlate.kt` (or a section): the Show-or-hide list.
- `BrainScreen.kt`, `SettingsScreen.kt`: filter items by `MenuPrefs`, keep keys
  literal. `ui/parts/Parts.kt` `Section()`: optional collapse.
- `ui/OpenPlace.kt`, `ChatSession` route handling for `menu_visibility`.
- `Nav.kt`: no new Screen is needed if the list lives inside Settings. (If a screen
  is preferred, append it last, as the file says.)

### Backend

- `backend/jarvis_quick.py`: `menu_visibility` intent (only if the owner says yes to
  voice). `tools/gen_sayable_cases.py` note as in section 6.
- `docs/JARVIS-API.md` section 108 (only for the route field).
- `docs/ARCHITECTURE.md` section 8, "One-sided on purpose": the tray is left alone in v1.

---

## 12. Owner's questions

Kept short, recommendation first.

**Q1. Should hiding be the same on the phone and the PC?**
- **Per device** (recommended): each remembers its own; asking Jarvis changes the
  devices that hear it.
- Shared: one setting for both. More work (a new route, updates between devices).

**Q2. Where should "Show or hide menus" live in Settings?**
- **Near the top, in Everyday** (recommended): easy to find when something is missing.
- In Rare, near the bottom.

**Q3. Should "hide the Finance menu" be on the 8-sentence "what can I say" list?**
- **No, keep it in the menu's own help line** (recommended): the list is full.
- Yes, replacing the weakest sentence.

**Q4. The system-tray menu (by the clock): tidy it too?**
- **Leave it alone for now** (recommended): it is the safety exit.
- Let me hide the extras (Faces, widget, Live and so on).

---

## 13. Feature audit checklist (to run after building, without being asked)

1. **Bugs:** hidden tab with focus, deep link to hidden target, empty storage,
   stale ids, collapsed section with a warning inside, rail count folding.
2. **Both apps:** desktop and phone each get the list, collapse and the route
   handling; tray left out in v1 (written in ARCHITECTURE section 8).
   `tools/check_parity.py` clean.
3. **Fit:** no card (nothing acts); same wording pattern as other settings; no
   clash with the Advanced switch, "Hide memory lists and chat history" (privacy),
   or `#more-options`; docs updated (`JARVIS-API` 108 if used, `BUILD-QUEUE`).
4. **Safety:** the never-hide test passes; a hidden menu never hides an approval
   or a stale-link warning; crisis text is unaffected.

---

## 14. Turned down / later

- **Shared across devices:** later, if the owner wants one layout everywhere.
- **Hiding tray items:** later (v2, section 9).
- **Reordering menus by drag:** not asked for; later.
- **Hiding a menu turns the feature off:** turned down (owner: hiding only tidies).
- **A card or Windows Hello to hide or show:** turned down; it only changes layout.
- **Hiding safety areas:** never (section 5).
- **Per-setting (single switch) hiding inside a card:** later; v1 works at card and
  plate level.
- **Auto-hiding menus never used:** turned down; the app does not guess.

---

## 15. Not verified

- Every line number and element id above comes from a read-only survey on
  2026-09-30 and is not re-checked here beyond `brain.html`'s tab ids, `Nav.kt`'s
  `Screen` enum, `settings.html`'s jump list and `jarvis_quick.py`'s
  `_OPEN_SETTINGS`.
- The current length of `jarvis_sayable.SENTENCES` was not counted; the limit is
  from `test_sayable.py` (5 to 8).
- Whether `tools/check_parity.py` treats a route *header field* as a route was not
  checked.
- Nothing was run on Windows, on Android, in Playwright or in CI. All Kotlin and
  Rust would be checked only by CI (see CLAUDE.md, "How the Android apps get built").
- Which existing card ids in `SECTIONS` map to the rows in 3a was not matched one
  by one; that is the first build step.
- JARVIS-API section 108 was reserved by the owner's instruction; whether a
  neighbouring number is already taken was not re-checked.
