/**
 * The Galaxy's flat layout presets - the pure half of Phase G0.
 *
 * Phase G0 of the Galaxy rework (the owner's answer A/A, 2026-10-23; the
 * blueprint `jarvis_galaxy_rework_architectural_blueprint_2026_10_23.md`, Part
 * B, presets 6-8) is deliberately small: the desktop brain window keeps its
 * current constellation (the physics layout in `brain.js` renderGraph/
 * startLayout), and beside it the owner can choose one of three FLAT layouts.
 * Nothing here draws: every function returns plain numbers and is
 * deterministic, so the layouts are unit-tested with no DOM at all.
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

/** Where the owner's chosen preset is remembered. A DEVICE display choice, in
 *  the same place and spirit as the theme (`jarvis.theme` in brain.js): it is
 *  never sent to the PC and never written to the backend. */
export const PRESET_STORAGE_KEY = "jarvis.galaxy.preset";

/** The three layouts G0 builds. Order is the hotkey order (6, 7, 8). */
export const BUILT_PRESETS = Object.freeze([
  Object.freeze({ id: "star-map", key: "6", label: "Star map", hint: "flat rings" }),
  Object.freeze({ id: "clean-tree", key: "7", label: "Clean tree", hint: "four rows" }),
  Object.freeze({ id: "zen-ring", key: "8", label: "Zen ring", hint: "one halo" }),
]);

/** The five rich presets the blueprint lists before these three.
 *
 *  Shown in the menu as "not built yet" - never silently missing, and never
 *  claiming to exist (the blueprint's phases G4 builds them; G0 builds only the
 *  flat layouts). */
export const PLANNED_PRESETS = Object.freeze([
  Object.freeze({ id: "planetary-orbit", key: "1", label: "Planetary orbit" }),
  Object.freeze({ id: "neural-arbor", key: "2", label: "Neural arbor" }),
  Object.freeze({ id: "nebula", key: "3", label: "Nebula" }),
  Object.freeze({ id: "dna-helix", key: "4", label: "DNA helix" }),
  Object.freeze({ id: "radar-dome", key: "5", label: "Radar dome" }),
]);

/** What the switcher shows, in menu order: the default, the five not-built
 *  presets in blueprint number order, then the three that work. */
export const PRESET_MENU = Object.freeze([
  Object.freeze({ id: DEFAULT_PRESET, key: null, label: "Constellation", built: true,
                  hint: "the current layout" }),
  ...PLANNED_PRESETS.map((p) => Object.freeze({ ...p, built: false, hint: "not built yet" })),
  ...BUILT_PRESETS.map((p) => Object.freeze({ ...p, built: true })),
]);

/** The preset a hotkey selects, or null. Only the three built layouts answer a
 *  key; 1-5 are handled by `plannedForKey` and shown as not built. */
export function presetForKey(key) {
  const text = String(key);
  return BUILT_PRESETS.find((p) => p.key === text) ?? null;
}

/** The not-built preset a hotkey names, or null. */
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
  return `${meta.label} is not built yet. Press 6, 7 or 8 for a flat layout.`;
}

/**
 * What a key press should do, given the preset already on screen.
 *
 * The decision only, so the page's handler is three lines and this is testable:
 *   - a built preset's key selects it; pressing it AGAIN returns to the
 *     constellation, so the current view is never more than one key away;
 *   - a not-built preset's key (1-5) asks the page to say so, and changes
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
 * Which preset a remembered value names. Only the three BUILT layouts can be
 * restored; anything else (the constellation's own id, a planned preset, a
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
    const ex = Math.cos(angle) * ZEN_RADIUS * 0.36;
    const ey = Math.sin(angle) * ZEN_RADIUS * 0.36;
    const cx = Math.cos(angle + 0.22) * ZEN_RADIUS * 0.7;
    const cy = Math.sin(angle + 0.22) * ZEN_RADIUS * 0.7;
    out.paths.push({
      d: `M ${round2(p.x)} ${round2(p.y)} Q ${round2(cx)} ${round2(cy)} ${round2(ex)} ${round2(ey)}`,
      kind: "chord",
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

/**
 * The layout for a preset id, or null when there is none to apply (the default
 * constellation is not a flat layout, and a planned preset does not exist).
 */
export function layoutFor(id, nodes, options) {
  switch (id) {
    case "star-map": return layoutStarMap(nodes, options);
    case "clean-tree": return layoutCleanTree(nodes, options);
    case "zen-ring": return layoutZenRing(nodes, options);
    default: return null;
  }
}
