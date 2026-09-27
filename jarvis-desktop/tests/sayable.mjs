/**
 * "Things you can say" - held to tests/fixtures/sayable-cases.json, which
 * tools/gen_sayable_cases.py makes from backend/jarvis_sayable.py. The
 * phone's SayableContractTest reads the same file.
 *
 *     node tests/sayable.mjs
 *
 * No browser: the pages are read as text, and sayable.js's own exports are
 * checked directly. Playwright checks the interactive behaviour (tapping a
 * line, the primer's fewer rows) in tests/ia.mjs, next to the primer's
 * other findings.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  DETAIL,
  FOOTER,
  HELP_BODY,
  HELP_TITLE,
  SENTENCES,
  TITLE,
  WALKTHROUGH_EXAMPLES,
} from "../src/sayable.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "src");
const CASES = JSON.parse(readFileSync(join(HERE, "fixtures", "sayable-cases.json"), "utf8"));
const page = (name) => readFileSync(join(SRC, name), "utf8");

const fails = [];
const check = (name, fn) => {
  try { fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/* ── The words are the backend's ─────────────────────────────────────────── */

check("TITLE, DETAIL and FOOTER are the backend's own words", () => {
  assert.equal(TITLE, CASES.title);
  assert.equal(DETAIL, CASES.detail);
  assert.equal(FOOTER, CASES.footer);
});

check("SENTENCES is the backend's list, in the same order", () => {
  assert.deepEqual(SENTENCES, CASES.sentences);
  assert.ok(SENTENCES.length >= 5 && SENTENCES.length <= 8, `${SENTENCES.length} sentences`);
});

check("WALKTHROUGH_EXAMPLES is exactly the backend's 3, a subset of SENTENCES", () => {
  assert.deepEqual(WALKTHROUGH_EXAMPLES, CASES.walkthrough_examples);
  assert.equal(WALKTHROUGH_EXAMPLES.length, 3);
  for (const s of WALKTHROUGH_EXAMPLES) assert.ok(SENTENCES.includes(s), s);
});

check("the Help/FAQ words are the backend's", () => {
  assert.equal(HELP_TITLE, CASES.help_title);
  assert.equal(HELP_BODY, CASES.help_body);
});

/* ── buildSayableList: fills, never sends. No `document` in plain node, so
   the DOM it builds is exercised in the browser instead - tests/ia.mjs,
   "tapping a sayable line fills the box and never sends" - and this only
   checks the source shape (never a click handler that sends, never a bare
   <button> that would submit a form on Enter). ─────────────────────────── */

check("buildSayableList never sends: no invoke/fetch/submit in its own body", () => {
  const js = page("sayable.js");
  const fn = js.slice(js.indexOf("export function buildSayableList"));
  const body = fn.slice(0, fn.indexOf("\nexport") === -1 ? fn.length : fn.indexOf("\nexport"));
  assert.doesNotMatch(body, /invoke\(|fetch\(|\.submit\(|stream_chat/);
  assert.match(body, /button\.type\s*=\s*"button"/, "a bare <button> submits a form on Enter");
  assert.match(body, /onPick\(sentence\)/, "a tap does not call back with its own sentence");
  assert.match(body, /aria-label.*Put ".*" in the box/, "the accessible name is silent about "
    + "what tapping it does");
});

/* ── The bar: replaces the 10 rows, points at Settings -> Shortcuts ──────── */

check("index.html's primer holds #sayable-list, and no <kbd> hotkey chips remain", () => {
  const html = page("index.html");
  assert.match(html, /id="sayable-list"/, "the primer has nowhere for sayable.js to render into");
  const primer = html.slice(html.indexOf('id="primer"'), html.indexOf("</section>",
    html.indexOf('id="primer"')));
  assert.doesNotMatch(primer, /data-hotkey=/, "a kbd-chip row is still hardcoded in the primer");
  // The note-app prefixes are not keyboard shortcuts, and stay: they have no
  // other home in either app today.
  for (const target of ["logseq", "joplin", "obsidian"]) {
    assert.match(primer, new RegExp(`data-note-target="${target}"`), target);
  }
});

check("main.js renders the list at startup and fills #prompt on a tap, never sends", () => {
  const main = page("main.js");
  assert.match(main, /import\s*\{\s*buildSayableList\s*\}\s*from\s*"\.\/sayable\.js"/);
  assert.match(main, /renderSayableList\(\)/, "the list is never rendered");
  const fn = main.slice(main.indexOf("function renderSayableList"));
  const body = fn.slice(0, fn.indexOf("\n}"));
  assert.match(body, /dom\.prompt\.value\s*=\s*sentence/, "a tap does not fill #prompt");
  assert.doesNotMatch(body, /invoke\(|stream_chat|\.send\(/, "a tap does more than fill the box");
  assert.doesNotMatch(main, /function syncPrimerKeys/, "the old hardcoded-vs-live check is dead "
    + "code now the chips are gone");
});

check("settings.html's Shortcuts card is where the footer line points", () => {
  assert.match(page("settings.html"), /<h2>Shortcuts<\/h2>/);
});

/* ── The walkthrough: screen 2, exactly 3, never screen 1 or 3 ───────────── */

check("onboarding.html puts exactly the 3 walkthrough examples on screen 2", () => {
  const html = page("onboarding.html");
  const s1 = html.slice(html.indexOf('id="screen-1"'), html.indexOf('id="screen-2"'));
  const s2 = html.slice(html.indexOf('id="screen-2"'), html.indexOf('id="screen-3"'));
  const s3 = html.slice(html.indexOf('id="screen-3"'));
  for (const example of WALKTHROUGH_EXAMPLES) {
    assert.ok(s2.includes(example), `screen 2 is missing ${example}`);
    assert.ok(!s1.includes(example), `screen 1 already has ${example}`);
    assert.ok(!s3.includes(example), `screen 3 already has ${example}`);
  }
  // Only the 3 walkthrough ones - not the other 4 SENTENCES, which would
  // crowd a screen that is meant to stay about approvals first.
  for (const s of SENTENCES) {
    if (WALKTHROUGH_EXAMPLES.includes(s)) continue;
    assert.ok(!s2.includes(s), `screen 2 has a non-walkthrough sentence: ${s}`);
  }
});

/* ── Help: both apps ──────────────────────────────────────────────────────── */

check("settings.html's FAQ has a \"What can I say?\" answer naming every sentence", () => {
  const html = page("settings.html");
  const i = html.indexOf("What can I say?");
  assert.ok(i >= 0, "no \"What can I say?\" FAQ entry");
  const raw = html.slice(html.lastIndexOf("<details", i), html.indexOf("</details>", i) + 11);
  // Line-wrapped source, not rendered HTML: a sentence split across two
  // source lines still reads as one to a browser, so it must here too.
  const entry = raw.replace(/\s+/g, " ");
  for (const s of SENTENCES) assert.ok(entry.includes(s), `FAQ entry is missing ${s}`);
  assert.match(entry, /what can you do\?/i, "the FAQ never says how to see the list again");
});

if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join("; ")}`);
  process.exit(1);
}
console.log("\nall sayable checks passed");
