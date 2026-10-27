/**
 * Galaxy rework Phase G0: the three flat layout presets - the pure layouts, the
 * switcher decisions, persistence/fallback, and the real Brain window.
 *
 *     node tests/galaxy-presets.mjs
 *
 * Phase G0 (the owner's answer A/A of 2026-10-23; the Galaxy blueprint, Part B)
 * adds eight flat layouts beside the constellation the desktop already draws:
 * `star-map`, `clean-tree` and `zen-ring` (hotkeys 6/7/8), and - built on
 * 2026-10-27, when the owner asked for "an easy way to change the appearance of
 * the jarvis galaxy to the other models" - `planetary-orbit`, `neural-arbor`,
 * `nebula`, `dna-helix` and `radar-dome` (hotkeys 1-5). Every one is chosen from
 * a menu chip or its hotkey in the Galaxy view. The default view is untouched,
 * nothing is "not built yet" any more, and the choice is remembered on this
 * device only.
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
 *  7. Audit follow-ups (2026-10-23, .dsh-scratch/GALAXY-G0-AUDIT): the Fit button
 *     and the `0` key use the flat layouts' wider margin (so labels stay inside
 *     the picture after a fit, not just after a switch); the chip row and the
 *     stage tell a keyboard/screen-reader user that presets 1-5 are planned and
 *     not built; and switching away during the constellation's assembly and back
 *     leaves a live constellation, never a frozen part-assembled one.
 */
import assert from "node:assert/strict";
import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import * as K from "./uikit.mjs";
import {
  ARBOR_ROWS,
  ARBOR_ROW_PITCH,
  BUILT_PRESETS,
  DEFAULT_PRESET,
  DOME_BASE,
  DOME_GROUND_DROP,
  DOME_PITCH,
  HELIX_AMPLITUDE,
  HELIX_STEPS_PER_TURN,
  MAX_LAYOUT_NODES,
  MIN_GAP,
  NEBULA_SPACING,
  PLANET_ASPECT,
  PLANET_B0,
  PLANET_PITCH,
  PLANNED_PRESETS,
  PRESET_MENU,
  PRESET_STORAGE_KEY,
  TREE_CORE,
  TREE_ROWS,
  TREE_ROW_Y,
  ZEN_HALO_GAP,
  ZEN_MAX_CHORDS,
  ZEN_RADIUS,
  arborRowCounts,
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

/** Every look the module builds, in hotkey order. Read from the module, so a
 *  look added there is covered here without editing this list. */
const LOOK_IDS = BUILT_PRESETS.map((p) => p.id);

/** The same eight as `[id, hotkey, plain label]`, in the order a person meets
 *  them: the five rich looks first (keys 1-5), then the three flat ones. */
const FLAT_LOOKS = BUILT_PRESETS.map((p) => [p.id, p.key, p.label]);

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

await check("all eight looks are built; keys 1-8 are theirs; nothing is planned any more", async () => {
  assert.equal(DEFAULT_PRESET, "constellation");
  assert.deepEqual(LOOK_IDS, ["planetary-orbit", "neural-arbor", "nebula", "dna-helix",
    "radar-dome", "star-map", "clean-tree", "zen-ring"]);
  assert.deepEqual(BUILT_PRESETS.map((p) => p.key), ["1", "2", "3", "4", "5", "6", "7", "8"]);
  assert.deepEqual(PLANNED_PRESETS, [], "a look is still listed as planned and not built");
  assert.equal(presetMeta(DEFAULT_PRESET).built, true);
  for (const look of BUILT_PRESETS) {
    assert.equal(presetMeta(look.id).built, true, `${look.id} is not marked built`);
    assert.equal(plannedForKey(look.key), null,
      `${look.id}'s hotkey is still answered by the not-built list`);
  }
  assert.equal(PRESET_MENU.length, 1 + BUILT_PRESETS.length);
  assert.equal(new Set(PRESET_MENU.map((p) => p.id)).size, PRESET_MENU.length, "duplicate preset id");
  assert.equal(PRESET_MENU.filter((p) => !p.built).length, 0, "a menu entry still says not built");
  assert.equal(presetForKey("1").id, "planetary-orbit");
  assert.equal(presetForKey("5").id, "radar-dome");
  assert.equal(presetForKey("8").id, "zen-ring");
  assert.equal(presetForKey("9"), null);
  assert.equal(plannedForKey("3"), null, "the nebula is built now");
  assert.equal(plannedForKey("6"), null);
});

await check("the menu names every built look and says nothing is 'not built yet'", async () => {
  for (const meta of PRESET_MENU) {
    assert.equal(meta.built, true, `${meta.id} is in the menu as not built`);
    assert.ok(meta.label && meta.label.trim().length > 1, `${meta.id} has no plain name`);
    assert.doesNotMatch(presetStatus(meta.id), /not built/i,
      `the status line still says ${meta.id} is not built`);
  }
  assert.match(presetStatus("star-map"), /^Layout: Star map\./);
  assert.match(presetStatus("planetary-orbit"), /^Layout: Planetary orbit\. Press its key again/);
  assert.match(presetStatus("nebula"), /^Layout: Nebula\./);
  assert.match(presetStatus(DEFAULT_PRESET), /constellation/);
  assert.equal(presetStatus("nope"), "");
});

/* ── 2. pure + deterministic ──────────────────────────────────────────── */

await check("the same list lays out the same way twice, every time - and is not mutated", async () => {
  for (const id of LOOK_IDS) {
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

/* ── 5b. the five rich looks built on 2026-10-27 ──────────────────────── */

await check("planetary orbit is one sun and homothetic ellipses around it", async () => {
  const layout = layoutPlanetaryOrbit(nodesFor(40));
  assert.deepEqual([layout.nodes[0].x, layout.nodes[0].y], [0, 0], "the first name is the sun");
  assert.ok(layout.rings.length >= 2, "40 names should need at least two orbits");
  assert.deepEqual(layout.rings.slice(0, 2), [PLANET_B0, PLANET_B0 + PLANET_PITCH],
    "orbits are a pitch apart, starting at the module's own first axis");
  // Every other name lies ON one of those ellipses:
  // (x/a)^2 + (y/b)^2 = 1 with a = b * PLANET_ASPECT.
  for (const point of layout.nodes.slice(1)) {
    const onOrbit = layout.rings.some((b) => {
      const a = b * PLANET_ASPECT;
      return Math.abs((point.x / a) ** 2 + (point.y / b) ** 2 - 1) < 0.02;
    });
    assert.ok(onOrbit, `a name at (${point.x.toFixed(1)}, ${point.y.toFixed(1)}) is on no orbit`);
  }
  assert.equal(layout.guides.circles.length, 0, "orbits are ellipses, not circles");
  assert.equal(layout.guides.paths.length, layout.rings.length, "one faint ellipse per orbit");
  for (const orbit of layout.guides.paths) {
    assert.equal(orbit.kind, "orbit");
    assert.match(orbit.d, /^M .* Z$/, "an orbit is a closed path");
    // The same ellipse as numbers, for a renderer that does not parse `d`.
    assert.ok(orbit.a > orbit.b, "an orbit's long axis is its semi-major axis");
    assert.ok(Math.abs(orbit.a / orbit.b - PLANET_ASPECT) < 1e-6, "an orbit has the family's shape");
  }
});

await check("neural arbor is a crown of rows widening upward, with dendrites down", async () => {
  const layout = layoutNeuralArbor(nodesFor(40));
  const counts = arborRowCounts(40);
  assert.deepEqual(counts, [1, 2, 3, 5, 8, 21], "the crown's rows are the module's own");
  assert.equal(counts.reduce((total, n) => total + n, 0), 40, "the rows hold exactly the list");
  for (let i = 1; i < counts.length; i++) {
    assert.ok(counts[i] >= counts[i - 1], `row ${i + 1} is narrower than row ${i}`);
  }
  assert.equal(layout.rows.length, counts.length, "one guide line per row");
  for (let i = 1; i < layout.rows.length; i++) {
    // Canvas y grows DOWNWARD, so the crown's next row up is a pitch SMALLER.
    assert.equal(layout.rows[i - 1] - layout.rows[i], ARBOR_ROW_PITCH,
      "rows keep the module's pitch");
  }
  // Every name's y IS its row's line, the rows are centred, and the root is alone.
  let at = 0;
  counts.forEach((count, row) => {
    const onRow = layout.nodes.slice(at, at + count);
    for (const point of onRow) {
      assert.equal(point.y, layout.rows[row], `${point.id} is not on its row's line`);
    }
    if (count > 1) {
      const xs = onRow.map((p) => p.x);
      assert.equal(new Set(xs.map((x) => x.toFixed(4))).size, count,
        `row ${row + 1} has two names at one x`);
      for (let i = 1; i < xs.length; i++) {
        assert.ok(Math.abs(xs[i] - xs[i - 1]) >= MIN_GAP - 1e-9,
          `row ${row + 1} has neighbours closer than a gap`);
      }
      assert.ok(Math.abs(xs[0] + xs[xs.length - 1]) < 1e-9, `row ${row + 1} is not centred`);
    }
    at += count;
  });
  assert.equal(layout.nodes[0].x, 0, "the root is not centred over its crown");
  assert.ok(layout.guides.lines.length > 0, "the arbor has no dendrites");
  assert.ok(layout.guides.lines.length <= 120, "the arbor drew too many dendrites");
  for (const line of layout.guides.lines) {
    assert.equal(line.kind, "dendrite");
    const ends = [line, line].map((shape, which) => {
      const x = which ? shape.x2 : shape.x1;
      const y = which ? shape.y2 : shape.y1;
      return layout.nodes.some((p) => Math.abs(p.x - x) < 1e-6 && Math.abs(p.y - y) < 1e-6);
    });
    assert.deepEqual(ends, [true, true], "a dendrite does not start and end on two names");
  }
});

await check("nebula is one soft cloud: no rings, no rows, no guides", async () => {
  const layout = layoutNebula(nodesFor(60));
  assert.deepEqual(layout.rings, [], "a cloud has no rings");
  assert.deepEqual(layout.rows, [], "a cloud has no rows");
  assert.deepEqual(layout.guides.circles, [], "a cloud has no guide circles");
  assert.deepEqual(layout.guides.lines, [], "a cloud has no guide lines");
  assert.deepEqual(layout.guides.paths, [], "a cloud has no guide paths");
  // Nothing lines up: no two names share a row or a column, which is what stops
  // it reading as a grid.
  const ys = layout.nodes.map((p) => p.y.toFixed(3));
  const xs = layout.nodes.map((p) => p.x.toFixed(3));
  assert.equal(new Set(ys).size, ys.length, "two names share a row");
  assert.equal(new Set(xs).size, xs.length, "two names share a column");
  const first = Math.hypot(layout.nodes[0].x, layout.nodes[0].y);
  const last = Math.hypot(layout.nodes[59].x, layout.nodes[59].y);
  assert.ok(last > first * 4, "the cloud did not grow outward");
  assert.equal(layout.minGap, MIN_GAP);
  assert.ok(NEBULA_SPACING > 1, "the cloud's spacing is looser than one gap");
});

await check("DNA helix is two strands twisting up each column, with a rung per row", async () => {
  const layout = layoutDnaHelix(nodesFor(40));
  assert.deepEqual(layout.rings, []);
  // Consecutive names are one row apart down a column, so their y difference is
  // at least a gap - the module's own no-overlap argument for this look.
  for (let i = 1; i < layout.nodes.length; i++) {
    assert.ok(Math.abs(layout.nodes[i].y - layout.nodes[i - 1].y) >= MIN_GAP - 1e-9,
      `names ${i - 1} and ${i} are less than a gap apart down the helix`);
  }
  // The two strands: consecutive names sit on opposite sides of their column's
  // axis, and the sideways offset is a cosine of the row (one turn every
  // HELIX_STEPS_PER_TURN rows), which is what makes the pair a twist.
  const columns = Math.max(1, Math.min(8, Math.round(Math.sqrt(40 / 6)) || 1));
  const perColumn = Math.ceil(40 / columns);
  const columnPitch = HELIX_AMPLITUDE * 2 + 30;
  for (let column = 0; column < columns; column++) {
    const first = column * perColumn;
    const rows = Math.min(perColumn, 40 - first);
    const centreX = (column - (columns - 1) / 2) * columnPitch;
    for (let k = 0; k < rows; k++) {
      const want = (k % 2 === 0 ? 1 : -1) * HELIX_AMPLITUDE
        * Math.cos(k * ((Math.PI * 2) / HELIX_STEPS_PER_TURN));
      assert.ok(Math.abs((layout.nodes[first + k].x - centreX) - want) < 1e-6,
        `row ${k} of column ${column + 1} is not on its strand`);
    }
  }
  // One rung between each pair of neighbouring rows, capped.
  assert.ok(layout.guides.paths.length > 0, "the helix has no rungs");
  assert.ok(layout.guides.paths.length <= 120, "the helix drew too many rungs");
  for (const rung of layout.guides.paths) {
    assert.equal(rung.kind, "rung");
    assert.ok(Number.isFinite(rung.x1) && Number.isFinite(rung.y2), "a rung has no numeric ends");
    assert.match(rung.d, /^M .* L .*$/, "a rung is a straight line between the two strands");
  }
});

await check("radar dome puts every name above a horizon, on arcs over a ground row", async () => {
  const layout = layoutRadarDome(nodesFor(40));
  const ground = layout.nodes.filter((p) => p.y > 0);
  assert.ok(ground.length >= 2, "the dome has no ground row");
  for (const point of ground) {
    assert.equal(point.y, DOME_GROUND_DROP, "a ground-row name is off the horizon line");
  }
  for (const point of layout.nodes.filter((p) => p.y <= 0)) {
    assert.ok(point.y < 0, "a dome name sits on the horizon instead of above it");
  }
  assert.ok(layout.rings.length >= 1, "the dome has no arcs");
  assert.equal(layout.rings[0], DOME_BASE, "the dome starts at the module's own first arc");
  for (let i = 1; i < layout.rings.length; i++) {
    assert.equal(layout.rings[i] - layout.rings[i - 1], DOME_PITCH, "the arcs keep one pitch");
  }
  assert.equal(layout.guides.circles.length, layout.rings.length, "one faint circle per arc");
  for (const circle of layout.guides.circles) {
    assert.equal(circle.kind, "dome");
    assert.ok(layout.rings.includes(circle.r), "a guide circle is not one of the arcs");
  }
  for (const point of layout.nodes.filter((p) => p.y < 0)) {
    const radius = Math.hypot(point.x, point.y);
    assert.ok(layout.rings.some((r) => Math.abs(radius - r) < 1e-6),
      `a dome name at radius ${radius.toFixed(1)} is on no arc`);
  }
  assert.equal(layout.guides.lines.length, 6, "the dome's six bearing spokes");
  assert.deepEqual(layout.rows, [DOME_GROUND_DROP]);
});

await check("the eight looks are eight different arrangements, not recolours", async () => {
  const nodes = nodesFor(40);
  const signatures = new Map();
  for (const id of LOOK_IDS) {
    const layout = layoutFor(id, nodes);
    const key = JSON.stringify(layout.nodes.map((p) => [Math.round(p.x * 100), Math.round(p.y * 100)]));
    assert.ok(!signatures.has(key), `${id} draws exactly the same picture as ${signatures.get(key)}`);
    signatures.set(key, id);
  }
  assert.equal(signatures.size, LOOK_IDS.length);
  // Each also has its own proportions: the ratio of a look's widest span to its
  // tallest is not another look's, which is what stops five of them reading as
  // one shape in five colours.
  const shapes = LOOK_IDS.map((id) => {
    const layout = layoutFor(id, nodes);
    const xs = layout.nodes.map((p) => p.x);
    const ys = layout.nodes.map((p) => p.y);
    const wide = Math.max(...xs) - Math.min(...xs);
    const tall = Math.max(...ys) - Math.min(...ys);
    return { id, ratio: +(wide / Math.max(1, tall)).toFixed(2) };
  });
  const distinct = new Set(shapes.map((s) => s.ratio));
  assert.ok(distinct.size >= 6,
    `only ${distinct.size} of ${shapes.length} looks have their own proportions: `
    + shapes.map((s) => `${s.id} ${s.ratio}`).join(", "));
  console.log(`      shapes: ${shapes.map((s) => `${s.id} ${s.ratio}`).join(", ")}`);
});

/* ── 6. the bound, no overlap, and the safe fallback guard ────────────── */

await check("every layout respects the picture's own 240-node bound", async () => {
  assert.equal(MAX_LAYOUT_NODES, MAX_RENDERED_NODES,
    "galaxy-presets.js and galaxy-view.js disagree about the cap");
  const many = nodesFor(500);
  for (const id of LOOK_IDS) {
    const layout = layoutFor(id, many);
    assert.equal(layout.nodes.length, MAX_LAYOUT_NODES, `${id} ignored the cap`);
    assert.deepEqual(layout.nodes.map((p) => p.id), many.slice(0, MAX_LAYOUT_NODES).map((n) => n.id),
      `${id} did not keep the ranked order`);
    assert.equal(layoutIsUsable(layout, many), true, `${id} fails its own usability guard`);
  }
});

await check("no two names are closer than the layout's gap, at 240 and at every smaller size tried", async () => {
  for (const size of [1, 2, 5, 6, 7, 20, 100, 239, 240]) {
    for (const id of LOOK_IDS) {
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
  for (const id of LOOK_IDS) {
    assert.equal(storedPreset(id), id);
    assert.equal(storedPreset(` ${id} `), id, "surrounding whitespace is tolerated");
  }
  assert.equal(storedPreset(DEFAULT_PRESET), DEFAULT_PRESET);
  for (const raw of ["no-such-layout", "constellation ", "", "  ", null,
                     undefined, 42, { id: "star-map" }]) {
    assert.equal(storedPreset(raw), DEFAULT_PRESET, `stored value ${JSON.stringify(raw)}`);
  }
});

/* ── 8. the keyboard decision, without a page ─────────────────────────── */

await check("hotkeys 1-8 apply a layout, a second press returns to the constellation", async () => {
  assert.deepEqual(switchRequest("1", DEFAULT_PRESET),
    { action: "apply", key: "1", id: "planetary-orbit" });
  assert.deepEqual(switchRequest("3", "star-map"), { action: "apply", key: "3", id: "nebula" });
  assert.deepEqual(switchRequest("6", DEFAULT_PRESET), { action: "apply", key: "6", id: "star-map" });
  assert.deepEqual(switchRequest("7", "star-map"), { action: "apply", key: "7", id: "clean-tree" });
  assert.deepEqual(switchRequest("8", "clean-tree"), { action: "apply", key: "8", id: "zen-ring" });
  assert.deepEqual(switchRequest("8", "zen-ring"),
    { action: "apply", key: "8", id: DEFAULT_PRESET },
  "pressing the active preset's key goes back to the constellation");
  assert.deepEqual(switchRequest("5", "radar-dome"),
    { action: "apply", key: "5", id: DEFAULT_PRESET });
  // The stage's own keys are not presets: pan/zoom/fit keep working.
  for (const key of ["0", "ArrowLeft", "+", "-", "Escape", "a", "9"]) {
    assert.equal(switchRequest(key, DEFAULT_PRESET), null, `key ${key} was stolen from the stage`);
  }
});

await check("every hotkey asks for a look that really lays out", async () => {
  for (const look of BUILT_PRESETS) {
    const request = switchRequest(look.key, DEFAULT_PRESET);
    assert.equal(request.action, "apply", `${look.key} did not ask to apply a look`);
    const layout = layoutFor(request.id, nodesFor(20));
    assert.ok(layout, `${look.key} names ${request.id}, which has no layout`);
    assert.equal(layout.id, request.id, `${look.key} drew ${layout.id}`);
  }
});

/* ── 9. performance: a switch must not be a noticeable pause ──────────── */

await check("laying out 240 names is fast enough to feel instant (all eight under 250 ms)", async () => {
  const many = nodesFor(240);
  const started = performance.now();
  for (const id of LOOK_IDS) {
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

/** Wait until the status line says this look is the one on screen - the one
 *  signal every flat look gives, including the nebula (which has no guides). */
async function waitForLook(page, label) {
  await page.waitForFunction(
    ({ want }) => document.getElementById("graph-preset-status").textContent
      .startsWith(`Layout: ${want}.`),
    { want: label });
}
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

await check("the real window has the nine chips and every one of them works", async () => {
  const page = await openBrain();
  await gotoGalaxy(page);
  assert.equal(await page.locator("#graph-presets button").count(), 1 + BUILT_PRESETS.length);
  assert.equal(await page.locator("#graph-presets button:disabled").count(), 0,
    "a chip is still disabled - nothing is 'not built yet' since 2026-10-27");
  for (const look of BUILT_PRESETS) {
    const label = (await chip(page, look.id).innerText()).replace(/\s+/g, " ");
    assert.equal(label, `${look.key} ${look.label}`, `${look.id}'s chip does not name its key`);
    assert.equal(await chip(page, look.id).isDisabled(), false, `${look.id} is not usable`);
  }
  assert.equal(await chip(page, DEFAULT_PRESET).getAttribute("aria-pressed"), "true");
  // Nothing in the window may still tell the owner a look does not exist.
  assert.doesNotMatch(await page.locator("#graph-presets").innerText(), /not built/i);
  assert.doesNotMatch(await page.locator("#graph-presets").getAttribute("aria-label"),
    /not built|planned/i);
  assert.match(await page.locator(".galaxy-stage").getAttribute("aria-label"),
    /Press 1 to 8 for a layout/);
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

await check("hotkey 1 draws the planetary orbits, and 3 the cloud with no guides at all", async () => {
  const page = await openBrain();
  await gotoGalaxy(page);
  await pressKey(page, "1");
  await waitForLook(page, "Planetary orbit");
  assert.equal(await chip(page, "planetary-orbit").getAttribute("aria-pressed"), "true");
  assert.ok(await guides(page, "path.galaxy-guide-chord").count() >= 2,
    "the planetary orbit drew no orbits");
  assert.equal(await guides(page, "line.galaxy-guide-line").count(), 0,
    "the planetary orbit is not a star map: it has no spokes");
  assert.equal(await visibleLinks(page), 0,
    "a flat look must not draw the constellation's fact-sharing web");
  await saveShot(page, "g0-planetary-orbit-32.png");
  // The nebula is the one look with NO guides: it is a cloud, and the page must
  // draw nothing under it rather than leaving the last look's rings behind.
  await pressKey(page, "3");
  await waitForLook(page, "Nebula");
  assert.equal(await guides(page, "path.galaxy-guide-chord").count(), 0,
    "the nebula kept the planetary orbits' guide paths");
  assert.equal(await guides(page, "circle.galaxy-guide-ring").count(), 0);
  assert.equal(await visibleLinks(page), 0);
  await saveShot(page, "g0-nebula-32.png");
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
  for (const [id, key, label] of FLAT_LOOKS) {
    await pressKey(page, key);
    await waitForLook(page, label);
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

await check("Fit and the 0 key keep every label inside the picture under each flat layout", async () => {
  const page = await openBrain();
  await gotoGalaxy(page);
  for (const [id, key, label] of FLAT_LOOKS) {
    await pressKey(page, key);
    await waitForLook(page, label);
    // The two general fit actions must use the wider margin a flat layout needs
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
