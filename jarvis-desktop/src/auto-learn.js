/**
 * Automatic learning, in the Brain window's Memory tab - JARVIS-API.md
 * section 19, "Automatic learning" (the owner's decision of 2026-09-24).
 *
 * Jarvis saves facts about the owner and their projects from the owner's
 * own words, without a card for each one, and every one of them is listed
 * here with a one-tap Forget. This module holds the words and reads what
 * the PC sends; brain.js holds the state, draws it, and calls the four
 * Rust commands (src-tauri/src/brain/auto_learn.rs) and the existing
 * brain_memory_forget.
 *
 * - "Learn automatically" (on by default) and "Also remember sensitive
 *   topics automatically" (off by default). Turning either ON raises one
 *   approval card; OFF is immediate. The same shape as the learning switch.
 * - "Saved automatically": newest first, the fact, when, a small "said
 *   aloud" mark for voice, Forget on each, and "Load older".
 * - On a `memory_saved` event (`{"ids": [...]}`, never the text) a quiet
 *   line, "Jarvis remembered 2 things", that opens the list. Never a
 *   pop-up, never the fact's words in a notification.
 *
 * Everything the PC sends goes in as text (`el()` in brain.js uses
 * `textContent`), never as markup.
 *
 * @module auto-learn
 */

import { whenWords } from "./history-view.js";

/** Section 5's words, word for word. The phone says the same. */
export const AUTO_LABEL = "Learn automatically";
export const AUTO_DETAIL =
  "Jarvis saves facts about you and your projects from what you type or say to it - " +
  "never from web pages, emails, documents or notes. You can forget any of them here.";
export const SENSITIVE_LABEL = "Also remember sensitive topics automatically";
export const SENSITIVE_DETAIL =
  "Health, money, passwords and account details, and private details about other " +
  "people. When this is off, Jarvis asks you first.";
export const LIST_TITLE = "Saved automatically";

/** The approval-card actions each switch's ON raises (jarvis-framework.toml). */
export const AUTO_ACTION = "learning_auto_enable";
export const SENSITIVE_ACTION = "learning_sensitive_enable";

/** One page of the list (the PC's default). */
export const PAGE = 30;

/** What each switch says, by which one it is. `where` is APPROVE_WHERE. */
export const SWITCHES = Object.freeze({
  auto: {
    label: AUTO_LABEL,
    detail: AUTO_DETAIL,
    action: AUTO_ACTION,
    command: "brain_memory_learning_auto",
    field: "auto",
    waitingField: "autoWaiting",
    waiting: (where) => `Waiting for your approval to turn on learning automatically. Approve it ${where}.`,
    on: "Jarvis now saves facts from your own words automatically. You can forget any of them here.",
    off: "Jarvis will not save anything automatically. New facts wait for your yes.",
    denied: "Learning automatically stays off: the card was denied or ran out of time.",
  },
  sensitive: {
    label: SENSITIVE_LABEL,
    detail: SENSITIVE_DETAIL,
    action: SENSITIVE_ACTION,
    command: "brain_memory_learning_sensitive",
    field: "sensitive",
    waitingField: "sensitiveWaiting",
    waiting: (where) =>
      `Waiting for your approval to remember sensitive topics automatically. Approve it ${where}.`,
    on: "Jarvis now saves sensitive topics automatically too.",
    off: "Sensitive topics wait for your yes again.",
    denied: "Sensitive topics still wait for your yes: the card was denied or ran out of time.",
  },
});

/** "Learn automatically" has meaning only while background learning is on. */
export const LEARNING_OFF_NOTE =
  "Background learning is off, so nothing is saved automatically. Start learning above to use this.";

/** The quiet line on a `memory_saved` event: "Jarvis remembered 2 things". */
export function rememberedLine(n) {
  const count = Number.isInteger(n) && n > 0 ? n : 0;
  if (!count) return "";
  return `Jarvis remembered ${count} ${count === 1 ? "thing" : "things"}`;
}

/**
 * The ids a `memory_saved` frame carries - `{"ids": [int, ...]}` and
 * nothing else (section 4, L10). Anything that is not a whole number is
 * dropped; a frame with none is not a save.
 */
export function savedIds(data) {
  const ids = data && Array.isArray(data.ids) ? data.ids : [];
  return ids.filter((id) => Number.isInteger(id));
}

/** The small mark for a fact learned from something said aloud. */
export const VOICE_MARK = "said aloud";
export const VOICE_TITLE = "Learned from something you said aloud to Jarvis.";

/** Where a fact was learned, in the row's words. Unknown says nothing. */
const DEVICE_WORDS = Object.freeze({
  desktop: "on this PC",
  hud: "on this PC",
  phone: "on your phone",
});

/**
 * The confirm before Forget - today's Forget question, word for word, so
 * both kinds of fact are forgotten the same way.
 */
export function forgetQuestion(f) {
  return (
    `Stop recalling this?\n\n${f.text}\n\n` +
    "It stays in the history but Jarvis will not use it again. " +
    "This cannot be undone."
  );
}

const num = (v) => (typeof v === "number" && Number.isFinite(v) ? v : null);
const text = (v) => (typeof v === "string" ? v : "");

/** A PC without automatic learning at all: the phone's words. */
export const AUTO_MISSING = "Your PC's Jarvis does not have automatic learning yet.";

/**
 * The switches and the list, read together.
 *
 * `status` is `GET /api/memory/learning` (`{enabled, auto, auto_sensitive,
 * auto_waiting, sensitive_waiting, auto_last, sensitive_last}`), which the
 * switches are drawn from; Rust answers `{available: false}` when the route
 * is missing (an older PC), and `null` means it could not be read. Then the
 * switches fall back to `auto` / `auto_sensitive` on the list itself, and
 * when neither is there, `switches` is false and `why` says so.
 *
 * `answer` is `GET /api/memory/auto`. `available: false` is a PC without it
 * (Rust answers that for a 404). `hidden` is "Windows Hello for memory lists
 * and chat history" holding the list back (Rust took the facts out, and
 * kept how many there were).
 *
 * A switch is on only when the PC says `true`: a missing field is not "yes".
 */
export function readAuto(answer, status = null) {
  const a = answer && typeof answer === "object" ? answer : {};
  const s = status && typeof status === "object" && status.available !== false
    && typeof status.auto === "boolean" ? status : null;
  const listed = a.available !== false;
  const from = s || (listed ? a : null);
  const list = listed && Array.isArray(a.facts) ? a.facts : [];
  return {
    available: listed,
    switches: from !== null,
    why: from || listed ? "" : AUTO_MISSING,
    auto: Boolean(from) && from.auto === true,
    sensitive: Boolean(from) && from.auto_sensitive === true,
    // Only the learning route says these; the queue says it too (brain.js).
    autoWaiting: Boolean(s) && s.auto_waiting === true,
    sensitiveWaiting: Boolean(s) && s.sensitive_waiting === true,
    learning: s && typeof s.enabled === "boolean" ? s.enabled : null,
    hidden: listed && a.hidden === true,
    hiddenCount: num(a.hidden_count) ?? 0,
    facts: list
      .filter((f) => f && Number.isInteger(f.id))
      .map((f) => ({
        id: f.id,
        text: text(f.text),
        savedAt: num(f.saved_at),
        provenance: text(f.provenance),
        device: text(f.device),
      })),
  };
}

/** One row's meta line: when it was saved, and where. */
export function factMeta(f, nowMs = Date.now()) {
  const parts = [whenWords(f.savedAt, nowMs), DEVICE_WORDS[f.device] || ""];
  return parts.filter(Boolean).join(" · ");
}

/** The next page added under the rows already shown, never one twice. */
export function addPage(rows, page) {
  const seen = new Set(rows.map((r) => r.id));
  return [...rows, ...page.filter((f) => !seen.has(f.id))];
}

/** The `before` for "Load older": the oldest `saved_at` shown, or null. */
export function olderThan(rows) {
  const times = rows.map((r) => r.savedAt).filter((t) => t !== null);
  return times.length ? Math.min(...times) : null;
}

/**
 * The next list read, with the older pages already loaded kept under it -
 * history-view.js's `refreshRows`, by `saved_at`. A first page that was not
 * full means there is nothing older, so nothing older is kept (a fact
 * forgotten elsewhere drops out). Returns `{rows, more}`.
 */
export function refreshRows(shown, page, pageSize, moreBefore) {
  const fresh = Array.isArray(page) ? page : [];
  if (fresh.length < pageSize) return { rows: fresh, more: false };
  const edge = olderThan(fresh);
  const ids = new Set(fresh.map((f) => f.id));
  const older = (Array.isArray(shown) ? shown : []).filter(
    (f) => !ids.has(f.id) && edge !== null && f.savedAt !== null && f.savedAt < edge
  );
  return { rows: [...fresh, ...older], more: older.length ? moreBefore : true };
}

/**
 * The reason line on a card that stayed a card (section 2): the PC's own
 * plain words - "from pasted text", "about health, a sensitive topic", "not
 * in your own words" - under `auto_reason` on its `/api/memory/pending` row. Nothing
 * when the PC sent none (absent or "").
 */
export function cardReason(p) {
  const why = p && text(p.auto_reason).trim();
  return why ? `Not saved automatically: ${why}` : "";
}
