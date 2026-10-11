/**
 * Search inside Settings (the owner's request of 2026-10-09).
 *
 * The suites that read settings.html as TEXT cannot see this feature at all -
 * they assert ids and words, and search adds neither. What has to be checked is
 * behaviour, in a real page:
 *
 *   - it filters live, and the section headings of what is left stay visible;
 *   - it matches the label AND the detail under it, not just the title;
 *   - it says nothing matched, in words, and says how to get everything back;
 *   - clearing the box restores the page EXACTLY - same cards, same values;
 *   - it never changes a setting: the box has no call to the PC in it;
 *   - a card hidden by "Show or hide menus" stays hidden through a search, and
 *     stays hidden after the box is emptied.
 *
 * The last one is the bug this feature could plausibly introduce: two reasons
 * for the same `hidden` attribute, and the search must only own one of them.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const { base, close } = await K.serve();
const browser = await K.launch();
const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/** The page, with every card open and every fold out of the way. */
const open = async (data = {}) => {
  const page = await K.open(browser, base, "settings.html", data, { width: 900, height: 1000 });
  await page.waitForTimeout(500);
  return page;
};

/** Card ids that are actually on screen, in page order. */
const showing = (page) => page.evaluate(() =>
  [...document.querySelectorAll("main .card")]
    .filter((c) => !c.hidden)
    .map((c) => c.id || "(no id)"));

/** Band headings that are actually on screen. */
const bands = (page) => page.evaluate(() =>
  [...document.querySelectorAll("main .settings-group-heading")]
    .filter((h) => !h.hidden)
    .map((h) => h.textContent.trim()));

const type = async (page, text) => {
  await page.locator("#settings-search-input").fill(text);
  await page.waitForTimeout(250);
};

/* ── The box is there, and it is first ──────────────────────────────────── */

await check("Settings opens with a search box, above the jump list", async () => {
  const html = readFileSync(join(HERE, "..", "src", "settings.html"), "utf8");
  assert.match(html, /id="settings-search-input"/, "no search box in settings.html");
  assert.match(html, /id="settings-search-none"/, "no empty state in settings.html");
  assert.ok(
    html.indexOf('id="settings-search"') < html.indexOf('id="settings-jump"'),
    "the search box must come before the jump list",
  );
  const page = await open();
  assert.equal(await page.locator("#settings-search-input").count(), 1);
  // Every card is on screen with nothing typed - search hides nothing by itself.
  const before = await showing(page);
  assert.ok(before.length >= 30, `only ${before.length} cards drawn with an empty box`);
  await page.close();
});

/* ── Filtering, live, with the headings kept ────────────────────────────── */

await check("typing filters the cards, and keeps the band of what is left", async () => {
  const page = await open();
  const all = await showing(page);
  await type(page, "backup");
  const left = await showing(page);
  assert.ok(left.length < all.length, "typing did not hide anything");
  assert.ok(left.includes("backup"), `Backups is not among ${left.join(", ")}`);
  assert.ok(!left.includes("voice"), "a card that cannot match is still drawn");
  const shownBands = await bands(page);
  assert.ok(shownBands.length >= 1,
    "every band heading was hidden, so the page no longer says where the card lives");
  await page.close();
});

await check("it matches the DETAIL text, not only the card title", async () => {
  const page = await open();
  // "Obscura" appears in the Browser card's own words and in no card title.
  await type(page, "obscura");
  const left = await showing(page);
  assert.ok(left.length >= 1, "a word from a card's detail found nothing");
  assert.ok(left.includes("browser-engine"),
    `"obscura" did not find the browser card: ${left.join(", ")}`);
  await page.close();
});

await check("a switch and its detail are both searchable", async () => {
  const page = await open();
  // The detail under "Start Jarvis Desktop when Windows starts".
  await type(page, "clipboard");
  const left = await showing(page);
  assert.ok(left.length >= 1, `nothing matched a word from a toggle's detail: ${left.join(", ")}`);
  await page.close();
});

/* ── The empty state ────────────────────────────────────────────────────── */

await check("nothing matched is said in words, with the way back", async () => {
  const page = await open();
  await type(page, "zzzznothinghere");
  assert.equal(await showing(page).then((l) => l.length), 0, "cards are still drawn");
  const none = await page.locator("#settings-search-none").innerText();
  assert.match(none, /zzzznothinghere/, "the empty state does not quote what was typed");
  assert.match(none, /clear|back/i, "the empty state does not say how to get everything back");
  assert.equal(await page.locator("#settings-jump").isVisible(), false,
    "a map of the whole page is still drawn over a filtered page");
  await page.close();
});

/* ── Clearing restores everything ───────────────────────────────────────── */

await check("clearing the box restores the page exactly", async () => {
  const page = await open();
  const before = await showing(page);
  const themeBefore = await page.evaluate(() =>
    document.documentElement.getAttribute("data-theme"));
  await type(page, "backup");
  await page.locator("#settings-search-clear").click();
  await page.waitForTimeout(250);
  const after = await showing(page);
  assert.deepEqual(after, before, "the cards that came back are not the cards that left");
  assert.equal(await page.locator("#settings-search-input").inputValue(), "");
  assert.equal(await page.evaluate(() => document.documentElement.getAttribute("data-theme")),
    themeBefore, "searching changed a setting");
  // Escape clears it too, and the box keeps the focus so typing can continue.
  await type(page, "voice");
  await page.locator("#settings-search-input").press("Escape");
  await page.waitForTimeout(200);
  assert.equal(await page.locator("#settings-search-input").inputValue(), "");
  await page.close();
});

/* ── Keyboard-first ─────────────────────────────────────────────────────── */

await check("Ctrl+F and Alt+F reach the box from anywhere in the page", async () => {
  const page = await open();
  await page.evaluate(() => document.getElementById("store-path")?.focus?.());
  await page.keyboard.press("Control+f");
  assert.equal(await page.evaluate(() => document.activeElement.id), "settings-search-input",
    "Ctrl+F did not reach the search box");
  await page.evaluate(() => document.getElementById("store-path")?.blur?.());
  await page.keyboard.press("Alt+f");
  assert.equal(await page.evaluate(() => document.activeElement.id), "settings-search-input",
    "Alt+F did not reach the search box");
  await page.close();
});

/* ── It is a view, never a change ───────────────────────────────────────── */

await check("the search box cannot change a setting or reach the PC", async () => {
  const js = readFileSync(join(HERE, "..", "src", "settings-search.js"), "utf8");
  // Comments are stripped first: this module's own header SAYS it contains no
  // `invoke(`, and a check that could not tell the sentence from the call would
  // fail on its own documentation.
  const code = js.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
  assert.doesNotMatch(code, /\binvoke\s*\(|\bfetch\s*\(|stream_chat|decide_approval/,
    "settings-search.js reaches the PC directly");
  assert.doesNotMatch(code, /localStorage|sessionStorage/,
    "settings-search.js writes something down");
  assert.doesNotMatch(code, /innerHTML|outerHTML|insertAdjacentHTML/,
    "settings-search.js builds markup instead of showing what is there");
  // And in the page: filtering a search left every control where it was.
  const page = await open();
  // The page's OWN boot makes a few calls (one of them a save); what matters is
  // that the search adds none, so the count is taken before anything is typed.
  const callsBefore = await page.evaluate(() => window.__calls.length);
  const stateBefore = await page.evaluate(() =>
    [...document.querySelectorAll("input[type=checkbox]")].map((i) => `${i.id}=${i.checked}`));
  await type(page, "voice");
  await type(page, "");
  const stateAfter = await page.evaluate(() =>
    [...document.querySelectorAll("input[type=checkbox]")].map((i) => `${i.id}=${i.checked}`));
  assert.deepEqual(stateAfter, stateBefore, "searching moved a switch");
  const added = await page.evaluate((n) => window.__calls.slice(n).map((c) => c[0]), callsBefore);
  assert.deepEqual(added, [], `searching called the PC: ${added.join(", ")}`);
  await page.close();
});

/* ── A hidden menu is a different fact from a hidden card ───────────────── */

await check("a card the owner hid stays hidden through a search and after it", async () => {
  const page = await open();
  // Hide a menu through the page's own machinery, exactly as the owner would.
  const hidden = await page.evaluate(async () => {
    const mod = await import("./menu-visibility-settings.js");
    const card = document.getElementById("backup");
    const mid = card.dataset.menuId || "settings.backup";
    mod.menuManager.hide(mid);
    mod.applyVisibility();
    return { hidden: card.hidden, attr: card.dataset.menuHidden };
  });
  assert.equal(hidden.hidden, true, "the card the test hid was not hidden");
  assert.equal(hidden.attr, "true", "the menu's decision was not recorded for the search to read");
  await type(page, "backup");
  assert.equal(await page.locator("#backup").isVisible(), false,
    "a search un-hid a card the owner had hidden");
  await type(page, "");
  assert.equal(await page.locator("#backup").isVisible(), false,
    "clearing the search un-hid a card the owner had hidden");
  await page.close();
});

await browser.close(); close();
console.log(fails.length ? `\n${fails.length} FAILED` : "\nsettings search filters, explains and restores");
process.exit(fails.length ? 1 : 0);
