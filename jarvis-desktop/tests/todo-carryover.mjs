/**
 * The to-do list's day carry-over, in the desktop half (2026-11-02; the
 * owner's choice of both modes with full daily rollover as the default;
 * Gemini's ruling 8; backend/jarvis_schedule.py; docs/JARVIS-API.md section
 * 179; src/coming-up.js and src/brain.js).
 *
 * WHAT THIS PROVES, in the app's own words:
 *  1. the PC's own age tag reaches a row and is shown in the ROLLOVER list
 *     ("from yesterday", "from Friday (3d ago)", "from Oct 26") - and an item
 *     written today grows no tag at all;
 *  2. the day-labelled view is the SAME rows grouped by the day the PC named,
 *     never a second copy, and switching back shows the identical list;
 *  3. an older PC (no `todo_mode`/`todo_days`) reads as rollover, so nothing
 *     changes for a backend from before this feature;
 *  4. while the private lists are hidden the tag is gone too - an age is a fact
 *     about words Rust has already taken out.
 *
 * Pure: no DOM, no Playwright, no network - it imports coming-up.js only.
 */
import assert from "node:assert/strict";

import {
  carryOf,
  metaOf,
  readSchedule,
  todoDays,
  todoItems,
  todoModes,
} from "../src/coming-up.js";

const id = (n) => `s${String(n).padStart(10, "0")}`;

const TODO = [
  { id: id(1), kind: "todo", text: "call the dentist", state: "active", list: "",
    created_date: "2026-10-30", carry: "from Friday (3d ago)" },
  { id: id(2), kind: "todo", text: "renew the prescription", state: "active", list: "",
    created_date: "2026-11-01", carry: "from yesterday" },
  { id: id(3), kind: "todo", text: "buy milk", state: "active", list: "",
    created_date: "2026-11-02" },
  { id: id(4), kind: "todo", text: "old thing", state: "active", list: "",
    created_date: "2026-10-20", carry: "from Oct 20" },
];

const ANSWER = {
  available: true,
  jobs: [],
  todo: TODO,
  todo_mode: "rollover",
  todo_modes: [
    { value: "rollover", label: "Daily rollover", detail: "everything still open" },
    { value: "day", label: "Day by day", detail: "each day its own list" },
  ],
  todo_days: [
    { date: "2026-11-02", label: "Today", count: 1, items: [id(3)] },
    { date: "2026-11-01", label: "Yesterday", count: 1, items: [id(2)] },
    { date: "2026-10-30", label: "Friday (3d ago)", count: 1, items: [id(1)] },
    { date: "2026-10-20", label: "Oct 20", count: 1, items: [id(4)] },
  ],
};

console.log("--- 1. the PC's own age tag on a rollover row ---");
const v = readSchedule(ANSWER);
assert.equal(v.todoMode, "rollover");
assert.equal(v.todo[0].carry, "from Friday (3d ago)");
assert.equal(v.todo[0].createdDate, "2026-10-30");
assert.equal(carryOf(v.todo[0]), "from Friday (3d ago)");
assert.equal(carryOf(v.todo[1]), "from yesterday");
assert.equal(carryOf(v.todo[2]), "", "an item written today has no tag");
assert.equal(carryOf(v.todo[3]), "from Oct 20");
// The tag is a meta line under the row, and only for a to-do.
assert.deepEqual(metaOf(v.todo[0], 0, carryOf(v.todo[0])),
  ["from Friday (3d ago)"]);
assert.deepEqual(metaOf(v.todo[2], 0, carryOf(v.todo[2])), []);
// A 3-day-old item never says "from yesterday": the words are the PC's.
assert.notEqual(v.todo[0].carry, "from yesterday");
// An alarm with the same (nonsense) field is not tagged: this is a to-do rule.
const alarm = readSchedule({ jobs: [], todo: [] });
assert.deepEqual(metaOf({ ...v.todo[0], kind: "alarm" }, 0, "from yesterday"), []);
assert.deepEqual(alarm.todo, []);
console.log("ok    the tag is the PC's words, shown once, and only for a to-do");

console.log("--- 2. day by day is the same rows, grouped ---");
const days = todoDays(v);
assert.deepEqual(days.map((d) => d.label),
  ["Today", "Yesterday", "Friday (3d ago)", "Oct 20"]);
assert.deepEqual(days.map((d) => d.items.map((j) => j.text)),
  [["buy milk"], ["renew the prescription"], ["call the dentist"], ["old thing"]]);
// Same items, same identity: nothing is copied or re-made by the switch.
assert.equal(days[2].items[0], v.todo[0]);
assert.equal(days.reduce((n, d) => n + d.items.length, 0), v.todo.length);
// ...and every open item is still on the rollover list, so switching back is
// the identical list.
assert.deepEqual(todoItems(v).map((j) => j.id), [id(1), id(2), id(3), id(4)]);
const dayView = readSchedule({ ...ANSWER, todo_mode: "day" });
assert.equal(dayView.todoMode, "day");
assert.deepEqual(dayView.todo, v.todo, "the rows the same in both modes");
assert.deepEqual(todoDays(dayView).map((d) => d.items.map((j) => j.id)),
  [[id(3)], [id(2)], [id(1)], [id(4)]]);
console.log("ok    the same rows in the same order, only grouped differently");

console.log("--- 3. an older PC reads as rollover ---");
const old = readSchedule({ available: true, jobs: [], todo: TODO });
assert.equal(old.todoMode, "rollover");
assert.deepEqual(old.todoDays, []);
assert.deepEqual(todoDays(old).map((d) => d.items.length), [4],
  "a PC with no grouping still shows every open item");
assert.deepEqual(todoModes(old).map((m) => m.value), ["rollover", "day"],
  "and the two modes are still offered, in a plain fallback");
console.log("ok    an older backend loses nothing and shows no empty list");

console.log("--- 4. hidden words take the age with them ---");
const hidden = readSchedule({
  available: true, hidden: true, jobs: [], todo: [
    { id: id(1), kind: "todo", text: "(hidden)", hidden: true, list: "",
      created_date: "2026-10-30", carry: "from Friday (3d ago)" },
  ],
});
assert.equal(carryOf(hidden.todo[0]), "",
  "no age is shown while the private lists are hidden");
assert.deepEqual(metaOf(hidden.todo[0], 0, carryOf(hidden.todo[0])), []);
console.log("ok    a hidden item carries no age");

console.log("\ntodo-carryover: every check passed");
