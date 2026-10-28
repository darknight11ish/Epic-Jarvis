/**
 * Where Settings was asked to open.
 *
 * WHY THIS EXISTS (the owner, 2026-10-27): "when i right click the jarvis tray
 * icon, click on update available, it only opens the settings page". The tray's
 * "Update available — v…" row now asks Rust for Settings *at the Updates
 * card* (`windows.rs`'s `show_settings_at`), and Rust tells this window in one
 * of two ways:
 *
 *   - a NEW window is built at `settings.html#updates`, so the place arrives as
 *     the fragment;
 *   - an OPEN window cannot be reloaded without losing whatever the owner had
 *     typed in it, so the place arrives as the
 *     [`SETTINGS_PLACE_EVENT`] event instead.
 *
 * The two doors carry the same value, and this module is the small pure part
 * that reads it: a place is ONE existing element id on `settings.html`
 * ("updates" is the only one Rust names today), never a URL, never a script,
 * never free text. `settings.js` is the half that scrolls, unfolds and focuses;
 * this half has no DOM and no Tauri in it, which is why it can be tested in
 * plain node.
 *
 * A place is also what the quickbar already leaves under
 * `jarvis.settings.place` (`plain-errors.js`) when it says "open <a settings
 * section>" - the freshness rule and the key are that mechanism's, reused
 * rather than copied.
 *
 * @module settings-place
 */

import { PLACE_FRESH_MS } from "./plain-errors.js";

/**
 * The event an open Settings hears a place by.
 *
 * `windows.rs`'s `SETTINGS_PLACE_EVENT` is the same spelling, and a Rust test
 * reads THIS file to hold the two together: a rename on one side alone would
 * leave the tray opening Settings at the top while every test still passed.
 */
export const SETTINGS_PLACE_EVENT = "settings-place";

/**
 * What a place may look like: a lower-case element id, starting with a letter.
 * Any id on the page fits; nothing with a slash, dot, space or `#` does, so a
 * fragment cannot be used to reach out of the page.
 */
const PLACE = /^[a-z][a-z0-9-]*$/;

/** No place id on this page is anywhere near this long. */
const MAX_PLACE = 64;

/** The place a fragment names (`#updates` -> "updates"), or null. */
export function placeFromHash(hash) {
  const text = String(hash == null ? "" : hash)
    .replace(/^#/, "")
    .toLowerCase();
  return text.length <= MAX_PLACE && PLACE.test(text) ? text : null;
}

/**
 * The place a stored `{ place, at }` record names, or null.
 *
 * The record is what `main.js`/`plain-errors.js` leave behind before asking
 * Rust to open Settings. It is only good while fresh: a place left hours ago
 * must not move the page the next time the owner opens Settings himself.
 * Anything unreadable is simply no place - the page then opens as it always
 * did, never with an error.
 */
export function placeFromStored(raw, now = Date.now()) {
  let left = null;
  try {
    left = JSON.parse(raw == null ? "null" : String(raw));
  } catch {
    return null;
  }
  if (!left || typeof left.place !== "string") return null;
  const place = left.place.trim().toLowerCase();
  if (!place || place.length > MAX_PLACE || !PLACE.test(place)) return null;
  if (!(Number(now) - Number(left.at) < PLACE_FRESH_MS)) return null;
  return place;
}
