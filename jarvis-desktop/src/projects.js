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
  instructions_under: "In your own words. Saved for later: Jarvis does not read this in chats yet.",
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

/**
 * The plan board's own words (PM4, 2026-11-21): the four Kanban columns, the
 * Ready List, the milestone bar, the blocker badges, the card's detail and the
 * one-click hub note. Kept apart from [`WORDS`] on purpose, and for the same
 * reason [`APP_WORDS`] is: WORDS is the phone's frozen step-3 contract, word
 * for word (tools/gen_projects_cases.py), and this board is the desktop's
 * first reader of a route the phone PR adds in the same wave
 * (docs/ARCHITECTURE.md section 8 says which half is deliberately one-sided).
 * `{name}` and friends are filled in by [`fill`].
 */
export const PLAN_WORDS = {
  board: "Project plan",
  project: "Project",
  all_projects: "All projects",
  under: "The plan Jarvis keeps for this project: the steps that are ready now, every step by its stage, the milestones, and the activity log. Read from your PC; nothing here is guessed.",
  missing: "Your PC's Jarvis cannot show a project's plan yet - update it by running apply-patches.ps1 on the PC.",
  hidden: "The plan is hidden until Windows Hello confirms it is you.",
  reading: "Reading the plan…",
  export: "Export hub note to Obsidian",
  export_title: "Writes one read-only copy of this project into your Obsidian vault. It asks you with one approval card first, and no benchmark number ever goes into the note.",
  export_missing: "Your PC's Jarvis cannot write a project's hub note yet - update it by running apply-patches.ps1 on the PC.",
  export_waiting: "Waiting for your approval card.",
  export_more: "The note is rebuilt from this project every time, and it is never read back.",
  ready: "Ready now",
  ready_under: "The steps that can be started now, in the order your PC keeps them.",
  ready_empty: "Nothing is ready to start right now.",
  ready_more: "{count} more ready steps are not shown here - switch to the full plan to see them.",
  ready_open: "Open ready item: {title}",
  milestones: "Milestones",
  milestones_empty: "No milestones yet.",
  progress: "Milestone progress",
  progress_work: "{done} of {total} work items done",
  progress_milestones: "{done} of {total} milestones done",
  progress_none: "No work items yet.",
  milestone_work: "{done} of {total}",
  column_planning: "Planning",
  column_progress: "In Progress",
  column_review: "In Review / Waiting",
  column_done: "Done",
  column_empty: "Nothing here.",
  item_open: "Open work item: {title}",
  blocked_by: "Blocked by {names}",
  blocked_by_one: "Blocked by {name}",
  milestone: "Milestone: {name}",
  due: "Due {date}",
  objective: "Objective",
  objective_none: "No objective is set for this project yet.",
  success: "Done looks like",
  waiting_on: "Waiting on",
  waiting_none: "No blockers are recorded for this card.",
  blocks: "Blocks",
  blocks_none: "Nothing is recorded as waiting on this card.",
  linked: "Linked pull request or note",
  linked_none: "No pull request or note is linked yet.",
  linked_pr: "Pull request #{number} - {state}{checks}",
  linked_checks: ", {words}",
  linked_note: "Note: {path}",
  linked_repo: "Repository: {repo}",
  activity: "Activity",
  activity_none: "Nothing is recorded for this card yet.",
  moves: "Move this card to",
  move_start: "Start it",
  move_review: "In review",
  move_done: "Done",
  move_reopen: "Reopen",
  moved: "Moved.",
  move_refused: "The PC refused the move.",
  add_item: "Add a work item",
  add_title: "A new work item",
  add_empty: "Give the work item a title.",
  add_long: "A work item title is at most 120 characters.",
  added: "Added.",
  close: "Close",
  status_backlog: "Planning",
  status_ready: "Ready",
  status_in_progress: "In progress",
  status_waiting_approval: "Waiting for approval",
  status_in_review: "In review",
  status_done: "Done",
  status_cancelled: "Cancelled",
  milestone_planned: "Planned",
  milestone_active: "In progress",
  milestone_done: "Done",
  pr_open: "open",
  pr_merged: "merged",
  pr_closed: "closed",
  ci_green: "checks green",
  ci_running: "checks running",
  ci_failed: "checks failed",
  ci_unknown: "checks unknown",
  executor: "Who does it: {who}",
  executor_owner: "you",
  executor_jarvis_local: "Jarvis, on this PC",
  executor_jarvis_cloud: "Jarvis, in the cloud",
  executor_jarvis_job: "a Jarvis job",
};

/** What each kind of `project_events` row is, in words (an unknown kind shows its own name). */
export const PLAN_EVENT_WORDS = {
  work_item_added: "Work item added",
  work_item_status: "Status changed",
  milestone_added: "Milestone added",
  project_plan_changed: "Project fields changed",
  edge_added: "Dependency added",
  work_item_link: "Linked to a job or pull request",
  pr_synced: "Pull request read",
  pr_merged_offer: "Pull request merged - offered as done",
  plan_seeded: "Imported from goals and work lists",
  checkpoint: "Checkpoint",
  reflection: "Reflection",
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
 * The forecast the PC sends with a benchmark read (`benchmark.forecast`,
 * JARVIS-API section 101.4), read with defaults; null when there is none
 * (a read without `points`, or an older PC) or its state is not one of the
 * six. `words` and `basis` are kept exactly as sent - this page never
 * builds them. `line` and `band` are the finished drawing points.
 */
export const FORECAST_STATES = Object.freeze(
  ["no_target", "reached", "not_enough", "range", "open_ended", "never"]);

export function readForecast(f) {
  const o = f && typeof f === "object" ? f : null;
  if (!o || !FORECAST_STATES.includes(o.state)) return null;
  const pt = (p) => (p && typeof p === "object" && num(p.at) !== null && num(p.value) !== null
    ? { at: p.at, value: p.value } : null);
  const line = o.line && typeof o.line === "object" ? (() => {
    const from = pt(o.line.from);
    const to = pt(o.line.to);
    return from && to ? { from, to, clipped: o.line.clipped === true } : null;
  })() : null;
  const band = o.band && typeof o.band === "object" ? (() => {
    const from = pt(o.band.from);
    const fast = pt(o.band.fast);
    const slow = pt(o.band.slow);
    return from && fast && slow ? {
      from,
      fast: { ...fast, clipped: o.band.fast.clipped === true },
      slow: { ...slow, clipped: o.band.slow.clipped === true, open: o.band.slow.open === true },
    } : null;
  })() : null;
  const drawn = line && band ? { line, band } : { line: null, band: null };
  return {
    state: o.state,
    words: text(o.words),
    basis: text(o.basis),
    lowWeeks: num(o.low_weeks),
    highWeeks: num(o.high_weeks),
    overTwoYears: o.over_two_years === true,
    why: text(o.why),
    used: num(o.used) || 0,
    needed: num(o.needed) || 0,
    firstAt: num(o.first_at),
    lastAt: num(o.last_at),
    horizonAt: num(o.horizon_at),
    crossLowAt: num(o.cross_low_at),
    crossAt: num(o.cross_at),
    crossHighAt: num(o.cross_high_at),
    ...drawn,
  };
}

/**
 * Where the chart's edges are once a forecast is drawn: x runs from the
 * first number to the last number or the farthest end of the dashed line
 * and band; y is `chartScale` over the numbers, the target, and the
 * forecast's own values (line start and end, the band's three corners).
 * A forecast without a line changes nothing. The same as
 * tools/gen_projects_cases.py's `forecast_extent` (`forecast_cases[*].extent`).
 * `points` are {at, value}; `f` is a `readForecast` answer or null.
 */
export function forecastExtent(points, f, target = null) {
  const pts = (points || []).filter((p) => num(p.at) !== null && num(p.value) !== null);
  const xs = pts.map((p) => p.at);
  const ys = pts.map((p) => p.value);
  if (f && f.line && f.band) {
    xs.push(f.line.to.at, f.band.fast.at, f.band.slow.at);
    ys.push(f.line.from.value, f.line.to.value, f.band.from.value,
      f.band.fast.value, f.band.slow.value);
  }
  return {
    x: xs.length ? [Math.min(...xs), Math.max(...xs)] : [0, 1],
    y: chartScale(ys, target),
  };
}

/**
 * The chart's drawing, as numbers only: each point's x and y inside a box
 * `width` by `height` (y grows downward, as in SVG), and the target line's
 * y, or null. Points are placed by their date: the first on the left, the
 * newest on the right; one point sits in the middle.
 *
 * With a `forecast` (a `readForecast` answer) that has a line, the box
 * grows to the right to hold the dashed line and band (`forecastExtent`),
 * and the answer also carries `forecast`: {line: {x1, y1, x2, y2},
 * band: [three {x, y}], bracket: {x1, x2, y} | null, arrows: [{x, y}]}.
 * A bracket needs both ends on the target level (`cross_low_at` and
 * `cross_high_at`); a clipped end (or the open slow end) gets an arrow and
 * no bracket end. Without a forecast, or for a state with no line, nothing
 * changes from before.
 */
export function chartGeometry(points, target, width, height, inset = 8, forecast = null) {
  const pts = (points || []).filter((p) => num(p.at) !== null && num(p.value) !== null);
  const drawn = forecast && forecast.line && forecast.band ? forecast : null;
  const ext = forecastExtent(pts, drawn, target);
  const [lo, hi] = ext.y;
  const w = width - inset * 2;
  const h = height - inset * 2;
  const y = (v) => inset + h - ((v - lo) / (hi - lo)) * h;
  const first = ext.x[0];
  const span = ext.x[1] - ext.x[0];
  const x = (at) => (span > 0 ? inset + ((at - first) / span) * w : inset + w / 2);
  const xy = pts.map((p) => ({
    id: text(p.id),
    at: p.at,
    value: p.value,
    x: x(p.at),
    y: y(p.value),
  }));
  const t = target !== null && target !== undefined && Number.isFinite(Number(target))
    ? y(Number(target)) : null;
  const out = { points: xy, target: t, lo, hi, extent: ext, forecast: null };
  if (drawn) {
    const { line, band } = drawn;
    const corner = (p) => ({ x: x(p.at), y: y(p.value) });
    const fast = { ...corner(band.fast), clipped: band.fast.clipped };
    const slow = { ...corner(band.slow), clipped: band.slow.clipped, open: band.slow.open };
    const end = corner(line.to);
    const arrows = [];
    const arrow = (p) => {
      if (!arrows.some((a) => Math.abs(a.x - p.x) < 0.5 && Math.abs(a.y - p.y) < 0.5)) {
        arrows.push({ x: p.x, y: p.y });
      }
    };
    if (band.fast.clipped) arrow(fast);
    if (band.slow.clipped || band.slow.open) arrow(slow);
    if (line.clipped) arrow(end);
    const bracket = t !== null && drawn.crossLowAt !== null && drawn.crossHighAt !== null
      && !band.slow.open
      ? { x1: x(drawn.crossLowAt), x2: x(drawn.crossHighAt), y: t } : null;
    out.forecast = {
      line: { x1: x(line.from.at), y1: y(line.from.value), x2: end.x, y2: end.y },
      band: [corner(band.from), fast, slow].map(({ x: px, y: py }) => ({ x: px, y: py })),
      bracket,
      arrows,
    };
  }
  return out;
}

/**
 * "3 numbers. Latest: 12 km." - the chart's words for a screen reader,
 * then a space and the PC's forecast sentence (`forecast.words`, as sent)
 * when there is a forecast. With no numbers it is only the empty sentence.
 */
export function chartSummary(bench) {
  const count = Number(bench.results) || (bench.points ? bench.points.length : 0);
  if (!count || !bench.latest) return WORDS.chart_empty;
  const base = fill(WORDS.chart_summary, { count, latest: withUnit(bench.latest.value, bench.unit) });
  const words = bench.forecast && bench.forecast.words ? bench.forecast.words : "";
  return words ? `${base} ${words}` : base;
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
    forecast: readForecast(o.forecast),
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

/* ── The plan board (PM4, 2026-11-21) ──────────────────────────────────────
 * `GET /api/projects/<id>/plan` - one project's plan, read from its own store
 * on the PC. The route is the phone PR's (see docs/ARCHITECTURE.md section 8);
 * this page reads it and never names it: the Rust command does.
 *
 * The four columns and the statuses each one holds. Every status the store
 * knows is in exactly one column, so no card is shown twice and none is
 * dropped; an unknown status still appears, in Planning, rather than being
 * hidden because this page did not recognise one word.
 */

export const PLAN_COLUMNS = Object.freeze([
  Object.freeze({ id: "planning", statuses: Object.freeze(["backlog", "ready"]) }),
  Object.freeze({ id: "progress", statuses: Object.freeze(["in_progress"]) }),
  Object.freeze({ id: "review", statuses: Object.freeze(["waiting_approval", "in_review"]) }),
  Object.freeze({ id: "done", statuses: Object.freeze(["done", "cancelled"]) }),
]);

/** Every work-item status the plan store has (backend jarvis_projects.WORK_STATUSES). */
export const WORK_STATUSES = Object.freeze([
  "backlog", "ready", "in_progress", "waiting_approval", "in_review", "done", "cancelled"]);

/** Which of the four columns one status is shown in. */
export function columnOf(status) {
  const s = text(status);
  for (const col of PLAN_COLUMNS) {
    if (col.statuses.includes(s)) return col.id;
  }
  return "planning";
}

/** "Planning", "In progress", ... for one status; an unknown word is shown as itself. */
export function statusWords(status) {
  const s = text(status);
  return PLAN_WORDS[`status_${s}`] || s;
}

/** "Planned", "In progress", "Done" for one milestone. */
export function milestoneStatusWords(status) {
  const s = text(status);
  return PLAN_WORDS[`milestone_${s}`] || s;
}

function whole(v) {
  return Number.isInteger(v) && v >= 0 ? v : 0;
}

/** The empty plan, so calling code never tests for null. */
function emptyPlan() {
  return {
    available: true,
    hidden: false,
    why: "",
    id: "",
    objective: "",
    successCriteria: "",
    status: "",
    targetDate: "",
    linkedRepo: "",
    linkedNotePath: "",
    slug: "",
    counts: { milestones: 0, workItems: 0, ready: 0, blocked: 0, edges: 0, events: 0 },
    milestones: [],
    items: [],
    ready: [],
    events: [],
  };
}

/** One work item, from the plan route's own shape. Nothing is trusted. */
export function readWorkItem(w) {
  const o = w && typeof w === "object" ? w : {};
  const blockedBy = Array.isArray(o.blocked_by)
    ? o.blocked_by.filter((b) => b && text(b.title)).map((b) => ({
      id: text(b.id), title: text(b.title), status: text(b.status) }))
    : [];
  return {
    id: text(o.id),
    project: text(o.project),
    milestone: text(o.milestone),
    title: text(o.title),
    detail: text(o.detail),
    status: text(o.status),
    priority: num(o.priority),
    dueDate: text(o.due_date),
    created: num(o.created),
    changed: num(o.changed),
    blockedBy,
    ready: o.ready === true,
    executor: text(o.executor) || "owner",
    linkedTaskId: text(o.linked_task_id),
    linkedPrNumber: num(o.linked_pr_number),
    linkedPrState: text(o.linked_pr_state),
    linkedCiStatus: text(o.linked_ci_status),
  };
}

/** One milestone, with its own work-item counts when the route sends them. */
export function readMilestone(m) {
  const o = m && typeof m === "object" ? m : {};
  const c = o.counts && typeof o.counts === "object" ? o.counts : {};
  return {
    id: text(o.id),
    title: text(o.title),
    status: text(o.status),
    dueDate: text(o.due_date),
    position: num(o.position),
    counts: { workItems: whole(c.work_items), done: whole(c.done) },
  };
}

/** One event row (project_events is append-only; this page only reads it). */
export function readEvent(e) {
  const o = e && typeof e === "object" ? e : {};
  return {
    id: text(o.id),
    at: num(o.at),
    kind: text(o.kind),
    subject: text(o.subject),
    detail: o.detail && typeof o.detail === "object" ? o.detail : {},
  };
}

/**
 * `GET /api/projects/<id>/plan`, read. `available: false` with the PC's own
 * sentence for a PC without the route; `hidden: true` while the private lists
 * are hidden (Rust took the plan out). A route answer wrapped in `plan` is
 * accepted too, so a backend that wraps it does not break this page.
 */
export function readPlan(answer) {
  const empty = emptyPlan();
  if (!answer || typeof answer !== "object") {
    return { ...empty, available: false, why: PLAN_WORDS.missing };
  }
  if (answer.hidden === true) {
    return { ...empty, hidden: true, why: PLAN_WORDS.hidden };
  }
  if (answer.available === false) {
    return { ...empty, available: false, why: text(answer.why) || PLAN_WORDS.missing };
  }
  const o = answer.plan && typeof answer.plan === "object" ? answer.plan : answer;
  const counts = o.counts && typeof o.counts === "object" ? o.counts : {};
  const milestones = Array.isArray(o.milestones) ? o.milestones.map(readMilestone) : [];
  const items = Array.isArray(o.work_items) ? o.work_items.map(readWorkItem) : [];
  return {
    ...empty,
    id: text(o.id) || text(o.project),
    objective: text(o.objective),
    successCriteria: text(o.success_criteria),
    status: text(o.status),
    targetDate: text(o.target_date),
    linkedRepo: text(o.linked_repo),
    linkedNotePath: text(o.linked_note_path),
    slug: text(o.slug),
    counts: {
      milestones: whole(counts.milestones) || milestones.length,
      workItems: whole(counts.work_items) || items.length,
      ready: whole(counts.ready),
      blocked: whole(counts.blocked),
      edges: whole(counts.edges),
      events: whole(counts.events),
    },
    milestones,
    items,
    ready: Array.isArray(o.ready) ? o.ready.filter((id) => text(id)).map(text) : [],
    events: Array.isArray(o.events) ? o.events.map(readEvent) : [],
  };
}

/** True when a plan has nothing to draw (a project with no plan rows yet). */
export function planEmpty(plan) {
  return !plan || (!plan.milestones.length && !plan.items.length && !plan.events.length
    && !plan.objective && !plan.successCriteria);
}

/** The work items in each of the four columns, in the route's own order. */
export function planColumns(plan) {
  const items = (plan && plan.items) || [];
  const out = {};
  for (const col of PLAN_COLUMNS) out[col.id] = [];
  for (const item of items) {
    const col = columnOf(item.status);
    out[col].push(item);
  }
  return out;
}

/** The Ready List: exactly the ids the route returned, in its order. */
export function readyItems(plan) {
  const byId = new Map(((plan && plan.items) || []).map((i) => [i.id, i]));
  return ((plan && plan.ready) || []).map((id) => byId.get(id)).filter(Boolean);
}

/** "Waiting on" names for one card, from the blockers the route sent. */
export function blockerNames(item) {
  return ((item && item.blockedBy) || []).map((b) => b.title).filter(Boolean);
}

/** The blocker badge's words for one card, or "" when nothing blocks it. */
export function blockerWords(item) {
  const names = blockerNames(item);
  if (!names.length) return "";
  return fill(names.length === 1 ? PLAN_WORDS.blocked_by_one : PLAN_WORDS.blocked_by,
    { name: names[0], names: names.join(", ") });
}

/** The work items another card is recorded as waiting on (the reverse link). */
export function blocksItems(plan, itemId) {
  return ((plan && plan.items) || []).filter((other) =>
    other.id !== itemId && other.blockedBy.some((b) => b.id === itemId));
}

/** The milestone of one item, or null. */
export function itemMilestone(plan, item) {
  if (!item || !item.milestone) return null;
  return ((plan && plan.milestones) || []).find((m) => m.id === item.milestone) || null;
}

/**
 * The project's progress, from the route's real counts: work items done out of
 * all work items, and milestones done out of all milestones. `percent` is the
 * bar's share - of the milestones when the project has any (the bar is the
 * design's "Milestone progress bar"), otherwise of the work items - rounded
 * down, so the bar never claims more than is done.
 */
export function milestoneProgress(plan) {
  const p = plan || {};
  const items = p.items || [];
  const milestones = p.milestones || [];
  const total = p.counts && p.counts.workItems ? p.counts.workItems : items.length;
  const done = items.filter((i) => i.status === "done").length;
  const milestoneDone = milestones.filter((m) => m.status === "done").length;
  const workPercent = total ? Math.floor((done / total) * 100) : 0;
  const milestonePercent = milestones.length
    ? Math.floor((milestoneDone / milestones.length) * 100) : null;
  return {
    workDone: done,
    workTotal: total,
    milestoneDone,
    milestoneTotal: milestones.length,
    workPercent,
    milestonePercent,
    percent: milestonePercent === null ? workPercent : milestonePercent,
  };
}

/** One row per milestone: its own counts (the route's, or counted from the items). */
export function milestoneRows(plan) {
  const p = plan || {};
  const items = p.items || [];
  return (p.milestones || []).map((m) => {
    const own = items.filter((i) => i.milestone === m.id);
    const fromItems = own.filter((i) => i.status === "done").length;
    const sent = m.counts.workItems > 0 || m.counts.done > 0;
    const done = sent ? m.counts.done : fromItems;
    const total = m.counts.workItems || own.length;
    return { ...m, workDone: done, workTotal: total,
      percent: total ? Math.floor((done / total) * 100) : 0 };
  });
}

/** "Pull request #12 - merged, checks green", or "" when none is linked. */
export function linkedPrWords(item) {
  const n = num(item && item.linkedPrNumber);
  if (n === null) return "";
  const state = PLAN_WORDS[`pr_${text(item.linkedPrState)}`] || text(item.linkedPrState)
    || PLAN_WORDS.pr_open;
  const ci = text(item.linkedCiStatus);
  const checks = ci ? fill(PLAN_WORDS.linked_checks, {
    words: PLAN_WORDS[`ci_${ci}`] || ci }) : "";
  return fill(PLAN_WORDS.linked_pr, { number: numberWords(n), state, checks });
}

/** "Who does it: Jarvis, on this PC" for one card. */
export function executorWords(item) {
  const executor = text(item && item.executor) || "owner";
  return fill(PLAN_WORDS.executor,
    { who: PLAN_WORDS[`executor_${executor}`] || executor });
}

/**
 * One `project_events` row in words, with the id `subject` resolved to the
 * work item's or milestone's own title. An unknown kind shows its own name
 * rather than an invented one.
 */
export function eventWords(event, plan) {
  const e = event && typeof event === "object" ? event : {};
  const kind = text(e.kind);
  const label = PLAN_EVENT_WORDS[kind] || kind || "Activity";
  const detail = e.detail && typeof e.detail === "object" ? e.detail : {};
  const subject = text(e.subject);
  let subjectWords = "";
  for (const item of ((plan && plan.items) || [])) {
    if (item.id === subject) subjectWords = item.title;
  }
  for (const milestone of ((plan && plan.milestones) || [])) {
    if (milestone.id === subject && !subjectWords) subjectWords = milestone.title;
  }
  let extra = "";
  if (detail.from !== undefined && detail.to !== undefined) {
    extra = `${statusWords(detail.from)} → ${statusWords(detail.to)}`;
  } else if (typeof detail.text === "string") {
    extra = detail.text;
  } else if (detail.status !== undefined) {
    extra = statusWords(detail.status);
  }
  return { kind, label, subject: subjectWords, extra, at: num(e.at) };
}

/** The events recorded for one card, newest first (the route sends newest first). */
export function itemEvents(plan, itemId) {
  return ((plan && plan.events) || []).filter((e) => e.subject === itemId);
}

/**
 * The status moves this page offers for one card, through the store's own
 * existing status path (the phone half's route: one event and one Undo
 * receipt). Nothing here changes a status by itself: the PC decides, refuses a
 * blocked item in its own words, and the page re-reads after every move.
 */
export function statusMoves(item) {
  const status = text(item && item.status);
  const closed = status === "done" || status === "cancelled";
  if (closed) return [{ status: "backlog", label: PLAN_WORDS.move_reopen }];
  const moves = [];
  if (status === "backlog" || status === "ready") {
    moves.push({ status: "in_progress", label: PLAN_WORDS.move_start });
  }
  if (status === "in_progress" || status === "waiting_approval") {
    moves.push({ status: "in_review", label: PLAN_WORDS.move_review });
  }
  moves.push({ status: "done", label: PLAN_WORDS.move_done });
  return moves;
}
