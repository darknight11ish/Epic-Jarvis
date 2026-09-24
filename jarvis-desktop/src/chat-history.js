/**
 * The conversation so far, which the quickbar sends along with each question.
 *
 * The quickbar used to send the newest question alone (plus any note or
 * clipboard context for that one turn). Nothing in this repository shows the
 * backend keeping a conversation of its own - requests carry no conversation
 * id, and every backend patch that touches `/api/chat` works on the
 * `messages` array the client sent - so a follow-up reached the model with
 * nothing before it. The HUD window's page already sends its own history
 * (`jarvis_hud.html`, `S.messages.slice(-12)`); this brings the quickbar, and
 * the phone (`jarvis-client/.../net/ChatHistory.kt`), in line. (Since chat
 * history on the PC, section 18, requests DO carry a `conversation_id` - but
 * only so the PC can file what it records; the model still gets only the
 * `messages` sent, so this window's history is still what a follow-up needs.)
 *
 * What is kept: pairs of (the question as sent, the whole answer), plain
 * text, for answers that finished, and where each question's words came
 * from (its `provenance`, below). No system turns, no screenshots, no tool
 * output, no approvals, no ids. A past answer that says "I have proposed
 * that" is only words; approvals are decided by id and nowhere else.
 *
 * Where the words came from (JARVIS-API.md section 18, "Chat history").
 * Every user turn carries a `provenance` - "typed", "voice", "clipboard",
 * "pasted", "picture_caption" - and it is KEPT with the turn and sent again
 * with it on every later request. It used to be plain strings here, so a tag
 * would have fallen off one turn later and the PC could not have told the
 * owner's own words from text pasted in. A turn with no tag is sent with
 * none, which the PC reads as "unknown" and treats as not the owner's own
 * words (fail closed).
 *
 * Which conversation: `newConversationId()` makes the id each request
 * carries as `conversation_id`. A new one on "New conversation", when the
 * chat is cleared (Esc), and when the app starts - so the PC's History list
 * shows one entry per conversation, not one per day.
 *
 * Where: in this window's memory only. Never written to disk. Cleared by
 * "New conversation" and by dismissing the window with Esc - the same moment
 * the answer card itself is cleared.
 *
 * How much. The model has 16,384 tokens in all (jarvis-primary.Modelfile).
 * Set aside: 2,048 for the answer (generous - every window now gets 1,024,
 * the Modelfile's num_predict), 250 for the Modelfile's SYSTEM prompt and
 * the chat template, 400 for the recalled-facts block, 2,600 for the tool
 * list (13 tools, 7,851 characters of JSON in backend/jarvis_agent.py), and
 * 3,000 for the new question with anything pasted in. That leaves about
 * 8,000. History gets at most MAX_CHARS = 18,000 characters - 6,000 tokens
 * even at a pessimistic 3 characters per token - and at most MAX_EXCHANGES =
 * 10 pairs.
 *
 * When it outgrows either limit, the oldest pairs go until it is down to
 * KEEP_EXCHANGES and KEEP_CHARS, not just one: the model re-reads its whole
 * prompt whenever the START of it changes (Ollama reuses what it has already
 * read only up to the first difference), which costs about 3 seconds at 6,000
 * tokens on this card. Dropping several at once means the start then stays
 * put for several turns. A message is never cut in half.
 *
 * These are an UPPER bound. The model really loaded may have far less room
 * (4,096 tokens unless jarvis-primary is the one loaded), so the PC asks
 * Ollama what it has and trims the oldest turns to fit before sending
 * (backend/jarvis_agent.py fit_messages, chat-stream.patch). Only the PC can
 * know that number.
 *
 * Mirrors ChatHistory.kt number for number. Change one, change both.
 */

export const MAX_EXCHANGES = 10;

/**
 * The tags the PC knows (section 18). "shared" is the phone's Share sheet
 * and never comes from this app; it is listed so the list is the whole list.
 */
export const PROVENANCE = Object.freeze([
  "typed",
  "voice",
  "shared",
  "clipboard",
  "pasted",
  "picture_caption",
]);

/** `tag` if the PC knows it, else null - sent as no tag at all ("unknown"). */
export function knownProvenance(tag) {
  return PROVENANCE.includes(tag) ? tag : null;
}

/**
 * A fresh conversation id: 8-64 characters of [A-Za-z0-9_-], which is what
 * the PC accepts (anything else it ignores). A random UUID where the page
 * has one, else 32 random hex characters - never `Math.random`, so two
 * windows cannot pick the same id.
 */
export function newConversationId(cryptoImpl = globalThis.crypto) {
  if (cryptoImpl && typeof cryptoImpl.randomUUID === "function") {
    return cryptoImpl.randomUUID();
  }
  const bytes = new Uint8Array(16);
  cryptoImpl.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

/** What the PC accepts as a conversation id (section 18). */
export const CONVERSATION_ID = /^[A-Za-z0-9_-]{8,64}$/;
export const MAX_CHARS = 18000;
export const KEEP_EXCHANGES = 6;
export const KEEP_CHARS = 12000;

/** Total characters in a window of `{ question, answer }` pairs. */
export function historyChars(window) {
  return window.reduce((n, ex) => n + ex.question.length + ex.answer.length, 0);
}

function fits(window, maxExchanges, maxChars) {
  return window.length <= maxExchanges && historyChars(window) <= maxChars;
}

function isBlank(text) {
  return typeof text !== "string" || !text.trim();
}

/**
 * `window` with one more finished turn on the end, trimmed if it has grown
 * past the limits. Never changes `window` itself. A blank question or answer
 * is not a turn worth replaying, so `window` comes back unchanged.
 *
 * `provenance` is where the question's words came from; it stays with the
 * pair for as long as the pair is kept. A tag the PC does not know is kept
 * as none.
 *
 * The newest pair is the last to go: it is kept alone if it is bigger than
 * KEEP_CHARS but inside MAX_CHARS, and dropped only when it is too big to
 * send at all.
 */
export function commitExchange(window, question, answer, provenance) {
  if (isBlank(question) || isBlank(answer)) return window;
  const tag = knownProvenance(provenance);
  const next = [...window, tag ? { question, answer, provenance: tag } : { question, answer }];
  if (fits(next, MAX_EXCHANGES, MAX_CHARS)) return next;
  while (next.length > 1 && !fits(next, KEEP_EXCHANGES, KEEP_CHARS)) next.shift();
  return fits(next, MAX_EXCHANGES, MAX_CHARS) ? next : [];
}

/**
 * The window as OpenAI-shaped messages, oldest first: a user turn and an
 * assistant turn per pair, `role` and `content` only - plus, on a user turn,
 * the `provenance` it was first sent with. The PC takes that tag off before
 * anything reaches a model. The caller puts the new question (and any
 * system turns that belong to it alone) after these.
 */
export function historyMessages(window) {
  const out = [];
  for (const ex of window) {
    out.push(userMessage(ex.question, ex.provenance));
    out.push({ role: "assistant", content: ex.answer });
  }
  return out;
}

/** One user turn, with its tag when it has one the PC knows. */
export function userMessage(content, provenance) {
  const tag = knownProvenance(provenance);
  return tag ? { role: "user", content, provenance: tag } : { role: "user", content };
}

/**
 * The tag on the words in the box, after one thing happened to the box.
 * The quickbar keeps one tag for its box and moves it here, so every rule is
 * in one place and tested without a browser (tests/chat-history.mjs):
 *
 * - `"clipboard"`: the clipboard hotkey put a short snippet in the box.
 * - `"paste"`: a `paste` or `drop` event on the box. It stays "pasted" until
 *   the box is empty again, however much is typed around it.
 * - `"edit"`: the owner changed the text by hand (an `input` event that was
 *   not a paste or a drop). An emptied box starts again as "typed"; an
 *   edited clipboard snippet or voice transcript is now the owner's typing.
 * - `"clear"`: the app emptied the box (sent, dismissed).
 *
 * @param {string} tag   the box's tag now
 * @param {string} what  one of the four above
 * @param {string} value the box's text after it happened
 */
export function boxTagAfter(tag, what, value = "") {
  if (what === "clipboard") return "clipboard";
  if (what === "paste") return "pasted";
  if (what === "clear") return "typed";
  if (what === "edit") {
    if (!value) return "typed";
    if (tag === "clipboard" || tag === "voice") return "typed";
  }
  return knownProvenance(tag) || "typed";
}

/**
 * The tag a turn is sent with. Words sent alongside a picture are a
 * "picture_caption" - unless they were pasted or came from the clipboard,
 * which stays said: those are not the owner's own words either way, and the
 * less trusted tag wins.
 */
export function sentProvenance(tag, hasPicture) {
  const known = knownProvenance(tag);
  if (!known) return null;
  if (hasPicture && (known === "typed" || known === "voice")) return "picture_caption";
  return known;
}
