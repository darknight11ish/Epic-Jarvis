/**
 * The quickbar opens compact (owner, 2026-10-19: "the jarvis bar is huge now, i
 * want it back to its compact size").
 *
 * What happened: the primer ("What you can do here / Things you can say") was
 * the empty state shown on every summon. Its served sayable list is ~11 rows,
 * so the bar grew to 577 px instead of its 80 px input row. It is useful help;
 * it is not what the bar should be every time it opens.
 *
 * These checks are structural, like bar-chrome.mjs, and for the same reason:
 * there is no browser in CI. They pin the three facts that make the compact
 * default real:
 *   1. the primer starts hidden in the markup;
 *   2. a visible control opens it and says so to a screen reader;
 *   3. main.js's one visibility function keeps it closed unless the owner
 *      opened it, and every summon resets that.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "src");
const read = (p) => readFileSync(p, "utf8");

const indexHtml = read(join(SRC, "index.html"));
const mainJs = read(join(SRC, "main.js"));
const styleCss = read(join(SRC, "style.css"));

const fails = [];
const check = (name, fn) => {
  try { fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/** The text of one function or listener block, by marker. */
function blockFor(source, marker, span = 900) {
  const at = source.indexOf(marker);
  assert.notEqual(at, -1, `${marker} is not in the file`);
  return source.slice(at, at + span);
}

check("the primer starts hidden in the markup", () => {
  assert.match(indexHtml, /<section class="primer" id="primer"[^>]*\bhidden\b/,
    "the primer must start hidden, or the bar opens huge on every summon");
});

check("the bar has a visible, named door to the primer", () => {
  assert.match(indexHtml, /id="sayable-toggle"/, "no #sayable-toggle on the bar");
  assert.match(indexHtml, /aria-controls="primer"/,
    "the button must say which panel it controls");
  assert.match(indexHtml, /<span class="sr-only">What can I say\?<\/span>/,
    "the ? button needs a name for a screen reader");
});

check("the one visibility function keeps the primer closed unless opened", () => {
  const block = blockFor(mainJs, "function syncPrimer()");
  assert.match(block, /dom\.primer\.hidden = busy \|\| !primerOpen;/,
    "syncPrimer must combine its busy check with the owner's primerOpen flag");
  assert.match(block, /dom\.sayableToggle\.setAttribute\("aria-pressed"/,
    "the ? button must show whether the panel is open");
});

check("the ? button toggles the primer and resizes the bar", () => {
  const block = blockFor(mainJs, '// "What can I say?" - the door to the "Things you can say" primer.');
  assert.match(block, /addEventListener\("click"/,
    "the ? button must have a click handler");
  assert.match(block, /primerOpen = !primerOpen;/,
    "the handler must toggle primerOpen");
  assert.match(block, /syncWindowHeight\(\)/,
    "the bar must re-measure after the panel opens or closes");
});

check("every summon starts compact", () => {
  const block = blockFor(mainJs, 'listen("focus-input"');
  assert.match(block, /primerOpen = false;/,
    "a new summon must reset the panel, not inherit the last one");
});

check("the ? mark has its own small style", () => {
  assert.match(styleCss, /\.sayable-mark\s*\{[^}]*font-size:\s*13px;/s,
    "the ? needs the compact toolbar size");
});

if (fails.length) {
  console.log(`\n${fails.length} failed`);
  process.exit(1);
}
console.log("\nall passed");
