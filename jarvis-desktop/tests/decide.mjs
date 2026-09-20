/**
 * One action, one decision.
 *
 * The approval gate is the surface this whole app is arranged around: nothing
 * runs until a person says so, once. Three separate defects let the same
 * action be decided twice, or stopped it being decided at all, and every one
 * of them was invisible — the buttons looked live either way, and only the
 * server's 409 stood between a double-decide and a real one.
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

const GATE = [K.APPROVAL_PLAIN];
const decides = (page) => page.evaluate(() => window.__decides || []);

/* ── The spotlight ───────────────────────────────────────────────────────── */

await check("a failed decision can be retried", async () => {
  // The latch exists to stop a second decision racing a successful first one.
  // A decision that never reached the server is not a first one — and leaving
  // the latch set made the gate permanently unanswerable, with both buttons
  // re-enabled and every click silently returning.
  const page = await K.open(browser, base, "index.html",
    { pending: GATE, decideFails: "connection refused" });
  await page.locator("#approval-approve").click();
  await page.waitForTimeout(250);
  await page.locator("#approval-approve").click();
  await page.waitForTimeout(250);
  const sent = await decides(page);
  const hint = await page.locator("#approval-hint").innerText();
  await page.close();
  assert.equal(sent.length, 2, `the retry did not reach the server (${sent.length} attempts)`);
  assert.match(hint, /nothing was decided/i, `the hint said "${hint}"`);
});

await check("a 409 keeps the latch, because it really was answered", async () => {
  const page = await K.open(browser, base, "index.html",
    { pending: GATE, decideFails: "HTTP 409 already decided" });
  await page.locator("#approval-approve").click();
  await page.waitForTimeout(250);
  await page.locator("#approval-deny").click();
  await page.waitForTimeout(250);
  const sent = await decides(page);
  await page.close();
  assert.equal(sent.length, 1, "a gate answered elsewhere was answered again here");
});

await check("an answered gate cannot be answered again when it reopens", async () => {
  // `decide_approval` does not re-read the queue, so between answering and the
  // server's next event the tray still says "1 waiting" and its row reopens
  // the same card. Clearing the latch on close disarmed it exactly then.
  const page = await K.open(browser, base, "index.html", { pending: GATE });
  await page.locator("#approval-approve").click();
  await page.waitForTimeout(200);
  // The resolution lands and closes the card.
  await page.evaluate((id) => window.__emit("approval-resolved", { id }), K.APPROVAL_PLAIN.id);
  await page.waitForTimeout(200);
  // The tray reopens it from a queue that has not caught up.
  await page.evaluate(() => window.__emit("show-approval", {}));
  await page.waitForTimeout(250);
  await page.locator("#approval-deny").click();
  await page.waitForTimeout(250);
  const sent = await decides(page);
  await page.close();
  assert.equal(sent.length, 1,
    `the same action was decided ${sent.length} times: ${JSON.stringify(sent)}`);
});

await check("CONTROL: a different gate can still be answered", async () => {
  // Everything above is a negative. Without this they would all pass on a
  // build where nothing can be approved at all.
  const page = await K.open(browser, base, "index.html",
    { pending: [K.APPROVAL_PLAIN, K.APPROVAL_RAISED] });
  await page.locator("#approval-approve").click();
  await page.waitForTimeout(200);
  await page.evaluate((id) => window.__emit("approval-resolved", { id }), K.APPROVAL_PLAIN.id);
  await page.waitForTimeout(200);
  await page.evaluate((items) => window.__emit("approvals-changed",
    { count: items.length, items }), [K.APPROVAL_RAISED]);
  await page.waitForTimeout(300);
  await page.locator("#approval-deny").click();
  await page.waitForTimeout(250);
  const sent = await decides(page);
  await page.close();
  assert.equal(sent.length, 2, `expected two different gates answered, got ${JSON.stringify(sent)}`);
  assert.notEqual(sent[0].id, sent[1].id);
});

/* ── The widget ──────────────────────────────────────────────────────────── */

const widget = (data) => K.open(browser, base, "widget.html", data, { width: 320, height: 460 });

await check("the widget cannot send two decisions for one action", async () => {
  const page = await widget({ pending: GATE });
  await page.locator("#btn-appr-yes").click();
  await page.waitForTimeout(150);
  await page.locator("#btn-appr-no").click();
  await page.waitForTimeout(250);
  const sent = await decides(page);
  await page.close();
  assert.equal(sent.length, 1,
    `the widget sent ${sent.length} decisions: ${JSON.stringify(sent)}`);
});

await check("filing a note does not disable the gate", async () => {
  // One `busy` flag served both. Filing runs a whole chat turn and takes
  // seconds, during which Approve and Deny were live-looking no-ops.
  const page = await widget({ pending: GATE });
  await page.evaluate(() => {
    // Hold the capture in flight.
    const real = window.__TAURI__.core.invoke;
    window.__TAURI__.core.invoke = async (cmd, args) =>
      cmd === "capture_note" ? new Promise(() => {}) : real(cmd, args);
  });
  await page.fill("#capture-input", "a note");
  await page.press("#capture-input", "Enter");
  await page.waitForTimeout(200);
  await page.locator("#btn-appr-yes").click();
  await page.waitForTimeout(250);
  const sent = await decides(page);
  await page.close();
  assert.equal(sent.length, 1, "the gate was unanswerable while a note was filing");
});

await check("CONTROL: the widget's buttons do work", async () => {
  const page = await widget({ pending: GATE });
  await page.locator("#btn-appr-yes").click();
  await page.waitForTimeout(250);
  const sent = await decides(page);
  await page.close();
  assert.equal(sent.length, 1);
  assert.equal(sent[0].approved, true);
});

/* ── The gate that is not in the webview ─────────────────────────────────── */

// Every check above drives the buttons, and buttons are a courtesy. The Rust
// command is what actually posts the decision, and it is reachable from any
// window holding the `approvals` capability without going through a button at
// all. The jarvis-client branch found the same shape on its own side — a
// staleness gate consulted by one caller out of seven — and raised it in
// docs/CROSS-CLIENT-CONTRACT.md. This is a source assertion because the Rust
// cannot be linked here: no MSVC linker, no GTK for the host target.
await check("the Rust command refuses a stale queue too, not just the buttons", async () => {
  const src = await (await import("node:fs/promises")).readFile(
    new URL("../src-tauri/src/commands.rs", import.meta.url), "utf8");
  const fn = src.slice(src.indexOf("pub async fn decide_approval"));
  const body = fn.slice(0, fn.indexOf("\n}\n"));
  assert.match(body, /StreamState>\(\)\.link\(\)\.stale/,
    "decide_approval posts without consulting the link state");
  const gate = body.indexOf(".stale");
  const post = body.indexOf(".post(");
  assert.ok(gate > 0 && gate < post,
    "the staleness check must come before the request, not after it");
});

// Same reasoning, second gate. `jarvis-link.js` attaches `option_id` when a
// proposal carries several plans, and for a long time this signature did not
// take one - so Tauri dropped the key and the call landed as a plain
// whole-proposal approve. The per-option buttons were disabled in the webview
// to stop that, which is exactly the "courtesy, not a gate" this file's own
// comment above rejects: any window with the `approvals` capability can
// invoke the command directly. There is still no server route that can carry
// a choice, so the command must REFUSE rather than approve something else.
await check("the Rust command refuses an option it cannot actually send", async () => {
  const src = await (await import("node:fs/promises")).readFile(
    new URL("../src-tauri/src/commands.rs", import.meta.url), "utf8");
  const fn = src.slice(src.indexOf("pub async fn decide_approval"));
  const body = fn.slice(0, fn.indexOf("\n}\n"));
  assert.match(body, /option_id:\s*Option<String>/,
    "decide_approval must accept option_id, or Tauri drops it silently");
  const refusal = body.indexOf("option_id");
  const post = body.indexOf(".post(");
  assert.ok(refusal > 0 && refusal < post,
    "the option check must come before the request, not after it");
  assert.match(body, /return Err\(format!\(\s*\n?\s*"this Jarvis cannot approve one option/,
    "an option_id must produce an error, not be forwarded or ignored");
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\none action, one decision");
process.exit(fails.length ? 1 : 0);
