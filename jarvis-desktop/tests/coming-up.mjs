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
 * - the standby schedule (2026-09-25): two times and Set up, ONE
 *   brain_schedule_add_standby (the PC raises one card), then its row in the
 *   list and a pointer instead of the form; held on a stale link; its line
 *   says how the last end went; no toast for a kind the PC says notifies
 *   nobody; the phone says the same words.
 * - the everyday quick wins (2026-09-25): "Just went off" with Snooze - ONE
 *   brain_schedule_act "snooze" for that id, ten minutes, asking nothing;
 *   named lists under their own headings with their own Add box; "Clear
 *   list" asks "are you sure?" first and sends the list and the count it
 *   showed - nothing on a "no"; all of it greyed on a stale link; list names
 *   hidden with the private lists; the to-do list itself has no Clear; the
 *   phone and the PC say the same words.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  actionsOf,
  addPlaceholder,
  CLEAR_LIST_LABEL,
  clearListQuestion,
  COMING_UP_DETAIL,
  COMING_UP_TITLE,
  countdown,
  DONE_LINE,
  HIDDEN_LIST_TITLE,
  LISTS_NOTE,
  namedLists,
  SNOOZE_LABEL,
  SNOOZE_SECONDS,
  tagOf,
  todoItems,
  WENT_OFF_DETAIL,
  WENT_OFF_TITLE,
  wentOffMeta,
  EMPTY_JOBS,
  EMPTY_TODO,
  LOCK_SCREEN,
  lengthWords,
  metaOf,
  readSchedule,
  SCHEDULE_MISSING,
  STANDBY_ADD,
  STANDBY_BAD_TIMES,
  STANDBY_DETAIL,
  STANDBY_END_LABEL,
  STANDBY_IS_SET,
  STANDBY_START_LABEL,
  STANDBY_TITLE,
  standbyOf,
  standbyTimes,
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

await check("the standby schedule's words, title, lines and times", async () => {
  const kt = readRepo("jarvis-client/app/src/main/java/com/jarvis/client/net/Schedule.kt")
    .replace(/"\s*\+\s*\n?\s*"/g, "");
  for (const words of [STANDBY_TITLE, STANDBY_DETAIL, STANDBY_START_LABEL, STANDBY_END_LABEL,
    STANDBY_ADD, STANDBY_IS_SET, STANDBY_BAD_TIMES]) {
    assert.ok(kt.includes(`"${words}"`), `the phone does not say: ${words}`);
  }
  const html = read("src/brain.html");
  assert.ok(html.includes(`>${STANDBY_TITLE}</h3>`));
  assert.ok(html.includes(`>${STANDBY_DETAIL}</p>`));
  assert.ok(html.includes(`>${STANDBY_IS_SET}</p>`));
  assert.ok(read("src-tauri/src/brain/schedule.rs").includes(`"${STANDBY_BAD_TIMES}"`));
  const job = { id: "s00000000aa", kind: "standby", text: "", state: "active", due: NOW + 60,
    when: "awake at 07:00 today, if the schedule put it on standby", repeats: true, repeat: "every day from 01:00 to 07:00",
    note: "Went on standby at 01:00." };
  const v = readSchedule({ jobs: [job], todo: [] });
  assert.equal(titleOf(v.jobs[0]), STANDBY_TITLE);
  assert.equal(titleOf({ ...v.jobs[0], hidden: true }), STANDBY_TITLE, "hidden words hid the title");
  assert.deepEqual(metaOf(v.jobs[0]), ["every day from 01:00 to 07:00",
    "next: awake at 07:00 today, if the schedule put it on standby", "Went on standby at 01:00."]);
  assert.deepEqual(actionsOf(v.jobs[0]), ["pause", "delete"]);
  assert.equal(standbyOf(v).id, "s00000000aa");
  assert.equal(standbyOf(readSchedule({ jobs: JOBS, todo: [] })), null);
  assert.deepEqual(standbyTimes("1:00", "07:00"), { at: "01:00", until: "07:00" });
  for (const [a, b] of [["01:00", "01:00"], ["24:00", "07:00"], ["", "07:00"], ["7", "8"]]) {
    assert.equal(standbyTimes(a, b), null, `${a} ${b}`);
  }
  // The PC's own words for the kind.
  const py = readRepo("backend/jarvis_standby_schedule.py");
  assert.ok(py.includes('"standby schedule"')
    && py.includes('edges=("on standby", "awake", ", if the schedule put it on standby")'));
});

/* ── Snooze and named lists: the words and the reading ────────────────── */

const WENT = [{ id: "s00000000c1", kind: "alarm", text: "", state: "fired", repeats: false,
  went_off_at: "07:00", fired_at: NOW - 60 }];
const LISTED = [
  { id: "s00000000d1", kind: "todo", text: "milk", state: "active", list: "shopping" },
  { id: "s00000000d2", kind: "todo", text: "eggs", state: "active", list: "shopping" },
  { id: "s00000000d3", kind: "todo", text: "post the letter", state: "active", list: "" },
];
const LISTS = [{ name: "shopping", title: "Shopping list", open: 2 }];

await check("snooze and named lists: both apps' words, and the PC's", async () => {
  const kt = readRepo("jarvis-client/app/src/main/java/com/jarvis/client/net/Schedule.kt")
    .replace(/"\s*\+\s*\n?\s*"/g, "");
  for (const words of [WENT_OFF_TITLE, WENT_OFF_DETAIL, SNOOZE_LABEL, LISTS_NOTE, CLEAR_LIST_LABEL,
    HIDDEN_LIST_TITLE]) {
    assert.ok(kt.includes(`"${words.replace(/"/g, '\\"')}"`), `the phone does not say: ${words}`);
  }
  assert.ok(kt.includes(`const val SNOOZE_SECONDS = ${SNOOZE_SECONDS}`));
  const html = read("src/brain.html");
  assert.ok(html.includes(`>${WENT_OFF_TITLE}</h3>`) && html.includes(`>${WENT_OFF_DETAIL}</p>`));
  assert.ok(html.includes(`>${LISTS_NOTE}</p>`));
  const rs = read("src-tauri/src/brain/schedule.rs");
  assert.ok(rs.includes(`SNOOZE_LABEL: &str = "${SNOOZE_LABEL}"`));
  assert.ok(rs.includes(`SNOOZE_SECONDS: f64 = ${SNOOZE_SECONDS}.0`));
  const py = readRepo("backend/jarvis_schedule.py");
  assert.ok(py.includes(`SNOOZE_DEFAULT = ${SNOOZE_SECONDS}.0`));
  assert.ok(py.includes('DEFAULT_LIST_TITLE = "To-do list"'));
  // "Clear the shopping list" said to Jarvis points here, by this button's name.
  assert.ok(readRepo("backend/jarvis_quick.py").includes(CLEAR_LIST_LABEL));
  assert.equal(clearListQuestion("Shopping list", 3),
    "Clear the shopping list? This deletes all 3 items on it, and cannot be undone.");
  assert.equal(clearListQuestion("Packing list", 1),
    "Clear the packing list? This deletes all 1 item on it, and cannot be undone.");
  assert.equal(addPlaceholder("Shopping list"), "Add to the shopping list");
  assert.equal(addPlaceholder("To-do list"), "Add to the to-do list");
});

await check("reading: what went off, the lists, and which items are on which", async () => {
  const v = readSchedule({ jobs: [], todo: LISTED, went_off: WENT, lists: LISTS });
  assert.equal(v.wentOff.length, 1);
  assert.deepEqual(wentOffMeta(v.wentOff[0]), ["Went off at 07:00"]);
  assert.deepEqual(wentOffMeta({ ...v.wentOff[0], missed: "missed at 07:00" }),
    ["Went off at 07:00 (late - the PC was off or asleep)"]);
  assert.deepEqual(todoItems(v).map((j) => j.text), ["post the letter"]);
  const lists = namedLists(v);
  assert.equal(lists.length, 1);
  assert.equal(lists[0].title, "Shopping list");
  assert.deepEqual(lists[0].items.map((j) => j.text), ["milk", "eggs"]);
  assert.equal(tagOf({ kind: "alarm", snoozed: true }), "alarm, snoozed");
  assert.equal(tagOf({ kind: "reminder", repeats: true }), "reminder, repeats");
  const old = readSchedule({ jobs: [], todo: [] });
  assert.deepEqual([old.wentOff, old.lists], [[], []], "an older PC is read as nothing new");
  const hid = namedLists(readSchedule({ jobs: [], todo: LISTED.map((j) => ({ ...j, list: j.list ? "hidden-1" : "" })),
    lists: [{ name: "hidden-1", title: "", open: 2 }], hidden: true }));
  assert.equal(hid[0].title, HIDDEN_LIST_TITLE);
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

await check("the standby schedule: two times, Set up, ONE request, then its row", async () => {
  const page = await workTab({ schedule: { jobs: [JOBS[0]], todo: [] } });
  const formShown = await page.locator("#standby-form").isVisible();
  const setHidden = await page.locator("#standby-is-set").isHidden();
  const start = await page.locator("#standby-start").inputValue();
  const end = await page.locator("#standby-end").inputValue();
  let asked = false;
  page.on("dialog", (d) => { asked = true; d.dismiss(); });
  await page.locator("#standby-start").fill("23:30");
  await page.locator("#standby-end").fill("06:45");
  await page.locator("#standby-add").click();
  await page.waitForTimeout(600);
  const sent = await page.evaluate(() => window.__scheduleCalls);
  const rows = await page.locator("#coming-up .row-item").allInnerTexts();
  const buttons = await page.locator("#coming-up .row-item").nth(1).locator("button").allInnerTexts();
  const formAfter = await page.locator("#standby-form").isHidden();
  const setAfter = await page.locator("#standby-is-set").isVisible();
  await page.close();
  assert.equal(formShown && setHidden, true, "the form was not offered");
  assert.equal(start, "01:00");
  assert.equal(end, "07:00");
  assert.equal(asked, false, "Set up asked a question in the app - the card on the PC is the question");
  assert.deepEqual(sent, [{ cmd: "brain_schedule_add_standby", start: "23:30", end: "06:45" }]);
  assert.equal(rows.length, 2);
  assert.match(rows[1], new RegExp(STANDBY_TITLE));
  assert.match(rows[1], /every day from 23:30 to 06:45/);
  assert.match(rows[1], new RegExp(WAITING.replace(/[.]/g, "\\.")));
  assert.deepEqual(buttons, ["Delete"]);
  assert.equal(formAfter && setAfter, true, "a second standby schedule was offered");
});

await check("the standby schedule is held on a stale link, and says how it last went", async () => {
  const job = { id: "s00000000aa", kind: "standby", text: "", state: "active", due: NOW + 60,
    left: 60, when: "awake at 07:00 today, if the schedule put it on standby", repeats: true, repeat: "every day from 01:00 to 07:00",
    note: "Skipped standby at 01:00: a task was running, and standby would unload the model it uses." };
  const stale = await workTab({ schedule: { jobs: [], todo: [] }, link: { stale: true } });
  const disabled = await stale.locator("#standby-add").isDisabled();
  await stale.close();
  assert.equal(disabled, true, "Set up was offered on a stale link");
  const page = await workTab({ schedule: { jobs: [job], todo: [] }, security: { hidden: true } });
  const text = await page.locator("#coming-up").innerText();
  const buttons = await page.locator("#coming-up .row-item").first().locator("button").allInnerTexts();
  await page.close();
  assert.match(text, new RegExp(STANDBY_TITLE));
  assert.match(text, /Skipped standby at 01:00/);
  assert.match(text, /next: awake at 07:00 today, if the schedule put it on standby/);
  assert.deepEqual(buttons, ["Pause", "Delete"]);
});

await check("Just went off: Snooze is ONE change for that id, ten minutes, asking nothing", async () => {
  const page = await workTab({ schedule: { jobs: [], todo: [], went_off: WENT } });
  const shown = await page.locator("#went-off-part").isVisible();
  const title = await page.locator("#went-off-part h3").innerText();
  const text = await page.locator("#went-off").innerText();
  let asked = false;
  page.on("dialog", (d) => { asked = true; d.dismiss(); });
  await page.locator("#went-off .row-item").first().getByRole("button", { name: SNOOZE_LABEL }).click();
  await page.waitForTimeout(500);
  const sent = await page.evaluate(() => window.__scheduleCalls);
  const after = await page.locator("#went-off-part").isHidden();
  const rows = await page.locator("#coming-up .row-item").allInnerTexts();
  await page.close();
  assert.equal(shown, true, "Just went off was not shown");
  assert.equal(title.trim().toLowerCase(), WENT_OFF_TITLE.toLowerCase());
  assert.match(text, /Went off at 07:00/);
  assert.equal(asked, false, "Snooze asked a question");
  assert.deepEqual(sent, [{ cmd: "brain_schedule_act", id: "s00000000c1", action: "snooze",
    seconds: SNOOZE_SECONDS }]);
  assert.equal(after, true, "it stayed under Just went off");
  assert.equal(rows.length, 1);
  assert.match(rows[0], /snoozed/i);
});

await check("nothing went off: the part is not shown", async () => {
  const page = await workTab({ schedule: { jobs: JOBS, todo: TODO } });
  const hidden = await page.locator("#went-off-part").isHidden();
  await page.close();
  assert.equal(hidden, true);
});

await check("a named list: its heading, its items, its own Add, and Clear list asks first", async () => {
  const page = await workTab({ schedule: { jobs: [], todo: LISTED, lists: LISTS } });
  const heading = await page.locator("#named-lists h3").allInnerTexts();
  const items = await page.locator("#named-lists .row-item").allInnerTexts();
  const todo = await page.locator("#todo-list .row-item").allInnerTexts();
  const placeholder = await page.locator("#named-lists input").getAttribute("placeholder");
  const todoButtons = await page.locator("#todo-list, #todo-form").locator("button").allInnerTexts();
  await page.locator("#named-lists input").fill("bread");
  await page.locator("#named-lists").getByRole("button", { name: "Add" }).click();
  await page.waitForTimeout(500);
  // No: nothing is sent.
  const questions = [];
  page.once("dialog", (d) => { questions.push(d.message()); d.dismiss(); });
  await page.locator("#named-lists").getByRole("button", { name: CLEAR_LIST_LABEL }).click();
  await page.waitForTimeout(400);
  const afterNo = await page.evaluate(() => window.__scheduleCalls.length);
  // Yes: ONE request with the list and the count shown.
  page.once("dialog", (d) => { questions.push(d.message()); d.accept(); });
  await page.locator("#named-lists").getByRole("button", { name: CLEAR_LIST_LABEL }).click();
  await page.waitForTimeout(600);
  const sent = await page.evaluate(() => window.__scheduleCalls);
  const left = await page.locator("#named-lists .row-item").count();
  await page.close();
  assert.deepEqual(heading.map((h) => h.trim().toLowerCase()), ["shopping list"]);
  assert.equal(items.length, 2);
  assert.match(items[0], /milk/);
  assert.deepEqual(todo.length, 1, "a shopping item showed on the to-do list");
  assert.equal(placeholder, "Add to the shopping list");
  assert.ok(!todoButtons.some((b) => /clear/i.test(b)), "the to-do list has a Clear");
  assert.deepEqual(questions, [clearListQuestion("Shopping list", 3), clearListQuestion("Shopping list", 3)]);
  assert.equal(afterNo, 1, "a no still cleared");
  assert.deepEqual(sent, [
    { cmd: "brain_schedule_add_todo", text: "bread", list: "shopping" },
    { cmd: "brain_schedule_clear_list", list: "shopping", count: 3 },
  ]);
  assert.equal(left, 0);
});

await check("on a stale link Snooze, a list's Add and Clear list are greyed", async () => {
  const page = await workTab({ schedule: { jobs: [], todo: LISTED, lists: LISTS, went_off: WENT },
    link: { stale: true } });
  const snooze = await page.locator("#went-off button").evaluateAll((bs) => bs.map((b) => b.disabled));
  const lists = await page.locator("#named-lists button").evaluateAll((bs) => bs.map((b) => b.disabled));
  await page.close();
  assert.ok(snooze.length === 1 && snooze.every(Boolean), `${snooze}`);
  assert.ok(lists.length >= 2 && lists.every(Boolean), `${lists}`);
});

await check("hidden: no list names, no words, no Add and no Clear list", async () => {
  const page = await workTab({ schedule: { jobs: [], todo: LISTED, lists: LISTS, went_off:
    [{ ...WENT[0], kind: "reminder", text: "see Dr Patel" }] }, security: { hidden: true } });
  const text = await page.locator("#coming-up-card").innerText();
  const buttons = await page.locator("#named-lists button").allInnerTexts();
  await page.close();
  assert.doesNotMatch(text, /shopping|milk|eggs|letter|Patel/i);
  assert.match(text, /\(hidden\) list/i);
  assert.deepEqual(buttons.filter((b) => /clear|add/i.test(b)), []);
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
  assert.ok(body.indexOf("wants_toast(&data)") >= 0
    && body.indexOf("wants_toast(&data)") < body.indexOf("read_job("),
    "a kind that notifies nobody (the standby schedule at 01:00) would still be toasted");
  assert.match(body, /security\.app_lock \|\| crate::lock::private_hidden/);
  assert.match(body, /first_time\(/, "a replayed event could toast twice");
  for (const cmd of ["brain_schedule_act", "brain_schedule_add_todo", "brain_schedule_add_standby",
    "brain_schedule_clear_list"]) {
    const f = rs.slice(rs.indexOf(`pub async fn ${cmd}(`));
    const b = f.slice(0, f.indexOf("\n}\n"));
    assert.ok(b.indexOf("require_link_live") >= 0 && b.indexOf("require_link_live") < b.indexOf("post("),
      `${cmd} is not held on a stale link`);
  }
  const list = rs.slice(rs.indexOf("pub async fn brain_schedule("));
  assert.match(list.slice(0, list.indexOf("\n}\n")), /private_hidden/);
  for (const cmd of ["brain_schedule", "brain_schedule_act", "brain_schedule_add_todo",
    "brain_schedule_add_standby", "brain_schedule_clear_list"]) {
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
  assert.match(rs, /pub\(crate\) const ACTIONS: &\[&str\] = &\[\s*"pause",\s*"resume",\s*"delete",\s*"done",\s*"add_time",\s*"snooze",?\s*\];/);
  // The toast's Snooze: only for the kinds that can be snoozed, and the
  // relaunch lands in one snooze held on a stale link.
  const toastBody = rs.slice(rs.indexOf("pub async fn toast_fired("));
  assert.match(toastBody.slice(0, toastBody.indexOf("\n}\n")), /SNOOZABLE\.contains/);
  const fromToast = rs.slice(rs.indexOf("pub(crate) async fn snooze_from_toast("));
  const ft = fromToast.slice(0, fromToast.indexOf("\n}\n"));
  assert.ok(ft.indexOf("require_link_live") >= 0 && ft.indexOf("require_link_live") < ft.indexOf("post("),
    "a toast's Snooze is not held on a stale link");
  const lib = read("src-tauri/src/lib.rs");
  assert.match(lib, /winrt_toast::snooze_id_from_argv\(&_argv\)/);
  assert.match(lib, /winrt_toast::snooze_at_startup\(&handle\)/);
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}`
  : "\nComing up: one job per tap, words hidden with the private lists, held on a stale link");
process.exit(fails.length ? 1 : 0);
