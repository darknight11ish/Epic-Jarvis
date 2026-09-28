/**
 * "Forget a time frame" - the words and the reading (the owner's decision of
 * 2026-09-28; backend/jarvis_forget_range.py; JARVIS-API.md section 64).
 * forget-range-panel.js draws it on the Brain's History tab.
 *
 * The owner picks some days; the PC lists what Jarvis learned and the chats
 * from then, each ticked; the owner unticks any to keep and presses "Forget
 * these"; the PC raises ONE approval card listing every item, decided by a
 * tap - never by voice. Approved: the facts are forgotten (as Forget does)
 * and the chats deleted, with 10 minutes to Undo.
 *
 * Pure: no DOM, no Tauri. tests/forget-range.mjs checks every function here
 * against the real backend's answers (tests/fixtures/forget-range-cases.json,
 * made by tools/gen_forget_range_cases.py), and the words against the
 * phone's copy (net/ForgetRange.kt).
 *
 * @module forget-range
 */

/** The screens' words, both apps, word for word (the contract's `words`). */
export const WORDS = Object.freeze({
  asked: "You asked Jarvis to forget {said}. Check the list below.",
  bad_date: "Type the dates like 2026-09-01.",
  between_us: "Between us",
  chats_head: "Chats from then",
  custom: "Choose the dates",
  date_hint: "A date like 2026-09-01",
  erase_note: "Facts are forgotten, as Forget does: they stop being used and stay in the history. " +
    "To wipe a fact's words for good, use Erase the words on that fact.",
  facts_head: "What Jarvis learned then",
  forget: "Forget these",
  from: "From",
  kind_chats: "Chats",
  kind_chatbot: "Chat with an AI",
  kind_compare: "Comparison",
  kind_facts: "What Jarvis learned",
  kind_live: "Live",
  kind_support: "Support chat",
  kinds: "What to look for",
  locked: "Unlock Jarvis to see this list.",
  missing: "Your PC's Jarvis cannot forget a time frame yet - run apply-patches.ps1 on the PC.",
  none_ticked: "Tick at least one thing to forget.",
  pinned: "Always kept in mind",
  show: "Show the list",
  spills: "Also has messages from outside these days - the whole chat is deleted.",
  stale: "The connection to Jarvis is catching up, so nothing can be sent until it does.",
  support: "A customer-support chat record - kept unless you tick it.",
  title: "Forget a time frame",
  to: "To",
  under: "Choose some days. Jarvis lists what it learned and your chats from then - untick " +
    "anything you want to keep, then tap Forget these. Nothing is removed until you approve the " +
    "card, and for 10 minutes one tap on Undo puts it all back.",
  undo: "Undo",
  undo_left: "{minutes} min left to undo",
  waiting: "Waiting for your yes on the approval card. Nothing is removed until you approve " +
    "it - saying yes out loud does not.",
});

/** Where the quickbar leaves "open Brain at Forget a time frame" (main.js). */
export const BRAIN_PLACE_KEY = "jarvis.brain.place";
/** The one place it can name. */
export const PLACE = "forget-range";
/** "Earlier chats" in the Jarvis bar (the chat audit, 2026-09-28): the
 *  History tab itself, left under the same key. */
export const HISTORY_PLACE = "history";
/** Said on the page (a window event) when chats were removed or put back -
 *  a card approved, an Undo - so History's list is read again at once. */
export const HISTORY_CHANGED = "jarvis-history-changed";

/** The PC's quick choices, in its order, when it has not said them yet. */
export const PRESETS = Object.freeze([
  { id: "today", label: "Today" },
  { id: "yesterday", label: "Yesterday" },
  { id: "this_week", label: "This week" },
  { id: "last_week", label: "Last week" },
  { id: "last_7_days", label: "The last 7 days" },
  { id: "this_month", label: "This month" },
  { id: "last_month", label: "Last month" },
]);

/** `{name}` and friends filled in. */
export function fill(template, values = {}) {
  return String(template).replace(/\{(\w+)\}/g, (m, k) => (k in values ? String(values[k]) : m));
}

const text = (v) => (typeof v === "string" ? v : "");
const num = (v) => (typeof v === "number" && Number.isFinite(v) ? v : 0);

/** "2026-09-01" or "2026-09-28T09:30" - what the PC reads and writes. */
export function isWhen(s) {
  return typeof s === "string" && /^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2})?$/.test(s);
}

/** The date part, for an `<input type="date">`. */
export function dayOf(s) {
  return isWhen(s) ? s.slice(0, 10) : "";
}

/** GET /api/memory/forget_range, as the page uses it. */
export function readStatus(v) {
  if (!v || typeof v !== "object") return { available: false, why: WORDS.missing };
  if (v.available === false) return { available: false, why: text(v.why) || WORDS.missing };
  const u = v.undo && typeof v.undo === "object" ? v.undo : null;
  const a = v.asked && typeof v.asked === "object" ? v.asked : null;
  const l = v.last && typeof v.last === "object" ? v.last : null;
  return {
    available: true,
    waiting: v.waiting === true,
    undo: u ? {
      secondsLeft: num(u.seconds_left),
      minutesLeft: num(u.minutes_left),
      facts: num(u.facts),
      chats: num(u.chats),
      said: text(u.said),
    } : null,
    last: l ? { outcome: text(l.outcome), message: text(l.message) } : null,
    asked: a && isWhen(a.from) && isWhen(a.to) ? {
      id: text(a.id),
      from: a.from,
      to: a.to,
      said: text(a.said),
      kinds: Array.isArray(a.kinds) ? a.kinds.filter((k) => k === "facts" || k === "chats") : [],
    } : null,
    maxItems: num(v.max_items) || 200,
    presets: Array.isArray(v.presets) && v.presets.length
      ? v.presets.filter((p) => p && typeof p.id === "string").map((p) => ({ id: p.id, label: text(p.label) }))
      : PRESETS.slice(),
  };
}

/** GET /api/memory/forget_range/preview, as the page uses it. */
export function readPreview(v) {
  if (!v || typeof v !== "object") return { available: false, why: WORDS.missing };
  if (v.available === false) return { available: false, why: text(v.why) || WORDS.missing };
  const f = v.frame && typeof v.frame === "object" ? v.frame : {};
  const facts = (Array.isArray(v.facts) ? v.facts : [])
    .filter((x) => x && Number.isInteger(x.id))
    .map((x) => ({
      id: x.id, text: text(x.text), label: text(x.label),
      pinned: x.pinned === true, betweenUs: x.between_us === true,
    }));
  const chats = (Array.isArray(v.chats) ? v.chats : [])
    .filter((x) => x && typeof x.id === "string")
    .map((x) => ({
      id: x.id, title: text(x.title), label: text(x.label), spills: x.spills === true,
      // The chat audit (2026-09-28): what kind of chat it is, and whether it
      // starts ticked - a customer-support record does not (the owner:
      // "Forget a time frame" asks before removing a support chat).
      kind: ["chat", "live", "support", "chatbot", "compare"].includes(x.kind) ? x.kind : "chat",
      ticked: x.ticked !== false && x.kind !== "support",
    }));
  const counts = v.counts && typeof v.counts === "object" ? v.counts : {};
  return {
    available: true,
    hidden: v.hidden === true,
    frame: { from: text(f.from), to: text(f.to), said: text(f.said) },
    kinds: Array.isArray(v.kinds) ? v.kinds.slice() : ["facts", "chats"],
    facts,
    chats,
    counts: { facts: num(counts.facts), chats: num(counts.chats) },
    tooMany: v.too_many === true,
    empty: v.empty === true,
    said: text(v.said),
    chatsWhy: text(v.chats_why),
  };
}

/**
 * "Forget these": the ids still ticked, in the list's own order, and the
 * two dates exactly as the PC wrote them. `ticked` holds "fact:<id>" and
 * "chat:<id>".
 */
export function forgetBody(preview, ticked) {
  const on = ticked instanceof Set ? ticked : new Set(ticked || []);
  return {
    from: preview.frame.from,
    to: preview.frame.to,
    facts: preview.facts.filter((x) => on.has(`fact:${x.id}`)).map((x) => x.id),
    chats: preview.chats.filter((x) => on.has(`chat:${x.id}`)).map((x) => x.id),
  };
}

/** Every item ticked - how a fresh list starts - except a customer-support
 *  chat's record, which goes only when the owner ticks it. */
export function allTicked(preview) {
  return new Set([
    ...preview.facts.map((x) => `fact:${x.id}`),
    ...preview.chats.filter((x) => x.ticked !== false).map((x) => `chat:${x.id}`),
  ]);
}

/** The tag beside a chat of a kind that is not an ordinary chat. */
export function chatKindTag(kind) {
  return kind && kind !== "chat" ? WORDS[`kind_${kind}`] || "" : "";
}

/** "Forget these (3)". */
export function forgetLabel(n) {
  return `${WORDS.forget} (${n})`;
}

/** The Undo line: what was done, and how long is left. */
export function undoLine(undo) {
  if (!undo) return "";
  return `${undo.said} ${fill(WORDS.undo_left, { minutes: undo.minutesLeft || 1 })}.`;
}
