/**
 * hud-edit.js - "Edit HUD" mode for the desktop HUD (H2 of the editable-HUD
 * design, 2026-10-21; rulings 23-27 in
 * `rulings_r1_r7_reminders_and_editable_hud_2026_10_21.md`).
 *
 * WHAT IT IS. The H1 module (`hud-layout.js`) owns the DATA - the card
 * registry, the seven presets, the closed-world normalizer, the protected-card
 * rule. This module owns the EDITOR: the pure reducer every input calls, the
 * pointer-event drag, and the card toolbars/region rendering. It is imported
 * by the HUD page as an external module (the page's inline-script count does
 * not change and its CSP stays as it was).
 *
 * THE ONE RULE. Drag, click buttons, keyboard shortcuts and undo all call the
 * SAME `applyAction`. There is no second mutation path, which is what makes
 * the WCAG 2.2 SC 2.5.7 claim mechanical instead of a promise. Every returned
 * layout has been through H1's `normalizeLayout`, so the protected cards are
 * present and visible, orders are canonical, and save-then-load cannot rewrite
 * the result.
 *
 * WHAT H2 EDITS (honest scope, said in the page's own words too). The cards
 * whose DOM is a self-contained section - the six Bento inspector cards, the
 * three left-rail panels, the approvals queue and (when the shell creates it)
 * the Jarvis-bar button - can move between three regions (left rail, stage
 * top, right rail), resize S/M/L/Tall, collapse and (except protected) hide.
 * The MAIN STAGE (conversation, the Galaxy view, the composer and the stage
 * tabs) is the stage: its registry rows still round-trip, but H2 does not
 * reparent the live stage, so its toolbar explains that instead of pretending
 * a move happened. Stage-card editing is H3/H4 territory.
 */

import {
  CARD_REGISTRY,
  REGIONS,
  PRESETS,
  cardRow,
  describeLayout,
  effectiveCollapsed,
  isUserLayout,
  normalizeLayout,
  presetInfo,
  presetLayout,
  userLayouts,
} from "./hud-layout.js";
import { loadLayout, saveLayout } from "./hud-layout-store.js";
import { ensureCustomCopy } from "./hud-presets.js";

/** The size buttons, as the ruling asks: Small / Medium / Wide / Tall. */
export const SIZES = Object.freeze([
  { key: "S", label: "Small", short: "S", col_span: 4, row_span: 1 },
  { key: "M", label: "Medium", short: "M", col_span: 6, row_span: 1 },
  { key: "L", label: "Wide", short: "L", col_span: 12, row_span: 1 },
  { key: "T", label: "Tall", short: "T", col_span: 12, row_span: 2 },
]);
export const SIZE_BY_KEY = Object.freeze(
  Object.fromEntries(SIZES.map((size) => [size.key, size])),
);

/** Human words for the five regions (the registry's own vocabulary). */
export const REGION_LABEL = Object.freeze({
  header: "Header",
  left_rail: "Left rail",
  stage_top: "Stage top",
  stage_main: "Stage",
  right_rail: "Right rail",
});

/** The regions H2 lets a panel card live in. */
export const EDIT_REGIONS = Object.freeze(["left_rail", "stage_top", "right_rail"]);

/**
 * The cards H2 can actually move: the ones whose DOM is a standalone section.
 * `approvals` is here (protected: it may move, it may never be hidden, and its
 * region is locked by the ruling). Everything else in the registry is FIXED:
 * the main stage, the composer, the Galaxy view, the header controls and any
 * card whose DOM does not exist on this page yet.
 */
export const MOVABLE_IDS = Object.freeze([
  "nav",
  "lanes",
  "systems",
  "bar_launcher",
  "approvals",
  "waiting",
  "telemetry",
  "tools",
  "brain_stats",
  "budget",
  "voice_stats",
]);

/** Card id -> the existing DOM element(s) that make up that card. */
export const CARD_DOM = Object.freeze({
  nav: ["#rail-nav"],
  lanes: ["#rail-lanes"],
  systems: ["#rail-systems"],
  bar_launcher: ["#hud-open-bar"],
  approvals: ["#approvals", "#initiative"],
  waiting: ["#rail-waiting"],
  telemetry: ["#rail-telemetry"],
  tools: ["#rail-tools"],
  brain_stats: ["#rail-memory"],
  budget: ["#rail-budget"],
  voice_stats: ["#rail-voice"],
});

/** Cards that H2 shows but deliberately does not reparent, with their reason. */
export const FIXED_IDS = Object.freeze({
  emergency_stop: "Stop everything is a fixed control in the header (Alt+Shift+X also works).",
  voice_controls: "The voice controls stay beside the composer.",
  conversation: "The conversation is the main stage.",
  composer: "The ask box is the main stage.",
  galaxy: "The Galaxy is the main stage's tab, not a panel card.",
  reminders: "Reminders and Today open in the main stage.",
  memory: "Memory opens in the main stage.",
});
export const FIXED_REASON = "This part of the HUD stays where it is.";

const REGION_SET = new Set(EDIT_REGIONS);
const MOVABLE_SET = new Set(MOVABLE_IDS);
const PROTECTED_SET = new Set(
  CARD_REGISTRY.filter((card) => card.protected).map((card) => card.id),
);
const CARD_BY_ID = new Map(CARD_REGISTRY.map((card) => [card.id, card]));

/* =========================================================================
 * 1. The pure reducer - ONE writer for every input
 * ========================================================================= */

function orderInRegion(cards, region) {
  return cards
    .filter((card) => card.region === region)
    .sort((a, b) => a.order - b.order || String(a.id).localeCompare(String(b.id)));
}

/** Re-number `order` contiguously 0..n-1 in each region (canonical order). */
function renumber(cards) {
  const out = [];
  for (const region of REGIONS) {
    orderInRegion(cards, region).forEach((card, index) => {
      out.push({ ...card, order: index });
    });
  }
  return out;
}

/**
 * One action -> `{ layout, changed, refused, note }`. Pure: never mutates
 * `layout`, always returns a document that is a fixed point of `normalizeLayout`.
 */
export function applyAction(layout, action, { pendingCount = 0 } = {}) {
  const base = normalizeLayout(layout);
  const act = action && typeof action === "object" ? action : {};
  const cards = base.cards.map((card) => ({ ...card, options: { ...card.options } }));
  const find = (id) => cards.find((card) => card.id === id);
  const say = (changed, note = "", refused = false) => {
    const doc = changed ? normalizeLayout(baseDocument(base, cards)) : base;
    if (changed) doc.updated_at = Math.floor(Date.now() / 1000);
    return { layout: doc, changed, refused, note };
  };
  const refuse = (note) => ({ layout: base, changed: false, refused: true, note });

  switch (act.type) {
    case "moveCard": {
      const card = find(act.id);
      if (!card) return refuse("That card is not in this layout.");
      if (!MOVABLE_SET.has(card.id)) return refuse(FIXED_REASON);
      if (!REGION_SET.has(act.region)) return refuse("That is not a region this editor can move a card to.");
      if (PROTECTED_SET.has(card.id)) {
        return refuse(`${CARD_BY_ID.get(card.id).label} always stays in ${REGION_LABEL[card.region]}.`);
      }
      if (card.region === act.region) {
        return { layout: base, changed: false, refused: false, note: `${CARD_BY_ID.get(card.id).label} is already in ${REGION_LABEL[act.region]}.` };
      }
      const target = orderInRegion(cards, act.region);
      const index = clampInt(act.index, 0, target.length, target.length);
      target.splice(index, 0, card);
      target.forEach((entry, at) => { entry.order = at; });
      card.region = act.region;
      const source = orderInRegion(cards, base.cards.find((c) => c.id === card.id).region)
        .filter((entry) => entry.id !== card.id);
      source.forEach((entry, at) => { entry.order = at; });
      return say(true, `${CARD_BY_ID.get(card.id).label} moved to ${REGION_LABEL[act.region]}.`);
    }
    case "reorderCard": {
      const card = find(act.id);
      if (!card) return refuse("That card is not in this layout.");
      if (!MOVABLE_SET.has(card.id)) return refuse(FIXED_REASON);
      const list = orderInRegion(cards, card.region);
      const at = list.findIndex((entry) => entry.id === card.id);
      const to = clampInt(at + clampInt(act.delta, -50, 50, 0), 0, list.length - 1, at);
      if (to === at) return { layout: base, changed: false, refused: false, note: "" };
      list.splice(to, 0, list.splice(at, 1)[0]);
      list.forEach((entry, index) => { entry.order = index; });
      return say(true, `${CARD_BY_ID.get(card.id).label} moved ${to < at ? "up" : "down"}.`);
    }
    case "resizeCard": {
      const card = find(act.id);
      if (!card) return refuse("That card is not in this layout.");
      if (!MOVABLE_SET.has(card.id)) return refuse(FIXED_REASON);
      const size = act.size
        ? SIZE_BY_KEY[act.size]
        : { col_span: act.col_span, row_span: act.row_span };
      if (!size) return refuse("That is not a size this editor offers.");
      const col = clampInt(size.col_span, 1, 12, card.col_span);
      const row = clampInt(size.row_span, 1, 4, card.row_span);
      if (col === card.col_span && row === card.row_span) {
        return { layout: base, changed: false, refused: false, note: "" };
      }
      card.col_span = col;
      card.row_span = row;
      const words = SIZES.find((entry) => entry.col_span === col && entry.row_span === row);
      return say(true, `${CARD_BY_ID.get(card.id).label} is now ${words ? words.label : `${col} wide`}.`);
    }
    case "toggleCollapsed": {
      const card = find(act.id);
      if (!card) return refuse("That card is not in this layout.");
      card.collapsed = act.collapsed === undefined ? !card.collapsed : Boolean(act.collapsed);
      const shown = effectiveCollapsed(card, pendingCount);
      return say(true, `${CARD_BY_ID.get(card.id).label} is ${shown ? "folded" : "open"}.`);
    }
    case "setVisible": {
      const card = find(act.id);
      if (!card) return refuse("That card is not in this layout.");
      const want = act.visible === undefined ? !card.visible : Boolean(act.visible);
      if (PROTECTED_SET.has(card.id) && !want) return refuse(`${CARD_BY_ID.get(card.id).label} can never be hidden.`);
      if (!MOVABLE_SET.has(card.id)) return refuse(FIXED_REASON);
      card.visible = want;
      return say(true, `${CARD_BY_ID.get(card.id).label} is ${want ? "shown" : "hidden"}.`);
    }
    case "resetToPreset": {
      const preset = PRESETS.find((entry) => entry.id === act.id);
      if (!preset) return refuse("That preset does not exist.");
      return { layout: presetLayout(preset.id), changed: true, refused: false, note: `Reset to ${presetInfo(preset.id).label}.` };
    }
    case "replaceLayout": {
      const doc = normalizeLayout(act.layout);
      return { layout: doc, changed: true, refused: false, note: act.note || "" };
    }
    default:
      return refuse("That is not an edit this HUD knows.");
  }
}

/** Rebuild a document from an edited card list (keeps every other field). */
function baseDocument(source, cards) {
  return {
    ...source,
    cards: renumber(cards),
    updated_at: Math.floor(Date.now() / 1000),
  };
}

function clampInt(value, lo, hi, fallback) {
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isInteger(n)) return fallback;
  return Math.min(hi, Math.max(lo, n));
}

/** Where a card of this size/region would sit, for tests and the toolbar. */
export function sizeKeyFor(card) {
  const found = SIZES.find(
    (size) => size.col_span === card.col_span && size.row_span === card.row_span,
  );
  return found ? found.key : null;
}

/* =========================================================================
 * 2. The editor: rendering, drag, toolbar, autosave, undo
 * ========================================================================= */

const SAVE_DEBOUNCE_MS = 400;
const UNDO_LIMIT = 50;

/**
 * Mount the editor on the live page. Returns a controller; the page's own
 * glue calls this once. Safe to call in a plain browser: without the shell
 * there is no save road, so the button hides itself (the tests that need it
 * stub the shell).
 */
export function mountHudEditor(options = {}) {
  const doc = options.document || globalThis.document;
  if (!doc) throw new Error("hud-edit needs a document");
  const store = options.store || { loadLayout, saveLayout };
  const shellPresent = typeof options.shellPresent === "boolean"
    ? options.shellPresent
    : Boolean(globalThis.__TAURI__ && globalThis.__TAURI__.core);
  let layout = null;
  let editing = false;
  let entrySnapshot = null;
  const undoStack = [];
  let saveTimer = null;
  let saving = false;
  let lastSavedAt = null;
  const cardShells = new Map();   // id -> shell element
  const regionEls = new Map();    // region -> element
  let dragState = null;
  let statusEl = null;
  let barEl = null;
  let badgeEl = null;

  const byId = (id) => doc.getElementById(id);
  const labelOf = (id) => (CARD_BY_ID.get(id) || { label: id }).label;
  const pendingCount = () => {
    try {
      const text = byId("appr-badge") ? byId("appr-badge").textContent : "";
      const n = parseInt(String(text).replace(/[^0-9]/g, ""), 10);
      return Number.isFinite(n) ? n : 0;
    } catch { return 0; }
  };

  function announce(words) {
    if (!statusEl) return;
    statusEl.textContent = words;
  }

  // ---------------------------------------------------------------- regions
  function ensureRegions() {
    if (regionEls.size) return;
    const shell = byId("shell");
    const left =
      (doc.querySelector(".rail.left") || null);
    const right = byId("rail-right");
    const stage = byId("stage");
    if (left) {
      const el = doc.createElement("div");
      el.className = "hud-region hud-region-left";
      el.setAttribute("data-hud-region", "left_rail");
      el.setAttribute("aria-label", REGION_LABEL.left_rail);
      left.insertBefore(el, byId("rail-nav"));
      regionEls.set("left_rail", el);
    }
    if (stage) {
      const el = doc.createElement("div");
      el.className = "hud-region hud-region-stage-top";
      el.setAttribute("data-hud-region", "stage_top");
      el.setAttribute("aria-label", REGION_LABEL.stage_top);
      stage.insertBefore(el, byId("banner") || stage.firstChild);
      regionEls.set("stage_top", el);
    }
    if (right) {
      const el = doc.createElement("div");
      el.className = "hud-region hud-region-right";
      el.setAttribute("data-hud-region", "right_rail");
      el.setAttribute("aria-label", REGION_LABEL.right_rail);
      right.insertBefore(el, byId("rail-close") ? byId("rail-close").nextSibling : right.firstChild);
      regionEls.set("right_rail", el);
    }
    if (!regionEls.size && shell) {
      // A very old page with no rails at all: one region so edit mode still
      // has somewhere honest to say it cannot move anything.
      const el = doc.createElement("div");
      el.className = "hud-region";
      el.setAttribute("data-hud-region", "right_rail");
      shell.appendChild(el);
      regionEls.set("right_rail", el);
    }
  }

  function makeShell(id) {
    const shell = doc.createElement("section");
    shell.className = "hud-card";
    shell.setAttribute("data-hud-card", id);
    shell.setAttribute("aria-label", labelOf(id));
    const head = doc.createElement("header");
    head.className = "hud-card-head";
    const handle = doc.createElement("button");
    handle.type = "button";
    handle.className = "hud-card-handle";
    handle.setAttribute("data-hud-card-handle", id);
    handle.setAttribute("aria-label", `Move ${labelOf(id)}. Use the arrow keys and buttons, or drag.`);
    handle.textContent = "\u2630";
    head.appendChild(handle);
    const title = doc.createElement("span");
    title.className = "hud-card-title";
    title.textContent = labelOf(id);
    head.appendChild(title);
    head.appendChild(buildToolbar(id));
    const body = doc.createElement("div");
    body.className = "hud-card-body";
    shell.appendChild(head);
    shell.appendChild(body);
    shell.addEventListener("keydown", (event) => onShellKey(event, id));
    cardShells.set(id, shell);
    // Move the real card nodes in ONCE; ids and listeners are not cloned.
    for (const selector of CARD_DOM[id] || []) {
      const node = doc.querySelector(selector);
      if (node) body.appendChild(node);
    }
    return shell;
  }

  function buildToolbar(id) {
    const wrap = doc.createElement("div");
    wrap.className = "hud-card-tools";
    wrap.setAttribute("role", "group");
    wrap.setAttribute("aria-label", `${labelOf(id)} layout controls`);
    const button = (command, text, title, extra = {}) => {
      const b = doc.createElement("button");
      b.type = "button";
      b.className = "hud-tool";
      b.setAttribute("data-hud-edit-command", command);
      b.setAttribute("data-hud-edit-card", id);
      b.textContent = text;
      b.title = title;
      b.setAttribute("aria-label", title);
      if (extra.disabled) {
        b.disabled = true;
        b.setAttribute("aria-disabled", "true");
      }
      if (extra.reason) b.setAttribute("title", `${title}\n${extra.reason}`);
      return b;
    };
    const protectedCard = PROTECTED_SET.has(id);
    const fixed = !MOVABLE_SET.has(id);
    wrap.appendChild(button("up", "\u2191", `Move ${labelOf(id)} up`, { disabled: fixed }));
    wrap.appendChild(button("down", "\u2193", `Move ${labelOf(id)} down`, { disabled: fixed }));
    // The direct region selector (ruling 27): a single-pointer alternative to
    // dragging across regions, and the words say which region is which.
    const regionWrap = doc.createElement("label");
    regionWrap.className = "hud-tool-select";
    regionWrap.textContent = "Move to";
    const select = doc.createElement("select");
    select.setAttribute("data-hud-edit-region", id);
    select.setAttribute("aria-label", `Move ${labelOf(id)} to another region`);
    for (const region of EDIT_REGIONS) {
      const option = doc.createElement("option");
      option.value = region;
      option.textContent = REGION_LABEL[region];
      select.appendChild(option);
    }
    select.disabled = fixed || protectedCard;
    if (protectedCard) select.title = `${labelOf(id)} always stays in ${REGION_LABEL[(CARD_BY_ID.get(id) || {}).region] || "its region"}.`;
    if (fixed) select.title = FIXED_IDS[id] || FIXED_REASON;
    regionWrap.appendChild(select);
    wrap.appendChild(regionWrap);
    // Size buttons S / M / L / T, each a real pressed button.
    const sizeWrap = doc.createElement("div");
    sizeWrap.className = "hud-tool-sizes";
    sizeWrap.setAttribute("role", "group");
    sizeWrap.setAttribute("aria-label", `${labelOf(id)} size`);
    for (const size of SIZES) {
      const b = button("size", size.short, `${labelOf(id)}: ${size.label}`, { disabled: fixed });
      b.setAttribute("data-hud-edit-size", size.key);
      sizeWrap.appendChild(b);
    }
    wrap.appendChild(sizeWrap);
    wrap.appendChild(button("collapse", "\u25be", `Fold ${labelOf(id)}`));
    const hide = button("hide", "\u2715", `Hide ${labelOf(id)}`, { disabled: fixed || protectedCard });
    if (protectedCard) hide.setAttribute("aria-description", `${labelOf(id)} can never be hidden.`);
    if (fixed) hide.setAttribute("title", `${FIXED_IDS[id] || FIXED_REASON}`);
    wrap.appendChild(hide);
    return wrap;
  }

  function ensureShells() {
    for (const card of layout.cards) {
      if (!MOVABLE_SET.has(card.id)) continue;
      if (cardShells.has(card.id)) continue;
      const shell = makeShell(card.id);
      const region = regionEls.get(EDIT_REGIONS.includes(card.region) ? card.region : "right_rail");
      if (region) region.appendChild(shell);
    }
    // The Jarvis-bar button is created by the shell bootstrap after this page
    // runs; catch it the first time we render after it appears.
    if (MOVABLE_SET.has("bar_launcher") && !cardShells.has("bar_launcher") && byId("hud-open-bar")) {
      const shell = makeShell("bar_launcher");
      const region = regionEls.get(
        (layout.cards.find((c) => c.id === "bar_launcher") || {}).region || "left_rail",
      );
      if (region) region.appendChild(shell);
    }
  }

  function render() {
    ensureRegions();
    ensureShells();
    if (!layout) return;
    const pending = pendingCount();
    const byRegion = new Map(EDIT_REGIONS.map((region) => [region, []]));
    for (const card of layout.cards) {
      if (!MOVABLE_SET.has(card.id)) continue;
      const shell = cardShells.get(card.id);
      if (!shell) continue;
      const regionName = EDIT_REGIONS.includes(card.region) ? card.region : "right_rail";
      byRegion.get(regionName).push(card);
      shell.hidden = !card.visible;
      shell.classList.toggle("hud-card-collapsed", effectiveCollapsed(card, pending));
      shell.setAttribute("data-hud-movable", "yes");
      shell.style.setProperty("--hud-span", String(card.col_span));
      shell.style.setProperty("--hud-rows", String(card.row_span));
      shell.setAttribute(
        "data-hud-span",
        `${card.col_span}x${card.row_span}`,
      );
      const collapseBtn = shell.querySelector('[data-hud-edit-command="collapse"]');
      if (collapseBtn) {
        const folded = effectiveCollapsed(card, pending);
        collapseBtn.setAttribute("aria-pressed", folded ? "true" : "false");
        collapseBtn.title = `${folded ? "Open" : "Fold"} ${labelOf(card.id)}`;
        collapseBtn.setAttribute("aria-label", collapseBtn.title);
      }
      const hideBtn = shell.querySelector('[data-hud-edit-command="hide"]');
      if (hideBtn) {
        hideBtn.setAttribute("aria-pressed", card.visible ? "false" : "true");
        hideBtn.textContent = card.visible ? "\u2715" : "\u25cb";
      }
    }
    for (const [region, cards] of byRegion) {
      const el = regionEls.get(region);
      if (!el) continue;
      cards.sort((a, b) => a.order - b.order || a.id.localeCompare(b.id));
      for (const card of cards) {
        const shell = cardShells.get(card.id);
        if (shell && shell.parentElement !== el) el.appendChild(shell);
      }
    }
    doc.body.setAttribute("data-hud-edit", editing ? "on" : "off");
    if (barEl) barEl.hidden = !editing;
    updateBadge();
    if (options.onRender) {
      try { options.onRender(layout, { editing }); } catch { /* never break the page */ }
    }
  }

  // -------------------------------------------------------------- save/undo
  function scheduleSave() {
    if (saveTimer) clearTimeout(saveTimer);
    if (saving) { saveTimer = setTimeout(scheduleSave, SAVE_DEBOUNCE_MS); return; }
    saveTimer = setTimeout(flushSave, SAVE_DEBOUNCE_MS);
  }

  async function flushSave() {
    saveTimer = null;
    saving = true;
    try {
      const answer = await store.saveLayout(layout);
      if (answer && answer.layout) layout = answer.layout;
      if (answer && answer.saved) {
        lastSavedAt = new Date();
        try {
          globalThis.dispatchEvent(new CustomEvent("jarvis:hud-layout-saved",
            { detail: layout }));
        } catch { /* an old engine: the badge still shows the name */ }
        announce(`Saved. ${describeLayout(layout)}`);
      } else {
        announce(`Not saved: ${(answer && answer.error) || "the PC refused the write"}.`);
      }
    } catch (error) {
      announce(`Not saved: ${error && error.message ? error.message : error}`);
    } finally {
      saving = false;
      render();
    }
  }

  function doAction(action, { snapshot = true } = {}) {
    const before = layout;
    const result = applyAction(layout, action, { pendingCount: pendingCount() });
    if (!result.changed) {
      if (result.note) announce(result.note);
      return result;
    }
    if (snapshot) {
      undoStack.push(before);
      if (undoStack.length > UNDO_LIMIT) undoStack.shift();
    }
    // H3 (Ruling 27): the first change to a SHIPPED layout is made to the
    // owner's copy, never silently to the built-in. Reset keeps a custom copy
    // a custom copy (its name and its saved layout survive a reset).
    let next = result.layout;
    let note = result.note;
    if (action.type === "resetToPreset") {
      if (isUserLayout(before)) {
        next = normalizeLayout({
          ...next,
          id: before.id,
          name: before.name,
          user_presets: userLayouts(before),
        });
      }
    } else if (!isUserLayout(before)) {
      next = ensureCustomCopy(next);
      note = `${note ? `${note} ` : ""}Editing your copy "${next.name}".`;
    }
    layout = next;
    render();
    scheduleSave();
    if (note) announce(note);
    return { ...result, layout };
  }

  function undo() {
    const previous = undoStack.pop();
    if (!previous) { announce("Nothing to undo."); return; }
    layout = previous;
    render();
    scheduleSave();
    announce("Undone.");
  }

  // H3-PM-2 (post-merge audit, 2026-10-22): entering edit mode must never
  // leave a protected card behind a closed rail. Every rail the current shell
  // slides away (or hides outright, like split-stage's right rail) is marked
  // `.edit-reveal`, which the page CSS brings on screen; leaving edit mode
  // removes the mark so the shell's own look returns untouched.
  const editRevealedRails = new Set();
  function revealRailsForEditing() {
    const view = doc.defaultView;
    const rails = [doc.querySelector(".rail.left"), doc.getElementById("rail-right")]
      .filter(Boolean);
    for (const rail of rails) {
      if (editing) {
        const style = view ? view.getComputedStyle(rail) : null;
        const box = rail.getBoundingClientRect();
        const hidden = !style || style.display === "none" || box.right <= 1
          || box.left >= (view ? view.innerWidth : 0) - 1;
        if (hidden) {
          rail.classList.add("edit-reveal");
          editRevealedRails.add(rail);
        }
      } else if (editRevealedRails.has(rail)) {
        rail.classList.remove("edit-reveal");
        editRevealedRails.delete(rail);
      }
    }
  }

  function setEditing(on) {
    editing = Boolean(on);
    if (editing) {
      entrySnapshot = layout;
      undoStack.length = 0;
      announce("");
    } else if (saveTimer) {
      flushSave();
    }
    revealRailsForEditing();
    render();
    updateEditButton();
  }

  function updateEditButton() {
    const button = byId("hud-edit-toggle");
    if (!button) return;
    button.setAttribute("aria-pressed", editing ? "true" : "false");
    button.textContent = editing ? "Done" : "Edit HUD";
    button.title = editing
      ? "Finish editing the HUD layout"
      : "Move, resize, fold or hide the HUD's cards";
    button.hidden = !shellPresent;
  }

  // ------------------------------------------------------------ interactions
  function cardFromEvent(target) {
    const shell = target && target.closest ? target.closest("[data-hud-card]") : null;
    return shell ? shell.getAttribute("data-hud-card") : null;
  }

  function onToolbarClick(event) {
    const button = event.target && event.target.closest
      ? event.target.closest("[data-hud-edit-command]") : null;
    if (!button) return;
    event.preventDefault();
    const id = button.getAttribute("data-hud-edit-card");
    const command = button.getAttribute("data-hud-edit-command");
    if (button.disabled) {
      announce(button.title || FIXED_REASON);
      return;
    }
    if (!editing) return;
    if (command === "up") doAction({ type: "reorderCard", id, delta: -1 });
    else if (command === "down") doAction({ type: "reorderCard", id, delta: 1 });
    else if (command === "size") {
      doAction({ type: "resizeCard", id, size: button.getAttribute("data-hud-edit-size") });
    } else if (command === "collapse") doAction({ type: "toggleCollapsed", id });
    else if (command === "hide") doAction({ type: "setVisible", id, visible: false });
  }

  function onRegionChange(event) {
    const select = event.target && event.target.closest
      ? event.target.closest("[data-hud-edit-region]") : null;
    if (!select) return;
    const id = select.getAttribute("data-hud-edit-region");
    if (!editing) return;
    doAction({ type: "moveCard", id, region: select.value, index: 0 });
  }

  function onShellKey(event, id) {
    if (!editing) return;
    const target = event.target;
    if (!target || !target.classList || !target.classList.contains("hud-card-handle")) return;
    const card = layout.cards.find((entry) => entry.id === id);
    if (!card) return;
    let handled = true;
    if (event.altKey && event.key === "ArrowUp") doAction({ type: "reorderCard", id, delta: -1 });
    else if (event.altKey && event.key === "ArrowDown") doAction({ type: "reorderCard", id, delta: 1 });
    else if (event.altKey && (event.key === "ArrowLeft" || event.key === "ArrowRight")) {
      const at = EDIT_REGIONS.indexOf(card.region);
      const next = event.key === "ArrowLeft" ? at - 1 : at + 1;
      if (next < 0 || next >= EDIT_REGIONS.length) announce(`${labelOf(id)} is already in ${REGION_LABEL[card.region]}.`);
      else doAction({ type: "moveCard", id, region: EDIT_REGIONS[next], index: 0 });
    } else if (event.shiftKey && (event.key === "ArrowLeft" || event.key === "ArrowRight")) {
      const step = event.key === "ArrowLeft" ? -2 : 2;
      doAction({ type: "resizeCard", id, col_span: card.col_span + step, row_span: card.row_span });
    } else if (event.shiftKey && (event.key === "ArrowUp" || event.key === "ArrowDown")) {
      const step = event.key === "ArrowUp" ? -1 : 1;
      doAction({ type: "resizeCard", id, col_span: card.col_span, row_span: card.row_span + step });
    } else if (event.key === "Enter" || event.key === " ") doAction({ type: "toggleCollapsed", id });
    else if (event.key === "h" || event.key === "H") doAction({ type: "setVisible", id, visible: !card.visible });
    else handled = false;
    if (handled) event.preventDefault();
  }

  // ---------------------------------------------------------------- pointer
  function onPointerDown(event) {
    if (!editing || dragState) return;
    const handle = event.target && event.target.closest
      ? event.target.closest("[data-hud-card-handle]") : null;
    if (!handle) return;
    const id = handle.getAttribute("data-hud-card-handle");
    const card = layout.cards.find((entry) => entry.id === id);
    if (!card || !MOVABLE_SET.has(id)) return;
    if (PROTECTED_SET.has(id)) {
      announce(`${labelOf(id)} always stays in ${REGION_LABEL[card.region]}.`);
      return;
    }
    event.preventDefault();
    const shell = cardShells.get(id);
    if (!shell) return;
    dragState = { id, shell, pointerId: event.pointerId, target: null };
    shell.classList.add("hud-card-dragging");
    try { handle.setPointerCapture(event.pointerId); } catch { /* ok */ }
  }

  function onPointerMove(event) {
    if (!dragState || event.pointerId !== dragState.pointerId) return;
    event.preventDefault();
    const drop = doc.elementFromPoint(event.clientX, event.clientY);
    const region = drop && drop.closest ? drop.closest("[data-hud-region]") : null;
    if (!region) return;
    for (const el of regionEls.values()) el.classList.remove("hud-region-drop");
    region.classList.add("hud-region-drop");
    dragState.target = region.getAttribute("data-hud-region");
    dragState.index = dropIndexIn(region, event.clientY, dragState.id);
  }

  function onPointerUp(event) {
    if (!dragState || event.pointerId !== dragState.pointerId) return;
    const { id, target, index } = dragState;
    dragState = null;
    const shell = cardShells.get(id);
    if (shell) shell.classList.remove("hud-card-dragging");
    for (const el of regionEls.values()) el.classList.remove("hud-region-drop");
    if (target) doAction({ type: "moveCard", id, region: target, index: index || 0 });
  }

  function dropIndexIn(region, clientY, movingId) {
    const shells = Array.from(region.querySelectorAll("[data-hud-card]"))
      .filter((el) => el.getAttribute("data-hud-card") !== movingId && !el.hidden);
    for (let i = 0; i < shells.length; i += 1) {
      const box = shells[i].getBoundingClientRect();
      if (clientY < box.top + box.height / 2) return i;
    }
    return shells.length;
  }

  // -------------------------------------------------------------- key handling
  function onKeyDown(event) {
    if (event.key === "Escape") {
      if (dragState) {
        const shell = cardShells.get(dragState.id);
        if (shell) shell.classList.remove("hud-card-dragging");
        for (const el of regionEls.values()) el.classList.remove("hud-region-drop");
        dragState = null;
        announce("Drag cancelled.");
        return;
      }
      if (editing) {
        event.preventDefault();
        setEditing(false);
        announce("HUD editing finished.");
      }
      return;
    }
    if (editing && (event.ctrlKey || event.metaKey) && String(event.key).toLowerCase() === "z") {
      event.preventDefault();
      undo();
    }
  }

  // --------------------------------------------------------------------- bar
  function ensureBar() {
    const stage = byId("stage");
    if (!stage) return;
    barEl = doc.createElement("div");
    barEl.className = "hud-edit-bar hud-edit-banner";
    barEl.id = "hud-edit-bar";
    barEl.hidden = true;
    barEl.setAttribute("role", "region");
    barEl.setAttribute("aria-label", "HUD editing controls");
    // Built node by node: this page has an HTML-sink rule (tests/html-sinks.mjs)
    // and a capture bar has no dynamic text needing markup.
    const words = doc.createElement("span");
    words.className = "hud-edit-words";
    words.textContent = "Editing the HUD — drag a card or use its buttons. Press Esc when done.";
    const status = doc.createElement("span");
    status.className = "hud-edit-status";
    status.id = "hud-edit-status";
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    barEl.append(words, status);
    for (const [what, text] of [["undo", "Undo"], ["reset", "Reset to preset"],
      ["discard", "Discard changes"], ["done", "Done"]]) {
      const button = doc.createElement("button");
      button.type = "button";
      button.className = "ghost";
      button.id = `hud-edit-${what}`;
      button.setAttribute("data-hud-edit-global", what);
      button.textContent = text;
      barEl.appendChild(button);
    }
    stage.insertBefore(barEl, byId("banner") || stage.firstChild);
    statusEl = doc.getElementById("hud-edit-status");
    barEl.addEventListener("click", (event) => {
      const button = event.target && event.target.closest
        ? event.target.closest("[data-hud-edit-global]") : null;
      if (!button) return;
      const what = button.getAttribute("data-hud-edit-global");
      if (what === "undo") undo();
      else if (what === "done") { setEditing(false); announce("HUD editing finished."); }
      else if (what === "reset") doAction({ type: "resetToPreset", id: layout.base_preset });
      else if (what === "discard" && entrySnapshot) {
        layout = entrySnapshot;
        undoStack.length = 0;
        setEditing(false);
        render();
        scheduleSave();
        announce("Changes discarded.");
      }
    });
  }

  function currentLayoutName() {
    if (!layout) return "Cockpit";
    if (isUserLayout(layout)) return layout.name;
    const info = presetInfo(layout.base_preset);
    return info ? info.label : (layout.name || "Cockpit");
  }

  function updateBadge() {
    if (!badgeEl || !layout) return;
    const name = currentLayoutName();
    badgeEl.textContent = `Layout: ${name}`;
    badgeEl.title = `HUD layout: ${name}. Open the Layouts menu.`;
    badgeEl.setAttribute("aria-label", `HUD layout: ${name}. Open the Layouts menu.`);
  }

  function ensureToggle() {
    const bar = doc.querySelector(".stage-bar");
    if (!bar) return;
    // F1 (2026-10-22): the read-only `Layout: <Preset Name>` badge sits next
    // to [Edit HUD]. It names the saved HUD layout and opens the Focus
    // presets card on click (L1) - it never chooses or saves a layout.
    badgeEl = doc.createElement("button");
    badgeEl.type = "button";
    badgeEl.className = "ghost hud-layout-badge";
    badgeEl.id = "hud-layout-badge";
    badgeEl.setAttribute("aria-expanded", "false");
    badgeEl.addEventListener("click", () => {
      try {
        globalThis.dispatchEvent(new CustomEvent("jarvis:hud-presets-open"));
      } catch { /* the badge still names the layout without a menu */ }
    });
    const button = doc.createElement("button");
    button.type = "button";
    button.className = "ghost hud-edit-toggle";
    button.id = "hud-edit-toggle";
    button.setAttribute("aria-pressed", "false");
    button.title = "Move, resize, fold or hide the HUD's cards";
    button.textContent = "Edit HUD";
    button.setAttribute("aria-label", "Edit HUD layout");
    bar.append(badgeEl, button);
    button.hidden = !shellPresent;
    button.addEventListener("click", () => {
      setEditing(!editing);
    });
    updateBadge();
  }

  // ------------------------------------------------------------------- mount
  function wire() {
    doc.addEventListener("click", onToolbarClick);
    doc.addEventListener("change", onRegionChange);
    doc.addEventListener("pointerdown", onPointerDown, true);
    doc.addEventListener("pointermove", onPointerMove, true);
    doc.addEventListener("pointerup", onPointerUp, true);
    doc.addEventListener("pointercancel", onPointerUp, true);
    doc.addEventListener("keydown", onKeyDown);
    ensureBar();
    ensureToggle();
    // The bootstrap pushes the saved layout (H1) and asks for edit mode when
    // Settings opens this window for editing.
    const adopt = (doc) => {
      if (editing || !doc) return;
      layout = normalizeLayout(doc);
      render();
    };
    globalThis.addEventListener("jarvis:hud-layout", (event) => adopt(event.detail));
    // The bootstrap's read is asynchronous and the editor may mount first.
    // Poll briefly for its global/event result, then stop (no timer leaks).
    let tries = 0;
    const waitForLayout = setInterval(() => {
      tries += 1;
      if (globalThis.__jarvisHudLayout) adopt(globalThis.__jarvisHudLayout);
      if (tries >= 20 || globalThis.__jarvisHudLayout) clearInterval(waitForLayout);
    }, 100);
    globalThis.addEventListener("jarvis:hud-edit-request", () => setEditing(true));
  }

  async function boot() {
    // The H1 bootstrap owns the SAVED document; this page must not read the
    // store itself at boot - that read would save a migrated layout as a side
    // effect, and a page load is not an edit. Until the bootstrap pushes its
    // answer, the old three-way value is the honest preview.
    // F1 (2026-10-22): the bootstrap's saved document is the only source;
    // this page no longer reads the retired localStorage layout key. Until it
    // arrives, Cockpit is the honest preview, exactly as the page paints.
    layout = globalThis.__jarvisHudLayout
      ? normalizeLayout(globalThis.__jarvisHudLayout)
      : presetLayout("cockpit");
    // PWA slice 2: a browser has no bootstrap to push a saved document, so
    // the editor reads THIS browser's own layout (hud-layout-store.js's
    // browser branch: localStorage, never the host PC's store). The desktop
    // path above is untouched: with a shell the bootstrap still pushes.
    if (!shellPresent && globalThis.__JARVIS_WEB_MODE) {
      try {
        const answer = await store.loadLayout();
        if (answer && answer.layout) layout = normalizeLayout(answer.layout);
      } catch { /* the page keeps the Cockpit preview */ }
    }
    wire();
    render();
    updateEditButton();
    return controller;
  }

  const controller = {
    get layout() { return layout; },
    get editing() { return editing; },
    setLayout(next) { layout = normalizeLayout(next); render(); },
    enter() { setEditing(true); },
    exit() { setEditing(false); },
    apply(action) { return doAction(action); },
    render,
    undo,
    flush: flushSave,
    sizeKeyFor,
  };
  return boot();
}
