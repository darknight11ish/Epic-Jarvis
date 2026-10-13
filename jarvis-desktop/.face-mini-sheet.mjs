/**
 * Scratch: build a contact sheet from .face-mini-out so the tiny renders can
 * actually be looked at. Each cell is the render at its true size, then
 * nearest-neighbour magnified, so what you see is what the pixels are.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.join(HERE, ".face-mini-out");
const K = await import("./tests/uikit.mjs");
const browser = await K.launch();
const page = await browser.newPage();

const args = process.argv.slice(2);
const id = args[0] || "redpanda";
const states = args[1] ? args[1].split(",") : ["idle", "listening", "thinking", "speaking", "approval", "standby", "error"];
const sizes = args[2] ? args[2].split(",").map(Number) : [34, 40, 68, 96, 120, 232];

const urls = {};
for (const s of states) for (const w of sizes) {
  const p = path.join(SRC, `${id}-${s}-${w}.png`);
  urls[`${s}-${w}`] = "data:image/png;base64," + fs.readFileSync(p).toString("base64");
}
const CELL = 120;
await page.setViewportSize({ width: CELL * sizes.length + 8, height: CELL * states.length + 24 });
await page.setContent(`<style>body{margin:0;background:#05070a}
 table{border-collapse:collapse}
 td{padding:1px;text-align:center;vertical-align:middle}
 img{display:block;width:${CELL - 8}px;height:${CELL - 8}px;image-rendering:pixelated}
 .lbl{color:#889;font:10px monospace}</style><table></table>`);
await page.evaluate(({ urls, states, sizes, CELL }) => {
  const t = document.querySelector("table");
  for (const s of states) {
    const tr = document.createElement("tr");
    for (const w of sizes) {
      const td = document.createElement("td");
      const img = document.createElement("img");
      img.src = urls[`${s}-${w}`];
      const lbl = document.createElement("div");
      lbl.className = "lbl";
      lbl.textContent = `${s} ${w}px`;
      td.append(img, lbl);
      tr.append(td);
    }
    t.append(tr);
  }
}, { urls, states, sizes, CELL });
const out = path.join(SRC, `sheet-${id}.png`);
await page.screenshot({ path: out });
console.log(out);
await browser.close();
