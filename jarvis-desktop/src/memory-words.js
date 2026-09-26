/**
 * The memory words both apps use - the memory review of 2026-09-27, I8-I11.
 *
 * The phone's net/MemoryWords.kt says exactly the same. Both are held to
 * tests/fixtures/memory-words-cases.json, which tools/gen_memory_words_cases.py
 * writes from the real backend (jarvis_memory's status, jarvis_intake's
 * older-news sentence); tests/memory-words.mjs and the phone's
 * MemoryWordsContractTest read it. Change a word here and the fixture's test
 * fails until the generator (and so the phone) says it too.
 *
 * - statusRows: GET /api/memory/status -> the rows of the memory counts,
 *   including "Answer ordering (re-ranker)" and "Said again" (I8).
 * - cardLines: a review card's `auto_reason` -> its "Not saved
 *   automatically" line, and the "older news" warning on a line of its own
 *   with plain dates (I9).
 * - plainDate / trueFromLine: "2026-01-01" -> "1 January 2026" / "true from
 *   1 January 2026" (I10).
 * - The one wording for a fact no longer in use (I11): "no longer used" in
 *   today's list, "true then" / "no longer true" when looking at a past date.
 *
 * Pure: no DOM, no clock, no locale. Everything the PC sends is read as data.
 *
 * @module memory-words
 */

export const MONTHS = Object.freeze(["January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December"]);

export const WORDS = Object.freeze({
  facts_in_use: "Facts in use",
  no_longer_used_count: "No longer used",
  embedding: "Embedding",
  embedding_words_only: "(matches words only until the real embedding model has downloaded)",
  search_by_meaning: "Search by meaning",
  search_by_meaning_off: "off - facts are found by keyword",
  waiting_to_be_indexed: "Waiting to be indexed",
  overnight: "Overnight tidying",
  overnight_on: "switched on, but not built yet - nothing runs",
  overnight_off: "off (not built yet)",
  reranker: "Answer ordering (re-ranker)",
  reranker_loading: "still loading - answers keep the old order until it is ready",
  reranker_not_started: "not loaded yet - it starts loading with the first question",
  reranker_off_by_setting: "turned off on the PC (JARVIS_MEMORY_RERANK=0)",
  said_again: "Said again",
  said_again_none: "nothing yet",
  repeats: "Repeated cards dropped",
  reason_prefix: "Not saved automatically: ",
  older_news_start: "It sounds older than what Jarvis knows",
  no_longer_used: "no longer used",
  true_then: "true then",
  no_longer_true: "no longer true",
  true_from: "true from",
});

const ISO = /^(\d{4})-(\d{2})-(\d{2})$/;
const ISO_IN_TEXT = /\b(\d{4}-\d{2}-\d{2})\b/g;

function daysIn(y, m) {
  if (m === 2) return (y % 4 === 0 && y % 100 !== 0) || y % 400 === 0 ? 29 : 28;
  return [4, 6, 9, 11].includes(m) ? 30 : 31;
}

/** The words for one day: 1 January 2026. The same in every locale. */
function dayWords(y, m, d) {
  return `${d} ${MONTHS[m - 1]} ${y}`;
}

/** "2026-01-01" -> "1 January 2026"; null for anything that is not a real
 *  day written exactly that way. */
export function plainDate(iso) {
  const m = typeof iso === "string" ? ISO.exec(iso) : null;
  if (!m) return null;
  const [y, mo, d] = [Number(m[1]), Number(m[2]), Number(m[3])];
  if (y < 1 || mo < 1 || mo > 12 || d < 1 || d > daysIn(y, mo)) return null;
  return dayWords(y, mo, d);
}

/** Unix seconds -> "1 January 2026", on this PC's calendar. "" for no time. */
export function plainDateOf(epochSeconds) {
  const t = typeof epochSeconds === "number" ? epochSeconds : Number(epochSeconds);
  if (!Number.isFinite(t) || t <= 0) return "";
  const when = new Date(t * 1000);
  if (Number.isNaN(when.getTime())) return "";
  return dayWords(when.getFullYear(), when.getMonth() + 1, when.getDate());
}

/** A GET /api/memory/auto row's `true_from` -> "true from 1 January 2026", or "". */
export function trueFromLine(iso) {
  const day = plainDate(iso);
  return day ? `${WORDS.true_from} ${day}` : "";
}

const isNum = (v) => typeof v === "number" && Number.isFinite(v);
const numText = (v) => (isNum(v) ? String(v) : null);
const count = (v) => (isNum(v) && Number.isInteger(v) && v >= 0 ? v : null);
const times = (n) => (n === 1 ? "once" : n === 2 ? "twice" : `${n} times`);

/** The re-ranker's row value, or null when there is nothing to say. */
export function rerankerValue(r) {
  if (!r || typeof r !== "object" || Array.isArray(r)) return null;
  switch (r.state) {
    case "on": {
      const parts = [];
      const used = count(r.used);
      if (used !== null) parts.push(`used for ${used} ${used === 1 ? "answer" : "answers"}`);
      const slow = count(r.slow);
      if (slow) {
        parts.push(`too slow ${times(slow)}, so ${slow === 1 ? "that answer" : "those answers"}`
          + " kept the old order");
      }
      return parts.length ? `on - ${parts.join("; ")}` : "on";
    }
    case "loading":
      return WORDS.reranker_loading;
    case "not started":
      return WORDS.reranker_not_started;
    case "off": {
      let why = typeof r.why === "string" ? r.why.trim() : "";
      if (why === "JARVIS_MEMORY_RERANK=0") why = WORDS.reranker_off_by_setting;
      return why ? `off - ${why}` : "off";
    }
    default:
      return null;
  }
}

/** "Said again": how many times the owner told Jarvis something it knew. */
export function saidAgainValue(v) {
  const n = count(v);
  if (n === null) return null;
  return n === 0 ? WORDS.said_again_none : times(n);
}

/**
 * The rows of the memory counts, `[label, value]`, in order. The desktop
 * adds the store's file path ("Store") itself; the phone never shows it.
 */
export function statusRows(s) {
  if (!s || typeof s !== "object" || Array.isArray(s) || s.available === false) return [];
  const out = [];
  const add = (k, v) => {
    if (v !== null && v !== undefined) out.push([k, v]);
  };
  add(WORDS.facts_in_use, numText(s.current));
  add(WORDS.no_longer_used_count, numText(s.retired));
  if (typeof s.embedder === "string" && s.embedder.trim()) {
    add(WORDS.embedding, s.semantic === false
      ? `${s.embedder} ${WORDS.embedding_words_only}` : s.embedder);
  }
  if (s.vector_search === false) add(WORDS.search_by_meaning, WORDS.search_by_meaning_off);
  if (isNum(s.unembedded) && s.unembedded > 0) {
    add(WORDS.waiting_to_be_indexed, numText(s.unembedded));
  }
  add(WORDS.reranker, rerankerValue(s.reranker));
  add(WORDS.said_again, saidAgainValue(s.said_again));
  const st = s.sleep_time;
  if (st && typeof st === "object" && !Array.isArray(st)) {
    add(WORDS.overnight, st.enabled === true ? WORDS.overnight_on : WORDS.overnight_off);
  }
  return out;
}

/**
 * A review card's reason, in two lines: `reason` ("Not saved automatically:
 * from pasted text") and `older` - the PC's "it sounds older" warning, on
 * its own line, with plain dates. Either is null when there is none.
 */
export function cardLines(row) {
  const raw = row && typeof row.auto_reason === "string" ? row.auto_reason : "";
  const i = raw.indexOf(WORDS.older_news_start);
  const before = i >= 0 ? raw.slice(0, i) : raw;
  const after = i >= 0 ? raw.slice(i).trim() : "";
  const reason = before.trim().replace(/\.+$/, "").trim();
  let older = null;
  if (after) {
    older = after.replace(ISO_IN_TEXT, (whole, iso) => plainDate(iso) || iso);
    if (!older.endsWith(".")) older += ".";
  }
  return { reason: reason ? WORDS.reason_prefix + reason : null, older };
}
