/**
 * Renders every surface in every state it can be in, into shots/<theme>/.
 *
 * Usage: node shots.mjs [theme ...]      (default: whatever the CSS ships)
 *
 * The point is to make a change visible across all the states it touches at
 * once, rather than checking the one screen that happened to be open.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import * as K from "./uikit.mjs";

const OUT = fileURLToPath(new URL("./shots", import.meta.url));
const themes = process.argv.slice(2);
const THEMES = themes.length ? themes : ["default"];

// Each scenario: which page, the viewport, the backend data, and a driver that
// puts the page into the state before the shutter.
const SCENES = [
  { id: "01-quickbar-idle", file: "index.html", vp: { width: 750, height: 200 },
    data: { pending: [], attention: K.ATTENTION_CLEAR } },

  { id: "02-quickbar-offline", file: "index.html", vp: { width: 750, height: 220 },
    data: { pending: [], attention: { ...K.ATTENTION_CLEAR, known: false },
            link: { connected: false, stale: true,
                    error: "could not reach the Jarvis server at http://127.0.0.1:4719" } } },

  { id: "03-quickbar-answer", file: "index.html", vp: { width: 750, height: 620 },
    data: { pending: [], attention: K.ATTENTION_CLEAR, answer: K.ANSWER_MD },
    async drive(page) {
      // Push a finished answer through the card's own render path.
      await page.evaluate(() => {
        const md = window.__answer;
        document.getElementById("card").hidden = false;
        document.documentElement.dataset.state = "done";
        document.getElementById("card-status-text").textContent = "Answered";
        document.getElementById("answer").innerHTML = "";
        return md;
      });
      await page.fill("#prompt", "what changed in the reactor spec this week?");
      await page.evaluate((md) => {
        // Use the page's own markdown renderer so this is the real output.
        const ev = new CustomEvent("__render", { detail: md });
        window.dispatchEvent(ev);
      }, K.ANSWER_MD);
    } },

  { id: "04-quickbar-approval", file: "index.html", vp: { width: 750, height: 480 },
    data: { pending: [K.APPROVAL_PLAIN], attention: K.ATTENTION_CLEAR } },

  { id: "05-quickbar-approval-raised", file: "index.html", vp: { width: 750, height: 620 },
    data: { pending: [K.APPROVAL_RAISED], attention: K.ATTENTION_CLEAR },
    async drive(page) { await page.click("#raised-context-wrap summary").catch(() => {}); } },

  { id: "06-quickbar-attention", file: "index.html", vp: { width: 750, height: 460 },
    data: { pending: [], attention: K.ATTENTION_BANKED } },

  { id: "07-quickbar-everything", file: "index.html", vp: { width: 750, height: 760 },
    data: { pending: [K.APPROVAL_RAISED], attention: K.ATTENTION_BANKED },
    async drive(page) {
      await page.evaluate(() => window.__emit("show-digest", null));
      await page.waitForTimeout(300);
    } },

  { id: "08-widget-collapsed", file: "widget.html", vp: { width: 340, height: 70 },
    data: { pending: [], prefs: { expanded: false } },
    async drive(page) {
      await page.evaluate((t) => window.__emit("desktop-telemetry", t), K.TELEMETRY);
      await page.evaluate(() => window.__emit("health-report",
        { services: [{ name: "jarvis", online: true }, { name: "ollama", online: true }] }));
      await page.waitForTimeout(200);
    } },

  { id: "09-widget-expanded", file: "widget.html", vp: { width: 340, height: 320 },
    data: { pending: [], prefs: { expanded: true } },
    async drive(page) {
      await page.evaluate((t) => window.__emit("desktop-telemetry", t), K.TELEMETRY);
      await page.evaluate(() => window.__emit("health-report",
        { services: [{ name: "jarvis", online: true }, { name: "ollama", online: true }] }));
      await page.waitForTimeout(200);
    } },

  { id: "10-widget-approval", file: "widget.html", vp: { width: 340, height: 400 },
    data: { pending: [K.APPROVAL_RAISED], prefs: { expanded: true } },
    async drive(page) {
      await page.evaluate((t) => window.__emit("desktop-telemetry", t), K.TELEMETRY);
      await page.waitForTimeout(200);
    } },

  { id: "11-settings", file: "settings.html", vp: { width: 680, height: 900 },
    data: { pending: [] } },
];

const { base, close } = await K.serve();
const browser = await K.launch();
const problems = [];

for (const theme of THEMES) {
  const dir = path.join(OUT, theme);
  fs.mkdirSync(dir, { recursive: true });
  for (const scene of SCENES) {
    const page = await K.open(browser, base, scene.file, scene.data, scene.vp);
    if (theme !== "default") {
      await page.evaluate((t) => document.documentElement.setAttribute("data-theme", t), theme);
      await page.waitForTimeout(150);
    }
    if (scene.drive) { try { await scene.drive(page); } catch (e) { problems.push(`${scene.id}: drive failed: ${e.message}`); } }
    await page.waitForTimeout(250);
    await page.screenshot({ path: path.join(dir, `${scene.id}.png`) });
    for (const e of page.__errors) problems.push(`${theme}/${scene.id}: ${e}`);
    await page.close();
  }
  console.log(`shot ${SCENES.length} scenes -> ${dir}`);
}

await browser.close();
close();
if (problems.length) { console.log("\nPROBLEMS:\n  " + problems.join("\n  ")); }
