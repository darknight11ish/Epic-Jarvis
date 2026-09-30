/**
 * Activity heatmap and balance chart, the pure half (the owner's tick of
 * 2026-09-30; docs/GOALS-PROGRESS-DESIGN.md part C and its "Progress
 * contract (frozen)"; JARVIS-API.md section 105; backend jarvis_progress.py).
 *
 * The PC works every count, shade, week label, value and sentence out; this
 * file only reads its answers with a default for every key, lays them out
 * (the shared geometry, checked against tests/fixtures/progress-cases.json)
 * and builds the screen-reader text. No DOM, no network, no storage.
 *
 * What is never here: any count of days in a run, any share of days, any
 * total for the balance chart, any single score, any red colour. The words the PC
 * sends are shown as sent.
 *
 * @module progress
 */

/** The fixed labels, key for key the contract's `words`. */
export const WORDS = Object.freeze({
  title: "Progress",
  heat_title: "Activity",
  heat_under: "Steps you tick and numbers you log, day by day. A quiet day is just a quiet day.",
  heat_total: "Last {weeks} weeks: {things} on {days}.",
  heat_empty: "Nothing here yet. A step you tick or a number you log will show on its day.",
  heat_undated: "Steps ticked before this was added have no date, so they are not shown.",
  day_some: "{things} on {date}",
  day_none: "Nothing on {date}",
  week_of: "Week of {date}",
  balance_title: "Balance",
  balance_under: "Pick 3 to 8 of your numbers or goals. Each spoke shows how far you are from your first number to your target. There is no total.",
  balance_none: "Nothing picked yet.",
  balance_few: "Pick at least 3 to see the chart.",
  balance_edit: "Choose what to show",
  balance_save: "Save the chart",
  balance_clear: "Clear the chart",
  balance_rename: "Name on the chart",
  balance_limit: "Pick 3 to 8 areas, or none to clear the chart.",
  no_numbers: "no numbers yet",
  no_target: "no target yet",
  no_steps: "no steps yet",
  gone: "gone",
  no_choices: "Nothing to pick from yet. Give a number a target, or accept a goal.",
  hidden: "Hidden while memory lists and chat history are hidden.",
  private: "Health or money: kept on screen, never read aloud or sent anywhere.",
  summary_heat: "Activity, last {weeks} weeks. {total}",
  summary_balance: "Balance chart, {n} areas. {items} No overall score.",
});

/** Words only this screen uses (not part of the shared contract). */
export const SCREEN_WORDS = Object.freeze({
  hidden_title: "Hidden",
  show: "Show",
  show_title: "Asks Windows Hello - your PIN, fingerprint or face - then shows this picture.",
  hidden_choice: "(hidden)",
  cancel: "Cancel",
  week_col: "Week",
  days: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
  read_failed: "Could not read the Progress pictures: ",
});

/** Fills `{name}` holes. */
export function fill(template, values = {}) {
  return String(template).replace(/\{(\w+)\}/g, (all, key) => (
    Object.prototype.hasOwnProperty.call(values, key) ? String(values[key]) : all));
}

/* ── Geometry the two apps share ──────────────────────────────────────── */

export const LIMITS = Object.freeze({
  weeks_default: 12, weeks_min: 4, weeks_max: 26, axes_min: 3, axes_max: 8,
  label_max: 24, label_short: 12,
});

/** Heatmap cell, gap and step (contract section 3). */
export const HEAT = Object.freeze({ cell: 14, gap: 3, step: 17, rows: 7, height: 116 });

/** The accent laid over the surface at each level; level 0 has no fill. */
export const SHADE_ALPHA = Object.freeze([0.0, 0.22, 0.42, 0.66, 0.92]);

/** Radar box, centre, outer ring radius, ring shares, label offset (section 4). */
export const RADAR = Object.freeze({
  size: 260, centre: 130, radius: 80, labelRadius: 94, rings: [0.25, 0.5, 0.75, 1.0], dotRadius: 4,
});

const r2 = (n) => Math.round(n * 100) / 100 + 0;

function num(v, fallback = 0) {
  return typeof v === "number" && Number.isFinite(v) ? v : fallback;
}

function text(v) {
  return typeof v === "string" ? v : "";
}

/** Width and height of the whole grid for `weeks` weeks. */
export function heatSize(weeks) {
  const w = Math.max(1, Math.trunc(num(weeks, LIMITS.weeks_default)));
  return { width: w * HEAT.step - HEAT.gap, height: HEAT.height };
}

/** One square per day, in the answer's order (`x = col * 17`, `y = row * 17`). */
export function heatRects(days) {
  return (Array.isArray(days) ? days : []).map((d) => ({
    date: text(d.date),
    x: num(d.col) * HEAT.step,
    y: num(d.row) * HEAT.step,
    size: HEAT.cell,
    level: Math.min(4, Math.max(0, Math.trunc(num(d.level)))),
  }));
}

/** The level's alpha, 0 to 0.92 (level 0 has no fill). */
export function shadeAlpha(level) {
  return SHADE_ALPHA[Math.min(4, Math.max(0, Math.trunc(num(level))))];
}

/** A legend swatch's wording from the PC's `levels`: "0", "1", "3-4", "5+". */
export function levelWords(level) {
  const min = num(level && level.min);
  const max = level ? level.max : null;
  if (max === null || max === undefined) return `${min}+`;
  return min === max ? String(min) : `${min}-${max}`;
}

/** The rings' radii (25, 50, 75, 100 per cent of the outer radius). */
export function ringRadii() {
  return RADAR.rings.map((share) => r2(RADAR.radius * share));
}

/**
 * The balance chart's geometry for a list of areas: spoke `i` of `n` aims
 * at -90 degrees + i * 360 / n (first straight up, then clockwise); a vertex
 * sits at radius * fraction; `fraction: null` puts it in the centre and
 * flags a dot. Numbers are rounded to 2 places, like the fixture.
 */
export function radar(fractions) {
  const list = Array.isArray(fractions) ? fractions : [];
  const n = list.length;
  const c = RADAR.centre;
  const out = {
    size: RADAR.size, center: { x: c, y: c }, radius: RADAR.radius, rings: ringRadii(),
    fractions: list.map((f) => (typeof f === "number" && Number.isFinite(f)
      ? Math.min(1, Math.max(0, f)) : null)),
    spokes: [], polygon: [], labels: [],
  };
  for (let i = 0; i < n; i += 1) {
    const angle = (-90 + (i * 360) / n) * (Math.PI / 180);
    const cs = Math.cos(angle);
    const sn = Math.sin(angle);
    const f = out.fractions[i];
    out.spokes.push({ x: r2(c + RADAR.radius * cs), y: r2(c + RADAR.radius * sn) });
    out.polygon.push(f === null
      ? { x: c, y: c, dot: true }
      : { x: r2(c + RADAR.radius * f * cs), y: r2(c + RADAR.radius * f * sn), dot: false });
    const dy = sn > 0.3 ? 10 : (sn < -0.3 ? 0 : 4);
    out.labels.push({
      x: r2(c + RADAR.labelRadius * cs),
      y: r2(c + RADAR.labelRadius * sn + dy),
      anchor: Math.abs(cs) < 0.2 ? "middle" : (cs > 0 ? "start" : "end"),
    });
  }
  return out;
}

/** The shape's corners as an SVG attribute value. */
export function polygonAttr(geometry) {
  return geometry.polygon.map((p) => `${p.x},${p.y}`).join(" ");
}

/* ── Reading the PC's answers ─────────────────────────────────────────── */

/** `GET /api/progress/activity`. A missing key gets its empty value. */
export function readActivity(raw) {
  const a = raw && typeof raw === "object" ? raw : {};
  const days = (Array.isArray(a.days) ? a.days : []).map((d) => ({
    date: text(d && d.date),
    col: Math.max(0, Math.trunc(num(d && d.col))),
    row: Math.min(6, Math.max(0, Math.trunc(num(d && d.row)))),
    count: Math.max(0, Math.trunc(num(d && d.count))),
    level: Math.min(4, Math.max(0, Math.trunc(num(d && d.level)))),
    words: text(d && d.words),
  }));
  const weeks = Math.max(1, Math.trunc(num(a.weeks, LIMITS.weeks_default)));
  return {
    available: a.available !== false,
    hidden: a.hidden === true,
    title: text(a.title) || WORDS.heat_title,
    weeks,
    columns: (Array.isArray(a.columns) ? a.columns : []).map((c, i) => ({
      col: Math.trunc(num(c && c.col, i)), label: text(c && c.label),
    })),
    days,
    total: Math.max(0, Math.trunc(num(a.total))),
    daysActive: Math.max(0, Math.trunc(num(a.days_active))),
    empty: a.empty === true,
    words: text(a.words),
    note: text(a.note) || WORDS.heat_undated,
    summary: text(a.summary),
    levels: Array.isArray(a.levels) ? a.levels : [],
    keepOnScreen: a.keep_on_screen === true,
    hiddenWords: text(a.hidden_words) || WORDS.hidden,
  };
}

const STATES = ["progress", "reached", "no_numbers", "no_target", "no_steps"];

/** `GET`/`POST /api/progress/balance`. */
export function readBalance(raw) {
  const b = raw && typeof raw === "object" ? raw : {};
  const axes = (Array.isArray(b.axes) ? b.axes : []).map((a) => {
    const fraction = a && typeof a.fraction === "number" && Number.isFinite(a.fraction)
      ? Math.min(1, Math.max(0, a.fraction)) : null;
    const state = STATES.includes(a && a.state) ? a.state : "progress";
    return {
      label: text(a && a.label), short: text(a && a.short) || text(a && a.label),
      name: text(a && a.name), kind: a && a.kind === "goal" ? "goal" : "bench",
      ref: text(a && a.ref), project: text(a && a.project), state,
      valueWords: text(a && a.value_words), fraction,
      keepOnScreen: Boolean(a && a.keep_on_screen === true),
    };
  });
  const choices = (Array.isArray(b.choices) ? b.choices : []).map((c) => ({
    kind: c && c.kind === "goal" ? "goal" : "bench",
    ref: text(c && c.ref), project: text(c && c.project), projectName: text(c && c.project_name),
    name: text(c && c.name), picked: Boolean(c && c.picked === true),
    keepOnScreen: Boolean(c && c.keep_on_screen === true),
    hidden: Boolean(c && c.hidden === true),
  }));
  return {
    available: b.available !== false,
    hidden: b.hidden === true,
    title: text(b.title) || WORDS.balance_title,
    axes,
    drawable: b.drawable === true,
    min: Math.trunc(num(b.min, LIMITS.axes_min)),
    max: Math.trunc(num(b.max, LIMITS.axes_max)),
    maxLabel: Math.trunc(num(b.max_label, LIMITS.label_max)),
    words: text(b.words),
    summary: text(b.summary),
    choices,
    keepOnScreen: b.keep_on_screen === true,
    hiddenWords: text(b.hidden_words) || WORDS.hidden,
  };
}

/* ── Screen-reader text ───────────────────────────────────────────────── */

/**
 * The heatmap as a week-per-row table: `[{label, cells: [words x 7 at most]}]`.
 * Cells run Monday to Sunday; a day after today has no cell (the answer has
 * none), so the last row may be short.
 */
export function heatRows(activity) {
  const a = activity || readActivity(null);
  const rows = (a.columns.length ? a.columns : []).map((c) => ({ col: c.col, label: c.label, cells: [] }));
  const byCol = new Map(rows.map((r) => [r.col, r]));
  for (const d of a.days) {
    const row = byCol.get(d.col);
    if (row) row.cells[d.row] = d.words;
  }
  return rows.map((r) => ({
    label: r.label,
    // A day the PC did not send (one after today) has no cell, never a made-up one.
    cells: Array.from(r.cells, (w) => w || ""),
  }));
}

/** A day's words, or the day's date when the PC sent none. */
export function dayWords(day) {
  return text(day && day.words);
}

/**
 * The list under the balance picture: one row per area, in the order sent -
 * never sorted, ranked or totalled. A private area is flagged in small type.
 * `text` is what a screen reader hears: "<label>: <value words>", and a
 * `no_numbers` row "<label>: no numbers yet".
 */
export function balanceList(balance) {
  const b = balance || readBalance(null);
  return b.axes.map((a) => {
    const value = a.valueWords || (a.state === "no_numbers" ? WORDS.no_numbers
      : a.state === "no_target" ? WORDS.no_target
        : a.state === "no_steps" ? WORDS.no_steps : "");
    return {
      label: a.label,
      value,
      private: a.keepOnScreen,
      text: value ? `${a.label}: ${value}` : a.label,
    };
  });
}

/** Whether a picker can add one more (the 9th is disabled). */
export function canPickMore(pickedCount, max = LIMITS.axes_max) {
  return pickedCount < max;
}

/** Whether Save is enabled: 3 to 8 ticked, or none (that clears the chart). */
export function saveState(pickedCount, min = LIMITS.axes_min, max = LIMITS.axes_max) {
  if (pickedCount === 0) return "clear";
  return pickedCount >= min && pickedCount <= max ? "save" : "off";
}

/**
 * The body of the save from the picker's ticks: in the order the rows are
 * listed, each with its typed name only if it differs from the row's name.
 */
export function pickBody(rows) {
  return (Array.isArray(rows) ? rows : [])
    .filter((r) => r && r.picked)
    .map((r) => {
      const one = { kind: r.kind, ref: r.ref };
      const label = text(r.label).trim();
      if (label && label !== r.name) one.label = label;
      return one;
    });
}
