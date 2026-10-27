/**
 * The bar's primer is GONE (owner's decision, 2026-10-27), and the bar is
 * still compact. This file used to pin the "Things you can say" panel, its
 * "?" door, its disclosure/aria-expanded contract and its compact default.
 *
 * The owner removed the door and the panel from the bar, so those checks
 * cannot describe the product any more. They are replaced by the NEW truth,
 * not weakened:
 *   1. neither the "?" button nor the panel is in the DOM (not hidden -
 *      absent), and neither is anything that only lived inside it;
 *   2. no JS that filled it survives (no syncPrimer, renderSayableList,
 *      renderPaletteHint, primerOpen, dom.primer or dom.sayableToggle), so
 *      nothing can throw on a missing #primer;
 *   3. no CSS addresses the removed panel, its list, its palette hint, its
 *      chat-ended note or the removed Esc badge;
 *   4. the bar still opens at its 80px input row, and its height still comes
 *      from the one measurement every surface calls;
 *   5. the help and palette the panel used to carry are still reachable, by
 *      the doors that really exist: Settings' Brain tab reuses sayable.js's
 *      HELP_TITLE/HELP_BODY, and "/" in an empty box still opens the palette;
 *   6. Esc still hides the bar - through the document keydown handler, which
 *      is what the removed badge only *named*;
 *   7. the note-prefix feature the panel explained still works: the note chip
 *      is on the bar and main.js still parses the prefixes.
 *
 * Structural, like bar-chrome.mjs, and for the same reason: there is no
 * browser needed to hold the shape of a file.
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
const paletteUi = read(join(SRC, "palette-ui.js"));
const desktopHelp = read(join(SRC, "desktop-help.js"));

const fails = [];
const check = (name, fn) => {
  try { fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/** Ids that were the primer's, or existed only inside it. */
const PRIMER_IDS = [
  "primer",
  "sayable-toggle",
  "sayable-list",
  "palette-hint",
  "earlier-chats-primer",
  "chat-ended-note",
  "note-targets-line",
];

check("neither the \"?\" door nor the primer panel is in the DOM", () => {
  for (const id of PRIMER_IDS) {
    assert.doesNotMatch(indexHtml, new RegExp(`id="${id}"`),
      `#${id} is still in index.html - the owner removed the primer and its door (2026-10-27)`);
  }
  assert.doesNotMatch(indexHtml, /class="primer"|class="primer-|data-note-target/,
    "a primer-only element is still in index.html");
  assert.doesNotMatch(indexHtml, /class="key-badge"/,
    "the Esc key badge is still in the bar - it left with the \"?\" and the pin");
  assert.doesNotMatch(indexHtml, /id="pin"/,
    "the pin button is still in the bar");
});

check("no JS that filled the primer survives", () => {
  for (const gone of ["function syncPrimer", "function renderSayableList",
                      "function renderPaletteHint", "let primerOpen",
                      "dom.primer", "dom.sayableToggle",
                      "buildSayableList", "buildPaletteHint"]) {
    assert.ok(!mainJs.includes(gone),
      `main.js still carries \`${gone}\` - it can only throw or do nothing now`);
  }
  // The chat-ended WORDS still reach a screen reader; only the visible span
  // that lived in the primer is gone.
  assert.match(mainJs, /announce\(line\)/, "the chat-ended line is no longer announced at all");
  assert.match(mainJs, /const line = endedPrivate \? PRIVATE_ENDED : endedTemporary \? ENDED_TEMPORARY : ENDED_SAVED;/,
    "the chat-ended words were lost with the primer instead of moving to the announcer");
});

check("no CSS addresses the removed panel or the removed badge", () => {
  for (const gone of [".primer", ".sayable-", ".palette-hint", ".key-badge"]) {
    assert.ok(!styleCss.includes(gone),
      `style.css still styles \`${gone}\`, which no element uses any more`);
  }
});

check("the bar still opens at its 80px input row", () => {
  assert.match(styleCss, /--bar-height:\s*80px/, "the bar's height constant moved");
  assert.match(styleCss, /\.shell\s*\{[^}]*max-height:\s*720px/s,
    "the shell's 720px clamp moved");
  assert.match(mainJs, /function syncWindowHeight\(\)/,
    "the one height measurement every surface calls is gone");
});

check("the help words still have a home outside the bar", () => {
  // The removed primer's "Things you can say" list is sayable.js's HELP_BODY;
  // the Brain's Tutorials and the FAQ reuse it verbatim.
  assert.match(desktopHelp, /import \{ HELP_BODY, HELP_TITLE \} from "\.\/sayable\.js"/,
    "the FAQ no longer reuses the sayable help, so the removed panel's words are gone from the app");
});

check("the palette still has its keyboard door", () => {
  assert.match(paletteUi, /event\.key === "\/"/,
    "typing \"/\" no longer opens the palette, and the removed Find button was its other door");
  assert.match(mainJs, /mountPalette\(\{/,
    "the palette is no longer mounted, so \"/\" has nothing to open");
});

check("Esc still hides the bar, through the handler rather than the badge", () => {
  const at = mainJs.indexOf('document.addEventListener("keydown", (event) => {\n  if (event.key === "Escape")');
  assert.notEqual(at, -1, "main.js no longer has the document-level Escape handler");
  const block = mainJs.slice(at, at + 900);
  assert.match(block, /dismiss\(\)/, "Escape no longer dismisses the bar");
  assert.match(mainJs, /await invoke\("hide_quickbar"\)/,
    "dismiss no longer calls hide_quickbar");
});

check("the note-prefix feature the panel explained still works", () => {
  assert.match(indexHtml, /id="note-chip"/, "the live note chip left with the primer");
  assert.match(mainJs, /function syncNoteChip\(\)/, "main.js no longer mirrors the note prefix");
  assert.match(mainJs, /parseNotePrefix\(dom\.prompt\.value\)/,
    "the note prefix is no longer parsed, so #log/#joplin/#obs would stop filing");
});

if (fails.length) {
  console.log(`\n${fails.length} failed`);
  process.exit(1);
}
console.log("\nthe primer is gone and the bar is still compact");
