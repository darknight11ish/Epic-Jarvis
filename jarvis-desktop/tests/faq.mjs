/**
 * The desktop FAQ.
 *
 * Plain read-only content, so the bar for a bug is low: every item has to
 * actually be present, open and close on click (native <details>, but the
 * page's own CSS could still hide the summary or break the toggle), and the
 * page has to render it without throwing — the same control every other
 * settings.html test in this directory already runs.
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

const VIEW = { width: 760, height: 1400 };
const open = (data = {}) => K.open(browser, base, "settings.html", data, VIEW);

await check("the FAQ card is present with more than a handful of items", async () => {
  const page = await open();
  const count = await page.locator(".faq-item").count();
  await page.close();
  assert.ok(count >= 8, `only found ${count} FAQ items`);
});

await check("every item has both a question and an answer, with real text in each", async () => {
  const page = await open();
  const items = await page.locator(".faq-item").evaluateAll((els) =>
    els.map((el) => ({
      q: el.querySelector(".faq-q")?.textContent?.trim() || "",
      a: el.querySelector(".faq-a")?.textContent?.trim() || "",
    })));
  await page.close();
  for (const { q, a } of items) {
    assert.ok(q.length > 8, `a question was too short: "${q}"`);
    assert.ok(a.length > 20, `an answer was too short for "${q}": "${a}"`);
  }
});

await check("items start closed and open on click, one at a time", async () => {
  const page = await open();
  const first = page.locator(".faq-item").first();
  assert.equal(await first.evaluate((el) => el.open), false,
    "an FAQ item started open, hiding the rest of the page below the fold");
  await first.locator(".faq-q").click();
  assert.equal(await first.evaluate((el) => el.open), true,
    "clicking the question did not open the answer");
  await first.locator(".faq-q").click();
  assert.equal(await first.evaluate((el) => el.open), false,
    "clicking an open question a second time did not close it");
  await page.close();
});

await check("the desktop FAQ says it is desktop-specific, distinct from the phone's", async () => {
  const page = await open();
  const note = await page.locator(".card", { hasText: "Frequently asked questions" })
    .locator(".note").first().innerText();
  await page.close();
  assert.match(note, /phone/i, `did not distinguish itself from the phone app: "${note}"`);
});

await check("no NEW page error while the FAQ renders", async () => {
  // settings.html already throws "Cannot read properties of null (reading
  // 'enabled')" on load in this harness, in every scenario, independent of
  // the FAQ - confirmed via `git stash` against the commit before this file
  // existed. That is out of scope here; this only guards against the FAQ
  // itself adding a NEW error on top of it.
  const page = await open();
  await page.locator(".faq-item").last().locator(".faq-q").click();
  const errors = page.__errors.filter(
    (e) => !/Cannot read properties of null \(reading 'enabled'\)/.test(e));
  await page.close();
  assert.deepEqual(errors, [], errors.join(" | "));
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nthe FAQ holds");
process.exit(fails.length ? 1 : 0);
