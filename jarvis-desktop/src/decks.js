/**
 * Review decks (the owner's decision of 2026-09-30; docs/QUIZ-DECKS-DESIGN.md,
 * "Slice contract (frozen)"; JARVIS-API.md section 102; backend jarvis_decks.py;
 * src-tauri/src/brain/decks.rs).
 *
 * The owner keeps questions from a quiz in a deck and is asked them again on a
 * schedule the PC works out. This module holds the shared words (word for word
 * as the phone uses them, held to tests/fixtures/decks-cases.json), the reading
 * of what the PC sends, the Keep screen's choices and the review session's
 * states. brain.js draws them.
 *
 * Nothing here is stored. No card text, no deck name, no answer - not in
 * localStorage, not as a draft. Deck words are the owner's own words, kept
 * sealed on the PC.
 *
 * The design keeps this calm: no points, no charts, nothing that tells the
 * owner they are late. A test scans every string in this file for the words the
 * contract bans (tests/decks.mjs).
 *
 * @module decks
 */

/* ── The shared words (contract C5) ─────────────────────────────────────── */

export const SECTION_TITLE = "My study decks";
export const CARDS_READY_HEADING = "Cards ready";
export const NOTHING_READY = "Nothing ready today";
export const NEW_PER_DAY_LABEL = "New cards a day";
export const REVIEW = "Review";
/** The button over every deck at once (its visible word is "Review"; this is its name for a screen reader). */
export const REVIEW_ALL = "Review all decks";
export const PAUSE = "Pause";
export const RESUME = "Resume";
export const DELETE_DECK = "Delete this deck";
export const DELETE_CARD = "Delete this card";
export const EDIT = "Edit";
export const SAVE = "Save";
export const CARDS_LINK = "Cards";
export const NEW_DECK = "New deck";
export const DECK_NAME = "Deck name";
export const DELETE = "Delete";
export const CANCEL = "Cancel";
export const DELETE_CONFIRM =
  "Are you sure? Deleting is immediate. Copies in older backups stay until they age out.";
export const EMPTY_STATE = "Keep questions from a quiz to make your first deck.";
export const REVIEW_HIDDEN = "Turn off Hide memory lists to review";

export const KEEP_BUTTON = "Keep these questions";
export const KEEP_FINISH = "Keep and finish";
export const KEEP_CANCEL = "Cancel";
export const KEEP_BACK_PLACEHOLDER = "Type the answer in your own words";
export const CHOOSE_DECK = "Choose a deck";
export const KEEP_HIDDEN = "Turn off Hide memory lists to keep questions";

export const SHOW_ANSWER = "Show answer";
export const TYPED_PLACEHOLDER = "Type your answer (only for you - it is not sent or marked)";
export const ENOUGH = "That's enough for now";
export const MORE = "Do 10 more";
export const STOP = "Stop";
export const BACK_HEADING = "Answer";
export const FROM_TEXT = "From the text";
export const EXAMPLE_SENTENCE = "Example sentence";

/** The four ratings, in this order, with the ids the PC takes. */
export const RATINGS = Object.freeze([
  { id: "again", label: "Didn't remember" },
  { id: "hard", label: "Remembered, with effort" },
  { id: "good", label: "Remembered" },
  { id: "easy", label: "Easy" },
]);

/** The desktop's own words (not in the shared list). */
export const HIDDEN_NAME = "(hidden)";
export const DECKS_INTRO =
  "Questions you keep from a quiz wait here, and Jarvis asks them again when it is time. " +
  "You rate each one yourself. Nothing is sent anywhere.";
export const REVIEW_ENDED = "Back to your decks";
export const LOADING = "Reading your decks.";
export const NO_CARDS = "No cards in this deck yet.";
export const PAUSED_TAG = "Paused";
export const NEW_TAG = "New";
export const FRONT_LABEL = "Front";
export const BACK_LABEL = "Back";
export const KEEP_INTRO =
  "Tick the questions to keep and write the answer for each in your own words. " +
  "Only what you see here is saved, on this PC.";
export const KEEP_SAVING = "Keeping these questions on this PC.";
export const MISSING =
  "Your PC's Jarvis does not have study decks yet - run apply-patches.ps1 on the PC.";
export const RATING_GROUP = "How well did you remember it?";
export const NO_CARD_ANSWER = "(no answer written)";
/**
 * Under the deck list when the rows' ready counts add up to more than the total.
 * (The phone says the same; held to tests/fixtures/decks-cases.json.)
 */
export const PER_DECK_NOTE =
  "New cards a day is shared by every deck, so the decks can show more cards ready than the total above.";

/** The PC's limits (JARVIS-API 102.2 `limits`), until it sends its own. */
export const LIMITS = Object.freeze({
  decks: 20, cards: 1000, name: 60, front: 500, back: 2000, newPerDay: 20,
});

/* ── Reading what the PC sends ─────────────────────────────────────────── */

const text = (v) => (typeof v === "string" ? v : "");
const count = (v) => (Number.isInteger(v) && v >= 0 ? v : 0);
const KINDS = ["study", "spanish", "mixed", "empty"];
const STATES = ["card", "empty", "enough", "paused", "no_decks"];

/** Whether the PC's answer is a refusal `{ok:false, ...}`. */
export function isRefusal(answer) {
  return Boolean(answer && typeof answer === "object" && answer.ok === false);
}

/**
 * The words to show for a refusal: the PC's own message, word for word (it
 * says which of no key / no library / wrong key, and which question is a
 * duplicate), else a general line.
 */
export function refusalWords(refusal) {
  const r = refusal && typeof refusal === "object" ? refusal : {};
  return (typeof r.message === "string" && r.message.trim()) || "Jarvis could not do that.";
}

/** The card-hidden answer of Rust: no call was made. */
export function isHiddenReview(answer) {
  return Boolean(answer && typeof answer === "object" && answer.hidden === true && !answer.state);
}

function readDeck(d) {
  if (!d || typeof d !== "object" || typeof d.id !== "string" || !d.id) return null;
  return {
    id: d.id,
    name: text(d.name),
    cards: count(d.cards),
    ready: count(d.ready),
    paused: d.paused === true,
    kind: KINDS.includes(d.kind) ? d.kind : "study",
  };
}

/**
 * `GET /api/decks`, read. `available` false carries `why`, which is shown word
 * for word; the counts and `line` still work then. Null for a reply that is
 * not a deck list at all.
 */
export function readDecks(raw) {
  if (!raw || typeof raw !== "object" || !Array.isArray(raw.decks)) return null;
  const lim = raw.limits && typeof raw.limits === "object" ? raw.limits : {};
  return {
    available: raw.available !== false,
    why: text(raw.why),
    decks: raw.decks.map(readDeck).filter(Boolean),
    ready: count(raw.ready),
    newPerDay: Number.isInteger(raw.new_per_day) ? raw.new_per_day : 5,
    newLeft: count(raw.new_left),
    nextReadyDay: typeof raw.next_ready_day === "string" && raw.next_ready_day ? raw.next_ready_day : null,
    line: text(raw.line),
    limits: {
      decks: count(lim.decks) || LIMITS.decks,
      cards: count(lim.cards) || LIMITS.cards,
      name: count(lim.name) || LIMITS.name,
      front: count(lim.front) || LIMITS.front,
      back: count(lim.back) || LIMITS.back,
      newPerDay: count(lim.new_per_day) || LIMITS.newPerDay,
    },
    hidden: raw.hidden === true,
  };
}

/** A card of a deck's list (`CardFull`). */
export function readCardFull(c) {
  if (!c || typeof c !== "object" || typeof c.id !== "string" || !c.id) return null;
  return {
    id: c.id,
    front: text(c.front),
    back: text(c.back),
    passage: text(c.passage),
    kind: text(c.kind),
    level: typeof c.level === "string" && c.level ? c.level : null,
    keySource: c.key_source === "text" || c.key_source === "model" ? c.key_source : null,
    keyLabel: typeof c.key_label === "string" && c.key_label ? c.key_label : null,
    isNew: c.new === true,
    dueDay: typeof c.due_day === "string" && c.due_day ? c.due_day : null,
  };
}

/** `GET /api/decks/{id}/cards`, read. */
export function readCards(raw) {
  if (!raw || typeof raw !== "object" || !Array.isArray(raw.cards)) return null;
  const deck = raw.deck && typeof raw.deck === "object" ? raw.deck : {};
  return {
    deckId: text(deck.id),
    deckName: text(deck.name),
    cards: raw.cards.map(readCardFull).filter(Boolean),
    hidden: raw.hidden === true,
  };
}

/** A card up for review (`CardView`). */
export function readCardView(c) {
  if (!c || typeof c !== "object" || typeof c.id !== "string" || !c.id) return null;
  return {
    id: c.id,
    front: text(c.front),
    kind: text(c.kind),
    level: typeof c.level === "string" && c.level ? c.level : null,
    deck: text(c.deck),
    isNew: c.new === true,
  };
}

/**
 * `GET /api/review`, `POST /api/review/more` and `POST /api/review/rate`,
 * read (a rate carries `next` instead of `card`). Null when it is not one.
 */
export function readReview(raw) {
  if (!raw || typeof raw !== "object" || !STATES.includes(raw.state)) return null;
  const run = raw.run && typeof raw.run === "object" ? raw.run : {};
  return {
    state: raw.state,
    ready: count(raw.ready),
    newLeft: count(raw.new_left),
    line: text(raw.line),
    card: readCardView(raw.next !== undefined ? raw.next : raw.card),
    run: { done: count(run.done), limit: count(run.limit) },
    comesBack: typeof raw.comes_back === "string" && raw.comes_back ? raw.comes_back : null,
  };
}

/** `POST /api/review/reveal`, read: `{answer, passage, keyLabel}` or null. */
export function readReveal(raw) {
  if (!raw || typeof raw !== "object" || !raw.back || typeof raw.back !== "object") return null;
  return {
    answer: text(raw.back.answer),
    passage: text(raw.back.passage),
    keyLabel: typeof raw.key_label === "string" && raw.key_label ? raw.key_label : null,
  };
}

/* ── What the section shows ────────────────────────────────────────────── */

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-10-03" as "3 Oct 2026" (display only). Anything else is returned as it came. */
export function formatDay(day) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(day || ""));
  if (!m) return String(day || "");
  const month = Number(m[2]);
  const d = Number(m[3]);
  if (month < 1 || month > 12 || d < 1 || d > 31) return String(day);
  return `${d} ${MONTHS[month - 1]} ${m[1]}`;
}

/** "Next cards ready on 3 Oct 2026", or "" when there is none. */
export function nextReadyLine(day) {
  return day ? `Next cards ready on ${formatDay(day)}` : "";
}

/** "8 cards" / "1 card". */
export function cardsLabel(n) {
  return n === 1 ? "1 card" : `${n} cards`;
}

/** "3 ready". */
export function readyLabel(n) {
  return `${n} ready`;
}

/** The count line of a deck row: "8 cards · 3 ready". */
export function deckMeta(deck) {
  return `${cardsLabel(deck.cards)} · ${readyLabel(deck.ready)}`;
}

/**
 * The section's top: the PC's own `line` under "Cards ready", or the empty
 * state when there are no decks at all (`line` is empty then).
 */
export function sectionTop(view) {
  if (!view) return { line: "", empty: false };
  return { line: view.line, empty: view.available && !view.decks.length && !view.line };
}

/**
 * Whether "Review" can be offered for a deck row: the deck has cards ready and
 * is not paused (never while the private lists are hidden or the decks cannot
 * be opened). The phone has the same rule.
 */
export function canReview(view, deck) {
  return Boolean(view && view.available && !view.hidden && deck && !deck.paused && deck.ready > 0);
}

/** Whether "Review all decks" can be offered: something is ready in a deck that is not paused. */
export function canReviewAll(view) {
  return Boolean(view && view.available && !view.hidden && view.ready > 0);
}

/**
 * Whether to say why the decks' own ready counts add up to more than the total
 * (the day's new cards are shared between decks, so each row counts what that
 * deck alone would offer).
 */
export function perDeckNoteShown(view) {
  return Boolean(view && view.decks.reduce((sum, d) => sum + d.ready, 0) > view.ready);
}

/**
 * What the review shows for the PC's `state` (contract C4). `nextDay` is
 * `next_ready_day` from the deck list. Returns
 * `{kind, title, note, actions}`; `actions` names buttons: `more`, `stop`.
 * `no_decks` means: leave the review and go back to the decks page.
 */
export function reviewScreen(review, nextDay) {
  const r = review || { state: "no_decks", line: "" };
  switch (r.state) {
    case "card":
      return { kind: "card", title: "", note: "", actions: ["stop"] };
    case "empty":
      return { kind: "empty", title: NOTHING_READY, note: nextReadyLine(nextDay), actions: ["stop"] };
    case "enough":
      return { kind: "enough", title: ENOUGH, note: "", actions: ["more", "stop"] };
    case "paused":
      return { kind: "paused", title: r.line, note: "", actions: ["stop"] };
    default:
      return { kind: "leave", title: "", note: "", actions: [] };
  }
}

/**
 * The passage's heading on a revealed card. A key written by the model is an
 * example sentence; the owner's own text is "From the text".
 */
export function backPassageHeading(reveal) {
  return reveal && reveal.keyLabel ? EXAMPLE_SENTENCE : FROM_TEXT;
}

/** A card's level as the shared line, or "". */
export function cardLevelLine(level) {
  return typeof level === "string" && /^(A1|A2|B1|B2|C1|C2)$/.test(level)
    ? `Level ${level} (roughly)` : "";
}

/* ── The Keep screen (contract C3) ─────────────────────────────────────── */

/** `Kept 3 questions` / `Kept 1 question`. */
export function keptLine(n) {
  return `Kept ${n} ${n === 1 ? "question" : "questions"}`;
}

/** Ticked by default for a mark of Partly or Not yet; not for Got it. */
export function defaultTick(level) {
  return level === "partly" || level === "not_yet";
}

/**
 * The rows of the Keep screen: every ANSWERED question of the open quiz. The
 * back is prefilled with the owner's own typed answer only for a Got it mark,
 * from `answers` (a Map of question number -> what the owner typed, held in
 * memory until the quiz ends, never for a crisis answer); it is empty for
 * Partly, Not yet, or an answer the app no longer has. The model's comment is
 * never a back.
 */
export function keepRows(quiz, answers) {
  const held = answers instanceof Map ? answers : new Map();
  const qs = quiz && Array.isArray(quiz.questions) ? quiz.questions : [];
  return qs.filter((q) => q.mark).map((q) => ({
    n: q.n,
    prompt: q.prompt,
    passage: q.mark.passage,
    tick: defaultTick(q.mark.level),
    back: q.mark.level === "got_it" && typeof held.get(q.n) === "string" ? held.get(q.n) : "",
  }));
}

/** The count line under a back box: "12 / 2000 characters". */
export function backCount(value) {
  const n = String(value || "").length;
  return { n, ok: n <= LIMITS.back, note: `${n} / ${LIMITS.back} characters` };
}

/** The default name of a new deck: the quiz's title, cut to 60 characters. */
export function defaultDeckName(title) {
  return Array.from(String(title || "").trim()).slice(0, LIMITS.name).join("");
}

/** Whether a new deck's name is 1-60 characters after trimming. */
export function deckNameOk(name) {
  const n = Array.from(String(name || "").trim()).length;
  return n >= 1 && n <= LIMITS.name;
}

/**
 * The `keep` body, or `{error}` in plain words. `choice` is a deck id or ""
 * for a new deck (named `newName`). Only `n` and `answer` go per card.
 */
export function keepPayload(rows, choice, newName) {
  const ticked = (rows || []).filter((r) => r.tick);
  if (!ticked.length) return { error: "Tick at least one question to keep." };
  for (const r of ticked) {
    if (!backCount(r.back).ok) return { error: "That answer is too long. Keep it to 2,000 characters or fewer." };
  }
  const cards = ticked.map((r) => ({ n: r.n, answer: String(r.back || "") }));
  if (choice) return { keep: { deck: choice, cards } };
  if (!deckNameOk(newName)) return { error: "A deck name is 1 to 60 characters.", nameProblem: true };
  return { keep: { deck: null, new_deck: String(newName).trim(), cards } };
}
