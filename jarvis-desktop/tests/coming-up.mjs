/**
 * "Coming up" on the Brain's Work tab, the toast when a job goes off, and
 * the "Done" line under an answer made without the model (the owner's
 * decisions of 2026-09-25; JARVIS-API.md section 21; src/coming-up.js,
 * brain.js paintComingUp, src-tauri/src/brain/schedule.rs, stream.rs).
 *
 * What must hold:
 * - the section says what it is in the words both apps use;
 * - timers count down, alarms and reminders say when, a repeating one says
 *   how often and its next time, a waiting one says it waits for the card;
 * - each row has its own Pause / Resume / Delete (to-do: Done / Delete),
 *   and a tap sends ONE brain_schedule_act for that one id, asking nothing;
 * - there is no "delete all", "clear" or "done all" anywhere;
 * - held on a stale link (greyed here, refused in Rust);
 * - the words hidden with the private lists under Windows Hello;
 * - a PC without the scheduler says so;
 * - a `schedule` event reads the list again;
 * - an answer whose route says `quick` shows the "Done" line;
 * - CONTROL: the Rust toasts on `fired`, reads the words by id, and shows
 *   only the kind's lock-screen words while App lock or hiding is on; the
 *   phone says the same words.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  actionsOf,
  COMING_UP_DETAIL,
  COMING_UP_TITLE,
  countdown,
  DONE_LINE,
  EMPTY_JOBS,
  EMPTY_TODO,
  LOCK_SCREEN,
  lengthWords,
  metaOf,
  readSchedule,
  SCHEDULE_MISSING,
  titleOf,
  TOAST_TITLES,
  TODO_TITLE,
  WAITING,
} from "../src/coming-up.js";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const readRepo = (p) => readFileSync(join(HERE, "..", "..", p), "utf8");

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const NOW = Math.floor(Date.now() / 1000);
const JOBS = [
  { id: "s0000000001", kind: "timer", text: "pasta", state: "active", due: NOW + 600,
    left: 600, duration: 600, repeats: false },
  { id: "s0000000002", kind: "alarm", text: "", state: "active", due: NOW + 3600,
    left: 3600, when: "07:00 tomorrow", repeats: false },
  { id: "s0000000003", kind: "reminder", text: "take my pills", state: "active",
    due: NOW + 7200, when: "07:00 on Monday", repeats: true,
    repeat: "every weekday (Monday to Friday) at 07:00", next: [NOW + 7200] },
  { id: "s0000000004", kind: "reminder", text: "stretch", state: "waiting", repeats: true,
    repeat: "every 2 hours", next: [NOW + 7200] },
];
const TODO = [{ id: "s0000000005", kind: "todo", text: "buy milk", state: "active", repeats: false }];

/* ── The words ─────────────────────────────────────────────────────────── */

await check("the section's words are both apps' words, word for word", async () => {
  assert.equal(COMING_UP_TITLE, "Coming up");
  assert.equal(TODO_TITLE, "To-do list");
  const html = read("src/brain.html");
  assert.match(html, /<h2>Coming up<\/h2>/);
  assert.ok(html.includes(`>${COMING_UP_DETAIL}</p>`));
  assert.match(html, />To-do list<\/h3>/);
  const kt = readRepo("jarvis-client/app/src/main/java/com/jarvis/client/net/Schedule.kt")
    .replace(/"\s*\+\s*\n?\s*"/g, "");
  for (const words of [COMING_UP_TITLE, COMING_UP_DETAIL, TODO_TITLE, EMPTY_JOBS, EMPTY_TODO,
    WAITING, SCHEDULE_MISSING, DONE_LINE, ...Object.values(TOAST_TITLES),
    ...Object.values(LOCK_SCREEN)]) {
    assert.ok(kt.includes(`"${words.replace(/"/g, '\\"')}"`), `the phone does not say: ${words}`);
  }
  // The PC's own words for a locked screen (jarvis_schedule.KINDS) are these.
  const py = readRepo("backend/jarvis_schedule.py");
  for (const [kind, words] of Object.entries(LOCK_SCREEN)) {
    assert.ok(py.includes(`register_kind("${kind}"`) && py.includes(`"${words}"`), kind);
  }
  // And the Rust toast's.
  const rs = read("src-tauri/src/brain/schedule.rs");
  for (const [kind, title] of Object.entries(TOAST_TITLES)) {
    assert.ok(rs.includes(`"${kind}" => "${title}"`), `toast title ${kind}`);
  }
  assert.ok(readRepo("backend/jarvis_quick.py").includes(`DONE_LINE = "${DONE_LINE}"`));
});

await check("countdowns, lengths and each row's lines", async () => {
  assert.equal(countdown(598), "9:58");
  assert.equal(countdown(3723), "1:02:03");
  assert.equal(countdown(-5), "0:00");
  assert.equal(lengthWords(5400), "1 hour 30 minutes");
  assert.equal(lengthWords(45), "45 seconds");
  const v = readSchedule({ jobs: JOBS, todo: TODO });
  assert.equal(titleOf(v.jobs[0]), "pasta timer");
  assert.deepEqual(metaOf(v.jobs[0], 2000), ["9:58 left"]);
  assert.equal(titleOf(v.jobs[1]), "Alarm");
  assert.deepEqual(metaOf(v.jobs[1]), ["07:00 tomorrow"]);
  assert.deepEqual(metaOf(v.jobs[2]), ["every weekday (Monday to Friday) at 07:00",
    "next: 07:00 on Monday"]);
  assert.deepEqual(metaOf(v.jobs[3]), ["every 2 hours", WAITING]);
  assert.deepEqual(actionsOf(v.jobs[0]), ["pause", "delete"]);
  assert.deepEqual(actionsOf(v.jobs[3]), ["delete"]);
  assert.deepEqual(actionsOf(v.todo[0]), ["done", "delete"]);
  const missed = readSchedule({ jobs: [{ ...JOBS[2], missed: "missed at 07:00" }], todo: [] });
  assert.ok(metaOf(missed.jobs[0]).includes("Went off late (missed at 07:00) - the PC was off or asleep."));
  for (const nothing of [null, {}, { jobs: [] }, "x"]) {
    const n = readSchedule(nothing);
    assert.equal(n.available, false);
    assert.equal(n.why, SCHEDULE_MISSING);
  }
  const bad = readSchedule({ jobs: [{ id: "all", kind: "timer" }, { id: "*" }], todo: [] });
  assert.equal(bad.jobs.length, 0, "a row without a real id was kept");
});

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

await check("the section: title, its line, every job with its own buttons, and the to-do list", async () => {
  const page = await workTab({ schedule: { jobs: JOBS, todo: TODO } });
  const card = page.locator("#coming-up-card");
  const title = (await card.locator("h2").textContent()).trim();
  const note = await card.locator(".note").first().innerText();
  const rows = await page.locator("#coming-up .row-item").allInnerTexts();
  const buttons = [];
  const items = page.locator("#coming-up .row-item");
  for (let i = 0; i < await items.count(); i++) buttons.push(await items.nth(i).locator("button").allInnerTexts());
  const todo = await page.locator("#todo-list .row-item").allInnerTexts();
  const todoButtons = await page.locator("#todo-list .row-item button").allInnerTexts();
  const everyButton = await page.locator("#coming-up-card button").allInnerTexts();
  await page.close();
  assert.equal(title, COMING_UP_TITLE);
  assert.equal(note, COMING_UP_DETAIL);
  assert.equal(rows.length, 4);
  assert.match(rows[0], /pasta timer/);
  assert.match(rows[0], /\d+:\d\d left/);
  assert.match(rows[1], /07:00 tomorrow/);
  assert.match(rows[2], /every weekday/);
  assert.match(rows[3], new RegExp(WAITING.replace(/[.]/g, "\\.")));
  assert.deepEqual(buttons, [["Pause", "Delete"], ["Pause", "Delete"], ["Pause", "Delete"], ["Delete"]]);
  assert.equal(todo.length, 1);
  assert.match(todo[0], /buy milk/);
  assert.deepEqual(todoButtons, ["Done", "Delete"]);
  for (const b of everyButton) {
    assert.doesNotMatch(b, /\ball\b|clear|everything/i, `a bulk control: ${b}`);
  }
});

await check("a timer counts down on its own, once a second", async () => {
  const page = await workTab({ schedule: { jobs: [JOBS[0]], todo: [] } });
  const first = await page.locator("#coming-up .row-item .countdown").innerText();
  await page.waitForTimeout(2200);
  const later = await page.locator("#coming-up .row-item .countdown").innerText();
  await page.close();
  assert.notEqual(first, later, `${first} did not move`);
});

await check("a tap sends ONE change for that id, asks nothing, and the list reads again", async () => {
  const page = await workTab({ schedule: { jobs: JOBS, todo: TODO } });
  let asked = false;
  page.on("dialog", (d) => { asked = true; d.dismiss(); });
  await page.locator("#coming-up .row-item").nth(1).getByRole("button", { name: "Delete" }).click();
  await page.waitForTimeout(500);
  await page.locator("#todo-list .row-item").first().getByRole("button", { name: "Done" }).click();
  await page.waitForTimeout(500);
  await page.locator("#coming-up .row-item").first().getByRole("button", { name: "Pause" }).click();
  await page.waitForTimeout(500);
  const sent = await page.evaluate(() => window.__scheduleCalls);
  const rows = await page.locator("#coming-up .row-item").count();
  const todo = await page.locator("#todo-list").innerText();
  const firstButtons = await page.locator("#coming-up .row-item").first().locator("button").allInnerTexts();
  await page.close();
  assert.equal(asked, false, "a change asked a question");
  assert.deepEqual(sent, [
    { cmd: "brain_schedule_act", id: "s0000000002", action: "delete" },
    { cmd: "brain_schedule_act", id: "s0000000005", action: "done" },
    { cmd: "brain_schedule_act", id: "s0000000001", action: "pause" },
  ]);
  assert.equal(rows, 3);
  assert.match(todo, new RegExp(EMPTY_TODO.replace(/[.]/g, "\\.")));
  assert.deepEqual(firstButtons, ["Resume", "Delete"]);
});

await check("a to-do item is added in the owner's words, one at a time", async () => {
  const page = await workTab({ schedule: { jobs: [], todo: [] } });
  await page.locator("#todo-text").fill("post the letter");
  await page.locator("#todo-add").click();
  await page.waitForTimeout(500);
  const sent = await page.evaluate(() => window.__scheduleCalls);
  const todo = await page.locator("#todo-list").innerText();
  const empty = await page.locator("#coming-up").innerText();
  await page.close();
  assert.deepEqual(sent, [{ cmd: "brain_schedule_add_todo", text: "post the letter" }]);
  assert.match(todo, /post the letter/);
  assert.equal(empty.trim(), EMPTY_JOBS);
});

await check("on a stale link every change is greyed", async () => {
  const page = await workTab({ schedule: { jobs: JOBS, todo: TODO }, link: { stale: true } });
  const disabled = await page.locator("#coming-up-card .row-item button").evaluateAll(
    (bs) => bs.map((b) => b.disabled));
  const add = await page.locator("#todo-add").isDisabled();
  await page.close();
  assert.ok(disabled.length > 0 && disabled.every(Boolean), `${disabled}`);
  assert.equal(add, true, "Add was offered on a stale link");
});

await check("the words are hidden with the private lists; the times stay", async () => {
  const page = await workTab({ schedule: { jobs: JOBS, todo: TODO }, security: { hidden: true } });
  const text = await page.locator("#coming-up-card").innerText();
  await page.close();
  assert.doesNotMatch(text, /pasta|pills|stretch|milk/);
  assert.match(text, /07:00 tomorrow/);
  assert.match(text, /Hidden until Windows Hello/);
});

await check("a PC without the scheduler: the section says so", async () => {
  const page = await workTab({});
  const text = await page.locator("#coming-up").innerText();
  const form = await page.locator("#todo-form").isHidden();
  await page.close();
  assert.equal(text.trim(), SCHEDULE_MISSING);
  assert.equal(form, true);
});

await check("a `schedule` event reads the list again", async () => {
  const page = await workTab({ schedule: { jobs: JOBS, todo: TODO } });
  const before = await page.evaluate(() => window.__schedule.reads);
  await page.evaluate(() => window.__emit("jarvis-event",
    { kind: "schedule", id: 9, data: { id: "s0000000001", kind: "timer", state: "fired", late: false } }));
  await page.waitForTimeout(400);
  const after = await page.evaluate(() => window.__schedule.reads);
  await page.close();
  assert.ok(after > before, `${before} -> ${after}`);
});

await check("an answer made without the model shows the Done line", async () => {
  const route = (r) => "\u001fjarvis-route:" + JSON.stringify(r);
  const page = await K.open(browser, base, "index.html", {
    chatReplies: [[route({ where: "local", lane: "no AI model", quick: "timer_set",
      injected_facts: 0, injected_ids: [] }), "Timer set for 10 minutes."],
    [route({ where: "local", lane: "qwen3:8b" }), "Hello."]],
  }, { width: 760, height: 620 });
  await page.locator("#prompt").fill("set a timer for 10 minutes");
  await page.keyboard.press("Enter");
  await page.waitForTimeout(700);
  const note = await page.locator("#answer-memory-note").innerText();
  await page.locator("#prompt").fill("hello");
  await page.keyboard.press("Enter");
  await page.waitForTimeout(700);
  const note2 = await page.locator("#answer-memory-note").isHidden();
  await page.close();
  assert.equal(note.trim(), DONE_LINE);
  assert.equal(note2, true, "the Done line stayed on an ordinary answer");
});

/* ── CONTROL: the Rust ────────────────────────────────────────────────── */

await check("CONTROL: toasts on fired only, words by id, lock-screen words while locked; Brain only", async () => {
  const stream = read("src-tauri/src/stream.rs");
  assert.match(stream, /"schedule" if event\.data\["state"\]\.as_str\(\) == Some\("fired"\) =>/);
  assert.match(stream, /spawn\(crate::brain::schedule::toast_fired\(/);
  const rs = read("src-tauri/src/brain/schedule.rs");
  const toast = rs.slice(rs.indexOf("pub async fn toast_fired("));
  const body = toast.slice(0, toast.indexOf("\n}\n"));
  assert.match(body, /security\.app_lock \|\| crate::lock::private_hidden/);
  assert.match(body, /first_time\(/, "a replayed event could toast twice");
  for (const cmd of ["brain_schedule_act", "brain_schedule_add_todo"]) {
    const f = rs.slice(rs.indexOf(`pub async fn ${cmd}(`));
    const b = f.slice(0, f.indexOf("\n}\n"));
    assert.ok(b.indexOf("require_link_live") >= 0 && b.indexOf("require_link_live") < b.indexOf("post("),
      `${cmd} is not held on a stale link`);
  }
  const list = rs.slice(rs.indexOf("pub async fn brain_schedule("));
  assert.match(list.slice(0, list.indexOf("\n}\n")), /private_hidden/);
  for (const cmd of ["brain_schedule", "brain_schedule_act", "brain_schedule_add_todo"]) {
    assert.match(read("src-tauri/build.rs"), new RegExp(`"${cmd}"`));
    assert.match(read("src-tauri/src/lib.rs"), new RegExp(`brain::schedule::${cmd},`));
    const sets = read("src-tauri/permissions/surfaces.toml").split("[[set]]").slice(1);
    const holders = sets.filter((s) => s.includes(`"allow-${cmd.replace(/_/g, "-")}"`))
      .map((s) => s.match(/identifier = "([^"]+)"/)[1]);
    assert.deepEqual(holders, ["brain-schedule"], cmd);
  }
  const caps = JSON.parse(read("src-tauri/capabilities/brain.json")).permissions;
  assert.ok(caps.includes("brain-schedule"));
  for (const other of ["quickbar", "widget", "hud", "settings", "faces", "onboarding"]) {
    const c = read(`src-tauri/capabilities/${other}.json`);
    assert.ok(!c.includes("brain-schedule"), `${other} holds brain-schedule`);
  }
  assert.match(rs, /pub\(crate\) const ACTIONS: &\[&str\] = &\["pause", "resume", "delete", "done", "add_time"\];/);
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}`
  : "\nComing up: one job per tap, words hidden with the private lists, held on a stale link");
process.exit(fails.length ? 1 : 0);
