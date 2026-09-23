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
 * the phone (`jarvis-client/.../net/ChatHistory.kt`), in line.
 *
 * What is kept: pairs of (the question as sent, the whole answer), plain
 * text, for answers that finished. No system turns, no screenshots, no tool
 * output, no approvals, no ids. A past answer that says "I have proposed
 * that" is only words; approvals are decided by id and nowhere else.
 *
 * Where: in this window's memory only. Never written to disk. Cleared by
 * "New conversation" and by dismissing the window with Esc - the same moment
 * the answer card itself is cleared.
 *
 * How much. The model has 16,384 tokens in all (jarvis-primary.Modelfile).
 * Set aside: 2,048 for the answer, 250 for the Modelfile's SYSTEM prompt and
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
 * Mirrors ChatHistory.kt number for number. Change one, change both.
 */

export const MAX_EXCHANGES = 10;
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
 * The newest pair is the last to go: it is kept alone if it is bigger than
 * KEEP_CHARS but inside MAX_CHARS, and dropped only when it is too big to
 * send at all.
 */
export function commitExchange(window, question, answer) {
  if (isBlank(question) || isBlank(answer)) return window;
  const next = [...window, { question, answer }];
  if (fits(next, MAX_EXCHANGES, MAX_CHARS)) return next;
  while (next.length > 1 && !fits(next, KEEP_EXCHANGES, KEEP_CHARS)) next.shift();
  return fits(next, MAX_EXCHANGES, MAX_CHARS) ? next : [];
}

/**
 * The window as OpenAI-shaped messages, oldest first: a user turn and an
 * assistant turn per pair, `role` and `content` only. The caller puts the
 * new question (and any system turns that belong to it alone) after these.
 */
export function historyMessages(window) {
  const out = [];
  for (const ex of window) {
    out.push({ role: "user", content: ex.question });
    out.push({ role: "assistant", content: ex.answer });
  }
  return out;
}
