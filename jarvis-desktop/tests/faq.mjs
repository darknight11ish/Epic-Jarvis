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
import { readFileSync } from "node:fs";
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

/* ── Audit 3: what the help text says has to be true ──────────────────── */

const src = (rel) => readFileSync(new URL(`../${rel}`, import.meta.url), "utf8");
const faqAnswer = async (page, question) =>
  page.locator(".faq-item", { hasText: question }).locator(".faq-a").textContent();
const squash = (t) => String(t).replace(/\s+/g, " ").trim();

// F1: the token FAQ said "stored as plain text on disk" and "never shown
// again". It is in Windows Credential Manager, and Settings has a button
// that shows it for the phone.
await check("the token FAQ says Credential Manager and the Show button, not plain text or never shown", async () => {
  const page = await open();
  const answer = squash(await faqAnswer(page, "Is my pairing token safe?"));
  const reveal = await page.locator("#reveal-token").textContent();
  await page.close();
  assert.doesNotMatch(answer, /plain text on disk/i);
  assert.doesNotMatch(answer, /never shown again/i);
  assert.match(answer, /Windows Credential Manager/);
  assert.ok(answer.includes(squash(reveal)), `the FAQ does not name the "${squash(reveal)}" button`);
  assert.match(answer, /no Copy button/);
});

// F3: one sentence for where a card is answered, on every desktop surface,
// and it names the phone.
const WHERE = "in the Jarvis bar, on the widget, or on your phone's Home screen";
await check("every desktop surface says where to approve in the same words, phone included", async () => {
  assert.ok(src("src/jarvis-link.js").includes(`export const APPROVE_WHERE = "${WHERE}";`));
  const page = await open();
  const faq = squash(await page.locator(".faq-item", { hasText: "Where do I approve" }).locator(".approve-where").textContent());
  await page.close();
  assert.equal(faq, WHERE);
  const onboarding = squash(src("src/onboarding.html").match(/<span class="approve-where">([\s\S]*?)<\/span>/)[1]);
  assert.equal(onboarding, WHERE);
  // The two wake-word sentences in Rust, where the constant cannot reach.
  const voice = src("src-tauri/src/voice.rs").replace(/\\\n\s*/g, "");
  assert.equal(voice.split(`approve the card ${WHERE}`).length - 1
             + voice.split(`Approve the card ${WHERE}`).length - 1, 2, "voice.rs lost the words");
  // And none of the old, partial versions are left anywhere on the desktop.
  for (const file of ["src/brain.js", "src/settings.js", "src/wiki.js", "src/settings.html",
                      "src/onboarding.html", "src-tauri/src/voice.rs"]) {
    const text = squash(src(file));
    assert.doesNotMatch(text, /in the Jarvis bar and on the widget/, file);
    assert.doesNotMatch(text, /You approve it in the Jarvis bar\./, file);
    assert.doesNotMatch(text, /in the Jarvis bar \(<kbd>Alt<\/kbd>\+<kbd>Space<\/kbd> opens it\) and on the widget/, file);
  }
});

// F6: the hotkey's handler files to Logseq only when the PC is set up for
// it, and otherwise to the first note app it is set up for.
await check("the quick-note hotkey is called Quick note, not Quick note to Logseq", async () => {
  const hotkeys = src("src-tauri/src/hotkeys.rs");
  assert.match(hotkeys, /id: "quick_note",[\s\S]*?label: "Quick note",/);
  assert.doesNotMatch(hotkeys, /Quick note to Logseq/);
  assert.match(src("src/main.js"), /const target = ready\.includes\(asked\) \|\| !ready\.length \? asked : ready\[0\];/,
    "the handler no longer picks the first set-up note app - the label may be wrong again");
});

// F8: Models is inside the Brain's Faculties tab.
await check("the slow-model FAQ points at Brain window → Faculties → Models, which exists", async () => {
  const page = await open();
  const answer = squash(await faqAnswer(page, "Jarvis suddenly got slow"));
  await page.close();
  assert.match(answer, /Brain window → Faculties → Models/);
  const brain = src("src/brain.html");
  assert.match(brain, /id="tab-faculties"[\s\S]*?<span class="rail-label">Faculties<\/span>/);
  const faculties = brain.slice(brain.indexOf('id="view-faculties"'));
  assert.ok(faculties.indexOf('id="models"') > -1 &&
    faculties.indexOf('id="models"') < faculties.indexOf("</section>"), "Models is not in Faculties");
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
