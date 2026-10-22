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
 * The shells a preset may choose between. H1 stores the value and keeps the
 * current three-way `data-hud-layout` look working; H2 draws the region grid
 * itself. The first three names are the existing layouts' own shells.
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

/** The themes the rest of the desktop already ships, plus "system". */
export const THEMES = Object.freeze(["system", "deep-space", "paper", "high-contrast"]);

/** The stage tabs a layout can open on (the page's own four plus Talk). */
export const STAGE_TABS = Object.freeze(["talk", "galaxy", "today", "memory", "telemetry"]);

/** The four cards no layout may hide (ruling 25). */
export const PROTECTED_IDS = Object.freeze([
  "approvals",
  "emergency_stop",
  "voice_controls",
  "bar_launcher",
]);

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
    label: "Brain switcher",
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
    label: "System lights",
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
    label: "Reminders and Today",
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
    id: "waiting",
    label: "Cards waiting",
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
    id: "telemetry",
    label: "Last answer telemetry",
    region: "right_rail",
    order: 1,
    col_span: 12,
    row_span: 2,
    visible: true,
    collapsed: false,
    protected: false,
    options: {},
  },
  {
    id: "tools",
    label: "Tools used",
    region: "right_rail",
    order: 2,
    col_span: 12,
    row_span: 1,
    visible: true,
    collapsed: false,
    protected: false,
    options: {},
  },
  {
    id: "brain_stats",
    label: "Memory and documents",
    region: "right_rail",
    order: 3,
    col_span: 12,
    row_span: 2,
    visible: true,
    collapsed: false,
    protected: false,
    options: {},
  },
  {
    id: "budget",
    label: "Rate budget",
    region: "right_rail",
    order: 4,
    col_span: 12,
    row_span: 1,
    visible: true,
    collapsed: false,
    protected: false,
    options: {},
  },
  {
    id: "voice_stats",
    label: "Voice readiness",
    region: "right_rail",
    order: 5,
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
      "The default three-column deck: navigation on the left, conversation in "
      + "the middle, and the waiting cards, telemetry and memory on the right.",
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
  focus: {
    label: "Focus",
    glyph: "\u25a2",
    blurb: "Quiet chat: the conversation and the waiting cards, nothing else.",
  },
  telemetry: {
    label: "Telemetry & Ops",
    glyph: "\u25a4",
    blurb:
      "The engineering view: live telemetry, tools, budget and voice readiness "
      + "beside the conversation.",
  },
  second_brain: {
    label: "Second Brain & Planner",
    glyph: "\u25c8",
    blurb:
      "Knowledge and planning: the Galaxy and Memory stage prominent, with "
      + "Reminders and the memory counts close by.",
  },
  minimal: {
    label: "Minimal",
    glyph: "\u25aa",
    blurb: "One compact column for a corner or a narrow half-monitor.",
  },
};

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
      ["waiting", {}],
      ["telemetry", {}],
      ["tools", {}],
      ["brain_stats", {}],
      ["budget", {}],
      ["voice_stats", {}],
    ],
    studio: [
      ["emergency_stop", {}],
      ["nav", { collapsed: true }],
      ["lanes", { collapsed: true }],
      ["systems", {}],
      ["bar_launcher", {}],
      ["approvals", {}],
      ["voice_controls", {}],
      ["conversation", { col_span: 6, row_span: 4 }],
      ["composer", { col_span: 6 }],
      ["galaxy", { visible: true, col_span: 6, row_span: 4 }],
      ["reminders", { visible: true, col_span: 6, row_span: 4 }],
      ["memory", { visible: true, col_span: 6, row_span: 4 }],
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
    focus: [
      ["emergency_stop", {}],
      ["bar_launcher", { collapsed: true }],
      ["approvals", {}],
      ["voice_controls", {}],
      ["conversation", { col_span: 12, row_span: 4 }],
      ["composer", {}],
      ["waiting", {}],
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
      ["waiting", {}],
      ["telemetry", { col_span: 12, row_span: 4 }],
      ["tools", {}],
      ["budget", {}],
      ["voice_stats", {}],
      ["brain_stats", {}],
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
      ["waiting", {}],
      ["brain_stats", { col_span: 12, row_span: 4 }],
      ["telemetry", {}],
      ["tools", {}],
      ["budget", {}],
      ["voice_stats", {}],
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
  cockpit: { shell_template: "three-column", theme: "system", density: "comfortable", default_stage_tab: "talk" },
  studio: { shell_template: "split-stage", theme: "system", density: "comfortable", default_stage_tab: "talk" },
  ambient: { shell_template: "center-core", theme: "system", density: "spacious", default_stage_tab: "talk" },
  focus: { shell_template: "two-column-left", theme: "paper", density: "comfortable", default_stage_tab: "talk" },
  telemetry: { shell_template: "three-column", theme: "deep-space", density: "compact", default_stage_tab: "telemetry" },
  second_brain: { shell_template: "three-column", theme: "system", density: "comfortable", default_stage_tab: "galaxy" },
  minimal: { shell_template: "single-stage-bento", theme: "system", density: "compact", default_stage_tab: "talk" },
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
    theme: facts.theme,
    density: facts.density,
    default_stage_tab: facts.default_stage_tab,
    cards: sortCards(cardsFor(presetId)),
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
  buildPreset("focus"),
  buildPreset("telemetry"),
  buildPreset("second_brain"),
  buildPreset("minimal"),
]);

/** The default preset, first in the list (fresh installs get this one). */
export const DEFAULT_PRESET_ID = PRESETS[0].id;

const PRESET_BY_ID = new Map(PRESETS.map((preset) => [preset.id, preset]));

/** The label/blurb/glyph for one preset id, or null. */
export function presetInfo(presetId) {
  if (!PRESET_BY_ID.has(presetId)) return null;
  return {
    id: presetId,
    label: PRESET_NOTE[presetId].label,
    blurb: PRESET_NOTE[presetId].blurb,
    glyph: PRESET_NOTE[presetId].glyph,
  };
}

/** A fresh, complete layout document for a built-in preset; unknown = cockpit. */
export function presetLayout(presetId) {
  const id = PRESET_BY_ID.has(presetId) ? presetId : DEFAULT_PRESET_ID;
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
export function normalizeLayout(doc) {
  if (!doc || typeof doc !== "object" || Array.isArray(doc)) {
    return presetLayout(DEFAULT_PRESET_ID);
  }
  if (doc.version !== LAYOUT_VERSION) {
    return presetLayout(DEFAULT_PRESET_ID);
  }
  const baseId = PRESET_BY_ID.has(doc.base_preset)
    ? doc.base_preset
    : PRESET_BY_ID.has(doc.id)
      ? doc.id
      : DEFAULT_PRESET_ID;
  const skeleton = buildPreset(baseId);
  const rawCards = Array.isArray(doc.cards) ? doc.cards : [];
  const seen = new Set();
  const cards = [];
  for (const entry of rawCards) {
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
  cards.splice(0, cards.length, ...sortCards(cards));
  return {
    version: LAYOUT_VERSION,
    id: textOf(doc.id, 60) || skeleton.id,
    name: textOf(doc.name, 60) || skeleton.name,
    base_preset: baseId,
    shell_template: SHELL_TEMPLATES.includes(doc.shell_template)
      ? doc.shell_template
      : skeleton.shell_template,
    theme: THEMES.includes(doc.theme) ? doc.theme : skeleton.theme,
    density: DENSITIES.includes(doc.density) ? doc.density : skeleton.density,
    default_stage_tab: PENDING_TABS.has(doc.default_stage_tab)
      ? doc.default_stage_tab
      : skeleton.default_stage_tab,
    cards,
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
  return presetLayout(PRESET_BY_ID.has(legacy) ? legacy : DEFAULT_PRESET_ID);
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

/** One line saying which preset a layout came from, for the Settings card. */
export function describeLayout(layout) {
  const doc = normalizeLayout(layout);
  const info = presetInfo(doc.base_preset);
  return info
    ? `${info.label}: ${info.blurb}`
    : `${doc.name}: a layout saved on this PC.`;
}
