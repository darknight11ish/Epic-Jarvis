/**
 * The Galaxy's flat layout presets - the pure half of Phase G0.
 *
 * The desktop brain window keeps its current constellation (the physics layout
 * in `brain.js` renderGraph/startLayout), and beside it the owner can choose one
 * of EIGHT flat layouts - "looks" now, since 2026-10-27 the owner asked for
 * "an easy way to change the appearance of the jarvis galaxy to the other
 * models". Nothing here draws: every function returns plain numbers and is
 * deterministic, so the layouts are unit-tested with no DOM at all.
 *
 * The five rich looks the blueprint listed first (its Part B, presets 1-5) were
 * marked "not built yet" until 2026-10-27; they are built here now:
 *
 *   - `planetary-orbit` - the first (best-known) name is a sun at the centre and
 *                       the rest ride homothetic ellipses around it, spaced by
 *                       ARC length so every neighbour is equally far apart.
 *   - `neural-arbor`    - a fan of rows, one node at the root, then Fibonacci
 *                       rows widening upward: a broom crown with dendrite lines
 *                       from each name to the row under it.
 *   - `nebula`          - one soft cloud: a golden-angle (Vogel) spiral, with a
 *                       gentle radial wobble and NO rings, rows or straight
 *                       lines - the one look whose shape is a blob.
 *   - `dna-helix`       - double helices side by side: two strands twisting
 *                       around each column's axis, with a rung between them at
 *                       every row. A helix longer than 60 names starts another
 *                       one beside it, which is what keeps a 240-name picture
 *                       square instead of a 6,000-unit ribbon.
 *   - `radar-dome`      - a dome over a horizon: names on concentric ARCS above
 *                       a ground row, with faint bearing spokes - a radar scope
 *                       that only uses the sky.
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

/** planetary-orbit: the first orbit's semi-minor axis, the pitch between orbits,
 *  the semi-major / semi-minor ratio (all orbits share it, so the family is
 *  homothetic - which is what guarantees one orbit never touches the next), and
 *  the arc-length spacing in gaps.
 *
 *  30 units of semi-minor pitch is 1.25 gaps of clear air between one orbit and
 *  the next at every angle, because homothetic ellipses keep a constant radial
 *  ratio rather than a constant difference. */
export const PLANET_B0 = 92;
export const PLANET_PITCH = 30;
export const PLANET_ASPECT = 1.85;
export const PLANET_ARC_GAP = 1.2;

/** neural-arbor: the root row's node count, then each row's count as a
 *  Fibonacci-style widening, the vertical pitch between rows, the widest a row
 *  may grow before its own nodes are squeezed to MIN_GAP, and the cap on the
 *  dendrite lines drawn from a name to the row beneath it.
 *
 *  Rows are separate horizontal lines 46 units apart, so two names in different
 *  rows can never be closer than 46 whatever their columns do. */
export const ARBOR_ROWS = Object.freeze([1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144]);
export const ARBOR_ROW_PITCH = 46;
export const ARBOR_COL_PITCH = 30;
export const ARBOR_ROW_WIDTH = 1200;
export const ARBOR_MAX_EDGES = 120;

/** nebula: how far apart neighbours sit, as a multiple of the layout gap, and
 *  the size of the gentle radial wobble that stops it reading as a disc.
 *
 *  A Vogel (golden-angle) spiral is the densest even disc of points there is, so
 *  one gap of spacing would put neighbours exactly on the limit; 1.6 gaps keeps
 *  the cloud loose and the wobble (6%) cannot close that margin. */
export const NEBULA_SPACING = 1.6;
export const NEBULA_WOBBLE = 0.06;
export const NEBULA_GOLDEN = 2.399963229728653;

/** dna-helix: the row pitch down one helix (it must clear a gap on its own, so
 *  no two names are ever closer than this whatever their sideways offset), the
 *  number of rows in one turn of the twist, the sideways amplitude of the two
 *  strands, and how many names one helix holds before a second one is drawn
 *  beside it.
 *
 *  Why a bank of helices and not one long one: a double helix side-on with 240
 *  names down 26-unit rows is 6,240 units tall and 124 wide - no camera clamp
 *  can frame that, so it would be drawn cropped. Twelve names per turn is what
 *  makes one column read as a twist, and the column count grows with the square
 *  root of the list (one more column per 6 names) so a 240-name picture stays
 *  roughly square instead of turning into a ribbon. */
export const HELIX_PITCH = 26;
export const HELIX_STEPS_PER_TURN = 12;
export const HELIX_AMPLITUDE = 62;
export const HELIX_NAMES_PER_COLUMN = 6;
export const HELIX_MAX_COLUMNS = 8;
export const HELIX_COLUMN_GAP = 30;
export const HELIX_MAX_RUNGS = 120;

/** radar-dome: the first arc's radius, the pitch between arcs, how many names
 *  stand on the ground row as a fraction of the list, the smallest spacing a
 *  ground row may use, and how far below the pole the ground row sits.
 *
 *  The dome is drawn in the upper half only, so the arcs share their centre at
 *  (0,0) with the guide circles - the ground row is 40 units below that centre,
 *  which is more than a gap, so no row name touches an arc's foot. */
export const DOME_BASE = 72;
export const DOME_PITCH = 36;
export const DOME_GROUND_SHARE = 0.18;
export const DOME_GROUND_GAP = 26;
export const DOME_GROUND_DROP = 40;

/** Where the owner's chosen preset is remembered. A DEVICE display choice, in
 *  the same place and spirit as the theme (`jarvis.theme` in brain.js): it is
 *  never sent to the PC and never written to the backend. */
export const PRESET_STORAGE_KEY = "jarvis.galaxy.preset";

/** Every look that is built, in hotkey order (1-8).
 *
 *  The five rich looks the blueprint listed first kept keys 1-5 and the three
 *  flat ones kept 6-8, so a key the owner already learned still means the same
 *  thing - and keys 1-5, which used to answer "not built yet", now draw a
 *  picture. */
export const BUILT_PRESETS = Object.freeze([
  Object.freeze({ id: "planetary-orbit", key: "1", label: "Planetary orbit",
                  hint: "orbits around one sun" }),
  Object.freeze({ id: "neural-arbor", key: "2", label: "Neural arbor",
                  hint: "a crown of branches" }),
  Object.freeze({ id: "nebula", key: "3", label: "Nebula", hint: "one soft cloud" }),
  Object.freeze({ id: "dna-helix", key: "4", label: "DNA helix",
                  hint: "two spirals, end-on" }),
  Object.freeze({ id: "radar-dome", key: "5", label: "Radar dome",
                  hint: "arcs over a horizon" }),
  Object.freeze({ id: "star-map", key: "6", label: "Star map", hint: "flat rings" }),
  Object.freeze({ id: "clean-tree", key: "7", label: "Clean tree", hint: "four rows" }),
  Object.freeze({ id: "zen-ring", key: "8", label: "Zen ring", hint: "one halo" }),
]);

/** Presets the blueprint names that are NOT built. Empty since 2026-10-27: all
 *  eight are built, so nothing anywhere may say "not built yet" about one of
 *  them. The list stays exported (and frozen) because the menu, the status line
 *  and the keyboard decision all still ask the question, and a later look may
 *  be planned again before it is built. */
export const PLANNED_PRESETS = Object.freeze([]);

/** What the switcher shows, in menu order: the default first, then every built
 *  look in hotkey order. */
export const PRESET_MENU = Object.freeze([
  Object.freeze({ id: DEFAULT_PRESET, key: null, label: "Constellation", built: true,
                  hint: "the current layout" }),
  ...BUILT_PRESETS.map((p) => Object.freeze({ ...p, built: true })),
]);

/** The preset a hotkey selects, or null. Every one of the eight looks answers
 *  its own key, 1 to 8. */
export function presetForKey(key) {
  const text = String(key);
  return BUILT_PRESETS.find((p) => p.key === text) ?? null;
}

/** The not-built preset a hotkey names, or null. Empty since 2026-10-27 (every
 *  look is built); kept so the keyboard decision still has a place to say so
 *  honestly if a future look is planned before it is built. */
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
  return `${meta.label} is not built yet. Press 1 to 8 for a look that is.`;
}

/**
 * What a key press should do, given the preset already on screen.
 *
 * The decision only, so the page's handler is three lines and this is testable:
 *   - a built look's key selects it; pressing it AGAIN returns to the
 *     constellation, so the current view is never more than one key away;
 *   - a not-built look's key (none today) asks the page to say so, and changes
 *     nothing;
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
 * anything else (the constellation's own id, a look planned but not built, a
 * corrupt value from an older build, `null`) means the constellation.
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
 *  Pure data, drawn by brain.js's own SVG layer; a test can assert it. */
function guides() {
  return { circles: [], lines: [], paths: [] };
}

function round2(v) {
  return Math.round(v * 100) / 100;
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
 *  the list's own order (most facts first), not by group. */
export function cleanTreeRowFor(node, index = 0) {
  if (index < TREE_CORE) return 0;
  const group = String(node?.group ?? "other");
  if (group === "person" || group === "pet") return 1;           // the beings
  if (group === "organisation" || group === "project") return 2; // the work
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
    const startX = round2(p.x);
    const startY = round2(p.y);
    const controlX = round2(Math.cos(angle + 0.22) * ZEN_RADIUS * 0.7);
    const controlY = round2(Math.sin(angle + 0.22) * ZEN_RADIUS * 0.7);
    const endX = round2(Math.cos(angle) * ZEN_RADIUS * 0.36);
    const endY = round2(Math.sin(angle) * ZEN_RADIUS * 0.36);
    out.paths.push({
      d: `M ${startX} ${startY} Q ${controlX} ${controlY} ${endX} ${endY}`,
      kind: "chord",
      // The same three points as numbers, so a renderer that is not SVG (the
      // HUD's canvas) can draw the very same curve without parsing `d`.
      x1: startX, y1: startY,
      cx: controlX, cy: controlY,
      x2: endX, y2: endY,
    });
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
 * The five rich looks (2026-10-27) - shared geometry
 * -------------------------------------------------------------------------- */

/** Ramanujan's approximation of an ellipse's perimeter. */
function ellipsePerimeter(a, b) {
  const h = ((a - b) * (a - b)) / ((a + b) * (a + b));
  return Math.PI * (a + b) * (1 + (3 * h) / (10 + Math.sqrt(4 - 3 * h)));
}

/**
 * `count` points on the ellipse (a cos t, b sin t), spaced evenly by ARC LENGTH
 * rather than by angle.
 *
 * Equal angles would crowd the ends of the long axis - the parametric speed
 * there is only `b` - and two names would land a gap apart at best and touching
 * at worst. Walking the perimeter at a constant arc step is what makes every
 * neighbour on an orbit the same distance apart, which is the whole no-overlap
 * argument for this layout.
 */
function ellipsePoints(count, a, b, phase = 0) {
  if (count <= 0) return [];
  const steps = Math.max(360, count * 12);
  const table = [{ s: 0, t: 0, x: a, y: 0 }];
  let walked = 0;
  let last = table[0];
  for (let i = 1; i <= steps; i++) {
    const t = (i / steps) * Math.PI * 2;
    const x = a * Math.cos(t);
    const y = b * Math.sin(t);
    walked += Math.hypot(x - last.x, y - last.y);
    last = { s: walked, t, x, y };
    table.push(last);
  }
  const out = [];
  let at = 0;
  for (let k = 0; k < count; k++) {
    const want = (k / count) * walked;
    while (at + 1 < table.length && table[at + 1].s < want) at++;
    const from = table[at];
    const to = table[Math.min(at + 1, table.length - 1)];
    const span = to.s - from.s;
    const f = span > 1e-9 ? (want - from.s) / span : 0;
    const t = from.t + (to.t - from.t) * f + phase;
    out.push({ x: a * Math.cos(t), y: b * Math.sin(t) });
  }
  return out;
}

/** An ellipse as a closed SVG path string, `samples` points around it. */
function ellipsePath(a, b, samples = 48) {
  const parts = [];
  for (let i = 0; i < samples; i++) {
    const t = (i / samples) * Math.PI * 2;
    parts.push(`${i === 0 ? "M" : "L"} ${round2(a * Math.cos(t))} ${round2(b * Math.sin(t))}`);
  }
  parts.push("Z");
  return parts.join(" ");
}

/* --------------------------------------------------------------------------
 * planetary-orbit
 * -------------------------------------------------------------------------- */

/**
 * One sun at the centre, and every other name riding an ellipse around it.
 *
 * The orbits are HOMOTHETIC - every one is the same shape, scaled - so the
 * radial distance between two neighbouring orbits is a constant fraction of the
 * radius: 30 units at the narrowest point and 55 at the widest, both more than a
 * gap. Names are spread by arc length (see `ellipsePoints`), so no two names on
 * one orbit are closer than about 1.2 gaps either.
 */
export function layoutPlanetaryOrbit(nodes, { gap = MIN_GAP } = {}) {
  const list = capped(nodes);
  const points = [];
  const orbits = [];
  // The core name is the sun: the one place in this picture with nothing beside
  // it, because everything else is in orbit.
  if (list.length) points.push({ x: 0, y: 0 });
  let ring = 0;
  while (points.length < list.length) {
    const b = PLANET_B0 + PLANET_PITCH * ring;
    const a = b * PLANET_ASPECT;
    const capacity = Math.max(1,
      Math.floor(ellipsePerimeter(a, b) / (gap * PLANET_ARC_GAP)));
    const count = Math.min(capacity, list.length - points.length);
    // A small deterministic phase per orbit, so two orbits' names do not line up
    // into radial spokes by accident.
    const phase = (ring * Math.PI) / Math.max(4, count * 2);
    points.push(...ellipsePoints(count, a, b, phase));
    orbits.push({ a, b });
    ring++;
    if (ring > 40) break;                  // unreachable at 240; a stop, not a cap
  }
  separate(points, gap);

  const out = guides();
  for (const orbit of orbits) {
    out.paths.push({
      d: ellipsePath(orbit.a, orbit.b),
      kind: "orbit",
      // The same ellipse as numbers, for the HUD's canvas (which draws the same
      // curve without parsing `d` - the two cannot drift, they are made here).
      a: round2(orbit.a),
      b: round2(orbit.b),
    });
  }
  return {
    id: "planetary-orbit",
    nodes: list.map((n, i) => ({ id: n.id, x: points[i].x, y: points[i].y })),
    rings: orbits.map((orbit) => orbit.b),
    rows: [],
    minGap: gap,
    guides: out,
  };
}

/* --------------------------------------------------------------------------
 * neural-arbor
 * -------------------------------------------------------------------------- */

/** The node count of each row of the arbor, top of the list first.
 *
 *  Row 1 is the single root; the rows under it widen like a Fibonacci tree
 *  (1, 2, 3, 5, 8, 13, ...) and the last row takes whatever is left, so the
 *  picture's silhouette is a crown that widens to the top. A remainder too small
 *  for its own row is merged into the row under it, so the crown never pinches
 *  (40 names are 1/2/3/5/8/21, not 1/2/3/5/8/13/8). */
export function arborRowCounts(total) {
  const want = Math.max(0, Math.floor(total));
  if (want === 0) return [];
  const rows = [];
  let left = want;
  for (let i = 0; i < ARBOR_ROWS.length && left > 0; i++) {
    const count = Math.min(ARBOR_ROWS[i], left);
    rows.push(count);
    left -= count;
  }
  // A list longer than the fixed rows can hold keeps widening, so a 240-name
  // arbor is still an arbor: each extra row is the last row's count again.
  while (left > 0) {
    const count = Math.min(ARBOR_ROWS[ARBOR_ROWS.length - 1], left);
    rows.push(count);
    left -= count;
  }
  while (rows.length > 1 && rows[rows.length - 1] < rows[rows.length - 2]) {
    const last = rows.pop();
    rows[rows.length - 1] += last;
  }
  return rows;
}

/**
 * A tree of rows widening upward: one root at the bottom, the crown at the top,
 * with a faint dendrite line from most names to the row beneath them.
 *
 * Rows are separate horizontal lines `ARBOR_ROW_PITCH` apart and each row's
 * neighbours are at least `MIN_GAP` apart, so neither two names in one row nor
 * two names in different rows can overlap - the same argument the clean tree
 * makes, in a shape that is a fan instead of a table.
 */
export function layoutNeuralArbor(nodes, { gap = MIN_GAP } = {}) {
  const list = capped(nodes);
  const counts = arborRowCounts(list.length);
  const rows = [];
  const points = [];
  const depth = counts.length;
  let index = 0;
  counts.forEach((count, row) => {
    // The root sits at the BOTTOM: canvas y grows downward, so the last row is
    // the lowest one.
    const y = ((depth - 1) / 2 - row) * ARBOR_ROW_PITCH;
    const pitch = count > 1
      ? Math.max(gap, Math.min(ARBOR_COL_PITCH, ARBOR_ROW_WIDTH / (count - 1)))
      : 0;
    const members = [];
    for (let j = 0; j < count; j++, index++) {
      members.push(index);
      points.push({ x: (j - (count - 1) / 2) * pitch, y });
    }
    rows.push({ row, y, count, members });
  });
  separate(points, gap);

  const out = guides();
  // One dendrite per name (except the root and any name in the bottom row, which
  // has nothing under it), to the nearest column of the row below. Capped, so a
  // 240-name arbor does not become a thicket.
  const edges = Math.min(ARBOR_MAX_EDGES, list.length);
  for (let i = Math.min(list.length - 1, edges - 1); i > 0; i--) {
    const row = rows.find((r) => r.members.includes(i));
    const below = row ? rows[rows.indexOf(row) + 1] : null;
    if (!row || !below) continue;
    const j = row.members.indexOf(i);
    const under = below.members[Math.min(below.count - 1,
      Math.round((j / Math.max(1, row.count - 1)) * (below.count - 1)))];
    if (under === undefined) continue;
    out.lines.push({
      x1: round2(points[i].x), y1: round2(points[i].y),
      x2: round2(points[under].x), y2: round2(points[under].y),
      kind: "dendrite",
    });
  }
  return {
    id: "neural-arbor",
    nodes: list.map((n, i) => ({ id: n.id, x: points[i].x, y: points[i].y })),
    rings: [],
    rows: rows.map((r) => r.y),
    minGap: gap,
    guides: out,
  };
}

/* --------------------------------------------------------------------------
 * nebula
 * -------------------------------------------------------------------------- */

/**
 * One soft cloud, and the only look with no rings, rows or straight lines.
 *
 * A Vogel (golden-angle) spiral is the most even way to fill a disc with points
 * with nothing arranged in rows or rings; the radius grows as sqrt(index) so
 * every part of the cloud has the same density. Neighbours are about
 * `NEBULA_SPACING` gaps apart, and the gentle wobble is far too small to close
 * that margin - `separate()` is still the backstop.
 */
export function layoutNebula(nodes, { gap = MIN_GAP } = {}) {
  const list = capped(nodes);
  const spread = gap * NEBULA_SPACING;
  const points = list.map((n, i) => {
    const radius = spread * Math.sqrt(i + 0.5);
    const wobble = 1 + NEBULA_WOBBLE * Math.sin(i * NEBULA_GOLDEN);
    const angle = i * NEBULA_GOLDEN;
    return {
      x: radius * wobble * Math.cos(angle),
      y: radius * wobble * Math.sin(angle),
    };
  });
  separate(points, gap);
  const out = guides();                    // a cloud has no guides: it is a cloud
  return {
    id: "nebula",
    nodes: list.map((n, i) => ({ id: n.id, x: points[i].x, y: points[i].y })),
    rings: [],
    rows: [],
    minGap: gap,
    guides: out,
  };
}

/* --------------------------------------------------------------------------
 * dna-helix
 * -------------------------------------------------------------------------- */

/**
 * Double helices side by side: two strands twisting around each column's own
 * axis, with a rung between them at every row.
 *
 * Every name sits on its column's own row ladder, `HELIX_PITCH` apart, so two
 * names in one column are at least 26 units apart whatever their sideways
 * offsets do - the two strands' curves DO cross, but their names never do,
 * because the crossing falls between two rows. Columns are `HELIX_COLUMN_GAP`
 * wider than two amplitudes, so the widest name of one column clears the widest
 * name of the next.
 *
 * A helix longer than `HELIX_PER_COLUMN` starts another one beside it, which is
 * what keeps a 240-name picture square instead of a 6,000-unit ribbon.
 */
export function layoutDnaHelix(nodes, { gap = MIN_GAP } = {}) {
  const list = capped(nodes);
  const columns = Math.max(1, Math.min(HELIX_MAX_COLUMNS,
    Math.round(Math.sqrt(list.length / HELIX_NAMES_PER_COLUMN)) || 1));
  const pitch = Math.max(gap * 1.05, HELIX_PITCH);
  const columnPitch = HELIX_AMPLITUDE * 2 + Math.max(gap, HELIX_COLUMN_GAP);
  const wave = Math.PI * 2 / HELIX_STEPS_PER_TURN;
  const points = [];
  const rungs = [];
  const perColumn = Math.ceil(list.length / columns);
  for (let column = 0; column < columns; column++) {
    const first = column * perColumn;
    const rows = Math.max(0, Math.min(perColumn, list.length - first));
    const centreX = (column - (columns - 1) / 2) * columnPitch;
    // Each column is centred on its own axis, so a short last column still
    // stands beside the others instead of hanging off the bottom.
    const top = -((rows - 1) / 2) * pitch;
    let previous = null;
    for (let k = 0; k < rows; k++) {
      const index = first + k;
      const strand = k % 2 === 0 ? 1 : -1;   // the two strands alternate rows
      const sideways = strand * HELIX_AMPLITUDE * Math.cos(k * wave);
      const point = { x: centreX + sideways, y: top + k * pitch };
      points[index] = point;
      if (previous) {
        rungs.push({
          d: `M ${round2(previous.x)} ${round2(previous.y)} `
            + `L ${round2(point.x)} ${round2(point.y)}`,
          kind: "rung",
          x1: round2(previous.x), y1: round2(previous.y),
          x2: round2(point.x), y2: round2(point.y),
        });
      }
      previous = point;
    }
  }
  separate(points, gap);

  const out = guides();
  out.paths.push(...rungs.slice(0, HELIX_MAX_RUNGS));
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

/** How many names fit on a HALF circle of `radius` with `gap` air. The chord
 *  between neighbours on a half circle is the same as on a full one, so this is
 *  half the full ring's capacity. */
function arcCapacity(radius, gap) {
  return Math.max(1, Math.floor(ringCapacity(radius, gap) / 2));
}

/**
 * A dome over a horizon: the first names on a ground row, the rest on arcs above
 * it, with faint bearing spokes.
 *
 * The arcs are the upper half of circles centred on (0,0) - so the guide circles
 * are real circles, and the dome's own names never touch the lower half of the
 * canvas. The ground row sits `DOME_GROUND_DROP` below the pole (more than a
 * gap), and its own spacing is stretched to at least `DOME_GROUND_GAP` however
 * many names stand on it.
 */
export function layoutRadarDome(nodes, { gap = MIN_GAP } = {}) {
  const list = capped(nodes);
  const total = list.length;
  const groundCount = total <= 2
    ? total
    : Math.min(total - 1, Math.max(2, Math.round(total * DOME_GROUND_SHARE)));
  const domeCount = total - groundCount;
  const arcs = [];
  let need = domeCount;
  let ring = 0;
  while (need > 0) {
    const radius = DOME_BASE + DOME_PITCH * ring;
    const capacity = arcCapacity(radius, gap);
    const count = Math.min(capacity, need);
    arcs.push({ radius, count });
    need -= count;
    ring++;
    if (ring > 60) break;                  // unreachable at 240; a stop, not a cap
  }
  const points = [];
  arcs.forEach(({ radius, count }) => {
    // The upper half, strictly between PI and 2PI: every name is above the
    // horizon (canvas y negative), which is what keeps the arcs clear of the
    // ground row below it. Half a step of offset keeps a name off both feet.
    for (let k = 0; k < count; k++) {
      const angle = Math.PI + ((k + 0.5) / count) * Math.PI;
      points.push({ x: Math.cos(angle) * radius, y: Math.sin(angle) * radius });
    }
  });
  const outer = arcs.length ? arcs[arcs.length - 1].radius : DOME_BASE;
  if (groundCount > 0) {
    const pitch = groundCount > 1
      ? Math.max(DOME_GROUND_GAP, (outer * 2) / (groundCount - 1))
      : 0;
    for (let g = 0; g < groundCount; g++) {
      points.push({
        x: (g - (groundCount - 1) / 2) * pitch,
        y: DOME_GROUND_DROP,
      });
    }
  }
  separate(points, gap);

  const out = guides();
  for (const arc of arcs) out.circles.push({ r: arc.radius, kind: "dome" });
  for (let k = 0; k < 6; k++) {
    const angle = Math.PI + (k + 0.5) * (Math.PI / 6);
    out.lines.push({
      x1: 0, y1: 0,
      x2: round2(Math.cos(angle) * outer), y2: round2(Math.sin(angle) * outer),
      kind: "bearing",
    });
  }
  return {
    id: "radar-dome",
    nodes: list.map((n, i) => ({ id: n.id, x: points[i].x, y: points[i].y })),
    rings: arcs.map((arc) => arc.radius),
    rows: [DOME_GROUND_DROP],
    minGap: gap,
    guides: out,
  };
}

/**
 * The layout for a preset id, or null when there is none to apply (the default
 * constellation is not a flat layout).
 */
export function layoutFor(id, nodes, options) {
  switch (id) {
    case "planetary-orbit": return layoutPlanetaryOrbit(nodes, options);
    case "neural-arbor": return layoutNeuralArbor(nodes, options);
    case "nebula": return layoutNebula(nodes, options);
    case "dna-helix": return layoutDnaHelix(nodes, options);
    case "radar-dome": return layoutRadarDome(nodes, options);
    case "star-map": return layoutStarMap(nodes, options);
    case "clean-tree": return layoutCleanTree(nodes, options);
    case "zen-ring": return layoutZenRing(nodes, options);
    default: return null;
  }
}
