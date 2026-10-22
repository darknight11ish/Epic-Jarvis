/**
 * Settings -> "The big HUD window": two per-computer cosmetic choices about
 * that window, in one card.
 *
 *  1. THE SWITCH (the owner's request of 2026-10-06): does the "Open the
 *     Jarvis bar" button show in the big "Jarvis" window? (`hud-window.js`
 *     OPEN_BAR_KEY, drawn by the bootstrap injected into the page.)
 *  2. THE LAYOUT (H1 of the editable-HUD design, Gemini rulings 23-28,
 *     2026-10-21): which of the seven built-in presets the big window starts
 *     from - Cockpit, Studio, Ambient, Focus, Telemetry & Ops, Second Brain &
 *     Planner and Minimal. The old three-way choice (cockpit/studio/ambient)
 *     is migrated the first time the store has nothing saved, so an owner who
 *     picked Studio keeps Studio.
 *
 * WHERE IT IS KEPT. The layout is a document in the desktop settings store
 * through the Rust commands `get_hud_layout`/`set_hud_layout` - the same
 * appearance class as the theme, no backend, no pairing token, no approval
 * card. The old `jarvis.hud.layout` localStorage key is still written as a
 * VIEW mirror so the page's three existing looks follow the pick at once;
 * it is not the source of truth. H2 draws the real region grid from the saved
 * document and the editor; this card only chooses a starting preset.
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
} from "./hud-layout-store.js";

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
  const chosen = answer && answer.layout ? answer.layout.base_preset : null;
  for (const [id, radio] of layoutRows) radio.checked = id === chosen;
  paintLayoutStatus();
}

/** Builds one row per built-in preset from the module's own table. */
function buildLayoutRows() {
  const list = $("hud-layout-list");
  if (!list || painted) return;
  painted = true;
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
  paintChosen();
}

/**
 * Saves the choice and repaints from what the store actually kept.
 *
 * The HUD window itself (another window) reads the saved document on its next
 * load through the injected bootstrap; the page's three in-header pills still
 * switch its look for now (H2 replaces that picker). Nothing is previewed in
 * THIS window.
 */
async function pickLayout(presetId) {
  const chosen = await choosePreset(presetId);
  answer = {
    layout: chosen.layout,
    saved: chosen.saved,
    source: chosen.source,
    error: chosen.error,
  };
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
