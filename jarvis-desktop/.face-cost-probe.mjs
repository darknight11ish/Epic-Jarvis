/**
 * Scratch: what one small face costs, and what it looks like. Each size gets
 * its OWN browser, so one trip cannot colour the next reading. The frame's own
 * surface numbers are sampled every 200 ms and the whole series is reported.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const K = await import("./tests/uikit.mjs");
const { base, close } = await K.serve();

const faces = (process.argv[2] || "redpanda").split(",");
const sizes = (process.argv[3] || "40,96,232").split(",").map(Number);
const state = process.argv[4] || "idle";

const rows = [];
for (const face of faces) {
  for (const w of sizes) {
    const browser = await K.launch();
    const page = await browser.newPage({ viewport: { width: Math.max(w, 60), height: Math.max(w, 60) }, deviceScaleFactor: 2 });
    await page.goto(`${base}/.face-probe.html?w=${w}&face=${encodeURIComponent(face)}&state=${encodeURIComponent(state)}`);
    await page.waitForFunction(() => window.__ready === true, null, { timeout: 60000 });
    const s = await page.evaluate(() => window.__samples);
    const series = await page.evaluate(() => window.__series || null);
    rows.push({ face, css: w, ...s, series });
    await browser.close();
  }
}
console.log(["face", "css", "canvas", "clientW", "gpuMs", "frames", "gpuTrips"].join("\t"));
for (const r of rows) {
  console.log([r.face, r.css, r.w, r.clientW, r.gpuMs == null ? "-" : Math.round(r.gpuMs * 100) / 100, r.frames, r.gpuTrips].join("\t"));
}
fs.writeFileSync(path.join(HERE, ".face-mini-out", "cost.json"), JSON.stringify(rows, null, 2));
close();
