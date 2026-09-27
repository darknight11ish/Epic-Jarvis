# Desktop JavaScript bug audit, 2026-09-27

Scope: the windows of the Tauri desktop app, meaning the JavaScript and HTML in
`jarvis-desktop/src`. The Rust was read only where a window's behaviour depends
on it. I looked hardest at the newest code, which has never had a bug audit:

- the floating face (`floating.html`, `floating.js`) and how it drives `faces.html`;
- "open <a settings section>" by voice or chat (`main.js` `openSettingsFromRoute`,
  `settings.js` `goToPlace`);
- "When to suggest the bigger model" (the two new switches in Settings, Second
  graphics card);
- the Floating face switch in Settings, and the tray and hotkey from the page's side.

After that I did a lighter pass over the rest of `src/`. Nothing was changed.
This is an audit only.

## In plain words (for the owner)

1. **"Open web search" (and every "open <a settings section>") does nothing on
   the PC.** Jarvis answers "Opening web search in Settings.", but the Settings
   window never opens. The page code is right. The Rust part in the middle drops
   the one field that says which section to open before the page sees it. The
   phone is not affected. The tests missed it because they skip that Rust part.
2. **The same Rust filter hides another line.** The small line "Done - answered
   on this PC without the AI model." under a timer or reminder answer has never
   appeared in the real desktop app since it was added on 2026-09-25. Same cause
   as item 1.
3. **The Floating face text in Settings gives the wrong key.** It says
   Alt+Shift+F brings up the Jarvis bar. Alt+Shift+F shows or hides the floating
   face. The Jarvis bar is Alt+Space.
4. **The Floating face switch can show the wrong state.** It is read once, when
   Settings opens. If you then turn the face on or off from the tray or with
   Alt+Shift+F, the switch in Settings still shows the old state.
5. **Keyboard users lose their place in Second graphics card.** After you press
   Space on any switch there, including the two new "suggest" switches, the
   keyboard focus jumps back to the top of the page. The code meant to keep the
   focus in place never gets a chance to run. I reproduced this in the test
   browser.
6. **A description is wrong again.** The floating face window can read the
   whole approval queue, including an email's full text. Its capability
   description says it never reads "the approval's own text". Nothing is shown
   or leaked. The window displays only the face. But this is the same kind of
   mismatch as #6 in the 2026-09-26 audit.

What I checked and found fine: the floating face's message passing and dragging,
`goToPlace` for every desktop section (including the original "Starting Jarvis
for you" case), both new "suggest" switches' requests and refusals, and the
shortcut list's new seventh action. The details are at the end.

## The table

| # | Severity | Where | One-line bug | Fix size |
|---|---|---|---|---|
| 1 | Medium | `main.js:973-982`, `commands.rs:1784-1843`, `commands.rs:2071-2081` | `open_settings` is removed by the Rust route-line filter, so "open <a settings section>" never opens Settings in the real app | XS |
| 2 | Low | `answer-memory.js:226`, `commands.rs:1784-1843` | `quick` is removed by the same filter, so the "Done - answered on this PC without the AI model." line never shows in the real app | XS |
| 3 | Low | `settings.html:512-519` | The Floating face help text says Alt+Shift+F brings up the Jarvis bar; that key toggles the floating face | XS |
| 4 | Low | `settings.js:702-725` | The Floating face switch is read once on load and never updated after a tray or hotkey toggle | XS |
| 5 | Low (keyboard/a11y) | `settings.js:1902-1920`, `settings.js:1979-1993`, `settings.js:2081-2088`, `settings.js:1836-1843` | Pressing a Second graphics card switch drops keyboard focus to the page body; the focus-restore code never fires (reproduced) | S |
| 6 | Low | `capabilities/floating.json`, `permissions/surfaces.toml:14-30`, `jarvis-link.js:1156-1197` | The floating window reads the full approval queue, but its capability description says it never reads an approval's text | XS |

Severity is how much harm the bug can do. Confidence is given with each finding.

## Detailed findings

### 1. "Open <a settings section>" never opens Settings in the real app

**Severity:** medium. The feature is completely dead on the desktop, and the
spoken answer says it happened ("Opening web search in Settings."). Nothing
unsafe happens. **Confidence:** high, from reading all three pieces.

The chain, step by step:

1. The backend puts the section id in `X-Jarvis-Route`
   (`backend/jarvis_quick.py` `route_fields`):
   `out["open_settings"] = res.open_settings`.
2. In the real app, the page never sees that header. `stream_chat` in Rust reads
   it and sends the page a filtered copy (`commands.rs:2071-2081`):
   ```rust
   if let Some(route) = response
       .headers()
       .get("X-Jarvis-Route")
       .and_then(|v| v.to_str().ok())
       .and_then(route_line_from_header)
   ```
3. `route_line_from_header` (`commands.rs:1784-1843`) is an allow-list. It copies
   `lane`, `where`, `gate`, `second_card`, `injected_facts`, `injected_sensitive`,
   `temporary`, `remember_off`, `memory_ids` and `turn_id`, and nothing else:
   ```rust
   for key in ["lane", "where", "gate", "second_card"] {
   ```
   `open_settings` is not on the list. `grep -rn open_settings
   jarvis-desktop/src-tauri` finds nothing at all.
4. So in `main.js:973-975`:
   ```js
   function openSettingsFromRoute(route) {
     const place = route && typeof route.open_settings === "string" ? route.open_settings : "";
     if (!place) return;
   ```
   `place` is always empty. Nothing is written for Settings, and
   `open_fix_place` is never called.

The only transport where this works is `streamViaFetch` (`main.js:2463-2465`),
which parses the raw header. That path runs only in browser preview, never in
the app.

Why no test caught it:
- No desktop test covers `open_settings` (`grep -ln
  "open_settings\|openSettingsFromRoute\|goToPlace" tests/*.mjs` finds nothing).
- The harness feeds the page route lines directly, skipping the Rust filter.
- `docs/JARVIS-API.md` section 58.1 says "no new Rust" was needed. That is how
  the filter was missed.

The page half works. I loaded `settings.html` in the harness with section ids
left under `jarvis.settings.place`, and each scrolled into view and took focus
(see "Areas read and found fine").

Smallest fix: in `route_line_from_header`, pass `open_settings` through when it
is a short string made only of `[a-z0-9-]`. Add a Rust test beside the existing
route-line tests (`commands.rs:5680-5850`). A harness test that goes through the
real filter's shape would also have caught finding 2.

### 2. The "Done - answered on this PC without the AI model." line never shows

**Severity:** low. It is a reassurance line, and its absence misleads nobody.
**Confidence:** high, same evidence as finding 1.

- The page shows the line only when the route has `quick`
  (`answer-memory.js:226`):
  `if (a.route && typeof a.route.quick === "string" && a.route.quick) lines.push(DONE_LINE);`
- `route_line_from_header` never passes `quick` (the allow-list is quoted in
  finding 1). Rust reads `quick` only for itself, in `quick_intent_from_route`,
  for "open a chat" (`commands.rs:1856-1859`, `2096-2115`). It never sends it to
  the page.
- `git log -S '"quick"' -- jarvis-desktop/src-tauri/src/commands.rs` shows
  `quick` first appeared in `commands.rs` with the floating-face commit
  (a06b7ad4), and only for Rust's own use. The Done line itself dates from
  8f8c31f6 (2026-09-25). So it has never shown in the real app.
- `tests/coming-up.mjs:598-603` passes because it hands the page a raw route
  line with `quick: "timer_set"`, a line the real Rust would never send.
- The phone shows the line correctly (`ChatSession.kt:634`), so the two apps
  disagree here.

Smallest fix: the same one-line change as finding 1. Pass `quick` through as a
short plain string.

### 3. The Floating face help text names the wrong key

**Severity:** low. It is wrong instructions for a beginner, and nothing breaks.
**Confidence:** high.

`settings.html:515-519`:
```html
A small window, always on top, that shows only Jarvis's face -
no text box. Drag it anywhere. Say "open a chat" (or press
Alt+Shift+F, or use Shortcuts below to change that) to bring
up the real Jarvis bar.
```
`hotkeys.rs` binds Alt+Shift+F to `toggle_floating`, "Show or hide the floating
face". The Jarvis bar is `toggle_quickbar`, `Alt+Space`. Pressing Alt+Shift+F as
the text says hides the face and opens no bar.

Smallest fix: reword it. For example: 'Say "open a chat", or press Alt+Space, to
bring up the Jarvis bar. Alt+Shift+F shows or hides this face.' Better still,
fill in the key names from `get_hotkeys`, because the text is hard-coded and goes
stale if the owner rebinds either key.

### 4. The Floating face switch goes stale after a tray or hotkey toggle

**Severity:** low. **Confidence:** high, checked by reading. I did not run it,
because it needs the real tray.

- `settings.js:702-711`: `paintFloating()` reads `get_floating` once, when the
  module loads. Nothing calls it again: no `visibilitychange`, no `focus`, no
  event. Compare `paintShared()` just above it (`settings.js:693-695`), which
  repaints on `visibilitychange`.
- `windows::toggle_floating` (tray and Alt+Shift+F) and the window's own
  close-request handler change `FloatingPrefs.enabled` but emit no event
  (`windows.rs:1125-1135`, and `attach_floating_listeners`).
- So with Settings open, pressing Alt+Shift+F leaves the switch showing the old
  state. Clicking it then sends the value the owner meant to change *to*, and
  that value may already be true. The first click can look like it did nothing.

Smallest fix: repaint on `visibilitychange` and `focus` like `paintShared`, or
emit a small `floating-changed` event from `set_floating` and `toggle_floating`
and listen for it.

### 5. Keyboard focus is lost after pressing any Second graphics card switch

**Severity:** low (keyboard and screen-reader use). **Confidence:** high,
reproduced.

Each toggle disables its own checkbox before sending, and then the section is
redrawn:
- `scSuggestToggle` (new): `input.disabled = true;` (`settings.js:1920`), then
  `await loadSecondCard()`.
- `scToggle` (`settings.js:2088`) and `scCombinedToggle` (`settings.js:1843`) do
  the same.

The redraw tries to put focus back (`settings.js:1902-1907` for the suggest rows,
`1979-1984` and `1988-1993` for the others):
```js
const focused = document.activeElement && document.activeElement.id;
sc.suggestSignals.replaceChildren(...suggest.signals.map(scSuggestRow));
if (focused && focused.startsWith("sc-suggest-")) {
```
But in Chromium, which WebView2 is built on, disabling the focused element moves
focus to `<body>` at once. By the time the redraw looks, `activeElement.id` is
empty, and the restore never runs.

Reproduction (throwaway harness script, now deleted). I opened `settings.html`
with `SECOND_CARD.capable_off`, focused `#sc-suggest-struggle` and pressed Space:
```
suggest: during BODY after BODY
master after BODY
```
The same happened for `#sc-switch-master`. The toggle itself works;
`tests/second-card.mjs` passes in full.

Smallest fix: note the focused id in each toggle before setting `disabled`, and
refocus that id after `loadSecondCard()`. Or skip `disabled` and rely on the
existing `scBusy` guard.

### 6. The floating window can read the whole approval queue; its description says it cannot

**Severity:** low. The page is this app's own bundled code and shows only the
face, so nothing is displayed or leaked. **Confidence:** high about what the
window holds. This is the same kind of mismatch as #6 in the 2026-09-26 audit.

- `capabilities/floating.json` grants `jarvis-link` and says the window needs
  "link/approval count, for which face state to show - never the approval's own
  text".
- The `jarvis-link` set (`permissions/surfaces.toml:14-30`) includes
  `allow-get-pending-approvals`.
- `floating.js:69` calls `startLink()`. `jarvis-link.js` `start()` then calls
  `get_pending_approvals` (`jarvis-link.js:1185-1197`) and listens to
  `approvals-changed` (`jarvis-link.js:1156-1164`). Every row arrives in full,
  including `detail`, which for an email is its whole text.
- The face frame is same-origin with no `sandbox` attribute (`floating.html:59-65`),
  so `faces.html` can reach `window.parent.__TAURI__` and use this window's
  grants. The claim in `floating.html:11-24` that the face "never holds a Tauri
  permission of its own" is true only in name. The frame can use the window's.
  In the harness, `f.contentWindow.parent.__TAURI__` was an object. The harness
  also injects the bridge into every frame, so this proves same-origin reach,
  not what real Tauri injects.

The floating window is not behind App lock (by design, `windows.rs:1015-1022`).
But it only holds this data in memory. It never shows it.

Smallest fix, pick one:
- Correct the description.
- Give `floating.js` a smaller read. The face needs only `get_link_state`, which
  already carries the `approvals` count `surfaceState` uses. So `floating.js`
  could call `get_link_state` and listen to the link event itself, instead of
  `start()`, under a new link-only permission set.
- Add `sandbox="allow-scripts allow-same-origin"`. That alone does not stop a
  same-origin frame reaching its parent, so it is not enough on its own.

## Possible, not verified

- **The floating face may keep drawing while hidden.** Unlike the widget, which
  empties its face frame's `src` whenever the face is not shown
  (`widget.js:401`), `floating.html` keeps `faces.html` loaded, and
  `hide_floating` only hides the window. Whether WebView2 pauses
  `requestAnimationFrame` in a hidden Tauri window depends on whether wry marks
  the webview invisible on hide. I could not check that here. Test on the PC:
  turn the face on and then off, and watch GPU use in Task Manager.
- **Opening a phone-only section from the desktop.** "Open smartwatch
  notifications" matches `watch-notify` (`app="phone"` in
  `jarvis_settings_registry.py`), and the backend answers the same sentence to
  both apps. On the desktop, `goToPlace` finds no `#watch-notify` and just
  returns. Once finding 1 is fixed, Settings would open at the top after
  "Opening smartwatch notifications in Settings." `JARVIS-API.md` 58.1 already
  admits the backend cannot tell the apps apart, so this is documented, not new.
- **The HUD's lane buttons put a server string into an attribute without
  escaping.** `jarvis_hud.html:1933` writes `data-lane="${l.id}"`, where `l.id`
  comes from the HUD server's `status.lanes`. The label next to it goes through
  `apprEscape`. The source is the owner's own `jarvis_hud.py`, so this is only a
  hardening point, not a reachable injection.

## Areas read and found fine

- **The floating face's messages** (`floating.js`). They copy `widget.js`
  `postFace`/`readFaceAppearance` exactly: the target origin is
  `location.origin`, and the frame checks `event.source === window.parent` and
  the origin (`faces.html:5193`). A state id it does not know is ignored. The
  first post, to a frame that has not loaded yet, is harmless: `onLink` posts at
  once and the frame's `load` posts again. It never calls `get_appearance` from
  inside the `appearance-changed` listener, so there is no loop. In the harness,
  `floating.html` loads with no console errors, and the frame reports
  `data-hud-face="ready"`.
- **Dragging.** `#face-frame` has `pointer-events: none`, so a click at the
  window's centre lands on `#drag`, which carries `data-tauri-drag-region`.
  `document.elementFromPoint(100,100).id` was `"drag"` in the harness.
  `floating.json` grants `core:window:allow-start-dragging`.
- **`goToPlace` after being made general** (`settings.js:746-781`). All 25
  desktop ids in `jarvis_settings_registry.SECTIONS` exist exactly once in
  `settings.html` (checked with grep). I ran 13 of them through the harness
  (start-jarvis, web-search, second-card, more-options, voice, about,
  backend-supports, updates, tool-updates, connection, backup, big-model,
  hardware). Each one scrolled into view and took focus. `about` and
  `backend-supports` sit near the page bottom, so they land lower on the screen,
  as far as the page can scroll. The original case still
  works: `start-jarvis` opens "More options" and focuses `#supervise`, and
  `tests/plain-errors.mjs` passes in full. `more-options` itself works, because
  `closest("details")` includes the element itself. A place is taken once and
  must be fresh (60 s). A missing id returns quietly. Reads and writes to
  `localStorage` are wrapped in `try`.
- **The "suggest" switches** (`settings.js:1874-1936`). The rows are built with
  `textContent` only. They send one request per tap, raise no card either way
  (as decided), are held on a stale link in Rust, go back to the PC's value after
  a refusal, and hide on an older backend. All of this is covered and passing in
  `tests/second-card.mjs`.
- **Shortcuts.** `tests/hotkeys.mjs` passes with the seventh action
  (`toggle_floating`).
- **General sweep.** Every `innerHTML` in `main.js`, `deep.js` and `widget.js`
  goes through the escape-first markdown renderer or `escapeHtml`. The
  `localStorage` writes are the theme, the zoom, the settings place and the
  voice-training time. The HUD's token copy is written only with
  `persist !== false`, and the desktop shell passes `false` and calls `forget()`
  first (`lib.rs:346-349`). `tool-updates-settings.js` builds everything with
  `textContent`, and its polling stops when it should.
- **`open_fix_place`** accepts only `"settings"` and `"brain"`, and
  `show_settings` goes through App lock (`windows.rs:399-404`). So once
  finding 1 is fixed, a spoken "open security" on a locked PC still asks for
  Windows Hello first.
