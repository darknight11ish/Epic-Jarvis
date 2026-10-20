/**
 * The setup questionnaire - the reading and the words the desktop draws
 * (JARVIS-API section 147; `backend/jarvis_setup.py`; the routes
 * `GET /api/setup`, `POST /api/setup/plan`, `POST /api/setup/apply`).
 *
 * WHAT THIS IS. A guided path through settings that ALREADY exist. The PC owns
 * the fourteen questions, their options and their help lines, the current
 * values, the last accepted answers, and every sentence a plan or an apply
 * answers with. This file holds no question, option, setting key, gate action
 * or tier: it reads the PC's answer and turns it into the small objects the
 * Settings card draws. A question added, renamed or removed by the PC appears,
 * moves or disappears without a desktop release.
 *
 * THE ONE THING IT MUST NEVER BECOME. It is a GUIDE, not a second settings
 * system. `planBody()` is READ-ONLY: the PC writes nothing and raises no card
 * for it, so this page may ask for a plan whenever the answers change.
 * `applyBody()` is the only body that carries `confirm: true`, and it exists
 * for one click on one button: the owner's explicit "apply these changes".
 * Nothing here applies on load, on a link reconnect, on a changed answer or on
 * a timer. `applyBody` itself does not call anything - `setup-bridge.js` is the
 * only file that sends it, and the test holds both facts.
 *
 * HONEST STATES. A change's `effect` is the PC's own: `instant` (it happens at
 * once), `card` (its own existing approval card waits for a person) or
 * `blocked` (this PC's settings file does not allow it, so it cannot be made
 * from here). A skipped row keeps the PC's reason word for word. A carded
 * change that is still waiting when the questionnaire's patience runs out is
 * reported as STILL WAITING - never as failed, never as done - and the review
 * shows what the PC saved (`last_outcomes`). Nothing here approves a card,
 * clears a latch, switches a model or applies a preset: the "what will you
 * mostly use it for" answer is a RECOMMENDATION only, and the PC says so.
 *
 * It is a plain ES module with no DOM and no Tauri import, so
 * `node tests/setup-questionnaire.mjs` can exercise every rule without a
 * browser. The DOM wiring is `setup-settings.js`; the bridge is
 * `setup-bridge.js`. Nothing here names a route - the Rust command owns the
 * three paths, so the parity check sees one caller, not three.
 *
 * @module setup-questionnaire
 */

/** This page's own words. Every question, option and sentence is the PC's. */
export const TITLE = "First-time setup";
export const KICKER =
  "Fourteen questions about how you want Jarvis to behave. Every answer " +
  "changes settings that already exist; nothing here is a new kind of rule.";
export const HELP =
  "Pick the answers that sound like you, then read what would change before " +
  "anything happens. Instant changes happen the moment you apply; anything " +
  "that loosens a rule still shows its own approval card on the PC, one at a " +
  "time. This page never applies anything by itself.";
export const ABOUT_FALLBACK =
  "A guided path through settings that already exist. Applying is one change " +
  "at a time; anything that loosens a rule still shows its own approval card.";
export const NOTHING_CHANGED =
  "Nothing has been changed yet. Pick answers and read the plan below; " +
  "nothing is written until you press Apply and then confirm.";
export const UPDATE_WORDS =
  "This PC's Jarvis does not have the setup questionnaire yet. In PowerShell " +
  "on the PC, in the Jarvis folder, run: .\\scripts\\apply-patches.ps1 . Then " +
  "restart Jarvis and open this again.";
export const BAD_READ_WORDS =
  "Jarvis answered, but not in a way this app can read. Update the backend by " +
  "running apply-patches.ps1.";
export const BAD_PLAN_WORDS =
  "Jarvis answered, but not with a readable plan. Update the backend by " +
  "running apply-patches.ps1.";
export const APPLY_HELD =
  "The connection to Jarvis is catching up. Applying your answers waits until " +
  "it is back - it changes settings, and a stale link must not carry a " +
  "write.";
export const APPLY_BUSY =
  "The PC is working through your changes, one at a time. Answer each approval " +
  "card on the PC as it appears; this can take a few minutes.";
export const NOTHING_TO_APPLY =
  "Nothing would change with these answers. Choose something different, or " +
  "close this card.";
export const CHOOSE_FIRST =
  "Choose at least one answer to see what it would change.";
export const PLAN_READING = "Working out what would change…";
export const ALL = "All";
export const NONE = "None";
export const APPLY = "Apply these changes";
export const CONFIRM = "Yes, apply them now";
export const CANCEL = "Cancel";
export const APPLYING = "Applying…";
export const PLAN_HEADING = "What would change";
export const SKIPPED_HEADING = "What would not change";
export const RECOMMENDATION_HEADING = "Recommended setup";
export const NO_CHANGES = "Nothing would change with these answers.";
export const STILL_WAITING =
  "A card is still waiting on the PC. Answer it there and the change is made; " +
  "nothing here can answer it for you.";
export const NOT_APPROVED =
  "The card was not approved, so that setting stays as it was.";
export const LAST_RUN_HEADING = "Last time you accepted this";
export const CARD_WAIT_FALLBACK_MINUTES = 5;

/** The three effect words. The PC decides which one a change has. */
export const EFFECT_WORDS = {
  instant: "Instant",
  card: "Asks you on a card",
  blocked: "Blocked",
};

/** The PC's state words for one applied change, in the owner's language. */
export const OUTCOME_WORDS = {
  changed: "Changed.",
  "asked-and-approved": "Changed - you approved its card.",
  "asked-and-denied": "Not changed - the card was not approved.",
  "asked-no-answer": "Still waiting: answer its card on the PC and it changes.",
  "not-available": "Not available on this PC.",
  "not-changed": "Not changed.",
  failed: "Did not change.",
};

function plain(value) {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return "";
}

function list(value) {
  return Array.isArray(value) ? value : [];
}

function object(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : null;
}

/** The effect word, or the PC's raw one when it is not one this app knows.
 *  An unknown effect is never rounded to "Instant". */
export function effectWords(effect) {
  const key = plain(effect).trim().toLowerCase();
  return EFFECT_WORDS[key] || key || "Unknown";
}

/** A plain answer's value, for a row: "on"/"off" become words. */
export function valueWords(value) {
  if (typeof value === "boolean") return value ? "on" : "off";
  return plain(value).trim() || "not set";
}

/** "Each card can wait up to 5 minutes for you." Never seconds. */
export function cardWaitWords(seconds) {
  const s = Number(seconds);
  const minutes = Number.isFinite(s) && s > 0
    ? Math.max(1, Math.round(s / 60))
    : CARD_WAIT_FALLBACK_MINUTES;
  return `Each approval card can wait up to ${minutes} minute${minutes === 1 ? "" : "s"} ` +
    "for you before the questionnaire moves on.";
}

/**
 * `GET /api/setup`, as the small reading this page draws.
 *
 * A question that is not an object with an id and a list of options is left
 * out rather than drawn wrong. `available: false` and a bridge failure both
 * become the same honest "nothing here yet" reading, in words.
 */
export function normaliseReading(raw) {
  const body = object(raw);
  if (!body) {
    return {
      available: false, reason: BAD_READ_WORDS, questions: [], current: {},
      answers: {}, completedAt: null, lastOutcomes: [], cardWaitS: null,
      about: "", storage: "",
    };
  }
  const questions = [];
  for (const row of list(body.questions)) {
    const q = object(row);
    if (!q || !plain(q.id)) continue;
    const options = [];
    for (const o of list(q.options)) {
      const option = object(o);
      if (!option || !plain(option.id)) continue;
      options.push({
        id: plain(option.id),
        label: plain(option.label),
        detail: plain(option.detail),
      });
    }
    if (!options.length) continue;
    questions.push({
      id: plain(q.id),
      title: plain(q.title) || plain(q.id),
      help: plain(q.help),
      multi: q.multi === true,
      allNone: q.all_none === true || q.multi === true,
      options,
    });
  }
  const current = {};
  const currentRaw = object(body.current);
  if (currentRaw) {
    for (const [key, value] of Object.entries(currentRaw)) {
      if (value === null || value === undefined) continue;
      if (typeof value === "boolean" || typeof value === "string") current[key] = value;
    }
  }
  const outcomes = [];
  for (const row of list(body.last_outcomes)) {
    const o = object(row);
    if (!o) continue;
    outcomes.push({
      setting: plain(o.setting),
      label: plain(o.label),
      effect: plain(o.effect),
      state: plain(o.state),
      message: plain(o.message),
    });
  }
  return {
    available: body.available !== false,
    reason: body.available === false
      ? (plain(body.why) || UPDATE_WORDS)
      : (plain(body.error) ? plain(body.error) : ""),
    questions,
    current,
    answers: object(body.answers) || {},
    completedAt: typeof body.completed_at === "number" ? body.completed_at : null,
    lastOutcomes: outcomes,
    cardWaitS: typeof body.card_wait_s === "number" ? body.card_wait_s : null,
    about: plain(body.about) || ABOUT_FALLBACK,
    storage: plain(body.storage),
  };
}

/** The question with this id, or null. */
export function questionById(reading, id) {
  const want = plain(id);
  return (reading && reading.questions || []).find((q) => q.id === want) || null;
}

function knownOptions(question) {
  return new Set((question.options || []).map((o) => o.id));
}

/**
 * A fresh draft for this reading: the last accepted answers, cleaned to the
 * choices this PC really offers today. An answer whose option has gone is
 * dropped rather than sent back as a stale id.
 */
export function draftFromAnswers(reading) {
  const draft = {};
  const answers = object(reading && reading.answers) || {};
  for (const question of (reading && reading.questions) || []) {
    if (!(question.id in answers)) continue;
    const value = answers[question.id];
    const known = knownOptions(question);
    if (typeof value === "string") {
      const word = value.trim();
      if (question.multi && (word === "all" || word === "none")) {
        draft[question.id] = word;
      } else if (known.has(word)) {
        draft[question.id] = word;
      }
      continue;
    }
    if (Array.isArray(value)) {
      const picked = value
        .filter((one) => typeof one === "string" && known.has(one.trim()))
        .map((one) => one.trim());
      if (picked.length) draft[question.id] = picked;
    }
  }
  return draft;
}

/** What this draft says for one question: a string, a list, or nothing. */
export function answerFor(draft, questionId) {
  const value = (draft || {})[questionId];
  if (Array.isArray(value)) return value.slice();
  if (typeof value === "string" && value) return value;
  return null;
}

/** One answer to a one-choice question. Returns a new draft. */
export function chooseOne(draft, questionId, optionId) {
  const next = { ...(draft || {}) };
  const value = plain(optionId);
  if (value) next[questionId] = value;
  else delete next[questionId];
  return next;
}

/** "All" for a choose-any question: the PC expands it, both apps agree. */
export function chooseAll(draft, questionId) {
  return { ...(draft || {}), [questionId]: "all" };
}

/** "None" for a choose-any question. */
export function chooseNone(draft, questionId) {
  return { ...(draft || {}), [questionId]: "none" };
}

/** Is this option on in the draft? "all" means every option is on. */
export function optionOn(draft, question, optionId) {
  const value = answerFor(draft, question.id);
  if (value === "all") return true;
  if (value === "none" || value === null) return false;
  if (Array.isArray(value)) return value.includes(plain(optionId));
  return value === plain(optionId);
}

/** Is the draft saying "All" / "None", for that pair of buttons? */
export function allNoneState(draft, questionId) {
  const value = answerFor(draft, questionId);
  if (value === "all") return "all";
  if (value === "none") return "none";
  return "";
}

/**
 * Flip ONE option of a choose-any question, returning a new draft.
 *
 * From "All", unchecking an option becomes the concrete list without it; from
 * "None", checking one becomes that one. This keeps the data-level "all" /
 * "none" answers the PC understands, while a checkbox still means what a
 * checkbox looks like it means.
 */
export function toggleOption(draft, question, optionId) {
  const id = plain(optionId);
  const next = { ...(draft || {}) };
  if (!id) return next;
  const value = answerFor(draft, question.id);
  let picked;
  if (value === "all") {
    picked = question.options.map((o) => o.id).filter((one) => one !== id);
  } else if (value === "none" || value === null) {
    picked = [id];
  } else {
    const current = Array.isArray(value) ? value : [value];
    picked = current.includes(id)
      ? current.filter((one) => one !== id)
      : [...current, id];
  }
  if (picked.length) next[question.id] = picked;
  else delete next[question.id];
  return next;
}

/** How many questions the owner has answered in this draft. */
export function answeredCount(draft) {
  return Object.keys(draft || {}).filter((key) => answerFor(draft, key) !== null).length;
}

function answerBody(draft) {
  const answers = {};
  for (const [questionId, value] of Object.entries(draft || {})) {
    if (Array.isArray(value)) {
      const picked = value.filter((one) => typeof one === "string" && one.trim());
      if (picked.length) answers[questionId] = picked;
    } else if (typeof value === "string" && value.trim()) {
      answers[questionId] = value.trim();
    }
  }
  return answers;
}

/**
 * `POST /api/setup/plan`'s body. READ-ONLY: the PC writes nothing and raises
 * no card for it, which is why this page may send it whenever the answers
 * change.
 */
export function planBody(draft) {
  return { answers: answerBody(draft) };
}

/**
 * `POST /api/setup/apply`'s body. THE ONE THING THIS PAGE MAY NOT SEND BY
 * ITSELF: `confirm: true` is the owner's answer to the plan, and only a click
 * on the confirm button may reach `setup-bridge.js`'s `applySetup()` with it.
 */
export function applyBody(draft) {
  return { answers: answerBody(draft), confirm: true };
}

function orderQuestions(reading) {
  const order = new Map();
  for (const [index, question] of ((reading && reading.questions) || []).entries()) {
    order.set(question.id, index);
  }
  return order;
}

/**
 * `POST /api/setup/plan`'s answer, as the review the page draws.
 *
 * `changes` keeps the PC's order within a question; `skipped` keeps the PC's
 * reasons word for word; `recommendation` is labelled a recommendation, never
 * a change. `effect` is never invented: a change the PC did not label is
 * "Unknown", not "Instant".
 */
export function planView(plan, reading) {
  const body = object(plan);
  if (!body) return { ok: false, error: BAD_PLAN_WORDS, changes: [], skipped: [], counts: {} };
  if (body.ok === false) {
    return {
      ok: false,
      error: plain(body.error) || BAD_PLAN_WORDS,
      changes: [], skipped: [], counts: {},
    };
  }
  const order = orderQuestions(reading);
  const title = (id) => (questionById(reading, id) || {}).title || plain(id);
  const changes = [];
  for (const row of list(body.changes)) {
    const change = object(row);
    if (!change) continue;
    const setting = plain(change.setting);
    if (!setting) continue;
    changes.push({
      setting,
      question: plain(change.question),
      questionTitle: title(change.question),
      label: plain(change.label) || setting,
      from: valueWords(change.from),
      to: valueWords(change.to),
      effect: plain(change.effect),
      effectWords: effectWords(change.effect),
      sentence: plain(change.sentence),
      knownQuestion: order.has(plain(change.question)),
    });
  }
  changes.sort((a, b) => {
    const ai = order.has(a.question) ? order.get(a.question) : Number.MAX_SAFE_INTEGER;
    const bi = order.has(b.question) ? order.get(b.question) : Number.MAX_SAFE_INTEGER;
    return ai - bi;
  });
  const skipped = [];
  for (const row of list(body.skipped)) {
    const skip = object(row);
    if (!skip) continue;
    skipped.push({
      setting: plain(skip.setting),
      reason: plain(skip.reason) || "Not changing.",
    });
  }
  const counts = { instant: 0, card: 0, blocked: 0 };
  for (const change of changes) {
    const key = change.effect.trim().toLowerCase();
    if (key in counts) counts[key] += 1;
  }
  const recommendation = object(body.recommendation)
    ? {
      id: plain(body.recommendation.id),
      title: plain(body.recommendation.title) || plain(body.recommendation.id),
      why: plain(body.recommendation.why),
    }
    : null;
  return {
    ok: true,
    changes,
    skipped,
    counts,
    hasChanges: changes.length > 0,
    summary: list(body.summary).map((one) => plain(one)).filter(Boolean),
    recommendation,
  };
}

/**
 * Can the one Apply button act, and if not, why in plain words?
 *
 * A stale link holds it: applying changes settings, and the project blocks
 * acting on a stale stream (rule 4). A plan with no changes holds it too -
 * there is nothing a person could be accepting.
 */
export function gate({ reading, plan, busy = false, stale = false } = {}) {
  if (!reading) return { enabled: false, why: "Reading this PC…" };
  if (reading.reason) return { enabled: false, why: reading.reason };
  if (!reading.available) return { enabled: false, why: UPDATE_WORDS };
  if (busy) return { enabled: false, why: APPLY_BUSY };
  if (stale) return { enabled: false, why: APPLY_HELD };
  if (!plan) return { enabled: false, why: CHOOSE_FIRST };
  if (plan.ok === false) return { enabled: false, why: plan.error || BAD_PLAN_WORDS };
  if (!plan.hasChanges) return { enabled: false, why: NOTHING_TO_APPLY };
  return { enabled: true, why: "" };
}

/** The words the confirm step shows. Counts come from the PC's own plan. */
export function confirmWords(plan) {
  const view = plan || { changes: [], counts: {} };
  const total = (view.changes || []).length;
  const cards = Number((view.counts || {}).card) || 0;
  if (!total) return NOTHING_TO_APPLY;
  const changes = `${total} change${total === 1 ? "" : "s"}`;
  const asking = cards
    ? ` ${cards} of them will ask you on a card on the PC, one at a time.`
    : " None of them needs an approval card.";
  return `Apply ${changes} now?${asking} Nothing has been changed yet.`;
}

/** `completed_at`, in the owner's local words, or "". */
export function completedWords(seconds) {
  if (typeof seconds !== "number" || !Number.isFinite(seconds) || seconds <= 0) return "";
  try {
    return new Date(seconds * 1000).toLocaleString();
  } catch {
    return "";
  }
}

/** One outcome row's words: the PC's own message, with our fixed fallback. */
export function outcomeWords(state) {
  return OUTCOME_WORDS[plain(state).trim().toLowerCase()] || "";
}

/**
 * `POST /api/setup/apply`'s answer, as the result the page draws.
 *
 * A card still waiting is "still waiting" in words; a denial says the setting
 * stays as it was; `ok: false` keeps its own reason and any outcomes the PC
 * did report. Nothing here is ever turned into "done".
 */
export function applyView(result) {
  const body = object(result);
  if (!body) {
    return { ok: false, error: "That did not work.", rows: [], waiting: 0, changedCount: 0, completedAt: null };
  }
  const rows = [];
  for (const row of list(body.outcomes)) {
    const outcome = object(row);
    if (!outcome) continue;
    const state = plain(outcome.state);
    rows.push({
      setting: plain(outcome.setting),
      label: plain(outcome.label) || plain(outcome.setting),
      effect: plain(outcome.effect),
      effectWords: effectWords(outcome.effect),
      state,
      stateWords: outcomeWords(state),
      message: plain(outcome.message),
      waited: outcome.waited === true,
    });
  }
  const waiting = rows.filter((row) => row.state === "asked-no-answer").length;
  const denied = rows.filter((row) => row.state === "asked-and-denied").length;
  const changed = rows.filter(
    (row) => row.state === "changed" || row.state === "asked-and-approved",
  ).length;
  const changedCount = typeof body.changed_count === "number" ? body.changed_count : changed;
  return {
    ok: body.ok !== false,
    confirmed: body.confirmed === true,
    error: plain(body.error),
    rows,
    waiting,
    denied,
    changedCount,
    completedAt: typeof body.completed_at === "number" ? body.completed_at : null,
    completedWords: completedWords(body.completed_at),
    summary: list(body.summary).map((one) => plain(one)).filter(Boolean),
    recommendation: object(body.recommendation) ? body.recommendation : null,
  };
}

/** The last run's outcomes from `GET /api/setup`, for the card's own line. */
export function lastRunView(reading) {
  const rows = ((reading && reading.lastOutcomes) || []).map((row) => ({
    ...row,
    stateWords: outcomeWords(row.state),
    effectWords: effectWords(row.effect),
  }));
  return {
    rows,
    at: reading && reading.completedAt ? completedWords(reading.completedAt) : "",
    waiting: rows.filter((row) => row.state === "asked-no-answer").length,
  };
}
