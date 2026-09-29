/**
 * "Photo to reminder" (the owner's choice, 2026-09-28; JARVIS-API.md section
 * 83; src/photo-reminder.js, main.js, brain.js, src-tauri/src/brain/
 * photo_reminder.rs; backend jarvis_photo_remind.py).
 *
 * What must hold:
 * - the Jarvis bar: after a capture, "Find a date in it" sends ONE
 *   photo_scan with the capture and nothing else; the proposal fills the
 *   What / Date / Time boxes; nothing is added until "Add a Jarvis reminder"
 *   is tapped, and then ONE photo_add_reminder with what the boxes hold;
 * - the words are outside text: drawn as text, never as HTML (a picture that
 *   says `<img onerror=...>` is shown as those characters), never put in the
 *   prompt, and gone from the page once the proposal is closed or used;
 * - nothing date-like: said plainly, and the owner can still type one;
 * - a scan the PC could not read: its sentence, and nothing else;
 * - held on a stale link (greyed here, refused in Rust);
 * - several dates: each can be picked;
 * - the Brain's Coming up: "Choose a picture..." shrinks the file to a
 *   capture's limits (a JPEG data URI) and shows the same proposal;
 * - CONTROL: the Rust command holds the add on a stale link and only sends
 *   a data: picture.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import * as K from "./uikit.mjs";
import {
  ADD_LABEL,
  FOUND_ONE,
  NO_TIME,
  NOTHING_FOUND,
  OUTSIDE_NOTE,
  readScan,
  reminderArgs,
} from "../src/photo-reminder.js";

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

const FLYER = {
  ok: true, outside: true, note: OUTSIDE_NOTE, said: FOUND_ONE,
  text: "Summer fair, Sat 12 Oct, 2pm",
  found: [{ title: "Summer fair", date: "2026-10-12", time: "14:00", at: 1791810000,
    time_found: true, passed: false, when: "Monday 12 October at 14:00" }],
};

/* ── Pure parts ───────────────────────────────────────────────────────── */

await check("readScan keeps at most three, drops a bad date, says nothing found plainly", () => {
  const many = readScan({ text: "x", found: [1, 2, 3, 4].map((d) => ({ title: `E${d}`,
    date: `2026-10-0${d}`, time: "10:00", time_found: true })) });
  assert.equal(many.found.length, 3);
  assert.equal(readScan({ text: "x", found: [{ date: "12/10", time: "10:00" }] }).found.length, 0);
  assert.equal(readScan({ text: "words", found: [] }).said, NOTHING_FOUND);
  assert.equal(readScan({ text: "Fair", found: [{ title: "Fair", date: "2026-10-12",
    time: "25:00" }] }).found[0].time, "09:00");
});

await check("reminderArgs: the owner's boxes, checked in shape", () => {
  assert.deepEqual(reminderArgs(" Summer fair ", "2026-10-12", "14:00").args,
    { date: "2026-10-12", time: "14:00", text: "Summer fair" });
  assert.ok(reminderArgs("x", "", "14:00").error);
  assert.ok(reminderArgs("x", "2026-10-12", "").error);
  assert.ok(reminderArgs("  ", "2026-10-12", "14:00").error);
});

/* ── The Jarvis bar ───────────────────────────────────────────────────── */

const { base, close } = await K.serve();
const browser = await K.launch();

const CAPTURE = {
  dataUri: "data:image/gif;base64,R0lGODlhAQABAAAAACw=",
  width: 1, height: 1, bytes: 634, elapsedMs: 12,
};

/** Answers photo_scan / photo_add_reminder, and writes every call down. */
function photoBridge(page, { scan = FLYER, scanFails = null, addAnswer = null } = {}) {
  return page.evaluate(({ scan, scanFails, addAnswer }) => {
    window.__photo = [];
    const core = window.__TAURI__.core;
    const invoke = core.invoke;
    core.invoke = async (cmd, args) => {
      if (cmd === "photo_scan") {
        window.__photo.push([cmd, args]);
        if (scanFails) throw new Error(scanFails);
        return JSON.parse(JSON.stringify(scan));
      }
      if (cmd === "photo_add_reminder") {
        window.__photo.push([cmd, args]);
        return addAnswer || { ok: true, job: { id: "s0123456789" },
          said: "Reminder set for 14:00 on Monday 12 October." };
      }
      return invoke(cmd, args);
    };
  }, { scan, scanFails, addAnswer });
}

async function bar(data = {}, opts = {}) {
  const page = await K.open(browser, base, "index.html", data);
  await photoBridge(page, opts);
  await page.evaluate((p) => window.__emit("screen-captured", p), CAPTURE);
  await page.waitForTimeout(100);
  return page;
}
const photoCalls = (page) => page.evaluate(() => window.__photo);

await check("the bar: Find a date sends ONE scan with the capture, and fills the boxes", async () => {
  const page = await bar();
  const label = (await page.locator("#capture-find-date").textContent()).trim();
  await page.locator("#capture-find-date").click();
  await page.waitForTimeout(200);
  const out = await page.evaluate(() => ({
    what: document.querySelector("#photo-proposal .photo-what").value,
    date: document.querySelector("#photo-proposal .photo-date").value,
    time: document.querySelector("#photo-proposal .photo-time").value,
    said: document.querySelector("#photo-proposal .photo-said").textContent,
    note: document.querySelector("#photo-proposal .photo-outside").textContent,
    prompt: document.getElementById("prompt").value,
    add: document.querySelector("#photo-proposal .photo-add").textContent,
  }));
  const calls = await photoCalls(page);
  const errors = page.__errors;
  await page.close();
  assert.equal(label, "Find a date in it");
  assert.deepEqual(calls, [["photo_scan", { image: CAPTURE.dataUri }]]);
  assert.deepEqual([out.what, out.date, out.time], ["Summer fair", "2026-10-12", "14:00"]);
  assert.equal(out.said, FOUND_ONE);
  assert.equal(out.note, OUTSIDE_NOTE);
  assert.equal(out.add, ADD_LABEL);
  assert.equal(out.prompt, "What am I looking at?", "the picture's words went into the prompt");
  assert.deepEqual(errors, []);
});

await check("nothing is added without the tap; the tap adds ONE reminder with the boxes' words", async () => {
  const page = await bar();
  await page.locator("#capture-find-date").click();
  await page.waitForTimeout(200);
  let calls = await photoCalls(page);
  assert.equal(calls.filter(([c]) => c === "photo_add_reminder").length, 0);
  await page.fill("#photo-proposal .photo-what", "Summer fair with Sam");
  await page.fill("#photo-proposal .photo-time", "15:30");
  await page.locator("#photo-proposal .photo-add").click();
  await page.waitForTimeout(200);
  calls = await photoCalls(page);
  const box = await page.locator("#photo-proposal").innerText();
  await page.close();
  assert.deepEqual(calls.filter(([c]) => c === "photo_add_reminder"),
    [["photo_add_reminder", { date: "2026-10-12", time: "15:30", text: "Summer fair with Sam" }]]);
  assert.match(box, /Reminder set for 14:00/);
  assert.doesNotMatch(box, /Sat 12 Oct|outside text/, "the picture's words stayed after adding");
});

await check("outside text is drawn as text, never as HTML", async () => {
  const evil = "<img src=x onerror=\"window.__pwned=1\">Fair";
  const page = await bar({}, { scan: { ...FLYER, text: evil,
    found: [{ ...FLYER.found[0], title: evil }] } });
  await page.locator("#capture-find-date").click();
  await page.waitForTimeout(300);
  const out = await page.evaluate(() => ({
    imgs: document.querySelectorAll("#photo-proposal img").length,
    what: document.querySelector("#photo-proposal .photo-what").value,
    words: document.querySelector("#photo-proposal .photo-text").textContent,
    pwned: window.__pwned === 1,
  }));
  await page.close();
  assert.equal(out.imgs, 0);
  assert.equal(out.pwned, false);
  assert.equal(out.what, "<img src=x onerror=\"window.__pwned=1\">Fair");
  assert.match(out.words, /<img src=x/);
});

await check("Close drops the proposal and its words; removing the capture does too", async () => {
  const page = await bar();
  await page.locator("#capture-find-date").click();
  await page.waitForTimeout(200);
  await page.locator("#photo-proposal .photo-close").click();
  const afterClose = await page.evaluate(() => ({
    hidden: document.getElementById("photo-proposal").hidden,
    html: document.getElementById("photo-proposal").innerHTML,
  }));
  await page.locator("#capture-find-date").click();
  await page.waitForTimeout(200);
  await page.locator("#capture-remove").click();
  const afterRemove = await page.evaluate(() => ({
    hidden: document.getElementById("photo-proposal").hidden,
    html: document.getElementById("photo-proposal").innerHTML,
  }));
  const calls = await photoCalls(page);
  await page.close();
  assert.deepEqual(afterClose, { hidden: true, html: "" });
  assert.deepEqual(afterRemove, { hidden: true, html: "" });
  assert.equal(calls.filter(([c]) => c === "photo_add_reminder").length, 0);
});

await check("nothing date-like: said plainly, and the owner can type one in", async () => {
  const page = await bar({}, { scan: { ok: true, outside: true, found: [], said: NOTHING_FOUND,
    text: "Seven dwarves" } });
  await page.locator("#capture-find-date").click();
  await page.waitForTimeout(200);
  const said = await page.locator("#photo-proposal .photo-said").textContent();
  await page.fill("#photo-proposal .photo-what", "Call the theatre");
  await page.fill("#photo-proposal .photo-date", "2026-10-20");
  await page.fill("#photo-proposal .photo-time", "10:00");
  await page.locator("#photo-proposal .photo-add").click();
  await page.waitForTimeout(200);
  const calls = await photoCalls(page);
  await page.close();
  assert.equal(said, NOTHING_FOUND);
  assert.deepEqual(calls.at(-1),
    ["photo_add_reminder", { date: "2026-10-20", time: "10:00", text: "Call the theatre" }]);
});

await check("no time on the picture: 09:00 filled in, and said", async () => {
  const page = await bar({}, { scan: { ...FLYER,
    found: [{ ...FLYER.found[0], time: "09:00", time_found: false }] } });
  await page.locator("#capture-find-date").click();
  await page.waitForTimeout(200);
  const hint = await page.locator("#photo-proposal .photo-hint").textContent();
  await page.close();
  assert.equal(hint, NO_TIME);
});

await check("several dates: each can be picked", async () => {
  const two = { ...FLYER, found: [FLYER.found[0], { title: "Bake sale", date: "2026-10-19",
    time: "11:00", time_found: true, passed: false, when: "Monday 19 October at 11:00" }] };
  const page = await bar({}, { scan: two });
  await page.locator("#capture-find-date").click();
  await page.waitForTimeout(200);
  await page.locator("#photo-proposal .photo-pick").nth(1).click();
  const out = await page.evaluate(() => [".photo-what", ".photo-date", ".photo-time"]
    .map((s) => document.querySelector(`#photo-proposal ${s}`).value));
  await page.close();
  assert.deepEqual(out, ["Bake sale", "2026-10-19", "11:00"]);
});

await check("a scan the PC could not read: its sentence, nothing else", async () => {
  const page = await bar({}, { scanFails: "Windows could not read the words in the picture." });
  await page.locator("#capture-find-date").click();
  await page.waitForTimeout(200);
  const text = await page.locator("#photo-proposal").innerText();
  const adds = await page.locator("#photo-proposal .photo-add").count();
  await page.close();
  assert.match(text, /Windows could not read the words/);
  assert.equal(adds, 0);
});

await check("held on a stale link", async () => {
  const page = await bar({ link: { stale: true } });
  await page.locator("#capture-find-date").click();
  await page.waitForTimeout(200);
  const disabled = await page.locator("#photo-proposal .photo-add").isDisabled();
  await page.close();
  assert.equal(disabled, true);
});

/* ── The Brain's Coming up ────────────────────────────────────────────── */

// A 2x2 red PNG.
const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFklEQVR4nGP8z8Dw" +
  "n4GBgYGJgYGBgQEAHgMCAe9O0DUAAAAASUVORK5CYII=", "base64");

await check("Brain: Choose a picture shrinks the file to a JPEG and shows the same proposal", async () => {
  const page = await K.open(browser, base, "brain.html", {}, { width: 1180, height: 900 });
  await photoBridge(page);
  await page.locator("#tab-work").click();
  await page.waitForTimeout(300);
  const label = (await page.locator("#photo-choose").textContent()).trim();
  await page.setInputFiles("#photo-file", { name: "flyer.png", mimeType: "image/png", buffer: PNG });
  await page.waitForTimeout(500);
  const calls = await photoCalls(page);
  const what = await page.locator("#photo-proposal .photo-what").inputValue();
  await page.close();
  assert.equal(label, "Choose a picture…");
  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], "photo_scan");
  assert.match(calls[0][1].image, /^data:image\/jpeg;base64,/);
  assert.equal(what, "Summer fair");
});

await check("Brain: not a picture is refused in words, nothing sent", async () => {
  const page = await K.open(browser, base, "brain.html", {}, { width: 1180, height: 900 });
  await photoBridge(page);
  await page.locator("#tab-work").click();
  await page.waitForTimeout(300);
  await page.evaluate(() => { document.getElementById("photo-file").accept = ""; });
  await page.setInputFiles("#photo-file", { name: "notes.txt", mimeType: "text/plain",
    buffer: Buffer.from("12 Oct 2pm") });
  await page.waitForTimeout(300);
  const calls = await photoCalls(page);
  const text = await page.locator("#photo-proposal").innerText();
  await page.close();
  assert.equal(calls.length, 0);
  assert.match(text, /not a picture Jarvis can read/);
});

/* ── CONTROL: the Rust ────────────────────────────────────────────────── */

await check("CONTROL: the add is held on a stale link, and only a data: picture is sent", () => {
  const rs = read("src-tauri/src/brain/photo_reminder.rs");
  assert.match(rs, /pub async fn photo_add_reminder[\s\S]*?require_link_live\(&app\)\?/);
  assert.match(rs, /starts_with\("data:image\/"\)/);
  assert.match(rs, /"\/api\/photo\/scan"/);
  assert.doesNotMatch(rs, /"repeat":/, "a photo never sets up a repeating reminder");
  const caps = JSON.parse(read("src-tauri/capabilities/quickbar.json"));
  assert.ok(caps.permissions.includes("photo-reminder"));
});

await browser.close();
await close();
if (fails.length) {
  console.log(`\n${fails.length} failed`);
  process.exit(1);
}
console.log("\nall passed");
