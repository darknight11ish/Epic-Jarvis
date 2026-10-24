/**
 * "Photo to reminder" - a letter with SEVERAL dates (2026-10-16; src/
 * photo-reminder.js, PhotoReminderDialog.kt).
 *
 * What must hold:
 * - tapping Add on the first of three dates sets ONE reminder and does NOT
 *   take the other two off the page: each still can be picked, the one that
 *   was added reads as added ("(added)") and cannot be picked again;
 * - the PC's sentence becomes the status line, and the picture's own
 *   words-read block and the outside-text note go on the first add (they are
 *   about the words, and a reminder is now set);
 * - a SECOND date can then really be added, with its own date and time -
 *   which is the whole point: one tap sets one reminder, not the only one;
 * - the Add button is shut while the boxes hold the one just added, so a
 *   quick second tap cannot set the same reminder twice;
 * - CONTROL: the phone keeps the other dates too and says "(added)" in the
 *   same words (net/PhotoReminder.kt, PhotoReminderDialog.kt).
 *
 * IT BITES: with src/photo-reminder.js reverted to its previous shape (the box
 * replaced by the PC's sentence), the first check fails on "one add must not
 * take the other dates off the page" and the CONTROL on P.addedWords.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import * as K from "./uikit.mjs";
import * as P from "../src/photo-reminder.js";

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};
const repo = (p) => readFileSync(new URL(`../../${p}`, import.meta.url), "utf8");

const FLYER = {
  ok: true, outside: true,
  said: "Found 3 dates. Check the first, or pick another, then tap to add it.",
  text: "Summer fair Sat 12 Oct 2pm; Bake sale 19 Oct 11am; Quiz night 24 Oct 7.30pm",
  found: [
    { title: "Summer fair", date: "2026-10-12", time: "14:00", time_found: true,
      passed: false, when: "Monday 12 October at 14:00" },
    { title: "Bake sale", date: "2026-10-19", time: "11:00", time_found: true,
      passed: false, when: "Monday 19 October at 11:00" },
    { title: "Quiz night", date: "2026-10-24", time: "19:30", time_found: true,
      passed: false, when: "Saturday 24 October at 19:30" },
  ],
};

const { base, close } = await K.serve();
const browser = await K.launch();
const CAPTURE = {
  dataUri: "data:image/gif;base64,R0lGODlhAQABAAAAACw=",
  width: 1, height: 1, bytes: 634, elapsedMs: 12,
};

/** Answers photo_scan with FLYER and echoes each reminder's date and time. */
function photoBridge(page) {
  return page.evaluate((scan) => {
    window.__photo = [];
    const core = window.__TAURI__.core;
    const invoke = core.invoke;
    core.invoke = async (cmd, args) => {
      if (cmd === "photo_scan") {
        window.__photo.push([cmd, args]);
        return JSON.parse(JSON.stringify(scan));
      }
      if (cmd === "photo_add_reminder") {
        window.__photo.push([cmd, args]);
        return { ok: true, job: { id: "s0123456789" },
          said: `Reminder set for ${args.time} on ${args.date}.` };
      }
      return invoke(cmd, args);
    };
  }, FLYER);
}

const addedCalls = (page) => page.evaluate(() =>
  window.__photo.filter(([c]) => c === "photo_add_reminder").map(([, a]) => a));

/* A read that cannot throw when the proposal has been taken off the page:
   every field is guarded, so a reverted box reads as null instead of a
   TypeError, and the assertion that names the fault is the one that fails. */
const READ = () => {
  const q = (sel) => document.querySelector(`#photo-proposal ${sel}`);
  return {
    picks: [...document.querySelectorAll("#photo-proposal .photo-pick")].map((b) => ({
      text: b.textContent, disabled: b.disabled })),
    said: (q(".photo-said") || {}).textContent || "",
    words: !!q(".photo-words"),
    outside: !!q(".photo-outside"),
    addDisabled: q(".photo-add") ? q(".photo-add").disabled : null,
    what: q(".photo-what") ? q(".photo-what").value : "",
    date: q(".photo-date") ? q(".photo-date").value : "",
    time: q(".photo-time") ? q(".photo-time").value : "",
  };
};

await check("three dates: one add keeps the other two live and marks the one added", async () => {
  const page = await K.open(browser, base, "index.html", {});
  page.setDefaultTimeout(8000);
  await photoBridge(page);
  await page.evaluate((p) => window.__emit("screen-captured", p), CAPTURE);
  await page.waitForTimeout(100);
  await page.locator("#capture-find-date").click();
  await page.waitForTimeout(200);
  const before = await page.locator("#photo-proposal .photo-pick").count();
  // The boxes already hold the first proposal, so one tap adds it.
  await page.locator("#photo-proposal .photo-add").click();
  await page.waitForTimeout(200);
  const after = await page.evaluate(READ);
  const calls = await addedCalls(page);
  const errors = page.__errors;
  // Fail on the fault that names itself before going on to the second date.
  assert.equal(before, 3);
  assert.equal(after.picks.length, 3, "one add must not take the other dates off the page");
  assert.equal(after.picks[0].text, "Monday 12 October at 14:00 - Summer fair (added)");
  assert.doesNotMatch(after.picks[1].text, /\(added\)/);
  assert.doesNotMatch(after.picks[2].text, /\(added\)/);
  assert.deepEqual(after.picks.map((p) => p.disabled), [true, false, false]);
  assert.match(after.said, /Reminder set for 14:00 on 2026-10-12/);
  assert.equal(after.words, false, "the picture's words-read block stayed after an add");
  assert.equal(after.outside, false, "the outside-text note stayed after an add");
  assert.equal(after.addDisabled, true, "the same reminder could be set twice");
  assert.deepEqual(calls, [{ date: "2026-10-12", time: "14:00", text: "Summer fair" }]);
  // The other two must still be clickable: pick the second one...
  await page.locator("#photo-proposal .photo-pick").nth(1).click();
  const boxes = await page.evaluate(READ);
  assert.deepEqual([boxes.what, boxes.date, boxes.time], ["Bake sale", "2026-10-19", "11:00"]);
  assert.equal(boxes.addDisabled, false, "the second date could not be picked");
  // ...and that one can really be added, with its own date and time.
  await page.locator("#photo-proposal .photo-add").click();
  await page.waitForTimeout(200);
  const second = await page.evaluate(READ);
  const secondCalls = await addedCalls(page);
  await page.close();
  assert.equal(secondCalls.length, 2);
  assert.deepEqual(secondCalls[1], { date: "2026-10-19", time: "11:00", text: "Bake sale" });
  assert.match(second.said, /Reminder set for 11:00 on 2026-10-19/);
  assert.match(second.picks[0].text, /\(added\)/);
  assert.match(second.picks[1].text, /\(added\)/);
  assert.equal(second.picks[2].disabled, false);
  assert.deepEqual(errors, []);
});

await check("CONTROL: the phone keeps the other dates too, and says the same words", () => {
  // The PC's own helper, so the words below are this tree's.
  assert.equal(P.addedWords("Monday 12 October at 14:00"), "Monday 12 October at 14:00 (added)");
  const kt = repo("jarvis-client/app/src/main/java/com/jarvis/client/net/PhotoReminder.kt");
  const dialog = repo(
    "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/PhotoReminderDialog.kt");
  assert.match(kt, /const val ADDED = "\(added\)"/);
  assert.match(kt, /fun addedWords\(label: String\): String/);
  // A revert to "only the PC's own sentence stays" fails all three of these.
  assert.match(dialog, /PhotoReminder\.proposals\(scan, added\)/,
    "the phone no longer draws every proposal");
  assert.match(dialog, /PhotoReminder\.addedWords\(/,
    "the phone does not mark the added one");
  assert.match(dialog, /PhotoReminder\.key\(date, time\) !in added/,
    "the phone would let the same reminder be added twice");
});

await browser.close();
await close();
if (fails.length) {
  console.log(`\n${fails.length} failed`);
  process.exit(1);
}
console.log("\nall passed");
