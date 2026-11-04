/**
 * "Personalize Jarvis" - the quiz reading and the words the desktop draws
 * (JARVIS-API section 147; `backend/jarvis_setup.py`; the routes
 * `GET /api/setup`, `POST /api/setup/plan`, `POST /api/setup/progress`,
 * `POST /api/setup/apply`).
 *
 * WHAT THIS IS. A guided path through settings that ALREADY exist. The PC owns
 * the questions (their sections and versions), their options and their help
 * lines, the current values, the last accepted answers, and every sentence a
 * plan or an apply answers with. This file holds no question, option, setting
 * key, gate action or tier: it reads the PC's answer and turns it into the
 * small objects the Settings card draws. A question added, renamed or removed
 * by the PC appears, moves or disappears without a desktop release - including
 * the number of questions, which is why this file never says how many there
 * are.
 *
 * THE ONE THING IT MUST NEVER BECOME. It is a GUIDE, not a second settings
 * system. `planBody()` is READ-ONLY: the PC writes nothing and raises no card
 * for it, so this page may ask for a plan whenever the answers change.
 * `applyBody()` is the only body that carries `confirm: true`, and it exists
 * for one click on one button: the owner's explicit "apply these changes".
 * Nothing here applies on load, on a link reconnect, on a changed answer or on
 * a timer. `applyBody` itself does not call anything - `setup-bridge.js` is the
 * only file that sends it, and the test holds both facts.
 * `progressBody()` is the third body (Wave B, 2026-11-03): where the owner is
 * in the card, a dismissal, or "Keep current settings". It records the owner's
 * own Option ids and one timestamp on the PC; it carries no `confirm`, calls no
 * setter and cannot change a setting.
 *
 * THE STEPPER (Wave B, ruling Q1). The card shows one question at a time by
 * default, under a row of section tabs, with a "show only new / unanswered"
 * filter. All of that is four pure functions here - `sectionsOf`,
 * `visibleQuestions`, `nextQuestion`, `progressWords` - so the rules can be
 * tested without a browser and the DOM file only paints what they return. A
 * backend that does not send sections or versions yet still works: every
 * question lands in one unnamed section and the filter keeps only the ones with
 * no answer, which is exactly what it should do with no version data.
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
 * four paths, so the parity check sees one caller, not four.
 *
 * @module setup-questionnaire
 */

/** This page's own words. Every question, option and sentence is the PC's. */
export const TITLE = "Personalize Jarvis";
export const KICKER =
  "\"Set up Jarvis\" above is the five choices that matter on day one; this " +
  "is the longer pass through settings that already exist, in short sections. " +
  "Step through one at a time, or show them all. Every answer changes settings " +
  "that already exist; nothing here is a new kind of rule.";
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

/* ── The stepper's own words (Wave B, 2026-11-03) ─────────────────────────── */

export const STEP_THROUGH = "Step through one by one";
export const SHOW_ALL = "Show all";
export const STEP_MODE_HINT =
  "One question at a time, in the PC's own order. Skip leaves an answer as it " +
  "was and moves on - nothing is written until Apply.";
export const FILTER_LABEL = "Show only new / unanswered";
export const FILTER_EMPTY =
  "Every question is answered and up to date. Untick the filter to read them " +
  "all again.";
/** The same empty panel, when THIS section holds none but other sections do.
 *  A different sentence on purpose: the label above counts the whole
 *  questionnaire, so "every question is answered" here would be a lie. */
export const FILTER_SECTION_EMPTY =
  "Nothing new in this section. Other sections still have some - pick one " +
  "above, or untick the filter to read this section in full.";
export const SECTION_FALLBACK_TITLE = "Questions";
export const BACK = "Back";
export const NEXT = "Next";
export const SKIP = "Skip this one";
export const FINISH = "Finish";
export const STEP_POSITION = (at, total) => `Question ${at} of ${total}`;
export const NOT_NOW = "Not now";
export const KEEP_CURRENT = "Keep current settings";
export const TAKE_AGAIN = "Take it again";
export const DONE_HEADING = "You have finished this pass";
export const DONE_WORDS =
  "Every question the PC has is answered. Change anything above and Apply, or " +
  "press \"Take it again\" to walk the whole quiz from the first question.";
/** The same block after "Keep current settings", which records
 *  `completed_version` and NO answer at all - so it may not claim answers that
 *  do not exist (audit 2026-11-03, bug 5). */
export const KEPT_WORDS =
  "Jarvis will not offer this again. Questions you have not answered are " +
  "still unanswered - answer them above and Apply, or press \"Take it again\" " +
  "to walk the whole quiz from the first question.";
export const KEEP_CURRENT_WORDS =
  "Keep current settings writes no answer and changes nothing: it just records " +
  "that you are happy as things are, so Jarvis stops offering this.";
export const NOT_NOW_WORDS =
  "Not now hides this offer. The card stays exactly where it is, and Jarvis " +
  "will not offer it again for a day.";
/** How long "Not now" hides the offer, in seconds - the same 24 hours the
 *  toast honours (`setup_offer::DISMISS_QUIET_SECS`), because one press must
 *  mean one thing. */
export const OFFER_QUIET_SECS = 24 * 60 * 60;

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
 *
 * `section` and `version` are the Wave B fields (ruling Q3): the PC sends them
 * per question, and `sections` as a top-level list of `{id, title}`. A backend
 * that has not been updated yet sends neither, and the reading is still usable:
 * `section` is `""`, `version` is `0`, and `sections` is derived from the
 * questions - see `sectionsOf`.
 */
export function normaliseReading(raw) {
  const body = object(raw);
  if (!body) {
    return {
      available: false, reason: BAD_READ_WORDS, questions: [], current: {},
      answers: {}, completedAt: null, lastOutcomes: [], cardWaitS: null,
      about: "", storage: "", sections: [],
      version: 0, completedVersion: 0, runs: 0, dismissedAt: null,
      inProgress: null, answeredCount: 0, progressError: "",
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
      // Wave B: where the question lives, and which version of the question set
      // it arrived in. An older backend sends neither; `0` is "no version
      // known", and the filter then keeps only questions with no answer.
      section: plain(q.section).trim(),
      version: wholeNumber(q.version),
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
  const sections = [];
  for (const row of list(body.sections)) {
    const s = object(row);
    if (!s || !plain(s.id)) continue;
    sections.push({ id: plain(s.id), title: plain(s.title) || plain(s.id) });
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
    sections,
    // The new state fields (build spec section 3.3). Each has a default that is
    // true of an older file: version 0 and completed 0 mean "no completion
    // recorded", which makes `isNewOrUnanswered` fall back to the answers alone.
    version: wholeNumber(body.version),
    completedVersion: wholeNumber(body.completed_version),
    runs: wholeNumber(body.runs),
    dismissedAt: typeof body.dismissed_at === "number" ? body.dismissed_at : null,
    inProgress: inProgressOf(body.in_progress),
    answeredCount: wholeNumber(body.answered_count),
    progressError: "",
  };
}

/** A whole, non-negative number, or 0 for anything else. */
function wholeNumber(value) {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : 0;
}

/** `in_progress` as this page needs it, or null: where the owner was. */
function inProgressOf(raw) {
  const body = object(raw);
  if (!body) return null;
  const where = {
    section: plain(body.section).trim(),
    question: plain(body.question).trim(),
    startedAt: typeof body.started_at === "number" ? body.started_at : null,
    draftAnswers: object(body.draft_answers) || {},
  };
  return where.question ? where : null;
}

/* ── The sections, the filter and the stepper (Wave B, ruling Q1) ─────────── */

/**
 * Is this question new, or still unanswered? The filter's whole rule (build
 * spec section 7.2):
 *
 *  * no answer at all, or
 *  * the question arrived in a newer version of the set than the one the owner
 *    last finished (`question.version > completed_version`) - which is what
 *    makes a `1 -> 2` bump offer exactly the questions that changed.
 *
 * With no version data (an older PC) the second half is always false, so the
 * filter keeps exactly the unanswered ones. It never hides a question it cannot
 * judge.
 */
export function isNewOrUnanswered(reading, question) {
  if (!question || !question.id) return false;
  const answers = object(reading && reading.answers) || {};
  if (!Object.prototype.hasOwnProperty.call(answers, question.id)) return true;
  return wholeNumber(question.version) > wholeNumber(reading && reading.completedVersion);
}

/**
 * The PC's questions, split into the sections it declares.
 *
 * The PC's own `sections` order wins when it sends one (`GET /api/setup`'s
 * `sections`). When it does not, the sections are derived from the questions'
 * own `section` values in the order the questions appear - so an older backend
 * still gets one tab per value it does send, and a backend that sends none
 * gets a single tab holding everything rather than a blank page.
 *
 * A section the PC declared but has no questions for is left out: the stepper
 * would open on an empty page.
 */
export function sectionsOf(reading) {
  const questions = (reading && reading.questions) || [];
  const declared = list(reading && reading.sections);
  const order = [];
  const titles = new Map();
  for (const row of declared) {
    if (!row || !row.id) continue;
    if (!titles.has(row.id)) {
      titles.set(row.id, row.title || row.id);
      order.push(row.id);
    }
  }
  if (!order.length) {
    for (const question of questions) {
      const id = question.section || "";
      if (!titles.has(id)) {
        titles.set(id, id || SECTION_FALLBACK_TITLE);
        order.push(id);
      }
    }
  }
  const out = [];
  for (const id of order) {
    const own = questions.filter((q) => (q.section || "") === id);
    if (!own.length) continue;
    out.push({ id, title: titles.get(id) || SECTION_FALLBACK_TITLE, questions: own });
  }
  return out;
}

/**
 * The questions the card is showing: one section's worth (or all of them), and
 * - when the filter is on - only the new and unanswered ones.
 *
 * Pure, and the count in the filter's own label is its length, so the number
 * on screen is computed and never typed.
 */
export function visibleQuestions(reading, { section = "", filter = false } = {}) {
  const want = plain(section);
  return ((reading && reading.questions) || []).filter((q) => {
    if (want && (q.section || "") !== want) return false;
    if (filter && !isNewOrUnanswered(reading, q)) return false;
    return true;
  });
}

/**
 * The filter's empty-state sentence, or "" when there is nothing to explain.
 *
 * ONE SCOPE, TWO LINES. The filter's own label counts every new or unanswered
 * question in the WHOLE questionnaire (`visibleQuestions(reading, {filter:
 * true})`), so the sentence underneath it may not claim the questionnaire is
 * finished while that number is above zero. It used to test the section on
 * screen only, and the two adjacent lines could contradict each other (audit
 * 2026-11-03, bug 6): "(4)" with "Every question is answered" beneath it.
 *
 * A section that holds none of them is a real, different answer - the card
 * must say THAT, not go blank and not claim completion.
 */
export function filterEmptyWords(reading, { section = "", filter = false } = {}) {
  if (!filter) return "";
  if (visibleQuestions(reading, { section, filter: true }).length) return "";
  if (!visibleQuestions(reading, { filter: true }).length) return FILTER_EMPTY;
  return FILTER_SECTION_EMPTY;
}

/**
 * Is the card's own offer row still offered - "Not now" included?
 *
 * The card draws two buttons that both end the offer, and the row must go when
 * either has been pressed. `dismissed_at` is the PC's own timestamp for "Not
 * now" (the toast already honours it); this is the same 24 hours on the same
 * clock (`setup_offer::may_offer_at`), so the row disappears the moment it is
 * pressed and stays gone on the next open within the day, instead of promising
 * quiet and painting itself again (audit 2026-11-03, bug 4).
 *
 * `now` is seconds since the epoch. A zero (or negative) timestamp is not a
 * real press, so it hides nothing; a clock that went backwards still counts as
 * "just pressed", which is the quiet reading - the same two choices the Rust
 * makes.
 */
export function offerShown(reading, now) {
  if (!reading || !reading.available) return false;
  if (!(reading.version > 0 && reading.completedVersion < reading.version)) return false;
  const at = reading.dismissedAt;
  if (typeof at !== "number" || !Number.isFinite(at) || at <= 0) return true;
  const clock = Number(now);
  // No usable clock is still no reason to contradict the PC's timestamp.
  if (!Number.isFinite(clock)) return false;
  return clock - at >= OFFER_QUIET_SECS;
}

/**
 * The next question, in the PC's order, that the draft has no answer for after
 * `fromId`; or null when there is none.
 *
 * This is the stepper's Next and Skip in one rule: Skip simply does not put the
 * id in the draft, and Next lands on the next thing still unanswered - which
 * keeps a retake short without hiding anything (the page still shows the
 * current question). `fromId` of `""` is the start, so
 * `nextQuestion(reading, {}, "")` is the first unanswered question overall.
 */
export function nextQuestion(reading, draft, fromId) {
  const questions = (reading && reading.questions) || [];
  const start = plain(fromId) ? questions.findIndex((q) => q.id === plain(fromId)) : -1;
  for (let i = start + 1; i < questions.length; i += 1) {
    if (answerFor(draft, questions[i].id) === null) return questions[i];
  }
  return null;
}

/**
 * The first question the owner has never answered, in the PC's order - where
 * the stepper opens after the walkthrough or "Finish now". Null when every
 * question has an answer.
 */
export function firstUnanswered(reading) {
  const answers = object(reading && reading.answers) || {};
  return ((reading && reading.questions) || [])
    .find((q) => !Object.prototype.hasOwnProperty.call(answers, q.id)) || null;
}

/**
 * "8 of 25 answered" - the progress line and the toast's own shape.
 *
 * Counted from the DRAFT, so it moves as the owner answers; the total is the
 * PC's own number of questions. It is a count, never a percentage: the PC's
 * question set is not a fixed size, and a percentage over a moving total is a
 * number that lies.
 */
export function progressWords(reading, draft) {
  const total = ((reading && reading.questions) || []).length;
  return `${answeredCount(draft)} of ${total} answered`;
}

/**
 * The "you have finished this pass" block, or "" when this pass is not done.
 *
 * It opens on `completed_version`, which the PC moves for TWO different
 * things: an apply, and "Keep current settings". Only the first leaves answers
 * behind. So the block says what is true of the draft on screen: every
 * question answered gets `DONE_WORDS`; a pass closed without answering some of
 * them gets `KEPT_WORDS`, which never claims an answer that does not exist
 * (audit 2026-11-03, bug 5 - the block said "Every question the PC has is
 * answered" after a press that writes no answer, and kept saying it).
 */
export function finishedPassWords(reading, draft) {
  if (!reading || !(reading.version > 0)) return "";
  if (reading.completedVersion < reading.version) return "";
  const questions = (reading && reading.questions) || [];
  const everyOne = questions.length > 0
    && questions.every((q) => answerFor(draft, q.id) !== null);
  return `${DONE_HEADING}. ${everyOne ? DONE_WORDS : KEPT_WORDS}`;
}

/** "Question 3 of 25", or "" when the id is not one this reading holds. */
export function positionWords(reading, questionId) {
  const questions = (reading && reading.questions) || [];
  const at = questions.findIndex((q) => q.id === plain(questionId));
  if (at < 0) return "";
  return STEP_POSITION(at + 1, questions.length);
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

/**
 * `POST /api/setup/progress`'s body (Wave B, ruling Q6). Three shapes, and only
 * these three:
 *
 *  * `{section?, question, draft_answers?}` - where the owner is in the card,
 *    and the choices staged so far. A draft is NEVER applied: this route calls
 *    no setter, raises no card, and Apply is still the only write.
 *  * `{dismiss: true}` - "Not now". One timestamp on the PC, and the toast and
 *    the launch offer are silent for 24 hours.
 *  * `{keep_current: true}` - "Keep current settings". It writes no answer and
 *    changes no setting; it records that the owner is happy as things are.
 *
 * It never carries `confirm`, and the Rust command builds the same three
 * shapes again before anything is sent.
 *
 * `clearDraft` is "Take it again" (audit 2026-11-03, bug 2). The PC's
 * `progress()` MERGES a supplied draft and only an EXPLICIT empty object
 * clears it - an absent `draft_answers` means "keep what you have". Omitting
 * the field for an empty draft therefore left the PC's stored answers in
 * place, and `load()` merged them straight back on the next open, undoing the
 * retake. With `clearDraft` the empty object is sent on purpose.
 */
export function progressBody({
  section = "", question = "", draft = null, clearDraft = false,
  dismiss = false, keepCurrent = false,
} = {}) {
  if (dismiss) return { dismiss: true };
  if (keepCurrent) return { keep_current: true };
  const body = {};
  const where = plain(section).trim();
  const id = plain(question).trim();
  if (where) body.section = where;
  if (id) body.question = id;
  if (clearDraft) {
    // The one explicit empty object: the PC clears on THIS, and on nothing
    // else. Anything the draft still holds is sent as usual.
    body.draft_answers = answerBody(draft || {});
  } else if (draft) {
    const answers = answerBody(draft);
    if (Object.keys(answers).length) body.draft_answers = answers;
  }
  return body;
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
