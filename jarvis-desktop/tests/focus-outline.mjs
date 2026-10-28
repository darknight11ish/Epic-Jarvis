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
}

// EVERY stylesheet that carries a whole window says what to use when
// forced-colors is on. `theme.css` was missing from the two-file `CHECKS` list
// above - the scope gap the 2026-10-27 accessibility audit found (finding 6).
// It is the one stylesheet with a window of its own on the list: the HUD links
// `theme.css` and `fonts.css` and nothing else, so the largest window in the
// app was the one with no high-contrast answer at all.
const FORCED_COLORS = ["widget.css", "style.css", "settings.css", "brain.css", "theme.css"];
for (const file of FORCED_COLORS) {
  assert.match(read(file), /@media \(forced-colors: active\)[\s\S]*outline: 2px solid Highlight/,
    `${file} has no forced-colors focus rule`);
}

const themeCss = read("theme.css");

// theme.css holds no component rules, so its forced-colors block answers the
// two things the tokens themselves carry into every window: the focus ring
// (a token can be repainted to the surface's own colour) and a SELECTED
// control whose only mark was a tinted fill and border. The second is what the
// HUD's chosen preset, lane, dock button and stage tab lose under Windows High
// Contrast, and `aria-pressed` / `aria-selected` is the fact already in the DOM
// to draw it back from - pinned here so it cannot quietly go away.
assert.match(themeCss,
  /\[aria-pressed="true"\],\s*\[aria-selected="true"\]\s*\{[^}]*outline: 2px solid Highlight/,
  "theme.css no longer restores a selected control under forced colours");

// The HUD page carries its own stylesheet inside `jarvis_hud.html` - it links
// only `theme.css` + `fonts.css` - and that is the page the 2026-10-27
// accessibility audit found THREE `outline:none` focus rules on (finding 5):
// `.msg.jarvis .speak-answer`, `.rail-toolbar-btn` and `.hud-presets-item`.
// The two-file `CHECKS` list above is what let that gap open, so the page is
// now checked here too. Its ring token is the page's own `--ice` (the HUD
// never uses the approval controls' `--focus-ring`), and `ruleBody` above
// cannot read it: the HUD writes `sel{` with no space before the brace.
const HUD = read("jarvis_hud.html")
  // Comments out first, newlines kept, so a selector quoted in a note can
  // never be mistaken for a rule (and a `:focus-visible` in a note can never
  // borrow the next rule's body).
  .replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, " "))
  .replace(/<!--[\s\S]*?-->/g, (m) => m.replace(/[^\n]/g, " "));

/** The body of the first rule whose selector line holds `sel`. */
function hudRule(sel) {
  const escaped = sel.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const found = new RegExp(`(?:^|\\n)[^\\n{}]*${escaped}[^\\n{}]*\\{([^}]*)\\}`).exec(HUD);
  assert.ok(found, `jarvis_hud.html has no rule for ${sel}`);
  return found[1];
}

for (const sel of [
  ".msg.jarvis .speak-answer:focus-visible",
  ".rail-toolbar-btn:focus-visible",
  ".hud-presets-item:focus-visible",
]) {
  const body = hudRule(sel);
  assert.match(body, /outline:\s*2px solid var\(--ice\)/,
    `jarvis_hud.html ${sel} needs a visible focus outline, not colour alone`);
  assert.match(body, /outline-offset:/, `jarvis_hud.html ${sel} needs an outline-offset`);
  assert.ok(!/outline:\s*none/.test(body), `jarvis_hud.html ${sel} removes the outline`);
}

// ...and the whole page, not just those three: no `:focus-visible` rule may
// turn the ring off. This is the half that stops the same gap returning on a
// fourth control nobody thought to add to the list. `outline:none` on a
// `:focus` rule (the text fields, which draw a border instead) is untouched -
// this is about the keyboard ring.
for (const rule of HUD.matchAll(/([^{}]*:focus-visible[^{}]*)\{([^}]*)\}/g)) {
  assert.ok(!/outline:\s*none/.test(rule[2]),
    `jarvis_hud.html silences the focus ring on ${rule[1].replace(/\s+/g, " ").trim()}`);
}

// The ring colour holds 3:1 on every theme's surfaces (computed 2026-09-30).
const theme = themeCss;
for (const v of ["#7df3ff", "#005263", "#ffffff"]) assert.ok(theme.includes(`--focus-ring: ${v};`), `--focus-ring ${v} moved: re-check its contrast`);
console.log("ok: approval focus rings are solid outlines with a forced-colors fallback");
