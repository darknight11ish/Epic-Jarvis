/**
 * The Settings card's HUD layout picker keeps the owner's saved layouts.
 *
 * H3 post-merge audit (task-100, H3-PM-1): choosing a built-in preset used to
 * save `presetLayout(id)`, whose `user_presets` is empty, so one radio click in
 * Settings silently deleted every layout in "My layouts". The store now takes
 * the current document and keeps its library; this test drives the real
 * settings.html page and reads back what the page actually wrote through
 * `set_hud_layout` - never the click's own promise.
 */
import assert from "node:assert/strict";
import * as K from "./uikit.mjs";
import { normalizeLayout, presetLayout } from "../src/hud-layout.js";

const { base, close } = await K.serve();
const browser = await K.launch();
const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const VIEW = { width: 900, height: 1800 };
const open = (hudLayout) => K.open(browser, base, "settings.html", { hudLayout }, VIEW);

/** The owner's saved document: active Quiet + one custom layout "Mine". */
function savedDocument() {
  const cockpit = presetLayout("cockpit");
  const entry = {
    id: "custom-cockpit-1", name: "Mine", base_preset: "cockpit",
    shell_template: "three-column", density: "comfortable",
    default_stage_tab: "talk", cards: cockpit.cards,
  };
  return normalizeLayout({ ...presetLayout("quiet"), user_presets: [entry] });
}

const writes = (page) => page.evaluate(() => (window.__hudLayoutWrites || []).length);
const saved = (page) => page.evaluate(() => window.__hudLayout);

await check("H3-PM-1: choosing a built-in preset in Settings keeps My layouts", async () => {
  const page = await open(savedDocument());
  await page.waitForSelector('#hud-layout-list input[name="hud-layout"]', { timeout: 10000 });
  // One custom row is listed, and it is the owner's saved layout, not a built-in.
  assert.equal(await page.locator('input[name="hud-layout"][value="custom-cockpit-1"]').count(), 1,
    "the saved custom layout is not listed");
  await page.locator('input[name="hud-layout"][value="cockpit"]').check();
  await page.waitForFunction(() => (window.__hudLayoutWrites || []).length > 0, null,
    { timeout: 8000 });
  const layout = await saved(page);
  assert.equal(layout.base_preset, "cockpit", "the chosen built-in preset is not active");
  assert.deepEqual(layout.user_presets.map((entry) => entry.id), ["custom-cockpit-1"],
    `the built-in choice deleted My layouts: ${JSON.stringify(layout.user_presets)}`);
  assert.equal(layout.user_presets[0].name, "Mine", "the saved layout lost its name");
  assert.equal(await writes(page), 1, "one preset choice made more than one write");
  const status = await page.locator("#hud-layout-status").innerText();
  assert.match(status, /Cockpit/, `the status line lies: ${status}`);
  await page.close();
  assert.deepEqual(page.__errors, []);
});

await check("H3-PM-1: choosing one of My layouts keeps the rest of the library", async () => {
  const page = await open(savedDocument());
  await page.waitForSelector('#hud-layout-list input[name="hud-layout"]', { timeout: 10000 });
  await page.locator('input[name="hud-layout"][value="custom-cockpit-1"]').check();
  await page.waitForFunction(() => (window.__hudLayoutWrites || []).length > 0, null,
    { timeout: 8000 });
  const layout = await saved(page);
  assert.equal(layout.id, "custom-cockpit-1", "the chosen saved layout is not active");
  assert.deepEqual(layout.user_presets.map((entry) => entry.id), ["custom-cockpit-1"],
    "choosing a saved layout lost the library");
  await page.close();
  assert.deepEqual(page.__errors, []);
});

await check("H3-PM-1: Reset HUD to Cockpit keeps My layouts", async () => {
  const page = await open(savedDocument());
  await page.waitForSelector("#hud-reset-layout", { timeout: 10000 });
  await page.locator("#hud-reset-layout").click();
  await page.waitForFunction(() => (window.__hudLayoutWrites || []).length > 0, null,
    { timeout: 8000 });
  const layout = await saved(page);
  assert.equal(layout.base_preset, "cockpit", "Reset did not choose Cockpit");
  assert.deepEqual(layout.user_presets.map((entry) => entry.id), ["custom-cockpit-1"],
    "Reset deleted My layouts");
  await page.close();
  assert.deepEqual(page.__errors, []);
});

await browser.close();
await close();
if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join(", ")}`);
  process.exit(1);
}
console.log("\nall passed");
