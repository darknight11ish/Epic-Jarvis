/**
 * guardian.js - the words and the reading for the Brain's "File history"
 * drawer (Pillar 18's file guardian; JARVIS-API section 140; LM-2C).
 *
 * PURE, so every rule is testable in node without a page: what a snapshot
 * answer means, which rows are drawn and in which order, what the drawer shows
 * for a diff, and what a restore answer should do next. `guardian-panel.js`
 * owns the DOM; this file owns the decisions.
 *
 * THE RULES
 *  - NEWEST FIRST. The PC already answers newest first; this sorts anyway, so
 *    an older backend's order cannot become the drawer's order.
 *  - NO FILE CONTENTS. A row is rebuilt from the keys the contract names
 *    (`path`, `label`, `before_sha256`, `size`, `timestamp`, `when`, `reason`,
 *    `receipt_id`); any other field a future backend sends is dropped rather
 *    than displayed. The list never shows a file's words - only the module's
 *    bounded diff does, and only after the owner asks for it.
 *  - HIDDEN MEANS EVERYTHING IS HIDDEN. While App lock is locked or "Hide
 *    memory lists and chat history" is on, Rust replaces the whole answer with
 *    one sentence (`hidden: true`); this file then draws that sentence and
 *    nothing else - no rows, no count, no path.
 *  - A RESTORE IS ONE REQUEST. A refused restore (the card was denied, nobody
 *    answered, or the PC would not take it) is displayed in the PC's own words
 *    and NOTHING is re-sent and nothing is re-read: no state changed.
 * @module guardian
 */

/** Longest diff this drawer keeps on screen; the PC already bounds it, this is
 *  the page's own second cap so a huge answer cannot become a huge page. */
export const MAX_DIFF_VIEW_CHARS = 70_000;

/** The fixed labels the drawer draws. Every other sentence is the PC's. */
export const WORDS = {
  title: "File history",
  under: "Copies Jarvis took of a file before changing it. It keeps the last versions on this PC; a restore asks first, in the Jarvis bar.",
  empty: "No copies yet - Jarvis has not changed a file it keeps a copy of.",
  missing: "Your PC's Jarvis does not have the file guardian yet. Run apply-patches.ps1 on the PC.",
  hidden_short: "Turn off Hide memory lists to see which files Jarvis kept a copy of.",
  show_diff: "Show the difference",
  restore: "Put this version back",
  restore_ask: "Put this version back? Jarvis will ask you in the Jarvis bar.",
  close_diff: "Close the difference",
  same: "The file is already that version.",
  binary: "One of the two versions is a binary file, so there is no line difference to show.",
  diff_cut: "The difference is long, so only the beginning is shown.",
  stale: "The connection to Jarvis is catching up, so nothing can be sent until it does.",
};

/** Bytes, in the same words the PC uses for the store. */
export function sizeWords(bytes) {
  const n = Number(bytes);
  if (!Number.isFinite(n) || n < 0) return "";
  if (n < 1024) return `${Math.round(n)} bytes`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function textOf(value) {
  return typeof value === "string" ? value : "";
}

/** One row, rebuilt from only the fields the contract names. */
function rowFrom(raw) {
  if (!raw || typeof raw !== "object") return null;
  const path = textOf(raw.path);
  const sha = textOf(raw.before_sha256).toLowerCase();
  if (!path || !sha) return null;
  const because = textOf(raw.reason);
  return {
    path,
    label: textOf(raw.label) || path,
    sha256: sha,
    size: Number.isFinite(Number(raw.size)) ? Number(raw.size) : 0,
    timestamp: Number.isFinite(Number(raw.timestamp)) ? Number(raw.timestamp) : 0,
    when: textOf(raw.when),
    reason: because,
    receiptId: textOf(raw.receipt_id),
  };
}

/**
 * What the drawer should draw for the snapshots route (through
 * brain_read's `guardian_history`). `{missing, hidden, hiddenWords, rows, words}`.
 */
export function snapshotModel(answer) {
  if (!answer || typeof answer !== "object" || answer.available === false) {
    return { missing: true, hidden: false, hiddenWords: "", rows: [], words: "" };
  }
  if (answer.hidden === true) {
    return {
      missing: false,
      hidden: true,
      hiddenWords: textOf(answer.hidden_words) || WORDS.hidden_short,
      rows: [],
      words: "",
    };
  }
  if (answer.ok === false || answer.refused === true) {
    return { missing: false, hidden: false, hiddenWords: "",
             rows: [], words: textOf(answer.words) || WORDS.missing };
  }
  const rows = Array.isArray(answer.snapshots)
    ? answer.snapshots.map(rowFrom).filter(Boolean)
    : [];
  // NEWEST FIRST, whatever order the answer arrived in. The journal index is
  // the tie-breaker so two snapshots in the same second keep the PC's order
  // (the later row first, as the backend lists them).
  rows.sort((a, b) => (b.timestamp - a.timestamp));
  return { missing: false, hidden: false, hiddenWords: "", rows,
           words: textOf(answer.words) };
}

/**
 * What the drawer should draw for `guardian_diff`'s answer: the module's own
 * bounded unified diff, in one <pre>, or the PC's sentence for same/binary/
 * refusal. The page's second cap is applied here; it never completes a cut.
 */
export function diffModel(answer) {
  if (!answer || typeof answer !== "object") {
    return { ok: false, text: "", truncated: false, words: WORDS.missing, hidden: false };
  }
  if (answer.hidden === true) {
    return { ok: false, text: "", truncated: false,
             words: textOf(answer.hidden_words) || WORDS.hidden_short, hidden: true };
  }
  const whole = textOf(answer.diff);
  let shown = whole;
  let truncated = answer.truncated === true;
  if (shown.length > MAX_DIFF_VIEW_CHARS) {
    shown = shown.slice(0, MAX_DIFF_VIEW_CHARS);
    truncated = true;
  }
  const base = textOf(answer.words);
  if (!shown) {
    return { ok: answer.ok !== false, text: "", truncated: false, hidden: false,
             words: base || (answer.same ? WORDS.same : WORDS.binary) };
  }
  return { ok: answer.ok !== false, text: shown, truncated, hidden: false,
           words: base || (truncated ? WORDS.diff_cut : "") };
}

/** The exact two strings a restore sends for one row - never a typed path. */
export function restoreRequest(row) {
  if (!row || typeof row !== "object") return null;
  const path = textOf(row.path);
  const sha = textOf(row.sha256);
  if (!path || !sha) return null;
  return { path, shaBefore: sha };
}

/**
 * What to do with a restore's answer. `refresh` is true ONLY when the PC says
 * it changed the file - a refused card changes nothing, so nothing is re-read
 * and nothing is re-sent.
 */
export function restoreModel(answer) {
  if (!answer || typeof answer !== "object") {
    return { ok: false, changed: false, refresh: false, hidden: false,
             words: WORDS.missing };
  }
  if (answer.hidden === true) {
    return { ok: false, changed: false, refresh: false, hidden: true,
             words: textOf(answer.hidden_words) || WORDS.hidden_short };
  }
  const ok = answer.ok === true;
  const changed = ok && answer.changed === true;
  return {
    ok,
    changed,
    refresh: changed,
    hidden: false,
    words: textOf(answer.words) || (ok ? "" : WORDS.missing),
  };
}

/**
 * The one hidden summary the drawer can show IMMEDIATELY, when App lock or the
 * hidden lists have just turned on and the next read has not come back yet. It
 * carries no row, no count and no path - the same shape Rust's hidden answer
 * has - so the old rows are gone from the screen before the network answers
 * (F13, 2026-10-18).
 */
export function hiddenModel(words = WORDS.hidden_short) {
  return {
    missing: false,
    hidden: true,
    hiddenWords: typeof words === "string" && words ? words : WORDS.hidden_short,
    rows: [],
    words: "",
  };
}
