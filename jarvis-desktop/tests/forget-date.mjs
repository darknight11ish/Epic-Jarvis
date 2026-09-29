/**
 * Forget's (and Reword's) "When did this actually stop being true?" box -
 * src/valid-to.js and brain.js's promptValidTo.
 *
 * A play tester (2026-09-27) found: "Sept 20" and "1 March" read as the year
 * 2001, a future date accepted, and "last week" showing an error and then
 * dropping the Forget the owner had already said yes to. What must hold:
 *
 * - a date with no year is the latest one that has already happened;
 * - a future date is refused in plain words;
 * - a refused answer asks again (the owner can retype, or leave it blank for
 *   "just now") - it never silently drops the confirmed Forget;
 * - Cancel on the date box still sends nothing, and says so.
 *
 * The pure reader first, then the Brain window in a real browser on the
 * uikit mock.
 */
import assert from "node:assert/strict";
import { IN_THE_FUTURE, NOT_A_DATE, validToFromText } from "../src/valid-to.js";
import * as K from "./uikit.mjs";

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

// 27 September 2026, mid-afternoon, local time.
const NOW = new Date(2026, 8, 27, 15, 0, 0);
const day = (y, m, d) => new Date(y, m - 1, d).getTime() / 1000;

/* ── The reader ──────────────────────────────────────────────────────────── */

await check("blank is \"just now\" - no date sent", async () => {
  assert.deepEqual(validToFromText("", NOW), { seconds: null });
  assert.deepEqual(validToFromText("   ", NOW), { seconds: null });
});

await check("a date with no year is this year's, when that has happened", async () => {
  assert.deepEqual(validToFromText("Sept 20", NOW), { seconds: day(2026, 9, 20) });
  assert.deepEqual(validToFromText("1 March", NOW), { seconds: day(2026, 3, 1) });
  assert.deepEqual(validToFromText("Sep 27", NOW), { seconds: day(2026, 9, 27) },
    "today counts as already happened");
});

await check("...and last year's when this year's is still to come", async () => {
  assert.deepEqual(validToFromText("1 December", NOW), { seconds: day(2025, 12, 1) });
  assert.deepEqual(validToFromText("Oct 3", NOW), { seconds: day(2025, 10, 3) });
});

await check("a typed year is kept", async () => {
  assert.deepEqual(validToFromText("2026-09-20", NOW), { seconds: day(2026, 9, 20) });
  assert.deepEqual(validToFromText("20 Sept 2024", NOW), { seconds: day(2024, 9, 20) });
  assert.deepEqual(validToFromText("March 2025", NOW), { seconds: day(2025, 3, 1) });
});

await check("a future date is refused in plain words", async () => {
  const a = validToFromText("2026-10-05", NOW);
  assert.equal(a.error, `"2026-10-05" ${IN_THE_FUTURE}`);
  assert.match(validToFromText("5 Oct 2027", NOW).error, /is in the future/);
});

await check("words that are not a date are refused, with examples", async () => {
  assert.equal(validToFromText("last week", NOW).error, `"last week" ${NOT_A_DATE}`);
  assert.match(NOT_A_DATE, /2026-09-20 or 20 Sept/);
  assert.match(validToFromText("2026-02-31", NOW).error, /not a date I understand/,
    "31 February must not roll into March");
});

/* ── In the Brain window ─────────────────────────────────────────────────── */

const { base, close } = await K.serve();
const browser = await K.launch();
const SIZE = { width: 1180, height: 820 };

async function forgetWith(answers) {
  const page = await K.open(browser, base, "brain.html", {}, SIZE);
  await page.locator("#tab-memory").click();
  await page.waitForTimeout(250);
  const seen = [];
  page.on("dialog", (d) => {
    seen.push({ type: d.type(), message: d.message(), value: d.defaultValue() });
    if (d.type() === "confirm") return d.accept();
    const next = answers.shift();
    return next === null ? d.dismiss() : d.accept(next);
  });
  await page.locator("#memory-facts .row-item").first()
            .getByRole("button", { name: "Forget" }).click();
  await page.waitForTimeout(400);
  const sent = await page.evaluate(() => window.__memoryWrites || []);
  const toast = await page.locator("#toast").innerText();
  await page.close();
  return { seen, sent, toast };
}

await check("\"last week\" asks again instead of dropping the confirmed Forget", async () => {
  const { seen, sent } = await forgetWith(["last week", ""]);
  const prompts = seen.filter((d) => d.type === "prompt");
  assert.equal(prompts.length, 2, JSON.stringify(seen));
  assert.match(prompts[1].message, /^"last week" is not a date I understand/);
  assert.match(prompts[1].message, /When did this actually stop being true\?/);
  assert.equal(prompts[1].value, "last week", "the typed words are kept to fix");
  assert.equal(sent.length, 1, JSON.stringify(sent));
  assert.equal(sent[0].cmd, "brain_memory_forget");
  assert.equal(sent[0].id, 7);
  assert.equal(sent[0].valid_to, undefined, "blank means just now - no date sent");
});

await check("a future date asks again; a real date then goes with the Forget", async () => {
  const { seen, sent } = await forgetWith(["2099-01-01", "2026-01-15"]);
  const prompts = seen.filter((d) => d.type === "prompt");
  assert.equal(prompts.length, 2);
  assert.match(prompts[1].message, /is in the future/);
  assert.equal(sent.length, 1);
  assert.equal(sent[0].valid_to, day(2026, 1, 15));
});

await check("Cancel on the date box sends nothing, and says so", async () => {
  const { sent, toast } = await forgetWith([null]);
  assert.equal(sent.length, 0);
  assert.equal(toast, "Nothing was forgotten.");
});

await browser.close();
await close();

if (fails.length) {
  console.log(`\n${fails.length} failed`);
  process.exit(1);
}
console.log("\nall passed");
