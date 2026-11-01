/**
 * The Studio stage panels are OPAQUE over their own area (the owner's report,
 * 2026-10-31: with the Telemetry stage tab active, the words of the main-screen
 * cards - Today / Coming up / Right now / Settings - showed THROUGH the panel,
 * "words on top of words").
 *
 *   node tests/hud-stage-opaque.mjs
 *
 * WHAT THIS PINS, and why the bug happened: `theme.css` deliberately gives the
 * dark theme translucent window surfaces - `--bg-window: rgba(4,7,12,.86)` and
 * `--surface-1: rgba(10,17,25,.9)` - because the window itself should mix with
 * the desktop behind it. The HUD page aliases those to `--void`/`--plate`
 * (`--void:var(--bg-window); --plate:var(--surface-1)`), and the split-stage
 * right rail (the Telemetry / Approvals / Reminders / Memory panel) painted
 * itself with `linear-gradient(var(--plate), var(--void))` alone. So the panel
 * was ~10-14% transparent and whatever the stage had painted behind it - the
 * main-screen feature cards in Edit HUD - read through it.
 *
 * The fix is theme-aware, not a hard-coded colour: the rail now puts
 * `--surface-sunken` under its own gradient. That token is OPAQUE in all three
 * themes (#04070c dark, rgb(228,233,240) light, rgb(0,0,0) high contrast), and
 * a background-color always paints BELOW a background gradient, so the panel
 * keeps the theme's gradient look and becomes solid.
 *
 * No browser needed: this suite reads the stylesheet and the three copies.
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

let passed = 0;
function check(name, fn) {
  fn();
  passed += 1;
  console.log(`ok   ${name}`);
}

const hud = read(join(SRC, "jarvis_hud.html"));
const theme = read(join(SRC, "theme.css"));

check("the Studio stage rail is opaque under its own theme gradient", () => {
  const selector = 'html[data-hud-shell="split-stage"] #rail-right{';
  const at = hud.indexOf(selector);
  assert.ok(at >= 0, "the split-stage #rail-right rule is missing");
  const rule = hud.slice(at, hud.indexOf("}", at));
  const gradient = rule.indexOf("background:linear-gradient(180deg, var(--plate), var(--void))");
  const base = rule.indexOf("background-color:var(--surface-sunken)");
  assert.ok(gradient >= 0, "the stage rail lost its own theme gradient");
  assert.ok(base >= 0, "the stage rail has no opaque surface token under its gradient");
  assert.ok(gradient < base,
    "background-color must come AFTER the background shorthand, or it is reset to transparent");
});

check("the opaque token really is opaque in every theme, and the reason is pinned", () => {
  const values = [...theme.matchAll(/--surface-sunken:\s*([^;]+);/g)].map((m) => m[1].trim());
  assert.equal(values.length, 3, `expected one --surface-sunken per theme, got ${values.length}`);
  for (const value of values) {
    assert.ok(!/rgba\(/i.test(value),
      `--surface-sunken is translucent in a theme: ${value}`);
    assert.match(value, /^#[0-9a-f]{6}$|^rgb\(\d+,\s*\d+,\s*\d+\)$/i,
      `--surface-sunken is not a plain opaque colour: ${value}`);
  }
  // The translucent surfaces are NOT a bug - they are the window's own look,
  // and this suite must not "fix" them away. The panel fix lives over them.
  assert.match(theme, /--bg-window:\s*rgba\(/,
    "the dark theme's translucent window token disappeared - the reason for the opaque base is gone");
});

check("only the stage rail gets the opaque base - the Galaxy view is untouched", () => {
  assert.equal((hud.match(/background-color:var\(--surface-sunken\)/g) || []).length, 1,
    "the opaque base was applied somewhere else as well");
  assert.match(hud, /html\[data-hud-shell="split-stage"\]\[data-hud-tab="galaxy"\] #brain\{display:flex;\}/,
    "the Galaxy tab's own stage rule changed");
});

check("the three copies of the HUD page stay byte-identical", () => {
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
