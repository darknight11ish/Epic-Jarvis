/**
 * "Jarvis is working on your screen, 0:42 - Stop" (the owner's choice of
 * 2026-09-28; screen-work.js, src-tauri/src/screen_work.rs).
 *
 * The widget's line shows only while the PC says a screen-control plan is
 * running, counts up, goes when the PC says the plan ended, and its Stop is
 * the Stop everything key - never the task Stop, never held by App lock.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import * as K from "./uikit.mjs";
import { WORKING_WORDS, nextScreenWork, secondsRunning } from "../src/screen-work.js";

const { base, close } = await K.serve();
const browser = await K.launch();
const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const IDLE = { activity: "idle", activity_detail: "" };
const RUNNING = { running: true, id: "task_ab12", elapsed_ms: 42_000 };
const widget = (data = {}) =>
  K.open(browser, base, "widget.html", { pending: [], link: IDLE, ...data }, { width: 320, height: 520 });
const report = (page, activity) => page.evaluate(
  (activity) => window.__emit("jarvis-link", {
    connected: true, stale: false, activity, activity_detail: activity === "working" ? "Step 1/3: a click in another program's window" : "",
  }),
  activity
);
const setPc = (page, answer) => page.evaluate((a) => { window.__screenWork = a; }, answer);
const calls = (page, name) => page.evaluate((n) => window.__calls.filter(([c]) => c === n).length, name);
const strip = (page) => page.locator("#screen-strip");

await check("idle: no line, and the PC is not asked at all", async () => {
  const page = await widget();
  await page.waitForTimeout(300);
  const hidden = await strip(page).isHidden();
  const asked = await calls(page, "screen_work");
  await page.close();
  assert.ok(hidden);
  assert.equal(asked, 0, "an idle Jarvis costs no requests");
});

await check("working on something else (no screen plan): no line", async () => {
  const page = await widget();
  await setPc(page, { running: false, id: null, elapsed_ms: null });
  await report(page, "working");
  await page.waitForTimeout(300);
  const hidden = await strip(page).isHidden();
  const asked = await calls(page, "screen_work");
  await page.close();
  assert.ok(hidden, "a web search or a chat answer is not Jarvis on the screen");
  assert.ok(asked >= 1, "working is when the widget asks");
});

await check("a screen plan running: the words, the clock from the PC's time, and Stop", async () => {
  const page = await widget();
  await setPc(page, RUNNING);
  await report(page, "working");
  await page.waitForTimeout(300);
  const visible = await strip(page).isVisible();
  const words = (await page.locator("#screen-word").textContent()).trim();
  const clock = (await page.locator("#screen-clock").textContent()).trim();
  const stop = (await page.locator("#screen-stop").textContent()).trim();
  const errors = page.__errors || [];
  await page.close();
  assert.ok(visible);
  assert.equal(words, WORKING_WORDS);
  assert.match(clock, /^0:4[23]$/, `clock was ${clock}`);
  assert.equal(stop, "Stop");
  assert.deepEqual(errors, []);
});

await check("the clock counts up while it runs", async () => {
  const page = await widget();
  await setPc(page, { running: true, id: "t1", elapsed_ms: 5_000 });
  await report(page, "working");
  await page.waitForTimeout(250);
  const first = (await page.locator("#screen-clock").textContent()).trim();
  await page.waitForTimeout(2200);
  const later = (await page.locator("#screen-clock").textContent()).trim();
  await page.close();
  assert.equal(first, "0:05");
  assert.ok(later === "0:07" || later === "0:08", `later was ${later}`);
});

await check("Stop is Stop everything - not the task Stop", async () => {
  const page = await widget();
  await setPc(page, RUNNING);
  await report(page, "working");
  await page.waitForTimeout(300);
  await page.locator("#screen-stop").click();
  await page.waitForTimeout(200);
  const everything = await calls(page, "stop_everything");
  const task = await calls(page, "stop_task");
  const stillShown = await strip(page).isVisible();
  await page.close();
  assert.equal(everything, 1);
  assert.equal(task, 0);
  assert.ok(stillShown, "the line goes when the PC says the plan ended, not on the click");
});

await check("the line goes when the PC says the plan ended", async () => {
  const page = await widget();
  await setPc(page, RUNNING);
  await report(page, "working");
  await page.waitForTimeout(300);
  await setPc(page, { running: false, id: null, elapsed_ms: null });
  await page.waitForTimeout(2300); // one poll
  const hidden = await strip(page).isHidden();
  await page.close();
  assert.ok(hidden);
});

await check("Jarvis stops working and the last ask fails: the line goes, no stale clock", async () => {
  const page = await widget();
  await setPc(page, RUNNING);
  await report(page, "working");
  await page.waitForTimeout(300);
  await page.evaluate(() => { window.__screenWorkFails = "could not reach the Jarvis server"; });
  await report(page, "idle");
  await page.waitForTimeout(300);
  const hidden = await strip(page).isHidden();
  await page.close();
  assert.ok(hidden);
});

await check("a failed ask while still working keeps the line (Stop stays in reach)", async () => {
  const page = await widget();
  await setPc(page, RUNNING);
  await report(page, "working");
  await page.waitForTimeout(300);
  await page.evaluate(() => { window.__screenWorkFails = "timed out"; });
  await page.waitForTimeout(2300);
  const visible = await strip(page).isVisible();
  await page.close();
  assert.ok(visible);
});

await check("App lock on: the line and its Stop still work (Stop is never held)", async () => {
  const page = await widget({ appLock: true });
  await setPc(page, RUNNING);
  await report(page, "working");
  await page.waitForTimeout(300);
  const visible = await strip(page).isVisible();
  const disabled = await page.locator("#screen-stop").isDisabled();
  await page.locator("#screen-stop").click();
  await page.waitForTimeout(150);
  const everything = await calls(page, "stop_everything");
  await page.close();
  assert.ok(visible);
  assert.ok(!disabled);
  assert.equal(everything, 1);
});

await check("the start time is fixed per plan, so the clock never jumps with each poll", async () => {
  const a = nextScreenWork(null, { running: true, id: "x", elapsed_ms: 10_000 }, 100_000);
  assert.deepEqual(a, { id: "x", since: 90_000 });
  const same = nextScreenWork(a, { running: true, id: "x", elapsed_ms: 13_500 }, 102_000);
  assert.equal(same, a);
  const next = nextScreenWork(a, { running: true, id: "y", elapsed_ms: null }, 200_000);
  assert.deepEqual(next, { id: "y", since: 200_000 }, "no trusted time: count from first seen");
  assert.equal(nextScreenWork(a, { running: false }, 1), null);
  assert.equal(nextScreenWork(a, null, 1), null);
  assert.equal(secondsRunning({ since: 1_000 }, 43_999), 42);
  assert.equal(secondsRunning({ since: 5_000 }, 1_000), 0);
});

await check("wiring: the HTML's words, the backend's tool name, and who may call the commands", async () => {
  const html = readFileSync(new URL("../src/widget.html", import.meta.url), "utf8");
  assert.ok(html.includes(`>${WORKING_WORDS}<`), "the HTML starts with the same words the module exports");
  const rs = readFileSync(new URL("../src-tauri/src/screen_work.rs", import.meta.url), "utf8");
  const agent = readFileSync(new URL("../../backend/jarvis_agent.py", import.meta.url), "utf8");
  assert.ok(rs.includes('pub const SCREEN_TOOL: &str = "control_computer";'));
  assert.match(agent, /"control_computer": "jarvis_ui_control"/,
    "the backend's screen-control tool is still called control_computer");
  const toml = readFileSync(new URL("../src-tauri/permissions/surfaces.toml", import.meta.url), "utf8");
  const set = toml.slice(toml.indexOf('identifier = "task-control"'));
  const block = set.slice(0, set.indexOf("]"));
  assert.ok(block.includes('"allow-screen-work"') && block.includes('"allow-stop-everything"'),
    "both ride with the task controls");
  const widgetCap = JSON.parse(readFileSync(new URL("../src-tauri/capabilities/widget.json", import.meta.url), "utf8"));
  assert.ok(widgetCap.permissions.includes("task-control"));
  const lib = readFileSync(new URL("../src-tauri/src/lib.rs", import.meta.url), "utf8");
  assert.ok(lib.includes("screen_work::stop_everything,") && lib.includes("screen_work::screen_work,"));
});

await browser.close();
close();
if (fails.length) {
  console.log(`\n${fails.length} failed`);
  process.exit(1);
}
console.log("\nall passed");
