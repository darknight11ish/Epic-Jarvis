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
import {
  APP_WORDS,
  appProjectBody,
  appTypeWords,
  benchBody,
  chartGeometry,
  chartSummary,
  diffLineKind,
  fill,
  mergeOffer,
  notesFrom,
  numberWords,
  pasteBody,
  projectMeta,
  readBench,
  readList,
  readProject,
  readTask,
  shortDate,
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
    if (!state.error) state.readAt = Date.now();
  } finally {
    state.reading = false;
  }
  paint();
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
  if (!v.projects.length) card.append(el("p", "empty", v.empty || "No projects yet."));
  else {
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
  const g = chartGeometry(pts, b.target, W, H);
  const svg = document.createElementNS(SVG, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("class", "pj-chart");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", `${b.name}: ${chartSummary(b)}`);
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
  if (g.points.length > 1) {
    const poly = document.createElementNS(SVG, "polyline");
    poly.setAttribute("points", g.points.map((q) => `${q.x.toFixed(1)},${q.y.toFixed(1)}`).join(" "));
    poly.setAttribute("class", "pj-line");
    svg.append(poly);
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
