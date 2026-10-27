/**
 * The Galaxy's flat layout presets - the pure half of Phase G0.
 *
 * The desktop brain window keeps its current constellation (the physics layout
 * in `brain.js` renderGraph/startLayout), and beside it the owner can choose
 * one of EIGHT looks. Nothing here draws: every function returns plain numbers
 * and is deterministic, so the layouts are unit-tested with no DOM at all.
 *
 * WHAT A PRESET IS (the blueprint's three simple views)
 *
 *   - `star-map`   - a flat tabletop schematic: every node on one plane, on
 *                    concentric rings at R = 34 / 68 / 108 (further rings at the
 *                    same 34px pitch only when the list outgrows them), with the
 *                    blueprint's seven subtle radial sector spokes.
 *   - `clean-tree` - a stationary, front-facing four-row hierarchy, using the
 *                    blueprint's row heights (Y = +62 / +24 / -14 / -48). The
 *                    blueprint's rows are the curated architecture bands (core,
 *                    brains, clusters, tools + memories); this picture's nodes
 *                    are the people and things saved facts name (`galaxy-view.js`),
 *                    so the same four bands are filled with the nearest real
 *                    meaning, top to bottom: the core (the names Jarvis knows most
 *                    about), the beings (people and pets), the work
 *                    (organisations and projects), and the rest (places, things
 *                    and kinds Jarvis is not sure about). The SHAPE is the
 *                    blueprint's; the words are this picture's.
 *   - `zen-ring`   - Ultra-minimal: the first (best-known) name at the centre and
 *                    the others spaced evenly on one R=108 halo, with inward
 *                    Bezier chords. A list too large for the one halo grows
 *                    OUTWARD at a 24px pitch, so R=108 stays the calm centre.
 *
 * THE FIVE RICH VIEWS the blueprint lists (built 2026-10-27)
 *
 *  The owner's ask of 2026-10-27 was "an easy way to change the appearance of
 *  the jarvis galaxy to the other models [modes]", so the five that used to be
 *  disabled chips are real looks now. They are FLAT, 2D interpretations of the
 *  blueprint's five rich views - not the WebGL engines (see the honesty note
 *  below), and each one is a different way of USING THE AREA:
 *
 *   - `planetary-orbit` - a sun at the centre (the best-known name) with the
 *                    rest on concentric ellipses (a = 74 + 46k, squashed to
 *                    0.6 of that height), a few bodies per orbit, each orbit's
 *                    bodies staggered by the golden angle so two orbits never
 *                    line their planets up. Ellipses, not circles, so it is not
 *                    the star map with a bigger centre.
 *   - `neural-arbor` - a soma at the centre, then a doubling tree: level m
 *                    holds up to 2^m names on a circle, and every name is
 *                    joined to its nearest name on the level before by one
 *                    faint dendrite. Each level's radius is chosen so its
 *                    neighbours still clear the gap, so the tree does not
 *                    overlap however many names it holds.
 *   - `nebula`      - a phyllotaxis cloud: names on the golden angle at
 *                    r = R*sqrt(t), so the density is even and the parastichies
 *                    read as spiral arms - no rings, no rows, no centre.
 *   - `dna-helix`   - two sine strands, the second braided half a rung behind
 *                    the first, joined by rungs, and tilted 30 degrees so the
 *                    braid runs across the picture instead of up it.
 *   - `radar-dome`  - a half disc above a horizon line: names on concentric
 *                    semicircle arcs, with the horizon and one sweep arm as
 *                    guides. The only look with a flat edge.
 *
 *  HONESTY ABOUT "RICH": the blueprint's five are 3D engines with their own
 *  controls (warp orbit, isolate cortical layer, sweep laser, lockdown dome...).
 *  What is built here is the FLAT half of each: deterministic 2D positions and
 *  guide lines in the same shape, with no 3D, no new dependency, no per-preset
 *  control, no extra data and no route. A look moves the dots; it never adds a
 *  node, a link, a label rule or a write.
 *
 * ONE COPY OF THE MATHS, AND A MIRROR
 *
 *  `jarvis_hud.html` is one vendored file with no imports, so the HUD's Galaxy
 *  carries a small INLINE MIRROR of these layout functions (documented as such
 *  at its own copy). The mirror must stay identical in behaviour:
 *  `jarvis-desktop/tests/hud.mjs` compares the two position for position, so a
 *  drift between them fails a test instead of quietly giving the two windows
 *  different pictures.
 *
 * HARD RULES THIS MODULE KEEPS
 *
 *   - Standard library only: no imports, no new dependency, no 3D, no remote
 *     asset, no server route, no `fetch`. It cannot write anything.
 *   - Deterministic: no `Math.random`, no clock, no locale. The same node list
 *     lays out the same way, twice, forever - so the picture the owner learns
 *     stays learnable.
 *   - Pure: the input nodes are read, never mutated. Each layout returns new
 *     `{id, x, y}` records in the SAME order they were given (the graph keeps
 *     `rank`, `group` and `weight`; a layout may only move a node).
 *   - Bounded: at most `MAX_LAYOUT_NODES` nodes are laid out, matching
 *     `galaxy-view.js`'s `MAX_RENDERED_NODES` (a test pins the two together).
 *   - Labels are NOT this module's business: `brain.js` chooses labels from the
 *     existing `rank`-based rules (`labelledNodes`), and a layout never changes
 *     a rank.
 *   - No overlap: every two nodes are at least the layout's own `minGap` apart
 *     in layout units (24 for the grids; 21 on the zen halo, which is what lets
 *     the blueprint's 31 names fit on one R=108 ring). `separate()` is the
 *     belt-and-braces guarantee the tests check at 240 nodes.
 *   - Nothing here throws for normal input; `layoutIsUsable()` is the caller's
 *     guard, and `brain.js` falls back to the constellation if even that fails.
 *
 * @module galaxy-presets
 */

/** The current physics constellation - the view that ships today, unchanged. */
export const DEFAULT_PRESET = "constellation";

/** The most names any layout is asked to place. Same bound as the picture. */
export const MAX_LAYOUT_NODES = 240;

/** Closest two node centres may be, in layout units, when a layout has no
 *  geometry of its own to justify a different number.
 *
 *  The drawn dot is at most 12px across (`radiusOf` tops out at 12), so 24 is
 *  two full dots plus air: a pair this far apart never reads as one blob. */
export const MIN_GAP = 24;

/** star-map: the three ring radii, the pitch of any extra ring, and the seven
 *  subtle sector spokes the blueprint's `6 · 2D Star Map` names. */
export const STAR_RINGS = Object.freeze([34, 68, 108]);
export const STAR_RING_PITCH = 34;
export const STAR_SPOKES = 7;

/** clean-tree: four rows, their blueprint Y values (top to bottom), and the
 *  spacing between neighbours in a row.
 *
 *  The blueprint's Row 1 is Y=+62, Row 2 Y=+24, Row 3 Y=-14 and Row 4 is the
 *  Y=-48..-64 band (tools and memories), measured on a screen where UP is
 *  positive. The canvas/SVG this picture is drawn in has the opposite sign (Y
 *  grows DOWNWARD), so the same four rows land at canvas Y = -62 / -24 / +14 /
 *  +48: the core stays at the TOP, exactly as the blueprint draws it. The rows
 *  are FIXED on screen - the tree is stationary by design - and a row is always
 *  one flat line, never a scattered band. */
export const TREE_ROWS = 4;
export const TREE_ROW_Y = Object.freeze([-62, -24, 14, 48]);
export const TREE_COL_GAP = 26;
/** How many of the best-known names sit on the core row. */
export const TREE_CORE = 6;

/** zen-ring: the one halo, the pitch of any overflow ring, and its chords.
 *
 *  The blueprint puts the core name at the centre and spaces the other 31
 *  names on one R=108 halo. 21 units of gap is what makes 31 fit on that one
 *  ring (2 * pi * 108 / 31 = 21.9), and the halo still clears a visible dot at
 *  the zoom a 32-name graph is drawn at. */
export const ZEN_RADIUS = 108;
export const ZEN_RING_PITCH = 24;
export const ZEN_HALO_GAP = 21;
export const ZEN_MAX_CHORDS = 48;

/** planetary-orbit: the innermost orbit's semi-major axis, the gap between
 *  orbits, the squash that makes them ellipses, and the sun's own clear space.
 *
 *  The blueprint draws planets on orbits round a star. Two orbits 46 apart,
 *  squashed to 0.6, are at least 46 * 0.6 = 27.6 apart at their closest (the
 *  minor-axis end), which clears the 24 gap; the sun sits well inside the first
 *  orbit's 74 * 0.6 = 44.4 near point. */
export const ORBIT_FIRST = 74;
export const ORBIT_PITCH = 46;
export const ORBIT_SQUASH = 0.6;
/** A stop for the orbit loop, never reached at 240 names; a whole circle needs
 *  ORBIT_FIRST + ORBIT_PITCH * k to reach r >= 917 at 240, so this is slack. */
export const ORBIT_MAX_ORBITS = 40;

/** neural-arbor: how much clear space the soma keeps, and the safety factor
 *  above the gap that every level's radius is built to (1.06 = 6% air, so a
 *  rounding error cannot put two names exactly on the limit). */
export const ARBOR_GAP_ROOM = 26;
export const ARBOR_SPREAD = 1.06;
/** A stop for the level loop; a real tree needs ~8 levels at 240 names. */
export const ARBOR_MAX_LEVELS = 24;

/** The golden angle in radians - the phyllotaxis constant the nebula's spiral
 *  arms and the planetary orbits' stagger both use. */
export const GOLDEN_ANGLE = 2.399963229728653;

/** nebula: the cloud's radius. R=250 is what keeps 240 names at least 24 apart
 *  in an even cloud: an even disc needs sqrt(240 * 24^2 / (pi * 0.81)) ~ 233. */
export const NEBULA_RADIUS = 250;

/** dna-helix: the vertical distance between rungs, the second strand's half
 *  rung offset, the wave's amplitude and its wavelength, and the tilt.
 *
 *  The half-rung offset is the whole no-overlap guarantee: any two names from
 *  the two strands are at least HELIX_RUNG / 2 = 24 apart vertically, whatever
 *  the wave does horizontally, and two names on one strand are a full rung
 *  apart. The tilt is a rigid rotation, so it cannot change any distance. */
export const HELIX_RUNG = 48;
export const HELIX_AMP = 46;
export const HELIX_WAVE = 192;
export const HELIX_TILT = -Math.PI / 6;

/** radar-dome: the innermost arc, the gap between arcs, the sweep arm's angle
 *  (60 degrees above the horizon), and a stop for the arc loop. */
export const DOME_FIRST = 46;
export const DOME_PITCH = 46;
export const DOME_SWEEP = -Math.PI / 3;
export const DOME_MAX_ARCS = 40;

/** Where the owner's chosen preset is remembered. A DEVICE display choice, in
 *  the same place and spirit as the theme (`jarvis.theme` in brain.js): it is
 *  never sent to the PC and never written to the backend. The HUD page keeps
 *  its own key for its own canvas (`jarvis.galaxy.hud.look`), because the two
 *  windows are separate surfaces (the HUD is also served to other devices). */
export const PRESET_STORAGE_KEY = "jarvis.galaxy.preset";

/** Every look the eight hotkeys choose. Order is the key order (1..8), which is
 *  also the blueprint's numbering: its five rich views first, then the three
 *  flat ones. `hint` is the one-line "what it is" the chip's tooltip uses. */
export const BUILT_PRESETS = Object.freeze([
  Object.freeze({ id: "planetary-orbit", key: "1", label: "Planetary orbit",
                  hint: "a sun and its orbits" }),
  Object.freeze({ id: "neural-arbor", key: "2", label: "Neural arbor",
                  hint: "branching dendrites" }),
  Object.freeze({ id: "nebula", key: "3", label: "Nebula", hint: "a drifting cloud" }),
  Object.freeze({ id: "dna-helix", key: "4", label: "DNA helix",
                  hint: "two strands and rungs" }),
  Object.freeze({ id: "radar-dome", key: "5", label: "Radar dome",
                  hint: "a dome of blips" }),
  Object.freeze({ id: "star-map", key: "6", label: "Star map", hint: "flat rings" }),
  Object.freeze({ id: "clean-tree", key: "7", label: "Clean tree", hint: "four rows" }),
  Object.freeze({ id: "zen-ring", key: "8", label: "Zen ring", hint: "one halo" }),
]);

/** Presets a build can list before it can draw them. EMPTY since 2026-10-27:
 *  all eight looks are built, so nothing is shown as "not built yet".
 *
 *  Kept (empty) rather than deleted, with `plannedForKey` below, because the
 *  menu/status/keyboard code is written to tell the truth about a future look
 *  that is listed before it exists - `brain.js` still refuses to draw a
 *  `built: false` chip. Deleting the shape would make that day a rewrite;
 *  leaving one empty list makes it one entry. */
export const PLANNED_PRESETS = Object.freeze([]);

/** What the switcher shows, in menu order: the default, then the eight looks in
 *  key order (the same order the chips have always had: 1 to 8). */
export const PRESET_MENU = Object.freeze([
  Object.freeze({ id: DEFAULT_PRESET, key: null, label: "Constellation", built: true,
                  hint: "the current layout" }),
  ...BUILT_PRESETS.map((p) => Object.freeze({ ...p, built: true })),
]);

/** The preset a hotkey selects, or null. Every look answers its own key now. */
export function presetForKey(key) {
  const text = String(key);
  return BUILT_PRESETS.find((p) => p.key === text) ?? null;
}

/** The not-built preset a hotkey names, or null. Always null now that all
 *  eight looks are built - see `PLANNED_PRESETS`. */
export function plannedForKey(key) {
  const text = String(key);
  return PLANNED_PRESETS.find((p) => p.key === text) ?? null;
}


/** One preset's menu entry by id, or null. */
export function presetMeta(id) {
  return PRESET_MENU.find((p) => p.id === id) ?? null;
}

/** The gap a layout guarantees, or null for the constellation. */
export function gapForPreset(id) {
  if (id === "zen-ring") return ZEN_HALO_GAP;
  return BUILT_PRESETS.some((p) => p.id === id) ? MIN_GAP : null;
}

/** What the live status line (and a test) says about a preset.
 *
 *  `null` for an unknown id; otherwise the owner's sentence. Kept here rather
 *  than in `brain.js` so the keyboard decision and its words are testable with
 *  no page. */
export function presetStatus(id) {
  const meta = presetMeta(id);
  if (!meta) return "";
  if (meta.built) {
    return meta.id === DEFAULT_PRESET
      ? "Layout: the constellation (the current view)."
      : `Layout: ${meta.label}. Press its key again for the constellation.`;
  }
  return `${meta.label} is not built yet. Press 1 to 8 for one of the eight looks.`;
}

/**
 * What a key press should do, given the preset already on screen.
 *
 * The decision only, so the page's handler is three lines and this is testable:
 *   - a built look's key (1-8) selects it; pressing it AGAIN returns to the
 *     constellation, so the current view is never more than one key away;
 *   - a key that names a listed-but-not-built preset asks the page to say so,
 *     and changes nothing (no such look today - see `PLANNED_PRESETS`);
 *   - anything else (0, arrows, letters... the stage's own pan/zoom keys) gets
 *     `null` and is left to the existing handler.
 */
export function switchRequest(key, activeId = DEFAULT_PRESET) {
  const built = presetForKey(key);
  if (built) {
    const id = activeId === built.id ? DEFAULT_PRESET : built.id;
    return { action: "apply", key: built.key, id };
  }
  const planned = plannedForKey(key);
  if (planned) return { action: "planned", key: planned.key, id: planned.id };
  return null;
}

/**
 * Which preset a remembered value names. Only a BUILT look can be restored;
 * anything else (the constellation's own id, a look this build does not have,
 * a corrupt value from an older build, `null`) means the constellation.
 *
 * This is the safe half of the persistence: the caller stores a string and
 * never trusts what it reads back, so a corrupt or stale value can only ever
 * fall back to the default view - it can never break the page.
 */
export function storedPreset(raw) {
  const id = typeof raw === "string" ? raw.trim() : "";
  return BUILT_PRESETS.some((p) => p.id === id) ? id : DEFAULT_PRESET;
}

/**
 * Is a layout usable enough to draw? The caller's own guard, so a bad layout
 * (a bug, a future edit, a preset whose code is missing) is caught HERE and the
 * picture safely stays on the constellation instead of drawing nonsense.
 *
 * Required: one point per (capped) input node, the SAME ids in the same order,
 * finite coordinates, and guide lists that are arrays when present. Deliberately
 * tolerant about the decorations: a layout may have no guides at all.
 */
export function layoutIsUsable(layout, nodes) {
  if (!layout || !Array.isArray(layout.nodes)) return false;
  const list = Array.isArray(nodes) ? nodes : [];
  const want = Math.min(list.length, MAX_LAYOUT_NODES);
  if (layout.nodes.length !== want) return false;
  for (let i = 0; i < want; i++) {
    const point = layout.nodes[i];
    const node = list[i];
    if (!point || !node || point.id !== node.id) return false;
    if (!Number.isFinite(point.x) || !Number.isFinite(point.y)) return false;
  }
  const decorations = layout.guides;
  if (decorations !== undefined) {
    if (!decorations || typeof decorations !== "object") return false;
    for (const key of ["circles", "lines", "paths"]) {
      const value = decorations[key];
      if (value !== undefined && !Array.isArray(value)) return false;
    }
  }
  return true;
}

/* --------------------------------------------------------------------------
 * Geometry helpers - pure, deterministic, shared by the three layouts
 * -------------------------------------------------------------------------- */

/** How many nodes fit on a circle of `radius` with `gap` air.
 *  Adjacent centres are `2R sin(pi / count)` apart, so the largest count whose
 *  chord still clears `gap` is pi / asin(gap / (2R)). */
function ringCapacity(radius, gap) {
  if (radius <= 0) return 1;
  const ratio = gap / (2 * radius);
  if (ratio >= 1) return 1;
  return Math.max(1, Math.floor(Math.PI / Math.asin(ratio)));
}

/** Points on a circle: `count` evenly spaced, starting at -90deg plus `phase`. */
function ringPoints(count, radius, phase = 0) {
  const out = [];
  for (let i = 0; i < count; i++) {
    const angle = -Math.PI / 2 + phase + (i / count) * Math.PI * 2;
    out.push({ x: Math.cos(angle) * radius, y: Math.sin(angle) * radius });
  }
  return out;
}

/**
 * The no-overlap guarantee, and only ever a guarantee: it is called after the
 * construction, which already clears the layout's gap on every pair. If a
 * future capacity formula is wrong, this still pushes the offenders apart
 * instead of drawing two names as one blob - deterministically (pairs in index
 * order, tie-break along a stable direction), never with a random jitter.
 */
function separate(points, gap) {
  const want = gap * gap;
  for (let pass = 0; pass < 80; pass++) {
    let moved = false;
    for (let i = 0; i < points.length; i++) {
      for (let j = i + 1; j < points.length; j++) {
        const a = points[i];
        const b = points[j];
        let dx = b.x - a.x;
        let dy = b.y - a.y;
        let d2 = dx * dx + dy * dy;
        if (d2 >= want) continue;
        if (d2 < 1e-9) {
          // Exactly on top of each other: pick a stable direction from the
          // indices, so the same list separates the same way every time.
          dx = ((i * 31 + j * 17) % 5) - 2 || 1;
          dy = ((i * 13 + j * 7) % 5) - 2 || 1;
          d2 = dx * dx + dy * dy;
        }
        const d = Math.sqrt(d2);
        const push = (gap - d) / 2;
        const ux = dx / d;
        const uy = dy / d;
        a.x -= ux * push;
        a.y -= uy * push;
        b.x += ux * push;
        b.y += uy * push;
        moved = true;
      }
    }
    if (!moved) break;
  }
  return points;
}

/** Bound the input to the picture's own cap, in its own (ranked) order. */
function capped(nodes) {
  const list = Array.isArray(nodes) ? nodes : [];
  return list.slice(0, MAX_LAYOUT_NODES);
}

/** The guide shapes a layout returns: faint rings, lines and chords.
 *  Pure data, drawn by brain.js's own SVG layer; a test can assert it.
 *
 *  A `path` is one SVG `d` string - and, for a renderer that is not SVG (the
 *  HUD's canvas mirror), the same geometry in plain numbers, whichever of these
 *  three fits the shape:
 *    - `points`: [[x, y], ...] the polyline the `d` draws;
 *    - `ellipse`: {a, b}, a full ellipse round the origin;
 *    - `from`/`ctrl`/`to`: the quadratic Bezier the `d` draws (`M ... Q ...`).
 *  At least one is always present, so a canvas can draw every guide. */
function guides() {
  return { circles: [], lines: [], paths: [] };
}

function round2(v) {
  return Math.round(v * 100) / 100;
}

/** One sampled polyline: the SVG text, and the points themselves. */
function polylinePath(points, kind) {
  const rounded = points.map((p) => [round2(p.x), round2(p.y)]);
  const d = rounded.map(([x, y], i) => `${i ? "L" : "M"} ${x} ${y}`).join(" ");
  return { d, kind, points: rounded };
}

/** One quadratic Bezier: the SVG text the Brain window draws, and the three
 *  points the canvas mirror re-draws it from (the same numbers, rounded the
 *  same way, so both renderers agree). */
function quadPath(from, ctrl, to, kind) {
  const a = { x: round2(from.x), y: round2(from.y) };
  const c = { x: round2(ctrl.x), y: round2(ctrl.y) };
  const b = { x: round2(to.x), y: round2(to.y) };
  return {
    d: `M ${a.x} ${a.y} Q ${c.x} ${c.y} ${b.x} ${b.y}`,
    kind,
    from: a,
    ctrl: c,
    to: b,
  };
}

/** A full ellipse round the origin, sampled finely enough to read as smooth. */
const ELLIPSE_SAMPLES = 72;
function ellipsePath(a, b, kind) {
  const points = [];
  for (let i = 0; i <= ELLIPSE_SAMPLES; i++) {
    const t = (i / ELLIPSE_SAMPLES) * Math.PI * 2;
    points.push({ x: a * Math.cos(t), y: b * Math.sin(t) });
  }
  const path = polylinePath(points, kind);
  path.ellipse = { a: round2(a), b: round2(b) };
  return path;
}

/** How many nodes fit on a HALF circle (a dome's arc) of `radius` with `gap`
 *  air: adjacent centres are 2R sin(pi / (2 * count)) apart, so the largest
 *  count whose chord clears `gap` is pi / (2 * asin(gap / (2R))). */
function halfRingCapacity(radius, gap) {
  if (radius <= 0) return 1;
  const ratio = gap / (2 * radius);
  if (ratio >= 1) return 1;
  return Math.max(1, Math.floor(Math.PI / (2 * Math.asin(ratio))));
}

/** The smallest angle between two directions, in [0, pi]. */
function angleBetween(a, b) {
  const turn = Math.PI * 2;
  const d = (((a - b) % turn) + turn) % turn;
  return d > Math.PI ? turn - d : d;
}

/* --------------------------------------------------------------------------
 * star-map
 * -------------------------------------------------------------------------- */

/**
 * A flat tabletop schematic: concentric rings, every node on the same plane.
 *
 * Ring 1 is R=34, ring 2 R=68, ring 3 R=108 - and only a list too large for
 * those three adds rings beyond 108 at the same 34px pitch, so the shape never
 * stops being a star map. The blueprint asks for seven subtle radial sector
 * spokes; they start at an offset between node angles so a spoke never runs
 * through a name.
 */
export function layoutStarMap(nodes, { gap = MIN_GAP } = {}) {
  const list = capped(nodes);
  const points = [];
  const rings = [];
  let ringIndex = 0;
  while (points.length < list.length) {
    const radius = ringIndex < STAR_RINGS.length
      ? STAR_RINGS[ringIndex]
      : STAR_RINGS[STAR_RINGS.length - 1]
        + STAR_RING_PITCH * (ringIndex - STAR_RINGS.length + 1);
    const capacity = ringCapacity(radius, gap);
    const count = Math.min(capacity, list.length - points.length);
    const phase = (ringIndex * Math.PI) / Math.max(1, capacity * 2);
    points.push(...ringPoints(count, radius, phase));
    rings.push(radius);
    ringIndex++;
  }
  separate(points, gap);

  const out = guides();
  for (const r of rings) out.circles.push({ r, kind: "ring" });
  const outer = rings.length ? rings[rings.length - 1] : STAR_RINGS[0];
  for (let k = 0; k < STAR_SPOKES; k++) {
    const angle = Math.PI / 7 + (k / STAR_SPOKES) * Math.PI * 2;
    out.lines.push({
      x1: 0, y1: 0,
      x2: Math.cos(angle) * outer, y2: Math.sin(angle) * outer,
      kind: "spoke",
    });
  }
  return {
    id: "star-map",
    nodes: list.map((n, i) => ({ id: n.id, x: points[i].x, y: points[i].y })),
    rings,
    rows: [],
    minGap: gap,
    guides: out,
  };
}

/* --------------------------------------------------------------------------
 * clean-tree
 * -------------------------------------------------------------------------- */

/** Which of the four rows a name belongs to. 0 is the core row, filled from
 *  the list's own order (most facts first), not by group.
 *
 *  Two graphs feed this layout: the Brain window's people-and-things picture
 *  (kinds: person, pet, place, organisation, project, thing) and the HUD's
 *  capability Galaxy (kinds: core, model, cluster, tool, and the memory kinds).
 *  The four bands have a meaning in each, so each kind maps to the band that
 *  means the same thing there. A kind neither graph has falls to "the rest". */
export function cleanTreeRowFor(node, index = 0) {
  if (index < TREE_CORE) return 0;
  const group = String(node?.group ?? "other");
  if (group === "person" || group === "pet") return 1;           // the beings
  if (group === "organisation" || group === "project") return 2; // the work
  // The HUD's own halves: the brains the PC runs, then the abilities they hold
  // (an ability group is a group OF abilities). Without these the HUD's clean
  // tree would be the core row and one long row of everything else.
  if (group === "model") return 1;                               // the brains
  if (group === "cluster" || group === "tool") return 2;         // the abilities
  return 3;                                                      // places & things
}

/**
 * Four stationary, front-facing rows at the blueprint's heights: core, beings,
 * work, the rest.
 *
 * The core row is the first `TREE_CORE` names in the list's ranked order (the
 * ones Jarvis knows most about); every other name goes to the row its kind
 * belongs to, centred on its own row. Rows are FIXED screen lines; neighbours in
 * a row are `TREE_COL_GAP` apart, so two rows can never overlap.
 */
export function layoutCleanTree(nodes, { gap = MIN_GAP } = {}) {
  const list = capped(nodes);
  const rows = TREE_ROW_Y.map((y, row) => ({ row, y, members: [] }));
  list.forEach((n, i) => rows[cleanTreeRowFor(n, i)].members.push({ node: n, index: i }));
  const points = new Array(list.length);
  for (const row of rows) {
    const count = row.members.length;
    row.members.forEach((entry, j) => {
      points[entry.index] = {
        x: (j - (count - 1) / 2) * TREE_COL_GAP,
        y: row.y,
      };
    });
  }
  separate(points, gap);

  const out = guides();
  for (const row of rows) {
    const half = (Math.max(0, row.members.length - 1) * TREE_COL_GAP) / 2 + 13;
    out.lines.push({ x1: -half, y1: row.y, x2: half, y2: row.y, kind: "row" });
  }
  return {
    id: "clean-tree",
    nodes: list.map((n, i) => ({ id: n.id, x: points[i].x, y: points[i].y })),
    rings: [],
    rows: rows.map((r) => r.y),
    minGap: gap,
    guides: out,
  };
}

/* --------------------------------------------------------------------------
 * zen-ring
 * -------------------------------------------------------------------------- */

/**
 * One calm halo: the best-known name at the centre, the rest on R=108, with
 * inward Bezier chords.
 *
 * A list too large for the one halo grows OUTWARD at the 24px pitch (it never
 * adds an inner ring), so R=108 stays the calm centre of the picture. One chord
 * is drawn for each name on the primary halo, capped so a large graph does not
 * become a web; the endpoints come from the laid-out points, so a chord always
 * touches its own name.
 */
export function layoutZenRing(nodes, { gap = ZEN_HALO_GAP } = {}) {
  const list = capped(nodes);
  const ringCounts = [];
  // The centre core takes the first name (blueprint: J.A.R.V.I.S. at [0,0]).
  let need = Math.max(0, list.length - 1);
  for (let r = 0; need > 0; r++) {
    const radius = ZEN_RADIUS + ZEN_RING_PITCH * r;
    const capacity = ringCapacity(radius, gap);
    const count = Math.min(capacity, need);
    ringCounts.push({ radius, count });
    need -= count;
    if (r > 40) break;                    // unreachable at 240; a stop, not a cap
  }
  const points = [];
  if (list.length) points.push({ x: 0, y: 0 });   // the core name
  ringCounts.forEach(({ radius, count }, index) => {
    points.push(...ringPoints(count, radius, index * (Math.PI / Math.max(2, count))));
  });
  separate(points, gap);

  const out = guides();
  for (const { radius } of ringCounts) {
    out.circles.push({ r: radius, kind: radius === ZEN_RADIUS ? "halo" : "ring" });
  }
  const halo = ringCounts[0]?.count ?? 0;
  const chords = Math.min(ZEN_MAX_CHORDS, halo);
  for (let k = 0; k < chords; k++) {
    const p = points[1 + k];              // points[0] is the centre core
    if (!p || (p.x === 0 && p.y === 0)) continue;
    const angle = Math.atan2(p.y, p.x);
    const ex = Math.cos(angle) * ZEN_RADIUS * 0.36;
    const ey = Math.sin(angle) * ZEN_RADIUS * 0.36;
    const cx = Math.cos(angle + 0.22) * ZEN_RADIUS * 0.7;
    const cy = Math.sin(angle + 0.22) * ZEN_RADIUS * 0.7;
    out.paths.push(quadPath(p, { x: cx, y: cy }, { x: ex, y: ey }, "chord"));
  }
  return {
    id: "zen-ring",
    nodes: list.map((n, i) => ({ id: n.id, x: points[i].x, y: points[i].y })),
    rings: ringCounts.map((r) => r.radius),
    rows: [],
    minGap: gap,
    guides: out,
  };
}

/* --------------------------------------------------------------------------
 * planetary-orbit
 * -------------------------------------------------------------------------- */

/**
 * A sun and its orbits: the best-known name at the centre, every other name on
 * one of a set of concentric ELLIPSES.
 *
 * Each orbit is 46 units wider than the one inside it and squashed to 0.6 of
 * that height, so two neighbouring orbits are at least 27.6 apart at their
 * closest (the minor-axis end) and the 24 gap holds without `separate()` having
 * to move anything. Bodies on an orbit are evenly spaced in the ellipse's own
 * parameter, which is what makes the count formula the one a circle of the
 * same *height* would give; each orbit starts at a different phase so two
 * orbits never line their planets up.
 *
 * The guides are the orbits themselves: one faint ellipse each. That is why it
 * does not read as the star map - the star map is circles and spokes.
 */
export function layoutPlanetaryOrbit(nodes, { gap = MIN_GAP } = {}) {
  const list = capped(nodes);
  const points = [];
  const orbits = [];
  if (list.length) points.push({ x: 0, y: 0 });          // the sun
  let need = Math.max(0, list.length - 1);
  for (let k = 0; need > 0 && k < ORBIT_MAX_ORBITS; k++) {
    const a = ORBIT_FIRST + ORBIT_PITCH * k;
    const b = a * ORBIT_SQUASH;
    const count = Math.min(ringCapacity(b, gap), need);
    const phase = k * GOLDEN_ANGLE;
    for (let j = 0; j < count; j++) {
      const t = -Math.PI / 2 + phase + (j / count) * Math.PI * 2;
      points.push({ x: Math.cos(t) * a, y: Math.sin(t) * b });
    }
    orbits.push({ a, b, count });
    need -= count;
  }
  separate(points, gap);

  const out = guides();
  for (const orbit of orbits) out.paths.push(ellipsePath(orbit.a, orbit.b, "orbit"));
  return {
    id: "planetary-orbit",
    nodes: list.map((n, i) => ({ id: n.id, x: points[i].x, y: points[i].y })),
    rings: orbits.map((orbit) => orbit.a),
    rows: [],
    minGap: gap,
    guides: out,
  };
}

/* --------------------------------------------------------------------------
 * neural-arbor
 * -------------------------------------------------------------------------- */

/**
 * A soma and its dendrites: a doubling tree, level by level.
 *
 * Level 0 is the soma at the centre. Level m holds up to 2^m names, evenly
 * spaced on a circle, and every name is joined by ONE faint dendrite to the
 * nearest name on the level before - so the guides are a tree with exactly
 * n - 1 edges, and the picture is a branching arbor rather than a set of
 * rings. Each level's radius is the smallest that keeps its own neighbours a
 * whole gap apart (2 * r * sin(pi / count) >= gap * 1.06) and that also keeps
 * it a gap clear of the level inside it, so no two names can collide however
 * many there are.
 *
 * A level that cannot be filled (240 names leave the last level short) spreads
 * the names it does hold over the whole circle, so the crown never has a
 * missing wedge.
 */
export function layoutNeuralArbor(nodes, { gap = MIN_GAP } = {}) {
  const list = capped(nodes);
  const points = [];
  const levels = [];                 // [{ radius, count, first }]
  let placed = 0;
  let previousRadius = 0;
  for (let m = 0; placed < list.length && m < ARBOR_MAX_LEVELS; m++) {
    const want = m === 0 ? 1 : 2 ** m;
    const count = Math.min(want, list.length - placed);
    let radius = 0;
    if (m > 0) {
      // A level holding one name has no neighbour to clear: only the level
      // inside it constrains its radius.
      const cleared = count > 1
        ? (gap * ARBOR_SPREAD) / (2 * Math.sin(Math.PI / count))
        : 0;
      radius = Math.max(cleared, previousRadius + gap, ARBOR_GAP_ROOM);
    }
    const first = points.length;
    for (let i = 0; i < count; i++) {
      const angle = ((i + 0.5) / count) * Math.PI * 2;
      points.push({ x: Math.cos(angle) * radius, y: Math.sin(angle) * radius });
    }
    levels.push({ radius, count, first });
    previousRadius = radius;
    placed += count;
  }
  separate(points, gap);

  const out = guides();
  for (let m = 1; m < levels.length; m++) {
    const parent = levels[m - 1];
    const child = levels[m];
    for (let i = 0; i < child.count; i++) {
      const at = child.first + i;
      const angle = Math.atan2(points[at].y, points[at].x);
      let nearest = parent.first;
      let nearestGap = Infinity;
      for (let j = 0; j < parent.count; j++) {
        const other = parent.first + j;
        const distance = angleBetween(angle, Math.atan2(points[other].y, points[other].x));
        if (distance < nearestGap) {
          nearestGap = distance;
          nearest = other;
        }
      }
      out.lines.push({
        x1: points[nearest].x, y1: points[nearest].y,
        x2: points[at].x, y2: points[at].y,
        kind: "dendrite",
      });
    }
  }
  return {
    id: "neural-arbor",
    nodes: list.map((n, i) => ({ id: n.id, x: points[i].x, y: points[i].y })),
    rings: levels.map((level) => level.radius),
    rows: [],
    minGap: gap,
    guides: out,
  };
}

/* --------------------------------------------------------------------------
 * nebula
 * -------------------------------------------------------------------------- */

/**
 * A drifting cloud: names on the golden angle at r = R * sqrt(t).
 *
 * That is the phyllotaxis sunflower, the one deterministic arrangement that
 * fills a disc at an even density: the area each name gets is the same, so the
 * 240-name case still clears the gap (R = 250 is sized for exactly that), and
 * the parastichies read as spiral arms. No rings, no rows, no centre name - the
 * cloud IS the look, so it carries no guides.
 */
export function layoutNebula(nodes, { gap = MIN_GAP } = {}) {
  const list = capped(nodes);
  const count = list.length;
  const points = [];
  for (let i = 0; i < count; i++) {
    const t = count > 1 ? (i + 0.5) / count : 0.5;
    const radius = NEBULA_RADIUS * Math.sqrt(t);
    const angle = i * GOLDEN_ANGLE;
    points.push({ x: Math.cos(angle) * radius, y: Math.sin(angle) * radius });
  }
  separate(points, gap);
  return {
    id: "nebula",
    nodes: list.map((n, i) => ({ id: n.id, x: points[i].x, y: points[i].y })),
    rings: [],
    rows: [],
    minGap: gap,
    guides: guides(),
  };
}

/* --------------------------------------------------------------------------
 * dna-helix
 * -------------------------------------------------------------------------- */

/** The point one strand takes at `v` (the un-tilted height), before the tilt. */
function helixPoint(v, strand, height) {
  const phase = (((v + height / 2) / HELIX_WAVE) * Math.PI * 2);
  const u = Math.cos(phase) * HELIX_AMP * (strand ? -1 : 1);
  const c = Math.cos(HELIX_TILT);
  const s = Math.sin(HELIX_TILT);
  return { x: u * c - v * s, y: u * s + v * c };
}

/**
 * A double helix: two strands braided half a rung apart, joined by rungs, and
 * tilted 30 degrees so the braid crosses the picture instead of standing up it.
 *
 * The half-rung offset is the whole no-overlap proof: two names from the two
 * strands are at least HELIX_RUNG / 2 = 24 apart VERTICALLY whatever the wave
 * does, and two names on one strand are a whole rung apart. The tilt is a rigid
 * rotation of every point, so it cannot change a distance. The height is a
 * whole number of rungs, so those offsets are exact.
 *
 * The guides are the two backbones (the same wave, sampled three times per
 * rung) and one rung per pair - a ladder you can read at a glance.
 */
export function layoutDnaHelix(nodes, { gap = MIN_GAP } = {}) {
  const list = capped(nodes);
  const rungs = Math.max(1, Math.ceil(list.length / 2));
  const height = rungs * HELIX_RUNG;
  const points = list.map((_, i) => {
    const rung = Math.floor(i / 2);
    const strand = i % 2;
    const v = rung * HELIX_RUNG + (strand ? HELIX_RUNG / 2 : 0) - height / 2;
    return helixPoint(v, strand, height);
  });
  separate(points, gap);

  const out = guides();
  for (const strand of [0, 1]) {
    const path = [];
    for (let s = 0; s <= rungs * 3; s++) {
      const v = ((s / 3) * HELIX_RUNG) + (strand ? HELIX_RUNG / 2 : 0) - height / 2;
      path.push(helixPoint(v, strand, height));
    }
    out.paths.push(polylinePath(path, "strand"));
  }
  for (let i = 0; i + 1 < points.length; i += 2) {
    out.lines.push({
      x1: points[i].x, y1: points[i].y,
      x2: points[i + 1].x, y2: points[i + 1].y,
      kind: "rung",
    });
  }
  return {
    id: "dna-helix",
    nodes: list.map((n, i) => ({ id: n.id, x: points[i].x, y: points[i].y })),
    rings: [],
    rows: [],
    minGap: gap,
    guides: out,
  };
}

/* --------------------------------------------------------------------------
 * radar-dome
 * -------------------------------------------------------------------------- */

/** A semicircle arc above the horizon (canvas Y grows downward, so the dome is
 *  the NEGATIVE-y half), sampled for the guide layer. */
const DOME_ARC_SAMPLES = 48;
function domeArcPath(radius) {
  const points = [];
  for (let i = 0; i <= DOME_ARC_SAMPLES; i++) {
    const phi = (i / DOME_ARC_SAMPLES) * Math.PI;
    points.push({ x: Math.cos(phi) * radius, y: -Math.sin(phi) * radius });
  }
  return polylinePath(points, "arc");
}

/**
 * A radar dome: a half disc above a horizon line, names on concentric arcs.
 *
 * The tightest pair on an arc is the same chord bound a half circle gives
 * (2r sin(pi / 2n) >= gap), and neighbouring arcs are 46 apart, further than
 * the gap. The horizon and one sweep arm at 60 degrees are the guides, and the
 * flat bottom edge is what makes this the only look that is not round.
 */
export function layoutRadarDome(nodes, { gap = MIN_GAP } = {}) {
  const list = capped(nodes);
  const points = [];
  const arcs = [];
  let need = list.length;
  for (let k = 0; need > 0 && k < DOME_MAX_ARCS; k++) {
    const radius = DOME_FIRST + DOME_PITCH * k;
    const count = Math.min(halfRingCapacity(radius, gap), need);
    for (let j = 0; j < count; j++) {
      const phi = ((j + 0.5) / count) * Math.PI;         // above the horizon
      points.push({ x: Math.cos(phi) * radius, y: -Math.sin(phi) * radius });
    }
    arcs.push(radius);
    need -= count;
  }
  separate(points, gap);

  const out = guides();
  for (const radius of arcs) out.paths.push(domeArcPath(radius));
  const outer = arcs.length ? arcs[arcs.length - 1] : DOME_FIRST;
  out.lines.push({ x1: -outer, y1: 0, x2: outer, y2: 0, kind: "horizon" });
  out.lines.push({
    x1: 0, y1: 0,
    x2: Math.cos(DOME_SWEEP) * outer, y2: Math.sin(DOME_SWEEP) * outer,
    kind: "sweep",
  });
  return {
    id: "radar-dome",
    nodes: list.map((n, i) => ({ id: n.id, x: points[i].x, y: points[i].y })),
    rings: arcs,
    rows: [],
    minGap: gap,
    guides: out,
  };
}

/**
 * The layout for a preset id, or null when there is none to apply (the default
 * constellation is not a flat layout, and a look this build does not have has
 * no layout).
 */
export function layoutFor(id, nodes, options) {
  switch (id) {
    case "star-map": return layoutStarMap(nodes, options);
    case "clean-tree": return layoutCleanTree(nodes, options);
    case "zen-ring": return layoutZenRing(nodes, options);
    case "planetary-orbit": return layoutPlanetaryOrbit(nodes, options);
    case "neural-arbor": return layoutNeuralArbor(nodes, options);
    case "nebula": return layoutNebula(nodes, options);
    case "dna-helix": return layoutDnaHelix(nodes, options);
    case "radar-dome": return layoutRadarDome(nodes, options);
    default: return null;
  }
}
