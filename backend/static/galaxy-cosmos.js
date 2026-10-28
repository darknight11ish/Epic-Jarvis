/**
 * The Galaxy's 3D cosmos - the eight looks from the Gemini page, drawn with
 * three.js over the HUD's REAL graph.
 *
 * The owner, 2026-10-27: "none of the galaxy on the current jarvis hud look
 * like the one that gemini made... i would to simplify all the galaxy options".
 * He chose "Port Gemini's exact 3D look" and Planetary Orrery as the default.
 * The reference is the standalone page
 * `j_a_r_v_i_s_holographic_neural_cosmos_v2_6_8_distinct_presets_custom_icon_studio.html`
 * (Three.js r128, one scene, 32 sample nodes, eight coordinate systems). This
 * module is the visual ENGINE half of that port; the Galaxy Options menu is a
 * separate workstream and only gets a mount point here.
 *
 * WHAT THIS MODULE IS
 *
 *   - One scene, one camera, one renderer: exactly the shape the Gemini page
 *     has (its "eight engines" are eight coordinate systems over one scene,
 *     not eight engines).
 *   - The EIGHT looks keep the ids the repository already uses in
 *     `galaxy-presets.js` (and therefore the ids the Brain window's chips and
 *     the look switcher already show). Mapping, Gemini id -> this module:
 *
 *       cosmos   -> planetary-orbit   Planetary Orrery  (the default)
 *       neural   -> neural-arbor      Neural Cortex
 *       memory   -> nebula            Memory Nebula
 *       helix    -> dna-helix         Chrono Helix
 *       sentinel -> radar-dome        Tactical Sentinel
 *       flat     -> star-map          2D Star Map
 *       tree     -> clean-tree        Clean Hierarchy
 *       ring     -> zen-ring          Zen Ring
 *
 *   - The geometry, guides, palette, camera and motion are ported faithfully:
 *     the same radii, the same wave amplitudes, the same guide bodies, the same
 *     `FogExp2` density 0.0016 (scaled with the camera only when the frame has
 *     to pull back, so a 240-name picture is not fogged to black), the same ACES
 *     exposure 1.25, the same 1,800 background stars and 3,200-point nebula
 *     cloud, the same five animation branches.
 *
 * WHAT IS DELIBERATELY DIFFERENT FROM THE GEMINI PAGE
 *
 *   - It draws the REAL graph (`/api/graph`): the page's 32 nodes carry
 *     invented facts about this owner (a network hostname, a folder path, a
 *     weekly sync, made-up retention scores). None of that is here. Labels are
 *     never drawn by this module at all: the page's existing label pass draws
 *     them, with its own node and label budgets.
 *   - Three fields the rich looks key on do not exist in `/api/graph`
 *     (`cluster`, `timestamp`, `secRing`). They are DERIVED from data that
 *     does exist, and every derivation is a named function below so the PR can
 *     say exactly what it approximates (see `wellOf`, `ringOf`,
 *     `timeFractions`).
 *   - Budgets: at most 240 names, and a ring that cannot hold its names at a
 *     readable spacing grows OUTWARD instead of crowding (Gemini's fixed radii
 *     are kept whenever the list fits them - i.e. for every graph up to about
 *     30 names, which is Gemini's own size).
 *   - Framing is the one place the page's own numbers are deliberately not
 *     copied. Gemini's cameras crop its own picture (6 of 32 names off-frame in
 *     its nebula at 1440x900) and its labels sit about 30 px tall under a
 *     banner across a third of the screen. Here every name is kept inside
 *     `FRAME_FILL` of the half-frame - Gemini's exact camera when the picture
 *     already fits it, the same angle from further back when it does not - so
 *     120 and 240 real names stay on screen; labels are the page's own 10-14 px
 *     pass, and there is no banner over the picture.
 *   - It is offline: three.js is loaded from this origin (`/three.min.js`),
 *     never from a CDN. If it is not there, `createEngine` resolves `null` and
 *     the page keeps drawing its 2D picture - the fallback, not a blank canvas.
 *   - Everything it creates is disposed of when a preset or the graph changes
 *     (the Gemini page leaks a `BufferGeometry` per preset switch).
 *
 * WHAT IT NEVER DOES
 *
 *   - No DOM work beyond the canvas it is handed; no fetch, no storage, no
 *     global key handler, no timer. The page owns the loop and the pauses.
 *   - No `Math.random`: the starfield and the nebula cloud come from a seeded
 *     generator, so the sky is the same on every load.
 *   - Nothing here throws for normal input. A failure anywhere in `createEngine`
 *     resolves `null`, and the caller's fallback is the shipped picture.
 *
 * The pure half (everything down to `createEngine`) imports nothing and touches
 * no DOM, so `tests/galaxy-cosmos.mjs` runs it with no browser at all.
 *
 * @module galaxy-cosmos
 */

/* ==========================================================================
 * 1. The eight looks: palette, camera, and the owner's default
 * ========================================================================== */

/** The look the Galaxy opens on, the owner's choice of 2026-10-27.
 *
 *  It is the Gemini page's own default (`cosmos`, Planetary Orrery). The page
 *  stores the choice under the existing look key, so it is applied once and
 *  remembered, and choosing the constellation later still works. */
export const COSMOS_DEFAULT_LOOK = "planetary-orbit";

/** The most names any look places. Same bound as `galaxy-presets.js`'s
 *  `MAX_LAYOUT_NODES` and the picture's own `MAX_RENDERED_NODES`. */
export const MAX_COSMOS_NODES = 240;

/** The most links drawn. The Gemini page has 39; a real graph can have
 *  thousands, and a thousand chords is a grey disc, so the first 360 in the
 *  payload's own order are drawn and the picture says nothing it cannot show. */
export const MAX_COSMOS_LINKS = 360;

/** Closest two node centres may be, in scene units, before a ring grows.
 *  The drawn bodies are at most 9 units across, so 24 is two bodies plus air -
 *  the same rule `galaxy-presets.js` uses for its flat layouts. */
export const MIN_GAP = 24;

/** The Gemini page's numbers, kept verbatim. */
export const STAR_COUNT = 1800;
export const NEBULA_POINTS = 3200;
export const FOG_DENSITY = 0.0016;
export const TONE_EXPOSURE = 1.25;
export const CAMERA_FOV = 45;
export const CAMERA_NEAR = 0.1;
export const CAMERA_FAR = 2000;

/** The orbit camera's limits, from the page's OrbitControls settings. */
export const MIN_CAMERA_DISTANCE = 20;
export const MAX_CAMERA_DISTANCE = 620;

/** How many names one helix column holds before another is drawn beside it.
 *
 *  Gemini puts 21 names on one 160-unit strand (about 7.6 units apart) and
 *  calls it a day. 24 keeps that spacing, so a picture of Gemini's own size is
 *  ONE column - and a 240-name picture becomes a bank of narrow helices instead
 *  of a 3,000-unit ribbon no camera can frame. */
export const HELIX_PER_COLUMN = 24;
export const HELIX_COLUMN_GAP = 160;

/** The zen ring's spacing: 21 units is what lets Gemini's own 31 names sit on
 *  one R=108 halo (2 * pi * 108 / 31 = 21.9). It is `galaxy-presets.js`'s own
 *  `ZEN_HALO_GAP` and the page's ring, in one number. */
export const ZEN_HALO_GAP = 21;

/** clean-tree's row width budget, and the pitch between wrapped lanes.
 *
 *  Gemini's rows are a fixed ~200 units wide (a 32-name graph). A 240-name row
 *  at the same width would be a smear, so a row wraps into lanes 30 units
 *  apart once it passes the width budget - the hierarchy still reads as rows. */
export const TREE_MAX_WIDTH = 2200;
export const TREE_LANE_PITCH = 30;
export const TREE_COL_GAP = 26;

/** One look's palette, camera and Gemini name.
 *
 *  `bg` is the page's own `bgHex` (it sets `document.body.style.
 *  backgroundColor`); the fog is the same colour at density `FOG_DENSITY`.
 *  `camera`/`lookAt` are the page's `cameraPos`/`lookAt`, verbatim. */
export const COSMOS_PRESETS = Object.freeze({
  "planetary-orbit": Object.freeze({
    id: "planetary-orbit",
    gemini: "cosmos",
    label: "Planetary orbit",
    title: "Planetary orrery",
    bg: "#030712",
    camera: Object.freeze([0, 150, 230]),
    lookAt: Object.freeze([0, 0, 0]),
    fitRadius: 130,
  }),
  "neural-arbor": Object.freeze({
    id: "neural-arbor",
    gemini: "neural",
    label: "Neural arbor",
    title: "Neural cortex",
    bg: "#090418",
    camera: Object.freeze([0, 45, 235]),
    lookAt: Object.freeze([0, 6, 0]),
    fitRadius: 118,
  }),
  nebula: Object.freeze({
    id: "nebula",
    gemini: "memory",
    label: "Nebula",
    title: "Memory nebula",
    bg: "#0c0612",
    camera: Object.freeze([65, 80, 185]),
    lookAt: Object.freeze([0, 0, 0]),
    fitRadius: 146,
  }),
  "dna-helix": Object.freeze({
    id: "dna-helix",
    gemini: "helix",
    label: "DNA helix",
    title: "Chrono helix",
    bg: "#021014",
    camera: Object.freeze([165, 15, 165]),
    lookAt: Object.freeze([0, 0, 0]),
    fitRadius: 96,
  }),
  "radar-dome": Object.freeze({
    id: "radar-dome",
    gemini: "sentinel",
    label: "Radar dome",
    title: "Tactical sentinel",
    bg: "#070b0e",
    camera: Object.freeze([0, 215, 135]),
    lookAt: Object.freeze([0, 0, 0]),
    fitRadius: 121,
  }),
  "star-map": Object.freeze({
    id: "star-map",
    gemini: "flat",
    label: "Star map",
    title: "2D star map",
    bg: "#040914",
    camera: Object.freeze([0, 255, 4]),
    lookAt: Object.freeze([0, 0, 0]),
    fitRadius: 110,
  }),
  "clean-tree": Object.freeze({
    id: "clean-tree",
    gemini: "tree",
    label: "Clean tree",
    title: "Clean hierarchy",
    bg: "#050a12",
    camera: Object.freeze([0, 8, 240]),
    lookAt: Object.freeze([0, 0, 0]),
    fitRadius: 120,
  }),
  "zen-ring": Object.freeze({
    id: "zen-ring",
    gemini: "ring",
    label: "Zen ring",
    title: "Zen ring",
    bg: "#03060c",
    camera: Object.freeze([0, 240, 25]),
    lookAt: Object.freeze([0, 0, 0]),
    fitRadius: 110,
  }),
});

/** The eight ids in hotkey order - the same order `BUILT_PRESETS` uses. */
export const COSMOS_PRESET_ORDER = Object.freeze([
  "planetary-orbit", "neural-arbor", "nebula", "dna-helix",
  "radar-dome", "star-map", "clean-tree", "zen-ring",
]);

/** True when `id` is one of the eight looks this module draws. */
export function isCosmosLook(id) {
  return Object.prototype.hasOwnProperty.call(COSMOS_PRESETS, String(id));
}

/** One look's profile, or null for the constellation and anything unknown. */
export function presetMeta(id) {
  return isCosmosLook(id) ? COSMOS_PRESETS[id] : null;
}

/** One look's camera pair, as plain arrays (a copy: callers may mutate). */
export function cameraFor(id) {
  const meta = presetMeta(id);
  return meta ? { position: meta.camera.slice(), lookAt: meta.lookAt.slice() }
              : { position: [0, 150, 230], lookAt: [0, 0, 0] };
}

/**
 * How much of the half-frame a name's own centre may use: every name is kept
 * within 82% of the way to an edge, so the outer 9% of the width and the height
 * is left for the rest of the picture - a round body's own radius, the label
 * above it, and air. Measured, not guessed: on a 900 px stage the margin is
 * 81 px, and the widest body at the 240-name budget is about 13 px across with
 * a 24 px label above it.
 *
 * This is the one rule that keeps the port readable where the reference page is
 * not: Gemini's page crops itself - its nebula puts 6 of 32 names off-frame at
 * 1440x900, its tree and ring crop too - because its cameras were tuned for one
 * picture size and nothing pulls them back. The look is Gemini's; the framing
 * is this repository's.
 */
export const FRAME_FILL = 0.82;

/**
 * The camera for a look: Gemini's own, unless the real picture does not fit it.
 *
 * Gemini tunes one camera per look for a 32-name picture on a wide window. The
 * HUD can show 240 names, on a stage that is sometimes a narrow column, so the
 * rule has two halves:
 *
 *   - the page's own camera is kept whenever EVERY name it is about to draw
 *     already sits inside `FRAME_FILL` of the half-frame at this aspect. A
 *     Gemini-sized picture therefore gets his exact position and angle;
 *   - otherwise the camera backs straight away from the same `lookAt` along
 *     the same direction - only the distance changes, so the look is still the
 *     look - and stops at the first distance where the outermost name is
 *     exactly on the `FRAME_FILL` line. `positions` is the actual set of
 *     points, so a flat ring and a tall helix are each fitted for their own
 *     shape; `radius` is a fallback for callers that only have a bounding
 *     sphere (a sphere of that radius about the lookAt is fitted whole, which
 *     is the conservative answer).
 *
 * The maths is exact and per-point, not a bounding-sphere guess: for a camera
 * at distance `d` along the look direction, a point has depth `d - s` and
 * horizontal offset `xc`, so it is inside the frame when
 * `d >= s + |xc| / (FILL * tan(halfFov) * aspect)` (and the same for the
 * vertical). The largest such bound is the distance that frames every name.
 *
 * Pure, so `tests/galaxy-cosmos.mjs` pins the framing without a camera at
 * 1440x900 at the 120- and 240-name budgets.
 */
export function cameraFrame(id, {
  positions = null, radius = 0, aspect = 1.6, fov = CAMERA_FOV,
} = {}) {
  const meta = presetMeta(id) || COSMOS_PRESETS[COSMOS_DEFAULT_LOOK];
  const lookAt = meta.lookAt.slice();
  const base = meta.camera.slice();
  const dx = base[0] - lookAt[0];
  const dy = base[1] - lookAt[1];
  const dz = base[2] - lookAt[2];
  const baseDistance = Math.hypot(dx, dy, dz) || 1;
  const half = (fov * Math.PI) / 180 / 2;
  const tanV = Math.tan(half);
  const tanH = tanV * Math.max(0.05, aspect);
  const need = frameDistanceFor(presetMeta(id) ? positions : null, radius, {
    lookAt, position: base, baseDistance, tanV, tanH,
  });
  if (!(need > baseDistance + 1e-6)) {
    return { position: base, lookAt, distance: baseDistance, fitted: false, fill: FRAME_FILL };
  }
  const k = need / baseDistance;
  return {
    position: [lookAt[0] + dx * k, lookAt[1] + dy * k, lookAt[2] + dz * k],
    lookAt,
    distance: need,
    fitted: true,
    fill: FRAME_FILL,
  };
}

/** The smallest camera distance that keeps every point inside `FRAME_FILL`.
 *  Shared by `cameraFrame` and the framing test, so both use one rule. */
function frameDistanceFor(positions, radius, { lookAt, position, baseDistance, tanV, tanH }) {
  let need = 0;
  if (Array.isArray(positions) && positions.length) {
    // The camera's own basis: it looks from `position` toward `lookAt`.
    const fx = (lookAt[0] - position[0]) / baseDistance;
    const fy = (lookAt[1] - position[1]) / baseDistance;
    const fz = (lookAt[2] - position[2]) / baseDistance;
    // right = normalize(cross(forward, worldUp)); forward is never vertical here.
    const rl = Math.hypot(fz, 0, fx) || 1;
    const rx = -fz / rl;
    const rz = fx / rl;
    const ux = -rz * fy;          // cross(right, forward)
    const uy = rz * fx - rx * fz;
    const uz = rx * fy;
    // The camera sits at lookAt - forward * distance, so a point's depth is
    // `distance + dot(point - lookAt, forward)`; call that component s and the
    // bound reads d >= s + |offset| / (FILL * tan).
    for (const point of positions) {
      const ox = point.x - lookAt[0];
      const oy = point.y - lookAt[1];
      const oz = point.z - lookAt[2];
      const s = -(ox * fx + oy * fy + oz * fz);
      const xc = ox * rx + oz * rz;
      const yc = ox * ux + oy * uy + oz * uz;
      need = Math.max(need,
        s + Math.abs(xc) / (FRAME_FILL * tanH),
        s + Math.abs(yc) / (FRAME_FILL * tanV));
    }
  } else {
    // A whole sphere about the lookAt: it is inside the view cone when
    // sin(halfAngle) >= radius / distance.
    const halfMin = Math.min(Math.atan(tanV), Math.atan(tanH));
    need = Math.max(0, radius) / (FRAME_FILL * Math.sin(halfMin));
  }
  return need;
}

/** The distance at which a sphere of `radius` fills the smaller of the two
 *  fields of view. Pure trigonometry, no three.js. */
export function fitDistance(radius, aspect = 1.6, fov = CAMERA_FOV) {
  const half = (fov * Math.PI / 180) / 2;
  const vertical = Math.tan(half);
  const horizontal = vertical * Math.max(0.2, aspect);
  const r = Math.max(1, radius);
  return Math.max(r / vertical, r / horizontal);
}

/** Where one point lands in one camera, in the engine's own terms.
 *
 *  Used by the page for its node buttons (via the live three.js camera) and by
 *  the framing test (via `cameraFrame`'s pure result), so both sides project
 *  the same way. `ndcX`/`ndcY` are -1..1 inside the frame, `x`/`y` are pixels
 *  when `width`/`height` are given, `k` is pixels per scene unit at that depth
 *  (so a body's drawn radius is `nodeRadius * k`), and `inFront` is false for a
 *  point behind the camera. */
export function projectPoint(point, camera, options = {}) {
  const { fov = CAMERA_FOV, aspect = 1.6, width = 0, height = 0 } = options;
  const position = (camera && camera.position) || [0, 0, 1];
  const lookAt = (camera && camera.lookAt) || [0, 0, 0];
  let fx = lookAt[0] - position[0];
  let fy = lookAt[1] - position[1];
  let fz = lookAt[2] - position[2];
  const fl = Math.hypot(fx, fy, fz) || 1;
  fx /= fl; fy /= fl; fz /= fl;
  const rl = Math.hypot(fz, 0, fx) || 1;
  const rx = -fz / rl;
  const rz = fx / rl;
  const ux = -rz * fy;
  const uy = rz * fx - rx * fz;
  const uz = rx * fy;
  const ox = point.x - position[0];
  const oy = point.y - position[1];
  const oz = point.z - position[2];
  const depth = ox * fx + oy * fy + oz * fz;
  const half = Math.tan((fov * Math.PI) / 180 / 2);
  const safeDepth = Math.max(1e-6, depth);
  const xc = ox * rx + oz * rz;
  const yc = ox * ux + oy * uy + oz * uz;
  const ndcX = xc / (safeDepth * half * Math.max(0.05, aspect));
  const ndcY = yc / (safeDepth * half);
  return {
    ndcX: depth > 0 ? ndcX : NaN,
    ndcY: depth > 0 ? ndcY : NaN,
    x: (ndcX * 0.5 + 0.5) * width,
    y: (-ndcY * 0.5 + 0.5) * height,
    k: (height / 2) / Math.max(1e-6, half * safeDepth),
    depth,
    inFront: depth > 0,
  };
}

/** The fog density a pulled-back camera uses.
 *
 *  Gemini's `FogExp2` density is 0.0016 because its cameras sit about 250 units
 *  out; at the 240-name budget this engine legitimately sits at 900 or 2,700
 *  units, where that density would fog the whole picture to the background
 *  colour (a 2,700-unit camera keeps about 3% of the light). Scaling the
 *  density with the framed distance keeps the DEPTH CUE - near names clear,
 *  far names fading - while keeping the far edge of the content about as
 *  visible as Gemini's own far edge. Gemini's 0.0016 is used unchanged for
 *  every picture his camera already frames (distance <= 250). */
export function fogDensityAt(distance, reference = 250) {
  const d = Number.isFinite(distance) ? Math.max(1, distance) : reference;
  return FOG_DENSITY * Math.min(1, reference / d);
}

/* ==========================================================================
 * 2. Roles: the eleven HUD groups folded onto Gemini's five categories
 * ========================================================================== */

/**
 * Gemini's five node categories, applied to the HUD's eleven groups.
 *
 * This is the 1:1 map the spec asks for (its §5.3 table): the capability half
 * is brains / ability groups / abilities, the memory half is everything saved.
 * `source` is a saved thing (where a fact came from) and `skill` is a
 * capability, so they join the memory and tool halves respectively rather than
 * inventing a sixth category. An unknown group is treated as memory: it is the
 * half that holds "things Jarvis has", which is the safer guess for a group
 * this module has never heard of.
 */
export const ROLE_OF_GROUP = Object.freeze({
  core: "core",
  model: "brain",
  cluster: "group",
  tool: "tool",
  skill: "tool",
  fact: "memory",
  document: "memory",
  entity: "memory",
  project: "memory",
  persona: "memory",
  source: "memory",
});

/** Gemini's category for one HUD group. */
export function roleOf(group) {
  return ROLE_OF_GROUP[String(group)] || "memory";
}

/** The nodes grouped by role, each list in the order it was given.
 *  `{core, brain, group, tool, memory}` - every list is a fresh array. */
export function byRole(nodes) {
  const out = { core: [], brain: [], group: [], tool: [], memory: [] };
  for (const node of Array.isArray(nodes) ? nodes : []) {
    if (!node || node.id === undefined || node.id === null) continue;
    out[roleOf(node.group)].push(node);
  }
  return out;
}

/**
 * Which ability group each ability belongs to, from the graph's own links.
 *
 * Gemini reads `parent` off each tool node. `/api/graph` sends the same fact as
 * a link instead (`cluster:x --has--> tool:y`, `jarvis_hud.py`), so this is a
 * derivation, not a guess: a link is only believed when its `kind` is `has`
 * (when the payload carries a kind at all) and its two ends are a group and an
 * ability. Anything unlinked is simply absent from the map, and the caller
 * places those abilities on a ring of their own.
 */
export function parentOf(nodes, links) {
  const role = new Map();
  for (const node of Array.isArray(nodes) ? nodes : []) {
    if (node && node.id !== undefined) role.set(node.id, roleOf(node.group));
  }
  const out = new Map();
  let groups = 0;
  for (const link of Array.isArray(links) ? links : []) {
    if (!link || groups > 4096) break;
    if (link.kind !== undefined && link.kind !== "has") continue;
    const a = role.get(link.source);
    const b = role.get(link.target);
    if (a === "group" && b === "tool" && !out.has(link.target)) {
      out.set(link.target, link.source);
      groups += 1;
    } else if (b === "group" && a === "tool" && !out.has(link.source)) {
      out.set(link.source, link.target);
      groups += 1;
    }
  }
  return out;
}

/* ==========================================================================
 * 3. The three fields `/api/graph` does not send, derived honestly
 * ========================================================================== */

/**
 * SENTINEL'S RINGS. Gemini bins nodes by `secRing` - a security taint band
 * (0 = own vault, 1 = behind a gate, 2 = external). `/api/graph` sends no such
 * field, so the three rings here are THREE KINDS OF THING instead:
 *
 *   ring 0 - Jarvis itself and what it runs on (core, brains, ability groups)
 *   ring 1 - what it can do (abilities and skills)
 *   ring 2 - everything it has saved (facts, documents, knowledge, projects,
 *            personas, sources)
 *
 * The picture is therefore NOT a security statement and the code never says
 * it is. The rings keep Gemini's radii, heights and colours so the look is the
 * look; only the meaning of membership is this repository's own.
 */
export const SENTINEL_RINGS = Object.freeze([
  Object.freeze({ key: "jarvis", r: 34, y: 18, color: "#10b981" }),
  Object.freeze({ key: "abilities", r: 72, y: 4, color: "#f59e0b" }),
  Object.freeze({ key: "saved", r: 115, y: -10, color: "#f43f5e" }),
]);

/** Which of the three sentinel rings one node belongs to (0, 1 or 2). */
export function ringOf(group) {
  const role = roleOf(group);
  if (role === "core" || role === "brain" || role === "group") return 0;
  if (role === "tool") return 1;
  return 2;
}

/**
 * NEBULA'S WELLS. Gemini keys its four clouds on `node.cluster`
 * (coding / hardware / schedule / network) - four invented categories that
 * `/api/graph` has no field for. The four wells here are the HUD's own memory
 * groups, which is the same structural idea (saved things grouped by what kind
 * of thing they are) using words the graph really contains. Each well keeps
 * Gemini's position, radius and colour.
 */
export const NEBULA_WELLS = Object.freeze([
  Object.freeze({ key: "facts", label: "Facts", at: Object.freeze([72, 22, 42]),
                 r: 38, color: "#fbbf24", groups: Object.freeze(["fact"]) }),
  Object.freeze({ key: "knowledge", label: "Knowledge", at: Object.freeze([-72, 22, -42]),
                 r: 38, color: "#a855f7",
                 groups: Object.freeze(["entity", "document", "persona"]) }),
  Object.freeze({ key: "work", label: "Projects", at: Object.freeze([-68, -32, 42]),
                 r: 34, color: "#10b981", groups: Object.freeze(["project"]) }),
  Object.freeze({ key: "sources", label: "Sources", at: Object.freeze([68, -32, -42]),
                 r: 34, color: "#06b6d4", groups: Object.freeze(["source"]) }),
]);

/** Which nebula well one group's saved things join (0..3). An unknown group
 *  joins the last well rather than vanishing. */
export function wellOf(group) {
  const name = String(group);
  for (let i = 0; i < NEBULA_WELLS.length; i++) {
    if (NEBULA_WELLS[i].groups.includes(name)) return i;
  }
  return NEBULA_WELLS.length - 1;
}

/**
 * HELIX'S ORDER. Gemini sorts its two strands by `node.timestamp` and maps
 * 0..100 onto the tunnel's height. `/api/graph` sends no timestamp, but it does
 * send `meta` and `detail` as free text, and this repository writes dates into
 * those (`"saved 2026-10-24"`, `"2026-10-01"`). So:
 *
 *   - a date inside `meta` (or `detail`) is read, when one parses;
 *   - with two or more dates the order is real time, and a node with no date
 *     sits in the middle (0.5) rather than being pushed to either end;
 *   - with fewer than two dates there is no time axis at all, so the strand is
 *     ordered by id and spread evenly - deterministic, and the code says so.
 *
 * The returned fraction is 0..1 per id. Nothing here claims the graph carries a
 * timestamp: `hasTime` says whether any real date was found.
 */
export function timeFractions(nodes) {
  const list = Array.isArray(nodes) ? nodes : [];
  const stamps = list.map((node) => stampOf(node));
  const known = stamps.filter((v) => v !== null);
  const out = new Map();
  if (known.length >= 2) {
    const min = Math.min(...known);
    const max = Math.max(...known);
    if (max > min) {
      list.forEach((node, i) => {
        const stamp = stamps[i];
        out.set(node.id, stamp === null ? 0.5 : (stamp - min) / (max - min));
      });
      return { fractions: out, hasTime: true };
    }
  }
  const ordered = list.slice().sort((a, b) => String(a.id).localeCompare(String(b.id)));
  const span = Math.max(1, ordered.length - 1);
  ordered.forEach((node, i) => out.set(node.id, i / span));
  return { fractions: out, hasTime: false };
}

/** One node's date as milliseconds, or null. Reads `meta` first, then
 *  `detail`; accepts `YYYY-MM-DD`, an optional time, or a bare epoch. */
export function stampOf(node) {
  if (!node) return null;
  for (const field of ["meta", "detail"]) {
    const text = node[field];
    if (typeof text !== "string" || !text) continue;
    const date = text.match(/(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?/);
    if (date) {
      const ms = Date.UTC(Number(date[1]), Number(date[2]) - 1, Number(date[3]),
        Number(date[4] || 0), Number(date[5] || 0));
      if (Number.isFinite(ms)) return ms;
    }
    const epoch = text.match(/\b(1\d{12}|\d{10})\b/);
    if (epoch) {
      const raw = Number(epoch[1]);
      const ms = raw > 1e11 ? raw : raw * 1000;
      if (Number.isFinite(ms)) return ms;
    }
  }
  return null;
}

/* ==========================================================================
 * 4. Ring plans: Gemini's radii, grown outward only when a list outgrows them
 * ========================================================================== */

/** How many names fit on a circle of `radius` with `gap` of air between
 *  neighbours. Adjacent centres are `2R sin(pi/count)` apart, so the largest
 *  count whose chord still clears `gap` is `pi / asin(gap / 2R)`. */
export function ringCapacity(radius, gap = MIN_GAP) {
  const r = Math.max(1, radius);
  const g = Math.max(1, gap);
  const ratio = g / (2 * r);
  if (ratio >= 1) return 2;
  return Math.max(2, Math.floor(Math.PI / Math.asin(ratio)));
}

/** The rings a list of `count` names needs, starting at `baseR` and stepping
 *  outward by `pitch` whenever a ring is full. `[{r, count}]`.
 *
 *  For every list that fits the base ring - which is every list up to about 28
 *  names at R=108 - this returns exactly one ring at Gemini's radius. */
export function ringPlan(count, baseR, { gap = MIN_GAP, pitch = 30 } = {}) {
  const plan = [];
  let left = Math.max(0, Math.floor(count));
  let radius = Math.max(1, baseR);
  let guard = 0;
  while (left > 0 && guard++ < 64) {
    const cap = ringCapacity(radius, gap);
    const take = Math.min(cap, left);
    plan.push({ r: radius, count: take });
    left -= take;
    radius += pitch;
  }
  return plan;
}

/** Where each item of a list sits on a plan of rings: `{item, r, angle, ring,
 *  index, of}`. Each ring's names are evenly spaced, and every extra ring turns
 *  a little further round, so two rings' names never line up into spokes. */
export function placeOnPlan(items, plan, phase = 0) {
  const list = Array.isArray(items) ? items : [];
  const out = [];
  let at = 0;
  for (let ring = 0; ring < plan.length; ring++) {
    const { r, count } = plan[ring];
    const turn = phase + ring * 0.31;
    for (let i = 0; i < count; i++) {
      const angle = (i / count) * Math.PI * 2 + turn;
      out.push({ item: list[at], r, angle, ring, index: i, of: count });
      at += 1;
    }
  }
  return out;
}

/** Where each item of a list sits on its rings: `{item, r, angle, ring, index}`.
 *  Angles are evenly spaced within a ring, with Gemini's own per-ring phase so
 *  two rings' names do not line up into spokes. */
export function placeOnRings(items, baseR, options = {}) {
  const list = Array.isArray(items) ? items : [];
  const plan = ringPlan(list.length, baseR, options);
  return placeOnPlan(list, plan, options.phase || 0);
}

/**
 * Several ring families on one picture, in order, with each family pushed
 * outward if the one before it had to grow.
 *
 * This is what stops a 240-name picture from drawing two families on the same
 * circle: Gemini's own radii never trip the floor (his 32 names fit inside
 * every base), so the faithful geometry is untouched for every graph of his
 * size, and a picture far larger than his stays readable instead of merging
 * two kinds of thing into one ring.
 */
export function ringLadder(stages, { gap = MIN_GAP } = {}) {
  const out = [];
  let floor = 0;
  for (const stage of Array.isArray(stages) ? stages : []) {
    const pitch = stage.pitch || 30;
    const base = Math.max(stage.base, floor);
    const plan = ringPlan((stage.items || []).length, base, { gap, pitch });
    const spots = placeOnPlan(stage.items || [], plan, stage.phase || 0);
    const outer = plan.length ? plan[plan.length - 1].r : base;
    floor = outer + pitch;
    out.push({ plan, spots, outer });
  }
  return out;
}
/** The budget: the first `MAX_COSMOS_NODES` names, in the order given.
 *  `nodes` is never mutated. A caller that caps by rank does so before this. */
export function budgetNodes(nodes, cap = MAX_COSMOS_NODES) {
  const list = Array.isArray(nodes) ? nodes : [];
  const limit = Math.max(0, Math.floor(cap));
  return list.length <= limit ? list.slice() : list.slice(0, limit);
}

/** The budget for links, deduplicated by endpoint pair (a payload may carry
 *  the same pair twice under two kinds). */
export function budgetLinks(links, cap = MAX_COSMOS_LINKS) {
  const list = Array.isArray(links) ? links : [];
  const seen = new Set();
  const out = [];
  for (const link of list) {
    if (!link) continue;
    const key = `${link.source}\u0000${link.target}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(link);
    if (out.length >= cap) break;
  }
  return out;
}

/* ==========================================================================
 * 5. Positions: the eight coordinate systems
 * ========================================================================== */

/** Row layout for clean-tree: each row's x offsets, wrapped into lanes once the
 *  row is wider than `maxWidth`. `[{x, lane}]`, centred on 0.
 *
 *  Gemini divides the row across a fixed span, so 240 leaves would be 0.8 units
 *  apart. Lanes keep the row's 26-unit pitch and stack extra lanes 30 units
 *  lower, which is the same picture at a size a camera can frame. */
export function treeRow(count, { maxWidth = TREE_MAX_WIDTH, gap = TREE_COL_GAP,
                                 lanePitch = TREE_LANE_PITCH } = {}) {
  const n = Math.max(0, Math.floor(count));
  if (!n) return [];
  const perLane = Math.max(1, Math.floor(maxWidth / Math.max(1, gap)) + 1);
  const out = [];
  let at = 0;
  let lane = 0;
  while (at < n) {
    const take = Math.min(perLane, n - at);
    for (let i = 0; i < take; i++) {
      const x = take === 1 ? 0 : (i - (take - 1) / 2) * gap;
      out.push({ x, lane, y: -lane * lanePitch });
      at += 1;
    }
    lane += 1;
  }
  return out;
}

/** The eight coordinate systems, as plain numbers.
 *
 *  Returns `[{id, x, y, z}]` in the SAME order as `nodes`, like the flat
 *  layouts do, so a caller can pair them up by index. `orbitTime` is the
 *  orrery's clock in the Gemini page's own units (it advances by
 *  `dt * 0.45 * warp`); every other look ignores it.
 *
 *  Options: `links` (for the orrery's moon orbits), `wide` (clean-tree's
 *  compact/wide switch), `sortByRing` (the zen ring's sort button).
 */
/**
 * The eight coordinate systems, as plain numbers.
 *
 * Returns `[{id, x, y, z}]` in the SAME order as `nodes`, like the flat
 * layouts do, so a caller can pair them up by index. `orbitTime` is the
 * orrery's clock in the Gemini page's own units (it advances by
 * `dt * 0.45 * warp`); every other look ignores it.
 *
 * Options: `links` (for the orrery's moon orbits), `wide` (clean-tree's
 * compact/wide switch), `sortByRing` (the zen ring's sort button).
 *
 * Gemini's numbers are used verbatim for every picture of his own size (his
 * 32 names fit inside every radius here). Two refinements only ever bite on a
 * picture much larger than his, and both are measured in the test suite:
 * `ringLadder` pushes a ring family outward when the family before it had to
 * grow, and a helix or a tree row grows in columns or lanes instead of
 * stretching a 240-name line past any camera.
 */
export function presetPositions(id, nodes, options = {}) {
  const list = budgetNodes(nodes);
  const positions = new Map();
  if (!list.length) return [];
  const roles = byRole(list);

  // The real graph has exactly one core node. If a picture ever holds more,
  // the extras ride WITH the brains instead of stacking on one point: two names
  // on the same place is unreadable and unclickable. Nothing else in this
  // module has to know about that case.
  const anchor = roles.core[0] || null;
  const brains = roles.core.length > 1
    ? roles.brain.concat(roles.core.slice(1)) : roles.brain;
  const place = (node, x, y, z) => positions.set(node.id, { x, y, z });

  if (id === "planetary-orbit") {
    const t = Number.isFinite(options.orbitTime) ? options.orbitTime : 0;
    // The sun: the one place in this picture with nothing beside it.
    if (anchor) place(anchor, 0, 0, 0);
    const parents = parentOf(list, options.links);
    const groupIds = new Set(roles.group.map((node) => node.id));
    const loose = roles.tool.filter((node) => !groupIds.has(parents.get(node.id)));
    // Four families, each on its own ring, in Gemini's order and at his radii:
    // brains R=38, ability groups R=78, unparented abilities R=98 (his page has
    // none - every tool has a parent there - so this ring is this repo's own,
    // sitting in the gap the page leaves), memories R=128.
    const [brainStage, groupStage, looseStage, beltStage] = ringLadder([
      { items: brains, base: 38, pitch: 20 },
      { items: roles.group, base: 78, pitch: 25 },
      { items: loose, base: 98, pitch: 15 },
      { items: roles.memory, base: 128, pitch: 30 },
    ]);
    // Brains: a two-period vertical wave of 4 units either way.
    for (const at of brainStage.spots) {
      place(at.item, Math.cos(at.angle) * at.r, Math.sin(at.angle * 2) * 4,
        Math.sin(at.angle) * at.r);
    }
    // Ability groups: a one-period wave of 6 units, and the page's own 0.3
    // phase so the planets do not line up with the brains.
    const groupSpot = new Map();
    for (const at of groupStage.spots) {
      const angle = at.angle + 0.3;
      const here = { x: Math.cos(angle) * at.r, y: Math.sin(angle) * 6, z: Math.sin(angle) * at.r };
      groupSpot.set(at.item.id, here);
      place(at.item, here.x, here.y, here.z);
    }
    // Abilities: a local R=19 orbit around their own moving group, each group's
    // moons phase-shifted, so two groups' moons never share a point.
    const moons = new Map();
    for (const node of roles.tool) {
      const parent = parents.get(node.id);
      if (!parent || !groupSpot.has(parent)) continue;
      if (!moons.has(parent)) moons.set(parent, []);
      moons.get(parent).push(node);
    }
    const groupList = roles.group.map((node) => node.id);
    for (const node of roles.tool) {
      const parent = parents.get(node.id);
      if (!parent || !groupSpot.has(parent)) continue;
      const siblings = moons.get(parent) || [node];
      const j = siblings.indexOf(node);
      const i = Math.max(0, groupList.indexOf(parent));
      const angle = (j / Math.max(1, siblings.length)) * Math.PI * 2 + i * 0.7 + t * 1.15;
      const spot = groupSpot.get(parent);
      place(node, spot.x + Math.cos(angle) * 19, spot.y + Math.sin(angle * 2) * 5,
        spot.z + Math.sin(angle) * 19);
    }
    for (const at of looseStage.spots) {
      const angle = at.angle + t * 0.8;
      place(at.item, Math.cos(angle) * at.r, Math.sin(angle) * 6, Math.sin(angle) * at.r);
    }
    // Memories: a three-period wave of 10 units - the asteroid belt.
    for (const at of beltStage.spots) {
      const angle = at.angle + 0.8;
      place(at.item, Math.cos(angle) * at.r, Math.sin(angle * 3) * 10,
        Math.sin(angle) * at.r);
    }

  } else if (id === "neural-arbor") {
    // Three horizontal layers, exactly the page's radii and heights: the soma
    // at the centre, brains R=32 at y=8, ability groups R=58 at y=0, abilities
    // R=84/98 at y=52/62, saved things R=70 at y=-46/-52.
    if (anchor) place(anchor, 0, 2, 0);
    for (const at of placeOnRings(brains, 32, { pitch: 28 })) {
      const angle = at.angle + Math.PI / 4;
      place(at.item, Math.cos(angle) * at.r, 8, Math.sin(angle) * at.r);
    }
    for (const at of placeOnRings(roles.group, 58, { pitch: 28 })) {
      place(at.item, Math.cos(at.angle) * at.r, 0, Math.sin(at.angle) * at.r);
    }
    for (const at of placeOnRings(roles.tool, 84, { pitch: 28 })) {
      const angle = at.angle + 0.15;
      const r = at.r + (at.index % 2) * 14;
      place(at.item, Math.cos(angle) * r, 52 + (at.index % 2) * 10, Math.sin(angle) * r);
    }
    for (const at of placeOnRings(roles.memory, 70, { pitch: 28 })) {
      const angle = at.angle + Math.PI / 6;
      place(at.item, Math.cos(angle) * at.r, -46 - (at.index % 2) * 6,
        Math.sin(angle) * at.r);
    }

  } else if (id === "nebula") {
    // The system half is pushed to an outer rim and the saved half is pulled
    // into four wells - the page's own emphasis, and the reason this look reads
    // as "memory first".
    if (anchor) place(anchor, 0, -65, 0);
    const perWell = [[], [], [], []];
    for (const node of roles.memory) perWell[wellOf(node.group)].push(node);
    perWell.forEach((members, well) => {
      const spot = NEBULA_WELLS[well];
      members.forEach((node, i) => {
        const angle = i * 2.35;
        place(node,
          spot.at[0] + Math.cos(angle) * 18,
          spot.at[1] + (i % 2 === 0 ? 11 : -11),
          spot.at[2] + Math.sin(angle) * 18);
      });
    });
    const rim = brains.concat(roles.group, roles.tool);
    for (const at of placeOnRings(rim, 135, { pitch: 40 })) {
      place(at.item, Math.cos(at.angle) * at.r, -55 + (at.index % 3) * 8,
        Math.sin(at.angle) * at.r);
    }

  } else if (id === "dna-helix") {
    // Two strands, ordered by real time when the graph carries any and by id
    // when it does not (see `timeFractions`). One column holds
    // `HELIX_PER_COLUMN` names per strand at the page's own spacing; a bigger
    // picture is a bank of helices side by side.
    if (anchor) place(anchor, 0, -82, 0);
    const time = timeFractions(list);
    const strandA = roles.memory.slice().sort((a, b) =>
      (time.fractions.get(a.id) - time.fractions.get(b.id))
      || String(a.id).localeCompare(String(b.id)));
    const inA = new Set(strandA.map((node) => node.id));
    const strandB = list
      .filter((node) => (!anchor || node.id !== anchor.id) && !inA.has(node.id))
      .slice()
      .sort((a, b) => (time.fractions.get(a.id) - time.fractions.get(b.id))
        || String(a.id).localeCompare(String(b.id)));
    const columns = Math.max(1, Math.ceil(Math.max(strandA.length, strandB.length)
      / HELIX_PER_COLUMN));
    const helix = (strand, phase) => {
      strand.forEach((node, i) => {
        const column = Math.floor(i / HELIX_PER_COLUMN);
        const local = i % HELIX_PER_COLUMN;
        const count = Math.min(HELIX_PER_COLUMN,
          strand.length - column * HELIX_PER_COLUMN);
        const t = count <= 1 ? 0 : local / (count - 1);
        const y = -80 + t * 160;
        const angle = t * Math.PI * 4 + phase;
        const x = (column - (columns - 1) / 2) * HELIX_COLUMN_GAP;
        place(node, x + Math.cos(angle) * 52, y, Math.sin(angle) * 52);
      });
    };
    helix(strandA, 0);
    helix(strandB, Math.PI);

  } else if (id === "radar-dome") {
    // Three terraced rings over a radar floor at y=-28. Gemini bins by a
    // security band; the bands here are the three kinds of thing the graph
    // really holds (see SENTINEL_RINGS and `ringOf`).
    if (anchor) place(anchor, 0, 28, 0);
    const zones = [[], [], []];
    for (const node of list) {
      if (anchor && node.id === anchor.id) continue;
      zones[ringOf(node.group)].push(node);
    }
    const stages = ringLadder([
      { items: zones[0], base: SENTINEL_RINGS[0].r, pitch: 24 },
      { items: zones[1], base: SENTINEL_RINGS[1].r, pitch: 24 },
      { items: zones[2], base: SENTINEL_RINGS[2].r, pitch: 30 },
    ]);
    stages.forEach((stage, zone) => {
      const info = SENTINEL_RINGS[zone];
      for (const at of stage.spots) {
        const angle = at.angle + zone * 0.45;
        place(at.item, Math.cos(angle) * at.r,
          info.y + (at.index % 2 === 0 ? 5 : -5),
          Math.sin(angle) * at.r);
      }
    });

  } else if (id === "star-map") {
    // Gemini's flat schematic: everything on Y=0, on rings at 34 / 68 / 108.
    // Three families share that one plane, so their rings must not meet: the
    // ladder keeps each family outside the one before it.
    if (anchor) place(anchor, 0, 0, 0);
    const [brainStage, groupStage, outerStage] = ringLadder([
      { items: brains, base: 34, pitch: 34 },
      { items: roles.group, base: 68, pitch: 34 },
      { items: roles.tool.concat(roles.memory), base: 108, pitch: 34 },
    ]);
    for (const at of brainStage.spots) {
      const angle = at.angle + Math.PI / 4;
      place(at.item, Math.cos(angle) * at.r, 0, Math.sin(angle) * at.r);
    }
    for (const at of groupStage.spots) {
      place(at.item, Math.cos(at.angle) * at.r, 0, Math.sin(at.angle) * at.r);
    }
    for (const at of outerStage.spots) {
      const angle = at.angle + 0.12;
      place(at.item, Math.cos(angle) * at.r, 0, Math.sin(angle) * at.r);
    }

  } else if (id === "clean-tree") {
    // Four bands, top to bottom: the core, the brains, the ability groups, and
    // the rest. Gemini's rows are Y = 62 / 24 / -14 / -48 and -64. A row too
    // long for one line wraps into lanes, and a wrapped band pushes the bands
    // under it DOWN instead of growing into them - so Gemini's own heights are
    // exact for every picture of his size, and a 240-name tree is a taller
    // flowchart rather than overlapping rows.
    const spread = options.wide ? 1.42 : 1;
    const leaves = roles.tool.concat(roles.memory);
    const bands = [
      { members: anchor ? [anchor] : [], gap: 44, paired: false, natural: 38 },
      { members: brains, gap: 44, paired: false, natural: 38 },
      { members: roles.group, gap: 40, paired: false, natural: 34 },
      { members: leaves, gap: TREE_COL_GAP, paired: true, natural: 34 },
    ];
    let y = 62;
    for (const band of bands) {
      const slots = treeRow(band.members.length, { gap: Math.round(band.gap * spread) });
      const lanes = slots.length ? Math.max(...slots.map((slot) => slot.lane)) + 1 : 0;
      band.members.forEach((node, i) => {
        const slot = slots[i] || { x: 0, lane: 0, y: 0 };
        // The leaf band keeps Gemini's alternating -48 / -64 pair per lane.
        const offset = band.paired
          ? -slot.lane * (TREE_LANE_PITCH + 14) - (i % 2) * 16
          : slot.y;
        place(node, slot.x, y + offset, 0);
      });
      const height = Math.max(0, lanes - 1) * (TREE_LANE_PITCH + (band.paired ? 14 : 0))
        + (band.paired && lanes > 0 ? 16 : 0);
      // One lane keeps Gemini's own row spacing exactly; a wrapped band needs
      // its lanes' full height plus a gap before the next band starts.
      y -= Math.max(band.natural, height + MIN_GAP);
    }

  } else if (id === "zen-ring") {
    // The core at the centre and every other name on one R=108 halo, spaced at
    // the page's own 21 units (which is what lets his 31 names fit one ring);
    // a picture too big for the halo grows outward at 34 a step.
    if (anchor) place(anchor, 0, 0, 0);
    let ringNodes = list.filter((node) => !anchor || node.id !== anchor.id);
    if (options.sortByRing) {
      ringNodes = ringNodes.slice().sort((a, b) =>
        (ringOf(a.group) - ringOf(b.group))
        || String(a.id).localeCompare(String(b.id)));
    }
    const plan = ringPlan(ringNodes.length, 108, { gap: ZEN_HALO_GAP, pitch: 34 });
    for (const at of placeOnPlan(ringNodes, plan)) {
      place(at.item, Math.cos(at.angle) * at.r, 0, Math.sin(at.angle) * at.r);
    }
  }

  // Any name a branch did not place still gets an honest place rather than a
  // silent pile at the origin.
  const out = [];
  for (const node of list) {
    const spot = positions.get(node.id);
    out.push({ id: node.id, x: spot ? spot.x : 0, y: spot ? spot.y : 0, z: spot ? spot.z : 0 });
  }
  return out;
}

/** The bounding radius of a set of positions about the origin, and the box. */
export function boundsOf(positions) {
  let radius = 0;
  let minY = Infinity;
  let maxY = -Infinity;
  for (const point of Array.isArray(positions) ? positions : []) {
    radius = Math.max(radius, Math.hypot(point.x, point.y, point.z));
    minY = Math.min(minY, point.y);
    maxY = Math.max(maxY, point.y);
  }
  return {
    radius,
    minY: Number.isFinite(minY) ? minY : 0,
    maxY: Number.isFinite(maxY) ? maxY : 0,
  };
}

/* ==========================================================================
 * 6. Guides: the bodies each look puts around the names
 * ========================================================================== */

/**
 * One look's guide bodies as plain data, for the render layer to build and for
 * a test to count. Every shape carries its own colour and opacity, because the
 * palette discipline is half of the look: one dark space, faint guide lines.
 *
 * Shape kinds (all coordinates are scene units):
 *   ring    - a flat ring in the XZ plane at height `y`
 *   halo    - a thin flat ring (the zen halo), same fields as `ring`
 *   ringY   - a vertical ring, upright in the XY plane (the neural soma band)
 *   hex     - a closed hexagonal plate at height `y`
 *   curve   - a quadratic Bezier: `from`, `control`, `to`, `samples`
 *   line    - a straight segment: `from`, `to`
 *   spokes  - `count` rays from the origin to radius `r` at height `y`
 *   cone    - a wireframe cone: `radius`, `height`, `sides`, `at`
 *   coneY   - dropped (kept out of the catalogue on purpose)
 *   dome    - a wireframe half sphere at height `y`
 *   sector  - a pie slice lying flat at height `y`
 *   disk    - the helix's laser disk: `r`, `rim`, `y`
 *   polyline- an open path through `points`
 *   star    - the guide-free marker (never emitted; see `guidesOf`)
 */
export function presetGuides(id, nodes, options = {}) {
  const list = budgetNodes(nodes);
  if (!list.length) return [];
  const positions = options.positions || presetPositions(id, list, options);
  const byId = new Map(positions.map((p) => [p.id, p]));
  const guides = [];
  const roles = byRole(list);

  // A guide band is only drawn when names stand on it: a lens can hide the
  // memory half entirely, and an empty ring around nothing is decoration
  // pretending to be data.
  const ringsUnder = (members) => {
    const radii = new Set();
    for (const node of members) {
      const spot = byId.get(node.id);
      if (spot) radii.add(Math.round(Math.hypot(spot.x, spot.z)));
    }
    return [...radii].filter((r) => r > 0).sort((a, b) => a - b);
  };
  const bandRings = (members, color, opacity) => {
    for (const r of ringsUnder(members)) guides.push({ kind: "ring", r, y: 0, color, opacity });
  };

  if (id === "planetary-orbit") {
    // Three ecliptic rings, R = 38 / 78 / 128 - the orrery's three roads, each
    // drawn only when something is in orbit on it.
    bandRings(roles.brain, "#a855f7", 0.28);
    bandRings(roles.group, "#10b981", 0.25);
    bandRings(roles.memory, "#fbbf24", 0.18);

  } else if (id === "neural-arbor") {
    // The cell body, three hexagonal cortical plates, and the six-arm arbour:
    // one apical trunk, two forked twigs and one basal root per arm.
    guides.push({ kind: "cone", radius: 16, height: 26, sides: 6, at: [0, 2, 0],
      color: "#a855f7", opacity: 0.38, wireframe: true });
    [
      { y: -46, r: 78, color: "#f472b6", opacity: 0.22 },
      { y: 0, r: 58, color: "#a855f7", opacity: 0.26 },
      { y: 52, r: 96, color: "#00f0ff", opacity: 0.28 },
    ].forEach((plate) => guides.push({
      kind: "hex", r: plate.r, y: plate.y, color: plate.color, opacity: plate.opacity,
    }));
    for (let arm = 0; arm < 6; arm++) {
      const angle = (arm * Math.PI) / 3;
      const canopy = [Math.cos(angle) * 86, 52, Math.sin(angle) * 86];
      const mid = [Math.cos(angle) * 26, 24, Math.sin(angle) * 26];
      guides.push({ kind: "curve", from: [0, 2, 0], control: mid, to: canopy,
        samples: 24, color: "#00f0ff", opacity: 0.35 });
      [-0.28, 0.28].forEach((fork) => {
        guides.push({
          kind: "curve", from: mid, control: canopy,
          to: [Math.cos(angle + fork) * 105, 64, Math.sin(angle + fork) * 105],
          samples: 16, color: "#c084fc", opacity: 0.26,
        });
      });
      const rootAngle = angle + Math.PI / 6;
      guides.push({
        kind: "curve", from: [0, -8, 0],
        control: [Math.cos(rootAngle) * 28, -22, Math.sin(rootAngle) * 28],
        to: [Math.cos(rootAngle) * 72, -46, Math.sin(rootAngle) * 72],
        samples: 20, color: "#f472b6", opacity: 0.28,
      });
    }

  } else if (id === "nebula") {
    // Four glowing wells; the 3,200-point cloud that fills them is built by
    // `nebulaCloud` (it is particle data, not a guide body). A well with no
    // saved things in it keeps its cloud and loses its ring.
    const perWell = [[], [], [], []];
    for (const node of roles.memory) perWell[wellOf(node.group)].push(node);
    perWell.forEach((members, well) => {
      if (!members.length) return;
      const spot = NEBULA_WELLS[well];
      guides.push({
        kind: "ring", r: spot.r, y: spot.at[1], at: spot.at.slice(),
        color: spot.color, opacity: 0.22,
      });
    });

  } else if (id === "dna-helix") {
    // Two strands, 36 base-pair rungs, and the laser disk that rides the time
    // axis. The strands run R=52 from y=-82 to y=+82 in one double turn.
    const steps = 72;
    const strandA = [];
    const strandB = [];
    for (let s = 0; s <= steps; s++) {
      const t = s / steps;
      const y = -82 + t * 164;
      const angle = t * Math.PI * 4;
      strandA.push([Math.cos(angle) * 52, y, Math.sin(angle) * 52]);
      strandB.push([Math.cos(angle + Math.PI) * 52, y, Math.sin(angle + Math.PI) * 52]);
      if (s % 2 === 0) {
        guides.push({ kind: "line", from: strandA[s], to: strandB[s],
          color: "#10b981", opacity: 0.25 });
      }
    }
    guides.push({ kind: "polyline", points: strandA, color: "#fbbf24", opacity: 0.7 });
    guides.push({ kind: "polyline", points: strandB, color: "#00f0ff", opacity: 0.7 });
    const columns = Math.max(1, Math.ceil(Math.max(roles.memory.length,
      list.length - roles.memory.length - 1) / HELIX_PER_COLUMN));
    const slice = Number.isFinite(options.timeValue) ? options.timeValue : 1;
    guides.push({
      kind: "disk", r: 62 + (columns - 1) * (HELIX_COLUMN_GAP / 2),
      rim: [61, 62.5], y: -80 + Math.min(1, Math.max(0, slice)) * 160,
      color: "#00f0ff", rimColor: "#00e5a3", columns,
    });

  } else if (id === "radar-dome") {
    // The floor at y=-28: three zone rings, four crosshair rays, the rotating
    // sweep wedge, and the containment dome over it. A zone with no names in it
    // keeps its colour on the floor via the crosshairs only - no empty ring.
    const floor = -28;
    const zones = [[], [], []];
    for (const node of list) {
      if (roles.core.some((core) => core.id === node.id)) continue;
      zones[ringOf(node.group)].push(node);
    }
    zones.forEach((members, zone) => {
      if (!members.length) return;
      for (const r of ringsUnder(members)) {
        guides.push({ kind: "ring", r, y: floor,
          color: SENTINEL_RINGS[zone].color, opacity: 0.55 });
      }
    });
    for (let a = 0; a < 4; a++) {
      const angle = (a * Math.PI) / 4;
      guides.push({
        kind: "line",
        from: [Math.cos(angle) * 122, floor, Math.sin(angle) * 122],
        to: [-Math.cos(angle) * 122, floor, -Math.sin(angle) * 122],
        color: "#0f766e", opacity: 0.35,
      });
    }
    guides.push({ kind: "sector", r: 118, y: floor + 0.3, thetaStart: 0,
      thetaLength: Math.PI / 5, color: "#10b981", opacity: 0.22 });
    guides.push({ kind: "dome", r: 72, y: floor, color: "#f59e0b",
      opacity: 0.1, wireframe: true });

  } else if (id === "star-map") {
    // Gemini's three rings plus its seven sector spokes. The rings are read off
    // the names themselves, so a family that had to grow gets a ring for every
    // ring it really uses and no ring stands over nothing.
    const outer = Math.max(108, Math.max(...positions.map(
      (p) => Math.hypot(p.x, p.z))) + 4);
    bandRings(roles.brain, "#1e293b", 0.75);
    bandRings(roles.group, "#1e293b", 0.75);
    bandRings(roles.tool.concat(roles.memory), "#1e293b", 0.75);
    guides.push({ kind: "spokes", count: 7, r: Math.max(112, outer + 4), y: 0,
      color: "#1e293b", opacity: 0.55 });

  } else if (id === "clean-tree") {
    // One baseline per band, one colour each, as wide as the names standing on
    // it. The heights are read back off the positions, so a wrapped band's line
    // follows its names instead of guessing Gemini's row.
    const bands = [
      { members: roles.core, color: "#10b981" },
      { members: roles.brain, color: "#a855f7" },
      { members: roles.group, color: "#06b6d4" },
      { members: roles.tool.concat(roles.memory), color: "#fbbf24" },
    ];
    bands.forEach((band) => {
      let half = 0;
      let y = null;
      for (const node of band.members) {
        const spot = byId.get(node.id);
        if (!spot) continue;
        half = Math.max(half, Math.abs(spot.x));
        y = y === null ? spot.y : Math.max(y, spot.y);
      }
      // A band with no names in it gets no baseline: a line under nothing is
      // decoration pretending to be a row.
      if (y === null) return;
      const width = Math.max(28, half + 22);
      guides.push({ kind: "line", from: [-width, y, -2], to: [width, y, -2],
        color: band.color, opacity: 0.22 });
    });

  } else if (id === "zen-ring") {
    // One halo, plus a thin outer ring for each extra ring the picture needed.
    const outer = Math.max(108, Math.max(...positions.map(
      (p) => Math.hypot(p.x, p.z))));
    let r = 108;
    guides.push({ kind: "halo", r: 108, y: 0, color: "#0d9488", opacity: 0.45 });
    while (r + 34 <= outer + 0.5) {
      r += 34;
      guides.push({ kind: "halo", r, y: 0, color: "#0d9488", opacity: 0.18 });
    }
  }

  return guides;
}

/** The links a look draws, as plain segments or curves.
 *
 *  Three shapes, exactly the page's three branches: a curved axon for the
 *  neural look, an inward chord through the halo for the zen ring, and a
 *  straight synapse everywhere else. Capped at `MAX_COSMOS_LINKS`. */
export function presetLinks(id, nodes, links, options = {}) {
  const list = budgetNodes(nodes);
  const positions = options.positions || presetPositions(id, list, options);
  const byId = new Map(positions.map((p) => [p.id, p]));
  const out = [];
  const cap = options.chords === false && id === "zen-ring" ? 0 : MAX_COSMOS_LINKS;
  for (const link of budgetLinks(links)) {
    const a = byId.get(link.source);
    const b = byId.get(link.target);
    if (!a || !b) continue;
    if (id === "neural-arbor") {
      // The page's organic axon: the midpoint pulled in to 0.75 and lifted 12.
      const control = {
        x: (a.x + b.x) / 2 * 0.75,
        y: (a.y + b.y) / 2 * 0.75 + 12,
        z: (a.z + b.z) / 2 * 0.75,
      };
      out.push({ a, b, control, samples: 20, color: "#c084fc", opacity: 0.36 });
    } else if (id === "zen-ring") {
      // The inward chord: midpoint pulled in to 0.35, so it bows through the
      // middle of the halo instead of hugging the rim.
      const control = {
        x: (a.x + b.x) / 2 * 0.35,
        y: (a.y + b.y) / 2 * 0.35,
        z: (a.z + b.z) / 2 * 0.35,
      };
      out.push({ a, b, control, samples: 18, color: "#2dd4bf", opacity: 0.24 });
    } else {
      const color = id === "radar-dome" ? "#10b981" : "#00f0ff";
      const opacity = id === "nebula" ? 0.12
        : (id === "star-map" || id === "clean-tree" ? 0.28 : 0.22);
      out.push({ a, b, control: null, samples: 2, color, opacity });
    }
    if (out.length >= cap) break;
  }
  return out;
}

/* ==========================================================================
 * 7. Particles: the starfield and the nebula clouds, seeded and deterministic
 * ========================================================================== */

/** A 32-bit seeded generator (mulberry32). Used so the sky is identical on
 *  every load: the page's own `Math.random` sky is different every time, which
 *  makes a screenshot comparison impossible and the picture subtly unstable. */
export function mulberry32(seed) {
  let a = (Number(seed) || 0) >>> 0;
  return function next() {
    a = (a + 0x6D2B79F5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** The background starfield: 1,800 points on a shell 350..900 units out, two
 *  in five cyan and three in five slate, exactly the page's mix. Returns
 *  `{positions, colors}` as `Float32Array`s ready for a BufferGeometry. */
export function starField(count = STAR_COUNT, seed = 20261027) {
  const n = Math.max(1, Math.floor(count));
  const random = mulberry32(seed);
  const positions = new Float32Array(n * 3);
  const colors = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) {
    const radius = 350 + random() * 550;
    const theta = random() * Math.PI * 2;
    const phi = Math.acos(random() * 2 - 1);
    positions[i * 3] = radius * Math.sin(phi) * Math.cos(theta);
    positions[i * 3 + 1] = radius * Math.sin(phi) * Math.sin(theta);
    positions[i * 3 + 2] = radius * Math.cos(phi);
    const cyan = random() > 0.55;
    colors[i * 3] = cyan ? 0 : 0.25;
    colors[i * 3 + 1] = cyan ? 0.85 : 0.45;
    colors[i * 3 + 2] = 1;
  }
  return { positions, colors };
}

/** The nebula cloud: `count` points split evenly across the four wells, with
 *  the page's `pow(u, 0.55) * r * 1.35` radial falloff and its 0.75 vertical
 *  flattening. Returns `{positions, colors}`. */
export function nebulaCloud(count = NEBULA_POINTS, seed = 20261028,
                            wells = NEBULA_WELLS) {
  const n = Math.max(1, Math.floor(count));
  const random = mulberry32(seed);
  const positions = new Float32Array(n * 3);
  const colors = new Float32Array(n * 3);
  const palette = wells.map((well) => hexToRgb(well.color));
  for (let i = 0; i < n; i++) {
    const well = i % wells.length;
    const at = wells[well].at;
    const tone = palette[well];
    const rad = Math.pow(random(), 0.55) * wells[well].r * 1.35;
    const theta = random() * Math.PI * 2;
    const phi = Math.acos(2 * random() - 1);
    positions[i * 3] = at[0] + rad * Math.sin(phi) * Math.cos(theta);
    positions[i * 3 + 1] = at[1] + rad * Math.sin(phi) * Math.sin(theta) * 0.75;
    positions[i * 3 + 2] = at[2] + rad * Math.cos(phi);
    colors[i * 3] = tone.r;
    colors[i * 3 + 1] = tone.g;
    colors[i * 3 + 2] = tone.b;
  }
  return { positions, colors };
}

/** `#rrggbb` (or `#rgb`) to `{r, g, b}` in 0..1, the shape three.js wants. */
export function hexToRgb(hex) {
  let text = String(hex || "").trim().replace(/^#/, "");
  if (text.length === 3) text = text.split("").map((c) => c + c).join("");
  const value = Number.parseInt(text, 16);
  if (!Number.isFinite(value) || text.length !== 6) return { r: 1, g: 1, b: 1 };
  return {
    r: ((value >> 16) & 255) / 255,
    g: ((value >> 8) & 255) / 255,
    b: (value & 255) / 255,
  };
}

/** A `#rrggbb` string as the 0xRRGGBB number three.js colours take. */
export function hexToInt(hex) {
  const text = String(hex || "").trim().replace(/^#/, "");
  const value = Number.parseInt(text.length === 3
    ? text.split("").map((c) => c + c).join("") : text, 16);
  return Number.isFinite(value) ? value : 0xffffff;
}

/* ==========================================================================
 * 8. The per-look small controls (Gemini's two buttons, in plain words)
 * ========================================================================== */

/**
 * Each look's two small controls. Gemini gives every preset a pair of buttons;
 * these are the same behaviours in this repository's words.
 *
 * `key` is what `engine.action(key)` understands, `label` is the button's
 * words, and `toggle` says whether the button has an on/off state (so the page
 * can set `aria-pressed`) or is a one-shot.
 */
export const PRESET_ACTIONS = Object.freeze({
  "planetary-orbit": Object.freeze([
    Object.freeze({ key: "warp", label: "Orbit faster", toggle: true }),
    Object.freeze({ key: "follow", label: "Follow a planet", toggle: true }),
  ]),
  "neural-arbor": Object.freeze([
    Object.freeze({ key: "wave", label: "Send a pulse", toggle: false }),
    Object.freeze({ key: "layer", label: "Highlight one layer", toggle: true }),
  ]),
  nebula: Object.freeze([
    Object.freeze({ key: "well", label: "Look at a cloud", toggle: false }),
    Object.freeze({ key: "shimmer", label: "Make it shimmer", toggle: true }),
  ]),
  "dna-helix": Object.freeze([
    Object.freeze({ key: "sweepBack", label: "Sweep to the start", toggle: false }),
    Object.freeze({ key: "sweepForward", label: "Sweep to now", toggle: false }),
  ]),
  "radar-dome": Object.freeze([
    Object.freeze({ key: "alert", label: "Flash the beam", toggle: true }),
    Object.freeze({ key: "lockdown", label: "Dome on or off", toggle: true }),
  ]),
  "star-map": Object.freeze([
    Object.freeze({ key: "topdown", label: "Look straight down", toggle: false }),
    Object.freeze({ key: "rings", label: "Ring guides", toggle: true }),
  ]),
  "clean-tree": Object.freeze([
    Object.freeze({ key: "wide", label: "Wide or compact", toggle: true }),
    Object.freeze({ key: "cascade", label: "Trace down the tree", toggle: false }),
  ]),
  "zen-ring": Object.freeze([
    Object.freeze({ key: "sort", label: "Sort the ring", toggle: true }),
    Object.freeze({ key: "chords", label: "Chord lines", toggle: true }),
  ]),
});

/** One look's controls, or an empty list. */
export function actionsFor(id) {
  return PRESET_ACTIONS[id] ? PRESET_ACTIONS[id].slice() : [];
}

/* ==========================================================================
 * 9. The render layer - three.js, loaded only when the page asks for it
 * ========================================================================== */

/** The one URL three.js is served from. Same origin, so the page's closed
 *  whitelist serves it; the vendoring PR owns that file and its key. */
const THREE_SCRIPT = "/three.min.js";

let loadingThree = null;

/** Can this browser draw WebGL at all? Asked before three.js is fetched, so a
 *  machine that cannot draw never downloads 600 KB to find out. */
export function webglSupported() {
  if (typeof document === "undefined") return false;
  try {
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl") || canvas.getContext("experimental-webgl"));
  } catch (error) {
    return false;
  }
}

/** Fetch three.js from this origin once, and resolve the global it publishes.
 *  Resolves `null` (never rejects) when it is missing: the caller's fallback is
 *  the shipped 2D picture, so a 404 here is a quiet downgrade, not an error.
 *
 *  The page itself also carries a `<script src="/three.min.js" defer>` tag, so
 *  the closed whitelist can see what it loads. When that tag is still in
 *  flight, this waits for it instead of appending a second copy of 600 KB. */
export function loadThree(timeoutMs = 8000) {
  if (typeof window === "undefined" || typeof document === "undefined") {
    return Promise.resolve(null);
  }
  const ready = () => (window.THREE && window.THREE.WebGLRenderer ? window.THREE : null);
  const already = ready();
  if (already) return Promise.resolve(already);
  if (loadingThree) return loadingThree;
  const pending = document.querySelector('script[src$="/three.min.js"]');
  if (pending) {
    loadingThree = new Promise((resolve) => {
      let settled = false;
      const finish = (value) => {
        if (settled) return;
        settled = true;
        if (!value) loadingThree = null;
        resolve(value || null);
      };
      pending.addEventListener("load", () => finish(ready()));
      pending.addEventListener("error", () => finish(null));
      setTimeout(() => finish(ready()), Math.max(1000, timeoutMs));
    });
    return loadingThree;
  }
  loadingThree = new Promise((resolve) => {
    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      // A miss is not remembered: the file may arrive later (the vendoring PR
      // merging, a server restarted), and the next call should try again.
      if (!value) loadingThree = null;
      resolve(value || null);
    };
    try {
      const script = document.createElement("script");
      script.src = THREE_SCRIPT;
      script.async = true;
      script.onload = () => finish(ready());
      script.onerror = () => finish(null);
      document.head.appendChild(script);
      setTimeout(() => finish(ready()), Math.max(1000, timeoutMs));
    } catch (error) {
      finish(null);
    }
  });
  return loadingThree;
}

/** The role colours used when the page does not hand its own palette in. */
export const ROLE_COLORS = Object.freeze({
  core: "#00e5a3",
  brain: "#38bdf8",
  group: "#10b981",
  tool: "#00f0ff",
  memory: "#fbbf24",
});

/**
 * Build the engine: one scene, one camera, one renderer, and the eight looks.
 *
 * Resolves an engine object, or `null` when this browser cannot draw WebGL or
 * three.js is not served beside the page. It NEVER rejects: the page's fallback
 * (the 2D picture it already ships) is always the answer to a failure here.
 *
 * Options:
 *   canvas    - the canvas element to draw into (required)
 *   colorFor  - `(group) => "#rrggbb"`, the page's own palette (optional)
 *   onFail    - called once when the GPU context is lost, so the page can drop
 *               back to its 2D picture instead of showing a frozen frame
 */
export async function createEngine(options = {}) {
  const canvas = options.canvas;
  if (!canvas || !webglSupported()) return null;
  const THREE = await loadThree();
  if (!THREE) return null;

  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: true,
      alpha: false,
      powerPreference: "high-performance",
    });
  } catch (error) {
    return null;
  }

  renderer.setPixelRatio(1);
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = TONE_EXPOSURE;

  const colorFor = typeof options.colorFor === "function"
    ? options.colorFor : (group) => ROLE_COLORS[roleOf(group)] || ROLE_COLORS.memory;
  const scene = new THREE.Scene();
  scene.fog = new THREE.FogExp2(hexToInt(COSMOS_PRESETS[COSMOS_DEFAULT_LOOK].bg), FOG_DENSITY);

  const camera = new THREE.PerspectiveCamera(CAMERA_FOV, 1.6, CAMERA_NEAR, CAMERA_FAR);
  const target = new THREE.Vector3(0, 0, 0);
  camera.position.set(0, 150, 230);
  camera.lookAt(target);

  // The scene's own furniture, built once and reused by every look.
  const guideRoot = new THREE.Group();
  scene.add(guideRoot);
  const nodeRoot = new THREE.Group();
  scene.add(nodeRoot);
  const linkRoot = new THREE.Group();
  scene.add(linkRoot);

  const state = {
    preset: COSMOS_DEFAULT_LOOK,
    nodes: [],
    links: [],
    groups: new Map(),
    meshes: new Map(),
    linkObjects: [],
    guides: [],
    stalks: [],
    orbits: null,
    cloud: null,
    stars: null,
    core: null,
    disk: null,
    sweep: null,
    dome: null,
    swatch: null,
    width: 2,
    height: 2,
    aspect: 1.6,
    frameDistance: 0,
    spinning: true,
    warp: 1,
    followId: null,
    timeValue: 1,
    layer: 0,
    alert: false,
    lockdown: false,
    ringSort: false,
    chords: true,
    wide: false,
    rings: true,
    shimmer: true,
    orbitClock: 0,
    lastData: 0,
    camTo: null,
    targetTo: null,
    flySpeed: 0.06,
    pulses: [],
    lastPulse: 0,
    lastTime: 0,
    disposed: false,
    lost: false,
    draws: 0,
    // How many times the link plan has been rebuilt (2026-10-28). Reported by
    // `info()` so a test can prove the cache really is a cache: a steady frame
    // must not move this number, and a changed graph or look must move it once.
    plans: 0,
  };

  /* ---- scene furniture ------------------------------------------------- */

  function buildStars() {
    const { positions, colors } = starField();
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    const material = new THREE.PointsMaterial({
      size: 1.8, vertexColors: true, transparent: true, opacity: 0.6,
      sizeAttenuation: true, depthWrite: false,
    });
    state.stars = new THREE.Points(geometry, material);
    state.stars.frustumCulled = false;
    scene.add(state.stars);
  }

  function buildCore() {
    // Gemini's gyroscopic core: a wireframe shell, a bright nucleus, three
    // rotating rings. Hidden for the neural and memory looks, as the page does
    // (its soma / clouds take the centre there).
    const group = new THREE.Group();
    const shell = new THREE.Mesh(
      new THREE.SphereGeometry(10, 32, 32),
      new THREE.MeshBasicMaterial({
        color: 0x00e5a3, wireframe: true, transparent: true, opacity: 0.8,
      }));
    group.add(shell);
    group.add(new THREE.Mesh(
      new THREE.SphereGeometry(6, 16, 16),
      new THREE.MeshBasicMaterial({ color: 0x00f0ff, transparent: true, opacity: 0.95 })));
    state.swatch = [];
    [
      { radius: 14, color: 0x00f0ff, speed: [0.015, 0.02, 0.005] },
      { radius: 17, color: 0x00e5a3, speed: [-0.01, 0.015, 0.02] },
      { radius: 20, color: 0x38bdf8, speed: [0.02, -0.01, 0.015] },
    ].forEach((ring) => {
      const mesh = new THREE.Mesh(
        new THREE.RingGeometry(ring.radius - 0.35, ring.radius, 64),
        new THREE.MeshBasicMaterial({
          color: ring.color, side: THREE.DoubleSide, transparent: true, opacity: 0.75,
        }));
      mesh.rotation.x = ring.radius * 0.11;
      mesh.rotation.y = ring.radius * 0.07;
      mesh.userData.speed = ring.speed;
      state.swatch.push(mesh);
      group.add(mesh);
    });
    state.core = group;
    scene.add(group);
  }

  buildStars();
  buildCore();

  /* ---- graphs ---------------------------------------------------------- */

  function disposeObject(object) {
    if (!object) return;
    object.traverse((child) => {
      if (child.geometry) child.geometry.dispose();
      if (child.material) {
        if (Array.isArray(child.material)) child.material.forEach((m) => m.dispose());
        else child.material.dispose();
      }
    });
  }

  function clearGroup(root, list) {
    for (const child of list) {
      root.remove(child);
      disposeObject(child);
    }
    list.length = 0;
  }

  function nodeRadius(node) {
    const weight = typeof node.weight === "number" ? node.weight : 1;
    return Math.max(3, Math.min(9, 3 + weight * 1.1));
  }

  function buildNodeObject(node) {
    const role = roleOf(node.group);
    const radius = nodeRadius(node);
    const colour = hexToInt(colorFor(node.group) || ROLE_COLORS[role] || ROLE_COLORS.memory);
    const group = new THREE.Group();
    let mesh = null;
    if (role === "brain") {
      mesh = new THREE.Mesh(
        new THREE.IcosahedronGeometry(radius, 0),
        new THREE.MeshBasicMaterial({
          color: colour, wireframe: true, transparent: true, opacity: 0.88,
        }));
      mesh.add(new THREE.Mesh(
        new THREE.SphereGeometry(radius * 0.45, 12, 12),
        new THREE.MeshBasicMaterial({ color: 0xffffff })));
      mesh.add(new THREE.Mesh(
        new THREE.RingGeometry(radius * 1.45, radius * 1.65, 32),
        new THREE.MeshBasicMaterial({
          color: colour, side: THREE.DoubleSide, transparent: true, opacity: 0.6,
        })));
    } else if (role === "group") {
      mesh = new THREE.Mesh(
        new THREE.TorusGeometry(radius * 0.8, 0.45, 16, 48),
        new THREE.MeshBasicMaterial({ color: colour, transparent: true, opacity: 0.9 }));
    } else if (role === "memory") {
      mesh = new THREE.Mesh(
        new THREE.OctahedronGeometry(radius, 0),
        new THREE.MeshBasicMaterial({ color: colour, transparent: true, opacity: 0.88 }));
    } else if (role === "core") {
      mesh = null;   // the core body is the gyroscopic reactor, built once
    } else {
      mesh = new THREE.Mesh(
        new THREE.SphereGeometry(radius, 16, 16),
        new THREE.MeshBasicMaterial({ color: colour, transparent: true, opacity: 0.92 }));
      mesh.add(new THREE.Mesh(
        new THREE.SphereGeometry(radius * 1.7, 12, 12),
        new THREE.MeshBasicMaterial({ color: colour, transparent: true, opacity: 0.22 })));
    }
    if (mesh) {
      group.add(mesh);
      state.meshes.set(node.id, mesh);
    }
    group.userData = { id: node.id, role, radius, colour };
    return group;
  }

  function setGraph(nodes, links) {
    state.nodes = budgetNodes(nodes);
    state.links = budgetLinks(links);
    for (const group of state.groups.values()) {
      nodeRoot.remove(group);
      disposeObject(group);
    }
    state.groups.clear();
    state.meshes.clear();
    for (const node of state.nodes) {
      const object = buildNodeObject(node);
      state.groups.set(node.id, object);
      nodeRoot.add(object);
    }
    rebuildScene();
  }

  /* ---- guides ---------------------------------------------------------- */

  function buildGuide(shape) {
    const colour = hexToInt(shape.color);
    const material = (extra = {}) => new THREE.MeshBasicMaterial({
      color: colour, side: THREE.DoubleSide, transparent: true,
      opacity: shape.opacity || 0.3, depthWrite: false, ...extra,
    });
    const lineMaterial = () => new THREE.LineBasicMaterial({
      color: colour, transparent: true, opacity: shape.opacity || 0.3, depthWrite: false,
    });
    const pointsGeometry = (points) => new THREE.BufferGeometry().setFromPoints(
      points.map((p) => new THREE.Vector3(p[0], p[1], p[2])));
    const circle = (radius, steps = 96) => {
      const points = [];
      for (let i = 0; i <= steps; i++) {
        const angle = (i / steps) * Math.PI * 2;
        points.push([Math.cos(angle) * radius, 0, Math.sin(angle) * radius]);
      }
      return points;
    };

    if (shape.kind === "ring" || shape.kind === "halo") {
      const at = shape.at || [0, shape.y || 0, 0];
      const mesh = new THREE.Mesh(
        new THREE.RingGeometry(Math.max(0.1, shape.r - 0.35), shape.r, 128), material());
      mesh.rotation.x = Math.PI / 2;
      mesh.position.set(at[0] || 0, shape.y || 0, at[2] || 0);
      return mesh;
    }
    if (shape.kind === "hex") {
      const points = [];
      for (let i = 0; i <= 6; i++) {
        const angle = (i * Math.PI) / 3;
        points.push([Math.cos(angle) * shape.r, shape.y, Math.sin(angle) * shape.r]);
      }
      return new THREE.Line(pointsGeometry(points), lineMaterial());
    }
    if (shape.kind === "curve") {
      const curve = new THREE.QuadraticBezierCurve3(
        new THREE.Vector3(...shape.from),
        new THREE.Vector3(...shape.control),
        new THREE.Vector3(...shape.to));
      return new THREE.Line(
        new THREE.BufferGeometry().setFromPoints(curve.getPoints(shape.samples || 16)),
        lineMaterial());
    }
    if (shape.kind === "line") {
      return new THREE.Line(pointsGeometry([shape.from, shape.to]), lineMaterial());
    }
    if (shape.kind === "polyline") {
      return new THREE.Line(pointsGeometry(shape.points), lineMaterial());
    }
    if (shape.kind === "spokes") {
      const group = new THREE.Group();
      for (let i = 0; i < shape.count; i++) {
        const angle = (i / shape.count) * Math.PI * 2;
        group.add(new THREE.Line(pointsGeometry([
          [0, shape.y || 0, 0],
          [Math.cos(angle) * shape.r, shape.y || 0, Math.sin(angle) * shape.r],
        ]), lineMaterial()));
      }
      return group;
    }
    if (shape.kind === "cone") {
      const mesh = new THREE.Mesh(
        new THREE.ConeGeometry(shape.radius, shape.height, shape.sides),
        material({ wireframe: Boolean(shape.wireframe) }));
      mesh.position.set(shape.at[0], shape.at[1], shape.at[2]);
      return mesh;
    }
    if (shape.kind === "dome") {
      const mesh = new THREE.Mesh(
        new THREE.SphereGeometry(shape.r, 28, 14, 0, Math.PI * 2, 0, Math.PI / 2),
        material({ wireframe: Boolean(shape.wireframe) }));
      mesh.position.y = shape.y || 0;
      return mesh;
    }
    if (shape.kind === "sector") {
      const mesh = new THREE.Mesh(
        new THREE.CircleGeometry(shape.r, 32, shape.thetaStart || 0,
          shape.thetaLength || Math.PI / 5), material());
      mesh.position.y = shape.y || 0;
      mesh.rotation.x = Math.PI / 2;
      return mesh;
    }
    if (shape.kind === "disk") {
      const group = new THREE.Group();
      const disk = new THREE.Mesh(
        new THREE.CircleGeometry(shape.r, 64), material({ opacity: 0.14 }));
      disk.rotation.x = Math.PI / 2;
      group.add(disk);
      const rim = new THREE.Mesh(
        new THREE.RingGeometry(shape.rim[0], shape.rim[1], 64),
        new THREE.MeshBasicMaterial({
          color: hexToInt(shape.rimColor), side: THREE.DoubleSide,
          transparent: true, opacity: 0.85,
        }));
      rim.rotation.x = Math.PI / 2;
      group.add(rim);
      group.position.y = shape.y || 0;
      state.disk = { group, shape };
      return group;
    }
    return null;
  }

  function rebuildGuides() {
    for (const child of state.guides) {
      guideRoot.remove(child);
      disposeObject(child);
    }
    state.guides = [];
    for (const stalk of state.stalks) {
      guideRoot.remove(stalk);
      disposeObject(stalk);
    }
    state.stalks = [];
    state.disk = null;
    state.sweep = null;
    state.dome = null;
    if (state.cloud) {
      scene.remove(state.cloud);
      disposeObject(state.cloud);
      state.cloud = null;
    }
    if (state.core) {
      // The page hides the reactor for the two looks whose own body takes the
      // centre: the neural soma and the memory clouds.
      state.core.visible = ["planetary-orbit", "radar-dome", "star-map", "zen-ring"]
        .includes(state.preset);
    }

    const guides = presetGuides(state.preset, state.nodes, {
      links: state.links,
      wide: state.wide,
      timeValue: state.timeValue,
      sortByRing: state.ringSort,
    });
    if (!state.rings && state.preset === "star-map") {
      // The "Ring guides" control: the star map's rings and spokes are the only
      // guides it has, so switching them off leaves a bare plane - the page's
      // own Toggle Sector Rings.
      for (const shape of guides) {
        if (shape.kind === "ring" || shape.kind === "spokes") continue;
        const object = buildGuide(shape);
        if (object) { guideRoot.add(object); state.guides.push(object); }
      }
    } else {
      for (const shape of guides) {
        const object = buildGuide(shape);
        if (!object) continue;
        guideRoot.add(object);
        state.guides.push(object);
        if (shape.kind === "sector") state.sweep = object;
        if (shape.kind === "dome") state.dome = object;
        if (shape.kind === "disk") state.disk = { group: object, shape };
      }
    }

    if (state.preset === "nebula"
        && state.nodes.some((node) => roleOf(node.group) === "memory")) {
      // The clouds are the saved half's sky. A lens that shows no saved things
      // gets no clouds: four glowing wells with nothing in them would be
      // decoration pretending to be data.
      const { positions: cloudPositions, colors } = nebulaCloud();
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute("position", new THREE.BufferAttribute(cloudPositions, 3));
      geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
      const material = new THREE.PointsMaterial({
        size: 2.6, vertexColors: true, transparent: true, opacity: 0.42,
        sizeAttenuation: true, depthWrite: false,
      });
      state.cloud = new THREE.Points(geometry, material);
      state.cloud.frustumCulled = false;
      guideRoot.add(state.cloud);
    }

    if (state.preset === "radar-dome") buildStalks();
  }

  function buildStalks() {
    // One vertical stalk per name, from the name down to the radar floor at
    // y=-28, coloured by zone - the page's "elevation stalks".
    if (state.preset !== "radar-dome") return;
    const floor = -28;
    for (const node of state.nodes) {
      const point = positionOf(node.id);
      if (!point) continue;
      const zone = ringOf(node.group);
      const colour = hexToInt(SENTINEL_RINGS[zone].color);
      const geometry = new THREE.BufferGeometry().setFromPoints([
        new THREE.Vector3(point.x, point.y, point.z),
        new THREE.Vector3(point.x, floor, point.z),
      ]);
      const line = new THREE.Line(geometry, new THREE.LineBasicMaterial({
        color: colour, transparent: true, opacity: 0.35, depthWrite: false,
      }));
      guideRoot.add(line);
      state.stalks.push(line);
    }
  }

  /* ---- positions and links -------------------------------------------- */

  // THE PICTURE'S OWN CACHE (2026-10-28, the owner's guardrail on this wave).
  //
  // `applyPositions` runs on EVERY frame of the Planetary Orrery - that look
  // really orbits - and it used to rebuild the whole picture's bookkeeping on
  // the way: a new array of position objects, two new Maps, and (through
  // `presetLinks`) a new 360-entry link array with a control object each. About
  // 1,500 objects a frame, every one of them the same shape as the one the last
  // frame had just thrown away, all of it handed to the garbage collector while
  // the GPU was already busy.
  //
  // So the SHAPE is cached and only the NUMBERS in it change:
  //   - `positions` and `positionById` are reused, and a moved planet writes
  //     three numbers into an object that already exists;
  //   - `linkPlan` holds the link set BY ID (never by object reference, which
  //     would go stale the moment a position object is replaced);
  //   - every link keeps its own Float32Array and its own BufferAttribute, and
  //     a frame writes into that array and sets `posAttr.needsUpdate = true`,
  //     so the GPU re-uploads the vertices instead of the page building a new
  //     geometry, material and Line.
  // `shapeDirty` is raised only when the SET changes: a new graph, another
  // look, or a control that changes which links exist. A frame that merely
  // moved leaves it down.
  let positions = [];
  let positionById = new Map();
  let linkPlan = [];
  let shapeDirty = true;

  function positionOf(id) {
    return positionById.get(id) || null;
  }

  /** Lay the names out again. `moved` means time advanced and nothing else did,
   *  so the cached shape still describes this frame and only the numbers move. */
  function applyPositions(moved) {
    const fresh = presetPositions(state.preset, state.nodes, {
      links: state.links,
      orbitTime: state.orbitClock,
      wide: state.wide,
      sortByRing: state.ringSort,
    });
    if (!moved) shapeDirty = true;
    let reuse = !shapeDirty && positions.length === fresh.length;
    if (reuse) {
      // The ids must still line up: a graph that changed under a look would
      // otherwise write one name's numbers into another name's object.
      for (let i = 0; i < fresh.length; i++) {
        if (positions[i].id !== fresh[i].id) { reuse = false; break; }
      }
    }
    if (reuse) {
      for (let i = 0; i < fresh.length; i++) {
        const point = positions[i];
        point.x = fresh[i].x;
        point.y = fresh[i].y;
        point.z = fresh[i].z;
      }
    } else {
      positions = fresh.map((p) => ({ id: p.id, x: p.x, y: p.y, z: p.z }));
      positionById = new Map(positions.map((p) => [p.id, p]));
      shapeDirty = true;
    }
    for (const [id, group] of state.groups) {
      const point = positionById.get(id);
      if (!point) continue;
      group.position.set(point.x, point.y, point.z);
    }
    updateLinks();
  }

  /** Rebuild the link set, its Line objects and their buffers. Runs only when
   *  the shape changed; a frame that only moved calls `updateLinks`, which
   *  finds this plan already in place. */
  function rebuildLinkPlan() {
    state.plans += 1;
    const wanted = presetLinks(state.preset, state.nodes, state.links, {
      positions, chords: state.chords,
    });
    linkPlan = wanted.map((link) => ({
      a: link.a.id,
      b: link.b.id,
      control: link.control,
      samples: link.samples,
      color: link.color,
      opacity: link.opacity,
    }));
    const sameShape = state.linkObjects.length === linkPlan.length
      && state.linkObjects.every((line, index) =>
        line.userData.samples === linkPlan[index].samples);
    if (!sameShape) {
      for (const line of state.linkObjects) {
        linkRoot.remove(line);
        disposeObject(line);
      }
      state.linkObjects = [];
      for (const plan of linkPlan) {
        const geometry = new THREE.BufferGeometry();
        geometry.setAttribute("position",
          new THREE.BufferAttribute(new Float32Array(plan.samples * 3), 3));
        const line = new THREE.Line(geometry, new THREE.LineBasicMaterial({
          color: hexToInt(plan.color), transparent: true, opacity: plan.opacity,
          depthWrite: false,
        }));
        line.userData.samples = plan.samples;
        line.userData.link = plan;
        // Kept, not looked up again every frame: this is the attribute a frame
        // marks dirty so the GPU re-uploads what was written into its array.
        line.userData.posAttr = geometry.getAttribute("position");
        linkRoot.add(line);
        state.linkObjects.push(line);
      }
    } else {
      state.linkObjects.forEach((line, index) => { line.userData.link = linkPlan[index]; });
    }
    // A look's line colour and its "chords hidden" rule are decided here, once,
    // rather than thirty times a second.
    const hidden = state.preset === "zen-ring" && !state.chords;
    state.linkObjects.forEach((line, index) => {
      const plan = linkPlan[index];
      if (!plan) return;
      line.material.color.setHex(hexToInt(plan.color));
      line.material.opacity = hidden ? 0 : plan.opacity;
      line.visible = !hidden;
    });
  }

  function updateLinks() {
    if (shapeDirty) {
      rebuildLinkPlan();
      shapeDirty = false;
    }
    for (let index = 0; index < linkPlan.length; index++) {
      const plan = linkPlan[index];
      const line = state.linkObjects[index];
      if (!plan || !line) continue;
      const source = positionById.get(plan.a);
      const sink = positionById.get(plan.b);
      if (!source || !sink) continue;
      const posAttr = line.userData.posAttr;
      const array = posAttr.array;
      if (plan.samples <= 2) {
        array[0] = source.x; array[1] = source.y; array[2] = source.z;
        array[3] = sink.x; array[4] = sink.y; array[5] = sink.z;
      } else {
        const ax = source.x; const ay = source.y; const az = source.z;
        const bx = sink.x; const by = sink.y; const bz = sink.z;
        const control = plan.control || { x: (ax + bx) / 2, y: (ay + by) / 2, z: (az + bz) / 2 };
        for (let i = 0; i < plan.samples; i++) {
          const t = i / (plan.samples - 1);
          const u = 1 - t;
          array[i * 3] = u * u * ax + 2 * u * t * control.x + t * t * bx;
          array[i * 3 + 1] = u * u * ay + 2 * u * t * control.y + t * t * by;
          array[i * 3 + 2] = u * u * az + 2 * u * t * control.z + t * t * bz;
        }
      }
      posAttr.needsUpdate = true;
    }
  }

  /* ---- morphology, camera and colour ---------------------------------- */

  function applyMorphology() {
    state.nodes.forEach((node) => {
      const group = state.groups.get(node.id);
      const mesh = state.meshes.get(node.id);
      if (!group) return;
      const role = roleOf(node.group);
      if (state.preset === "nebula") {
        // Saved things grow, the capability half recedes - the page's own
        // emphasis rule, and the reason that look reads as "memory first".
        const scale = role === "memory" ? 2.15 : (role === "core" ? 1 : 0.6);
        group.scale.setScalar(scale);
        if (mesh && mesh.material) mesh.material.opacity = role === "memory" ? 0.98 : 0.35;
      } else if (state.preset === "radar-dome") {
        group.scale.setScalar(1.15);
        if (mesh && mesh.material) {
          mesh.material.color = new THREE.Color(
            hexToInt(SENTINEL_RINGS[ringOf(node.group)].color));
          mesh.material.opacity = 0.95;
        }
      } else {
        group.scale.setScalar(1);
        if (mesh && mesh.material) {
          mesh.material.color = new THREE.Color(
            hexToInt(colorFor(node.group) || ROLE_COLORS[role] || ROLE_COLORS.memory));
          mesh.material.opacity = 0.9;
        }
      }
      // The neural "highlight one layer" control dims the other two layers
      // rather than hiding them: every name stays a real button.
      if (state.preset === "neural-arbor" && state.layer) {
        const layer = role === "memory" ? 1 : (role === "brain" || role === "group" ? 2 : 3);
        const dim = layer !== state.layer;
        if (mesh && mesh.material) {
          mesh.material.transparent = true;
          mesh.material.opacity = dim ? 0.14 : 0.95;
        }
        group.scale.setScalar(dim ? 0.8 : 1.15);
      }
    });
  }

  function applyPalette() {
    const meta = COSMOS_PRESETS[state.preset] || COSMOS_PRESETS[COSMOS_DEFAULT_LOOK];
    scene.fog.color.setHex(hexToInt(meta.bg));
    renderer.setClearColor(hexToInt(meta.bg), 1);
  }

  /** Put the camera where the picture needs it. `positions` is the whole
   *  picture, so the frame is fitted to the names that are really there; the
   *  fog is pulled with the camera so a 240-name picture is still visible. */
  function framedCamera(presetId = state.preset) {
    const radius = boundsOf(positions).radius;
    const framed = cameraFrame(presetId, {
      positions,
      radius,
      aspect: state.aspect,
    });
    state.frameDistance = framed.distance;
    scene.fog.density = fogDensityAt(framed.distance);
    // The page's far plane is 2,000 because its cameras sit about 250 out. A
    // 240-name picture is framed thousands of units out, and with a fixed far
    // plane the picture would be CLIPPED OUT - the tree drew nothing at all
    // until this followed the frame. Only ever grown, never shrunk below the
    // page's own number.
    const far = Math.max(CAMERA_FAR, framed.distance + radius * 1.6 + 100);
    if (Math.abs(camera.far - far) > 0.5) {
      camera.far = far;
      camera.updateProjectionMatrix();
    }
    return framed;
  }

  function setCamera(presetId = state.preset) {
    const framed = framedCamera(presetId);
    state.camTo = new THREE.Vector3(...framed.position);
    state.targetTo = new THREE.Vector3(...framed.lookAt);
  }

  function snapCamera(presetId = state.preset) {
    const framed = framedCamera(presetId);
    camera.position.set(...framed.position);
    target.set(...framed.lookAt);
    camera.lookAt(target);
    state.camTo = null;
    state.targetTo = null;
  }

  /* ---- the eight looks ------------------------------------------------ */

  function rebuildScene() {
    applyPalette();
    applyPositions();
    rebuildGuides();
    applyMorphology();
    state.orbitClock = 0;
    snapCamera();
  }

  function setPreset(id) {
    if (!isCosmosLook(id) || id === state.preset) return state.preset;
    state.preset = id;
    scene.rotation.set(0, 0, 0);
    state.layer = 0;
    state.followId = null;
    state.alert = false;
    state.lockdown = false;
    state.timeValue = 1;
    applyPalette();
    applyPositions();
    rebuildGuides();
    applyMorphology();
    setCamera();
    return state.preset;
  }

  /* ---- the animation branches ---------------------------------------- */

  function firePulses(count) {
    const wants = Math.max(1, Math.min(8, Math.floor(count || 1)));
    const pool = state.links.length ? state.links : [];
    if (!pool.length) return;
    for (let i = 0; i < wants; i++) {
      const link = pool[i % pool.length];
      // `null` start means "on the next frame": a pulse fired before the page
      // has drawn once waits for it instead of vanishing.
      state.pulses.push({
        link,
        start: state.lastData || null,
        duration: 900 + i * 220,
      });
    }
  }

  function animate(dt, now) {
    state.lastData = now;
    // The gyroscopic core turns in every look that shows it.
    if (state.core && state.core.visible && state.spinning) {
      for (const ring of state.swatch || []) {
        ring.rotation.x += ring.userData.speed[0];
        ring.rotation.y += ring.userData.speed[1];
        ring.rotation.z += ring.userData.speed[2];
      }
    }
    if (state.preset === "planetary-orbit" && state.spinning) {
      state.orbitClock += dt * 0.45 * state.warp;
      // `true` = time advanced and nothing else did: the cached link plan is
      // still this frame's shape, so only its numbers are rewritten.
      applyPositions(true);
      if (state.followId) {
        const point = positionOf(state.followId);
        if (point) {
          focusPoint.set(point.x, point.y, point.z);
          target.lerp(focusPoint, 0.08);
        }
      }
    } else if (state.preset === "neural-arbor" && state.spinning) {
      if (now - state.lastPulse > 1400) {
        state.lastPulse = now;
        firePulses(1);
      }
    } else if (state.preset === "nebula" && state.spinning) {
      spinView(0.001);
      for (const node of state.nodes) {
        if (roleOf(node.group) !== "memory") continue;
        const mesh = state.meshes.get(node.id);
        if (!mesh) continue;
        mesh.rotation.y += 0.025;
        mesh.rotation.x += 0.01;
        if (state.shimmer) {
          const pulse = 1 + Math.sin(now / 700 + node.id.length) * 0.06;
          mesh.scale.setScalar(pulse);
        }
      }
    } else if (state.preset === "dna-helix" && state.spinning) {
      spinView(0.0025);
      if (state.disk) state.disk.group.rotation.y -= 0.01;
    } else if (state.preset === "radar-dome" && state.spinning && state.sweep) {
      state.sweep.rotation.z += dt * 1.4;
    }

    // The camera ease: the page lerps position and target at 0.06/frame.
    if (state.camTo) {
      camera.position.lerp(state.camTo, state.flySpeed);
      if (state.targetTo) target.lerp(state.targetTo, state.flySpeed);
      if (camera.position.distanceTo(state.camTo) < 1.2) {
        camera.position.copy(state.camTo);
        if (state.targetTo) target.copy(state.targetTo);
        state.camTo = null;
        state.targetTo = null;
      }
      camera.lookAt(target);
    } else {
      camera.lookAt(target);
    }

    // Synapse packets: a bright bead travelling along a link, then gone.
    for (let i = state.pulses.length - 1; i >= 0; i--) {
      const pulse = state.pulses[i];
      if (pulse.start === null) pulse.start = now;
      const elapsed = now - pulse.start;
      if (elapsed > pulse.duration) {
        state.pulses.splice(i, 1);
        if (pulse.bead) {
          scene.remove(pulse.bead);
          disposeObject(pulse.bead);
        }
        continue;
      }
      const source = positionOf(pulse.link.source);
      const sink = positionOf(pulse.link.target);
      if (!source || !sink) { state.pulses.splice(i, 1); continue; }
      if (!pulse.bead) {
        pulse.bead = new THREE.Mesh(
          new THREE.SphereGeometry(1.6, 8, 8),
          new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.9 }));
        pulse.bead.frustumCulled = false;
        scene.add(pulse.bead);
      }
      const t = elapsed / pulse.duration;
      pulse.bead.position.set(
        source.x + (sink.x - source.x) * t,
        source.y + (sink.y - source.y) * t + (state.preset === "neural-arbor" ? 12 * Math.sin(t * Math.PI) : 0),
        source.z + (sink.z - source.z) * t);
      pulse.bead.material.opacity = 0.9 * (1 - t);
    }
  }

  /* ---- projection: the page's node buttons ride on this ---------------- */

  const projected = new THREE.Vector3();
  const worldPoint = new THREE.Vector3();
  // The follow camera's scratch point: reused every frame, because a look at a
  // moving planet must not allocate a Vector3 thirty times a second.
  const focusPoint = new THREE.Vector3();

  function project(id) {
    const group = state.groups.get(id);
    if (!group || !state.width || !state.height) return null;
    // The WORLD position, not the local one: three looks turn the whole scene
    // (the nebula and the helix), and a label or a button that used the local
    // position would slowly drift off its body as the scene turned.
    group.updateWorldMatrix(true, false);
    worldPoint.setFromMatrixPosition(group.matrixWorld);
    projected.copy(worldPoint).project(camera);
    if (projected.z < -1 || projected.z > 1) return null;
    const depth = camera.position.distanceTo(worldPoint);
    const half = Math.tan((CAMERA_FOV * Math.PI / 180) / 2);
    const k = (state.height / 2) / Math.max(1, half * depth);
    return {
      x: (projected.x * 0.5 + 0.5) * state.width,
      y: (-projected.y * 0.5 + 0.5) * state.height,
      k,
      depth,
    };
  }

  /** Turn the picture by moving the CAMERA around its target instead of
   *  rotating the scene. For unlit materials the image is identical - the
   *  relative motion of camera and content is the same - but every label and
   *  every node button is projected from this camera, so they stay on their
   *  bodies, and a name can never rotate out of the frame the camera fitted.
   *  (The page's own reference scene turns the scene and crops itself.) */
  function spinView(step) {
    if (!step) return;
    const offset = camera.position.clone().sub(target);
    const cos = Math.cos(step);
    const sin = Math.sin(step);
    camera.position.set(
      target.x + offset.x * cos - offset.z * sin,
      camera.position.y,
      target.z + offset.x * sin + offset.z * cos);
    camera.lookAt(target);
  }

  /* ---- the small controls --------------------------------------------- */

  function actionState(key) {
    switch (key) {
      case "warp": return state.warp > 1;
      case "follow": return Boolean(state.followId);
      case "layer": return state.layer !== 0;
      case "alert": return state.alert;
      case "lockdown": return state.lockdown;
      case "rings": return state.rings;
      case "wide": return state.wide;
      case "sort": return state.ringSort;
      case "chords": return state.chords;
      case "shimmer": return state.shimmer;
      default: return false;
    }
  }

  function action(key) {
    switch (key) {
      case "warp":
        state.warp = state.warp > 1 ? 1 : 3.2;
        return actionState(key);
      case "follow": {
        if (state.followId) { state.followId = null; return false; }
        const group = state.nodes.find((node) => roleOf(node.group) === "group");
        state.followId = group ? group.id : null;
        if (state.followId) setCamera();
        return Boolean(state.followId);
      }
      case "wave":
        firePulses(7);
        return true;
      case "layer":
        state.layer = (state.layer + 1) % 4;   // 0 = every layer
        applyMorphology();
        return actionState(key);
      case "well": {
        const index = (action.well = ((action.well || 0) + 1) % NEBULA_WELLS.length);
        const spot = NEBULA_WELLS[index].at;
        state.camTo = new THREE.Vector3(spot[0] * 1.6, spot[1] * 1.6, spot[2] * 1.6 + 120);
        state.targetTo = new THREE.Vector3(spot[0], spot[1], spot[2]);
        return true;
      }
      case "shimmer":
        state.shimmer = !state.shimmer;
        if (!state.shimmer) {
          for (const node of state.nodes) {
            const mesh = state.meshes.get(node.id);
            if (mesh && roleOf(node.group) === "memory") mesh.scale.setScalar(1);
          }
        }
        return state.shimmer;
      case "sweepBack":
      case "sweepForward": {
        state.timeValue = key === "sweepBack" ? 0 : 1;
        rebuildGuides();
        return true;
      }
      case "alert":
        state.alert = !state.alert;
        if (state.sweep) state.sweep.material.color.setHex(state.alert ? 0xf43f5e : 0x10b981);
        return state.alert;
      case "lockdown":
        state.lockdown = !state.lockdown;
        if (state.dome) {
          state.dome.material.opacity = state.lockdown ? 0.34 : 0.1;
          state.dome.material.color.setHex(state.lockdown ? 0xf43f5e : 0xf59e0b);
        }
        return state.lockdown;
      case "topdown":
        snapCamera();
        return true;
      case "rings":
        state.rings = !state.rings;
        rebuildGuides();
        return state.rings;
      case "wide":
        state.wide = !state.wide;
        applyPositions();
        rebuildGuides();
        snapCamera();
        return state.wide;
      case "cascade":
        firePulses(3);
        return true;
      case "sort":
        state.ringSort = !state.ringSort;
        applyPositions();          // raises the dirty flag: the layout moved
        return state.ringSort;
      case "chords":
        state.chords = !state.chords;
        shapeDirty = true;         // which links exist changed: rebuild them
        updateLinks();
        return state.chords;
      default:
        return null;
    }
  }

  /* ---- frames, resize, dispose --------------------------------------- */

  function resize(width, height, dpr = 1) {
    const wasAspect = state.aspect;
    state.width = Math.max(1, Math.round(width || 0));
    state.height = Math.max(1, Math.round(height || 0));
    state.aspect = state.width / state.height;
    renderer.setPixelRatio(Math.min(Math.max(1, dpr || 1), 2));
    renderer.setSize(state.width, state.height, false);
    camera.aspect = state.aspect;
    camera.updateProjectionMatrix();
    // A NARROWER stage is a smaller frame: the same camera would crop the
    // picture, which is exactly what Gemini's page does. Re-frame when the
    // stage's shape really changed, so a window resize can never strand a name.
    if (positions.length && Math.abs(state.aspect - wasAspect) > 0.005) setCamera();
    return { width: state.width, height: state.height, aspect: state.aspect };
  }

  function frame(now) {
    if (state.disposed || state.lost) return false;
    if (state.width < 2 || state.height < 2) return false;
    const stamp = Number.isFinite(now) ? now : state.lastTime;
    const dt = state.lastTime ? Math.min((stamp - state.lastTime) / 1000, 0.1) : 0;
    state.lastTime = stamp;
    animate(dt, stamp);
    renderer.render(scene, camera);
    state.draws += 1;
    return true;
  }

  function dispose() {
    state.disposed = true;
    for (const group of state.groups.values()) disposeObject(group);
    state.groups.clear();
    state.meshes.clear();
    for (const line of state.linkObjects) disposeObject(line);
    state.linkObjects = [];
    // The cached picture goes with the engine: a later write must not reach
    // into a disposed Line's buffer.
    linkPlan = [];
    positions = [];
    positionById = new Map();
    shapeDirty = true;
    for (const child of state.guides) disposeObject(child);
    state.guides = [];
    if (state.stars) disposeObject(state.stars);
    if (state.core) disposeObject(state.core);
    if (state.cloud) disposeObject(state.cloud);
    for (const pulse of state.pulses) if (pulse.bead) disposeObject(pulse.bead);
    state.pulses = [];
    try { canvas.removeEventListener("webglcontextlost", onContextLost, false); }
    catch (error) { /* no canvas left */ }
    try { renderer.dispose(); } catch (error) { /* already gone */ }
  }

  function onContextLost(event) {
    event.preventDefault();
    state.lost = true;
    if (typeof options.onFail === "function") {
      try { options.onFail(); } catch (error) { /* the page's business */ }
    }
  }

  // Built once per engine and removed in `dispose`, because the page builds a
  // NEW engine on the same canvas every time a hidden galaxy is shown again
  // (2026-10-28). A listener left behind would call the disposed engine's
  // `onFail` on a later context loss and turn 3D off for good.
  canvas.addEventListener("webglcontextlost", onContextLost, false);

  // Build the first look with whatever graph the caller has (usually nothing
  // yet: `setGraph` follows within the same frame in the page's own flow).
  rebuildScene();

  return {
    setGraph,
    setPreset,
    setSpinning(on) { state.spinning = Boolean(on); return state.spinning; },
    resize,
    frame,
    project,
    orbit(dx, dy) {
      // Spherical orbit around the target, at the page's own sensitivity.
      const offset = camera.position.clone().sub(target);
      const radius = Math.max(1, offset.length());
      const theta = Math.atan2(offset.x, offset.z) + (dx || 0);
      const phi = Math.min(Math.PI * 0.48, Math.max(0.08,
        Math.acos(Math.min(1, Math.max(-1, offset.y / radius))) - (dy || 0)));
      camera.position.set(
        target.x + radius * Math.sin(phi) * Math.sin(theta),
        target.y + radius * Math.cos(phi),
        target.z + radius * Math.sin(phi) * Math.cos(theta));
      camera.lookAt(target);
      state.camTo = null;
      state.targetTo = null;
      return { theta, phi, radius };
    },
    zoom(factor) {
      const offset = camera.position.clone().sub(target);
      // The floor is Gemini's own closeness; the ceiling follows the FRAME, not
      // a constant: a 240-name picture legitimately sits thousands of units out,
      // and a fixed 620 cap would snap the camera into the middle of it on the
      // first wheel notch.
      const ceiling = Math.max(MAX_CAMERA_DISTANCE, (state.frameDistance || 0) * 2.5);
      const radius = Math.min(ceiling,
        Math.max(MIN_CAMERA_DISTANCE, offset.length() * (factor || 1)));
      offset.setLength(radius);
      camera.position.copy(target).add(offset);
      camera.lookAt(target);
      state.camTo = null;
      state.targetTo = null;
      return radius;
    },
    resetView() {
      snapCamera();
      return true;
    },
    action,
    actionState,
    actions() { return actionsFor(state.preset); },
    look() { return state.preset; },
    info() {
      return {
        preset: state.preset,
        nodes: state.nodes.length,
        links: state.linkObjects.length,
        guides: state.guides.length,
        draws: state.draws,
        // The cached topology's own rebuild count: unchanged on a steady frame.
        plans: state.plans,
        lost: state.lost,
        disposed: state.disposed,
        spinning: state.spinning,
        width: state.width,
        height: state.height,
        aspect: state.aspect,
        distance: camera.position.distanceTo(target),
        frameDistance: state.frameDistance,
        fill: FRAME_FILL,
        fog: scene.fog ? scene.fog.density : 0,
      };
    },
    dispose,
  };
}
