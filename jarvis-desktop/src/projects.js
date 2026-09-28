/**
 * Projects (the owner's decision of 2026-09-28, "Projects, like Claude's
 * Projects and more"; docs/PROJECTS-DESIGN.md build step 3; JARVIS-API.md
 * section 61; backend jarvis_projects.py) - the words, and how to read what
 * the PC sends. No DOM: projects-panel.js draws it.
 *
 * The phone says the same words (net/Projects.kt). Both apps are tested
 * against one contract file, tests/fixtures/projects-cases.json, made by
 * tools/gen_projects_cases.py from the real backend: its `words` are these,
 * word for word; its `numbers` are how the PC writes a number with its
 * unit; its `scales` are where a chart's bottom and top go.
 *
 * What asks first (the PC decides, never this page): Shareable ON, and
 * taking off a private mark Jarvis made by itself - one approval card each.
 * Everything else is the owner writing down their own things, no card.
 *
 * @module projects
 */

/** The screens' own words. Keep in step with the contract file. */
export const WORDS = {
  title: "Projects",
  under: "One place for each thing you are working on - an app, or a goal like a half marathon: how Jarvis should help, your notes, and numbers you track. Kept on your PC.",
  new: "New project",
  name: "Name",
  kind_life: "Life - numbers you track",
  kind_coding: "Coding - a folder on your PC",
  create: "Create",
  coding_on_pc: "A coding project's folder is chosen on your PC. Make coding projects there.",
  set_on_pc: "Set on your PC",
  instructions: "How Jarvis should work on this",
  instructions_under: "In your own words. Jarvis reads this in this project's chats.",
  notes: "Project notes",
  notes_under: "Short lines to keep in mind for this project, one per line.",
  save: "Save",
  folder: "Folder",
  folder_none: "No folder yet.",
  folder_choose: "Choose a folder…",
  folder_clear: "Clear",
  folder_under: "Only a folder on \"Folders Jarvis may look in\" (Settings), or one inside it.",
  shareable: "Shareable",
  shareable_under: "Off by default: nothing from this project is shared. Turning it on asks you with an approval card first; turning it off is instant.",
  work_list: "Work list",
  work_list_none: "No work list.",
  work_list_under: "A named list in Coming up. Add to it there, or say \"add ... to the {name}\".",
  benchmarks: "Benchmarks",
  benchmarks_empty: "No benchmarks yet. Add one to track a number over time.",
  add_benchmark: "Add a benchmark",
  bench_name: "What you measure",
  bench_unit: "Unit (optional)",
  bench_better: "Better is",
  better_higher: "Higher",
  better_lower: "Lower",
  better_either: "Don't say",
  bench_target: "Target (optional)",
  add: "Add",
  log: "Log",
  log_value: "A number",
  private_label: "private - not read aloud",
  mark_private: "Mark private",
  remove_mark: "Remove the private mark",
  remove_mark_card: "Jarvis marked this itself. Removing the mark asks you with an approval card first, because afterwards its numbers may be read aloud.",
  remove_mark_yours: "You marked this. Removing your mark is instant.",
  waiting_card: "Waiting for your yes on the approval card.",
  chart_empty: "No numbers yet - log the first one.",
  chart_target: "Target",
  chart_summary: "{count} numbers. Latest: {latest}.",
  latest: "Latest",
  remove_number: "Remove this number",
  delete_project: "Delete project",
  delete_project_q: "Delete the project \"{name}\"? Its benchmarks and every number logged go with it. This cannot be undone.",
  delete_bench: "Delete benchmark",
  delete_bench_q: "Delete the benchmark \"{name}\" and every number logged for it? This cannot be undone.",
  delete_yes: "Delete",
  delete_no: "Keep it",
  command_on_pc: "A benchmark's command is written and changed on your PC.",
  missing: "Your PC's Jarvis does not have Projects yet - run apply-patches.ps1 on the PC.",
  stale: "The connection to Jarvis is catching up, so nothing can be sent until it does.",
  back: "All projects",
  open: "Open",
  life: "Life",
  coding: "Coding",
};

/** `{name}` and friends filled in. */
export function fill(template, values) {
  return String(template).replace(/\{(\w+)\}/g, (m, k) =>
    (values && Object.prototype.hasOwnProperty.call(values, k) ? String(values[k]) : m));
}

function text(v) {
  return typeof v === "string" ? v : "";
}

function num(v) {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

/**
 * A number the way the PC writes it (jarvis_projects._num_words): a whole
 * number without a point, otherwise at most four places with the trailing
 * zeros taken off. 5 -> "5", 72.5 -> "72.5", 0.125 -> "0.125".
 */
export function numberWords(v) {
  const n = Number(v);
  if (!Number.isFinite(n)) return "";
  if (Number.isInteger(n)) return String(n);
  return n.toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
}

/** With its unit, as the PC says it (`_with_unit`): "5 km", "$200", "12.5%". */
export function withUnit(v, unit) {
  const n = numberWords(v);
  const u = text(unit);
  if (!u) return n;
  if (u === "$" || u === "£" || u === "€") return `${u}${n}`;
  if (u === "%") return `${n}%`;
  return `${n} ${u}`;
}

/**
 * Where the chart's bottom and top are ([lo, hi], lo < hi): every value and
 * the target fit, with a tenth of the range spare each way; one value (or all
 * the same) gets one unit of room each way, or a tenth of its size when that
 * is bigger. The same as tools/gen_projects_cases.py's `chart_scale`.
 */
export function chartScale(values, target = null) {
  const pool = (values || []).map(Number).filter(Number.isFinite);
  if (target !== null && target !== undefined && Number.isFinite(Number(target))) {
    pool.push(Number(target));
  }
  if (!pool.length) return [0, 1];
  const lo = Math.min(...pool);
  const hi = Math.max(...pool);
  if (hi - lo < 1e-9) {
    const room = Math.max(1, Math.abs(lo) * 0.1);
    return [lo - room, hi + room];
  }
  const pad = (hi - lo) * 0.1;
  return [lo - pad, hi + pad];
}

/**
 * The chart's drawing, as numbers only: each point's x and y inside a box
 * `width` by `height` (y grows downward, as in SVG), and the target line's
 * y, or null. Points are placed by their date: the first on the left, the
 * newest on the right; one point sits in the middle.
 */
export function chartGeometry(points, target, width, height, inset = 8) {
  const pts = (points || []).filter((p) => num(p.at) !== null && num(p.value) !== null);
  const [lo, hi] = chartScale(pts.map((p) => p.value), target);
  const w = width - inset * 2;
  const h = height - inset * 2;
  const y = (v) => inset + h - ((v - lo) / (hi - lo)) * h;
  const first = pts.length ? pts[0].at : 0;
  const last = pts.length ? pts[pts.length - 1].at : 0;
  const span = last - first;
  const xy = pts.map((p) => ({
    id: text(p.id),
    at: p.at,
    value: p.value,
    x: span > 0 ? inset + ((p.at - first) / span) * w : inset + w / 2,
    y: y(p.value),
  }));
  const t = target !== null && target !== undefined && Number.isFinite(Number(target))
    ? y(Number(target)) : null;
  return { points: xy, target: t, lo, hi };
}

/** "3 numbers. Latest: 12 km." - the chart's words for a screen reader. */
export function chartSummary(bench) {
  const count = Number(bench.results) || (bench.points ? bench.points.length : 0);
  if (!count || !bench.latest) return WORDS.chart_empty;
  return fill(WORDS.chart_summary, { count, latest: withUnit(bench.latest.value, bench.unit) });
}

/** One benchmark, from the PC's `view`. */
export function readBench(b) {
  const o = b && typeof b === "object" ? b : {};
  const change = o.change && typeof o.change === "object" ? o.change : null;
  return {
    id: text(o.id),
    name: text(o.name),
    kind: o.kind === "command" ? "command" : "number",
    unit: text(o.unit),
    better: o.better === "higher" || o.better === "lower" ? o.better : null,
    target: num(o.target),
    sensitive: o.sensitive === true,
    keepOnScreen: o.keep_on_screen === true || o.sensitive === true,
    keepOnScreenWords: text(o.keep_on_screen_words),
    markedByYou: o.marked_by_you === true,
    unmark: o.unmark === "card" || o.unmark === "instant" ? o.unmark : "",
    unmarkWaiting: o.unmark_waiting === true,
    unmarkLast: o.unmark_last && typeof o.unmark_last === "object" ? text(o.unmark_last.message) : "",
    results: Number.isInteger(o.results) ? o.results : 0,
    latest: o.latest && num(o.latest.value) !== null
      ? { id: text(o.latest.id), value: o.latest.value, at: num(o.latest.at) } : null,
    said: change ? text(change.said) : "",
    verdict: change ? text(change.verdict) : "",
    targetReached: change ? change.target_reached === true : false,
    command: text(o.command),
    runnable: o.runnable === true,
    notRunnableWhy: text(o.not_runnable_why),
    points: Array.isArray(o.points)
      ? o.points.filter((p) => p && num(p.value) !== null && num(p.at) !== null)
        .map((p) => ({ id: text(p.id), at: p.at, value: p.value }))
      : null,
  };
}

/** One project, from the PC's `full` (or the list's `summary`). */
export function readProject(p) {
  const o = p && typeof p === "object" ? p : {};
  const folder = o.folder && typeof o.folder === "object" ? o.folder : null;
  const wl = o.work_list && typeof o.work_list === "object" ? o.work_list : null;
  const last = o.shareable_last && typeof o.shareable_last === "object" ? o.shareable_last : null;
  return {
    id: text(o.id),
    name: text(o.name),
    kind: o.kind === "coding" ? "coding" : "life",
    instructions: text(o.instructions),
    notes: Array.isArray(o.notes) ? o.notes.filter((n) => typeof n === "string") : [],
    folder: folder ? { path: text(folder.path), name: text(folder.name) || text(folder.path),
      listed: folder.listed !== false, said: text(folder.said) } : null,
    shareable: o.shareable === true,
    shareableWaiting: o.shareable_waiting === true,
    shareableLast: last ? text(last.message) : "",
    workList: wl ? { name: text(wl.name), title: text(wl.title) || text(wl.name) } : null,
    benchmarks: Number.isInteger(o.benchmarks) ? o.benchmarks : 0,
    benchList: Array.isArray(o.benchmark_list) ? o.benchmark_list.map(readBench) : [],
    max: o.max && typeof o.max === "object" ? o.max : {},
  };
}

/**
 * GET /api/projects, read. `available: false` with the reason for a PC
 * without Projects; `hidden: true` while the private lists are hidden
 * (Rust took the projects out, and kept only how many).
 */
export function readList(answer) {
  if (!answer || typeof answer !== "object" || answer.available === false) {
    const why = answer && text(answer.why).trim() ? text(answer.why).trim() : WORDS.missing;
    return { available: false, why, projects: [], hidden: false, hiddenCount: 0, max: 30 };
  }
  if (answer.hidden === true) {
    return { available: true, why: "", projects: [], hidden: true,
      hiddenCount: Number(answer.hidden_count) || 0, max: 30 };
  }
  return {
    available: true,
    why: "",
    projects: Array.isArray(answer.projects) ? answer.projects.map(readProject).filter((p) => p.id) : [],
    hidden: false,
    hiddenCount: 0,
    empty: text(answer.empty),
    max: Number.isInteger(answer.max) ? answer.max : 30,
  };
}

/** The lines under a project's name in the list. */
export function projectMeta(p) {
  const kind = p.kind === "coding" ? WORDS.coding : WORDS.life;
  const n = p.benchmarks;
  return [`${kind} · ${n} ${n === 1 ? "benchmark" : "benchmarks"}`];
}

/** The body of the notes box: one line per note, blanks dropped. */
export function notesFrom(textarea) {
  return String(textarea || "").split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
}

/**
 * What the private-mark button does for one benchmark, or null when it has
 * none: "card" (Jarvis's own mark - the PC asks with a card first) or
 * "instant" (only the owner's own mark). Never offered while a card waits.
 */
export function unmarkOffer(b) {
  if (!b.keepOnScreen || !b.unmark || b.unmarkWaiting) return null;
  return {
    kind: b.unmark,
    label: WORDS.remove_mark,
    why: b.unmark === "card" ? WORDS.remove_mark_card : WORDS.remove_mark_yours,
  };
}

/**
 * The body for "Add a benchmark", or an error sentence. A number: name,
 * unit, which way is better, a target. A command (a coding project, on the
 * PC): its words too.
 */
export function benchBody({ name, unit, better, target, kind, command }) {
  const body = { name: String(name || "").trim(), kind: kind === "command" ? "command" : "number" };
  if (!body.name) return { error: "Give the benchmark a name." };
  if (String(unit || "").trim()) body.unit = String(unit).trim();
  if (better === "higher" || better === "lower") body.better = better;
  const t = String(target ?? "").trim();
  if (t) {
    const v = Number(t.replace(",", "."));
    if (!Number.isFinite(v)) return { error: "The target is a number, like 21.1." };
    body.target = v;
  }
  if (body.kind === "command") {
    const c = String(command || "").trim();
    if (!c) return { error: "Write the command, like: pytest -q" };
    body.command = c;
  }
  return { body };
}

/** A logged value from the box: a number, or null. "72,5" is 72.5. */
export function valueFrom(raw) {
  const t = String(raw ?? "").trim().replace(",", ".");
  if (!t) return null;
  const v = Number(t);
  return Number.isFinite(v) ? v : null;
}

/** A date for a chart point or a logged number: "3 Oct". */
export function shortDate(at) {
  const d = new Date(Number(at) * 1000);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}
