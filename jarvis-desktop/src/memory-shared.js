/**
 * "Between us", in the Brain window's Memory tab - the owner's decision of
 * 2026-09-27 (JARVIS-API.md section 44, `/api/memory/shared`).
 *
 * A shared joke or nickname is an ordinary fact - "Remember: we call the
 * printer 'the beast'" is saved exactly as any other "Remember: ..." is
 * (§19) - with a label the owner's own tap adds: `meta.kind = "shared"`.
 * Jarvis may use it in an answer when relevant, in Warm manner only (§27,
 * §44.4) - never set automatically, and never by the model.
 *
 * This module holds the words and reads what the PC sends; brain.js holds
 * the state, draws the section and the "Between us" toggle on the fact
 * lists, and calls the two Rust commands (src-tauri/src/brain/shared.rs):
 * brain_memory_shared (a read, hidden with the other memory lists) and
 * brain_memory_share (one fact per call, held on a stale link, no card).
 *
 * The phone says the same words (net/MemoryShared.kt).
 *
 * @module memory-shared
 */

/** The section's title and its one line - both apps, word for word. */
export const SHARED_TITLE = "Between us";
export const SHARED_DETAIL =
  "Shared jokes and nicknames. Jarvis may bring one up when it fits - never in Plain manner.";

/** The toggle on a fact. */
export const SHARE_LABEL = "Between us";
export const UNSHARE_LABEL = "Not between us";
export const SHARE_TITLE =
  "Tag this as a shared joke or nickname. Jarvis may use it when relevant, in Warm manner only.";
export const UNSHARE_TITLE = "Take this off \"Between us\". The fact itself stays.";

/** Said after a tag or an untag went through. */
export const SHARED = "Tagged. It is now in \"Between us\".";
export const UNSHARED = "Untagged. The fact itself stays.";

/** The list with nothing on it. */
export const SHARED_EMPTY =
  "Nothing tagged yet. Use \"Between us\" on a fact to add a shared joke or nickname here.";

/** A PC without the list (Rust answers `{available: false}` for 404 / 501). */
export const SHARED_MISSING = "Your PC's Jarvis does not have the \"Between us\" list yet.";

const num = (v) => (typeof v === "number" && Number.isFinite(v) ? v : null);
const text = (v) => (typeof v === "string" ? v : "");

/**
 * `brain_memory_shared`'s answer, read.
 *
 * `{facts: [<full fact rows>]}` from the PC; `available: false` (with
 * `why`) from an older PC; `hidden: true` with `hidden_count` while
 * Windows Hello hides the memory lists (Rust took the facts out). `ids` is
 * every tagged fact's id, which the fact lists read to say "Between us" or
 * "Not between us". A fact without a whole-number id is dropped, never
 * guessed.
 */
export function readShared(answer) {
  const a = answer && typeof answer === "object" ? answer : {};
  const available = a.available !== false && Array.isArray(a.facts);
  const facts = available ? a.facts : [];
  const rows = facts
    .filter((f) => f && Number.isInteger(f.id))
    .map((f) => ({ id: f.id, text: text(f.text), created: num(f.created) }));
  return {
    available,
    why: available ? "" : text(a.why) || SHARED_MISSING,
    hidden: available && a.hidden === true,
    hiddenCount: num(a.hidden_count) ?? 0,
    facts: rows,
    ids: new Set(rows.map((f) => f.id)),
  };
}

/** Whether a fact is tagged "Between us", by what the PC last said. */
export function isShared(view, id) {
  return Boolean(view && view.ids instanceof Set && view.ids.has(Number(id)));
}
