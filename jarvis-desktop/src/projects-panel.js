/**
 * Brain -> Projects: the page (the owner's decision of 2026-09-28;
 * docs/PROJECTS-DESIGN.md build step 3). projects.js holds the words and the
 * reading; this draws them into `#projects-root` and sends the owner's taps
 * through three Rust commands (brain/projects.rs): `projects_read`,
 * `projects_write` (ONE change, named by an action from a fixed list) and
 * `projects_choose_folder` (the Windows folder picker).
 *
 * Kept out of brain.js on purpose, so the Brain's other tabs and this one
 * never edit the same lines. brain.js only lists the tab and calls
 * `showProjects()` when it is opened.
 *
 * Rules this page keeps:
 * - Everything the PC wrote reaches the page as text (`textContent`), never
 *   as markup.
 * - A number marked private (health or money, or marked by the owner) is
 *   shown with "private - not read aloud" and is never put into anything
 *   spoken: a status line after logging one says only "Logged."
 * - Every change is greyed while the link is stale or down (rule 4; Rust
 *   refuses it too), except turning Shareable OFF.
 * - Deleting a project or a benchmark asks "are you sure?" first.
 * - An app Jarvis builds (docs/APPS-IN-PROJECTS-DESIGN.md) is a coding
 *   project with an App section: its latest saved version, its open tasks,
 *   and a Task view that shows the WHOLE change as text (never cut, never
 *   stored or logged here). Merge asks the PC, which raises ONE card in the
 *   Jarvis bar; this page shows how it ended, in the PC's own sentence.
 *   Discard asks "are you sure?". Pasting a change in is this PC only.
 * - The PC decides what asks first. This page never approves anything:
 *   a card it causes shows in the Jarvis bar like any other.
 *
 * @module projects-panel
 */

import { announce, currentLink, linkWords, onLink, onQueue } from "./jarvis-link.js";
import { refreshProgress, setProgressVisible } from "./progress-panel.js";
// "Ask for a picture, and keep it" (the owner's decision of 2026-09-27;
// JARVIS-API section 129). It sits beside the Progress pictures, above the
// project list, and reads on its own - never blocking this page.
import { refreshPictures, setPicturesVisible } from "./pictures-panel.js";
// "File history" (LM-2C): the copies of files Jarvis changed, beside the
// pictures and above the project list. It reads on its own, never blocks
// this page, and Rust hides it whole while App lock or the private lists
// are on (brain/guardian.rs).
import { refreshGuardian, setGuardianVisible } from "./guardian-panel.js";
import {
  APP_WORDS,
  PLAN_COLUMNS,
  PLAN_WORDS,
  appProjectBody,
  appTypeWords,
  benchBody,
  blockerWords,
  blocksItems,
  chartGeometry,
  chartSummary,
  columnOf,
  diffLineKind,
  eventWords,
  executorWords,
  fill,
  itemEvents,
  itemMilestone,
  linkedPrWords,
  mergeOffer,
  milestoneProgress,
  milestoneRows,
  milestoneStatusWords,
  notesFrom,
  numberWords,
  pasteBody,
  planColumns,
  planEmpty,
  projectMeta,
  readBench,
  readList,
  readPlan,
  readProject,
  readTask,
  readyItems,
  shortDate,
  statusMoves,
  statusWords,
  taskChange,
  taskTitleBody,
  unmarkOffer,
  valueFrom,
  versionLines,
  withUnit,
  WORDS,
} from "./projects.js";

const TAURI = globalThis.__TAURI__;
const SVG = "http://www.w3.org/2000/svg";

const state = {
  list: null,
  /** The open project's id, or null for the list. */
  open: null,
  project: null,
  /** The open task's id (an app project), or null; `taskData` is its detail. */
  task: null,
  taskData: null,
  /** bench id -> its view with chart points. */
  points: {},
  /** project id -> {instructions, notes} typed but not saved yet. */
  drafts: {},
  /** task id -> the text pasted but not sent yet. */
  pastes: {},
  error: "",
  said: "",
  reading: false,
  /** A refresh asked for while a read was running: read again when it ends. */
  again: false,
  readAt: 0,
  /** The plan board's selected project id (the list view), or "". */
  boardProject: "",
  /** That project's plan, a `readPlan` answer; null before the first read. */
  plan: null,
  /** The plan read's own error sentence, when the read threw (not availability). */
  planError: "",
  /** The open work item's id, whose detail is drawn under the board. */
  boardItem: "",
};

/** Buttons and fields that send a change: greyed while the link cannot be confirmed. */
const live = new Set();

async function invoke(command, args = {}) {
  const core = globalThis.__TAURI__ && globalThis.__TAURI__.core;
  if (!core || !core.invoke) return null;
  return core.invoke(command, args);
}

function errorText(error) {
  return String((error && error.message) || error || "Something went wrong.");
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function canAct() {
  return linkWords(currentLink()).canAct;
}

function syncLive(node) {
  const ok = canAct() || node.dataset.heldOff === "true";
  node.disabled = !ok || node.dataset.busy === "true" || node.dataset.off === "true";
  node.title = ok ? node.dataset.title || "" : WORDS.stale;
}

function syncAllLive() {
  for (const n of live) {
    if (!n.isConnected) live.delete(n);
    else syncLive(n);
  }
}

/** A button. `live` ones send a change and wait for a live link. */
function button(label, onClick, { danger = false, title = "", isLive = true, ghost = false } = {}) {
  const b = el("button", `btn small${danger ? " danger" : ""}${ghost ? " ghost" : ""}`, label);
  b.type = "button";
  b.dataset.title = title;
  if (title) b.title = title;
  if (isLive) {
    live.add(b);
    syncLive(b);
  }
  b.addEventListener("click", async () => {
    b.dataset.busy = "true";
    b.disabled = true;
    try {
      await onClick();
    } finally {
      b.dataset.busy = "false";
      if (isLive) syncLive(b);
      else b.disabled = false;
    }
  });
  return b;
}

function labelled(labelText, field, under) {
  const box = el("label", "lbl pj-field");
  box.append(el("span", "", labelText), field);
  if (under) box.append(el("span", "pj-under", under));
  return box;
}

function root() {
  return document.getElementById("projects-root");
}

/** One line under everything the page did last, spoken politely. */
function say(message, tone = "") {
  state.said = String(message || "");
  const line = document.getElementById("projects-said");
  if (line) {
    line.textContent = state.said;
    line.dataset.tone = tone;
  }
  if (state.said) announce(state.said, tone === "bad" ? "assertive" : "polite");
}

/* ── Reading ──────────────────────────────────────────────────────────── */

async function readListNow() {
  try {
    state.list = readList(await invoke("projects_read", {}));
    state.error = "";
  } catch (error) {
    state.error = errorText(error);
  }
}

async function readProjectNow(id) {
  try {
    const out = await invoke("projects_read", { project: id });
    if (out && out.hidden === true) {
      state.project = { hidden: true };
      state.points = {};
      state.taskData = null;
      return;
    }
    const p = readProject(out && out.project);
    if (!p.id) {
      state.open = null;
      state.project = null;
      return;
    }
    state.project = p;
    const points = {};
    await Promise.all(p.benchList.map(async (b) => {
      try {
        const got = await invoke("projects_read", { project: id, bench: b.id, points: 365 });
        if (got && got.benchmark) points[b.id] = readBench(got.benchmark);
      } catch {
        /* the list's own latest number still shows */
      }
    }));
    state.points = points;
    state.error = "";
    await readTaskNow(id);
  } catch (error) {
    state.error = errorText(error);
  }
}

/** The open task, if any. A task that is gone (merged, discarded) closes its view. */
async function readTaskNow(projectId) {
  state.taskData = null;
  if (!state.task) return;
  try {
    const got = await invoke("projects_read", { project: projectId, task: state.task });
    if (got && got.hidden === true) {
      state.task = null;
      return;
    }
    const t = readTask(got);
    if (t.task) state.taskData = t;
    else state.task = null;
  } catch {
    state.task = null;
  }
}

/** The board's project: the selected one, still on the list, or the first. */
function boardProjectId() {
  const v = state.list;
  if (!v || !v.available || v.hidden || !v.projects.length) return "";
  const ids = v.projects.map((p) => p.id);
  return ids.includes(state.boardProject) ? state.boardProject : ids[0];
}

/**
 * The selected project's plan, from the PC. Read on its own so a PC that does
 * not have the route yet shows its own sentence instead of an empty board -
 * the page never draws an empty plan and calls it the project's plan.
 */
async function readBoardNow() {
  state.plan = null;
  state.planError = "";
  const id = boardProjectId();
  state.boardProject = id;
  if (!id) {
    state.boardItem = "";
    return;
  }
  try {
    const out = await invoke("projects_read", { project: id, plan: true });
    state.plan = readPlan(out);
  } catch (error) {
    state.plan = null;
    state.planError = errorText(error);
  }
  if (state.boardItem && state.plan && !state.plan.items.some((i) => i.id === state.boardItem)) {
    state.boardItem = "";
  }
}

/** Reads what is on screen again, then draws it. */
export async function showProjects() {
  if (state.reading) {
    // A change finished while a read was already running: that read may have
    // started before the change, so read once more when it ends rather than
    // dropping this one (bug audit 2026-09-29).
    state.again = true;
    return;
  }
  state.reading = true;
  try {
    await readListNow();
    if (state.open) await readProjectNow(state.open);
    else await readBoardNow();
    if (!state.error) state.readAt = Date.now();
  } finally {
    state.reading = false;
  }
  paint();
  // The Progress pictures (progress-panel.js) sit above the list, not inside
  // a project; they read on their own and never block this page. The Pictures
  // gallery (pictures-panel.js) sits beside them and follows the same rule.
  setProgressVisible(!state.open);
  if (!state.open) refreshProgress();
  setPicturesVisible(!state.open);
  if (!state.open) refreshPictures();
  setGuardianVisible(!state.open);
  if (!state.open) refreshGuardian();
  if (state.again) {
    state.again = false;
    await showProjects();
  }
}

/** When the list was last read without an error - the Brain's status line
 *  (it said "reading…" for ever before; the chat audit, 2026-09-28). */
export function readAtMs() {
  return state.readAt || 0;
}

/* ── Changing ─────────────────────────────────────────────────────────── */

/**
 * ONE change. A 202 means the PC raised an approval card; its own message
 * says so. `quiet` keeps the number out of anything spoken.
 */
async function write(action, args, { done = "", quiet = false, onDone = null } = {}) {
  try {
    const out = await invoke("projects_write", { action, ...args });
    if (out && out.ok === false) {
      say(String(out.error || "Refused."), "bad");
      return null;
    }
    const message = out && typeof out.message === "string" ? out.message : "";
    say(quiet ? done || "Done." : message || done || "Done.", "ok");
    // Runs BEFORE the repaint below, so what it clears is already gone when
    // the screen is drawn again.
    if (onDone) onDone();
    return out || {};
  } catch (error) {
    say(errorText(error), "bad");
    return null;
  } finally {
    await showProjects();
  }
}

async function createProject(nameField, kindField) {
  const name = nameField.value.trim();
  if (!name) {
    say("Give the project a name.", "bad");
    nameField.focus();
    return;
  }
  const body = appProjectBody(name, kindField.value) || { name, kind: kindField.value };
  const out = await write("create", { body }, { done: "Created." });
  if (out && out.project && out.project.id) {
    state.open = out.project.id;
    await showProjects();
  }
}

/** "Add an app I already have": link a folder that has no project. */
async function adoptApp(a) {
  const out = await write("create", { body: appProjectBody("", `adopt:${a.name}`) },
    { done: "Added." });
  if (out && out.project && out.project.id) {
    state.open = out.project.id;
    await showProjects();
  }
}

async function openTask(id) {
  state.task = id;
  await showProjects();
  const heading = document.getElementById("projects-task-heading");
  if (heading) heading.focus();
}

async function backToProject() {
  state.task = null;
  state.taskData = null;
  await showProjects();
  const heading = document.getElementById("projects-heading");
  if (heading) heading.focus();
}

async function startTask(p, field) {
  const got = taskTitleBody(field.value);
  if (got.error) {
    say(got.error, "bad");
    field.focus();
    return;
  }
  const out = await write("app_task_start", { project: p.id, body: got.body }, { done: "Task started." });
  if (out && out.task && out.task.task) await openTask(out.task.task);
}

async function pasteChange(p, t, area) {
  const got = pasteBody(area.value);
  if (got.error) {
    say(got.error, "bad");
    area.focus();
    return;
  }
  // The pasted text is dropped as soon as the change goes through - before
  // the repaint that write() ends with, which would otherwise draw the box
  // with the same change still in it (a second press added it twice; bug
  // audit 2026-09-29).
  await write("app_task_files", { project: p.id, task: t.task, body: got.body },
    { done: "Added to this task.", onDone: () => { delete state.pastes[t.task]; } });
}

/** Merge: ONE request; the PC raises the card, this page never decides it. */
async function mergeTask(p, t) {
  await write("app_task_merge", { project: p.id, task: t.task, body: {} }, { done: "Merge asked." });
}

async function discardTask(p, t) {
  const q = t.waiting || (p.app && p.app.mergeWaiting === t.task)
    ? APP_WORDS.discard_waiting_q : APP_WORDS.discard_q;
  if (!window.confirm(q)) return;
  const out = await write("app_task_discard", { project: p.id, task: t.task, body: {} },
    { done: "Thrown away." });
  if (out) await backToProject();
}

async function openProject(id) {
  state.open = id;
  state.task = null;
  state.taskData = null;
  state.project = null;
  state.points = {};
  await showProjects();
  const heading = document.getElementById("projects-heading");
  if (heading) heading.focus();
}

async function backToList() {
  state.open = null;
  state.task = null;
  state.taskData = null;
  state.project = null;
  state.points = {};
  await showProjects();
}

async function saveText(p, instructions, notes) {
  const out = await write("update", {
    project: p.id,
    body: { instructions: instructions.value, notes: notesFrom(notes.value) },
  }, { done: "Saved." });
  if (out) delete state.drafts[p.id];
}

async function deleteProject(p) {
  const q = p.app ? APP_WORDS.delete_app_project_q : WORDS.delete_project_q;
  if (!window.confirm(fill(q, { name: p.name }))) return;
  const out = await write("delete", { project: p.id },
    { done: p.app ? APP_WORDS.deleted_app_kept : "Deleted." });
  if (out) await backToList();
}

async function setShareable(p, on, box) {
  box.disabled = true;
  await write("shareable", { project: p.id, body: { on } });
}

async function logNumber(p, b, field) {
  const value = valueFrom(field.value);
  if (value === null) {
    say("Type a number, like 5 or 72.5.", "bad");
    field.focus();
    return;
  }
  const out = await write("log", { project: p.id, bench: b.id, body: { value } },
    { done: "Logged.", quiet: b.keepOnScreen });
  if (out && !b.keepOnScreen && out.benchmark && out.benchmark.change) {
    say(`Logged. ${out.benchmark.change.said || ""}`.trim(), "ok");
  }
}

async function unmark(p, b) {
  await write("unmark", { project: p.id, bench: b.id, body: {} });
}

async function markPrivate(p, b) {
  await write("bench_update", { project: p.id, bench: b.id, body: { sensitive: true } },
    { done: "Marked private." });
}

async function deleteBench(p, b) {
  if (!window.confirm(fill(WORDS.delete_bench_q, { name: b.name }))) return;
  await write("bench_delete", { project: p.id, bench: b.id }, { done: "Deleted." });
}

async function removeNumber(p, b, point) {
  await write("result_delete", { project: p.id, bench: b.id, result: point.id },
    { done: "Removed.", quiet: true });
}

async function chooseFolder(p) {
  try {
    const out = await invoke("projects_choose_folder", { project: p.id });
    if (out && out.cancelled) return;
    say("Folder chosen.", "ok");
  } catch (error) {
    say(errorText(error), "bad");
  }
  await showProjects();
}

/* ── Drawing ──────────────────────────────────────────────────────────── */

function paint() {
  const box = root();
  if (!box) return;
  live.clear();
  const out = [];
  if (state.open && state.project && state.task && state.taskData && !state.project.hidden) {
    out.push(taskCard(state.project, state.taskData));
  } else if (state.open && state.project) out.push(state.project.hidden ? hiddenCard() : projectCard(state.project));
  else out.push(listCard());
  const said = el("p", "pj-said", state.said);
  said.id = "projects-said";
  said.setAttribute("role", "status");
  out.push(said);
  box.replaceChildren(...out);
}

function hiddenCard() {
  const card = el("div", "card card-wide pj-card");
  card.append(el("h2", "", WORDS.title));
  card.append(hiddenNode(state.list ? state.list.hiddenCount : 0));
  return card;
}

function hiddenNode(count) {
  const box = el("div", "private-hidden");
  const n = Number(count) || 0;
  box.append(el("p", "empty", n
    ? `${n} ${n === 1 ? "project" : "projects"}, hidden until Windows Hello confirms it is you.`
    : "Hidden until Windows Hello confirms it is you."));
  box.append(button("Show", async () => {
    try {
      await invoke("reveal_private_answers");
    } catch (error) {
      say(errorText(error), "bad");
      return;
    }
    await showProjects();
  }, { isLive: false,
    title: "Asks Windows Hello - your PIN, fingerprint or face - then shows this list." }));
  return box;
}

/* ── The plan board (PM4, 2026-11-21) ──────────────────────────────────────
 * The existing Projects view keeps its list; the board sits above it and reads
 * one project's plan from the PC. It is a READ except for two named actions:
 * switching the board's project (a read) and Export, which is the existing
 * hub-export action - ONE notes-editor card, raised by the PC, never here.
 * No work item's status is changed from this page: a status move is the
 * project store's own route, with its receipt and Undo, and this page does not
 * add a second one.
 */

async function chooseBoardProject(id) {
  state.boardProject = String(id || "");
  state.boardItem = "";
  await showProjects();
  const sel = document.getElementById("projects-board-select");
  if (sel) sel.focus();
}

async function openBoardItem(id) {
  state.boardItem = String(id || "");
  paint();
  const heading = document.getElementById("projects-item-heading");
  if (heading) heading.focus();
}

async function closeBoardItem() {
  const was = state.boardItem;
  state.boardItem = "";
  paint();
  const card = [...document.querySelectorAll(".pj-wcard")]
    .find((node) => node.dataset.id === was);
  if (card) card.focus();
}

/** Export: the existing hub-export action. ONE request; the PC raises the card. */
async function exportHub() {
  const id = state.boardProject;
  if (!id) return;
  await write("export_hub", { project: id }, { done: PLAN_WORDS.export_waiting });
}

/**
 * ONE status move, through the project store's own status path (the receipt
 * and Undo are the store's). A blocked item is the PC's to refuse; its own
 * sentence is shown and the board is read again, so the card never silently
 * changes column.
 */
async function moveItem(projectId, item, status) {
  await write("work_item_status",
    { project: projectId, item: item.id, body: { status } }, { done: PLAN_WORDS.moved });
}

/** ONE new work item - the store's own quick add. */
async function addWorkItem(projectId, field) {
  const title = String(field.value || "").trim();
  if (!title) {
    say(PLAN_WORDS.add_empty, "bad");
    field.focus();
    return;
  }
  if ([...title].length > 120) {
    say(PLAN_WORDS.add_long, "bad");
    field.focus();
    return;
  }
  const out = await write("work_item_add", { project: projectId, body: { title } },
    { done: PLAN_WORDS.added });
  if (out) field.value = "";
}

function boardSection(v) {
  const chosen = boardProjectId();
  const board = el("section", "pj-board");
  board.id = "projects-board";
  board.setAttribute("aria-label", PLAN_WORDS.board);
  board.dataset.project = chosen;

  const head = el("div", "pj-board-head");
  const label = el("label", "lbl pj-selector");
  label.append(el("span", "", PLAN_WORDS.project));
  const select = el("select", "field");
  select.id = "projects-board-select";
  select.setAttribute("aria-label", PLAN_WORDS.project);
  for (const p of v.projects) {
    const option = el("option", "", p.name);
    option.value = p.id;
    select.append(option);
  }
  select.value = chosen;
  select.addEventListener("change", () => chooseBoardProject(select.value));
  label.append(select);
  const exportButton = button(PLAN_WORDS.export, exportHub, { title: PLAN_WORDS.export_title });
  exportButton.id = "projects-export";
  const chosenName = (v.projects.find((p) => p.id === chosen) || {}).name || "";
  exportButton.setAttribute("aria-label", `${PLAN_WORDS.export}: ${chosenName}`);
  head.append(label, exportButton);
  board.append(head);
  board.append(el("p", "note pj-board-under", PLAN_WORDS.under));
  board.append(el("p", "note pj-export-under", PLAN_WORDS.export_more));

  const plan = state.plan;
  if (state.planError) {
    board.append(el("p", "empty failed", `Could not read the plan: ${state.planError}.`));
  } else if (plan && plan.hidden) {
    board.append(el("p", "empty", PLAN_WORDS.hidden));
  } else if (plan && plan.available === false) {
    board.append(el("p", "empty failed pj-plan-missing", plan.why));
  } else if (!plan) {
    board.append(el("p", "empty", PLAN_WORDS.reading));
  } else {
    board.append(planSection(plan), readySection(plan), milestoneSection(plan),
      kanbanSection(plan), addWorkItemForm(chosen));
    if (state.boardItem) board.append(itemDetail(plan, state.boardItem));
    if (planEmpty(plan)) board.append(el("p", "note", PLAN_WORDS.ready_empty));
  }
  return board;
}

/** Quick add: ONE work item through the store's own add path. */
function addWorkItemForm(projectId) {
  const form = el("form", "todo-form pj-add-item");
  form.id = "projects-add-item";
  form.autocomplete = "off";
  const field = el("input", "field todo-text");
  field.type = "text";
  field.maxLength = 120;
  field.id = "projects-item-title";
  field.placeholder = PLAN_WORDS.add_title;
  field.setAttribute("aria-label", PLAN_WORDS.add_title);
  const add = el("button", "btn small", PLAN_WORDS.add_item);
  add.type = "submit";
  live.add(add);
  syncLive(add);
  form.append(field, add);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    addWorkItem(projectId, field);
  });
  return form;
}

/** The project-level words a card opens on: its objective is the anchor. */
function planSection(plan) {
  const box = el("section", "pj-plan-fields");
  box.append(el("h3", "subhead", PLAN_WORDS.objective));
  box.append(el("p", "pj-line pj-objective", plan.objective || PLAN_WORDS.objective_none));
  if (plan.successCriteria) {
    box.append(el("h4", "pj-detail-label", PLAN_WORDS.success),
      el("p", "pj-line pj-success", plan.successCriteria));
  }
  return box;
}

/** The milestone bar: the project's real counts, never an estimate. */
function milestoneSection(plan) {
  const box = el("section", "pj-progress-box");
  box.id = "projects-progress-box";
  box.setAttribute("aria-label", PLAN_WORDS.progress);
  box.append(el("h3", "subhead", PLAN_WORDS.progress));
  const p = milestoneProgress(plan);
  const words = p.workTotal
    ? `${fill(PLAN_WORDS.progress_work, { done: p.workDone, total: p.workTotal })} · `
      + fill(PLAN_WORDS.progress_milestones,
        { done: p.milestoneDone, total: p.milestoneTotal })
    : PLAN_WORDS.progress_none;
  const bar = el("div", "pj-bar");
  bar.id = "projects-progress";
  bar.setAttribute("role", "progressbar");
  bar.setAttribute("aria-label", PLAN_WORDS.progress);
  bar.setAttribute("aria-valuemin", "0");
  bar.setAttribute("aria-valuemax", "100");
  bar.setAttribute("aria-valuenow", String(p.percent));
  bar.setAttribute("aria-valuetext", words);
  const fillBar = el("span", "pj-bar-fill");
  fillBar.style.width = `${p.percent}%`;
  bar.append(fillBar);
  box.append(bar, el("p", "pj-progress-words", words));

  const rows = milestoneRows(plan);
  if (!rows.length) box.append(el("p", "note", PLAN_WORDS.milestones_empty));
  else {
    const list = el("ul", "pj-milestones");
    for (const m of rows) {
      const li = el("li", "pj-milestone");
      li.dataset.id = m.id;
      const name = el("span", "pj-milestone-name", m.title);
      const tag = el("span", "row-tag pj-milestone-status", milestoneStatusWords(m.status));
      tag.dataset.status = m.status;
      const count = el("span", "pj-milestone-count",
        fill(PLAN_WORDS.milestone_work, { done: m.workDone, total: m.workTotal }));
      const mini = el("span", "pj-mini-bar");
      mini.setAttribute("aria-hidden", "true");
      const miniFill = el("span", "pj-mini-bar-fill");
      miniFill.style.width = `${m.percent}%`;
      mini.append(miniFill);
      li.append(name, tag, count, mini);
      list.append(li);
    }
    box.append(list);
  }
  return box;
}

/** The Ready List: exactly the ids the route returned, in its order. */
function readySection(plan) {
  const box = el("section", "pj-ready");
  box.id = "projects-ready";
  box.setAttribute("aria-label", PLAN_WORDS.ready);
  box.append(el("h3", "subhead", PLAN_WORDS.ready),
    el("p", "note", PLAN_WORDS.ready_under));
  const ready = readyItems(plan);
  if (!ready.length) {
    box.append(el("p", "empty", PLAN_WORDS.ready_empty));
    return box;
  }
  const list = el("ul", "pj-ready-list");
  for (const item of ready) {
    const li = el("li", "pj-ready-item");
    li.dataset.id = item.id;
    const open = button(fill(PLAN_WORDS.ready_open, { title: item.title }),
      () => openBoardItem(item.id), { isLive: false, ghost: true });
    open.dataset.id = item.id;
    li.append(open);
    const tag = el("span", "row-tag pj-status", statusWords(item.status));
    tag.dataset.status = item.status;
    li.append(tag);
    if (item.dueDate) li.append(el("span", "pj-wcard-due", fill(PLAN_WORDS.due, { date: item.dueDate })));
    const blocked = blockerWords(item);
    if (blocked) li.append(el("span", "pj-blocker", blocked));
    list.append(li);
  }
  box.append(list);
  const total = plan.counts.ready || ready.length;
  if (total > ready.length) {
    box.append(el("p", "note", fill(PLAN_WORDS.ready_more, { count: total - ready.length })));
  }
  return box;
}

/** The four columns: Planning | In Progress | In Review / Waiting | Done. */
function kanbanSection(plan) {
  const columns = planColumns(plan);
  const board = el("div", "pj-kanban");
  board.id = "projects-kanban";
  for (const col of PLAN_COLUMNS) {
    const section = el("section", "pj-col");
    section.dataset.column = col.id;
    const heading = el("h3", "pj-col-title", PLAN_WORDS[`column_${col.id}`]);
    section.append(heading, el("span", "pj-col-count", String(columns[col.id].length)));
    const cards = el("div", "pj-cards");
    if (!columns[col.id].length) {
      cards.append(el("p", "empty pj-col-empty", PLAN_WORDS.column_empty));
    }
    for (const item of columns[col.id]) cards.append(workCard(plan, item));
    section.append(cards);
    board.append(section);
  }
  return board;
}

/** One work item as a card; the whole card is the button that opens it. */
function workCard(plan, item) {
  const card = el("button", "pj-wcard");
  card.type = "button";
  card.dataset.id = item.id;
  card.dataset.status = item.status;
  card.setAttribute("aria-label", fill(PLAN_WORDS.item_open, { title: item.title }));
  card.append(el("span", "pj-wcard-title", item.title));
  const meta = el("span", "pj-wcard-meta");
  const tag = el("span", "row-tag pj-status", statusWords(item.status));
  tag.dataset.status = item.status;
  meta.append(tag);
  if (item.dueDate) {
    meta.append(el("span", "pj-wcard-due", fill(PLAN_WORDS.due, { date: item.dueDate })));
  }
  const milestone = itemMilestone(plan, item);
  if (milestone) {
    meta.append(el("span", "pj-wcard-milestone",
      fill(PLAN_WORDS.milestone, { name: milestone.title })));
  }
  card.append(meta);
  const blocked = blockerWords(item);
  if (blocked) {
    const badge = el("span", "pj-blocker", blocked);
    badge.dataset.state = "warn";
    card.append(badge);
  }
  card.addEventListener("click", () => openBoardItem(item.id));
  return card;
}

/** One card's detail: objective anchor, dependencies, links and activity. */
function itemDetail(plan, id) {
  const item = plan.items.find((i) => i.id === id);
  if (!item) return el("p", "empty", PLAN_WORDS.activity_none);
  const box = el("section", "pj-detail");
  box.id = "projects-item";
  box.dataset.id = item.id;
  const head = el("div", "pj-detail-head");
  const heading = el("h3", "pj-detail-title", item.title);
  heading.id = "projects-item-heading";
  heading.tabIndex = -1;
  const close = button(PLAN_WORDS.close, closeBoardItem, { isLive: false, ghost: true });
  close.id = "projects-item-close";
  close.setAttribute("aria-label", `${PLAN_WORDS.close}: ${item.title}`);
  head.append(heading, close);
  box.append(head);
  const lines = [statusWords(item.status)];
  if (item.dueDate) lines.push(fill(PLAN_WORDS.due, { date: item.dueDate }));
  lines.push(executorWords(item));
  box.append(el("p", "pj-line pj-detail-meta", lines.join(" · ")));
  if (item.detail) box.append(el("p", "pj-line pj-detail-text", item.detail));

  // Status moves: the store's own status path, one receipt each. The PC
  // refuses a blocked item in its own words; nothing here decides.
  box.append(el("h4", "pj-detail-label", PLAN_WORDS.moves));
  const moves = el("div", "row pj-moves");
  for (const move of statusMoves(item)) {
    const b = button(move.label,
      () => moveItem(state.boardProject, item, move.status));
    b.dataset.status = move.status;
    b.setAttribute("aria-label", `${move.label}: ${item.title}`);
    moves.append(b);
  }
  box.append(moves);

  box.append(el("h4", "pj-detail-label", PLAN_WORDS.objective));
  box.append(el("p", "pj-line pj-objective", plan.objective || PLAN_WORDS.objective_none));
  if (plan.successCriteria) {
    box.append(el("h4", "pj-detail-label", PLAN_WORDS.success),
      el("p", "pj-line pj-success", plan.successCriteria));
  }

  box.append(el("h4", "pj-detail-label", PLAN_WORDS.waiting_on));
  if (item.blockedBy.length) {
    const list = el("ul", "pj-deps pj-deps-blocked");
    for (const blocker of item.blockedBy) {
      const li = el("li", "pj-dep");
      li.dataset.id = blocker.id;
      li.append(el("span", "pj-dep-name", blocker.title),
        el("span", "row-tag pj-status", statusWords(blocker.status)));
      list.append(li);
    }
    box.append(list);
  } else box.append(el("p", "pj-line", PLAN_WORDS.waiting_none));

  const blocks = blocksItems(plan, item.id);
  box.append(el("h4", "pj-detail-label", PLAN_WORDS.blocks));
  if (blocks.length) {
    const list = el("ul", "pj-deps pj-deps-blocks");
    for (const other of blocks) {
      const li = el("li", "pj-dep");
      li.append(el("span", "pj-dep-name", other.title),
        el("span", "row-tag pj-status", statusWords(other.status)));
      list.append(li);
    }
    box.append(list);
  } else box.append(el("p", "pj-line", PLAN_WORDS.blocks_none));

  box.append(el("h4", "pj-detail-label", PLAN_WORDS.linked));
  const pr = linkedPrWords(item);
  let linked = false;
  if (pr) {
    box.append(el("p", "pj-line pj-linked-pr", pr));
    linked = true;
  }
  if (plan.linkedNotePath) {
    box.append(el("p", "pj-line pj-linked-note",
      fill(PLAN_WORDS.linked_note, { path: plan.linkedNotePath })));
    linked = true;
  }
  if (plan.linkedRepo) {
    box.append(el("p", "pj-line pj-linked-repo",
      fill(PLAN_WORDS.linked_repo, { repo: plan.linkedRepo })));
    linked = true;
  }
  if (!linked) box.append(el("p", "pj-line", PLAN_WORDS.linked_none));

  box.append(el("h4", "pj-detail-label", PLAN_WORDS.activity));
  const events = itemEvents(plan, item.id);
  if (!events.length) box.append(el("p", "pj-line", PLAN_WORDS.activity_none));
  else {
    const list = el("ol", "pj-events");
    for (const event of events) list.append(eventRow(event, plan));
    box.append(list);
  }
  return box;
}

function eventRow(event, plan) {
  const words = eventWords(event, plan);
  const li = el("li", "pj-event");
  li.dataset.kind = words.kind;
  li.append(el("span", "pj-event-when", shortDate(words.at)));
  const main = el("span", "pj-event-main");
  main.append(el("span", "pj-event-kind", words.label));
  if (words.subject) main.append(el("span", "pj-event-subject", words.subject));
  if (words.extra) main.append(el("span", "pj-event-extra", words.extra));
  li.append(main);
  return li;
}

/** The existing project list (the board above it is the plan view). */
function listCard() {
  const card = el("div", "card card-wide pj-card");
  const h = el("h2", "", WORDS.title);
  card.append(h, el("p", "note", WORDS.under));
  if (state.error && !state.list) {
    card.append(el("p", "empty failed", `Could not read Projects: ${state.error}.`));
    return card;
  }
  const v = state.list;
  if (!v) {
    card.append(el("p", "empty", "Reading…"));
    return card;
  }
  if (!v.available) {
    card.append(el("p", "empty", v.why));
    return card;
  }
  if (v.hidden) {
    card.append(hiddenNode(v.hiddenCount));
    return card;
  }
  if (state.error) card.append(el("p", "empty failed", `Could not read it again: ${state.error}.`));
  // The plan board (PM4, 2026-11-21) sits above the list; the list stays the
  // way into a project's instructions, notes and benchmarks, as it was.
  if (v.projects.length) card.append(boardSection(v));
  if (!v.projects.length) card.append(el("p", "empty", v.empty || "No projects yet."));
  else {
    card.append(el("h3", "subhead", PLAN_WORDS.all_projects));
    const rows = el("div", "rows pj-list");
    for (const p of v.projects) {
      const item = el("div", "row-item");
      item.dataset.id = p.id;
      item.append(el("span", "row-tag", p.app ? APP_WORDS.app_project
        : (p.kind === "coding" ? WORDS.coding : WORDS.life)));
      const main = el("div", "row-main");
      main.append(el("span", "row-title", p.name));
      for (const line of projectMeta(p)) main.append(el("span", "row-meta", line));
      item.append(main);
      const actions = el("div", "row-actions");
      const open = button(WORDS.open, () => openProject(p.id), { isLive: false });
      open.setAttribute("aria-label", `${WORDS.open} ${p.name}`);
      actions.append(open);
      item.append(actions);
      rows.append(item);
    }
    card.append(rows);
  }
  // New project.
  card.append(el("h3", "subhead", WORDS.new));
  const form = el("form", "todo-form pj-new");
  form.autocomplete = "off";
  const name = el("input", "field todo-text");
  name.type = "text";
  name.maxLength = 60;
  name.id = "projects-new-name";
  name.placeholder = WORDS.name;
  name.setAttribute("aria-label", WORDS.name);
  const kind = el("select", "field");
  kind.id = "projects-new-kind";
  kind.setAttribute("aria-label", "Kind of project");
  for (const [value, label] of [["life", WORDS.kind_life], ["coding", WORDS.kind_coding],
    ["app-web", APP_WORDS.new_app_web], ["app-android", APP_WORDS.new_app_android]]) {
    const o = el("option", "", label);
    o.value = value;
    kind.append(o);
  }
  const create = el("button", "btn small", WORDS.create);
  create.type = "submit";
  live.add(create);
  syncLive(create);
  form.append(name, kind, create);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    createProject(name, kind);
  });
  card.append(form);
  if (v.projects.length >= v.max) {
    create.dataset.off = "true";
    syncLive(create);
    card.append(el("p", "note", `There are already ${v.max} projects - delete one first.`));
  }
  if (v.unlinked && v.unlinked.length) {
    card.append(el("h3", "subhead", APP_WORDS.adopt_title), el("p", "note", APP_WORDS.adopt_under));
    const rows = el("div", "rows pj-unlinked");
    for (const a of v.unlinked) {
      const item = el("div", "row-item");
      item.dataset.app = a.name;
      item.append(el("span", "row-tag", APP_WORDS.app_project));
      const main = el("div", "row-main");
      main.append(el("span", "row-title", a.title), el("span", "row-meta", appTypeWords(a.type)));
      item.append(main);
      const actions = el("div", "row-actions");
      const add = button(APP_WORDS.adopt, () => adoptApp(a));
      add.setAttribute("aria-label", `${APP_WORDS.adopt} ${a.title}`);
      if (v.projects.length >= v.max) {
        add.dataset.off = "true";
        syncLive(add);
      }
      actions.append(add);
      item.append(actions);
      rows.append(item);
    }
    card.append(rows);
  }
  return card;
}

function projectCard(p) {
  const card = el("div", "card card-wide pj-card pj-project");
  card.dataset.id = p.id;
  const top = el("div", "pj-top");
  top.append(button(`← ${WORDS.back}`, backToList, { isLive: false, ghost: true }));
  card.append(top);
  const h = el("h2", "", p.name);
  h.id = "projects-heading";
  h.tabIndex = -1;
  card.append(h);
  card.append(el("p", "note", p.app ? APP_WORDS.new_app
    : (p.kind === "coding" ? WORDS.kind_coding : WORDS.kind_life)));
  if (state.error) card.append(el("p", "empty failed", `Could not read it again: ${state.error}.`));

  // How Jarvis should work on this, and the notes.
  const draft = state.drafts[p.id] || {};
  const instructions = el("textarea", "field pj-text");
  instructions.id = "projects-instructions";
  instructions.maxLength = Number(p.max.instructions) || 1500;
  instructions.rows = 4;
  instructions.value = draft.instructions ?? p.instructions;
  const notes = el("textarea", "field pj-text");
  notes.id = "projects-notes";
  notes.rows = 3;
  notes.value = draft.notes ?? p.notes.join("\n");
  const keep = () => {
    state.drafts[p.id] = { instructions: instructions.value, notes: notes.value };
  };
  instructions.addEventListener("input", keep);
  notes.addEventListener("input", keep);
  card.append(labelled(WORDS.instructions, instructions, WORDS.instructions_under));
  card.append(labelled(WORDS.notes, notes, WORDS.notes_under));
  const saveRow = el("div", "row");
  saveRow.append(button(WORDS.save, () => saveText(p, instructions, notes)));
  card.append(saveRow);

  // An app Jarvis builds: its version, its tasks. It has no folder.
  if (p.app) card.append(appSection(p));

  // The folder: coding projects, chosen on this PC with the picker.
  if (p.kind === "coding" && !p.app) {
    card.append(el("h3", "subhead", WORDS.folder));
    card.append(el("p", "pj-line", p.folder ? p.folder.path : WORDS.folder_none));
    if (p.folder && !p.folder.listed) card.append(el("p", "pj-warn", p.folder.said));
    const row = el("div", "row");
    row.append(button(WORDS.folder_choose, () => chooseFolder(p)));
    if (p.folder) {
      row.append(button(WORDS.folder_clear, () =>
        write("update", { project: p.id, body: { folder: null } }, { done: "Cleared." })));
    }
    card.append(row, el("p", "note", WORDS.folder_under));
  }

  // Shareable: ON asks with a card (the PC raises it); OFF is instant.
  card.append(el("h3", "subhead", WORDS.shareable));
  const switchBox = el("input", "");
  switchBox.type = "checkbox";
  switchBox.id = "projects-shareable";
  switchBox.setAttribute("role", "switch");
  switchBox.checked = p.shareable;
  switchBox.setAttribute("aria-checked", String(p.shareable));
  if (p.shareable) switchBox.dataset.heldOff = "true";    // OFF is never held
  if (p.shareableWaiting) switchBox.dataset.off = "true";
  live.add(switchBox);
  syncLive(switchBox);
  switchBox.addEventListener("change", () => setShareable(p, switchBox.checked, switchBox));
  const sw = el("label", "lbl check pj-switch");
  sw.append(switchBox, el("span", "", WORDS.shareable));
  card.append(sw, el("p", "note", WORDS.shareable_under));
  if (p.shareableWaiting) card.append(el("p", "pj-warn", WORDS.waiting_card));
  else if (p.shareableLast) card.append(el("p", "pj-line", p.shareableLast));

  // The work list: a named list on the one scheduler.
  card.append(el("h3", "subhead", WORDS.work_list));
  card.append(el("p", "pj-line", p.workList ? p.workList.title : WORDS.work_list_none));
  if (p.workList) {
    card.append(el("p", "note", fill(WORDS.work_list_under, { name: p.workList.title.toLowerCase() })));
  }

  // Benchmarks.
  card.append(el("h3", "subhead", WORDS.benchmarks));
  if (!p.benchList.length) card.append(el("p", "empty", WORDS.benchmarks_empty));
  for (const b0 of p.benchList) card.append(benchBlock(p, state.points[b0.id] || b0));
  card.append(addBenchForm(p));

  const end = el("div", "row pj-end");
  end.append(button(WORDS.delete_project, () => deleteProject(p), { danger: true }));
  card.append(end);
  return card;
}

/** An app project's App section: version, open tasks, Start a task. */
function appSection(p) {
  const app = p.app;
  const box = el("section", "pj-app");
  box.setAttribute("aria-label", APP_WORDS.section);
  box.append(el("h3", "subhead", APP_WORDS.section));
  box.append(el("p", "pj-line", `${appTypeWords(app.type)}${app.title ? ` - ${app.title}` : ""}`));
  for (const line of versionLines(app)) {
    const l = el("p", app.gitOk ? "pj-line" : "pj-warn", line);
    if (app.gitOk) l.classList.add("pj-version");
    box.append(l);
  }
  box.append(el("p", "note", APP_WORDS.files_where), el("p", "note", APP_WORDS.only_here));
  if (app.mergeWaiting) box.append(el("p", "pj-warn pj-merge-waiting", WORDS.waiting_card));
  else if (app.last && app.last.message) {
    const l = el("p", "pj-line pj-merge-last", app.last.message);
    l.dataset.outcome = app.last.outcome;
    box.append(l);
  }
  box.append(el("h4", "pj-bench-name", APP_WORDS.tasks));
  if (!app.tasks.length) box.append(el("p", "empty", APP_WORDS.tasks_empty));
  else {
    const rows = el("div", "rows pj-tasks");
    for (const t of app.tasks) {
      const item = el("div", "row-item");
      item.dataset.task = t.task;
      const main = el("div", "row-main");
      main.append(el("span", "row-title", t.title), el("span", "row-meta", taskChange(t)));
      if (t.olderMain) main.append(el("span", "row-meta pj-older", APP_WORDS.task_older));
      if (t.waiting || app.mergeWaiting === t.task) {
        main.append(el("span", "row-meta pj-warn", APP_WORDS.task_waiting));
      }
      item.append(main);
      const actions = el("div", "row-actions");
      const open = button(APP_WORDS.task_open, () => openTask(t.task), { isLive: false });
      open.setAttribute("aria-label", `${APP_WORDS.task_open}: ${t.title}`);
      actions.append(open);
      item.append(actions);
      rows.append(item);
    }
    box.append(rows);
  }
  if (app.gitOk) {
    const form = el("form", "todo-form pj-start");
    form.autocomplete = "off";
    const title = el("input", "field todo-text");
    title.type = "text";
    title.maxLength = 120;
    title.id = "projects-task-title";
    title.placeholder = APP_WORDS.start_title;
    title.setAttribute("aria-label", APP_WORDS.start_title);
    const go = el("button", "btn small", APP_WORDS.start_task);
    go.type = "submit";
    live.add(go);
    syncLive(go);
    form.append(title, go);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      startTask(p, title);
    });
    box.append(form, el("p", "note", APP_WORDS.start_under));
  }
  return box;
}

/**
 * One task: its files, the WHOLE change (added lines green, removed red, all
 * text), Merge, Discard, and the paste box. The change is set with
 * textContent, line by line, and nothing else keeps it.
 */
function taskCard(p, t) {
  const card = el("div", "card card-wide pj-card pj-task");
  card.dataset.id = p.id;
  card.dataset.task = t.task;
  const top = el("div", "pj-top");
  top.append(button(`← ${APP_WORDS.back_project}`, backToProject, { isLive: false, ghost: true }));
  card.append(top);
  const h = el("h2", "", t.title);
  h.id = "projects-task-heading";
  h.tabIndex = -1;
  card.append(h);
  card.append(el("p", "note", `${p.name} - ${taskChange(t)}`));
  if (state.error) card.append(el("p", "empty failed", `Could not read it again: ${state.error}.`));
  if (t.source === "pasted") card.append(el("p", "pj-line", APP_WORDS.merge_pasted));
  if (t.olderMain) card.append(el("p", "pj-warn pj-older", `This task was ${APP_WORDS.task_older}.`));
  const app = p.app || { mergeWaiting: "", tasks: [] };
  const offer = mergeOffer(app, t);
  if (offer.waiting) card.append(el("p", "pj-warn", WORDS.waiting_card));
  else if (app.last && app.last.task === t.task && app.last.message) {
    card.append(el("p", "pj-line pj-merge-last", app.last.message));
  }

  card.append(el("h3", "subhead", APP_WORDS.task_files_title));
  if (!t.list.length) card.append(el("p", "empty", APP_WORDS.task_diff_empty));
  else {
    const rows = el("div", "rows pj-task-files");
    for (const f of t.list) {
      const item = el("div", "row-item");
      const main = el("div", "row-main");
      main.append(el("span", "row-title pj-path", f.path),
        el("span", "row-meta", `+${f.added} -${f.removed}`));
      item.append(main);
      rows.append(item);
    }
    card.append(rows);
  }

  card.append(el("h3", "subhead", APP_WORDS.task_diff_title));
  if (t.diff) {
    card.append(el("p", "note", APP_WORDS.task_diff_under));
    card.append(diffBlock(t.diff));
  } else card.append(el("p", "empty", t.refused || APP_WORDS.task_diff_empty));
  if (t.refused && t.diff) card.append(el("p", "pj-warn", t.refused));

  const row = el("div", "row pj-task-actions");
  const merge = button(APP_WORDS.merge, () => mergeTask(p, t), { title: offer.ok ? APP_WORDS.merge_how : offer.why });
  merge.id = "projects-task-merge";
  if (!offer.ok) {
    merge.dataset.off = "true";
    syncLive(merge);
  }
  const discard = button(APP_WORDS.discard, () => discardTask(p, t), { danger: true });
  discard.id = "projects-task-discard";
  row.append(merge, discard);
  card.append(row);
  card.append(el("p", "note", offer.ok ? APP_WORDS.merge_how : offer.why));

  // Paste a change in: this PC only (the phone has no such box).
  card.append(el("h3", "subhead", APP_WORDS.paste));
  const area = el("textarea", "field pj-text pj-paste");
  area.id = "projects-paste";
  area.rows = 6;
  area.spellcheck = false;
  area.setAttribute("aria-label", APP_WORDS.paste);
  area.value = state.pastes[t.task] || "";
  area.addEventListener("input", () => {
    state.pastes[t.task] = area.value;
  });
  card.append(area, el("p", "note", APP_WORDS.paste_under));
  const prow = el("div", "row");
  const add = button(APP_WORDS.paste_button, () => pasteChange(p, t, area));
  add.id = "projects-paste-go";
  if (offer.waiting) {
    add.dataset.off = "true";
    syncLive(add);
  }
  prow.append(add);
  card.append(prow);
  return card;
}

/** The whole change as text: one span per line, coloured by its first character. */
function diffBlock(diff) {
  const pre = el("pre", "pj-diff");
  pre.id = "projects-diff";
  pre.tabIndex = 0;
  pre.setAttribute("role", "region");
  pre.setAttribute("aria-label", APP_WORDS.task_diff_title);
  const lines = String(diff).split("\n");
  const frag = document.createDocumentFragment();
  lines.forEach((line, i) => {
    const span = el("span", `pj-d pj-d-${diffLineKind(line)}`);
    span.textContent = i < lines.length - 1 ? `${line}\n` : line;
    frag.append(span);
  });
  pre.append(frag);
  return pre;
}

function benchBlock(p, b) {
  const box = el("section", "pj-bench");
  box.dataset.id = b.id;
  box.setAttribute("aria-label", b.name);
  const head = el("div", "pj-bench-head");
  head.append(el("h4", "pj-bench-name", b.name));
  if (b.keepOnScreen) {
    const tag = el("span", "row-tag pj-private", WORDS.private_label);
    tag.dataset.state = "warn";
    if (b.keepOnScreenWords) tag.title = b.keepOnScreenWords;
    head.append(tag);
  }
  box.append(head);

  if (b.kind === "command") {
    box.append(el("code", "pj-command", b.command));
    box.append(el("p", "note", b.notRunnableWhy));
    if (p.app) box.append(el("p", "note pj-cant-run", APP_WORDS.cant_run));
  }

  if (b.latest) {
    const line = el("p", "pj-latest");
    line.append(el("span", "pj-latest-label", `${WORDS.latest}: `),
      el("strong", "", withUnit(b.latest.value, b.unit)));
    if (b.said) line.append(el("span", "pj-change", ` · ${b.said}`));
    if (b.targetReached) line.append(el("span", "pj-change", " · Target reached."));
    box.append(line);
  }
  box.append(chart(b));

  // The numbers themselves, newest first, each with Remove (a typo).
  if (b.points && b.points.length) {
    const details = el("details", "pj-numbers");
    details.append(el("summary", "", `Numbers (${b.points.length})`));
    const rows = el("div", "rows");
    for (const point of [...b.points].reverse().slice(0, 30)) {
      const item = el("div", "row-item");
      item.append(el("span", "row-tag", shortDate(point.at)));
      const main = el("div", "row-main");
      main.append(el("span", "row-title", withUnit(point.value, b.unit)));
      item.append(main);
      const actions = el("div", "row-actions");
      const rm = button(WORDS.remove_number, () => removeNumber(p, b, point), { ghost: true });
      rm.setAttribute("aria-label", `${WORDS.remove_number}: ${shortDate(point.at)}`);
      actions.append(rm);
      item.append(actions);
      rows.append(item);
    }
    details.append(rows);
    box.append(details);
  }

  if (b.kind === "number") {
    const form = el("form", "todo-form pj-log");
    form.autocomplete = "off";
    const field = el("input", "field todo-text");
    field.type = "text";
    field.inputMode = "decimal";
    field.placeholder = b.unit ? `${WORDS.log_value} (${b.unit})` : WORDS.log_value;
    field.setAttribute("aria-label", `${WORDS.log_value} for ${b.name}`);
    const go = el("button", "btn small", WORDS.log);
    go.type = "submit";
    live.add(go);
    syncLive(go);
    form.append(field, go);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      logNumber(p, b, field);
    });
    box.append(form);
  }

  // The private mark.
  const marks = el("div", "row pj-marks");
  const offer = unmarkOffer(b);
  if (offer) {
    marks.append(button(offer.label, () => unmark(p, b), { title: offer.why }));
  } else if (!b.keepOnScreen) {
    marks.append(button(WORDS.mark_private, () => markPrivate(p, b), { ghost: true }));
  }
  marks.append(button(WORDS.delete_bench, () => deleteBench(p, b), { danger: true }));
  box.append(marks);
  if (offer) box.append(el("p", "note", offer.why));
  if (b.unmarkWaiting) box.append(el("p", "pj-warn", WORDS.waiting_card));
  else if (b.unmarkLast) box.append(el("p", "pj-line", b.unmarkLast));
  return box;
}

/** The chart: dated points, a line through them, and the target as a dashed line. */
function chart(b) {
  const W = 320;
  const H = 120;
  const pts = b.points || (b.latest ? [b.latest] : []);
  if (!pts.length) return el("p", "empty pj-chart-empty", WORDS.chart_empty);
  const f = b.forecast;
  const g = chartGeometry(pts, b.target, W, H, 8, f);
  const svg = document.createElementNS(SVG, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("class", "pj-chart");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", `${b.name}: ${chartSummary(b)}`);
  const poly = (coords, cls) => {
    const p = document.createElementNS(SVG, "polygon");
    p.setAttribute("points", coords.map((q) => `${q.x.toFixed(1)},${q.y.toFixed(1)}`).join(" "));
    p.setAttribute("class", cls);
    return p;
  };
  const line = (x1, y1, x2, y2, cls) => {
    const l = document.createElementNS(SVG, "line");
    l.setAttribute("x1", x1);
    l.setAttribute("y1", y1);
    l.setAttribute("x2", x2);
    l.setAttribute("y2", y2);
    l.setAttribute("class", cls);
    return l;
  };
  svg.append(line(0, H - 0.5, W, H - 0.5, "pj-axis"));
  if (g.target !== null) {
    svg.append(line(0, g.target, W, g.target, "pj-target"));
  }
  if (g.forecast) {
    // The guess, under the numbers: a translucent triangle, its dashed
    // edge, the dashed trend line, a bracket on the target and an arrow
    // where the drawing stops short. Decoration only - the words carry it.
    const fc = g.forecast;
    const group = document.createElementNS(SVG, "g");
    group.setAttribute("class", "pj-forecast");
    group.setAttribute("aria-hidden", "true");
    group.append(poly(fc.band, "pj-band"));
    group.append(line(fc.line.x1, fc.line.y1, fc.line.x2, fc.line.y2, "pj-trend"));
    if (fc.bracket) {
      const { x1, x2, y } = fc.bracket;
      const cls = "pj-bracket";
      group.append(line(x1, y, x2, y, cls), line(x1, y - 4, x1, y + 4, cls),
        line(x2, y - 4, x2, y + 4, cls));
    }
    for (const a of fc.arrows) {
      const chevron = document.createElementNS(SVG, "polyline");
      chevron.setAttribute("points",
        `${(a.x - 5).toFixed(1)},${(a.y - 4).toFixed(1)} ${a.x.toFixed(1)},${a.y.toFixed(1)} ${(a.x - 5).toFixed(1)},${(a.y + 4).toFixed(1)}`);
      chevron.setAttribute("class", "pj-arrow");
      group.append(chevron);
    }
    svg.append(group);
  }
  if (g.points.length > 1) {
    const path = document.createElementNS(SVG, "polyline");
    path.setAttribute("points", g.points.map((q) => `${q.x.toFixed(1)},${q.y.toFixed(1)}`).join(" "));
    path.setAttribute("class", "pj-line");
    svg.append(path);
  }
  for (const q of g.points) {
    const dot = document.createElementNS(SVG, "circle");
    dot.setAttribute("cx", q.x.toFixed(1));
    dot.setAttribute("cy", q.y.toFixed(1));
    dot.setAttribute("r", "3");
    dot.setAttribute("class", "pj-dot");
    const t = document.createElementNS(SVG, "title");
    t.textContent = `${shortDate(q.at)}: ${withUnit(q.value, b.unit)}`;
    dot.append(t);
    svg.append(dot);
  }
  const wrap = el("figure", "pj-chart-wrap");
  wrap.append(svg);
  const legend = el("figcaption", "pj-legend");
  legend.append(el("span", "pj-legend-range",
    `${numberWords(Math.round(g.lo * 100) / 100)} – ${numberWords(Math.round(g.hi * 100) / 100)}`
    + (b.unit ? ` ${b.unit}` : "")));
  if (b.target !== null) {
    legend.append(el("span", "pj-legend-target", `${WORDS.chart_target}: ${withUnit(b.target, b.unit)}`));
  }
  wrap.append(legend);
  if (f && f.words) {
    // The PC's sentence, as sent, where the "Target" caption is. The
    // chart's label already carries it for a screen reader, so this copy is
    // hidden from one to avoid being read twice. On the owner's screen only.
    const words = el("p", "pj-forecast-words", f.words);
    words.dataset.state = f.state;
    words.setAttribute("aria-hidden", "true");
    wrap.append(words);
    if (f.basis) {
      const basis = el("p", "note pj-forecast-basis", f.basis);
      basis.setAttribute("aria-hidden", "true");
      wrap.append(basis);
    }
  }
  return wrap;
}

function addBenchForm(p) {
  const box = el("details", "pj-add");
  box.append(el("summary", "", WORDS.add_benchmark));
  const form = el("form", "pj-add-form");
  form.autocomplete = "off";
  const input = (id, label, max) => {
    const f = el("input", "field");
    f.type = "text";
    f.id = id;
    if (max) f.maxLength = max;
    return [f, labelled(label, f)];
  };
  const [name, nameBox] = input("projects-bench-name", WORDS.bench_name, 40);
  const [unit, unitBox] = input("projects-bench-unit", WORDS.bench_unit, 16);
  const better = el("select", "field");
  better.id = "projects-bench-better";
  for (const [value, label] of [["", WORDS.better_either], ["higher", WORDS.better_higher],
    ["lower", WORDS.better_lower]]) {
    const o = el("option", "", label);
    o.value = value;
    better.append(o);
  }
  const [target, targetBox] = input("projects-bench-target", WORDS.bench_target, 20);
  target.inputMode = "decimal";
  const row = el("div", "row");
  row.append(nameBox, unitBox, labelled(WORDS.bench_better, better), targetBox);
  form.append(row);
  let kind = null;
  let command = null;
  if (p.kind === "coding") {
    kind = el("select", "field");
    kind.id = "projects-bench-kind";
    for (const [value, label] of [["number", "A number you log"], ["command", "A command on this PC"]]) {
      const o = el("option", "", label);
      o.value = value;
      kind.append(o);
    }
    let commandBox;
    [command, commandBox] = input("projects-bench-command", "Command", 300);
    const row2 = el("div", "row");
    row2.append(labelled("Kind", kind), commandBox);
    form.append(row2, el("p", "note", WORDS.command_on_pc));
  }
  const go = el("button", "btn small", WORDS.add);
  go.type = "submit";
  live.add(go);
  syncLive(go);
  const end = el("div", "row");
  end.append(go);
  form.append(end);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const got = benchBody({
      name: name.value, unit: unit.value, better: better.value, target: target.value,
      kind: kind ? kind.value : "number", command: command ? command.value : "",
    });
    if (got.error) {
      say(got.error, "bad");
      return;
    }
    await write("bench_add", { project: p.id, body: got.body }, { done: "Added." });
  });
  box.append(form);
  return box;
}

/* ── Wiring ───────────────────────────────────────────────────────────── */

onLink(() => syncAllLive());

// A card this page caused (Shareable ON, taking a mark off) is answered in
// the Jarvis bar; when the queue changes while one waits, read it again.
let lastQueue = null;
onQueue((queue) => {
  const n = queue && Number.isFinite(queue.count) ? queue.count : null;
  const changed = lastQueue !== null && n !== lastQueue;
  lastQueue = n;
  const p = state.project;
  const waiting = p && !p.hidden && (p.shareableWaiting || p.benchList.some((b) => b.unmarkWaiting)
    || (p.app && p.app.mergeWaiting));
  const visible = root() && !root().closest("[hidden]");
  if (changed && waiting && visible) showProjects();
});

// Settings changed, or a Show ended: read again - Rust decides whether it
// comes back hidden.
if (TAURI && TAURI.event && TAURI.event.listen) {
  const reread = () => {
    const box = root();
    if (box && !box.closest("[hidden]")) showProjects();
  };
  TAURI.event.listen("security-changed", reread);
  TAURI.event.listen("private-hidden", reread);
}
