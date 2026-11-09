/**
 * hud-edit-select.mjs - in Edit HUD, a first click on the main screen SELECTS,
 * it never performs.
 *
 *     node tests/hud-edit-select.mjs
 *
 * THE OWNER'S REPORT (2026-11-09, with a screenshot of Edit HUD): "in the edit
 * HUD, when i click on any part including the left column icons, there should
 * be the edit options that appear. right now when i click on it it just opens
 * the icon's intended menu."
 *
 * WHAT THIS PROVES, on the real page in a real Chromium:
 *
 *   (a) entering Edit HUD and clicking a LEFT-RAIL icon (the Navigation card's
 *       Talk/Brain buttons) selects that card - the Cards tab names it and the
 *       card shell carries the selected state - and does NOT switch the view,
 *       so the icon's intended screen never opened;
 *   (b) clicking a BUTTON drawn inside another card (the Focus presets card's
 *       Cloud button) selects that card and leaves the button un-pressed, so
 *       no card performs its real action from a first click;
 *   (c) the left column's own toolbar icon (Presets) selects the Navigation
 *       card and does NOT open the Presets menu;
 *   (d) the editor's own controls still work: a card's size button resizes it
 *       and Undo puts it back, and Done leaves edit mode - after which the same
 *       left-rail icon click DOES act exactly as before;
 *   (e) dragging a card by its handle still moves it between regions;
 *   (f) EVERY visible left-column icon that is not itself a card (Presets,
 *       Live, Faces, Galaxy options, the Studio dock, the injected settings
 *       gear) selects Navigation and opens nothing.
 *
 * The pure half (the card/DOM map, the source pins for the interception) is
 * tests/hud-edit.mjs; this is the real-page half. No new route, command,
 * permission or dependency is involved: the page stays offline and this suite
 * is served from `src/` exactly as tests/hud.mjs serves it.
 *
 * RUNNING IT. Playwright is not a dependency of this package (tests/README.md
 * says why): `npm i -D playwright && npx playwright install chromium` first, or
 * copy an existing install into `node_modules`.
 */
import assert from "node:assert/strict";
import * as K from "./uikit.mjs";
import { SIZES } from "../src/hud-edit.js";

const VIEW = { width: 1600, height: 1000 };
const SMALL = SIZES.find((size) => size.key === "S");

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (error) { fails.push(name); console.log(`FAIL  ${name}\n      ${error.message}`); }
};

const { base, close } = await K.serve();
const browser = await K.launch();

/** The page with Edit HUD on, the way the owner enters it. */
async function openEdit() {
  const page = await K.open(browser, base, "jarvis_hud.html", {}, VIEW);
  await page.waitForSelector("#hud-edit-toggle", { timeout: 10000 });
  await page.waitForFunction(() => Boolean(window.__jarvisHudEdit), null, { timeout: 10000 });
  assert.equal(await page.locator("#hud-edit-toggle").innerText(), "Edit HUD",
    "the toggle is not offering Edit HUD before edit mode");
  await page.click("#hud-edit-toggle");
  await page.waitForFunction(() => document.body.getAttribute("data-hud-edit") === "on",
    null, { timeout: 10000 });
  await page.waitForTimeout(200);
  // K.open's harness stubs the Tauri IPC but not every REST read, so its
  // __errors list carries this page's expected 404s. What a click must not do
  // is throw: only real JavaScript exceptions are collected here.
  const pageErrors = [];
  page.on('pageerror', (error) => pageErrors.push(String(error)));
  page.__pageErrors = pageErrors;
  return page;
}

/** The id of the ONE card shell painted as selected, or null. */
const selectedCard = (page) => page.evaluate(() => {
  const shell = [...document.querySelectorAll("[data-hud-card]")]
    .find((node) => node.getAttribute("data-hud-edit-selected") === "true");
  return shell ? shell.getAttribute("data-hud-card") : null;
});

/** The Cards tab's options line for the selected card. */
const optionsWords = (page) => page.evaluate(() => {
  const pane = document.getElementById("hud-edit-card-controls");
  return pane ? pane.textContent : "";
});

const viewState = (page) => page.evaluate(() => ({
  talkOn: document.getElementById("talk").classList.contains("on"),
  brainOn: document.getElementById("brain").classList.contains("on"),
  talkSelected: document.querySelector('#rail-nav [data-view="talk"]').getAttribute("aria-selected"),
  brainSelected: document.querySelector('#rail-nav [data-view="brain"]').getAttribute("aria-selected"),
  title: document.getElementById("stage-title").textContent,
}));

/* (a) + (c): a left-rail icon selects its card, never switches the screen,
 * then Done gives the icon its action back. */
await check("(a) in Edit HUD a left-rail icon selects the Navigation card and does not switch away", async () => {
  const page = await openEdit();
  const before = await viewState(page);
  assert.equal(before.talkOn, true, "the page did not start on the Talk view");
  await page.click('#rail-nav [data-view="brain"]');
  await page.waitForTimeout(200);
  assert.equal(await selectedCard(page), "nav", "the Navigation card was not selected");
  assert.match(await optionsWords(page), /Options for Navigation/,
    `the options rail does not name the selected card: ${await optionsWords(page)}`);
  assert.equal(await page.evaluate(() => document.body.getAttribute("data-hud-edit-tab")),
    "cards", "the Cards tab did not open for the selection");
  const after = await viewState(page);
  assert.deepEqual(after, before,
    `the Brain icon still switched the view in Edit HUD: ${JSON.stringify(after)}`);
  assert.deepEqual(page.__pageErrors, [], `the page threw: ${page.__pageErrors}`);
  await page.close();
});

await check("(c) the left column's own Presets icon selects Navigation and opens no menu", async () => {
  const page = await openEdit();
  assert.equal(await page.evaluate(() => document.getElementById("rail-presets") !== null), true,
    "the left column has no Presets icon to test");
  await page.click("#rail-presets");
  await page.waitForTimeout(200);
  assert.equal(await selectedCard(page), "nav", "the Presets icon did not select Navigation");
  assert.match(await optionsWords(page), /Options for Navigation/,
    `the options rail does not name Navigation: ${await optionsWords(page)}`);
  assert.equal(await page.evaluate(
    () => Boolean(document.getElementById("hud-presets-menu"))), false,
  "the Presets menu opened in Edit HUD instead of selecting a card");
  assert.equal(await page.evaluate(
    () => document.getElementById("rail-presets").getAttribute("aria-expanded")), "false",
  "the Presets icon announced an open menu in Edit HUD");
  assert.deepEqual(page.__pageErrors, [], `the page threw: ${page.__pageErrors}`);
  await page.close();
});

/* (b): a button drawn inside another card selects that card, and does not act. */
await check("(b) a button inside another card selects it and does not press it", async () => {
  const page = await openEdit();
  assert.equal(await page.evaluate(() => Boolean(document.querySelector("#preset-cloud"))), true,
    "the Focus presets card has no Cloud button to test");
  assert.equal(await page.locator("#preset-cloud").getAttribute("aria-pressed"), "false",
    "the Cloud button did not start un-pressed");
  await page.click("#preset-cloud");
  await page.waitForTimeout(200);
  assert.equal(await selectedCard(page), "lanes", "the Focus presets card was not selected");
  assert.match(await optionsWords(page), /Options for Focus presets/,
    `the options rail does not name the selected card: ${await optionsWords(page)}`);
  assert.equal(await page.locator("#preset-cloud").getAttribute("aria-pressed"), "false",
    "the Cloud button still performed its own action in Edit HUD");
  assert.deepEqual(page.__pageErrors, [], `the page threw: ${page.__pageErrors}`);
  await page.close();
});

/* (d): the editor's own controls keep working, and Done gives the page back. */
await check("(d) the card toolbar and Undo still work, and Done makes the icon act again", async () => {
  const page = await openEdit();
  await page.click('#rail-nav [data-view="talk"]');
  await page.waitForTimeout(200);
  assert.equal(await selectedCard(page), "nav", "the Navigation card was not selected");
  const sized = await page.evaluate(() => window.__jarvisHudEdit.layout.cards
    .find((card) => card.id === "nav"));
  assert.notEqual(sized.col_span, SMALL.col_span, "the card already had the size under test");
  // The selected card's toolbar is moved into the bar; the S button is real.
  await page.click('#hud-edit-card-controls [data-hud-edit-size="S"]');
  await page.waitForTimeout(200);
  assert.equal(await page.evaluate(() => window.__jarvisHudEdit.layout.cards
    .find((card) => card.id === "nav").col_span), SMALL.col_span,
  "the selected card's S button did not resize it in Edit HUD");
  await page.click("#hud-edit-undo");
  await page.waitForTimeout(200);
  assert.equal(await page.evaluate(() => window.__jarvisHudEdit.layout.cards
    .find((card) => card.id === "nav").col_span), sized.col_span,
  "Undo did not put the size back in Edit HUD");
  await page.click("#hud-edit-done");
  await page.waitForFunction(() => document.body.getAttribute("data-hud-edit") === "off",
    null, { timeout: 10000 });
  await page.waitForTimeout(200);
  await page.click('#rail-nav [data-view="brain"]');
  await page.waitForTimeout(250);
  const after = await viewState(page);
  assert.equal(after.brainSelected, "true", "the Brain icon did not act after Done");
  assert.equal(after.talkSelected, "false", "the Talk icon stayed selected after Done");
  assert.equal(after.title, "Brain map", "the Brain screen did not open after Done");
  assert.deepEqual(page.__pageErrors, [], `the page threw: ${page.__pageErrors}`);
  await page.close();
});

/* (e): the drag path is pointerdown/pointermove/pointerup, not click. */
await check("(e) dragging a card's handle still moves it between regions", async () => {
  const page = await openEdit();
  const drag = await page.evaluate(() => {
    const card = document.querySelector('[data-hud-card="waiting"]');
    const handle = card && card.querySelector("[data-hud-card-handle]");
    const region = document.querySelector('[data-hud-region="stage_top"]');
    if (!handle || !region) return null;
    const h = handle.getBoundingClientRect();
    const r = region.getBoundingClientRect();
    return {
      id: card.getAttribute("data-hud-card"),
      before: window.__jarvisHudEdit.layout.cards
        .find((entry) => entry.id === "waiting").region,
      from: { x: h.x + h.width / 2, y: h.y + h.height / 2 },
      to: { x: r.x + r.width / 2, y: r.y + 4 },
    };
  });
  assert.ok(drag, "the Waiting card or the stage-top region is missing");
  assert.notEqual(drag.before, "stage_top", "the Waiting card already starts in stage top");
  assert.ok(drag.from.y > 0 && drag.from.x > 0, "the Waiting card's drag handle is not on screen");
  await page.mouse.move(drag.from.x, drag.from.y);
  await page.mouse.down();
  await page.mouse.move(drag.to.x, drag.to.y, { steps: 8 });
  await page.mouse.up();
  await page.waitForTimeout(700);
  const after = await page.evaluate((id) => window.__jarvisHudEdit.layout.cards
    .find((entry) => entry.id === id).region, drag.id);
  assert.equal(after, "stage_top", `dragging ${drag.id} did not move it to stage top`);
  assert.deepEqual(page.__pageErrors, [], `the page threw: ${page.__pageErrors}`);
  await page.close();
});

/* (f): every left-column icon that is NOT a card of its own. */
const iconState = (page) => page.evaluate(() => ({
  talkOn: document.getElementById("talk").classList.contains("on"),
  brainOn: document.getElementById("brain").classList.contains("on"),
  title: document.getElementById("stage-title").textContent,
  tab: document.body.getAttribute("data-hud-tab") || "",
  presets: Boolean(document.getElementById("hud-presets-menu")),
  galaxy: (() => {
    const panel = document.getElementById("galaxy-options");
    return panel ? panel.getBoundingClientRect().height > 1 : false;
  })(),
  live: (() => {
    const live = document.getElementById("rail-live");
    return live ? live.getAttribute("aria-pressed") : null;
  })(),
}));

await check("(f) every visible left-column icon selects Navigation and opens nothing", async () => {
  const page = await openEdit();
  const icons = await page.evaluate(() => [...document.querySelectorAll(".rail.left button")]
    .filter((button) => !button.closest("[data-hud-card]"))
    .filter((button) => {
      const box = button.getBoundingClientRect();
      const style = getComputedStyle(button);
      return box.width > 1 && box.height > 1 && style.display !== "none"
        && style.visibility !== "hidden";
    })
    .map((button) => {
      const id = button.id;
      const choice = button.getAttribute("data-hud-tab-choice");
      return {
        id: id || `dock-${choice}`,
        selector: id
          ? `#${CSS.escape(id)}`
          : `.rail.left [data-hud-tab-choice="${CSS.escape(choice || "")}"]`,
        expanded: button.getAttribute("aria-expanded"),
        pressed: button.getAttribute("aria-pressed"),
      };
    }));
  assert.ok(icons.length >= 4,
    `the left column exposed only ${icons.length} icon(s) to sweep: ${JSON.stringify(icons)}`);
  console.log(`      swept ${icons.length}: ${icons.map((icon) => icon.id).join(", ")}`);
  for (const icon of icons) {
    const before = await iconState(page);
    await page.evaluate((selector) => {
      const button = document.querySelector(selector);
      if (button) button.click();
    }, icon.selector);
    await page.waitForTimeout(120);
    const after = await iconState(page);
    assert.equal(await selectedCard(page), "nav",
      `${icon.id} did not select the Navigation card`);
    assert.match(await optionsWords(page), /Options for Navigation/,
      `${icon.id} did not open Navigation's options`);
    assert.deepEqual(after, before, `${icon.id} performed its own action in Edit HUD`);
    const own = await page.evaluate((selector) => {
      const button = document.querySelector(selector);
      return {
        expanded: button ? button.getAttribute("aria-expanded") : null,
        pressed: button ? button.getAttribute("aria-pressed") : null,
      };
    }, icon.selector);
    assert.equal(own.expanded, icon.expanded, `${icon.id} announced an opened menu`);
    assert.equal(own.pressed, icon.pressed, `${icon.id} changed its own pressed state`);
    assert.deepEqual(page.__pageErrors, [], `${icon.id} threw: ${page.__pageErrors}`);
  }
  await page.close();
});

await browser.close();
close();

console.log(`\n${fails.length ? `${fails.length} failed` : "all passed"}`);
if (fails.length) { console.log(`failed: ${fails.join(", ")}`); process.exit(1); }
