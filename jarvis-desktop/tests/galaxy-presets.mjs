/**
 * The Galaxy's eight looks - the pure layouts, the switcher decisions,
 * persistence/fallback, and the real Brain window.
 *
 *     node tests/galaxy-presets.mjs
 *
 * Phase G0 (the owner's answer A/A of 2026-10-23; the Galaxy blueprint, Part B,
 * presets 6-8) added three flat layouts beside the constellation. On 2026-10-27
 * the owner asked for "an easy way to change the appearance of the jarvis galaxy
 * to the other models [modes]" and chose BOTH: the other five looks were built
 * too, so all eight are real now (`planetary-orbit`, `neural-arbor`, `nebula`,
 * `dna-helix`, `radar-dome`, `star-map`, `clean-tree`, `zen-ring`), each on its
 * own hotkey 1-8, each with a chip in the Galaxy bar. The constellation is still
 * the default and the choice is still remembered on this device only.
 *
 * WHAT THIS SUITE HOLDS
 *
 *  1. The layouts are PURE and DETERMINISTIC: the same node list, twice, gives
 *     the same positions; the input nodes are not mutated; no clock or random is
 *     involved. No DOM is needed for any of it - that half runs first.
 *  2. The geometry each look is named for is real: star map = concentric rings
 *     at 34/68/108 with seven spokes; clean tree = four stationary rows at the
 *     blueprint's heights; zen ring = the core at the centre, one R=108 halo,
 *     inward chords; planetary orbit = a sun at the centre and the rest on
 *     ellipses; neural arbor = a soma with one dendrite per name and exactly
 *     n - 1 edges (a tree); nebula = one even cloud with no rings and no rows;
 *     DNA helix = two backbones with one rung per pair, tilted; radar dome = a
 *     half disc above a horizon with a sweep arm.
 *  3. No two nodes are closer than the layout's own gap (24; 21 on the zen
 *     halo), at 240 nodes and at every smaller size tried - the same 240-node
 *     bound as galaxy-view.js's MAX_RENDERED_NODES, pinned here so the two
 *     cannot drift.
 *  4. The keyboard decision is pure and testable: 1-8 apply their look or
 *     return to the constellation on a second press, other keys are left alone;
 *     all nine menu entries are built.
 *  5. Persistence and the safe fallback are themselves pure enough to test with
 *     no page: a stored value only ever restores one of the eight looks,
 *     anything else (corrupt, stale, a whole object) is the constellation, and a
 *     bad layout object is rejected by `layoutIsUsable`.
 *  6. In the REAL Brain window (Playwright): the nine chips are there, pressing
 *     a hotkey moves the picture to that look (guide rings/lines/paths appear,
 *     the buttons follow), pressing it again returns to the constellation, the
 *     default view still draws its dots, the choice survives a page reload, a
 *     corrupt stored value falls back to the constellation with no page error,
 *     and with the real 32-node graph every look keeps the dots apart.
 *  7. Audit follow-ups (2026-10-23, .dsh-scratch/GALAXY-G0-AUDIT): the Fit
 *     button and the `0` key use the looks' wider margin (so labels stay inside
 *     the picture after a fit, not just after a switch); the chip row and the
 *     stage say what a keyboard/screen-reader user needs; and switching away
 *     during the constellation's assembly and back leaves a live constellation,
 *     never a frozen part-assembled one.
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
  layoutDnaHelix,
  layoutFor,
  layoutIsUsable,
  layoutNebula,
  layoutNeuralArbor,
  layoutPlanetaryOrbit,
  layoutRadarDome,
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

/** Capacity of one DOME arc (a half circle): n points sit 2R sin(pi/2n) apart,
 *  so n = floor(pi / (2 asin(gap / 2R))). */
function expectedDomeCapacity(radius, gap = MIN_GAP) {
  return Math.floor(Math.PI / (2 * Math.asin(gap / (2 * radius))));
}

/** The names, in order, of every guide line whose end is that point. */
function linesEndingAt(layout, point) {
  return layout.guides.lines.filter((line) =>
    Math.abs(line.x2 - point.x) < 1e-9 && Math.abs(line.y2 - point.y) < 1e-9);
}

const ALL_LOOKS = ["planetary-orbit", "neural-arbor", "nebula", "dna-helix",
                   "radar-dome", "star-map", "clean-tree", "zen-ring"];

/* ── 1. the presets themselves ────────────────────────────────────────── */

await check("all eight looks are built; 1-8 are their keys; nothing is planned any more", async () => {
  assert.equal(DEFAULT_PRESET, "constellation");
  assert.deepEqual(BUILT_PRESETS.map((p) => p.id), ALL_LOOKS,
    "the looks are the blueprint's five rich views, then the three flat ones");
  assert.deepEqual(BUILT_PRESETS.map((p) => p.key),
    ["1", "2", "3", "4", "5", "6", "7", "8"]);
  assert.deepEqual([...PLANNED_PRESETS], [], "nothing is left unbuilt");
  assert.equal(presetMeta(DEFAULT_PRESET).built, true);
  assert.equal(PRESET_MENU.length, 1 + BUILT_PRESETS.length);
  assert.equal(new Set(PRESET_MENU.map((p) => p.id)).size, PRESET_MENU.length,
    "duplicate preset id");
  // The menu has not been reordered: the default, then keys 1 to 8.
  assert.deepEqual(PRESET_MENU.map((p) => p.key), [null, "1", "2", "3", "4", "5", "6", "7", "8"]);
  for (const p of PRESET_MENU) assert.equal(p.built, true, `${p.id} is not built`);
  for (const key of ["1", "2", "3", "4", "5", "6", "7", "8"]) {
    const look = presetForKey(key);
    assert.ok(look, `key ${key} selects no look`);
    assert.equal(plannedForKey(key), null, `key ${key} is still treated as planned`);
  }
  assert.equal(presetForKey("6").id, "star-map");
  assert.equal(presetForKey("1").id, "planetary-orbit");
  assert.equal(presetForKey("9"), null);
  assert.equal(presetForKey("0"), null);
});

await check("every look's status line names it, and none says 'not built yet'", async () => {
  for (const p of BUILT_PRESETS) {
    assert.match(presetStatus(p.id), new RegExp(`^Layout: ${p.label}\\.`), p.id);
    assert.match(presetStatus(p.id), /press its key again for the constellation/i, p.id);
    assert.ok(p.hint && p.hint !== "not built yet", `${p.id} has no one-line hint`);
    assert.doesNotMatch(presetStatus(p.id), /not built yet/, p.id);
  }
  assert.match(presetStatus(DEFAULT_PRESET), /constellation/);
  assert.equal(presetStatus("nope"), "");
});

/* ── 2. pure + deterministic ──────────────────────────────────────────── */

await check("the same list lays out the same way twice, every time - and is not mutated", async () => {
  for (const id of ALL_LOOKS) {
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

/* ── 5b. planetary-orbit: a sun + concentric ellipses ─────────────────── */

await check("planetary orbit is a sun at the centre and the rest on concentric ellipses", async () => {
  const nodes = nodesFor(40);
  const layout = layoutPlanetaryOrbit(nodes);
  assert.deepEqual([layout.nodes[0].x, layout.nodes[0].y], [0, 0],
    "the best-known name is the sun");
  // Three orbits at 40 names: 11 + 18 on the first two, the rest on the third.
  const counts = [expectedRingCapacity(74 * 0.6), expectedRingCapacity(120 * 0.6)];
  counts.push(40 - 1 - counts[0] - counts[1]);
  assert.deepEqual(layout.rings, [74, 120, 166], "the ellipse axes, 46 apart");
  assert.equal(layout.guides.paths.length, 3, "one orbit guide per ellipse");
  for (const path of layout.guides.paths) {
    assert.ok(path.ellipse && path.ellipse.b < path.ellipse.a, "an orbit must be an ellIPSE, not a circle");
  }
  // Every body sits exactly on its own orbit: (x/a)^2 + (y/b)^2 == 1.
  let at = 1;
  counts.forEach((count, orbit) => {
    const a = layout.rings[orbit];
    const b = a * 0.6;
    for (let k = 0; k < count; k++, at++) {
      const p = layout.nodes[at];
      const onIt = (p.x * p.x) / (a * a) + (p.y * p.y) / (b * b);
      assert.ok(Math.abs(onIt - 1) < 1e-9,
        `node ${at} left orbit ${orbit} (value ${onIt.toFixed(6)})`);
    }
  });
  assert.equal(at, 40, "every name after the sun is on an orbit");
  assert.ok(nearestPair(layout) >= MIN_GAP - 1e-9, "planetary orbit overlaps");
});

/* ── 5c. neural-arbor: a soma, a dendrite per name, n - 1 edges ───────── */

await check("neural arbor is a tree: one dendrite per name, doubling levels, n - 1 edges", async () => {
  const nodes = nodesFor(40);
  const layout = layoutNeuralArbor(nodes);
  assert.equal(Math.abs(layout.nodes[0].x), 0, "the soma is at the centre (x)");
  assert.equal(Math.abs(layout.nodes[0].y), 0, "the soma is at the centre (y)");
  assert.equal(layout.guides.lines.length, 39, "one dendrite for every name but the soma");
  // Each non-soma name ends exactly ONE dendrite; the soma ends none.
  for (let i = 1; i < layout.nodes.length; i++) {
    const ends = linesEndingAt(layout, layout.nodes[i]);
    assert.equal(ends.length, 1, `${nodes[i].id} is the end of ${ends.length} dendrites`);
  }
  assert.equal(linesEndingAt(layout, layout.nodes[0]).length, 0, "a dendrite ends on the soma");
  // A parent is always closer to the centre than its child: the picture grows
  // outward, and the levels really double (1, 2, 4, 8, 16, ... names at a radius).
  const radiusOf = (p) => Math.hypot(p.x, p.y);
  const levels = new Map();
  for (const node of layout.nodes) {
    const key = radiusOf(node).toFixed(3);
    levels.set(key, (levels.get(key) || 0) + 1);
  }
  assert.deepEqual([...levels.values()], [1, 2, 4, 8, 16, 9],
    `the levels do not double (saw ${[...levels.values()].join(", ")})`);
  for (const line of layout.guides.lines) {
    assert.ok(Math.hypot(line.x1, line.y1) < Math.hypot(line.x2, line.y2),
      "a dendrite points inward");
  }
  assert.deepEqual(layout.rings.map((r) => r.toFixed(3)), [...levels.keys()]);
  assert.ok(nearestPair(layout) >= MIN_GAP - 1e-9, "neural arbor overlaps");
});

/* ── 5d. nebula: one even cloud, no line-work ─────────────────────────── */

await check("nebula is one even cloud: no rings, no rows, no ring of names", async () => {
  const layout = layoutNebula(nodesFor(240));
  assert.equal(layout.nodes.length, 240);
  assert.deepEqual(layout.rings, []);
  assert.deepEqual(layout.rows, []);
  assert.equal(layout.guides.circles.length + layout.guides.lines.length
    + layout.guides.paths.length, 0, "the cloud is the look; it needs no line-work");
  const radii = layout.nodes.map((p) => Math.hypot(p.x, p.y));
  assert.ok(Math.min(...radii) < 30, "the cloud has a dense centre");
  assert.ok(Math.max(...radii) > 240, "and a wide rim");
  assert.equal(new Set(radii.map((r) => r.toFixed(3))).size, 240,
    "two names share a radius - that is a ring, not a cloud");
  const directions = new Set(layout.nodes.map((p) => Math.atan2(p.y, p.x).toFixed(4)));
  assert.ok(directions.size > 230, "the cloud collapsed into a few spokes");
});

/* ── 5e. dna-helix: two strands, rungs, tilted ────────────────────────── */

await check("DNA helix is two backbones joined by one rung per pair, tilted across the picture", async () => {
  const nodes = nodesFor(64);
  const layout = layoutDnaHelix(nodes);
  assert.equal(layout.guides.paths.length, 2, "two backbones");
  assert.equal(layout.guides.lines.length, 32, "one rung for each pair of names");
  // Every name is the end of exactly one rung, and the rungs pair 0-1, 2-3, ...
  const same = (a, b) => Math.abs(a.x - b.x) < 1e-9 && Math.abs(a.y - b.y) < 1e-9;
  for (let i = 0; i < layout.nodes.length; i += 2) {
    const a = layout.nodes[i];
    const b = layout.nodes[i + 1];
    assert.ok(layout.guides.lines.some((line) =>
      (same(a, { x: line.x1, y: line.y1 }) && same(b, { x: line.x2, y: line.y2 }))
        || (same(b, { x: line.x1, y: line.y1 }) && same(a, { x: line.x2, y: line.y2 }))),
    `names ${i} and ${i + 1} share no rung`);
  }
  // It runs across the picture, not up it: a vertical helix would stay inside
  // the wave's own width.
  const widest = Math.max(...layout.nodes.map((p) => Math.abs(p.x)));
  assert.ok(widest > 200, `the helix is not tilted (widest ${widest.toFixed(1)})`);
  assert.ok(nearestPair(layout) >= MIN_GAP - 1e-9, "DNA helix overlaps");
  // An odd list leaves the last name unpaired, never a broken rung.
  const odd = layoutDnaHelix(nodesFor(7));
  assert.equal(odd.guides.lines.length, 3);
  assert.equal(odd.nodes.length, 7);
});

/* ── 5f. radar-dome: a half disc above a horizon + a sweep arm ────────── */

await check("radar dome is a half disc above a horizon, with one sweep arm", async () => {
  const layout = layoutRadarDome(nodesFor(20));
  assert.ok(layout.nodes.every((p) => p.y < 0), "a blip below the horizon");
  assert.deepEqual(layout.rings, [46, 92, 138], "three arcs hold 20 names");
  assert.equal(layout.guides.paths.length, 3, "one arc guide each");
  assert.equal(layout.guides.lines.length, 2, "the horizon and the sweep arm");
  const horizon = layout.guides.lines.find((line) => line.kind === "horizon");
  assert.deepEqual([horizon.y1, horizon.y2], [0, 0], "the horizon is flat");
  const sweep = layout.guides.lines.find((line) => line.kind === "sweep");
  assert.ok(sweep.y2 < 0, "the sweep arm points into the dome");
  // Every name sits exactly on one of the arcs.
  const counts = [expectedDomeCapacity(46), expectedDomeCapacity(92)];
  counts.push(20 - counts[0] - counts[1]);
  let at = 0;
  counts.forEach((count, arc) => {
    for (let k = 0; k < count; k++, at++) {
      const radius = Math.hypot(layout.nodes[at].x, layout.nodes[at].y);
      assert.ok(Math.abs(radius - layout.rings[arc]) < 1e-9,
        `node ${at} left arc ${arc} (r=${radius})`);
    }
  });
  assert.equal(at, 20);
  assert.ok(nearestPair(layout) >= MIN_GAP - 1e-9, "radar dome overlaps");
});

await check("the four bands of the clean tree mean the same thing in the HUD's graph", async () => {
  // The same function serves two graphs: the Brain's people and things, and the
  // HUD's models, ability groups and abilities. Each kind keeps its band's
  // meaning; anything neither graph has falls to the last row.
  const row = (group, index) => cleanTreeRowFor({ group }, index);
  assert.equal(row("person", 9), 1);
  assert.equal(row("pet", 9), 1);
  assert.equal(row("organisation", 9), 2);
  assert.equal(row("project", 9), 2);
  assert.equal(row("place", 9), 3);
  assert.equal(row("model", 9), 1);
  assert.equal(row("cluster", 9), 2);
  assert.equal(row("tool", 9), 2);
  assert.equal(row("whatever", 9), 3);
  assert.equal(row("model", 0), 0, "the core row is still the best-known names");
});


await check("every layout respects the picture's own 240-node bound", async () => {
  assert.equal(MAX_LAYOUT_NODES, MAX_RENDERED_NODES,
    "galaxy-presets.js and galaxy-view.js disagree about the cap");
  const many = nodesFor(500);
  for (const id of ALL_LOOKS) {
    const layout = layoutFor(id, many);
    assert.equal(layout.nodes.length, MAX_LAYOUT_NODES, `${id} ignored the cap`);
    assert.deepEqual(layout.nodes.map((p) => p.id), many.slice(0, MAX_LAYOUT_NODES).map((n) => n.id),
      `${id} did not keep the ranked order`);
    assert.equal(layoutIsUsable(layout, many), true, `${id} fails its own usability guard`);
  }
});

await check("no two names are closer than the layout's gap, at 240 and at every smaller size tried", async () => {
  for (const size of [1, 2, 5, 6, 7, 20, 32, 100, 239, 240]) {
    for (const id of ALL_LOOKS) {
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

await check("only the eight looks can be restored; anything else is the constellation", async () => {
  assert.equal(typeof PRESET_STORAGE_KEY, "string");
  for (const id of ALL_LOOKS) {
    assert.equal(storedPreset(id), id);
    assert.equal(storedPreset(` ${id} `), id, "surrounding whitespace is tolerated");
  }
  assert.equal(storedPreset(DEFAULT_PRESET), DEFAULT_PRESET);
  for (const raw of ["no-such-layout", "zen-ring-2027", "", "  ", null,
                     undefined, 42, { id: "star-map" }]) {
    assert.equal(storedPreset(raw), DEFAULT_PRESET, `stored value ${JSON.stringify(raw)}`);
  }
});

/* ── 8. the keyboard decision, without a page ─────────────────────────── */

await check("hotkeys 1-8 apply their look, and a second press returns to the constellation", async () => {
  for (const preset of BUILT_PRESETS) {
    assert.deepEqual(switchRequest(preset.key, DEFAULT_PRESET),
      { action: "apply", key: preset.key, id: preset.id }, `key ${preset.key}`);
    assert.deepEqual(switchRequest(preset.key, preset.id),
      { action: "apply", key: preset.key, id: DEFAULT_PRESET },
    `pressing the active look's key must go back to the constellation (${preset.id})`);
  }
  // Stepping between two looks works too, not only from the constellation.
  assert.deepEqual(switchRequest("4", "nebula"), { action: "apply", key: "4", id: "dna-helix" });
  // The stage's own keys are not presets: pan/zoom/fit keep working.
  for (const key of ["0", "ArrowLeft", "+", "-", "Escape", "a", "9"]) {
    assert.equal(switchRequest(key, DEFAULT_PRESET), null, `key ${key} was stolen from the stage`);
  }
});

/* ── 9. performance: a switch must not be a noticeable pause ──────────── */

await check("laying out 240 names is fast enough to feel instant (all eight under 250 ms)", async () => {
  const many = nodesFor(240);
  const started = performance.now();
  for (const id of ALL_LOOKS) {
    const layout = layoutFor(id, many);
    assert.equal(layout.nodes.length, 240);
  }
  const elapsed = performance.now() - started;
  assert.ok(elapsed < 250, `eight 240-name layouts took ${elapsed.toFixed(1)} ms`);
  console.log(`      (eight 240-name layouts: ${elapsed.toFixed(1)} ms)`);
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

await check("the real window has the nine chips, all of them usable", async () => {
  const page = await openBrain();
  await gotoGalaxy(page);
  assert.equal(await page.locator("#graph-presets button").count(), 9);
  assert.equal(await page.locator("#graph-presets button:disabled").count(), 0,
    "no look is disabled any more");
  for (const p of BUILT_PRESETS) {
    const label = (await chip(page, p.id).innerText()).replace(/\s+/g, " ");
    assert.match(label, new RegExp(`^${p.key} ${p.label}$`), label);
    assert.equal(await chip(page, p.id).isDisabled(), false, `${p.id} should be usable`);
    assert.match(await chip(page, p.id).getAttribute("title"),
      new RegExp(`Press ${p.key}`), `${p.id} does not say which key chooses it`);
  }
  assert.equal(await chip(page, DEFAULT_PRESET).getAttribute("aria-pressed"), "true");
  // A keyboard/screen-reader user hears the same thing the chips show: the
  // constellation and eight looks on keys 1 to 8, and nothing planned.
  assert.match(await page.locator("#graph-presets").getAttribute("aria-label"),
    /eight looks \(keys 1 to 8\)/);
  assert.doesNotMatch(await page.locator("#graph-presets").getAttribute("aria-label"),
    /not built yet/);
  assert.match(await page.locator(".galaxy-stage").getAttribute("aria-label"),
    /Press 1 to 8 for another look/);
  assert.doesNotMatch(await page.locator(".galaxy-stage").getAttribute("aria-label"),
    /not built/);
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

await check("hotkeys 1-5 draw the five rich looks, each with its own line-work", async () => {
  const page = await openBrain();
  await gotoGalaxy(page);
  const before = await page.locator("#graph-overlay .galaxy-node-button").count();
  // The 32-node fixture: 3 orbits, 31 dendrites, 16 DNA rungs + 2 backbones,
  // 3 dome arcs + the horizon and the sweep arm, and a cloud with no lines.
  const cases = [
    ["planetary-orbit", "1", { paths: 3, lines: 0, circles: 0 }],
    ["neural-arbor", "2", { paths: 0, lines: 31, circles: 0 }],
    ["nebula", "3", { paths: 0, lines: 0, circles: 0 }],
    ["dna-helix", "4", { paths: 2, lines: 16, circles: 0 }],
    ["radar-dome", "5", { paths: 3, lines: 2, circles: 0 }],
  ];
  for (const [id, key, want] of cases) {
    await pressKey(page, key);
    await page.waitForFunction(({ id, want }) => {
      const pressed = document.querySelector(
        `#graph-presets button[data-preset="${id}"]`).getAttribute("aria-pressed");
      const layer = document.querySelector('#graph-svg [data-layer="guides"]');
      if (pressed !== "true" || !layer) return false;
      return layer.querySelectorAll("path").length === want.paths
        && layer.querySelectorAll("line").length === want.lines
        && layer.querySelectorAll("circle").length === want.circles;
    }, { id, want }, { timeout: 5000 });
    assert.equal(await chip(page, id).getAttribute("aria-pressed"), "true", id);
    assert.match(await status(page), new RegExp(`^Layout: ${BUILT_PRESETS.find((p) => p.id === id).label}\\.`));
    assert.equal(await visibleLinks(page), 0, `${id}: the fact-sharing web is still drawn`);
    assert.equal(await page.locator("#graph-overlay .galaxy-node-button").count(), before,
      `${id} changed the set of names`);
    await saveShot(page, `g0-${id}-32.png`);
  }
  // The same key again returns to the constellation, from the last look.
  await pressKey(page, "5");
  await page.waitForFunction(() =>
    document.querySelectorAll('#graph-svg [data-layer="guides"]').length === 0);
  assert.equal(await chip(page, DEFAULT_PRESET).getAttribute("aria-pressed"), "true");
  assert.ok(await visibleLinks(page) > 0, "the constellation's fact links did not come back");
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

await check("with the real 32-node graph every look keeps the dots apart and the labels readable", async () => {
  const page = await openBrain();
  await gotoGalaxy(page);
  let buttonsSeen = 0;
  // `minPx` is what the DRAWN picture must clear. The three flat looks have
  // always been checked at the picture's own 24 px; the tall/shallow rich looks
  // are fitted smaller by the same Fit (a helix 16 rungs long is 710 units
  // high), so their floor is the one that still reads as separate dots.
  for (const [id, key, minPx, minLabels] of [
    ["planetary-orbit", "1", 18, 10],
    ["neural-arbor", "2", 18, 10],
    ["nebula", "3", 18, 8],
    ["dna-helix", "4", 12, 8],
    ["radar-dome", "5", 18, 10],
    ["star-map", "6", 24, 24],
    ["clean-tree", "7", 24, 24],
    ["zen-ring", "8", 24, 24],
  ]) {
    await pressKey(page, key);
    await page.waitForFunction((id) => document.querySelector(
      `#graph-presets button[data-preset="${id}"]`).getAttribute("aria-pressed") === "true",
    id, { timeout: 5000 });
    await page.waitForTimeout(150);
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
    assert.ok(metrics.closest >= minPx,
      `${id}: two dots are only ${metrics.closest.toFixed(1)} px apart on screen`);
    // The labels follow the window's existing rule: the best-connected names,
    // drawn in full, centred on their dot and inside the picture (not clipped).
    // A dense look fits fewer before their boxes would collide; the cap is 24.
    assert.ok(metrics.labels.length >= minLabels,
      `${id}: expected at least ${minLabels} labels, got ${metrics.labels.length}`);
    for (const label of metrics.labels) {
      assert.ok(label.text && label.text.trim().length > 0, `${id}: an empty label`);
      assert.ok(label.centered, `${id}: label "${label.text}" is not centred on its dot`);
      assert.ok(label.inside, `${id}: label "${label.text}" is clipped by the stage`);
    }
    console.log(`      ${id}: closest dots ${metrics.closest.toFixed(1)} px, `
      + `${metrics.labels.length} labels`);
    buttonsSeen = metrics.dots;
  }
  assert.equal(buttonsSeen, 32);
  assert.deepEqual(page.__errors, [], `the page logged errors: ${page.__errors.join("; ")}`);
  await page.close();
});

await check("Fit and the 0 key keep every label inside the picture under each look", async () => {
  const page = await openBrain();
  await gotoGalaxy(page);
  for (const [id, key] of [["planetary-orbit", "1"], ["neural-arbor", "2"], ["nebula", "3"],
    ["dna-helix", "4"], ["radar-dome", "5"], ["star-map", "6"], ["clean-tree", "7"],
    ["zen-ring", "8"]]) {
    await pressKey(page, key);
    await page.waitForFunction((id) => document.querySelector(
      `#graph-presets button[data-preset="${id}"]`).getAttribute("aria-pressed") === "true",
    id, { timeout: 5000 });
    await page.waitForTimeout(150);
    // The two general fit actions must use the wider margin a look needs
    // (audit finding F1): neither may clip the outer labels.
    for (const action of ["0", "Fit"]) {
      if (action === "0") await pressKey(page, "0");
      else await page.locator("#graph-refit").click();
      await page.waitForTimeout(150);
      const clipped = await page.evaluate(() => {
        const stage = document.querySelector(".galaxy-stage").getBoundingClientRect();
        return [...document.querySelectorAll("#graph-overlay .galaxy-node-label")]
          .filter((el) => {
            const r = el.getBoundingClientRect();
            return r.left < stage.left - 2 || r.right > stage.right + 2
              || r.top < stage.top - 2 || r.bottom > stage.bottom + 2;
          })
          .map((el) => el.textContent);
      });
      assert.deepEqual(clipped, [], `${id}: ${action} clipped labels ${clipped.join(", ")}`);
    }
  }
  assert.deepEqual(page.__errors, [], `the page logged errors: ${page.__errors.join("; ")}`);
  await page.close();
});

await check("switching away during the assembly and back leaves a live constellation", async () => {
  const page = await openBrain();
  await page.locator("#rail-advanced-toggle").click();
  await page.locator("#tab-galaxy").click();
  // No wait for the dots: press 6 then 6 while the graph is still loading or
  // assembling (~1.3 s). The return must not restore a frozen mid-assembly
  // snapshot (audit finding F3) - the constellation has to be alive.
  await page.locator(".galaxy-stage").focus();
  await page.keyboard.press("6");
  await page.keyboard.press("6");
  await page.waitForFunction(() =>
    document.querySelectorAll("#graph-overlay .galaxy-node-button").length > 0);
  await page.waitForFunction(() =>
    document.querySelectorAll('#graph-svg [data-layer="guides"]').length === 0);
  assert.ok(await page.locator("#graph-overlay .galaxy-node-button").count() > 0,
    "the constellation did not come back after a mid-assembly switch");
  assert.match(await page.locator("#graph-stat").innerText(), /names/);
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
  // The guides are removed by the constellation's own paint, which lands a frame
  // or two after the key press - the same reason the mid-assembly check above
  // waits for it. Asserting synchronously here failed on this PC's Windows run
  // and in CI run 40060312564 (2026-10-24): the status line and the nodes were
  // already right while the guides layer was still on screen.
  await page.waitForFunction(() =>
    document.querySelectorAll('#graph-svg [data-layer="guides"]').length === 0,
  { timeout: 5000 });
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
