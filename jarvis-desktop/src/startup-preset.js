/**
 * Startup preset - the reading and the words the Settings row draws
 * (2026-11-22).
 *
 * THE SETTING IS THE PC'S. `GET /api/work` carries the ten focus presets and,
 * beside them, `startup_preset: {"preset": "<id>", "why": ""}` - the preset the
 * owner marked to load by itself when Atlas starts (`backend/jarvis_presets.py`,
 * `docs/JARVIS-API.md`). `POST /api/work/startup-preset` sets or clears it. This
 * module only reads that answer and turns it into the small view objects the
 * Settings card draws; it deliberately knows no preset id or name, so a preset
 * added, renamed or removed by the PC appears, moves or disappears without a
 * desktop release.
 *
 * WHAT IT DOES NOT DO. Nothing here saves, approves or retries. Setting a preset
 * raises the PC's ONE `change_own_config` card, and only a press of the card's
 * own button in the Atlas bar can approve it; this page waits on that answer and
 * repeats the PC's own sentence. Clearing is a tightening and needs no card.
 *
 * It is a plain ES module with no DOM and no Tauri import, so the words can be
 * checked without a webview. The DOM wiring is `startup-preset-settings.js`.
 */

/** This card's own words. Every preset's name comes from the PC. */
export const NO_PRESET = "No preset";
export const NOW_NONE = `Now: ${NO_PRESET} - Atlas starts with nothing loaded.`;
export const NOW_UNKNOWN =
  "Now: no preset is loaded, because this PC has no preset with the saved name.";
export const MISSING =
  "This PC's Jarvis does not have the start-up preset setting yet. Update the " +
  "backend by running apply-patches.ps1, then open this again.";
export const BAD_ANSWER =
  "The PC answered, but not in a way this app can read. Update the backend by " +
  "running apply-patches.ps1.";
export const STALE =
  "The connection to Jarvis is catching up, so nothing can be saved until it does.";
export const REFUSED = "That did not work.";
export const CHANGED = "Saved.";
export const ASKED =
  "The PC put one card up for your answer. Nothing changes until you answer it.";
export const CARD_REFUSED =
  "The card was not approved, so nothing changed. Atlas starts exactly as it " +
  "did before.";
export const SAVED_ELSEWHERE =
  "A chat sentence can change this setting too, so open this card again to see " +
  "the latest value.";

function words(value) {
  return typeof value === "string" ? value.trim() : "";
}

/** One preset row from the PC's own list; a row without an id or a name is not
 *  a preset this page can offer, so it is dropped rather than drawn blank. */
function presetRow(row) {
  if (!row || typeof row !== "object") return null;
  const id = words(row.id);
  const name = words(row.title) || words(row.name) || words(row.label);
  return id && name ? { id, name } : null;
}

function unavailable(why) {
  return {
    available: false,
    why,
    presets: [],
    saved: "",
    current: "",
    currentName: "",
    unknownCurrent: "",
    note: "",
  };
}

/**
 * The PC's `/api/work` answer, read. Never throws.
 *
 * `raw` is whatever the bridge returned: the route's body unchanged, or an
 * `{available: false, why}` object the bridge itself produced when the call
 * failed. A shape this desktop cannot read is an honest `available: false` with
 * the update line, never an invented preset list.
 */
export function readStartupPreset(raw) {
  if (typeof raw === "string") return unavailable(raw.trim() || BAD_ANSWER);
  if (!raw || typeof raw !== "object") return unavailable(BAD_ANSWER);
  if (raw.available === false) {
    return unavailable(words(raw.why) || words(raw.error) || MISSING);
  }
  if (raw.ok === false) {
    return unavailable(words(raw.why) || words(raw.error) || words(raw.message) || MISSING);
  }
  const rows = Array.isArray(raw.presets) ? raw.presets.map(presetRow).filter(Boolean) : [];
  const presets = [];
  const seen = new Set();
  for (const row of rows) {
    if (seen.has(row.id)) continue;
    seen.add(row.id);
    presets.push(row);
  }
  if (!presets.length) return unavailable(BAD_ANSWER);

  const block = raw.startup_preset && typeof raw.startup_preset === "object"
    ? raw.startup_preset : {};
  const saved = words(block.preset);
  const why = words(block.why);
  const known = presets.find((preset) => preset.id === saved) || null;
  return {
    available: true,
    why: "",
    presets,
    // The PC's OWN saved id, known or not. It is what the select must be
    // compared against to decide whether a press would change anything: a
    // remembered name this list does not carry must still be clearable.
    saved,
    current: known ? known.id : "",
    currentName: known ? known.name : "",
    // The PC remembers a name this build's list does not carry, and says why
    // nothing is loaded. Shown as the PC's own sentence, never silently hidden.
    unknownCurrent: saved && !known ? saved : "",
    note: why,
  };
}

/** The "Now:" line. The current value is the PC's, never the select's. */
export function currentWords(view) {
  if (!view || !view.available) return (view && view.why) || MISSING;
  if (view.current) return `Now: Atlas loads the ${view.currentName} preset when it starts.`;
  if (view.unknownCurrent) return NOW_UNKNOWN;
  return NOW_NONE;
}

/** The one sentence above the row that states the card rule plainly. */
export function cardWords(where) {
  const place = words(where) || "on the PC";
  return (
    `Saving a preset asks you first: one card appears ${place}, and nothing ` +
    `changes until you approve it. Choosing "${NO_PRESET}" takes effect at once ` +
    `and asks nothing.`
  );
}

/**
 * What is said while the PC is answering. Setting a preset raises a card and the
 * command waits for it, so this is said BEFORE the result arrives - the owner
 * needs to know where to look. Clearing raises nothing, and says so.
 */
export function savingWords(id, where) {
  if (!id) return "Clearing it now - this needs no card.";
  const place = words(where) || "on the PC";
  return `Waiting for your answer to the card ${place}. Nothing changes until you approve it.`;
}

/** The body the one write sends: the preset's PC id, or "" to clear it. */
export function saveArgs(id) {
  return { preset: String(id || "") };
}

/**
 * The PC's answer, in words. Its own `message`/`error` wins; this module only
 * supplies the honest fallback when the PC said nothing, and never turns a
 * refusal into a success.
 */
export function resultWords(raw) {
  if (typeof raw === "string") return raw.trim() || REFUSED;
  if (!raw || typeof raw !== "object") return REFUSED;
  const said = words(raw.message) || words(raw.error) || words(raw.why);
  if (raw.ok === false) {
    if (said) return said;
    return raw.card === true ? CARD_REFUSED : REFUSED;
  }
  if (said) return said;
  if (raw.changed === true) return CHANGED;
  return ASKED;
}
