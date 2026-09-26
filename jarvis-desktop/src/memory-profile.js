/**
 * "Always keep in mind", in the Brain window's Memory tab - the owner's
 * decision of 2026-09-24 (JARVIS-API.md section 6, `/api/memory/profile`).
 *
 * A short list of facts the owner pins. Jarvis reads them with every
 * question, word for word - a search alone only finds facts that share
 * words or meaning with the question, so "the owner is vegetarian" was
 * missing from "what should I cook tonight?". The list holds fact ids only;
 * the words are the facts' own, never summarised or rewritten, and a
 * pinned fact that is forgotten, corrected or erased leaves the list by
 * itself. The whole list may use 1,200 characters.
 *
 * This module holds the words and reads what the PC sends; brain.js holds
 * the state, draws the section and the Pin / Unpin buttons on the fact
 * lists, and calls the two Rust commands (src-tauri/src/brain/profile.rs):
 * brain_memory_profile (a read, hidden with the other memory lists) and
 * brain_memory_pin (one fact per call, held on a stale link, no card).
 *
 * The phone says the same words (net/MemoryProfile.kt).
 *
 * @module memory-profile
 */

/** The section's title and its one line - both apps, word for word. */
export const PROFILE_TITLE = "Always keep in mind";
export const PROFILE_DETAIL =
  "Jarvis reads these with every question, word for word. Keep it short.";

/** The buttons on a fact. */
export const PIN_LABEL = "Pin";
export const UNPIN_LABEL = "Unpin";
export const PIN_TITLE =
  "Always keep in mind: Jarvis reads this with every question, word for word.";
export const UNPIN_TITLE =
  "Take this off \"Always keep in mind\". The fact itself stays.";

/** Said after a pin or an unpin went through. */
export const PINNED = "Pinned. Jarvis reads it with every question.";
export const UNPINNED = "Unpinned. The fact itself stays.";

/** The list with nothing on it. */
export const PROFILE_EMPTY =
  "Nothing pinned yet. Use Pin on a fact to have Jarvis read it with every question.";

/** A PC without the list (Rust answers `{available: false}` for 404 / 501). */
export const PROFILE_MISSING =
  "Your PC's Jarvis does not have the \"Always keep in mind\" list yet.";

/** The PC's limit when it does not say (jarvis_memory.PROFILE_LIMIT). */
export const DEFAULT_LIMIT = 1200;

/** 1200 -> "1,200". By hand, so both apps and every locale say the same. */
export function grouped(n) {
  const v = Math.max(0, Math.floor(Number(n) || 0));
  return String(v).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

/** "N of 1,200 characters used" - both apps' words. */
export function usedLine(chars, limit) {
  return `${grouped(chars)} of ${grouped(limit)} characters used`;
}

const num = (v) => (typeof v === "number" && Number.isFinite(v) ? v : null);
const text = (v) => (typeof v === "string" ? v : "");

/**
 * `brain_memory_profile`'s answer, read.
 *
 * `{facts: [{id, text, added}], chars, limit}` from the PC; `available:
 * false` (with `why`) from an older PC; `hidden: true` with `hidden_count`
 * while Windows Hello hides the memory lists (Rust took the facts out).
 * `ids` is every pinned fact's id, which the fact lists read to say Pin or
 * Unpin. A fact without a whole-number id is dropped, never guessed.
 */
export function readProfile(answer) {
  const a = answer && typeof answer === "object" ? answer : {};
  // Rust hands on only an answer with a `facts` list, or `{available:
  // false}`; anything else is not a list this window can trust.
  const available = a.available !== false && Array.isArray(a.facts);
  const facts = available ? a.facts : [];
  const rows = facts
    .filter((f) => f && Number.isInteger(f.id))
    .map((f) => ({ id: f.id, text: text(f.text), added: num(f.added) }));
  const chars = num(a.chars);
  return {
    available,
    why: available ? "" : text(a.why) || PROFILE_MISSING,
    hidden: available && a.hidden === true,
    hiddenCount: num(a.hidden_count) ?? 0,
    facts: rows,
    chars: chars ?? rows.reduce((n, f) => n + f.text.length, 0),
    limit: num(a.limit) ?? DEFAULT_LIMIT,
    ids: new Set(rows.map((f) => f.id)),
  };
}

/** Whether a fact is on the list, by what the PC last said. */
export function isPinned(view, id) {
  return Boolean(view && view.ids instanceof Set && view.ids.has(Number(id)));
}
