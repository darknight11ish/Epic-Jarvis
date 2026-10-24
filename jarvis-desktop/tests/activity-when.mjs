/**
 * "When" on an Activity row: the decision time, read under either name
 * (src/brain.js `activityWhen`; docs/JARVIS-API.md section 42.1).
 *
 * THE BUG (bug audit 2026-10-24, C3). `jarvis_gate.history()` sends
 * `created`/`decided` - measured on the live gate at 13:52 PT, where a
 * decided row's `decided` was a number like `1792875072.03678` and there was
 * no `decided_at` key at all. `activityWhen` read only `h.decided_at`, so a
 * decided card fell back to `created` and showed the RAISE time as if it were
 * the decision time.
 *
 * WHAT MUST HOLD NOW. Same function, both wire shapes:
 * - the decision time when the row has one, under `decided_at` (the alias
 *   added 2026-10-24) or `decided` (the column an older PC sends);
 * - else the raise time, under `created_at` or `created`;
 * - else 0, never a made-up time or NaN;
 * - and the same answer for a new PC (aliases) and an old one (columns only),
 *   which is the whole of "backward AND forward compatible".
 *
 * The function is LIFTED OUT OF THE REAL brain.js and run (`new
 * Function`), not copied here, the same way bar-primer.mjs runs `syncPrimer` -
 * so a rename or a revert in brain.js fails this file rather than silently
 * passing against a stale copy. Browser-free on purpose:
 *
 *     node tests/activity-when.mjs
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const BRAIN = readFileSync(join(HERE, "..", "src", "brain.js"), "utf8");

/** The whole `function <name>(...) { ... }` block, braces counted. */
function functionSource(source, name) {
  const opening = source.match(new RegExp(`function\\s+${name}\\s*\\([^)]*\\)\\s*\\{`));
  assert.ok(opening, `brain.js has no function ${name}`);
  const start = opening.index;
  let depth = 0;
  for (let i = start; i < source.length; i += 1) {
    if (source[i] === "{") depth += 1;
    else if (source[i] === "}") {
      depth -= 1;
      if (depth === 0) return source.slice(start, i + 1);
    }
  }
  throw new Error(`${name} never closes`);
}

const activityWhen = new Function(
  `${functionSource(BRAIN, "activityWhen")}; return activityWhen;`)();

const fails = [];
const check = (name, fn) => {
  try { fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

// The live gate's own measured value, kept as a decimal with a fraction so a
// reader can see it is the real shape and not a round number.
const RAISED = 1792800000.5;
const DECIDED = 1792875072.03678;

check("an OLD PC's row (only `decided`) shows the decision time, not the raise time", () => {
  assert.equal(activityWhen({ id: "old", created: RAISED, decided: DECIDED }), DECIDED);
  // The number, not a string, is what the gate sends; a string still reads.
  assert.equal(activityWhen({ created: RAISED, decided: String(DECIDED) }), DECIDED);
});

check("a NEW PC's row (both aliases) shows the same decision time", () => {
  assert.equal(activityWhen({
    created: RAISED, decided: DECIDED, created_at: RAISED, decided_at: DECIDED,
  }), DECIDED);
  // The alias is read first when both are present; they are equal on the real
  // wire, so this only pins which one wins if they ever are not.
  assert.equal(activityWhen({ created: 1, decided: 100, created_at: 2, decided_at: 200 }), 200);
});

check("a pending row has no decision time, so it shows when it was raised", () => {
  // The gate sends both decision keys as null on a waiting card.
  assert.equal(activityWhen({
    created: RAISED, created_at: RAISED, decided: null, decided_at: null,
  }), RAISED);
  // An older PC's pending row carries only the column names.
  assert.equal(activityWhen({ created: RAISED, decided: null }), RAISED);
});

check("`created_at` alone is enough, as it was always meant to be", () => {
  assert.equal(activityWhen({ created_at: RAISED }), RAISED);
  assert.equal(activityWhen({ created: RAISED }), RAISED);
});

check("a zero or missing time is NOT a time: it never wins, and never NaN", () => {
  // `decided: 0` is "not decided", not 1 January 1970.
  assert.equal(activityWhen({ created: RAISED, decided: 0 }), RAISED);
  assert.equal(activityWhen({ created: RAISED, decided_at: 0 }), RAISED);
  assert.equal(activityWhen({}), 0);
  assert.equal(activityWhen({ created: null, decided: null }), 0);
  assert.equal(activityWhen({ created: "not a time", decided: "nonsense" }), 0);
  for (const row of [{}, { decided: "x" }, { created: -5 }]) {
    assert.ok(Number.isFinite(activityWhen(row)), `not finite for ${JSON.stringify(row)}`);
    assert.equal(activityWhen(row) >= 0, true);
  }
});

console.log(fails.length
  ? `\n${fails.length} failed: ${fails.join(", ")}`
  : "\nActivity's when: the decision time under either name, the raise time only as the fallback");
process.exit(fails.length ? 1 : 0);
