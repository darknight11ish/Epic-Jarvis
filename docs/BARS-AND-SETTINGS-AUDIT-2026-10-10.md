# The bars and the settings door: an audit, and what changed (2026-10-10)

> **Where every word here comes from.** Written inside
> `.dsh-scratch/bars-ux`, branch `feat/bars-toggle-and-settings`, off
> `origin/main` at `0aa6150d`. Every "what it does today" claim names the file
> and line it was read at, on that commit. Nothing here is remembered or
> guessed.
>
> This page answers the owner's four requests of 2026-10-10, in his own words:
>
> 1. *"open jarvis bar in the main desktop jarvis program should also hide it
>    if it is clicked again after it pops up"*
> 2. *"any jarvis shortcut bar should be able to be hidden with a button on
>    the bar itself"*
> 3. *"audit for this"*
> 4. *"i should be able to access settings on the desktop program easily too,
>    there should be a settings symbol button"*
> 5. *"can it control parts of my pc like if i ask open notion, or open
>    settings, or open jarvis settings. it should be able to do all of that."*

---

## 1. The audit: every bar, what opens it, and whether it toggles

| Bar / window | What it is in code | What opens it | Toggles or only shows? | Hide/close control on the bar itself |
|---|---|---|---|---|
| **Jarvis bar** (a.k.a. the command palette / spotlight) | window label `quickbar`, page `src/index.html`, `src-tauri/src/windows.rs:303` `show_quickbar_unlocked` | `Alt+Space` (`hotkeys.rs:59-63`, action `toggle_quickbar`); the tray menu's Show/Hide row (`tray.rs:1518`); left-clicking the tray icon (`tray.rs:1653`); "open the Jarvis bar" said out loud (`jarvis_quick.py:3092` `_OPEN_CHAT` → `commands.rs:2307` `show_quickbar`) | **Hotkey: YES, toggles** — `lib.rs:1310` calls `look::toggle_bar_with_look` → `windows.rs:379` `toggle_quickbar`. **Tray menu row: YES, toggles** (`tray.rs:1518`). **Tray icon left click: NO — only showed** (`tray.rs:1661` called `show_quickbar`). **Voice "open the Jarvis bar": only shows** (`commands.rs:2315`) | **NONE.** The bar has mic, Live, Watch, temporary, pin and `↵` (`index.html:118-231`) and no × or Close. The ways out are Esc (`main.js:4902` `dismiss`), `Alt+Space` again, losing focus (`windows.rs:224-233`), or the tray |
| **HUD** | window label `hud`, page `jarvis_hud.html` (the backend's own page, vendored) | The tray's "Show HUD Window" and its approvals row (`tray.rs`), `Alt+…`-less: `show_hud`/`toggle_hud` (`windows.rs:720-778`), and the `hud` window is built at startup (`lib.rs:1439`) | **`toggle_hud` (windows.rs:755) toggles**, but the tray rows call `show_hud` on purpose (`windows.rs:720-724`: "a toggle there would hide the window for anyone who clicked while it was already open behind something else") | It is the one window with a real title bar (`windows.rs:88`), so the OS × is the hide control; `CloseRequested` hides rather than destroys (`windows.rs:103-110`) |
| **Desktop widget** | window label `widget`, page `src/widget.html` | `Alt+Shift+W` (`hotkeys.rs:93-97`), the tray's row (`tray.rs:1524`) | **Toggles** (`windows.rs:1021` `toggle_widget`) | **YES.** `Escape` calls `hide_widget` (`widget.js:1715-1718`), and the widget's own permission set carries `allow-hide-widget` for exactly that (`surfaces.toml:359-361`) |
| **Floating face** | window label `floating`, page `src/floating.html` | `Alt+Shift+F` (`hotkeys.rs:110-116`), the tray's row (`tray.rs:1530`) | **Toggles** (`windows.rs:1286` `toggle_floating`) | **NONE, by design.** `floating.html:9` says so: "No text, no buttons, no title bar", and `capabilities/floating.json` says "this window has no button to act with at all". The whole window is a drag handle (`floating.html:70`) |
| **Settings window** | window label `settings`, page `src/settings.html` | The tray's **Settings and help…** (`tray.rs:359`, `tray.rs:1609-1610`); every error's fix button in the bar and the Brain (`main.js:1444`, `1446`, `1464`; `brain.js:13443`); "open \<a settings section\>" said out loud (`jarvis_quick.py:1048-1071` → `open_settings` on `X-Jarvis-Route` → `main.js:1598` `openSettingsFromRoute`) | n/a — it is shown and focused, and it is **not** something the owner wants toggled off | It is an ordinary decorated window, so the OS × closes it |
| **Any quickbar besides the above** | — | — | — | **There is none.** The eleven webviews are `index.html` (the bar), `jarvis_hud.html`, `widget.html`, `floating.html`, `settings.html`, `brain.html`, `faces.html`, `features.html`, `onboarding.html`, `live-badge.html`, `watch-badge.html` (`capabilities/*.json`). The last two are badges, not bars |

### What already worked

* **The `Alt+Space` shortcut already toggled** (`windows.rs:379`), and so did
  the tray's own Show/Hide row.
* **The widget already had a hide control** — Escape, with its own ACL grant
  behind it.
* **The HUD already had a hide control** — its title bar's ×.
* **Every bar that is toggled by a shortcut already toggles.**
* **Settings already had four in-app doors** (the tray, and the error-fix
  buttons in the bar and the Brain).

### What did not

1. **The tray icon's left click only showed the bar.** Clicking the
   notification-area icon while the bar was already up did nothing visible —
   the exact complaint of request 1, and the one route out of four that did not
   toggle. `tray.rs:1661`.
2. **No bar carried a visible hide control.** The Jarvis bar's only ways out
   were a key, a menu, or losing focus. Request 2.
3. **No settings symbol anywhere.** The owner could not see one; request 4.
4. **The widget's own offline card was dead.** `widget.js` invokes
   `open_fix_place` (its "Show me where" button), and `capabilities/widget.json`
   never granted it — so every tap was refused at the ACL, silently, which is
   precisely the failure `tools/check_command_acl.py` exists to catch for
   *registered* commands. This is the same class of bug as the 2026-09-27 bug
   audit's finding #2 (`crash_notes`, `find_python`).
5. **"open Notion", "open settings", "open Jarvis settings" did nothing.**
   There was no code path anywhere in the repository that started a program or
   a Windows panel. `jarvis_media.py:45` says in its own words that media
   control never "open[s] an app"; `jarvis_bakeoff.py:971`'s `os.startfile` is
   a benchmark tool, not a feature.

---

## 2. The `.visible(false)` finding, and what it really says

The pairing investigation recorded that the Settings window is built
`.visible(false)` and that "an outer driver cannot reveal it". Both halves are
in the code, and they are two different facts:

* **`windows.rs:472`** builds the window `.visible(false)`. That is deliberate
  and it is about a **flash**: `window_memory.rs:restore` puts the window back
  where the owner left it *before* it is shown, so it does not appear centred
  for one frame and then jump (`windows.rs:470-472`).
* **`windows.rs:449-490`** `show_settings_unlocked` immediately shows it,
  unminimises it and focuses it — `.visible(false)` included. **So the window
  is not un-revealable from inside the app at all.** Every in-app door works:
  the tray (verified by reading `tray.rs:1609-1610`), and `open_fix_place` from
  a page.
* What actually bit the pairing work was a **history** bug, not a visibility
  one: the `open_settings` field was being **filtered out** of the route line
  before it reached the page, so the page never learned it should open
  Settings. `docs/BUG-AUDIT-2026-09-27-desktop-rust.md` finding #1 says it
  exactly: *"the Settings window never opens. The PC's backend sends the right
  signal, and the page knows what to do with it. But the Rust in between passes
  on only a fixed list of fields, and this new field is not on that list."*
  The fix landed — `commands.rs:1940` now carries `open_settings` — and this
  work had to add four more names to that same list
  (`commands.rs:1969-1989`), which is the same trap for a fourth time.

**Conclusion, plainly: it is about driving it from outside, not about the
window.** The `.visible(false)` is a one-frame anti-flash measure that the
same function immediately undoes. The gear on the bar is therefore an in-app
door to a window that opens perfectly well — and that is the only kind of door
this feature used.

---

## 3. What changed

### 3.1 The tray icon toggles (request 1)

* `tray.rs` `handle_tray_icon_event` now calls `windows::toggle_quickbar`
  instead of `windows::show_quickbar`.
* `windows.rs` gained `focus_quickbar_input`, and `toggle_quickbar` calls it on
  the way up. Before this, **only** the hotkey path placed the caret in the
  bar's input (`lib.rs` emitted `FOCUS_INPUT` itself); the tray icon and the
  tray menu row did not, so a bar summoned from the notification area was on
  screen and not ready to type in. Now every route gets the same caret, and
  `lib.rs`'s and `tray.rs`'s duplicate emits are gone.
* "open the Jarvis bar" said out loud still only shows, on purpose: it is the
  owner asking for the bar, and hiding it because he asked for it twice would
  be wrong.

### 3.2 A hide button on the bar (request 2)

`index.html` gained `#hide-bar`, an × beside the pin, calling the
**already-granted** `hide_quickbar` — the same command `Esc` runs
(`main.js:4902`), which drops the pin in Rust (`windows.rs:363-364`) so the
next summon starts clean. No new command, no new grant.

The widget (Escape) and the HUD (its title bar) already had one; the floating
face deliberately still has none — see §5.

### 3.3 A settings gear (request 4)

* **The Jarvis bar**: `#open-settings`, a gear beside the pin, calling
  `open_fix_place { place: "settings" }` — the door this window's own error-fix
  buttons already used. The quickbar already holds `allow-open-fix-place`
  (`surfaces.toml:284`).
* **The widget**: `#btn-settings`, a gear on its compact bar, the same call —
  and `surfaces.toml`'s `widget-surface` and `capabilities/widget.json` were
  given `open-fix-place`, which **also fixes the widget's dead offline card**
  (§1 finding 4).
* **The HUD and the floating face deliberately got none** — see §5. **The HUD
  half was reversed by the owner on 2026-10-10 (§10.2): the HUD now has the
  same gear, added by the shell's bootstrap, and `capabilities/hud.json` was
  granted `open-fix-place` for it. The floating face still has none.**

### 3.4 Opening apps and panels from the owner's own words (request 5)

New module **`backend/jarvis_open.py`** (shipped whole, no patch), called by
`jarvis_quick.py`'s existing fast path. `jarvis_quick.py` already answered
"pause the music" and "open a chat" without the model and without a card; this
is the same shape for the same reason, and it follows `jarvis_media.py`
exactly: **no card, no route of its own, no model tool, and it never imports
`jarvis_gate` at all**, so there is no action name to give a tier to and
nothing here can be made to ask.

What each phrase does:

> **Superseded on 2026-10-10 for the "settings" rows.** The owner answered
> question 1 in §7 by flipping the default: a bare "open settings" is
> **Jarvis's** own window now, and only "open Windows settings" reaches
> `ms-settings:`. See **§10.1** for the answer as built, the new wording, and
> the bug found on the way. The rest of this table is unchanged.

| The owner says | Kind | What happens |
|---|---|---|
| "open Notion" | `app` | Resolved by the desktop **against this PC's own Start menu** (`open_app.rs`), not by the backend and not by the model |
| "open notepad", "open calculator", "open task manager", "open file explorer", "open control panel" | `app` (built) / `other` | Windows' own accessories and the fixed shell commands; the backend names the program, so no lookup is needed |
| "open settings", "open windows settings", "open my settings" | `panel` | Windows' own Settings (`ms-settings:`), with a note saying so and naming the other door |
| "open display settings", "open sound", "open privacy" … | `panel` | The named Windows panel, from a fixed list of `ms-settings:` addresses |
| "open Jarvis settings", "open jarvis preferences" | `jarvis` | Jarvis's own Settings window, at the top |
| "open web search", "open voice settings", "open backups" … | `jarvis` | Jarvis's own Settings, **at that section** — these are resolved by the settings registry that already owns them (`jarvis_settings_registry.py`), first by `_settings_open` and then, as a backstop, by `jarvis_open`'s own guard |

**How "settings" is disambiguated, and why:**

* "**open Jarvis settings**" — only these explicit words (or one of the
  registry's own section names) open **Jarvis's** Settings.
* "**open settings**", "open Windows settings", "open my settings" — open
  **Windows** Settings. This is the plain reading of the owner's own sentence,
  and it is the one Windows itself calls "Settings".
* The answer **says which one it opened and how to ask for the other**: *"That
  is Windows' own Settings. Say \"open Jarvis settings\" for Jarvis's."* The
  same note appears for every word that is both a Windows panel and a Jarvis
  section (`security`, `sound`, `display`, `camera`, `backup`, …).
* Whatever the owner's words name that matches **nothing** is **not guessed
  at**: the desktop looks it up in this PC's real Start-menu shortcuts and, if
  it is not there, says so plainly — *"I could not find an app called X on
  this PC. Open it once from the Start menu, then ask me again."* There is no
  nearest match, and a name matching two different shortcuts is reported
  rather than picked between.

**Where the opening actually happens, and why:** in Rust, from
`X-Jarvis-Route` on the chat stream (`commands.rs open_app_from_route`, called
by `stream_chat`), exactly like "open a chat". Nothing crosses the IPC
boundary, so **no new Tauri command, no `build.rs` entry, no `surfaces.toml`
set, and no capability grant** was needed — and no page holds a permission to
start a program. The launcher is `ShellExecuteExW`, the same call this app
already uses to open a link in the owner's browser.

**Nothing private leaves the PC**, there is no public tunnel, the frontend is
still 11 webviews and not a framework, Acrylic is still over Mica, Material 3
Expressive is still rejected, and the faces are untouched.

### 3.5 One more thing the audit turned up

The registry's own `open_settings` matcher (`jarvis_quick._OPEN_SETTINGS`)
**compares the whole phrase**, so "open the backup settings" was never a
settings jump — it fell through to the model. `jarvis_open.py`'s section guard
now catches it, so "open the backup settings" lands on Jarvis's Backups card.
(`jarvis_open` deliberately does **not** claim the phrases `_settings_open`
already owns: "open web search" is still `settings_open` with the
`open_settings` field both apps have known since 2026-09-27. This was found by
`test_settings_registry.py` failing when it was tried the other way round.)

---

## 4. Tests and gates, with real results

| Gate | Result |
|---|---|
| `cargo fmt --check` | **clean** (0) |
| `cargo clippy --all-targets -- -D warnings` | **clean** (0) |
| `cargo check --offline --all-targets` | **clean**, no warnings |
| `cargo test --offline --lib` for the new module + route line | **8/8 `open_app` tests pass**, `the_route_line_carries_what_open_named` passes (731 other lib tests filtered out; `cargo test` in full OOMs this machine, as briefed) |
| `tools/check_command_acl.py` | **"359 commands, generate_handler! and build.rs agree."** (0) |
| `tools/check_invoke_grants.py` | **"320 command(s) invoked from 11 page(s); every one is granted"** (0) |
| `backend/test_jarvis_open.py` (new) | **79 passed, 0 failed** |
| `backend/test_settings_registry.py` | **125 passed, 0 failed** (2 assertions updated, see §6) |
| `backend/test_shipped_modules.py` | **601 passed, 0 failed** |
| `backend/test_base_matches_repo.py` | **13 passed, 0 failed** (it caught `jarvis_quick.py` and `jarvis_open.py` drifting from `jarvis-backend/`; both were copied over) |
| `jarvis-desktop/tests/bar-chrome.mjs` (new) | **13/13 pass** — no browser needed, so it runs in CI |
| Quick-path regression: `test_media`, `test_identity`, `test_pc_help`, `test_places`, `test_news`, `test_next_time`, `test_animal`, `test_menu_visibility`, `test_find_phone`, `test_lockdown`, `test_today`, `test_widgets`, `test_open_chat`, `test_quick_wins`, `test_feature_list`, `test_settings_rows` | **all 0 failed** |
| `scripts/apply-patches.ps1` pure ASCII | **0 non-ASCII bytes** |

**One pre-existing failure, not mine:** `cargo test --offline --lib` also runs
`commands::wiki_tests::only_a_real_jarvis_wiki_folder_is_opened`, which fails
in this sandbox with `Os { code: 5, kind: PermissionDenied }` because it
creates a temp folder and the sandbox denies it. It is untouched by this work
and fails the same way on unmodified `main`.

---

## 5. What was deliberately left alone, and why

* **The floating face has no hide button.** `floating.html:9` and
  `capabilities/floating.json` both state the design: the window is *only*
  Jarvis's face — "no text, no buttons, no title bar" — and the whole window is
  a drag handle. Adding a visible control there would be a new visual language
  on the one surface built to have none. It is hidden by `Alt+Shift+F`, by its
  tray row, or by asking out loud.
* **No settings gear on the HUD or the floating face.** **The HUD half was
  answered by the owner on 2026-10-10: it gets the gear — see §10.2, which
  supersedes this bullet for the HUD.** As written here, the HUD was the one
  surface where the design note was explicit that it holds "no approve, deny,
  memory-write, recording or settings command"
  (`capabilities/hud.json`), and it loads the backend's own vendored page,
  which is not ours to add chrome to — hence the gear is added by the shell's
  injected bootstrap and the capability's own sentence was corrected. The
  floating face is the same argument as above and **still has no gear**;
  the owner answered only for the HUD.
* **The HUD's and the widget's own toggle routes are unchanged.** The HUD's
  tray rows still deliberately `show` rather than toggle
  (`windows.rs:720-724`), because the reason written there is a good one.
* **`jarvis_media.py`, the faces, the themes and the eleven webviews** are
  untouched.
* **No new Tauri command.** There is none to add: both the gear and the × use
  commands this window already holds, and the app-launching half runs in Rust
  off the chat stream. This is why `build.rs`, `surfaces.toml` and the
  capability files needed no new command entry at all — the only ACL change is
  the widget being granted a set that already existed.
* **No `jarvis_gate` tier, no `[autonomy.tiers]` line and no route.** Following
  the music/video precedent, an action reached only from the owner's own words
  has no gate action to give a tier to, and the model has no tool for it.

---

## 6. What was updated rather than left

* `backend/jarvis_quick.py` — the fast path, the `Result` fields, and
  `route_fields`. Its grammar check moved **after** the settings block: the
  first attempt put it before, and `test_settings_registry.py` failed on "open
  web search" (it became `open_app` instead of `settings_open`). That is a real
  regression the test caught, and the ordering comment now says why.
* `backend/test_settings_registry.py` — two assertions said "open the door" and
  "open the pod bay doors" must match **nothing**. They now match the app
  opener (`open_app`), which is correct: they are "open ..." sentences. The
  claim that suite actually makes — that they name no settings **section** — is
  checked instead, and the phrases are now asserted to be the app opener's.
* `scripts/apply-patches.ps1` (`$SHIPPED`) and `backend/_where.py`
  (`SHIPPED`) — `jarvis_open.py` added, in the same order, which is what
  `test_shipped_modules.py` checks.
* `jarvis-backend/jarvis_open.py` (new) and `jarvis-backend/jarvis_quick.py`
  (re-synced) — `test_base_matches_repo.py` requires the published base to be
  byte-identical to the repository's copy.
* `jarvis-desktop/src-tauri/src/commands.rs` — four names added to the
  route-line filter's allowlist; this is the exact place a field was silently
  dropped in 2026-09-27 (`docs/BUG-AUDIT-2026-09-27-desktop-rust.md` #1).

---

## 7. What the owner must decide

**Q1. Where should "open settings" land by default?**

Right now it opens **Windows** Settings, and the answer tells him how to ask
for Jarvis's.

* **Keep it: "open settings" = Windows Settings, "open Jarvis settings" =
  Jarvis** *(recommended — it is the plain reading of what the words say, and
  the answer always names the other door)*
* **Flip it: "open settings" = Jarvis settings, "open Windows settings" =
  Windows**
* **Ask every time: neither opens until he picks from two buttons** *(needs a
  new question UI in the bar, so it is the largest of the three)*

**Q2. Should the HUD get a settings gear too?**

The HUD is the window that holds today "no settings command" on purpose.

* **No — leave the HUD as it is** *(recommended: it is the one surface whose own
  permission file argues against holding one, and the tray's "Settings and
  help…" is two clicks away)*
* **Yes — add the same gear, and grant the HUD the navigation-only command**
* **Yes, but only if it is the same small gear as the bar's** *(identical to
  the option above in effect; listed so "make it look the same" is a real
  answer)*

---

## 8. The risk

* **"open Notion" depends on a Start-menu shortcut existing.** The index is
  this PC's two Start-menu folders, read once at startup
  (`open_app.rs::warm_up`). An app with no Start-menu entry cannot be found
  **by name** and the owner is told so. Nothing is guessed, so the failure is
  honest rather than wrong — but it is a real limit, and it has only been run
  against this sandbox's filesystem, never against the owner's installed apps.
* **A panel address that Windows refuses** (an edition without that page)
  surfaces as Windows' own error in plain words rather than a silent nothing —
  but which of the `ms-settings:` addresses exist on *his* build has not been
  checked from here.
* **The four new route-line names are the fourth time this exact filter has
  dropped a field.** There is a test for the new ones
  (`the_route_line_carries_what_open_named`), but the general hazard is
  unchanged: a future field added on the Python side and not in that list fails
  silently.
* **Nothing here has been run against the owner's running app.** No build, no
  restart and no window was opened: the Rust gates are compile-and-lint only,
  and the UI tests that would drive a real page need Playwright, which is not
  installed in this checkout. See §9.

---

## 9. What needs the owner's running app to verify

1. That the tray icon's second click really hides the bar (request 1) — the
   code path is proven by test, the on-screen behaviour is not.
2. That the gear and the × are **findable at a glance** on the bar, and that
   the × was not pressed by accident while typing.
3. That "open Notion" finds the real Notion on his PC, and that the first
   `ms-settings:` page opens on his Windows build.
4. That the widget's gear opens Settings (and that its offline card's buttons
   now work, which they never have).
5. The bar's own width with two more icon buttons on it: the row has
   `flex-wrap`, so it should reflow rather than clip, but the pixels have not
   been seen.

---

## 10. The owner's answers to §7 (2026-10-10), and what they changed

Both questions are now answered, and **this section supersedes §3.4's table,
§3.4's own "how settings is disambiguated" list, §3.5, and §5's second
bullet**. Where this section and those disagree, this one is what the code
does.

### 10.1 Q1 — the owner chose **"flip it"**

**A bare "open settings" now opens JARVIS's own Settings window, at the top**
(`kind: "jarvis"`, `open_place: ""`). It is no longer Windows Settings.

* **"open Windows settings"** — and "open the windows settings app" — is the
  words that reach **Windows' own Settings** (`ms-settings:`). It is now
  matched **explicitly**, by `jarvis_open._WINDOWS_SAID`, before the Windows
  panel list and long before the PC's Start-menu index, so a shortcut that
  happened to be called "Windows Settings" can never steal the phrase.
* **"open my settings"**, "open the settings app" and "open the settings
  screen" land on Jarvis's, the same as the bare phrase.
* **The answer says which one it opened and how to ask for the other**, on
  both readings:
  * bare "open settings" → *"Opening Jarvis settings on this PC."* plus the
    note *"That is Jarvis's own settings window. Say "open Windows
    settings" for Windows' own."*
  * "open Windows settings" → *"Opening Windows Settings on this PC."*, no
    note needed, because the owner named the one he wanted.
* **The disambiguation note for words that are both** (security, sound,
  camera, backup, display, …) is kept and was made **truthful after the
  flip**. It used to name the other reading as *"open Jarvis settings"*, which
  is now exactly what a bare "open settings" already does — the one thing the
  note must never do is send the owner to the phrase he just said. It now
  names the other reading as the **section jump**: *"That is Windows' own
  sound page. Say "open Jarvis settings, sound" for the one inside Jarvis."*
  The panel itself is unchanged: an ambiguous word still opens the **Windows**
  page by name, exactly as §3.4 said.
* The `Opened` note is no longer only about `settings`; it is what the answer
  carries whenever a phrase has two real readings.

**A bug this work found and fixed:** the kind-noun peel in `resolve` was
written with `re.sub` over a pattern that can match the empty string, so
"open the display settings app" was handed to the app index as a program
called "display settings" instead of reaching the Display page. The peel is
now a real match (`_without_kind_noun`) and runs **at most twice**, so a name
carrying two of those nouns still lands on its panel. `test_jarvis_open.py`
holds both cases.

### 10.2 Q2 — the owner chose **"yes, add the same gear"**

**The big HUD window now has a settings gear.** Where and what it calls:

* **Where:** on the HUD's own **stage bar**, immediately before the page's
  own "Telemetry" button — the bar that already carries the model and state
  chips. There is no title bar in the page itself (the OS draws the window's),
  so the stage bar is this window's chrome.
* **What it calls:** `open_fix_place { place: "settings" }` — **exactly** the
  command the Jarvis bar's gear and the widget's gear call. **No new Tauri
  command, no new Rust code.** It draws the **same gear glyph** and carries
  the **same "Jarvis settings" name for a screen reader**, so all three look
  and read alike.
* **Where the code lives:** `src-tauri/src/hud_bootstrap.js`, the shell script
  injected into the HUD before its own. It is **not** in `jarvis_hud.html`,
  which is vendored byte-identical from the backend folder and must stay that
  way (`bar-chrome.mjs` asserts the page has no `#hud-settings`). Adding it
  here is the same road the "Open the Jarvis bar" button already takes.
* **The capability change, deliberately named:** **`capabilities/hud.json`**
  now pulls in the **`open-fix-place`** set (`allow-open-fix-place`), and its
  own description was corrected — it used to say, in so many words, that this
  window holds "no … settings command". That set is navigation only: it opens
  or focuses Settings at a named place, changes no setting, approves nothing,
  and the app lock still applies to whatever it opens. It is the same grant
  the widget needed, for the same reason: **a visible control wired to a
  command its window does not hold fails silently**, which is exactly how the
  widget's offline card stayed dead. `permissions/surfaces.toml` records the
  same, beside the set.
* **The route-line allowlist did NOT need the field added.** The audit's §6
  warning is about the filter in `commands.rs::route_line_from_header`, which
  had silently dropped `open_settings` four times. This gear opens Settings by
  **calling a command**, not by reading a route line, so it never touches that
  filter. The filter's four `open_app*` names and `open_place`, added by this
  branch, already carry "open settings" → Jarvis's as well: after the flip the
  same names ride that line, with `open_app_kind: "jarvis"` and an **empty**
  `open_place` meaning "the top of the window". No name was added, and none
  was needed.
* **Not changed:** the floating face still has no gear and no hide button
  (§5's first (now merged) bullet) — the owner answered only for the HUD.

### 10.3 What the tests now hold

* `backend/test_jarvis_open.py` — bare "open settings" and "open my settings"
  are Jarvis's; "open Windows settings", "open windows settings" and "open the
  windows settings app" are `ms-settings:`; the note names the other door and
  **never** names the phrase the owner just said; ambiguous words still open
  the Windows page and name the section jump.
* `jarvis-desktop/tests/bar-chrome.mjs` — now **18 checks**, five of them new:
  the HUD's gear exists and is named, calls `open_fix_place`, sits on the stage
  bar, draws the shared glyph, and the window is really granted the set
  (`surfaces.toml` **and** `capabilities/hud.json`).
* `backend/jarvis_open.py`'s shipped twin `jarvis-backend/jarvis_open.py` is
  byte-identical (`test_base_matches_repo.py`).

### 10.4 Still only the owner's running app can confirm

Adding to §9: that the gear is **findable at a glance** on the HUD's stage bar
at the window's real size, and that tapping it opens Settings at the top. No
build, no restart and no window was opened by this work.

---

## 11. The rebase onto `main` (348ffbb2, 2026-10-10), and what CI found

`main` had moved 29 commits and `gh pr update-branch` refused the PR
("Cannot update PR branch due to conflicts"), so this was a real hand rebase in
`.dsh-scratch/bars-ux` (detached at the old tip, `8918fc97`, because the local
branch ref was stale at `02de7ac2`).

**Two conflicts, both resolved as a union — nothing dropped from either side:**

* **`jarvis-desktop/package.json`** — `test:ui`. `main` had added
  `galaxy-constellation`/`galaxy-button-engine`; this branch puts
  `bar-chrome.mjs` first. Kept both.
* **`jarvis-desktop/src-tauri/capabilities/hud.json`** — the window's
  `description`. `main`'s copy of that sentence is **truncated**: it reads
  "...mark on one answer, and hide it again.\" (two yes/no answers,
  `get_lock_flags`, ...)", with the clause that parenthetical explains missing
  and a stray `\"` left behind. The union restores the missing clause
  (`whether App lock and "Hide memory lists" are on`) and keeps this branch's
  `open-fix-place` paragraph and grant. The `hide_quickbar` wording from
  `main`'s 2026-10-09 HUD toggle is kept too — it is the same sentence both
  sides had rewritten.

**Two defects CI found after the push — both real, both fixed here:**

1. **`origin/main` does not compile with `--all-targets`.** `windows.rs`
   carried TWO `#[cfg(test)] mod tests` blocks — one from the floating
   click-through work (`parse_hit_mask`, `FloatingState`), one from the
   widget-clamp work (`clamp_into`) — so `cargo clippy --all-targets -- -D
   warnings` and `cargo check --offline --all-targets` both died with
   `error[E0428]: the name tests is defined multiple times`. It is `main`'s,
   not this branch's (this branch never touched a test module): main's own CI
   run for `348ffbb2` fails its `rust` job on exactly this. The two are merged
   into ONE module, every test from both sides kept verbatim. **Any other
   branch rebased onto this `main` inherits the same red gate.**
2. **`backend/test_screen_turn.py` failed — a regression this branch caused.**
   "start watching my screen" was being claimed by the new `open_app` matcher
   (it resolved to a program called "watching my"), because `jarvis_quick.py`
   tried `_open(s)` *before* `_watch(s)`. The watch session never started and
   no screen was ever read. `_open(s)` now runs **last** among the real
   matchers, so it can only claim a phrase no other feature already owns;
   `test_screen_turn.py` is back to **99 passed, 0 failed** and
   `test_jarvis_open.py` stays at **88 passed**.

`tools/check_literal_keys.py` also failed on this branch's new module: a
duplicate `"ms-settings:bluetooth"` key in `_PANEL_NAMES` (lines 570 and 589,
identical values — CPython kept the last and said nothing). The duplicate is
removed, in `backend/jarvis_open.py` and its byte-identical twin.

**Fresh evidence after the rebase and the fixes above** (§4's numbers are from
before the rebase):

| Gate | Result |
|---|---|
| `cargo fmt --check` | **clean** (0) |
| `cargo clippy --all-targets -- -D warnings` | **clean** (0) |
| `cargo check --offline --all-targets` | **clean** (0) |
| `cargo test` | **not run** — it OOMs this machine, as briefed; `check --all-targets` type-checks the merged test module |
| `tools/check_stale_twins.py` (now on `main`) | **all 183 modules match**, line endings ignored (0) |
| `tools/check_command_acl.py` | **360 commands agree** (0) |
| `tools/check_invoke_grants.py` | **321 calls from 11 pages, every one granted** (0) |
| `tools/check_parity.py` | **No undecided drift** (0) |
| `tools/gen_menu_cases.py --check`, `gen_settings_cases.py --check` | **both match** (0) |
| `tools/check_claims.py` | **125 claims; every `built` holds, every `open` is open** (0) |
| `tools/check_literal_keys.py`, `check_event_names.py`, `check_media_csp.py`, `check_same_tick_paths.py`, `check_tutorial_places.py`, `check_vacuous_checks.py`, `gen_notices.py --check` | **all 0** |
| Backend: `test_jarvis_open` 88, `test_settings_registry` 125, `test_settings_rows` 21, `test_shipped_modules` 604, `test_base_matches_repo` 20, `test_claims` 45, `test_menu_visibility` 393, `test_screen_turn` 99, `test_patch_history` 24 | **0 failed in every one** |
| Desktop: `bar-chrome` **18 checks**, `hud-window`, `hud`, `security`, `csp`, `csp-inline`, `settings-catalogue` (**27 toggle rows**), `settings-search`, `settings-failures`, `a11y`, `ia`, `palette`, `widget-board`, `menu-visibility` | **all exit 0** |
| `faces.mjs` | **39 passed, 1 skipped** — no `glslangValidator` on this PC; the `backend` job runs that check |
| `scripts/apply-patches.ps1` pure ASCII | **0 non-ASCII bytes** of 280,351 |

No settings row was added or moved by this branch, so no `SETTINGS_ITEM_INDEX`
position and no `LimitsTest` pin moved: `test_settings_registry.py` still
recomputes the index from `SettingsScreen.kt`'s real `item(key = ...)` order and
matches it, and all four generated settings copies agree (27 toggle rows). The
one test pin this rebase did move is `tests/hud.mjs`'s exact permission list for
the HUD window, which now names `open-fix-place` — the gear the owner asked for.


