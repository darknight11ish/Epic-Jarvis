/**
 * Where a spoken answer is cut into pieces, one piece per `speak_reply`.
 * Pure, no page in it (tests/speech-pieces.mjs), and the same rule, with
 * the same numbers and the same word list, as the phone's
 * `SpeechText.findSentences` (jarvis-client voice/SpeechText.kt). Both
 * apps are held to one list of cases:
 * tests/fixtures/first-piece-cases.json.
 *
 * Every piece after the first is a sentence, as before: text up to `.`,
 * `!` or `?` FOLLOWED BY whitespace - punctuation alone is not enough,
 * because the stream may not have produced the next character yet.
 *
 * The FIRST piece of an answer may be shorter (the owner's decision of
 * 2026-09-24: "speech starts at the first comma"). Making the first
 * sentence's sound is the slowest step before Jarvis says anything, so the
 * first piece is cut as soon as there is a phrase worth saying:
 *
 *   - at `,` `;` or `:` followed by whitespace (so "1,450" and "10:30" are
 *     never cut), once at least FIRST_PIECE_MIN_CHARS characters come
 *     before it, and the word before it is not one a speaker would never
 *     pause after ("and", "the", "to" - AVOID_PAUSE_WORDS);
 *   - at a sentence end, if that comes first;
 *   - or, with no such mark, after FIRST_PIECE_FORCE_WORDS complete words
 *     (at the first one from there that is not in AVOID_PAUSE_WORDS).
 *
 * The idea and the numbers 10 and the word list are from KoljaB's
 * stream2sentence (MIT; stream2sentence.py `minimum_first_fragment_length`
 * and avoid_pause_words.py, copied and lowercased - THIRD-PARTY-NOTICES.txt).
 * The code is written here.
 */

/** Characters that must come before a first-piece cut at `,` `;` `:`. */
export const FIRST_PIECE_MIN_CHARS = 10;
/** Complete words after which the first piece is cut even with no mark. */
export const FIRST_PIECE_FORCE_WORDS = 12;
/** The marks the first piece may end at, besides a sentence end. */
export const FIRST_PIECE_MARKS = ",;:";

/** Words a speaker does not pause after - stream2sentence's
 *  avoid_pause_words.py, in its order, lowercased, each word once. */
export const AVOID_PAUSE_WORDS = Object.freeze([
  // conjunctions
  "and", "or", "but", "so", "for", "nor", "yet",
  // prepositions
  "in", "on", "at", "by", "with", "about", "of", "to", "from", "as", "over", "under",
  "through", "between", "during", "there",
  // articles
  "a", "an", "the",
  // possessives and demonstratives
  "my", "your", "his", "her", "its", "our", "their", "this", "that", "these", "those",
  // auxiliary verbs
  "is", "are", "was", "were", "am", "be", "been", "being", "do", "does", "did", "have",
  "has", "had", "can", "could", "shall", "should", "will", "would", "may", "might", "must",
  // pronouns
  "i", "we", "you", "he", "she", "it", "they", "who", "whom", "whose", "which",
  // quantifiers
  "some", "many", "few", "all", "any", "most", "much", "none", "several",
  // adverbs
  "very", "too", "just", "quite", "almost", "nearly", "only",
  // interrogatives
  "what", "where", "when", "why", "how",
  // subordinating conjunctions
  "although", "because", "if", "since", "though", "while", "until", "unless",
]);

const AVOID = new Set(AVOID_PAUSE_WORDS);

/** Whitespace, the same six characters on both apps (Java's `\s`). */
const isSpace = (c) => c === " " || c === "\t" || c === "\n" || c === "\r" || c === "\f" || c === "\v";

/** The last word of `text`, without the punctuation around it, lowercased. */
function lastWord(text) {
  const words = text.trim().split(/[ \t\n\r\f\v]+/);
  return words[words.length - 1].replace(/^[^\p{L}\p{N}']+|[^\p{L}\p{N}']+$/gu, "").toLowerCase();
}

/** `text` cut after `end`, and past the whitespace that follows. */
function cutAt(text, end) {
  let consumed = end;
  while (consumed < text.length && isSpace(text[consumed])) consumed += 1;
  return { piece: text.slice(0, end), consumed };
}

/** The first piece of an answer: see the top of this file. */
function firstPiece(text) {
  let words = 0;
  for (let i = 0; i < text.length - 1; i += 1) {
    const c = text[i];
    if (isSpace(c) || !isSpace(text[i + 1])) continue;
    words += 1;
    const piece = text.slice(0, i + 1);
    if (c === "." || c === "!" || c === "?") return cutAt(text, i + 1);
    if (FIRST_PIECE_MARKS.includes(c)) {
      const before = piece.slice(0, -1);
      if (before.trim().length >= FIRST_PIECE_MIN_CHARS && !AVOID.has(lastWord(before))) {
        return cutAt(text, i + 1);
      }
    }
    if (words >= FIRST_PIECE_FORCE_WORDS && !AVOID.has(lastWord(piece))) return cutAt(text, i + 1);
  }
  return null;
}

/**
 * The next piece of `text` (what has arrived and not yet been cut) to
 * speak: `{ piece, consumed }`, where `consumed` is how far into `text` it
 * reached, trailing whitespace included - or null when no piece is
 * complete yet. `first`: nothing of this answer has been cut yet.
 */
export function nextSpeechPiece(text, first) {
  if (first) return firstPiece(text);
  const match = text.match(/^([\s\S]*?[.!?])\s+/);
  return match ? { piece: match[1], consumed: match[0].length } : null;
}
