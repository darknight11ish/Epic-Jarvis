/**
 * Quiz me on a text (the owner's "go ahead", 2026-09-30;
 * docs/STUDY-FROM-TEXT-DESIGN.md section 11; JARVIS-API.md section 98;
 * backend jarvis_quiz.py; src-tauri/src/brain/quiz.rs).
 *
 * The owner pastes some text, the PC's local model writes a few questions,
 * the owner types an answer to each and sees a mark. This module holds the
 * shared words, the limits, the plain message for every error code and the
 * reading of what the PC sends; brain.js draws the section.
 *
 * Nothing here is stored. The quiz lives in the PC's memory only; this app
 * keeps no text, no answers and no marks - not in localStorage, not as a
 * draft. The text is outside text: Jarvis never learns facts from it.
 *
 * @module quiz
 */

export const QUIZ_TITLE = "Quiz me on a text";
export const QUIZ_INTRO =
  "Paste some text and Jarvis writes a few questions about it. Your answers are marked by the model " +
  "on this PC. Nothing is saved unless you choose Keep, nothing is learned, and nothing leaves this PC.";
export const START_LABEL = "Write questions";
export const ANSWER_LABEL = "Check my answer";
export const FINISH_LABEL = "Finish";
export const STOP_LABEL = "Stop and forget this quiz";
export const CLOSE_LABEL = "Close";
export const AGAIN_HEADING = "Look at these again";
export const AGAIN_EMPTY = "Nothing to look at again.";
export const OUTSIDE_LINE =
  "This text is treated as outside text: Jarvis never learns facts from it.";
export const GUESS_LABEL = "Jarvis's guess";
/** Shown in place of a question's words while the private lists are hidden (both apps). */
export const HIDDEN_WORDS = "(hidden)";

/** Extra words of the desktop's own (not in the shared list). */
export const NEXT_LABEL = "Next question";
export const TEXT_PLACEHOLDER = "Paste the text here";
export const ANSWER_PLACEHOLDER = "Type your answer";
export const SOURCE_LABEL = "From the text";
export const QUIZ_MISSING =
  "Your PC's Jarvis does not have Quiz yet - run apply-patches.ps1 on the PC.";
export const WRITING = "Writing questions on this PC. This can take a little while.";
export const CHECKING = "Checking your answer on this PC. This can take a little while.";

/** The PC's limits (JARVIS-API section 98). */
export const LIMITS = Object.freeze({
  textMin: 200, textMax: 20000, answerMin: 1, answerMax: 2000, count: 5, open: 3,
});

/** The three marks, in the owner's own words. */
export const LEVEL_LABELS = Object.freeze({
  got_it: "Got it", partly: "Partly", not_yet: "Not yet",
});

export const KIND_LABELS = Object.freeze({
  recall: "Remember", explain: "Explain why", apply: "Apply",
  // Spanish practice (JARVIS-API section 102.4); the shared words.
  translate: "Translate", blank: "Fill the blank", complete: "Finish the sentence",
});

/* ── Spanish practice (docs/QUIZ-DECKS-DESIGN.md, Slice contract C2 and C5) ── */

export const MODE_TEXT = "Text";
export const MODE_SPANISH = "Spanish practice";
export const MODES = Object.freeze([
  { id: "text", label: MODE_TEXT },
  { id: "spanish", label: MODE_SPANISH },
]);
export const LEVEL_HEADING = "Level (roughly)";
export const LEVEL_IDS = Object.freeze(["A1", "A2", "B1", "B2", "C1", "C2"]);
export const DEFAULT_LEVEL = "A2";
export const EXERCISES = Object.freeze([
  { id: "translate", label: "Translate" },
  { id: "blank", label: "Fill the blank" },
  { id: "complete", label: "Finish the sentence" },
  { id: "mixed", label: "Mixed" },
]);
export const DEFAULT_EXERCISE = "mixed";
export const TOPIC_LABEL = "Topic (optional)";
export const TOPIC_MAX = 60;
export const SPANISH_TEXT_PLACEHOLDER = "Paste Spanish text (optional)";
export const EXAMPLE_HEADING = "Example sentence";
export const ACCENTS = Object.freeze(["á", "é", "í", "ó", "ú", "ñ", "ü", "¿", "¡"]);
/** Desktop's own words (not in the shared list). */
export const SPANISH_WRITING = "Writing Spanish questions on this PC. This can take a little while.";
export const SPANISH_INTRO =
  "Type your answers in Spanish. Paste some Spanish text of your own and the questions come from it, " +
  "or leave the box empty and Jarvis writes the sentences. Nothing is saved unless you choose Keep, nothing is learned, and nothing leaves this PC.";
export const OLD_PC_SPANISH =
  "Your PC's Jarvis does not have Spanish practice yet - run apply-patches.ps1 on the PC.";
export const ACCENT_ROW_LABEL = "Spanish letters";

/** "Level B1 (roughly)". Empty for no level. */
export function levelLine(level) {
  return LEVEL_IDS.includes(level) ? `Level ${level} (roughly)` : "";
}

/** The live count under the topic box: "0 / 60". */
export function topicCount(value) {
  const n = String(value || "").length;
  return { n, ok: n <= TOPIC_MAX, note: `${n} / ${TOPIC_MAX}` };
}

/**
 * Puts `ch` into `value` where the cursor (or selection) is. Returns the new
 * value and where the cursor goes; a value that would pass `max` characters
 * is left as it is.
 */
export function insertAtCursor(value, start, end, ch, max = 2000) {
  const v = String(value || "");
  const a = Number.isInteger(start) ? Math.max(0, Math.min(start, v.length)) : v.length;
  const b = Number.isInteger(end) ? Math.max(a, Math.min(end, v.length)) : a;
  const next = v.slice(0, a) + ch + v.slice(b);
  if (next.length > max) return { value: v, caret: a };
  return { value: next, caret: a + ch.length };
}

/**
 * The choices for `POST /api/quiz` in Spanish practice. Text may be empty (the
 * model then writes the sentences). Returns `{args}` or `{error}`.
 */
export function spanishStartArgs({ text, level, exercise, topic }) {
  const t = String(text || "").trim();
  if (t) {
    const c = textCount(t);
    if (!c.ok) return { error: errorWords({ error: c.n < LIMITS.textMin ? "text_too_short" : "text_too_long" }) };
  }
  if (!topicCount(topic).ok) return { error: "Keep the topic to 60 characters or fewer." };
  const args = { mode: "spanish", level: LEVEL_IDS.includes(level) ? level : DEFAULT_LEVEL,
    exercise: EXERCISES.some((e) => e.id === exercise) ? exercise : DEFAULT_EXERCISE };
  if (t) args.text = String(text);
  const tp = String(topic || "").trim();
  if (tp) args.topic = tp;
  return { args };
}

/**
 * What to show under a mark after the answer (contract C2): the key line
 * "Answer: <expected>" and the backend's own `key_label` under it, the
 * passage's heading (`From the text` when the key is the owner's own text or
 * in Text mode, `Example sentence` when the model wrote it), and whether
 * "Jarvis's guess" shows (only a model-marked, unverified mark).
 */
export function markLines(mark, quiz) {
  const m = mark || {};
  const q = quiz || {};
  return {
    answerLine: typeof m.expected === "string" && m.expected ? `Answer: ${m.expected}` : "",
    keyLabel: typeof m.keyLabel === "string" ? m.keyLabel : "",
    passageHeading: q.keySource === "model" ? EXAMPLE_HEADING : SOURCE_LABEL,
    showGuess: m.markedBy === "model" && q.verified !== true,
  };
}

export function levelLabel(level) {
  return LEVEL_LABELS[level] || "";
}

/**
 * A plain sentence for every error code of the contract. An unknown code
 * falls back to the PC's own message, then to a general line.
 */
export const ERROR_WORDS = Object.freeze({
  text_too_short: "That text is too short to make questions from. Paste at least 200 characters.",
  text_too_long: "That text is too long. Paste at most 20,000 characters, or a shorter part of it.",
  bad_count: "Ask for between 1 and 10 questions.",
  too_many_quizzes:
    "Three quizzes are already open on the PC. Stop and forget one before starting another.",
  not_found: "That quiz is not open any more. It may have ended, or the PC restarted. Paste the text again to start a new one.",
  bad_question: "That is not one of this quiz's questions.",
  already_answered: "You have already answered that question.",
  answer_empty: "Type an answer first.",
  answer_too_long: "That answer is too long. Keep it to 2,000 characters or fewer.",
  model_unavailable:
    "The model on this PC did not answer. Nothing was changed - try again in a moment.",
});

/** The words to show for a refusal `{ok:false, error, message}`. */
export function errorWords(refusal) {
  const r = refusal && typeof refusal === "object" ? refusal : {};
  return ERROR_WORDS[r.error]
    || (typeof r.message === "string" && r.message ? r.message : "")
    || "Jarvis could not do that.";
}

const LEVELS = Object.keys(LEVEL_LABELS);
const KINDS = Object.keys(KIND_LABELS);
const MODE_IDS = MODES.map((m) => m.id);
const text = (v) => (typeof v === "string" ? v : "");
const count = (v) => (Number.isInteger(v) && v >= 0 ? v : 0);

/** Whether the PC's answer is a refusal we can put words to. */
export function isRefusal(answer) {
  return Boolean(answer && typeof answer === "object" && answer.ok === false);
}

/**
 * A crisis answer (JARVIS-API 98.4): the PC did not mark it and sends
 * `{ok:true, crisis:true, message}` instead. The message is the PC's own
 * words (the chat's help wording) - never written in this app. Returns the
 * message, or "" when the answer is not a crisis one (or has no words).
 */
export function readCrisis(answer) {
  return answer && typeof answer === "object" && answer.crisis === true
    && typeof answer.message === "string" ? answer.message.trim() : "";
}

/** True for a crisis answer, even one that came without usable words. */
export function isCrisis(answer) {
  return Boolean(answer && typeof answer === "object" && answer.crisis === true);
}

/**
 * The PC's help message as paragraphs of runs, so it can be drawn with
 * textContent only: `**bold**` becomes a bold run, a blank line a new
 * paragraph. Returns `[[{text, bold}, ...], ...]`.
 */
export function crisisParagraphs(message) {
  return String(message || "").split(/\n{2,}/).map((p) => p.trim()).filter(Boolean).map((p) =>
    p.split("**").map((t, i) => ({ text: t, bold: i % 2 === 1 })).filter((r) => r.text));
}

/**
 * `{level, comment, passage, markedBy, expected, keyLabel}`, or null when it
 * is not a real mark. An older PC sends no `marked_by`: its marks are the
 * model's, so `markedBy` is "model" then (the guess label stays, as before).
 */
export function readMark(m) {
  if (!m || typeof m !== "object" || !LEVELS.includes(m.level)) return null;
  return {
    level: m.level, comment: text(m.comment), passage: text(m.passage),
    markedBy: m.marked_by === "code" ? "code" : "model",
    expected: typeof m.expected === "string" ? m.expected : null,
    keyLabel: typeof m.key_label === "string" && m.key_label ? m.key_label : null,
  };
}

/**
 * The PC's `quiz`, read. Null when there is no usable quiz. A question with
 * no whole-number `n` is dropped, never guessed. `hidden` is true while the
 * private lists are hidden (Rust took the words out).
 */
export function readQuiz(q) {
  if (!q || typeof q !== "object" || typeof q.id !== "string" || !q.id) return null;
  const questions = (Array.isArray(q.questions) ? q.questions : [])
    .filter((x) => x && typeof x === "object" && Number.isInteger(x.n) && x.n >= 1)
    .map((x) => ({
      n: x.n,
      kind: KINDS.includes(x.kind) ? x.kind : "recall",
      prompt: text(x.prompt),
      mark: readMark(x.mark),
    }));
  return {
    id: q.id,
    title: text(q.title),
    verified: q.grader_verified === true,
    questions,
    answered: count(q.answered),
    hidden: q.hidden === true,
    // An older PC sends no `mode` (JARVIS-API 102.4): `mode` is then "" and the
    // page says so and offers Text mode only.
    mode: MODE_IDS.includes(q.mode) ? q.mode : "",
    level: LEVEL_IDS.includes(q.level) ? q.level : null,
    keySource: q.key_source === "text" || q.key_source === "model" ? q.key_source : null,
    // The PC's own words about Spanish crisis phrases - never copied here.
    notice: typeof q.notice === "string" ? q.notice : "",
    // A quiz made from a video's captions carries `source: "youtube"` (JARVIS-API
    // 112); a text or Spanish quiz has neither key.
    source: q.source === "youtube" ? "youtube" : "",
  };
}

/** `{counts, again}` from the PC's summary; missing pieces are zero/empty. */
export function readSummary(s) {
  const o = s && typeof s === "object" ? s : {};
  const c = o.counts && typeof o.counts === "object" ? o.counts : {};
  return {
    counts: { got_it: count(c.got_it), partly: count(c.partly), not_yet: count(c.not_yet) },
    again: (Array.isArray(o.again) ? o.again : []).filter((n) => Number.isInteger(n) && n >= 1),
  };
}

/** The first question with no mark yet, or null when all are answered. */
export function nextQuestion(quiz) {
  return quiz ? quiz.questions.find((q) => !q.mark) || null : null;
}

/** "Question 2 of 5 - 1 answered", or "All 5 answered" when nothing is left. */
export function progressLine(quiz) {
  if (!quiz || !quiz.questions.length) return "";
  const total = quiz.questions.length;
  const next = nextQuestion(quiz);
  const done = quiz.questions.filter((q) => q.mark).length;
  return next
    ? `Question ${next.n} of ${total} · ${done} answered`
    : `All ${total} answered`;
}

/** The live count under the paste box, and whether it can be sent. */
export function textCount(value) {
  // The PC checks the length AFTER trimming, so the count is of the trimmed text.
  const n = String(value || "").trim().length;
  const ok = n >= LIMITS.textMin && n <= LIMITS.textMax;
  let note = `${n.toLocaleString("en-US")} / ${LIMITS.textMax.toLocaleString("en-US")} characters`;
  if (n < LIMITS.textMin) note += ` · at least ${LIMITS.textMin} needed`;
  else if (n > LIMITS.textMax) note += " · too long";
  return { n, ok, note };
}

/** One line of the "Look at these again" list: "3. The question's words". */
export function againLine(n, quiz) {
  const q = quiz ? quiz.questions.find((x) => x.n === n) : null;
  return `${n}. ${q && q.prompt ? q.prompt : HIDDEN_WORDS}`;
}

/** The live count under the answer box, and whether it can be sent. */
export function answerCount(value) {
  const n = String(value || "").trim().length;
  const raw = String(value || "").length;
  const ok = n >= LIMITS.answerMin && raw <= LIMITS.answerMax;
  return { n: raw, ok, note: `${raw} / ${LIMITS.answerMax} characters` };
}

/** The summary as a sentence for the counts (no percentage, no grade). */
export function countsLine(summary) {
  const c = summary.counts;
  return `${c.got_it} ${LEVEL_LABELS.got_it} · ${c.partly} ${LEVEL_LABELS.partly} · ${c.not_yet} ${LEVEL_LABELS.not_yet}`;
}

/* ── Quiz me on a YouTube video (docs/STUDY-FROM-TEXT-DESIGN.md section 14,
      JARVIS-API.md section 112; youtube.js draws it; brain/youtube.rs) ───────

   The owner pastes a link; the PC raises ONE approval card for it and, after a
   yes, reads the video's CAPTION TEXT and writes questions. Nothing here is
   stored, and the link is never kept: not in a draft, a log, a notification
   or an error sentence. Every refusal and failure sentence is the PC's own,
   shown as it came - this file writes none of its own for the YouTube part
   (the contract's one missing-feature line, and the few below, aside). These
   words and rules are held to tests/fixtures/youtube-cases.json, which the
   phone reads too. */

export const YT_TITLE = "Quiz me on a YouTube video";
export const YT_INTRO =
  "Paste a YouTube link and Jarvis reads the video's captions (the words shown as subtitles), " +
  "then quizzes you on them. It asks with a card first, every time.";
export const YT_TERMS =
  "This breaks YouTube's terms and may be blocked. Only the caption text is fetched - " +
  "never the video or its sound. The link tells YouTube which video you are studying.";
export const YT_OUTSIDE =
  "The captions are treated as outside text: Jarvis never learns facts from them. " +
  "Your answers are marked by the model on this PC.";
export const YT_PLACEHOLDER = "Paste a YouTube video link";
export const YT_START = "Read the captions and write questions";
export const YT_CANCEL = "Cancel";
export const YT_LABEL = "From YouTube captions";
export const YT_MISSING =
  "Your PC's Jarvis does not have YouTube quizzes yet - run apply-patches.ps1 on the PC.";

/** The desktop's own words (the phone says the same). */
export const YT_STARTING = "Asking…";
export const YT_CANCELLING = "Cancelling…";
export const YT_UNREADABLE = "Your PC sent something this app could not read.";
export const YT_NO_LINK = "Paste a video link first.";

export const YT_POLL_SECONDS = 2;
export const YT_UNKNOWN_LIMIT_SECONDS = 180;
export const YT_LINK_MAX = 300;
/** The question count sent with a link (the phone's default too). */
export const YT_COUNT = 5;

/** The state words the PC sends, and what an app does with each. */
const YT_PHASES = Object.freeze({
  waiting: "waiting", fetching: "working", writing: "working", ready: "ready",
  denied: "ended", timed_out: "ended", withdrawn: "ended", refused: "ended", failed: "ended",
});

/** When the PC's message is empty, its state's reference words (an end must never be blank). */
const YT_STATE_WORDS = Object.freeze({
  waiting: "Waiting for your yes on the approval card.",
  fetching: "Reading the captions from YouTube...",
  writing: "Writing the questions...",
  ready: "Ready.",
  denied: "You said no, so nothing was fetched.",
  timed_out: "Nobody answered the card in time, so nothing was fetched.",
  withdrawn: "You cancelled before the card was answered, so nothing was fetched.",
  refused: "The card could not be answered, so nothing was fetched.",
  failed: "Could not make a quiz from that video.",
});

/**
 * "waiting" (also offers Cancel), "working", "ready" or "ended". An unknown
 * word is still "working" (decode leniently); ytIsKnown tells the caller so it
 * can stop after YT_UNKNOWN_LIMIT_SECONDS with the PC's last message.
 */
export function ytPhase(state) {
  return Object.prototype.hasOwnProperty.call(YT_PHASES, state) ? YT_PHASES[state] : "working";
}

export function ytIsKnown(state) {
  return Object.prototype.hasOwnProperty.call(YT_PHASES, state);
}

/** Whether polling goes on for this phase. */
export function ytKeepPolling(phase) {
  return phase === "waiting" || phase === "working";
}

/** True once a state this app does not know has been seen for the limit. `sinceMs` is null when known. */
export function ytGiveUpOnUnknown(sinceMs, nowMs) {
  return Number.isFinite(sinceMs) && nowMs - sinceMs >= YT_UNKNOWN_LIMIT_SECONDS * 1000;
}

const YT_ID = /^[A-Za-z0-9_-]{1,64}$/;

/** Whether an id is safe to put in a route. */
export function ytValidId(id) {
  return typeof id === "string" && YT_ID.test(id);
}

/** Whether the field holds something to send. The app does not judge the link itself. */
export function ytCanStart(link) {
  return String(link || "").trim().length > 0;
}

/**
 * One request as the PC describes it, or null with no usable id or state.
 * Unknown keys are ignored; a `quiz` that cannot be read leaves `quiz` null.
 */
export function ytReadRequest(o) {
  if (!o || typeof o !== "object") return null;
  const id = typeof o.id === "string" ? o.id.trim() : "";
  const state = typeof o.state === "string" ? o.state.trim() : "";
  if (!ytValidId(id) || !state) return null;
  const minutes = Number.isInteger(o.minutes) && o.minutes >= 1 ? o.minutes : null;
  const message = typeof o.message === "string" ? o.message.trim() : "";
  const link = typeof o.link === "string" && o.link.trim() ? o.link.trim() : null;
  return {
    id, state, message, link,
    truncated: o.truncated === true,
    minutes,
    error: typeof o.error === "string" && o.error ? o.error : null,
    quiz: readQuiz(o.quiz),
    phase: ytPhase(state),
  };
}

/** `GET /api/youtube`: whether the feature is there, the link limit and the newest request. */
export function ytReadInfo(answer) {
  if (!answer || typeof answer !== "object" || typeof answer.available !== "boolean") return null;
  const limits = answer.limits && typeof answer.limits === "object" ? answer.limits : {};
  const linkMax = Number.isInteger(limits.link) && limits.link >= 1 && limits.link <= 10000
    ? limits.link : YT_LINK_MAX;
  return {
    available: answer.available,
    linkMax,
    latest: ytReadRequest(answer.latest),
    hidden: answer.hidden === true,
  };
}

/** What to show for a request: the PC's message, else its state's reference words. */
export function ytShown(request) {
  return request.message || YT_STATE_WORDS[request.state] || "";
}

/** The line above the questions of a captions quiz that covers only the first part, else null. */
export function ytTruncatedNote(request) {
  return request.truncated ? ytShown(request) : null;
}

/**
 * What to make of the answer to a start, a read or a cancel. `lead` is the
 * short opening of the app's own sentences ("Not started."), used only when
 * the PC gave no words. Returns `{ok, request, said, code, gone}`:
 * a refusal shows the PC's `message` word for word; `gone` means the PC no
 * longer has the request.
 */
export function ytOutcome(answer, lead) {
  if (!answer || typeof answer !== "object") {
    return { ok: false, request: null, said: `${lead} ${YT_UNREADABLE}`, code: null, gone: false };
  }
  if (answer.ok === false) {
    const code = typeof answer.error === "string" && answer.error ? answer.error : null;
    const own = typeof answer.message === "string" ? answer.message.trim() : "";
    return {
      ok: false, request: null, code, gone: code === "not_found",
      said: own || `${lead} Your PC's Jarvis cannot do this right now.`,
    };
  }
  const request = ytReadRequest(answer.request);
  if (!request) return { ok: false, request: null, said: `${lead} ${YT_UNREADABLE}`, code: null, gone: false };
  // A "ready" with no readable quiz is not a quiz: say so rather than open nothing.
  if (request.phase === "ready" && (!request.quiz || !request.quiz.questions.length)) {
    return { ok: false, request, said: `${lead} ${YT_UNREADABLE}`, code: null, gone: false };
  }
  return { ok: true, request, said: ytShown(request), code: null, gone: false };
}

/** Whether a read quiz came from YouTube captions. */
export function ytFromCaptions(quiz) {
  return Boolean(quiz && quiz.source === "youtube");
}
