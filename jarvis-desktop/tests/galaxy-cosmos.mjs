/**
 * The 3D cosmos: the eight looks from the Gemini page, ported onto the HUD's
 * real graph - proved as pure maths, with no browser and no three.js.
 *
 *     node tests/galaxy-cosmos.mjs
 *
 * WHY THIS SUITE EXISTS
 *
 * The owner, 2026-10-27: "none of the galaxy on the current jarvis hud look
 * like the one that gemini made... i would to simplify all the galaxy
 * options". He chose the exact 3D port, and Planetary Orrery as the default
 * look. `src/galaxy-cosmos.js` is that engine; this suite is the half of it
 * that can be proved without a GPU.
 *
 * WHAT IT HOLDS
 *
 *  1. THE EIGHT LOOKS ARE THE REPOSITORY'S EIGHT. Their ids are exactly
 *     `galaxy-presets.js`'s `BUILT_PRESETS` ids, in hotkey order, so the look
 *     switcher and the Brain window cannot list one thing while the 3D engine
 *     draws another. Each carries Gemini's own palette, camera and look-at,
 *     compared number by number against the reference page.
 *  2. THE CAMERA IS GEMINI'S UNTIL A NAME WOULD LEAVE THE FRAME. A picture that
 *     already fits gets the page's exact position; a 120- or 240-name one backs
 *     away along the same direction, and only the distance changes. The frame
 *     itself is proved in 8.
 *  3. THE THREE FIELDS THE BACKEND DOES NOT SEND ARE DERIVED, NOT INVENTED.
 *     `ringOf` (the radar look's three rings), `wellOf` (the nebula's four
 *     wells) and `timeFractions` (the helix's order) are pure functions over
 *     data `/api/graph` really sends; each is pinned here, including the
 *     no-timestamp fallback.
 *  4. GEMINI'S GEOMETRY AT GEMINI'S SIZE. At 32 names every look reproduces the
 *     page's radii, wave amplitudes, row heights and guide bodies exactly; at
 *     240 names a ring that cannot hold its names grows outward instead of
 *     crowding, which is the one deliberate deviation and is measured here.
 *  5. THE GUIDE BODIES ARE THE PAGE'S, COUNTED: three ecliptic rings, three
 *     hexagonal cortical plates with six trunks, twelve twigs and six roots,
 *     four nebula wells, thirty-six helix rungs, three radar zones with four
 *     crosshairs, seven star-map spokes, four tree baselines, one zen halo.
 *  6. THE SKY IS DETERMINISTIC: 1,800 stars and 3,200 nebula points from a
 *     seeded generator, so the same build draws the same sky twice.
 *  7. BUDGETS: at most 240 names and 360 links, in the order given, and the
 *     input is never mutated.
 *  8. EVERY REAL NAME IS INSIDE A COMFORTABLE FRAME, which is the one thing the
 *     reference page gets wrong and this port must not copy. At 1440x900 - and
 *     on the HUD's real stage shapes - with 32, 120 and 240 names, in all eight
 *     looks, at rest and around the orrery's orbit: every name's centre is
 *     within `FRAME_FILL` (82%) of the half-frame, there is room for its label
 *     above it on the canvas, and the picture still fills the frame. The fog is
 *     proved in the same place: it thins with the camera, so a 240-name picture
 *     is not fogged to black.
 *  9. THE FRAME BUDGET IS TWO RULES, NOT ONE. A slow renderer first loses
 *     PIXELS: the 3D canvas steps down to `RENDER_SCALE_MIN` while the label
 *     canvas and the picture's size on screen never move. A renderer still slow
 *     after that draws every OTHER frame, so the motion steps instead of the
 *     page freezing. Both halves are pinned here as pure maths - that a fast
 *     machine never rises above the display's own ratio, that a slow one only
 *     ever steps down and stops at the floor, and that a picture which got cheap
 *     earns its pixels back one step at a time. The thresholds themselves are
 *     pinned too, so the half-rate switch cannot drift away from the resolution
 *     rule that is supposed to have gone first.
 *
 *     AND THE PIXELS COME BACK ON A 30 Hz SCREEN. A display that presents every
 *     33.3 ms never looks "fast", so the fast threshold alone left a picture
 *     that had stepped down soft until reload (audit B1, finding 4). The
 *     probational climb is pinned here as maths too: a steady 30 Hz picture
 *     recovers full resolution, a genuinely slow one never leaves the floor and
 *     takes the half rate exactly once, a refused probe puts the picture back
 *     unchanged and asks less and less often, and a picture finds the
 *     resolution it can really afford instead of guessing.
 *
 * The render layer (three.js, the GPU, the canvas) is proved by the HUD suites
 * and by CI's browser run, not here.
 */
import assert from "node:assert/strict";

import {
  CAMERA_FOV,
  COSMOS_DEFAULT_LOOK,
  COSMOS_PRESET_ORDER,
  COSMOS_PRESETS,
  FAST_FRAME_MS,
  FOG_DENSITY,
  FRAME_FILL,
  HELIX_PER_COLUMN,
  MAX_COSMOS_LINKS,
  MAX_COSMOS_NODES,
  MIN_GAP,
  NEBULA_POINTS,
  NEBULA_WELLS,
  PRESET_ACTIONS,
  PROBE_BACKOFF_MAX,
  PROBE_BACKOFF_SAMPLES,
  PROBE_STEADY_MS,
  PROBE_STEADY_SAMPLES,
  RENDER_SCALE_MIN,
  ROLE_OF_GROUP,
  SENTINEL_RINGS,
  SLOW_FRAME_MS,
  STAR_COUNT,
  TONE_EXPOSURE,
  VERY_SLOW_FRAME_MS,
  ZEN_HALO_GAP,
  actionsFor,
  boundsOf,
  budgetLinks,
  budgetNodes,
  byRole,
  cameraFor,
  cameraFrame,
  createFrameScale,
  fitDistance,
  fogDensityAt,
  hexToInt,
  hexToRgb,
  isCosmosLook,
  mulberry32,
  nebulaCloud,
  nextFrameScale,
  nextRenderScale,
  parentOf,
  presetGuides,
  presetLinks,
  presetMeta,
  presetPositions,
  projectPoint,
  ringCapacity,
  ringOf,
  ringPlan,
  roleOf,
  stampOf,
  starField,
  timeFractions,
  treeRow,
  wellOf,
} from "../src/galaxy-cosmos.js";
import { BUILT_PRESETS, DEFAULT_PRESET } from "../src/galaxy-presets.js";

const fails = [];
let passed = 0;

function check(name, fn) {
  try {
    fn();
    passed += 1;
    console.log(`ok   ${name}`);
  } catch (error) {
    fails.push({ name, error });
    console.log(`FAIL ${name}\n     ${error && error.message ? error.message : error}`);
  }
}

/* -------------------------------------------------------------------------
 * Fixtures: a graph shaped the way /api/graph sends it
 * ---------------------------------------------------------------------- */

/** The HUD's eleven groups, one node each, plus repeat nodes per group. */
function graphOf(counts) {
  const nodes = [];
  const links = [];
  for (const [group, count] of Object.entries(counts)) {
    for (let i = 0; i < count; i++) {
      nodes.push({
        id: group === "core" ? "core" : `${group}:${i + 1}`,
        label: `${group} ${i + 1}`,
        group,
        weight: 1 + (i % 3),
      });
    }
  }
  // cluster -> tool "has" links, the shape the backend really sends
  const clusters = nodes.filter((n) => n.group === "cluster");
  const tools = nodes.filter((n) => n.group === "tool");
  tools.forEach((tool, i) => {
    const cluster = clusters[i % Math.max(1, clusters.length)];
    if (cluster) links.push({ source: cluster.id, target: tool.id, kind: "has" });
  });
  nodes.filter((n) => n.group === "model").forEach((model, i) => {
    links.push({ source: "core", target: model.id, kind: "runs" });
    if (tools[i]) links.push({ source: model.id, target: tools[i].id, kind: "uses" });
  });
  clusters.forEach((cluster) => {
    links.push({ source: "core", target: cluster.id, kind: "runs" });
  });
  return { nodes, links };
}

/** Gemini's own picture size: 1 core, 4 brains, 7 groups, 12 tools, 8 saved. */
function geminiShaped() {
  return graphOf({
    core: 1, model: 4, cluster: 7, tool: 12, fact: 5, document: 1, project: 1, source: 1,
  });
}

/** A graph at one of the HUD's own budgets, shaped like `/api/graph` really is:
 *  one core, the brains and ability groups that exist, and the rest saved
 *  things. `size` names are returned exactly, so 120 and 240 are the page's
 *  two caps rather than approximations of them. */
function budgetGraph(size) {
  const spec = [
    ["core", 1], ["model", 4], ["cluster", 6], ["tool", 40], ["fact", 25],
    ["document", 10], ["entity", 8], ["project", 6], ["persona", 4],
    ["source", 12], ["skill", 4],
  ];
  const total = spec.reduce((sum, [, count]) => sum + count, 0);
  const nodes = [];
  for (const [group, count] of spec) {
    const want = Math.max(1, Math.round((count * size) / total));
    for (let i = 0; i < want && nodes.length < size; i++) {
      nodes.push({
        id: group === "core" ? "core" : `${group}:${i + 1}`,
        label: `${group} ${i + 1}`,
        group,
        weight: 1 + (i % 3),
      });
    }
  }
  while (nodes.length < size) {
    nodes.push({ id: `fact:extra${nodes.length}`, label: `note ${nodes.length}`,
      group: "fact", weight: 1 });
  }
  return nodes;
}

function nearest(positions) {
  let worst = Infinity;
  for (let i = 0; i < positions.length; i++) {
    for (let j = i + 1; j < positions.length; j++) {
      const a = positions[i];
      const b = positions[j];
      worst = Math.min(worst, Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z));
    }
  }
  return worst;
}

/* -------------------------------------------------------------------------
 * 1. The eight looks, and the repository's own look ids
 * ---------------------------------------------------------------------- */

check("the eight 3D looks are exactly the repository's eight looks, in hotkey order",
  () => {
    assert.deepEqual(COSMOS_PRESET_ORDER, BUILT_PRESETS.map((p) => p.id));
    assert.equal(COSMOS_PRESET_ORDER.length, 8);
    for (const id of COSMOS_PRESET_ORDER) assert.ok(isCosmosLook(id), `${id} is not a look`);
    // The constellation is not one of them: it is the physics picture, and the
    // fallback, and this engine must never claim it.
    assert.equal(DEFAULT_PRESET, "constellation");
    assert.equal(isCosmosLook(DEFAULT_PRESET), false);
    assert.equal(presetMeta(DEFAULT_PRESET), null);
    assert.equal(presetMeta("not-a-look"), null);
  });

check("the default look is the Planetary Orrery, and it is a look", () => {
  assert.equal(COSMOS_DEFAULT_LOOK, "planetary-orbit");
  assert.ok(isCosmosLook(COSMOS_DEFAULT_LOOK));
  assert.equal(COSMOS_PRESETS[COSMOS_DEFAULT_LOOK].gemini, "cosmos");
});

check("every look carries Gemini's own palette and camera, number by number", () => {
  const reference = {
    "planetary-orbit": ["cosmos", "#030712", [0, 150, 230], [0, 0, 0]],
    "neural-arbor": ["neural", "#090418", [0, 45, 235], [0, 6, 0]],
    nebula: ["memory", "#0c0612", [65, 80, 185], [0, 0, 0]],
    "dna-helix": ["helix", "#021014", [165, 15, 165], [0, 0, 0]],
    "radar-dome": ["sentinel", "#070b0e", [0, 215, 135], [0, 0, 0]],
    "star-map": ["flat", "#040914", [0, 255, 4], [0, 0, 0]],
    "clean-tree": ["tree", "#050a12", [0, 8, 240], [0, 0, 0]],
    "zen-ring": ["ring", "#03060c", [0, 240, 25], [0, 0, 0]],
  };
  assert.deepEqual(Object.keys(COSMOS_PRESETS).sort(), Object.keys(reference).sort());
  for (const [id, [gemini, bg, camera, lookAt]] of Object.entries(reference)) {
    const meta = COSMOS_PRESETS[id];
    assert.equal(meta.gemini, gemini, `${id}: Gemini's own id`);
    assert.equal(meta.bg, bg, `${id}: background/fog colour`);
    assert.deepEqual([...meta.camera], camera, `${id}: camera position`);
    assert.deepEqual([...meta.lookAt], lookAt, `${id}: look-at`);
    assert.deepEqual(cameraFor(id), { position: camera, lookAt }, `${id}: cameraFor`);
  }
});

check("the page's fog, exposure and field of view are the rendered ones", () => {
  assert.equal(FOG_DENSITY, 0.0016);
  assert.equal(TONE_EXPOSURE, 1.25);
  assert.equal(CAMERA_FOV, 45);
  assert.equal(STAR_COUNT, 1800);
  assert.equal(NEBULA_POINTS, 3200);
});

check("the camera is Gemini's until a name would leave the comfortable frame", () => {
  // A two-name picture is far inside Gemini's own frame: his position, exactly,
  // for the six looks whose own cameras already frame it. (The other two pull
  // back a little: their base camera puts a name at the very edge.)
  const tiny = [{ id: "core", group: "core" }, { id: "fact:1", group: "fact" }];
  let kept = 0;
  for (const id of COSMOS_PRESET_ORDER) {
    const at = presetPositions(id, tiny);
    const framed = cameraFrame(id, { positions: at, aspect: 1.6 });
    const base = cameraFor(id);
    assert.deepEqual(framed.lookAt, base.lookAt, `${id}: the look-at moved`);
    assert.equal(framed.fill, FRAME_FILL);
    if (!framed.fitted) {
      kept += 1;
      assert.deepEqual(framed.position, base.position, `${id}: a kept camera changed`);
    } else {
      // Only the distance changes: the offset stays parallel to Gemini's own.
      const was = [base.position[0] - base.lookAt[0], base.position[1] - base.lookAt[1],
        base.position[2] - base.lookAt[2]];
      const now = [framed.position[0] - base.lookAt[0], framed.position[1] - base.lookAt[1],
        framed.position[2] - base.lookAt[2]];
      const cross = [
        was[1] * now[2] - was[2] * now[1],
        was[2] * now[0] - was[0] * now[2],
        was[0] * now[1] - was[1] * now[0],
      ];
      assert.ok(Math.hypot(...cross) < 1e-6, `${id}: the angle changed, not just the distance`);
      assert.ok(framed.distance > Math.hypot(...was), `${id}: a pull-back came closer`);
    }
  }
  assert.ok(kept >= 6, `only ${kept} of 8 looks keep Gemini's own camera on a two-name picture`);

  // The radius-only path is the conservative whole-sphere rule (a caller with no
  // positions): it can only be further out than the flat-fit distance.
  const sphere = cameraFrame("star-map", { radius: 280, aspect: 1.6 });
  assert.equal(sphere.fitted, true);
  assert.ok(sphere.distance > fitDistance(280, 1.6));
  const near = cameraFrame("planetary-orbit", { radius: 40, aspect: 1.6 });
  assert.equal(near.fitted, false);
  assert.deepEqual(near.position, cameraFor("planetary-orbit").position);
});

check("every name sits inside a comfortable frame at 1440x900, at 120 and at 240 names", () => {
  const frames = [
    { name: "the 1440x900 window", width: 1440, height: 900 },
    { name: "the HUD stage at 1440x900", width: 970, height: 806 },
    { name: "a narrow stage", width: 800, height: 773 },
  ];
  for (const frame of frames) {
    const aspect = frame.width / frame.height;
    for (const size of [32, 120, MAX_COSMOS_NODES]) {
      const nodes = budgetGraph(size);
      for (const id of COSMOS_PRESET_ORDER) {
        // The orrery moves while it spins: frame it at rest and check the whole
        // orbit too, so a moving name cannot leave the frame either.
        const rest = presetPositions(id, nodes, { orbitTime: 0 });
        const framed = cameraFrame(id, { positions: rest, radius: boundsOf(rest).radius, aspect });
        let widest = 0;
        for (const t of [0, 0.6, 1.4, 2.2, 3.7]) {
          const at = presetPositions(id, nodes, { orbitTime: t });
          for (const point of at) {
            const seen = projectPoint(point,
              { position: framed.position, lookAt: framed.lookAt },
              { aspect, width: frame.width, height: frame.height });
            const where = `${id} at ${size} names (${frame.name}, t=${t})`;
            assert.ok(seen.inFront, `${where}: a name is behind the camera`);
            assert.ok(Math.abs(seen.ndcX) <= FRAME_FILL + 1e-9,
              `${where}: ${point.id} is ${seen.ndcX.toFixed(2)} across (fill ${FRAME_FILL})`);
            assert.ok(Math.abs(seen.ndcY) <= FRAME_FILL + 1e-9,
              `${where}: ${point.id} is ${seen.ndcY.toFixed(2)} up (fill ${FRAME_FILL})`);
            // The label is drawn ABOVE the body (10-14 px text, a 7 px gap), and
            // a body is at most 9 scene units across: both must fit on canvas.
            assert.ok(seen.y - 9 * seen.k - 21 >= 0,
              `${where}: ${point.id} has no room for its label above it`);
            widest = Math.max(widest, Math.abs(seen.ndcX), Math.abs(seen.ndcY));
          }
        }
        // ... and it is not a dot in the middle of an empty frame: the picture
        // really was fitted, not merely shrunk.
        assert.ok(widest > 0.4,
          `${id} at ${size}: the picture only fills ${(widest * 100).toFixed(0)}% of the frame`);
      }
    }
  }
});

check("the fog fades with the camera, so 240 names are not fogged out", () => {
  assert.equal(FOG_DENSITY, 0.0016);
  assert.equal(fogDensityAt(200), FOG_DENSITY);           // Gemini's own frame: untouched
  assert.ok(fogDensityAt(900) < FOG_DENSITY);
  assert.ok(fogDensityAt(2700) < fogDensityAt(900));      // further out, thinner still
  for (const size of [32, 120, MAX_COSMOS_NODES]) {
    const nodes = budgetGraph(size);
    for (const id of COSMOS_PRESET_ORDER) {
      const at = presetPositions(id, nodes, { orbitTime: 0 });
      const framed = cameraFrame(id, { positions: at, aspect: 1440 / 900 });
      const density = fogDensityAt(framed.distance);
      const visible = Math.exp(-((density * framed.distance) ** 2));
      assert.ok(visible > 0.8,
        `${id} at ${size}: only ${(visible * 100).toFixed(0)}% of the far edge survives the fog`);
      if (framed.distance <= 250) assert.equal(density, FOG_DENSITY);
    }
  }
  // Why the scaling exists: Gemini's fixed density at a 240-name tree's distance
  // leaves almost nothing of the picture.
  const worst = Math.exp(-((FOG_DENSITY * 2000) ** 2));
  assert.ok(worst < 0.02, `the fixed density keeps ${(worst * 100).toFixed(1)}% at 2,000 units`);
});

/* -------------------------------------------------------------------------
 * 2. Roles: the HUD's eleven groups on Gemini's five categories
 * ---------------------------------------------------------------------- */

check("every group the page knows has a role, and an unknown group is treated as saved",
  () => {
    const groups = ["core", "model", "cluster", "tool", "fact", "source", "document",
      "entity", "project", "skill", "persona"];
    for (const group of groups) {
      assert.ok(ROLE_OF_GROUP[group], `${group} has no role`);
      assert.equal(roleOf(group), ROLE_OF_GROUP[group]);
    }
    assert.deepEqual(new Set(Object.values(ROLE_OF_GROUP)),
      new Set(["core", "brain", "group", "tool", "memory"]));
    assert.equal(roleOf("something-new"), "memory");
    assert.equal(roleOf("core"), "core");
  });

check("byRole keeps the order it was given and never mutates the nodes", () => {
  const { nodes } = geminiShaped();
  const before = JSON.stringify(nodes);
  const roles = byRole(nodes);
  assert.equal(JSON.stringify(nodes), before);
  const flat = Object.values(roles).flat();
  assert.equal(flat.length, nodes.length);
  assert.equal(roles.core.length, 1);
  assert.equal(roles.brain.length, 4);
  assert.equal(roles.group.length, 7);
  assert.equal(roles.tool.length, 12);
  assert.equal(roles.memory.length, 8);
  assert.deepEqual(roles.tool.map((n) => n.id),
    nodes.filter((n) => n.group === "tool").map((n) => n.id));
});

check("an ability's parent comes from the graph's own has links, not from a field", () => {
  const { nodes, links } = geminiShaped();
  const parents = parentOf(nodes, links);
  const tool = nodes.find((n) => n.group === "tool");
  const cluster = nodes.find((n) => n.group === "cluster");
  assert.equal(parents.get(tool.id), cluster.id);
  // A model -> tool link is not a parent link.
  const other = nodes.find((n) => n.group === "model");
  for (const [child, parent] of parents) {
    assert.equal(roleOf(nodes.find((n) => n.id === child).group), "tool");
    assert.equal(roleOf(nodes.find((n) => n.id === parent).group), "group");
  }
  assert.ok(other);
  // A link of another kind never invents a parent.
  const weird = parentOf(nodes, [{ source: cluster.id, target: tool.id, kind: "mentions" }]);
  assert.equal(weird.size, 0);
});

/* -------------------------------------------------------------------------
 * 3. The three fields the backend does not send: derived, and said so
 * ---------------------------------------------------------------------- */

check("the radar look's rings are kinds of thing, mapped from the real groups", () => {
  assert.equal(SENTINEL_RINGS.length, 3);
  assert.deepEqual(SENTINEL_RINGS.map((ring) => [ring.r, ring.y]),
    [[34, 18], [72, 4], [115, -10]]);
  assert.equal(ringOf("core"), 0);
  assert.equal(ringOf("model"), 0);
  assert.equal(ringOf("cluster"), 0);
  assert.equal(ringOf("tool"), 1);
  assert.equal(ringOf("skill"), 1);
  for (const group of ["fact", "document", "entity", "project", "persona", "source"]) {
    assert.equal(ringOf(group), 2, group);
  }
});

check("the nebula's four wells are the graph's own saved groups, and every one is reachable",
  () => {
    assert.equal(NEBULA_WELLS.length, 4);
    const reached = new Set(NEBULA_WELLS.map((well) => well.key));
    assert.equal(reached.size, 4);
    assert.equal(wellOf("fact"), 0);
    assert.equal(wellOf("entity"), 1);
    assert.equal(wellOf("project"), 2);
    assert.equal(wellOf("source"), 3);
    // Every saved group the page knows lands in a well, and no well is empty.
    const used = new Set(["fact", "entity", "document", "project", "persona", "source"]
      .map(wellOf));
    assert.equal(used.size, 4);
    // An unknown group joins the last well rather than vanishing.
    assert.equal(wellOf("something-new"), 3);
  });

check("a date in the meta text is read, and a node without one is not ordered arbitrarily",
  () => {
    const withDates = [
      { id: "b", meta: "saved 2026-10-20" },
      { id: "a", meta: "saved 2026-10-01" },
      { id: "c", meta: "no date here" },
      { id: "d", detail: "2026-10-31T09:00" },
    ];
    const { fractions, hasTime } = timeFractions(withDates);
    assert.equal(hasTime, true);
    assert.ok(fractions.get("a") < 0.01);
    assert.ok(fractions.get("d") > 0.99);
    assert.ok(fractions.get("b") > 0.5 && fractions.get("b") < 0.9);
    assert.equal(fractions.get("c"), 0.5, "a node with no date sits in the middle");
    for (const value of fractions.values()) assert.ok(value >= 0 && value <= 1);

    const none = timeFractions([{ id: "z" }, { id: "a" }, { id: "m" }]);
    assert.equal(none.hasTime, false, "no dates must not be reported as a time axis");
    assert.ok(none.fractions.get("a") < none.fractions.get("m"));
    assert.ok(none.fractions.get("m") < none.fractions.get("z"));
    assert.equal(none.fractions.get("a"), 0);
    assert.equal(none.fractions.get("z"), 1);
    // A single date is not an axis either.
    assert.equal(timeFractions([{ id: "a", meta: "2026-10-01" }, { id: "b" }]).hasTime, false);
  });

check("stampOf reads the shapes this repository really writes, and nothing else", () => {
  assert.equal(stampOf({ meta: "saved 2026-10-20" }), Date.UTC(2026, 9, 20));
  assert.equal(stampOf({ meta: "2026-10-20T14:30" }), Date.UTC(2026, 9, 20, 14, 30));
  assert.equal(stampOf({ detail: "2026-01-02" }), Date.UTC(2026, 0, 2));
  assert.equal(stampOf({ meta: "1760000000" }), 1760000000000);
  assert.equal(stampOf({ meta: "nothing" }), null);
  assert.equal(stampOf({}), null);
  assert.equal(stampOf(null), null);
});

/* -------------------------------------------------------------------------
 * 4. Ring plans: Gemini's radii, grown only when they must be
 * ---------------------------------------------------------------------- */

check("a ring holds what the page's radius can hold, and grows only past that", () => {
  assert.equal(ringCapacity(38), 9);       // pi / asin(24/76)
  assert.equal(ringCapacity(78), 20);
  assert.equal(ringCapacity(108), 28);
  assert.equal(ringCapacity(128), 33);
  for (const r of [34, 38, 68, 78, 108, 115, 128]) {
    const cap = ringCapacity(r);
    assert.ok(2 * r * Math.sin(Math.PI / cap) >= MIN_GAP, `R=${r} crowds its names`);
  }
  // Gemini's own pictures fit one ring.
  for (const [count, base] of [[4, 38], [7, 78], [8, 128], [12, 108]]) {
    const plan = ringPlan(count, base);
    assert.equal(plan.length, 1, `${count} names at R=${base} needed ${plan.length} rings`);
    assert.equal(plan[0].count, count);
    assert.equal(plan[0].r, base);
  }
  // The zen halo is the page's 31 names on one R=108 ring, at its own 21 units.
  const halo = ringPlan(31, 108, { gap: ZEN_HALO_GAP });
  assert.equal(halo.length, 1);
  assert.equal(halo[0].count, 31);
  // 240 names at R=108 cannot fit: rings grow outward, and every name has a place.
  const big = ringPlan(MAX_COSMOS_NODES, 108, { pitch: 34 });
  assert.ok(big.length > 1);
  assert.equal(big.reduce((sum, ring) => sum + ring.count, 0), MAX_COSMOS_NODES);
  for (const ring of big) assert.ok(ring.count <= ringCapacity(ring.r));
  for (let i = 1; i < big.length; i++) assert.equal(big[i].r, big[i - 1].r + 34);
});

/* -------------------------------------------------------------------------
 * 5. Positions: Gemini's geometry at Gemini's size
 * ---------------------------------------------------------------------- */

check("the orrery is Gemini's: R=38/78/128 with the page's own wave amplitudes", () => {
  const { nodes, links } = geminiShaped();
  const at = presetPositions("planetary-orbit", nodes, { links, orbitTime: 0 });
  assert.equal(at.length, nodes.length);
  const byId = new Map(at.map((p) => [p.id, p]));
  const core = nodes.find((n) => n.group === "core");
  assert.deepEqual(byId.get(core.id), { id: core.id, x: 0, y: 0, z: 0 });

  const brains = nodes.filter((n) => n.group === "model");
  brains.forEach((brain, i) => {
    const angle = (i / brains.length) * Math.PI * 2;
    const spot = byId.get(brain.id);
    assert.ok(Math.abs(spot.x - Math.cos(angle) * 38) < 1e-9, "brain x");
    assert.ok(Math.abs(spot.y - Math.sin(angle * 2) * 4) < 1e-9, "brain wave");
    assert.ok(Math.abs(spot.z - Math.sin(angle) * 38) < 1e-9, "brain z");
  });

  const groups = nodes.filter((n) => n.group === "cluster");
  groups.forEach((group, i) => {
    const angle = (i / groups.length) * Math.PI * 2 + 0.3;
    const spot = byId.get(group.id);
    assert.ok(Math.abs(Math.hypot(spot.x, spot.z) - 78) < 1e-9, "group radius 78");
    assert.ok(Math.abs(spot.y - Math.sin(angle) * 6) < 1e-9, "group wave");
  });

  const memories = nodes.filter((n) => !["core", "model", "cluster", "tool"].includes(n.group));
  memories.forEach((memory, i) => {
    const angle = (i / memories.length) * Math.PI * 2 + 0.8;
    const spot = byId.get(memory.id);
    assert.ok(Math.abs(Math.hypot(spot.x, spot.z) - 128) < 1e-9, "memory belt 128");
    assert.ok(Math.abs(spot.y - Math.sin(angle * 3) * 10) < 1e-9, "memory wave");
  });

  // An ability rides a 19-unit orbit around its own group: the page's moons.
  const parents = parentOf(nodes, links);
  const tool = nodes.find((n) => n.group === "tool");
  const parentSpot = byId.get(parents.get(tool.id));
  const toolSpot = byId.get(tool.id);
  const away = Math.hypot(toolSpot.x - parentSpot.x, toolSpot.y - parentSpot.y,
    toolSpot.z - parentSpot.z);
  assert.ok(away > 12 && away < 26, `an ability orbited at ${away.toFixed(2)}, not about 19`);
});

check("every look places every name once, with finite numbers, deterministically", () => {
  const { nodes, links } = geminiShaped();
  const before = JSON.stringify(nodes);
  for (const id of COSMOS_PRESET_ORDER) {
    const first = presetPositions(id, nodes, { links });
    const second = presetPositions(id, nodes, { links });
    assert.deepEqual(first, second, `${id} is not deterministic`);
    assert.equal(first.length, nodes.length, `${id} lost or added a name`);
    assert.deepEqual(first.map((p) => p.id), nodes.map((n) => n.id),
      `${id} changed the order`);
    for (const point of first) {
      assert.ok(Number.isFinite(point.x) && Number.isFinite(point.y)
        && Number.isFinite(point.z), `${id}: ${point.id} is not a number`);
    }
    // No two names sit on the same point in any look.
    if (id !== "dna-helix") {
      assert.ok(nearest(first) > 1, `${id}: two names share a place`);
    }
  }
  assert.equal(JSON.stringify(nodes), before, "a look mutated its input");
});

check("the flat and ring looks keep their own spacing at every size, including 240", () => {
  const gapFor = { "star-map": MIN_GAP, "zen-ring": ZEN_HALO_GAP };
  for (const size of [2, 7, 32, 120, 240]) {
    const nodes = Array.from({ length: size }, (_, i) => ({
      id: `n:${i}`, group: ["core", "model", "cluster", "tool", "fact"][i % 5],
    }));
    for (const id of ["star-map", "zen-ring"]) {
      const at = presetPositions(id, nodes);
      if (size > 1) {
        assert.ok(nearest(at) >= gapFor[id] - 1e-6,
          `${id} at ${size} names: closest pair ${nearest(at).toFixed(1)}`);
      }
    }
  }
});

check("the tree keeps its four bands and lets a long row wrap into lanes", () => {
  const small = Array.from({ length: 1 }, (_, i) => ({ id: `a${i}`, group: "core" }));
  const smallAt = presetPositions("clean-tree", small);
  assert.deepEqual(smallAt[0], { id: "a0", x: 0, y: 62, z: 0 });

  // At Gemini's own size the four row heights are his, exactly.
  const shaped = geminiShaped();
  const geminiAt = presetPositions("clean-tree", shaped.nodes);
  const rowOf = (group) => [...new Set(geminiAt
    .filter((p, i) => shaped.nodes[i].group === group).map((p) => Math.round(p.y)))];
  assert.deepEqual(rowOf("core"), [62]);
  assert.deepEqual(rowOf("model"), [24]);
  assert.deepEqual(rowOf("cluster"), [-14]);
  assert.deepEqual([...new Set(geminiAt
    .filter((p, i) => ["tool", "fact", "document", "project", "source"]
      .includes(shaped.nodes[i].group))
    .map((p) => Math.round(p.y)))].sort((a, b) => b - a), [-48, -64]);

  // A 240-name tree: bands wrap, and a wrapped band pushes the ones under it
  // DOWN instead of growing into them; nothing overlaps and nothing leaves z=0.
  const nodes = Array.from({ length: MAX_COSMOS_NODES }, (_, i) => ({
    id: `n:${i}`, group: ["core", "model", "cluster", "tool", "fact"][i % 5],
  }));
  const at = presetPositions("clean-tree", nodes);
  for (const point of at) assert.equal(point.z, 0, "the tree is a flat flowchart");
  assert.ok(nearest(at) >= 20, `the tree crowded to ${nearest(at).toFixed(1)} units`);
  const top = Math.max(...at.filter((p, i) => nodes[i].group === "core").map((p) => p.y));
  const bottom = Math.min(...at.filter((p, i) => nodes[i].group === "fact").map((p) => p.y));
  const lowest = (group) => Math.min(...at.filter((p, i) => nodes[i].group === group)
    .map((p) => p.y));
  const highest = (group) => Math.max(...at.filter((p, i) => nodes[i].group === group)
    .map((p) => p.y));
  assert.equal(top, 62, "the core stays at the top of the hierarchy");
  assert.ok(bottom < -64, "a 240-name picture did not wrap past Gemini's own rows");
  assert.ok(highest("model") < top, "the brains are not under the core");
  assert.ok(highest("cluster") < lowest("model"), "the ability groups are not under the brains");
  assert.ok(highest("tool") < lowest("cluster"), "the leaves are not under the groups");
  // A single row of 240 wraps: one lane could never hold it at its own pitch.
  const lanes = treeRow(MAX_COSMOS_NODES);
  assert.ok(lanes.length > 1, "a 240-name row did not wrap");
  const perLane = new Map();
  for (const slot of lanes) perLane.set(slot.lane, (perLane.get(slot.lane) || 0) + 1);
  const laneCounts = [...perLane.values()];
  // 2,200 units of width at a 26-unit pitch holds 85 names a lane.
  assert.equal(Math.max(...laneCounts), 85, "a lane holds more than the width budget");
  for (let i = 1; i < laneCounts.length; i++) {
    assert.ok(laneCounts[i] <= laneCounts[0], "a later lane holds more than the first");
  }
});

check("the helix orders its two strands by real time when it can, and says when it cannot",
  () => {
    const nodes = [
      { id: "core", group: "core" },
      { id: "fact:old", group: "fact", meta: "2026-06-01" },
      { id: "fact:new", group: "fact", meta: "2026-10-01" },
      { id: "tool:1", group: "tool", meta: "2026-08-01" },
      { id: "tool:2", group: "tool", meta: "2026-09-01" },
    ];
    const at = presetPositions("dna-helix", nodes);
    const byId = new Map(at.map((p) => [p.id, p]));
    assert.equal(byId.get("core").y, -82);
    assert.ok(byId.get("fact:old").y < byId.get("fact:new").y, "the saved strand is not in time order");
    assert.ok(byId.get("tool:1").y < byId.get("tool:2").y, "the other strand is not in time order");
    for (const point of at) {
      if (point.id === "core") continue;
      assert.ok(Math.abs(Math.hypot(point.x, point.z) - 52) < 1e-9, "the helix radius is 52");
    }
  });

check("a 240-name helix becomes a bank of columns, not a 3,000-unit ribbon", () => {
  const nodes = Array.from({ length: MAX_COSMOS_NODES }, (_, i) => ({
    id: `n:${i}`, group: i % 3 === 0 ? "fact" : "tool",
  }));
  const at = presetPositions("dna-helix", nodes);
  const xs = new Set(at.filter((p) => p.id !== "n:0").map((p) => Math.round(p.x)));
  assert.ok(xs.size > 2, "a 240-name helix did not use columns");
  const height = Math.max(...at.map((p) => p.y)) - Math.min(...at.map((p) => p.y));
  assert.ok(height < 260, `the helix grew to ${height.toFixed(0)} units tall`);
  assert.ok(HELIX_PER_COLUMN >= 16 && HELIX_PER_COLUMN <= 40);
});

/* -------------------------------------------------------------------------
 * 6. Guides: the page's bodies, counted
 * ---------------------------------------------------------------------- */

check("the orrery has Gemini's three ecliptic rings at R=38/78/128", () => {
  const { nodes, links } = geminiShaped();
  const guides = presetGuides("planetary-orbit", nodes, { links });
  const rings = guides.filter((g) => g.kind === "ring");
  assert.deepEqual(rings.map((g) => g.r), [38, 78, 128]);
  assert.deepEqual(rings.map((g) => g.color), ["#a855f7", "#10b981", "#fbbf24"]);
  assert.deepEqual(rings.map((g) => g.opacity), [0.28, 0.25, 0.18]);
});

check("the neural look has the soma, three plates and six arms of four fibres", () => {
  const { nodes } = geminiShaped();
  const guides = presetGuides("neural-arbor", nodes);
  const kinds = (kind) => guides.filter((g) => g.kind === kind);
  assert.equal(kinds("cone").length, 1);
  assert.equal(kinds("cone")[0].sides, 6);
  assert.equal(kinds("cone")[0].radius, 16);
  assert.equal(kinds("cone")[0].height, 26);
  assert.deepEqual(kinds("hex").map((g) => [g.y, g.r]), [[-46, 78], [0, 58], [52, 96]]);
  const curves = kinds("curve");
  assert.equal(curves.length, 6 + 6 * 2 + 6, "six trunks, twelve twigs, six roots");
  // The apical trunk leaves the soma at (0, 2, 0) and reaches the canopy at 52.
  const trunk = curves.find((c) => c.from[1] === 2);
  assert.deepEqual(trunk.from, [0, 2, 0]);
  assert.equal(trunk.to[1], 52);
  assert.equal(trunk.samples, 24);
  // The basal roots end on the base plate.
  const root = curves.find((c) => c.to[1] === -46);
  assert.deepEqual(root.to, [Math.cos(Math.PI / 6) * 72, -46, Math.sin(Math.PI / 6) * 72]);
});

check("the nebula has four wells and the page's 3,200-point cloud", () => {
  const guides = presetGuides("nebula", geminiShaped().nodes);
  const wells = guides.filter((g) => g.kind === "ring");
  assert.equal(wells.length, 4);
  assert.deepEqual(wells.map((g) => g.at),
    NEBULA_WELLS.map((well) => [...well.at]));
  const cloud = nebulaCloud();
  assert.equal(cloud.positions.length, NEBULA_POINTS * 3);
});

check("the helix has 36 rungs, two strands and the laser disk on the time axis", () => {
  const guides = presetGuides("dna-helix", geminiShaped().nodes, { timeValue: 1 });
  // The page loops s = 0..72 and draws a rung at every even s, so it draws 37
  // (the port brief says 36; that is the 72/2 pair count and is one short).
  assert.equal(guides.filter((g) => g.kind === "line").length, 37);
  const strands = guides.filter((g) => g.kind === "polyline");
  assert.equal(strands.length, 2);
  for (const strand of strands) {
    assert.equal(strand.points.length, 73);
    assert.equal(strand.points[0][1], -82);
    assert.equal(strand.points[72][1], 82);
    for (const point of strand.points) {
      assert.ok(Math.abs(Math.hypot(point[0], point[2]) - 52) < 1e-9);
    }
  }
  const disk = guides.find((g) => g.kind === "disk");
  assert.equal(disk.r, 62);
  assert.equal(disk.rim[0], 61);
  assert.equal(disk.y, 80, "the disk starts at today's end of the tunnel");
  // Sweeping to the start moves the disk to the other end.
  const back = presetGuides("dna-helix", geminiShaped().nodes, { timeValue: 0 });
  assert.equal(back.find((g) => g.kind === "disk").y, -80);
});

check("the radar look has three zones, four crosshairs, a sweep and a dome", () => {
  // A picture small enough for Gemini's own rings: 4 names in the inner zone,
  // 2 in the middle, 2 on the rim.
  const small = graphOf({ core: 1, model: 2, cluster: 2, tool: 2, fact: 2 });
  const guides = presetGuides("radar-dome", small.nodes, { links: small.links });
  const rings = guides.filter((g) => g.kind === "ring");
  assert.deepEqual(rings.map((g) => g.r), [34, 72, 115]);
  assert.deepEqual(rings.map((g) => g.y), [-28, -28, -28]);
  assert.deepEqual(rings.map((g) => g.color), ["#10b981", "#f59e0b", "#f43f5e"]);
  assert.equal(guides.filter((g) => g.kind === "line").length, 4);
  const sector = guides.find((g) => g.kind === "sector");
  assert.equal(sector.r, 118);
  assert.equal(sector.thetaLength, Math.PI / 5);
  const dome = guides.find((g) => g.kind === "dome");
  assert.equal(dome.r, 72);
  assert.equal(dome.y, -28);

  // A zone that outgrows its ring grows OUTWARD by the same rule as every other
  // ring in this module: the picture keeps the three zones, a crowded one just
  // takes two rings.
  const big = geminiShaped();
  const many = presetGuides("radar-dome", big.nodes, { links: big.links });
  const radii = many.filter((g) => g.kind === "ring").map((g) => g.r);
  assert.ok(radii.length >= 3);
  assert.ok(radii.every((r) => r >= 34));
  for (const base of [34, 72, 115]) {
    assert.ok(radii.some((r) => r >= base), `no ring at or past the ${base} zone`);
  }
});


check("the three simple looks have their own guides: rings, baselines and a halo", () => {
  const { nodes } = geminiShaped();
  const flat = presetGuides("star-map", nodes);
  assert.deepEqual(flat.filter((g) => g.kind === "ring").map((g) => g.r), [34, 68, 108]);
  assert.equal(flat.filter((g) => g.kind === "spokes").length, 1);
  assert.equal(flat.find((g) => g.kind === "spokes").count, 7);

  const tree = presetGuides("clean-tree", nodes);
  const lines = tree.filter((g) => g.kind === "line");
  assert.equal(lines.length, 4);
  assert.deepEqual(lines.map((g) => g.from[1]), [62, 24, -14, -48]);
  assert.ok(lines.every((line) => line.from[2] === -2 && line.to[2] === -2));
  assert.deepEqual(lines.map((g) => g.color),
    ["#10b981", "#a855f7", "#06b6d4", "#fbbf24"]);

  const ring = presetGuides("zen-ring", nodes);
  const halo = ring.filter((g) => g.kind === "halo");
  assert.equal(halo.length, 1);
  assert.equal(halo[0].r, 108);
  assert.equal(halo[0].color, "#0d9488");
});

/* -------------------------------------------------------------------------
 * 7. Links: the page's three shapes
 * ---------------------------------------------------------------------- */

check("links are straight synapses, curved axons or inward chords, per look", () => {
  const { nodes, links } = geminiShaped();
  const straight = presetLinks("planetary-orbit", nodes, links);
  assert.ok(straight.length > 0);
  assert.ok(straight.every((link) => link.control === null));
  assert.equal(straight[0].color, "#00f0ff");

  const neural = presetLinks("neural-arbor", nodes, links);
  assert.ok(neural.every((link) => link.control && link.samples === 20));
  assert.equal(neural[0].color, "#c084fc");

  const chords = presetLinks("zen-ring", nodes, links);
  assert.ok(chords.every((link) => link.control && link.samples === 18));
  assert.equal(chords[0].color, "#2dd4bf");
  // The chord bows inward: its control point is nearer the centre than the
  // midpoint of the two ends (the page's 0.35 rule).
  const chord = chords[0];
  const mid = { x: (chord.a.x + chord.b.x) / 2, z: (chord.a.z + chord.b.z) / 2 };
  assert.ok(Math.hypot(chord.control.x, chord.control.z)
    < Math.hypot(mid.x, mid.z) * 0.8);

  const sentinel = presetLinks("radar-dome", nodes, links);
  assert.equal(sentinel[0].color, "#10b981");

  // Links never invent an endpoint the picture does not hold.
  const ghost = presetLinks("star-map", nodes, [{ source: "nope", target: nodes[0].id }]);
  assert.equal(ghost.length, 0);
  // The cap holds, and a repeated pair is counted once.
  const many = Array.from({ length: MAX_COSMOS_LINKS + 200 }, (_, i) => ({
    source: nodes[i % nodes.length].id, target: nodes[(i + 1) % nodes.length].id,
  }));
  assert.ok(presetLinks("star-map", nodes, many).length <= MAX_COSMOS_LINKS);
  const repeated = new Array(500).fill({ source: nodes[0].id, target: nodes[1].id });
  assert.equal(presetLinks("star-map", nodes, repeated).length, 1);
});

/* -------------------------------------------------------------------------
 * 8. Particles: the page's counts, from a seeded generator
 * ---------------------------------------------------------------------- */

check("the sky is 1,800 stars on a shell 350..900 out, and it is the same sky twice", () => {
  const first = starField();
  const second = starField();
  assert.equal(first.positions.length, STAR_COUNT * 3);
  assert.deepEqual([...first.positions], [...second.positions]);
  for (let i = 0; i < STAR_COUNT; i++) {
    const r = Math.hypot(first.positions[i * 3], first.positions[i * 3 + 1],
      first.positions[i * 3 + 2]);
    assert.ok(r >= 349.9 && r <= 900.1, `star ${i} at ${r.toFixed(1)}`);
  }
  // Two colours only: the page's cyan and slate (compared as numbers: a
  // Float32Array stores 0.85 as 0.85000002, so text comparison would lie).
  const colours = new Set();
  for (let i = 0; i < STAR_COUNT; i++) {
    colours.add([first.colors[i * 3], first.colors[i * 3 + 1], first.colors[i * 3 + 2]]
      .map((value) => value.toFixed(3)).join(","));
  }
  assert.equal(colours.size, 2, "the page uses exactly two star colours");
  assert.ok(colours.has("0.000,0.850,1.000"), "the cyan star is missing");
  assert.ok(colours.has("0.250,0.450,1.000"), "the slate star is missing");
});

check("the nebula cloud splits evenly across the four wells and stays inside them", () => {
  const cloud = nebulaCloud();
  assert.equal(cloud.positions.length, NEBULA_POINTS * 3);
  const perWell = NEBULA_POINTS / NEBULA_WELLS.length;
  for (let well = 0; well < NEBULA_WELLS.length; well++) {
    let inside = 0;
    for (let i = well; i < NEBULA_POINTS; i += NEBULA_WELLS.length) {
      const at = NEBULA_WELLS[well].at;
      const d = Math.hypot(cloud.positions[i * 3] - at[0],
        cloud.positions[i * 3 + 1] - at[1], cloud.positions[i * 3 + 2] - at[2]);
      if (d <= NEBULA_WELLS[well].r * 1.35 + 1e-6) inside += 1;
    }
    assert.equal(inside, perWell, `well ${well} leaked points`);
  }
  assert.deepEqual([...nebulaCloud().positions], [...cloud.positions]);
});

check("the seeded generator repeats, and colours convert both ways", () => {
  const a = mulberry32(7);
  const b = mulberry32(7);
  for (let i = 0; i < 20; i++) assert.equal(a(), b());
  const c = mulberry32(8);
  assert.notEqual(mulberry32(7)(), c());
  assert.deepEqual(hexToRgb("#00f0ff"), { r: 0, g: 0xf0 / 255, b: 1 });
  assert.deepEqual(hexToRgb("#fff"), { r: 1, g: 1, b: 1 });
  assert.equal(hexToInt("#030712"), 0x030712);
  assert.equal(hexToInt("nonsense"), 0xffffff);
});

/* -------------------------------------------------------------------------
 * 9. Budgets
 * ---------------------------------------------------------------------- */

check("the budget keeps the order it was given, never mutates, and holds 240", () => {
  const nodes = Array.from({ length: 400 }, (_, i) => ({ id: `n:${i}`, group: "fact" }));
  const before = JSON.stringify(nodes);
  const cut = budgetNodes(nodes);
  assert.equal(cut.length, MAX_COSMOS_NODES);
  assert.equal(cut[0].id, "n:0");
  assert.equal(cut[MAX_COSMOS_NODES - 1].id, `n:${MAX_COSMOS_NODES - 1}`);
  assert.equal(JSON.stringify(nodes), before);
  assert.equal(budgetNodes(nodes.slice(0, 10)).length, 10);
  assert.equal(budgetNodes(null).length, 0);
});

check("the link budget dedupes by pair, keeps order, and holds 360", () => {
  const links = Array.from({ length: 700 }, (_, i) => ({
    source: `a${i % 10}`, target: `b${i}`,
  }));
  const cut = budgetLinks(links);
  assert.equal(cut.length, MAX_COSMOS_LINKS);
  assert.deepEqual(cut[0], links[0]);
  assert.equal(budgetLinks([{ source: "a", target: "b" }, { source: "a", target: "b" }]).length, 1);
});

check("boundsOf reports the radius about the origin, and an empty picture is zero", () => {
  const one = boundsOf([{ id: "a", x: 3, y: 4, z: 0 }]);
  assert.equal(one.radius, 5);
  assert.equal(one.minY, 4);
  assert.deepEqual(boundsOf([]), { radius: 0, minY: 0, maxY: 0 });
});

/* -------------------------------------------------------------------------
 * 10. The per-look controls
 * ---------------------------------------------------------------------- */

check("every look has its two plain-word controls, and no look is missing one", () => {
  assert.deepEqual(Object.keys(PRESET_ACTIONS).sort(), [...COSMOS_PRESET_ORDER].sort());
  const keys = new Set();
  for (const id of COSMOS_PRESET_ORDER) {
    const actions = actionsFor(id);
    assert.equal(actions.length, 2, `${id} has ${actions.length} controls`);
    for (const action of actions) {
      assert.equal(typeof action.key, "string");
      assert.ok(action.key.length > 1);
      assert.ok(!keys.has(action.key), `${action.key} is used twice`);
      keys.add(action.key);
      assert.equal(typeof action.label, "string");
      assert.ok(action.label.length >= 4 && action.label.length <= 24,
        `${id}: "${action.label}" is not a button label`);
      assert.equal(typeof action.toggle, "boolean");
      // Plain words only: no camelCase identifiers on a button.
      assert.ok(!/[a-z][A-Z]/.test(action.label), `${action.label} is code, not words`);
    }
  }
  assert.deepEqual(actionsFor(DEFAULT_PRESET), []);
  assert.deepEqual(actionsFor("not-a-look"), []);
});

/* -------------------------------------------------------------------------
 * 11. The frame budget
 *
 * The owner's ask that produced this: the Galaxy must stay usable on a machine
 * with no usable GPU instead of crawling. Two halves, in this order - fewer
 * pixels, then fewer frames - and the second only turns on once the first has
 * given all it can.
 *
 * The audit of 2026-10-28 added the other direction: earning PIXELS BACK when
 * the display, not the machine, is what holds the frame rate down. That is
 * `nextFrameScale`, and the last five checks here drive it exactly as the
 * frame loop does - one sample per six frames - because the bug it fixes is a
 * bug about a SEQUENCE of samples, not about one.
 * ---------------------------------------------------------------------- */

check("the frame budget's thresholds are ordered, and the floor is a fraction", () => {
  assert.ok(FAST_FRAME_MS < SLOW_FRAME_MS, "the fast threshold is not below the slow one");
  assert.ok(SLOW_FRAME_MS < VERY_SLOW_FRAME_MS, "the slow threshold is not below the very-slow one");
  assert.ok(RENDER_SCALE_MIN > 0 && RENDER_SCALE_MIN < 1,
    `RENDER_SCALE_MIN is ${RENDER_SCALE_MIN}, which is not a fraction of the display ratio`);
  // The half-rate switch and the resolution rule name the SAME number, which is
  // what "still slow after the resolution has given all it can" means. If these
  // ever drift apart the picture either steps frames while pixels were still
  // available, or never steps at all.
  assert.equal(SLOW_FRAME_MS, 34);
});

check("a fast renderer never draws more pixels than the display has", () => {
  // At the display's own ratio and faster than FAST_FRAME_MS, there is nothing
  // to win: the 3D canvas may not be upscaled past 1.
  assert.equal(nextRenderScale(1, 8), 1);
  assert.equal(nextRenderScale(1, FAST_FRAME_MS - 1), 1);
  // Below full scale it climbs, but never past the display's ratio.
  let scale = RENDER_SCALE_MIN;
  for (let i = 0; i < 40; i += 1) scale = nextRenderScale(scale, 8);
  assert.equal(scale, 1, "a cheap picture never earned all its pixels back");
  // And a value that is already 1 stays 1.
  assert.equal(nextRenderScale(1, 1), 1);
});

check("a slow renderer loses pixels one step at a time, and stops at the floor", () => {
  const slow = SLOW_FRAME_MS + 5;
  assert.equal(nextRenderScale(1, slow), 0.75);
  assert.equal(nextRenderScale(0.75, slow), 0.5625);
  assert.equal(nextRenderScale(0.5625, slow), 0.421875);
  // The floor is a floor: further slow frames cannot take it below.
  assert.equal(nextRenderScale(RENDER_SCALE_MIN, slow), RENDER_SCALE_MIN);
  assert.equal(nextRenderScale(0.3, slow), RENDER_SCALE_MIN,
    "0.3 * 0.75 is below the floor, so it must clamp rather than go under it");
  // Never below the floor on any slow input, stepping down from full.
  let scale = 1;
  for (let i = 0; i < 50; i += 1) {
    scale = nextRenderScale(scale, SLOW_FRAME_MS + 1);
    assert.ok(scale >= RENDER_SCALE_MIN, `scale fell to ${scale}, under the floor`);
  }
  assert.equal(scale, RENDER_SCALE_MIN);
});

check("a very slow renderer goes straight to the floor, not one step at a time", () => {
  // 60ms+ is under 17 frames a second: there is no point rationing 25% at a
  // time, so the rule jumps to the floor in ONE frame.
  assert.equal(nextRenderScale(1, VERY_SLOW_FRAME_MS + 1), RENDER_SCALE_MIN);
  assert.equal(nextRenderScale(1, 1000), RENDER_SCALE_MIN);
});

check("a picture that got cheap earns its pixels back one step at a time", () => {
  const fast = FAST_FRAME_MS - 5;
  assert.equal(nextRenderScale(0.5, fast), 0.5 / 0.75);
  assert.equal(nextRenderScale(0.9, fast), 1, "90% climbs to the display ratio, not past it");
  // It takes more than one fast frame to get from the floor to full - that is
  // what stops a machine on the edge from flapping between 25% and 100%.
  assert.equal(nextRenderScale(RENDER_SCALE_MIN, fast), RENDER_SCALE_MIN / 0.75);
  assert.ok(nextRenderScale(RENDER_SCALE_MIN, fast) < 1);
});

check("a steady frame changes nothing, and nonsense input is never a broken picture", () => {
  // Between FAST and SLOW - the ordinary 30-60 fps band - the scale is held.
  assert.equal(nextRenderScale(1, 30), 1);
  assert.equal(nextRenderScale(0.5, 30), 0.5);
  // A scale that is not a positive number falls back to the display ratio
  // rather than to NaN or zero pixels.
  assert.equal(nextRenderScale(Number.NaN, 8), 1);
  assert.equal(nextRenderScale(0, 8), 1);
  assert.equal(nextRenderScale(-3, 8), 1);
  assert.equal(nextRenderScale(undefined, 8), 1);
  // A gap that is not a usable number is the identity: no sample, no change.
  assert.equal(nextRenderScale(0.5, Number.NaN), 0.5);
  assert.equal(nextRenderScale(0.5, 0), 0.5);
  assert.equal(nextRenderScale(0.5, -12), 0.5);
});

check("the rule is monotone: worse frames never give a picture more pixels", () => {
  const medians = [1, FAST_FRAME_MS - 1, FAST_FRAME_MS, 30, SLOW_FRAME_MS,
    SLOW_FRAME_MS + 1, 50, VERY_SLOW_FRAME_MS, VERY_SLOW_FRAME_MS + 1, 200];
  for (const start of [1, 0.75, 0.5, RENDER_SCALE_MIN]) {
    let previous = Infinity;
    for (const median of medians) {
      const scale = nextRenderScale(start, median);
      assert.ok(scale <= previous + 1e-12,
        `a worse frame (${median}ms) raised the scale from ${previous} to ${scale}`);
      previous = scale;
    }
    assert.ok(previous >= RENDER_SCALE_MIN && previous <= 1,
      `the slowest frame left the scale at ${previous}`);
  }
});

/* -------------------------------------------------------------------------
 * 11b. Getting the pixels BACK (audit B1, finding 4, 2026-10-28)
 *
 * The base rule above only ever climbs under FAST_FRAME_MS, which a 30 Hz
 * display never reaches - so these five checks drive the layer above it,
 * sample by sample, and pin the three things that make the recovery safe: a
 * steady 30 Hz picture climbs, a genuinely slow one never does, and a refused
 * probe is undone exactly and then asked for less and less often.
 * ---------------------------------------------------------------------- */

/* The frame loop's own rhythm, for the checks below: six gaps make one sample
 * and the sample's median is what `nextFrameScale` is fed (`frame()`, six
 * lines of it). `gapFor(state, index)` is the display's answer for the picture
 * being drawn: a 30 Hz display answers 33.3 ms whatever the scale, a machine
 * that cannot afford more answers slower as soon as it is asked, and a machine
 * with room answers the same either way. Returns every state after each
 * sample, so a scenario reads as a list of observations. */
function driveScale(start, samples, gapFor) {
  const seen = [];
  let state = createFrameScale(start);
  for (let i = 0; i < samples; i += 1) {
    state = nextFrameScale(state, gapFor(state, i));
    seen.push(state);
  }
  return seen;
}

/** How many times the picture asked for more pixels (a probational step up). */
function climbs(seen) {
  let count = 0;
  for (let i = 1; i < seen.length; i += 1) {
    if (seen[i].scale > seen[i - 1].scale + 1e-9) count += 1;
  }
  return count;
}

check("the probe's numbers are ordered, and a sample never changes the state it was given", () => {
  assert.ok(PROBE_STEADY_SAMPLES >= 2, "a single sample is not a steady run");
  assert.ok(PROBE_STEADY_MS > 0 && PROBE_STEADY_MS < FAST_FRAME_MS,
    `a ${PROBE_STEADY_MS} ms "steady" window cannot tell a steady display from a jittery one`);
  assert.ok(PROBE_BACKOFF_SAMPLES >= PROBE_STEADY_SAMPLES,
    "the wait after a refused probe is shorter than the evidence needed to ask");
  assert.ok(PROBE_BACKOFF_MAX >= PROBE_BACKOFF_SAMPLES,
    "the longest wait is shorter than the first one");
  // A frozen state may be read and never written: the frame loop keeps the
  // state it had before the sample, and so must a test.
  const frozen = Object.freeze(createFrameScale(RENDER_SCALE_MIN));
  const after = nextFrameScale(frozen, 33.3);
  assert.equal(frozen.scale, RENDER_SCALE_MIN, "the rule changed the state it was given");
  assert.equal(frozen.steady, 0, "the rule counted a sample into the state it was given");
  // One sample is not yet evidence, so it moves nothing.
  assert.equal(after.scale, RENDER_SCALE_MIN);
  assert.equal(after.steady, 1, `one sample counted as ${after.steady}`);
  // A sample that is not a usable number is the identity, as in the base rule.
  assert.equal(nextFrameScale(frozen, Number.NaN).scale, RENDER_SCALE_MIN);
  assert.equal(nextFrameScale(frozen, 0).scale, RENDER_SCALE_MIN);
});

check("a 30 Hz display is not a slow machine: the picture climbs back to full", () => {
  // THE BUG THIS PINS (audit B1, finding 4). A 30 Hz display hands out a frame
  // every 33.3 ms even when the page does nothing, so on that screen nothing is
  // ever under FAST_FRAME_MS and the base rule - correctly, for its own job -
  // holds: 40 frames at 33.3 ms leave the floor at the floor. Widening the base
  // rule's threshold is the UNSAFE fix, because 33.3 ms is also exactly what a
  // machine that can only manage 30 frames a second shows; the recovery has to
  // be a question, not a threshold, which is what the layer above is.
  let plain = RENDER_SCALE_MIN;
  for (let i = 0; i < 40; i += 1) plain = nextRenderScale(plain, 33.3);
  assert.equal(plain, RENDER_SCALE_MIN);
  // The frame loop's own rhythm: 40 FRAMES is under seven samples, and it is
  // already off the floor - this is the exact sequence the audit measured.
  const frames = driveScale(RENDER_SCALE_MIN, 7, () => 33.3);
  assert.ok(frames[6].scale > RENDER_SCALE_MIN + 1e-9,
    `40 frames at 33.3 ms left the scale at ${frames[6].scale}`);
  // 40 SAMPLES - 240 frames, about eight seconds at 30 Hz - is full resolution,
  // and it got there climbing, never flapping: every sample is at or above the
  // one before it.
  const seen = driveScale(RENDER_SCALE_MIN, 40, () => 33.3);
  assert.equal(seen[seen.length - 1].scale, 1,
    `40 steady samples at 33.3 ms left the scale at ${seen[seen.length - 1].scale}`);
  for (let i = 1; i < seen.length; i += 1) {
    assert.ok(seen[i].scale >= seen[i - 1].scale - 1e-9,
      `the recovery went backwards: ${seen[i - 1].scale} then ${seen[i].scale}`);
  }
  assert.equal(seen[seen.length - 1].halfRate, false,
    "the half rate stayed on once the picture had all its pixels back");
  // A real 30 Hz display is not exactly 30 Hz: timestamps jitter by a few
  // tenths of a millisecond and the peak refresh is 33.0 ms on some panels. The
  // steady window has to be wide enough for that, and narrow enough that a
  // machine whose frames jump about never counts as steady.
  const jittered = driveScale(RENDER_SCALE_MIN, 40, (_state, i) =>
    [33.0, 33.6, 33.2, 33.4][i % 4]);
  assert.equal(jittered[jittered.length - 1].scale, 1,
    `a 30 Hz display that jitters by 0.6 ms recovered only to ${jittered[jittered.length - 1].scale}`);
  // And at full resolution a steady 30 Hz display stays there: the probe has
  // nothing to ask for and must not invent anything.
  for (const state of driveScale(1, 40, () => 33.3)) {
    assert.equal(state.scale, 1, "a picture at full resolution moved");
  }
});

check("a genuinely slow machine stays at the floor and takes the half rate there, once", () => {
  // 45-60 ms is 17-22 frames a second: there is no interval here that a 30 Hz
  // display could be mistaken for, so the probe must never fire, and the
  // half-rate switch must come on exactly once - at the floor, as its rule says
  // - and then stay on, even though at the half rate the intervals improve.
  const seen = driveScale(1, 60, (_state, i) => 45 + (i % 3) * 7.5);
  for (let i = 0; i < seen.length; i += 1) {
    assert.ok(seen[i].scale >= RENDER_SCALE_MIN, `the scale fell to ${seen[i].scale}`);
    if (i > 0) assert.ok(seen[i].scale <= seen[i - 1].scale + 1e-9,
      `a slow machine gained pixels: ${seen[i - 1].scale} then ${seen[i].scale}`);
  }
  assert.equal(seen[seen.length - 1].scale, RENDER_SCALE_MIN);
  assert.equal(climbs(seen), 0, "a genuinely slow machine was asked to spend more pixels");
  const floorAt = seen.findIndex((state) => state.scale <= RENDER_SCALE_MIN + 1e-9);
  assert.ok(floorAt > 0, "the picture never reached the floor");
  assert.equal(seen[floorAt].halfRate, true, "the half rate did not come on at the floor");
  let flips = 0;
  for (let i = 1; i < seen.length; i += 1) {
    if (seen[i].halfRate !== seen[i - 1].halfRate) flips += 1;
  }
  assert.equal(flips, 1, `the half rate switched ${flips} times instead of once`);
  // The switch is LATCHED. A single improved interval - which is exactly what
  // the half rate produces, since the cheap frame is the one that is skipped -
  // must not read as "not slow any more" and switch it off again. That
  // re-derivation is the two-frame flicker this replaced: with half rate on,
  // the intervals measure the display, not the work.
  let after = nextFrameScale(seen[seen.length - 1], 33.3);
  assert.equal(after.halfRate, true, "one improved interval switched the half rate off");
  after = nextFrameScale(after, 45);
  assert.equal(after.halfRate, true, "the half rate flapped back on a genuinely slow machine");
  assert.equal(after.scale, RENDER_SCALE_MIN, "the picture left the floor");
});

check("a refused probe puts the picture back unchanged, and asks less and less often", () => {
  // A 30 Hz display whose machine is exactly at its limit: it holds 33.3 ms at
  // the floor and needs 45 ms the moment more pixels are spent. This is the
  // machine the fix must NOT punish - it is fine, but only just - and it is the
  // one the audit's "climb whenever the frame is not slow" fix would have
  // softened for ever.
  const seen = driveScale(RENDER_SCALE_MIN, 300,
    (state) => (state.scale <= RENDER_SCALE_MIN + 1e-9 ? 33.3 : 45));
  const ups = [];
  for (let i = 1; i < seen.length; i += 1) {
    if (seen[i].scale > seen[i - 1].scale + 1e-9) ups.push(i);
  }
  assert.ok(ups.length >= 1, "the picture never asked for pixels, so nothing was tested");
  assert.ok(ups.length <= 6,
    `the picture asked for pixels ${ups.length} times in 300 samples - that is a visible flap`);
  for (const i of ups) {
    // One probational step, by the base rule's own factor, and the refusal is
    // the very next sample taking it back to the floor - not lower.
    assert.equal(seen[i].scale, RENDER_SCALE_MIN / 0.75,
      `a probe went to ${seen[i].scale}, not one step up`);
    assert.ok(i + 1 < seen.length, "the run ended during a probe");
    assert.equal(seen[i + 1].scale, RENDER_SCALE_MIN,
      `a refused probe left the picture at ${seen[i + 1].scale}, not where it was`);
    assert.equal(seen[i + 1].halfRate, false,
      "a refused probe cost a machine that holds 30 fps its full frame rate");
  }
  // The waits grow, so a machine that cannot afford more is asked a handful of
  // times early and then essentially never.
  for (let k = 1; k < ups.length; k += 1) {
    assert.ok(ups[k] - ups[k - 1] > ups[k - 1] - (ups[k - 2] ?? 0),
      `the wait before probe ${k + 1} did not grow: at samples ${ups.join(", ")}`);
  }
  const last = seen[seen.length - 1];
  assert.equal(last.scale, RENDER_SCALE_MIN, "the picture did not end where it started");
  assert.equal(last.halfRate, false);
});

check("the picture settles at the resolution the machine can really afford", () => {
  // Afford up to 60% of the display's ratio: 33.3 ms at or below it, 45 ms
  // above. The rule should find that step and stay on it - neither the floor
  // (which is the bug) nor full resolution (which is the unsafe fix).
  const seen = driveScale(RENDER_SCALE_MIN, 120,
    (state) => (state.scale <= 0.6 + 1e-9 ? 33.3 : 45));
  const last = seen[seen.length - 1];
  assert.ok(last.scale > 0.5, `the picture settled at ${last.scale}, barely off the floor`);
  assert.ok(last.scale <= 0.6 + 1e-9, `the picture settled at ${last.scale}, past what is affordable`);
  assert.equal(last.halfRate, false);
  // Never runs away: the highest step it ever took is one probe above what the
  // machine can afford, and that probe was refused.
  const highest = Math.max(...seen.map((state) => state.scale));
  assert.ok(highest <= 0.6 / 0.75 + 1e-9, `the picture reached ${highest}`);
  // And it is settled, not wandering: the last 30 samples are all at the step
  // it chose. A probe may be refused inside that window, so allow the sample of
  // the probe itself - but the picture is back where it was on the next one.
  const tail = seen.slice(-30);
  const off = tail.filter((state) => Math.abs(state.scale - last.scale) > 1e-9);
  assert.ok(off.length <= 2,
    `${off.length} of the last 30 samples were away from ${last.scale.toFixed(4)} - the picture is wandering`);
});

/* -------------------------------------------------------------------------
 * Report
 * ---------------------------------------------------------------------- */

console.log(`\n${passed} check(s) passed, ${fails.length} failed`);
if (fails.length) process.exitCode = 1;
