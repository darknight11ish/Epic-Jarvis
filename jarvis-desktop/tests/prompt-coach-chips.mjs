/**
 * "Add this": one fix chip on the prompt coach's panel, on the desktop.
 *
 * src/prompt-coach-panel.js, src/main.js (the bar), backend/jarvis_prompt_coach.py.
 *
 * WHAT THIS SUITE IS FOR. The coach returns up to four issues, each with a
 * smallest fix. "Send the suggestion" REPLACES what the owner typed with the
 * rewritten prompt and sends it - that stays exactly as it is. What arrived on
 * 2026-10-16 is a SECOND control: pressing one fix puts that one clarification
 * AFTER the owner's own words in the box, and sends nothing. The two must not
 * turn into one: replacing his words silently is the failure this guards.
 *
 * It is browser-free on purpose (plain node, no Playwright): the join is a pure
 * function, and the wiring is read out of the two source files. The click
 * itself is exercised by CI's browser suites against the real bar.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { WORDS, withClarification } from "../src/prompt-coach-panel.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const PANEL = read("src/prompt-coach-panel.js");
const MAIN = read("src/main.js");

const fails = [];
const check = (name, fn) => {
  try {
    fn();
    console.log(`ok    ${name}`);
  } catch (e) {
    fails.push(name);
    console.log(`FAIL  ${name}\n      ${e.message}`);
  }
};

check("a fix chip APPENDS to the owner's words and never replaces them", () => {
  assert.equal(withClarification("export the invoices", "the project is Atlas."),
               "export the invoices the project is Atlas.");
});

check("... his words are still first, in his own order", () => {
  const out = withClarification("why did my last message fail", "it was sent at 09:12.");
  assert.ok(out.startsWith("why did my last message fail"), out);
  assert.ok(out.endsWith("it was sent at 09:12."), out);
});

check("CONTROL: the suggestion path still REPLACES (a different button)", () => {
  assert.match(MAIN, /sendSuggestion: async \(text\) => \{\s*dom\.prompt\.value = text;/);
});

check("the chip is a button of its own, with its own words", () => {
  assert.match(PANEL, /className = "text-button coach-fix-chip"/);
  assert.equal(WORDS.addFix, "Add this");
  assert.notEqual(WORDS.addFix, WORDS.sendSuggestion);
});

check("pressing it calls addFix with that issue's fix - never send()", () => {
  const handler = PANEL.match(/addEventListener\("click", \(\) => \{[\s\S]*?\n\s*\}\);/);
  assert.ok(handler, "the chip's click handler is not in the panel");
  assert.match(handler[0], /addFix\(issue\.fix\)/);
  assert.doesNotMatch(handler[0], /\bsend\(/, "the chip must never send");
});

check("the bar joins the two through withClarification", () => {
  const wiring = MAIN.match(/addFix: \(fix\) => \{[\s\S]*?\n    \},/);
  assert.ok(wiring, "main.js has no addFix wiring");
  assert.match(wiring[0], /withClarification\(before, fix\)/);
  assert.doesNotMatch(wiring[0], /\bsend\(/, "addFix must never send a turn");
});

check("edge: an empty box takes the fix alone; an empty fix changes nothing", () => {
  assert.equal(withClarification("", "the project is Atlas."), "the project is Atlas.");
  assert.equal(withClarification("keep me", ""), "keep me");
  assert.equal(withClarification("keep me", "   "), "keep me");
});

check("edge: trailing space in the box does not double up", () => {
  assert.equal(withClarification("keep me  ", "add this"), "keep me add this");
});

console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nall checks passed");
process.exit(fails.length ? 1 : 0);
