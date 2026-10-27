/**
 * hud-galaxy-looks.mjs - the Galaxy's look switcher in the HUD, and the ONE
 * order the owner asked the dock's icons and the stage's words to share.
 *
 *     node tests/hud-galaxy-looks.mjs
 *
 * THE TWO THINGS THIS SUITE EXISTS FOR (the owner, 2026-10-27)
 *
 *   1. "id like an easy way to change the appearance of the jarvis galaxy to
 *      the other models" - and by galaxy they meant "the matrix of ideas and
 *      all sorts of things, not the jarvis face model". So the HUD's own Galaxy
 *      (the #brain view, the one with the Memory / Neural / Unified lenses) has
 *      a look switcher beside those lenses. It lists every look
 *      `galaxy-presets.js` builds - never a planned one, never one it does not
 *      build - and choosing one lays the SAME names out in that look, remembers
 *      the choice on this device under the module's own storage key, and brings
 *      it back on the next load. A stored value that is unknown, stale or
 *      nonsense is the constellation, not a broken picture.
 *   2. "the icons on the left column dontt match the order of teh horizontal
 *      words in the jarvis hud (reminder is out of place for example)" - the
 *      #studio-dock icons and the #stage-tabs words were two different orders.
 *      They are pinned to each other here, in both directions: reorder one and
 *      this fails until the other follows, and a dock icon whose own title no
 *      longer names the word above it fails too.
 *
 * WHAT "APPLIED" MEANS, MEASURED RATHER THAN TRUSTED. For every look the suite
 * reads the page's own layout (`galaxy.lookInfo()`, the seam that exists for
 * this - the same spirit as `budgetInfo()`), the real positions of the dot
 * buttons, and then checks that the picture on screen IS that layout: a
 * least-squares similarity (scale + offset) between the layout's coordinates
 * and the dots' screen centres has to fit to a fraction of a pixel. A label
 * change would not survive that, and neither would a layout that was computed
 * and then not drawn.
 *
 * It also proves the picture is STATIONARY (a flat look must not run the
 * physics) and that the dots cannot overlap once drawn (the layout's own gap,
 * scaled by the camera, still exceeds the drawn dot).
 *
 * The three byte-identical copies of the page are checked here too: this file
 * must never pass against a HUD where only one copy has the switcher.
 */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import * as K from "./uikit.mjs";
import {
  BUILT_PRESETS,
  DEFAULT_PRESET,
  PLANNED_PRESETS,
  PRESET_STORAGE_KEY,
  layoutIsUsable,
} from "../src/galaxy-presets.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");

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

/* ── The page, and the two copies of it that must be identical ──────────── */

const HUD_COPIES = ["src/jarvis_hud.html", "../backend/jarvis_hud.html",
                    "../jarvis-backend/jarvis_hud.html"];
const HUD = read("src/jarvis_hud.html");
const sha = (text) => createHash("sha256").update(text, "utf8").digest("hex");

/** Every `data-hud-tab-choice` in a named element, in the order written. */
function choicesIn(html, id, closeTag) {
  const at = html.indexOf(`id="${id}"`);
  assert.ok(at > -1, `jarvis_hud.html has no #${id}`);
  const end = html.indexOf(closeTag, at);
  assert.ok(end > at, `#${id} has no ${closeTag}`);
  return [...html.slice(at, end).matchAll(/data-hud-tab-choice="([a-z]+)"/g)].map((m) => m[1]);
}

/** The stage tabs as `{ id, word }`, in the order written. */
function stageTabs(html) {
  const at = html.indexOf('id="stage-tabs"');
  assert.ok(at > -1, "jarvis_hud.html has no #stage-tabs");
  const end = html.indexOf("</div>", at);
  return [...html.slice(at, end).matchAll(
    /data-hud-tab-choice="([a-z]+)"[^>]*>([^<]+)<\/button>/g)]
    .map((m) => ({ id: m[1], word: m[2].trim() }));
}

/** The dock buttons as `{ id, title }`, in the order written. */
function dockIcons(html) {
  const at = html.indexOf('id="studio-dock"');
  assert.ok(at > -1, "jarvis_hud.html has no #studio-dock");
  const end = html.indexOf("</nav>", at);
  const block = html.slice(at, end);
  return [...block.matchAll(
    /<button\b[^>]*?data-hud-tab-choice="([a-z]+)"[^>]*?title="([^"]*)"/g)]
    .map((m) => ({ id: m[1], title: m[2] }));
}

/** The layout script's own tab order (`var TABS = [...]`). */
function scriptTabs(html) {
  const m = html.match(/var TABS = \[([^\]]*)\]/);
  assert.ok(m, "the HUD's layout script has no TABS list");
  return [...m[1].matchAll(/"([a-z]+)"/g)].map((x) => x[1]);
}

/* ── 1. the dock's icons and the stage's words are one order ────────────── */

const DOCK = dockIcons(HUD);
const TABS = stageTabs(HUD);

await check("the three copies of the HUD page are byte-identical", async () => {
  const first = sha(HUD);
  for (const path of HUD_COPIES.slice(1)) {
    assert.equal(sha(read(path)), first,
      `${path} is not byte-identical to src/jarvis_hud.html - the page is ` +
      "vendored from one file, and backend/test_base_matches_repo.py fails when they drift");
  }
});

await check("the left column's icons are in the stage's own word order", async () => {
  assert.ok(TABS.length >= 5, `only ${TABS.length} stage tabs were read`);
  assert.deepEqual(DOCK.map((b) => b.id), TABS.map((t) => t.id),
    `the dock draws ${DOCK.map((b) => b.id).join(" > ")} but the words above it read ` +
    `${TABS.map((t) => t.id).join(" > ")} - the owner's complaint of 2026-10-27 ` +
    '("reminder is out of place for example") is exactly this mismatch');
});

await check("every dock icon says the word the stage tab says", async () => {
  DOCK.forEach((button, index) => {
    const word = TABS[index].word.toLowerCase();
    assert.ok(button.title.toLowerCase().startsWith(word),
      `the ${index + 1}th icon is titled "${button.title}", which does not start with ` +
      `"${TABS[index].word}" - the icon and the word above it now describe different things`);
  });
});

await check("the layout script's tab list is the same order too", async () => {
  assert.deepEqual(scriptTabs(HUD), TABS.map((t) => t.id),
    "the layout script's TABS list disagrees with the stage tab bar it selects by");
});

await check("the reorder kept every id, data attribute and the Jarvis bar button", async () => {
  const ids = DOCK.map((b) => b.id);
  assert.equal(new Set(ids).size, ids.length, "a tab choice is named twice in the dock");
  assert.deepEqual([...ids].sort(), TABS.map((t) => t.id).sort(),
    "the dock and the tab bar no longer offer the same set of sections");
  assert.match(HUD, /id="dock-quickbar"/, "the dock's Jarvis bar button was lost");
  // The icons themselves are the page's own glyphs, not new ones.
  for (const glyph of ["&#10022;", "&#10003;", "&#9200;&#xFE0E;", "&#9672;", "&#9637;"]) {
    assert.ok(HUD.includes(glyph), `the dock glyph ${glyph} is gone`);
  }
});

/* ── 2. the switcher, in the real HUD ───────────────────────────────────── */

const { base, close } = await K.serve();
const browser = await K.launch();

/** Everything the page logged that is NOT the harness's own 404 noise. The HUD
 *  asks its backend for a dozen routes and this harness has no backend, so
 *  404/REQFAIL lines are the harness, not the page. */
const realErrors = (page) => (page.__errors || [])
  .filter((line) => !/^(HTTP \d{3}|REQFAIL) /.test(line));

const LOOK_LABEL = new Map([[DEFAULT_PRESET, "Constellation"],
  ...BUILT_PRESETS.map((p) => [p.id, p.label])]);

/** Open the HUD, show the Brain view (the Galaxy), and stop the spin so a flat
 *  look's picture is stationary and square-on before anything is measured. */
async function openGalaxy(pageOptions = {}) {
  const page = await K.open(browser, base, "jarvis_hud.html",
    { pending: [] }, { width: 1200, height: 900, ...pageOptions });
  await page.waitForFunction(() =>
    document.querySelectorAll(".galaxy-node-btn").length > 0, null, { timeout: 15000 });
  await page.locator('[data-view="brain"]').click();
  await page.waitForFunction(() =>
    document.getElementById("galaxy-look").options.length > 0, null, { timeout: 10000 });
  await page.locator("#g-spin").click();          // Pause spin: a still picture
  await page.waitForTimeout(200);
  return page;
}

/** The picture as the page itself knows it: which look, the layout behind it,
 *  and where each dot button really is on screen. */
const picture = (page) => page.evaluate(() => {
  const info = galaxy.lookInfo();
  const dots = [...document.querySelectorAll(".galaxy-node-btn")]
    .filter((b) => !b.hidden)
    .map((b) => {
      const r = b.getBoundingClientRect();
      return {
        id: b.getAttribute("data-galaxy-node"),
        x: r.left + r.width / 2,
        y: r.top + r.height / 2,
      };
    });
  return {
    look: info.look,
    layout: info.layout,
    dots,
    data: document.getElementById("galaxy-counts").getAttribute("data-galaxy-look"),
    switcher: document.getElementById("galaxy-look").value,
    stored: localStorage.getItem("jarvis.galaxy.preset"),
  };
});

/** How well the layout's coordinates explain the dots' screen positions, as a
 *  similarity (screen = k * world + offset): the scale, the worst node's
 *  leftover error in pixels, and the closest two dots on screen. */
function fit(pic) {
  const byId = new Map(pic.dots.map((d) => [d.id, d]));
  const pairs = (pic.layout ? pic.layout.nodes : []).filter((p) => byId.has(p.id));
  let mwx = 0, mwy = 0, msx = 0, msy = 0;
  for (const p of pairs) {
    const d = byId.get(p.id);
    mwx += p.x; mwy += p.y; msx += d.x; msy += d.y;
  }
  mwx /= pairs.length; mwy /= pairs.length;
  msx /= pairs.length; msy /= pairs.length;
  let num = 0, den = 0;
  for (const p of pairs) {
    const d = byId.get(p.id);
    num += (p.x - mwx) * (d.x - msx) + (p.y - mwy) * (d.y - msy);
    den += (p.x - mwx) ** 2 + (p.y - mwy) ** 2;
  }
  const k = den ? num / den : 0;
  let worst = 0;
  for (const p of pairs) {
    const d = byId.get(p.id);
    worst = Math.max(worst, Math.hypot(
      d.x - (msx + k * (p.x - mwx)), d.y - (msy + k * (p.y - mwy))));
  }
  let closest = Infinity;
  for (let i = 0; i < pic.dots.length; i++) {
    for (let j = i + 1; j < pic.dots.length; j++) {
      closest = Math.min(closest, Math.hypot(
        pic.dots[i].x - pic.dots[j].x, pic.dots[i].y - pic.dots[j].y));
    }
  }
  return { pairs: pairs.length, k, worst, closest };
}

async function choose(page, id) {
  await page.selectOption("#galaxy-look", id);
  await page.waitForFunction((want) =>
    document.getElementById("galaxy-counts").getAttribute("data-galaxy-look") === want,
  id, { timeout: 5000 });
  await page.waitForTimeout(200);                 // the overlay follows the canvas
  return picture(page);
}

await check("the Galaxy view has one look switcher, in the search bar beside the lenses", async () => {
  const page = await openGalaxy();
  const where = await page.evaluate(() => {
    const pick = document.getElementById("galaxy-look-pick");
    const select = document.getElementById("galaxy-look");
    const bar = document.querySelector(".brain-search");
    return {
      inBar: Boolean(bar && pick && bar.contains(pick) && bar.contains(select)),
      shown: Boolean(pick) && !pick.hidden,
      lenses: document.querySelectorAll("button[data-galaxy-lens]").length,
      label: select ? select.getAttribute("aria-label") : null,
      dock: Boolean(document.getElementById("studio-dock")),
      canvas: Boolean(document.getElementById("galaxy")),
      overlay: Boolean(document.getElementById("galaxy-overlay")),
    };
  });
  assert.equal(where.inBar, true, "the switcher is not in the Galaxy's own search bar");
  assert.equal(where.shown, true, "the switcher stayed hidden even though the module loaded");
  assert.equal(where.lenses, 3, "the Memory / Neural / Unified lenses are no longer three");
  assert.equal(where.label, "Galaxy look", "the switcher has no accessible name");
  assert.equal(where.canvas, true, "the Galaxy canvas is gone");
  assert.equal(where.overlay, true, "the Galaxy's dot buttons are gone");
  assert.equal(where.dock, true, "the Studio dock is gone");
  assert.deepEqual(realErrors(page), [], `the page logged: ${realErrors(page).join("; ")}`);
  await page.close();
});

await check("it lists every built look and no planned one, in one order", async () => {
  const page = await openGalaxy();
  const options = await page.evaluate(() =>
    [...document.getElementById("galaxy-look").options]
      .map((o) => ({ value: o.value, label: o.textContent })));
  assert.deepEqual(options.map((o) => o.value), [DEFAULT_PRESET, ...BUILT_PRESETS.map((p) => p.id)],
    "the switcher's list is not the module's own list of looks");
  assert.deepEqual(options.map((o) => o.label),
    [DEFAULT_PRESET, ...BUILT_PRESETS.map((p) => p.id)].map((id) => LOOK_LABEL.get(id)),
    "the switcher's words are not the looks' plain names");
  // Nothing may advertise a look that is not built - the five rich ones used to
  // read "not built yet" in the Brain window, and the HUD must not say it either.
  for (const planned of PLANNED_PRESETS) {
    assert.ok(!options.some((o) => o.value === planned.id),
      `the switcher offers "${planned.id}", which the module does not build`);
  }
  const text = await page.locator("#galaxy-look-pick").innerText();
  assert.doesNotMatch(text, /not built/i, `the switcher still says "${text}"`);
  assert.deepEqual(realErrors(page), [], `the page logged: ${realErrors(page).join("; ")}`);
  await page.close();
});

await check("choosing each look really applies that layout to the names on screen", async () => {
  const page = await openGalaxy();
  const before = await picture(page);
  assert.equal(before.look, DEFAULT_PRESET, "the window did not open on the constellation");
  assert.equal(before.layout, null, "the constellation should have no flat layout");
  for (const meta of BUILT_PRESETS) {
    const pic = await choose(page, meta.id);
    assert.equal(pic.look, meta.id, `${meta.id}: the page does not think that look is on`);
    assert.equal(pic.data, meta.id, `${meta.id}: the counts line disagrees`);
    assert.equal(pic.switcher, meta.id, `${meta.id}: the switcher's own value disagrees`);
    assert.ok(pic.layout, `${meta.id}: no layout was placed`);
    assert.equal(pic.layout.id, meta.id, `${meta.id}: the layout says it is ${pic.layout.id}`);
    assert.equal(layoutIsUsable(pic.layout, pic.layout.nodes), true,
      `${meta.id}: the page drew a layout the module's own guard rejects`);
    const shape = fit(pic);
    assert.equal(shape.pairs, pic.layout.nodes.length, `${meta.id}: a name in the layout is not on screen`);
    assert.ok(shape.k > 0.2, `${meta.id}: the picture is not scaled sensibly (k=${shape.k})`);
    // THE POINT: the dots are exactly the layout, up to scale and offset.
    assert.ok(shape.worst < 1.5,
      `${meta.id}: the dots on screen are not the layout (worst node is ${shape.worst.toFixed(2)} px off)`);
    // The layout's own gap survives the camera: the drawn dot is 20 units
    // across, so the centres can never be closer than the gap once scaled.
    assert.ok(shape.closest >= pic.layout.minGap * shape.k * 0.98,
      `${meta.id}: two dots are ${shape.closest.toFixed(1)} px apart, closer than the ` +
      `layout's ${pic.layout.minGap}-unit gap (${(pic.layout.minGap * shape.k).toFixed(1)} px)`);
    // A flat look is a stationary diagram: the physics must not be running.
    const again = await picture(page);
    const moved = again.dots.filter((dot) => {
      const was = pic.dots.find((d) => d.id === dot.id);
      return !was || Math.hypot(dot.x - was.x, dot.y - was.y) > 0.5;
    });
    assert.deepEqual(moved.map((d) => d.id), [],
      `${meta.id}: the picture is still being simulated (${moved.length} of ${pic.dots.length} moved)`);
    console.log(`      ${meta.id}: ${pic.dots.length} names, closest ${shape.closest.toFixed(1)} px, `
      + `fit ${shape.worst.toFixed(2)} px`);
  }
  // Back to the constellation: the physics picture returns, and it moves again.
  const back = await choose(page, DEFAULT_PRESET);
  assert.equal(back.look, DEFAULT_PRESET, "choosing the constellation did not go back");
  assert.equal(back.layout, null, "the constellation kept a flat layout");
  const first = await picture(page);
  await page.waitForTimeout(400);
  const later = await picture(page);
  const still = first.dots.filter((dot) => {
    const was = later.dots.find((d) => d.id === dot.id);
    return was && Math.hypot(dot.x - was.x, dot.y - was.y) > 0.5;
  });
  assert.ok(still.length > 0, "the constellation is not moving again - the physics stayed stopped");
  assert.deepEqual(realErrors(page), [], `the page logged: ${realErrors(page).join("; ")}`);
  await page.close();
});

await check("the choice is remembered on this device and comes back on the next load", async () => {
  const page = await openGalaxy();
  const pic = await choose(page, "radar-dome");
  const stored = await page.evaluate((key) => localStorage.getItem(key), PRESET_STORAGE_KEY);
  assert.equal(stored, "radar-dome", "the choice was not remembered under the module's own key");
  const before = fit(pic);
  await page.reload();
  await page.waitForFunction(() =>
    document.querySelectorAll(".galaxy-node-btn").length > 0, null, { timeout: 15000 });
  await page.locator('[data-view="brain"]').click();
  await page.waitForFunction(() =>
    document.getElementById("galaxy-counts").getAttribute("data-galaxy-look") === "radar-dome",
  null, { timeout: 10000 });
  await page.locator("#g-spin").click();
  await page.waitForTimeout(250);
  const after = await picture(page);
  assert.equal(after.look, "radar-dome", "the saved look did not come back after a reload");
  assert.equal(after.switcher, "radar-dome", "the switcher did not come back on the saved look");
  assert.equal(after.layout.id, "radar-dome", "the saved look came back without its layout");
  const shape = fit(after);
  assert.ok(shape.worst < 1.5, `the restored picture is not the layout (${shape.worst.toFixed(2)} px off)`);
  assert.ok(Math.abs(shape.k - before.k) < 0.2,
    `the restored picture is framed differently (${shape.k.toFixed(2)} vs ${before.k.toFixed(2)})`);
  // The constellation forgets the key, the way the Brain window's does.
  await choose(page, DEFAULT_PRESET);
  assert.equal(await page.evaluate((key) => localStorage.getItem(key), PRESET_STORAGE_KEY), null,
    "the constellation should clear the stored look");
  assert.deepEqual(realErrors(page), [], `the page logged: ${realErrors(page).join("; ")}`);
  await page.close();
});

await check("a stored value that is not a look is the constellation, not a broken page", async () => {
  const page = await openGalaxy();
  for (const junk of ["no-such-look-from-an-older-build", "", "{\"id\":\"nebula\"}"]) {
    await page.evaluate(([key, value]) => localStorage.setItem(key, value),
      [PRESET_STORAGE_KEY, junk]);
    await page.reload();
    await page.waitForFunction(() =>
      document.querySelectorAll(".galaxy-node-btn").length > 0, null, { timeout: 15000 });
    await page.locator('[data-view="brain"]').click();
    await page.waitForTimeout(400);
    const pic = await page.evaluate(() => ({
      look: galaxy.look(),
      data: document.getElementById("galaxy-counts").getAttribute("data-galaxy-look"),
      switcher: document.getElementById("galaxy-look").value,
      layout: galaxy.lookInfo().layout,
      dots: document.querySelectorAll(".galaxy-node-btn").length,
    }));
    assert.equal(pic.look, DEFAULT_PRESET, `stored ${JSON.stringify(junk)} did not fall back`);
    assert.equal(pic.data, DEFAULT_PRESET, `stored ${JSON.stringify(junk)}: the counts line disagrees`);
    assert.equal(pic.switcher, DEFAULT_PRESET, `stored ${JSON.stringify(junk)}: the switcher disagrees`);
    assert.equal(pic.layout, null, `stored ${JSON.stringify(junk)}: a layout was drawn anyway`);
    assert.ok(pic.dots > 0, `stored ${JSON.stringify(junk)}: the picture is empty`);
    const shape = await page.evaluate(() => document.getElementById("galaxy").width > 0);
    assert.equal(shape, true, `stored ${JSON.stringify(junk)}: the canvas has no size`);
    assert.deepEqual(realErrors(page), [], `stored ${JSON.stringify(junk)}: ${realErrors(page).join("; ")}`);
  }
  await page.close();
});

await check("the switcher is one keyboard stop and does not steal the page's keys", async () => {
  const page = await openGalaxy();
  const focused = await page.evaluate(() => {
    const select = document.getElementById("galaxy-look");
    select.focus();
    return {
      isIt: document.activeElement === select,
      tabIndex: select.tabIndex,
      // The page's own Space-to-talk rule must stay on the mic: the HUD has no
      // view-scoped key handler, so a digit hotkey here would fire while the
      // owner is typing in the chat box. The switcher is the keyboard path.
      space: document.getElementById("mic").getAttribute("aria-pressed"),
    };
  });
  assert.equal(focused.isIt, true, "the look switcher cannot take the focus");
  assert.ok(focused.tabIndex >= 0, "the look switcher is not in the tab order");
  assert.equal(focused.space, "false", "the microphone's own state changed");
  await page.keyboard.press("ArrowDown");
  await page.waitForTimeout(150);
  const look = await page.evaluate(() => galaxy.look());
  assert.equal(look, BUILT_PRESETS[0].id,
    "the arrow keys on the switcher do not choose the next look");
  assert.deepEqual(realErrors(page), [], `the page logged: ${realErrors(page).join("; ")}`);
  await page.close();
});

await browser.close();
await close();

console.log();
if (fails.length) {
  console.log(`${fails.length} FAILED:`);
  for (const name of fails) console.log(`  - ${name}`);
  process.exit(1);
}
console.log("Every HUD Galaxy look and dock-order check passed.");
