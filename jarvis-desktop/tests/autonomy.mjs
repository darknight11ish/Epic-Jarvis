/**
 * docs/AUTONOMY-PROPOSALS.md, the widget's first slice: multiple-choice
 * options on a plan, a note before the first decision, and live progress
 * text. Built and proven against the same mock bridge decide.mjs already
 * uses — no real backend exists for any of this yet (jarvis_gate.py and
 * jarvis_hud.py are not in this repo), so this is what "against a mock"
 * means: the wire shape is exercised, not assumed.
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

const widget = (data) => K.open(browser, base, "widget.html", data, { width: 320, height: 520 });
const decides = (page) => page.evaluate(() => window.__decides || []);
const amends = (page) => page.evaluate(() => window.__amends || []);

/* ── §3a: multiple-choice options ────────────────────────────────────────── */

await check("CONTROL: a plain (single/no-option) plan looks exactly as before", async () => {
  const page = await widget({ pending: [K.APPROVAL_PLAIN] });
  const optionsHidden = await page.locator("#appr-options").isHidden();
  const yesVisible = await page.locator("#btn-appr-yes").isVisible();
  await page.close();
  assert.ok(optionsHidden, "the options container should stay hidden with no options");
  assert.ok(yesVisible, "the static Approve button must still be the way to approve");
});

await check("a multi-option plan hides the static Approve button and lists each option", async () => {
  const page = await widget({ pending: [K.APPROVAL_WITH_OPTIONS] });
  const yesHidden = await page.locator("#btn-appr-yes").isHidden();
  const optionButtons = await page.locator("#appr-options .appr-option").count();
  const labels = await page.locator("#appr-options .opt-label").allInnerTexts();
  await page.close();
  assert.ok(yesHidden, "the static Approve button must not double up with the option buttons");
  assert.equal(optionButtons, 2, "both options from the plan should each get a button");
  assert.deepEqual(labels, ["Wait, don't reply yet", "Reply and ask for a refund"]);
});

await check("Deny still works on a multi-option card, with no option id", async () => {
  const page = await widget({ pending: [K.APPROVAL_WITH_OPTIONS] });
  await page.locator("#btn-appr-no").click();
  await page.waitForTimeout(200);
  const sent = await decides(page);
  await page.close();
  assert.equal(sent.length, 1);
  assert.equal(sent[0].approved, false);
  assert.equal(sent[0].optionId, undefined, "denying should never carry an option id");
});

await check("clicking an option sends that option's id, approved", async () => {
  const page = await widget({ pending: [K.APPROVAL_WITH_OPTIONS] });
  await page.locator('#appr-options .appr-option[data-option-id="opt_reply"]').click();
  await page.waitForTimeout(200);
  const sent = await decides(page);
  await page.close();
  assert.equal(sent.length, 1);
  assert.equal(sent[0].approved, true);
  assert.equal(sent[0].optionId, "opt_reply");
});

await check("a new card resets the options rendered for the last one", async () => {
  // The bug this guards against: options are appended, not replaced, so a
  // second card would show the first card's choices underneath its own.
  const page = await widget({ pending: [K.APPROVAL_WITH_OPTIONS] });
  await page.evaluate((id) => window.__emit("approval-resolved", { id }), K.APPROVAL_WITH_OPTIONS.id);
  await page.waitForTimeout(150);
  await page.evaluate((items) => window.__emit("approvals-changed",
    { count: items.length, items }), [K.APPROVAL_PLAIN]);
  await page.waitForTimeout(250);
  const optionButtons = await page.locator("#appr-options .appr-option").count();
  const optionsHidden = await page.locator("#appr-options").isHidden();
  await page.close();
  assert.equal(optionButtons, 0, "the previous card's option buttons must not survive");
  assert.ok(optionsHidden);
});

/* ── §3b: a note before the first decision ───────────────────────────────── */

await check("sending a note calls amend, not decide, and does not close the card", async () => {
  const page = await widget({ pending: [K.APPROVAL_PLAIN] });
  await page.fill("#appr-note", "actually, wait until tomorrow");
  await page.press("#appr-note", "Enter");
  await page.waitForTimeout(200);
  const sentAmends = await amends(page);
  const sentDecides = await decides(page);
  const cardHidden = await page.locator("#approval-card").isHidden();
  await page.close();
  assert.equal(sentAmends.length, 1);
  assert.equal(sentAmends[0].id, K.APPROVAL_PLAIN.id);
  assert.equal(sentAmends[0].note, "actually, wait until tomorrow");
  assert.equal(sentDecides.length, 0, "a note must never itself approve or deny anything");
  assert.ok(!cardHidden, "the card stays open — a note is not a decision");
});

await check("an empty note sends nothing", async () => {
  const page = await widget({ pending: [K.APPROVAL_PLAIN] });
  await page.press("#appr-note", "Enter");
  await page.waitForTimeout(150);
  const sent = await amends(page);
  await page.close();
  assert.equal(sent.length, 0);
});

await check("the note field cannot be used once this card's decision is in flight", async () => {
  // Same lesson `busy`/`deciding` already learned once for the capture
  // field: a shared or missing flag makes one action silently swallow
  // another's input while it is running.
  const page = await widget({ pending: [K.APPROVAL_PLAIN] });
  await page.evaluate(() => {
    const real = window.__TAURI__.core.invoke;
    window.__TAURI__.core.invoke = async (cmd, args) =>
      cmd === "decide_approval" ? new Promise(() => {}) : real(cmd, args);
  });
  await page.locator("#btn-appr-yes").click();
  await page.waitForTimeout(150);
  const noteDisabled = await page.locator("#appr-note").isDisabled();
  await page.close();
  assert.ok(noteDisabled, "a note about a plan already being decided would arrive too late");
});

await check("a stale link disables the note field along with the decision buttons", async () => {
  const page = await widget({ pending: [K.APPROVAL_PLAIN], link: { stale: true } });
  const noteDisabled = await page.locator("#appr-note").isDisabled();
  const sendDisabled = await page.locator("#btn-appr-note-send").isDisabled();
  await page.close();
  assert.ok(noteDisabled && sendDisabled);
});

/* ── §3c: live progress ──────────────────────────────────────────────────── */

await check("progress text shows while Jarvis reports working", async () => {
  const page = await widget({
    pending: [], link: { activity: "working", activity_detail: "Step 2/3: click \"Send\"" },
  });
  const text = await page.locator("#widget-progress").innerText();
  const hidden = await page.locator("#widget-progress").isHidden();
  await page.close();
  assert.ok(!hidden);
  assert.equal(text, 'Step 2/3: click "Send"');
});

await check("progress is hidden when idle, even if a stale detail string is still set", async () => {
  const page = await widget({
    pending: [], link: { activity: "idle", activity_detail: "Step 2/3: click \"Send\"" },
  });
  const hidden = await page.locator("#widget-progress").isHidden();
  await page.close();
  assert.ok(hidden, "an idle Jarvis has nothing in progress to narrate");
});

await check("CONTROL: no activity_detail at all renders exactly as before", async () => {
  const page = await widget({ pending: [] });
  const hidden = await page.locator("#widget-progress").isHidden();
  const errors = page.__errors;
  await page.close();
  assert.ok(hidden);
  assert.deepEqual(errors, [], "a backend that never sends activity_detail must not error");
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\noptions, notes, and progress — all against the mock, none against a real backend");
process.exit(fails.length ? 1 : 0);
