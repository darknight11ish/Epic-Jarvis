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
 *
 * The suite's second half checks the typo tolerance added 2026-10-10 (one
 * search word may be a little misspelt - NOT a licence to match anything
 * roughly the same shape). Those checks run `rank` in the page, so they
 * measure the shipped module rather than a copy of it.
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

/**
 * `rank` as the PAGE loads it - the shipped module, in the browser - so the
 * matching checks measure the code the search box really runs. A copy of the
 * rules written into this file could pass while the module did something else.
 */
const rankOf = (page, label, text, query) => page.evaluate(
  async ([l, t, q]) => (await import("./settings-search.js")).rank(l, t, q),
  [label, text, query]);

/** The four tiers, named as the module and `SettingsSearch.kt` name them. */
const EXACT = 4;   // the token IS a word of the heading
const PREFIX = 3;  // the token starts a word of the heading
const FUZZY = 2;   // the token is a near miss of a word of the heading
const DETAIL = 1;  // the token is somewhere in the part's text
const NONE = 0;

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

await check("a switch is found by its own label, not only by its detail", async () => {
  // The phone's defect of 2026-10-13 was that a switch's own words found
  // nothing, because the phone matches a hand-kept index. This module matches
  // the page's own text at the moment of the search, so the two switches below
  // are checks that the desktop really does not have that gap - and that the
  // labels a person reads are the words that find them. Read from the DOM
  // rather than written out again here, so a relabelled switch fails this
  // rather than passing against a stale copy.
  const page = await open();
  const securityLabel = await page.locator("#sec-private").evaluate((box) =>
    box.closest("label").querySelector("span").textContent.replace(/\s+/g, " ").trim());
  assert.ok(securityLabel.length > 0,
    "the memory-lists switch has no label at all, so a person has nothing to type");
  await type(page, securityLabel.toLowerCase());
  const left = await showing(page);
  assert.ok(left.includes("security"),
    `typing the switch's own label, "${securityLabel}", did not find the Security card: ` +
    `${left.join(", ") || "nothing was left showing"}`);
  // A phrase from the middle of the same label, which is what a person types
  // when they half-remember the switch.
  await type(page, "memory lists");
  assert.ok((await showing(page)).includes("security"),
    `"memory lists" did not find the card that switch is drawn in: ${(await showing(page)).join(", ")}`);
  // ...and a second switch elsewhere, read the same way, so this is not one
  // row's happy accident.
  const clickLabel = await page.locator("#floating-click-through").evaluate((box) =>
    box.closest("label").querySelector("span").textContent.replace(/\s+/g, " ").trim());
  await type(page, clickLabel.toLowerCase());
  assert.ok((await showing(page)).includes("appearance-card"),
    `typing "${clickLabel}" did not find the Appearance card: ${(await showing(page)).join(", ")}`);
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

/* ── One typo must not hide a setting (2026-10-10) ──────────────────────── */

await check("a single typo still finds the card", async () => {
  const page = await open();
  // "notifcation" is one letter dropped and one added from "notifications" -
  // the exact miss the field reported, where the card used to vanish.
  await type(page, "notifcation");
  const left = await showing(page);
  assert.ok(left.includes("notifications"),
    `one typed typo hid the card: ${left.join(", ") || "nothing was left showing"}`);
  assert.equal(await rankOf(page, "Notifications", "", "notifcation"), FUZZY,
    "a miss of a heading's own word is not ranked as a near miss");
  // One edit, at a length where one is the whole budget (4-7 letters is 1)...
  assert.equal(await rankOf(page, "Setting", "", "setzing"), FUZZY,
    "one substitution in a seven-letter word was not tolerated");
  // ...and two edits at that length is one too many, or "settings" would be
  // reachable from anything of the same shape.
  assert.equal(await rankOf(page, "Setting", "", "setzinx"), NONE,
    "a seven-letter word tolerated two edits");
  // A long word gets two: "notifcation" -> "notifications" is two.
  assert.equal(await rankOf(page, "Notifications", "", "notifcation"), FUZZY);
  await page.close();
});

await check("a swapped pair of letters still finds the card", async () => {
  const page = await open();
  // Swapping two neighbours is ONE mistake, not two - "voise" for "voice".
  await type(page, "voise");
  const left = await showing(page);
  assert.ok(left.includes("voice"),
    `a transposition hid the card: ${left.join(", ") || "nothing was left showing"}`);
  assert.equal(await rankOf(page, "Your voice", "", "voise"), FUZZY,
    "a swapped pair counted as two edits, or as no match at all");
  await page.close();
});

await check("a short word matches its own word, never a longer one an edit away", async () => {
  const page = await open();
  // A word of three letters or fewer gets NO edit tolerance at all: with one,
  // "cat" would reach "chat", "bat", "cot" and "cut".
  assert.equal(await rankOf(page, "Chat", "", "cat"), NONE,
    `a three-letter search reached a longer word (cat -> chat)`);
  assert.equal(await rankOf(page, "", "a chat about it", "cat"), NONE,
    "a three-letter search reached a longer word in the detail text");
  // ...and it must still match the word it IS, even when another word in the
  // same heading begins with it - "cat" is a word, not only a prefix.
  assert.equal(await rankOf(page, "Cat", "", "cat"), EXACT,
    "a word that equals the heading was not an exact match");
  assert.equal(await rankOf(page, "Cat catalogue", "", "cat"), EXACT,
    "a short word was demoted to a prefix match because a longer word begins with it");
  await page.close();
});

await check("a word typed in full does not reach a different word with a different opening", async () => {
  const page = await open();
  // One edit apart, but they do not open with the same two letters. The
  // prefix guard is what keeps a whole word from landing on its neighbour.
  assert.equal(await rankOf(page, "Rocket", "", "docket"), NONE,
    "a word typed in full reached a different word one letter away");
  assert.equal(await rankOf(page, "Deck", "", "dock"), NONE,
    "a four-letter word reached a different word one letter away");
  // The other half of the same rule: same opening, one edit out, it matches.
  assert.equal(await rankOf(page, "Rocket", "", "rockit"), FUZZY,
    "a near miss with the same opening was not tolerated");
  // And words with nothing in common find nothing on the page at all.
  await type(page, "zebra");
  assert.equal((await showing(page)).length, 0,
    `unrelated words found cards: ${(await showing(page)).join(", ")}`);
  assert.equal(await page.locator("#settings-search-none").isVisible(), true,
    "an unrelated word did not reach the 'nothing matches' answer");
  await page.close();
});

await check("two words must BOTH be in the same part (AND, not OR)", async () => {
  const page = await open();
  await type(page, "voice");
  const one = await showing(page);
  await type(page, "voice strict");
  const both = await showing(page);
  assert.ok(both.includes("voice"),
    `"voice strict" did not find the Voice card: ${both.join(", ") || "nothing was left showing"}`);
  assert.ok(both.length < one.length,
    `adding a second word did not narrow the page (${both.length} then ${one.length})`);
  // A card holding only ONE of the words must not be drawn: that is OR, and
  // it is what the query used to do when it was compared as one string.
  await type(page, "voice backup");
  assert.ok(!(await showing(page)).includes("voice"),
    "a card with only one of the two words was drawn anyway");
  assert.equal(await rankOf(page, "Your voice", "", "voice backup"), NONE,
    "a word matching once counted for two words of the query");
  assert.equal(await rankOf(page, "Your voice", "a backup of your voice", "voice backup"), DETAIL,
    "both words in the same part did not match");
  await page.close();
});

await check("the tiers still run exact, prefix, near miss, then the detail text", async () => {
  const page = await open();
  const label = "Your voice", body = "a paragraph about the voice print";
  assert.equal(await rankOf(page, label, body, "voice"), EXACT,
    "a word of the heading is not the top tier");
  assert.equal(await rankOf(page, label, body, "voic"), PREFIX,
    "a prefix of a heading word is not the second tier");
  assert.equal(await rankOf(page, label, body, "voise"), FUZZY,
    "a near miss of a heading word is not the third tier");
  assert.equal(await rankOf(page, "", body, "voice"), DETAIL,
    "the detail text is not the floor");
  assert.equal(await rankOf(page, "", body, "voise"), DETAIL,
    "a near miss inside the detail text fell out of the match entirely");
  assert.ok(await rankOf(page, label, body, "voice") > await rankOf(page, "", body, "voice"),
    "a heading match no longer beats a body match");
  await page.close();
});

await check("every case in the SHARED cross-app fixture matches the desktop engine", async () => {
  // The fixture is the contract BETWEEN THE APPS, and this suite is the
  // desktop's side of it. `SettingsSearchTest.kt` runs the same file against
  // the Kotlin engine, so a rule that quietly changes here and not there
  // fails on one side or the other.
  //
  // It exists because the test that does compare the two apps (`SettingsSearchTest`'s
  // "the two apps say the same words about the same box") only compares the
  // eight WORD CONSTANTS - never the matching rules. That gap is how the
  // phone's `word.contains(token)` floor came to match "voice" inside
  // "conversation" while this engine correctly refused to, with every test on
  // both sides still green.
  //
  // Measured, not hand-written: the cases are generated from THIS engine by
  // tools/gen-settings-search-cases.mjs, so the file cannot flatter either side.
  const { rank } = await import("../src/settings-search.js");
  const fixture = JSON.parse(
    readFileSync(join(HERE, "fixtures", "settings-search-cases.json"), "utf8"),
  );
  const wrong = [];
  for (const c of fixture.cases) {
    const parts = Object.entries(fixture.parts).map(([key, p]) => [
      key, rank(p.label, p.text, c.query),
    ]);
    const hits = parts.filter(([, r]) => r > 0).map(([k]) => k).sort();
    if (hits.join(",") !== c.hits.join(",")) {
      wrong.push(`"${c.query}": expected [${c.hits.join(", ")}] but got [${hits.join(", ")}]`);
    }
  }
  assert.equal(wrong.length, 0, `the desktop engine drifted from the shared fixture:\n      ${wrong.join("\n      ")}`);
  // And the fixture pins the budget table itself, so a change to it is a change
  // to both apps at once rather than one.
  for (const [len, want] of Object.entries(fixture.budget)) {
    const { fuzzyBudget } = await import("../src/settings-search.js");
    assert.equal(fuzzyBudget("x".repeat(Number(len))), want,
      `fuzzyBudget for ${len} letters is no longer ${want}`);
  }
});

await browser.close(); close();
console.log(fails.length ? `\n${fails.length} FAILED` : "\nsettings search filters, explains and restores");
process.exit(fails.length ? 1 : 0);
