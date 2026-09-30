// Focus rings on the approval controls are a solid bright outline (owner's
// choice, 2026-09-30: "solid bright outline, no fade"), never a box-shadow
// alone - a shadow is dropped in Windows high-contrast (forced-colors) mode -
// and each stylesheet says what to use when forced-colors is on. No browser.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const SRC = join(dirname(fileURLToPath(import.meta.url)), "..", "src");
const read = (f) => readFileSync(join(SRC, f), "utf8");

/** The body of the first top-level rule whose selector list is exactly `sel`. */
function ruleBody(css, sel) {
  const at = css.indexOf(`${sel} {`);
  assert.ok(at >= 0, `no rule for ${sel}`);
  return css.slice(css.indexOf("{", at) + 1, css.indexOf("}", at));
}

const CHECKS = {
  "widget.css": [".btn:focus-visible", ".appr-option:focus-visible"],
  "style.css": [".approval-button:focus-visible", ".approval-option:focus-visible"],
};
for (const [file, sels] of Object.entries(CHECKS)) {
  const css = read(file);
  for (const sel of sels) {
    const body = ruleBody(css, sel);
    assert.match(body, /outline:\s*2px solid var\(--focus-ring\)/, `${file} ${sel} needs a solid focus outline`);
    assert.match(body, /outline-offset:/, `${file} ${sel} needs an outline-offset`);
    assert.ok(!/outline:\s*none/.test(body), `${file} ${sel} removes the outline`);
  }
  assert.match(css, /@media \(forced-colors: active\)[\s\S]*outline: 2px solid Highlight/, `${file} has no forced-colors focus rule`);
}

// The ring colour holds 3:1 on every theme's surfaces (computed 2026-09-30).
const theme = read("theme.css");
for (const v of ["#7df3ff", "#005263", "#ffffff"]) assert.ok(theme.includes(`--focus-ring: ${v};`), `--focus-ring ${v} moved: re-check its contrast`);
console.log("ok: approval focus rings are solid outlines with a forced-colors fallback");
