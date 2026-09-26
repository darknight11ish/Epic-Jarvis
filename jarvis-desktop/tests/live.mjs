/**
 * Brain -> Live: what Jarvis is doing, step by step.
 *
 * Live used to say per-step reasoning "is not on the bus yet". The backend's
 * tool loop now publishes `step` events (jarvis_agent.py `_step_event`):
 * asking the model, each tool starting / finishing / being refused, writing
 * the answer. These check that Live shows them in plain words, shows the
 * tool loop's `activity` detail in both event shapes, and no longer claims
 * the steps are missing - while saying plainly that the model's own
 * reasoning is not shown, and why.
 */
import assert from "node:assert/strict";
import * as K from "./uikit.mjs";

const { base, close } = await K.serve();
const browser = await K.launch();
const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

async function live() {
  const page = await K.open(browser, base, "brain.html", {}, { width: 1180, height: 780 });
  await page.locator("#rail-advanced-toggle").click();
  await page.locator("#tab-live").click();
  await page.waitForTimeout(150);
  return page;
}

const frame = (kind, data, id) => ({ kind, id, data });
const rows = (page) => page.evaluate(() => [...document.querySelectorAll("#trace li")].map((li) => ({
  kind: li.querySelector(".trace-kind")?.textContent,
  body: li.querySelector(".trace-body")?.textContent,
})));

await check("a tool turn's steps appear in Live, in order, in plain words", async () => {
  const page = await live();
  const steps = [
    { phase: "model", round: 1 },
    { phase: "tool_started", tool: "calculator" },
    { phase: "tool_finished", tool: "calculator", ok: true },
    { phase: "tool_refused", tool: "shell_exec" },
    { phase: "tool_finished", tool: "file_read", ok: false },
    { phase: "tool_refused", tool: "unknown" },
    { phase: "model", round: 2 },
    { phase: "answer" },
  ];
  await page.evaluate((frames) => {
    frames.forEach((f) => window.__emit("jarvis-event", f));
  }, steps.map((d, i) => frame("step", d, 100 + i)));
  await page.waitForTimeout(150);
  const got = (await rows(page)).filter((r) => r.kind === "step").map((r) => r.body);
  const errors = page.__errors;
  await page.close();
  assert.deepEqual(got, [
    "asking the model",
    "using calculator",
    "calculator done",
    "shell_exec not allowed",
    "file_read failed",
    "the model asked for a tool Jarvis does not have",
    "asking the model again (round 2)",
    "writing the answer",
  ]);
  assert.deepEqual(errors, []);
});

await check("the tool loop's activity detail shows, in either event shape", async () => {
  const page = await live();
  await page.evaluate(() => {
    window.__emit("jarvis-event", { kind: "activity", id: 1,
      data: { key: "activity", value: { state: "working", detail: "Using calculator..." } } });
    window.__emit("jarvis-event", { kind: "activity", id: 2, data: { state: "speaking" } });
  });
  await page.waitForTimeout(150);
  const got = (await rows(page)).filter((r) => r.kind === "activity").map((r) => r.body);
  await page.close();
  assert.deepEqual(got, ["working · Using calculator...", "speaking"]);
});

await check("Live no longer says steps are missing, and says why reasoning is not shown", async () => {
  const page = await live();
  const note = await page.locator("#trace-note").textContent();
  await page.close();
  assert.doesNotMatch(note, /not on the bus yet/);
  assert.match(note, /each tool/);
  assert.match(note, /thinking is not shown/);
  assert.match(note, /reaches your phone/);
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nLive shows the steps, and only the steps");
process.exit(fails.length ? 1 : 0);
