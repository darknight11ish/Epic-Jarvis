/**
 * antislop.mjs - the Anti-Slop filter's data mapping, without a browser.
 *
 *     node tests/antislop.mjs
 *
 * WHY THIS EXISTS (2026-10-28, the anti-slop UI slice). src/antislop.js turns
 * the PC's `GET /api/antislop` answer into what the card draws, and turns a
 * click into the one change that is sent. Both halves are pure, so they are
 * checked here with no browser at all - which is what lets this run in CI's
 * backend job as well as at the desk. tests/antislop-settings.mjs drives the
 * real page on top of this.
 *
 * The cases below are the shapes a real `jarvis_antislop` answers with, plus
 * the two that matter for honesty: a body with no yes-or-no is never read as
 * "off", and a half-shaped answer keeps what the PC does hold.
 */

import assert from "node:assert/strict";
import * as A from "../src/antislop.js";

const fails = [];
const check = (name, fn) => {
  try { fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/** The PC's own answer, word for word (jarvis_antislop.get_state()). */
const STATE = {
  enabled: false,
  mode: "during",
  scopes: { copy: true, code: true, ui: true },
  dials: { energy: 1, rhythm: 2, motion: 1 },
  show_delivery_gate_on_ui_tasks: true,
  updated_at: 1793164200.0,
};

check("the PC's own shape is read as the card draws it", () => {
  const v = A.readAntislop(STATE);
  assert.equal(v.available, true);
  assert.equal(v.enabled, false);
  assert.equal(v.mode, "during");
  assert.deepEqual(v.scopes.map((s) => s.id), ["copy", "code", "ui"]);
  assert.deepEqual(v.scopes.map((s) => s.on), [true, true, true]);
  assert.deepEqual(v.dials, { energy: 1, rhythm: 2, motion: 1 });
  assert.equal(v.gate, true);
  // The three scope names are the card's own words, in that order.
  assert.deepEqual(v.scopes.map((s) => s.label),
    ["Copy & answers", "Code comments", "Web & UI design"]);
});

check("a body with no yes-or-no is NOT read as off", () => {
  const v = A.readAntislop({ mode: "during" });
  assert.equal(v.available, false);
  assert.equal(v.why, A.MISSING);
  assert.equal(A.readAntislop(null).available, false);
  assert.equal(A.readAntislop({ available: false, why: "no such route" }).why, "no such route");
});

check("a half-shaped answer keeps what the PC really holds", () => {
  // An older backend that answers the switch but not the dials yet.
  const v = A.readAntislop({ enabled: true });
  assert.equal(v.available, true);
  assert.equal(v.enabled, true);
  assert.equal(v.mode, "during", "a missing mode is the default the PC picks");
  assert.deepEqual(v.dials, A.DIAL_DEFAULT);
  assert.deepEqual(v.scopes.map((s) => s.on), [true, true, true],
    "a scope the PC did not name is on, which is what it is");
  assert.equal(v.gate, true);
});

check("a scope the PC turned off is off, and only that one", () => {
  const v = A.readAntislop({ ...STATE, scopes: { copy: true, code: false, ui: true } });
  assert.deepEqual(v.scopes.map((s) => s.on), [true, false, true]);
  assert.equal(A.scopeOn(v, "code"), false);
  assert.equal(A.scopeOn(v, "ui"), true);
});

check("an unknown mode is not invented - it falls to during", () => {
  assert.equal(A.readAntislop({ ...STATE, mode: "sometime" }).mode, "during");
  assert.equal(A.readAntislop({ ...STATE, mode: "after" }).mode, "after");
});

check("a dial outside 1-3 falls back to the default for that dial", () => {
  const v = A.readAntislop({ ...STATE, dials: { energy: 0, rhythm: 4, motion: 3 } });
  assert.deepEqual(v.dials, { energy: 1, rhythm: 2, motion: 3 });
  assert.deepEqual(A.readAntislop({ ...STATE, dials: { energy: "2" } }).dials,
    { energy: 2, rhythm: 2, motion: 1 }, "a numeric string is still the number");
});

check("one dial moved sends all three, with only that one changed", () => {
  const v = A.readAntislop(STATE);
  assert.deepEqual(A.dialsAfter(v, "energy", 3), { energy: 3, rhythm: 2, motion: 1 });
  assert.deepEqual(A.dialsAfter(v, "motion", 3), { energy: 1, rhythm: 2, motion: 3 });
  // A value the PC would refuse is not forwarded as an impossible step.
  assert.deepEqual(A.dialsAfter(v, "energy", 9), { energy: 1, rhythm: 2, motion: 1 });
});

check("each state has its own sentence, and OFF says what it costs", () => {
  assert.match(A.SAID.off, /0 prompt tokens/);
  assert.match(A.OFF_NOTE, /0 prompt tokens/);
  assert.match(A.saidFor("enabled", true), /is on/);
  assert.match(A.saidFor("enabled", false), /is off/);
  assert.match(A.saidFor("code", false), /Code comments/);
  assert.match(A.saidFor("gate", true), /Delivery Gate/);
  assert.match(A.modeSaid("after"), /audit and list findings/);
  assert.match(A.modeSaid("during"), /filter while Jarvis writes/);
});

check("the three scopes and the two modes are exactly the contract's", () => {
  assert.deepEqual(A.SCOPES.map((s) => s.id), ["copy", "code", "ui"]);
  assert.deepEqual(A.MODES.map((m) => m.id), ["during", "after"]);
  assert.deepEqual([...A.DIAL_KEYS], ["energy", "rhythm", "motion"]);
  assert.deepEqual([...A.DIAL_STEPS], [1, 2, 3]);
  // Every scope and mode explains itself: a bare checkbox teaches nothing.
  for (const s of A.SCOPES) assert.ok(s.why.length > 20, s.id);
  for (const m of A.MODES) assert.ok(m.why.length > 20, m.id);
  for (const key of A.DIAL_KEYS) assert.ok(A.DIALS[key].why.length > 20, key);
});

check("a dial pill's words name the dial and the step", () => {
  assert.equal(A.dialWords("energy", 2), "Energy 2 of 3");
  assert.equal(A.dialWords("motion", 3), "Motion 3 of 3");
});

if (fails.length) {
  console.log(`\n${fails.length} failed`);
  process.exit(1);
}
console.log("\nall passed");
