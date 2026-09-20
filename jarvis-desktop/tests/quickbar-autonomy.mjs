/**
 * docs/AUTONOMY-PROPOSALS.md, mirrored onto the quickbar: the widget got
 * options (§3a), a note before deciding (§3b), live progress (§3c), and
 * pause/stop/inject on a running task (§3d) first (tests/autonomy.mjs,
 * tests/task-controls.mjs); this brings the same four to index.html/main.js.
 * Built and proven against the same mock bridge those already use — no real
 * backend exists for any of this yet (jarvis_gate.py and jarvis_hud.py are
 * not in this repo).
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

const quickbar = (data) => K.open(browser, base, "index.html", data);
const decides = (page) => page.evaluate(() => window.__decides || []);
const amends = (page) => page.evaluate(() => window.__amends || []);
const taskActions = (page) => page.evaluate(() => window.__taskActions || []);
const taskNotes = (page) => page.evaluate(() => window.__taskNotes || []);
const reportActivity = (page, activity, detail = "") => page.evaluate(
  ({ activity, detail }) => window.__emit("jarvis-link", {
    connected: true, stale: false, activity, activity_detail: detail,
  }),
  { activity, detail }
);
const WORKING = { activity: "working", activity_detail: "Step 1/2: reading the inbox" };

/* ── §3a: multiple-choice options ────────────────────────────────────────── */

await check("CONTROL: a plain (single/no-option) plan looks exactly as before", async () => {
  const page = await quickbar({ pending: [K.APPROVAL_PLAIN] });
  const optionsHidden = await page.locator("#approval-options").isHidden();
  const yesVisible = await page.locator("#approval-approve").isVisible();
  await page.close();
  assert.ok(optionsHidden, "the options container should stay hidden with no options");
  assert.ok(yesVisible, "the static Approve button must still be the way to approve");
});

await check("a multi-option plan hides the static Approve button and lists each option", async () => {
  const page = await quickbar({ pending: [K.APPROVAL_WITH_OPTIONS] });
  const yesHidden = await page.locator("#approval-approve").isHidden();
  const optionButtons = await page.locator("#approval-options .approval-option").count();
  const labels = await page.locator("#approval-options .opt-label").allInnerTexts();
  await page.close();
  assert.ok(yesHidden, "the static Approve button must not double up with the option buttons");
  assert.equal(optionButtons, 2, "both options from the plan should each get a button");
  assert.deepEqual(labels, ["Wait, don't reply yet", "Reply and ask for a refund"]);
});

await check("Deny still works on a multi-option card, with no option id", async () => {
  const page = await quickbar({ pending: [K.APPROVAL_WITH_OPTIONS] });
  await page.locator("#approval-deny").click();
  await page.waitForTimeout(200);
  const sent = await decides(page);
  await page.close();
  assert.equal(sent.length, 1);
  assert.equal(sent[0].approved, false);
  assert.equal(sent[0].optionId, undefined, "denying should never carry an option id");
});

await check("option buttons are disabled - option_id never reaches decide_approval (docs/JARVIS-API.md §8)", async () => {
  // Was "clicking an option sends that option's id, approved" - that only
  // proved the JS-side plumbing worked, which was never the bug. Rust's
  // `decide_approval` takes `(app, id, approved)`; Tauri drops `option_id`
  // before any request is built, so the option a person clicked was never
  // the option approved. See widget.js's copy of this test for the fuller
  // story - same fix, same reason, mirrored here for the quickbar window.
  const page = await quickbar({ pending: [K.APPROVAL_WITH_OPTIONS] });
  const optionButtons = page.locator("#approval-options .approval-option");
  const disabledFlags = await optionButtons.evaluateAll((els) => els.map((el) => el.disabled));
  await page.close();
  assert.deepEqual(disabledFlags, [true, true], "no option can be approved until a decide-with-option route exists");
});

/* ── §3b: a note before the first decision ───────────────────────────────── */

await check("sending a note calls amend_approval, not decide_approval", async () => {
  const page = await quickbar({ pending: [K.APPROVAL_PLAIN] });
  await page.fill("#approval-note", "wait, check the price first");
  await page.locator("#approval-note-send").click();
  await page.waitForTimeout(200);
  const noted = await amends(page);
  const decided = await decides(page);
  await page.close();
  assert.equal(noted.length, 1);
  assert.equal(noted[0].note, "wait, check the price first");
  assert.deepEqual(decided, [], "a note must never look like a decision");
});

await check("a failed note leaves the gate answerable and does not clear the field", async () => {
  const page = await quickbar({ pending: [K.APPROVAL_PLAIN], amendFails: "backend has no amend route" });
  await page.fill("#approval-note", "still here");
  await page.locator("#approval-note-send").click();
  await page.waitForTimeout(200);
  const value = await page.locator("#approval-note").inputValue();
  const approveDisabled = await page.locator("#approval-approve").isDisabled();
  await page.close();
  assert.equal(value, "still here");
  assert.ok(!approveDisabled, "a failed note must not disable the gate it belongs to");
});

/* ── §3c: live progress ──────────────────────────────────────────────────── */

await check("progress text shows while Jarvis reports working", async () => {
  const page = await quickbar({ pending: [], link: WORKING });
  const text = await page.locator("#progress-line").innerText();
  const hidden = await page.locator("#progress-line").isHidden();
  await page.close();
  assert.ok(!hidden);
  assert.equal(text, "Step 1/2: reading the inbox");
});

await check("progress is hidden when idle, even if a stale detail string is still set", async () => {
  const page = await quickbar({
    pending: [], link: { activity: "idle", activity_detail: "Step 1/2: reading the inbox" },
  });
  const hidden = await page.locator("#progress-line").isHidden();
  await page.close();
  assert.ok(hidden, "an idle Jarvis has nothing in progress to narrate");
});

await check("CONTROL: no activity_detail at all renders exactly as before", async () => {
  const page = await quickbar({ pending: [] });
  const hidden = await page.locator("#progress-line").isHidden();
  const errors = page.__errors;
  await page.close();
  assert.ok(hidden);
  assert.deepEqual(errors, [], "a backend that never sends activity_detail must not error");
});

/* ── §3d: pause, stop, and inject-while-running ──────────────────────────── */

await check("task controls are hidden while idle", async () => {
  const page = await quickbar({ pending: [], link: { activity: "idle", activity_detail: "" } });
  const hidden = await page.locator("#task-controls").isHidden();
  await page.close();
  assert.ok(hidden);
});

await check("task controls appear while working, Pause shown and Resume hidden", async () => {
  const page = await quickbar({ pending: [], link: WORKING });
  const controlsHidden = await page.locator("#task-controls").isHidden();
  const pauseHidden = await page.locator("#btn-task-pause").isHidden();
  const resumeHidden = await page.locator("#btn-task-resume").isHidden();
  await page.close();
  assert.ok(!controlsHidden);
  assert.ok(!pauseHidden);
  assert.ok(resumeHidden);
});

await check("clicking Pause sends pause_task but does NOT swap to Resume by itself", async () => {
  const page = await quickbar({ pending: [], link: WORKING });
  await page.locator("#btn-task-pause").click();
  await page.waitForTimeout(200);
  const sent = await taskActions(page);
  const pauseHidden = await page.locator("#btn-task-pause").isHidden();
  const resumeHidden = await page.locator("#btn-task-resume").isHidden();
  await page.close();
  assert.deepEqual(sent, ["pause_task"]);
  assert.ok(!pauseHidden && resumeHidden,
    "a click only proves a request was sent - the button must not claim the task paused on its own say-so");
});

await check("Resume appears only once the server itself reports activity: \"paused\"", async () => {
  const page = await quickbar({ pending: [], link: WORKING });
  await page.locator("#btn-task-pause").click();
  await page.waitForTimeout(200);
  await reportActivity(page, "paused", "Step 1/2: reading the inbox");
  await page.waitForTimeout(200);
  const pauseHidden = await page.locator("#btn-task-pause").isHidden();
  const resumeHidden = await page.locator("#btn-task-resume").isHidden();
  const controlsHidden = await page.locator("#task-controls").isHidden();
  await page.close();
  assert.ok(pauseHidden && !resumeHidden);
  assert.ok(!controlsHidden, "a paused task is still live - §3d keeps its card open, not closed out");
});

await check("Stop sends stop_task", async () => {
  const page = await quickbar({ pending: [], link: WORKING });
  await page.locator("#btn-task-stop").click();
  await page.waitForTimeout(200);
  const sent = await taskActions(page);
  await page.close();
  assert.deepEqual(sent, ["stop_task"]);
});

await check("a task note is sent via inject_task_note without approving or denying anything", async () => {
  const page = await quickbar({ pending: [], link: WORKING });
  await page.fill("#task-note", "skip the spam folder");
  await page.locator("#btn-task-note-send").click();
  await page.waitForTimeout(200);
  const notes = await taskNotes(page);
  const decided = await decides(page);
  const cleared = await page.locator("#task-note").inputValue();
  await page.close();
  assert.deepEqual(notes, ["skip the spam folder"]);
  assert.deepEqual(decided, []);
  assert.equal(cleared, "");
});

await check("a failed pause surfaces its real error in the answer feed", async () => {
  const page = await quickbar({ pending: [], link: WORKING, taskActionFails: "command not found" });
  await page.locator("#btn-task-pause").click();
  await page.waitForTimeout(200);
  const feed = await page.locator("#answer").innerText();
  const pauseHidden = await page.locator("#btn-task-pause").isHidden();
  await page.close();
  assert.match(feed, /command not found/);
  assert.ok(!pauseHidden, "a rejected request must not claim the task actually paused");
});

await check("CONTROL: no page error from any of the above", async () => {
  const page = await quickbar({ pending: [K.APPROVAL_WITH_OPTIONS], link: WORKING });
  await page.locator("#btn-task-pause").click();
  await reportActivity(page, "paused");
  await page.waitForTimeout(100);
  await page.locator("#btn-task-resume").click();
  await reportActivity(page, "working");
  await page.waitForTimeout(100);
  await page.locator("#btn-task-stop").click();
  await page.fill("#task-note", "note");
  await page.locator("#btn-task-note-send").click();
  await page.fill("#approval-note", "note");
  await page.locator("#approval-note-send").click();
  await page.waitForTimeout(300);
  const errors = page.__errors;
  await page.close();
  assert.deepEqual(errors, [], JSON.stringify(errors));
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nthe quickbar now carries options, notes, progress, and pause/stop/inject too");
process.exit(fails.length ? 1 : 0);
