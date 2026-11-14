/**
 * Settings → "Personalize Jarvis" (JARVIS-API section 147; the PC's module is
 * `backend/jarvis_setup.py`, its routes are installed by `setup.patch`).
 *
 * THE CARD, UPGRADED IN PLACE (Wave B, 2026-11-03; Gemini's ruling Q1). No new
 * window and no second page: this same Settings card now has
 *
 *  - a row of SECTION tabs, built from the PC's own `sections`;
 *  - a "Step through one by one" / "Show all" mode, where step mode paints ONE
 *    question and a Back / Skip / Next row;
 *  - a progress line, "8 of 25 answered", counted from the draft;
 *  - a "show only new / unanswered" filter, driven by each question's own
 *    `version` against `completed_version`;
 *  - "Take it again", "Not now" and "Keep current settings".
 *
 * Every question, option, section and sentence is the PC's. The rules live in
 * `setup-questionnaire.js` (DOM-free, so `node tests/setup-questionnaire.mjs`
 * can test them); this file only paints them and sends the calls.
 *
 * THE ONE ACTION. "Apply these changes" is the only control that writes
 * settings, and it takes TWO presses: the first shows the confirm step with the
 * plan's own count ("3 changes - 1 of them will ask you on a card"), the second
 * calls `applySetup(applyBody(draft))`, which is the only body in the app
 * carrying `confirm: true`. There is no apply on load, on a link reconnect, on
 * a changed answer or on a timer. `load()` never calls `applySetup()`, and the
 * suite pins that.
 *
 * THE OTHER WRITES ARE NOT SETTINGS. "Not now" and "Keep current settings" post
 * one progress note (`POST /api/setup/progress`, through the same Rust command,
 * cardless and desktop-only): a timestamp, and - for "Keep current settings" -
 * the PC's own `completed_version`. Neither carries an answer, calls a setter or
 * raises a card. The stepper's position is sent the same way, debounced, so the
 * phone and the HUD can say where the PC's card is. Finish is that same note
 * with its own words (2026-11-13): recording that the pass is done is not a
 * change, and the answers are still applied only by Apply.
 *
 * HONEST WAITING. The PC works through the changes one at a time and waits on
 * each existing approval card, so applying can take minutes. The card says so
 * before the press and while it runs, and a card still waiting when the PC's
 * patience runs out is drawn as STILL WAITING - never as done and never as
 * failed. Nothing here approves a card.
 */
import { currentLink, onLink } from "./jarvis-link.js";
import { applySetup, planSetup, progressSetup, readSetup } from "./setup-bridge.js";
import {
  ALL,
  APPLY,
  APPLYING,
  APPLY_BUSY,
  BACK,
  CANCEL,
  CONFIRM,
  FILTER_LABEL,
  FINISH,
  HELP,
  KEEP_CURRENT,
  KEEP_CURRENT_WORDS,
  KICKER,
  LAST_RUN_HEADING,
  NEXT,
  NONE,
  NOTHING_CHANGED,
  NOTHING_TO_APPLY,
  NOT_NOW,
  NOT_NOW_WORDS,
  PLAN_HEADING,
  PLAN_READING,
  RECOMMENDATION_HEADING,
  SHOW_ALL,
  SKIPPED_HEADING,
  SKIP,
  STEP_END,
  STEP_FINISH,
  STEP_MODE_HINT,
  STEP_QUESTION,
  STEP_THROUGH,
  TAKE_AGAIN,
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
  filterEmptyWords,
  finishedPassWords,
  firstUnanswered,
  gate,
  lastRunView,
  nextQuestion,
  nextStep,
  normaliseReading,
  offerShown,
  optionOn,
  planBody,
  planView,
  positionWords,
  progressBody,
  progressWords,
  questionById,
  sectionsOf,
  toggleOption,
  visibleQuestions,
} from "./setup-questionnaire.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);
const PLAN_DEBOUNCE_MS = 250;
/** How long after the last step the position is sent. Long enough that walking
 *  through five questions is one write, not five. */
const PROGRESS_DEBOUNCE_MS = 700;

const $ = (id) => document.getElementById(id);

const el = {
  body: $("sq-body"),
  reading: $("sq-reading"),
  title: $("sq-title"),
  kicker: $("sq-kicker"),
  help: $("sq-help"),
  done: $("sq-done"),
  sections: $("sq-sections"),
  mode: $("sq-mode"),
  step: $("sq-step"),
  showall: $("sq-showall"),
  modeHint: $("sq-mode-hint"),
  progress: $("sq-progress"),
  filterRow: $("sq-filter-row"),
  filter: $("sq-filter"),
  filterWords: $("sq-filter-words"),
  filterEmpty: $("sq-filter-empty"),
  questions: $("sq-questions"),
  stepnav: $("sq-stepnav"),
  prev: $("sq-prev"),
  skip: $("sq-skip"),
  next: $("sq-next"),
  stepWhere: $("sq-step-where"),
  planStatus: $("sq-plan-status"),
  plan: $("sq-plan"),
  counts: $("sq-counts"),
  apply: $("sq-apply"),
  applyWhy: $("sq-apply-why"),
  again: $("sq-again"),
  confirm: $("sq-confirm"),
  confirmText: $("sq-confirm-text"),
  confirmYes: $("sq-confirm-yes"),
  confirmNo: $("sq-confirm-no"),
  result: $("sq-result"),
  last: $("sq-last"),
  about: $("sq-about"),
  storage: $("sq-storage"),
  cardWait: $("sq-card-wait"),
  offerBtns: $("sq-offer-btns"),
  notNow: $("sq-not-now"),
  keep: $("sq-keep"),
  offerWhy: $("sq-offer-why"),
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

/* The stepper's own view state. Not settings: which question is on screen, and
 * whether the card is showing one at a time. */
let stepMode = true;
let section = "";
let currentId = "";
let filterOn = false;
let progressTimer = 0;
/** The last position sent, so an unchanged position is not re-sent on every
 *  repaint (and a replay of the same note never reaches the PC). */
let sentProgress = "";

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

/* ── The sections, the filter and the progress line ──────────────────────── */

function questionsShown() {
  return visibleQuestions(reading, { section, filter: filterOn });
}

function paintSections() {
  if (!el.sections) return;
  const sections = sectionsOf(reading);
  el.sections.replaceChildren();
  el.sections.hidden = sections.length === 0;
  for (const row of sections) {
    const tab = node("button", "choice", row.title);
    tab.type = "button";
    tab.dataset.section = row.id;
    tab.setAttribute("role", "tab");
    tab.setAttribute("aria-pressed", row.id === section ? "true" : "false");
    tab.addEventListener("click", () => {
      if (busy) return;
      section = row.id;
      currentId = "";
      paintView();
      queueProgress();
    });
    el.sections.append(tab);
  }
}

function paintProgress() {
  if (el.progress) el.progress.textContent = progressWords(reading, draft);
  if (el.filterWords) {
    const fresh = visibleQuestions(reading, { filter: true }).length;
    el.filterWords.textContent = `${FILTER_LABEL} (${fresh})`;
  }
  if (el.filterEmpty) {
    // One scope governs both lines: the count above is the whole
    // questionnaire's, so this sentence is too (`filterEmptyWords` says which
    // of the two truths it is).
    const words = filterEmptyWords(reading, { section, filter: filterOn });
    el.filterEmpty.hidden = !words;
    el.filterEmpty.textContent = words;
  }
  if (el.done) {
    // "Finished" is `completed_version`, which "Keep current settings" moves
    // without answering anything - so the block is the model's to word, never
    // a sentence typed here.
    const words = finishedPassWords(reading, draft);
    el.done.hidden = !words;
    el.done.textContent = words;
  }
}

function paintMode() {
  if (el.step) el.step.setAttribute("aria-pressed", stepMode ? "true" : "false");
  if (el.showall) el.showall.setAttribute("aria-pressed", stepMode ? "false" : "true");
  if (el.modeHint) {
    el.modeHint.hidden = !stepMode;
    el.modeHint.textContent = stepMode ? STEP_MODE_HINT : "";
  }
  if (el.stepnav) el.stepnav.hidden = !stepMode;
  if (el.step) el.step.textContent = STEP_THROUGH;
  if (el.showall) el.showall.textContent = SHOW_ALL;
}

function paintOffer() {
  if (!el.offerBtns) return;
  // "Not now" counts here too: the toast and the HUD were already silenced by
  // `dismissed_at`, and this row used to stay on screen and promise the
  // opposite (audit 2026-11-03, bug 4).
  const offered = offerShown(reading, Date.now() / 1000);
  el.offerBtns.hidden = !offered;
  if (el.notNow) el.notNow.textContent = NOT_NOW;
  if (el.keep) el.keep.textContent = KEEP_CURRENT;
  if (el.offerWhy) {
    el.offerWhy.textContent = offered ? `${NOT_NOW_WORDS} ${KEEP_CURRENT_WORDS}` : "";
    el.offerWhy.hidden = !offered;
  }
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

/**
 * The one question the stepper is showing, decided from the view state.
 *
 * `currentId` is kept across repaints; when it no longer names something the
 * card is showing (the section changed, the filter hid it, the PC re-read), the
 * first visible question takes over, so the card can never sit on a blank panel
 * with a Next button that has nowhere to go.
 */
function currentQuestion() {
  const shown = questionsShown();
  if (!shown.length) return null;
  const found = shown.find((q) => q.id === currentId);
  return found || shown[0];
}

function paintQuestions() {
  if (!el.questions) return;
  const shown = questionsShown();
  el.questions.replaceChildren();
  if (!shown.length) {
    if (el.stepWhere) el.stepWhere.textContent = "";
    paintStepNav();
    return;
  }
  if (stepMode) {
    const one = currentQuestion();
    currentId = one ? one.id : "";
    if (one) el.questions.append(questionRow(one));
  } else {
    for (const question of shown) el.questions.append(questionRow(question));
  }
  paintStepNav();
  renderQuestionsState();
}

/**
 * The Back / Skip / Next row, painted from ONE rule: what the next press does.
 *
 * `nextStep` decides the label (Next, or Finish when the press is the one that
 * records the pass), whether Next can be pressed at all, and - when it cannot -
 * the sentence under the row that says what is left. The page computes nothing
 * about the next step itself; before 2026-11-13 it did, and the last question
 * was a press that did nothing (`FINISH` was painted only while a single
 * question was on screen, and nothing was wired to it anyway).
 */
function paintStepNav() {
  if (!el.stepWhere) return;
  const shown = questionsShown();
  if (!stepMode) {
    el.stepWhere.textContent = "";
    return;
  }
  const one = currentQuestion();
  const at = one ? shown.findIndex((q) => q.id === one.id) : 0;
  const action = nextStep(reading, {
    section, filter: filterOn, currentId: one ? one.id : "", draft,
  });
  el.stepWhere.textContent = action.why || (one ? positionWords(reading, one.id) : "");
  if (el.prev) {
    el.prev.textContent = BACK;
    el.prev.disabled = busy || at <= 0;
  }
  if (el.skip) el.skip.textContent = SKIP;
  if (el.next) {
    el.next.textContent = action.kind === STEP_FINISH ? FINISH : NEXT;
    el.next.disabled = busy || action.kind === STEP_END;
  }
}

function renderQuestionsState() {
  for (const question of questionsShown()) syncQuestion(question);
}

/** While the one apply runs, no answer may change under it: the whole
 *  questionnaire is turned off, visibly, not just ignored by the handlers. */
function setQuestionsEnabled(enabled) {
  if (!el.questions) return;
  for (const input of el.questions.querySelectorAll("input")) input.disabled = !enabled;
  for (const button of el.questions.querySelectorAll("[data-pick]")) {
    button.disabled = !enabled;
  }
  for (const button of (el.stepnav && el.stepnav.querySelectorAll("button")) || []) {
    button.disabled = !enabled;
  }
  for (const button of (el.sections && el.sections.querySelectorAll("button")) || []) {
    button.disabled = !enabled;
  }
}

/** Everything the view state decides, painted in one pass. */
function paintView() {
  paintSections();
  paintMode();
  paintProgress();
  paintOffer();
  paintQuestions();
}

/* ── The stepper's moves ─────────────────────────────────────────────────── */

function stepTo(questionId) {
  const next = questionById(reading, questionId);
  if (!next) return;
  currentId = next.id;
  if (next.section) section = next.section;
  paintView();
  queueProgress();
}

/**
 * Next: the model's one move (`nextStep`), and nothing worked out here.
 *
 * Step to the question it names - `stepTo` opens the section that question is
 * in; ask to record the pass when it says FINISH; and do nothing at all when it
 * says END, because in that state the button is painted disabled with its own
 * sentence under the row.
 */
function goNext() {
  const one = currentQuestion();
  const action = nextStep(reading, {
    section, filter: filterOn, currentId: one ? one.id : "", draft,
  });
  if (action.kind === STEP_FINISH) {
    void finishPass();
    return;
  }
  if (action.kind === STEP_QUESTION && action.id) stepTo(action.id);
}

function goBack() {
  const shown = questionsShown();
  const at = shown.findIndex((q) => q.id === currentId);
  if (at > 0) {
    stepTo(shown[at - 1].id);
    return;
  }
  const sections = sectionsOf(reading);
  const here = sections.findIndex((row) => row.id === section);
  if (here <= 0) return;
  section = sections[here - 1].id;
  const shownNow = visibleQuestions(reading, { section, filter: filterOn });
  const last = shownNow[shownNow.length - 1];
  if (last) stepTo(last.id);
}

/**
 * Skip: drop this question's staged answer and land on the next one that still
 * has none.
 *
 * Leaving the id out of the draft is the whole mechanism (build spec section
 * 7.2): `planBody` sends only the draft, the PC plans nothing for an absent id,
 * and the merge on apply keeps the answer the owner already had. The
 * `nextQuestion` rule is the same one the card's "first unanswered" uses, so a
 * retake walks only what still needs an answer.
 */
function skipCurrent() {
  const one = currentQuestion();
  if (!one) return;
  draft = chooseOne(draft, one.id, "");
  const next = nextQuestion(reading, draft, one.id);
  renderQuestionsState();
  paintProgress();
  if (next) {
    stepTo(next.id);
  } else {
    paintView();
    queueProgress();
  }
}

/** "Take it again": empty the draft and start at the first question. Writes
 *  nothing - the old answers are still on the PC until Apply. */
function takeAgain() {
  if (busy) return;
  planGeneration += 1;
  draft = {};
  plan = null;
  lastResult = null;
  filterOn = false;
  stepMode = true;
  if (el.filter) el.filter.checked = false;
  if (el.result) el.result.replaceChildren();
  if (el.plan) el.plan.replaceChildren();
  if (el.counts) el.counts.textContent = "";
  if (el.planStatus) el.planStatus.textContent = NOTHING_CHANGED;
  const first = (reading && reading.questions || [])[0];
  section = first && first.section ? first.section : "";
  currentId = first ? first.id : "";
  paintView();
  say("Starting again from the first question. Nothing has been changed.");
  paintApply();
  clearStagedDraft();
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
  if (el.again) el.again.textContent = TAKE_AGAIN;
  setQuestionsEnabled(!busy);
  // `setQuestionsEnabled` re-enables the Back/Next/Skip row as a whole; the
  // step itself decides whether Back has anywhere to go.
  paintStepNav();
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

/* ── Where the owner is (POST /api/setup/progress) ──────────────────────── */

/**
 * Tell the PC where the card is, after the walking has stopped for a moment.
 *
 * Debounced and de-duplicated, because walking five questions should be one
 * small write rather than five. A failure is NOT shown and NOT retried: where
 * the card is happens to be a nicety (the phone and the HUD read it), it
 * changes no setting, and a status line about it would be noise on a card that
 * is otherwise working. The next step tries again.
 */
function queueProgress() {
  if (!reading || !reading.available || !currentId) return;
  clearTimeout(progressTimer);
  progressTimer = setTimeout(() => {
    progressTimer = 0;
    void sendProgress(progressBody({ section, question: currentId, draft }));
  }, PROGRESS_DEBOUNCE_MS);
}

async function sendProgress(body) {
  const key = JSON.stringify(body);
  if (key === sentProgress) return;
  sentProgress = key;
  const answer = await progressSetup(body);
  if (answer && answer.ok === false) {
    // Let the next step try again rather than believing it was recorded.
    sentProgress = "";
  }
}

/**
 * "Take it again" tells the PC the staged draft is gone, AT ONCE.
 *
 * It cannot ride `queueProgress`'s debounce for two reasons. The PC clears a
 * draft on an EXPLICIT empty object and keeps whatever it has when the field
 * is absent (`progress()`), so the empty object has to be built on purpose
 * (`progressBody({clearDraft: true})`). And if the owner answered within
 * `PROGRESS_DEBOUNCE_MS`, the queued note would be replaced by the answered
 * one - leaving the old draft on the PC, to be merged straight back by
 * `load()` on the next open (audit 2026-11-03, bug 2).
 *
 * The position rides with it, so this is still one small write and not two.
 */
function clearStagedDraft() {
  if (!reading || !reading.available || !currentId) return;
  clearTimeout(progressTimer);
  progressTimer = 0;
  void sendProgress(progressBody({
    section, question: currentId, draft, clearDraft: true,
  }));
}

/** "Not now": hide the offer for a day. No answer is written. */
async function notNow() {
  if (busy) return;
  sentProgress = "";
  const answer = await progressSetup(progressBody({ dismiss: true }));
  if (answer && answer.ok === false) {
    say(answer.error || "That did not reach the PC. Try again in a moment.", "warn");
    return;
  }
  if (reading) reading.dismissedAt = Date.now() / 1000;
  paintOffer();
  say("Not now. Jarvis will not offer this again for a day.");
}

/**
 * Record the pass as complete on the PC: `{"keep_current": true}`, the one
 * cardless note that moves `completed_version`.
 *
 * It writes no answer, calls no setter and raises no card - so it is never an
 * apply, and the two presses on Apply stay the only way a setting changes. Both
 * "Keep current settings" and Finish are this same note, with their own words;
 * one press, one write, and a refusal is said in the PC's own sentence.
 */
async function recordPassComplete() {
  sentProgress = "";
  const answer = await progressSetup(progressBody({ keepCurrent: true }));
  if (answer && answer.ok === false) {
    say(answer.error || "That did not reach the PC. Try again in a moment.", "warn");
    return false;
  }
  if (reading) reading.completedVersion = reading.version;
  paintView();
  paintApply();
  return true;
}

/** "Keep current settings": the owner is happy as they are. No setting, no
 *  answer and no card - one progress note that moves `completed_version`. */
async function keepCurrent() {
  if (busy) return;
  if (!(await recordPassComplete())) return;
  say("Kept as it is. Nothing was changed, and Jarvis will not offer this again.");
}

/**
 * Finish: the last question's Next, once every question has an answer
 * (2026-11-13).
 *
 * `nextStep` is the only thing that offers this, so it can never be pressed on
 * a pass that still has questions without an answer. The press records the pass
 * as complete through the same cardless note as "Keep current settings"; it
 * applies nothing, and the words say so, because the answers on screen are
 * staged and only Apply writes them.
 */
async function finishPass() {
  if (busy) return;
  if (!(await recordPassComplete())) return;
  say("Finished. Jarvis has recorded that you have been through this pass and " +
    "will not offer it again. Your answers are applied only by Apply these " +
    "changes.");
}

/* ── Reading, planning, applying ─────────────────────────────────────────── */

async function load() {
  planGeneration += 1; // any plan still in flight is for the old reading
  const raw = await readSetup();
  reading = normaliseReading(raw);
  draft = draftFromAnswers(reading);
  // The chat's staged choices (the `setup_quiz` tool writes
  // `in_progress.draft_answers`) are shown as the draft's own, cleaned the same
  // way as the saved answers, so a choice staged in chat is highlighted here.
  const staged = reading.inProgress && reading.inProgress.draftAnswers;
  if (staged && Object.keys(staged).length) {
    draft = { ...draft, ...draftFromAnswers({ ...reading, answers: staged }) };
  }
  lastResult = null;
  sentProgress = "";
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
  // Where to open: the question the PC remembers (a resume), else the first one
  // the owner has never answered - which is ruling Q3's "first unanswered
  // question on open". A finished quiz opens at the top of its own list.
  const resumed = reading.inProgress
    ? questionById(reading, reading.inProgress.question)
    : null;
  const start = resumed || firstUnanswered(reading) || reading.questions[0] || null;
  const sections = sectionsOf(reading);
  if (start && start.section) section = start.section;
  else if (!section && sections.length) section = sections[0].id;
  currentId = start ? start.id : "";
  if (el.filter) {
    el.filter.checked = filterOn;
  }
  lastRunRows();
  paintView();
  plan = null;
  if (reading.available && answeredCount(draft)) schedulePlan();
  else {
    if (el.plan) el.plan.replaceChildren();
    if (el.counts) el.counts.textContent = "";
    if (el.planStatus) el.planStatus.textContent = reading.available ? NOTHING_CHANGED : "";
  }
  paintApply();
  say(reading.available ? "" : reading.reason, reading.available ? "" : "warn");
  if (reading.available) queueProgress();
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
  paintProgress();
  paintApply();
  schedulePlan();
  queueProgress();
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
    el.again?.addEventListener("click", takeAgain);
    el.step?.addEventListener("click", () => {
      if (busy) return;
      stepMode = true;
      paintView();
      queueProgress();
    });
    el.showall?.addEventListener("click", () => {
      if (busy) return;
      stepMode = false;
      paintView();
    });
    el.filter?.addEventListener("change", () => {
      if (busy) return;
      filterOn = el.filter.checked === true;
      currentId = "";
      paintView();
      queueProgress();
    });
    el.prev?.addEventListener("click", () => {
      if (!busy) goBack();
    });
    el.next?.addEventListener("click", () => {
      if (!busy) goNext();
    });
    el.skip?.addEventListener("click", () => {
      if (!busy) skipCurrent();
    });
    el.notNow?.addEventListener("click", () => void notNow());
    el.keep?.addEventListener("click", () => void keepCurrent());
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
