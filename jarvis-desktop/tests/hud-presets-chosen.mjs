/**
 * The chosen preset is a RECTANGLE, not the word "(chosen)" (the owner's
 * request, 2026-10-31: every chosen name grew a noisy suffix).
 *
 *   node tests/hud-presets-chosen.mjs
 *
 * WHAT IS PROVEN, without a browser (CI also runs the real-page half in
 * tests/hud-presets.mjs):
 *
 *   - no list builds a visible label with " (chosen)" in it; the word survives
 *     only in the item's accessible name (aria-label), never on screen;
 *   - one helper marks the chosen row: the `is-chosen` class, aria-current, and
 *     that accessible-name word - so the model presets, the Cloud row and the
 *     cloud providers cannot drift apart;
 *   - the page's stylesheet paints `.hud-presets-item.is-chosen` as a border in
 *     the HUD's own token (--ice), not a word;
 *   - all three desktop copies of the page and all three copies of the
 *     renderer stay byte-identical.
 *
 * It needs no Playwright and no npm install: only Node's own modules.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const DESK = join(HERE, "..");
const SRC = join(DESK, "src");
const ROOT = join(DESK, "..");
const read = (file) => readFileSync(file);
const text = (file) => readFileSync(file, "utf8");

let passed = 0;
function check(name, fn) {
  fn();
  passed += 1;
  console.log(`ok   ${name}`);
}

const js = text(join(SRC, "hud-presets.js"));
const html = text(join(SRC, "jarvis_hud.html"));

check("no visible label is built with a (chosen) suffix any more", () => {
  assert.ok(!/\.chosen\s*\?\s*" \(chosen\)"/.test(js),
    "a list still appends the visible ' (chosen)' suffix");
  assert.ok(js.includes("(chosen)"),
    "the word (chosen) vanished entirely - a screen reader loses the state");
  // Every non-comment use of the word must sit inside the one helper that
  // writes it to the accessible name, never in a visible label builder.
  const start = js.indexOf("function markChosen");
  const end = js.indexOf("\n  }", start);
  assert.ok(start > 0 && end > start, "the markChosen helper is missing");
  const outside = (js.slice(0, start) + js.slice(end)).split("\n")
    .filter((line) => line.includes(" (chosen)"));
  for (const line of outside) {
    assert.ok(/\/\/|\*/.test(line),
      `the visible suffix ' (chosen)' is not confined to the accessible name: ${line.trim()}`);
  }
});

check("one helper marks the chosen row: class, aria-current and accessible word", () => {
  assert.equal((js.match(/\.classList\.add\("is-chosen"\)/g) || []).length, 1,
    "there is not exactly one writer of the is-chosen class");
  assert.equal((js.match(/\bmarkChosen\(/g) || []).length, 4,
    "expected one definition plus three calls (model presets, Cloud row, providers)");
  assert.match(js, /button\.setAttribute\("aria-current", "true"\)/,
    "the chosen row does not say aria-current");
  assert.ok(js.includes("${visible} (chosen). ${hint}"),
    "the chosen word is not kept in the accessible name");
  assert.match(js, /const visible = \(button\.textContent \|\| ""\)\.trim\(\)/,
    "the helper does not build its name from the visible label");
});

check("the page paints the chosen row as a rectangle in the HUD's own tokens", () => {
  const at = html.indexOf(".hud-presets-item.is-chosen{");
  assert.ok(at >= 0, "the .hud-presets-item.is-chosen rule is missing");
  const rule = html.slice(at, html.indexOf("}", at));
  assert.match(rule, /border-color:var\(--ice\)/,
    "the chosen rectangle does not use the HUD's --ice token");
  assert.match(rule, /background:rgb\(var\(--accent-rgb\)/,
    "the chosen row has no tint");
});

check("the three copies of the HUD page stay byte-identical", () => {
  const files = [
    join(SRC, "jarvis_hud.html"),
    join(ROOT, "jarvis-backend", "jarvis_hud.html"),
    join(ROOT, "backend", "jarvis_hud.html"),
  ];
  const first = read(files[0]);
  for (const file of files.slice(1)) {
    assert.ok(first.equals(read(file)), `${files[0]} and ${file} differ`);
  }
});

check("the three copies of the presets renderer stay byte-identical", () => {
  const files = [
    join(SRC, "hud-presets.js"),
    join(ROOT, "jarvis-backend", "hud-presets.js"),
    join(ROOT, "backend", "static", "hud-presets.js"),
  ];
  const first = read(files[0]);
  for (const file of files.slice(1)) {
    assert.ok(first.equals(read(file)), `${files[0]} and ${file} differ`);
  }
});

console.log(`\n${passed} passed, 0 skipped, 0 failed`);
