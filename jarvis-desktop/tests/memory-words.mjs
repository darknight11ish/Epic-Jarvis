/**
 * The memory words both apps use (the memory review of 2026-09-27, I8-I11),
 * held to tests/fixtures/memory-words-cases.json, which
 * tools/gen_memory_words_cases.py makes from the real backend. The phone's
 * MemoryWordsContractTest reads the same file, so the two apps cannot word
 * memory differently.
 *
 *     node tests/memory-words.mjs
 *
 * No browser: src/memory-words.js is pure, and brain.js / auto-learn.js are
 * read as text to prove they use it rather than words of their own.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  cardLines,
  MONTHS,
  plainDate,
  plainDateOf,
  statusRows,
  trueFromLine,
  WORDS,
} from "../src/memory-words.js";
import { cardReason, factMeta, readAuto } from "../src/auto-learn.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const CASES = JSON.parse(readFileSync(join(HERE, "fixtures", "memory-words-cases.json"), "utf8"));
const src = (name) => readFileSync(join(HERE, "..", "src", name), "utf8");

const fails = [];
const check = (name, fn) => {
  try { fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

check("the words are the fixture's, word for word", () => {
  assert.deepEqual({ ...WORDS }, CASES.words);
  assert.deepEqual([...MONTHS], CASES.months);
});

check("plain dates: 1 January 2026, and nothing for a day that is not real", () => {
  for (const c of CASES.dates) assert.equal(plainDate(c.iso), c.says, c.iso);
});

check("I10: a Saved automatically row's true_from -> \"true from 1 January 2026\"", () => {
  for (const c of CASES.true_from) {
    assert.equal(trueFromLine(c.row.true_from) || null, c.line, JSON.stringify(c.row));
  }
});

check("I10: the row's small line says it, after when it was saved", () => {
  const now = 1790000000 * 1000;
  for (const c of CASES.true_from) {
    const [fact] = readAuto({ facts: [c.row] }).facts;
    const meta = factMeta(fact, now);
    if (c.line) assert.ok(meta.endsWith(c.line), meta);
    else assert.ok(!meta.includes(WORDS.true_from), meta);
  }
});

check("I8: the memory counts' rows, from the real status in every re-ranker state", () => {
  for (const c of CASES.status) assert.deepEqual(statusRows(c.status), c.rows, c.name);
});

check("I9: the reason line, and the older-news warning on its own line", () => {
  for (const c of CASES.cards) {
    assert.deepEqual(cardLines(c.row), { reason: c.reason, older: c.older }, JSON.stringify(c.row));
    // auto-learn.js's cardReason is the first line and nothing more.
    assert.equal(cardReason(c.row) || null, c.reason, JSON.stringify(c.row));
  }
});

check("plain dates from a time: on this PC's calendar, in the same words", () => {
  const t = new Date(2026, 0, 1, 12, 0, 0).getTime() / 1000;
  assert.equal(plainDateOf(t), "1 January 2026");
  assert.equal(plainDateOf(null), "");
  assert.equal(plainDateOf(-5), "");
  assert.equal(plainDateOf(Infinity), "");
  assert.equal(plainDateOf(1e20), "");
});

check("brain.js draws the counts from statusRows and says the new label", () => {
  const brain = src("brain.js");
  assert.match(brain, /statusRows\(body\)/);
  assert.match(brain, /cardLines\(p\)/);
  assert.match(brain, /WORDS\.repeats/);
  assert.doesNotMatch(brain, /"Repeats"/);
  assert.doesNotMatch(brain, /no longer recalled/);
  // The full list never shows a bare "2825d ago" for when a fact became true.
  assert.doesNotMatch(brain, /ago\(f\.valid_from\)/);
});

if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join(", ")}`);
  process.exit(1);
}
console.log("\nmemory-words: all passed");
