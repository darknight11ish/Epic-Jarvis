/**
 * The morning briefing on the desktop (the owner's decisions of 2026-09-25;
 * JARVIS-API.md section 22; src/briefing.js, brain.js paintBriefing,
 * src/briefing-settings.js, src-tauri/src/brain/briefing.rs, stream.rs).
 *
 * What must hold:
 * - the words are both apps' words and the PC's own;
 * - Brain -> Work shows the latest briefing: its sections with their lines,
 *   the weather-and-news line, what was left out, and "Brief me now", which
 *   is a READ - not greyed on a stale link;
 * - its lines are hidden with the private lists under Windows Hello; the
 *   counts stay;
 * - a PC without it says so; a `schedule` event for a briefing reads it
 *   again; in Coming up a briefing job is called "Morning briefing";
 * - Settings -> Morning briefing lists the setups with one Stop each (ONE
 *   briefing per tap), sets one up with the scheduler's rule (the PC raises
 *   the card), greys both on a stale link, says what a briefing includes,
 *   and never shows the briefing itself;
 * - Settings -> Morning briefing has "Show who new emails are from" (on by
 *   default, the owner's decision of 2026-09-25): OFF is sent at once, even
 *   on a stale link; ON is greyed on a stale link and otherwise asks the PC,
 *   which raises ONE approval card; the email senders are LINES of the
 *   briefing, so they are hidden with the private lists;
 * - "What did I miss?" (2026-09-25): a read like "Brief me now" - offered on
 *   a stale link, ONE brain_briefing_now {missed: true}; its answer is shown
 *   with no weather line and its own note; its lines hidden with the private
 *   lists; a PC from before it (an ordinary briefing back) is said plainly;
 *   the phone and the PC say the same words;
 * - CONTROL: the toast says only the fixed words and only when the
 *   briefing is ready; setting up and stopping are held on a stale link in
 *   Rust, and so is turning the senders ON; the powers sit with the right
 *   windows.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  ASKED,
  BRIEFING_DETAIL,
  BRIEFING_MISSING,
  BRIEFING_TITLE,
  EMPTY,
  KEPT,
  LOCK_SCREEN,
  MISSED_DETAIL,
  MISSED_LABEL,
  MISSED_MISSING,
  readMissed,
  NOW_LABEL,
  OUTSIDE_LINE,
  readBriefing,
  readSenders,
  SENDERS_DETAIL,
  SENDERS_LABEL,
  SENDERS_MISSING,
  SENDERS_WAITING,
  sendersView,
  SETUP_DETAIL,
  SETUP_NONE,
  setupArgs,
  SPOKEN,
  TOAST_TITLE,
} from "../src/briefing.js";
import { titleOf, KIND_TAGS } from "../src/coming-up.js";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const readRepo = (p) => readFileSync(join(HERE, "..", "..", p), "utf8");

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/** The PC's own words for the weather (jarvis_briefing.WEATHER_OFF, NEWS_LINE). */
const WEATHER_OFF = "Not included: the weather. It comes only from your own Home Assistant, " +
  "which is not set up for Jarvis on this PC.";
const NEWS_LINE = "News: not available. No news provider has been chosen, so Jarvis fetches " +
  "nothing from the internet for this.";

const BRIEFING = {
  id: "b0123456789",
  heading: "Your briefing for Friday 25 September, made at 07:00.",
  made: 1790000000,
  missed: "",
  private: true,
  sections: [
    { key: "calendar", title: "Calendar", state: "ok", summary: "2 events today.",
      items: ["All day: Mum's birthday", "09:30 Dentist"] },
    { key: "today", title: "Today", state: "ok", summary: "1 reminder still to come today.",
      items: ["12:00 call the bank"] },
    { key: "todo", title: "To-do list", state: "ok", summary: "1 open item.", items: ["buy milk"] },
    { key: "approvals", title: "Approvals", state: "empty", summary: "No approval cards waiting.", items: [] },
    { key: "email", title: "Email", state: "ok", summary: "3 unread emails.",
      items: ["From Alex, Your Bank and GitHub"] },
  ],
  not_included: [],
  text: "…",
};
const SETUPS = [{ id: "s00000000b1", kind: "briefing", state: "active", repeats: true,
  repeat: "every weekday (Monday to Friday) at 07:00", when: "07:00 on Monday" }];
const SOURCES = {
  calendar: { state: "on", said: "Included: your calendar." },
  email: { state: "off", said: "Not included: how many unread emails you have is not set up for Jarvis on this PC." },
  weather: { state: "off", said: WEATHER_OFF },
};
const SENDERS_ON = { on: true, waiting: false, last: null, why: "" };
const SENDERS_OFF = { on: false, waiting: false, last: null, why: "" };
const SCENARIO = { briefing: BRIEFING, setups: SETUPS, sources: SOURCES, senders: SENDERS_ON };

/* ── The words ─────────────────────────────────────────────────────────── */

await check("the words are both apps' words and the PC's own", async () => {
  const kt = readRepo("jarvis-client/app/src/main/java/com/jarvis/client/net/Briefing.kt")
    .replace(/"\s*\+\s*\n?\s*"/g, "");
  for (const words of [BRIEFING_TITLE, BRIEFING_DETAIL, EMPTY, NOW_LABEL, BRIEFING_MISSING, KEPT,
    LOCK_SCREEN, OUTSIDE_LINE, SETUP_DETAIL, SETUP_NONE, ASKED, SPOKEN, SENDERS_LABEL,
    SENDERS_DETAIL, SENDERS_WAITING, SENDERS_MISSING]) {
    assert.ok(kt.includes(`"${words.replace(/"/g, '\\"')}"`), `the phone does not say: ${words}`);
  }
  const py = readRepo("backend/jarvis_briefing.py").replace(/"\s*\n\s*"/g, "");
  for (const words of [LOCK_SCREEN, OUTSIDE_LINE, WEATHER_OFF, NEWS_LINE,
    EMPTY.replace(/"/g, '\\"')]) {
    assert.ok(py.includes(words), `the PC does not say: ${words}`);
  }
  const rs = read("src-tauri/src/brain/briefing.rs");
  assert.ok(rs.includes(`LOCK_SCREEN: &str = "${LOCK_SCREEN}"`));
  assert.ok(rs.includes(`TOAST_TITLE: &str = "${TOAST_TITLE}"`));
  assert.ok(rs.replace(/"\s*\n\s*/g, '"').includes(`"${BRIEFING_MISSING}"`));
  assert.ok(rs.replace(/"\s*\n\s*/g, '"').includes(`"${SENDERS_MISSING}"`));
  const html = read("src/settings.html").replace(/\s+/g, " ");
  assert.ok(html.includes(SENDERS_LABEL) && html.includes(SENDERS_DETAIL),
    "Settings does not show the senders switch in both apps' words");
  // The PC's email words for "What it includes", and its card, say the same.
  assert.ok(py.includes("Included: how many unread emails you have, and who the newest "));
  assert.ok(py.includes("If you say no: nothing changes - the briefing shows only how many new emails "));
  assert.equal(titleOf({ kind: "briefing", text: "", hidden: false }), "Morning briefing");
  assert.equal(KIND_TAGS.briefing, "briefing");
});

await check("reading the answer, and the setup's rule", async () => {
  const v = readBriefing({ available: true, briefing: BRIEFING, setups: SETUPS, sources: SOURCES,
    senders: SENDERS_ON });
  assert.equal(v.briefing.sections.length, 5);
  assert.equal(v.setups[0].id, "s00000000b1");
  for (const nothing of [null, {}, { available: false }, "x"]) {
    const n = readBriefing(nothing);
    assert.equal(n.available, false);
    assert.equal(n.why, BRIEFING_MISSING);
  }
  assert.equal(v.senders.on, true);
  assert.equal(readBriefing({ available: true, briefing: null }).senders, null, "an older PC");
  assert.deepEqual(sendersView(null, true), { show: false, checked: false, canChange: false,
    lines: [SENDERS_MISSING] });
  assert.equal(sendersView(readSenders(SENDERS_OFF), false).canChange, false, "ON offered on a stale link");
  assert.equal(sendersView(readSenders(SENDERS_ON), false).canChange, true, "OFF held on a stale link");
  const waiting = sendersView(readSenders({ ...SENDERS_OFF, waiting: true }), true);
  assert.equal(waiting.checked, true);
  assert.deepEqual(waiting.lines, [SENDERS_WAITING]);
  const denied = sendersView(readSenders({ ...SENDERS_OFF, last: { outcome: "denied",
    message: "The card was turned down, so the briefing shows the number only." } }), true);
  assert.deepEqual(denied.lines, ["The card was turned down, so the briefing shows the number only."]);
  assert.deepEqual(setupArgs("weekday", "07:00"), { every: "weekday", at: "07:00" });
  assert.deepEqual(setupArgs("week", "08:30", [4, 0, 4]), { every: "week", at: "08:30", days: [0, 4] });
  assert.equal(setupArgs("week", "08:30", []), null);
  assert.equal(setupArgs("hours", "08:30"), null);
  assert.equal(setupArgs("day", "25:00"), null);
});

/* ── The Brain window ─────────────────────────────────────────────────── */

const { base, close } = await K.serve();
const browser = await K.launch();
const SIZE = { width: 1180, height: 1100 };

async function workTab(data = {}) {
  const page = await K.open(browser, base, "brain.html", data, SIZE);
  await page.locator("#tab-work").click();
  await page.waitForTimeout(500);
  return page;
}

await check("Brain -> Work: the latest briefing, section by section", async () => {
  const page = await workTab({ briefing: SCENARIO });
  const card = page.locator("#briefing-card");
  const title = (await card.locator("h2").textContent()).trim();
  const note = await card.locator(".note").first().innerText();
  const text = await card.innerText();
  await page.close();
  assert.equal(title, BRIEFING_TITLE);
  assert.equal(note, BRIEFING_DETAIL);
  for (const bit of ["Your briefing for Friday 25 September", "2 events today.", "09:30 Dentist",
    "12:00 call the bank", "buy milk", "3 unread emails.", "From Alex, Your Bank and GitHub",
    OUTSIDE_LINE, KEPT, NOW_LABEL]) {
    assert.ok(text.includes(bit), `missing: ${bit}`);
  }
});

await check("the weather from Home Assistant: its own section, and the PC's last line (I75)", async () => {
  const withWeather = {
    ...BRIEFING,
    sections: [{ key: "weather", title: "Weather", state: "ok", summary: "Now 12 °C, partly cloudy.",
      items: ["Today: rain, 9 to 14 °C, 80% chance of rain", "Tomorrow: sunny, 11 to 18 °C"] },
    ...BRIEFING.sections],
    outside_line: NEWS_LINE,
  };
  const page = await workTab({ briefing: { ...SCENARIO, briefing: withWeather } });
  const text = await page.locator("#briefing-card").innerText();
  await page.close();
  assert.match(text, /weather/i);
  for (const bit of ["Now 12 °C, partly cloudy.", "Today: rain, 9 to 14 °C, 80% chance of rain",
    "Tomorrow: sunny, 11 to 18 °C", NEWS_LINE]) {
    assert.ok(text.includes(bit), `missing: ${bit}`);
  }
  assert.ok(!text.includes(OUTSIDE_LINE), "the old weather-and-news line beside a weather section");
});

await check("Brief me now is a read: it works on a stale link too", async () => {
  const now = { ...BRIEFING, heading: "Your briefing for Friday 25 September, made at 09:12." };
  const page = await workTab({ briefing: { ...SCENARIO, now }, link: { stale: true } });
  const disabled = await page.locator("#briefing-now").isDisabled();
  await page.locator("#briefing-now").click();
  await page.waitForTimeout(500);
  const calls = await page.evaluate(() => window.__briefingCalls.map((c) => c.cmd));
  const text = await page.locator("#briefing").innerText();
  await page.close();
  assert.equal(disabled, false, "a read was greyed on a stale link");
  assert.ok(calls.includes("brain_briefing_now"), calls.join());
  assert.match(text, /made at 09:12/);
});

const MISSED = {
  id: "b00000000m1", source: "missed", private: true, missed: "",
  heading: "What you missed since 14:05 today, when you last talked to Jarvis.",
  sections: [
    { key: "went_off", title: "Went off", state: "ok", summary: "1 reminder went off.",
      items: ["15:00 call the bank"] },
    { key: "approvals", title: "Approvals", state: "empty", summary: "No approval cards waiting.", items: [] },
    { key: "next", title: "Coming up", state: "ok", summary: "The next is at 18:00 today.",
      items: ["18:00 today: water the plants"] },
  ],
  not_included: [],
};

await check("What did I miss?: the words are both apps' and the PC's", async () => {
  const kt = readRepo("jarvis-client/app/src/main/java/com/jarvis/client/net/Briefing.kt")
    .replace(/"\s*\+\s*\n?\s*"/g, "");
  for (const words of [MISSED_LABEL, MISSED_DETAIL, MISSED_MISSING]) {
    assert.ok(kt.includes(`"${words.replace(/"/g, '\\"')}"`), `the phone does not say: ${words}`);
  }
  const py = readRepo("backend/jarvis_briefing.py").replace(/"\s*\n\s*"/g, "");
  for (const words of [MISSED_LABEL, MISSED_DETAIL, MISSED_MISSING.replace(/"/g, '\\"')]) {
    assert.ok(py.includes(words), `the PC does not say: ${words}`);
  }
  assert.ok(read("src/brain.html").includes(`>${MISSED_LABEL}</button>`));
  assert.equal(readMissed({ briefing: { ...BRIEFING, source: "now" } }), null,
    "an ordinary briefing was read as What did I miss?");
  assert.equal(readMissed({ briefing: MISSED }).briefing.source, "missed");
});

await check("What did I miss? is a read: ONE request, on a stale link too, shown with its own note", async () => {
  const page = await workTab({ briefing: { ...SCENARIO, missed: MISSED }, link: { stale: true } });
  const disabled = await page.locator("#briefing-missed").isDisabled();
  await page.locator("#briefing-missed").click();
  await page.waitForTimeout(500);
  const calls = await page.evaluate(() => window.__briefingCalls.filter((c) => c.cmd === "brain_briefing_now"));
  const text = await page.locator("#briefing").innerText();
  await page.close();
  assert.equal(disabled, false, "a read was greyed on a stale link");
  assert.deepEqual(calls, [{ cmd: "brain_briefing_now", missed: true }]);
  assert.match(text, /What you missed since 14:05 today/);
  assert.match(text, /15:00 call the bank/);
  assert.ok(text.includes(MISSED_DETAIL));
  assert.ok(!text.includes(OUTSIDE_LINE), "the weather line on What did I miss?");
  assert.ok(!text.includes(KEPT), "What did I miss? said it is kept");
});

await check("What did I miss?: hidden lines stay hidden; an older PC is said plainly", async () => {
  const page = await workTab({ briefing: { ...SCENARIO, missed: MISSED }, security: { hidden: true } });
  await page.locator("#briefing-missed").click();
  await page.waitForTimeout(500);
  const text = await page.locator("#briefing-card").innerText();
  await page.close();
  assert.doesNotMatch(text, /bank|plants/);
  assert.match(text, /1 reminder went off\./);
  const old = await workTab({ briefing: SCENARIO });
  await old.locator("#briefing-missed").click();
  await old.waitForTimeout(500);
  const toasts = await old.locator("body").innerText();
  const heading = await old.locator("#briefing").innerText();
  await old.close();
  assert.ok(toasts.includes(MISSED_MISSING), "an older PC was not said plainly");
  assert.match(heading, /Your briefing for Friday 25 September/);
});

await check("the lines are hidden with the private lists; the counts stay", async () => {
  const page = await workTab({ briefing: SCENARIO, security: { hidden: true } });
  const text = await page.locator("#briefing-card").innerText();
  await page.close();
  assert.doesNotMatch(text, /Dentist|bank|milk|birthday|Alex|GitHub/);
  assert.match(text, /2 events today\./);
  assert.match(text, /3 unread emails\./);
  assert.match(text, /Hidden until Windows Hello/);
});

await check("no briefing yet: it says how to get one", async () => {
  const page = await workTab({ briefing: { setups: [], sources: SOURCES } });
  const text = await page.locator("#briefing").innerText();
  await page.close();
  assert.equal(text.trim(), EMPTY);
});

await check("a PC without it: the section says so, and offers no button", async () => {
  const page = await workTab({});
  const text = await page.locator("#briefing").innerText();
  const hidden = await page.locator("#briefing-now").isHidden();
  await page.close();
  assert.equal(text.trim(), BRIEFING_MISSING);
  assert.equal(hidden, true);
});

await check("a `schedule` event for a briefing reads it again; in Coming up it is 'Morning briefing'", async () => {
  const page = await workTab({ briefing: SCENARIO,
    schedule: { jobs: [{ id: "s00000000b1", kind: "briefing", text: "", state: "active", repeats: true,
      repeat: "every weekday (Monday to Friday) at 07:00", when: "07:00 on Monday", due: 1 }], todo: [] } });
  const before = await page.evaluate(() => window.__briefing.reads);
  await page.evaluate(() => window.__emit("jarvis-event",
    { kind: "schedule", id: 9, data: { id: "s00000000b1", kind: "briefing", state: "ready" } }));
  await page.waitForTimeout(400);
  const after = await page.evaluate(() => window.__briefing.reads);
  const row = await page.locator("#coming-up .row-item").first().innerText();
  await page.close();
  assert.ok(after > before, `${before} -> ${after}`);
  assert.match(row, /Morning briefing/);
  assert.match(row, /briefing, repeats/i);
});

/* ── Settings ─────────────────────────────────────────────────────────── */

const settings = (data) => K.open(browser, base, "settings.html", data, { width: 820, height: 1400 });

await check("Settings: the setups, one Stop each, what it includes - never the briefing", async () => {
  const page = await settings({ briefing: SCENARIO });
  await page.waitForTimeout(600);
  const text = await page.locator("#briefing-settings").innerText();
  const stops = await page.locator("#br-setups button").allInnerTexts();
  const every = await page.locator("#briefing-settings button").allInnerTexts();
  await page.close();
  assert.match(text, /every weekday \(Monday to Friday\) at 07:00/);
  assert.match(text, /Included: your calendar\./);
  assert.ok(text.includes(WEATHER_OFF), "the weather's line, in the PC's words");
  assert.ok(text.includes(SPOKEN));
  assert.doesNotMatch(text, /Dentist|bank|milk/, "Settings showed the briefing itself");
  assert.deepEqual(stops, ["Stop"]);
  for (const b of every) assert.doesNotMatch(b, /\ball\b|clear|everything/i, `a bulk control: ${b}`);
});

await check("Settings: Set up sends the scheduler's rule; Stop sends ONE id; both ask nothing here", async () => {
  const page = await settings({ briefing: SCENARIO });
  await page.waitForTimeout(600);
  let asked = false;
  page.on("dialog", (d) => { asked = true; d.dismiss(); });
  await page.locator("#br-time").fill("06:45");
  await page.getByRole("button", { name: "Chosen days" }).click();
  await page.getByRole("button", { name: "Tuesday" }).click();
  await page.getByRole("button", { name: "Wednesday" }).click();
  await page.getByRole("button", { name: "Thursday" }).click();
  await page.locator("#br-set").click();
  await page.waitForTimeout(500);
  const status = await page.locator("#br-status").innerText();
  await page.locator("#br-setups button").first().click();
  await page.waitForTimeout(500);
  const calls = await page.evaluate(() => window.__briefingCalls.filter((c) => c.cmd !== "get_briefing_setup"));
  await page.close();
  assert.equal(asked, false);
  assert.deepEqual(calls, [
    { cmd: "set_briefing", every: "week", at: "06:45", days: [0, 4] },
    { cmd: "stop_briefing", id: "s00000000b1" },
  ]);
  assert.equal(status, ASKED);
});

await check("Settings: 'Show who new emails are from' - on by default, OFF sent at once", async () => {
  const page = await settings({ briefing: SCENARIO });
  await page.waitForTimeout(600);
  const label = await page.locator("#br-senders-row").innerText();
  const checked = await page.locator("#br-senders").isChecked();
  await page.locator("#br-senders").click();
  await page.waitForTimeout(500);
  const calls = await page.evaluate(() => window.__briefingCalls.filter((c) => c.cmd === "set_briefing_senders"));
  const status = await page.locator("#br-senders-status").innerText();
  const after = await page.locator("#br-senders").isChecked();
  await page.close();
  assert.ok(label.includes(SENDERS_LABEL) && label.includes(SENDERS_DETAIL), label);
  assert.equal(checked, true, "not on by default");
  assert.deepEqual(calls, [{ cmd: "set_briefing_senders", enabled: false }]);
  assert.match(status, /the number|how many new emails/);
  assert.equal(after, false);
});

await check("Settings: turning the senders ON asks the PC, which shows a card", async () => {
  const page = await settings({ briefing: { ...SCENARIO, senders: SENDERS_OFF } });
  await page.waitForTimeout(600);
  await page.locator("#br-senders").click();
  await page.waitForTimeout(600);
  const calls = await page.evaluate(() => window.__briefingCalls.filter((c) => c.cmd === "set_briefing_senders"));
  const status = await page.locator("#br-senders-status").innerText();
  const lines = await page.locator("#br-senders-lines").innerText();
  const checked = await page.locator("#br-senders").isChecked();
  await page.close();
  assert.deepEqual(calls, [{ cmd: "set_briefing_senders", enabled: true }]);
  assert.match(status, /Waiting for your approval/);
  assert.ok(lines.includes(SENDERS_WAITING), lines);
  assert.equal(checked, true, "a waiting card reads as on");
});

await check("Settings: on a stale link the senders' ON is greyed, and OFF still goes", async () => {
  const off = await settings({ briefing: { ...SCENARIO, senders: SENDERS_OFF }, link: { stale: true } });
  await off.waitForTimeout(600);
  const heldOn = await off.locator("#br-senders").isDisabled();
  await off.close();
  const on = await settings({ briefing: SCENARIO, link: { stale: true } });
  await on.waitForTimeout(600);
  const offAllowed = await on.locator("#br-senders").isDisabled();
  await on.locator("#br-senders").click();
  await on.waitForTimeout(500);
  const calls = await on.evaluate(() => window.__briefingCalls.filter((c) => c.cmd === "set_briefing_senders"));
  await on.close();
  assert.equal(heldOn, true, "ON was offered on a stale link");
  assert.equal(offAllowed, false, "OFF was held on a stale link");
  assert.deepEqual(calls, [{ cmd: "set_briefing_senders", enabled: false }]);
});

await check("Settings: a PC without the setting says so, and offers no switch", async () => {
  const page = await settings({ briefing: { ...SCENARIO, senders: undefined } });
  await page.waitForTimeout(600);
  const hidden = await page.locator("#br-senders-row").isHidden();
  const lines = await page.locator("#br-senders-lines").innerText();
  await page.close();
  assert.equal(hidden, true);
  assert.equal(lines.trim(), SENDERS_MISSING);
});

await check("Settings: on a stale link Set up and Stop are greyed", async () => {
  const page = await settings({ briefing: SCENARIO, link: { stale: true } });
  await page.waitForTimeout(600);
  const set = await page.locator("#br-set").isDisabled();
  const stop = await page.locator("#br-setups button").first().isDisabled();
  await page.close();
  assert.equal(set, true);
  assert.equal(stop, true);
});

/* ── CONTROL: the Rust ────────────────────────────────────────────────── */

await check("CONTROL: the toast is the fixed words, on ready only; changes held on a stale link; the right windows", async () => {
  const stream = read("src-tauri/src/stream.rs");
  assert.match(stream, /"schedule" if event\.data\["state"\]\.as_str\(\) == Some\("ready"\) =>/);
  assert.match(stream, /spawn\(crate::brain::briefing::toast_ready\(/);
  const rs = read("src-tauri/src/brain/briefing.rs");
  const toast = rs.slice(rs.indexOf("pub async fn toast_ready("));
  const tbody = toast.slice(0, toast.indexOf("\n}\n"));
  assert.match(tbody, /commands::notify\(&app, TOAST_TITLE, LOCK_SCREEN\)/);
  assert.doesNotMatch(tbody, /"text"|summary|items/, "the toast reads the briefing");
  assert.match(tbody, /first_time\(/, "a replayed event could toast twice");
  const sched = read("src-tauri/src/brain/schedule.rs");
  const fired = sched.slice(sched.indexOf("pub async fn toast_fired("));
  assert.match(fired.slice(0, fired.indexOf("\n}\n")), /if kind == "briefing" \{\s*return;/);
  for (const cmd of ["set_briefing", "stop_briefing"]) {
    const f = rs.slice(rs.indexOf(`pub async fn ${cmd}(`));
    const b = f.slice(0, f.indexOf("\n}\n"));
    assert.ok(b.indexOf("require_link_live") >= 0 && b.indexOf("require_link_live") < b.indexOf("post("),
      `${cmd} is not held on a stale link`);
  }
  const sf = rs.slice(rs.indexOf("pub async fn set_briefing_senders("));
  const sb = sf.slice(0, sf.indexOf("\n}\n"));
  assert.match(sb, /if enabled \{\s*require_link_live\(&app\)\?;\s*\}/, "senders ON is not held on a stale link");
  assert.ok(sb.indexOf("require_link_live") < sb.indexOf("post_raw("), "held after it was sent");
  const now = rs.slice(rs.indexOf("pub async fn brain_briefing_now("));
  assert.doesNotMatch(now.slice(0, now.indexOf("\n}\n")), /require_link_live/, "a read is held");
  const stop = rs.slice(rs.indexOf("pub async fn stop_briefing("));
  assert.match(stop.slice(0, stop.indexOf("\n}\n")), /is_setup\(/, "Settings could delete any job");
  const sets = read("src-tauri/permissions/surfaces.toml").split("[[set]]").slice(1);
  const holders = (cmd) => sets.filter((s) => s.includes(`"allow-${cmd.replace(/_/g, "-")}"`))
    .map((s) => s.match(/identifier = "([^"]+)"/)[1]);
  for (const cmd of ["brain_briefing", "brain_briefing_now"]) {
    assert.deepEqual(holders(cmd), ["brain-briefing"], cmd);
  }
  for (const cmd of ["get_briefing_setup", "set_briefing", "stop_briefing", "set_briefing_senders"]) {
    assert.deepEqual(holders(cmd), ["settings-surface"], cmd);
  }
  for (const cmd of ["brain_briefing", "brain_briefing_now", "get_briefing_setup", "set_briefing",
    "stop_briefing", "set_briefing_senders"]) {
    assert.match(read("src-tauri/build.rs"), new RegExp(`"${cmd}"`));
    assert.match(read("src-tauri/src/lib.rs"), new RegExp(`brain::briefing::${cmd},`));
  }
  assert.ok(JSON.parse(read("src-tauri/capabilities/brain.json")).permissions.includes("brain-briefing"));
  for (const other of ["quickbar", "widget", "hud", "settings", "faces", "onboarding"]) {
    assert.ok(!read(`src-tauri/capabilities/${other}.json`).includes("brain-briefing"), other);
  }
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}`
  : "\nMorning briefing: the fixed words on every notification, lines hidden with the private lists, changes held on a stale link");
process.exit(fails.length ? 1 : 0);
