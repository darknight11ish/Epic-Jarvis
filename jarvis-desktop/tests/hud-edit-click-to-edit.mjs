/**
 * hud-edit-click-to-edit.mjs - Q6 of the owner's UI review (2026-11-09):
 * "Click-to-Select Card Editing - Hide All Card Toolbars Until Clicked".
 *
 *     node tests/hud-edit-click-to-edit.mjs
 *
 * THE OWNER'S DIAGNOSIS: "the UI is clunky and overwhelming a lot, including
 * in the edit hud menu" - every card carried a 7-button engineering toolbar,
 * so 10-15 cards put 70-105 tiny buttons on screen.
 *
 * WHAT THIS PROVES, against the real page in a real Chromium:
 *
 *   - in NORMAL use (body[data-hud-edit="off"]) no card draws a toolbar at all;
 *   - entering Edit HUD still draws NO toolbar, even though every editable card
 *     now wears the dashed outline and the "Click to edit" pill;
 *   - clicking a card's title selects exactly that card and its plain-words
 *     inspector appears - and it is the ONLY inspector on the canvas;
 *   - clicking a different card moves the one inspector there (the first
 *     card's row goes away again);
 *   - the inspector is real: pressing `Compact` (`S`) resizes the selected card
 *     in the layout document, and the pressed pill says so;
 *   - Done leaves edit mode and the canvas is clean again.
 *
 * The source half of these rules is tests/hud-edit.mjs and
 * tests/hud-edit-tabs.mjs; this is the real-page half. Nothing here adds a
 * route, a command, a permission or a dependency.
 *
 * RUNNING IT. Playwright is not a dependency of this package (tests/README.md
 * says why): `npm i -D playwright && npx playwright install chromium` first, or
 * copy an existing install into `node_modules`.
 */
import assert from "node:assert/strict";
import * as K from "./uikit.mjs";
import { SIZES } from "../src/hud-edit.js";

const VIEW = { width: 1600, height: 1000 };
const COMPACT = SIZES.find((size) => size.key === "S");

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (error) { fails.push(name); console.log(`FAIL  ${name}\n      ${error.message}`); }
};

const { base, close } = await K.serve();
const browser = await K.launch();

/** Every card toolbar that is actually painted (a display:none row has no box). */
const drawnToolbars = (page) => page.evaluate(() => [...document.querySelectorAll(".hud-card-tools")]
  .filter((el) => {
    const box = el.getBoundingClientRect();
    return box.width > 1 && box.height > 1;
  })
  .map((el) => {
    const card = el.closest("[data-hud-card]");
    return card ? card.getAttribute("data-hud-card") : "?";
  }));

const selectedIds = (page) => page.evaluate(() => [...document.querySelectorAll("[data-hud-card]")]
  .filter((el) => el.getAttribute("data-hud-edit-selected") === "true")
  .map((el) => el.getAttribute("data-hud-card")));

const cardOf = (page, id) => page.evaluate((cardId) => {
  const card = window.__jarvisHudEdit.layout.cards.find((entry) => entry.id === cardId);
  return card ? { col_span: card.col_span, row_span: card.row_span, visible: card.visible } : null;
}, id);

async function openHud() {
  const page = await K.open(browser, base, "jarvis_hud.html", {}, VIEW);
  await page.waitForSelector("#hud-edit-toggle", { timeout: 10000 });
  await page.waitForFunction(() => Boolean(window.__jarvisHudEdit), null, { timeout: 10000 });
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(String(error)));
  page.__pageErrors = pageErrors;
  return page;
}

await check("Q6: normal use draws zero per-card toolbars", async () => {
  const page = await openHud();
  try {
    assert.equal(await page.evaluate(() => document.body.getAttribute("data-hud-edit")), "off");
    assert.deepEqual(await drawnToolbars(page), [],
      "a per-card toolbar is painted before Edit HUD is even on");
  } finally {
    await page.close();
  }
});

await check("Q6: entering Edit HUD still draws no toolbar until a card is clicked", async () => {
  const page = await openHud();
  try {
    await page.click("#hud-edit-toggle");
    await page.waitForFunction(() => document.body.getAttribute("data-hud-edit") === "on",
      null, { timeout: 10000 });
    await page.waitForTimeout(200);
    assert.deepEqual(await drawnToolbars(page), [],
      "Edit HUD is a wall of toolbars again - no card has been clicked yet");
    assert.deepEqual(await selectedIds(page), [], "a card was selected without a click");
    // Every editable card says what a click does, and outlines itself.
    const cards = await page.evaluate(() => [...document.querySelectorAll("[data-hud-card]")]
      .map((card) => {
        const style = getComputedStyle(card);
        const pill = card.querySelector(".hud-card-edit-pill");
        return {
          id: card.getAttribute("data-hud-card"),
          border: style.borderTopStyle,
          pill: pill ? pill.textContent : null,
        };
      }));
    assert.ok(cards.length >= 8, `only ${cards.length} card shells were drawn`);
    for (const card of cards) {
      assert.ok(card.border === "dashed" || card.border === "dotted",
        `${card.id} has no dashed edit outline (border-top-style is ${card.border})`);
      assert.equal(card.pill, "Click to edit", `${card.id} does not offer "Click to edit"`);
    }
  } finally {
    await page.close();
  }
});

await check("Q6: a click selects exactly that card and draws its ONE inspector", async () => {
  const page = await openHud();
  try {
    await page.click("#hud-edit-toggle");
    await page.waitForFunction(() => document.body.getAttribute("data-hud-edit") === "on",
      null, { timeout: 10000 });
    await page.waitForTimeout(200);
    await page.locator('[data-hud-card="nav"] .hud-card-title').click();
    await page.waitForTimeout(250);
    assert.deepEqual(await selectedIds(page), ["nav"],
      `the click did not select exactly the Navigation card: ${JSON.stringify(await selectedIds(page))}`);
    assert.deepEqual(await drawnToolbars(page), ["nav"],
      `the inspector is not the selected card's alone: ${JSON.stringify(await drawnToolbars(page))}`);

    // A second click moves the one inspector; the first card's row is put away.
    await page.locator('[data-hud-card="waiting"] .hud-card-title').click();
    await page.waitForTimeout(250);
    assert.deepEqual(await selectedIds(page), ["waiting"],
      "clicking another card did not move the selection");
    assert.deepEqual(await drawnToolbars(page), ["waiting"],
      `two inspectors are drawn at once: ${JSON.stringify(await drawnToolbars(page))}`);
  } finally {
    await page.close();
  }
});

await check("Q6: the one inspector is real - Compact resizes the selected card", async () => {
  const page = await openHud();
  try {
    await page.click("#hud-edit-toggle");
    await page.waitForFunction(() => document.body.getAttribute("data-hud-edit") === "on",
      null, { timeout: 10000 });
    await page.waitForTimeout(200);
    await page.locator('[data-hud-card="nav"] .hud-card-title').click();
    await page.waitForTimeout(250);
    const before = await cardOf(page, "nav");
    assert.notEqual(before.col_span, COMPACT.col_span, "the card is already the size under test");
    await page.locator('[data-hud-card="nav"] [data-hud-edit-size="S"]').click();
    await page.waitForTimeout(300);
    assert.equal((await cardOf(page, "nav")).col_span, COMPACT.col_span,
      "the selected card's Compact pill did not resize it");
    assert.equal(await page.evaluate(() => document.querySelector(
      '[data-hud-card="nav"] [data-hud-edit-size="S"]').getAttribute("aria-pressed")), "true",
      "the pressed pill does not say which size the card is on");
    // Done is still the one loud way out, and normal use is clean again.
    await page.click("#hud-edit-done");
    await page.waitForFunction(() => document.body.getAttribute("data-hud-edit") === "off",
      null, { timeout: 10000 });
    await page.waitForTimeout(200);
    assert.deepEqual(await drawnToolbars(page), [], "a toolbar survived leaving Edit HUD");
  } finally {
    await page.close();
  }
});

await browser.close();
if (close) await close();

console.log(`\n${fails.length ? `${fails.length} failed` : "all passed"}`);
if (fails.length) { console.log(`failed: ${fails.join(", ")}`); process.exit(1); }
