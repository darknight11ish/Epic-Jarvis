/**
 * selection-chip.js - the Jarvis bar's "Attach selection" chip (Pillar 24-B).
 *
 * The PC reads the owner's highlighted text before the bar takes focus
 * (src-tauri/src/selection.rs, GET /api/selection, backend
 * jarvis_ui_control.read_selection()). This module is the PURE half: it turns
 * that answer into what the chip shows, and the prompts the quick actions
 * put in the box. main.js owns the DOM; no rule here is about a widget, so
 * every one is testable in node against a real 24-A payload.
 *
 * The rules, from the owner's Spotlight-6 decision (2026-10-18):
 *  - only a SUCCESSFUL read with non-empty text shows a chip; a refused or
 *    empty answer shows NOTHING (never a fake empty chip);
 *  - the payload names the PROGRAM, never the window title (24-A's rule) -
 *    and even if a payload carried a `title` field this module must ignore it;
 *  - the preview is the first ~40 characters of the SCRUBBED text, flattened
 *    to one line; the attached text is the payload's text EXACTLY (scrubbed,
 *    and the truncated marker respected - nothing is completed or invented);
 *  - NOTHING reaches the model by itself: the chip only puts words in the
 *    box, and the owner presses Enter.
 */

/** How much of the scrubbed selection the chip's one line shows. */
export const PREVIEW_CHARS = 40;

/** How many characters a chip label may be, including the app name. */
export const LABEL_CHARS = 160;

const FLAT = /\s+/g;

function textOf(value) {
  return typeof value === "string" ? value : "";
}

/** One line of a text, cut to `limit` characters with a real ellipsis. */
export function preview(text, limit = PREVIEW_CHARS) {
  const flat = textOf(text).replace(FLAT, " ").trim();
  if (!flat) return "";
  return flat.length > limit ? `${flat.slice(0, limit)}…` : flat;
}

/**
 * What the bar should show for one /api/selection answer, or `{ show: false }`.
 *
 * Only `ok === true` with real text is shown. `app` falls back to "the window
 * in front" when the PC could not name the program; the window TITLE is never
 * read, from any field.
 */
export function chipFor(result) {
  if (!result || typeof result !== "object" || result.ok !== true) {
    return { show: false };
  }
  const text = textOf(result.text);
  if (!text.trim()) return { show: false };
  const app = textOf(result.app).replace(FLAT, " ").trim() || "the window in front";
  const shown = preview(text);
  const label = `📎 Attach selection from ${app} — "${shown}"`;
  return {
    show: true,
    app,
    text,                       // the scrubbed text, EXACTLY as the PC returned it
    scrubbed: result.scrubbed === true,
    truncated: result.truncated === true,
    preview: shown,
    label: label.length > LABEL_CHARS ? `${label.slice(0, LABEL_CHARS - 1)}…` : label,
    // One selection's identity: the same program + the same scrubbed words.
    // Used only to keep a dismissed selection dismissed; no title is in it.
    fingerprint: `${app}\u0000${text}`,
  };
}

/** Was this exact selection dismissed with ×? (Same selection, no chip.) */
export function dismissed(fingerprint, lastDismissed) {
  return Boolean(fingerprint) && fingerprint === lastDismissed;
}

/** Put the selection's own words in the box, exactly as they arrived. */
export function attachPrompt(current, text) {
  const body = textOf(text);
  if (!body) return textOf(current);
  const before = textOf(current);
  return before.trim() ? `${before.trimEnd()}\n${body}` : body;
}

/** [Explain]: a local prompt, no backend call, no model call from here. */
export function explainPrompt(text) {
  return `Explain this:\n${textOf(text)}`;
}

/** [Summarize]: a local prompt, no backend call. */
export function summarizePrompt(text) {
  return `Summarize this:\n${textOf(text)}`;
}
