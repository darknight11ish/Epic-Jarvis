/**
 * Scratch: what the app itself draws at a given size. Opens the served probe
 * page (which frames the REAL faces.html?mode=display) and screenshots the
 * frame.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const K = await import("./tests/uikit.mjs");

const face = process.argv[2] || "redpanda";
const sizes = (process.argv[3] || "232,150,120,96,68,40,34").split(",").map(Number);
const states = (process.argv[4] || "idle").split(",");

const { base, close } = await K.serve();
const browser = await K.launch();
const outDir = path.join(HERE, ".face-mini-out");
fs.mkdirSync(outDir, { recursive: true });

const shots = [];
for (const w of sizes) {
  for (const state of states) {
    const page = await browser.newPage({ viewport: { width: Math.max(w, 60), height: Math.max(w, 60) }, deviceScaleFactor: 2 });
    await page.goto(`${base}/.face-probe.html?w=${w}&face=${encodeURIComponent(face)}&state=${encodeURIComponent(state)}`);
    await page.waitForFunction(() => window.__ready === true, null, { timeout: 30000 });
    const shot = path.join(outDir, `app-${face}-${state}-${w}.png`);
    await page.locator("#f").screenshot({ path: shot });
    shots.push(`${shot}  (frame ${w}px, device pixel ${await page.evaluate(() => document.getElementById("f").contentDocument.getElementById("display-canvas").width)}px)`);
    await page.close();
  }
}
console.log(shots.join("\n"));
await browser.close();
close();
