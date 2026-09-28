/**
 * Chat history, in the Brain window's History tab - JARVIS-API.md section
 * 18, "Chat history" (backend/chat-history.patch, jarvis_chat_log.py).
 *
 * The PC keeps each conversation - typed, pasted and spoken - encrypted, on
 * the PC, when "Keep chat history on this PC" is on (the owner's default,
 * CLAUDE.md 2026-09-24). This module reads what the PC sends and draws it;
 * brain.js holds the state and calls the four Rust commands
 * (src-tauri/src/brain/history.rs).
 *
 * - The list: title, when, which app, a "voice" mark if anything in it was
 *   said aloud, a "read outside text" mark once Jarvis read text that was
 *   not the owner's (a web page, a file, a tool's output). Newest first,
 *   with "Load older".
 * - One conversation, read-only. Where a turn's words came from is said
 *   quietly under it when they were not typed or spoken by the owner.
 * - Delete ONE, after a confirm. There is no "delete all" here or on the
 *   PC: irreversible bulk actions stay off the API.
 * - The switch and "Delete conversations older than" are drawn by brain.js
 *   with the words below, the same shape as the learning switch.
 *
 * Everything the PC sends goes in as text (`el()` in brain.js uses
 * `textContent`), never as markup: a transcript is the owner's words and
 * the model's, and neither may become an element.
 *
 * @module history-view
 */
import { isSideTalk, SEEN } from "./live-rules.js";

/** Section 5's words. The phone says the same (JARVIS-API.md section 18). */
export const SWITCH_LABEL = "Keep chat history on this PC";
export const SWITCH_DETAIL =
  "Your chats, including what you say to Jarvis by voice, are kept on this PC, " +
  "encrypted. Nothing is sent anywhere.";
export const OFF_REPLY =
  "Chat history is off. Nothing new is kept. What is already kept stays until you delete it.";
export const ON_REPLY = "Chat history is on.";
export const DENIED_REPLY = "Chat history stays off: the card was denied or ran out of time.";

/** "Delete conversations older than", in the order shown. */
export const KEEP_CHOICES = Object.freeze([
  { days: 0, label: "Never" },
  { days: 30, label: "30 days" },
  { days: 90, label: "90 days" },
  { days: 365, label: "1 year" },
]);

/** One page of the list (the PC's default). */
export const PAGE = 30;

/** Which app a conversation was had in: the row's tag, and its longer
 *  title. The tags are the phone's too (one wording, 2026-09-24). */
export const DEVICE_TAGS = Object.freeze({
  desktop: { tag: "PC", words: "Had in the Jarvis bar on this PC." },
  hud: { tag: "HUD", words: "Had in the HUD window on this PC." },
  phone: { tag: "phone", words: "Had on your phone." },
});

/** The row tag for a device; one the PC did not name is "unknown". */
export function deviceTag(device) {
  return DEVICE_TAGS[device] || { tag: "unknown", words: "The PC did not say which app this was had in." };
}

/**
 * How a user turn's words are labelled when they are NOT the owner's own
 * typing or voice. Typed and voice say nothing: they are the usual case, and
 * a label on every line would be noise. Anything the PC does not know
 * (including a missing tag) is "not known where from" - never silence.
 */
export const PROVENANCE_WORDS = Object.freeze({
  typed: "",
  voice: "",
  shared: "shared from another app",
  pasted: "pasted",
  clipboard: "from clipboard",
  picture_caption: "sent with a picture",
  voice_unverified: "said aloud, but not confirmed by this PC",
  unknown: "not known where from",
});

/** The tainted line: under an opened conversation that read outside text,
 *  and the title of each "read outside text" mark. The phone's words too. */
export const TAINT_TITLE =
  "In this conversation Jarvis read text that did not come from you - a web " +
  "page, a file, an email or another tool's output - from the marked message on.";

/** Under a question whose answer the PC did not keep (`answer_kept: false`):
 *  a cloud model's answer, or one that did not finish. The PC does not say
 *  which, so neither does this. The phone's ChatLog.NOT_KEPT_LINE. */
export const NOT_KEPT_LINE =
  "Jarvis's answer to this was not kept: it came from a cloud model, or it did not finish.";

/** Said with Delete, in both apps (ease-of-use audit 2026-09-27, #7), when
 *  there is nothing to offer: the chat taught no fact still in use, or this
 *  PC cannot list them. The phone's ChatLog.DELETE_KEEPS_FACTS. */
export const DELETE_KEEPS_FACTS =
  "Deleting a chat does not forget facts Jarvis learned from it. Forget those one by one in the Brain.";

/* ── Deleting a chat offers to forget the facts it taught (2026-09-28) ──
 * JARVIS-API.md section 79; the phone's ChatLog, word for word. The list
 * comes from brain_conversation_facts (a read, hidden like every memory
 * list). NOTHING IS TICKED to start with: deleting a chat must never widen
 * into forgetting by itself - the owner ticks each fact to forget. Each
 * ticked fact is then forgotten through the ordinary Forget, one at a time. */

/** Above the list, with how many facts the chat taught. */
export function chatFactsIntro(n) {
  return n === 1
    ? "Jarvis learned 1 fact from this chat. It is kept unless you tick it - a ticked fact is forgotten, like Forget in the Brain."
    : `Jarvis learned ${n} facts from this chat. They are kept unless you tick them - each ticked fact is forgotten, like Forget in the Brain.`;
}

/** While the memory lists are hidden: the facts are not shown, and kept. */
export function chatFactsHiddenLine(n) {
  return `Jarvis learned ${n} ${n === 1 ? "fact" : "facts"} from this chat. `
    + "Your memory lists are hidden, so they are kept. To forget any, show the memory lists first.";
}

/** The Delete button's words, with how many ticked facts go with it. */
export function deleteChatButton(n) {
  if (!n) return "Delete the chat";
  return `Delete the chat and forget ${n} ${n === 1 ? "fact" : "facts"}`;
}

/** The "are you sure?" before deleting, with the ticked facts named. */
export function deleteAndForgetQuestion(c, facts) {
  const n = facts.length;
  if (!n) {
    return `Delete this conversation?\n\n${c.title || "(no title)"}\n\n`
      + "It is removed from this PC. This cannot be undone. The facts it taught are kept.";
  }
  const list = facts.map((f) => `- ${f.text}`).join("\n");
  return `Delete this conversation and forget ${n} ${n === 1 ? "fact" : "facts"}?\n\n`
    + `${c.title || "(no title)"}\n\nForget:\n${list}\n\n`
    + "The chat is removed from this PC and cannot be brought back. A forgotten fact is not used again; it stays in Jarvis's history until you erase its words.";
}

/** What happened, in one sentence. */
export function deleteDoneWords({ gone = false, forgot = 0, failed = 0 } = {}) {
  const chat = gone ? "That conversation was already deleted." : "Deleted from this PC.";
  if (!forgot && !failed) return chat;
  const done = forgot ? ` Forgot ${forgot} ${forgot === 1 ? "fact" : "facts"}.` : "";
  const bad = failed
    ? ` ${failed} ${failed === 1 ? "fact" : "facts"} could not be forgotten - try Forget on ${failed === 1 ? "it" : "them"} in the Brain.`
    : "";
  return chat + done + bad;
}

/**
 * brain_conversation_facts's answer, read: {available, facts: [{id, text}],
 * hiddenCount, why}. An older PC (`available: false`) or anything odd is
 * "nothing to offer", and Delete asks exactly as it always did.
 */
export function readChatFacts(v) {
  const o = v && typeof v === "object" ? v : {};
  if (o.available === false) return { available: false, facts: [], hiddenCount: 0, why: text(o.why) };
  const facts = (Array.isArray(o.facts) ? o.facts : [])
    .filter((f) => f && Number.isInteger(f.id) && f.id > 0 && typeof f.text === "string" && f.text.trim())
    .map((f) => ({ id: f.id, text: f.text.trim() }));
  const hiddenCount = o.hidden === true ? Math.max(0, num(o.hidden_count) || 0) : 0;
  return { available: true, facts, hiddenCount, why: "" };
}

const num = (v) => (typeof v === "number" && Number.isFinite(v) ? v : null);
const text = (v) => (typeof v === "string" ? v : "");

/** The words under a user turn, or "" for the owner's own typing or voice. */
export function provenanceWords(tag) {
  const t = text(tag);
  if (Object.prototype.hasOwnProperty.call(PROVENANCE_WORDS, t)) return PROVENANCE_WORDS[t];
  return PROVENANCE_WORDS.unknown;
}

/** The label a keep-days value is shown with; an unknown one is said as it is. */
export function keepLabel(days) {
  const hit = KEEP_CHOICES.find((c) => c.days === days);
  return hit ? hit.label : `${days} days`;
}

/**
 * Whether choosing `to` deletes something now, and so asks first: any
 * limit, when there was none ("Never") or a longer one. Going back to
 * "Never", or to a longer limit, deletes nothing. The phone's
 * `ChatLog.keepNeedsConfirm`.
 */
export function keepNeedsConfirm(from, to) {
  if (!Number.isFinite(to) || to === 0) return false;
  return !Number.isFinite(from) || from === 0 || to < from;
}

/** The question asked (`window.confirm`) before such a change. Both apps. */
export function keepConfirm(to) {
  return `Delete every conversation older than ${keepLabel(to).toLowerCase()} from your PC now, ` +
    "and from then on? This cannot be undone.";
}

/**
 * The next list read, with the older pages already loaded kept under it.
 * The fresh first page replaces the newest rows; the rows "Load older"
 * brought in stay when they are older than everything on that page (a
 * conversation that moved up is not shown twice). A first page that was
 * not full means there is nothing older, so nothing older is kept.
 * Returns `{rows, more}`.
 */
export function refreshRows(shown, page, pageSize, moreBefore) {
  const fresh = Array.isArray(page) ? page : [];
  const full = fresh.length >= pageSize;
  if (!full) return { rows: fresh, more: false };
  const edge = olderThan(fresh);
  const ids = new Set(fresh.map((c) => c.id));
  const older = (Array.isArray(shown) ? shown : []).filter(
    (c) => !ids.has(c.id) && edge !== null && c.updated !== null && c.updated < edge
  );
  return { rows: [...fresh, ...older], more: older.length ? moreBefore : true };
}

/**
 * `GET /api/history`'s answer, read. `available: false` is an older backend
 * (Rust answers `{available: false, why}` for a 404). `hidden` is "Windows
 * Hello for memory lists and chat history" holding the list back (Rust
 * took the conversations out, and kept how many there were).
 */
export function readHistory(answer) {
  const a = answer && typeof answer === "object" ? answer : {};
  if (a.available === false) {
    return { available: false, why: text(a.why).trim(), conversations: [] };
  }
  const list = Array.isArray(a.conversations) ? a.conversations : [];
  const enabled = a.enabled === true;
  return {
    available: true,
    why: "",
    enabled,
    // Recording only when the PC says so: a missing field is not "yes".
    recording: a.recording === true,
    whyNot: text(a.why_not).trim(),
    waiting: a.waiting === true,
    keepDays: num(a.keep_days) ?? 0,
    encrypted: a.encrypted === true,
    hidden: a.hidden === true,
    hiddenCount: num(a.hidden_count) ?? 0,
    conversations: list
      .filter((c) => c && typeof c.id === "string" && c.id)
      .map((c) => ({
        id: c.id,
        title: text(c.title).trim(),
        started: num(c.started),
        updated: num(c.updated),
        turns: num(c.turns) ?? 0,
        device: text(c.device),
        hasVoice: c.has_voice === true,
        tainted: c.tainted === true,
      })),
  };
}

/** `GET /api/history/conversation`'s answer, read. */
export function readConversation(answer) {
  const a = answer && typeof answer === "object" ? answer : {};
  const turns = Array.isArray(a.turns) ? a.turns : [];
  return {
    id: text(a.id),
    title: text(a.title).trim(),
    tainted: a.tainted === true,
    turns: turns
      .filter((t) => t && (t.role === "user" || t.role === "assistant"))
      .map((t) => ({
        role: t.role,
        // Jarvis Live's side-talk marker, in a chat kept before side remarks
        // stopped being kept at all (the owner's answer of 2026-09-28): shown
        // as "(not for Jarvis)", never the raw marker (live-rules.js).
        text: t.role === "assistant" && isSideTalk(text(t.text)) ? SEEN.not_for_me : text(t.text),
        at: num(t.at),
        // Only user turns carry one. Missing on a user turn is "unknown".
        provenance: t.role === "user" ? text(t.provenance) || "unknown" : "",
        readOutside: t.read_outside === true,
        // Only the PC's "false" says so; an older PC sends nothing.
        answerKept: t.answer_kept !== false,
      })),
  };
}

/**
 * The next page added under the rows already shown. A conversation that
 * moved (it got a new turn, so it is newer now) is not shown twice.
 */
export function addPage(rows, page) {
  const seen = new Set(rows.map((r) => r.id));
  return [...rows, ...page.filter((c) => !seen.has(c.id))];
}

/** The `before` for "Load older": the oldest `updated` shown, or null. */
export function olderThan(rows) {
  const times = rows.map((r) => r.updated).filter((t) => t !== null);
  return times.length ? Math.min(...times) : null;
}

/** When, in plain words: "just now", "5 min ago", "3 h ago", or the date
 *  with its weekday ("Tue 22 Sept 2026"), so "Tuesday's chat" can be found. */
export function whenWords(epochSeconds, nowMs = Date.now()) {
  const t = num(epochSeconds);
  if (t === null || t <= 0) return "";
  const s = Math.max(0, Math.round(nowMs / 1000 - t));
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  const d = new Date(t * 1000);
  const day = d.toLocaleDateString("en-GB", { weekday: "short" });
  const date = d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
  return `${day} ${date}`;
}

/** One row's meta line: when it was last added to, and how many turns. */
export function rowMeta(c, nowMs = Date.now()) {
  const parts = [whenWords(c.updated ?? c.started, nowMs)];
  parts.push(`${c.turns} ${c.turns === 1 ? "turn" : "turns"}`);
  return parts.filter(Boolean).join(" · ");
}

/**
 * The line that says why nothing new is being kept although the switch is
 * on, or "". The PC's own `why_not` is shown as it is - "plainly", section
 * 4 - with a plain fallback when it sent none. With the switch off, the
 * switch already says so, and a second "it is off" would only be noise.
 */
export function notRecordingLine(v) {
  if (!v || !v.available || v.recording || !v.enabled) return "";
  return v.whyNot || "Nothing new is being kept right now, and the PC did not say why.";
}

/**
 * The confirm shown before deleting ONE conversation (brain.js asks it with
 * `window.confirm`, like Forget on a fact).
 */
export function deleteQuestion(c, note = "") {
  return (
    `Delete this conversation?\n\n${c.title || "(no title)"}\n\n` +
    `It is removed from this PC. This cannot be undone.\n\n${note || DELETE_KEEPS_FACTS}`
  );
}

/**
 * What a `keep_days` change did, from the PC's reply: how many were deleted
 * by it (`deleted`), or the PC's own `message` when it sent one.
 */
export function keepReply(days, out) {
  const said = out && text(out.message).trim();
  if (said) return said;
  const n = out && num(out.deleted);
  const label = keepLabel(days);
  if (days === 0) return "Conversations are kept until you delete them.";
  const rule = `Conversations older than ${label.replace(/^1 year$/, "a year")} are deleted.`;
  if (n === null) return rule;
  return n === 0
    ? `${rule} None were old enough to go yet.`
    : `${rule} ${n} ${n === 1 ? "was" : "were"} deleted just now.`;
}

/* ==========================================================================
   "Search what was said" and "Find in this chat" (JARVIS-API.md section 71;
   the owner's choice of 2026-09-28, under their answer of 2026-09-27: "A
   search box in History for the owner's own old chats is allowed now
   (shown on screen only; nothing saved, nothing handed to the AI)").

   The search box asks the PC (`brain_history_search`), which opens each
   kept conversation in memory for that one search and keeps nothing. This
   window keeps nothing either: the words typed are not stored anywhere, and
   the results are dropped when the box is cleared. "Find in this chat" is
   done here, over the conversation already open - it asks the PC nothing.
   The phone says the same words (net/ChatLog.kt).
   ========================================================================== */

export const SEARCH_PLACEHOLDER = "Search what was said…";
export const SEARCH_LABEL = "Search what was said in your chats";
/** Under the box while a search is shown. */
export const SEARCH_NOTE =
  "Searched on your PC, in your kept chats only. Nothing is saved and nothing is sent to the AI.";
export const SEARCHING = "Searching…";
export const SEARCH_NONE = "No kept conversation has all of those words.";
/** An older PC: the box narrows the loaded list by title, and says so. The
 *  Rust sends this sentence (brain/history.rs SEARCH_UPDATE). */
export const TITLES_ONLY =
  "This PC's Jarvis can only search titles. To search what was said, update it by running " +
  "apply-patches.ps1 on the PC.";
/** The shortest search sent to the PC; a shorter one filters titles only. */
export const SEARCH_MIN = 2;

export const FIND_LABEL = "Find in this chat";
export const FIND_PLACEHOLDER = "Find in this chat…";
export const FIND_NONE = "Not in this chat.";

/** "Found in 3 messages", or "" when the PC gave no count. */
export function hitsWords(n) {
  if (!Number.isFinite(n) || n <= 0) return "";
  return `found in ${n} ${n === 1 ? "message" : "messages"}`;
}

/** "3 of 7", "1 match", or the "not in this chat" line. */
export function findCountWords(current, total) {
  if (!total) return FIND_NONE;
  if (total === 1) return "1 match";
  return `${current + 1} of ${total}`;
}

/** The last line under the results: more than shown, or stopped early. */
export function searchMoreWords(v) {
  if (!v) return "";
  if (v.more) return "Showing the newest matches only. Add another word to narrow it down.";
  if (v.partial) {
    return `Stopped after the newest ${v.searched} conversations to stay quick. ` +
      "Add another word to narrow it down.";
  }
  return "";
}

function readParts(parts) {
  return (Array.isArray(parts) ? parts : [])
    .filter((p) => p && typeof p.text === "string")
    .map((p) => ({ text: p.text, hit: p.hit === true }));
}

/**
 * `GET /api/history/search`'s answer, read. `available: false` is an
 * older PC (Rust answers `{available: false, why}` for a 404 or 501).
 * `queryOk: false` is a search the PC would not run (too short or too
 * long), with its sentence in `why`.
 */
export function readSearch(answer) {
  const a = answer && typeof answer === "object" ? answer : {};
  if (a.available === false) {
    return { available: false, why: text(a.why).trim() || TITLES_ONLY, conversations: [] };
  }
  const list = Array.isArray(a.conversations) ? a.conversations : [];
  return {
    available: true,
    queryOk: a.query_ok !== false,
    why: text(a.why).trim(),
    whyNot: text(a.why_not).trim(),
    more: a.more === true,
    partial: a.partial === true,
    searched: num(a.searched) ?? 0,
    conversations: list
      .filter((c) => c && typeof c.id === "string" && c.id)
      .map((c) => {
        const s = c.snippet && typeof c.snippet === "object" ? c.snippet : {};
        return {
          id: c.id,
          title: text(c.title).trim(),
          started: num(c.started),
          updated: num(c.updated),
          turns: num(c.turns) ?? 0,
          device: text(c.device),
          hasVoice: c.has_voice === true,
          tainted: c.tainted === true,
          hits: num(c.hits) ?? 0,
          snippet: {
            role: ["user", "assistant", "title"].includes(s.role) ? s.role : "user",
            at: num(s.at),
            before: s.before === true,
            after: s.after === true,
            parts: readParts(s.parts),
          },
        };
      }),
  };
}

/**
 * Draws a snippet's parts into `box`: plain text, and each matched word in
 * a `<mark>`. Text only (`el` sets `textContent`), so nothing the PC sends
 * becomes markup. "…" where the PC cut the message.
 */
export function renderSnippet(box, snippet, { el }) {
  box.replaceChildren();
  const who = snippet.role === "assistant" ? "Jarvis: " : snippet.role === "title" ? "" : "You: ";
  if (who) box.append(el("span", "search-who", who));
  if (snippet.before) box.append("…");
  for (const p of snippet.parts) {
    box.append(p.hit ? el("mark", "search-hit", p.text) : document.createTextNode(p.text));
  }
  if (snippet.after) box.append("…");
}

/** The words to find, as one pattern: each word of `needle`, any case. */
function findPattern(needle) {
  const words = String(needle || "").trim().split(/\s+/).filter((w) => w.length >= 1);
  if (!words.length) return null;
  const escaped = words
    .sort((a, b) => b.length - a.length)
    .map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  return new RegExp(escaped.join("|"), "giu");
}

/**
 * Where `needle`'s words are in an open conversation: `[{turn, start,
 * end}]`, in reading order. Any of the words counts (the search found the
 * conversation because every word is SOMEWHERE in it; each place is worth
 * stepping to). Offsets are into each turn's text as the PC sent it.
 */
export function findMatches(conv, needle) {
  const rx = findPattern(needle);
  if (!rx || !conv || !Array.isArray(conv.turns)) return [];
  const out = [];
  conv.turns.forEach((t, turn) => {
    const s = text(t.text);
    rx.lastIndex = 0;
    let m;
    while ((m = rx.exec(s)) !== null) {
      if (!m[0].length) { rx.lastIndex += 1; continue; }
      out.push({ turn, start: m.index, end: m.index + m[0].length });
    }
  });
  return out;
}

/** One turn's text with its matches marked; the current one is `.find-current`. */
function markedText(el, s, matches, current) {
  const p = el("p", "history-text");
  if (!matches.length) {
    p.textContent = s;
    return p;
  }
  let at = 0;
  for (const m of matches) {
    if (m.start > at) p.append(document.createTextNode(s.slice(at, m.start)));
    const mark = el("mark", m === current ? "find-hit find-current" : "find-hit", s.slice(m.start, m.end));
    p.append(mark);
    at = m.end;
  }
  if (at < s.length) p.append(document.createTextNode(s.slice(at)));
  return p;
}

/**
 * Draws one conversation, read-only, into `box`. `helpers.el` is brain.js's
 * text-only element builder. `find`, when given, is `{matches, current}`
 * from findMatches(): those places are marked, the current one apart.
 */
export function renderTranscript(box, conv, { el }, find = null) {
  box.replaceChildren();
  if (conv.tainted) box.append(el("p", "history-taint-note", TAINT_TITLE));
  if (!conv.turns.length) {
    box.append(el("p", "empty", "Nothing was kept from this conversation."));
    return;
  }
  const matches = find && Array.isArray(find.matches) ? find.matches : [];
  const current = matches.length ? matches[Math.max(0, Math.min(matches.length - 1, find.current || 0))] : null;
  const list = el("ol", "history-turns");
  conv.turns.forEach((t, index) => {
    const item = el("li", "history-turn");
    item.dataset.role = t.role;
    const head = el("div", "history-turn-head");
    head.append(el("span", "history-who", t.role === "user" ? "You" : "Jarvis"));
    const when = whenWords(t.at);
    if (when) head.append(el("span", "history-when", when));
    const from = t.role === "user" ? provenanceWords(t.provenance) : "";
    if (from) head.append(el("span", "history-from", from));
    if (t.readOutside) {
      const mark = el("span", "history-mark history-mark-taint", "read outside text");
      mark.title = TAINT_TITLE;
      head.append(mark);
    }
    item.append(head);
    item.append(markedText(el, text(t.text), matches.filter((m) => m.turn === index), current));
    if (t.role === "user" && t.answerKept === false) {
      item.append(el("p", "history-not-kept", NOT_KEPT_LINE));
    }
    list.append(item);
  });
  box.append(list);
}
