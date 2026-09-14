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
  ["--focus-ring", "--bg-window", 3.0, "the focus ring on the window"],
  ["--focus-ring", "--surface-1", 3.0, "the focus ring on a card"],
  // The galaxy: every node colour has to be distinguishable from the canvas.
  ["--node-h1", "--bg-window", 3.0, "graph hue 1"],
  ["--node-h2", "--bg-window", 3.0, "graph hue 2"],
  ["--node-h3", "--bg-window", 3.0, "graph hue 3"],
  ["--node-h4", "--bg-window", 3.0, "graph hue 4"],
  ["--node-h5", "--bg-window", 3.0, "graph hue 5"],
  // Semantic colours render as 9.5px uppercase text on `.row-tag`, which is
  // body text and needs 4.5 — the 3.0 floor they used to carry was the
  // non-text floor and was simply the wrong number for how they are used.
  ["--ok", "--surface-1", 4.5, "the ok state as text"],
  ["--warn", "--surface-1", 4.5, "the warn state as text"],
  ["--bad", "--surface-1", 4.5, "the bad state as text"],
  ["--info", "--surface-1", 4.5, "the info state as text"],
  ["--text-faint", "--surface-2", 4.5, "faint text on a raised card"],
  ["--text-muted", "--surface-2", 4.5, "muted text on a raised card"],
  ["--text-faint", "--surface-sunken", 4.5, "placeholder text in a field"],
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
