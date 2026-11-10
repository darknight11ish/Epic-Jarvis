/**
 * hud-layout.js - the desktop HUD's layout model (the editable-HUD design's H1,
 * Gemini rulings 23-28, 2026-10-21; docs/ARCHITECTURE.md section 8).
 *
 * WHAT THIS IS, IN PLAIN WORDS. The big HUD window is arranged in named
 * regions (a left rail, a stage top, the stage, a right rail and a header),
 * and every card lives in one region in a chosen order, with a width and a
 * height. This module is the one place that says which cards exist, which
 * arrangement each of the seven built-in presets is, and how an untrusted
 * document (a hand-edited one, an imported one, an old one) becomes a safe
 * layout. It changes nothing on screen by itself: H2 is the editor that draws
 * it, and the Settings picker and the HUD bootstrap read it through here.
 *
 * WHY REGIONS AND NOT x/y. The HUD has to work at 150% DPI and at narrow
 * widths. A free (x, y) grid would need a collision solver to stop cards
 * overlapping when the window changes size; regions plus a CSS Grid span get
 * the same freedom and let the browser's own grid do the reflow. `x` and `y`
 * are therefore reserved and ignored in v1 (ruling 23) - they are dropped,
 * never trusted.
 *
 * THE PROTECTED CARDS. Four cards can never be hidden by any preset or any
 * import (ruling 25): approvals, the emergency stop, the voice controls and
 * the bar launcher. `normalizeLayout` forces them visible and puts a missing
 * one back in its default region, so a hand-edited document cannot remove the
 * one surface a pending approval must reach. `approvals` may be collapsed
 * when nothing waits, but is rendered expanded the moment a card arrives -
 * that is a transient view state, derived by `effectiveCollapsed`, never
 * written back into the saved layout (ruling 7).
 *
 * NO DEPENDENCY, NO BUILD STEP. This file is plain ES module JavaScript, the
 * same as the rest of the pages, and it is imported by the Settings window,
 * by the HUD bootstrap (as a string copy, the bootstrap cannot import) and by
 * tests/hud-layout.mjs. `contract/hud-presets.json` mirrors the seven presets
 * so Rust and the tests can read the same data; the test compares the two and
 * fails if they drift.
 *
 * WAVE 15 (2026-11-09): every preset now carries the COMPOSITION the redesign
 * spec's section 1.2 table asks for - which cards are the hero, which support
 * it, and which are gone - and the two capped layouts are capped in DATA, not
 * in a screenshot: Cockpit's right column is 2 (one card plus the page's own
 * today panel) and Command Center's is 3. "Gone" means `visible: false` on a
 * card the document still NAMES, never a dropped card, because hud-edit.js
 * re-adds a card a document does not name at its visible default. `visibleCards`
 * and `rightColumn` are the two readers of that data, shared by the page and
 * the tests. Two things are PAGE hooks rather than model data, and are declared
 * here so the page and this module cannot disagree about their spelling:
 * `PRESET_ATTR` (the active layout id as an attribute on <html>/<body>, so page
 * CSS can speak about one layout) and `RETURN_PILL` (the always-on way back
 * from Face Only / Mini View).
 *
 * @module hud-layout
 */

/** The version of the document shape this build reads and writes. */
export const LAYOUT_VERSION = 1;

/** The named regions a card can live in (ruling 23). `header` is first. */
export const REGIONS = Object.freeze([
  "header",
  "left_rail",
  "stage_top",
  "stage_main",
  "right_rail",
]);

/**
 * The shells a preset may choose between. H3 renders the value directly:
 * `data-hud-shell` on <html>/<body> and the six CSS/Flexbox variants on the
 * page (the old `data-hud-layout` look and the three-pill picker are gone).
 * The first three names are the layouts that predate H3.
 */
export const SHELL_TEMPLATES = Object.freeze([
  "three-column",
  "split-stage",
  "center-core",
  "two-column-left",
  "two-column-right",
  "single-stage-bento",
]);

/** The densities the renderer understands. */
export const DENSITIES = Object.freeze(["comfortable", "compact", "spacious"]);

/** The default values a document missing a field is repaired to. */
export const DEFAULT_SHELL = "three-column";
export const DEFAULT_DENSITY = "comfortable";
export const DEFAULT_STAGE_TAB = "talk";

/**
 * The most user layouts the owner may keep, and the rules for their ids and
 * names. Bounded here and in Rust (`hud_layout.rs`): a layout library is an
 * appearance-class document, not a dumping ground.
 */
export const MAX_USER_PRESETS = 20;
export const USER_NAME_MAX = 60;
export const USER_ID_RE = /^custom-[a-z0-9][a-z0-9-]{0,39}$/;

/** The stage tabs a layout can open on (the page's own four plus Talk). */
export const STAGE_TABS = Object.freeze(["talk", "galaxy", "today", "reminders", "memory", "telemetry"]);

/** The four cards no layout may hide (ruling 25). */
export const PROTECTED_IDS = Object.freeze([
  "approvals",
  "emergency_stop",
  "voice_controls",
  "bar_launcher",
]);

/**
 * THE ONE PAGE PANEL THAT IS NOT A CARD (Wave 15, 2026-11-09, spec section
 * 1.2/5.2). The reminders/today panel (`#rail-reminders` on the page) is drawn
 * by the page itself and is not in `CARD_REGISTRY`, so no layout can move it or
 * name it. In the shells whose right column is a STATIC column (the page's
 * `three-column` and `two-column-right`) it always fills one slot there, and
 * the spec's caps count it: "right column max 2" for `cockpit` is one layout
 * card (Waiting for You) plus this panel, and "exactly 3" for `second_brain` is
 * two layout cards (Waiting for You, Second Brain Counts) plus this panel.
 * `rightColumn()` below is the one place that adds them up, and it counts this
 * panel ONLY for those two shells - see `STATIC_RIGHT_RAIL_SHELLS` for why a
 * drawer or a zero-width column does not count it.
 *
 * The right rail also carries the page's transient `#setup-offer`; it is not
 * listed here because it appears only while the setup quiz is unfinished and is
 * not one of the layout's cards.
 *
 * To make it a real card, the page owner adds it to the model: a
 * `today` registry row here, `CARD_DOM.today = ["#rail-reminders"]` and
 * `today` in `MOVABLE_IDS` in hud-edit.js (and the page's `placeReminders()`
 * must stop moving that node between the rail and the stage, which
 * `hud-edit.js` would otherwise yank out of its own shell). Until then it is
 * declared here as a FIXED slot rather than quietly ignored.
 *
 * WHICH SPEC CARD IT IS: the spec names the second card of the right column
 * "Next Up Today" in Cockpit and "Today & Reminders" in Command Center. Both
 * are this one panel - Cockpit's column is `waiting` + this panel (2), Command
 * Center's is `waiting` + `brain_stats` + this panel (3). The owner's Calendar
 * card (`calendar`, the next seven days) is OFF in both, because a third
 * surface of the same "what is coming up" would break the cap the spec sets.
 */
export const FIXED_RAIL_PANELS = Object.freeze([
  Object.freeze({
    id: "rail-reminders",
    label: "Today & Reminders",
    region: "right_rail",
    order: 1,
  }),
]);

/**
 * The attribute the page writes on `<html>` and `<body>` to name the ACTIVE
 * layout id, so page CSS can speak about one layout at a time (Wave 15). The
 * model already carries the id; without this attribute the page can only see
 * the shell template, and `cockpit` and `second_brain` share none of their
 * shape with `studio`/`telemetry` in the stylesheet's vocabulary. The page is
 * the intended writer (it is the only side that knows the store answered);
 * nothing in this tree writes it yet, so this module only names the attribute
 * for the page and pins the spelling so a later page edit cannot rename it.
 */
export const PRESET_ATTR = "data-hud-preset";

/**
 * THE RETURN PILL (Wave 15, spec section 1.2). `ambient` ("Face Only") and
 * `minimal` ("Mini View") show almost nothing, so each must carry one always-on
 * control back to the owner's everyday layout - `[ ⤢ Back to Command Center ]`
 * - at the top right. The pill is page markup: this declares its id, class,
 * words, glyph and destination so the page, the presets menu and the tests share
 * one spelling (and so a renamed pill fails a test instead of vanishing).
 */
export const RETURN_PILL = Object.freeze({
  id: "hud-return-pill",
  class: "hud-return-pill",
  label: "Back to Command Center",
  glyph: "\u2922",
  target_preset: "second_brain",
});

/** The layouts whose whole stage is the face, and so must show the pill. */
export const RETURN_PILL_LAYOUTS = Object.freeze(["ambient", "minimal"]);

/**
 * The shells that draw the right column as a STATIC column on the glass (the
 * page's own CSS). Only there does the page-owned `#rail-reminders` panel fill
 * a slot in it, which is why `rightColumn()` counts that panel for these shells
 * and for no others: `split-stage` gives the column no width except on its
 * inspector tabs (where it is a fixed overlay), and `two-column-left`,
 * `center-core` and `single-stage-bento` open the right rail as a slide-over
 * drawer, so a closed drawer's panel is not on the glass.
 */
const STATIC_RIGHT_RAIL_SHELLS = Object.freeze(["three-column", "two-column-right"]);

/**
 * The card registry: one entry per card the HUD can show. `region`, `order`,
 * `col_span`, `row_span` and `collapsed` are the DEFAULTS a preset or a repaired
 * layout starts from; `protected` is enforced by `normalizeLayout`, never
 * trusted from a document. The labels are the owner's words, not code names,
 * so the H2 edit toolbar and the Settings picker can show them unchanged.
 */
export const CARD_REGISTRY = Object.freeze([
  {
    id: "emergency_stop",
    label: "Stop everything",
    region: "header",
    order: 0,
    col_span: 4,
    row_span: 1,
    visible: true,
    collapsed: false,
    protected: true,
    options: {},
  },
  {
    id: "nav",
    label: "Navigation",
    region: "left_rail",
    order: 0,
    col_span: 12,
    row_span: 2,
    visible: true,
    collapsed: false,
    protected: false,
    options: {},
  },
  {
    id: "lanes",
    label: "Focus presets",
    region: "left_rail",
    order: 1,
    col_span: 12,
    row_span: 1,
    visible: true,
    collapsed: false,
    protected: false,
    options: {},
  },
  {
    id: "systems",
    label: "Systems",
    region: "left_rail",
    order: 2,
    col_span: 12,
    row_span: 1,
    visible: true,
    collapsed: false,
    protected: false,
    options: {},
  },
  {
    id: "bar_launcher",
    label: "Open the Jarvis bar",
    region: "left_rail",
    order: 3,
    col_span: 12,
    row_span: 1,
    visible: true,
    collapsed: false,
    protected: true,
    options: {},
  },
  {
    id: "approvals",
    label: "Waiting for you",
    region: "stage_top",
    order: 0,
    col_span: 12,
    row_span: 1,
    visible: true,
    collapsed: false,
    protected: true,
    options: {},
  },
  {
    id: "voice_controls",
    label: "Voice controls",
    region: "stage_top",
    order: 1,
    col_span: 4,
    row_span: 1,
    visible: true,
    collapsed: false,
    protected: true,
    options: {},
  },
  {
    id: "conversation",
    label: "Conversation",
    region: "stage_main",
    order: 0,
    col_span: 12,
    row_span: 4,
    visible: true,
    collapsed: false,
    protected: false,
    options: { tab: "talk" },
  },
  {
    id: "composer",
    label: "Ask Jarvis",
    region: "stage_main",
    order: 1,
    col_span: 12,
    row_span: 1,
    visible: true,
    collapsed: false,
    protected: false,
    options: {},
  },
  {
    id: "galaxy",
    label: "Galaxy",
    region: "stage_main",
    order: 2,
    col_span: 12,
    row_span: 4,
    visible: false,
    collapsed: false,
    protected: false,
    options: { tab: "galaxy" },
  },
  {
    id: "reminders",
    label: "Reminders",
    region: "stage_main",
    order: 3,
    col_span: 12,
    row_span: 4,
    visible: false,
    collapsed: false,
    protected: false,
    options: { tab: "today" },
  },
  {
    id: "memory",
    label: "Memory",
    region: "stage_main",
    order: 4,
    col_span: 12,
    row_span: 4,
    visible: false,
    collapsed: false,
    protected: false,
    options: { tab: "memory" },
  },
  {
    // The owner's own calendar (2026-10-29): a card like every other one, so
    // Edit HUD can move it between the left rail, the stage top and the right
    // rail, hide it and put it back. Its markup home is `#rail-calendar`, the
    // rail section directly above the waiting cards - which is why it takes
    // order 0 here and the six cards that were already in this rail each move
    // down one. Nothing else about them changes.
    id: "calendar",
    label: "Calendar",
    region: "right_rail",
    order: 0,
    col_span: 12,
    row_span: 1,
    visible: true,
    collapsed: false,
    protected: false,
    options: {},
  },
  {
    id: "waiting",
    label: "Cards waiting",
    region: "right_rail",
    order: 1,
    col_span: 12,
    row_span: 1,
    visible: true,
    collapsed: false,
    protected: false,
    options: {},
  },
  {
    id: "telemetry",
    label: "Last Answer Speed",
    region: "right_rail",
    order: 2,
    col_span: 12,
    row_span: 2,
    visible: true,
    collapsed: false,
    protected: false,
    options: {},
  },
  {
    id: "tools",
    label: "Abilities used",
    region: "right_rail",
    order: 3,
    col_span: 12,
    row_span: 1,
    visible: true,
    collapsed: false,
    protected: false,
    options: {},
  },
  {
    id: "brain_stats",
    label: "Second brain & vault",
    region: "right_rail",
    order: 4,
    col_span: 12,
    row_span: 2,
    visible: true,
    collapsed: false,
    protected: false,
    options: {},
  },
  {
    id: "budget",
    label: "Daily Cloud Limit",
    region: "right_rail",
    order: 5,
    col_span: 12,
    row_span: 1,
    visible: true,
    collapsed: false,
    protected: false,
    options: {},
  },
  {
    id: "voice_stats",
    label: "Voice",
    region: "right_rail",
    order: 6,
    col_span: 12,
    row_span: 1,
    visible: true,
    collapsed: false,
    protected: false,
    options: {},
  },
]);

const CARD_BY_ID = new Map(CARD_REGISTRY.map((card) => [card.id, card]));

function defaultCard(id) {
  const card = CARD_BY_ID.get(id);
  return card
    ? {
        ...card,
        options: { ...card.options },
      }
    : null;
}

/**
 * Build a card row from the registry defaults, overridden by `patch`, with
 * only the fields a layout document may carry. Exported for the H2 editor and
 * for tests; the sanitizer below is the only thing that touches untrusted data.
 */
export function cardRow(id, patch = {}) {
  const base = defaultCard(id);
  if (!base) return null;
  const row = {
    id,
    region: REGIONS.includes(patch.region) ? patch.region : base.region,
    order: intIn(patch.order, 0, 50, base.order),
    col_span: intIn(patch.col_span, 1, 12, base.col_span),
    row_span: intIn(patch.row_span, 1, 4, base.row_span),
    visible: boolOf(patch.visible, base.visible),
    collapsed: boolOf(patch.collapsed, base.collapsed),
    options: cleanOptions(patch.options, base.options),
  };
  if (base.protected) row.visible = true;
  return row;
}

function intIn(value, lo, hi, fallback) {
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isInteger(n) || n < lo || n > hi) return fallback;
  return n;
}

function boolOf(value, fallback) {
  return typeof value === "boolean" ? value : fallback;
}

function cleanOptions(value, fallback = {}) {
  const out = {};
  if (value && typeof value === "object" && !Array.isArray(value)) {
    if (typeof value.tab === "string" && STAGE_TABS.includes(value.tab)) {
      out.tab = value.tab;
    }
  }
  if (!("tab" in out) && fallback && typeof fallback.tab === "string"
      && STAGE_TABS.includes(fallback.tab)) {
    out.tab = fallback.tab;
  }
  return out;
}

function textOf(value, max, fallback = "") {
  if (typeof value !== "string") return fallback;
  const trimmed = value.trim().replace(/\s+/g, " ");
  return trimmed ? trimmed.slice(0, max) : fallback;
}

const PRESET_NOTE = {
  cockpit: {
    label: "Cockpit",
    glyph: "\u229e",
    blurb:
      "The everyday deck: the conversation and the ask box at the centre, "
      + "with the waiting count and today's reminders in one narrow column - "
      + "the calendar, telemetry and the other system cards folded away.",
  },
  studio: {
    label: "Studio",
    glyph: "\u25eb",
    blurb:
      "Side-by-side deep work: a slim left dock, half the window for the "
      + "conversation, and the stage inspector beside it.",
  },
  ambient: {
    label: "Ambient",
    glyph: "\u25ce",
    blurb:
      "Voice-first: one large core, the latest exchange, floating status pills "
      + "and a centred box - no side rails.",
  },
  quiet: {
    label: "Quiet",
    glyph: "\u25a2",
    blurb:
      "Quiet chat: one centred column for reading and writing, with approvals "
      + "above it and no side cards.",
  },
  telemetry: {
    label: "Telemetry & Ops",
    glyph: "\u25a4",
    blurb:
      "The engineering view: the speed and GPU board in the right column, "
      + "beside a compact conversation and no second approval card.",
  },
  second_brain: {
    label: "Second Brain & Planner",
    glyph: "\u25c8",
    blurb:
      "Command center: the conversation and the Galaxy in the middle, with "
      + "three cards beside it - waiting, today's reminders, memory counts.",
  },
  minimal: {
    label: "Minimal",
    glyph: "\u25aa",
    blurb: "One compact column for a corner or a narrow half-monitor.",
  },
};

/**
 * EACH PRESET'S COMPOSITION (Wave 15, 2026-11-09). The first/second/gone
 * columns of the redesign spec's section 1.2 table, as data:
 *
 *   cockpit      Just Talk - the conversation and the ask box at the centre;
 *                the right column holds the waiting count and the page's today
 *                panel (2). The calendar, last-turn telemetry, abilities,
 *                budget, memory counts and voice meter are OFF. Its left rail
 *                is NOT on the glass - the page draws `cockpit` as two
 *                columns from PRESET_ATTR - but the rail's three cards stay
 *                present and visible so its drawer is not empty; they are no
 *                one's DEFAULT navigation any more.
 *   second_brain Command Center (the owner's layout) - Talk + Galaxy on the
 *                stage; the right column is capped at three: waiting,
 *                second-brain counts and the page's today panel. Last-turn
 *                telemetry, abilities, budget, voice meter and the calendar
 *                are OFF.
 *   quiet        Quiet Desk - one centred column; every side-rail card is OFF,
 *                including the waiting count.
 *   telemetry    System Monitor - the speed/GPU board is the only right-rail
 *                card, and the duplicate right-rail approval card, abilities,
 *                budget, memory counts and voice meter are OFF.
 *   studio       Custom Grid - nothing is forced OFF: every card is present
 *                and visible, in the default three-column order, so the owner's
 *                own arrangement is the only thing that hides anything.
 *   ambient      Face Only and minimal Mini View - every ordinary card is OFF;
 *                only the protected cards (and the face/composer the shell
 *                draws) remain, plus the page's return pill.
 *
 * EVERY MOVABLE CARD IS NAMED IN EVERY PRESET, even when it is off, on
 * purpose: a card a document does not name is re-added at its registry
 * defaults (visible) by hud-edit.js's `withRegistryCards`, so an omitted card
 * would quietly come back on the glass. `visible: false` is the only honest
 * way to say "this layout does not show it".
 */
function cardsFor(presetId) {
  const rows = {
    cockpit: [
      ["emergency_stop", {}],
      ["nav", {}],
      ["lanes", {}],
      ["systems", {}],
      ["bar_launcher", {}],
      ["approvals", {}],
      ["voice_controls", {}],
      ["conversation", {}],
      ["composer", {}],
      ["calendar", { visible: false }],
      ["waiting", { order: 0 }],
      ["telemetry", { visible: false }],
      ["tools", { visible: false }],
      ["brain_stats", { visible: false }],
      ["budget", { visible: false }],
      ["voice_stats", { visible: false }],
    ],
    studio: [
      ["emergency_stop", {}],
      ["nav", { collapsed: true }],
      ["lanes", {}],
      ["systems", {}],
      ["bar_launcher", {}],
      ["approvals", {}],
      ["voice_controls", {}],
      ["conversation", { col_span: 6, row_span: 4 }],
      ["composer", { col_span: 6 }],
      ["galaxy", { visible: true, col_span: 6, row_span: 4 }],
      ["reminders", { visible: true, col_span: 6, row_span: 4 }],
      ["memory", { visible: true, col_span: 6, row_span: 4 }],
      ["calendar", {}],
      ["waiting", {}],
      ["telemetry", {}],
      ["tools", {}],
      ["brain_stats", {}],
      ["budget", {}],
      ["voice_stats", {}],
    ],
    ambient: [
      ["emergency_stop", {}],
      ["bar_launcher", { collapsed: true }],
      ["approvals", { collapsed: true }],
      ["voice_controls", {}],
      ["conversation", { col_span: 12, row_span: 4 }],
      ["composer", {}],
      ["calendar", { visible: false }],
      ["waiting", { visible: false }],
      ["telemetry", { visible: false }],
      ["tools", { visible: false }],
      ["brain_stats", { visible: false }],
      ["budget", { visible: false }],
      ["voice_stats", { visible: false }],
      ["nav", { visible: false }],
      ["lanes", { visible: false }],
      ["systems", { visible: false }],
    ],
    quiet: [
      ["emergency_stop", {}],
      ["bar_launcher", { collapsed: true }],
      ["approvals", {}],
      ["voice_controls", {}],
      ["conversation", { col_span: 12, row_span: 4 }],
      ["composer", {}],
      ["calendar", { visible: false }],
      ["waiting", { visible: false }],
      ["nav", { visible: false }],
      ["lanes", { visible: false }],
      ["systems", { visible: false }],
      ["telemetry", { visible: false }],
      ["tools", { visible: false }],
      ["brain_stats", { visible: false }],
      ["budget", { visible: false }],
      ["voice_stats", { visible: false }],
    ],
    telemetry: [
      ["emergency_stop", {}],
      ["nav", {}],
      ["lanes", {}],
      ["systems", {}],
      ["bar_launcher", {}],
      ["approvals", {}],
      ["voice_controls", {}],
      ["conversation", {}],
      ["composer", {}],
      ["calendar", { visible: false }],
      ["waiting", { visible: false }],
      ["telemetry", { order: 0, col_span: 12, row_span: 4 }],
      ["tools", { visible: false }],
      ["budget", { visible: false }],
      ["voice_stats", { visible: false }],
      ["brain_stats", { visible: false }],
    ],
    second_brain: [
      ["emergency_stop", {}],
      ["nav", {}],
      ["lanes", {}],
      ["systems", {}],
      ["bar_launcher", {}],
      ["approvals", {}],
      ["voice_controls", {}],
      ["conversation", {}],
      ["composer", {}],
      ["galaxy", { visible: true, col_span: 12, row_span: 4 }],
      ["reminders", { visible: true, col_span: 6, row_span: 4 }],
      ["memory", { visible: true, col_span: 6, row_span: 4 }],
      ["calendar", { visible: false }],
      ["waiting", { order: 0 }],
      ["brain_stats", { order: 1, col_span: 12, row_span: 2 }],
      ["telemetry", { visible: false }],
      ["tools", { visible: false }],
      ["budget", { visible: false }],
      ["voice_stats", { visible: false }],
    ],
    minimal: [
      ["emergency_stop", {}],
      ["bar_launcher", { collapsed: true }],
      ["approvals", { collapsed: true }],
      ["voice_controls", {}],
      ["conversation", { col_span: 12, row_span: 4 }],
      ["composer", {}],
      ["nav", { visible: false }],
      ["lanes", { visible: false }],
      ["systems", { visible: false }],
      ["calendar", { visible: false }],
      ["waiting", { visible: false }],
      ["telemetry", { visible: false }],
      ["tools", { visible: false }],
      ["brain_stats", { visible: false }],
      ["budget", { visible: false }],
      ["voice_stats", { visible: false }],
    ],
  }[presetId];
  return rows.map(([id, patch]) => cardRow(id, patch)).filter(Boolean);
}

const PRESET_FACTS = {
  // TWO-COLUMN COCKPIT (Wave 15, spec §1.2 "Just Talk": "Remove Left
  // Sidebar"). The shell stays `three-column` because Command Center
  // (`second_brain`) is the SAME shell and keeps its sidebar: the two layouts
  // are told apart by PAGE CSS through `PRESET_ATTR` (the attribute below),
  // which the page now writes. For `cockpit` the page draws #shell as two
  // columns - stage + the 248px right rail - and the left rail is its
  // off-canvas drawer, opened by the header's "☰ Controls" toggle (the same
  // drawer, the same Escape, that `center-core`/`single-stage-bento` use).
  // So the wall of rail symbols is not DEFAULT navigation any more, while
  // every door it holds (Presets, Faces, Calendar, Live, Brain, Galaxy
  // options) is still one click away. In Edit HUD the two-column rule is
  // switched OFF (`body:not([data-hud-edit="on"])`), so editing still shows
  // the real three-column arrangement the document describes.
  //
  // The alternative - changing this value to `two-column-right` - would give
  // the same two columns but would take the whole shell machinery with it
  // (the shell-keyed #reactor sizes, the drawer logic and every
  // `data-hud-shell` pin), and it would draw the rail as a drawer whether or
  // not the page's preset attribute exists. The page's shape is the page's
  // business: the model says what the layout IS, PRESET_ATTR lets the
  // stylesheet speak about one layout.
  cockpit: { shell_template: "three-column", density: "comfortable", default_stage_tab: "talk" },
  studio: { shell_template: "split-stage", density: "comfortable", default_stage_tab: "talk" },
  ambient: { shell_template: "center-core", density: "spacious", default_stage_tab: "talk" },
  quiet: { shell_template: "two-column-left", density: "comfortable", default_stage_tab: "talk" },
  telemetry: { shell_template: "three-column", density: "compact", default_stage_tab: "telemetry" },
  second_brain: { shell_template: "three-column", density: "comfortable", default_stage_tab: "galaxy" },
  minimal: { shell_template: "single-stage-bento", density: "compact", default_stage_tab: "talk" },
};

/** Build one preset's complete layout document (fresh objects, never shared). */
function buildPreset(presetId) {
  const note = PRESET_NOTE[presetId];
  const facts = PRESET_FACTS[presetId];
  return {
    version: LAYOUT_VERSION,
    id: presetId,
    name: note.label,
    base_preset: presetId,
    shell_template: facts.shell_template,
    density: facts.density,
    default_stage_tab: facts.default_stage_tab,
    cards: sortCards(cardsFor(presetId)),
    user_presets: [],
    updated_at: 0,
  };
}

/** The one canonical card order: region first, then order, then id. */
function sortCards(cards) {
  return cards.slice().sort((a, b) => REGIONS.indexOf(a.region) - REGIONS.indexOf(b.region)
    || a.order - b.order || a.id.localeCompare(b.id));
}

/** The seven built-in presets, in the order the pickers draw them. */
export const PRESETS = Object.freeze([
  buildPreset("cockpit"),
  buildPreset("studio"),
  buildPreset("ambient"),
  buildPreset("quiet"),
  buildPreset("telemetry"),
  buildPreset("second_brain"),
  buildPreset("minimal"),
]);

/** The default preset, first in the list (fresh installs get this one). */
export const DEFAULT_PRESET_ID = PRESETS[0].id;

const PRESET_BY_ID = new Map(PRESETS.map((preset) => [preset.id, preset]));

/**
 * Old names the store may still hold, and the id each one now means. "focus"
 * was H1's layout name before the 2026-10-22 coherence slice renamed it
 * "quiet"; a saved layout carrying it is migrated silently, never dropped.
 */
export const PRESET_ALIASES = Object.freeze({ focus: "quiet" });

function canonicalPresetId(presetId) {
  const key = typeof presetId === "string" ? presetId : "";
  return PRESET_ALIASES[key] || key;
}

/** The label/blurb/glyph for one preset id, or null. Old ids are accepted. */
export function presetInfo(presetId) {
  const id = canonicalPresetId(presetId);
  if (!PRESET_BY_ID.has(id)) return null;
  return {
    id,
    label: PRESET_NOTE[id].label,
    blurb: PRESET_NOTE[id].blurb,
    glyph: PRESET_NOTE[id].glyph,
  };
}

/** A fresh, complete layout document for a built-in preset; unknown = cockpit. */
export function presetLayout(presetId) {
  const key = canonicalPresetId(presetId);
  const id = PRESET_BY_ID.has(key) ? key : DEFAULT_PRESET_ID;
  return normalizeLayout(buildPreset(id));
}

const PENDING_TABS = new Set(STAGE_TABS);

/**
 * The layout a document means. CLOSED-WORLD: only known cards, regions and
 * tokens survive; unknown keys are dropped (never copied through), `x`/`y` are
 * ignored, the four protected cards are forced visible, and a protected card
 * missing from the document is put back where the registry says it goes.
 *
 * A wrong or missing version is not repaired field by field: it is replaced by
 * the default preset. The alternative - guessing what an older/newer document
 * meant - is how a layout silently becomes a different one.
 */
/**
 * The cards a document means: known ids only, unique, the four protected cards
 * always present and visible, canonical region/order order. Shared by the
 * active document and every saved user layout, so the two can never validate
 * differently.
 */
function normalizedCards(rawCards) {
  const seen = new Set();
  const cards = [];
  for (const entry of Array.isArray(rawCards) ? rawCards : []) {
    if (!entry || typeof entry !== "object" || Array.isArray(entry)) continue;
    const id = textOf(entry.id, 40);
    if (!CARD_BY_ID.has(id) || seen.has(id)) continue;
    seen.add(id);
    cards.push(cardRow(id, entry));
  }
  // A protected card is never absent and never hidden, whatever the document
  // said. The rest may be absent: a preset that does not use a card simply
  // does not include it.
  for (const id of PROTECTED_IDS) {
    if (!seen.has(id)) {
      cards.push(cardRow(id, {}));
      seen.add(id);
    } else {
      const card = cards.find((entry) => entry.id === id);
      card.visible = true;
    }
  }
  // Stable region/order order: the renderer and the tests both read this, and
  // a document cannot smuggle in an order that puts a region's cards in
  // arbitrary array order.
  return sortCards(cards);
}

/** One saved user layout, or null when the entry cannot be read safely. */
function normalizedUserPreset(entry) {
  if (!entry || typeof entry !== "object" || Array.isArray(entry)) return null;
  const baseKey = canonicalPresetId(entry.base_preset);
  if (!PRESET_BY_ID.has(baseKey)) return null;
  const id = textOf(entry.id, 40);
  if (!USER_ID_RE.test(id) || PRESET_BY_ID.has(id)) return null;
  const name = textOf(entry.name, USER_NAME_MAX);
  if (!name) return null;
  const skeleton = buildPreset(baseKey);
  return {
    id,
    name,
    base_preset: baseKey,
    shell_template: SHELL_TEMPLATES.includes(entry.shell_template)
      ? entry.shell_template
      : skeleton.shell_template,
    density: DENSITIES.includes(entry.density) ? entry.density : skeleton.density,
    default_stage_tab: PENDING_TABS.has(entry.default_stage_tab)
      ? entry.default_stage_tab
      : skeleton.default_stage_tab,
    cards: normalizedCards(entry.cards),
  };
}

/** The saved user-layout library from a document (bounded, de-duplicated). */
export function userLayouts(doc) {
  const out = [];
  const ids = new Set();
  const raw = doc && typeof doc === "object" && Array.isArray(doc.user_presets)
    ? doc.user_presets : [];
  for (const entry of raw) {
    if (out.length >= MAX_USER_PRESETS) break;
    const clean = normalizedUserPreset(entry);
    if (!clean || ids.has(clean.id)) continue;
    ids.add(clean.id);
    out.push(clean);
  }
  return out;
}

/** Whether the document is one of the owner's own saved layouts. */
export function isUserLayout(doc) {
  const id = doc && typeof doc === "object" ? doc.id : null;
  return typeof id === "string" && USER_ID_RE.test(id)
    && userLayouts(doc).some((entry) => entry.id === id);
}

export function normalizeLayout(doc) {
  if (!doc || typeof doc !== "object" || Array.isArray(doc)) {
    return presetLayout(DEFAULT_PRESET_ID);
  }
  if (doc.version !== LAYOUT_VERSION) {
    return presetLayout(DEFAULT_PRESET_ID);
  }
  const baseKey = canonicalPresetId(doc.base_preset);
  const idKey = canonicalPresetId(doc.id);
  const baseId = PRESET_BY_ID.has(baseKey)
    ? baseKey
    : PRESET_BY_ID.has(idKey)
      ? idKey
      : DEFAULT_PRESET_ID;
  const skeleton = buildPreset(baseId);
  const cards = normalizedCards(doc.cards);
  const library = userLayouts(doc);
  const wantedId = textOf(doc.id, 60);
  const activeUser = USER_ID_RE.test(wantedId)
    ? library.find((entry) => entry.id === wantedId) || null
    : null;
  const builtInId = PRESET_BY_ID.has(idKey) ? idKey : null;
  // A saved old name ("Focus") follows its preset to the new name ("Quiet");
  // a custom layout's own name is never touched.
  let name = (PRESET_ALIASES[doc.base_preset] || PRESET_ALIASES[doc.id])
    && String(doc.name || "").trim().toLowerCase() === "focus"
    ? skeleton.name
    : textOf(doc.name, USER_NAME_MAX) || skeleton.name;
  let id = builtInId || wantedId || skeleton.id;
  if (activeUser) {
    id = activeUser.id;
    name = textOf(doc.name, USER_NAME_MAX) || activeUser.name;
  } else if (USER_ID_RE.test(wantedId)) {
    // A custom id with no library entry cannot be served: fall back to its
    // base built-in rather than render a layout the list does not contain.
    id = baseId;
    name = skeleton.name;
  }
  return {
    version: LAYOUT_VERSION,
    id,
    name,
    base_preset: baseId,
    shell_template: SHELL_TEMPLATES.includes(doc.shell_template)
      ? doc.shell_template
      : skeleton.shell_template,
    density: DENSITIES.includes(doc.density) ? doc.density : skeleton.density,
    default_stage_tab: PENDING_TABS.has(doc.default_stage_tab)
      ? doc.default_stage_tab
      : skeleton.default_stage_tab,
    cards,
    user_presets: library,
    updated_at: intIn(doc.updated_at, 0, 2 ** 52, 0),
  };
}

/** Parse layout JSON text. Returns a normalized document or null. */
export function parseLayoutText(text) {
  if (typeof text !== "string") return null;
  let value;
  try {
    value = JSON.parse(text);
  } catch {
    return null;
  }
  if (typeof value === "string") return migrateLegacyLayout(value);
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return normalizeLayout(value);
}

/**
 * The old `jarvis.hud.layout` localStorage value, carried into the new model.
 * `cockpit`/`studio`/`ambient` keep their meaning; anything else (and nothing
 * stored at all) is the default. Case and surrounding spaces are tolerated
 * because the old picker stored the trimmed value but a hand edit may not.
 */
export function migrateLegacyLayout(value) {
  const legacy = typeof value === "string" ? value.trim().toLowerCase() : "";
  return presetLayout(PRESET_BY_ID.has(canonicalPresetId(legacy)) ? legacy : DEFAULT_PRESET_ID);
}

/**
 * The state the renderer actually uses for one card. `approvals` is shown
 * expanded the moment a card waits, and folds back the moment none does - a
 * transient view state (ruling 7), never written into the saved layout.
 */
export function effectiveCollapsed(card, pendingCount = 0) {
  if (!card || typeof card !== "object") return false;
  if (card.id === "approvals" && Number(pendingCount) > 0) return false;
  return Boolean(card.collapsed);
}

/**
 * The card ids a layout actually draws in one region, in the order the rail
 * paints them. The page and the tests read the SAME answer here, so "the right
 * column is capped at three" is one number from one place (Wave 15).
 */
export function visibleCards(layout, region) {
  const doc = normalizeLayout(layout);
  return doc.cards
    .filter((card) => card.region === region && card.visible)
    .map((card) => card.id);
}

/**
 * The right column as a count: the layout cards on the glass plus the one
 * page-owned panel (`FIXED_RAIL_PANELS`) that fills a slot there when the
 * layout's shell draws the column statically. This is the number the redesign
 * spec's caps are about - `cockpit` 2, `second_brain` 3 - so the page and the
 * tests can assert the SAME arithmetic rather than counting two different
 * things. A drawer shell (or `split-stage`, whose rail is a zero-width overlay)
 * counts no fixed panel, because none of it is on the glass.
 */
export function rightColumn(layout) {
  const doc = normalizeLayout(layout);
  const cards = doc.cards
    .filter((card) => card.region === "right_rail" && card.visible)
    .sort((a, b) => a.order - b.order || a.id.localeCompare(b.id))
    .map((card) => card.id);
  const staticRail = STATIC_RIGHT_RAIL_SHELLS.includes(doc.shell_template);
  const fixed = staticRail ? FIXED_RAIL_PANELS.map((panel) => panel.id) : [];
  return Object.freeze({
    cards: Object.freeze(cards),
    fixed: Object.freeze(fixed),
    total: cards.length + fixed.length,
  });
}

/**
 * The return pill a layout must show, or null. `base_preset` is what counts, so
 * the owner's own saved copy of Face Only keeps its way back; every other
 * layout (and every unknown document, which normalizes to the default) answers
 * null. The page draws `RETURN_PILL`'s markup while this answers non-null and
 * chooses `target_preset` when it is clicked.
 */
export function returnPillFor(layout) {
  const doc = normalizeLayout(layout);
  if (!RETURN_PILL_LAYOUTS.includes(doc.base_preset)) return null;
  return { ...RETURN_PILL };
}

/** One line saying which preset a layout came from, for the Settings card. */
export function describeLayout(layout) {
  const doc = normalizeLayout(layout);
  const info = presetInfo(doc.base_preset);
  return info
    ? `${info.label}: ${info.blurb}`
    : `${doc.name}: a layout saved on this PC.`;
}
