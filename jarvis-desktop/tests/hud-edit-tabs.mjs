/**
 * Edit HUD, simplified (the owner's request, 2026-10-31: "the edit hud needs
 * to be way more simplified with the options under menu tabs instead of
 * everything all at once").
 *
 *   node tests/hud-edit-tabs.mjs
 *
 * WHAT THIS PINS, without a browser (the real page is driven by the Playwright
 * cases in tests/hud-edit-fieldtest.mjs and tests/hud.mjs, which CI runs):
 *
 *   - the slim default view: title, one sentence, Done / Undo / Reset /
 *     Discard, and four tabs - nothing else drawn until a tab is opened;
 *   - Cards is the default tab, and a card's controls are NOT on the canvas:
 *     the SAME `.hud-card-tools` element is moved into the ONE selected-card
 *     editor when a card is picked, so no control or handler is rewritten;
 *   - Presets uses the focus-preset outline class (`is-chosen`) and Apply is
 *     the existing `resetToPreset` action;
 *   - Panels is the existing order/region controls grouped by region;
 *   - Advanced lists hidden/folded cards with the existing `setVisible` /
 *     `toggleCollapsed` actions, and names the always-visible cards;
 *   - the four whole-edit controls and their ids are unchanged;
 *   - the three HUD page copies stay byte-identical.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "src");
const ROOT = join(HERE, "..", "..");
const read = (file) => readFileSync(file, "utf8");
const readBytes = (file) => readFileSync(file);

const JS = read(join(SRC, "hud-edit.js"));
const HUD = read(join(SRC, "jarvis_hud.html"));

let passed = 0;
function check(name, fn) {
  fn();
  passed += 1;
  console.log(`ok   ${name}`);
}

check("the bar is slim and still carries the four whole-edit controls", () => {
  assert.ok(JS.includes('title.textContent = "Edit HUD"'), "the bar has no title");
  assert.ok(JS.includes('words.textContent = "Drag a card, or open its options."'),
    "the bar's one sentence changed");
  for (const what of ["undo", "reset", "discard", "done"]) {
    assert.ok(JS.includes(`["${what}", `), `the ${what} control is gone`);
    assert.ok(JS.includes("data-hud-edit-global"), "the whole-edit controls lost their handler");
  }
});

check("four tabs, Cards first, each with tab/tabpanel wiring", () => {
  const order = [...JS.matchAll(/\["(cards|presets|panels|advanced)", "(Cards|Presets|Panels|Advanced)"\]/g)]
    .map((m) => m[1]);
  assert.deepEqual(order, ["cards", "presets", "panels", "advanced"],
    `the tabs are not the owner's four in order: ${JSON.stringify(order)}`);
  assert.match(JS, /setAttribute\("role", "tab"\)/);
  assert.match(JS, /setAttribute\("role", "tabpanel"\)/);
  assert.match(JS, /setAttribute\("aria-selected", "false"\)/);
  assert.ok(JS.includes('editTab = "cards"'), "Cards is not the default tab");
  assert.match(JS, /doc\.body\.setAttribute\("data-hud-edit-tab", editTab\)/,
    "the active tab is not on the body for the stylesheet");
});

check("cards: no control rows on the canvas; one selected card's SAME tools move into the bar", () => {
  assert.match(HUD,
    /body\[data-hud-edit="on"\] \.hud-card \.hud-card-tools\{display:none !important;\}/,
    "the card control rows are not hidden on the canvas");
  assert.match(HUD, /\.hud-edit-card-controls \.hud-card-tools\{display:flex/,
    "the selected card's controls are not shown in the bar");
  assert.match(JS, /const tools = shell \? shell\.querySelector\("\.hud-card-tools"\) : null;/,
    "the bar does not take the card's OWN toolbar element");
  assert.match(JS, /editor\.appendChild\(tools\);/,
    "the card's own toolbar is not moved into the selected-card editor");
  assert.match(JS, /selectedCard/);
  assert.match(JS, /function onEditCardClick\(/, "a click on a card does not select it");
  assert.ok(JS.includes("hud-edit-selected"), "the selected card is not marked for the outline");
  assert.match(HUD, /\.hud-card\[data-hud-edit-selected="true"\]\{/,
    "the selected card has no outline");
});

check("presets: the chosen one wears is-chosen, and Apply is the existing resetToPreset", () => {
  assert.match(JS, /"hud-edit-preset-name" \+ \(chosen \? " is-chosen" : ""\)/,
    "the chosen preset is not outlined with is-chosen");
  assert.match(JS, /data-hud-edit-preset/);
  assert.match(JS, /doAction\(\{ type: "resetToPreset", id: preset\.getAttribute\("data-hud-edit-preset"\) \}\)/,
    "Apply is not the existing reset-to-preset action");
  assert.match(JS, /Applying is one Undo away/);
});

check("panels: the existing order controls, grouped by region", () => {
  assert.match(JS, /for \(const region of EDIT_REGIONS\)/);
  assert.match(JS, /REGION_LABEL\[region\]/);
  assert.match(JS, /"data-hud-edit-command": command/,
    "the panels tab does not reuse the card order controls");
  assert.match(JS, /"data-hud-edit-card": card\.id/);
});

check("advanced: hidden and folded cards use the existing actions; always-visible named", () => {
  assert.match(JS, /"data-hud-edit-advanced": "show"/);
  assert.match(JS, /"data-hud-edit-advanced": "expand"/);
  assert.match(JS, /doAction\(\{ type: "setVisible", id \}\)/,
    "Show is not the existing setVisible action");
  assert.match(JS, /doAction\(\{ type: "toggleCollapsed", id \}\)/,
    "Expand is not the existing toggleCollapsed action");
  assert.match(JS, /always visible; it can never be hidden|Always visible \(no Hide control\)/,
    "the always-visible cards are not named");
});

check("behaviour is untouched: no network call here, the normalizer is not edited, Esc still exits", () => {
  assert.ok(!/new XMLHttpRequest|fetch\(/.test(JS),
    "the edit code calls the network - there is no new route in this change");
  assert.ok(!/normalizeLayout\s*=\s*function|function normalizeLayout\(/.test(JS),
    "the layout normalizer was redefined here");
  assert.match(JS, /key === "Escape"|"Escape"/,
    "Esc no longer exits edit mode");
});

check("the four whole-edit controls keep their ids and the tabs stay out of the way", () => {
  for (const id of ["hud-edit-undo", "hud-edit-reset", "hud-edit-discard", "hud-edit-done"]) {
    assert.ok(JS.includes("`hud-edit-${what}`"), "the control ids changed");
  }
  assert.match(HUD, /\.hud-edit-tabs\{/);
  assert.match(HUD, /\.hud-edit-pane\[hidden\]\{display:none !important;\}/);
});

check("the three HUD page copies stay byte-identical", () => {
  const files = [
    join(SRC, "jarvis_hud.html"),
    join(ROOT, "jarvis-backend", "jarvis_hud.html"),
    join(ROOT, "backend", "jarvis_hud.html"),
  ];
  const first = readBytes(files[0]);
  for (const file of files.slice(1)) {
    assert.ok(first.equals(readBytes(file)), `${files[0]} and ${file} differ`);
  }
});

console.log(`\n${passed} passed, 0 skipped, 0 failed`);
