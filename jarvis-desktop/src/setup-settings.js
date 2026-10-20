/**
 * Settings -> "First-time setup" (JARVIS-API section 147; the PC's module is
 * `backend/jarvis_setup.py`, its routes are installed by `setup.patch`).
 *
 * The fourteen questions, in the PC's own words, in one card. The owner picks
 * answers, the page asks the PC for a READ-ONLY plan (`POST /api/setup/plan`),
 * and the plan is drawn beside the questions: every change with the PC's own
 * sentence and its effect - Instant, Asks you on a card, or Blocked - plus
 * everything the PC says would NOT change and why.
 *
 * THE ONE ACTION. "Apply these changes" is the only control that writes, and
 * it takes TWO presses: the first shows the confirm step with the plan's own
 * count ("3 changes - 1 of them will ask you on a card"), the second calls
 * `applySetup(applyBody(draft))`, which is the only body in the app carrying
 * `confirm: true`. There is no apply on load, on a link reconnect, on a
 * changed answer or on a timer. `load()` never calls `applySetup()`, and the
 * suite pins that.
 *
 * HONEST WAITING. The PC works through the changes one at a time and waits on
 * each existing approval card, so applying can take minutes. The card says so
 * before the press and while it runs, and a card still waiting when the PC's
 * patience runs out is drawn as STILL WAITING - never as done and never as
 * failed. Nothing here approves a card.
 *
 * `setup-questionnaire.js` owns every rule and every word that can be tested
 * without a browser; this file only paints it and sends the two calls.
 */
import { currentLink, onLink } from "./jarvis-link.js";
import { applySetup, planSetup, readSetup } from "./setup-bridge.js";
import {
  ALL,
  APPLY,
  APPLYING,
  APPLY_BUSY,
  CANCEL,
  CONFIRM,
  HELP,
  KICKER,
  LAST_RUN_HEADING,
  NONE,
  NOTHING_CHANGED,
  NOTHING_TO_APPLY,
  PLAN_HEADING,
  PLAN_READING,
  RECOMMENDATION_HEADING,
  SKIPPED_HEADING,
  TITLE,
  allNoneState,
  answeredCount,
  applyBody,
  applyView,
  cardWaitWords,
  chooseAll,
  chooseNone,
  chooseOne,
  confirmWords,
  draftFromAnswers,
  gate,
  lastRunView,
  normaliseReading,
  optionOn,
  planBody,
  planView,
  toggleOption,
} from "./setup-questionnaire.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);
const PLAN_DEBOUNCE_MS = 250;

const $ = (id) => document.getElementById(id);

const el = {
  body: $("sq-body"),
  reading: $("sq-reading"),
  title: $("sq-title"),
  kicker: $("sq-kicker"),
  help: $("sq-help"),
  questions: $("sq-questions"),
  planStatus: $("sq-plan-status"),
  plan: $("sq-plan"),
  counts: $("sq-counts"),
  apply: $("sq-apply"),
  applyWhy: $("sq-apply-why"),
  confirm: $("sq-confirm"),
  confirmText: $("sq-confirm-text"),
  confirmYes: $("sq-confirm-yes"),
  confirmNo: $("sq-confirm-no"),
  result: $("sq-result"),
  last: $("sq-last"),
  about: $("sq-about"),
  storage: $("sq-storage"),
  cardWait: $("sq-card-wait"),
  status: $("sq-status"),
};

let reading = null;
let draft = {};
let plan = null;
let busy = false;
let pending = false;
let planTimer = 0;
/** Bumped whenever the plan on screen stops being the one that was asked for
 *  (an answer changed, the card was re-read). A plan answer that arrives after
 *  that is thrown away - two requests can finish out of order, and the older
 *  plan must never overwrite the newer one. */
let planGeneration = 0;
let lastResult = null;

function live() {
  try {
    return !Boolean(currentLink() && currentLink().stale);
  } catch {
    return false;
  }
}

function say(text, tone) {
  if (!el.status) return;
  el.status.textContent = text || "";
  if (tone) el.status.dataset.tone = tone;
  else delete el.status.dataset.tone;
}

function node(tag, className, text) {
  const made = document.createElement(tag);
  if (className) made.className = className;
  if (text !== undefined && text !== null) made.textContent = String(text);
  return made;
}

/* ── The questions ───────────────────────────────────────────────────────── */

function optionRow(question, option) {
  const wrap = node("label", "toggle");
  const input = document.createElement("input");
  input.type = question.multi ? "checkbox" : "radio";
  input.name = `sq-q-${question.id}`;
  input.value = option.id;
  input.dataset.option = option.id;
  const text = node("span", "", option.label);
  if (option.detail) text.append(node("span", "toggle-detail", option.detail));
  wrap.append(input, text);
  input.addEventListener("change", () => {
    if (!reading || busy) return;
    if (question.multi) {
      draft = toggleOption(draft, question, option.id);
    } else {
      draft = chooseOne(draft, question.id, option.id);
    }
    onAnswered();
  });
  return wrap;
}

function allNoneRow(question) {
  if (!question.allNone) return null;
  const row = node("div", "choices");
  const all = node("button", "choice", ALL);
  all.type = "button";
  all.addEventListener("click", () => {
    if (!reading || busy) return;
    draft = chooseAll(draft, question.id);
    onAnswered();
  });
  const none = node("button", "choice", NONE);
  none.type = "button";
  none.addEventListener("click", () => {
    if (!reading || busy) return;
    draft = chooseNone(draft, question.id);
    onAnswered();
  });
  all.dataset.pick = "all";
  none.dataset.pick = "none";
  row.append(all, none);
  return row;
}

function questionRow(question) {
  const box = node("div", "fr-row");
  box.dataset.question = question.id;
  box.append(node("h3", "subhead", question.title));
  if (question.help) box.append(node("p", "note", question.help));
  const controls = node("div", "fr-controls");
  const list = node("div", "fr-choices");
  for (const option of question.options) list.append(optionRow(question, option));
  controls.append(list);
  const allNone = allNoneRow(question);
  if (allNone) controls.append(allNone);
  box.append(controls);
  return box;
}

/** Bring the drawn controls in line with the draft, without rebuilding them. */
function syncQuestion(question) {
  const box = el.questions && el.questions.querySelector(`[data-question="${question.id}"]`);
  if (!box) return;
  for (const input of box.querySelectorAll("input[data-option]")) {
    input.checked = optionOn(draft, question, input.dataset.option);
  }
  const row = box.querySelector(".choices");
  const state = allNoneState(draft, question.id);
  if (row) {
    for (const button of row.querySelectorAll("[data-pick]")) {
      button.setAttribute("aria-pressed", button.dataset.pick === state ? "true" : "false");
    }
  }
}

function paintQuestions() {
  if (!el.questions) return;
  el.questions.replaceChildren();
  for (const question of (reading && reading.questions) || []) {
    el.questions.append(questionRow(question));
  }
  renderQuestionsState();
}

function renderQuestionsState() {
  for (const question of (reading && reading.questions) || []) syncQuestion(question);
}

/** While the one apply runs, no answer may change under it: the whole
 *  questionnaire is turned off, visibly, not just ignored by the handlers. */
function setQuestionsEnabled(enabled) {
  if (!el.questions) return;
  for (const input of el.questions.querySelectorAll("input")) input.disabled = !enabled;
  for (const button of el.questions.querySelectorAll("[data-pick]")) {
    button.disabled = !enabled;
  }
}

/* ── The plan (read-only on the PC) ──────────────────────────────────────── */

function planRows(view) {
  if (!el.plan) return;
  el.plan.replaceChildren();
  if (!view || view.ok === false) return;
  const groups = new Map();
  for (const change of view.changes) {
    const key = change.knownQuestion ? change.questionTitle : "Other settings";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(change);
  }
  for (const [title, changes] of groups) {
    const box = node("div", "fr-row");
    box.append(node("h3", "subhead", title));
    for (const change of changes) {
      const line = node("p", "sc-line");
      line.dataset.setting = change.setting;
      line.dataset.effect = change.effect;
      const effect = node("strong", "", `${change.effectWords}: `);
      line.append(effect, document.createTextNode(change.sentence || change.label));
      box.append(line);
    }
    el.plan.append(box);
  }
  if (view.skipped.length) {
    const box = node("div", "fr-row");
    box.append(node("h3", "subhead", SKIPPED_HEADING));
    for (const skip of view.skipped) {
      const line = node("p", "note", skip.reason);
      line.dataset.setting = skip.setting;
      box.append(line);
    }
    el.plan.append(box);
  }
  if (view.recommendation) {
    const box = node("div", "fr-row");
    box.append(node("h3", "subhead", RECOMMENDATION_HEADING));
    box.append(node("p", "note",
      `${view.recommendation.title} - a recommendation only. ${view.recommendation.why}`));
    el.plan.append(box);
  }
}

function countsWords(view) {
  if (!view || view.ok === false) return "";
  const parts = [];
  if (view.counts.instant) parts.push(`${view.counts.instant} instant`);
  if (view.counts.card) parts.push(`${view.counts.card} on a card`);
  if (view.counts.blocked) parts.push(`${view.counts.blocked} blocked`);
  return parts.length ? `${view.changes.length} change${view.changes.length === 1 ? "" : "s"} (${parts.join(", ")})` : "";
}

function syncConfirm() {
  if (!el.confirm) return;
  el.confirm.hidden = !pending;
  if (!pending) return;
  if (el.confirmText) el.confirmText.textContent = confirmWords(plan);
  if (el.confirmYes) {
    el.confirmYes.textContent = CONFIRM;
    // The second press is still held by the same gate as the first: a link
    // that goes stale between the two presses must not send the write.
    el.confirmYes.disabled = !gate({ reading, plan, busy, stale: !live() }).enabled;
  }
  if (el.confirmNo) el.confirmNo.textContent = CANCEL;
}

function paintApply() {
  if (!el.apply) return;
  const gateNow = gate({ reading, plan, busy, stale: !live() });
  el.apply.disabled = !gateNow.enabled;
  el.apply.textContent = busy ? APPLYING : APPLY;
  if (el.applyWhy) {
    el.applyWhy.textContent = gateNow.why;
    el.applyWhy.hidden = !gateNow.why;
  }
  setQuestionsEnabled(!busy);
  syncConfirm();
}

/* ── The last run ────────────────────────────────────────────────────────── */

function lastRunRows() {
  if (!el.last) return;
  el.last.replaceChildren();
  const last = lastRunView(reading);
  if (!last.rows.length) {
    el.last.hidden = true;
    return;
  }
  el.last.hidden = false;
  el.last.append(node("h3", "subhead", LAST_RUN_HEADING));
  for (const row of last.rows) {
    const line = node("p", "note");
    const said = row.message || row.stateWords || row.state;
    line.textContent = `${row.label || row.setting}: ${said}`;
    line.dataset.state = row.state;
    el.last.append(line);
  }
  if (last.at) el.last.append(node("p", "note", `Accepted ${last.at}.`));
  const summary = lastRunSummary();
  if (summary) el.last.append(node("p", "note", summary));
}

function lastRunSummary() {
  const last = lastRunView(reading);
  if (!last.rows.length) return "";
  const done = last.rows.filter(
    (row) => row.state === "changed" || row.state === "asked-and-approved",
  ).length;
  if (last.waiting) {
    return `${last.waiting} card${last.waiting === 1 ? " is" : "s are"} still waiting on the ` +
      `PC from last time; ${done} change${done === 1 ? "" : "s"} went through.`;
  }
  return `${done} change${done === 1 ? "" : "s"} went through last time.`;
}

function resultRows(result) {
  if (!el.result) return;
  el.result.replaceChildren();
  if (!result) return;
  if (result.error) el.result.append(node("p", "note", result.error));
  for (const row of result.rows) {
    const line = node("p", "sc-line");
    line.dataset.state = row.state;
    line.textContent = `${row.label}: ${row.message || row.stateWords}`;
    el.result.append(line);
  }
  if (result.waiting) {
    el.result.append(node("p", "note",
      "A card is still waiting on the PC. Answer it there and the change is made; " +
      "nothing here can answer it for you."));
  }
}

/* ── Reading, planning, applying ─────────────────────────────────────────── */

async function load() {
  planGeneration += 1; // any plan still in flight is for the old reading
  const raw = await readSetup();
  reading = normaliseReading(raw);
  draft = draftFromAnswers(reading);
  lastResult = null;
  if (el.body) el.body.hidden = false;
  if (el.reading) el.reading.hidden = true;
  if (el.title) el.title.textContent = TITLE;
  if (el.kicker) el.kicker.textContent = KICKER;
  if (el.help) el.help.textContent = HELP;
  if (el.about) el.about.textContent = reading.about;
  if (el.storage) {
    el.storage.textContent = reading.storage ? `Saved on the PC: ${reading.storage}.` : "";
  }
  if (el.cardWait) {
    el.cardWait.textContent = reading.available ? cardWaitWords(reading.cardWaitS) : "";
  }
  lastRunRows();
  paintQuestions();
  plan = null;
  if (reading.available && answeredCount(draft)) schedulePlan();
  else {
    if (el.plan) el.plan.replaceChildren();
    if (el.counts) el.counts.textContent = "";
    if (el.planStatus) el.planStatus.textContent = reading.available ? NOTHING_CHANGED : "";
  }
  paintApply();
  say(reading.available ? "" : reading.reason, reading.available ? "" : "warn");
}

function onAnswered() {
  planGeneration += 1; // the plan on screen was for the old answers
  renderQuestionsState();
  lastResult = null;
  if (el.result) el.result.replaceChildren();
  // The plan on screen was for the OLD answers: clear it before asking again,
  // so the one Apply button cannot be pressed against a stale count.
  plan = null;
  if (el.plan) el.plan.replaceChildren();
  if (el.counts) el.counts.textContent = "";
  if (el.planStatus) el.planStatus.textContent = PLAN_READING;
  say("Working out what would change. Nothing has been changed yet.");
  paintApply();
  schedulePlan();
}

function schedulePlan() {
  clearTimeout(planTimer);
  planTimer = setTimeout(() => {
    planTimer = 0;
    refreshPlan();
  }, PLAN_DEBOUNCE_MS);
}

async function refreshPlan() {
  if (!reading || !reading.available) return;
  const generation = ++planGeneration;
  const answers = planBody(draft).answers;
  if (!Object.keys(answers).length) {
    plan = null;
    if (el.plan) el.plan.replaceChildren();
    if (el.counts) el.counts.textContent = "";
    if (el.planStatus) el.planStatus.textContent = NOTHING_CHANGED;
    paintApply();
    return;
  }
  if (el.planStatus) el.planStatus.textContent = PLAN_READING;
  const got = planView(await planSetup({ answers }), reading);
  if (generation !== planGeneration) return; // a newer plan is on its way
  plan = got;
  if (el.planStatus) {
    el.planStatus.textContent = plan.ok === false
      ? plan.error
      : plan.hasChanges
        ? `${PLAN_HEADING} - read from the PC, nothing changed yet.`
        : NOTHING_TO_APPLY;
  }
  if (el.counts) el.counts.textContent = countsWords(plan);
  planRows(plan);
  if (plan.ok !== false && plan.hasChanges) say(NOTHING_CHANGED);
  paintApply();
}

function beginApply() {
  if (busy || pending) return;
  if (!gate({ reading, plan, busy, stale: !live() }).enabled) {
    paintApply();
    return;
  }
  pending = true;
  paintApply();
  if (el.confirmYes) el.confirmYes.focus();
}

function cancelApply() {
  pending = false;
  paintApply();
}

async function confirmApply() {
  if (busy || !pending) return;
  pending = false;
  busy = true;
  say(APPLY_BUSY);
  paintApply();
  let applied = null;
  let trouble = "";
  try {
    const body = applyBody(draft);
    applied = applyView(await applySetup(body));
    if (applied.ok === false && applied.error) trouble = applied.error;
    else if (applied.waiting) {
      trouble = `${applied.waiting} card${applied.waiting === 1 ? " is" : "s are"} still ` +
        "waiting - answer it on the PC.";
    } else {
      trouble = `Done. ${applied.changedCount} change` +
        `${applied.changedCount === 1 ? "" : "s"} made.`;
    }
  } catch (error) {
    applied = applyView({ ok: false, error: String((error && error.message) || error) });
    trouble = applied.error || "That did not work.";
  } finally {
    busy = false;
    // The re-read refreshes the prefill and the last-run rows - and clears the
    // result on purpose - so the result just received is drawn again after it.
    await load();
    lastResult = applied;
    if (applied) {
      resultRows(applied);
      if (el.result) el.result.hidden = false;
    }
    const good = Boolean(applied && applied.ok && !applied.waiting);
    say(trouble, good ? "ok" : "warn");
    paintApply();
  }
}

function paint() {
  paintApply();
}

if (el.body && el.questions) {
  if (IS_TAURI) {
    el.apply?.addEventListener("click", beginApply);
    el.confirmYes?.addEventListener("click", confirmApply);
    el.confirmNo?.addEventListener("click", cancelApply);
    onLink(() => paint());
    load();
  } else if (el.reading) {
    el.reading.hidden = false;
    el.reading.textContent = "This window cannot ask the PC.";
  }
} else if (el.reading) {
  el.reading.hidden = false;
  el.reading.textContent = "This window cannot ask the PC.";
}
