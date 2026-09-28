/**
 * Reading the answer to "When did this actually stop being true?" - the
 * optional date box Reword and Forget show in Brain › Memory.
 *
 * A play tester (2026-09-27) found three ways the old one-line
 * `Date.parse` went wrong:
 *
 *   * "Sept 20" and "1 March" came back as the year 2001. The browser's date
 *     reader fills a missing year with 2001, not this year, so the fact was
 *     recorded as having stopped being true 25 years ago.
 *   * A date in the future was accepted, though nothing can have stopped
 *     being true next week.
 *   * "last week" showed an error - and then the Forget the owner had
 *     already confirmed was quietly dropped. (That half is fixed in
 *     brain.js's `promptValidTo`, which now asks again instead.)
 *
 * So: a date with no year means the most recent one that has already
 * happened (this year's, or last year's if this year's is still to come),
 * and a future date is refused in plain words.
 *
 * No page, no Tauri: node can import it (tests/forget-date.mjs).
 *
 * @module valid-to
 */

/** Shown under the question when the typed words are not a date. */
export const NOT_A_DATE =
  "is not a date I understand. Try a date like 2026-09-20 or 20 Sept, " +
  "or leave it blank for \"just now\".";

/** Shown under the question when the typed date has not happened yet. */
export const IN_THE_FUTURE =
  "is in the future. Pick a day that has already happened, " +
  "or leave it blank for \"just now\".";

/**
 * The typed answer as a moment, measured against `now` (a Date; today when
 * left out). Returns one of:
 *
 *   { seconds: null }    - left blank: "just now", the usual case. The
 *                          server then uses the moment it receives the
 *                          request (JARVIS-API.md, /api/memory/forget).
 *   { seconds: <number> } - unix seconds, local midnight of that day.
 *   { error: <string> }  - a plain sentence to show before asking again.
 */
export function validToFromText(raw, now) {
  const today = now instanceof Date ? now : new Date();
  const text = String(raw == null ? "" : raw).trim();
  if (!text) return { seconds: null };
  let when;
  // A bare YYYY-MM-DD is built as local midnight, not Date.parse's UTC
  // midnight - west of Greenwich that shift lands the timestamp on the
  // previous calendar day, the same trap the "as of" picker avoids.
  const iso = /^(\d{4})-(\d{1,2})-(\d{1,2})$/.exec(text);
  if (iso) {
    const y = Number(iso[1]);
    const m = Number(iso[2]);
    const d = Number(iso[3]);
    when = new Date(y, m - 1, d);
    // new Date() quietly rolls 31 February into March; refuse it instead.
    if (when.getFullYear() !== y || when.getMonth() !== m - 1 || when.getDate() !== d) {
      return { error: `"${text}" ${NOT_A_DATE}` };
    }
  } else {
    const ms = Date.parse(text);
    if (Number.isNaN(ms)) return { error: `"${text}" ${NOT_A_DATE}` };
    const parsed = new Date(ms);
    when = new Date(parsed.getFullYear(), parsed.getMonth(), parsed.getDate());
    // No year typed: only one number, the day ("Sept 20", "1 March").
    // The browser answered 2001 for it; use the latest one that has
    // already happened instead.
    const numbers = text.match(/\d+/g) || [];
    if (numbers.length <= 1 && !(numbers[0] && numbers[0].length > 2)) {
      when = new Date(today.getFullYear(), parsed.getMonth(), parsed.getDate());
      if (when.getTime() > today.getTime()) {
        when = new Date(today.getFullYear() - 1, parsed.getMonth(), parsed.getDate());
      }
    }
  }
  if (when.getTime() > today.getTime()) return { error: `"${text}" ${IN_THE_FUTURE}` };
  return { seconds: when.getTime() / 1000 };
}
