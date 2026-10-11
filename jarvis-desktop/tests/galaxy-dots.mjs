/**
 * The Galaxy in the REAL Brain window: every dot is a button you can Tab to.
 *
 *     node tests/galaxy-dots.mjs
 *
 * `tests/galaxy-constellation.mjs` checks the module with no browser;
 * `tests/galaxy-button-engine.mjs` proves a dot is focusable and clickable on a
 * bare page. This is the one that matters to the owner: the actual window,
 * wired up, with the real graph.
 *
 *  - the drawing and the controls are one per name, and they agree;
 *  - one Tab stop per dot, in the picture's own order - and a dot the legend has
 *    FILTERED OUT leaves the tab order with its button;
 *  - Enter opens the same panel a click opens, with the name the button
 *    announced, so what a screen reader hears and what appears cannot differ;
 *  - a drag that ends on a dot pans instead of selecting it;
 *  - the drawing is `aria-hidden`, because the buttons already say all of it;
 *  - and the panel's own controls keep working with the picture behind them.
 *    That last one is not hypothetical: the stage's pointerup handler once wiped
 *    the panel on every click of one of the panel's buttons, because it treated
 *    "not a dot button" as "empty space". The stack trace read
 *    `select(null) <- pointerup <- the row button's click`.
 */
import assert from "node:assert/strict";
import * as K from "./uikit.mjs";

const { base, close } = await K.serve();
const browser = await K.launch();
const ENTITIES = K.makeEntities();

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/** The words behind Priya's dots, so the panel has rows to render. `makeEntities`
 *  names fact ids 10-14 for her, and `memory_used` reads this map. Without it the
 *  panel correctly says "No facts to show." and there is nothing to click. */
const USED = {
  10: { id: 10, text: "Priya loves jazz", current: true, pinned: true, created: 1790000000, valid_to: null, erased_at: null },
  11: { id: 11, text: "Priya likes tea", current: true, pinned: false, created: 1789900000, valid_to: null, erased_at: null },
  12: { id: 12, text: "Priya lives in Leeds", current: true, pinned: false, created: 1789800000, valid_to: null, erased_at: null },
  13: { id: 13, text: "Priya is my sister", current: true, pinned: false, created: 1789700000, valid_to: null, erased_at: null },
  14: { id: 14, text: "Priya runs on Tuesdays", current: true, pinned: false, created: 1789600000, valid_to: null, erased_at: null },
};

async function galaxy() {
  const page = await K.open(browser, base, "brain.html",
    { brain: { ...K.BRAIN, memory_entities: ENTITIES } }, { width: 1200, height: 900 });
  await page.evaluate((s) => Object.assign(window, s), { __usedFacts: USED });
  await page.waitForTimeout(400);
  await page.locator("#rail-advanced-toggle").click();
  await page.locator("#tab-galaxy").click();
  await page.waitForTimeout(2200);
  return page;
}

await check("one button per drawn name, and one dot per button", async () => {
  const page = await galaxy();
  const buttons = await page.locator("#graph-overlay .galaxy-node-button").count();
  const dots = await page.locator("#graph-svg circle.galaxy-node-shape").count();
  const links = await page.locator("#graph-svg line.galaxy-link").count();
  const stat = await page.locator("#graph-stat").innerText();
  await page.close();
  assert.match(stat, new RegExp(`^${ENTITIES.entities.length} names`), stat);
  assert.equal(buttons, ENTITIES.entities.length, `expected a button per name, found ${buttons}`);
  assert.equal(dots, buttons, "a dot with no button, or a button with no dot");
  assert.ok(links > 0, "no links were drawn");
});

await check("the picture is decoration: hidden from screen readers, and it does not eat clicks", async () => {
  const page = await galaxy();
  const svgHidden = await page.locator("#graph-svg").getAttribute("aria-hidden");
  const svgEvents = await page.locator("#graph-svg").evaluate((el) => getComputedStyle(el).pointerEvents);
  await page.close();
  assert.equal(svgHidden, "true", "the drawing is read out as well as the buttons");
  assert.equal(svgEvents, "none", "the drawing swallows clicks meant for the button on top of it");
});

await check("Tab reaches a dot, and Enter opens the panel for the name it announced", async () => {
  const page = await galaxy();
  const first = page.locator("#graph-overlay .galaxy-node-button").first();
  const announced = await first.getAttribute("aria-label");
  const name = announced.split(",")[0];
  await first.focus();
  const focused = await page.evaluate(() => document.activeElement?.getAttribute("aria-label"));
  assert.equal(focused, announced, "focus did not land on the dot");
  await page.keyboard.press("Enter");
  await page.waitForTimeout(300);
  const title = await page.locator("#node-label").innerText();
  const inspector = await page.locator("#inspector").isVisible();
  await page.close();
  assert.ok(inspector, "Enter on a dot opened nothing");
  assert.equal(title, name, `the button said "${announced}" and the panel says "${title}"`);
});

await check("every dot is its own Tab stop, in the picture's own order", async () => {
  const page = await galaxy();
  const labels = await page.locator("#graph-overlay .galaxy-node-button")
    .evaluateAll((els) => els.map((e) => e.getAttribute("aria-label")));
  await page.locator("#graph-overlay .galaxy-node-button").first().focus();
  const seen = [];
  for (let i = 0; i < 4; i++) {
    seen.push(await page.evaluate(() => document.activeElement?.getAttribute("aria-label")));
    await page.keyboard.press("Tab");
  }
  await page.close();
  assert.deepEqual(seen, labels.slice(0, 4), `Tab order was ${JSON.stringify(seen)}`);
});

await check("a dot the legend has filtered out leaves the Tab order with its button", async () => {
  const page = await galaxy();
  const pet = page.locator("#legend .legend-item", { hasText: /pets/i }).first();
  const before = await page.locator("#graph-overlay .galaxy-node-button:not([hidden])").count();
  await pet.click();
  await page.waitForTimeout(300);
  const after = await page.locator("#graph-overlay .galaxy-node-button:not([hidden])").count();
  const hiddenDots = await page.locator("#graph-svg .galaxy-node[hidden]").count();
  await page.close();
  assert.ok(after < before, `filtering out pets left every button: ${before} -> ${after}`);
  assert.ok(hiddenDots > 0, "the button went but its dot stayed on the picture");
});

await check("a drag that ends on a dot pans instead of selecting it", async () => {
  const page = await galaxy();
  const box = await page.locator("#graph-overlay .galaxy-node-button:not([hidden])").first().boundingBox();
  const statBefore = await page.locator("#graph-stat").innerText();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + 40, box.y + box.height / 2 + 30, { steps: 5 });
  await page.mouse.up();
  await page.waitForTimeout(300);
  const inspector = await page.locator("#inspector").isVisible();
  const statAfter = await page.locator("#graph-stat").innerText();
  await page.close();
  assert.equal(inspector, false, "a drag across a dot selected it");
  assert.equal(statAfter, statBefore);
});

await check("clicking a dot with the pointer selects it, as Enter does", async () => {
  const page = await galaxy();
  const second = page.locator("#graph-overlay .galaxy-node-button").nth(1);
  const announced = await second.getAttribute("aria-label");
  const name = announced.split(",")[0];
  await second.click();
  await page.waitForTimeout(300);
  const title = await page.locator("#node-label").innerText();
  await page.close();
  assert.equal(title, name, `clicking "${name}" opened the panel for "${title}"`);
});

await check("the panel's own controls still work with the picture behind them", async () => {
  const page = await galaxy();
  await page.fill("#graph-search", "Priya");
  await page.waitForTimeout(700);
  const rows = await page.locator("#galaxy-facts-list li").count();
  assert.ok(rows > 0, "the search opened no facts to click");
  await page.locator("#galaxy-facts-list li").first()
    .getByRole("button", { name: "Open in Memory" }).click({ timeout: 8000 });
  await page.waitForTimeout(600);
  const out = await page.evaluate(() => ({
    title: document.getElementById("memory-about-title").textContent,
    memoryVisible: !document.getElementById("view-memory").hidden,
  }));
  await page.close();
  assert.ok(out.memoryVisible, "the panel's own button did nothing - the click was swallowed");
  assert.match(out.title, /Priya/, `the About page opened as "${out.title}"`);
});

await check("the drawing matches the buttons: a filtered-out name has neither", async () => {
  const page = await galaxy();
  const pairs = await page.evaluate(() => {
    const buttons = [...document.querySelectorAll("#graph-overlay .galaxy-node-button")]
      .map((b) => b.getAttribute("data-node"));
    const dots = [...document.querySelectorAll("#graph-svg .galaxy-node")]
      .map((g) => g.getAttribute("data-node"));
    return { buttons: buttons.sort(), dots: dots.sort() };
  });
  await page.close();
  assert.deepEqual(pairs.buttons, pairs.dots,
    "the buttons and the drawn dots name different sets of nodes");
});

await browser.close();
await close();
console.log(fails.length
  ? `\n${fails.length} failed: ${fails.join(", ")}`
  : "\nin the real window, every dot is a button you can Tab to, and the picture follows it");
process.exit(fails.length ? 1 : 0);
