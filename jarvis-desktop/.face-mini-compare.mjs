/**
 * Scratch: put the app's own screenshots next to the probe renders, at each
 * true size, so the two camera fits can be compared and the tiny sizes can be
 * judged. Each cell is nearest-neighbour magnified from the real pixels.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.join(HERE, ".face-mini-out");
const K = await import("./tests/uikit.mjs");
const browser = await K.launch();
const page = await browser.newPage();

const id = process.argv[2] || "redpanda";
const state = process.argv[3] || "idle";
const sizes = (process.argv[4] || "232,120,96,68,40,34").split(",").map(Number);

const b64 = (p) => fs.existsSync(p) ? "data:image/png;base64," + fs.readFileSync(p).toString("base64") : null;
const app = {}, probe = {};
for (const w of sizes) {
  app[w] = b64(path.join(SRC, `app-${id}-${state}-${w}.png`));
  probe[w] = b64(path.join(SRC, `${id}-${state}-${w}.png`));
}
const CELL = 150;
await page.setViewportSize({ width: CELL * sizes.length + 8, height: CELL * 2 + 30 });
await page.setContent(`<style>body{margin:0;background:#05070a}
 table{border-collapse:collapse}
 td{padding:1px;text-align:center}
 img{display:block;width:${CELL - 8}px;height:${CELL - 8}px;image-rendering:pixelated}
 .lbl{color:#889;font:10px monospace}</style><table></table>`);
await page.evaluate(({ app, probe, sizes, CELL }) => {
  const t = document.querySelector("table");
  for (const [name, set] of [["the app's own frame", app], ["probe (raw shader)", probe]]) {
    const tr = document.createElement("tr");
    for (const w of sizes) {
      const td = document.createElement("td");
      if (set[w]) { const img = document.createElement("img"); img.src = set[w]; td.append(img); }
      const lbl = document.createElement("div");
      lbl.className = "lbl";
      lbl.textContent = set[w] ? `${name === "probe (raw shader)" ? "probe" : "app"} ${w}px` : `${w}px n/a`;
      td.append(lbl);
      tr.append(td);
    }
    t.append(tr);
  }
}, { app, probe, sizes, CELL });
const out = path.join(SRC, `compare-${id}-${state}.png`);
await page.screenshot({ path: out });
console.log(out);
await browser.close();
