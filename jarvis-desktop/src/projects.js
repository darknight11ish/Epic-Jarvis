/**
 * Projects (the owner's decision of 2026-09-28, "Projects, like Claude's
 * Projects and more"; docs/PROJECTS-DESIGN.md build step 3; JARVIS-API.md
 * section 88; backend jarvis_projects.py) - the words, and how to read what
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

/**
 * The words of the "App" section (docs/APPS-IN-PROJECTS-DESIGN.md sections 1,
 * 2, 3 and 5), kept apart from WORDS on purpose: WORDS is compared word for
 * word with the shared contract file and the phone. When the backend's
 * fixture carries these, point the test at it. The sentences that say how a
 * merge ended are NOT here: the PC sends them (`app.merge.last.message`) and
 * this page shows them as they come.
 */
export const APP_WORDS = {
  section: "App",
  type_web: "Web app",
  type_android: "Android app (native)",
  files_where: "Files: kept on this PC in Jarvis's apps folder.",
  only_here: "This app's files are only on this PC.",
  latest_version: "Latest version: {subject}, {date}",
  versions: "{count} saved versions",
  version_one: "1 saved version",
  no_versions: "No saved version yet.",
  tasks: "Open tasks",
  tasks_empty: "No open tasks. A task is one change to the app that you look at first, then add or throw away.",
  task_files: "{files} files, +{added} -{removed}",
  task_files_one: "1 file, +{added} -{removed}",
  task_nothing: "Nothing in it yet",
  task_older: "made before another change - may not fit",
  task_waiting: "waiting for your card",
  task_open: "Open task",
  start_task: "Start a task",
  start_title: "What is the change?",
  start_under: "Starting a task only makes an empty copy of the app to work in. Nothing runs and your app is not touched.",
  git_missing: "This PC has no git, so the app's saved versions cannot be shown.",
  back_project: "Back to the project",
  task_files_title: "Files in this change",
  task_diff_title: "The whole change",
  task_diff_under: "Green lines are added, red lines are removed. This is everything that will be added to your app.",
  task_diff_empty: "Nothing to show yet.",
  merge: "Merge",
  merge_how: "Approve the card that appears - it needs Windows Hello.",
  merge_pasted: "You pasted this change in on your PC.",
  merge_blocked_card: "A card for this app is already waiting - answer it first.",
  discard: "Discard",
  discard_q: "Throw this change away? It has not been added to your app. Nothing in your app changes.",
  discard_waiting_q: "Throw this change away? The approval card waiting for it is withdrawn. Nothing in your app changes.",
  paste: "Paste a change in",
  paste_under: "Blocks that start with <<<FILE folder/name.txt>>> and end with <<<END>>>, or <<<DELETE folder/name.txt>>> to remove a file. They land only in this task - nothing reaches your app until you approve the merge card. On your PC only.",
  paste_button: "Add to this task",
  paste_empty: "Paste the change first.",
  new_app: "An app Jarvis builds",
  new_app_web: "An app Jarvis builds - web",
  new_app_android: "An app Jarvis builds - native Android",
  adopt_title: "Add an app I already have",
  adopt_under: "These app folders are already in Jarvis's apps folder but have no project. Adding one only links it - nothing runs.",
  adopt: "Add",
  cant_run: "Jarvis cannot run this yet. Run it yourself and log the number.",
  delete_app_project_q: "Delete the project \"{name}\"? Its benchmarks and every number logged go with it. The app's files stay on this PC and can be added back later. This cannot be undone.",
  deleted_app_kept: "Deleted. The app's files stay on this PC and can be added back.",
  app_project: "App",
  open_tasks_meta: "{count} open",
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
    app: o.app && typeof o.app === "object" ? readApp(o.app) : null,
    workList: wl ? { name: text(wl.name), title: text(wl.title) || text(wl.name) } : null,
    benchmarks: Number.isInteger(o.benchmarks) ? o.benchmarks : 0,
    benchList: Array.isArray(o.benchmark_list) ? o.benchmark_list.map(readBench) : [],
    max: o.max && typeof o.max === "object" ? o.max : {},
  };
}

const OUTCOMES = ["merged", "denied", "timed_out", "stale", "unsaved", "conflict",
  "withdrawn", "refused", "failed"];

/** A task in the list (design 7.1 "task summary"). */
export function readTaskSummary(t) {
  const o = t && typeof t === "object" ? t : {};
  const n = (v) => (Number.isFinite(Number(v)) && Number(v) >= 0 ? Number(v) : 0);
  return {
    task: text(o.task),
    title: text(o.title),
    started: num(o.started),
    source: o.source === "jarvis" || o.source === "pasted" ? o.source : "empty",
    files: n(o.files),
    added: n(o.added),
    removed: n(o.removed),
    olderMain: o.older_main === true,
    waiting: o.waiting === true,
  };
}

/**
 * One task with its whole change (`GET .../app/tasks/<task>`, or the answer to
 * pasting into it). `diff` is the whole text, never cut: it is shown as text
 * and never stored or logged by this page.
 */
export function readTask(answer) {
  const t = answer && typeof answer === "object" && answer.task && typeof answer.task === "object"
    ? answer.task : answer;
  const o = t && typeof t === "object" ? t : {};
  return {
    ...readTaskSummary(o),
    list: Array.isArray(o.list)
      ? o.list.filter((f) => f && text(f.path)).map((f) => ({
        path: text(f.path), added: text(f.added), removed: text(f.removed) }))
      : [],
    diff: text(o.diff),
    tooBig: o.too_big === true,
    refused: text(o.refused),
  };
}

/**
 * A project's `app`: the full object (tasks is an array, `main`, `merge`) or
 * the list's short one (`tasks` is a number, `merge_waiting`). Never trusts a
 * shape it was not given.
 */
export function readApp(a) {
  const o = a && typeof a === "object" ? a : null;
  if (!o) return null;
  const main = o.main && typeof o.main === "object" ? o.main : null;
  const merge = o.merge && typeof o.merge === "object" ? o.merge : {};
  const last = merge.last && typeof merge.last === "object" ? merge.last : null;
  const full = Array.isArray(o.tasks);
  const waiting = full ? text(merge.waiting) : (o.merge_waiting === true ? "yes" : "");
  return {
    full,
    name: text(o.name),
    type: o.type === "android" ? "android" : "web",
    title: text(o.title),
    gitOk: o.git_ok !== false,
    said: text(o.said),
    main: main ? {
      head: text(main.head), subject: text(main.subject), at: num(main.at),
      versions: Number.isInteger(main.versions) ? main.versions : 0 } : null,
    tasks: full ? o.tasks.map(readTaskSummary).filter((t) => t.task) : [],
    taskCount: full ? o.tasks.length : (Number.isInteger(o.tasks) ? o.tasks : 0),
    mergeWaiting: waiting,
    last: last ? {
      task: text(last.task),
      outcome: OUTCOMES.includes(last.outcome) ? last.outcome : "failed",
      message: text(last.message), at: num(last.at) } : null,
  };
}

/** GET /api/projects: the app folders that have no project yet. */
export function readUnlinked(answer) {
  const a = answer && Array.isArray(answer.unlinked_apps) ? answer.unlinked_apps : [];
  return a.filter((x) => x && text(x.name)).map((x) => ({
    name: text(x.name), type: x.type === "android" ? "android" : "web",
    title: text(x.title) || text(x.name) }));
}

/** "Web app" or "Android app (native)". */
export function appTypeWords(type) {
  return type === "android" ? APP_WORDS.type_android : APP_WORDS.type_web;
}

/** "3 files, +41 -2" for a task row. */
export function taskChange(t) {
  if (!t.files) return APP_WORDS.task_nothing;
  return fill(t.files === 1 ? APP_WORDS.task_files_one : APP_WORDS.task_files,
    { files: t.files, added: t.added, removed: t.removed });
}

/** "Latest version: Jarvis: Add a dark mode, 3 Oct" and "7 saved versions". */
export function versionLines(app) {
  if (!app.gitOk) return [app.said || APP_WORDS.git_missing];
  if (!app.main || !app.main.head) return [APP_WORDS.no_versions];
  const n = app.main.versions;
  return [
    fill(APP_WORDS.latest_version, { subject: app.main.subject, date: shortDate(app.main.at) }),
    n === 1 ? APP_WORDS.version_one : fill(APP_WORDS.versions, { count: n }),
  ];
}

/**
 * What Merge does for one task, as data: `{ok: true}`, or `{ok: false, why}`
 * with a plain sentence (also what greys the button). A change that cannot be
 * shown whole raises no card, so it is told why here instead.
 */
export function mergeOffer(app, t) {
  if (t.waiting || app.mergeWaiting === t.task) return { ok: false, why: WORDS.waiting_card, waiting: true };
  if (app.mergeWaiting) return { ok: false, why: APP_WORDS.merge_blocked_card };
  if (t.refused) return { ok: false, why: t.refused };
  return { ok: true, why: "" };
}

/** Which lines of a diff are added, removed, a hunk mark or a file header. */
export function diffLineKind(line) {
  if (line.startsWith("+++") || line.startsWith("---") || line.startsWith("diff ")
    || line.startsWith("index ") || line.startsWith("new file") || line.startsWith("deleted file")) return "meta";
  if (line.startsWith("@@")) return "hunk";
  if (line.startsWith("+")) return "add";
  if (line.startsWith("-")) return "del";
  return "ctx";
}

/** The body for "Start a task", or an error sentence. The PC checks it again. */
export function taskTitleBody(raw) {
  const title = String(raw || "").trim();
  if (!title) return { error: "Give the task a title." };
  if ([...title].length > 120) return { error: "A task title is at most 120 characters." };
  return { body: { title } };
}

/**
 * The body for pasting a change in, or an error sentence. Whether there are
 * real <<<FILE>>> blocks in it is the PC's to say - it does.
 */
export function pasteBody(raw) {
  const blocks = String(raw || "");
  if (!blocks.trim()) return { error: APP_WORDS.paste_empty };
  if ([...blocks].length > 2000000) return { error: "That paste is too big - split it into smaller changes." };
  return { body: { blocks } };
}

/**
 * The body for a new project that is an app: `choice` is "app-web",
 * "app-android" or "adopt:<folder>"; null for anything else.
 */
export function appProjectBody(name, choice) {
  const c = String(choice || "");
  if (c === "app-web" || c === "app-android") {
    return { name: String(name || "").trim(), kind: "coding",
      app: { type: c === "app-android" ? "android" : "web" } };
  }
  if (c.startsWith("adopt:")) return { kind: "coding", app: { adopt: c.slice(6) } };
  return null;
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
    unlinked: readUnlinked(answer),
    hidden: false,
    hiddenCount: 0,
    empty: text(answer.empty),
    max: Number.isInteger(answer.max) ? answer.max : 30,
  };
}

/** The lines under a project's name in the list. */
export function projectMeta(p) {
  const kind = p.app ? APP_WORDS.app_project : (p.kind === "coding" ? WORDS.coding : WORDS.life);
  const n = p.benchmarks;
  const lines = [`${kind} · ${n} ${n === 1 ? "benchmark" : "benchmarks"}`];
  if (p.app) {
    const bits = [];
    if (p.app.taskCount) bits.push(fill(APP_WORDS.open_tasks_meta, { count: p.app.taskCount }));
    if (p.app.mergeWaiting) bits.push(APP_WORDS.task_waiting);
    if (bits.length) lines.push(`${APP_WORDS.app_project} · ${bits.join(" · ")}`);
  }
  return lines;
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
