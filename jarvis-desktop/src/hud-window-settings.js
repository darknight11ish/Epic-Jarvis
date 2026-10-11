/**
 * Settings -> "The big HUD window": the one switch that shows or hides the
 * "Open the Jarvis bar" button in the big "Jarvis" window (the owner's
 * request of 2026-10-06; hud-window.js is the setting itself).
 *
 * The same shape as the other small Settings pages (notifications-settings.js
 * is the nearest one): import the reader, paint the row from it, save on
 * change. Nothing here calls Rust - a cosmetic switch changes at once and
 * raises no approval card - so this page needs no command, no capability and
 * no card.
 *
 * The row is an ordinary `<label class="toggle">` + checkbox, like the
 * floating face's and every other plain switch on this page: a checkbox does
 * not want `aria-checked`, which is for `role="switch"` widgets only.
 *
 * @module hud-window-settings
 */

import {
  OPEN_BAR_KEY,
  openBarShown,
  saveOpenBarShown,
  describeOpenBar,
} from "./hud-window.js";

const $ = (id) => document.getElementById(id);

/** The HUD window, which reads the same key, may obey a change made while it
 *  is open (this window origin's `localStorage` is shared by every Jarvis
 *  window on this computer). Nothing else writes this key today; the listener
 *  is here so a second writer could never make the two disagree silently. */
function onStorageKey(event) {
  if (event && event.key && event.key !== OPEN_BAR_KEY) return;
  paint();
}

function paint() {
  const on = openBarShown();
  const box = $("hud-open-bar-show");
  if (box) box.checked = on;
  const line = $("hud-open-bar-status");
  if (line) line.textContent = describeOpenBar(on);
}

export function initHudWindowSettings() {
  const box = $("hud-open-bar-show");
  if (!box) return;
  paint();
  box.addEventListener("change", () => {
    saveOpenBarShown(box.checked);
    paint();
  });
  window.addEventListener("storage", onStorageKey);
}

if (typeof document !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initHudWindowSettings);
  } else {
    initHudWindowSettings();
  }
}
