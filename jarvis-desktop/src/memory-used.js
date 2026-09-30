/**
 * Temporary chat, "Used in this answer" and "Jarvis remembered N things" -
 * the owner's decisions of 2026-09-25 (JARVIS-API.md sections 4, 6, 18.1
 * and 19.5).
 *
 * TEMPORARY CHAT. One tap in the quickbar. While it is on, every question
 * is sent with `temporary: true`, and the PC recalls no facts (no pinned
 * list either), learns nothing (no "Remember:" either) and keeps nothing in
 * the chat history. Tools, approval cards and the rest are unchanged, so it
 * needs no card: it only makes things stricter. Turning it on or off starts
 * a new conversation, so nothing said in one kind is re-sent in the other.
 * A PC without it says so before anything is sent (commands.rs
 * `temporary_chat_available`, and `stream_chat` checks again); an answer
 * whose X-Jarvis-Route does not say `temporary: true` gets a plain warning
 * rather than a pretence.
 *
 * USED IN THIS ANSWER. X-Jarvis-Route lists the facts an answer used by id
 * only (commands.rs passes them on as `memory_ids`, numbers). A quiet line
 * under the answer, "Used 2 memories", opens the list: the words are read
 * from the PC by id then (brain/used.rs `memory_used` - hidden, like every
 * memory list, while Windows Hello hides them), each with Forget and "Erase
 * the words" (the Brain's one-fact commands, held on a stale link, asked
 * about first in the words both apps use). A pinned fact says so.
 *
 * The Brain's "Jarvis remembered 2 things" line opens the same list for the
 * facts automatic learning just saved (the `memory_saved` event's ids).
 *
 * This module holds the words and reads what the PC sends; main.js and
 * brain.js draw. The phone says the same words (net/MemoryUsed.kt).
 *
 * @module memory-used
 */

/** The mode's name, and the one line on the empty chat - both apps. */
export const TEMPORARY_LABEL = "Temporary chat";
export const TEMPORARY_LINE =
  "Temporary chat: Jarvis won't use or learn from your memory, and this chat isn't kept.";
/** The toggle's two titles. */
export const TEMPORARY_ON_TITLE =
  "Start a temporary chat: Jarvis won't use or learn from your memory, and it isn't kept";
export const TEMPORARY_OFF_TITLE = "End the temporary chat and start a normal one";
/** Said when the owner turns it on or off (a new conversation each time). */
export const TEMPORARY_STARTED = "Temporary chat started. Nothing in it is remembered or kept.";
export const TEMPORARY_ENDED = "Temporary chat ended. Your next question starts a normal chat.";

/** A PC whose backend has no temporary chat - commands.rs
 *  TEMPORARY_UNAVAILABLE, word for word. Nothing is sent. */
export const TEMPORARY_UNAVAILABLE =
  "Temporary chat isn't available on this PC's version of Jarvis, so nothing was sent. " +
  "Run apply-patches.ps1 on the PC to update it.";

/** An answer to a temporary question whose route header does not confirm
 *  it - never pretend it was. */
export const TEMPORARY_NOT_CONFIRMED =
  "Your PC did not confirm this was a temporary chat, so this answer may have used your " +
  "memory and the chat may be kept.";

/** A "Remember: ..." in a temporary chat (the route's `remember_off`). */
export const REMEMBER_OFF = "Remember: is off in a temporary chat.";

/** A game or role-play the PC put in a temporary chat by itself (the
 *  owner's decision of 2026-09-27; games-temporary.patch): said under the
 *  answer, both apps (the chat audit, 2026-09-28 - it used to say nothing,
 *  though JARVIS-API section 4 promised the apps showed it). */
export const GAME_TEMPORARY =
  "This looks like a game or role-play, so it's a temporary chat: nothing is kept or learned.";

/**
 * What the route header says about a temporary question, once it is in:
 * "confirmed" (`temporary: true`), "unconfirmed" (anything else - an older
 * PC, or memory the PC cannot switch off), or "" for a normal question -
 * and "game" when the app did NOT ask for a temporary chat but the PC made
 * it one: only a detected game or role-play does that.
 */
export function temporaryOutcome(sentTemporary, route) {
  const temporary = Boolean(route && typeof route === "object" && route.temporary === true);
  if (!sentTemporary) return temporary ? "game" : "";
  return temporary ? "confirmed" : "unconfirmed";
}

/** The facts an answer used, as the route line carries them (`memory_ids`,
 *  whole numbers above 0), each once. */
export function usedIds(route) {
  const ids = route && Array.isArray(route.memory_ids) ? route.memory_ids : [];
  const out = [];
  for (const id of ids) if (Number.isInteger(id) && id > 0 && !out.includes(id)) out.push(id);
  return out;
}

/** "Used 1 memory" / "Used 2 memories" - the quiet line under an answer. */
export function usedLine(n) {
  const count = Number.isInteger(n) && n > 0 ? n : 0;
  if (!count) return "";
  return `Used ${count} ${count === 1 ? "memory" : "memories"}`;
}

/** The list's titles: under an answer, and in the Brain. */
export const USED_TITLE = "Used in this answer";
export const REMEMBERED_TITLE = "Remembered just now";
export const USED_LINE_TITLE = "Show which of your saved facts this answer used.";
export const REMEMBERED_LINE_TITLE = "Show what Jarvis just saved automatically.";
/** The Brain's way on to the whole list, as before. */
export const SHOW_ALL = "Show everything saved automatically";

/** What each fact can say beside its words. */
export const PINNED_MARK = "pinned";
export const PINNED_MARK_TITLE = "On \"Always keep in mind\": Jarvis reads it with every question.";
export const NOT_CURRENT_MARK = "no longer in use";
export const NOT_CURRENT_TITLE =
  "Jarvis no longer uses this fact (it was forgotten, corrected or ran out). An answer about " +
  "the past can still mention it.";

/** A PC without the read route (Rust answers `{available: false}`). */
export const USED_MISSING =
  "Your PC's Jarvis cannot show which facts these were yet - run apply-patches.ps1 on the PC " +
  "to update it.";

/** While Windows Hello hides the memory lists. The quickbar cannot ask
 *  Windows Hello itself: Show is in the Brain. */
export function hiddenLine(n, where = "quickbar") {
  const count = Number.isInteger(n) && n > 0 ? n : 0;
  const what = count === 1 ? "This fact is" : "These facts are";
  const how = where === "brain"
    ? "hidden until Windows Hello confirms it is you."
    : "hidden until Windows Hello confirms it is you - press Show on the Brain's Memory tab.";
  return `${what} ${how}`;
}

/** Ids the PC had no fact for at all. */
export function missingLine(n) {
  const count = Number.isInteger(n) && n > 0 ? n : 0;
  if (!count) return "";
  return count === 1
    ? "1 of them is no longer on this PC."
    : `${count} of them are no longer on this PC.`;
}

const num = (v) => (typeof v === "number" && Number.isFinite(v) ? v : null);
const text = (v) => (typeof v === "string" ? v : "");

/**
 * `memory_used`'s answer, read.
 *
 * `{facts: [{id, text, current, pinned, created, valid_to, erased_at}],
 * missing: [id]}` from the PC; `available: false` (with `why`) from an
 * older one; `hidden: true` with `hidden_count` while Windows Hello hides
 * the memory lists (Rust took the facts out). A fact without a whole-number
 * id is dropped, never guessed. An erased fact never has words here: the
 * PC sends none, and even a stray "[erased]" is not shown.
 */
export function readUsed(answer) {
  const a = answer && typeof answer === "object" ? answer : {};
  const available = a.available !== false && Array.isArray(a.facts);
  const facts = (available ? a.facts : [])
    .filter((f) => f && Number.isInteger(f.id) && f.id > 0)
    .map((f) => {
      const erasedAt = num(f.erased_at);
      return {
        id: f.id,
        text: erasedAt || f.left_out === true ? "" : text(f.text),
        current: f.current === true && !erasedAt,
        pinned: f.pinned === true && f.current === true && !erasedAt,
        validTo: num(f.valid_to),
        erasedAt,
        // Topic controls: the fact's topic was switched off since the answer;
        // the PC sends no words for it (`left_out`).
        leftOut: f.left_out === true && !erasedAt,
      };
    });
  const missing = (available && Array.isArray(a.missing) ? a.missing : [])
    .filter((id) => Number.isInteger(id));
  return {
    available,
    why: available ? "" : text(a.why) || USED_MISSING,
    hidden: available && a.hidden === true,
    hiddenCount: num(a.hidden_count) ?? 0,
    facts,
    missing,
  };
}

/**
 * What one row offers: Forget only on a fact still in use (a forgotten one
 * has nothing to forget), and "Erase the words" on any fact that still has
 * its words - the desktop erases forgotten facts too, as in the Brain.
 */
export function rowActions(f) {
  return {
    forget: Boolean(f && f.current && !f.erasedAt),
    erase: Boolean(f && !f.erasedAt),
  };
}

/* ==========================================================================
 * "Where this came from", and the quote check (feasibility I42/I132,
 * docs/CUTTING-EDGE-2026-09-26-round3-knowledge.md detail 1;
 * docs/JARVIS-API.md section 55)
 *
 * Only saved facts were ever listed under an answer ("Used in this answer",
 * above). A note, a wiki page, a web result or a file the model read was
 * not listed anywhere ("No tool receipt", JARVIS-API.md section 4). This
 * reads GET /api/chat/sources?turn_id=<id> - by the SAME id "Used in this
 * answer" and the right/wrong mark already use - and lists what a reading
 * tool actually returned this turn, by reference only (never a note's or a
 * file's full text, never a web page fetched to preview it), plus which
 * quoted phrases in the answer were not found in any of them.
 *
 * There is no cheap COUNT for this the way `memory_ids` gives "Used in this
 * answer" one: a tool's result is only known once the tool loop finishes,
 * long after X-Jarvis-Route (which carries `turn_id`) was already sent. So
 * `answer-memory.js` fetches this once, quietly, right when an answer
 * finishes, and shows the line only if there is something to show - never
 * a guessed count first, the way "Used 2 memories" can.
 * ========================================================================== */

/** The list's title under an answer. */
export const SOURCES_TITLE = "Where this came from";
/** The quiet line under an answer - a label, not a count (see above). */
export const SOURCES_LINE = "Where this came from";
export const SOURCES_LINE_TITLE = "Show what Jarvis actually read for this answer.";

/** A PC without the read route (Rust answers `{available: false}`). */
export const SOURCES_MISSING =
  "Your PC's Jarvis cannot show where this answer came from yet - run apply-patches.ps1 on " +
  "the PC to update it.";

/** Beside a quoted phrase the PC could not find in what it read this turn -
 *  a warning only: it changes nothing about the answer already shown. */
export const QUOTE_WARNING_TITLE =
  "Jarvis quoted this, but it is not in what Jarvis actually read this turn - it may have " +
  "the quote wrong.";
export const QUOTE_WARNING_LABEL = "not found in what Jarvis read";

/** The plain-English label for each kind `jarvis_sources.py` gives out. */
export const SOURCE_KIND_LABEL = { note: "Note", wiki: "Wiki page", web: "Web", file: "File" };

/** A web source's host only - Jarvis never fetches the page to preview it,
 *  and neither does this app: the full link shows only once the owner taps
 *  it (a real navigation, `data-external`, opened in the real browser). */
export function hostOf(url) {
  try {
    return new URL(url).host || String(url || "");
  } catch {
    return String(url || "");
  }
}

const KNOWN_SOURCE_KINDS = ["note", "wiki", "web", "file"];

/**
 * `chat_sources`'s answer, read.
 *
 * `{sources: [{kind, ref?, url?, path?, title?}], unverified_quotes: [str]}`
 * from the PC; `available: false` (with `why`) from an older one; `hidden:
 * true` with `hidden_count` while Windows Hello hides the memory lists
 * (Rust took every reference out - see brain/sources.rs `redact_sources`).
 * A source of an unknown kind, or with none of `ref`/`url`/`path`, is
 * dropped, never guessed at.
 */
export function readSources(answer) {
  const a = answer && typeof answer === "object" ? answer : {};
  const available = a.available !== false && Array.isArray(a.sources);
  const sources = (available ? a.sources : [])
    .filter((s) => s && KNOWN_SOURCE_KINDS.includes(s.kind))
    .map((s) => ({ kind: s.kind, ref: text(s.ref), url: text(s.url), path: text(s.path),
      title: text(s.title) }))
    .filter((s) => s.ref || s.url || s.path);
  const quotes = (available && Array.isArray(a.unverified_quotes) ? a.unverified_quotes : [])
    .filter((q) => typeof q === "string" && q.trim());
  return {
    available,
    why: available ? "" : text(a.why) || SOURCES_MISSING,
    hidden: available && a.hidden === true,
    hiddenCount: num(a.hidden_count) ?? 0,
    sources,
    quotes,
  };
}

/**
 * One source's plain line: the kind, then whatever it is safe to show. A
 * web source shows its HOST only (never the full link, never a title a
 * website chose); a note, wiki page or file shows its title when there is
 * one, else its reference.
 */
export function sourceLine(s) {
  const label = (s && SOURCE_KIND_LABEL[s.kind]) || "Source";
  if (!s) return label;
  if (s.kind === "web") return `${label}: ${hostOf(s.url)}`;
  const shown = s.title || s.ref || s.path || "";
  return shown ? `${label}: ${shown}` : label;
}

/** True only for a web source with something that looks like a real link -
 *  the one kind an app may ever turn into a clickable, real navigation. */
export function isOpenable(s) {
  return Boolean(s && s.kind === "web" && /^https?:\/\//i.test(s.url || ""));
}
