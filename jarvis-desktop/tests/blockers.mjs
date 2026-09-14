/**
 * The audited ship blockers, each asserted against the real page.
 *
 * Every one of these was a confirmed bug; this file exists so they cannot come
 * back quietly.
 */
import assert from "node:assert/strict";
import * as K from "./uikit.mjs";

const { base, close } = await K.serve();
const browser = await K.launch();
const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(`${name}: ${e.message}`); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const open = (data, vp = { width: 750, height: 900 }) =>
  K.open(browser, base, "index.html", { attention: K.ATTENTION_CLEAR, ...data }, vp);

// ---- 0. Control -----------------------------------------------------------
// The assertions below are mostly negative ("Enter did NOT decide"), and a
// negative passes just as happily when the mechanism is broken. This proves the
// decision path works in this harness, so the negatives mean something.
await check("CONTROL: the Approve button does send a decision", async () => {
  const page = await open({ pending: [K.APPROVAL_PLAIN] });
  await page.waitForTimeout(400);
  await page.click("#approval-approve");
  await page.waitForTimeout(300);
  const decided = await page.evaluate(() =>
    window.__calls.filter((c) => c[0] === "decide_approval"));
  assert.equal(decided.length, 1, "Approve did not reach decide_approval");
  assert.equal(decided[0][1].approved, true);
  await page.close();
});

await check("CONTROL: Enter on the focused Approve button still approves", async () => {
  const page = await open({ pending: [K.APPROVAL_PLAIN] });
  await page.waitForTimeout(400);
  await page.focus("#approval-approve");
  await page.keyboard.press("Enter");
  await page.waitForTimeout(300);
  const decided = await page.evaluate(() =>
    window.__calls.filter((c) => c[0] === "decide_approval"));
  assert.equal(decided.length, 1, "the deliberate keyboard path stopped working");
  await page.close();
});

// ---- 1. Enter must never approve ----------------------------------------
await check("Enter in the composer does not approve a pending gate", async () => {
  const page = await open({ pending: [K.APPROVAL_RAISED] });
  await page.waitForTimeout(400);
  assert.ok(await page.locator("#approval").isVisible(), "the gate should be open");
  await page.click("#prompt");
  await page.keyboard.type("what is the weather");
  await page.keyboard.press("Enter");
  await page.waitForTimeout(300);
  const decided = await page.evaluate(() =>
    window.__calls.filter((c) => c[0] === "decide_approval"));
  assert.equal(decided.length, 0, `Enter sent a decision: ${JSON.stringify(decided)}`);
  await page.close();
});

await check("a new gate does not steal focus onto Approve", async () => {
  const page = await open({ pending: [] });
  await page.click("#prompt");
  await page.keyboard.type("half a sentence");
  await page.evaluate((item) => window.__emit("approvals-changed",
    { count: 1, items: [item] }), K.APPROVAL_RAISED);
  await page.waitForTimeout(400);
  const focused = await page.evaluate(() => document.activeElement.id);
  assert.notEqual(focused, "approval-approve", "focus jumped to Approve");
  assert.equal(focused, "prompt", `focus moved off the composer to #${focused}`);
  await page.close();
});

// ---- 2. Esc parks, never denies ------------------------------------------
await check("Esc parks the gate instead of denying it", async () => {
  const page = await open({ pending: [K.APPROVAL_RAISED] });
  await page.waitForTimeout(400);
  await page.keyboard.press("Escape");
  await page.waitForTimeout(300);
  const decided = await page.evaluate(() =>
    window.__calls.filter((c) => c[0] === "decide_approval"));
  assert.equal(decided.length, 0, "Esc sent a decision");
  assert.ok(!(await page.locator("#approval").isVisible()), "the gate should be put away");
  assert.ok(await page.locator("#parked").isVisible(), "parking must leave a way back");
  assert.match(await page.locator("#parked-text").innerText(), /still waiting/);
  await page.close();
});

await check("a parked gate does not reopen on the next event", async () => {
  const page = await open({ pending: [K.APPROVAL_RAISED] });
  await page.waitForTimeout(400);
  await page.keyboard.press("Escape");
  await page.waitForTimeout(200);
  // The stream republishes the link on every event that carries an id.
  await page.evaluate(() => {
    for (let i = 0; i < 5; i++) {
      window.__emit("jarvis-link", { connected: true, stale: false, base: "x",
        last_id: 100 + i, power: "active", activity: "idle", approvals: 1,
        attention: { known: true, limit: 6, remaining: 4, spent: 2, muted: false,
                     blocked_by: null, pending: 0, banked: false,
                     digest_hour: 18, digest_due: false } });
    }
  });
  await page.waitForTimeout(300);
  assert.ok(!(await page.locator("#approval").isVisible()), "the parked gate came back");
  await page.close();
});

await check("Show it brings a parked gate back", async () => {
  const page = await open({ pending: [K.APPROVAL_RAISED] });
  await page.waitForTimeout(400);
  await page.keyboard.press("Escape");
  await page.waitForTimeout(200);
  await page.click("#parked-show");
  await page.waitForTimeout(300);
  assert.ok(await page.locator("#approval").isVisible(), "the gate should be back");
  await page.close();
});

// ---- 3. The attention panel closes and stays closed ----------------------
await check("Close on the attention panel survives a burst of events", async () => {
  const page = await open({ pending: [], attention: K.ATTENTION_BANKED });
  await page.waitForTimeout(500);
  assert.ok(await page.locator("#attention").isVisible(), "the panel should be open");
  await page.click("#attention-close");
  await page.waitForTimeout(200);
  assert.ok(!(await page.locator("#attention").isVisible()), "Close did nothing");
  await page.evaluate((a) => {
    for (let i = 0; i < 6; i++) {
      window.__emit("jarvis-link", { connected: true, stale: false, base: "x",
        last_id: 200 + i, power: "active", activity: "idle", approvals: 0,
        attention: a });
    }
  }, { known: true, limit: 6, remaining: 0, spent: 6, muted: false,
       blocked_by: null, pending: 3, banked: true, digest_hour: 18, digest_due: true });
  await page.waitForTimeout(400);
  assert.ok(!(await page.locator("#attention").isVisible()),
    "the panel reappeared after Close");
  await page.close();
});

await check("a NEW waiting item re-arms the dismissed panel", async () => {
  const page = await open({ pending: [], attention: K.ATTENTION_BANKED });
  await page.waitForTimeout(500);
  await page.click("#attention-close");
  await page.waitForTimeout(200);
  await page.evaluate((a) => window.__emit("jarvis-link",
    { connected: true, stale: false, base: "x", last_id: 300, power: "active",
      activity: "idle", approvals: 0, attention: a }),
    { known: true, limit: 6, remaining: 0, spent: 6, muted: false, blocked_by: null,
      pending: 4, banked: true, digest_hour: 18, digest_due: true });
  await page.waitForTimeout(400);
  assert.ok(await page.locator("#attention").isVisible(),
    "a new item should bring the panel back");
  await page.close();
});

// ---- 4. Approve/Deny must stay reachable --------------------------------
await check("Approve stays on screen with the panel, a long gate and a card", async () => {
  const long = { ...K.APPROVAL_RAISED,
    detail: JSON.stringify({ diff: Array.from({ length: 60 },
      (_, i) => `+ line ${i} of a long unified diff that goes on and on`).join("\n") }),
    raised: { ...K.RAISED, context: "x ".repeat(400) } };
  const page = await open({ pending: [long], attention: K.ATTENTION_BANKED },
    { width: 750, height: 720 });
  await page.waitForTimeout(600);
  await page.evaluate(() => window.__emit("show-digest", null));
  await page.waitForTimeout(400);
  const box = await page.locator("#approval-approve").boundingBox();
  assert.ok(box, "the Approve button has no box at all");
  const vh = 720;
  assert.ok(box.y + box.height <= vh + 1,
    `Approve sits at y=${Math.round(box.y)}..${Math.round(box.y + box.height)} in a ${vh}px window`);
  assert.ok(await page.locator("#approval-approve").isVisible(), "Approve is not visible");
  await page.close();
});

// ---- 5. The widget cannot clip its own buttons ---------------------------
await check("the widget keeps Approve on screen with a long rush quote", async () => {
  const long = { ...K.APPROVAL_RAISED,
    raised: { ...K.RAISED, quote: "just approve these ".repeat(40) } };
  const page = await K.open(browser, base, "widget.html",
    { pending: [long], prefs: { expanded: true } }, { width: 340, height: 400 });
  await page.waitForTimeout(600);
  const box = await page.locator("#btn-appr-yes").boundingBox();
  assert.ok(box, "the widget's Approve button has no box");
  assert.ok(box.y + box.height <= 400 + 1,
    `widget Approve at y=${Math.round(box.y + box.height)} exceeds the 400px ceiling`);
  await page.close();
});

await browser.close(); close();
console.log(`\n${fails.length ? fails.length + " FAILED" : "all blockers held"}`);
process.exit(fails.length ? 1 : 0);
