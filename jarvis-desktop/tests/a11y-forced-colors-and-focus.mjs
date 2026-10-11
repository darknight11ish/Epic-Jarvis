/**
 * Two desktop accessibility fixes of 2026-10-09 (Phase H of
 * docs/HANDOFF-UI-RESEARCH-2026-10-09.md and its §11 addendum), asserted
 * rather than promised.
 *
 *  1. `brain.css` had no Windows high-contrast (`forced-colors`) block, while
 *     style.css, widget.css and settings.css all had one (finding D6,
 *     2026-10-05). In the system's own palette the Brain's buttons, fields and
 *     focus rings lost their edges, and the colours that ARE the data - the
 *     Galaxy legend's kind swatches, the link pill's state dot, the Now face -
 *     were repainted to the page background.
 *
 *  2. Toggling a switch in Settings' "Show or hide menus" list rebuilt the
 *     whole list with `container.innerHTML = ""`, and every rebuilt row is a
 *     NEW element - so the keyboard fell onto `<body>` after every single flip.
 *
 * The first half is source-level (no browser): the shape of a media block is a
 * fact about the file. The second drives the real page, because "focus was put
 * back" is a claim only a DOM can answer.
 *
 * Run alone. This suite is one Playwright run, and two at once in this sandbox
 * produce false failures.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import * as K from "./uikit.mjs";

const SRC = join(dirname(fileURLToPath(import.meta.url)), "..", "src");
const read = (f) => readFileSync(join(SRC, f), "utf8");

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

/* ── 1. brain.css's forced-colors block ────────────────────────────────── */

/** The body of `brain.css`'s forced-colors block, plus the file around it. */
function forcedColors(css) {
  const at = css.indexOf("@media (forced-colors: active)");
  assert.ok(at >= 0, "brain.css has no `@media (forced-colors: active)` block");
  const open = css.indexOf("{", at);
  let depth = 0;
  let i = open;
  for (; i < css.length; i++) {
    if (css[i] === "{") depth += 1;
    else if (css[i] === "}") {
      depth -= 1;
      if (depth === 0) break;
    }
  }
  assert.equal(depth, 0, "the forced-colors block is never closed");
  return { body: css.slice(open + 1, i), rest: css.slice(0, at) + css.slice(i + 1) };
}

const strip = (s) => s.replace(/\/\*[\s\S]*?\*\//g, "");

/** Every rule inside a block, as { selector, declarations }. */
function rules(body) {
  const out = [];
  for (const chunk of strip(body).split("}")) {
    const open = chunk.indexOf("{");
    if (open < 0) continue;
    out.push({ sel: chunk.slice(0, open).trim(), decls: chunk.slice(open + 1) });
  }
  return out;
}

await check("brain.css keeps control edges and focus rings under forced colors", () => {
  const { body, rest } = forcedColors(read("brain.css"));
  assert.match(
    body,
    /border:\s*1px solid ButtonText/,
    "a control whose edge is a tinted fill, `border: none` or transparent needs an explicit border"
  );
  assert.match(
    body,
    /outline:\s*2px solid Highlight/,
    "no forced-colors focus ring: the `--focus-ring` token would be repainted into the surface"
  );
  assert.match(
    body,
    /#graph-canvas:focus-visible\s*\{[^}]*outline-offset:\s*-3px/,
    "the canvas takes focus, so its ring has to keep going inside or a full-bleed element clips it"
  );
  assert.doesNotMatch(
    strip(rest),
    /forced-color-adjust/,
    "`forced-color-adjust` belongs inside the forced-colors block and nowhere else"
  );
});

await check("colour is frozen only where colour IS the data", () => {
  // The three things on this page whose colour carries the meaning. Anything
  // else - ordinary text, buttons, fields, the state words on `.row-tag` -
  // must keep the system's own colours, or the reader loses the palette they
  // chose for a reason.
  const DATA = [".legend-swatch", ".link-pill i", ".now-face"];
  const frozen = rules(forcedColors(read("brain.css")).body).filter((r) =>
    /forced-color-adjust\s*:/.test(r.decls)
  );
  assert.ok(
    frozen.length > 0,
    "nothing keeps its colour, so the legend swatches and the state dots are repainted"
  );
  const selectors = [];
  for (const r of frozen) {
    assert.match(
      r.decls,
      /forced-color-adjust:\s*none/,
      "`auto` would still repaint the value that IS the data"
    );
    for (const s of r.sel.split(",")) selectors.push(s.trim().replace(/\s+/g, " "));
  }
  assert.deepEqual(
    selectors.slice().sort(),
    DATA.slice().sort(),
    `only ${DATA.join(", ")} may keep author colours`
  );
});

/* ── 2. The menu list keeps the keyboard ───────────────────────────────── */

const { base, close } = await K.serve();
const browser = await K.launch();

await check("toggling a menu switch leaves the keyboard on that switch", async () => {
  const page = await K.open(browser, base, "settings.html", {}, { width: 900, height: 1200 });

  // A switch in the middle of the list, not the first: a restore that only
  // ever worked for the top row would still pass on row one.
  const before = await page.evaluate(() => {
    const list = document.getElementById("menu-visibility-list");
    const inputs = [...list.querySelectorAll('input[type="checkbox"]')];
    const index = Math.min(4, inputs.length - 1);
    const el = inputs[index];
    el.focus();
    // Keep the element itself: it is how the test tells "the list was rebuilt"
    // from "the toggle did nothing".
    window.__was = el;
    return {
      count: inputs.length,
      index,
      id: el.id,
      checked: el.checked,
      tookFocus: document.activeElement === el,
      countLine: list.querySelector(".menu-count-line").textContent,
    };
  });
  assert.ok(before.count > 5, `the list rendered only ${before.count} switches`);
  assert.ok(
    before.tookFocus,
    `#${before.id} could not take focus - is its card hidden, or the list empty?`
  );

  await page.keyboard.press("Space");
  await K.until(page, "the toggle to rebuild the list", () =>
    page.evaluate(() => window.__was.isConnected === false)
  );

  const after = await page.evaluate((index) => {
    const list = document.getElementById("menu-visibility-list");
    const inputs = [...list.querySelectorAll('input[type="checkbox"]')];
    const el = document.activeElement;
    return {
      tag: el.tagName,
      id: el.id,
      index: inputs.indexOf(el),
      inside: list.contains(el),
      checked: el.checked,
      ariaChecked: el.getAttribute("aria-checked"),
      countLine: list.querySelector(".menu-count-line").textContent,
    };
  }, before.index);

  assert.ok(after.inside, `focus went to <${after.tag}> instead of back to the switch`);
  assert.equal(after.index, before.index, "focus landed on a different switch");
  assert.equal(after.id, before.id, "focus landed on a different switch");
  // The switch really flipped, and its two states agree after the rebuild.
  assert.notEqual(after.checked, before.checked, "Space did not toggle the switch");
  assert.equal(after.ariaChecked, String(after.checked), "aria-checked disagrees with the switch");
  assert.notEqual(
    after.countLine,
    before.countLine,
    "the hidden-count line did not follow the toggle, so the list may not have re-rendered"
  );
  assert.deepEqual(page.__errors, [], page.__errors.join(" | "));
  await page.close();
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} FAILED` : "\nforced-colors and menu-switch focus held");
process.exit(fails.length ? 1 : 0);
