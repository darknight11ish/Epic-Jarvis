/**
 * The 3D engine's per-frame budget: does a moving picture reuse the picture it
 * already has, or rebuild it thirty times a second?
 *
 *     node tests/galaxy-engine-reuse.mjs
 *
 * WHY THIS SUITE EXISTS
 *
 * The owner's guardrail for this wave (2026-10-28): the Galaxy's 3D engine must
 * CACHE ITS TOPOLOGY. `applyPositions` runs on every frame of the Planetary
 * Orrery - that look really orbits - and it used to rebuild the whole picture's
 * bookkeeping every time: a fresh array of position objects, two fresh Maps and
 * a fresh link array out of `presetLinks`, each entry carrying its own control
 * object. About 1,500 objects a frame, every one the same shape as the one the
 * previous frame had just thrown away.
 *
 * `galaxy-cosmos.mjs` proves the PURE half (layouts, framing, budgets). It
 * cannot see this, because the cost is in the render layer. `hud-galaxy-looks`
 * runs the real page in Chromium and proves pixels - and is not run at a desk
 * without Playwright. So this suite is the middle: the REAL `createEngine`,
 * driven with a small stand-in for three.js that COUNTS what gets constructed.
 * No GPU, no browser, no pixels - just the question the guardrail asks.
 *
 * WHAT IT HOLDS
 *
 *  1. A STEADY ORBITING FRAME ALLOCATES NOTHING THE GPU HAS TO RE-UPLOAD.
 *     After the first frame, sixty more frames of the Planetary Orrery construct
 *     no BufferGeometry, no BufferAttribute, no Line, no Mesh, no material and
 *     no Color.
 *  2. THE BUFFERS ARE THE SAME OBJECTS, AND THEY ARE MARKED. Every link's
 *     Float32Array is the same object frame to frame, its numbers really moved
 *     (the moons orbited), and its `needsUpdate` was raised so three.js
 *     re-uploads it.
 *  3. THE SHAPE STILL REBUILDS WHEN THE SHAPE CHANGES: a new graph, another
 *     look, and the zen-ring's chords toggle all build a new link set - the
 *     cache is a cache, not a stale picture - and the frame after each change is
 *     quiet again.
 *  4. DISPOSE REALLY LETS GO. The renderer is disposed, the canvas listener is
 *     removed (the page builds a NEW engine on the same canvas after Hide the
 *     galaxy, so a listener left behind would call a disposed engine's `onFail`
 *     and turn 3D off for good), and no frame draws afterwards.
 */
import assert from "node:assert/strict";

/* -------------------------------------------------------------------------
 * The stand-in for three.js: only what `createEngine` touches, and a counter
 * on every constructor so "did this frame allocate?" is a number, not a guess.
 * ---------------------------------------------------------------------- */

const built = new Map();
function count(name) {
  built.set(name, (built.get(name) || 0) + 1);
}
function taken() {
  const out = Object.fromEntries(built);
  built.clear();
  return out;
}

class Vector3 {
  constructor(x = 0, y = 0, z = 0) {
    count("Vector3");
    this.x = x; this.y = y; this.z = z;
  }
  set(x, y, z) { this.x = x; this.y = y; this.z = z; return this; }
  setScalar(value) { this.x = value; this.y = value; this.z = value; return this; }
  copy(other) { this.x = other.x; this.y = other.y; this.z = other.z; return this; }
  clone() { return new Vector3(this.x, this.y, this.z); }
  add(other) { this.x += other.x; this.y += other.y; this.z += other.z; return this; }
  sub(other) { this.x -= other.x; this.y -= other.y; this.z -= other.z; return this; }
  length() { return Math.hypot(this.x, this.y, this.z); }
  setLength(value) {
    const now = this.length() || 1;
    return this.set(this.x * value / now, this.y * value / now, this.z * value / now);
  }
  lerp(other, alpha) {
    this.x += (other.x - this.x) * alpha;
    this.y += (other.y - this.y) * alpha;
    this.z += (other.z - this.z) * alpha;
    return this;
  }
  distanceTo(other) { return Math.hypot(this.x - other.x, this.y - other.y, this.z - other.z); }
  setFromMatrixPosition() { return this; }
  project() { return this; }
}

class Color {
  constructor(hex = 0xffffff) { count("Color"); this.hex = hex; }
  setHex(hex) { this.hex = hex; return this; }
  set(hex) { this.hex = hex; return this; }
}

/** Every Line the engine builds, so the test can look at the real buffers. */
const builtLines = [];

class Object3D {
  constructor() {
    count(this.constructor.name);
    this.position = new Vector3();
    this.scale = new Vector3(1, 1, 1);
    this.rotation = {
      x: 0, y: 0, z: 0,
      set: (x, y, z) => { this.rotation.x = x; this.rotation.y = y; this.rotation.z = z; },
    };
    this.userData = {};
    this.children = [];
    this.visible = true;
    this.frustumCulled = true;
    this.matrixWorld = { elements: [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1] };
  }
  add(child) { if (child) { child.parent = this; this.children.push(child); } return this; }
  remove(child) {
    const at = this.children.indexOf(child);
    if (at >= 0) this.children.splice(at, 1);
    return this;
  }
  traverse(fn) {
    fn(this);
    for (const child of this.children.slice()) child.traverse(fn);
  }
  updateWorldMatrix() { /* the test never projects a point */ }
  lookAt() {}
}

class BufferAttribute {
  constructor(array, itemSize) {
    count("BufferAttribute");
    this.array = array;
    this.itemSize = itemSize;
    this.needsUpdate = false;
  }
}

class BufferGeometry {
  constructor(...args) {
    count(this.constructor === BufferGeometry ? "BufferGeometry" : this.constructor.name);
    void args;
    this.attributes = new Map();
    this.disposed = false;
  }
  setAttribute(name, attribute) { this.attributes.set(name, attribute); return this; }
  getAttribute(name) { return this.attributes.get(name); }
  setFromPoints(points) {
    this.setAttribute("position", new BufferAttribute(new Float32Array(points.length * 3), 3));
    return this;
  }
  dispose() { this.disposed = true; }
}

class Material {
  constructor(params = {}) {
    count(this.constructor.name);
    this.color = new Color(params.color === undefined ? 0xffffff : params.color);
    this.opacity = params.opacity === undefined ? 1 : params.opacity;
    this.transparent = Boolean(params.transparent);
    this.depthWrite = params.depthWrite !== false;
    this.disposed = false;
  }
  dispose() { this.disposed = true; }
}

class PointsMaterial extends Material {}
class MeshBasicMaterial extends Material {}
class LineBasicMaterial extends Material {}

class Mesh extends Object3D {
  constructor(geometry, material) {
    super();
    this.geometry = geometry;
    this.material = material;
  }
}

class Line extends Mesh {
  constructor(geometry, material) {
    super(geometry, material);
    builtLines.push(this);
  }
}

class Points extends Mesh {}

class Scene extends Object3D {
  constructor() { super(); this.fog = null; }
}

class Group extends Object3D {}

class FogExp2 {
  constructor(color, density) {
    count("FogExp2");
    this.color = new Color(color);
    this.density = density;
  }
}

class PerspectiveCamera extends Object3D {
  constructor(fov, aspect, near, far) {
    super();
    this.fov = fov; this.aspect = aspect; this.near = near; this.far = far;
  }
  updateProjectionMatrix() {}
}

class QuadraticBezierCurve3 {
  constructor(from, control, to) {
    count("QuadraticBezierCurve3");
    this.from = from; this.control = control; this.to = to;
  }
  getPoints(steps = 16) {
    const out = [];
    for (let i = 0; i <= steps; i++) {
      const t = i / steps;
      out.push(new Vector3(
        (1 - t) * (1 - t) * this.from.x + 2 * (1 - t) * t * this.control.x + t * t * this.to.x,
        (1 - t) * (1 - t) * this.from.y + 2 * (1 - t) * t * this.control.y + t * t * this.to.y,
        (1 - t) * (1 - t) * this.from.z + 2 * (1 - t) * t * this.control.z + t * t * this.to.z));
    }
    return out;
  }
}

/** Every renderer the engine builds, so `dispose` can be checked for real. */
const builtRenderers = [];

class WebGLRenderer {
  constructor(options = {}) {
    count("WebGLRenderer");
    this.canvas = options.canvas;
    this.disposed = false;
    this.renders = 0;
    builtRenderers.push(this);
  }
  setPixelRatio() {}
  setSize() {}
  setClearColor() {}
  render() { this.renders += 1; }
  dispose() { this.disposed = true; }
}

const THREE = {
  Vector3, Color, BufferAttribute, BufferGeometry,
  PointsMaterial, MeshBasicMaterial, LineBasicMaterial,
  Mesh, Line, Points, Scene, Group, FogExp2, PerspectiveCamera,
  QuadraticBezierCurve3, WebGLRenderer,
  // Every body `presetGuides` can ask for: the engine builds them, so the stub
  // accepts the same shapes even when one look only uses three of them.
  SphereGeometry: BufferGeometry,
  RingGeometry: BufferGeometry,
  ConeGeometry: BufferGeometry,
  CircleGeometry: BufferGeometry,
  IcosahedronGeometry: BufferGeometry,
  TorusGeometry: BufferGeometry,
  OctahedronGeometry: BufferGeometry,
  ACESFilmicToneMapping: 4,
  DoubleSide: 2,
};

/* -------------------------------------------------------------------------
 * The page the engine thinks it is in: a canvas, and a window holding THREE.
 * ---------------------------------------------------------------------- */

let contextLostListeners = 0;
const canvas = {
  hidden: false,
  addEventListener(type) { if (type === "webglcontextlost") contextLostListeners += 1; },
  removeEventListener(type) { if (type === "webglcontextlost") contextLostListeners -= 1; },
  getContext: () => ({}),
};
globalThis.document = {
  createElement: () => canvas,
  querySelector: () => null,
  head: { appendChild() {} },
};
globalThis.window = { THREE };

const { createEngine, COSMOS_DEFAULT_LOOK } = await import("../src/galaxy-cosmos.js");

/* -------------------------------------------------------------------------
 * A graph the shape of /api/graph's
 * ---------------------------------------------------------------------- */

function graphOf() {
  const nodes = [{ id: "core", label: "Jarvis", group: "core", weight: 9 }];
  for (let i = 0; i < 4; i++) {
    nodes.push({ id: `brain-${i}`, label: `Brain ${i}`, group: "brain", weight: 5 });
  }
  for (let i = 0; i < 6; i++) {
    nodes.push({ id: `group-${i}`, label: `Group ${i}`, group: "project", weight: 3 });
  }
  for (let i = 0; i < 18; i++) {
    nodes.push({ id: `tool-${i}`, label: `Tool ${i}`, group: "tool", weight: 1 });
  }
  for (let i = 0; i < 12; i++) {
    nodes.push({ id: `memory-${i}`, label: `Memory ${i}`, group: "person", weight: 2 });
  }
  const links = [];
  // Every tool hangs off a group, the way the orrery's moons orbit one.
  for (let i = 0; i < 18; i++) links.push({ source: `group-${i % 6}`, target: `tool-${i}`, kind: "has" });
  for (let i = 0; i < 12; i++) links.push({ source: "core", target: `memory-${i}`, kind: "knows" });
  for (let i = 0; i < 6; i++) links.push({ source: "core", target: `group-${i}`, kind: "has" });
  return { nodes, links };
}

/** The link Lines the engine owns right now: the ones carrying a cached position
 *  buffer that has not been disposed with an earlier picture. */
const linkLines = () => builtLines.filter((line) =>
  line.userData && line.userData.posAttr && !line.geometry.disposed);

const fails = [];
let passed = 0;
async function check(name, fn) {
  try {
    await fn();
    passed += 1;
    console.log(`ok   ${name}`);
  } catch (error) {
    fails.push({ name, error });
    console.log(`FAIL ${name}\n     ${error && error.message ? error.message : error}`);
  }
}

/* -------------------------------------------------------------------------
 * The checks
 * ---------------------------------------------------------------------- */

const graph = graphOf();
const engine = await createEngine({ canvas });
assert.ok(engine, "createEngine returned nothing, so nothing below can be measured");

engine.resize(1200, 900, 1);
engine.setPreset(COSMOS_DEFAULT_LOOK);
engine.setGraph(graph.nodes, graph.links);
engine.setSpinning(true);

let clock = 0;
/** Run `frames` frames, returning what was constructed during them. */
function step(frames = 1) {
  taken();                                    // discard what the caller built
  for (let i = 0; i < frames; i++) {
    clock += 16.7;
    engine.frame(clock);
  }
  return taken();
}

step(1);                                      // frame zero builds the picture

await check("sixty frames of the orbiting orrery build no geometry, buffer, line, mesh, material or colour", () => {
  const plansBefore = engine.info().plans;
  const counts = step(60);
  for (const name of ["BufferGeometry", "BufferAttribute", "Line", "Mesh",
    "MeshBasicMaterial", "LineBasicMaterial", "Color", "WebGLRenderer"]) {
    assert.equal(counts[name] || 0, 0,
      `${name} was constructed ${counts[name] || 0} time(s) in 60 steady frames; `
      + "the picture is being rebuilt instead of reused");
  }
  const info = engine.info();
  assert.equal(info.plans, plansBefore,
    `the link plan was rebuilt ${info.plans - plansBefore} time(s) in 60 steady frames `
    + "(the cache is not caching: `presetLinks` must not run on a frame that only moved)");
  assert.equal(info.lost, false, "the stand-in never lost its context");
  assert.ok(info.draws > 60, `the engine drew ${info.draws} frames, so 60 frames did not run`);
});

await check("every link's Float32Array is the same object frame to frame, is marked, and really moved", () => {
  const lines = linkLines();
  assert.ok(lines.length > 0, "no link kept a position buffer");
  const before = lines.map((line) => line.userData.posAttr.array);
  for (const line of lines) line.userData.posAttr.needsUpdate = false;
  const snapshot = before.map((array) => Array.from(array));

  step(1);

  for (let i = 0; i < lines.length; i++) {
    const attr = lines[i].userData.posAttr;
    assert.equal(attr.array, before[i],
      `link ${i} replaced its Float32Array - the buffer was rebuilt, not updated in place`);
    assert.equal(attr.needsUpdate, true,
      `link ${i} never raised needsUpdate, so the GPU would never see the new vertices`);
  }
  const moved = before.filter((array, i) =>
    array.some((value, at) => value !== snapshot[i][at]));
  assert.ok(moved.length > 0,
    "no link moved in a frame of the Planetary Orrery, so the orbit did not tick");
});

await check("a new graph rebuilds the link objects and the plan exactly once, then holds still", () => {
  const plansBefore = engine.info().plans;
  const shape = graphOf();
  shape.links = shape.links.slice(0, 12);      // a genuinely different set
  engine.setGraph(shape.nodes, shape.links);
  const builtNow = taken();
  assert.ok((builtNow.Line || 0) > 0,
    "setGraph built no new Lines, so the cache never noticed a changed graph");
  assert.equal(engine.info().plans, plansBefore + 1,
    "a changed graph did not rebuild the link plan exactly once");
  const plansAfter = engine.info().plans;
  const counts = step(10);
  assert.equal(counts.Line || 0, 0, "the ten frames after a new graph built more Lines");
  assert.equal(counts.BufferGeometry || 0, 0,
    "the ten frames after a new graph built more geometries");
  assert.equal(engine.info().plans, plansAfter, "the ten frames after a new graph rebuilt the plan");
});

await check("another look rebuilds the lines once, then holds still", () => {
  const plansBefore = engine.info().plans;
  engine.setPreset("zen-ring");
  const builtNow = taken();
  assert.ok((builtNow.Line || 0) > 0, "switching look built no new Lines");
  assert.equal(engine.info().plans, plansBefore + 1,
    "a look change did not rebuild the link plan exactly once");
  const plansAfter = engine.info().plans;
  const counts = step(10);
  assert.equal(counts.Line || 0, 0, "the zen ring rebuilt its Lines every frame");
  assert.equal(counts.BufferAttribute || 0, 0, "the zen ring rebuilt its buffers every frame");
  assert.equal(engine.info().plans, plansAfter, "the zen ring rebuilt its plan every frame");
});

await check("the zen-ring chords toggle rebuilds the link set: a cache, not a stale picture", () => {
  const full = engine.info().links;
  assert.ok(full > 0, "the zen ring drew no chords to begin with");
  const plansBefore = engine.info().plans;
  engine.action("chords");                     // hide them
  const off = engine.info().links;
  // `presetLinks` still returns ONE entry at the zen ring's chords-off cap of 0
  // (it pushes before it checks the cap) - the look hides every line instead.
  // That is the pure half's own behaviour and is not changed here.
  assert.ok(off <= 1, `chords off still drew ${off} links`);
  const hidden = linkLines().every((line) => line.visible === false);
  assert.equal(hidden, true, "chords off left a chord line visible");
  engine.action("chords");                     // and back on
  assert.equal(engine.info().links, full, "chords back on did not restore the same link count");
  assert.equal(linkLines().every((line) => line.visible === true), true,
    "chords back on left a chord line hidden");
  assert.equal(engine.info().plans, plansBefore + 2,
    "the two chords clicks did not each rebuild the link plan");
});

await check("dispose lets go: the renderer is disposed and the canvas listener is removed", () => {
  assert.ok(contextLostListeners > 0, "no context-lost listener was ever added");
  const listeners = contextLostListeners;
  const renderer = builtRenderers.at(-1);
  engine.dispose();
  assert.equal(renderer.disposed, true, "dispose left the WebGL renderer alive");
  assert.equal(contextLostListeners, listeners - 1,
    "dispose left its webglcontextlost listener on the canvas; the next engine built on "
    + "this canvas would inherit it and call a disposed engine's onFail");
  assert.equal(engine.frame(clock + 16.7), false, "a disposed engine still drew a frame");
});

/* -------------------------------------------------------------------------
 * Report
 * ---------------------------------------------------------------------- */

console.log();
if (fails.length) {
  console.log(`${fails.length} FAILED:`);
  for (const fail of fails) console.log(`  - ${fail.name}`);
  process.exit(1);
}
console.log(`${passed} check(s) passed. The 3D engine reuses its picture between frames.`);
