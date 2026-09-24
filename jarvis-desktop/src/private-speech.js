/**
 * May the answer to a question asked BY VOICE be read aloud? The owner's
 * rule (docs/JARVIS-API.md section 16, "What the apps must do about
 * private answers"), as one function with no page in it
 * (tests/private-speech.mjs).
 *
 * With "private answers stay on screen" (the default), an answer drawn
 * from email, the calendar, notes or what Jarvis remembers is shown, and
 * not read aloud, unless the question was typed. So for a voice question
 * whose utterance reply said `private_aloud: false` - or did not say at
 * all, which is what an older PC sends - the answer is read aloud only
 * when nothing says it is private:
 *
 *   - `question_private` is not true (the words asked about something
 *     private: the router's private-topic list, plus notes and memory);
 *   - the chat reply's `X-Jarvis-Route` has no `gate: "private"`;
 *   - it has no `injected_facts` above 0 (remembered facts went in);
 *   - no tool ran while it was being written. The stream carries no
 *     tool receipt (section 4), so "a tool ran" is read from the only sign
 *     it gives: `: jarvis-status working` (a tool running) or `approval`
 *     (a tool's card waiting). A tool that finishes in under 1.5 seconds
 *     says neither (jarvis_agent.STATUS_DELAY_SECONDS) - that gap is the
 *     server's, and the doc says so.
 *
 * Otherwise Jarvis says one fixed line instead, `PRIVATE_LINE`, once.
 * `private_aloud: true` (the owner chose "voice check is enough", and the
 * very strict check passed) reads everything aloud as before.
 *
 * @module private-speech
 */

/** What Jarvis says instead of reading a private answer aloud. */
export const PRIVATE_LINE = "It's on your screen.";

/** The `: jarvis-status` words that mean a tool ran (or waited on a card). */
export const TOOL_WORDS = Object.freeze(["working", "approval"]);

/**
 * The privacy facts of one voice question, from the utterance reply
 * (`HeardReply`, camelCased by voice.rs): `{privateAloud, questionPrivate}`.
 * Anything missing reads as the refusing answer for `privateAloud` and as
 * "not said" for `questionPrivate`.
 */
export function privacyFromHeard(heard) {
  const h = heard && typeof heard === "object" ? heard : {};
  return {
    privateAloud: h.privateAloud === true,
    questionPrivate: h.questionPrivate === true,
  };
}

/**
 * May this answer be read aloud? `ctx`: `{privateAloud, questionPrivate}`
 * from the question, `route` (the route line's object: `gate`,
 * `injected_facts`) and `toolRan`.
 */
export function mayReadAloud(ctx) {
  const c = ctx && typeof ctx === "object" ? ctx : {};
  if (c.privateAloud === true) return true;
  if (c.questionPrivate === true) return false;
  const route = c.route && typeof c.route === "object" ? c.route : {};
  if (String(route.gate || "").trim().toLowerCase() === "private") return false;
  const facts = Number(route.injected_facts);
  if (Number.isFinite(facts) && facts > 0) return false;
  if (c.toolRan === true) return false;
  return true;
}
