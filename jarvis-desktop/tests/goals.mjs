/**
 * Goals on the Brain's Work tab - a plan the owner edits, one card per
 * acting step (the owner's "build it now", 2026-09-27; JARVIS-API.md
 * section 59; src/goals.js, brain.js paintGoals, src-tauri/src/brain/
 * goals.rs).
 *
 * What must hold:
 * - the section says what it is in its own words, and lists goals from
 *   GET /api/goals (brain_goals);
 * - a new goal is a draft, created from the owner's own words alone
 *   (POST /api/goals via brain_goals_create), no card, no confirm;
 * - a draft's steps can be added, edited and removed by hand before
 *   Accept sends the CURRENT plan (brain_goals_accept) - accepting is the
 *   only thing here that can raise a card, and it is the backend's own
 *   weekly check-in card, shown "Waiting for your yes on the approval
 *   card" exactly like a repeating reminder's;
 * - an active goal's steps are checkboxes; ticking one sends ONE
 *   brain_goals_step for that goal and index, asking nothing;
 * - Stop tracking is one tap, immediate, no confirm dialog
 *   (brain_goals_stop);
 * - there is no bulk control anywhere in the card;
 * - every write is held on a stale link (greyed here, refused in Rust);
 * - the words are hidden with the private lists under Windows Hello, same
 *   as Coming up;
 * - a PC without Goals says so, and the new-goal form is not offered;
 * - the empty state says so in words that tell the owner what to do next;
 * - CONTROL: every write command is held on a stale link in Rust, the read
 *   is redacted under the same private-lists gate as schedule, and the
 *   Rust/JS/permissions wiring (lib.rs, build.rs, surfaces.toml,
 *   capabilities) all agree, on this window only.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  ACCEPT_LABEL,
  checkinJobFor,
  checkinLines,
  DEFAULT_LIMITS,
  EMPTY_GOALS,
  GOALS_DETAIL,
  GOALS_MISSING,
  GOALS_TITLE,
  NEW_GOAL_LABEL,
  NEW_GOAL_PLACEHOLDER,
  openCount,
  planIsValid,
  readGoals,
  statusLabel,
  STOP_LABEL,
} from "../src/goals.js";
import { WAITING } from "../src/coming-up.js";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const DRAFT = { id: "g0000000001", text: "insulate the garage before winter",
  plan: [{ step: "insulate the garage before winter", by: "", done: false }],
  status: "draft", created: 1, changed: 1 };
const ACTIVE = { id: "g0000000002", text: "learn to bake bread",
  plan: [{ step: "buy flour", by: "this week", done: true },
         { step: "try a recipe", by: "", done: false }],
  status: "active", created: 2, changed: 2 };
const CHECKIN_JOB = { id: "s00000000dd", kind: "goal_checkin", text: ACTIVE.text,
  state: "waiting", repeats: true, repeat: "every Monday at 09:00" };
const STOPPED = { id: "g0000000003", text: "learn Spanish",
  plan: [{ step: "install Duolingo", by: "", done: true }], status: "stopped",
  created: 3, changed: 3 };

/* ── The words and the pure reading ───────────────────────────────────── */

await check("the section's words, in the page", async () => {
  assert.equal(GOALS_TITLE, "Goals");
  const html = read("src/brain.html");
  assert.match(html, /<h2>Goals<\/h2>/);
  assert.ok(html.includes(`>${GOALS_DETAIL}</p>`));
  assert.ok(html.includes(`placeholder="${NEW_GOAL_PLACEHOLDER}"`));
  assert.match(html, new RegExp(`>${NEW_GOAL_LABEL}</button>`));
});

await check("reading GET /api/goals: ids, plans, limits, and an older PC", async () => {
  const v = readGoals({ ok: true, goals: [DRAFT, ACTIVE], limits: { text: 300, steps: 7, goals: 20, by: 40 } });
  assert.equal(v.available, true);
  assert.equal(v.goals.length, 2);
  assert.equal(v.goals[1].plan[0].done, true);
  assert.deepEqual(v.limits, { text: 300, steps: 7, goals: 20, by: 40, needs: 3 });
  assert.equal(v.locks, false, "a PC that sends no needs limit has no locks");
  assert.equal(openCount(v), 2, "a stopped goal does not count as open");
  const withStopped = readGoals({ ok: true, goals: [DRAFT, ACTIVE, STOPPED] });
  assert.equal(openCount(withStopped), 2);
  for (const nothing of [null, {}, "x"]) {
    const n = readGoals(nothing);
    assert.equal(n.available, false);
    assert.equal(n.why, GOALS_MISSING);
  }
  assert.deepEqual(readGoals({ goals: [] }).goals, [], "an empty list is a real, available answer");
  const bad = readGoals({ goals: [{ id: "all" }, { id: "*" }, DRAFT] });
  assert.equal(bad.goals.length, 1, "a row without a real id was kept");
  assert.deepEqual(readGoals({ goals: [] }).limits, DEFAULT_LIMITS, "no limits sent falls back to the PC's own defaults");
});

await check("a plan is only valid with real, short-enough steps", async () => {
  assert.equal(planIsValid([{ step: "contact installers", by: "this week" }]), true);
  assert.equal(planIsValid([]), false, "empty");
  assert.equal(planIsValid([{ step: "" }]), false, "blank step");
  assert.equal(planIsValid(Array(8).fill({ step: "x" })), false, "over the step limit");
  assert.equal(planIsValid([{ step: "x".repeat(301) }]), false, "step too long");
  assert.equal(planIsValid([{ step: "x", by: "y".repeat(41) }]), false, "date label too long");
});

await check("statusLabel and the check-in lines", async () => {
  assert.equal(statusLabel("draft"), "Draft");
  assert.equal(statusLabel("active"), "Active");
  assert.equal(statusLabel("stopped"), "Stopped");
  assert.deepEqual(checkinLines(null, WAITING), []);
  assert.deepEqual(checkinLines({ repeat: "every Monday at 09:00", state: "waiting" }, WAITING),
    ["Weekly check-in: every Monday at 09:00", WAITING]);
  assert.deepEqual(checkinLines({ repeat: "every Monday at 09:00", state: "paused" }, WAITING),
    ["Weekly check-in: every Monday at 09:00", "Paused"]);
  const note = '"insulate the garage before winter": still on track for "contact 3 installers" (this week)?';
  assert.deepEqual(checkinLines({ repeat: "every Monday at 09:00", state: "active", note }, WAITING),
    ["Weekly check-in: every Monday at 09:00", note]);
  assert.equal(checkinJobFor(ACTIVE, [], "s1"), null);
  assert.equal(checkinJobFor(ACTIVE, [CHECKIN_JOB], "s00000000dd").id, "s00000000dd");
  // No known id (a reload lost it): falls back to matching the job's own
  // text, which accept() set to the goal's own words.
  assert.equal(checkinJobFor(ACTIVE, [CHECKIN_JOB], null).id, "s00000000dd");
  assert.equal(checkinJobFor(DRAFT, [CHECKIN_JOB], null), null, "a different goal's words never match");
});

const LIFE_ID = CASES.cases.life.project.id;

/* ── The Brain window ─────────────────────────────────────────────────── */

const { base, close } = await K.serve();
const browser = await K.launch();
const SIZE = { width: 1180, height: 900 };

async function workTab(data = {}) {
  const page = await K.open(browser, base, "brain.html", data, SIZE);
  await page.locator("#tab-work").click();
  await page.waitForTimeout(500);
  return page;
}

await check("the section lists goals: a draft's editor, an active goal's checkboxes", async () => {
  const page = await workTab({ goals: { goals: [DRAFT, ACTIVE] },
    schedule: { jobs: [CHECKIN_JOB], todo: [] } });
  const card = page.locator("#goals-card");
  const title = (await card.locator("h2").textContent()).trim();
  const note = await card.locator(".note").first().innerText();
  const blockCount = await page.locator("#goals-list .goal-block").count();
  await page.close();
  assert.equal(title, GOALS_TITLE);
  assert.equal(note, GOALS_DETAIL);
  assert.equal(blockCount, 2);
});

await check("a draft: editable step text, Add a step, and Accept sends the edited plan", async () => {
  const page = await workTab({ goals: { goals: [DRAFT] } });
  const block = page.locator("#goals-list .goal-block").first();
  const stepField = block.locator(".goal-editor-row input").first();
  await stepField.fill("contact 3 installers");
  await block.getByRole("button", { name: "Add a step" }).click();
  const rows = block.locator(".goal-editor-row");
  await rows.nth(1).locator("input").first().fill("pick one and book it");
  await block.getByRole("button", { name: "Accept" }).click();
  await page.waitForTimeout(400);
  const sent = await page.evaluate(() => window.__goalsCalls);
  await page.close();
  assert.equal(sent.length, 1);
  assert.equal(sent[0].cmd, "brain_goals_accept");
  assert.equal(sent[0].id, "g0000000001");
  assert.deepEqual(sent[0].plan, [
    { step: "contact 3 installers", by: "", done: false, needs: [], measure: null },
    { id: "s1", step: "pick one and book it", by: "", done: false, needs: [], measure: null },
  ]);
});

await check("Remove takes a step out of the draft before it is ever sent anywhere", async () => {
  const twoStepDraft = { ...DRAFT, plan: [{ step: "one", by: "", done: false },
    { step: "two", by: "", done: false }] };
  const page = await workTab({ goals: { goals: [twoStepDraft] } });
  const block = page.locator("#goals-list .goal-block").first();
  await block.getByRole("button", { name: "Remove" }).first().click();
  const left = await block.locator(".goal-editor-row").count();
  await block.getByRole("button", { name: "Accept" }).click();
  await page.waitForTimeout(400);
  const sent = await page.evaluate(() => window.__goalsCalls);
  await page.close();
  assert.equal(left, 1);
  assert.deepEqual(sent[0].plan, [{ step: "two", by: "", done: false, needs: [], measure: null }]);
});

await check("accepting shows \"waiting for your yes\", the same words a reminder card uses", async () => {
  const page = await workTab({ goals: { goals: [DRAFT] } });
  const block = page.locator("#goals-list .goal-block").first();
  await block.getByRole("button", { name: "Accept" }).click();
  await page.waitForTimeout(500);
  const text = await page.locator("#goals-list").innerText();
  const stopButtons = await page.locator("#goals-list").getByRole("button", { name: "Stop tracking" }).count();
  await page.close();
  assert.match(text, new RegExp(WAITING.replace(/[.]/g, "\\.")));
  assert.match(text, /every Monday at 09:00/);
  assert.equal(stopButtons, 1, "an active goal offers Stop tracking");
});

await check("an active goal's steps are checkboxes; ticking one sends ONE change, asking nothing", async () => {
  const page = await workTab({ goals: { goals: [ACTIVE] }, schedule: { jobs: [CHECKIN_JOB], todo: [] } });
  let asked = false;
  page.on("dialog", (d) => { asked = true; d.dismiss(); });
  const block = page.locator("#goals-list .goal-block").first();
  const boxes = block.locator('input[type="checkbox"]');
  assert.equal(await boxes.nth(0).isChecked(), true, "buy flour is already done");
  assert.equal(await boxes.nth(1).isChecked(), false);
  await boxes.nth(1).check();
  await page.waitForTimeout(500);
  const sent = await page.evaluate(() => window.__goalsCalls);
  await page.close();
  assert.equal(asked, false, "ticking a step asked a question");
  assert.deepEqual(sent, [{ cmd: "brain_goals_step", id: "g0000000002", index: 1, done: true }]);
});

await check("Stop tracking is one tap, no confirm dialog, and immediate", async () => {
  const page = await workTab({ goals: { goals: [ACTIVE] }, schedule: { jobs: [CHECKIN_JOB], todo: [] } });
  let asked = false;
  page.on("dialog", (d) => { asked = true; d.dismiss(); });
  await page.locator("#goals-list").getByRole("button", { name: "Stop tracking" }).click();
  await page.waitForTimeout(500);
  const sent = await page.evaluate(() => window.__goalsCalls);
  const stopButtons = await page.locator("#goals-list").getByRole("button", { name: "Stop tracking" }).count();
  const text = await page.locator("#goals-list").innerText();
  await page.close();
  assert.equal(asked, false, "Stop tracking asked a question - it must be immediate, no confirm");
  assert.deepEqual(sent, [{ cmd: "brain_goals_stop", id: "g0000000002" }]);
  assert.equal(stopButtons, 0, "a stopped goal still offered Stop tracking");
  assert.match(text, /stopped/i);
});

await check("a new goal: typing the words alone is enough", async () => {
  const page = await workTab({ goals: { goals: [] } });
  await page.locator("#goals-new-text").fill("insulate the garage before winter");
  await page.locator("#goals-new-add").click();
  await page.waitForTimeout(500);
  const sent = await page.evaluate(() => window.__goalsCalls);
  const text = await page.locator("#goals-list").innerText();
  const cleared = await page.locator("#goals-new-text").inputValue();
  await page.close();
  assert.deepEqual(sent, [{ cmd: "brain_goals_create", text: "insulate the garage before winter" }]);
  assert.match(text, /insulate the garage before winter/);
  assert.equal(cleared, "");
});

await check("no bulk control anywhere in the card", async () => {
  const page = await workTab({ goals: { goals: [DRAFT, ACTIVE, STOPPED] },
    schedule: { jobs: [CHECKIN_JOB], todo: [] } });
  const buttons = await page.locator("#goals-card button").allInnerTexts();
  await page.close();
  for (const b of buttons) {
    assert.doesNotMatch(b, /\ball\b|clear|everything/i, `a bulk control: ${b}`);
  }
});

await check("the empty state says what to do next", async () => {
  const page = await workTab({ goals: { goals: [] } });
  const text = await page.locator("#goals-list").innerText();
  await page.close();
  assert.equal(text.trim(), EMPTY_GOALS);
});

await check("a PC without Goals: the section says so, and offers no new-goal form", async () => {
  const page = await workTab({});
  const text = await page.locator("#goals-list").innerText();
  const formHidden = await page.locator("#goals-new-form").isHidden();
  await page.close();
  assert.equal(text.trim(), GOALS_MISSING);
  assert.equal(formHidden, true);
});

await check("held on a stale link: Add, Accept, a step's checkbox and Stop tracking are all greyed", async () => {
  const page = await workTab({ goals: { goals: [DRAFT, ACTIVE] },
    schedule: { jobs: [CHECKIN_JOB], todo: [] }, link: { stale: true } });
  const addDisabled = await page.locator("#goals-new-add").isDisabled();
  const acceptDisabled = await page.locator("#goals-list").getByRole("button", { name: "Accept" }).isDisabled();
  const boxDisabled = await page.locator('#goals-list input[type="checkbox"]').first().isDisabled();
  const stopDisabled = await page.locator("#goals-list").getByRole("button", { name: "Stop tracking" }).isDisabled();
  await page.close();
  assert.equal(addDisabled, true);
  assert.equal(acceptDisabled, true);
  assert.equal(boxDisabled, true);
  assert.equal(stopDisabled, true);
});

await check("the words are hidden with the private lists; status and steps stay visible", async () => {
  const page = await workTab({ goals: { goals: [ACTIVE] },
    schedule: { jobs: [CHECKIN_JOB], todo: [] }, security: { hidden: true } });
  const text = await page.locator("#goals-card").innerText();
  await page.close();
  assert.doesNotMatch(text, /learn to bake bread|buy flour|try a recipe/);
  assert.match(text, /Hidden until Windows Hello confirms it is you\./);
});

await check("a draft opened while the lists are hidden gets its real steps back after Show", async () => {
  // Bug audit 2026-09-29: the blank steps the PC sends while hidden were kept
  // as the editor's working copy, so they stayed blank after Show and Accept
  // refused an empty plan.
  const page = await workTab({ goals: { goals: [DRAFT] }, security: { hidden: true } });
  const hiddenValue = await page.locator("#goals-list .goal-editor-row input").first().inputValue();
  await page.evaluate(() => { window.__security.revealed = true; });
  await page.evaluate(() => window.__emit("security-changed", {}));
  await page.waitForTimeout(600);
  const shownValue = await page.locator("#goals-list .goal-editor-row input").first().inputValue();
  await page.close();
  assert.equal(hiddenValue, "", "the words were not hidden to begin with (the test is not testing anything)");
  assert.equal(shownValue, DRAFT.plan[0].step);
});

await check("full: the new-goal form is not offered, and it says why", async () => {
  const many = Array.from({ length: 20 }, (_, i) => ({ ...DRAFT, id: `g${String(i).padStart(10, "0")}`,
    text: `goal ${i}` }));
  const page = await workTab({ goals: { goals: many } });
  const formHidden = await page.locator("#goals-new-form").isHidden();
  const text = await page.locator("#goals-list").innerText();
  await page.close();
  assert.equal(formHidden, true);
  assert.match(text, /20 goals are already open/);
});

await check("a `schedule` event carrying a goal_checkin reads Coming up again, which Goals shares", async () => {
  const page = await workTab({ goals: { goals: [ACTIVE] },
    schedule: { jobs: [{ ...CHECKIN_JOB, state: "waiting" }], todo: [] } });
  const before = await page.locator("#goals-list").innerText();
  await page.evaluate(() => {
    const jobs = window.__schedule.jobs;
    jobs[0].state = "active";
    delete jobs[0].note;
  });
  await page.evaluate(() => window.__emit("jarvis-event",
    { kind: "schedule", id: 9, data: { id: "s00000000dd", kind: "goal_checkin", state: "changed" } }));
  await page.waitForTimeout(400);
  const after = await page.locator("#goals-list").innerText();
  await page.close();
  assert.match(before, new RegExp(WAITING.replace(/[.]/g, "\\.")));
  assert.doesNotMatch(after, new RegExp(WAITING.replace(/[.]/g, "\\.")));
});

await check("CONTROL: every write is held on a stale link, the read is redacted, and the wiring agrees", async () => {
  const rs = read("src-tauri/src/brain/goals.rs");
  for (const cmd of ["brain_goals_create", "brain_goals_accept", "brain_goals_step", "brain_goals_stop"]) {
    const f = rs.slice(rs.indexOf(`pub async fn ${cmd}(`));
    const body = f.slice(0, f.indexOf("\n}\n"));
    assert.ok(body.indexOf("require_link_live") >= 0
      && body.indexOf("require_link_live") < body.indexOf("post("),
      `${cmd} is not held on a stale link`);
  }
  const list = rs.slice(rs.indexOf("pub async fn brain_goals("));
  assert.match(list.slice(0, list.indexOf("\n}\n")), /private_hidden/);
  for (const cmd of ["brain_goals", "brain_goals_create", "brain_goals_accept", "brain_goals_step",
    "brain_goals_stop"]) {
    assert.match(read("src-tauri/build.rs"), new RegExp(`"${cmd}"`));
    assert.match(read("src-tauri/src/lib.rs"), new RegExp(`brain::goals::${cmd},`));
    const sets = read("src-tauri/permissions/surfaces.toml").split("[[set]]").slice(1);
    const holders = sets.filter((s) => s.includes(`"allow-${cmd.replace(/_/g, "-")}"`))
      .map((s) => s.match(/identifier = "([^"]+)"/)[1]);
    assert.deepEqual(holders, ["brain-goals"], cmd);
  }
  const caps = JSON.parse(read("src-tauri/capabilities/brain.json")).permissions;
  assert.ok(caps.includes("brain-goals"));
  for (const other of ["quickbar", "widget", "hud", "settings", "faces", "floating", "onboarding"]) {
    const c = read(`src-tauri/capabilities/${other}.json`);
    assert.ok(!c.includes("brain-goals"), `${other} holds brain-goals`);
  }
  // Accepting is the only route that can ever raise a card - Rust never
  // decides that itself, it only forwards to the backend's own accept route.
  const accept = rs.slice(rs.indexOf("pub async fn brain_goals_accept("));
  assert.match(accept.slice(0, accept.indexOf("\n}\n")), /\/api\/goals\/\{id\}\/accept/);
  const stop = rs.slice(rs.indexOf("pub async fn brain_goals_stop("));
  assert.match(stop.slice(0, stop.indexOf("\n}\n")), /\/api\/goals\/\{id\}\/stop/);
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}`
  : "\nGoals: no card except the backend's own weekly check-in, one tap for Stop tracking, hidden with the private lists");
process.exit(fails.length ? 1 : 0);
