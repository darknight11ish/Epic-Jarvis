/**
 * Scratch: every state of one face at the quickbar reactor's real sizes.
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
const states = (process.argv[3] || "idle,listening,thinking,approval,error,standby").split(",");
const sizes = (process.argv[4] || "30,34,40").split(",").map(Number);

const b64 = (p) => fs.existsSync(p) ? "data:image/png;base64," + fs.readFileSync(p).toString("base64") : null;
const CELL = 160;
const cells = [];
for (const w of sizes) for (const s of states) cells.push({ s, w, url: b64(path.join(SRC, `app-${id}-${s}-${w}.png`)) });

await page.setViewportSize({ width: CELL * states.length + 8, height: CELL * sizes.length + 30 });
await page.setContent(`<style>body{margin:0;background:#05070a}
 table{border-collapse:collapse}
 td{padding:1px;text-align:center}
 img{display:block;width:${CELL - 8}px;height:${CELL - 8}px;image-rendering:pixelated}
 .lbl{color:#889;font:10px monospace}</style><table></table>`);
await page.evaluate(({ cells, states, sizes, CELL }) => {
  const t = document.querySelector("table");
  for (const w of sizes) {
    const tr = document.createElement("tr");
    for (const s of states) {
      const found = cells.find((c) => c.s === s && c.w === w);
      const td = document.createElement("td");
      if (found && found.url) { const img = document.createElement("img"); img.src = found.url; td.append(img); }
      const lbl = document.createElement("div");
      lbl.className = "lbl";
      lbl.textContent = found && found.url ? `${s} @${w}px` : `${s} @${w}px (none)`;
      td.append(lbl);
      tr.append(td);
    }
    t.append(tr);
  }
}, { cells, states, sizes, CELL });
const out = path.join(SRC, `states-${id}-bar.png`);
await page.screenshot({ path: out });
console.log(out);
await browser.close();
