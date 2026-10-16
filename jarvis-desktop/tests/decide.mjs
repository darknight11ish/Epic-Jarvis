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

/* ── What the owner types into the bar ───────────────────────────────────── */

/**
 * The owner's report of 2026-10-16: "after i click open the card and type into
 * the jarvis bar that i approve, nothing happens. i have no idea what happens".
 * He was right - there was no typed path at all. There is one now, and these
 * checks hold it to the three rules it has to obey: it decides only when the
 * whole message is the decision, it decides through the button's own
 * `decideApproval`, and it never guesses at an ambiguous sentence.
 */
const typeIntoTheBar = async (page, text) => {
  await page.fill("#prompt", text);
  await page.keyboard.press("Enter");
  await page.waitForTimeout(300);
};

await check("typing “i approve” answers the waiting card, and sends no chat turn", async () => {
  const page = await K.open(browser, base, "index.html", { pending: GATE });
  const turnsBefore = await K.turnsSent(page);
  await typeIntoTheBar(page, "i approve");
  const sent = await decides(page);
  const turns = await K.turnsSent(page);
  const feed = await page.locator("#answer").innerText();
  const box = await page.locator("#prompt").inputValue();
  await page.close();
  assert.equal(sent.length, 1, `nothing was decided: ${JSON.stringify(sent)}`);
  assert.equal(sent[0].id, K.APPROVAL_PLAIN.id);
  assert.equal(sent[0].approved, true);
  assert.equal(turns, turnsBefore,
    "the words were ALSO sent to the model, so the owner gets an answer about something else");
  assert.match(feed, /Approved/, `the bar said nothing about the decision: ${feed}`);
  assert.equal(box, "", "the decision stayed in the box, where Enter would send it again");
});

await check("typing “deny” denies it, through the same command", async () => {
  const page = await K.open(browser, base, "index.html", { pending: GATE });
  await typeIntoTheBar(page, "Deny.");
  const sent = await decides(page);
  await page.close();
  assert.deepEqual(sent.map((d) => [d.id, d.approved]), [[K.APPROVAL_PLAIN.id, false]]);
});

await check("CONTROL: an ordinary prompt still goes to the model while a card waits", async () => {
  // The typed path must not swallow what the bar is for. A prompt that is not
  // one of the decision's own forms is a prompt, card or no card.
  const page = await K.open(browser, base, "index.html",
    { pending: GATE, chatReplies: ["Tuesday at 3."] });
  const before = await K.turnsSent(page);
  await typeIntoTheBar(page, "when is the dentist?");
  const sent = await decides(page);
  const turns = await K.turnsSent(page);
  await page.close();
  assert.equal(sent.length, 0, "an ordinary question decided the card");
  assert.equal(turns, before + 1, "the prompt never reached the model");
});

await check("a sentence that only sounds like an answer decides nothing, and says so", async () => {
  // "yes", "ok do it", "go ahead": exactly the words that produced "i have no
  // idea what happens". Rule 4 forbids inferring a decision from them, and
  // sending them to the model is what made the bar look broken - so the bar
  // answers with what to press, and the card is untouched.
  for (const said of ["yes", "ok", "go ahead", "do it", "sure, please do"]) {
    const page = await K.open(browser, base, "index.html", { pending: GATE });
    const turnsBefore = await K.turnsSent(page);
    await typeIntoTheBar(page, said);
    const sent = await decides(page);
    const turns = await K.turnsSent(page);
    const hint = await page.locator("#approval-hint").innerText();
    await page.close();
    assert.equal(sent.length, 0, `"${said}" was taken as a decision`);
    assert.equal(turns, turnsBefore, `"${said}" was quietly sent to the model`);
    assert.match(hint, /press Approve or Deny/i, `"${said}" got no explanation ("${hint}")`);
  }
});

await check("a raised card refuses a typed approval, and a typed deny still works", async () => {
  // `quickActionable` is the gate every faster path goes through, and typing is
  // a faster path: an item carrying `raised` is on the card BECAUSE outside
  // text tried to hurry the reader, so the fast answer must not be available
  // for it. Deny is never held - refusing costs a retry.
  const raised = await K.open(browser, base, "index.html", { pending: [K.APPROVAL_RAISED] });
  await typeIntoTheBar(raised, "i approve");
  const refused = await decides(raised);
  const hint = await raised.locator("#approval-hint").innerText();
  await raised.close();
  assert.equal(refused.length, 0, "a raised card was approved from a typed word");
  assert.match(hint, /tried to rush/i, `the refusal did not say why: "${hint}"`);

  const denying = await K.open(browser, base, "index.html", { pending: [K.APPROVAL_RAISED] });
  await typeIntoTheBar(denying, "i deny it");
  const denied = await decides(denying);
  await denying.close();
  assert.deepEqual(denied.map((d) => [d.id, d.approved]), [[K.APPROVAL_RAISED.id, false]]);
});

await check("a parked card is not answered from a typed word - the bar says where it is", async () => {
  // Esc puts a card aside without deciding it, so a queue can be waiting with
  // nothing on screen. Picking one of those from a word would be a guess at
  // WHICH card the owner meant.
  const page = await K.open(browser, base, "index.html", { pending: GATE });
  await page.keyboard.press("Escape");
  await page.waitForTimeout(200);
  await typeIntoTheBar(page, "i approve");
  const sent = await decides(page);
  const feed = await page.locator("#answer").innerText();
  await page.close();
  assert.equal(sent.length, 0, "a card that was not on screen was decided from a typed word");
  assert.match(feed, /waiting/i, `the bar did not say a card is waiting: ${feed}`);
  assert.match(feed, /decides nothing/i, `the bar did not say nothing was decided: ${feed}`);
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
// `decide_approval` is a thin command now: the body both it and a
// notification's Deny share is `answer_approval` (the Windows Hello check for
// an Approve lives there too - tests/security.mjs), so that is what is read.
await check("the Rust command refuses a stale queue too, not just the buttons", async () => {
  const src = await (await import("node:fs/promises")).readFile(
    new URL("../src-tauri/src/commands.rs", import.meta.url), "utf8");
  const cmd = src.slice(src.indexOf("pub async fn decide_approval"));
  assert.match(cmd.slice(0, cmd.indexOf("\n}\n")), /answer_approval\(/,
    "decide_approval no longer goes through answer_approval");
  const fn = src.slice(src.indexOf("async fn answer_approval"));
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
  const cmd = src.slice(src.indexOf("pub async fn decide_approval"));
  assert.match(cmd.slice(0, cmd.indexOf("\n}\n")), /option_id:\s*Option<String>/,
    "decide_approval must accept option_id, or Tauri drops it silently");
  const fn = src.slice(src.indexOf("async fn answer_approval"));
  const body = fn.slice(0, fn.indexOf("\n}\n"));
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
