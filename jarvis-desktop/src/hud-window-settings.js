/**
 * Settings -> "The big HUD window": two per-computer cosmetic choices about
 * that window, in one card.
 *
 *  1. THE SWITCH (the owner's request of 2026-10-06): does the "Open the
 *     Jarvis bar" button show in the big "Jarvis" window? (`hud-window.js`
 *     OPEN_BAR_KEY, drawn by the bootstrap injected into the page.)
 *  2. THE LAYOUT (H1 + H3 of the editable-HUD design, rulings 23-28/Q5):
 *     which layout the big window starts from - the seven built-in ones
 *     (Cockpit, Studio, Ambient, Quiet, Telemetry & Ops, Second Brain &
 *     Planner, Minimal) plus the owner's own saved layouts ("My layouts",
 *     H3). The old three-way choice is migrated the first time the store has
 *     nothing saved, so an owner who picked Studio keeps Studio.
 *
 * WHERE IT IS KEPT. The layout is a document in the desktop settings store
 * through the Rust commands `get_hud_layout`/`set_hud_layout` - the same
 * appearance class as the theme, no backend, no pairing token, no approval
 * card. The same document carries the owner's saved layouts; this card lists
 * them and writes through the SAME one command (no new command, no new
 * grant). H3 renders the preset's own shell, density and opening tab.
 *
 * A SAVE THAT DID NOT HAPPEN IS SHOWN AS NOT SAVED. The status line is painted
 * from the store's answer, never from the click.
 *
 * @module hud-window-settings
 */

import {
  OPEN_BAR_KEY,
  openBarShown,
  saveOpenBarShown,
  describeOpenBar,
} from "./hud-window.js";
import {
  choosePreset,
  layoutStatus,
  loadLayout,
  presetRows,
  saveLayout,
} from "./hud-layout-store.js";
import {
  DEFAULT_PRESET_ID,
  normalizeLayout,
  presetLayout,
  userLayouts,
} from "./hud-layout.js";
import { applyUserLayout } from "./hud-presets.js";

const $ = (id) => document.getElementById(id);

/* ── 1. The "Open the Jarvis bar" button switch ──────────────────────────── */

function paintOpenBar() {
  const on = openBarShown();
  const box = $("hud-open-bar-show");
  if (box) box.checked = on;
  const line = $("hud-open-bar-status");
  if (line) line.textContent = describeOpenBar(on);
}

/* ── 2. The HUD layout preset picker ─────────────────────────────────────── */

const layoutRows = new Map();
let answer = null;
let painted = false;

function paintLayoutStatus() {
  const line = $("hud-layout-status");
  if (line) line.textContent = layoutStatus(answer);
}

function paintChosen() {
  const activeId = answer && answer.layout ? answer.layout.id : null;
  for (const [id, radio] of layoutRows) radio.checked = id === activeId;
  paintLayoutStatus();
}

/** Builds one row per built-in preset from the module's own table. */
function buildLayoutRows() {
  const list = $("hud-layout-list");
  if (!list) return;
  painted = true;
  list.replaceChildren();
  layoutRows.clear();
  for (const row of presetRows(answer)) {
    const label = document.createElement("label");
    label.className = "theme-row";
    // `data-choice`, not `data-hud-layout`: a row carrying the HUD's own
    // attribute would describe itself as the layout rather than as a choice.
    label.dataset.choice = row.id;
    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = "hud-layout";
    radio.value = row.id;
    radio.addEventListener("change", () => pickLayout(row.id));
    const glyph = document.createElement("span");
    glyph.className = "swatch layout-swatch";
    glyph.setAttribute("aria-hidden", "true");
    glyph.textContent = row.glyph;
    const text = document.createElement("span");
    text.className = "theme-text";
    const name = document.createElement("span");
    name.className = "theme-name";
    name.textContent = row.label;
    const blurb = document.createElement("span");
    blurb.className = "theme-blurb";
    blurb.textContent = row.blurb;
    text.append(name, blurb);
    const check = document.createElement("span");
    check.className = "theme-check";
    check.setAttribute("aria-hidden", "true");
    check.textContent = "\u2713";
    label.append(radio, glyph, text, check);
    list.append(label);
    layoutRows.set(row.id, radio);
  }
  buildUserRows(list);
  paintChosen();
}

/**
 * One row per owner-saved layout (H3). Built from the SAME saved document the
 * window's Layouts menu shows; choosing one writes through the one existing
 * command, exactly like a built-in preset.
 */
function buildUserRows(list) {
  const library = answer && answer.layout ? userLayouts(answer.layout) : [];
  for (const entry of library) {
    const label = document.createElement("label");
    label.className = "theme-row";
    label.dataset.choice = entry.id;
    label.dataset.userLayout = "1";
    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = "hud-layout";
    radio.value = entry.id;
    radio.addEventListener("change", () => pickUserLayout(entry.id));
    const glyph = document.createElement("span");
    glyph.className = "swatch layout-swatch";
    glyph.setAttribute("aria-hidden", "true");
    glyph.textContent = "\u2605";
    const text = document.createElement("span");
    text.className = "theme-text";
    const name = document.createElement("span");
    name.className = "theme-name";
    name.textContent = entry.name;
    const blurb = document.createElement("span");
    blurb.className = "theme-blurb";
    blurb.textContent = "Your saved layout. Edit it in the window's Layouts menu.";
    text.append(name, blurb);
    label.append(radio, glyph, text);
    list.append(label);
    layoutRows.set(entry.id, radio);
  }
  if (!library.length) {
    const empty = document.createElement("p");
    empty.className = "note";
    empty.dataset.userLayout = "1";
    empty.textContent = "No saved layouts yet: open the big window's Layouts "
      + "menu and press Duplicate to keep one.";
    list.append(empty);
  }
}

/**
 * Saves the choice and repaints from what the store actually kept.
 *
 * The HUD window itself (another window) reads the saved document on its next
 * load through the injected bootstrap. Nothing is previewed in THIS window.
 * H3-PM-1 (post-merge audit): the current document is passed through, so
 * picking a built-in preset replaces only the active arrangement and keeps
 * every layout in "My layouts" - the same rule Reset and the Layouts menu use.
 */
async function pickLayout(presetId) {
  const chosen = await choosePreset(presetId, answer && answer.layout);
  answer = {
    layout: chosen.layout,
    saved: chosen.saved,
    source: chosen.source,
    error: chosen.error,
  };
  paintChosen();
}

/** Choose one of the owner's own saved layouts (H3). */
async function pickUserLayout(id) {
  if (!answer || !answer.layout) return;
  const saved = await saveLayout(applyUserLayout(answer.layout, id));
  answer = { layout: saved.layout, saved: saved.saved, source: saved.source,
    error: saved.error };
  buildLayoutRows();
  paintChosen();
}

/** One-click reset (Ruling 28 item 3): back to Cockpit, keeping My layouts. */
async function resetToCockpit() {
  const base = presetLayout(DEFAULT_PRESET_ID);
  const library = answer && answer.layout ? userLayouts(answer.layout) : [];
  const saved = await saveLayout(normalizeLayout({ ...base, user_presets: library }));
  answer = { layout: saved.layout, saved: saved.saved, source: saved.source,
    error: saved.error };
  buildLayoutRows();
  paintChosen();
}

/* ── 3. The editor: open the HUD window in edit mode (H2, 2026-10-22) ────── */

/**
 * H2's editor lives in the HUD page. This Settings control is only the door:
 * one navigation command (`open_hud_edit`) shows that window and asks it to
 * enter edit mode; it saves nothing and approves nothing. In a plain browser
 * (or an older shell without the command) the status line says so honestly.
 */
async function openEditor() {
  const line = $("hud-edit-open-status");
  const tauri = globalThis.__TAURI__;
  const invoke = tauri && tauri.core && tauri.core.invoke;
  if (typeof invoke !== "function") {
    if (line) line.textContent = "Open the Jarvis desktop app to edit the HUD.";
    return;
  }
  try {
    await invoke("open_hud_edit");
    if (line) line.textContent = "The big HUD window is open in edit mode. Escape finishes.";
  } catch (e) {
    if (line) line.textContent = `The HUD window could not be opened: ${e && e.message ? e.message : e}`;
  }
}

/* ── Start ───────────────────────────────────────────────────────────────── */

export function initHudWindowSettings() {
  paintOpenBar();
  const box = $("hud-open-bar-show");
  if (box) {
    box.addEventListener("change", () => {
      saveOpenBarShown(box.checked);
      paintOpenBar();
    });
  }
  // `painted` guards the one-time row build; the async load repaints the
  // chosen row when the store answers (and reports an honest failure).
  const editButton = $("hud-edit-open");
  if (editButton) editButton.addEventListener("click", openEditor);
  const reset = $("hud-reset-layout");
  if (reset) reset.addEventListener("click", resetToCockpit);
  buildLayoutRows();
  loadLayout().then((loaded) => {
    answer = loaded;
    buildLayoutRows();
    paintChosen();
  });
}

if (typeof document !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initHudWindowSettings);
  } else {
    initHudWindowSettings();
  }
}

export { OPEN_BAR_KEY, openBarShown, saveOpenBarShown };
