/**
 * docs/AUTONOMY-PROPOSALS.md §3d: pause, resume, stop, and a note for
 * whatever task is running right now. DRAFT routes, same footing as
 * §3a-§3c before them — no real backend exists for `pause_task`,
 * `resume_task`, `stop_task`, or `inject_task_note` (jarvis_gate.py and
 * jarvis_hud.py are not in this repo), so this proves the wire shape and
 * the honesty rule: clicking Pause must never itself make the button say
 * Resume. Only a real `activity: "paused"` reported back through the same
 * event stream approvals already use is allowed to do that - a click only
 * proves a request was sent, not that anything happened.
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
const taskActions = (page) => page.evaluate(() => window.__taskActions || []);
const taskNotes = (page) => page.evaluate(() => window.__taskNotes || []);
const reportActivity = (page, activity, detail = "") => page.evaluate(
  ({ activity, detail }) => window.__emit("jarvis-link", {
    connected: true, stale: false, activity, activity_detail: detail,
  }),
  { activity, detail }
);
const WORKING = { activity: "working", activity_detail: "Step 1/2: reading the inbox" };
const IDLE = { activity: "idle", activity_detail: "" };

await check("controls are hidden while idle", async () => {
  const page = await widget({ pending: [], link: IDLE });
  const hidden = await page.locator("#task-controls").isHidden();
  await page.close();
  assert.ok(hidden, "nothing is running, so there is nothing to pause, stop, or note");
});

await check("controls appear while a task is working, Pause shown and Resume hidden", async () => {
  const page = await widget({ pending: [], link: WORKING });
  const controlsHidden = await page.locator("#task-controls").isHidden();
  const pauseHidden = await page.locator("#btn-task-pause").isHidden();
  const resumeHidden = await page.locator("#btn-task-resume").isHidden();
  await page.close();
  assert.ok(!controlsHidden);
  assert.ok(!pauseHidden, "Pause is the first thing offered on a fresh working task");
  assert.ok(resumeHidden);
});

await check("clicking Pause sends pause_task but does NOT swap to Resume by itself", async () => {
  const page = await widget({ pending: [], link: WORKING });
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
  const page = await widget({ pending: [], link: WORKING });
  await page.locator("#btn-task-pause").click();
  await page.waitForTimeout(200);
  await reportActivity(page, "paused", "Step 1/2: reading the inbox");
  await page.waitForTimeout(200);
  const pauseHidden = await page.locator("#btn-task-pause").isHidden();
  const resumeHidden = await page.locator("#btn-task-resume").isHidden();
  const controlsHidden = await page.locator("#task-controls").isHidden();
  await page.close();
  assert.ok(pauseHidden && !resumeHidden, "the server's own report is what flips the button, nothing else");
  assert.ok(!controlsHidden, "a paused task is still live - §3d keeps its card open, not closed out");
});

await check("Resume sends resume_task; Pause returns once the server reports \"working\" again", async () => {
  const page = await widget({ pending: [], link: WORKING });
  await reportActivity(page, "paused");
  await page.waitForTimeout(150);
  await page.locator("#btn-task-resume").click();
  await page.waitForTimeout(200);
  const sentBeforeConfirm = await taskActions(page);
  const resumeHiddenBeforeConfirm = await page.locator("#btn-task-resume").isHidden();
  await reportActivity(page, "working");
  await page.waitForTimeout(150);
  const pauseHiddenAfterConfirm = await page.locator("#btn-task-pause").isHidden();
  await page.close();
  assert.deepEqual(sentBeforeConfirm, ["resume_task"]);
  assert.ok(!resumeHiddenBeforeConfirm, "clicking Resume must not itself swap back to Pause");
  assert.ok(!pauseHiddenAfterConfirm, "only the server's \"working\" report brings Pause back");
});

await check("Stop sends stop_task", async () => {
  const page = await widget({ pending: [], link: WORKING });
  await page.locator("#btn-task-stop").click();
  await page.waitForTimeout(200);
  const sent = await taskActions(page);
  await page.close();
  assert.deepEqual(sent, ["stop_task"]);
});

await check("a note is sent via inject_task_note without approving or denying anything", async () => {
  const page = await widget({ pending: [], link: WORKING });
  await page.fill("#task-note", "skip the spam folder");
  await page.locator("#btn-task-note-send").click();
  await page.waitForTimeout(200);
  const notes = await taskNotes(page);
  const decides = await page.evaluate(() => window.__decides || []);
  const cleared = await page.locator("#task-note").inputValue();
  await page.close();
  assert.deepEqual(notes, ["skip the spam folder"]);
  assert.deepEqual(decides, [], "a task note must never look like an approval decision");
  assert.equal(cleared, "");
});

await check("a failed pause surfaces its real error and does not swap to Resume", async () => {
  const page = await widget({ pending: [], link: WORKING, taskActionFails: "command not found" });
  await page.locator("#btn-task-pause").click();
  await page.waitForTimeout(200);
  const flash = await page.locator("#widget-flash").innerText();
  const pauseHidden = await page.locator("#btn-task-pause").isHidden();
  await page.close();
  assert.match(flash, /command not found/);
  assert.ok(!pauseHidden, "a rejected request must not claim the task actually paused");
});

await check("a failed note surfaces its real error and leaves the text box alone", async () => {
  const page = await widget({ pending: [], link: WORKING, taskNoteFails: "command not found" });
  await page.fill("#task-note", "still here");
  await page.locator("#btn-task-note-send").click();
  await page.waitForTimeout(200);
  const flash = await page.locator("#widget-flash").innerText();
  const value = await page.locator("#task-note").inputValue();
  await page.close();
  assert.match(flash, /command not found/);
  assert.equal(value, "still here", "a failed send must not silently clear what was typed");
});

await check("controls disappear once the server reports idle, and a stale Resume does not carry over", async () => {
  const page = await widget({ pending: [], link: WORKING });
  await reportActivity(page, "paused");
  await page.waitForTimeout(150);
  const resumeHiddenWhilePaused = await page.locator("#btn-task-resume").isHidden();

  await reportActivity(page, "idle");
  await page.waitForTimeout(150);
  const controlsHiddenNowIdle = await page.locator("#task-controls").isHidden();

  await reportActivity(page, "working", "a second, unrelated task");
  await page.waitForTimeout(150);
  const pauseHiddenOnFreshTask = await page.locator("#btn-task-pause").isHidden();
  const resumeHiddenOnFreshTask = await page.locator("#btn-task-resume").isHidden();
  await page.close();

  assert.ok(!resumeHiddenWhilePaused, "Resume should be showing right before the task ends");
  assert.ok(controlsHiddenNowIdle, "nothing is running, so the controls go away with it");
  assert.ok(!pauseHiddenOnFreshTask && resumeHiddenOnFreshTask,
    "a new task must offer Pause first, not a stale Resume left over from the last one");
});

await check("CONTROL: no page error from any of the above", async () => {
  const page = await widget({ pending: [], link: WORKING });
  await page.locator("#btn-task-pause").click();
  await reportActivity(page, "paused");
  await page.waitForTimeout(100);
  await page.locator("#btn-task-resume").click();
  await reportActivity(page, "working");
  await page.waitForTimeout(100);
  await page.locator("#btn-task-stop").click();
  await page.fill("#task-note", "note");
  await page.locator("#btn-task-note-send").click();
  await page.waitForTimeout(300);
  const errors = page.__errors;
  await page.close();
  assert.deepEqual(errors, [], JSON.stringify(errors));
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\npause, resume, stop, and a note — the button only ever believes the server, never its own click");
process.exit(fails.length ? 1 : 0);
