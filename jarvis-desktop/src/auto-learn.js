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

/** What each switch says, by which one it is. `where` is APPROVE_WHERE.
 *  `off` is said only when the PC's OFF answer carried no sentence of its
 *  own (the PC's `message` wins, FIXLIST 5). */
export const SWITCHES = Object.freeze({
  auto: {
    label: AUTO_LABEL,
    detail: AUTO_DETAIL,
    action: AUTO_ACTION,
    command: "brain_memory_learning_auto",
    field: "auto",
    waitingField: "autoWaiting",
    lastField: "autoLast",
    waiting: (where) => `Waiting for your approval to turn on learning automatically. Approve it ${where}.`,
    on: "Jarvis now saves facts from your own words automatically. You can forget any of them here.",
    off: "\"Learn automatically\" is off. Every fact waits for your yes.",
  },
  sensitive: {
    label: SENSITIVE_LABEL,
    detail: SENSITIVE_DETAIL,
    action: SENSITIVE_ACTION,
    command: "brain_memory_learning_sensitive",
    field: "sensitive",
    waitingField: "sensitiveWaiting",
    lastField: "sensitiveLast",
    waiting: (where) =>
      `Waiting for your approval to remember sensitive topics automatically. Approve it ${where}.`,
    on: "Jarvis now saves sensitive topics automatically too.",
    off: "Sensitive topics wait for your yes again.",
  },
});

/** Under the sensitive switch while "Learn automatically" is off. */
export const SENSITIVE_NEEDS_AUTO =
  "\"Learn automatically\" is off, so this changes nothing until it is on.";

/** The button in the waiting line: OFF while an ON card waits withdraws
 *  the card (the PC's own rule), and is never held on a stale link. */
export const CANCEL_LABEL = "Cancel the request";
export const CANCEL_TITLE =
  "Withdraws the approval card. It stays off, and approving the card later changes nothing.";

/**
 * How the newest ON card ended (`auto_last` / `sensitive_last`, `{outcome,
 * why, message, at}`), in the "last setting card" words both apps use
 * (WORDING.md). `why` is the PC's reason for the record and is kept out of
 * this line (FIXLIST 28); a refused or failed card says the PC's own plain
 * `message` when it sent one.
 */
export function lastLine(which, last) {
  const sw = SWITCHES[which];
  const l = last && typeof last === "object" ? last : null;
  if (!sw || !l) return "";
  const message = text(l.message).trim();
  switch (l.outcome) {
    case "enabled":
      return `Approved: "${sw.label}" is on now.`;
    case "denied":
      return `You said no, so "${sw.label}" stays off.`;
    case "timed_out":
      return "Nobody answered the card in time, so nothing changed.";
    case "withdrawn":
      return "You turned it off while the card waited, so approving it changed nothing.";
    case "refused":
      return message || "Your PC's settings do not let this be approved, so it stayed off.";
    case "failed":
      return message || "Your PC could not turn it on, so it stayed off.";
    default:
      return "";
  }
}

/**
 * The last-card line to show under a switch now, or "". Nothing while a
 * card waits (the waiting line says it); "Approved" only while the switch
 * is on, and every other ending only while it is off - so a line never
 * contradicts the switch it sits under.
 */
export function lastLineNow(which, v) {
  const sw = SWITCHES[which];
  if (!sw || !v) return "";
  const last = v[sw.lastField];
  if (!last || v[sw.waitingField]) return "";
  const on = v[sw.field] === true;
  if ((last.outcome === "enabled") !== on) return "";
  return lastLine(which, last);
}

/** Said when an ON card left the queue and the switch is still off, from
 *  a PC that did not say how the card ended. */
export function stillOffLine(which) {
  const sw = SWITCHES[which];
  return sw ? `"${sw.label}" stays off. The card was not approved.` : "";
}

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

/** Where a fact was learned, in the row's words - History's device names
 *  (WORDING.md: PC, HUD, phone), as the phone says them. Unknown says
 *  nothing. */
const DEVICE_WORDS = Object.freeze({
  desktop: "from the PC",
  hud: "from the HUD",
  phone: "from the phone",
});

/**
 * The confirm before Forget, for every fact - this list and "What Jarvis
 * knows about you" alike, so both kinds are forgotten the same way. The
 * owner kept the question (decision 24); the words are both apps'.
 */
export function forgetQuestion(f) {
  return (
    `Stop recalling this?\n\n${f.text}\n\n` +
    "Jarvis keeps a record that it once knew this, but will not use it again. " +
    "This cannot be undone."
  );
}

/** Said after a Forget went through. */
export const FORGOTTEN = "Forgotten. Jarvis will not use it again.";

/** Under "Saved automatically": History and this list are separate. */
export const HISTORY_NOTE =
  "Deleting a conversation from History does not forget facts learned from it - use Forget here.";

/** The list with nothing in it, and the line added while the switch is off. */
export const EMPTY = "Nothing has been saved automatically yet.";
export const AUTO_OFF = "\"Learn automatically\" is off.";

const num = (v) => (typeof v === "number" && Number.isFinite(v) ? v : null);
const text = (v) => (typeof v === "string" ? v : "");

/** `auto_last` / `sensitive_last`: `{outcome, why, message}` or null. */
function readLast(v) {
  if (!v || typeof v !== "object") return null;
  const outcome = text(v.outcome).trim();
  if (!outcome) return null;
  return { outcome, why: text(v.why).trim(), message: text(v.message).trim() };
}

/** A PC without automatic learning at all: the phone's words. */
export const AUTO_MISSING = "Your PC's Jarvis does not have automatic learning yet.";

/**
 * The switches and the list, read together.
 *
 * `status` is `GET /api/memory/learning` (`{enabled, auto, auto_sensitive,
 * auto_waiting, sensitive_waiting, auto_last, sensitive_last, why}`), which the
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
    // How the newest ON card of each switch ended, or null.
    autoLast: s ? readLast(s.auto_last) : null,
    sensitiveLast: s ? readLast(s.sensitive_last) : null,
    // The settings file was damaged: the PC's sentence (it then treats
    // "Learn automatically" as off), shown under that switch (FIXLIST 1).
    fileWhy: s ? text(s.why).trim() : "",
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
