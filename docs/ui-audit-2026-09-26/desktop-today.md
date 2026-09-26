# Desktop app today: a visual inventory

Part of the cutting-edge UI audit. This is only about **how the desktop windows
look right now**. Ideas for what to change belong to the other reports. Where I
say "should", I mean "this is the gap a redesign would close".

Everything here was checked against the files in
`/home/user/Epic-Jarvis/jarvis-desktop/src`, and cited as `file:line`. I made
the screenshots from a **copy** of the app, never inside the repo.

## How the screenshots were made (and what they cannot show)

- I copied `jarvis-desktop/` (leaving out `src-tauri/target` and `node_modules`)
  to `scratchpad/ui-audit/desk-copy/`. I also copied the one contract file the
  test harness reads from `jarvis-client`. Then I ran `tests/shots.mjs default paper`
  there. The fresh shots are in `scratchpad/ui-audit/desk-copy/tests/shots/{default,paper}/`.
- The harness only covers the quickbar, the widget and the top of Settings. So I
  wrote two small extra scripts **inside the copy**: `tests/extra-shots.mjs` and
  `tests/answer-shot.mjs`. They produced Brain (every tab, all three themes),
  the whole Settings page, Faces, onboarding, the HUD, High Contrast versions and a
  real streamed answer. They are in `scratchpad/ui-audit/shots-extra/`.
- **Caveat 1, fonts.** The container has no Segoe UI. So every shot uses the
  Linux fallback font (DejaVu Sans). On Windows, the quickbar, widget and
  Settings will look a little tighter and more modern than these pictures.
  Chakra Petch and IBM Plex are bundled with the app (`src/fonts/`), so the
  Brain headings, HUD, Faces and onboarding do render in their real fonts here.
- **Caveat 2, data.** The harness stubs the backend with recorded payloads
  (`tests/uikit.mjs:1-10`). Layout and styling are real. The numbers are samples.
- **Two harness scenes are stale (worth knowing before anyone trusts the
  committed shots):**
  - `03-quickbar-answer` has always shown an **empty answer**. That includes the
    committed one from 2026-09-14. The scene fires a `__render` event
    (`tests/shots.mjs:40-44`), and nothing in `src/` or `tests/uikit.mjs`
    listens for it (I grepped for it). So the most-read surface in the product
    has never been in the screenshot set. My `answer-shot.mjs` streams the same
    markdown through the real chat path instead
    (`shots-extra/quickbar-answer-default.png`), and it renders well.
  - `02-quickbar-offline` looks identical to `01-quickbar-idle`. The window is
    only 220px tall, so the offline banner at the bottom gets cut off. At 620px
    the banner is there (`shots-extra/quickbar-offline-tall.png`).

## The windows, one by one

### 1. Quickbar, the "Jarvis bar" (`index.html`, `style.css`, `main.js`)

- **Layout:** a frameless, see-through bar about 750px wide. From left to right: a
  small reactor logo drawn in SVG (`index.html:50-74`), a large single text box,
  then a row with the route badge ("Local / model"), mic, hands-free, temporary chat,
  pin and send. Below it are panels that expand: the shortcut primer, the "waiting to
  be told" digest, an answer card, an approval card, and a footer with the
  service dots (Core / Ollama / LiteLLM) and an `Esc dismiss` hint.
- **Type:** `--font-ui` (Segoe UI Variable) for the text, and `--font-mono` for code,
  key caps, tags and the approval title (`style.css:1267-1275`).
- **Colour:** everything comes from `theme.css` tokens. Cyan is the accent, and green,
  amber and red carry meaning.
- **Icons:** hand-drawn inline SVG (8 `<svg>` in `index.html`). The icons have no
  text labels, only tooltips: "Hold to talk", "Listen for hey Jarvis", "Start a
  temporary chat", "Keep Jarvis open" (`index.html:123,149,168,183`). The
  hands-free icon is a plain target ⊙ and temporary chat is a ghost. A
  beginner cannot guess either one without hovering.
- **Motion:** the window slides and scales in (`shell-in` 180ms, `style.css:126,138`).
  Cards rise in (`card-in` 200ms, `:682,685`). A thin highlight sweeps along the top
  edge while an answer streams (`scan`, `:190-212`), and it is switched off under
  reduced motion (`:214-221`). The mic pulses and the reactor logo breathes. Four
  reduced-motion blocks exist (`style.css:214,319,548,1763`).
- **Answer card:** clean. Bold and italic come through, inline code gets a tinted
  chip, and code blocks sit on a black well with a cyan left edge. The status says
  "COMPLETE", with Copy / New conversation. This is the best-looking part of the bar
  (`shots-extra/quickbar-answer-default.png`).
- **Approval card:** a clear amber left bar, a shield icon, a "NEEDS YOUR OK" label,
  the cost line ("No undo · leaves this machine — there is no unsend"), and
  "Nothing runs until you decide." When a rush was detected, a red "Tier raised"
  box appears. It is unmissable and plain, as intended (`default/04`, `05`, `07`).
- **Empty / idle:** the shortcut primer lists every hotkey with key caps, plus a
  "Nothing runs without you" line. It is useful, but it is a table of 10 rows on a
  bar meant to feel light.
- **Offline:** a red-edged banner at the **bottom**: "Offline — Jarvis is not
  answering… Approving is blocked until it reconnects" with Reconnect. The top of the
  bar does not change. The "Local" route badge keeps its lit cyan look while
  offline (`shots-extra/quickbar-offline-tall.png`). In a short window the banner
  sits below the fold, as the harness crop shows.

### 2. Widget (`widget.html`, `widget.css`, `widget.js`)

- **Collapsed** (340×70): a green dot plus "62°" with no label (the label is only in the
  tooltip "GPU temperature", `widget.html:46`), a "LOCAL" pill, the note chips
  `#log #jop #obs`, pin, and expand.
- **Expanded:** the chosen face in an iframe (`widget.js:395`
  `faces.html?mode=display&feed=parent`), then VRAM, CPU and GPU meters (these have
  warn and critical states, `widget.css:442-450`), then a "Capture a note…" row.
- **Approval in the widget:** a rounded amber-edged box, "Needs your OK", the rush quote,
  "An email - open the Jarvis bar to read all of it", then **Deny as a red outline
  button and a solid green "Read it in the Jarvis bar" button**
  (`widget.css:724-740`; `default/10`).
- Feels polished: compact and readable, the face earns its space, and the meters
  are simple.
- Feels dated or cryptic: `#jop` / `#obs` are abbreviations, "62°" is a bare number,
  and the buttons are 11px text with a 5px radius written straight into the CSS
  (`widget.css:704-716`), so they ignore the `--radius-control` token.

### 3. Brain (`brain.html`, `brain.css`, `brain.js`)

- **Layout:** a left rail with a three-ring logo (`brain.html:37-43`), then
  Memory, History, Faculties and Work, and an "Advanced" fold for Galaxy, Live, Trust
  and Watch. A theme dropdown sits at the bottom of the rail. The right side has a top
  bar with the view title in Chakra Petch (`brain.css:220-226`), a grey one-line
  subtitle, a "Linked" pill and Refresh, then a status line ("Link live · memory read
  just now") and the page's cards.
- **Rail icons are text symbols, not drawn icons:** ✦ ◷ ◆ ▤ ◍ ≋ ⛨ ◈
  (`brain.html:55-112`, class `rail-glyph`). They render in whatever font the
  system has, at slightly different weights and baselines. This is the most
  "dated" detail in the app (`shots-extra/brain-*.png`).
- **Card titles:** Chakra Petch, cyan, uppercase, 12px, letter-spaced
  (`brain.css:596-605`). This looks good and gives the Brain a "HUD" character.
- **Memory tab:** mostly paragraphs of explanation followed by a key/value list
  ("Background learning: on / Waiting: 2 / Note: extraction is a scaffold…"),
  pill buttons, and two checkboxes with long descriptions. Empty states are one
  grey line ("Nothing has been saved automatically yet.").
- **Galaxy:** the most striking screen. It is a force graph on near-black, with
  ten groups drawn in five hues, each as a filled or a hollow dot
  (`theme.css:161-181`), and a chip legend with counts. It genuinely looks
  cutting-edge.
- **Live:** a flat cyan disc for "Idle" (not the animated face), a key/value
  list, and an "interruption budget" segmented bar. The segmented bar is a nice touch.
- **Trust / Work / Faculties:** long cards of text and key/value rows. Hashes and
  jargon show through ("digest 9f2c1a77be40", "Head sequence", "Lane", "mcp tool").
- **Across every tab:** the same red "rush latch" banner repeats under the top bar
  on every view (in the sample data). It is right to show it, but it takes the
  first row of every page.
- **Themes:** Daylight and High Contrast both look correct here
  (`shots-extra/paper-brain-memory.png`, `high-contrast-brain-memory.png`).

### 4. Settings (`settings.html`, `settings.css`, `settings.js`)

- **Layout:** one column of **22 cards** on one scrolling page. The first card is
  `settings.html:50` and the last is `:1316`. The comment says this is on purpose:
  "One long page of cards, Connection first" (`settings.html:36-38`). There is **no
  in-page menu or jump list** (the only `href="#"` is a hidden voice-model link,
  `:389`). Rendered at 680px wide, the page is about **14,500px tall**, roughly 16
  screens (`shots-extra/settings-full.png`, 28,938px at 2x).
- **Text density:** Connection alone is about 6 paragraphs before the first button.
  Voice has about 15 separate explanations. The explanations are honest and
  well written, but together they make a wall.
- **Controls:** there are three different on/off patterns. The first is a label
  followed by a native checkbox on the right ("Look for updates…",
  `settings.html:267-270`, with no `accent-color`, so it shows as the browser's blue). The
  second is a checkbox on the left with a title and description (`.toggle`,
  `settings.css:135`, cyan). The third is segmented buttons ("Straight away / 1 min /
  5 min / 15 min", "Keep on screen (recommended) / Read aloud"). The segmented ones are the
  clearest and most modern.
- **Headings:** there are three levels that look unrelated to each other. Card titles
  are 13px uppercase cyan in the **UI font** (`settings.css:69-76`), while Brain uses
  Chakra Petch for the same role. Sub-heads are bold white sentence case. Field labels
  are grey uppercase.
- **Status lines** use mono in green ("Windows Hello is set up on this PC.") or plain
  text. Missing-component messages print file paths
  ("~/.openjarvis/voice-models/tts").

### 5. Faces, the "Jarvis Reactor Kit" (`faces.html`, `faces-spec.js`, `jarvis-visual-spec.json`)

- The most designed window in the app. It has a big Chakra Petch title, a mono
  over-line ("20 FACES · 50 COLOURS · 12 PATTERNS"), state chips with colour swatches, a
  pattern row, a 10×5 palette grid, quality and frame-rate segmented controls, and a
  grid of live face previews (Arc, Orbit, Geodesic, Spectrum, Tokamak…).
- It keeps its own palette on purpose (`tests/themes-all.mjs:22-26`).
- It reads like a developer tool: "batch 0/3 measured 45.7 ms/frame · 10 live" and
  "13 fps · 1.0x" on every tile. Headless Chromium measured 11–13 fps here. That
  says nothing about a real GPU.

### 6. HUD (`jarvis_hud.html`)

- A three-column "instrument" layout: a left rail (TALK / BRAIN, lanes, systems), the
  face in the centre with the conversation, and a right rail (last exchange, memory
  counts, budget, voice).
- It has **its own palette and tokens** (`jarvis_hud.html:24-57`: `--void`,
  `--plate`, `--ice`, `--gold`, and eleven graph hues `--g-*`). It does not load
  `theme.css`, and the comment says it commits to one dark look (`:20-22`). So the
  HUD ignores the three themes, and its brain graph colours differ from the Brain
  window's five-hue galaxy (`theme.css:161-181`).
- **Low-contrast labels:** section labels use `--dimmer` `#3f5566`
  (`jarvis_hud.html:87,102,134,146,201,309`) at 9–10.5px. I computed
  **2.3–2.6:1** against its three backgrounds (the floor for text is 4.5:1). The
  HUD is not in `contrast.mjs`, `a11y.mjs` or `themecheck.mjs` (I grepped
  them). The same goes for onboarding.
- The demo data shows "escalate / critic / bulk — CLOUD" lanes and a "FREE-TIER
  BUDGET" section. I have **not checked** whether the real HUD server still reports
  cloud lanes. If it does not, those rows are leftover design, and they visually
  suggest a cloud path in a local-first app.

### 7. Onboarding (`onboarding.html`)

- Three steps, a big glowing cyan dot, "1 OF 3 — THE TRAY ICON", a large heading,
  three example rows, step dots and a filled cyan Next button. It is clean and friendly.
- **It teaches the wrong colours.** The example dots are written into the page as
  hex values: Thinking amber `#ffb648` and Waiting-on-you red `#ff6a6a`
  (`onboarding.html:85-86`). The real default colours come from the shared visual
  spec, which the tray reads too (`src-tauri/src/spec.rs:1-24`). In that spec,
  Thinking is an azure-to-violet sweep and "Waiting on you" is **amber**
  (`jarvis-visual-spec.json`, states `thinking` / `approval`; `theme.css:156,158`).
  So a new user is told "amber = thinking", and the first time amber actually means
  "approve something" they will read it wrong. The inline style also has a raw
  `rgba(255,255,255,0.03)` (`onboarding.html:78`). The token check only scans five
  CSS files (`scripts/check-tokens.py:12`), so it never sees this.

## Cross-cutting findings

1. **Tokens that exist only in one file.** `--surface-raised`, `--hairline` and
   `--hairline-strong` are defined only in `style.css:37` (and its own block), but
   they are used in `settings.css:159-160,435,462,464`, `widget.css:161,174,192,194,603-604,760-761`
   and `brain.css:819-820`. Those three pages never load `style.css`. I checked the
   computed styles in the copy: `--surface-raised` is empty in Settings, the widget
   and Brain, and a disabled `.btn` there has a **transparent** background. The
   Settings hotkey boxes are transparent too. `check-tokens.py` and `tokens.mjs`
   both pass (I ran them in the copy), so nothing catches this. This is a real
   styling bug and it is cheap to fix.
2. **Two type families for the same job.** Chakra Petch is loaded only by Brain, HUD,
   Faces and onboarding. It is not loaded by the quickbar, widget or Settings
   (`index.html:28-29`, `widget.html:28-29`, `settings.html:28-29` do not link
   `fonts/fonts.css`). So card titles are Chakra Petch in Brain and the plain UI font in
   Settings, and the bar that people see most has none of the "Jarvis" typeface.
3. **No type scale.** Across the four main stylesheets there are about 20 different
   font sizes, most of them crowded between 9.5px and 13.5px (for example 43× 12px,
   43× 11px, 30× 11.5px, 21× 10px, 16× 12.5px, 12× 10.5px, 8× 9.5px). A "type
   scale" means a short fixed list of sizes. There is no size token in `theme.css`,
   only families (`theme.css:204-209`).
4. **Radius and motion tokens are half-used.** 65 radii are written as raw pixel
   values against 34 that use the token. Durations are mostly raw (`shell-in 180ms`,
   `card-in 200ms`, widget `140ms`), even though `--dur-*` exists
   (`theme.css:214-218`).
5. **The same thing looks different in different windows:**
   - The route badge is "Local / model" in bold sentence case in the bar, "LOCAL" as an
     uppercase mono pill in the widget (`widget.html:49`), and the "Linked" pill in Brain.
   - Approve and Deny: in the bar, Deny is neutral and Approve is a tinted green outline
     (`style.css:1623-1638`). In the widget, Deny is a red outline and Approve is solid
     green (`widget.css:724-740`).
   - The approval title is monospace, cut off with "…" on one line
     (`style.css:1267-1275`), while the widget's title is bold sans and wraps.
   - The face: the chosen animated face appears in the HUD and the expanded widget. The
     bar has its own small SVG reactor (`index.html:50-74`), and Brain has a
     three-ring SVG mark (`brain.html:37-43`) and a flat disc on Live.
6. **Raw machine text leaks into the look:** the JSON arguments on the model-switch
   approval (`{"ref": "qwen3:8b"}`, `default/04`), "tier auto → ask", "from
   tool:browser_navigate", "digest 9f2c…", file paths in Settings, and the footer's
   "Core / Ollama / LiteLLM". The approval card is meant to stay plain (so that is
   the other reports' call), but this is where the app looks most like a dev tool.
7. **Reduced motion gaps (small):** the Settings update bar's endless sweep
   (`settings.css:524-532`) has no `prefers-reduced-motion` block. Settings has none at
   all, and neither does onboarding. The token-level collapse in `theme.css:398-407`
   shortens durations but, as its own comment says, cannot stop keyframe loops.

## What already feels polished (keep it)

- **The token contract and the three themes.** Reactor, Daylight and High Contrast
  are real, tested palettes. Daylight is a true light theme, not an inversion, and High
  Contrast clears 7:1 with thicker strokes (`theme.css:260-395`). All shots in all
  three themes looked right.
- **The Galaxy graph** and the **Faces kit**. These are the two "wow" surfaces. They
  already look cutting-edge.
- **The answer card**: its markdown, code wells and inline code chips.
- **The approval card in the bar**: its amber edge, shield, plain cost line, and "Nothing
  runs until you decide". It is plain and unmissable, as it must be.
- **Segmented choice buttons** in Settings (lock timeout, read-aloud, hands-free
  trust). These are the most modern control in the app.
- **The widget's meters** with warn and critical levels, and its compact header.
- **Onboarding's layout**: one idea per step, a big heading, and a single Next.
- **Motion that means something**: the streaming scan line, card rise-in and
  mic pulse, each with a reduced-motion fallback in the bar.

## What looks dated, cramped, inconsistent or plain

- Dated: the Brain rail's text-symbol icons (✦◷◆▤◍≋⛨◈), the native blue checkbox in
  Updates, and the key/value lists of raw numbers (Trust ledger, Live).
- Cramped: widget buttons and labels at 10–11px; HUD labels at 9–10px in low-contrast
  grey; the quickbar primer table on a small bar.
- Inconsistent: two heading fonts, three on/off control patterns, three route-badge
  styles, two Approve/Deny styles, three kinds of "Jarvis mark", and HUD colours that
  ignore the themes.
- Plain: Settings (22 cards, 16 screens, no menu) and most Brain tabs (text-heavy
  cards with one-line grey empty states). Empty states have no picture or next step,
  only a sentence.
- Wrong: onboarding's tray colours contradict the real spec, and three tokens are
  undefined in three windows.
