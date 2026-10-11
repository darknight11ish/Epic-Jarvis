/**
 * Does a real browser focus and click the dots?
 *
 *     node tests/galaxy-button-engine.mjs
 *
 * The pure suite proves the module builds the right tree. It cannot prove the
 * tree WORKS, and that is the whole question - which is not a hypothetical:
 *
 *   The first version of `galaxy-constellation.js` put a `<button>` INSIDE the
 *   SVG. It looked correct, the pure suite passed, and in real Chromium it was
 *   **not focusable and never clicked**: Tab skipped past every dot, Enter and
 *   Space did nothing, and Playwright called the element not visible. A picture
 *   of an accessible control, which is precisely the failure this work exists to
 *   prevent. THIS FILE IS WHAT CAUGHT IT, and it is why the buttons are HTML
 *   elements over the drawing rather than shapes inside it.
 *
 * So: build the constellation on a real page, Tab to a dot, press Enter, and
 * check the page heard it. Anything that regresses the "is it really a button"
 * question fails here.
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

const PAGE = `<!doctype html>
<html><head><meta charset="utf-8"><style>
  html, body { margin: 0; background: #04070c; color: #f2f5f8; }
  /* The stage: the drawing and the buttons share one positioned box, which is
     how a button lands exactly on its dot. */
  .galaxy-stage { position: relative; width: 600px; height: 400px; }
  .galaxy-stage svg { position: absolute; inset: 0; width: 100%; height: 100%; }
  .galaxy-overlay { position: absolute; inset: 0; overflow: hidden; }
  .galaxy-node-label { position: absolute; left: 0; top: 0; font: 11px system-ui; color: #f2f5f8; white-space: nowrap; }
  .galaxy-node-button {
    position: absolute; left: 0; top: 0; padding: 0; border: 0; border-radius: 50%;
    background: transparent; cursor: pointer;
  }
  .galaxy-node-button:focus-visible { outline: 2px solid #7df3ff; outline-offset: 2px; }
  .galaxy-node-button.is-selected circle { }
  .galaxy-node-button[hidden] { display: none; }
</style></head>
<body>
  <button id="before">before</button>
  <div class="galaxy-stage">
    <svg id="galaxy" aria-hidden="true"></svg>
    <div class="galaxy-overlay" id="galaxy-overlay"></div>
  </div>
  <button id="after">after</button>
  <script type="module">
    import { buildConstellation } from "./galaxy-constellation.js";
    const nodes = [
      { id: 1, label: "Priya", group: "person", weight: 43, rank: 0, deg: 2, x: 0, y: 0 },
      { id: 2, label: "Lisbon", group: "place", weight: 3, rank: 1, deg: 1, x: 60, y: 40 },
    ];
    const links = [{ s: nodes[0], t: nodes[1] }];
    const view = { x: 120, y: 100, scale: 1 };
    const m = {
      nodes, links, focus: null, hidden: () => false, labels: [],
      translate: (n) => ({ x: n.x * view.scale + view.x, y: n.y * view.scale + view.y }),
      describe: (n) => ({
        x: n.x * view.scale + view.x, y: n.y * view.scale + view.y,
        colour: "var(--node-h1)", shape: { kind: "disc", radius: 8, strokeWidth: 0 },
        label: n.label, dim: false, selected: false, near: false, focusable: true,
      }),
    };
    const host = { svg: document.getElementById("galaxy"), overlay: document.getElementById("galaxy-overlay") };
    window.__built = buildConstellation(host, m, document);
    window.__picked = [];
    for (const [id, entry] of window.__built.buttons) {
      entry.button.addEventListener("click", () => window.__picked.push(id));
    }
  <\/script>
</body></html>`;

async function open() {
  const page = await browser.newPage();
  await page.route("**/galaxy-probe.html", (route) =>
    route.fulfill({ status: 200, contentType: "text/html", body: PAGE }));
  await page.goto(`${base}/galaxy-probe.html`, { waitUntil: "load" });
  await page.waitForTimeout(300);
  return page;
}

await check("CONTROL: the constellation built, one button per name, each with its own dot", async () => {
  const page = await open();
  const buttons = await page.locator(".galaxy-overlay button").count();
  const labels = await page.locator(".galaxy-overlay button")
    .evaluateAll((els) => els.map((e) => e.getAttribute("aria-label")));
  const shapes = await page.locator("#galaxy circle").count();
  await page.close();
  assert.equal(buttons, 2, `expected 2 buttons, found ${buttons}`);
  assert.deepEqual(labels, ["Priya", "Lisbon"]);
  assert.equal(shapes, 2, "each name needs a drawn dot");
});

await check("Tab reaches a dot, and Enter picks it - the thing an SVG button could not do", async () => {
  const page = await open();
  await page.locator("#before").focus();
  await page.keyboard.press("Tab");
  const active = await page.evaluate(() => document.activeElement?.getAttribute("aria-label"));
  assert.equal(active, "Priya",
    `Tab from #before landed on ${JSON.stringify(active)} - the dots are not in the tab order`);
  await page.keyboard.press("Enter");
  await page.waitForTimeout(80);
  const picked = await page.evaluate(() => window.__picked);
  await page.close();
  assert.deepEqual(picked, [1], "Enter on a focused dot did not fire click");
});

await check("Space picks it too, as a button should", async () => {
  const page = await open();
  await page.locator(".galaxy-overlay button").nth(1).focus();
  await page.keyboard.press(" ");
  await page.waitForTimeout(80);
  const picked = await page.evaluate(() => window.__picked);
  await page.close();
  assert.deepEqual(picked, [2], "Space on a focused dot did not fire click");
});

await check("a pointer click picks the dot, and Tab steps to the next one", async () => {
  const page = await open();
  await page.locator(".galaxy-overlay button").first().click();
  await page.waitForTimeout(80);
  const first = await page.evaluate(() => window.__picked);
  await page.locator(".galaxy-overlay button").first().focus();
  await page.keyboard.press("Tab");
  const active = await page.evaluate(() => document.activeElement?.getAttribute("aria-label"));
  await page.close();
  assert.deepEqual(first, [1], "a pointer click did not reach the dot");
  assert.equal(active, "Lisbon", "Tab did not step to the next dot");
});

await check("the dot has a visible focus ring, and the picture is hidden from screen readers", async () => {
  const page = await open();
  await page.locator(".galaxy-overlay button").first().focus();
  const outline = await page.evaluate(() => {
    const el = document.activeElement;
    const cs = getComputedStyle(el);
    return { width: cs.outlineWidth, style: cs.outlineStyle, tag: el.tagName.toLowerCase() };
  });
  // The SVG is the drawing only: a screen reader must hear the buttons, once,
  // and not a second copy of the same picture.
  const svgHidden = await page.locator("#galaxy").getAttribute("aria-hidden");
  await page.close();
  assert.equal(outline.tag, "button");
  assert.notEqual(outline.style, "none", "a focused dot has no visible focus ring");
  assert.equal(svgHidden, "true", "the drawing is exposed to screen readers as well as the buttons");
});

await check("a filtered-out dot leaves the tab order and the accessibility tree", async () => {
  const page = await open();
  await page.evaluate(() => {
    const m = window.__built;
    // Hide the pet group the way the legend does.
    for (const [, entry] of m.buttons) {
      if (entry.node.group === "place") {
        entry.button.hidden = true;
        entry.group.setAttribute("hidden", "");
      }
    }
  });
  await page.locator("#before").focus();
  await page.keyboard.press("Tab");
  const first = await page.evaluate(() => document.activeElement?.getAttribute("aria-label"));
  await page.keyboard.press("Tab");
  const second = await page.evaluate(() => document.activeElement?.id ?? document.activeElement?.tagName);
  await page.close();
  assert.equal(first, "Priya");
  assert.equal(second, "after", "a hidden dot is still in the tab order");
});

await browser.close();
await close();
console.log(fails.length
  ? `\n${fails.length} failed: ${fails.join(", ")}`
  : "\na dot is a real button in a real engine: Tab reaches it, Enter and Space click it, and CSS paints it");
process.exit(fails.length ? 1 : 0);
