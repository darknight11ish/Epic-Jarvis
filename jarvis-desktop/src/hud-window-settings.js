/**
 * Settings -> "The big HUD window": two per-computer cosmetic choices about
 * that window, in one card.
 *
 *  1. THE SWITCH (the owner's request of 2026-10-06): does the "Open the
 *     Jarvis bar" button show in the big "Jarvis" window? (`hud-window.js`
 *     OPEN_BAR_KEY, drawn by the bootstrap injected into the page.)
 *  2. THE LAYOUT (the owner's request of 2026-10-20, the HUD work order's
 *     PART III+IV): which of the three UIs the big window wears - Command
 *     Cockpit (the default), Studio Split-Workspace or Ambient Voice Core.
 *     All three are ONE page switched by `document.body.dataset.hudLayout`
 *     (`hud-window.js` HUD_LAYOUT_KEY; the page's own inline script reads the
 *     same key).
 *
 * The same shape as the other small Settings pages (notifications-settings.js
 * is the nearest one): import the reader, paint the controls from it, save on
 * change. Nothing here calls Rust - both choices are cosmetic, change at once
 * and raise no approval card - so this page needs no command, no capability and
 * no card. The layout rows are the theme picker's own row markup
 * (`label.theme-row`, radios, a glyph, the name and one line) because that is
 * this page's existing pattern for "pick one of N looks": a screen reader then
 * says which is chosen with no extra wiring.
 *
 * @module hud-window-settings
 */

import {
  OPEN_BAR_KEY,
  openBarShown,
  saveOpenBarShown,
  describeOpenBar,
  HUD_LAYOUT_KEY,
  HUD_LAYOUTS,
  HUD_LAYOUT_INFO,
  readHudLayout,
  saveHudLayout,
  normaliseHudLayout,
  describeHudLayout,
} from "./hud-window.js";

const $ = (id) => document.getElementById(id);

/* ── 1. The "Open the Jarvis bar" button switch ──────────────────────────── */

function paintOpenBar() {
  const on = openBarShown();
  const box = $("hud-open-bar-show");
  if (box) box.checked = on;
  const line = $("hud-open-bar-status");
  if (line) line.textContent = describeOpenBar(on);
}

/* ── 2. The HUD layout picker ────────────────────────────────────────────── */

let painted = false;

/** Builds the three rows once, from HUD_LAYOUT_INFO (never by hand). */
function buildLayoutRows() {
  const list = $("hud-layout-list");
  if (!list || painted) return;
  painted = true;
  for (const id of HUD_LAYOUTS) {
    const info = HUD_LAYOUT_INFO[id];
    const row = document.createElement("label");
    row.className = "theme-row";
    // `data-choice`, not `data-hud-layout`: the HUD's own reading is the
    // body attribute, and a row carrying it would describe itself as the
    // layout rather than as a choice of one.
    row.dataset.choice = id;
    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = "hud-layout";
    radio.value = id;
    const glyph = document.createElement("span");
    glyph.className = "swatch layout-swatch";
    glyph.setAttribute("aria-hidden", "true");
    glyph.textContent = info.glyph;
    const text = document.createElement("span");
    text.className = "theme-text";
    const name = document.createElement("span");
    name.className = "theme-name";
    name.textContent = info.label;
    const blurb = document.createElement("span");
    blurb.className = "theme-blurb";
    blurb.textContent = info.blurb;
    text.append(name, blurb);
    const check = document.createElement("span");
    check.className = "theme-check";
    check.setAttribute("aria-hidden", "true");
    check.textContent = "\u2713";
    row.append(radio, glyph, text, check);
    radio.addEventListener("change", () => pickLayout(id));
    list.append(row);
  }
}

function paintLayoutRows() {
  const list = $("hud-layout-list");
  if (!list) return;
  const chosen = readHudLayout();
  for (const row of list.querySelectorAll(".theme-row")) {
    row.querySelector("input").checked = row.dataset.choice === chosen;
  }
  const line = $("hud-layout-status");
  if (line) line.textContent = describeHudLayout(chosen);
}

/**
 * Saves the choice and repaints the rows.
 *
 * Nothing is previewed in THIS window: the choice is about the big HUD
 * window, which is another window - it obeys through the shared `storage`
 * event while it is open, and on its next load otherwise. If storage refuses
 * the write (private mode, cleared site data), the rows must not show a
 * choice that was not kept - so they are repainted from what storage actually
 * holds.
 */
function pickLayout(id) {
  const chosen = normaliseHudLayout(id);
  const saved = saveHudLayout(chosen);
  paintLayoutRows();
  const line = $("hud-layout-status");
  if (line && !saved) {
    line.textContent = `Could not save the HUD layout, so it stays ${
      HUD_LAYOUT_INFO[readHudLayout()].label}. This computer is not letting `
      + "Settings store a preference.";
  }
}

/** The HUD window, which reads the same keys, may obey a change made while it
 *  is open (this window origin's `localStorage` is shared by every Jarvis
 *  window on this computer). Nothing else writes these keys today; the
 *  listener is here so a second writer could never make the two disagree
 *  silently. */
function onStorageKey(event) {
  if (event && event.key && event.key !== OPEN_BAR_KEY && event.key !== HUD_LAYOUT_KEY) return;
  paintOpenBar();
  paintLayoutRows();
}

/* ── Wiring ─────────────────────────────────────────────────────────────── */

export function initHudWindowSettings() {
  const box = $("hud-open-bar-show");
  const list = $("hud-layout-list");
  if (!box && !list) return;
  if (box) {
    paintOpenBar();
    box.addEventListener("change", () => {
      saveOpenBarShown(box.checked);
      paintOpenBar();
    });
  }
  if (list) {
    buildLayoutRows();
    paintLayoutRows();
  }
  window.addEventListener("storage", onStorageKey);
}

if (typeof document !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initHudWindowSettings);
  } else {
    initHudWindowSettings();
  }
}
