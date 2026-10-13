/**
 * Scratch: does the bar's frame actually take the state, and the owner's
 * face, from the messages main.js posts? Sends the real protocols and reads
 * the frame's own record of what it was told.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const K = await import("./tests/uikit.mjs");
const { base, close } = await K.serve();
const browser = await K.launch();
const page = await browser.newPage({ viewport: { width: 300, height: 80 }, deviceScaleFactor: 2 });
const errors = [];
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
await page.goto(`${base}/.bar-probe.html`);
await page.waitForFunction(() => window.__ready === true, null, { timeout: 30000 });

const out = [];
async function look(label) {
  const r = await page.evaluate(() => {
    const f = document.getElementById("reactor-face");
    const d = f.contentDocument;
    const cv = d.getElementById("display-canvas");
    return {
      ready: d.documentElement.getAttribute("data-hud-face"),
      canvas: cv ? [cv.width, cv.clientWidth] : null,
      label: cv ? cv.getAttribute("aria-label") : null,
      offline: d.documentElement.getAttribute("data-face-offline"),
      faceId: d.defaultView.__faceSwitch ? d.defaultView.__faceSwitch.now().face : null,
      lastState: d.defaultView.__faceVoice ? d.defaultView.__faceVoice.lastState : null,
    };
  });
  out.push([label, r]);
}

await look("after load");
// Exactly what main.js posts: the state, then the appearance.
await page.evaluate(() => window.__send({ type: "jarvis-hud-face", state: "thinking", offline: false, focus: false, waiting: 0, serious: false }));
await page.waitForTimeout(900);
await look("thinking");
await page.evaluate(() => window.__send({ type: "jarvis-hud-face", appearance: { face: "pygmyowl", bindings: {} } }));
await page.waitForTimeout(1200);
await look("appearance=pygmyowl");
await page.evaluate(() => window.__send({ type: "jarvis-hud-face", state: "standby", offline: true, focus: false, waiting: 0, serious: false }));
await page.waitForTimeout(900);
await look("offline");

for (const [label, r] of out) console.log(label.padEnd(22), JSON.stringify(r));
console.log("console errors:", errors.length ? errors : "none");
fs.writeFileSync(path.join(HERE, ".face-mini-out", "bar-wiring.json"), JSON.stringify({ out, errors }, null, 2));
await browser.close();
close();
