# Handoff — the UI, flexibility and Brain research, and what to do next

**Written 2026-10-09.** Everything a fresh conversation needs to continue this work
without re-researching it, without undoing a decision that was already made, and
without repeating a mistake this research already caught.

**Read in this order:** this file → [`SUMMARY-UI-RESEARCH-2026-10-09.md`](SUMMARY-UI-RESEARCH-2026-10-09.md)
(the five-minute version) → [`UI-CUTTING-EDGE-2026-10-09.md`](UI-CUTTING-EDGE-2026-10-09.md)
(the full research, 18 parts) → [`RULE-FLEXIBILITY.md`](RULE-FLEXIBILITY.md)
(how a rule may be relaxed) → the repo's own `CLAUDE.md` (which is the
owner's decisions log and always wins over anything here).

---

## 1. What was produced, and where it lives

| File | What it is | Size |
|---|---|---|
| `docs/UI-CUTTING-EDGE-2026-10-09.md` | **The full research.** 18 parts: the UI plan, the current open PRs and six self-corrections, the flexibility audit, text messages, and Brain compared to the outside world | ~2,400 lines |
| `docs/SUMMARY-UI-RESEARCH-2026-10-09.md` | **The five-minute version**, plain words | ~245 lines |
| `docs/HANDOFF-UI-RESEARCH-2026-10-09.md` | This file | — |

**These three are untracked new files.** They are not committed. Nothing in this
research has been built; no application code was changed by it.

### What the research actually covered

1. **The UI, both apps** — how to make the Android app and the desktop app better
   looking, more effective, simpler and more customizable. Six parallel research
   streams: Tauri 2 + WebView2, Jetpack Compose, design tokens across both apps,
   AI-assistant chat/approval UI, spotlight-and-widget surfaces, and visual craft
   (motion, colour, shaders).
2. **Flexibility** — how to make all the features configurable, without turning
   settings into a wall.
3. **Text messages (SMS)** — GitHub repos and tools for controlling messages.
4. **Every open PR** — reconciled against `main`, which forced six corrections.
5. **Brain** — the internal-state hub and its Galaxy graph, compared against
   seventeen graph libraries and ten different design paradigms.

---

## 2. The current state of the repository (measured, not remembered)

```
Branch:      docs/patch-anchor-fragility
HEAD:        62265666  Merge pull request #147 (docs/patch-anchor-fragility)
origin/main: 6fa64841  (as checked 2026-10-09 14:14)
```

**Nine PRs are open:** #151 `feat/new-chat-timer` · #152 `feat/handoff-front-setting`
(**this one has a merge conflict**) · #156 `feat/searxng-setup` · #157 `feat/voice-bar`
· #158 `audit/android-device` · #159 `fix/android15-compat` ·
#160 `fix/reanchor-tutorials-and-screen-attach` · #161 `fix/stale-connection-status` ·
#162 `fix/watch-false-allclear`.

**Twenty-four remote branches are unmerged.** Three matter:

- **`origin/audit-pass-2026-10-05` and `origin/next-browser-suites` are the same
  commit** (`43f60139`), and **all seven of its commits are already in `main`** under
  different hashes. Merging it today is a **net deletion of 754 files.** Do not.
- **`origin/next-auditpass-review`** holds the proof of that, in one document.
- **The widget's wrong-card fix is hiding on that superseded branch** as
  `jarvis-desktop/src/approval-target.js` + `tests/approval-target.mjs`. Lift the
  file; do not merge the branch.

**Uncommitted in the working tree** (someone is mid-work — coordinate before
touching these):

| File | What the change is |
|---|---|
| `CLAUDE.md` | Modified — the owner's decisions log |
| `docs/CLAIMS.tsv` | Modified |
| `jarvis-client/.../ui/screens/SettingsScreen.kt` | **A settings search box** — `SettingsSearch` / `SettingsSearchWords`, and `SETTINGS_ITEM_INDEX` renumbered |
| `jarvis-desktop/src/settings.html` | The same search box, 86 lines |

**New untracked docs written outside this research:** `docs/RULE-FLEXIBILITY.md`,
`docs/CAR-MODE-DESIGN.md`, `docs/HANDOFF-SETTINGS-AND-INSTALLER.md`,
`docs/DSH-PLUGIN-BRIDGE-DESIGN.md`,
`docs/SELF-IMPROVEMENT-AND-CAPABILITY-AUDIT-2026-10-06.md`,
`docs/HANDOFF-2026-10-06-self-improvement-audit-and-openjarvis-borrows.md`.

---

## 3. Do not re-open these — they are decided

A fresh agent will otherwise "helpfully" undo them. All four of these came out of
this research.

### 3.1 Auto-send is forbidden forever

`docs/RULE-FLEXIBILITY.md` entry 002, from the owner on 2026-10-09: Jarvis never
sends a message by itself — *"not in car mode, not when the owner is driving, not for
a contact the owner has named, not ever. Auto-send is not a setting that is off by
default — it is not built at all."*

**An earlier draft of this research recommended "auto-reply to named senders only"
as the most defensible reading of the owner's request. That recommendation was wrong
and has been struck from the report.** If a request arrives that sounds like
auto-send, that is **a finding to report**, not a feature to add.

What *is* allowed (entry 002, and it is **not** a rule relaxation): Jarvis may
compose a reply, **speak it aloud**, accept a **spoken** reply (worked out on the PC —
a client never does speech-to-text), and show it back. The human always sends. Two
settings, either can be on alone: *"Jarvis can suggest replies"* and *"I can reply by
voice"* — off is immediate, on raises a card. Messages Jarvis does **not** answer at
all, and says so: one-time codes, banking, money, health, and anything that commits
the owner to a plan.

### 3.2 Car mode may read texts aloud, and that is the only exception

`RULE-FLEXIBILITY.md` entry 001. Car mode is **phone-only** — a real head unit needs
Play distribution and rule 5 says sideload-only, so that is the shape of the feature,
not a limitation to work around. See `docs/CAR-MODE-DESIGN.md` for the design (two
modes: **Driving**, screen mostly off, voice first; **Parked**, screen on, large
targets for a glance). What is kept, unchanged: **never replies, never sends**; codes
hidden before anything reaches the model **or the speaker**; every message is outside
text; nothing leaves the owner's devices; off by default, turned on by asking.

### 3.3 Four things the 2026-10-05 audit called broken are already fixed

Do not spend time on these. Each was verified fixed on `main`:

| Was reported broken | Actually |
|---|---|
| `imePadding()` missing on the Android root | Fixed — `MainActivity.kt:1805`, commit **`8c0da3af`** |
| Settings' "Jump to" used stale indices | Fixed — `SettingsScreen.kt:242,255` via `ScrollToKeyOnce` |
| `Modifier.pressable` had no minimum tap target | Fixed — `ui/parts/Parts.kt:102-124`, `minTouchTarget = 48.dp` |
| The chrome accent was a literal, not derived from Idle | **Already derived** since **`24fed569`** — which *predates* the audit that said it was missing. `jarvis-link.js:921-1064` ports `accentFor`, and `legibleColour()` **is** the two-backdrop contrast walk |
| `settings.css` and `brain.css` both lacked `forced-colors` | `settings.css` **has had it** since **`f4eaf03f`**. Only `brain.css` lacks it |

### 3.4 Three pieces of standard advice that are wrong for this repo

The report's Part 2 explains each in full. In short:

- **Do not swap Acrylic for Mica.** `windows.rs:126-143` already reasons it out: Fluent
  puts Mica on long-lived base layers and Acrylic on transient light-dismiss surfaces,
  and a command palette is the canonical Acrylic case; Mica samples the wallpaper
  rather than blurring what is behind, which loses the glass effect on a 750×80 pane;
  and Mica needs Windows 11 22000+ where Windows 10 fails outright. **What is still
  worth doing:** *measure a drag* of the quickbar and the widget, because the ~7 Hz
  resize throttle covers resizing but not dragging, which is what Tauri's warning
  actually names.
- **Do not rewrite the desktop frontend in a component framework.** It is **11
  separate HTML documents, each its own webview and its own JS realm** — a framework
  runtime would be instantiated once per window, and Svelte/Solid need a compiler.
  `brain.js` being 497 KB is an **ES-modules** problem; `@layer` is the cascade
  problem; `<template>` + `cloneNode` is the rendering problem.
- **Do not adopt Material 3 Expressive.** It is **not in `material3` 1.4.0** — the
  whole Expressive surface is on the `1.5.0` line, currently `1.5.0-beta01`, and the
  release notes show a promotion being **reverted** (`MaterialShapes`,
  `LoadingIndicator` in `1.5.0-alpha19`). It also overshoots (spatial springs at
  damping 0.6–0.8), which contradicts the project's own *"small, slow, eased, never
  busy"* doctrine. Take expressive's **stiffness** with **standard damping 0.9–1.0**.

---

## 4. The work, in order

Effort estimates assume one beginner-to-intermediate developer.

### Phase A — the two widget approval defects (about half a day) — **do this first**

There are two, and the first is the most serious thing this research found.

**(a) The wrong-card bug.** The widget has **one** pair of Approve/Deny buttons and
**one** card slot. When a card is answered elsewhere — the phone, the Jarvis bar —
the next card slides into slot 0 and the buttons stay put, so a click aimed at the
card the owner was *reading* decides a card they have never seen. `widget.js` reads
`state.approval`, which is by then the new card, and the queue lookup that could have
caught it is never made. Buttons disabled for a stale decision is a *different* thing
from a swapped card, so `syncApprovalButtons` cannot catch it. This is finding 1 of the
five that matter most in `docs/DEEP-AUDITS-2026-10-05.md` §5, and **no branch fixes it.**

*The fix already exists* — `jarvis-desktop/src/approval-target.js` on
`origin/audit-pass-2026-10-05`:

```powershell
git show origin/audit-pass-2026-10-05:jarvis-desktop/src/approval-target.js
git show origin/audit-pass-2026-10-05:jarvis-desktop/tests/approval-target.mjs
```

Its shape: capture the card id **when the buttons are pressed**, look it up in the
queue live at that moment; if it has gone, decide nothing and say so in one sentence
("That card was answered elsewhere, so nothing was sent."); **refuse Deny the same
way**, because "deny whatever is on screen now" is the same wrong-card decision with
the opposite sign. Nothing in that module decides anything — the caller still goes
through `decide_approval` in Rust.

**(b) The clamped-detail bug** (audit D1). `widget.js:1080` still keys the redirect on
`isHeavy(approval)` alone, and `heavy-approve.js:34-35`'s `isHeavy` is
`notice.weight === "heavy"` only — so a **missing `notice` counts as "normal"** and a
320×44 strip can approve a card that sends email or switches a model, on two clamped
lines. Fix it on data the card already carries: redirect whenever
`approval.risk.reach !== "local"` **or** `risk.reversible !== "yes"`.

**(c) While in there:** `docs/DEEP-AUDITS-2026-10-05.md` §5 records that desktop text
sits at **10–11 px in places, including the widget's own Approve and Deny** — which
contradicts `theme.css`'s own rule that nothing protecting or warning the owner sits
below `--text-sm`.

**Then run:** `cd jarvis-desktop; npm run test:all`

### Phase B — one source of truth for the look (about half a day) — **best value per hour**

The two apps share theme **names** but not theme **values**. `tests/continuity.mjs:33-73`
asserts the labels and blurbs match and regex-checks two surface hex values; it does not
check the colours. Those are hand-maintained in two languages, and three phone values
had already drifted a digit.

1. Extract the theme values into `tokens/themes.tokens.json` in **DTCG shape** (a token
   is any object with `$value`; a group is any object without it; `$type` inherits down;
   aliases are `{group.token}`).
2. Write `tools/tokens/build.mjs` (zero dependencies) emitting `src/theme.css` **and**
   `jarvis-client/.../ui/theme/Themes.kt`, keeping today's exact selector and class names.
3. Add a `--check` drift mode to the existing test run.
4. **Extend `tests/continuity.mjs` from "words match" to "values match".** This is the
   item that retires the whole bug class.
5. Add the two-backdrop contrast assertion over the generated output (the desktop already
   checks against black *and* white because its windows are translucent — keep that).

**Why not Style Dictionary:** it genuinely can do this (it has a built-in
`compose/object` format alongside `css/variables`, Apache-2.0, ~4.9k★), but of its ~40
formats this needs two, and it requires Node ≥ 22. Shape the JSON as real DTCG now and
adopting it later is a config file, not a migration.

**Note:** the desktop theme ids are `deep-space` / `paper` / `high-contrast`; the phone's
are `reactor` / `daylight` / `contrast`. That mapping is deliberate and tested — keep it.

### Phase C — the desktop's modern-CSS pass (about 3–4 days)

WebView2 is Evergreen Chromium (~154), so there are **no Safari/Firefox fallbacks to
write, anywhere**. Already in use: `color-mix()` (11), `:has()` (9), `accent-color` (7),
`tabular-nums` (7), `color-scheme` (3). **Not used at all:** `@layer`, `oklch()`,
`@starting-style`, `@container`, `@scope`, `content-visibility`, `text-wrap`,
`interpolate-size`, `field-sizing`, `light-dark()`.

In order: **`@layer`** ordering across the 10 stylesheets (fixes which sheet wins) ·
**`@starting-style` + `transition-behavior: allow-discrete`** for the approval card and
HUD enter/exit, deleting JS timing code · **`content-visibility` +
`contain-intrinsic-size`** on the chat thread, memory lists and History, and
`contain: strict` on the face canvas · then the one-line wins (`text-wrap: balance`
/`pretty`, full `accent-color` coverage, `text-wrap`, `field-sizing`) · then a **spacing
and radius scale** in `theme.css` and enforcement of it (there are ~95 literal
`border-radius` rules against 4 tokens) · then `oklch()` authoring and the contrast walk ·
then a static grain overlay and the layered-shadow-plus-rim recipe.

**Do not:** adopt Tailwind or daisyUI (Tauri's CSP forbids CDN content and Tailwind's
`@theme` block *is* a colour-literal file — that would swap one enforced contract for two
unenforced ones); vendor anything by CDN (`npm pack` it once and `@import` from
`@layer vendor`); or use cross-document View Transitions between windows (they work only
inside one document, and these are separate webviews).

### Phase D — the phone, on stable versions only (about 4–6 days)

**Open PR #159 already fixes the display-cutout inset bug** — review and merge it rather
than writing it (`WindowInsets.systemBars.union(WindowInsets.displayCutout)`; Android 15
lays a `targetSdk 35+` window under the cutout, and only landscape lost content).

Genuinely unstarted, and each verified: **predictive back** at `targetSdk 36` (on
Android 16 `onBackPressed` is not called and `KEYCODE_BACK` is not dispatched at all —
that is a silent break, not polish) · **the urgent notification channel created once at
final importance** (a channel's importance can only ever be *lowered* after creation) ·
**an in-app and a notification route to every approval**, so the widget is never the only
way in (Android 15+ force-stopping the app disables its widgets) · **`key` + `contentType`
on the thread `LazyColumn`** plus `Modifier.animateContentSize()` · **springs** replacing
`tween` · **shared-element transitions** for approval cards · **baseline profiles**
(sideloading means no Play cloud-profile delivery — a real disadvantage a shipped
profile fixes) · **Glance 1.1.1 → 1.2.0** (**not** 1.3.0-alpha02, which demands AGP
9.2.0) · **`material3.adaptive` + `NavigationSuiteScaffold`** (Android 16 ignores
`screenOrientation` at `sw ≥ 600 dp` for `targetSdk 36`) · **`graphics-shapes:1.1.0`** ·
**reduce-motion wired to the system setting** · **pin `material3:1.4.0` explicitly** ·
**bundle IBM Plex Sans** (`JarvisTheme.kt:227-231` says it is the only change needed,
and it is the only real code TODO in the app).

**Verify before relying:** whether `material3:1.5.0-beta01` needs `compileSdk 36` or 37
is the go/no-go for ever adopting Expressive, and it could not be determined from
metadata — `CheckAarMetadata` fails fast and cheaply if you try the swap on a scratch
branch.

### Phase E — the approval card and "what is it doing" (about 3–4 days)

The card: a **cause line** saying why it exists now (audit D8 — still open, and the
origin row exists *only* for a server `raised` payload); the **missing sentence saying
what it does NOT grant** (audit D2 — three of the project's own documents ask for it
verbatim and grepping the tree finds it nowhere); the **Deny treatment** (audit D3 —
`style.css` has `.approval-button` and `.approval-deny:hover` but **no `.approval-deny`
base rule**, while `widget.css:797-801` makes Deny red-bordered at rest, so refusing
looks like the destructive act); no default button; outcome-named labels; and the
irreversible few behind the existing Windows Hello / screen-lock step.

Grounding worth keeping: Anthropic's own post reports **users approve roughly 93% of
permission prompts**, and a browser study found fatigue setting in inside 60 seconds.
So the rule is **fight fatigue by raising fewer cards, not by weakening any card** —
and if a feature would raise more than a handful of cards a week, *that is a design
defect in the feature*.

The activity block: one collapsible block per turn, not one bubble per tool, with the
state vocabulary **Pending → Awaiting Approval → Responded → Running → Completed /
Error / Denied**.

### Phase F — flexibility (about 1–2 weeks, in slices)

**Read `UI-CUTTING-EDGE-2026-10-09.md` Part 15 first** — it has the three recipe
variants with exact file lists. In short: **merge the three flexibility PRs first**
(#151, #157, #152 — resolve #152's conflict), because each is a worked example of the
recipe and merging first means copying a shape that is already on `main`. Then **land
the settings search box already in the working tree**, then **one "How long things last"
card with nine rows** (`late_ring_limit`, `offline_grace`, `focus_minutes`,
`live_minutes`, `screen_minutes`, `tellme_window_days`, `chat_keep_days`,
`history_chars`, `undo_minutes`) — nine `LIMITS` lines and nine appended phone rows, not
nine cards.

The machinery already exists: `jarvis_settings_registry.py` (`SECTIONS`, 42 rows),
`jarvis_asks_first.py` (`HARD_LIMITS`, `MUST_ASK`, `PC_ONLY_ACTIONS`, `NEVER_HIDE`,
`FIXED`), `jarvis_limits.py` (**`LIMITS`, exactly 7 entries**), `jarvis_menus.py`
(`MENUS`, 110 rows), `features/features.json` (121 features). Adding a setting means a
`Section`, a `_m(...)` row, `python3 tools/gen_menu_cases.py`, three lines in
`MenuPlaces.kt` / `OpenPlace.kt` / `SettingsJump.kt`, a `covers` entry, and the
byte-identical copy of `features.json` to both clients.

**Part 15.5's "must stay fixed" list and `RULE-FLEXIBILITY.md`'s floor list agree** —
see §5 below. Do not make any of them a setting.

### Phase G — Brain (see §6)

### Phase H — accessibility (1–2 days)

The streamed answer has **no live region** while 102 status lines do (audit §3.1) — so a
screen reader hears "Couldn't read the watch list" but never hears the answer arrive.
Fix: `aria-live="polite"` (**never** `assertive`) on a **separate, initially empty**
status element, with `aria-busy="true"` while streaming. Announce "Thinking…" at the
start and the answer at the end; **never per token.** On the phone the equivalent is
`Modifier.semantics { liveRegion = LiveRegionMode.Polite }` (confirm the names).

Also: a `forced-colors` block in **`brain.css` only** (audit D6 — `settings.css` has had
one since `f4eaf03f`) · focus restore in the menu-visibility list (`menu-visibility-settings.js:64-67`
still does `container.innerHTML = ""` then rebuild, with no `document.activeElement`
read — the correct idiom already exists in `settings.js:2137`) · the `.mjs` → `.py`
comment fix (`theme.css:14,23` and `brain.css:7` name `check-tokens.mjs` and
`check-contrast.mjs`, **neither of which exists**; the real files are
`scripts/check-tokens.py` and `tests/contrast.mjs`).

---

## 5. The boundaries — do not cross these

From `CLAUDE.md`'s five non-negotiable rules and `RULE-FLEXIBILITY.md`'s floor. Six are
absolutely unrelaxable:

1. **No public tunnel.** No ngrok, no Cloudflare Tunnel, no Tailscale Funnel.
2. **Never auto-approve anything**, and acting stays blocked while the event stream is
   stale.
3. **The pairing token and every API key are never logged**, and never written to disk
   in plain text.
4. **A client never does speech-to-text.** The words are worked out on the PC.
5. **Non-commercial, sideloaded, never on Play.**
6. **No bulk approval, and nothing that clears a rush latch.**

**How a rule may be relaxed at all** (`RULE-FLEXIBILITY.md`): three steps, all required.
(1) A written entry naming the rule, the feature, the date, **who decided** — an agent may
not — and exactly which protections are kept. (2) A gate action at tier `ask`, so a card
says in plain words *which rule* is being relaxed, not "allow feature X". (3) A line on
the "What asks first" page. **Turning a relaxation off is always immediate, with no
card.**

**The eight things a flexibility pass must never touch** (Part 15.5, guarded by tests
that fail the build — `test_asks_first.py:209-233`, `:362-396`, `:431`, plus
`check_parity.py`, `check_feature_list.py`, `gen_menu_cases.py --check`):
`HARD_LIMITS` · `MUST_ASK` · `PC_ONLY_ACTIONS` · `NEVER_HIDE` · the `FIXED` set and the
fail-safe tier parse (an unknown tier must read as `"never"`, never `"auto"`) · the
injection detector's own lists (`jarvis_content_risk.py:78,90,171` — *a detector the owner
can tune off is a detector an attacker can tune off*) · the event-stream contract
(`jarvis_events.py:62 RING=512`, `:71 KEEPALIVE=20` — named to clients in
`JARVIS-API.md`) · the Android safety floor (`abiFilters`, `versionCode`, the
approval/alarm channel importance, `setOngoing(true)`, `Security.kt:26,29,56`, the
smart-turn/stop-word thresholds, `commands.rs:1124 OWN_SUFFIXES`).

---

## 6. Brain — the ten directions, and which to pick

**Read Part 17.2 of the report first: it states the exact rules.** The critical one is
that the guard is *narrower than "no libraries"*:

```js
// jarvis-desktop/tests/galaxy-panel.mjs:104-121  (verified)
assert.deepEqual(scripts, ["brain.js"], "brain.html gained a script src");
assert.ok(!/from "https?:|import\(/.test(code), "an outside import");
assert.deepEqual([...code.matchAll(/invoke\(\s*"([a-z_]+)"/g)].map(m => m[1]), ["memory_used"]);
// and the panel may not mention: chat, history, document, graph, forget, erase, pin
```

So it forbids a second `<script src>` in `brain.html` and any remote/dynamic import — but
**adding a new local ES module is fine.** `package.json` has exactly **one** dependency,
`@tauri-apps/cli`, a build tool.

**And the good news: Galaxy is better than it looks.** ~330 lines in `brain.js` from
`:12076`, with a deterministic ring seed, 320 bounded cooling ticks, uniform-grid
repulsion, rAF-coalesced redraws, a theme-colour cache, and an 8 ms chunked settle under
`prefers-reduced-motion`. `galaxy-view.js` is the pure half, and it **already cites
Hindsight as its idea source**.

**Seventeen libraries were checked. At ~100 nodes, none beats what exists.** Two traps:
**tldraw** (its LICENSE forbids production use, forbids interfering with licence-key
enforcement, requires a watermark, and permits transmitting usage data to tldraw) and
**Neo4j NVL** (proprietary licence limited to Neo4j's own products, *plus* a Segment
analytics dependency). The only library worth a deliberate rule change is **d3-force**
(ISC, 15.4 KB / 5.7 KB gzip) — and its useful part, a static `tick(n)` layout with pinned
nodes, is effectively already built.

**The recommendation, in order:**

1. **Pin Galaxy as DOM/SVG "constellation"** — real `<button>`s on a ring or spiral by
   `kind`, sized by fact count, labels above a zoom threshold. Days. No library, no rule
   change, and it makes the project's own rule — *"nothing is drawn only on the canvas"* —
   **structurally true instead of promised.** Keyboard navigation, CSS-variable theming,
   forced-colours and **zero motion** all come free.
2. **Add the matrix/table view** as a second surface. Days. The only fully accessible
   view; this is what a screen reader will actually use.
3. **The calm Model tab** — `ollama ps` almost verbatim (model · which card · VRAM used of
   total · **until when**) plus nvtop's per-process → GPU mapping, with the second card
   reading **"ready, idle"**, never a warning. `hardware-panel.js` already reads the data.
4. **Freeze the layout** (Quartz's trick — precompute and store the coordinates) if
   Galaxy still feels unsettled. Needs a stored `x,y`, so a real backend change.
5. **The Work tab as a trace** (a Jaeger-style waterfall with two-run compare) **and steps
   inside the answer** — they share one span schema. **Span labels must stay metadata-only
   (`step kind, duration, outcome`)** or this becomes a new place private text lives
   outside the encrypted store.
6. **The Plex** (focus + context) and **the River** (timeline) as *siblings* to Galaxy,
   not replacements.
7. **The Ledger Trust tab** — one state word, a decisions-per-week sparkline, a filterable
   list; the rush latch and stale link become **named states**, never red errors.

**Do not:** build a live force-directed graph that animates while the assistant works
(it contradicts calm + reduced-motion, steals GPU from the model on shared cards, and
invites reading position as meaning when position is a simulation artefact) · run a
Langfuse/Phoenix-style observability stack beside Jarvis (a second privacy surface for
exactly the content rule 1 protects — and Phoenix is Elastic License 2.0, Langfuse is
open core) · put a single "risk score" on Trust (shame-adjacent, and it becomes the thing
nobody reads).

---

## 7. How to verify anything you change

```powershell
cd jarvis-desktop
npm run test:all      # test:tokens, test:ui, test:a11y, test:palette, test:themes, test:voice, test:release
npm run test:tokens   # the literal-colour check — fails on a colour outside theme.css
npm run test:themes   # themecheck, themes-all, distinct, contrast
npm run test:a11y     # a11y, disabled, palette-ui
```

The guard that will catch a Brain library: `node tests/galaxy-panel.mjs`.
The guard that will catch a new setting nobody declared: `python3 tools/check_feature_list.py`
and `python3 tools/gen_menu_cases.py --check`.
The guard that will catch the two clients drifting: `python3 tools/check_parity.py`.

**Do not trust "tests passed" alone.** `docs/DEEP-AUDITS-2026-10-05.md` §5 records that
**141 suite lines printed SKIP as PASS**, which is why several of the findings above went
unnoticed. That was fixed, but check what a test actually asserts before citing it.

---

## 8. What is genuinely uncertain

State these honestly; do not let a later session present them as facts.

- **The `compileSdk` question for Material 3 Expressive.** Whether `material3:1.5.0-beta01`
  needs 36 or 37 could not be determined from metadata. It is the go/no-go, and one
  scratch-branch build settles it.
- **The notification, bubble, Quick-Settings and foreground-service details** on Android
  14–16 are the least-verified part of the research. Read
  `about/versions/14/changes/fgs-types-required` and `about/versions/15/behavior-changes-15`
  in a real browser before touching floating/bubble mode.
- **Whether `material3.adaptive` and `graphics-shapes:1.1.0` raise the `compileSdk` floor.**
  One build each.
- **Does a `NotificationListenerService` actually complete another SMS app's reply
  `PendingIntent`?** The `RemoteInput` docs name a listener as the expected "remote input
  collection service", which implies yes — **unverified. Hardware test required.**
- **KDE Connect's SMS plugin on Windows.** It is compiled into the Windows build, and the
  Android half definitely sends SMS (KDE bug #464392, fixed 2023). Whether it *functions*
  on Windows is unproven. One afternoon over Tailscale.
- **`document.ariaNotify()` in the owner's WebView2.** Baseline 2026 (September 2026) and
  aimed exactly at the streaming-answer problem, but whether this build ships it is
  unverified — feature-detect it.
- **Every GPU cost ratio in Part 9.3** is arithmetic on pixel and step counts, not a
  measurement. The two Turing cards are the only place the open 60 fps-cap question can be
  settled.
- **The Android 15 `SYSTEM_ALERT_WINDOW` + background-FGS change** was found only through a
  search snippet of a localised page.

---

## 9. Open decisions

These are the owner's, and `CLAUDE.md` says give them as short multiple choice.

**Brain's visual element — which first?**
- **A — The DOM/SVG constellation** *(recommended)* — days, no library, makes the
  accessibility rule true by construction.
- **I — The table view** — if accessibility matters more than looks.
- **D — The River** — if you want the quickest visible win.

**The whole message history — should Jarvis be able to browse and search every text ever
sent or received?** (This is the only SMS question still open; car mode and drafting are
decided.)
- **No, leave it** *(recommended)* — car mode and drafting already cover reading and
  replying.
- **Yes, and write the `RULE-FLEXIBILITY.md` entry first** — it is a real reversal of the
  SMS rule and needs your decision.

**Also unanswered in `docs/CAR-MODE-DESIGN.md` §6 ("Questions only the owner can
answer")** — read that section before building car mode.

---

## 10. First actions for the next conversation

1. `git status` and `git log --oneline -5` — **confirm the state has not moved** since
   2026-10-09. If `main` moved or PRs merged, re-check Part 14's Table 3 before trusting
   any "still open" claim in this research.
2. Read `docs/SUMMARY-UI-RESEARCH-2026-10-09.md` (five minutes).
3. **Phase A** — the widget's two approval defects. The wrong-card bug is the most
   serious finding and no branch has claimed it.
4. **Phase B** — one source of truth for the theme colours, plus the values-match test.
5. Then ask the owner which Brain direction to take, and build it.

---

## 11. Addendum, 2026-10-09 (the desktop session) — what this research got wrong

Written after the desktop session re-checked §4's Phase A against `main` before
building anything (which is what step 1 above asks for). **Five corrections.**
The first one is the important one: the research's headline finding is not true
of `main`, and a fresh agent that trusts it will spend a day re-doing work that
was done on 5 October.

### 11.1 The wrong-card bug is FIXED, on `main`, and its fix is not on an abandoned branch

§2 and §4(a) say the widget's wrong-card fix "is already written and hiding on a
superseded branch", `origin/audit-pass-2026-10-05`, and that "**no branch fixes
it**". Both halves are wrong. `jarvis-desktop/src/approval-target.js` and
`jarvis-desktop/tests/approval-target.mjs` are **in `main`**, added by

```
6a37a9a5  desktop: the widget cannot approve a card it never showed,
          and the notification switches gate the posters      (5 Oct 2026 10:41)
```

which is an ancestor of `main` (verified with `git merge-base --is-ancestor`).
`node tests/approval-target.mjs` passes on `main`: 12 checks, including "a card
answered elsewhere between the press and the click is refused" and "a repaint
under the finger never moves the decision to the new card". `widget.js` already
carries the `ApprovalTarget` import, `state.cards.paint/press/resolve`, and the
`GONE_LINE` refusal.

**What this means for the next session:** do not lift the file, and above all do
not merge `audit-pass-2026-10-05` / `next-browser-suites` to get it — §2's own
warning stands, that merge is a net deletion of 754 files. The correct reading of
the timeline is that this branch was superseded *because its commits reached
`main` under different hashes*, and this one file was among them.

### 11.2 The clamped-detail bug WAS real — fixed in PR #177

§4(b) is accurate and was worth doing. `isHeavy` is `notice.weight === "heavy"`,
so a card with **no `notice`** read as `"normal"` and a 320×44 strip that clamps
its detail to two lines could approve it. Fixed by one pure gate,
`needsFullCard()` in `heavy-approve.js` (`risk` missing → true;
`risk.reach !== "local"` → true; `risk.reversible !== "yes"` → true), asked in
both `openApproval()` and `decide()`. `isHeavy` keeps its own job on the bar.

### 11.3 The streamed answer has a live region — §4 Phase H is wrong about that

Phase H says *"The streamed answer has **no live region** while 102 status lines
do"*, and that `index.html` needs one. It has the opposite: the answer
deliberately has **no** `aria-live` — `index.html:788-796` explains why, and
`jarvis-link.js:1287-1367` implements the shared announcer instead (two eagerly
created `sr-only` regions, `aria-relevant="additions"`, `aria-atomic="true"`,
one `announce()` entry point). The comment records that the old
`aria-live` on the answer was itself the bug, because `paint()` reassigns the
whole `innerHTML`. So: **do not add `aria-live` to `#answer`**; it would
reintroduce the regression the announcer exists to prevent.

Still real in Phase H: **`brain.css` has no `forced-colors` block** (verified —
`settings.css` has one at line 1279) and the `.mjs` → `.py` comment drift in
`theme.css:14,23` (the real files are `scripts/check-tokens.py` and
`tests/contrast.mjs`).

### 11.4 The settings "Jump to" and the settings search box moved on

`main` now carries PR **#163** (the settings toggle-row generator, merged
2026-10-09) and PR **#164** (`feat/settings-search`, open), and the working-tree
search box this research found uncommitted is parked in a stash, not in the
tree. **Do not hand-write or hand-edit a toggle row in `settings.html` any
more** — they are spliced between comment markers from the registry. Land #164
rather than rebuilding its 86 lines.

### 11.5 One line of this file's own "do not" list has since been superseded

Nothing in §3 changed. But note that #163 merging **unblocks** §4's item 3 (the
Docker settings layer). Its module is in PR #175, still open, so the pair lands
together rather than one now and one later.

### 11.6 How the desktop session verified all of this

```
git log --oneline -1 origin/main                       # 58f93e86 (#163)
git merge-base --is-ancestor 6a37a9a5 origin/main      # ancestor (0)
node tests/approval-target.mjs                         # 12 ok, 0 failing
node tests/heavy-approve.mjs                           # 16 ok, 0 failing
node tests/security.mjs                                # incl. the D1 control
py -3 scripts/check-tokens.py                          # 0 unreachable colours
```

Two of these need saying out loud: **`python3` does not exist on this machine**
— the harness note in `HANDOFF-DESKTOP-2026-10-09.md` is right, use `py -3`, and
`npm run test:all` cannot pass here unmodified for that reason alone (it calls
`python3` in `test:tokens`). And the browser suites **cannot be run in parallel**
in one sandbox: two concurrent Playwright runs produced two false failures
(`blockers.mjs`'s Approve control and `palette-ui.mjs`'s `face-voice.js`
`REQFAIL`), and both passed when re-run alone. Run them in series.

