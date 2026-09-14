/**
 * Every theme in theme.css, against every pair that matters, over both a black
 * and a white backdrop.
 *
 * The two backdrops are the point. These windows are transparent and the
 * desktop behind them is not ours to choose, so a pair that clears 4.5:1 over
 * black and 2.4:1 over white is a pair that fails on somebody's wallpaper.
 */
import * as K from "./uikit.mjs";
import { readTokens, check } from "./contrast.mjs";

// [foreground, background, floor, what it is]
// 4.5 is the WCAG AA floor for body text; 3.0 for large text and for a UI
// boundary that carries meaning.
const PAIRS = [
  ["--text", "--bg-window", 4.5, "body text on the window"],
  ["--text", "--surface-1", 4.5, "body text on a card"],
  ["--text", "--surface-2", 4.5, "body text on a raised card"],
  ["--text-muted", "--bg-window", 4.5, "muted text on the window"],
  ["--text-muted", "--surface-1", 4.5, "muted text on a card"],
  ["--text-muted", "--surface-sunken", 4.5, "muted text in a sunken well"],
  ["--text-faint", "--bg-window", 4.5, "faint text on the window"],
  ["--text-faint", "--surface-1", 4.5, "faint text on a card"],
  ["--accent", "--bg-window", 3.0, "accent as a boundary"],
  ["--accent", "--surface-1", 3.0, "accent on a card"],
  ["--text-on-accent", "--accent", 4.5, "text on an accent fill"],
  ["--ok", "--surface-1", 3.0, "the ok state"],
  ["--warn", "--surface-1", 3.0, "the warn state"],
  ["--bad", "--surface-1", 3.0, "the bad state"],
  ["--info", "--surface-1", 3.0, "the info state"],
  ["--focus-ring", "--bg-window", 3.0, "the focus ring on the window"],
  ["--focus-ring", "--surface-1", 3.0, "the focus ring on a card"],
  // The galaxy: every node colour has to be distinguishable from the canvas.
  ["--node-core", "--bg-window", 3.0, "graph: core"],
  ["--node-model", "--bg-window", 3.0, "graph: model"],
  ["--node-tool", "--bg-window", 3.0, "graph: tool"],
  ["--node-skill", "--bg-window", 3.0, "graph: skill"],
  ["--node-persona", "--bg-window", 3.0, "graph: persona"],
  ["--node-fact", "--bg-window", 3.0, "graph: fact"],
  ["--node-document", "--bg-window", 3.0, "graph: document"],
  ["--node-cluster", "--bg-window", 3.0, "graph: cluster"],
  ["--node-source", "--bg-window", 3.0, "graph: source"],
  ["--node-entity", "--bg-window", 3.0, "graph: entity"],
];

const THEMES = ["default", "ember", "paper", "high-contrast"];
// The high-contrast theme claims AAA, so it is held to it rather than to AA.
const AAA = { "high-contrast": true };

const { base, close } = await K.serve();
const browser = await K.launch();
const page = await browser.newPage({ viewport: { width: 800, height: 600 } });
await page.goto(`${base}/index.html`);
await page.evaluate(() => {
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = "theme.css";
  document.head.append(link);
  return new Promise(r => { link.onload = r; link.onerror = r; });
});
await page.waitForTimeout(200);

const props = [...new Set(PAIRS.flatMap(p => [p[0], p[1]]))];
const tokens = await readTokens(page, props, THEMES);

let fails = 0, checked = 0;
for (const theme of THEMES) {
  const missing = props.filter(p => !tokens[theme][p] || tokens[theme][p] === "");
  console.log(`\n[${theme}]${missing.length ? `  MISSING: ${missing.join(", ")}` : ""}`);
  const bad = [];
  for (const [fg, bg, floor, what] of PAIRS) {
    const min = AAA[theme] ? Math.max(floor, floor >= 4.5 ? 7 : 4.5) : floor;
    const r = check(tokens[theme][fg], tokens[theme][bg], min);
    checked++;
    if (!r.ok) { fails++; bad.push([what, r, fg, bg, min]); }
  }
  if (!bad.length) console.log(`  all ${PAIRS.length} pairs pass`);
  for (const [what, r, fg, bg, min] of bad) {
    console.log(`  FAIL ${String(r.worst).padStart(6)}:1 (need ${min})  ${what}`);
    console.log(`       ${fg}=${r.fg} on ${bg}=${r.bg}  [black ${r.overBlack} / white ${r.overWhite}]`);
  }
}
await browser.close(); close();
console.log(`\n${checked} checks, ${fails} failures.`);
process.exit(fails ? 1 : 0);
