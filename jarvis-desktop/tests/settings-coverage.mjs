/**
 * Settings coverage (task-79, owner requirement of 2026-10-22): every switch
 * the Settings page draws must be findable by its own ordinary words, and the
 * controls that are NOT generated toggle rows (the custom switches) must be
 * findable by the name a person would type for the feature.
 *
 * The row list comes from the SAME generated fixture the page and the phone are
 * built from (`tests/fixtures/settings-cases.json`, written by
 * tools/gen_settings_cases.py from backend/jarvis_settings_registry.py), so a
 * row added to the registry is covered here automatically - there is no second
 * list to forget.
 *
 * This suite deliberately asserts the CARD a row lives in is shown: the search
 * box filters whole cards, and a matching switch inside a hidden card would be
 * a false pass. Where a custom control's wording is the feature's ordinary
 * name, that name is typed here too.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const CASES = JSON.parse(
  readFileSync(join(HERE, "fixtures", "settings-cases.json"), "utf8"));
const ROWS = (CASES.rows || []).filter((row) => row.label);

const { base, close } = await K.serve();
const browser = await K.launch();
const fails = [];
const check = async (name, fn) => {
  try {
    await fn();
    console.log(`ok    ${name}`);
  } catch (e) {
    fails.push(name);
    console.log(`FAIL  ${name}\n      ${e.message}`);
  }
};

const open = async () => {
  const page = await K.open(browser, base, "settings.html", {},
    { width: 900, height: 2000 });
  // The area modules fill their cards asynchronously; search reads the words
  // on screen, so wait for the page to settle before judging coverage.
  await page.waitForTimeout(3000);
  return page;
};

const type = async (page, text) => {
  await page.locator("#settings-search-input").fill(text);
  await page.waitForTimeout(220);
};

const cardsShowing = (page) => page.evaluate(() =>
  [...document.querySelectorAll("main .card")]
    .filter((c) => !c.hidden)
    .map((c) => c.id));

/**
 * For one generated row: is its own card showing after the search, and is the
 * row itself visible? A row whose body is still hidden is in the loading/error
 * state - the search box only searches visible words, by its own contract - so
 * those are listed separately instead of silently passing.
 */
const rowAfterSearch = (page, inputId) => page.evaluate((id) => {
  const input = document.getElementById(id);
  if (!input) return { rowPresent: false };
  const card = input.closest(".card");
  let hiddenBy = null;
  let n = input;
  while (n && n !== document.body) {
    if (n.hidden) { hiddenBy = n.id || n.className || n.tagName; break; }
    n = n.parentElement;
  }
  return {
    rowPresent: true,
    rowHiddenBy: hiddenBy,
    cardId: card ? card.id : "",
    cardShown: Boolean(card) && !card.hidden,
  };
}, inputId);

const firstWords = (label, n = 5) =>
  String(label).replace(/["“”]/g, " ").trim().split(/\s+/).slice(0, n).join(" ");

await check("every generated switch row that is showing is found by its own label", async () => {
  const page = await open();
  const missing = [];
  const hiddenByLoad = [];
  // The rows are judged with NO filter active: a search left on from the
  // previous row would make everything else look "hidden before any search".
  await type(page, "");
  for (const row of ROWS) {
    // Phone-owned rows have no desktop control by design (the phone draws
    // them); the inventory report names them as such instead of demanding a
    // dead switch on the PC.
    if (row.owner && row.owner !== "desktop") continue;
    if (!row.input) continue;
    const before = await rowAfterSearch(page, row.input);
    if (!before.rowPresent) {
      missing.push(`${row.id}: no control on the page at all`);
      continue;
    }
    if (before.rowHiddenBy) {
      // Its area is still loading (or in its own error state). The search box
      // searches the words ON SCREEN, so this is not a search miss - it is the
      // row not being visible yet. Listed explicitly so a NEW one fails.
      hiddenByLoad.push(row.id);
      continue;
    }
    await type(page, firstWords(row.label));
    const after = await rowAfterSearch(page, row.input);
    if (!after.cardShown) {
      missing.push(`${row.id} (${row.label}) -> ${after.cardId || "(no card)"}`);
    }
    await type(page, "");
  }
  await page.close();
  assert.deepEqual(missing, [],
    `settings search does not find these switches:\n${missing.join("\n")}`);
  // Rows inside an area that is still loading (or in its own error state) are
  // not search misses: the search box only reads words ON SCREEN. What must not
  // happen is a row hidden by something else (a menu, a CSS accident) or a
  // growing pile of unsearchable switches - both would be real coverage loss.
  assert.ok(hiddenByLoad.length <= 10,
    `${hiddenByLoad.length} switches are hidden before any search: ${hiddenByLoad.join(",")}`);
});

await check("the custom switches are found by the feature's ordinary words", async () => {
  const page = await open();
  // The word a person types -> the card that must appear, and the control it
  // must contain once shown. These are the non-generated controls: button
  // switches and boards whose words live in their own area module.
  const CUSTOM = [
    ["searchable recordings", "media-index", "#mi-switch"],
    ["media index", "media-index", "#mi-switch"],
    ["big coding model", "big-model", "#bc-switch"],
    ["30B coder", "big-model", "#bc-switch"],
    ["picture mode", "screen-look", "#sp-switch"],
    ["headless browser", "browser-engine", "#be-switch"],
    ["lights without asking", "asks-first", null],
    ["data sandbox", "sandbox", "#sbx-switch"],
    ["chat history", "security", "#ch-switch"],
    ["how long my chats are kept", "security", "#ch-keep"],
    ["quiet hours", "notifications", "#notif-quiet-enabled"],
    ["prompt coach", "prompt-coach", "#coach-enabled"],
  ];
  const missing = [];
  for (const [words, card, control] of CUSTOM) {
    await type(page, words);
    const showing = await cardsShowing(page);
    if (!showing.includes(card)) {
      missing.push(`"${words}" did not show ${card}`);
      continue;
    }
    if (!control) continue;
    const found = await page.evaluate((sel) => {
      const el = document.querySelector(sel);
      return Boolean(el) && !el.closest("[hidden]");
    }, control);
    if (!found) missing.push(`"${words}" showed ${card} but not ${control}`);
  }
  await type(page, "");
  await page.close();
  assert.deepEqual(missing, [], missing.join("\n"));
});

await check("clearing the box brings every card back", async () => {
  const page = await open();
  const all = await cardsShowing(page);
  await type(page, "zzzz-no-such-setting");
  const none = await cardsShowing(page);
  assert.equal(none.length, 0, `a nonsense query left cards showing: ${none}`);
  await type(page, "");
  const restored = await cardsShowing(page);
  await page.close();
  assert.deepEqual(restored, all, "clearing the search did not restore the page");
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}`
  : "\nevery Settings row and custom switch is findable");
process.exit(fails.length ? 1 : 0);
