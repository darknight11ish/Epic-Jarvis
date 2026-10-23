/**
 * Galaxy rework Phase G0: the three flat layout presets - the pure layouts, the
 * switcher decisions, persistence/fallback, and the real Brain window.
 *
 *     node tests/galaxy-presets.mjs
 *
 * Phase G0 (the owner's answer A/A of 2026-10-23; the Galaxy blueprint, Part B,
 * presets 6-8) adds three flat layouts beside the constellation the desktop
 * already draws: `star-map`, `clean-tree` and `zen-ring`, chosen from a menu chip
 * or hotkeys 6/7/8 in the Galaxy view. The default view is untouched, the five
 * rich presets are shown disabled as "not built yet", and the choice is
 * remembered on this device only.
 *
 * WHAT THIS SUITE HOLDS
 *
 *  1. The layouts are PURE and DETERMINISTIC: the same node list, twice, gives
 *     the same positions; the input nodes are not mutated; no clock or random is
 *     involved. No DOM is needed for any of it - that half runs first.
 *  2. The geometry the blueprint names is real: star map = concentric rings at
 *     34/68/108 (further rings at the same pitch only when outgrown) with seven
 *     sector spokes; clean tree = four stationary front-facing rows at the
 *     blueprint's Y = +62/+24/-14/-48; zen ring = the core at the centre, the
 *     rest on one R=108 halo (outward rings only when a list cannot fit it),
 *     with inward Bezier chords.
 *  3. No two nodes are closer than the layout's own gap (24; 21 on the zen halo),
 *     at 240 nodes and at every smaller size tried - the same 240-node bound as
 *     galaxy-view.js's MAX_RENDERED_NODES, pinned here so the two cannot drift.
 *  4. The keyboard decision is pure and testable: 6/7/8 apply or return to the
 *     constellation, 1-5 report "not built yet", other keys are left alone; the
 *     menu's nine entries have the right enabled/disabled shape.
 *  5. Persistence and the safe fallback are themselves pure enough to test with
 *     no page: a stored value only ever restores one of the three built layouts,
 *     anything else (corrupt, stale, planned, a whole object) is the
 *     constellation, and a bad layout object is rejected by `layoutIsUsable`.
 *  6. In the REAL Brain window (Playwright): the chips are there, pressing a
 *     hotkey moves the picture to that layout (guide rings/lines/chords appear,
 *     the buttons follow), pressing it again returns to the constellation, 1-5
 *     announce themselves without changing the layout, the default view still
 *     draws its dots, the choice survives a page reload, a corrupt stored value
 *     falls back to the constellation with no page error, and with the real
 *     32-node graph every layout keeps the dots apart and the labels readable.
 */
import assert from "node:assert/strict";
import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import * as K from "./uikit.mjs";
import {
  BUILT_PRESETS,
  DEFAULT_PRESET,
  MAX_LAYOUT_NODES,
  MIN_GAP,
  PLANNED_PRESETS,
  PRESET_MENU,
  PRESET_STORAGE_KEY,
  TREE_CORE,
  TREE_ROWS,
  TREE_ROW_Y,
  ZEN_HALO_GAP,
  ZEN_MAX_CHORDS,
  ZEN_RADIUS,
  cleanTreeRowFor,
  gapForPreset,
  layoutCleanTree,
  layoutFor,
  layoutIsUsable,
  layoutStarMap,
  layoutZenRing,
  plannedForKey,
  presetForKey,
  presetMeta,
  presetStatus,
  storedPreset,
  switchRequest,
} from "../src/galaxy-presets.js";
import { MAX_RENDERED_NODES } from "../src/galaxy-view.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const EVIDENCE = join(HERE, "..", "..", ".dsh-scratch", "GALAXY-G0-EVIDENCE");
const WANT_SHOTS = process.env.JARVIS_GALAXY_SHOTS === "1";

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

/* ── fixtures ─────────────────────────────────────────────────────────── */

/** A deterministic entity-shaped node list, in the ranked order brain.js keeps:
 *  most facts first (high weight), then rank. Groups cycle so every row of the
 *  clean tree has members. */
function nodesFor(n, groups = ["person", "pet", "place", "organisation",
                               "project", "thing", "other"]) {
  return Array.from({ length: n }, (_, i) => ({
    id: `e:${i + 1}`,
    group: groups[i % groups.length],
    weight: Math.max(1, n - i),
    rank: i,
  }));
}

function radii(layout) {
  return layout.nodes.map((p) => Math.hypot(p.x, p.y));
}

function nearestPair(layout) {
  let worst = Infinity;
  const nodes = layout.nodes;
  for (let i = 0; i < nodes.length; i++) {
    for (let j = i + 1; j < nodes.length; j++) {
      const d = Math.hypot(nodes[i].x - nodes[j].x, nodes[i].y - nodes[j].y);
      if (d < worst) worst = d;
    }
  }
  return worst;
}

/** Capacity of one ring, recomputed from the spec rather than the module:
 *  n evenly spaced points sit 2R sin(pi/n) apart, so n = floor(pi/asin(gap/2R)). */
function expectedRingCapacity(radius, gap = MIN_GAP) {
  return Math.floor(Math.PI / Math.asin(gap / (2 * radius)));
}

/* ── 1. the presets themselves ────────────────────────────────────────── */

await check("the three flat layouts are built; 6/7/8 are their keys; the five rich presets are not", async () => {
  assert.equal(DEFAULT_PRESET, "constellation");
  assert.deepEqual(BUILT_PRESETS.map((p) => p.id), ["star-map", "clean-tree", "zen-ring"]);
  assert.deepEqual(BUILT_PRESETS.map((p) => p.key), ["6", "7", "8"]);
  assert.deepEqual(PLANNED_PRESETS.map((p) => p.key), ["1", "2", "3", "4", "5"]);
  assert.equal(presetMeta(DEFAULT_PRESET).built, true);
  for (const p of PLANNED_PRESETS) assert.equal(presetMeta(p.id).built, false, p.id);
  assert.equal(PRESET_MENU.length, 1 + PLANNED_PRESETS.length + BUILT_PRESETS.length);
  assert.equal(new Set(PRESET_MENU.map((p) => p.id)).size, PRESET_MENU.length, "duplicate preset id");
  assert.equal(presetForKey("6").id, "star-map");
  assert.equal(presetForKey("9"), null);
  assert.equal(plannedForKey("3").label, "Nebula");
  assert.equal(plannedForKey("6"), null);
});

await check("the menu shows the not-built presets disabled rather than hiding them", async () => {
  const planned = PRESET_MENU.filter((p) => !p.built);
  assert.equal(planned.length, 5);
  for (const p of planned) {
    assert.equal(p.hint, "not built yet", p.id);
    assert.match(presetStatus(p.id), /is not built yet\. Press 6, 7 or 8/);
  }
  assert.match(presetStatus("star-map"), /^Layout: Star map\./);
  assert.match(presetStatus(DEFAULT_PRESET), /constellation/);
  assert.equal(presetStatus("nope"), "");
});

/* ── 2. pure + deterministic ──────────────────────────────────────────── */

await check("the same list lays out the same way twice, every time - and is not mutated", async () => {
  for (const id of ["star-map", "clean-tree", "zen-ring"]) {
    const nodes = nodesFor(40);
    const before = JSON.parse(JSON.stringify(nodes));
    const first = layoutFor(id, nodes);
    const second = layoutFor(id, nodes);
    assert.equal(JSON.stringify(nodes), JSON.stringify(before), `${id} mutated its input`);
    assert.deepEqual(first, second, `${id} is not deterministic`);
    assert.equal(first.id, id);
    assert.equal(first.minGap, gapForPreset(id), `${id} reports the wrong gap`);
    for (const p of first.nodes) {
      assert.ok(Number.isFinite(p.x) && Number.isFinite(p.y), `${id} produced a non-finite point`);
    }
    assert.deepEqual(first.nodes.map((p) => p.id), nodes.map((n) => n.id),
      `${id} changed the node order`);
  }
  assert.equal(layoutFor(DEFAULT_PRESET, nodesFor(3)), null, "the constellation is not a flat layout");
  assert.equal(layoutFor("nebula", nodesFor(3)), null, "a planned preset must not pretend to lay out");
  assert.equal(layoutFor("no-such-preset", nodesFor(3)), null);
});

/* ── 3. star-map: rings, spokes, no centre node ───────────────────────── */

await check("star map is a flat plane: rings R=34/68/108 and seven sector spokes", async () => {
  const layout = layoutStarMap(nodesFor(40));
  assert.deepEqual(layout.rings, [34, 68, 108], "the three rings the blueprint names");
  // Ring membership is contiguous in ranked order, with the computed capacities.
  const counts = [expectedRingCapacity(34), expectedRingCapacity(68),
    40 - expectedRingCapacity(34) - expectedRingCapacity(68)];
  let at = 0;
  for (let ring = 0; ring < 3; ring++) {
    for (let k = 0; k < counts[ring]; k++, at++) {
      assert.ok(Math.abs(radii(layout)[at] - layout.rings[ring]) < 1e-6,
        `node ${at} is not on ring ${layout.rings[ring]} (r=${radii(layout)[at]})`);
    }
  }
  assert.equal(at, 40);
  assert.equal(layout.guides.circles.length, 3, "one guide circle per ring");
  assert.equal(layout.guides.lines.length, 7, "the blueprint's seven sector spokes");
  for (const line of layout.guides.lines) {
    assert.deepEqual([line.x1, line.y1], [0, 0], "a spoke starts at the centre");
    assert.ok(Math.abs(Math.hypot(line.x2, line.y2) - 108) < 1e-6, "a spoke reaches the outer ring");
  }
  assert.ok(nearestPair(layout) >= MIN_GAP - 1e-9, "star map overlaps at 40 names");
});

await check("a star map that outgrows 108 grows outward at the same 34px pitch", async () => {
  const layout = layoutStarMap(nodesFor(240));
  assert.equal(layout.nodes.length, 240);
  assert.deepEqual(layout.rings.slice(0, 3), [34, 68, 108]);
  assert.equal(layout.rings.length, 7, "240 names need seven rings");
  assert.equal(layout.rings.at(-1), 244, `expected the last ring at 244, got ${layout.rings.at(-1)}`);
  // The blueprint's three base rings are not evenly pitched (108 - 68 = 40);
  // only the rings added when a list outgrows them keep the 34px pitch.
  for (let i = 3; i < layout.rings.length; i++) {
    assert.equal(layout.rings[i] - layout.rings[i - 1], 34, "growing rings keep the 34px pitch");
  }
});

/* ── 4. clean-tree: four stationary, front-facing rows ────────────────── */

await check("clean tree is four front-facing rows at the blueprint's heights", async () => {
  const nodes = nodesFor(40);
  const layout = layoutCleanTree(nodes);
  assert.equal(layout.rows.length, TREE_ROWS);
  assert.deepEqual(layout.rows, [...TREE_ROW_Y], "the blueprint's four rows, top to bottom");
  assert.deepEqual(layout.rows, [-62, -24, 14, 48],
    "core stays at the top: the blueprint's up-positive Y becomes canvas down-positive Y");
  const rowOf = new Map();
  nodes.forEach((n, i) => rowOf.set(n.id, cleanTreeRowFor(n, i)));
  assert.equal([...rowOf.values()].filter((r) => r === 0).length, TREE_CORE,
    "the core row is the best-known names");
  // Every node's y IS its row's y: rows are fixed lines, not scattered bands.
  for (const node of layout.nodes) {
    const row = rowOf.get(node.id);
    assert.equal(node.y, layout.rows[row], `${node.id} is not on its row's line`);
  }
  for (let row = 0; row < TREE_ROWS; row++) {
    assert.ok([...rowOf.values()].includes(row), `row ${row} has no names in this fixture`);
  }
  assert.equal(layout.guides.lines.length, TREE_ROWS, "one faint guide line per row");
  assert.equal(layout.rings.length, 0);
  assert.ok(nearestPair(layout) >= MIN_GAP - 1e-9, "clean tree overlaps");
});

/* ── 5. zen-ring: centre core + one halo + chords ─────────────────────── */

await check("zen ring is the core at the centre and the rest on one R=108 halo with chords", async () => {
  const layout = layoutZenRing(nodesFor(32));
  assert.deepEqual(layout.rings, [ZEN_RADIUS], "the blueprint's 32 names fit ONE halo");
  assert.deepEqual([layout.nodes[0].x, layout.nodes[0].y], [0, 0], "the first name is the core");
  for (const r of radii(layout).slice(1)) {
    assert.ok(Math.abs(r - ZEN_RADIUS) < 1e-6, `a name left the halo (r=${r})`);
  }
  assert.equal(layout.guides.circles.length, 1);
  assert.equal(layout.guides.circles[0].kind, "halo");
  assert.equal(layout.guides.paths.length, 31, "one inward chord per halo name");
  for (const chord of layout.guides.paths) {
    assert.match(chord.d, /^M -?[\d.]+ -?[\d.]+ Q -?[\d.]+ -?[\d.]+ -?[\d.]+ -?[\d.]+$/);
  }
  assert.ok(nearestPair(layout) >= ZEN_HALO_GAP - 1e-9, "zen ring overlaps");
});

await check("a list too big for the halo grows OUTWARD, so 108 stays the calm centre", async () => {
  const layout = layoutZenRing(nodesFor(240));
  assert.equal(layout.nodes.length, 240);
  assert.deepEqual(layout.rings.slice(0, 6), [108, 132, 156, 180, 204, 228]);
  for (let i = 1; i < layout.rings.length; i++) {
    assert.equal(layout.rings[i] - layout.rings[i - 1], 24, "rings keep the 24px pitch");
  }
  assert.ok(layout.guides.paths.length <= ZEN_MAX_CHORDS, "chords are capped");
  assert.ok(nearestPair(layout) >= ZEN_HALO_GAP - 1e-9, "zen ring overlaps at 240 names");
});

/* ── 6. the bound, no overlap, and the safe fallback guard ────────────── */

await check("every layout respects the picture's own 240-node bound", async () => {
  assert.equal(MAX_LAYOUT_NODES, MAX_RENDERED_NODES,
    "galaxy-presets.js and galaxy-view.js disagree about the cap");
  const many = nodesFor(500);
  for (const id of ["star-map", "clean-tree", "zen-ring"]) {
    const layout = layoutFor(id, many);
    assert.equal(layout.nodes.length, MAX_LAYOUT_NODES, `${id} ignored the cap`);
    assert.deepEqual(layout.nodes.map((p) => p.id), many.slice(0, MAX_LAYOUT_NODES).map((n) => n.id),
      `${id} did not keep the ranked order`);
    assert.equal(layoutIsUsable(layout, many), true, `${id} fails its own usability guard`);
  }
});

await check("no two names are closer than the layout's gap, at 240 and at every smaller size tried", async () => {
  for (const size of [1, 2, 5, 6, 7, 20, 100, 239, 240]) {
    for (const id of ["star-map", "clean-tree", "zen-ring"]) {
      const layout = layoutFor(id, nodesFor(size));
      assert.equal(layout.nodes.length, size);
      const pair = nearestPair(layout);
      assert.ok(pair >= layout.minGap - 1e-9,
        `${id} at ${size}: two names are ${pair.toFixed(3)} apart`);
    }
  }
});

await check("the safe-fallback guard rejects a bad layout instead of drawing it", async () => {
  const nodes = nodesFor(40);
  const good = layoutCleanTree(nodes);
  assert.equal(layoutIsUsable(good, nodes), true);
  assert.equal(layoutIsUsable(null, nodes), false);
  assert.equal(layoutIsUsable({ nodes: [] }, nodes), false, "wrong length");
  assert.equal(layoutIsUsable({ nodes: good.nodes.map((p, i) =>
    i === 0 ? { ...p, id: "someone else" } : p) }, nodes), false, "wrong ids");
  assert.equal(layoutIsUsable({ nodes: good.nodes.map((p, i) =>
    i === 0 ? { ...p, x: Number.NaN } : p) }, nodes), false, "non-finite point");
  assert.equal(layoutIsUsable({ nodes: good.nodes, guides: { circles: "no" } }, nodes), false,
    "guide lists must be arrays");
  assert.equal(layoutIsUsable({ nodes: good.nodes }, nodes), true, "a layout may have no guides");
});

/* ── 7. persistence: this device only, and never trusted ──────────────── */

await check("only the three built layouts can be restored; anything else is the constellation", async () => {
  assert.equal(typeof PRESET_STORAGE_KEY, "string");
  for (const id of ["star-map", "clean-tree", "zen-ring"]) {
    assert.equal(storedPreset(id), id);
    assert.equal(storedPreset(` ${id} `), id, "surrounding whitespace is tolerated");
  }
  assert.equal(storedPreset(DEFAULT_PRESET), DEFAULT_PRESET);
  for (const raw of ["nebula", "planetary-orbit", "no-such-layout", "", "  ", null,
                     undefined, 42, { id: "star-map" }]) {
    assert.equal(storedPreset(raw), DEFAULT_PRESET, `stored value ${JSON.stringify(raw)}`);
  }
});

/* ── 8. the keyboard decision, without a page ─────────────────────────── */

await check("hotkeys 6/7/8 apply a layout, a second press returns to the constellation", async () => {
  assert.deepEqual(switchRequest("6", DEFAULT_PRESET), { action: "apply", key: "6", id: "star-map" });
  assert.deepEqual(switchRequest("7", "star-map"), { action: "apply", key: "7", id: "clean-tree" });
  assert.deepEqual(switchRequest("8", "clean-tree"), { action: "apply", key: "8", id: "zen-ring" });
  assert.deepEqual(switchRequest("8", "zen-ring"),
    { action: "apply", key: "8", id: DEFAULT_PRESET },
  "pressing the active preset's key goes back to the constellation");
  // The stage's own keys are not presets: pan/zoom/fit keep working.
  for (const key of ["0", "ArrowLeft", "+", "-", "Escape", "a", "9"]) {
    assert.equal(switchRequest(key, DEFAULT_PRESET), null, `key ${key} was stolen from the stage`);
  }
});

await check("hotkeys 1-5 say the rich presets are not built yet, and change nothing", async () => {
  assert.deepEqual(switchRequest("1", "star-map"),
    { action: "planned", key: "1", id: "planetary-orbit" });
  assert.deepEqual(switchRequest("5", "zen-ring"),
    { action: "planned", key: "5", id: "radar-dome" });
  assert.match(presetStatus("planetary-orbit"), /not built yet/);
});

/* ── 9. performance: a switch must not be a noticeable pause ──────────── */

await check("laying out 240 names is fast enough to feel instant (all three under 250 ms)", async () => {
  const many = nodesFor(240);
  const started = performance.now();
  for (const id of ["star-map", "clean-tree", "zen-ring"]) {
    const layout = layoutFor(id, many);
    assert.equal(layout.nodes.length, 240);
  }
  const elapsed = performance.now() - started;
  assert.ok(elapsed < 250, `three 240-name layouts took ${elapsed.toFixed(1)} ms`);
  console.log(`      (three 240-name layouts: ${elapsed.toFixed(1)} ms)`);
});

/* ── 10. the real Brain window ────────────────────────────────────────── */

const { base, close } = await K.serve();
const browser = await K.launch();
/** The real 32-node graph: makeEntities()' own 8 named people/things plus 24
 *  generated ones - the curated size the blueprint's flat views are for. */
const ENTITIES = K.makeEntities(0.75);
assert.equal(ENTITIES.entities.length, 32, "the readability fixture is the real 32-node graph");

async function openBrain(scale = 0.75, extra = {}) {
  const ent = scale === 0.75 ? ENTITIES : K.makeEntities(scale);
  const page = await K.open(browser, base, "brain.html",
    { brain: { ...K.BRAIN, memory_entities: ent }, ...extra },
    { width: 1200, height: 900 });
  return page;
}

/** Show the Galaxy view and wait until its dots exist. */
async function gotoGalaxy(page) {
  await page.locator("#rail-advanced-toggle").click();
  await page.locator("#tab-galaxy").click();
  await page.waitForFunction(() =>
    document.querySelectorAll("#graph-overlay .galaxy-node-button").length > 0);
  await page.waitForTimeout(250);
}

const guides = (page, selector) => page.locator(`#graph-svg [data-layer="guides"] ${selector}`);
const chip = (page, id) => page.locator(`#graph-presets button[data-preset="${id}"]`);
const status = (page) => page.locator("#graph-preset-status").innerText();
/** How many fact-sharing links are actually PAINTED (not just in the DOM). A
 *  flat layout hides them with CSS: they are the physics picture's edges and
 *  turn a stationary diagram into a web. */
const visibleLinks = (page) => page.locator("#graph-svg .galaxy-link").evaluateAll(
  (els) => els.filter((el) => getComputedStyle(el).display !== "none").length);

async function pressKey(page, key) {
  await page.locator(".galaxy-stage").focus();
  await page.keyboard.press(key);
}

async function saveShot(page, name) {
  if (!WANT_SHOTS) return;
  mkdirSync(EVIDENCE, { recursive: true });
  await page.screenshot({ path: join(EVIDENCE, name) });
}

await check("the real window has the nine chips; the five not-built ones are disabled", async () => {
  const page = await openBrain();
  await gotoGalaxy(page);
  assert.equal(await page.locator("#graph-presets button").count(), 9);
  assert.equal(await page.locator("#graph-presets button:disabled").count(), 5);
  for (const p of PLANNED_PRESETS) {
    const label = (await chip(page, p.id).innerText()).replace(/\s+/g, " ");
    assert.match(label, new RegExp(`^${p.key} ${p.label} not built yet$`), label);
    assert.equal(await chip(page, p.id).isDisabled(), true, `${p.id} is not disabled`);
  }
  for (const p of BUILT_PRESETS) {
    assert.equal(await chip(page, p.id).isDisabled(), false, `${p.id} should be usable`);
  }
  assert.equal(await chip(page, DEFAULT_PRESET).getAttribute("aria-pressed"), "true");
  // The chip row must not make the window scroll sideways (the first version
  // did: the zen-ring evidence screenshot was cut off on the left).
  const overflow = await page.evaluate(() =>
    document.documentElement.scrollWidth - window.innerWidth);
  assert.ok(overflow <= 1, `the window scrolls ${overflow}px sideways because of the chips`);
  assert.deepEqual(page.__errors, [], `the page logged errors: ${page.__errors.join("; ")}`);
  await saveShot(page, "g0-default-32.png");
  await page.close();
});

await check("hotkey 6 turns the constellation into a star map, and 6 again brings it back", async () => {
  const page = await openBrain();
  await gotoGalaxy(page);
  const before = await page.locator("#graph-overlay .galaxy-node-button").count();
  const started = performance.now();
  await pressKey(page, "6");
  await page.waitForFunction(() =>
    document.querySelectorAll('#graph-svg [data-layer="guides"] circle.galaxy-guide-ring').length === 3);
  const elapsed = performance.now() - started;
  assert.ok(elapsed < 2000, `the star map took ${elapsed.toFixed(0)} ms to appear`);
  assert.equal(await chip(page, "star-map").getAttribute("aria-pressed"), "true");
  assert.equal(await chip(page, DEFAULT_PRESET).getAttribute("aria-pressed"), "false");
  assert.match(await status(page), /^Layout: Star map\./);
  assert.equal(await guides(page, "line.galaxy-guide-line").count(), 7, "seven spokes");
  assert.equal(await visibleLinks(page), 0,
    "a flat layout must not draw the constellation's fact-sharing web");
  assert.equal(await page.locator("#graph-overlay .galaxy-node-button").count(), before,
    "the star map changed the set of names");
  await saveShot(page, "g0-star-map-32.png");
  await pressKey(page, "6");
  await page.waitForFunction(() =>
    document.querySelectorAll('#graph-svg [data-layer="guides"]').length === 0);
  assert.equal(await chip(page, DEFAULT_PRESET).getAttribute("aria-pressed"), "true");
  assert.ok(await visibleLinks(page) > 0, "the constellation's fact links did not come back");
  assert.equal(await page.locator("#graph-overlay .galaxy-node-button").count(), before,
    "the constellation did not come back");
  assert.deepEqual(page.__errors, [], `the page logged errors: ${page.__errors.join("; ")}`);
  await page.close();
});

await check("hotkey 7 draws the four-row clean tree, and a chip click switches too", async () => {
  const page = await openBrain();
  await gotoGalaxy(page);
  await pressKey(page, "7");
  await page.waitForFunction(() =>
    document.querySelectorAll('#graph-svg [data-layer="guides"] line.galaxy-guide-line').length === 4);
  assert.match(await status(page), /^Layout: Clean tree\./);
  assert.equal(await guides(page, "circle.galaxy-guide-ring").count(), 0);
  assert.equal(await visibleLinks(page), 0, "the clean tree drew the fact-sharing web");
  await saveShot(page, "g0-clean-tree-32.png");
  await chip(page, "zen-ring").click();
  await page.waitForFunction(() =>
    document.querySelectorAll('#graph-svg [data-layer="guides"] circle.galaxy-guide-ring').length === 1);
  assert.equal(await chip(page, "zen-ring").getAttribute("aria-pressed"), "true");
  assert.match(await status(page), /^Layout: Zen ring\./);
  const chords = await guides(page, "path.galaxy-guide-chord").count();
  assert.equal(chords, 31, `expected one chord per halo name, got ${chords}`);
  assert.equal(await visibleLinks(page), 0, "the zen ring drew the fact-sharing web");
  await saveShot(page, "g0-zen-ring-32.png");
  assert.deepEqual(page.__errors, [], `the page logged errors: ${page.__errors.join("; ")}`);
  await page.close();
});

await check("hotkeys 1-5 announce 'not built yet' and leave the layout alone", async () => {
  const page = await openBrain();
  await gotoGalaxy(page);
  await pressKey(page, "8");
  await page.waitForFunction(() =>
    document.querySelectorAll('#graph-svg [data-layer="guides"] circle.galaxy-guide-ring').length === 1);
  await pressKey(page, "3");
  assert.match(await status(page), /^Nebula is not built yet\./);
  assert.equal(await chip(page, "zen-ring").getAttribute("aria-pressed"), "true",
    "a planned preset changed the layout");
  assert.equal(await guides(page, "circle.galaxy-guide-ring").count(), 1);
  assert.deepEqual(page.__errors, [], `the page logged errors: ${page.__errors.join("; ")}`);
  await page.close();
});

await check("the choice survives a page reload; the default chip clears the memory", async () => {
  const page = await openBrain();
  await gotoGalaxy(page);
  await pressKey(page, "7");
  await page.waitForFunction(() =>
    document.querySelectorAll('#graph-svg [data-layer="guides"] line.galaxy-guide-line').length === 4);
  assert.equal(await page.evaluate((key) => localStorage.getItem(key), PRESET_STORAGE_KEY),
    "clean-tree", "the choice was not remembered on this device");
  await page.reload();
  await page.waitForFunction(() => document.querySelector("#tab-galaxy") !== null);
  await gotoGalaxy(page);
  await page.waitForFunction(() =>
    document.querySelectorAll('#graph-svg [data-layer="guides"] line.galaxy-guide-line').length === 4);
  assert.equal(await chip(page, "clean-tree").getAttribute("aria-pressed"), "true",
    "the saved layout did not come back after a reload");
  await pressKey(page, "7");
  await page.waitForFunction(() =>
    document.querySelectorAll('#graph-svg [data-layer="guides"]').length === 0);
  assert.equal(await page.evaluate((key) => localStorage.getItem(key), PRESET_STORAGE_KEY), null,
    "the constellation should forget the stored layout");
  assert.deepEqual(page.__errors, [], `the page logged errors: ${page.__errors.join("; ")}`);
  await page.close();
});

await check("a corrupt remembered value is the constellation, not a broken page", async () => {
  const page = await openBrain(0.75,
    { storage: { [PRESET_STORAGE_KEY]: "no-such-layout-from-an-older-build" } });
  await gotoGalaxy(page);
  assert.equal(await chip(page, DEFAULT_PRESET).getAttribute("aria-pressed"), "true");
  assert.equal(await page.locator('#graph-svg [data-layer="guides"]').count(), 0);
  assert.deepEqual(page.__errors, [], `the page logged errors: ${page.__errors.join("; ")}`);
  await page.close();
});

await check("with the real 32-node graph every layout keeps the dots apart and the labels readable", async () => {
  const page = await openBrain();
  await gotoGalaxy(page);
  const counts = { buttons: 0, labels: 0 };
  for (const [id, key, waitSelector] of [
    ["star-map", "6", 'circle.galaxy-guide-ring'],
    ["clean-tree", "7", 'line.galaxy-guide-line'],
    ["zen-ring", "8", 'circle.galaxy-guide-ring'],
  ]) {
    await pressKey(page, key);
    await page.waitForFunction(
      ({ selector }) => document.querySelectorAll(
        `#graph-svg [data-layer="guides"] ${selector}`).length > 0,
      { selector: waitSelector });
    assert.equal(await visibleLinks(page), 0, `${id}: the fact-sharing web is still drawn`);
    const metrics = await page.evaluate(() => {
      const cs = [...document.querySelectorAll("#graph-overlay .galaxy-node-button")]
        .map((el) => {
          const r = el.getBoundingClientRect();
          return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
        });
      let closest = Infinity;
      for (let i = 0; i < cs.length; i++) {
        for (let j = i + 1; j < cs.length; j++) {
          closest = Math.min(closest, Math.hypot(cs[i].x - cs[j].x, cs[i].y - cs[j].y));
        }
      }
      const stage = document.querySelector(".galaxy-stage").getBoundingClientRect();
      // A dot's true centre is the drawn circle's centre; the HTML button is
      // keyed from that point but is a square whose top-left lands there.
      const dotById = new Map([...document.querySelectorAll("#graph-svg g.galaxy-node")]
        .map((g) => {
          const r = g.getBoundingClientRect();
          return [g.getAttribute("data-node"), r.left + r.width / 2];
        }));
      const labels = [...document.querySelectorAll("#graph-overlay .galaxy-node-label")].map((el) => {
        const r = el.getBoundingClientRect();
        return {
          text: el.textContent,
          // The label must be CENTRED on its dot: the label's own centre is
          // within 2px of the drawn dot's centre on the same node. (This is
          // what the shipped `margin-left: -50%` got wrong - see brain.css.)
          centered: Math.abs((r.left + r.width / 2)
            - dotById.get(el.getAttribute("data-label-for"))) <= 2,
          inside: r.left >= stage.left - 2 && r.right <= stage.right + 2
            && r.top >= stage.top - 2 && r.bottom <= stage.bottom + 2,
        };
      });
      return { dots: cs.length, closest, labels };
    });
    assert.equal(metrics.dots, ENTITIES.entities.length, `${id} lost or added names`);
    assert.ok(metrics.closest >= 24,
      `${id}: two dots are only ${metrics.closest.toFixed(1)} px apart on screen`);
    // The labels follow the window's existing rule: the 24 best-connected names,
    // drawn in full, centred on their dot and inside the picture (not clipped).
    assert.equal(metrics.labels.length, 24, `${id}: expected the usual 24 labels`);
    for (const label of metrics.labels) {
      assert.ok(label.text && label.text.trim().length > 0, `${id}: an empty label`);
      assert.ok(label.centered, `${id}: label "${label.text}" is not centred on its dot`);
      assert.ok(label.inside, `${id}: label "${label.text}" is clipped by the stage`);
    }
    console.log(`      ${id}: closest dots ${metrics.closest.toFixed(1)} px, `
      + `${metrics.labels.length} labels`);
    if (id === "star-map") counts.buttons = metrics.dots;
    counts.labels = metrics.labels.length;
  }
  assert.equal(counts.buttons, 32);
  assert.deepEqual(page.__errors, [], `the page logged errors: ${page.__errors.join("; ")}`);
  await page.close();
});

await check("the default view still draws after switching back, and nothing errors", async () => {
  const page = await openBrain();
  await gotoGalaxy(page);
  const statBefore = await page.locator("#graph-stat").innerText();
  await pressKey(page, "6");
  await pressKey(page, "6");
  const statAfter = await page.locator("#graph-stat").innerText();
  assert.equal(statAfter, statBefore, "the constellation's count line changed");
  assert.ok(await page.locator("#graph-overlay .galaxy-node-button").count() > 0);
  assert.equal(await page.locator('#graph-svg [data-layer="guides"]').count(), 0);
  assert.deepEqual(page.__errors, [], `the page logged errors: ${page.__errors.join("; ")}`);
  await page.close();
});

await browser.close();
await close();

console.log();
if (fails.length) {
  console.log(`${fails.length} FAILED, ${fails.length ? "" : ""}`);
  for (const name of fails) console.log(`  - ${name}`);
  process.exit(1);
}
console.log("Every galaxy-presets check passed.");
