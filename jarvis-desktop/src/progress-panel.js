/**
 * Brain -> Projects: the "Progress" section at the top (the owner's tick of
 * 2026-09-30; docs/GOALS-PROGRESS-DESIGN.md part C, "Progress contract
 * (frozen)"; JARVIS-API.md section 105). progress.js holds the geometry and
 * the reading; this draws them into `#progress-root` and sends the one
 * change there is (which 3 to 8 areas the balance chart shows) through
 * `brain_progress_balance_save` (brain/progress.rs).
 *
 * Rules this page keeps:
 * - Hand-drawn SVG only; every colour is a theme token (projects.css), never
 *   red; a quiet day is a plain outline.
 * - Every number and sentence is the PC's, shown as sent (`textContent`
 *   only, never markup). This page works out no shade, week label, value or
 *   total. There is no overall score, no run of days, no share of days.
 * - The pictures are decoration for a screen reader: a week-per-row table
 *   and the list under the balance chart carry the same words.
 * - ONE rule for hidden lists, the same on the phone: when the PC says
 *   `keep_on_screen` and Rust has taken the picture out (private lists hidden,
 *   or App lock locked), only its hidden words and a Show button are drawn -
 *   the same Windows Hello gate Projects uses (when it is App lock that hides
 *   it, Show cannot lift that, and the line says to unlock first). While the
 *   lists are hidden (`lists_hidden`) there is no picker and a save is refused.
 * - Nothing is stored here: not the answers, not the ticks. Not spoken.
 * - The save is greyed on a stale link (rule 4; Rust refuses it too). A
 *   refusal from the PC is shown beside the picker as sent and changes
 *   nothing.
 *
 * @module progress-panel
 */

import { announce, currentLink, linkWords, onLink } from "./jarvis-link.js";
import {
  balanceList,
  canPickMore,
  heatRects,
  heatRows,
  heatSize,
  levelWords,
  pickBody,
  polygonAttr,
  radar,
  RADAR,
  readActivity,
  readBalance,
  readFailedLine,
  SCREEN_WORDS,
  saveState,
  WORDS,
} from "./progress.js";

const SVG = "http://www.w3.org/2000/svg";

const state = {
  activity: null,
  balance: null,
  /** Both routes answered "no such route": the section is not shown at all. */
  missing: false,
  error: "",
  editing: false,
  /** Picker rows: {kind, ref, name, projectName, hidden, picked, label}. */
  rows: [],
  /** The PC's refusal sentence for the last save, as sent. */
  editError: "",
  said: "",
  visible: true,
  reading: false,
  again: false,
  /** Counts the ticks in one edit, so new areas are added in the order ticked. */
  seq: 0,
};

/** Controls that send a change: greyed while the link cannot be confirmed. */
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

function svgEl(tag, attrs = {}, className = "") {
  const node = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, String(v));
  if (className) node.setAttribute("class", className);
  return node;
}

function root() {
  return document.getElementById("progress-root");
}

function canAct() {
  return linkWords(currentLink()).canAct;
}

function syncLive(node) {
  const ok = canAct();
  node.disabled = !ok || node.dataset.off === "true" || node.dataset.busy === "true";
  node.title = ok ? node.dataset.title || "" : "The link to your PC is not confirmed live, so nothing can be sent.";
}

function syncAllLive() {
  for (const n of live) {
    if (!n.isConnected) live.delete(n);
    else syncLive(n);
  }
}

function button(label, onClick, { title = "", isLive = false, ghost = false, fkey = "" } = {}) {
  const b = el("button", `btn small${ghost ? " ghost" : ""}`, label);
  b.type = "button";
  b.dataset.title = title;
  if (title) b.title = title;
  if (fkey) b.dataset.fkey = fkey;
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
      if (b.isConnected) {
        if (isLive) syncLive(b);
        else b.disabled = false;
      }
    }
  });
  return b;
}

function say(message, tone = "") {
  state.said = String(message || "");
  const line = document.getElementById("progress-said");
  if (line) {
    line.textContent = state.said;
    line.dataset.tone = tone;
  }
  if (state.said) announce(state.said, tone === "bad" ? "assertive" : "polite");
}

/* ── Reading ──────────────────────────────────────────────────────────── */

/** `available: false` (an older PC has no such route) or nothing back at all. */
function unavailable(raw) {
  return raw === null || raw === undefined || (raw && raw.available === false);
}

/** Reads both pictures again, then draws them. Errors show as one line. */
export async function refreshProgress() {
  if (state.reading) {
    state.again = true;
    return;
  }
  state.reading = true;
  try {
    const [a, b] = await Promise.allSettled([
      invoke("brain_progress_activity", {}),
      invoke("brain_progress_balance", {}),
    ]);
    const errors = [];
    let none = 0;
    if (a.status === "fulfilled") {
      if (unavailable(a.value)) {
        none += 1;
        state.activity = null;
      } else state.activity = readActivity(a.value);
    } else {
      errors.push(errorText(a.reason));
      state.activity = null;
    }
    if (b.status === "fulfilled") {
      if (unavailable(b.value)) {
        none += 1;
        state.balance = null;
      } else state.balance = readBalance(b.value);
    } else {
      errors.push(errorText(b.reason));
      state.balance = null;
    }
    state.missing = none === 2;
    state.error = errors[0] || "";
    if (state.editing && (!state.balance || state.balance.hidden || state.balance.listsHidden)) {
      state.editing = false;
    }
  } finally {
    state.reading = false;
  }
  paint();
  if (state.again) {
    state.again = false;
    await refreshProgress();
  }
}

/** The section shows on the Projects list, not inside one project. */
export function setProgressVisible(visible) {
  state.visible = Boolean(visible);
  const box = root();
  if (box) box.hidden = !state.visible || state.missing;
}

/* ── Picker ───────────────────────────────────────────────────────────── */

function openEditor() {
  const b = state.balance;
  if (!b) return;
  if (b.listsHidden) return;
  state.seq = 0;
  state.rows = b.choices.map((c) => {
    const at = b.axes.findIndex((a) => a.kind === c.kind && a.ref === c.ref);
    return {
      kind: c.kind, ref: c.ref, name: c.name, projectName: c.projectName, hidden: c.hidden,
      picked: c.picked && !c.hidden, label: at >= 0 ? b.axes[at].label : c.name,
      // Where it is on the chart now (-1: not on it) and when it was ticked in
      // this edit: the chart keeps its order and new areas go after it.
      at: c.picked && !c.hidden ? at : -1, tick: 0,
    };
  });
  state.editError = "";
  state.editing = true;
  paint("edit");
}

function closeEditor() {
  state.editing = false;
  state.editError = "";
  paint("edit-open");
}

async function saveChart() {
  const axes = pickBody(state.rows);
  if (state.balance && state.balance.listsHidden) {
    state.editError = state.balance.hiddenWords;
    paint("save");
    return;
  }
  try {
    const out = await invoke("brain_progress_balance_save", { axes });
    if (out === null) return;
    state.balance = readBalance(out);
    state.editing = false;
    state.editError = "";
    paint("edit-open");
    say(axes.length ? WORDS.saved : WORDS.cleared, "ok");
  } catch (error) {
    // The PC's own sentence, as sent; nothing was stored, so the picker stays.
    state.editError = errorText(error);
    const line = document.getElementById("progress-edit-error");
    if (line) line.textContent = state.editError;
    else paint("save");
    announce(state.editError, "assertive");
  }
}

/* ── Drawing ──────────────────────────────────────────────────────────── */

/** Puts the keyboard back where it was after a repaint, by `data-fkey`. */
function paint(focusKey) {
  const box = root();
  if (!box) return;
  const active = document.activeElement;
  const had = box.contains(active) ? (active.dataset && active.dataset.fkey) || "" : "";
  live.clear();
  box.hidden = !state.visible || state.missing;
  if (state.missing) {
    box.replaceChildren();
    return;
  }
  const card = el("section", "card card-wide pg-card");
  card.setAttribute("aria-labelledby", "progress-heading");
  const h = el("h2", "", WORDS.title);
  h.id = "progress-heading";
  card.append(h);
  if (state.error && !state.activity && !state.balance) {
    card.append(el("p", "empty failed", readFailedLine(state.error)));
  } else {
    if (state.activity) card.append(heatBlock(state.activity));
    if (state.balance) card.append(balanceBlock(state.balance));
    if (state.error) card.append(el("p", "empty failed", readFailedLine(state.error)));
  }
  // After the pictures and the picker, so the keyboard reaches them first. The
  // phone's "Refresh" link does the same: read both pictures again.
  const foot = el("div", "pg-foot");
  foot.append(button(WORDS.refresh, () => refreshProgress(), {
    ghost: true, fkey: "refresh", title: "Read the Progress pictures again",
  }));
  const said = el("p", "pg-said", state.said);
  said.id = "progress-said";
  said.setAttribute("role", "status");
  foot.append(said);
  card.append(foot);
  box.replaceChildren(card);
  restoreFocus(box, focusKey || had);
}

function restoreFocus(box, key) {
  if (!key) return;
  const target = [...box.querySelectorAll("[data-fkey]")].find((n) => n.dataset.fkey === key
    && !n.disabled);
  if (target) target.focus();
}

function hiddenBlock(kind, words) {
  const wrap = el("div", "private-hidden pg-hidden");
  wrap.dataset.kind = kind;
  wrap.append(el("p", "empty", words));
  wrap.append(button(WORDS.show, async () => {
    try {
      await invoke("reveal_private_answers");
    } catch (error) {
      say(errorText(error), "bad");
      return;
    }
    await refreshProgress();
    // "Show" lifts "Hide memory lists" only. When the picture is hidden because
    // App lock is locked, nothing changes: say what to do, not a dead button.
    const still = kind === "activity" ? state.activity : state.balance;
    if (still && still.hidden) say(WORDS.still_hidden, "bad");
  }, { title: SCREEN_WORDS.show_title, fkey: `show:${kind}` }));
  return wrap;
}

/* The heatmap ------------------------------------------------------------ */

function heatBlock(a) {
  const block = el("div", "pg-block pg-heat");
  block.append(el("h3", "subhead", a.title || WORDS.heat_title));
  block.append(el("p", "note", WORDS.heat_under));
  if (a.hidden) {
    block.append(hiddenBlock("activity", a.hiddenWords));
    return block;
  }
  const { width, height } = heatSize(a.weeks);
  const svg = svgEl("svg", {
    viewBox: `0 0 ${width} ${height}`, width, height, "aria-hidden": "true", focusable: "false",
  }, "pg-grid");
  svg.style.maxWidth = "100%";
  const byDate = new Map(a.days.map((d) => [d.date, d]));
  for (const r of heatRects(a.days)) {
    const day = byDate.get(r.date);
    const g = svgEl("g", {}, "pg-day");
    const tip = svgEl("title");
    tip.textContent = day ? day.words : r.date;
    g.append(tip);
    const geometry = { x: r.x, y: r.y, width: r.size, height: r.size, rx: 3 };
    if (r.level > 0) g.append(svgEl("rect", geometry, "pg-base"));
    g.append(svgEl("rect", geometry, `pg-cell pg-l${r.level}`));
    svg.append(g);
  }
  const fig = el("figure", "pg-figure");
  fig.append(svg);
  fig.append(legend(a));
  block.append(fig);
  block.append(el("p", "pg-words", a.words));
  block.append(el("p", "pg-undated", a.note));
  block.append(heatTable(a));
  return block;
}

/** Five swatches, decoration only (the table carries the words). */
function legend(a) {
  const levels = a.levels.length === 5 ? a.levels
    : [0, 1, 2, 3, 4].map((level) => ({ level, min: level, max: level === 4 ? null : level }));
  const size = 10;
  const svg = svgEl("svg", {
    viewBox: `0 0 ${levels.length * (size + 4) - 4} ${size}`,
    width: levels.length * (size + 4) - 4, height: size, "aria-hidden": "true", focusable: "false",
  }, "pg-legend");
  levels.forEach((lv, i) => {
    const geometry = { x: i * (size + 4), y: 0, width: size, height: size, rx: 2 };
    const g = svgEl("g", {}, "pg-day");
    const tip = svgEl("title");
    tip.textContent = levelWords(lv);
    g.append(tip);
    if (i > 0) g.append(svgEl("rect", geometry, "pg-base"));
    g.append(svgEl("rect", geometry, `pg-cell pg-l${i}`));
    svg.append(g);
  });
  return svg;
}

/** The week-per-row table for a screen reader: "Week of 6 Oct" rows. */
function heatTable(a) {
  const table = el("table", "pg-table");
  table.append(el("caption", "", a.summary || `${WORDS.heat_title}. ${a.words}`));
  const head = el("tr");
  const corner = el("th", "", SCREEN_WORDS.week_col);
  corner.scope = "col";
  head.append(corner);
  for (const day of SCREEN_WORDS.days) {
    const th = el("th", "", day);
    th.scope = "col";
    head.append(th);
  }
  const thead = el("thead");
  thead.append(head);
  const tbody = el("tbody");
  for (const week of heatRows(a)) {
    const tr = el("tr");
    const th = el("th", "", week.label);
    th.scope = "row";
    tr.append(th);
    for (const words of week.cells) tr.append(el("td", "", words));
    tbody.append(tr);
  }
  table.append(thead, tbody);
  // A table ignores a one pixel width, so the visually hidden box is its wrapper.
  const hidden = el("div", "sr-only");
  hidden.append(table);
  return hidden;
}

/* The balance chart ------------------------------------------------------ */

function balanceBlock(b) {
  const block = el("div", "pg-block pg-balance");
  block.append(el("h3", "subhead", b.title || WORDS.balance_title));
  block.append(el("p", "note", WORDS.balance_under));
  if (b.hidden) {
    block.append(hiddenBlock("balance", b.hiddenWords));
    return block;
  }
  if (b.words) block.append(el("p", "pg-words", b.words));
  const list = balanceList(b);
  if (b.axes.length) {
    const fig = el("figure", "pg-figure");
    if (b.drawable) fig.append(radarSvg(b));
    const cap = el("figcaption", "sr-only", b.summary);
    fig.append(cap);
    block.append(fig);
    const ul = el("ul", "pg-list");
    for (const row of list) {
      const li = el("li", "pg-item");
      li.append(el("span", "pg-item-label", row.label));
      if (row.value) li.append(document.createTextNode(": "), el("span", "pg-item-value", row.value));
      if (row.private) li.append(document.createTextNode(" "), el("span", "pg-private", WORDS.private));
      ul.append(li);
    }
    block.append(ul);
  }
  // No picker while the lists are hidden: the same rule as the phone.
  if (b.listsHidden) return block;
  block.append(state.editing ? editor(b) : editButton(b));
  return block;
}

function editButton() {
  const wrap = el("div", "pg-actions");
  wrap.append(button(WORDS.balance_edit, () => openEditor(), { fkey: "edit-open" }));
  return wrap;
}

/** The radar: rings, spokes, shape, dots and labels. Decorative to a reader. */
function radarSvg(b) {
  const g = radar(b.axes.map((a) => a.fraction));
  const c = RADAR.centre;
  const svg = svgEl("svg", {
    viewBox: "-60 -12 380 304", role: "presentation", "aria-hidden": "true", focusable: "false",
  }, "pg-radar");
  g.rings.forEach((r, i) => {
    svg.append(svgEl("circle", { cx: c, cy: c, r }, i === g.rings.length - 1 ? "pg-ring pg-target" : "pg-ring"));
  });
  for (const s of g.spokes) {
    svg.append(svgEl("line", { x1: c, y1: c, x2: s.x, y2: s.y }, "pg-spoke"));
  }
  svg.append(svgEl("polygon", { points: polygonAttr(g) }, "pg-shape"));
  g.polygon.forEach((p) => {
    if (p.dot) svg.append(svgEl("circle", { cx: p.x, cy: p.y, r: RADAR.dotRadius }, "pg-empty-dot"));
    else svg.append(svgEl("circle", { cx: p.x, cy: p.y, r: 3 }, "pg-vertex"));
  });
  g.labels.forEach((l, i) => {
    const axis = b.axes[i];
    // A label above the picture sits one line higher, so its second line
    // (the value) clears the outer ring instead of crossing it.
    const above = l.anchor === "middle" && g.spokes[i].y < c;
    const y = above ? l.y - 12 : l.y;
    const t = svgEl("text", { x: l.x, y, "text-anchor": l.anchor }, "pg-label");
    t.append(document.createTextNode(axis.short));
    const value = svgEl("tspan", { x: l.x, dy: "1.25em" }, "pg-value");
    value.textContent = axis.valueWords || (axis.state === "no_numbers" ? WORDS.no_numbers : "");
    t.append(value);
    svg.append(t);
  });
  return svg;
}

/* The picker ------------------------------------------------------------- */

function pickedCount() {
  return state.rows.filter((r) => r.picked).length;
}

function editor(b) {
  const form = el("form", "pg-editor");
  form.autocomplete = "off";
  form.setAttribute("aria-label", WORDS.balance_edit);
  form.append(el("p", "note", WORDS.balance_limit));
  if (!state.rows.length) {
    form.append(el("p", "empty", WORDS.no_choices));
  }
  const list = el("div", "pg-picks");
  for (const row of state.rows) list.append(pickRow(row, b));
  form.append(list);
  const err = el("p", "pg-edit-error", state.editError);
  err.id = "progress-edit-error";
  err.setAttribute("role", "alert");
  form.append(err);
  const actions = el("div", "pg-actions");
  const save = el("button", "btn small", WORDS.balance_save);
  save.type = "submit";
  save.id = "progress-save";
  save.dataset.fkey = "save";
  live.add(save);
  actions.append(save, button(SCREEN_WORDS.cancel, () => closeEditor(), { ghost: true, fkey: "cancel" }));
  form.append(actions);
  const sync = () => {
    const mode = saveState(pickedCount(), b.min, b.max);
    save.textContent = mode === "clear" ? WORDS.balance_clear : WORDS.balance_save;
    save.dataset.off = mode === "off" ? "true" : "false";
    syncLive(save);
    for (const box of form.querySelectorAll("input[type=checkbox]")) {
      const r = state.rows.find((x) => `${x.kind}:${x.ref}` === box.dataset.key);
      box.disabled = Boolean(r && (r.hidden || (!r.picked && !canPickMore(pickedCount(), b.max))));
    }
    for (const name of form.querySelectorAll(".pg-rename")) {
      const r = state.rows.find((x) => `${x.kind}:${x.ref}` === name.dataset.key);
      name.hidden = !(r && r.picked);
    }
  };
  form.addEventListener("change", (event) => {
    const box = event.target;
    if (!box || box.type !== "checkbox") return;
    const r = state.rows.find((x) => `${x.kind}:${x.ref}` === box.dataset.key);
    if (r && !r.hidden) {
      r.picked = box.checked;
      // Ticked: after the areas already on the chart, in the order ticked.
      // Unticked: it gives up its place, so ticking it again adds it at the end.
      r.at = -1;
      r.tick = box.checked ? (state.seq += 1) : 0;
    }
    sync();
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (save.disabled) return;
    save.dataset.busy = "true";
    save.disabled = true;
    try {
      await saveChart();
    } finally {
      save.dataset.busy = "false";
      if (save.isConnected) sync();
    }
  });
  sync();
  return form;
}

function pickRow(row, b) {
  const key = `${row.kind}:${row.ref}`;
  const item = el("div", "pg-pick");
  const label = el("label", "pg-pick-label");
  const box = el("input");
  box.type = "checkbox";
  box.checked = row.picked;
  box.dataset.key = key;
  box.dataset.fkey = `pick:${key}`;
  label.append(box);
  const words = el("span", "pg-pick-words");
  words.append(el("span", "pg-pick-name", row.hidden ? SCREEN_WORDS.hidden_choice : row.name));
  if (row.projectName && !row.hidden) words.append(el("span", "pg-pick-project", row.projectName));
  label.append(words);
  item.append(label);
  if (!row.hidden) {
    const name = el("input", "field pg-rename");
    name.type = "text";
    name.maxLength = b.maxLabel;
    name.value = row.label;
    name.dataset.key = key;
    name.dataset.fkey = `name:${key}`;
    name.setAttribute("aria-label", `${WORDS.balance_rename}: ${row.name}`);
    name.placeholder = row.name;
    name.hidden = !row.picked;
    name.addEventListener("input", () => {
      row.label = name.value;
    });
    item.append(name);
  }
  return item;
}

/* ── Wiring ───────────────────────────────────────────────────────────── */

onLink(() => syncAllLive());
