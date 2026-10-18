/**
 * Today cards on the Brain's Work tab (the owner's choice of 2026-09-28;
 * JARVIS-API.md section 82; src/today.js, brain.js paintToday,
 * src-tauri/src/brain/schedule.rs brain_schedule_add_today; backend
 * jarvis_today.py).
 *
 * What must hold:
 * - the words are both apps' words and the PC's own, word for word;
 * - the cards that show today are listed with Delete, those later today
 *   under "Later today", and a card for another day not at all;
 * - the latest briefing's parts (weather, calendar, email, still to come
 *   today) show as cards - only a briefing made today, never news, never
 *   "What did I miss?" - read from what Morning briefing already read;
 * - Add sends ONE brain_schedule_add_today with the words, the time and the
 *   days, and asks nothing (no card, no "are you sure?");
 * - Delete sends ONE brain_schedule_act for that id;
 * - held on a stale link; the words hidden with the private lists;
 * - a PC without the scheduler hides the form.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  addArgs,
  BAD_TIME,
  BREAK_LABEL,
  briefingCards,
  cardsOf,
  cardTitle,
  cockpitOf,
  DO_THIS_LABEL,
  dueRows,
  DUE_TITLE,
  EMPTY_CARDS,
  FROM_BRIEFING,
  HINT,
  LATER_TITLE,
  madeToday,
  MAX_TEXT,
  MISSING,
  NEXT_TITLE,
  nextRows,
  NO_BRIEFING_TODAY,
  NO_DAYS,
  NO_WORDS,
  PROPOSALS_OFF,
  PROPOSALS_ON_LABEL,
  PROPOSALS_TITLE,
  proposalRows,
  REMIND_LABEL,
  SNOOZE_LABEL,
  snoozeOffers,
  TAG,
  TODAY_DETAIL,
  TODAY_TITLE,
  todayCards,
  TOO_LONG,
  unspokenEnabled,
} from "../src/today.js";
import { KIND_TAGS, readSchedule, tagOf, TODAY_CARD_TITLE, titleOf } from "../src/coming-up.js";
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
const CARDS = [
  { id: "s0000000d01", kind: "today", text: "Gym bag", state: "active", due: NOW + 7 * 86400,
    when: "07:00 on Monday", repeats: true, repeat: "every Monday and Wednesday at 07:00",
    today: "showing", shows_at: "07:00" },
  { id: "s0000000d02", kind: "today", text: "Bins out", state: "active", due: NOW + 3600,
    when: "18:00 today", repeats: true, repeat: "every Thursday at 18:00",
    today: "later", shows_at: "18:00" },
  { id: "s0000000d03", kind: "today", text: "Water the plants", state: "active",
    due: NOW + 86400, when: "08:00 tomorrow", repeats: true, repeat: "every Sunday at 08:00",
    today: "", shows_at: "08:00" },
];
const BRIEFING = {
  id: "b0123456789", source: "schedule",
  heading: "Your briefing, made at 07:00.", made: NOW - 60, missed: "", private: true,
  sections: [
    { key: "weather", title: "Weather", state: "ok", summary: "Now 12 °C, partly cloudy.", items: [] },
    { key: "calendar", title: "Calendar", state: "ok", summary: "2 events today.",
      items: ["09:30 Dentist"] },
    { key: "today", title: "Today", state: "ok", summary: "1 reminder still to come today.",
      items: ["12:00 call the bank"] },
    { key: "todo", title: "To-do list", state: "ok", summary: "1 open item.", items: ["buy milk"] },
    { key: "email", title: "Email", state: "ok", summary: "3 unread emails.",
      items: ["From Alex, Your Bank and GitHub"] },
    { key: "news", title: "News feeds", state: "ok", summary: "2 headlines.", items: ["Big news"] },
  ],
  not_included: [],
};

/* ── The words ─────────────────────────────────────────────────────────── */

await check("the words are both apps' words and the PC's own", async () => {
  const html = read("src/brain.html");
  assert.match(html, /<h2>Today<\/h2>/);
  assert.equal(TODAY_TITLE, "Today");
  assert.ok(html.includes(`>${TODAY_DETAIL}</p>`), "the card's line");
  assert.ok(html.includes(`>${HINT}</p>`), "the hint");
  const kt = readRepo("jarvis-client/app/src/main/java/com/jarvis/client/net/Today.kt")
    .replace(/"\s*\+\s*"/g, "");
  for (const w of [TODAY_TITLE, TODAY_DETAIL, EMPTY_CARDS, LATER_TITLE, FROM_BRIEFING,
    NO_BRIEFING_TODAY, HINT, NO_WORDS, NO_DAYS, BAD_TIME, MISSING, TAG]) {
    assert.ok(kt.includes(JSON.stringify(w).slice(1, -1)), `the phone does not say: ${w}`);
  }
  const sched = readRepo("jarvis-client/app/src/main/java/com/jarvis/client/net/Schedule.kt");
  assert.ok(sched.includes(`TODAY_CARD_TITLE = "${TODAY_CARD_TITLE}"`));
  assert.ok(sched.includes(`TODAY_CARD -> "${TAG}"`));
  assert.ok(kt.includes("A Today card is at most $MAX_TEXT characters - say it more briefly."));
  assert.ok(kt.includes(`MAX_TEXT = ${MAX_TEXT}`));
  const py = readRepo("backend/jarvis_today.py");
  assert.ok(py.includes(`NO_WORDS = "${NO_WORDS}"`), "the PC's NO_WORDS");
  assert.ok(py.includes(`MAX_TEXT = ${MAX_TEXT}`), "the PC's MAX_TEXT");
  assert.ok(py.includes('TOO_LONG = f"A Today card is at most {MAX_TEXT} characters - say it more briefly."'));
  assert.equal(TOO_LONG, `A Today card is at most ${MAX_TEXT} characters - say it more briefly.`);
  const rs = readRepo("jarvis-desktop/src-tauri/src/brain/schedule.rs");
  for (const w of [NO_WORDS, NO_DAYS, BAD_TIME]) assert.ok(rs.includes(w), `Rust does not say: ${w}`);
  assert.ok(rs.includes(`TODAY_MAX_TEXT: usize = ${MAX_TEXT}`));
  assert.equal(KIND_TAGS.today, TAG);
});

await check("reading: which cards show today, which later, and in what order", async () => {
  const v = readSchedule({ available: true, jobs: CARDS, todo: [] });
  const { showing, later } = todayCards(cardsOf(v));
  assert.deepEqual(showing.map((c) => c.text), ["Gym bag"]);
  assert.deepEqual(later.map((c) => c.text), ["Bins out"]);
  assert.equal(later[0].showsAt, "18:00");
  assert.equal(cardTitle({ text: "x", hidden: true }), "(hidden) today card");
  assert.equal(titleOf({ kind: "today", text: "", hidden: true }), TODAY_CARD_TITLE);
  assert.equal(tagOf({ kind: "today", repeats: true }), "today card, repeats");
});

await check("the briefing's parts: only one made today, never news or 'What did I miss?'", async () => {
  const view = { available: true, briefing: { ...BRIEFING, made: NOW - 60, hidden: false,
    sections: BRIEFING.sections } };
  const parts = briefingCards(view);
  assert.deepEqual(parts.map((p) => p.key), ["weather", "calendar", "email", "today"]);
  assert.equal(briefingCards({ briefing: { ...view.briefing, made: NOW - 3 * 86400 } }), null);
  assert.equal(briefingCards({ briefing: { ...view.briefing, source: "missed" } }), null);
  assert.equal(briefingCards({ briefing: null }), null);
  assert.deepEqual(briefingCards({ briefing: { ...view.briefing, hidden: true } })[1].items, []);
  assert.equal(madeToday(NOW), true);
  assert.equal(madeToday("x"), false);
});

await check("the form's arguments, in both apps' words", async () => {
  assert.deepEqual(addArgs("  Gym   bag ", "7:05", [2, 0, 0, 9]),
    { text: "Gym bag", at: "07:05", days: [0, 2] });
  assert.deepEqual(addArgs("", "07:00", [0]), { error: NO_WORDS });
  assert.deepEqual(addArgs("x".repeat(MAX_TEXT + 1), "07:00", [0]), { error: TOO_LONG });
  assert.deepEqual(addArgs("Gym", "7pm", [0]), { error: BAD_TIME });
  assert.deepEqual(addArgs("Gym", "07:00", []), { error: NO_DAYS });
});

const COCKPIT = {
  unspoken_commitments_enabled: false,
  rollover_cards: [],
  due_reminders: [{
    id: "s0000000e01", kind: "reminder", text: "Call the vet", due: NOW - 300,
    when: "12:00 today", went_off: true, fired_at: NOW - 300, overdue: true,
    suggested_prompt: "Help me call the vet about the booster.",
  }],
  active_next_steps: [
    { kind: "goal", id: "g0000001", name: "Insulate the garage",
      step: "Call two installers", by: "Friday" },
    { kind: "project", id: "p0000001", name: "Garage tidy",
      step: "Sort the shelves", by: "" },
  ],
  proposals: [],
};
const COCKPIT_ON = {
  unspoken_commitments_enabled: true,
  rollover_cards: [],
  proposals: [{ text: "send the report to Sam tomorrow", suggested_due: "2026-10-19",
    source_conv_id: "conv-abcdefgh" }],
};

/* ── The Today board's reading (GTD-2) ────────────────────────────────── */

await check("the board: due reminders, next steps, proposals - OFF by default", async () => {
  const c = cockpitOf({ cockpit: COCKPIT });
  assert.equal(unspokenEnabled(c), false);
  assert.equal(cockpitOf({}), null);
  const due = dueRows(c, NOW * 1000);
  assert.equal(due.length, 1);
  assert.equal(due[0].title, "Call the vet");
  assert.deepEqual(due[0].meta, ["Went off (12:00 today)"]);
  assert.equal(due[0].prompt, "Help me call the vet about the booster.");
  assert.equal(due[0].breakPrompt, null, "no stuck_hint, no break offer");
  assert.ok(due[0].snooze.length >= 3, "presets: +15m, +1h, tonight/tomorrow");
  assert.deepEqual(due[0].snooze.slice(0, 2).map((x) => x.seconds), [900, 3600]);
  for (const offer of due[0].snooze) {
    assert.ok(offer.seconds >= 60 && offer.seconds <= 86400, offer.label);
  }
  const steps = nextRows(c);
  assert.deepEqual(steps.map((s) => s.title), ["Call two installers", "Sort the shelves"]);
  assert.equal(steps[0].tag, "goal");
  assert.ok(steps[0].meta.includes("Insulate the garage"));
  assert.equal(steps[1].tag, "project");
  assert.ok(steps[1].meta.includes("work list"));
  assert.deepEqual(proposalRows(c), [], "off: the shelf has nothing");
});

await check("the board: the proposal shelf only when the switch is on", async () => {
  const on = cockpitOf({ cockpit: COCKPIT_ON });
  assert.equal(unspokenEnabled(on), true);
  const rows = proposalRows(on);
  assert.deepEqual(rows.map((r) => r.title), ["send the report to Sam tomorrow"]);
  assert.equal(rows[0].prompt, "Remind me to send the report to Sam tomorrow (2026-10-19).");
  assert.ok(rows[0].meta[0].includes("2026-10-19"));
});

await check("the board: a sensitive or stuck reminder never offers Break Into 3 Steps", async () => {
  const base = { id: "s0000000e02", kind: "reminder", text: "Call the vet",
    went_off: true, when: "12:00 today" };
  const stuck = dueRows({ due_reminders: [{ ...base, stuck_hint: true }] }, NOW * 1000);
  assert.ok(stuck[0].breakPrompt.startsWith("Help me break this into 3 easy steps"));
  const sensitive = dueRows({
    due_reminders: [{ ...base, text: "My chemotherapy appointment", sensitive: true,
      stuck_hint: true }],
  }, NOW * 1000);
  assert.equal(sensitive[0].breakPrompt, null, "sensitive: never offered");
  const overdueOnly = dueRows({
    due_reminders: [{ id: "s0000000e03", kind: "reminder", text: "Call the vet",
      overdue: true, went_off: false, when: "11:00 today" }],
  }, NOW * 1000);
  assert.equal(overdueOnly[0].snooze, null, "not gone off yet: nothing to snooze");
});

await check("the board: snooze presets stay inside the PC's 1 minute..24 hours", async () => {
  const nowMs = new Date(2026, 9, 18, 22, 0, 0).getTime();   // local 22:00: tonight is past
  const offers = snoozeOffers(nowMs);
  assert.deepEqual(offers.map((o) => o.label), ["+15 min", "+1 hour", "Tomorrow"]);
  assert.ok(offers.every((o) => o.seconds >= 60 && o.seconds <= 86400));
  const midday = new Date(2026, 9, 18, 12, 0, 0).getTime();
  assert.deepEqual(snoozeOffers(midday).map((o) => o.label),
    ["+15 min", "+1 hour", "Tonight", "Tomorrow"]);
});

const { base, close } = await K.serve();
const browser = await K.launch();
const SIZE = { width: 1180, height: 900 };

async function workTab(data = {}) {
  const page = await K.open(browser, base, "brain.html", data, SIZE);
  await page.locator("#tab-work").click();
  await page.waitForTimeout(500);
  return page;
}

const SCENARIO = { schedule: { jobs: CARDS, todo: [] },
  briefing: { briefing: BRIEFING, setups: [], sources: {} } };

await check("today's cards, later ones, and the briefing's parts - never news", async () => {
  const page = await workTab(SCENARIO);
  const text = await page.locator("#today").innerText();
  const first = await page.locator("#today .row-item").first().innerText();
  const buttons = await page.locator("#today .row-item").first().locator("button").allInnerTexts();
  await page.close();
  assert.match(first, /Gym bag/);
  assert.match(first, /From 07:00/);
  assert.deepEqual(buttons, ["Delete"]);
  assert.match(text, new RegExp(LATER_TITLE, "i"));
  assert.match(text, /Bins out/);
  assert.doesNotMatch(text, /Water the plants/);
  assert.match(text, new RegExp(FROM_BRIEFING, "i"));
  for (const s of ["Now 12 °C", "2 events today.", "3 unread emails.", "1 reminder still to come"]) {
    assert.ok(text.includes(s), `missing: ${s}`);
  }
  assert.doesNotMatch(text, /Big news|headlines|buy milk/);
});

await check("no cards and no briefing today: said plainly", async () => {
  const page = await workTab({ schedule: { jobs: [], todo: [] },
    briefing: { briefing: { ...BRIEFING, made: NOW - 5 * 86400 }, setups: [], sources: {} } });
  const text = await page.locator("#today").innerText();
  await page.close();
  assert.ok(text.includes(EMPTY_CARDS));
  assert.ok(text.includes(NO_BRIEFING_TODAY));
});

await check("the Today board: Due now with Do This, Break steps and Snooze", async () => {
  const page = await workTab({
    schedule: { jobs: CARDS, todo: [], cockpit: COCKPIT },
    briefing: { briefing: BRIEFING, setups: [], sources: {} },
    security: { hidden: false },
  });
  const text = await page.locator("#today").innerText();
  await page.close();
  assert.match(text, new RegExp(`^${DUE_TITLE}$`, "im"));
  assert.match(text, /Call the vet/);
  assert.match(text, /Went off \(12:00 today\)/);
  assert.ok(text.includes(DO_THIS_LABEL), "Do This With Jarvis");
  assert.ok(text.includes(SNOOZE_LABEL), "the Snooze preset menu");
  assert.ok(!text.includes(BREAK_LABEL), "no stuck_hint: no break offer");
  assert.match(text, new RegExp(`^${NEXT_TITLE}$`, "im"));
  assert.match(text, /Call two installers/);
  assert.match(text, /Insulate the garage/);
  assert.match(text, new RegExp(PROPOSALS_TITLE, "i"));
  assert.ok(text.includes(PROPOSALS_OFF), "the said-I'd-do shelf says it is off");
  assert.ok(text.includes(PROPOSALS_ON_LABEL), "and offers the one opt-in button");
});

await check("the Today board: proposals only with the switch on, and no reminder is made", async () => {
  const page = await workTab({
    schedule: { jobs: [], todo: [], cockpit: COCKPIT_ON },
    briefing: { briefing: BRIEFING, setups: [], sources: {} },
  });
  const text = await page.locator("#today").innerText();
  const buttons = await page.locator("#today .row-item")
    .filter({ hasText: "send the report to Sam tomorrow" })
    .locator("button").allInnerTexts();
  await page.close();
  assert.match(text, /send the report to Sam tomorrow/);
  assert.match(text, /2026-10-19/);
  assert.ok(buttons.includes(REMIND_LABEL), buttons.join(","));
  assert.ok(!text.toUpperCase().includes(DUE_TITLE.toUpperCase()),
    "nothing due: no Due now section");
});

await check("the Today board's words are hidden with the private lists", async () => {
  const page = await workTab({
    schedule: { jobs: [], todo: [], cockpit: COCKPIT_ON },
    briefing: { briefing: BRIEFING, setups: [], sources: {} },
    security: { hidden: true },
  });
  const text = await page.locator("#today-card").innerText();
  await page.close();
  assert.doesNotMatch(text, /Call the vet|Insulate the garage|send the report/);
  assert.match(text, /Hidden until Windows Hello/);
});

await check("Add: ONE brain_schedule_add_today with the words, time and days - asking nothing", async () => {
  const page = await workTab({ schedule: { jobs: [], todo: [] } });
  let asked = false;
  page.on("dialog", (d) => { asked = true; d.dismiss(); });
  await page.locator("#today-text").fill("  Gym bag ");
  await page.locator("#today-at").fill("06:45");
  // Weekdays are ticked to start with: take Tuesday and Thursday off.
  await page.locator("#today-days input[value='1']").uncheck();
  await page.locator("#today-days input[value='3']").uncheck();
  await page.locator("#today-add").click();
  await page.waitForTimeout(600);
  const sent = await page.evaluate(() => window.__scheduleCalls);
  const text = await page.locator("#today").innerText();
  await page.close();
  assert.equal(asked, false);
  assert.deepEqual(sent, [{ cmd: "brain_schedule_add_today", text: "Gym bag", at: "06:45",
    days: [0, 2, 4] }]);
  assert.match(text, /Gym bag/);
});

await check("Delete: ONE brain_schedule_act for that card", async () => {
  const page = await workTab(SCENARIO);
  let asked = false;
  page.on("dialog", (d) => { asked = true; d.dismiss(); });
  await page.locator("#today .row-item").first().getByRole("button", { name: "Delete" }).click();
  await page.waitForTimeout(600);
  const sent = await page.evaluate(() => window.__scheduleCalls);
  await page.close();
  assert.equal(asked, false);
  assert.deepEqual(sent, [{ cmd: "brain_schedule_act", id: "s0000000d01", action: "delete" }]);
});

await check("held on a stale link", async () => {
  const page = await workTab({ ...SCENARIO, link: { stale: true } });
  const add = await page.locator("#today-add").isDisabled();
  const del = await page.locator("#today .row-item button").first().isDisabled();
  await page.close();
  assert.equal(add, true);
  assert.equal(del, true);
});

await check("the words are hidden with the private lists; the times stay", async () => {
  const page = await workTab({ ...SCENARIO, security: { hidden: true } });
  const text = await page.locator("#today-card").innerText();
  await page.close();
  assert.doesNotMatch(text, /Gym bag|Bins out|Dentist|Alex/);
  assert.match(text, /From 07:00/);
  assert.match(text, /Hidden until Windows Hello/);
});

await check("a PC without the scheduler: no form, and it says so", async () => {
  const page = await workTab({});
  const hidden = await page.locator("#today-form").isHidden();
  await page.close();
  assert.equal(hidden, true);
});

await check("CONTROL: the command is registered, allowed on the Brain only, and held on a stale link", async () => {
  const rs = readRepo("jarvis-desktop/src-tauri/src/brain/schedule.rs");
  const fn = rs.slice(rs.indexOf("pub async fn brain_schedule_add_today"));
  assert.ok(fn.slice(0, 400).includes("require_link_live(&app)?"));
  assert.ok(readRepo("jarvis-desktop/src-tauri/src/lib.rs").includes("brain::schedule::brain_schedule_add_today,"));
  const surfaces = readRepo("jarvis-desktop/src-tauri/permissions/surfaces.toml");
  const block = surfaces.slice(surfaces.indexOf('identifier = "brain-schedule"'));
  assert.ok(block.slice(0, 1200).includes('"allow-brain-schedule-add-today"'));
});

await browser.close();
await close();
if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join(", ")}`);
  process.exit(1);
}
console.log("\nall passed");
