/**
 * A Today board that could not be READ is not an empty day (silent-failure
 * audit 2026-10-27, row 5).
 *
 * WHY THIS SUITE EXISTS. `GET /api/today/cockpit` failing used to reach the
 * page as "no board": Rust turned every failure into `None` and merged nothing,
 * and today.js/brain.js draw no board exactly like a quiet day - no "Due now",
 * no "Next steps", and the said-I'd-do switch reading off. An unanswered
 * question was drawn as the answer "nothing is due", on the one board that
 * exists so a due reminder is not missed.
 *
 * WHAT IT PROVES, without a browser:
 *   1. the marker's spelling is ONE word in both halves - Rust's
 *      `COCKPIT_ERROR_KEY` and the field `coming-up.js` reads - because a typo
 *      there would switch the whole fix off silently;
 *   2. `readSchedule` keeps three cases apart: a board that was read, a PC
 *      with no board at all (no marker: an older backend, nothing to say), and
 *      a read that FAILED (`cockpitError: true`, no board);
 *   3. the page draws the explicit sentence, and a Retry, for the failed read;
 *   4. the words never say the day is clear, and name no technical thing.
 *
 * The rendered page half is `tests/today.mjs`'s "a read that FAILED is said"
 * check (it drives brain.html, so it needs Playwright); this file is the part
 * that runs anywhere.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { readSchedule } from "../src/coming-up.js";
import { BOARD_UNREADABLE, cockpitOf, cockpitUnreadable } from "../src/today.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (relative) => readFileSync(join(HERE, "..", relative), "utf8");
const rs = read("src-tauri/src/brain/schedule.rs");
const comingUpSrc = read("src/coming-up.js");
const brainSrc = read("src/brain.js");

const fails = [];
const check = (name, fn) => {
  try { fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const LIST = { available: true, jobs: [], todo: [] };

check("the marker is ONE spelling in Rust and in the page", () => {
  const m = rs.match(/COCKPIT_ERROR_KEY: &str = "([a-z_]+)"/);
  assert.ok(m, "schedule.rs no longer names its own key constant");
  assert.equal(m[1], "cockpit_error");
  assert.ok(comingUpSrc.includes(`a.${m[1]} === true`),
    `coming-up.js does not read "${m[1]}" - the marker would never reach the page`);
});

check("a failed board read is carried, with no board invented", () => {
  const v = readSchedule({ ...LIST, cockpit_error: true });
  assert.equal(v.cockpitError, true);
  assert.equal(cockpitOf(v), null, "a failed read left a board in the view");
  assert.equal(cockpitUnreadable(v), true);
});

check("a PC with no board at all is not a failure", () => {
  // An older backend (no `/api/today/cockpit`): Rust sends no marker, and the
  // page must not claim a read failed when there was nothing to read.
  const older = readSchedule(LIST);
  assert.equal(older.cockpitError, false);
  assert.equal(cockpitUnreadable(older), false);
  assert.equal(cockpitOf(older), null);
  // A PC whose scheduler is missing too.
  const missing = readSchedule({ available: false, why: "no scheduler" });
  assert.equal(missing.cockpitError, false);
});

check("a board that WAS read is unchanged, marker and all", () => {
  const board = { available: true, unspoken_commitments_enabled: true, due_reminders: [],
    active_next_steps: [], proposals: [] };
  const v = readSchedule({ ...LIST, cockpit: board });
  assert.deepEqual(cockpitOf(v), board);
  assert.equal(v.cockpitError, false, "a good read was marked as a failure");
  const explicit = readSchedule({ ...LIST, cockpit: board, cockpit_error: false });
  assert.equal(explicit.cockpitError, false);
});

check("the page draws the sentence and a Retry for an unread board", () => {
  const start = brainSrc.indexOf("function todayBoardNodes(v)");
  assert.ok(start > 0, "brain.js no longer has todayBoardNodes");
  const fn = brainSrc.slice(start, start + 1200);
  assert.match(fn, /const cockpit = todayCockpit\(v\);/);
  assert.match(fn, /if \(!todayBoardUnreadable\(v\)\) return \[\];/,
    "the board's failure is back to drawing nothing");
  assert.match(fn, /TODAY_BOARD_UNREADABLE/);
  assert.match(fn, /button\("Retry", loadComingUp\)/, "no way to ask again");
  // ... and the import that makes the sentence available is really there.
  assert.match(brainSrc, /BOARD_UNREADABLE as TODAY_BOARD_UNREADABLE,/);
  assert.match(brainSrc, /cockpitUnreadable as todayBoardUnreadable,/);
});

check("the words say it was not read, and never that the day is clear", () => {
  assert.match(BOARD_UNREADABLE, /could not read today's board/i);
  assert.match(BOARD_UNREADABLE, /does not mean nothing is due/i,
    "the sentence must refuse the empty-day reading out loud");
  assert.doesNotMatch(BOARD_UNREADABLE, /[{}<>]|::|undefined|null|cockpit_error|\bHTTP\b/i,
    "a control character or a technical word reached the owner");
  assert.ok(BOARD_UNREADABLE.length <= 240, "too long for the Today card's line");
});

if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join(", ")}`);
  process.exit(1);
}
console.log("\nan unread Today board says so - it is never drawn as a clear day");
